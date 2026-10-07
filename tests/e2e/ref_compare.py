"""기준 대조 — 실제 스텝바이스텝 워크북 면(reference.pdf)과 우리 지면을 항목별로 잰다.

    python3 tests/e2e/ref_compare.py [지면id] [기준쪽] [--json]

기준 항목은 PDF 에서 그때그때 뽑는다(판형·머리띠·지문 상자·발문·줄 간격·O/X 상자·꼬리).
우리 지면은 :5099 라이브러리에서 읽는다. 틀리면 무엇이 몇 mm 다른지 한 줄로 말한다.
"""
import json
import os
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(REPO, "catalog", "workbook", "designs", "d1", "reference.pdf")
BASE = os.environ.get("YONE_BASE", "http://127.0.0.1:5099")
TOL = 1.5                                   # mm — 이 안이면 맞은 것으로 본다


def mm(v):
    return round(v / 72 * 25.4, 1)


def ref_page(pno):
    """기준 면 하나 → 잴 수 있는 값들."""
    import fitz
    d = fitz.open(REF)
    p = d[pno - 1]
    out = {"w": mm(p.rect.width), "h": mm(p.rect.height), "texts": [], "rects": []}
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = s["text"].strip()
                if t:
                    out["texts"].append({"x": mm(s["bbox"][0]), "y": mm(s["bbox"][1]), "size": round(s["size"] / 72 * 25.4 * 72 / 25.4, 1),
                                         "pt": round(s["size"], 1), "font": s["font"], "color": f"#{s['color']:06x}", "t": t})
    for dr in p.get_drawings():
        r = dr["rect"]
        if r.width < 1.5 or r.height < 1.5:
            continue
        hexf = None
        if dr.get("fill"):
            hexf = "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in dr["fill"][:3])
        out["rects"].append({"x": mm(r.x0), "y": mm(r.y0), "w": mm(r.width), "h": mm(r.height), "fill": hexf})
    return out


def ours(page_id, set_id=None):
    """우리 지면을 **실제로 그려서** 잰다 — 문장 끝에 붙는 개체처럼 그릴 때 정해지는 자리까지 본다."""
    import re
    sys.path.insert(0, REPO)
    from core.units import render, store
    lib = store.library()
    by = lambda k: {x["id"]: x for x in lib[k]}                          # noqa: E731
    pg = by("pages").get(page_id)
    if not pg:
        raise SystemExit(f"지면 {page_id} 없음 — 있는 것: {[p['id'] for p in lib['pages']]}")
    spec = by("specs").get(pg.get("spec") or "a4") or {"w": 210, "h": 297}
    skin = by("skins").get((next((p for p in lib["plans"] if page_id in json.dumps(p)), {}) or {}).get("skin") or "") or lib["skins"][0]
    st = next((x for x in lib["sets"] if x["id"] == set_id), None) if set_id else None
    ctx = render.Ctx(skin, lib)
    svgs = render.page_canvas_svgs(ctx, pg, spec, sample_set=st)
    svg = svgs[0]["svg"] if isinstance(svgs[0], dict) else svgs[0]
    boxes, tx, ty = [], 0.0, 0.0
    attr = lambda tag, k: (re.search(rf'\b{k}="([-\d.]+)"', tag) or [None, None])[1]      # noqa: E731
    for m in re.finditer(r'<g transform="translate\(([-\d.]+),([-\d.]+)\)"[^>]*>|<rect\b[^>]*>|<ellipse\b[^>]*>|<foreignObject\b[^>]*>(.*?)</foreignObject>', svg, re.S):
        tag = m.group(0)
        if tag.startswith("<g "):
            tx, ty = float(m.group(1)), float(m.group(2))
        elif tag.startswith("<rect") or tag.startswith("<ellipse"):
            if tag.startswith("<ellipse"):
                cx, cy, rx, ry = (attr(tag, k) for k in ("cx", "cy", "rx", "ry"))
                if None in (cx, cy, rx, ry):
                    continue
                x, y, w, h = float(cx) - float(rx), float(cy) - float(ry), float(rx) * 2, float(ry) * 2
            else:
                x, y, w, h = (attr(tag, k) for k in ("x", "y", "width", "height"))
                if None in (x, y, w, h):
                    continue
            boxes.append({"x": round(tx + float(x), 1), "y": round(ty + float(y), 1),
                          "w": round(float(w), 1), "h": round(float(h), 1), "t": "rect", "text": ""})
        else:
            txt = re.sub(r"<[^>]+>", "", m.group(3) or "").strip()
            if txt:
                boxes.append({"x": round(tx, 1), "y": round(ty, 1), "w": 0, "h": 0, "t": "text", "text": txt})
    return pg, spec, boxes


def near(a, b, tol=TOL):
    return a is not None and b is not None and abs(a - b) <= tol


def compare(page_id="page_2", pno=8, set_id=None):
    """기준 쪽에서 잴 것을 스스로 뽑아 우리 지면과 맞춰 본다 — 유형마다 항목이 다르다."""
    r = ref_page(pno)
    pg, spec, boxes = ours(page_id, set_id)
    rows = []

    def row(name, want, got, ok):
        rows.append({"항목": name, "기준": want, "우리": got, "ok": bool(ok)})

    row("판형", f"{r['w']:.0f}×{r['h']:.0f}mm", f"{spec['w']:.0f}×{spec['h']:.0f}mm",
        near(r["w"], float(spec["w"]), 6.5) and near(r["h"], float(spec["h"]), 6.5))     # A4 로 옮기면 6mm 차

    # 1) 면(색 있는 상자) — 기준에 있는 큰 면마다 우리 쪽에 비슷한 것이 있나
    rboxes = sorted([x for x in r["rects"] if x["w"] > 20 and x["h"] > 4], key=lambda x: (x["y"], x["x"]))
    oboxes = [b for b in boxes if b["t"] == "rect" and b["w"] > 20 and b["h"] > 4]
    for rb in rboxes[:4]:
        hit = min(oboxes, key=lambda b: abs(b["y"] - rb["y"]) + abs(b["w"] - rb["w"]) / 3, default=None)
        ok = hit and near(hit["y"], rb["y"], 4) and near(hit["w"], rb["w"], 10)
        row(f"면 {rb['w']:.0f}×{rb['h']:.0f} @y{rb['y']:.0f}",
            f"x{rb['x']:.0f} y{rb['y']:.0f}", (f"x{hit['x']:.0f} y{hit['y']:.0f}" if hit else "없음"), ok)

    # 2) 머리 글 — 기준의 큰 글자(코드·제목)
    heads = [t for t in r["texts"] if t["pt"] >= 12 and t["y"] < 30][:2]
    for ht in heads:
        hit = next((b for b in boxes if b["t"] == "text" and b["text"].strip() == ht["t"]), None)
        row(f"머리 글 「{ht['t'][:10]}」", f"y{ht['y']:.0f}", (f"y{hit['y']:.0f}" if hit else "없음"),
            hit is not None and near(hit["y"], ht["y"], 3))

    # 3) 되풀이되는 줄 — 기준에서 같은 크기 상자가 3개 이상 세로로 늘어서면 간격을 본다
    from collections import defaultdict
    g = defaultdict(list)
    for x in r["rects"]:
        g[(round(x["w"]), round(x["h"]))].append(x["y"])
    rep = max((v for k, v in g.items() if len(v) >= 3), key=len, default=None)
    if rep:
        rep = sorted(rep)
        same = [x for x in r["rects"] if (round(x["w"]), round(x["h"])) == max(((k, len(v)) for k, v in g.items() if len(v) >= 3), key=lambda kv: kv[1])[0]]
        xs = sorted(x["x"] for x in same)
        gap = round(rep[1] - rep[0], 1) or round(xs[1] - xs[0], 1)
        og = defaultdict(list)
        for b in boxes:
            if b["t"] == "rect":
                og[(round(b["w"]), round(b["h"]))].append(b["y"])
        orep = max((v for v in og.values() if len(v) >= 3), key=len, default=None)
        ogap = None
        if orep:
            key = max(((k, len(v)) for k, v in og.items() if len(v) >= 3), key=lambda kv: kv[1])[0]
            oxs = sorted(b["x"] for b in boxes if b["t"] == "rect" and (round(b["w"]), round(b["h"])) == key)
            ys = sorted(orep)
            ogap = round(ys[1] - ys[0], 1) or (round(oxs[1] - oxs[0], 1) if len(oxs) > 1 else None)
        row("되풀이 도형 수", len(rep), len(orep) if orep else 0, orep is not None and len(orep) == len(rep))
        row("줄 간격", f"{gap}mm", f"{ogap}mm" if ogap else "없음", ogap is not None and near(gap, ogap, 0.6))
        movable = len({round(x["x"]) for x in r["rects"] if round(x["w"]) == round(rep and 0 or 0)}) > 1
    # 4) 원고 자리 — 지면에 자리가 몇 개인가 (기준은 셀 수 없으니 0 보다 큰지만)
    slots = sum(1 for it in (pg.get("items") or []) if (it.get("atom") or {}).get("bind") or it.get("block"))
    row("원고 자리", "1개 이상", f"{slots}개", slots > 0)
    ok = sum(1 for x in rows if x["ok"])
    return rows, ok, len(rows)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pid = args[0] if args else "page_2"
    pno = int(args[1]) if len(args) > 1 else 8
    rows, ok, n = compare(pid, pno)
    if "--json" in sys.argv:
        print(json.dumps({"ok": ok, "n": n, "rows": rows}, ensure_ascii=False, indent=1))
    else:
        print(f"기준: reference.pdf {pno}쪽 · 우리: {pid}")
        for x in rows:
            print(f"  {'맞음' if x['ok'] else '다름'}  {x['항목']:32} 기준 {str(x['기준']):28} 우리 {x['우리']}")
        print(f"\n== {ok}/{n} 맞음 ==")
