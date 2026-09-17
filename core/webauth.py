# -*- coding: utf-8 -*-
"""Y.OS 계정으로 스튜디오를 지킨다 — **로그인 화면은 Y.OS 에 있고, 여기는 표(토큰)만 검사한다.**

Y.OS 앱들(core·contents·design)은 Auth.js(구글)로 로그인하고, 앱 사이는 **공유 비밀로 서명한 표**를
주고받는다(core `src/server/widget/token.ts` 의 `signWidgetToken`, `CHAT_LINK_SECRET`). 스튜디오도 같은 꼴이다:

    payload = base64url(JSON {u: 사용자id, e: 만료(ms), n?: 이름, m?: 이메일, r?: 역할})
    token   = payload + "." + base64url(HMAC-SHA256(YOS_LINK_SECRET, payload))

세 가지 신원이 들어온다.
    사람(브라우저)   Y.OS 가 만든 표를 `/auth/callback?token=…&next=…` 로 한 번 가져오면
                     이 서버가 서명한 세션 쿠키로 바꿔 준다(표 수명이 짧아도 작업이 안 끊긴다).
    사람(API·앱)     `Authorization: Bearer <표>` 매 요청.
    시스템(contents·core·design)  `Authorization: Bearer <SERVICE_TOKEN>` → role=service
                     (yos-typeset 의 SERVICE_TOKEN 과 같은 규칙).

환경변수
    YOS_LINK_SECRET      표 서명 비밀 — Y.OS 쪽 STUDIO_LINK_SECRET 과 **같은 값**. 있으면 인증이 켜진다
    SERVICE_TOKEN        시스템 간 토큰(콤마로 여러 개). Y.OS 쪽 STUDIO_SERVICE_TOKEN 과 같은 값
    YOS_LOGIN_URL        미인증 브라우저를 보낼 곳(Y.OS 의 스튜디오 진입 라우트). `?next=<돌아올 URL>` 을 붙인다
    YOS_ORIGINS          CORS · iframe 허용 출처(콤마) 예: https://yos-contents-web.vercel.app,https://yos-design-web.vercel.app
    YONE_SECRET_KEY      세션 쿠키·임베드 토큰 서명 키 — 인증 켠 상태에서 **필수**
    YONE_AUTH            off | link   기본: YOS_LINK_SECRET 이 있으면 link, 없으면 off(로컬)
    YONE_SESSION_HOURS   세션 쿠키 수명(기본 12)
    YONE_ALLOWED_ROLES   (선택) 이 역할만 통과(콤마). 비우면 로그인한 누구나
    YONE_COOKIE_SECURE   1 이면 https 뒤가 아니어도 Secure 쿠키(프록시가 TLS 를 벗기는 경우 — Fly 가 그렇다)
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse

from flask import Blueprint, g, jsonify, make_response, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = "yone_session"
bp = Blueprint("webauth", __name__)

_PUBLIC_PREFIX = ("/auth/", "/static/")
_PUBLIC_EXACT = ("/api/health", "/api/v1/health", "/healthz", "/favicon.ico")
# 이 경로들은 contents 화면 안 iframe 으로 들어갈 수 있다(작업대·지면·PDF)
_EMBEDDABLE = ("/book-studio", "/embed/", "/catalog/out/", "/api/v1/renders/")


class AuthError(Exception):
    pass


# ── 설정 ────────────────────────────────────────────────────────
def _env(k, default=""):
    return (os.environ.get(k) or default).strip()


def mode():
    m = _env("YONE_AUTH").lower()
    if m in ("off", "link"):
        return m
    return "link" if _env("YOS_LINK_SECRET") else "off"


def origins():
    return [o.strip().rstrip("/") for o in _env("YOS_ORIGINS").split(",") if o.strip()]


def _service_tokens():
    raw = _env("SERVICE_TOKEN") or _env("YOS_SERVICE_TOKENS")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _allowed_roles():
    return {r.strip() for r in _env("YONE_ALLOWED_ROLES").split(",") if r.strip()}


def _secret(app):
    s = _env("YONE_SECRET_KEY")
    if s:
        return s
    if mode() == "link":
        raise RuntimeError("인증이 켜졌는데(YOS_LINK_SECRET) YONE_SECRET_KEY 가 없다 — 세션 쿠키를 서명할 수 없다")
    # 로컬(off): 프로세스마다 임의 키. 쿠키를 쓰지 않으니 상관없다.
    return app.secret_key or secrets.token_hex(32)


def _serializer(salt):
    from flask import current_app
    return URLSafeTimedSerializer(current_app.secret_key, salt=salt)


# ── Y.OS 링크 토큰 ───────────────────────────────────────────────
def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64url(t):
    t = t.strip()
    return base64.urlsafe_b64decode(t + "=" * (-len(t) % 4))


def make_link_token(user, ttl_seconds=8 * 3600, secret=None):
    """Y.OS 가 만드는 것과 같은 표. 테스트·수동 발급용 (Y.OS 쪽 구현은 signWidgetToken 과 같다)."""
    secret = secret if secret is not None else _env("YOS_LINK_SECRET")
    payload = {"u": user["sub"], "e": int(time.time() * 1000) + int(ttl_seconds * 1000)}
    for src, dst in (("name", "n"), ("email", "m"), ("role", "r")):
        if user.get(src):
            payload[dst] = user[src]
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    mac = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + mac


def verify_link_token(token):
    """`payload.mac` → 사용자 dict. 틀리면 AuthError."""
    secret = _env("YOS_LINK_SECRET")
    if not secret:
        raise AuthError("YOS_LINK_SECRET 이 없다 — 표를 검증할 수 없다")
    if not token or token.count(".") != 1:
        raise AuthError("표 모양이 아니다 (payload.mac)")
    body, mac = token.split(".", 1)
    want = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, want):
        raise AuthError("표 서명이 맞지 않는다")
    try:
        c = json.loads(_unb64url(body).decode("utf-8"))
    except Exception:
        raise AuthError("표 내용을 읽을 수 없다")
    if not isinstance(c, dict) or not c.get("u"):
        raise AuthError("표에 사용자(u)가 없다")
    exp = c.get("e")
    if not isinstance(exp, (int, float)) or exp < time.time() * 1000:
        raise AuthError("표가 만료됐다")
    return {"sub": str(c["u"]), "email": c.get("m"), "name": c.get("n") or c.get("m") or str(c["u"]),
            "role": c.get("r") or "user", "via": "link"}


def _bearer():
    h = request.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return ""


def _identify():
    """요청의 신원. 순서: 서비스 토큰 → Bearer JWT → 세션 쿠키. 없으면 None."""
    tok = _bearer()
    if tok:
        if tok in _service_tokens():
            return {"sub": "service", "name": "service", "role": "service", "via": "service"}
        return verify_link_token(tok)
    c = request.cookies.get(COOKIE)
    if c:
        try:
            hours = float(_env("YONE_SESSION_HOURS", "12"))
            return _serializer("session").loads(c, max_age=int(hours * 3600))
        except SignatureExpired:
            raise AuthError("세션이 만료됐다")
        except BadSignature:
            raise AuthError("세션 쿠키가 이상하다")
    return None


def current_user():
    return getattr(g, "user", None)


def is_service():
    u = current_user()
    return bool(u and u.get("via") == "service")


# ── 쿠키·임베드 토큰 ────────────────────────────────────────────
def _cookie_secure():
    return _env("YONE_COOKIE_SECURE") == "1" or request.is_secure


def set_session(resp, user):
    hours = float(_env("YONE_SESSION_HOURS", "12"))
    user = {k: user.get(k) for k in ("sub", "email", "name", "role")}
    user["via"] = "cookie"
    secure = _cookie_secure()
    # iframe(contents 안)에서도 쿠키가 실리려면 SameSite=None + Secure 여야 한다.
    resp.set_cookie(COOKIE, _serializer("session").dumps(user), max_age=int(hours * 3600),
                    httponly=True, secure=secure, samesite="None" if secure else "Lax", path="/")
    return resp


def clear_session(resp):
    resp.delete_cookie(COOKIE, path="/")
    return resp


def make_embed_token(next_path, user, ttl=300):
    """contents 가 iframe 에 넣을 **일회성 짧은 주소**의 토큰. `/auth/embed?t=…` 가 받는다."""
    if not next_path.startswith("/") or next_path.startswith("//"):
        raise ValueError("next 는 이 서버 안의 경로여야 한다")
    payload = {"next": next_path, "user": {k: user.get(k) for k in ("sub", "email", "name", "role")},
               "ttl": int(ttl)}
    return _serializer("embed").dumps(payload)


def _safe_next(n, default="/catalog"):
    n = (n or "").strip()
    if not n.startswith("/") or n.startswith("//") or "\\" in n:
        return default
    return n


# ── 라우트 ──────────────────────────────────────────────────────
@bp.route("/auth/callback", methods=["GET", "POST"])
def callback():
    """Y.OS 로그인 뒤 여기로: `?token=<표>&next=/catalog` (또는 POST JSON {token, next})."""
    body = request.get_json(silent=True) or {}
    token = (request.args.get("token") or request.form.get("token") or body.get("token") or "").strip()
    nxt = _safe_next(request.args.get("next") or request.form.get("next") or body.get("next"))
    if not token:
        return jsonify({"error": "token 이 없다"}), 400
    try:
        user = verify_link_token(token)
    except AuthError as e:
        return jsonify({"error": str(e)}), 401
    if _allowed_roles() and user.get("role") not in _allowed_roles():
        return jsonify({"error": f"이 역할은 스튜디오를 쓸 수 없다: {user.get('role')}"}), 403
    if request.method == "POST" and not request.form:
        return set_session(jsonify({"ok": True, "user": user, "next": nxt}), user)
    return set_session(redirect(nxt), user)


@bp.route("/auth/embed")
def embed():
    """contents 의 iframe 이 처음 여는 주소. 토큰을 세션 쿠키로 바꾸고 `next` 로 보낸다."""
    t = (request.args.get("t") or "").strip()
    if not t:
        return jsonify({"error": "t 가 없다"}), 400
    try:
        head = _serializer("embed").loads_unsafe(t)[1] or {}
        payload = _serializer("embed").loads(t, max_age=int(head.get("ttl") or 300))
    except SignatureExpired:
        return jsonify({"error": "임베드 토큰이 만료됐다 — 다시 발급"}), 401
    except BadSignature:
        return jsonify({"error": "임베드 토큰이 이상하다"}), 401
    return set_session(redirect(_safe_next(payload.get("next"))), payload["user"])


@bp.route("/auth/logout", methods=["GET", "POST"])
def logout():
    resp = redirect(_env("YOS_LOGIN_URL") or "/") if request.method == "GET" else jsonify({"ok": True})
    return clear_session(resp)


@bp.route("/auth/me")
def me():
    u = current_user()
    return jsonify({"mode": mode(), "user": u, "authenticated": bool(u)})


# ── 요청 훅 ─────────────────────────────────────────────────────
def _wants_json():
    p = request.path
    if p.startswith("/api/") or p.startswith("/book-studio/") or p.startswith("/embed/"):
        return True
    acc = request.headers.get("Accept", "")
    return "application/json" in acc and "text/html" not in acc


def _deny(msg, code=401):
    if _wants_json() or not _env("YOS_LOGIN_URL"):
        return jsonify({"error": msg, "login": _env("YOS_LOGIN_URL") or None}), code
    back = request.url
    return redirect(_env("YOS_LOGIN_URL") + ("&" if "?" in _env("YOS_LOGIN_URL") else "?")
                    + "next=" + urllib.parse.quote(back, safe=""))


def _cors(resp):
    o = request.headers.get("Origin", "").rstrip("/")
    if o and o in origins():
        resp.headers["Access-Control-Allow-Origin"] = o
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "600"
        resp.headers.add("Vary", "Origin")
    return resp


def _before():
    g.user = None
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))
    if mode() == "off":
        g.user = {"sub": "local", "name": "local", "role": "admin", "via": "off"}
        return None
    p = request.path
    if p in _PUBLIC_EXACT or p.startswith(_PUBLIC_PREFIX):
        # /auth/me 는 신원을 알면 실어 주되, 몰라도 막지 않는다
        if p == "/auth/me":
            try:
                g.user = _identify()
            except AuthError:
                g.user = None
        return None
    try:
        g.user = _identify()
    except AuthError as e:
        return _deny(str(e))
    if not g.user:
        return _deny("로그인이 필요하다")
    if g.user.get("via") != "service" and _allowed_roles() and g.user.get("role") not in _allowed_roles():
        return _deny(f"이 역할은 스튜디오를 쓸 수 없다: {g.user.get('role')}", 403)
    return None


def _after(resp):
    _cors(resp)
    if mode() == "off":
        return resp                      # 로컬은 지금까지처럼 — 헤더로 화면을 바꾸지 않는다
    p = request.path
    embeddable = p.startswith(_EMBEDDABLE)
    ancestors = "'self' " + " ".join(origins()) if embeddable else "'none'"
    studio = p.startswith("/book-studio") or p.startswith("/embed/")
    csp = ("default-src 'self'; "
           + ("script-src 'self' 'unsafe-inline' 'unsafe-eval'; " if studio
              else "script-src 'self' 'unsafe-inline'; ")
           + "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
           + ("connect-src 'self' data:; " if studio else "connect-src 'self'; ")
           + "media-src 'self' blob:; object-src 'self'; "
           + f"frame-ancestors {ancestors}; form-action 'self'; base-uri 'self'")
    resp.headers.setdefault("Content-Security-Policy", csp)
    if not embeddable:
        resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if _cookie_secure():
        resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return resp


def install(app):
    """앱에 인증·CORS·보안 헤더를 건다. `studio_server.create_app()` 이 부른다."""
    app.secret_key = _secret(app)
    if mode() == "link":
        # 프록시(Fly·Caddy) 뒤에서 https 인지 알아야 Secure 쿠키를 낸다
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.register_blueprint(bp)
    app.before_request(_before)
    app.after_request(_after)
    return app


def describe():
    """기동 배너용 한 줄."""
    if mode() == "off":
        return "꺼짐 (로컬 — 로그인 없음)"
    return (f"켜짐 — Y.OS 링크 토큰(YOS_LINK_SECRET); 서비스 토큰 {len(_service_tokens())}개; "
            f"출처 {', '.join(origins()) or '없음'}")
