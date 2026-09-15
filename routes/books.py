# -*- coding: utf-8 -*-
"""책 목록 — **조판된 책을 모아 보고, PDF 를 열고, 다시 조판하거나 지운다.**

책의 실체는 스튜디오 트리(`조판/교재/…/<책>/`)다. 카탈로그에서 만든 책도, 손으로 넣은 책도
`config.json` 만 있으면 여기 뜬다(`bin/viv --list` 와 같은 목록). 산출 PDF·쪽수·날짜·원고 수·
어느 틀·디자인으로 만들었는지(`config._카탈로그`)를 같이 보여 준다.

    /books                 목록 (틀별)
    /api/books             JSON
    POST /api/books/rebuild {key}   data → build → print → verify 다시 (카탈로그 잡과 같은 실행기)
    DELETE /api/books      {key}    책 폴더 삭제 — 사용자가 확인한 뒤에만
"""
import datetime
import json
import os
import shutil
import threading
import time
import unicodedata as u
import uuid

from flask import Blueprint, abort, jsonify, render_template, request

bp = Blueprint("books", __name__)


def _nfc(s):
    return u.normalize("NFC", s or "")


def _studio():
    from core.render_vivlio.config import _studio_root
    return _studio_root()


def _pages(p):
    try:
        import fitz
        return len(fitz.open(p))
    except Exception:
        return None


def books():
    from routes.catalog import _books, _bid, _meta
    names = {k: v["name"] for k, v in _meta().items()}
    out = []
    root = _studio()
    for b in _books():
        d = os.path.join(root, b["key"])
        if not os.path.isdir(d):
            continue
        cfg = {}
        try:
            cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
        except Exception:
            pass
        pdfs = []
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".pdf") or "_시안_" in f or "measure" in f:
                continue
            p = os.path.join(d, f)
            kind = "인쇄" if f.endswith("_인쇄.pdf") else ("불량" if "_불량" in f else ("최종" if f.endswith("_최종.pdf") else "조판"))
            pdfs.append({"name": _nfc(f), "kind": kind, "pages": _pages(p), "size_mb": round(os.path.getsize(p) / 1048576, 1),
                         "date": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")})
        ms_dir = os.path.join(d, (cfg.get("manuscript") or {}).get("dir", "원고") if isinstance(cfg.get("manuscript"), dict) else "원고")
        n_ms = 0
        if os.path.isdir(ms_dir):
            for _r, _ds, fs in os.walk(ms_dir):
                n_ms += sum(1 for f in fs if not f.startswith((".", "~$")))
        cat = cfg.get("_카탈로그") or {}
        latest = max((p["date"] for p in pdfs), default="")
        out.append({"key": _nfc(b["key"]), "bid": _bid(b["key"]), "series": b.get("series"),
                    "series_name": names.get(b.get("series"), b.get("series")), "title": _nfc(b.get("title") or ""),
                    "book": cfg.get("book") or {}, "pdfs": pdfs, "manuscripts": n_ms, "latest": latest,
                    "design": cat.get("design_name") or cfg.get("_디자인") or "", "made": cat.get("made", ""),
                    "has_build": os.path.isdir(os.path.join(d, "build"))})
    out.sort(key=lambda x: (x["series_name"] or "", x["latest"]), reverse=False)
    return out


@bp.route("/books")
def page():
    from routes.catalog import _meta
    order = list(_meta().keys())
    bs = books()
    groups = {}
    for b in bs:
        groups.setdefault(b["series"], []).append(b)
    ordered = [(s, _meta()[s]["name"], groups[s]) for s in order if s in groups]
    return render_template("books.html", groups=ordered, total=len(bs), active_nav="책")


@bp.route("/api/books")
def api_books():
    return jsonify(books())


@bp.route("/api/books/pdf")
def latest_pdf():
    """그 책의 실물 PDF — 조판본(_최종 > 내지). 인쇄본·견본·시안은 뺀다."""
    from routes.catalog import _books, _bid
    key = _nfc(request.args.get("b", ""))
    known = {_nfc(b["key"]): b for b in _books()}
    hit = known.get(key) or next((b for b in known.values() if _bid(b["key"]) == key), None)
    if not hit:
        return jsonify({"error": "모르는 책"}), 404
    d = os.path.join(_studio(), hit["key"])
    cands = [f for f in os.listdir(d) if f.lower().endswith(".pdf") and not f.endswith("_인쇄.pdf")
             and "_시안_" not in f and "_견본" not in f and "_불량" not in f and "measure" not in f and "_thumbs" not in f]
    if not cands:
        return jsonify({"pdf": None})
    fin = [f for f in cands if f.endswith("_최종.pdf")]
    pick = max(fin or cands, key=lambda f: os.path.getmtime(os.path.join(d, f)))
    return jsonify({"pdf": _nfc(pick), "pages": _pages(os.path.join(d, pick)), "bid": _bid(hit["key"]),
                    "url": f"/catalog/out/{_bid(hit['key'])}/{pick}",
                    "date": datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(d, pick))).strftime("%m-%d %H:%M")})


@bp.route("/api/books/rebuild", methods=["POST"])
def rebuild():
    from routes.catalog import JOBS, _LOCK, _run, _bid, _books
    key = _nfc((request.get_json(silent=True) or {}).get("key", ""))
    known = {_nfc(b["key"]): b for b in _books()}
    if key not in known:
        return jsonify({"error": "모르는 책"}), 400
    d = os.path.join(_studio(), known[key]["key"])
    cfg = json.load(open(os.path.join(d, "config.json"), encoding="utf-8"))
    cat = cfg.get("_카탈로그") or {}
    job = {"id": uuid.uuid4().hex[:8], "status": "running", "log": [], "book_dir": d, "key": key, "bid": _bid(key),
           "stem": (cfg.get("output") or {}).get("stem", ""), "series": cfg.get("series"), "design": cat.get("design", "d1"),
           "started": time.time(), "pdfs": []}
    with _LOCK:
        JOBS[job["id"]] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return jsonify({"job": job["id"], "key": key, "bid": job["bid"]})


@bp.route("/api/books", methods=["DELETE"])
def delete():
    from routes.catalog import _books
    key = _nfc((request.get_json(silent=True) or {}).get("key", ""))
    known = {_nfc(b["key"]): b for b in _books()}
    if key not in known:
        return jsonify({"error": "모르는 책"}), 400
    d = os.path.realpath(os.path.join(_studio(), known[key]["key"]))
    root = os.path.realpath(_studio())
    if not d.startswith(root + os.sep) or not os.path.exists(os.path.join(d, "config.json")):
        abort(400)
    shutil.rmtree(d)
    # 빈 부모 폴더는 정리 (교재명 폴더까지)
    parent = os.path.dirname(d)
    while parent.startswith(root + os.sep) and os.path.isdir(parent) and not os.listdir(parent):
        os.rmdir(parent)
        parent = os.path.dirname(parent)
    return jsonify({"ok": True})
