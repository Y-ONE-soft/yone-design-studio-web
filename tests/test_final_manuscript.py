# -*- coding: utf-8 -*-
"""파이널 **원고 직독**(B6) 계약 검사 — GDrive 없이 돈다.

지키려는 것은 다섯 학교 180지문을 **내용으로 짝지어** 읽어 낸 규칙들이다:
  · 시험범위 토큰(`리딩파워12강,14강`)에서 강을 **하나도 빠뜨리지 않는다**
    — 예전 정규식은 뒤쪽 `,14강` 을 통째로 흘렸다
  · 원고 라벨 → 파이널 라벨 (출처마다 방언이 다르다)
  · 차례(교과서 → 강 → 모의 → 고3)
  · 정답지를 문제지로 착각하지 않는다
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from engines.final import manuscript as M            # noqa: E402
from engines.final import manuscript_locate as L     # noqa: E402


# ── 시험범위 토큰 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,want", [
    ("광문2_워크북01(리딩파워12강,14강)_내지.indd", [("rp", 12), ("rp", 14)]),
    ("광문2_워크북01(리딩파워15,16,17강)_내지(수정전).indd",
     [("rp", 15), ("rp", 16), ("rp", 17)]),
    ("상일1_워크북04(올림포스10-12,14-16강)_내지.indd",
     [("olpo", 10), ("olpo", 11), ("olpo", 12),
      ("olpo", 14), ("olpo", 15), ("olpo", 16)]),
    ("광문2_워크북04(25년3월)_내지.indd", [("mock", 25, 3)]),
    ("명일3_FINALEDGE분석편02(18,19,20,21강)_내지.indd",
     [("bare", 18), ("bare", 19), ("bare", 20), ("bare", 21)]),
    ("광문3_FINALEDGE분석편03(29,30강,test2)_내지.indd",
     [("bare", 29), ("bare", 30), ("test", 2)]),
])
def test_scope_tokens(name, want):
    assert L.parse_tokens(name) == want


def test_textbook_token_keeps_both_lessons():
    got = L.parse_tokens("상일1_워크북03(올림포스15,16,17,18강,미래엔3,4과DL)_내지.indd")
    assert ("lesson", 3) in got and ("lesson", 4) in got


# ── 라벨 규칙 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("src,raw,want", [
    ({"kind": "lesson", "lesson": 4}, "L4-본문1(p.94)", "교과서4과 본문1"),
    ({"kind": "lesson", "lesson": 4}, "L4-Read More(p.109)", "교과서4과 RM"),
    ({"kind": "lesson", "lesson": 3, "deeplearning": True},
     "L3-본문9", "교과서3과 딥러닝"),
    ({"kind": "olpo", "unit": 15}, "p100-수능 대비 ANALYSIS", "올포 15강 분석"),
    ({"kind": "olpo", "unit": 15}, "p102-no.01", "올포 15강 본문1"),
    # 장문(1지문 2문항)은 첫 번호를 쓴다
    ({"kind": "olpo", "unit": 17}, "p116-no.01~02", "올포 17강 본문1"),
    ({"kind": "olpo", "unit": 12}, "p85-서술형 Practice", "올포 12강 서술형"),
    ({"kind": "rp", "unit": 15}, "p106-Example 1", "리딩파워 15강 Ex01"),
    ({"kind": "rp", "unit": 15}, "p108-no.1", "리딩파워 15강 01"),
    ({"kind": "mock", "year": 25, "month": 3}, "p2-no.20", "250320"),
    ({"kind": "mock", "year": 25, "month": 3}, "p8-no.41~42", "250341~42"),
    ({"kind": "mock", "year": 23, "month": 11}, "p5-no.33", "231133"),
    ({"kind": "teuk", "unit": 17}, "p102-no.02", "17강 02"),
    ({"kind": "teuk", "unit": 19}, "p115-no.03~04", "19강 03~04"),
    ({"kind": "test", "unit": 1}, "p213-no.24~25", "test1 24~25"),
])
def test_label_rule(src, raw, want):
    assert L.to_final_label(src, raw) == want


def test_label_rule_returns_none_when_unknown():
    assert L.to_final_label({"kind": "olpo", "unit": 1}, "p1-알 수 없는 것") is None


# ── 원고 파일 고르기 ─────────────────────────────────────────────────────
def test_manuscript_pick_skips_answer_sheets(tmp_path):
    for n in ("Step1 C1 문장배열 정답지.docx", "Step1 C1 문장배열.docx",
              "Step2 C2 영작배열 정답.docx", "Step2 C2 영작배열(서술형).hwpx",
              "Step2 C2 영작배열.docx"):
        (tmp_path / n).write_text("x")
    assert os.path.basename(M.find_manuscript(str(tmp_path), "arrange")) \
        == "Step1 C1 문장배열.docx"
    # 괄호가 붙은 변형본보다 기본형 docx 를 고른다
    assert os.path.basename(M.find_manuscript(str(tmp_path), "writing")) \
        == "Step2 C2 영작배열.docx"


def test_manuscript_pick_handles_g3_number_dialect(tmp_path):
    for n in ("3. 문장배열 정답.docx", "3. 문장배열.docx"):
        (tmp_path / n).write_text("x")
    assert os.path.basename(M.find_manuscript(str(tmp_path), "arrange")) \
        == "3. 문장배열.docx"


# ── 원고 라벨 뜯기 ───────────────────────────────────────────────────────
def test_parse_label_drops_trailing_page():
    assert M.parse_label("L4-본문1(p.94)") == {"page": "L4", "key": "본문1"}
    assert M.parse_label("p106-Example 1") == {"page": "p106",
                                               "key": "Example 1"}


def test_block_head_is_numbered_but_not_an_item():
    assert M.is_block_head("1. p160-no.01")
    assert not M.is_block_head("(A) Something happened.")
    assert not M.is_block_head("Q. 문맥 상 다음 문장들의 …")


# ── 차례 ─────────────────────────────────────────────────────────────────
def test_order_is_textbook_then_units_then_mock_then_g3():
    from final_manuscript_build import order_key
    labels = ["250320", "리딩파워 15강 01", "교과서4과 본문2", "교과서4과 RM",
              "리딩파워 15강 Ex01", "17강 02", "교과서3과 본문1", "250319"]
    assert sorted(labels, key=order_key) == [
        "교과서3과 본문1", "교과서4과 본문2", "교과서4과 RM",
        "리딩파워 15강 Ex01", "리딩파워 15강 01", "250319", "250320", "17강 02"]


# ── 시험범위 = 섹션 합집합 ────────────────────────────────────────────────
def test_scope_is_the_union_of_all_sections():
    """한 섹션에서 빠진 지문이 다른 섹션에 살아 있으면 그것도 범위다."""
    from final_manuscript_build import scope_labels
    content = {
        "vol1": {"문장배열": [{"header": "리딩파워 12강 01"}],
                 "문장삽입": [],
                 "중요어휘_왼": "250320\nsome text\n\n>>   내용요약   \nsum\n"},
        "vol2": {"어법_헤더": ["리딩파워 14강 01"],
                 "영작_헤더_상세": [{"header": "리딩파워 14강 02",
                                "start_idx": 0}]},
    }
    got = scope_labels(content)
    assert {"리딩파워 12강 01", "리딩파워 14강 01",
            "리딩파워 14강 02", "250320"} <= got
