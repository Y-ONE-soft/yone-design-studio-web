"""W18 품질 루프 8라운드 가드 — 신규 선정 2종:
c17 고1 23년 11월 모의고사 워크북 폴더 → workbook_sero_v2 (세로 첫 품질 루프)
c18 리딩파워(Reading power) 유형편 완성 기출문제(Step 3에 사용함).hwp
    → ebs_workbook_v2

결함 재현→수리 고정:
  D1 (c18) 선두 표제 블록의 날짜-only 메모("17. 11. 23")가 문항 번호 보호
     규칙에 오인 보호돼 본문 첫 단락으로 인쇄 → 파서
     _strip_step3_leading_junk 날짜 예외 + 게이트 G20 [선두잔재]
  D2 (c18/sero 잠복) 시작 신호 없는 해요체 발문("영어로 번역하세요
     [9강 1번]" / "11. (주관식) … 고르세요. [정답 2개]")이 지문 스타일로
     인쇄 → 플랜 오버레이 꼬리 [출처/태그]+세요-체 종결 → Q + 게이트 G13
     확장 (꼬리 태그 + 시오/세요 종결)
  D3 (c17) 정답/스텝1·2 파일의 Step3 오라우팅 — "고1 23년 11월 NN번_정답
     .hwp" 20종 + "…워크북step3_정답지.hwpx" + "Step1 A1 어휘선택(2단계
     34번).docx"가 Step3로 흘러 중복/정답 사이클 생성 → sero_v2 라우팅 가드
  D4 (c17) 정규 모의고사 워크북 마커 미인식 — 고N #NN / NN. / N. pN-no.NN /
     NN번 셰이프에서 q_num 분할 0 → 전 스텝 침묵 유실(빈 사이클 조판) →
     sero_v2 자체 분할 오케스트레이션 (v1 helpers 재사용)
  D5 (c17) sero verify 완제품 게이트 부재 — 위 침묵 유실이 verify ok=True로
     통과 → 게이트 통합 (pseudo-plan/steps 어댑터 + G9 uploads)
"""
import json
import os

from engines.workbook_v2.gate import inspect_workbook_finish

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"


def _fixture(name):
    path = os.path.join(TESTS_DIR, "fixtures", "w18_defect_dumps", name)
    return json.load(open(path, encoding="utf-8"))


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


# ── D1 게이트: G20 선두 날짜-only 잔재 ──────────────────────────────────────

def test_gate_g20_detects_leading_date():
    d = _dump([
        {"t": "17. 11. 23", "s": _ST_P},
        {"t": "다음 글의 내용과 일치하는 것은? [1강-E2]", "s": _ST_Q},
        {"t": "Anne Mangen at the University of Oslo studied.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert any("선두잔재" in c for c in rep["critical"])


def test_gate_g20_ignores_mid_story_date():
    """본문 중간의 날짜-only 단락은 검사하지 않는다 (스토리 선두 한정)."""
    d = _dump([
        {"t": "다음 글의 내용과 일치하는 것은?", "s": _ST_Q},
        {"t": "2017. 11. 23", "s": _ST_P},
        {"t": "Some passage text here.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("선두잔재" in c for c in rep["critical"])


def test_gate_g20_ignores_question_number_lead():
    """선두 문항 번호("1. 다음 …")는 날짜가 아니다."""
    d = _dump([
        {"t": "1. 다음 글을 읽고 물음에 답하시오.", "s": _ST_Q},
        {"t": "Passage body.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("선두잔재" in c for c in rep["critical"])


# ── D2 게이트: G13 확장 (꼬리 태그 + 시오/세요 종결) ────────────────────────

def test_gate_g13_ext_detects_tail_tag_seyo():
    d = _dump([
        {"t": "영어로 번역하세요 [9강 1번]", "s": _ST_P},
        {"t": "Passage body sentence.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_catches_sero_latent_dump():
    """세로 e79f8af9 기출력(W5, 게이트 이전)의 잠복 결함 — "11. (주관식)
    어법상 틀린 곳을 고르세요. [정답 2개]"가 지문 스타일 (수리 전 실덤프
    발췌 픽스처 — 재조판 후에도 검출 근거 유지)."""
    rep = inspect_workbook_finish(None, None,
                                  _fixture("e79f8af9_qstyle_pre_fix.json"))
    assert any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_clean_when_q_styled():
    d = _dump([
        {"t": "영어로 번역하세요 [9강 1번]", "s": _ST_Q},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_ignores_plain_tail_tag():
    """시오/세요 종결이 아닌 꼬리 태그 라인(출처 마커 인쇄 관행)은 무관."""
    d = _dump([
        {"t": "이것은 해설 문장이다 [3점]", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("발문스타일" in c for c in rep["critical"])


# ── D1 파서: _strip_step3_leading_junk 날짜 예외 ────────────────────────────

def _paras(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def test_strip_leading_junk_drops_date_in_title_block():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "영어는 언어다",
        "Readign Power 유형편 완성 기출문제",
        "17. 11. 23",
        "다음 글의 내용과 일치하는 것은? [1강-E2]",
        "Anne Mangen at the University of Oslo studied the performance.",
    ))
    texts = [p["text"] for p in out]
    assert texts[0].startswith("다음 글의 내용과")
    assert "17. 11. 23" not in texts


def test_strip_leading_junk_keeps_mid_document_date():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "다음 글의 내용과 일치하는 것은?",
        "17. 11. 23",
        "Passage body.",
    ))
    assert [p["text"] for p in out] == [
        "다음 글의 내용과 일치하는 것은?", "17. 11. 23", "Passage body."]


def test_strip_leading_junk_keeps_question_number():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "1. 다음 글을 읽고 물음에 답하시오.", "Passage body."))
    assert len(out) == 2


# ── D2 플랜: 해요체 + 꼬리 태그 발문 오버레이 ───────────────────────────────

def test_s3_effective_kind_tail_tag_seyo():
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("UNKNOWN", "영어로 번역하세요 [9강 1번]") == "Q"
    assert _s3_effective_kind(
        "UNKNOWN",
        "11. (주관식) 어법상 틀린 곳을 고르세요. [정답 2개]") == "Q"


def test_s3_effective_kind_seyo_without_tag_unchanged():
    """시작 신호도 꼬리 태그도 없는 해요체는 기존 규칙 유지 (해석 문장
    오탐 방지 — W16 AND 결합 설계 보존)."""
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("UNKNOWN", "영어로 번역하세요") == "UNKNOWN"


def test_s3_effective_kind_strong_kind_not_overridden():
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("P", "영어로 번역하세요 [9강 1번]") == "P"


def test_s3_effective_kind_tag_but_not_seyo_end_unchanged():
    """꼬리 태그가 있어도 몸통이 세요-체 종결이 아니면 무변경 (지문 속
    출처 표기 문장 보호)."""
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind(
        "UNKNOWN", "그는 학교에 갔다 [3점]") == "UNKNOWN"
