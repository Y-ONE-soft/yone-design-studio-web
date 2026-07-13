"""W21 — 품질 루프 11라운드 결함 가드 (실사용 1호 결함 8건 전량 수리).

투입 원고: 실서비스 job 0e3108fd — 2026 성덕고 외부지문 워크북1
(workbook_supp_v2, 학교 키 없이 _default 내지 [원본]워크북_C).
코퍼스: tests/corpus/workbook_supp/r11c23ext1 (골든 content.json = job 산출).
진실 기준: 같은 계열의 v1 실물 완제품 워크북03(외부지문)_내지.indd 덤프
(v1 렌더 자체는 '헤더 0개'로 이 결함을 전부 재현 — 실물은 조판사 손마무리
결과. data_corpus/round11/v1_wb03_ext_dump.json).

사용자 지목 결함 → 수리/가드 매핑:
  D1/D3 어휘선택·내용종합 지문번호 [N]에 '어휘선택번호' 스타일
        → build_step1_a1/b2 $BASIC (v1 실물 [기본 단락]) + G23 라벨스타일
  D4    문장배열 발문-주어진 문장 사이 빈 단락
        → build_step1_c1 발문 삽입 후 잔여 빈 단락 제거 + G25 발문빈단락
  D5~D8 빈칸어휘/어법선택/어법OX/빈칸어법 — 프레임 브레이크 미발생 +
        'N. no.M' 헤더 원문 인쇄 → is_header_line/is_a1_header/extract_tail
        무-p형 인식 + G24 프레임브레이크 + G1 헤더잔존
  전체-1 빈 페이지 잔존(빈 STEP3 M 마스터 84p) → page_cleanup delete 모드
        ('M 보존' v1 관행 폐기 확정) + G4 delete 모드 무면제
  전체-2 섹션 우측 시작인데 전부 동일 마스터 → section_masters op
        (A/B·C/D 쌍 — 템플릿 p13 어휘 선택 2 실측) + G26 섹션마스터
  간지   외부지문 원고에 '고1 모의고사' 간지 → G27 간지적합 warning
        (v1 실물도 같은 라벨 유지 관행 — 자동 치환 근거 없음, 사람 확인)

r2(c12/c14 명일 외부지문)가 못 잡은 이유: 그 원고들은 p-형 헤더
("1. p1-no.3과 추가지문")라 무-p형 미인식 경로가 발동하지 않았고,
지문번호 라벨 스타일/발문 빈 단락/마스터·빈 페이지는 게이트 미측정 부류였다.
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
GOLDEN = os.path.join(CORPUS, "workbook_supp", "r11c23ext1", "golden",
                      "content.json")
BAD_DUMP = os.path.join(FIXTURES, "w21_defect_dumps",
                        "typeset_dump_supp_bad_0e3108fd.json")

import pytest

from engines.workbook_v2.plan import (steps_to_plan, unit_paras,
                                      passage_labels, is_header_line,
                                      is_a1_header, extract_tail)
from engines.workbook_supp_v2.engine import (WorkbookSuppV2Engine,
                                             _STEP_MAP)
from engines.workbook_v2.gate import inspect_workbook_finish


@pytest.fixture(scope="module")
def content():
    return json.load(open(GOLDEN, encoding="utf-8"))


@pytest.fixture(scope="module")
def plan(content):
    p = steps_to_plan(content["steps"], workbook_type="모의고사",
                      step_map=_STEP_MAP)
    p["page_cleanup"] = {"empty": "delete"}
    p["section_masters"] = True
    p["divider"] = {"line1": "고1 모의고사", "line2": "25년 10월"}
    p["passage_numbers"] = {"labels": passage_labels(content["steps"]),
                            "steps": ["step1_c2", "step2_b1", "step2_c1"]}
    return p


def _flow(plan, step):
    return next(f for f in plan["flows"] if f["step"] == step)


# ── D5~D8: 무-p형 헤더 'N. no.M' 인식 ───────────────────────────────────────

def test_nop_header_recognizers():
    for h in ("1. no.1", "2. no.2", "17. no.17", "3. no.41~42"):
        assert is_header_line(h), h
        assert is_a1_header(h), h
    assert extract_tail("1. no.1") == "1"
    assert extract_tail("3. no.41~42") == "41~42"
    # 기존 형식 무회귀
    assert is_header_line("1. p2-no.20")
    assert is_header_line("1. p1-no.3과 추가지문")
    assert extract_tail("1. p2-no.20") == "20"
    assert extract_tail("1. p1-no.3과 추가지문") == "3과 추가지문"
    # 본문/발문은 헤더가 아님
    for t in ("1. Developmental psychologists have found",
              "no.1 뒤에 본문이 이어지는 일반 문장 no.2 포함",
              "이 글의 주제로 가장 적절한 것은?"):
        assert not is_header_line(t), t


def test_nop_passage_labels(content):
    assert passage_labels(content["steps"]) == ["1", "2", "3", "4"]


def test_header_steps_split_per_passage(plan):
    """수리 전: c2/a1/b1/c1(어법) 전부 1유닛 통짜 — 프레임 브레이크 0."""
    for step in ("step1_c2", "step2_a1", "step2_b1", "step2_c1"):
        assert len(_flow(plan, step)["units"]) == 4, step
    # 헤더 원문이 플랜에 잔존하지 않음 (a1은 {N} 정규화)
    for step in ("step1_c2", "step2_b1", "step2_c1"):
        for u in _flow(plan, step)["units"]:
            for p in unit_paras(u):
                assert "no.1" not in p["t"] and "no.2" not in p["t"], \
                    (step, p["t"][:40])
    a1_texts = [p["t"] for u in _flow(plan, "step2_a1")["units"]
                for p in unit_paras(u)]
    assert "{1}" in a1_texts and "{4}" in a1_texts


# ── D1/D3: 지문번호 라벨 [N] = [기본 단락] (v1 실물 파리티) ──────────────────

def test_label_bracket_basic_style(plan):
    for step in ("step1_a1", "step1_a1_2", "step1_b2"):
        fl = _flow(plan, step)
        brackets = [p for u in fl["units"] for p in unit_paras(u)
                    if p["t"].strip().startswith("[")
                    and p["t"].strip().endswith("]")]
        assert brackets, step
        assert all(p["s"] == "$BASIC" for p in brackets), step


# ── D4: 발문-주어진 문장 사이 빈 단락 제거 ───────────────────────────────────

def test_c1_prompt_adjacent_to_btm(plan):
    fl = _flow(plan, "step1_c1")
    found = 0
    for u in fl["units"]:
        ps = unit_paras(u)
        for i, p in enumerate(ps):
            if (p["s"] or "").endswith("하단 문제"):
                found += 1
                nxt = ps[i + 1]
                assert nxt["t"].strip(), (p["t"][:30], "다음이 빈 단락")
                assert "하단" in nxt["s"], nxt["s"]
    assert found == 4


# ── 전체-1/전체-2: supp 데코 (delete 모드 + 섹션 마스터 op) ──────────────────

def test_supp_default_template_decorations(content, tmp_path):
    job = str(tmp_path)
    with open(os.path.join(job, "content.json"), "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["page_cleanup"] == {"empty": "delete"}
    assert deco["section_masters"] is True


def test_step_map_contracts():
    """계약 키가 target으로 플랜에 실린다 (게이트/실행기 소비)."""
    for step in ("step1_a1", "step1_a1_2", "step1_b2"):
        assert _STEP_MAP[step]["label_contract"]["style"] == "$BASIC"
    for step in ("step1_c2", "step2_a1", "step2_b1", "step2_c1"):
        assert _STEP_MAP[step]["per_passage_units"] is True
    assert _STEP_MAP["step1_c2"]["master_pair"] == \
        {"left": "A-마스터", "right": "B-마스터"}
    assert _STEP_MAP["step2_c1"]["master_pair"] == \
        {"left": "C-마스터", "right": "D-마스터"}
    assert "master_pair" not in _STEP_MAP["step3"]


def test_executor_has_w21_ops():
    src = open(os.path.join(os.path.dirname(TESTS_DIR), "core", "jsx",
                            "workbook_flow.body.jsx"), encoding="utf-8").read()
    assert "fixSectionMasters" in src
    assert 'op.empty === "delete"' in src
    assert "plan.section_masters" in src
    # 비대면 문서 좌/우 판정 — pg.side 단독 사용 금지 (전부 RIGHT_HAND 실측)
    assert "documentOffset % 2" in src


def test_dump_jsx_has_w21_fields():
    src = open(os.path.join(os.path.dirname(TESTS_DIR), "core", "jsx",
                            "dump_stories.jsx"), encoding="utf-8").read()
    assert '\\"fc\\":' in src.replace("'", '"') or '"fc":' in src
    assert '"pages":' in src or 'pages' in src
    assert "documentOffset % 2" in src


# ── 게이트: 기존 불량 출력(0e3108fd)에서 사용자 지목 8건 전량 검출 ──────────

BAD_PLAN = os.path.join(FIXTURES, "w21_defect_dumps",
                        "render_plan_supp_bad_0e3108fd.json")


@pytest.fixture(scope="module")
def bad_report(content):
    """불량 출력 당시의 플랜(0e3108fd 원본 — c2/a1/b1/c1 1유닛 통짜) +
    현행 step_map 계약 주입 + 확정 정책 op — '게이트가 그때 있었다면'
    사용자 지목 8건을 전부 검출했는지의 소급 실증."""
    dump = json.load(open(BAD_DUMP, encoding="utf-8"))
    plan = json.load(open(BAD_PLAN, encoding="utf-8"))
    for fl in plan["flows"]:
        smap = _STEP_MAP.get(fl["step"]) or {}
        for k in ("label_contract", "per_passage_units", "master_pair"):
            if k in smap:
                fl.setdefault("target", {})[k] = smap[k]
    plan["page_cleanup"] = {"empty": "delete"}
    plan["section_masters"] = True
    return inspect_workbook_finish(content, plan, dump)


def test_gate_detects_user_defects(bad_report):
    rep = bad_report
    assert not rep["ok"]
    kinds = [c.split("]")[0] + "]" for c in rep["critical"]]
    assert "[헤더잔존]" in kinds        # D5~D8 (헤더 원문 인쇄)
    assert "[라벨스타일]" in kinds      # D1/D3
    assert "[프레임브레이크]" in kinds  # D5~D8 (지문 분리 미발생)
    assert "[발문빈단락]" in kinds      # D4
    assert "[잔여페이지]" in kinds      # 전체-1 (M 페이지 84 — 무면제)
    assert "[섹션마스터]" in kinds      # 전체-2
    assert rep["stats"]["header_leaks"] == 16
    assert rep["stats"]["label_style_bad"] == 12
    assert rep["stats"]["frame_break_plan_fail"] == 4
    assert rep["stats"]["prompt_gap_blanks"] == 4
    # 84 (M 마스터 빈 STEP3) + 2 (stale 판정 밖 빈 페이지 — pages 인벤토리)
    assert rep["stats"]["stale_pages"] == 86
    assert rep["stats"]["section_master_bad"] >= 5


def test_gate_divider_type_warning(bad_report):
    # 간지: 외부지문 원고 + '고1 모의고사' 라벨 → warning (v1 실물 관행상
    # 자동 치환 금지 — 사람 확인 지목)
    assert any("[간지적합]" in w for w in bad_report["warnings"])
    assert bad_report["stats"].get("divider_type_mismatch") == 3


def test_gate_g2_step3_answer_rows_kept(bad_report):
    """step3 말미 압축 정답표(플랜 보존분)는 critical 아님 — v1 실물
    (워크북03(외부지문) 스토리 53)도 지문 스타일로 유지하는 관행."""
    assert bad_report["stats"].get("answer_rows_step3_kept") == 6
    assert not any("[정답잔존]" in c for c in bad_report["critical"])


def test_gate_g2_marker_answer_rows_still_critical():
    """플랜에 없는 정답표 행(파서가 잘라야 했던 '정답' 블록 잔존 —
    06f4b2c2 계열)은 여전히 critical."""
    plan = {"flows": [{"step": "step3", "target": {"master": "O"},
                       "units": [[{"t": "문항 본문 paragraph one", "s": "S"}]]}]}
    dump = {"stories": [{"idx": 0, "pg": ["188"], "overflow": False,
                         "paragraphs": [
                             {"t": "문항 본문 paragraph one\r", "s": "S"},
                             {"t": "1. ①   2. ②   3. ⑤\r", "s": "S"}]}],
            "stale_pages": []}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump)
    assert any("[정답잔존]" in c for c in rep["critical"])


def test_gate_g24_frame_break_measured():
    """G24② — fc(프레임 첫 문자 인덱스) 실측: 유닛 시작이 프레임 경계에
    없으면 critical, 경계에 있으면 통과."""
    flow = {"step": "step1_c2", "target": {}, "break_per_unit": True,
            "units": [[{"t": "alpha bravo charlie one", "s": "P"}],
                      [{"t": "delta echo foxtrot two", "s": "P"}]]}
    plan = {"flows": [flow]}
    paras = [{"t": "alpha bravo charlie one\r", "s": "P"},
             {"t": "delta echo foxtrot two\r", "s": "P"}]
    # 경계 미존재 (프레임 1개, fc=[0]) → critical
    dump_bad = {"stories": [{"idx": 0, "pg": ["94"], "fc": [0],
                             "overflow": False, "paragraphs": paras}],
                "stale_pages": []}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump_bad)
    assert any("[프레임브레이크]" in c and "경계" in c
               for c in rep["critical"])
    # 두 번째 유닛 시작(offset 24)이 프레임 시작 → 통과
    dump_ok = {"stories": [{"idx": 0, "pg": ["94", "95"], "fc": [0, 24],
                            "overflow": False, "paragraphs": paras}],
               "stale_pages": []}
    rep2 = inspect_workbook_finish({"steps": {}}, plan, dump_ok)
    assert not any("[프레임브레이크]" in c for c in rep2["critical"])


def test_gate_g26_section_master():
    flow = {"step": "step1_b1", "break_per_unit": True,
            "target": {"master_pair": {"left": "A-마스터",
                                       "right": "B-마스터"}},
            "units": [[{"t": "golf hotel india juliet kilo", "s": "P"}]]}
    plan = {"flows": [flow], "section_masters": True}
    story = {"idx": 0, "pg": ["13"], "overflow": False,
             "paragraphs": [{"t": "golf hotel india juliet kilo\r",
                             "s": "P"}]}
    dump = {"stories": [story], "stale_pages": [],
            "pages": [{"p": "13", "m": "A-마스터", "side": "R",
                       "empty": False}]}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump)
    assert any("[섹션마스터]" in c for c in rep["critical"])
    dump["pages"][0]["m"] = "B-마스터"
    rep2 = inspect_workbook_finish({"steps": {}}, plan, dump)
    assert not any("[섹션마스터]" in c for c in rep2["critical"])
    # op 미사용 플랜은 warning 강등
    plan2 = {"flows": [flow]}
    dump["pages"][0]["m"] = "A-마스터"
    rep3 = inspect_workbook_finish({"steps": {}}, plan2, dump)
    assert not any("[섹션마스터]" in c for c in rep3["critical"])
    assert any("[섹션마스터]" in w for w in rep3["warnings"])


def test_gate_clean_plan_dump_passes(content, plan):
    """수리 후 상태를 모사한 합성 덤프(프레임 경계/마스터 정합 포함)는
    critical 0."""
    from engines.workbook_v2.plan import STEP_MAP  # noqa: F401 (계약 무관)
    stories = []
    pages = []
    page_no = 4
    for fl in plan["flows"]:
        paras = []
        fc = []
        off = 0
        for u in fl["units"]:
            fc.append(off)
            for p in unit_paras(u):
                t = p["t"] + "\r"
                paras.append({"t": t, "s": p["s"] or ""})
                off += len(t)
        pgs = [str(page_no)]
        pair = (fl.get("target") or {}).get("master_pair")
        side = "R" if page_no % 2 == 1 else "L"
        if pair:
            pages.append({"p": str(page_no),
                          "m": pair["right" if side == "R" else "left"],
                          "side": side, "empty": False})
        stories.append({"idx": len(stories), "overflow": False, "pg": pgs,
                        "fc": fc, "b": [31, 20], "paragraphs": paras})
        page_no += 2
    # 상/하단 기하 (G5)
    for fl, b in (("step2_a1", [31, 20]), ("step2_a1_btm", [164, 20])):
        probe = max((p["t"] for u in _flow(plan, fl)["units"]
                     for p in unit_paras(u)), key=len)
        for st in stories:
            if any(probe == p["t"].rstrip("\r") for p in st["paragraphs"]):
                st["b"] = b
                st["pg"] = ["114"]
    # 갱신된 지문번호 프레임 — 콘텐츠(c2 스토리)가 있는 페이지에 배치
    c2_probe = max((p["t"] for u in _flow(plan, "step1_c2")["units"]
                    for p in unit_paras(u)), key=len)
    c2_pg = next(st["pg"] for st in stories
                 if any(p["t"].rstrip("\r") == c2_probe
                        for p in st["paragraphs"]))
    for lb in plan["passage_numbers"]["labels"]:
        stories.append({"idx": len(stories), "overflow": False,
                        "pg": list(c2_pg), "b": [32, 10], "fc": [0],
                        "paragraphs": [{"t": lb + "\r", "s": "[기본 단락]"}]})
    dump = {"doc": "x", "stories": stories, "overflow_stories": 0,
            "page_count": page_no, "pages": pages, "stale_pages": []}
    rep = inspect_workbook_finish(content, plan, dump)
    assert rep["critical"] == [], rep["critical"]
    # 간지적합은 warning으로만 남는다 (외부지문 + 모의고사 라벨 detect는
    # 간지 스토리가 덤프에 있을 때만 — 합성 덤프엔 간지 없음 → 0)
    assert rep["stats"].get("divider_type_mismatch") in (None, 0)
