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


# ── 주석 자리 재기 ──────────────────────────────────────────────────
#
# 구문분석 주석은 낱말 **가운데**에 걸린다. 줄 끝 낱말에 긴 주석이 걸리면
# 판면을 넘어 **제본 안전 영역까지 침범한다**(광문1 실측: 54면 `consciousness
# fluctuates continuously` 가 148.9mm — 재단선 밖이다). 스프링 제본이라 그
# 자리는 구멍이 뚫려 아예 안 보인다.
#
# 어디까지 나가는지는 **줄바꿈이 끝나야** 알 수 있어서 글자 수로는 못 잡는다.
# 그래서 측정용 조판에서 주석마다 **번호를 색으로 새겨** 오른쪽 끝을 재고,
# 본 조판에서 그만큼 왼쪽으로 민다. 옮기는 것은 **넘친 것만**이다 — 예전에
# 전부 왼쪽에 붙였다가 오히려 더 잘렸다(한영1 178→156).
MARK_RUBY = False        # 측정용 조판에서만 켠다
_RIDX = [0]              # 이 지문에서 몇 번째 주석인가
_RDX = {}                # {주석 차례: 왼쪽으로 밀 mm}


def ruby_reset(dx=None):
    """지문 하나를 그리기 전에 부른다. `dx` 는 이 지문의 밀기 표."""
    _RIDX[0] = 0
    _RDX.clear()
    _RDX.update(dx or {})


def ruby_count():
    return _RIDX[0]


def _run_html(r):
    cls = []
    m = r.get("mark")
    if m in _MARK_CLS:
        cls.append(_MARK_CLS[m])
    inner = ESC(r["t"])
    if r.get("ruby"):
        slot = r.get("slot") or "dn"
        st = _ruby_fit(r["ruby"])
        k = _RIDX[0]
        _RIDX[0] += 1
        if MARK_RUBY:                       # 번호를 색으로 새긴다(측정용)
            st += ";color:rgb(2,%d,%d)" % (k // 256, k % 256)
        elif _RDX.get(k):
            st += ";margin-left:%.2fmm" % (-_RDX[k])
        inner = '<span class="w%s">%s<i class="%s"%s>%s</i></span>' % (
            (" " + " ".join(cls)) if cls else "", inner, slot,
            (' style="%s"' % st.lstrip(";")) if st else "", ESC(r["ruby"]))
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
_SENT_END = re.compile(r'[.!?][\'"\u2019\u201d)\]]*\s')

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "assets", "pocketbook")


def _svg(name):
    """계열 아이콘을 **HTML 안에 그대로** 심는다.

    ⚠ `<img>` 로 두면 그 SVG 안에서 지면 서체(`PBJalnan`)를 못 써서 동반의어
      표식의 A·B·C 가 엉뚱한 글꼴로 나온다. 딱지 아이콘도 같은 방식으로 맞춘다.
    """
    with open(os.path.join(_ASSETS, name + ".svg"), encoding="utf-8") as f:
        return f.read().replace("<svg ", '<svg class="ic-%s" ' % name, 1)


def _glue_icon(ico, html):
    """서술형 표식을 **첫 낱말에 붙여** 준다.

    표식은 폭 0 인 인라인 상자라 브라우저가 그 **뒤에서 줄을 바꿔** 버린다 —
    그러면 줄 끝에 별표만 덩그러니 남고 문장은 다음 줄에서 시작한다(사용자가
    두 번 지적했다). 표식과 첫 낱말을 한 덩이로 묶어 그 자리를 막는다.
    """
    out, i, depth, cut = [], 0, 0, None
    while i < len(html):
        c = html[i]
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
        elif depth == 0 and c in " \u00a0":
            cut = i
            break
        i += 1
    if cut is None:
        return '<span class="nb">%s%s</span>' % (ico, html)
    return '<span class="nb">%s%s</span>%s' % (ico, html[:cut], html[cut:])


_RE_ITEM = re.compile(r"(?<!^)(?=[\u25a1\u2022\u203b])")   # □ • ※ 앞


def _item_breaks(html, on):
    """실용문 항목 머리(`□`·`•`·`※`) 앞에서 줄을 바꾼다.

    ⚠ 안내문·도표는 원고가 **한 문단**으로 흘러 들어와 항목 구조가 사라진다
      (연구원 지적 4건: `□ Date and Time` 이 앞 문장에 붙어 버림). 표식이 있는
      지문에서만, **표식 바로 앞**에 줄바꿈을 넣는다 — 일반 지문은 안 건드린다.
    """
    return _RE_ITEM.sub("<br>", html) if on else html


def _is_notice(p):
    """실용문(안내문·도표)인가 — 항목 표식이 있는 지문."""
    t = "".join(x.get("t", "") for x in (p.get("passage_runs") or []))
    return sum(t.count(c) for c in "\u25a1\u2022\u203b") >= 2


def runs_html(runs, items=False):
    """형광펜은 **연속 구간**이다 — 낱말마다 칠하면 어절 사이가 비어 줄무늬가 된다."""
    out, cur_hl, buf = [], None, []

    seen_yellow = [False]        # 이 문장에서 '서술형' 표식을 이미 달았는가

    def flush():
        if not buf:
            return
        s = "".join(buf)
        if cur_hl:
            # ⚠ 표식은 **문장 하나에 하나**다. 노란 형광펜이 여러 토막으로
            #   끊긴 것은 사이에 다른 설명이 낀 것일 뿐 서술형이 여럿인 게
            #   아니다(사용자 지적). 문장이 끝날 때까지 한 번만 단다.
            ico = _ICON if (cur_hl == "yellow" and not seen_yellow[0]) else ""
            if ico:
                seen_yellow[0] = True
            out.append('<mark class="hl-%s">%s</mark>'
                       % (cur_hl, _glue_icon(ico, s) if ico else s))
        else:
            out.append(s)
        # ⚠ 문장 끝은 **형광펜 안쪽에도** 있다. 바깥 글만 보면 문장이 형광펜
        #   안에서 끝났을 때 다음 문장이 열리지 않아, 여러 문장에 표식이 하나만
        #   붙는다(사용자 지적).
        if _SENT_END.search(s):
            seen_yellow[0] = False
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
def _school_tail(M):
    """왼쪽 꼬리말 `POCKET BOOK` 뒤에 붙는 **학교 이름**(사용자 지시)."""
    sc = str(M.get("school") or "").strip()
    return (" %s" % ESC(sc)) if sc else ""


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
    tag = "" if p.get("_part") == 2 else _badge_text(p)
    if tag and M.get("topic_box"):
        # ⚠ 「주제 :」 칸을 넣으면 한 줄짜리 긴 배지가 그 칸을 **덮는다**
        #   (`능률(민) SL2 본문2`, 사용자 지적). 광문은 배지를 세로로 세워
        #   위 칸에 교재명, 아래 칸에 지문번호를 넣는다.
        b2 = M["badge2"]
        head, no = _badge_parts(p)
        sz, ld = _badge2_fit((head, no), b2[2], b2[3], M)
        parts.append('<div class="badge two" style="%s;font-size:%.2fpt;'
                     'line-height:%gmm">%s<span>%s</span></div>'
                     % (_box(b2[0], b2[1], b2[2], b2[3]), sz, ld,
                        ('<span class="bh">%s</span>' % ESC(head))
                        if head else "", ESC(no)))
    elif tag:
        # ⚠ 배지 폭은 18mm 고정이었다. 분석본에서 오는 긴 라벨
        #   (`3과 MR1 Brain Insights`)이 **양옆으로 잘려 나갔다**. 최소 폭은
        #   지키고 글에 맞춰 늘리되, 너무 길면 글자를 줄여 판면을 안 넘긴다.
        parts.append('<div class="badge" style="%s%s">%s</div>'
                     % (_box(b[0], b[1], None, b[3]), _badge_fit(tag, M),
                        ESC(tag)))
    sc = ""
    if scale != 1.0 or p.get("lead"):
        sc = ";font-size:%gpt;line-height:%gpt" % (
            M["passage_size"] * scale, p.get("lead") or M["passage_lead"])
    lead = p.get("lead") or M["passage_lead"]
    # ⚠ 자리표는 **원래 클래스 그대로** 얹는다(`refs.mark` 이 합쳐 준다).
    #   뜻 있는 클래스를 같이 넣으면 지면이 달라진다.
    ruby_reset(p.get("_rdx"))
    parts.append('<div%s style="left:%gmm;top:%s;width:%gmm;'
                 'height:%gmm%s">%s</div>'
                 % (_refs.mark(_refs.of(p, "passage_runs"), "passage"),
                    ps[0], passage_top(M, lead), ps[2], ps[3], sc,
                    _item_breaks(runs_html(p["passage_runs"]),
                                 _is_notice(p))))
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
        # 넘칠 때는 **행간 → 자간 → 글자 크기** 차례로 조인다(사용자 지시).
        #   행간만으로 되면 글자 크기는 건드리지 않는다 — 지문마다 글자가
        #   제각각이면 펼침면이 들쭉날쭉해 보인다.
        st = ""
        if p.get("trans_lead"):
            st += ";line-height:%gmm" % p["trans_lead"]
        if p.get("trans_track"):
            st += ";letter-spacing:%.3fem" % p["trans_track"]
        ts = p.get("trans_scale", 1.0)
        if ts != 1.0:
            st += ";font-size:%gpt" % (M["trans_size"] * ts)
        parts.append('<div%s style="%s%s"><p>%s</p></div>'
                     % (_refs.mark(_refs.of(p, "translation"), "translation"),
                        _box(tr[0], tr[1], tr[2]), st,
                        _item_breaks(ESC(p["translation"]), _is_notice(p))))
    # 「주제 :」 써 보는 칸 — 광문 완성본에만 있다(`options.topic_box`).
    # ⚠ 갈라진 장문의 **뒷면**은 앞면에서 이어지는 같은 지문이다 — 배지도
    #   주제 칸도 다시 달지 않는다(사용자 지적).
    if M.get("topic_box") and p.get("_part") != 2:
        tb2 = M["topicbox"]; tl = M["topicbox_lab"]; tp = M["topicbox_pen"]
        parts.append('<div class="tbox" style="%s"></div>'
                     % _box(tb2[0], tb2[1], tb2[2], tb2[3]))
        parts.append('<div class="tboxlab" style="%s">주제 :</div>'
                     % _box(tl[0], tl[1]))
        parts.append('<div class="tboxpen" style="%s">%s</div>'
                     % (_box(tp[0], tp[1], tp[2], tp[3]), _svg("pen")))
    parts.append('<div class="folio" style="%s"><b>%s</b> POCKET BOOK%s</div>'
                 % (_box(12.9, M["folio_y"]), folio, _school_tail(M)))
    return ('<section class="pg %s"><div class="trim">%s</div></section>'
            % (page_kind(p), "".join(parts)))


_RE_UNIT_KIND = re.compile(r"\d{1,2}\s*강|Unit\s*\d{1,2}", re.I)


# ── 어휘 파트 ───────────────────────────────────────────────────────
# 원고는 그 낱말이 쓰인 자리를 `[…]` 로 감싸 온다. 지면에서는 대괄호를 지우고
# **그 말에만 색**을 준다(완성본 문자 스타일 `뜻 빨간색`·`예문_뜻 빨간색`).
_HIT = re.compile(r"\[([^\[\]]+)\]")


# ⚠ 뜻 칸의 `[형]`·`[명]` 은 **품사 표시**지 강조가 아니다. 예문의 대괄호와
#   같은 규칙으로 칠하면 뜻이 온통 빨개진다(완성본은 `표제어 뜻 괄호` 6pt).
_POS = re.compile(r"^(명|대|동|형|부|전|접|감|조|수)\d?$")


def _hit(t, pos_only=False):
    out, i = [], 0
    for m in _HIT.finditer(t):
        out.append(ESC(t[i:m.start()]))
        inner = m.group(1)
        if _POS.match(inner.strip()):
            out.append('<span class="pos">[%s]</span>' % ESC(inner))
        elif pos_only:
            out.append(ESC(m.group(0)))
        else:
            out.append('<span class="hit">%s</span>' % ESC(inner))
        i = m.end()
    out.append(ESC(t[i:]))
    return "".join(out)


def voca_page(pg, M, folio, side="l", part=None, palette=None):
    """어휘 한 면 — 26-1-기말 완성본 그대로.

    왼쪽 단에 **번호 · 회독칸 3개 · 표제어**, 오른쪽 단에 **뜻 · 예문 · 해석**.
    낱말 사이에는 가는 선이 있고, 머리말은 지문 배지가 아니라 **베이지 딱지**다.
    ⚠ 완성본에는 발음기호·파생어가 없다. 26-2 원고에 새로 들어왔으므로
      발음기호는 표제어 옆에, 파생어는 뜻 아래에 작게 얹는다.
    """
    v, hd = M["voca"], M["voca_head"]
    x = v[0] if side == "l" else M["margin_r"]
    ck = ('<span class="ck"></span>' * 3)
    ents = []
    for e in pg["items"]:
        r = ['<p class="mn">%s</p>' % _hit(e.get("mean", ""), True)]
        if e.get("derived"):
            r.append('<p class="dv">%s</p>' % _hit(e["derived"], True))
        for en, ko in e.get("ex") or ():
            r.append('<p class="ex">%s</p>' % _hit(en))
            if ko:
                r.append('<p class="exk">%s</p>' % _hit(ko))
        ents.append(
            '<div class="ent"><div class="l"><span class="no">%03d</span>%s'
            '<span class="hw">%s</span>%s</div><div class="r">%s</div></div>'
            % (e.get("seq") or e["no"], ck, ESC(e["word"]),
               ('<span class="ipa">%s</span>' % ESC(e["ipa"]))
               if e.get("ipa") else "", "".join(r)))
    # 머리말 딱지는 **왼쪽 면에만** 있다(완성본 실측: 오른쪽 면은 꼬리말 `VOCA`).
    # 머리말 딱지는 **왼쪽 면에만** 있다(완성본 실측: 오른쪽 면은 꼬리말 `VOCA`).
    # 딱지 폭은 **글에 맞춰 늘어난다** — 못 박으면 `Unit 15` 가 두 줄로 접힌다.
    head = ('<div class="vhead" style="left:%gmm;top:%gmm;height:%gmm">%s%s</div>'
            % (x, hd[1], hd[3], _svg("chip_voca"),
               ESC(pg["day"]))) if side == "l" else ""
    body = ('<div class="voca" style="%s">%s</div>'
            % (_box(x, v[1], v[2], v[3]), "".join(ents)))
    if side == "l":
        foot = ('<div class="folio" style="%s"><b>%s</b> POCKET BOOK%s</div>'
                % (_box(12.9, M["folio_y"]), folio, _school_tail(M)))
    else:
        foot = ('<div class="folio r" style="%s">'
                '<span style="color:var(--ink)">VOCA</span> <b>%s</b></div>'
                % (_box(M["margin_l"], M["folio_y"],
                        M["page_w"] - M["margin_l"] - 15.0), folio))
    tab = side_tab(M, part, palette) if side == "r" else ""
    return ('<section class="pg k-voca"><div class="trim">%s%s%s%s</div>'
            '</section>' % (head, body, foot, tab))


def page_kind(p):
    """지문 성격 → 면 클래스. 위·아래 띠 색이 여기서 갈린다.

    원본은 마스터를 나눠 띠 색으로 교재를 구분한다(교과서 하늘 · 부교재 연보라
    · 모의고사 베이지). 한 색으로 통일하면 펼쳐 놓고 어느 교재인지 알 수 없다.

    ⚠ `교과서` 로 시작하는지만 봤더니 **교과서 이름이 그대로 온 책**(광문1 의
      `능률(민) SL2`)이 부교재 색으로 나갔다. 갈림길은 이름이 아니라 **강이
      붙었는지**다 — 부교재만 `N강`·`Unit N` 을 쓴다.
    """
    unit = str(p.get("category") or p.get("unit") or "")
    if "모의고사" in unit or str(p.get("no") or "").isdigit():
        return "k-mock"
    if _RE_UNIT_KIND.search(unit):
        return "k-unit"
    return "k-lesson" if unit else ""


# 플로우노트에서 **색이 붙는 것은 기호 글자뿐**이다.
# ⚠ 줄이 화살표로 시작한다고 **줄 전체를 칠하면 안 된다** — 원본은 글자 단위다
#   (완성본 6권 실측: 본문은 한 색, 기호 스타일만 따로 있다).
_SYM = set("→⇒⟶⇨➔➜⟹←⟵↑↓↔⇔▶▸►◀‣")
# ①②③… 로 시작하는 줄은 **묶음의 머리**다. 앞에 한 숨 띄워야 ①-② 가 눈에 갈린다.
_SEC = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳❶❷❸❹❺")
# 줄머리 대괄호 표제 — `[핵심]` `[인용]` `[결론]`. 묶음의 머리라 색을 달리하고
# 앞을 띄운다(사용자 지적: "이렇게 구분되는 대괄호는 다른 색으로").
# ⚠ 12자로 끊어 놨더니 표제가 **조용히 본문이 됐다** — 색도 간격도 안 붙는다.
# 완성본 표제 3,155개를 재 보니 중앙 3자지만 95%가 14자, 최대 43자라서
# 12자 상한은 완성본의 7%까지 죽이고 있었다. 넉넉히 30자로 연다.
_LEAD_BRK = re.compile(r"^\s*\[[^\]]{1,30}\]")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


# ── 플로우노트 한 줄 폭 ─────────────────────────────────────────────
#
# 글자 수로 어림하면 안 된다. 플로우 글꼴(KCC 도담도담)은 한글 자폭이 제각각이라
# (`가` 0.760em · `음` 0.670em) 같은 글자 수라도 3mm 넘게 차이 난다. 한 글자만
# 넘쳐 다음 줄로 떨어지는 일(사용자 지적)을 잡으려면 **자폭을 실제로 재야** 한다.
_FLOW_FONT = "KCCDodamdodam_OTF.otf"
_ADV = {}


def _adv(ch):
    """글자 하나의 자폭(em). 글꼴을 못 읽으면 한글 0.76 / 나머지 0.5 로 본다."""
    if ch in _ADV:
        return _ADV[ch]
    if _ADV.get("_") is None and "_" not in _ADV:
        _load_adv()
    if _ADV.get("_bad"):
        return 0.76 if ord(ch) > 0x2000 else 0.5
    _ADV[ch] = 0.76 if ord(ch) > 0x2000 else 0.5
    return _ADV[ch]


def _load_adv():
    import glob
    try:
        from fontTools.ttLib import TTFont
        here = os.path.dirname(os.path.abspath(__file__))
        # …/core/render_vivlio/series/pocketbook → 저장소 뿌리까지 네 단계다.
        root = here
        for _ in range(4):
            root = os.path.dirname(root)
        hit = glob.glob(os.path.join(root, "**", _FLOW_FONT), recursive=True)
        f = TTFont(hit[0])
        em, hm, cm = f["head"].unitsPerEm, f["hmtx"], f.getBestCmap()
        for code, g in cm.items():
            _ADV[chr(code)] = hm[g][0] / em
    except Exception:
        _ADV["_bad"] = True
    _ADV["_"] = None


def flow_width_mm(line, size_pt, track_em):
    """이 줄을 한 줄로 늘어놓았을 때의 폭(mm)."""
    _load_adv() if "_" not in _ADV else None
    em = size_pt / 72.0 * 25.4
    bad = _ADV.get("_bad")
    w = 0.0
    for ch in line:
        a = (0.76 if ord(ch) > 0x2000 else 0.5) if bad else _ADV.get(ch, 0.5)
        w += (a + track_em) * em
    return w


def flow_html(line):
    """플로우노트 한 줄 → HTML. 기호 글자만 색을 입힌다.

    ⚠ 원고에 `**굵게**` 같은 표시가 오면 **별표가 그대로 인쇄된다**(실측:
      `**구식(outdated)**`). 조판이 벗겨 준다 — 원고 양식에도 쓰지 말라고 적었다.
    """
    line = _MD_BOLD.sub(r"\1", line)
    out, i = [], 0
    m = _LEAD_BRK.match(line)
    if m:                       # 줄머리 `[핵심]` — 표제라 색을 달리한다
        # ⚠ 딱지와 그 뒤 글은 **떨어지면 안 된다**(사용자 지적). 딱지만 앞줄에
        #   남고 글이 다음 줄로 넘어가면 `[결론]` 이 무엇의 결론인지 안 보인다.
        #   딱지 자체는 통째로 묶고, 뒤 빈칸은 NBSP 로 붙여 둔다.
        out.append('<span class="brk">%s</span>' % ESC(m.group(0).strip()))
        i = m.end()
        while i < len(line) and line[i] == " ":
            i += 1
        if i < len(line):
            out.append("\u00a0")
    buf = []
    for ch in line[i:]:
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


# 한 글자만 넘쳐 다음 줄로 떨어지는 줄은 **자간을 조여 한 줄에 앉힌다**
# (사용자 지시). 넘침이 이만큼 이내일 때만 손댄다 — 두 줄이 마땅한 줄까지
# 억지로 붙이면 글자가 뭉개진다.
_TIGHT_MAX = 1.12          # 단 폭 대비
_TIGHT_FLOOR = -0.19       # em, 자간 하한


# 조판기가 실제로 그린 폭은 우리 어림보다 조금 넓다(광문1 771줄 실측: 중앙
# 1.005 · 95% 1.014). 그 몫을 안 빼서 `애착`·`생김` 처럼 **한 글자가 다음 줄로**
# 떨어졌다(사용자 지적, 11곳). 단을 그만큼 좁게 보고 미리 조인다.
_WIDTH_SAFE = 0.985


def _tight(line, col_mm, size_pt, track_em):
    """이 줄이 조금 넘치면 한 줄에 앉힐 자간(em), 아니면 None."""
    if not col_mm or not line.strip():
        return None
    col_mm *= _WIDTH_SAFE
    w = flow_width_mm(line, size_pt, track_em)
    if w <= col_mm or w > col_mm * _TIGHT_MAX:
        return None
    em = size_pt / 72.0 * 25.4
    # 글자 사이마다 자간이 한 번씩 들어간다 — 필요한 만큼만 더 조인다
    need = track_em - (w - col_mm + 0.15) / (len(line) * em)
    return None if need < _TIGHT_FLOOR else need


_FHEAD = re.compile(r"^\s*\[([^\]]{1,12})\]\s*")


_RE_DUPMARK = re.compile(r"^(\s*)((?:[\u2192\u00b7\-=]\s*){2,})")


def _tidy_line(ln):
    """줄머리 표식이 겹친 것을 하나로 (`→ → 진한…` → `→ 진한…`)."""
    m = _RE_DUPMARK.match(ln)
    if not m:
        return ln
    first = m.group(2).strip()[0]
    return "%s%s %s" % (m.group(1), first, ln[m.end():].lstrip())


def flow_chunks(lines, cap=4):
    """플로우노트를 **마인드맵 덩어리**로 나눈다 — 3개나 4개.

    원고가 이미 `[도입]`·`[핵심]`·`[결론]` 같은 머리말로 흐름을 끊어 놓았다
    (광문1 66지문 전수: 100% 가 머리말을 갖고 있고 덩어리가 2~7개).
    그대로 쓰면 덩어리가 너무 잘아 상자가 일곱 개가 된다 — **붙어 있는 것들
    중 가장 짧은 짝부터 합쳐** 개수를 줄인다.

    글이 적으면(9줄 이하) 3덩어리, 많으면 4덩어리까지다(사용자 지시).
    거꾸로 덩어리가 셋이 안 되는데 한 덩어리가 길면 반으로 가른다.
    """
    lines = [_tidy_line(x) for x in lines]
    ch = []
    for ln in lines:
        if ch and _FHEAD.match(ln):
            ch.append([ln])
        elif ch:
            ch[-1].append(ln)
        else:
            ch.append([ln])
    if not ch:
        return []
    want = 3 if len(lines) <= 9 else cap
    # ⚠ 그냥 **가장 짧은 짝**부터 붙이면 한 덩어리만 일곱 줄로 부풀어 그 상자만
    #   글이 7.2pt 까지 줄어든다(본문2·41~42번 실측). 붙인 뒤 **가장 큰 덩어리가
    #   제일 작아지는** 짝을 고른다 — 넷이 고르게 나뉜다.
    while len(ch) > want:
        i = min(range(len(ch) - 1),
                key=lambda k: (max([len(ch[k]) + len(ch[k + 1])]
                                   + [len(c) for j, c in enumerate(ch)
                                      if j not in (k, k + 1)]),
                               len(ch[k]) + len(ch[k + 1])))
        ch[i] = ch[i] + ch.pop(i + 1)
    while len(ch) < 3 and max(len(c) for c in ch) >= 4:
        i = max(range(len(ch)), key=lambda k: len(ch[k]))
        c = ch.pop(i)
        h = (len(c) + 1) // 2
        ch[i:i] = [c[:h], c[h:]]
    return ch


def _fbox_size(M):
    """덩어리 상자 한 칸 크기 — `flow` 자리에서 바로 낸다(따로 적지 않는다)."""
    fl, ins, gap = M["flow"], M["fbox_inset"], M["fbox_gap"]
    return ((fl[2] - 2 * ins - gap) / 2.0, (fl[3] - 2 * ins - gap) / 2.0)


def flow_boxes(M, n, tall_first=False, w2=(1, 1), col1=None,
               col3=False):
    """덩어리 상자 자리 → `[(x, y, w, h)]` · 잇는 표식 자리 → `[(x, y, 세로냐)]`.

    읽는 차례는 **세로**다 — 왼쪽 단을 위에서 아래로 읽고 오른쪽 단으로 넘어간다.

        1  3
        2  4

    ⚠ 예전엔 가로로(1 2 / 3 4) 놓고 두 단 사이 한가운데에 아래 화살표를 뒀다.
      화살표가 어디서 어디로 가는지 안 보였다(사용자 지적). 이제 화살표는
      **그 단 안**, 제 상자 두 개 사이에만 놓는다. 셋이면 왼쪽 단에 둘을 쌓고
      오른쪽 단은 한 칸을 통으로 쓴다.
    """
    fl, ins, gap = M["flow"], M["fbox_inset"], M["fbox_gap"]
    x0, y0 = fl[0] + ins, fl[1] + ins
    w, h = fl[2] - 2 * ins, fl[3] - 2 * ins
    cw, chh = (w - gap) / 2.0, (h - gap) / 2.0
    d = M["fconn"]
    xr, yb = x0 + cw + gap, y0 + chh + gap
    # 3단 나란히 — 왼쪽에서 오른쪽으로만 읽는다.
    if n == 3 and col3:
        c3 = (w - 2 * gap) / 3.0
        box = [(x0 + k * (c3 + gap), y0, c3, h) for k in range(3)]
        conn = [(x0 + c3 + gap / 2 - d / 2, y0 + h / 2 - d / 2, ""),
                (x0 + 2 * c3 + 1.5 * gap - d / 2, y0 + h / 2 - d / 2, "")]
        return box, conn
    # 한 단 3칸 — 위에서 아래로만 읽는다. 순서를 배울 게 없어 가장 잘 읽힌다.
    if col1:
        tot = float(sum(col1)) or 1.0
        room = h - 2 * gap
        box, conn, yy = [], [], y0
        for k, wk in enumerate(col1):
            bh = room * wk / tot
            box.append((x0, yy, w, bh))
            yy += bh
            if k < len(col1) - 1:
                conn.append((x0 + w / 2 - d / 2, yy + gap / 2 - d / 2, "d"))
                yy += gap
        return box, conn
    down = lambda cx, yy: (cx + cw / 2 - d / 2, yy - d / 2, "d")
    if n <= 1:
        return [(x0, y0, w, h)][:n], []
    # ⚠ 단을 건너뛰는 자리는 **대각선**이다 — 왼쪽 단 아래 상자에서 오른쪽 단
    #   위 상자로 간다. 옆으로 곧게 뻗은 표식을 두면 위 칸 둘을 가로로 읽으라는
    #   말처럼 보인다(사용자 지적).
    across = (x0 + cw + gap / 2 - d / 2, y0 + h / 2 - d / 2, "x")
    if n == 2:
        return [(x0, y0, cw, h), (xr, y0, cw, h)], [across]
    if n == 3:
        # ⚠ 통 칸을 늘 오른쪽에 두면 거기 든 덩어리가 짧을 때 칸이 텅 빈다.
        #   **c1 과 c3 중 긴 쪽**이 통 칸을 갖고, 쌓이는 쪽은 두 덩어리의
        #   길이대로 나눈다(반씩 자르면 긴 덩어리만 글자가 줄었다).
        a, b = w2
        f = min(0.70, max(0.30, a / float(a + b))) if a + b else 0.5
        ha = (h - gap) * f
        hb = h - gap - ha
        if tall_first:
            return ([(x0, y0, cw, h), (xr, y0, cw, ha),
                     (xr, y0 + ha + gap, cw, hb)],
                    [across, down(xr, y0 + ha + gap / 2)])
        return ([(x0, y0, cw, ha), (x0, y0 + ha + gap, cw, hb),
                 (xr, y0, cw, h)],
                [down(x0, y0 + ha + gap / 2), across])
    # ⚠ 2→3(단을 건너뛰는 자리)을 안 이으면 흐름이 끊겨 보인다(사용자 지적).
    #   세 표식이 한 줄로 서서 `아래 → 옆 → 아래` 로 읽힌다.
    return ([(x0, y0, cw, chh), (x0, yb, cw, chh),
             (xr, y0, cw, chh), (xr, yb, cw, chh)],
            [down(x0, y0 + chh + gap / 2), across,
             down(xr, y0 + chh + gap / 2)])


_MARK = re.compile(r"^\s*(\[[^\]]{1,12}\]|→|·|-|=)[\s\u00a0]*")


def _hang_mm(txt, size_pt, track_em):
    """이 줄의 **줄머리 표식 폭**(mm). 표식이 없으면 0.

    ⚠ 모든 줄에 같은 값을 주면 표식 없는 줄까지 들여쓰기가 붙는다(사용자 지적).
      그리고 `→` 와 `·` 는 폭이 다르므로 값도 달라야 한다 — 실제 자폭으로 잰다.
    """
    m = _MARK.match(txt)
    if not m:
        return 0.0
    return flow_width_mm(m.group(0).replace("\u00a0", " "), size_pt, track_em)


def _wrap_n(txt, col_mm, size_pt, track_em, hang=0.0):
    """이 글이 폭 `col_mm` 안에서 **몇 줄이 되는지**. 낱말 단위로 접는다.

    ⚠ 예전엔 `전체 폭 ÷ 단 폭` 으로 어림했다. 낱말이 통째로 넘어가는 몫을
      못 세어 늘 낙관적이었고, 40개 상자에서 글이 아래로 삐져나왔다(실측).
    """
    col_mm *= _WIDTH_SAFE
    # 이어지는 줄은 표식만큼 좁다
    wide, narrow = col_mm, max(col_mm - hang, col_mm * 0.5)
    n, cur = 1, 0.0
    col_mm = wide
    for tok in re.split(r"(\s+)", txt):
        if not tok:
            continue
        w = flow_width_mm(tok, size_pt, track_em)
        if cur and cur + w > col_mm:
            if tok.strip():
                n += 1
                cur = 0.0
                col_mm = narrow
            else:
                continue
        while w > col_mm:               # 한 낱말이 한 줄보다 길면 글자로 끊긴다
            n += 1
            w -= col_mm
            col_mm = narrow
        cur += w
    return n


# 글자는 **1pt 안에서만** 줄인다(9.5→8.5). 2pt 씩 뛰면 잘못 들어간 것처럼
# 보인다(사용자 지적) — 모자란 몫은 행간으로 메운다.
_FLOW_FLOOR = 0.895
_LEAD_FLOOR = 0.78


def _flow_need(chunk, col_mm, M, size, lead_sc=1.0):
    """이 덩어리가 그 크기·행간에서 먹는 높이(mm)."""
    lead = M["flow_lead"] * (size / M["flow_size"]) * lead_sc
    need = 0.0
    for i, ln in enumerate(chunk):
        txt = _MD_BOLD.sub(r"\1", ln)
        if not i:
            txt = _FHEAD.sub("", txt)      # 머리말은 딱지로 빠진다
        if not txt.strip():
            continue
        need += _wrap_n(txt, col_mm, size, M["flow_track"],
                        _hang_mm(txt, size, M["flow_track"])) * lead
    return need


def flow_fit(chunk, col_mm, box_h, M, head=True):
    """안 들어가면 줄일 배율 → `(글자, 행간)`.

    ⚠ 예전엔 글자와 행간을 한꺼번에 줄여 9.5pt 옆에 7pt 가 앉았다 — 잘못 들어간
      것처럼 보인다(사용자 지적). **행간을 먼저** 조이고, 그래도 모자랄 때만
      글자를 1pt 안에서 내린다.
    """
    room = box_h - 2 * M["fbox_pad"] - 1.2 \
        - (M["fbox_head"] if head else 0.0)
    fsc = 1.0
    while True:
        lsc = 1.0
        while lsc >= _LEAD_FLOOR:
            if _flow_need(chunk, col_mm, M, M["flow_size"] * fsc, lsc) <= room:
                return fsc, round(lsc, 2)
            lsc = round(lsc - 0.03, 2)
        if fsc <= _FLOW_FLOOR:
            return _FLOW_FLOOR, _LEAD_FLOOR
        fsc = max(_FLOW_FLOOR, round(fsc - 0.035, 3))


def flow_rows(lines, col_mm=0.0, size_pt=9.0, track_em=-0.05):
    """플로우노트 줄들 → `<p>` 목록. 묶음 머리 앞은 띄운다.

    `col_mm` 을 주면 **한 글자만 넘치는 줄의 자간을 조여** 한 줄로 앉힌다.
    글자 수로 어림하면 안 되고(자폭이 제각각) 실제 자폭으로 재야 한다.
    """
    out = []
    for i, line in enumerate(lines):
        head = (line.lstrip()[:1] in _SEC) or bool(_LEAD_BRK.match(line))
        # ⚠ 덩어리 상자가 이미 갈래를 갈라 준다. 상자 **안**에서 또 벌리면
        #   이어지는 내용이 끊긴 것처럼 보인다(사용자 지적).
        cls = ""
        plain = _MD_BOLD.sub(r"\1", line)
        tr = _tight(plain, col_mm, size_pt, track_em)
        sty = [] if tr is None else ["letter-spacing:%.4fem" % tr]
        # ⚠ `[원인]`·`[반전]` 같은 머리말 줄까지 들여쓰면 들여쓰기 종류가 너무
        #   많아져 어지럽다(사용자 지적) — 머리말 줄은 들여쓰지 않는다.
        hang = 0.0 if _FHEAD.match(plain) else _hang_mm(plain, size_pt, track_em)
        if hang:
            sty.append("padding-left:%.2fmm;text-indent:-%.2fmm"
                       % (hang, hang))
        st = (' style="%s"' % ";".join(sty)) if sty else ""
        out.append('<p%s%s>%s</p>' % (cls, st, flow_html(line)))
    return out


def flow_col_mm(M):
    """플로우노트 **한 단**의 폭(mm) — 상자 − 좌우 여백 − 단 사이."""
    return (M["flow"][2] - 6.0 - 3.0) / 2.0


# 배지는 **어느 교재의 몇 강인지**가 보여야 한다. `1강 01` 만으로는 올림포스인지
# 수특인지 알 수 없다(사용자 지적). 꼬리말이 쓰는 단원 이름에서 교재만 떼어 앞에
# 붙인다 — 길게 쓰지 않고 `올림포스 1강 01` 처럼 짧게.
_BOOK_SHORT = {"수능특강": "수특"}


_RE_TAG_NO = re.compile(r"\d{1,2}\s*(?:강|과)|Unit\s*\d{1,2}", re.I)
_RE_UNIT_TAIL = re.compile(r"\s*(?:\d{1,2}\s*(?:강|과)|Unit\s*\d{1,2})\s*$", re.I)


def _badge_text(p):
    """배지 글 — `올림포스 1강 01` · `능률(민) SL2 본문2`.

    라벨이 `1강 01` 이면 **무슨 1강인지** 안 보인다(사용자 지적). 단원에서
    교재 이름을 떼어 앞에 붙인다. 라벨이 이미 강·과 번호를 들고 있으면
    단원의 번호는 빼고 **교재 이름만** 붙인다 — 안 그러면 `올림포스 1강 1강 01`.
    """
    lab = str(p.get("label") or "")
    # ⚠ `no`(=pno) 를 먼저 보면 `240941~42` 가 `240941` 로 잘린다. 합본 지문은
    #   **범위 그대로** 적어야 한다(사용자 지시) — 라벨이 이미 여섯 자리면 그것.
    tag = lab if re.fullmatch(r"\d{6}(?:[-~]\d{1,3})?", lab) \
        else str(p.get("no") or lab or "")
    unit = str(p.get("category") or p.get("unit") or "").strip()
    if p.get("_badge_raw") or not tag or not unit or unit in ("교과서", "모의고사"):
        return tag
    # 라벨이 강·과 번호를 들고 있을 때만 단원의 번호를 뗀다. `서술형 Practice`
    # 처럼 번호가 없는 라벨에서 떼면 **몇 강인지가 사라진다**.
    head = (_RE_UNIT_TAIL.sub("", unit).strip() or unit) \
        if _RE_TAG_NO.search(tag) else unit
    head = _BOOK_SHORT.get(head, head)
    if not head or head in tag:
        return tag
    return "%s %s" % (head, tag)


def _badge_parts(p):
    """배지를 **교재명 / 지문번호** 두 도막으로. 두 줄 배지가 쓴다."""
    tag = str(p.get("label") or p.get("no") or "")
    if re.fullmatch(r"\d{6}(?:[-~]\d{1,3})?", tag):
        return "모의고사", tag        # 위 칸은 갈래, 아래 칸은 지문번호
    full = _badge_text(p)
    if full != tag and full.endswith(tag):
        return full[:-len(tag)].strip(), tag
    # ⚠ 라벨 자체가 `능률(민) SL2 본문1` 처럼 통짜로 올 때가 있다(`_badge_raw`).
    #   그대로 두면 한 줄이 길어 칸을 넘는다 — 뒤쪽 번호 토막에서 가른다.
    m = re.search(r"\s((?:본문|Reading|RC)\s*\d+|\d+\s*강\s*\d+|\d+번|"
                  r"\d+~\d+번|[^\s]{1,8})$", full)
    if m and m.start():
        return full[:m.start()].strip(), m.group(1).strip()
    return "", full


def _badge2_fit(lines, w_mm, h_mm, M):
    """두 줄 배지 글자 크기 — 긴 줄이 폭 안에 들도록 줄인다."""
    base = M["badge_size"] * 0.86
    room = w_mm - 2 * M["badge2_pad"]
    em = base / 72.0 * 25.4
    w = max(sum(em if ord(c) > 0x2000 else em * 0.55 for c in t)
            for t in lines if t)
    sz = base if w <= room else max(5.2, base * room / w)
    # 두 줄이 상자 높이를 넘지 않게
    lead = min(M["badge2_lead"], (h_mm - 2 * M["badge2_pad"]) / 2.0)
    return sz, lead


def _badge_fit(tag, M):
    """배지 글자 크기 — 라벨이 길면 줄여서 판면 안에 둔다."""
    room = M["page_w"] - M["badge"][0] - M["margin_r"]      # 15→130mm
    em = M["badge_size"] / 72.0 * 25.4
    w = sum(em if ord(c) > 0x2000 else em * 0.55 for c in tag) + 2.0
    if w <= room:
        return ""
    return ";font-size:%.2fpt" % max(6.0, M["badge_size"] * room / w)


def _line_est(txt, width_mm, size_pt):
    """글이 몇 줄이 될지 어림. 한글은 한 자 1em, 영문은 0.5em 로 본다."""
    if not txt:
        return 0
    em = size_pt / 72.0 * 25.4
    w = sum(em if ord(c) > 0x2000 else em * 0.5 for c in txt)
    return max(1, int(w / max(width_mm, 1.0)) + (1 if w % width_mm else 0))


_CARD_LEAD_FLOOR = 0.70     # 7pt 글자에 2.94mm — 이 아래로는 붙는다


def _card_fit(c, M):
    """카드가 넘칠 것 같으면 미리 줄인다.

    카드는 34.6×22mm 로 작고 개수가 많다(한 책에 수백 장). 지문처럼 면마다 재면
    측정 조판이 감당이 안 된다 — 그래서 **자폭으로 줄 수를 세어** 단계로 줄인다.
    """
    # ⚠ `_wrap_n` 은 플로우노트 서체(도담도담)의 자폭표라 카드에는 안 맞는다
    #   — 그걸로 재 봤더니 넘침이 3장에서 20장으로 늘었다. 카드는 글자 수로
    #   어림하되 **23자**로 잡는다(24자면 낱말째 넘어가는 몫을 놓쳐 12장이 넘쳤다).
    per = 23.0
    lines = 0
    for txt in (("%s %s" % (c["w"], c.get("ko", ""))).strip(),
                ("= " + ", ".join(c.get("syn") or [])) if c.get("syn") else "",
                ("↔ " + ", ".join(c.get("ant") or [])) if c.get("ant") else ""):
        if txt:
            lines += max(1, int(len(txt) / per) + (1 if len(txt) % per else 0))
    room = int((M["card"][3] - 2 * M["card_pad"]) / M["card_lead"])
    if lines <= room:
        return ""
    # ⚠ 글자 크기는 **건드리지 않는다**(사용자 지시) — 카드마다 크기가 달라지면
    #   잘못 들어간 것처럼 보인다. 모자란 몫은 **행간**으로만 메운다.
    room_mm = M["card"][3] - 2 * M["card_pad"] - 0.6
    lead = max(M["card_lead"] * _CARD_LEAD_FLOOR, room_mm / lines)
    return ";line-height:%.2fmm" % lead


_CONN = ('<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
         '<path d="M%g %g L%g %g" stroke="currentColor" stroke-width="4"'
         ' stroke-dasharray="9 8" stroke-linecap="round" fill="none"/>'
         '<path d="%s" fill="currentColor"/></svg>')


# 파트 = **교재 단위**다(사용자 지시). 강마다 딱지를 달면 계단이 잘게 쪼개져
# 덮은 채로 찾는다는 귀 인덱스의 구실을 못 한다 — `올림포스 1강`~`8강` 은
# 딱지 하나(`올림포스`)로 잇는다.
_RE_TAB_TAIL = re.compile(r"\s*\d{1,2}\s*[강과]\s*$")
_RE_TAB_UNITNO = re.compile(r"\s*(?:Unit|Lesson|Day)\s*\d{1,2}\s*$", re.I)


def tab_part(cat, kind=""):
    """지문 단원 → (딱지 이름, 갈래). 갈래가 딱지 색을 정한다."""
    c = re.sub(r"\s+", " ", str(cat or "")).strip()
    if not c:
        return ("", "")
    if c.startswith("어휘"):
        return ("어휘", "k-voca")
    if "모의고사" in c:
        return ("모의고사", "k-mock")
    # ⚠ 갈래는 **띠와 같은 잣대**(`page_kind`)로 가른다. 여기서 따로 `N과` 를
    #   보면 `교과서 3과` 가 부교재로 새 버린다(실측).
    if kind == "k-mock":
        return ("모의고사", "k-mock")
    if kind == "k-unit" or (not kind and _RE_TAB_UNITNO.search(c)):
        name = _RE_TAB_UNITNO.sub("", _RE_TAB_TAIL.sub("", c)).strip()
        return (name or c, "k-unit")
    # 교과서는 책마다 이름이 다르다(`능률(민) SL2`·`비상(홍)`). 가장자리에서는
    # 그 이름보다 **갈래**가 눈에 들어와야 한다(사용자 지시).
    return ("교과서", "k-lesson")


def part_list(passages, voca=False):
    """책의 파트 차례 → [(딱지 이름, 갈래)]. 나온 순서 그대로, 어휘는 맨 뒤."""
    out = []
    for p in passages or ():
        if p.get("kind") == "memtest":
            continue
        c = (p.get("category") or "").strip()
        if not c:
            continue
        it = tab_part(c, page_kind(p))
        if it[0] and it not in out:
            out.append(it)
    if voca:
        out.append(("어휘", "k-voca"))
    return out


def _part_of(order, cat, kind=""):
    """지문 → (몇째 파트, 파트 수, 딱지 이름, 갈래, 같은 갈래 안 몇째)."""
    it = tab_part(cat, kind)
    i = order.index(it) if it in order else 0
    same = [j for j, x in enumerate(order) if x[1] == it[1]]
    return (i, len(order), it[0], it[1], same.index(i) if i in same else 0)


def side_tab(M, part, palette=None):
    """오른쪽 면 바깥 모서리의 파트 딱지 — 뒤 파트일수록 아래로 내려간다."""
    if not part or len(part) < 5:
        return ""
    i, n, text, kind, step = part
    if not text or n <= 0:
        return ""
    top, bot = M["tab_top"], M["tab_bot"]
    span = bot - top
    h = min(M["tab_h"], span / float(n) * 0.7)
    # 딱지 높이 + 틈만큼만 **조금씩** 내린다(사용자 지시). 면 끝까지 고르게 흩지
    # 않는다 — 파트가 많아 쪽번호에 닿을 때만 간격을 좁힌다.
    step_y = h + M.get("tab_gap", 1.0)
    if n > 1:
        step_y = min(step_y, (span - h) / float(n - 1))
    else:
        step_y = 0.0
    y = top + i * step_y
    bg = T.tab_color(kind, step, palette)
    x = M["page_w"] - M["tab_w"]
    return ('<div class="stab" style="%s;background:%s;color:%s">%s</div>'
            % (_box(x, y, M["tab_w"] + M["bleed"], h), bg, T.tab_ink(bg),
               ESC(text)))


def right_page(p, M, folio, category="", part=None, palette=None):
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
    # ⚠ 예전엔 한 상자에 두 단으로 흘려 넣었다. 왼쪽 단을 다 읽고 오른쪽으로
    #   건너뛰어야 해서 글의 **흐름**이 안 보였다(사용자 지시로 바꿈).
    #   이제 원고의 `[머리말]` 을 경계로 3~4덩어리로 끊어 마인드맵처럼 앉힌다.
    parts.append('<div class="flow" style="%s"></div>'
                 % _box(fl[0], fl[1], fl[2], fl[3]))
    ch = flow_chunks(p.get("flownote") or [])
    # 셋이면 어느 쪽이 통 칸인지는 **덩어리 길이**가 정한다
    # ⚠ 한 단 3칸은 세로가 1/3 로 줄어든다. 폭이 두 배가 돼도 줄은 거의 안
    #   줄어서(48mm 에서도 대부분 한 줄에 든다) **글이 많은 지문은 안 들어간다**.
    #   들어가는 지문만 한 단으로 놓고, 넘치는 지문은 두 단을 그대로 쓴다 —
    #   글자를 줄여 가며 한 단을 고집할 이유가 없다.
    # `flow3` 손잡이 — 3덩어리 짜임새를 골라 본다(auto/one/two/three).
    mode = str(M.get("flow3") or "auto")
    col1 = None
    if len(ch) == 3 and mode == "two":
        pass
    elif len(ch) == 3:
        wcol = M["flow"][2] - 2 * M["fbox_inset"] - 2 * M["fbox_pad"]
        need = [_flow_need(c, wcol, M, M["flow_size"]) + 2 * M["fbox_pad"]
                for c in ch]
        room = M["flow"][3] - 2 * M["fbox_inset"] - 2 * M["fbox_gap"]
        if mode == "one" or (mode == "auto" and sum(need) <= room):
            col1 = need
    tall = len(ch) == 3 and not col1 and len(ch[0]) > len(ch[2])
    w2 = (1, 1)
    if len(ch) == 3 and not col1:
        # ⚠ 줄 수로만 나누면 안 된다 — 상자마다 여백·머리말 딱지가 8.6mm 씩
        #   먼저 먹는다. 그걸 안 세어 짧은 덩어리 상자가 눌리고 글자가 줄었다.
        cwv = _fbox_size(M)[0] - 2 * M["fbox_pad"]
        ov = 2 * M["fbox_pad"] + M["fbox_head"] + 1.2
        pair = (ch[1], ch[2]) if tall else (ch[0], ch[1])
        w2 = tuple(_flow_need(c, cwv, M, M["flow_size"]) + ov for c in pair)
    boxes, conns = flow_boxes(M, len(ch), tall, w2, col1,
                              mode == "three")
    for n, (c, (bx, by, bw, bh)) in enumerate(zip(ch, boxes)):
        col = bw - 2 * M["fbox_pad"]
        fsc, lsc = flow_fit(c, col, bh, M, not col1)
        fst = "" if (fsc, lsc) == (1.0, 1.0) else \
            ' style="font-size:%gpt;line-height:%gmm"' % (
                round(M["flow_size"] * fsc, 2),
                round(M["flow_lead"] * fsc * lsc, 2))
        # ⚠ 화살표만으로는 칸을 가로로 읽을 여지가 남는다(사용자 지적).
        #   머리말 앞에 **차례 번호**를 박아 흐름을 못 박는다.
        m = _FHEAD.match(c[0])
        lab = ('<span class="fbn">%d</span>%s' % (
            n + 1, ('<span class="fbt">%s</span>' % ESC(m.group(1)))
            if m else ""))
        body = list(c)
        if m:
            body[0] = c[0][m.end():]
        body = [x for x in body if x.strip()]
        if col1:
            # 한 단은 세로가 빠듯하다 — 딱지를 따로 한 줄 쓰지 않고 첫 줄에 붙인다
            head = ""
            rows = flow_rows(body[1:], col, M["flow_size"] * fsc,
                             M["flow_track"])
            rows.insert(0, '<p class="fbl">%s%s</p>'
                        % (lab, flow_html(body[0]) if body else ""))
        else:
            head = '<div class="fbh">%s</div>' % lab
            rows = flow_rows(body, col, M["flow_size"] * fsc, M["flow_track"])
        # 모눈은 판 한 장이다 — 이 상자가 판 안에서 놓인 만큼 밀어 본다
        bg = ";background-size:%gmm %gmm;background-position:%gmm %gmm" % (
            fl[2], fl[3], -(bx - fl[0]), -(by - fl[1]))
        parts.append('<div class="fbox" style="%s%s">%s<div class="fbi"%s>'
                     '%s</div></div>'
                     % (_box(bx, by, bw, bh), bg, head, fst, "".join(rows)))
    # 잇는 표식 — **점선 한 줄에 아주 작은 화살촉**. 방향만 알려 주면 된다.
    #   ⚠ 예전엔 대각선만 커서 눈에 튀었다(사용자 지적) — 셋 다 같은 규격이다.
    #   색도 주황이 아니라 상자 테두리와 같은 색을 쓴다.
    for cx, cy, kind in conns:
        ln = M["fconn_len"]
        cx += M["fconn"] / 2
        cy += M["fconn"] / 2
        if kind == "x":
            parts.append('<div class="fconn x" style="%s">%s</div>'
                         % (_box(cx - ln / 2, cy - ln / 2, ln, ln),
                            _CONN % (6, 94, 78, 22, "M96 4 L74 10 L90 26 Z")))
        elif kind == "d":
            parts.append('<div class="fconn" style="%s">%s</div>'
                         % (_box(cx - ln / 2, cy - ln / 2, ln, ln),
                            _CONN % (50, 4, 50, 78, "M50 96 L40 72 L60 72 Z")))
        else:                       # 옆으로
            parts.append('<div class="fconn" style="%s">%s</div>'
                         % (_box(cx - ln / 2, cy - ln / 2, ln, ln),
                            _CONN % (4, 50, 78, 50, "M96 50 L72 40 L72 60 Z")))
    # 주제 / 요약문
    parts.append('<div class="topicband" style="%s"></div>'
                 % _box(tb[0], tb[1], tb[2], tb[3]))
    # ⚠ 딱지 자리를 **줄 수로 어림해 놓으면** 주제가 두 줄일 때 요약문 딱지
    #   옆에 주제 둘째 줄이 온다(사용자 지적, 두 번). 어림을 버리고 딱지와 글을
    #   **한 줄로 묶는다** — 브라우저가 알아서 맞추므로 어긋날 수가 없다.
    tsc = p.get("topic_scale", 1.0)
    tst = "" if tsc == 1.0 else ";font-size:%gpt;line-height:%gmm" % (
        M["topic_size"] * tsc, M["topic_lead"] * tsc)
    tt = []
    for cls, lab, key in (("t", "주제", "topic"), ("s", "요약문", "summary")):
        if not p.get(key):
            continue
        tt.append('<div class="trow"><span class="tbadge %s">%s</span>'
                  '<span class="ttext">%s</span></div>'
                  % (cls, lab, ESC(p[key])))
    parts.append('<div class="topictext" style="%s%s">%s</div>'
                 % (_box(tb[0] + 2.0, tb[1] + 1.2,
                         tb[2] - 4.0),
                    tst, "".join(tt)))
    # 동반의어
    parts.append('<div class="synpanel" style="%s"></div>'
                 % _box(sp[0], sp[1], sp[2], sp[3]))
    parts.append('<div class="syntitle" style="%s">%s동반의어</div>'
                 % (_box(st[0], st[1], st[2], st[3]), _svg("synmark")))
    # ⚠ 동그라미는 괘선이 **끊기는 바로 그 점**에 앉는다 — 제목 덮개의 좌·우
    #   끝이고, 높이는 괘선 자체(패널 윗변)다. 완성본 실측: 지름 1.05mm,
    #   중심 x = 20.70 / 43.33(덮개 양끝), y = 88.11(패널 윗변). 옆에 띄워 두면
    #   선과 어긋나 엉뚱한 데 점이 찍힌 것처럼 보인다(사용자 지적).
    dot = M["syntitle_dot"]
    for cx in (st[0], st[0] + st[2]):
        parts.append('<div class="syndot" style="%s"></div>'
                     % _box(cx - dot / 2.0, sp[1] - dot / 2.0))
    # ⚠ 카드가 9장이 안 되면 **빈 상자를 그리지 않는다**. 색면만 남으면 덜 만든
    #   것처럼 보인다(기존 포켓북에서 온 지문은 6장짜리도 있다).
    cards = (p.get("synonyms") or [])[:9]
    for i in range(len(cards)):
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
    parts.append(side_tab(M, part, palette))
    # ⚠ 띠 색은 **펼침면 단위**다. 왼쪽 면에만 주면 한 지문의 두 면이 다른
    #   색으로 나간다(사용자 지적).
    return ('<section class="pg %s"><div class="trim">%s</div></section>'
            % (page_kind(p), "".join(parts)))


def memtest_page(p, M, folio, answer, category="", part=None,
                 palette=None):
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
    # 귀 인덱스는 **오른쪽 면에만** — 암기 TEST 는 정답면이 오른쪽이다.
    if answer:
        parts.append(side_tab(M, part, palette))
    return '<section class="pg"><div class="trim">%s</div></section>' % "".join(parts)


def split_half(p):
    """장문 지문을 **문장 경계에서 반으로** 갈라 두 벌로 돌려준다.

    글자 수가 절반에 가장 가까운 문장 끝에서 자른다. 해석도 같은 비율로
    나눈다 — 정확히 짝지을 수는 없지만 눈으로 따라갈 만큼은 맞는다.
    """
    runs = p.get("passage_runs") or []
    tot = sum(len(x.get("t") or "") for x in runs)
    if tot < 400:
        return [p]
    cut, acc, best = 0, 0, None
    for i, x in enumerate(runs):
        acc += len(x.get("t") or "")
        if (x.get("t") or "").rstrip().endswith((".", "?", "!", "\u201d")):
            d = abs(acc - tot / 2)
            if best is None or d < best:
                best, cut = d, i + 1
    if not cut or cut >= len(runs):
        cut = len(runs) // 2
    tr = p.get("translation") or ""
    # ⚠ 예전엔 **띄어쓰기**에서 잘라 해석이 문장 한가운데서 면이 갈렸다
    #   (`…파티를 떠나 그가 옷을` / `빌릴 수 있는 가게로 갔다.`, 연구원 지적).
    #   **문장 끝**(`.`·`?`·`!`)에서 가장 가까운 자리를 고른다.
    aim = int(len(tr) * (sum(len(x.get("t") or "")
                             for x in runs[:cut]) / max(tot, 1)))
    ends = [m.end() for m in re.finditer(r"[.?!\u201d]\s", tr)]
    k = min(ends, key=lambda e: abs(e - aim)) if ends else tr.find(" ", aim)
    # ⚠ 자를 자리를 못 찾으면(`k<=0`) 예전엔 뒤쪽 해석을 **빈 채로** 뒀다 —
    #   글이 통째로 사라진다. 글은 어떤 경우에도 지우지 않는다(사용자 지시):
    #   못 자르겠으면 **앞쪽에 다 싣는다**.
    ta, tb = (tr[:k].strip(), tr[k:].strip()) if k > 0 else (tr, "")
    if tr and not (ta + tb).strip():
        ta = tr
    a = dict(p, passage_runs=runs[:cut], translation=ta, illust=None, _part=1)
    b = dict(p, passage_runs=runs[cut:], translation=tb, illust=None, _part=2)
    return [a, b]


_BORDER_MM = 0.5 * 25.4 / 72          # 상자 테두리 .5pt


def memo_box(M):
    """메모 면 흰 모눈 상자 → (x, y, 폭, 높이, 칸, 가로 칸 수, 세로 칸 수) mm.

    판(`flow`) 안쪽으로 `fbox_inset` 만큼 물린 자리에, **칸 크기(FLOW NOTE 와
    같은 `flow_grid`)로 딱 나눠떨어지는** 상자를 가운데 앉힌다. 한 칸이 안 되는
    나머지는 판 여백으로 양쪽에 똑같이 나눈다 — 모눈이 네 변 모두 테두리에서
    끝나고 가장자리에 얇은 칸이 남지 않는다.
    """
    fx, fy, fw, _fh = M["flow"]
    inset, cell = M["fbox_inset"], M["flow_grid"]
    aw, ah = fw - 2 * inset, M["memo_h"] - 2 * inset
    cols = int((aw - 2 * _BORDER_MM) // cell)
    rows = int((ah - 2 * _BORDER_MM) // cell)
    bw, bh = cols * cell + 2 * _BORDER_MM, rows * cell + 2 * _BORDER_MM
    return (fx + inset + (aw - bw) / 2.0, fy + inset + (ah - bh) / 2.0,
            bw, bh, cell, cols, rows)


def memo_page(M, folio, kind="", part=None, palette=None):
    """메모 면 — 오른쪽 면이 빌 때 빈 채로 두지 않는다(사용자 지시).

    FLOW NOTE 면과 같은 짜임이다: 딱지와 한 몸인 베이지 판 + 판 안쪽 흰 모눈 상자.
    """
    fl = M["flow"]
    bx, by, bw, bh, cell, cols, rows = memo_box(M)
    grid = "background-size:%.4fmm %.4fmm" % (cols * cell, rows * cell)
    return ('<section class="pg %s"><div class="trim">'
            '<div class="flowchip" style="%s">%sMEMO</div>'
            '<div class="flow" style="%s"></div>'
            '<div class="mbox" style="%s;%s"></div>'
            '<div class="folio r" style="%s"><b>%s</b></div>'
            '%s</div></section>'
            % (kind,
               _box(M["flow_chip"][0], M["flow_chip"][1],
                    M["flow_chip"][2], M["flow_chip"][3]), _svg("chip_flow"),
               _box(fl[0], fl[1], fl[2], M["memo_h"]),
               _box(bx, by, bw, bh), grid,
               _box(M["margin_l"], M["folio_y"],
                    M["page_w"] - M["margin_l"] - 15.0), folio,
               side_tab(M, part, palette)))


def body_pages(rows, folio_start=2, nv=0):
    """본문 면 수(간지 빼고) — **G-P1 과 같은 셈**이다.

    조판과 검수가 각자 세면 어긋난다(`page_plan` 머리 주석). 어휘는 왼쪽 면부터
    시작하므로 앞이 홀수로 끝나면 빈 면이 한 장 낀다.
    """
    per = [lead + step for lead, step in page_plan(rows, folio_start)]
    gap = 1 if (nv and (int(folio_start) + sum(per)) % 2) else 0
    return sum(per) + gap + int(nv)


def page_plan(rows, folio_start=2):
    """지문마다 **빈 면 몇 장 뒤에 몇 면을 쓰는지** → `[(빈 면, 면 수)]`.

    조판과 검수가 각자 세면 어긋난다 — 짤지문을 넣자마자 G-P3 가 24지문에서
    엉뚱하게 울렸다(실측). 한 곳에서 세고 둘 다 이걸 본다.
    """
    out, folio = [], int(folio_start)
    for r in rows:
        if r.get("kind") == "memtest" or r.get("short"):
            out.append((0, 1)); folio += 1
            continue
        lead = 1 if folio % 2 else 0     # 온전한 지문은 왼쪽 면에서 시작한다
        folio += lead + 2
        out.append((lead, 2))
    return out


def _memo_kind(p):
    return page_kind(p)


def build_html(data, css_name="pocket.css"):
    # 작업대에서 지면을 눌러 그 자리를 고칠 수 있게 — **렌더 직전에 한 번**.
    # ⚠ 안 하면 클릭해도 조용히 아무 일도 안 일어난다(자리표가 없으니까).
    _refs.index_paths(data, [("passages",), ("passages", "cards")])
    M = dict(T.METRICS)
    M.update(data.get("metrics") or {})
    pages = []
    folio = int(data.get("folio_start", 1))
    # 귀 인덱스 — 파트 차례를 먼저 세어야 딱지가 몇 칸씩 내려갈지 정해진다.
    order = part_list(data["passages"], bool(data.get("voca")))
    pal = data.get("palette") or None
    if data.get("cover"):
        pages.append('<section class="pg"><div class="trim">'
                     '<img src="%s" style="width:100%%;height:100%%;'
                     'object-fit:cover"></div></section>' % ESC(data["cover"]))
        folio += 1
    for p, (lead, _step) in zip(data["passages"],
                               page_plan(data["passages"], folio)):
        cat = p.get("category", "")
        for _ in range(lead):
            # ⚠ 짝을 맞추려 끼우는 면은 **빈 채로 두지 않는다**(사용자 지시).
            # 메모 면도 오른쪽 면이면 딱지를 단다 — 안 그러면 가장자리
            # 계단이 그 한 장에서 끊긴다.
            pages.append(memo_page(
                M, folio, page_kind(p),
                _part_of(order, cat, page_kind(p)) if folio % 2 else None,
                pal))
            folio += 1
        if p.get("kind") == "memtest":
            pg = memtest_page(p, M, folio, p.get("answer"), cat,
                              _part_of(order, cat, page_kind(p)), pal)
            if pg:
                pages.append(pg); folio += 1
            continue
        # ⚠ 모의고사 짤지문(18·19·25~28·43~45번)은 오른쪽 면이 없다 — 안내문·
        #   도표라 플로우노트를 쓸 거리가 없다(사용자 지시). 두 개가 한 펼침면에
        #   나란히 들어간다.
        if p.get("short"):
            pages.append(left_page(p, M, folio)); folio += 1
            continue
        if p.get("split"):
            for half in split_half(p):
                pages.append(left_page(half, M, folio)); folio += 1
            continue
        pages.append(left_page(p, M, folio)); folio += 1
        pages.append(right_page(p, M, folio, cat,
                                _part_of(order, cat, page_kind(p)), pal))
        folio += 1
    # 어휘 파트는 **맨 뒤**다(26-1-기말 완성본과 같은 자리). 한 DAY 가 펼침면
    # 하나이므로 왼쪽 면부터 시작해야 짝이 맞는다.
    for i, vp in enumerate(data.get("voca") or ()):
        if i == 0 and folio % 2:
            pages.append('<section class="pg k-voca"><div class="trim">'
                         '</div></section>')
            folio += 1
        pages.append(voca_page(vp, M, folio,
                               "l" if folio % 2 == 0 else "r",
                               _part_of(order, "어휘", "k-voca"), pal))
        folio += 1
    # 인쇄 규약 — 총 면수 4의 배수. 모자란 면은 **MEMO 면**(빈 면 금지, 사용자
    # 지시). 오른쪽 면이면 귀 딱지도 단다(마지막 파트).
    pad = int(data.get("pad_pages") or 0)
    if pad:
        last = next((q for q in reversed(data["passages"])
                     if q.get("kind") != "memtest"), {})
        kind = "k-voca" if data.get("voca") else page_kind(last)
        cat = "어휘" if data.get("voca") else (last.get("category") or "")
        for _ in range(pad):
            pages.append(memo_page(
                M, folio, kind,
                _part_of(order, cat, kind) if folio % 2 else None, pal))
            folio += 1
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<title>%s</title><link rel="stylesheet" href="%s"></head><body>'
            '%s</body></html>'
            % (ESC(data.get("title", "포켓북")), css_name, "".join(pages)))
