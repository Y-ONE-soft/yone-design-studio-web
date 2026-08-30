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


# ── 편집 이력 (edits.py) ─────────────────────────────────────────
class _Cfg(object):
    def __init__(self, d):
        self.d = d

    def path(self, n):
        import os
        return os.path.join(self.d, n)


@pytest.fixture
def book(tmp_path):
    import json as J
    data = {"lessons": [{"problems": [
        {"no": 1, "stem": "원래 발문",
         "blocks": [{"paras": ["가나다 라마바", "사아자"]}]}]}]}
    (tmp_path / "data.json").write_text(J.dumps(data, ensure_ascii=False),
                                        encoding="utf-8")
    return _Cfg(str(tmp_path))


P = "lessons.0.problems.0.blocks.0.paras"


def _paras(cfg):
    from core.render_vivlio import edits as ed
    return ed.load_data(cfg)["lessons"][0]["problems"][0]["blocks"][0]["paras"]


def test_set_and_undo_restores_original(book):
    """되돌리면 **원고 그대로**로 돌아와야 한다 — 이게 없으면 아무도 못 쓴다."""
    from core.render_vivlio import edits as ed
    ed.push(book, {"op": "set", "ref": P + ".0", "v": "고친 것"})
    assert _paras(book)[0] == "고친 것"
    ed.undo(book)
    assert _paras(book)[0] == "가나다 라마바"


def test_redo(book):
    from core.render_vivlio import edits as ed
    ed.push(book, {"op": "set", "ref": P + ".0", "v": "고친 것"})
    ed.undo(book)
    ed.redo(book)
    assert _paras(book)[0] == "고친 것"


def test_new_edit_after_undo_truncates(book):
    """되돌린 뒤 새로 고치면 앞으로 갈 것은 잘린다(편집기 관례)."""
    from core.render_vivlio import edits as ed
    ed.push(book, {"op": "set", "ref": P + ".0", "v": "첫째"})
    ed.push(book, {"op": "set", "ref": P + ".0", "v": "둘째"})
    ed.undo(book)
    st = ed.push(book, {"op": "set", "ref": P + ".0", "v": "셋째"})
    assert st["head"] == len(st["ops"]) == 2
    assert _paras(book)[0] == "셋째"
    ed.undo(book)
    assert _paras(book)[0] == "첫째"


def test_structure_ops(book):
    """문단 나누기·합치기·넣기·지우기 — 값 표로는 담을 수 없던 것들."""
    from core.render_vivlio import edits as ed
    ed.push(book, {"op": "split", "ref": P + ".0", "at": 3})
    assert _paras(book) == ["가나다", "라마바", "사아자"]
    ed.push(book, {"op": "merge", "ref": P + ".0"})
    assert _paras(book) == ["가나다 라마바", "사아자"]
    ed.push(book, {"op": "insert", "ref": P + ".1", "v": "끼운 단락"})
    assert _paras(book) == ["가나다 라마바", "끼운 단락", "사아자"]
    ed.push(book, {"op": "delete", "ref": P + ".1"})
    assert _paras(book) == ["가나다 라마바", "사아자"]
    for _ in range(4):
        ed.undo(book)
    assert _paras(book) == ["가나다 라마바", "사아자"]


def test_missing_ref_warns_not_silent(book):
    """원고가 바뀌어 자리가 사라지면 **조용히 넘기지 않는다**."""
    from core.render_vivlio import edits as ed
    ed.push(book, {"op": "set", "ref": P + ".9", "v": "x"})
    lines = []
    ed.load_data(book, log=lines.append)
    assert any("자리를 못 찾" in x for x in lines)


def test_migrates_old_errata(book):
    """예전 값 표(errata.json)는 처음 읽을 때 연산으로 옮겨진다."""
    import json as J
    import os
    from core.render_vivlio import edits as ed
    with open(os.path.join(book.d, "errata.json"), "w", encoding="utf-8") as f:
        J.dump({"_note": "x", P + ".0": "옛 정오표"}, f, ensure_ascii=False)
    assert _paras(book)[0] == "옛 정오표"
    st = ed.read(book)
    assert st["head"] == 1 and st["ops"][0]["op"] == "set"
