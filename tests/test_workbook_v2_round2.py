"""W12 — 품질 루프 2라운드 결함 가드 (미학습 원고 3종 실증 결함의 재발 방지).

투입 원고 (docs/원고_구조_인벤토리.md 다양성 후보):
  후보⑫ 명일여고1 외부지문2 워크북 — 코너명형 헤더 + Unit 구분선
  후보⑭ 명일여고1 외부지문3 워크북 — 수능 Analysis 헤더 + 올림포스 스텝3
  후보②  리딩파워 유형(기본) 변형문제 문제모음 hwp

결함→가드 매핑:
  D1 코너명형 헤더("N. pN-수능 Analysis") 미인식 → 첫 정규식 매치 이전
     지문 통째 유실 (파서 _RE_HEADER_NUM 한글 꼬리 영문 혼용)
  D2 원전 Unit 구분선("Unit 10 긴 어구 빈칸") 본문 잔존 (파서 구분선 제거
     + 게이트 G8)
  D3 C1/A1 빌더 라벨: {분석N}/{N} (plan _C1_GREPS/extract_tail)
  D4 hwp 탭 제어문자 유실 → 표형 선지 셀 병합 (extractors 탭 보존)
  D5 변형문제 문제모음 파일명 → Step3 라우팅 (침묵 유실 + 게이트 G7 빈플랜)
  D6 passage_labels가 p80을 p8+"0"으로 쪼개 엉뚱한 지문번호 프레임 갱신
"""
import json
import os
import struct

import pytest

from engines.workbook.parser import (_RE_HEADER_NUM, _strip_chapter_dividers,
                                     _strip_manuscript_headers)
from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_v2.plan import (extract_tail, is_a1_header,
                                      is_header_line, passage_labels,
                                      build_step1_c1)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


def _paras(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


# ── D1: 코너명형 헤더 인식 (파서 정규식) ────────────────────────────────────

def test_header_num_recognizes_corner_names():
    for h in ("1. p80-수능 Analysis", "2. p96-수능 Analysis",
              "1. p104-수능 Analysis", "3. p98-Practice 01",
              "4. p108-Practice 03"):
        assert _RE_HEADER_NUM.match(h), h
    # 기존 형식 무회귀
    for h in ("1. p2-no.18", "18. p8-no.41~42", "1. p8-Example 1",
              "1. p1-no.3과 추가지문", "1. L1-본문1  (정답 1개)"):
        assert _RE_HEADER_NUM.match(h), h
    # 본문/구분선은 헤더가 아님
    for t in ("Unit 13 문장 삽입", "15.  Striving making your presentations",
              "The Internet really is a strange place."):
        assert not _RE_HEADER_NUM.match(t), t


def test_strip_headers_keeps_corner_name_passages():
    """첫 정규식 매치가 뒤쪽 헤더일 때 앞 지문이 통째로 잘리던 유실 재현."""
    paras = _paras(
        "명일여고1 외부지문3", "Q. [   ] 안에서 고르시오.", "어법선택(문제지)",
        "", "Unit 13 문장 삽입", "1. p104-수능 Analysis",
        "Recent research on brain function seems to indicate that most.",
        "", "Unit 14 글의 순서 배열", "3. p116-Practice 03",
        "Reminding is very useful for planning and for understanding.")
    kept = _strip_manuscript_headers(paras)
    texts = [p["text"] for p in kept]
    assert texts[0] == "1. p104-수능 Analysis"      # 첫 헤더부터 보존
    assert "Recent research on brain function seems to indicate that most." \
        in texts


# ── D2: Unit 구분선 제거 (파서) ─────────────────────────────────────────────

def test_unit_divider_stripped():
    paras = _paras("Unit 10 긴 어구 빈칸", "1. p80-수능 Analysis",
                   "Chapter 03. 추론적 이해 - 09 빈칸 추론 (1)",
                   "The Internet really is a strange place.",
                   "Unit 15 is a normal English sentence here.")
    kept = [p["text"] for p in _strip_chapter_dividers(paras)]
    assert "Unit 10 긴 어구 빈칸" not in kept
    assert not any(t.startswith("Chapter") for t in kept)
    # 영문 본문 "Unit 15 is ..."는 보존 (한글 유형명일 때만 구분선)
    assert "Unit 15 is a normal English sentence here." in kept


# ── D3: 플랜 계층 — 헤더 판정/라벨 ─────────────────────────────────────────

def test_plan_header_line_and_tail():
    assert is_header_line("1. p80-수능 Analysis")
    assert is_a1_header("1. p80-수능 Analysis")
    assert extract_tail("1. p80-수능 Analysis") == "분석1"
    assert extract_tail("2. p96-수능 Analysis") == "분석2"
    # 기존 수능대비 ANALYSIS 동작 무변경
    assert extract_tail("1. p20 수능대비 ANALYSIS") == "분석"


def test_c1_greps_corner_labels():
    step = {"paragraphs": _paras(
        "1. p80-수능 Analysis",
        "(A) The statistics will vary depending on which article you read.",
        "3. p98-Practice 01",
        "(A) Strive to make your presentations as personal as possible.")}
    built = build_step1_c1(step)
    heads = []
    for u in built["units"]:
        paras = u["paras"] if isinstance(u, dict) else u
        for p in paras:
            if p["t"].strip():
                heads.append(p["t"].strip())
                break
    assert "{분석1}" in heads
    assert "{1}" in heads
    assert built["warnings"] == []


# ── D4: hwp 탭 제어문자 보존 (추출 계층) ────────────────────────────────────

def _hwp_payload(*items):
    """items: str(텍스트) 또는 "TAB" — HWP5 PARA_TEXT payload 합성."""
    out = b""
    for it in items:
        if it == "TAB":
            out += struct.pack("<8H", 9, 0, 0, 0, 0, 0, 0, 9)
        else:
            out += it.encode("utf-16-le")
    return out


def test_hwp_tab_preserved():
    from core.extract.extractors import (_hwp_decode_paratext,
                                         _hwp_text_with_underline)
    payload = _hwp_payload("① is", "TAB", "be done", "TAB", "it")
    assert _hwp_decode_paratext(payload) == "① is\tbe done\tit"
    text, runs = _hwp_text_with_underline(payload, [(0, 0)], {0: False})
    assert text == "① is\tbe done\tit"
    assert "".join(r["t"] for r in runs) == text


# ── D5: 변형문제 문제모음 → Step3 라우팅 ───────────────────────────────────

def test_variant_pool_filename():
    from engines.workbook_v2.engine import _is_variant_pool_filename
    assert _is_variant_pool_filename(
        "리딩파워 유형 (기본)-Unit 15- 123문제 [변형문제]-.hwp")
    assert _is_variant_pool_filename("고1 변형 문제 모음.docx")
    assert not _is_variant_pool_filename("변형문제 정답지.hwp")
    assert not _is_variant_pool_filename("Step1 A1 어휘선택.docx")


# ── 게이트 확장 G7/G8 (검출 실증 — 수리 전 상태 재현) ───────────────────────

def _dump(*para_texts):
    return {"stories": [{"idx": 0, "overflow": False,
                         "paragraphs": [{"t": t, "s": ""}
                                        for t in para_texts]}]}


def test_gate_g7_empty_plan_critical():
    """수리 전 후보② 상태 재현: 원고가 어느 스텝에도 매핑되지 않아
    플랜 유닛 0인데 verify ok=True로 끝나던 침묵 유실."""
    plan = {"flows": [{"step": "step3", "target": {}, "units": []}]}
    rep = inspect_workbook_finish({"steps": {}}, plan, _dump("아무 내용"))
    assert any(c.startswith("[빈플랜]") for c in rep["critical"])
    assert not rep["ok"]


def test_gate_g8_divider_leak_critical():
    """수리 전 후보⑫ 출력 재현: Unit 구분선이 본문에 인쇄됨."""
    plan = {"flows": [{"step": "step2_a1", "target": {},
                       "units": [[{"t": "x", "s": "P"}]]}]}
    rep = inspect_workbook_finish(
        {"steps": {}}, plan,
        _dump("Unit 13 문장 삽입", "{Practice 01}",
              "Strive to make your presentations."))
    assert any(c.startswith("[구분선잔존]") for c in rep["critical"])


def test_gate_g1_detects_corner_header_leak():
    """수리 전 후보⑫/⑭ 출력 재현: 코너명형 헤더 원문 인쇄 — is_header_line
    확장으로 G1이 검출한다 (확장 전에는 미검출 유형)."""
    plan = {"flows": [{"step": "step1_c2", "target": {},
                       "units": [[{"t": "x", "s": "P"}]]}]}
    rep = inspect_workbook_finish(
        {"steps": {}}, plan,
        _dump("1. p80-수능 Analysis", "본문 내용"))
    assert any(c.startswith("[헤더잔존]") for c in rep["critical"])


def test_gate_clean_round2_passes():
    """수리 후 상태: 코너명형 라벨({분석1}/{Practice 01})은 잔존으로 오탐하지
    않는다."""
    plan = {"flows": [{"step": "step2_a1", "target": {},
                       "units": [[{"t": "{분석1}", "s": "P"}]]}]}
    rep = inspect_workbook_finish(
        {"steps": {}}, plan,
        _dump("{분석1}", "{분석2}", "{Practice 01}", "본문."))
    assert rep["critical"] == []


# ── D6: passage_labels 페이지번호 쪼개기 차단 ───────────────────────────────

def test_passage_labels_corner_headers_fall_back_to_brackets():
    """p80이 p8+'0'으로 쪼개져 라벨 [0,6,8]이 나오던 결함 (W12 실증:
    지문번호 프레임이 0/6/8로 갱신됨). 코너명형 헤더 스텝은 라벨을 내지
    않고 step1_a1 bracket 폴백([분석N]/[N])이 담당해야 한다."""
    steps = {
        "step1_c2": {"paragraphs": _paras(
            "1. p80-수능 Analysis", "본문", "3. p98-Practice 01", "본문")},
        "step1_a1": {"paragraphs": _paras(
            "[분석1]", "본문", "[분석2]", "본문", "[1]", "본문", "[3]",
            "본문")},
    }
    assert passage_labels(steps) == ["분석1", "분석2", "1", "3"]
    # W11 추가지문형 무회귀
    steps_w11 = {"step1_c2": {"paragraphs": _paras(
        "1. p1-no.3과 추가지문", "본문", "2. p1-no.4과 추가지문", "본문")}}
    assert passage_labels(steps_w11) == ["3과 추가지문", "4과 추가지문"]


# ── 코퍼스 레벨: 라운드2 케이스 지문 수 보존 ────────────────────────────────

@pytest.mark.parametrize("case,expect_units", [
    ("r2c12ext2", 4),   # 분석1/분석2/Practice01/Practice03
    ("r2c14ext3", 3),   # 13-A/14-A/Practice03(14-3)
])
def test_round2_corpus_passage_counts(case, expect_units):
    golden = os.path.join(CORPUS, "workbook_supp", case, "golden",
                          "content.json")
    steps = json.load(open(golden, encoding="utf-8"))["steps"]
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    from engines.workbook_supp_v2.engine import _STEP_MAP
    ensure_step3_kinds(steps.get("step3"))
    plan = steps_to_plan(steps, workbook_type="모의고사",
                         step_map=dict(_STEP_MAP))
    by_step = {fl["step"]: len(fl["units"]) for fl in plan["flows"]}
    for key in ("step1_a2", "step1_b2", "step1_c2", "step2_a1",
                "step2_a1_btm", "step2_b1", "step2_c1", "step2_c2"):
        assert by_step[key] == expect_units, (case, key, by_step)
    assert plan.get("warnings") == []
    # 구분선/헤더 원문이 플랜에 남지 않음
    from engines.workbook_v2.plan import unit_paras, _norm_header
    import re as _re
    div = _re.compile(r"^Unit\s+\d+\s+[가-힣]")
    for fl in plan["flows"]:
        for u in fl["units"]:
            for p in unit_paras(u):
                t = _norm_header(p["t"])
                assert not div.match(t), (fl["step"], t)
                if t.startswith("{") or t.startswith("["):
                    continue
                assert not is_header_line(t), (fl["step"], t)


def test_round2_c02_step3_routing_and_tabs():
    """후보② 골든: 변형문제 문제모음이 step3로 라우팅되고 표형 선지 탭이
    보존된다 (v2 라우팅 + 탭 수리 통합 가드)."""
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r2c02rp15", "golden",
                          "content.json")
    steps = json.load(open(golden, encoding="utf-8"))["steps"]
    st3 = steps["step3"]
    assert st3["normal_count"] == 1
    paras = st3["normal"][0]["paragraphs"]
    assert len(paras) > 600
    tabs = sum((p.get("text") or "").count("\t") for p in paras)
    assert tabs >= 200
    # 문서 말미 '정답' 블록 절단 (W11 수리 가드 — 이 원고에서도 유효)
    assert (paras[-1].get("text") or "").strip() != "정답"
