"""W23 — 품질 루프 13라운드 결함 가드 (실사용 3차 피드백 4건).

투입: 실서비스 job 6c1430c3 (공통영어1 능률(민) Unit.3 추가지문 워크북,
workbook_supp_v2 — 출력 워크북1_내지_v2_4.indd 36p)의 사용자 피드백 4건.
불량 픽스처: tests/fixtures/w23_defect_dumps/ — 불량 출력 실물을 W23 확장
덤프(fp/fonts/style_fonts)로 재덤프한 것 + 당시 플랜. 코퍼스:
tests/corpus/workbook_supp/r13c24addu (골든 content = job 산출, 파서 무변경).

피드백 → 원인/수리/가드 매핑:
  F1 간지 미입력인데 '모의고사'로 인쇄 — '[N과 추가지문]' bracket 헤더
     원고가 무-p형('N. no.M') 감지에 안 잡혀 workbook_type 메타 기본값
     '모의고사'로 추락 (plan.divider={'line1':'모의고사','source':'type'}).
     → supp _detect_supp_type 판정 사다리: 파일/폴더명 '외부지문' 토큰 →
       무-p형 → 'N과 추가지문' 헤더('추가지문') → 비모의고사 메타 →
       중립 '부교재'. supp에서 '모의고사'는 어떤 경우에도 자동 금지.
     → 게이트 G27 확장: source=type + line1='모의고사' = critical.
  F2 짤지문 간지 스프레드(p34~35) 잔존 — 짤지문 섹션은 v2가 콘텐츠를
     배치하지 않는 템플릿 영역인데, 라벨 페이지에 섹션 마스터(O)가 적용돼
     ([원본]워크북_C p263 실측) 마스터-없음 기준의 간지 판정/삭제/갱신을
     전부 비껴갔다.
     → 실행기 removeOrphanDividers (delete 모드 cleanupPages — 라벨 뒤에
       다음 간지/문서 끝까지 플로우 콘텐츠가 없으면 스프레드째 삭제)
     → 게이트 G28③ 고아 간지 (delete critical / 아니면 warning)
  F3 CO₂의 ₂(U+2082) 미표시 — 본문 폰트 Noto Sans CJK KR의 cmap에 아래첨자
     숫자 글리프가 없음 (core.fontcov 실측 — 불량 출력 151건).
     → 플랜 SUBSCRIPT_PRINT_TABLE: ₂→2 + {"sub": True} 서식 run, 실행기
       Position.SUBSCRIPT 직접 적용 (문자스타일 아님 — 어떤 폰트든 렌더)
     → 게이트 G29: 등재 문자 잔존 critical(G10 확장 패턴) + 스타일 적용
       폰트 cmap 실측 글리프 미지원 warning (fonts/style_fonts 덤프 확장)
  F4 문제가 오른쪽 페이지에서 잘려 다음 장으로 이어짐 (신규 조판 규칙:
     왼쪽→오른쪽 허용, 오른쪽→다음 장 금지 — 문제 전체를 다음 페이지로).
     → plan.question_keep_op(문제 시작 flat 인덱스 계약, supp+본가 opt-in)
       + 실행기 enforceQuestionKeep (NEXT_PAGE 밀기 캐스케이드 + 오버플로우
       확장 + delete 모드 alignPartFillers 재실행)
     → 게이트 G30: fp(프레임별 페이지 — W23 덤프 확장)로 걸침 재계산,
       op 사용 critical / 구출력 warning 소급 (불량 출력 2건: p29→p30,
       p31→p32).
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
GOLDEN = os.path.join(TESTS_DIR, "corpus", "workbook_supp", "r13c24addu",
                      "golden", "content.json")

from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_v2.plan import (steps_to_plan, unit_paras,
                                      question_keep_op,
                                      apply_subscript_print_map,
                                      SUBSCRIPT_PRINT_TABLE)
from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine, _STEP_MAP


@pytest.fixture(scope="module")
def content():
    return json.load(open(GOLDEN, encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_dump():
    return json.load(open(W23_DUMP, encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_plan():
    return json.load(open(W23_PLAN, encoding="utf-8"))


@pytest.fixture(scope="module")
def bad_report(content, bad_dump, bad_plan):
    """불량 출력(워크북1_내지_v2_4) 그대로 — 당시 플랜(간지 '모의고사',
    question_keep 계약 없음)."""
    return inspect_workbook_finish(content, bad_plan, bad_dump)


def test_bad_output_all_four_detected(bad_report):
    """소급 검출 실증 — 사용자 피드백 4건이 게이트에 전부 잡힌다.
    F3/F4는 당시 플랜에 계약(치환/question_keep)이 없어 warning 지목
    (G3/G4의 'op 사용 시 critical' 패턴 — critical 경로는 아래 개별 가드)."""
    crit = bad_report["critical"]
    warn = bad_report["warnings"]
    assert any("모의고사' 자동 라벨 금지" in c for c in crit), crit    # F1
    assert any(c.startswith("[파트경계] 고아 간지") and "p35" in c
               for c in crit), crit                                    # F2
    assert any(w.startswith("[글리프커버리지]") and "U+2082" in w
               for w in warn), warn                                    # F3
    assert any(w.startswith("[문제단위킵]") and "2건" in w
               for w in warn), warn                                    # F4
    assert bad_report["stats"]["orphan_dividers"] == 1
    assert bad_report["stats"]["subscript_residue"] == 151
    assert bad_report["stats"]["question_keep_viol"] == 2


# ── F1: supp 간지 교재유형 판정 사다리 ───────────────────────────────────────

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


def test_supp_divider_addu_header(content, tmp_path):
    """'[N과 추가지문]' bracket 헤더 원고 → '추가지문' (6c1430c3 실증)."""
    job = _mk_job(tmp_path, content)
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "추가지문", "line2": "",
                               "source": "type"}


def test_supp_divider_ext_filename_token(tmp_path):
    """업로드 파일명의 '외부지문' 토큰 → '외부지문' (헤더 형식 무관)."""
    job = _mk_job(tmp_path, {"steps": {}},
                  uploads=["manuscripts_외부지문 Step1 A1.docx"])
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"]["line1"] == "외부지문"


def test_supp_divider_neutral_fallback(tmp_path):
    """판정 불가(p형 헤더 + 메타 기본) → 중립 '부교재' — '모의고사'는 어떤
    경우에도 자동으로 나가지 않는다 (W22 폴백 '모의고사'의 의미론 갱신)."""
    job = _mk_job(tmp_path, {"steps": {"step1_a1": {"paragraphs":
                                                    [{"text": "1. p2-no.20"}]}}})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "부교재", "line2": "",
                               "source": "type"}


def test_supp_divider_meta_non_mock(tmp_path):
    """workbook_type 메타가 '모의고사'가 아니면 그 값 (사용자 폼 신호)."""
    job = _mk_job(tmp_path, {"steps": {}}, meta={"workbook_type": "교과서"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"]["line1"] == "교과서"


def test_supp_divider_user_text_wins(content, tmp_path):
    job = _mk_job(tmp_path, content, meta={"divider_text": "성덕고 워크북"})
    deco = WorkbookSuppV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "성덕고 워크북", "line2": "",
                               "source": "user"}


def test_gate_g27_mock_type_contract(bad_plan, bad_dump, content):
    """plan.divider(source=type, line1=모의고사) = 계약 위반 critical —
    라벨이 '기대 문구대로' 갱신됐어도 잡힌다 (불량 출력이 이 상태)."""
    rep = inspect_workbook_finish(content, bad_plan, bad_dump)
    assert any("모의고사' 자동 라벨 금지" in c for c in rep["critical"])
    # user 입력이 '모의고사'인 것은 계약 위반이 아니다
    plan2 = copy.deepcopy(bad_plan)
    plan2["divider"]["source"] = "user"
    rep2 = inspect_workbook_finish(content, plan2, bad_dump)
    assert not any("자동 라벨 금지" in c for c in rep2["critical"])


# ── F2: 고아 간지 스프레드 (G28③ + 실행기) ──────────────────────────────────

def _orphan_dump(with_content_after):
    """간지 라벨 p5 뒤에 콘텐츠 페이지가 있는/없는 합성 덤프."""
    stories = [
        {"idx": 0, "pg": ["2"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": "alpha bravo charlie delta echo\r", "s": "P"}]},
        {"idx": 1, "pg": ["5"], "fc": [0], "overflow": False,
         "paragraphs": [{"t": "고2 모의고사\r", "s": "[기본 단락]"},
                        {"t": "26년 3월 짤지문", "s": "[기본 단락]"}]},
    ]
    if with_content_after:
        stories.append(
            {"idx": 2, "pg": ["6"], "fc": [0], "overflow": False,
             "paragraphs": [{"t": "alpha bravo charlie delta echo\r",
                             "s": "P"}]})
    pages = [{"p": str(i), "m": m, "side": ("R" if i % 2 else "L"),
              "empty": False}
             for i, m in ((1, ""), (2, "A-마스터"), (3, "A-마스터"),
                          (4, "O-마스터"), (5, "O-마스터"), (6, "O-마스터"))]
    return {"doc": "x", "stories": stories, "overflow_stories": 0,
            "page_count": 6, "pages": pages, "stale_pages": []}


_ORPHAN_PLAN = {"flows": [{"step": "step1_a1", "target": {},
                           "units": [[{"t": "alpha bravo charlie delta echo",
                                       "s": "P"}]]}],
                "page_cleanup": {"empty": "delete"}}


def test_gate_g28_orphan_divider_critical():
    rep = inspect_workbook_finish({"steps": {}}, _ORPHAN_PLAN,
                                  _orphan_dump(with_content_after=False))
    bad = [c for c in rep["critical"] if "고아 간지" in c]
    assert bad and "p5" in bad[0], rep["critical"]
    assert rep["stats"]["orphan_dividers"] == 1


def test_gate_g28_divider_with_content_kept():
    rep = inspect_workbook_finish({"steps": {}}, _ORPHAN_PLAN,
                                  _orphan_dump(with_content_after=True))
    assert not [c for c in rep["critical"] if "고아 간지" in c]
    assert not [w for w in rep["warnings"] if "고아 간지" in w]
    assert rep["stats"]["orphan_dividers"] == 0


def test_gate_g28_orphan_non_delete_warning():
    plan = {"flows": _ORPHAN_PLAN["flows"],
            "page_cleanup": {"empty_master": "M"}}
    rep = inspect_workbook_finish({"steps": {}}, plan,
                                  _orphan_dump(with_content_after=False))
    assert not [c for c in rep["critical"] if "고아 간지" in c]
    assert [w for w in rep["warnings"] if "고아 간지" in w]


def test_executor_f2_orphan_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function removeOrphanDividers" in src
    assert "function isDividerLabelLike" in src
    body = src.split("function cleanupPages")[1].split("\nfunction ")[0]
    # delete 모드에서 alignPartFillers보다 먼저 호출 (삭제 → 정렬 순서)
    assert "removeOrphanDividers(doc, flowIds)" in body
    assert (body.index("removeOrphanDividers(doc, flowIds)")
            < body.index("alignPartFillers(doc)"))


# ── F3: 아래첨자 인쇄 매핑 + G29 글리프 커버리지 ─────────────────────────────

def test_subscript_map_runs_offsets():
    """₂→2 치환 + sub run 분리 — 밑줄 runs 오프셋/플래그 보존."""
    para = {"text": "The CO₂ level", "runs": [
        {"t": "The CO₂ ", "ul": False}, {"t": "level", "ul": True}]}
    out = apply_subscript_print_map(para)
    assert out["text"] == "The CO2 level"
    assert "".join(r["t"] for r in out["runs"]) == out["text"]
    sub = [r for r in out["runs"] if r.get("sub")]
    assert len(sub) == 1 and sub[0]["t"] == "2"
    ul = [r for r in out["runs"] if r.get("ul")]
    assert len(ul) == 1 and ul[0]["t"] == "level"
    # runs 없는 단락은 전체 비밑줄 run으로 실체화
    out2 = apply_subscript_print_map({"text": "H₂O"})
    assert out2["text"] == "H2O"
    assert [r.get("sub", False) for r in out2["runs"]] == [False, True, False]
    # 치환 대상 없는 단락은 원본 그대로 (사본/무변형)
    p3 = {"text": "no subs"}
    assert apply_subscript_print_map(p3) is p3


def test_plan_substitutes_all_subscripts(content):
    """r13c24addu 골든(₂ 151건 잠복) → 플랜에 ₂ 잔존 0 + sub run 151개.
    골든 content에는 ₂가 보존된다 (플랜 계층 치환 — W20 PUA 전례)."""
    plan = steps_to_plan(content["steps"], workbook_type="모의고사",
                         step_map=_STEP_MAP)
    resid = 0
    sub_runs = 0
    for fl in plan["flows"]:
        for u in fl["units"]:
            for p in unit_paras(u):
                resid += sum(p["t"].count(c) for c in SUBSCRIPT_PRINT_TABLE)
                sub_runs += sum(1 for r in p.get("runs") or []
                                if r.get("sub"))
    assert resid == 0
    assert sub_runs == 151
    raw = json.dumps(content, ensure_ascii=False)
    assert raw.count("₂") == 306          # 원고(골든) 무변형 — text+runs 쌍


def test_fontcov_parser_sanity():
    from core.fontcov import font_covers
    helv = "/System/Library/Fonts/Helvetica.ttc"
    if os.path.isfile(helv):
        assert font_covers(helv, "A") is True
    assert font_covers("/no/such/font.otf", "A") is None
    # 불량 출력의 실측 근거: 본문 폰트 Noto Sans CJK KR에 U+2082 글리프 없음
    noto = os.path.expanduser("~/Library/Fonts/NotoSansCJKkr-Regular.otf")
    if os.path.isfile(noto):
        assert font_covers(noto, "₂") is False
        assert font_covers(noto, "한") is True


def test_gate_g29_registered_residue(bad_report, content, bad_dump):
    """구플랜(₂ 잔존 — 치환 미지원)은 warning 소급, 치환된 현행 플랜의
    출력에 잔존하면 critical (매핑 미적용 출력)."""
    warn = [w for w in bad_report["warnings"]
            if w.startswith("[글리프커버리지]")]
    assert warn and "'₂'(U+2082) 151건" in warn[0], bad_report["warnings"]
    plan_now = steps_to_plan(content["steps"], workbook_type="모의고사",
                             step_map=_STEP_MAP)
    rep = inspect_workbook_finish(content, plan_now, bad_dump)
    crit = [c for c in rep["critical"] if c.startswith("[글리프커버리지]")]
    assert crit and "'₂'(U+2082) 151건" in crit[0], rep["critical"]


def test_gate_g29_clean_after_substitution(bad_dump, bad_plan, content):
    """치환된 출력(₂→2)을 모사 — 글리프커버리지 critical 소멸."""
    d = copy.deepcopy(bad_dump)
    for st in d["stories"]:
        for p in st["paragraphs"]:
            p["t"] = p["t"].replace("₂", "2")
    rep = inspect_workbook_finish(content, bad_plan, d)
    assert not [c for c in rep["critical"]
                if c.startswith("[글리프커버리지]")]


def test_gate_g29_font_uncovered_warning(bad_dump):
    """cmap 실측 경로 — 적용 폰트가 커버하지 않는 특수문자(U+2000~2BFF,
    비등재)를 warning으로 지목한다. 불량 덤프의 실제 폰트 매핑을 사용해
    미커버 문자를 동적으로 찾는다 (폰트 파일 없으면 skip)."""
    from core.fontcov import font_covers
    sf = {e["s"]: (e["f"], e["fs"]) for e in bad_dump["style_fonts"]}
    fl = {e["n"]: e["loc"] for e in bad_dump["fonts"]}
    style, loc = None, None
    for s, (fam, fs) in sf.items():
        loc = fl.get(f"{fam}\t{fs}") or fl.get(fam)
        if loc and os.path.isfile(loc):
            style = s
            break
    if not style:
        pytest.skip("덤프 폰트 파일이 이 기기에 없음")
    probe = next((chr(cp) for cp in range(0x2000, 0x2C00)
                  if chr(cp) not in SUBSCRIPT_PRINT_TABLE
                  and font_covers(loc, chr(cp)) is False), None)
    if probe is None:
        pytest.skip("이 폰트는 검사 범위를 전부 커버")
    dump = {"doc": "x", "overflow_stories": 0, "page_count": 1,
            "pages": [], "stale_pages": [],
            "fonts": bad_dump["fonts"], "style_fonts": bad_dump["style_fonts"],
            "stories": [{"idx": 0, "pg": ["1"], "fc": [0], "overflow": False,
                         "paragraphs": [{"t": f"probe {probe} char\r",
                                         "s": style}]}]}
    rep = inspect_workbook_finish({"steps": {}}, {"flows": []}, dump)
    hits = [w for w in rep["warnings"] if w.startswith("[글리프커버리지]")]
    assert hits and f"U+{ord(probe):04X}" in hits[0], rep["warnings"]


def test_executor_f3_sub_run_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "Position.SUBSCRIPT" in src
    assert "runs[ri].sub" in src


# ── F4: 문제 단위 펼침면 킵 (question_keep + G30) ────────────────────────────

def test_question_keep_op_contract(content):
    plan = steps_to_plan(content["steps"], workbook_type="모의고사",
                         step_map=_STEP_MAP)
    qk = question_keep_op(plan)
    assert qk and set(qk["flows"]) == {"step3"}
    starts = qk["flows"]["step3"]["starts"]
    # 문제 24개 — 첫 문제(인덱스 0)는 밀기 대상에서 제외
    assert len(starts) == 23
    assert 0 not in starts
    assert starts == sorted(starts)
    assert any("실전문제 번호" in s for s in qk["q_styles"])
    # 대상 스텝이 없으면 None (op 미적용)
    assert question_keep_op({"flows": []}) is None


def test_engine_decorations_opt_in(tmp_path, content):
    """supp + 본가 데코가 question_keep 센티널을 싣는다 (opt-in)."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    job = _mk_job(tmp_path, content)
    assert WorkbookSuppV2Engine()._plan_decorations(job, {}).get(
        "question_keep") is True
    assert WorkbookV2Engine()._plan_decorations(job, {}).get(
        "question_keep") is True


def test_gate_g30_retro_warning(bad_report):
    """불량 출력 소급 — 계약 없는 구플랜은 warning 지목 (2건: 요약 문제
    p29→p30, 문장삽입 문제 p31→p32 — 실측 확인)."""
    hits = [w for w in bad_report["warnings"] if w.startswith("[문제단위킵]")]
    assert hits and "p29→p30" in hits[0] and "p31→p32" in hits[0], hits
    assert bad_report["stats"]["question_keep_viol"] == 2


def test_gate_g30_critical_with_contract(content, bad_dump, bad_plan):
    """question_keep 계약이 실린 플랜에서 걸침 잔존 = critical."""
    plan = copy.deepcopy(bad_plan)
    qk = question_keep_op(plan)
    assert qk
    plan["question_keep"] = qk
    rep = inspect_workbook_finish(content, plan, bad_dump)
    bad = [c for c in rep["critical"] if c.startswith("[문제단위킵]")]
    assert bad and "2건" in bad[0], rep["critical"]


def test_gate_g30_same_spread_ok(content, bad_dump, bad_plan):
    """왼쪽→오른쪽(같은 스프레드) 이어짐은 허용 — 걸침 2건을 제거한 덤프를
    모사하면 문제단위킵 무지적."""
    d = copy.deepcopy(bad_dump)
    for st in d["stories"]:
        if len(st.get("paragraphs", [])) > 100:
            # 프레임 경계를 스프레드 경계와 정렬: 12프레임을 6페이지에
            # L,R 순서로 재배치하되 걸침이 없도록 fc를 문제 경계에 스냅
            offs, cum = [], 0
            for p in st["paragraphs"]:
                offs.append(cum)
                cum += len(p["t"])
            bounds = [i for i, p in enumerate(st["paragraphs"])
                      if "실전문제 번호" in p["s"] or "다음 글을 읽고" in p["s"]]
            # 문제 4개씩 한 페이지 (24문제/6페이지) — 페이지 경계가 항상
            # 문제 시작과 일치 → 걸침 0
            pages = ["28", "29", "30", "31", "32", "33"]
            fc, fp = [], []
            for pi, b in enumerate(range(0, 24, 4)):
                fc.append(offs[bounds[b]] if b < len(bounds) else offs[0])
                fp.append(pages[pi])
            fc[0] = 0
            st["fc"], st["fp"] = fc, fp
    plan = copy.deepcopy(bad_plan)
    plan["question_keep"] = question_keep_op(plan)
    rep = inspect_workbook_finish(content, plan, d)
    assert not [c for c in rep["critical"] if c.startswith("[문제단위킵]")]
    assert rep["stats"]["question_keep_viol"] == 0


def test_gate_g30_left_start_manual_warning(content, bad_dump, bad_plan):
    """왼쪽 시작 + 스프레드 초과(한 문제가 2페이지 초과)는 밀어도 해소
    불가 — warning (수동 확인)."""
    d = copy.deepcopy(bad_dump)
    for st in d["stories"]:
        if len(st.get("paragraphs", [])) > 100:
            # 스토리 전체를 문제 1개처럼: 경계 스타일을 첫 발문만 남기고
            # 전부 선지 스타일로 — L 시작(p28) + p33 종료 = 스프레드 초과
            first = True
            for p in st["paragraphs"]:
                if "실전문제 번호" in p["s"] or "다음 글을 읽고" in p["s"]:
                    if first:
                        first = False
                    else:
                        p["s"] = "STEP 03 > S_선지 올림포스"
    plan = copy.deepcopy(bad_plan)
    plan["question_keep"] = {"flows": {"step3": {"starts": [1]}},
                             "q_styles": []}
    rep = inspect_workbook_finish(content, plan, d)
    assert not [c for c in rep["critical"] if c.startswith("[문제단위킵]")]
    assert [w for w in rep["warnings"] if "스프레드 초과" in w], \
        rep["warnings"]


def test_executor_f4_keep_sources():
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function enforceQuestionKeep" in src
    assert "function expandStoryOverflow" in src
    assert "function spreadIdOf" in src
    # 훅 순서: page_cleanup 이후, section_masters 이전 (삭제 전에 밀면
    # 빈 페이지 삭제가 좌우를 되밀리는 순환)
    main = src.split("var plan = readJSONFile(PLAN)")[1]
    assert (main.index("wb_v2 page_cleanup")
            < main.index("wb_v2 question_keep")
            < main.index("wb_v2 section_masters"))
    # 캐스케이드 가드 + 컬렉션 캐시 + 하트비트 (철칙)
    keep = src.split("function enforceQuestionKeep")[1].split(
        "\nfunction ")[0]
    assert "everyItem().getElements()" in keep
    assert "starts.length * 2 + 10" in keep
    assert "문제단위킵 검사 진행" in keep
    assert "expandStoryOverflow" in keep


# ── 무회귀: 본가/EBS/교과서 파생 엔진 플랜 계약 ─────────────────────────────

def test_mockexam_divider_still_unchanged(tmp_path):
    """본가 c04 divider 무회귀 (F1은 supp 전용 — 본가는 W19 D4 그대로)."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    golden = os.path.join(TESTS_DIR, "corpus", "workbook_v2",
                          "r5c04mock211", "golden", "content.json")
    cont = json.load(open(golden, encoding="utf-8"))
    job = _mk_job(tmp_path, cont)
    deco = WorkbookV2Engine()._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "고2 모의고사", "line2": "25년 6월"}


def test_derived_engines_no_question_keep(tmp_path):
    """교과서/EBS 파생 엔진의 데코는 question_keep 미탑재 (opt-in 시작 —
    supp+본가만. 파생 계열 확산은 실기 검증 후)."""
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine
    job = _mk_job(tmp_path, {"steps": {}})
    for eng in (TextbookWorkbookV2Engine(), EbsWorkbookV2Engine()):
        deco = eng._plan_decorations(job, {})
        assert "question_keep" not in deco, type(eng).__name__
