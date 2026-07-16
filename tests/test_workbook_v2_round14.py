"""품질 루프 14라운드 (W24) 가드 — 간지 두 줄 분리 입력 + 자동 문구 통일
+ 완제품 레이아웃 정책(delete/section_masters/question_keep)의 계열 확산.

과제 1 (사용자 확정 스펙 — 간지 입력·문구):
  - 간지는 line1(교재유형) + line2(디테일 범위) 두 줄 구조 — supp 업로드
    폼을 divider_line1/divider_line2 두 필드(둘 다 선택)로 분리. 기존
    단일 divider_text는 하위호환 (있으면 line1로 소비).
  - 자동 판정 표기 '추가지문' → '외부지문' 통일 ('N과 추가지문' 감지
    시에도 표기는 '외부지문'). 게이트 G27 확장: source=type +
    line1='추가지문' = 구 판정 사다리 잔존 플랜 critical.

과제 2 (계열 확산 — 실기 1건 검증 후 활성):
  - supp에서 검증된 3종 op(page_cleanup delete / section_masters /
    question_keep)를 교과서·EBS·수능특강 계열로 확산.
  - 활성 안 한 계열(본가/세로)은 플랜 무변경 (무회귀 가드).
"""
import copy
import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
W23_DUMP = os.path.join(FIXTURES, "w23_defect_dumps",
                        "typeset_dump_supp_bad_6c1430c3.json")
W23_PLAN = os.path.join(FIXTURES, "w23_defect_dumps",
                        "render_plan_supp_bad_6c1430c3.json")
GOLDEN_SUPP = os.path.join(TESTS_DIR, "corpus", "workbook_supp",
                           "r13c24addu", "golden", "content.json")

from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine


@pytest.fixture(scope="module")
def content():
    return json.load(open(GOLDEN_SUPP, encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_dump():
    return json.load(open(W23_DUMP, encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_plan():
    return json.load(open(W23_PLAN, encoding="utf-8"))


def _mk_job(tmp_path, content_obj, uploads=(), meta=None):
    job = str(tmp_path)
    json.dump(content_obj, open(os.path.join(job, "content.json"), "w",
                                encoding="utf-8"), ensure_ascii=False)
    up = os.path.join(job, "uploads")
    os.makedirs(up, exist_ok=True)
    for n in uploads:
        open(os.path.join(up, n), "w").close()
    for k, v in (meta or {}).items():
        open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8").write(v)
    return job


# ── 과제 1: 간지 두 줄 분리 입력 ─────────────────────────────────────────────

def test_supp_divider_two_lines_user(content, tmp_path):
    """line1+line2 입력 → 둘 다 사용자 문구, source=user."""
    job = _mk_job(tmp_path, content,
                  meta={"divider_line1": "외부지문",
                        "divider_line2": "Unit.3 추가지문"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "외부지문",
                               "line2": "Unit.3 추가지문", "source": "user"}


def test_supp_divider_line2_only_keeps_auto_line1(content, tmp_path):
    """line2만 입력 → line1은 자동 판정(source=type — G27 '모의고사' 금지
    계약 유지), line2는 사용자 문구."""
    job = _mk_job(tmp_path, content, meta={"divider_line2": "Unit.3"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "외부지문", "line2": "Unit.3",
                               "source": "type"}


def test_supp_divider_legacy_text_as_line1(content, tmp_path):
    """W22 단일 divider_text 하위호환 — 있으면 line1로 소비 (line2 병용
    가능). divider_line1이 있으면 그쪽이 우선."""
    job = _mk_job(tmp_path, content, meta={"divider_text": "성덕고 워크북",
                                           "divider_line2": "3과"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "성덕고 워크북", "line2": "3과",
                               "source": "user"}


def test_supp_divider_line1_wins_over_legacy(content, tmp_path):
    job = _mk_job(tmp_path, content, meta={"divider_text": "구문구",
                                           "divider_line1": "새문구"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"]["line1"] == "새문구"
    assert deco["divider"]["source"] == "user"


def test_supp_upload_spec_two_line_slots():
    """upload_spec: divider_line1/divider_line2 두 텍스트 슬롯 + 하위호환
    divider_text 슬롯 (라우트 슬롯 처리 재사용 — 새 라우트 없음)."""
    spec = WorkbookSuppV2Engine().upload_spec
    keys = [s["key"] for s in spec["slots"]]
    assert "divider_line1" in keys and "divider_line2" in keys
    assert "divider_text" in keys      # 하위호환
    assert keys[0] == "manuscripts"    # 파일 슬롯 무변경


def test_supp_template_two_line_fields():
    html = open(os.path.join(REPO, "templates",
                             "typeset_workbook_supp_v2.html"),
                encoding="utf-8").read()
    assert 'name="divider_line1"' in html
    assert 'name="divider_line2"' in html
    # 단일 필드는 폼에서 제거 (슬롯 하위호환만 유지)
    assert 'name="divider_text"' not in html


# ── 과제 1: 자동 문구 '추가지문' → '외부지문' + G27 확장 ─────────────────────

def test_supp_addu_header_auto_label_is_ext(content, tmp_path):
    """'[N과 추가지문]' 헤더 원고의 자동 판정 표기 = '외부지문' (r14)."""
    job = _mk_job(tmp_path, content)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"]["line1"] == "외부지문"
    assert deco["divider"]["source"] == "type"


def test_gate_g27_addu_auto_label_critical(bad_plan, bad_dump, content):
    """source=type + line1='추가지문' = 구 판정 사다리(r13 ③) 잔존 플랜
    critical — 자동 표기는 '외부지문'이 계약 (r14)."""
    plan = copy.deepcopy(bad_plan)
    plan["divider"] = {"line1": "추가지문", "line2": "", "source": "type"}
    rep = inspect_workbook_finish(content, plan, bad_dump)
    assert any("'추가지문'" in c and "외부지문" in c
               for c in rep["critical"]), rep["critical"]


def test_gate_g27_addu_user_label_ok(bad_plan, bad_dump, content):
    """사용자가 직접 '추가지문'을 입력(source=user)한 것은 계약 위반이
    아니다."""
    plan = copy.deepcopy(bad_plan)
    plan["divider"] = {"line1": "추가지문", "line2": "", "source": "user"}
    rep = inspect_workbook_finish(content, plan, bad_dump)
    assert not any("자동 판정 표기가" in c for c in rep["critical"])
