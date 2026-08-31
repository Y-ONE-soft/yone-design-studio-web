#!/usr/bin/env python3
"""파이널 Vivliostyle ↔ 완성본 **지면 기하** 대조.

글자가 같아도 자리가 다르면 다른 책이다. 섹션마다 고정점(헤더 기준선, 본문
첫 줄 기준선, 행간, 단 좌우, 상자 좌우)을 재서 나란히 놓는다.

  python3 scripts/final_viv_geom.py <완성본.pdf> <viv.pdf> --vol 1
"""
import argparse
import sys

import fitz

MM = 25.4 / 72
SEC = {1: [("문장 배열", "arrange"), ("문장 삽입", "insert"),
           ("중요 어휘", "vocab")],
       2: [("어법 수정", "grammar"), ("서술형 영작", "writing")]}


def find_page(doc, needle, lo=1):
    for i in range(lo, doc.page_count):
        if needle in doc[i].get_text():
            return i
    return None


def col_lines(page, xmax=60.0, ylo=25.0, yhi=200.0):
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            s = l["spans"][0]
            y = s["origin"][1] * MM
            if y < ylo or y > yhi or l["bbox"][0] * MM > xmax:
                continue
            out.append((round(y, 2), round(s["size"], 2),
                        round(l["bbox"][0] * MM, 2),
                        round(l["bbox"][2] * MM, 2),
                        "".join(x["text"] for x in l["spans"])[:26]))
    out.sort()
    return out


def boxes(page, xmax=120.0):
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        if not d.get("fill") or r.x0 * MM > xmax or r.height * MM < 3:
            continue
        out.append((round(r.y0 * MM, 2), round(r.y1 * MM, 2),
                    round(r.x0 * MM, 2), round(r.x1 * MM, 2)))
    return sorted(out)


def report(tag, doc, page):
    ls = col_lines(doc[page])
    print(f"   {tag} p{page+1}")
    for y, sz, x0, x1, t in ls[:4]:
        print(f"      base {y:7.2f}  x {x0:6.2f}→{x1:6.2f}  {sz:5.2f}pt  {t!r}")
    if len(ls) > 2:
        print(f"      행간 {ls[2][0]-ls[1][0]:.2f}mm")
    bx = boxes(doc[page])
    if bx:
        print(f"      상자 {bx[:3]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--vol", type=int, default=1)
    a = ap.parse_args()
    A, B = fitz.open(a.ref), fitz.open(a.new)
    for needle, kind in SEC[a.vol]:
        pa, pb = find_page(A, needle), find_page(B, needle)
        print(f"== {kind}")
        if pa is None or pb is None:
            print("   면을 못 찾았다")
            continue
        report("완성본", A, pa + 1 if kind != "vocab" else pa)
        report("viv   ", B, pb + 1 if kind != "vocab" else pb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
