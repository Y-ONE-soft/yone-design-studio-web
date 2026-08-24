"""W25 — 하단 문제(step2_a1_btm) 헤더의 꼬리 주석 "(정답 N개)" 미인식 결함 가드.

실증(2026-08-24, 부교재 워크북 올림포스 독해기본2 1강 — 사용자 지목):
어법 선택 하단 문제가 통째로 누락되고, 지문 헤더
"1. p8-수능 대비 ANALYSIS  (정답 1개)" 가 본문에 그대로 인쇄됐다.

뿌리: legacy 헤더 판정(v2 plan.is_header_line / v1 run.jsx isHeaderLine)이
꼬리 주석 그룹 `(?:\\([^)]{0,40}\\))?` 을 **패턴마다 개별로** 달고 있었고,
코너명형(수능Analysis / 수능대비ANALYSIS) · Practice형 · no.N형 · L-p형은
그 그룹이 없었다. 하단 문제 헤더는 관행적으로 항상 "(정답 N개)"가 붙기
때문에, 그 스텝의 헤더만 골라서 전멸했다 —
코퍼스 실측: 새로 인식되는 헤더 27개가 **전부** step2_a1_btm.

수리: 꼬리 주석을 패턴이 아니라 판정 함수 한 곳에서 벗긴다(기존 판정이
False일 때만 재시도 — additive). 코너명은 문구 하드코딩 대신 꼴로 매치.
"""
import os
import re

import pytest

from engines.workbook_v2.plan import (build_step2_a1_btm, is_header_line,
                                      unit_paras)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSX = os.path.join(REPO, "engines", "workbook", "jsx", "run.jsx")


# 실제 코퍼스/원고에서 뽑은 하단 문제 헤더 (전부 "(정답 N개)" 꼬리)
BTM_HEADERS = [
    "1. p8-수능 대비 ANALYSIS  (정답 1개)",     # 사용자 지목 원고
    "2. p9-수능 대비 ANALYSIS  (정답 2개)",
    "1. p80-수능 Analysis  (정답 1개)",         # r2c12ext2
    "2. p96-수능 Analysis  (정답 1개)",
    "3. p98-Practice 01  (정답 1개)",
    "4. p108-Practice 03  (정답 1개)",
    "1. p122-Example  (정답 1개)",              # ebs 코퍼스
    "2. p123-Example 2  (정답 1개)",
    "1. L1-본문1(p.17)  (정답 1개)",            # textbook 코퍼스
    "8. L1-Further Reading(p.26-27)  (정답 1개)",
    "1. no.1  (정답 1개)",                      # 외부지문 무-p형
]

# 헤더가 아닌 줄 — 꼬리 벗기기가 본문/발문을 헤더로 승격하면 안 된다
NON_HEADERS = [
    "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은? (정답 1개)",
    "Dear Bloom Cookie customers, With our lease coming to an end.",
    "Unit 13 문장 삽입",
    "고1_2023_11월(경기도)[12월시행]",
    "(정답 1개)",
    "어법선택(문제지)",
]


@pytest.mark.parametrize("text", BTM_HEADERS)
def test_btm_header_with_answer_count_is_recognized(text):
    assert is_header_line(text), text


@pytest.mark.parametrize("text", NON_HEADERS)
def test_body_lines_are_not_promoted(text):
    assert not is_header_line(text), text


def test_corner_name_is_matched_by_shape_not_wording():
    """코너명 문구 하드코딩 탈피 — 미학습 코너명도 꼴로 잡힌다."""
    for t in ("1. p8-수능 유형 ANALYSIS  (정답 1개)",
              "2. p12-내신 대비 REVIEW",
              "3. p20-심화 Practice"):
        assert is_header_line(t), t


def test_btm_units_split_per_header():
    """헤더 미인식이면 build_step2_a1_btm은 유닛 0개 — 문항 통째 누락."""
    texts = [
        "어법선택(문제지)",
        "1. p8-수능 대비 ANALYSIS  (정답 1개)",
        "Dear Bloom Cookie ①customers, we have ②finally made the "
        "③decision to ④move ⑤there this year.",
        "",
        "2. p9-수능 대비 ANALYSIS  (정답 1개)",
        "The store ①has changed a lot and ②we realized ③that ④it "
        "⑤works well for everyone.",
    ]
    step_data = {"paragraphs": [{"text": t, "runs": [{"t": t, "ul": False}]}
                                for t in texts]}
    out = build_step2_a1_btm(step_data)
    assert len(out["units"]) == 2, out["units"]
    # 헤더 줄은 유닛 내용에 남지 않는다 (본문 인쇄 잔존 방지)
    flat = " ".join(p["t"] for u in out["units"] for p in unit_paras(u))
    assert "ANALYSIS" not in flat, flat
    assert "Bloom Cookie" in flat, flat      # 지문 본문은 살아 있어야 한다


# ── v1 run.jsx 파리티: 렌더 JSX도 같은 헤더를 인식해야 한다 ──────────────────
# v1 엔진(workbook / workbook_supp / textbook_workbook / ebs_workbook /
# suneungteukgang_workbook)은 이 JSX의 isHeaderLine 하나로 헤더를 제거하고
# 프레임을 분리한다 — 파이썬만 고치면 v1 출력은 그대로 깨진 채 남는다.

_JS_LITERAL = re.compile(r"/(\^.*?\$)/(i?),?\s*$")


def _jsx_header_patterns():
    """run.jsx의 headerPatterns 배열을 파이썬 정규식으로 옮긴다."""
    src = open(JSX, encoding="utf-8").read()
    start = src.index("var headerPatterns = [")
    body = src[start:src.index("];", start)]
    pats = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("/^"):
            continue
        m = _JS_LITERAL.match(line)
        assert m, line
        pats.append(re.compile(m.group(1),
                               re.I if m.group(2) else 0))
    assert pats, "headerPatterns 추출 실패"
    return pats


def _jsx_is_header_line(text, pats):
    """run.jsx isHeaderLine의 파이썬 등가 (꼬리 벗기기 재시도 포함)."""
    hn = (text or "").replace("﻿", "")
    hn = re.sub("[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", hn)
    hn = re.sub(r"[ \t]+", " ", hn).strip()
    if len(hn) > 60:
        return False
    body = re.sub(r"^\d+\s*[.)]?\s*", "", hn)
    if not body or len(body) > 50:
        return False
    if any(p.match(re.sub(r"\s+", "", body)) for p in pats):
        return True
    stripped = re.sub(r"(?:\s*\([^()]{0,40}\))+\s*$", "", body).strip()
    if not stripped or stripped == body:
        return False
    return any(p.match(re.sub(r"\s+", "", stripped)) for p in pats)


def test_jsx_has_tail_parens_retry():
    src = open(JSX, encoding="utf-8").read()
    assert "reHdrTailParens" in src, "run.jsx에 꼬리 주석 벗기기가 없음"


@pytest.mark.parametrize("text", BTM_HEADERS)
def test_jsx_recognizes_same_btm_headers(text):
    assert _jsx_is_header_line(text, _jsx_header_patterns()), text


@pytest.mark.parametrize("text", NON_HEADERS)
def test_jsx_does_not_promote_body_lines(text):
    assert not _jsx_is_header_line(text, _jsx_header_patterns()), text
