# -*- coding: utf-8 -*-
"""만들기 — 사다리를 한 칸씩 보고, 구성을 골라, 책을 만든다.

    ① 부품   역할마다 지면 조각 하나        `book … make --what=parts`
    ② 틀     빈 칸 + 껍데기 + 간지          `book … make --what=frames`
    ③ 스텝   틀 + 부품 + 지문 n개           `book … make --what=step --key=… --n=…`
    ④ 책     구성(스텝 넣고 빼기·순서·세로) `book … select … ; data ; render --sample`

화면은 얇다 — 모든 일은 `core.render_vivlio.book` CLI 가 한다. 그래서 같은 일을
사람은 여기서, 클로드는 터미널에서 똑같이 할 수 있다.

지면은 작업대와 같은 프레임(`/book-studio/frame`)에 앉힌다. 산출 HTML 은 책의
`build/` 안에 `make_*.html` 로 놓이므로 `/book-studio/doc/<bid>/…` 로 그대로 온다.
"""
import json
import re

from flask import Blueprint, jsonify, render_template, request

from routes.book_studio import _bid, _book_dir, _books, _run

bp = Blueprint("make", __name__)

_RE_KEY = re.compile(r"^[a-z0-9_]{1,32}$")


def _wb_books():
    return [b for b in _books() if b.get("series") == "workbook"]


@bp.route("/make")
def page():
    bs = _wb_books()
    key = request.args.get("b") or ""
    _, meta = _book_dir(key) if key else (None, None)
    if meta:
        key = meta["key"]
    elif bs:
        key = bs[0]["key"]
    return render_template("make.html", books=bs, book_key=key,
                           bid=_bid(key) if key else "", active_nav="만들기")


def _need_book():
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return None, None, (jsonify({"error": "모르는 책"}), 404)
    return d, meta, p


@bp.route("/api/make/sections")
def api_sections():
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    r = _run([d, "sections", "--json"], timeout=60)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-800:]}), 500
    # 로그 머리줄(■ …) 뒤에 JSON 배열 하나
    txt = r.stdout[r.stdout.find("["):]
    try:
        items = json.loads(txt)
    except ValueError:
        return jsonify({"error": "섹션 목록을 못 읽었다", "raw": r.stdout[-800:]}), 500
    try:
        with open(d + "/config.json", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    return jsonify({"sections": items, "select": cfg.get("select") or {},
                    "cycle": (cfg.get("options") or {}).get("order") == "cycle",
                    "book": cfg.get("book") or {}})


@bp.route("/api/make/level", methods=["POST"])
def api_level():
    """사다리 한 칸 → HTML. 돌려주는 `doc` 을 프레임에 앉히면 된다."""
    d, meta, p = _need_book()
    if not d:
        return p
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


@bp.route("/api/make/compose", methods=["POST"])
def api_compose():
    """구성을 쓰고(select·세로) data 를 다시 뽑아 견본을 앉힌다.

    exclude / order : 스텝 키 목록.  limits : {키: 지문 수}.  cycle : 세로 여부.
    full=true 면 견본이 아니라 전권 HTML(오래 걸리고 브라우저가 버겁다).
    """
    d, meta, p = _need_book()
    if not d:
        return p
    keys = lambda xs: [k for k in (xs or []) if _RE_KEY.match(str(k))]  # noqa: E731
    args = [d, "select"]
    if p.get("clear"):
        args.append("--clear")
    else:
        ex, order = keys(p.get("exclude")), keys(p.get("order"))
        if ex:
            args.append("--exclude=" + ",".join(ex))
        if order:
            args.append("--order=" + ",".join(order))
        lim = p.get("limits") or {}
        parts = ["%s=%d" % (k, int(v)) for k, v in lim.items()
                 if _RE_KEY.match(str(k)) and str(v).isdigit() and int(v) > 0]
        if parts:
            args.append("--limits=" + ",".join(parts))
    if p.get("cycle") is not None:
        args.append("--cycle=" + ("on" if p.get("cycle") else "off"))
    args += ["data", "render"] + ([] if p.get("full") else ["--sample"])
    r = _run(args, timeout=600)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/index.html" % meta["bid"],
                    "log": r.stdout[-2000:]})
