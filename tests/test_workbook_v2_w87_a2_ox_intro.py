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
재사용한다.)

후속(같은 날, 사용자 지적 "EBS랑 교과서도 똑같이 들어가야 해"): 처음엔
workbook_type=="모의고사"로만 게이트했다가 너무 좁았다 — 교과서(textbook_
workbook_v2)는 모의고사와 **같은 내지 파일**을 쓰고, EBS 리딩파워(ebs_
workbook_v2)도 스타일 인벤토리 실측으로 이 스타일이 **있다**. 반대로
workbook_type="EBS" 값을 똑같이 쓰는 수능특강(suneungteukgang_workbook_v2)
분석/문제 내지는 이 스타일이 **없다**(B1/B2류 번호 스타일 자체가 없는
계열) — 같은 문자열 "EBS"가 서로 다른 두 내지 계열을 가리켜 workbook_type
만으로는 못 가른다. 그래서 workbook_type 휴리스틱을 버리고, `steps_to_plan`
에 명시적 `a2_ox_intro` 인자를 추가해(기본 True) 스타일이 없는 계열만
호출부(suneungteukgang_workbook_v2.prepare_jsx)에서 False로 끈다.
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
    res = build_step1_a2(d)                    # ox_intro 기본값 True
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
    res = build_step1_a2(d)
    assert any(_INTRO in p["t"] for u in res["units"] for p in
              (u["paras"] if isinstance(u, dict) else u))


def test_ox_intro_false_is_fully_silent():
    """호출부가 명시적으로 끄면 완전 무접촉 — 다른 단락도 그대로."""
    from engines.workbook_v2.plan import build_step1_a2, unit_paras
    d = _load("0a5da924")["step1_a2"]
    on = build_step1_a2(d, ox_intro=True)
    off = build_step1_a2(d, ox_intro=False)
    assert len(on["units"]) == len(off["units"])
    for u_on, u_off in zip(on["units"], off["units"]):
        rows_on = unit_paras(u_on)
        rows_off = unit_paras(u_off)
        assert not any(r["t"] == _INTRO for r in rows_off)
        assert [r for r in rows_on if r["t"] != _INTRO] == rows_off


def test_steps_to_plan_threads_a2_ox_intro_flag():
    """steps_to_plan(a2_ox_intro=...)이 실제로 step1_a2 빌더에 전달된다."""
    from engines.workbook_v2.plan import steps_to_plan
    steps = {"step1_a2": _load("0a5da924")["step1_a2"]}
    on = steps_to_plan(steps)                  # 기본값 True
    off = steps_to_plan(steps, a2_ox_intro=False)
    on_flow = next(f for f in on["flows"] if f["step"] == "step1_a2")
    off_flow = next(f for f in off["flows"] if f["step"] == "step1_a2")
    on_texts = {p["t"] for u in on_flow["units"] for p in u}
    off_texts = {p["t"] for u in off_flow["units"] for p in u}
    assert _INTRO in on_texts
    assert _INTRO not in off_texts


def test_suneungteukgang_engine_opts_out_explicitly():
    """수능특강 분석/문제 내지는 이 스타일이 없다 — 엔진이 명시적으로 끈다."""
    src = open(os.path.join(
        os.path.dirname(TESTS_DIR), "engines", "suneungteukgang_workbook_v2",
        "engine.py"), encoding="utf-8").read()
    assert "a2_ox_intro=False" in src
