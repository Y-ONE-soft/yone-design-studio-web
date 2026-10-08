"""원본 쪽 읽기 · 비교 — 편집기 재현의 기준 도구. 절차: docs/편집기_재현/절차.md

    python3 tests/e2e/pagecmp.py selftest <원본.pdf> <쪽>      비교 도구 검증 (같으면 100%, 1mm 밀면 잡아야 한다)
    python3 tests/e2e/pagecmp.py elements <원본.pdf> <쪽>      원본 요소표 (지면 좌표 mm — 재단 여백을 뺀 값)

좌표: 원본 PDF 는 재단 여백(bleed)째 216×303 이다. 지면 = trimbox 안쪽. 그래서 비율이 아니라 trimbox 원점을 뺀다.
"""
import json, os, re, sys

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


def _unspace(t):
    """자간을 넓게 준 글은 PDF 에서 'S T E P' 로 읽힌다 — 한 조각 안의 글자 사이 빈칸을 걷는다."""
    t = t.strip()
    return re.sub(r"(?<=\S) (?=\S)", "", t) if re.fullmatch(r"(\S )+\S", t) else t


def _glyph_text(page, ln):
    """줄의 글자를 자리로 다시 읽는다 — 글자 사이 틈이 보통 틈보다 글자 크기 1/4 이상 크면 띄어쓰기.
    (자간을 넓게 준 글·글자마다 조각난 글을 PDF 가 'S T E P' 처럼 빈칸을 넣어 읽기 때문)"""
    gl = []
    for b in page.get_text("rawdict", clip=pymupdf.Rect(ln["bbox"]) + (-1, -1, 1, 1))["blocks"]:
        for l2 in b.get("lines", []):
            for sp in l2["spans"]:
                for ch in sp["chars"]:
                    if ch["c"].strip():
                        gl.append((ch["bbox"][0], ch["bbox"][2], ch["c"], sp["size"]))
    gl.sort()
    if not gl:
        return ""
    gaps = sorted(gl[i][0] - gl[i - 1][1] for i in range(1, len(gl)))
    med = gaps[len(gaps) // 2] if gaps else 0
    out = gl[0][2]
    for i in range(1, len(gl)):
        out += (" " if gl[i][0] - gl[i - 1][1] > med + gl[i][3] * 0.25 else "") + gl[i][2]
    return out


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
                    "sw": _mm(g["width"]) if g.get("width") else None, "n": len(g["items"]),
                    **({"opacity": round(min(o for o in (g.get("fill_opacity"), g.get("stroke_opacity")) if o is not None) * 100)}
                       if min((o for o in (g.get("fill_opacity"), g.get("stroke_opacity")) if o is not None), default=1) < 0.999 else {})})
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
            txt = _glyph_text(p, ln)
            out.append({"k": "text", "text": txt,
                        "x": _mm(x0 - ox), "y": _mm(y0 - oy), "w": _mm(x1 - x0), "h": _mm(y1 - y0),
                        "size": round(spans[0]["size"], 1), "color": "#%06x" % spans[0]["color"],
                        **({"opacity": round(spans[0]["alpha"] / 2.55)} if spans[0].get("alpha", 255) < 255 else {}),
                        "font": spans[0]["font"]})
    for im in p.get_image_info():
        r = pymupdf.Rect(im["bbox"])
        if not any(e["k"] == "image" and abs(e["x"] - _mm(r.x0 - ox)) < 0.1 for e in out):
            out.append({"k": "image", "x": _mm(r.x0 - ox), "y": _mm(r.y0 - oy), "w": _mm(r.width), "h": _mm(r.height)})
    return out


FONT_DIRS = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts"]
FONT_CANDIDATES = [f"Montserrat-{w}.otf" for w in ("Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black")] + \
    [f"GmarketSans{w}.otf" for w in ("Light", "Medium", "Bold")] + \
    [f"NotoSansCJKkr-{w}.otf" for w in ("Light", "Regular", "Medium", "Bold", "Black")] + \
    [f"EliceDXNeolliOTF-{w}.otf" for w in ("Light", "Medium", "Bold")] + ["EliceDigitalBaeumOTF_Regular.otf", "EliceDigitalBaeumOTF_Bold.otf"]


def _ink(img, bg=None):
    """잉크 가면(글자 화소) + 그 상자."""
    g = img.convert("L")
    bg = g.getpixel((0, 0)) if bg is None else bg
    m = g.point(lambda v: 255 if abs(v - bg) > 60 else 0)
    return m, m.getbbox()


def fonts(pdf, pno, dpi=300, top=3):
    """원본 글마다 어느 서체·자간인지 — 후보 서체로 같은 크기 글을 그려 원본 글자 모양과 겹쳐 본다.
    자간은 잉크 폭이 원본과 같아지게 푼다. 결과 tracking 은 편집기 단위(1/1000 em)."""
    from PIL import ImageDraw, ImageFont
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    paths = {f: next((os.path.join(dd, f) for dd in FONT_DIRS if os.path.exists(os.path.join(dd, f))), None) for f in FONT_CANDIDATES}
    extra = os.environ.get("FONTS_TRY")                    # 더 맞대 볼 서체 폴더 (받은 후보) — 그 안의 .otf/.ttf 전부
    if extra:
        for n in sorted(os.listdir(extra)):
            if n.lower().endswith((".otf", ".ttf")):
                paths[n] = os.path.join(extra, n)
    res = []
    for e in elements(pdf, pno):
        if e["k"] != "text":
            continue
        r = pymupdf.Rect(e["x"] / PT + ox, e["y"] / PT + oy, (e["x"] + e["w"]) / PT + ox, (e["y"] + e["h"]) / PT + oy) + (-3, -3, 3, 3)
        pix = p.get_pixmap(dpi=dpi, clip=r)
        orig = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        om, ob = _ink(orig)
        if not ob:
            continue
        om = om.crop(ob)
        px = e["size"] * dpi / 72.0
        txt = e["text"]
        best = []
        for name, path in paths.items():
            if not path:
                continue
            f = ImageFont.truetype(path, round(px))
            def draw(t):
                im = Image.new("L", (int(om.size[0] * 1.6 + px * 2), int(px * 2.2)), 0)
                dr = ImageDraw.Draw(im)
                x = px * 0.3
                for ch in txt:
                    dr.text((x, px * 0.4), ch, font=f, fill=255)
                    x += f.getlength(ch) + t
                return im.crop(im.getbbox()) if im.getbbox() else None
            m0 = draw(0)
            if m0 is None:
                continue
            t = (om.size[0] - m0.size[0]) / max(1, len(txt) - 1)
            m = draw(t)
            W, H = max(m.size[0], om.size[0]), max(m.size[1], om.size[1])
            a = Image.new("L", (W, H), 0); a.paste(om, (0, 0))
            b = Image.new("L", (W, H), 0); b.paste(m, (0, 0))
            inter = sum(ImageChops.multiply(a, b).point(lambda v: 1 if v else 0).histogram()[1:2])
            uni = sum(ImageChops.lighter(a, b).point(lambda v: 1 if v else 0).histogram()[1:2]) or 1
            best.append((inter / uni, name, round(t / px * 1000), m.size[1] - om.size[1]))
        best.sort(reverse=True)
        res.append({"text": txt, "size": e["size"], "x": e["x"], "y": e["y"],
                    "best": [{"font": n, "match": round(sc * 100, 1), "tracking": tr, "dh_px": dh} for sc, n, tr, dh in best[:top]]})
    return res


def page_array(pdf, pno, dpi=300, trim=True):
    import numpy as np
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    pix = p.get_pixmap(dpi=dpi, clip=p.trimbox if trim else None)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]


def color_box(arr, color, x, y, w, h, pad=1.5, tol=40, dpi=300):
    """창(요소 자리 ± pad mm) 안에서 그 색 화소들의 상자(mm). 없으면 None."""
    import numpy as np
    k = dpi / 25.4
    H, W = arr.shape[:2]
    x0, y0 = max(0, int((x - pad) * k)), max(0, int((y - pad) * k))
    x1, y1 = min(W, int((x + w + pad) * k) + 1), min(H, int((y + h + pad) * k) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    c = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)])
    m = (np.abs(arr[y0:y1, x0:x1].astype(int) - c).max(axis=2) <= tol)
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    return [round(float(x0 + xs.min()) / k, 2), round(float(y0 + ys.min()) / k, 2),
            round(float(xs.max() - xs.min() + 1) / k, 2), round(float(ys.max() - ys.min() + 1) / k, 2)]


def shape_match(ra, ma, color, tol, a, b, dpi=300):
    """글자 모양 비교 — 원본 상자 a 와 결과 상자 b 안의 그 색 잉크를 같은 크기로 맞대고
    (잉크 양 비율 = 굵기, 겹침 IoU = 글자 모양·서체·대체 글자). 위치·크기 측정이 못 잡는 차이를 잡는다."""
    import numpy as np
    from PIL import Image
    k = dpi / 25.4
    c = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)])

    def cover(arr, bx):
        """화소마다 바탕색 → 글자색 사이 어디쯤인가(0~1) — 가장자리 흐린 화소도 그만큼만 센다. 바탕 = 상자 둘레의 가장 흔한 색"""
        x0, y0 = int(bx[0] * k), int(bx[1] * k)
        x1, y1 = int((bx[0] + bx[2]) * k) + 1, int((bx[1] + bx[3]) * k) + 1
        H, W = arr.shape[:2]
        win = arr[max(0, y0 - 3):min(H, y1 + 3), max(0, x0 - 3):min(W, x1 + 3)].astype(float)
        rim = np.concatenate([win[0], win[-1], win[:, 0], win[:, -1]])
        vals, cnt = np.unique(rim.round(), axis=0, return_counts=True)
        bg = vals[cnt.argmax()]
        d = c - bg
        if not (d * d).sum():
            return np.zeros((1, 1))
        t = ((arr[y0:y1, x0:x1].astype(float) - bg) * d).sum(axis=2) / (d * d).sum()
        near = np.abs(arr[y0:y1, x0:x1].astype(int) - c).max(axis=2) <= max(tol, 90)   # 다른 색 글(옆 요소)은 빼고
        return np.clip(t, 0, 1) * near
    ca, cb = cover(ra, a), cover(ma, b)
    if not ca.size or not cb.size or ca.sum() < 1:
        return None, None
    cb = np.asarray(Image.fromarray((cb * 255).astype(np.uint8)).resize((ca.shape[1], ca.shape[0]), Image.BILINEAR)) / 255.0
    ink = float(cb.sum()) / float(ca.sum())
    ma_, mb_ = ca > 0.5, cb > 0.5

    def grow(m, r=2):                                          # 2화소(0.17mm) 넓힌다 — 0.1mm 어긋남에 겹침이 무너지지 않게
        g = m.copy()
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                g[max(0, dy):m.shape[0] + min(0, dy), max(0, dx):m.shape[1] + min(0, dx)] |= \
                    m[max(0, -dy):m.shape[0] + min(0, -dy), max(0, -dx):m.shape[1] + min(0, -dx)]
        return g
    hit_b = float((mb_ & grow(ma_)).sum()) / max(1.0, float(mb_.sum()))     # 내 잉크가 원본 자리에 있는 비율
    hit_a = float((ma_ & grow(mb_)).sum()) / max(1.0, float(ma_.sum()))     # 원본 잉크가 내 자리에 있는 비율
    return round(ink, 2), round(min(hit_a, hit_b), 2)


SHAPE_INK = 0.12        # 잉크 양이 원본과 이만큼(비율) 넘게 다르면 굵기가 다르다
SHAPE_IOU = 0.90        # 겹침(0.17mm 너그럽게)이 이보다 낮으면 글자 모양이 다르다


def measure(ref_pdf, ref_page, my_pdf, elems, dpi=300):
    """요소마다 원본과 결과의 같은 색 상자를 재서 차이(mm). elems: [{id, x, y, w, h, color, pad?}]"""
    ra, ma = page_array(ref_pdf, ref_page, dpi), page_array(my_pdf, 1, dpi)
    if ma.shape != ra.shape:                                    # 결과 PDF 가 A4 그대로가 아니면 맞춘다
        from PIL import Image
        import numpy as np
        ma = np.asarray(Image.fromarray(ma).resize((ra.shape[1], ra.shape[0])))
    out = []
    for e in elems:
        pad = e.get("pad", 1.5)
        col, tol = e.get("see", e["color"]), e.get("ctol", 40)          # see = 투명도까지 섞여 보이는 색
        a = color_box(ra, col, e["x"], e["y"], e["w"], e["h"], pad, tol, dpi=dpi)
        b = color_box(ma, col, e["x"], e["y"], e["w"], e["h"], max(pad, e.get("search", pad)), tol, dpi=dpi)
        r = {"id": e["id"], "ref": a, "my": b}
        if a and b:
            r.update(dx=round(b[0] - a[0], 2), dy=round(b[1] - a[1], 2), dw=round(b[2] - a[2], 2), dh=round(b[3] - a[3], 2))
            r["ok"] = bool(max(abs(r["dx"]), abs(r["dy"]), abs(r["dw"]), abs(r["dh"])) <= e.get("tol", 0.3))
            if "text" in e:                                            # 글은 모양(굵기·서체)까지
                r["ink"], r["iou"] = shape_match(ra, ma, col, tol, a, b, dpi)
                if r["ink"] is not None:
                    r["shape_ok"] = bool(abs(r["ink"] - 1) <= SHAPE_INK and r["iou"] >= e.get("shape_iou", SHAPE_IOU))
                    r["ok"] = r["ok"] and r["shape_ok"]
        else:
            r["ok"] = False
        out.append(r)
    return out


if __name__ == "__main__":
    cmd, pdf, pno = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if cmd == "inkcolors":                                   # 글이 실제로 보이는 색 — 투명도가 있으면 지정 색과 다르다
        a = page_array(pdf, pno)
        k = 300 / 25.4
        for e in elements(pdf, pno):
            if e["k"] != "text":
                continue
            w = a[int(e["y"] * k):int((e["y"] + e["h"]) * k), int(e["x"] * k):int((e["x"] + e["w"]) * k)].reshape(-1, 3).astype(int)
            far = w[abs(w - w[0]).sum(1).argmax()]
            print(f"{e['text'][:16]:18s} 지정 {e['color']}  보이는 #{far[0]:02x}{far[1]:02x}{far[2]:02x}")
    elif cmd == "fonts":
        for r in fonts(pdf, pno):
            b = r["best"]
            print(f"{r['text'][:22]:24s} {r['size']:>5}pt  " + "  ".join(f"{x['font'].rsplit('.', 1)[0]} {x['match']}% 자간{x['tracking']}" for x in b))
    elif cmd == "elements":
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
