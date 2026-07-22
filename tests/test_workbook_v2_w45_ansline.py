"""W45 — 답란 전용 단락스타일 `S_답란` 신설 + 매핑 전환 가드.

배경(역학습 W44): 답란("(A): _____", "주제문: ____")을 현행 판정기는 선지
스타일로 처리하는데 완성 조판본 다수(61건/13문서)는 지문 스타일이었다.
사용자 확인: 선지 스타일의 들여쓰기 때문에 답란 정렬이 깨져 손으로 지문
스타일로 바꾼 것 — 완성본의 지문 스타일은 의도가 아니라 **회피**다.

확정 스펙:
  - 답란은 답란 전용 스타일 `S_답란`(지문 스타일 복제 + 들여쓰기 0)로 인쇄
  - 템플릿에 아직 없을 수 있으므로 fail-open: 플랜이 s=S_답란 + s_fb=선지 +
    ind0=true 를 함께 실어 렌더가 폴백 + 들여쓰기 0 브릿지를 적용
  - 게이트 G44: 템플릿에 S_답란이 있는데 미적용이면 critical, 없으면 warning
  - 채점기: 회피 관행 행을 태깅해 정답을 S_답란으로 재정의
"""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from engines.workbook_v2.gate import inspect_workbook_finish    # noqa: E402
from engines.workbook_v2.plan import build_step3                # noqa: E402

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_C = "STEP 03 > S_선지 올림포스"
_ST_BOX = "STEP 03 > 보기 올림포스"
_ST_ANSL = "STEP 03 > S_답란"


def _s3(paras):
    return {"normal": [{"question_num": 1, "paragraphs": paras}]}


def _dump(paras):
    return {"stories": [{"idx": 0, "pg": ["1"], "paragraphs": paras}],
            "stale_pages": []}


# ── 매핑 전환 ───────────────────────────────────────────────────────────────

def test_plan_ansline_style_with_fallback():
    """콜론형 답란 쌍 → S_답란 + 폴백/브릿지 필드."""
    unit = build_step3(_s3([
        {"text": "11. 다음 글을 읽고 주제문을 완성하시오.", "kind": "Q"},
        {"text": "주제문:", "kind": "UNKNOWN"},
        {"text": "_" * 40, "kind": "UNKNOWN"},
    ]))["units"][0]
    assert [p["s"] for p in unit[1:]] == [_ST_ANSL, _ST_ANSL]
    assert all(p["s_fb"] == _ST_C and p["ind0"] is True for p in unit[1:])
    # 답란이 아닌 단락에는 폴백/브릿지 필드가 붙지 않는다 (기존 무영향)
    assert "s_fb" not in unit[0] and "ind0" not in unit[0]


def test_plan_paren_ansline_style():
    """보기 블록 뒤 괄호 라벨 답란도 S_답란."""
    unit = build_step3(_s3([
        {"text": "<보기 B>", "kind": "Box"},
        {"text": "what / on / help / and", "kind": "Box"},
        {"text": "(A) " + "_" * 50, "kind": "Box"},
        {"text": "(B) " + "_" * 50, "kind": "Box"},
    ]))["units"][0]
    assert unit[2]["s"] == _ST_ANSL and unit[3]["s"] == _ST_ANSL
    assert unit[1]["s"] == _ST_BOX


# ── 게이트 G44 ──────────────────────────────────────────────────────────────

_PLAN_ANSL = {"flows": [{"step": "step3", "units": [[
    {"t": "<보기 B>", "s": _ST_BOX},
    {"t": "what / on / help", "s": _ST_BOX},
    {"t": "(A) " + "_" * 50, "s": _ST_ANSL, "s_fb": _ST_C, "ind0": True},
]]}]}


def test_gate_g44_critical_when_style_exists_but_unused():
    """템플릿에 S_답란이 있는데(문서 어딘가 사용됨) 답란에 미적용 = critical."""
    dump = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 50 + "\r", "s": _ST_C},        # 결함
        {"t": "주제문:\r", "s": _ST_ANSL},                   # 스타일 존재 근거
        {"t": "_" * 40 + ".\r", "s": _ST_ANSL},
    ])
    rep = inspect_workbook_finish({}, _PLAN_ANSL, dump)
    assert rep["stats"]["ansline_style_present"] is True
    assert rep["stats"]["ansline_style_miss"] == 1
    assert any("[답란스타일]" in c for c in rep["critical"])


def test_gate_g44_warns_when_template_lacks_style():
    """템플릿에 S_답란이 없으면 선지 폴백 — fail-open (warning만)."""
    dump = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 50 + "\r", "s": _ST_C},
    ])
    rep = inspect_workbook_finish({}, _PLAN_ANSL, dump)
    assert rep["stats"]["ansline_style_present"] is False
    assert rep["stats"]["ansline_style_miss"] == 0
    assert not any("[답란스타일]" in c for c in rep["critical"])
    assert any("[답란스타일]" in w for w in rep["warnings"])


def test_gate_g44_ok_when_applied():
    dump = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 50 + "\r", "s": _ST_ANSL},
    ])
    rep = inspect_workbook_finish({}, _PLAN_ANSL, dump)
    assert rep["stats"]["ansline_style_miss"] == 0
    assert not any("[답란스타일]" in m
                   for m in rep["critical"] + rep["warnings"])


def test_gate_g35_g40_accept_ansline_style():
    """기존 답란 계약(G35/G40)은 S_답란도 답란 계열로 인정 (회귀 방지)."""
    dump = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 50 + "\r", "s": _ST_ANSL},
        {"t": "주제문:\r", "s": _ST_ANSL},
        {"t": "_" * 40 + ".\r", "s": _ST_ANSL},
    ])
    rep = inspect_workbook_finish({}, _PLAN_ANSL, dump)
    assert rep["stats"]["paren_blank_miss"] == 0
    assert rep["stats"]["ansl_miss"] == 0


# ── 채점기 태깅 ─────────────────────────────────────────────────────────────

def test_score_avoidance_tagging():
    import score_against_truth as S
    assert S.ansline_avoidance(_ST_ANSL, _ST_P, "(A): " + "_" * 40)
    assert S.ansline_avoidance(_ST_C, _ST_P, "주제문:")
    # 완성본이 이미 답란 계열이면 회피가 아니다
    assert not S.ansline_avoidance(_ST_ANSL, _ST_C, "(A): " + "_" * 40)
    # 답란 형태가 아니면 태깅하지 않는다 (진짜 오답은 그대로 오답)
    assert not S.ansline_avoidance(_ST_C, _ST_P,
                                   "① Fussen is the final stop.")


def test_score_retag_makes_avoidance_rows_correct():
    import score_against_truth as S
    rows = [{"job": "j", "step": "step3", "unit": 0, "idx": 0,
             "text": "(A): " + "_" * 40, "gold_style": _ST_P,
             "gold_text": "(A): " + "_" * 40, "doc": "d", "series": "워크북",
             "human_edited": True, "align_conf": 1.0}]
    preds = {"j": {"idx": {("step3", 0, 0): (rows[0]["text"], _ST_ANSL)},
                   "bykey": {}}}
    res, _ = S.score(rows, preds, ansline_retag=True)
    assert res[0]["tag"] == S.AVOIDANCE_TAG and res[0]["ok"] is True
    res2, _ = S.score(rows, preds, ansline_retag=False)
    assert res2[0]["tag"] == S.AVOIDANCE_TAG and res2[0]["ok"] is False
