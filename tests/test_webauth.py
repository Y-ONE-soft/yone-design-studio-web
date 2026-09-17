# -*- coding: utf-8 -*-
"""core/webauth — Y.OS 링크 토큰(HMAC) · 서비스 토큰 · 세션 쿠키 · 임베드 토큰 · CORS.

Chromium·Vivliostyle 없이 Flask 테스트 클라이언트만으로 돈다.
"""
import importlib
import os
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ENV = ("YONE_AUTH", "YOS_LINK_SECRET", "YOS_LOGIN_URL", "SERVICE_TOKEN", "YOS_SERVICE_TOKENS",
        "YOS_ORIGINS", "YONE_SECRET_KEY", "YONE_ALLOWED_ROLES", "YONE_COOKIE_SECURE",
        "YONE_STUDIO_ROOT", "BLOB_READ_WRITE_TOKEN")


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("YONE_STUDIO_ROOT", str(tmp_path))
    return monkeypatch


def _app():
    import studio_server
    importlib.reload(studio_server)
    app = studio_server.create_app()
    app.config["TESTING"] = True
    return app


SECRET = "s3cret-s3cret-s3cret-s3cret-s3cret"


def _tok(secret=SECRET, ttl=600, **user):
    """Y.OS 의 signWidgetToken 과 같은 꼴: base64url(JSON{u,e,n,m,r}) . base64url(HMAC)."""
    import base64, hashlib, hmac, json
    u = {"sub": "u1", "email": "a@b.c", "name": "A", "role": "designer"}
    u.update(user)
    payload = {"u": u["sub"], "e": int(time.time() * 1000) + ttl * 1000, "n": u["name"], "m": u["email"],
               "r": u["role"]}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    mac = base64.urlsafe_b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return body + "." + mac


def test_off_mode_passes_everything(env):
    app = _app()
    c = app.test_client()
    r = c.get("/auth/me")
    assert r.status_code == 200 and r.get_json()["mode"] == "off"
    assert c.get("/api/v1/catalog").status_code == 200
    # 로컬은 보안 헤더로 화면을 바꾸지 않는다
    assert "Content-Security-Policy" not in c.get("/catalog").headers


def test_link_mode_blocks_without_token(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    env.setenv("YOS_LOGIN_URL", "https://core.example/login")
    app = _app()
    c = app.test_client()
    r = c.get("/api/v1/catalog")
    assert r.status_code == 401 and r.get_json()["login"] == "https://core.example/login"
    r = c.get("/catalog", headers={"Accept": "text/html"})
    assert r.status_code == 302 and r.headers["Location"].startswith("https://core.example/login?next=")
    assert c.get("/api/v1/health").status_code == 200        # 공개


def test_bearer_token_and_bad_token(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    app = _app()
    c = app.test_client()
    ok = c.get("/auth/me", headers={"Authorization": "Bearer " + _tok()})
    assert ok.get_json()["user"]["sub"] == "u1" and ok.get_json()["user"]["role"] == "designer"
    assert ok.get_json()["mode"] == "link"
    bad = c.get("/api/v1/catalog", headers={"Authorization": "Bearer " + _tok(secret="wrong-wrong-wrong-wrong-wrong-wrong")})
    assert bad.status_code == 401
    expired = c.get("/api/v1/catalog", headers={"Authorization": "Bearer " + _tok(ttl=-5)})
    assert expired.status_code == 401
    assert c.get("/api/v1/catalog", headers={"Authorization": "Bearer " + _tok()}).status_code == 200


def test_link_token_matches_yos_helper_shape(env):
    """스튜디오가 만드는 표와 Y.OS(signWidgetToken 꼴) 표가 서로 통한다."""
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    from core import webauth
    app = _app()
    with app.test_request_context():
        mine = webauth.make_link_token({"sub": "u7", "name": "나", "email": "n@y.os", "role": "staff"})
        u = webauth.verify_link_token(mine)
        assert u["sub"] == "u7" and u["role"] == "staff" and u["via"] == "link"
        u2 = webauth.verify_link_token(_tok(sub="u8"))
        assert u2["sub"] == "u8"
        for bad in ("", "abc", "a.b.c", _tok() + "x"):
            with pytest.raises(webauth.AuthError):
                webauth.verify_link_token(bad)


def test_callback_sets_session_cookie(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    app = _app()
    c = app.test_client()
    r = c.get("/auth/callback?token=" + _tok() + "&next=/catalog")
    assert r.status_code == 302 and r.headers["Location"].endswith("/catalog")
    assert "yone_session=" in r.headers.get("Set-Cookie", "")
    # 쿠키만으로 통과
    assert c.get("/api/v1/catalog").status_code == 200
    me = c.get("/auth/me").get_json()
    assert me["user"]["via"] == "cookie" and me["user"]["sub"] == "u1"
    # next 는 이 서버 안 경로만
    r = c.get("/auth/callback?token=" + _tok() + "&next=https://evil.example/")
    assert r.headers["Location"].endswith("/catalog")
    c.post("/auth/logout")
    assert c.get("/api/v1/catalog").status_code == 401


def test_allowed_roles(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    env.setenv("YONE_ALLOWED_ROLES", "admin,designer")
    c = _app().test_client()
    assert c.get("/api/v1/catalog", headers={"Authorization": "Bearer " + _tok(role="student")}).status_code == 403
    assert c.get("/api/v1/catalog", headers={"Authorization": "Bearer " + _tok(role="admin")}).status_code == 200


def test_service_token(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    env.setenv("SERVICE_TOKEN", "tokA, tokB")
    c = _app().test_client()
    r = c.get("/auth/me", headers={"Authorization": "Bearer tokB"})
    assert r.get_json()["user"]["role"] == "service"
    assert c.get("/api/v1/catalog", headers={"Authorization": "Bearer tokC"}).status_code == 401


def test_embed_token_flow(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    env.setenv("SERVICE_TOKEN", "svc")
    env.setenv("YOS_ORIGINS", "https://contents.example")
    env.setenv("YONE_PUBLIC_URL", "https://studio.example")
    app = _app()
    svc = app.test_client()
    r = svc.post("/api/v1/embed-token", json={"next": "/book-studio?b=abc", "ttl": 60,
                                              "user": {"sub": "u9", "name": "조교", "role": "staff"}},
                 headers={"Authorization": "Bearer svc"})
    assert r.status_code == 200
    url = r.get_json()["url"]
    assert url.startswith("https://studio.example/auth/embed?t=")
    # 새 브라우저(iframe)가 그 주소를 연다 → 쿠키 → next
    browser = app.test_client()
    r = browser.get(url.replace("https://studio.example", ""))
    assert r.status_code == 302 and r.headers["Location"].endswith("/book-studio?b=abc")
    assert browser.get("/auth/me").get_json()["user"]["sub"] == "u9"
    # 바깥 주소는 거절
    r = svc.post("/api/v1/embed-token", json={"next": "https://evil.example"},
                 headers={"Authorization": "Bearer svc"})
    assert r.status_code == 400
    # 임베드 경로는 contents 출처의 iframe 을 허용, 다른 경로는 막는다
    r = browser.get("/api/v1/health")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    r = browser.get("/book-studio")
    assert "frame-ancestors 'self' https://contents.example" in r.headers["Content-Security-Policy"]
    assert "X-Frame-Options" not in r.headers


def test_cors_for_allowed_origin(env):
    env.setenv("YOS_LINK_SECRET", SECRET)
    env.setenv("YONE_SECRET_KEY", "k" * 32)
    env.setenv("YOS_ORIGINS", "https://contents.example")
    c = _app().test_client()
    pre = c.options("/api/v1/renders", headers={"Origin": "https://contents.example",
                                                 "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 204
    assert pre.headers["Access-Control-Allow-Origin"] == "https://contents.example"
    assert "Authorization" in pre.headers["Access-Control-Allow-Headers"]
    r = c.get("/api/v1/health", headers={"Origin": "https://other.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_refuses_public_host_without_auth(env, monkeypatch):
    import studio_server
    importlib.reload(studio_server)
    monkeypatch.setattr("sys.argv", ["studio_server.py", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit) as e:
        studio_server.main()
    assert e.value.code == 2
