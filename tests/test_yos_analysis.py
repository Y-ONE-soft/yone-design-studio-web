# -*- coding: utf-8 -*-
"""contents 분석본(yos-analysis-v1, 조판 문서) → 편집기 제작 분석본 틀 원고 (core/sources/yos_analysis.py)"""
import re

from core.sources import yos_analysis as ya


def _span(tagged, word, role, **kw):
    counted = re.sub(r"\[[^\]]*\]", "", tagged)                       # 역할 마크 자리 = 대괄호 태그만 빼고 센 자리
    s = counted.index(word)
    return dict({"start": s, "end": s + len(word), "role": role}, **kw)


def test_ruby_and_roles():
    t = "B: Sounds[V] like[전] a great idea."
    runs = ya.sentence_runs(t, [_span(t, "like", "grammar"), _span(t, "great", "vocab")])
    assert runs == ["B: ", {"t": "Sounds", "ruby": {"t": "V", "pos": "below"}}, " ",
                    {"t": "like", "ruby": {"t": "전", "pos": "below"}, "cs": "파랑 글자"}, " a ",
                    {"t": "great", "cs": "빨강 글자"}, " idea."]


def test_highlight_badge_and_overlap():
    t = "players[S] aimed[V] to go"
    runs = ya.sentence_runs(t, [_span(t, "players aimed", "descriptive", badge=True), _span(t, "aimed", "vocab")])
    assert runs[0] == {"t": "players", "ruby": [dict(ya.BADGE), {"t": "S", "pos": "below"}], "cs": "형광 노랑"}
    assert runs[2] == {"t": "aimed", "ruby": {"t": "V", "pos": "below"}, "cs": ["빨강 글자", "형광 노랑"]}   # 글자색 먼저, 형광 다음
    assert runs[-1] == " to go"


def test_upper_ruby_and_elision():
    t = "sing for ⌃(the elderly) them[^Cuju] instead"
    runs = ya.sentence_runs(t, [])
    assert "".join(r if isinstance(r, str) else r["t"] for r in runs) == "sing for them instead"   # 생략 자리 띄어쓰기 하나
    them = next(r for r in runs if isinstance(r, dict))
    assert them["ruby"] == {"t": "Cuju the elderly", "pos": "above"}


def test_record_and_short_lesson():
    doc = {"meta": {"title": "Lesson 1. We Share, We Care", "source": "A Listen and Answer 1 (p.12)", "subject": ""},
           "title": {"en": "", "ko": "노래 봉사"}, "topic": "T", "summary": "S", "layoutType": "base",
           "sentences": [{"no": 1, "tagged": "Hi[S].", "ko": "안녕.", "gps": ["hi 는 감탄사"], "refs": [], "marks": []}],
           "keyQuestion": {"q": "맞는 것은?", "passage": ["A", "B"], "choices": ["x", "<u>y</u>"], "answerIndex": 2},
           "voca": [{"word": "hi", "ko": "안녕"}]}
    c, rep = ya.to_content({"format": "yos-analysis-v1", "analyses": [doc, dict(doc, layoutType="short")]})
    r = c["분석 펼침면"][0]
    assert (r["강"], r["회차"], r["지문제목"]) == ("1과", "분석", "A Listen and Answer 1 (p.12) · 노래 봉사")
    assert r["문장+해석"][0]["문장"][0] == {"t": "", "side": "* hi 는 감탄사"}
    assert r["문장+해석"][0]["문장"][1] == "1 "
    assert r["발문+문제지문+선지"][0]["선지"] == ["① x\n② ", {"t": "y", "cs": "밑줄"}]
    assert r["답"] == "답: ②" and r["어휘"] == "hi\t안녕"
    assert len(c["분석 펼침면"]) == 1 and rep["skipped"][0]["why"].startswith("짤지문형")
    assert ya.short_lesson("7강 분석") == "7강" and ya.short_lesson("Unit 3") == "3과"
