# -*- coding: utf-8 -*-
"""워크북 원고(역할 원고) → 캔버스 — 변환기(core/units/workbook_src) · 원고 자리 글상자 · 요소의 자리 이름 채우기 · 정답지."""
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(REPO, "tests", "fixtures", "units")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(SEED, tmp_path / "catalog" / "_units")
    from core.units import store
    monkeypatch.setattr(store, "CATALOG", str(tmp_path / "catalog"))
    return store.library()


def _sets():
    """워크북 v2 엔진이 읽은 스텝 모양 → 세트 (지문 20)."""
    from core.units import workbook_src
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
    return {"atom": {"t": "text", "x": 0, "y": 0, "w": 170, "h": h, "size": 9, "font": "$body", "color": "$ink", "bind": bind}, "x": 20, "y": y}


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


def test_catalog_without_manuscript():
    """원고를 넣기 전에도 틀을 그릴 수 있다 — 워크북 유형(받는 원고)·자리(원고 자리) 목록이 엔진 표에서 온다. 세트 kind 와 같은 이름."""
    from core.units import workbook_src
    c = workbook_src.catalog()
    assert len(c["kinds"]) == 11 and c["kinds"][0] == "A1 어휘 선택 1" and "C2 영작 배열" in c["kinds"]
    assert {s["kind"] for s in _sets()} <= set(c["kinds"])
    assert c["labels"]["ox_item"] == "O/X 문항" and "no" not in c["labels"]


def test_looks_like_workbook():
    from core.units import workbook_src
    assert workbook_src.looks_like_workbook(["Step1 A1 어휘선택.docx", "Step2 B1 어법OX.docx"])
    assert not workbook_src.looks_like_workbook(["원고.docx", "Step1 A1 어휘선택.docx"])


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
    assert len(out) == 1 and "(1) fun" in out[0]["svg"] and "③" in out[0]["svg"]


def test_bind_schema_allows_joined_slots():
    """자리 이름 a+b(자리 여럿)는 저장된다 — 전엔 스키마에 걸려 그 면이 저장·복제가 안 됐다."""
    from core.units import store
    page = {"id": "page_1", "name": "t", "spec": "a4", "zones": [], "items": [_text("b2_q+b2_choice", 40)]}
    assert store.validate("pages", page) is None
    page["items"][0]["atom"]["bind"] = "b2_q+"
    assert store.validate("pages", page)
