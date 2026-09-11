"""세서특필 렌더러 — data.json → build/index.html.

## 면 구성 (정본 26-1 기말과 같은 순서)

    1  표지 속(정본 면)          §ART1§
    2·3 CONTENTS 펼침(정본 면)   §ART2§ §ART3§
    4·5 PART 1 간지(정본 면)     §ART4§ §ART5§
    6~ PART 1 세희T PICK 중요문장          ← 왼쪽 면에서 연다
       (MEMO)
    PART 2 간지(정본 면)         §ART6§ §ART7§ ← 왼쪽 면
    대표유형 01~NN (설명 = 왼쪽 면, 연습 = 오른쪽 면)
    광문고 기출 서술형 실전문제 (세트마다 새 면)
    정답 및 해설 (2단)
    뒤표지 속(정본 면)           §ART8§       ← 왼쪽 면 = 마지막 면(짝수)

정본 면 자리는 빈 면에 표식만 심어 두고, 조판이 끝난 뒤 `finish.inserts` 가
정본 PDF 의 면으로 바꿔 끼운다. 쪽번호가 실제 면 번호와 맞도록 자리를 먼저 차지한다.

## 절은 왼쪽 면에서 연다
`break-before: left` 가 만든 백면은 1패스에서 찾아, 2패스에서 그 자리에 **MEMO 면**을
넣는다(정본 p.93 과 같은 방식). 어느 절 앞이 비었는지는 백면 **다음 면**의 표식
(§S…§ / §P…§ / §ART…§)으로 안다.
"""
import html
import os
import re

from core.render_vivlio import stage

# ── 부(部)별 색 — 정본 실측(화면색). CMYK 는 계열 print_defaults 에서 못 박는다 ──
PAL = {
    1: {"band": "#ffe4b9", "pill": "#f8a57e", "tab": "#5b579f", "shadow": "#824f8c",
        "arc": "#f58e7d", "dot": "#a4a8d5"},
    2: {"band": "#dbddef", "pill": "#959ecf", "tab": "#5b579f", "shadow": "#824f8c",
        "arc": "#a4a8d5", "dot": "#f58e7d"},
    3: {"band": "#f5dada", "pill": "#daa0af", "tab": "#824f8c", "shadow": "#5b579f",
        "arc": "#f6a0b0", "dot": "#a4a8d5"},
}
PART_NO = {1: 1, 2: 2, 3: 2}         # 정답 및 해설도 PART 02 의 절이다

RE_MARK = re.compile(r'\(([a-h])\)')
RE_NOTICE = re.compile(r'^([⟪《][^⟫》]+[⟫》])\s*')


def esc(s):
    return html.escape(s or "", quote=False)


def inl(x):
    """서식 조각 → HTML (굵게·밑줄)."""
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


def mk(tag):
    return f'<span class="mk">§{tag}§</span>'


def mkz(tag):
    """흐름 속 자리표시 — 높이 0 짜리 블록(줄을 만들지 않는다)."""
    return f'<div class="mkz">§{tag}§</div>'


# ── 아이콘 (24 단위 viewBox · 정본의 이모지 자리) ────────────────────────
def _svg(body, vb="0 0 24 24"):
    return (f'<span class="ic"><svg viewBox="{vb}" xmlns="http://www.w3.org/2000/svg">'
            f'{body}</svg></span>')


ICON = {
    # 4줄 요약 — 메모지
    "note": _svg('<rect x="4" y="3" width="16" height="18" rx="2.6" fill="#fee5db" '
                 'stroke="#e35a4d" stroke-width="1.7"/>'
                 '<path d="M8 8.5h8M8 12h8M8 15.5h5" stroke="#e35a4d" stroke-width="1.7" '
                 'stroke-linecap="round"/>'),
    # 3단계 프로세스 — 전구
    "bulb": _svg('<path d="M12 2.6a6.6 6.6 0 0 0-3.9 11.9c.7.5 1.1 1.3 1.1 2.1v.6h5.6v-.6'
                 'c0-.8.4-1.6 1.1-2.1A6.6 6.6 0 0 0 12 2.6z" fill="#ffe9a4" stroke="#fcbb6e" '
                 'stroke-width="1.3"/><path d="M10.4 12.4 12 9.8l1.6 2.6" fill="none" '
                 'stroke="#f58e7d" stroke-width="1.1" stroke-linecap="round" '
                 'stroke-linejoin="round"/><rect x="9.2" y="17.9" width="5.6" height="1.7" '
                 'rx=".8" fill="#a4a8d5"/><rect x="9.9" y="20.2" width="4.2" height="1.6" '
                 'rx=".8" fill="#a4a8d5"/>'),
    # 필승법 — 불꽃
    "flame": _svg('<path d="M12.4 2.2c.4 3-1.6 4.6-3.2 6.4C7.6 10.4 6 12.3 6 15.1 6 18.9 8.7 '
                  '21.8 12 21.8s6-2.7 6-6.5c0-2.7-1.3-4.4-2.5-5.9-.1 1.3-.7 2.3-1.6 2.9'
                  '.3-3.7-.3-6.8-1.5-9.3z" fill="#f58e7d"/><path d="M12.2 11.4c.2 1.6-.7 '
                  '2.5-1.5 3.4-.7.8-1.3 1.7-1.3 2.9 0 1.7 1.2 3 2.7 3s2.8-1.3 2.8-3c0-1.3-.6'
                  '-2.1-1.2-2.8-.1.7-.4 1.1-.8 1.4.1-1.9-.1-3.5-.7-4.9z" fill="#ffe9a4"/>'),
    # 해설 — 돋보기
    "lens": _svg('<circle cx="10.2" cy="10.2" r="6.2" fill="#fff" stroke="#5b579f" '
                 'stroke-width="1.9"/><path d="M14.8 14.8l5.6 5.6" stroke="#5b579f" '
                 'stroke-width="2.6" stroke-linecap="round"/><path d="M7.2 9a3.4 3.4 0 0 1 '
                 '2.6-2.4" fill="none" stroke="#a4a8d5" stroke-width="1.4" '
                 'stroke-linecap="round"/>'),
    # 오답 주의 — 말풍선
    "warn": _svg('<path d="M4 5.6A2.6 2.6 0 0 1 6.6 3h10.8A2.6 2.6 0 0 1 20 5.6v8.2a2.6 2.6 '
                 '0 0 1-2.6 2.6H11l-4.4 4v-4A2.6 2.6 0 0 1 4 13.8z" fill="#e35a4d"/>'
                 '<path d="M12 6.6v4.6" stroke="#fff" stroke-width="2.1" '
                 'stroke-linecap="round"/><circle cx="12" cy="13.6" r="1.15" fill="#fff"/>'),
}

PEN = ('<span class="pen"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
       '<rect x="2" y="2" width="20" height="20" fill="#fff"/>'
       '<path d="M15.6 3.8l4.6 4.6L9.1 19.5 3.4 20.6l1.1-5.7z" fill="#fff" '
       'stroke="#a4a8d5" stroke-width="1.35" stroke-linejoin="round"/>'
       '<path d="M13.4 6l4.6 4.6M4.5 14.9l4.6 4.6" stroke="#a4a8d5" stroke-width="1.35"/>'
       '</svg></span>')

DARROW = ('<div class="darrow"><svg viewBox="0 0 10 12" xmlns="http://www.w3.org/2000/svg">'
          '<path d="M5 1v8.2M1.6 6.2 5 9.8l3.4-3.6" fill="none" stroke="#f58e7d" '
          'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')


# ── 머리(러닝) ─────────────────────────────────────────────────────────
def _svg_hd(body, texts=""):
    """머리 한 벌 = 도형(SVG) + 글자(HTML).

    ⚠ 글자를 SVG `<text>` 로 두면 **웹서체를 안 탄다**(Vivliostyle 실측 — 가나초콜릿이
      시스템 고딕으로 대체됐다). 글자는 HTML 로 얹고 `.hd` 안에서만 절대 위치를 준다
      (러닝 요소 자체에는 position 을 주지 않는다).
    """
    return ('<div class="hd"><svg viewBox="0 0 216 31.5" xmlns="http://www.w3.org/2000/svg">'
            f'{body}</svg>{texts}</div>')


def _ht(cls, left, top, text, right=None):
    pos = f"right:{right}mm" if right is not None else f"left:{left}mm"
    return f'<span class="ht {cls}" style="{pos};top:{top}mm">{esc(text)}</span>'


def band(part, title):
    """절 첫 면(왼쪽)의 띠 — PART 알약. 좌표 = 정본 p.6/36/94 미디어 mm."""
    p = PAL[part]
    no = f"{PART_NO[part]:02d}"
    return _svg_hd(
        f'<rect x="0" y="0" width="216" height="31.5" fill="{p["band"]}"/>'
        f'<rect x="41.66" y="11.6" width="1.79" height="14.2" rx=".9" fill="{p["shadow"]}"/>'
        f'<rect x="26.8" y="12.5" width="143.53" height="13.5" rx="6.75" fill="{p["pill"]}"/>'
        '<path d="M61.3 12.74H163.55A6.5 6.5 0 0 1 163.55 25.74H61.3Z" fill="#fff"/>'
        f'<path d="M31.8 27V12.3Q31.8 11.6 32.5 11.6H41.84Q42.54 11.6 42.54 12.3V27Z" '
        f'fill="{p["tab"]}"/>',
        _ht("h-pa", 33.19, BAND_Y["pa"], "PA") + _ht("h-pa", 33.46, BAND_Y["rt"], "RT")
        + _ht("h-no", 46.33, BAND_Y["no"], no) + _ht("h-ti", 66.13, BAND_Y["ti"], title))


# 머리 글자 윗변(mm, 줄높이 1) — 정본 글자 중심에 맞춰 잰 값
BAND_Y = {"pa": 14.88, "rt": 19.82, "no": 16.14, "ti": 17.09, "logo": 16.82}


def curve(part, side, label=""):
    """곡선 머리. 오른쪽 면에는 워드마크(또는 MEMO)."""
    p = PAL[part]
    x0, x1 = (19.365, 195.685) if side == "R" else (18.115, 194.435)
    r, top, bot = 6.4, 12.7, 19.4
    body = (f'<path d="M{x0} {bot}V{top + r}A{r} {r} 0 0 1 {x0 + r} {top}H{x1 - r}'
            f'A{r} {r} 0 0 1 {x1} {top + r}V{bot}" fill="none" stroke="{p["arc"]}" '
            f'stroke-width=".42"/>'
            f'<circle cx="{x0}" cy="20.09" r="1.14" fill="{p["dot"]}"/>'
            f'<circle cx="{x1}" cy="20.09" r="1.14" fill="{p["dot"]}"/>')
    texts = _ht("h-logo", 0, BAND_Y["logo"], label, right=24.6) if label else ""
    return _svg_hd(body, texts)


def runners(cfg, part, title, with_band=True):
    """절 머리에서 거는 러닝 요소 한 벌 — 띠(왼쪽) · 곡선(양쪽) · 꼬리말(양쪽)."""
    b = cfg.book
    wm = b.get("wordmark", "세/서/특/필")
    no = PART_NO[part]
    out = []
    if with_band:
        out.append(f'<div class="rhL">{band(part, title)}</div>')
    out.append(f'<div class="rhL">{curve(part, "L")}</div>')
    out.append(f'<div class="rhR">{curve(part, "R", wm)}</div>')
    out.append('<div class="pfL"><div class="ft ftL"><span class="pn"></span>'
               f'<span class="bar">|</span><span class="run">{esc(b.get("running", ""))}</span>'
               f'<span class="wm">{esc(wm)}</span></div></div>')
    out.append('<div class="pfR"><div class="ft ftR">'
               f'<span class="sect"><i>필승법 PART. {no:02d}</i>{esc(title)}</span>'
               '<span class="bar">|</span><span class="pn"></span></div></div>')
    return "".join(out)


def memo_page(cfg, part):
    """MEMO 면 — 곡선 머리 + MEMO. 뒤따르는 면이 MEMO 머리를 물려받지 않게 곡선을 다시 건다."""
    return (f'<div class="memo"><div class="rhL">{curve(part, "L")}</div>'
            f'<div class="rhR">{curve(part, "R", "MEMO")}</div>{mk("MEMO")}</div>'
            f'<div class="rhL">{curve(part, "L")}</div>'
            f'<div class="rhR">{curve(part, "R", cfg.book.get("wordmark", "세/서/특/필"))}</div>')


def art(n, left=False):
    return f'<div class="art{" left" if left else ""}">{mk(f"ART{n}")}</div>'


# ── PART 1 ─────────────────────────────────────────────────────────────
def render_part1(cfg, items):
    out = []
    prev = None
    for it in items:
        t = it["t"]
        if t == "group":
            if it["kind"]:
                out.append(f'<div class="grp"><span class="dot">&gt;</span>'
                           f'<span class="k">{esc(it["kind"])}</span>'
                           f'<span class="r">{esc(it["rest"])}</span></div>')
            prev = "grp"
            continue
        if t == "src":
            cls = "srcw" + (" first" if prev == "grp" else "")
            out.append(f'<div class="{cls}"><span class="src">{esc(it["r"])}</span></div>')
            prev = "src"
        elif t == "sent":
            out.append(f'<div class="sent a-{prev}"><p class="en">{esc(it["en"])}</p>'
                       f'<p class="ko">{esc(it["ko"])}</p>'
                       f'<div class="wbox">{PEN}</div></div>')
            prev = "sent"
        elif t == "pt":
            exp = "".join(f'<p class="pexp">{inl(e)}</p>' for e in it["exp"])
            out.append(f'<div class="pt a-{prev}"><span class="plab">{esc(it["label"])}</span>'
                       f'<p class="pat">{esc(it["pat"])}</p>{exp}</div>')
            prev = "pt"
    return "".join(out)


# ── 문항 몸체 ──────────────────────────────────────────────────────────
def stem_html(s):
    s = esc(s)
    return re.sub(r'\[원문 변형\]', '<span class="tg">[원문 변형]</span>', s)


def passage_html(r):
    t = plain(r) if not isinstance(r, str) else r
    m = RE_NOTICE.match(t) if isinstance(r, str) else None
    if m:
        return f'<b>{esc(m.group(1))}</b> {esc(t[m.end():])}'
    return inl(r)


def grammar_html(r):
    """어법 지문(밑줄 조각) — 안내문 제목 ⟪…⟫ 은 지문 상자와 같이 굵게."""
    if r and isinstance(r[0], str):
        m = RE_NOTICE.match(r[0])
        if m:
            return f'<b>{esc(m.group(1))}</b> ' + inl([r[0][m.end():]] + list(r[1:]))
    return inl(r)


def sub_line(r):
    """소문항 줄 — 앞의 (a) 기호에 색을 준다(읽는 기준점)."""
    return re.sub(r'^\(([a-h])\)', r'<span class="sm">(\1)</span>', inl(r))


def qbody(blocks, main_box="cbox"):
    out = []
    for b in blocks:
        t = b["t"]
        if t == "line":
            out.append(f'<p class="ql">{sub_line(b["r"])}</p>')
        elif t == "summary":
            out.append(f'<div class="cbox sum"><span class="bl">〈요약문〉</span>'
                       f'{inl(b["r"])}</div>')
        elif t == "grammar":
            out.append(f'<div class="{main_box}">{grammar_html(b["r"])}</div>')
        elif t == "passage":
            out.append(f'<div class="{main_box}">{passage_html(b["r"])}</div>')
        elif t == "bogi":
            out.append(f'<div class="bogi"><div class="bl">&lt;보기&gt;</div>'
                       f'<div class="bw">{esc(b["r"])}</div></div>')
        elif t == "case":
            out.append(f'<div class="cbox case"><span class="bl">[{esc(b["label"])}]</span>'
                       f'{inl(b["r"])}</div>')
        elif t == "diagram":
            sep = DARROW if b.get("flow", True) else '<div class="dgap"></div>'
            steps = sep.join(f'<div class="dstep">{inl(s)}</div>' for s in b["steps"])
            out.append(f'<div class="diag"><div class="bl">[{esc(b["title"])}]</div>'
                       f'{steps}</div>')
    return "".join(out)


# ── PART 2 · 대표유형 ──────────────────────────────────────────────────
RE_FIRST_SENT = re.compile(r'^(.+?[.!?])(\s|$)')


def exp_para(t):
    if re.match(r'^\([a-h]\)', t):
        m = RE_FIRST_SENT.match(t)
        if m:
            return (f'<p class="it"><span class="hl">{esc(m.group(1))}</span>'
                    f'{esc(t[m.end(1):])}</p>')
        return f'<p class="it">{esc(t)}</p>'
    return f'<p>{esc(t)}</p>'


def answer_inline(a):
    parts = [p.strip() for p in re.split(r'\s{2,}(?=\([a-h]\))', a) if p.strip()]
    return "&nbsp;&nbsp; ".join(RE_MARK.sub(r'<span class="m">(\1)</span>', esc(p))
                                 for p in parts)


def render_type(cfg, ty, summary=None, sid=""):
    title = f'대표유형 {ty["no"]:02d} : {ty["title"]}'
    out = [f'<div class="sec band" id="{sid}">{mkz(sid)}{runners(cfg, 2, title)}']
    if summary:
        items = "".join(f'<p class="sum-i"><span class="hl">{esc(s)}</span></p>'
                        for s in summary["items"])
        out.append(f'<div class="sum"><div class="sum-t">{ICON["note"]}'
                   f'{esc(summary["title"])}</div>{items}</div>')
    out.append(f'<div class="tbar"><span class="dot">&gt;</span>{esc(ty["kind"])}</div>')
    out.append("".join(f'<p class="tdesc">{esc(d)}</p>' for d in ty["desc"]))
    steps = "".join(
        f'<div class="step s{s["no"]}"><div class="step-h"><span class="pill">STEP {s["no"]}</span>'
        f'{esc(s["title"])}</div><div class="cham"><div>'
        + "".join(f'<p>{esc(x)}</p>' for x in s["body"]) + '</div></div></div>'
        for s in ty["steps"])
    out.append(f'<div class="proc"><div class="proc-t">{ICON["bulb"]}{esc(ty["proc"])}</div>'
               f'{steps}</div>')
    out.append(f'<div class="note tipn"><div class="nt">{ICON["flame"]}{esc(ty["tip_title"])}'
               '</div>' + "".join(f'<p class="tip">{esc(t)}</p>' for t in ty["tip"]) + '</div>')

    pid = f'P{ty["no"]}'
    prob = [f'<div class="prob" id="{pid}">{mkz(pid)}'
            f'<div class="prob-h"><span class="no">연습 {ty["no"]:02d}</span>'
            f'{stem_html(ty["stem"])}</div>']
    if ty["tag"]:
        prob.append(f'<div class="xtag-row"><span class="xtag">{esc(ty["tag"])}</span></div>')
    prob.append(f'<div class="qbody">{qbody(ty["blocks"], main_box="pbox2")}</div>')
    prob.append(f'<div class="note expn"><div class="nt">{ICON["lens"]}{esc(ty["exp_title"])}'
                '</div><div class="exp">' + "".join(exp_para(t) for t in ty["exp"])
                + '</div></div>')
    prob.append(f'<div class="wbx"><div class="wrong-t">{ICON["warn"]}{esc(ty["wrong_title"])}'
                '</div><ul class="wrong">' + "".join(f'<li>{esc(w)}</li>' for w in ty["wrong"])
                + '</ul></div>')
    prob.append(f'<p class="pans"><span class="lab">[연습 {ty["no"]:02d} 정답]</span>'
                f'{answer_inline(ty["answer"])}</p>')
    prob.append('</div>')
    out.append("".join(prob))
    out.append('</div>')
    return "".join(out)


# ── PART 2 · 실전 세트 ────────────────────────────────────────────────
def render_set(s, first=False, fit=0, gap=None):
    """fit = 한 면에 넣으려고 조인 단계(0~4) · gap = 면 아래 남는 자리의 몫 —
    {"q": {문항번호: 문항 앞에 더할 mm}, "l": {문항번호: 소문항 줄 사이에 더할 mm}}."""
    badge = '<span class="badge">광문고 기출</span>' if s["gichul"] else ""
    cls = "set" + (" first" if first else "") + "".join(f" fit{k}" for k in range(1, fit + 1))
    g = gap or {}
    out = [f'<div class="{cls}">{mkz("B%d" % s["lo"])}'
           f'<div class="set-src">{badge}'
           f'<span class="stab">&lt;{esc(s["src"])}&gt;</span></div>']
    for h in s["hist"]:
        out.append(f'<p class="hist"><b>광문고 기출 출제 이력</b>{esc(h)}</p>')
    out.append(f'<p class="lead"><span class="rg">[{s["lo"]}~{s["hi"]}]</span>'
               f'{esc(s["lead"])}</p>')
    for p in s["passages"]:
        lab = f'<span class="plab2">[{esc(p["label"])}]</span>' if p["label"] else ""
        out.append(f'<div class="pbox"><div class="cham"><div>{lab}{passage_html(p["r"])}'
                   '</div></div></div>')
    for q in s["qs"]:
        xg, xl = g.get("q", {}).get(q["no"], 0), g.get("l", {}).get(q["no"], 0)
        sty = f' style="--xg:{xg:.1f}mm;--xl:{xl:.1f}mm"' if xg or xl else ""
        out.append(f'<div class="q"{sty}>{mkz("Q%d" % q["no"])}<div class="q-h"><span class="qn">{q["no"]:02d}</span>'
                   f'<p class="qs">{stem_html(q["stem"])}</p></div>'
                   f'<div class="qbody">{qbody(q["blocks"])}</div>{mkz("Z%d" % q["no"])}</div>')
    out.append('</div>')
    return "".join(out)


# ── 정답 및 해설 ─────────────────────────────────────────────────────
def answer_lines(a):
    parts = [p.strip() for p in re.split(r'\s{2,}(?=\([a-h]\))', a) if p.strip()]
    fmt = lambda p: RE_MARK.sub(r'<span class="m">(\1)</span>', esc(p))   # noqa: E731
    long_ = any(len(p.split()) > 3 for p in parts) or len(a) > 46
    if len(parts) > 1 and long_:
        return "<br>".join(fmt(p) for p in parts)
    return "&nbsp;&nbsp; ".join(fmt(p) for p in parts)


def render_answers(cfg, sets, sid):
    title = cfg.book.get("answers", "정답 및 해설")
    out = [f'<div class="sec band" id="{sid}">{mkz(sid)}{runners(cfg, 3, title)}'
           '<div class="ans">']
    for s in sets:
        out.append(f'<div class="ahead"><span class="rg">{s["lo"]}~{s["hi"]}</span>'
                   f'{esc(s["src"])}</div>')
        for x in s["items"]:
            exp = RE_MARK.sub(r'<span class="m">(\1)</span>', esc(x["exp"]))
            out.append(f'<div class="aitem"><div class="ahd"><div class="ano">{x["no"]:02d}</div>'
                       f'<div class="aline">{answer_lines(x["ans"])}</div></div>'
                       f'<p class="aexp"><span class="alab">해설</span>{exp}</p></div>')
        out.append(f'<p class="trans"><span class="alab">지문 해석</span>'
                   f'{esc(s["trans"])}</p>')
    out.append('</div></div>')
    return "".join(out)


# ── 조립 ──────────────────────────────────────────────────────────────
def write(cfg, d, build_dir, log=print, memos=(), fit=None, gaps=None):
    """memos = MEMO 면을 앞에 끼울 요소 id 들(§표식§ 이름)."""
    memos = set(memos or ())
    b = cfg.book
    parts = []

    def before(tag, part):
        if tag in memos:
            parts.append(memo_page(cfg, part))

    parts += [art(1), art(2), art(3), art(4), art(5)]
    parts.append(f'<div class="sec band" id="S1">{mkz("S1")}'
                 f'{runners(cfg, 1, b.get("part1", "세희T PICK 중요문장"))}'
                 f'{render_part1(cfg, d["part1"])}</div>')
    before("ART6", 1)
    parts += [art(6, left=True), art(7)]
    p2 = d["part2"]
    for k, ty in enumerate(p2["types"]):
        sid = f'T{ty["no"]}'
        if k:
            before(sid, 2)
        html_t = render_type(cfg, ty, p2["summary"] if k == 0 else None, sid)
        pid = f'P{ty["no"]}'
        if pid in memos:          # 연습 면 앞 백면(설명이 두 면을 넘친 경우)
            html_t = html_t.replace(f'<div class="prob" id="{pid}">',
                                    memo_page(cfg, 2) + f'<div class="prob" id="{pid}">', 1)
        parts.append(html_t)
    before("S2", 2)
    parts.append(f'<div class="sec band" id="S2">{mkz("S2")}'
                 f'{runners(cfg, 2, b.get("part2", "광문고 기출 서술형 실전문제"))}'
                 + "".join((memo_page(cfg, 2) if f'B{s["lo"]}' in memos else '')
                           + render_set(s, k == 0, (fit or {}).get(s["lo"], 0),
                                        (gaps or {}).get(s["lo"]))
                           for k, s in enumerate(p2["sets"]))
                 + '</div>')
    before("S3", 2)
    parts.append(render_answers(cfg, d["answers"], "S3"))
    before("ART8", 3)
    parts.append(art(8, left=True))

    doc = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           f'<title>{esc(b.get("title", ""))}</title>'
           '<link rel="stylesheet" href="theme.css">' + stage.BOOK_CSS_LINKS
           + '</head><body>' + "".join(parts) + '</body></html>')
    path = os.path.join(build_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    log(f"  HTML {len(doc):,}자 · MEMO {sorted(memos) or '없음'} · 조임 {fit or '없음'} · "
        f"여백 {len(gaps or {})}세트")
    return path
