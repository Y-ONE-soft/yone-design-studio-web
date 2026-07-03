"""헤드리스 책 목업 엔진 — A/B 라이트맵 방식 (Photoshop 불필요).
흰 표지 렌더(A)·검은 표지 렌더(B)를 한 번만 베이크해두면
  out = B + cover*(A-B)
로 원근·조명·페이지단면·스파이럴 오클루전을 재현한다.
바인딩별 템플릿: 무선(wireless) / 스프링(spring) / 중철(saddle04).
"""
import os
import numpy as np
import cv2
from PIL import Image, ImageFilter

BAKE = os.path.join(os.path.dirname(__file__), "bake")

# 바인딩 이름 → 베이크 템플릿
TEMPLATES = {"무선": "wireless", "스프링": "spring", "중철": "saddle04"}

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

def _detect_quad(A, B):
    diff = np.abs(A[..., :3] - B[..., :3]).mean(2)
    mask = (diff > 40).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    # 최소면적 회전사각형 → 오클루전(스파이럴)에 강함
    box = cv2.boxPoints(cv2.minAreaRect(c))
    peri = cv2.arcLength(c, True)
    for k in (0.02, 0.03, 0.05):
        ap = cv2.approxPolyDP(c, k * peri, True)
        if len(ap) == 4:
            box = ap; break
    return _order_quad(box)

def _prep_cover(img, target_ratio, crop=10):
    a = np.asarray(img.convert("RGB"))
    if a.shape[0] > 2*crop and a.shape[1] > 2*crop:
        a = a[crop:a.shape[0]-crop, crop:a.shape[1]-crop]
    h, w = a.shape[:2]
    tw = round(h * target_ratio)
    if tw > w:
        pl = (tw - w) // 2; pr = tw - w - pl
        a = np.concatenate([np.repeat(a[:, :1], pl, 1), a, np.repeat(a[:, -1:], pr, 1)], axis=1)
    elif tw < w:
        th = round(w / target_ratio); pt = (th - h) // 2; pb = th - h - pt
        a = np.concatenate([np.repeat(a[:1, :], pt, 0), a, np.repeat(a[-1:, :], pb, 0)], axis=0)
    return a

def _front_of_spread(img):
    w, h = img.size
    if w / h > 1.2:               # 펼침 → 오른쪽 절반이 앞표지
        return img.crop((w // 2, 0, w, h))
    return img

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

def render(cover_img, binding, long_edge=1500, shadow=True):
    """cover_img: PIL.Image (앞표지 또는 펼침), binding: 무선/스프링/중철."""
    tpl = TEMPLATES.get(binding)
    if not tpl:
        raise ValueError(f"알 수 없는 바인딩: {binding}")
    A, B = _get_ab(tpl)
    H, W = A.shape[:2]
    quad = _detect_quad(A, B)
    tl, tr, br, bl = quad
    wq = (np.linalg.norm(tr-tl) + np.linalg.norm(br-bl)) / 2
    hq = (np.linalg.norm(bl-tl) + np.linalg.norm(br-tr)) / 2
    cov = _prep_cover(_front_of_spread(cover_img), wq / hq)
    ch, cw = cov.shape[:2]
    M = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [cw-1, 0], [cw-1, ch-1], [0, ch-1]]), quad)
    warped = cv2.warpPerspective(cov, M, (W, H), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255.0
    out_rgb = np.clip(B[..., :3] + warped * (A[..., :3] - B[..., :3]), 0, 255)
    out_img = Image.fromarray(np.dstack([out_rgb, A[..., 3]]).astype(np.uint8), "RGBA")
    # 표지 위 요소(스파이럴 등) 오버레이 — 반투명이라 라이트맵으로 재현 불가
    over_path = os.path.join(BAKE, f"{tpl}_over.png")
    if os.path.exists(over_path):
        out_img.alpha_composite(Image.open(over_path).convert("RGBA"))
    if shadow:
        res = _add_shadow(np.asarray(out_img, dtype=np.float32))
    else:
        res = out_img; bb = res.getbbox(); res = res.crop(bb) if bb else res
    s = long_edge / max(res.size)
    return res.resize((round(res.width*s), round(res.height*s)), Image.LANCZOS)


if __name__ == "__main__":
    import sys
    Image.open(sys.argv[1])
    r = render(Image.open(sys.argv[1]), sys.argv[2])
    r.save(sys.argv[3]); print("saved", sys.argv[3], r.size)
