# -*- coding: utf-8 -*-
"""분석본 결합 — 월 폴더 후보 .indd 탐색 (`_find_analysis_files`).

명칭이 '분석본'으로 굳기 전(23년 이전) 회차는 같은 물건을 `모의고사(New)`로
부른다. 파일명 화이트리스트가 아니라 '월 폴더 바로 아래의 .indd = 그 회차의
분석본'이라는 구조로 잡는지, 그리고 그 폴백이 기존(24년~) 폴더의 동작을
바꾸지 않는지 고정한다. InDesign·GDrive 비의존(합성 트리).
"""
import os
import sys
import unicodedata

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

from engines.analysis_merge.engine import AnalysisMergeEngine  # noqa: E402


def _mk(tmp_path, name, files):
    d = tmp_path / name
    d.mkdir()
    for f in files:
        (d / f).write_text("x", encoding="utf-8")
    return str(d)


def _names(paths):
    return [unicodedata.normalize("NFC", os.path.basename(p)) for p in paths]


def _find(folder):
    return _names(AnalysisMergeEngine._find_analysis_files(folder, ["분석본"]))


def test_old_naming_mogosa_is_analysis(tmp_path):
    """23년 이전 회차: `…모의고사(New).indd` 가 분석본 후보로 잡힌다."""
    d = _mk(tmp_path, "고1 23년 6월", [
        "고1 23년 6월 모의고사(New).indd",
        "고1 23년 6월 모의고사(New) 2.indd",
        "23년-6월-고1모의변형100.hwp",
    ])
    assert _find(d) == [
        "고1 23년 6월 모의고사(New).indd",
        "고1 23년 6월 모의고사(New) 2.indd",
    ]


def test_old_naming_keeps_jjal_last(tmp_path):
    """짤지문본은 후보에 들어가되 본편보다 **뒤** — 본편이 먼저 매칭된다."""
    d = _mk(tmp_path, "고1 23년 11월", [
        "고1 23년 11월 모의고사(New).indd",
        "고1 23년 11월 모의고사(New) 2.indd",
        "고1 23년 11월 짤지문.indd",
    ])
    assert _find(d) == [
        "고1 23년 11월 모의고사(New).indd",
        "고1 23년 11월 모의고사(New) 2.indd",
        "고1 23년 11월 짤지문.indd",
    ]


def test_bare_jjal_joins_even_when_primary_matches(tmp_path):
    """'분석본'이 없는 이름의 짤지문본(25년 10월)도 후보에 합류 — 맨 뒤."""
    d = _mk(tmp_path, "고1 25년 10월", [
        "고1 25년 10월 분석본.indd",
        "고1 25년 10월 분석본 2.indd",
        "고1 25년 10월 짤지문.indd",
    ])
    assert _find(d) == [
        "고1 25년 10월 분석본.indd",
        "고1 25년 10월 분석본 2.indd",
        "고1 25년 10월 짤지문.indd",
    ]


def test_current_naming_unchanged(tmp_path):
    """24년~ 폴더는 1차(패턴)에서 끝나 폴백이 아예 돌지 않는다 — 무변경."""
    d = _mk(tmp_path, "고1 24년 3월", [
        "고1 24년 3월 분석본(New).indd",
        "고1 24년 3월 분석본(New) 2.indd",
        "고1 24년 3월 분석본(짤 지문).indd",
        "고1 24년 3월 분석본(New).pdf",
    ])
    assert _find(d) == [
        "고1 24년 3월 분석본(New).indd",
        "고1 24년 3월 분석본(New) 2.indd",
        "고1 24년 3월 분석본(짤 지문).indd",
    ]


def test_fallback_excludes_other_kinds(tmp_path):
    """폴백이 돌더라도 리뷰테스트·워크북·마스터 템플릿은 후보가 아니다."""
    d = _mk(tmp_path, "고2 23년 11월", [
        "고2 23년 11월 모의고사.indd",
        "고2 23년 11월 리뷰테스트.indd",
        "고2 23년 11월 워크북.indd",
        "[원본]분석본_내지(마스터).indd",
    ])
    assert _find(d) == ["고2 23년 11월 모의고사.indd"]


def test_lock_files_ignored(tmp_path):
    d = _mk(tmp_path, "고1 23년 3월", [
        "고1 23년 3월 모의고사(New).indd",
        "~고1 23년 3월 모의~jfhz2c.idlk",
    ])
    assert _find(d) == ["고1 23년 3월 모의고사(New).indd"]
