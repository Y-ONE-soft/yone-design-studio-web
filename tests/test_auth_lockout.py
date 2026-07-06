"""로그인 시도 제한 (C3-13) — (클라이언트IP, username) 키 실패 5회 → 10분 잠금.

라우트 추가 없이 기존 /login POST 내부에서만 동작하므로 url_map 파리티에
영향 없다. 시간 경과는 routes.auth._now 를 모킹해 검증한다.
"""
import os

import pytest

os.environ.setdefault("YONE_SECRET_KEY", "test-secret-key")
os.environ["YONE_ADMIN_PASSWORD"] = "test-admin-pw"
os.environ["YONE_ASSISTANT_PASSWORD"] = "test-assist-pw"

import app as app_module  # noqa: E402
from routes import auth as auth_module  # noqa: E402

LOCK_MSG = "잠시 후 다시 시도"
FAIL_MSG = "아이디 또는 비밀번호가 틀렸습니다"


def _reset_limiter():
    with auth_module._login_lock:
        auth_module._login_attempts.clear()


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    _reset_limiter()
    with app_module.app.test_client() as c:
        yield c
    _reset_limiter()   # 다른 테스트 파일(test_auth_users 등)에 잠금 누수 방지


def _login(client, username, password, ip=None):
    headers = {"CF-Connecting-IP": ip} if ip else {}
    return client.post("/login", data={"username": username, "password": password},
                       headers=headers)


# ── 5회 실패 → 잠금 ──────────────────────────────────────────────────

def test_five_failures_lock(client):
    for _ in range(4):
        r = _login(client, "admin", "wrong-pw")
        body = r.get_data(as_text=True)
        assert FAIL_MSG in body and LOCK_MSG not in body
    # 5번째 실패까지는 일반 오류 문구 (잠금은 이후 시도부터 적용)
    r = _login(client, "admin", "wrong-pw")
    assert FAIL_MSG in r.get_data(as_text=True)
    # 6번째부터 잠금 문구
    r = _login(client, "admin", "wrong-pw")
    body = r.get_data(as_text=True)
    assert LOCK_MSG in body and FAIL_MSG not in body


def test_locked_rejects_correct_password(client):
    for _ in range(5):
        _login(client, "admin", "wrong-pw")
    r = _login(client, "admin", "test-admin-pw")
    assert r.status_code == 200                      # 302 리다이렉트 아님
    assert LOCK_MSG in r.get_data(as_text=True)
    with client.session_transaction() as s:
        assert not s.get("authenticated")


def test_locked_attempt_does_not_extend_lock(client):
    for _ in range(5):
        _login(client, "admin", "wrong-pw")
    with auth_module._login_lock:
        e = dict(auth_module._login_attempts[("127.0.0.1", "admin")])
    _login(client, "admin", "wrong-pw")              # 잠금 중 시도
    with auth_module._login_lock:
        e2 = auth_module._login_attempts[("127.0.0.1", "admin")]
        assert e2["count"] == e["count"]
        assert e2["locked_until"] == e["locked_until"]


# ── 10분 경과 후 해제 (시간 모킹) ────────────────────────────────────

def test_lock_expires_after_10min(client, monkeypatch):
    for _ in range(5):
        _login(client, "admin", "wrong-pw")
    r = _login(client, "admin", "test-admin-pw")
    assert LOCK_MSG in r.get_data(as_text=True)      # 잠금 중엔 정답도 거부

    real_now = auth_module._now()
    monkeypatch.setattr(auth_module, "_now",
                        lambda: real_now + auth_module.LOGIN_LOCKOUT_SECONDS + 1)
    r = _login(client, "admin", "test-admin-pw")
    assert r.status_code == 302                      # 해제 → 정상 로그인
    with client.session_transaction() as s:
        assert s.get("authenticated") is True
    with auth_module._login_lock:                    # lazy sweep으로 엔트리 제거
        assert ("127.0.0.1", "admin") not in auth_module._login_attempts


# ── 성공 시 카운터 초기화 ────────────────────────────────────────────

def test_success_resets_counter(client):
    for _ in range(4):
        _login(client, "admin", "wrong-pw")
    r = _login(client, "admin", "test-admin-pw")
    assert r.status_code == 302
    with auth_module._login_lock:
        assert ("127.0.0.1", "admin") not in auth_module._login_attempts
    client.get("/logout")
    # 초기화됐으므로 다시 4회 실패해도 잠금 아님
    for _ in range(4):
        r = _login(client, "admin", "wrong-pw")
        assert FAIL_MSG in r.get_data(as_text=True)
    r = _login(client, "admin", "test-admin-pw")
    assert r.status_code == 302


# ── CF-Connecting-IP 헤더로 클라이언트 구분 ──────────────────────────

def test_cf_connecting_ip_separates_clients(client):
    for _ in range(5):
        _login(client, "admin", "wrong-pw", ip="203.0.113.10")
    # 같은 IP → 잠금
    r = _login(client, "admin", "test-admin-pw", ip="203.0.113.10")
    assert LOCK_MSG in r.get_data(as_text=True)
    # 다른 IP → 영향 없음 (터널 뒤 전 사용자가 하나로 묶이지 않아야 함)
    r = _login(client, "admin", "test-admin-pw", ip="198.51.100.7")
    assert r.status_code == 302


def test_keys_are_per_username_too(client):
    for _ in range(5):
        _login(client, "admin", "wrong-pw")
    # 같은 IP라도 다른 username은 별도 카운터
    r = _login(client, "assistant", "test-assist-pw")
    assert r.status_code == 302
