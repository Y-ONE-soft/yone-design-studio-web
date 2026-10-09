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
CATALOG = os.environ.get("YONE_CATALOG_DIR") or os.path.join(REPO, "catalog")   # 컨테이너: 볼륨
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


def _image_to_pdf(img_path, pdf_path, dpi=300):
    """지면 이미지 한 장을 PDF 한 면으로. 크기는 dpi 가정으로 환산."""
    import fitz
    from PIL import Image
    w, h = Image.open(img_path).size
    doc = fitz.open()
    page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
    page.insert_image(page.rect, filename=img_path)
    doc.save(pdf_path)
    doc.close()


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
    if not knobs:                      # 손잡이가 없으면 대조할 것도 없다 — 조판 코드가 없는 틀(표지 등)도 등록되게
        return {}, []
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
    from routes.catalog import _ddir, _designs, _new_id
    from core.render_vivlio import knobs as kn
    ds = _designs(series)
    did = _new_id(series)
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
    # 올린 PDF 가 이 디자인의 **아트워크 원본**이다 — 디자인 폴더 참고/ 에 두고 config 가
    # 그것을 가리키게 한다(nhj 맥 절대경로 같은 바깥 파일에 기대지 않는다). 책을 만들 때
    # 참고/·assets/ 가 책 폴더로 같이 복사된다.
    os.makedirs(os.path.join(d, "참고"), exist_ok=True)
    shutil.copy2(pdf_path, os.path.join(d, "참고", "reference.pdf"))
    cfg, rewired = _point_artwork_at(cfg, "참고/reference.pdf")
    json.dump(cfg, open(os.path.join(d, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    artwork = extract_artwork(series, d)
    # 올린 PDF 의 면을 견본 사진으로 (이 디자인이 목표로 하는 모습)
    for k, p in enumerate(pages, 1):
        shutil.copy2(p["file"], os.path.join(d, f"preview_{k}.png"))
    json.dump({"name": verdict.get("design_name") or pdf_name, "desc": "PDF 초안 · 확인 필요",
               "source": f"PDF: {pdf_name}", "date": datetime.date.today().isoformat(), "draft": True,
               "intake": {"verdict": verdict, "measured": measured, "applied": changes, "rejected": bad,
                          "artwork": {"rewired": rewired, **artwork}}},
              open(os.path.join(d, "design.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return did, changes, bad


_EXTERNAL = re.compile(r"^(\$\{STUDIO\}|~|/)")


def _point_artwork_at(cfg, ref):
    """config 안의 아트워크 원본 경로(`src_pdf`·`cover_pdf`·`art_pdf`·`jobs[].src`)를
    디자인 폴더의 참고 PDF 로 돌린다. 이미 디자인 폴더 상대경로면 그대로 둔다.
    Returns: (cfg, 바꾼 키 목록)."""
    done = []
    a = cfg.get("assets")
    if isinstance(a, dict):
        for k in ("src_pdf", "cover_pdf"):
            v = a.get(k)
            if isinstance(v, str) and (not v or _EXTERNAL.match(v)):
                a[k] = ref
                done.append(f"assets.{k}")
        for j in a.get("jobs") or []:
            if isinstance(j, dict) and isinstance(j.get("src"), str) and _EXTERNAL.match(j["src"]):
                j["src"] = ref
                done.append(f"assets.jobs.{j.get('name', '?')}.src")
    f = cfg.get("finish")
    if isinstance(f, dict):
        v = f.get("art_pdf")
        if isinstance(v, str) and _EXTERNAL.match(v):
            f["art_pdf"] = ref
            done.append("finish.art_pdf")
        for key in ("inserts", "append"):
            for it in f.get(key) or []:
                if isinstance(it, dict) and isinstance(it.get("pdf"), str) and _EXTERNAL.match(it["pdf"]):
                    it["pdf"] = ref
                    done.append(f"finish.{key}.pdf")
    return cfg, done


def extract_artwork(series, design_dir, log=None):
    """디자인 폴더의 참고 PDF 에서 로고·조각을 잘라 `assets/` 로 (계열 `gen_theme`).

    실패해도 디자인 등록은 막지 않는다 — 어느 조각이 안 나왔는지만 남긴다.
    Returns: {"ok": bool, "log": [...], "assets": [...]}"""
    from core.render_vivlio.config import BookConfig
    from core.render_vivlio import book as book_mod
    lines = []
    cfg_p = os.path.join(design_dir, "config.json")
    try:
        cfg = BookConfig(json.load(open(cfg_p, encoding="utf-8")), design_dir)
        if not (cfg.section("assets") or {}).get("jobs"):
            return {"ok": True, "log": ["자를 조각이 없는 틀"], "assets": _asset_files(design_dir)}
        book_mod.gen_theme(cfg, log=lambda m: (lines.append(str(m)), log and log(m)))
        return {"ok": True, "log": lines, "assets": _asset_files(design_dir)}
    except Exception as e:
        lines.append(f"실패: {e}")
        return {"ok": False, "log": lines, "assets": _asset_files(design_dir)}


def _asset_files(design_dir):
    a = os.path.join(design_dir, "assets")
    return sorted(os.listdir(a)) if os.path.isdir(a) else []


# ── 라우트 ───────────────────────────────────────────────────────
ASK_SYSTEM = """너는 Y.ONE 스튜디오(영어 교재 코드 조판, Vivliostyle)의 디자인 도우미다. 한국어로 짧고 구체적으로 답한다.
스튜디오의 구조: 폴더(카탈로그 디렉토리) → 틀(계열 코드 = 면 구성, 코드로만 늘어남) → 디자인(그 틀의 한 모습: 색·치수·서체) → 원고를 넣으면 책.
콘텐츠 연동 단위는 블록 11종: B1 원문지문·B2 지문분석·B3 요약노트·B4 개념·전략·B5 어휘·B6 문항·B7 변형지문·B8 문장드릴·B9 정답해설·B10 구조면·B11 관리양식.
사용자가 할 수 있는 명령: `/ 틀 등록하기`(첨부한 완성본 PDF·지면 이미지를 판정해 기존 틀의 디자인으로 등록), `/ 새 틀 요청`(면 구성이 다른 것 — 클로드 코드 세션에서 코드로 만듦), `/ 디자인 검색`, `/ 불러오기`.
형식: 짧은 문단과 `-` 목록만. 마크다운 제목(#)·코드 펜스(```)는 쓰지 않는다. 명령은 `/ 틀 등록하기` 처럼 한 줄 안에 적는다.
원칙: 디자인은 지어내지 않고 기존 완성본을 실측해 옮긴다. 사용자가 원하는 디자인을 설명하거나 지면을 첨부하면 (1) 어느 틀·폴더에 가장 가까운지 (2) 기존 디자인으로 되는지, 새 틀이 필요한지 (3) 다음에 할 명령 하나를 말한다. 모르는 것은 모른다고 한다. 없는 기능을 있다고 하지 않는다."""


@bp.route("/api/catalog/ask", methods=["POST"])
def ask():
    """기본 프롬프트 — 원하는 디자인을 말로(+첨부) 물으면 클로드가 어느 틀·폴더인지, 다음 명령이 무엇인지 답한다.
    `history` = [{role, text}] 최근 대화(클라이언트가 들고 있음). 첨부는 판정용 면 그림으로 같이 보낸다(등록은 안 한다)."""
    import tempfile
    if not have_key():
        return jsonify({"error": "클로드 키가 없다 (~/.config/yone/env)"}), 400
    from routes.catalog import _dirs, _meta
    text = (request.form.get("text") or "").strip()
    try:
        history = json.loads(request.form.get("history") or "[]")[-8:]
    except ValueError:
        history = []
    f = request.files.get("file")
    content = []
    tmp = None
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        tmp = tempfile.mkdtemp(prefix="ask_")
        src = os.path.join(tmp, "ref" + (ext if ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp") else ".bin"))
        f.save(src)
        try:
            if ext == ".pdf":
                pages = render_pages(src, tmp)[:3]
                content.append({"type": "text", "text": f"## 첨부 PDF `{f.filename}` 의 면들 (계측 {json.dumps(measure(src), ensure_ascii=False)[:600]})"})
                for pg in pages:
                    content.append({"type": "text", "text": f"({pg['label']} — {pg['page']}쪽)"})
                    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64png(pg["file"])}})
            elif ext in (".png", ".jpg", ".jpeg", ".webp"):
                content.append({"type": "text", "text": f"## 첨부 지면 이미지 `{f.filename}`"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64png(src)}})
        except Exception as e:
            content.append({"type": "text", "text": f"(첨부 `{f.filename}` 을 못 읽었다: {e})"})
    dirs = {d["id"]: d["name"] for d in _dirs()}
    cat = "\n".join(f"- 폴더 「{dirs.get(v.get('dir'), '기타')}」 › 틀 `{k}` {v['name']}: {v.get('desc', '')}" for k, v in _meta().items())
    content.append({"type": "text", "text": "## 지금 등록된 폴더·틀\n" + cat + "\n(틀이 없는 폴더: " + ", ".join(n for i, n in dirs.items() if i not in {v.get('dir') for v in _meta().values()}) + ")"})
    content.append({"type": "text", "text": "## 사용자\n" + (text or "(첨부만 보냄 — 이 지면이 어느 틀에 가까운지 말해 줘)")})
    msgs = [{"role": h["role"], "content": h["text"]} for h in history if h.get("role") in ("user", "assistant") and h.get("text")]
    msgs.append({"role": "user", "content": content})
    try:
        import anthropic
        r = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=1200, system=ASK_SYSTEM, messages=msgs)
        answer = "".join(b.text for b in r.content if b.type == "text").strip()
    except Exception as e:
        return jsonify({"error": f"클로드 호출 실패: {e}"}), 500
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return jsonify({"text": answer, "attached": bool(f and f.filename)})


@bp.route("/api/catalog/intake", methods=["POST"])
def intake():
    """① 잰다 ② 판정한다 — 여기서 멈춘다. 등록은 사람이 확인한 뒤 `decide` 로.

    `series` 를 같이 보내면(틀 화면의 디자인 등록) 클로드 키가 없을 때 판정을 건너뛰고
    그 틀로 정해진 것으로 두어 잰 값만으로 초안을 만들 수 있다.
    """
    from routes.catalog import _meta
    series = (request.form.get("series") or "").strip()
    if not have_key() and series not in _meta():
        return jsonify({"error": "클로드 키가 없다. bin/studio 를 띄우기 전에 `export ANTHROPIC_API_KEY=…` (README_로컬실행.md)"}), 400
    f = request.files.get("pdf")
    ext = os.path.splitext(f.filename or "")[1].lower() if f else ""
    if not f or ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        return jsonify({"error": "PDF 나 지면 이미지(png·jpg)를 올려야 한다"}), 400
    hint = (request.form.get("hint") or "").strip()
    jid = uuid.uuid4().hex[:8]
    d = os.path.join(INTAKE, jid)
    os.makedirs(d, exist_ok=True)
    pdf_name = os.path.basename(f.filename)
    pdf_path = os.path.join(d, "ref.pdf")
    if ext == ".pdf":
        f.save(pdf_path)
    else:
        # 지면 이미지 → 한 면짜리 PDF. 실제 치수를 모르니 300dpi 스캔으로 가정한다(판형·여백은 어림, 모양 판정용).
        img_path = os.path.join(d, "ref" + ext)
        f.save(img_path)
        try:
            _image_to_pdf(img_path, pdf_path)
        except Exception as e:
            return jsonify({"error": f"이미지를 못 읽었다: {e}"}), 400
        hint = (hint + "\n(지면 이미지 1장 — 치수는 300dpi 가정한 어림값)").strip()
    try:
        measured = measure(pdf_path)
        pages = render_pages(pdf_path, d)
    except Exception as e:
        return jsonify({"error": f"PDF 를 못 읽었다: {e}"}), 400
    if have_key():
        cards = _template_cards()
        try:
            verdict = judge(measured, pages, cards, hint)
        except Exception as e:
            return jsonify({"error": f"판정 실패: {e}", "measured": measured}), 500
    else:                                   # 키 없음 + 틀 지정 — 판정 없이 사람이 고른 틀
        verdict = {"verdict": "design", "series": series, "confidence": 0, "design_name": os.path.splitext(pdf_name)[0],
                   "reasons": ["클로드 키가 없어 판정을 건너뜀 — 사람이 고른 틀"], "knobs": {}, "skipped": True}
    # 원고 견본(docx·hwpx·xlsx·json…) — 새 틀을 만들 때 파서가 볼 것. `원고/` 에 그대로 둔다.
    manuscripts = []
    for x in request.files.getlist("extra"):
        if x and x.filename:
            os.makedirs(os.path.join(d, "원고"), exist_ok=True)
            x.save(os.path.join(d, "원고", os.path.basename(x.filename)))
            manuscripts.append(os.path.basename(x.filename))
    state = {"id": jid, "pdf": pdf_name, "hint": hint, "measured": measured, "verdict": verdict,
             "pages": [{"label": p["label"], "page": p["page"], "file": os.path.basename(p["file"])} for p in pages],
             "manuscripts": manuscripts, "date": datetime.date.today().isoformat(), "status": "judged"}
    json.dump(state, open(os.path.join(d, "state.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
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
        if st.get("status") in ("new_request", "forging", "forge_paused", "forged", "forge_failed"):
            out.append({"id": jid, "name": st.get("name"), "pdf": st.get("pdf"), "date": st.get("date"), "status": st.get("status"),
                        "note": st.get("note", ""), "trim": st["measured"].get("trim_mm"), "pages": st["measured"].get("pages"),
                        "judged": st["verdict"].get("series"), "confidence": st["verdict"].get("confidence"),
                        "reasons": st["verdict"].get("reasons", [])[:3], "path": f"catalog/_intake/{jid}/ref.pdf",
                        "forge_round": st.get("forge_round")})
    return out


@bp.route("/api/catalog/intake")
def intake_list():
    """결정 대기 + 새 틀 요청 — 새 프로젝트 AI 칸의 '불러오기'."""
    return jsonify({"claude": have_key(), "model": MODEL, "pending": pending(), "new_requests": new_requests()})


@bp.route("/api/catalog/intake/<jid>")
def intake_get(jid):
    if not re.match(r"^[0-9a-f]{8}$", jid):
        abort(404)
    sp = os.path.join(INTAKE, jid, "state.json")
    if not os.path.exists(sp):
        abort(404)
    from routes.catalog import _meta
    state = json.load(open(sp, encoding="utf-8"))
    return jsonify({**state, "templates": [{"series": k, "name": v["name"]} for k, v in _meta().items()]})


@bp.route("/catalog/intake/<jid>/<path:name>")
def intake_img(jid, name):
    """판정에 쓴 면 그림(page_*.png)과 라운드 대조 그림(round_N/*.png)."""
    from flask import send_from_directory
    if not re.match(r"^[0-9a-f]{8}$", jid) or not re.match(r"^(page_[a-z0-9]+|round_\d+/[A-Za-z0-9_\-]+)\.png$", name):
        abort(404)
    return send_from_directory(os.path.join(INTAKE, jid), name)


# ── 새 틀 만들기 (forge) — 이 맥에서 Claude Code 를 headless 로, **라운드**로 돌린다 ───────────────
# 배포 서버(Fly)엔 claude CLI 가 없으니 로컬(bin/studio)에서만. 요청 하나 = 세션 하나(--session-id), 라운드마다 --resume.
# 라운드 끝에 에이전트가 `round.json` 을 쓰고 멈춘다 → 사람이 스레드에서 답하면 다음 라운드. 예전 개발자와 밤새 왕복하던
# 방식을 그대로 옮긴 것 — 실측·조판·대조는 기계가, 판정은 사람이.
_FORGE = {}          # jid → {"proc", "started"}


def _claude_cli():
    return shutil.which("claude")


def _forge_protocol(jid, state, name, did, dir_name):
    """세션 첫 라운드에 주는 규칙 — 라운드 프로토콜 + 이 저장소의 새 계열 절차."""
    d = os.path.join(INTAKE, jid)
    ms = [os.path.join(d, "원고", m) for m in state.get("manuscripts", [])]
    v = state.get("verdict") or {}
    return f"""너는 이 스튜디오의 조판 개발자다. 사람과 **라운드**로 일해서 새 틀(계열) 「{name}」 을 만든다. 카탈로그 폴더 `{did}`({dir_name}).

## 라운드 규칙 (반드시)
- 한 라운드 = 이 세션의 한 번 응답. 라운드 끝에 `{d}/round.json` 을 쓰고 멈춘다. 다음 라운드는 사람의 답으로 이어진다(같은 세션).
- round.json 형식: {{"round": N, "stage": "measure|code|fix|register", "summary": "3~6줄(무엇을 했고 무엇이 맞고 무엇이 미심쩍은지)",
  "ask": "사람에게 확인받을 것 한 줄(없으면 \\"\\")", "compare": [{{"ref": "round_N/ref_p3.png", "out": "round_N/out_p3.png", "note": "이 면에서 다른 점"}}], "done": false}}
  - 그림은 `{d}/round_N/` 에 png 로 — ref = 완성본 면(fitz, dpi 60), out = 내가 조판한 면(같은 자리). 1라운드는 ref 만.
  - compare 는 구성(면 유형)마다 대표 1면씩. 지문만 다른 면은 넣지 않는다.
- 사람이 "등록해" 라고 하면: 카탈로그 등록·커밋·main 머지까지 하고 done: true. 그 전엔 main 에 머지하지 않는다(워크트리에만).
- 사람에게 묻는 건 대조로도 못 가르는 것만. 판단이 필요하면 완성본을 열어 맞춘다(정본 = 완성본).

## 재료
- 완성본 PDF: {os.path.join(d, 'ref.pdf')}  (원본 이름 {state.get('pdf')})
- 원고 견본: {json.dumps(ms, ensure_ascii=False) if ms else '없음 — PDF 글에서 원고 형식을 추정하고 config.manuscript 에 필요한 형식을 적는다. 견본이 오면 다음 라운드에 파서를 붙인다'}
- 요청 메모: {state.get('note') or state.get('hint') or '(없음)'}
- 판정 근거(가장 가까운 기존 틀 `{v.get('series')}`): {' / '.join((v.get('reasons') or [])[:4])}

## 이 저장소의 새 계열 절차
1. 먼저 읽는다: CLAUDE.md, docs/인계_20260914/02_계열별_현황.md §14 와 가장 가까운 계열 절, docs/인계_20260914/07_틀별_디자인·원고_자료.md.
2. 코드는 워크트리에서(EnterWorktree, 이름 new-series-<영문키>). 메인 체크아웃은 편집이 막혀 있다. 라운드가 바뀌어도 같은 워크트리를 쓴다.
3. 실측: PyMuPDF 로 판형·도련·여백·서체(name 테이블)·크기·색·자간. 면 구성(어떤 면이 몇 종인가)을 적는다.
4. 계열 코드: `core/render_vivlio/series/<영문키>/`(`__init__.py`·`data.py`·`render.py`·`verify.py`) + `themes/<영문키>.css` + `series/__init__.py` register. 파서는 구조 판정(라벨 화이트리스트 금지).
5. 등록: `catalog/catalog.json` 에 `"<영문키>": {{"name": "{name}", "desc": …, "root": …, "ready": "auto", "dir": "{did}"}}` (Read 후 Edit, 기존 항목 삭제 금지) + `catalog/<영문키>/designs/d1/` 에 config.json·design.json·참고/reference.pdf·preview_1..5.png.
6. 시험 조판은 `bin/viv` 또는 `python -m core.render_vivlio.book`. 게이트 결과와 쪽수를 summary 에.
제약: 요청 밖 리팩터링 금지, 다른 계열·틀·디자인 파일 불변, 비밀값 금지. 막히면 그 지점에서 round.json 에 적고 멈춘다.
이미 같은 틀의 계열 코드가 있으면(지난 시도 — `catalog/catalog.json` 과 `core/render_vivlio/series/` 확인) 새로 만들지 않고 그것을 이어서 고친다.

## 1라운드 (지금)
실측 + 구성 판독 + 가장 가까운 기존 계열 + 만들 계획만. **코드는 아직 쓰지 않는다.** 구성마다 대표 면을 `round_1/ref_pN.png` 로 뽑아 compare 에 ref 만 넣고, ask 에 확인받을 것을 적는다."""


def _forge_round_prompt(state, message):
    """2라운드 이후 — 사람의 답 + 라운드 규칙 상기."""
    n = int(state.get("forge_round") or 1) + 1
    d = os.path.join(INTAKE, state["id"])
    return f"""[{n}라운드] 사람의 답: {message.strip() or '계속'}

이어서 진행한다. 이번 라운드 끝에 `{d}/round.json` 을 다시 쓴다(round: {n}, 그림은 `{d}/round_{n}/`). 조판했으면 compare 에 완성본(ref)과 조판본(out)을 같은 면끼리 짝지어 넣고 note 에 차이를 적는다. "등록해" 였으면 카탈로그 등록·커밋·main 머지 후 done: true."""


@bp.route("/api/catalog/intake/<jid>/forge", methods=["POST"])
def forge_start(jid):
    """새 틀 요청을 Claude Code(headless)로 라운드 진행. body {dir, name} = 첫 라운드, {message} = 다음 라운드(같은 세션 --resume)."""
    import subprocess
    import threading
    if not re.match(r"^[0-9a-f]{8}$", jid):
        abort(404)
    d = os.path.join(INTAKE, jid)
    sp = os.path.join(d, "state.json")
    if not os.path.exists(sp):
        abort(404)
    cli = _claude_cli()
    if not cli:
        return jsonify({"error": "이 서버에는 claude CLI 가 없다 — 이 맥의 bin/studio 에서만 된다"}), 400
    if jid in _FORGE and _FORGE[jid]["proc"].poll() is None:
        return jsonify({"ok": True, "status": "forging", "already": True})
    other = _forging_other(jid)               # 한 번에 하나만 — 둘이 같은 틀을 만들면 워크트리·머지가 엉킨다
    if other:
        return jsonify({"error": f"이미 새 틀을 만드는 중이다 ({other}). 끝난 뒤 다시."}), 409
    state = json.load(open(sp, encoding="utf-8"))
    body = request.get_json(silent=True) or {}
    from routes.catalog import _dirs
    dirs = {x["id"]: x["name"] for x in _dirs()}
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)              # 안에서 또 세션이라고 오해하지 않게
    # 권한은 좁게: 파일 편집은 자동 승인, 셸은 git·python·bin/*·복사 정도만. 나머지(네트워크·삭제·배포)는 headless 라 거부된다.
    allowed = ("Read Edit Write Glob Grep EnterWorktree ExitWorktree "
               "Bash(git *) Bash(python3 *) Bash(python *) Bash(bin/*) Bash(ls *) Bash(cp *) Bash(mkdir *) Bash(cat *) Bash(head *) Bash(wc *)")
    common = ["--permission-mode", "acceptEdits", "--allowedTools", allowed, "--output-format", "stream-json", "--verbose",
              "--max-budget-usd", os.environ.get("YONE_FORGE_BUDGET_USD", "40")]
    if state.get("forge_session"):            # 다음 라운드 — 같은 세션에 이어 붙인다
        prompt = _forge_round_prompt(state, body.get("message") or "")
        args = [cli, "-p", prompt, "--resume", state["forge_session"]] + common
        rnd = int(state.get("forge_round") or 1) + 1
    else:                                     # 첫 라운드
        did = body.get("dir") if body.get("dir") in dirs else "etc"
        name = (body.get("name") or state.get("name") or os.path.splitext(state.get("pdf", "새 틀"))[0]).strip()
        prompt = _forge_protocol(jid, state, name, did, dirs[did])
        state.update({"name": name, "dir": did, "forge_session": str(uuid.uuid4())})
        args = [cli, "-p", prompt, "--session-id", state["forge_session"]] + common
        rnd = 1
    open(os.path.join(d, f"forge_prompt_{rnd}.md"), "w", encoding="utf-8").write(prompt)
    log = open(os.path.join(d, "forge.log"), "a", encoding="utf-8")
    log.write(f"\n══ {rnd}라운드 {datetime.datetime.now().isoformat(timespec='seconds')} ══\n"); log.flush()
    # stream-json 으로 받아 사람이 읽을 줄(도구 호출·말)로 바꿔 forge.log 에 쓴다.
    proc = subprocess.Popen(args, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, start_new_session=True, text=True)
    _FORGE[jid] = {"proc": proc, "started": datetime.datetime.now().isoformat(timespec="seconds")}
    state.update({"status": "forging", "forge_round": rnd, "forge_started": _FORGE[jid]["started"], "forge_pid": proc.pid})
    state.pop("round", None)
    json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def _pump():
        for line in proc.stdout:
            for out in _forge_lines(line):
                log.write(out + "\n")
            log.flush()
        rc = proc.wait()
        log.close()
        st = json.load(open(sp, encoding="utf-8"))
        st.update(_forge_end(d, rc))
        json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    threading.Thread(target=_pump, daemon=True).start()
    return jsonify({"ok": True, "status": "forging", "id": jid, "round": rnd})


def _forge_end(d, rc):
    """라운드가 끝난 뒤 상태 — round.json 이 있으면 그것(done 이면 forged, 아니면 forge_paused), 없으면 종료 코드로."""
    out = {"forge_rc": rc, "forge_ended": datetime.datetime.now().isoformat(timespec="seconds")}
    rp = os.path.join(d, "round.json")
    r = None
    if os.path.exists(rp):
        try:
            r = json.load(open(rp, encoding="utf-8"))
        except ValueError:
            r = None
    if r:
        out["round"] = r
        out["status"] = "forged" if r.get("done") else "forge_paused"
    else:
        out["status"] = "forged" if rc == 0 else "forge_failed"
    return out


def _forge_lines(line):
    """stream-json 한 줄 → 읽을 수 있는 로그 줄들. 도구 호출은 이름+대상, 말은 앞 300자, 결과는 5줄 요약."""
    try:
        ev = json.loads(line)
    except ValueError:
        return [line.rstrip()] if line.strip() else []
    t = ev.get("type")
    out = []
    if t == "assistant":
        for b in (ev.get("message") or {}).get("content") or []:
            if b.get("type") == "text" and b.get("text", "").strip():
                out.append("💬 " + b["text"].strip()[:300].replace("\n", " "))
            elif b.get("type") == "tool_use":
                i = b.get("input") or {}
                tgt = i.get("command") or i.get("file_path") or i.get("pattern") or i.get("name") or ""
                out.append(f"🔧 {b.get('name')}  {str(tgt)[:120]}")
    elif t == "result":
        out.append(f"■ 끝 ({ev.get('subtype')}) · {ev.get('num_turns')}턴 · ${ev.get('total_cost_usd', 0):.2f}")
        if ev.get("result"):
            out.append(str(ev["result"])[:2000])
    return out


def _forging_other(jid):
    """지금 만드는 중인 다른 요청 id. 프로세스가 살아 있을 때만."""
    for j, f in _FORGE.items():
        if j != jid and f["proc"].poll() is None:
            return j
    return None


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


@bp.route("/api/catalog/intake/<jid>/forge")
def forge_status(jid):
    if not re.match(r"^[0-9a-f]{8}$", jid):
        abort(404)
    d = os.path.join(INTAKE, jid)
    sp = os.path.join(d, "state.json")
    if not os.path.exists(sp):
        abort(404)
    st = json.load(open(sp, encoding="utf-8"))
    # 서버가 도중에 재시작되면 기다리던 스레드가 없어진다 — 프로세스가 죽어 있으면 끝난 것으로 본다(결과는 로그 마지막 줄).
    if st.get("status") == "forging" and jid not in _FORGE and not _alive(st.get("forge_pid")):
        st.update(_forge_end(d, None))
        st["note"] = (st.get("note") or "") + " (서버 재시작으로 종료 코드를 못 받음 — 로그 확인)"
        json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lp = os.path.join(d, "forge.log")
    tail = ""
    if os.path.exists(lp):
        with open(lp, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-6000:]
    return jsonify({"status": st.get("status"), "rc": st.get("forge_rc"), "started": st.get("forge_started"),
                    "ended": st.get("forge_ended"), "log": tail, "name": st.get("name"), "dir": st.get("dir"),
                    "round": st.get("round"), "round_no": st.get("forge_round"), "session": bool(st.get("forge_session"))})


# ── AI 스레드 = Claude Code 세션 ──────────────────────────────────────────────
# 새 프로젝트 AI 칸의 기본 프롬프트. 예전엔 API 한 번(도구 없음)이었는데, 이제 새 틀 만들기와 같은 방식 —
# 이 맥의 Claude Code 세션 하나가 스레드에 붙어 사람의 말대로 보고·판정·등록·조판·수정한다. 턴마다 --resume.
CHAT = os.path.join(INTAKE, "_chat")
_CHAT = {}           # tid → {"proc"}


def _chat_protocol(tid, files):
    d = os.path.join(CHAT, tid)
    return f"""너는 Y.ONE 스튜디오(영어 교재 코드 조판, Vivliostyle)의 조판 개발자이자 도우미다. 이 스레드는 한 사람과의 대화다. 사람이 말하는 대로 한다. 한국어, 짧고 구체적으로.

## 할 수 있는 것 (이 저장소 안에서)
- 카탈로그 보기·설명: 폴더(`catalog/dirs.json`) → 틀(`catalog/catalog.json`, `core/render_vivlio/series/*`) → 디자인(`catalog/<틀>/designs/*`).
- 첨부(완성본 PDF·지면 이미지) 판정 — 어느 틀의 디자인인가 / 새 틀인가: `python3 -c "from routes.intake import measure, render_pages, judge, _template_cards; …"` (판정 결과와 근거를 사람에게).
- 기존 틀에 디자인 등록: `routes.intake.register_draft(series, verdict, measured, pdf_path, pages, pdf_name)` 또는 사람에게 새 프로젝트의 `/ 틀 등록하기` 를 안내.
- 책 만들기·다시 조판: `bin/viv "<책 폴더>" all`, `python -m core.render_vivlio.book`. 디자인 손보기: 디자인 config·overrides.css 손잡이(`bin/viv <책> knobs`).
- 새 틀 만들기: 라운드로 — docs 읽기(CLAUDE.md, docs/인계_20260914/02_계열별_현황.md §14, 07_틀별_디자인·원고_자료.md) → PDF 실측 → 워크트리에서 계열 코드(`core/render_vivlio/series/<키>/` + `themes/<키>.css` + register) → 시험 조판 → 완성본과 대조 → 사람이 "등록해" 하면 `catalog/catalog.json` 등록 + 디자인 d1 + 커밋·main 머지.
- 코드 수정은 워크트리에서(EnterWorktree). 메인 체크아웃은 편집이 막혀 있다. 서버 재시작은 사람이 한다 — 코드가 바뀌었으면 그렇게 말한다.

## 턴 규칙
- 답은 말로 한다. 그림을 보여줄 것(대조·견본·판정에 쓴 면)이 있거나 확인이 필요하면 `{d}/card.json` 을 쓴다:
  {{"summary": "3~6줄", "ask": "확인받을 것 한 줄 또는 \\"\\"", "compare": [{{"ref": "turn_N/ref_p3.png", "out": "turn_N/out_p3.png", "note": "차이"}}], "links": [{{"label": "폴더 열기", "href": "/projects?dir=…"}}]}}
  그림은 `{d}/turn_N/` 에 png 로(fitz dpi 60). 없으면 card.json 을 쓰지 않는다.
- 정본 = 완성본. 디자인은 지어내지 않는다. 사람에게 묻는 건 대조로도 못 가르는 것만. 요청 밖 리팩터링 금지. 비밀값 금지.
- 첨부 파일은 `{d}/files/` 에 있다: {json.dumps(files, ensure_ascii=False) if files else '(없음)'}"""


def _chat_turn_prompt(state, text, new_files):
    n = int(state.get("turn") or 0) + 1
    d = os.path.join(CHAT, state["id"])
    add = f"\n(새 첨부: {json.dumps(new_files, ensure_ascii=False)} — `{d}/files/`)" if new_files else ""
    return f"[{n}턴] 사람: {text.strip() or '(첨부만)'}{add}\n\n그림·확인이 필요하면 `{d}/card.json` (그림은 `{d}/turn_{n}/`). 아니면 말로만."


@bp.route("/api/catalog/chat", methods=["POST"])
def chat_send():
    """스레드에 한 턴 보내기. multipart: tid(없으면 새 스레드), text, files[]. 로컬(claude CLI) 에서만."""
    import subprocess
    import threading
    cli = _claude_cli()
    if not cli:
        return jsonify({"error": "이 서버에는 claude CLI 가 없다 — 이 맥의 bin/studio 에서만 된다"}), 400
    tid = (request.form.get("tid") or "").strip()
    if tid and not re.match(r"^[0-9a-f]{8}$", tid):
        abort(400)
    tid = tid or uuid.uuid4().hex[:8]
    d = os.path.join(CHAT, tid)
    os.makedirs(os.path.join(d, "files"), exist_ok=True)
    sp = os.path.join(d, "state.json")
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {"id": tid, "session": str(uuid.uuid4()), "turn": 0, "files": []}
    if tid in _CHAT and _CHAT[tid]["proc"].poll() is None:
        return jsonify({"error": "아직 앞 턴이 끝나지 않았다"}), 409
    new_files = []
    for x in request.files.getlist("files"):
        if x and x.filename:
            x.save(os.path.join(d, "files", os.path.basename(x.filename)))
            new_files.append(os.path.basename(x.filename))
    state["files"] = state.get("files", []) + new_files
    text = (request.form.get("text") or "").strip()
    turn = int(state.get("turn") or 0) + 1
    if turn == 1:
        prompt = _chat_protocol(tid, state["files"]) + "\n\n[1턴] 사람: " + (text or "(첨부만 — 이게 어느 틀에 가까운지 봐줘)")
        args = [cli, "-p", prompt, "--session-id", state["session"]]
    else:
        prompt = _chat_turn_prompt(state, text, new_files)
        args = [cli, "-p", prompt, "--resume", state["session"]]
    allowed = ("Read Edit Write Glob Grep EnterWorktree ExitWorktree "
               "Bash(git *) Bash(python3 *) Bash(python *) Bash(bin/*) Bash(ls *) Bash(cp *) Bash(mkdir *) Bash(cat *) Bash(head *) Bash(wc *)")
    args += ["--permission-mode", "acceptEdits", "--allowedTools", allowed, "--output-format", "stream-json", "--verbose",
             "--max-budget-usd", os.environ.get("YONE_CHAT_BUDGET_USD", "20")]
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    cp = os.path.join(d, "card.json")
    if os.path.exists(cp):
        os.remove(cp)                          # 이번 턴 카드만 보이게
    log = open(os.path.join(d, "chat.log"), "a", encoding="utf-8")
    log.write(f"\n══ {turn}턴 {datetime.datetime.now().isoformat(timespec='seconds')} ══\n"); log.flush()
    proc = subprocess.Popen(args, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, start_new_session=True, text=True)
    _CHAT[tid] = {"proc": proc}
    state.update({"status": "running", "turn": turn, "pid": proc.pid, "text": "", "last_user": text})
    json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def _pump():
        final = ""
        for line in proc.stdout:
            for out in _forge_lines(line):
                log.write(out + "\n")
            try:
                ev = json.loads(line)
                if ev.get("type") == "result" and ev.get("result"):
                    final = str(ev["result"])
            except ValueError:
                pass
            log.flush()
        rc = proc.wait()
        log.close()
        st = json.load(open(sp, encoding="utf-8"))
        card = None
        if os.path.exists(cp):
            try:
                card = json.load(open(cp, encoding="utf-8"))
            except ValueError:
                card = None
        st.update({"status": "done" if rc == 0 else ("stopped" if st.get("status") == "stopped" else "failed"),
                   "rc": rc, "text": final or st.get("text", ""), "card": card})
        json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    threading.Thread(target=_pump, daemon=True).start()
    return jsonify({"ok": True, "tid": tid, "turn": turn, "status": "running"})


@bp.route("/api/catalog/chat/<tid>")
def chat_status(tid):
    if not re.match(r"^[0-9a-f]{8}$", tid):
        abort(404)
    d = os.path.join(CHAT, tid)
    sp = os.path.join(d, "state.json")
    if not os.path.exists(sp):
        abort(404)
    st = json.load(open(sp, encoding="utf-8"))
    if st.get("status") == "running" and tid not in _CHAT and not _alive(st.get("pid")):
        st.update({"status": "done", "rc": None, "text": st.get("text") or "(서버가 재시작돼 이 턴의 답을 못 받았다 — 로그 참고)"})
        json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lp = os.path.join(d, "chat.log")
    tail = ""
    if os.path.exists(lp):
        with open(lp, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-6000:]
    return jsonify({"status": st.get("status"), "turn": st.get("turn"), "text": st.get("text", ""), "card": st.get("card"), "log": tail, "rc": st.get("rc")})


@bp.route("/api/catalog/chat/<tid>/stop", methods=["POST"])
def chat_stop(tid):
    """턴 중간에 멈추기 — 프로세스 그룹에 SIGTERM. 세션은 남아 다음 턴에 이어진다."""
    import signal
    if not re.match(r"^[0-9a-f]{8}$", tid):
        abort(404)
    sp = os.path.join(CHAT, tid, "state.json")
    if not os.path.exists(sp):
        abort(404)
    st = json.load(open(sp, encoding="utf-8"))
    pid = st.get("pid")
    f = _CHAT.get(tid)
    if f and f["proc"].poll() is None:
        try:
            os.killpg(os.getpgid(f["proc"].pid), signal.SIGTERM)
        except OSError:
            pass
    elif _alive(pid):
        try:
            os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        except OSError:
            pass
    st.update({"status": "stopped", "text": st.get("text") or "(멈춤)"})
    json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return jsonify({"ok": True})


@bp.route("/catalog/chat/<tid>/<path:name>")
def chat_img(tid, name):
    from flask import send_from_directory
    if not re.match(r"^[0-9a-f]{8}$", tid) or not re.match(r"^turn_\d+/[A-Za-z0-9_\-]+\.png$", name):
        abort(404)
    return send_from_directory(os.path.join(CHAT, tid), name)


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
