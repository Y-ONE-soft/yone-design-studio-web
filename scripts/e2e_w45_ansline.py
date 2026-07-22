#!/usr/bin/env python3
"""W45 E2E — 답란 전용 스타일 `S_답란` 실 InDesign 재조판 실증.

케이스: workbook/0a5da924 (부교재 워크북 — 괄호/콜론 답란이 다수 실린
실사용 원고. round18과 같은 케이스라 이전 결과와 1:1 대조 가능).

검증:
  1. 플랜 — 답란 단락이 s=S_답란 + s_fb=선지 + ind0=true 를 싣는다
  2. 출력 — 그 단락이 실제로 S_답란으로 인쇄된다 (덤프 실측)
  3. 게이트 — G44 ansline_style_present True / miss 0 / critical 0
  4. 회귀 — round18 계약(순열 선지 90행, G40 답란 0건) 유지
  5. 크롭 — 답란이 있는 페이지 PNG (사람 눈 확인용)

안전: 템플릿은 **S_답란을 넣은 로컬 사본**
(data_corpus/template_ansline/워크북C_모의고사.indd — 원본 무수정).
출력은 data_corpus/w45_ansline/ 로 리다이렉트. 사용자가 InDesign에 열어둔
문서는 건드리지 않는다 (사전/사후 문서 목록 대조, 프로세스 kill 없음).

사용: python3 scripts/e2e_w45_ansline.py [--no-png]
"""
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.exists(ENV):
    for _line in open(ENV):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ANSLINE = "S_답란"
TEMPLATE = os.path.join(REPO, "data_corpus", "template_ansline",
                        "워크북C_모의고사.indd")


def _docs():
    try:
        return subprocess.check_output(
            ["osascript", "-e",
             'tell application "Adobe InDesign 2026" to get name of '
             'documents'], text=True).strip()
    except Exception:                                        # noqa: BLE001
        return "(조회 실패)"


def _norm(t):
    return (t or "").replace("\r", "").strip()


_RE_ANSLINE = re.compile(
    r"^[(（]\s*[A-Za-z가-힣0-9]{1,3}\s*[)）]\s*[:：]?\s*_{3,}[\s_]*[.,]?$")


def main():
    want_png = "--no-png" not in sys.argv
    if not os.path.isfile(TEMPLATE):
        print(f"[중단] S_답란 사본 템플릿이 없습니다: {TEMPLATE}\n"
              f"  먼저: python3 scripts/add_ansline_style.py --mode copy "
              f"--targets workbook --use-existing-copy")
        return 2

    case_dir = os.path.join(REPO, "tests", "corpus", "workbook", "0a5da924")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "w45_ansline"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)               # noqa: E731

    docs_before = _docs()
    print(f"[사전] InDesign 문서: {docs_before}")

    import _replay
    import engines.workbook_v2.engine as base_mod
    from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine

    real_load = base_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["_default"] = TEMPLATE
        return cfg

    base_mod._load_v1_config = _patched
    engine = WorkbookSuppV2Engine()

    print("== 1/5 parse")
    _replay.build_job(case_dir, job)
    with open(os.path.join(job, "filename_stem.txt"), "w",
              encoding="utf-8") as f:
        f.write("W45답란")
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/5 prepare_jsx + 플랜 계약")
    engine.prepare_jsx(json_path, job, log)
    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    s3p = [p for fl in plan["flows"] if fl["step"] == "step3"
           for u in fl["units"]
           for p in (u["paras"] if isinstance(u, dict) else u)]
    ansl = [p for p in s3p if ANSLINE in (p.get("s") or "")]
    fails = []
    if len(ansl) < 80:
        fails.append(f"플랜: S_답란 단락 {len(ansl)}개 (80+ 기대)")
    if not all(p.get("s_fb") and p.get("ind0") for p in ansl):
        fails.append("플랜: 답란 폴백/브릿지 필드 누락")
    print(f"  [플랜] S_답란 {len(ansl)}단락 / 폴백 s_fb+ind0 동반 OK")

    print("== 3/5 run_indesign (290p — 저장/PDF 수십 분 가능)")
    for stale in ("조판_로그.txt",):
        p = os.path.join(job, stale)
        if os.path.exists(p):
            os.remove(p)
    engine.run_indesign(job, log)

    print("== 4/5 verify + 게이트 G44")
    result = engine.verify(job, log)
    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    styled = [(_norm(p.get("t")), p.get("s") or "", p)
              for st in dump.get("stories", []) or []
              for p in st.get("paragraphs") or []]

    out_ansl = [(t, s) for t, s, _ in styled if _RE_ANSLINE.match(t)]
    applied = [x for x in out_ansl if ANSLINE in x[1]]
    if not out_ansl:
        fails.append("출력: 괄호 답란 라인이 하나도 없음 (케이스 확인)")
    elif len(applied) < len(out_ansl):
        bad = sorted({s for t, s in out_ansl if ANSLINE not in s})
        fails.append(f"출력: 답란 {len(out_ansl)}행 중 S_답란 "
                     f"{len(applied)}행 (미적용 스타일 {bad})")

    from engines.workbook_v2.gate import inspect_workbook_finish
    content = json.load(open(json_path, encoding="utf-8"))
    rep = inspect_workbook_finish(content, plan, dump,
                                  uploads_dir=os.path.join(job, "uploads"))
    st = rep["stats"]
    if not st.get("ansline_style_present"):
        fails.append("게이트 G44: 출력에 S_답란 흔적 없음")
    if st.get("ansline_style_miss"):
        fails.append(f"게이트 G44: 미적용 {st['ansline_style_miss']}")
    if st.get("paren_blank_miss"):
        fails.append(f"G40 회귀: 답란 스타일 미적용 {st['paren_blank_miss']}")
    if st.get("ansl_miss"):
        fails.append(f"G35 회귀: 답란 쌍 미적용 {st['ansl_miss']}")
    numbered = [t for t, _, _ in styled
                if re.match(r"^[①-⑤] \([ABC]\) － \([ABC]\) － \([ABC]\)$", t)]
    if len(numbered) != 90:
        fails.append(f"round18 회귀: 순열 선지 {len(numbered)}행 (90 기대)")
    crit = list(rep["critical"])
    if crit:
        fails.append(f"게이트 critical {len(crit)}: {crit[:3]}")
    jsx_log = open(os.path.join(job, "조판_로그.txt"),
                   encoding="utf-8").read()
    if "[답란] S_답란 없음" in jsx_log:
        fails.append("렌더: 폴백 경로가 탔다 (사본에 S_답란이 없음?)")

    print(json.dumps({"ok": result.get("ok"),
                      "출력 답란": len(out_ansl),
                      "S_답란 적용": len(applied),
                      "G44 present": st.get("ansline_style_present"),
                      "G44 miss": st.get("ansline_style_miss"),
                      "critical": len(crit),
                      "warnings": len(rep["warnings"])},
                     ensure_ascii=False, indent=1))

    print("== 5/5 크롭 PNG (답란 페이지)")
    if want_png and not fails:
        try:
            from core.visual_inspect import render_indd_pages
            indd = result.get("indd_path") or ""
            if not indd:
                cands = [os.path.join(out, f) for f in os.listdir(out)
                         if f.endswith(".indd")]
                indd = max(cands, key=os.path.getmtime) if cands else ""
            if indd:
                pngs, how = render_indd_pages(
                    indd, os.path.join(out, "png"), log, dpi=110)
                print(f"  PNG {len(pngs)}장 ({how}) → {os.path.join(out, 'png')}")
            else:
                print("  [건너뜀] 산출 .indd 경로를 찾지 못함")
        except Exception as e:                               # noqa: BLE001
            print(f"  [경고] PNG export 실패(검증 무관): {e}")

    for f_ in fails:
        print("FAIL", f_)
    ok = result.get("ok") and not fails
    print("\n결과:", "OK — S_답란 적용 + 게이트 critical 0" if ok else "FAIL")
    docs_after = _docs()
    print(f"[사후] InDesign 문서: {docs_after}")
    if docs_before != docs_after:
        print("경고: 문서 목록 변화 — 확인 필요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
