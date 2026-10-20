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
    # 묶음(투명 그룹) 불투명 — 인디자인은 개체 투명도를 바깥 묶음(/ca + Form Do)에 건다. 그 안 경로·글은 제 값이 1 로 나온다.
    # 묶음은 겹쳐 들어가니 바깥부터 곱한다. 글은 글 상자 가운데를 품은 가장 깊은 묶음의 값.
    stack, groups, draws = [], [], []
    for g in p.get_drawings(extended=True):
        lv = g.get("level", 0)
        while stack and stack[-1][0] >= lv:
            stack.pop()
        cum = stack[-1][1] if stack else 1.0
        if g.get("type") == "group":
            cum *= float(g.get("opacity") or 1.0)
            groups.append((pymupdf.Rect(g["rect"]), cum, len(stack)))
            stack.append((lv, cum))
        elif g.get("type") == "clip":
            stack.append((lv, cum))
        elif g.get("items"):
            draws.append((g, cum))

    def group_alpha(bb):
        c = pymupdf.Point((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        inn = [(dp, cm) for r, cm, dp in groups if r.x0 - 0.5 <= c.x <= r.x1 + 0.5 and r.y0 - 0.5 <= c.y <= r.y1 + 0.5]
        return max(inn)[1] if inn else 1.0

    for g, cum in draws:
        r = g["rect"]
        curved = any(it[0] == "c" for it in g["items"])
        kinds = {it[0] for it in g["items"]}
        kind = "ellipse" if curved and len(g["items"]) in (4, 5) and abs(r.width - r.height) < 0.6 else \
               "rect" if kinds <= {"re"} or (kinds <= {"l"} and len(g["items"]) == 4 and not curved) else \
               "line" if kinds == {"l"} and len(g["items"]) == 1 else "path"
        out.append({"k": kind, "x": _mm(r.x0 - ox), "y": _mm(r.y0 - oy), "w": _mm(r.width), "h": _mm(r.height),
                    "fill": _hex(g.get("fill")), "stroke": _hex(g.get("color")) if g.get("color") is not None else None,
                    "sw": _mm(g["width"]) if g.get("width") else None, "n": len(g["items"]),
                    **({"opacity": round(cum * min((o for o in (g.get("fill_opacity"), g.get("stroke_opacity")) if o is not None), default=1) * 100)}
                       if cum * min((o for o in (g.get("fill_opacity"), g.get("stroke_opacity")) if o is not None), default=1) < 0.999 else {})})
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
            al = spans[0].get("alpha", 255) / 255 * group_alpha((x0, y0, x1, y1))
            out.append({"k": "text", "text": txt,
                        "x": _mm(x0 - ox), "y": _mm(y0 - oy), "w": _mm(x1 - x0), "h": _mm(y1 - y0),
                        "size": round(spans[0]["size"], 1), "color": "#%06x" % spans[0]["color"],
                        **({"opacity": round(al * 100)} if al < 0.999 else {}),
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
    try:                                                   # 후보 = 시스템 서체(편집기에서 고를 수 있는 것) — 없으면 예전 후보
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from core.units.fonts import system_fonts
        paths = {f["file"]: f["path"] for f in system_fonts() if not f["italic"]}
    except Exception:
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
    clip = p.trimbox if trim else None
    if trim and p.trimbox != p.rect:
        # 재단선 왼쪽 위를 화소 격자 0 에 — clip 으로 자르면 쪽 전체 격자 그대로라 재단 여백 8.504pt 가 300dpi 에서 0.433화소 밀려
        # 0.17mm 막대 같은 가는 것의 잉크가 0.88~1.32 로 흔들리고 띠 가장자리 화소가 한 줄 더 잡혔다(2026-10-20 상일보카 꼬리 「|」 · 위 띠).
        # 결과 PDF(편집기 인쇄)는 재단선이 0 이라 같은 격자가 된다
        try:
            p.set_cropbox(p.trimbox)
            clip = None
        except Exception:
            pass
    pix = p.get_pixmap(dpi=dpi, clip=clip)
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
        far = np.abs(vals - c).max(axis=1) > 60                         # 글자색에 가까운 색은 바탕이 아니다 — 흰 글 둘레에 흰 종이가 걸려도(꼬리표 밖) 꼬리표 색을 바탕으로
        bg = vals[far][cnt[far].argmax()] if far.any() else vals[cnt.argmax()]
        d = c - bg
        if not (d * d).sum():
            return np.zeros((1, 1))
        t = ((arr[y0:y1, x0:x1].astype(float) - bg) * d).sum(axis=2) / (d * d).sum()
        near = np.abs(arr[y0:y1, x0:x1].astype(int) - c).max(axis=2) <= max(tol, 90)   # 다른 색 글(옆 요소)은 빼고
        t = t * near
        # 검정 계열 글은 그림마다 실제 글자색(꽉 칠한 화소의 진하기)으로 맞춘다 — 원본(인디자인) 검정은 CMYK K100 이라 화면 변환에서
        # #231f20 보다 옅어(회색 41 대 32) 굵기·모양이 같아도 잉크가 4% 적게 잡혀 ±12% 경계에서 떨어졌다(14c 「시오.」 덮은 면적 2.71 대 2.73mm²).
        # 흰 글·색 글은 지정 색 그대로(맞추면 01·08 흰 제목이 0.85 로 떨어진다).
        solid = t[t > 0.6]
        if c.max() <= 80 and solid.size >= 8:
            t = t / max(float(np.percentile(solid, 90)), 0.5)
        return np.clip(t, 0, 1)
    ca, cb = cover(ra, a), cover(ma, b)
    if not ca.size or not cb.size or ca.sum() < 1:
        return None, None
    ink = float(cb.sum()) / float(ca.sum())                     # 잉크 양은 각자 상자에서 그대로 — 늘려 맞추면 1mm 남짓 글자는 1화소 차이에 ±20% 흔들렸다
    H, W = max(ca.shape[0], cb.shape[0]), max(ca.shape[1], cb.shape[1])   # 겹침은 늘리지 않고 왼쪽 위를 맞춰 같은 크기로 채운다
    ca = np.pad(ca, ((0, H - ca.shape[0]), (0, W - ca.shape[1])))
    cb = np.pad(cb, ((0, H - cb.shape[0]), (0, W - cb.shape[1])))
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


def shown_color(arr, e, dpi=300):
    """원본 그림의 요소 상자 안에서 바탕(둘레의 가장 흔한 색)과 가장 다른 화소 색 = 글이 실제로 보이는 색"""
    import numpy as np
    k = dpi / 25.4
    x0, y0 = max(0, int(e["x"] * k) - 3), max(0, int(e["y"] * k) - 3)
    win = arr[y0:int((e["y"] + e["h"]) * k) + 4, x0:int((e["x"] + e["w"]) * k) + 4].astype(int)
    rim = np.concatenate([win[0], win[-1], win[:, 0], win[:, -1]])
    vals, cnt = np.unique(rim, axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    flat = win.reshape(-1, 3)
    c = flat[np.abs(flat - bg).sum(1).argmax()]
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def measure(ref_pdf, ref_page, my_pdf, elems, dpi=300):
    """요소마다 원본과 결과의 같은 색 상자를 재서 차이(mm). elems: [{id, x, y, w, h, color, pad?}]"""
    ra, ma = page_array(ref_pdf, ref_page, dpi), page_array(my_pdf, 1, dpi)
    if ma.shape != ra.shape:                                    # 크롬 인쇄 쪽은 A4 보다 0.11mm 좁다(594.96pt, 크롬 반올림) — 늘리지 말고 같은 배율 그대로
        import numpy as np                                      # 왼쪽 위에 맞춰 모자란 곳은 끝 화소로 채우고 남는 곳은 자른다 (늘리면 가는 선이 흐려지고 오른쪽 끝이 밀린다)
        H, W = ra.shape[:2]
        ma = ma[:H, :W]
        ma = np.pad(ma, ((0, H - ma.shape[0]), (0, W - ma.shape[1]), (0, 0)), mode="edge")
    out = []
    for e in elems:
        pad = e.get("pad", 1.5)
        col, tol = e.get("see", e["color"]), e.get("ctol", 40)          # see = 투명도까지 섞여 보이는 색
        if col == "auto":                                               # 원본 그림에서 실제로 보이는 색 — 투명을 CMYK 로 섞은 원본(인디자인)은 계산과 다르다
            col = shown_color(ra, e, dpi)
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
