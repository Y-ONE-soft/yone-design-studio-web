"""워크북 v2 플랜 빌더 가드 — step3 (W1) + 순수 텍스트 6스텝 (W2)."""
import json
import os
import re

from engines.workbook_v2.plan import steps_to_plan

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")


def _inventory():
    return set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_workbookC.json"),
        encoding="utf-8"))["paragraph_styles"])


def _load(case):
    path = os.path.join(TESTS_DIR, "corpus", "workbook", case,
                        "golden", "content.json")
    return json.load(open(path, encoding="utf-8"))


def _flow(plan, step):
    return next(f for f in plan["flows"] if f["step"] == step)


def _words(texts):
    out = set()
    for t in texts:
        out.update(w.lower() for w in _RE_WORD.findall(t))
    return out


def _plan_words(flow):
    return _words(p["t"] for u in flow["units"] for p in u)


def test_step3_builder_corpus():
    inv = set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_workbookC.json"),
        encoding="utf-8"))["paragraph_styles"])
    case = os.path.join(TESTS_DIR, "corpus", "workbook", "0a5da924")
    c = json.load(open(os.path.join(case, "golden", "content.json"),
                       encoding="utf-8"))
    plan = steps_to_plan(c["steps"])
    s3 = next(f for f in plan["flows"] if f["step"] == "step3")
    assert len(s3["units"]) == 22
    assert s3["target"] == {"master": "O"}
    styles = {p["s"] for u in s3["units"] for p in u}
    assert all(s in inv for s in styles), styles - inv
    # 정답/그룹헤더는 제거돼야 함 (kind GH/A → 미포함)
    texts = [p["t"] for u in s3["units"] for p in u]
    assert not any(t.strip() in ("정답", "[정답]") for t in texts)


# ── W2: 순수 텍스트 6스텝 ────────────────────────────────────────────────────
# 케이스별 기대 유닛 수 = 지문 수 (모의고사 18지문 / 리딩파워·교과 3지문).
_W2_UNITS = {
    "0a5da924": {"step1_a1": 18, "step1_a1_2": 18, "step1_b2": 18,
                 "step1_c2": 18, "step2_a1": 18, "step2_a1_btm": 18,
                 "step2_c1": 18},
    "01accf5a": {"step1_a1": 3, "step1_a1_2": 3, "step1_c2": 3,
                 "step2_a1": 3, "step2_a1_btm": 3, "step2_c1": 3},
    "0807ebd8": {"step1_a1": 3, "step1_a1_2": 3, "step1_c2": 3,
                 "step2_a1": 3, "step2_a1_btm": 3, "step2_c1": 3},
    "0e3844d2": {"step1_a1": 3, "step1_a1_2": 3, "step1_c2": 3,
                 "step2_a1": 3, "step2_a1_btm": 3, "step2_c1": 3},
}


def test_w2_styles_and_units_corpus():
    """(a) 사용 스타일 전부 실물 인벤토리 존재 + (c) 유닛 수 = 지문 수."""
    inv = _inventory()
    for case, expected in _W2_UNITS.items():
        plan = steps_to_plan(_load(case)["steps"])
        for step, n_units in expected.items():
            flow = _flow(plan, step)
            assert len(flow["units"]) == n_units, (case, step)
            styles = {p["s"] for u in flow["units"] for p in u}
            assert None not in styles, (case, step)
            assert styles <= inv, (case, step, styles - inv)


def test_w2_content_conservation_corpus():
    """(b) 내용 보존 — 의도적 삭제 룰(빈 단락/헤더/Hard/비지문) 제외 전량."""
    from engines.workbook_v2.plan import (_is_blank, _is_bracket_para,
                                          _has_circled, _RE_HARD,
                                          is_header_line, is_a1_header)
    for case in _W2_UNITS:
        steps = _load(case)["steps"]
        plan = steps_to_plan(steps)
        for step in _W2_UNITS[case]:
            raw = [p["text"] for p in steps[step]["paragraphs"]]
            flow = _flow(plan, step)
            got = _plan_words(flow)
            if step in ("step1_a1", "step1_a1_2"):
                keep = [t for t in raw
                        if not _is_blank(t) and not _RE_HARD.match(t)]
                assert got == _words(keep), (case, step)
            elif step == "step1_b2":
                assert got == _words(raw), (case, step)   # 삭제 없음
            elif step in ("step1_c2", "step2_c1"):
                keep = [t for t in raw
                        if not is_header_line(t) and not _is_blank(t)]
                assert got == _words(keep), (case, step)
            elif step == "step2_a1":
                # 헤더는 {tail}로 변환 — 비헤더 내용은 전량 보존
                keep = [t for t in raw if not is_a1_header(t)]
                plan_body = [p["t"] for u in flow["units"] for p in u
                             if not re.match(r"^\{[^}]*\}$", p["t"])]
                assert _words(plan_body) == _words(keep), (case, step)
                n_hdr = sum(1 for t in raw if is_a1_header(t))
                n_conv = sum(1 for u in flow["units"] for p in u
                             if re.match(r"^\{[^}]+\}$", p["t"]))
                assert n_conv == n_hdr, (case, step)
            elif step == "step2_a1_btm":
                keep = [t for t in raw if _has_circled(t)]
                assert got == _words(keep), (case, step)


def test_w2_step1_a1_semantics():
    """1A1: ❮❯→[] 치환, 지문번호→NUM, 본문→A1_어휘 선택, 빈 단락 제거."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_a1")
    for unit in flow["units"]:
        assert unit[0]["s"] == "STEP 01 > A_어휘 선택 번호"
        assert re.match(r"^\[\d+(?:~\d+)?\]$", unit[0]["t"])
        for p in unit[1:]:
            assert p["s"] == "STEP 01 > A1_어휘 선택"
            assert "❮" not in p["t"] and "❯" not in p["t"]
            assert p["t"].strip()
    body = flow["units"][0][1]["t"]
    assert "(1)[ ⓐ learned  / ⓑ forgot ]" in body


def test_w2_step1_b2_semantics():
    """1B2: [N]→NUM, 본문→박스, (N)→번호, 원문자→선지."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_b2")
    unit = flow["units"][0]
    assert unit[0]["t"] == "[20]"
    assert unit[0]["s"] == "STEP 01 > A_어휘 선택 번호"
    assert unit[1]["s"] == "STEP 01 > A2_본문 박스"
    styles = {p["t"][:3]: p["s"] for p in unit if p["t"].strip()}
    assert styles["(1)"] == "STEP 01 > B2_내용 종합 번호"
    assert styles["① B"] == "STEP 01 > B2_내용 종합 선지"


def test_w2_wordfill_semantics():
    """1C2/2C1: 헤더 제거, 한글 2자+ → 한글해석 스타일."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    for step, st_p, st_k in [
            ("step1_c2", "STEP 01 > C2_빈칸 어휘",
             "STEP 01 > C2_빈칸 어휘 한글"),
            ("step2_c1", "STEP 02 > C1_빈칸 어법",
             "STEP 01 > C2_빈칸 어휘 한글")]:
        flow = _flow(plan, step)
        for u in flow["units"]:
            for p in u:
                assert not re.match(r"^\d+\.\s*p\d+", p["t"]), (step, p["t"])
                want = st_k if re.search(r"[가-힣].*[가-힣]",
                                         p["t"], re.S) else st_p
                assert p["s"] == want, (step, p["t"][:40])


def test_w2_step2_a1_semantics():
    """2A1: 헤더 → {tail} 정규화 (본문번호/no.N/Example)."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step2_a1")
    assert flow["units"][0][0]["t"] == "{20}"
    assert all(u[0]["t"].startswith("{") for u in flow["units"])
    assert all(p["s"] == "STEP 02 > A1_어법 선택"
               for u in flow["units"] for p in u)
    # Example 라벨 케이스 (리딩파워)
    plan2 = steps_to_plan(_load("01accf5a")["steps"])
    heads = [u[0]["t"] for u in _flow(plan2, "step2_a1")["units"]]
    assert heads == ["{Example}", "{1}", "{2}"]


def test_w2_step2_a1_btm_semantics():
    """2A1 하단: 원문자 지문만 유지(1지문=1유닛), 지문 밑줄 문자스타일."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step2_a1_btm")
    assert flow.get("ul_style") == "공통 > 지문 밑줄"
    for u in flow["units"]:
        assert len(u) == 1
        assert u[0]["s"] == "STEP 02 > A1_어법 선택 하단"
        assert any(0x2460 <= ord(ch) <= 0x2473 for ch in u[0]["t"])
