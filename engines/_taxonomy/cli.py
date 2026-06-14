"""
engines/_taxonomy CLI — 단일 원고/발문 분류 도구.

사용:
    # 단일 발문
    python3 -m engines._taxonomy.cli classify "다음 글의 제목으로 가장 적절한 것은?"

    # 원고 한 파일
    python3 -m engines._taxonomy.cli file /path/to/manuscript.hwpx

    # JSON 출력
    python3 -m engines._taxonomy.cli file /path/to/manuscript.hwpx --json
"""
import argparse
import json
import sys

from .classify import classify
from .extract import extract_and_classify


def cmd_classify(args):
    code, label, kind = classify(args.question)
    if code:
        if args.json:
            print(json.dumps({"q": args.question, "code": code, "label": label, "kind": kind}, ensure_ascii=False))
        else:
            print(f"{code}\t{label}\t{kind}")
    else:
        if args.json:
            print(json.dumps({"q": args.question, "code": None}, ensure_ascii=False))
        else:
            print("(미분류)")
            sys.exit(2)


def cmd_file(args):
    results = extract_and_classify(args.path)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    n_total = len(results)
    n_classified = sum(1 for r in results if r["code"])
    print(f"파일: {args.path}")
    print(f"발문 수: {n_total}, 분류 성공: {n_classified} ({n_classified/max(n_total,1)*100:.1f}%)")
    print("---")
    for r in results:
        code = r["code"] or "(미분류)"
        print(f"L{r['line_idx']:>4}  {code:30} {r['q'][:80]}")


def main():
    ap = argparse.ArgumentParser(prog="engines._taxonomy.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("classify", help="발문 1개 분류")
    p1.add_argument("question", help="발문 문자열")
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(func=cmd_classify)

    p2 = sub.add_parser("file", help="원고 한 파일 분류")
    p2.add_argument("path", help="hwp/hwpx/docx 경로")
    p2.add_argument("--json", action="store_true")
    p2.set_defaults(func=cmd_file)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
