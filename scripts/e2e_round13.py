#!/usr/bin/env python3
"""품질 루프 13라운드 E2E (W23) — 실사용 3차 피드백 4건 수리의 실기 검증.

케이스: r13c24addu (실서비스 job 6c1430c3 — 공통영어1 능률(민) Unit.3
추가지문 워크북, workbook_supp_v2 _default 내지, filename_stem '1').

수리 검증 항목 (사용자 피드백 4건):
  F1 간지 '추가지문' ('[N과 추가지문]' 헤더 실측 유형 — '모의고사' 자동
     라벨 금지)
  F2 짤지문 고아 간지 스프레드 0 (removeOrphanDividers — 불량 출력 p34~35)
  F3 CO₂ 아래첨자 — ₂(U+2082) 잔존 0, '2'+Position.SUBSCRIPT 렌더
     (본문 폰트 Noto Sans CJK KR cmap에 글리프 없음 실측)
  F4 step3 문제 오른쪽→다음 장 걸침 0 (enforceQuestionKeep — 불량 출력
     2건: p29→p30 요약, p31→p32 문장삽입)

사용: python3 scripts/e2e_round13.py

안전(출력 리다이렉트): round11/12 하네스와 동일 — _load_v1_config 패치로
출력은 data_corpus/round13/out/, 내지는 data_corpus/template_test/
워크북C_모의고사.indd 로컬 사본. 실 운영 경로/사용자 문서 무접촉.
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
                            "r13c24addu")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round13",
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

    print("== 1/4 parse (r13c24addu)")
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
    # F1: 간지 미입력 → 실측 유형 자동 판정 ('모의고사' 자동 라벨 금지)
    # W24 r14 의미론 갱신: 자동 판정 표기 '추가지문' → '외부지문' 통일
    assert plan["divider"] == {"line1": "외부지문", "line2": "",
                               "source": "type"}, plan["divider"]
    # F3: 플랜에 아래첨자 잔존 0 + sub 서식 run
    resid = sum(p["t"].count("₂") for fl in plan["flows"]
                for u in fl["units"]
                for p in (u["paras"] if isinstance(u, dict) else u))
    subruns = sum(1 for fl in plan["flows"] for u in fl["units"]
                  for p in (u["paras"] if isinstance(u, dict) else u)
                  for r in p.get("runs") or [] if r.get("sub"))
    assert resid == 0 and subruns == 151, (resid, subruns)
    # F4: question_keep 계약 (문제 23개 — 첫 문제 제외)
    qk = plan.get("question_keep") or {}
    assert len((qk.get("flows") or {}).get("step3", {})
               .get("starts") or []) == 23, qk

    print("== 3/4 run_indesign")
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    # ── r13 실측 요약 (피드백 4건) ──────────────────────────────────────
    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    inv = {str(e.get("p")): e for e in pages}
    print(f"\n페이지 수: {dump.get('page_count')}")
    # F1 간지 라벨 실측
    labels = []
    for st in dump.get("stories", []):
        ps = st.get("paragraphs", [])
        if (len(st.get("pg") or []) == 1 and len(ps) >= 2
                and ps[0].get("t", "").startswith(("추가지문", "외부지문"))):
            labels.append(str(st["pg"][0]))
    print("간지(외부지문) 페이지:",
          [(p, inv.get(p, {}).get("side")) for p in sorted(
              labels, key=lambda x: int(x) if x.isdigit() else 0)])
    # F2 짤지문 간지 잔존 실측
    jjm = [st for st in dump.get("stories", [])
           if any("짤지문" in (p.get("t") or "")
                  for p in st.get("paragraphs", []))]
    print("짤지문 간지 스토리:", [(s["idx"], s.get("pg")) for s in jjm]
          or "0 (고아 간지 스프레드 삭제)")
    # F3 ₂ 잔존 실측
    resid_out = sum((p.get("t") or "").count("₂")
                    for st in dump.get("stories", [])
                    for p in st.get("paragraphs", []))
    print("출력 ₂(U+2082) 잔존:", resid_out)
    print("\n결과:", "OK verify ok=True" if result["ok"]
          else "FAIL verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
