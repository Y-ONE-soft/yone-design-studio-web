"""W40 — 사용자 육안 검수 6건 가드 (workbook_supp_v2 0a5da924 실증).

결함 (부교재 워크북 "워크북E2E테스트" — 문항 번호는 전권 통산):
  1. 다열 선지("(A)(B)(C)" 헤더 + "①x\ty\tz") 열이 안 맞음 — v1 실물
     실측(배재2_워크북01: 기본 12.7mm 탭 그리드 관행)을 실행기
     applyChoiceTabs가 명시 탭스톱으로 재현. 게이트 G42 (덤프 cx).
  2. 프레임 하단 발문 고아 ("38 다음 글에서 전체 흐름과 관계 없는
     문장은?" 단독 잔류) — question_keep_op의 stem_keep 계약 + 실행기
     enforceStemKeep. 게이트 G41 (fc 실측 — 소급 8건 실증).
  3. 순서배열 선지 "(A) － (C) － (B)" 5행 원문자 누락 — 원고 hwpx 2열
     표(번호 셀|순열 셀)의 단독 ①~⑤ 셀을 _strip_step3_answers가 정답
     번호로 오인 제거 (병합이 번호 매칭 경로에 빠져 있었다). 파서
     _merge_step3_split_choice_numbers 선호출 + 플랜 _s3_number_order_rows
     폴백. 게이트 G38 (소급 90행 실증).
     — G10(PUA)/G29(글리프)/G36(TF선지)이 못 잡은 이유: 이 결함은 문자
     인코딩/폰트 문제가 아니라 파싱 단계의 '단락 삭제'라 출력에 흔적이
     없었고, G36은 T/F 행 전용이다. G38이 순열 행 형태를 출력에서 직접
     검사해 봉합.
  4. 215번 네모 어법 선택형 지문에 배경 오적용 — 판정 2(P_ORDER_LABEL)가
     "(A)\t(B)\t(C)" 선지 헤더를 순서배열 항목으로 오인. nxt kind P 한정
     + 유형 veto (expects_given_block False, Q 한정) + 요약문 형태 예외.
     게이트 G39 (소급 22건 실증).
  5. <보기 B> 아래 "(A) ______" = 답란 — W39 콜론형(G35)의 괄호 라벨형
     확장 (Box/Cond 전파의 무한글 흡수 차단 + AnsL 승격). 게이트 G40
     (소급 82건 실증).
  6. 밑줄 빈칸 라인 프레임 오른쪽 초과 — 실행기 blank_fit(자간 한도 -50,
     초과 시 [경고]). 게이트 G43 (덤프 hox).
"""
import json
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

from core.structure import block_grammar as BG                  # noqa: E402
from core.structure import classify_paragraphs                  # noqa: E402
from engines.workbook_v2.gate import inspect_workbook_finish    # noqa: E402
from engines.workbook_v2.plan import (build_step3,              # noqa: E402
                                      question_keep_op)

_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_BG = "STEP 03 > 배경 올림포스"
_ST_C = "STEP 03 > S_선지 올림포스"
_ST_BOX = "STEP 03 > 보기 올림포스"

_ORDER_Q = "주어진 글 다음에 이어질 글의 순서로 가장 적절한 것을 고르시오."
_PAREN_Q = ("다음 (A), (B), (C)의 각 네모 안에서 어법에 맞는 표현으로 "
            "가장 적절한 것은?")
_PASSAGE = ("Remember how you learned to drive or cook? You practiced "
            "while someone coached you. You kept trying until you could "
            "do it on your own, and the person helping you would praise "
            "your progress along the way. Children learn values much the "
            "same way, practicing kinds of behavior while a coach helps "
            "focus their attention on outcomes and their meaning over "
            "time and effort.")


def _p(text, kind=None):
    d = {"text": text, "runs": [{"t": text, "ul": False}]}
    if kind:
        d["kind"] = kind
    return d


def _s3(paras):
    return {"normal": [{"question_num": "t", "paragraphs": paras}],
            "short": []}


def _dump(paras, **kw):
    d = {"stories": [{"idx": 0, "pg": ["1"], "paragraphs": paras}],
         "stale_pages": []}
    d.update(kw)
    return d


# ── 결함 3: 순서배열 선지 원문자 ────────────────────────────────────────────

def test_parser_merges_lone_circled_cells_before_answer_strip():
    """hwpx 2열 표 평탄화(①,행,②,행,…)가 번호 매칭 경로에서도 병합된다
    (0a5da924 '고1 26년 6월 20번.hwpx' 실증 — 재발 방지 시퀀스 가드)."""
    from engines.workbook.parser import (_merge_step3_split_choice_numbers,
                                         _strip_step3_answers)
    rows = ["(A) － (C) － (B)", "(B) － (A) － (C)", "(B) － (C) － (A)",
            "(C) － (A) － (B)", "(C) － (B) － (A)"]
    paras = [{"text": _ORDER_Q, "runs": []}]
    for d, r in zip("①②③④⑤", rows):
        paras.append({"text": d, "runs": [{"t": d, "ul": False}]})
        paras.append({"text": r, "runs": [{"t": r, "ul": False}]})
    merged = _merge_step3_split_choice_numbers(paras)
    stripped = _strip_step3_answers(merged)
    texts = [p["text"] for p in stripped]
    assert texts[1:] == [d + " " + r for d, r in zip("①②③④⑤", rows)]
    # 역순(병합 없이 제거 먼저)이면 번호가 유실된다 — 결함 재현 확인
    lost = _strip_step3_answers(paras)
    assert [p["text"] for p in lost][1:] == rows


def test_plan_numbers_bare_perm_rows():
    """구 content(번호 없는 순열 행 5연속) 재플랜 폴백 — ①~⑤ 부여 +
    선지 스타일. 4행 이하/라벨 중복 행은 무변경."""
    rows = ["(A) － (C) － (B)", "(B) － (A) － (C)", "(B) － (C) － (A)",
            "(C) － (A) － (B)", "(C) － (B) － (A)"]
    paras = [_p(_ORDER_Q, "Q"), _p(_PASSAGE, "P-CONTEXT")] + \
        [_p(r, "P") for r in rows]
    built = build_step3(_s3(paras))
    unit = built["units"][0]
    perm = [p for p in unit if "－" in p["t"]]
    assert len(perm) == 5
    for d, p in zip("①②③④⑤", perm):
        assert p["t"].startswith(d + " "), p["t"]
        assert "선지" in p["s"], p["s"]
        assert p["runs"][0]["t"] == d + " "
    # 4행뿐이면 폴백 미발동 (선지 확신 부족 — 원고 형태 보존)
    built4 = build_step3(_s3(paras[:-1]))
    perm4 = [p for p in built4["units"][0] if "－" in p["t"]]
    assert all(not p["t"].startswith("①") for p in perm4)


def test_gate_g38_perm_rows():
    """G38: 원문자 누락 순열 행 검출 — 현행 플랜 critical / 구플랜 warning.
    수리된 출력(원문자 + 선지)은 침묵."""
    bad = _dump([{"t": "(A) － (C) － (B)\r", "s": _ST_P}])
    plan_new = {"flows": [{"step": "step3", "units": [[
        {"t": "① (A) － (C) － (B)", "s": _ST_C}]]}]}
    r = inspect_workbook_finish({}, plan_new, bad)
    assert any("[순서선지]" in c for c in r["critical"])
    r2 = inspect_workbook_finish({}, {"flows": []}, bad)
    assert any("[순서선지]" in w for w in r2["warnings"])
    ok = _dump([{"t": "① (A) － (C) － (B)\r", "s": _ST_C}])
    r3 = inspect_workbook_finish({}, plan_new, ok)
    assert not any("[순서선지]" in m
                   for m in r3["critical"] + r3["warnings"])


# ── 결함 4: 네모/괄호 선택형 지문 배경 오적용 ──────────────────────────────

def test_classifier_paren_q_passage_stays_p():
    """네모 어법 발문 + 지문 + "(A)\t(B)\t(C)" 헤더 — 지문은 P (배경
    아님). 순서배열의 주어진 글(판정 2 본래 표적)은 유지."""
    out = classify_paragraphs([
        _p(_PAREN_Q), _p(_PASSAGE), _p("(A)\t(B)\t(C)"),
        _p("①help\tdon't coach\thow"),
    ])
    assert out[0]["kind"] == "Q"
    assert out[1]["kind"] == "P"
    assert out[2]["kind"] == "C"
    out2 = classify_paragraphs([
        _p(_ORDER_Q), _p("You practiced while someone coached you."),
        _p("(A) If you don't coach your child, she will find coaches."),
        _p("(B) Children learn values much the same way."),
    ])
    assert out2[1]["kind"] == "P-CONTEXT"


def test_classifier_summary_blank_form_preserved():
    """요약 빈칸형의 요약문(인라인 (A)/(B) 빈칸)은 배경 유지 — 선지
    헤더형(r10c21)과 답란형(r2c02) 모두."""
    q = ("위 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), (B)에 "
         "들어갈 말로 가장 적절한 것은?")
    summary = ("Although we don't think it's (A)__________ to get back "
               "to the previous state, our mind is (B)________ by it.")
    out = classify_paragraphs([
        _p(q), _p(summary), _p("(A)\t(B)"),
        _p("①demanding\thindered"),
    ])
    assert out[1]["kind"] == "P-CONTEXT", out[1]
    q2 = "위 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), (B)를 채우시오."
    out2 = classify_paragraphs([
        _p(q2), _p(summary),
        _p("(A) ________________"), _p("(B) ________________"),
    ])
    assert out2[1]["kind"] == "P-CONTEXT", out2[1]


def test_plan_demotes_stale_paren_bg():
    """구 kind 주석(P-CONTEXT)의 네모어법 지문 재플랜 — 지문 스타일로
    강등 (이중 방어). 요약문 형태 주석은 배경 유지."""
    stem = _p(_PAREN_Q, "Q")
    stem["q_code"] = "OBJ-GRM-PAREN"     # 파서 주석과 동일 (실 content 형태)
    built = build_step3(_s3([
        stem, _p(_PASSAGE, "P-CONTEXT"),
        _p("(A)\t(B)\t(C)", "C"), _p("①help\tdon't\thow", "C"),
    ]))
    unit = built["units"][0]
    assert unit[1]["s"] == _ST_P, unit[1]["s"]


def test_gate_g39_paren_bg():
    bad = _dump([
        {"t": _PAREN_Q + "\r", "s": _ST_Q},
        {"t": _PASSAGE + "\r", "s": _ST_BG},
        {"t": "(A)\t(B)\t(C)\r", "s": _ST_C},
    ])
    plan_new = {"flows": [{"step": "step3", "units": [[
        {"t": _PAREN_Q, "s": _ST_Q}, {"t": _PASSAGE, "s": _ST_P}]]}]}
    r = inspect_workbook_finish({}, plan_new, bad)
    assert any("[지문배경]" in c for c in r["critical"])
    r2 = inspect_workbook_finish({}, {"flows": []}, bad)
    assert any("[지문배경]" in w for w in r2["warnings"])
    ok = _dump([
        {"t": _PAREN_Q + "\r", "s": _ST_Q},
        {"t": _PASSAGE + "\r", "s": _ST_P},
    ])
    r3 = inspect_workbook_finish({}, plan_new, ok)
    assert not any("[지문배경]" in m
                   for m in r3["critical"] + r3["warnings"])


# ── 결함 5: 괄호 라벨 답란 ──────────────────────────────────────────────────

def test_classifier_paren_blank_after_box_is_ansl():
    """<보기> 어구 나열 뒤 "(A) ______"는 AnsL (Box 흡수 차단) — 조건
    뒤 콜론형 "(A) : ___"도 동일. 보기 어구 나열 자체는 Box 유지."""
    out = classify_paragraphs([
        _p("<보기 B>"),
        _p("what / on / important skills / help / and / their attention"),
        _p("(A) " + "_" * 60), _p("(B) " + "_" * 60),
    ])
    assert out[1]["kind"] == "Box"
    assert out[2]["kind"] == "AnsL" and out[3]["kind"] == "AnsL"
    out2 = classify_paragraphs([
        _p("<조건>"), _p("- 본문에 쓰인 단어만 사용할 것"),
        _p("(A) : _______________"), _p("(B) : _______________"),
    ])
    assert out2[1]["kind"] == "Cond"
    assert out2[2]["kind"] == "AnsL" and out2[3]["kind"] == "AnsL"


def test_plan_stale_box_blank_promoted():
    """구 kind 주석(Box 흡수)의 "(A) ___" 재플랜 — 선지 계열(AnsL)로
    승격 (이중 방어)."""
    built = build_step3(_s3([
        _p("<보기 B>", "Box"), _p("what / on / help / and", "Box"),
        _p("(A) " + "_" * 60, "Box"), _p("(B) " + "_" * 60, "Box"),
    ]))
    unit = built["units"][0]
    assert unit[2]["s"] == _ST_C and unit[3]["s"] == _ST_C, \
        [(p["t"][:12], p["s"]) for p in unit]
    assert unit[1]["s"] == _ST_BOX


def test_gate_g40_paren_blank():
    bad = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 60 + "\r", "s": _ST_BOX},
        {"t": "(B) " + "_" * 60 + "\r", "s": _ST_BOX},
    ])
    plan_new = {"flows": [{"step": "step3", "units": [[
        {"t": "what / on / help", "s": _ST_BOX},
        {"t": "(A) " + "_" * 60, "s": _ST_C}]]}]}
    r = inspect_workbook_finish({}, plan_new, bad)
    assert any("[괄호답란]" in c for c in r["critical"])
    r2 = inspect_workbook_finish({}, {"flows": []}, bad)
    assert any("[괄호답란]" in w for w in r2["warnings"])
    ok = _dump([
        {"t": "<보기 B>\r", "s": _ST_BOX},
        {"t": "what / on / help\r", "s": _ST_BOX},
        {"t": "(A) " + "_" * 60 + "\r", "s": _ST_C},
    ])
    r3 = inspect_workbook_finish({}, plan_new, ok)
    assert not any("[괄호답란]" in m
                   for m in r3["critical"] + r3["warnings"])


def test_gate_g40_ignores_blank_after_passage():
    """지문/요약문 뒤 단독 "(A) ___"(Ans — 지문 관행 유지)는 위치 신호가
    없어 검출하지 않는다 (W39 '쌍만 승격' 결정 보존)."""
    d = _dump([
        {"t": _PASSAGE + "\r", "s": _ST_P},
        {"t": "(A) : _______________\r", "s": _ST_P},
    ])
    r = inspect_workbook_finish({}, {"flows": []}, d)
    assert not any("[괄호답란]" in m for m in r["critical"] + r["warnings"])


# ── 결함 2: 발문 고아 (stem_keep) ───────────────────────────────────────────

def test_question_keep_op_includes_stem_keep():
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": "지문", "s": _ST_P}, {"t": "발문?", "s": _ST_Q},
        {"t": "지문2", "s": _ST_P}]]}]}
    op = question_keep_op(plan)
    assert op and op["stem_keep"] == {"min_lines": 2}


def test_gate_g41_stem_orphan():
    """발문이 프레임 끝(다음 프레임 직전)에 단독 — fc 실측 검출.
    stem_keep 계약 critical / 무계약 warning / 정상 배치 침묵."""
    q = "다음 글에서 전체 흐름과 관계 없는 문장은?\r"
    ps = [{"t": "0. 앞 문제 본문\r", "s": _ST_P},
          {"t": q, "s": _ST_Q},
          {"t": _PASSAGE + "\r", "s": _ST_P}]
    off_q = len(ps[0]["t"])
    off_body = off_q + len(q)
    story = {"idx": 0, "pg": ["1", "2"], "paragraphs": ps,
             "fc": [0, off_body], "fp": ["1", "2"]}
    dump = {"stories": [story], "stale_pages": [],
            "pages": [{"p": "1", "side": "R"}, {"p": "2", "side": "L"}]}
    plan = {"flows": [{"step": "step3", "units": [[
        {"t": p["t"].rstrip("\r"), "s": p["s"]} for p in ps]]}],
        "question_keep": {"flows": {"step3": {"starts": [1]}},
                          "q_styles": [_ST_Q],
                          "stem_keep": {"min_lines": 2}}}
    r = inspect_workbook_finish({}, plan, dump)
    assert any("[발문고아]" in c for c in r["critical"]), r
    plan_old = dict(plan)
    plan_old["question_keep"] = {"flows": {"step3": {"starts": [1]}},
                                 "q_styles": [_ST_Q]}
    r2 = inspect_workbook_finish({}, plan_old, dump)
    assert any("[발문고아]" in w for w in r2["warnings"])
    story_ok = dict(story)
    story_ok["fc"] = [0, off_q]      # 발문부터 새 프레임 (수리 후 배치)
    r3 = inspect_workbook_finish({}, plan, {**dump,
                                            "stories": [story_ok]})
    assert not any("[발문고아]" in m
                   for m in r3["critical"] + r3["warnings"])


# ── 결함 1: 다열 선지 열 정렬 (G42) ─────────────────────────────────────────

def test_gate_g42_tab_alignment():
    rows_bad = [
        {"t": "(A)\t(B)\t(C)\r", "s": _ST_C, "cx": [10, 40, 70]},
        {"t": "①help\tdon't coach\thow\r", "s": _ST_C,
         "cx": [10, 22.7, 48.1]},
        {"t": "②to help\tdon't coach\twhat\r", "s": _ST_C,
         "cx": [10, 35.4, 60.8]},
    ]
    d = _dump(rows_bad)
    plan_ct = {"flows": [], "choice_tabs": {"steps": ["step3"]}}
    r = inspect_workbook_finish({}, plan_ct, d)
    assert any("[선지열정렬]" in c for c in r["critical"]), r
    r2 = inspect_workbook_finish({}, {"flows": []}, d)
    assert any("[선지열정렬]" in w for w2 in [r2["warnings"]]
               for w in w2)
    rows_ok = [
        {"t": "①help\tdon't coach\thow\r", "s": _ST_C,
         "cx": [10, 35.4, 60.8]},
        {"t": "②to help\tdon't coach\twhat\r", "s": _ST_C,
         "cx": [10, 35.4, 60.8]},
    ]
    r3 = inspect_workbook_finish({}, plan_ct, _dump(rows_ok))
    assert not any("[선지열정렬]" in m
                   for m in r3["critical"] + r3["warnings"])


def test_gate_g42_old_dump_notice():
    """cx 없는 구덤프 + choice_tabs 계약 — 재덤프 안내 warning."""
    d = _dump([{"t": "①help\tdon't\thow\r", "s": _ST_C}])
    r = inspect_workbook_finish(
        {}, {"flows": [], "choice_tabs": {"steps": ["step3"]}}, d)
    assert any("[선지열정렬]" in w and "재덤프" in w for w in r["warnings"])


# ── 결함 6: 빈칸 프레임 경계 (G43) ──────────────────────────────────────────

def test_gate_g43_blank_overflow():
    d = _dump([{"t": "(A) " + "_" * 80 + "\r", "s": _ST_C}],
              hox=[{"st": 0, "p": "209", "over": 3.1,
                    "t": "(A) ______"}])
    r = inspect_workbook_finish({}, {"flows": []}, d)
    assert any("[빈칸경계]" in w for w in r["warnings"])
    r2 = inspect_workbook_finish(
        {}, {"flows": [], "blank_fit": {"max_tracking": -50}}, d)
    assert any("[빈칸경계]" in w and "한도" in w for w in r2["warnings"])
    d_ok = _dump([{"t": "본문\r", "s": _ST_P}], hox=[])
    r3 = inspect_workbook_finish({}, {"flows": []}, d_ok)
    assert not any("[빈칸경계]" in w for w in r3["warnings"])
