# -*- coding: utf-8 -*-
"""책 목록 — **조판된 책을 모아 보고, PDF 를 열고, 다시 조판하거나 지운다.**

책의 실체는 스튜디오 트리(`조판/교재/…/<책>/`)다. 카탈로그에서 만든 책도, 손으로 넣은 책도
`config.json` 만 있으면 여기 뜬다(`bin/viv --list` 와 같은 목록). 산출 PDF·쪽수·날짜·원고 수·
어느 틀·디자인으로 만들었는지(`config._카탈로그`)를 같이 보여 준다.

    /books                 목록 (틀별, 표)
    /projects              프로젝트 — Canva 식 "모든 프로젝트" (최근 카드 · 폴더 = 틀 · 전체)
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


def _ago(stamp):
    """'2026-09-15 15:58' → '몇 분 전 편집함' 식. 없으면 '아직 조판 안 함'."""
    if not stamp:
        return "아직 조판 안 함"
    try:
        t = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return stamp
    m = int((datetime.datetime.now() - t).total_seconds() // 60)
    if m < 1:
        return "방금 편집함"
    if m < 60:
        return f"{m}분 전 편집함"
    if m < 24 * 60:
        return f"{m // 60}시간 전 편집함"
    if m < 30 * 24 * 60:
        return f"{m // (24 * 60)}일 전 편집함"
    return t.strftime("%Y-%m-%d 편집함")


def projects():
    """`books()` + 디렉토리(카탈로그 dirs.json)·편집 시각 문구. 최근 것이 앞."""
    from routes.catalog import _dir_of, _dirs, _meta
    meta, dirs = _meta(), {d["id"]: d for d in _dirs()}
    out = []
    for b in books():
        did = _dir_of(meta.get(b["series"]) or {}, set(dirs))
        d = dirs.get(did) or {}
        out.append({**b, "dir": did, "dir_name": d.get("name", did), "dir_color": d.get("color", "#8b91a5"),
                    "ago": _ago(b["latest"]), "day": (b["latest"] or "")[:10]})
    out.sort(key=lambda x: x["latest"], reverse=True)
    return out


@bp.route("/projects")
def page_projects():
    """`?dir=<디렉토리>` 면 그 폴더 안의 책만, `?q=` 면 제목·틀·디자인에 그 말이 든 책만."""
    from routes.catalog import DEFAULT_DIR, _dir_of, _dirs, _meta
    bs = projects()
    counts, tcounts = {}, {}
    for b in bs:
        counts[b["dir"]] = counts.get(b["dir"], 0) + 1
    ids = {d["id"] for d in _dirs()}
    for m in _meta().values():                       # 틀 수 — 지울 때 "안의 틀 n개는 기타로" 안내용
        tcounts[_dir_of(m, ids)] = tcounts.get(_dir_of(m, ids), 0) + 1
    # 폴더 = 카탈로그 디렉토리(dirs.json 순서). 기타는 책·틀이 있을 때만.
    folders = [{**d, "n": counts.get(d["id"], 0), "t": tcounts.get(d["id"], 0)}
               for d in _dirs() if d["id"] != DEFAULT_DIR or counts.get(d["id"]) or tcounts.get(d["id"])]
    did = _nfc(request.args.get("dir", "")).strip()
    q = _nfc(request.args.get("q", "")).strip().lower()
    folder = next((f for f in folders if f["id"] == did), None) if did else None
    designs = []
    if folder:
        bs = [b for b in bs if b["dir"] == did]
        from routes.catalog import templates                     # 이 폴더의 틀·디자인 — 여기서 바로 만들 수 있게
        for t in templates():
            if t["dir"] != did:
                continue
            for d in t["designs"]:
                imgs = d["previews"] or [m["file"] for m in d["masters"]]
                designs.append({"series": t["series"], "tname": t["name"], "ready": t["ready"], "id": d["id"], "name": d["name"],
                                "draft": d.get("draft", False), "n": len(imgs),
                                "img": f"/catalog/{'preview' if d['previews'] else 'master'}/{t['series']}/{d['id']}/{imgs[0]}" if imgs else ""})
    if q:
        bs = [b for b in bs if q in " ".join((b["title"], b["key"], b["series_name"] or "", b["design"])).lower()]
    return render_template("projects.html", books=bs, folders=folders, folder=folder, q=q, designs=designs,
                           total=sum(counts.values()), active_nav="프로젝트")


@bp.route("/project/new")
def page_project_new():
    """새 프로젝트 — Canva 편집기 꼴의 전체화면. 왼쪽에서 디자인(틀의 모습)을 고르면 가운데에 그 페이지 틀이
    보이고, [만들기] 가 그 디자인의 원고 넣기 화면(/catalog/<틀>/<디자인>)으로 보낸다. 새 창으로 연다."""
    from routes.catalog import templates
    from routes.intake import MODEL, have_key
    allt = templates()
    ts = [t for t in allt if t["designs"]]
    series_map = {t["series"]: {"name": t["name"], "dir": t["dir"], "dir_name": t["dir_name"]} for t in allt}
    return render_template("project_new.html", templates=ts, claude=have_key(), model=MODEL,
                           series_map=series_map, n=sum(len(t["designs"]) for t in ts))


@bp.route("/design/<series>/<design>")
def page_design(series, design):
    """디자인 상세 — 지면 전부(페이지 틀 + 견본 사진) 크게 보기. 원고 넣기·새 프로젝트에서 열기·확인 완료·삭제."""
    from routes.catalog import _ID, template_info
    t = template_info(series)
    if not t or not _ID.match(design):
        abort(404)
    d = next((x for x in t["designs"] if x["id"] == design), None)
    if not d:
        abort(404)
    pages = [{"src": f"/catalog/master/{series}/{design}/{m['file']}", "label": m["label"], "kind": "페이지 틀", "page": m.get("page")} for m in d["masters"]] \
          + [{"src": f"/catalog/preview/{series}/{design}/{p}", "label": f"견본 {i + 1}", "kind": "견본 사진"} for i, p in enumerate(d["previews"])]
    return render_template("design_detail.html", t=t, d=d, pages=pages, active_nav="프로젝트")


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
