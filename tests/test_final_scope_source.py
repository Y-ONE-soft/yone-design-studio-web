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


# ── Y.OS 구조화 입력 ────────────────────────────────────────────────────
#
# 아래 문자열은 Y.OS `/work/exam` 화면에서 그대로 가져온 실제 값이다.
def test_yos_book_name_to_folder_name():
    """`공통영어2_NE능률민병천` — Y.OS 는 붙여 쓰고 원고 폴더는 `능률(민)`."""
    assert S.normalize_book("공통영어2_NE능률민병천") == ("공통영어2", "능률(민)")
    assert S.normalize_book("공통영어1_NE능률오준일") == ("공통영어1", "능률(오)")


def test_yos_latin_publisher_is_not_a_brand_prefix():
    """`NE능률…` 의 NE 는 버리지만 `YBM박준언` 의 YBM 은 출판사다."""
    assert S.normalize_book("영어II_YBM박준언") == ("영어Ⅱ", "YBM(박)")
    assert S.normalize_book("공통영어2_YBM김은형") == ("공통영어2", "YBM(김)")


def test_lesson_ranges_split_at_the_lesson_head():
    got = S.lesson_ranges(
        "Lesson 1. Bonding with Others 1~9, "
        "Lesson 2. What Keeps Us Moving Forward 1~12")
    assert got == {1: list(range(1, 10)), 2: list(range(1, 13))}


def test_unit_ranges_do_not_bleed_across_the_comma():
    """`08 1~5, 09 1~5` — 쉼표를 넘어가면 8강이 9,10 까지 삼킨다."""
    got = S.unit_ranges("08 1~5, 09 1~5, 10 1~5")
    assert [(u["no"], u["nums"]) for u in got] == [
        (8, [1, 2, 3, 4, 5]), (9, [1, 2, 3, 4, 5]), (10, [1, 2, 3, 4, 5])]


def test_unit_ranges_read_by_position_not_by_shape():
    """Y.OS 실제 값 — 맨 뒤 숫자 묶음이 지문, 그 앞 마지막 숫자가 강.

    지문수(Y.OS 가 센 값)와 맞춰 본 것이라 숫자에 근거가 있다.
    """
    got = S.unit_ranges(
        "08 1~5, 09 1~5, 10 1~5, 11 1~5, 12 1~5, "
        "Mini Test 1 2~5, 12~17, 19~23, Mini Test 2 4~7, 12~16")
    assert sum(len(u["nums"]) for u in got) == 49          # Y.OS: 49지문
    assert [u["name"] for u in got][-2:] == ["Mini Test", "Mini Test"]

    got2 = S.unit_ranges(
        "(PART 01) 09 관계사 1~4, (PART 01) 10 형용사 · 부사 · 비교 구문 1~4, "
        "(PART 01) 11 접속사와 전치사 1~4, (PART 01) 12 주의할 구문 1~4")
    assert sum(len(u["nums"]) for u in got2) == 16         # Y.OS: 16지문
    assert [u["no"] for u in got2] == [9, 10, 11, 12]      # PART 01 은 강이 아니다


def test_mini_test_is_a_round_not_a_unit():
    sc = S.from_yos_entries(
        [("부교재", "수능특강 Light 영어독해연습(2025.10)",
          "08 1~5, Mini Test 1 2~5", "9지문")], grade=2)
    assert ("teuk", 8) in sc["tokens"] and ("test", 1) in sc["tokens"]


def test_yos_entries_carry_the_passage_level_limit():
    """글로 받던 시절의 마지막 구멍 — 지문 번호가 항목에 들어 있다."""
    sc = S.from_yos_entries([
        ("교과서", "공통영어2_NE능률민병천",
         "Lesson 1. Bonding with Others 1~9, Lesson 2. X 1~12", "21지문"),
        ("모의고사", "고1_2024_09월(인천시)", "15~18, 20~24", "9지문"),
    ], grade=1)
    assert sc["detail"][("lesson", 1)]["only"] == list(range(1, 10))
    assert sc["detail"][("mock", 24, 9)]["only"] == [15, 16, 17, 18,
                                                     20, 21, 22, 23, 24]


def test_yos_mock_keeps_its_own_grade():
    """고2 반이 고1 회차를 쓴다 — 회차의 학년은 반의 학년이 아니다."""
    sc = S.from_yos_entries(
        [("모의고사", "고1_2026_06월", "14~17", "4지문")], grade=2)
    assert sc["detail"][("mock", 26, 6)]["grade"] == 1


def test_yos_freeform_entry_falls_back_to_prose():
    sc = S.from_yos_entries(
        [("직접 입력", "* 영어Ⅰ 미래엔(김) 4과 / * 고2 25년 3월 18~45", "0지문")],
        grade=2)
    assert ("lesson", 4) in sc["tokens"] and ("mock", 25, 3) in sc["tokens"]


def test_count_gate_catches_a_misread_range():
    """지문수 대조 — Y.OS 가 센 값과 내가 읽은 값이 다르면 잡는다."""
    good = [("부교재", "수능특강 Light", "08 1~5, 09 1~5", "10지문")]
    assert S.count_gate(good, {"grade": 2}) == []
    bad = [("부교재", "수능특강 Light", "08 1~5", "49지문")]
    assert S.count_gate(bad, {"grade": 2}) == [
        {"book": "수능특강 Light", "want": 49, "got": 5}]


def test_count_gate_skips_freeform():
    """`직접 입력` 은 Y.OS 도 0지문이라 셀 수 없다 — 그것 자체가 신호다."""
    assert S.count_gate([("직접 입력", "교과서 1과", "0지문")], {}) == []


def test_parenthesised_exclusions():
    """`(24-3, 27-3 제외)` — 강-지문 짝. 실제 광문3 시험범위 글."""
    sc = S.parse("* 수능특강 영어 17, 18, 21~30강(24-3, 27-3 제외), "
                 "TEST 2 (1, 8, 10~11, 24~28번 제외)", grade=3)
    assert sc["detail"][("teuk", 27)]["exclude"] == [3]
    assert sc["detail"][("teuk", 26)].get("exclude") is None
    assert S.in_scope("27강 02", sc) and not S.in_scope("27강 03", sc)


def test_plain_exclusions_attach_to_the_nearest_token():
    """맨 숫자 제외는 **바로 앞** 것(Test 2)의 몫이지 앞 강들의 것이 아니다."""
    sc = S.parse("* 수능특강 영어 21~23강, TEST 2 (1, 8, 10~11번 제외)", grade=3)
    assert sc["detail"][("test", 2)]["exclude"] == [1, 8, 10, 11]
    assert sc["detail"].get(("teuk", 21), {}).get("exclude") is None
    assert not S.in_scope("test2 01", sc) and S.in_scope("test2 03", sc)


def test_reading_power_carries_no_vocabulary():
    """리딩파워는 중요어휘를 싣지 않는다(사용자 확정).

    시트에는 데이터가 있어서 강 목록을 넘기면 딸려 온다 — 광문2 가 18→54
    지문으로 부풀었다. 올포는 반대로 **싣는다**(상일1 완성본).
    """
    import inspect
    from engines.final import assemble
    src = inspect.getsource(assemble.vocab)
    assert "rp_lectures=None" in src


def test_tokens_come_out_in_book_order():
    """범위 글의 **적힌 순서**를 그대로 따르면 안 된다.

    `17, 18, 21~30강` 은 범위가 먼저 풀려 21~30 이 앞에 온다 — 그러면
    어법·어휘 섹션만 21강부터 시작해 문장배열과 어긋난다(실증: 광문3).
    """
    got = S.scope_text_tokens(
        "* 수능특강 영어 17, 18, 21~24강, TEST 2")
    assert got == [("teuk", 17), ("teuk", 18), ("teuk", 21), ("teuk", 22),
                   ("teuk", 23), ("teuk", 24), ("test", 2)]


def test_book_order_is_textbook_then_units_then_mock():
    got = S.scope_text_tokens(
        "* 고2 25년 3월 / * Reading Power 유형편 완성 14~15, 12강 "
        "/ * 영어Ⅰ 미래엔(김) 4과")
    assert got == [("lesson", 4), ("rp", 12), ("rp", 14), ("rp", 15),
                   ("mock", 25, 3)]
