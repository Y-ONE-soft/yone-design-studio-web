"""W91 — 영작배열 지문기호형 헤더 ("1. p62-A") 인식.

사용자 지적 2026-09-05 (job 145aeaaa 수능만만 09~10강): "영작배열에
지문번호가 왜 없어?" — 지면에 지문 구분 없이 4문항이 통으로 실렸다.

뿌리: 이 교재의 지문 헤더는 페이지 마커 뒤가 **한 글자 지문기호**다
("1. p62-A"). legacy 헤더 패턴은 pN- 뒤에 숫자나 두 글자 이상의 낱말을
요구해 이 꼴만 통째로 놓쳤고, 빈칸어법·어법OX는 헤더 뒤가 영어 본문이라
구조 인식기(body_next)가 대신 잡았지만 영작배열은 헤더 뒤가 한글 해석이라
구조 신호도 없어 헤더 0개 → 유닛 1개 + 라벨 0개가 됐다 (W67이 만든
bracket 폴백도 헤더가 0이면 발동하지 않는다).
"""
import json


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def test_legacy_header_pattern_accepts_letter_code():
    from engines.workbook_v2.plan import is_header_line, _norm_header
    for t in ("1. p62-A", "2. p68-C", "3. p100-B"):
        assert is_header_line(_norm_header(t)), t


def test_letter_code_pattern_does_not_swallow_body():
    """본문 문장·기존 표기는 건드리지 않는다."""
    from engines.workbook_v2.plan import is_header_line, _norm_header
    for t in ("p62-A는 무엇인가", "1. p50-no.01", "The p62-A sample"):
        legacy = is_header_line(_norm_header(t))
        if t == "1. p50-no.01":
            assert legacy                     # 기존 no.형 — 종전대로 헤더
        else:
            assert not legacy, t


def test_c2_units_split_and_label_paragraph():
    """헤더가 인식되면 유닛이 지문 수만큼 갈리고 [라벨] 단락이 앞에 선다."""
    from engines.workbook_v2.plan import build_step2_c2
    data = {"paragraphs": _p(
        "1. p62-C",
        "그렇게 하면 신체가 유당을 혈액으로 흡수하기가 더 쉬워진다.",
        "( easier / doing so / makes / it ) ( to / lactose / absorb ).",
        "2. p68-C",
        "저지방 식단은 섭취 열량을 줄이는 데 도움을 주기 위한 것이다.",
        "( consumed / the amount of calories / reduce / a low-fat diet ).")}
    flow = build_step2_c2(data)
    units = flow["units"]
    assert len(units) == 2
    for u in units:
        paras = u["paragraphs"] if isinstance(u, dict) else u
        assert paras[0]["t"] == "[C]"



def test_c2_regression_job_145aeaaa():
    """실물 원고(job 145aeaaa 영작배열) — 통짜 1유닛 → 지문 2유닛."""
    import os
    path = os.path.join("jobs", "145aeaaa", "content.json")
    if not os.path.exists(path):
        return                                  # 잡 보관본이 없으면 생략
    from engines.workbook_v2.plan import build_step2_c2
    with open(path, encoding="utf-8") as fh:
        steps = json.load(fh)["steps"]
    flow = build_step2_c2(steps["step2_c2"])
    assert len(flow["units"]) == 2
    heads = [(u["paragraphs"] if isinstance(u, dict) else u)[0]["t"]
             for u in flow["units"]]
    assert heads == ["[C]", "[C]"]
