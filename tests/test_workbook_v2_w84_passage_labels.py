"""W84 — 스텝마다 지문 구성이 다를 때의 지문번호 프레임 라벨.

사용자 지적(2026-08-31, 수능만만 09강): "본문으로 들어가야 되는 게 실전예제
045 이런 뒤에 걸로 들어가있어. 지문 번호가 안 맞아."

원인: 지문번호 프레임 갱신 op가 **공용 라벨 한 벌**을 모든 스텝에 그대로
썼다. 이 교재는 스텝1이 실전예제 4지문뿐인데 스텝2(어법 O/X·빈칸 어법)는
본문 2 + 실전예제 4라, 앞의 본문 두 자리에 '실전예제 045/046'이 박혔다.
"""


def _step(*texts):
    return {"paragraphs": [{"text": t} for t in texts]}


def _passage(n):
    return ("A long English passage sentence number %d that fills a line "
            "and keeps going for a while so the parser sees a body." % n)


def _supp_steps():
    """스텝1 = 실전예제 4지문(대괄호 라벨) / 스텝2 = 본문 2 + 실전예제 4."""
    a1 = []
    for i in (45, 46, 47, 48):
        a1 += ["[실전예제 %03d]" % i, _passage(i)]
    b1 = []
    for h in ("1. P60-본문", "2. P61-본문"):
        b1 += [h, _passage(1)]
    for k, i in enumerate((45, 46, 47, 48), start=3):
        b1 += ["%d. P65-N%03d" % (k, i), _passage(i)]
    return {"step1_a1": _step(*a1), "step2_b1": _step(*b1)}


def test_common_labels_are_step1_brackets():
    from engines.workbook_v2.plan import passage_labels
    assert passage_labels(_supp_steps()) == [
        "실전예제 045", "실전예제 046", "실전예제 047", "실전예제 048"]


def test_extra_head_passages_get_their_own_label():
    from engines.workbook_v2.plan import passage_labels_by_step
    by = passage_labels_by_step(_supp_steps(), ["step2_b1"])
    assert by["step2_b1"] == ["본문", "본문", "실전예제 045", "실전예제 046",
                              "실전예제 047", "실전예제 048"]


def test_positional_fallback_when_numbering_differs():
    """대괄호 라벨과 헤더의 번호 체계가 다른 원고(10강: 실전01 vs N049)."""
    from engines.workbook_v2.plan import passage_labels_by_step
    steps = _supp_steps()
    steps["step1_a1"] = _step(*sum(
        [["[실전%02d]" % i, _passage(i)] for i in (1, 2, 3, 4)], []))
    b1 = []
    for h in ("1. P66-본문", "2. P67-본문"):
        b1 += [h, _passage(1)]
    for k, i in enumerate((49, 50, 51, 52), start=3):
        b1 += ["%d. P70-N%03d" % (k, i), _passage(i)]
    steps["step2_b1"] = _step(*b1)
    by = passage_labels_by_step(steps, ["step2_b1"])
    assert by["step2_b1"] == ["본문", "본문", "실전01", "실전02",
                              "실전03", "실전04"]


def test_equal_count_step_is_left_alone():
    """지문 수가 같으면 공용 라벨이 이미 맞다 — 표기를 흔들지 않는다.

    (비상 'Extended Reading' 계열이 'Main Reading'으로 바뀌던 회귀 방지)"""
    from engines.workbook_v2.plan import passage_labels_by_step
    steps = _supp_steps()
    b1 = []
    for k, i in enumerate((45, 46, 47, 48), start=1):
        b1 += ["%d. P65-N%03d" % (k, i), _passage(i)]
    steps["step2_b1"] = _step(*b1)
    assert passage_labels_by_step(steps, ["step2_b1"]) == {}


def test_head_repeating_common_label_is_skipped():
    """앞머리가 공용 라벨과 같은 지문이면 헤더 추출이 어긋난 것 — 무접촉."""
    from engines.workbook_v2.plan import passage_labels_by_step
    steps = _supp_steps()
    b1 = []
    for k, i in enumerate((45, 46, 45, 46, 47, 48), start=1):
        b1 += ["%d. P65-N%03d" % (k, i), _passage(i)]
    steps["step2_b1"] = _step(*b1)
    assert passage_labels_by_step(steps, ["step2_b1"]) == {}
