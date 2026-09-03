"""W86 — 본문 O/X 섹션 지시문(발문) 누락.

사용자 지적(2026-08-31): "워크북 STEP1 A2 / '다음 글의 내용과 일치하면 O,
일치하지 않으면 X를 고르시오.' 이거 발문으로 들어가는 로직이 누락돼있는 것
같은데."

확인 결과 맞다 — 내지 템플릿 인벤토리(tests/fixtures/template_spec_workbookC)
에서 어법 O/X 섹션 페이지(p132)에는 지시문 프레임이 있고 본문 O/X 섹션
페이지(p22)에는 아예 없다. 엔진에도 그 자리를 채우는 로직이 없었다.

수리: 같은 책의 지시문 프레임(어법 O/X)을 복제해 같은 자리에 놓는다 —
위치·크기·단락스타일은 디자인이라 조판이 새로 정하지 않는다. 본보기가
없으면(그 스텝이 안 실린 원고) 계약을 만들지 않는다.
"""


def test_contract_needs_both_target_and_model_step():
    from engines.workbook_v2.plan import section_prompts_op
    both = {"flows": [{"step": "step1_a2"}, {"step": "step2_b1"},
                      {"step": "step3"}]}
    ops = section_prompts_op(both)
    assert len(ops) == 1
    assert ops[0]["step"] == "step1_a2"
    assert ops[0]["from_step"] == "step2_b1"
    assert ops[0]["text"] == \
        "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오."
    # 본보기 스텝이 없으면 계약 없음 (조판이 디자인을 새로 정하지 않는다)
    assert section_prompts_op({"flows": [{"step": "step1_a2"}]}) == []
    assert section_prompts_op({"flows": [{"step": "step2_b1"}]}) == []


def test_band_prompt_is_exempt_from_q_style_gate():
    """머리 띠 지시문은 발문 계열 스타일이 아닌 게 맞다 — G13 면제."""
    from engines.workbook_v2.gate import inspect_workbook_finish
    text = "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오."
    dump = {"stories": [{"paragraphs": [
        {"t": text, "s": "STEP 01 > 머리 띠 지시문"}]}], "pages": []}
    content = {"steps": {}}

    def _run(plan):
        out = inspect_workbook_finish(content, plan, dump)
        return list(out.get("critical") or []) + list(out.get("warnings") or [])

    exempt = _run({"flows": [], "section_prompts": [
        {"step": "step1_a2", "from_step": "step2_b1", "text": text}]})
    assert not any("발문스타일" in m for m in exempt)
    # 플랜에 없는 같은 모양의 발문은 그대로 검출된다
    caught = _run({"flows": [], "section_prompts": []})
    assert any("발문스타일" in m for m in caught)
