"""검수 — 틀 + 원고(세트) + 옷으로 책을 그려 보고 문제를 모은다. PDF 로 내기 전 게이트.

    report(lib, plan, skin_id, sets=None) → {"ok", "pages", "errors", "warns", "issues": [{level, msg}], "labels": [...]}

error  = 책으로 내면 안 되는 것 — 원고 빠진 자리(빈 채로 나감)·안 실린 원고·필수 자리 비움·틀에 없는 지면
warn   = 확인할 것 — 넘침(이어진 면)·한 면보다 큰 요소·토큰/스타일 없음·안 쓰인 원고
info   = 면 수·원고 수
그리는 코드(render)가 issue 를 남기고, 여기서는 세트 단위 검사(안 쓰인 kind)와 요약만 더한다.
"""
from core.units import render, store


def report(lib, plan, skin_id=None, sets=None):
    skins = store.by_id(lib.get("skins"))
    skin = skins.get(skin_id) or (lib["skins"][0] if lib.get("skins") else render.DEFAULT_SKIN)
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
