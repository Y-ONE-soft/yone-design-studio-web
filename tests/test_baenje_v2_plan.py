"""배N제 v2 — 파서/플랜 오프라인 검증 (InDesign 불필요).

원고 없이도 도는 합성 케이스 + style_map/템플릿 인벤토리 정합성.
실 원고 E2E는 scripts/e2e_engine_baenje_v2.py.
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


def _rows(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def test_problem_classification_by_structure():
    from engines.baenje_v2.parser import classify_problem_paragraphs
    warns = []
    got = classify_problem_paragraphs(_rows(
        "1. 다음 글에서 전체 흐름과 관계 없는 문장은?",
        "Imagine an urban area that is fast becoming a slum after a recession.",
        "① the failure of the police to account for their own crime statistics",
        "2. 다음 글의 내용에 맞도록, <보기>의 어구를 모두 사용하여 완성하시오.",
        "A rhyme is usually the repetition of the final sound of a word.",
        "<보기>",
        "(a) A rapper describes a childhood in a district.",
        "(b) A singer lists the luxury cars she bought.",
        "[조건]",
        "① 위에 주어진 어구를 한 번씩만 모두 사용할 것",
        "3. 다음 글의 내용에 근거한 대화의 밑줄 친 부분 중 어색한 것은?",
        "After the peace treaty, the gangs started partying together.",
        "Yungi: I keep hearing that hip-hop began at parties in the Bronx.",
        "Hyeona: It is. After the peace treaty, gangs threw parties together.",
    ), warns)
    assert [p["no"] for p in got] == [1, 2, 3]
    kinds = [p["kind"] for p in got[0]["paras"]]
    assert kinds == ["stem", "passage", "choice"]
    kinds2 = [p["kind"] for p in got[1]["paras"]]
    assert kinds2 == ["stem", "passage", "bogi", "bogi", "bogi", "cond", "cond"]
    kinds3 = [p["kind"] for p in got[2]["paras"]]
    assert kinds3 == ["stem", "passage", "dialogue", "dialogue"]
    assert warns == []


def test_answer_blocks_strip_markers():
    from engines.baenje_v2.parser import classify_answer_paragraphs
    warns = []
    got = classify_answer_paragraphs(_rows(
        "2026학년도 2학기 중간고사 대비 · 배재고 2학년 〔해설지〕",
        "1", "[정답] ④", "[해석] 경기 침체 후 …", "(A) 그 파티에서 …",
        "[해설] ④는 버려진 건물을 …",
        "2", "[정답] ①", "[해석] 힙합이라는 단어의 …",
    ), warns)
    assert [b["no"] for b in got] == [1, 2]
    assert [p["kind"] for p in got[0]["paras"]] == [
        "num", "answer", "trans", "cont", "expl"]
    # 마커는 파서에서 제거 (스타일이 '정답 |' 라벨을 자동 생성)
    assert got[0]["paras"][1]["t"] == "④"
    assert got[0]["paras"][2]["t"].startswith("경기 침체")
    assert warns == []


def test_plan_shapes_and_breaks():
    from engines.baenje_v2.plan import content_to_plan, flow_paras
    content = {
        "format": "baenje-content-v1",
        "units": [{"label": "L1", "start_q": 1}, {"label": "L2", "start_q": 3}],
        "problems": [
            {"no": 1, "paras": [{"t": "1. 다음 …?", "kind": "stem"},
                                {"t": "Body one.", "kind": "passage"}]},
            {"no": 2, "paras": [{"t": "2. 다음 …?", "kind": "stem"}]},
            {"no": 3, "paras": [{"t": "3. 다음 …?", "kind": "stem"}]},
        ],
        "answers": [
            {"no": 1, "paras": [{"t": "1", "kind": "num"},
                                {"t": "④", "kind": "answer"}]},
            {"no": 3, "paras": [{"t": "3", "kind": "num"},
                                {"t": "①", "kind": "answer"}]},
        ],
        "warnings": [],
    }
    plan = content_to_plan(content)
    assert plan["format"] == "bj-flows-v1"
    body = plan["flows"][0]
    ans = plan["flows"][1]
    assert body["break_per_unit"] is True     # 문항 1개 = 프레임 1개
    assert ans["break_per_unit"] is False     # 정답지는 이어 흘림
    # 첫 유닛은 페이지 브레이크 없음, 두 번째 유닛(3번)은 새 페이지
    assert [u["page_break"] for u in body["units"]] == [False, False, True]
    assert body["units"][0]["unit_label"] == "L1"
    assert body["units"][2]["unit_label"] == "L2"
    # 라벨 단락은 플랜 시퀀스에 스타일 None으로 포함
    seq = flow_paras(plan, "body")
    assert seq[0] == ("L1", None)
    assert seq[1][1] == "문제"
    ops = plan["ops"]
    assert ops["unit_masters"]["body"] == {"left": "L0", "right": "L2",
                                           "cont": "L1"}
    assert ops["unit_masters"]["answers"] == {"left": "C0", "right": "C2",
                                              "cont": "C1"}
    assert ops["keep_block_in_spread"] == "answers"


def test_long_blank_answer_line_is_left_aligned():
    from engines.baenje_v2.plan import content_to_plan
    content = {"units": [], "problems": [{"no": 1, "paras": [
        {"t": "1. 빈칸을 완성하시오.", "kind": "stem"},
        {"t": "Rhyming matters because ＿＿＿＿＿＿＿＿.", "kind": "passage"},
    ]}], "answers": [], "warnings": []}
    plan = content_to_plan(content)
    paras = plan["flows"][0]["units"][0]["paras"]
    assert paras[0].get("align") is None
    assert paras[1]["align"] == "left"


def test_style_map_exists_in_template_inventory():
    """style_map 배N제 섹션의 모든 스타일이 실물 [원본] 템플릿에 존재."""
    smap = json.load(open(os.path.join(
        REPO, "core", "structure", "style_map.json"),
        encoding="utf-8"))["baenje"]
    inv = set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_baenje.json"),
        encoding="utf-8"))["paragraph_styles"])
    missing = []
    for table in ("BODY", "ANS"):
        for kind, style in smap[table].items():
            if style not in inv:
                missing.append(f"{table}/{kind}: {style}")
    assert not missing, f"템플릿에 없는 스타일 참조: {missing}"
