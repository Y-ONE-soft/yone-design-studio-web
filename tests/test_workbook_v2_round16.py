"""W38 — 문항 내부 블록 문법 확립 + 실서비스 job 6b66b750 지목 결함 5건 가드.

결함 (공통영어2 YBM(김) 1과 워크북, 2026-07-20 실사용 출력):
  1. 크레딧 뒤 M-R 잔여 — 스펙 정정: 크레딧-L = 문서 마지막 (책은 왼쪽 끝)
  2. 빈칸어휘/빈칸어법 지문번호 프레임 좌/우 크기 불일치 (L 8.9 vs R 7.72mm)
  3. <조건> 블록 안 "1) …시오." 번호 항목이 발문 취급 (W16 D3 폐기)
  4. [요약문] 마커+요약 문장 배경 누락 (지문 스타일 인쇄)
  5. 영어 지시문 발문("10. Choose True or False …") 지문 취급

블록 문법: core/structure/block_grammar.py — 블록 진입 마커가 열리면 후속
라인 판정은 블록 문맥이 제약. 유형별 기대 시퀀스는 block_sequences.json
(실측 수집), 하드 불변식 위반은 validate_sequence가 [경고] 지목.
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

_DELETE_PLAN = {"flows": [], "page_cleanup": {"empty": "delete"}}


def _dump(paras, **kw):
    d = {"stories": [{"idx": 0, "pg": ["1"], "paragraphs": paras}],
         "stale_pages": []}
    d.update(kw)
    return d


# ── 블록 문법 단위: cond_item_take (실측 규칙) ──────────────────────────────

def test_cond_item_take_paren_always_item():
    assert BG.cond_item_take("1) 9단어로 빈칸을 완성하시오.", 1) == (True, 2)
    assert BG.cond_item_take("2) 다음 단어를 한 번씩 사용하여 배열하시오.",
                             2) == (True, 3)


def test_cond_item_take_dot_sequence_continuation():
    # ebs r8c18 실증: "1.(A)는 … 쓰시오." / "2.(B)는 … 쓰시오"
    assert BG.cond_item_take("1.(A)는 본문에서 찾아 변형하여 한단어로 쓰시오.",
                             1) == (True, 2)
    # r6c10 실증: "2. 아래의 우리말 해석을 …" — '아래의'는 '아래 글'이 아님
    assert BG.cond_item_take(
        "2. 아래의 우리말 해석을 예시와 같은 강조구문을 이용하여 "
        "영작하시오.", 2) == (True, 3)


def test_cond_item_take_true_question_closes_block():
    # 번호 시퀀스 이탈 (supp 실증 "22. 다음 글의 내용을 …")
    take, no = BG.cond_item_take(
        "22. 다음 글의 내용을 한 문장으로 요약하고자 한다.", 2)
    assert not take and no == 2
    # 첫 항목 기대 시점 + 발문 어휘 선두
    take, _ = BG.cond_item_take("1. 다음 글의 밑줄 친 부분 중 어색한 것은?", 1)
    assert not take


def test_cond_item_take_bullet_item():
    assert BG.cond_item_take("· 우리말과 같은 의미가 되도록 영작하시오.",
                             1) == (True, 1)


# ── 블록 문법 단위: 영어 발문 / 요약문 마커 ────────────────────────────────

def test_english_question_recognition():
    assert BG.is_english_question(
        "10. Choose True or False (T/F) based on the content of the "
        "following text.")
    assert BG.is_english_question(
        '71. What makes the song "For Good" moving according to the '
        "text? [SL2-4]")
    # 번호 없는 명령문(지문 문장)·소문자 계속행·T/F 진술문은 발문 아님
    assert not BG.is_english_question("Let's look at three examples.")
    assert not BG.is_english_question(
        "44. as though it were their own, crying when they see")
    assert not BG.is_english_question(
        "1) Trisha Prabhu is a young scientist from the U.K. (T/F)")


def test_sum_marker_forms():
    assert BG.SUM_MARKER.match("[요약문]")
    assert BG.SUM_MARKER.match("요약문")
    # W39 결함 1 (사용자 확정 — W38 '꺾쇠형=Box 관행 유지' 폐기):
    # 꺾쇠형도 대괄호형과 동일한 배경 블록 마커다.
    assert BG.SUM_MARKER.match("<요약문>")
    assert BG.SUM_MARKER.match("<요약>")
    # 보기 마커는 여전히 Box (요약문 계열만 Sum)
    assert not BG.SUM_MARKER.match("<보기>")


# ── 분류기: 결함 3/4/5 파서 계층 가드 ───────────────────────────────────────

def test_classifier_summary_block_background():
    out = classify_paragraphs([
        {"text": "38. 다음 글의 내용을 한 문장으로 요약하고자 한다. "
                 "빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?"},
        {"text": "There are a lot of things that fill us with hope for "
                 "the future: technology, science, and accountable "
                 "leaders committed to doing good."},
        {"text": "[요약문]"},
        {"text": "Young people provide significant (A)__________ for the "
                 "future by actively addressing (B)__________ problems."},
        {"text": "① potential ┈ educational"},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[2] == "Sum"
    assert kinds[3] == "P-CONTEXT", "요약 문장 = 배경"
    assert kinds[4] == "C"


def test_classifier_english_tf_question():
    out = classify_paragraphs([
        {"text": "10. Choose True or False (T/F) based on the content of "
                 "the following text."},
        {"text": "There are a lot of things that fill us with hope for "
                 "the future: technology, science, and accountable "
                 "leaders committed to doing good."},
        {"text": "1) Trisha Prabhu is a young scientist. (T/F)"},
    ])
    assert out[0]["kind"] == "Q"
    assert out[1]["kind"] == "P"
    assert out[2]["kind"] != "Q", "T/F 진술문은 발문 아님"


# ── validate_sequence 하드 불변식 ───────────────────────────────────────────

def test_validate_sequence_flags_defective_shapes():
    warns = BG.validate_sequence([
        ("Q", "11. 다음 글을 읽고, 주제문을 완성하시오."),
        ("Q", "1) 9단어로 빈칸을 완성하시오."),      # 번호 재시작 발문
    ])
    assert any("발문 직후 번호 재시작" in w for w in warns)
    warns2 = BG.validate_sequence([
        ("Cond", "<조건>"),
        ("Q", "다음 글의 주제는?"),                  # 항목 0 고아 마커
    ])
    assert any("고아 마커" in w for w in warns2)
    warns3 = BG.validate_sequence([
        ("Sum", "[요약문]"),
        ("C", "① potential"),                       # 배경 문장 0
    ])
    assert any("요약문 마커 뒤 배경 문장 0" in w for w in warns3)


def test_validate_sequence_clean_on_healthy_unit():
    warns = BG.validate_sequence([
        ("Q", "38. 다음 글의 내용을 한 문장으로 요약하고자 한다."),
        ("P", "There are a lot of things."),
        ("Sum", "[요약문]"),
        ("P-CONTEXT", "Young people provide hope."),
        ("C", "① potential"),
        ("Q", "39. 다음 글의 제목으로 가장 적절한 것은?"),  # 연번 발문 나열
        ("Q", "40. 다음 글의 주제로 가장 적절한 것은?"),
    ])
    assert warns == []


# ── 플랜 계층 이중 방어 (구 kind 주석 재실행) ───────────────────────────────

def test_plan_block_overlay_with_stale_annotations():
    """구버전 kind 주석(조건 항목=Q, 요약문=UNKNOWN)이어도 플랜 계층
    블록 문맥 오버레이가 스타일을 교정한다 (W16 D2 이중 방어 전례)."""
    out = build_step3({"normal": [{"question_num": "textbook", "paragraphs": [
        {"text": "11. 다음 글을 읽고, 주제문을 주어진 조건에 맞게 "
                 "완성하시오.", "kind": "Q"},
        {"text": "[조건]", "kind": "Cond"},
        {"text": "1) 9단어로 빈칸을 완성하시오.", "kind": "Q"},
        {"text": "2) 다음 단어를 한 번씩 사용하여 배열하시오.", "kind": "Q"},
        {"text": "[요약문]", "kind": "UNKNOWN"},
        {"text": "Young people provide significant hope for the future.",
         "kind": "P"},
        {"text": "10. Choose True or False (T/F) based on the content of "
                 "the following text.", "kind": "UNKNOWN"},
    ]}], "short": []})
    paras = out["units"][0]

    def style_of(prefix):
        return next(p["s"] for p in paras if p["t"].startswith(prefix))

    assert style_of("1) 9단어로") == _ST_COND
    assert style_of("2) 다음 단어를") == _ST_COND
    assert style_of("[요약문]") == _ST_BG
    assert style_of("Young people") == _ST_BG
    # 영어 발문 — Q 스타일 + 번호 제거
    assert any(p["s"] == _ST_Q and p["t"].startswith("Choose True")
               for p in paras)
    assert out["warnings"] == []


def test_plan_cond_overlay_not_promoted_by_sio():
    """플랜 오버레이(_s3_effective_kind)의 '시오→Q 승격'이 조건 블록 안
    불릿/번호 항목을 발문 스타일로 되돌리지 않는다 (r4c03essay 잠복 실증:
    Cond 주석 + 시오-체 불릿이 발문 스타일로 인쇄되던 결함)."""
    out = build_step3({"normal": [{"question_num": "textbook", "paragraphs": [
        {"text": "<조건>", "kind": "Cond"},
        {"text": "· 우리말과 같은 의미가 되도록 영작하시오.", "kind": "Cond"},
        {"text": "· 10단어를 넘지 마시오. (의미가 같아도 감점)",
         "kind": "Cond"},
    ]}], "short": []})
    styles = [p["s"] for p in out["units"][0]]
    assert styles == [_ST_COND, _ST_COND, _ST_COND]
    assert out["warnings"] == []


# ── 게이트: G32 요약문배경 (양방향) ─────────────────────────────────────────

_SUM_PLAN = {"flows": [{"step": "step3", "units": [[
    {"t": "[요약문]", "s": _ST_BG},
    {"t": "Young people provide hope.", "s": _ST_BG},
]]}], "page_cleanup": {"empty": "delete"}}


def test_gate_g32_detects_summary_without_background():
    rep = inspect_workbook_finish({}, _SUM_PLAN, _dump([
        {"t": "[요약문]", "s": _ST_P},                       # 수리 전 출력
        {"t": "Young people provide hope.", "s": _ST_P},
    ]))
    assert any("[요약문배경]" in c for c in rep["critical"])
    assert rep["stats"]["sum_bg_miss"] == 1


def test_gate_g32_old_plan_downgrades_to_warning():
    rep = inspect_workbook_finish({}, {"flows": []}, _dump([
        {"t": "[요약문]", "s": _ST_P},
        {"t": "Young people provide hope.", "s": _ST_P},
    ]))
    assert not any("[요약문배경]" in c for c in rep["critical"])
    assert any("[요약문배경]" in w for w in rep["warnings"])


def test_gate_g32_clean_when_background_applied():
    rep = inspect_workbook_finish({}, _SUM_PLAN, _dump([
        {"t": "[요약문]", "s": _ST_BG},
        {"t": "Young people provide hope.", "s": _ST_BG},
        {"t": "① potential ┈ educational", "s": "STEP 03 > S_선지 올림포스"},
    ]))
    assert rep["stats"]["sum_bg_miss"] == 0


# ── 게이트: G13 영어 발문 확장 (양방향 + WH 반례) ───────────────────────────

def test_gate_g13_detects_english_imperative_as_passage():
    rep = inspect_workbook_finish({}, _DELETE_PLAN, _dump([
        {"t": "10. Choose True or False (T/F) based on the content of the "
              "following text.", "s": _ST_P},                # 수리 전 출력
    ]))
    assert any("[발문스타일]" in c and "Choose" in c for c in rep["critical"])


def test_gate_g13_clean_english_paths():
    rep = inspect_workbook_finish({}, _DELETE_PLAN, _dump([
        # 정상 출력: Q 스타일 + 번호 제거 (번호 접두 없음 = 시그니처 미해당)
        {"t": "Choose True or False (T/F) based on the content of the "
              "following text.", "s": _ST_Q},
        # r11 외부지문 실측 반례: WH-의문형 '지문 제목'은 기본 단락이 정상
        {"t": "7. Why don't we think different more often?",
         "s": "[기본 단락]"},
        # 번호 잔존이라도 T/F 진술문은 미해당
        {"t": "1) Trisha Prabhu is a young scientist. (T/F)", "s": _ST_P},
    ]))
    assert rep["stats"]["q_style_miss"] == 0


# ── 게이트: G33 라벨 프레임 좌/우 기하 (양방향) ─────────────────────────────

_G33_PLAN = {"flows": [], "page_cleanup": {"empty": "delete"},
             "passage_numbers": {"labels": ["본문1", "본문2"],
                                 "steps": ["step1_c2"]}}


def _g33_dump(right_w):
    pages = [{"p": "34", "m": "O-마스터", "side": "L", "empty": False},
             {"p": "35", "m": "O-마스터", "side": "R", "empty": False}]
    x2 = 12.78 + right_w
    stories = [
        {"idx": 1, "pg": ["34"], "fb": [[32, 9.6, 84.92, 18.5]],
         "paragraphs": [{"t": "본문1", "s": ""}]},
        {"idx": 2, "pg": ["35"], "fb": [[32, 12.78, 84.92, x2]],
         "paragraphs": [{"t": "본문2", "s": ""}]},
    ]
    return {"stories": stories, "pages": pages, "stale_pages": []}


def test_gate_g33_detects_lr_width_mismatch():
    rep = inspect_workbook_finish({}, _G33_PLAN, _g33_dump(7.72))
    assert any("[라벨프레임기하]" in c for c in rep["critical"])
    assert rep["stats"]["label_frame_lr_bad"] == 1


def test_gate_g33_clean_when_normalized():
    rep = inspect_workbook_finish({}, _G33_PLAN, _g33_dump(8.9))
    assert rep["stats"]["label_frame_lr_bad"] == 0


def test_gate_g33_skips_old_dump_without_fb():
    d = _g33_dump(7.72)
    for s in d["stories"]:
        s.pop("fb")
    rep = inspect_workbook_finish({}, _G33_PLAN, d)
    assert not any("[라벨프레임기하]" in c
                   for c in rep["critical"] + rep["warnings"])


# ── 실행기 소스 가드 (결함 1/2) ─────────────────────────────────────────────

def test_executor_credit_no_trailing_memo():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "판권 오른쪽 메모(M) 페이지 추가" not in src, \
        "W38 스펙 정정: 크레딧 뒤 메모 페이지를 붙이지 않는다"
    assert "왼쪽 정렬 — 책 끝" in src


def test_executor_label_frame_lr_normalization():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "라벨 프레임 좌우 크기 통일" in src
    assert "canonW" in src and "pageSideOf(doc, labelFrames" in src


# ── 유형별 블록 시퀀스 데이터 (실측 수집물 존재/정합) ────────────────────────

def test_block_sequences_data_collected():
    data = BG.load_block_sequences()
    assert data.get("sequences"), "block_sequences.json 실측 수집물 필요"
    assert data["_source"]["units"] >= 900
    # 요약문 유형: 수리 후 시퀀스에 SUM+PC가 관측된다
    summ = data["sequences"].get("OBJ-SUM-BLANK-AB") or {}
    if summ:
        assert any("SUM" in s for s in summ.get("observed", {}))
