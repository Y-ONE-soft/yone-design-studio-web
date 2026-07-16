"""workbook_supp_v2 W11 — 06f4b2c2 결함 6건 수리의 오프라인 가드.

코퍼스: tests/corpus/workbook_supp/06f4b2c2 (교과서 추가지문형 부교재 —
"1. p1-no.3과 추가지문" 헤더 + Step3 말미 '정답' 블록).

결함 매핑:
  D1/D3 헤더 인식/잔존  → 파서 _RE_HEADER_NUM 한글꼬리 + plan is_header_line/
                          extract_tail/_C1_GREPS (test_header_*)
  D2   상/하단 반전     → supp step_map pos 힌트 (test_step_map_pos)
  D4   페이지 정리      → _plan_decorations page_cleanup (test_decorations)
  D5   지문번호 프레임  → passage_labels + passage_numbers op (test_labels)
  D6   정답 포함        → 파서 '정답' 단독줄 절단 (test_step3_no_answers)
게이트: 기존 불량 덤프(tests/fixtures/typeset_dump_supp_bad_06f4b2c2.json)에서
  헤더잔존/정답잔존/지문번호 critical 검출 (test_gate_detects_defects).
"""
import json
import os

import pytest

from engines.workbook_v2.plan import (steps_to_plan, unit_paras,
                                      passage_labels, is_header_line,
                                      is_a1_header, extract_tail)
from engines.workbook_supp_v2.engine import (WorkbookSuppV2Engine,
                                             _STEP_MAP)
from engines.workbook_v2.gate import inspect_workbook_finish

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(TESTS_DIR, "corpus", "workbook_supp", "06f4b2c2",
                      "golden", "content.json")
BAD_DUMP = os.path.join(TESTS_DIR, "fixtures",
                        "typeset_dump_supp_bad_06f4b2c2.json")


@pytest.fixture(scope="module")
def content():
    return json.load(open(GOLDEN, encoding="utf-8"))


@pytest.fixture(scope="module")
def plan(content):
    p = steps_to_plan(content["steps"], workbook_type="모의고사",
                      step_map=_STEP_MAP)
    p["page_cleanup"] = {"empty_master": "M"}
    p["passage_numbers"] = {"labels": passage_labels(content["steps"]),
                            "steps": ["step1_c2", "step2_b1", "step2_c1"]}
    return p


def _flow(plan, step):
    return next(f for f in plan["flows"] if f["step"] == step)


def _texts(flow):
    return [p["t"] for u in flow["units"] for p in unit_paras(u)]


# ── D1: 추가지문형 헤더 인식 (기존 형식 무회귀 포함) ─────────────────────────

def test_header_recognizers():
    assert is_header_line("1. p1-no.3과 추가지문")
    assert is_header_line("2. p2-no.4과 추가지문  (정답 1개)")
    assert is_a1_header("1. p1-no.3과 추가지문")
    # 기존 형식 무회귀
    assert is_header_line("1. p2-no.20")
    assert is_header_line("18. p8-no.41~42")
    assert not is_header_line("Carbon capture and storage is a technology")
    assert not is_header_line("① how carbon capture works")


def test_header_extract_tail():
    assert extract_tail("1. p1-no.3과 추가지문") == "3과 추가지문"
    # 기존 형식 무회귀
    assert extract_tail("1. p2-no.20") == "20"
    assert extract_tail("1. p2-no.20 본문") == "본문"


def test_parser_header_num_korean_tail():
    from engines.workbook.parser import _RE_HEADER_NUM
    assert _RE_HEADER_NUM.match("1. p1-no.3과 추가지문")
    assert _RE_HEADER_NUM.match("2. p2-no.4과 추가지문  (정답 1개)")
    m = _RE_HEADER_NUM.match("1. p1-no.3과 추가지문")
    assert m.group(1) == "3"
    # 기존 형식 무회귀 (골든 스냅샷이 전량 가드 — 여기선 대표 케이스)
    assert _RE_HEADER_NUM.match("1. p2-no.18")
    assert _RE_HEADER_NUM.match("1. L1-본문1  (정답 1개)")
    assert not _RE_HEADER_NUM.match("이 글의 주제로 가장 적절한 것은?")


# ── D3: 플랜 산출물에 헤더 원문 잔존 없음 + 라벨 정규화 ──────────────────────

def test_no_raw_headers_in_plan(plan):
    for fl in plan["flows"]:
        for t in _texts(fl):
            assert "no.3과" not in t and "no.4과" not in t, (fl["step"], t)


def test_a1_header_tail_braces(plan):
    texts = _texts(_flow(plan, "step2_a1"))
    assert "{3과 추가지문}" in texts
    assert "{4과 추가지문}" in texts
    assert "{과 추가지문}" not in texts       # 수리 전 회귀 형태


def test_c1_header_braces(plan):
    braces = [t for t in _texts(_flow(plan, "step1_c1")) if "{" in t]
    assert braces == ["{3과 추가지문}", "{4과 추가지문}"]


def test_header_steps_unit_split(plan):
    # 헤더 인식 → 지문 2개 = 유닛 2개 (수리 전에는 1유닛 통짜)
    for step in ("step1_c2", "step2_b1", "step2_c1"):
        assert len(_flow(plan, step)["units"]) == 2, step


# ── D2: supp step_map pos 힌트 ───────────────────────────────────────────────

def test_step_map_pos(plan):
    assert _STEP_MAP["step2_a1"]["pos"] == "top"
    assert _STEP_MAP["step2_a1_btm"]["pos"] == "bottom"
    assert WorkbookSuppV2Engine()._step_map() is _STEP_MAP
    tg = {f["step"]: f["target"] for f in plan["flows"]}
    assert tg["step2_a1"].get("pos") == "top"
    assert tg["step2_a1_btm"].get("pos") == "bottom"
    # W13: 본가/textbook 실기(c05/c13/c15) + v1 실물 SL2 기하 확인으로
    # 기본 STEP_MAP에도 pos 확산 (W11의 '실기 확인 후 별도' 조건 충족)
    from engines.workbook_v2.plan import STEP_MAP as BASE
    assert BASE["step2_a1"]["pos"] == "top"
    assert BASE["step2_a1_btm"]["pos"] == "bottom"


# ── D4/D5: supp 데코레이션 (page_cleanup + passage_numbers) ──────────────────

def test_labels(content):
    assert passage_labels(content["steps"]) == ["3과 추가지문", "4과 추가지문"]
    # 모의고사형 무회귀: 헤더 "1. p2-no.20" → "20"
    mock = {"step1_c2": {"paragraphs": [
        {"text": "1. p2-no.20"}, {"text": "본문..."},
        {"text": "2. p3-no.21"}]}}
    assert passage_labels(mock) == ["20", "21"]


def test_decorations(content, tmp_path):
    job = str(tmp_path)
    with open(os.path.join(job, "content.json"), "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    # W21 r11 (실사용 0e3108fd 전체-1/전체-2): 기본 내지는 빈 STEP3 페이지
    # 삭제(delete 모드 — 'M 마스터 보존' v1 관행 폐기 확정) + 섹션 시작
    # 좌/우 마스터 정합 op. 학교 전용 내지는 기존 동작 유지.
    assert deco["page_cleanup"] == {"empty": "delete"}
    assert deco["section_masters"] is True
    assert deco["passage_numbers"]["labels"] == ["3과 추가지문",
                                                 "4과 추가지문"]
    assert deco["passage_numbers"]["steps"] == ["step1_c2", "step2_b1",
                                                "step2_c1"]


def test_base_engine_decorations_unchanged(tmp_path):
    """본가 데코 가드 — W13부터 page_cleanup opt-in (c05 실기: 잔여 22페이지).
    passage_numbers는 본가 미적용 유지 (모의고사 번호 프레임 정합).
    W23 r13 의미론 갱신: question_keep 센티널 추가 (F4 — 문제 단위 펼침면
    킵, supp+본가 opt-in. prepare_jsx가 플랜 완성 후 계약으로 확장)."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    deco = WorkbookV2Engine()._plan_decorations(str(tmp_path), {})
    assert deco == {"page_cleanup": {"empty_master": "M"},
                    "question_keep": True}
    assert "passage_numbers" not in deco


# ── D6: step3 정답 블록 절단 ─────────────────────────────────────────────────

def test_step3_no_answers(content, plan):
    paras = content["steps"]["step3"]["normal"][0]["paragraphs"]
    texts = [p["text"] for p in paras]
    assert not any(t.strip() == "정답" for t in texts)
    assert not any("1. ①" in t for t in texts)
    s3 = _texts(_flow(plan, "step3"))
    assert not any("1. ①" in t or "(A) securely" in t for t in s3)
    # 문항 내용은 보존 (마지막 문항 24번의 답란까지)
    assert any("답:" in t for t in s3)


def test_strip_step3_answers_bare_marker():
    from engines.workbook.parser import _strip_step3_answers
    paras = [{"text": "24. 다음 글을 읽고..."}, {"text": "답: ___"},
             {"text": "정답"}, {"text": "1. ①   2. ⑤"}]
    out = _strip_step3_answers(paras)
    assert [p["text"] for p in out] == ["24. 다음 글을 읽고...", "답: ___"]


# ── 게이트: 기존 불량 덤프에서 결함 자동 검출 ────────────────────────────────

def test_gate_detects_defects(content, plan):
    dump = json.load(open(BAD_DUMP, encoding="utf-8"))
    rep = inspect_workbook_finish(content, plan, dump)
    assert not rep["ok"]
    kinds = [c.split("]")[0] + "]" for c in rep["critical"]]
    assert "[헤더잔존]" in kinds       # D1/D3
    assert "[정답잔존]" in kinds       # D6
    assert "[지문번호]" in kinds       # D5
    # 구버전 덤프 — 페이지/좌표 정보 없음은 경고로 안내 (D2/D4는 재덤프 필요)
    assert any("잔여페이지" in w for w in rep["warnings"])
    assert any("상하배치" in w for w in rep["warnings"])
    assert rep["stats"]["header_leaks"] >= 6
    assert rep["stats"]["answer_leaks"] >= 2
    assert rep["stats"]["number_frame_unknown"] >= 17


def test_gate_extended_dump_detects_swap_and_stale(content, plan):
    """W11 확장 덤프 필드(b/pg/stale_pages) 경로 — 합성 덤프로 게이트 검증."""
    dump = json.load(open(BAD_DUMP, encoding="utf-8"))
    # 상/하단 반전 재현: a1 프로브 스토리를 하단(top 164), btm을 상단(31)에
    a1_probe = max((p["t"] for st in dump["stories"]
                    for p in st["paragraphs"] if "1[is / are]" in p["t"]),
                   key=len)
    for st in dump["stories"]:
        joined = "".join(p["t"] for p in st["paragraphs"])
        if a1_probe in joined:
            st["b"] = [164, 20]
            st["pg"] = ["114"]
        if "①is an environmental technology" in joined:
            st["b"] = [31, 20]
            st["pg"] = ["114"]
    dump["stale_pages"] = [{"p": "6", "m": "A-마스터"},
                           {"p": "200", "m": "M-마스터"}]
    rep = inspect_workbook_finish(content, plan, dump)
    kinds = [c.split("]")[0] + "]" for c in rep["critical"]]
    assert "[상하반전]" in kinds       # D2
    assert "[잔여페이지]" in kinds     # D4
    # M-마스터 빈 페이지는 의도된 상태 — 잔여로 세지 않음
    assert rep["stats"]["stale_pages"] == 1


def test_gate_clean_output_passes(content, plan):
    """수리 후 상태를 모사한 덤프는 게이트 통과 (경고 없는 critical 0)."""
    stories = []
    for fl in plan["flows"]:
        paras = [{"t": p["t"], "s": p["s"] or ""}
                 for u in fl["units"] for p in unit_paras(u)]
        st = {"idx": len(stories), "overflow": False, "pg": ["10"],
              "b": [31, 20], "paragraphs": paras}
        stories.append(st)
    # 상/하단 좌표를 올바르게 배치
    a1_probe = max((p["t"] for u in _flow(plan, "step2_a1")["units"]
                    for p in unit_paras(u)), key=len)
    btm_probe = max((p["t"] for u in _flow(plan, "step2_a1_btm")["units"]
                     for p in unit_paras(u)), key=len)
    for st in stories:
        joined = [p["t"] for p in st["paragraphs"]]
        if a1_probe in joined:
            st["b"] = [31, 20]
            st["pg"] = ["114"]
        if btm_probe in joined:
            st["b"] = [164, 20]
            st["pg"] = ["114"]
    # 갱신된 지문번호 프레임 (단일 단락 스토리)
    for lb in plan["passage_numbers"]["labels"]:
        stories.append({"idx": len(stories), "overflow": False,
                        "pg": ["94"], "b": [32, 10],
                        "paragraphs": [{"t": lb + "\r", "s": "[기본 단락]"}]})
    dump = {"doc": "x", "stories": stories, "overflow_stories": 0,
            "page_count": 40, "stale_pages": []}
    rep = inspect_workbook_finish(content, plan, dump)
    assert rep["critical"] == [], rep["critical"]
