#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""분석본 결합 v2 엔진 E2E — parse → prepare_jsx → run_jsx → verify 전체.

사용:
  python3 scripts/e2e_engine_analysis_merge_v2.py            # 코퍼스 모드 (기본)
  python3 scripts/e2e_engine_analysis_merge_v2.py --real     # 실 GDrive 저장 모드

코퍼스 모드 (안전 — 기본):
  - GDrive 저장 base를 data_corpus/analysis_merge_v2/e2e/gdrive_out/ 으로
    리다이렉트. 실서비스/GDrive 경로 무접촉.
실 모드 (--real):
  - 실제 GDrive 분석본/고1,고2(공통)/ 아래 저장하되, 시험기간을
    "검증-테스트"(신규 폴더)로 강제 — 기존 폴더/파일 무접촉
    (신규 폴더/파일 생성만 한다는 스펙 검증용).

소스 강 폴더 탐색은 실제 GDrive '모의고사 작업'을 읽는다 (읽기 전용).
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.isfile(ENV):
    for _line in open(ENV):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def main():
    real = "--real" in sys.argv
    out_root = os.path.join(REPO, "data_corpus", "analysis_merge_v2", "e2e")
    job = os.path.join(out_root, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import engines.analysis_merge_v2.engine as eng_mod
    from engines.analysis_merge_v2.engine import AnalysisMergeV2Engine

    if not real:
        gdrive_out = os.path.join(out_root, "gdrive_out")
        os.makedirs(gdrive_out, exist_ok=True)
        real_load = eng_mod._load_config

        def _patched():
            cfg = real_load()
            cfg["save_base"] = gdrive_out
            return cfg

        eng_mod._load_config = _patched

    engine = AnalysisMergeV2Engine()

    # ── 입력 (기존 결합 실물과 동일 계열: 고2 25년 6월 + 22년 3월) ──────────
    meta = {
        "grade": "고2",
        "school": "검증1",
        "exam_period": "검증-테스트",
        "issue_num": "1",
        "ganji_school": "2026 검증고2",
        "ranges": json.dumps(
            [{"title": "고2 25년 6월 모의고사", "detail": "33번"},
             {"title": "고2 22년 3월 모의고사", "detail": "33-34번"}],
            ensure_ascii=False),
        "result_name": "",
    }
    for k, v in meta.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)
    uploaded = {"codes": "25년 6월 33번, 22년 3월 33-34번"}

    print("== 1/4 parse")
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    jsx_path = engine.prepare_jsx(json_path, job, log)

    print("== 3/4 run_indesign (파이프라인과 동일 경로)")
    assert jsx_path == os.path.join(job, "run.jsx")
    engine.run_indesign(job, log)

    print("== 4/4 verify")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=2))
    assert "pdf_path" not in result, "스펙1 위반: pdf_path 반환됨"
    if not result["ok"]:
        print("E2E FAIL — 게이트 미통과", file=sys.stderr)
        sys.exit(1)
    print(f"E2E OK — 저장: {result['gdrive_path']}")


if __name__ == "__main__":
    main()
