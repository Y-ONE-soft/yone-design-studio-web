"""완성본(인디자인 원본) PDF 에서 고정 아트워크를 잘라 `assets/` 로.

투명 여백을 자동으로 잘라내고, 테마에 쓸 background 위치/크기(mm)를 출력한다.
좌표를 눈대중으로 잘라 **글자가 잘리는 사고**가 있었으므로 넉넉히 자르고 자동
트림에 맡긴다(글자 bbox 만 믿으면 아래가 잘린다). 회색 띠 위 그림은 바탕색을
언믹스해 투명으로 만든다.

디자인이 바뀔 때만 돌린다 — 빌드 경로에는 들어가지 않는다.
잘라낼 대상은 config 의 `assets.jobs` 에 둔다:
    [{"name","page","rect":[x0,y0,x1,y1],"unmix":{"bg":[r,g,b],
      "zones":[[x분기mm,[r,g,b]], …]}}]
`page` 가 음수면 뒤에서 센다(-1 = 마지막 면). `src` 를 적으면 조각마다 다른 완성본.
"""
import os
import fitz

PT = 72 / 25.4
DPI = 1600


def unmix(im, x0mm, bg, zones, dpi):
    """단색 바탕 위 그림 → 바탕을 투명하게(잉크색은 구역별로 지정)."""
    px = im.load()
    scale = 25.4 / dpi
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            xm = x0mm + x * scale
            ink = next(c for lim, c in zones if xm < lim)
            num = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            den = max(abs(ink[0] - bg[0]), abs(ink[1] - bg[1]), abs(ink[2] - bg[2]))
            al = 0 if den == 0 else min(255, int(round(num * 255 / den)))
            if al < 10:      # 바탕 잔여값 — 완전 투명으로
                al = 0
            px[x, y] = (ink[0], ink[1], ink[2], al)
    return im


def trim(pix, x0, y0, dpi, key=None):
    """투명 여백 제거 → (PIL 이미지, 실제 위치 mm)"""
    from PIL import Image
    im = Image.frombytes('RGBA', (pix.width, pix.height), pix.samples)
    if key:
        im = unmix(im, x0, key[0], key[1], dpi)
    bbox = im.getbbox()
    im = im.crop(bbox)
    scale = 25.4 / dpi
    return im, (x0 + bbox[0] * scale, y0 + bbox[1] * scale,
                (bbox[2] - bbox[0]) * scale, (bbox[3] - bbox[1]) * scale)


def build(cfg, log=print):
    """config 의 `assets` 대로 아트워크를 추출한다."""
    spec = cfg.section('assets') or {}
    src = cfg.resolve(spec.get('src_pdf', ''))
    out = cfg.resolve(spec.get('dir', 'assets'))
    if not src or not os.path.exists(src):
        raise FileNotFoundError(f'아트워크 원본 없음: {src}')
    os.makedirs(out, exist_ok=True)
    doc = fitz.open(src)
    docs = {src: doc}
    for job in spec.get('jobs') or []:
        name, page = job['name'], job['page']
        jsrc = cfg.resolve(job['src']) if job.get('src') else src
        if jsrc not in docs:
            if not os.path.exists(jsrc):
                raise FileNotFoundError(f'아트워크 원본 없음: {jsrc}')
            docs[jsrc] = fitz.open(jsrc)
        jdoc = docs[jsrc]
        if page < 0:                      # -1 = 마지막 면(뒤 간지) — 완성본마다 면수가 다르다
            page += len(jdoc)
        x0, y0, x1, y1 = job['rect']
        um = job.get('unmix')
        key = None
        if um:
            key = (tuple(um['bg']),
                   [(lim, tuple(c)) for lim, c in um['zones']])
        dpi = job.get('dpi') or (DPI if not key else 800)
        pix = jdoc[page].get_pixmap(
            dpi=dpi, clip=fitz.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT),
            alpha=True)
        im, (mx, my, mw, mh) = trim(pix, x0, y0, dpi, key)
        im.save(os.path.join(out, f'{name}.png'))
        log(f'{name}.png  {im.width}×{im.height}px  '
            f'→ no-repeat {mx:.2f}mm {my:.2f}mm / {mw:.2f}mm {mh:.2f}mm')
    for d in docs.values():
        d.close()
    return out
