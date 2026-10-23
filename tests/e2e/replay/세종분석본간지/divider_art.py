"""세종 간지 바탕 그림 — 원본 1쪽(도련 포함)에서 원고 자리 글(학교 · 권 번호 · 교재명 · 강제목)을 지우고 SVG(글자는 윤곽)로.
guide=0 이면 학습 가이드 카드(그림 · 머리 선)도 지운다."""
import os, glob, sys, pymupdf
S = os.path.dirname(os.path.abspath(__file__))
D = os.path.expanduser("~/Downloads/세종고 분석본 표지, 내지 디자인")
fs = sorted(glob.glob(D + "/*.pdf"))
src = pymupdf.open(fs[0])
for guide in (1, 0):
    doc = pymupdf.open()
    doc.insert_pdf(src, from_page=0, to_page=0)
    p = doc[0]
    T = p.trimbox
    for t in ("세종고", "공통영어2 비상(홍) Unit 1", "A Road Ahead", "1"):
        for r in p.search_for(t):
            if t == "1" and not (r.x0 > 290 and r.y0 > 420 and r.y1 < 470):
                continue
            p.add_redact_annot(r)
    p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if not guide:   # 가이드 카드(재단 기준 y 575~760 안에 다 든 그림)를 지운다
        p.add_redact_annot(pymupdf.Rect(T.x0 + 195, T.y0 + 575, T.x0 + 400, T.y0 + 760), fill=False)
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=1)
    svg = p.get_svg_image(text_as_path=True)
    out = f"{S}/sejong_divider{'_guide' if guide else ''}.svg"
    open(out, "w").write(svg)
    print(out, len(svg), p.rect)
