"""역학습 인프라 가드 (W44/W46) — 정렬기 + 계열 어댑터 + 규칙 보강."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reverse_learn.adapters import adapter_for, can_predict  # noqa: E402
from core.reverse_learn.align import (align, align_document, flatten_dump,  # noqa: E402
                                      flatten_plan, norm_key, story_scope)
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


# ── W46 정렬 교차오염 차단 (플랜 target 우선) ───────────────────────────────

def _xcontam_fixture():
    """같은 본문이 두 스텝(a2/b1)에 재등장 — 득표만으로는 대응이 겹친다."""
    body = [BODY, "Second sentence of the very same passage body text here."]
    plan = {"flows": [
        {"step": "step1_a2", "target": {"marker": "본문 O/X"},
         "units": [[{"t": t, "s": "P-A2"} for t in body]]},
        {"step": "step1_b1", "target": {"marker": "본문 정리"},
         "units": [[{"t": t, "s": "P-B1"} for t in body]]},
    ]}
    # 덤프(문서 배치) 순서는 플랜 순서와 다르다 — b1 지면이 앞에 온다.
    dump = {
        "pages": [{"p": "7", "m": "A-마스터"}, {"p": "40", "m": "A-마스터"}],
        "stories": [
            {"idx": 0, "pg": ["40"],
             "paragraphs": [{"t": "본문 정리", "s": "마커"}]},
            {"idx": 1, "pg": ["40"],
             "paragraphs": [{"t": t, "s": "GOLD_B1"} for t in body]},
            {"idx": 2, "pg": ["7"],
             "paragraphs": [{"t": "본문 O/X", "s": "마커"}]},
            {"idx": 3, "pg": ["7"],
             "paragraphs": [{"t": t, "s": "GOLD_A2"} for t in body]},
        ]}
    return plan, dump


def test_story_scope_maps_steps_by_marker_page():
    plan, dump = _xcontam_fixture()
    targets = {f["step"]: {"markers": [f["target"]["marker"]]}
               for f in plan["flows"]}
    scope = story_scope(dump, targets)
    assert scope["step1_a2"] == {2, 3}
    assert scope["step1_b1"] == {0, 1}


def test_story_scope_master_prefix():
    dump = {"pages": [{"p": "3", "m": "O-마스터"}, {"p": "4", "m": "A-마스터"}],
            "stories": [{"idx": 0, "pg": ["3"], "paragraphs": []},
                        {"idx": 1, "pg": ["4"], "paragraphs": []}]}
    assert story_scope(dump, {"step3": {"masters": ["O"]}}) == {"step3": {0}}


def test_align_document_target_scope_blocks_cross_contamination():
    plan, dump = _xcontam_fixture()
    pp, gg = flatten_plan(plan), flatten_dump(dump)
    targets = {f["step"]: {"markers": [f["target"]["marker"]]}
               for f in plan["flows"]}
    scope = story_scope(dump, targets)

    def golds(res):
        return {(pp[x["p"]]["step"], gg[x["g"]]["style"]) for x in res["pairs"]}

    before = golds(align_document(pp, gg, min_story_hits=1))
    after = golds(align_document(pp, gg, min_story_hits=1, step_stories=scope))
    # 교차오염: 득표만 쓰면 b1이 a2 스토리(또는 그 잔여)에 붙는다
    assert ("step1_b1", "GOLD_A2") in before
    assert after == {("step1_a2", "GOLD_A2"), ("step1_b1", "GOLD_B1")}


def test_align_document_falls_back_when_scope_misses():
    """target이 지면을 못 찾으면(마커 없는 완성본) 기존 득표 동작 유지."""
    plan, dump = _xcontam_fixture()
    pp, gg = flatten_plan(plan), flatten_dump(dump)
    base = align_document(pp, gg, min_story_hits=1)
    same = align_document(pp, gg, min_story_hits=1,
                          step_stories=story_scope(dump, {"step1_a2": {
                              "markers": ["존재하지 않는 마커"]}}))
    assert base["pairs"] == same["pairs"]


# ── W46 계열 어댑터 ─────────────────────────────────────────────────────────

def test_adapter_for_by_series_and_shape():
    assert adapter_for("교과서워크북") == "workbook"
    assert adapter_for("블랙북") == "blackbook"
    assert adapter_for("세서스페셜") == "seseospecial"
    assert adapter_for("화이트북") == "whitebook"
    assert adapter_for("", {"days": []}) == "whitebook"
    assert adapter_for("포켓북", {"analysis_files": []}) is None


def test_can_predict_requires_payload():
    assert not can_predict({"steps": {}}, "워크북")
    assert can_predict({"steps": {"step3": {}}}, "워크북")
    assert not can_predict({"sections": {"part1_problem": []}}, "블랙북")
    assert can_predict({"sections": {"problems_p1": None}}, "블랙북")
    assert can_predict({"part1": {"paragraphs": []}}, "세서스페셜")
    assert not can_predict({"practices": []}, "화이트북")


def test_seseospecial_adapter_normalizes_area_to_step():
    from core.reverse_learn.adapters import build_plan as _bp
    content = {"part1": {"paragraphs": [{"text": "hello", "style_code": 0}]},
               "part2": {"passages": []}}
    plan, name = _bp(content, series="세서스페셜")
    assert name == "seseospecial"
    assert [f["step"] for f in plan["flows"]][:1] == ["part1"]
    assert flatten_plan(plan)[0]["text"] == "hello"


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
