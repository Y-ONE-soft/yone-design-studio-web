# -*- coding: utf-8 -*-
"""포켓북 HTML 생성 — 지문 데이터 → 지면.

좌표는 전부 `theme.METRICS` 에서 온다. 지면에 인라인 style 로 박고, 색·서체 같은
'모양'만 CSS 클래스로 둔다. 그래야 판형·여백을 config 로 바꿔도 CSS 를 안 고친다.

구문분석 주석은 **낱말에 앵커된 절대배치 span** 이다. 줄바꿈은 브라우저가 하고
주석은 낱말을 따라간다 — 원고가 길어져도 사람이 손볼 곳이 없다.
"""
import html
import os
import re

from core.render_vivlio import refs as _refs
from core.render_vivlio.series.pocketbook import theme as T

def ESC(s):
    """글을 HTML 로. 평문은 예전 그대로.
    # ⚠ 작업대에서 **글자 단위 서식**을 걸면 이 값이 서식 조각 목록이 된다.
    #   그때 `html.escape()` 는 죽고 **조판이 통째로 안 나온다**(실측: 라벨에
    #   자간을 줬더니 `'list' object has no attribute 'replace'`).
    """
    if isinstance(s, str):
        return html.escape(s)
    if s is None:
        return ""
    from core.render_vivlio import richtext as _rt
    return _rt.to_html(s, blanks=False)


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
_MARK_CLS = {"blue": "blue", "red": "red", "wave": "wave",
             "num": "n", "blank": "blank"}


# 구문분석 주석이 **문장 하나**로 오는 경우가 있다(분석본 실측: 낱말 `T` 에
# 50자, `bother` 에 70자). 7pt 로 한 줄에 늘어놓으면 단(115mm)을 넘어 지면 밖으로
# 나가고 **통째로 잘려 사라진다**(세종1 260633·한영1 241036). 단 안에 들어오도록
# 그것만 글자를 줄인다 — 보통 주석(10자 안팎)은 손대지 않는다.
_RUBY_MAX_MM = 112.0
_RUBY_EM_MM = 7.0 / 72.0 * 25.4       # 7pt


_RUBY_CENTER_MM = 40.0


def _ruby_fit(rb):
    """긴 주석이 지면 밖으로 나가지 않게 잡는다.

    주석은 낱말 **가운데**에 건다(인디자인과 같다). 문장 하나가 통째로 루비로
    오는 경우가 있어(41,510개 중 127개, 0.31% 가 36mm 초과) 줄 끝 낱말에 걸리면
    절반이 지면 밖으로 나가 잘린다. 인디자인도 텍스트 프레임에서 똑같이 잘린다 —
    **여기서 자리를 옮기면 원본과 달라진다.** 왼쪽에 붙여 봤더니 이번엔 오른쪽으로
    더 많이 잘렸다(한영1 178→156 실측). 그래서 자리는 그대로 두고, **단보다 넓어
    어디에 놔도 안 들어가는 것만** 글자를 줄인다. 잘릴 수 있는 것은 검수가
    목록으로 알린다(G-P3 경고).
    """
    w = ruby_mm(rb)
    if w <= _RUBY_MAX_MM:
        return ""
    return ";font-size:%.2fpt" % max(4.0, 7.0 * _RUBY_MAX_MM / w)


def ruby_mm(rb):
    """주석을 한 줄로 늘어놓았을 때의 폭(mm) 어림."""
    return sum(_RUBY_EM_MM if ord(c) > 0x2000 else _RUBY_EM_MM * 0.5
               for c in rb)


def _run_html(r):
    cls = []
    m = r.get("mark")
    if m in _MARK_CLS:
        cls.append(_MARK_CLS[m])
    inner = ESC(r["t"])
    if r.get("ruby"):
        slot = r.get("slot") or "dn"
        fit = _ruby_fit(r["ruby"])
        inner = '<span class="w%s">%s<i class="%s"%s>%s</i></span>' % (
            (" " + " ".join(cls)) if cls else "", inner, slot,
            (' style="%s"' % fit) if fit else "", ESC(r["ruby"]))
        return inner
    if cls:
        return '<span class="%s">%s</span>' % (" ".join(cls), inner)
    return inner


def _cluster(runs):
    """런 흐름 → **낱말 덩이** 목록. 공백에서만 끊는다.

    ⚠ 루비가 낱말 **일부**에 걸리면(`everyon` + 루비 `e`) 그 자리가 inline-block
      경계라 브라우저가 낱말 한가운데서 줄을 바꾼다(`everyon / e`). 인디자인은
      그러지 않는다. 덩이째 `nowrap` 으로 묶어 막는다.
    """
    groups, cur = [], []
    for r in runs:
        if r.get("br"):
            if cur:
                groups.append(cur)
                cur = []
            groups.append([r])
            continue
        t = r["t"]
        # ⚠ **공백 한 칸에 주석이 붙는 경우가 있다**(`' or what size '` 의 빈칸에
        #   `복합관계형용사`). 아래 공백 쪼개기에 그냥 넘기면 조각이 빈 글자가 돼
        #   **주석이 통째로 버려진다**(광문2 3과 MR2·MR6 실측). 낱말처럼 따로
        #   세우되 줄바꿈 자리는 남긴다. 공백은 접히므로 NBSP 로 세운다.
        if r.get("ruby") and not t.strip():
            if cur:
                groups.append(cur)
                cur = []
            groups.append([dict(r, t="\u00a0")])
            groups.append(None)
            continue
        if " " not in t and "\u00a0" not in t:
            cur.append(r)
            continue
        parts = t.split(" ")
        for i, piece in enumerate(parts):
            if i:
                if cur:
                    groups.append(cur)
                    cur = []
                groups.append(None)          # 공백 = 끊을 수 있는 자리
            if piece:
                cur.append(dict(r, t=piece))
    if cur:
        groups.append(cur)
    return groups


# 노란 형광펜에는 **'서술형' 손글씨 표식**이 딸려 온다(원본: 형광펜_노랑 문자
# 범위 안에 앵커된 벡터, 바닥중앙 기준 8.5pt 위). 벡터는 22KB 라 지문마다 심으면
# 문서가 부는다 — 파일 하나로 두고 가리킨다.
_ICON = '<span class="ico"><img src="img/seosul.svg" alt=""></span>'

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "assets", "pocketbook")


def _svg(name):
    """계열 아이콘을 **HTML 안에 그대로** 심는다.

    ⚠ `<img>` 로 두면 그 SVG 안에서 지면 서체(`PBJalnan`)를 못 써서 동반의어
      표식의 A·B·C 가 엉뚱한 글꼴로 나온다. 딱지 아이콘도 같은 방식으로 맞춘다.
    """
    with open(os.path.join(_ASSETS, name + ".svg"), encoding="utf-8") as f:
        return f.read().replace("<svg ", '<svg class="ic-%s" ' % name, 1)


def runs_html(runs):
    """형광펜은 **연속 구간**이다 — 낱말마다 칠하면 어절 사이가 비어 줄무늬가 된다."""
    out, cur_hl, buf = [], None, []

    def flush():
        if not buf:
            return
        s = "".join(buf)
        if cur_hl:
            ico = _ICON if cur_hl == "yellow" else ""
            out.append('<mark class="hl-%s">%s%s</mark>' % (cur_hl, ico, s))
        else:
            out.append(s)
        del buf[:]

    for grp in _cluster(runs):
        if grp is None:                      # 공백
            buf.append(" ")
            continue
        if len(grp) == 1 and grp[0].get("br"):
            flush()
            out.append("<br>")
            cur_hl = None
            continue
        hl = grp[0].get("hl") if grp[0].get("mark") == "hl" else None
        if hl != cur_hl:
            flush()
            cur_hl = hl
        inner = "".join(_run_html(r) for r in grp)
        buf.append('<span class="wc">%s</span>' % inner
                   if len(grp) > 1 else inner)
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
    # ⚠ 자리표는 **원래 클래스 그대로** 얹는다(`refs.mark` 이 합쳐 준다).
    #   뜻 있는 클래스를 같이 넣으면 지면이 달라진다.
    parts.append('<div%s style="left:%gmm;top:%s;width:%gmm;'
                 'height:%gmm%s">%s</div>'
                 % (_refs.mark(_refs.of(p, "passage_runs"), "passage"),
                    ps[0], passage_top(M, lead), ps[2], ps[3], sc,
                    runs_html(p["passage_runs"])))
    if L.get("rule"):
        parts.append('<div class="rule" style="%s"></div>'
                     % _box(M["margin_l"], L["rule"], ps[2]))
    if il and p.get("illust"):
        parts.append('<div class="chip" style="%s">PICTURE</div>'
                     % _box(L["chip_pic_x"], L["chip_y"], ch[0], ch[1]))
        parts.append('<div class="illust" style="%s"><img src="%s" alt=""></div>'
                     % (_box(il[0], il[1], il[2], il[3]), ESC(p["illust"])))
    parts.append('<div class="chip" style="%s">TRANSLATION</div>'
                 % _box(L["chip_trn_x"], L["chip_y"], ch[0], ch[1]))
    if p.get("translation"):
        ts = p.get("trans_scale", 1.0)
        st = "" if ts == 1.0 else ";font-size:%gpt;line-height:%gmm" % (
            M["trans_size"] * ts, M["trans_lead"] * ts)
        parts.append('<div%s style="%s%s"><p>%s</p></div>'
                     % (_refs.mark(_refs.of(p, "translation"), "translation"),
                        _box(tr[0], tr[1], tr[2]), st, ESC(p["translation"])))
    parts.append('<div class="folio" style="%s"><b>%s</b> POCKET BOOK</div>'
                 % (_box(12.9, M["folio_y"]), folio))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


# 플로우노트에서 **색이 붙는 것은 기호 글자뿐**이다.
# ⚠ 줄이 화살표로 시작한다고 **줄 전체를 칠하면 안 된다** — 원본은 글자 단위다
#   (완성본 6권 실측: 본문은 한 색, 기호 스타일만 따로 있다).
_SYM = set("→⇒⟶⇨➔➜⟹←⟵↑↓↔⇔▶▸►◀‣")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def flow_html(line):
    """플로우노트 한 줄 → HTML. 기호 글자만 색을 입힌다.

    ⚠ 원고에 `**굵게**` 같은 표시가 오면 **별표가 그대로 인쇄된다**(실측:
      `**구식(outdated)**`). 조판이 벗겨 준다 — 원고 양식에도 쓰지 말라고 적었다.
    """
    line = _MD_BOLD.sub(r"\1", line)
    out, buf = [], []
    for ch in line:
        if ch in _SYM:
            if buf:
                out.append(ESC("".join(buf)))
                del buf[:]
            out.append('<span class="sym">%s</span>' % ESC(ch))
        else:
            buf.append(ch)
    if buf:
        out.append(ESC("".join(buf)))
    return "".join(out)


def _line_est(txt, width_mm, size_pt):
    """글이 몇 줄이 될지 어림. 한글은 한 자 1em, 영문은 0.5em 로 본다."""
    if not txt:
        return 0
    em = size_pt / 72.0 * 25.4
    w = sum(em if ord(c) > 0x2000 else em * 0.5 for c in txt)
    return max(1, int(w / max(width_mm, 1.0)) + (1 if w % width_mm else 0))


def _card_fit(c, M):
    """카드가 넘칠 것 같으면 미리 줄인다.

    카드는 34.6×32mm 로 작고 개수가 많다(한 책에 수백 장). 지문처럼 면마다 재면
    측정 조판이 감당이 안 된다 — 그래서 **글자 수로 줄 수를 어림**해 단계로 줄인다.
    한 줄에 들어가는 글자 수는 7pt 에서 약 24자(실측 34.6mm − 여백 4mm).
    """
    per = 24.0
    lines = 0
    for txt in (("%s %s" % (c["w"], c.get("ko", ""))).strip(),
                ("= " + ", ".join(c.get("syn") or [])) if c.get("syn") else "",
                ("↔ " + ", ".join(c.get("ant") or [])) if c.get("ant") else ""):
        if txt:
            lines += max(1, int(len(txt) / per) + (1 if len(txt) % per else 0))
    room = int((M["card"][3] - 2 * M["card_pad"]) / M["card_lead"])
    if lines <= room:
        return ""
    sc = max(0.78, round(room / float(lines), 2))
    return ";font-size:%gpt;line-height:%gmm" % (
        M["card_size"] * sc, M["card_lead"] * sc)


def right_page(p, M, folio, category=""):
    fl = M["flow"]
    fc = M["flow_chip"]
    tb = M["topic"]
    sp = M["syn_panel"]
    st = M["syn_title"]
    cd = M["card"]
    parts = []
    # 플로우노트
    parts.append('<div class="flowchip" style="%s">%sFLOW NOTE</div>'
                 % (_box(fc[0], fc[1], fc[2], fc[3]), _svg("chip_flow")))
    rows = ["<p>%s</p>" % flow_html(line)
            for line in (p.get("flownote") or [])]
    fsc = p.get("flow_scale", 1.0)
    fst = "" if fsc == 1.0 else ";font-size:%gpt;line-height:%gmm" % (
        M["flow_size"] * fsc, M["flow_lead"] * fsc)
    # ⚠ 모눈 깔개를 `.flow::before` 로 두면 **단(column) 흐름에 끼어** 깔리지
    #   않는다(불투명도가 하나도 안 먹은 것처럼 보였다). 상자와 단을 나눈다.
    parts.append('<div class="flow" style="%s">'
                 '<div class="flowin" style="%s">%s</div></div>'
                 % (_box(fl[0], fl[1], fl[2], fl[3]), fst.lstrip(";"),
                    "".join(rows)))
    # 주제 / 요약문
    parts.append('<div class="topicband" style="%s"></div>'
                 % _box(tb[0], tb[1], tb[2], tb[3]))
    # ⚠ 두 딱지는 **색이 다르다**(원본: 주제 CMYK 66/52/0/19, 요약문 0/32/48/9).
    #   같은 색이면 어디까지가 주제고 어디부터 요약문인지 안 보인다.
    parts.append('<div class="tbadge t" style="%s">주제</div>'
                 % _box(tb[0] + 2.4, tb[1] + 1.4))
    # ⚠ 주제가 두 줄이면 요약문은 셋째 줄에서 시작한다. 딱지를 붙박아 두면
    #   요약문 딱지 옆에 **주제 둘째 줄**이 오게 된다(사용자 지적).
    tw = tb[0] + tb[2] - M["topic_text_x"] - 2.0
    lines = _line_est(p.get("topic") or "", tw, M["topic_size"])
    parts.append('<div class="tbadge s" style="%s">요약문</div>'
                 % _box(tb[0] + 2.0,
                        tb[1] + 1.4 + max(1, lines) * M["topic_lead"] + 1.6))
    tt = []
    if p.get("topic"):
        tt.append("<p>%s</p>" % ESC(p["topic"]))
    if p.get("summary"):
        tt.append("<p>%s</p>" % ESC(p["summary"]))
    tsc = p.get("topic_scale", 1.0)
    tst = "" if tsc == 1.0 else ";font-size:%gpt;line-height:%gmm" % (
        M["topic_size"] * tsc, M["topic_lead"] * tsc)
    parts.append('<div class="topictext" style="%s%s">%s</div>'
                 % (_box(M["topic_text_x"], tb[1] + 1.0,
                         tb[0] + tb[2] - M["topic_text_x"] - 2.0),
                    tst, "".join(tt)))
    # 동반의어
    parts.append('<div class="synpanel" style="%s"></div>'
                 % _box(sp[0], sp[1], sp[2], sp[3]))
    parts.append('<div class="syntitle" style="%s">%s동반의어</div>'
                 % (_box(st[0], st[1], st[2], st[3]), _svg("synmark")))
    cards = (p.get("synonyms") or [])[:9]
    for i in range(9):
        col, row = i % 3, i // 3
        x = cd[0] + col * M["card_gap_x"]
        y = cd[1] + row * M["card_gap_y"]
        body, fit = "", ""
        if i < len(cards):
            c = cards[i]
            body = '<p%s>%s %s</p>' % (
                _refs.mark(_refs.of(c, "w"), "w1"), ESC(c["w"]),
                ESC(c.get("ko", "")))
            if c.get("syn"):
                body += '<p class="s1">= %s</p>' % ESC(", ".join(c["syn"]))
            if c.get("ant"):
                body += '<p class="a1">↔ %s</p>' % ESC(", ".join(c["ant"]))
            fit = _card_fit(c, M)
        parts.append('<div class="card" style="%s;background:var(--card%d)%s">%s</div>'
                     % (_box(x, y, cd[2], cd[3]), col + 1, fit, body))
    foot = ('<span style="color:var(--ink)">%s</span> <b>%s</b>'
            % (ESC(category), folio)) if category else "<b>%s</b>" % folio
    parts.append('<div class="folio r" style="%s">%s</div>'
                 % (_box(M["margin_l"], M["folio_y"],
                         M["page_w"] - M["margin_l"] - 15.0), foot))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


def memtest_page(p, M, folio, answer, category=""):
    mt = M["memtest"]
    runs = p.get("runs") if p.get("kind") == "memtest" else (
        (p.get("memtest") or {}).get("a" if answer else "q"))
    if not runs:
        return ""
    fit = ""
    if p.get("mt_lead"):
        fit = ";line-height:%gpt" % p["mt_lead"]
    if p.get("mt_scale"):
        fit += ";font-size:%gpt" % (M["memtest_size"] * p["mt_scale"])
    label = "암기 TEST 정답" if answer else "암기 TEST"
    # ⚠ 문제면과 정답면은 **색이 다르다**(원본 B-마스터: 문제=베이지 바탕에
    #   같은 색 테두리, 정답=연파랑 바탕에 파란 테두리). 같은 색으로 두면
    #   펼쳐 놓고 어느 쪽이 정답인지 알 수 없다.
    a = " a" if answer else ""
    parts = ['<div class="mtchip%s" style="%s">%s%s</div>'
             % (a, _box(mt[0], 12.4, 30.0, 6.0), _svg("chip_memtest"), label),
             '<div class="mtbox%s" style="%s"></div>'
             % (a, _box(mt[0], mt[1], mt[2], mt[3])),
             '<div class="memtest" style="%s%s">%s</div>'
             % (_box(mt[0] + 3.0, mt[1] + 3.0, mt[2] - 6.0), fit,
                runs_html(runs))]
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
    # 작업대에서 지면을 눌러 그 자리를 고칠 수 있게 — **렌더 직전에 한 번**.
    # ⚠ 안 하면 클릭해도 조용히 아무 일도 안 일어난다(자리표가 없으니까).
    _refs.index_paths(data, [("passages",), ("passages", "cards")])
    M = dict(T.METRICS)
    M.update(data.get("metrics") or {})
    pages = []
    folio = int(data.get("folio_start", 1))
    if data.get("cover"):
        pages.append('<section class="pg"><div class="trim">'
                     '<img src="%s" style="width:100%%;height:100%%;'
                     'object-fit:cover"></div></section>' % ESC(data["cover"]))
        folio += 1
    for p in data["passages"]:
        cat = p.get("category", "")
        if p.get("kind") == "memtest":
            pg = memtest_page(p, M, folio, p.get("answer"), cat)
            if pg:
                pages.append(pg); folio += 1
            continue
        pages.append(left_page(p, M, folio)); folio += 1
        pages.append(right_page(p, M, folio, cat)); folio += 1
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<title>%s</title><link rel="stylesheet" href="%s"></head><body>'
            '%s</body></html>'
            % (ESC(data.get("title", "포켓북")), css_name, "".join(pages)))
