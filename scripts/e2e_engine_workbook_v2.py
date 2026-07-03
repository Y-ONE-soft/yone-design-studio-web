#!/usr/bin/env python3
"""워크북 v2 '엔진' E2E — 엔진 클래스 전체 파이프라인 검증.

parse → prepare_jsx → run_indesign → verify 를 코퍼스 케이스로 실행한다.
(플랜 단독 E2E는 scripts/e2e_v2_workbook.py — 이쪽은 엔진 래퍼까지 검증)

사용: python3 scripts/e2e_engine_workbook_v2.py [0a5da924]

안전(출력 리다이렉트): 엔진의 _load_v1_config를 패치해
  - indd_output_dir → data_corpus/wb_engine_e2e/<case>/
  - indd_original["모의고사"] → data_corpus/template_test/워크북C_모의고사.indd
실 운영 경로(조판/교재/워크북)와 GDrive는 건드리지 않는다.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "0a5da924"
    case_dir = os.path.join(REPO, "tests", "corpus", "workbook", case)
    out = os.path.abspath(os.path.join(REPO, "data_corpus",
                                       "wb_engine_e2e", case))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import _replay
    import engines.workbook_v2.engine as eng_mod
    from engines.workbook_v2.engine import WorkbookV2Engine

    # ── 출력 리다이렉트: v1 config 로더 패치 ────────────────────────────────
    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["모의고사"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        return cfg

    eng_mod._load_v1_config = _patched
    engine = WorkbookV2Engine()

    print(f"== 1/4 parse ({case})")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)

    print("== 3/4 run_indesign")
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
