"""특강 합본(special) 렌더러 — data.json → build/index.html.

## 왜 흐름 조판인가

항목 높이가 제각각이라(낱말 카드 1~4줄, 예제 지문 6~14줄, 해설 2~8줄) 슬롯에
앉히면 면이 비어 보인다. **덩어리는 쪼개지 않는다**만 걸고 흐르게 두되, 흐름이
깨지면 안 되는 곳에만 면을 고정한다:

  · 부(部) 간지 — 오른쪽(홀수) 면 · 목차 · PART 표지 — 새 면
  · 어휘 Week · 독해 예제 — 새 면
  · **강 개념 면 / 구문 연습문제 / 어법 연습문제 — 각각 한 면씩** 따로 연다
    (개념을 읽다 말고 문제로 넘어가지 않게. 사용자 지시)

## 강 개념 면 = 위 절반 개념 + 아래 절반 필기 모눈

필기 모눈은 **면 아래 같은 자리**에 고정한다(`.gridbox`, top 150mm). 앞 내용
길이에 따라 오르내리면 면마다 리듬이 달라진다. 그래서 개념 면은 버퍼에 모았다가
한 번에 `<section class="cpage">` 로 낸다.

## 세 블록은 성격이 다르다

`필기 POINT`(체크리스트) · `어법 개념`(정의 문단) · `필기노트`(쓰는 자리)는
생김새가 서로 달라야 한다. 어느 것인지는 **뒤따르는 내용**으로 가른다 —
불릿이 오면 POINT, 문단이 오면 개념, 빈 표가 오면 필기노트. 라벨 글자에 기대면
원고가 조금만 달라져도 깨진다.

## 원고의 '공백 정렬'을 표로 되돌린다

원고는 목차·부록·정답을 공백 여러 칸으로 줄맞춤해 두었다 → 2칸 이상 공백을 열
경계로 본다. 부록만은 줄맞춤이 들쭉날쭉해 **한글이 끝나는 곳**을 뜻/예시 경계로.

## 기입선

원고의 밑줄 친 탭이 학생이 쓰는 자리다. POINT(점검 항목)와 해석하기(서술)는
성격이 달라 모양도 다르게 낸다 — 앞은 베이지 띠 안의 짧은 줄, 뒤는 라벨 칩 +
손글씨용 넓은 줄.
"""
import html
import json
import os
import re

# 판면(mm) — 재단선 기준. 도련은 백엔드가 페이지 크기로 더한다.
DEFAULT_METRICS = {
    "margin_top": 22.0,
    "margin_bottom": 20.0,
    "margin_inner": 20.0,
    "margin_outer": 16.0,
}

RE_GAP2 = re.compile(r" {2,}")
RE_HAN = re.compile(r"[가-힣]")
VOL_ORDER = ("vocab", "grammar", "reading")
HALF = 5              # 어법 연습문제 10문항을 나누는 자리

# 간지·목차 면이 이미 쓴 블록 — 흐름에서 다시 그리면 두 번 나온다
FRONT = {"vol_desc", "toc_title", "toc_1", "toc_2"}


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    return m


# ── 인라인 ──────────────────────────────────────────────────────────────
ROLE_CLASS = {"num": "r-num", "src": "r-src", "pos": "r-pos"}


def esc(s):
    """연속 공백은 의미(간격)다 — 살린다."""
    t = html.escape(s)
    return RE_GAP2.sub(lambda m: "&nbsp;" * (len(m.group(0)) - 1) + " ", t)


def inl(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return esc(x)
    if isinstance(x, dict):
        t = esc(x.get("t", ""))
        if x.get("u"):
            t = f"<u>{t}</u>"
        if x.get("b"):
            t = f"<b>{t}</b>"
        cls = ROLE_CLASS.get(x.get("k"))
        if cls:
            t = f'<span class="{cls}">{t}</span>'
        return t
    return "".join(inl(i) for i in x)


def plain(x):
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("t", "")
    return "".join(plain(i) for i in x)


def cols(text, limit=0):
    """2칸 이상 공백 = 열 경계."""
    parts = [p.strip() for p in RE_GAP2.split(text.strip()) if p.strip()]
    if limit and len(parts) > limit:
        parts = parts[:limit - 1] + ["  ".join(parts[limit - 1:])]
    return parts


def split_gloss(text):
    """뜻(한글·괄호) / 예시(영문)의 경계 — 공백 수가 아니라 **글자 종류**로."""
    last = -1
    for i, ch in enumerate(text):
        if RE_HAN.match(ch) or ch == ")":
            last = i
    if last < 0:
        return "", text.strip()
    return text[:last + 1].strip(), text[last + 1:].strip()


# ── 기입선 ──────────────────────────────────────────────────────────────
def fields(rich):
    """rich → 라벨 목록. 원고의 밑줄 탭이 기입선이다."""
    out, buf = [], ""
    for seg in rich:
        t = plain(seg)
        if t == "\t" or (isinstance(seg, dict) and seg.get("u")
                         and t.strip() == ""):
            out.append(buf.strip())
            buf = ""
        else:
            buf += t
    if buf.strip():
        out.append(buf.strip())
    return out


def point_row(rich):
    """`POINT  □ 핵심 구조 ⎵  □ 본동사 ⎵` — 점검 항목 띠."""
    labs = fields(rich)
    tag = ""
    if labs and labs[0].upper().startswith("POINT"):
        tag = labs[0][:5]
        labs = [labs[0][5:].strip()] + labs[1:]
    cells = "".join(f'<span class="fcell"><span class="fl">{esc(t)}</span>'
                    f'<span class="fline"></span></span>' for t in labs if t)
    return (f'<div class="frow pt"><span class="ptag">{esc(tag or "POINT")}'
            f'</span>{cells}</div>')


def write_row(rich):
    """`해석하기 ⎵` — 손글씨 한 줄."""
    labs = [t for t in fields(rich) if t]
    lab = labs[0] if labs else ""
    return (f'<div class="frow wr"><span class="fl"><i>{esc(lab)}</i></span>'
            f'<span class="fline"></span></div>')


def rules(n, cls="wbox"):
    """괘선 상자 — 괘선은 실제 요소로 그린다."""
    return f'<div class="{cls}">' + '<i></i>' * n + '</div>'


def grid_svg(w=174.0, h=118.0, step=5.0):
    """필기용 모눈 — 래스터가 아니라 벡터 선으로."""
    L = []
    x = 0.0
    while x <= w + .01:
        L.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h:.1f}"/>')
        x += step
    y = 0.0
    while y <= h + .01:
        L.append(f'<line x1="0" y1="{y:.1f}" x2="{w:.1f}" y2="{y:.1f}"/>')
        y += step
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}mm" height="{h}mm">'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#fdfbf6"/>'
            f'<g stroke="#e2dccd" stroke-width=".18">{"".join(L)}</g>'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="none" '
            f'stroke="#cfc7b4" stroke-width=".4"/></svg>')


def gridbox(label):
    return (f'<div class="gridbox"><div class="gl">{esc(label or "필기 노트")}'
            f'</div>{grid_svg()}</div>')


# ── 머리 띠 ─────────────────────────────────────────────────────────────
def runhead(vol, sec, off=False):
    """머리 띠 — 왼쪽 면과 오른쪽 면은 여백이 달라 요소를 둘로 낸다."""
    o = " rh-off" if off else ""
    body = (f'<div class="band"><div class="in">{esc(vol)}'
            f'<i class="bar"></i>'
            f'<span class="sec">{esc(sec)}</span></div>'
            f'<div class="crest"></div></div><div class="rule2"></div>')
    return (f'<div class="rhL{o}">{body}</div>'
            f'<div class="rhR{o}">{body}</div>')


# ══════════════════════════════════════════════════════════ 부별 렌더러
def render_vocab(vol, out):
    """어휘부 — Week 마다 새 면, 분류 띠 아래 낱말 카드가 흐른다."""
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t == "week":
            week = plain(b["r"])
            out.append(f'<section class="week-open">{runhead(vol["name"], week)}'
                       f'<h2 class="week">{inl(b["r"])}</h2></section>')
        elif t == "group":
            c = cols(plain(b["r"]), 3)
            head = esc(c[0].lstrip("■ ").strip()) if c else ""
            rest = "".join(f'<span class="g{k}">{esc(v)}</span>'
                           for k, v in enumerate(c[1:], 1))
            out.append(f'<div class="vgroup"><span class="g0">{head}</span>'
                       f'{rest}</div>')
        elif t == "word":
            out.append(word_card(b))
        elif t == "appendix":
            out.append(appendix_row(b))
        else:
            out.append(generic(b))
        i += 1


def word_card(b):
    senses = "".join(f'<div class="w-sense">{inl(s)}</div>' for s in b["senses"])
    ex = "".join(f'<div class="w-ex">{inl(e)}</div>' for e in b["ex"])
    note = f'<div class="w-note">{esc(b["note"])}</div>' if b.get("note") else ""
    return (
        '<div class="wcard">'
        f'  <div class="w-l"><div class="w-no">{esc(b["no"])}</div>'
        f'    <div class="w-head">{esc(b["head"])}</div>'
        f'    <div class="w-build">{esc(b["build"])}</div>{senses}</div>'
        f'  <div class="w-r">{ex}{note}{rules(2, "wbox tight")}</div>'
        '</div>')


def appendix_row(b):
    txt = plain(b["r"]).lstrip("· ").strip()
    c = RE_GAP2.split(txt, 1)
    key = c[0].strip()
    gloss, ex = split_gloss(c[1] if len(c) > 1 else "")
    return (f'<div class="apx"><span class="a-k">{esc(key)}</span>'
            f'<span class="a-g">{esc(gloss)}</span>'
            f'<span class="a-e">{esc(ex)}</span></div>')


# ── 머리+첫 덩어리 묶음 ─────────────────────────────────────────────────
class Keeper(object):
    """머리를 **뒤따르는 첫 덩어리와 함께** 묶는다.

    `break-after: avoid` 만으로는 부족했다 — '구문' 구분 칩이 면 맨 아래에 혼자
    남고 첫 항목이 다음 면으로 넘어갔다.
    """

    def __init__(self, out):
        self.out = out
        self.pend = []

    def head(self, html_):
        self.flush()
        self.pend.append(html_)

    def body(self, html_):
        if self.pend:
            self.out.append('<div class="keep">' + "".join(self.pend)
                            + html_ + "</div>")
            self.pend = []
        else:
            self.out.append(html_)

    def flush(self):
        if self.pend:
            self.out.append("".join(self.pend))
            self.pend = []


# ─────────────────────────────────────────────────────────── 구문·어법부
def render_grammar(vol, out):
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    k = Keeper(out)
    cp = None            # 개념 면 버퍼 {"body": [...], "grid": 라벨}
    drill_gram = False    # 지금 열려 있는 연습이 어법 쪽인가
    col_open = False
    qn = 0                # 지금 연습 안에서 몇 번째 문항인가

    def close_cpage():
        nonlocal cp
        if cp is None:
            return
        out.append('<section class="cpage">' + "".join(cp["body"])
                   + gridbox(cp["grid"]) + "</section>")
        cp = None

    def close_col():
        nonlocal col_open
        if col_open:
            k.flush()
            out.append("</div>")
            col_open = False

    def put(h):
        """개념 면이 열려 있으면 그리로, 아니면 흐름으로."""
        if cp is not None:
            cp["body"].append(h)
        else:
            k.body(h)

    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t in ("part_no", "lesson", "ans_head", "drill"):
            close_cpage()
            k.flush()

        if t == "part_no":
            close_col()
            title = ""
            if i + 1 < n and blocks[i + 1]["t"] == "part_title":
                title = plain(blocks[i + 1]["r"])
                i += 1
            out.append(part_page(plain(b["r"]), title))
        elif t == "lesson":
            cp = {"body": [runhead(vol["name"], plain(b["r"])),
                           f'<h3 class="lesson">{inl(b["r"])}</h3>'],
                  "grid": "필기 노트"}
        elif t == "lesson_sub":
            put(kv_line(plain(b["r"]), "lsub"))
        elif t == "subhead":
            # 어느 블록인지는 **뒤따르는 내용**이 정한다
            nxt = blocks[i + 1]["t"] if i + 1 < n else ""
            if nxt == "notebox":
                if cp is not None:
                    cp["grid"] = plain(b["r"])
                i += 1                        # 빈 표는 모눈이 대신한다
            elif nxt == "concept":
                put(f'<div class="h-concept">{inl(b["r"])}</div>')
            elif nxt == "bullet":
                put(f'<h4 class="h-point">{inl(b["r"])}</h4>')
            else:
                put(f'<h4 class="subhead">{inl(b["r"])}</h4>')
        elif t == "bullet":
            put(f'<div class="bul">{inl(strip_mark(b["r"], "•"))}</div>')
        elif t == "concept":
            put(f'<div class="concept">{kv_inline(plain(b["r"]))}</div>')
        elif t == "notebox":
            if cp is None:
                put(rules(8, "wbox"))
        elif t == "drill":
            title = plain(b["r"])
            drill_gram = "어법" in title
            qn = 0
            g = " gram" if drill_gram else ""
            note = ""
            if i + 1 < n and blocks[i + 1]["t"] == "drill_note":
                note = f'<div class="drill-note">{inl(blocks[i + 1]["r"])}</div>'
                i += 1
            out.append(f'<div class="drillpage{g}">'
                       f'<div class="drill{g}"><h4>{inl(b["r"])}</h4>'
                       f'{note}</div>')
            out.append("</div>")            # 연습 머리만 새 면을 연다
            k.head(f'<div class="qhead{g}"></div>')
        elif t == "q":
            j = i + 1
            rows = []
            while j < n and blocks[j]["t"] in ("q_point", "q_field"):
                rows.append(point_row(blocks[j]["r"])
                            if blocks[j]["t"] == "q_point"
                            else write_row(blocks[j]["r"]))
                j += 1
            g = " gram" if drill_gram else ""
            qn += 1
            # 어법 연습은 한 강에 10문항이라 한 면에 안 들어간다. 흐름에 맡기면
            # 7+3 처럼 뒷면이 휑해진다 → **5+5 로 나눈다**.
            if drill_gram and qn == HALF + 1:
                k.flush()
                out.append('<div class="pbr"></div>')
            k.body(f'<div class="qitem{g}">{q_line(b["r"])}'
                   + "".join(rows) + "</div>")
            i = j - 1
        elif t == "ans_head":
            txt = plain(b["r"])
            if txt.startswith("PART"):
                close_col()
                out.append(f'<section class="anspage">'
                           f'{runhead(vol["name"], "정답 및 해설")}'
                           f'<h3 class="ans-part">{inl(b["r"])}</h3></section>')
                out.append('<div class="anscol">')
                col_open = True
                k = Keeper(out)
            else:
                k.head(f'<h3 class="ans-lesson">{inl(b["r"])}</h3>')
        elif t == "ans_kind":
            g = " gram" if "어법" in plain(b["r"]) else ""
            drill_gram = bool(g)
            k.head(f'<div class="ans-kind{g}">{inl(b["r"])}</div>')
        elif t == "ans_q":
            j = i + 1
            body = []
            while j < n and blocks[j]["t"] in ("ans_en", "ans_item"):
                bb = blocks[j]
                if bb["t"] == "ans_en":
                    body.append(f'<div class="ans-en">'
                                f'{kv_inline(bb["r"], en=True)}</div>')
                else:
                    body.append(ans_item(bb["r"]))
                j += 1
            k.body(f'<div class="aitem">{ans_q_line(b["r"])}'
                   + "".join(body) + "</div>")
            i = j - 1
        else:
            put(generic(b))
        i += 1
    close_cpage()
    close_col()
    k.flush()


def strip_mark(rich, mark):
    """머리 기호는 CSS 가 그린다 — 원고의 기호는 뗀다."""
    out = list(rich)
    if out:
        first = out[0]
        t = plain(first).lstrip()
        if t.startswith(mark):
            t = t[len(mark):].lstrip()
            out[0] = t if isinstance(first, str) else dict(first, t=t)
    return out


def q_line(rich):
    """문항 — 앞머리 번호를 원형 배지로."""
    num, rest = "", list(rich)
    if rest and isinstance(rest[0], dict) and rest[0].get("k") == "num":
        num = plain(rest[0]).strip()
        rest = rest[1:]
    return (f'<div class="q"><span class="q-no"><i>{esc(num)}</i></span>'
            f'<span class="q-t">{inl(rest)}</span></div>')


def ans_q_line(rich):
    num, rest = "", list(rich)
    if rest and plain(rest[0]).strip().isdigit():
        num = plain(rest[0]).strip()
        rest = rest[1:]
    return (f'<div class="a-q"><span class="a-no">{esc(num)}</span>'
            f'<span class="a-t">{inl(rest)}</span></div>')


def ans_item(rich):
    txt = plain(rich)
    if "|" in txt:
        lab, _, body = txt.partition("|")
        return (f'<div class="a-item"><span class="a-lab">{esc(lab.strip())}</span>'
                f'<span class="a-body">{esc(body.strip())}</span></div>')
    return f'<div class="a-item"><span class="a-body">{inl(rich)}</span></div>'


def kv_line(txt, cls):
    c = cols(txt, 2)
    if len(c) == 2:
        return (f'<div class="{cls}"><span class="chip">{esc(c[0])}</span>'
                f'<span>{esc(c[1])}</span></div>')
    return f'<div class="{cls}"><span>{esc(txt)}</span></div>'


def kv_inline(rich, en=False):
    txt = plain(rich) if not isinstance(rich, str) else rich
    if "|" in txt[:14]:
        lab, _, body = txt.partition("|")
        return (f'<span class="chip">{esc(lab.strip())}</span>'
                f'<span>{esc(body.strip())}</span>')
    return inl(rich)


def part_page(no, title):
    return (f'<section class="partpage">'
            f'<div class="p-no">{esc(no)}</div>'
            f'<div class="p-ttl">{esc(title)}</div></section>')


# ───────────────────────────────────────────────────────────────── 독해부
def render_reading(vol, out):
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    week = pending_week = ""
    k = Keeper(out)
    cp = None

    def close_cpage():
        nonlocal cp
        if cp is None:
            return
        out.append('<section class="cpage">' + "".join(cp["body"])
                   + gridbox(cp["grid"]) + "</section>")
        cp = None

    def put(h):
        if cp is not None:
            cp["body"].append(h)
        else:
            k.body(h)

    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t in ("week", "lesson", "rpart_no", "ex_tag"):
            close_cpage()
            k.flush()
        if pending_week and t not in ("week", "lesson", "rpart_no"):
            out.append(f'<section class="week-open">'
                       f'{runhead(vol["name"], pending_week)}'
                       f'<h2 class="week">{esc(pending_week)}</h2></section>')
            pending_week = ""

        if t == "rpart_no":
            title = ""
            if i + 1 < n and blocks[i + 1]["t"] == "rpart_title":
                title = plain(blocks[i + 1]["r"])
                i += 1
            out.append(part_page(plain(b["r"]), title))
        elif t == "week":
            week = pending_week = plain(b["r"])
        elif t == "lesson":
            brow = (f'<div class="weekbrow">{esc(pending_week)}</div>'
                    if pending_week else "")
            rh = runhead(vol["name"],
                         (week + "  ·  " if week else "") + plain(b["r"]))
            cp = {"body": [rh, brow,
                           f'<h3 class="lesson">{inl(b["r"])}</h3>'],
                  "grid": "필기 노트"}
            pending_week = ""
        elif t == "concept_head":
            put(f'<div class="ch">{esc(plain(b["r"]).strip("＜＞ "))}</div>')
        elif t == "block_head":
            put(f'<h4 class="bh">{inl(strip_mark(b["r"], "●"))}</h4>')
        elif t == "block_bullet":
            put(f'<div class="bbul">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "wnote_head":
            if cp is not None:
                cp["grid"] = plain(b["r"]).strip().lstrip("❖ ").strip()
            else:
                k.head(f'<div class="nh">{esc(plain(b["r"]).strip())}</div>')
        elif t == "note_head":
            txt = plain(b["r"]).strip().lstrip("❖ ").strip()
            k.head(f'<div class="nh">{esc(txt)}</div>')
        elif t == "notebox":
            if cp is None:
                k.body(rules(6, "wbox"))
        elif t == "ex_tag":
            out.append(ex_tag(b["r"]))
        elif t == "stem":
            k.body(f'<div class="stem">{inl(b["r"])}</div>')
        elif t == "passage":
            k.body(f'<div class="psg">{inl(b["r"])}</div>')
        elif t == "footnote":
            k.body(f'<div class="fnote">{inl(b["r"])}</div>')
        elif t == "choice":
            j = i
            items = []
            while j < n and blocks[j]["t"] == "choice":
                items.append(f'<li>{inl(blocks[j]["r"])}</li>')
                j += 1
            k.body('<ul class="choices">' + "".join(items) + "</ul>")
            i = j - 1
        elif t == "bg_head":
            txt = plain(b["r"]).strip().lstrip("❖ ").strip()
            k.head(f'<div class="bgh">{esc(txt)}</div>')
        elif t == "bg_item":
            k.body(f'<div class="bgi">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "trans_head":
            k.head(f'<div class="th">'
                   f'{esc(plain(b["r"]).strip().lstrip("❖ ").strip())}</div>')
        elif t == "trans":
            k.body(f'<div class="trans">{inl(b["r"])}</div>')
        elif t == "ans_line":
            k.body(ans_line(b["r"]))
        else:
            put(generic(b))
        i += 1
    close_cpage()
    k.flush()


def ex_tag(rich):
    c = [x for x in cols(plain(rich)) if x != "·"]
    no = c[0] if c else ""
    lvl = c[-1] if len(c) > 1 and c[-1].startswith("[") else ""
    mid = "  ·  ".join(c[1:-1] if lvl else c[1:])
    return (f'<div class="extag"><span class="x-no"><i>{esc(no)}</i></span>'
            f'<span class="x-m">{esc(mid)}</span>'
            f'<span class="x-l"><i>{esc(lvl.strip("[] "))}</i></span></div>')


def ans_line(rich):
    txt = plain(rich).strip()
    if txt.startswith("·"):                       # 배경지식 노트 정답
        body = txt.lstrip("· ").strip()
        src, _, rest = body.partition("]")
        return (f'<div class="aline bg"><span class="l-src">'
                f'{esc(src.strip("[ "))}</span>'
                f'<span class="l-body">{esc(rest.strip())}</span></div>')
    c = [x for x in cols(txt) if x != "→"]
    no = c[0] if c else ""
    ans = c[-1] if len(c) > 1 else ""
    mid = "&nbsp;&nbsp;·&nbsp;&nbsp;".join(esc(x) for x in c[1:-1])
    return (f'<div class="aline"><span class="l-no">{esc(no)}</span>'
            f'<span class="l-body">{mid}</span>'
            f'<span class="l-ans">{esc(ans)}</span></div>')


def generic(b):
    return f'<div class="x-{b["t"]}">{inl(b.get("r"))}</div>'


# ─────────────────────────────────────────────────────── 표지 · 간지 · 목차
def cover_page(cfg, cover):
    sub = title = ""
    rows, tail = [], []
    for b in cover:
        t, txt = b["t"], plain(b["r"])
        if t == "cover_sub":
            sub = txt
        elif t == "cover_title":
            title = txt
        elif t == "cover_note":
            if "\t" in txt:
                kk, _, v = txt.partition("\t")
                rows.append(f'<tr><th>{esc(kk.strip())}</th>'
                            f'<td>{esc(v.strip())}</td></tr>')
            elif txt.strip():
                tail.append(f'<div class="c-tail">{esc(txt.strip())}</div>')
    bk = cfg.book
    who = "  ·  ".join(x for x in (bk.get("school"), bk.get("teacher")) if x)
    return (
        '<section class="coverpage">'
        f'  <div class="c-brand">{esc(bk.get("brand", ""))}</div>'
        f'  <div class="c-sub">{esc(sub)}</div>'
        f'  <h1 class="c-ttl">{esc(title)}</h1>'
        f'  <table class="c-spec">{"".join(rows)}</table>'
        f'  {"".join(tail)}'
        f'  <div class="c-who">{esc(who)}</div>'
        '</section>')


def divider_page(vol, no):
    lines = [b for b in vol["blocks"] if b["t"] == "vol_desc"]
    desc = "".join(f'<div class="d-desc">{inl(b["r"])}</div>' for b in lines)
    return (f'<section class="divider">'
            f'  <div class="d-in">'
            f'    <div class="d-no">PART {no:02d}</div>'
            f'    <h1 class="d-ttl">{esc(vol["name"])}</h1></div>'
            f'  <div class="d-edge"></div>'
            f'  <div class="d-band">{desc}</div>'
            f'  <div class="d-ghost">{no:02d}</div>'
            f'</section>')


def toc_page(vol):
    rows = []
    for b in vol["blocks"]:
        if b["t"] == "toc_title":
            continue
        if b["t"] == "toc_1":
            c = cols(plain(b["r"]), 3)
            kk = esc(c[0]) if c else ""
            rest = "".join(f'<span class="t{i}">{esc(v)}</span>'
                           for i, v in enumerate(c[1:], 1))
            cls = "t-1" if rest else "t-1 solo"
            rows.append(f'<div class="{cls}"><span class="t0">{kk}</span>'
                        f'{rest}</div>')
        elif b["t"] == "toc_2":
            rows.append(f'<div class="t-2">{inl(b["r"])}</div>')
    return ('<section class="tocpage">'
            f'<h2 class="toc-h">CONTENTS</h2>'
            f'<div class="toc-sub">{esc(vol["name"])}</div>'
            + "".join(rows) + "</section>")


# ──────────────────────────────────────────────────────────────── 조립
RENDERERS = {"vocab": render_vocab, "grammar": render_grammar,
             "reading": render_reading}


def write(cfg, d, build_dir, log=print):
    m = metrics_of(cfg)
    pal = cfg.section("palette") or {}
    parts = [cover_page(cfg, d["cover"])]
    for k, vol in enumerate(d["volumes"], 1):
        vid = vol["id"]
        parts.append(f'<div class="vol v-{vid}">')
        parts.append(divider_page(vol, k))
        parts.append(toc_page(vol))
        body = []
        RENDERERS.get(vid, render_reading)(vol, body)
        parts.append('<div class="flow">' + "".join(body) + "</div>")
        parts.append("</div>")
    # 제본은 **짝수 면**으로 끝나야 한다 — 마지막이 홀수면 MEMO 한 면을 더한다.
    parts.append(f'<section class="memopage v-{d["volumes"][-1]["id"]}">'
                 '<div class="rhL rh-off"></div><div class="rhR rh-off"></div>'
                 f'<h2 class="memo-h">MEMO</h2>{grid_svg(174, 210)}'
                 '</section>')

    css_vars = ":root{\n" + "".join(
        f"  --mgn-{k.split('_')[1]}: {v}mm;\n" for k, v in m.items()
        if k.startswith("margin_")) + "}\n" + palette_css(pal)

    doc = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f'<title>{html.escape(cfg.book.get("title", ""))}</title>'
        '<link rel="stylesheet" href="theme.css">'
        f'<style>{css_vars}</style></head><body>'
        + "".join(parts) + "</body></html>")
    path = os.path.join(build_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    log(f"  HTML {len(doc):,}자 → {path}")
    return path


def palette_css(pal):
    out = []
    for vid in VOL_ORDER:
        p = pal.get(vid) or {}
        if not p:
            continue
        out.append(f".v-{vid}{{" + "".join(
            f"--c-{k}:{v};" for k, v in p.items()) + "}")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────── 검수 대조
#
# 원고 → PDF **직접 대조**다. "단락을 100% 소비했다"는 게이트는 파서 사고를 그냥
# 통과시킨 적이 있다. 그래서 세는 것은 블록 수가 아니라 **본문 글자**다.
# 조판이 라벨·머리기호·구분자를 떼어 칩·배지로 옮기므로, 구분자로 잘라 **가장
# 긴 조각**을 대조 문자열로 쓴다. 그 조각이 없으면 그것은 진짜 유실이다.
RE_SEPS = re.compile(r"[|→·•●❖＜＞\[\]\t]| {2,}")


def probe_text(text, floor=10):
    frags = [f.strip() for f in RE_SEPS.split(text or "")]
    best = max(frags, key=len) if frags else ""
    return best[:70] if len(best) >= floor else ""


def verify_sequence(d):
    """조판 순서대로 (설명, 원문 조각). 위치가 앞으로 가면 순서 어긋남이다."""
    seq = []
    for vol in d["volumes"]:
        vid = vol["id"]
        for b in vol["blocks"]:
            t = b["t"]
            if t == "notebox":
                continue
            if t == "word":
                seq.append((f"{vid}/{b['no']} {b['head']}", b["head"]))
                for s in b["senses"]:
                    frag = probe_text(plain(s), 3)
                    if frag:
                        seq.append((f"{vid}/{b['head']} 뜻", frag))
                for e in b["ex"]:
                    txt = "".join(plain(s) for s in e
                                  if not (isinstance(s, dict)
                                          and s.get("k") == "src"))
                    frag = probe_text(txt.strip("❶❷ "))
                    if frag:
                        seq.append((f"{vid}/{b['head']} 예문", frag))
                continue
            frag = probe_text(plain(b.get("r")))
            if frag:
                seq.append((f"{vid}/{t}", frag))
    return seq
