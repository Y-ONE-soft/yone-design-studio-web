#!/usr/bin/env python3
"""품질 루프 18라운드(W40) E2E — 사용자 육안 검수 6건 수리 실 InDesign 검증.

케이스: workbook/0a5da924 (부교재 워크북 "워크북E2E테스트" — 실사용 지목
원고). parse→prepare→InDesign 재조판→verify + 결함 6건 덤프 실측:
  1. 다열 선지 열 정렬 — cx 실측 열 편차 0 (G42) + 탭 그룹 존재
  2. 발문 고아 — stem_orphans 0 (G41)
  3. 순서배열 선지 원문자 — bare 순열 행 0 + "① (A) － (C) － (B)" 선지 90행
  4. 네모/괄호 지문 배경 — paren_q_bg 0 (G39)
  5. 보기/조건 뒤 "(A) ___" 답란 — 선지 스타일 (G40 0건)
  6. 밑줄 빈칸 프레임 경계 — hox 실측 (0 또는 자간 한도 [경고] 짝)
  + verify ok / critical 0 / 사용자 문서 무접촉

사용: python3 scripts/e2e_round18.py

안전: 출력 리다이렉트 (data_corpus/round18/supp_0a5da924/), 내지는 로컬
사본 (data_corpus/template_test/워크북C_모의고사.indd). InDesign에 열려
있는 다른 문서 무접촉 (사전/사후 문서 목록 대조).
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


def _docs():
    try:
        return subprocess.check_output(
            ["osascript", "-e",
             'tell application "Adobe InDesign 2026" to get name of '
             'documents'], text=True).strip()
    except Exception:
        return "(조회 실패)"


def _norm(t):
    return (t or "").replace("\r", "").strip()


def main():
    case_dir = os.path.join(REPO, "tests", "corpus", "workbook", "0a5da924")
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round18",
                                       "supp_0a5da924"))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)   # noqa: E731

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
        cfg["indd_original"]["_default"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        return cfg

    base_mod._load_v1_config = _patched
    engine = WorkbookSuppV2Engine()

    print("== 1/4 parse (0a5da924 재파싱 — W40 수리 반영)")
    _replay.build_job(case_dir, job)
    with open(os.path.join(job, "filename_stem.txt"), "w",
              encoding="utf-8") as f:
        f.write("E2E테스트")
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)
    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    # 플랜 선검증 — W40 op 계약
    assert plan.get("choice_tabs", {}).get("steps") == ["step3"]
    assert plan.get("blank_fit", {}).get("max_tracking") == -50
    assert plan.get("question_keep", {}).get("stem_keep") == {"min_lines": 2}
    s3p = [p for fl in plan["flows"] if fl["step"] == "step3"
           for u in fl["units"]
           for p in (u["paras"] if isinstance(u, dict) else u)]
    perm = [p for p in s3p
            if re.match(r"^[①-⑤] \([ABC]\) － \([ABC]\) － \([ABC]\)$",
                        _norm(p["t"]))]
    assert len(perm) == 90 and all("선지" in p["s"] for p in perm), \
        (len(perm), sorted({p["s"] for p in perm}))
    paren_blank = [p for p in s3p
                   if re.match(r"^\([A-C]\)\s*[:：]?\s*_{3,}", _norm(p["t"]))
                   and "선지" in p["s"]]
    assert len(paren_blank) >= 80, len(paren_blank)
    print(f"  [플랜] 순열 선지 {len(perm)}행 / 괄호 답란 "
          f"{len(paren_blank)}행 / op 3종 OK")

    print("== 3/4 run_indesign (290p — 저장/PDF 수십 분 가능)")
    for stale in ("조판_로그.txt",):
        p = os.path.join(job, stale)
        if os.path.exists(p):
            os.remove(p)
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트 + 결함 실측)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    styled = [(_norm(p.get("t")), p.get("s") or "", p)
              for st in dump.get("stories", []) or []
              for p in st.get("paragraphs") or []]

    fails = []
    # 결함 3 — bare 순열 행 0 + 원문자 순열 행 90 (선지 스타일)
    bare = [t for t, s, _ in styled
            if re.match(r"^\([ABC]\) － \([ABC]\) － \([ABC]\)$", t)]
    numbered = [(t, s) for t, s, _ in styled
                if re.match(r"^[①-⑤] \([ABC]\) － \([ABC]\) － \([ABC]\)$",
                            t)]
    if bare:
        fails.append(f"결함3: 원문자 없는 순열 행 잔존 {len(bare)}")
    if len(numbered) != 90 or any("선지" not in s for _, s in numbered):
        fails.append(f"결함3: 순열 선지 {len(numbered)}행 "
                     f"{sorted({s for _, s in numbered})}")
    # 결함 4 — 네모어법 발문 직후 배경 0 (게이트 통계로 재확인)
    from engines.workbook_v2.gate import inspect_workbook_finish
    content = json.load(open(json_path, encoding="utf-8"))
    rep = inspect_workbook_finish(content, plan, dump,
                                  uploads_dir=os.path.join(job, "uploads"))
    if rep["stats"].get("paren_q_bg"):
        fails.append(f"결함4: 배경 오적용 {rep['stats']['paren_q_bg']}")
    # 결함 5 — 보기/조건 뒤 괄호 답란 스타일
    if rep["stats"].get("paren_blank_miss"):
        fails.append(f"결함5: 답란 스타일 미적용 "
                     f"{rep['stats']['paren_blank_miss']}")
    # 결함 2 — 발문 고아 0
    if rep["stats"].get("stem_orphans"):
        fails.append(f"결함2: 발문 고아 잔존 {rep['stats']['stem_orphans']}")
    # 결함 1 — 열 정렬 편차 0 + cx 실측 존재
    if rep["stats"].get("choice_tab_misaligned"):
        fails.append(f"결함1: 열 불일치 "
                     f"{rep['stats']['choice_tab_misaligned']}")
    has_cx = any(p.get("cx") for _, _, p in styled)
    if not has_cx:
        fails.append("결함1: 덤프 cx 필드 없음 (재덤프/렌더 확인)")
    # 결함 6 — hox 실측 (0이 이상적, 잔존은 자간 한도 [경고] 짝 확인)
    hox = dump.get("hox") or []
    jsx_log = open(os.path.join(job, "조판_로그.txt"),
                   encoding="utf-8").read()
    if hox and "한도" not in jsx_log:
        fails.append(f"결함6: 경계 초과 {len(hox)}건인데 자간 한도 [경고] "
                     f"로그 없음 (보정 미동작 의심)")
    if "빈칸넘침 보정" not in jsx_log:
        fails.append("결함6: blank_fit 실행 흔적 없음")
    if "선지열정렬" not in jsx_log:
        fails.append("결함1: choice_tabs 실행 흔적 없음")
    if "발문고아킵" not in jsx_log:
        fails.append("결함2: stem_keep 실행 흔적 없음")

    crit = [c for c in rep["critical"]]
    if crit:
        fails.append(f"게이트 critical {len(crit)}: {crit[:3]}")

    for f_ in fails:
        print("FAIL", f_)
    print(f"  [실측] 순열 선지 {len(numbered)} / hox {len(hox)} / "
          f"게이트 warning {len(rep['warnings'])}")
    ok = result["ok"] and not fails
    print("\n결과:", "OK — 결함 6건 실측 해소 + verify ok" if ok else "FAIL")
    docs_after = _docs()
    print(f"[사후] InDesign 문서: {docs_after}")
    if docs_before != docs_after:
        print("경고: 문서 목록 변화 — 확인 필요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
