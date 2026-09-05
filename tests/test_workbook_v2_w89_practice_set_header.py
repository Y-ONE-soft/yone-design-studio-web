"""W89 — "학평 변형" 연습용 문제 세트 원고의 표제/설명 두 줄 잔존 + 도표
답표/선지 셀 조각남.

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


# ── 인라인 ＜조건＞ 마커 분리 (사용자 지적 "여긴 조건인데 조건 안입혀지고") ──

def test_inline_cond_marker_split_into_two_lines():
    from engines.workbook.parser import _split_step3_inline_cond_marker
    rows = _p("＜조건＞ 글에 쓰인 형태 그대로 쓸 것. (어형 변화 불가)",
             "(A) ______________　　(B) ______________")
    out = _texts(_split_step3_inline_cond_marker(rows))
    assert out == ["＜조건＞", "글에 쓰인 형태 그대로 쓸 것. (어형 변화 불가)",
                   "(A) ______________　　(B) ______________"]


def test_standalone_cond_marker_untouched():
    """이미 단독 줄인 마커는 그대로 — 이중 분리 방지."""
    from engines.workbook.parser import _split_step3_inline_cond_marker
    rows = _p("＜조건＞", "· 반드시 강조 구문을 사용할 것.")
    assert _texts(_split_step3_inline_cond_marker(rows)) == _texts(rows)


def test_normalize_pipeline_applies_cond_split_and_classifies_correctly():
    """분리 후 core.structure가 두 줄 다 Cond로 인식한다(마커는 단독
    줄이어야 한다는 공용 규약을 그대로 만족)."""
    from engines.workbook.parser import _normalize_step3_manuscript
    from core.structure import classify_paragraphs
    rows = _p("다음 글을 읽고, 빈칸에 알맞은 말을 쓰시오.",
             "＜조건＞ 글에 쓰인 형태 그대로 쓸 것. (어형 변화 불가)",
             "(A) ______________　　(B) ______________")
    out = _normalize_step3_manuscript(rows, item_num=None)
    kinds = [r["kind"] for r in classify_paragraphs(out)]
    texts = _texts(out)
    assert texts[1] == "＜조건＞"
    assert kinds[texts.index("＜조건＞")] == "Cond"
    assert kinds[texts.index("글에 쓰인 형태 그대로 쓸 것. (어형 변화 불가)")] \
        == "Cond"


# ── 표 선지 셀 재결합 (사용자 지적 "선지 정렬 엉망"/"이건 뭐야") ──────────

def test_table_choice_cells_merged_with_header():
    from engines.workbook.parser import _merge_step3_table_choice_cells
    rows = _p("(A)", "(B)",
             "①", "memory", "sharpens",
             "②", "memory", "breaks",
             "③", "eyes", "breaks",
             "④", "eyes", "sharpens",
             "⑤", "patience", "sharpens")
    out = _texts(_merge_step3_table_choice_cells(rows))
    assert out == [
        "(A)\t(B)",
        "①\tmemory\tsharpens",
        "②\tmemory\tbreaks",
        "③\teyes\tbreaks",
        "④\teyes\tsharpens",
        "⑤\tpatience\tsharpens",
    ]


def test_single_lone_circled_line_not_merged():
    """반복(2행+)이 없는 단독 원문자 줄은 절대 건드리지 않는다 — 오탐 방지."""
    from engines.workbook.parser import _merge_step3_table_choice_cells
    rows = _p("①", "그냥 뒤따르는 무관한 한 줄.")
    assert _texts(_merge_step3_table_choice_cells(rows)) == _texts(rows)


def test_classify_paragraphs_recognizes_merged_choice_row_as_C():
    """골든 관행(r5c04mock211)과 동일하게, 합친 줄은 선지(C)로 분류된다."""
    from engines.workbook.parser import _merge_step3_table_choice_cells
    from core.structure import classify_paragraphs
    rows = _p("①", "memory", "sharpens", "②", "memory", "breaks")
    merged = _merge_step3_table_choice_cells(rows)
    kinds = [r["kind"] for r in classify_paragraphs(merged)]
    assert kinds == ["C", "C"]


# ── 답표 열 머리 셀 재결합 (사용자 지적 "기호 고친 표현이 … 왜 조건으로") ──

def test_ans_table_header_cells_merged():
    from engines.workbook.parser import _merge_step3_ans_table_header_cells
    rows = _p("기호", "고친 표현", "(1)")
    out = _texts(_merge_step3_ans_table_header_cells(rows))
    assert out == ["기호        고친 표현", "(1)"]


def test_cond_block_stops_before_ans_table_header_after_merge():
    """핵심 회귀 방지: ＜조건＞ 채점 안내 뒤에 답표 헤더가 와도 조건으로
    삼키지 않는다 — 정규화 파이프라인 전체(병합 포함)를 거쳐야 한다."""
    from engines.workbook.parser import _normalize_step3_manuscript
    from core.structure import classify_paragraphs
    rows = _p(
        "다음 글의 밑줄 친 ⓐ~ⓕ 중 어법상 틀린 곳 2개를 찾아 기호를 쓰고, "
        "각각 바르게 고쳐 쓰시오.",
        "＜조건＞",
        "· 반드시 기호를 쓰고 고친 표현을 각각 기입한 경우에만 정답으로 처리함.",
        "기호", "고친 표현", "(1)", "", "(2)", "",
    )
    out = _normalize_step3_manuscript(rows, item_num=None)
    result = classify_paragraphs(out)
    by_text = {r["text"]: r["kind"] for r in result if r["text"]}
    assert by_text["＜조건＞"] == "Cond"
    assert by_text["기호        고친 표현"] == "UNKNOWN"      # Cond에 안 먹힘
    assert by_text["(1)"] == "UNKNOWN"
    assert by_text["(2)"] == "UNKNOWN"


def test_cond_item_mentioning_vocab_word_not_falsely_ended():
    """회귀 재현(tests/corpus/textbook_workbook/r7c11oldwb 실증): 조건
    항목 문장이 우연히 답표 어휘 하나("오류")를 담아도 조건 블록을 안
    끊는다 — 답표 헤더는 항상 라벨 2개 이상이 한 줄에 온다."""
    from core.structure import rules as R
    assert not R.is_ans_table_header_line("3. 철자 오류 1건 당 1점씩 감점")
    assert R.is_ans_table_header_line("기호        고친 표현")


def test_ans_table_header_merge_does_not_absorb_preceding_unrelated_lines():
    """회귀 재현(af602035 고2 25년 6월 18번 실증): 편지 맺음말 "James
    Martin"/"Principal"이 답표 헤더("틀린 부분"/"수정") 바로 앞에 짧은
    단독 줄로 와도 함께 삼키지 않는다 — 어휘가 실제로 걸린 셀에서만
    시작해 뒤로만(앞으로는 안) 이어붙인다."""
    from engines.workbook.parser import _merge_step3_ans_table_header_cells
    rows = _p("James Martin", "Principal", "틀린 부분", "수정",
             "다음 글의 빈칸에 들어갈 알맞은 단어를 쓰시오.")
    out = _texts(_merge_step3_ans_table_header_cells(rows))
    assert out == ["James Martin", "Principal", "틀린 부분        수정",
                   "다음 글의 빈칸에 들어갈 알맞은 단어를 쓰시오."]


# ── 서답형 라벨 줄 재결합 (사용자 지적 "13/14 두 번호가 붙는다") ──────────

def test_subjective_label_merged_with_following_prompt():
    from engines.workbook.parser import _merge_step3_subjective_label_line
    rows = _p("서답형 1.",
             "다음 글의 밑줄 친 ⓐ~ⓕ 중 어법상 틀린 곳 2개를 찾아 기호를 "
             "쓰고, 각각 바르게 고쳐 쓰시오.")
    out = _texts(_merge_step3_subjective_label_line(rows))
    assert out == ["서답형 1. 다음 글의 밑줄 친 ⓐ~ⓕ 중 어법상 틀린 곳 2개를 "
                  "찾아 기호를 쓰고, 각각 바르게 고쳐 쓰시오."]


def test_subjective_label_alone_at_end_untouched():
    """뒤에 발문이 없으면(원고 끝 등) 절대 건드리지 않는다."""
    from engines.workbook.parser import _merge_step3_subjective_label_line
    rows = _p("서답형 3.")
    assert _texts(_merge_step3_subjective_label_line(rows)) == ["서답형 3."]


def test_normalize_pipeline_merged_subjective_label_gets_single_question_kind():
    """핵심 회귀 방지: 합친 뒤 core.structure가 한 단락으로만 Q 판정한다
    — 라벨과 발문이 각각 번호 스타일을 받아 번호가 두 번 매겨지던 결함."""
    from engines.workbook.parser import _normalize_step3_manuscript
    from core.structure import classify_paragraphs
    rows = _p("서답형 2.",
             "다음 글을 읽고, 아래 요약문의 빈칸 (A), (B)에 들어갈 말을 "
             "글에서 찾아 각각 한 단어로 그대로 쓰시오.")
    out = _normalize_step3_manuscript(rows, item_num=None)
    assert len(out) == 1
    result = classify_paragraphs(out)
    assert result[0]["kind"] == "Q"
