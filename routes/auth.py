"""인증 — 로그인/로그아웃 + 앱 전역 인증 훅 + 보안 헤더 (app.py에서 분리, C2-9).

check_auth / add_no_cache는 before_app_request / after_app_request로 등록되어
블루프린트 소속과 무관하게 기존 app.before_request / app.after_request와 동일하게
모든 요청에 적용된다.
"""
import threading
import time
from functools import wraps

from flask import (Blueprint, jsonify, redirect, request, session, url_for)

from core.webdata import load_users

bp = Blueprint("auth", __name__)

# ── 로그인 시도 제한 (C3-13) ─────────────────────────────────────────
# (클라이언트IP, username) 키로 실패 5회 → 10분 잠금. 잠금 중 시도는
# 카운트/잠금 연장 없이 거부. 성공 시 카운터 초기화. 인메모리라 Flask
# 재시작 시 초기화됨 (단일 프로세스 launchd 운영이라 충분).
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 600  # 10분

_login_attempts = {}   # (ip, username) -> {"count", "locked_until", "last_at"}
_login_lock = threading.Lock()

# 테스트에서 시간 모킹이 가능하도록 간접 호출
_now = time.time


def _client_ip():
    """실제 클라이언트 IP.

    서비스는 Cloudflare Tunnel → localhost:5010이라 request.remote_addr은
    항상 로컬 주소다. 실제 클라이언트 IP는 CF-Connecting-IP 헤더에 있고,
    로컬 직접 접속(스테이징/테스트)에는 헤더가 없어 remote_addr로 폴백.
    """
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"


def _sweep_expired(now):
    """만료 엔트리 lazy 청소 — 호출자가 _login_lock을 잡은 상태여야 한다."""
    stale = [
        key for key, e in _login_attempts.items()
        if (e["locked_until"] and now >= e["locked_until"])          # 잠금 만료
        or (not e["locked_until"]
            and now - e["last_at"] > LOGIN_LOCKOUT_SECONDS)          # 오래된 실패
    ]
    for key in stale:
        del _login_attempts[key]


def _is_locked(ip, username):
    now = _now()
    with _login_lock:
        _sweep_expired(now)
        e = _login_attempts.get((ip, username))
        return bool(e and e["locked_until"] and now < e["locked_until"])


def _record_failure(ip, username):
    """실패 1회 기록. (누적 실패 수, 이번에 잠금 발동 여부)를 반환."""
    now = _now()
    with _login_lock:
        e = _login_attempts.setdefault(
            (ip, username), {"count": 0, "locked_until": 0.0, "last_at": now})
        e["count"] += 1
        e["last_at"] = now
        locked_now = False
        if e["count"] >= LOGIN_MAX_FAILURES and not e["locked_until"]:
            e["locked_until"] = now + LOGIN_LOCKOUT_SECONDS
            locked_now = True
        return e["count"], locked_now


def _clear_failures(ip, username):
    with _login_lock:
        _login_attempts.pop((ip, username), None)

# 조교(assistant)가 접근할 수 없는 경로 — 목업/채팅
ASSISTANT_BLOCKED_PATHS = ("/mockup", "/chat")
ASSISTANT_BLOCKED_API_PREFIXES = ("/api/mockup/",)


def _is_blocked_for_assistant(path):
    for p in ASSISTANT_BLOCKED_PATHS:
        if path == p or path.startswith(p + "/"):
            return True
    for p in ASSISTANT_BLOCKED_API_PREFIXES:
        if path.startswith(p):
            return True
    return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.is_json or request.path.startswith("/api/") or request.path.startswith("/chat/send") or request.path.startswith("/chat/watch"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated


@bp.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        ip = _client_ip()
        if _is_locked(ip, username):
            # 잠금 중 시도는 카운트/잠금 연장 없이 거부 (정답이어도 거부)
            print(f"[auth] 로그인 잠금 중 시도 거부: ip={ip} username={username!r}",
                  flush=True)
            error = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요"
        else:
            user = load_users().get(username)
            if user and user["password"] == pw:
                _clear_failures(ip, username)
                session["authenticated"] = True
                session["username"] = username
                session["role"] = user["role"]
                return redirect("/")
            count, locked_now = _record_failure(ip, username)
            print(f"[auth] 로그인 실패: ip={ip} username={username!r} "
                  f"(누적 {count}회{' — 10분 잠금 발동' if locked_now else ''})",
                  flush=True)
            error = "아이디 또는 비밀번호가 틀렸습니다"
    return '''
    <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>로그인 — Y.ONE DESIGN</title>
    <style>body{background:#111;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
    .box{background:#1a1a1a;padding:40px;border-radius:16px;text-align:center;min-width:280px}
    h2{margin:0 0 24px;font-size:18px;letter-spacing:.5px}
    h2 span{color:#6366f1}
    .field{margin-bottom:14px;text-align:left}
    .field label{display:block;font-size:12px;color:#9aa0a6;margin-bottom:6px;font-weight:500}
    input{width:100%%;box-sizing:border-box;padding:12px;border:1px solid #444;border-radius:8px;background:#111;color:#fff;font-size:14px;outline:none}
    button{width:100%%;padding:12px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:14px;cursor:pointer;margin-top:4px}
    .err{color:#f87171;font-size:12px;margin-bottom:8px}</style></head>
    <body><div class="box"><h2>Y.ONE <span>DESIGN</span></h2>
    ''' + (f'<div class="err">{error}</div>' if error else '') + '''
    <form method="POST">
    <div class="field"><label>아이디</label><input type="text" name="username" autofocus autocomplete="username"></div>
    <div class="field"><label>비밀번호</label><input type="password" name="password" autocomplete="current-password"></div>
    <button type="submit">로그인</button></form></div></body></html>
    '''


@bp.route("/logout")
def logout_page():
    session.clear()
    return redirect("/login")


@bp.before_app_request
def check_auth():
    # 로그인 페이지와 static 파일은 인증 불필요
    if request.path in ("/login", "/logout", "/api/health") or request.path.startswith("/static/"):
        return
    # 외부 공개 소개 페이지 (routes/pages.py /design — 가격 제외 단가표)
    if request.path == "/design" or request.path.startswith("/design/"):
        return
    # [임시 진단] /debug/* 인증 우회
    if request.path.startswith("/debug/"):
        return
    if not session.get("authenticated"):
        if request.is_json or request.path.startswith("/api/") or request.path.startswith("/chat/send") or request.path.startswith("/chat/watch"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect("/login")
    # 조교 권한 제한: 목업/채팅 접근 불가
    if session.get("role") == "assistant" and _is_blocked_for_assistant(request.path):
        if request.is_json or request.path.startswith("/api/") or request.path.startswith("/chat/send") or request.path.startswith("/chat/watch"):
            return jsonify({"error": "forbidden"}), 403
        return redirect("/")


@bp.after_app_request
def add_no_cache(response):
    if "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    response.headers["X-Served-By"] = "flask-live"
    # 내지 작업대의 미리보기는 **우리 화면이 우리 뷰어를 iframe 으로** 문다
    # (`/book-studio` → `/book-studio/viewer/…` → `/book-studio/doc/…`).
    # 기본값 `frame-ancestors 'none'` 이면 자기 자신도 못 물어 미리보기가 빈
    # 상자로 나온다 — 실제로 여기서 걸렸다. **같은 출처만** 열어 준다.
    _self_frame = request.path.startswith("/book-studio/viewer") or \
        request.path.startswith("/book-studio/doc")
    # ⚠ Vivliostyle 뷰어 번들은 CSS 를 계산할 때 문자열을 함수로 만든다(eval).
    #   기본 CSP 로는 그 자리에서 EvalError 가 나고 **지면이 영원히 안 그려진다**
    #   (증상은 '빈 상자'뿐이라 원인을 알기 어렵다 — 콘솔을 봐야 나온다).
    #   그래서 `'unsafe-eval'` 은 **뷰어 번들 경로에만** 준다. 이 번들은 우리가
    #   node_modules 에 고정해 둔 정적 파일이고 사용자 입력이 들어가지 않는다.
    #   앱의 다른 화면은 그대로 eval 금지다.
    _viewer = request.path.startswith("/book-studio/viewer")
    # ⚠ Vivliostyle 은 **기본 스타일시트를 `data:` URL 로 fetch 한다**(파일이
    #   아니라 번들 안에 문자열로 들어 있다). `connect-src 'self'` 로는 그게
    #   막히고, 콘솔에만 조용히 남는다 — 지면은 그려지지만 기본 규칙이 빠진
    #   채로 그려진다. 작업대 경로에만 `data:` 를 연다.
    _studio = request.path.startswith("/book-studio")
    # ── 보안 헤더 ──
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if _self_frame else "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), interest-cohort=(), "
        "payment=(), usb=(), accelerometer=(), gyroscope=(), magnetometer=(), "
        "midi=(), fullscreen=(self), display-capture=()"
    )
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
    # ── Content Security Policy (인라인 스크립트/스타일 사용 중이라 unsafe-inline 허용) ──
    # localhost/127.0.0.1 접근 시에는 upgrade-insecure-requests 제외 — 로컬은 HTTP라
    # 이 지시문이 켜지면 fetch가 https://localhost:5010 으로 강제 업그레이드되어 실패.
    _host = (request.host or "").split(":")[0]
    _is_local = _host in ("localhost", "127.0.0.1", "::1")
    _csp = (
        "default-src 'self'; "
        + ("script-src 'self' 'unsafe-inline' 'unsafe-eval'; " if _viewer
           else "script-src 'self' 'unsafe-inline'; ") +
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        + ("connect-src 'self' data:; " if _studio
           else "connect-src 'self'; ") +
        "media-src 'self' blob:; "
        "object-src 'none'; "
        + ("frame-ancestors 'self'; " if _self_frame else "frame-ancestors 'none'; ") +
        "form-action 'self'; "
        "base-uri 'self'"
    )
    if not _is_local:
        _csp += "; upgrade-insecure-requests"
    response.headers["Content-Security-Policy"] = _csp
    # 캐시된 자격증명으로 뒤로가기 방지
    response.headers["Clear-Site-Data"] = '"cache"' if response.status_code == 401 else response.headers.get("Clear-Site-Data", "")
    if not response.headers["Clear-Site-Data"]:
        del response.headers["Clear-Site-Data"]
    return response
