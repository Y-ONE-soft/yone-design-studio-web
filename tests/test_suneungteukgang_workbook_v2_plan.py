"""수능특강 워크북 v2 플랜 가드 — 2단계(분석/문제) 분리 + content-only 코퍼스."""
import json
import os
import re

from engines.suneungteukgang_workbook_v2.engine import _STAGE_MAPS
from engines.workbook_v2.plan import (ensure_step3_kinds, steps_to_plan,
                                      unit_paras)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")

# 케이스별 기대 유닛 수 (최초 실행 스냅샷 고정)
_EXPECTED = {
    "65cf0265": {
        "analysis": {"step1_a1": 3, "step1_a2": 3, "step1_c1": 6,
                     "step1_c2": 3, "step2_a1": 2, "step2_a1_btm": 3,
                     "step2_c2": 1},
        "problem": {"step3": 1},
    },
    "4fa1510e": {
        "analysis": {"step1_a1": 19, "step1_a2": 19, "step1_c1": 38,
                     "step1_c2": 19, "step2_a1": 19, "step2_a1_btm": 19,
                     "step2_c2": 1},
        "problem": {"step3": 1},
    },
}


def _content(case):
    path = os.path.join(TESTS_DIR, "corpus", "suneungteukgang_workbook",
                        case, "golden", "content.json")
    content = json.load(open(path, encoding="utf-8"))
    assert content["workbook_type"] == "EBS"
    ensure_step3_kinds(content["steps"].get("step3"))
    return content


def _stage_plan(steps, stage):
    smap = _STAGE_MAPS[stage]
    sub = {k: v for k, v in steps.items() if k in smap}
    return steps_to_plan(sub, workbook_type="EBS", step_map=smap)


def test_stage_maps_match_v1_literals():
    """스테이지 매핑 = v1 엔진 클래스 상수와 정확히 일치 (이식 진실 앵커)."""
    from engines.suneungteukgang_workbook.engine import (
        SuneungteukgangWorkbookEngine as V1)
    assert _STAGE_MAPS["analysis"] == V1._ANALYSIS_STEP_STORY_MAP
    assert _STAGE_MAPS["problem"] == V1._PROBLEM_STEP_STORY_MAP
    assert "_doc" not in _STAGE_MAPS


def test_stage_units_snapshot():
    for case, stages in _EXPECTED.items():
        steps = _content(case)["steps"]
        for stage, expected in stages.items():
            plan = _stage_plan(steps, stage)
            assert plan["unsupported"] == [], (case, stage)
            got = {f["step"]: len(f["units"]) for f in plan["flows"]}
            assert got == expected, (case, stage, got)


def test_stage_separation_covers_all_steps():
    """분석(7스텝) + 문제(step3) 합집합 = 원고 스텝 전부 (leftover 없음)."""
    placeable = set(_STAGE_MAPS["analysis"]) | set(_STAGE_MAPS["problem"])
    for case in _EXPECTED:
        steps = _content(case)["steps"]
        assert set(steps) <= placeable, (case, set(steps) - placeable)


def test_c1_ebs_next_frame():
    """수능특강도 EBS 유형 — C1 헤더는 NEXT_FRAME (page_break 유닛 없음)."""
    for case in _EXPECTED:
        plan = _stage_plan(_content(case)["steps"], "analysis")
        c1 = next(f for f in plan["flows"] if f["step"] == "step1_c1")
        assert not any(isinstance(u, dict) and u.get("page_break")
                       for u in c1["units"]), case


def test_problem_stage_step3_master_d():
    plan = _stage_plan(_content("65cf0265")["steps"], "problem")
    s3 = plan["flows"][0]
    assert s3["step"] == "step3"
    assert s3["target"] == {"master": "D"}
    n_paras = sum(len(unit_paras(u)) for u in s3["units"])
    assert n_paras > 100


def test_content_conservation():
    """플랜 단어 보존 — 의도적 삭제 룰 제외 90%+ (스테이지 합산)."""
    from engines.workbook_v2.plan import _has_circled
    for case in _EXPECTED:
        content = _content(case)
        got = set()
        for stage in ("analysis", "problem"):
            plan = _stage_plan(content["steps"], stage)
            for flow in plan["flows"]:
                for u in flow["units"]:
                    for p in unit_paras(u):
                        got.update(w.lower()
                                   for w in _RE_WORD.findall(p["t"]))
        src = set()
        for key, sdata in content["steps"].items():
            if key == "step3":
                texts = [p.get("text") or ""
                         for grp in ("normal", "short")
                         for it in sdata.get(grp) or []
                         for p in it["paragraphs"]]
            elif key == "step2_a1_btm":
                texts = [p.get("text") or "" for p in sdata["paragraphs"]
                         if _has_circled(p.get("text") or "")]
            else:
                texts = [p.get("text") or "" for p in sdata["paragraphs"]]
            for t in texts:
                src.update(w.lower() for w in _RE_WORD.findall(t))
        kept = len(src & got) / len(src)
        assert kept >= 0.9, (case, kept, sorted(src - got)[:10])
