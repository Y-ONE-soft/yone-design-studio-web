# -*- coding: utf-8 -*-
"""조립 — 부품을 담아 구성을 만들고, 구성으로 책을 만든다.

    부품 라이브러리   catalog/<계열>/parts/parts.json + PNG (`book … make --what=thumbs` 가 굽는다)
    구성 캔버스       부품 순서 + 지문 수 + 가로/세로 → 미리보기(견본 원고로, config 안 건드림)
                     → 이름 붙여 저장: catalog/<계열>/compositions.json
    책               구성을 기존 책에 적용(select) 또는 새 책(디자인·이름·원고 → data → 견본)에 적용

지금 부품은 **스텝 단위**(원고 파일 단위와 같다). 면 안 조합은 계열 렌더러에서 부품을
빼낸 뒤에 온다 — 그때도 이 화면과 저장 형식은 그대로다(부품 목록만 잘게 늘어난다).

화면은 얇다 — 모든 일은 `core.render_vivlio.book` CLI 가 한다. 클로드도 터미널에서 같은 일을
할 수 있다: `book <책> make --what=compose --steps=step1_c1,step3 --limits=step1_c1=2 --cycle=on`.
"""
import json
import os
import re
import time

from flask import Blueprint, abort, jsonify, render_template, request, send_from_directory

from routes.book_studio import _bid, _book_dir, _books, _run

bp = Blueprint("make", __name__)

SERIES = "workbook"
_RE_KEY = re.compile(r"^[a-z0-9_]{1,32}$")
_RE_NAME = re.compile(r"^[^/\\\x00-\x1f]{1,40}$")      # 구성 이름 — 경로 글자만 막는다
_RE_PNG = re.compile(r"^[a-z0-9_]{1,40}\.png$")


def _cat(*p):
    from routes.catalog import CATALOG
    return os.path.join(CATALOG, SERIES, *p)


def _cfg_of(d):
    try:
        with open(os.path.join(d, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _wb_books():
    return [b for b in _books() if b.get("series") == SERIES]


def _parts():
    try:
        with open(_cat("parts", "parts.json"), encoding="utf-8") as f:
            return json.load(f).get("parts") or []
    except (OSError, ValueError):
        return []


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ── 화면 ────────────────────────────────────────────────────────

@bp.route("/make")
def page():
    from core.render_vivlio.config import _studio_root
    from routes.catalog import template_info
    bs = _wb_books()
    for b in bs:
        cat = _cfg_of(os.path.join(_studio_root(), b["key"])).get("_카탈로그") or {}
        b["design"] = cat.get("design_name") or cat.get("design") or ""
    tpl = template_info(SERIES) or {}
    designs = [{"id": d["id"], "name": d.get("name", d["id"]), "draft": bool(d.get("draft")),
                "preview": (d.get("previews") or [None])[0]} for d in tpl.get("designs") or []]
    return render_template("make.html", parts=_parts(), books=bs, designs=designs,
                           fields=tpl.get("fields") or [], slot_hint=tpl.get("slot_hint", ""),
                           root=tpl.get("root", ""), compositions=_read_json(_cat("compositions.json")),
                           active_nav="조립")


@bp.route("/make/parts/<name>")
def part_png(name):
    if not _RE_PNG.match(name):
        abort(404)
    return send_from_directory(_cat("parts"), name)


# ── 미리보기 — config 안 건드림 ─────────────────────────────────

def _comp_args(p):
    """화면의 구성 → CLI 옵션. steps 는 순서 그대로, limits 는 {키: 지문 수}."""
    steps = [str(k) for k in (p.get("steps") or []) if _RE_KEY.match(str(k))]
    lim = {str(k): int(v) for k, v in (p.get("limits") or {}).items()
           if _RE_KEY.match(str(k)) and str(v).isdigit() and int(v) > 0}
    return steps, lim, bool(p.get("cycle"))


@bp.route("/api/make/preview", methods=["POST"])
def api_preview():
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "견본 책을 모른다"}), 404
    steps, lim, cycle = _comp_args(p)
    if not steps:
        return jsonify({"error": "부품이 하나도 없다"}), 400
    args = [d, "make", "--what=compose", "--steps=" + ",".join(steps),
            "--n=%d" % max(0, min(int(p.get("n") or 2), 99))]
    if lim:
        args.append("--limits=" + ",".join("%s=%d" % kv for kv in lim.items()))
    if cycle:
        args.append("--cycle=on")
    r = _run(args, timeout=180)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/make_compose.html" % meta["bid"],
                    "log": r.stdout[-1200:]})


# ── 구성 저장소 ────────────────────────────────────────────────

@bp.route("/api/make/compositions")
def api_compositions():
    return jsonify({"series": SERIES, "compositions": _read_json(_cat("compositions.json"))})


@bp.route("/api/make/compositions", methods=["POST"])
def api_composition_save():
    p = request.get_json(silent=True) or {}
    name = str(p.get("name") or "").strip()
    if not _RE_NAME.match(name):
        return jsonify({"error": "이름은 1~40자, 슬래시 없이"}), 400
    steps, lim, cycle = _comp_args(p)
    if not steps:
        return jsonify({"error": "부품이 하나도 없다"}), 400
    path = _cat("compositions.json")
    comps = _read_json(path)
    comps[name] = {"steps": steps, "limits": lim, "cycle": cycle,
                   "note": str(p.get("note") or "")[:200], "made": time.strftime("%Y-%m-%d %H:%M")}
    _write_json(path, comps)
    return jsonify({"ok": True, "compositions": comps})


@bp.route("/api/make/compositions", methods=["DELETE"])
def api_composition_delete():
    p = request.get_json(silent=True) or {}
    name = str(p.get("name") or "")
    path = _cat("compositions.json")
    comps = _read_json(path)
    if name not in comps:
        return jsonify({"error": "없는 구성"}), 404
    comps.pop(name)
    _write_json(path, comps)
    return jsonify({"ok": True, "compositions": comps})


# ── 구성을 책에 적용 (config 의 select 를 쓴다) ──────────────────

@bp.route("/api/make/apply", methods=["POST"])
def api_apply():
    """구성 → 그 책의 select(넣을 스텝·순서·지문 수)·세로 → data → 견본."""
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    steps, lim, cycle = _comp_args(p)
    if not steps:
        return jsonify({"error": "부품이 하나도 없다"}), 400
    from core.render_vivlio.series.workbook.data import STEP_META
    known = [k for k, m in STEP_META.items() if not m.get("attach_to")]
    exclude = [k for k in known if k not in steps]
    r = _run([d, "select", "--clear"], timeout=60)       # 지난 구성을 깨끗이 지우고 새로 쓴다
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    args = [d, "select", "--order=" + ",".join(steps), "--cycle=" + ("on" if cycle else "off")]
    if exclude:
        args.append("--exclude=" + ",".join(exclude))
    if lim:
        args.append("--limits=" + ",".join("%s=%d" % kv for kv in lim.items()))
    args += ["data", "render", "--sample"]
    r = _run(args, timeout=600)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "key": meta["key"], "bid": meta["bid"],
                    "doc": "/book-studio/doc/%s/index.html" % meta["bid"], "log": r.stdout[-1500:]})


@bp.route("/api/make/book-info")
def api_book_info():
    """책 하나의 현황 — 구성(select)·PDF 목록·지문 수."""
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = _cfg_of(d)
    stats = {}
    try:
        with open(os.path.join(d, "data.json"), encoding="utf-8") as f:
            stats = json.load(f).get("stats") or {}
    except (OSError, ValueError):
        pass
    pdfs = sorted((n for n in os.listdir(d) if n.lower().endswith(".pdf") and "_견본" not in n),
                  key=lambda n: os.path.getmtime(os.path.join(d, n)), reverse=True)
    return jsonify({"key": meta["key"], "bid": meta["bid"], "select": cfg.get("select") or {},
                    "cycle": (cfg.get("options") or {}).get("order") == "cycle",
                    "book": cfg.get("book") or {}, "stats": stats, "pdfs": pdfs[:4],
                    "has_build": os.path.exists(os.path.join(d, "build", "index.html"))})


# ── 해부도 (부품·틀·스텝) — 역할별 조각 보기 ─────────────────────

@bp.route("/api/make/level", methods=["POST"])
def api_level():
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    what = p.get("what") or "parts"
    if what not in ("parts", "frames", "step"):
        return jsonify({"error": "모르는 칸: " + str(what)}), 400
    args = [d, "make", "--what=" + what]
    if what == "step":
        key = str(p.get("key") or "")
        if not _RE_KEY.match(key):
            return jsonify({"error": "스텝 키가 이상하다"}), 400
        args += ["--key=" + key, "--n=%d" % max(1, min(int(p.get("n") or 2), 20))]
    r = _run(args, timeout=180)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    m = re.search(r"^MAKE_HTML=(.+)$", r.stdout, re.M)
    if not m:
        return jsonify({"error": "산출 경로가 없다", "log": r.stdout[-800:]}), 500
    name = m.group(1).strip().rsplit("/", 1)[-1]
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/%s" % (meta["bid"], name),
                    "log": r.stdout[-1200:]})
