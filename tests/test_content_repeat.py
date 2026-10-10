import json
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


def test_record_spans_spread():
    """한 레코드가 펼침면 두 쪽에 걸치면 목록은 왼쪽 → 오른쪽으로 이어 꺼내고, 글 하나는 두 쪽 모두에"""
    pages = {"L": {"id": "L", "name": "A1", "items": [box("제목", 5), box("번호"), box("번호", 120)]},
             "R": {"id": "R", "name": "A1 오른쪽", "items": [box("번호"), box("번호", 120), box("제목", 5)]}}
    plan = {"sections": [{"id": "s1", "pages": [{"page": p, "repeat": "each_set"} for p in ("L", "R")]}]}
    data = {"A1": [{"제목": "어휘 1", "번호": ["2", "4", "6", "8"]}, {"제목": "어휘 2", "번호": ["10", "12", "14", "16"]}]}
    filled, rep = content.fill(content.plan_pages(plan, pages, data), data)
    assert [text_of(p) for p in filled] == [["어휘 1", "2", "4"], ["6", "8", "어휘 1"], ["어휘 2", "10", "12"], ["14", "16", "어휘 2"]]
    assert rep["unfilled"] == {}


def test_fold_group_when_slot_blank():
    """접기 묶음 — 원고가 비운 자리의 묶음은 안 그리고 그 띠만큼 아래 것을 끌어올린다(빈 필드 줄 제거)"""
    from core.units import render

    def it(name, y, h, fold=None, bind=True):
        a = {"t": "text", "w": 150, "h": h, "text": "임시"}
        if bind:
            a["bind"] = name
        if fold:
            a["fold"] = fold
        return {"x": 20, "y": y, "atom": a}
    page = {"id": "P", "name": "A2", "items": [it("지문", 30, 20), it("번호", 60, 5, "q1", bind=False), it("선지", 66, 20, "q1"),
                                               it("발문", 95, 5), it("진술", 102, 8)]}
    filled, _ = content.fill([page], {"지문": "글", "선지": "", "발문": "물음", "진술": "문장"})
    assert filled[0]["items"][2].get("_empty") and not filled[0]["items"][3].get("_empty")
    folded, bands = render.fold_bands(filled[0])
    assert folded == {1, 2}
    assert len(bands) == 1 and abs(bands[0][4] + 35) < 1e-6            # 띠 위(60) → 아래 첫 요소(95): 35mm 끌어올림
    ok, _ = content.fill([page], {"지문": "글", "선지": "① 하나", "발문": "물음", "진술": "문장"})
    assert render.fold_bands(ok[0]) == (set(), [])                     # 원고가 있으면 그대로


def test_fold_attached_keeps_gap_below():
    """위 상자에 붙은 묶음(주석)이 접히면 제 높이만 걷힌다 — 아래 틈은 남는다"""
    from core.units import render

    def it(name, y, h, fold=None):
        a = {"t": "text", "w": 150, "h": h, "text": "임시", "bind": name}
        if fold:
            a["fold"] = fold
        return {"x": 20, "y": y, "atom": a}
    page = {"id": "P", "items": [it("지문", 30, 20), it("주석", 50, 8, "주석"), it("선지", 64, 20)]}
    filled, _ = content.fill([page], {"지문": "글", "주석": "", "선지": "①"})
    folded, bands = render.fold_bands(filled[0])
    assert folded == {1} and abs(bands[0][4] + 8) < 1e-6              # 주석 높이 8 만 — 선지 위 틈 6 은 그대로


def test_flow_per_page_share():
    """흐르는 글상자(글 잇기 안 함)가 펼침면 쪽마다 제 몫의 문항 목록을 받는다"""
    flow = lambda: {"x": 20, "y": 30, "atom": {"t": "text", "bind": "번호+문장", "w": 150, "text": "임시"}}
    pages = {"L": {"id": "L", "name": "C2", "items": [flow()]}, "R": {"id": "R", "name": "C2 오른쪽", "items": [flow()]}}
    plan = {"sections": [{"id": "s1", "pages": [{"page": p, "repeat": "each_set"} for p in ("L", "R")]}]}
    rec = {"번호+문장": [[{"번호": "01", "문장": "가"}, {"번호": "02", "문장": "나"}], [{"번호": "03", "문장": "다"}]]}
    filled, rep = content.fill(content.plan_pages(plan, pages, {"C2": [rec]}), {"C2": [rec]})
    flat = lambda pg: json.dumps(pg["items"][0]["fields"], ensure_ascii=False)
    assert "가" in flat(filled[0]) and "나" in flat(filled[0]) and "다" not in flat(filled[0])
    assert "다" in flat(filled[1]) and "가" not in flat(filled[1])
    assert rep["filled"] == 3
    assert not content.per_occurrence([[["번호", "01"], ["문장", "가"]]])          # 문항 하나가 [자리, 글] 목록인 꼴은 몫이 아니다
