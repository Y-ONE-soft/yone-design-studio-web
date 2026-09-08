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


def runs_html(runs):
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
            out.append('<mark class="hl-%s">%s%s</mark>' % (cur_hl, ico, s))
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
    tag = _badge_text(p)
    if tag:
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


def voca_page(pg, M, folio, side="l"):
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
    head = ('<div class="vhead" style="%s">%s</div>'
            % (_box(x, hd[1], hd[2], hd[3]), ESC(pg["day"])))
    body = ('<div class="voca" style="%s">%s</div>'
            % (_box(x, v[1], v[2], v[3]), "".join(ents)))
    if side == "l":
        foot = ('<div class="folio" style="%s"><b>%s</b> POCKET BOOK</div>'
                % (_box(12.9, M["folio_y"]), folio))
    else:
        foot = ('<div class="folio r" style="%s">'
                '<span style="color:var(--ink)">VOCA</span> <b>%s</b></div>'
                % (_box(M["margin_l"], M["folio_y"],
                        M["page_w"] - M["margin_l"] - 15.0), folio))
    return ('<section class="pg k-voca"><div class="trim">%s%s%s</div></section>'
            % (head, body, foot))


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
_TIGHT_FLOOR = -0.16       # em, 자간 하한


def _tight(line, col_mm, size_pt, track_em):
    """이 줄이 조금 넘치면 한 줄에 앉힐 자간(em), 아니면 None."""
    if not col_mm or not line.strip():
        return None
    w = flow_width_mm(line, size_pt, track_em)
    if w <= col_mm or w > col_mm * _TIGHT_MAX:
        return None
    em = size_pt / 72.0 * 25.4
    # 글자 사이마다 자간이 한 번씩 들어간다 — 필요한 만큼만 더 조인다
    need = track_em - (w - col_mm + 0.15) / (len(line) * em)
    return None if need < _TIGHT_FLOOR else need


def flow_rows(lines, col_mm=0.0, size_pt=9.0, track_em=-0.05):
    """플로우노트 줄들 → `<p>` 목록. 묶음 머리 앞은 띄운다.

    `col_mm` 을 주면 **한 글자만 넘치는 줄의 자간을 조여** 한 줄로 앉힌다.
    글자 수로 어림하면 안 되고(자폭이 제각각) 실제 자폭으로 재야 한다.
    """
    out = []
    for i, line in enumerate(lines):
        head = (line.lstrip()[:1] in _SEC) or bool(_LEAD_BRK.match(line))
        cls = ' class="sec"' if head and i else ""
        tr = _tight(_MD_BOLD.sub(r"\1", line), col_mm, size_pt, track_em)
        st = "" if tr is None else ' style="letter-spacing:%.4fem"' % tr
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
    tag = str(p.get("no") or p.get("label") or "")
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
    fsc = p.get("flow_scale", 1.0)
    rows = flow_rows(p.get("flownote") or [], flow_col_mm(M),
                     M["flow_size"] * fsc, M["flow_track"])
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
    # ⚠ 동그라미는 **제목 바로 양옆** — 괘선이 제목 때문에 끊기는 그 자리다.
    #   판면 모서리에 두면 엉뚱한 데 점이 찍힌다(사용자 지적).
    dot = M["syntitle_dot"]
    for x in (st[0] - M["syntitle_dot_gap"] - dot,
              st[0] + st[2] + M["syntitle_dot_gap"]):
        parts.append('<div class="syndot" style="%s"></div>'
                     % _box(x, st[1] + st[3] / 2.0 - dot / 2.0))
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
    # ⚠ 띠 색은 **펼침면 단위**다. 왼쪽 면에만 주면 한 지문의 두 면이 다른
    #   색으로 나간다(사용자 지적).
    return ('<section class="pg %s"><div class="trim">%s</div></section>'
            % (page_kind(p), "".join(parts)))


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
    # 어휘 파트는 **맨 뒤**다(26-1-기말 완성본과 같은 자리). 한 DAY 가 펼침면
    # 하나이므로 왼쪽 면부터 시작해야 짝이 맞는다.
    for i, vp in enumerate(data.get("voca") or ()):
        if i == 0 and folio % 2:
            pages.append('<section class="pg k-voca"><div class="trim">'
                         '</div></section>')
            folio += 1
        pages.append(voca_page(vp, M, folio, "l" if folio % 2 == 0 else "r"))
        folio += 1
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<title>%s</title><link rel="stylesheet" href="%s"></head><body>'
            '%s</body></html>'
            % (ESC(data.get("title", "포켓북")), css_name, "".join(pages)))
