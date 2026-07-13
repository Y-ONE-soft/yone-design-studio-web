"""W20 — 품질 루프 10라운드 결함 가드 (미해소 잠복 2건 우선 타격 + 소급).

투입 원고 (inventory.jsonl 시그니처 스캔 선정 — 우선 타격 지정이 거리
기준을 오버라이드, 선정 상세는 docs/workbook_v2_로드맵.md W20):
  c21 리딩파워 유형완성 기출문제-11강(133문제).hwp — 인라인 PUA 겹따옴표
      (U+F0852/F0853 ×2쌍) 보유 실증 → ebs_workbook_v2 (잠복 ① W14 (1))
  c22 고1 25년 3월 모의고사 워크북 폴더 — 스텝3 U+F003B 단독 단락 14건
      보유 실증 (전수 스캔 최다) → workbook_v2 (잠복 ② W14 (2))

결함→가드 매핑:
  D1 인라인 PUA 인쇄 매핑 부재 — hwp 문자표 심볼(겹따옴표 U+F0852/F0853,
     요약 화살표 U+F0036/F003B/F0EA)이 본문 혼입으로 tofu 인쇄 (c06 W14
     최종 출력 실증 2건 + c21 실증). 플랜 계층 PUA_PRINT_TABLE 1:1 치환
     (파서/디코더 무변경 — 골든 byte-identical) + G10 확장(등재 코드
     혼입 잔존 = critical, 미등재는 warning 유지).
"""
import copy
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")
FIXTURES = os.path.join(TESTS_DIR, "fixtures")


# ── D1: PUA 인쇄 매핑 테이블 ────────────────────────────────────────────────

def test_pua_print_table_entries_are_single_char():
    """1:1(한 글자) 치환만 허용 — _map_chars의 runs 오프셋 보존 전제."""
    from engines.workbook_v2.plan import PUA_PRINT_TABLE
    assert PUA_PRINT_TABLE, "매핑 테이블이 비어 있음"
    for cp, repl in PUA_PRINT_TABLE.items():
        assert isinstance(repl, str) and len(repl) == 1, hex(cp)
    # 실증 코드 5종 등재 (근거 없는 확대 금지 — 추가는 문맥 실증 필수)
    assert set(PUA_PRINT_TABLE) == {0xF0852, 0xF0853, 0xF0036, 0xF003B,
                                    0xF0EA}
    assert PUA_PRINT_TABLE[0xF0852] == "“"
    assert PUA_PRINT_TABLE[0xF0853] == "”"
    assert PUA_PRINT_TABLE[0xF003B] == "⇩"


def test_apply_pua_print_map_preserves_runs_and_source():
    from engines.workbook_v2.plan import apply_pua_print_map
    para = {"text": "puts it, \U000f0852Seventy-five\U000f0853 done",
            "runs": [{"t": "puts it, \U000f0852Seventy", "ul": False},
                     {"t": "-five\U000f0853 done", "ul": True}],
            "kind": "P"}
    src = copy.deepcopy(para)
    out = apply_pua_print_map([para])[0]
    assert out["text"] == "puts it, “Seventy-five” done"
    assert out["runs"][0]["t"] == "puts it, “Seventy"
    assert out["runs"][1] == {"t": "-five” done", "ul": True}
    assert out["kind"] == "P"
    assert para == src, "원본 mutate 금지 (사본 반환)"
    # 중첩(step3) 형태 + 매핑 미등재 PUA 통과
    step3 = {"normal": [{"question_num": "31",
                         "paragraphs": [{"text": "\U000f003b"},
                                        {"text": "불릿항목"}]}],
             "short": []}
    out3 = apply_pua_print_map(step3)
    assert out3["normal"][0]["paragraphs"][0]["text"] == "⇩"
    assert out3["normal"][0]["paragraphs"][1]["text"] == "불릿항목"


def test_steps_to_plan_maps_inline_pua_c06_corpus():
    """c06 골든(r4c06rpcr) — 인라인 겹따옴표가 플랜에서 정자로 치환."""
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r4c06rpcr", "golden",
                          "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          _is_pua)
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="EBS")
    txt = json.dumps(plan, ensure_ascii=False)
    assert not any(_is_pua(ch) for ch in txt), "플랜에 PUA 잔존"
    assert "“Seventy-five percent" in txt
    assert "whole family.”In other words" in txt
    # content 원본은 무변형 (골든 byte-identical 전제)
    raw = open(golden, encoding="utf-8").read()
    assert "\U000f0852" in raw


def test_sero_cycle_plan_maps_pua():
    """세로 사이클 빌더도 같은 매핑 적용 (슬롯 + step3 경로)."""
    from engines.workbook_sero_v2.plan import _build_cycle
    cyc = {"q_num": "31", "code": "", "steps": {
        "step1_b1": [{"text": "the \U000f0852quoted\U000f0853 body",
                      "runs": []}],
        "step3": [{"text": "요약 지문", "kind": "P"},
                  {"text": "\U000f003b", "kind": "UNKNOWN"},
                  {"text": "After summary", "kind": "P"}],
    }}
    plan = _build_cycle(cyc, set(), "모의고사")
    txt = json.dumps(plan, ensure_ascii=False)
    from engines.workbook_v2.plan import _is_pua
    assert not any(_is_pua(ch) for ch in txt)
    assert "“quoted”" in txt


REPO = os.path.dirname(TESTS_DIR)


# ── r10 코퍼스 앵커 (c21/c22 — 편입 골든의 플랜 수치 고정) ──────────────────

def test_r10c21_plan_anchor():
    """c21 골든 → 플랜: PUA 0 + 겹따옴표 정자 + E2E 실측 수치."""
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r10c21rp11",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          _is_pua)
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="EBS")
    txt = json.dumps(plan, ensure_ascii=False)
    assert not any(_is_pua(ch) for ch in txt)
    assert "“land of opportunity”" in txt
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert len(paras) == 746            # E2E 실측 (2026-07-13)
    assert sum(1 for p in paras if "배경" in (p.get("s") or "")) == 33


def test_r10c22_plan_anchor():
    """c22 골든 → 플랜: U+F003B(원고 28건) 전량 소화 + divider."""
    golden = os.path.join(CORPUS, "workbook_v2", "r10c22mock2503g1",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    raw = open(golden, encoding="utf-8").read()
    assert raw.count("\U000f003b") == 28   # 원고 잠복 (파서 무변경 보존)
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          _is_pua)
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="모의고사")
    txt = json.dumps(plan, ensure_ascii=False)
    assert not any(_is_pua(ch) for ch in txt)
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert len(fl["units"]) == 25           # E2E 실측 (18 normal + 7 short)
    assert sum(1 for p in paras if "배경" in (p.get("s") or "")) == 28


# ── 세로 divider op 이식 (W20 — G22 소급 c17) ───────────────────────────────

def test_sero_executor_has_divider_op():
    """세로 실행기 divider — 라벨 내용 정확 매칭 방식 소스 가드.

    가로의 마스터/프레임 휴리스틱 대신 '고N 모의고사'+'YY년 M월' 연속
    2단락 매칭만 갱신 — '…월 짤지문' 라벨은 끝 앵커($)로 비매치
    (v1 관행 보존, G22 제외와 동일)."""
    src = open(os.path.join(REPO, "core", "jsx",
                            "workbook_sero_flow.body.jsx"),
               encoding="utf-8").read()
    assert "plan.divider" in src
    body = src.split("plan.divider && plan.divider.line1")[1]
    body = body.split("relockIcons")[0]
    assert r"/^고\d\s*모의고사\s*$/" in body
    assert r"월\s*$/" in body          # 끝 앵커 — 짤지문 라벨 비매치
    assert "간지 텍스트 업데이트" in body


def test_sero_meta_and_gate_plan_include_divider():
    """sero prepare_jsx가 meta에 divider를 싣고 verify pseudo-plan으로
    전달 (G22 critical 승격 계약) — 소스 가드."""
    src = open(os.path.join(REPO, "engines", "workbook_sero_v2",
                            "engine.py"), encoding="utf-8").read()
    assert "_mockexam_divider" in src
    assert src.index("_mockexam_divider(job_dir)") < src.index("n_warn = 0")
    assert '"divider": meta.get("divider")' in src


# ── G10 확장 — 검출 실증 (수리 전 c06 실덤프 발췌 픽스처) ────────────────────

def test_gate_g10_mapped_inline_critical_on_pre_fix_c06_dump():
    from engines.workbook_v2.gate import inspect_workbook_finish
    dump = json.load(open(os.path.join(
        FIXTURES, "w20_defect_dumps", "c06_inline_pua_pre_fix.json"),
        encoding="utf-8"))
    plan = {"flows": [{"step": "step3",
                       "units": [[{"t": "body", "s": "S"}]]}]}
    rep = inspect_workbook_finish({}, plan, dump)
    assert rep["stats"]["pua_mapped_inline"] == 2
    assert any("[특수문자]" in c and "매핑" in c for c in rep["critical"])


def test_gate_g10_unknown_inline_stays_warning():
    from engines.workbook_v2.gate import inspect_workbook_finish
    plan = {"flows": [{"step": "step3",
                       "units": [[{"t": "body", "s": "S"}]]}]}
    dump = {"stories": [{"paragraphs": [
        {"t": "make us“independently” choose", "s": "S"}]}],
        "stale_pages": []}
    rep = inspect_workbook_finish({}, plan, dump)
    assert not any("[특수문자]" in c for c in rep["critical"])
    assert any("[특수문자]" in w for w in rep["warnings"])
