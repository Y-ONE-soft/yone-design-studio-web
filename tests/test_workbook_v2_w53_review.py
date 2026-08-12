"""W53 — 배재2 워크북01(YBM박 1,2,3과) 검수 지시 2건의 플랜 계층 반영.

실물 근거: 검수자(윤기 영어) PDF 주석 2026-08-12, 조판 완제품
`배재2_워크북01(YBM박1,2,3과)_내지.indd`.

  1. C1 문장배열의 보충지문 라벨이 순번으로 인쇄 ({8}/{9}).
     헤더 "8. L1-Further Reading(p.26-27)"에 '본문N'이 없어 선두 순번
     폴백이 걸린다. 같은 책 어휘선택/빈칸어휘 섹션은 원고 대괄호 라벨이라
     이미 [Further Reading]/[Further Reading 1]/[Further Reading 2] —
     같은 책 안의 정상 구간이 컨벤션의 정답. 검수 지시도 동일
     (p31 'Further Reading', p96/97·p160/161 'Further Reading 1/2').

  2. 실전문제 섹션 머리에 세트 안내문 1줄이 얹혀 인쇄 (과당 1건 = 3건).
     교과서/부교재 계열은 STEP3 전체가 question_num="textbook" 통짜
     아이템(코퍼스 35건 중 30건)이라 '발문 2개 이상' 조건이 항상 참 —
     세트 단위 스펙(2026-08-07)이 섹션 머리에 오발동한 것. 원고에 있는
     안내문은 그대로 보존한다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.workbook_v2.plan import build_step1_c1, build_step3  # noqa: E402


def _p(text):
    return {"text": text, "runs": [{"t": text, "ul": False}]}


def _c1_labels(headers):
    paras = []
    for h in headers:
        paras += [_p(h), _p("(A) alpha"), _p("(B) beta")]
    out = build_step1_c1({"paragraphs": paras}, workbook_type="교과서")
    return [q["t"] for u in out["units"]
            for q in (u["paras"] if isinstance(u, dict) else u)
            if q["t"].startswith("{") and q["t"].endswith("}")]


def test_c1_corner_label_numbered_when_repeated():
    """보충지문 2개 → Further Reading 1 / 2 (배재2 2·3과 실측)."""
    labels = _c1_labels(
        ["1. L2-본문1(p.40)", "2. L2-본문2(p.42)", "3. L2-본문3(p.44)",
         "4. L2-본문4(p.46)", "5. L2-본문5(p.48)", "6. L2-본문6(p.50)",
         "7. L2-Further Reading(p.56)", "8. L2-Further Reading(p.58)"])
    assert labels[-2:] == ["{Further Reading 1}", "{Further Reading 2}"]
    assert "{7}" not in labels and "{8}" not in labels


def test_c1_corner_label_bare_when_single():
    """보충지문 1개 → 접미 없음 (배재2 1과 p31 검수 지시)."""
    labels = _c1_labels(
        ["1. L1-본문1(p.10)", "2. L1-본문2(p.12)", "3. L1-본문3(p.14)",
         "4. L1-본문4(p.16)", "5. L1-본문5(p.18)",
         "6. L1-Further Reading(p.26-27)"])
    assert labels[-1] == "{Further Reading}"
    assert "{6}" not in labels


def test_c1_numeric_label_untouched_without_corner_name():
    """회귀 가드: 코너명 없는 헤더의 순번 라벨은 무접촉 (모의고사 계열)."""
    labels = _c1_labels(["1. no.1", "2. no.2"])
    assert labels == ["{1}", "{2}"]


def _step3_units(question_num, n_questions):
    paras = []
    for i in range(n_questions):
        paras.append({"text": "%d. 다음 글의 요지로 가장 적절한 것은?" % (i + 1),
                      "kind": "Q"})
        paras.append({"text": "Passage body %d." % (i + 1), "kind": "P"})
    out = build_step3({"normal": [{"question_num": question_num,
                                   "paragraphs": paras}]})
    return out["units"]


def test_step3_aggregate_item_gets_no_fabricated_intro():
    """통짜(textbook) 아이템에는 세트 안내문을 만들어 넣지 않는다."""
    units = _step3_units("textbook", 3)
    texts = [q["t"] for u in units for q in u]
    assert not any("물음에 답하시오" in t for t in texts), texts[:5]


def test_step3_numbered_set_keeps_intro_spec():
    """문항번호 세트(2026-08-07 확정 스펙)에는 그대로 삽입."""
    units = _step3_units("20", 3)
    texts = [q["t"] for u in units for q in u]
    assert any("다음 글을 읽고 물음에 답하시오." == t for t in texts), texts[:5]
