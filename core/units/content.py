"""원고 넣기 — 틀(인터페이스)에 원고(구현체)를 넣는다.

틀   = 글상자마다 자리 이름(atom.bind) + 임시 글(atom.text) + 스타일. 스타일은 틀이 가진다.
원고 = {"자리 이름": "글" | ["글1", "글2", …]} — 같은 자리가 여러 번이면 문서 읽는 순서대로 하나씩:
       쪽 순서 → 쪽 안에서는 위에서 아래(같은 높이면 왼쪽부터). 지면에 단(columns)이 있으면 단 순서
       (왼쪽 단 위→아래, 다음 단 — 여러 단에 걸친 상자는 그 높이에서 먼저). 원고에는 글만 온다.
글 잇기(atom.story) = 상자 여럿이 글 하나를 차례로 흘린다 — 자리는 첫 상자 하나, 넘친 줄은 그리기(units_compose.js)가 넘긴다.
넣으면 그 자리의 임시 글 대신 원고 글이 나온다. 원고에 없는 자리는 임시 글 그대로.

규약: docs/편집기_재현/원고자리_규약.md
"""
import copy


def plan_page_ids(plan):
    """문서(틀)의 쪽 id 순서 — 앞면 → 구간(간지 + 쪽) → 뒷면."""
    ids = list(plan.get("front") or [])
    for sc in plan.get("sections") or []:
        if sc.get("divider"):
            ids.append(sc["divider"])
        ids.extend(p["page"] if isinstance(p, dict) else p for p in sc.get("pages") or [])
    ids.extend(plan.get("back") or [])
    return ids


def _slot(it):
    """글상자의 자리 이름. 글 잇기의 이어지는 상자(story_seq ≥ 2)는 자리가 아니다 — 이야기 하나 = 자리 하나, 원고는 첫 상자에만."""
    from core.units.render import story_cont
    a = it.get("atom") or {}
    b = (a.get("bind") or "").strip()
    return b if b and not b.startswith("sys.") and a.get("t") == "text" and not story_cont(a) else None


def _reading_key(pg, width):
    """쪽 안 읽는 순서 — 단이 없으면 위 → 왼쪽. 단(pg.columns.n ≥ 2)이 있으면 단 순서(왼쪽 단 위→아래, 다음 단):
    여러 단에 걸친 상자(쪽 머리 제목 등)는 그 높이에서 단 순서를 끊고 먼저 읽는다(인디자인 기사 흐름처럼)."""
    col = pg.get("columns") or {}
    n = int(col.get("n") or 1)
    yx = lambda it: (round(float(it.get("y") or 0), 1), float(it.get("x") or 0))
    if n < 2:
        return lambda it: yx(it)
    m = pg.get("margins") or {}
    left = float(m.get("left", m.get("inside", 20)) or 0)
    right = float(m.get("right", m.get("outside", 20)) or 0)
    g = float(col.get("gutter") if col.get("gutter") is not None else 5)
    cw = max((float(width) - left - right - g * (n - 1)) / n, 1.0)
    width_ = lambda it: float(it.get("w") or (it.get("atom") or {}).get("w") or 0)      # 개체 폭(패널에서 고친 값)이 먼저
    col_of = lambda it: min(n - 1, max(0, int((float(it.get("x") or 0) + width_(it) / 2 - left + g / 2) // (cw + g))))   # 가운데가 든 단
    wide = lambda it: width_(it) > cw + g                               # 단 하나보다 넓다 = 여러 단에 걸친 상자(번호가 단 경계에 조금 걸친 것은 아니다)
    cuts = sorted(float(it.get("y") or 0) for it in pg.get("items") or [] if _slot(it) and wide(it))
    def key(it):
        y = float(it.get("y") or 0)
        seg = sum(1 for c in cuts if c <= y + 0.01)
        return (seg, 0, 0) + yx(it) if wide(it) else (seg, 1, col_of(it)) + yx(it)
    return key


def slots(pages, width_of=None):
    """문서의 자리 목록 — 읽는 순서대로 [(쪽 번호, 요소 번호, 자리 이름, 임시 글)]. 쪽 순서 → 쪽 안 읽는 순서(_reading_key).
    width_of(쪽) = 쪽 폭 mm(단 나누기에 쓴다, 없으면 210)."""
    out = []
    for pi, pg in enumerate(pages):
        items = [(i, it) for i, it in enumerate(pg.get("items") or []) if _slot(it)]
        key = _reading_key(pg, (width_of(pg) if width_of else None) or 210)
        items.sort(key=lambda t: key(t[1]))
        out += [(pi, i, _slot(it), (it.get("atom") or {}).get("text") or "") for i, it in items]
    return out


def schema(pages, width_of=None):
    """바깥에 알려 줄 자리 표 — 자리 이름마다 몇 번 나오는지와 임시 글(어떤 꼴의 글이 오는지 보기)."""
    sch = {}
    for _, _, name, sample in slots(pages, width_of):
        d = sch.setdefault(name, {"count": 0, "samples": []})
        d["count"] += 1
        if len(d["samples"]) < 3:
            d["samples"].append(sample if isinstance(sample, str) else "")
    return sch


def story_value(bind, records, slot_fmt=None):
    """여러 자리를 한 줄기 글로(인디자인 한 스토리 여러 단락 스타일) — bind = "번호+발문+지문+선지",
    records = [{자리: 글, …}, …] 문항 순서. 자리마다 문단(글 안 줄바꿈 = 문단 여럿)이 되고 문단 첫머리에 그 자리 표시(ps)가 붙어
    그리기(render._text_html)가 그 자리의 단락 스타일을 입힌다. slot_fmt[자리].inline 이면 따로 문단을 만들지 않고
    다음 문단 첫머리에 붙는다(문항 번호 — 발문 첫 줄 앞)."""
    fmt = slot_fmt or {}
    parts = [p for p in bind.split("+") if p]
    out, carry = [], []

    def para(slot, line):
        nonlocal carry
        if out:
            out.append("\n")
        out.append({"ps": slot, "t": ""})
        out.extend(carry)
        carry = []
        if line:
            out.append(line)
    for rec in records:
        for s in parts:
            v = rec.get(s) if isinstance(rec, dict) else None
            if v in (None, ""):
                continue
            if (fmt.get(s) or {}).get("inline"):
                carry.append({"ps": s, "inline": True, "t": str(v)})
                continue
            for line in str(v).split("\n"):
                para(s, line)
    if carry:                                                           # 붙을 문단이 없으면 제 문단으로
        para(carry[0]["ps"], "")
    return out


def fill(pages, content, width_of=None):
    """원고를 자리에 나눠 넣은 쪽 사본과 보고. 쪽 원본은 건드리지 않는다.
    보고 = {"filled": n, "unfilled": {자리: 남은 자리 수}, "extra": {자리: 남은 원고 수}, "unknown": [틀에 없는 자리 이름]}."""
    pages = copy.deepcopy(pages)
    queue = {k: (list(v) if isinstance(v, list) else [v]) for k, v in (content or {}).items()}
    known, filled, unfilled = set(), 0, {}
    for pi, i, name, _ in slots(pages, width_of):
        known.add(name)
        q = queue.get(name)
        if q and "+" in name and isinstance(q[0], dict):              # 여러 자리 한 줄기 — 문항 목록 전부가 이 글(잇기 상자들로 흘러간다)
            atom = pages[pi]["items"][i].get("atom") or {}
            pages[pi]["items"][i]["fields"] = {name: story_value(name, q, atom.get("slot_fmt"))}
            filled += len(q)
            q.clear()
        elif q:
            pages[pi]["items"][i]["fields"] = {name: q.pop(0)}     # 그리기는 글상자의 fields 를 자리 값으로 쓴다
            filled += 1
        else:
            unfilled[name] = unfilled.get(name, 0) + 1
    extra = {k: len(v) for k, v in queue.items() if v and k in known}
    unknown = sorted(k for k in queue if k not in known)
    return pages, {"filled": filled, "unfilled": unfilled, "extra": extra, "unknown": unknown}
