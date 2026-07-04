"""교과서 워크북 v2 플랜 가드 — content-only 코퍼스 (GDrive parse 불가).

코퍼스: tests/corpus/textbook_workbook/<job>/golden/content.json
(v1 파서 실물 출력 — 구버전이라 step3 kind 미주석 → ensure_step3_kinds 경유).
내지 = 모의고사와 동일 [원본]워크북_C → 인벤토리 가드도 workbookC 픽스처.
"""
import json
import os
import re

from engines.workbook_v2.plan import (STEP_MAP, ensure_step3_kinds,
                                      steps_to_plan, unit_paras)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")

# 케이스별 기대 유닛 수 (지문 수 기반 — 최초 실행 스냅샷 고정)
_EXPECTED_UNITS = {
    "80dd3fa2": {"step1_a1": 5, "step1_a1_2": 5, "step1_a2": 5,
                 "step1_b1": 10, "step1_b2": 5, "step1_c1": 10,
                 "step1_c2": 5, "step2_a1": 5, "step2_a1_btm": 5,
                 "step2_b1": 5, "step2_c1": 5, "step2_c2": 5, "step3": 1},
    "20a3838b": {"step1_a1": 2, "step1_a1_2": 2, "step1_a2": 2,
                 "step1_b1": 4, "step1_b2": 2, "step1_c1": 4,
                 "step1_c2": 2, "step2_a1": 2, "step2_a1_btm": 0,
                 "step2_b1": 2, "step2_c1": 2, "step2_c2": 2, "step3": 1},
}


def _inventory():
    return set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_workbookC.json"),
        encoding="utf-8"))["paragraph_styles"])


def _plan(case):
    path = os.path.join(TESTS_DIR, "corpus", "textbook_workbook", case,
                        "golden", "content.json")
    content = json.load(open(path, encoding="utf-8"))
    assert content["workbook_type"] == "교과서"
    ensure_step3_kinds(content["steps"].get("step3"))
    return steps_to_plan(content["steps"], workbook_type="교과서")


def test_units_styles_and_targets():
    """13스텝 전부 지원 + 유닛 수 스냅샷 + 스타일 실물 인벤토리 가드."""
    inv = _inventory()
    for case, expected in _EXPECTED_UNITS.items():
        plan = _plan(case)
        assert plan["unsupported"] == [], case
        assert len(plan["flows"]) == len(expected), case
        for flow in plan["flows"]:
            assert len(flow["units"]) == expected[flow["step"]], \
                (case, flow["step"])
            # 타깃 = 모의고사 기본 매핑 (v1 textbook은 stepStoryMap 미지정
            # = run.jsx 기본값 사용과 동일)
            assert flow["target"] == STEP_MAP[flow["step"]], \
                (case, flow["step"])
            styles = {p["s"] for u in flow["units"] for p in unit_paras(u)}
            assert None not in styles, (case, flow["step"])
            assert {s for s in styles if s != "$BASIC"} <= inv, \
                (case, flow["step"], styles - inv)


def test_step1_c1_textbook_branch_page_breaks():
    """C1 교과서 분기 — 비EBS이므로 헤더(2번째+) 유닛은 NEXT_PAGE."""
    plan = _plan("80dd3fa2")
    c1 = next(f for f in plan["flows"] if f["step"] == "step1_c1")
    pb = sum(1 for u in c1["units"]
             if isinstance(u, dict) and u.get("page_break"))
    assert pb == 4      # 5지문 — 첫 헤더 제외 4개


def test_step3_kind_reannotation():
    """구버전 content(kind 없음) → ensure_step3_kinds가 재주석해
    step3 유닛이 비지 않고 스타일이 UNKNOWN 일변도가 아니다."""
    path = os.path.join(TESTS_DIR, "corpus", "textbook_workbook",
                        "80dd3fa2", "golden", "content.json")
    content = json.load(open(path, encoding="utf-8"))
    s3 = content["steps"]["step3"]
    assert not any(p.get("kind")
                   for it in s3["normal"] for p in it["paragraphs"])
    ensure_step3_kinds(s3)
    kinds = {p.get("kind") for it in s3["normal"] for p in it["paragraphs"]}
    assert {"Q", "P", "C"} <= kinds
    plan = steps_to_plan(content["steps"], workbook_type="교과서")
    s3_flow = next(f for f in plan["flows"] if f["step"] == "step3")
    n_paras = sum(len(unit_paras(u)) for u in s3_flow["units"])
    assert n_paras > 700    # 825단락 중 BLANK/GH/A 제외 전량 배치


def test_content_conservation():
    """플랜 단어 ⊇ 원고 단어 (의도적 삭제 룰 제외) — 스텝 단위 근사 가드:
    각 플로우의 단어 집합이 원본 스텝 단락 대비 90%+ 보존."""
    for case in _EXPECTED_UNITS:
        path = os.path.join(TESTS_DIR, "corpus", "textbook_workbook", case,
                            "golden", "content.json")
        content = json.load(open(path, encoding="utf-8"))
        ensure_step3_kinds(content["steps"].get("step3"))
        plan = steps_to_plan(content["steps"], workbook_type="교과서")
        for flow in plan["flows"]:
            if flow["step"] == "step3":
                src_texts = [p.get("text") or ""
                             for it in content["steps"]["step3"]["normal"]
                             for p in it["paragraphs"]]
            elif flow["step"] == "step2_a1_btm":
                # v1 삭제 룰: 원문자(①~⑳) 없는 단락 전부 삭제 —
                # 원고가 원문자 미사용(20a3838b 1[what/that]식)이면 전량
                # 삭제가 v1 파리티다. 원문자 단락만 보존 대상.
                from engines.workbook_v2.plan import _has_circled
                src_texts = [p.get("text") or "" for p in
                             content["steps"][flow["step"]]["paragraphs"]
                             if _has_circled(p.get("text") or "")]
            else:
                src_texts = [p.get("text") or "" for p in
                             content["steps"][flow["step"]]["paragraphs"]]
            src = set()
            for t in src_texts:
                src.update(w.lower() for w in _RE_WORD.findall(t))
            got = set()
            for u in flow["units"]:
                for p in unit_paras(u):
                    got.update(w.lower() for w in _RE_WORD.findall(p["t"]))
            if not src:
                continue
            kept = len(src & got) / len(src)
            assert kept >= 0.9, (case, flow["step"], kept,
                                 sorted(src - got)[:10])
