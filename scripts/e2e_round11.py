#!/usr/bin/env python3
"""품질 루프 11라운드 E2E (W21) — 실사용 1호 결함 원고 재조판.

케이스: r11c23ext1 (실서비스 job 0e3108fd — 2026 성덕고 외부지문 워크북1,
workbook_supp_v2 _default 내지). 사용자 지목 결함 8건 수리의 실기 검증.

사용: python3 scripts/e2e_round11.py

안전(출력 리다이렉트): _load_v1_config(workbook_v2 모듈 전역 — 상속 경로)를
패치해 출력은 data_corpus/round11/out/, 내지는 data_corpus/template_test/
워크북C_모의고사.indd("_default" 키) 로컬 사본으로 고정. 실 운영 경로/사용자
문서(워크북1_내지_v2_2.indd) 무접촉.
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
    case_dir = os.path.join(REPO, "tests", "corpus", "workbook_supp",
                            "r11c23ext1")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round11",
                                       "out"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import _replay
    import engines.workbook_v2.engine as base_mod
    from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine

    real_load = base_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["_default"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        return cfg

    base_mod._load_v1_config = _patched
    engine = WorkbookSuppV2Engine()

    print("== 1/4 parse (r11c23ext1)")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)
    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    assert plan["page_cleanup"] == {"empty": "delete"}, plan["page_cleanup"]
    assert plan.get("section_masters") is True
    units = {f["step"]: len(f["units"]) for f in plan["flows"]}
    for step in ("step1_c2", "step2_a1", "step2_b1", "step2_c1"):
        assert units[step] == 4, (step, units[step])

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
