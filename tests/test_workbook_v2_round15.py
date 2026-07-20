# -*- coding: utf-8 -*-
"""W30-r15 — 실서비스 job 376b34d0 (교과서 워크북 v2, 공통영어2 YBM(김) 1과)
실사용 결함 7건 수리 가드.

결함 실물 (uploads 실측 원문 repr):
  1. step1_c1: '6. L1-추가본문' 헤더가 _C1_GREPS 미정규화 → 추가본문 지문이
     본문5 블록에 흡수 (유닛 10개 — page_break/발문/프레임 분리 누락)
  2~4. step1_c2/step2_b1/step2_c1: '1. L1-p. 13 본문 1' (compact
     'L1-p.13본문1') / '6. L1-추가본문' (compact 'L1-추가본문')이
     is_header_line 미인식 → 지문 6개가 유닛 1개 통짜 + 헤더 원문 인쇄
  5. step3: 출처 라인 '공통영어2_YBM(김) 1과_03' 인쇄 (kind UNKNOWN 추락)
  6. p95~98 프레임 1개 잔존 — expandStoryOverflow가 마지막 프레임 1개만
     복제 (2단 O-마스터 페이지의 1단 열화)
  7. 크레딧(판권) p99 오른쪽 단독 — 크레딧 왼쪽 정렬 + 오른쪽 메모(M) 규칙
     (W22 파트 경계 규칙의 크레딧 확장, 사용자 확정 스펙)

게이트 봉합 규명 (경고 0이었던 이유):
  - G7: 전 플로우 합산 유닛 수만 검사 — 스텝별 유닛 1개는 통과
  - G6: is_header_line OR is_a1_header 로 '인식'을 판정 — a1 인식기가
    L-형을 잡아 recognized>0, 정작 유닛 분할 빌더는 is_header_line 사용
  - G24①: per_passage_units 계약이 교과서 step_map에 미등재 (r14 '실물
    대조 근거 없음' 보류) — 이번 실물로 근거 확보, 등재
  - (G1 헤더잔존 critical은 발화했으나 /api/result 401로 사용자 미전달)

불량 픽스처: tests/fixtures/w30_r15_defect_dumps/ (당시 플랜/출력 덤프).
코퍼스: tests/corpus/textbook_workbook/r15c25ybm2 (골든 = 수리 후 파서 산출).
"""
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "tests", "corpus")
CASE = os.path.join(CORPUS, "textbook_workbook", "r15c25ybm2")
FIXT = os.path.join(REPO, "tests", "fixtures", "w30_r15_defect_dumps")

from engines.workbook_v2.gate import inspect_workbook_finish   # noqa: E402
from engines.workbook_v2.plan import (is_header_line, steps_to_plan,   # noqa: E402
                                      ensure_step3_kinds, passage_labels,
                                      unit_paras, _RE_S3_TEXTBOOK_SRC)


def _case_steps():
    c = json.load(open(os.path.join(CASE, "golden", "content.json"),
                       encoding="utf-8"))
    return c["steps"]


def _case_plan():
    steps = _case_steps()
    ensure_step3_kinds(steps.get("step3"))
    return steps_to_plan(steps, workbook_type="교과서")


def _paras(flow):
    return [p for u in flow["units"] for p in unit_paras(u)]


# ── 결함 2~4: L-p-코너명형 / L-한글라벨형 헤더 인식 ─────────────────────────

def test_header_line_recognizes_textbook_lp_corner_forms():
    assert is_header_line("1. L1-p. 13 본문 1")
    assert is_header_line("2. L1-p. 14 본문 2")
    assert is_header_line("6. L1-추가본문")
    # 기존 형식 무회귀
    assert is_header_line("1. p2-no.20")
    assert is_header_line("1. L1-본문1")
    assert is_header_line("1. no.1")
    assert is_header_line("1. p1-no.3과 추가지문")
    # 본문 문장/한글 해석 줄은 헤더가 아니다
    assert not is_header_line("우리를 미래에 대한 희망으로 채우는 많은 것들")
    assert not is_header_line("There are a lot of things that fill us")


def test_case_plan_per_passage_units():
    plan = _case_plan()
    by_step = {fl["step"]: len(fl["units"]) for fl in plan["flows"]}
    for key in ("step1_c2", "step2_b1", "step2_c1", "step1_a1",
                "step2_a1", "step2_a1_btm"):
        assert by_step[key] == 6, (key, by_step)
    assert by_step["step1_c1"] == 12          # 지문 6 × (본문 + 하단)
    assert plan.get("warnings") == []
    assert passage_labels(_case_steps()) == [
        "본문1", "본문2", "본문3", "본문4", "본문5", "추가본문"]
    # 헤더 원문이 어느 플로우에도 남지 않는다 (G1 부류의 플랜 차원 증명)
    for fl in plan["flows"]:
        for p in _paras(fl):
            assert "L1-p" not in p["t"] and "L1-추가본문" not in p["t"], (
                fl["step"], p["t"][:60])


# ── 결함 1: step1_c1 추가본문 헤더 정규화 + 이중 중괄호 교정 ────────────────

def test_case_c1_headers_normalized_single_brace():
    plan = _case_plan()
    fl = next(f for f in plan["flows"] if f["step"] == "step1_c1")
    hdrs = [p["t"] for p in _paras(fl) if p["t"].startswith("{")]
    assert hdrs == ["{본문1}", "{본문2}", "{본문3}", "{본문4}", "{본문5}",
                    "{추가본문}"]
    assert not any("{{" in h for h in hdrs)
    # 추가본문 블록도 page_break 유닛으로 분리된다
    pb = [bool(isinstance(u, dict) and u.get("page_break"))
          for u in fl["units"]]
    assert pb.count(True) == 5                # 2번째~6번째 지문 헤더


# ── 결함 5: step3 출처 라인 제거 ────────────────────────────────────────────

def test_step3_textbook_source_lines_removed():
    assert _RE_S3_TEXTBOOK_SRC.match("공통영어2_YBM(김) 1과_03")
    assert _RE_S3_TEXTBOOK_SRC.match("공통영어2_YBM(김) 1과_01~02")
    # 본문 문장 오매치 없음
    assert not _RE_S3_TEXTBOOK_SRC.match("There are a lot of things")
    assert not _RE_S3_TEXTBOOK_SRC.match("1과_03")
    plan = _case_plan()
    fl = next(f for f in plan["flows"] if f["step"] == "step3")
    texts = [p["t"] for p in _paras(fl)]
    assert not any(_RE_S3_TEXTBOOK_SRC.match(t.strip()) for t in texts)
    # 제거는 출처 라인만 — 문항 콘텐츠는 보존
    joined = "\n".join(texts)
    assert "다음 글의 주제로 가장 적절한 것은?" in joined


def test_condition_paren_note_stays_cond():
    """GH_SUBTITLE 토큰 상한 (W30-r15): 조건 블록의 긴 괄호 부연은 부제가
    아니다 — GH로 증발+Cond 사슬 절단 대신 Cond 유지 (G15 조건항목의 원인
    수리. 짧은 유형 부제는 기존대로 GH)."""
    from core.structure.paragraph_kind import _is_group_header
    assert not _is_group_header("(필요시 단어의 형태를 변형하거나 단어 중복 사용 가능)")
    assert _is_group_header("(빈칸, 함축의미)")       # 기존 부제 무회귀
    st3 = _case_steps()["step3"]
    kinds = {}
    for it in (st3.get("normal") or []) + (st3.get("short") or []):
        for p in it.get("paragraphs") or []:
            t = (p.get("text") or "").strip()
            if t.startswith("3. 완전한 문장이") or t.startswith("(필요시"):
                kinds.setdefault(t[:12], set()).add(p.get("kind"))
    assert all(v == {"Cond"} for v in kinds.values()), kinds


# ── 게이트 봉합: 불량 픽스처 소급 검출 (당시 플랜/덤프 실물) ─────────────────

@pytest.fixture(scope="module")
def bad_report():
    plan = json.load(open(os.path.join(
        FIXT, "render_plan_bad_376b34d0.json"), encoding="utf-8"))
    # 재조판 플랜에는 step_map 계약이 target으로 실린다 — 소급 픽스처에도
    # 현행 계약을 주입해 '계약이 있었다면 잡았는가'를 검증
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    smap = TextbookWorkbookV2Engine()._step_map()
    for fl in plan["flows"]:
        ppu = (smap.get(fl["step"]) or {}).get("per_passage_units")
        if ppu:
            fl.setdefault("target", {})["per_passage_units"] = True
    dump = json.load(open(os.path.join(
        FIXT, "typeset_dump_bad_376b34d0.json"), encoding="utf-8"))
    content = json.load(open(os.path.join(CASE, "golden", "content.json"),
                             encoding="utf-8"))
    return inspect_workbook_finish(content, plan, dump)


def test_bad_output_gate_detects_all_seven_families(bad_report):
    crit = bad_report["critical"]

    def has(key, frag=""):
        return any(c.startswith(key) and frag in c for c in crit)

    assert has("[헤더잔존]", "L1-p. 13")                       # 결함 2~4 증상
    assert has("[프레임브레이크]", "지문 분리 미발생")           # 결함 2~4 (G24①)
    assert has("[프레임브레이크]", "헤더 마커 5개 < 지문 6개")   # 결함 1 (G24①b)
    assert has("[출처잔존]", "공통영어2_YBM(김)")               # 결함 5 (G1 확장)
    assert has("[프레임결손]", "p95, p96, p97")                # 결함 6 (G31)
    assert has("[파트경계] 크레딧", "오른쪽 페이지")             # 결함 7 (G28④)


def test_bad_output_g24_lists_three_wordfill_steps(bad_report):
    msg = next(c for c in bad_report["critical"]
               if c.startswith("[프레임브레이크] 지문 분리 미발생"))
    for step in ("step1_c2", "step2_b1", "step2_c1"):
        assert step in msg


# ── 게이트 합성 검증 (양방향) ───────────────────────────────────────────────

_DELETE_PLAN = {"flows": [], "page_cleanup": {"empty": "delete"}}


def _pages(specs):
    return [{"p": p, "m": m, "side": s, "empty": e}
            for p, m, s, e in specs]


def _rep(pages, stories=None, plan=None):
    dump = {"stories": stories or [], "stale_pages": [], "pages": pages}
    return inspect_workbook_finish({"steps": {}}, plan or _DELETE_PLAN, dump)


def test_g28_credit_right_critical():
    pages = _pages([("1", "A-마스터", "R", False), ("2", "O-마스터", "L", False),
                    ("3", "", "R", False)])
    stories = [{"idx": 0, "pg": ["1", "2"], "fp": ["1", "2"],
                "paragraphs": [{"t": "content", "s": ""}]}]
    rep = _rep(pages, stories)
    assert any("크레딧 p3가 오른쪽" in c for c in rep["critical"])


def test_g28_credit_left_last_page_ok():
    """W38 정정 스펙: 크레딧-왼쪽 + 문서 마지막 페이지 = 정상 (책은
    오른쪽 시작, 왼쪽(크레딧) 끝 — W30의 '뒤 메모 필요'는 폐기)."""
    pages = _pages([("1", "A-마스터", "R", False), ("2", "", "L", False)])
    stories = [{"idx": 0, "pg": ["1"], "fp": ["1"],
                "paragraphs": [{"t": "content", "s": ""}]}]
    rep = _rep(pages, stories)
    assert not any("크레딧" in c for c in rep["critical"]), rep["critical"]


def test_g28_credit_trailing_memo_critical():
    """W38 정정 스펙: 크레딧 뒤 오른쪽 메모(M) 페이지 = 위반 (W30 스펙으로
    만든 구출력 6b66b750 [p100 크레딧-L, p101 M-R] 소급 검출)."""
    pages = _pages([("1", "A-마스터", "R", False), ("2", "", "L", False),
                    ("3", "M-마스터", "R", False)])
    stories = [{"idx": 0, "pg": ["1"], "fp": ["1"],
                "paragraphs": [{"t": "content", "s": ""}]}]
    rep = _rep(pages, stories)
    assert any("크레딧" in c and "잔여 페이지" in c for c in rep["critical"]), \
        rep["critical"]
    assert any("M 페이지" in c for c in rep["critical"])


def test_g28_credit_non_delete_downgrades_to_warning():
    pages = _pages([("1", "A-마스터", "R", False), ("2", "O-마스터", "L", False),
                    ("3", "", "R", False)])
    stories = [{"idx": 0, "pg": ["1", "2"], "fp": ["1", "2"],
                "paragraphs": [{"t": "content", "s": ""}]}]
    rep = _rep(pages, stories, plan={"flows": []})
    assert not any("크레딧" in c for c in rep["critical"])
    assert any("크레딧" in w for w in rep["warnings"])


def test_g31_interior_frame_deficit_critical_with_contract():
    pages = _pages([(str(i), "O-마스터", "R" if i % 2 else "L", False)
                    for i in range(1, 6)])
    fp = ["1", "1", "2", "3", "3", "4", "4", "5", "5"]   # p2 결손 (중간)
    stories = [{"idx": 7, "pg": sorted(set(fp), key=int), "fp": fp,
                "paragraphs": [{"t": "x", "s": ""}]}]
    plan = {"flows": [], "page_cleanup": {"empty": "delete"},
            "question_keep": {"flows": {"step3": {"starts": [1]}}}}
    rep = _rep(pages, stories, plan=plan)
    assert any(c.startswith("[프레임결손]") and "p2" in c
               for c in rep["critical"]), rep["critical"]


def test_g31_first_last_page_deficit_allowed():
    """첫/마지막 페이지 결손은 정상(섹션 중간 시작·스레드 절단) — 미발화."""
    pages = _pages([(str(i), "O-마스터", "R" if i % 2 else "L", False)
                    for i in range(1, 5)])
    fp = ["1", "2", "2", "3", "3", "4"]        # 첫·끝 페이지만 1프레임
    stories = [{"idx": 7, "pg": ["1", "2", "3", "4"], "fp": fp,
                "paragraphs": [{"t": "x", "s": ""}]}]
    plan = {"flows": [], "page_cleanup": {"empty": "delete"},
            "question_keep": {"flows": {"step3": {"starts": [1]}}}}
    rep = _rep(pages, stories, plan=plan)
    assert not any(c.startswith("[프레임결손]") for c in rep["critical"])


def test_source_leak_gate_bidirectional():
    dump = {"stories": [{"idx": 0, "pg": ["1"],
                         "paragraphs": [{"t": "공통영어2_YBM(김) 1과_03",
                                         "s": "STEP 03 > 실전 문제 지문"}]}],
            "stale_pages": []}
    rep = inspect_workbook_finish({"steps": {}}, {"flows": []}, dump)
    assert any(c.startswith("[출처잔존]") for c in rep["critical"])
    dump2 = {"stories": [{"idx": 0, "pg": ["1"],
                          "paragraphs": [{"t": "There are things 1과 이야기",
                                          "s": ""}]}], "stale_pages": []}
    rep2 = inspect_workbook_finish({"steps": {}}, {"flows": []}, dump2)
    assert not any(c.startswith("[출처잔존]") for c in rep2["critical"])


# ── 실행기 소스 가드 (round12 test_executor_f2_filler_sources 패턴) ─────────

def test_executor_r15_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    # 결함 6: 다중 프레임 복제 확장
    assert "function framesOfStoryOnPage" in src
    assert "function relBoundsOfFrames" in src
    expand = src.split("function expandStoryOverflow")[1].split(
        "\nfunction ")[0]
    assert "framesOfStoryOnPage(story, lp)" in expand
    assert "relBoundsOfFrames(srcPage, srcFrames)" in expand
    # 결함 7: 크레딧 정렬 op — 페이지 수를 바꾸는 op 이후 1회 호출
    assert "function alignCreditPage" in src
    tail = src.split("wb_v2 question_keep")[1]
    assert "alignCreditPage(doc)" in tail
    assert "wb_v2 credit_align" in tail


# ── 코퍼스 파스 스냅샷 (round3 커스텀 리플레이 패턴) ─────────────────────────

def test_round15_textbook_parse_snapshot(tmp_path):
    import _replay
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    job = str(tmp_path / "job")
    os.makedirs(job)
    for n in os.listdir(os.path.join(CASE, "meta")):
        with open(os.path.join(CASE, "meta", n)) as f:
            val = f.read()
        with open(os.path.join(job, n), "w") as f:
            f.write(val)
    with open(os.path.join(job, "manuscript_folder.txt"), "w") as f:
        f.write(os.path.join(CASE, "inputs_folder"))
    logs = []
    json_path = TextbookWorkbookV2Engine().parse({"manuscripts": []}, job,
                                                 logs.append)
    produced = _replay.canonicalize(
        json.load(open(json_path, encoding="utf-8")), [job])
    golden = _replay.canonicalize(
        json.load(open(os.path.join(CASE, "golden", "content.json"),
                       encoding="utf-8")), [])
    diff = _replay.first_diff(produced, golden)
    assert diff is None, diff
