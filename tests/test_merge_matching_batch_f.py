# -*- coding: utf-8 -*-
"""배치 F (W36) — merge 계열 소스 폴더·파일 매칭 구조화 (감사 §9 F안).

검증 계약:
  · 기존 리터럴 매칭분 무변경 (2차는 1차 0건일 때만 진입 — additive)
  · 숫자 토큰 매칭 확산: 세로/가로판 .indd, 마더텅 강 폴더, 강 코드
  · '분석.indd' 축약형 회복 (감사 실증 #6 후반 — 배치 A 미해결 (4))
  · mothertongue → analysis_merge 매처 위임 (배치 A 2차 월 폴더 합류)
  · 미발견 시 후보 리스트를 에러/로그에 동봉 (침묵 금지)
"""
import os
import unicodedata

import pytest


def _nfc(s):
    return unicodedata.normalize("NFC", s)


@pytest.fixture
def fake_entries(monkeypatch):
    """list_manuscript_entries → tmp 트리 직접 listdir (배치 A 테스트 패턴)."""
    import engines.final.extractor as ext
    monkeypatch.setattr(
        ext, "list_manuscript_entries",
        lambda d, log=None: [(_nfc(n), os.path.join(d, n))
                             for n in sorted(os.listdir(d))]
        if os.path.isdir(d) else [])
    yield


# ── 세로/가로판 .indd 숫자 토큰 2차 ─────────────────────────────────────────

def _touch(folder, *names):
    for n in names:
        (folder / n).write_bytes(b"")


def test_sero_legacy_match_unchanged(tmp_path):
    from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
    _touch(tmp_path, "고1 25년 6월 세로(C).indd",
           "MockExam_고1_25년_6월_세로판.indd")
    got = MockexamSeroMergeEngine._find_vertical_file(
        str(tmp_path), "1", "25", "06")
    # 1차 매칭 존재 시 1차 결과 그대로 (최단 파일명)
    assert os.path.basename(got) == "고1 25년 6월 세로(C).indd"


def test_sero_numeric_token_fallback(tmp_path):
    from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
    # '고1' 접두가 아니고 구분자가 언더스코어 — 1차 전멸 → 2차 회복
    _touch(tmp_path, "MockExam_고1_2025년_6월_세로판.indd",
           "MockExam_고1_2025년_9월_세로판.indd",   # 다른 월 오탐 가드
           "MockExam_고2_2025년_6월_세로판.indd")   # 다른 학년 오탐 가드
    got = MockexamSeroMergeEngine._find_vertical_file(
        str(tmp_path), "1", "25", "06")
    assert got and os.path.basename(got) == "MockExam_고1_2025년_6월_세로판.indd"


def test_sero_fallback_requires_sero_token(tmp_path):
    from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
    _touch(tmp_path, "MockExam_고1_2025년_6월_전체판.indd")
    assert MockexamSeroMergeEngine._find_vertical_file(
        str(tmp_path), "1", "25", "06") is None


def test_horiz_numeric_token_fallback_forbids_sero(tmp_path):
    from engines.mockexam_horiz_merge.engine import MockexamHorizMergeEngine
    _touch(tmp_path, "MockExam_고1_2025년_6월_세로 전체.indd",   # 세로 배제
           "MockExam_고1_2025년_6월_전 체(C).indd")
    got = MockexamHorizMergeEngine._find_vertical_file(
        str(tmp_path), "1", "25", "06")
    assert got and os.path.basename(got) == "MockExam_고1_2025년_6월_전 체(C).indd"


def test_sero_parse_not_found_lists_candidates(tmp_path):
    from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
    gdrive = tmp_path / "gdrive" / "고1"
    gdrive.mkdir(parents=True)
    _touch(gdrive, "고1 25년 3월 세로(C).indd")
    job = tmp_path / "job"
    job.mkdir()
    (job / "grade.txt").write_text("고1", encoding="utf-8")

    engine = MockexamSeroMergeEngine()
    engine._config = lambda: {"gdrive_base": str(tmp_path / "gdrive")}
    logs = []
    with pytest.raises(FileNotFoundError) as e:
        engine.parse({"codes": "250632"}, str(job), logs.append)
    msg = str(e.value)
    assert "25년 6월" in msg
    assert ".indd 후보" in msg and "고1 25년 3월 세로(C).indd" in msg


# ── 분석본 후보 매칭 — '분석.indd' 축약형 (실증 #6 후반) ────────────────────

def test_analysis_files_short_form_recovered(tmp_path, fake_entries):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    _touch(tmp_path, "분석.indd", "표지.indd")
    got = AnalysisMergeEngine._find_analysis_files(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["분석.indd"]


def test_analysis_files_despaced_pattern(tmp_path, fake_entries):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    _touch(tmp_path, "고1 3월 분석 본.indd")
    got = AnalysisMergeEngine._find_analysis_files(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["고1 3월 분석 본.indd"]


def test_analysis_files_legacy_priority_unchanged(tmp_path, fake_entries):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    # 1차 매칭이 있으면 2차 미진입 — 축약형은 후보에 추가되지 않음 (기존 무변경)
    _touch(tmp_path, "분석본.indd", "분석본 2.indd", "분석.indd")
    got = AnalysisMergeEngine._find_analysis_files(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["분석본.indd", "분석본 2.indd"]


def test_analysis_parse_error_lists_candidates(tmp_path, fake_entries,
                                               monkeypatch):
    import engines.analysis_merge.engine as am
    month = tmp_path / "gdrive" / "고1" / "고1 25년 6월"
    month.mkdir(parents=True)
    _touch(month, "표지.indd")          # 분석본 아님 → 파일 미발견 경로
    job = tmp_path / "job"
    job.mkdir()
    (job / "grade.txt").write_text("고1", encoding="utf-8")
    monkeypatch.setattr(am, "_load_config",
                        lambda: {"gdrive_base": str(tmp_path / "gdrive"),
                                 "file_patterns": ["분석본"]})
    engine = am.AnalysisMergeEngine()
    logs = []
    with pytest.raises(FileNotFoundError) as e:
        engine.parse({"codes": "250632"}, str(job), logs.append)
    msg = str(e.value)
    assert "분석본 파일 없음" in msg
    assert ".indd 후보" in msg and "표지.indd" in msg


# ── mothertongue — analysis_merge 매처 위임 + 강 폴더 2차 ───────────────────

def test_mothertongue_month_folder_gains_batch_a_fallback(tmp_path,
                                                          fake_entries):
    from engines.mothertongue_merge.engine import _find_month_folder
    base = tmp_path / "고1" / "고1_25년 10월"       # 언더스코어 (실증 #6)
    base.mkdir(parents=True)
    got = _find_month_folder(str(tmp_path), "1", "25", "10")
    assert got and os.path.basename(got) == "고1_25년 10월"


def test_mothertongue_analysis_files_delegated(tmp_path, fake_entries):
    from engines.mothertongue_merge.engine import _find_analysis_files
    _touch(tmp_path, "분석.indd")
    got = _find_analysis_files(str(tmp_path))
    assert [os.path.basename(p) for p in got] == ["분석.indd"]


def test_mothertongue_fallback_lesson_folder_token(tmp_path, fake_entries):
    from engines.mothertongue_merge.engine import _find_fallback_file
    d1 = tmp_path / "마더텅 7강 옛기출"            # 접두 아님 → 2차 토큰
    d1.mkdir()
    _touch(d1, "마더텅 7강.indd")
    d2 = tmp_path / "17강 자료"                    # 오탐 가드 (7 ≠ 17)
    d2.mkdir()
    _touch(d2, "마더텅 17강.indd")
    got = _find_fallback_file(str(tmp_path), "07")
    assert got and os.path.basename(got) == "마더텅 7강.indd"


def test_mothertongue_fallback_prefix_unchanged(tmp_path, fake_entries):
    from engines.mothertongue_merge.engine import _find_fallback_file
    d1 = tmp_path / "7강 빈칸 추론"                # 1차 접두 매칭 (기존)
    d1.mkdir()
    _touch(d1, "마더텅 7강.indd")
    got = _find_fallback_file(str(tmp_path), "07")
    assert got and os.path.basename(got) == "마더텅 7강.indd"


# ── vert_to_horiz — 강 코드 4차 (despace) ───────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("마더텅7강 세로.indd", "07"),          # 기존 1차
    ("한영고1 7강 세로.indd", "07"),        # 기존 2차
    ("Lesson 07 세로.indd", "07"),          # 기존 3차
    ("마더텅_7_강 세로.indd", "07"),        # 신규 4차 (언더스코어)
    ("마더텅 7 강.indd", "07"),             # 신규 4차 (공백)
    ("세로버전.indd", None),                # 미인식 → None (파서는 경고 후 01)
])
def test_extract_gang_code_variants(name, expected):
    from engines.vert_to_horiz.engine import _extract_gang_code
    assert _extract_gang_code(name) == expected
