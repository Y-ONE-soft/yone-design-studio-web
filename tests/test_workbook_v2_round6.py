"""W16 품질 루프 6라운드 가드 — 후보⑦(EBS 리딩파워 유형편(완성) Unit17
Step3.hwp, [REVIEW N강-N번]형) + 후보⑩(15개정 천재(이) 8과 서술형 hwpx —
후보⑨ 동형 파이널 문장배열은 파이널 v1 관할이라 대체).

결함 재현→수리 고정:
  D1 [서술형 N] 접두 + 해요체("쓰세요") 발문이 지문 스타일 (c07 실증)
     → 플랜 오버레이 _s3_effective_kind 확장 + 게이트 G13
  D2 WORD_DEF 과광폭 — 대화문 화자 라벨("Minji:"/"A: …")·영문 제목이
     영단어 스타일 (c10 실증 6건 + c04 안내문 필드 27건·80dd3fa2 잠복.
     v1 실물: 전부 지문 스타일) → WORD_DEF 한글 뜻 + 2+글자 머리 + G14
  D3 <조건> 블록 항목 스타일 공백 3경로 (c10 실증 + c04/c05/0a5da924
     잠복) — (a) 영어 어구 나열에서 propagation 중단 → v1 pass 15
     의미론(skip-계속), (b) ◦⦁ㆍ∙ 불릿 마커 미등록, (c) 조건 문구가
     taxonomy 발문으로 오매칭(Q) → 무힌트 + '것' 종결 강등 + G15
"""
import json
import os

from core.structure.paragraph_kind import classify_paragraphs
from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_v2.plan import build_step3

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_COND = "STEP 03 > 조건 올림포스"
_ST_WORD = "STEP 03 > 영단어"

_SEYO_Q = ("[서술형 2] 다음 글의 밑줄 친 without을 if로 시작하여 바꿔 쓸 때 "
           "빈칸에 들어갈 알맞은 표현을 쓰세요. [리딩파워, Chapter4 Review "
           "17강 3번]")


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


def _plan_stub():
    return {"flows": [{"step": "step3", "units": [[{"t": "x"}]]}]}


# ── D1 게이트 G13: 발문 스타일 누락 — 수리 전 상태 재현으로 검출 실증 ─────────

def test_gate_g13_detects_seyo_question_as_passage():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": _SEYO_Q, "s": _ST_P},                     # 수리 전: 지문 스타일
    ]))
    assert any("[발문스타일]" in c for c in rep["critical"])
    assert rep["stats"]["q_style_miss"] == 1


def test_gate_g13_clean_when_question_styled():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": _SEYO_Q, "s": _ST_Q},
        # 시오-체 발문 (기존 정상 경로)
        {"t": "다음 글의 주제로 가장 적절한 것을 고르시오.", "s": _ST_Q},
        # 지문/선지/조건 단락은 시그니처 미해당 — false positive 방지
        {"t": "다음 주어진 예시처럼 강조 구문을 만들어 보자.", "s": _ST_P},
        {"t": "주어진 표현으로 시작할 것", "s": _ST_COND},
        {"t": "[REVIEW 17강-2번]", "s": _ST_P},          # 단독 마커 무해
    ]))
    assert rep["stats"]["q_style_miss"] == 0


# ── D2 게이트 G14: 영단어 오분류 — 수리 전 상태 재현으로 검출 실증 ────────────

def test_gate_g14_detects_non_vocab_word_style():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "Minji:", "s": _ST_WORD},                       # 화자 라벨
        {"t": "Gijisi Juldarigi Festival: A Celebration of Tradition",
         "s": _ST_WORD},                                      # 영문 제목
        {"t": "A: 노란색 코트를 입고 있는 저 여자 아이는 누구야?",
         "s": _ST_WORD},                                      # 1글자 머리
        {"t": "Dates: July 5-7, 2025", "s": _ST_WORD},        # 안내문 필드
    ]))
    assert any("[영단어오분류]" in c for c in rep["critical"])
    assert rep["stats"]["word_style_bad"] == 4


def test_gate_g14_clean_for_real_vocab():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "inherit: 물려받다", "s": _ST_WORD},
        {"t": "*extensively 널리, 광범위하게", "s": _ST_WORD},
        {"t": "Minji: Now, what does juldarigi mean to you?",
         "s": _ST_P},                                    # 지문 스타일이면 무관
    ]))
    assert rep["stats"]["word_style_bad"] == 0


# ── D3 게이트 G15: 조건 항목 스타일 — 수리 전 상태 재현으로 검출 실증 ─────────

def test_gate_g15_detects_condition_items_styled_as_passage():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "team, teams, their, even though,", "s": _ST_P},   # 어구 (skip)
        {"t": "both, tried, won, best, my", "s": _ST_P},         # 어구 (skip)
        {"t": "1. 위 단어들을 어형변화 없이 모두, 한 번씩만 사용할 것",
         "s": _ST_P},                                    # 수리 전: 지문
        {"t": "2. 위 단어들 외에 3개의 단어를 추가하여 '나의 팀'을 강조하는 "
              "문장으로 완성할 것", "s": _ST_P},
        {"t": "정답: ___________________", "s": _ST_P},   # 답란 = 블록 종료
    ]))
    assert any("[조건항목]" in c for c in rep["critical"])
    assert rep["stats"]["cond_item_miss"] == 2


def test_gate_g15_detects_bullet_items():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "◦ It(가주어), that(진주어)를 활용할 것", "s": _ST_COND},
        {"t": "◦ Gijisi juldarigi, couples, a child를 활용할 것",
         "s": _ST_P},                                    # 수리 전 (c10 실증)
        {"t": "⦁(1)은 Only later로 시작할 것", "s": _ST_P},  # c05 잠복 셰이프
    ]))
    assert rep["stats"]["cond_item_miss"] == 2


def test_gate_g15_clean_paths():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "- 관계대명사 활용", "s": _ST_COND},
        {"t": "정답: ___________________", "s": _ST_P},
        # 별도 블록: 시오-체 번호 항목은 발문 유지가 v1 실물 관행 (4ed24266)
        {"t": "<조건>", "s": _ST_COND},
        {"t": "1.(A)는 본문에서 찾아 변형하여 한단어로 쓰시오.", "s": _ST_Q},
        {"t": "2.(B)는 본문에서 찾아 한 단어로 쓰시오", "s": _ST_Q},
        # 별도 블록: 발문 시작 신호 발문 = 블록 종료
        {"t": "<조건>", "s": _ST_COND},
        {"t": "다음 글의 주제로 가장 적절한 것은?", "s": _ST_Q},
        # 별도 블록: 영어 어구 나열은 지문 유지 (v1 실물 관행 — c15/wordlist)
        {"t": "<조건>", "s": _ST_COND},
        {"t": "end / plot / have / it / a / me / keep / from", "s": _ST_P},
        {"t": "→ ____________________", "s": _ST_P},
    ]))
    assert rep["stats"]["cond_item_miss"] == 0


def test_gates_false_positive_free_on_known_good_dumps():
    """기존 양품 덤프에 새 게이트 false-critical 0 (파일 존재 시)."""
    good = [
        "data_corpus/round2/c12_wb2/out/job/typeset_dump.json",
        "data_corpus/round3/c13_ybm/out/job/typeset_dump.json",
        "data_corpus/round4/c03_tb_essay/out/job/typeset_dump.json",
        "data_corpus/round4/c06_rp_cr/out/job/typeset_dump.json",
        "data_corpus/tbwb_engine_e2e/20a3838b/job/typeset_dump.json",
        "data_corpus/wb_sero_e2e/e79f8af9/job/typeset_dump.json",
    ]
    for rel in good:
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        rep = inspect_workbook_finish(None, None, d)
        for key in ("발문스타일", "영단어오분류", "조건항목"):
            assert not [c for c in rep["critical"] if key in c], (rel, key)


def test_gates_catch_latent_defects_in_prior_outputs():
    """W16 게이트가 이전 라운드 실출력의 잠복 결함을 잡는다 (검출 실증 —
    c04 안내문 필드 영단어 27 + c05 ⦁조건 5. 수리 전 실덤프에서 추출한
    보존 픽스처 — 재조판 후에도 검출 근거 유지)."""
    cases = {
        "fixtures/w16_defect_dumps/c04_pre_fix.json": ("word_style_bad", 27),
        "fixtures/w16_defect_dumps/c05_pre_fix.json": ("cond_item_miss", 5),
    }
    for rel, (key, expected) in cases.items():
        path = os.path.join(TESTS_DIR, rel)
        d = json.load(open(path, encoding="utf-8"))
        rep = inspect_workbook_finish(None, None, d)
        assert rep["stats"][key] >= expected, (rel, key, rep["stats"][key])
