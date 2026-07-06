"""Flask 앱 조립 — 전역 패치 + 앱 설정 + 블루프린트 등록 (C2-9 분리 후).

라우트 본체는 routes/ (auth/pages/typeset/folders/tools/admin),
파이프라인은 core/pipeline.py, JSON 캐시·데이터 로드는 core/webdata.py.
이 파일의 shutil 패치는 어떤 엔진/코어 모듈 import보다 먼저 실행되어야 한다.
"""
import errno
import os
import shutil
import time

from flask import Flask
from datetime import timedelta

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


# ── 앱 생성 + 설정 ────────────────────────────────────────────────
# (shutil 패치 이후에 import — core/engines 모듈이 패치된 copy를 쓰도록)
import config
from core.webdata import RetryingFileSystemLoader

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
# 표지 .ai / 세로변환 .indd는 수백 MB급이라 1GB 유지 (256MB 하향 시도는 회귀 — 2026-07-05).
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024   # 1 GB 요청 전체 크기
app.config["MAX_FORM_MEMORY_SIZE"] = 64 * 1024 * 1024   # 64 MB 텍스트 필드 합
app.config["MAX_FORM_PARTS"] = 10000                     # 멀티파트 part 수
app.jinja_loader = RetryingFileSystemLoader(
    os.path.join(os.path.dirname(__file__), "templates")
)
os.makedirs(config.JOBS_DIR, exist_ok=True)


# ── 블루프린트 등록 ───────────────────────────────────────────────
# auth의 before_app_request(인증) / after_app_request(보안 헤더)는 등록과
# 동시에 앱 전역 훅으로 적용된다 (기존 app.before_request/after_request와 동일).
from routes import ALL_BLUEPRINTS

for _bp in ALL_BLUEPRINTS:
    app.register_blueprint(_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=True,
            use_reloader=True)
