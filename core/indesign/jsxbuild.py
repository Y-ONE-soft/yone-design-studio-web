"""JSX 빌드 — 공용 코어(lib.jsxinc) + 본문을 concat해 실행용 JSX 생성.

ExtendScript는 안정적인 런타임 include가 없으므로(#include는 경로 제약)
빌드 시점 concat 방식을 쓴다 (마스터플랜 Phase 3).

사용:
    from core.indesign.jsxbuild import build_jsx
    jsx_path = build_jsx(body_template_path,
                         {"__INDD_PATH__": "...", "__OUT_PATH__": "..."},
                         log_path="/tmp/x.log")
"""
import os
import tempfile

_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_PATH = os.path.join(os.path.dirname(_DIR), "jsx", "lib.jsxinc")


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def build_jsx(body_path, replacements, log_path, out_path=None):
    """lib.jsxinc + 본문 템플릿 → 실행용 JSX 파일 경로 반환.

    - replacements의 플레이스홀더를 본문에서 치환 (값은 문자열 이스케이프됨)
    - __LIB_LOG_PATH__ 전역과 runner 호환 settingsPath 라인을 선두에 주입
    """
    with open(_LIB_PATH, encoding="utf-8") as f:
        lib = f.read()
    with open(body_path, encoding="utf-8") as f:
        body = f.read()
    for key, val in (replacements or {}).items():
        body = body.replace(key, _esc(val))

    header = (
        "// 자동 생성 (core.indesign.jsxbuild) — 수정 금지. 원본: "
        f"{os.path.basename(body_path)} + lib.jsxinc\n"
        f'var settingsPath = "{_esc(log_path)}";  // runner 호환 (미사용)\n'
        f'var __LIB_LOG_PATH__ = "{_esc(log_path)}";\n'
    )
    src = header + lib + "\n" + body

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".jsx", prefix="yone_built_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(src)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(src)
    return out_path
