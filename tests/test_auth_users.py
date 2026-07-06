"""인증/사용자 구조 (C2-8) — data/users.json 로드 + 로그인 동작.

app 모듈 import 전에 반드시 환경변수를 넣어야 한다 (YONE_SECRET_KEY 미설정 시
app.py가 RuntimeError로 기동 거부). 사용자 로더는 core/webdata.py (C2-9 분리 후).
"""
import os

import pytest

os.environ.setdefault("YONE_SECRET_KEY", "test-secret-key")
os.environ["YONE_ADMIN_PASSWORD"] = "test-admin-pw"
os.environ["YONE_ASSISTANT_PASSWORD"] = "test-assist-pw"

import app as app_module  # noqa: E402
from core import webdata  # noqa: E402


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


# ── load_users ───────────────────────────────────────────────────────

def test_load_users_from_json():
    users = webdata.load_users()
    assert set(users) >= {"admin", "assistant"}
    assert users["admin"]["role"] == "admin"
    assert users["admin"]["password"] == "test-admin-pw"
    assert users["assistant"]["role"] == "assistant"
    assert users["assistant"]["password"] == "test-assist-pw"


def test_load_users_fallback_when_file_missing(monkeypatch):
    # users.json 부재 → read_json_cached가 default(내장 스펙)를 반환 (fail-open)
    missing = os.path.join(webdata.DATA_DIR, "__no_such_users__.json")
    monkeypatch.setattr(webdata, "USERS_FILE", missing)
    try:
        users = webdata.load_users()
    finally:
        webdata.invalidate_json_cache(missing)
    assert set(users) == {"admin", "assistant"}
    assert users["admin"]["password"] == "test-admin-pw"


def test_load_users_fallback_when_spec_malformed(monkeypatch):
    # 파손된 스펙(유효 항목 0) → 내장 기본값으로 폴백
    monkeypatch.setattr(webdata, "read_json_cached",
                        lambda path, default: {"broken": True})
    users = webdata.load_users()
    assert set(users) == {"admin", "assistant"}
    assert users["admin"]["role"] == "admin"


def test_resolve_users_spec_skips_invalid_entries():
    users = webdata.resolve_users_spec([
        {"username": "ok", "role": "admin", "password_env": "YONE_ADMIN_PASSWORD"},
        {"role": "admin"},          # username 없음 → 스킵
        "not-a-dict",               # dict 아님 → 스킵
        {"username": "norole", "password_env": "YONE_ADMIN_PASSWORD"},
    ])
    assert set(users) == {"ok", "norole"}
    assert users["norole"]["role"] == "assistant"   # role 기본값


def test_users_json_never_contains_password():
    # 보안 게이트: users.json 자체에 password 키/실비밀번호가 없어야 함
    import json
    with open(webdata.USERS_FILE, encoding="utf-8") as f:
        spec = json.load(f)
    for u in spec:
        assert "password" not in u
        assert set(u) <= {"username", "role", "password_env"}


# ── 로그인 동작 (Flask test client) ──────────────────────────────────

def test_admin_login_success(client):
    r = client.post("/login", data={"username": "admin",
                                    "password": "test-admin-pw"})
    assert r.status_code == 302
    assert r.headers["Location"] in ("/", "http://localhost/")
    with client.session_transaction() as s:
        assert s["authenticated"] is True
        assert s["username"] == "admin"
        assert s["role"] == "admin"


def test_assistant_login_success_and_role(client):
    r = client.post("/login", data={"username": "assistant",
                                    "password": "test-assist-pw"})
    assert r.status_code == 302
    with client.session_transaction() as s:
        assert s["authenticated"] is True
        assert s["role"] == "assistant"


def test_wrong_password_fails(client):
    r = client.post("/login", data={"username": "admin",
                                    "password": "wrong-pw"})
    assert r.status_code == 200
    assert "아이디 또는 비밀번호가 틀렸습니다" in r.get_data(as_text=True)
    with client.session_transaction() as s:
        assert not s.get("authenticated")


def test_unknown_user_fails(client):
    r = client.post("/login", data={"username": "nobody",
                                    "password": "test-admin-pw"})
    assert r.status_code == 200
    with client.session_transaction() as s:
        assert not s.get("authenticated")


def test_unauthenticated_page_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_unauthenticated_api_returns_401(client):
    r = client.get("/api/schools")
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_health_open_without_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json().get("ok") is True


def test_assistant_blocked_from_mockup(client):
    client.post("/login", data={"username": "assistant",
                                "password": "test-assist-pw"})
    r = client.get("/mockup")
    assert r.status_code == 302          # 페이지 → "/"로 리다이렉트
    r = client.post("/api/mockup/upload")
    assert r.status_code == 403          # API → 403
