"""contents 원고(yos-workbook-v1) → 편집기 제작 틀 원고 (core/sources/yos_editor.py)"""
from collections import Counter

from core.sources import yos_editor

SAMPLE = {"교재명": "견본 교재", "단원명": "1강",
          "A어휘선택": [{"제목": "어휘 선택 1", "지문번호": ["2", "4", "6", "8"], "지문": ["a", "b", "c", "d"]}]}
CAPS = {"A어휘선택": Counter({"제목": 1, "지문번호": 4, "지문": 4}),
        "B내용종합": Counter({"제목": 1, "지문번호": 2, "지문": 2, "문제번호": 6, "발문": 6, "선지": 6}),
        "C빈칸어휘": Counter({"제목": 1, "지문번호": 2, "문항번호+빈칸문장+해석": 2}),
        "C빈칸어법": Counter({"제목": 1, "지문번호": 2, "문항번호+빈칸문장+해석": 2}),
        "C영작배열": Counter({"제목": 1, "지문번호": 10, "문항번호": 10, "우리말": 10, "보기단어": 10}),
        "S실전문제": Counter({"지문번호+번호+발문+보기+지문+요약문+선지+조건+주석": 1})}


def _data(items, n=1):
    return {"format": "yos-workbook-v1", "book": {"title": "연동 시험"},
            "passages": [{"no": str(18 + i), "content": f"passage {i}", "items": items} for i in range(n)]}


VOCAB = {"key": "vocab-choice", "label": "어휘선택 1단계", "content": {"kind": "vocab-choice", "text": "x (1)❮ ⓐ up / ⓑ down ❯ y"}}


def test_vocab_choice_marks_and_record():
    content, rep = yos_editor.to_content(_data([VOCAB]), SAMPLE, CAPS)
    assert content["A어휘선택"] == [{"제목": "어휘 선택 1", "지문번호": ["18"], "지문": ["x [ ⓐ up / ⓑ down ] y"]}]
    assert content["교재명"] == "연동 시험" and content["단원명"] == "1강"
    assert [s["key"] for s in rep["sent"]] == ["vocab-choice"]


def test_passages_per_set_from_template():
    content, _ = yos_editor.to_content(_data([VOCAB], 5), SAMPLE, CAPS)
    assert [r["지문번호"] for r in content["A어휘선택"]] == [["18", "19", "20", "21"], ["22"]]


def test_unknown_kind_reported_and_empty():
    content, rep = yos_editor.to_content(_data([{"key": "raw:grammar-ox", "label": "어법OX", "content": {"kind": "raw"}}]), SAMPLE, CAPS)
    assert content == {}
    assert rep["skipped"][0]["label"] == "어법OX"


def test_blanks_hint_and_plain():
    rows = {"rows": [{"en": "much 1[colder], but 2[crucially] it", "ko": "해석", "blanks": [{"no": 1, "hint": "c", "answer": "colder"}, {"no": 2, "hint": "c", "answer": "crucially"}]}]}
    content, _ = yos_editor.to_content(_data([{"key": "vocab-blank", "label": "빈칸어휘 1단계", "content": dict(rows, kind="vocab-blank")},
                                              {"key": "grammar-blank", "label": "빈칸어법", "content": dict(rows, kind="grammar-blank")}]), SAMPLE, CAPS)
    k = "문항번호+빈칸문장+해석"
    assert content["C빈칸어휘"][0][k] == [[{"문항번호": "01.", "빈칸문장": "much {c}__, but {c}__ it", "해석": "해석"}]]
    assert content["C빈칸어법"][0][k][0][0]["빈칸문장"] == "much __, but __ it"


def test_summary_pads_questions_per_passage():
    q = {"prompt": "[1~2] 다음 글을 읽고, 물음에 답하시오.\n1. Which is true?", "choices": ["a", "b"], "answer": "1"}
    item = {"key": "mock-exam", "label": "내용종합", "content": {"kind": "mock-exam", "questions": [q, dict(q, prompt="2. Pick all.", passage="<보기>\n(a) x")]}}
    content, _ = yos_editor.to_content(_data([item], 2), SAMPLE, CAPS)
    r = content["B내용종합"][0]
    assert r["문제번호"] == ["01", "02", "", "01", "02", ""]
    assert r["발문"][0] == "Which is true?" and r["발문"][1] == "Pick all.\n<보기>\n(a) x"
    assert r["선지"][0] == "① a\n② b"


def test_writing_order_rows_and_exam_story():
    wo = {"key": "writing-order", "label": "영작배열 1단계", "content": {"kind": "writing-order", "items": [{"ko": "가", "chunks": ["a", "b"]}, {"ko": "나", "chunks": ["c"]}]}}
    topic = {"key": "mock-exam", "label": "주제", "content": {"kind": "mock-exam", "questions": [{"prompt": "주제는?", "choices": ["x", "y"]}]}}
    content, _ = yos_editor.to_content(_data([wo, topic]), SAMPLE, CAPS)
    assert content["C영작배열"][0]["보기단어"] == ["( a / b )", "( c )"] and content["C영작배열"][0]["지문번호"] == ["18", ""]
    story = content["지문번호+번호+발문+보기+지문+요약문+선지+조건+주석"]
    assert story[0][0] == ["지문번호", "18"] and story[1] == [["번호", "01"], ["발문", "주제는?"], ["선지", "① x\n② y"]]
