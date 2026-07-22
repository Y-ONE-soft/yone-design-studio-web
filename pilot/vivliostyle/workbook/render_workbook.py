#!/usr/bin/env python3
"""W43 Vivliostyle 2차 파일럿 — 워크북(wb-flows-v1) 렌더 플랜 → 대표 구간 HTML.

기존 파이프라인 산출물(jobs/<id>/render_plan.json)을 소비만 한다(기존 코드 무수정).
대표 구간: 간지(앞/뒤) + 각 스텝 첫 유닛(지문 20 사이클) + STEP3 실전 문제 전체
(요약문 배경·조건 박스·보기 박스 포함) — 디자인 요소 유형 전수 커버.

- 간지·STEP1·STEP2 구간: InDesign 마스터의 고정 프레임 구조를 절대배치 시트로 1:1 재현
- STEP3 구간: CSS Paged Media 2단 자동 흘림 (러닝 헤더/푸터 + counter-reset)

사용:
    python3 pilot/vivliostyle/workbook/render_workbook.py \
        data_corpus/round18/supp_0a5da924/job/render_plan.json -o out/workbook.html
"""
import argparse
import html
import json
import os
import re

# ---------------------------------------------------------------- inline utils

_RE_A1_CHOICE = re.compile(r"\(\d+\)(\[[^\]]*\])")     # (1)[ ⓐ x / ⓑ y ] → 번호 숨김
_RE_S2_CHOICE = re.compile(r"\d+(\[[^\]]*\])")          # 1[a / b] → 번호 숨김
_RE_BLANK = re.compile(r"\d+\[([^\]]+)\]")              # 빈칸 어휘 N[word]
_RE_OX_N = re.compile(r"^\((\d+)\)\s*")
_RE_ALBL = re.compile(r"^\(([A-G])\)\s?")
_RE_UNDERSCORES = re.compile(r"_{3,}")


def esc(t):
    return html.escape(t, quote=False)


def runs_html(para, cls_map=None):
    """runs → 밑줄 반영 인라인 HTML (runs 없으면 본문 그대로)."""
    runs = para.get("runs") or []
    if not runs:
        return esc(para["t"])
    out = []
    for r in runs:
        t = esc(r["t"])
        out.append(f"<u>{t}</u>" if r.get("ul") else t)
    return "".join(out)


def sel_markup(text_html, numbered):
    """[ ... / ... ] 선택 괄호를 파란 볼드로. numbered=True면 앞 번호 제거."""
    rx = _RE_A1_CHOICE if numbered else _RE_S2_CHOICE
    text_html = rx.sub(lambda m: f'<span class="sel">{m.group(1)}</span>', text_html)
    # 번호 없는 잔여 [ ⓐ ... ] 도 처리 (실물 GREP과 동일하게 ⓐ 포함 괄호만)
    text_html = re.sub(r"(?<!>)(\[[^\[\]]*ⓐ[^\[\]]*\])",
                       r'<span class="sel">\1</span>', text_html)
    return text_html


def blank_markup(text_html):
    """빈칸 어휘 N[word] → 첫 글자(핑크 볼드) + 단어 길이 비례 밑줄."""
    def rep(m):
        w = m.group(1)
        first, hidden = w[:1], max(len(w) - 1, 3)
        width = round(2.4 + hidden * 2.95, 1)
        return (f'<span class="bl"><b>{esc(first)}</b>'
                f'<span class="ln" style="width:{width}mm"></span></span>')
    return _RE_BLANK.sub(rep, text_html)


CHK_SVG = ('<svg class="chk" viewBox="0 0 41 41" xmlns="http://www.w3.org/2000/svg">'
           '<rect x="1" y="1" width="39" height="39" rx="8" fill="{out}"/>'
           '<rect x="5" y="5" width="31" height="31" rx="5" fill="{inn}"/>'
           '<path d="M12 21 L18 27 L29 14" stroke="{out}" stroke-width="4.5" '
           'fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def chk(step):
    if step == 1:
        return CHK_SVG.format(out="#a3bbda", inn="#f3f0e6")
    return CHK_SVG.format(out="#cb94af", inn="#ede8de")


# ---------------------------------------------------------------- 공통 조각

def header(step, tag, logo, title, title_dx=None):
    dx = f' style="--title-dx:{title_dx}"' if title_dx else ""
    return (f'<div class="band"></div>'
            f'<div class="ribbon">STEP <b>0{step}</b><span class="tag">{tag}</span></div>'
            f'<div class="steplogo">{logo}</div>'
            f'<div class="steptitle"{dx}>{esc(title)}</div>')


def floral(step):
    img = "floral_step3.png" if step == 3 else "floral_step12.png"
    return f'<img class="floral" src="assets/{img}">'


def folio_left(no):
    return (f'<div class="folio-l"><span class="no">{no}</span>'
            f'<span class="bk">STEP BY STEP</span></div>')


def folio_right(no, step):
    return (f'<div class="folio-r"><span class="bk">STEP0{step}</span>'
            f'<span class="no">{no}</span></div>')


def paras(unit):
    return unit["paras"] if isinstance(unit, dict) else unit


def label_of(unit):
    ps = paras(unit)
    if ps and ps[0]["s"] == "$BASIC" and re.match(r"^[\[{].+[\]}]$", ps[0]["t"]):
        return ps[0]["t"].strip("[]{}"), ps[1:]
    return None, ps


# ---------------------------------------------------------------- 시트 빌더

def sheet_divider_front():
    return ('<div class="sheet divider">'
            '<div class="dotline"></div>'
            '<div class="dv-title">STEP. 01</div>'
            '</div>')


def sheet_divider_back(menu):
    mi = "".join(f'<div class="mi"><span class="tok">{esc(t)}</span>'
                 f'<span class="lbl">{esc(l)}</span></div>' for t, l in menu)
    return ('<div class="sheet divider">'
            '<div class="strip"><img src="assets/divider_strip.png"></div>'
            '<div class="dv-back-title">부교재</div>'
            '<div class="dv-dot2"></div>'
            f'<div class="menu">{mi}</div>'
            '<div class="brand"><div class="b1">STEP BY STEP</div>'
            '<div class="b2">스텝바이스텝 워크북</div></div>'
            '</div>')


def sheet_a1(units, folio, side, title):
    """어휘 선택: 상(30mm)/하(154mm) 고정 프레임에 유닛 2개."""
    frames = []
    for i, u in enumerate(units[:2]):
        label, ps = label_of(u)
        body = "".join(
            f'<p class="en">{sel_markup(runs_html(p), numbered=True)}</p>'
            for p in ps if p["t"].strip())
        top = "30.6mm" if i == 0 else "154.6mm"
        frames.append(f'<div class="a1-frame" style="top:{top}">'
                      f'<span class="pnum">{esc(label or "")}</span>{body}</div>')
    hdr = (header(1, "FRAME", "A1", title, "10.8mm") if side == "L"
           else '<div class="band"></div>' + floral(1))
    foot = folio_left(folio) if side == "L" else folio_right(folio, 1)
    left = "23mm" if side == "L" else "25mm"
    return (f'<div class="sheet s1">{hdr}'
            f'<div class="content" style="left:{left}">{"".join(frames)}</div>'
            f'{foot}</div>')


def sheet_a2(unit, folio):
    label, ps = label_of(unit)
    box, items = [], []
    n = 0
    for p in ps:
        if not p["t"].strip():
            continue
        if p["s"].endswith("본문 박스"):
            box.append(f'<p>{runs_html(p)}</p>')
        else:  # OX문제
            n += 1
            t = _RE_OX_N.sub("", p["t"])
            items.append(f'<div class="ox-item"><span class="n">{n:02d}</span>'
                         f'{esc(t)}<img class="tf" src="assets/tf_button.png"></div>')
    return (f'<div class="sheet s1">{header(1, "FRAME", "A2", "본문 O/X", "11.1mm")}'
            f'<div class="content" style="top:33.4mm">'
            f'<span class="pnum">{esc(label or "")}</span>'
            f'<div class="a2-box">{"".join(box)}</div>{"".join(items)}</div>'
            f'{folio_left(folio)}</div>')


def sheet_c1(unit_top, unit_btm, folio):
    label, ps = label_of(unit_top)
    lines = []
    for p in ps:
        if not p["t"].strip():
            continue
        m = _RE_ALBL.match(p["t"])
        if m:
            rest = p["t"][m.end():]
            lines.append(f'<p><span class="albl">({m.group(1)})</span> {esc(rest)}</p>')
        else:
            lines.append(f'<p>{runs_html(p)}</p>')
    top_html = (f'<span class="pnum">{esc(label or "")}</span>'
                f'<div class="c1-box">{"".join(lines)}</div>'
                f'<img class="ans-arrow" src="assets/arrow_answer.png">')

    ps2 = paras(unit_btm)
    btm = []
    for p in ps2:
        if not p["t"].strip():
            continue
        if p.get("icon"):
            btm.append(f'<div class="q-head">{chk(1)}{esc(p["t"])}</div>')
        elif p["s"].endswith("하단"):
            btm.append(f'<div class="given-box"><p>{esc(p["t"].strip())}</p></div>')
        else:  # 하단 지문
            btm.append(f'<div class="lined-box"><p>{esc(p["t"])}</p></div>')
    return (f'<div class="sheet s1">{header(1, "FRAME", "C1", "문장 배열", "10.5mm")}'
            f'<div class="content" style="top:36mm">{top_html}</div>'
            f'<div class="bottom-q" style="left:23mm;top:156.4mm">{"".join(btm)}</div>'
            f'{folio_left(folio)}</div>')


def sheet_c2(unit, folio, pnum_label):
    ps = paras(unit)
    items, n = [], 0
    for p in ps:
        if not p["t"].strip():
            continue
        if p["s"].endswith("한글"):
            items.append(f'<p class="c2-kr">{esc(p["t"])}</p>')
        else:
            n += 1
            body = blank_markup(esc(p["t"]))
            items.append(f'<div class="c2-item"><span class="n">{n}.</span>'
                         f'{body}</div>')
    return (f'<div class="sheet s1">{header(1, "FRAME", "C2", "빈칸 어휘", "12.0mm")}'
            f'<div class="content" style="left:26mm;width:172mm;top:29.7mm">'
            f'<span class="pnum c2-pnum">{esc(pnum_label)}</span>{"".join(items)}</div>'
            f'{folio_left(folio)}</div>')


def sheet_s2a1(unit_top, unit_btm, folio, bottom_prompt):
    label, ps = label_of(unit_top)
    if label is None and ps and re.match(r"^\{.+\}$", ps[0]["t"]):
        label, ps = ps[0]["t"].strip("{}"), ps[1:]
    body = "".join(f'<p class="en">{sel_markup(runs_html(p), numbered=False)}</p>'
                   for p in ps if p["t"].strip())
    ps2 = paras(unit_btm)
    box = "".join(f'<p>{runs_html(p)}</p>' for p in ps2 if p["t"].strip())
    return (f'<div class="sheet s2">{header(2, "BUILD UP", "A1", "어법 선택", "10.8mm")}'
            f'<div class="content s2a1-top" style="top:32.5mm">'
            f'<span class="pnum">{esc(label or "")}</span>{body}</div>'
            f'<div class="bottom-q" style="left:23mm;top:156.5mm">'
            f'<div class="q-head">{chk(2)}{esc(bottom_prompt)}</div>'
            f'<div class="orange-box">{box}</div></div>'
            f'{folio_left(folio)}</div>')


def sheet_s2c2(unit, folio):
    label, ps = label_of(unit)
    items, n, cur = [], 0, []
    for p in ps:
        if p.get("icon"):
            cur.append('<img class="ans-writing wr-ans" src="assets/writing_answer.png">')
            items.append(f'<div class="wr-item">{"".join(cur)}</div>')
            cur = []
        elif not p["t"].strip():
            continue
        elif p["s"].endswith("보기"):
            cur.append(f'<div class="wr-box"><p>{esc(p["t"])}</p></div>')
        else:  # 번호(한글 지시문)
            n += 1
            cur.insert(0, f'<span class="n">{n:02d}.</span>')
            cur.append(f'<div class="kr">{esc(p["t"])}</div>')
            # 순서 조정: 번호, 한글, (이후 보기/답지)
            cur = [cur[0], cur[-1]] + cur[1:-1]
    if cur:
        items.append(f'<div class="wr-item">{"".join(cur)}</div>')
    return (f'<div class="sheet s2">{header(2, "BUILD UP", "C2", "영작 배열", "12.0mm")}'
            f'<div class="content" style="top:35.5mm">'
            f'<span class="pnum" style="display:block;margin-bottom:4.6mm">'
            f'{esc(label or "")}</span>{"".join(items)}</div>'
            f'{folio_left(folio)}</div>')


# ---------------------------------------------------------------- STEP3 흘림

S3_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
S3_P = "STEP 03 > 실전 문제 지문 올림포스_"
S3_C = "STEP 03 > S_선지 올림포스"
S3_BG = "STEP 03 > 배경 올림포스"
S3_COND = "STEP 03 > 조건 올림포스"
S3_BOGI = "STEP 03 > 보기 올림포스"


def s3_flow(unit):
    """STEP3 유닛 → 2단 흘림 HTML. 배경/조건/보기 연속 단락은 한 박스로 묶음."""
    ps = [p for p in paras(unit)]
    out, qn, i = [], 0, 0
    prev_cls = None
    while i < len(ps):
        p = ps[i]
        s = p["s"]
        t = p["t"]
        if s in (S3_BG, S3_COND, S3_BOGI):
            cls = {"STEP 03 > 배경 올림포스": "bg-box3",
                   "STEP 03 > 조건 올림포스": "cond-box3",
                   "STEP 03 > 보기 올림포스": "bogi-box3"}[s]
            group = []
            while i < len(ps) and ps[i]["s"] == s:
                gt = runs_html(ps[i])
                tcls = ' class="t"' if ps[i]["t"].startswith("<") and cls == "cond-box3" else ""
                if ps[i]["t"].strip():
                    group.append(f"<p{tcls}>{gt}</p>")
                i += 1
            wrap = cls.replace("box", "wrap")
            out.append(f'<div class="{wrap}"><div class="{cls}">'
                       f'{"".join(group)}</div></div>')
            prev_cls = cls
            continue
        if s == S3_Q:
            qn += 1
            first = " qfirst" if qn == 1 else ""
            out.append(f'<p class="q3{first}"><span class="qn">{qn:02d}</span>'
                       f'{runs_html(p)}</p>')
            prev_cls = "q"
        elif s == S3_P:
            out.append(f'<p class="p3">{runs_html(p)}</p>')
            prev_cls = "p"
        elif s == S3_C:
            first = " first" if prev_cls != "ch" else ""
            tab = " tabbed" if "\t" in t else ""
            out.append(f'<p class="ch3{first}{tab}">{runs_html(p)}</p>')
            prev_cls = "ch"
        i += 1
    return "".join(out)


def section_s3(unit):
    hdr = (f'<div class="s3-hdr"><div class="ribbon">STEP <b>03</b>'
           f'<span class="tag">TEST</span></div>'
           f'<div class="steplogo">S</div>'
           f'<div class="steptitle" style="--title-dx:6.4mm">실전 문제</div></div>')
    folios = ('<div class="s3-folio-l"><span class="no"></span>'
              '<span class="bk">STEP BY STEP</span></div>'
              '<div class="s3-folio-r"><span class="bk">STEP03</span>'
              '<span class="no"></span></div>')
    # 러닝 요소는 섹션 안 선두에 둔다 (섹션 밖이면 무명 페이지가 생김 — 1차 빌드 실증)
    return f'<section class="s3flow">{hdr}{folios}{s3_flow(unit)}</section>'


# ---------------------------------------------------------------- 문서 조립

MENU_S1 = [("A1", "어휘 선택"), ("A2", "본문 O/X"), ("B1", "본문 정리"),
           ("B2", "내용 종합"), ("C1", "문장 배열"), ("C2", "빈칸 어휘")]

S2A1_PROMPT = "다음 밑줄 친 부분 중 어법상 틀린 것은?"  # C-마스터 하단 프레임 고정 발문


def build_html(plan):
    flows = {f["step"]: f for f in plan["flows"]}
    u = lambda step, i=0: flows[step]["units"][i]

    label_c2, _ = label_of(u("step1_a1"))  # 빈칸 어휘 사이드 번호 = 지문 20

    sheets = [
        sheet_divider_front(),
        sheet_divider_back(MENU_S1),
        sheet_a1([u("step1_a1", 0), u("step1_a1", 1)], 4, "L", "어휘 선택 1"),
        sheet_a1([u("step1_a1", 2), u("step1_a1", 3)], 5, "R", "어휘 선택 1"),
        sheet_a2(u("step1_a2"), 22),
        sheet_c1(u("step1_c1", 0), u("step1_c1", 1), 76),
        sheet_c2(u("step1_c2"), 94, label_c2 or "20"),
        sheet_s2a1(u("step2_a1"), u("step2_a1_btm"), 114, S2A1_PROMPT),
        sheet_s2c2(u("step2_c2"), 168),
    ]
    body = "\n".join(sheets) + "\n" + section_s3(u("step3"))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>STEP BY STEP 워크북 — Vivliostyle 2차 파일럿</title>
<link rel="stylesheet" href="workbook_theme.css">
</head>
<body>
{body}
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", help="render_plan.json 경로 (wb-flows-v1)")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    assert plan.get("format") == "wb-flows-v1", plan.get("format")
    text = build_html(plan)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
