"""W34 배치 D — v1 공유 파서 헤더 계층의 구조 인식기 합류 테스트.

계약 (docs/인식지점_전수감사.md §9 D안):
  ① 정규식이 인식하던 것은 전부 기존 경로 그대로 (하위호환 하한)
  ② 구조 인식기 추가 인식분은 additive (정규식 미인식 → 승격)
  ③ 안전 밸브 YONE_PARSER_STRUCT_HEADERS=0 → 합류 전체 무효 (기존 동작)
  ④ 파서 계층은 fail-open (예외/침묵 승격 없음 — 침묵 금지는 v2 G6 담당)

감사 실증 #2 (마더텅형·신형 헤더: 파서 정규식 0/3 vs 구조 3/3)의
파서 계층 재실행을 포함한다.
"""
import pytest

from engines.workbook import parser as P
from engines.workbook_sero import parser as SP


def _mk(texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


_BODY = [
    "The rise of social media has fundamentally changed how people "
    "communicate with each other across the world.",
    "Scientists have long debated whether animals possess genuine "
    "emotions or merely instinctive responses.",
    "Urban gardening has emerged as a popular movement in cities "
    "around the globe over the past decade.",
]

# 감사 실증 #2-A: 마더텅형 (v1 파서 정규식 0/3)
MOTHERTONGUE = _mk([
    "마더텅 옛기출 워크북",
    "Q. 다음 글을 읽고 물음에 답하시오.",
    "1강 18번 170918", _BODY[0],
    "1강 19번 170919", _BODY[1],
    "1강 20번 170920", _BODY[2],
])

# 감사 실증 #2-B: 가상 신형 (어느 정규식에도 없는 형식)
NEWFORM = _mk([
    "새책 어휘선택(문제지)",
    "Q. 문맥 상 알맞은 것을 고르시오.",
    "지문 1 (p. 24)", _BODY[0],
    "지문 2 (p. 26)", _BODY[1],
    "지문 3 (p. 28)", _BODY[2],
])

# 정규식 인식 + 미인식 신형(2회 반복) 혼재 — additive 확인
MIXED = _mk([
    "고1_2025_10월",
    "1. p2-no.18", _BODY[0],
    "고1 25년 10월 20번", _BODY[1],
    "고1 25년 10월 21번", _BODY[2],
    "3. p4-no.22", _BODY[0],
])


@pytest.fixture
def valve_off(monkeypatch):
    monkeypatch.setattr(P, "USE_STRUCT_HEADER_DETECT", False)


# ── 실증 #2 재실행 (파서 계층) ──────────────────────────────────────────────

def test_mothertongue_headers_promoted():
    """마더텅형 3/3 승격 — strip 시작점 + 지문번호 (N번 표기의 마지막 발생)."""
    extras = P._struct_header_extras(MOTHERTONGUE)
    assert len(extras) == 3
    stripped = P._strip_manuscript_headers(MOTHERTONGUE)
    assert stripped[0]["text"] == "1강 18번 170918"
    assert P._extract_question_numbers(MOTHERTONGUE, "t") == [18, 19, 20]


def test_newform_headers_promoted():
    """신형 '지문 N (p. M)' 3/3 승격 — 괄호부 제거 후 유일 숫자 규칙."""
    extras = P._struct_header_extras(NEWFORM)
    assert len(extras) == 3
    stripped = P._strip_manuscript_headers(NEWFORM)
    assert stripped[0]["text"] == "지문 1 (p. 24)"
    assert P._extract_question_numbers(NEWFORM, "t") == [1, 2, 3]


def test_mixed_additive_interleaved():
    """혼재 원고 — 정규식 인식분은 그대로, 승격분은 문서 순으로 삽입."""
    assert P._extract_question_numbers(MIXED, "t") == [18, 20, 21, 22]
    # 정규식 인식 라인은 승격 집합에 절대 없다 (additive 경계)
    extras = P._struct_header_extras(MIXED)
    for i in extras:
        assert not P._legacy_header_marker(MIXED[i]["text"])


# ── 안전 밸브 (③) ──────────────────────────────────────────────────────────

def test_valve_off_restores_legacy(valve_off):
    assert P._struct_header_extras(MOTHERTONGUE) == set()
    assert P._extract_question_numbers(MOTHERTONGUE, "t") == []
    assert P._extract_question_numbers(MIXED, "t") == [18, 22]
    # strip은 기존 2차 구조 판정(_is_passage_marker_struct)이 그대로 동작
    assert (P._strip_manuscript_headers(MOTHERTONGUE)[0]["text"]
            == "1강 18번 170918")


# ── 하위호환 하한 (①) — 기존 지원 형식 전부 동일 처리 ──────────────────────

_LEGACY_DOCS = [
    ("L형", ["책", "1. L1-본문1", _BODY[0], "2. L1-본문2", _BODY[1]]),
    ("L페이지형", ["책 제목", "1. L4-p.82", _BODY[0]]),
    ("모의고사형", ["고1_2025_10월", "1. p2-no.20", _BODY[0]]),
    ("대괄호한글", ["어휘선택(문제지)", "[본문1]", _BODY[0]]),
    ("대괄호숫자", ["헤더", "[20]", _BODY[0]]),
]


@pytest.mark.parametrize("name,texts", _LEGACY_DOCS,
                         ids=[n for n, _ in _LEGACY_DOCS])
def test_legacy_docs_identical_on_off(name, texts, monkeypatch):
    """정규식이 전부 인식하는 원고는 합류 on/off 출력이 동일해야 한다."""
    paras = _mk(texts)
    on_strip = [p["text"] for p in P._strip_manuscript_headers(paras)]
    on_nums = P._extract_question_numbers(paras, "t")
    monkeypatch.setattr(P, "USE_STRUCT_HEADER_DETECT", False)
    off_strip = [p["text"] for p in P._strip_manuscript_headers(paras)]
    off_nums = P._extract_question_numbers(paras, "t")
    assert on_strip == off_strip
    assert on_nums == off_nums


# ── 번호 추출 휴리스틱 (확신 표기만 — 모호하면 None) ────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("1강 18번 170918", 18),      # N번 마지막 발생
    ("17년 11월 21번", 21),
    ("41~42번", 41),              # 범위 → 첫 번호 (기존 규약)
    ("no.7 지문", 7),             # no.N 우선
    ("1. PROJECT 2-본문3", 3),    # 본문N
    ("지문 1 (p. 24)", 1),        # 괄호부 제거 후 유일 숫자
    ("250920", None),             # 6자리 코드 단독 — 추측 금지
    ("1. 24-10-고1-31", None),    # 다수 숫자 모호 — 추측 금지
])
def test_struct_header_qnum(text, expected):
    assert P._struct_header_qnum(text) == expected


# ── 파서 계층 fail-open (④) ────────────────────────────────────────────────

def test_fail_open_on_detector_error(monkeypatch):
    """인식기 예외 시 빈 집합 폴백 — v1 파서는 절대 죽지 않는다."""
    import core.structure.header_detect as hd
    monkeypatch.setattr(hd, "detect_headers",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert P._struct_header_extras(MOTHERTONGUE) == set()
    assert P._extract_question_numbers(MOTHERTONGUE, "t") == []


# ── sero v1 합류 — 집합 교차 검증 (W18 D4 준용) ─────────────────────────────

_SERO_PARAS = _mk([
    "고1 25년 10월 20번", _BODY[0],
    "고1 25년 10월 21번", _BODY[1],
    "고1 25년 10월 33번", _BODY[2],   # step3 집합에 없는 번호 — 승격 금지
])


def test_sero_struct_split_with_known_set():
    secs = SP._split_paragraphs_by_qnum(_SERO_PARAS,
                                        known_qnums={"20", "21"})
    assert [s["q_num"] for s in secs] == ["20", "21"]
    # 미검증 번호(33)는 마커로 인정되지 않고 직전 섹션 본문에 유지
    assert any("33번" in (p["text"] if isinstance(p, dict) else p)
               for p in secs[-1]["paragraphs"])


def test_sero_no_known_set_is_legacy():
    """known_qnums 미제공(기존 호출 시그니처) → 기존 동작 100% 동일."""
    assert SP._split_paragraphs_by_qnum(_SERO_PARAS) == []


def test_sero_legacy_markers_unaffected():
    paras = _mk([
        "[15강 14번 171140]", _BODY[0],
        "[15강 15번 171141]", _BODY[1],
    ])
    legacy = SP._split_paragraphs_by_qnum(paras)
    joined = SP._split_paragraphs_by_qnum(paras, known_qnums={"14", "15"})
    assert legacy == joined
    assert [s["q_num"] for s in legacy] == ["14", "15"]


def test_sero_valve_off(monkeypatch):
    monkeypatch.setattr(P, "USE_STRUCT_HEADER_DETECT", False)
    assert SP._split_paragraphs_by_qnum(_SERO_PARAS,
                                        known_qnums={"20", "21"}) == []
