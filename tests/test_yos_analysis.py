# -*- coding: utf-8 -*-
"""contents 분석본(yos-analysis-v1, 조판 문서) ⇄ 편집기 제작 분석본 틀 원고 (core/sources/yos_analysis.py)

왕복 검사 재료: tests/fixtures/analysis_docs.json — 분석본 NEW 사본 22문항(161문장)의 조판 문서(2026-10-12, contents 에서 읽기만)."""
import copy
import json
import os
import re

from core.sources import yos_analysis as ya

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "analysis_docs.json")
META = ("raw", "src", "rl")


def _strip(v):
    if isinstance(v, list):
        return [_strip(x) for x in v]
    if isinstance(v, dict):
        return {k: _strip(x) for k, x in v.items() if k not in META}
    return v


def _visible(runs):
    """화면에 보이는 것만 — 되돌리기 칸(raw · src · rl)을 뗀 조각"""
    return ya.norm_runs(_strip(ya.norm_runs(runs)))


def _span(tagged, word, role, **kw):
    counted = re.sub(r"\[[^\]]*\]", "", tagged)                       # 역할 마크 자리 = 대괄호 태그만 빼고 센 자리
    s = counted.index(word)
    return dict({"start": s, "end": s + len(word), "role": role}, **kw)


def _doc(sentences, **kw):
    d = {"meta": {"title": "Lesson 1. We Share, We Care", "source": "A Listen and Answer 1 (p.12)", "subject": "", "pageStart": 2},
         "title": {"en": "", "ko": "노래 봉사"}, "topic": "T", "summary": "S", "layoutType": "base", "sentences": sentences,
         "keyQuestion": {"q": "맞는 것은?", "passage": ["A", "B"], "choices": ["x", "<u>y</u>"], "answerIndex": 2},
         "examPoints": [], "examPointItems": [], "images": [], "voca": [{"word": "hi", "ko": "안녕", "sent": "", "tone": "", "antonym": "", "synonym": ""}]}
    d.update(kw)
    return d


def test_ruby_and_roles():
    t = "B: Sounds[V] like[전] a great idea."
    runs = _visible(ya.sentence_runs(t, [_span(t, "like", "grammar"), _span(t, "great", "vocab")]))
    assert runs == ["B: ", {"t": "Sounds", "ruby": {"t": "V", "pos": "below"}}, " ",
                    {"t": "like", "ruby": {"t": "전", "pos": "below"}, "cs": "파랑 글자"}, " a ",
                    {"t": "great", "cs": "빨강 글자"}, " idea."]


def test_highlight_badge_and_overlap():
    t = "players[S] aimed[V] to go"
    runs = _visible(ya.sentence_runs(t, [_span(t, "players aimed", "descriptive", badge=True), _span(t, "aimed", "vocab")]))
    assert runs[0] == {"t": "players", "ruby": [dict(ya.BADGE), {"t": "S", "pos": "below"}], "cs": "형광 노랑"}
    assert runs[2] == {"t": "aimed", "ruby": {"t": "V", "pos": "below"}, "cs": ["빨강 글자", "형광 노랑"]}   # 글자색 먼저, 형광 다음
    assert runs[-1] == " to go"


def test_upper_ruby_elision_and_refs():
    t = "sing for ⌃(the elderly) them[^Cuju] instead. It was it."
    runs = _visible(ya.sentence_runs(t, [], ["It = the song", "it = the song"]))
    assert "".join(r if isinstance(r, str) else r["t"] for r in runs) == "sing for them instead. It was it."   # 생략 자리 띄어쓰기 하나
    them = next(r for r in runs if isinstance(r, dict) and r["t"] == "them")
    assert them["ruby"] == {"t": "the elderly Cuju", "pos": "above"}
    its = [r for r in runs if isinstance(r, dict) and r["t"].lower().startswith("it")]
    assert [r["ruby"]["t"] for r in its] == ["the song", "the song"]       # 지칭어는 같은 낱말 모두에, 한 낱말에 하나


def test_record_and_short_lesson():
    doc = _doc([{"no": 1, "tagged": "Hi[S].", "ko": "안녕.", "gps": ["hi 는 감탄사"], "refs": [], "marks": []}])
    c, rep = ya.to_content({"format": "yos-analysis-v1", "analyses": [doc, dict(doc, layoutType="short")]})
    r = c["분석 펼침면"][0]
    assert (r["강"], r["회차"], r["지문제목"]) == ("1과", "분석", "A Listen and Answer 1 (p.12) · 노래 봉사")
    assert r["번호+문장+해석"][0]["문장"][0] == {"t": "", "side": "* hi 는 감탄사"}
    assert r["발문+문제지문+선지"][0]["선지"] == ["① x\n② ", {"t": "y", "cs": "밑줄"}]
    assert r["답"] == "답: ②" and r["어휘"] == "hi\t안녕"
    assert len(c["분석 펼침면"]) == 1 and rep["skipped"][0]["why"].startswith("짤지문형")
    assert ya.short_lesson("7강 분석") == "7강" and ya.short_lesson("Unit 3") == "3과"


def test_roundtrip_real_docs():
    """실데이터 22문항 — ① 안 고친 그대로 돌려받으면 원래 문서 ② 지문(_h) 없이 다시 지어도 보이는 게 같으면 원래 문서
    ③ 되돌리기 칸까지 지워도 보이는 지면은 같다"""
    docs = [x["doc"] for x in json.load(open(FIX, encoding="utf-8"))]
    assert len(docs) == 22
    for doc in docs:
        rec = ya.record(doc)
        assert ya.to_doc(rec, doc) == (doc, [])
        r2 = copy.deepcopy(rec)
        for row in r2["번호+문장+해석"]:
            row.pop("_h")
        assert ya.to_doc(r2, doc) == (doc, [])
        for s, row in zip(doc["sentences"], rec["번호+문장+해석"]):
            t, m, g, rf = ya.runs_sentence(_strip(row["문장"]))
            back = ([{"t": "", "side": "\n".join("* " + y for y in g)}] if g else []) + ya.sentence_runs(t, m, rf)
            assert _visible(back) == _visible(row["문장"]), (s["no"], s["tagged"])


def _edit(doc, fn):
    rec = ya.record(doc)
    fn(rec)
    return ya.to_doc(rec, doc)


def test_edits_come_back_as_contents_data():
    t = "It[S] read[V] like a story that was written."
    doc = _doc([{"no": 3, "tagged": t, "ko": "그것은 읽혔다.", "gps": ["like 는 전치사"], "refs": ["it = 구조 이야기"],
                 "marks": [_span(t, "story", "antecedent"), _span(t, "written", "grammar")]}])

    def runs(rec):
        return rec["번호+문장+해석"][0]["문장"]

    def find(rec, word):
        return next(r for r in runs(rec) if isinstance(r, dict) and r.get("t") == word)

    # 낱말에 색 — 「read」 를 빨강 글자(어휘)로
    d, ch = _edit(doc, lambda rec: find(rec, "read").update(cs="빨강 글자"))
    s = d["sentences"][0]
    assert ch == ["문장 3"] and s["tagged"] == t and _span(t, "read", "vocab") in s["marks"]
    # 아래 윗주 고치기 — 「read」 의 V → V2
    d, _ = _edit(doc, lambda rec: find(rec, "read")["ruby"].update(t="V2"))
    assert d["sentences"][0]["tagged"].startswith("It[S] read[V2] like")
    # 지칭어 윗주 지우기 → refs 에서 빠진다
    d, _ = _edit(doc, lambda rec: find(rec, "It")["ruby"].pop(0))
    assert d["sentences"][0]["refs"] == []
    # 낱말 고치기 — 뒤 마크 자리가 따라 민다
    def retype(rec):
        rr = runs(rec)
        i = next(i for i, r in enumerate(rr) if isinstance(r, str) and " like a " in r)
        rr[i] = rr[i].replace(" like a ", " just like a ")
    d, _ = _edit(doc, retype)
    s = d["sentences"][0]
    assert "just like a story" in s["tagged"]
    counted = re.sub(r"\[[^\]]*\]", "", s["tagged"])
    st = next(m for m in s["marks"] if m["role"] == "antecedent")
    assert counted[st["start"]:st["end"]] == "story"
    # 문법 포인트(옆 메모) · 해석 · 주제 · 어휘 · 답
    def misc(rec):
        runs(rec)[0]["side"] = "* like 는 전치사\n* read 는 자동사"
        rec["번호+문장+해석"][0]["해석"] = "그건 이야기처럼 읽혔다."
        rec["주제"] = "새 주제"
        rec["어휘"] = "hi\t안녕하세요\nstory\t이야기"
        rec["답"] = "답: ①"
    d, ch = _edit(doc, misc)
    s = d["sentences"][0]
    assert s["gps"] == ["like 는 전치사", "read 는 자동사"] and s["ko"] == "그건 이야기처럼 읽혔다."
    assert d["topic"] == "새 주제" and d["keyQuestion"]["answerIndex"] == 1
    assert [v["word"] for v in d["voca"]] == ["hi", "story"] and d["voca"][0]["ko"] == "안녕하세요"
    assert d["meta"] == doc["meta"] and d["images"] == doc["images"]           # 지면에 없는 칸은 그대로


def test_divider_fields():
    # 간지 — 보낸 것만 간지 칸으로(빈 줄은 빼고, 세 칸은 늘 함께), 안 보내면 간지 칸이 없다(간지 면 안 찍힘)
    data = {"analyses": [], "divider": {"school": " 2026 이대부고1 ", "volume": 1,
                                        "lines": [{"book": "공통영어2 YBM(김)", "lesson": "3과 Beyond Barriers"}, {"book": "", "lesson": ""}]}}
    content, _ = ya.to_content(data)
    assert content == {"학교": ["2026 이대부고1"], "권번호": ["1"], "교재명+강제목": [{"교재명": "공통영어2 YBM(김)", "강제목": "3과 Beyond Barriers"}]}
    content, _ = ya.to_content({"analyses": [], "divider": {"school": "2026 광문고1"}})
    assert content["권번호"] == [""] and content["교재명+강제목"] == [{"교재명": "", "강제목": ""}]
    assert ya.to_content({"analyses": []})[0] == {}
