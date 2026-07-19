#!/usr/bin/env python3
"""품질 루프 15라운드 E2E — 실서비스 결함 7건(job 376b34d0) 수리 검증.

케이스: r15c25ybm2 (공통영어2 YBM(김) 1과 — W30-r15 실사용 코퍼스).
검증(재조판 실측):
  1~4. 교과서 L-p-코너명형 헤더 인식 — step1_c2/step2_b1/step2_c1 유닛 6,
       step1_c1 유닛 12({추가본문} 포함), 헤더 원문 인쇄 0 (G1/G24)
  5.   step3 출처 라인 인쇄 0 (G1 확장 [출처잔존])
  6.   오버플로우 확장 페이지 2단 프레임 복제 (G31 [프레임결손] 0)
  7.   크레딧(판권) 왼쪽 정렬 + 오른쪽 메모(M) 페이지 (G28④)

사용: python3 scripts/e2e_round15.py

안전(출력 리다이렉트): 엔진 _load_v1_config 패치 — indd_output_dir →
data_corpus/round15/c25_tb/, 내지는 data_corpus/template_test/
워크북C_모의고사.indd 로컬 사본. 실 운영 경로/사용자 문서 무접촉.
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
                            "r15c25ybm2")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round15",
                                       "c25_tb"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)   # noqa: E731

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

    print("== 1/3 prepare_jsx (r15c25ybm2 — 코퍼스 content.json 재사용)")
    for fn in os.listdir(os.path.join(case_dir, "meta")):
        if fn.endswith(".txt"):
            shutil.copy2(os.path.join(case_dir, "meta", fn),
                         os.path.join(job, fn))
    json_path = os.path.join(job, "content.json")
    shutil.copy2(os.path.join(case_dir, "golden", "content.json"), json_path)
    engine.prepare_jsx(json_path, job, log)

    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    by_step = {fl["step"]: len(fl["units"]) for fl in plan["flows"]}
    print(f"  [플랜] 유닛: c2={by_step.get('step1_c2')} "
          f"b1={by_step.get('step2_b1')} 2c1={by_step.get('step2_c1')} "
          f"c1={by_step.get('step1_c1')} / 경고 {plan.get('warnings')}")
    assert by_step.get("step1_c2") == 6 and by_step.get("step2_b1") == 6
    assert by_step.get("step2_c1") == 6 and by_step.get("step1_c1") == 12
    ppu = [fl["step"] for fl in plan["flows"]
           if (fl.get("target") or {}).get("per_passage_units")]
    print(f"  [플랜] per_passage_units 계약: {sorted(ppu)}")

    print("== 2/3 run_indesign")
    # 러너 stale 완료마커 조기반환 방지 (W7 함정) — 이전 실행 로그 제거
    for stale in ("조판_로그.txt",):
        p = os.path.join(job, stale)
        if os.path.exists(p):
            os.remove(p)
    engine.run_indesign(job, log)

    print("== 3/3 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    # ── r15 실측 요약 (결함 6/7 지오메트리) ──────────────────────────────
    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    print(f"\n페이지 수: {dump.get('page_count')}")
    framed = set()
    for st in dump.get("stories", []):
        for p in st.get("fp") or []:
            framed.add(str(p))
    tail = [(pe.get("p"), pe.get("m"), pe.get("side"))
            for pe in pages[-4:]]
    print("말미 페이지:", tail)
    big = max(dump.get("stories", []),
              key=lambda s: len(s.get("paragraphs") or []))
    from collections import Counter
    cnt = Counter(str(p) for p in big.get("fp") or [])
    order = []
    for p in big.get("fp") or []:
        if str(p) not in order:
            order.append(str(p))
    deficient = [p for p in order[1:-1] if cnt[p] < 2]
    print(f"step3 스토리 페이지 {len(order)}개 / 중간 1프레임 페이지: "
          f"{deficient or 0}")
    print("\n결과:", "OK verify ok=True" if result["ok"]
          else "FAIL verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
