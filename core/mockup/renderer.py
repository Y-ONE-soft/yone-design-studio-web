"""Book mockup renderer — ported from mockup_app.py"""
import io
import numpy as np
import cv2
from PIL import Image

COVER_W, COVER_H = 500, 707

DEFAULTS = {
    "scale": 1.0, "offset_x": 0, "offset_y": 0,
    "slope": 25, "spine_width": 20, "top_height": 14,
    "shadow_opacity": 100, "shadow_dist_x": 20, "shadow_dist_y": 28,
    "back_dist_x": 0, "back_dist_y": 0,
    "bg_color": "#1a1a22", "bg_transparent": False, "show_back": True,
}

SPECS = {
    "scale":          ("전체 스케일",   0.30, 1.50, 0.01, True),
    "offset_x":       ("좌우 이동",    -400,  400,    1, False),
    "offset_y":       ("상하 이동",    -300,  300,    1, False),
    "slope":          ("기울기",          0,   60,    1, False),
    "spine_width":    ("책등 너비",       4,   60,    1, False),
    "top_height":     ("상단 면 높이",    2,   40,    1, False),
    "shadow_opacity": ("그림자 강도",     0,  200,    1, False),
    "shadow_dist_x":  ("그림자 가로",     0,  120,    1, False),
    "shadow_dist_y":  ("그림자 세로",     0,  120,    1, False),
    "back_dist_x":    ("뒷표지 가로",  -300,  300,    1, False),
    "back_dist_y":    ("뒷표지 세로",  -200,  200,    1, False),
}


def load_cover_bytes(file_bytes, filename="", page=0):
    """page: PDF 페이지 인덱스. 범위 밖이면 None (이미지 파일은 page>0이면 None)."""
    name = filename.lower()
    if name.endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if page >= doc.page_count:
                return None
            pg = doc[page]
            mat = fitz.Matrix(200/72, 200/72)
            clip = pg.trimbox
            if clip.is_empty or clip.width < 10:
                clip = pg.rect
            pix = pg.get_pixmap(matrix=mat, clip=clip, alpha=False)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        except ImportError:
            raise RuntimeError("PDF 처리를 위해 PyMuPDF 필요")
    return None if page > 0 else Image.open(io.BytesIO(file_bytes)).convert("RGB")


def default_crop_params(img, side="front"):
    """이미지의 기본 크롭 파라미터를 반환."""
    w, h = img.size
    if w / h > 5 / 7:
        cw = int(h * 5 / 7); ch = h
    else:
        cw = w; ch = int(w * 7 / 5)
    ch = min(ch, h); cw = min(cw, w)
    is_spread = (w / h) > 1.2
    if is_spread and side == "front":
        cx = w - cw
    elif is_spread and side == "back":
        cx = 0
    else:
        cx = (w - cw) // 2
    cy = (h - ch) // 2
    return {"cx": cx, "cy": cy, "cw": cw, "w": w, "h": h}


def apply_crop(img, cx, cy, cw):
    w, h = img.size
    ch = int(cw * 7 / 5)
    cx = max(0, min(int(cx), w - cw))
    cy = max(0, min(int(cy), h - ch))
    return img.crop((cx, cy, cx + cw, cy + ch)).resize((COVER_W, COVER_H), Image.LANCZOS)


def _alpha_comp(dst, src):
    df = dst.astype(np.float32)/255; sf = src.astype(np.float32)/255
    sa = sf[...,3:4]; da = df[...,3:4]; oa = sa + da*(1-sa)
    rgb = np.where(oa > 1e-6, (sf[...,:3]*sa + df[...,:3]*da*(1-sa))/oa, 0)
    return np.clip(np.concatenate([rgb, oa], -1)*255, 0, 255).astype(np.uint8)


def _warp(src, quad, sz):
    h, w = src.shape[:2]
    M = cv2.getPerspectiveTransform(
        np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),
        np.float32(quad))
    return cv2.warpPerspective(src, M, sz,
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0,0))


def _poly_shadow(sz, quad, off, blur, op):
    w, h = sz; s = np.zeros((h,w,4), dtype=np.uint8)
    cv2.fillConvexPoly(s, np.array([[x+off[0],y+off[1]] for x,y in quad], dtype=np.int32), (0,0,0,op))
    return cv2.GaussianBlur(s, (0,0), blur)


def _ellipse_shadow(sz, cx, cy, rx, ry, blur, op):
    w, h = sz; s = np.zeros((h,w,4), dtype=np.uint8)
    cv2.ellipse(s, (cx,cy), (rx,ry), 0, 0, 360, (0,0,0,op), -1)
    return cv2.GaussianBlur(s, (0,0), blur)


def _spine_tex(cover, sw):
    h, w = cover.shape[:2]; sw = max(4, min(sw, w))
    t = cover[:,w-sw:].copy().astype(np.float32)
    t[...,:3] *= 0.72 * np.linspace(1.0, 0.80, sw, dtype=np.float32).reshape(1,sw,1)
    return t.clip(0,255).astype(np.uint8)


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def render(front_img, back_img, params):
    p = {**DEFAULTS, **params}
    CW, CH = 1400, 1000; sz = (CW, CH)
    sc = p["scale"]; dx = p["offset_x"]; dy = p["offset_y"]
    FD = p["spine_width"]; FS = p["slope"]; FOH = p["top_height"]
    so = p["shadow_opacity"]/100; sdx = p["shadow_dist_x"]; sdy = p["shadow_dist_y"]
    bdx = p["back_dist_x"]; bdy = p["back_dist_y"]
    transp = p.get("bg_transparent", False); show_back = p["show_back"]

    canvas = np.zeros((CH, CW, 4), dtype=np.uint8)
    if not transp:
        canvas[:] = (*_hex_rgb(p["bg_color"]), 255)

    fr = np.array(front_img.convert("RGBA").resize((COVER_W, COVER_H), Image.LANCZOS), dtype=np.uint8)
    cx0 = CW/2 + dx; cy0 = CH/2 + dy
    def s(x, y): return (cx0 + (x-CW/2)*sc, cy0 + (y-CH/2)*sc)
    FX, FY = 195, 155
    fx, fy = s(FX, FY)
    fw = COVER_W*sc; fh = COVER_H*sc; fd = FD*sc; fs_ = FS*sc; foh = FOH*sc
    def fq(x, y): return (fx+x, fy+y)
    ff_q = [fq(0,0), fq(fw,fs_), fq(fw,fs_+fh), fq(0,fh)]
    fs_q = [fq(fw,fs_), fq(fw+fd,fs_-foh), fq(fw+fd,fs_+fh-foh), fq(fw,fs_+fh)]
    ft_pts = np.array([fq(fd,-foh), fq(fw+fd,fs_-foh), fq(fw,fs_), fq(0,0)], dtype=np.int32)
    f_sil = [fq(0,0), fq(fd,-foh), fq(fw+fd,fs_-foh), fq(fw+fd,fs_+fh-foh), fq(0,fh)]
    fpo = int(min(255, 255*so*0.55)); fco = int(min(255, 255*so*0.18))

    if show_back and back_img is not None:
        br = np.array(back_img.convert("RGBA").resize((COVER_W, COVER_H), Image.LANCZOS), dtype=np.uint8)
        bx0, by0 = 478+bdx, 88+bdy; bx, by = s(bx0, by0)
        def bq(x, y): return (bx+x, by+y)
        bf_q = [bq(0,0), bq(fw,fs_), bq(fw,fs_+fh), bq(0,fh)]
        bs_q = [bq(fw,fs_), bq(fw+fd,fs_-foh), bq(fw+fd,fs_+fh-foh), bq(fw,fs_+fh)]
        bt_pts = np.array([bq(fd,-foh), bq(fw+fd,fs_-foh), bq(fw,fs_), bq(0,0)], dtype=np.int32)
        b_sil = [bq(0,0), bq(fd,-foh), bq(fw+fd,fs_-foh), bq(fw+fd,fs_+fh-foh), bq(0,fh)]
        bpo = int(min(255, 255*so*0.35)); bco = int(min(255, 255*so*0.12))
        canvas = _alpha_comp(canvas, _poly_shadow(sz, b_sil, (sdx, sdy), 35, bpo))
        canvas = _alpha_comp(canvas, _ellipse_shadow(sz, int(bx+fw//2), int(by+fs_+fh+8), int(fw//2+14), 15, 18, bco))
        canvas = _alpha_comp(canvas, _warp(_spine_tex(br, int(fd)), bs_q, sz))
        canvas = _alpha_comp(canvas, _warp(br, bf_q, sz))
        cv2.fillConvexPoly(canvas, bt_pts, (238,235,230,255))

    canvas = _alpha_comp(canvas, _poly_shadow(sz, f_sil, (sdx, sdy), 38, fpo))
    canvas = _alpha_comp(canvas, _ellipse_shadow(sz, int(fx+fw//2), int(fy+fs_+fh+10), int(fw//2+16), 18, 20, fco))
    canvas = _alpha_comp(canvas, _warp(_spine_tex(fr, int(fd)), fs_q, sz))
    canvas = _alpha_comp(canvas, _warp(fr, ff_q, sz))
    cv2.fillConvexPoly(canvas, ft_pts, (238,235,230,255))
    return Image.fromarray(canvas, "RGBA")


def render_to_bytes(front_img, back_img, params, fmt="PNG"):
    result = render(front_img, back_img, params)
    buf = io.BytesIO()
    if fmt.upper() == "PNG":
        result.save(buf, format="PNG")
    else:
        bg = Image.new("RGB", result.size, (255, 255, 255))
        bg.paste(result, mask=result.split()[-1])
        bg.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf.getvalue()
