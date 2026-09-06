"""W92 — 지문 헤더 직전의 단원 제목 줄 (수능만만 10~12강 지적).

사용자 지적 2026-09-06: "10 형용사.부사.비교 구문 - 비교 구문" 이 지면에
그대로 인쇄됐다 — 어법 O/X 지면에서는 문항 번호(17.)와 O|X 버튼까지 받았다.

원고에서 이 줄은 지문 헤더("2. P67-본문") 바로 앞에 한 번씩 놓인다. 문서에
한 번만 나오므로 W61의 '헤더 앞 반복' 규칙에 안 걸리고, 헤더와 글자가 겹치지
않아 W50의 '내용-포함' 규칙에도 안 걸렸다. 제목의 꼴(강 번호 + 한글 +
제목 구분자, 비문장)로 판정해 헤더 블록에 흡수한다.
"""


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


# ── 형태 판정 ───────────────────────────────────────────────────────────────

def test_unit_title_shapes():
    from core.structure.header_detect import _is_unit_title
    for t in ("10 형용사.부사.비교 구문 - 비교 구문",
              "11 접속사와 전치사 - 상관접속사.접속사 vs. 전치사",
              "12 주의할 구문 - 어순.병렬 구조"):
        assert _is_unit_title(t), t


def test_unit_title_rejects_body_and_headers():
    from core.structure.header_detect import _is_unit_title
    for t in ("2. P67-본문",                       # 지문 헤더
              "1. 다음 글의 요지로 가장 적절한 것은?",   # 발문
              "그러나 최근 전문가들은 인터페이스를 개발하고 있다.",  # 본문 문장
              "10 형용사 부사 비교 구문",             # 구분자 없음
              "[Check Up 4] The test was so difficult"):
        assert not _is_unit_title(t), t


# ── 헤더 블록 흡수 ──────────────────────────────────────────────────────────

def test_title_before_header_is_absorbed():
    from core.structure.header_detect import detect_headers
    texts = ["1. P60-본문",
             "The first sentence of a long English passage goes here now.",
             "",
             "10 형용사.부사.비교 구문 - 비교 구문",
             "2. P67-본문",
             "Another long English passage sentence follows this header."]
    det = detect_headers(texts)
    assert det.is_header(4)
    assert det.is_absorbed(3)          # 제목 줄 — 제거 대상
    assert not det.is_header(3)        # 유닛 경계는 아니다


# ── 빌더 결선 (유닛 수 불변 + 제목 제거) ────────────────────────────────────

def test_builders_drop_unit_title_keeping_units():
    from engines.workbook_v2.plan import build_step2_b1
    data = {"paragraphs": _p(
        "1. P60-본문",
        "1. This is the main reason for the delay of the whole project.",
        "",
        "10 형용사.부사.비교 구문 - 비교 구문",
        "2. P67-본문",
        "2. The water was too cold as ice in the middle of the winter.")}
    flow = build_step2_b1(data)
    texts = [q.get("t", "") for u in flow["units"]
             for q in (u["paragraphs"] if isinstance(u, dict) else u)]
    assert len(flow["units"]) == 2
    assert not any("형용사" in t for t in texts)
