"""W90 — 생성 원고(LLM 변형문제) Step3 머리 부속물 (수능만만 09~10강 지적).

사용자 지적 2026-09-05 (job 145aeaaa 수능만만 부교재 v2 STEP3):
  ① 원고 머리의 편집 안내문('원문을 보존하고 … 적용했습니다.')이 지문으로 인쇄
  ② 문항마다 '문항 N' 줄이 완제품 자동 번호('01')와 겹쳐 두 번 인쇄
  ③ 출처·난이도 막대('09강 A | 난이도 상')가 그대로 인쇄
  ④ 문항 사이 괘선('──…' 62자)이 단 폭을 넘어 석 줄로 흘러 밑줄처럼 보임

넷 다 워크시트 편집용 부속물이다 — 완제품은 같은 자리를 자기 디자인으로
채운다. 문구가 아니라 형태(합쇼체 종결 / 문항 라벨 / 괘선 / 머리글 막대)로
가른다.
"""


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def _texts(paras):
    return [p["text"] for p in paras]


# ── ① 머리 안내문 ───────────────────────────────────────────────────────────

def test_head_guide_sentence_is_junk():
    from engines.workbook.parser import _strip_step3_rights_and_title
    out = _texts(_strip_step3_rights_and_title(
        _p("HIGH-DIFFICULTY GRAMMAR & READING",
           "09~10강 어법Practice 변형문제 40제",
           "총 40문항  ·  문제지  ·  원문 기반 변형",
           "원문을 보존하고, 각 문항의 요구에 필요한 최소 범위에서만 "
           "문법·빈칸 변형을 적용했습니다.",
           "다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?")))
    assert out == ["다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?"]


def test_polite_sentence_inside_body_is_kept():
    """합쇼체 허용은 머리 블록에서만 — 본문 중간 존댓말 줄은 보존."""
    from engines.workbook.parser import _strip_step3_rights_and_title
    rows = _p("1. 다음 글의 요지로 가장 적절한 것은?",
              "Thank you for your letter.",
              "귀하의 편지에 감사드립니다.",
              "2. 다음 글의 주제로 적절한 것은?")
    assert _texts(_strip_step3_rights_and_title(rows)) == _texts(rows)


# ── ②③ 문항 라벨 + 메타 막대 ───────────────────────────────────────────────

def test_item_label_and_meta_bar_removed():
    from engines.workbook.parser import _strip_step3_generated_item_meta
    out = _texts(_strip_step3_generated_item_meta(
        _p("문항 1",
           "09강 A  |  난이도 상",
           "다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?",
           "This is the office ________________ my girlfriend works.")))
    assert out == ["다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?",
                   "This is the office ________________ my girlfriend works."]


def test_meta_bar_only_next_to_item_label():
    """머리글 막대 판정만으로 문서 전체를 지우지 않는다 — 이웃 규칙."""
    from engines.workbook.parser import _strip_step3_generated_item_meta
    rows = _p("1. 다음 표의 내용과 일치하지 않는 것은?",
              "Monday  |  Tuesday  |  Wednesday")
    assert _texts(_strip_step3_generated_item_meta(rows)) == _texts(rows)


def test_item_label_needs_bare_number_line():
    """'문항 3' 형태의 단독 줄만 — 문장 속 '문항'은 보존."""
    from engines.workbook.parser import _strip_step3_generated_item_meta
    rows = _p("문항 3의 밑줄 친 부분과 쓰임이 같은 것은?",
              "문항 3 다음 글을 읽고 물음에 답하시오.")
    assert _texts(_strip_step3_generated_item_meta(rows)) == _texts(rows)


# ── ④ 괘선 구분줄 ───────────────────────────────────────────────────────────

def test_rule_line_removed_but_answer_blank_kept():
    from engines.workbook.parser import _strip_step3_generated_item_meta
    out = _texts(_strip_step3_generated_item_meta(
        _p("─" * 62,
           "=" * 20,
           "________________",
           "This is the office ________________ my girlfriend works.")))
    assert out == ["________________",
                   "This is the office ________________ my girlfriend works."]


# ── 파이프라인 결선 ─────────────────────────────────────────────────────────

def test_normalize_pipeline_strips_all_four():
    from engines.workbook.parser import _normalize_step3_manuscript
    out = _texts(_normalize_step3_manuscript(
        _p("09~10강 어법Practice 변형문제 40제",
           "원문을 보존하고, 각 문항의 요구에 필요한 최소 범위에서만 "
           "문법·빈칸 변형을 적용했습니다.",
           "문항 1",
           "09강 A  |  난이도 상",
           "다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?",
           "This is the office ________________ my girlfriend works.",
           "① in which",
           "─" * 62,
           "문항 2",
           "09강 문법 종합  |  난이도 상",
           "다음 ⓐ~ⓓ 중 어법상 틀린 문장의 개수는?")))
    assert out == ["다음 문장의 빈칸에 들어갈 말로 어법상 가장 적절한 것은?",
                   "This is the office ________________ my girlfriend works.",
                   "① in which",
                   "다음 ⓐ~ⓓ 중 어법상 틀린 문장의 개수는?"]
