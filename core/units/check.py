"""검수 — 틀 + 원고(세트) + 옷으로 책을 그려 보고 문제를 모은다. PDF 로 내기 전 게이트.

    report(lib, plan, skin_id, sets=None) → {"ok", "pages", "errors", "warns", "issues": [{level, msg}], "labels": [...]}

error  = 책으로 내면 안 되는 것 — 원고 빠진 자리(빈 채로 나감)·안 실린 원고·필수 자리 비움·틀에 없는 지면
warn   = 확인할 것 — 넘침(이어진 면)·한 면보다 큰 요소·토큰/스타일 없음·안 쓰인 원고
info   = 면 수·원고 수
그리는 코드(render)가 issue 를 남기고, 여기서는 세트 단위 검사(안 쓰인 kind)와 요약만 더한다.
"""
import json

from core.units import render, store


def _plan_page_ids(plan):
    ids = list(plan.get("front") or [])
    for sec in plan.get("sections") or []:
        if sec.get("divider"):
            ids.append(sec["divider"])
        ids += [pg.get("page") for pg in sec.get("pages") or []]
    ids += list(plan.get("back") or [])
    seen, out = set(), []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def layout(ctx, page, spec):
    """판 짜임새 — 눈으로 보기 전에 잡는다. 면 밖 · 자리끼리 겹침 · 줄 간격 들쭉날쭉."""
    W, H = float(spec["w"]), float(spec["h"])
    pg = json.loads(json.dumps(page))
    pg["_canvas"] = True
    pg["_noguides"] = True
    name = page.get("name") or page.get("id")
    boxes = []
    for p in render.place_items(ctx, pg, W, H):
        it = p["it"]
        boxes.append({"x": float(it.get("x") or 0), "y": p["y"], "w": p["w"], "h": p["h"],
                      "key": it.get("block") or it.get("part"), "slot": bool(it.get("block") or it.get("part"))})
    for b in boxes:
        out = max(-b["x"], -b["y"], b["x"] + b["w"] - W, b["y"] + b["h"] - H)
        if out > 2:                                   # 2mm 까지는 봐준다 — 글 높이는 어림이고 도련까지 쓰는 면도 있다
            ctx.issue("error" if b["slot"] else "warn",
                      f"지면 {name}: 요소가 면 밖으로 {out:.0f}mm 나갔다 ({b['x']:.0f},{b['y']:.0f} {b['w']:.0f}×{b['h']:.0f}mm)")
    slots = [b for b in boxes if b["slot"]]
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            if (a["x"] < b["x"] + b["w"] - 0.5 and b["x"] < a["x"] + a["w"] - 0.5
                    and a["y"] < b["y"] + b["h"] - 0.5 and b["y"] < a["y"] + a["h"] - 0.5):
                ctx.issue("warn", f"지면 {name}: 자리 둘이 겹친다 ({a['key']} · {b['key']}, {b['y']:.0f}mm 언저리)")
    rows = {}
    for b in slots:
        rows.setdefault(b["key"], []).append(b["y"])
    for key, ys in rows.items():
        if len(ys) < 3:
            continue
        ys = sorted(ys)
        gaps = [round(ys[i + 1] - ys[i], 2) for i in range(len(ys) - 1)]
        if max(gaps) - min(gaps) > 0.5:
            ctx.issue("warn", f"지면 {name}: {key} {len(ys)}줄의 간격이 들쭉날쭉하다 ({min(gaps):.1f}~{max(gaps):.1f}mm)")


def report(lib, plan, skin_id=None, sets=None):
    skins = store.by_id(lib.get("skins"))
    skin = skins.get(skin_id) or skins.get(plan.get("skin")) or (lib["skins"][0] if lib.get("skins") else {"id": "", "tokens": {}})   # 문서가 입은 옷으로 — 남의 옷으로 검수하면 토큰 없음이 쏟아진다
    ctx = render.Ctx(skin, lib, {"title": plan.get("name", ""), "tag": ""})
    sets = list(sets if sets is not None else lib.get("sets") or [])
    pages = render.plan_svgs(ctx, plan, sets, lib)
    # 어느 구간도 받지 않는 원고
    wanted = set()
    open_all = False
    for sec in plan.get("sections") or []:
        for pg in sec.get("pages") or []:
            if pg.get("sets"):
                wanted.update(pg["sets"])
            else:
                open_all = True
    if not open_all:
        for s in sets:
            if s.get("kind") not in wanted:
                ctx.issue("warn", f"원고 {s.get('id')} (kind {s.get('kind')}) 는 어느 구간도 받지 않아 책에 없다")
    specs = store.by_id(lib.get("specs"))
    pages_by_id = store.by_id(lib.get("pages"))
    for pid in _plan_page_ids(plan):
        pg = pages_by_id.get(pid)
        if pg:
            layout(ctx, pg, specs.get(plan.get("spec")) or specs.get(pg.get("spec")) or render.DEFAULT_SPEC)
    cont = sum(1 for p in pages if "이어서" in (p.get("label") or ""))
    if cont:
        ctx.issue("info", f"넘쳐서 이어진 면 {cont}")
    if not sets:
        ctx.issue("error", "원고(세트)가 하나도 없다")
    ctx.issue("info", f"{len(pages)}면 · 원고 {len(sets)}개")
    errors = [i for i in ctx.issues if i["level"] == "error"]
    warns = [i for i in ctx.issues if i["level"] == "warn"]
    return {"ok": not errors, "pages": len(pages), "errors": len(errors), "warns": len(warns),
            "issues": ctx.issues, "labels": [p.get("label") for p in pages]}
