# -*- coding: utf-8 -*-
"""PDF 받기 — **완성본 PDF 를 올리면 어느 틀인지 판정하고 디자인 초안을 만든다.**

전 개발자 시절 클로드가 세션에서 하던 일을 화면으로 옮긴 것이다:
  1. PDF 를 잰다  — 판형·재단·여백·서체·글자 크기·색 (PyMuPDF, mm)
  2. 판정한다     — 12개 틀의 페이지 틀 이미지와 나란히 놓고 "어느 틀의 디자인인가 / 새 틀인가"
  3. 초안을 만든다 — 그 틀의 손잡이(색·치수)를 PDF 값으로 채운 디자인을 `draft` 로 등록

⚠ 결과는 **초안**이다. 색·판형·여백은 잰 값이니 대체로 맞지만, 레이아웃(요소 배치)은 코드라
  PDF 에서 못 만든다. "새 틀" 판정이 나오면 Claude Code 세션에서 코드 작업이 필요하다.

키는 환경변수 `ANTHROPIC_API_KEY` 로만 받는다(파일에 두지 않는다). 모델은 `YONE_ASSIST_MODEL`.
"""
import base64
import collections
import datetime
import io
import json
import os
import re
import shutil
import uuid

from flask import Blueprint, abort, jsonify, request

bp = Blueprint("intake", __name__)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(REPO, "catalog")
INTAKE = os.path.join(CATALOG, "_intake")
MODEL = os.environ.get("YONE_ASSIST_MODEL", "claude-opus-5")
PT = 25.4 / 72.0


def have_key():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ── 1. 재기 ─────────────────────────────────────────────────────
def _hex(c):
    if isinstance(c, int):
        return "#%06x" % c
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in c[:3])
    return None


def _is_gray(h):
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return max(r, g, b) - min(r, g, b) < 18


def measure(pdf_path, sample=8):
    """PDF 한 권의 치수·서체·색. 전부 mm."""
    import fitz
    doc = fitz.open(pdf_path)
    n = len(doc)
    p0 = doc[0]
    mb, tb = p0.mediabox, p0.trimbox
    bleed = round((tb.x0 - mb.x0) * PT, 1) if tb != mb else 0.0
    trim_w, trim_h = round(tb.width * PT, 1), round(tb.height * PT, 1)
    # 본문 면 표본: 앞뒤 간지를 피해 가운데에서 고르게
    picks = sorted(set(max(2, min(n - 2, round(2 + i * (n - 4) / max(1, sample - 1)))) for i in range(sample))) if n > 4 else list(range(n))
    fonts = collections.Counter()
    sizes = collections.Counter()
    tcol = collections.Counter()
    dcol = collections.Counter()
    x0s, x1s, y0s, y1s = [], [], [], []
    head, foot = 0, 0
    for i in picks:
        pg = doc[i]
        W, H = pg.rect.width, pg.rect.height
        for b in pg.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    t = sp.get("text", "").strip()
                    if not t:
                        continue
                    k = len(t)
                    fonts[sp.get("font", "?")] += k
                    sizes[round(sp.get("size", 0) * 2) / 2] += k
                    h = _hex(sp.get("color"))
                    if h:
                        tcol[h] += k
                bx = ln["bbox"]
                if bx[1] < H * 0.12:
                    head += 1
                elif bx[3] > H * 0.94:
                    foot += 1
                else:
                    x0s.append(bx[0]); x1s.append(bx[2]); y0s.append(bx[1]); y1s.append(bx[3])
        for d in pg.get_drawings():
            for key in ("fill", "color"):
                h = _hex(d.get(key)) if d.get(key) is not None else None
                if h and h not in ("#ffffff", "#000000") and not _is_gray(h):
                    r = d.get("rect")
                    area = (r.width * r.height) if r else 1
                    dcol[h] += max(1, int(area * PT * PT))
    def q(v, lo):
        v = sorted(v)
        return v[int(len(v) * lo)] if v else None
    margins = None
    if x0s:
        margins = {"left": round(q(x0s, 0.05) * PT - (tb.x0 * PT), 1),
                   "right": round(trim_w - (q(x1s, 0.95) * PT - tb.x0 * PT), 1),
                   "top": round(q(y0s, 0.05) * PT - tb.y0 * PT, 1),
                   "bottom": round(trim_h - (q(y1s, 0.95) * PT - tb.y0 * PT), 1)}
    tot = sum(sizes.values()) or 1
    return {
        "pages": n, "trim_mm": [trim_w, trim_h], "bleed_mm": bleed,
        "media_mm": [round(mb.width * PT, 1), round(mb.height * PT, 1)],
        "margins_mm": margins,
        "fonts": [{"font": f, "share": round(c / tot, 3)} for f, c in fonts.most_common(8)],
        "sizes_pt": [{"pt": s, "share": round(c / tot, 3)} for s, c in sizes.most_common(6)],
        "text_colors": [{"hex": h, "share": round(c / tot, 3)} for h, c in tcol.most_common(8)],
        "shape_colors": [{"hex": h, "area_mm2": c} for h, c in dcol.most_common(8)],
        "running_header": head > len(picks) * 0.5, "running_footer": foot > len(picks) * 0.5,
        "sampled_pages": [i + 1 for i in picks],
    }


def render_pages(pdf_path, out_dir, dpi=50):
    """판정용 그림: 1면·2면·가운데 펼침면·마지막 면."""
    import fitz
    doc = fitz.open(pdf_path)
    n = len(doc)
    mid = max(3, (n // 2) // 2 * 2 + 1)
    picks = [("p1", 0), ("p2", 1 if n > 1 else 0), ("left", mid if n > mid else 0),
             ("right", mid + 1 if n > mid + 1 else 0), ("last", n - 1)]
    out = []
    seen = set()
    for label, i in picks:
        if i in seen:
            continue
        seen.add(i)
        p = os.path.join(out_dir, f"page_{label}.png")
        doc[i].get_pixmap(dpi=dpi).save(p)
        out.append({"label": label, "page": i + 1, "file": p})
    return out


# ── 2. 판정 ─────────────────────────────────────────────────────
def _b64png(path, max_px=900):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _series_doc(series):
    """계열 코드의 머리 설명(면 구성·원고 형식) — 디자인·이미지가 없어도 틀은 이걸로 판정한다."""
    try:
        import importlib
        m = importlib.import_module(f"core.render_vivlio.series.{series}")
        return (m.__doc__ or "").strip()[:1800]
    except Exception:
        return ""


def _series_knobs(series, cfg_dir=None):
    """손잡이 선언 + 값. 디자인이 없으면 `{"series": s}` 만으로 기본값을 읽는다."""
    import tempfile
    from core.render_vivlio import book as bookmod, knobs as kn
    try:
        if cfg_dir:
            bc = bookmod.load(cfg_dir)
        else:
            tmp = tempfile.mkdtemp(prefix="yone_series_")
            json.dump({"series": series}, open(os.path.join(tmp, "config.json"), "w", encoding="utf-8"))
            bc = bookmod.load(tmp)
        return [{"key": k["key"], "label": k["label"], "kind": k["kind"], "value": k["value"],
                 "unit": k.get("unit")} for k in kn.describe(bc, bookmod._series(bc))]
    except Exception:
        return []


def _template_cards():
    """틀 12개 전부 — 디자인이 없는 틀도 후보다(계열 코드가 곧 틀이다).

    디자인이 있으면 그 config·페이지 틀 이미지를 붙이고, 없으면 계열 코드의 구조 설명과
    손잡이 기본값만으로 판정한다. ⚠ 디자인이 0개라고 후보에서 빼면 그 틀은 영영
    "새 틀"로 오판된다(워크북 디자인을 지운 뒤 실제로 그랬다).
    """
    from routes.catalog import _meta, _designs, _design_cfg, _ddir
    cards = []
    for series, m in _meta().items():
        ds = _designs(series)
        d0 = ds[0] if ds else None
        cfg = _design_cfg(series, d0["id"]) if d0 else {}
        spec = _series_knobs(series, _ddir(series, d0["id"]) if d0 else None)
        img = None
        if d0 and d0["masters"]:
            f = d0["masters"][1]["file"] if len(d0["masters"]) > 1 else d0["masters"][0]["file"]
            img = os.path.join(_ddir(series, d0["id"]), f)
        page = cfg.get("page") or {k["key"].split(".")[1]: k["value"] for k in spec if k["key"].startswith("page.")}
        examples = []
        for dd in ds:
            it = (dd.get("intake") or {})
            if dd.get("draft"):
                continue                      # 확인 전 초안은 사례로 안 쓴다
            if it.get("verdict"):
                v = it["verdict"]; mm = it.get("measured") or {}
                examples.append({"design": dd["name"], "source": dd.get("source", ""), "confidence": v.get("confidence"),
                                 "trim_mm": mm.get("trim_mm"), "reasons": (v.get("reasons") or [])[:4]})
            else:
                examples.append({"design": dd["name"], "source": dd.get("source", ""), "registered_from_book": True})
        cards.append({"series": series, "name": m["name"], "desc": m.get("desc", ""), "doc": _series_doc(series),
                      "examples": examples,
                      "page": page, "fonts": [f["file"] if isinstance(f, dict) else f for f in cfg.get("fonts") or []],
                      "knobs": spec, "manuscript": cfg.get("manuscript"), "image": img, "has_design": bool(d0)})
    return cards


SYSTEM = """너는 Y.ONE STUDIO 교재 조판 시스템의 디자인 판정자다.

이 시스템에는 '틀'(계열 코드 = 면 구성·레이아웃·원고 읽는 규칙)이 12개 있고, 틀마다 '디자인'(색·치수·서체 값)이 여러 개 있다.
사용자가 올린 완성본 PDF 가 다음 중 무엇인지 판정한다:
  - "design": 기존 틀 중 하나와 **면 구성이 같다** (같은 자리에 같은 종류의 요소: 머리띠·탭·카드·상자·쪽번호·간지). 색·여백·판형·서체·글자 크기만 다르다.
  - "new":    어느 틀과도 면 구성이 다르다(요소 배치가 다름, 면 종류가 다름, 원고 종류가 다름). 코드 작업이 필요하다.
  - "unsure": 비슷한 틀이 있지만 확신이 없다.

판정 기준은 **구조**다. 색이 달라도 구조가 같으면 design 이다. 색이 같아도 구조가 다르면 new 다.
틀에 아직 디자인(이미지)이 없을 수 있다 — 그때는 그 틀의 '면 구성(계열 코드 설명)'을 읽고 올린 PDF 와 대조한다. 설명이 맞으면 이미지가 없어도 design 이다.
틀에 '확정된 사례'가 있으면 그것이 가장 강한 근거다 — 사람이 맞다고 확인한 판정이므로, 올린 PDF 가 그 사례와 같은 특징(간지·머리말·탭·쪽번호 규칙·판형)을 보이면 같은 틀로 본다.
design 이면 그 틀의 손잡이(knobs) 중 PDF 에서 읽힌 값으로 바꿀 것을 knobs=[{key, value}] 로 제안한다 — value 는 문자열: 색은 \"#rrggbb\", 치수는 \"12.5\" 같은 숫자 문자열(mm). 확실한 것만.
판형(trim)이 다르면 page.width / page.height 를 제안한다.
근거는 한국어로, 사람이 읽고 판단할 수 있게 구체적으로(어느 요소가 같고 다른지)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["design", "new", "unsure"]},
        "series": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "design_name": {"type": "string"},
        "knobs": {"type": "array", "items": {"type": "object",
                  "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                  "required": ["key", "value"], "additionalProperties": False}},
        "notes": {"type": "string"},
    },
    "required": ["verdict", "series", "confidence", "reasons", "design_name", "knobs", "notes"],
    "additionalProperties": False,
}


def judge(measured, pages, cards, hint=""):
    import anthropic
    content = []
    content.append({"type": "text", "text": "## 올린 PDF 의 계측값 (mm)\n```json\n" + json.dumps(measured, ensure_ascii=False, indent=1) + "\n```"})
    if hint:
        content.append({"type": "text", "text": "## 사용자가 적은 힌트\n" + hint})
    content.append({"type": "text", "text": "## 올린 PDF 의 면들"})
    for pg in pages:
        content.append({"type": "text", "text": f"({pg['label']} — {pg['page']}쪽)"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64png(pg["file"])}})
    content.append({"type": "text", "text": "## 기존 틀 12개"})
    for c in cards:
        txt = (f"### 틀 `{c['series']}` — {c['name']}\n{c['desc']}\n"
               f"면 구성(계열 코드 설명):\n{c['doc'] or '(설명 없음)'}\n"
               f"판형 {c['page']}\n서체 {c['fonts'] or '(디자인 없음 — 계열 기본)'}\n"
               f"원고 {json.dumps(c['manuscript'], ensure_ascii=False)[:200] if c['manuscript'] else '(계열 규칙)'}\n손잡이:\n"
               + "\n".join(f"  - {k['key']} ({k['label']}, {k['kind']}) = {k['value']}" for k in c["knobs"]))
        if c.get("examples"):
            txt += "\n이 틀로 **확정된 사례**(사람이 맞다고 확인한 것):\n" + "\n".join(
                f"  - {e['design']} ← {e['source']}" + (f" (판형 {e['trim_mm']}, 확신 {e['confidence']}) 근거: " + " / ".join(e["reasons"]) if e.get("reasons") else " (책 폴더에서 등록)")
                for e in c["examples"])
        content.append({"type": "text", "text": txt})
        if c["image"] and os.path.exists(c["image"]):
            content.append({"type": "text", "text": f"(틀 `{c['series']}` 의 페이지 틀 — 원고 자리는 회색)"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64png(c["image"], 700)}})
        else:
            content.append({"type": "text", "text": f"(틀 `{c['series']}` 는 아직 등록된 디자인·이미지가 없다 — 위 '면 구성' 설명과 손잡이로 판단한다. 설명이 올린 PDF 의 면 구성과 맞으면 design 이다)"})
    content.append({"type": "text", "text": "판정하라. series 는 design/unsure 일 때 틀의 영문 키(예: vocacard), new 면 null."})
    client = anthropic.Anthropic()
    r = client.messages.create(
        model=MODEL, max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next(b.text for b in r.content if b.type == "text")
    out = json.loads(text)
    # 손잡이는 [{key, value}] 로 받아 dict 로 (스키마가 열린 object 를 못 받는다)
    out["knobs"] = {k["key"]: k["value"] for k in (out.get("knobs") or []) if k.get("key")}
    return out


# ── 3. 초안 등록 ────────────────────────────────────────────────
def _vet_knobs(series, design_id, knobs):
    """모델이 준 손잡이 값을 그 틀의 선언과 대조해 통과한 것만."""
    from routes.catalog import _ddir
    from core.render_vivlio import book as bookmod, knobs as kn
    bc = bookmod.load(_ddir(series, design_id))
    spec = {k["key"]: k for k in kn.describe(bc, bookmod._series(bc))}
    ok, bad = {}, []
    for key, val in (knobs or {}).items():
        k = spec.get(key)
        if not k:
            bad.append(f"모르는 손잡이 {key}"); continue
        if k["kind"] == "color":
            if not (isinstance(val, str) and re.match(r"^#[0-9a-fA-F]{6}$", val)):
                bad.append(f"{key}: 색 형식 아님 ({val})"); continue
            ok[key] = val.lower()
        else:
            try:
                v = float(val)
            except (TypeError, ValueError):
                bad.append(f"{key}: 숫자 아님 ({val})"); continue
            lo, hi = k.get("min"), k.get("max")
            if lo is not None and v < lo or hi is not None and v > hi:
                bad.append(f"{key}: 범위 밖 {v} ({lo}~{hi})"); continue
            ok[key] = v
    return ok, bad


def register_draft(series, verdict, measured, pdf_path, pages, pdf_name):
    """그 틀의 첫 디자인 config 를 바탕으로 손잡이 값을 덮어쓴 초안 디자인을 만든다."""
    from routes.catalog import _ddir, _designs, _next_id
    from core.render_vivlio import knobs as kn
    ds = _designs(series)
    did = _next_id(series)
    d = _ddir(series, did)
    os.makedirs(d, exist_ok=True)
    if ds:
        base = ds[0]["id"]
        raw = open(os.path.join(_ddir(series, base), "config.json"), encoding="utf-8").read()
    else:
        # 디자인이 없는 틀 — 계열 기본값(`{"series": s}`)에서 시작. 손잡이 대조도 그 기준으로
        base = None
        raw = json.dumps({"series": series, "book": {"title": pdf_name}, "page": {"width": 210, "height": 297, "bleed": 3},
                          "output": {"dir": "."}}, ensure_ascii=False, indent=2) + "\n"
        json.dump(json.loads(raw), open(os.path.join(d, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ok, bad = _vet_knobs(series, base or did, verdict.get("knobs") or {})
    changes = dict(ok)
    tw, th = measured["trim_mm"]
    cfg0 = json.loads(raw)
    pg = cfg0.get("page") or {}
    if abs(float(pg.get("width", 0)) - tw) > 1 or abs(float(pg.get("height", 0)) - th) > 1:
        changes["page.width"] = tw
        changes["page.height"] = th
    if measured["bleed_mm"] and abs(float(pg.get("bleed", 3)) - measured["bleed_mm"]) > 0.4:
        changes["page.bleed"] = measured["bleed_mm"]
    try:
        raw = kn.patch_text(raw, changes) if changes else raw
    except Exception:
        raw = json.dumps(kn.apply(json.loads(raw), changes), ensure_ascii=False, indent=2) + "\n"
    cfg = json.loads(raw)
    cfg["_디자인"] = f"PDF 초안 — {pdf_name} ({datetime.date.today().isoformat()}). 확인 전."
    json.dump(cfg, open(os.path.join(d, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if base:
        for sub in ("overrides.css", "assets", "참고"):
            src = os.path.join(_ddir(series, base), sub)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(d, sub))
            elif os.path.isdir(src):
                shutil.copytree(src, os.path.join(d, sub), dirs_exist_ok=True)
    shutil.copy2(pdf_path, os.path.join(d, "reference.pdf"))
    # 올린 PDF 의 면을 견본 사진으로 (이 디자인이 목표로 하는 모습)
    for k, p in enumerate(pages, 1):
        shutil.copy2(p["file"], os.path.join(d, f"preview_{k}.png"))
    json.dump({"name": verdict.get("design_name") or pdf_name, "desc": "PDF 초안 · 확인 필요",
               "source": f"PDF: {pdf_name}", "date": datetime.date.today().isoformat(), "draft": True,
               "intake": {"verdict": verdict, "measured": measured, "applied": changes, "rejected": bad}},
              open(os.path.join(d, "design.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return did, changes, bad


# ── 라우트 ───────────────────────────────────────────────────────
@bp.route("/api/catalog/intake", methods=["POST"])
def intake():
    """① 잰다 ② 판정한다 — 여기서 멈춘다. 등록은 사람이 확인한 뒤 `decide` 로."""
    if not have_key():
        return jsonify({"error": "클로드 키가 없다. bin/studio 를 띄우기 전에 `export ANTHROPIC_API_KEY=…` (README_로컬실행.md)"}), 400
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF 파일을 올려야 한다"}), 400
    hint = (request.form.get("hint") or "").strip()
    jid = uuid.uuid4().hex[:8]
    d = os.path.join(INTAKE, jid)
    os.makedirs(d, exist_ok=True)
    pdf_name = os.path.basename(f.filename)
    pdf_path = os.path.join(d, "ref.pdf")
    f.save(pdf_path)
    try:
        measured = measure(pdf_path)
        pages = render_pages(pdf_path, d)
    except Exception as e:
        return jsonify({"error": f"PDF 를 못 읽었다: {e}"}), 400
    cards = _template_cards()
    try:
        verdict = judge(measured, pages, cards, hint)
    except Exception as e:
        return jsonify({"error": f"판정 실패: {e}", "measured": measured}), 500
    state = {"id": jid, "pdf": pdf_name, "hint": hint, "measured": measured, "verdict": verdict,
             "pages": [{"label": p["label"], "page": p["page"], "file": os.path.basename(p["file"])} for p in pages],
             "date": datetime.date.today().isoformat(), "status": "judged"}
    json.dump(state, open(os.path.join(d, "state.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from routes.catalog import _meta
    return jsonify({**state, "templates": [{"series": k, "name": v["name"]} for k, v in _meta().items()]})


@bp.route("/api/catalog/intake/<jid>/decide", methods=["POST"])
def decide(jid):
    """사람의 결정. series = 틀 키 → 그 틀의 디자인 초안 / "__new__" → 새 틀 요청."""
    if not re.match(r"^[0-9a-f]{8}$", jid):
        abort(404)
    d = os.path.join(INTAKE, jid)
    sp = os.path.join(d, "state.json")
    if not os.path.exists(sp):
        abort(404)
    state = json.load(open(sp, encoding="utf-8"))
    body = request.get_json(silent=True) or {}
    series = (body.get("series") or "").strip()
    name = (body.get("name") or "").strip()
    from routes.catalog import _meta
    if series == "__new__":
        state.update({"status": "new_request", "name": name or state["pdf"], "note": body.get("note", "")})
        json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return jsonify({"ok": True, "status": "new_request", "id": jid})
    if series not in _meta():
        return jsonify({"error": "모르는 틀"}), 400
    verdict = dict(state["verdict"])
    if name:
        verdict["design_name"] = name
    # 판정과 다른 틀을 골랐으면 그 틀 손잡이가 아닌 값은 검증에서 걸러진다(색 제안은 판정 틀 기준이므로)
    chosen_differs = series != state["verdict"].get("series")
    pages = [{"label": p["label"], "page": p["page"], "file": os.path.join(d, p["file"])} for p in state["pages"]]
    try:
        did, applied, bad = register_draft(series, verdict, state["measured"], os.path.join(d, "ref.pdf"), pages, state["pdf"])
    except Exception as e:
        return jsonify({"error": f"초안 등록 실패: {e}"}), 500
    # 사람이 고른 틀이므로 판정 근거는 "사람 확인"으로 기록
    dj = os.path.join(_ddir_(series, did), "design.json")
    info = json.load(open(dj, encoding="utf-8"))
    info["intake"]["decided_by_user"] = True
    info["intake"]["judged_series"] = state["verdict"].get("series")
    json.dump(info, open(dj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    state.update({"status": "registered", "series": series, "design": did})
    json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return jsonify({"ok": True, "series": series, "design": did, "link": f"/catalog/{series}/{did}",
                    "applied": applied, "rejected": bad, "chosen_differs": chosen_differs})


def _ddir_(series, design):
    from routes.catalog import _ddir
    return _ddir(series, design)


def pending():
    """판정은 됐는데 사람이 아직 결정하지 않은 PDF."""
    out = []
    if not os.path.isdir(INTAKE):
        return out
    for jid in sorted(os.listdir(INTAKE)):
        sp = os.path.join(INTAKE, jid, "state.json")
        if not os.path.exists(sp):
            continue
        st = json.load(open(sp, encoding="utf-8"))
        if st.get("status") == "judged":
            v = st["verdict"]
            out.append({"id": jid, "pdf": st.get("pdf"), "date": st.get("date"), "verdict": v.get("verdict"),
                        "series": v.get("series"), "confidence": v.get("confidence"), "design_name": v.get("design_name"),
                        "reasons": v.get("reasons", []), "trim": st["measured"].get("trim_mm"), "pages": st["measured"].get("pages")})
    return out


def new_requests():
    """새 틀 요청 목록 — 사람이 '분류 안 됨'으로 남긴 PDF 들. Claude Code 세션에서 집어 간다."""
    out = []
    if not os.path.isdir(INTAKE):
        return out
    for jid in sorted(os.listdir(INTAKE)):
        sp = os.path.join(INTAKE, jid, "state.json")
        if not os.path.exists(sp):
            continue
        st = json.load(open(sp, encoding="utf-8"))
        if st.get("status") == "new_request":
            out.append({"id": jid, "name": st.get("name"), "pdf": st.get("pdf"), "date": st.get("date"),
                        "note": st.get("note", ""), "trim": st["measured"].get("trim_mm"), "pages": st["measured"].get("pages"),
                        "judged": st["verdict"].get("series"), "confidence": st["verdict"].get("confidence"),
                        "reasons": st["verdict"].get("reasons", [])[:3], "path": f"catalog/_intake/{jid}/ref.pdf"})
    return out


@bp.route("/api/catalog/intake/<jid>", methods=["DELETE"])
def intake_del(jid):
    if not re.match(r"^[0-9a-f]{8}$", jid):
        abort(404)
    shutil.rmtree(os.path.join(INTAKE, jid), ignore_errors=True)
    return jsonify({"ok": True})


@bp.route("/api/catalog/design/<series>/<design>/confirm", methods=["POST"])
def confirm(series, design):
    """초안 → 확정. design.json 의 draft 를 내린다."""
    from routes.catalog import _ddir, _ID
    if not _ID.match(design):
        abort(404)
    p = os.path.join(_ddir(series, design), "design.json")
    if not os.path.exists(p):
        abort(404)
    info = json.load(open(p, encoding="utf-8"))
    info["draft"] = False
    info["desc"] = (info.get("desc") or "").replace("PDF 초안 · 확인 필요", "PDF 에서 만든 디자인")
    json.dump(info, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return jsonify({"ok": True})


@bp.route("/api/catalog/claude")
def claude_status():
    return jsonify({"enabled": have_key(), "model": MODEL})
