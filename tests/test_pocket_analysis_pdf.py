"""분석본 PDF(코드 조판) → 포켓북 지문. 명일2 분석본05 실측 사례로 못 박는다.

IDML 없이 PDF 로만 오는 분석본(Y.OS 조판 → pdf-lib)을 `analysis_pdf` 가
지면에서 되읽는다. 여기 적힌 것은 전부 **실제로 틀렸던 자리**다:

  · `zero` 밑 `V1` 가 넉 낱말 구간 `likely … on` 에 걸렸다(가운데가 우연히 같다)
  · `graduating,` 밑 `동명사` 가 쉼표·옆 낱말로 갔다
  · 정리 면(핵심기출 사본)이 본문 뒤에 통째로 붙었다
  · VOCA 칸이 낱말 가운데서 쪼개졌다(`fascinated 매 | 료된`)
  · 물결이 소프트 마스크에 있어 곧은 밑줄로 읽혔다
  · 해석이 낱말 가운데서 줄이 바뀌어 `기 울이는` 으로 띄어졌다

원본 PDF 가 이 기계에 없으면 건너뛴다(교재 자료는 리포에 넣지 않는다).
"""
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "pocket_harvest"))

POCKET = os.path.expanduser("~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북")
PDF = os.path.join(POCKET, "_idml", "analysis", "고1,고2(공통)", "26-2-중간",
                   "명일2", "명일여고2_분석본05(추가 읽기자료).pdf")
CORPUS = os.path.join(POCKET, "_corpus")

pytestmark = pytest.mark.skipif(not os.path.exists(PDF), reason="원본 PDF 없음")


def _read(ko_dirs):
    import analysis_pdf as A
    A.KO_DIRS[:] = ko_dirs
    A._KO = None
    return A.read_book(PDF)


@pytest.fixture(scope="module")
def book():
    # 한글 줄 잇기와 무관한 시험 — 코퍼스를 안 읽는다(빈 폴더)
    return _read([tempfile.mkdtemp()])


def _runs(p):
    return p["passage"][0]["runs"]


def _first(p, word):
    return next(r for r in _runs(p) if r["t"] == word)


def test_two_passages_and_independent_count(book):
    import analysis_pdf as A
    assert len(book) == 2
    assert A.source_count(PDF) == 2


def test_clean_copy_matches_and_no_summary_page_in_body(book):
    for p in book:
        assert p["source"]["clean_match"] is True
        body = "".join(r["t"] for r in _runs(p))
        assert "NOTE" not in body and "다음 글" not in body


def test_topic_summary_title(book):
    p1 = book[0]
    assert p1["title"]["ko"] == "세균 성장의 수상한 지연"
    assert p1["topic"] == ("Monod's curiosity about a puzzling growth lag "
                           "in bacteria")
    assert p1["summary"].startswith("Jacques Monod found that")


def test_voca_cells_not_split(book):
    v = book[0]["voca"]
    assert len(v) == 16
    assert v[0] == {"w": "fascinated", "ko": "매료된"}
    assert {"w": "stumble upon", "ko": "우연히 발견하다"} in v
    assert len(book[1]["voca"]) == 18


def test_ruby_goes_to_single_word_first(book):
    p1, p2 = book
    assert _first(p1, "researcher")["ruby"] == "S"
    assert _first(p1, "how")["ruby"] == "O 간접의문문"
    assert _first(p2, "zero")["ruby"] == "V1"
    assert _first(p2, "likely")["ruby"] is None
    assert _first(p2, "graduating")["ruby"] == "동명사"
    assert all(r["ruby"] != "동명사" for r in _runs(p2)
               if r["t"] in (",", "school", "struggles"))


def test_second_row_label(book):
    row2 = [r for r in _runs(book[1]) if r.get("slot") == "dn2"]
    assert [(r["t"], r["ruby"]) for r in row2] == [("in", "this variability")]


def test_marks_highlight_wave(book):
    p1, p2 = book
    assert _first(p1, "named")["mark"] == "blue"
    assert _first(p1, "puzzling")["mark"] == "red"
    assert _first(p1, "elements")["hl"] == "orange"
    assert _first(p1, "sugar,")["hl"] == "yellow"
    waves = [r["t"] for r in _runs(p2) if r.get("wave")]
    assert waves == ["confirming", "investigating", "zero", "attempt", "single",
                     "attempt", "is", "considered", "has", "was", "raised",
                     "left", "struggles"]
    assert _first(p2, "confirming")["mark"] == "blue"
    assert not any(r.get("wave") for r in _runs(p1))


def _corpus_ready():
    if not os.path.isdir(CORPUS):
        return False
    # iCloud 에서 내려받지 않은(dataless) 파일이 있으면 읽다가 멈춘다
    return not any(e.stat(follow_symlinks=False).st_flags & 0x40000000
                   for e in os.scandir(CORPUS) if e.name.endswith(".json"))


@pytest.mark.skipif(not _corpus_ready(), reason="코퍼스가 iCloud 에만 있다")
def test_korean_line_joins():
    b = _read([CORPUS])
    ko = " ".join(p["translation"][0]["runs"][0]["t"] for p in b)
    for good in ("기울이는", "입증하려고", "일자리를", "이력을 지니고",
                 "원인이 아닐", "그는 이해하기"):
        assert good in ko, good
    for bad in ("기 울이는", "입 증하려고", "일자 리를"):
        assert bad not in ko, bad
