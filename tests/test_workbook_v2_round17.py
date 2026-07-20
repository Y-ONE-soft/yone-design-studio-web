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


# ── 게이트 G12 확장: 문장삽입 배경 — SRC 마커 한정 폐기 (결함 2 소급) ──────

_INSERT_Q = "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳을 고르시오."


def _plan_insert(bg=True):
    return {"flows": [{"step": "step3", "units": [[
        {"t": _INSERT_Q, "s": _ST_Q},
        {"t": "He would often do experiments.", "s": _ST_BG if bg else _ST_P},
        {"t": "Kelvin Doe has been fascinated with electronics.",
         "s": _ST_P},
    ]]}], "page_cleanup": {}}


def test_gate_g12_detects_insert_bg_missing_without_src_marker():
    """소급 검출 실증 — 수리 전 출력(6b66b750/round16: ❮주어진 문장❯
    지문 스타일, 출처 마커 없음)은 W15 SRC 한정 G12가 침묵하던 케이스.
    현행 플랜(배경 실림)과 어긋나면 critical."""
    dump = _dump([
        {"t": _INSERT_Q, "s": _ST_Q},
        {"t": "〈He would often do experiments.〉", "s": _ST_P},   # 결함
        {"t": "Kelvin Doe has been fascinated with electronics.",
         "s": _ST_P},
    ])
    rep = inspect_workbook_finish({}, _plan_insert(bg=True), dump)
    assert any("[문장삽입배경]" in c for c in rep["critical"])
    # 구플랜(배경 미실림 — W38 이전 산출) 소급은 warning
    rep2 = inspect_workbook_finish({}, _plan_insert(bg=False), dump)
    assert any("[문장삽입배경]" in w for w in rep2["warnings"])
    assert not any("[문장삽입배경]" in c for c in rep2["critical"])


def test_gate_g12_clean_and_variant_paths():
    # 정상: 주어진 문장 배경
    rep = inspect_workbook_finish({}, _plan_insert(), _dump([
        {"t": _INSERT_Q, "s": _ST_Q},
        {"t": "〈He would often do experiments.〉", "s": _ST_BG},
        {"t": "Kelvin Doe has been fascinated.", "s": _ST_P},
    ]))
    assert rep["stats"]["insert_bg_missing"] == 0
    # 재사용 변형: 주어진 문장 없이 곧장 선지 = 슬롯 부재 정상
    rep2 = inspect_workbook_finish({}, _plan_insert(), _dump([
        {"t": _INSERT_Q, "s": _ST_Q},
        {"t": "① (A)-(C)-(B)", "s": _ST_C},
        {"t": "② (B)-(A)-(C)", "s": _ST_C},
    ]))
    assert rep2["stats"]["insert_bg_missing"] == 0
    # step1_c1 자동 발문(하단 의미론 — STEP 01 스토리)은 대상 아님
    rep3 = inspect_workbook_finish({}, _plan_insert(), _dump([
        {"t": "아래 주어진 문장이 들어갈 위치로 알맞은 곳을 고르시오.",
         "s": "STEP 01 > C_문장 배열 하단 문제"},
        {"t": "It was under the sea.", "s": "STEP 01 > C_문장 배열 하단"},
    ]))
    assert rep3["stats"]["insert_bg_missing"] == 0


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


# ── 결함 2 / 아키텍처: 유형 주도 주어진 블록 슬롯 배정 ──────────────────────

def test_expects_given_block_from_measured_sequences():
    """block_sequences.json 실측이 배정의 입력 — 참조형(문장삽입/순서배열)
    만 발문 직후 배경 슬롯을 기대한다."""
    assert BG.expects_given_block("OBJ-FLW-INSERT")
    assert BG.expects_given_block("OBJ-FLW-ORDER")
    assert not BG.expects_given_block("OBJ-CTN-TOPIC")
    assert not BG.expects_given_block("SRV-WRT-SUMM")
    assert not BG.expects_given_block("OBJ-FLW-BLANK-AB")


def test_expects_given_block_prior_for_unclassified():
    # 유형 미분류 발문은 마커 문구가 프라이어
    assert BG.expects_given_block(None, "다음 글의 흐름으로 보아, 주어진 "
                                        "문장이 들어갈 곳으로 알맞은 것은?")
    # '주어진 표현'은 <보기> 내용물 참조 — 주어진 블록 아님 (0a5da924 실측)
    assert not BG.expects_given_block(
        None, "다음 글을 읽고, <보기>에 주어진 표현을 글의 흐름에 적절하도록 "
              "재배열하여 빈칸에 들어갈 말을 쓰시오.")
    # 빈칸 발문의 '들어가기에'는 프라이어 아님 (r2c02rp15 실측)
    assert not BG.expects_given_block(
        None, "다음 빈칸에 들어가기에 적절한 것은?(15-EX)")


def test_given_block_form():
    assert BG.is_given_block_form(
        "❮He would often do experiments with discarded electronics he "
        "found in trash cans to create his own inventions.❯")
    assert BG.is_given_block_form("Nothing is static.")
    # 구조 라벨/미완결 라인은 후보 아님
    assert not BG.is_given_block_form("[Unit 09 - Practice 01]")
    assert not BG.is_given_block_form("p32-no.5")
    assert not BG.is_given_block_form("주어진 문장")


def test_classifier_insert_given_sentence_wrapped():
    """87번 실증 — '주어진 문장'(❮…❯ 래퍼 → UNKNOWN)이 유형·위치·형태로
    배경에 배정된다. 마커 어휘 매칭이 아니라 하향식 배정 (68번 '주어진
    글'은 되고 87번 '주어진 문장'은 안 되던 결함의 해소)."""
    out = classify_paragraphs([
        {"text": "14. 글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 "
                 "적절한 곳을 고르시오."},
        {"text": "❮He would often do experiments with discarded "
                 "electronics he found in trash cans to create his own "
                 "inventions.❯"},
        {"text": "Kelvin Doe, a self-taught inventor and engineer from "
                 "Sierra Leone, has been fascinated with electronics "
                 "since childhood. ①In 2009, at the young age of "
                 "thirteen, Kelvin built his own FM radio station."},
    ])
    assert out[0]["kind"] == "Q" and out[0]["q_code"] == "OBJ-FLW-INSERT"
    assert out[1]["kind"] == "P-CONTEXT"
    assert out[2]["kind"] == "P"


def test_classifier_bracket_label_does_not_consume_slot():
    """구조 라벨("[Unit 09 - Practice 01]")은 발문과 본문 사이의 구조
    요소 — 슬롯을 소비하지 않고 씨앗 단락이 배경을 받는다 (r7c16 실측)."""
    out = classify_paragraphs([
        {"text": "주어진 글 다음에 이어질 글의 순서로 가장 적절한 것을 "
                 "고르시오."},
        {"text": "[Unit 09 - Practice 01]"},
        {"text": "According to natural law theory, moral principles are "
                 "grounded in human nature itself."},
        {"text": "(A) Natural law theorists believe that the natural "
                 "world reveals moral truths to careful observers."},
    ])
    assert out[1]["kind"] == "UNKNOWN"          # 라벨은 라벨대로
    assert out[2]["kind"] == "P-CONTEXT"        # 씨앗 = 배경
    assert out[3]["kind"] == "P"


def test_plan_given_slot_dual_defense_stale_kinds():
    """구 kind 주석(UNKNOWN/P) 재실행도 플랜 2패스가 배경으로 배정."""
    r = build_step3(_s3([
        {"text": "14. 글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 "
                 "적절한 곳을 고르시오.", "kind": "Q",
         "q_code": "OBJ-FLW-INSERT"},
        {"text": "❮He would often do experiments with discarded "
                 "electronics to create his own inventions.❯",
         "kind": "UNKNOWN"},
        {"text": "Kelvin Doe, a self-taught inventor and engineer from "
                 "Sierra Leone, has been fascinated with electronics "
                 "since childhood.", "kind": "P"},
    ]))
    styles = [p["s"] for p in r["units"][0]]
    assert styles[0] == _ST_Q
    assert styles[1] == _ST_BG
    assert styles[2] == _ST_P
    assert not r["warnings"]


def test_plan_given_slot_unassignable_warns():
    """기대 슬롯 배정 불가 = 침묵 강등 금지 — [경고] + 후보 지목."""
    r = build_step3(_s3([
        {"text": "14. 글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 "
                 "적절한 곳을 고르시오.", "kind": "Q",
         "q_code": "OBJ-FLW-INSERT"},
        {"text": "이 문단은 한국어 해설이라 주어진 블록 형태가 아니다. "
                 "발문 유형은 배경 단락을 기대하지만 배정할 수 없다.",
         "kind": "K"},
    ]))
    assert any("[슬롯]" in w for w in r["warnings"])


# ── 결함 3: 조건 블록 안 단어 나열 = 조건 내용물 ────────────────────────────

def test_cond_wordlist_form():
    assert BG.is_cond_wordlist("creator / with / Sierra Leone, / "
                               "Kelvin Doe, / electronics / from")
    assert BG.is_cond_wordlist("of / the young / at / thirteen / age")
    assert BG.is_cond_wordlist("team, teams, their, even though,")
    # 영문 완결 문장/한글 라인/답란 빈칸은 나열이 아니다
    assert not BG.is_cond_wordlist(
        "In 2009, at the young age of thirteen, Kelvin built his own "
        "FM radio station, a generator, and a windmill.")
    assert not BG.is_cond_wordlist("1) 11단어로 빈칸을 완성하시오.")
    assert not BG.is_cond_wordlist("_____________________________.")


def test_classifier_cond_block_wordlist_is_cond():
    """84/85번 실증 — 조건 항목("다음 단어를 …")이 참조하는 단어 나열은
    조건 블록의 내용물. 뒤따르는 답란 라벨("주제문:")은 흡수 금지."""
    out = classify_paragraphs([
        {"text": "11. 다음 글을 읽고, 주제문을 주어진 조건에 맞게 "
                 "완성하시오."},
        {"text": "Kelvin Doe, a self-taught inventor and engineer from "
                 "Sierra Leone, has been fascinated with electronics "
                 "since childhood and built his own FM radio station."},
        {"text": "[조건]"},
        {"text": "1) 11단어로 빈칸을 완성하시오."},
        {"text": "2) 다음 단어를 한 번씩 사용하여 배열하시오."},
        {"text": "creator / with / Sierra Leone, / Kelvin Doe, / "
                 "electronics / from / a self-educated / innovates"},
        {"text": "주제문:"},
        {"text": "__________________________________________."},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[2] == "Cond"
    assert kinds[3] == "Cond" and kinds[4] == "Cond"
    assert kinds[5] == "Cond", "단어 나열 = 조건 내용물"
    assert kinds[6] != "Cond", "답란 라벨은 조건 흡수 금지"


def test_classifier_cond_wordlist_then_paren_note_still_absorbed():
    """나열 뒤 괄호 부연("(필요시 …)")의 인접 흡수는 유지 (r15c25 실측
    — W30-r15 GH_SUBTITLE 상한 케이스 무회귀)."""
    out = classify_paragraphs([
        {"text": "<조건>"},
        {"text": "1. 20단어 이내로 작성할 것"},
        {"text": "2. 제시된 단어를 모두 사용할 것"},
        {"text": "- young, social, inspire, innovate"},
        {"text": "(필요시 단어의 형태를 변형하거나 단어 중복 사용 가능)"},
        {"text": "3. 완전한 문장이 되도록 작성할 것"},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[3] == "Cond" and kinds[4] == "Cond" and kinds[5] == "Cond"


def test_plan_cond_wordlist_dual_defense():
    """구 kind 주석(P/UNKNOWN) 재실행도 플랜 오버레이가 조건으로."""
    r = build_step3(_s3([
        {"text": "11. 다음 글을 읽고, 주제문을 주어진 조건에 맞게 "
                 "완성하시오.", "kind": "Q"},
        {"text": "[조건]", "kind": "Cond"},
        {"text": "1) 11단어로 빈칸을 완성하시오.", "kind": "Q"},
        {"text": "2) 다음 단어를 한 번씩 사용하여 배열하시오.", "kind": "Q"},
        {"text": "creator / with / Sierra Leone, / Kelvin Doe, / "
                 "electronics / from", "kind": "P"},
    ]))
    styles = [p["s"] for p in r["units"][0]]
    assert styles[1] == _ST_COND
    assert styles[2] == _ST_COND and styles[3] == _ST_COND
    assert styles[4] == _ST_COND, "단어 나열 = 조건 (플랜 이중 방어)"


def test_gate_g34_detects_wordlist_not_cond_style():
    """소급 검출 실증 — 수리 전 출력(round16: 나열이 지문 스타일)."""
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": "<조건>", "s": _ST_COND},
        {"t": "of / the young / at / thirteen / age", "s": _ST_COND},
    ]]}], "page_cleanup": {}}
    dump = _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "1) 6단어로 빈칸을 완성하시오.", "s": _ST_COND},
        {"t": "2) 다음 단어를 한 번씩 사용하여 배열하시오.", "s": _ST_COND},
        {"t": "of / the young / at / thirteen / age", "s": _ST_P},  # 결함
    ])
    rep = inspect_workbook_finish({}, plan, dump)
    assert rep["stats"]["cond_content_miss"] == 1
    assert any("[조건내용]" in c for c in rep["critical"])
    # 구플랜(조건 나열 미실림) 소급은 warning
    rep2 = inspect_workbook_finish(
        {}, {"flows": [], "page_cleanup": {}}, dump)
    assert any("[조건내용]" in w for w in rep2["warnings"])


# ── 결함 4: "주제문:" + 빈칸 = 답란 (AnsL — 선지 계열) ─────────────────────

def test_classifier_answer_label_blank_pair():
    """라벨 콜론 단독 라인 + 밑줄 빈칸 = 답란 쌍 (실물 v1 콜론형 답란 =
    S_선지 계열 실측 20a3838b 18건). 단독 빈칸(Ans)은 기존 관행 유지."""
    out = classify_paragraphs([
        {"text": "주제문:"},
        {"text": "__________________________________________."},
        {"text": ""},
        {"text": "________________________"},        # 단독 빈칸 = Ans 유지
    ])
    assert out[0]["kind"] == "AnsL"
    assert out[1]["kind"] == "AnsL"
    assert out[3]["kind"] == "Ans"


def test_answer_label_not_absorbed_by_box_propagation():
    out = classify_paragraphs([
        {"text": "<보기>"},
        {"text": "change / to / tackle / design"},
        {"text": "주제문:"},
        {"text": "____________________."},
    ])
    assert out[1]["kind"] == "Box"
    assert out[2]["kind"] == "AnsL" and out[3]["kind"] == "AnsL"


def test_plan_ansl_style_and_dual_defense():
    """AnsL → S_선지 올림포스 (실물 콜론형 답란 관행). 구 kind 주석
    (UNKNOWN) 재실행도 플랜 2패스가 쌍으로 배정."""
    r = build_step3(_s3([
        {"text": "11. 다음 글을 읽고, 주제문을 주어진 조건에 맞게 "
                 "완성하시오.", "kind": "Q"},
        {"text": "주제문:", "kind": "UNKNOWN"},
        {"text": "__________________________________________.",
         "kind": "UNKNOWN"},
    ]))
    styles = [p["s"] for p in r["units"][0]]
    assert styles[1] == _ST_C and styles[2] == _ST_C


def test_gate_g35_detects_answer_pair_styled_as_passage():
    """소급 검출 실증 — 수리 전 출력(round16: 주제문:/빈칸 지문 스타일)."""
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": "주제문:", "s": _ST_C},
        {"t": "____________________.", "s": _ST_C},
    ]]}], "page_cleanup": {}}
    dump = _dump([
        {"t": "주제문:", "s": _ST_P},                       # 결함
        {"t": "__________________________________________.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish({}, plan, dump)
    assert rep["stats"]["ansl_miss"] == 2
    assert any("[답란]" in c for c in rep["critical"])
    rep2 = inspect_workbook_finish(
        {}, {"flows": [], "page_cleanup": {}}, dump)
    assert any("[답란]" in w for w in rep2["warnings"])
    # 정상 경로 + 단독 빈칸(지문 관행)은 무지목
    rep3 = inspect_workbook_finish({}, plan, _dump([
        {"t": "주제문:", "s": _ST_C},
        {"t": "____________________.", "s": _ST_C},
        {"t": "다음은 재구성한 문장이다.", "s": _ST_P},
        {"t": "____________________", "s": _ST_P},
    ]))
    assert rep3["stats"]["ansl_miss"] == 0


# ── 결함 5: T/F 선택 행 = 선지 ──────────────────────────────────────────────

_TFQ = ("10. Choose True or False (T/F) based on the content of the "
        "following text.")


def test_tf_forms():
    assert BG.is_tf_question(_TFQ)
    assert BG.is_tf_question("다음 글의 내용과 일치하면 T, 일치하지 않으면 "
                             "F를 고르시오. (T/F)")
    assert not BG.is_tf_question("다음 글의 주제로 가장 적절한 것은?")
    assert BG.is_tf_choice_row(
        "1) Trisha Prabhu is a young scientist from the U.K. (T/F)")
    assert BG.is_tf_choice_row("5) Kelvin designed a generator. (O/X)")
    assert not BG.is_tf_choice_row("1) 9단어로 빈칸을 완성하시오.")
    assert not BG.is_tf_choice_row(
        "1) Trisha Prabhu is a young scientist.")   # 선택 표기 꼬리 없음


def test_classifier_tf_rows_are_choices():
    """111번 실증 — 진위 선택 문항의 'N) 문장 (T/F)' 행 = 선지."""
    out = classify_paragraphs([
        {"text": _TFQ},
        {"text": "Trisha Prabhu, Kelvin Doe, and John Michael Stagliano "
                 "are all examples of young social activists who have "
                 "made significant contributions to society."},
        {"text": "1) Trisha Prabhu is a young scientist from the U.K. "
                 "fighting cyberbullying. (T/F)"},
        {"text": "2) The text mentions that the efforts of these young "
                 "activists do not utilize technology. (T/F)"},
    ])
    assert out[0]["kind"] == "Q"
    assert out[1]["kind"] == "P"
    assert out[2]["kind"] == "C" and out[3]["kind"] == "C"


def test_plan_tf_rows_dual_defense_and_candidate_warning():
    r = build_step3(_s3([
        {"text": _TFQ, "kind": "Q"},
        {"text": "Trisha Prabhu and Kelvin Doe are young activists.",
         "kind": "P"},
        {"text": "1) Trisha Prabhu is a young scientist. (T/F)",
         "kind": "UNKNOWN"},
        {"text": "2) Kelvin built his own FM radio station.",
         "kind": "UNKNOWN"},          # 꼬리 없음 — 후보 지목
    ]))
    styles = [p["s"] for p in r["units"][0]]
    assert styles[2] == _ST_C
    assert styles[3] == _ST_P
    assert any("선지행(T/F) 후보" in w for w in r["warnings"])


def test_gate_g36_detects_tf_rows_styled_as_passage():
    """소급 검출 실증 — 수리 전 출력(round16: T/F 행 20개 지문 스타일)."""
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": "1) Trisha is a scientist. (T/F)", "s": _ST_C},
    ]]}], "page_cleanup": {}}
    dump = _dump([
        {"t": "Choose True or False (T/F) based on the content of the "
              "following text.", "s": _ST_Q},
        {"t": "Trisha Prabhu is fighting cyberbullying with ReThink.",
         "s": _ST_P},
        {"t": "1) Trisha Prabhu is a young scientist. (T/F)",
         "s": _ST_P},                                       # 결함
        {"t": "2) ReThink uses artificial intelligence. (T/F)",
         "s": _ST_P},                                       # 결함
    ])
    rep = inspect_workbook_finish({}, plan, dump)
    assert rep["stats"]["tf_choice_miss"] == 2
    assert any("[TF선지]" in c for c in rep["critical"])
    rep2 = inspect_workbook_finish(
        {}, {"flows": [], "page_cleanup": {}}, dump)
    assert any("[TF선지]" in w for w in rep2["warnings"])
    # 정상 경로
    rep3 = inspect_workbook_finish({}, plan, _dump([
        {"t": "Choose True or False (T/F) based on the text.",
         "s": _ST_Q},
        {"t": "1) Trisha Prabhu is a young scientist. (T/F)", "s": _ST_C},
    ]))
    assert rep3["stats"]["tf_choice_miss"] == 0


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
