"""contents 원고(yos-workbook-v1) → 편집기 제작 틀 원고 (core/sources/yos_editor.py)"""
from core.sources import yos_editor

SAMPLE = {"교재명": "견본 교재", "단원명": "1강",
          "A어휘선택": [{"제목": "어휘 선택 1", "지문번호": ["2", "4", "6", "8"], "지문": ["a", "b", "c", "d"]}]}


def _data(n, kinds=("vocab-choice",)):
    return {"format": "yos-workbook-v1", "book": {"title": "연동 시험"},
            "passages": [{"no": str(18 + i), "items": [{"key": k, "label": k, "content": {"kind": k, "text": "x (1)❮ ⓐ up / ⓑ down ❯ y"}}
                                                         for k in kinds]} for i in range(n)]}


def test_vocab_choice_marks_and_record():
    content, rep = yos_editor.to_content(_data(1), SAMPLE)
    assert content["A어휘선택"] == [{"제목": "어휘 선택 1", "지문번호": ["18"], "지문": ["x [ ⓐ up / ⓑ down ] y"]}]
    assert content["교재명"] == "연동 시험" and content["단원명"] == "1강"
    assert [s["key"] for s in rep["sent"]] == ["vocab-choice"]


def test_four_passages_per_spread():
    content, _ = yos_editor.to_content(_data(5), SAMPLE)
    assert [r["지문번호"] for r in content["A어휘선택"]] == [["18", "19", "20", "21"], ["22"]]


def test_unknown_kind_reported_and_empty():
    content, rep = yos_editor.to_content(_data(1, kinds=("grammar-ox",)), SAMPLE)
    assert content == {}
    assert rep["skipped"][0]["key"] == "grammar-ox"
