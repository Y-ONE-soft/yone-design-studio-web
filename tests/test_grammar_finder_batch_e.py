# -*- coding: utf-8 -*-
"""배치 E (W36) — final 어법수정 탐색기 8종 유사도화 (docs/인식지점_전수감사.md §9).

검증 계약:
  · 기존 리터럴 매칭분 100% 유지 (tier1 = 레거시 술어 그대로 — additive)
  · 감사 실증 #5 ('어법 수정' 공백 → 탐색 0건 무로그) 회복
  · 침묵 금지 — 기대 소스 폴더가 있는데 매칭 0건이면 후보 목록과 [경고]
  · 오탐 가드 — 실 GDrive sweep이 드러낸 'Step2 A1 어법선택(수정)' 류
    (subsequence 티어 폐기 근거) 미매칭 유지
  · 안전 밸브 YONE_FINAL_FUZZY_FIND=0 → 리터럴 단독 (기존 동작)
"""
import os
import unicodedata

import pytest

from engines.final.grammar_finder import (
    fuzzy_grammar_match, folder_token_match, list_docx_candidates, warn_zero
)
from engines.final.grammar_word_parser import (
    find_grammar_word_files, find_mockexam_grammar_files,
    find_mockexam_grammar_files_by_codes, find_mothertongue_grammar_files,
    find_ebs_grammar_files,
)


def _nfd(s):
    return unicodedata.normalize("NFD", s)


@pytest.fixture
def no_mirror(monkeypatch):
    """미러/GDrive 합집합 우회 — tmp 트리를 직접 listdir."""
    import engines.final.extractor as ext
    monkeypatch.setattr(ext, "_resolve_local_mirror",
                        lambda src, log=None: src)
    yield


# ── fuzzy_grammar_match 단위 ────────────────────────────────────────────────

@pytest.mark.parametrize("fn", [
    "고1_2025년10월_어법 수정_문제지.docx",     # 감사 실증 #5 (공백)
    "고1_어법_수정_문제지.docx",               # 언더스코어
    "공통영어1_어법(수정) 문제지.docx",         # 괄호
    "올림포스_어법수정_문제.docx",             # '_문제' 끝맺음 (문제지 생략형)
])
def test_fuzzy_new_recognitions(fn):
    assert fuzzy_grammar_match(fn)


def test_fuzzy_nfd_filename():
    assert fuzzy_grammar_match(_nfd("어법 수정_문제지.docx"))


@pytest.mark.parametrize("fn", [
    "Step2 A1 어법선택(수정).docx",   # 실 GDrive sweep 오탐 실증 — 미매칭 유지
    "Step2 B1 어법 OX(수정).docx",
    "고1_어법 수정_정답지.docx",       # 답안류 제외 (정규화 기준)
    "고1_어법수정_해 설.docx",
    "어법 수정_문제지.hwp",           # 확장자
    "~어법 수정_문제지.docx",          # 임시파일
    "고1_문법 수정_문제지.docx",       # 키 토큰 없음
])
def test_fuzzy_rejections(fn):
    assert not fuzzy_grammar_match(fn, require_probsheet=False) \
        or fn.endswith("문제지.docx") and False


def test_fuzzy_probsheet_gate():
    # 문제지 표기 없는 어법수정 파일 — 문제지 요구 시 미매칭, 리딩파워식(불요) 매칭
    fn = "고1_어법 수정 모음.docx"
    assert not fuzzy_grammar_match(fn, require_probsheet=True)
    assert fuzzy_grammar_match(fn, require_probsheet=False)


def test_fuzzy_range_variant():
    fn = "41~42번 어법 수정.docx"     # 범위 변형 + 공백 (문제지 불요 의미론)
    assert not fuzzy_grammar_match(fn, require_probsheet=True)
    assert fuzzy_grammar_match(fn, require_probsheet=True,
                               allow_range_variant=True)


def test_fuzzy_valve_off(monkeypatch):
    monkeypatch.setenv("YONE_FINAL_FUZZY_FIND", "0")
    assert not fuzzy_grammar_match("고1_어법 수정_문제지.docx")
    assert not folder_token_match("공통영어1_능률민", "능률(민)")


def test_folder_token_match():
    assert folder_token_match("공통영어1_능률민 1과", "능률(민)")
    assert folder_token_match("고1 25년 10월", "25년10월")
    assert not folder_token_match("공통영어1 미래엔(김)", "능률(민)")


# ── 실증 #5 재현 — find_mockexam_grammar_files ──────────────────────────────

def _make_mock_tree(tmp_path, fname):
    base = tmp_path / "모의고사 작업" / "고1" / "고1 25년 10월" / "직전보충"
    base.mkdir(parents=True)
    (base / fname).write_bytes(b"")
    return base


def test_mockexam_space_variant_recovered(tmp_path, no_mirror):
    _make_mock_tree(tmp_path, "고1_2025년10월_어법 수정_문제지.docx")
    logs = []
    found = find_mockexam_grammar_files(
        str(tmp_path), "25년10월", "고1", log=logs.append)
    assert len(found) == 1 and found[0][1] == "2510"
    assert any("유사 매칭" in l for l in logs)


def test_mockexam_legacy_unchanged(tmp_path, no_mirror):
    _make_mock_tree(tmp_path, "고1_2025년10월_어법수정_문제지.docx")
    logs = []
    found = find_mockexam_grammar_files(
        str(tmp_path), "25년10월", "고1", log=logs.append)
    assert len(found) == 1
    assert not any("유사 매칭" in l or "[경고]" in l for l in logs)


def test_mockexam_zero_warns_with_candidates(tmp_path, no_mirror):
    _make_mock_tree(tmp_path, "고1_다른자료.docx")
    logs = []
    found = find_mockexam_grammar_files(
        str(tmp_path), "25년10월", "고1", log=logs.append)
    assert found == []
    warn = [l for l in logs if "[경고]" in l]
    assert warn and "고1_다른자료.docx" in warn[0]


def test_mockexam_valve_off_restores_old_behavior(tmp_path, no_mirror,
                                                  monkeypatch):
    monkeypatch.setenv("YONE_FINAL_FUZZY_FIND", "0")
    _make_mock_tree(tmp_path, "고1_2025년10월_어법 수정_문제지.docx")
    found = find_mockexam_grammar_files(str(tmp_path), "25년10월", "고1")
    assert found == []                     # 기존 동작 (침묵 0건)


def test_mockexam_month_folder_numeric_token(tmp_path, no_mirror):
    # 월 폴더 숫자-단위 사이 공백 변형 (배치 A 2차 패턴 확산 — 1차 실패형)
    base = tmp_path / "모의고사 작업" / "고1" / "고1 25 년 10 월"
    base.mkdir(parents=True)
    (base / "고1_25년10월_어법수정_문제지.docx").write_bytes(b"")
    logs = []
    found = find_mockexam_grammar_files(
        str(tmp_path), "25년10월", "고1", log=logs.append)
    assert len(found) == 1
    assert any("유사 매칭" in l for l in logs)


def test_mockexam_rsync_partial_still_pruned(tmp_path, no_mirror):
    # dev-guide 2026-06-26 가지치기 회귀 가드 — 유사도화 후에도 유지
    base = _make_mock_tree(tmp_path, "고1_어법수정_문제지.docx")
    bad = base / ".rsync-partial"
    bad.mkdir()
    (bad / "고1_어법수정_문제지.docx").write_bytes(b"")
    found = find_mockexam_grammar_files(str(tmp_path), "25년10월", "고1")
    assert len(found) == 1
    assert ".rsync-partial" not in found[0][0]


# ── find_grammar_word_files (교과서) ────────────────────────────────────────

def _make_textbook_tree(tmp_path, pub_folder="공통영어1 능률(민)",
                        lesson_folder="공통영어1 능률(민) 1과",
                        fname="공통영어1_어법수정_문제지.docx"):
    d = tmp_path / "교과서 작업" / "공통영어1" / pub_folder / lesson_folder
    d.mkdir(parents=True)
    (d / fname).write_bytes(b"")
    return d


def test_textbook_legacy_unchanged(tmp_path, no_mirror):
    _make_textbook_tree(tmp_path)
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["1과"], log=logs.append)
    assert len(found) == 1
    assert not any("[경고]" in l or "유사" in l for l in logs)


def test_textbook_file_space_variant(tmp_path, no_mirror):
    _make_textbook_tree(tmp_path, fname="공통영어1_어법 수정_문제지.docx")
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["1과"], log=logs.append)
    assert len(found) == 1
    assert any("유사 매칭" in l for l in logs)


def test_textbook_publisher_folder_normalized(tmp_path, no_mirror):
    # 교재 폴더 '능률민' (괄호 탈락) — 1차 실패 → 2차 정규화 매칭
    _make_textbook_tree(tmp_path, pub_folder="공통영어1_능률민",
                        lesson_folder="공통영어1 능률민 1과")
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["1과"], log=logs.append)
    assert len(found) == 1
    assert any("교재 폴더 유사 매칭" in l for l in logs)


def test_textbook_lesson_folder_padded(tmp_path, no_mirror):
    # 과 폴더 숫자-단위 사이 공백 변형 '1 과' — 1차 실패 → 2차 숫자 토큰 매칭
    _make_textbook_tree(tmp_path, lesson_folder="공통영어1 능률(민) 1 과")
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["1과"], log=logs.append)
    assert len(found) == 1
    assert any("폴더 유사 매칭" in l for l in logs)


def test_textbook_lesson_zero_warns(tmp_path, no_mirror):
    d = _make_textbook_tree(tmp_path, fname="다른자료.docx")
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["1과"], log=logs.append)
    assert found == []
    warn = [l for l in logs if "[경고]" in l and "매칭 0건" in l]
    assert warn and "다른자료.docx" in warn[0]


def test_textbook_lesson_missing_lists_candidates(tmp_path, no_mirror):
    _make_textbook_tree(tmp_path)     # 1과만 존재
    logs = []
    found = find_grammar_word_files(
        str(tmp_path), "공통영어1", "능률(민)", ["3과"], log=logs.append)
    assert found == []
    warn = [l for l in logs if "[경고]" in l and "3과 폴더 없음" in l]
    assert warn and "1과" in warn[0]   # 후보 폴더 나열


# ── find_ebs_grammar_files — 올포 침묵 금지 ─────────────────────────────────

def test_ebs_olpo_unit_missing_warns(tmp_path, no_mirror):
    d = tmp_path / "EBS 작업" / "올림포스 독해기본1" / "올림포스 독해기본1 2강"
    d.mkdir(parents=True)
    (d / "올림포스_어법수정_문제지.docx").write_bytes(b"")
    logs = []
    found = find_ebs_grammar_files(
        str(tmp_path), "올포2-3강", log=logs.append, grade="고1")
    assert [u for _, u in found] == [2]
    assert any("[경고]" in l and "3강 폴더 미발견" in l for l in logs)


def test_ebs_olpo_zero_files_warns(tmp_path, no_mirror):
    d = tmp_path / "EBS 작업" / "올림포스 독해기본1" / "올림포스 독해기본1 2강"
    d.mkdir(parents=True)
    (d / "노트.docx").write_bytes(b"")
    logs = []
    found = find_ebs_grammar_files(
        str(tmp_path), "올포2강", log=logs.append, grade="고1")
    assert found == []
    assert any("[경고]" in l and "매칭 0건" in l for l in logs)


# ── find_mothertongue_grammar_files ─────────────────────────────────────────

def test_mothertongue_folder_normalized_and_file_variant(tmp_path, no_mirror):
    d = (tmp_path / "모의고사 작업" / "고1"
         / "한영고1_마더텅_예전기출" / "3강 예전 기출")
    d.mkdir(parents=True)
    (d / "마더텅3강_어법 수정_문제지.docx").write_bytes(b"")
    logs = []
    found = find_mothertongue_grammar_files(str(tmp_path), "고1",
                                            log=logs.append)
    assert len(found) == 1 and found[0][1] == 3
    assert any("마더텅 폴더 유사 매칭" in l for l in logs)
    assert any("유사 매칭" in l for l in logs)


def test_mothertongue_absent_warns(tmp_path, no_mirror):
    (tmp_path / "모의고사 작업" / "고1").mkdir(parents=True)
    logs = []
    found = find_mothertongue_grammar_files(str(tmp_path), "고1",
                                            log=logs.append)
    assert found == []
    assert any("[경고]" in l for l in logs)


# ── find_mockexam_grammar_files_by_codes — 폴더 미발견 경고 ─────────────────

def test_by_codes_missing_month_folder_warns(tmp_path, no_mirror):
    base = tmp_path / "모의고사 작업" / "고2" / "고2 25년 3월"
    base.mkdir(parents=True)
    (base / "고2_어법수정_문제지.docx").write_bytes(b"")
    logs = []
    found = find_mockexam_grammar_files_by_codes(
        str(tmp_path), "고2", ["250320", "240940"], log=logs.append)
    assert len(found) == 1 and found[0][1] == "2503"
    assert any("[경고]" in l and "24년 9월" in l and "미발견" in l
               for l in logs)


# ── 헬퍼 단위 ───────────────────────────────────────────────────────────────

def test_list_docx_candidates_prunes_dot_dirs(tmp_path):
    (tmp_path / "a.docx").write_bytes(b"")
    bad = tmp_path / ".rsync-partial"
    bad.mkdir()
    (bad / "b.docx").write_bytes(b"")
    assert list_docx_candidates(str(tmp_path)) == ["a.docx"]


def test_warn_zero_without_candidates(tmp_path):
    logs = []
    warn_zero(logs.append, "테스트", str(tmp_path))
    assert logs and "[경고]" in logs[0] and "후보 없음" in logs[0]
