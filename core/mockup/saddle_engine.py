"""헤드리스 중철(saddle) 목업 엔진 — A/B 라이트맵 방식.
Photoshop 불필요. 베이크된 A(흰 표지)/B(검은 표지) 렌더로부터
  out = B + cover*(A-B)
로 원근·조명·페이지단면을 재현한다.
"""
import os
import numpy as np
import cv2
from PIL import Image, ImageFilter

BAKE = os.path.join(os.path.dirname(__file__), "bake")

def _load_rgba(path):
    im = Image.open(path).convert("RGBA")
    return np.asarray(im, dtype=np.float32)

def _order_quad(pts):
    # pts: 4x2 → TL,TR,BR,BL
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(1); d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)

def _detect_quad(A, B):
    diff = np.abs(A[..., :3] - B[..., :3]).mean(2)
    mask = (diff > 40).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cnts, key=cv2.contourArea)
    peri = cv2.arcLength(c, True)
    for k in (0.02, 0.03, 0.05, 0.08):
        ap = cv2.approxPolyDP(c, k * peri, True)
        if len(ap) == 4:
            return _order_quad(ap)
    # fallback: minAreaRect
    box = cv2.boxPoints(cv2.minAreaRect(c))
    return _order_quad(box)

def _prep_cover(img, target_ratio, crop=10):
    """PDF 밝은 테두리 제거 후 좌우 edge-replicate로 target_ratio(w/h)에 맞춤."""
    a = np.asarray(img.convert("RGB"))
    a = a[crop:a.shape[0]-crop, crop:a.shape[1]-crop]
    h, w = a.shape[:2]
    tw = round(h * target_ratio)
    if tw > w:
        pl = (tw - w) // 2; pr = tw - w - pl
        left = np.repeat(a[:, :1, :], pl, axis=1)
        right = np.repeat(a[:, -1:, :], pr, axis=1)
        a = np.concatenate([left, a, right], axis=1)
    elif tw < w:  # 표지가 더 넓으면 상하 패딩
        th = round(w / target_ratio); pt = (th - h) // 2; pb = th - h - pt
        top = np.repeat(a[:1, :, :], pt, axis=0); bot = np.repeat(a[-1:, :, :], pb, axis=0)
        a = np.concatenate([top, a, bot], axis=0)
    return a

def _add_shadow(rgba, opacity=0.30, dx_f=0.006, dy_f=0.020, blur_f=0.020, pad_f=0.14):
    im = Image.fromarray(rgba.astype(np.uint8), "RGBA")
    bb = im.getbbox()
    if bb: im = im.crop(bb)
    w, h = im.size
    dx, dy = int(dx_f*h), int(dy_f*h); blur = blur_f*h; m = int(pad_f*h)
    alpha = im.split()[-1]
    shmask = alpha.point(lambda a: int(a*opacity))
    shadow = Image.new("RGBA", (w+2*m, h+2*m), (0, 0, 0, 0))
    tint = Image.new("RGBA", (w, h), (18, 18, 22, 255))
    shadow.paste(tint, (m+dx, m+dy), shmask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    out = shadow.copy(); out.alpha_composite(im, (m, m))
    bb = out.getbbox()
    return out.crop(bb) if bb else out

def render_saddle(cover_img, template="saddle04", long_edge=1500, shadow=True):
    A = _load_rgba(os.path.join(BAKE, f"{template}_A.png"))
    B = _load_rgba(os.path.join(BAKE, f"{template}_B.png"))
    H, W = A.shape[:2]
    quad = _detect_quad(A, B)
    # 쿼드 비율(앞표지 면 종횡비) 추정 → 표지를 그 비율로 패딩
    tl, tr, br, bl = quad
    wq = (np.linalg.norm(tr-tl) + np.linalg.norm(br-bl)) / 2
    hq = (np.linalg.norm(bl-tl) + np.linalg.norm(br-tr)) / 2
    cov = _prep_cover(cover_img, wq/hq)
    ch, cw = cov.shape[:2]
    Hm = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [cw-1, 0], [cw-1, ch-1], [0, ch-1]]), quad)
    warped = cv2.warpPerspective(cov, Hm, (W, H), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    c01 = warped / 255.0
    out_rgb = B[..., :3] + c01 * (A[..., :3] - B[..., :3])
    out = np.dstack([np.clip(out_rgb, 0, 255), A[..., 3]])
    if shadow:
        res = _add_shadow(out)
    else:
        res = Image.fromarray(out.astype(np.uint8), "RGBA")
        bb = res.getbbox(); res = res.crop(bb) if bb else res
    s = long_edge / max(res.size)
    return res.resize((round(res.width*s), round(res.height*s)), Image.LANCZOS)

if __name__ == "__main__":
    import sys
    cov = Image.open(sys.argv[1])
    out = render_saddle(cov)
    out.save(sys.argv[2])
    print("saved", sys.argv[2], out.size)
