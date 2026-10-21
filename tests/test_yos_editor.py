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
    assert content["A어휘선택"] == [{"제목": "어휘 선택 1", "지문번호": ["1"], "지문": ["x [ ⓐ up / ⓑ down ] y"]}]
    assert content["교재명"] == "연동 시험" and content["단원명"] == ""          # 단원명은 contents 가 안 보낸다 — 견본 글을 남기지 않는다
    assert [s["key"] for s in rep["sent"]] == ["vocab-choice"]


def test_vocab_choice_uploaded_manuscript():
    """워크북 프리셋 「업로드본」 — 원고 그대로(doc 만, text 없음) 1단계 · 2단계도 지문 칸에 들어간다(2026-10-20 빈 면 사고)"""
    def ms(kind, body):
        return {"form": "manuscript", "kind": kind, "label": "[21]",
                "doc": {"problem": [{"type": "p", "style": "Heading_num", "runs": [{"t": "[21]"}]},
                                    {"type": "p", "style": "Normal_modified_box", "runs": [{"t": "x "}, {"b": True, "t": body}, {"t": " y"}]}],
                        "answer": [{"type": "p", "style": "Normal_exp", "runs": [{"t": "(1) ⓐ"}]}]}}
    items = [{"key": "vocab-choice", "label": "어휘선택 1단계", "content": ms("vocab-choice", "(1)❮ ⓐ up  / ⓑ down ❯")},
             {"key": "vocab-choice-2", "label": "어휘선택 2단계", "content": ms("vocab-choice-2", "(1)❮ ⓐ big / ⓑ large ❯")}]
    content, rep = yos_editor.to_content(_data(items), SAMPLE, CAPS)
    assert content["A어휘선택"] == [{"제목": "어휘 선택 1", "지문번호": ["1"], "지문": ["x [ ⓐ up / ⓑ down ] y"]},
                                   {"제목": "어휘 선택 2", "지문번호": ["1"], "지문": ["x [ ⓐ big / ⓑ large ] y"]}]
    assert [s["key"] for s in rep["sent"]] == ["vocab-choice", "vocab-choice-2"]


def test_component_manuscript_form():
    """컴포넌트 원고 꼴(wb-manuscript — AI · 업로드 같은 꼴) → 구성: 본문정리+주제 → B본문정리, 어법수정 → A어법선택 객관식 칸,
    영작배열(낱말 · 서술형) → C영작배열 한 구성"""
    ms = lambda comp, **kw: {"key": comp, "label": comp, "content": dict(form="wb-manuscript", component=comp, **kw)}
    items = [ms("cq-b54cc606", passage="P", topics=["t1", "t2"], titles=["h1", "h2"]),
             ms("q-topic", prompt="다음 글의 주제로 가장 적절한 것은?", passage="P", notes="* a: 가", choices=["x", "y"], answer="1"),
             ms("grammar-choice", passage="a 1[is / are] b", answers=[{"no": 1, "word": "is"}]),
             ms("cq-df5aa646", count=1, passage="a ①<u>is</u> b", answer="①", explanation=""),
             ms("cq-5361e6bd", items=[{"no": 1, "ko": "가", "words": "(a / b)", "answer": "a b"}]),
             ms("cq-dc819941", items=[{"no": 1, "ko": "나", "words": "( a / b ) ( c )", "answer": "a b c"}])]
    caps = dict(CAPS, B본문정리=Counter({"제목": 1, "지문번호": 2, "지문+주제+글제목": 2, "발문+문제지문+주석+선지": 2}),
                A어법선택=Counter({"제목": 1, "지문번호": 2, "지문": 2, "발문+문제지문": 2}),
                C영작배열=Counter({"제목": 1, "지문번호": 10, "문항번호": 10, "우리말": 10, "보기단어": 10}))
    content, rep = yos_editor.to_content(_data(items), SAMPLE, caps)
    assert not rep["skipped"]
    b = content["B본문정리"][0]
    assert b["지문+주제+글제목"][0] == [[["지문", "P"], ["주제", "t1\nt2"], ["글제목", "h1\nh2"]]]
    assert b["발문+문제지문+주석+선지"][0][0][0] == ["발문", "다음 글의 주제로 가장 적절한 것은?"]
    a = content["A어법선택"][0]
    assert a["지문"] == ["a [is / are] b"]
    assert a["발문+문제지문"][0] == [[["발문", "다음 밑줄 친 부분 중 어법상 틀린 것은?"], ["문제지문", ["a ①", {"t": "is", "cs": "밑줄"}, " b"]]]]
    assert content["C영작배열"][0]["보기단어"] == ["(a / b)", "( a / b ) ( c )"]


def test_question_form_goes_to_exam_story():
    """문제 꼴(유형 전용 꼴이 없는 것 — AI · 업로드 같은 꼴, 2026-10-21) → 실전 문제 자리. 문제 묶음이 아닌 유형은 빠진다"""
    q = {"no": 1, "prompt": "다음 글의 요지로 가장 적절한 것은?", "passage": "a <u>b</u>", "choices": ["x", "y"], "answer": "2"}
    items = [{"key": "cq-64489a01", "label": "주장", "content": dict(form="wb-manuscript", component="cq-64489a01", group="question", questions=[q])},
             {"key": "interpretation-1", "label": "본문해석 1단계", "content": dict(form="wb-manuscript", component="interpretation-1", group="step1", questions=[q])}]
    content, rep = yos_editor.to_content(_data(items), SAMPLE, CAPS)
    story = content["지문번호+번호+발문+보기+지문+요약문+선지+조건+주석"]
    assert story[1] == [["번호", "01"], ["발문", "다음 글의 요지로 가장 적절한 것은?"], ["보기", ["a ", {"t": "b", "cs": "밑줄"}]], ["선지", "① x\n② y"]]
    assert [s["key"] for s in rep["sent"]] == ["cq-64489a01"]
    assert [s["key"] for s in rep["skipped"]] == ["interpretation-1"]


def test_passages_per_set_from_template():
    content, _ = yos_editor.to_content(_data([VOCAB], 5), SAMPLE, CAPS)
    assert [r["지문번호"] for r in content["A어휘선택"]] == [["1", "2", "3", "4"], ["5"]]


def test_unknown_kind_reported_and_empty():
    content, rep = yos_editor.to_content(_data([{"key": "raw:grammar-ox", "label": "어법OX", "content": {"kind": "raw"}}]), SAMPLE, CAPS)
    assert content == {}
    assert rep["skipped"][0]["label"] == "어법OX"


def test_blanks_hint_and_plain():
    rows = {"rows": [{"en": "much 1[colder], but 2[crucially] it", "ko": "해석", "blanks": [{"no": 1, "hint": "c", "answer": "colder"}, {"no": 2, "hint": "c", "answer": "crucially"}]}]}
    content, _ = yos_editor.to_content(_data([{"key": "vocab-blank", "label": "빈칸어휘 1단계", "content": dict(rows, kind="vocab-blank")},
                                              {"key": "grammar-blank", "label": "빈칸어법", "content": dict(rows, kind="grammar-blank")}]), SAMPLE, CAPS)
    k = "문항번호+빈칸문장+해석"
    cs = {"t": "c", "cs": "첫 글자"}                                     # 힌트 = 꾸밈 조각(문자 스타일 「첫 글자」), 빈칸 「__」은 템플릿 GREP 이 문자 스타일 「빈칸」으로
    assert content["C빈칸어휘"][0][k] == [[{"문항번호": "01.", "빈칸문장": ["much ", cs, "__, but ", cs, "__ it"], "해석": "해석"}]]
    assert content["C빈칸어법"][0][k][0][0]["빈칸문장"] == "much __, but __ it"


def test_summary_pads_questions_per_passage():
    q = {"prompt": "[1~2] 다음 글을 읽고, 물음에 답하시오.\n1. Which is true?", "choices": ["a", "b"], "answer": "1"}
    item = {"key": "mock-exam", "label": "내용종합", "content": {"kind": "mock-exam", "questions": [q, dict(q, prompt="2. Pick all.", passage="<보기>\n(a) x")]}}
    content, _ = yos_editor.to_content(_data([item], 2), SAMPLE, CAPS)
    r = content["B내용종합"][0]
    assert r["문제번호"] == ["01", "02", "", "01", "02", ""]
    assert r["발문"][0] == "Which is true?" and r["발문"][1] == "Pick all.\n<보기>\n(a) x"
    assert r["선지"][0] == "① a\n② b"


def test_summary_flow_story_per_passage():
    """흐름 틀(지문+문제번호+발문+선지 — 인디자인 스토리) — 지문마다 한 줄기, 있는 문제만(칸 채우기 · 접기 묶음 없이), 밑줄은 문자 스타일 조각"""
    q = {"prompt": "1. Which is <u>true</u>?", "choices": ["a", "b"], "answer": "1"}
    item = {"key": "mock-exam", "label": "내용종합", "content": {"kind": "mock-exam", "questions": [q, dict(q, prompt="2. Pick all.")]}}
    caps = dict(CAPS, B내용종합=Counter({"제목": 1, "지문번호": 2, "지문+문제번호+발문+선지": 2}))
    content, _ = yos_editor.to_content(_data([item], 2), SAMPLE, caps)
    r = content["B내용종합"][0]
    k = "지문+문제번호+발문+선지"
    assert r["지문번호"] == ["1", "2"] and len(r[k]) == 2
    first = r[k][0]
    assert first[0] == [["지문", "passage 0"]] and len(first) == 3                # 지문 + 문제 둘(빈 문제 칸 없음)
    assert first[1] == [["문제번호", "01"], ["발문", ["Which is ", {"t": "true", "cs": "밑줄"}, "?"]], ["선지", "① a\n② b"]]


def test_ox_flow_story_per_passage():
    """흐름 틀 A본문OX — 지문 · O/X 문제 01 · 진술마다 번호 · 글(빈 객관식 칸 · 빈 진술 칸 없음)"""
    qs = [{"prompt": "다음 글의 내용과 일치하면 O", "passage": "It is <u>red</u>."}, {"prompt": "x", "passage": "It is blue."}]
    item = {"key": "mock-exam", "label": "내용OX 영어", "content": {"kind": "mock-exam", "questions": qs}}
    caps = dict(CAPS, A본문OX=Counter({"제목": 1, "지문번호": 2, "지문+문제번호+발문+선지+진술번호+진술": 2}))
    content, _ = yos_editor.to_content(_data([item], 1), SAMPLE, caps)
    items = content["A본문OX"][0]["지문+문제번호+발문+선지+진술번호+진술"][0]
    assert items[0] == [["지문", "passage 0"]] and items[1] == [["문제번호", "01"], ["발문", "다음 글의 내용과 일치하면 O"]]
    assert items[2] == [["진술번호", "01"], ["진술", ["It is ", {"t": "red", "cs": "밑줄"}, "."]]] and items[3] == [["진술번호", "02"], ["진술", "It is blue."]]


def test_grammar_two_frames_passage_and_fixed_question():
    """A어법선택 — 위 프레임 「지문」(따로 선 자리) + 아래 문제 프레임(발문+문제지문 — contents 에 문제가 없으면 빈 줄기)"""
    item = {"key": "grammar-choice", "label": "어법선택", "content": {"kind": "grammar-choice", "text": "a 1[is / are] b"}}
    caps = dict(CAPS, A어법선택=Counter({"제목": 1, "지문번호": 2, "지문": 2, "발문+문제지문": 2}))
    content, _ = yos_editor.to_content(_data([item], 2), SAMPLE, caps)
    r = content["A어법선택"][0]
    assert r["지문"] == ["a [is / are] b"] * 2 and r["발문+문제지문"] == [[], []]


def test_writing_order_rows_and_exam_story():
    wo = {"key": "writing-order", "label": "영작배열 1단계", "content": {"kind": "writing-order", "items": [{"ko": "가", "chunks": ["a", "b"]}, {"ko": "나", "chunks": ["c"]}]}}
    topic = {"key": "mock-exam", "label": "주제", "content": {"kind": "mock-exam", "questions": [{"prompt": "주제는?", "choices": ["x", "y"]}]}}
    content, _ = yos_editor.to_content(_data([wo, topic]), SAMPLE, CAPS)
    assert content["C영작배열"][0]["보기단어"] == ["( a / b )", "( c )"] and content["C영작배열"][0]["지문번호"] == ["1", ""]
    story = content["지문번호+번호+발문+보기+지문+요약문+선지+조건+주석"]
    assert story[0][0] == ["지문번호", "1"] and story[1] == [["번호", "01"], ["발문", "주제는?"], ["선지", "① x\n② y"]]
