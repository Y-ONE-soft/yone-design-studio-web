"""W22 — 품질 루프 12라운드 결함 가드 (실사용 2차 피드백 3건).

투입: W21 재조판본 data_corpus/round11/out/워크북1_내지_v2_2.pdf(62p —
성덕고 외부지문 워크북1, workbook_supp_v2)의 사용자 검토 피드백. 원고는
r11c23ext1 그대로 (파서 무변경 — 출력/게이트 계층 수리).
불량 픽스처: tests/fixtures/w22_defect_dumps/ (W21 재조판본의 덤프/플랜 —
이 출력이 W21 게이트를 '전부 통과'했으므로 아래 3건은 게이트 구멍이었다).

피드백 → 원인/수리/가드 매핑:
  F1 p34 어법선택 빈 페이지가 삭제 안 됨 — 페이지마다 얹히는 반복 장식
     (어법선택 발문 "다음 밑줄 친 부분 중 어법상 틀린 것은?" 단일 프레임)이
     '텍스트 있음'으로 delete 모드 삭제 판정과 덤프 empty 판정을 모두
     비껴감. p47 영작배열 섹션 탭(' 영작 배열')도 동일 기전.
     → 실행기 cleanupPages: 플로우 콘텐츠 페이지에서 장식 텍스트 수집
       (furnKeyOf/furn) 후 같은 텍스트만 남은 페이지를 빈 페이지로 판정
     → 게이트 G4 확장: 장식-빈 페이지를 delete 모드 잔여로 합산
  F2 파트 경계 오른쪽 채움 페이지(예: p47)는 삭제가 아니라 M(메모) 마스터 —
     간지 스프레드 = 왼쪽 빈 페이지 + 오른쪽 라벨 실측([원본]워크북_C).
     페이지 삭제로 라벨이 왼쪽으로 밀리면 간지 앞에 M 채움 페이지 삽입.
     → 실행기 alignPartFillers (delete 모드 cleanupPages가 호출)
     → 게이트 G28 파트경계 (라벨 좌측 = 채움 누락 / M 페이지 위치 검증)
  F3 간지 내용 교재별 설정 (사용자 확정 스펙, supp 계열 한정): 업로드 시
     간지 문구 입력 필드 — 입력하면 그 문구, 미입력이면 교재유형만 표기
     (예: '외부지문'). '고N 모의고사/25년 10월'은 supp 폼이 년/월을 받지
     않아 엔진 기본값이 찍히던 잔재 — 폐기.
     → upload_spec divider_text 텍스트 슬롯(라우트 무변경 — 기존 슬롯
       처리 재사용) + _divider_deco + G27 스펙 갱신 (source 계약 시
       모의고사 잔재/기대 문구 불일치 = critical)
"""
import copy
import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
W22_DUMP = os.path.join(FIXTURES, "w22_defect_dumps",
                        "typeset_dump_supp_w21out_0e3108fd.json")
W22_PLAN = os.path.join(FIXTURES, "w22_defect_dumps",
                        "render_plan_supp_w21out_0e3108fd.json")
GOLDEN = os.path.join(TESTS_DIR, "corpus", "workbook_supp", "r11c23ext1",
                      "golden", "content.json")

from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine


@pytest.fixture(scope="module")
def content():
    return json.load(open(GOLDEN, encoding="utf-8"))


@pytest.fixture(scope="module")
def w21_dump():
    return json.load(open(W22_DUMP, encoding="utf-8"))


@pytest.fixture(scope="module")
def w21_plan():
    return json.load(open(W22_PLAN, encoding="utf-8"))


@pytest.fixture(scope="module")
def w21_report(content, w21_dump, w21_plan):
    """W21 재조판본 그대로 (당시 플랜 — divider source 계약 없음)."""
    return inspect_workbook_finish(content, w21_plan, w21_dump)


# ── F1: 게이트 G4 확장 — 장식-빈 페이지 소급 검출 ────────────────────────────

def test_gate_g4_detects_p34_p47(w21_report):
    """W21 게이트를 통과했던 출력에서 사용자 지목 p34(어법선택 발문 잔존) +
    p47(영작배열 탭 잔존)을 critical로 검출한다 — 게이트 구멍의 폐쇄."""
    stale = [c for c in w21_report["critical"] if c.startswith("[잔여페이지]")]
    assert stale, w21_report["critical"]
    assert "p34" in stale[0] and "p47" in stale[0], stale[0]
    assert w21_report["stats"]["stale_pages"] == 2


def test_gate_g4_furniture_synthetic():
    """장식 판정 양방향: 콘텐츠 페이지에서 수집된 반복 장식만 남은 페이지는
    잔여, 수집되지 않은 고유 텍스트(간지류) 페이지는 보존."""
    plan = {"flows": [{"step": "step2_a1", "target": {},
                       "units": [[{"t": "alpha bravo charlie delta echo",
                                   "s": "P"}]]}],
            "page_cleanup": {"empty": "delete"}}
    furn_t = " 다음 밑줄 친 부분 중 어법상 틀린 것은?\r"
    stories = [
        {"idx": 0, "pg": ["30"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": "alpha bravo charlie delta echo\r", "s": "P"}]},
        {"idx": 1, "pg": ["30"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": furn_t, "s": "Q"}]},       # 콘텐츠 페이지 장식
        {"idx": 2, "pg": ["31"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": furn_t, "s": "Q"}]},       # 잔여 페이지 장식
        {"idx": 3, "pg": ["31"], "fc": [-1], "overflow": False,
         "paragraphs": [{"t": "", "s": ""}]},            # 절단 잔여 빈 프레임
        {"idx": 4, "pg": ["32"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": "여기만 있는 고유 안내 문구\r", "s": "Q"}]},
    ]
    pages = [{"p": p, "m": "C-마스터", "side": s, "empty": False}
             for p, s in (("30", "L"), ("31", "R"), ("32", "L"))]
    dump = {"doc": "x", "stories": stories, "overflow_stories": 0,
            "page_count": 3, "pages": pages, "stale_pages": []}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump)
    stale = [c for c in rep["critical"] if c.startswith("[잔여페이지]")]
    assert stale and "p31" in stale[0], rep["critical"]
    assert "p32" not in stale[0]          # 고유 텍스트 페이지는 보존
    assert "p30" not in stale[0]          # 콘텐츠 페이지는 보존
    # delete 모드가 아니면 장식 판정 미적용 (기존 M 모드 동작 무변경)
    plan_m = dict(plan, page_cleanup={"empty_master": "M"})
    rep_m = inspect_workbook_finish({"steps": {}}, plan_m, dump)
    assert not [c for c in rep_m["critical"] if c.startswith("[잔여페이지]")]


def test_executor_f1_furniture_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function furnKeyOf" in src
    body = src.split("function cleanupPages")[1].split("\nfunction ")[0]
    assert "furnKeyOf" in body            # 장식 수집 + 프레임 판정
    assert "frameFurn" in body
    # 장식 판정은 delete 모드 한정 (기존 M 모드 동작 무변경)
    assert "deleteEmpty && !frameBlank" in body


# ── F2: 파트 경계 채움 페이지 (M 마스터) ─────────────────────────────────────

def _boundary_dump(pages, label_pg):
    stories = [
        {"idx": 0, "pg": [label_pg], "fc": [0], "overflow": False,
         "paragraphs": [{"t": "외부지문\r", "s": "L"}, {"t": "\r", "s": "L"}]},
    ]
    return {"doc": "x", "stories": stories, "overflow_stories": 0,
            "page_count": len(pages), "pages": pages, "stale_pages": []}


_BOUNDARY_PLAN = {"flows": [], "page_cleanup": {"empty": "delete"},
                  "section_masters": True,
                  "divider": {"line1": "외부지문", "line2": "",
                              "source": "type"}}


def test_gate_g28_label_left_missing_filler():
    pages = [{"p": "46", "m": "", "side": "L", "empty": False},
             {"p": "47", "m": "", "side": "R", "empty": False}]
    rep = inspect_workbook_finish({"steps": {}}, _BOUNDARY_PLAN,
                                  _boundary_dump(pages, "46"))
    bad = [c for c in rep["critical"] if c.startswith("[파트경계]")]
    assert bad and "왼쪽 페이지" in bad[0], rep["critical"]


def test_gate_g28_filler_ok():
    """정상 배치: 콘텐츠(L 끝) → M 채움(R) → 간지 왼쪽 빈(L) → 라벨(R)."""
    pages = [{"p": "46", "m": "M-마스터", "side": "R", "empty": False},
             {"p": "47", "m": "", "side": "L", "empty": False},
             {"p": "48", "m": "", "side": "R", "empty": False}]
    rep = inspect_workbook_finish({"steps": {}}, _BOUNDARY_PLAN,
                                  _boundary_dump(pages, "48"))
    assert not [c for c in rep["critical"] if c.startswith("[파트경계]")]
    assert rep["stats"].get("part_boundary_bad") == 0


def test_gate_g28_stray_m_page():
    """delete 모드의 M 페이지는 간지 직전 오른쪽 채움만 허용 — 그 외 위치는
    빈 페이지 잔재 (W21 '완전 정리' 정책)."""
    pages = [{"p": "40", "m": "M-마스터", "side": "L", "empty": False},
             {"p": "41", "m": "C-마스터", "side": "R", "empty": False},
             {"p": "42", "m": "", "side": "L", "empty": False},
             {"p": "43", "m": "", "side": "R", "empty": False}]
    rep = inspect_workbook_finish({"steps": {}}, _BOUNDARY_PLAN,
                                  _boundary_dump(pages, "43"))
    bad = [c for c in rep["critical"] if c.startswith("[파트경계]")]
    assert bad and "M 페이지 p40" in bad[0], rep["critical"]


def test_gate_g28_non_delete_mode_warning():
    """delete 모드가 아니면 warning 강등 (구출력/타 계열 소급 — v1 실물도
    밀린 간지를 방치한 관행이라 critical 소급은 과함)."""
    pages = [{"p": "46", "m": "", "side": "L", "empty": False}]
    plan = {"flows": [], "divider": {"line1": "외부지문", "line2": "",
                                     "source": "type"}}
    rep = inspect_workbook_finish({"steps": {}}, plan,
                                  _boundary_dump(pages, "46"))
    assert not [c for c in rep["critical"] if c.startswith("[파트경계]")]
    assert [w for w in rep["warnings"] if w.startswith("[파트경계]")]


def test_gate_g28_w21_output_labels_aligned(w21_report):
    """W21 재조판본의 간지 라벨(p3/p29/p49)은 전부 오른쪽 — 파트경계 무결
    (p47 잔존이 '우연히' 정렬을 지켰던 상태. 삭제 후에는 M 채움이 계약).
    W23 r13 의미론 갱신: 짤지문 고아 간지(p61 — 뒤따르는 콘텐츠 없음)는
    G28③이 새로 소급 검출한다 (r13 F2, 당시엔 게이트 구멍). 정렬(왼쪽
    라벨/M 위치) 계열 무결만 이 테스트의 원래 검증 대상으로 유지."""
    align = [c for c in w21_report["critical"]
             if c.startswith("[파트경계]") and "고아 간지" not in c
             and "크레딧" not in c]
    assert not align
    orphan = [c for c in w21_report["critical"] if "고아 간지" in c]
    assert orphan and "짤지문" not in orphan[0]  # 라벨 첫 줄('고2 모의고사')로 지목
    # W38 의미론 재정정: 사용자 확정 스펙은 '크레딧 왼쪽 + 문서 마지막
    # 페이지' (W30의 '오른쪽 메모 필요'는 잘못된 스펙으로 폐기) —
    # 구출력(p62 크레딧 왼쪽, 마지막)은 이제 스펙 그대로 = 무결.
    credit = [c for c in w21_report["critical"] if "크레딧" in c]
    assert not credit, credit


def test_executor_f2_filler_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function alignPartFillers" in src
    assert "function pageSideOf" in src
    assert "function isDividerLabelPage" in src
    # 프로브 추출 마커 (scripts/e2e_round12_filler_probe.py가 소비)
    assert "[W22 파트경계 유틸 시작]" in src
    assert "[W22 파트경계 유틸 끝]" in src
    # delete 모드의 cleanupPages가 호출
    body = src.split("function cleanupPages")[1].split("\nfunction ")[0]
    assert "alignPartFillers(doc)" in body


# ── F3: 간지 문구 스펙 (supp 계열) ───────────────────────────────────────────

def test_supp_upload_spec_divider_text():
    """W24 r14 의미론 갱신: 간지 입력이 두 필드(line1/line2)로 분리 —
    W22 단일 divider_text 슬롯은 하위호환으로 유지 (line1로 소비)."""
    spec = WorkbookSuppV2Engine().upload_spec
    for key in ("divider_line1", "divider_line2", "divider_text"):
        slot = next(s for s in spec["slots"] if s["key"] == key)
        assert slot.get("type") == "text"
        assert not slot.get("required")
    # 파일 슬롯은 그대로 (라우트/폼 처리 무변경)
    assert [s["key"] for s in spec["slots"]][0] == "manuscripts"


def test_supp_divider_deco_type_nop(content, tmp_path):
    """미입력 + 외부지문(무-p형 'N. no.M' 헤더) 원고 → '외부지문'."""
    job = str(tmp_path)
    json.dump(content, open(os.path.join(job, "content.json"), "w",
                            encoding="utf-8"), ensure_ascii=False)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "외부지문", "line2": "",
                               "source": "type"}


def test_supp_divider_deco_user_text(content, tmp_path):
    """간지 문구 입력 시 그 문구가 우선한다."""
    job = str(tmp_path)
    json.dump(content, open(os.path.join(job, "content.json"), "w",
                            encoding="utf-8"), ensure_ascii=False)
    open(os.path.join(job, "divider_text.txt"), "w",
         encoding="utf-8").write("성덕고 영어 워크북")
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "성덕고 영어 워크북", "line2": "",
                               "source": "user"}


def test_supp_divider_deco_type_fallback(tmp_path):
    """미입력 + 유형 신호 없는 원고 → 중립 '부교재' — 년/월 잔재 없음.
    W23 r13 의미론 갱신 (F1 — 사용자 확정): 기존 폴백 '모의고사'(메타
    기본값)는 supp에서 어떤 경우에도 자동으로 나가면 안 된다 (6c1430c3
    실사용 결함 — 게이트 G27이 critical로 계약 감시)."""
    job = str(tmp_path)
    json.dump({"grade": 1, "year": 25, "month": 10,
               "steps": {"step1_a1": {"paragraphs":
                                      [{"text": "1. p2-no.20"}]}}},
              open(os.path.join(job, "content.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "부교재", "line2": "",
                               "source": "type"}


def test_supp_template_has_divider_field():
    """W24 r14 의미론 갱신: 폼은 두 줄 분리 입력 노출 (divider_text 단일
    필드는 폼에서 제거 — 슬롯 하위호환만 유지)."""
    html = open(os.path.join(REPO, "templates",
                             "typeset_workbook_supp_v2.html"),
                encoding="utf-8").read()
    assert 'name="divider_line1"' in html
    assert 'name="divider_line2"' in html


# ── F3: 게이트 G27 스펙 갱신 ────────────────────────────────────────────────

def _supp_plan(w21_plan, line1="외부지문", source="type"):
    plan = copy.deepcopy(w21_plan)
    plan["divider"] = {"line1": line1, "line2": "", "source": source}
    return plan


def test_gate_g27_mock_residue_critical(content, w21_dump, w21_plan):
    """supp divider 계약이 있는데 출력에 '고1 모의고사/25년 10월' 잔재 —
    critical (W21 출력이 이 상태: p3/p29/p49)."""
    rep = inspect_workbook_finish(content, _supp_plan(w21_plan), w21_dump)
    bad = [c for c in rep["critical"] if c.startswith("[간지적합]")]
    assert bad and "잔재" in bad[0], rep["critical"]
    assert rep["stats"]["divider_type_mismatch"] == 3


def _replace_labels(dump, new_line1):
    d = copy.deepcopy(dump)
    n = 0
    for s in d["stories"]:
        ps = s.get("paragraphs", [])
        if len(ps) >= 2 and ps[0]["t"].startswith("고1 모의고사"):
            ps[0]["t"] = new_line1 + "\r"
            ps[1]["t"] = "\r"
            n += 1
    assert n == 3
    return d


def test_gate_g27_updated_label_ok(content, w21_dump, w21_plan):
    """간지 3개(p3/p29/p49)가 기대 문구로 갱신된 출력 — 간지적합 clean."""
    rep = inspect_workbook_finish(content, _supp_plan(w21_plan),
                                  _replace_labels(w21_dump, "외부지문"))
    assert not [c for c in rep["critical"] if c.startswith("[간지적합]")]
    assert not [w for w in rep["warnings"] if w.startswith("[간지적합]")]
    assert rep["stats"].get("divider_label_wrong") == 0


def test_gate_g27_wrong_label_critical(content, w21_dump, w21_plan):
    """간지가 기대 문구가 아닌 다른 문구로 갱신됨 — critical."""
    rep = inspect_workbook_finish(content,
                                  _supp_plan(w21_plan, "성덕고 워크북",
                                             source="user"),
                                  _replace_labels(w21_dump, "외부지문"))
    bad = [c for c in rep["critical"] if c.startswith("[간지적합]")]
    assert bad and "불일치" in bad[0], rep["critical"]


def test_gate_g27_legacy_warning_unchanged(w21_report):
    """source 계약 없는 플랜(W21 당시 출력)은 기존 W21 동작 유지 —
    외부지문 원고 + 모의고사 라벨 → warning (사람 확인 지목)."""
    assert not [c for c in w21_report["critical"]
                if c.startswith("[간지적합]")]
    assert [w for w in w21_report["warnings"] if w.startswith("[간지적합]")]
    assert w21_report["stats"]["divider_type_mismatch"] == 3


# ── 무회귀: 본가(모의고사) divider 기존 동작 유지 ────────────────────────────

def test_mockexam_divider_unchanged(tmp_path):
    """c04(고2 25-6)/c20(고2 25-3) 골든 content로 본가 데코 재빌드 —
    '고N 모의고사 / YY년 M월' 그대로 (supp만 스펙 변경)."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    cases = [("r5c04mock211", "고2 모의고사", "25년 6월"),
             ("r9c20mock2503", "고2 모의고사", "25년 3월")]
    for name, l1, l2 in cases:
        golden = os.path.join(TESTS_DIR, "corpus", "workbook_v2", name,
                              "golden", "content.json")
        cont = json.load(open(golden, encoding="utf-8"))
        job = os.path.join(str(tmp_path), name)
        os.makedirs(job, exist_ok=True)
        json.dump(cont, open(os.path.join(job, "content.json"), "w",
                             encoding="utf-8"), ensure_ascii=False)
        deco = WorkbookV2Engine()._plan_decorations(job, {})
        assert deco["divider"] == {"line1": l1, "line2": l2}, name
