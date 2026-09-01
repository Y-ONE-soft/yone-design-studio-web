# -*- coding: utf-8 -*-
"""파이널 계열(final) 오프라인 계약 검사 — InDesign·Vivliostyle 없이 돈다.

지키려는 것은 **지난 조판에서 실제로 깨졌던 것들**이다:
  · 문장삽입의 '주어진 문장 상자'를 스타일 이름으로 가르면 교과서 지문 셋이
    상자를 잃는다 → 자리(둘째 줄)로 판정하는가
  · 영작 헤더의 start_idx 가 단조가 아니면 옆 강 영작이 섞인다(광문3 실증)
    → 오름차순 경계로 자르는가
  · 중요어휘 `250341` ↔ 문장배열 `250341~42` 라벨 방언
  · 사분면 계약 — 두 칸을 쓰는 지문이 있으면 뒤 지문의 기대 면이 밀린다
  · 판면 수치(단 폭·단 사이·여백)가 완성본 실측과 맞는가
"""
import json
import os
import re

import pytest

from core.render_vivlio.series.final import data as D
from core.render_vivlio.series.final import render as R
from core.render_vivlio.series.final import verify as V

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(os.path.dirname(HERE), "core", "render_vivlio",
                   "themes", "final.css")


def _content(**over):
    c = {
        "school": "테스트고2", "grade": "고2", "exam_period": "26-1-기말",
        "vol1": {
            "문장배열": [
                {"header": "교과서1과 본문1", "items": ["(A) One.", "(B) Two."]},
                {"header": "250341~42", "items": ["(A) Long."],
                 "passage": "Given sentence."},
            ],
            "문장삽입": [
                {"header": "교과서1과 본문1", "paras": [
                    {"style": "문장 배열 하단 문제", "text": "아래 주어진 문장…"},
                    {"style": "문장 배열 하단 문제", "text": "<Title of passage>"},
                    {"style": "문장 배열 하단 문제", "text": "(A) First."},
                ]},
            ],
            "중요어휘_왼": ("교과서1과 본문1\n"
                        "The [answer] is here.\n"
                        "\n>>   내용요약   \nA [short] summary.\n"
                        "\n250341\nSecond [passage] text.\n"
                        "\n>>   내용요약   \nSecond [summary].\n"),
        },
        "vol2": {
            "어법수정": ["교과서1과 본문1", "It 1[looked] fine.",
                      "250341~42", "They 2[was] here."],
            "어법_헤더": ["교과서1과 본문1", "250341~42"],
            "서술형영작": [
                {"korean": "가", "choices": "( a / b )"},
                {"korean": "나", "choices": "( c / d )"},
                {"korean": "다", "choices": "( e / f )"},
            ],
            # ⚠ start_idx 가 단조가 아니다 — 광문3에서 영작이 회전 변위한 모양
            "영작_헤더_상세": [{"header": "두번째", "start_idx": 2},
                        {"header": "첫번째", "start_idx": 0}],
            "영작_헤더": ["두번째", "첫번째"],
        },
    }
    for k, v in over.items():
        c[k] = v
    return c


def build():
    warns = []
    return D.from_content(_content(), warns.append), warns


# ── 데이터 변환 ────────────────────────────────────────────────────────
def test_two_volumes_from_one_content():
    d, warns = build()
    assert set(d["vols"]) == {"1", "2"}
    kinds = [s["kind"] for s in d["vols"]["1"]["sections"]]
    assert kinds == ["arrange", "insert", "vocab"]
    assert [s["kind"] for s in d["vols"]["2"]["sections"]] == ["grammar",
                                                              "writing"]
    assert not warns


def test_insert_box_is_the_second_line_not_the_style():
    """스타일이 항목과 같아도 **둘째 줄**이 주어진 문장이다."""
    d, _ = build()
    b = d["vols"]["1"]["sections"][1]["blocks"][0]
    assert b["prompt"].startswith("아래 주어진")
    assert b["given"] == "<Title of passage>"
    assert b["items"] == ["(A) First."]


def test_vocab_splits_and_normalises_long_label():
    d, _ = build()
    voc = d["vols"]["1"]["sections"][2]["blocks"]
    assert [b["header"] for b in voc] == ["교과서1과 본문1", "250341~42"]
    assert all(b["summary"] for b in voc)
    seg = voc[0]["passage"][0]
    assert {"a": "answer"} in seg


def test_grammar_pairs_header_and_body():
    d, _ = build()
    g = d["vols"]["2"]["sections"][0]["blocks"]
    assert [b["header"] for b in g] == ["교과서1과 본문1", "250341~42"]
    assert {"a": "looked"} in g[0]["body"]      # 원고의 번호는 버린다


def test_writing_slices_by_ascending_start_idx():
    """헤더 순서가 뒤섞여도 **경계는 오름차순**이라야 옆 강이 안 섞인다."""
    d, _ = build()
    w = {b["header"]: [p["korean"] for p in b["pairs"]]
         for b in d["vols"]["2"]["sections"][1]["blocks"]}
    assert w["첫번째"] == ["가", "나"]
    assert w["두번째"] == ["다"]


def test_gate_stops_when_only_some_passages_have_a_summary():
    """요약이 아예 없는 판(고3)은 정상이고, **일부만 없는 것**이 결함이다."""
    c = _content()
    c["vol1"]["중요어휘_왼"] = ("교과서1과 본문1\nThe [answer] is here.\n"
                          "\n250341\nSecond [passage] text.\n"
                          "\n>>   내용요약   \nOnly this one has a summary.\n")
    with pytest.raises(SystemExit):
        D.gate(D.from_content(c), c, lambda m: None)


def test_gate_allows_a_book_with_no_summaries_at_all():
    c = _content()
    c["vol1"]["중요어휘_왼"] = ("교과서1과 본문1\nThe [answer] is here.\n"
                          "\n250341\nSecond [passage] text.\n")
    D.gate(D.from_content(c), c, lambda m: None)     # 예외가 없어야 한다


def test_summary_mark_dialects():
    """`>>   내용요약` · `>>내용요약` · `|  내용요약  |` 세 가지가 실재한다."""
    for mark in (">>   내용요약   ", ">>내용요약", "|  내용요약  |", ">> 내용요약"):
        assert D.is_summary_mark(mark)
    assert not D.is_summary_mark("내용요약은 다음과 같이 길게 이어지는 본문 문장이다")


def test_hyphen_artifacts_are_reported_not_fixed():
    c = _content()
    c["vol1"]["문장배열"][0]["items"] = ["(A) It was lim-ited.", "(B) limited"]
    d = D.from_content(c)
    hits = D.hyphen_artifacts(d)
    assert "lim-ited" in hits
    # 내용은 그대로 둔다 — 고치는 자리는 원고이지 조판이 아니다
    assert d["vols"]["1"]["sections"][0]["blocks"][0]["items"][0].endswith(
        "lim-ited.")


# ── 렌더 규칙 ─────────────────────────────────────────────────────────
def test_blank_width_follows_answer_length():
    h = R._blank("owe")
    assert 'width:2.052em' in h and '<span class="bl">o<' in h
    assert R._blank("obligations").count("width:7.524em") == 1
    assert R._blank("") == ""


def test_item_marker_is_bold_only_for_A_style_labels():
    assert '<span class="m">(A)</span>' in R._item("(A) Hello.")
    assert '<span class="m">' not in R._item("Hello (A) world.")


def test_spaces_in_manuscript_are_preserved():
    """원고의 연속 공백은 의미 있는 간격이다 — HTML 은 그냥 두면 줄인다."""
    assert R.esc("a   b") == "a\u00a0\u00a0 b"


def test_grammar_keeps_brackets_bold():
    out = R.inl_grammar(["It ", {"a": "looked"}, " fine."])
    assert '<span class="g">[looked]</span>' in out


def test_fit_is_leading_then_two_slots_never_a_smaller_font():
    """활자 크기는 책 전체에서 하나다 — 넘치면 행간, 더 넘치면 두 칸."""
    assert 'class="blk tall"' in R._open_blk({"span": 2})
    assert '--lead:0.9600' in R._open_blk({"lead": 0.96})
    assert "font-size" not in R._open_blk({"lead": 0.96})

    from core.render_vivlio.series.final import FinalSeries as F
    m = R.DEFAULT_METRICS
    cap = m["slot"] - 0.5
    line = R.LINE_MM["arrange"]
    # 한 줄 넘침 → 행간
    assert "lead" in F._one_fit("arrange", cap + line, cap, m)
    # 세 줄 넘침 → 두 칸
    assert F._one_fit("arrange", cap + 3 * line, cap, m) == {"span": 2}
    # 어휘(면당 한 지문)는 두 칸이 없다 → 흘림
    vcap = m["vocab_avail"] - m["vocab_safety"]
    assert F._one_fit("vocab", vcap + 3 * R.LINE_MM["vocab"], vcap,
                      m) == {"flow": True}


# ── 사분면 계약 ────────────────────────────────────────────────────────
def test_expected_pages_accounts_for_two_slot_blocks():
    sec = {"kind": "arrange", "blocks": [{}] * 6}
    assert V.expected_pages(sec, {}) == [(0, 0)] * 4 + [(1, 1)] * 2
    # 두 칸짜리는 **빈 단**이 필요하다 — 앞 단의 남은 칸은 비고 뒤가 밀린다
    # (`column-fill: auto` 가 실제로 이렇게 흘린다)
    assert V.expected_pages(sec, {1: 2}) == [(0, 0), (0, 0)] + [(1, 1)] * 4
    assert V.expected_pages({"kind": "vocab", "blocks": [{}] * 3}, {}) == \
        [(0, 0), (1, 1), (2, 2)]
    assert V.expected_pages({"kind": "grammar", "blocks": [{}] * 5}, {}) == \
        [(0, 0), (0, 0), (1, 1), (1, 1), (2, 2)]
    # 흘린 지문은 면에 걸친다 — 걸치는 면 전부가 '제자리'다
    assert V.expected_pages({"kind": "grammar", "blocks": [{}] * 3},
                            {1: 3}) == [(0, 0), (0, 1), (2, 2)]


# ── 판면(테마) 계약 ───────────────────────────────────────────────────
def _css():
    with open(CSS, encoding="utf-8") as f:
        return f.read()


def test_page_frame_matches_measured_original():
    """완성본 실측: 안쪽 여백 21/25, 단 83.7mm, 단 사이 3.3mm."""
    css = _css()
    assert "--colw:   83.7mm" in css
    assert "--colgap: 3.3mm" in css
    m = re.search(r"@page :left \{\s*\n\s*margin-left: ([\d.]+)mm; "
                  r"margin-right: ([\d.]+)mm;", css)
    assert m and (float(m.group(1)), float(m.group(2))) == (21.0, 24.3)
    m = re.search(r"@page :right \{\s*\n\s*margin-left: ([\d.]+)mm; "
                  r"margin-right: ([\d.]+)mm;", css)
    assert m and (float(m.group(1)), float(m.group(2))) == (25.0, 20.3)
    # 두 단 + 사이 = 판면 폭
    assert abs((83.7 * 2 + 3.3) - (216 - 21 - 24.3)) < 0.01


def test_grid_has_no_fixed_height():
    """⚠ `.grid` 에 height 를 주면 면으로 안 쪼개지고 옆으로 흘러 나간다."""
    css = _css()
    grid = re.search(r"\.grid \{[^}]*\}", css).group(0)
    assert "height" not in grid
    assert "column-fill: auto" in grid


def test_blocks_are_not_clipped():
    """넘치는 내용을 자르면 유실이 조용해진다 — overflow:hidden 금지."""
    css = _css()
    blk = re.search(r"\n\.blk \{ height:[^}]*\}", css).group(0)
    assert "overflow" not in blk
    assert "height: var(--slot)" in blk


def test_tracking_is_the_measured_value():
    assert "letter-spacing: -0.04em" in _css()
