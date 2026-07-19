# -*- coding: utf-8 -*-
"""W30-r15 후속 — ❮❯(U+276E/F) 글리프 인쇄 매핑 가드.

r15 재조판 실측(job 376b34d0 재조판 c25) 잔존 warning 1건: step3 실전문제
지문의 삽입 문장 표기 ❮…❯ 12건이 본문 폰트 Noto Sans CJK KR cmap에 글리프
없음 (core.fontcov 실측 — 전 7웨이트 미지원) → tofu/미표시 인쇄.

수리 (W23 SUBSCRIPT_PRINT_TABLE ₂ 전례 — 등가 치환 + 플랜 계층):
  - plan.GLYPH_PRINT_TABLE: ❮→〈(U+3008) / ❯→〉(U+3009). 치환 문자는
    cmap 실측으로 선택 — 〈〉는 Noto Sans CJK KR 전 7웨이트 커버
    (‹›/《》/＜＞도 커버되나 원표기와 가장 가까운 홑꺾쇠 채택).
  - 단 아래첨자/PUA와 달리 **빌더 이후** 적용 (steps_to_plan 내
    apply_glyph_print_map_units) — 1A1 빌더의 ❮❯→[](_A1_TABLE)·1A2 빌더의
    ❮T/F❯ 토큰 제거가 ❮❯를 소비하므로 빌더 전 치환은 해당 로직을
    무력화한다. 1:1 치환 — 텍스트/runs 오프셋 보존, content 원본 무변형.
  - 게이트 G29 ①b: 등재 문자 출력 잔존 = 치환된 현행 플랜이면 critical,
    구플랜(플랜에 등재 문자 잔존) 소급은 warning. ② cmap 실측 경로는
    등재 문자를 제외 (①b와 이중 보고 방지).

픽스처: tests/fixtures/w30_r15_defect_dumps/ (당시 플랜/출력 덤프 — ❮❯
12건 잔존 실물), 코퍼스: tests/corpus/textbook_workbook/r15c25ybm2.
"""
import copy
import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
CASE = os.path.join(TESTS_DIR, "corpus", "textbook_workbook", "r15c25ybm2")
FIXT = os.path.join(TESTS_DIR, "fixtures", "w30_r15_defect_dumps")

from engines.workbook_v2.gate import inspect_workbook_finish   # noqa: E402
from engines.workbook_v2.plan import (GLYPH_PRINT_TABLE,       # noqa: E402
                                      apply_glyph_print_map_units,
                                      ensure_step3_kinds, steps_to_plan,
                                      unit_paras)


@pytest.fixture(scope="module")
def content():
    return json.load(open(os.path.join(CASE, "golden", "content.json"),
                          encoding="utf-8"))


@pytest.fixture(scope="module")
def case_plan(content):
    steps = copy.deepcopy(content["steps"])
    ensure_step3_kinds(steps.get("step3"))
    return steps_to_plan(steps, workbook_type="교과서")


@pytest.fixture(scope="module")
def bad_plan():
    return json.load(open(os.path.join(
        FIXT, "render_plan_bad_376b34d0.json"), encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_dump():
    return json.load(open(os.path.join(
        FIXT, "typeset_dump_bad_376b34d0.json"), encoding="utf-8"))


# ── 치환 문자 선택 근거: cmap 실측 ───────────────────────────────────────────

def test_font_cmap_evidence():
    """❮❯ 미지원 / 〈〉 지원 — Noto Sans CJK KR 실측 (없으면 skip)."""
    from core.fontcov import font_covers
    fonts = [os.path.expanduser(f"~/Library/Fonts/NotoSansCJKkr-{w}.otf")
             for w in ("Regular", "Medium", "Bold")]
    fonts = [f for f in fonts if os.path.isfile(f)]
    if not fonts:
        pytest.skip("Noto Sans CJK KR 미설치")
    for f in fonts:
        assert font_covers(f, "❮") is False
        assert font_covers(f, "❯") is False
        assert font_covers(f, "〈") is True
        assert font_covers(f, "〉") is True


# ── 유닛 단위 치환 — runs 오프셋 보존 ────────────────────────────────────────

def test_glyph_map_units_runs_offsets():
    units = [{"paras": [
        {"t": "❮He would often❯ do", "s": "S", "runs": [
            {"t": "❮He would ", "ul": False},
            {"t": "often❯", "ul": True},
            {"t": " do", "ul": False}]},
        {"t": "no target", "s": "S", "runs": [{"t": "no target", "ul": False}]},
    ]}]
    apply_glyph_print_map_units(units)
    p = units[0]["paras"][0]
    assert p["t"] == "〈He would often〉 do"
    assert "".join(r["t"] for r in p["runs"]) == p["t"]
    assert [r["ul"] for r in p["runs"]] == [False, True, False]
    # 대상 없는 단락 무변형
    assert units[0]["paras"][1]["t"] == "no target"


def test_glyph_map_units_no_text_runs_kept():
    """t 없는 run(아이콘 등)은 그대로 보존."""
    units = [[{"t": "❮x❯", "s": "S",
               "runs": [{"icon": "TF"}, {"t": "❮x❯", "ul": False}]}]]
    apply_glyph_print_map_units(units)
    p = units[0][0]
    assert p["t"] == "〈x〉"
    assert p["runs"][0] == {"icon": "TF"}
    assert p["runs"][1]["t"] == "〈x〉"


# ── r15 코퍼스: 플랜 치환 실측 + 빌더 소비 로직 보존 ─────────────────────────

def test_case_plan_substitutes_all_glyphs(content, case_plan):
    """골든(❮ 408건 잠복) → 플랜 잔존 0, step3 삽입 문장 표기 12건이
    〈〉로 치환, 전 단락 runs 오프셋 일치. 골든 content는 무변형."""
    resid = 0
    subst = 0
    for fl in case_plan["flows"]:
        for u in fl["units"]:
            for p in unit_paras(u):
                t = p.get("t") or ""
                resid += sum(t.count(ch) for ch in GLYPH_PRINT_TABLE)
                subst += t.count("〈") + t.count("〉")
                if p.get("runs"):
                    joined = "".join(r.get("t", "") for r in p["runs"]
                                     if isinstance(r.get("t"), str))
                    assert joined == t
    assert resid == 0
    assert subst == 12
    raw = json.dumps(content, ensure_ascii=False)
    assert raw.count("❮") == 408 and raw.count("❯") == 408   # 원본 무변형


def test_builder_consumption_still_first(content, case_plan):
    """1A1 빌더의 ❮❯→[] 소비가 유지된다 — 글리프 치환이 빌더 이후라
    A1 어휘 선택 괄호는 여전히 []로 인쇄 (〈〉 아님)."""
    a1 = [fl for fl in case_plan["flows"] if fl["step"] == "step1_a1"]
    assert a1
    src_has = "❮" in json.dumps(content["steps"]["step1_a1"],
                                ensure_ascii=False)
    assert src_has, "전제: 원고 1A1에 ❮❯ 존재"
    for u in a1[0]["units"]:
        for p in unit_paras(u):
            assert "〈" not in p["t"] and "❮" not in p["t"]


# ── 게이트 G29 ①b: 소급 warning / 매핑 미적용 critical / 치환 후 0 ──────────

def test_gate_glyph_residue_retro_warning(content, bad_plan, bad_dump):
    """구플랜(❮ 잔존 — 치환 미지원)의 구출력 12건 = warning 소급."""
    rep = inspect_workbook_finish(content, bad_plan, bad_dump)
    assert rep["stats"]["glyph_residue"] == 12
    w = [m for m in rep["warnings"]
         if "글리프 인쇄 매핑 등재 문자 잔존" in m]
    assert w and "U+276E" in w[0] and "6건" in w[0], rep["warnings"]
    assert not [m for m in rep["critical"]
                if "글리프 인쇄 매핑" in m]


def test_gate_glyph_residue_critical_with_current_plan(content, case_plan,
                                                       bad_dump):
    """치환된 현행 플랜(등재 문자 0)의 출력에 잔존 = 매핑 미적용 = critical."""
    rep = inspect_workbook_finish(content, case_plan, bad_dump)
    c = [m for m in rep["critical"]
         if "글리프 인쇄 매핑 등재 문자 잔존" in m]
    assert c and "U+276F" in c[0], rep["critical"]


def test_gate_clean_after_substitution(content, case_plan, bad_dump):
    """치환된 출력(❮❯→〈〉)을 모사 — [글리프커버리지] 계열 전무 (①b 잔존
    0 + ② cmap 경로도 등재 문자 제외로 침묵) = 'G29 warning 0'."""
    d = copy.deepcopy(bad_dump)
    for st in d["stories"]:
        for p in st["paragraphs"]:
            p["t"] = (p["t"].replace("❮", "〈").replace("❯", "〉"))
    rep = inspect_workbook_finish(content, case_plan, d)
    assert rep["stats"]["glyph_residue"] == 0
    assert not [m for m in rep["warnings"] + rep["critical"]
                if m.startswith("[글리프커버리지]")], (
        rep["warnings"], rep["critical"])
