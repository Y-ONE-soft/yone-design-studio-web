"""역학습 인프라 가드 (W44) — 정렬기 + 완성본 대조로 나온 규칙 보강 1건."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reverse_learn.align import (align, align_document, flatten_dump,  # noqa: E402
                                      flatten_plan, norm_key)
from engines.workbook_v2 import plan as P  # noqa: E402

BODY = ("Farmers welcome visitors to their fields every single summer "
        "season here in the countryside.")


def _step(texts):
    return {"paragraphs": [{"text": t, "runs": [{"t": t, "ul": False}]}
                           for t in texts]}


# ── 정렬기 ──────────────────────────────────────────────────────────────────

def test_norm_key_absorbs_punctuation_and_case():
    assert norm_key("(A) Hello, World!") == norm_key("A Hello World")


def test_align_document_monotone_and_cross_story():
    plan = {"flows": [
        {"step": "step1_a1", "units": [[
            {"t": "alpha one sentence here", "s": "S1"},
            {"t": "beta two sentence here", "s": "S1"},
        ]]},
        {"step": "step3", "units": [[
            {"t": "gamma three sentence here", "s": "S2"},
            {"t": "delta four sentence here", "s": "S2"},
        ]]},
    ]}
    # 덤프의 스토리 순서는 플랜의 스텝 순서와 반대 — 전역 단조 정렬로는
    # 한쪽 스텝이 통째로 버려진다 (align_document가 스텝↔스토리를 먼저 잡는다).
    dump = {"stories": [
        {"idx": 0, "paragraphs": [{"t": "gamma three sentence here", "s": "G2"},
                                  {"t": "delta four sentence here", "s": "G2"}]},
        {"idx": 1, "paragraphs": [{"t": "alpha one sentence here", "s": "G1"},
                                  {"t": "beta two sentence here", "s": "G1"}]},
    ]}
    pp, gg = flatten_plan(plan), flatten_dump(dump)
    res = align_document(pp, gg, min_story_hits=1)
    assert res["stats"]["aligned"] == 4
    for x in res["pairs"]:
        assert norm_key(pp[x["p"]]["text"]) == norm_key(gg[x["g"]]["text"])


def test_align_skips_human_inserted_paragraph():
    """완성본에만 있는 단락(사람 추가)은 정렬에서 빠질 뿐 오정렬되지 않는다."""
    plan = {"flows": [{"step": "s", "units": [[
        {"t": "the first paragraph of the passage", "s": "A"},
        {"t": "the third paragraph of the passage", "s": "A"},
    ]]}]}
    dump = {"stories": [{"idx": 0, "paragraphs": [
        {"t": "the first paragraph of the passage", "s": "A"},
        {"t": "완성본에서 사람이 새로 넣은 안내 문구", "s": "B"},
        {"t": "the third paragraph of the passage", "s": "A"},
    ]}]}
    pp, gg = flatten_plan(plan), flatten_dump(dump)
    res = align(pp, gg)
    assert res["stats"]["aligned"] == 2
    assert [gg[x["g"]]["idx"] for x in res["pairs"]] == [0, 2]


# ── W44 규칙 보강: step1_c1 헤더 부분 인식 ──────────────────────────────────

def _c1_texts(second_header):
    return ["1. L4-본문1(p.94)", "(A) " + BODY, "(B) " + BODY, "(C) " + BODY,
            "", second_header, "(A) " + BODY, "(B) " + BODY, "(C) " + BODY, ""]


def _styles(built):
    out = []
    for u in built["units"]:
        paras = u if isinstance(u, list) else u["paras"]
        out.extend((p["s"], p["t"]) for p in paras)
    return out


def test_c1_missed_header_promoted_to_block():
    """GREP 열거가 못 잡는 형식("2. L4-Read More(p.109)")도 블록이 된다.

    완성본 실증(ac9fc469 영어Ⅰ_미래엔(김) 4과): 미인식 블록의 (A)~(J)가
    스타일 없이 인쇄됐고, 사람이 마무리한 최종본은 C1_문장 배열이었다.
    """
    built = P.build_step1_c1(_step(_c1_texts("2. L4-Read More(p.109)")),
                             workbook_type="교과서")
    assert len(built["units"]) == 2
    styles = [s for s, t in _styles(built) if t.startswith(("(A)", "(B)", "(C)"))]
    assert styles and all(s == P._style("STEP1C1", "P") for s in styles)


def test_c1_promotion_requires_ordinal_continuation():
    """순번이 이어지지 않는 라인은 승격하지 않는다 (오분할 방지)."""
    built = P.build_step1_c1(_step(_c1_texts("9. L4-Read More(p.109)")),
                             workbook_type="교과서")
    assert len(built["units"]) == 1


def test_c1_promotion_requires_following_choices():
    """뒤에 (A)~(Z) 배열 선지가 없으면 승격하지 않는다."""
    texts = ["1. L4-본문1(p.94)", "(A) " + BODY, "(B) " + BODY, "",
             "2. L4-Read More(p.109)", "이 블록은 배열 선지가 없다.", ""]
    built = P.build_step1_c1(_step(texts), workbook_type="교과서")
    assert len(built["units"]) == 1


def test_c1_promotion_switch_off_restores_old_behaviour():
    old = P.PROMOTE_C1_MISSED_HDR
    P.PROMOTE_C1_MISSED_HDR = False
    try:
        built = P.build_step1_c1(_step(_c1_texts("2. L4-Read More(p.109)")),
                                 workbook_type="교과서")
        assert len(built["units"]) == 1
    finally:
        P.PROMOTE_C1_MISSED_HDR = old
