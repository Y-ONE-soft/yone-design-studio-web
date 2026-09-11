"""한끝 계열 렌더러 — data.json → build/index.html (+ build/page.css).

지면 규칙(사용자 지시 2026-09-11):
  · 문제는 **한 면 위·아래 두 칸**에 한 덩어리씩(세트는 지문 + 딸린 문항이 한 덩어리).
  · 한 칸에 안 들어가는 덩어리는 **한 면 통째**로 쓴다:
      - 위 칸 차례였다면 → 그 면의 아래 칸을 지우고 한 면에 길게
      - 아래 칸 차례였다면 → 아래 칸은 비워 두고 다음 면으로 넘겨 한 면에 길게
  · 1면 = 앞 간지(표지 느낌 1면), 마지막 면 = 뒤 간지(1면). 파트마다 간지 2면(펼침면).
  · 파트 간지는 왼쪽(짝수) 면에서 시작, 총 면수 4의 배수, 마지막 면 짝수 — 모자라면 MEMO.
높이는 추정하지 않고 **잰다**(한 면에 한 덩어리 측정 조판 → heights.json).

`@page` 판면·머리 괘선은 치수(config.metrics)에서 굽는다(page.css) — CSS 와 배치 계산이
같은 수를 보게. 테마(themes/hankkeut.css)는 부품 모양만 갖는다.
"""
import collections
import html
import json
import math
import os
import re

from core.render_vivlio import stage
from core.render_vivlio.series.hankkeut import palette

DEFAULT_METRICS = {
    "top": 30.0,      # 재단선 → 판면 위. 머리 이중 괘선은 재단선에서 19.5mm
    "bottom": 20.0,
    "inner": 20.0,    # 안쪽(제본) 여백
    "outer": 17.0,    # 바깥 여백 — 글자는 재단선에서 5mm 안쪽 규약을 넉넉히 넘는다
    "slot": 119.5,    # 반 면 칸
    "gap": 7.0,       # 두 칸 사이(가운데 괘선 자리)
}
RULE_Y = 19.5          # 머리 이중 괘선(재단선 기준) — 표지 꺾쇠 모티프
TYPE_NAME = {"grammar": "어법 고쳐쓰기", "summary": "요약문 빈칸",
             "arrange": "배열 영작", "etc": "서술형"}
MEASURE_H = 1400.0     # 측정 조판의 면 높이 — 한 덩어리가 한 면을 넘어도 한 면에 잰다

# 표지(한문끝) 실측 — 앞표지 격자 글자(재단선 기준, 25pt). 행 기준선이 고르지 않은 것도 실측대로.
COVER_COLS = [19.86 + 40.745 * k for k in range(5)]
COVER_ROWS = [57.10, 97.87, 140.59]


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    pg = cfg.page
    m["bleed"] = float(pg.get("bleed", 3))
    m["W"], m["H"] = float(pg.get("width", 210)), float(pg.get("height", 297))
    m["body_h"] = m["H"] - m["top"] - m["bottom"]
    # 칸 두 개 합보다 조금 작게 — 딱 맞추면 반올림으로 둘째 칸이 다음 면으로 밀린다
    m["pg_h"] = m["body_h"] - 0.8
    m["full"] = m["pg_h"]
    m["text_w"] = m["W"] - m["inner"] - m["outer"]
    m["body_top"] = m["bleed"] + m["top"]
    return m


# ------------------------------------------------------------------ 인라인

def esc(s):
    return html.escape(s or '')


RE_SN = re.compile(r'\[\((\d{1,2})\)\]')                   # 지문 문장 번호 [(1)]
RE_LB = re.compile(r'\b([A-Za-z])((?:\s_)+)(?![_A-Za-z])')  # 첫 글자 + 글자 칸 h _ _ _
RE_CNT = re.compile(r'\((\d{1,2})\s*자\)')
RE_AB = re.compile(r'\(([A-E])\)')
RE_US = re.compile(r'_{3,}')
RE_WIDE = re.compile(r'　+| {3,}')


def _ul(n, ctx):
    if ctx == 'passage':
        return '<span class="ul tgt"></span>'
    return f'<span class="ul {"s" if n <= 8 else "m" if n <= 24 else "l"}"></span>'


def fx(t, ctx):
    """이스케이프된 글에 조판 표식을 입힌다 — 밑줄 문자는 한 글자도 인쇄하지 않는다."""
    if ctx == 'passage':
        t = RE_SN.sub(lambda m: f'<span class="sn">({m.group(1)})</span>', t)
        t = RE_US.sub(lambda m: _ul(len(m.group(0)), 'passage'), t)
    elif ctx == 'summary':
        t = RE_LB.sub(lambda m: ('<span class="lb"><span class="l1">' + m.group(1)
                                 + '</span>' + '<span class="u"></span>' * m.group(2).count('_')
                                 + '</span>'), t)
        t = RE_CNT.sub(lambda m: f'<span class="cnt">{m.group(1)}자</span>', t)
        t = RE_AB.sub(lambda m: f'<b class="ab">({m.group(1)})</b>', t)
    elif ctx == 'ans':
        t = re.sub(r'^답\s*[:：]\s*', '<span class="alab">답</span>', t)
        t = re.sub(r'\(\s*\)', '(<span class="pgap"></span>)', t)
        t = RE_AB.sub(lambda m: f'<b class="ab">({m.group(1)})</b>', t)
        t = RE_US.sub(lambda m: _ul(len(m.group(0)), 'ans'), t)
        t = RE_WIDE.sub('<span class="agap"></span>', t)
    return t


def inl(x, ctx='plain'):
    if x is None:
        return ''
    if isinstance(x, str):
        return fx(esc(x), ctx)
    if isinstance(x, dict):
        t = fx(esc(x.get('t', '')), ctx)
        if x.get('u'):
            t = f'<u>{t}</u>'
        if x.get('b'):
            t = f'<b>{t}</b>'
        if x.get('i'):
            t = f'<i>{t}</i>'
        return t
    return ''.join(inl(i, ctx) for i in x)


def src_split(s):
    """`11강 2번 — 고1 23년 11월 33번` → ('11강 2번', '고1 23년 11월 33번')"""
    a, sep, b = (s or '').partition('—')
    return (a.strip(), b.strip()) if sep else ((s or '').strip(), '')


def part_range(P):
    nos = [q['no'] for u in P['units'] for q in u['items']]
    return (nos[0], nos[-1]) if nos else (0, 0)


def part_meta(cfg, P):
    L = cfg.get("parts") or []
    return L[P['no'] - 1] if P['no'] - 1 < len(L) else {}


# ------------------------------------------------------------------ 덩어리

def item_html(q):
    o = ['<div class="q">']
    tag = f' <span class="tag">{esc(q["tag"])}</span>' if q.get('tag') else ''
    o.append(f'<p class="stem"><span class="no">{q["no"]:02d}</span>'
             f'{esc(q["stem"])}{tag}</p>')
    for b in q['blocks']:
        t = b['t']
        if t == 'note':
            o.append(f'<p class="note">{esc(b["text"])}</p>')
        elif t == 'passage':
            o.append('<div class="pbox">' + ''.join(
                f'<p>{inl(p, "passage")}</p>' for p in b['paras']) + '</div>')
        elif t == 'cond':
            o.append('<div class="cond"><div class="cl"><span>조건</span></div>'
                     '<div class="ci">' + ''.join(f'<p>{esc(x)}</p>' for x in b['items'])
                     + '</div></div>')
        elif t == 'summary':
            o.append('<div class="summary">' + ''.join(
                f'<p>{inl(p, "summary")}</p>' for p in b['paras']) + '</div>')
        elif t == 'pieces':
            o.append(pieces_html(b))
        elif t == 'ans':
            o.append('<div class="ans">' + ''.join(
                f'<p>{fx(esc(ln), "ans")}</p>' for ln in b['lines']) + '</div>')
    o.append('</div>')
    return ''.join(o)


def pieces_html(b):
    cols = max(1, b.get('cols') or 4)
    cells = b['cells']
    w = 100.0 / cols
    o = ['<table class="pieces">']
    for i in range(0, len(cells), cols):
        row = cells[i:i + cols]
        o.append('<tr>' + ''.join(
            f'<td style="width:{w:.2f}%"><span class="pn">'
            f'{c["n"] if c["n"] is not None else ""}</span>{inl(c["text"])}</td>'
            for c in row) + '<td class="empty"></td>' * (cols - len(row)) + '</tr>')
    o.append('</table>')
    return ''.join(o)


def unit_html(u):
    o = [f'<div class="unit u-{u["kind"]}">']
    c1 = ''
    if u['kind'] == 'set':
        lo, hi = u['range']
        c1 = (f'<span class="rng">{lo:02d}–{hi:02d}</span>'
              f'<span class="uh">{esc(u["head"])}</span>')
    a, b = src_split(u['source'])
    c2 = f'<span class="src"><b>{esc(a)}</b>{esc(b)}</span>' if a else ''
    o.append(f'<div class="uhead"><div class="c1">{c1}</div><div class="c2">{c2}</div></div>')
    if u['passage']:
        o.append('<div class="pbox">' + ''.join(
            f'<p>{inl(p, "passage")}</p>' for p in u['passage']) + '</div>')
    for n in u.get('notes') or []:
        o.append(f'<p class="note">{esc(n)}</p>')
    for q in u['items']:
        o.append(item_html(q))
    o.append(f'<span class="mk">§E{u["id"]}§</span></div>')
    return ''.join(o)


# ------------------------------------------------------------------ 배치

def layout(units, heights, m):
    """[(면 종류, [(칸, 덩어리)])] — 칸 ∈ top/bot/full, 면 종류 ∈ half/full/over."""
    pages, pos = [], 'top'
    for u in units:
        h = heights.get(u['id'])
        if h is not None and h > m['slot']:
            # 위 칸 차례 → 이 면을 통째로 / 아래 칸 차례 → 아래 칸 비우고 다음 면 통째로
            pages.append(('over' if h > m['full'] else 'full', [('full', u)]))
            pos = 'top'
        elif pos == 'top':
            pages.append(('half', [('top', u)]))
            pos = 'bot'
        else:
            pages[-1][1].append(('bot', u))
            pos = 'top'
    return pages


def body_pages(pages, heights, m):
    n = 0
    for kind, slots in pages:
        if kind == 'over':
            n += math.ceil(heights.get(slots[0][1]['id'], m['full']) / m['full'])
        else:
            n += 1
    return n


def memo_plan(counts):
    """파트별 본문 면 수 → MEMO 면 계획.

    1면(앞 간지)이 홀수라 파트 간지(2면)는 짝수 면에서 시작해야 펼침면이 된다.
    끝은 뒤 간지까지 합쳐 4의 배수(마지막 면 짝수).
    """
    c, before = 1, []
    for n in counts:
        x = 1 if c % 2 == 0 else 0
        before.append(x)
        c += x + 2 + n
    end = (3 - c % 4) % 4
    return {"before": before, "end": end, "total": c + end + 1}


# ------------------------------------------------------------------ 간지 · 앞뒤

def rule_motif(x, y, w, tick):
    """표지의 굵은+가는 이중 괘선에 세로 꺾쇠."""
    return (f'<i class="rl" style="left:{x:.2f}mm;top:{y:.2f}mm;width:{w:.2f}mm"></i>'
            f'<i class="rl2" style="left:{x:.2f}mm;top:{y + 2.4:.2f}mm;width:{w:.2f}mm"></i>'
            f'<i class="tk" style="left:{x:.2f}mm;top:{y:.2f}mm;height:{tick:.2f}mm"></i>')


def front_html(cfg, data, m):
    b = m['bleed']
    cov = cfg.section('cover') or {}
    grid = cov.get('grid') or []
    acc = {tuple(a) for a in cov.get('accent') or []}
    o = ['<section class="front paper">', '<span class="mk">§FRONT§</span>',
         rule_motif(20 + b, 17.1 + b, 171.1, 15.7)]
    for r, row in enumerate(grid[:3]):
        for c, ch in enumerate(row[:5]):
            x, y = COVER_COLS[c] + b, COVER_ROWS[r] + b
            a = (r, c) in acc
            o.append(f'<span class="cg{" ac" if a else ""}" '
                     f'style="left:{x:.2f}mm;top:{y - 7.9:.2f}mm">{esc(ch)}</span>')
            if a:
                o.append(f'<i class="sl" style="left:{x + 0.59:.2f}mm;'
                         f'top:{y - 11.63:.2f}mm"></i>')
    # 가운데 — 속표지로서의 정보(판 표기 + 파트 목록). 표지에는 없는 자리다.
    o.append(f'<div class="cv-ed" style="left:{20 + b:.2f}mm;top:{170 + b:.2f}mm">'
             f'<p class="e1">{esc(cov.get("edition", ""))}</p>'
             f'<p class="e2">{esc(cov.get("target", ""))}</p><table class="cv-parts">')
    for P in data['parts']:
        lo, hi = part_range(P)
        o.append(f'<tr class="p{P["no"]}"><td class="bar"><i></i></td>'
                 f'<td class="no">PART {P["no"]:02d}</td><td class="t">{esc(P["title"])}</td>'
                 f'<td class="r">{lo:02d} – {hi:02d}</td></tr>')
    o.append('</table></div>')
    o.append(f'<div class="cv-wm" style="right:{16.1 + b:.2f}mm;top:{244.1 + b - 2.1:.2f}mm">'
             f'{esc(cfg.book.get("wordmark", ""))}</div>')
    o.append(f'<i class="rl" style="left:{62.4 + b:.2f}mm;top:{274.6 + b:.2f}mm;width:128.3mm"></i>')
    o.append(f'<img class="logo" src="assets/logo_books.svg" '
             f'style="left:{20 + b:.2f}mm;top:{269.1 + b:.2f}mm;width:34.2mm">')
    o.append('</section>')
    return ''.join(o)


def back_html(cfg, m):
    b = m['bleed']
    cov = cfg.section('cover') or {}
    o = ['<section class="back paper">', '<span class="mk">§BACK§</span>',
         f'<div class="bk-tl" style="top:{101.2 + b - 1.5:.2f}mm">'
         + ''.join(f'<p>{esc(t)}</p>' for t in cov.get('tagline') or []) + '</div>',
         f'<div class="bk-wm" style="top:{122.2 + b - 1.6:.2f}mm">{esc(cfg.book.get("title", ""))}</div>']
    if cov.get('colophon'):
        o.append(f'<div class="bk-colo" style="top:{240 + b:.2f}mm">{esc(cov["colophon"])}</div>')
    o.append(f'<img class="logo" src="assets/logo_gakin.svg" '
             f'style="left:{86.5 + b:.2f}mm;top:{262.2 + b:.2f}mm;width:37mm">')
    o.append('</section>')
    return ''.join(o)


def divl_html(cfg, P, m):
    """파트 간지 왼쪽 면 — 표지와 같은 돌 바탕 + 큰 파트 번호(주색)."""
    b, n = m['bleed'], P['no']
    x = m['outer'] + b
    lo, hi = part_range(P)
    meta = part_meta(cfg, P)
    nq = sum(len(u['items']) for u in P['units'])
    o = [f'<section class="divl paper p{n}">', f'<span class="mk">§DL{n}§</span>',
         rule_motif(x, 17.1 + b, 118, 15.7),
         f'<div class="dl-part" style="left:{x + 0.3:.2f}mm;top:{52 + b:.2f}mm">PART</div>',
         f'<div class="dl-no" style="left:{x - 2.4:.2f}mm;top:{58 + b:.2f}mm">{n:02d}</div>',
         f'<div class="dl-t" style="left:{x:.2f}mm;top:{113 + b:.2f}mm">{esc(P["title"])}</div>']
    if meta.get('en'):
        o.append(f'<div class="dl-en" style="left:{x + 0.3:.2f}mm;top:{128 + b:.2f}mm">'
                 f'{esc(meta["en"])}</div>')
    o.append(f'<i class="dl-bar" style="left:{x:.2f}mm;top:{136 + b:.2f}mm"></i>')
    o.append(f'<div class="dl-foot" style="left:{x:.2f}mm;top:{268 + b:.2f}mm">'
             f'<b>{lo:02d} – {hi:02d}</b>문항 {nq}  ·  지문 {len(P["units"])}</div>')
    o.append(f'<div class="dl-wm" style="right:{m["inner"] + b:.2f}mm;top:{266.4 + b:.2f}mm">'
             f'{esc(cfg.book.get("wordmark", ""))}</div>')
    o.append('</section>')
    return ''.join(o)


def divr_html(cfg, data, P, m):
    """파트 간지 오른쪽 면 — 주색 띠 + 구성 칩 + 지문 목록(왼쪽 면과 넣는 것이 다르다)."""
    b, n = m['bleed'], P['no']
    x = m['inner'] + b
    types = collections.Counter(q['type'] for u in P['units'] for q in u['items'])
    o = [f'<section class="divr p{n}">', f'<span class="mk">§DR{n}§</span>',
         f'<div class="dr-field" style="height:{64 + b:.2f}mm"></div>',
         f'<div class="dr-head" style="left:{x:.2f}mm;top:{21 + b:.2f}mm;width:{m["text_w"]:.2f}mm">'
         f'<p class="k">PART {n:02d}</p><p class="t">{esc(P["title"])}</p><p class="chips">'
         + ''.join(f'<span class="chip">{TYPE_NAME[k]}<b>{v}</b></span>' for k, v in types.items())
         + '</p></div>',
         f'<div class="dr-body" style="left:{x:.2f}mm;top:{78 + b:.2f}mm;width:{m["text_w"]:.2f}mm">',
         '<p class="dr-h">지문 목록<span>문항 번호 · 출처</span></p>']
    U = P['units']
    k = math.ceil(len(U) / 2)
    cols = [U[:k], U[k:]]
    o.append(f'<table class="toc{" dense" if k > 16 else ""}">')
    for r in range(k):
        cells = []
        for col in cols:
            if r < len(col):
                u = col[r]
                a, s2 = src_split(u['source'])
                nos = [q['no'] for q in u['items']]
                lab = f'{nos[0]:02d}–{nos[-1]:02d}' if len(nos) > 1 else f'{nos[0]:02d}'
                cells.append(f'<td class="n">{lab}</td><td class="s"><b>{esc(a)}</b>{esc(s2)}</td>')
            else:
                cells.append('<td class="n"></td><td class="s"></td>')
        o.append('<tr>' + cells[0] + '<td class="g"></td>' + cells[1] + '</tr>')
    o.append('</table>')
    intro = data.get('intro') or {}
    if n == 1 and intro.get('lines') and k <= 16:
        o.append('<div class="intro">'
                 f'<p class="ih">{esc(intro.get("heading") or "")}</p>'
                 + ''.join(f'<p class="il"><span class="inum">{i + 1}</span>{esc(t)}</p>'
                           for i, t in enumerate(intro['lines'])) + '</div>')
    o.append('</div></section>')
    return ''.join(o)


def memo_html(pno):
    return (f'<section class="memo p{pno}"><span class="mk">§MEMO§</span>'
            '<div class="ml">' + '<i></i>' * 25 + '</div></section>')


def body_html(cfg, P, pages):
    n, bk = P['no'], cfg.book
    o = [f'<section class="part p{n}">',
         f'<div class="hdrL p{n}"><span class="pb">PART {n:02d}</span>'
         f'<span class="pt">{esc(P["title"])}</span></div>',
         f'<div class="hdrR p{n}"><span class="ed">{esc(bk.get("header", ""))}</span>'
         f'<span class="wm">{esc(bk.get("wordmark", ""))}</span></div>',
         f'<div class="footL p{n}"><span class="pg"></span><span class="bar"></span>'
         f'<span class="ft">{esc(bk.get("footer", ""))}</span></div>',
         f'<div class="footR p{n}"><span class="ft">PART {n:02d}&#8195;{esc(P["title"])}</span>'
         f'<span class="bar"></span><span class="pg"></span></div>']
    for kind, slots in pages:
        o.append(f'<div class="pg {kind}">')
        for pos, u in slots:
            if pos == 'bot':
                o.append('<div class="sep"></div>')
            o.append(f'<div class="slot {pos}">{unit_html(u)}</div>')
        o.append('</div>')
    o.append('</section>')
    return ''.join(o)


# ------------------------------------------------------------------ 판면 CSS

def page_css(m):
    b = m['bleed']
    W, H = m['W'] + 2 * b, m['H'] + 2 * b
    top, bot = b + m['top'], b + m['bottom']
    Lm, Rm = b + m['outer'], b + m['inner']     # 왼쪽 면: 바깥이 왼쪽
    tw, ry = m['text_w'], b + RULE_Y

    def rules(x):
        k = 'linear-gradient(#231f20,#231f20) no-repeat'
        return (f'{k} {x:.2f}mm {ry:.2f}mm / 0.3mm 8mm, '
                f'{k} {x:.2f}mm {ry:.2f}mm / {tw:.2f}mm 0.3mm, '
                f'{k} {x:.2f}mm {ry + 2.1:.2f}mm / {tw:.2f}mm 0.18mm')

    hd = f'width:{tw:.2f}mm; height:{top:.2f}mm; vertical-align:bottom;'
    ft = f'width:{tw:.2f}mm; height:{bot:.2f}mm; vertical-align:top;'
    memo = ('content:"MEMO"; padding-bottom:12.4mm; font:700 9pt/1 Gm; color:#6D6E71;'
            ' letter-spacing:0.14em;')
    return f"""
/* 판면 — metrics 에서 굽는다(배치 계산과 같은 수) */
@page {{ size: {W:.2f}mm {H:.2f}mm; margin: {top:.2f}mm {Rm:.2f}mm {bot:.2f}mm {Rm:.2f}mm; }}
@page :left  {{ margin-left: {Lm:.2f}mm; margin-right: {Rm:.2f}mm; }}
@page :right {{ margin-left: {Rm:.2f}mm; margin-right: {Lm:.2f}mm; }}
@page body:left {{
  background: {rules(Lm)};
  @top-left {{ content: element(hdrL); {hd} }}
  @bottom-left {{ content: element(footL); {ft} }}
}}
@page body:right {{
  background: {rules(Rm)};
  @top-right {{ content: element(hdrR); {hd} }}
  @bottom-right {{ content: element(footR); {ft} }}
}}
@page memo:left {{
  background: {rules(Lm)};
  @top-left {{ {memo} padding-left:3.4mm; {hd} text-align:left; }}
}}
@page memo:right {{
  background: {rules(Rm)};
  @top-right {{ {memo} {hd} text-align:right; }}
}}
@page front {{ margin: 0; }}
@page back {{ margin: 0; }}
@page divl {{ margin: 0; }}
@page divr {{ margin: 0; }}
.front, .back, .divl, .divr {{ width: {W:.2f}mm; height: {H - 0.4:.2f}mm; }}
.pg {{ height: {m['pg_h']:.2f}mm; }}
.slot {{ height: {m['slot']:.2f}mm; }}
.sep {{ height: {m['gap']:.2f}mm; }}
.sep::before {{ top: {m['gap'] / 2 - 0.05:.2f}mm; }}
"""


# ------------------------------------------------------------------ 문서

def document(cfg, data, heights, mode=None, memo=None):
    m = metrics_of(cfg)
    o = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         f'<title>{esc(cfg.book.get("title", ""))}</title>',
         '<link rel="stylesheet" href="theme.css">',
         '<link rel="stylesheet" href="page.css">',
         stage.BOOK_CSS_LINKS]
    parts = data['parts']
    if mode == 'measure':
        o.append(f'<style>@page {{ size: {m["W"] + 2 * m["bleed"]:.2f}mm {MEASURE_H:.0f}mm; }}'
                 '@page meas { margin-bottom: 5mm; }'
                 '.meas { page: meas; break-before: page; }'
                 '.meas:first-child { break-before: auto; }</style></head><body>')
        for P in parts:
            for u in P['units']:
                o.append(f'<section class="meas p{P["no"]}">{unit_html(u)}</section>')
        o.append('</body></html>')
        return '\n'.join(o)

    o.append('</head><body>')
    o.append(front_html(cfg, data, m))
    for i, P in enumerate(parts):
        for _ in range(memo['before'][i]):
            o.append(memo_html(P['no']))
        o.append(divl_html(cfg, P, m))
        o.append(divr_html(cfg, data, P, m))
        o.append(body_html(cfg, P, layout(P['units'], heights, m)))
    for _ in range(memo['end']):
        o.append(memo_html(parts[-1]['no'] if parts else 1))
    o.append(back_html(cfg, m))
    o.append('</body></html>')
    return '\n'.join(o)


def write(cfg, data, build_dir, heights=None, mode=None, memo=None, log=None):
    """→ (html 경로, MEMO 계획). 본 조판이면 배치표(layout.json)도 남긴다 — 검수가 본다."""
    m = metrics_of(cfg)
    heights = heights or {}
    os.makedirs(build_dir, exist_ok=True)
    with open(os.path.join(build_dir, 'page.css'), 'w', encoding='utf-8') as f:
        f.write(palette.css(len(data['parts'])) + page_css(m))
    lay = {P['no']: layout(P['units'], heights, m) for P in data['parts']}
    if mode != 'measure' and memo is None:
        memo = memo_plan([body_pages(lay[P['no']], heights, m) for P in data['parts']])
    text = document(cfg, data, heights, mode, memo)
    out = os.path.join(build_dir, 'measure.html' if mode == 'measure' else 'index.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    if mode != 'measure':
        with open(os.path.join(build_dir, 'layout.json'), 'w', encoding='utf-8') as f:
            json.dump({'memo': memo, 'layout': {
                str(k): [[kind, [[pos, u['id']] for pos, u in slots]] for kind, slots in v]
                for k, v in lay.items()}}, f, ensure_ascii=False, indent=1)
    if log:
        if mode == 'measure':
            log(f'[렌더] measure.html {len(text):,} bytes  [측정용]')
        else:
            kinds = collections.Counter(k for v in lay.values() for k, _ in v)
            log(f'[렌더] index.html {len(text):,} bytes · 높이 {len(heights)} 반영 · '
                f'반 면 {kinds["half"]} / 한 면 {kinds["full"]} / 넘침 {kinds["over"]} · '
                f'MEMO 앞{memo["before"]} 끝{memo["end"]} · 예상 {memo["total"]}면')
    return out, memo
