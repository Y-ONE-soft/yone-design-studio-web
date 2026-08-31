# -*- coding: utf-8 -*-
"""포켓북 HTML 생성 — 지문 데이터 → 지면.

좌표는 전부 `theme.METRICS` 에서 온다. 지면에 인라인 style 로 박고, 색·서체 같은
'모양'만 CSS 클래스로 둔다. 그래야 판형·여백을 config 로 바꿔도 CSS 를 안 고친다.

구문분석 주석은 **낱말에 앵커된 절대배치 span** 이다. 줄바꿈은 브라우저가 하고
주석은 낱말을 따라간다 — 원고가 길어져도 사람이 손볼 곳이 없다.
"""
import html
import os

from core.render_vivlio.series.pocketbook import theme as T

ESC = html.escape


def _px(*parts):
    return ";".join(p for p in parts if p)


def passage_top(M, lead):
    """지문 상자의 top — **첫 기준선을 행간과 무관하게 고정**한다.

    행간을 줄이면 첫 줄의 half-leading 이 줄어 글이 위로 올라간다. 그러면 지문마다
    첫 줄 높이가 달라져 펼침면이 어긋나 보인다. (L0−L)/2 만큼 되밀어 준다.
    ⚠ margin-top 은 절대배치 상자에서 먹지 않는다(실측) — top 에 넣어야 한다.
    """
    off = M["first_baseline_fix"] + (M["passage_lead"] - lead) / 2.0
    # ⚠ `calc(24mm + -7.7pt)` 는 **잘못된 CSS** 다 — 속성이 통째로 버려지고
    #   조용히 기본 위치로 돌아간다(그래서 첫 기준선이 8.5pt 어긋났다).
    op = "-" if off < 0 else "+"
    return "calc(%gmm %s %gpt)" % (M["passage"][1], op, abs(off))


def _box(x, y, w=None, h=None):
    s = "left:%gmm;top:%gmm" % (x, y)
    if w is not None:
        s += ";width:%gmm" % w
    if h is not None:
        s += ";height:%gmm" % h
    return s


# ── 지문 본문 ─────────────────────────────────────────────
def _run_html(r):
    cls = []
    m = r.get("mark")
    if m in ("blue", "red", "wave"):
        cls.append(m)
    inner = ESC(r["t"])
    if r.get("ruby"):
        slot = r.get("slot") or "dn"
        inner = '<span class="w%s">%s<i class="%s">%s</i></span>' % (
            (" " + " ".join(cls)) if cls else "", inner, slot, ESC(r["ruby"]))
        return inner
    if cls:
        return '<span class="%s">%s</span>' % (" ".join(cls), inner)
    return inner


def runs_html(runs):
    """형광펜은 **연속 구간**이다 — 낱말마다 칠하면 어절 사이가 비어 줄무늬가 된다."""
    out, cur_hl, buf = [], None, []

    def flush():
        if not buf:
            return
        s = "".join(buf)
        out.append('<mark class="hl-%s">%s</mark>' % (cur_hl, s) if cur_hl else s)
        del buf[:]

    for r in runs:
        if r.get("br"):
            flush()
            out.append("<br>")
            continue
        hl = r.get("hl") if r.get("mark") == "hl" else None
        if hl != cur_hl:
            flush()
            cur_hl = hl
        buf.append(_run_html(r))
    flush()
    return "".join(out)


def paras_html(paras, cls=""):
    if not paras:
        return ""
    return "".join('<p%s>%s</p>' % (' class="%s"' % cls if cls else "",
                                    runs_html(p["runs"]))
                   for p in paras)


# ── 지면 ──────────────────────────────────────────────────
def left_page(p, M, folio):
    """왼쪽 면. 배치는 삽화 유무가 가른다(A/C/E) — theme.LAYOUTS."""
    L = dict(T.LAYOUTS[T.layout_for(p)])
    b = M["badge"]
    ps = list(M["passage"])
    ps[3] = L["passage_h"]
    ch = M["chip"]
    il = L.get("illust")
    tr = L["trans"]
    scale = p.get("scale", 1.0)
    parts = []
    tag = p.get("no") or p.get("label") or ""
    if tag:
        parts.append('<div class="badge" style="%s">%s</div>'
                     % (_box(b[0], b[1], b[2], b[3]), ESC(tag)))
    sc = ""
    if scale != 1.0 or p.get("lead"):
        sc = ";font-size:%gpt;line-height:%gpt" % (
            M["passage_size"] * scale, p.get("lead") or M["passage_lead"])
    lead = p.get("lead") or M["passage_lead"]
    parts.append('<div class="passage" style="left:%gmm;top:%s;width:%gmm;'
                 'height:%gmm%s">%s</div>'
                 % (ps[0], passage_top(M, lead), ps[2], ps[3], sc,
                    runs_html(p["passage_runs"])))
    if L.get("rule"):
        parts.append('<div class="rule" style="%s"></div>'
                     % _box(M["margin_l"], L["rule"], ps[2]))
    if il and p.get("illust"):
        parts.append('<div class="chip" style="%s">PICTURE</div>'
                     % _box(L["chip_pic_x"], L["chip_y"], ch[0], ch[1]))
        parts.append('<div class="illust" style="%s"><img src="%s" alt=""></div>'
                     % (_box(il[0], il[1], il[2]), ESC(p["illust"])))
    parts.append('<div class="chip" style="%s">TRANSLATION</div>'
                 % _box(L["chip_trn_x"], L["chip_y"], ch[0], ch[1]))
    if p.get("translation"):
        ts = p.get("trans_scale", 1.0)
        st = "" if ts == 1.0 else ";font-size:%gpt;line-height:%gmm" % (
            M["trans_size"] * ts, M["trans_lead"] * ts)
        parts.append('<div class="translation" style="%s%s"><p>%s</p></div>'
                     % (_box(tr[0], tr[1], tr[2]), st, ESC(p["translation"])))
    parts.append('<div class="folio" style="%s"><b>%s</b> POCKET BOOK</div>'
                 % (_box(12.9, M["folio_y"]), folio))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


_ARROW = ("→", "⇒", "▶")


def right_page(p, M, folio, category=""):
    fl = M["flow"]
    fc = M["flow_chip"]
    tb = M["topic"]
    sp = M["syn_panel"]
    st = M["syn_title"]
    cd = M["card"]
    parts = []
    # 플로우노트
    parts.append('<div class="flowchip" style="%s">💡 FLOW NOTE</div>'
                 % _box(fc[0], fc[1], fc[2], fc[3]))
    rows = []
    for line in p.get("flownote") or []:
        cls = ' class="arrow"' if line.lstrip().startswith(_ARROW) else ""
        rows.append("<p%s>%s</p>" % (cls, ESC(line)))
    parts.append('<div class="flow" style="%s">%s</div>'
                 % (_box(fl[0], fl[1], fl[2], fl[3]), "".join(rows)))
    # 주제 / 요약문
    parts.append('<div class="topicband" style="%s"></div>'
                 % _box(tb[0], tb[1], tb[2], tb[3]))
    parts.append('<div class="tbadge" style="%s">주제</div>'
                 % _box(tb[0] + 2.4, tb[1] + 1.4))
    parts.append('<div class="tbadge" style="%s">요약문</div>'
                 % _box(tb[0] + 2.0, tb[1] + 6.5))
    tt = []
    if p.get("topic"):
        tt.append("<p>%s</p>" % ESC(p["topic"]))
    if p.get("summary"):
        tt.append("<p>%s</p>" % ESC(p["summary"]))
    parts.append('<div class="topictext" style="%s">%s</div>'
                 % (_box(M["topic_text_x"], tb[1] + 1.0,
                         tb[0] + tb[2] - M["topic_text_x"] - 2.0),
                    "".join(tt)))
    # 동반의어
    parts.append('<div class="synpanel" style="%s"></div>'
                 % _box(sp[0], sp[1], sp[2], sp[3]))
    parts.append('<div class="syntitle" style="%s">Ⓐ Ⓑ Ⓒ 동반의어</div>'
                 % _box(st[0], st[1], st[2], st[3]))
    cards = (p.get("synonyms") or [])[:9]
    for i in range(9):
        col, row = i % 3, i // 3
        x = cd[0] + col * M["card_gap_x"]
        y = cd[1] + row * M["card_gap_y"]
        body = ""
        if i < len(cards):
            c = cards[i]
            body = '<p class="w1">%s %s</p>' % (ESC(c["w"]), ESC(c.get("ko", "")))
            if c.get("syn"):
                body += '<p class="s1">= %s</p>' % ESC(", ".join(c["syn"]))
            if c.get("ant"):
                body += '<p class="a1">↔ %s</p>' % ESC(", ".join(c["ant"]))
        parts.append('<div class="card" style="%s;background:var(--card%d)">%s</div>'
                     % (_box(x, y, cd[2], cd[3]), col + 1, body))
    foot = ('<span style="color:var(--ink)">%s</span> <b>%s</b>'
            % (ESC(category), folio)) if category else "<b>%s</b>" % folio
    parts.append('<div class="folio r" style="%s">%s</div>'
                 % (_box(M["margin_l"], M["folio_y"],
                         M["page_w"] - M["margin_l"] - 15.0), foot))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


def memtest_page(p, M, folio, answer, category=""):
    mt = M["memtest"]
    runs = (p.get("memtest") or {}).get("a" if answer else "q")
    if not runs:
        return ""
    label = "암기 TEST 정답" if answer else "암기 TEST"
    parts = ['<div class="mtchip" style="%s">📝 %s</div>'
             % (_box(mt[0], 12.4, 30.0, 6.0), label),
             '<div class="mtbox" style="%s"></div>'
             % _box(mt[0], mt[1], mt[2], mt[3]),
             '<div class="memtest" style="%s">%s</div>'
             % (_box(mt[0] + 3.0, mt[1] + 3.0, mt[2] - 6.0), runs_html(runs))]
    foot = "<b>%s</b> POCKET BOOK" % folio
    if answer:
        foot = ('<span style="color:var(--ink)">%s</span> <b>%s</b>'
                % (ESC(category), folio)) if category else "<b>%s</b>" % folio
    cls = "folio r" if answer else "folio"
    parts.append('<div class="%s" style="%s">%s</div>'
                 % (cls, _box(12.9 if not answer else M["margin_l"],
                              M["folio_y"],
                              None if not answer
                              else M["page_w"] - M["margin_l"] - 15.0), foot))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


def build_html(data, css_name="pocket.css"):
    M = dict(T.METRICS)
    M.update(data.get("metrics") or {})
    pages, folio = [], 1
    if data.get("cover"):
        pages.append('<section class="pg"><div class="trim">'
                     '<img src="%s" style="width:100%%;height:100%%;'
                     'object-fit:cover"></div></section>' % ESC(data["cover"]))
        folio += 1
    for p in data["passages"]:
        cat = p.get("category", "")
        pages.append(left_page(p, M, folio)); folio += 1
        pages.append(right_page(p, M, folio, cat)); folio += 1
        if p.get("memtest"):
            q = memtest_page(p, M, folio, False, cat)
            if q:
                pages.append(q); folio += 1
            a = memtest_page(p, M, folio, True, cat)
            if a:
                pages.append(a); folio += 1
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<title>%s</title><link rel="stylesheet" href="%s"></head><body>'
            '%s</body></html>'
            % (ESC(data.get("title", "포켓북")), css_name, "".join(pages)))
