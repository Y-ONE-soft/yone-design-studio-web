#!/usr/bin/env python3
"""품질 루프 12라운드 E2E (W22) — 실사용 2차 피드백 3건 수리의 실기 검증.

케이스: r11c23ext1 (실서비스 job 0e3108fd — 2026 성덕고 외부지문 워크북1,
workbook_supp_v2 _default 내지) — W21 재조판본(62p)과 같은 원고.

수리 검증 항목 (사용자 피드백 3건):
  F1 p34류 장식-빈 페이지 0 (어법선택 발문/영작배열 탭 잔존 페이지 삭제)
  F2 파트 경계 정렬 — 간지 라벨 전부 오른쪽 페이지 (이 코퍼스는 전 섹션이
     짝수 페이지라 M 채움 미발동이 정상. 채움 분기 자체의 실기 검증은
     scripts/e2e_round12_filler_probe.py — 출력 indd 스크래치 사본에 교란)
  F3 간지 '외부지문' (미입력 기본 — 교재유형 표기. 입력 경로는
     divider_text.txt 메타 주입 pytest로 검증)

사용: python3 scripts/e2e_round12.py

안전(출력 리다이렉트): round11 하네스와 동일 — _load_v1_config 패치로
출력은 data_corpus/round12/out/, 내지는 data_corpus/template_test/
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
                            "r11c23ext1")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round12",
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
    # F3: 간지 문구 미입력 → 교재유형(외부지문)만, 모의고사/년월 잔재 없음
    assert plan["divider"] == {"line1": "외부지문", "line2": "",
                               "source": "type"}, plan["divider"]
    units = {f["step"]: len(f["units"]) for f in plan["flows"]}
    for step in ("step1_c2", "step2_a1", "step2_b1", "step2_c1"):
        assert units[step] == 4, (step, units[step])

    print("== 3/4 run_indesign")
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    # ── r12 실측 요약 (피드백 3건) ──────────────────────────────────────
    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    print(f"\n페이지 수: {dump.get('page_count')}")
    label_pages = []
    for st in dump.get("stories", []):
        ps = st.get("paragraphs", [])
        if (len(st.get("pg") or []) == 1 and len(ps) >= 2
                and ps[0].get("t", "").startswith("외부지문")):
            label_pages.append(str(st["pg"][0]))
    inv = {str(e.get("p")): e for e in pages}
    print("간지(외부지문) 페이지:",
          [(p, inv.get(p, {}).get("side")) for p in sorted(
              label_pages, key=lambda x: int(x) if x.isdigit() else 0)])
    m_pages = [e for e in pages if str(e.get("m") or "").startswith("M")]
    print("M 마스터 페이지:", [(e["p"], e["side"]) for e in m_pages]
          or "없음 (전 섹션 짝수 페이지 — 채움 불필요가 정상)")
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
