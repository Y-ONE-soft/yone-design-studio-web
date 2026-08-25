# -*- coding: utf-8 -*-
"""연도 묶음 폴더 흡수 — `모의고사 작업/고1/고1 25년(3,6,9,10,11월)/고1 25년 3월`.

2026-08-25 고1 21~25년 회차 폴더가 연도 묶음 폴더 안으로 내려가면서,
학년 폴더를 한 겹만 listdir 하던 탐색이 전부 회차를 못 찾게 됐다.
게다가 묶음 이름이 "11월" 을 부분문자열로 품고 있어 substring 매칭 쪽은
**묶음 폴더를 11월 회차로 오인**했다 (못 찾는 것보다 나쁘다 — 어법수정은
묶음 전체를 os.walk 해 다른 달 원고까지 같은 회차로 라벨링한다).
"""
import os
import unicodedata

import pytest

GROUP = "고1 25년(3,6,9,10,11월)"
ROUNDS = ["고1 25년 3월", "고1 25년 6월", "고1 25년 9월", "고1 25년 10월"]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@pytest.fixture
def mock_base(tmp_path):
    """고1 = 묶음 폴더 + 평면 회차 혼재 / 고2 = 전부 평면 (실측 구조)."""
    base = tmp_path / "모의고사 작업"
    for r in ROUNDS:
        (base / "고1" / GROUP / r).mkdir(parents=True)
    (base / "고1" / "고1 26년 3월").mkdir(parents=True)
    (base / "고1" / "한영고1 마더텅 예전 기출" / "13강 어법").mkdir(parents=True)
    (base / "고2" / "고2 25년 3월").mkdir(parents=True)
    (base / "고2" / "고2 20년 이전" / "고2 201124").mkdir(parents=True)
    return base


def _plain_entries(d, log=None):
    if not os.path.isdir(d):
        return []
    return [(_nfc(n), os.path.join(d, n)) for n in sorted(os.listdir(d))]


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def test_month_dir_entries_flattens_group(mock_base):
    from core.mock_folders import month_dir_entries
    names = [n for n, _ in month_dir_entries(str(mock_base / "고1"))]
    for r in ROUNDS:
        assert r in names
    assert "고1 26년 3월" in names
    # 묶음 폴더 자체는 회차가 아니다 — 목록에 남으면 11월 회차로 오인된다
    assert GROUP not in names
    # 회차가 아닌 폴더는 종전대로 통과 (다른 탐색이 이 목록을 함께 쓴다)
    assert "한영고1 마더텅 예전 기출" in names


def test_month_dir_entries_flat_grade_unchanged(mock_base):
    from core.mock_folders import month_dir_entries
    names = [n for n, _ in month_dir_entries(str(mock_base / "고2"))]
    assert names == ["고2 20년 이전", "고2 25년 3월"]


# ── 분석본 결합 (마더텅 결합·분석본 결합 v2 가 위임) ────────────────────────

def test_analysis_merge_finds_nested_round(mock_base, monkeypatch):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    import engines.final.extractor as ext
    monkeypatch.setattr(ext, "list_manuscript_entries", _plain_entries)
    got = AnalysisMergeEngine._find_month_folder(str(mock_base), 1, "25", 3)
    assert got and os.path.basename(_nfc(got)) == "고1 25년 3월"


def test_analysis_merge_group_name_not_mistaken_for_november(
        mock_base, monkeypatch):
    """'고1 25년(3,6,9,10,11월)' 은 11월 회차가 아니다 (25년엔 11월이 없다)."""
    from engines.analysis_merge.engine import AnalysisMergeEngine
    import engines.final.extractor as ext
    monkeypatch.setattr(ext, "list_manuscript_entries", _plain_entries)
    assert AnalysisMergeEngine._find_month_folder(
        str(mock_base), 1, "25", 11) is None


# ── 워크북 선택 결합 (원고) ─────────────────────────────────────────────────

def test_workbook_select_finds_nested_manuscripts(mock_base):
    from engines.workbook_select.engine import WorkbookSelectEngine
    (mock_base / "고1" / GROUP / "고1 25년 3월" / "워크북").mkdir()
    got, err = WorkbookSelectEngine._find_manuscript_dir(
        str(mock_base), "1", 25, 3)
    assert err is None
    assert _nfc(got).endswith("고1 25년 3월/워크북")


def test_blankcheck_finds_nested_workbook_dir(mock_base):
    from engines.workbook_select import blankcheck
    (mock_base / "고1" / GROUP / "고1 25년 6월" / "고1 25년 6월 워크북").mkdir()
    got = blankcheck._workbook_dir(str(mock_base), "1", "250629")
    assert got and _nfc(got).endswith("고1 25년 6월 워크북")


# ── 직전보충 어법수정 ───────────────────────────────────────────────────────

def _touch_grammar(d, name):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("x", encoding="utf-8")


def test_mockexam_grammar_finds_nested_round(mock_base):
    from engines.final.grammar_word_parser import find_mockexam_grammar_files
    _touch_grammar(mock_base / "고1" / GROUP / "고1 25년 3월",
                   "고1_2025_03월-읽기영역_어법수정_문제지.docx")
    got = find_mockexam_grammar_files(str(mock_base.parent), "25년3월", "고1")
    assert [y for _, y in got] == ["2503"]


def test_mockexam_grammar_group_not_walked_as_november(mock_base):
    """묶음을 11월로 오인하면 3·6·9·10월 원고까지 2511 로 딸려 온다."""
    from engines.final.grammar_word_parser import find_mockexam_grammar_files
    for r in ROUNDS:
        _touch_grammar(mock_base / "고1" / GROUP / r,
                       f"{r}_어법수정_문제지.docx")
    got = find_mockexam_grammar_files(str(mock_base.parent), "25년11월", "고1")
    assert got == []


def test_mothertongue_modern_folder_nested(mock_base):
    from engines.final.mothertongue_grammar_loader import (
        _modern_folder_for_yymm)
    got = _modern_folder_for_yymm(str(mock_base.parent), "고1", "2510")
    assert got and _nfc(got).endswith("고1 25년 10월")
