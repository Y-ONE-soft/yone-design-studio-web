"""도표만 모은 분석본(배재2 분석본04 `23년9월,도표`)에서 온 모의고사 지문.

라벨이 회차(`고2 24년 9월`)로 잡혀 짤지문 판정이 안 되고 책 끝에 붙었다.
"""
from core.render_vivlio.series.pocketbook import (
    _mark_short, _mock_label, _order_mock_rounds)


def _m(pno, label, chapter="", cat=None):
    return {"kind": "passage", "pno": pno, "label": label, "chapter": chapter, "_rank": 2,
            "category": cat or "고2 %s년 %d월 모의고사" % (pno[:2], int(pno[2:4]))}


def test_chart_passage_label_from_chapter_becomes_short_and_moves():
    rows = [_m("240924", "24번"), _m("240929", "29번"), _m("250924", "24번"),
            _m("250929", "29번"), _m("240925", "고2 24년 9월", "25번"),
            _m("250925", "고2 25년 9월", "25번")]
    log = []
    _mark_short(rows, {}, log.append)
    _mock_label(rows, log.append)
    _order_mock_rounds(rows, log.append)
    assert [r["label"] for r in rows] == ["240924", "240925", "240929",
                                         "250924", "250925", "250929"]
    assert [bool(r.get("short")) for r in rows] == [False, True, False, False, True, False]


def test_round_order_keeps_first_appearance():
    rows = [_m("250920", "250920"), _m("240920", "240920"), _m("230920", "230920")]
    _order_mock_rounds(rows, lambda *_: None)
    assert [r["pno"] for r in rows] == ["250920", "240920", "230920"]


def test_non_mock_chapter_label_untouched():
    rows = [{"kind": "passage", "label": "1강 01", "chapter": "1번", "category": "수능특강 1강",
             "_rank": 1, "pno": ""}]
    _mark_short(rows, {}, lambda *_: None)
    assert rows[0]["label"] == "1강 01" and not rows[0].get("short")


def test_textbook_rows_between_mocks_stay_put():
    tb = {"kind": "passage", "label": "1과 본문1", "category": "교과서 1과", "_rank": 1}
    rows = [tb, _m("240929", "240929"), _m("240925", "240925")]
    _order_mock_rounds(rows, lambda *_: None)
    assert rows[0] is tb and [r["pno"] for r in rows[1:]] == ["240925", "240929"]
