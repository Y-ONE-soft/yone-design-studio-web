"""특강 합본(special) 렌더러 — data.json → build/index.html.

## 무엇을 우선하는가

"덜 꾸몄는데 더 출판물처럼." 요소를 늘리지 않고 **위계**로 읽히게 한다.

  1. 머리(내비게이션)는 두 단계 — 상위(PART/WEEK)는 작게, 현재 위치는 한 단 크게
  2. 제목은 번호를 떼어 따로 세우고, 밑줄에 기대지 않는다
  3. 라벨 체계는 셋뿐 — A 대분류 / B 학습 포인트 / C 작성 영역
  4. 중요도 차이를 **크기**로 벌린다(색으로 다 해결하지 않는다)
  5. 부(部)마다 머리의 **내용 구성**이 다르다(색만 바꾸지 않는다)
  6. 번호 거터 하나로 모든 시작선을 맞춘다

## 흐름 조판

항목 높이가 제각각이라 슬롯에 앉히면 면이 빈다. "덩어리는 쪼개지 않는다"만 걸고
흐르게 두되, 흐름이 깨지면 안 되는 곳에만 면을 고정한다 — 부 간지(2면 세트) ·
목차 · PART 오프너 · 어휘 Week · 강 개념 면 · 구문/어법 연습 · 독해 예제.

## 두 가지 함정(둘 다 실측으로 겪었다)

  · `break-inside: avoid` 를 **flex 컨테이너에 직접** 걸면 덩어리가 조용히
    사라진다 → 두 단짜리는 `display: table`.
  · 본문 흐름 요소에 `position: relative/absolute` 를 주면 그 단락이 뒤 레이어로
    밀려 **PDF 글자 추출 순서가 읽는 순서와 어긋난다** → 표식은 매달린 들여쓰기 +
    inline-block 도형으로만.
"""
import html
import json
import os
import re

DEFAULT_METRICS = {
    "margin_top": 22.0, "margin_bottom": 20.0,
    "margin_inner": 20.0, "margin_outer": 16.0,
}

RE_GAP2 = re.compile(r" {2,}")
RE_HAN = re.compile(r"[가-힣]")
RE_LEADNUM = re.compile(r"^\s*(\d+)\s*(?:강|주)?\s*[.·]?\s*")
RE_EXNUM = re.compile(r"^\s*([❶-❿①-⑳])\s*")
RE_CIRC = re.compile(r"^\s*([①-⑳])\s*")
VOL_ORDER = ("vocab", "grammar", "reading")
VOL_EN = {"vocab": "VOCABULARY", "grammar": "SYNTAX & GRAMMAR",
          "reading": "READING"}
HALF = 5              # 어법 연습문제 10문항을 나누는 자리
FRONT = {"vol_desc", "toc_title", "toc_1", "toc_2"}
BOOK = [""]           # 머리 오른쪽 면에 들어가는 책 이름(write() 가 채운다)


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    return m


# ── 인라인 ──────────────────────────────────────────────────────────────
ROLE_CLASS = {"num": "r-num", "src": "r-src", "pos": "r-pos"}


def esc(s):
    t = html.escape(s or "")
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
    parts = [p.strip() for p in RE_GAP2.split((text or "").strip()) if p.strip()]
    if limit and len(parts) > limit:
        parts = parts[:limit - 1] + ["  ".join(parts[limit - 1:])]
    return parts


def split_gloss(text):
    """뜻(한글·괄호) / 예시(영문)의 경계 — 공백 수가 아니라 글자 종류로."""
    last = -1
    for i, ch in enumerate(text):
        if RE_HAN.match(ch) or ch == ")":
            last = i
    if last < 0:
        return "", text.strip()
    return text[:last + 1].strip(), text[last + 1:].strip()


def numtitle(txt):
    """`1강.  목적격 …` → ("01", "목적격 …"). 번호를 떼어 따로 세우기 위해."""
    m = RE_LEADNUM.match(txt or "")
    if not m:
        return "", (txt or "").strip()
    return f"{int(m.group(1)):02d}", txt[m.end():].strip()


# ── 기입선 ──────────────────────────────────────────────────────────────
def fields(rich):
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


def wr_row(labels, cls=""):
    """작성 영역(라벨 C) — 색 캡슐 없이 **작은 라벨 + 실제 줄**.

    라벨이 둘이면 한 줄에 나란히, 하나면 폭 전체를 쓴다.
    """
    labels = [t.lstrip("□ ").strip() for t in labels if t and t.strip()]
    if not labels:
        return ""
    if len(labels) == 1:
        return (f'<div class="wr {cls}"><span class="wl">{esc(labels[0])}</span>'
                f'<span class="wline"></span></div>')
    cells = "".join(f'<span class="wc"><span class="wl">{esc(t)}</span>'
                    f'<span class="wline"></span></span>' for t in labels)
    return f'<div class="wr multi {cls}">{cells}</div>'


def point_row(rich):
    labs = fields(rich)
    if labs and labs[0].upper().startswith("POINT"):
        labs = [labs[0][5:].strip()] + labs[1:]
    return wr_row(labs, "pt")


def write_row(rich):
    return wr_row(fields(rich), "long")


def rules(n, cls="wbox"):
    return f'<div class="{cls}">' + '<i></i>' * n + '</div>'


def grid_svg(w=174.0, h=104.0, step=5.0):
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
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#fcfaf5"/>'
            f'<g stroke="#e6e0d2" stroke-width=".16">{"".join(L)}</g>'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="none" '
            f'stroke="#d5cdba" stroke-width=".35"/></svg>')


def gridbox(label, h=104.0):
    return (f'<div class="gridbox"><div class="wl solo">{esc(label)}</div>'
            f'{grid_svg(174.0, h)}</div>')


# ── 머리 띠 ────────────────────────────────────────────────────────────
#
# 헤더는 **내비게이션 텍스트를 늘어놓는 자리가 아니다.** 두 면이 한 세트로 보이되
# 왼쪽 면과 오른쪽 면이 지는 것이 다르다(중2 같이새김 내지와 같은 구성):
#
#   왼쪽(짝수) — 왼쪽 상단에 **도형(각진 색면)** + 그 단원 표기
#   오른쪽(홀수) — 오른쪽 상단에 **도형(원)** + 크레스트 + **책 이름**
#
# 옅은 띠는 두 면에 똑같이 깔려 펼침을 가로지른다 → 세트로 읽힌다.
# ⚠ 왼쪽 면 그래픽을 반전해 오른쪽에 쓰지 않는다.
def runhead(unit_top, unit_no, label, main, sub, book, off=False):
    o = " rh-off" if off else ""
    chip = (f'<span class="chip{"" if unit_no else " solo"}">'
            f'<i class="c1">{esc(unit_top)}</i>'
            + (f'<i class="c2">{esc(unit_no)}</i>' if unit_no else '')
            + '</span>')
    txt = (f'<span class="ht"><i class="l1">{esc(label)}</i>'
           f'<i class="l2">{esc(main)}'
           + (f'<b>{esc(sub)}</b>' if sub else '') + '</i></span>')
    # 꼬리말 — 왼쪽 면은 교재명, 오른쪽 면은 단원명
    unit = "  ·  ".join(x for x in (f"{unit_top} {unit_no}".strip(), main) if x)
    return (f'<div class="rhL{o}"><div class="hd hdL">'
            f'<span class="blk"></span>{chip}{txt}</div></div>'
            f'<div class="rhR{o}"><div class="hd hdR">'
            f'<span class="bk">{esc(book)}</span>'
            f'<span class="crest"></span></div></div>'
            f'<div class="pfL{o}"><div class="ft ftL">'
            f'<span class="pn"></span>{esc(book)}</div></div>'
            f'<div class="pfR{o}"><div class="ft ftR">'
            f'{esc(unit)}<span class="pn"></span></div></div>')


# ── 제목(번호를 떼어 세운다) ────────────────────────────────────────────
def title_block(kind, num, label, text, sub=""):
    """`01 / LESSON / 제목` — 번호는 그래픽, 라벨은 A 계열, 제목이 중심."""
    n = f'<span class="tn">{esc(num)}</span>' if num else ""
    lb = f'<i class="tk">{esc(label)}</i>' if label else ""
    sb = f'<div class="tsub">{sub}</div>' if sub else ""
    return (f'<div class="ttl {kind}">{n}'
            f'<div class="tt">{lb}<h2 class="th2">{esc(text)}</h2>{sb}</div>'
            f'</div>')


# ══════════════════════════════════════════════════════════ 어휘부
def render_vocab(vol, out):
    """어휘 — WEEK 숫자가 가장 중요한 정보다(머리 면이 그것을 진다)."""
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    k = Keeper(out)
    wk_no, wk_root = "", ""
    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t == "week":
            k.flush()
            txt = plain(b["r"])
            wk_no, wname = numtitle(txt.replace("Week", "").strip()
                                    if txt.startswith("Week") else "")
            if not wk_no:
                wname = txt.lstrip("부록 —").strip() or txt
            # 그 주의 어근 정보 — 다음 분류 띠에서 가져온다
            root, gloss = "", ""
            for nb in blocks[i + 1:i + 3]:
                if nb["t"] == "group":
                    c = cols(plain(nb["r"]), 3)
                    root = c[1] if len(c) > 1 else ""
                    gloss = c[2] if len(c) > 2 else ""
                    break
            wk_root = "  ·  ".join(x for x in (root, gloss) if x)
            ttl, sub, lab = root or (wname or txt), gloss, "WEEK"
            if not wk_no:                      # 부록 — 번호가 없는 주
                ttl, sub, lab = wname or txt, "", "APPENDIX"
            out.append('<section class="week-open">'
                       + runhead("WEEK" if wk_no else "부록", wk_no,
                                 "VOCABULARY",
                                 root or (wname or txt), gloss, BOOK[0])
                       + title_block("big", wk_no, lab, ttl, esc(sub))
                       + '</section>')
        elif t == "group":
            c = cols(plain(b["r"]), 3)
            head = c[0].lstrip("■ ").strip() if c else ""
            rest = "".join(f'<span class="g{j}">{esc(v)}</span>'
                           for j, v in enumerate(c[1:], 1))
            k.head(f'<div class="vgroup"><span class="g0">{esc(head)}</span>'
                   f'{rest}</div>')
        elif t == "word":
            k.body(word_card(b))
        elif t == "appendix":
            k.body(appendix_row(b))
        else:
            k.body(generic(b))
        i += 1
    k.flush()


def word_card(b):
    """낱말 카드 — 시선은 **표제어 → 뜻/어원 → 예문 → KEY POINT** 순이다.

    원고의 `❶❷`·`❖ KEY POINT` 는 글자로 두지 않는다. KEY POINT 는 표제어보다
    먼저 보이면 안 되므로 색을 빼고 **조용한 기입 줄**로 둔다.
    """
    senses = "".join(f'<div class="w-sense">{inl(s)}</div>' for s in b["senses"])
    ex = []
    for k, e in enumerate(b["ex"], 1):
        seq = list(e)
        m = RE_EXNUM.match(plain(seq[0]) if seq else "")
        if m:
            t = plain(seq[0])[m.end():]
            seq[0] = t if isinstance(seq[0], str) else dict(seq[0], t=t)
        ex.append(f'<div class="w-ex"><span class="exn">{k}</span>'
                  f'{inl(seq)}</div>')
    key = ('<div class="w-key"><span class="wl">KEY POINT</span>'
           '<span class="wline"></span></div>')
    return (
        '<div class="wcard">'
        f'  <div class="w-l"><div class="w-head">{esc(b["head"])}'
        f'    <span class="w-no">{esc(b["no"].replace("no. ", ""))}</span></div>'
        f'    {senses}<div class="w-build">{esc(b["build"])}</div></div>'
        f'  <div class="w-r">{"".join(ex)}{key}</div>'
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
    """머리를 뒤따르는 첫 덩어리와 함께 묶는다(`break-after: avoid` 로는 부족)."""

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


# ══════════════════════════════════════════════════════════ 구문·어법부
def render_grammar(vol, out):
    """구문·어법 — PART → 강 → 세부 주제. 머리 면이 PART·주제를 진다."""
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    k = Keeper(out)
    cp = None
    drill_gram = False
    col_open = False
    qn = 0
    part_no, part_ttl = "", ""
    les_no, les_ttl = "", ""

    def close_cpage():
        nonlocal cp
        if cp is None:
            return
        out.append('<section class="cpage">' + "".join(cp["body"])
                   + gridbox(cp["grid"], cp.get("gh", 84.0)) + "</section>")
        cp = None

    def close_col():
        nonlocal col_open
        if col_open:
            k.flush()
            out.append("</div>")
            col_open = False

    def put(h):
        if cp is not None:
            cp["body"].append(h)
        else:
            k.body(h)

    def rh():
        pno = part_no.replace("PART", "").strip() or "—"
        return runhead("PART", pno, f'{vol["name"]}   {VOL_EN["grammar"]}',
                       f"{int(les_no)}강" if les_no else part_ttl,
                       les_ttl if les_no else "", BOOK[0])

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
            part_no, part_ttl = plain(b["r"]), title
            les_no = les_ttl = ""
            out.append(part_page(plain(b["r"]), title,
                                 part_items(blocks, i, ("part_no",))))
        elif t == "lesson":
            les_no, les_ttl = numtitle(plain(b["r"]))
            cp = {"body": [rh(),
                           title_block("big", les_no, "LESSON", les_ttl)],
                  "grid": "필기 노트", "gh": 108.0}
        elif t == "lesson_sub":
            put(keyline(plain(b["r"])))
        elif t == "subhead":
            nxt = blocks[i + 1]["t"] if i + 1 < n else ""
            if nxt == "notebox":
                if cp is not None:
                    cp["grid"] = plain(b["r"])
                i += 1
            elif nxt == "concept":
                put(f'<div class="blk-h">{esc(plain(b["r"]))}</div>')
            elif nxt == "bullet":
                put(f'<div class="blk-h">{esc(plain(b["r"]))}</div>')
            else:
                put(f'<div class="blk-h">{esc(plain(b["r"]))}</div>')
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
            out.append(f'<section class="drillpage{g}">{rh()}'
                       f'<div class="drill">'
                       f'<h3 class="drill-h">{esc(title)}</h3>{note}</div>'
                       f'</section>')
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
            if drill_gram and qn == HALF + 1:
                k.flush()
                out.append('<div class="pbr"></div>')
            k.body(f'<div class="qitem{g}">{q_line(b["r"])}'
                   f'<div class="qbody">' + "".join(rows) + "</div></div>")
            i = j - 1
        elif t == "ans_head":
            txt = plain(b["r"])
            if txt.startswith("PART"):
                close_col()
                c = cols(txt, 2)
                out.append('<section class="anspage">'
                           + runhead("정답", "해설", VOL_EN["grammar"],
                                     c[0] if c else "",
                                     c[1] if len(c) > 1 else "", BOOK[0])
                           + title_block("ans", "", "ANSWERS", txt)
                           + '</section><div class="anscol">')
                col_open = True
                k = Keeper(out)
            else:
                k.head(f'<h3 class="ans-lesson">{esc(txt)}</h3>')
        elif t == "ans_kind":
            g = " gram" if "어법" in plain(b["r"]) else ""
            k.head(f'<div class="ans-kind{g}">{esc(plain(b["r"]))}</div>')
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
    out = list(rich)
    if out:
        first = out[0]
        t = plain(first).lstrip()
        if t.startswith(mark):
            t = t[len(mark):].lstrip()
            out[0] = t if isinstance(first, str) else dict(first, t=t)
    return out


def keyline(txt):
    """`핵심 구조   …` — 강의 요약. 개념 면에서 **가장 먼저 읽히는 줄**."""
    c = cols(txt, 2)
    if len(c) == 2:
        return (f'<div class="keyline"><i>{esc(c[0])}</i>'
                f'<span>{esc(c[1])}</span></div>')
    return f'<div class="keyline"><span>{esc(txt)}</span></div>'


def q_line(rich):
    num, rest = "", list(rich)
    if rest and isinstance(rest[0], dict) and rest[0].get("k") == "num":
        num = plain(rest[0]).strip()
        rest = rest[1:]
    return (f'<div class="q"><span class="q-no">{esc(num)}</span>'
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
        return (f'<div class="a-item"><span class="a-lab">{esc(lab.strip())}'
                f'</span><span class="a-body">{esc(body.strip())}</span></div>')
    return f'<div class="a-item"><span class="a-body">{inl(rich)}</span></div>'


def kv_inline(rich, en=False):
    txt = plain(rich) if not isinstance(rich, str) else rich
    if "|" in txt[:14]:
        lab, _, body = txt.partition("|")
        return (f'<i class="ilab">{esc(lab.strip())}</i>{esc(body.strip())}')
    return inl(rich)


def part_page(no, title, items=()):
    rows = "".join(
        f'<div class="p-it"><span class="pn">{i:02d}</span>'
        f'<span class="pt">{esc(t)}</span></div>'
        for i, t in enumerate(items, 1))
    lst = f'<div class="p-list">{rows}</div>' if rows else ""
    return (f'<section class="partpage"><div class="slab"></div>'
            f'<div class="p-no">{esc(no)}</div>'
            f'<div class="p-ttl">{esc(title)}</div>{lst}</section>')


def part_items(blocks, i, stop, key="lesson"):
    out = []
    for b in blocks[i + 1:]:
        if b["t"] in stop:
            break
        if b["t"] == key:
            out.append(plain(b["r"]))
    return out


# ══════════════════════════════════════════════════════════ 독해부
def render_reading(vol, out):
    """독해 — WEEK 와 문제 유형이 축이다. 지문이 가장 무겁고 해석이 가장 가볍다."""
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    k = Keeper(out)
    cp = None
    wk_no, wk_ttl = "", ""
    les_no, les_ttl = "", ""
    ex_kind = ""
    pending_week = ""
    bg = None
    col_open = False      # 정답 목록은 2단으로 흐른다

    def flush_bg():
        nonlocal bg
        if bg:
            k.body(f'<div class="bgcard"><div class="bgh">{bg[0]}</div>'
                   f'<div class="bgb">{"".join(bg[1])}</div></div>')
            bg = None

    def close_cpage():
        nonlocal cp
        if cp is None:
            return
        out.append('<section class="cpage">' + "".join(cp["body"])
                   + gridbox(cp["grid"], cp.get("gh", 84.0)) + "</section>")
        cp = None

    def put(h):
        if cp is not None:
            cp["body"].append(h)
        else:
            k.body(h)

    def rh():
        # 번호가 없는 주(정답 목록)는 숫자 칸 대신 라벨만 둔다
        return runhead("WEEK" if wk_no else "ANSWERS", wk_no,
                       VOL_EN["reading"], wk_ttl,
                       ex_kind or les_ttl, BOOK[0])

    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t in ("week", "lesson", "rpart_no", "ex_tag"):
            flush_bg()
            close_cpage()
            k.flush()
            if col_open:
                out.append("</div>")
                col_open = False
        if pending_week and t not in ("week", "lesson", "rpart_no"):
            out.append(f'<section class="week-open">{rh()}'
                       + title_block("big", wk_no,
                                     "WEEK" if wk_no else "ANSWERS", wk_ttl)
                       + '</section>')
            pending_week = ""

        if t == "rpart_no":
            title = ""
            if i + 1 < n and blocks[i + 1]["t"] == "rpart_title":
                title = plain(blocks[i + 1]["r"])
                i += 1
            out.append(part_page(plain(b["r"]), title,
                                 part_items(blocks, i, ("rpart_no",), "week")))
        elif t == "week":
            txt = plain(b["r"])
            wk_no, wk_ttl = numtitle(txt.replace("Week", "").strip())
            if not wk_no:
                wk_ttl = txt
            les_no = les_ttl = ex_kind = ""
            pending_week = wk_ttl
        elif t == "lesson":
            les_no, les_ttl = numtitle(plain(b["r"]))
            pending_week = ""
            cp = {"body": [rh(),
                           title_block("big", les_no, "LESSON", les_ttl,
                                       esc(f"WEEK {wk_no}  ·  {wk_ttl}"))],
                  "grid": "필기 노트", "gh": 74.0}
        elif t == "concept_head":
            put(f'<div class="blk-h lead">'
                f'{esc(plain(b["r"]).strip("＜＞ "))}</div>')
        elif t == "block_head":
            put(f'<div class="blk-h">{esc(plain(strip_mark(b["r"], "●")))}'
                f'</div>')
        elif t == "block_bullet":
            put(f'<div class="bbul">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "wnote_head":
            if cp is not None:
                cp["grid"] = plain(b["r"]).strip().lstrip("❖ ").strip()
            else:
                k.head(f'<div class="wl solo">'
                       f'{esc(plain(b["r"]).strip().lstrip("❖ ").strip())}</div>')
        elif t == "note_head":
            txt = plain(b["r"]).strip().lstrip("❖ ").strip()
            k.head(f'<div class="wl solo">{esc(txt)}</div>')
        elif t == "notebox":
            if cp is None:
                k.body(rules(5, "wbox"))
        elif t == "ex_tag":
            c = [x for x in cols(plain(b["r"])) if x != "·"]
            ex_kind = c[1] if len(c) > 1 else ""
            out.append(f'<section class="expage">{rh()}{ex_tag(b["r"])}'
                       f'</section>')
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
                items.append(f'<li>{choice_line(blocks[j]["r"])}</li>')
                j += 1
            k.body('<ul class="choices">' + "".join(items) + "</ul>")
            i = j - 1
        elif t == "bg_head":
            # 배경지식 노트는 이 교재의 특징 콘텐츠다 → **독립 카드**로 묶는다
            flush_bg()
            bg = [esc(plain(b["r"]).strip().lstrip("❖ ").strip()), []]
        elif t == "bg_item":
            if bg:
                bg[1].append(f'<div class="bgi">'
                             f'{inl(strip_mark(b["r"], "·"))}</div>')
            else:
                k.body(f'<div class="bgi">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "trans_head":
            # 해석은 위계가 가장 낮다 — 묶어 두면 면을 통째로 넘겨 빈 면을 만든다.
            # 남은 자리에서 시작해 흐르게 둔다.
            flush_bg()
            k.flush()
            out.append(f'<div class="th">'
                       f'{esc(plain(b["r"]).strip().lstrip("❖ ").strip())}</div>')
        elif t == "trans":
            out.append(f'<div class="trans">{inl(b["r"])}</div>')
        elif t == "ans_line":
            if not col_open:
                k.flush()
                out.append('<div class="anscol lines">')
                col_open = True
            k.body(ans_line(b["r"]))
        else:
            put(generic(b))
        i += 1
    flush_bg()
    close_cpage()
    k.flush()
    if col_open:
        out.append("</div>")


def choice_line(rich):
    h = inl(rich)
    m = RE_CIRC.match(plain(rich))
    if m:
        h = h.replace(m.group(1), f'<span class="cn">{m.group(1)}</span>', 1)
    return h


def ex_tag(rich):
    c = [x for x in cols(plain(rich)) if x != "·"]
    no = c[0] if c else ""
    lvl = c[-1] if len(c) > 1 and c[-1].startswith("[") else ""
    mid = "  ·  ".join(c[1:-1] if lvl else c[1:])
    n2, _ = numtitle(no.replace("예제", "").strip())
    return (f'<div class="extag"><span class="x-no">{esc(n2 or no)}</span>'
            f'<span class="x-m"><i>EXAMPLE</i>{esc(mid)}</span>'
            f'<span class="x-l">{esc(lvl.strip("[] "))}</span></div>')


def ans_line(rich):
    txt = plain(rich).strip()
    if txt.startswith("·"):
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


def divider_page(cfg, vol, no):
    """부 간지 — **2면 한 세트**. 왼쪽은 제목 색면, 오른쪽은 그 부의 차례.

    차례를 따로 한 면에 두지 않는다 — 간지를 펼치면 무엇을 배우는지가 바로 보여야
    한다. 두 면은 책등에서 이어지는 원 하나로 묶인다.
    """
    lines = [b for b in vol["blocks"] if b["t"] == "vol_desc"]
    desc = "".join(f'<div class="d-desc">{inl(b["r"])}</div>' for b in lines)
    bk = cfg.book
    foot = "  ·  ".join(x for x in (bk.get("brand"), bk.get("school"),
                                    bk.get("teacher")) if x)
    return (
        f'<section class="dvL v-{vol["id"]}"><div class="orb"></div>'
        f'  <div class="in"><div class="d-no">PART {no:02d}</div>'
        f'    <h1 class="d-ttl">{esc(vol["name"])}</h1>'
        f'    <div class="d-en">{esc(VOL_EN.get(vol["id"], ""))}</div>'
        f'    <div class="d-rule"></div>{desc}</div>'
        f'  <div class="foot">{esc(foot)}</div></section>'
        f'<section class="dvR v-{vol["id"]}"><div class="orb"></div>'
        f'  <div class="num">{no:02d}</div>'
        + toc_body(vol) + '</section>')


def end_page(cfg, d):
    """뒤 간지 — 책을 닫는 면. `break-before: left` 라 마지막 면이 짝수가 된다."""
    bk = cfg.book
    foot = "  ·  ".join(x for x in (bk.get("school"), bk.get("teacher")) if x)
    # ⚠ 러닝 요소(`position: running()`)를 이 섹션 **안에** 두면 섹션이 통째로
    #   비어 나온다(실측). 형제로 앞에 둔다.
    return ('<div class="rhL rh-off"></div><div class="rhR rh-off"></div>'
            '<div class="pfL rh-off"></div><div class="pfR rh-off"></div>'
            f'<section class="endpage v-{d["volumes"][-1]["id"]}">'
            '<div class="bg"></div><div class="orb"></div>'
            f'<div class="e-in"><div class="e-brand">'
            f'{esc(bk.get("brand", ""))}</div>'
            f'<div class="e-ttl">{esc(bk.get("title", ""))}</div>'
            '<div class="e-rule"></div>'
            f'<div class="e-sub">{esc(bk.get("subject", ""))}</div></div>'
            f'<div class="e-foot">{esc(foot)}</div>'
            '<div class="e-logo"></div></section>')


def toc_body(vol):
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
    return ('<div class="toc">'
            '<div class="toc-k">CONTENTS</div>'
            + "".join(rows) + "</div>")


# ──────────────────────────────────────────────────────────────── 조립
RENDERERS = {"vocab": render_vocab, "grammar": render_grammar,
             "reading": render_reading}


def write(cfg, d, build_dir, log=print, memos=1, fills=()):
    BOOK[0] = (cfg.book.get("running")
               or f'{cfg.book.get("school", "")} {cfg.book.get("title", "")}')
    m = metrics_of(cfg)
    pal = cfg.section("palette") or {}
    parts = [cover_page(cfg, d["cover"])]
    for k, vol in enumerate(d["volumes"], 1):
        vid = vol["id"]
        vol["part"] = f"PART {k:02d}"
        parts.append(f'<div class="vol v-{vid}">')
        parts.append(divider_page(cfg, vol, k))
        body = []
        RENDERERS.get(vid, render_reading)(vol, body)
        parts.append('<div class="flow">' + "".join(body) + "</div>")
        parts.append("</div>")
    parts.append(end_page(cfg, d))

    fill_css = "".join(
        f"@page :nth({n}) {{ background: {c}; }}\n" for n, c in fills)
    css_vars = ":root{\n" + "".join(
        f"  --mgn-{k.split('_')[1]}: {v}mm;\n" for k, v in m.items()
        if k.startswith("margin_")) + "}\n" + palette_css(pal) + fill_css

    doc = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
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
RE_SEPS = re.compile(r"[|→·•●❖＜＞\[\]\t]| {2,}")


def probe_text(text, floor=10):
    frags = [f.strip() for f in RE_SEPS.split(text or "")]
    best = max(frags, key=len) if frags else ""
    return best[:70] if len(best) >= floor else ""


def verify_sequence(d):
    """조판 순서대로 (설명, 원문 조각). 표식이 아니라 **본문 글자**를 센다."""
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
                    frag = probe_text(RE_EXNUM.sub("", txt))
                    if frag:
                        seq.append((f"{vid}/{b['head']} 예문", frag))
                continue
            frag = probe_text(plain(b.get("r")))
            if frag:
                seq.append((f"{vid}/{t}", frag))
    return seq
