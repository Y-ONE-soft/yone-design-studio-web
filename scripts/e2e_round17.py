#!/usr/bin/env python3
"""품질 루프 17라운드(W39) E2E — 하향식 슬롯 배정 전환 + 지목 결함 6건 검증.

케이스: r15c25ybm2 (공통영어2 YBM(김) 1과 — 골든은 W39 슬롯 배정 승격본).
검증(재조판 실측 — 문항 번호는 전권 통산):
  1. [요약문] 마커 + 요약 문장 = 배경 (W38 회귀 확인 — 꺾쇠형은 이
     원고에 없음: 유닛/코퍼스 검증 + supp 크롭은 별도)
  2. 87번 주어진 문장(❮…❯→〈…〉) = 배경 스타일 (문장삽입 6건 전수)
  3. 84/85번 조건 블록 단어 나열 = 조건 스타일 (8건)
  4. 84/85번 "주제문:" + 빈칸 = 답란(선지 계열) 스타일 (8라인)
  5. 111번 "N) 문장 (T/F)" 행 = 선지 스타일 (20행)
  6. 발문 "밑줄 친 <영어구>" 인용 밑줄 — 플랜 runs 검증(G37) + PDF 크롭
  + 게이트 critical 0 + verify ok + 오버플로우 0 + 사용자 문서 무접촉

사용: python3 scripts/e2e_round17.py

안전: 출력 리다이렉트 (data_corpus/round17/c25_tb/), 내지는 로컬 사본
(data_corpus/template_test/워크북C_모의고사.indd). 사용자 문서 무접촉 —
InDesign에 열려 있는 다른 문서를 닫지 않는다.
"""
import json
import os
import re
import shutil
import subprocess
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


def _docs():
    try:
        return subprocess.check_output(
            ["osascript", "-e",
             'tell application "Adobe InDesign 2026" to get name of '
             'documents'], text=True).strip()
    except Exception:
        return "(조회 실패)"


def main():
    case_dir = os.path.join(REPO, "tests", "corpus", "textbook_workbook",
                            "r15c25ybm2")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round17",
                                       "c25_tb"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)   # noqa: E731

    docs_before = _docs()
    print(f"[사전] InDesign 문서: {docs_before}")

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

    print("== 1/3 prepare_jsx (r15c25ybm2 — W39 승격 골든 content.json)")
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
    assert not plan.get("warnings"), plan.get("warnings")
    s3 = next(fl for fl in plan["flows"] if fl["step"] == "step3")
    s3p = [p for u in s3["units"]
           for p in (u["paras"] if isinstance(u, dict) else u)]

    # 플랜 선검증 (6건)
    given = [p for p in s3p if p["t"].strip().startswith(("❮", "〈"))]
    wordlists = [p for p in s3p if re.match(
        r"^(?:creator|of / the|optimism|with /|transform|the future|is / be"
        r"|serve)", p["t"].strip())]
    ansl = [p for p in s3p if p["t"].strip() == "주제문:"
            or re.match(r"^_{20,}\.$", p["t"].strip())]
    tf_rows = [p for p in s3p
               if re.match(r"^\d\)\s.*\(T/F\)\s*$", p["t"].strip())]
    sums = [p for p in s3p if p["t"].strip() == "[요약문]"]
    q_ul = [p for p in s3p if "밑줄 친 " in p["t"]
            and any(r.get("ul") for r in p.get("runs") or [])
            and "번호" in p["s"]]
    assert len(given) == 6 and all("배경" in p["s"] for p in given), \
        [(p["t"][:30], p["s"]) for p in given]
    assert len(wordlists) == 8 and all("조건" in p["s"] for p in wordlists), \
        [(p["t"][:30], p["s"]) for p in wordlists]
    assert len(ansl) == 8 and all("선지" in p["s"] for p in ansl), \
        [(p["t"][:30], p["s"]) for p in ansl]
    assert len(tf_rows) == 20 and all("선지" in p["s"] for p in tf_rows), \
        [(p["t"][:40], p["s"]) for p in tf_rows]
    assert len(sums) == 9 and all("배경" in p["s"] for p in sums)
    assert len(q_ul) >= 9, len(q_ul)
    print(f"  [플랜] 주어진 문장 배경 {len(given)} / 조건 나열 "
          f"{len(wordlists)} / 답란 {len(ansl)} / T/F 선지 {len(tf_rows)} / "
          f"[요약문] 배경 {len(sums)} / 발문 인용 밑줄 {len(q_ul)} OK")

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
    styled = [(_norm(p.get("t") or ""), p.get("s") or "")
              for st in dump.get("stories", []) or []
              for p in st.get("paragraphs") or []]

    fails = []
    # 결함 2 — 주어진 문장(글리프 매핑 후 〈…〉) 배경
    d_given = [(t, s) for t, s in styled if t.startswith("〈")]
    if len(d_given) != 6 or any("배경" not in s for t, s in d_given):
        fails.append(f"결함2: 주어진 문장 배경 {d_given}")
    # 결함 3 — 조건 나열
    d_wl = [(t, s) for t, s in styled
            if re.match(r"^(?:creator|of / the|optimism|with /|transform"
                        r"|the future|is / be|serve)", t)]
    if len(d_wl) != 8 or any("조건" not in s for t, s in d_wl):
        fails.append(f"결함3: 조건 나열 {[(t[:20], s) for t, s in d_wl]}")
    # 결함 4 — 답란
    d_ansl = [(t, s) for t, s in styled
              if t == "주제문:" or re.match(r"^_{20,}\.$", t)]
    if len(d_ansl) != 8 or any("선지" not in s for t, s in d_ansl):
        fails.append(f"결함4: 답란 {[(t[:15], s) for t, s in d_ansl]}")
    # 결함 5 — T/F 선지
    d_tf = [(t, s) for t, s in styled
            if re.match(r"^\d\)\s.*\(T/F\)$", t)]
    if len(d_tf) != 20 or any("선지" not in s for t, s in d_tf):
        fails.append(f"결함5: T/F 선지 {len(d_tf)}건 "
                     f"{sorted({s for _, s in d_tf})}")
    # 결함 1(회귀) — [요약문] 배경
    d_sum = [(t, s) for t, s in styled if t == "[요약문]"]
    if len(d_sum) != 9 or any("배경" not in s for t, s in d_sum):
        fails.append(f"결함1: [요약문] 배경 {d_sum}")

    for f in fails:
        print("FAIL", f)
    ok = result["ok"] and not fails
    print("\n결과:", "OK verify ok=True + 결함 실측 해소 (밑줄은 크롭 확인)"
          if ok else "FAIL")
    docs_after = _docs()
    print(f"[사후] InDesign 문서: {docs_after}")
    if docs_before != docs_after:
        print("경고: 문서 목록 변화 — 확인 필요")
    return 0 if ok else 1


def _norm(t):
    return t.replace("\r", "").strip()


if __name__ == "__main__":
    sys.exit(main())
