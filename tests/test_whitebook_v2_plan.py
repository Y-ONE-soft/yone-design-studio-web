"""화이트북 v2 플랜 빌더 오프라인 테스트 — 코퍼스 골든 기반.

v1 파리티 앵커: e41f1c70 케이스의 v1 실행 로그(2026-05-13 실물)와 대조 —
Day11 정답 스토리 136단락, A 30/B 32/C 5세트/E 5 등.
"""
import json
import os
import re

import pytest

from engines.whitebook_v2.plan import (
    content_to_plan, unit_paras, _ul_runs, _split_ones)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _golden(case):
    p = os.path.join(TESTS_DIR, "corpus", "whitebook", case,
                     "golden", "content.json")
    return json.load(open(p, encoding="utf-8"))


@pytest.fixture(scope="module")
def plan_full():
    return content_to_plan(_golden("e41f1c70"), issue_num="1")


def _flow(plan, area):
    return next(fl for fl in plan["flows"] if fl["area"] == area)


def test_flow_layout(plan_full):
    areas = [fl["area"] for fl in plan_full["flows"]]
    assert areas == ["A", "B", "C", "D_box", "D_item", "E",
                     "ans", "prac_main", "prac_ans"]
    for area in ("A", "B", "C", "D_box", "D_item", "E", "ans"):
        assert len(_flow(plan_full, area)["units"]) == 10, area
    for area in ("prac_main", "prac_ans"):
        assert len(_flow(plan_full, area)["units"]) == 3, area
    assert plan_full["week_text"] == "1주 차"
    assert plan_full["ul_style"] == "밑줄"


def test_day1_unit_counts_v1_log_parity(plan_full):
    """v1 실행 로그(e41f1c70) 실측과 유닛 단락 수 대조."""
    # A: 30단어
    assert len(unit_paras(_flow(plan_full, "A")["units"][0])) == 30
    # B: 32문장 (kor 포함 시 2단락씩 — v1 로그는 '32문장')
    b0 = unit_paras(_flow(plan_full, "B")["units"][0])
    assert sum(1 for p in b0 if p["s"] == "C 예문") == 32
    # C: 5세트 (보기줄 5 + defs)
    c0 = unit_paras(_flow(plan_full, "C")["units"][0])
    assert sum(1 for p in c0 if p["s"] == "C 단어 박스") == 5
    # E: 5문장
    assert len(unit_paras(_flow(plan_full, "E")["units"][0])) == 5
    # 정답: 136단락 (v1 로그 '정답(Day11): 136단락')
    assert len(unit_paras(_flow(plan_full, "ans")["units"][0])) == 136


def test_answer_unit_ops(plan_full):
    unit = _flow(plan_full, "ans")["units"][0]
    paras = unit["paras"]
    ops = unit["ops"]
    # 헤더 5개: A(' 정답', 공백1) + B/C/D/E('  정답', 공백2)
    hdrs = [i for i, p in enumerate(paras) if p["s"] == "정답 > 정답_"]
    assert len(hdrs) == 5
    assert paras[hdrs[0]]["t"] == " 정답"
    for h in hdrs[1:]:
        assert paras[h]["t"] == "  정답"
    # 아이콘: 섹션 0~4가 헤더 단락에 1:1
    assert ops["icons"] == [{"p": h, "sec": s} for s, h in enumerate(hdrs)]
    assert ops["ans_frame_fix"] is True
    assert ops["ans_char"] == {"style": "정답", "paras": hdrs}
    # 번호 재시작: 섹션 1+ 첫 정답 + '[문제 N]' 다음 정답 (v1 postProcess)
    restart = ops["numbering_restart"]
    assert restart == sorted(set(restart))
    for i in restart:
        assert paras[i]["s"] == "정답 > 정답지 번호"
    # B 섹션 첫 항목(헤더 바로 다음)은 재시작 대상
    assert hdrs[1] + 1 in restart
    # '[문제 N]' 해설 다음 정답 항목도 재시작
    sol = next(i for i, p in enumerate(paras)
               if p["s"] == "정답 및 해설 > 해설_" and "[문제" in p["t"])
    assert sol + 1 in restart


def test_d_box_ones_split(plan_full):
    """v1 applyOnesGrep 등가 — ① 앞 공백이 단락 경계로 바뀌었는지."""
    golden = _golden("e41f1c70")
    for di, unit in enumerate(_flow(plan_full, "D_box")["units"]):
        paras = unit_paras(unit)
        assert paras, f"day {di} D_box 비어 있음"
        joined = "\r".join(p["t"] for p in paras)
        # 분할 후에도 원문자 앞 공백열이 남아 있으면 GREP 미이식
        assert not re.search("[ ]+[①-⑳㉑-㉟㊱-㊿]", joined)
        # 〈보기〉 헤더 제거 (v1 스킵)
        assert "〈보기〉" not in joined
        # 내용 보존: 원본 bogis_raw 단어셋 == 플랜 단어셋
        src = " ".join(golden["days"][di]["content"]["D"]["bogis_raw"])
        assert set(_RE_WORD.findall(src)) == set(_RE_WORD.findall(joined))
        assert unit["ops"]["expand_move"] == ["D 단어 new", "발문", "E 전치사"]


def test_underline_runs(plan_full):
    """<u>..</u> 마커 → runs 변환 (마커 제거 + 위치 보존)."""
    found_ul = 0
    for area in ("prac_main", "prac_ans"):
        for unit in _flow(plan_full, area)["units"]:
            for p in unit_paras(unit):
                assert "<u>" not in p["t"] and "</u>" not in p["t"]
                if p["runs"]:
                    assert "".join(r["t"] for r in p["runs"]) == p["t"]
                    if any(r["ul"] for r in p["runs"]):
                        found_ul += 1
    assert found_ul > 0  # 골든에 밑줄 마커 실재 (예: '않은')


def test_ul_runs_edge_cases():
    assert _ul_runs("plain") == ("plain", [])
    t, runs = _ul_runs("ab <u>cd</u> ef")
    assert t == "ab cd ef"
    assert runs == [{"t": "ab ", "ul": False}, {"t": "cd", "ul": True},
                    {"t": " ef", "ul": False}]
    t2, runs2 = _ul_runs("<u>x</u><u>y</u>")
    assert t2 == "xy" and all(r["ul"] for r in runs2)


def test_split_ones():
    assert _split_ones("① a  ② b ③ c") == ["① a", "② b", "③ c"]
    assert _split_ones("no circles here") == ["no circles here"]
    assert _split_ones("㉑ x  ㊱ y") == ["㉑ x", "㊱ y"]


def test_content_conservation(plan_full):
    """골든 content의 실질 영단어가 플랜 어딘가에 전부 존재 (검수 게이트 사전판)."""
    golden = _golden("e41f1c70")
    plan_words = set()
    for fl in plan_full["flows"]:
        for unit in fl["units"]:
            for p in unit_paras(unit):
                plan_words.update(
                    w.lower() for w in _RE_WORD.findall(p["t"]))

    src_words = set()

    def _collect(obj):
        if isinstance(obj, str):
            src_words.update(w.lower() for w in _RE_WORD.findall(
                re.sub(r"</?u>", "", obj)))
        elif isinstance(obj, list):
            for v in obj:
                _collect(v)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect(v)

    _collect(golden)
    missing = src_words - plan_words
    assert not missing, f"플랜 누락 단어: {sorted(missing)[:10]}"


def test_skip_units_when_no_practice():
    """구버전 케이스(연습문제 없음) — prac 유닛 전부 skip, Day 유닛은 정상."""
    plan = content_to_plan(_golden("3b3ddc5a"), issue_num="")
    assert plan["week_text"] is None
    for area in ("prac_main", "prac_ans"):
        assert all(u.get("skip") for u in _flow(plan, area)["units"])
    assert all(not u.get("skip") for u in _flow(plan, "A")["units"])
    # 정답 유닛도 전부 채워짐 (main_ans 슬롯 존재)
    assert all(not u.get("skip") for u in _flow(plan, "ans")["units"])
