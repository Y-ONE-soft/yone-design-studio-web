"""헤드리스 책 목업 엔진 — A/B 라이트맵 방식 (Photoshop 불필요).
흰 표지 렌더(A)·검은 표지 렌더(B)를 한 번 베이크 → out = B + cover*(A-B).

바인딩: 무선/스프링/중철(단면) · 중철펼침(2페이지) · 낱장(종이 1장)

표지 맞춤(fit): 1.0=프레임 꽉 채움(가장자리까지, 상단 위주로 살짝 크롭).
  <1=축소(단색 여백, 줄무늬 없음) · >1=확대(중앙 크롭).
비율이 안 맞는 표지(A4 vs US레터)도 여백은 표지 테두리 중앙값 단색으로 채워 깔끔.
"""
import os
import numpy as np
import cv2
from PIL import Image, ImageFilter, ImageDraw

BAKE = os.path.join(os.path.dirname(__file__), "bake")

TEMPLATES = {"무선": "wireless", "스프링": "spring", "중철": "saddle04"}
SPREAD = {"중철펼침": "saddle02"}
FLAT = {"낱장"}
ALL_BINDINGS = list(TEMPLATES) + list(SPREAD) + list(FLAT)

_cache = {}

def _load(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)

def _get_ab(tpl):
    if tpl not in _cache:
        _cache[tpl] = (_load(os.path.join(BAKE, f"{tpl}_A.png")),
                       _load(os.path.join(BAKE, f"{tpl}_B.png")))
    return _cache[tpl]

def _order_quad(pts):
    pts = pts.reshape(-1, 2).astype(np.float32)
    s = pts.sum(1); d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)

def _quad_from_contour(c):
    peri = cv2.arcLength(c, True)
    for k in (0.02, 0.03, 0.05):
        ap = cv2.approxPolyDP(c, k * peri, True)
        if len(ap) == 4:
            return _order_quad(ap)
    return _order_quad(cv2.boxPoints(cv2.minAreaRect(c)))

def _detect_quads(A, B, n=1):
    diff = np.abs(A[..., :3] - B[..., :3]).mean(2)
    mask = (diff > 40).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:n]
    quads = [_quad_from_contour(c) for c in cnts]
    quads.sort(key=lambda q: q[:, 0].mean())
    return quads

def _rect_dims(quad, base=2000):
    wq = (np.linalg.norm(quad[1]-quad[0]) + np.linalg.norm(quad[2]-quad[3])) / 2
    hq = (np.linalg.norm(quad[3]-quad[0]) + np.linalg.norm(quad[2]-quad[1])) / 2
    return max(1, round(base * wq / hq)), base

def _border_color(a):
    b = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]], axis=0).reshape(-1, 3)
    return np.median(b, axis=0)

def _place(cover_img, FW, FH, fit=1.0, top_bias=0.62, crop_border=10):
    """표지를 FW×FH 프레임에 배치. fit=1=꽉채움(가장자리, 상단위주 크롭),
    <1=축소(단색 여백), >1=확대(크롭)."""
    a = np.asarray(cover_img.convert("RGB"))
    if a.shape[0] > 2*crop_border and a.shape[1] > 2*crop_border:
        a = a[crop_border:a.shape[0]-crop_border, crop_border:a.shape[1]-crop_border]
    ch, cw = a.shape[:2]
    fill = max(FW/cw, FH/ch)
    scale = fill * max(0.4, min(2.0, fit))
    nw, nh = max(1, round(cw*scale)), max(1, round(ch*scale))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    r = cv2.resize(a, (nw, nh), interpolation=interp).astype(np.float32)
    canvas = np.full((FH, FW, 3), _border_color(a), dtype=np.float32)
    xoff = (FW - nw) // 2
    yoff = -int(round((nh - FH) * top_bias)) if nh > FH else (FH - nh) // 2
    dx0, dx1 = max(0, xoff), min(FW, xoff + nw)
    dy0, dy1 = max(0, yoff), min(FH, yoff + nh)
    canvas[dy0:dy1, dx0:dx1] = r[dy0-yoff:dy1-yoff, dx0-xoff:dx1-xoff]
    return canvas

def _front_of_spread(img):
    w, h = img.size
    return img.crop((w // 2, 0, w, h)) if w / h > 1.2 else img

def _warp_into(rect, quad, W, H):
    FH, FW = rect.shape[:2]
    M = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [FW-1, 0], [FW-1, FH-1], [0, FH-1]]), quad)
    warp = cv2.warpPerspective(rect, M, (W, H), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    mask = np.zeros((H, W), np.float32)
    cv2.fillConvexPoly(mask, quad.astype(np.int32), 1.0)
    return warp, mask[..., None]

def _add_shadow(rgba, opacity=0.30, dx_f=0.006, dy_f=0.020, blur_f=0.020, pad_f=0.14):
    im = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    bb = im.getbbox()
    if bb: im = im.crop(bb)
    w, h = im.size
    dx, dy = int(dx_f*h), int(dy_f*h); blur = blur_f*h; m = int(pad_f*h)
    shmask = im.split()[-1].point(lambda a: int(a*opacity))
    shadow = Image.new("RGBA", (w+2*m, h+2*m), (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", (w, h), (18, 18, 22, 255)), (m+dx, m+dy), shmask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    out = shadow.copy(); out.alpha_composite(im, (m, m))
    bb = out.getbbox()
    return out.crop(bb) if bb else out

def _finish(out_img, tpl, long_edge, shadow):
    over = os.path.join(BAKE, f"{tpl}_over.png") if tpl else None
    if over and os.path.exists(over):
        out_img.alpha_composite(Image.open(over).convert("RGBA"))
    if shadow:
        res = _add_shadow(np.asarray(out_img, dtype=np.float32))
    else:
        res = out_img; bb = res.getbbox(); res = res.crop(bb) if bb else res
    s = long_edge / max(res.size)
    return res.resize((round(res.width*s), round(res.height*s)), Image.LANCZOS)

def _composite(A, B, C):
    out_rgb = np.clip(B[..., :3] + (C/255.0) * (A[..., :3] - B[..., :3]), 0, 255)
    return Image.fromarray(np.dstack([out_rgb, A[..., 3]]).astype(np.uint8), "RGBA")

def _flat_sheet(cover, long_edge, shadow):
    src = cover.convert("RGB"); w, h = src.size
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, (max(1, h//4), max(1, w//4))).astype(np.float32)
    noise = (noise - noise.min()) / (np.ptp(noise) + 1e-6) * 255
    tex = Image.fromarray(noise.astype(np.uint8)).resize((w, h)).filter(ImageFilter.GaussianBlur(0.6))
    paper = src.convert("RGBA")
    paper.alpha_composite(Image.merge("RGBA", [tex]*3 + [Image.new("L", (w, h), 12)]))
    edge = Image.new("L", (w, h), 0); d = ImageDraw.Draw(edge)
    b = max(2, int(min(w, h)*0.004)); d.rectangle([0, 0, w-1, h-1], outline=40, width=b)
    edge = edge.filter(ImageFilter.GaussianBlur(b))
    paper.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 0), edge.point(lambda a: int(a*0.25)))
    res = _add_shadow(np.asarray(paper, dtype=np.float32), opacity=0.26, dy_f=0.016, blur_f=0.016) if shadow else paper
    s = long_edge / max(res.size)
    return res.resize((round(res.width*s), round(res.height*s)), Image.LANCZOS)

def render(cover_img, binding, back_img=None, long_edge=1500, shadow=True, fit=1.0):
    if binding in FLAT:
        return _flat_sheet(cover_img, long_edge, shadow)

    if binding in SPREAD:
        tpl = SPREAD[binding]; A, B = _get_ab(tpl); H, W = A.shape[:2]
        quads = _detect_quads(A, B, n=2)
        pages = [_front_of_spread(cover_img), _front_of_spread(back_img or cover_img)]
        C = np.zeros((H, W, 3), np.float32)
        for cov_src, quad in zip(pages, quads):
            FW, FH = _rect_dims(quad)
            warp, mask = _warp_into(_place(cov_src, FW, FH, fit), quad, W, H)
            C = C*(1-mask) + warp*mask
        return _finish(_composite(A, B, C), tpl, long_edge, shadow)

    tpl = TEMPLATES[binding]; A, B = _get_ab(tpl); H, W = A.shape[:2]
    quad = _detect_quads(A, B, n=1)[0]
    FW, FH = _rect_dims(quad)
    warp, mask = _warp_into(_place(_front_of_spread(cover_img), FW, FH, fit), quad, W, H)
    return _finish(_composite(A, B, warp*mask), tpl, long_edge, shadow)


if __name__ == "__main__":
    import sys
    r = render(Image.open(sys.argv[1]), sys.argv[2],
               fit=float(sys.argv[4]) if len(sys.argv) > 4 else 1.0)
    r.save(sys.argv[3]); print("saved", sys.argv[3], r.size)
