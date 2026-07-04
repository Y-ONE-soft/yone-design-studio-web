import errno
import io
import json
import os
import shutil
import threading
import time
import uuid
from datetime import timedelta

from flask import (Flask, Response, jsonify, render_template,
                   request, send_file, stream_with_context,
                   session, redirect, url_for)
from functools import wraps
from jinja2 import FileSystemLoader

import config

# ── shutil.copy2 fast-path 패치 ───────────────────────────────────
# Google Drive 가상 마운트나 dataless 파일을 shutil.copy2로 복사할 때,
# macOS zero-copy 시스템콜(fcopyfile)이 EDEADLK를 그대로 raise해서
# 엔진 작업이 중단되는 문제 방지. EDEADLK/EAGAIN/EINTR이 fast-path에서
# 발생하면 _GiveupOnFastCopy로 변환해 shutil이 자동으로 일반 read/write
# copy로 fallback하게 한다. 이 패치는 글로벌이라 모든 엔진의 copy2 호출에
# 동일 효과.
if hasattr(shutil, "_fastcopy_fcopyfile") and hasattr(shutil, "_GiveupOnFastCopy"):
    _orig_fastcopy_fcopyfile = shutil._fastcopy_fcopyfile
    def _patched_fastcopy_fcopyfile(fsrc, fdst, flags):
        try:
            return _orig_fastcopy_fcopyfile(fsrc, fdst, flags)
        except OSError as e:
            if e.errno in (errno.EDEADLK, errno.EAGAIN, errno.EINTR):
                raise shutil._GiveupOnFastCopy(e)
            raise
    shutil._fastcopy_fcopyfile = _patched_fastcopy_fcopyfile

# GDrive Stream FS의 일시적 EDEADLK는 시간으로만 풀린다. 단일 orig 호출 +
# 지수 백오프(1+3+8+15+30초, 누적 57초) 재시도. 과거 cp/ditto subprocess 폴백은
# EDEADLK 클래스에 무력하고 자기 경합만 유발했기에 제거.
def _retry_then_subprocess(orig, *args, **kwargs):
    backoffs = [1, 3, 8, 15, 30]
    last_err = None
    for attempt in range(5):
        try:
            return orig(*args, **kwargs)
        except OSError as e:
            if e.errno not in (errno.EDEADLK, errno.EAGAIN, errno.EINTR):
                raise
            last_err = e
        if attempt < 4:
            time.sleep(backoffs[attempt])
    raise last_err


_orig_copy2     = shutil.copy2
_orig_copy      = shutil.copy
_orig_copyfile  = shutil.copyfile

def _patched_copy2(*a, **k):    return _retry_then_subprocess(_orig_copy2, *a, **k)
def _patched_copy(*a, **k):     return _retry_then_subprocess(_orig_copy, *a, **k)
def _patched_copyfile(*a, **k): return _retry_then_subprocess(_orig_copyfile, *a, **k)

shutil.copy2    = _patched_copy2
shutil.copy     = _patched_copy
shutil.copyfile = _patched_copyfile


# ── 인증 설정 ──────────────────────────────────────────────────────
# 사용자 계정. 비밀번호는 반드시 환경변수(.env 또는 launchd)에서만 주입.
#   YONE_ADMIN_PASSWORD     → admin 비밀번호
#   YONE_ASSISTANT_PASSWORD → assistant 비밀번호
# 환경변수 미설정 시 fallback은 빈 문자열 → 어떤 비밀번호로도 로그인 불가 (보안 정책).
USERS = {
    "admin":     {"password": os.environ.get("YONE_ADMIN_PASSWORD",     ""), "role": "admin"},
    "assistant": {"password": os.environ.get("YONE_ASSISTANT_PASSWORD", ""), "role": "assistant"},
}

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

import core.job_manager as jm
from core.indesign import runner as indesign
from core import workbook_edit as wb_edit
from core.uploads import sanitize_filename, allowed_by_accept
from engines import registry

_DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
_SCHOOLS_FILE  = os.path.join(_DATA_DIR, "schools.json")
_SUBJECTS_FILE = os.path.join(_DATA_DIR, "subjects.json")


# JSON 캐시 — invalidation 기반.
# 과거 mtime 비교 방식은 매 요청마다 stat syscall이 필요해서, werkzeug 리로더와
# 다수 요청 스레드가 동시에 같은 파일을 stat/open하면서 macOS APFS가
# EDEADLK(Errno 11)를 반환하는 일이 잦았다. 이제는 한 번 로드한 값을 메모리에
# 영구 보관하고, _save_* 시 캐시를 직접 갱신한다(파일 외부 변경은 반영 안 됨).
_json_cache = {}            # path -> data
_json_cache_lock = threading.Lock()


def _read_json_cached(path, default):
    """디스크 read는 첫 호출과 invalidation 직후에만 발생.
    EDEADLK/EAGAIN/EINTR은 짧은 backoff로 5회 재시도하고, 그래도 실패하면
    캐시에 저장하지 않고 default를 반환해 페이지가 깨지지 않도록 한다.
    """
    with _json_cache_lock:
        if path in _json_cache:
            return _json_cache[path]
        if not os.path.exists(path):
            _json_cache[path] = default
            return default
        last_err = None
        for attempt in range(5):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                _json_cache[path] = data
                return data
            except OSError as e:
                if e.errno not in (errno.EDEADLK, errno.EAGAIN, errno.EINTR):
                    raise
                last_err = e
                time.sleep(0.05 * (attempt + 1))
        print("[_read_json_cached] all retries failed for %s: %s" % (path, last_err))
        return default


def _invalidate_json_cache(path):
    with _json_cache_lock:
        _json_cache.pop(path, None)


def _load_schools():
    return _read_json_cached(_SCHOOLS_FILE, [])

def _save_schools(data):
    """원자적 쓰기 + 캐시 즉시 갱신.
    임시 파일에 쓰고 os.replace로 atomic rename하면 read 스레드가 partial
    JSON을 만날 일이 없고, 동일 lock 안에서 캐시도 갱신해 디스크 재read를
    유발하지 않는다.
    """
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _SCHOOLS_FILE + ".tmp"
    with _json_cache_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SCHOOLS_FILE)
        _json_cache[_SCHOOLS_FILE] = data

def _load_subjects():
    return _read_json_cached(_SUBJECTS_FILE, [])


# 디스크 file open 재시도 — macOS APFS가 동시 open 시 간헐적으로 반환하는
# EDEADLK/EAGAIN/EINTR을 흡수한다. 정적 파일 서빙, 임의 read 등 jinja 외 경로에서도 사용.
_RETRY_ERRNOS = (errno.EDEADLK, errno.EAGAIN, errno.EINTR)


def _retry_on_edeadlk(fn, *args, **kwargs):
    last_err = None
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except OSError as e:
            if e.errno not in _RETRY_ERRNOS:
                raise
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    raise last_err


class _RetryingFileSystemLoader(FileSystemLoader):
    """Jinja FileSystemLoader.get_source를 EDEADLK retry로 감싼다.
    TEMPLATES_AUTO_RELOAD=True 환경에서 다수 동시 요청이 같은 .html을
    stat/open하다가 macOS APFS가 Errno 11로 거부할 때 페이지가 500으로 깨지는
    문제 방지. 정상 캐싱/auto_reload 동작은 그대로 유지된다.
    """
    def get_source(self, environment, template):
        return _retry_on_edeadlk(super().get_source, environment, template)


app = Flask(__name__)
# secret_key: 환경변수에서만 주입. 미설정 시 시작 실패 (보안 정책).
_secret = os.environ.get("YONE_SECRET_KEY", "")
if not _secret:
    raise RuntimeError(
        "YONE_SECRET_KEY 환경변수가 설정되지 않았습니다. "
        ".env 파일 또는 launchd 환경변수로 등록하세요."
    )
app.secret_key = _secret
# 세션 정책: 브라우저 종료 시 만료 (브라우저 세션 쿠키). 추가 안전망으로 12시간 절대 만료.
app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True
# Werkzeug 3.0+ form parsing 보안 한도 — 멀티 파일 업로드용으로 크게.
# (C1-3) 1GB → 256MB 하향: 원고(docx/hwpx) 다중 업로드는 수십 MB 수준이라 충분.
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024    # 256 MB 요청 전체 크기
app.config["MAX_FORM_MEMORY_SIZE"] = 64 * 1024 * 1024   # 64 MB 텍스트 필드 합
app.config["MAX_FORM_PARTS"] = 10000                     # 멀티파트 part 수
app.jinja_loader = _RetryingFileSystemLoader(
    os.path.join(os.path.dirname(__file__), "templates")
)
os.makedirs(config.JOBS_DIR, exist_ok=True)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.is_json or request.path.startswith("/api/") or request.path.startswith("/chat/send") or request.path.startswith("/chat/watch"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        user = USERS.get(username)
        if user and user["password"] == pw:
            session["authenticated"] = True
            session["username"] = username
            session["role"] = user["role"]
            return redirect("/")
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


@app.route("/logout")
def logout_page():
    session.clear()
    return redirect("/login")


@app.before_request
def check_auth():
    # 로그인 페이지와 static 파일은 인증 불필요
    if request.path in ("/login", "/logout", "/api/health") or request.path.startswith("/static/"):
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

@app.after_request
def add_no_cache(response):
    if "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    response.headers["X-Served-By"] = "flask-live"
    # ── 보안 헤더 ──
    response.headers["X-Frame-Options"] = "DENY"
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
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
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

# 목업 세션 (token → {front_img, back_img})
_mockup_sessions = {}


# ── 페이지 라우트 ─────────────────────────────────────────────────────────

_SECTION_CONFIG = {
    "조판": {
        "title": "조판",
        "hero_title": "Y.ONE 조판",
        "hero_desc": "교재를 선택하고 원고를 업로드하면 InDesign 조판 → PDF까지 자동으로 처리됩니다.",
        "hero_tip": "원하는 <strong>교재 카드</strong>를 클릭하면 원고 업로드 화면으로 이동합니다.",
        "cta_text": "시작",
    },
    "표지": {
        "title": "표지",
        "hero_title": "Y.ONE 표지",
        "hero_desc": "세네카 조정, 아웃라인 변환, PDF 출력까지 표지 작업을 자동화합니다.",
        "hero_tip": "원하는 <strong>표지 종류</strong>를 선택하면 작업 화면으로 이동합니다.",
        "cta_text": "시작",
    },
    "가공": {
        "title": "가공",
        "hero_title": "Y.ONE 가공",
        "hero_desc": "조판이 완료된 교재에서 시험범위 외 회차/유형별 문항을 일괄 정리합니다.",
        "hero_tip": "가공할 <strong>교재 종류</strong>를 선택하세요.",
        "cta_text": "시작",
    },
}


def _subjects_by_section(section):
    return [c for c in _load_subjects() if c.get("section") == section]


@app.route("/")
def index():
    cfg = _SECTION_CONFIG["조판"]
    return render_template("index.html",
                           subjects=_subjects_by_section("조판"),
                           active_nav="조판",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"])


@app.route("/cover")
def cover_index():
    cfg = _SECTION_CONFIG["표지"]
    return render_template("index.html",
                           subjects=_subjects_by_section("표지"),
                           active_nav="표지",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"])


@app.route("/processing")
def processing_index():
    cfg = _SECTION_CONFIG["가공"]
    subjects = _subjects_by_section("가공")
    # "가공" 섹션은 engine_id 카드를 직접 라우트로 사용 (typeset이 아닌 processing)
    return render_template("index.html",
                           subjects=subjects,
                           active_nav="가공",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"],
                           card_url_prefix="/processing/")


def _section_for_engine(material_id):
    for cat in _load_subjects():
        for item in cat.get("items", []):
            if item.get("engine_id") == material_id:
                return cat.get("section", "조판")
    return "조판"


# ── 가공: 워크북 가공 페이지 + API ──────────────────────────────────────

@app.route("/processing/workbook_edit")
def processing_workbook_edit():
    return render_template("processing_workbook_edit.html",
                           active_nav="가공",
                           section_title="워크북 가공")


@app.route("/api/processing/workbook/upload", methods=["POST"])
def api_wb_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"status": "err", "msg": "file 필드가 없습니다"})
    r = wb_edit.save_upload(f)
    return jsonify(r)


@app.route("/api/processing/workbook/job-files")
def api_wb_job_files():
    job_dir = request.args.get("jobDir", "")
    if not job_dir or not os.path.isdir(job_dir):
        return jsonify({"status": "err", "msg": "잡 폴더 없음"})
    return jsonify({"status": "ok", "files": wb_edit.list_job_files(job_dir)})


@app.route("/api/processing/workbook/active-info", methods=["POST"])
def api_wb_active_info():
    return jsonify(wb_edit.active_info())


@app.route("/api/processing/workbook/list-candidates", methods=["POST"])
def api_wb_list_candidates():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.list_candidates(doc_path=data.get("docPath")))


@app.route("/api/processing/workbook/identify-rounds", methods=["POST"])
def api_wb_identify_rounds():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.identify_rounds(
        doc_path=data.get("docPath"),
        story_indices=data.get("storyIndices"),
    ))


@app.route("/api/processing/workbook/remove-seo", methods=["POST"])
def api_wb_remove_seo():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.remove_seo(
        doc_path=data.get("docPath"),
        backup=bool(data.get("backup", True)),
        extract=bool(data.get("extract", True)),
        story_indices=data.get("storyIndices"),
    ))


@app.route("/api/processing/workbook/remove-rounds", methods=["POST"])
def api_wb_remove_rounds():
    data = request.get_json(silent=True) or {}
    spec = data.get("roundSpec") or {}
    if not isinstance(spec, dict) or not spec:
        return jsonify({"status": "err", "msg": "roundSpec 필요"})
    return jsonify(wb_edit.remove_rounds(
        round_spec=spec,
        doc_path=data.get("docPath"),
        backup=bool(data.get("backup", True)),
        extract=bool(data.get("extract", True)),
    ))


@app.route("/api/processing/workbook/compare", methods=["POST"])
def api_wb_compare():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.compare(
        doc_path=data.get("docPath"),
        orig_path=data.get("origPath", ""),
    ))


@app.route("/api/processing/workbook/save", methods=["POST"])
def api_wb_save():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.save_doc(doc_path=data.get("docPath")))


@app.route("/api/processing/workbook/passage-detect", methods=["POST"])
def api_wb_passage_detect():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.passage_detect(
        doc_path=data.get("docPath"),
        readers=data.get("readers", ""),
    ))


@app.route("/api/processing/workbook/passage-select", methods=["POST"])
def api_wb_passage_select():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.passage_select(
        doc_path=data.get("docPath"),
        nums=data.get("nums", ""),
        select_mode=data.get("selectMode", "keep"),
        backup=bool(data.get("backup", True)),
        relayout=bool(data.get("relayout", True)),
        leftover=data.get("leftover", "tight"),
        save=bool(data.get("save", True)),
        readers=data.get("readers", ""),
    ))


@app.route("/api/processing/workbook/convert-docx", methods=["POST"])
def api_wb_convert_docx():
    data = request.get_json(silent=True) or {}
    txt_path = data.get("txtPath", "")
    return jsonify(wb_edit.convert_txt_to_docx(txt_path))


@app.route("/api/processing/workbook/download")
def api_wb_download():
    """가공 결과 파일 다운로드. path는 절대경로 (작업 폴더 한정)."""
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        return "파일 없음", 404
    # 경로 보호: 워크북가공 작업 폴더 또는 _local 폴더만 허용
    real = os.path.realpath(path)
    allowed_prefixes = [
        os.path.expanduser("~/Documents/작업/Y.ONE STUDIO/"),
        "/tmp/",
    ]
    if not any(real.startswith(p) for p in allowed_prefixes):
        return "허용되지 않은 경로", 403
    return send_file(real, as_attachment=True, download_name=os.path.basename(real))


@app.route("/typeset/<material_id>")
def typeset_page(material_id):
    try:
        engine = registry.get(material_id)
    except KeyError:
        return "교재를 찾을 수 없습니다.", 404
    tmpl = getattr(engine, "template_name", "typeset.html")
    nav = _section_for_engine(material_id)

    # 파이널 엔진: 워크북 폴더에서 학교 목록 자동 스캔
    exam_periods = []
    current_period = ""
    if material_id == "final":
        from engines.final.engine import (
            _load_config as _load_final_config,
            scan_exam_periods, estimate_exam_period, resolve_exam_period,
        )
        fcfg = _load_final_config()
        exam_periods = scan_exam_periods(fcfg["gdrive_base"])
        # 드롭다운으로 명시 선택 시 URL 파라미터 우선, 없으면 날짜 기반 자동 추정
        sel = request.args.get("exam_period", "").strip()
        if sel and sel in exam_periods:
            current_period = sel
        else:
            current_period = (estimate_exam_period(exam_periods)
                              or resolve_exam_period(fcfg))
        schools = engine.scan_schools(fcfg["gdrive_base"], current_period)
        if not schools:
            schools = _load_schools()
    else:
        schools = _load_schools()

    return render_template(tmpl, engine=engine, schools=schools,
                           active_nav=nav, exam_periods=exam_periods,
                           current_period=current_period)


# ── 폴더 브라우저 API (웹 기반 — 원격 접속에서도 동작) ────────────────────────

@app.route("/api/browse-folder", methods=["POST"])
def api_browse_folder():
    """서버 파일시스템의 폴더 목록을 반환. 어떤 기기에서 접속해도 동작."""
    import unicodedata as _ud
    data = request.get_json() or {}
    path = data.get("path", "")

    # 기본 경로: 구글드라이브 분석본/고1,고2(공통) 폴더
    if not path:
        path = os.path.expanduser(
            "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com"
            "/내 드라이브/콘텐츠 관리/내신대비"
            "/인디자인 파일/분석본/고1,고2(공통)"
        )
        if not os.path.isdir(path):
            path = os.path.expanduser(
                "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com"
                "/내 드라이브/콘텐츠 관리/내신대비"
            )
        if not os.path.isdir(path):
            path = os.path.expanduser("~")

    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return jsonify({"error": "폴더를 찾을 수 없습니다", "path": path})

    dirs = []
    has_indd = False
    try:
        for raw in sorted(os.listdir(path)):
            nfc = _ud.normalize("NFC", raw)
            full = os.path.join(path, raw)
            if raw.startswith("."):
                continue
            if os.path.isdir(full):
                dirs.append(nfc)
            elif nfc.endswith(".indd") and "분석본" in nfc:
                has_indd = True
    except PermissionError:
        return jsonify({"error": "접근 권한 없음", "path": path})

    parent = os.path.dirname(path) if path != "/" else None
    return jsonify({
        "path": path,
        "parent": parent,
        "dirs": dirs,
        "has_indd": has_indd,
    })


# ── 교과서 워크북 폴더 탐색 API ──────────────────────────────────────────────

@app.route("/api/textbook-workbook/subjects")
def api_tw_subjects():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    return jsonify(TextbookWorkbookEngine.list_subjects())


@app.route("/api/textbook-workbook/publishers")
def api_tw_publishers():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    return jsonify(TextbookWorkbookEngine.list_publishers(subject))


@app.route("/api/textbook-workbook/lessons")
def api_tw_lessons():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    publisher = request.args.get("publisher", "")
    return jsonify(TextbookWorkbookEngine.list_lessons(subject, publisher))


@app.route("/api/textbook-workbook/files")
def api_tw_files():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    publisher = request.args.get("publisher", "")
    lesson_folder = request.args.get("lesson_folder", "")
    return jsonify(TextbookWorkbookEngine.list_files(subject, publisher, lesson_folder))


# ── EBS 리딩파워 워크북 폴더 탐색 API ─────────────────────────────────────────

@app.route("/api/ebs-workbook/units")
def api_ebs_units():
    from engines.ebs_workbook.engine import EbsWorkbookEngine
    return jsonify(EbsWorkbookEngine.list_units())


@app.route("/api/ebs-workbook/files")
def api_ebs_files():
    from engines.ebs_workbook.engine import EbsWorkbookEngine
    unit_folder = request.args.get("unit_folder", "")
    return jsonify(EbsWorkbookEngine.list_files(unit_folder))


# ── 수능특강 워크북 폴더 탐색 API ─────────────────────────────────────────────

@app.route("/api/suneungteukgang-workbook/units")
def api_st_units():
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    return jsonify(SuneungteukgangWorkbookEngine.list_units())


@app.route("/api/suneungteukgang-workbook/files")
def api_st_files():
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    unit_folder = request.args.get("unit_folder", "")
    return jsonify(SuneungteukgangWorkbookEngine.list_files(unit_folder))


@app.route("/api/suneungteukgang-workbook/merge", methods=["POST"])
def api_st_merge():
    """다중 강 통합 — 강별 indd를 첫 indd 끝에 duplicate해서 한 파일로 합침."""
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    body = request.get_json() or {}
    lessons = body.get("lessons", [])
    if not isinstance(lessons, list) or len(lessons) < 2:
        return jsonify({"error": "lessons 배열(2개 이상) 필요"}), 400

    logs = []
    def _log(msg):
        logs.append(msg)
    result = SuneungteukgangWorkbookEngine.merge_lessons(lessons, _log)
    return jsonify({"result": result, "logs": logs})


# ── 서버 진단 API ────────────────────────────────────────────────────────────

@app.route("/diagnose")
def diagnose_page():
    return '''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>서버 진단</title>
    <style>body{background:#111;color:#eee;font-family:sans-serif;max-width:600px;margin:40px auto;padding:0 20px}
    pre{background:#1a1a1a;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.6}
    button{background:#6366f1;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:14px;cursor:pointer;margin:8px 4px 8px 0}
    button:disabled{opacity:.5} .ok{color:#22c55e} .bad{color:#f87171}
    h1{font-size:20px} .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px}
    .tag.on{background:#22c55e22;color:#22c55e} .tag.off{background:#f8717122;color:#f87171}</style></head>
    <body><h1>서버 진단</h1>
    <div id="status">불러오는 중...</div>
    <div style="margin-top:16px">
      <button onclick="startID()">InDesign 실행</button>
      <button onclick="load()">새로고침</button>
    </div>
    <script>
    async function load(){
      var el=document.getElementById('status');
      el.textContent='불러오는 중...';
      try{
        var r=await fetch('/api/diagnose');
        if(!r.ok){el.innerHTML='<span class="bad">API 오류: '+r.status+'</span>';return;}
        var d=await r.json();
        var h='<p>InDesign: '+(d.indesign.indexOf('실행 중')>=0
          ?'<span class="tag on">'+d.indesign+'</span>'
          :'<span class="tag off">'+d.indesign+'</span>')+'</p>';
        h+='<p>tmp settings: '+((typeof d.tmp_settings==='string')?d.tmp_settings:d.tmp_settings.length+'개')+'</p>';
        h+='<h3>최근 작업</h3><pre>';
        (d.recent_jobs||[]).forEach(function(j){
          var ok=j.log.indexOf('완료')>=0;
          h+='<span class="'+(ok?'ok':'bad')+'">'+j.age+'</span> '+j.school+' ('+j.job+')\n  '+j.log+'\n\n';
        });
        h+='</pre>';
        el.innerHTML=h;
      }catch(e){el.innerHTML='<span class="bad">연결 실패: '+e.message+'</span>';}
    }
    async function startID(){
      try{
        var r=await fetch('/api/indesign/start',{method:'POST'});
        var d=await r.json();
        document.getElementById('status').innerHTML=d.ok
          ?'<span class="ok">'+d.app+' 실행 요청 완료 (10초 후 새로고침)</span>'
          :'<span class="bad">실패: '+d.error+'</span>';
        setTimeout(load,10000);
      }catch(e){document.getElementById('status').innerHTML='<span class="bad">연결 실패: '+e.message+'</span>';}
    }
    load();
    </script></body></html>'''


@app.route("/api/health")
def api_health():
    """간단한 헬스체크 — 인증 없이 접근 가능. 외부 모니터링/Tailscale 등에서 사용."""
    import subprocess as _hsp, time as _htime
    info = {"ok": True}

    # InDesign 가동 여부 (3초 timeout)
    info["indesign_running"] = False
    for ver in ("2026", "2025", "2024"):
        try:
            r = _hsp.run(
                ["osascript", "-e", f'tell application "Adobe InDesign {ver}" to return running'],
                capture_output=True, text=True, timeout=3
            )
            if "true" in r.stdout.lower():
                info["indesign_running"] = True
                info["indesign_version"] = ver
                break
        except Exception:
            continue

    # 활성 작업 (jobs/ 5분 내 수정된 폴더 수)
    jobs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
    active = 0
    if os.path.isdir(jobs_dir):
        cutoff = _htime.time() - 300
        try:
            for d in os.listdir(jobs_dir):
                full = os.path.join(jobs_dir, d)
                if os.path.isdir(full) and os.path.getmtime(full) > cutoff:
                    active += 1
        except Exception:
            pass
    info["active_jobs"] = active

    # 마지막 자동 git pull
    pull_log = os.path.expanduser("~/Library/Logs/yone-auto-pull.log")
    if os.path.exists(pull_log):
        info["last_auto_pull"] = _htime.strftime(
            "%Y-%m-%d %H:%M:%S", _htime.localtime(os.path.getmtime(pull_log))
        )

    # 주요 환경변수 (값은 노출 X, 설정 여부만)
    info["env"] = {
        "YONE_STUDIO_ROOT": bool(os.environ.get("YONE_STUDIO_ROOT")),
        "YONE_ADMIN_PASSWORD": bool(os.environ.get("YONE_ADMIN_PASSWORD")),
        "YONE_ASSISTANT_PASSWORD": bool(os.environ.get("YONE_ASSISTANT_PASSWORD")),
        "YONE_SECRET_KEY": bool(os.environ.get("YONE_SECRET_KEY")),
        "ASSISTANT_SHARE_DIR": bool(os.environ.get("ASSISTANT_SHARE_DIR")),
    }

    return jsonify(info)


@app.route("/api/diagnose")
def api_diagnose():
    """아이맥 서버 상태 진단 — InDesign, /tmp, 최근 작업 확인."""
    import subprocess, glob as _glob, time as _time
    info = {}

    # 1) InDesign 실행 여부
    for ver in ["2026", "2025", "2024", "2023"]:
        app_name = f"Adobe InDesign {ver}"
        try:
            r = subprocess.run(
                ["osascript", "-e", f'tell application "{app_name}" to return running'],
                capture_output=True, text=True, timeout=3
            )
            if "true" in r.stdout or "running" in r.stdout:
                info["indesign"] = f"{app_name} (실행 중)"
                break
        except Exception:
            continue
    else:
        info["indesign"] = "InDesign 미실행"

    # 2) /tmp/pocketbook_* 파일
    tmp_files = _glob.glob("/tmp/pocketbook_*/settings.json")
    info["tmp_settings"] = tmp_files if tmp_files else "없음"

    # 3) 최근 3개 작업 상태
    jobs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
    recent = []
    if os.path.isdir(jobs_dir):
        job_ids = sorted(os.listdir(jobs_dir),
                         key=lambda x: os.path.getmtime(os.path.join(jobs_dir, x))
                         if os.path.isdir(os.path.join(jobs_dir, x)) else 0,
                         reverse=True)[:3]
        for jid in job_ids:
            jdir = os.path.join(jobs_dir, jid)
            if not os.path.isdir(jdir):
                continue
            log_path = os.path.join(jdir, "typeset_log.txt")
            school_path = os.path.join(jdir, "school.txt")
            school = open(school_path).read().strip() if os.path.exists(school_path) else "?"
            has_log = os.path.exists(log_path)
            log_tail = ""
            if has_log:
                lines = open(log_path, encoding="utf-8", errors="ignore").readlines()
                log_tail = (lines[-1].strip() if lines else "")
            age = int(_time.time() - os.path.getmtime(jdir))
            recent.append({
                "job": jid, "school": school,
                "log": log_tail if has_log else "로그 없음 (JSX 미실행)",
                "age": f"{age // 60}분 전",
            })
    info["recent_jobs"] = recent

    return jsonify(info)


@app.route("/api/indesign/start", methods=["GET", "POST"])
def api_indesign_start():
    """InDesign 원격 실행."""
    import subprocess
    for ver in ["2026", "2025", "2024", "2023"]:
        app_name = f"Adobe InDesign {ver}"
        if os.path.isdir(f"/Applications/{app_name}"):
            try:
                subprocess.Popen(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return jsonify({"ok": True, "app": app_name})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": False, "error": "InDesign 설치를 찾을 수 없습니다"})


# ── 포켓북 분석본 스캔 API ────────────────────────────────────────────────────

@app.route("/api/pocketbook/scan-dir", methods=["POST"])
def api_pocketbook_scan():
    import re as _re
    import unicodedata as _ud
    data = request.get_json()
    folder = data.get("path", "")

    if not folder or not os.path.isdir(folder):
        return jsonify({"files": [], "error": "폴더를 찾을 수 없습니다"})

    # macOS NFD 파일명 대응: NFC 정규화 후 매칭
    raw_files = os.listdir(folder)
    analysis = []
    pocketbook = None
    for raw in raw_files:
        nfc = _ud.normalize("NFC", raw)
        if not nfc.endswith(".indd"):
            continue
        if "분석본" in nfc:
            if _re.search(r"\d{2}년\d{1,2}월", nfc) or "모의" in nfc or "마더텅" in nfc:
                stype = "모의고사"
            elif "올포" in nfc or "올림" in nfc:
                stype = "EBS"
            else:
                stype = "교과서"
            analysis.append({"name": nfc, "type": stype, "raw": raw})
        elif "포켓북" in nfc and "분석본" not in nfc and not pocketbook:
            pocketbook = os.path.join(folder, raw)

    analysis.sort(key=lambda x: (_re.search(r"(\d+)", x["name"]).group(1)
                                  if _re.search(r"(\d+)", x["name"]) else "99"))
    result = [{"name": a["name"], "type": a["type"]} for a in analysis]

    return jsonify({"files": result, "pocketbook": pocketbook, "folder": folder})


# ── 파이널 워크북 감지 API ────────────────────────────────────────────────────

@app.route("/api/final/detect-workbooks", methods=["POST"])
def api_final_detect():
    data = request.get_json()
    school = data.get("school", "")
    grade = data.get("grade", "고1")
    exam_period = data.get("exam_period", "").strip()
    from engines.final.engine import (
        FinalEngine, _load_config as _load_final_config,
        scan_exam_periods, estimate_exam_period,
    )
    from engines.final.scope_parser import parse_all_scopes
    fcfg = _load_final_config()
    if not exam_period:
        exam_period = estimate_exam_period(scan_exam_periods(fcfg["gdrive_base"]))
    files, wb_dir, _ = FinalEngine.find_workbook_files(
        fcfg["gdrive_base"], exam_period, grade, school
    )
    scopes = parse_all_scopes(files) if files else []

    # 교재 매핑 정보
    textbook_info = fcfg.get("school_textbook_map", {}).get(
        exam_period, {}
    ).get(school)

    # 고3: 분석편에서 사용 가능한 강 목록 반환
    available_lectures = []
    if grade == "고3":
        available_lectures = FinalEngine.scan_lectures()

    return jsonify({
        "count": len(files),
        "files": [os.path.basename(f) for f in files],
        "path": wb_dir,
        "scopes": scopes,
        "textbook": textbook_info,
        "available_lectures": available_lectures,
    })


# ── 동형모의고사 API ──────────────────────────────────────────────────────────

@app.route("/api/mockexam/schools")
def api_mockexam_schools():
    from engines.mockexam.engine import MockexamEngine
    schools = MockexamEngine.scan_schools()
    return jsonify(schools)


# ── 마더텅 결합 API ──────────────────────────────────────────────────────────

@app.route("/api/mothertongue/lessons")
def api_mothertongue_lessons():
    from engines.mothertongue_merge.engine import MothertongueMergeEngine
    grade = request.args.get("grade", "고1")
    school = request.args.get("school", "한영고1")
    return jsonify(MothertongueMergeEngine.list_lessons(grade, school))


# ── 학교 관리 API ────────────────────────────────────────────────────────────

@app.route("/api/schools")
def api_schools_get():
    return jsonify(_load_schools())


@app.route("/api/schools", methods=["POST"])
def api_schools_add():
    data = request.get_json()
    grade, name = data.get("grade", "").strip(), data.get("name", "").strip()
    if not grade or not name:
        return jsonify({"error": "grade/name 필요"}), 400
    schools = _load_schools()
    if grade not in schools:
        schools[grade] = []
    if name not in schools[grade]:
        schools[grade].append(name)
        _save_schools(schools)
    return jsonify({"ok": True})


@app.route("/api/schools/<grade>/<school_name>", methods=["DELETE"])
def api_schools_delete(grade, school_name):
    schools = _load_schools()
    if grade in schools and school_name in schools[grade]:
        schools[grade].remove(school_name)
        _save_schools(schools)
    return jsonify({"ok": True})


@app.route("/mockup")
def mockup_page():
    from core.mockup.renderer import DEFAULTS, SPECS
    return render_template("mockup.html", defaults=DEFAULTS, specs=SPECS,
                           active_nav="목업")


@app.route("/api/mockup/upload", methods=["POST"])
def api_mockup_upload():
    from core.mockup import renderer
    front = request.files.get("front")
    back  = request.files.get("back")
    if not front:
        return jsonify({"error": "앞표지 필요"}), 400
    try:
        front_bytes = front.read()
        front_img = renderer.load_cover_bytes(front_bytes, front.filename)
        front_crop = renderer.default_crop_params(front_img, "front")
        # 중철펼침용: 앞 파일이 2페이지 PDF면 2페이지를 자동 추출
        front_p2 = renderer.load_cover_bytes(front_bytes, front.filename, page=1)
        back_img = None
        back_crop = None
        if back and back.filename:
            back_img = renderer.load_cover_bytes(back.read(), back.filename)
            back_crop = renderer.default_crop_params(back_img, "back")
        token = uuid.uuid4().hex[:10]
        _mockup_sessions[token] = {"front": front_img, "back": back_img, "front_p2": front_p2}
        return jsonify({"token": token, "front_crop": front_crop, "back_crop": back_crop,
                        "has_p2": front_p2 is not None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mockup/render", methods=["POST"])
def api_mockup_render():
    from core.mockup import renderer
    token  = request.form.get("token")
    params = json.loads(request.form.get("params", "{}"))
    fmt    = request.form.get("fmt", "PNG")
    session = _mockup_sessions.get(token)
    if not session:
        return "세션 없음 — 표지를 다시 업로드해 주세요.", 400
    try:
        front = renderer.apply_crop(session["front"],
            params.pop("front_cx", 0), params.pop("front_cy", 0),
            params.pop("front_cw", renderer.COVER_W))
        back = None
        if session.get("back"):
            back = renderer.apply_crop(session["back"],
                params.pop("back_cx", 0), params.pop("back_cy", 0),
                params.pop("back_cw", renderer.COVER_W))
        data = renderer.render_to_bytes(front, back, params, fmt)
        mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
        return Response(data, mimetype=mime)
    except Exception as e:
        return str(e), 500


@app.route("/api/mockup/render_binding", methods=["POST"])
def api_mockup_render_binding():
    """무선/스프링/중철 바인딩 목업 — 헤드리스 A/B 라이트맵 엔진 (Photoshop 불필요)."""
    from core.mockup import mockup_engine
    from PIL import Image as _Img
    import io as _io
    token   = request.form.get("token")
    binding = request.form.get("binding", "")
    fmt     = request.form.get("fmt", "PNG").upper()
    session = _mockup_sessions.get(token)
    if not session:
        return "세션 없음 — 표지를 다시 업로드해 주세요.", 400
    if binding not in mockup_engine.ALL_BINDINGS:
        return f"알 수 없는 바인딩: {binding}", 400
    try:
        fit = float(request.form.get("fit", "1.0"))
    except ValueError:
        fit = 1.0
    fit = max(0.7, min(1.3, fit))
    back_img = session.get("back") or session.get("front_p2")  # 뒷표지 없으면 2페이지 자동
    try:
        img = mockup_engine.render(session["front"], binding,
                                   back_img=back_img, long_edge=1500, fit=fit)
        buf = _io.BytesIO()
        if fmt == "PNG":
            img.save(buf, "PNG", optimize=True); mime = "image/png"
        else:
            bg = _Img.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1]); bg.save(buf, "JPEG", quality=92)
            mime = "image/jpeg"
        return Response(buf.getvalue(), mimetype=mime)
    except Exception as e:
        return str(e), 500


# ── API ──────────────────────────────────────────────────────────────────

@app.route("/api/run/<material_id>", methods=["POST"])
def api_run(material_id):
    try:
        engine = registry.get(material_id)
    except KeyError:
        print(f"[ERROR] 교재 없음: material_id='{material_id}'")
        return jsonify({"error": f"교재 없음 (id: {material_id})"}), 404

    job_id = jm.create_job(material_id)
    job_dir = jm.get_job(job_id)["dir"]
    upload_dir = os.path.join(job_dir, "uploads")

    # 학교 저장 (공통 메타데이터)
    school = request.form.get("school", "").strip()
    if school:
        open(os.path.join(job_dir, "school.txt"), "w").write(school)

    # issue_num 저장 (공통 메타데이터)
    issue_num = request.form.get("issue_num", "").strip()
    if issue_num:
        open(os.path.join(job_dir, "issue_num.txt"), "w").write(issue_num)

    # grade 저장 (단어장 등 학년 선택이 필요한 교재)
    grade = request.form.get("grade", "").strip()
    if grade:
        open(os.path.join(job_dir, "grade.txt"), "w").write(grade)

    # year/month 저장 (워크북 등 시험 연도/월 선택이 필요한 교재)
    year = request.form.get("year", "").strip()
    if year:
        open(os.path.join(job_dir, "year.txt"), "w").write(year)
    month = request.form.get("month", "").strip()
    if month:
        open(os.path.join(job_dir, "month.txt"), "w").write(month)

    # 고3 선택된 강 목록 저장
    lectures = request.form.get("lectures", "").strip()
    if lectures:
        open(os.path.join(job_dir, "lectures.txt"), "w",
             encoding="utf-8").write(lectures)

    # 동형모의고사 메타데이터 저장
    for meta_key in ("exam_period", "exam_date", "exam_type", "round"):
        val = request.form.get(meta_key, "").strip()
        if val:
            open(os.path.join(job_dir, f"{meta_key}.txt"), "w",
                 encoding="utf-8").write(val)

    # 교과서 워크북 메타데이터 저장
    for meta_key in ("subject", "publisher", "lesson", "lesson_folder",
                     "manuscript_folder", "workbook_type"):
        val = request.form.get(meta_key, "").strip()
        if val:
            open(os.path.join(job_dir, f"{meta_key}.txt"), "w",
                 encoding="utf-8").write(val)

    # 부교재 워크북: 파일명 stem (학교명_{stem}_내지.indd 의 stem 부분)
    filename_stem = request.form.get("filename_stem", "").strip()
    if filename_stem:
        open(os.path.join(job_dir, "filename_stem.txt"), "w",
             encoding="utf-8").write(filename_stem)

    # 워크북 조판 제외 섹션 (체크박스 그룹 — multi-value)
    exclude_list = request.form.getlist("exclude")
    if exclude_list:
        open(os.path.join(job_dir, "exclude.txt"), "w",
             encoding="utf-8").write(",".join(exclude_list))

    # 업로드 파일 및 텍스트 필드 저장
    # — 진단 로그: multipart 파싱 결과 (Werkzeug 3.x form 한도 디버그용)
    try:
        _form_keys = list(request.form.keys())
        _file_keys = list(request.files.keys())
        _file_counts = {k: len(request.files.getlist(k)) for k in _file_keys}
        print(f"[upload-debug] job={job_id} form_keys={_form_keys} "
              f"file_keys={_file_keys} file_counts={_file_counts} "
              f"content_length={request.content_length}", flush=True)
    except Exception as _e:
        print(f"[upload-debug-error] {_e}", flush=True)

    uploaded = {}
    for slot in engine.upload_spec["slots"]:
        key = slot["key"]
        # 학년 필터: 슬롯에 grade가 지정되어 있고 선택 학년과 다르면 건너뛰기
        slot_grade = slot.get("grade")
        if slot_grade and grade and slot_grade != grade:
            continue
        if slot.get("type") in ("text", "textarea"):
            val = request.form.get(key, "").strip()
            if val:
                # 텍스트 값은 job_dir/{key}.txt 로 저장
                txt_path = os.path.join(job_dir, f"{key}.txt")
                open(txt_path, "w", encoding="utf-8").write(val)
                uploaded[key] = val
            elif slot.get("required"):
                jm.fail(job_id, f"필수 입력 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 입력 누락: {slot['label']}"}), 400
        elif slot.get("multiple"):
            files = request.files.getlist(key)
            paths = []
            for f in files:
                if f and f.filename:
                    # (C1-3) 확장자 화이트리스트 — 슬롯 accept가 진실
                    if not allowed_by_accept(f.filename, slot.get("accept", "")):
                        msg = (f"허용되지 않는 파일 형식: {f.filename} "
                               f"(허용: {slot.get('accept')})")
                        jm.fail(job_id, msg)
                        return jsonify({"job_id": job_id, "error": msg}), 400
                    safe_name = f"{key}_{sanitize_filename(f.filename)}"
                    path = os.path.join(upload_dir, safe_name)
                    f.save(path)
                    paths.append(path)
            if paths:
                uploaded[key] = paths
            elif slot.get("required"):
                jm.fail(job_id, f"필수 파일 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 파일 누락: {slot['label']}"}), 400
        else:
            f = request.files.get(key)
            if f and f.filename:
                # (C1-3) 확장자 화이트리스트 — 슬롯 accept가 진실
                if not allowed_by_accept(f.filename, slot.get("accept", "")):
                    msg = (f"허용되지 않는 파일 형식: {f.filename} "
                           f"(허용: {slot.get('accept')})")
                    jm.fail(job_id, msg)
                    return jsonify({"job_id": job_id, "error": msg}), 400
                safe_name = f"{key}_{sanitize_filename(f.filename)}"
                path = os.path.join(upload_dir, safe_name)
                f.save(path)
                uploaded[key] = path
            elif slot.get("required"):
                jm.fail(job_id, f"필수 파일 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 파일 누락: {slot['label']}"}), 400

    threading.Thread(
        target=_run_pipeline,
        args=(engine, job_id, job_dir, uploaded),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/api/stream/<job_id>")
def api_stream(job_id):
    if not jm.get_job(job_id):
        return "job not found", 404

    return Response(
        stream_with_context(jm.stream(job_id)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/api/cancel/<job_id>", methods=["POST"])
def api_cancel(job_id):
    if not jm.get_job(job_id):
        return jsonify({"error": "job not found"}), 404
    jm.cancel_job(job_id)
    return jsonify({"ok": True})


@app.route("/api/result/<job_id>")
def api_result(job_id):
    job = jm.get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify({
        "status": job["status"],
        "result": job["result"],
    })


@app.route("/debug/safecopy")
def debug_safecopy():
    """[임시 진단] _gdrive_safe_copy를 실제 파이프라인 흐름대로 호출."""
    import os, time, threading
    from engines.final.extractor import _gdrive_safe_copy
    # 실제 사용자 작업에서 실패한 파일로 변경
    F = ('/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/'
         '내 드라이브/콘텐츠 관리/내신대비/'
         '인디자인 파일/워크북/모의고사/고1/'
         '고1_25년_3월_전체(C).indd')
    out = []
    out.append(f"PID: {os.getpid()}, thread: {threading.current_thread().name}")
    out.append("")

    # 메인 스레드 (Flask request thread)에서 호출
    out.append("=== 메인 스레드 (Flask request thread) ===")
    dst = f"/tmp/debug_safecopy_main_{os.getpid()}.docx"
    if os.path.exists(dst): os.remove(dst)
    t0 = time.time()
    captured = []
    ok, err = _gdrive_safe_copy(F, dst, log=lambda m: captured.append(m))
    out.append(f"결과: ok={ok}, time={time.time()-t0:.2f}s")
    out.append(f"dst size: {os.path.getsize(dst) if os.path.exists(dst) else 0}")
    if captured:
        out.append("로그:")
        out.extend(["  " + l for l in captured])
    if not ok:
        out.append(f"마지막 err: {err[:500]}")
    if os.path.exists(dst): os.remove(dst)
    out.append("")

    # 백그라운드 스레드 (실제 파이프라인 패턴)에서 호출
    out.append("=== 백그라운드 스레드 (daemon=True, 실제 파이프라인 패턴) ===")
    result = {}
    captured2 = []
    def worker():
        dst2 = f"/tmp/debug_safecopy_thread_{os.getpid()}.docx"
        if os.path.exists(dst2): os.remove(dst2)
        t = time.time()
        ok2, err2 = _gdrive_safe_copy(F, dst2,
                                      log=lambda m: captured2.append(m))
        result["ok"] = ok2
        result["err"] = err2
        result["time"] = time.time() - t
        result["size"] = os.path.getsize(dst2) if os.path.exists(dst2) else 0
        result["thread"] = threading.current_thread().name
        if os.path.exists(dst2): os.remove(dst2)

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(timeout=180)
    out.append(f"thread name: {result.get('thread', 'TIMEOUT')}")
    out.append(f"결과: ok={result.get('ok')}, time={result.get('time', 0):.2f}s")
    out.append(f"dst size: {result.get('size', 0)}")
    if captured2:
        out.append("로그:")
        out.extend(["  " + l for l in captured2])
    if not result.get('ok'):
        out.append(f"마지막 err: {str(result.get('err', ''))[:500]}")
    return "<pre>" + "\n".join(out) + "</pre>"


@app.route("/download/<job_id>/pdf")
def download_pdf(job_id):
    job = jm.get_job(job_id)
    if not job or not job.get("result"):
        return "결과 없음", 404
    pdf_path = job["result"].get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF 없음", 404
    return send_file(pdf_path, as_attachment=True,
                     download_name=os.path.basename(pdf_path))


# ── 파이프라인 실행 (백그라운드 스레드) ──────────────────────────────────

def _classify_failure(msg):
    """실패 메시지를 유형으로 분류 — 향후 유형별 집계용."""
    if not msg:
        return "unknown"
    if ("스크립트 전달 실패" in msg) or ("스크립트 시작 안 됨" in msg):
        return "startup_delivery"          # 1단계 자동 재시도 대상
    if ("미갱신" in msg) or ("행(hang)" in msg) or ("응답 없음" in msg):
        return "hang_timeout"
    if ("Errno 11" in msg) or ("Resource deadlock" in msg) or ("EDEADLK" in msg):
        return "file_lock_edeadlk"
    if ("[오류]" in msg) or ("스토리" in msg) or ("찾을 수 없" in msg):
        return "jsx_data_error"
    low = msg.lower()
    if ("폰트" in msg) or ("링크" in msg) or ("font" in low) or ("link" in low):
        return "font_link_missing"
    return "other"


def _persist_failure(job_id, job_dir, engine, stage, err_msg, tb):
    """실패 이력을 디스크에 영속화 — 유형별 집계 + 1단계 커버리지 측정용.

    jm.fail 은 in-memory 스트림이라 재부팅 시 소실된다. 여기서
    job_dir/failure.json(개별, traceback 포함) + 중앙 JSONL(전체 집계)로 남긴다.
    이 함수는 절대 예외를 밖으로 던지지 않는다(실패 경로를 깨지 않기 위해).
    """
    import time as _t
    material_id = getattr(engine, "material_id", "") or ""
    rec = {
        "ts": _t.strftime("%Y-%m-%d %H:%M:%S"),
        "job_id": job_id,
        "material_id": material_id,
        "stage": stage,
        "error": (err_msg or "")[:500],
        "category": _classify_failure(err_msg or ""),
    }
    try:
        with open(os.path.join(job_dir, "failure.json"), "w", encoding="utf-8") as f:
            json.dump({**rec, "traceback": (tb or "")[-4000:]}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        cpath = os.path.expanduser("~/Library/Logs/yonestudio-failures.jsonl")
        with open(cpath, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run_pipeline(engine, job_id: str, job_dir: str, uploaded: dict):
    log = lambda m: jm.put_log(job_id, m)
    skip_id = getattr(engine, "skip_indesign", False)
    total = "2" if skip_id else "3"
    stage = "init"   # 실패 시 어느 단계에서 났는지 기록용
    try:
        # ── 1단계: 파싱 ──────────────────────────────────────────────
        stage = "parse"
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log(f"[1/{total}] 원고 파싱 중...")
        json_path = engine.parse(uploaded, job_dir, log)
        log(f"[1/{total}] 파싱 완료 ✓")

        if jm.is_cancelled(job_id):
            return

        # ── 2단계: InDesign 조판 (skip_indesign이면 건너뛰기) ────────
        if not skip_id:
            stage = "indesign"
            log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            log("[2/3] InDesign 조판 중...")
            jsx_path = engine.prepare_jsx(json_path, job_dir, log)
            # 엔진에 전용 InDesign 실행기가 있으면 사용
            if hasattr(engine, 'run_indesign'):
                engine.run_indesign(job_dir, log)
            else:
                log_filename = getattr(engine, "log_filename", "조판_로그.txt")
                # settings.json의 output_dir에서 로그 경로 결정 (/tmp일 수 있음)
                _settings_path = os.path.join(job_dir, ".settings.json")
                if os.path.exists(_settings_path):
                    with open(_settings_path) as _sf:
                        _sdata = json.load(_sf)
                    log_file = os.path.join(_sdata.get("output_dir", job_dir), log_filename)
                else:
                    log_file = os.path.join(job_dir, log_filename)
                jsx_timeout = getattr(engine, "jsx_timeout", 300)
                indesign.run_jsx(jsx_path, log, poll_log_path=log_file,
                                 timeout=jsx_timeout,
                                 cancel_check=lambda: jm.is_cancelled(job_id))
            log("[2/3] 조판 완료 ✓")

        if jm.is_cancelled(job_id):
            return

        # ── 마지막 단계: 검수 ────────────────────────────────────────
        stage = "verify"
        step = total
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log(f"[{step}/{total}] 검수 중...")
        result = engine.verify(job_dir, log)
        log(f"[{step}/{total}] 검수 완료 ✓")

        # ── 범용 검수 게이트 (opt-in: YONE_INSPECT=1) ────────────────────
        # 조판 산출 .indd를 다시 열어 content.json 단어셋과 대조 — 내용 누락
        # 자동 검출. 엔진 코드/JSX 무수정, 실패해도 조판 결과에 영향 없음.
        # (mockexam_v2는 verify에 자체 게이트 내장 — 중복 덤프 방지 위해 제외)
        if (os.environ.get("YONE_INSPECT") == "1"
                and engine.material_id != "mockexam_v2"):
            try:
                from core.inspect import inspect_generic
                log("[검수+] 내용 보존 대조 중...")
                g = inspect_generic(job_dir, log)
                if g is not None:
                    result["inspect"] = g
                    if g["ok"]:
                        log(f"[검수+] ✅ 내용 보존 확인 "
                            f"({g['content_words']}단어, indd {g['indd_count']}개)")
                    else:
                        result["ok"] = False
                        warn = (f"[검수+] ❌ 내용 누락 의심 {g['missing_words']}단어: "
                                + ", ".join(g["missing_sample"][:8]))
                        result.setdefault("warnings", []).append(warn)
                        log(warn)
                    if g["overflow_stories"]:
                        log(f"[검수+] ⚠️ 오버플로우 스토리 {g['overflow_stories']}개")
            except Exception as _ie:
                log(f"[검수+] 건너뜀 (검수 실패가 조판을 막지 않음): {_ie}")

        # PDF를 목업 IN 폴더에 자동 복사
        pdf_path = result.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            os.makedirs(config.MOCKUP_IN_DIR, exist_ok=True)
            dest = os.path.join(config.MOCKUP_IN_DIR, os.path.basename(pdf_path))
            shutil.copy2(pdf_path, dest)
            result["mockup_file"] = os.path.basename(pdf_path)
            log(f"목업 폴더 복사 완료: {os.path.basename(pdf_path)}")

        jm.done(job_id, result)

        # 조교 공유 폴더로 비동기 복사 (ASSISTANT_SHARE_DIR 환경변수 설정 시).
        # 별도 thread라 GDrive 지연/실패가 메인 pipeline에 영향 없음.
        try:
            from core.sharing import share_job_async
            school = ""
            school_path = os.path.join(job_dir, "school.txt")
            if os.path.exists(school_path):
                with open(school_path, encoding="utf-8") as _sf:
                    school = _sf.read().strip()
            # result에서 .indd 경로 힌트 추출 (settings.json fallback보다 정확함)
            _indd_hint = None
            if isinstance(result, dict):
                _indd_hint = result.get("indd_path") or result.get("indd_paths")
            share_job_async(job_id, job_dir, school, log, indd_path=_indd_hint, material_id=getattr(engine, "material_id", None))
        except Exception as _e:
            log(f"[공유] 시작 실패 (무시): {_e}")

    except Exception as e:
        log(f"[오류] {e}")
        import traceback
        tb = traceback.format_exc()
        log(tb)
        jm.fail(job_id, str(e))
        # 실패 이력 영속화(분석용). 실패 경로를 절대 깨지 않도록 예외 무시.
        try:
            _persist_failure(job_id, job_dir, engine, stage, str(e), tb)
        except Exception:
            pass


# ── Claude 채팅 (원격 접속용) ────────────────────────────────────────

import subprocess as _sp

_CONV_FILE = os.path.join(os.path.expanduser("~"), ".claude-desktop-data.json")

def _load_convs():
    try:
        with open(_CONV_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"conversations": []}

def _save_convs(data):
    with open(_CONV_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

@app.route("/chat")
def chat_page():
    return render_template("chat.html", active_nav="채팅")

@app.route("/chat/folders")
def chat_folders():
    """작업 폴더 목록 반환."""
    base = config.STUDIO_ROOT
    try:
        dirs = [{"name": d, "path": os.path.join(base, d)}
                for d in sorted(os.listdir(base))
                if os.path.isdir(os.path.join(base, d)) and not d.startswith('.')]
        return jsonify(dirs)
    except Exception:
        return jsonify([])

@app.route("/chat/conversations")
def chat_conversations():
    """데스크탑 앱 대화 목록 반환."""
    data = _load_convs()
    convs = data.get("conversations", [])
    return jsonify([{
        "id": c.get("id"),
        "title": c.get("title", "새 대화"),
        "sessionId": c.get("sessionId"),
        "workingDir": c.get("workingDir"),
        "messageCount": len(c.get("messages", [])),
        "createdAt": c.get("createdAt"),
    } for c in convs[:30]])

@app.route("/chat/conversations/<conv_id>/messages")
def chat_messages(conv_id):
    """특정 대화의 메시지 반환."""
    data = _load_convs()
    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
    if not conv:
        return jsonify({"error": "not found"}), 404
    msgs = conv.get("messages", [])
    return jsonify({
        "sessionId": conv.get("sessionId"),
        "workingDir": conv.get("workingDir"),
        "messages": [{"role": m.get("role"), "content": m.get("content", ""), "timestamp": m.get("timestamp")}
                     for m in msgs if m.get("role") in ("user", "assistant") and m.get("content")]
    })

@app.route("/chat/conversations/<conv_id>/append", methods=["POST"])
def chat_append(conv_id):
    """웹에서 보낸 메시지/응답을 데스크탑 대화에 추가."""
    body = request.json or {}
    data = _load_convs()
    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
    if not conv:
        return jsonify({"error": "not found"}), 404
    msg = {
        "id": str(uuid.uuid4())[:8],
        "role": body.get("role", "user"),
        "content": body.get("content", ""),
        "timestamp": int(body.get("timestamp", 0)) or int(__import__('time').time() * 1000),
    }
    conv.setdefault("messages", []).append(msg)
    if body.get("sessionId"):
        conv["sessionId"] = body["sessionId"]
    _save_convs(data)
    return jsonify({"ok": True})

@app.route("/chat/watch/<conv_id>")
def chat_watch(conv_id):
    """SSE: 대화 변경 실시간 감지. 메시지 수가 바뀌면 새 메시지 전송."""
    import time as _time
    def generate():
        last_count = 0
        last_mtime = 0
        while True:
            try:
                mtime = os.path.getmtime(_CONV_FILE)
                if mtime != last_mtime:
                    last_mtime = mtime
                    data = _load_convs()
                    conv = next((c for c in data.get("conversations", []) if c.get("id") == conv_id), None)
                    if conv:
                        msgs = [m for m in conv.get("messages", []) if m.get("role") in ("user", "assistant") and m.get("content")]
                        if len(msgs) != last_count:
                            new_msgs = msgs[last_count:] if last_count > 0 else msgs[-1:]
                            last_count = len(msgs)
                            for m in new_msgs:
                                yield f"data: {json.dumps({'role': m['role'], 'content': m['content']}, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            _time.sleep(2)
    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/chat/conversations/create", methods=["POST"])
def chat_create_conv():
    """웹에서 새 대화 생성 → 데스크탑 앱 데이터에 저장."""
    body = request.json or {}
    import time as _t
    conv_id = str(uuid.uuid4())[:8] + str(int(_t.time()))[-4:]
    data = _load_convs()
    conv = {
        "id": conv_id,
        "title": body.get("title", "새 대화")[:40],
        "messages": [],
        "sessionId": None,
        "workingDir": body.get("workingDir") or config.STUDIO_ROOT,
        "createdAt": int(_t.time() * 1000),
    }
    data.setdefault("conversations", []).insert(0, conv)
    _save_convs(data)
    return jsonify({"id": conv_id})

@app.route("/chat/send", methods=["POST"])
def chat_send():
    """Claude CLI 실행 후 SSE 스트리밍 응답."""
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("sessionId")
    working_dir = data.get("workingDir") or config.STUDIO_ROOT

    if not message:
        return Response("data: {\"type\":\"error\",\"content\":\"빈 메시지\"}\n\ndata: [DONE]\n\n",
                        mimetype="text/event-stream")

    claude_path = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude")
    args = [claude_path, "--dangerously-skip-permissions", "-p", message,
            "--output-format", "stream-json", "--verbose"]
    if session_id:
        args.extend(["--resume", session_id])

    def generate():
        try:
            proc = _sp.Popen(args, cwd=working_dir,
                             stdout=_sp.PIPE, stderr=_sp.PIPE,
                             text=True, env={**os.environ, "LANG": "ko_KR.UTF-8"})
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    # 세션 ID 전달
                    if ev.get("type") == "system" and ev.get("session_id"):
                        yield f"data: {json.dumps({'type':'session','sessionId':ev['session_id']})}\n\n"
                    # 텍스트 스트리밍
                    elif ev.get("type") == "assistant" and ev.get("message"):
                        content = ev["message"].get("content", [])
                        for block in content:
                            if block.get("type") == "text" and block.get("text"):
                                yield f"data: {json.dumps({'type':'text','content':block['text']})}\n\n"
                    elif ev.get("type") == "result" and ev.get("result"):
                        yield f"data: {json.dumps({'type':'text','content':ev['result']})}\n\n"
                except json.JSONDecodeError:
                    pass
            proc.wait()
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=True,
            use_reloader=True)
