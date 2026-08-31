"""파이널 직전보충 렌더러 — data.json → build/index.html.

지면 규칙(완성본 실측, `tests/fixtures/final_viv_baseline.json`):

  · ①문장배열 ②문장삽입 = **사분면 고정**. 한 칸 126mm · 두 단 × 두 줄.
    `column-fill: auto` 로 왼 단을 위→아래로 채운 뒤 오른 단으로 넘어간다.
  · ③중요어휘 = 한 면 한 지문. 왼(빈칸)·오(정답)을 **표 두 행**으로 짠다 —
    지문 행과 요약 행. 인디자인은 두 스토리를 따로 흘리고 `>>내용요약` 줄의
    기준선을 재서 맞췄는데(그러다 명일3 test1 24~25 꼬리가 통째로 사라졌다),
    행으로 묶으면 어긋날 수가 없다.
  · ④어법수정 ⑤서술형영작 = 한 단 한 지문(한 면 2지문).

넘침 정책(사용자 확정): **칸 높이를 지키고, 넘치는 지문만 활자를 단계적으로
줄인다.** 인디자인이 런타임에 하던 것과 같다. 줄인 지문은 검수 리포트에
남긴다 — 조용히 줄이지 않는다. 줄이려면 행간이 활자를 따라가야 하므로
line-height 를 **단위 없이**(배수) 준다.
"""
import html
import os
import re

from core.render_vivlio import refs as _refs
from core.render_vivlio import stage
from core.render_vivlio.series.final import data as data_mod

# 완성본 실측(mm/pt). 책이 필요하면 config.metrics 로 덮는다.
DEFAULT_METRICS = {
    "slot": 126.0,        # 사분면 한 칸
    "body_top": 29.57,    # 판면 위 (배열·삽입·어법·영작)
    "body_h": 253.0,      # 판면 높이
    "vocab_top": 30.0,    # 판면 위 (중요어휘)
    "vocab_avail": 252.57,   # 중요어휘 면이 실제로 주는 높이(303-30-20.43)
    "vocab_safety": 4.0,     # 잉크 바닥 ↔ 상자 바닥 차이만큼의 여유
    "base_pt": 8.5,       # 본문 활자
    "min_pt": 7.0,        # 축소 하한 — 여기까지 줄여도 안 들어가면 결함
    "step_pt": 0.1,       # 축소 눈금
}

RE_ITEM = re.compile(r"^\((?P<m>[A-Z])\)\s*")
# 측정용 면 높이 — 아주 길게 잡아 **한 지문이 절대 쪼개지지 않게** 한다.
# (쪼개지면 면 수 ≠ 지문 수가 되어 측정이 통째로 실패한다.)
MEASURE_PAGE_H = 500.0
# 단 폭(mm) — **재는 폭과 조판하는 폭이 같아야** 높이가 맞는다(완성본 실측).
COL_W = 83.7
NBSP = " "


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    return m


# ------------------------------------------------------------------ 인라인
def esc(s):
    """HTML 이스케이프 + **연속 공백 보존**(원고의 의미 있는 간격)."""
    s = html.escape(s or "")
    return re.sub(r" {2,}",
                  lambda m: NBSP * (len(m.group(0)) - 1) + " ", s)


# 빈칸 밑줄 폭 = 정답 글자 수 × 이 값(em). 완성본 227개 실측에서
# 글자수별 **최솟값**(= 양끝정렬이 안 늘린 줄)이 2.05mm/글자로 일정했다
# → 8.5pt 기준 0.684em. 활자를 줄여도 따라가도록 em 으로 준다.
BLANK_EM = 0.684


def _blank(word):
    """빈칸 = 첫 글자(굵게) + 남은 낱말 길이만큼의 밑줄.

    ⚠ 밑줄을 고정폭 공백(NBSP) 으로 채우면 안 된다 — Noto 의 공백은 0.224em
      이라 완성본의 3분의 1 밖에 안 된다(실제로 밑줄이 토막처럼 보였다).
    """
    w = (word or "").strip()
    if not w:
        return ""
    head = html.escape(w[0])
    return (f'<span class="bl">{head}'
            f'<span class="u" style="width:{len(w) * BLANK_EM:.3f}em">'
            f'</span></span>')


def inl_cloze(segs):
    """중요어휘 왼쪽 — `[답]` 을 빈칸으로."""
    return "".join(_blank(x["a"]) if isinstance(x, dict) else esc(x)
                   for x in segs)


def inl_answer(segs):
    """중요어휘 오른쪽 — `[답]` 을 굵은 낱말로."""
    return "".join(f'<span class="ansv">{esc(x["a"])}</span>'
                   if isinstance(x, dict) else esc(x) for x in segs)


def inl_grammar(segs):
    """어법수정 — `[낱말]` 을 **대괄호째** 굵게(완성본 실측)."""
    return "".join(f'<span class="g">[{esc(x["a"])}]</span>'
                   if isinstance(x, dict) else esc(x) for x in segs)


def _item(text):
    """`(A) …` 의 머리표만 굵게."""
    m = RE_ITEM.match(text or "")
    if not m:
        return esc(text)
    return (f'<span class="m">({m.group("m")})</span> '
            f'{esc(text[m.end():])}')


# ------------------------------------------------------------------ 조각
def _open_blk(fit, base="blk"):
    f = fit or {}
    cls = base + (" tall" if f.get("span") == 2 else "") \
                + (" flow" if f.get("flow") else "")
    st = (f' style="font-size:{fit["pt"]:.2f}pt"'
          if fit and fit.get("pt") else "")
    return f'<div class="{cls}"{st}>'


def _fit_attrs(fit):
    """축소·두 칸 지정 → HTML 속성. `fit` 은 {"pt":…, "span":2} 또는 None."""
    if not fit:
        return ""
    cls = ' class="blk tall"' if fit.get("span") == 2 else ""
    st = f' style="font-size:{fit["pt"]:.2f}pt"' if fit.get("pt") else ""
    return cls + st


def band(sec, flow=False):
    """섹션 띠 — 검은 사각형 + 번호 + 제목.

    짝수 면은 배경(사각형)+러닝 요소(글자)로 매 면 그려지고, 섹션 첫 면은
    홀수여도 붙으므로 흐름 맨 앞에 높이 0 으로 한 벌 더 심는다(겹쳐도 같은
    그림이라 표가 안 난다).
    """
    inner = (f'<span class="n">{sec["no"]}</span>'
             f'<span class="t">{esc(sec["title"])}</span>')
    if not flow:
        return f'<div class="bandrun band">{inner}</div>'
    return (f'<div class="sechdr"><div class="mask"></div>'
            f'<div class="sq"></div>'
            f'<div class="band">{inner}</div></div>')


def head_right(chapter):
    return (f'<div class="headR">'
            f'<span class="tab">Chapter.{chapter["no"]:02d}&nbsp;&nbsp;|'
            f'&nbsp;&nbsp;{esc(chapter["en"])}</span>'
            f'<span class="wm">FINAL&nbsp;STEP</span></div>')


def feet(chapter, title=""):
    """꼬리말 — 홀수 면은 `CHAPTER.0N 섹션이름 쪽번호`.

    ⚠ 섹션 이름을 `string-set`/`string()` 으로 끌어오려 했더니 **조용히 빈
      문자열**이 나왔다(Vivliostyle 이 마진 박스 밖 러닝 요소의 string() 을
      풀지 않는다). 러닝 요소를 **섹션마다 다시 선언**하면 그 면부터 새 값이
      쓰이므로, 이름을 그냥 박아 넣는다.
    """
    return ('<div class="footL"><span class="pg"></span>'
            '<span class="lb">FINAL STEP</span></div>'
            f'<div class="footR"><span class="ch">CHAPTER.'
            f'{chapter["no"]:02d}</span><span class="lb">{esc(title)}</span>'
            '<span class="pg"></span></div>')


def divider(chapter, sections):
    """간지 — 완성본 실측(광문2 Vol1/Vol2 1면).

    워드마크(`FINAL STEP` + 표제)는 `내지/1P.ai` 에서 뜬 그림이고, 장 상자와
    차례는 권마다 달라서 조판한다. 고3 은 문장삽입이 없어 차례가 두 줄이 아니라
    한 줄이 된다 — 완성본을 그대로 끼우면 이걸 못 맞춘다.
    """
    o = ['<div class="art"><div class="rule r1"></div>',
         '<img class="wm" src="assets/wordmark.png" alt="">',
         '<div class="rule r2"></div>',
         f'<div class="chbox">Chapter.{chapter["no"]:02d}&nbsp;&nbsp;|'
         f'&nbsp;&nbsp;{esc(chapter["en"])}</div>',
         '<div class="toc">']
    seen = set()
    for sec in sections:
        first = sec["no"] not in seen
        seen.add(sec["no"])
        cls = "g" if first else "s"
        num = f'<span class="n">{sec["no"]}</span>' if first else \
              '<span class="n"></span>'
        o.append(f'<p class="{cls}">{num}{esc(sec["toc"])}</p>')
    o.append('</div></div>')
    return "".join(o)


ANSLINE = ('<p class="ansline"><span class="ar">&#xFF1E;</span>'
           '<span class="ln"></span></p>')


# ------------------------------------------------------------------ 블록
def blk_arrange(b, fit=None, mark=""):
    o = [_open_blk(fit),
         f'<h3{mark}>{esc(b["header"])}</h3>']
    if b.get("given"):
        o.append(f'<div class="given">{esc(b["given"])}</div>')
    for it in b["items"]:
        o.append(f'<p class="it">{_item(it)}</p>')
    o.append(ANSLINE)
    o.append('</div>')
    return "".join(o)


def blk_insert(b, fit=None, mark=""):
    o = [_open_blk(fit),
         f'<h3{mark}>{esc(b["header"])}</h3>']
    if b.get("prompt"):
        o.append(f'<p class="prompt">{esc(b["prompt"])}</p>')
    if b.get("given"):
        o.append(f'<div class="given">{esc(b["given"])}</div>')
    for it in b["items"]:
        o.append(f'<p class="it">{_item(it)}</p>')
    o.append('</div>')
    return "".join(o)


def blk_vocab(b, fit=None, mark=""):
    """지문 행 + 요약 행. 두 행이라 좌우 `>>내용요약` 이 저절로 맞는다."""
    def cell(kind, paras, fn):
        body = "".join(f'<p class="vp">{fn(p)}</p>' for p in paras)
        return f'<div class="{kind}"><div class="vcell">{body}</div></div>'

    o = [_open_blk(fit, "blk blk-vocab"),
         f'<h3{mark}>{esc(b["header"])}</h3>',
         '<div class="vpair">',
         cell("l", b["passage"], inl_cloze),
         cell("r", b["passage"], inl_answer),
         '</div>']
    if b.get("summary"):
        def scell(kind, fn):
            body = "".join(f'<p class="vp">{fn(p)}</p>' for p in b["summary"])
            return (f'<div class="{kind}"><div class="vcell">'
                    f'<p class="hd">&gt;&gt;&nbsp;&nbsp;&nbsp;내용요약</p>'
                    f'{body}</div></div>')
        o.append(f'<div class="vpair vsum">{scell("l", inl_cloze)}'
                 f'{scell("r", inl_answer)}</div>')
    o.append('</div>')
    return "".join(o)


def blk_grammar(b, fit=None, mark=""):
    return (_open_blk(fit)
            + f'<h3{mark}>{esc(b["header"])}</h3>'
            + f'<p class="body">{inl_grammar(b["body"])}</p></div>')


def blk_writing(b, fit=None, mark=""):
    o = [_open_blk(fit),
         f'<h3{mark}>{esc(b["header"])}</h3>']
    for p in b["pairs"]:
        o.append('<div class="wpair">'
                 f'<p class="wkor">{esc(p["korean"])}</p>'
                 f'<p class="wcho">{esc(p["choices"])}</p></div>')
    o.append('</div>')
    return "".join(o)


BLK = {"arrange": blk_arrange, "insert": blk_insert, "vocab": blk_vocab,
       "grammar": blk_grammar, "writing": blk_writing}
# 한 지문이 차지하는 칸 — 사분면(126mm)인가 한 단 통짜(253mm)인가
SLOT_KIND = {"arrange": "slot", "insert": "slot", "vocab": "page",
             "grammar": "col", "writing": "col"}


# ------------------------------------------------------------- 클릭 편집 자리표
REF_SPEC = ("vols", ("sections",))


def index_refs(data):
    try:
        return _refs.index(data, REF_SPEC)
    except Exception:
        return None


def _mark(_b):
    return ""


# ------------------------------------------------------------------ 문서
def key_of(vol, sec, i, b):
    return f"{vol}-{sec['kind']}-{i}"


def document(cfg, data, vol, fits=None, mode=None):
    v = data["vols"][str(vol)]
    ch = v["chapter"]
    fits = fits or {}
    o = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         f'<title>{esc(cfg.book.get("title", ""))} Vol{vol}</title>',
         '<link rel="stylesheet" href="theme.css">',
         stage.BOOK_CSS_LINKS]
    if mode == "measure":
        m = metrics_of(cfg)
        # ⚠ 잉크 바닥은 **상자 바닥이 아니다.** 행간이 넓은 섹션(어휘 7.06mm,
        #   어법 9.52mm)에서는 마지막 줄의 여유만큼 5~7mm 를 적게 잰다 —
        #   그만큼 '들어간다'고 잘못 판정해 요약이 다음 면으로 밀렸다.
        #   블록 끝에 높이 0 인 표식을 찍어 **상자 바닥**을 재게 한다.
        o.append('<style>@page{size:216mm %.2fmm}'
                 '.grid{column-count:1;width:%.2fmm;height:auto}'
                 '.blk{height:auto!important;overflow:visible!important}'
                 '.blk + .blk{break-before:page}'
                 '.blk::after{content:"\\25AA";display:block;'
                 'font-size:2pt;line-height:0;color:#000}'
                 '.sechdr{display:none}</style>'
                 % (MEASURE_PAGE_H, COL_W))
    o.append('</head><body>')
    o.append(feet(ch))
    if mode != "measure":
        o.append(head_right(ch))
        o.append(divider(ch, v["sections"]))

    for sec in v["sections"]:
        kind = sec["kind"]
        o.append(f'<section class="sec sec-{kind}">')
        o.append(f'<div class="secmark">{esc(sec["title"])}</div>')
        o.append(feet(ch, sec["title"]))
        if mode != "measure":
            o.append(band(sec))
            o.append(band(sec, flow=True))
        o.append('<div class="grid">')
        for i, b in enumerate(sec["blocks"]):
            o.append(BLK[kind](b, fits.get(key_of(vol, sec, i, b))))
        o.append('</div></section>')
    o.append('</body></html>')
    return "\n".join(o)


MODE_FILE = {None: "index.html", "measure": "measure.html"}


def write(cfg, data, vol, build_dir, fits=None, mode=None, log=None):
    text = document(cfg, data, vol, fits, mode)
    os.makedirs(build_dir, exist_ok=True)
    name = MODE_FILE[mode]
    if mode is None:
        name = "index.html"
    out = os.path.join(build_dir, name)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    if log:
        log(f"[렌더] Vol{vol} {os.path.basename(out)} {len(text):,} bytes"
            + ("  [측정용]" if mode else ""))
    return out
