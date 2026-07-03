"""블랙북 v2 렌더 플랜 빌더 — 섹션 파싱 결과 → bb-flows 플랜.

플랜 포맷 (core/jsx/blackbook_flow.body.jsx가 실행):
{
  "format": "bb-flows-v1",
  "flows": [
    {"area": "module_p1", "break_per_unit": true,  "units": [[{t,s,runs},...], ...]},
    {"area": "large",     "break_per_unit": true,  "units": [...]},   # 어휘 본문당 1프레임
    {"area": "module_p2", "break_per_unit": true,  "units": [...]},
    {"area": "narrow_1",  "break_per_unit": false, "units": [[...]]}, # part1 정답 (스토리 흘리기)
    {"area": "narrow_2",  "break_per_unit": false, "units": [[...]]}
  ]
}
배치 의미론은 v1 run.jsx와 동일 (연결 스토리 + 문제 블록 프레임브레이크,
프레임 부족 시 해당 영역 마지막 페이지 복제). 스타일 결정은 여기(데이터).
"""
from core.structure.style_resolver import load_style_map


def _tables():
    smap = load_style_map()["blackbook"]
    return smap["FLOW"], smap["V1TYPES"]


def _ir_item_to_unit(item, flow_map):
    """v2 IR 문항 → 단락 목록 [{t,s,runs}] (mockexam_v2 render와 동일 의미론)."""
    unit = []

    def emit(text, kind, runs=None):
        unit.append({"t": text, "s": flow_map.get(kind) or flow_map["UNKNOWN"],
                     "runs": runs or []})

    if item.get("_group_intro"):
        emit(item["_group_intro"], "Q-INTRO")
    marker = (item.get("header") or {}).get("marker")
    q_line = f"{marker} {item['question']}" if marker else item["question"]
    emit(q_line, "Q")

    from engines.mockexam_v2.render import _runs_from_marks
    for block in (item.get("stimulus") or {}).get("blocks", []):
        kind = "P-CONTEXT" if block.get("kind") == "para" else "P"
        label = block.get("label")
        if label in ("Word", "K", "Ans", "UNKNOWN"):
            kind = label
        emit(block["content"], kind,
             _runs_from_marks(block["content"], block.get("marks")))

    given = item.get("given")
    if given and given.get("content"):
        box_kind = "Box@summary" if given.get("type") == "summary_box" else "Box"
        if box_kind == "Box":
            emit("<보기>", "Box")
        for line in given["content"].split("\n"):
            if line.strip():
                emit(line, box_kind)

    if item.get("constraints"):
        emit("<조건>", "Cond")
        for c in item["constraints"]:
            emit(c, "Cond")

    if item.get("choices"):
        for ch in item["choices"]["items"]:
            label = ch.get("label") or ""
            emit(f"{label} {ch['content']}".strip(), "C")
    return unit


def _vocab_item_to_unit(item, v1_map):
    unit = []
    for p in item.get("paragraphs", []):
        style = v1_map.get(p.get("type")) or "!박스_지문"
        unit.append({"t": p.get("text", ""), "s": style,
                     "runs": p.get("runs") or []})
    return unit


def _answers_to_unit(items, v1_map):
    """정답 목록 → 한 스토리 흘리기 유닛 (v1 place 의미론: 'N.  답' + 해설)."""
    unit = []
    for a in items:
        unit.append({"t": f"{a['num']}.  {a['answer']}",
                     "s": v1_map["answer"], "runs": []})
        if a.get("explanation"):
            unit.append({"t": a["explanation"], "s": v1_map["explanation"],
                         "runs": []})
    return unit


def sections_to_plan(sections):
    flow_map, v1_map = _tables()
    flows = []

    p1 = sections.get("problems_p1")
    if p1 and p1["items"]:
        flows.append({"area": "module_p1", "break_per_unit": True,
                      "units": [_ir_item_to_unit(it, flow_map)
                                for it in p1["items"]]})
    if sections.get("vocab"):
        flows.append({"area": "large", "break_per_unit": True,
                      "units": [_vocab_item_to_unit(it, v1_map)
                                for it in sections["vocab"]]})
    p2 = sections.get("problems_p2")
    if p2 and p2["items"]:
        flows.append({"area": "module_p2", "break_per_unit": True,
                      "units": [_ir_item_to_unit(it, flow_map)
                                for it in p2["items"]]})
    if sections.get("answers_p1"):
        flows.append({"area": "narrow_1", "break_per_unit": False,
                      "units": [_answers_to_unit(sections["answers_p1"], v1_map)]})
    if sections.get("answers_p2"):
        flows.append({"area": "narrow_2", "break_per_unit": False,
                      "units": [_answers_to_unit(sections["answers_p2"], v1_map)]})
    return {"format": "bb-flows-v1", "flows": flows}
