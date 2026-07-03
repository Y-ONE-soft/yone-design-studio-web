"""헤드리스 책 목업 엔진 — A/B 라이트맵 방식 (Photoshop 불필요).
흰 표지 렌더(A)·검은 표지 렌더(B)를 한 번만 베이크해두면
  out = B + cover*(A-B)
로 원근·조명·페이지단면·스파이럴 오클루전을 재현한다.

바인딩:
  무선/스프링/중철  → 단면 앞표지 (A/B 1쿼드)
  중철펼침          → 펼친 2페이지 (A/B 2쿼드, front=왼쪽·back=오른쪽)
  낱장              → 가로/세로 A4 종이 1장 (목업 없이 종이질감+그림자)

fit: 표지 맞춤 배율(0.85~1.15). 1.0=프레임 꽉 채움, <1=축소(가장자리 복제 여백),
     >1=확대(가장자리 크롭).
"""
import os
import numpy as np
import cv2
from PIL import Image, ImageFilter, ImageDraw

BAKE = os.path.join(os.path.dirname(__file__), "bake")

TEMPLATES = {"무선": "wireless", "스프링": "spring", "중철": "saddle04"}  # 단면
SPREAD = {"중철펼침": "saddle02"}                                        # 펼침
FLAT = {"낱장"}                                                          # 종이 1장
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
    quads.sort(key=lambda q: q[:, 0].mean())      # 왼→오
    return quads

def _prep_cover(img, target_ratio, crop=10, fit=1.0):
    a = np.asarray(img.convert("RGB"))
    if a.shape[0] > 2*crop and a.shape[1] > 2*crop:
        a = a[crop:a.shape[0]-crop, crop:a.shape[1]-crop]
    h, w = a.shape[:2]
    tw = round(h * target_ratio)
    if tw > w:
        pl = (tw - w) // 2
        a = np.concatenate([np.repeat(a[:, :1], pl, 1), a, np.repeat(a[:, -1:], tw-w-pl, 1)], axis=1)
    elif tw < w:
        th = round(w / target_ratio); pt = (th - h) // 2
        a = np.concatenate([np.repeat(a[:1, :], pt, 0), a, np.repeat(a[-1:, :], th-h-pt, 0)], axis=0)
    # fit: 표지 맞춤 배율
    h, w = a.shape[:2]
    if fit < 0.999:                                # 축소 → 가장자리 복제 여백
        nw, nh = round(w/fit), round(h/fit)
        pl, pt = (nw-w)//2, (nh-h)//2
        a = np.concatenate([np.repeat(a[:, :1], pl, 1), a, np.repeat(a[:, -1:], nw-w-pl, 1)], axis=1)
        a = np.concatenate([np.repeat(a[:1, :], pt, 0), a, np.repeat(a[-1:, :], nh-h-pt, 0)], axis=0)
    elif fit > 1.001:                              # 확대 → 중앙 크롭
        nw, nh = round(w/fit), round(h/fit)
        x, y = (w-nw)//2, (h-nh)//2
        a = a[y:y+nh, x:x+nw]
    return a

def _front_of_spread(img):
    w, h = img.size
    return img.crop((w // 2, 0, w, h)) if w / h > 1.2 else img

def _warp_into(cover, quad, W, H):
    ch, cw = cover.shape[:2]
    M = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [cw-1, 0], [cw-1, ch-1], [0, ch-1]]), quad)
    warp = cv2.warpPerspective(cover, M, (W, H), flags=cv2.INTER_CUBIC,
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
    over_path = os.path.join(BAKE, f"{tpl}_over.png") if tpl else None
    if over_path and os.path.exists(over_path):
        out_img.alpha_composite(Image.open(over_path).convert("RGBA"))
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
    src = cover.convert("RGB")
    w, h = src.size
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
    if shadow:
        res = _add_shadow(np.asarray(paper, dtype=np.float32), opacity=0.26, dy_f=0.016, blur_f=0.016)
    else:
        res = paper
    s = long_edge / max(res.size)
    return res.resize((round(res.width*s), round(res.height*s)), Image.LANCZOS)

def render(cover_img, binding, back_img=None, long_edge=1500, shadow=True, fit=1.0):
    """cover_img: PIL.Image. binding: 무선/스프링/중철/중철펼침/낱장."""
    if binding in FLAT:
        return _flat_sheet(cover_img, long_edge, shadow)

    if binding in SPREAD:
        tpl = SPREAD[binding]; A, B = _get_ab(tpl); H, W = A.shape[:2]
        quads = _detect_quads(A, B, n=2)
        pages = [_front_of_spread(cover_img), _front_of_spread(back_img or cover_img)]
        C = np.zeros((H, W, 3), np.float32)
        for cov_src, quad in zip(pages, quads):
            wq = (np.linalg.norm(quad[1]-quad[0]) + np.linalg.norm(quad[2]-quad[3])) / 2
            hq = (np.linalg.norm(quad[3]-quad[0]) + np.linalg.norm(quad[2]-quad[1])) / 2
            warp, mask = _warp_into(_prep_cover(cov_src, wq/hq, fit=fit), quad, W, H)
            C = C*(1-mask) + warp*mask
        return _finish(_composite(A, B, C), tpl, long_edge, shadow)

    tpl = TEMPLATES[binding]; A, B = _get_ab(tpl); H, W = A.shape[:2]
    quad = _detect_quads(A, B, n=1)[0]
    wq = (np.linalg.norm(quad[1]-quad[0]) + np.linalg.norm(quad[2]-quad[3])) / 2
    hq = (np.linalg.norm(quad[3]-quad[0]) + np.linalg.norm(quad[2]-quad[1])) / 2
    cov = _prep_cover(_front_of_spread(cover_img), wq/hq, fit=fit)
    warp, mask = _warp_into(cov, quad, W, H)
    C = warp * mask
    return _finish(_composite(A, B, C), tpl, long_edge, shadow)


if __name__ == "__main__":
    import sys
    r = render(Image.open(sys.argv[1]), sys.argv[2],
               fit=float(sys.argv[4]) if len(sys.argv) > 4 else 1.0)
    r.save(sys.argv[3]); print("saved", sys.argv[3], r.size)
