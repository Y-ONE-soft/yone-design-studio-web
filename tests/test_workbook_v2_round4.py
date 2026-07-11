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
