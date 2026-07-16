#!/usr/bin/env python3
"""품질 루프 14라운드 E2E — 수능특강 워크북 v2 레이아웃 정책 확산 검증.

2단계(분석본/문제본) 각각 delete 모드 + 문제본 divider_solo('N강' 셸
간지) + question_keep 활성 후:
  1) 27강(65cf0265) / Test 2(4fa1510e) 강별 재조판 — 스테이지별 게이트
     (W15 잔여 '문제본 39p D-마스터 셸 + 2강 간지' 해소 실측)
  2) merge_lessons(27강 + Test 2) — 페이지 삭제와 다강 통합의 상호작용
     검증 (머지 게이트: 강별 단어셋 보존 + 스프레드 수 정합)

사용: python3 scripts/e2e_round14_stg.py [render|merge|all(기본)]

안전(출력 리다이렉트): _load_v1_config 패치 — 출력은
data_corpus/round14/stg/, 내지는 data_corpus/template_test/
수능특강_{분석,문제}_내지.indd 로컬 사본. 실 운영 경로/사용자 문서 무접촉.
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

CASES = [("65cf0265", "27강", "27강"),
         ("4fa1510e", "Test 2", "Test2")]
OUT = os.path.abspath(os.path.join(REPO, "data_corpus", "round14", "stg"))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
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
    all_ok = True

    if mode in ("render", "all"):
        for case, label, short in CASES:
            print(f"== [{label}] 렌더 (코퍼스 {case})", flush=True)
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
            pp = json.load(open(os.path.join(job,
                                             "render_plan_problem.json"),
                                encoding="utf-8"))
            assert pp["page_cleanup"] == {"empty": "delete",
                                          "divider_solo": "강"}
            engine.run_indesign(job, log)
            result = engine.verify(job, log)
            print(json.dumps({k: v for k, v in result.items()
                              if k != "stories"},
                             ensure_ascii=False, indent=1))
            for st_label in ("analysis", "problem"):
                dp = os.path.join(job, f"typeset_dump_{st_label}.json")
                d = json.load(open(dp, encoding="utf-8"))
                shell = [s for s in d.get("stories", [])
                         if any((p.get("t") or "").strip() == "2강"
                                for p in s.get("paragraphs", []))]
                print(f"  [{st_label}] 페이지 {d.get('page_count')} / "
                      f"'2강' 셸 간지 스토리 {len(shell)}개 / 빈 페이지 "
                      f"{sum(1 for e in (d.get('pages') or []) if e.get('empty'))}")
            all_ok = all_ok and result["ok"]

    if mode in ("merge", "all"):
        labels = [label for _, label, _ in CASES]
        print(f"== merge_lessons {labels}", flush=True)
        result = SuneungteukgangWorkbookV2Engine.merge_lessons(labels, log)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        m_ok = (not result["errors"]
                and result["analysis"] and result["problem"]
                and all(v.get("ok") for v in result["verify"].values())
                and len(result["verify"]) == 2)
        print("merge:", "OK" if m_ok else "FAIL")
        all_ok = all_ok and m_ok

    print("\n결과:", "OK" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
