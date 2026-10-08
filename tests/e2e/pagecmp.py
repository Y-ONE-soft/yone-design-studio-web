"""원본 쪽 읽기 · 비교 — 편집기 재현의 기준 도구. 절차: docs/편집기_재현/절차.md

    python3 tests/e2e/pagecmp.py selftest <원본.pdf> <쪽>      비교 도구 검증 (같으면 100%, 1mm 밀면 잡아야 한다)
    python3 tests/e2e/pagecmp.py elements <원본.pdf> <쪽>      원본 요소표 (지면 좌표 mm — 재단 여백을 뺀 값)

좌표: 원본 PDF 는 재단 여백(bleed)째 216×303 이다. 지면 = trimbox 안쪽. 그래서 비율이 아니라 trimbox 원점을 뺀다.
"""
import json, sys

import pymupdf
from PIL import Image, ImageChops

PT = 25.4 / 72.0
DPI = 110


def _mm(v):
    return round(v * PT, 2)


def _hex(c):
    if c is None:
        return None
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x * 255))) for x in c[:3])


def page_image(pdf, pno, dpi=DPI):
    """지면(trimbox)만 그림으로."""
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    pix = p.get_pixmap(dpi=dpi, clip=p.trimbox)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ink_match(a, b, tol=48):
    """바탕을 뺀 '잉크' 화소만 센다 — 둘 중 하나라도 잉크인 자리 가운데 같은 비율(%)."""
    b = b.resize(a.size)
    bg = max(a.getcolors(1 << 24) or [(0, (255, 255, 255))])[1]
    flat = Image.new("RGB", a.size, bg)
    ink_a = ImageChops.difference(a, flat).convert("L").point(lambda v: 255 if v > 24 else 0)
    ink_b = ImageChops.difference(b, flat).convert("L").point(lambda v: 255 if v > 24 else 0)
    union = ImageChops.lighter(ink_a, ink_b)
    bad = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > tol else 0)
    bad = ImageChops.multiply(bad, union)
    n_union = sum(union.histogram()[1:]) or 1
    return 100 * (1 - sum(bad.histogram()[1:]) / n_union), bad


def save_views(a, b, bad, stem):
    b = b.resize(a.size)
    side = Image.new("RGB", (a.size[0] * 2 + 20, a.size[1]), "white")
    side.paste(a, (0, 0))
    side.paste(b, (a.size[0] + 20, 0))
    side.save(stem + "_side.png")
    Image.composite(Image.new("RGB", a.size, (230, 40, 40)), a.convert("L").convert("RGB"), bad).save(stem + "_diff.png")


def elements(pdf, pno):
    """원본 요소표 — 면(채움)·선·원/곡선·글·그림. 좌표는 지면 기준 mm."""
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for g in p.get_drawings():
        r = g["rect"]
        curved = any(it[0] == "c" for it in g["items"])
        kinds = {it[0] for it in g["items"]}
        kind = "ellipse" if curved and len(g["items"]) in (4, 5) and abs(r.width - r.height) < 0.6 else \
               "rect" if kinds <= {"re"} or (kinds <= {"l"} and len(g["items"]) == 4 and not curved) else \
               "line" if kinds == {"l"} and len(g["items"]) == 1 else "path"
        out.append({"k": kind, "x": _mm(r.x0 - ox), "y": _mm(r.y0 - oy), "w": _mm(r.width), "h": _mm(r.height),
                    "fill": _hex(g.get("fill")), "stroke": _hex(g.get("color")) if g.get("color") is not None else None,
                    "sw": _mm(g["width"]) if g.get("width") else None, "n": len(g["items"])})
    for b in p.get_text("dict")["blocks"]:
        if b["type"] == 1:
            r = pymupdf.Rect(b["bbox"])
            out.append({"k": "image", "x": _mm(r.x0 - ox), "y": _mm(r.y0 - oy), "w": _mm(r.width), "h": _mm(r.height)})
            continue
        for ln in b["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            x0 = min(s["bbox"][0] for s in spans); y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans); y1 = max(s["bbox"][3] for s in spans)
            out.append({"k": "text", "text": "".join(s["text"] for s in ln["spans"]).strip(),
                        "x": _mm(x0 - ox), "y": _mm(y0 - oy), "w": _mm(x1 - x0), "h": _mm(y1 - y0),
                        "size": round(spans[0]["size"], 1), "color": "#%06x" % spans[0]["color"],
                        "font": spans[0]["font"]})
    for im in p.get_image_info():
        r = pymupdf.Rect(im["bbox"])
        if not any(e["k"] == "image" and abs(e["x"] - _mm(r.x0 - ox)) < 0.1 for e in out):
            out.append({"k": "image", "x": _mm(r.x0 - ox), "y": _mm(r.y0 - oy), "w": _mm(r.width), "h": _mm(r.height)})
    return out


if __name__ == "__main__":
    cmd, pdf, pno = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if cmd == "elements":
        for e in elements(pdf, pno):
            print(json.dumps(e, ensure_ascii=False))
    elif cmd == "selftest":
        a = page_image(pdf, pno)
        same, _ = ink_match(a, a)
        px = round(DPI / 25.4)                                     # 1mm 화소
        shifted = Image.new("RGB", a.size, a.getpixel((a.size[0] - 1, a.size[1] - 1)))
        shifted.paste(a, (px, px))
        moved, _ = ink_match(a, shifted)
        print(f"같은 쪽: {same:.1f}%   1mm 민 쪽: {moved:.1f}%")
        ok = same > 99.9 and moved < 90
        print("비교 도구 검증", "통과" if ok else "실패 — 이 비교는 못 믿는다")
        sys.exit(0 if ok else 1)
