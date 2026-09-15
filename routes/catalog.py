# -*- coding: utf-8 -*-
"""카탈로그 — **틀 → 디자인 → 원고.**

    틀(series)     계열 코드 하나 = 면 구성(레이아웃). 12개. 코드로만 늘어난다.
    디자인(design) 그 틀의 한 모습 = config(색·치수·서체) + overrides.css + 페이지 틀 이미지.
                   책을 작업대에서 손본 뒤 "디자인으로 등록"하면 늘어난다.
    원고           디자인을 고르고 올리면 새 책.

    /catalog                              틀 12개
    /catalog/<series>                     그 틀의 디자인들 (+ 디자인 등록)
    /catalog/<series>/<design>            디자인 하나: 페이지 틀 이미지 + 원고 넣기
    POST /api/catalog/create              새 책 → data → build → print → verify (배경)
    POST /api/catalog/design/<series>     책 하나를 디자인으로 등록 (config·css 복사, 페이지 틀 뽑기)
    DELETE /api/catalog/design/<series>/<design>

폴더:
    catalog/catalog.json                        틀 목록(이름·설명·루트 폴더)
    catalog/<series>/designs/<id>/design.json   {name, desc, source, date}
    catalog/<series>/designs/<id>/config.json   기준 config (options.expect 는 뺀다)
    catalog/<series>/designs/<id>/overrides.css (있으면)
    catalog/<series>/designs/<id>/master_N.png  페이지 틀(원고 자리를 비운 지면) + masters.json
    catalog/<series>/designs/<id>/preview_N.png 견본 사진(보기용)

원칙은 `engines/vivlio_book/engine.py` 와 같다 — **틀·디자인은 건드리지 않고 언제나 새 폴더를
만든다**, 조판은 subprocess(`python -m core.render_vivlio.book`)로 돈다.
"""
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata as u
import uuid

from flask import (Blueprint, abort, jsonify, render_template, request,
                   send_from_directory)

bp = Blueprint("catalog", __name__)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(REPO, "catalog")
JOBS = {}
_LOCK = threading.Lock()
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")

MASTER_PICKS = (("first", "앞 간지"), ("second", "시작면"), ("left", "본문 왼쪽 면"),
                ("right", "본문 오른쪽 면"), ("last", "뒤 간지"))


def _nfc(s):
    return u.normalize("NFC", s or "")


def _python():
    for p in (os.environ.get("YONE_VIV_PYTHON"),
              "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
              "/opt/homebrew/bin/python3", sys.executable):
        if p and os.path.exists(p):
            return p
    return sys.executable


def _bid(key):
    return hashlib.sha1(_nfc(key).encode("utf-8")).hexdigest()[:10]


def _studio():
    from core.render_vivlio.config import _studio_root
    return _studio_root()


def _books():
    r = subprocess.run([_python(), "-m", "core.render_vivlio.book", "list", "--json"],
                       cwd=REPO, capture_output=True, text=True, timeout=60)
    try:
        out = r.stdout
        return json.loads(out[out.find("["):]) if "[" in out else []
    except ValueError:
        return []


# ── 틀 ──────────────────────────────────────────────────────────
def _meta():
    return json.load(open(os.path.join(CATALOG, "catalog.json"), encoding="utf-8"))


def _ddir(series, design):
    return os.path.join(CATALOG, series, "designs", design)


def _designs(series):
    root = os.path.join(CATALOG, series, "designs")
    if not os.path.isdir(root):
        return []
    out = []
    for d in sorted(os.listdir(root), key=lambda x: (len(x), x)):
        p = os.path.join(root, d, "design.json")
        if not os.path.exists(p) or not os.path.exists(os.path.join(root, d, "config.json")):
            continue
        info = json.load(open(p, encoding="utf-8"))
        info["id"] = d
        info["masters"] = _masters(series, d)
        info["previews"] = _previews(series, d)
        out.append(info)
    return out


def _design_cfg(series, design):
    p = os.path.join(_ddir(series, design), "config.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def _masters(series, design):
    p = os.path.join(_ddir(series, design), "masters.json")
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding="utf-8")).get("pages", [])


def _previews(series, design):
    d = _ddir(series, design)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if re.match(r"preview_\d+\.png$", f))


def _slots(cfg):
    """디자인 config 가 요구하는 원고 칸."""
    m = cfg.get("manuscript") or {}
    files = m.get("files")
    if isinstance(files, dict) and files:
        return {"mode": "files", "slots": [{"key": k, "example": v} for k, v in files.items()]}
    if isinstance(m.get("plan"), str):
        return {"mode": "files", "slots": [{"key": "plan", "example": "render_plan.json"}]}
    named = {k: v for k, v in m.items()
             if isinstance(v, str) and not k.startswith("_") and k not in ("dir", "pattern")
             and re.search(r"\.(docx|hwpx|xlsx|json|pdf)$", v)}
    if named:
        return {"mode": "named", "slots": [{"key": k, "example": v} for k, v in named.items()]}
    hint = ""
    if m.get("pattern"):
        hint = f"파일 이름 규칙: {m['pattern']}  (lessons {m.get('lessons')})"
    elif m.get("_note"):
        hint = m["_note"]
    return {"mode": "folder", "slots": [], "hint": hint}


def _readiness(cfg):
    from core.render_vivlio import stage
    missing = []
    for f in cfg.get("fonts") or []:
        name = f["file"] if isinstance(f, dict) else f
        if stage.find_font(name) is None:
            missing.append(name)
    ext = []
    for m in re.findall(r'"((?:\$\{STUDIO\}|~/)[^"]+)"', json.dumps(cfg, ensure_ascii=False)):
        p = os.path.expanduser(m.replace("${STUDIO}", _studio()))
        if not os.path.exists(p):
            ext.append(m)
    return {"fonts_missing": missing, "paths_missing": ext}


def template_info(series):
    meta = _meta().get(series)
    if not meta:
        return None
    designs = _designs(series)
    cfg = _design_cfg(series, designs[0]["id"]) if designs else None
    r = _readiness(cfg) if cfg else {"fonts_missing": [], "paths_missing": []}
    ready = meta.get("ready", "auto")
    if ready == "auto" and (r["fonts_missing"] or r["paths_missing"] or not designs):
        ready = "blocked"
    return {"series": series, "name": meta["name"], "desc": meta.get("desc", ""),
            "root": meta.get("root", series), "ready": ready, "designs": designs,
            "pipeline": meta.get("pipeline"), "fields": meta.get("fields") or [],
            "slot_hint": meta.get("slot_hint", ""),
            "fonts_missing": r["fonts_missing"], "paths_missing": r["paths_missing"],
            "page": (cfg or {}).get("page")}


def templates():
    return [t for t in (template_info(s) for s in _meta()) if t]


# ── 화면 ────────────────────────────────────────────────────────
@bp.route("/catalog")
def gallery():
    from routes.intake import have_key, new_requests, pending
    return render_template("catalog.html", templates=templates(), active_nav="틀", claude=have_key(),
                           new_requests=new_requests(), pending=pending(),
                           tnames={k: v["name"] for k, v in _meta().items()})


@bp.route("/catalog/<series>")
def series_page(series):
    t = template_info(series)
    if not t:
        abort(404)
    books = [b for b in _books() if b.get("series") == series]
    return render_template("catalog_series.html", t=t, books=books, active_nav="틀")


@bp.route("/catalog/<series>/<design>")
def design_page(series, design):
    t = template_info(series)
    if not t or not _ID.match(design):
        abort(404)
    d = next((x for x in t["designs"] if x["id"] == design), None)
    if not d:
        abort(404)
    cfg = _design_cfg(series, design)
    slots = _slots(cfg)
    if t.get("pipeline"):                       # 통합웹 파서를 거치는 틀은 원고를 폴더째 받는다
        slots = {"mode": "folder", "slots": [], "hint": t.get("slot_hint", "")}
    return render_template("catalog_design.html", t=t, d=d, slots=slots,
                           page=cfg.get("page"), active_nav="틀")


@bp.route("/catalog/master/<series>/<design>/<name>")
def master_img(series, design, name):
    if not _ID.match(design) or not re.match(r"^master_\d+\.png$", name):
        abort(404)
    return send_from_directory(_ddir(series, design), name)


@bp.route("/catalog/preview/<series>/<design>/<name>")
def preview_img(series, design, name):
    if not _ID.match(design) or not re.match(r"^preview_\d+\.png$", name):
        abort(404)
    return send_from_directory(_ddir(series, design), name)


@bp.route("/api/catalog/templates")
def api_templates():
    return jsonify(templates())


# ── 디자인 등록 ─────────────────────────────────────────────────
def _strip_book_specific(cfg):
    """책 한 권에만 속하는 값(기대 수량)을 뺀다 — 디자인은 여러 책이 쓴다."""
    o = cfg.get("options")
    if isinstance(o, dict):
        for k in ("expect", "_expect_note"):
            o.pop(k, None)
    m = cfg.get("manuscript")
    if isinstance(m, dict) and m.get("dir") == "../원고":
        m["dir"] = "원고"
    cfg.setdefault("output", {})["dir"] = "."
    return cfg


def _next_id(series):
    root = os.path.join(CATALOG, series, "designs")
    ns = [int(m.group(1)) for d in (os.listdir(root) if os.path.isdir(root) else [])
          if (m := re.match(r"^d(\d+)$", d))]
    return f"d{(max(ns) + 1) if ns else 1}"


def register_design(series, name, book_dir, key=None, desc=""):
    """책 하나의 모습(config·overrides.css)을 그 틀의 디자인으로 저장하고 페이지 틀을 뽑는다."""
    if series not in _meta():
        raise ValueError("모르는 틀")
    cfg_p = os.path.join(book_dir, "config.json")
    if not os.path.exists(cfg_p):
        raise ValueError("config.json 이 없는 폴더")
    cfg = json.load(open(cfg_p, encoding="utf-8"))
    if cfg.get("series") != series:
        raise ValueError(f"그 책은 {cfg.get('series')} 틀이다 — {series} 에 넣을 수 없다")
    did = _next_id(series)
    d = _ddir(series, did)
    os.makedirs(d, exist_ok=True)
    cfg = _strip_book_specific(cfg)
    cfg["_디자인"] = f"{name} — 기준 책 {key or book_dir} ({datetime.date.today().isoformat()})"
    json.dump(cfg, open(os.path.join(d, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    ov = os.path.join(book_dir, "overrides.css")
    if os.path.exists(ov) and os.path.getsize(ov) > 0:
        shutil.copy2(ov, os.path.join(d, "overrides.css"))
    # 디자인 그림(간지 3D·로고 SVG·구름 png …)은 디자인의 일부다 — 같이 담는다
    for sub in ("assets", "참고"):
        src = os.path.join(book_dir, sub)
        if os.path.isdir(src) and os.listdir(src):
            shutil.copytree(src, os.path.join(d, sub), dirs_exist_ok=True)
    json.dump({"name": name, "desc": desc, "source": key or book_dir,
               "date": datetime.date.today().isoformat()},
              open(os.path.join(d, "design.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        masters(series, did, book_dir, key)
        snap(series, did, book_dir, key)
    except Exception:
        pass
    return did


@bp.route("/api/catalog/design/<series>", methods=["POST"])
def design_add(series):
    name = _nfc(request.form.get("name", "")).strip()
    key = _nfc(request.form.get("book", "")).strip()
    desc = _nfc(request.form.get("desc", "")).strip()
    if not name or not key:
        return jsonify({"error": "디자인 이름과 기준 책을 골라야 한다"}), 400
    known = {_nfc(b["key"]): b for b in _books()}
    if key not in known:
        return jsonify({"error": "모르는 책"}), 400
    book_dir = os.path.join(_studio(), known[key]["key"])
    try:
        did = register_design(series, name, book_dir, key, desc)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"design": did})


@bp.route("/api/catalog/design/<series>/<design>", methods=["DELETE"])
def design_del(series, design):
    if not _ID.match(design):
        abort(404)
    d = _ddir(series, design)
    if os.path.isdir(d):
        shutil.rmtree(d)
    return jsonify({"ok": True})


# ── 페이지 틀 · 견본 사진 ───────────────────────────────────────
def _book_pdf(book_dir):
    """견본·페이지 틀을 찍을 PDF 하나. 조판본(_최종 > 내지) > 인쇄본 > `원본/`(예전 완성본) 순."""
    def pick(folder):
        cands = sorted(glob.glob(os.path.join(folder, "*.pdf")))
        cands = [c for c in cands if "_시안_" not in c and "_불량" not in c and "measure" not in c]
        rgb = [c for c in cands if not c.endswith("_인쇄.pdf")]
        fin = [c for c in rgb if c.endswith("_최종.pdf")]
        return (fin or rgb or cands or [None])[-1]
    return pick(book_dir) or pick(os.path.join(book_dir, "원본"))


def masters(series, design, book_dir, key=None):
    """페이지 틀 — **원고가 들어가는 자리를 비운 지면.** 인디자인의 마스터 페이지에 해당.

    조판된 PDF 에서 면 종류별로 한 면씩 뽑아, 본문 영역의 글 줄을 회색 자리표로 바꾼다.
    머리·바닥의 러닝 요소(PART·섹션 라벨·쪽번호)와 도형·배경(띠·밴드·탭)은 그대로 둔다 —
    그것이 틀이고, 회색 줄이 원고가 흘러드는 자리다.
    """
    import fitz
    pdf = _book_pdf(book_dir)
    if not pdf:
        return None
    d = _ddir(series, design)
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(os.path.join(d, "master_*.png")):
        os.remove(f)
    doc = fitz.open(pdf)
    n = len(doc)
    mid = max(3, (n // 2) // 2 * 2 + 1)      # 홀수 index = 짝수 쪽 = 왼쪽 면
    idx = {"first": 0, "second": 1 if n > 1 else 0, "left": mid if n > mid else 0,
           "right": mid + 1 if n > mid + 1 else 0, "last": n - 1}
    pages = []
    for k, (key_, label) in enumerate(MASTER_PICKS, 1):
        i = idx[key_]
        one = fitz.open()
        one.insert_pdf(doc, from_page=i, to_page=i)
        pg = one[0]
        H = pg.rect.height
        for b in pg.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                x0, y0, x1, y1 = ln["bbox"]
                if y0 < H * 0.12 or y1 > H * 0.94:
                    continue
                if not "".join(sp["text"] for sp in ln["spans"]).strip():
                    continue
                pg.add_redact_annot(fitz.Rect(x0, y0 + (y1 - y0) * 0.18, x1, y1 - (y1 - y0) * 0.18),
                                    fill=(0.80, 0.82, 0.86))
        try:
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=0)
        except TypeError:
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        pg.get_pixmap(dpi=80).save(os.path.join(d, f"master_{k}.png"))
        pages.append({"file": f"master_{k}.png", "label": label, "page": i + 1})
        one.close()
    json.dump({"source": key or book_dir, "pdf": os.path.basename(pdf), "pages": pages,
               "date": datetime.date.today().isoformat()},
              open(os.path.join(d, "masters.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return pdf


def _next_preview(d):
    ns = [int(m.group(1)) for f in os.listdir(d) if (m := re.match(r"preview_(\d+)\.png$", f))]
    return (max(ns) + 1) if ns else 1


def snap(series, design, book_dir, key=None, replace=True):
    """견본 사진 3장(첫 본문·가운데 펼침면·첫 면). 보기용."""
    import fitz
    from PIL import Image
    pdf = _book_pdf(book_dir)
    if not pdf:
        return None
    d = _ddir(series, design)
    os.makedirs(d, exist_ok=True)
    if replace:
        for f in glob.glob(os.path.join(d, "preview_*.png")):
            os.remove(f)
    doc = fitz.open(pdf)
    n = len(doc)
    pix = lambda i: doc[i].get_pixmap(dpi=80)
    img = lambda px: Image.frombytes("RGB", (px.width, px.height), px.samples)
    img(pix(1 if n > 1 else 0)).save(os.path.join(d, f"preview_{_next_preview(d)}.png"))
    mid = max(3, (n // 2) // 2 * 2 + 1)
    if n > mid + 1:
        a, b = img(pix(mid)), img(pix(mid + 1))
        out = Image.new("RGB", (a.width + b.width + 4, max(a.height, b.height)), "white")
        out.paste(a, (0, 0)); out.paste(b, (a.width + 4, 0))
        out.save(os.path.join(d, f"preview_{_next_preview(d)}.png"))
    img(pix(0)).save(os.path.join(d, f"preview_{_next_preview(d)}.png"))
    json.dump({"source": key or book_dir, "pdf": os.path.basename(pdf), "pages": n,
               "date": datetime.date.today().isoformat()},
              open(os.path.join(d, "preview.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return pdf


@bp.route("/api/catalog/preview/<series>/<design>", methods=["POST"])
def preview_add(series, design):
    """사용자가 넣는 보기용 사진. PNG·JPG 는 그대로, PDF 는 첫 면."""
    if not _ID.match(design) or not os.path.isdir(_ddir(series, design)):
        abort(404)
    d = _ddir(series, design)
    n = 0
    for f in request.files.getlist("img"):
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        dst = os.path.join(d, f"preview_{_next_preview(d)}.png")
        data = f.read()
        try:
            if ext == ".pdf":
                import fitz
                fitz.open(stream=data, filetype="pdf")[0].get_pixmap(dpi=80).save(dst)
            else:
                import io
                from PIL import Image
                im = Image.open(io.BytesIO(data)).convert("RGB")
                im.thumbnail((1400, 1400))
                im.save(dst, "PNG")
        except Exception as e:
            return jsonify({"error": f"이미지를 못 읽었다: {f.filename} ({e})"}), 400
        n += 1
    return jsonify({"added": n})


@bp.route("/api/catalog/preview/<series>/<design>/<name>", methods=["DELETE"])
def preview_del(series, design, name):
    if not _ID.match(design) or not re.match(r"^preview_\d+\.png$", name):
        abort(404)
    p = os.path.join(_ddir(series, design), name)
    if os.path.exists(p):
        os.remove(p)
    return jsonify({"ok": True})


# ── 새 책 만들기 ────────────────────────────────────────────────
MS_EXT = (".docx", ".hwp", ".hwpx", ".xlsx", ".pdf", ".json", ".idml")


def _gather_folder(path):
    """이 맥의 폴더 → 원고 파일 목록(하위 폴더 포함). 드라이브가 동기화돼 있으면 업로드 없이 바로 읽는다."""
    path = os.path.expanduser(_nfc(path).strip())
    if not os.path.isdir(path):
        raise ValueError(f"폴더가 없다: {path}")
    out = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d != "build"]
        for f in sorted(files):
            if f.startswith(("~$", ".")) or not f.lower().endswith(MS_EXT):
                continue
            out.append(os.path.join(root, f))
    if not out:
        raise ValueError("폴더에 원고 파일(docx·hwp·hwpx·xlsx·pdf)이 없다")
    return out


def _incoming(files, form, dest_root):
    """원고를 모은다 — 올린 파일(폴더째면 상대경로 유지) 또는 `folder_path`. 저장된 절대경로 목록."""
    paths = []
    fp = (form.get("folder_path") or "").strip()
    if fp:
        for src in _gather_folder(fp):
            rel = os.path.relpath(src, os.path.expanduser(_nfc(fp).strip()))
            dst = os.path.join(dest_root, _nfc(rel))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            paths.append(dst)
        return paths
    for f in files.getlist("slot_folder"):
        if not f or not f.filename:
            continue
        rel = _nfc(f.filename).replace("\\", "/").lstrip("/")
        if ".." in rel or not rel.lower().endswith(MS_EXT):
            continue
        dst = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        f.save(dst)
        paths.append(dst)
    return paths


def _match_slots(slots, paths):
    """폴더로 받았는데 칸이 이름별로 나뉜 틀 — 예전 파일 이름과 가장 닮은 파일을 칸에 넣는다."""
    import difflib
    used, out = set(), {}
    for sl in slots:
        ex = _nfc(sl["example"]).lower()
        best, score = None, 0.0
        for p_ in paths:
            if p_ in used:
                continue
            nm = _nfc(os.path.basename(p_)).lower()
            if os.path.splitext(nm)[1] != os.path.splitext(ex)[1]:
                continue
            r = difflib.SequenceMatcher(None, nm, ex).ratio()
            if r > score:
                best, score = p_, r
        if best and score >= 0.35:
            out[sl["key"]] = best
            used.add(best)
    return out


def _safe_name(s):
    s = _nfc(s).strip()
    if not s or any(c in s for c in "/\\") or ".." in s:
        return None
    return s


@bp.route("/api/catalog/create", methods=["POST"])
def create():
    from core.render_vivlio import knobs as kn

    series = request.form.get("series", "")
    design = request.form.get("design", "")
    meta = _meta().get(series)
    if not meta or not _ID.match(design):
        return jsonify({"error": "모르는 틀·디자인"}), 400
    cfg_p = os.path.join(_ddir(series, design), "config.json")
    if not os.path.exists(cfg_p):
        return jsonify({"error": "디자인 설정이 없다"}), 400
    if meta.get("ready") == "manual":
        return jsonify({"error": "이 틀은 여기서 못 만든다 (README_로컬실행.md)"}), 400

    name = _safe_name(request.form.get("name", ""))
    period = _safe_name(request.form.get("period", ""))
    school = _nfc(request.form.get("school", "")).strip()
    title = _nfc(request.form.get("title", "")).strip() or name
    if not name or not period:
        return jsonify({"error": "교재명과 학기는 꼭 적어야 한다 (예: 이의1보카 / 27-1-중간)"}), 400

    rel = os.path.join("조판", "교재", meta.get("root", series), name, period)
    out_dir = os.path.join(_studio(), rel)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        return jsonify({"error": f"이미 있는 폴더다: {rel} — 덮어쓰지 않는다. 학기 이름을 바꿀 것"}), 400
    os.makedirs(os.path.join(out_dir, "원고"), exist_ok=True)

    cfg = json.load(open(cfg_p, encoding="utf-8"))
    raw = open(cfg_p, encoding="utf-8").read()
    slots = _slots(cfg)
    changes, n = {}, 0
    files = request.files
    pipeline = meta.get("pipeline")
    if pipeline == "workbook_v2":
        # 통합웹 워크북 파서: 원고 여러 개 → content.json → render_plan.json (wb-flows-v1)
        up = os.path.join(out_dir, "원고", "업로드")
        os.makedirs(up, exist_ok=True)
        try:
            paths = _incoming(files, request.form, up)
        except ValueError as e:
            shutil.rmtree(out_dir, ignore_errors=True)
            return jsonify({"error": str(e)}), 400
        n = len(paths)
        if not n:
            shutil.rmtree(out_dir, ignore_errors=True)
            return jsonify({"error": "원고를 하나도 올리지 않았다"}), 400
        job = os.path.join(out_dir, "원고", "_job")
        os.makedirs(job, exist_ok=True)
        for fld in meta.get("fields") or []:
            v = _nfc(request.form.get("f_" + fld["key"], "")).strip() or fld.get("default", "")
            with open(os.path.join(job, fld["key"] + ".txt"), "w", encoding="utf-8") as fh:
                fh.write(v)
        if school:
            with open(os.path.join(job, "school.txt"), "w", encoding="utf-8") as fh:
                fh.write(school)
        try:
            plan = _workbook_plan(paths, job)
        except Exception as e:
            shutil.rmtree(out_dir, ignore_errors=True)
            return jsonify({"error": f"원고를 못 읽었다: {e}"}), 400
        shutil.copy2(plan, os.path.join(out_dir, "원고", "render_plan.json"))
        changes["manuscript.plan"] = "${BOOK}/원고/render_plan.json"
    elif slots["mode"] in ("files", "named"):
        prefix = "manuscript.files." if slots["mode"] == "files" else "manuscript."
        # 폴더째 왔으면(경로 입력·폴더 드롭) 예전 파일 이름과 닮은 것을 칸에 배정한다
        bulk = []
        if (request.form.get("folder_path") or "").strip() or files.getlist("slot_folder"):
            tmp = os.path.join(out_dir, "원고", "_받은것")
            os.makedirs(tmp, exist_ok=True)
            try:
                bulk = _incoming(files, request.form, tmp)
            except ValueError as e:
                shutil.rmtree(out_dir, ignore_errors=True)
                return jsonify({"error": str(e)}), 400
        matched = _match_slots(slots["slots"], bulk) if bulk else {}
        for s in slots["slots"]:
            f = files.get("slot_" + s["key"])
            fname = None
            if f and f.filename:
                fname = _nfc(os.path.basename(f.filename))
                f.save(os.path.join(out_dir, "원고", fname))
            elif s["key"] in matched:
                fname = _nfc(os.path.basename(matched[s["key"]]))
                shutil.move(matched[s["key"]], os.path.join(out_dir, "원고", fname))
            if not fname:
                continue
            n += 1
            if s["key"] == "plan":
                changes["manuscript.plan"] = "${BOOK}/원고/" + fname
            else:
                changes[prefix + s["key"]] = fname
        if bulk:
            shutil.rmtree(os.path.join(out_dir, "원고", "_받은것"), ignore_errors=True)
    else:
        try:
            paths = _incoming(files, request.form, os.path.join(out_dir, "원고"))
        except ValueError as e:
            shutil.rmtree(out_dir, ignore_errors=True)
            return jsonify({"error": str(e)}), 400
        n = len(paths)
    if not n:
        return jsonify({"error": "원고를 하나도 올리지 않았다"}), 400

    changes["book.title"] = title
    changes["book.period"] = period
    if school:
        changes["book.school"] = school
    stem = f"{school}_{name}_내지" if school else f"{name}_내지"
    changes["output.stem"] = stem
    changes["output.dir"] = "."
    try:
        raw = kn.patch_text(raw, changes)
    except Exception:
        raw = json.dumps(kn.apply(json.loads(raw), changes), ensure_ascii=False, indent=2) + "\n"
    # 어느 틀·디자인에서 왔는지 남긴다 — 책 목록이 보여 주고, 다시 조판할 때 참고
    try:
        dj = json.load(open(os.path.join(_ddir(series, design), "design.json"), encoding="utf-8"))
        cfg_out = json.loads(raw)
        cfg_out["_카탈로그"] = {"series": series, "design": design, "design_name": dj.get("name", design),
                               "made": datetime.date.today().isoformat()}
        raw = json.dumps(cfg_out, ensure_ascii=False, indent=2) + "\n"
    except Exception:
        pass
    with open(os.path.join(out_dir, "config.json"), "w", encoding="utf-8") as fh:
        fh.write(raw)
    ov = os.path.join(_ddir(series, design), "overrides.css")
    if os.path.exists(ov):
        shutil.copy2(ov, os.path.join(out_dir, "overrides.css"))
    for sub in ("assets", "참고"):
        src = os.path.join(_ddir(series, design), sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(out_dir, sub), dirs_exist_ok=True)

    job = {"id": uuid.uuid4().hex[:8], "status": "running", "log": [], "book_dir": out_dir,
           "key": rel, "bid": _bid(rel), "stem": stem, "series": series, "design": design,
           "started": time.time(), "pdfs": []}
    with _LOCK:
        JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return jsonify({"job": job["id"], "key": rel, "bid": job["bid"]})


def _workbook_plan(paths, job_dir):
    """통합웹 워크북 v2 엔진으로 원고 → render_plan.json.

    `prepare_jsx` 는 플랜을 쓴 **다음** 인디자인 원본(.indd)을 찾다가 멈춘다(이 기기엔 없다).
    플랜은 그 전에 이미 저장되므로, 그 예외는 삼키고 플랜 파일만 확인한다.
    """
    from engines.workbook_v2.engine import WorkbookV2Engine
    eng = WorkbookV2Engine()
    msgs = []
    log = lambda m: msgs.append(str(m))
    # 폴더 구조(Step3/ 하위 폴더)를 갖춰 왔으면 **폴더째** 넘긴다 — 파서가 그 구조를 믿는다.
    # 파일만 흩어 왔으면 목록으로 넘겨 엔진이 이름으로 스텝을 나눈다.
    #   ⚠ 폴더가 있는데도 목록으로 넘기면 'Step3/…문제지.docx' 가 이름에 Step3 표시가 없어
    #     밖으로 빠지고, 짝인 PDF 만 Step3 에 남아 "짝 없는 PDF" 오류로 멈춘다(실측).
    root = os.path.commonpath(paths) if len(paths) > 1 else os.path.dirname(paths[0])
    while root and not os.path.isdir(root):
        root = os.path.dirname(root)
    has_step3 = any(re.match(r"(?i)^step\s*3$", d) for d in os.listdir(root)) if root else False
    if has_step3:
        log(f"[원고] 폴더 구조 그대로 읽음: {os.path.basename(root)}/ (Step3/ 포함)")
        cj = eng.parse({"manuscripts": root}, job_dir, log)
    else:
        cj = eng.parse({"manuscripts": paths}, job_dir, log)
    try:
        eng.prepare_jsx(cj, job_dir, log)
    except Exception:
        pass
    plan = os.path.join(job_dir, "render_plan.json")
    if not os.path.exists(plan):
        raise RuntimeError("플랜을 만들지 못했다: " + " / ".join(msgs[-3:]))
    with open(os.path.join(job_dir, "파서_로그.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(msgs) + "\n")
    return plan


def _run(job):
    job["log"].append(f"[새 책] {job['key']}")
    plog = os.path.join(job["book_dir"], "원고", "_job", "파서_로그.txt")
    if os.path.exists(plog):
        warn = [ln for ln in open(plog, encoding="utf-8").read().splitlines() if "⚠" in ln or "미소비" in ln]
        job["log"] += ["[파서] " + w[:200] for w in warn[:12]]
    cmd = [_python(), "-u", "-m", "core.render_vivlio.book", job["book_dir"], "all"]
    try:
        p = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
        for line in p.stdout:
            line = line.rstrip()
            if line and "DeprecationWarning" not in line and "fitz" not in line:
                job["log"].append(line)
        p.wait(timeout=1800)
        job["rc"] = p.returncode
    except Exception as e:
        job["log"].append(f"[오류] {e}")
        job["rc"] = -1
    d = job["book_dir"]
    job["pdfs"] = sorted(f for f in os.listdir(d) if f.endswith(".pdf"))
    if job["pdfs"]:
        job["status"] = "done" if job["rc"] == 0 else "done_warn"
        try:
            if not _masters(job["series"], job["design"]):
                masters(job["series"], job["design"], d, job["key"])
                job["snapped"] = True
            if not _previews(job["series"], job["design"]):
                snap(job["series"], job["design"], d, job["key"])
        except Exception as e:
            job["log"].append(f"[페이지 틀] 못 뽑음: {e}")
    else:
        job["status"] = "failed"
    with open(os.path.join(d, "조판_로그.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(job["log"]) + "\n")


@bp.route("/api/catalog/job/<jid>")
def job_status(jid):
    j = JOBS.get(jid)
    if not j:
        abort(404)
    since = int(request.args.get("since", 0))
    return jsonify({"status": j["status"], "log": j["log"][since:], "n": len(j["log"]),
                    "snapped": j.get("snapped", False), "pdfs": j.get("pdfs", []),
                    "bid": j["bid"], "key": j["key"], "elapsed": round(time.time() - j["started"])})


@bp.route("/catalog/out/<bid>/<path:name>")
def out_pdf(bid, name):
    if not name.endswith(".pdf") or "/" in name:
        abort(404)
    for j in JOBS.values():
        if j["bid"] == bid:
            return send_from_directory(j["book_dir"], name)
    from routes.book_studio import _book_dir
    d, _ = _book_dir(bid)
    if not d:
        abort(404)
    return send_from_directory(d, name)
