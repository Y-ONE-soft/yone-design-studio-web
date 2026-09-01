"""data.json → HTML — 워크북 지면 조립.

지면은 두 종류다.

  **고정 시트** (간지·STEP1·STEP2) — 한 면에 지문 1~2개. InDesign 마스터의 고정
  프레임 구조를 절대배치로 옮긴 것이라 면 수가 미리 정해진다. 짝/홀 머리말이
  파이썬에서 계산된다.

  **흘림 섹션** (영작 배열·실전 문제) — 면 수가 내용에 따라 늘어난다. 머리말은
  `position: running()` + `@page :left/:right` 로 CSS 가 붙인다. 흘림 섹션은
  각 STEP 의 **맨 뒤**에만 오므로 그 뒤의 파리티는 `break-before: verso` 가 고친다.

아이콘은 전부 인라인 SVG 다 — 최신 완성본의 아이콘(O|X 버튼·체크박스·이중
화살표 답지)은 단순한 도형이라 래스터를 넣을 이유가 없다(해상도·라이선스 자유).
"""
import html
import re

# ──────────────────────────────────────────────────────── 인라인 마크업

_RE_SEL_NUM = re.compile(r"(?<![A-Za-z])\d+(\[[^\[\]]*\])")   # 1[a / b] · (1)[…]
_RE_SEL_PAREN = re.compile(r"\((\d+)\)(\s*\[[^\[\]]*\])")
_RE_SEL_BARE = re.compile(r"(\[[^\[\]]*[ⓐ/][^\[\]]*\])")
_RE_BLANK = re.compile(r"(?<![A-Za-z])(\d+)\[([^\[\]]+)\]")
_RE_ALBL = re.compile(r"^\(([A-Z])\)\s?")
_RE_OXNUM = re.compile(r"^\(?(\d+)\)?[.\s]\s*")
_RE_LEADNUM = re.compile(r"^(\d+)\.\s*")
_RE_BADGE = re.compile(r"^\{([^}]{1,6})\}\s*")
_RE_ANSLEAK = re.compile(r"\s*[①②③④⑤⑥⑦⑧⑨⑩]\s*$")
_RE_SRCCODE = re.compile(r"\s*\[\s*\d{2,6}\s*\]\s*$")   # 발문 꼬리의 원고 코드 `[52]`
_RE_LEADSEQ = re.compile(r"^\s*\d{1,4}\s*(?=[가-힣A-Z(])")  # 발문 앞 원고 일련번호
_RE_CIRCLED = re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*")
# 원고 부속물 — 번호 + 한글 구문명만 있는 줄(영어가 한 글자도 없다). 지면에 나가면
# 출처처럼 보인다. 구조로 판정: 로마자가 전혀 없고, 숫자로 시작하며, 한글이 있다.
_RE_NOISE = re.compile(r"^\s*\d+\s*[.\s][^A-Za-z]*$")


def is_manuscript_noise(t):
    t = (t or "").strip()
    if not t or len(t) > 40:
        return False
    if re.search(r"[A-Za-z]", t):
        return False
    return bool(_RE_NOISE.match(t) and re.search(r"[가-힣]", t))


def esc(t):
    return html.escape(t or "", quote=False)


# ── 글자 폭 재기 ──────────────────────────────────────────────────────
# O|X 버튼이 마지막 줄에 붙는지, 아니면 줄을 넘겨 혼자 내려가는지 **미리** 알아야
# 한다(CSS 로는 판별이 안 된다). 넘어갈 때만 오른쪽 정렬로 돌린다.
_METRICS = {}


def _metrics():
    if "w" not in _METRICS:
        import os
        from fontTools.ttLib import TTFont
        fp = os.path.expanduser("~/Library/Fonts/NotoSansCJKkr-Regular.otf")
        try:
            f = TTFont(fp, lazy=True)
            _METRICS["upm"] = f["head"].unitsPerEm
            _METRICS["cmap"] = f.getBestCmap()
            _METRICS["hmtx"] = f["hmtx"]
            _METRICS["w"] = True
        except Exception:
            _METRICS["w"] = False
    return _METRICS.get("w")


def text_mm(t, pt, track_em=-0.028):
    """글자 폭(mm) — 자간 보정 포함. 서체를 못 읽으면 None."""
    if not _metrics():
        return None
    upm, cmap, hmtx = _METRICS["upm"], _METRICS["cmap"], _METRICS["hmtx"]
    total = 0
    n = 0
    for ch in t:
        g = cmap.get(ord(ch))
        if g is None:
            g = cmap.get(ord("x"))
        if g is None:
            continue
        total += hmtx[g][0]
        n += 1
    mm = total / upm * pt * 25.4 / 72.0
    return mm + n * track_em * pt * 25.4 / 72.0


def button_drops(plain, pt, width_mm, btn_mm=24.1):
    """마지막 줄에 버튼이 못 붙는가 — 줄 용량을 재서 어림한다."""
    w = text_mm(plain, pt)
    if w is None or width_mm <= 0:
        return False
    if w <= width_mm - btn_mm:
        return False                      # 한 줄에 글 + 버튼이 다 들어간다
    import math
    lines = max(1, math.ceil(w / width_mm))
    last = w - (lines - 1) * width_mm
    return last > width_mm - btn_mm


def runs_html(block):
    """runs 를 살려 밑줄을 반영한다. runs 가 없으면 본문 그대로."""
    runs = block.get("runs") or []
    if not runs:
        return esc(block.get("text"))
    out = []
    for r in runs:
        t = esc(r.get("t"))
        out.append(f"<u>{t}</u>" if r.get("ul") else t)
    return "".join(out)


def sel_markup(s):
    """선택 괄호를 파랑 볼드로. 앞에 붙은 번호는 감춘다(실물 GREP 과 같은 동작)."""
    s = _RE_SEL_PAREN.sub(lambda m: f'<span class="sel">{m.group(2).strip()}</span>', s)
    s = _RE_SEL_NUM.sub(lambda m: f'<span class="sel">{m.group(1)}</span>', s)
    # 이미 <span class="sel"> 로 감싼 자리를 또 감싸지 않게 — 태그 밖만 본다
    out, last = [], 0
    for m in _RE_SEL_BARE.finditer(s):
        before = s[last:m.start()]
        if before.rstrip().endswith('class="sel">'):
            out.append(before + m.group(1))
        else:
            out.append(before + f'<span class="sel">{m.group(1)}</span>')
        last = m.end()
    out.append(s[last:])
    return "".join(out)


def blank_markup(s, hint=True):
    """`N[word]` → 밑줄 빈칸. 스텝에 따라 **앞 글자 힌트가 있고 없다.**

    실측(완성본):
      · 빈칸 **어휘**  — 앞 글자 하나를 남긴다 (`B____ l______ can i____`)
      · 빈칸 **어법**  — 앞 글자도 없이 통째로 가린다 (`1. This is the ____ reason.`)

    빈칸 폭은 가린 단어의 폭이 아니라 **손으로 답을 쓰는 자리**다. 실측(8pt):
    가린 글자 수 n 에 대해 `4.9mm + 2.04mm × n` — 어휘는 n=글자수-1(앞 글자를
    빼므로), 어법은 n=글자수. em 으로 옮기면 `1.74em + 0.72em × n`.

    가린 글자는 HTML 에 **넣지 않는다** — 넣으면 PDF 에서 정답이 복사된다
    (완성본도 안 뽑힌다).
    """
    def rep(m):
        w = m.group(2)
        n = min(len(w) - 1 if hint else len(w), 15)      # 상한 15칸(실물 관행)
        em = round(1.74 + 0.72 * max(n, 1), 2)
        head = f'<b>{esc(w[:1])}</b>' if hint and len(w) > 1 else ""
        if hint and len(w) < 2:
            return f'<span class="bl"><b>{esc(w)}</b></span>'
        return f'<span class="bl">{head}<i style="width:{em}em"></i></span>'
    return _RE_BLANK.sub(rep, s)


# ──────────────────────────────────────────────────────── 아이콘 (SVG)

SVG_TF = (
    '<svg class="ico tf" viewBox="0 0 210 48" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="1.5" y="1.5" width="207" height="45" rx="5" ry="5" fill="#fff" '
    'stroke="var(--rule)" stroke-width="3"/>'
    '<circle cx="72" cy="24" r="10" fill="none" stroke="var(--num-blue)" '
    'stroke-width="6"/>'
    '<rect x="103" y="13" width="4" height="22" fill="var(--rule)"/>'
    '<path d="M130 14 L150 34 M150 14 L130 34" stroke="#c0736c" '
    'stroke-width="6" stroke-linecap="round"/></svg>')


def svg_chk(step):
    col = "var(--s1)" if step == 1 else ("var(--s2)" if step == 2 else "var(--s3)")
    return (f'<svg class="ico chk" viewBox="0 0 44 44" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="44" height="44" rx="8" fill="{col}"/>'
            f'<rect x="8" y="8" width="28" height="28" rx="8" fill="#fff"/>'
            f'<path d="M14 23 L20 29 L31 14" stroke="{col}" stroke-width="3.4" '
            f'fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def svg_ansline(step, wide=False):
    """이중 화살표 + 밑줄. 실전 답 쓰는 자리."""
    col = "var(--s1)" if step == 1 else ("var(--s2)" if step == 2 else "var(--s3)")
    if wide:
        # 실측(완성본 원본 이미지 474×32 = 167.13×11.34mm): 화살표는 위 4.5mm 왼쪽,
        # 첫 괘선 y=4.8mm(굵게), 둘째 괘선 y=11.0mm(얇게). 답을 두 줄로 쓴다.
        return ('<div class="ansline wide">'
                f'<svg viewBox="0 0 480 32" xmlns="http://www.w3.org/2000/svg">'
                f'<path d="M1 1 L10 6.5 L1 12 Z M11 1 L20 6.5 L11 12 Z" fill="{col}"/>'
                f'<rect x="1" y="13" width="478" height="2" fill="var(--rule)"/>'
                f'<rect x="1" y="31" width="478" height="1" fill="var(--rule)"/>'
                '</svg></div>')
    return ('<div class="ansline">'
            f'<svg viewBox="0 0 270 12" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M1 1 L7 4.6 L1 8.2 Z M7.5 1 L13.5 4.6 L7.5 8.2 Z" fill="{col}"/>'
            f'<rect x="1" y="10" width="268" height="1.4" fill="{col}" opacity="0.55"/>'
            '</svg></div>')


ICON_SVG = {
    "TF 버튼": lambda step: SVG_TF,
    "화살표 답지": lambda step: svg_ansline(step),
    "STEP2 영작 답지": lambda step: svg_ansline(step, wide=True),
    "STEP1 문제아이콘": lambda step: svg_chk(1),
    "STEP2 문제아이콘": lambda step: svg_chk(2),
}


def icon_html(label, step):
    fn = ICON_SVG.get(label)
    return fn(step) if fn else ""


# ──────────────────────────────────────────────────────── 블록 → HTML

_BOXED = {
    "box_body": ("box-body", None),
    "q_passage": ("box-q", None),
    "arr_given": ("box-given", None),
    "arr_bottom": ("box-lined", None),
    "arr_line": ("box-arr", None),
    "write_box": ("box-write", None),
    "gram_bottom": ("box-orange", None),
}


def _p_arr(b):
    t = runs_html(b)
    m = _RE_ALBL.match(b.get("text") or "")
    if m:
        rest = t[len(m.group(0)):] if t.startswith(m.group(0)) else t
        return f'<p><span class="albl">({m.group(1)})</span> {rest}</p>'
    return f"<p>{t}</p>"


def blocks_html(blocks, step, ctx=None):
    """유닛 블록 목록 → 지면 HTML. 연속 같은 역할은 한 상자로 묶는다."""
    out = []
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        role = b["role"]
        if is_manuscript_noise(b.get("text")):
            i += 1                       # 원고 부속물(구문명 줄) — 지면에 내지 않는다
            continue

        # ── 아이콘만 있는 블록 (답지 줄) ──
        if not (b.get("text") or "").strip() and b.get("icon"):
            out.append(icon_html(b["icon"], step))
            i += 1
            continue

        # ── 상자류: 연속으로 묶는다 ──
        if role in _BOXED:
            cls = _BOXED[role][0]
            body = []
            while i < n and blocks[i]["role"] == role:
                if (blocks[i].get("text") or "").strip():
                    body.append(_p_arr(blocks[i]) if role == "arr_line"
                                else f"<p>{runs_html(blocks[i])}</p>")
                i += 1
            if role == "box_body" and ctx in ("step1_b1",):
                cls += " cream"      # B1 본문 정리만 크림 박스 (실측)
            out.append(f'<div class="{cls}">{"".join(body)}</div>')
            continue

        # ── O/X 문항 ──
        if role == "ox_item":
            t = b.get("text") or ""
            m = _RE_OXNUM.match(t)
            num = int(m.group(1)) if m else 0
            body = runs_html(b)
            if m:
                body = body[len(m.group(0)):] if body.startswith(m.group(0)) else body
            plain = re.sub(r"<[^>]+>", "", body)
            drop = button_drops(plain, 9.5, 160.8)
            out.append(f'<div class="ox{" drop" if drop else ""}">'
                       f'<span class="n">{num:02d}</span>{body}'
                       f'{icon_html(b.get("icon") or "TF 버튼", step)}</div>')
            i += 1
            continue

        # ── 어법 O/X (번호가 본문에 들어 있다) ──
        if role == "gram_ox":
            t = b.get("text") or ""
            m = _RE_LEADNUM.match(t)
            body = runs_html(b)
            num = ""
            if m:
                if body.startswith(m.group(0)):
                    body = body[len(m.group(0)):]
                num = f'<span class="n">{int(m.group(1)):02d}.</span>'
            plain = re.sub(r"<[^>]+>", "", body)
            drop = button_drops(plain, 9.0, 158.9)
            out.append(f'<div class="gox{" drop" if drop else ""}">{num}{body}'
                       f'{icon_html(b.get("icon") or "TF 버튼", step)}</div>')
            i += 1
            continue

        # ── 본문 정리 카드 (주제/제목 배지 + 뒤따르는 줄) ──
        if role in ("sum_topic", "sum_title"):
            kind = "topic" if role == "sum_topic" else "title"
            t = runs_html(b)
            m = _RE_BADGE.match(b.get("text") or "")
            badge = m.group(1) if m else ("주제" if kind == "topic" else "제목")
            if m and t.startswith(m.group(0)):
                t = t[len(m.group(0)):]
            lines = [f"<p>{t}</p>"]
            i += 1
            while i < n and blocks[i]["role"] == "sum_line":
                if (blocks[i].get("text") or "").strip():
                    lines.append(f"<p>{runs_html(blocks[i])}</p>")
                i += 1
            out.append(f'<div class="sum {kind}"><span class="badge">{esc(badge)}'
                       f'</span>{"".join(lines)}</div>')
            continue
        if role == "sum_line":            # 배지 없이 홀로 온 줄
            if (b.get("text") or "").strip():
                out.append(f'<div class="sum"><p>{runs_html(b)}</p></div>')
            i += 1
            continue

        # ── 내용 종합 문항 ──
        if role == "b2_q":
            t = b.get("text") or ""
            m = _RE_OXNUM.match(t)
            num = int(m.group(1)) if m else 1
            body = runs_html(b)
            if m:
                body = body[len(m.group(0)):] if body.startswith(m.group(0)) else body
            i += 1
            ch = []
            while i < n and blocks[i]["role"] == "b2_choice":
                if (blocks[i].get("text") or "").strip():
                    ch.append(f"<p>{runs_html(blocks[i])}</p>")
                i += 1
            chh = f'<div class="choices">{"".join(ch)}</div>' if ch else ""
            out.append(f'<div class="b2q"><span class="n">{num:02d} |</span>'
                       f'<div class="qt">{body}</div>{chh}</div>')
            continue

        # ── 하단 문제 발문 ──
        if role in ("q_prompt", "intro"):
            t = _RE_ANSLEAK.sub("", b.get("text") or "")   # 꼬리 정답 표시 제거
            t = _RE_SRCCODE.sub("", t)                     # 꼬리 원고 코드 `[049]`
            cls = "q-head" if role == "q_prompt" else "s3-intro"
            ic = icon_html(b.get("icon") or "", step) if role == "q_prompt" else ""
            out.append(f'<div class="{cls}">{ic}{esc(t)}</div>')
            i += 1
            continue

        # ── 선지 ──
        if role in ("q_choice", "s3_choice"):
            ch = []
            while i < n and blocks[i]["role"] == role:
                if (blocks[i].get("text") or "").strip():
                    ch.append(f"<p>{runs_html(blocks[i])}</p>")
                i += 1
            out.append(f'<div class="choices">{"".join(ch)}</div>')
            continue

        # ── 빈칸 (어휘·어법) ──
        if role in ("blank_vocab", "blank_gram"):
            t = b.get("text") or ""
            m = _RE_LEADNUM.match(t)
            # 어법은 앞 글자 힌트가 없다(실측) — 어휘만 첫 글자를 남긴다
            body = blank_markup(runs_html(b), hint=(role == "blank_vocab"))
            if m and body.startswith(m.group(0)):
                body = body[len(m.group(0)):]
            num = m.group(1) if m else str(_next_blank_no(out))
            i += 1
            kr = ""
            if i < n and blocks[i]["role"] == "blank_kr":
                kt = _RE_LEADNUM.sub("", blocks[i].get("text") or "")
                kr = f'<div class="blk-kr">{esc(kt)}</div>'
                i += 1
            # 본문과 해석은 **한 덩어리** — 면이 갈리면 짝이 떨어진다
            out.append(f'<div class="blk-item"><div class="blk">'
                       f'<span class="n">{esc(num)}.</span>{body}</div>{kr}</div>')
            continue
        if role == "blank_kr":
            t = _RE_LEADNUM.sub("", b.get("text") or "")
            out.append(f'<div class="blk-kr">{esc(t)}</div>')
            i += 1
            continue

        # ── 어법 선택 / 어휘 선택 ──
        if role in ("gram_sel", "vocab_sel"):
            cls = "gsel" if role == "gram_sel" else "en"
            body = sel_markup(runs_html(b))
            # ⚠ `[Check Up 1]` 같은 대괄호 **라벨**은 선택지가 아니라 지문 번호다.
            #   파랑 볼드로 물들이지 않는다(완성본은 파랑이지만 그건 고쳐야 할 쪽).
            #   선택 괄호는 `/` 나 ⓐ 가 들어 있어 sel_markup 이 이미 가려낸다.
            out.append(f'<div class="{cls}"><p>{body}</p></div>'
                       if role == "gram_sel" else f'<p class="en">{body}</p>')
            i += 1
            continue

        # ── 영작 배열 ──
        if role == "write_kr":
            kr = esc(_RE_LEADNUM.sub("", b.get("text") or ""))
            i += 1
            inner = []
            while i < n and blocks[i]["role"] in ("write_box", "basic"):
                bb = blocks[i]
                if bb["role"] == "write_box" and (bb.get("text") or "").strip():
                    inner.append(f'<div class="box-write"><p>{runs_html(bb)}</p></div>')
                elif bb.get("icon"):
                    inner.append(icon_html(bb["icon"], step))
                elif (bb.get("text") or "").strip():
                    break
                i += 1
            no = _next_write_no(out)
            out.append(f'<div class="wr"><span class="n">{no:02d}.</span>'
                       f'<div class="kr">{kr}</div>{"".join(inner)}</div>')
            continue

        # ── 남은 것: 문단 그대로 ──
        if (b.get("text") or "").strip():
            out.append(f'<p class="en">{sel_markup(runs_html(b))}</p>')
        elif b.get("icon"):
            out.append(icon_html(b["icon"], step))
        i += 1
    return "".join(out)


def _next_blank_no(out):
    return sum(1 for x in out if 'class="blk"' in x) + 1


def _next_write_no(out):
    return sum(1 for x in out if 'class="wr"' in x) + 1




# ──────────────────────────────────────────────────────── 지면 조립
#
# 머리말의 좌/우와 쪽번호를 **파이썬이 세지 않는다.** 이름 붙인 페이지(named page)
# + `position: running()` + `@page :left/:right` 로 CSS 가 정한다.
#
# 왜 그렇게 하나: 영작 배열·실전 문제는 **면 수가 내용에 따라 늘어나는 흘림**이라
# 파이썬이 셀 수 없다. 예전 파일럿처럼 고정 시트만 세면 흘림 뒤부터 짝/홀이
# 어긋나고, 어긋난 채로 뒤 스텝 전체가 뒤집힌다. 세지 않으면 어긋날 일도 없다.


def running_head(step, logo, title, tag, note=None):
    """이 스텝 구간의 머리말·꼬리말. 섹션 **선두**에 둔다.

    ⚠ 러닝 요소를 섹션 밖에 두면 무명 페이지가 생기고 named page 가 첫 면에
      안 붙는다(1차 파일럿 실증).
    """
    return (
        f'<div class="run r-hdrL">{hdr_left(step, logo, title, tag, note)}</div>'
        f'<div class="run r-hdrR">{hdr_right(step, logo)}</div>'
        f'<div class="run r-folL"><span class="folio l">'
        f'<span class="no"></span><span class="bk">STEP BY STEP</span></span></div>'
        f'<div class="run r-folR"><span class="folio r">'
        f'<span class="bk">STEP 0{step}</span><span class="no"></span></span></div>')


def hdr_left(step, logo, title, tag, note=None):
    dots = "".join(f'<i class="{"on" if k == step else ""}">{k}</i>'
                   for k in (1, 2, 3))
    return (f'<div class="hdr"><div class="bar"></div>'
            f'<div class="kicker">STEP <b>0{step}</b></div>'
            f'<div class="tag">{esc(tag)}</div>'
            f'<div class="logo">{esc(logo)}</div>'
            f'<div class="title">{esc(title)}</div>'
            f'<div class="steps">{dots}<u></u><u></u></div>'
            f'{f"<div class=\'note\'>{esc(note)}</div>" if note else ""}</div>')


def hdr_right(step, logo):
    return (f'<div class="hdr-r"><div class="biglogo">{esc(logo)}</div>'
            f'<div class="brand">STEP BY STEP</div></div>' + tabs(step))


def tabs(step):
    b = []
    for k in (1, 2, 3):
        on = " on" if k == step else ""
        lbl = f"STEP 0{k}" if k == step else f"0{k}"
        b.append(f'<b class="t{k}{on}">{lbl}</b>')
    return f'<div class="tabs">{"".join(b)}</div>'


def zone(body, pos="top", cls=""):
    top = {"top": "var(--z-top)", "bottom": "var(--z-btm)"}[pos]
    return (f'<div class="zone z-{pos} {cls}" style="top:{top}">{body}'
            f'<span class="zend"></span></div>')


def page_block(zones, cls=""):
    """고정 시트 한 면 — 판면 높이만큼의 블록. 안쪽은 절대배치."""
    return f'<div class="pg {cls}">{"".join(zones)}</div>'


# 어법 O/X 첫 면의 **템플릿 고정 예시**. 원고가 아니라 마스터에 박힌 그림이라
# 좌표를 실측해 그대로 옮긴다(완성본 p38 기준, 상자 x=22.91 y=31.41 168×23.87).
#   옅은 O|X 칸 #f9fcf3 · 빨간 동그라미/밑줄/교정 #d2232a
OX_EXAMPLE = (
    '<div class="ox-ex">'
    '<span class="s1">All experimental equipment must be handled with care.</span>'
    '<span class="s2">A warehouse is a large facility which products are storing '
    'before it is sold.</span>'
    '<span class="mk m1">O<i>|</i>X</span><span class="ring r1"></span>'
    '<span class="mk m2">O<i>|</i>X</span><span class="ring r2"></span>'
    '<span class="ul u1"></span><span class="ul u2"></span><span class="ul u3"></span>'
    '<span class="fx f1">\u21b3 where</span>'
    '<span class="fx f2">\u21b3 stored</span>'
    '<span class="fx f3">\u21b3 they are</span>'
    '</div>')


# ── 간지 ────────────────────────────────────────────────────────────

DIV_LABELS = {1: "FRAME", 2: "BUILD UP", 3: "TEST"}


def divider_section(step, line1, line2):
    dots = "".join(f'<i class="{"on" if k == step else ""}">{k}</i>'
                   for k in (1, 2, 3))
    labs = "".join(f"<s>{esc(DIV_LABELS[k])}</s>" for k in (1, 2, 3))
    front = (f'<div class="pg divider"><div class="cap"></div>'
             f'<div class="vbar"></div>'
             f'<div class="kick">STEP</div><div class="big">0{step}</div>'
             f'<div class="flow">{dots}<u></u><u></u>{labs}</div>'
             f'<div class="mark">STEP BY STEP</div></div>')
    back = (f'<div class="pg divider back"><div class="cap"></div>'
            f'<div class="l1">{esc(line1)}</div>'
            f'<div class="l2">{esc(line2)}</div>'
            f'<div class="ghost">0{step}</div>{tabs(step)}</div>')
    return (f'<section class="sec div s{step}">{front}{back}</section>')


# ── 스텝 구간 ────────────────────────────────────────────────────────

TIGHT = set()          # 측정 패스가 채운다 — 한두 줄만 넘긴 덩어리 번호
TIGHT2 = set()         # 한 단계로 안 당겨진 덩어리 (더 좁힌다)
PUSH = set()           # 통째로 다음 면으로 밀 세트 번호 (장 넘김 금지)
KEEP = set()           # 장을 넘어 갈라진 문항 번호 — 그것만 안 갈리게 묶는다
_SIDX = [0]            # 세트 일련번호 (문서 순서 — fit.turns 와 같은 셈)
_BIDX = [0]            # 문서 순서 덩어리 번호 (document() 가 0 으로 되돌린다)


def _beg():
    """덩어리 시작 표식 + 이 덩어리가 조여야 하는지."""
    i = _BIDX[0]
    _BIDX[0] += 1
    cls = " tight2" if i in TIGHT2 else (" tight" if i in TIGHT else "")
    return i, ('<span class="zbeg"></span>', cls)


def fixed_section(st, idx):
    """고정 시트 스텝 하나 → 섹션."""
    n = st["step"]
    lay = st["layout"]
    groups = st["groups"]
    side_label = st["key"] in ("step1_c2", "step2_c1")
    pages = []

    if lay == "a1":
        for k in range(0, len(groups), 2):
            zs = []
            for j, g in enumerate(groups[k:k + 2]):
                lbl = (f'<span class="pnum">{esc(g["label"])}</span>'
                       if g.get("label") else "")
                body = "".join(blocks_html(u, n, st["key"]) for u in g["units"])
                zs.append(zone(lbl + body, "top" if j == 0 else "bottom", "z-a1"))
            pages.append(page_block(zs))
    elif lay == "pair":
        for g in groups:
            us = g["units"]
            lbl = (f'<span class="pnum">{esc(g["label"])}</span>'
                   if g.get("label") else "")
            zs = [zone(lbl + blocks_html(us[0], n, st["key"]), "top")]
            if len(us) > 1:
                zs.append(zone("".join(blocks_html(u, n, st["key"]) for u in us[1:]),
                               "bottom"))
            pages.append(page_block(zs))
    else:                                            # sheet
        # ⚠ 여기는 **흘림**이다. 절대배치 칸에 가두면 넘친 내용이 잘려 사라진다
        #   (실물도 안 자른다 — 어법 선택 '본문' 20문장은 두 면에 걸친다: 실측
        #   기준 p30-31·p32-33). 지문 묶음마다 새 면에서 시작하고, 길면 이어진다.
        for gi, g in enumerate(groups):
            body = "".join(blocks_html(u, n, st["key"]) for u in g["units"])
            example = ""
            if st["key"] == "step2_b1" and gi == 0:
                # 템플릿 고정 예시 + 안내문 — **첫 면에만**, 그리고 지문 라벨보다
                # **위**에 온다(실측: 상자 y=31.41 · 라벨은 그 아래).
                note = (f'<div class="note-once">{esc(st["note"])}</div>'
                        if st.get("note") else "")
                example = note + OX_EXAMPLE
            head = ""
            if g.get("label"):
                head = (f'<div class="pn-side"><span class="pnum">'
                        f'{esc(g["label"])}</span></div>' if side_label
                        else f'<span class="pnum">{esc(g["label"])}</span>')
            btm = ""
            if g.get("attach"):
                prompt = st.get("bottom_prompt")
                ph = (f'<div class="q-head">{svg_chk(n)}{esc(prompt)}</div>'
                      if prompt else "")
                btm = (f'<div class="attach">{ph}'
                       + "".join(blocks_html(u, n, st["key"]) for u in g["attach"])
                       + "</div>")
                # ⚠ 하단 문제를 고정 자리(y=164)에 못 박지 않는다 — 하단 문제가
                #   **없는** 지문이 있고 스텝마다 지문 수도 다르다(수능만만 실측).
                #   못 박으면 없는 지문에서 빈 자리가 생긴다. 자리는 흐름이 정한다.
                body = f'<div class="topzone">{body}</div>' 
            q_idx, (mark, tight) = _beg()
            pages.append(f'<div class="grp{tight}">{mark}'
                         f'{example}{head}{body}{btm}'
                         f'<span class="bend"></span></div>')

    run = running_head(n, st["logo"], st["title"], st["tag"])
    return (f'<section class="sec fixed s{n} k-{st["key"]}" id="sec{idx}">'
            f'{run}{"".join(pages)}</section>'), len(pages)


def flow_sec(st, idx):
    """흘림 스텝(영작 배열·실전 문제) → 섹션. 면 수는 조판이 정한다."""
    n = st["step"]
    two = st["layout"] == "s3"
    body = []
    qseq = 1
    for gi, g in enumerate(st["groups"]):
        # 실물은 **지문 하나가 한 면**에서 시작한다(실측: 영작 배열 N049~N052 가
        # 각각 새 면). 흘림이라도 묶음 경계에서는 면을 끊는다.
        cls = "gstart" + (" first" if gi == 0 else "")
        body.append(f'<div class="{cls}">')
        if g.get("label"):
            body.append(f'<p class="pnum flowlbl">{esc(g["label"])}</p>')
        for blocks in g["units"]:
            if two:
                html_s, qseq2 = s3_blocks(blocks, qseq)
                qseq = qseq2 + 1
                body.append(html_s)
            else:
                body.append(blocks_html(blocks, n, st["key"]))
        body.append('</div>')
    run = running_head(n, st["logo"], st["title"], st["tag"], st.get("note"))
    cls = "twocol" if two else "onecol"
    return (f'<section class="sec flow {cls} s{n} k-{st["key"]}" id="sec{idx}">'
            f'{run}<div class="flowbody">{"".join(body)}</div></section>')


_S3_BOX = {"s3_bg": "bg3", "s3_cond": "cond3", "s3_bogi": "bogi3"}


COL_W = 81.5      # 실전 2단 한 단 폭(mm)
COL_H = 240.0     # 한 단 높이(mm) — 이보다 큰 덩어리는 묶어 봐야 면만 비운다


def _est_mm(html_or_text, pt, lh, width=COL_W, indent=0.0):
    """이 글이 차지할 높이(mm) 어림 — 덩어리를 묶을지 정하는 데만 쓴다."""
    t = re.sub(r"<[^>]+>", "", html_or_text)
    w = text_mm(t, pt)
    if w is None:
        return lh
    import math
    return max(1, math.ceil((w + indent) / max(width, 1))) * lh


def _block_h(chunks):
    return sum(chunks)


def s3_blocks(blocks, start_no=1):
    """실전(STEP3) 유닛 → 2단 흘림 HTML.

    두 겹으로 묶는다:
      **문항 덩어리**(`.q-block`) — 발문 + 지문 + 선지. 면이 갈릴 때 통째로 넘어간다.
      **세트 덩어리**(`.set-block`) — 안내문(`다음 글을 읽고…`) + 지문 + 딸린 문항들.
        '위 글'을 앞장에서 찾게 하면 안 되므로 세트도 통째로 넘긴다.

    문항 번호는 **책 전체에서 이어진다**(실물 실측: 01~159 연속). 세트가 열려도
    돌아가지 않는다.
    """
    out = []
    qn = start_no - 1
    i, n = 0, len(blocks)
    prev = None
    q_open = False
    set_open = False
    q_mark = set_mark = 0
    set_idx = q_idx = -1
    q_tight = ""
    q_h = set_h = 0.0
    head_open = False
    head_first = False

    def close_q():
        nonlocal q_open, set_h
        if q_open:
            out.append('<span class="bend"></span></div>')
            first = "first-of-set" in out[q_mark]
            cls = "q-block" + (" first-of-set" if first else "")
            # ⚠ 예전에는 한 단에 들어갈 문항을 **전부** 묶었다. 그러면 단 바닥이
            #   통째로 비어 완성본보다 단이 40% 더 나온다(실측: 완성본 40단 /
            #   이 판 57단, 완성본은 단의 22%가 선지로 시작한다 = 갈라도 된다).
            #   장(오른쪽→다음 왼쪽)을 넘어 갈라진 문항만 측정해서 묶는다.
            if q_idx in KEEP:
                cls += " keep"
            out[q_mark] = f'<div class="{cls}">'
            set_h += q_h
            q_open = False

    def close_set():
        nonlocal set_open
        if set_open:
            out.append('<span class="setend"></span></div>')
            # 한 단에 들어갈 세트만 통째로 묶는다 — 넘치면 묶어 봐야 면만 빈다
            cls = "set-block"
            if set_idx in PUSH:
                cls += " push"     # 장 넘김 금지 — 세트 통째로 다음 면에서 시작
            out[set_mark] = f'<div class="{cls}">'
            set_open = False

    while i < n:
        b = blocks[i]
        r = b["role"]

        if r in _S3_BOX:
            cls = _S3_BOX[r]
            grp = []
            while i < n and blocks[i]["role"] == r:
                if (blocks[i].get("text") or "").strip():
                    grp.append(f"<p>{runs_html(blocks[i])}</p>")
                i += 1
            out.append(f'<div class="wrap3"><div class="{cls}">'
                       f'{"".join(grp)}</div></div>')
            prev = "box"
            continue

        if r == "intro":
            close_q()
            close_set()
            t = _RE_SRCCODE.sub("", (b.get("text") or "").strip())
            out.append('<div class="set-block" data-h="0">')
            set_mark = len(out) - 1
            set_idx = _SIDX[0]
            _SIDX[0] += 1
            set_h = 0.0
            set_open = True
            # 안내문 + 지문은 **첫 문항까지** 한 덩어리로 — 세트 전체가 한 단보다
            # 길면 통째로는 못 묶으니(다단에서 break-inside 는 단도 못 넘는다),
            # 적어도 '위 글'과 첫 문항이 갈리지 않게 한다.
            out.append('<div class="set-head"><span class="setmark"></span>')
            head_open = True
            out.append(f'<p class="s3-intro">{esc(t)}</p>')
            prev = "i"
        elif r == "s3_q":
            close_q()
            if head_open:
                out.append("</div>")     # 지문 묶음을 닫고 첫 문항이 이어 붙는다
                head_open = False
                head_first = True
            qn += 1
            t = _RE_SRCCODE.sub("", _RE_LEADSEQ.sub("", runs_html(b)))
            q_idx, (mark, tight) = _beg()
            out.append(f'<div class="q-block first-of-set{tight}">'
                       if head_first else f'<div class="q-block{tight}">')
            q_mark = len(out) - 1          # ⚠ 여는 태그 자리. 표식 뒤로 잡으면
            q_tight = tight                #   close_q 가 표식을 덮어써 사라진다
            out.append(mark)
            head_first = False
            q_h = _est_mm(t, 8, 4.94, indent=9.0) + 8.93
            out.append(f'<p class="q3"><span class="qn">{qn:02d}</span>{t}</p>')
            q_open = True
            prev = "q"
        elif r == "s3_passage":
            t = runs_html(b)
            parts = re.split(r"(?=\((?:[A-C])\)\s)", t)
            if len(parts) > 2 and all(len(x) > 12 for x in parts[1:]):
                for k, seg in enumerate([x for x in parts if x.strip()]):
                    cls = "p3 seq" + (" first" if k == 0 else "")
                    out.append(f'<p class="{cls}">{seg.strip()}</p>')
            else:
                out.append(f'<p class="p3">{t}</p>')
            q_h += _est_mm(t, 8, 4.94)
            prev = "p"
        elif r == "s3_choice":
            ct = runs_html(b)
            out.append(f'<p class="ch3{" first" if prev != "ch" else ""}">{ct}</p>')
            q_h += _est_mm(ct, 8, 5.23, indent=3.6)
            prev = "ch"
        elif (b.get("text") or "").strip():
            out.append(f'<p class="{"ans3" if r in ("s3_answer", "s3_word") else "p3"}">'
                       f'{runs_html(b)}</p>')
            prev = "a"
        i += 1

    if head_open:
        out.append("</div>")
    close_q()
    close_set()
    return "".join(out), qn


# ── 문서 ────────────────────────────────────────────────────────────

FONTS = [
    ("Noto Sans CJK KR", "NotoSansCJKkr-Regular.otf", 400),
    ("Noto Sans CJK KR", "NotoSansCJKkr-Medium.otf", 500),
    ("Noto Sans CJK KR", "NotoSansCJKkr-Bold.otf", 700),
    ("Gmarket Sans", "GmarketSansMedium.otf", 500),
    ("Gmarket Sans", "GmarketSansBold.otf", 700),
    ("Elice DX Neolli", "EliceDXNeolliOTF-Medium.otf", 500),
    ("Elice DX Neolli", "EliceDXNeolliOTF-Bold.otf", 700),
    ("Elice Baeum", "EliceDigitalBaeumOTF_Regular.otf", 400),
    ("Elice Baeum", "EliceDigitalBaeumOTF_Bold.otf", 700),
    ("Yeongdo", "YeongdoOTF.otf", 400),
    ("Montserrat", "Montserrat-Medium.otf", 500),
    ("Montserrat", "Montserrat-Bold.otf", 700),
    ("LotteMartDream", "12롯데마트드림Bold.ttf", 700),
    ("TTMamablock", "TTMamablockB.ttf", 700),
    ("Cafe24Supermagic", "Cafe24Supermagic-Bold-v1.0.otf", 700),
]


def font_css():
    return "\n".join(
        f'@font-face{{font-family:"{fam}";src:url("fonts/{f}");'
        f'font-weight:{w};font-display:block;}}'
        for fam, f, w in FONTS)


def document(data, title="워크북"):
    _BIDX[0] = 0
    parts = ['<section class="sec blank"><div class="pg"></div></section>']
    rows = []
    seen = set()
    idx = 0
    book = data.get("book") or {}
    for st in data["steps"]:
        n = st["step"]
        if n not in seen:
            seen.add(n)
            parts.append(divider_section(n, book.get("line1", ""),
                                         book.get("line2", "")))
            rows.append((f"STEP0{n} 간지", 2))
        idx += 1
        if st["layout"] in ("flow", "s3"):
            parts.append(flow_sec(st, idx))
            rows.append((st["key"], "흘림"))
        else:
            html_s, npages = fixed_section(st, idx)
            parts.append(html_s)
            rows.append((st["key"], npages))
    doc = ("<!DOCTYPE html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
           f"<title>{esc(title)}</title>\n<style>\n{font_css()}\n</style>\n"
           "<link rel=\"stylesheet\" href=\"theme.css\">\n</head>\n<body>\n"
           + "\n".join(parts) + "\n</body>\n</html>\n")
    return doc, rows


def write(cfg, data, build_dir, log=print):
    _SIDX[0] = 0        # 세트 번호는 **문서 전체** 순서다 (측정 패스와 맞춘다)
    import os
    text, rows = document(data, (cfg.book or {}).get("title") or "워크북")
    os.makedirs(build_dir, exist_ok=True)
    p = os.path.join(build_dir, "index.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    for k, v in rows:
        log(f"    {k:<14} {v}면" if isinstance(v, int) else f"    {k:<14} {v}")
    return p
