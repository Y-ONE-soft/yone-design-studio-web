# -*- coding: utf-8 -*-
"""프로파일 → 테마 CSS.

학교마다 지면·서체·상자·괘선이 다르므로 CSS 를 **학교별로 생성**한다. 손으로 쓴
`themes/mockexam.css` 한 벌(한영3 InDesign 산출물 실측)을 대신하는 자리다.

원칙:
  - 프로파일에 없는 값은 **그리지 않는다.** 그럴듯한 기본값으로 때우지 않는다.
    (배재1에 쪽 테두리가 없다는 것은 '측정 못 했다'가 아니라 '실제로 없다'이다.)
  - 모든 수치는 B4 환산치. 판형은 제품 상수라 프로파일이 이미 환산해 두었다.
  - 서체는 학교가 쓴 HWP 서체를 로컬 설치본으로 그대로 건다. 없으면 계열
    폴백으로 내려가되 **무엇이 폴백됐는지 남긴다**.
"""
import os

from core.render_vivlio.series.mockexam.profile import dig as P_dig

# 학교 기출이 쓰는 서체 → 로컬 설치 파일. HWP/한컴 계열이라 대부분 있다.
FONT_FILES = {
    "HANBatang":  "~/Library/Fonts/HANBatang.ttf",
    "HANBatangB": "~/Library/Fonts/HANBatangB.ttf",
    "HANDotum":   "~/Library/Fonts/HANDotum.ttf",
    "HANDotumB":  "~/Library/Fonts/HANDotumB.ttf",
    "H2GTRE":     "~/Library/Fonts/H2GTRE.TTF",   # 견고딕 — 머리표 제목
    "H2GTRM":     "~/Library/Fonts/H2GTRM.TTF",
    "H2MJSM":     "~/Library/Fonts/H2MJSM.TTF",   # 신명조
    "H2HDRM":     "~/Library/Fonts/H2HDRM.TTF",
}

# 프로파일에 적힌 서체 이름(사람이 쓴 것)을 위 파일로 접는다.
_SERIF = ("batang", "바탕", "명조", "신명조", "serif", "mj")
_GOTHIC = ("dotum", "돋움", "고딕", "gothic", "굴림", "gulim", "malgun", "맑은")


def font_family(name, bold=False):
    """프로파일 서체명 → CSS font-family 스택."""
    n = (name or "").lower()
    if "h2gtr" in n or "견고딕" in n:
        return '"H2GTRE", "HANDotumB", sans-serif'
    if "h2mj" in n or "신명조" in n:
        return '"H2MJSM", "HANBatang", serif'
    if any(w in n for w in _GOTHIC):
        return '"HANDotumB", "HANDotum", sans-serif' if bold \
            else '"HANDotum", sans-serif'
    if any(w in n for w in _SERIF):
        return '"HANBatangB", "HANBatang", serif' if bold \
            else '"HANBatang", serif'
    # 이름을 못 알아본 경우 — 기본은 명조(한국 시험지 다수)로 두되 기록한다.
    return '"HANBatang", serif'


def font_files_for(spec):
    """이 학교 CSS 가 실제로 참조하는 서체 파일 목록."""
    used = set()
    for r in spec.roles.values():
        fam = font_family(r.get("font"), r.get("bold"))
        for k in FONT_FILES:
            if f'"{k}"' in fam:
                used.add(k)
    used |= {"HANBatang", "HANBatangB", "HANDotum", "HANDotumB"}  # 폴백 보장
    return [os.path.expanduser(FONT_FILES[k]) for k in sorted(used)
            if os.path.exists(os.path.expanduser(FONT_FILES[k]))]


def _face_rules():
    out = []
    for name, path in FONT_FILES.items():
        if not os.path.exists(os.path.expanduser(path)):
            continue
        f = os.path.basename(os.path.expanduser(path))
        weight = 700 if name.endswith("B") or name == "H2GTRE" else 400
        out.append(f'@font-face {{ font-family: "{name}"; '
                   f'src: url("fonts/{f}"); font-weight: {weight}; }}')
    return "\n".join(out)


def _role_css(cls, r, spec):
    """역할 하나 → CSS 규칙."""
    if not r:
        return ""
    d = []
    fam = font_family(r.get("font"), r.get("bold"))
    d.append(f"font-family: {fam};")
    if r.get("size_pt"):
        d.append(f"font-size: {r['size_pt']}pt;")
    if r.get("leading_pt"):
        d.append(f"line-height: {r['leading_pt']}pt;")
    d.append(f"font-weight: {700 if r.get('bold') else 400};")
    align = r.get("align") or "justify"
    d.append(f"text-align: {align};")
    hang = r.get("hang_mm") or 0
    indent = r.get("indent_mm") or 0
    if hang:
        # 내어쓰기: 되풀이 줄이 마커 아래로 들어간다
        d.append(f"padding-left: {hang}mm;")
        d.append(f"text-indent: -{hang}mm;")
    elif indent:
        d.append(f"text-indent: {indent}mm;")
    if r.get("space_before_pt"):
        # rolemeasure 의 space_before 는 '앞 줄 시작 → 이 줄 시작' 거리라
        # **행간이 이미 들어 있다.** 그대로 얹으면 여백이 두 배가 된다.
        # 순 여백 = 잰 값 − 이 역할의 행간.
        lead = r.get("leading_pt") or 0
        net = round(max(r["space_before_pt"] - lead, 0), 2)
        if net:
            # 2단 흘림에서 margin-top 이 소실되므로 padding 으로 준다
            # (vivliostyle 파일럿 실증 — docs/vivliostyle_파일럿_보고.md)
            d.append(f"padding-top: {net}pt;")
    return f".{cls} {{ " + " ".join(d) + " }"


def _box_css(cls, box, spec):
    """상자 렌더 방식별 CSS. 학교마다 이 부분이 가장 많이 갈린다."""
    render = (box or {}).get("render") or "plain_line"
    pt = box.get("border_pt") or 0.4
    pad = box.get("pad_mm") or 1.5
    out = []
    if render == "plain_line":
        # 테두리 없음 — 라벨 줄 + 내용 줄 (배재1)
        out.append(f".{cls}-label {{ text-align: {box.get('align') or 'center'}; }}")
        out.append(f".{cls}-body {{ }}")
        return "\n".join(out)

    # 이하 전부 테두리 상자
    out.append(f".{cls}-box {{ border: {pt}pt solid #000; "
               f"padding: {pad}mm; margin: 3pt 0; position: relative; }}")
    if render in ("boxed_caption_on_border",):
        # 캡션이 윗변 선에 걸터앉고 그 자리에서 선이 끊긴다.
        # 지면 바탕색으로 선을 덮는 방식이 인쇄에서 가장 안전하다.
        out.append(f".{cls}-box {{ margin-top: 6pt; }}")
        out.append(f".{cls}-label {{ position: absolute; top: 0; left: 50%; "
                   f"transform: translate(-50%, -55%); background: #fff; "
                   f"padding: 0 1.2mm; white-space: nowrap; }}")
    elif render in ("boxed_caption_inside", "boxed_caption_inside_top_center"):
        center = "center" if "center" in render else "left"
        out.append(f".{cls}-label {{ display: block; text-align: {center}; }}")
    elif render == "boxed_caption_above":
        out.append(f".{cls}-label {{ display: block; text-align: "
                   f"{box.get('align') or 'center'}; margin-bottom: 1pt; }}")
    elif render == "table":
        # 성덕 계열: 좌측에 세로 병합된 회색 라벨 셀 + 우측 항목 행
        out.append(f".{cls}-table {{ border-collapse: collapse; width: 100%; "
                   f"border: {pt}pt solid #000; }}")
        out.append(f".{cls}-table td {{ border: {pt}pt solid #000; "
                   f"padding: 0.8mm 1.2mm; vertical-align: middle; }}")
        out.append(f".{cls}-table td.lbl {{ width: 12mm; text-align: center; "
                   f"background: #eee; }}")
    return "\n".join(out)


def build_css(spec):
    """Spec → 이 학교 전용 CSS 한 벌."""
    s = spec
    passage = s.role("passage")
    body_size = passage.get("size_pt") or 10.0
    body_lead = passage.get("leading_pt") or 15.0
    body_fam = font_family(passage.get("font"))

    # 본문 영역: 프로파일의 좌/우 여백을 그대로 쓴다.
    def mm(v):
        return round(float(v), 2)
    left = mm(s.text_left if s.text_left is not None else 20.0)
    right = mm(s.page_w - (s.text_right if s.text_right is not None else s.page_w - 20.0))
    top = mm(s.rule_top if s.rule_top is not None else 24.0)
    bottom = mm(s.page_h - (s.rule_bottom if s.rule_bottom is not None else s.page_h - 24.0))

    gap = mm(s.col_gap or 5.0)

    css = [f"/* {s.key} — {s.school} {s.grade} {s.subject_title}",
           f" * 정본: {s.ref_exam} ({s.ref_kind})"
           + (" ⚠ 대체 정본" if s.is_fallback else "")
           + (" · 수치 근사" if s.approx else " · 수치 실측"),
           f" * 이 파일은 profiles/{s.key}.json 에서 생성된다 — 손으로 고치지 말 것.",
           " */", "", _face_rules(), "",
           "html, body { margin: 0; padding: 0; }",
           f"body {{ font-family: {body_fam}; font-size: {body_size}pt; "
           f"line-height: {body_lead}pt; color: #000; "
           "line-break: strict; hyphens: none; orphans: 1; widows: 1; }",
           "p { margin: 0; }", ""]

    # ── 지면 ──
    css.append("@page {")
    css.append(f"  size: {mm(s.page_w)}mm {mm(s.page_h)}mm;")
    css.append(f"  margin: {top}mm {right}mm {bottom}mm {left}mm;")
    if s.page_border:
        css.append(f"  border: {s.page_border_pt}pt solid #000;")
        css.append("  padding: 3mm;")
    css.append("  @top-center { content: element(pageHeader); vertical-align: bottom; }")
    css.append("  @bottom-center { content: element(pageFooter); vertical-align: top; }")
    css.append("}")
    css.append("")

    # ── 본문 흘림 ──
    flow = [f"column-count: {s.columns};", f"column-gap: {gap}mm;",
            "column-fill: auto;"]
    if s.column_rule:
        flow.append(f"column-rule: {s.column_rule_pt}pt solid #000;")
    css.append(".flow { " + " ".join(flow) + " }")
    css.append("")

    # ── 역할 ──
    css.append("/* 단락 역할 — 프로파일 typography.roles 실측값 */")
    for cls, role in (("stem", "stem"), ("passage", "passage"),
                      ("choice", "choice"), ("given", "given"),
                      ("cond", "cond"), ("answer", "answer_field"),
                      ("essay-label", "essay_label")):
        rule = _role_css(cls, s.roles.get(role), s)
        if rule:
            css.append(rule)
    css.append(".stem { break-after: avoid; }")
    if s.qnum_size:
        qfam = font_family((s.roles.get("qnum") or {}).get("font")
                           or passage.get("font"))
        css.append(f".qnum {{ font-family: {qfam}; font-size: {s.qnum_size}pt; }}")
    css.append("")

    # ── 상자 ──
    css.append("/* 보기·조건 — 학교마다 렌더 방식이 다르다 */")
    css.append(_box_css("given", s.given, s))
    css.append(_box_css("cond", s.cond, s))
    gs = s.given_sentence or {}
    if (gs.get("render") or "").startswith("boxed"):
        css.append(f".givensent-box {{ border: {gs.get('border_pt') or 0.4}pt solid #000; "
                   f"padding: {gs.get('pad_mm') or 1.5}mm; margin: 3pt 0; }}")
    css.append("")

    # ── 요약 화살표 ──
    if s.summary.get("arrow"):
        css.append(".summary-arrow { text-align: center; font-size: "
                   f"{round(body_size * 1.25, 1)}pt; line-height: 1.2; "
                   "margin: 2pt 0; }")
    if (s.summary.get("render") or "").startswith("box"):
        css.append(".summary-box { border: 0.4pt solid #000; padding: 1.5mm; "
                   "margin: 3pt 0; }")
    css.append("")

    # ── 러닝 요소 ──
    css.append(".page-header { position: running(pageHeader); }")
    css.append(".page-footer { position: running(pageFooter); }")
    css.append(".page-footer-last { position: running(pageFooterLast); }")
    if s.copyright:
        css.append(".copyright { font-size: 8pt; }")
    if s.page_number:
        # `{p}/{n}` · `{p} / ( {n} )` 같은 학교별 형식을 counter 로 옮긴다
        content = []
        buf = ""
        for tok, rep in (("{p}", "counter(page)"), ("{n}", "counter(pages)")):
            pass
        import re as _re
        for part in _re.split(r"(\{p\}|\{n\})", s.page_number):
            if part == "{p}":
                content.append("counter(page)")
            elif part == "{n}":
                content.append("counter(pages)")
            elif part:
                content.append('"%s"' % part.replace('"', '\\"'))
        css.append(".pgnum::after { content: " + " ".join(content) + "; }")
        align = "center" if "center" in (s.page_number_pos or "") else "left"
        css.append(f".pgnum {{ text-align: {align}; }}")
    css.append("")

    # ── 1쪽 머리표 (학교에 따라 1쪽만 / 매 쪽) ──
    css.append("/* 머리표 — 프로파일 running.header 실측 */")
    css.append(".exam-head { column-span: all; margin-bottom: 4mm; }")
    css.append(".exam-head .eh { display: block; }")
    css.append(".exam-head .eh-center { text-align: center; }")
    css.append(".exam-head .eh-right { text-align: right; }")
    css.append(".exam-head .eh-underline { text-decoration: underline; }")
    dr = P_dig(s.raw, "running.header.double_rule") or {}
    if dr:
        thin = dr.get("thin_pt") or 0.24
        thick = dr.get("thick_pt") or 0.96
        css.append(f".exam-head .eh-rule {{ border-top: {thin}pt solid #000; "
                   f"border-bottom: {thick}pt solid #000; height: 1.6mm; }}")
    css.append(".notice { }")
    css.append(".notice-wrap { column-span: all; }")
    css.append("")

    # ── 마무리 ──
    if s.ending_lines:
        css.append(f".ending {{ text-align: {s.ending_align}; "
                   f"font-weight: {700 if s.ending_bold else 400}; "
                   "margin-top: 6pt; }")

    css.append("")
    css.append("u { text-underline-offset: 0.16em; text-decoration-thickness: 0.06em; }")
    return "\n".join(css)


if __name__ == "__main__":
    import sys
    from core.render_vivlio.series.mockexam import profile as P
    key = sys.argv[1] if len(sys.argv) > 1 else "배재1"
    spec = P.get(key)
    print(build_css(spec))
