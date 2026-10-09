"""기준 쪽의 면·선·글을 A4 좌표(mm)로 뽑는다. 대본 쓰기 전에 본다.

사용: python3 tests/e2e/ref_dump.py <기준쪽> [fill|text|all]
"""
import os, sys
import pymupdf

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(REPO, "catalog", "workbook", "designs", "d1", "reference.pdf")
PT = 25.4 / 72.0
K = 297 / 303.0                                    # 기준 303mm → A4 297mm


def mm(v):
    return round(v * PT, 1)


def ymm(v):
    return round(v * PT * K, 1)


def hexc(c):
    if c is None:
        return "-"
    if isinstance(c, (int, float)):
        c = pymupdf.sRGB_to_pdf(int(c)) if c > 1 else (c, c, c)
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x * 255))) for x in c)


pno = int(sys.argv[1])
what = sys.argv[2] if len(sys.argv) > 2 else "all"
page = pymupdf.open(REF)[pno - 1]

if what in ("fill", "all"):
    print("== 면·선 (x y w h 채움 테두리) ==")
    rows = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width < 0.3 or r.height < 0.3:
            continue
        rows.append((mm(r.x0), ymm(r.y0), mm(r.width), round(r.height * PT * K, 1),
                     hexc(d.get("fill")), hexc(d.get("color")),
                     round((d.get("width") or 0) * PT, 2), d["items"][0][0] if d["items"] else "?"))
    rows.sort(key=lambda t: (t[1], t[0]))
    for t in rows:
        print(f"  x{t[0]:>6} y{t[1]:>6} w{t[2]:>6} h{t[3]:>6} 채움 {t[4]} 테두리 {t[5]} 굵기 {t[6]} {t[7]}")

if what in ("text", "all"):
    print("== 글 (x y 폭 크기 색 서체) ==")
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if not sp["text"].strip():
                    continue
                print(f"  x{mm(sp['bbox'][0]):>6} y{ymm(sp['bbox'][1]):>6} w{mm(sp['bbox'][2]-sp['bbox'][0]):>6}"
                      f" {round(sp['size']*PT/25.4*72,1):>5}pt {hexc(sp['color'])} {sp['font'][:22]:22} {sp['text'][:40]!r}")
