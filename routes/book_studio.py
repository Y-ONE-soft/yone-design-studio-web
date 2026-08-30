# -*- coding: utf-8 -*-
"""내지 작업대 — 값을 만지는 동안 지면이 바뀐다.

`/cover-studio`(표지 작업대)의 내지 판이다. 같은 뼈대를 따른다:
목록은 하드코딩하지 않고 **폴더에서 찾고**, 조절판은 **계열이 선언한 손잡이**로
저절로 그려진다. 새 책을 만들면 저절로 여기 나타나고, 계열에 손잡이를 더하면
저절로 조절판에 나타난다.

## 왜 이 화면인가

지금까지 색 하나를 바꾸려면 클로드 세션을 열어야 했다. 값이 어디 있는지 모르고
(계열 코드? config? 테마 CSS?), 바꿔도 전권 조판 20~50초를 돌려 PDF 뷰어를 다시
열어야 했기 때문이다. 여기서는 **왼쪽에서 값을 만지면 오른쪽 지면이 바뀐다.**

## 왜 subprocess 인가

`cover_studio` 와 같은 이유 하나 더. 조판 엔진은 계열 모듈을 import 하는데,
계열은 모듈 전역(DEFAULT_METRICS 등)을 들고 있어 한 요청의 값이 다음 요청에
남을 수 있다. 프로세스를 새로 띄우면 그 오염이 원천적으로 없다. 게다가 Flask 가
뜬 파이썬과 조판 파이썬이 다를 수 있다(표지 화면이 이미 그렇다).

## 미리보기는 **뷰어가 직접 조판**한다

PDF 를 굽지 않는다(20~50초). `build/index.html` 을 Vivliostyle 뷰어에 물리면
브라우저가 그 자리에서 조판한다 — 다시 그리는 데 **0.4초**다.
뷰어 번들은 `core/render_vivlio/node_modules/@vivliostyle/viewer/lib` 에 이미 있다.

⚠ **미리보기 면수는 최종 조판과 다를 수 있다.** 뷰어는 렌더하는 대로 세고,
  2패스가 만드는 `pages.css` 는 지난 빌드 것이다. 면수·면 나눔이 걸린 판단은
  `build` 를 돌려 PDF 로 봐야 한다. 미리보기는 **디자인을 보는 자리**다.
"""
import hashlib
import json
import os
import subprocess
import sys
import unicodedata as u

from flask import (Blueprint, Response, abort, jsonify, render_template,
                   request, send_from_directory)

bp = Blueprint("book_studio", __name__)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "core", "render_vivlio", "node_modules",
                      "@vivliostyle", "viewer", "lib")


def _nfc(s):
    return u.normalize("NFC", s or "")


def _python():
    """조판 엔진을 돌릴 파이썬. Flask 가 뜬 것과 다를 수 있다."""
    for p in (os.environ.get("YONE_VIV_PYTHON"),
              "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
              "/opt/homebrew/bin/python3", sys.executable):
        if p and os.path.exists(p):
            return p
    return sys.executable


def _run(args, timeout=180, stdin_data=None):
    return subprocess.run([_python(), "-m", "core.render_vivlio.book"] + args,
                          cwd=REPO, capture_output=True, text=True,
                          timeout=timeout, input=stdin_data)


def _bid(key):
    """책 키 → 경로 한 조각짜리 짧은 id.

    미리보기 URL 은 `…/doc/<bid>/index.html` 이고 테마·서체·자산은 그 **상대
    경로**로 딸려 온다(`theme.css`, `fonts/…`, `assets/…`). 그래서 책을 가리키는
    부분이 **한 조각**이어야 한다 — 키(`조판/교재/…`)를 그대로 쓰면 슬래시 때문에
    조각이 갈라져 하위 폴더가 404 가 된다(여기서 실제로 걸렸다).
    """
    return hashlib.sha1(_nfc(key).encode("utf-8")).hexdigest()[:10]


def _books():
    r = _run(["list", "--json"], timeout=60)
    if r.returncode != 0:
        return []
    try:
        bs = json.loads(r.stdout)
    except ValueError:
        return []
    for b in bs:
        b["bid"] = _bid(b["key"])
    return bs


def _book_dir(key):
    """**키(스튜디오 루트 기준 상대경로) → 절대경로.** 목록에 있는 것만 연다.

    웹에서 받은 경로를 그대로 쓰면 경로 넘나들기를 막을 수 없다. 그래서 키를
    받아 **목록과 대조**한 뒤 서버가 다시 붙인다.
    """
    key = _nfc(key or "")
    for b in _books():
        if key in (_nfc(b["key"]), b["bid"]):     # 키로도 bid 로도 찾는다
            from core.render_vivlio.config import _studio_root
            return os.path.join(_studio_root(), b["key"]), b
    return None, None


# ── 화면 ────────────────────────────────────────────────────────
@bp.route("/book-studio")
def studio():
    bs = _books()
    key = request.args.get("b") or (bs[0]["key"] if bs else "")
    return render_template("book_studio.html", books=bs, book_key=key,
                           active_nav="작업대")


# ── API ─────────────────────────────────────────────────────────
@bp.route("/api/book-studio/knobs")
def api_knobs():
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    r = _run([d, "knobs", "--json"], timeout=60)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-800:]}), 500
    # 엔진이 머리줄(■ …)을 먼저 찍으므로 JSON 만 골라낸다
    body = r.stdout[r.stdout.find("["):] if "[" in r.stdout else "[]"
    try:
        items = json.loads(body)
    except ValueError:
        return jsonify({"error": "손잡이 목록을 읽지 못했다"}), 500
    return jsonify({"book": meta, "knobs": items})


@bp.route("/api/book-studio/save", methods=["POST"])
def api_save():
    """손잡이 값을 config.json 에 쓰고 다시 렌더한다."""
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    sets, resets = [], []
    for k, v in (p.get("changes") or {}).items():
        if any(c in str(k) for c in ",= \n"):
            return jsonify({"error": f"이상한 손잡이 이름: {k}"}), 400
        if v is None:
            resets.append(k)
        else:
            if any(c in str(v) for c in ",\n"):
                return jsonify({"error": f"이상한 값: {v}"}), 400
            sets.append(f"{k}={v}")
    if not sets and not resets:
        return jsonify({"error": "바꿀 것이 없다"}), 400
    args = [d, "knobs"]
    if sets:
        args.append("--set=" + ",".join(sets))
    if resets:
        args.append("--reset=" + ",".join(resets))
    r = _run(args, timeout=60)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-800:]}), 500
    return jsonify({"ok": True, "log": r.stdout[-1500:]})


@bp.route("/api/book-studio/render", methods=["POST"])
def api_render():
    """조판 직전까지만 다시 만든다(PDF 를 굽지 않는다) — 보통 0.4초.

    기본은 **견본**이다. 전권(116~259면)을 브라우저 안에서 조판시키면 렌더러가
    버거워 화면이 멎는다(실제로 겪었다). 디자인을 보는 데는 몇 면이면 되고,
    면수·면 나눔이 걸린 판단은 어차피 `build` 로 PDF 를 봐야 한다.
    """
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    args = [d, "render"] + ([] if p.get("full") else ["--sample"])
    r = _run(args, timeout=300)
    if r.returncode != 0:
        return jsonify({"error": (r.stderr or r.stdout)[-1500:]}), 500
    return jsonify({"ok": True, "log": r.stdout[-1500:]})


@bp.route("/api/book-studio/text", methods=["GET", "POST"])
def api_text():
    """지면에서 클릭한 글 한 조각을 읽고 고친다.

    고친 것은 `data.json` 이 아니라 **편집 이력**(`edits.json`)에 연산으로 쌓인다 —
    data.json 은 원고에서 만들어지므로 거기 직접 쓰면 `data` 를 한 번 돌리는 순간
    말없이 되돌아간다. 이력은 읽는 자리에서 얹히므로 조판도 검수도 같은 글을 본다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    from core.render_vivlio import richtext as rt
    get = request.method == "GET"
    p = {} if get else (request.get_json(silent=True) or {})
    d, meta = _book_dir(request.args.get("b") if get else p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    ref = (request.args.get("ref") if get else p.get("ref")) or ""
    if not ref or any(c in ref for c in "/\\ \n"):
        return jsonify({"error": "이상한 자리표"}), 400
    cfg = bookmod.load(d)
    cur, raw = ed.preview(cfg)
    if not ed.exists(cur, ref):
        return jsonify({"error": f"원본에 없는 자리: {ref}"}), 404
    st = ed.read(cfg)
    if get:
        touched = any(o.get("ref") == ref for o in st["ops"][:st["head"]])
        return jsonify({"ref": ref,
                        "text": rt.to_text(ed.get(cur, ref)),
                        "origin": rt.to_text(ed.get(raw, ref)),
                        "edited": touched,
                        "history": {"head": st["head"], "total": len(st["ops"])}})
    text = p.get("text")
    if text is None:
        return jsonify({"error": "글이 없다"}), 400
    if len(text) > 20000:
        return jsonify({"error": "너무 길다"}), 400
    if p.get("revert"):
        # 원고대로 = 원고의 그 값으로 되돌리는 **연산**을 쌓는다.
        # 지우개가 아니라 또 하나의 편집이라, 이것도 되돌릴 수 있다.
        st = ed.push(cfg, {"op": "set", "ref": ref, "v": ed.get(raw, ref),
                           "note": "원고대로"})
    else:
        st = ed.push(cfg, {"op": "set", "ref": ref,
                           "v": rt.from_text(text, like=ed.get(raw, ref))})
    return jsonify({"ok": True, "entries": st["head"],
                    "history": {"head": st["head"], "total": len(st["ops"])}})


@bp.route("/api/book-studio/op", methods=["POST"])
def api_op():
    """구조 편집 — 문단 나누기·합치기·넣기·지우기. 글자 편집과 같은 이력에 쌓인다."""
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    op = p.get("op")
    if op not in ed.OPS:
        return jsonify({"error": f"모르는 연산: {op}"}), 400
    ref = p.get("ref") or ""
    if not ref or any(c in ref for c in "/\\ \n"):
        return jsonify({"error": "이상한 자리표"}), 400
    cfg = bookmod.load(d)
    st = ed.push(cfg, {k: v for k, v in p.items()
                       if k in ("op", "ref", "v", "at", "note")})
    return jsonify({"ok": True,
                    "history": {"head": st["head"], "total": len(st["ops"])}})


@bp.route("/api/book-studio/history", methods=["GET", "POST"])
def api_history():
    """편집 이력 보기 / 되돌리기 · 다시 실행."""
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    get = request.method == "GET"
    p = {} if get else (request.get_json(silent=True) or {})
    d, meta = _book_dir(request.args.get("b") if get else p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    if not get:
        act = p.get("action")
        n = max(1, min(int(p.get("n") or 1), 200))
        if act == "undo":
            ed.undo(cfg, n)
        elif act == "redo":
            ed.redo(cfg, n)
        else:
            return jsonify({"error": f"모르는 동작: {act}"}), 400
    st = ed.read(cfg)
    rows = [{"i": i, "op": o.get("op"), "ref": o.get("ref"),
             "at": o.get("at", ""), "note": o.get("note", ""),
             "applied": i < st["head"]}
            for i, o in enumerate(st["ops"])]
    return jsonify({"head": st["head"], "total": len(st["ops"]),
                    "ops": rows[-60:]})


@bp.route("/api/vivlio-book/slots")
def api_vivlio_slots():
    """기준 책이 요구하는 원고 슬롯 — 조판 카드가 칸을 그릴 때 쓴다.

    빈 목록이면 '원고 폴더를 통째로 훑는 계열'(블랙북)이라는 뜻이다.
    """
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    try:
        from engines.vivlio_book.engine import book_slots
        return jsonify({"book": meta, "slots": book_slots(meta["key"])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/book-studio/refs")
def api_refs():
    """`build/refs.json` — 화면의 `vrefN` 클래스 ↔ 원본 자리표."""
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    p = os.path.join(d, "build", "refs.json")
    if not os.path.exists(p):
        return jsonify({})
    with open(p, encoding="utf-8") as f:
        return Response(f.read(), mimetype="application/json")


@bp.route("/api/book-studio/overrides", methods=["GET", "POST"])
def api_overrides():
    """손잡이 밖 탈출구 — 책 폴더의 `overrides.css` 를 읽고 쓴다."""
    key = (request.get_json(silent=True) or {}).get("b") if request.method == "POST" \
        else request.args.get("b")
    d, meta = _book_dir(key)
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    path = os.path.join(d, "overrides.css")
    if request.method == "GET":
        text = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                text = f.read()
        return jsonify({"css": text})
    css = (request.get_json(silent=True) or {}).get("css", "")
    if len(css) > 200_000:
        return jsonify({"error": "너무 크다(200KB 넘음)"}), 400
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)
    return jsonify({"ok": True, "bytes": len(css.encode("utf-8"))})


# ── 미리보기용 정적 파일 ─────────────────────────────────────────
CORE = os.path.join(REPO, "core", "render_vivlio", "node_modules",
                    "@vivliostyle", "core", "lib")


@bp.route("/book-studio/core/<path:sub>")
def core_js(sub):
    """`@vivliostyle/core` — **뷰어 앱 없이** 우리 캔버스에 직접 조판하는 엔진.

    지금까지는 Vivliostyle **뷰어 앱**을 iframe 으로 물고 있었다. 그러면 그 앱의
    툴바(목차·검색·글자 크기·인쇄…)가 화면 위쪽을 차지하고, 우리가 그걸 못 바꾼다.
    조판 프로그램을 만들려면 **화면은 우리 것**이어야 한다.

    CoreViewer 는 `viewportElement` 로 **우리 div** 를 받아 거기에 지면을 그린다.
    게다가 `documentObject`(파싱한 DOM 을 그대로) 와 `userStyleSheet`(CSS 문자열)를
    받으므로, 색·여백을 바꿀 때 **서버를 거치지 않고** 그 자리에서 다시 앉힐 수 있다.
    """
    return send_from_directory(CORE, sub)


@bp.route("/book-studio/viewer/")
@bp.route("/book-studio/viewer/<path:sub>")
def viewer(sub="index.html"):
    if not os.path.isdir(VIEWER):
        abort(404, "Vivliostyle 뷰어가 없다 — `npm --prefix core/render_vivlio ci`")
    return send_from_directory(VIEWER, sub)


@bp.route("/book-studio/doc/<bid>/<path:sub>")
def doc(bid, sub):
    """고른 책의 **`build/` 안만** 내준다.

    책 폴더 전체가 아니라 `build/` 만 연다 — 원고·산출 PDF·백업이 웹으로 새면
    안 된다. `send_from_directory` 가 경로 넘나들기를 막지만, bid 로만 책을
    고르게 해 두어 애초에 임의 경로가 들어올 자리를 없앤다.
    """
    d, meta = _book_dir(bid)
    if not d:
        return abort(404)
    return send_from_directory(os.path.join(d, "build"), sub)
