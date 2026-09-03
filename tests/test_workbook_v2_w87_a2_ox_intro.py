"""W87 — 본문 O/X 섹션 발문("다음 글의 내용과 일치하면 O, 일치하지 않으면
X를 고르시오.") 누락.

사용자 지적(2026-09-03, 명일2_워크북04 완성본 역참조): STEP1 A2(본문 O/X)
섹션에 이 발문이 유닛마다 반복돼야 하는데 조판물엔 아예 없었다.

원인: 이 문장은 **어느 원고에도 없다**(전 코퍼스 확인) — Step3의
"다음 글을 읽고 물음에 답하시오."(_STEP3_SET_INTRO)처럼 완제품이 유닛마다
엔진이 심어 인쇄하는 문구인데, A2에는 그 삽입 로직 자체가 없었다.

(과거 시도 W86은 이 문구를 섹션 머리 띠에 프레임 복제로 한 번만 넣었는데,
실물 완성본을 열어 직접 확인해 보니 틀렸다 — 이 발문은 머리 띠가 아니라
**본문 흐름 안에서 지문마다 반복**되고, 스타일은 새로 만든 게 아니라
B2(내용 종합) 섹션의 번호 스타일("STEP 01 > B2_내용 종합 번호")을 그대로
재사용한다. 이 파일은 그 올바른 메커니즘만 검증한다.)
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_INTRO = "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오."
_INTRO_STYLE = "STEP 01 > B2_내용 종합 번호"


def _load(case):
    path = os.path.join(TESTS_DIR, "corpus", "workbook", case,
                        "golden", "content.json")
    return json.load(open(path, encoding="utf-8"))["steps"]


def test_intro_inserted_once_per_unit_after_passage():
    from engines.workbook_v2.plan import build_step1_a2, unit_paras
    d = _load("0a5da924")["step1_a2"]
    res = build_step1_a2(d, workbook_type="모의고사")
    for u in res["units"]:
        rows = unit_paras(u)
        idx = [i for i, r in enumerate(rows) if r["t"] == _INTRO]
        assert len(idx) == 1, rows          # 유닛당 정확히 1회
        i = idx[0]
        assert rows[i]["s"] == _INTRO_STYLE
        assert rows[i - 1]["s"] == "STEP 01 > A2_본문 박스"   # 지문 바로 뒤
        assert rows[i + 1]["s"] == "STEP 01 > A2_OX문제"      # 첫 문항 바로 앞


def test_intro_text_not_sourced_from_manuscript():
    """이 문장은 원고 어디에도 없다 — 엔진이 심은 것이지 원고 보존이 아니다."""
    from engines.workbook_v2.plan import build_step1_a2
    d = _load("0a5da924")["step1_a2"]
    raw_texts = [p["text"] for p in d["paragraphs"]]
    assert not any(_INTRO in t for t in raw_texts)
    res = build_step1_a2(d, workbook_type="모의고사")
    assert any(_INTRO in p["t"] for u in res["units"] for p in
              (u["paras"] if isinstance(u, dict) else u))


def test_intro_gated_to_moui_gosa_template_only():
    """W87 후속: 스타일은 모의고사(워크북_C) 계열에만 실측 확인됐다 — EBS/
    수능특강/교과서 파생 엔진의 다른 내지엔 이 스타일이 없어(스타일 인벤토리
    실측) workbook_type이 다르면 발문을 심지 않는다(무접촉 — 조판이 없는
    스타일을 지어내지 않는다)."""
    from engines.workbook_v2.plan import build_step1_a2, unit_paras
    d = _load("0a5da924")["step1_a2"]
    for wt in ("EBS", "교과서"):
        res = build_step1_a2(d, workbook_type=wt)
        for u in res["units"]:
            rows = unit_paras(u)
            assert not any(r["t"] == _INTRO for r in rows), (wt, rows)


def test_step1a2_is_context_builder_receiving_workbook_type():
    from engines.workbook_v2.plan import _CTX_BUILDERS
    assert "step1_a2" in _CTX_BUILDERS
