"""특강 합본(special) 렌더러 — data.json → build/index.html.

## 왜 흐름 조판인가

이 책의 항목은 높이가 제각각이다(낱말 카드 1줄~4줄, 예제 지문 6줄~14줄, 해설
2줄~8줄). 블랙북처럼 슬롯에 앉히려면 슬롯을 항목 최대치에 맞춰야 하고 그러면 면이
비어 보인다. 그래서 **덩어리는 쪼개지 않는다**(`break-inside: avoid`)만 걸고
나머지는 흐르게 둔다. 대신 흐름이 깨지면 안 되는 곳에만 면을 고정한다:

  · 부(部) 간지 · 목차 · PART 표지 — 오른쪽(홀수) 면에서 시작
  · 어휘 Week · 구문어법 강 · 독해 예제 — 새 면에서 시작
    (예제 한 벌 = 태그+발문+지문+선택지+NOTE+해석. 한 면에 딱 들어가고, 학생이
     쓰는 NOTE 칸이 면 아래에 여유 있게 남는다.)

## 원고의 '공백 정렬'을 표로 되돌린다

원고는 목차·부록·정답을 **공백 여러 칸으로 줄맞춤**해 두었다(Word 에서 눈으로
맞춘 것). 그대로 흘리면 비례 서체에서 어긋난다 → 2칸 이상 공백을 열 경계로 보고
표로 되돌린다. 부록만은 줄맞춤이 들쭉날쭉해서(한 칸만 띈 줄이 있다) **한글이
끝나는 곳**을 뜻과 예시의 경계로 삼는다 — 공백 수가 아니라 글자 종류로.

## 기입선

원고의 밑줄 친 탭(`\\t`)이 학생이 쓰는 자리다. 탭을 그대로 두면 폭이 서체에
휘둘리므로 **남은 폭을 채우는 상자**로 바꾼다.
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
    """뜻(한글·괄호) / 예시(영문)의 경계 — 공백 수가 아니라 **글자 종류**로.

    부록의 줄맞춤은 들쭉날쭉하다("… 가치, 힘 value  valuable" 처럼 한 칸만 띈
    줄이 있다). 마지막 한글(또는 닫는 괄호) 뒤가 예시다.
    """
    last = -1
    for i, ch in enumerate(text):
        if RE_HAN.match(ch) or ch == ")":
            last = i
    if last < 0:
        return "", text.strip()
    return text[:last + 1].strip(), text[last + 1:].strip()


# ── 기입선 ──────────────────────────────────────────────────────────────
def fields(rich):
    """rich → [(라벨, 기입선 유무)]. 원고의 밑줄 탭이 기입선이다."""
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


def field_row(rich, cls="frow"):
    labels = fields(rich)
    if len(labels) <= 1:
        return f'<div class="{cls}"><span class="fl">{esc(labels[0] if labels else "")}</span>' \
               f'<span class="fline"></span></div>'
    cells = "".join(f'<span class="fcell"><span class="fl">{esc(t)}</span>'
                    f'<span class="fline"></span></span>' for t in labels)
    return f'<div class="{cls} multi">{cells}</div>'


def rules(n, cls="wbox"):
    """괘선 상자 — 괘선은 실제 요소로 그린다.

    (얇은 괘선을 `linear-gradient` 배경으로 깔면 72dpi 래스터로 나가 사라진다.)
    """
    return f'<div class="{cls}">' + '<i></i>' * n + '</div>'


# ── 부(部) 머리말 갱신자 ────────────────────────────────────────────────
def runhead(vol, right):
    return (f'<div class="rh"><span class="rh-l">{esc(vol)}</span>'
            f'<span class="rh-r">{esc(right)}</span></div>')


# ══════════════════════════════════════════════════════════ 부별 렌더러
def render_vocab(vol, out):
    """어휘부 — Week 마다 새 면, 분류 띠 아래 낱말 카드가 흐른다."""
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    week = ""
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


# ─────────────────────────────────────────────────────────── 구문·어법부
def render_grammar(vol, out):
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    lesson = ""
    in_ans = False
    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t == "part_no":
            title = ""
            if i + 1 < n and blocks[i + 1]["t"] == "part_title":
                title = plain(blocks[i + 1]["r"])
                i += 1
            in_ans = not title            # '정답 및 해설' 은 제목이 따로 없다
            lesson = plain(b["r"])
            out.append(part_page(vol, plain(b["r"]), title))
        elif t == "lesson":
            lesson = plain(b["r"])
            out.append(f'<section class="lesson-open">'
                       f'{runhead(vol["name"], lesson)}'
                       f'<h3 class="lesson">{inl(b["r"])}</h3></section>')
        elif t == "lesson_sub":
            out.append(kv_line(plain(b["r"]), "lsub"))
        elif t == "subhead":
            out.append(f'<h4 class="subhead">{inl(b["r"])}</h4>')
        elif t == "bullet":
            out.append(f'<div class="bul">{inl(strip_mark(b["r"], "•"))}</div>')
        elif t == "concept":
            out.append(f'<div class="concept">{kv_inline(plain(b["r"]))}</div>')
        elif t == "notebox":
            out.append(rules(9, "wbox big"))
        elif t == "drill":
            note = ""
            if i + 1 < n and blocks[i + 1]["t"] == "drill_note":
                note = f'<div class="drill-note">{inl(blocks[i + 1]["r"])}</div>'
                i += 1
            out.append(f'<div class="drill"><h4>{inl(b["r"])}</h4>{note}</div>')
        elif t == "q":
            j = i + 1
            rows = []
            while j < n and blocks[j]["t"] in ("q_point", "q_field"):
                rows.append(field_row(blocks[j]["r"],
                                      "frow pt" if blocks[j]["t"] == "q_point"
                                      else "frow"))
                j += 1
            out.append(f'<div class="qitem">{q_line(b["r"])}'
                       + "".join(rows) + "</div>")
            i = j - 1
        elif t == "ans_head":
            txt = plain(b["r"])
            cls = "ans-part" if txt.startswith("PART") else "ans-lesson"
            if cls == "ans-part":
                lesson = txt
            out.append(f'<h3 class="{cls}">{runhead(vol["name"], "정답 및 해설")}'
                       f'{inl(b["r"])}</h3>')
        elif t == "ans_kind":
            out.append(f'<div class="ans-kind">{inl(b["r"])}</div>')
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
            out.append(f'<div class="aitem">{ans_q_line(b["r"])}'
                       + "".join(body) + "</div>")
            i = j - 1
        else:
            out.append(generic(b))
        i += 1


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
    """문항 — 앞머리 번호를 배지로 뗀다."""
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
    """`주어  |  …` — 라벨과 내용을 나눈다."""
    txt = plain(rich)
    if "|" in txt:
        lab, _, body = txt.partition("|")
        return (f'<div class="a-item"><span class="a-lab">{esc(lab.strip())}</span>'
                f'<span class="a-body">{esc(body.strip())}</span></div>')
    return f'<div class="a-item"><span class="a-body">{inl(rich)}</span></div>'


def kv_line(txt, cls):
    """`핵심 구조   …` — 앞 라벨을 칩으로."""
    c = cols(txt, 2)
    if len(c) == 2:
        return (f'<div class="{cls}"><span class="chip">{esc(c[0])}</span>'
                f'<span>{esc(c[1])}</span></div>')
    return f'<div class="{cls}"><span>{esc(txt)}</span></div>'


def kv_inline(rich, en=False):
    """`어법 개념 | …` / `문제 | …` — 해설 쪽 원고의 라벨 표기."""
    txt = plain(rich) if not isinstance(rich, str) else rich
    if "|" in txt[:14]:
        lab, _, body = txt.partition("|")
        return (f'<span class="chip">{esc(lab.strip())}</span>'
                f'<span class="{"en" if en else ""}">{esc(body.strip())}</span>')
    return inl(rich)


def part_page(vol, no, title):
    return (f'<section class="partpage">{runhead(vol["name"], no)}'
            f'<div class="p-no">{esc(no)}</div>'
            f'<div class="p-ttl">{esc(title)}</div></section>')


# ───────────────────────────────────────────────────────────────── 독해부
def render_reading(vol, out):
    blocks = vol["blocks"]
    i, n = 0, len(blocks)
    week = ""
    while i < n:
        b = blocks[i]
        t = b["t"]
        if t in FRONT:
            i += 1
            continue
        if t == "rpart_no":
            title = ""
            if i + 1 < n and blocks[i + 1]["t"] == "rpart_title":
                title = plain(blocks[i + 1]["r"])
                i += 1
            out.append(part_page(vol, plain(b["r"]), title))
        elif t == "week":
            week = plain(b["r"])
            out.append(f'<section class="week-open">{runhead(vol["name"], week)}'
                       f'<h2 class="week">{inl(b["r"])}</h2></section>')
        elif t == "lesson":
            out.append(f'<section class="lesson-open">'
                       f'{runhead(vol["name"], week + "  ·  " + plain(b["r"]))}'
                       f'<h3 class="lesson">{inl(b["r"])}</h3></section>')
        elif t == "concept_head":
            out.append(f'<div class="ch">{esc(plain(b["r"]).strip("＜＞ "))}</div>')
        elif t == "block_head":
            out.append(f'<h4 class="bh">{inl(strip_mark(b["r"], "●"))}</h4>')
        elif t == "block_bullet":
            out.append(f'<div class="bbul">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "note_head":
            txt = plain(b["r"]).strip()
            out.append(f'<div class="nh">{esc(txt.lstrip("❖ ").strip())}</div>')
        elif t == "notebox":
            out.append(rules(6, "wbox"))
        elif t == "ex_tag":
            out.append(ex_tag(b["r"]))
        elif t == "stem":
            out.append(f'<div class="stem">{inl(b["r"])}</div>')
        elif t == "passage":
            out.append(f'<div class="psg">{inl(b["r"])}</div>')
        elif t == "footnote":
            out.append(f'<div class="fnote">{inl(b["r"])}</div>')
        elif t == "choice":
            j = i
            items = []
            while j < n and blocks[j]["t"] == "choice":
                items.append(f'<li>{inl(blocks[j]["r"])}</li>')
                j += 1
            out.append('<ul class="choices">' + "".join(items) + "</ul>")
            i = j - 1
        elif t == "bg_head":
            txt = plain(b["r"]).strip().lstrip("❖ ").strip()
            out.append(f'<div class="bgh">{esc(txt)}</div>')
        elif t == "bg_item":
            out.append(f'<div class="bgi">{inl(strip_mark(b["r"], "·"))}</div>')
        elif t == "trans_head":
            out.append('<div class="th">해석</div>')
        elif t == "trans":
            out.append(f'<div class="trans">{inl(b["r"])}</div>')
        elif t == "ans_line":
            out.append(ans_line(b["r"]))
        else:
            out.append(generic(b))
        i += 1


def ex_tag(rich):
    c = [x for x in cols(plain(rich)) if x != "·"]
    no = c[0] if c else ""
    lvl = c[-1] if len(c) > 1 and c[-1].startswith("[") else ""
    mid = "  ·  ".join(c[1:-1] if lvl else c[1:])
    return (f'<div class="extag"><span class="x-no">{esc(no)}</span>'
            f'<span class="x-m">{esc(mid)}</span>'
            f'<span class="x-l">{esc(lvl.strip("[] "))}</span></div>')


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
                k, _, v = txt.partition("\t")
                rows.append(f'<tr><th>{esc(k.strip())}</th>'
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
            k = esc(c[0]) if c else ""
            rest = "".join(f'<span class="t{i}">{esc(v)}</span>'
                           for i, v in enumerate(c[1:], 1))
            cls = "t-1" if rest else "t-1 solo"
            rows.append(f'<div class="{cls}"><span class="t0">{k}</span>{rest}</div>')
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
def verify_sequence(d):
    """조판 순서대로 (설명, 원문) — PDF 전문에서 그대로 찾는다.

    표식이 아니라 **내용**을 센다. 낱말·문항·지문 본문이 그 순서로 다 있어야 한다.
    """
    seq = []
    for vol in d["volumes"]:
        vid = vol["id"]
        for b in vol["blocks"]:
            t = b["t"]
            if t == "word":
                seq.append((f"{vid}/{b['no']} {b['head']}", b["head"]))
                for e in b["ex"]:
                    txt = "".join(plain(s) for s in e
                                  if not (isinstance(s, dict)
                                          and s.get("k") == "src"))
                    seq.append((f"{vid}/{b['head']} 예문", txt.strip("❶❷ ")[:60]))
            elif t in ("q", "ans_en", "passage", "trans", "choice", "concept"):
                txt = plain(b["r"])
                if t == "q":
                    txt = re.sub(r"^\s*\d+\s+", "", txt)
                if len(txt.strip()) >= 12:
                    seq.append((f"{vid}/{t}", txt.strip()[:60]))
    return seq
