"""리딩파워(EBS) 워크북 v2 플랜 가드 — content-only 코퍼스 (GDrive parse 불가).

코퍼스: tests/corpus/ebs_workbook/<job>/golden/content.json (v1 파서 실물 출력).
EBS 분기 3종이 핵심: C1 헤더 NEXT_FRAME(NEXT_PAGE 아님)·화살표 빈 단락 재사용,
C2 bracket 프레임브레이크 생략 + 빈 줄 2개, EBS 전용 step_map(step3 마스터 O).
스타일 인벤토리 가드는 실물 스펙(template_spec_ebs_readingpower.json) 추출 후
test_style_resolver 확장으로 커버 (여기서는 스타일 존재/비None만).
"""
import json
import os
import re

from engines.ebs_workbook_v2.engine import _STEP_MAP
from engines.workbook_v2.plan import (_c2_is_bracket, ensure_step3_kinds,
                                      steps_to_plan, unit_paras)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")

# 케이스별 기대 유닛 수 (지문 6개 단원 — 최초 실행 스냅샷 고정)
_EXPECTED_UNITS = {
    "4ed24266": {"step1_a1": 6, "step1_a2": 6, "step1_c1": 12,
                 "step1_c2": 6, "step2_a1": 6, "step2_a1_btm": 6,
                 "step2_c2": 1, "step3": 1},
    "fbb8dbc5": {"step1_a1": 6, "step1_a2": 6, "step1_c1": 12,
                 "step1_c2": 6, "step2_a1": 6, "step2_a1_btm": 6,
                 "step2_c2": 1, "step3": 1},
}


def _content(case):
    path = os.path.join(TESTS_DIR, "corpus", "ebs_workbook", case,
                        "golden", "content.json")
    content = json.load(open(path, encoding="utf-8"))
    assert content["workbook_type"] == "EBS"
    ensure_step3_kinds(content["steps"].get("step3"))
    return content


def _plan(case):
    return steps_to_plan(_content(case)["steps"], workbook_type="EBS",
                         step_map=_STEP_MAP)


def test_units_targets_and_styles():
    """8스텝 전부 지원 + 유닛 수 스냅샷 + EBS step_map 타깃."""
    for case, expected in _EXPECTED_UNITS.items():
        plan = _plan(case)
        assert plan["unsupported"] == [], case
        assert len(plan["flows"]) == len(expected), case
        for flow in plan["flows"]:
            assert len(flow["units"]) == expected[flow["step"]], \
                (case, flow["step"])
            assert flow["target"] == _STEP_MAP[flow["step"]], \
                (case, flow["step"])
            styles = {p["s"] for u in flow["units"] for p in unit_paras(u)}
            assert None not in styles, (case, flow["step"])


def test_step_map_matches_v1_settings():
    """EBS step_map = v1 prepare_jsx의 ebs_step_story_map 리터럴 + step3.

    W12: step2_a1/btm에 pos(top/bottom) 기하 힌트 추가 — 4ed24266 실기에서
    rank 선택이 상/하단을 뒤바꾸는 상하반전 확인(a1 top 164 ≥ btm 31),
    supp W11 결함②의 확산 조건(실기 확인) 충족. v1 마커/페이지는 그대로.
    W24 r14: STEP1 4스텝에 master_pair(A/B — 내지 46p 실측: 우측 시작
    p7/p13 = B-마스터) 계약 등재. STEP2는 C-마스터 좌/우 공용이라 미등재
    (section_masters op는 실기 검증 불가로 보류 — G26 warning 감시만)."""
    v1 = {
        "step1_a1":     {"page": "4",  "marker": "어휘 선택"},
        "step1_a2":     {"page": "7",  "marker": "본문 O/X"},
        "step1_c1":     {"page": "10", "marker": "문장 배열"},
        "step1_c2":     {"page": "13", "marker": "빈칸 어휘"},
        "step2_a1":     {"page": "22", "marker": "어법 수정"},
        "step2_a1_btm": {"page": "22", "marker": "어법 수정", "rank": 2},
        "step2_c2":     {"page": "28", "marker": "영작 배열"},
    }
    pos = {"step2_a1": "top", "step2_a1_btm": "bottom"}
    pair = {"left": "A-마스터", "right": "B-마스터"}
    for k, v in v1.items():
        expected = dict(v, **({"pos": pos[k]} if k in pos else {}))
        if k.startswith("step1_"):
            expected["master_pair"] = pair
        assert _STEP_MAP[k] == expected, k
    # step3: v1 settings 미지정 = run.jsx 기본 마스터 O
    assert _STEP_MAP["step3"] == {"master": "O"}
    assert set(_STEP_MAP) == set(v1) | {"step3"}


def test_c1_ebs_next_frame_no_page_break():
    """EBS C1: 헤더(2번째+)도 NEXT_FRAME — page_break 유닛이 없어야 한다
    (v1 run.jsx 1230 — 리딩파워는 페이지당 2프레임)."""
    for case in _EXPECTED_UNITS:
        c1 = next(f for f in _plan(case)["flows"] if f["step"] == "step1_c1")
        assert not any(isinstance(u, dict) and u.get("page_break")
                       for u in c1["units"]), case


def test_c2_ebs_single_flow_with_blank_gaps():
    """EBS C2: bracket 프레임브레이크 생략(유닛 1개) + bracket(2번째+) 앞
    빈 줄 정확히 2개 + 보기 블록 끝 영작 답지 아이콘 (v1 2125/6·7단계)."""
    for case in _EXPECTED_UNITS:
        c2 = next(f for f in _plan(case)["flows"] if f["step"] == "step2_c2")
        assert len(c2["units"]) == 1, case
        unit = unit_paras(c2["units"][0])
        brackets = [i for i, p in enumerate(unit) if _c2_is_bracket(p["t"])]
        assert len(brackets) >= 2, case
        for i in brackets[1:]:
            assert unit[i - 1]["t"] == "" and unit[i - 2]["t"] == "", \
                (case, i)
        icons = [p for p in unit if p.get("icon")]
        assert len(icons) == len(brackets), case
        assert all(p["icon"]["label"] == "STEP2 영작 답지" for p in icons)


def test_c2_mockexam_path_unchanged():
    """회귀 가드 — 같은 원고를 모의고사 유형으로 빌드하면 기존 동작
    (bracket 유닛 분할)이 그대로다."""
    content = _content("4ed24266")
    plan = steps_to_plan(content["steps"], workbook_type="모의고사",
                         step_map=_STEP_MAP)
    c2 = next(f for f in plan["flows"] if f["step"] == "step2_c2")
    assert len(c2["units"]) == 6      # 지문 6개 = 유닛 6개


def test_step_map_filters_unknown_steps():
    """step_map 지정 시 매핑에 없는 스텝은 unsupported로 보고 (배치 불가)."""
    content = _content("4ed24266")
    partial = {"step1_a1": _STEP_MAP["step1_a1"]}
    plan = steps_to_plan(content["steps"], workbook_type="EBS",
                         step_map=partial)
    assert [f["step"] for f in plan["flows"]] == ["step1_a1"]
    assert set(plan["unsupported"]) == set(content["steps"]) - {"step1_a1"}


def test_content_conservation():
    """플랜 단어 보존 — 의도적 삭제 룰 제외 90%+ (스텝 단위 근사 가드)."""
    from engines.workbook_v2.plan import _has_circled
    for case in _EXPECTED_UNITS:
        content = _content(case)
        plan = steps_to_plan(content["steps"], workbook_type="EBS",
                             step_map=_STEP_MAP)
        for flow in plan["flows"]:
            if flow["step"] == "step3":
                src_texts = [p.get("text") or ""
                             for grp in ("normal", "short")
                             for it in content["steps"]["step3"].get(grp) or []
                             for p in it["paragraphs"]]
            elif flow["step"] == "step2_a1_btm":
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
