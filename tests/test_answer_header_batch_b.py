"""배치 B (W33) — 정답부 시작 인식 rules 합류 (docs/인식지점_전수감사.md §9).

감사 리스크 3위: _strip_step3_answers의 리터럴 튜플 4종이 taxonomy
A_PATTERNS가 아는 표기('정답과 해설')를 몰라 정답표가 문제지에 인쇄되던
'서로 다른 눈' 문제 (실증 #3) — rules.A_SECTION_HEADER 공유로 원천 제거.
"""
import pytest


def _paras(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


# ── 구 리터럴이 공유 패턴의 부분집합임을 가드 (골든 diff 0 계약) ────────────

def test_legacy_tuple_subset_of_shared_pattern():
    from core.structure.rules import A_SECTION_HEADER
    # 가로 파서 구 튜플 4종
    for t in ("정답 및 해설", "빠른 정답 찾기", "정답지", "정답"):
        assert A_SECTION_HEADER.match(t), t
    # 세로 파서 구 목록 (콜론/영문 제외 — 세로 고유 표기로 별도 유지)
    for t in ("[정답]", "【정답】", "<정답>", "정답 및 해설"):
        assert A_SECTION_HEADER.match(t), t


def test_shared_pattern_new_notations():
    """감사 실증 #3 — 구 튜플이 못 자르던 4변형 전부 인식."""
    from core.structure.rules import A_SECTION_HEADER
    for t in ("정답과 해설", "정답 · 해설", "[정답 및 해설]", "정답 및 해설",
              "정답/해설", "빠른 정답", "해설"):
        assert A_SECTION_HEADER.match(t), t


def test_shared_pattern_rejections():
    """발문/본문/문항별 정답 표기는 섹션 헤더가 아니다 (과절단 가드)."""
    from core.structure.rules import A_SECTION_HEADER
    for t in ("다음 글의 제목으로 가장 적절한 것은?",
              "■ 정답: ③ 해설 참조",          # 콜론 뒤 내용 — 문항별 정답
              "정답과 해설을 참고하여 고치시오.",
              "위 문제의 해설은 뒷장에 있다.",
              "1. 정답 및 해설 참조"):
        assert not A_SECTION_HEADER.match(t), t


# ── 파서 절단 (실증 #3 재현 — 전: '정답 및 해설'만 절단) ────────────────────

@pytest.mark.parametrize("header", ["정답 및 해설", "정답과 해설",
                                    "정답 · 해설", "[정답 및 해설]"])
def test_strip_step3_answers_cuts_all_variants(header):
    from engines.workbook.parser import _strip_step3_answers
    paras = _paras(
        "1. 다음 글의 제목으로 가장 적절한 것은?",
        "The passage is about silence in engineering.",
        header,
        "1) ③  2) ⑤  3) ①",
        "4) ②  5) ④",
    )
    out = _strip_step3_answers(paras)
    texts = [p["text"] for p in out]
    assert header not in texts, "섹션 헤더 잔존"
    assert not any("1) ③" in t for t in texts), f"{header}: 정답표 잔존"
    assert texts[0].startswith("1. 다음 글의")        # 문제부 보존


def test_strip_step3_answers_keeps_body():
    """헤더 없는 원고는 문제부 무손실 (개별 정답 줄 제거 규칙만 동작)."""
    from engines.workbook.parser import _strip_step3_answers
    paras = _paras(
        "1. 다음 글의 제목으로 가장 적절한 것은?",
        "Long English passage that must survive the cut entirely.",
        "① first  ② second",
    )
    out = _strip_step3_answers(paras)
    assert len(out) == 3


def test_sero_answer_headers_share_rules():
    from engines.workbook_sero.parser import _strip_step3_answers_aggressive
    paras = _paras(
        "1. 다음 중 옳은 것은?",
        "Body sentence.",
        "정답과 해설",            # 구 세로 목록이 모르던 표기
        "1번 - ③",
    )
    out = _strip_step3_answers_aggressive(paras)
    texts = [p["text"] for p in out]
    assert "정답과 해설" not in texts
    assert not any("1번 - ③" in t for t in texts)
    assert texts[0].startswith("1.")


# ── 분류기와 같은 눈 (kind A) ───────────────────────────────────────────────

def test_classifier_same_eye():
    from core.structure import classify_paragraphs
    res = classify_paragraphs(_paras("정답과 해설"))
    assert res[0]["kind"] == "A", "판정기·파서가 같은 눈이어야 함 (배치 B)"
