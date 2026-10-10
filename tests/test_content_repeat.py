"""「원고마다」 묶음 되풀이 — core.units.content.plan_pages + fill (인디자인 데이터 병합의 레코드처럼)."""
from core.units import content


def box(name, y=30):
    return {"x": 20, "y": y, "atom": {"t": "text", "bind": name, "w": 80, "text": "임시 " + name}}


PAGES = {
    "cov": {"id": "cov", "name": "표지", "items": [box("교재명")]},
    "L": {"id": "L", "name": "A1 왼쪽", "items": [box("지문 번호")]},
    "R": {"id": "R", "name": "A1 오른쪽", "items": [box("지문"), box("지문", 120)]},
    "end": {"id": "end", "name": "뒷면", "items": []},
}
PLAN = {"front": ["cov"], "sections": [{"id": "s1", "pages": [{"page": "L", "repeat": "each_set"}, {"page": "R", "repeat": "each_set"}]}],
        "back": ["end"]}


def text_of(pg):
    return [list(it["fields"].values())[0] for it in pg["items"] if it.get("fields")]


def test_run_repeats_per_record():
    data = {"교재명": "공통영어", "A1 왼쪽": [{"지문 번호": "01", "지문": ["가", "나"]}, {"지문 번호": "02", "지문": ["다", "라"]}]}
    pages = content.plan_pages(PLAN, PAGES, data)
    assert [p["id"] for p in pages] == ["cov", "L", "R", "L~2", "R~2", "end"]
    filled, rep = content.fill(pages, data)
    assert [text_of(p) for p in filled] == [["공통영어"], ["01"], ["가", "나"], ["02"], ["다", "라"], []]
    assert rep["unknown"] == [] and rep["filled"] == 7


def test_no_records_once():
    pages = content.plan_pages(PLAN, PAGES, {"교재명": "x"})
    assert [p["id"] for p in pages] == ["cov", "L", "R", "end"]
    assert all("_rec" not in p for p in pages)


def test_template_untouched():
    content.plan_pages(PLAN, PAGES, {"A1 왼쪽": [{"지문 번호": "1"}, {"지문 번호": "2"}]})
    assert PAGES["L"]["id"] == "L" and "_rec" not in PAGES["L"]


def test_adjacent_runs_split_by_named_page():
    pages = dict(PAGES, L2={"id": "L2", "name": "A2 왼쪽", "items": [box("지문 번호")]})
    plan = {"sections": [{"id": "s1", "pages": [{"page": p, "repeat": "each_set"} for p in ("L", "R", "L2")]}]}
    data = {"A1 왼쪽": [{"지문 번호": "1"}, {"지문 번호": "2"}], "A2 왼쪽": [{"지문 번호": "9"}]}
    out = content.plan_pages(plan, pages, data)
    assert [p["id"] for p in out] == ["L", "R", "L~2", "R~2", "L2"]
    filled, _ = content.fill(out, data)
    assert [text_of(p) for p in filled] == [["1"], [], ["2"], [], ["9"]]
