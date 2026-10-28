"""세종 간지 바탕 그림 — 원본 1쪽(도련 포함)에서 원고 자리 글(권 번호 · 교재명 · 강제목)을 지우고 SVG(글자는 윤곽)로.
guide=0 이면 학습 가이드 카드(그림 · 머리 선)도 지운다.
학교 「세종고」는 남긴다 — 원본 서체(TT 옴니고딕 L)가 시스템 서체에 없어 글상자로는 모양이 달라진다(2026-10-28).

    divider_art.py <원본 내지 PDF> <교재명 글> <강제목 글> <내보낼 폴더> <이름 앞말>
    예) 중간(남색): … 세종1_분석본01(비상홍1과)_내지.pdf "공통영어2 비상(홍) Unit 1" "A Road Ahead" out sejong_divider
        기말(버건디): … 세종1_분석본01(비상홍3과)_내지.pdf "공통영어2 비상(홍) Unit 3" "The Gift of Art" out sejong_final_divider"""
import sys, pymupdf
SRC, BOOK, LESSON, S, STEM = sys.argv[1:6]
src = pymupdf.open(SRC)
for guide in (1, 0):
    doc = pymupdf.open()
    doc.insert_pdf(src, from_page=0, to_page=0)
    p = doc[0]
    T = p.trimbox
    for t in (BOOK, LESSON, "1"):
        for r in p.search_for(t):
            if t == "1" and not (r.x0 > 290 and r.y0 > 420 and r.y1 < 470):
                continue
            p.add_redact_annot(r)
    p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if not guide:   # 가이드 카드(재단 기준 y 575~760 안에 다 든 그림)를 지운다
        p.add_redact_annot(pymupdf.Rect(T.x0 + 195, T.y0 + 575, T.x0 + 400, T.y0 + 760), fill=False)
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=1)
    svg = p.get_svg_image(text_as_path=True)
    out = f"{S}/{STEM}{'_guide' if guide else ''}.svg"
    open(out, "w").write(svg)
    print(out, len(svg), p.rect)
