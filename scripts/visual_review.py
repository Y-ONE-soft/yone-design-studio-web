#!/usr/bin/env python3
"""시각 검수 2층 준비 — 산출물을 검토 폴더로 정리하고 의심 페이지 목록 생성 (W29).

1층(core.visual_inspect)을 실행해 페이지 PNG + 기계 검사 리포트를
data_corpus/visual_review/<이름>/ 에 정리하고, 검수 에이전트(사람 눈 대행)가
열어볼 의심 페이지 목록(review_queue.json)을 남긴다.
큐 = 1층 플래그(critical+review) 페이지 + 무작위 표본 + 고정 표본(첫/가운데/끝).

이후 절차는 .claude/skills/visual-review/SKILL.md — 에이전트가 큐의 이미지를
Read로 열어 체크리스트 검수를 수행하고 review_result.json 을 남긴다.

사용:
  python3 scripts/visual_review.py <job_dir | .pdf> [--dump 덤프.json]
      [--name 검토폴더명] [--dpi 96] [--sample 6] [--seed 0]
job_dir 를 주면 .settings.json/typeset_dump*.json 에서 산출물·덤프 자동 발견.
"""
import argparse
import json
import os
import random
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.visual_inspect import (  # noqa: E402
    inspect_pages, render_pdf_pages, _find_output_files,
)

REVIEW_ROOT = os.path.join(ROOT, "data_corpus", "visual_review")


def _discover(target):
    """job_dir 또는 pdf 경로 → (pdf_path, dump_path|None, 기본이름)."""
    target = os.path.abspath(target)
    if target.lower().endswith(".pdf"):
        return target, None, os.path.splitext(os.path.basename(target))[0]
    if not os.path.isdir(target):
        raise SystemExit(f"대상 없음: {target}")
    pdfs = []
    sp = os.path.join(target, ".settings.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as f:
            _find_output_files(json.load(f), (".pdf",), pdfs)
    if not pdfs:   # job_dir 자체/out 하위 탐색
        for base in (target, os.path.join(target, "out")):
            if os.path.isdir(base):
                pdfs += [os.path.join(base, n) for n in sorted(os.listdir(base))
                         if n.lower().endswith(".pdf")]
    if not pdfs:
        raise SystemExit(f"PDF를 찾지 못함: {target}")
    dump = None
    for name in sorted(os.listdir(target)):
        if name.startswith("typeset_dump") and name.endswith(".json"):
            dump = os.path.join(target, name)
            break
    return pdfs[0], dump, os.path.basename(target.rstrip("/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="job_dir 또는 .pdf")
    ap.add_argument("--dump", help="typeset_dump.json 경로 (자동 발견 덮어쓰기)")
    ap.add_argument("--name", help="검토 폴더 이름 (기본: 대상 이름)")
    ap.add_argument("--dpi", type=int, default=96,
                    help="렌더 해상도 (2층은 눈으로 보므로 96 권장)")
    ap.add_argument("--sample", type=int, default=6, help="무작위 표본 페이지 수")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    pdf, dump_path, default_name = _discover(args.target)
    if args.dump:
        dump_path = os.path.abspath(args.dump)
    name = args.name or default_name
    out_dir = os.path.join(REVIEW_ROOT, name)
    pages_dir = os.path.join(out_dir, "pages")
    if os.path.isdir(pages_dir):
        shutil.rmtree(pages_dir)
    os.makedirs(pages_dir, exist_ok=True)

    print(f"[1/3] 렌더: {pdf} @ {args.dpi}dpi")
    pngs, backend = render_pdf_pages(pdf, pages_dir, dpi=args.dpi, log=print)
    dump = None
    if dump_path and os.path.isfile(dump_path):
        with open(dump_path, encoding="utf-8") as f:
            dump = json.load(f)

    print(f"[2/3] 1층 기계 검사 ({len(pngs)}페이지, dump={'있음' if dump else '없음'})")
    report = inspect_pages(pngs, dump=dump)
    report["source"] = pdf
    report["render_backend"] = backend
    report["dpi"] = args.dpi
    with open(os.path.join(out_dir, "visual_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # 의심 페이지 큐: 플래그(critical/review) + 고정 표본 + 무작위 표본
    flagged = list(report["summary"]["flagged_pages"])
    n = report["page_count"]
    fixed = {1, max(1, n // 2), n}
    rng = random.Random(args.seed)
    rest = [p for p in range(1, n + 1) if p not in flagged and p not in fixed]
    randoms = sorted(rng.sample(rest, min(args.sample, len(rest))))
    queue = []
    page_by_num = {p["page"]: p for p in report["pages"]}
    for p in sorted(set(flagged) | fixed | set(randoms)):
        rec = page_by_num[p]
        reason = ([f"{f['code']}({f['level']}): {f['detail']}"
                   for f in rec["flags"] if f["level"] in ("critical", "review")]
                  or (["고정 표본"] if p in fixed else ["무작위 표본"]))
        queue.append({"page": p, "png": os.path.relpath(rec["png"], out_dir),
                      "reasons": reason})
    doc_items = [f"{f['code']}({f['level']}): {f['detail']}"
                 for f in report["doc_flags"]]
    with open(os.path.join(out_dir, "review_queue.json"), "w",
              encoding="utf-8") as f:
        json.dump({
            "name": name, "source": pdf, "page_count": n,
            "layer1": {"critical": report["summary"]["critical"],
                       "review": report["summary"]["review"],
                       "doc_flags": doc_items},
            "queue": queue,
            "skill": ".claude/skills/visual-review/SKILL.md",
            "result_file": "review_result.json",
        }, f, ensure_ascii=False, indent=1)

    print(f"[3/3] 검토 폴더: {out_dir}")
    print(f"  1층: critical {report['summary']['critical']} / "
          f"review {report['summary']['review']}")
    print(f"  큐: {len(queue)}페이지 — {[q['page'] for q in queue]}")
    print("  다음: visual-review 스킬 절차로 큐 이미지를 검수하고 "
          "review_result.json 작성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
