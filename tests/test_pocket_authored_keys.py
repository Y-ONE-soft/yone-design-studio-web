"""저술물(오른쪽 면)을 지문에 붙일 때 쓰는 **이름** — 실제로 안 붙었던 자리.

  · 모의고사 라벨은 저술물을 얹은 **뒤에** 여섯 자리로 통일된다(`38번`→`250938`).
    통일 뒤 이름으로 저장하면 안 붙는다 — 배재1 32개 중 13개만 붙었다.
  · 한 책에 회차가 둘이면(배재2: 24년9월·25년9월) `38번` 이 **겹친다**.
    겹친 이름으로 찾으면 다른 회차 지문에 같은 플로우노트가 인쇄된다.
  · 그래서 지문번호(`pno`)로도 찾는다 — 회차가 들어 있어 겹치지 않는다.
"""
from core.render_vivlio.series.pocketbook import _label_keys


def test_pno_is_one_of_the_keys():
    keys = _label_keys({"label": "38번", "pno": "250938"}, "모의고사")
    assert "250938" in keys and "38번" in keys


def test_same_label_two_rounds_are_told_apart():
    a = _label_keys({"label": "38번", "pno": "240938"}, "모의고사")
    b = _label_keys({"label": "38번", "pno": "250938"}, "모의고사")
    assert set(a) != set(b)
    assert "240938" in a and "250938" in b


def test_textbook_row_unchanged():
    assert _label_keys({"label": "1과 본문1", "pno": ""}, "교과서 1과") == ["1과 본문1"]


def test_lecture_label_still_corrected():
    # 부교재 분석 지문 — 교정 뒤 이름(`7강 분석`)도 같이 써 본다
    keys = _label_keys({"label": "분석", "pno": ""}, "올림포스 7강")
    assert "7강 분석" in keys
