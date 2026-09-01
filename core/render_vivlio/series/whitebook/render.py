"""화이트북 계열 렌더러 — data.json → build/index.html.

지면 규칙(인디자인 완성본 `배재1_화이트북01_내지_v2_2.pdf` 23~27·40면 실측):

  · **한 면 4문항 사분면 고정.** 한 칸 122.5mm, 두 단(82.05mm) × 두 칸.
    `column-fill: auto` 로 왼 단을 채운 뒤 오른 단으로 넘어간다 — 문항이 짧아도
    칸을 비워 두는 것이 이 교재의 설계다(사용자 확정).
  · Day 하나 = 20문항 = 정확히 5면. Day 는 새 면에서 시작한다.
  · 정답은 **뒤에 몰아서** — Day 마다 새 면, 2단 흐름.

한글은 8.77pt Noto, 로마자는 9.21pt Minion Semibold/Regular — 인디자인 합성 서체를
그대로 옮기려고 **한글 덩어리만 `<span class="kr">`** 로 감싼다(크기가 다르면 줄바꿈
지점이 달라진다).
"""
import html

from core.render_vivlio import richtext as _rt
import os
import re

from core.render_vivlio import stage
from core.render_vivlio import refs as _refs

# 판면 기본값(mm) — 완성본 실측. 책이 필요하면 config.metrics 로 덮는다.
DEFAULT_METRICS = {
    "slot": 122.5,        # 사분면 한 칸
    "col_w": 82.05,       # 문제 한 단
    "col_gap": 3.65,      # 문제 단 사이
    "ans_gap": 6.25,      # 정답 단 사이
    "body_top": 30.0,     # 판면 위 (문제면)
    "body_h": 246.0,      # 판면 높이 = 사분면 두 칸 + 여유
    "ans_top": 16.0,      # 판면 위 (정답면)
    "ans_h": 258.0,
}

RE_HANGUL = re.compile(r"[가-힣ㄱ-ㆎ][가-힣ㄱ-ㆎ"
                       r"0-9 ,.·~!?()\[\]'\"%:;/－-]*")
RE_UND = re.compile(r"_{3,}")
# ⚠ `esc_gap` 이 먼저 돌아 공백이 `&nbsp;` 가 된다 — 둘 다 받아야 한다.
RE_BRACKET_GAP = re.compile(r"\[(?:\s|&nbsp;)+\]")
RE_BULLET = re.compile(r"^\s*([∙•·])\s*")


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    return m


# ------------------------------------------------------------------ 인라인

def esc_gap(s):
    """연속 공백(의미 있는 간격)을 보존 — HTML 은 공백을 축약한다."""
    return re.sub(r" {2,}", lambda m: "&nbsp;" * (len(m.group(0)) - 1) + " ", s)


def _wrap_kr(s):
    """한글 덩어리를 `.kr` 로 — 로마자와 크기가 다르다(합성 서체)."""
    return RE_HANGUL.sub(lambda m: f'<span class="kr">{m.group(0)}</span>', s)


def _wrap_gapx(s):
    """빈칸 표기(`__________`, `[       ]`)는 본문 서체가 아니다."""
    s = RE_UND.sub(lambda m: f'<span class="gapx">{m.group(0)}</span>', s)
    return RE_BRACKET_GAP.sub(
        lambda m: f'<span class="gapx">{m.group(0)}</span>', s)


def esc1(x):
    """한 조각 — 평문은 예전 그대로, 작업대가 건 글자 서식은 살려서.
    # ⚠ 작업대에서 **글자 단위 서식**을 걸면 이 값이 서식 조각 목록이 된다.
    #   그때 `html.escape()` 는 죽고 **조판이 통째로 안 나온다**(실측: 라벨에
    #   자간을 줬더니 `'list' object has no attribute 'replace'`).
    """
    if isinstance(x, str):
        return html.escape(x)
    return inl(x)


def inl(x):
    """rich 세그먼트 → HTML"""
    if x is None:
        return ""
    if isinstance(x, str):
        return _wrap_gapx(_wrap_kr(esc_gap(html.escape(x))))
    if isinstance(x, dict):
        t = _wrap_gapx(_wrap_kr(esc_gap(html.escape(x.get("t", "")))))
        # 작업대에서 건 **글자 단위 서식**(크기·색·자간·이름 붙인 문자 스타일).
        # ⚠ 안 받으면 저장은 되는데 지면은 그대로다 — 조용해서 더 나쁘다.
        a = _rt.seg_attr(x)
        if a:
            t = f"<span{a}>{t}</span>"
        if x.get("u"):
            t = f"<u>{t}</u>"
        if x.get("b"):
            t = f"<b>{t}</b>"
        if x.get("i"):
            t = f"<i>{t}</i>"
        t += _rt.foot_html(x)                # 각주(있으면)
        return t
    return "".join(inl(i) for i in x)


def plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("t", "")
    if x is None:
        return ""
    return "".join(plain(i) for i in x)


# ── 클릭 편집용 자리표
REF_SPEC = ("days", ("problems", "answers"))


def index_refs(data):
    return _refs.index(data, REF_SPEC)


def ref_of(obj, sub=""):
    return _refs.of(obj, sub)


def _mark(ref, base=""):
    return _refs.mark(ref, base)


# ------------------------------------------------------------------ 조각

def hdr_day(label):
    """문제 머리 — 띠 위의 흰 패널 + 청록 탭."""
    n = label.split()[-1]
    return ('<div class="dayhdr">'
            '<div class="panel"></div>'
            f'<div class="tab"><span class="w">DAY</span>'
            f'<span class="n">{html.escape(n)}</span></div>'
            '<div class="ttl">EXERCISE</div></div>')


def hdr_ans(label):
    """정답 머리 — 베이지 띠에 걸린 청록 탭."""
    return ('<div class="anshdr"><div class="tab">'
            '<span class="l">정답&nbsp;&nbsp; |&nbsp;&nbsp; </span>'
            f'<span class="d">{html.escape(label)}</span></div></div>')


def foot_left(brand):
    """짝수(왼쪽) 면 꼬리말 — 쪽번호 + 교재명. **어느 면이든 같다** → 한 번만.

    색이 셋이라 마진 박스 하나로는 안 된다 → running 요소.
    """
    return ('<div class="footL"><span class="pg"></span>'
            '<span class="bar">|</span>'
            f'<span class="lb">{html.escape(brand)}</span></div>')


def foot_right(label):
    """홀수(오른쪽) 면 꼬리말 — 섹션 라벨 + 쪽번호."""
    return (f'<div class="footR"><span class="lb">{html.escape(label)}</span>'
            '<span class="bar">|</span><span class="pg"></span></div>')


def _bullet(body_html, src):
    m = RE_BULLET.match(src)
    if not m:
        return body_html
    # 머리기호는 본문 서체가 아니다 — 10pt Noto Thin
    return re.sub(r"^\s*[∙•·]\s*",
                  '<span class="bu">•</span> ', body_html, count=1)


def _starts_kr(rich):
    p = plain(rich).lstrip()
    return bool(p) and "\uac00" <= p[0] <= "\ud7a3"


def render_question(item):
    q = ref_of(item)
    o = ['<div class="q">']
    o.append(f'<p{_mark(q and q + ".stem", "head")}>'
             f'<span class="no">{item["no"]:02d}</span>'
             f'{inl(item["stem"])}</p>')
    blocks = item["blocks"]
    for bi, b in enumerate(blocks):
        t = b["t"]
        br = f"{q}.blocks.{bi}" if q else ""
        if t == "bogi":
            o.append('<div class="bogi"><p class="bt">&lt; 보기&gt;</p>')
            for k, x in enumerate(b["items"]):
                o.append(f'<p{_mark(br and f"{br}.items.{k}", "bi")}>'
                         f'{_bullet(inl(x), plain(x))}</p>')
            o.append('</div>')
        elif t == "passage":
            o.append('<div class="pbox">')
            for k, x in enumerate(b["paras"]):
                o.append(f'<p{_mark(br and f"{br}.paras.{k}")}>{inl(x)}</p>')
            o.append('</div>')
        elif t == "choice":
            # ⚠ 표지 뒤 공백은 **글자로 넣지 않는다.** 로마자 선지와 한글 선지는
            #   인디자인에서 들여쓰기가 다르다(4.25mm vs 3.84mm) → 여백으로 준다.
            cls = "ch kr1" if _starts_kr(b["body"]) else "ch"
            o.append(f'<p{_mark(br and br + ".body", cls)}>'
                     f'<span class="m">{b["mark"]}</span>{inl(b["body"])}</p>')
        elif t == "trans":
            o.append(f'<p{_mark(br and br + ".body", "tr")}>'
                     f'<span class="ar">→</span>{inl(b["body"])}</p>')
    o.append('</div>')
    return "".join(o)


def render_answer(a):
    ar = ref_of(a)
    o = ['<div class="a">']
    o.append(f'<p{_mark(ar and ar + ".answer", "ahead")}>'
             f'<span class="no">{a["no"]:02d}</span>{inl(a["answer"])}</p>')
    for k, x in enumerate(a["notes"]):
        o.append(f'<p{_mark(ar and f"{ar}.notes.{k}", "note")}>{inl(x)}</p>')
    o.append('</div>')
    return "".join(o)


# ------------------------------------------------------------------ 문서

MODE_FILE = {None: "index.html", "measure": "measure.html"}


def document(cfg, data, mode=None):
    o = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         f'<title>{html.escape(cfg.book.get("title", ""))}</title>',
         '<link rel="stylesheet" href="theme.css">',
         stage.BOOK_CSS_LINKS]
    if mode == "measure":
        # 한 면에 한 문항만 — 자연 높이를 잰다
        o.append('<style>.qgrid{column-count:1;width:%.2fmm}'
                 '.q{height:auto!important;break-before:page}</style>'
                 % metrics_of(cfg)["col_w"])
    o.append('</head><body>')
    o.append(foot_left(cfg.book.get("brand", "")))
    if mode != "measure":
        # 앞 간지 자리 — 마감 때 완성본 아트워크 면으로 바뀐다(§DIV1§).
        # ⚠ 흐름 안에 실제 한 면으로 두어야 쪽번호와 좌우(짝/홀)가 완성본과 맞는다.
        o.append('<div class="divider"><span>§DIV1§</span></div>')

    for D in data["days"]:
        lab = D["label"]
        o.append('<section class="sec sec-q">')
        o.append(f'<div class="secmark">{html.escape(lab)}</div>')
        o.append(foot_right(lab))
        o.append(hdr_day(lab))
        o.append('<div class="qgrid">')
        for it in D["problems"]:
            o.append(render_question(it))
        o.append('</div></section>')

    if mode != "measure":
        for D in data["days"]:
            lab = D["label"]
            o.append('<section class="sec sec-a">')
            o.append(f'<div class="secmark">{html.escape(lab)}</div>')
            o.append(foot_right(lab))
            o.append(hdr_ans(lab))
            o.append('<div class="answers">')
            for a in D["answers"]:
                o.append(render_answer(a))
            o.append('</div></section>')
    o.append('</body></html>')
    return "\n".join(o)


def write(cfg, data, build_dir, mode=None, log=None):
    index_refs(data)
    text = document(cfg, data, mode)
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, MODE_FILE[mode])
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    _refs.dump(build_dir)
    if log:
        log(f"[렌더] {os.path.basename(out)} {len(text):,} bytes"
            + ("  [측정용]" if mode else ""))
    return out
