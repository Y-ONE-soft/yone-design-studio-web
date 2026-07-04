"""세서특필 v2 플랜/엔진 오프라인 테스트 — 코퍼스 골든 기반 (InDesign 불필요).

앵커 수치는 v1 실물 출력 dump 대조로 확정 (2026-07-04):
  광문2 코퍼스(71f664f1) ↔ v1 실제 출력(광문2_세서특필02_내지.indd, job 동일):
    part1 432(구파서)→492(현행: 답안지 60 추가), part2 656단락+브레이크 32
    (v1은 FRAME_BREAK 문자 삽입으로 688단락 — v2는 텍스트 무변형 유닛 33개),
    answers 330단락. 스타일 코드↔실물 적용 스타일 1:1 확증.
"""
import json
import os

import pytest

from engines.seseospecial_v2.plan import (content_to_plan, flow_paras,
                                          unit_paras, _runs_from_ul_ranges)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus", "seseospecial")


def _golden(case):
    return json.load(open(os.path.join(CORPUS, case, "golden", "content.json"),
                          encoding="utf-8"))


def _flow(plan, area):
    for fl in plan["flows"]:
        if fl["area"] == area:
            return fl
    return None


# ── 유닛/단락 수 앵커 (v1 실물 dump 대조 수치) ──────────────────────────────

def test_plan_counts_gwangmun2():
    plan = content_to_plan(_golden("71f664f1"))
    assert plan["format"] == "ss-flows-v1"
    assert plan["part1_page"] == 6
    p1, p2, ans = (_flow(plan, a) for a in ("part1", "part2", "answers"))
    assert len(flow_paras(p1)) == 492          # 432(v1 job) + 답안지 60(현행 파서)
    assert len(p1["units"]) == 1 and not p1["break_per_unit"]
    assert len(flow_paras(p2)) == 656          # intro 76 + main 580
    assert len(p2["units"]) == 33              # v1 브레이크 32개 + 1
    assert p2["break_per_unit"]
    assert len(flow_paras(ans)) == 330
    assert len(ans["units"]) == 1 and not ans["break_per_unit"]


def test_plan_counts_gwangmun1():
    plan = content_to_plan(_golden("300e567a"))
    p2 = _flow(plan, "part2")
    assert len(flow_paras(p2)) == 1229         # intro 162 + main 1067
    assert len(p2["units"]) == 37              # 출처 33 + 소제목 3 브레이크 + 1
    assert len(flow_paras(_flow(plan, "part1"))) == 612
    assert len(flow_paras(_flow(plan, "answers"))) == 612


# ── 유닛 분할 = v1 브레이크 의미론 (출처/소제목 앞 프레임 분리) ─────────────

def test_part2_units_start_with_break_styles():
    smap_break = {"A ver > 실전문제 > 출처", "A ver > 소제목"}
    for case in ("71f664f1", "300e567a"):
        p2 = _flow(content_to_plan(_golden(case)), "part2")
        for u in p2["units"][1:]:
            first = unit_paras(u)[0]
            assert first["s"] in smap_break, \
                f"{case}: 유닛 시작이 브레이크 스타일 아님: {first['s']!r}"


# ── 내용 보존 (골든 → 플랜 순서 그대로 1:1) ────────────────────────────────

@pytest.mark.parametrize("case", ["1a438aac", "300e567a", "41198133",
                                  "71f664f1", "a517de1f"])
def test_plan_preserves_all_text_in_order(case):
    golden = _golden(case)
    plan = content_to_plan(golden)
    want_p1 = [p["text"] for p in golden["part1"]["paragraphs"]]
    got_p1 = [p["t"] for p in flow_paras(_flow(plan, "part1"))]
    assert got_p1 == want_p1

    want_p2 = [e["text"] for e in
               (golden["part2"].get("intro") or []) + golden["part2"]["main"]]
    got_p2 = [p["t"] for p in flow_paras(_flow(plan, "part2"))]
    assert got_p2 == want_p2

    want_ans = [a["text"] for a in golden["part2"]["answers"]]
    got_ans = [p["t"] for p in flow_paras(_flow(plan, "answers"))]
    assert got_ans == want_ans


# ── 스타일이 실물 템플릿 인벤토리에 전부 존재 (광문2/광문3) ─────────────────

@pytest.mark.parametrize("fixture", ["template_spec_seseospecial_광문2.json",
                                     "template_spec_seseospecial_광문3.json"])
def test_plan_styles_exist_in_template_inventory(fixture):
    inv = set(json.load(open(os.path.join(TESTS_DIR, "fixtures", fixture),
                             encoding="utf-8"))["paragraph_styles"])
    missing = set()
    for case in ("300e567a", "71f664f1"):
        for fl in content_to_plan(_golden(case))["flows"]:
            for p in flow_paras(fl):
                if p["s"] and p["s"] not in inv:
                    missing.add(p["s"])
    assert not missing, f"템플릿에 없는 스타일: {sorted(missing)}"


# ── 정답 없음 → answers 플로우 생략 (v1: 기존 정답 스토리 보존) ─────────────

def test_no_answers_flow_when_empty():
    golden = _golden("71f664f1")
    golden["part2"]["answers"] = []
    plan = content_to_plan(golden)
    assert _flow(plan, "answers") is None
    assert [fl["area"] for fl in plan["flows"]] == ["part1", "part2"]


# ── 구형식 밑줄 ul_ranges → runs 변환 (v1 밑줄 이식) ────────────────────────

def test_ul_ranges_to_runs():
    runs = _runs_from_ul_ranges("abcdefghij", "2:5,7:9")
    assert runs == [
        {"t": "ab", "ul": False},
        {"t": "cde", "ul": True},
        {"t": "fg", "ul": False},
        {"t": "hi", "ul": True},
        {"t": "j", "ul": False},
    ]
    assert "".join(r["t"] for r in runs) == "abcdefghij"
    assert _runs_from_ul_ranges("abc", None) == []
    assert _runs_from_ul_ranges("abc", "") == []
    assert _runs_from_ul_ranges("abc", "잘못:된") == []


# ── 엔진 parse = v1 완전 위임 (골든 파리티) ─────────────────────────────────

def test_engine_parse_delegates_to_v1(tmp_path):
    import _replay
    from engines.seseospecial_v2.engine import SeseoSpecialV2Engine
    case_dir = os.path.join(CORPUS, "71f664f1")
    job_dir = str(tmp_path / "job")
    produced = _replay.replay(SeseoSpecialV2Engine(), case_dir, job_dir)
    golden = _replay.canonicalize(_golden("71f664f1"), [])
    produced = _replay.canonicalize(produced, [job_dir])
    assert _replay.first_diff(produced, golden) is None
