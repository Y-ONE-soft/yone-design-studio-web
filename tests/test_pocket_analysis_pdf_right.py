"""분석본 PDF **오른쪽 면** — 플로우노트(NOTE 상자)·동반의어 칸.

분석본마다 오른쪽 면이 다르다. 추가 읽기 자료(명일2 05)는 NOTE 가 빈 상자이고
동반의어 칸이 없지만, 들어 있는 판도 있다 — 들어 있으면 그게 포켓북 오른쪽 면의
정본이라 우리가 다시 쓰지 않고 읽어 온다.

표본은 Y.OS **실제 조판 엔진**으로 찍었다(`tests/corpus/pocket_analysis_pdf/`).
여기 적힌 것은 전부 실제로 걸렸던 자리다:

  · 머리글 크기로 표를 찾았다 — 명일2 는 5.9pt 인데 강동 2024 는 9pt 다
  · 머리글 색이 구문분석 파랑(`#557abc`)이라 표가 통째로 안 읽혔다
  · 칸 순서가 디자인마다 다르다 — 강동은 유의어·반의어, 배재는 반의어·동의어
  · `핵심기출문제` 와 `FLOW NOTE` 는 **기준선이 같아** 한 줄로 묶인다
  · 상자 경계를 단 가운데로 어림하면 옆 단 `[정답] : ②`(x283)가 딸려 온다
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "pocket_harvest"))
FIX = os.path.join(HERE, "corpus", "pocket_analysis_pdf")

POCKET = os.path.expanduser("~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북")
REAL = os.path.join(POCKET, "_idml", "analysis", "고1,고2(공통)", "26-2-중간",
                    "명일2", "명일여고2_분석본05(추가 읽기자료).pdf")


def _read(name):
    import analysis_pdf as A
    A.KO_DIRS[:] = []
    return A.read_book(os.path.join(FIX, name))


def _cards(name):
    got = _read(name)
    assert len(got) == 1
    return got[0]


def test_synonym_table_read():
    """동반의어 표 → 카드. 유의어·반의어가 제 칸에서 온다."""
    p = _cards("yos_synonym.pdf")
    cards = {c["w"]: c for c in p["synonyms"]}
    assert cards["inefficient"] == {"w": "inefficient", "ko": "비효율적인",
                                    "syn": ["wasteful"], "ant": ["efficient"]}
    assert cards["overlook"]["syn"] == ["ignore"]
    assert cards["overlook"]["ant"] == ["notice"]
    # 반의어가 없는 낱말도 카드가 된다(완성본 19% 가 반의어 없음)
    assert cards["transition"] == {"w": "transition", "ko": "변화",
                                   "syn": ["shift"], "ant": []}


def test_synonym_cards_only_when_written():
    """칸이 있다고 다 카드가 아니다 — 적힌 줄만 센다(표 28줄 중 8줄)."""
    p = _cards("yos_synonym.pdf")
    assert len(p["voca"]) == 28
    assert len(p["synonyms"]) == 8
    assert all(c["syn"] or c["ant"] for c in p["synonyms"])


def test_column_order_is_read_by_name():
    """칸 순서가 달라도 유의어·반의어가 뒤집히지 않는다.

    강동 2024 는 `단어·의미·유의어·반의어`, 배재는 `단어·뜻·품사·반의어·동의어`다.
    자리로 읽으면 두 판이 서로 뒤집힌다.
    """
    a = {c["w"]: c for c in _cards("yos_synonym.pdf")["synonyms"]}
    b = {c["w"]: c for c in _cards("yos_synonym_baejae.pdf")["synonyms"]}
    for w in ("inefficient", "overlook", "potential", "effective"):
        assert a[w]["syn"] == b[w]["syn"], w
        assert a[w]["ant"] == b[w]["ant"], w


def test_flownote_box_read():
    """NOTE 상자의 글 → 플로우노트. 접힌 줄은 앞 줄에 이어 붙인다."""
    p = _cards("yos_flownote.pdf")
    assert p["flownote"] == [
        "[도입] 몸속 원자는 우주만큼 오래됐다",
        "→ 숨 쉴 때 들이마신 원자 일부만 다시 나간다",
        "[예시] 남은 원자는 몸의 일부가 되고 여러 방법으로 몸을 떠난다",
        "[결론] 원자는 빌려 쓰는 것 · 600년도 더 전",
    ]


def test_flownote_does_not_eat_the_exam_column():
    """두 단(`핵심기출문제 | FLOW NOTE`)에서 옆 단 글이 섞이지 않는다."""
    p = _cards("yos_flownote.pdf")
    joined = " ".join(p["flownote"])
    assert "정답" not in joined
    assert "Many atoms" not in joined
    assert "제목으로" not in joined


def test_empty_note_box_stays_empty():
    """빈 상자는 빈 채로 — 학생이 쓰는 자리다(강동 2024 흐름 상자 넷)."""
    assert _cards("yos_synonym.pdf")["flownote"] == []


@pytest.mark.skipif(not os.path.exists(REAL), reason="원본 PDF 없음")
def test_real_additional_reading_unchanged():
    """명일2 추가 읽기 자료는 NOTE 가 비었고 동반의어 칸이 없다 — 전과 같다."""
    import analysis_pdf as A
    A.KO_DIRS[:] = []
    got = A.read_book(REAL)
    assert [len(g["voca"]) for g in got] == [16, 18]
    assert [g["flownote"] for g in got] == [[], []]
    assert [g["synonyms"] for g in got] == [[], []]
