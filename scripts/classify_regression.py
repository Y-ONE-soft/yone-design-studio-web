#!/usr/bin/env python3
"""발문 분류 리그레션 — 룰 변경이 분류율을 어디서 올리고/깨뜨리는지 수치로 확인.

사용:
    python3 scripts/classify_regression.py                    # 베이스라인과 비교
    python3 scripts/classify_regression.py --update-baseline  # 현재 결과를 베이스라인으로

입력:  data_corpus/manuscripts_questions.jsonl (scripts/extract_questions.py 산출)
베이스라인: tests/classify_baseline.json (git 관리 — 코드별 집계 + 분류율)

비교 로직:
  - 전체/카테고리별 분류율 변화
  - leaf 코드별 건수 변화 (신규/소멸/증감)
  - "분류되던 발문이 미분류로 떨어진" 회귀는 실패(exit 1)로 처리
    (동일 발문 텍스트의 코드 이동은 정보로만 표시 — 룰 개선의 정상 결과일 수 있음)
"""
import argparse
import collections
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

CORPUS = os.path.join(REPO, "data_corpus", "manuscripts_questions.jsonl")
BASELINE = os.path.join(REPO, "tests", "classify_baseline.json")


def run_classification():
    from engines._taxonomy import classify
    per_code = collections.Counter()
    per_cat_total = collections.Counter()
    per_cat_hit = collections.Counter()
    unclassified = collections.Counter()   # 발문 텍스트 → 빈도
    total = 0
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            q = (item.get("q") or "").strip()
            if not q:
                continue
            total += 1
            cat = item.get("category") or "(없음)"
            per_cat_total[cat] += 1
            code, _label, _kind = classify(q)
            if code:
                per_code[code] += 1
                per_cat_hit[cat] += 1
            else:
                unclassified[q] += 1
    return {
        "total": total,
        "classified": sum(per_code.values()),
        "rate": round(sum(per_code.values()) / total * 100, 2) if total else 0.0,
        "per_code": dict(sorted(per_code.items())),
        "per_category_rate": {
            c: round(per_cat_hit[c] / n * 100, 1)
            for c, n in sorted(per_cat_total.items()) if n >= 50
        },
        "top_unclassified": [
            {"q": q, "n": n} for q, n in unclassified.most_common(50)
        ],
        "unclassified_kinds": len(unclassified),
    }


def compare(base, cur):
    print(f"전체: {cur['classified']}/{cur['total']} = {cur['rate']}% "
          f"(베이스라인 {base['rate']}%, {cur['rate'] - base['rate']:+.2f}%p)")
    regressed = cur["rate"] < base["rate"] - 0.05  # 부동소수 여유
    b_codes, c_codes = base["per_code"], cur["per_code"]
    changes = []
    for code in sorted(set(b_codes) | set(c_codes)):
        d = c_codes.get(code, 0) - b_codes.get(code, 0)
        if d:
            changes.append((abs(d), code, b_codes.get(code, 0), c_codes.get(code, 0)))
    if changes:
        print("\n코드별 변화 (상위 20):")
        for _, code, b, c in sorted(changes, reverse=True)[:20]:
            print(f"  {code:32s} {b:6d} → {c:6d} ({c - b:+d})")
    else:
        print("코드별 변화 없음.")
    cat_diff = []
    for cat, r in cur["per_category_rate"].items():
        br = base["per_category_rate"].get(cat)
        if br is not None and abs(r - br) >= 0.5:
            cat_diff.append(f"  {cat}: {br}% → {r}%")
    if cat_diff:
        print("\n카테고리별 분류율 변화 (±0.5%p 이상):")
        print("\n".join(cat_diff))
    if regressed:
        print("\n❌ 분류율 회귀 — 룰 변경을 재검토하세요.")
        return 1
    print("\n✅ 분류율 회귀 없음.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(CORPUS):
        print(f"코퍼스 없음: {CORPUS}\n먼저 scripts/extract_questions.py를 실행하세요.")
        return 2

    cur = run_classification()
    print(f"분류 완료: {cur['classified']}/{cur['total']} = {cur['rate']}% "
          f"(미분류 {cur['unclassified_kinds']}종)")

    if args.update_baseline or not os.path.isfile(BASELINE):
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f"베이스라인 갱신: {BASELINE}")
        return 0

    base = json.load(open(BASELINE, encoding="utf-8"))
    return compare(base, cur)


if __name__ == "__main__":
    sys.exit(main())
