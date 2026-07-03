"""'.indd → template_spec.json' 추출 (Phase 3).

내지 템플릿의 기계가독 스펙: 마스터, 페이지 맵(적용 마스터·프레임 배치·
마커 텍스트 머리), 단락/문자 스타일 전체 경로 인벤토리, 라벨 아이템.

신규 내지 등록 절차 = 이 함수 1회 실행 + 의미 라벨링(사람, ~30분) —
기존의 "InDesign 열어 역추적 + config 수기 기입"을 대체한다.

사용:
    from core.template_spec import extract_template_spec
    spec = extract_template_spec("/path/템플릿.indd", "/path/spec.json", print)
"""
import json
import os

from core.indesign.jsxbuild import build_jsx

_BODY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "jsx", "extract_template_spec.body.jsx")


def extract_template_spec(indd_path, out_json, log, timeout=600):
    from core.indesign.runner import run_jsx
    spec_log = out_json + ".log"
    for p in (out_json, spec_log):
        try:
            os.remove(p)
        except OSError:
            pass
    jsx_path = build_jsx(_BODY,
                         {"__INDD_PATH__": indd_path, "__OUT_PATH__": out_json},
                         log_path=spec_log)
    try:
        run_jsx(jsx_path, log, poll_log_path=spec_log, timeout=timeout,
                completion_marker="스펙 추출 완료")
    finally:
        try:
            os.remove(jsx_path)
        except OSError:
            pass
    if not os.path.isfile(out_json):
        raise RuntimeError(f"스펙 파일이 생성되지 않음: {out_json}")
    return json.load(open(out_json, encoding="utf-8"))
