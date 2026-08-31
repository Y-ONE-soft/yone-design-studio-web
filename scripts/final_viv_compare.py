#!/usr/bin/env python3
"""파이널 Vivliostyle 산출 ↔ 인디자인 완성본 대조.

같은 원고를 두 엔진으로 조판했으니 **면·글줄이 같아야 한다.** 다르면 어디서
갈렸는지 짚어 준다.

  python3 scripts/final_viv_compare.py <완성본.pdf> <viv.pdf> [--pages]
"""
import argparse
import collections
import re
import sys

import fitz

MM = 25.4 / 72


def page_headers(doc, size=12.0, tol=0.4):
    out = []
    for p in doc:
        hs = []
        for b in p.get_text("dict")["blocks"]:
            if b["type"] != 0 or not b["lines"]:
                continue
            s = b["lines"][0]["spans"][0]
            if abs(s["size"] - size) < tol:
                hs.append((round(b["bbox"][0] * MM, 1),
                           round(b["bbox"][1] * MM, 1), s["text"].strip()))
        out.append([h[2] for h in sorted(hs, key=lambda t: (t[0], t[1]))])
    return out


def lines_of(doc):
    out = []
    for p in doc:
        ls = []
        for b in p.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t:
                    ls.append((round(l["bbox"][0] * MM, 2),
                               round(l["bbox"][1] * MM, 2),
                               round(l["bbox"][2] * MM, 2), t))
        out.append(ls)
    return out


def norm(t):
    return re.sub(r"\s+", "", t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--pages", action="store_true")
    a = ap.parse_args()
    A, B = fitz.open(a.ref), fitz.open(a.new)
    print(f"쪽수  완성본 {A.page_count}  viv {B.page_count}")

    ha, hb = page_headers(A), page_headers(B)
    if a.pages:
        for i in range(max(len(ha), len(hb))):
            x = ha[i] if i < len(ha) else []
            y = hb[i] if i < len(hb) else []
            mark = "   " if x == y else " ! "
            print(f"{i+1:>3}{mark}{x}\n    {'' if x==y else y}")
    same = sum(1 for i in range(min(len(ha), len(hb))) if ha[i] == hb[i])
    print(f"면별 지문 배치 일치 {same}/{min(len(ha), len(hb))}")

    # 글줄 — 완성본에 있는 줄이 viv 에도 같은 모양으로 있는가
    la = [t for pg in lines_of(A) for *_x, t in pg]
    lb = [t for pg in lines_of(B) for *_x, t in pg]
    sa, sb = collections.Counter(map(norm, la)), collections.Counter(map(norm, lb))
    only_a = [t for t in la if sa[norm(t)] > sb.get(norm(t), 0)]
    only_b = [t for t in lb if sb[norm(t)] > sa.get(norm(t), 0)]
    print(f"글줄  완성본 {len(la)}  viv {len(lb)}  "
          f"완성본에만 {len(only_a)}  viv에만 {len(only_b)}")
    for t in only_a[:12]:
        print("   -", t[:88])
    for t in only_b[:12]:
        print("   +", t[:88])

    # 글자 총량 — 내용 유실 감시(줄바꿈이 달라도 글자는 같아야 한다)
    ta = norm("".join(la))
    tb = norm("".join(lb))
    print(f"글자수 완성본 {len(ta):,}  viv {len(tb):,}  차 {len(tb)-len(ta):+,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
