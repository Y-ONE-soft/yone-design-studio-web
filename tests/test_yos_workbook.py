# -*- coding: utf-8 -*-
"""core/sources/yos_workbook — contents 의 지문별 워크북 원고(yos-workbook-v1) → 워크북 data.json.

고정본은 contents 가 실제로 저장하는 kind 별 모양(scripts/workbook-source/lib/content.ts)을 따른다.
"""
import json
import os

import pytest

from core.sources import SourceError, resolve
from core.sources import yos_workbook as yw

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def raw():
    with open(os.path.join(HERE, "fixtures", "yos_workbook_v1.json"), encoding="utf-8") as f:
        return json.load(f)


def _step(d, key):
    return next(s for s in d["steps"] if s["key"] == key)


def test_steps_and_labels(raw):
    d = yw.to_data(raw)
    assert [s["key"] for s in d["steps"]] == [
        "step1_a1", "step1_a1_2", "step1_a2", "step1_c1", "step1_c2", "step2_a1", "step2_b1", "step2_c2"]
    for s in d["steps"]:
        assert s["groups"][0]["label"] == "20"
        assert s["layout"]                              # STEP_META 를 그대로 물려받는다
    assert d["book"]["line2"] == "26년 3월"


def test_vocab_choice_brackets_and_two_stages(raw):
    d = yw.to_data(raw)
    a1 = _step(d, "step1_a1")["groups"][0]["units"][0][0]
    a2 = _step(d, "step1_a1_2")["groups"][0]["units"][0][0]
    assert a1["role"] == "vocab_sel" and "(1)[ ⓐ inferior / ⓑ better ]" in a1["text"]
    assert "❮" not in a1["text"]
    # 한 원고에 (1) 이 두 번 → 뒤쪽은 2단계, 문장 첫머리부터
    assert a2["text"].startswith("There is simply no (1)[ ⓐ superior")
    assert "superior" not in a1["text"]


def test_content_ox_has_passage_prompt_and_tf_icon(raw):
    blocks = _step(yw.to_data(raw), "step1_a2")["groups"][0]["units"][0]
    assert [b["role"] for b in blocks] == ["box_body", "b2_q", "ox_item", "ox_item"]
    assert blocks[2]["text"].startswith("(1) ") and blocks[2]["icon"] == "TF 버튼"


def test_blank_vocab_uses_answer_or_hint(raw):
    blocks = _step(yw.to_data(raw), "step1_c2")["groups"][0]["units"][0]
    assert blocks[0]["text"].endswith("1[influence] or stir an audience.")   # 정답 있음
    assert blocks[1]["role"] == "blank_kr"
    assert "2[t]" in blocks[2]["text"]                                        # 정답 없음 → 힌트 글자


def test_grammar_choice_answer_key_attaches_bottom(raw):
    g = _step(yw.to_data(raw), "step2_a1")["groups"][0]
    assert g["units"][0][0]["role"] == "gram_sel" and "1[to influence / influencing]" in g["units"][0][0]["text"]
    assert g["attach"][0][0]["role"] == "gram_bottom" and "①to influence" in g["attach"][0][0]["text"]


def test_grammar_fix_underlines_marks_per_sentence(raw):
    blocks = _step(yw.to_data(raw), "step2_b1")["groups"][0]["units"][0]
    assert [b["text"][:3] for b in blocks] == ["1. ", "2. ", "3. "]
    assert "[" not in blocks[0]["text"]
    assert [r["t"] for r in blocks[0]["runs"] if r["ul"]] == ["are"]


def test_unknown_items_are_skipped_with_log(raw):
    lines = []
    yw.to_data(raw, log=lines.append)
    assert any("본문해석 1단계" in l for l in lines)


def test_resolve_adapts_by_format_marker(raw):
    kind, obj = resolve({"type": "data", "data": raw}, "workbook")
    assert kind == "data" and "steps" in obj and "format" not in obj
    with pytest.raises(SourceError):
        resolve({"type": "data", "data": raw}, "vocabook")
    with pytest.raises(SourceError):
        resolve({"type": "data", "data": dict(raw, passages=[])}, "workbook")
