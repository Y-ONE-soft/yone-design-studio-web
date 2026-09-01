# -*- coding: utf-8 -*-
"""시험범위 **정본 갈아 끼우기** 계약 검사 — 망 없이 돈다.

여기서 지키려는 것은 하나다: 범위를 적은 **글**에서 원고를 찾을 만큼의
정보를 잃지 않고 읽어 낸다. 실제 시험범위 시트(26-1-기말)의 글을 그대로
표본으로 쓴다 — 사람이 쓰는 말투가 곧 형식이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.final import scope_source as S      # noqa: E402


def t(text):
    return [S.token_text(x) for x in S.scope_text_tokens(text)]


def test_series_is_read_even_when_the_book_name_sits_between():
    """`올림포스 독해기본1 15~18강` — 사이에 교재 이름이 낀다."""
    assert t("* 올림포스 영어독해 기본1 10~12, 14~16강") == [
        "올림포스 10강", "올림포스 11강", "올림포스 12강",
        "올림포스 14강", "올림포스 15강", "올림포스 16강"]


def test_book_name_digits_are_not_unit_numbers():
    """`기본1` 의 1 은 강이 아니다 — `강` 으로 끝나는 묶음만 센다."""
    assert ("olpo", 1) not in S.scope_text_tokens("올림포스 영어독해 기본1 15강")


def test_parenthesis_is_publisher_not_scope():
    """파일 이름과 달리 글에서는 괄호가 범위가 아니다."""
    assert t("* 영어Ⅰ 미래엔(김) 4과") == ["교과서 4과"]


def test_star_starts_a_new_item():
    """`* … 3과 * … 4과` 를 한 도막으로 보면 뒤쪽 출판사를 잃는다."""
    sc = S.parse("* 공통영어1 능률(민) 3과 * 공통영어2 YBM(김) 4과(추가본문X)")
    assert sc["detail"][("lesson", 3)]["publisher"] == "능률(민)"
    assert sc["detail"][("lesson", 4)]["publisher"] == "YBM(김)"
    assert sc["detail"][("lesson", 4)]["subject"] == "공통영어2"
    assert "추가본문X" in sc["detail"][("lesson", 4)]["notes"]
    assert "notes" not in sc["detail"][("lesson", 3)]


def test_series_carries_over_the_slash():
    """`수능특강 영어 18강 … / 19강 … / 21~23강` — 계열은 한 번만 적는다."""
    got = S.scope_text_tokens(
        "* 수능특강 영어 18강 2, 4 / 19강 3~4, 7~8 / 21~23강 1, 3")
    assert got == [("teuk", 18), ("teuk", 19),
                   ("teuk", 21), ("teuk", 22), ("teuk", 23)]


def test_uppercase_test_counts():
    assert ("test", 2) in S.scope_text_tokens("TEST 2 (1, 8, 10~11번 제외)")


def test_mock_month_and_question_numbers_are_not_units():
    """`고2 25년 3월 18~45` 의 18~45 는 문항번호지 강이 아니다."""
    got = S.scope_text_tokens("* 고2 25년 3월 18~45")
    assert got == [("mock", 25, 3)]


def test_cross_check_ignores_the_series_prefix():
    """`18강`(접두 없음)과 `수능특강 18강` 은 같은 것이다."""
    a = {"tokens": [("teuk", 18)]}
    b = {"tokens": [("bare", 18)]}
    d = S.cross_check(a, b)
    assert d["only_a"] == [] and d["only_b"] == []


def test_cross_check_reports_a_real_difference():
    a = {"tokens": [("lesson", 4), ("rp", 12)]}
    b = {"tokens": [("rp", 12)]}
    assert S.cross_check(a, b)["only_a"] == [("lesson", 4)]


def test_workbook_filenames_still_work():
    """정본이 없을 때의 폴백은 그대로 둔다."""
    got = S.from_workbook_names(
        ["광문2_워크북01(리딩파워12강,14강)_내지.indd"])
    assert got["tokens"] == [("rp", 12), ("rp", 14)]
