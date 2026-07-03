"""v2 렌더 플랜 빌더 — content v2 IR → 단락 시퀀스 [{"t","s","runs"}].

핵심 설계: 레이아웃/스타일 결정은 전부 여기(파이썬+데이터)에서 끝내고,
JSX(render_flow.body.jsx)는 플랜을 그대로 실행만 한다.
스타일은 core/structure/style_map.json의 "mockexam_v2" 섹션 — 실물 템플릿
인벤토리 대조 테스트로 보호되며, 없는 스타일 자동 생성은 하지 않는다(v1과 차이).
"""

from core.structure.style_resolver import resolve_style


def _style(kind, overrides=None):
    return resolve_style("mockexam_v2", "FLOW", kind, overrides=overrides)


def _runs_from_marks(content, marks):
    """IR 블록 marks(span) → 밑줄 runs [{"t","ul"}] (JSX 밑줄 적용용)."""
    if not marks:
        return []
    spans = sorted((m["span"][0], m["span"][1]) for m in marks
                   if m.get("type") == "underline" and m.get("span"))
    if not spans:
        return []
    runs = []
    pos = 0
    for s, e in spans:
        s, e = max(s, pos), min(e, len(content))
        if s > pos:
            runs.append({"t": content[pos:s], "ul": False})
        if e > s:
            runs.append({"t": content[s:e], "ul": True})
        pos = max(pos, e)
    if pos < len(content):
        runs.append({"t": content[pos:], "ul": False})
    return runs


def ir_to_render_plan(doc, overrides=None):
    """v2 문서 → [{"t": 단락텍스트, "s": 스타일명, "runs": [...]}]"""
    plan = []

    def emit(text, kind, runs=None):
        plan.append({"t": text, "s": _style(kind, overrides), "runs": runs or []})

    for item in doc["items"]:
        # 그룹 도입문 (그룹 첫 문항 앞 1회)
        if item.get("_group_intro"):
            emit(item["_group_intro"], "Q-INTRO")

        # 발문: 머리 마커 + 발문 본문 (서술형은 서술형 번호 스타일)
        marker = (item.get("header") or {}).get("marker")
        q_line = f"{marker} {item['question']}" if marker else item["question"]
        emit(q_line, "Q-SRV" if item.get("kind") == "서술형" else "Q")

        # 지문 블록
        for block in (item.get("stimulus") or {}).get("blocks", []):
            kind = "P-CONTEXT" if block.get("kind") == "para" else "P"
            label = block.get("label")
            if label in ("Word", "K", "Ans", "UNKNOWN"):
                kind = label
            emit(block["content"], kind,
                 _runs_from_marks(block["content"], block.get("marks")))

        # 보기/요약 박스 (마커 라인 재구성 + 내용)
        given = item.get("given")
        if given and given.get("content"):
            if given.get("type") != "summary_box":
                emit("<보기>", "Box")
            for line in given["content"].split("\n"):
                if line.strip():
                    emit(line, "Box")

        # 조건 박스
        if item.get("constraints"):
            emit("<조건>", "Cond")
            for c in item["constraints"]:
                emit(c, "Cond")

        # 선지
        if item.get("choices"):
            for ch in item["choices"]["items"]:
                label = ch.get("label") or ""
                emit(f"{label} {ch['content']}".strip(), "C")

    return plan
