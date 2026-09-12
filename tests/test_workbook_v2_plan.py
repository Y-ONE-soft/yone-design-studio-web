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
    # 2026-09-12 사용자 확정 스펙: 모의고사 짤지문은 별도 스토리
    # (step3_short — 간지 뒤 짤지문 섹션). 합계는 그대로 22.
    s3s = next(f for f in plan["flows"] if f["step"] == "step3_short")
    assert len(s3["units"]) == 18 and len(s3s["units"]) == 4
    assert s3["target"] == {"master": "O"}
    assert s3s["target"]["split_after_marker"] == "짤지문"
    # 유닛은 리스트 또는 {"paras": [...]} (왼쪽 면 시작 유닛)
    paras = [p for f in (s3, s3s) for u in f["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    # "$BASIC" 은 실행기 센티널(문서 내장 [기본 단락]) — 템플릿 스타일
    # 인벤토리 대상이 아니다 (지문번호 {YYMMQQ} 단락이 쓴다)
    styles = {p["s"] for p in paras if not str(p["s"]).startswith("$")}
    # W45: 답란 신설 스타일(S_답란)은 템플릿 반영 전이라 인벤토리에 없을 수
    # 있다 — 그 단락은 반드시 폴백(s_fb, 인벤토리 존재)을 함께 실어야 한다.
    pending = {p["s"] for p in paras if p.get("s_fb")}
    assert all(p.get("s_fb") in inv for p in paras if p.get("s_fb"))
    assert all(s in inv for s in styles - pending), styles - inv - pending
    # 정답/그룹헤더는 제거돼야 함 (kind GH/A → 미포함)
    texts = [p["t"] for p in paras]
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
            # $BASIC = 문서 내장 [기본 단락] 센티널 — 인벤토리 밖 허용
            # (W21 r11: 지문번호 [N]은 v1 파리티로 [기본 단락])
            assert styles <= (inv | {"$BASIC"}), (case, step, styles - inv)


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
    """1A1: ❮❯→[] 치환, 지문번호→기본 단락, 본문→A1_어휘 선택, 빈 단락 제거.

    지문번호 [N] = $BASIC (W21 r11): v1 processStep1A1은 전체 BASIC_PARA 후
    본문 구간만 스타일링 — S1_A_NUM('A_어휘 선택 번호')은 선언만 되고 미사용.
    v1 실물(워크북03(외부지문) 스토리 21) '[1]' = [기본 단락] 실측."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_a1")
    for unit in flow["units"]:
        assert unit[0]["s"] == "$BASIC"
        assert re.match(r"^\[\d+(?:~\d+)?\]$", unit[0]["t"])
        for p in unit[1:]:
            assert p["s"] == "STEP 01 > A1_어휘 선택"
            assert "❮" not in p["t"] and "❯" not in p["t"]
            assert p["t"].strip()
    body = flow["units"][0][1]["t"]
    assert "(1)[ ⓐ learned  / ⓑ forgot ]" in body


def test_w2_step1_b2_semantics():
    """1B2: [N]→기본 단락(W21 r11 — v1 실물 파리티), 본문→박스, (N)→번호,
    원문자→선지."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_b2")
    unit = flow["units"][0]
    assert unit[0]["t"] == "[20]"
    assert unit[0]["s"] == "$BASIC"
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


# ── W3: 아이콘 4스텝 (1A2/1B1/2B1/2C2) ──────────────────────────────────────
# 유닛 수 기대치 (0a5da924 = 모의고사 18지문. 1B1은 지문당 2유닛(본문+하단문제),
# 2C2는 본세트+모범예시 세트 = 지문당 2유닛).
_W3_UNITS = {
    "0a5da924": {"step1_a2": 18, "step1_b1": 36, "step2_b1": 18,
                 "step2_c2": 36},
}
# "$BASIC" = 문서 내장 [기본 단락] 센티널 (인벤토리 실물 아님 — 실행기 해석)
_BASIC = "$BASIC"


def _icons(flow):
    return [p for u in flow["units"] for p in u if p.get("icon")]


def test_w3_styles_and_units_corpus():
    """사용 스타일 전부 실물 인벤토리(+$BASIC 센티널) + 유닛 수."""
    inv = _inventory() | {_BASIC}
    for case, expected in _W3_UNITS.items():
        plan = steps_to_plan(_load(case)["steps"])
        for step, n_units in expected.items():
            flow = _flow(plan, step)
            assert len(flow["units"]) == n_units, (case, step)
            styles = {p["s"] for u in flow["units"] for p in u}
            assert None not in styles, (case, step)
            # $BASIC = 문서 내장 [기본 단락] 센티널 — 인벤토리 밖 허용
            # (W21 r11: 지문번호 [N]은 v1 파리티로 [기본 단락])
            assert styles <= (inv | {"$BASIC"}), (case, step, styles - inv)


def test_w3_content_conservation_corpus():
    """내용 보존 — 의도 삭제 룰 반영 후 단어 전량 보존."""
    from engines.workbook_v2.plan import (_is_blank, _RE_C2_SOLO_NUM,
                                          is_header_line,
                                          _STEP1_A2_OX_INTRO)
    for case in _W3_UNITS:
        steps = _load(case)["steps"]
        plan = steps_to_plan(steps)
        # 1A2: 삭제는 빈 단락뿐 — ❮T/F❯ 토큰 제거는 단어(2자+)에 영향 없음.
        # W87: 원고엔 없는 O/X 발문을 유닛마다 엔진이 심는다 — 그 낱말만
        # 추가분으로 허용하고, 나머지는 그대로 전량 보존.
        raw = [p["text"] for p in steps["step1_a2"]["paragraphs"]]
        added = _plan_words(_flow(plan, "step1_a2")) - _words(raw)
        assert added <= _words([_STEP1_A2_OX_INTRO]), case
        assert _words(raw) <= _plan_words(_flow(plan, "step1_a2")), case
        # 1B1: 삭제 없음 ({주제}/{제목} 병합·정규화만)
        raw = [p["text"] for p in steps["step1_b1"]["paragraphs"]]
        assert _plan_words(_flow(plan, "step1_b1")) == _words(raw), case
        # 2B1: 헤더+빈 단락 삭제
        raw = [p["text"] for p in steps["step2_b1"]["paragraphs"]]
        keep = [t for t in raw if not is_header_line(t) and not _is_blank(t)]
        assert _plan_words(_flow(plan, "step2_b1")) == _words(keep), case
        # 2C2: (N) 단독줄 + 빈 단락 + 영어 전용 답 단락 삭제
        raw = [p["text"] for p in steps["step2_c2"]["paragraphs"]]
        keep = []
        for t in raw:
            if _RE_C2_SOLO_NUM.match(t) or _is_blank(t):
                continue
            has_br = "[" in t and "]" in t
            eng_only = (re.search(r"[A-Za-z]", t)
                        and not re.search("[가-힣]", t) and "/" not in t)
            if eng_only and not has_br:
                continue
            keep.append(t)
        assert _plan_words(_flow(plan, "step2_c2")) == _words(keep), case


def test_w3_step1_a2_semantics():
    """1A2: ❮T/F❯ 토큰 제거+TF 버튼 아이콘, 본문=박스, TF단락=OX."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_a2")
    icons = _icons(flow)
    assert len(icons) == 90         # 18지문 × 5문항
    for p in icons:
        assert p["icon"] == {"label": "TF 버튼", "pos": "end", "pad": " "}
        assert p["s"] == "STEP 01 > A2_OX문제"
        assert "❮" not in p["t"] and "❯" not in p["t"]
    unit = flow["units"][0]
    assert unit[0]["t"] == "[20]" and unit[0]["s"] == _BASIC
    assert unit[1]["s"] == "STEP 01 > A2_본문 박스"
    # W87: 지문 뒤·첫 문항 앞에 O/X 발문을 엔진이 심는다 (원고엔 없음 —
    # 실물 완성본 역참조로 확정한 스타일. B2 내용 종합 번호 재사용)
    assert unit[2]["t"] == "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오."
    assert unit[2]["s"] == "STEP 01 > B2_내용 종합 번호"
    # 토큰만 제거되고 앞 본문은 보존 (v1: range.remove()와 동일)
    assert unit[3]["t"].startswith("(1) People usually learn")
    assert "T / F" not in unit[3]["t"]


def test_w3_step1_b1_semantics():
    """1B1: {주제}/{제목} 병합·정규화, 다음 발문 아이콘+탭, 하단 스타일."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step1_b1")
    subj = [p for u in flow["units"] for p in u
            if p["s"] == "STEP 01 > B1_내용 정리 주제"]
    title = [p for u in flow["units"] for p in u
             if p["s"] == "STEP 01 > B1_내용 정리 제목" and p["t"]]
    assert len(subj) == 18 and len(title) == 18
    assert all(p["t"].startswith("{주제} ") for p in subj)
    assert all(p["t"].startswith("{제목} ") for p in title)
    icons = _icons(flow)
    assert len(icons) == 18
    for p in icons:
        assert p["icon"] == {"label": "STEP1 문제아이콘", "pos": "start",
                             "pad": "\t"}
        assert p["s"] == "STEP 01 > 하단 문제"
        assert re.match("^\\s*[\"'“”‘’]*다음", p["t"])
    # 하단 문제 유닛: 발문 → 지문 → 빈 줄 → 선지 5개 (선지 위 빈 줄 보장)
    u1 = flow["units"][1]
    assert u1[0]["s"] == "STEP 01 > 하단 문제"
    assert u1[1]["s"] == "STEP 01 > 하단 문제_지문"
    assert u1[2]["t"] == ""
    assert [p["s"] for p in u1[3:8]] == ["STEP 01 > 하단 문제_선지"] * 5
    # 본문 유닛: bracket=$BASIC, 다음 단락=본문 박스, {제목} 앞 빈 줄
    u0 = flow["units"][0]
    assert u0[0]["s"] == _BASIC
    assert u0[1]["s"] == "STEP 01 > B1_본문 박스"
    ti = next(i for i, p in enumerate(u0) if p["t"].startswith("{제목}"))
    assert u0[ti - 1]["t"] == ""


def test_w3_step2_b1_semantics():
    """2B1: 헤더 제거+유닛 분할, 전 단락 어법 OX + TF 버튼 링크 place."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step2_b1")
    paras = [p for u in flow["units"] for p in u]
    assert len(paras) == 133 and len(_icons(flow)) == 133
    for p in paras:
        assert p["s"] == "STEP 02 > B1_어법 OX"
        assert p["icon"] == {"label": "TF 버튼", "pos": "end", "pad": " ",
                             "mode": "place"}
        assert p["t"].strip()


def test_w3_step2_c2_semantics():
    """2C2: 한글→번호, 슬래시→보기, 보기 블록 끝 아이콘, 유닛 꼬리 빈 줄 2개."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    flow = _flow(plan, "step2_c2")
    icons = _icons(flow)
    assert icons and all(
        p["icon"] == {"label": "STEP2 영작 답지", "pos": "start"}
        and p["t"] == "" and p["s"] == _BASIC for p in icons)
    for u in flow["units"]:
        assert u[0]["s"] == _BASIC          # [N] bracket
        assert re.match(r"^\s*\[", u[0]["t"])
    # 보기 블록 끝 = 아이콘 단락 (보기 직후에만)
    for u in flow["units"]:
        for i, p in enumerate(u):
            if p.get("icon"):
                assert u[i - 1]["s"] == "STEP 02 > C2_영작 배열 보기"
    # 마지막 제외 각 유닛 꼬리에 빈 줄 2개 (bracket 앞 간격 보장)
    for u in flow["units"][:-1]:
        assert u[-1]["t"] == "" and u[-2]["t"] == ""
    # 영어 전용 답 단락은 삭제됨
    for u in flow["units"]:
        for p in u:
            t = p["t"]
            if (re.search(r"[A-Za-z]", t) and "/" not in t
                    and not ("[" in t and "]" in t)):
                assert re.search("[가-힣]", t), t[:60]


# ── W4: step1_c1 (문장 배열 — 최난) ─────────────────────────────────────────
# v1 processStep1C1 이식: 헤더 정규화 GREP, 프레임 분리(NEXT_PAGE/FRAME),
# 화살표 답지 아이콘, 하단 발문 삽입. 유닛은 {"paras", "page_break"} dict.

def _uparas(u):
    from engines.workbook_v2.plan import unit_paras
    return unit_paras(u)


def test_w4_step1_c1_units_and_styles():
    """모의고사 18지문 = 상단 18 + 하단 18 유닛, 헤더(2번째+) page_break."""
    inv = _inventory() | {_BASIC}
    plan = steps_to_plan(_load("0a5da924")["steps"])
    assert plan["unsupported"] == []            # step1_c1 완성 → 미지원 0
    flow = _flow(plan, "step1_c1")
    units = flow["units"]
    assert len(units) == 36
    # page_break: 첫 헤더 제외 헤더 유닛 17개만 (v1: h=1부터 NEXT_PAGE)
    pbs = [bool(u.get("page_break")) for u in units]
    assert sum(pbs) == 17
    assert pbs[0] is False                      # 첫 헤더
    assert all(pbs[i] for i in range(2, 36, 2))  # 상단 유닛(2번째+)
    assert not any(pbs[i] for i in range(1, 36, 2))  # 하단 유닛
    styles = {p["s"] for u in units for p in _uparas(u)}
    assert styles <= inv, styles - inv
    assert "STEP 01 > C1_문장 배열" in styles
    assert "STEP 01 > C1_문장 배열 하단" in styles
    assert "STEP 01 > C1_문장 배열 하단 지문" in styles


def test_w4_step1_c1_headers_normalized():
    """'1. p2-no.20' → '{20}' 정규화 + [기본 단락], 상단 유닛 선두."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    units = _flow(plan, "step1_c1")["units"]
    tops = units[0::2]
    for u in tops:
        head = _uparas(u)[0]
        assert re.match(r"^\{\d+(?:~\d+)?\}$", head["t"]), head["t"]
        assert head["s"] == _BASIC
    assert _uparas(tops[0])[0]["t"] == "{20}"


def test_w4_step1_c1_bottom_prompts_and_arrows():
    """하단 유닛 = 발문(하단 문제+아이콘) 선두, 유형별 발문, 화살표 18개."""
    plan = steps_to_plan(_load("0a5da924")["steps"])
    units = _flow(plan, "step1_c1")["units"]
    bottoms = units[1::2]
    circ, order = 0, 0
    for u in bottoms:
        ps = _uparas(u)
        assert ps[0]["s"] == "STEP 01 > 하단 문제"
        assert ps[0]["icon"] == {"label": "STEP1 문제아이콘",
                                 "pos": "start", "pad": "\t"}
        if "위치로 알맞은" in ps[0]["t"]:
            circ += 1
        elif "이어질 문장들의" in ps[0]["t"]:
            order += 1
        # 주어진 문장(하단) — 탭/선행 3+공백 제거됨
        btm = [p for p in ps if p["s"] == "STEP 01 > C1_문장 배열 하단"]
        assert len(btm) == 1
        assert not re.match(r"^\s{3,}", btm[0]["t"]) and "\t" not in btm[0]["t"]
        assert [p for p in ps
                if p["s"] == "STEP 01 > C1_문장 배열 하단 지문"]
    assert (circ, order) == (10, 8)             # 0a5da924 유형 구성
    arrows = [p for u in units for p in _uparas(u)
              if p.get("icon", {}).get("label") == "화살표 답지"]
    assert len(arrows) == 18
    for p in arrows:
        assert p["t"] == "" and p["s"] == _BASIC
        assert p["icon"] == {"label": "화살표 답지", "pos": "start"}
    # 화살표는 상단 유닛 끝(선지 뒤), 발문보다 앞 (v1 배치 순서)
    for u in units[0::2]:
        assert _uparas(u)[-1].get("icon", {}).get("label") == "화살표 답지"


def test_w4_step1_c1_content_conservation():
    """삭제 룰(공백 bracket/프리앰블/헤더 정규화) 외 내용 전량 보존."""
    for case in ("0a5da924", "01accf5a", "0807ebd8", "0e3844d2"):
        steps = _load(case)["steps"]
        flow = _flow(steps_to_plan(steps), "step1_c1")
        got = _words(p["t"] for u in flow["units"] for p in _uparas(u))
        # 헤더 줄 제외 원문 전량 보존 (헤더는 {N}으로 정규화됨)
        keep = [p["text"] for p in steps["step1_c1"]["paragraphs"]
                if not re.match(r"^\s*\d+\.\s*p", p["text"])]
        missing = _words(keep) - got
        assert not missing, (case, sorted(missing)[:8])


def test_w4_step1_c1_ebs_branch():
    """EBS: 헤더 page_break 없음(NEXT_FRAME), 화살표는 빈 단락 재사용 1개."""
    plan = steps_to_plan(_load("0807ebd8")["steps"], workbook_type="EBS")
    units = _flow(plan, "step1_c1")["units"]
    assert not any(u.get("page_break") for u in units)
    plan2 = steps_to_plan(_load("0807ebd8")["steps"])   # 비EBS 대조
    units2 = _flow(plan2, "step1_c1")["units"]
    assert sum(bool(u.get("page_break")) for u in units2) == 2  # 헤더 3-1


def test_w4_step1_c1_exclude_btm():
    """step1_c1_btm 제외: 하단(BTM/BTM_T/발문) 삭제, 상단 유닛만."""
    plan = steps_to_plan(_load("0a5da924")["steps"],
                         exclude=["step1_c1_btm"])
    units = _flow(plan, "step1_c1")["units"]
    assert len(units) == 18
    styles = {p["s"] for u in units for p in _uparas(u)}
    assert "STEP 01 > C1_문장 배열 하단" not in styles
    assert "STEP 01 > C1_문장 배열 하단 지문" not in styles
    assert "STEP 01 > 하단 문제" not in styles
    # step1_c1 전체 제외는 플로우 자체가 빠짐
    plan2 = steps_to_plan(_load("0a5da924")["steps"], exclude=["step1_c1"])
    assert not [f for f in plan2["flows"] if f["step"] == "step1_c1"]
