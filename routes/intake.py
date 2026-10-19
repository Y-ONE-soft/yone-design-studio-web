# -*- coding: utf-8 -*-
"""PDF 등록 — 완성본 PDF 를 관리 라인업(틀)의 디자인 카드로 올린다(편집기 재현 1단계 「원본 올리기」).

    bin/register-design <PDF> <틀> [이름]  ·  관리 ＋ → 「PDF 등록」 (POST /api/catalog/register-pdf, 잡으로)

PDF 를 재고(판형 · 도련 · 서체 · 색, mm) 디자인 폴더에 원본(참고/reference.pdf) · 견본 그림 · design.json(made: pdf)을 두고
면 판정(routes/catalog.design_layouts)으로 구성을 계산해 둔다.
(클로드 PDF 판정 · 새 틀 만들기 · 예전 틀 디자인을 바탕으로 한 초안 · 로고 조각 자르기는 2026-10-19 예전 조판 엔진과 함께 지웠다.)
"""
import collections
import datetime
import json
import os
import shutil
import uuid

from flask import Blueprint, abort, jsonify, request

bp = Blueprint("intake", __name__)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.environ.get("YONE_CATALOG_DIR") or os.path.join(REPO, "catalog")   # 컨테이너: 볼륨
INTAKE = os.path.join(CATALOG, "_intake")
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


def register_pdf(pdf, series, name=None, log=print):
    """완성본 PDF 를 그 틀의 디자인으로 등록 — bin/register-design · 관리 ＋ 「PDF 등록」이 같이 쓴다.
    → (디자인 id, 잰 값, 구성). 반복되는 면은 구성 하나로 묶인다(design_layouts)."""
    import tempfile
    import unicodedata
    from routes.catalog import _ddir, _new_id, design_layouts
    pdf_name = unicodedata.normalize("NFC", os.path.basename(pdf)).strip()
    name = unicodedata.normalize("NFC", name or os.path.splitext(pdf_name)[0]).strip()
    m = measure(pdf)
    log(f"PDF {m['pages']}면 · {m['trim_mm'][0]:g}×{m['trim_mm'][1]:g}mm")
    did = _new_id(series)
    d = _ddir(series, did)
    os.makedirs(os.path.join(d, "참고"), exist_ok=True)
    shutil.copy2(pdf, os.path.join(d, "참고", "reference.pdf"))
    with tempfile.TemporaryDirectory() as tmp:
        for k, p in enumerate(render_pages(pdf, tmp, dpi=80), 1):          # 올린 PDF 의 면 = 견본 사진
            shutil.copy2(p["file"], os.path.join(d, f"preview_{k}.png"))
    today = datetime.date.today().isoformat()
    tw, th = m["trim_mm"]
    json.dump({"series": series, "book": {"title": name}, "page": {"width": tw, "height": th, "bleed": m["bleed_mm"]},
               "_디자인": f"{pdf_name} ({today})"},
              open(os.path.join(d, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # 틀별 구성 규칙(SECTION_RULES)은 그 틀의 원래 책용이라 새 책에는 안 쓴다 — 면에 인쇄된 라벨·생김새로만 구성
    json.dump({"name": name, "desc": f"{pdf_name} · {m['pages']}페이지", "source": f"PDF: {pdf_name}", "date": today,
               "draft": False, "layout_rules": False, "made": "pdf", "intake": {"measured": m}},
              open(os.path.join(d, "design.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("구성 묶는 중…")
    r = design_layouts(series, did)
    log(f"등록 끝 — 구성 {len(r['layouts'])}개")
    return did, m, r


@bp.route("/api/catalog/register-pdf", methods=["POST"])
def api_register_pdf():
    """관리 ＋ 「PDF 등록」 — 폼 pdf(파일) · series(틀) · name(이름, 없으면 파일 이름). 잡으로 돈다 → {job}. 상태는 /api/units/job/<id>"""
    from core import jobs
    from routes.catalog import _meta
    f = request.files.get("pdf")
    series = (request.form.get("series") or "").strip()
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF 파일을 고르세요"}), 400
    if series not in _meta():
        return jsonify({"error": f"틀 {series} 없음"}), 404
    tmp = os.path.join(INTAKE, "_upload_" + uuid.uuid4().hex[:8])
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, os.path.basename(f.filename.replace("\\", "/")) or "upload.pdf")
    f.save(path)
    name = (request.form.get("name") or "").strip() or None

    def go(job, log):
        try:
            did, m, r = register_pdf(path, series, name, log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {"series": series, "design": did, "pages": m["pages"], "layouts": len(r["layouts"]), "url": f"/design/{series}/{did}"}
    job = jobs.start("pdf-register", go, meta={"series": series, "pdf": f.filename})
    return jsonify({"ok": True, "job": job.id})


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
