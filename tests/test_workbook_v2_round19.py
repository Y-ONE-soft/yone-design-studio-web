"""W49 — 지문번호 하위분할(major-minor) 순번 인식 + 시각 게이트 오탐 감축.

실서비스 job 0e3e6469 (영어Ⅱ_YBM(박)_1과_전체(C), textbook_workbook_v2) 검수
에이전트 지목 결함:

  A. 하위분할 헤더 `N. L1-본문2-1(p.18)` 4개(본문2-1/2-2/4-1/4-2)가 미인식 →
     - step2_c2(영작배열): 헤더 원문 그대로 인쇄 (G1 [헤더잔존]).
     - step1_c1(문장배열): GREP이 `본문2`만 잡아 `{본문2}-1(p.18)` 잔재 →
       마커 4<8 (G24 [프레임브레이크]) + 라벨 충돌(2-1·2-2 둘 다 {본문2}).
     뿌리: legacy `is_header_line`의 `본문\\d+`가 `-M` 뒤를 못 받아 구조
     인식기의 seq(단조성)로만 잡혔고, step2_c2는 seq 제외 규칙이 있어 미제거.
     수리: '순번은 계층적(major.minor)' 구조 일반화 — `본문\\d+(?:[-–—.]\\d+)*`.
     (어휘 특례가 아니라 하위분할 전체를 순번으로 본다.)

이 테스트는 동결 원고(tests/corpus/textbook_workbook/r19c01ybmpark/golden/
content.json — 실서비스 산출 그대로)로 플랜을 빌드해 8/8 클린 마커 +
step2_c2 잔존 0 + 게이트 critical 0을 가드한다.
"""
import json
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

import re                                                       # noqa: E402
from engines.workbook_v2.plan import (                          # noqa: E402
    is_header_line, steps_to_plan,
    _C1_GREPS, _C1_RESID, _C1_REMNANT)
from engines.workbook_v2.gate import inspect_workbook_finish    # noqa: E402

_FIXTURE = os.path.join(REPO, "tests", "corpus", "textbook_workbook",
                        "r19c01ybmpark", "golden", "content.json")
_RE_MARKER = re.compile(r"^\{+[^{}]+\}+$")

# 실 원고의 step1_c1 8개 지문 헤더 (동결 — 회귀 판별용)
_C1_HEADERS = [
    "1. L1-본문1(p.17)", "2. L1-본문2-1(p.18)", "3. L1-본문2-2(p.19)",
    "4. L1-본문3(p.20)", "5. L1-본문4-1(p.21)", "6. L1-본문4-2(p.22)",
    "7. L1-본문5(p.23)", "8. L1-Further Reading(p.26-27)",
]


def _grep_c1(text):
    t = text
    for rx, repl in _C1_GREPS:
        t = rx.sub(repl, t)
    for _ in range(3):
        for rx, repl in _C1_RESID:
            t = rx.sub(repl, t)
    for rx, repl in _C1_REMNANT:
        t = rx.sub(repl, t)
    return t


def test_legacy_recognizes_hyphen_subdivision_headers():
    """legacy is_header_line이 본문N-M 하위분할 헤더를 모두 인식 (seq 강등 방지)."""
    for h in _C1_HEADERS:
        assert is_header_line(h), h


def test_c1_grep_yields_clean_distinct_markers():
    """step1_c1 GREP이 본문N-M을 잔재 없이 서로 다른 {본문N-M} 마커로 정규화."""
    out = [_grep_c1(h) for h in _C1_HEADERS[:7]]   # Further Reading은 승격 담당
    assert out[1] == "{본문2-1}" and out[2] == "{본문2-2}"
    assert out[4] == "{본문4-1}" and out[5] == "{본문4-2}"
    for o in out:
        assert _RE_MARKER.match(o), o          # `-1(p.18)` 잔재 없음
    assert len(set(out)) == len(out)           # 라벨 충돌 없음


def _build_plan():
    with open(_FIXTURE, encoding="utf-8") as f:
        content = json.load(f)
    plan = steps_to_plan(content.get("steps", {}), workbook_type="교과서")
    return content, plan


def test_plan_step1_c1_eight_clean_markers():
    """플랜: step1_c1이 지문 8개를 8개 클린 마커로 분리 (G24 마커 결손 0)."""
    _content, plan = _build_plan()
    c1 = next(f for f in plan["flows"] if f["step"] == "step1_c1")
    markers = [p["t"] for u in c1["units"]
               for p in (u["paras"] if isinstance(u, dict) else u)
               if _RE_MARKER.match((p.get("t") or "").strip())]
    assert len(markers) == 8, markers
    for lbl in ("{본문2-1}", "{본문2-2}", "{본문4-1}", "{본문4-2}"):
        assert lbl in markers, (lbl, markers)


def test_plan_step2_c2_no_header_leak():
    """플랜: step2_c2가 본문N-M 헤더 원문을 제거 (G1 [헤더잔존] 예방)."""
    _content, plan = _build_plan()
    c2 = next(f for f in plan["flows"] if f["step"] == "step2_c2")
    leaks = [p["t"] for u in c2["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)
             if is_header_line((p.get("t") or "").strip())]
    assert leaks == [], leaks


def test_gate_no_header_or_framebreak_critical():
    """게이트 완제품 검사: 플랜을 스토리 덤프로 근사해 [헤더잔존]/[프레임브레이크]
    critical이 없음을 확인 (수리 전엔 둘 다 발생)."""
    content, plan = _build_plan()
    # 각 플로우 → 스토리 하나(유닛 단락 이어붙임), 마커/본문이 '인쇄된' 상태.
    stories = []
    for idx, fl in enumerate(plan["flows"]):
        paras = [{"t": (p.get("t") or "") + "\r"}
                 for u in fl["units"]
                 for p in (u["paras"] if isinstance(u, dict) else u)]
        stories.append({"idx": idx, "pg": ["1"], "paragraphs": paras,
                        "fp": ["1"], "fb": [[10, 10, 280, 200]]})
    dump = {"stories": stories, "pages": [{"p": "1", "b": [0, 0, 297, 210]}],
            "overflow_stories": 0, "stale_pages": []}
    report = inspect_workbook_finish(content, plan, dump)
    bad = [c for c in report["critical"]
           if "[헤더잔존]" in c or "[프레임브레이크]" in c]
    assert bad == [], bad
