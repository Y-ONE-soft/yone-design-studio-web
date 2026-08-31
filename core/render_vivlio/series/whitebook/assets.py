"""완성본 PDF 에서 화이트북 머리 아트워크를 뽑아 `assets/` 로.

두 조각뿐이다.
  · `emblem.png` — 홀수 면 바깥 위의 **흰** 로고. 하늘 띠 위에 흰 잉크로 찍혀
    있어서 띠 색을 언믹스해 투명으로 만든다.
  · `brand.png`  — 짝수 면 바깥 위의 `✦ WHITE BOOK VOL.N`. 앞부분(마름모 +
    WHITE BOOK)은 **AcademyEngravedStd** 라 이 기계에 없다 → 완성본에서 그대로
    떠 오고, 권 번호(`VOL.N`)만 Elice 로 다시 그려 붙인다.
    ⚠ 완성본에서 통째로 뜨면 `VOL.1` 이 그대로 박혀 2권에 1권 표기가 나간다.
"""
import os

import fitz

from core.render_vivlio import stage

PT = 72 / 25.4
DPI = 1200

# 완성본 실측(mm, 재단 기준) — 1권 24면
ART = {"page": 23, "rect": [15.00, 7.40, 51.30, 14.20]}     # ✦ WHITE BOOK
EMBLEM = {"page": 24, "rect": [187.80, 6.10, 203.90, 16.40]}
BAND = (212, 222, 237)      # #d4deed 하늘 띠
TEAL = (24, 166, 192)       # #18a6c0
VOL = {"x": 36.08, "baseline": 4.48, "size_pt": 9.0,
       "font": "EliceDigitalBaeumOTF_Regular.otf"}


def _unmix(im, bg, ink):
    """단색 바탕 위 한 색 잉크 → 바탕을 투명하게."""
    px = im.load()
    den = max(abs(ink[i] - bg[i]) for i in range(3)) or 1
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y][:3]
            num = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            a = min(255, int(round(num * 255.0 / den)))
            px[x, y] = (ink[0], ink[1], ink[2], 0 if a < 10 else a)
    return im


def _grab(doc, job, bg, ink, dpi=DPI):
    from PIL import Image
    x0, y0, x1, y1 = job["rect"]
    pix = doc[job["page"]].get_pixmap(
        dpi=dpi, clip=fitz.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT))
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return _unmix(im.convert("RGBA"), bg, ink)


def build(cfg, log=print):
    from PIL import Image, ImageDraw, ImageFont
    spec = cfg.section("assets") or {}
    src = cfg.resolve(spec.get("src_pdf", ""))
    out = cfg.resolve(spec.get("dir", "assets"))
    if not src or not os.path.exists(src):
        raise FileNotFoundError(f"아트워크 원본 없음: {src}")
    os.makedirs(out, exist_ok=True)
    doc = fitz.open(src)

    em = _grab(doc, EMBLEM, BAND, (255, 255, 255))
    em.save(os.path.join(out, "emblem.png"))
    log(f"emblem.png  {em.width}×{em.height}px  "
        f"(재단 {EMBLEM['rect'][0]:.2f},{EMBLEM['rect'][1]:.2f})")

    art = _grab(doc, ART, BAND, TEAL)
    vol = str(spec.get("volume", cfg.book.get("volume", 1)))
    fp = stage.find_font(VOL["font"])
    if not fp:
        raise FileNotFoundError(f"서체 없음: {VOL['font']}")
    px_mm = DPI / 25.4
    # 캔버스를 오른쪽으로 넉넉히 늘려 `VOL.N` 을 그린다
    w = int(round((ART["rect"][2] - ART["rect"][0] + 12.0) * px_mm))
    canvas = Image.new("RGBA", (w, art.height), (0, 0, 0, 0))
    canvas.paste(art, (0, 0))
    font = ImageFont.truetype(fp, int(round(VOL["size_pt"] / 72.0 * DPI)))
    d = ImageDraw.Draw(canvas)
    asc, _desc = font.getmetrics()
    d.text((int(round(VOL["x"] * px_mm)),
            int(round(VOL["baseline"] * px_mm)) - asc),
           f"VOL.{vol}", font=font, fill=TEAL + (255,))
    bbox = canvas.getbbox()
    canvas = canvas.crop((0, 0, bbox[2], art.height))
    canvas.save(os.path.join(out, "brand.png"))
    log(f"brand.png   {canvas.width}×{canvas.height}px  "
        f"→ 폭 {canvas.width / px_mm:.2f}mm (VOL.{vol})")
    doc.close()
    return out
