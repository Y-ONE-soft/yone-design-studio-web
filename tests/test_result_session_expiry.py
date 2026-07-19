"""/api/result 세션 만료 401 — 게이트 critical 미전달 사고 재현 (W30 후속).

실증 (job 376b34d0, 2026-07-19 22:19~22:32 운영 로그): 장시간 조판 중
로그인 세션이 12시간 절대 만료를 넘기면 SSE(/api/stream)는 연결 시점
인증만 통과해 로그를 계속 흘리지만, [DONE] 후의 /api/result 폴링은 401
{"error": "unauthorized"}를 받는다 — 종전 typeset.js는 이를 '결과 아직
없음'으로 오분류해 21회(초기+재시도 20) 폴링 후 "알 수 없는 오류"만
표시했고, verify 게이트 critical이 사용자에게 도달하지 못했다.

만료 메커니즘 (Flask 3.x 실측): SecureCookieSessionInterface.open_session이
비영구(non-permanent) 세션에도 max_age=PERMANENT_SESSION_LIFETIME(12h)을
적용하고, 비영구 세션 쿠키는 로그인 시 1회만 발급된다(요청마다 재발급
없음 — should_set_cookie는 session.modified만 봄). 즉 로그인 시각 기준
절대 12시간 후 모든 요청의 쿠키 서명이 SignatureExpired → 익명 세션 →
/api/* 는 401.

수리는 프론트(static/js/typeset.js) — 401 명시 감지 + 재로그인 안내 카드 +
job_id localStorage 보관 + 재로그인 복귀 시 자동 결과 복원. 라우트·세션
정책은 무변경 (보안 약화 없음 — 이 파일이 401 유지를 가드한다).
라우트 추가 없음 → url_map 파리티(test_route_parity) 무영향.
"""
import os
import time

import itsdangerous
import pytest

os.environ.setdefault("YONE_SECRET_KEY", "test-secret-key")
os.environ.setdefault("YONE_ADMIN_PASSWORD", "test-admin-pw")
os.environ.setdefault("YONE_ASSISTANT_PASSWORD", "test-assist-pw")

import app as app_module  # noqa: E402
import core.job_manager as jm  # noqa: E402

EXPIRE_SKEW = 13 * 3600   # 12시간 한도 초과
VALID_SKEW = 11 * 3600    # 12시간 한도 이내


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # job 디렉터리를 tmp로 격리 (리포 jobs/ 오염 방지)
    monkeypatch.setattr(jm, "JOBS_DIR", str(tmp_path))
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def _login(client, monkeypatch=None, skew=0):
    """로그인 — skew>0이면 세션 쿠키를 skew초 과거 타임스탬프로 서명
    (itsdangerous TimestampSigner.get_timestamp 패치, 로그인 요청 동안만)."""
    if skew:
        orig = itsdangerous.TimestampSigner.get_timestamp
        monkeypatch.setattr(itsdangerous.TimestampSigner, "get_timestamp",
                            lambda self: int(time.time()) - skew)
        try:
            r = client.post("/login", data={"username": "admin",
                                            "password": "test-admin-pw"})
        finally:
            monkeypatch.setattr(itsdangerous.TimestampSigner,
                                "get_timestamp", orig)
    else:
        r = client.post("/login", data={"username": "admin",
                                        "password": "test-admin-pw"})
    assert r.status_code == 302
    return r


def _done_job_with_critical():
    """게이트 critical을 포함한 완료 job (파이프라인 verify 결과 모사)."""
    job_id = jm.create_job("textbook_workbook_v2")
    jm.done(job_id, {
        "ok": False,
        "overflow": 0,
        "warnings": ["[글리프커버리지] 적용 폰트가 글리프 미지원 12건"],
        "critical": ["[프레임결손] 스토리 58 중간 페이지 프레임 결손"],
    })
    return job_id


# ── 정상 세션: 결과 + 게이트 경고 전달 계약 ──────────────────────────────

def test_result_delivers_gate_findings_with_valid_session(client, monkeypatch):
    _login(client, monkeypatch)
    job_id = _done_job_with_critical()
    r = client.get(f"/api/result/{job_id}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "done"
    assert body["result"]["critical"], "게이트 critical이 결과 페이로드에 있어야 함"
    assert body["result"]["warnings"]


def test_result_ok_within_12h(client, monkeypatch):
    """11시간 경과 쿠키는 아직 유효 — 만료 경계가 정확히 12h임을 실증."""
    _login(client, monkeypatch, skew=VALID_SKEW)
    job_id = _done_job_with_critical()
    r = client.get(f"/api/result/{job_id}")
    assert r.status_code == 200
    assert r.get_json()["status"] == "done"


# ── 사고 재현: 12시간 초과 세션 → 401 ────────────────────────────────────

def test_result_401_after_session_expiry(client, monkeypatch):
    """로그인 12시간 후 폴링 = 401 {"error":"unauthorized"} (job 376b34d0
    재현). 프론트가 이 응답을 명시 처리하므로 라우트는 401 유지가 정답
    (인증 우회·세션 연장 없음 — 이 어서션이 보안 약화를 가드)."""
    _login(client, monkeypatch, skew=EXPIRE_SKEW)
    job_id = _done_job_with_critical()
    r = client.get(f"/api/result/{job_id}")
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_stream_also_401_after_expiry(client, monkeypatch):
    """SSE 재연결도 만료 후엔 401 — EventSource onerror → fetchResult 경유로
    같은 401 처리 흐름에 합류함을 뒷받침."""
    _login(client, monkeypatch, skew=EXPIRE_SKEW)
    job_id = _done_job_with_critical()
    r = client.get(f"/api/stream/{job_id}")
    assert r.status_code == 401


def test_relogin_recovers_result(client, monkeypatch):
    """만료 → 재로그인 → 같은 job_id 재조회로 결과·게이트 경고 회복
    (프론트 localStorage 복원 흐름의 서버측 전제: 결과는 인메모리 보관)."""
    _login(client, monkeypatch, skew=EXPIRE_SKEW)
    job_id = _done_job_with_critical()
    assert client.get(f"/api/result/{job_id}").status_code == 401
    _login(client, monkeypatch)   # 재로그인 (새 쿠키)
    r = client.get(f"/api/result/{job_id}")
    assert r.status_code == 200
    assert r.get_json()["result"]["critical"]


# ── job 소멸(서버 재시작): 404 계약 ──────────────────────────────────────

def test_result_404_json_for_unknown_job(client, monkeypatch):
    """프론트 404 분기(재시도 없이 안내)가 의존하는 계약 가드."""
    _login(client, monkeypatch)
    r = client.get("/api/result/no-such-job")
    assert r.status_code == 404
    assert r.get_json() == {"error": "job not found"}
