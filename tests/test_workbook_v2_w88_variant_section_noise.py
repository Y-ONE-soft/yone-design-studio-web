"""W88 — 여러 변형 섹션을 이어붙인 Step3 원고의 편집용 태그 잔존.

사용자 지적(2026-09-04, 고2 26년 6월 부산 모의고사): "19번 / 심경 /
Section ❶ / 고2 2026년 6월 부산광역시 교육청 — 이런 게 왜 아직도 들어가는
거야."

원고가 한 문항을 여러 변형(Section)으로 이어붙인 형태일 때, 섹션 경계마다
편집용 태그 묶음이 반복된다:
  · "19번"      — 문항 자기 번호(원본 파일명과 같은 수)
  · "심경"       — 유형 표기(원고마다 다른 말: 도표/안내문/…)
  · "Section ❶" — 변형 구획 표시
그리고 정답 시작 직전엔 시험 출처 헤더("고2 2026년 6월 부산광역시 교육청")
가 반복된다.

핵심 함정: 유형 표기("심경")는 **새 문항 앞**(W83이 잡던 자리)이 아니라
**이미 나온 발문의 자기 번호 태그와 Section 마커 사이**에 낀다. 처음엔
"앞줄이 발문(?/…시오로 끝남)이면 그 뒤 짧은 한글 줄은 유형 표기"로 넓혔다가
코퍼스 79개 잡이 흔들렸다 — "번호 수정안"/"틀린 부분" 같은 **진짜 답란 표
머리글**도 발문 바로 뒤에 온다. 최종 판정은 낱말이 아니라 **두 확실한
이웃**(자기 번호 태그, Section 마커) 사이라는 자리만 본다.
"""


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def _texts(paras):
    from engines.workbook.parser import _s3_text
    return [_s3_text(p) for p in paras if _s3_text(p)]


def test_section_marker_stripped_anywhere():
    from engines.workbook.parser import _strip_step3_section_markers
    rows = _p("① a", "Section ❶", "② b", "Section ❷")
    assert _texts(_strip_step3_section_markers(rows)) == ["① a", "② b"]


def test_own_item_number_tag_requires_exact_match():
    from engines.workbook.parser import _strip_step3_own_item_number_tag
    rows = _p("어법상 어색한 것을 모두 고르면?", "19번", "① a")
    out = _texts(_strip_step3_own_item_number_tag(rows, item_num="19"))
    assert out == ["어법상 어색한 것을 모두 고르면?", "① a"]
    # 다른 번호는 절대 건드리지 않는다 — 본문 속 진짜 숫자일 수 있다
    same = _texts(_strip_step3_own_item_number_tag(rows, item_num="20"))
    assert same == _texts(rows)
    # item_num 없으면 완전 무접촉
    assert _texts(_strip_step3_own_item_number_tag(rows)) == _texts(rows)


def test_exam_source_line_needs_year_and_origin_keyword():
    from engines.workbook.parser import _strip_step3_exam_source_line
    rows = _p("고2 2026년 6월 부산광역시 교육청",
              "고2｜2026년 6월 부산광역시 교육청",
              "정답 및 해설")
    out = _texts(_strip_step3_exam_source_line(rows))
    assert out == ["정답 및 해설"]
    # 연도 없는 짧은 줄, 또는 종결부호가 있는 진짜 문장은 그대로
    untouched = _p("교육청 발표에 따르면 학생 수가 증가했다.")
    assert _texts(_strip_step3_exam_source_line(untouched)) == \
        _texts(untouched)


def test_variant_type_tag_only_between_number_tag_and_section_marker():
    """핵심 회귀 방지: 낱말이 아니라 자리로 판정 — 답란 표 머리글은
    안 건드린다("번호 수정안"/"틀린 부분" 같은 진짜 표 헤더가 발문 바로
    뒤에 오는 경우가 코퍼스에 실제로 있다)."""
    from engines.workbook.parser import _strip_step3_variant_type_tag
    # 진짜 사례: 발문 → 19번 → 심경 → Section ❶ → 선지
    cluster = _p("윗글의 밑줄 친 것 중 어색한 것을 모두 고르면?",
                 "19번", "심경", "Section ❶", "① a")
    out = _texts(_strip_step3_variant_type_tag(cluster, item_num="19"))
    assert out == ["윗글의 밑줄 친 것 중 어색한 것을 모두 고르면?",
                   "19번", "Section ❶", "① a"]        # "심경"만 빠짐
    # 오탐 방지: Section 마커가 없으면(=답란 표 헤더 등 일반적인 경우)
    # 무엇이 오든 절대 지우지 않는다
    table_header = _p("전체를 다시 쓰시오.", "19번", "번호           수정안",
                      "① a")
    assert _texts(_strip_step3_variant_type_tag(
        table_header, item_num="19")) == _texts(table_header)


def test_full_manuscript_cluster_removed_content_preserved():
    """네 가지 잔재가 한 원고 안에 다 있어도 실제 문항 내용은 그대로."""
    from engines.workbook.parser import _normalize_step3_manuscript
    rows = _p(
        "다음 글을 읽고 물음에 답하시오.",
        "A passage sentence that is long enough to be real content here.",
        "윗글의 밑줄 친 것 중 어색한 것을 모두 고르면?",
        "19번", "심경", "Section ❶",
        "① a  ② b  ③ c  ④ d  ⑤ e",
        "고2｜2026년 6월 부산광역시 교육청",
        "정답 및 해설",
    )
    out = _texts(_normalize_step3_manuscript(rows, item_num="19"))
    assert "19번" not in out
    assert "심경" not in out
    assert "Section ❶" not in out
    assert not any("부산광역시" in t for t in out)
    assert "A passage sentence that is long enough to be real content here." \
        in out
    assert "윗글의 밑줄 친 것 중 어색한 것을 모두 고르면?" in out
