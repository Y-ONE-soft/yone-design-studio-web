"""한끝 계열 렌더러 — data.json → build/index.html (+ build/page.css).

지면 규칙(사용자 지시 2026-09-11):
  · 문제는 **한 면 위·아래 두 칸**에 한 덩어리씩.
  · 한 칸에 안 들어가는 덩어리는 **한 면 통째**로 쓴다:
      - 위 칸 차례였다면 → 그 면의 아래 칸을 지우고 한 면에 길게
      - 아래 칸 차례였다면 → 아래 칸은 비워 두고 다음 면으로 넘겨 한 면에 길게
  · 1면 = 앞 간지(표지 느낌 1면), 마지막 면 = 뒤 간지(1면). 파트마다 간지 2면(펼침면).
  · 파트 간지는 왼쪽(짝수) 면에서 시작, 총 면수는 `finish.multiple` 의 배수 — 모자라면 MEMO.
높이는 추정하지 않고 **잰다**(한 면에 한 덩어리 측정 조판 → heights.json).

정답 및 풀이(2026-09-13 확정 원고)는 문제 뒤 파트 — 빠른 정답 표 한 벌 + 문항별 풀이 2단 흐름.
유형(요약·어법·내용 질문·일치·배열·낱말)은 파트와 다른 축이라 **유형 칩 색**으로 가른다.

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
TYPE_NAME = {"summary": "요약문 단어 쓰기", "grammar": "어법 고쳐쓰기",
             "ask": "내용 질문 답 영작", "match": "내용 일치",
             "arrange": "본문 문장 배열 영작", "vocab": "낱말 고쳐쓰기", "etc": "서술형"}
TYPE_ORDER = ("summary", "grammar", "ask", "match", "arrange", "vocab", "etc")
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
    # 총 면수 배수 — 중철이면 4, 무선·스프링이면 2(규약)
    m["multiple"] = int((cfg.section("finish") or {}).get("multiple", 2))
    return m


# ------------------------------------------------------------------ 인라인

def esc(s):
    return html.escape(s or '')


def _plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get('t', '')
    if isinstance(x, list):
        return ''.join(_plain(i) for i in x)
    return ''


RE_SN = re.compile(r'\[\((\d{1,2})\)\]')                   # 지문 문장 번호 [(1)]
RE_SA = re.compile(r'\(([a-h])\)')                          # 낱말 문항 기호 (a)
RE_TGT = re.compile(r'\[\s*_{3,}\s*([.?!]?)\s*\]')          # 배열 빈칸 [____.]
# 요약문 빈칸 한 벌 = `(A) h _ _ _ _ (9자)` — 라벨·첫 글자·칸·글자 수를 **한 덩어리**로
# 묶어 줄이 갈리지 않게 한다(글자 수만 다음 줄로 떨어졌다).
RE_LB = re.compile(r'(?:\(([A-E])\)\s*)?\b([A-Za-z])((?:\s_)+)(?![_A-Za-z])'
                   r'(?:\s*\(\s*(\d{1,2})\s*자\s*\))?')
RE_CNT = re.compile(r'\((\d{1,2})\s*자\)')
RE_AB = re.compile(r'\(([A-E])\)')
RE_US = re.compile(r'_{3,}')
RE_WIDE = re.compile(r'　+| {3,}')
RE_SLASH = re.compile(r'\s*　/　\s*')


def _ul(n, ctx):
    if ctx == 'passage':
        return '<span class="ul tgt"></span>'
    return f'<span class="ul {"s" if n <= 8 else "m" if n <= 24 else "l"}"></span>'


def fx(t, ctx):
    """이스케이프된 글에 조판 표식을 입힌다 — 밑줄 문자는 한 글자도 인쇄하지 않는다."""
    if ctx == 'passage':
        t = RE_SN.sub(lambda m: f'<span class="sn">({m.group(1)})</span>', t)
        t = RE_SA.sub(lambda m: f'<span class="sa">({m.group(1)})</span>', t)
        t = RE_TGT.sub(lambda m: '<span class="ul tgt"></span>' + m.group(1), t)
        t = RE_US.sub(lambda m: _ul(len(m.group(0)), 'passage'), t)
    elif ctx == 'summary':
        t = RE_LB.sub(lambda m: (
            '<span class="lb">'
            + (f'<b class="ab">({m.group(1)})</b>' if m.group(1) else '')
            + f'<span class="l1">{m.group(2)}</span>'
            + '<span class="u"></span>' * m.group(3).count('_')
            + (f'<span class="cnt">{m.group(4)}자</span>' if m.group(4) else '')
            + '</span>'), t)
        t = RE_CNT.sub(lambda m: f'<span class="cnt">{m.group(1)}자</span>', t)
    elif ctx == 'ans':
        t = re.sub(r'^답\s*[:：]\s*', '<span class="alab">답</span>', t)
        t = re.sub(r'\(\s*\)', '(<span class="pgap"></span>)', t)
        t = RE_AB.sub(lambda m: f'<b class="ab">({m.group(1)})</b>', t)
        t = RE_US.sub(lambda m: _ul(len(m.group(0)), 'ans'), t)
        t = RE_WIDE.sub('<span class="agap"></span>', t)
    elif ctx == 'val':
        # 정답 두 개 사이 `　/　` → 가는 세로 괘선
        t = RE_SLASH.sub('<span class="asep"></span>', t)
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


def wordmark(s):
    """`한.서.끝.` → 글자 + 네모 점. 수정 표지의 점은 마침표가 아니라 **네모 도형**이다."""
    return ''.join('<i class="dot"></i>' if ch == '.' else esc(ch) for ch in s or '')


def src_split(s):
    """출처 → (굵게 쓸 번호, 나머지).

    `11강 2번 — 고1 23년 11월 33번` → ('11강 2번', '고1 23년 11월 33번')
    `마더텅 빈칸 추론 11강 2번`       → ('11강 2번', '마더텅 빈칸 추론')
    """
    s = (s or '').strip()
    a, sep, b = s.partition('—')
    if sep:
        return a.strip(), b.strip()
    m = re.match(r'^(.*?)\s*(\d+\s*강\s*\d+\s*번)$', s)
    if m and m.group(1):
        return m.group(2), m.group(1)
    return s, ''


def part_range(P):
    if P.get('kind') == 'answers':
        nos = [a['no'] for a in P.get('quick') or []]
    else:
        nos = [q['no'] for u in P['units'] for q in u['items']]
    return (nos[0], nos[-1]) if nos else (0, 0)


def part_meta(cfg, P):
    L = cfg.get("parts") or []
    return L[P['no'] - 1] if P['no'] - 1 < len(L) else {}


def type_chip(ty, label=None, count=None):
    c = f'<b>{count}</b>' if count is not None else ''
    return f'<span class="ty ty-{ty}">{esc(label or TYPE_NAME.get(ty, ""))}{c}</span>'


# ------------------------------------------------------------------ 문항

def wline_html(ln):
    """`답 → Babies learn language by ____.` — 도입부 + 채움 밑줄 + 한 줄 더(영작 공간)."""
    body = re.sub(r'^답\s*→\s*', '', ln)
    m = re.match(r'^(.*?)_{3,}\s*([.?!]?)\s*$', body)
    pre, end = (m.group(1).strip(), m.group(2)) if m else (body.strip(), '')
    return ('<table class="wline"><tr><td class="c0"><span class="alab">답</span></td>'
            f'<td class="c1">{esc(pre)}</td><td class="c2"></td><td class="c3">{esc(end)}</td></tr>'
            '<tr><td class="c0"></td><td class="c4" colspan="3"></td></tr></table>')


def item_html(q):
    o = ['<div class="q">']
    tag = f' <span class="tag">{esc(q["tag"])}</span>' if q.get('tag') else ''
    o.append(f'<p class="stem"><span class="no">{q["no"]:02d}</span>'
             f'{inl(q["stem"])}{tag}</p>')
    for b in q['blocks']:
        t = b['t']
        if t == 'note':
            o.append(f'<p class="note">{esc(b["text"])}</p>')
        elif t == 'passage':
            o.append('<div class="pbox">' + ''.join(
                f'<p>{inl(p, "passage")}</p>' for p in b['paras']) + '</div>')
        elif t == 'arrow':
            o.append('<div class="arrow"><i></i></div>')
        elif t == 'summary':
            o.append('<div class="summary">' + ''.join(
                f'<p>{inl(p, "summary")}</p>' for p in b['paras']) + '</div>')
        elif t == 'cond':
            items = ''.join(
                f'<p><b class="cn">{x["n"]}.</b>{esc(x["text"])}</p>' if isinstance(x, dict)
                else f'<p>{esc(x)}</p>' for x in b['items'])
            tail = ''.join(f'<p class="ct">{esc(x)}</p>' for x in b.get('tail') or [])
            o.append(f'<div class="cond"><div class="cl"><span>{esc(b.get("label") or "조건")}</span></div>'
                     f'<div class="ci">{items}{tail}</div></div>')
        elif t == 'bogi':
            o.append(f'<div class="bogi"><p class="bh"><span class="bl">{esc(b.get("label") or "보기")}</span></p>'
                     + ''.join(f'<p class="bi"><span class="bn">{x["n"]}</span>{esc(x["text"])}</p>'
                               for x in b['items']) + '</div>')
        elif t == 'ask':
            o.append(f'<p class="ask"><span class="ql">Q</span>{esc(b["text"])}</p>')
        elif t == 'words':
            o.append(f'<div class="words"><span class="wl">{esc(b["label"])}</span>'
                     + ''.join(f'<span class="w">{esc(w)}</span>' for w in b['items']) + '</div>')
        elif t == 'pieces':
            o.append(pieces_html(b))
        elif t == 'ans':
            for ln in b['lines']:
                if re.match(r'^답\s*→', ln):
                    o.append(wline_html(ln))
                else:
                    o.append(f'<div class="ans"><p>{fx(esc(ln), "ans")}</p></div>')
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
    if u['kind'] == 'set':
        lo, hi = u['range']
        c1 = (f'<span class="rng">{lo:02d}–{hi:02d}</span>'
              f'<span class="uh">{esc(u["head"])}</span>')
    else:
        q = u['items'][0]
        c1 = type_chip(q.get('type', 'etc'), q.get('label'))
    a, b = src_split(u['source'])
    c2 = f'<span class="src">{esc(b)}<b>{esc(a)}</b></span>' if a else ''
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


# ------------------------------------------------------------------ 정답 및 풀이

def answer_html(a):
    o = ['<div class="ai">',
         f'<div class="ah"><span class="an">{a["no"]:02d}</span>'
         f'<span class="av">{fx(inl(a["answer"]), "val")}</span></div>']
    for s in a['sections']:
        if s['title']:
            o.append(f'<p class="asl"><span>{esc(s["title"])}</span></p>')
        for b in s['blocks']:
            if b['t'] == 'p':
                o.append(f'<p class="ap">{inl(b["rich"])}</p>')
            elif b['t'] == 'steps':
                for k, it in enumerate(b['items']):
                    o.append(f'<p class="st"><span class="sno">{k + 1}</span>{inl(it)}</p>')
            elif b['t'] == 'rows':
                o.append('<table class="rows">')
                for r in b['rows']:
                    cells = (r + ['', '', '', ''])[:4] if len(r) <= 4 else r
                    cls = ['n', 'm', 'x', 'r'] + [''] * (len(cells) - 4)
                    o.append('<tr>' + ''.join(f'<td class="{c}">{esc(v)}</td>'
                                              for c, v in zip(cls, cells)) + '</tr>')
                o.append('</table>')
    o.append(f'<span class="mk">§A{a["no"]}§</span></div>')
    return ''.join(o)


def answers_html(cfg, P):
    o = [f'<section class="part apart p{P["no"]}">', running_html(cfg, P),
         '<div class="qk"><p class="sech">빠른 정답</p><table class="quick">']
    for a in P['quick']:
        a_, b_ = src_split(a['source'])
        o.append(f'<tr><td class="n">{a["no"]:02d}</td>'
                 f'<td class="t">{type_chip(a.get("type", "etc"), a["label"])}</td>'
                 f'<td class="v">{fx(esc(a["answer"]), "val")}</td>'
                 f'<td class="s">{esc(b_)} <b>{esc(a_)}</b></td></tr>')
    o.append('</table></div><div class="ex"><p class="sech">문항별 정답 및 풀이</p><div class="cols">')
    for a in P['answers']:
        o.append(answer_html(a))
    o.append('</div></div></section>')
    return ''.join(o)


def est_answer_pages(P):
    """정답 파트 면 수 **어림** — 첫 조판의 MEMO 계획용. 틀리면 패리티 루프가 고친다."""
    chars = sum(len(_plain(b.get('rich') or b.get('items') or '')) + 40
                for a in P['answers'] for s in a['sections'] for b in s['blocks'])
    return 2 + math.ceil(chars / 5600)


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


def memo_plan(counts, multiple=2):
    """파트별 본문 면 수 → MEMO 면 계획.

    1면(앞 간지)이 홀수라 파트 간지(2면)는 짝수 면에서 시작해야 펼침면이 된다.
    끝은 뒤 간지까지 합쳐 `multiple` 의 배수(마지막 면 짝수).
    """
    c, before = 1, []
    for n in counts:
        x = 1 if c % 2 == 0 else 0
        before.append(x)
        c += x + 2 + n
    end = (-(c + 1)) % max(2, multiple)
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
    head = data.get('head') or {}
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
    # 가운데 — 속표지로서의 정보(원고 머리의 제목·구성·범위 + 파트 목록). 표지에는 없는 자리다.
    edition = cov.get('edition') or head.get('title', '')
    target = cov.get('target') or head.get('summary', '')
    scope = cov.get('scope') or head.get('scope', '')
    o.append(f'<div class="cv-ed" style="left:{20 + b:.2f}mm;top:{168 + b:.2f}mm">'
             f'<p class="e1">{esc(edition)}</p><p class="e2">{esc(target)}</p>'
             + (f'<p class="e3">{esc(scope)}</p>' if scope else '') + '<table class="cv-parts">')
    for P in data['parts']:
        lo, hi = part_range(P)
        o.append(f'<tr class="p{P["no"]}"><td class="bar"><i></i></td>'
                 f'<td class="no">PART {P["no"]:02d}</td><td class="t">{esc(P["title"])}</td>'
                 f'<td class="r">{lo:02d} – {hi:02d}</td></tr>')
    o.append('</table></div>')
    # 수정 표지 실측: 마지막 네모 점의 오른쪽 끝 = 재단선 기준 191.26mm
    o.append(f'<div class="cv-wm" style="right:{210 - 191.26 + b:.2f}mm;top:{244.1 + b - 2.1:.2f}mm">'
             f'{wordmark(cfg.book.get("wordmark", ""))}</div>')
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
    # 수정 표지 실측(뒤표지 = 재단선 기준 x 81.5~123.0, y 264.6~272.6) — 남색 로고
    o.append(f'<img class="logo" src="assets/logo_gakin.svg" '
             f'style="left:{81.5 + b:.2f}mm;top:{264.6 + b:.2f}mm;width:41.5mm">')
    o.append('</section>')
    return ''.join(o)


def divl_html(cfg, P, m):
    """파트 간지 왼쪽 면 — 표지와 같은 돌 바탕 + 큰 파트 번호(주색)."""
    b, n = m['bleed'], P['no']
    x = m['outer'] + b
    lo, hi = part_range(P)
    meta = part_meta(cfg, P)
    if P.get('kind') == 'answers':
        foot = f'<b>{lo:02d} – {hi:02d}</b>빠른 정답  ·  문항별 풀이 {len(P["answers"])}'
    else:
        nq = sum(len(u['items']) for u in P['units'])
        foot = f'<b>{lo:02d} – {hi:02d}</b>문항 {nq}'
    o = [f'<section class="divl paper p{n}">', f'<span class="mk">§DL{n}§</span>',
         rule_motif(x, 17.1 + b, 118, 15.7),
         f'<div class="dl-part" style="left:{x + 0.3:.2f}mm;top:{52 + b:.2f}mm">PART</div>',
         f'<div class="dl-no" style="left:{x - 2.4:.2f}mm;top:{58 + b:.2f}mm">{n:02d}</div>',
         f'<div class="dl-t" style="left:{x:.2f}mm;top:{113 + b:.2f}mm">{esc(P["title"])}</div>']
    if meta.get('en'):
        o.append(f'<div class="dl-en" style="left:{x + 0.3:.2f}mm;top:{128 + b:.2f}mm">'
                 f'{esc(meta["en"])}</div>')
    o.append(f'<i class="dl-bar" style="left:{x:.2f}mm;top:{136 + b:.2f}mm"></i>')
    o.append(f'<div class="dl-foot" style="left:{x:.2f}mm;top:{268 + b:.2f}mm">{foot}</div>')
    o.append(f'<div class="dl-wm" style="right:{m["inner"] + b:.2f}mm;top:{266.4 + b:.2f}mm">'
             f'{wordmark(cfg.book.get("wordmark", ""))}</div>')
    o.append('</section>')
    return ''.join(o)


def divr_html(cfg, data, P, m):
    """파트 간지 오른쪽 면 — 주색 띠 + 구성 칩 + 목록(왼쪽 면과 넣는 것이 다르다)."""
    b, n = m['bleed'], P['no']
    x = m['inner'] + b
    answers = P.get('kind') == 'answers'
    if answers:
        secs = collections.Counter(s['title'] for a in P['answers'] for s in a['sections'] if s['title'])
        chips = ''.join(f'<span class="chip">{esc(k)}<b>{v}</b></span>' for k, v in secs.items())
        head_k = '정답 및 풀이 구성'
    else:
        types = collections.Counter(q['type'] for u in P['units'] for q in u['items'])
        chips = ''.join(type_chip(k, count=types[k]) for k in TYPE_ORDER if types.get(k))
        head_k = (data.get('head') or {}).get('scope', '')
    o = [f'<section class="divr p{n}">', f'<span class="mk">§DR{n}§</span>',
         f'<div class="dr-field" style="height:{64 + b:.2f}mm"></div>',
         f'<div class="dr-head" style="left:{x:.2f}mm;top:{21 + b:.2f}mm;width:{m["text_w"]:.2f}mm">'
         f'<p class="k">PART {n:02d}</p><p class="t">{esc(P["title"])}</p>'
         + (f'<p class="sc">{esc(head_k)}</p>' if head_k else '')
         + f'<p class="chips">{chips}</p></div>',
         f'<div class="dr-body" style="left:{x:.2f}mm;top:{78 + b:.2f}mm;width:{m["text_w"]:.2f}mm">']
    if answers:
        # 유형별 문항 번호 — 풀이를 유형으로 찾아가는 색인(유형 칩 색의 범례이기도 하다)
        by = collections.defaultdict(list)
        for a in P['quick']:
            by[a.get('type', 'etc')].append(a['no'])
        o.append('<p class="dr-h">유형별 문항<span>같은 색 칩이 문제지·풀이에 붙어 있다</span></p>'
                 '<table class="tyidx">')
        labels = {a.get('type', 'etc'): a['label'] for a in P['quick']}
        for k in TYPE_ORDER:
            if by.get(k):
                o.append(f'<tr><td class="t">{type_chip(k, labels.get(k))}</td><td class="v">'
                         + ''.join(f'<span>{v:02d}</span>' for v in by[k]) + '</td></tr>')
        o.append('</table>')
    else:
        U = P['units']
        k = math.ceil(len(U) / 2)
        cols = [U[:k], U[k:]]
        o.append('<p class="dr-h">문항 목록<span>문항 번호 · 출처 · 유형</span></p>'
                 f'<table class="toc{" dense" if k > 16 else ""}">')
        for r in range(k):
            cells = []
            for col in cols:
                if r < len(col):
                    u = col[r]
                    a, s2 = src_split(u['source'])
                    nos = [q['no'] for q in u['items']]
                    lab = f'{nos[0]:02d}–{nos[-1]:02d}' if len(nos) > 1 else f'{nos[0]:02d}'
                    ty = data_short(u['items'][0].get('type'))
                    cells.append(f'<td class="n">{lab}</td><td class="s"><b>{esc(a)}</b>{esc(s2)}</td>'
                                 f'<td class="y">{esc(ty)}</td>')
                else:
                    cells.append('<td class="n"></td><td class="s"></td><td class="y"></td>')
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


def data_short(ty):
    from core.render_vivlio.series.hankkeut.data import TYPE_SHORT
    return TYPE_SHORT.get(ty, '')


def memo_html(pno):
    return (f'<section class="memo p{pno}"><span class="mk">§MEMO§</span>'
            '<div class="ml">' + '<i></i>' * 25 + '</div></section>')


def running_html(cfg, P):
    n, bk = P['no'], cfg.book
    return (f'<div class="hdrL p{n}"><span class="pb">PART {n:02d}</span>'
            f'<span class="pt">{esc(P["title"])}</span></div>'
            f'<div class="hdrR p{n}"><span class="ed">{esc(bk.get("header", ""))}</span>'
            f'<span class="wm">{wordmark(bk.get("wordmark", ""))}</span></div>'
            f'<div class="footL p{n}"><span class="pg"></span><span class="bar"></span>'
            f'<span class="ft">{esc(bk.get("footer", ""))}</span></div>'
            f'<div class="footR p{n}"><span class="ft">PART {n:02d}&#8195;{esc(P["title"])}</span>'
            f'<span class="bar"></span><span class="pg"></span></div>')


def body_html(cfg, P, pages):
    o = [f'<section class="part p{P["no"]}">', running_html(cfg, P)]
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
            if P.get('kind') == 'answers':
                continue
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
        if P.get('kind') == 'answers':
            o.append(answers_html(cfg, P))
        else:
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
        f.write(palette.css(len(data['parts'])) + palette.type_css() + page_css(m))
    lay = {P['no']: layout(P['units'], heights, m) for P in data['parts']
           if P.get('kind') != 'answers'}
    if mode != 'measure' and memo is None:
        memo = memo_plan([est_answer_pages(P) if P.get('kind') == 'answers'
                          else body_pages(lay[P['no']], heights, m) for P in data['parts']],
                         m['multiple'])
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
