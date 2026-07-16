#!/usr/bin/env python3
"""품질 루프 14라운드 E2E — 교과서 워크북 v2 레이아웃 정책 확산 검증.

케이스: r3c13ybm (공통영어1 YBM(김) Project 1 — W13 실조판 코퍼스).
검증: page_cleanup delete 모드 + section_masters + question_keep의 교과서
계열 활성 (supp W21~W23 검증 3종 op 확산 — 내지가 supp와 같은
[원본]워크북_C). 특이점: 교과서 간지 텍스트 op(divider)와 delete의
상호작용 — 실행기 순서(page_cleanup → … → divider)에서 잔존 간지 문구가
교과서 라벨로 갱신되는지, 고아 간지(원고에 없는 스텝)는 스프레드째
삭제되는지 실측.

사용: python3 scripts/e2e_round14_textbook.py

안전(출력 리다이렉트): 엔진 모듈 _load_v1_config 패치 —
indd_output_dir → data_corpus/round14/c13_tb/, 내지는
data_corpus/template_test/워크북C_모의고사.indd 로컬 사본.
실 운영 경로/사용자 문서 무접촉.
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
    case_dir = os.path.join(REPO, "tests", "corpus", "textbook_workbook",
                            "r3c13ybm")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round14",
                                       "c13_tb"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import engines.textbook_workbook_v2.engine as eng_mod
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = {"_default": os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")}
        return cfg

    eng_mod._load_v1_config = _patched
    engine = TextbookWorkbookV2Engine()

    print("== 1/3 prepare_jsx (r3c13ybm — 코퍼스 content.json 재사용)")
    for fn in os.listdir(os.path.join(case_dir, "meta")):
        if fn.endswith(".txt"):
            shutil.copy2(os.path.join(case_dir, "meta", fn),
                         os.path.join(job, fn))
    json_path = os.path.join(job, "content.json")
    shutil.copy2(os.path.join(case_dir, "golden", "content.json"), json_path)
    engine.prepare_jsx(json_path, job, log)

    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    assert plan["page_cleanup"] == {"empty": "delete"}, plan["page_cleanup"]
    assert plan.get("section_masters") is True
    qk = plan.get("question_keep") or {}
    n_starts = sum(len(v.get("starts") or [])
                   for v in (qk.get("flows") or {}).values())
    pairs = sum(1 for fl in plan["flows"]
                if (fl.get("target") or {}).get("master_pair"))
    print(f"  [플랜] 문제단위킵 시작점 {n_starts}개 / master_pair 계약 "
          f"{pairs}개 플로우 / divider {plan.get('divider')}")

    print("== 2/3 run_indesign")
    engine.run_indesign(job, log)

    print("== 3/3 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    # ── r14 실측 요약 ────────────────────────────────────────────────────
    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    print(f"\n페이지 수: {dump.get('page_count')}")
    # 간지 라벨 실측 (divider 갱신 + 고아 간지 삭제 확인)
    l1 = (plan.get("divider") or {}).get("line1", "")
    labels = []
    stale_mock = 0
    for st in dump.get("stories", []):
        ps = st.get("paragraphs", [])
        if len(st.get("pg") or []) == 1 and len(ps) >= 2:
            t0 = (ps[0].get("t") or "").strip()
            if t0.startswith(l1) and l1:
                labels.append(str(st["pg"][0]))
            if "모의고사" in t0:
                stale_mock += 1
    inv = {str(e.get("p")): e for e in pages}
    print("간지(교과서 라벨) 페이지:",
          [(p, inv.get(p, {}).get("side")) for p in labels])
    print("모의고사 간지 잔재:", stale_mock)
    empty_left = [e.get("p") for e in pages if e.get("empty")]
    print("빈 페이지 잔존:", empty_left or 0)
    print("\n결과:", "OK verify ok=True" if result["ok"]
          else "FAIL verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
