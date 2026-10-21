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


def test_bare_records_pick_named_face_in_order():
    # order: data — 덩어리의 「_면」이 고른 면으로, 원고 차례 그대로. 앞뒤 「한 번만」 쪽은 안 찍고, 이름 없는 이어지는 쪽(빈 면 N)은 앞 면의 한 벌
    pages = {
        "cov": {"id": "cov", "name": "속표지", "items": [box("교재명", 20, 20)]},
        "a": {"id": "a", "name": "A", "items": [box("지문", 20, 20)]},
        "a2": {"id": "a2", "name": "빈 면 2", "items": [box("지문", 20, 20)]},
        "b": {"id": "b", "name": "B", "items": [box("지문", 20, 20)]},
        "end": {"id": "end", "name": "뒤표지", "items": []},
    }
    sec = {"pages": [{"page": "cov", "repeat": "once"}, {"page": "a", "repeat": "each_set"}, {"page": "a2", "repeat": "each_set"},
                     {"page": "b", "repeat": "each_set"}, {"page": "end", "repeat": "once"}]}
    recs = {"원고": [{"지문": ["1"], "_면": "B"}, {"지문": ["1", "2"], "_면": "A"}]}
    out = content.plan_pages({"sections": [sec], "bare": True}, pages, recs)
    assert [p["name"] for p in out] == ["B", "A", "빈 면 2"]
    out = content.plan_pages({"sections": [sec]}, pages, recs)        # bare 가 아니면 예전처럼 앞뒤 쪽까지
    assert out[0]["name"] == "속표지" and out[-1]["name"] == "뒤표지"


def test_bare_once_story_page_is_a_face():
    # order: data — 「한 번만」 쪽이라도 글 잇기 첫 상자에 원고 자리(한 줄기 「a+b」)가 있으면 면, 이어 받는 쪽은 그 면에 붙고 덧쪽 표시(_spare)
    head = {"x": 20, "y": 20, "atom": {"t": "text", "bind": "번호+발문", "story": "s1", "story_seq": 1, "w": 80, "text": "x"}}
    cont = {"x": 20, "y": 20, "atom": {"t": "text", "story": "s1", "story_seq": 2, "w": 80, "text": ""}}
    pages = {"a": {"id": "a", "name": "A", "items": [box("지문", 20, 20)]},
             "s": {"id": "s", "name": "S실전", "items": [head]}, "s2": {"id": "s2", "name": "S실전 오른쪽", "items": [cont]},
             "m": {"id": "m", "name": "MEMO", "items": []}}
    sec = {"pages": [{"page": "a", "repeat": "each_set"}, {"page": "s", "repeat": "once"}, {"page": "s2", "repeat": "once"}, {"page": "m", "repeat": "once"}]}
    recs = {"원고": [{"번호+발문": [[["번호", "01"]]], "_면": "S실전"}, {"지문": ["1"], "_면": "A"}, {"번호+발문": [[["번호", "02"]]], "_면": "S실전"}]}
    out = content.plan_pages({"sections": [sec], "bare": True}, pages, recs)
    assert [p["name"] for p in out] == ["S실전", "S실전 오른쪽", "A", "S실전", "S실전 오른쪽"]
    assert [p.get("_spare") for p in out] == [None, "s1", None, None, "s1"]
