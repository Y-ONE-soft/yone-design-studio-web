"""W39 — 유형 주도 하향식 슬롯 배정 전환 + 실사용 지목 결함 6건 가드.

결함 (공통영어2 YBM(김) 1과 워크북 v2, 2026-07-20 산출 — 문항 번호는
전권 통산: 68=2부9, 84/85=3부11/12, 87=3부14, 111=5부10):
  1. <요약문> 꺾쇠형도 배경 (대괄호형과 동일 — Box 관행 폐기, 사용자 확정)
  2. 87 "주어진 문장"(❮…❯) 블록 미처리 — 유형 주도 배정으로 해소
     (마커 어휘 추가로 때우지 않는다: 전환의 검증 케이스)
  3. 84/85 조건 블록 안 단어 나열("creator / with / …")은 조건
  4. 84/85 "주제문:" + 빈칸 = 답란 (실물 v1 콜론형 답란 = S_선지 계열)
  5. 111 "N) 문장 (T/F)" 선택 행 = 선지
  6. 발문의 "밑줄 친 <영어구>" 인용은 밑줄 렌더 (원고 runs 없어도 —
     대상 특정이 모호하면 [경고], 임의 밑줄 금지)

아키텍처: 발문 taxonomy 유형 → block_sequences.json 실측 시퀀스가 배정의
입력(expects_given_block). 마커 문구는 프라이어로 강등 — 미지의 표현
("주어진 표현/어구")이어도 유형·위치·형태가 맞으면 배정.
"""
import json
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

from core.structure import block_grammar as BG                  # noqa: E402
from core.structure import classify_paragraphs                  # noqa: E402
from engines.workbook_v2.gate import inspect_workbook_finish    # noqa: E402
from engines.workbook_v2.plan import build_step3                # noqa: E402

_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_COND = "STEP 03 > 조건 올림포스"
_ST_BG = "STEP 03 > 배경 올림포스"
_ST_C = "STEP 03 > S_선지 올림포스"
_ST_BOX = "STEP 03 > 보기 올림포스"

_DELETE_PLAN = {"flows": [], "page_cleanup": {"empty": "delete"}}


def _dump(paras, **kw):
    d = {"stories": [{"idx": 0, "pg": ["1"], "paragraphs": paras}],
         "stale_pages": []}
    d.update(kw)
    return d


def _s3(paras):
    return {"normal": [{"question_num": "t", "paragraphs": paras}],
            "short": []}


# ── 결함 1: <요약문> 꺾쇠형도 배경 ──────────────────────────────────────────

def test_classifier_sum_angle_marker_background():
    out = classify_paragraphs([
        {"text": "38. 다음 글의 내용을 한 문장으로 요약하시오."},
        {"text": "There are a lot of things that fill us with hope for "
                 "the future: technology, science, and accountable "
                 "leaders committed to doing good."},
        {"text": "<요약문>"},
        {"text": "Young people provide significant (A)__________ for the "
                 "future by actively addressing (B)__________ problems."},
        {"text": "① potential ┈ educational"},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[2] == "Sum"
    assert kinds[3] == "P-CONTEXT"
    assert kinds[4] == "C"


def test_plan_sum_angle_stale_box_kinds_get_background():
    """구 kind 주석(꺾쇠=Box 시절) 재실행도 배경으로 — 플랜 이중 방어.
    선지 행(①~⑤/(A) 헤더)은 stale Box여도 배경 전파가 멈춘다."""
    r = build_step3(_s3([
        {"text": "38. 다음 글의 내용을 요약하시오.", "kind": "Q"},
        {"text": "<요약문>", "kind": "Box"},
        {"text": "Young people provide (A)_____ for the future.",
         "kind": "Box"},
        {"text": "(A)\t    (B)", "kind": "Box"},
        {"text": "① potential ┈ educational", "kind": "Box"},
    ]))
    styles = [p["s"] for p in r["units"][0]]
    assert styles[1] == _ST_BG and styles[2] == _ST_BG
    assert styles[3] == _ST_BOX and styles[4] == _ST_BOX  # 전파 정지
    assert not r["warnings"]


def test_gate_g32_detects_angle_sum_marker_not_background():
    """소급 검출: 수리 전 출력(꺾쇠 요약문 = 보기/지문 스타일) 재현."""
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": "<요약문>", "s": _ST_BG},
        {"t": "Young people provide hope.", "s": _ST_BG},
    ]]}], "page_cleanup": {}}
    rep = inspect_workbook_finish({}, plan, _dump([
        {"t": "<요약문>", "s": _ST_BOX},
        {"t": "Young people provide hope.", "s": _ST_BOX},
    ]))
    assert any("[요약문배경]" in c for c in rep["critical"])
