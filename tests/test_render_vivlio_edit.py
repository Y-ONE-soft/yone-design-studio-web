"""클릭 편집의 두 축 — 서식 왕복(richtext)과 정오표(errata). 오프라인.

여기서 지켜야 하는 것은 하나다: **글자를 고치다가 서식을 잃지 않을 것.**
어법 문제는 밑줄이 곧 문제라서, 민글로 받았다 되돌리면 글자는 맞는데 문제가
망가진다(특강에서 이미 겪었다). 그래서 왕복을 기계로 못박는다.
"""
import json

import pytest

from core.render_vivlio import errata as er
from core.render_vivlio import richtext as rt


# ── richtext ────────────────────────────────────────────────────
CASES = [
    "그냥 민글",
    ["앞 ", {"t": "밑줄", "u": True}, " 뒤"],
    ["앞 ", {"t": "굵게", "b": True}, " 뒤"],
    [{"t": "굵고 밑줄", "b": True, "u": True}],
    ["a ", {"t": "b", "i": True}, " c ", {"t": "d", "u": True}],
]


@pytest.mark.parametrize("rich", CASES)
def test_roundtrip_keeps_meaning(rich):
    """폈다 되접으면 **글자도 서식도** 같아야 한다."""
    text = rt.to_text(rich)
    back = rt.from_text(text, like=rich)
    assert rt.plain(back) == rt.plain(rich)
    assert rt.to_text(back) == text


def test_plain_stays_plain():
    """민글은 민글로 — 모양이 바뀌면 data.json 이 달라져 회귀가 시끄러워진다."""
    assert rt.from_text("그냥 민글", like="원래 민글") == "그냥 민글"
    assert isinstance(rt.from_text("가나다", like="x"), str)


def test_marks_render():
    assert rt.to_text(["a ", {"t": "b", "u": True}]) == "a __b__"
    assert rt.to_text([{"t": "b", "b": True}]) == "**b**"
    assert rt.to_text([{"t": "b", "i": True}]) == "//b//"


def test_literal_marks_escape():
    """글자 그대로의 `**` 는 표시로 오해되면 안 된다."""
    rich = "곱셈 ** 별표 __ 밑줄"
    text = rt.to_text(rich)
    assert rt.from_text(text, like=rich) == rich


def test_underline_survives_edit():
    """밑줄 안 글자만 고쳐도 밑줄이 남는다 — 이 검사가 이 파일의 핵심이다."""
    rich = ["다음 ", {"t": "밑줄 친", "u": True}, " 부분"]
    text = rt.to_text(rich).replace("밑줄 친", "밑줄친")
    back = rt.from_text(text, like=rich)
    assert any(isinstance(s, dict) and s.get("u") for s in back), "밑줄이 사라졌다"
    assert rt.plain(back) == "다음 밑줄친 부분"


# ── errata ──────────────────────────────────────────────────────
DATA = {"lessons": [{"problems": [{"no": 1, "stem": "원래 발문",
                                   "blocks": [{"paras": ["가", "나"]}]}]}]}


def test_get_walks_lists_and_dicts():
    assert er.get(DATA, "lessons.0.problems.0.stem") == "원래 발문"
    assert er.get(DATA, "lessons.0.problems.0.blocks.0.paras.1") == "나"
    assert er.get(DATA, "lessons.9.problems.0.stem", "없음") == "없음"


def test_apply_overwrites_only_listed():
    d = json.loads(json.dumps(DATA))
    er.apply(d, {"lessons.0.problems.0.stem": "고친 발문"})
    assert d["lessons"][0]["problems"][0]["stem"] == "고친 발문"
    assert d["lessons"][0]["problems"][0]["blocks"][0]["paras"] == ["가", "나"]


def test_apply_reports_missing(capsys):
    """자리가 사라지면 **조용히 넘기지 않는다** — '고쳤는데 왜 안 바뀌지'를 막는다."""
    d = json.loads(json.dumps(DATA))
    lines = []
    er.apply(d, {"lessons.0.problems.5.stem": "x"}, log=lines.append)
    assert any("자리를 못 찾은" in x for x in lines)


def test_exists():
    assert er.exists(DATA, "lessons.0.problems.0.stem")
    assert not er.exists(DATA, "lessons.0.problems.0.없는것")
