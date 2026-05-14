"""
STUDIO_ROOT / ~ 기준 상대경로 -> 절대경로 resolve.

config.json에서 3가지 경로 형식을 지원:
  1) 절대경로 (/Users/...) -> 그대로
  2) ~/... -> os.path.expanduser
  3) 상대경로 (조판/교재/...) -> STUDIO_ROOT 기준
"""

import os

import config

_HOME = os.path.expanduser("~")
_ICLOUD_DOCS = os.path.join(
    _HOME,
    "Library", "Mobile Documents",
    "com~apple~CloudDocs", "Documents",
)


_INDD_ORIGINAL_MARKER = "조판/인디자인 원본/"


def _try_indd_redirect(path):
    """INDD_ORIGINAL_BASE 환경변수가 있으면, '조판/인디자인 원본/' 접두사를
    그 경로로 redirect한다. macOS iCloud Drive의 dataless(EDEADLK) 회피용 —
    인디자인 원본 폴더를 GDrive 등 안전한 위치로 옮긴 환경에서 사용.

    환경변수 미설정 또는 새 경로에 파일 없으면 None 반환 → 옛 경로 fallback.
    """
    indd_base = os.environ.get("INDD_ORIGINAL_BASE", "").strip()
    if not indd_base or _INDD_ORIGINAL_MARKER not in path:
        return None
    rest = path.split(_INDD_ORIGINAL_MARKER, 1)[1]
    if indd_base.startswith("~"):
        indd_base = os.path.expanduser(indd_base)
    candidate = os.path.join(indd_base, rest)
    return candidate if os.path.exists(candidate) else None


def resolve(path):
    """config.json 경로값을 실제 절대경로로 변환한다."""
    if not path:
        return path

    # INDD_ORIGINAL_BASE redirect (인디자인 원본 폴더가 GDrive 등으로 이동된 환경)
    redirected = _try_indd_redirect(path)
    if redirected:
        return redirected

    # ~/... 형식
    if path.startswith("~"):
        expanded = os.path.expanduser(path)
        # ~/Documents/... 가 실제로 없으면 iCloud Documents로 폴백
        if not os.path.exists(expanded):
            local_docs = os.path.join(_HOME, "Documents")
            if expanded.startswith(local_docs):
                icloud = expanded.replace(local_docs, _ICLOUD_DOCS, 1)
                if os.path.exists(icloud):
                    return icloud
        return expanded

    # 이미 절대경로
    if os.path.isabs(path):
        return path

    # 상대경로 -> STUDIO_ROOT 기준
    resolved = os.path.join(config.STUDIO_ROOT, path)
    if not os.path.exists(resolved):
        # 로컬 Documents에서 실행된 경우 iCloud 경로로 폴백
        icloud_studio = os.path.join(_ICLOUD_DOCS, "작업", "Y.ONE STUDIO")
        icloud_resolved = os.path.join(icloud_studio, path)
        if os.path.exists(icloud_resolved):
            return icloud_resolved
    return resolved


def resolve_config(cfg, keys):
    """cfg dict에서 지정된 keys의 값을 resolve한다.
    값이 str이면 단일 resolve, dict이면 value별로 resolve."""
    for key in keys:
        if key not in cfg:
            continue
        val = cfg[key]
        if isinstance(val, str):
            cfg[key] = resolve(val)
        elif isinstance(val, dict):
            cfg[key] = {k: resolve(v) if isinstance(v, str) else v
                        for k, v in val.items()}
    return cfg
