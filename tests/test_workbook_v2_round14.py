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


# ── 과제 2: 레이아웃 정책 계열 확산 (textbook / ebs / suneungteukgang) ────────

def test_textbook_decorations_expanded(tmp_path):
    """교과서: supp 검증 3종 op 활성 — delete + section_masters +
    question_keep (r14 c13 실기 검증. 내지가 supp와 같은 [원본]워크북_C)."""
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    job = _mk_job(tmp_path, {"steps": {}},
                  meta={"subject": "공통영어1",
                        "publisher": "공통영어1 YBM(김)",
                        "lesson": "Project 1"})
    deco = TextbookWorkbookV2Engine()._plan_decorations(job, {})
    assert deco["page_cleanup"] == {"empty": "delete"}
    assert deco["section_masters"] is True
    assert deco["question_keep"] is True
    # 기존 데코 무회귀
    assert deco["textbook_postprocess"] is True
    assert deco["divider"]["line1"] == "공통영어1 YBM(김)"


def test_textbook_step_map_master_pairs():
    """교과서 step_map: 기본 STEP_MAP과 동일 마커/pos + master_pair
    (STEP1 = A/B, STEP2 = C/D — supp W21 실측 계약 재사용, supp 전용
    label_contract/per_passage_units는 미등재)."""
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    from engines.workbook_v2.plan import STEP_MAP
    smap = TextbookWorkbookV2Engine()._step_map()
    base_map = {k: v for k, v in STEP_MAP.items() if k != "_doc"}
    assert set(smap) == set(base_map)
    for k, base in base_map.items():
        entry = dict(smap[k])
        pair = entry.pop("master_pair", None)
        assert entry == base, k                      # 마커/페이지/pos 동일
        if k == "step3":
            assert pair is None
        else:
            want = ("A-마스터", "B-마스터") if k.startswith("step1") \
                else ("C-마스터", "D-마스터")
            assert pair == {"left": want[0], "right": want[1]}, k
        assert "label_contract" not in smap[k]
        assert "per_passage_units" not in smap[k]


def test_ebs_decorations_delete_and_question_keep(tmp_path):
    """EBS: delete + question_keep 활성 (r14 c16 프로브 critical 0 —
    delete가 M-모드와 다른 구간은 마지막 간지 이후뿐이라 간지 정렬
    구조 보존, 정렬 붕괴는 G28 delete critical이 감시). divider_solo는
    수능특강 셸 전용 — EBS 미사용. section_masters는 보류 (STEP3 단독
    코퍼스라 실기 검증 불가 — master_pair 계약만 G26 warning 감시)."""
    from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine
    deco = EbsWorkbookV2Engine()._plan_decorations(str(tmp_path), {})
    assert deco == {"page_cleanup": {"empty": "delete"},
                    "question_keep": True}


def test_ebs_step_map_master_pair_step1_only():
    """EBS step_map: STEP1만 master_pair(A/B — 내지 46p 실측: 우측 시작
    p7/p13 = B-마스터). STEP2는 C 좌/우 공용이라 미등재, section_masters
    op는 실기 검증 불가(코퍼스 전부 STEP3 단독)로 보류 — G26 warning
    감시만."""
    from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine
    smap = EbsWorkbookV2Engine()._step_map()
    pair = {"left": "A-마스터", "right": "B-마스터"}
    for k in smap:
        if k.startswith("step1_"):
            assert smap[k]["master_pair"] == pair, k
        else:
            assert "master_pair" not in smap[k], k


def test_stg_stage_plans_expanded(tmp_path, monkeypatch):
    """수능특강 2단계: 분석본 delete / 문제본 delete + divider_solo('N강'
    셸 간지) + question_keep 계약 (r14 27강 실기 + merge 검증)."""
    import engines.suneungteukgang_workbook_v2.engine as eng_mod
    from engines.suneungteukgang_workbook_v2.engine import (
        SuneungteukgangWorkbookV2Engine)
    case = os.path.join(TESTS_DIR, "corpus", "suneungteukgang_workbook",
                        "65cf0265")
    job = tmp_path / "job"
    job.mkdir()
    t_a = tmp_path / "analysis.indd"
    t_p = tmp_path / "problem.indd"
    t_a.write_bytes(b"A")
    t_p.write_bytes(b"P")
    monkeypatch.setattr(eng_mod, "_load_v1_config", lambda: {
        "indd_output_dir": str(tmp_path / "out"),
        "indd_original": {"analysis": str(t_a), "problem": str(t_p)},
    })
    (job / "lesson.txt").write_text("27강", encoding="utf-8")
    json_path = str(job / "content.json")
    (job / "content.json").write_text(
        open(os.path.join(case, "golden", "content.json"),
             encoding="utf-8").read(), encoding="utf-8")
    engine = SuneungteukgangWorkbookV2Engine()
    engine.prepare_jsx(json_path, str(job), lambda m: None)
    pa = json.load(open(str(job / "render_plan_analysis.json"),
                        encoding="utf-8"))
    pp = json.load(open(str(job / "render_plan_problem.json"),
                        encoding="utf-8"))
    assert pa["page_cleanup"] == {"empty": "delete"}
    assert "question_keep" not in pa          # 분석본은 step3 플로우 없음
    assert pp["page_cleanup"] == {"empty": "delete", "divider_solo": "강"}
    qk = pp.get("question_keep") or {}
    starts = (qk.get("flows") or {}).get("step3", {}).get("starts") or []
    assert starts and all(s > 0 for s in starts)
    assert qk.get("q_styles")


def test_gate_g28_divider_solo_orphan(bad_plan):
    """G28③ divider_solo 확장 — 'N강' 단독 단락 셸 간지의 고아 판정
    (opt-in 플랜 critical / 미사용 플랜은 후보 제외 = 잔존 침묵 방지용
    양방향)."""
    dump = {
        "pages": [{"p": str(i), "m": "", "side": "R" if i % 2 else "L",
                   "empty": False} for i in range(1, 7)],
        "stories": [
            # 콘텐츠 플로우 (p2)
            {"idx": 0, "pg": ["2"], "overflow": False,
             "paragraphs": [{"t": "Content body paragraph one\r",
                             "s": "STEP 01"}]},
            # 'N강' 단독 단락 셸 간지 (p5) — 뒤 콘텐츠 없음
            {"idx": 1, "pg": ["5"], "overflow": False,
             "paragraphs": [{"t": "2강\r", "s": "간지"}]},
        ],
    }
    content = {"steps": {}}
    base = {"flows": [{"step": "step1_a1", "target": {},
                       "units": [{"paras": [
                           {"t": "Content body paragraph one",
                            "s": "STEP 01"}]}]}],
            "unsupported": [], "warnings": []}
    plan_solo = dict(base, page_cleanup={"empty": "delete",
                                         "divider_solo": "강"})
    rep = inspect_workbook_finish(content, plan_solo, dump)
    assert rep["stats"].get("orphan_dividers") == 1
    assert any("고아 간지" in c for c in rep["critical"])
    # divider_solo 없는 delete 플랜: 단락 1개 라벨은 후보 제외 (기존 의미)
    plan_plain = dict(base, page_cleanup={"empty": "delete"})
    rep2 = inspect_workbook_finish(content, plan_plain, dump)
    assert rep2["stats"].get("orphan_dividers") == 0


def test_gate_g28_divider_solo_kept_when_content_follows(bad_plan):
    """'N강' 간지 뒤에 콘텐츠가 있으면 고아가 아니다 (현재 강 간지 보존)."""
    dump = {
        "pages": [{"p": str(i), "m": "", "side": "R" if i % 2 else "L",
                   "empty": False} for i in range(1, 7)],
        "stories": [
            {"idx": 0, "pg": ["3"], "overflow": False,
             "paragraphs": [{"t": "1강\r", "s": "간지"}]},
            {"idx": 1, "pg": ["4"], "overflow": False,
             "paragraphs": [{"t": "Content body paragraph one\r",
                             "s": "STEP 01"}]},
        ],
    }
    content = {"steps": {}}
    plan = {"flows": [{"step": "step1_a1", "target": {},
                       "units": [{"paras": [
                           {"t": "Content body paragraph one",
                            "s": "STEP 01"}]}]}],
            "unsupported": [], "warnings": [],
            "page_cleanup": {"empty": "delete", "divider_solo": "강"}}
    rep = inspect_workbook_finish(content, plan, dump)
    assert rep["stats"].get("orphan_dividers") == 0


def test_executor_divider_solo_sources():
    """실행기 소스 가드 — isDividerLabelLike의 allowSolo('N강') 분기 +
    alignPartFillers의 M 마스터 지연 lookup (M 없는 내지 노이즈 제거)."""
    src = open(os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "function isDividerLabelLike(pg, flowIds, allowSolo)" in src
    assert "/^\\d+강$/" in src
    body = src.split("function alignPartFillers")[1].split(
        "// [W22 파트경계 유틸 끝]")[0]
    assert "function lookupM()" in body
    # 라벨 왼쪽 페이지 판정(continue) 이후에만 M lookup 호출 (지연)
    assert (body.index("if (!isDividerLabelPage(pg)) { continue; }")
            < body.index("if (!lookupM()) { return; }"))


def test_mainline_and_sero_unchanged(tmp_path):
    """활성 안 한 계열 무회귀 — 본가(모의고사)는 M-모드 + question_keep
    (W23 그대로, section_masters 없음), 세로는 M-모드 + divider만 (W20
    그대로). 기본 STEP_MAP에 master_pair 미등재 (본가 플랜 diff 0)."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    from engines.workbook_v2.plan import STEP_MAP
    deco = WorkbookV2Engine()._plan_decorations(str(tmp_path), {})
    assert deco["page_cleanup"] == {"empty_master": "M"}
    assert deco["question_keep"] is True
    assert "section_masters" not in deco
    assert all("master_pair" not in v for v in STEP_MAP.values())
    sero = open(os.path.join(REPO, "engines", "workbook_sero_v2",
                             "engine.py"), encoding="utf-8").read()
    assert '"page_cleanup": {"empty_master": "M"}' in sero
    assert "question_keep" not in sero
    assert "section_masters" not in sero


# ── 과제 2: 수능특강 merge × delete 파리티 (r14 실기 결함 수리) ──────────────

def _merge_stats(spreads, pages, merged_spreads, merged_pages,
                 parity_pads=0, start_offsets=None):
    sources = []
    for i, (sp, pg) in enumerate(zip(spreads, pages)):
        s = {"path": f"/x/src{i}.indd", "spreads": sp, "pages": pg,
             "paras": [f"word{i} alpha bravo"]}
        if start_offsets is not None:
            s["start_offset"] = start_offsets[i]
        sources.append(s)
    st = {"sources": sources, "dup_fail": 0,
          "merged": {"path": "/x/m.indd", "spreads": merged_spreads,
                     "pages": merged_pages}}
    if parity_pads:
        st["parity_pads"] = parity_pads
    return st


def _merge_dump():
    return {"stories": [{"idx": 0, "overflow": False, "paragraphs": [
        {"t": "word0 word1 alpha bravo", "s": "본문"}]}]}


def test_gate_merge_parity_pad_slack():
    """홀수 강(9p) + 채움 1장 — 스프레드 +1/페이지 +1 허용 (r14 실측:
    27강 문제본 9p → 채움 후 Test2 append, 시작 오프셋 짝수)."""
    from engines.suneungteukgang_workbook_v2.engine import _gate_merge
    st = _merge_stats([5, 26], [9, 51], merged_spreads=32, merged_pages=61,
                      parity_pads=1, start_offsets=[0, 10])
    ok, warnings, info = _gate_merge(st, _merge_dump(),
                                     ["/x/src0.indd", "/x/src1.indd"])
    assert ok is True, warnings
    assert info["parity_pads"] == 1


def test_gate_merge_detects_left_start():
    """2번째 강 시작이 홀수 오프셋(인쇄 왼쪽) = 표지/간지 뒤집힘 —
    r14 실기 실증 (27강 문제본 9p 그대로 append 시 Test2 표지 offset 9)."""
    from engines.suneungteukgang_workbook_v2.engine import _gate_merge
    st = _merge_stats([5, 26], [9, 51], merged_spreads=32, merged_pages=60,
                      start_offsets=[0, 9])
    ok, warnings, _ = _gate_merge(st, _merge_dump(),
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is False
    assert any("인쇄 왼쪽 페이지" in w for w in warnings)


def test_gate_merge_detects_page_sum_mismatch():
    """통합본 페이지 수 ≠ 소스 합+채움 = 유실/중복 (신규 불변식)."""
    from engines.suneungteukgang_workbook_v2.engine import _gate_merge
    st = _merge_stats([5, 26], [10, 50], merged_spreads=31, merged_pages=59)
    ok, warnings, _ = _gate_merge(st, _merge_dump(),
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is False
    assert any("페이지 수 불일치" in w for w in warnings)


def test_gate_merge_legacy_stats_no_new_keys():
    """구버전 stats(파리티 키 없음)는 기존 의미 그대로 — 시작 파리티
    검사 생략, 스프레드 정확 합."""
    from engines.suneungteukgang_workbook_v2.engine import _gate_merge
    st = _merge_stats([6, 6], [12, 12], merged_spreads=12, merged_pages=24)
    ok, warnings, _ = _gate_merge(st, _merge_dump(),
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is True, warnings


def test_merge_jsx_parity_pad_sources():
    """merge JSX 소스 가드 — append 전 홀수 파리티 채움 + start_offset
    기록 (게이트 (d) 입력)."""
    src = open(os.path.join(REPO, "core", "jsx", "merge_spreads.body.jsx"),
               encoding="utf-8").read()
    assert "dst.pages.length % 2 === 1" in src
    assert "parity_pads" in src
    assert "start_offset: dst.pages.length" in src
    # 채움이 duplicate 루프보다 먼저
    assert (src.index("dst.pages.length % 2 === 1")
            < src.index("spreads[s].duplicate"))
