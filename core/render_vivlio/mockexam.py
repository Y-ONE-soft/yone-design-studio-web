"""동형모의고사 시리즈 — 렌더 플랜 → 시맨틱 HTML (W51).

파일럿 `pilot/vivliostyle/render_html.py` 를 백엔드로 승격한 것. 플랜의
스타일명(실물 InDesign 단락 스타일명)을 CSS 클래스로 1:1 매핑하면
`themes/mockexam.css`(CSS Paged Media)가 조판한다.

플랜 소비 인터페이스는 mockexam_v2 의 `ir_to_render_plan` 출력과 동일하다 —
InDesign 백엔드와 **같은 플랜**을 받는다.
"""
import html
import re

# 실물 InDesign 단락 스타일명 → CSS 클래스
STYLE_CLASS = {
    "문제 번호": "q",
    "서술형 번호": "srv",
    "다음 글을 읽고": "intro",
    "지문": "passage",
    "영어지문_순서": "porder",
    "영어지문 번호": "pnum",
    "선지": "choice",
    "조건": "cond",
    "테두리": "boxline",
    "보스조건박스": "boxline",
    "테두리 대화문": "boxline",
    "영단어": "word",
    "서술형답지": "ans",
    "점수": "score",
}

# HWP 사설영역(PUA) 글리프 → 유니코드
PUA_MAP = {"\U000f003b": "⬇"}
_RE_ARROW = re.compile(r"([⬇↓])")

# 지문류 단락 안의 (a)~(e)/(A)~(E)/[A]/[B] 마커 볼드 (실물 GREP 재현)
_RE_GREP_BOLD = re.compile(r"(\(\s*[A-Ea-e]\s*\)|\[[AB]\])")
_GREP_BOLD_STYLES = {"passage", "porder", "srv"}


def _fix_pua(text):
    for k, v in PUA_MAP.items():
        text = text.replace(k, v)
    return text


def _esc(text):
    return html.escape(_fix_pua(text or ""), quote=False)


def _inline(text, runs, css_class):
    """단락 텍스트 → 인라인 HTML (밑줄 runs + GREP 볼드 + 화살표)."""
    if runs:
        parts = []
        for r in runs:
            t = _esc(r["t"])
            parts.append(f"<u>{t}</u>" if r.get("ul") else t)
        out = "".join(parts)
    else:
        out = _esc(text)
    if css_class in _GREP_BOLD_STYLES:
        out = _RE_GREP_BOLD.sub(r"<b>\1</b>", out)
    out = _RE_ARROW.sub(r'<span class="arrow">\1</span>', out)
    return out


def plan_to_body(plan):
    """렌더 플랜 → 본문 HTML 조각 목록.

    - 문제/서술형 번호는 파이썬 카운터로 재현(검증 가능하도록 데이터에 박제).
    - 연속된 '테두리' 단락은 하나의 박스로 묶음.
    """
    out = []
    q_no = 0
    srv_no = 0
    prev_cls = None
    state = {"box_open": False}

    def close_box():
        if state["box_open"]:
            out.append("</div>")
            state["box_open"] = False

    for item in plan:
        cls = STYLE_CLASS.get(item.get("s"), "passage")
        text = item.get("t", "")
        inner = _inline(text, item.get("runs"), cls)

        if cls == "boxline":
            if not state["box_open"]:
                out.append('<div class="box">')
                state["box_open"] = True
            out.append(f'<p class="boxline">{inner}</p>')
            prev_cls = cls
            continue
        close_box()

        if cls == "q":
            q_no += 1
            out.append(f'<p class="q"><span class="qnum">{q_no}.&#8199;&#8199;'
                       f'</span>{inner}</p>')
        elif cls == "srv":
            srv_no += 1
            out.append(f'<p class="srv"><span class="qnum">[서술형 {srv_no}]'
                       f'&#8199;&#8199;</span>{inner}</p>')
        elif cls == "choice":
            first = " choice-first" if prev_cls != "choice" else ""
            out.append(f'<p class="choice{first}">{inner}</p>')
        else:
            out.append(f'<p class="{cls}">{inner}</p>')
        prev_cls = cls

    close_box()
    return out


def _header_html(case):
    """러닝 헤더: 저작권 문구 + 시험 정보 머리표 — 매 페이지 반복."""
    c = case
    return f"""
<div class="page-header">
  <div class="copyright">{_esc(c.get("copyright_line", ""))}</div>
  <table class="exam-head">
    <tr>
      <td class="lbl code-lbl">과목코드</td>
      <td class="lbl">구분</td>
      <td class="val">{_esc(c.get("exam_title", ""))}</td>
      <td class="title" rowspan="3">{_esc(c.get("subject_title", ""))}</td>
      <td class="lbl wide">출제교사</td>
      <td class="lbl">부장</td>
      <td class="lbl">교감</td>
    </tr>
    <tr>
      <td class="code" rowspan="2">{_esc(c.get("subject_code", ""))}</td>
      <td class="lbl">일시</td>
      <td class="val">{_esc(c.get("date_line", ""))}</td>
      <td class="teachers" rowspan="2">{_esc(c.get("teachers", ""))}</td>
      <td rowspan="2"></td>
      <td rowspan="2"></td>
    </tr>
    <tr>
      <td class="lbl">대상</td>
      <td class="val">{_esc(c.get("target_line", ""))}</td>
    </tr>
  </table>
</div>"""


def _footer_html(case):
    """러닝 푸터 2종: 일반('다음 쪽에 계속')과 마지막('끝.').

    마지막 페이지 적용은 build.render_html_to_pdf(last_page_end=True) 가
    @page :nth(N) 오버라이드로 주입.
    """
    school = _esc("( " + case.get("school_full", "") + " )")
    common = (f'<div class="foot-row"><span class="pgnum"></span>'
              f'<span class="foot-school">{school}</span></div>')
    return (f'<div class="page-footer">'
            f'<div class="cont-line">☞다음 쪽에 계속</div>{common}</div>\n'
            f'<div class="page-footer-last">'
            f'<div class="cont-line"><span class="end-mark">끝.</span></div>'
            f'{common}</div>')


def _qtype_box_html(case):
    """문제유형 박스 — 1페이지 왼쪽 단 최상단 (플로우 첫 블록)."""
    b = case.get("qtype_box")
    if not b:
        return ""
    return f"""
<table class="qtype-box">
  <tr>
    <td class="qt-lbl" rowspan="2">문제유형</td>
    <td>선택형</td>
    <td>서답형</td>
  </tr>
  <tr>
    <td>( {b.get("select_items", "")} ) 문항 / ( {b.get("select_points", "")} ) 점</td>
    <td>( {b.get("essay_items", "")} ) 문항 / ( {b.get("essay_points", "")} ) 점</td>
  </tr>
</table>"""


def build_html(plan, case):
    body = "\n".join(plan_to_body(plan))
    title = _esc(case.get("subject_title", "동형모의고사"))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title} — Vivliostyle</title>
<link rel="stylesheet" href="theme.css">
</head>
<body>
{_header_html(case)}
{_footer_html(case)}
<section class="flow">
{_qtype_box_html(case)}
{body}
</section>
</body>
</html>
"""
