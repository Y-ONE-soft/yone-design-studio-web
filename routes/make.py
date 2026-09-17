# -*- coding: utf-8 -*-
"""조립 — 사용자 순서로 책 한 권을 만든다.

    ① 책      워크북 책 고르기 (새 책은 새 프로젝트에서)
    ② 구성    스텝 넣고 빼기·순서·지문 수·가로/세로 → 프리셋으로 저장·불러오기
              (구조 보기: 부품·틀·스텝 해부도 — `book … make --what=…`)
    ③ 옷      색 손잡이 + 책 이름표(제목·학교·간지 문구)
    ④ 원고    지금 든 원고·지문 수 확인 (원고를 바꾸는 건 새 프로젝트)
    ⑤ 결과    견본(1초) → 전권 PDF(몇 분, 카탈로그 잡)

화면은 얇다 — 모든 일은 `core.render_vivlio.book` CLI 가 한다. 그래서 같은 일을
사람은 여기서, 클로드는 터미널에서 똑같이 할 수 있다.

지면은 작업대와 같은 프레임(`/book-studio/frame`)에 앉힌다. 산출 HTML 은 책의
`build/` 안에 있으므로 `/book-studio/doc/<bid>/…` 로 그대로 온다.

프리셋은 `catalog/<계열>/presets.json` — {이름: {select, cycle, made}}. 책이 아니라
계열에 붙는다(다음 책에서 고르는 게 목적이다).
"""
import json
import os
import re
import time

from flask import Blueprint, jsonify, render_template, request

from routes.book_studio import REPO, _bid, _book_dir, _books, _run

bp = Blueprint("make", __name__)

_RE_KEY = re.compile(r"^[a-z0-9_]{1,32}$")
_RE_NAME = re.compile(r"^[^/\\\x00-\x1f]{1,40}$")      # 프리셋 이름 — 경로 글자만 막는다


def _wb_books():
    return [b for b in _books() if b.get("series") == "workbook"]


def _cfg_of(d):
    try:
        with open(os.path.join(d, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


@bp.route("/make")
def page():
    from core.render_vivlio.config import _studio_root
    bs = _wb_books()
    for b in bs:
        cfg = _cfg_of(os.path.join(_studio_root(), b["key"]))
        cat = cfg.get("_카탈로그") or {}
        b["design"] = cat.get("design_name") or cat.get("design") or ""
        b["made"] = cat.get("made") or ""
    key = request.args.get("b") or ""
    _, meta = _book_dir(key) if key else (None, None)
    if meta:
        key = meta["key"]
    elif bs:
        key = bs[0]["key"]
    return render_template("make.html", books=bs, book_key=key,
                           bid=_bid(key) if key else "", active_nav="조립")


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
    cfg = _cfg_of(d)
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


@bp.route("/api/make/book", methods=["POST"])
def api_book():
    """책 이름표(제목·학교·간지 문구) → config.book. 간지는 data 를 다시 뽑아야 바뀐다."""
    d, meta, p = _need_book()
    if not d:
        return p
    args = [d, "book"]
    for k in ("title", "school", "period", "line1", "line2", "brand"):
        if k in p and p[k] is not None:
            v = str(p[k]).replace("\n", " ").strip()
            args.append(f"--{k}={v}" if v else f"--{k}=")
    if len(args) == 2:
        return jsonify({"error": "바꿀 칸이 없다"}), 400
    args += ["data", "render", "--sample"]
    r = _run(args, timeout=600)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "doc": "/book-studio/doc/%s/index.html" % meta["bid"],
                    "log": r.stdout[-1200:]})


@bp.route("/api/make/manuscript")
def api_manuscript():
    """④ 원고 — 지금 이 책에 든 것. 플랜 경로·업로드 파일·지문 수."""
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = _cfg_of(d)
    plan = (cfg.get("manuscript") or {}).get("plan") or ""
    plan_p = plan.replace("${BOOK}", d)
    up = os.path.join(d, "원고", "업로드")
    files = []
    if os.path.isdir(up):
        for n in sorted(os.listdir(up)):
            fp = os.path.join(up, n)
            if os.path.isfile(fp) and not n.startswith("."):
                files.append({"name": n, "size": os.path.getsize(fp)})
    stats = {}
    try:
        with open(os.path.join(d, "data.json"), encoding="utf-8") as f:
            stats = json.load(f).get("stats") or {}
    except (OSError, ValueError):
        pass
    pdfs = sorted((n for n in os.listdir(d) if n.lower().endswith(".pdf") and "_견본" not in n),
                  key=lambda n: os.path.getmtime(os.path.join(d, n)), reverse=True)
    return jsonify({"plan": plan, "plan_exists": bool(plan_p) and os.path.exists(plan_p),
                    "has_build": os.path.exists(os.path.join(d, "build", "index.html")),
                    "files": files, "stats": stats, "pdfs": pdfs[:4],
                    "catalog": cfg.get("_카탈로그") or {}, "series": cfg.get("series")})


# ── 구성 프리셋 — 계열에 붙는다 ──────────────────────────────────

def _presets_path(series):
    if not _RE_KEY.match(series or ""):
        return None
    return os.path.join(REPO, "catalog", series, "presets.json")


def _read_presets(series):
    p = _presets_path(series)
    if not p or not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _write_presets(series, data):
    p = _presets_path(series)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


@bp.route("/api/make/presets")
def api_presets():
    series = request.args.get("series") or "workbook"
    return jsonify({"series": series, "presets": _read_presets(series)})


@bp.route("/api/make/presets", methods=["POST"])
def api_preset_save():
    """지금 이 책의 구성(select + 세로)을 이름 붙여 저장."""
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    name = str(p.get("name") or "").strip()
    if not _RE_NAME.match(name):
        return jsonify({"error": "이름은 1~40자, 슬래시 없이"}), 400
    cfg = _cfg_of(d)
    series = cfg.get("series") or meta.get("series")
    pre = _read_presets(series)
    pre[name] = {"select": cfg.get("select") or {},
                 "cycle": (cfg.get("options") or {}).get("order") == "cycle",
                 "from": meta["key"], "made": time.strftime("%Y-%m-%d %H:%M")}
    _write_presets(series, pre)
    return jsonify({"ok": True, "presets": pre})


@bp.route("/api/make/presets", methods=["DELETE"])
def api_preset_delete():
    p = request.get_json(silent=True) or {}
    series = p.get("series") or "workbook"
    name = str(p.get("name") or "")
    pre = _read_presets(series)
    if name not in pre:
        return jsonify({"error": "없는 프리셋"}), 404
    pre.pop(name)
    _write_presets(series, pre)
    return jsonify({"ok": True, "presets": pre})
