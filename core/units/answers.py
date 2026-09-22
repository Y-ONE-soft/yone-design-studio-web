"""정답지 — 세트의 정답(answer·bool 자리)을 모아 정답 세트로 만든다. 틀 구간이 kind `answers` 를 쓰면 자동으로 붙는다.

    answer_sets(sets, blocks) → [{kind: "answers", id, blocks: [{block: "answer_row", fields: {no, answers}}]}]

answers 값은 서식 조각 목록 — 블록 이름은 굵게, 번호·정답은 그대로. 정답이 하나도 없는 세트는 빠진다.
정답 줄 블록(answer_row: no + answers)이 라이브러리에 없으면 빈 목록.
"""

CIRC = "①②③④⑤⑥⑦⑧⑨⑩"


def _fmt(v, ftype):
    if ftype == "bool":
        return "O" if v else "X"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v).strip()


def answer_sets(sets, blocks, row_block="answer_row"):
    by_id = {b["id"]: b for b in blocks or []}
    if row_block not in by_id:
        return []
    out = []
    for s in sets or []:
        if s.get("kind") == "answers":
            continue
        groups = []                                  # [(블록 이름, [(no, 정답)])]
        for b in s.get("blocks") or []:
            blk = by_id.get(b.get("block")) or {}
            fields = blk.get("fields") or {}
            ans = next((f for f, d in fields.items() if (d or {}).get("type") in ("answer", "bool")), None)
            if not ans:
                continue
            v = (b.get("fields") or {}).get(ans)
            if v is None or v == "":
                continue
            entry = (str((b.get("fields") or {}).get("no") or ""), _fmt(v, fields[ans].get("type")))
            if groups and groups[-1][0] == blk.get("name"):
                groups[-1][1].append(entry)
            else:
                groups.append((blk.get("name") or b.get("block"), [entry]))
        if not groups:
            continue
        rich = []
        for k, (name, entries) in enumerate(groups):
            if k:
                rich.append("\u00a0\u00a0\u00a0")                                        # HTML 이 빈칸을 합치므로 고정 빈칸
            rich.append({"t": name + " ", "b": True})
            rich.append("\u00a0 ".join((f"{no}. " if no else "") + a for no, a in entries))
        out.append({"kind": "answers", "id": str(s.get("id", "")), "blocks": [{"block": row_block, "fields": {"no": str(s.get("id", "")), "answers": rich}}]})
    return out
