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
    for m in re.finditer(r'<g transform="translate\(([-\d.]+),([-\d.]+)\)"[^>]*>|<rect\b[^>]*>|<foreignObject\b[^>]*>(.*?)</foreignObject>', svg, re.S):
        tag = m.group(0)
        if tag.startswith("<g "):
            tx, ty = float(m.group(1)), float(m.group(2))
        elif tag.startswith("<rect"):
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


def compare(page_id="page_2", pno=8, set_id="301"):
    r = ref_page(pno)
    pg, spec, boxes = ours(page_id, set_id)
    rows = []

    def row(name, want, got, ok):
        rows.append({"항목": name, "기준": want, "우리": got, "ok": bool(ok)})

    row("판형", f"{r['w']:.0f}×{r['h']:.0f}mm", f"{spec['w']:.0f}×{spec['h']:.0f}mm",
        near(r["w"], float(spec["w"]), 0.6) and near(r["h"], float(spec["h"]), 0.6))

    band = max((x for x in r["rects"] if x["y"] <= 1 and x["w"] > 150), key=lambda x: x["h"], default=None)
    ourband = max((b for b in boxes if b["t"] == "rect" and b["y"] <= 1 and (b["w"] or 0) > 150), key=lambda b: b["h"] or 0, default=None)
    row("머리띠 높이", f"{band['h']}mm" if band else "-", f"{ourband['h']}mm" if ourband else "없음",
        band and ourband and near(band["h"], float(ourband["h"] or 0), 3))

    pbox = next((x for x in r["rects"] if 140 < x["w"] < 170 and 35 < x["h"] < 60), None)
    ourp = next((b for b in boxes if b["t"] == "rect" and 140 < (b["w"] or 0) < 170 and 35 < (b["h"] or 0) < 60), None)
    row("지문 상자 자리", f"x{pbox['x']} y{pbox['y']} {pbox['w']}×{pbox['h']}" if pbox else "-",
        f"x{ourp['x']} y{ourp['y']} {ourp['w']}×{ourp['h']}" if ourp else "없음",
        pbox and ourp and near(pbox["x"], ourp["x"]) and near(pbox["y"], ourp["y"]) and near(pbox["w"], float(ourp["w"])))

    ox = sorted([x for x in r["rects"] if 19 < x["w"] < 23 and 3.5 < x["h"] < 5.5], key=lambda x: x["y"])
    ourox = sorted([b for b in boxes if b["t"] == "rect" and 19 < (b["w"] or 0) < 23 and 3.5 < (b["h"] or 0) < 5.5], key=lambda b: b["y"])
    row("O/X 줄 수", len(ox), len(ourox), len(ox) == len(ourox))
    if len(ox) >= 2 and len(ourox) >= 2:
        g1 = round(ox[1]["y"] - ox[0]["y"], 1)
        g2 = round(ourox[1]["y"] - ourox[0]["y"], 1)
        row("줄 간격", f"{g1}mm", f"{g2}mm", near(g1, g2, 0.6))
        movable = len({round(x["x"]) for x in ox}) > 1
        ourmove = len({round(b["x"]) for b in ourox}) > 1
        row("O/X 상자가 문장 끝을 따라간다", "예 (줄마다 x 다름)", "예" if ourmove else "아니오 (한 자리 고정)", movable == ourmove)

    reftxt = {t["t"]: t for t in r["texts"]}
    for key in ("A2", "본문 O/X"):
        rt = reftxt.get(key)
        ot = next((b for b in boxes if (b.get("text") or "").strip() == key), None)
        if rt:
            row(f"머리 글 「{key}」 자리", f"x{rt['x']} y{rt['y']}", f"x{ot['x']} y{ot['y']}" if ot else "없음",
                ot and near(rt["x"], ot["x"], 2.5) and near(rt["y"], ot["y"], 3))
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
