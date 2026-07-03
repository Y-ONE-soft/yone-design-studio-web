"""jsxbuild 단위 테스트 — concat 구조/치환/러너 호환 헤더."""
import os

from core.indesign.jsxbuild import build_jsx

BODY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "core", "jsx", "extract_template_spec.body.jsx")


def test_build_concat_and_substitution(tmp_path):
    out = build_jsx(BODY,
                    {"__INDD_PATH__": '/tmp/한글 "경로".indd',
                     "__OUT_PATH__": "/tmp/out.json"},
                    log_path="/tmp/spec.log",
                    out_path=str(tmp_path / "built.jsx"))
    src = open(out, encoding="utf-8").read()
    # 러너 호환 헤더 (runner가 존재를 정규식 요구)
    assert 'var settingsPath = "/tmp/spec.log"' in src
    assert 'var __LIB_LOG_PATH__ = "/tmp/spec.log"' in src
    # lib 함수들이 본문보다 앞에 concat
    assert src.index("function jsonStringify") < src.index('var INDD =')
    assert "function styleFullPath" in src
    # 플레이스홀더 치환 + 이스케이프
    assert "__INDD_PATH__" not in src
    assert '\\"경로\\"' in src
    # ES3 금지 문법이 새어들지 않았는지 (기초 가드)
    for banned in ("=>", "let ", "const ", "`"):
        assert banned not in src, f"ES3 금지 문법 발견: {banned}"
