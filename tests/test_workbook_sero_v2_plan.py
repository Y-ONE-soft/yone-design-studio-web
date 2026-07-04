"""워크북 세로 v2 사이클 플랜 빌더 가드.

코퍼스: tests/corpus/workbook_sero/
  - e79f8af9: Step1~3 전체 (7사이클 — 마더텅 15강)
  - b74f395f / b9e0f1a4: Step3만 (7사이클 — STEP1/2는 clear 슬롯)
스타일 인벤토리: tests/fixtures/template_spec_workbook_sero.json (실물 추출).
"""
import json
import os
import re

from engines.workbook_sero_v2.plan import content_to_plan
from engines.workbook_v2.plan import unit_paras

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")
_BASIC = "$BASIC"

_FULL_CASE = "e79f8af9"
_S3_ONLY_CASES = ("b74f395f", "b9e0f1a4")

# 슬롯 → 스텝 고정 매핑 (v1 seroProcessCycle의 페이지 구조)
_EXPECTED_SLOT_STEPS = {
    "p0_top": "step1_a1_2", "p0_bot": "step1_a1", "p1_main": "step1_a2",
    "p2_main": "step1_b1", "p3_main": "step1_b2", "p4_main": "step1_c1",
    "p5_main": "step1_c2", "p6_sel": "step2_a1", "p6_btm": "step2_a1_btm",
    "p7_main": "step2_b1", "p8_main": "step2_c1", "p9_main": "step2_c2",
    "step3": "step3",
}


def _inventory():
    return set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_workbook_sero.json"),
        encoding="utf-8"))["paragraph_styles"])


def _load(case):
    path = os.path.join(TESTS_DIR, "corpus", "workbook_sero", case,
                        "golden", "content.json")
    return json.load(open(path, encoding="utf-8"))


def _words(texts):
    out = set()
    for t in texts:
        out.update(w.lower() for w in _RE_WORD.findall(t))
    return out


def _slot(cyc, name):
    return next(s for s in cyc["slots"] if s["slot"] == name)


def _slot_paras(slot):
    return [p for u in slot["units"] for p in unit_paras(u)]


def test_full_case_slots_and_styles():
    """전체 원고: 13슬롯 전부 채움, 스타일은 실물 인벤토리(+$BASIC)만."""
    inv = _inventory() | {_BASIC}
    plan = content_to_plan(_load(_FULL_CASE))
    assert plan["format"] == "wb-sero-cycles-v1"
    assert plan["cycle_count"] == 7
    assert plan["unsupported"] == []
    for cyc in plan["cycles"]:
        slots = {s["slot"]: s for s in cyc["slots"]}
        assert set(slots) == set(_EXPECTED_SLOT_STEPS), cyc["q_num"]
        for name, s in slots.items():
            assert s["step"] == _EXPECTED_SLOT_STEPS[name]
            assert not s.get("clear"), (cyc["q_num"], name)
            styles = {p["s"] for p in _slot_paras(s)}
            assert None not in styles, (cyc["q_num"], name)
            assert styles <= inv, (cyc["q_num"], name, styles - inv)
        assert cyc["qnum_slots"] == ["p5_num", "p7_num", "p8_num"]


def test_step3_only_cases_clear_slots():
    """Step3만 있는 원고: STEP1/2 슬롯은 전부 clear (잔존 데이터 비움)."""
    for case in _S3_ONLY_CASES:
        plan = content_to_plan(_load(case))
        assert plan["cycle_count"] == 7
        for cyc in plan["cycles"]:
            slots = {s["slot"]: s for s in cyc["slots"]}
            for name, step in _EXPECTED_SLOT_STEPS.items():
                if name == "step3":
                    assert not slots[name].get("clear")
                    assert slots[name]["units"]
                else:
                    assert slots[name].get("clear") is True, (case, name)


def test_markers_prepended():
    """v1 seroAugment 마커 — 슬롯별 [N]/[code]/{N}/{code} 선두 단락."""
    plan = content_to_plan(_load(_FULL_CASE))
    cyc = plan["cycles"][0]
    qn, code = cyc["q_num"], cyc["code"]
    assert qn == "1" and code == "180940"
    first = lambda name: _slot_paras(_slot(cyc, name))[0]["t"]
    assert first("p0_top") == f"[{code}]"       # step1_a1_2 → [code]
    assert first("p0_bot") == f"[{qn}]"         # step1_a1 → [q_num]
    assert first("p1_main") == f"[{qn}]"
    assert first("p2_main") == f"[{qn}]"
    assert first("p3_main") == f"[{qn}]"
    assert first("p4_main") == "{%s}" % qn      # step1_c1 → {q_num}
    assert first("p6_sel") == "{%s}" % qn       # step2_a1 → {q_num}
    assert first("p9_main") == "{%s}" % code    # step2_c2 → {code}
    # 마커 없음 스텝: 선두가 마커 형태가 아님
    for name in ("p5_main", "p7_main", "p8_main"):
        assert not re.match(r"^[\[{]\d+[\]}]$", first(name)), name
    # step3 → {code} 선두 + $BASIC (v1 processStep3 pass 19)
    s3 = _slot_paras(_slot(cyc, "step3"))
    assert s3[0]["t"] == "{%s}" % code and s3[0]["s"] == _BASIC


def test_step3_kind_styles():
    """step3 kind 주석 → 발문/지문/선지 스타일 + 문장삽입 배경 보강."""
    plan = content_to_plan(_load(_FULL_CASE))
    got_bg = 0
    for cyc in plan["cycles"]:
        paras = _slot_paras(_slot(cyc, "step3"))
        styles = {p["s"] for p in paras}
        assert "STEP 03 > S_실전문제 번호 수정 올림포스" in styles, cyc["q_num"]
        assert "STEP 03 > 실전 문제 지문 올림포스_" in styles, cyc["q_num"]
        # 문장삽입 발문 뒤 첫 본문 = 배경 (v1 processStep3 규칙 보강)
        for i, p in enumerate(paras):
            if (p["s"] == "STEP 03 > S_실전문제 번호 수정 올림포스"
                    and re.search(r"들어갈\s*위치", p["t"])):
                nxt = next(q for q in paras[i + 1:] if q["t"].strip())
                assert nxt["s"] == "STEP 03 > 배경 올림포스", cyc["q_num"]
                got_bg += 1
    assert got_bg >= 3      # 마더텅 15강 — 문장삽입 변형 4문항 (코퍼스 실측)


def test_content_conservation():
    """플랜 단어 보존 — 사이클×슬롯의 원고 단어가 플랜에 전량 존재.

    (의도 삭제 룰은 workbook_v2 빌더와 동일 — 여기서는 영단어(4자+)만
    엄격 대조해 세로 재편성 과정의 누락을 가드한다.)
    """
    re_eng = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
    for case in (_FULL_CASE,) + _S3_ONLY_CASES:
        content = _load(case)
        plan = content_to_plan(content)
        for raw_cyc, plan_cyc in zip(content["cycles"], plan["cycles"]):
            got = set()
            for s in plan_cyc["slots"]:
                if s.get("clear"):
                    continue
                for p in _slot_paras(s):
                    got.update(w.lower() for w in re_eng.findall(p["t"]))
            # step3는 삭제 룰 없음(정답류는 파서가 이미 제거) → 전량 보존
            want = set()
            for p in raw_cyc["steps"]["step3"]:
                want.update(w.lower()
                            for w in re_eng.findall(p.get("text") or ""))
            missing = want - got
            assert not missing, (case, raw_cyc["q_num"],
                                 sorted(missing)[:8])


def test_c1_no_condition_split():
    """세로 C1은 조건(주어진 문장) NEXT_FRAME 분리 없음 — 유닛 2개 고정.

    v1 실물 출력 대조(E2E)로 확정: 사이클 C1 페이지는 프레임 2개(상단 보기 +
    하단 발문/지문)라 조건 분리를 켜면 오버플로우. 상단+하단 = 2유닛이어야
    하고, 유닛 선두는 헤더({N}) 또는 하단 스타일이어야 한다.
    """
    plan = content_to_plan(_load(_FULL_CASE))
    for cyc in plan["cycles"]:
        s = _slot(cyc, "p4_main")
        assert len(s["units"]) == 2, (cyc["q_num"], len(s["units"]))
        bottom = [p for u in s["units"][1:] for p in unit_paras(u)]
        assert bottom[0]["s"] == "STEP 01 > 하단 문제", cyc["q_num"]
        # 주어진 문장(조건)은 BTM 분홍 박스 — 문장삽입 변형 포함 (조건 gap
        # 일반화 보강: 무스타일 방치 금지)
        styles = [p["s"] for p in bottom]
        assert "STEP 01 > C1_문장 배열 하단" in styles, cyc["q_num"]
        assert "$BASIC" not in [p["s"] for p in bottom
                                if p["t"].strip()
                                and re.match(r"^[A-Za-z]", p["t"].strip())
                                ], cyc["q_num"]


def test_exclude_gates():
    """제외 섹션 — v1 페이지 게이트 의미론 (슬롯 자체가 빠짐)."""
    content = _load(_FULL_CASE)
    plan = content_to_plan(content, exclude=["step1_a1", "step2_a1",
                                             "step3", "step2_b1"])
    for cyc in plan["cycles"]:
        slots = {s["slot"] for s in cyc["slots"]}
        # step1_a1 게이트 → P+0 두 슬롯 모두 제외 (v1 quirk 보존)
        assert "p0_top" not in slots and "p0_bot" not in slots
        # step2_a1 게이트 → P+6 두 슬롯 모두 제외
        assert "p6_sel" not in slots and "p6_btm" not in slots
        assert "step3" not in slots
        assert "p7_main" not in slots
        # q_num 표기도 게이트를 따름 (P+7은 step2_b1 게이트)
        assert cyc["qnum_slots"] == ["p5_num", "p8_num"]
        # 나머지는 유지
        assert "p4_main" in slots and "p9_main" in slots


def test_exclude_c1_bottom():
    """step1_c1_btm — 하단(발문/BTM/BTM_T)만 제외, 상단 유지."""
    plan = content_to_plan(_load(_FULL_CASE), exclude=["step1_c1_btm"])
    for cyc in plan["cycles"]:
        s = _slot(cyc, "p4_main")
        styles = {p["s"] for p in _slot_paras(s)}
        assert "STEP 01 > C1_문장 배열 하단" not in styles
        assert "STEP 01 > 하단 문제" not in styles
        assert "STEP 01 > C1_문장 배열" in styles


def test_icons_present_full_case():
    """아이콘 op — TF 버튼/문제아이콘/화살표/영작답지가 사이클마다 존재."""
    plan = content_to_plan(_load(_FULL_CASE))
    for cyc in plan["cycles"]:
        labels = {}
        for s in cyc["slots"]:
            if s.get("clear"):
                continue
            for p in _slot_paras(s):
                ic = p.get("icon")
                if ic:
                    labels[ic["label"]] = labels.get(ic["label"], 0) + 1
        assert labels.get("TF 버튼", 0) > 0, cyc["q_num"]        # 1A2 + 2B1
        assert labels.get("화살표 답지", 0) >= 1, cyc["q_num"]    # 1C1
        assert labels.get("STEP1 문제아이콘", 0) >= 1, cyc["q_num"]
