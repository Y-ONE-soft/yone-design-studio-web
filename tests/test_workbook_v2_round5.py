"""W15 품질 루프 5라운드 가드 — 후보④(모의고사 변형 211문제 pool) +
후보⑧(수능특강 원고 hwpx → 2단계 경로 침묵 유실).

결함 재현→수리 고정:
  D1 출처 마커 kind 오분류 (심경추론 마커 → 발문 스타일) → SRC kind
  D2 파서 선지 ① prepend가 마커를 오염 → 마커 boundary
  D3 문장삽입 P-CONTEXT 스캔이 마커에 막힘 → SRC 스킵
  D4 게이트 G11(마커오염/마커스타일)·G12(문장삽입배경)
  D5 수능특강 v2 verify 완제품 게이트 부재 → 스테이지별 통합
  D6 수능특강 v2 빈 플랜 침묵 성공 → prepare_jsx 조기 차단
"""
import json
import os

import pytest

from core.structure.paragraph_kind import classify_paragraphs
from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_v2.plan import build_step3

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_MARKER = "[202506H2_19심경추론_변형]"
_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_BG = "STEP 03 > 배경 올림포스"


# ── D1: 출처 마커 kind — taxonomy 오매칭 차단 ────────────────────────────────

def test_src_marker_kind():
    out = classify_paragraphs([
        {"text": "다음 글의 제목으로 가장 적절한 것은?"},
        {"text": _MARKER},                      # 수리 전: "심경추론"이 Q로 오매칭
        {"text": "[202506H2_25도표_변형]"},
        {"text": "[올림포스2 13강 Analysis]"},   # 변형] 아님 — SRC 아님
        {"text": "[Gateway]"},                  # 기존 GH 유지
    ])
    assert out[0]["kind"] == "Q"
    assert out[1]["kind"] == "SRC"
    assert out[2]["kind"] == "SRC"
    assert out[3]["kind"] != "SRC"
    assert out[4]["kind"] == "GH"


# ── D3: 문장삽입 배경 — 발문→마커→주어진 문장 순서에서 P-CONTEXT ─────────────

def test_insert_prompt_bg_skips_marker():
    out = classify_paragraphs([
        {"text": "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 "
                 "곳을 고르시오."},
        {"text": "[202506H2_21함축의미추론_변형]"},
        {"text": "However, this assumption is incorrect."},
        {"text": "Of central importance for understanding the development "
                 "of handedness is the fact that early hominids made tools "
                 "with their hands over long periods."},
    ])
    assert out[1]["kind"] == "SRC"
    assert out[2]["kind"] == "P-CONTEXT", "주어진 문장이 배경(P-CONTEXT)이어야 함"
    assert out[3]["kind"] == "P"


# ── D2: 파서 선지 자동번호가 마커를 오염시키지 않음 ──────────────────────────

def test_choice_prepend_skips_src_marker():
    from engines.workbook.parser import _add_step3_choice_numbers
    paras = [
        {"text": "다음 도표의 내용과 일치하지 않는 것은?"},
        {"text": "[202506H2_25도표_변형]"},
        {"text": "The graph above shows US dairy product imports from 2018 "
                 "to 2022."},
        {"text": "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?"},
    ]
    out = _add_step3_choice_numbers([dict(p) for p in paras])
    assert out[1]["text"] == "[202506H2_25도표_변형]", "마커에 ① 오염 금지"


def test_choice_prepend_still_numbers_choices_after_marker():
    from engines.workbook.parser import _add_step3_choice_numbers
    paras = [
        {"text": "다음 글의 제목으로 가장 적절한 것은?"},
        {"text": _MARKER},
        {"text": "Peter stepped out of the freezing night air and into the "
                 "brightly lit hospital lobby, holding his daughter."},
        {"text": "A Father's Night of Relief"},
        {"text": "When Silence Was the Answer"},
        {"text": "The Hospital That Never Sleeps"},
        {"text": "Waiting in Vain for a Diagnosis"},
        {"text": "A Fever That Changed Everything"},
    ]
    out = _add_step3_choice_numbers([dict(p) for p in paras])
    assert out[1]["text"] == _MARKER
    assert [p["text"][0] for p in out[3:8]] == ["①", "②", "③", "④", "⑤"]


# ── D1/배경: build_step3 — 마커 스타일 일관 + 화살표 배경이 마커를 통과 ──────

def test_build_step3_src_style_and_arrow_passthrough():
    step = {"normal": [{"question_num": "textbook", "code": "",
                        "paragraphs": [
        {"text": "다음 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), "
         "(B)에 들어갈 말로 가장 적절한 것은?", "kind": "Q"},
        {"text": _MARKER, "kind": "SRC"},
        {"text": "\U000F003B", "kind": "UNKNOWN"},     # PUA 요약 화살표
        {"text": "[202506H2_23주제추론_변형]", "kind": "SRC"},
        {"text": "People are more likely to wait for a larger reward.",
         "kind": "P"},
    ]}], "short": []}
    units = build_step3(step)["units"]
    paras = units[0]
    texts = [p["t"] for p in paras]
    assert "\U000F003B" not in texts, "PUA 화살표 단락은 삭제"
    styles = {p["t"][:14]: p["s"] for p in paras}
    assert styles[_MARKER[:14]] == _ST_P
    assert styles["[202506H2_23주제"] == _ST_P, "마커는 배경을 소비하지 않음"
    assert paras[-1]["s"] == _ST_BG, "배경은 마커 다음 실제 요약문에"


# ── D4: 게이트 G11/G12 — 수리 전 상태 재현으로 검출 실증 ─────────────────────

def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"], "b": [0, 0]}],
            "stale_pages": []}


def test_gate_g11_marker_style_and_pollution():
    dump = _dump([
        {"t": _MARKER, "s": _ST_P},
        {"t": "[202506H2_20주장추론_변형]", "s": _ST_P},
        {"t": "[202506H2_22어법_변형]", "s": _ST_Q},        # 오스타일 (수리 전)
        {"t": "①[202506H2_25도표_변형]", "s": "STEP 03 > S_선지 올림포스"},
    ])
    rep = inspect_workbook_finish({}, {"flows": [{"step": "step3",
                                                  "units": [[{"t": "x"}]]}]},
                                  dump)
    crit = " ".join(rep["critical"])
    assert "[마커오염]" in crit
    assert "[마커스타일]" in crit
    assert rep["stats"]["src_polluted"] == 1
    assert rep["stats"]["src_marker_styles"] == 2


def test_gate_g11_clean_when_uniform():
    dump = _dump([
        {"t": _MARKER, "s": _ST_P},
        {"t": "[202506H2_20주장추론_변형]", "s": _ST_P},
    ])
    rep = inspect_workbook_finish({}, {"flows": [{"step": "step3",
                                                  "units": [[{"t": "x"}]]}]},
                                  dump)
    assert not [c for c in rep["critical"] if "마커" in c]


def test_gate_g12_insert_bg():
    base = [
        {"t": _MARKER, "s": _ST_P},
        {"t": "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳을 "
              "고르시오.", "s": _ST_Q},
        {"t": "However, this assumption is incorrect.", "s": _ST_P},
    ]
    rep = inspect_workbook_finish(
        {}, {"flows": [{"step": "step3", "units": [[{"t": "x"}]]}]},
        _dump(base))
    assert any("[문장삽입배경]" in w for w in rep["warnings"]), "수리 전 상태 검출"

    fixed = [dict(base[0]), dict(base[1]),
             {"t": "However, this assumption is incorrect.", "s": _ST_BG}]
    rep2 = inspect_workbook_finish(
        {}, {"flows": [{"step": "step3", "units": [[{"t": "x"}]]}]},
        _dump(fixed))
    assert not any("[문장삽입배경]" in w for w in rep2["warnings"])


def test_gate_g12_scoped_to_marker_stories():
    """마커 없는 스토리(step1_c1 발문 등)는 G12 미적용 — false positive 방지."""
    dump = _dump([
        {"t": "아래 주어진 문장이 들어갈 위치로 알맞은 곳을 고르시오.",
         "s": "STEP 01 > 하단 문제"},
        {"t": "Some sentence.", "s": "C1_문장 배열 하단 지문"},
    ])
    rep = inspect_workbook_finish(
        {}, {"flows": [{"step": "step1_c1", "units": [[{"t": "x"}]]}]}, dump)
    assert not any("[문장삽입배경]" in w for w in rep["warnings"])


# ── c04 코퍼스 통합 앵커 — 플랜 수준 완제품 특성 ─────────────────────────────

@pytest.fixture(scope="module")
def c04_plan():
    import re
    golden = os.path.join(TESTS_DIR, "corpus", "workbook_v2", "r5c04mock211",
                          "golden", "content.json")
    content = json.load(open(golden, encoding="utf-8"))
    step3 = content["steps"]["step3"]
    return build_step3(step3), step3, re


def test_c04_pool_plan_anchors(c04_plan):
    plan, step3, re_mod = c04_plan
    paras = [p for u in plan["units"] for p in u]
    markers = [p for p in paras
               if re_mod.match(r"^\[[^\[\]]{2,}변형\]$", p["t"].strip())]
    assert len(markers) == 183
    assert {p["s"] for p in markers} == {_ST_P}, "마커 스타일 일관(지문)"
    assert not [p for p in paras
                if re_mod.match(r"^[①-⑤]\[", p["t"].strip())], "① 오염 없음"
    bg = [p for p in paras if p["s"] == _ST_BG]
    assert len(bg) >= 21, "요약 화살표 9 + 문장삽입 12 배경"
    pua = [ch for p in paras for ch in p["t"]
           if 0xE000 <= ord(ch) <= 0xF8FF or 0xF0000 <= ord(ch) <= 0xFFFFD]
    assert not pua, "U+F003B 요약 화살표는 플랜에서 소거"


# ── D5/D6: 수능특강 v2 — 빈 플랜 차단 + 게이트 통합 ─────────────────────────

@pytest.fixture()
def stg_engine(tmp_path, monkeypatch):
    import engines.suneungteukgang_workbook_v2.engine as eng_mod
    real = eng_mod._load_v1_config

    def _patched():
        cfg = real()
        cfg["indd_output_dir"] = str(tmp_path / "out")
        cfg["indd_original"] = {
            "analysis": os.path.join(REPO, "data_corpus", "template_test",
                                     "수능특강_분석_내지.indd"),
            "problem": os.path.join(REPO, "data_corpus", "template_test",
                                    "수능특강_문제_내지.indd"),
        }
        return cfg

    monkeypatch.setattr(eng_mod, "_load_v1_config", _patched)
    return eng_mod.SuneungteukgangWorkbookV2Engine()


def test_stg_v2_empty_plan_blocked(stg_engine, tmp_path):
    """W15 c08 재현: 원고가 어느 스텝에도 매핑 안 됨 → 조기 차단.

    수리 전에는 빈 템플릿 2개가 verify ok=True로 '성공'했다
    (실증: data_corpus/round5/c08_stg — 분석/문제 PDF까지 생성)."""
    job = tmp_path / "job"
    job.mkdir()
    (job / "lesson.txt").write_text("12강")
    content = {"steps": {"step3": {"normal": [], "short": [],
                                   "normal_count": 0, "short_count": 0}}}
    json_path = job / "content.json"
    json_path.write_text(json.dumps(content, ensure_ascii=False))
    with pytest.raises(ValueError, match="유닛이 0개"):
        stg_engine.prepare_jsx(str(json_path), str(job), lambda m: None)


def test_stg_v2_verify_runs_gate_per_stage(stg_engine, tmp_path,
                                           monkeypatch):
    """verify가 스테이지별로 완제품 게이트를 실행하고 critical을 ok=False로
    반영하는지 — 빈 플랜 덤프(수리 전 c08 상태)로 G7 critical 2건 기대."""
    import core.inspect
    job = tmp_path / "job"
    job.mkdir()
    content_path = job / "content.json"
    content_path.write_text(json.dumps({"steps": {}}, ensure_ascii=False))
    pdf = job / "x.pdf"
    pdf.write_text("pdf")
    stages = []
    for label, kor in (("analysis", "분석본"), ("problem", "문제본")):
        plan_path = job / f"render_plan_{label}.json"
        plan_path.write_text(json.dumps({"flows": [], "warnings": []},
                                        ensure_ascii=False))
        stages.append({"label": label, "kor": kor,
                       "plan_path": str(plan_path),
                       "indd_path": str(job / f"{label}.indd"),
                       "pdf_path": str(pdf),
                       "log_path": str(job / f"log_{label}.txt")})
    (job / ".settings.json").write_text(json.dumps({
        "stages": stages, "json_path": str(content_path),
        "unsupported": []}, ensure_ascii=False))

    monkeypatch.setattr(core.inspect, "dump_indd",
                        lambda indd, out, log: {"stories": [],
                                                "stale_pages": []})
    result = stg_engine.verify(str(job), lambda m: None)
    assert result["ok"] is False
    crits = [w for w in result["warnings"] if "[빈플랜]" in w]
    assert any("[분석본]" in c for c in crits)
    assert any("[문제본]" in c for c in crits)
