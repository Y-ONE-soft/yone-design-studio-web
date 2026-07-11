"""W14 — 품질 루프 4라운드 결함 가드 (미학습 원고 2종 실증 결함의 재발 방지).

투입 원고 (docs/원고_구조_인벤토리.md 다양성 후보):
  후보③ 공통영어1 비상(홍) 3과 타학교 기출 서술형 hwpx (조건 지시문
         발문 헤더형, Step3 단독) → textbook_workbook_v2
  후보⑥ 리딩파워 유형완성 기출문제-16강 CR-4(177문제).hwp ([CRN-N]형
         기출 문제모음) → ebs_workbook_v2

결함→가드 매핑:
  D1 문제모음 파일명 라우팅 공백 — '변형문제' 토큰 없는 기출 문제모음
     ("…기출문제-16강 CR-4(177문제).hwp")이 어느 스텝에도 매핑되지 않아
     prepare_jsx 빈플랜 차단에 걸림 (c06 실증 — W12 안전망이 침묵 유실은
     막았으나 조판 자체가 불가). 붙은 문항수 표기 "\\d문제"를 문제모음
     신호로 라우팅 (전수 인벤토리 20982건 중 36종 전부 문제모음 실증).
  D2 요약 화살표(⇩)의 hwp 사용자 영역(PUA) 인코딩 변형 — v1 pass 11
     포트(_RE_S3_ARROW)가 리터럴 화살표만 매칭해 (c05 모의고사
     18건)/\U000f0036(c06 2건) 단독 단락이 tofu로 인쇄되고 요약문 배경도
     미부여. 플랜 삭제+배경 일반화 + 게이트 G10 [특수문자] 이중 방어
     (검출 실증: 수리 전 c05 W13 최종 출력 덤프 → G10 critical 18건).
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


# ── D1: 문제모음 파일명 라우팅 (\d문제) ─────────────────────────────────────

def test_variant_pool_count_marker_routes():
    from engines.workbook_v2.engine import (_is_variant_pool_filename,
                                            _routes_to_step3)
    # W14 c06 실물 + 인벤토리 대표 문제모음
    for f in ("리딩파워 유형완성 기출문제-16강 CR-4(177문제).hwp",
              "리딩파워유형편완성_CH1_01강_변형문제(46문제).hwp",
              "고2_2023년-12월-모의고사_변형문제_18_42_231문제_아잉카아카데미.hwp",
              "3과 50문제.hwp"):
        assert _is_variant_pool_filename(f), f
        assert _routes_to_step3(f), f


def test_variant_pool_count_marker_rejects():
    from engines.workbook_v2.engine import _is_variant_pool_filename
    # 정답/해설 본, 스텝 원고, 문항수가 아닌 띄어쓴 "N 문제"(day 범위)
    for f in ("변형문제 정답지.hwp",
              "리딩파워유형편완성_CH1_01강_변형문제(46문제) 해설.hwp",
              "Step1 A1 어휘선택.docx",
              "배재고 어휘 DAY23~25 문제.hwpx",
              "24년 3월 고2 문제.hwpx"):
        assert not _is_variant_pool_filename(f), f


# ── D2: PUA 화살표 — 플랜 삭제+배경 + 게이트 G10 ───────────────────────────

def _mk_step3(paragraphs):
    return {"normal": [{"question_num": "20", "paragraphs": paragraphs}],
            "short": []}


def test_step3_pua_arrow_deleted_and_next_bg():
    from engines.workbook_v2.plan import build_step3, _style
    bg = _style("STEP3", "P-CONTEXT")
    for arrow in ("", "\U000f0036", "\U000f003b", "↓"):
        st3 = _mk_step3([
            {"text": "다음 글을 아래와 같이 요약할 때 알맞은 것은?",
             "kind": "Q"},
            {"text": "One of the most important aspects is trust.",
             "kind": "P"},
            {"text": arrow, "kind": "UNKNOWN"},
            {"text": "To maintain a relationship, keep (A)___.",
             "kind": "P"},
        ])
        units = build_step3(st3)["units"]
        paras = [p for u in units
                 for p in (u["paras"] if isinstance(u, dict) else u)]
        texts = [p["t"] for p in paras]
        assert arrow not in texts, f"화살표 단락 잔존: {arrow!r}"
        summary = [p for p in paras if p["t"].startswith("To maintain")]
        assert summary and summary[0]["s"] == bg, \
            f"요약문 배경 미부여 ({arrow!r})"


def test_step3_normal_symbols_not_treated_as_arrow():
    """일반 문자/기호 단독 단락은 화살표 규칙 미발동 (과일반화 방지)."""
    from engines.workbook_v2.plan import _s3_arrow_para
    for t in ("→", "①", "*benign: 무해한", "A", "", "  ", "￼"):
        assert not _s3_arrow_para(t), repr(t)
    for t in ("", "\U000f0036", "↓", "⇩⇩"):
        assert _s3_arrow_para(t), repr(t)


def test_gate_g10_pua_detection():
    from engines.workbook_v2.gate import inspect_workbook_finish
    plan = {"flows": [{"step": "step3",
                       "units": [[{"t": "body", "s": "S"}]]}]}
    mk = lambda paras: {"stories": [{"paragraphs": paras}],
                        "stale_pages": []}
    # 단독 PUA 단락 → critical
    rep = inspect_workbook_finish(
        {}, plan, mk([{"t": "\r", "s": "S"},
                      {"t": "정상 본문 paragraph", "s": "S"}]))
    assert any("[특수문자]" in c for c in rep["critical"])
    assert rep["stats"]["pua_solo"] == 1
    # 본문 혼입 → warning (critical 아님)
    rep = inspect_workbook_finish(
        {}, plan, mk([{"t": "본문 \U000f0036 혼입", "s": "S"}]))
    assert not any("[특수문자]" in c for c in rep["critical"])
    assert any("[특수문자]" in w for w in rep["warnings"])
    # 깨끗한 출력 + 앵커(U+FFFC)는 미발동
    rep = inspect_workbook_finish(
        {}, plan, mk([{"t": "정상 본문￼", "s": "S"}]))
    assert not any("[특수문자]" in c
                   for c in rep["critical"] + rep["warnings"])


def test_round4_c05_golden_plan_has_no_pua():
    """W13 편입 c05 골든 재플랜 — PUA 화살표 18건 삭제 + 요약문 배경."""
    golden = os.path.join(CORPUS, "workbook_v2", "r3c05mock", "golden",
                          "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          _is_pua)
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="모의고사")
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert not any(any(_is_pua(ch) for ch in p.get("t", ""))
                   for p in paras), "PUA 화살표 잔존"
    assert len(fl["units"]) == 25          # 유닛 수 무변 (W13 가드와 일치)
    assert sum(1 for p in paras if "배경" in (p.get("s") or "")) >= 18


# ── 코퍼스 가드: 후보③ (교과서 서술형 Step3 단독) ──────────────────────────

def test_round4_c03_parse_snapshot(tmp_path):
    """r4c03essay 커스텀 리플레이 — manuscript_folder 메타 경로 (r3 교과서
    2종과 동일 방식). Step3/ 하위 폴더의 서술형 hwpx가 textbook 경로로
    소비된다."""
    import _replay
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    case_dir = os.path.join(CORPUS, "textbook_workbook", "r4c03essay")
    job = str(tmp_path / "job")
    os.makedirs(job)
    for n in os.listdir(os.path.join(case_dir, "meta")):
        with open(os.path.join(case_dir, "meta", n)) as f:
            val = f.read()
        with open(os.path.join(job, n), "w") as f:
            f.write(val)
    with open(os.path.join(job, "manuscript_folder.txt"), "w") as f:
        f.write(os.path.join(case_dir, "inputs_folder"))
    logs = []
    json_path = TextbookWorkbookV2Engine().parse({"manuscripts": []}, job,
                                                 logs.append)
    produced = _replay.canonicalize(
        json.load(open(json_path, encoding="utf-8")), [job])
    golden = _replay.canonicalize(
        json.load(open(os.path.join(case_dir, "golden", "content.json"),
                       encoding="utf-8")), [])
    diff = _replay.first_diff(produced, golden)
    assert diff is None, diff


def test_round4_c03_plan_essay_stems_and_blanks():
    """후보③ 골든 재플랜 — 조건 지시문 발문(…시오. [3과])이 번호 스타일,
    <조건>/<보기> 스타일, 학생 답란('정답: ___')은 삭제되지 않고 보존."""
    golden = os.path.join(CORPUS, "textbook_workbook", "r4c03essay",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    st3 = c["steps"]["step3"]
    items = (st3.get("normal") or []) + (st3.get("short") or [])
    assert len(items) == 1 and items[0]["question_num"] == "textbook"
    n_src = len(items[0]["paragraphs"])
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    ensure_step3_kinds(st3)
    plan = steps_to_plan(c["steps"], workbook_type="교과서")
    assert plan.get("warnings") == []
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert len(paras) == n_src == 161      # 서술형 원고 전 단락 보존
    def sty(prefix):
        return [p for p in paras if (p.get("t") or "").startswith(prefix)]
    assert "번호" in sty("다음 글의 빈칸 부분을 <보기>의")[0]["s"]
    assert "조건" in sty("<조건>")[0]["s"]
    assert "보기" in sty("<보기>")[0]["s"]
    blanks = [p for p in paras if (p.get("t") or "").startswith("정답: _")]
    assert len(blanks) >= 5                # 학생 답란 보존 (삭제 금지)


# ── 코퍼스 가드: 후보⑥ (리딩파워 기출 문제모음 177문제) ────────────────────

def test_round4_c06_golden_pool_step3():
    """후보⑥ 골든 — 문항수 표기 라우팅으로 step3 단일 풀 소비, 발문/선지
    구조 대량 인식, 플랜에서 PUA 화살표 삭제."""
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r4c06rpcr",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    st3 = c["steps"]["step3"]
    assert st3["normal_count"] == 1
    paras = st3["normal"][0]["paragraphs"]
    assert len(paras) > 1000
    kinds = {p.get("kind") for p in paras}
    assert {"Q", "P", "C", "Cond", "Box"} <= kinds
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          _is_pua)
    from engines.ebs_workbook_v2.engine import _STEP_MAP
    ensure_step3_kinds(st3)
    plan = steps_to_plan(c["steps"], workbook_type="EBS",
                         step_map=dict(_STEP_MAP))
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    pl = [p for u in fl["units"]
          for p in (u["paras"] if isinstance(u, dict) else u)]
    # PUA '단독' 화살표 2건은 삭제, 발문은 번호 스타일 157+
    solo = [p for p in pl
            if p.get("t") and all(_is_pua(ch) for ch in p["t"].strip())]
    assert solo == []
    assert sum(1 for p in pl if "번호" in (p.get("s") or "")) >= 157


# ── D3: 교과서 step3 문항번호 잔재 프레임 삭제 (clear_steps) ────────────────

def test_round4_textbook_deco_clear_steps_with_labels(tmp_path):
    """라벨이 있는 교과서(c13/c15류)도 clear_steps 포함 — 갱신+잔재 삭제
    동시 (기존 갱신 동작 무변, 실행기가 step3 페이지 잔재만 추가 정리)."""
    import json as _json
    from engines.textbook_workbook_v2.engine import (
        TextbookWorkbookV2Engine, _NUMBER_FRAME_STEPS)
    job = tmp_path / "job"
    job.mkdir()
    for k in ("subject", "publisher", "lesson"):
        (job / f"{k}.txt").write_text("x", encoding="utf-8")
    content = {"steps": {"step1_c2": {"paragraphs": [
        {"text": "1. p10-본문1"}, {"text": ""},
        {"text": "An example passage sentence for label extraction here."},
    ]}}}
    (job / "content.json").write_text(
        _json.dumps(content, ensure_ascii=False), encoding="utf-8")
    deco = TextbookWorkbookV2Engine()._plan_decorations(str(job), {})
    pn = deco["passage_numbers"]
    assert pn["clear_steps"] == ["step3"]
    assert pn["steps"] == list(_NUMBER_FRAME_STEPS)


def test_round4_jsx_clear_steps_present():
    """실행기 JSX에 clear_steps 처리 이식 확인 (op 키 계약 가드)."""
    src = open(os.path.join(os.path.dirname(TESTS_DIR),
                            "core", "jsx", "workbook_flow.body.jsx"),
               encoding="utf-8").read()
    assert "clear_steps" in src
    assert "지문번호 잔재 프레임 삭제" in src
