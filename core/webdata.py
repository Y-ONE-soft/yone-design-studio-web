"""웹앱 데이터 파일 로드/캐시 — app.py에서 분리 (C2-9). 의미론 무변경.

JSON 캐시 — invalidation 기반.
과거 mtime 비교 방식은 매 요청마다 stat syscall이 필요해서, werkzeug 리로더와
다수 요청 스레드가 동시에 같은 파일을 stat/open하면서 macOS APFS가
EDEADLK(Errno 11)를 반환하는 일이 잦았다. 이제는 한 번 로드한 값을 메모리에
영구 보관하고, save_* 시 캐시를 직접 갱신한다(파일 외부 변경은 반영 안 됨).
"""
import errno
import json
import os
import threading
import time

from jinja2 import FileSystemLoader

_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(_BASE_DIR, "data")
SCHOOLS_FILE  = os.path.join(DATA_DIR, "schools.json")
SUBJECTS_FILE = os.path.join(DATA_DIR, "subjects.json")
USERS_FILE    = os.path.join(DATA_DIR, "users.json")

_json_cache = {}            # path -> data
_json_cache_lock = threading.Lock()


def read_json_cached(path, default):
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
        print("[read_json_cached] all retries failed for %s: %s" % (path, last_err))
        return default


def invalidate_json_cache(path):
    with _json_cache_lock:
        _json_cache.pop(path, None)


def load_schools():
    return read_json_cached(SCHOOLS_FILE, [])


def save_schools(data):
    """원자적 쓰기 + 캐시 즉시 갱신.
    임시 파일에 쓰고 os.replace로 atomic rename하면 read 스레드가 partial
    JSON을 만날 일이 없고, 동일 lock 안에서 캐시도 갱신해 디스크 재read를
    유발하지 않는다.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SCHOOLS_FILE + ".tmp"
    with _json_cache_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SCHOOLS_FILE)
        _json_cache[SCHOOLS_FILE] = data


def load_subjects():
    return read_json_cached(SUBJECTS_FILE, [])


# ── 사용자 계정 로드 (C2-8) ──────────────────────────────────────────
# data/users.json 스키마: [{"username", "role", "password_env"}] — 비밀번호는
# 파일에 두지 않고 password_env가 가리키는 환경변수에서 매 호출 시 resolve.
# users.json 부재/파손 시 기존 하드코딩과 동일한 내장 기본값으로 폴백(fail-open).
DEFAULT_USERS_SPEC = [
    {"username": "admin",     "role": "admin",     "password_env": "YONE_ADMIN_PASSWORD"},
    {"username": "assistant", "role": "assistant", "password_env": "YONE_ASSISTANT_PASSWORD"},
]


def resolve_users_spec(spec):
    """spec 리스트 → {username: {"password", "role"}}. 잘못된 항목은 건너뜀."""
    users = {}
    if not isinstance(spec, list):
        return users
    for u in spec:
        if not isinstance(u, dict):
            continue
        name = (u.get("username") or "").strip()
        if not name:
            continue
        users[name] = {
            "password": os.environ.get(u.get("password_env") or "", ""),
            "role": u.get("role") or "assistant",
        }
    return users


def load_users():
    """username → {"password", "role"} dict. users.json은 read_json_cached로
    1회만 디스크 read (EDEADLK 회피), 유효 항목이 하나도 없으면 내장 기본값."""
    users = resolve_users_spec(read_json_cached(USERS_FILE, DEFAULT_USERS_SPEC))
    if not users:
        users = resolve_users_spec(DEFAULT_USERS_SPEC)
    return users


# ── 디스크 file open 재시도 ──────────────────────────────────────────
# macOS APFS가 동시 open 시 간헐적으로 반환하는 EDEADLK/EAGAIN/EINTR을 흡수.
# 정적 파일 서빙, 임의 read 등 jinja 외 경로에서도 사용.
RETRY_ERRNOS = (errno.EDEADLK, errno.EAGAIN, errno.EINTR)


def retry_on_edeadlk(fn, *args, **kwargs):
    last_err = None
    for attempt in range(5):
        try:
            return fn(*args, **kwargs)
        except OSError as e:
            if e.errno not in RETRY_ERRNOS:
                raise
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    raise last_err


class RetryingFileSystemLoader(FileSystemLoader):
    """Jinja FileSystemLoader.get_source를 EDEADLK retry로 감싼다.
    TEMPLATES_AUTO_RELOAD=True 환경에서 다수 동시 요청이 같은 .html을
    stat/open하다가 macOS APFS가 Errno 11로 거부할 때 페이지가 500으로 깨지는
    문제 방지. 정상 캐싱/auto_reload 동작은 그대로 유지된다.
    """
    def get_source(self, environment, template):
        return retry_on_edeadlk(super().get_source, environment, template)
