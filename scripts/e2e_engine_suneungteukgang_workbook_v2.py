#!/usr/bin/env python3
"""수능특강 워크북 v2 엔진 E2E — prepare_jsx → run_indesign(2단계) → verify.

parse는 GDrive 단원 폴더에 의존해 재실행 불가 → 코퍼스의 content.json
(= v1 파서 실물 출력)에서 시작한다.

사용: python3 scripts/e2e_engine_suneungteukgang_workbook_v2.py [65cf0265]

안전(출력 리다이렉트): 엔진 모듈의 _load_v1_config를 패치해
  - indd_output_dir → data_corpus/stg_engine_e2e/<case>/
  - indd_original → data_corpus/template_test/수능특강_{분석,문제}_내지.indd
실 운영 경로(조판/교재/워크북)와 GDrive는 건드리지 않는다.
"""
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "65cf0265"
    case_dir = os.path.join(REPO, "tests", "corpus",
                            "suneungteukgang_workbook", case)
    out = os.path.abspath(os.path.join(REPO, "data_corpus",
                                       "stg_engine_e2e", case))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import engines.suneungteukgang_workbook_v2.engine as eng_mod
    from engines.suneungteukgang_workbook_v2.engine import (
        SuneungteukgangWorkbookV2Engine)

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = {
            "analysis": os.path.join(REPO, "data_corpus", "template_test",
                                     "수능특강_분석_내지.indd"),
            "problem": os.path.join(REPO, "data_corpus", "template_test",
                                    "수능특강_문제_내지.indd"),
        }
        return cfg

    eng_mod._load_v1_config = _patched
    engine = SuneungteukgangWorkbookV2Engine()

    print(f"== 1/3 prepare_jsx ({case} — 코퍼스 content.json 재사용)")
    for fn in os.listdir(os.path.join(case_dir, "meta")):
        if fn.endswith(".txt"):
            shutil.copy2(os.path.join(case_dir, "meta", fn),
                         os.path.join(job, fn))
    json_path = os.path.join(job, "content.json")
    shutil.copy2(os.path.join(case_dir, "golden", "content.json"), json_path)
    engine.prepare_jsx(json_path, job, log)

    print("== 2/3 run_indesign (분석본 → 문제본)")
    engine.run_indesign(job, log)

    print("== 3/3 verify (검수 게이트 — 두 indd)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
