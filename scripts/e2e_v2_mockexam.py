#!/usr/bin/env python3
"""동형 v2 E2E — 코퍼스 원고 → v2 IR → 렌더 플랜 → 실제 InDesign 조판 → 검수.

사용: python3 scripts/e2e_v2_mockexam.py [029c4385]
안전: 템플릿 원본은 safe_copy로 스크래치 복사, 출력은 data_corpus/e2e_v2/.
기존 mockexam(v1)은 관여하지 않는다.
"""
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "029c4385"
    cdir = os.path.join(REPO, "tests", "corpus", "mockexam", case)
    out = os.path.join(REPO, "data_corpus", "e2e_v2", case)
    os.makedirs(out, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    school = open(f"{cdir}/meta/school.txt").read().strip()
    grade = open(f"{cdir}/meta/grade.txt").read().strip()
    print(f"== 1/5 v2 parse ({case}: {school} {grade})")
    from engines.mockexam_v2.parser import parse_manuscripts
    docs = parse_manuscripts(glob.glob(f"{cdir}/inputs/*"),
                             meta={"school": school, "grade": grade}, log=log)
    name, doc = docs[0]     # 1회분 파일럿
    json.dump(doc, open(f"{out}/content_v2.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  회차: {name} — 문항 {len(doc['items'])}")

    print("== 2/5 렌더 플랜")
    from engines.mockexam_v2.render import ir_to_render_plan
    plan = ir_to_render_plan(doc)
    plan_path = f"{out}/render_plan.json"
    json.dump(plan, open(plan_path, "w", encoding="utf-8"), ensure_ascii=False)
    styles = sorted({p["s"] for p in plan if p["s"]})
    print(f"  단락 {len(plan)}개 / 스타일 {len(styles)}종: {styles}")

    print("== 3/5 템플릿 복사 + InDesign 조판")
    from core.paths import resolve
    from core.base import safe_copy_indd
    from core.indesign.jsxbuild import build_jsx
    from core.indesign.runner import run_jsx
    gnum = re.sub(r"\D", "", grade) or "1"
    src = resolve(f"조판/인디자인 원본/[원본]{school[:2]}{gnum}_동형모의고사.indd")
    tpl = safe_copy_indd(src, f"{out}/template.indd")
    out_indd = f"{out}/{school[:2]}{gnum}_동형_v2.indd"
    out_pdf = out_indd.replace(".indd", ".pdf")
    jsx_log = f"{out}/render.log"
    try:
        os.remove(jsx_log)
    except OSError:
        pass
    jsx = build_jsx(os.path.join(REPO, "core", "jsx", "render_flow.body.jsx"),
                    {"__TEMPLATE_PATH__": tpl, "__PLAN_PATH__": plan_path,
                     "__OUT_INDD__": out_indd, "__OUT_PDF__": out_pdf},
                    log_path=jsx_log)
    run_jsx(jsx, log, poll_log_path=jsx_log, timeout=900,
            completion_marker="v2 조판 완료")

    print("== 4/5 스토리 덤프")
    from core.inspect import dump_indd
    dump = dump_indd(out_indd, f"{out}/typeset_dump.json", log)

    print("== 5/5 검수 (내용 보존 + 스타일)")
    want = {w.lower() for p in plan for w in _RE_WORD.findall(p["t"])}
    got = set()
    style_hit = style_total = 0
    dump_texts = {}
    for st in dump["stories"]:
        for pp in st["paragraphs"]:
            for w in _RE_WORD.findall(pp["t"]):
                got.add(w.lower())
            key = re.sub(r"\s+", " ", pp["t"]).strip()[:60]
            if key and key not in dump_texts:
                dump_texts[key] = pp["s"]
    for p in plan:
        if not p["s"]:
            continue
        key = re.sub(r"\s+", " ", p["t"]).strip()[:60]
        if key in dump_texts:
            style_total += 1
            actual = dump_texts[key]
            if actual == p["s"] or actual.endswith("> " + p["s"]):
                style_hit += 1
    missing = want - got
    report = {
        "items": len(doc["items"]),
        "plan_paragraphs": len(plan),
        "missing_words": len(missing),
        "missing_sample": sorted(missing)[:10],
        "style_matched": style_hit,
        "style_total": style_total,
        "overflow_stories": dump.get("overflow_stories", 0),
        "render_warnings": [l for l in open(jsx_log, encoding="utf-8")
                            if "[경고]" in l],
    }
    json.dump(report, open(f"{out}/report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    ok = report["missing_words"] == 0
    print("\n결과:", "✅ 내용 보존 통과" if ok else "❌ 내용 누락")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
