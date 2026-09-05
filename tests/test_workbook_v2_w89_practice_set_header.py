"""W89 — "학평 변형" 연습용 문제 세트 원고의 표제/설명 두 줄 잔존.

사용자 지적(2026-09-05, 고1 26년 9월 모의고사 워크북): 서답형 문항 앞에
"고1 2026년 9월 학평 변형 — 지문 33 (모방론과 폴록) 【문제】" / "연습용 ·
독립 문항 15개. …정답·해설: 지문33_정답해설.docx" 두 줄이 그대로 인쇄돼
발문처럼 보였다.

원고는 지문별 문제 파일(예: '지문33_문제.docx')마다 맨 앞에 이 두 줄이
반복된다. W88과 같은 부류(원고 편집 잔재)지만 낱말이 원고마다(제목·지문
번호·정답 파일명) 전부 달라 낱말 목록으로는 못 잡는다. 대신 각 줄이
실제 발문/지문 문장에는 나올 수 없는 고유 표식을 갖는다는 점으로 잡는다:
표제 줄은 전각 괄호 【문제】로 끝나고, 설명 줄은 파일명(.docx)을 그대로
노출한다. 코퍼스 실측(Step3 폴더 520개 파일)으로 이 두 신호가 걸린 자리는
이 잡의 4개 파일뿐임을 확인했다 — 다른 원고에 우연히 걸리는 자리 없음.
"""


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def _texts(paras):
    from engines.workbook.parser import _s3_text
    return [_s3_text(p) for p in paras if _s3_text(p)]


def test_practice_set_title_and_desc_stripped():
    from engines.workbook.parser import _strip_step3_practice_set_header
    rows = _p(
        "고1 2026년 9월 학평 변형 — 지문 33 (모방론과 폴록) 【문제】",
        "연습용 · 독립 문항 15개. …정답·해설: 지문33_정답해설.docx",
        "1. 다음 글의 제목으로 가장 적절한 것은?",
    )
    out = _texts(_strip_step3_practice_set_header(rows))
    assert out == ["1. 다음 글의 제목으로 가장 적절한 것은?"]


def test_real_content_with_docx_or_bracket_word_untouched_elsewhere():
    """혹시 모를 오탐 방지: 두 신호(전각【문제】 종결, .docx 노출)가 없는
    일반 발문/지문은 절대 건드리지 않는다."""
    from engines.workbook.parser import _strip_step3_practice_set_header
    rows = _p(
        "다음 글을 읽고 물음에 답하시오.",
        "A passage sentence with no special markers at all.",
        "① a  ② b  ③ c  ④ d  ⑤ e",
    )
    assert _texts(_strip_step3_practice_set_header(rows)) == _texts(rows)


def test_normalize_pipeline_removes_header_and_preserves_body():
    from engines.workbook.parser import _normalize_step3_manuscript
    rows = _p(
        "고1 2026년 9월 학평 변형 — 지문 33 (모방론과 폴록) 【문제】",
        "연습용 · 독립 문항 15개. …정답·해설: 지문33_정답해설.docx",
        "1. 다음 글의 제목으로 가장 적절한 것은?",
        "The ancient Greeks felt that the visual artist's goal was "
        "to copy visual experience.",
        "① Greek Pottery: A Window into Lost Paintings",
    )
    out = _texts(_normalize_step3_manuscript(rows, item_num="33"))
    assert not any("【문제】" in t for t in out)
    assert not any(".docx" in t for t in out)
    assert "1. 다음 글의 제목으로 가장 적절한 것은?" in out
    assert "① Greek Pottery: A Window into Lost Paintings" in out
