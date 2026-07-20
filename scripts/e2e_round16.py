#!/usr/bin/env python3
"""품질 루프 16라운드(W38) E2E — 실서비스 결함 5건(job 6b66b750) 수리 검증.

케이스: r15c25ybm2 (공통영어2 YBM(김) 1과 — 골든은 W38 블록 문법 승격본).
검증(재조판 실측):
  1. 크레딧(판권) = 왼쪽 + 문서 마지막 페이지 (뒤 잔여 페이지 0 — 스펙 정정)
  2. 빈칸어휘/빈칸어법 지문번호 라벨 프레임 좌/우 크기 동일 (왼쪽 기준)
  3. <조건> 블록 번호 항목("1) …시오.") = 조건 스타일 (발문 스타일 0)
  4. [요약문] 마커 + 요약 문장 = 배경 스타일
  5. 영어 지시문 발문("Choose True or False …") = 발문 스타일 + 번호 제거
  + 게이트 critical 0 (G13/G15/G28④/G32/G33 갱신 계약)

사용: python3 scripts/e2e_round16.py

안전: 출력 리다이렉트 (data_corpus/round16/c25_tb/), 내지는 로컬 사본
(data_corpus/template_test/워크북C_모의고사.indd). 사용자 문서 무접촉 —
InDesign에 열려 있는 다른 문서를 닫지 않는다.
"""
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.exists(ENV):
    for _line in open(ENV):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def main():
    case_dir = os.path.join(REPO, "tests", "corpus", "textbook_workbook",
                            "r15c25ybm2")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round16",
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

    print("== 1/3 prepare_jsx (r15c25ybm2 — W38 승격 골든 content.json)")
    for fn in os.listdir(os.path.join(case_dir, "meta")):
        if fn.endswith(".txt"):
            shutil.copy2(os.path.join(case_dir, "meta", fn),
                         os.path.join(job, fn))
    json_path = os.path.join(job, "content.json")
    shutil.copy2(os.path.join(case_dir, "golden", "content.json"), json_path)
    engine.prepare_jsx(json_path, job, log)

    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    print(f"  [플랜] 경고: {plan.get('warnings')}")
    s3 = next(fl for fl in plan["flows"] if fl["step"] == "step3")
    s3p = [p for u in s3["units"]
           for p in (u["paras"] if isinstance(u, dict) else u)]
    cond_items = [p for p in s3p if p["t"].strip().startswith(("1)", "2)"))
                  and "시오" in p["t"]]
    sum_marks = [p for p in s3p if p["t"].strip() == "[요약문]"]
    eng_qs = [p for p in s3p if p["t"].startswith("Choose True or False")]
    assert cond_items and all("조건" in p["s"] for p in cond_items), \
        [p["s"] for p in cond_items]
    assert len(sum_marks) == 9 and all("배경" in p["s"] for p in sum_marks)
    assert len(eng_qs) == 4 and all("번호" in p["s"] for p in eng_qs), \
        [p["s"] for p in eng_qs]
    print(f"  [플랜] 조건 항목 {len(cond_items)} 전부 조건 스타일 / "
          f"[요약문] {len(sum_marks)} 배경 / 영어 발문 {len(eng_qs)} "
          f"번호 스타일+번호 제거 OK")

    print("== 2/3 run_indesign")
    for stale in ("조판_로그.txt",):
        p = os.path.join(job, stale)
        if os.path.exists(p):
            os.remove(p)
    engine.run_indesign(job, log)

    print("== 3/3 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    print(f"\n페이지 수: {dump.get('page_count')}")
    tail = [(pe.get("p"), pe.get("m"), pe.get("side"))
            for pe in pages[-4:]]
    print("말미 페이지:", tail)

    fails = []
    # 결함 1 — 크레딧 = 왼쪽 + 마지막 (뒤 잔여 0)
    last = pages[-1]
    if not (str(last.get("m") or "") in ("", "[None]")
            and last.get("side") == "L"):
        fails.append(f"결함1: 마지막 페이지가 크레딧-L이 아님 {tail}")

    # 결함 2 — 라벨 프레임 좌/우 크기 (본문N/추가본문)
    pinv = {str(pe.get("p")): pe for pe in pages}
    geo = {"L": [], "R": []}
    for st in dump.get("stories", []):
        ps = st.get("paragraphs") or []
        if len(ps) != 1:
            continue
        tt = (ps[0].get("t") or "").strip()
        if not (tt.startswith("본문") or tt == "추가본문"):
            continue
        fbs, pgs = st.get("fb") or [], st.get("pg") or []
        if len(fbs) == 1 and len(pgs) == 1:
            pe = pinv.get(str(pgs[0]))
            b = fbs[0]
            if pe and abs((b[2] - b[0]) - 52.92) < 3:   # 세로형 라벨만
                geo[pe.get("side")].append(round(b[3] - b[1], 2))
    print(f"세로 라벨 폭 — L: {sorted(set(geo['L']))} / "
          f"R: {sorted(set(geo['R']))}")
    if geo["L"] and geo["R"]:
        if max(geo["R"]) - min(geo["L"] + geo["R"]) > 0.3 \
                or abs(max(geo["R"]) - max(geo["L"])) > 0.3:
            fails.append(f"결함2: 좌/우 라벨 폭 불일치 {geo}")
    else:
        fails.append("결함2: 라벨 프레임 실측 불가")

    # 결함 3/4/5 — 덤프 스타일 실측
    styled = [(p.get("t") or "", p.get("s") or "")
              for st in dump.get("stories", []) or []
              for p in st.get("paragraphs") or []]
    bad3 = [t for t, s in styled
            if t.strip().startswith(("1)", "2)")) and "시오" in t
            and "조건" not in s]
    bad4 = [t for t, s in styled if t.strip() == "[요약문]" and "배경" not in s]
    ok5 = [s for t, s in styled if t.startswith("Choose True or False")]
    bad5 = [t for t, s in styled
            if t.strip().startswith("10. Choose True")]   # 번호 잔존 = 미인식
    if bad3:
        fails.append(f"결함3: 조건 항목 비조건 스타일 {len(bad3)}건")
    if bad4:
        fails.append(f"결함4: [요약문] 비배경 {len(bad4)}건")
    if not ok5 or any("번호" not in s for s in ok5) or bad5:
        fails.append(f"결함5: 영어 발문 스타일/번호 이상 (Q스타일 {ok5}, "
                     f"번호 잔존 {len(bad5)})")
    print(f"결함3 잔존 {len(bad3)} / 결함4 잔존 {len(bad4)} / "
          f"결함5 영어발문 {len(ok5)}건 번호제거+Q스타일, 번호잔존 {len(bad5)}")

    for f in fails:
        print("FAIL", f)
    print("\n결과:", "OK verify ok=True + 결함 5건 실측 해소"
          if (result["ok"] and not fails) else "FAIL")
    return 0 if (result["ok"] and not fails) else 1


if __name__ == "__main__":
    sys.exit(main())
