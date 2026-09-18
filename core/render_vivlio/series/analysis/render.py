# -*- coding: utf-8 -*-
"""분석본 계열 렌더러 — data.json → build/index.html.

지면(완성본 PDF 실측):
    앞표지 1P  → `front`
    지문마다 짝면(왼쪽 구문분석) + 홀면(오른쪽 문항+FLOW·VOCA) 두 면

머리(왼쪽면) 청록 머리띠, 오른쪽 하단 러닝 푸터 「모의고사 회차 N번」.
색·서체·치수는 themes/analysis.css. 짝면부터 시작하도록 `break-before:left` 로 붙인다.
"""
import html
import os


def esc(s):
    return html.escape(s or "")


def _p(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return esc(x)
    if isinstance(x, list):
        return "".join(_p(i) for i in x)
    if isinstance(x, dict):
        return esc(x.get("t", ""))
    return ""


def _passage_html(passage):
    """구문분석 지문 — 문단마다 <p>, 조각마다 <span>."""
    out = []
    for para in passage or []:
        pieces = []
        for run in para.get("runs") or []:
            t = esc(run.get("t", ""))
            sv = run.get("sv")
            if sv:
                t = f'{t}<sup class="sv">{esc(sv)}</sup>'
            pieces.append(t)
        out.append(f'<p class="pl">{"".join(pieces)}</p>')
    return "\n".join(out)


def _list_col(items, cls):
    lis = "\n".join(f'<li>{_p(x)}</li>' for x in (items or []))
    return f'<ul class="{cls}">{lis}</ul>' if lis else ""


def _voca_table(items):
    if not items:
        return ""
    rows = []
    for it in items:
        rows.append(f'<tr><td class="w">{_p(it.get("w"))}</td>'
                    f'<td class="p">{_p(it.get("p"))}</td>'
                    f'<td class="m">{_p(it.get("m"))}</td></tr>')
    return f'<table class="voca">{"".join(rows)}</table>'


def _chk_row(items):
    if not items:
        return ""
    cells = "".join(f'<span class="chk">{_p(x)}</span>' for x in items)
    return f'<div class="chks">{cells}</div>'


def _front(book):
    return (
        '<section class="front">'
        f'<div class="fr-school">{esc(book.get("school", ""))}</div>'
        f'<div class="fr-series">{esc(book.get("series_label", "스텝업 분석본"))}</div>'
        f'<div class="fr-vol">{esc(str(book.get("subtitle", "")))}</div>'
        f'<div class="fr-range">{esc(book.get("range", ""))}</div>'
        '</section>'
    )


def _even(p):
    """짝면(왼쪽) — 구문분석."""
    band = esc(p.get("band", ""))
    return (
        '<section class="even">'
        f'<div class="band">{band}</div>'
        f'<div class="grampt">{_list_col(p.get("grampt"), "grampt-list")}</div>'
        f'<div class="passage">{_passage_html(p.get("passage"))}</div>'
        f'<div class="trans">{_p(p.get("translation"))}</div>'
        '</section>'
    )


def _odd(p):
    """홀면(오른쪽) — 문항 + FLOW + 기출포인트 + VOCA."""
    q = p.get("question") or {}
    choices = "".join(f'<li>{_p(c)}</li>' for c in (q.get("choices") or []))
    return (
        '<section class="odd">'
        f'<div class="tline"><span class="lab">주제</span>{_p(p.get("topic"))}</div>'
        f'<div class="sline"><span class="lab">요약</span>{_p(p.get("summary"))}</div>'
        '<div class="row">'
        '  <div class="qbox">'
        '    <div class="qhead">핵심기출문제</div>'
        f'    <div class="stem">{_p(q.get("stem"))}</div>'
        f'    <div class="qp">{_p(q.get("passage"))}</div>'
        f'    <ol class="choices">{choices}</ol>'
        '  </div>'
        '  <div class="flow">'
        '    <div class="fhead">FLOW NOTE</div>'
        '    <div class="fspace"></div>'
        '  </div>'
        '</div>'
        f'{_chk_row(p.get("chks"))}'
        f'{_voca_table(p.get("voca"))}'
        '</section>'
    )


def write(cfg, d, bd, log=None):
    os.makedirs(bd, exist_ok=True)
    book = d.get("book") or {}
    parts = [_front(book)]
    for p in d.get("passages") or []:
        parts.append(_even(p))
        parts.append(_odd(p))
    body = "\n".join(parts)
    title = esc(book.get("title", "분석본"))
    html_doc = (
        '<!doctype html><html lang="ko"><head>'
        '<meta charset="utf-8">'
        f'<title>{title}</title>'
        '<link rel="stylesheet" href="page.css">'
        '<link rel="stylesheet" href="_base.css">'
        '<link rel="stylesheet" href="theme.css">'
        '<link rel="stylesheet" href="overrides.css">'
        '</head><body>\n' + body + '\n</body></html>\n'
    )
    hp = os.path.join(bd, "index.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(html_doc)
    # 판면 치수 — page.css (없으면 테마 CSS 안의 @page 를 쓴다)
    _write_page_css(cfg, bd)
    if log:
        log(f"[분석본] HTML {len(d.get('passages') or [])}편 → {hp}")
    return hp


def _write_page_css(cfg, bd):
    pg = cfg.page
    W, H = float(pg["width"]), float(pg["height"])
    bleed = float(pg.get("bleed", 3))
    css = (
        f'@page {{ size: {W}mm {H}mm; margin: 0; bleed: {bleed}mm; marks: crop; }}\n'
        f':root {{ --page-w: {W}mm; --page-h: {H}mm; --bleed: {bleed}mm; }}\n'
    )
    with open(os.path.join(bd, "page.css"), "w", encoding="utf-8") as f:
        f.write(css)
