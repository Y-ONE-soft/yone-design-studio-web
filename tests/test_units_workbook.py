# -*- coding: utf-8 -*-
"""워크북 원고(역할 원고) → 캔버스 — 원고 형식 등록부(core/units/formats) · 원고 자리 글상자 · 요소의 자리 이름 채우기 · 정답지."""
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(REPO, "tests", "fixtures", "units")


def _t(svg):
    """그린 글에서 한국어 공백 표시(<span lang="ko"> </span> — 한국어 꼴 공백 폭)를 걷어 글만 — 낱말 찾기용"""
    import re as _re
    return _re.sub(r'<span lang="ko">([^<]*)</span>', r"\1", svg)


@pytest.fixture
def lib(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(SEED, tmp_path / "catalog" / "_units")
    from core.units import store
    monkeypatch.setattr(store, "CATALOG", str(tmp_path / "catalog"))
    return store.library()


def _sets():
    """워크북 v2 엔진이 읽은 스텝 모양 → 세트 (지문 20)."""
    from core.units.formats import workbook as workbook_src
    steps = [
        {"step": 1, "logo": "A2", "title": "본문 O/X", "key": "step1_a2", "groups": [{"label": "20", "units": [[
            {"role": "box_body", "text": "Learning games need to be fun enough."},
            {"role": "b2_q", "text": "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오."},
            {"role": "ox_item", "text": "(1) Games must be entertaining."},
            {"role": "ox_item", "text": "(2) Developers try to entertain."},
            {"role": "ox_item", "text": "(3) Fun makes learning harder."}]]}]},
        {"step": 2, "logo": "B1", "title": "어법 O/X", "key": "step2_b1", "groups": [{"label": "20", "units": [[
            {"role": "gram_ox", "text": "1.  Learning games need being fun."}]]}]},
        {"step": 1, "logo": "C2", "title": "빈칸 어휘", "key": "step1_c2", "groups": [{"label": "20", "units": [[
            {"role": "blank_vocab", "text": "Learning games need to be 1[fun] enough."},
            {"role": "blank_kr", "text": "학습 게임은 충분히 재미있어야 한다."}]]}]},
        {"step": 1, "logo": "B1", "title": "본문 정리", "key": "step1_b1", "groups": [{"label": "20", "units": [[
            {"role": "q_prompt", "text": "다음 글의 주제로 가장 적절한 것은? ③"}]]}]},
        {"step": 3, "logo": "S", "title": "실전 문제", "key": "step3", "groups": [{"label": "20", "units": [[
            {"role": "s3_q", "text": "빠진다"}]]}]},
    ]
    return workbook_src.steps_to_sets(steps)


def _text(bind, y, h=20):
    return {"atom": {"t": "text", "x": 0, "y": 0, "w": 170, "h": h, "size": 9, "font": "$body", "color": "$ink", "bind": bind, "auto_size": "height"}, "x": 20, "y": y}


def _ctx(lib, lib2=None):
    from core.units import render, store
    return render.Ctx(store.by_id(lib["skins"])["d2"], lib2 or lib, {})


def test_workbook_sets_from_steps():
    """스텝 × 지문마다 세트 하나 · id 에 스텝(Step1 B1 과 Step2 B1 이 안 겹치게) · 번호·정답은 떼어 따로 · 스텝 3 은 아직 뺀다."""
    sets = _sets()
    assert [s["id"] for s in sets] == ["20·1A2", "20·2B1", "20·1C2", "20·1B1"]
    a2 = sets[0]
    assert a2["kind"] == "A2 본문 O/X" and a2["group"] == "20" and a2["labels"]["ox_item"] == "O/X 문항"
    assert [b["fields"] for b in a2["blocks"] if b["block"] == "ox_item"][0] == {"no": "(1)", "ox_item": "Games must be entertaining."}
    c2 = [b["fields"] for b in sets[2]["blocks"] if b["block"] == "blank_vocab"][0]
    assert "fun" not in c2["blank_vocab"] and c2["answer"] == "(1) fun"          # 학생 면에 정답이 안 찍힌다
    q = [b["fields"] for b in sets[3]["blocks"] if b["block"] == "q_prompt"][0]
    assert q == {"answer": "③", "q_prompt": "다음 글의 주제로 가장 적절한 것은?"}
    head = [b for b in a2["blocks"] if b["block"] == "head"][0]              # 머리 띠가 유형마다 받는 정보 — 없어도 검수에 안 뜬다
    assert head["optional"] and head["fields"]["code"] == "A2" and head["fields"]["type_title"] == "본문 O/X"
    assert head["fields"]["step_tag"].startswith("STEP 01") and sets[1]["blocks"][1]["fields"]["step_tag"].startswith("STEP 02")
    from core.units import store
    assert all(store.validate("sets", s) is None for s in sets)


def test_catalog_without_manuscript():
    """원고를 넣기 전에도 틀을 그릴 수 있다 — 원고 형식마다 유형(받는 원고)·자리(원고 자리) 목록을 밝힌다. 세트 kind 와 같은 이름."""
    from core.units import formats
    cat = {c["id"]: c for c in formats.catalog()}
    c = cat["workbook"]
    assert len(c["kinds"]) == 11 and c["kinds"][0] == "A1 어휘 선택 1" and "C2 영작 배열" in c["kinds"]
    assert {s["kind"] for s in _sets()} <= set(c["kinds"])
    assert c["fields"]["ox_item"] == "O/X 문항" and "no" not in c["fields"]
    assert cat["mockexam"]["kinds"] == ["동형 모의고사"] and cat["mockexam"]["fields"]["m_choice"] == "선지"


def test_format_detect():
    """파일 이름으로 원고 형식을 알아본다 — 캔버스·렌더러는 책 종류를 모른다."""
    from core.units import formats
    assert formats.detect(["Step1 A1 어휘선택.docx", "Step2 B1 어법OX.docx"]) == "workbook"
    assert formats.detect(["한영고1 동형 모의고사 1회.hwpx"]) == "mockexam"
    assert formats.detect(["원고.docx"]) is None


def test_mockexam_paragraphs_to_set():
    """모의고사 — 단락 역할을 자리 이름으로, 발문엔 차례 번호, 한 회 = 원고 하나(머리 정보는 optional)."""
    from core.units.formats import mockexam
    paras = [{"pstyle": "다음 글을 읽고", "text": "[1~2] 다음 글을 읽고 답하시오."}, {"pstyle": "지문", "text": "Passage one."},
             {"pstyle": "문제 번호", "text": "윗글의 주제는?"}, {"pstyle": "선지", "text": "① a"}, {"pstyle": "문제 번호", "text": ""},
             {"pstyle": "지문", "text": ""}, {"pstyle": "서술형 번호", "text": "[서답형1] 쓰시오."}]
    s = mockexam.paragraphs_to_set(paras, "한영고", "1", 1)
    assert s["id"] == "한영고1 1회" and s["blocks"][0]["optional"]
    assert [b["block"] for b in s["blocks"][1:]] == ["m_group", "m_passage", "m_q", "m_choice", "m_q", "m_desc"]
    assert s["blocks"][3]["fields"]["m_q"] == "1. 윗글의 주제는?" and s["blocks"][5]["fields"]["m_q"] == "2."


def test_slot_fmt_in_story(lib):
    """자리마다 서식 — 한 스토리에 흘릴 때 원고 형식의 기본(발문 굵게)에 글상자의 slot_fmt 가 덧씌운다."""
    from core.units import render
    st = dict(_sets()[0], fmt={"b2_q": {"b": True}})
    pg = {"id": "t", "items": [_text("b2_q+ox_item", 40)]}
    render._fill_items(pg, st, _ctx(lib))
    v = pg["items"][0]["fields"]["b2_q+ox_item"]
    heads = [x for x in v if isinstance(x, dict) and x.get("b")]
    assert heads and heads[0]["t"].startswith("다음 글의") and not any(isinstance(x, dict) and x.get("b") and "Games" in x.get("t", "") for x in v)
    pg = {"id": "t", "items": [_text("b2_q+ox_item", 40)]}
    pg["items"][0]["atom"]["slot_fmt"] = {"ox_item": {"i": True}, "b2_q": {"b": False}}
    render._fill_items(pg, st, _ctx(lib))
    v = pg["items"][0]["fields"]["b2_q+ox_item"]
    assert not any(isinstance(x, dict) and x.get("b") for x in v) and any(isinstance(x, dict) and x.get("i") for x in v)


def test_atom_slots_fill_like_data_merge(lib):
    """원고 자리 글상자 — 여럿이면 n번째 값, 하나면 전부 흘러 들어감(번호 칸이 없으면 번호를 글 앞에), a+b 는 원고 순서대로 섞음."""
    from core.units import render
    st = _sets()[0]
    ctx = _ctx(lib)
    pg = {"id": "t", "items": [_text("pnum", 10, 8), _text("ox_item", 40), _text("ox_item", 60)]}
    render._fill_items(pg, st, ctx)
    assert [it["fields"] for it in pg["items"]] == [{"pnum": "20"}, {"ox_item": "Games must be entertaining."}, {"ox_item": "Developers try to entertain."}]
    assert any("1개는" in i["msg"] and "안 실린다" in i["msg"] for i in ctx.issues)       # 셋째 줄은 자리가 없다
    ctx = _ctx(lib)
    pg = {"id": "t", "items": [_text("ox_item", 40)]}
    render._fill_items(pg, st, ctx)
    assert render.rich_plain(pg["items"][0]["fields"]["ox_item"]).split("\n") == [
        "(1) Games must be entertaining.", "(2) Developers try to entertain.", "(3) Fun makes learning harder."]
    assert not [i for i in ctx.issues if "O/X" in i["msg"] or "ox_item" in i["msg"]]
    pg = {"id": "t", "items": [_text("b2_q+ox_item", 40)]}
    render._fill_items(pg, st, _ctx(lib))
    lines = render.rich_plain(pg["items"][0]["fields"]["b2_q+ox_item"]).split("\n")
    assert lines[0].startswith("다음 글의") and lines[1].startswith("(1)") and len(lines) == 4


def test_element_fills_by_slot_names_for_role_sets(lib):
    """요소(블록)도 역할 원고는 자리 이름으로 받는다 — 같은 요소 셋이면 O/X 한 줄씩. labels 없는 원고는 여전히 유형 이름으로만."""
    from core.units import render
    row = {"id": "p_row", "name": "O/X 줄", "source": "content", "fields": {"no": {"type": "text"}, "ox_item": {"type": "rich"}},
           "variants": [{"id": "v1", "part": "gox_row"}]}
    lib2 = dict(lib, blocks=lib["blocks"] + [row])
    pg = {"id": "t", "items": [{"block": "p_row", "x": 20, "y": y} for y in (40, 50, 60)]}
    render._fill_items(pg, _sets()[0], _ctx(lib, lib2))
    assert [it["fields"] for it in pg["items"]] == [{"no": "(1)", "ox_item": "Games must be entertaining."},
                                                  {"no": "(2)", "ox_item": "Developers try to entertain."},
                                                  {"no": "(3)", "ox_item": "Fun makes learning harder."}]
    st = {"kind": "passage", "id": "9", "blocks": [{"block": "gram_ox", "fields": {"no": 1, "sentence": "x"}}]}
    pg = {"id": "t", "items": [{"block": "p_row", "x": 20, "y": 40}]}
    render._fill_items(pg, st, _ctx(lib, lib2))
    assert pg["items"][0].get("_empty")                                          # 자리 이름이 같아도 다른 유형으로 안 샌다


def test_answers_page_once_collects_all(lib):
    """정답지 면(한 번만 · 받는 원고 answers) — 모든 원고의 정답을 한 흐름으로. 원자 「정답 묶음」 자리가 받는다."""
    from core.units import render
    lib2 = {k: list(v) for k, v in lib.items()}
    lib2["pages"] = lib2["pages"] + [{"id": "ans", "name": "정답", "spec": "a4", "zones": [], "items": [_text("answers", 30, 200)]}]
    plan = {"id": "p", "name": "p", "spec": "a4", "front": [], "back": [],
            "sections": [{"id": "s", "name": "본문", "pages": [{"page": "ans", "repeat": "once", "sets": ["answers"]}]}]}
    out = render.plan_svgs(_ctx(lib, lib2), plan, _sets(), lib2)
    assert len(out) == 1 and "(1) fun" in _t(out[0]["svg"]) and "③" in out[0]["svg"]


def test_two_passages_per_page(lib):
    """「지문 2개씩 한 장」(per 2) — 지문 번호·본문 자리를 두 벌 그린 면에 지문 둘이 위·아래로. 유형별·지문별 둘 다."""
    from core.units import render, store
    from core.units.formats import workbook as workbook_src
    mk = lambda no: {"step": 1, "logo": "A1", "title": "어휘 선택 1", "key": "step1_a1",
                     "groups": [{"label": str(no), "units": [[{"role": "vocab_sel", "text": f"passage {no}"}]]}]}
    sets = workbook_src.steps_to_sets([mk(20), mk(21), mk(22)])
    lib2 = {k: list(v) for k, v in lib.items()}
    lib2["pages"] = lib2["pages"] + [{"id": "a1", "name": "A1", "spec": "a4", "zones": [], "items": [
        _text("pnum", 30, 6), _text("vocab_sel", 40, 90), _text("pnum", 150, 6), _text("vocab_sel", 160, 90)]}]
    for order in (None, "by_set"):
        plan = {"id": "p", "name": "p", "spec": "a4", "front": [], "back": [], "order": order,
                "sections": [{"id": "s", "name": "본문", "pages": [{"page": "a1", "repeat": "each_set", "per": 2, "sets": ["A1 어휘 선택 1"]}]}]}
        assert store.validate("plans", dict(plan, order="by_set")) is None
        out = render.plan_svgs(_ctx(lib, lib2), plan, sets, lib2)
        assert len(out) == 2, order                                               # 지문 셋 → 20·21 한 면, 22 한 면
        assert "passage 20" in _t(out[0]["svg"]) and "passage 21" in _t(out[0]["svg"]) and "passage 22" in _t(out[1]["svg"])


def test_mirror_part_flips_inside():
    """왼쪽 면(짝수 쪽) — 요소 안쪽 배치도 좌우로: 오른쪽 끝 옆 탭이 왼쪽 끝으로. 글자는 그대로."""
    from core.units import render
    part = {"id": "t", "w": 200, "h": 10, "atoms": [{"t": "rect", "x": 190, "y": 0, "w": 10, "h": 10},
                                                   {"t": "line", "x1": 0, "y1": 0, "x2": 20, "y2": 0},
                                                   {"t": "text", "x": 0, "y": 0, "w": 30, "h": 5, "text": "12"},
                                                   {"t": "text", "x": 150, "y": 0, "w": 50, "h": 5, "text": "A2", "align": "right"}]}
    m = render.mirror_part(part)
    assert m["atoms"][0]["x"] == 0 and (m["atoms"][1]["x1"], m["atoms"][1]["x2"]) == (200, 180) and m["atoms"][2]["x"] == 170
    assert m["atoms"][2]["text"] == "12" and part["atoms"][0]["x"] == 190                   # 원본은 안 바뀐다
    assert "align" not in m["atoms"][2] and m["atoms"][3]["align"] == "left" and m["atoms"][3]["x"] == 0   # 정렬 준 글만 바깥쪽으로


def test_bind_schema_allows_joined_slots():
    """자리 이름 a+b(자리 여럿)는 저장된다 — 전엔 스키마에 걸려 그 면이 저장·복제가 안 됐다."""
    from core.units import store
    page = {"id": "page_1", "name": "t", "spec": "a4", "zones": [], "items": [_text("b2_q+b2_choice", 40)]}
    assert store.validate("pages", page) is None
    page["items"][0]["atom"]["bind"] = "b2_q+"
    assert store.validate("pages", page)


def test_raw_colors_and_fonts_without_brand(lib):
    """빈 상태에서 그린다 — 색·서체를 직접 값(#rrggbb · 서체 이름)으로 저장하고, 브랜드가 없어도 기본 견본으로 그린다."""
    from core.units import render, store
    atom = {"t": "text", "x": 0, "y": 0, "w": 60, "h": 8, "size": 12, "font": "Montserrat", "color": "#77a1c4", "text": "STEP"}
    page = {"id": "page_1", "name": "t", "spec": "a4", "zones": [], "items": [{"atom": atom, "x": 10, "y": 10},
            {"atom": {"t": "rect", "x": 0, "y": 0, "w": 20, "h": 5, "fill": "#cba56f"}, "x": 10, "y": 30}]}
    assert store.validate("pages", page) is None
    page["items"][0]["atom"]["color"] = "$Bad"
    assert store.validate("pages", page)                                   # 견본 이름 규칙은 그대로
    page["items"][0]["atom"]["color"] = "#77a1c4"
    lib2 = dict(lib, skins=[])
    ctx = render.Ctx(None, lib2, {})                                       # 브랜드 없음 — 기본 견본
    svg = render.page_canvas_svgs(ctx, page, render.DEFAULT_SPEC)[0]["svg"]
    assert "#77a1c4" in svg and "Montserrat" in svg and "#cba56f" in svg and "#ff00ff" not in svg
    ctx = render.Ctx(None, lib2, {})
    t = {"t": "text", "x": 0, "y": 0, "w": 60, "h": 8, "size": 9, "font": "$body", "color": "$ink", "text": "x"}
    svg = render.page_canvas_svgs(ctx, dict(page, items=[{"atom": t, "x": 0, "y": 0}]), render.DEFAULT_SPEC)[0]["svg"]
    assert "#231f20" in svg and "#ff00ff" not in svg and not ctx.warnings            # $ink · $body 는 기본 견본에서


def _mock_set():
    from core.units.formats import mockexam
    paras = [{"pstyle": "문제 번호", "text": "윗글의 주제는?"}, {"pstyle": "지문", "text": "First paragraph. " * 20},
             {"pstyle": "지문", "text": "Second paragraph. " * 20}, {"pstyle": "선지", "text": "① a"}, {"pstyle": "선지", "text": "② b"}] * 12
    s = mockexam.paragraphs_to_set(paras, "한영고", "1", 1)
    return dict(s, format="mockexam", labels=mockexam.LABELS, fmt=mockexam.FMT)


def test_paragraph_shapes_in_story(lib):
    """단락 모양(자리마다 서식) — 잇닿은 지문 단락은 테두리 상자 하나로, 선지는 들여쓰기. 그려지면 div 로."""
    from core.units import render
    pg = {"id": "t", "items": [_text("m_q+m_passage+m_choice", 40)]}
    render._fill_items(pg, _mock_set(), _ctx(lib))
    v = pg["items"][0]["fields"]["m_q+m_passage+m_choice"]
    paras = [x for x in v if isinstance(x, dict) and "para" in x]
    boxes = [x for x in paras if x["para"].get("box")]
    assert len(boxes) == 12 and "Second paragraph" in render.rich_plain(boxes[0])            # 지문 두 단락이 상자 하나
    assert any(x["para"].get("indent") == 3 for x in paras)
    html = render.rich_html(v, _ctx(lib))
    assert html.count("border:0.3px solid") == 12 and "padding-left:3.00px" in html


def test_overflow_continues_on_other_page(lib):
    """넘치면 이어 갈 면(page.cont) — 첫 면(제목 있음)에서 넘친 글이 둘째 면 모양의 같은 자리 글상자로. 상자 안에서 잘려도 모양 유지."""
    from core.units import render
    story = "m_q+m_passage+m_choice"
    first = {"id": "f1", "name": "첫", "spec": "a4", "zones": [], "cont": "f2",
             "items": [dict(_text(None, 20, 10), atom=dict(_text(None, 20, 10)["atom"], text="FIRST TITLE")), _text(story, 40, 230)]}
    first["items"][0]["atom"].pop("bind", None)
    nxt = {"id": "f2", "name": "둘", "spec": "a4", "zones": [], "items": [
        {"atom": {"t": "text", "x": 0, "y": 0, "w": 170, "h": 8, "size": 9, "font": "$body", "color": "$ink", "text": "RUNNING HEAD"}, "x": 20, "y": 20},
        _text(story, 35, 235)]}
    lib2 = {k: list(v) for k, v in lib.items()}
    lib2["pages"] = lib2["pages"] + [first, nxt]
    plan = {"id": "p", "name": "p", "spec": "a4", "front": [], "back": [],
            "sections": [{"id": "s", "name": "본문", "pages": [{"page": "f1", "repeat": "each_set"}]}]}
    out = render.plan_svgs(_ctx(lib, lib2), plan, [_mock_set()], lib2)
    assert len(out) >= 2
    assert "FIRST TITLE" in _t(out[0]["svg"]) and "RUNNING HEAD" not in _t(out[0]["svg"])
    assert [("RUNNING HEAD" in _t(o["svg"]), "FIRST TITLE" in _t(o["svg"])) for o in out[1:]] == [(True, False)] * (len(out) - 1), [o["label"] for o in out]
    assert "윗글의 주제는" in _t(out[-1]["svg"]) or "② b" in _t(out[-1]["svg"])
    assert all("border:0.3px solid" in o["svg"] for o in out)                                # 나뉜 상자도 양쪽 모두 상자
    # 이어 갈 면이 문서에 들어 있어도 「찍지 않음」이면 따로 안 찍힌다 · 면마다 자기 판형
    first["spec"] = nxt["spec"] = "b4_exam"
    plan["sections"][0]["pages"].append({"page": "f2", "repeat": "none"})
    from core.units import store
    assert store.validate("plans", plan) is None
    out2 = render.plan_svgs(_ctx(lib, lib2), plan, [_mock_set()], lib2)
    assert len(out2) <= len(out) and 'viewBox="0 0 257' in out2[0]["svg"]                  # B4 라 면이 늘지 않고, B4 로 찍힌다
