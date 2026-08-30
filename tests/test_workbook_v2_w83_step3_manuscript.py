"""W83 — 부교재 Step3 원고 정규화 (수능만만 09강 재조판 지적 7건).

사용자 지적: ①책 표제·유형 라벨·저작권 줄이 지문으로 인쇄 ②발문 끝 각주
번호('…것은?155)') ③한 발문이 두 조각 나 번호가 두 번 ④지문이 중간에서
끊김 ⑤원고 157문항인데 번호가 모자람 ⑥주어진 문장에 상자 스타일 미적용
⑦한 줄에 두 개인 선지가 어긋남.

③~⑥은 뿌리가 하나다 — 원고가 PDF/HWP 변환본이라 한 문단이 **시각 줄마다**
별개 단락으로 끊겨 있다. 되붙이면 발문 인식(→번호·문항 수)과 주어진 문장
상자 판정이 함께 살아난다.
"""
import re


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def _texts(paras):
    return [p["text"] for p in paras]


# ── ③④⑤ 쪼개진 단락 되붙임 ─────────────────────────────────────────────────

def test_join_english_wrapped_passage():
    from engines.workbook.parser import _join_step3_split_paragraphs
    long_head = ("A person who chooses to avoid using or consuming animal "
                 "products is known as a vegan. Like")
    out = _texts(_join_step3_split_paragraphs(
        _p(long_head, "vegetarians, vegans don't eat meat.")))
    assert out == [long_head + " vegetarians, vegans don't eat meat."]


def test_join_split_prompt_keeps_one_number():
    """발문이 두 조각이면 조판이 번호를 두 번 매긴다 (원고 157 → 번호 153)."""
    from engines.workbook.parser import _join_step3_split_paragraphs
    out = _texts(_join_step3_split_paragraphs(
        _p("90. 위 글에서 foreign aggressors 가 의미하는 바로 가장 적절한 것",
           "은?90)")))
    assert out == ["90. 위 글에서 foreign aggressors 가 의미하는 바로 "
                   "가장 적절한 것은?90)"]


def test_join_glue_respects_korean_word_break():
    """한글은 낱말 사이에서 끊길 수도, 한가운데서 끊길 수도 있다."""
    from engines.workbook.parser import _join_step3_split_paragraphs
    mid = _texts(_join_step3_split_paragraphs(
        _p("106. 위 글의 밑줄 친 (K)부분이 의미하는 바를 본문에서 찾아 필요시 변",
           "형하여 적으시오.106)")))
    assert "필요시 변형하여" in mid[0]
    between = _texts(_join_step3_split_paragraphs(
        _p("45. 위", "글에서 advertising 이 의미하는 바로 적절한 것은?45)")))
    assert "45. 위 글에서" in between[0]


def test_join_keeps_separate_units():
    """새 구조 단위(선지·조건·발문 머리)는 앞줄에 붙지 않는다."""
    from engines.workbook.parser import _join_step3_split_paragraphs
    rows = _p("① be lowered by peer pressure",
              "② make you feel more confident",
              "• 필요 시 단어의 형태를 변형할 것",
              "3. 단어 수: 15단어",
              "위 글의 밑줄 친 ⓐ~ⓔ 중, 흐름상 어색한 것은?")
    assert _texts(_join_step3_split_paragraphs(rows)) == _texts(rows)


def test_join_stops_at_blank_and_answer_header():
    from engines.workbook.parser import _join_step3_split_paragraphs
    rows = _p("A long English sentence that fills the whole visual line and",
              "", "continues after a blank paragraph")
    assert len(_join_step3_split_paragraphs(rows)) == 3
    rows2 = _p("A long English sentence that fills the whole visual line and",
               "정답 및 해설")
    assert len(_join_step3_split_paragraphs(rows2)) == 2


# ── ① 발문 각주 번호 ────────────────────────────────────────────────────────

def test_strip_footnote_ref_only_when_number_matches():
    from engines.workbook.parser import _strip_step3_footnote_refs
    out = _texts(_strip_step3_footnote_refs(
        _p("155. 다음 글의 요지로 가장 적절한 것은?155)",
           "12. 다음 글의 빈칸에 들어갈 말은?12)[45]",
           "3. 다음 중 옳은 것은?9)")))
    assert out[0] == "155. 다음 글의 요지로 가장 적절한 것은?"
    assert out[1] == "12. 다음 글의 빈칸에 들어갈 말은?[45]"   # 꼬리 태그는 보존
    assert out[2] == "3. 다음 중 옳은 것은?9)"                 # 번호 불일치 — 보존


# ── ⓪ 워크시트 잔재 ────────────────────────────────────────────────────────

def test_strip_rights_notice_anywhere_and_book_title():
    from engines.workbook.parser import _strip_step3_rights_and_title
    out = _texts(_strip_step3_rights_and_title(
        _p("High School 수능만만 기본 문법어법어휘 150제 PART 01 09 관계사 Made by",
           "1. 다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?",
           "이 자료는 저작권의 보호를 받는 합법 저작물로 무단 배포 및 "
           "재판매할 수 없습니다. (SV-86065)",
           "2. 다음 글의 주제로 적절한 것은?")))
    assert out == ["1. 다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?",
                   "2. 다음 글의 주제로 적절한 것은?"]


def test_type_labels_need_prompt_after_and_finished_line_before():
    from engines.workbook.parser import _strip_step3_type_labels
    rows = _p("⑤ be damaged by how we see ourselves",
              "빈칸 추론",                       # 라벨 — 앞은 선지, 뒤는 발문
              "5. 다음 글의 빈칸에 들어갈 말은?",
              "- 한 칸당 하나의 단어를 적을 것",
              "필요시 어형 변화 가능",           # 조건 항목 — 앞줄이 조건이다
              "6. 다음 글의 주제로 적절한 것은?")
    out = _texts(_strip_step3_type_labels(rows))
    assert "빈칸 추론" not in out
    assert "필요시 어형 변화 가능" in out


def test_english_label_only_with_korean_label_convention():
    from engines.workbook.parser import _strip_step3_type_labels
    lone = _p("끝난 문장이다.", "Transformation", "1. 다음 글의 요지는?")
    assert "Transformation" in _texts(_strip_step3_type_labels(lone))
    with_conv = _p("끝난 문장이다.", "빈칸 추론", "1. 다음 글의 요지는?",
                   "또 끝난 문장이다.", "어휘 추론", "2. 다음 글의 주제는?",
                   "또또 끝난 문장이다.", "Implication & Content",
                   "3. 다음 글의 제목은?")
    out = _texts(_strip_step3_type_labels(with_conv))
    assert "빈칸 추론" not in out and "Implication & Content" not in out


# ── ⑦ 다열 선지 열 정렬 ────────────────────────────────────────────────────

def test_choice_grid_gets_tabs_but_single_row_does_not():
    from engines.workbook_v2.plan import normalize_choice_tabs
    def _plan(*rows):
        return {"flows": [{"step": "step3", "units": [[
            {"t": t, "s": "STEP 03 > S_선지 올림포스",
             "runs": [{"t": t, "ul": False}]} for t in rows]]}]}
    grid = _plan("① (A)-(C)-(B) ② (B)-(A)-(C)",
                 "③ (B)-(C)-(A) ④ (C)-(A)-(B)",
                 "⑤ (C)-(B)-(A)")
    assert normalize_choice_tabs(grid) == 2
    rows = grid["flows"][0]["units"][0]
    assert rows[0]["t"] == "① (A)-(C)-(B)\t② (B)-(A)-(C)"
    assert "\t" not in rows[2]["t"]
    single = _plan("① (A)  ② (B)  ③ (C)  ④ (D)  ⑤ (E)")
    assert normalize_choice_tabs(single) == 0   # 맞출 상대가 없는 한 줄
