#!/usr/bin/env python3
"""단락종류 판정기 실측 — 골든 코퍼스 workbook Step3 단락 분포 + UNKNOWN 목록.

사용: python3 scripts/eval_structure.py [--engine workbook] [--show-unknown N]
룰 보강 루프: UNKNOWN 목록 확인 → core/structure/rules.py에 데이터 추가 → 재실행.
"""
import argparse, collections, json, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from core.structure import classify_paragraphs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="workbook")
    ap.add_argument("--show-unknown", type=int, default=20)
    args = ap.parse_args()
    base = os.path.join(REPO, "tests", "corpus", args.engine)
    dist = collections.Counter()
    unknown = collections.Counter()
    for case in sorted(os.listdir(base)):
        g = os.path.join(base, case, "golden", "content.json")
        if not os.path.isfile(g):
            continue
        c = json.load(open(g, encoding="utf-8"))
        step3 = c.get("steps", {}).get("step3") or {}
        for group in ("normal", "short"):
            for item in step3.get(group, []) or []:
                for r in classify_paragraphs(item.get("paragraphs", [])):
                    dist[r["kind"]] += 1
                    if r["kind"] == "UNKNOWN":
                        unknown[r["text"][:80]] += 1
    total = sum(dist.values()) or 1
    for k, v in dist.most_common():
        print(f"  {k:10s} {v:5d} ({v / total * 100:.1f}%)")
    if unknown:
        print(f"\nUNKNOWN {sum(unknown.values())}건 상위 {args.show_unknown}:")
        for t, n in unknown.most_common(args.show_unknown):
            print(f"  {n:3d}x {t!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
