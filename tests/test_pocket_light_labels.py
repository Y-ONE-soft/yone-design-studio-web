"""수능특강 Light 라벨 — 광문2 연구원 검수(2026-09-14).

  · `N강 분석` → `N강 01` 로 바꾸고 `N강 02` **앞**으로(분석본은 맨 뒤에 둔다)
  · `5~6번` → `N강 05~06`
  · 올림포스처럼 분석과 01 이 따로 있는 책은 그대로
"""
from core.render_vivlio.series.pocketbook import _fix_lecture_label

LIGHT = {"file": "광문2_분석본01(수특라이트영독1,2강)_내지.idml"}
OLPO = {"file": "광문1_분석본02(올포7,8강)_내지.idml"}


def _row(label, unit, src):
    return {"label": label, "unit": unit, "source": dict(src)}


def test_light_analysis_becomes_01_and_moves_first():
    rows = [_row("1강 02", "수능특강 1강", LIGHT), _row("1강 03", "수능특강 1강", LIGHT),
            _row("분석", "수능특강 1강", LIGHT),
            _row("2강 02", "수능특강 2강", LIGHT), _row("2강 분석", "수능특강 2강", LIGHT)]
    _fix_lecture_label(rows, lambda *a: None)
    assert [r["label"] for r in rows] == ["1강 01", "1강 02", "1강 03", "2강 01", "2강 02"]


def test_range_label_gets_lecture():
    rows = [_row("4강 04", "수능특강 4강", LIGHT), _row("5~6번", "수능특강 4강", LIGHT)]
    _fix_lecture_label(rows, lambda *a: None)
    assert rows[1]["label"] == "4강 05~06"


def test_other_books_keep_analysis():
    rows = [_row("7강 분석", "올림포스 7강", OLPO), _row("7강 01", "올림포스 7강", OLPO)]
    _fix_lecture_label(rows, lambda *a: None)
    assert [r["label"] for r in rows] == ["7강 분석", "7강 01"]


def test_light_with_existing_01_untouched():
    rows = [_row("1강 01", "수능특강 1강", LIGHT), _row("1강 분석", "수능특강 1강", LIGHT)]
    _fix_lecture_label(rows, lambda *a: None)
    assert [r["label"] for r in rows] == ["1강 01", "1강 분석"]
