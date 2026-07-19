"""W31 — 구조 우선 헤더 인식기 (core/structure/header_detect) 가드.

2026-07-19 실사용 재발(job 376b34d0, textbook_workbook_v2): "1. L1-p. 13
본문 1" 형식이 정규식 열거에 없어 4개 섹션이 유닛 1 통짜 + 경고 0.
새 인식기는 형식이 아니라 구조(짧은 라인/숫자/순번/마커/직후 영어 본문/
자기 유사 반복/순번 단조성)로 판정한다 — 여기의 가드가 그 계약을 지킨다.
"""
import json
import os

import pytest

from core.structure.header_detect import (Detection, HeaderSilenceError,
                                          detect_from_candidates,
                                          detect_headers, line_signals,
                                          is_structural_candidate, shape_of)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASELINE = os.path.join(_REPO, "docs", "원고_구조_인식률_baseline.json")

_BODY = ("There are a lot of things that fill us with hope for the "
         "future: technology, science, and responsible leaders.")


# ── 1. 2026-07-19 실패 케이스 (376b34d0) — 구조 신호만으로 인식 ─────────────

def test_fail_20260719_recognized_without_legacy():
    """정규식 프라이어 없이(legacy=None) 구조 신호만으로 전 헤더 인식."""
    texts = []
    for i in range(1, 6):
        texts.append("%d. L1-p. %d 본문 %d" % (i, 12 + i, i))
        texts.append(_BODY)
        texts.append("우리를 미래에 대한 희망으로 채우는 많은 것들이 있다.")
    texts.append("6. L1-추가본문")
    texts.append(_BODY)
    det = detect_headers(texts)
    got = sorted(det.header_idx)
    assert got == [0, 3, 6, 9, 12, 15], got
    assert not det.silent()


def test_fail_20260719_signals():
    sig = line_signals("1. L1-p. 13 본문 1")
    assert sig["short"] and sig["digit"] and sig["numbered"] and sig["marker"]
    assert not sig["stem"] and not sig["answerish"]
    assert is_structural_candidate("1. L1-p. 13 본문 1")


# ── 2. 호환성 계약: legacy 인식분은 항상 유지 (diff 0 하한) ──────────────────

def test_legacy_lines_always_headers():
    texts = ["아무 관련 없는 한글 문장이다", "1. p2-no.18", _BODY]
    det = detect_headers(texts, legacy=lambda t: t == "1. p2-no.18")
    assert 1 in det.header_idx
    # legacy가 잡은 라인은 구조 신호와 무관하게 유지
    det2 = detect_headers(["가나다라"], legacy=lambda t: True)
    assert 0 in det2.header_idx


# ── 3. 오탐 가드: 발문/정답/선지 나열은 후보에서 배제 ───────────────────────

@pytest.mark.parametrize("line", [
    "1. 다음 글의 밑줄 친 부분 중 어법상 틀린 것은?",
    "Q. 문맥 상 다음 문장들의 적절한 순서를 쓰시오.",
    "정답: 4번",
    "2. 10단어 이내로 작성할 것",
    "1. ① 2. ② 3. ③",
])
def test_non_headers_not_candidates(line):
    assert not is_structural_candidate(line)


def test_body_line_not_candidate():
    assert not is_structural_candidate(_BODY)


# ── 4. 자기 유사 전파 + 순번 단조성 ─────────────────────────────────────────

def test_shape_cluster_promotion():
    """앵커 1개(직후 본문)의 셰이프가 같은 문서의 닮은 후보를 승격."""
    texts = ["1. p2-no.18", _BODY,
             "2. p4-no.20", "한글 해석만 뒤따르는 경우",
             "3. p6-no.22", "한글 해석만 뒤따르는 경우"]
    det = detect_headers(texts)
    assert {0, 2, 4} <= det.header_idx


def test_sequence_promotion_monotonic():
    """셰이프 반복 3+ + 숫자 토큰 단조 증가 → 직후 본문 없이도 승격."""
    texts = []
    for i in range(1, 5):
        texts.append("본문%d" % i)
        texts.append("한글 제목 또는 해석 줄")
    det = detect_headers(texts)
    assert {0, 2, 4, 6} <= det.header_idx


def test_sequence_not_promoted_when_not_monotonic():
    """반복돼도 숫자가 단조 증가하지 않으면(비순번 잡음) 승격 안 함."""
    texts = []
    for v in (7, 3, 9, 2):
        texts.append("본문%d" % v)
        texts.append("한글 제목 또는 해석 줄")
    det = detect_headers(texts)
    assert not det.header_idx


def test_shape_of_normalizes_digits_dashes_spaces():
    assert shape_of("1. L1-p. 13 본문 1") == shape_of("2. L1–p. 14 본문 2")


# ── 5. 침묵 금지 ────────────────────────────────────────────────────────────

def test_silent_when_candidates_unrecognized():
    """강한 후보(직후 영어 본문) 2+개 미인식 → silent (조판 중단 사유).

    합성: 마커는 있으나 셰이프가 서로 다르고 순번도 단조가 아님 —
    앵커/클러스터/시퀀스 모두 실패하는 상황."""
    det = Detection()
    det.candidates = [
        {"i": 0, "t": "x", "score": 0, "via": None,
         "signals": {"body_next": True}},
        {"i": 5, "t": "y", "score": 0, "via": None,
         "signals": {"body_next": True}},
    ]
    assert det.silent()
    det.header_idx = {0, 5}
    assert not det.silent()


def test_plan_wordfill_raises_on_silence():
    """플랜 빌더(_build_wordfill)가 침묵 실패 시 HeaderSilenceError."""
    from engines.workbook_v2.plan import build_step1_c2
    paras = []
    # 서로 셰이프가 다르고 순번 비단조인 미지 형식 헤더 2개 + 영어 본문
    paras.append({"text": "결9번 p8", "runs": []})
    paras.append({"text": _BODY, "runs": []})
    paras.append({"text": "p3 결결5", "runs": []})
    paras.append({"text": _BODY, "runs": []})
    with pytest.raises(HeaderSilenceError):
        build_step1_c2({"paragraphs": paras})


def test_plan_wordfill_splits_new_format():
    """376b34d0 형식: 새 인식기가 유닛을 지문별로 분할 + 헤더 제거."""
    from engines.workbook_v2.plan import build_step1_c2
    paras = []
    for i in range(1, 7):
        paras.append({"text": "%d. L1-p. %d 본문 %d" % (i, 12 + i, i),
                      "runs": []})
        paras.append({"text": _BODY, "runs": []})
        paras.append({"text": "우리를 희망으로 채우는 것들이 있다.",
                      "runs": []})
    built = build_step1_c2({"paragraphs": paras})
    assert len(built["units"]) == 6
    joined = json.dumps(built["units"], ensure_ascii=False)
    assert "본문 1" not in joined  # 헤더 원문 인쇄 금지


# ── 6. 전수 인벤토리 리그레션 지표 (baseline JSON 가드) ─────────────────────

def test_baseline_struct_v2_rate():
    """구조 인식기 인식률 baseline — 재측정 시 이 수치 아래로 떨어지면
    회귀 (scripts/structure_coverage.py 재실행으로 갱신)."""
    b = json.load(open(_BASELINE, encoding="utf-8"))
    assert b["struct_v2_rate_pct"] >= 96.0, b["struct_v2_rate_pct"]
    assert b["struct_v2_rate_pct"] > b["regex_recognition_rate_pct"]
    assert b["struct_v2_stem_fp"] == 0
    assert b["fail_20260719_v2_recognized"] is True
    # 참고: 파서 정규식(_RE_HEADER_NUM)은 이 헤더를 매치하지만, 실제
    # 실패 지점은 플랜 계층(is_header_line._HEADER_PATTERNS)이었다 —
    # 파서·플랜·게이트가 서로 다른 눈을 쓰던 것이 W31의 수리 대상.


def test_detect_from_candidates_same_core():
    """측정 경로(detect_from_candidates)와 실전 경로가 같은 판정."""
    cands = [{"t": "%d. L1-p. %d 본문 %d" % (i, 12 + i, i),
              "body_next": True} for i in range(1, 7)]
    det = detect_from_candidates(cands)
    assert len(det.header_idx) == 6
