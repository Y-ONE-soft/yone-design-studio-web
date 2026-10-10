"""원본 PDF 한 면의 일부(로고 등)를 그림 파일(SVG)로 꺼낸다 — 디자이너가 원본에서 로고 파일을 내보내 편집기에 올리는 것과 같다.

    python3 tests/e2e/pdfsvg.py <PDF> <쪽> <x> <y> <w> <h> <나갈 파일.svg>      (자리는 재단선 기준 mm)

그 자리 안의 칠한 도형(면·선·곡선)만 옮긴다(색 그대로). 글은 옮기지 않는다.
"""
import sys
import pymupdf

PT = 25.4 / 72


def export(pdf, pno, x, y, w, h, out):
    p = pymupdf.open(pdf)[pno - 1]
    t = p.trimbox
    clip = pymupdf.Rect(t.x0 + x / PT, t.y0 + y / PT, t.x0 + (x + w) / PT, t.y0 + (y + h) / PT)
    paths = []
    for d in p.get_drawings():
        r = d["rect"]
        if not (clip.contains(r) or clip.intersects(r)) or r.width > clip.width * 1.5:
            continue
        seg, cur = [], None
        for it in d["items"]:
            k = it[0]
            pts = it[1:]
            if k == "re":
                rr = pts[0]
                seg.append(f"M{rr.x0 - clip.x0:.3f} {rr.y0 - clip.y0:.3f}H{rr.x1 - clip.x0:.3f}V{rr.y1 - clip.y0:.3f}H{rr.x0 - clip.x0:.3f}Z")
                cur = None
                continue
            if k == "qu":
                q = pts[0]
                seg.append("M" + " L".join(f"{pp.x - clip.x0:.3f} {pp.y - clip.y0:.3f}" for pp in (q.ul, q.ur, q.lr, q.ll)) + "Z")
                cur = None
                continue
            a = pts[0]
            if cur is None or abs(cur.x - a.x) > 0.01 or abs(cur.y - a.y) > 0.01:
                seg.append(f"M{a.x - clip.x0:.3f} {a.y - clip.y0:.3f}")
            if k == "l":
                b = pts[1]
                seg.append(f"L{b.x - clip.x0:.3f} {b.y - clip.y0:.3f}")
                cur = b
            elif k == "c":
                c1, c2, b = pts[1], pts[2], pts[3]
                seg.append(f"C{c1.x - clip.x0:.3f} {c1.y - clip.y0:.3f} {c2.x - clip.x0:.3f} {c2.y - clip.y0:.3f} {b.x - clip.x0:.3f} {b.y - clip.y0:.3f}")
                cur = b
        if d.get("closePath"):
            seg.append("Z")
        hx = lambda v: "#" + "".join("%02x" % round(c * 255) for c in v[:3]) if v else "none"
        fill = hx(d.get("fill"))
        stroke = hx(d.get("color")) if d.get("color") and d.get("width") else "none"
        sw = f' stroke-width="{d["width"]:.3f}"' if stroke != "none" else ""
        rule = ' fill-rule="evenodd"' if d.get("even_odd") else ""
        paths.append(f'<path d="{"".join(seg)}" fill="{fill}" stroke="{stroke}"{sw}{rule}/>')
    W, H = clip.width, clip.height
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.3f} {H:.3f}" width="{W * PT:.3f}mm" height="{H * PT:.3f}mm">'
           + "".join(paths) + "</svg>")
    open(out, "w", encoding="utf-8").write(svg)
    return len(paths)


if __name__ == "__main__":
    a = sys.argv
    print(export(a[1], int(a[2]), float(a[3]), float(a[4]), float(a[5]), float(a[6]), a[7]), "도형")
