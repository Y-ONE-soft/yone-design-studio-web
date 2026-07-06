#!/usr/bin/env python3
"""부교재 워크북 v2 '엔진' E2E — 엔진 클래스 전체 파이프라인 검증.

supp v2는 WorkbookV2Engine 100% 상속(내지 lookup + 출력명만 오버라이드)이라,
워크북 코퍼스(0a5da924)로 parse→prepare→InDesign→verify를 돌려 훅 경로까지
실기 검증한다.

사용: python3 scripts/e2e_engine_workbook_supp_v2.py [0a5da924]

안전(출력 리다이렉트): _load_v1_config(workbook_v2 모듈 전역 — 상속 경로)를
패치해 출력은 data_corpus/wb_supp_e2e/, 내지는 data_corpus/template_test/
워크북C_모의고사.indd("_default" 키)로 고정. 실 운영 경로 무접촉.
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
    # supp 전용 코퍼스(tests/corpus/workbook_supp/) 우선, 없으면 워크북 코퍼스
    case_dir = os.path.join(REPO, "tests", "corpus", "workbook_supp", case)
    if not os.path.isdir(case_dir):
        case_dir = os.path.join(REPO, "tests", "corpus", "workbook", case)
    out = os.path.abspath(os.path.join(REPO, "data_corpus",
                                       "wb_supp_e2e", case))
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

    print(f"== 1/4 parse ({case})")
    _replay.build_job(case_dir, job)
    # supp 필수 메타: 사용자 지정 파일명 (E2E 식별용 stem)
    with open(os.path.join(job, "filename_stem.txt"), "w",
              encoding="utf-8") as f:
        f.write("E2E테스트")
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)
    settings = json.load(open(os.path.join(job, ".settings.json"),
                              encoding="utf-8"))
    assert settings["indd_path"].endswith("워크북E2E테스트_내지_v2.indd"), \
        settings["indd_path"]

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
