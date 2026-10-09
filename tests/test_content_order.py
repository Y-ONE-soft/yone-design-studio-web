"""원고 읽는 순서 — core.units.content.slots (단이 있는 쪽은 단 순서)."""
from core.units import content


def box(name, x, y, w=80):
    return {"x": x, "y": y, "atom": {"t": "text", "bind": name, "w": w, "text": name}}


def names(pages, **kw):
    return [n for _, _, n, _ in content.slots(pages, **kw)]


def test_no_columns_top_then_left():
    pg = {"items": [box("a", 105, 30), box("b", 20, 40), box("c", 20, 30)]}
    assert names([pg]) == ["c", "a", "b"]


def test_two_columns_left_column_first():
    # 두 단(A4, 여백 20, 간격 5) — 왼쪽 단 문항이 오른쪽 단보다 아래에 있어도 먼저
    pg = {"margins": {"left": 20, "right": 20}, "columns": {"n": 2, "gutter": 5},
          "items": [box("q2", 107.5, 30), box("q1", 20, 30), box("q1b", 20, 120), box("q2b", 107.5, 60)]}
    assert names([pg]) == ["q1", "q1b", "q2", "q2b"]


def test_spanning_box_cuts_columns():
    # 가운데 높이에 두 단에 걸친 상자가 있으면: 위 칸(왼쪽 → 오른쪽) → 걸친 상자 → 아래 칸(왼쪽 → 오른쪽)
    pg = {"margins": {"left": 20, "right": 20}, "columns": {"n": 2, "gutter": 5},
          "items": [box("R1", 107.5, 30), box("L1", 20, 30), box("wide", 20, 140, w=170),
                    box("R2", 107.5, 160), box("L2", 20, 170)]}
    assert names([pg]) == ["L1", "R1", "wide", "L2", "R2"]


def test_fill_follows_reading_order():
    pg = {"margins": {"left": 20, "right": 20}, "columns": {"n": 2, "gutter": 5},
          "items": [box("발문", 107.5, 30), box("발문", 20, 200)]}
    pages, rep = content.fill([pg], {"발문": ["첫째", "둘째"]})
    assert pages[0]["items"][1]["fields"] == {"발문": "첫째"}       # 왼쪽 단(아래쪽이어도)
    assert pages[0]["items"][0]["fields"] == {"발문": "둘째"}
    assert rep["filled"] == 2


def test_number_hanging_over_column_edge_is_not_spanning():
    # 오른쪽 단 번호가 단 경계보다 1mm 왼쪽에서 시작해도 그 단 — 개체 폭(it.w)이 원자 폭(처음 그린 값)보다 먼저
    num = {"x": 105.93, "y": 27, "w": 13.8, "atom": {"t": "text", "bind": "번호", "w": 24, "text": "00"}}
    right = {"x": 106, "y": 33, "w": 81.9, "atom": {"t": "text", "bind": "오른쪽", "w": 60, "text": "x"}}
    pg = {"columns": {"n": 2, "gutter": 4}, "items": [num, box("왼쪽", 20, 160), right]}
    assert names([pg]) == ["왼쪽", "번호", "오른쪽"]
