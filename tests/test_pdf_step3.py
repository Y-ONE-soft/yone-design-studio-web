"""PDF Step3 원고 파싱 (사용자 지시 2026-09-12) — 합성 PDF 회귀 시험.

실물 대조(수특라이트 12강 hwp ↔ 같은 원고 PDF: 내용 낱말 6,555개 차이 0 ·
밑줄 낱말 779개 전부 일치)는 GDrive 원고라 여기 넣지 못한다. 대신 추출기가
기대는 규칙 하나하나를 합성 PDF 로 못박는다.
"""
import os
import sys

import pytest

fitz = pytest.importorskip("fitz")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.extract.pdf import (_pdf_extract_paragraphs, PdfTextUnreadable,  # noqa: E402
                              _glue, _check_readable, _breaks,
                              _strip_lead_bullet, _trim_superscript_ref)

KO = "korea"          # PyMuPDF 내장 한글 글꼴

LOREM = ("The stock market is very important for companies because it can "
         "provide them with the money they need to grow and expand their "
         "business across many regions and markets over a long period.")


def _page(doc):
    return doc.new_page(width=595, height=842)


def _box(page, rect, text, size=9, font="helv", align=3):
    rc = page.insert_textbox(fitz.Rect(*rect), text, fontsize=size,
                             fontname=font, align=align)
    assert rc >= 0, "글상자 넘침 — 시험 PDF 설계 오류"


def _save(doc, tmp_path, name="t.pdf"):
    p = str(tmp_path / name)
    doc.save(p)
    return p


def _texts(paras):
    return [p["text"] for p in paras if p["text"].strip()]


def test_two_columns_read_left_then_right_and_margins_dropped(tmp_path):
    doc = fitz.open()
    for n in (1, 2):
        pg = _page(doc)
        pg.insert_text((200, 30), "Workbook Header Title", fontsize=9)
        pg.insert_text((290, 815), f"- {n} -", fontsize=9)
        _box(pg, (40, 80, 285, 400), f"LEFT{n} " + LOREM)
        _box(pg, (310, 80, 555, 400), f"RIGHT{n} " + LOREM)
    paras = _pdf_extract_paragraphs(_save(doc, tmp_path))
    t = _texts(paras)
    assert [x.split()[0] for x in t] == ["LEFT1", "RIGHT1", "LEFT2", "RIGHT2"]
    assert not any("Header" in x or x.startswith("-") for x in t)
    # 양끝정렬 줄들이 한 단락으로 이어진다 (줄마다 끊기지 않음)
    assert t[0].endswith("period.")


def test_paragraph_breaks_by_reflow_and_choices(tmp_path):
    doc = fitz.open()
    pg = _page(doc)
    body = ("1. What is the main idea of the passage?\n" + LOREM + "\n"
            "① to explain the rules\n② to ask parents\n③ to inform readers\n")
    _box(pg, (40, 80, 285, 600), body, align=0, font=KO)     # ① 글리프가 있는 글꼴
    t = _texts(_pdf_extract_paragraphs(_save(doc, tmp_path)))
    assert t[0].startswith("1. What is")
    assert t[1].startswith("The stock market") and t[1].endswith("period.")
    assert t[2:] == ["① to explain the rules", "② to ask parents",
                     "③ to inform readers"]


def test_underline_segments_but_not_box_borders(tmp_path):
    doc = fitz.open()
    pg = _page(doc)
    _box(pg, (50, 100, 280, 300), LOREM)
    # 상자 테두리 (글자보다 넓게 뻗는다) — 밑줄이 아니다
    pg.draw_rect(fitz.Rect(44, 94, 286, 180), color=(0, 0, 0), width=0.3)
    hits = pg.search_for("very important")      # 양끝정렬이면 낱말마다 조각
    x0, x1 = min(h.x0 for h in hits), max(h.x1 for h in hits)
    y = hits[0].y1 - 0.2 * 9 + 1.0
    pg.draw_line((x0, y), (x1, y), color=(0, 0, 0), width=0.4)
    paras = _pdf_extract_paragraphs(_save(doc, tmp_path), extract_underline=True)
    ul = "".join(r["t"] for p in paras for r in p["runs"] if r["ul"])
    assert ul.strip() == "very important"


def test_endnote_section_cut_and_refs_removed(tmp_path):
    doc = fitz.open()
    pg = _page(doc)
    body = "".join(f"{i}. Which is correct?{i})\n{LOREM}\n" for i in (1, 2, 3))
    _box(pg, (40, 80, 555, 700), body, align=0)
    pg2 = _page(doc)
    _box(pg2, (40, 80, 555, 400),
         "Answer Keys\n1) because of the reason\n2) since the text says so\n"
         "3) the last one\n", align=0)
    logs = []
    t = _texts(_pdf_extract_paragraphs(_save(doc, tmp_path), log=logs.append))
    assert not any("Answer" in x or x.startswith(("1)", "2)", "3)")) for x in t)
    assert t[0] == "1. Which is correct?"            # 각주번호 '1)' 제거
    assert any("미주" in l for l in logs)


def test_garbled_text_layer_refused():
    # Ghostscript 재출력본 실측 모양 — 공백이 'ா', 한글이 엉뚱한 문자
    good = list("다음 글의 제목으로 가장 적절한 것은? The stock market " * 20)
    _check_readable(good, "ok.pdf")                       # 통과
    bad = list("Howாdoாcompaniesாuseாtheாstockாmarket௕ ݟԼ/ݟ஍ " * 20)
    with pytest.raises(PdfTextUnreadable):
        _check_readable(bad, "ybm.pdf")
    with pytest.raises(PdfTextUnreadable):                # 스캔본: 글자 없음 + 그림
        _check_readable([], "scan.pdf", img_pages=3, n_pages=3)


def test_hangul_char_wrap_glue():
    ch = lambda s: [{"c": c, "ul": False} for c in s]
    # 줄 끝 공백 관행 문서: 한글-한글 사이 공백 없음 → 글자 단위 줄바꿈
    assert _glue(ch("쓰시"), ch("오.")) is None           # 한글은 붙여 쓴다
    assert _glue(ch("찾아 "), ch("쓰시오")) is None         # 줄 끝 공백은 그대로
    assert _glue(ch("well-"), ch("being")) is None
    assert _glue(ch("is a"), ch("waste"))["c"] == " "


# ── 파서·라우팅·게이트 ──────────────────────────────────────────────────────

def _pool_pdf(path, n=6, tag="A"):
    doc = fitz.open()
    pg = _page(doc)
    body = "".join(
        f"{i}. What is the main idea {tag}{i}?\n{LOREM}\n"
        f"① option one\n② option two\n③ option three\n"
        for i in range(1, n + 1))
    _box(pg, (40, 60, 555, 800), body, size=8, align=0)
    doc.save(path)


def _docx(path, texts):
    from docx import Document
    d = Document()
    for t in texts:
        d.add_paragraph(t)
    d.save(path)


def test_parser_reads_pdf_only_step3(tmp_path):
    from engines.workbook.parser import _parse_step3_folder
    s3 = tmp_path / "Step3"
    s3.mkdir()
    _pool_pdf(str(s3 / "예상 문제 A.pdf"))
    st3 = _parse_step3_folder(str(s3), 0, 0, 0, [], [], {})
    items = st3["normal"]
    assert len(items) == 1 and items[0]["question_num"] == "textbook"
    text = " ".join(p["text"] for p in items[0]["paragraphs"])
    assert "main idea A6" in text and "option three" in text
    assert "excluded_pdfs" not in st3


def test_parser_prefers_edit_source_and_skips_answer_pdf(tmp_path):
    from engines.workbook.parser import _parse_step3_folder
    from engines.workbook_v2.routing import reconcile_step3
    s3 = tmp_path / "Step3"
    s3.mkdir()
    lines = []
    for i in range(1, 7):
        lines += [f"{i}. What is the main idea A{i}?", LOREM,
                  "① option one", "② option two", "③ option three"]
    _docx(str(s3 / "변형문제.docx"), lines)
    _pool_pdf(str(s3 / "업체 변형문제 인쇄본.pdf"))       # 번호 없는 PDF = 참고본
    _pool_pdf(str(s3 / "변형문제 정답지.pdf"), tag="Z")
    logs = []
    st3 = _parse_step3_folder(str(s3), 0, 0, 0, [], [], {}, log=logs.append)
    text = " ".join(p["text"] for it in st3["normal"] for p in it["paragraphs"])
    assert text.count("main idea A6") == 1              # 두 번 들어가지 않는다
    assert "A6?" in text and "Z1" not in text
    assert sorted(st3["excluded_pdfs"]) == ["변형문제 정답지.pdf",
                                            "업체 변형문제 인쇄본.pdf"]
    assert sum("step3 PDF 제외" in l for l in logs) == 2
    stats = reconcile_step3(str(s3), st3, logs.append)     # [오류]로 멈추지 않는다
    assert len(stats["excluded"]) == 2


def test_parser_number_file_prefers_hwp_docx_over_pdf(tmp_path):
    from engines.workbook.parser import _parse_step3_folder
    s3 = tmp_path / "Step3"
    s3.mkdir()
    _docx(str(s3 / "20번.docx"), ["다음 글의 요지로 가장 적절한 것은?", "DOCX " + LOREM,
                                  "① a", "② b"])
    _pool_pdf(str(s3 / "20번.pdf"), n=1, tag="PDF")
    st3 = _parse_step3_folder(str(s3), 1, 26, 9, [20], [], {})
    assert len(st3["normal"]) == 1
    text = " ".join(p["text"] for p in st3["normal"][0]["paragraphs"])
    assert "DOCX" in text and "PDF1" not in text


def test_routing_pdf_goes_to_step3_except_answers_and_step12():
    from engines.workbook_v2.routing import route_step3, pdf_routes_to_step3
    assert route_step3("영어1 동아(박) 5과 - 예상 문제 A.pdf")
    assert pdf_routes_to_step3("2026년_9월_고1_모의고사_변형문제_문제지_수정본.pdf")
    assert not route_step3("2026년_9월_고1_모의고사_변형문제_정답지_수정본.pdf")
    assert not route_step3("Step1 A1 어휘선택.pdf")
    assert not pdf_routes_to_step3("Step3 원고.docx")


def test_gate_counts_excluded_pdf_as_expected(tmp_path):
    from engines.workbook_v2.gate import find_unused_uploads
    up = tmp_path / "uploads"
    (up / "Step3").mkdir(parents=True)
    (up / "Step3" / "변형문제.docx").write_bytes(b"x")
    (up / "Step3" / "업체 인쇄본.pdf").write_bytes(b"x")
    content = {"steps": {"step3": {
        "normal": [{"question_num": "textbook", "paragraphs": []}],
        "short": [], "excluded_pdfs": ["업체 인쇄본.pdf"]}}}
    expected, suspicious = find_unused_uploads(content, str(up))
    assert "업체 인쇄본.pdf" in expected
    assert suspicious == []


def test_parser_pdf_twins_by_name_and_number(tmp_path):
    # 명일여고1 '1강 1번.hwpx' + '1강 1번.pdf' 짝 실측 — 같은 이름·같은 번호는
    # 편집 원고만, 편집 원고가 없는 번호('1강 3번.pdf')는 PDF 로 읽는다
    from engines.workbook.parser import _parse_step3_folder
    s3 = tmp_path / "Step3"
    s3.mkdir()
    _docx(str(s3 / "1강 1번.docx"), ["다음 글의 요지로 가장 적절한 것은?",
                                    "DOCX " + LOREM, "① a", "② b"])
    _pool_pdf(str(s3 / "1강 1번.pdf"), n=1, tag="TWIN")
    _pool_pdf(str(s3 / "1강 3번.pdf"), n=1, tag="ONLY")
    logs = []
    st3 = _parse_step3_folder(str(s3), 0, 0, 0, [], [], {}, log=logs.append)
    text = " ".join(p["text"] for it in st3["normal"] for p in it["paragraphs"])
    assert "DOCX" in text and "ONLY1" in text and "TWIN1" not in text
    assert st3["excluded_pdfs"] == ["1강 1번.pdf"]


def _line(text, x0=40.0, x1=285.0, base=100.0, size=9.0):
    chars = [{"c": c, "x0": x0 + i * 4.0, "x1": x0 + i * 4.0 + 4.0, "ul": False}
             for i, c in enumerate(text)]
    return {"text": text, "chars": chars, "x0": x0, "x1": x1, "base": base,
            "size": size, "_colkey": (0, "L")}


def test_prompt_ends_at_instruction_even_when_line_is_full():
    # 명일3 수특 추가문제 실측 — 발문 끝줄이 단 끝까지 차서 우리말 줄이 붙었다
    prev = _line("모두 사용하여 영작하시오.", x1=284.0)
    cur = _line("부부는 서로 공감하려는 동기가 매우 높다;", base=113.0)
    assert _breaks(prev, cur, 285.0, 13.0, "1", 2, para_is_q=True)[0]
    # 발문이 아닌 한글 단락은 단 끝까지 찼으면 이어진다
    assert not _breaks(prev, cur, 285.0, 13.0, "부", 2, para_is_q=False)[0]
    # 발문 안 문장 중간 줄바꿈은 이어진다
    mid = _line("12. 다음 글의 밑줄 친 우리말과 같은 뜻이 되도록", x1=284.0)
    nxt = _line("<보기>에 주어진 단어만을 모두 사용하여", base=113.0)
    assert not _breaks(mid, nxt, 285.0, 13.0, "1", 1, para_is_q=True)[0]


def test_two_sentence_prompt_and_inline_choice_brackets():
    # '…요약하고자 한다.' 는 발문 안 — 끊지 않는다 (지시형 어미에서만 끝)
    a = _line("19. 다음 글의 내용을 한 문장으로 요약하고자 한다.", x1=284.0)
    b = _line("빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?", base=113.0)
    assert not _breaks(a, b, 285.0, 13.0, "1", 1, para_is_q=True)[0]
    c = _line("Hunters in the Ache tribe, living in the jungle,", base=126.0)
    assert _breaks(b, c, 285.0, 13.0, "1", 2, para_is_q=True)[0]
    # 지문 속 괄호 선택형이 줄 머리에 걸려도 지문은 이어진다
    p1 = _line("volunteers matched couples with 5)", x1=284.0)
    p2 = _line("6)[matching / matched] pairs at the same ages.", base=113.0)
    assert not _breaks(p1, p2, 285.0, 13.0, "M", 3)[0]
    p3 = _line("[striking / strikingly], the more similar people", base=113.0)
    assert not _breaks(p1, p3, 285.0, 13.0, "M", 3)[0]
    # 세트 안내('[서답형 1~2] … 답하시오.') 뒤 지문은 끊는다
    s1 = _line("[서답형 1~2] 다음 글을 읽고 물음에 답하시오.", x1=284.0)
    s2 = _line("Located in the historic city of Ningbo, China,", base=113.0)
    assert _breaks(s1, s2, 285.0, 13.0, "[", 1, para_is_q=True)[0]


def _chs(text, size=10.0, tail_size=None, tail=0):
    out = [{"c": c, "size": size, "ul": False} for c in text]
    if tail_size:
        for c in out[-tail:]:
            c["size"] = tail_size
    return out


def test_superscript_ref_and_bullet_glyph_trimmed():
    txt = lambda cs: "".join(c["c"] for c in cs)
    # 첨자 각주번호(7.6pt)는 떼고, 본문 크기 '(단어 2개)'·'5)' 는 둔다
    body, ref = _trim_superscript_ref(_chs("가장 적절한 것은?12)", tail_size=7.6, tail=3))
    assert txt(body) == "가장 적절한 것은?" and ref == 12      # 번호는 미주 판정용으로 남긴다
    body, ref = _trim_superscript_ref(_chs("변형할 것)12)", tail_size=7.6, tail=3))
    assert txt(body) == "변형할 것)" and ref == 12
    body, ref = _trim_superscript_ref(_chs("본문 속 번호 5)"))
    assert txt(body) == "본문 속 번호 5)" and ref is None
    # hwp 글머리표가 글자로 찍힌 것(∎, 기호 글꼴 사용자 영역)은 떼고 ■ 는 둔다
    assert txt(_strip_lead_bullet(_chs("∎ 다음 글을 읽고 물음에 답하시오."))) \
        == "다음 글을 읽고 물음에 답하시오."
    assert txt(_strip_lead_bullet(_chs("\uf076 다음 글을 읽고"))) == "다음 글을 읽고"
    assert txt(_strip_lead_bullet(_chs("■ 어휘 정리"))) == "■ 어휘 정리"


def test_wide_space_blank_is_kept():
    """밑줄 없이 전각 공백으로 만든 빈칸(너른터 원고) — 칸이 사라지면 답 쓸 자리가 없다.

    합성 PDF 로는 재현이 안 된다(글상자가 공백을 지운다) — 글자 자료로 못박는다.
    """
    from core.extract.pdf import _line_chars, _chars_to_para
    mk = lambda c, x0, x1, sz=9.0: {"c": c, "x0": x0, "x1": x1, "base": 100.0,
                                    "size": sz, "ul": False}
    # 'to' 다음 40pt 빈 자리 → 빈칸, 그 뒤 '.' (원고 실측 모양)
    span = {"base": 100.0, "size": 9.0, "spans": [{"chars": [
        mk("t", 10, 15), mk("o", 15, 20), mk(".", 60, 63), mk("I", 63, 69)]}]}
    chars = _line_chars(span)
    blanks = [c for c in chars if c.get("blank")]
    assert len(blanks) >= 4, [c["c"] for c in chars]
    p = _chars_to_para(chars)
    assert p["text"].startswith("to") and "  " in p["text"], repr(p["text"])
    # 줄 끝이 빈칸이면 단락을 끊지 않는다
    prev = {"text": "to    ", "chars": chars[:6], "x0": 10, "x1": 20, "base": 100.0,
            "size": 9.0, "_colkey": (0, "S")}
    cur = {"text": "Instead of the park", "chars": [mk("I", 10, 16)],
           "x0": 10, "x1": 100, "base": 113.0, "size": 9.0, "_colkey": (0, "S")}
    assert _breaks(prev, cur, 300.0, 13.0) == (False, False)
