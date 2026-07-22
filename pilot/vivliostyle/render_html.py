#!/usr/bin/env python3
"""W42 Vivliostyle 파일럿 — mockexam_v2 렌더 플랜 → 시맨틱 HTML.

기존 파이프라인(engines.mockexam_v2.parser.build_ir → render.ir_to_render_plan)을
소비만 한다(기존 코드 무수정). 플랜의 스타일명(실물 InDesign 단락 스타일명)을
CSS 클래스로 1:1 매핑해 theme.css(CSS Paged Media)가 조판한다.

사용:
    python3 pilot/vivliostyle/render_html.py tests/corpus/mockexam/029c4385 \
        --case pilot/vivliostyle/case_hanyoung3.json -o out/exam.html
"""
import argparse
import glob
import html
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

# 실물 InDesign 단락 스타일명 → CSS 클래스 (template_spec_dh_hanyoung3.json 스타일 인벤토리)
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

# HWP 사설영역(PUA) 글리프 → 유니코드 (실물은 폰트 폴백으로 ⬇ 렌더)
PUA_MAP = {"\U000f003b": "⬇"}
_RE_ARROW = re.compile(r"([⬇↓])")

# 실물 템플릿의 GREP 스타일 재현: 지문류 단락 안의 (a)~(e)/(A)~(E)/[A]/[B] 마커 볼드
_RE_GREP_BOLD = re.compile(r"(\(\s*[A-Ea-e]\s*\)|\[[AB]\])")
_GREP_BOLD_STYLES = {"passage", "porder", "srv"}


def _fix_pua(text):
    for k, v in PUA_MAP.items():
        text = text.replace(k, v)
    return text


def _esc(text):
    return html.escape(_fix_pua(text), quote=False)


def _inline(text, runs, css_class):
    """단락 텍스트 → 인라인 HTML (밑줄 runs + GREP 볼드 + 탭)."""
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
    # 탭 → InDesign 탭 스톱 근사 (theme.css: white-space:pre-wrap + tab-size)
    return out


def plan_to_body(plan):
    """렌더 플랜 → 본문 HTML 조각 목록.

    - 문제 번호/서술형 번호 자동 번호는 실물 템플릿의 단락 번호 매기기(H2gtrE)를
      파이썬 카운터로 재현 (검증 가능하도록 데이터에 박제).
    - 연속된 '테두리' 단락은 하나의 박스로 묶음.
    """
    out = []
    q_no = 0
    srv_no = 0
    prev_cls = None
    box_open = False

    def close_box():
        nonlocal box_open
        if box_open:
            out.append("</div>")
            box_open = False

    for item in plan:
        cls = STYLE_CLASS.get(item["s"], "passage")
        text = item["t"]
        inner = _inline(text, item.get("runs"), cls)

        if cls == "boxline":
            if not box_open:
                out.append('<div class="box">')
                box_open = True
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


def header_html(case):
    """머리표(러닝 헤더): 저작권 문구 + 시험 정보 테이블 — 매 페이지 반복."""
    c = case
    return f"""
<div class="page-header">
  <div class="copyright">{_esc(c["copyright_line"])}</div>
  <table class="exam-head">
    <tr>
      <td class="lbl code-lbl">과목코드</td>
      <td class="lbl">구분</td>
      <td class="val">{_esc(c["exam_title"])}</td>
      <td class="title" rowspan="3">{_esc(c["subject_title"])}</td>
      <td class="lbl wide">출제교사</td>
      <td class="lbl">부장</td>
      <td class="lbl">교감</td>
    </tr>
    <tr>
      <td class="code" rowspan="2">{_esc(c["subject_code"])}</td>
      <td class="lbl">일시</td>
      <td class="val">{_esc(c["date_line"])}</td>
      <td class="teachers" rowspan="2">{_esc(c["teachers"])}</td>
      <td rowspan="2"></td>
      <td rowspan="2"></td>
    </tr>
    <tr>
      <td class="lbl">대상</td>
      <td class="val">{_esc(c["target_line"])}</td>
    </tr>
  </table>
</div>"""


def footer_html(case):
    """러닝 푸터 2종: 일반 페이지('다음 쪽에 계속')와 마지막 페이지('끝.').

    마지막 페이지 적용은 build.py 2차 패스가 @page :nth(N) 오버라이드로 주입.
    """
    school = _esc("( " + case["school_full"] + " )")
    common = (f'<div class="foot-row"><span class="pgnum"></span>'
              f'<span class="foot-school">{school}</span></div>')
    return (f'<div class="page-footer">'
            f'<div class="cont-line">☞다음 쪽에 계속</div>{common}</div>\n'
            f'<div class="page-footer-last">'
            f'<div class="cont-line"><span class="end-mark">끝.</span></div>'
            f'{common}</div>')


def qtype_box_html(case):
    """문제유형 박스 — 1페이지 왼쪽 단 최상단 (플로우 첫 블록)."""
    b = case["qtype_box"]
    return f"""
<table class="qtype-box">
  <tr>
    <td class="qt-lbl" rowspan="2">문제유형</td>
    <td>선택형</td>
    <td>서답형</td>
  </tr>
  <tr>
    <td>( {b["select_items"]} ) 문항 / ( {b["select_points"]} ) 점</td>
    <td>( {b["essay_items"]} ) 문항 / ( {b["essay_points"]} ) 점</td>
  </tr>
</table>"""


def build_html(plan, case):
    body = "\n".join(plan_to_body(plan))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{_esc(case["subject_title"])} — Vivliostyle 파일럿</title>
<link rel="stylesheet" href="theme.css">
</head>
<body>
{header_html(case)}
{footer_html(case)}
<section class="flow">
{qtype_box_html(case)}
{body}
</section>
</body>
</html>
"""


def load_plan_from_corpus(case_dir):
    """코퍼스 케이스 → 렌더 플랜 (라이브 파이프라인 소비 — 기존 코드 무수정)."""
    from engines.mockexam_v2.parser import extract_file_paragraphs, build_ir
    from engines.mockexam_v2.render import ir_to_render_plan

    inputs = sorted(glob.glob(os.path.join(case_dir, "inputs", "*.hwpx"))
                    + glob.glob(os.path.join(case_dir, "inputs", "*.hwp"))
                    + glob.glob(os.path.join(case_dir, "inputs", "*.docx")))
    if not inputs:
        raise SystemExit(f"원고 없음: {case_dir}/inputs")
    paras = extract_file_paragraphs(inputs[0])
    doc = build_ir(paras)
    return ir_to_render_plan(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir", help="코퍼스 케이스 디렉터리 (inputs/*.hwpx)")
    ap.add_argument("--case", required=True, help="템플릿 비품 설정 JSON")
    ap.add_argument("-o", "--out", required=True, help="출력 HTML 경로")
    args = ap.parse_args()

    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)
    plan = load_plan_from_corpus(args.case_dir)
    html_text = build_html(plan, case)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"플랜 {len(plan)}개 단락 → {args.out}")


if __name__ == "__main__":
    main()
