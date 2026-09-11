"""표지 PDF 의 **벡터** 로고 → SVG (assets/*.svg).

한문끝 표지(일러스트) 로고는 글자가 아니라 채움 패스다(각인Books 13개·각인입시전문학원
27개). 래스터로 뜨면 300dpi 규약을 못 지키고 종이 바탕이 같이 딸려 온다 → 사각형
안의 채움 패스만 골라 SVG 패스로 옮긴다. 인쇄에서는 먹(K100)으로 나간다.

config `assets.jobs[]` = {name, page, rect:[x0,y0,x1,y1] mm(미디어 좌표), color}.
"""
import os

from core.render_vivlio import stage  # noqa: F401  (서체·자산 배치와 같은 층)

K = 72 / 25.4


def _hex(c):
    return '#%02X%02X%02X' % tuple(int(round(v * 255)) for v in c[:3])


def svg_of(page, rect_mm, color=None):
    import fitz
    R = fitz.Rect(*[v * K for v in rect_mm])
    ox, oy = R.x0, R.y0

    def f(p):
        return f'{(p.x - ox) / K:.3f} {(p.y - oy) / K:.3f}'

    def same(a, b):
        return b is not None and abs(a.x - b.x) < 1e-3 and abs(a.y - b.y) < 1e-3

    paths = []
    for dr in page.get_drawings():
        if dr.get('fill') is None or not R.contains(dr['rect']):
            continue
        d, last = [], None
        for it in dr['items']:
            op = it[0]
            if op == 'l':
                if not same(it[1], last):
                    d.append('M' + f(it[1]))
                d.append('L' + f(it[2]))
                last = it[2]
            elif op == 'c':
                if not same(it[1], last):
                    d.append('M' + f(it[1]))
                d.append('C' + f(it[2]) + ' ' + f(it[3]) + ' ' + f(it[4]))
                last = it[4]
            elif op == 're':
                r = it[1]
                d.append(f'M{f(r.tl)}L{f(r.tr)}L{f(r.br)}L{f(r.bl)}Z')
                last = None
            elif op == 'qu':
                q = it[1]
                d.append(f'M{f(q.ul)}L{f(q.ur)}L{f(q.lr)}L{f(q.ll)}Z')
                last = None
        if not d:
            continue
        if dr.get('closePath'):
            d.append('Z')
        rule = 'evenodd' if dr.get('even_odd') else 'nonzero'
        paths.append(f'<path d="{"".join(d)}" fill="{color or _hex(dr["fill"])}" '
                     f'fill-rule="{rule}"/>')
    w, h = rect_mm[2] - rect_mm[0], rect_mm[3] - rect_mm[1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.3f} {h:.3f}" '
            f'width="{w:.3f}mm" height="{h:.3f}mm">' + ''.join(paths) + '</svg>'), len(paths)


def build(cfg, log=print):
    import fitz
    a = cfg.section("assets") or {}
    src = cfg.resolve(a.get("cover_pdf", ""))
    if not src or not os.path.exists(src):
        raise FileNotFoundError(f"표지 PDF 없음: {src}")
    out_dir = cfg.resolve(a.get("dir", "assets"))
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(src)
    res = {}
    for job in a.get("jobs") or []:
        svg, n = svg_of(doc[job.get("page", 0)], job["rect"], job.get("color"))
        if not n:
            raise ValueError(f"로고 {job['name']}: 사각형 안에 채움 패스가 없다 {job['rect']}")
        p = os.path.join(out_dir, job["name"] + ".svg")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(svg)
        res[job["name"]] = n
        log(f"[자산] {job['name']}.svg  패스 {n}개")
    return res


def missing(cfg):
    a = cfg.section("assets") or {}
    d = cfg.resolve(a.get("dir", "assets"))
    return [j["name"] for j in a.get("jobs") or []
            if not os.path.exists(os.path.join(d, j["name"] + ".svg"))]
