#!/usr/bin/env python3
"""수능특강 워크북 v2 다중 강 통합(merge) E2E.

강별 렌더(코퍼스 content.json 2건: 27강 + Test 2) → merge_lessons →
검수 게이트(강별 단어셋 보존 + 스프레드 수 정합)까지 완주.

사용: python3 scripts/e2e_engine_suneungteukgang_workbook_v2_merge.py
      (강별 indd가 이미 공유 출력 폴더에 있으면 렌더는 자동 생략 —
       data_corpus/stg_engine_e2e/65cf0265 의 기존 27강 산출물은 자동 복사)

안전(출력 리다이렉트): 엔진 모듈의 _load_v1_config를 패치해
  - indd_output_dir → data_corpus/stg_engine_e2e/merge_st/
  - indd_original → data_corpus/template_test/수능특강_{분석,문제}_내지.indd
실 운영 경로(조판/교재/워크북)와 GDrive는 건드리지 않는다.
선행: bash scripts/indesign_watchdog.sh ensure
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

# (케이스 id, 강 라벨, 파일명 토큰)
CASES = [("65cf0265", "27강", "27강"),
         ("4fa1510e", "Test 2", "Test2")]
OUT = os.path.abspath(os.path.join(REPO, "data_corpus", "stg_engine_e2e",
                                   "merge_st"))


def _lesson_outputs_exist(short):
    return all(os.path.exists(os.path.join(
        OUT, f"EBS_수능특강_{short}_{tok}_v2.indd"))
        for tok in ("분석", "문제"))


def main():
    os.makedirs(OUT, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import engines.suneungteukgang_workbook_v2.engine as eng_mod
    from engines.suneungteukgang_workbook_v2.engine import (
        SuneungteukgangWorkbookV2Engine)

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = OUT
        cfg["indd_original"] = {
            "analysis": os.path.join(REPO, "data_corpus", "template_test",
                                     "수능특강_분석_내지.indd"),
            "problem": os.path.join(REPO, "data_corpus", "template_test",
                                    "수능특강_문제_내지.indd"),
        }
        return cfg

    eng_mod._load_v1_config = _patched
    engine = SuneungteukgangWorkbookV2Engine()

    # ── 1단계: 강별 v2 indd 확보 (재사용 → 복사 → 렌더 순) ──────────────
    for case, label, short in CASES:
        if _lesson_outputs_exist(short):
            print(f"== [{label}] 기존 산출물 재사용 (merge_st/)")
            continue
        prior = os.path.join(REPO, "data_corpus", "stg_engine_e2e", case)
        prior_ok = all(os.path.exists(os.path.join(
            prior, f"EBS_수능특강_{short}_{tok}_v2.indd"))
            for tok in ("분석", "문제"))
        if prior_ok:
            print(f"== [{label}] 이전 E2E 산출물 복사 ({case}/ → merge_st/)")
            for tok in ("분석", "문제"):
                fn = f"EBS_수능특강_{short}_{tok}_v2.indd"
                shutil.copy2(os.path.join(prior, fn),
                             os.path.join(OUT, fn))
            continue

        print(f"== [{label}] 렌더 (코퍼스 {case} content.json 재사용)")
        case_dir = os.path.join(REPO, "tests", "corpus",
                                "suneungteukgang_workbook", case)
        job = os.path.join(OUT, f"job_{case}")
        os.makedirs(job, exist_ok=True)
        for fn in os.listdir(os.path.join(case_dir, "meta")):
            if fn.endswith(".txt"):
                shutil.copy2(os.path.join(case_dir, "meta", fn),
                             os.path.join(job, fn))
        json_path = os.path.join(job, "content.json")
        shutil.copy2(os.path.join(case_dir, "golden", "content.json"),
                     json_path)
        engine.prepare_jsx(json_path, job, log)
        engine.run_indesign(job, log)
        # 강별 verify는 W8-3에서 통과 확인됨 — 여기선 산출물 존재만 확인
        if not _lesson_outputs_exist(short):
            print(f"❌ [{label}] 강별 indd 미생성 — 중단")
            return 1

    # ── 2단계: merge + 검수 게이트 ───────────────────────────────────────
    labels = [label for _, label, _ in CASES]
    print(f"== merge_lessons {labels}")
    result = SuneungteukgangWorkbookV2Engine.merge_lessons(labels, log)

    print(json.dumps(result, ensure_ascii=False, indent=1))
    ok = (not result["errors"]
          and result["analysis"] and result["problem"]
          and all(v.get("ok") for v in result["verify"].values())
          and len(result["verify"]) == 2)
    print("\n결과:", "✅ merge 게이트 통과" if ok else "❌ merge 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
