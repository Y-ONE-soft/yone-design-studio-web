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

## 화면이 우리 것이다 — 뷰어 앱을 벗었다

예전에는 Vivliostyle **뷰어 앱**을 iframe 으로 물었다. 그러면 그 앱 툴바가 화면
위쪽을 차지하는데 우리가 못 바꾼다. 이제 `@vivliostyle/core` 의 CoreViewer 를
**우리 div**(`#ide-stage`)에 물린다(`core/render_vivlio/webcore/`). 그래서 도구줄·
툴·팔레트가 전부 우리 것이고, 지면이 **같은 문서 안**에 있어 클릭·편집이 iframe 을
넘나들지 않는다. 색은 `userStyleSheet` 로 **서버 없이** 미리 볼 수 있다.

PDF 는 굽지 않는다(20~50초). 서버는 `build/index.html` 만 만들고(0.4초) 조판은
브라우저가 한다.

⚠ **미리보기 면수는 최종 조판과 다를 수 있다.** 뷰어는 렌더하는 대로 세고,
  2패스가 만드는 `pages.css` 는 지난 빌드 것이다. 면수·면 나눔이 걸린 판단은
  `build` 를 돌려 PDF 로 봐야 한다. 미리보기는 **디자인을 보는 자리**다.
"""
import hashlib
import json
import os
import re
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


def _build_dir(book_dir):
    """그 책의 조판 결과 폴더. 계열이 안다 — 중등부는 책 폴더 밖에 쓴다.

    ⚠ 여기를 `<책폴더>/build` 로 못 박아 두면 중등부는 **404 만 난다**
      (지면이 안 나오는데 로그는 조용해서 원인을 찾기 어렵다).
    """
    from core.render_vivlio import book as bookmod
    try:
        return bookmod.build_dir(bookmod.load(book_dir))
    except Exception:
        return os.path.join(book_dir, "build")


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
    """`?b=…` 로 책을 지정할 수 있다.

    ⚠ 맥의 파일 이름은 **NFD**(ㄱ+ㅏ)라 목록의 키도 NFD 인데, 주소창이나 링크로
      들어오는 글자는 대개 **NFC**(가) 다. 그냥 비교하면 안 맞아서 **조용히 첫
      책이 열린다**(그래 놓고 팔레트만 맞는 책 것이 와 더 헷갈린다). 그래서
      목록과 대조해 **목록에 있는 그 키**로 바꿔 넘긴다.
    """
    bs = _books()
    key = request.args.get("b") or ""
    _, meta = _book_dir(key) if key else (None, None)
    if meta:
        key = meta["key"]
    elif bs:
        key = bs[0]["key"]
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
    # ⚠ 값도 **같은 이력**에 쌓는다. 예전에는 별도 CLI 가 config 를 직접 고쳐서
    #   ⌘Z 로 못 되돌렸다 — 무엇을 되돌리려면 어느 단추를 눌러야 하는지 사람이
    #   알아야 했다. 인디자인은 무엇을 했든 ⌘Z 하나다.
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as _ed
    cfg = bookmod.load(d)
    done, st = [], _ed.read(cfg)
    for k, v in (p.get("changes") or {}).items():
        st = _ed.push(cfg, {"op": "knob", "key": k,
                            "v": None if v is None else _num(v)})
        done.append(k)
    return jsonify({"ok": True, "changed": done, "history": _hist(st),
                    "log": "값 %d개를 이력에 쌓았습니다 — ⌘Z 로 되돌릴 수 있습니다"
                           % len(done)})


def _num(v):
    """`"3.5"` 처럼 온 숫자는 숫자로 — config 에 문자열로 박히면 조판이 다르다."""
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    t = str(v).strip()
    try:
        return int(t) if t.lstrip("-").isdigit() else float(t)
    except ValueError:
        return t


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

    # ── 글이 어디서 오는가 ──
    # 지면의 글이 전부 원고에서 오는 것은 아니다. 머리 띠 제목은 **책 설정**
    # (`book.subject`)이고, 탭·기입칸은 **조판이 만든 것**이라 원본이 없다.
    # 그걸 구분 안 하고 다 원고로 보면, 클릭했을 때 "원본에 없는 자리" 만
    # 뜨고 왜 안 되는지 알 수 없다.
    from core.render_vivlio import refs as _refs
    src = _refs.source_of(ref)
    if src == "fixed":
        return jsonify({"error": "조판이 만든 자리라 글을 고칠 수 없습니다 — "
                                 "모양은 오른쪽 '단락 스타일'에서 바꿉니다",
                        "kind": "fixed"}), 409
    if src == "config":
        return _text_from_config(cfg, ref, p, get)

    # ⚠ 계열에 따라 **원고 자료 파일이 아예 없다**(포켓북은 원고에서 바로
    #   지면을 만든다). 그냥 열면 500 이 난다 — 무엇이 되고 안 되는지 말한다.
    if not os.path.exists(ed.data_path(cfg)):
        return jsonify({"error": "이 교재는 원고에서 바로 조판해 글을 여기서 "
                                 "못 고칩니다 — 모양(스타일·색·여백)은 됩니다",
                        "kind": "nodata"}), 409
    cur, raw = ed.preview(cfg)
    if not ed.exists(cur, ref):
        return jsonify({"error": f"원본에 없는 자리: {ref}"}), 404
    # ⚠ 덩어리 자리표(지문 상자·문항 전체)에는 **글이 없다** — 그건 상자지
    #   글이 아니다. 그냥 열면 빈 편집기가 떠서 무엇이 잘못됐는지 알 수 없다.
    val = ed.get(cur, ref)
    # 합친 표 칸은 `{"v": …, "c": 2}` 라 겉보기에 덩어리다. 안쪽 글로 내려가지
    # 않으면 **합치는 순간 그 칸을 못 고치게 된다**(합치기가 글을 가둔다).
    if isinstance(val, dict) and "t" not in val and "v" in val:
        ref += ".v"
        val = ed.get(cur, ref)
    if isinstance(val, dict) and "t" not in val:
        return jsonify({"error": "덩어리라 글이 없습니다 — 두 번 눌러 안쪽 "
                                 "한 줄을 고르거나, 모양은 오른쪽 패널에서 바꾸세요",
                        "kind": "container"}), 409
    if isinstance(val, list) and any(isinstance(x, (dict, list))
                                     and not (isinstance(x, dict) and "t" in x)
                                     for x in val):
        return jsonify({"error": "여러 줄이 든 자리입니다 — 두 번 눌러 "
                                 "한 줄만 고르세요", "kind": "container"}), 409
    st = ed.read(cfg)
    if get:
        touched = any(o.get("ref") == ref for o in st["ops"][:st["head"]])
        return jsonify({"ref": ref,
                        "text": rt.to_text(ed.get(cur, ref)),
                        # 편집기는 **보이는 그대로** 고친다 — 표시(`**굵게**`)가
                        # 아니라 진짜 서식이라야 글자 단위 서식이 안 날아간다.
                        "html": rt.to_html(ed.get(cur, ref)),
                        "origin": rt.to_text(ed.get(raw, ref)),
                        "edited": touched,
                        "history": _hist(st)})
    text = p.get("text")
    src_html = p.get("html")
    if text is None and src_html is None:
        return jsonify({"error": "글이 없다"}), 400
    if len(text or src_html or "") > 40000:
        return jsonify({"error": "너무 길다"}), 400
    if p.get("revert"):
        # 원고대로 = 원고의 그 값으로 되돌리는 **연산**을 쌓는다.
        # 지우개가 아니라 또 하나의 편집이라, 이것도 되돌릴 수 있다.
        st = ed.push(cfg, {"op": "set", "ref": ref, "v": ed.get(raw, ref),
                           "note": "원고대로"})
    elif src_html is not None:
        st = ed.push(cfg, {"op": "set", "ref": ref,
                           "v": rt.from_html(src_html, like=ed.get(raw, ref))})
    else:
        st = ed.push(cfg, {"op": "set", "ref": ref,
                           "v": rt.from_text(text, like=ed.get(raw, ref))})
    return jsonify({"ok": True, "entries": st["head"],
                    "history": _hist(st)})


def _text_from_config(cfg, ref, p, get):
    """머리 띠 제목처럼 **책 설정**에서 오는 글.

    원고가 아니라 `config.json` 을 고쳐야 한다 — 편집 이력에 쌓으면 아무 일도
    안 일어난다(그 자리가 data.json 에 없기 때문이다). 한 번 고치면 그 책의
    모든 머리 띠가 같이 바뀐다는 것도 화면에 알려 준다.
    """
    import shutil
    from core.render_vivlio import knobs as kn
    val = kn.get(cfg.data, ref)
    if val is None:
        return jsonify({"error": f"설정에 없는 자리: {ref}"}), 404
    if get:
        return jsonify({"ref": ref, "text": str(val), "origin": str(val),
                        "edited": False, "kind": "config",
                        "note": "이 글은 원고가 아니라 **책 설정**에서 옵니다 — "
                                "고치면 이 책의 같은 자리가 모두 바뀝니다."})
    text = p.get("text")
    if text is None:
        return jsonify({"error": "글이 없다"}), 400
    if len(text) > 500 or "\n" in text:
        return jsonify({"error": "설정 값이 너무 길거나 줄이 나뉘었다"}), 400
    path = cfg.path("config.json")
    raw = open(path, encoding="utf-8").read()
    try:
        out = kn.patch_text(raw, {ref: text})
    except Exception as e:
        return jsonify({"error": f"설정을 못 고쳤다: {e}"}), 500
    shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return jsonify({"ok": True, "kind": "config",
                    "note": "책 설정을 고쳤습니다(되돌리려면 config.json.bak)."})


@bp.route("/api/book-studio/op", methods=["POST"])
def api_op():
    """구조 편집 — 문단 나누기·합치기·넣기·지우기. 글자 편집과 같은 이력에 쌓인다."""
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    p = request.get_json(silent=True) or {}
    op = p.get("op")
    if op not in ed.OPS:
        return jsonify({"error": f"모르는 연산: {op}"}), 400
    ref = p.get("ref") or ""
    if not ref or any(c in ref for c in "/\\ \n") or ".." in ref:
        return jsonify({"error": "이상한 자리표"}), 400
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    st = ed.push(cfg, {k: v for k, v in p.items()
                       if k in ("op", "ref", "v", "at", "note")})
    return jsonify({"ok": True,
                    "history": _hist(st)})


# 길이를 재는 속성 — 여기에 **맨 숫자**를 넣으면 CSS 가 통째로 무시된다.
_LEN_PROPS = {
    "font-size", "letter-spacing", "word-spacing", "text-indent",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "width", "height", "min-height", "max-width", "top", "left", "right",
    "bottom", "border-width", "border-radius", "column-gap", "gap",
}
_LEN_OK = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(pt|mm|cm|in|px|em|rem|%|q)$", re.I)


def _needs_unit(prop, val):
    """`font-size: 20` 처럼 단위 없는 값을 **미리** 잡는다.

    ⚠ 이게 없어서 화면에서 20 을 넣으면 CSS 가 통째로 무시되고, 그런데도
      "저장했습니다" 가 떴다. 조용히 아무 일도 안 하는 것이 제일 나쁘다.
    """
    v = (val or "").strip()
    if not v or prop.lower() not in _LEN_PROPS:
        return ""
    if v in ("0", "auto", "inherit", "initial", "unset", "normal"):
        return ""
    if _LEN_OK.match(v):
        return ""
    if re.match(r"^-?[\d.]+$", v):
        return (f"{prop}: {v} — 단위가 없습니다. "
                f"pt·mm 을 붙여 주세요(예: {v}pt).")
    return ""


@bp.route("/api/book-studio/styles", methods=["GET", "POST"])
def api_styles():
    """단락 스타일 — 선택자 하나에 걸린 규칙을 읽고 쓴다.

    인디자인의 단락 스타일에 해당한다: **하나를 고치면 그 스타일이 걸린 곳이 전부
    바뀐다.** 우리는 조판이 CSS 라 그게 곧 규칙 하나를 고치는 일이다.
    `config.json` 의 `styles` 절에 쌓고 `build/knobs.css` 로 나간다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import knobs as kn
    import json as _json
    import shutil
    get = request.method == "GET"
    p = {} if get else (request.get_json(silent=True) or {})
    if not get:
        # ⚠ 검사를 책 조회보다 **먼저** 한다. 뒤에 두면 '모르는 책' 404 가 먼저
        #   나서 검사가 도는지 아닌지를 시험으로 알 수 없다(실제로 그랬다).
        sel = (p.get("selector") or "").strip()
        if not sel or len(sel) > 200 or "{" in sel or "}" in sel:
            return jsonify({"error": "이상한 선택자"}), 400
        props = p.get("props")
        if not isinstance(props, dict):
            return jsonify({"error": "규칙이 없다"}), 400
        for k, v in props.items():
            if any(c in str(k) + str(v) for c in "{};<>"):
                return jsonify({"error": f"이상한 값: {k}: {v}"}), 400
            bad = _needs_unit(str(k), str(v))
            if bad:
                return jsonify({"error": bad}), 400
    d, meta = _book_dir(request.args.get("b") if get else p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    if get:
        # 스타일 목록에 `.pbox` 같은 CSS 이름만 나오면 무엇을 고르는지 알 수
        # 없다. 계열이 붙여 둔 사람 이름을 같이 준다.
        try:
            from core.render_vivlio import series as _sreg
            names = dict(_sreg.get(cfg.series).style_names or {})
        except Exception:
            names = {}
        return jsonify({"styles": cfg.section("styles") or {}, "names": names})
    # ⚠ 파일을 직접 고치지 않는다. **같은 이력**에 연산으로 쌓아야
    #   ⌘Z 하나로 글도 디자인도 되돌릴 수 있다(예전엔 `.bak` 으로 갈라져 있었다).
    from core.render_vivlio import edits as _ed
    cur = dict((cfg.section("styles") or {}).get(sel) or {})
    for k, v in props.items():
        if v in ("", None):
            cur.pop(k, None)
        else:
            cur[k] = v
    st = _ed.push(cfg, {"op": "style", "sel": sel, "v": cur or None})
    cfg.reload()
    styles = cfg.section("styles") or {}
    return jsonify({"ok": True, "styles": styles, "history": _hist(st)})


@bp.route("/api/book-studio/paraclass", methods=["POST"])
def api_paraclass():
    """고른 자리에 **이름 붙인 스타일**을 건다(인디자인의 단락 스타일 적용).

    ## 왜 따로 있나

    "이 자리에만" 은 `[data-ref="…"]` 선택자로 걸린다 — 그 한 곳만 바뀐다.
    인디자인의 단락 스타일은 **이름을 고치면 걸린 곳이 전부** 바뀌는 것이다.
    그러려면 그 문단이 **그 스타일 이름을 달고 있어야** 한다.

    조판 결과의 class 는 계열 렌더러가 정하므로, 사람이 더 다는 이름은
    편집 이력에 `cls` 연산으로 쌓고 `refs.mark()` 가 얹는다 — 계열 코드를
    하나도 안 고쳐도 **아홉 계열 모두**에서 된다.

    ⚠ 스타일 이름은 `ps-` 로 시작한다. 계열이 쓰는 클래스(`.q`·`.head`)와
      섞이면 어느 쪽이 사람 것인지 알 수 없다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    # 한 자리(`ref`) 또는 **여러 자리**(`refs`) — 찾기 결과 전부에 거는 길.
    raw = p.get("refs")
    refs = [str(x).strip() for x in raw] if isinstance(raw, list) \
        else [str(p.get("ref") or "").strip()]
    refs = [r for r in refs if r]
    if not refs:
        return jsonify({"error": "이상한 자리표"}), 400
    if len(refs) > 3000:
        return jsonify({"error": "한 번에 너무 많습니다"}), 400
    for ref in refs:
        if any(c in ref for c in "/\\ \n") or ".." in ref:
            return jsonify({"error": f"이상한 자리표: {ref}"}), 400
    names = []
    for n in str(p.get("cls") or "").replace(".", " ").split():
        if not re.match(r"^ps-[0-9A-Za-z가-힣_-]{1,40}$", n):
            return jsonify({"error": f"스타일 이름은 `ps-`로 시작합니다: {n}"}), 400
        names.append(n)
    cfg = bookmod.load(d)
    v = " ".join(names)
    st = ed.read(cfg)
    for ref in refs:
        st = ed.push(cfg, {"op": "cls", "ref": ref, "v": v,
                           "note": "단락 스타일"})
    return jsonify({"ok": True, "cls": v, "count": len(refs),
                    "history": _hist(st)})


IMG_OK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
IMG_MAX = 20 * 1024 * 1024


@bp.route("/api/book-studio/images", methods=["GET", "POST"])
def api_images():
    """그림 — 책 폴더 `assets/` 에 넣고 목록을 준다.

    ## 왜 파서가 아니라 여기서 넣는가

    원고(hwpx)에 든 그림은 계열 파서가 뽑는다. 그런데 조판을 하다 보면 원고에
    없던 그림을 **한 자리에만** 넣어야 할 때가 생긴다(도표를 다시 그렸다든가).
    그걸 하려고 계열 코드를 고치면 그 계열 책이 전부 흔들린다. 그래서 그림은
    파일로 넣고 **CSS 규칙 한 줄**로 그 자리에 앉힌다 —
    `[data-ref="…"]::after{content:url("assets/그림.png")}`.
    계열 코드가 하나도 안 바뀌므로 이미 납품한 책은 그대로다.

    ⚠ `assets/` 는 `build/` 로 통째 복사된다(`stage.stage_book_assets`).
      그래서 지운 그림은 다음 조판에서 사라진다 — 규칙도 같이 지울 것.
    """
    import shutil
    from core.render_vivlio import book as bookmod
    get = request.method == "GET"
    if not get:
        f0 = request.files.get("file")
        if not f0 or not f0.filename:
            return jsonify({"error": "파일이 없다"}), 400
        if not f0.filename.lower().endswith(IMG_OK):
            return jsonify(
                {"error": "그림 파일이 아니다 (%s)" % ", ".join(IMG_OK)}), 400
    key = request.args.get("b") if get else request.form.get("b")
    d, meta = _book_dir(key)
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    adir = cfg.resolve((cfg.section("assets") or {}).get("dir", "assets"))

    def listing():
        if not os.path.isdir(adir):
            return []
        out = []
        for n in sorted(os.listdir(adir)):
            if n.lower().endswith(IMG_OK) and not n.startswith("."):
                out.append({"name": n,
                            "size": os.path.getsize(os.path.join(adir, n))})
        return out

    if get:
        return jsonify({"images": listing(), "dir": adir})

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "파일이 없다"}), 400
    name = os.path.basename(f.filename).replace("\\", "")
    if not name.lower().endswith(IMG_OK):
        return jsonify({"error": "그림 파일이 아니다 (%s)" % ", ".join(IMG_OK)}), 400
    os.makedirs(adir, exist_ok=True)
    dst = os.path.join(adir, name)
    if os.path.exists(dst):                       # 덮어쓰지 않는다 — 다른 자리가 쓸 수 있다
        stem, ext = os.path.splitext(name)
        i = 2
        while os.path.exists(dst):
            name = "%s_%d%s" % (stem, i, ext)
            dst = os.path.join(adir, name)
            i += 1
    f.save(dst)
    if os.path.getsize(dst) > IMG_MAX:
        os.remove(dst)
        return jsonify({"error": "그림이 너무 크다 (20MB 넘음)"}), 400
    return jsonify({"ok": True, "name": name, "images": listing()})


def _knob_spec(d):
    """계열이 선언한 손잡이 + 지금 값. 모델에게 줄 목록이자 검사표다."""
    r = _run([d, "knobs", "--json"], timeout=60)
    if r.returncode != 0:
        return []
    body = r.stdout[r.stdout.find("["):] if "[" in r.stdout else "[]"
    try:
        return json.loads(body)
    except ValueError:
        return []


@bp.route("/api/book-studio/assist", methods=["GET", "POST"])
def api_assist():
    """한국어로 시키면 클로드가 **디자인 값**을 고친다.

    고칠 수 있는 곳은 셋뿐이고(손잡이 · styles · overrides.css) 셋 다 **그 책
    폴더 안 파일**이라 다른 책은 어떤 경우에도 안 바뀐다. 계열 코드도 원고도
    이 길로는 못 건드린다 — 그게 이 기능을 붙일 수 있는 유일한 조건이다.
    자세한 것은 `core/render_vivlio/assist.py` 머리말.
    """
    import shutil
    from core.render_vivlio import assist
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import knobs as kn

    if request.method == "GET":       # 화면이 "쓸 수 있는가" 를 먼저 묻는다
        return jsonify({"ready": assist.have_key(), "model": assist.MODEL})

    p = request.get_json(silent=True) or {}
    prompt = (p.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "무엇을 고칠지 적어 주세요"}), 400
    if len(prompt) > 2000:
        return jsonify({"error": "너무 깁니다"}), 400
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404

    cfg = bookmod.load(d)
    spec = _knob_spec(d)
    ctx = assist.context(cfg, spec,
                         page_classes=p.get("classes") or (),
                         picked=str(p.get("picked") or "")[:200])
    try:
        raw = assist.ask(prompt, ctx)
    except assist.Refused as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:                       # 통신·인증 실패
        return jsonify({"error": f"클로드를 못 불렀습니다: {e}"}), 502

    got = assist.vet(raw, spec)
    if not (got["knobs"] or got["styles"] or got["overrides_css"] is not None):
        return jsonify({"ok": True, "changed": 0, "note": got["note"],
                        "refused": got["refused"]})

    # ── 고치기 전에 되돌릴 자리를 만든다 ──
    cpath = cfg.path("config.json")
    opath = cfg.path("overrides.css")
    changes = dict(got["knobs"])
    if got["styles"]:
        merged = dict(cfg.section("styles") or {})
        for sel, props in got["styles"].items():
            cur = dict(merged.get(sel) or {})
            for k2, v2 in props.items():
                if v2 == "":
                    cur.pop(k2, None)
                else:
                    cur[k2] = v2
            if cur:
                merged[sel] = cur
            else:
                merged.pop(sel, None)
        changes["styles"] = merged
    if changes:
        rawtxt = open(cpath, encoding="utf-8").read()
        try:
            out = kn.patch_text(rawtxt, changes)
        except Exception:
            out = json.dumps(kn.apply(cfg.data, changes),
                             ensure_ascii=False, indent=2) + "\n"
        shutil.copy2(cpath, cpath + ".bak")
        with open(cpath, "w", encoding="utf-8") as f:
            f.write(out)
    if got["overrides_css"] is not None:
        if os.path.exists(opath):
            shutil.copy2(opath, opath + ".bak")
        else:
            # ⚠ 원래 **없던** 파일이면 `.bak` 도 없어서 되돌릴 방법이 사라진다.
            #   "원래 없었다" 는 것도 되돌릴 상태다 — 표식을 남긴다.
            with open(opath + ".none", "w") as f:
                f.write("이 파일이 있으면 overrides.css 는 원래 없던 것이다\n")
        with open(opath, "w", encoding="utf-8") as f:
            f.write(got["overrides_css"])

    return jsonify({"ok": True, "note": got["note"], "refused": got["refused"],
                    "knobs": got["knobs"], "styles": got["styles"],
                    "css_changed": got["overrides_css"] is not None,
                    "changed": len(got["knobs"]) + len(got["styles"])
                               + (1 if got["overrides_css"] is not None else 0)})


@bp.route("/api/book-studio/assist-undo", methods=["POST"])
def api_assist_undo():
    """직전 한 번을 되돌린다 — `.bak` 을 도로 씌운다."""
    import shutil
    from core.render_vivlio import book as bookmod
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    back = []
    for name in ("config.json", "overrides.css"):
        f = cfg.path(name)
        if os.path.exists(f + ".none"):     # 원래 없던 파일 — 도로 없앤다
            if os.path.exists(f):
                os.remove(f)
            os.remove(f + ".none")
            back.append(name + " (지움)")
        elif os.path.exists(f + ".bak"):
            shutil.copy2(f + ".bak", f)
            back.append(name)
    if not back:
        return jsonify({"error": "되돌릴 것이 없습니다"}), 404
    return jsonify({"ok": True, "restored": back})


def _hist(st):
    """이력 상태 한 줄 — **고친 것을 알린 모든 응답**에 실어야 한다.

    ⚠ 안 실으면 화면의 되돌리기 단추가 **꺼진 채로 남는다.** 실제로 그랬다:
      스타일을 바꿔 지면은 바뀌었는데 ⌘Z 가 회색이라 되돌릴 수가 없었다.
      고친 것을 알리는 자리는 여기 하나로 모은다.
    """
    return {"head": st["head"], "total": len(st["ops"])}


def _list_slot(ref, data=None, cfg=None):
    """이 자리표가 **어느 목록의 몇 번째**인가 → (목록 경로, 넣을 자리).

    표·상자는 목록 안에 들어간다. 예전에는 `blocks` 목록만 찾아서 문항 안에서만
    넣을 수 있었다 — 어휘부처럼 `paras` 목록만 있는 자리에서는 "넣을 자리가
    아니다" 만 떴다. 어느 목록이든 받되, **아무 목록에나 넣으면 안 된다.**

    ⚠ `…problems.0.stem` 을 고르면 위로 올라가다 `problems` 목록을 만난다.
      거기 상자를 끼우면 **문항 자리에 상자가 들어가** 조판이 깨진다. 그래서
      그 목록에 실제로 든 것이 **글·블록**인지 보고 정한다(이름이 아니라 내용).
    """
    from core.render_vivlio import edits as _ed
    parts = ref.split(".")
    while parts:
        if parts[-1].isdigit() and len(parts) >= 2:
            base = ".".join(parts[:-1])
            if data is not None:
                lst = _ed.get(data, base)
                ok = isinstance(lst, list) and _accepts(cfg, base, lst)
                if not ok:
                    parts.pop()
                    continue
            return base, int(parts[-1]) + 1
        parts.pop()
    return None, 0


def _accepts(cfg, base, lst):
    """이 목록이 표·상자를 받나 — **계열에게 묻는다**(모르면 공용 규칙)."""
    key = base.rsplit(".", 1)[-1]
    if cfg is not None:
        try:
            from core.render_vivlio import book as _b
            return bool(_b._series(cfg).accepts_block(key, lst))
        except Exception:
            pass
    return _para_like(lst)


# 판정은 `series/base.py` 한 곳에 있다 — 계열이 좁힐 수 있어야 해서 거기 산다.
from core.render_vivlio.series.base import CHUNK_KEYS as _CHUNK_KEYS  # noqa: E402
from core.render_vivlio.series.base import para_like as _para_like    # noqa: E402


@bp.route("/api/book-studio/pagerules", methods=["GET", "POST"])
def api_pagerules():
    """마스터 페이지(`@page`) — 면에 걸리는 것(여백·머리·꼬리).

    단락 스타일로는 면을 못 건드린다. CSS 조판에서 `@page` 가 인디자인의
    마스터 페이지 자리다. 여기 적은 것은 계열 테마 **뒤에** 나가므로
    한 줄만 적어도 그 값만 바뀐다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    get = request.method == "GET"
    p = {} if get else (request.get_json(silent=True) or {})
    if not get:
        sel = str(p.get("sel") or "").strip()
        if len(sel) > 60 or any(c in sel for c in "{};<>"):
            return jsonify({"error": "이상한 면 이름"}), 400
        props = p.get("props")
        if not isinstance(props, dict):
            return jsonify({"error": "규칙이 없다"}), 400
        for k, v in props.items():
            if any(c in str(k) + str(v) for c in "{};<>"):
                return jsonify({"error": f"이상한 값: {k}: {v}"}), 400
            bad = _needs_unit(str(k), str(v))
            if bad:
                return jsonify({"error": bad}), 400
    d, meta = _book_dir(request.args.get("b") if get else p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    if get:
        return jsonify({"rules": cfg.section("page_rules") or {},
                        "hint": "왼쪽 면은 `:left`, 오른쪽 면은 `:right`, "
                                "빈칸은 모든 면입니다."})
    rules = dict(cfg.section("page_rules") or {})
    cur = dict(rules.get(sel) or {})
    for k, v in props.items():
        if v in ("", None):
            cur.pop(k, None)
        else:
            cur[k] = v
    if cur:
        rules[sel] = cur
    else:
        rules.pop(sel, None)
    # 같은 이력에 — ⌘Z 로 되돌아간다
    st = ed.push(cfg, {"op": "knob", "key": "page_rules",
                       "v": rules or None, "note": "마스터 페이지"})
    cfg.reload()
    return jsonify({"ok": True, "rules": cfg.section("page_rules") or {},
                    "history": _hist(st)})


@bp.route("/api/book-studio/box", methods=["POST"])
def api_box():
    """자유 배치 상자 — 넣기 · 옮기기 · 지우기.

    인디자인의 "프레임을 좌표로 놓기" 다. 흐름 한가운데 둔 상자가 **그 면을
    기준으로** 앉는다(실측 확인). 상자도 원고 자료라 편집 이력에 쌓인다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import box as bx
    from core.render_vivlio import edits as ed
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    ref = (p.get("ref") or "").strip()
    if not ref or any(c in ref for c in "/\\ \n") or ".." in ref:
        return jsonify({"error": "이상한 자리표"}), 400
    act = p.get("action")
    cfg = bookmod.load(d)
    cur, _raw = ed.preview(cfg)

    if act == "insert":
        base, at = _list_slot(ref, cur, cfg)
        if base is None:
            return jsonify({"error": "여기에는 넣을 수 없습니다 — "
                                     "지문·선지·본문 **한 줄**을 고르고 다시 해 보세요"}), 409
        b = bx.new(p.get("kind") or "text")
        # 그림상자 — **자산 폴더의 그 그림**만 받는다(경로를 받으면 안 된다).
        img = os.path.basename(str(p.get("img") or "").strip())
        if img:
            if not img.lower().endswith(IMG_OK) or "/" in img or ".." in img:
                return jsonify({"error": "그림 이름이 이상합니다"}), 400
            b["img"] = "assets/" + img
            b.pop("paras", None)
        if p.get("wrap") in ("left", "right"):
            b["wrap"] = p["wrap"]
            b["at"] = {"width": b["at"].get("width", "40mm")}
        st = ed.push(cfg, {"op": "insert", "ref": f"{base}.{at}", "v": b,
                           "note": "상자 넣기"})
        return jsonify({"ok": True, "ref": f"{base}.{at}",
                        "history": _hist(st)})

    block = ed.get(cur, ref)
    if not isinstance(block, dict) or block.get("t") != "box":
        return jsonify({"error": "상자가 아닙니다"}), 409
    if act == "delete":
        st = ed.push(cfg, {"op": "delete", "ref": ref, "note": "상자 지우기"})
        return jsonify({"ok": True,
                        "history": _hist(st)})
    if act == "style":
        # 상자 모양(바탕·테두리·둥근 모서리·그림자·투명도·회전) —
        # 인디자인의 개체 속성이다. **적은 것만** 받는다.
        b = json.loads(json.dumps(block))      # 사본에 고친다
        st = dict(b.get("style") or {})
        props = p.get("props")
        if not isinstance(props, dict) or not props:
            return jsonify({"error": "바꿀 모양이 없습니다"}), 400
        for k, v in props.items():
            if k not in bx.STYLE_KEYS:
                return jsonify({"error": f"모르는 항목: {k}"}), 400
            v = str(v or "").strip()
            if any(c in v for c in "{};<>\"'"):
                return jsonify({"error": f"이상한 값: {k}: {v}"}), 400
            if v:
                st[k] = v
            else:
                st.pop(k, None)
        if st:
            b["style"] = st
        else:
            b.pop("style", None)
        st2 = ed.push(cfg, {"op": "set", "ref": ref, "v": b, "note": "상자 모양"})
        return jsonify({"ok": True, "history": _hist(st2)})
    if act != "move":
        return jsonify({"error": f"모르는 동작: {act}"}), 400
    b = json.loads(json.dumps(block))
    at = dict(b.get("at") or {})
    for k in bx.AT_KEYS:
        if k in (p.get("at") or {}):
            v = bx._len(p["at"][k])
            if v:
                at[k] = v
            else:
                at.pop(k, None)
    b["at"] = at
    if "wrap" in p:
        if p["wrap"] in ("left", "right"):
            b["wrap"] = p["wrap"]
        else:
            b.pop("wrap", None)
    st = ed.push(cfg, {"op": "set", "ref": ref, "v": b, "note": "상자 옮기기"})
    return jsonify({"ok": True,
                    "history": _hist(st)})


@bp.route("/api/book-studio/export", methods=["POST"])
def api_export():
    """PDF 로 내보내기 — 조판본(RGB) 또는 인쇄 원고(CMYK).

    인디자인의 「내보내기」 자리다. 지금까지는 통합웹의 조판 카드에서만 됐는데,
    작업대에서 고치고 곧바로 뽑아 볼 수 있어야 한다.

    ⚠ **오래 걸린다**(전권 조판 20~50초, 인쇄 원고는 더). 그래서 진행 상황을
      돌려주고, 화면은 기다리는 동안 무엇을 하고 있는지 적는다.
    """
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    kind = p.get("kind") or "pdf"
    if kind not in ("pdf", "press"):
        return jsonify({"error": f"모르는 종류: {kind}"}), 400
    steps = ["build"] if kind == "pdf" else ["build", "print"]
    logs = []
    for st in steps:
        r = _run([d, st], timeout=1800)
        logs.append(r.stdout[-4000:])
        if r.returncode != 0:
            return jsonify({"error": (r.stderr or r.stdout)[-1200:],
                            "log": "\n".join(logs)}), 500
    from core.render_vivlio import book as bookmod
    cfg = bookmod.load(d)
    out = _last_pdf(cfg, d)
    return jsonify({"ok": True, "log": "\n".join(logs),
                    "pdf": os.path.basename(out) if out else None,
                    "note": ("인쇄 원고(CMYK)까지 만들었습니다"
                             if kind == "press" else "조판본 PDF 를 만들었습니다")})


@bp.route("/api/book-studio/table", methods=["POST"])
def api_table():
    """표 넣기·행·열 늘리고 줄이기.

    표도 **원고 자료**다 — 그래서 편집 이력에 연산으로 쌓인다(⌘Z 로 되돌아간다).
    자리는 고른 문항의 `blocks` 목록이다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    from core.render_vivlio import table as tbl
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    ref = (p.get("ref") or "").strip()
    if not ref or any(c in ref for c in "/\\ \n") or ".." in ref:
        return jsonify({"error": "이상한 자리표"}), 400
    act = p.get("action")
    cfg = bookmod.load(d)
    cur, _raw = ed.preview(cfg)

    if act == "insert":
        # 고른 자리가 든 **블록 목록**을 찾아 그 뒤에 넣는다
        base, at = _list_slot(ref, cur, cfg)
        if base is None:
            return jsonify({"error": "여기에는 넣을 수 없습니다 — "
                                     "지문·선지·본문 **한 줄**을 고르고 다시 해 보세요"}), 409
        cols = max(1, min(int(p.get("cols") or 2), 12))
        rows = max(1, min(int(p.get("rows") or 2), 60))
        st = ed.push(cfg, {"op": "insert", "ref": f"{base}.{at}",
                           "v": tbl.new(cols, rows, bool(p.get("head", True))),
                           "note": "표 넣기"})
        return jsonify({"ok": True, "ref": f"{base}.{at}",
                        "history": _hist(st)})

    # 행·열 늘리고 줄이기 — 표 블록 자체를 통째로 갈아 끼운다
    block = ed.get(cur, ref)
    if not isinstance(block, dict) or block.get("t") != "table":
        return jsonify({"error": "표가 아닙니다"}), 409
    b = json.loads(json.dumps(block))          # 사본
    rows = b.setdefault("rows", [])
    # 줄·칸은 **그 자리에** 넣고 뺀다(인디자인의 "위에 넣기 / 이 줄 지우기").
    # `at` 을 안 주면 예전처럼 맨 뒤다.
    at = p.get("at")
    at = None if at in (None, "") else int(at)
    if act in ("addrow", "delrow", "addcol", "delcol"):
        fn = {"addrow": tbl.add_row, "delrow": tbl.del_row,
              "addcol": tbl.add_col, "delcol": tbl.del_col}[act]
        try:
            fn(b, at)
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
    elif act == "widths":
        # 칸 너비 — 인디자인의 열 폭. 길이 값만 받는다.
        from core.render_vivlio import box as _bx
        ws = [_bx._len(x) for x in (p.get("widths") or [])]
        if not ws or any(not w for w in ws):
            return jsonify({"error": "칸 너비는 `30%` · `24mm` 처럼 적습니다"}), 400
        b["widths"] = ws
    elif act == "align":
        al = [x for x in (p.get("align") or [])
              if x in ("left", "center", "right", "justify")]
        if not al:
            return jsonify({"error": "정렬은 left·center·right 입니다"}), 400
        b["align"] = al
    elif act == "style":
        # 표 모양(괘선·안 여백·줄 높이·머리줄 바탕) — 인디자인의 표 스타일.
        st = dict(b.get("style") or {})
        props = p.get("props")
        if not isinstance(props, dict) or not props:
            return jsonify({"error": "바꿀 모양이 없습니다"}), 400
        for k, v in props.items():
            if k not in tbl.STYLE:
                return jsonify({"error": f"모르는 항목: {k}"}), 400
            v = str(v or "").strip()
            if any(c in v for c in "{};<>\"'"):
                return jsonify({"error": f"이상한 값: {k}: {v}"}), 400
            if v:
                st[k] = v
            else:
                st.pop(k, None)
        if st:
            b["style"] = st
        else:
            b.pop("style", None)
    elif act == "cellstyle":
        # 칸 하나의 모양 — 인디자인의 셀 스타일. 좌표는 머리줄이 0행이다.
        try:
            tbl.set_cell_style(b, p.get("r"), p.get("c"), p.get("props") or {})
        except (ValueError, TypeError, IndexError, KeyError) as e:
            return jsonify({"error": str(e) or "칸을 못 찾았습니다"}), 409
    elif act in ("merge", "unmerge"):
        # 인디자인의 셀 병합. 좌표는 **머리줄을 0행으로** 세는 화면과 같다.
        try:
            if act == "merge":
                tbl.merge(b, p.get("r0"), p.get("c0"), p.get("r1"), p.get("c1"))
            else:
                tbl.unmerge(b, p.get("r"), p.get("c"))
        except (ValueError, TypeError, IndexError, KeyError) as e:
            return jsonify({"error": str(e) or "합칠 수 없는 자리입니다"}), 409
    elif act == "delete":
        st = ed.push(cfg, {"op": "delete", "ref": ref, "note": "표 지우기"})
        return jsonify({"ok": True,
                        "history": _hist(st)})
    else:
        return jsonify({"error": f"모르는 동작: {act}"}), 400
    st = ed.push(cfg, {"op": "set", "ref": ref, "v": b, "note": "표 " + act})
    return jsonify({"ok": True,
                    "history": _hist(st)})


@bp.route("/api/book-studio/fonts")
def api_fonts():
    """이 책이 **쓸 수 있는 서체**.

    ## 왜 브라우저의 로컬 폰트 목록을 쓰지 않는가

    브라우저에도 설치 서체를 훑는 길(`queryLocalFonts`)이 있지만, 크로미움
    데스크톱에서만 되고 **인쇄에는 맞지 않는다.** PDF 에 들어가는 것은 이 책이
    **임베드한 서체**뿐이다 — 화면에만 있는 서체를 고르면 조판은 되는데 PDF 는
    딴 글씨가 된다. 그래서 서버가
      ① 이 책이 이미 싣는 서체와
      ② 이 기계에 있어 **더 실을 수 있는** 서체를
    갈라서 준다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import stage as stg
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    used, missing = [], []
    for f in (cfg.get("fonts") or []):
        name = f.get("name") or os.path.splitext(f.get("file", ""))[0]
        path = stg.find_font(f.get("file", ""))
        (used if path else missing).append(
            {"name": name, "file": f.get("file"), "ok": bool(path)})
    have = set()
    for dd in stg.FONT_DIRS:
        if not os.path.isdir(dd):
            continue
        for n in sorted(os.listdir(dd)):
            if n.lower().endswith((".otf", ".ttf", ".ttc")) and not n.startswith("."):
                have.add(n)
    return jsonify({"used": used, "missing": missing,
                    "available": sorted(have)[:600],
                    "dirs": list(stg.FONT_DIRS)})


@bp.route("/api/book-studio/thumbs")
def api_thumbs():
    """페이지 패널이 쓸 **실제 지면 그림** 목록.

    ## 왜 PDF 에서 뽑는가

    지면을 다시 그려 썸네일을 만들려면 전권을 조판해야 해서 몇 분이 든다.
    그런데 **마지막에 구운 PDF 가 이미 그 그림**이다 — 인디자인 페이지 패널도
    결국 조판된 면을 보여 준다. 그래서 PDF 에서 뽑는다(면당 수 ms).

    ⚠ 그래서 **마지막 조판본 기준**이다. 방금 고친 것은 다시 조판해야 그림에
      나온다. 화면에 그 사실을 적는다(안 적으면 옛 그림을 지금 것으로 오해한다).
    """
    import glob
    from core.render_vivlio import book as bookmod
    d, meta = _book_dir(request.args.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    cfg = bookmod.load(d)
    pdf = _last_pdf(cfg, d)
    if not pdf:
        return jsonify({"pages": 0, "note": "아직 조판한 PDF 가 없습니다"})
    try:
        import fitz
        doc = fitz.open(pdf)
        n = doc.page_count
        doc.close()
    except Exception as e:
        return jsonify({"error": f"PDF 를 못 열었습니다: {e}"}), 500
    return jsonify({"pages": n, "pdf": os.path.basename(pdf),
                    "at": int(os.path.getmtime(pdf)),
                    "bid": meta["bid"]})


def _last_pdf(cfg, d):
    """이 책이 마지막으로 구운 내지 PDF. 없으면 폴더에서 가장 새 것."""
    import glob
    try:
        p = cfg.out_pdf("")
        if os.path.exists(p):
            return p
    except Exception:
        pass
    cands = [x for x in glob.glob(os.path.join(d, "*.pdf"))
             if "인쇄용" not in x and "CMYK" not in x]
    return max(cands, key=os.path.getmtime) if cands else None


@bp.route("/book-studio/thumb/<bid>/<int:n>.png")
def thumb(bid, n):
    """면 하나의 그림. 만든 것은 `build/thumbs/` 에 둔다(다시 안 그린다).

    `?dpi=` 로 크기를 고른다(24~160). 페이지 패널은 작은 것(24)을 쓰고,
    **먼 면으로 뛸 때**는 큰 것을 지면 자리에 잠깐 깔아 둔다 — 조판 엔진이
    그 면까지 그리는 데 시간이 걸려서, 그동안 빈 판을 보여 주지 않으려고.
    """
    from core.render_vivlio import book as bookmod
    d, meta = _book_dir(bid)
    if not d:
        return abort(404)
    cfg = bookmod.load(d)
    pdf = _last_pdf(cfg, d)
    if not pdf or n < 1:
        return abort(404)
    tdir = os.path.join(_build_dir(d), "thumbs")
    os.makedirs(tdir, exist_ok=True)
    try:
        dpi = max(24, min(int(request.args.get("dpi") or 24), 160))
    except ValueError:
        dpi = 24
    stamp = int(os.path.getmtime(pdf))
    out = os.path.join(tdir, f"{stamp}_{n}_{dpi}.png")
    if not os.path.exists(out):
        try:
            import fitz
            doc = fitz.open(pdf)
            if n > doc.page_count:
                return abort(404)
            doc[n - 1].get_pixmap(dpi=dpi).save(out)
            doc.close()
        except Exception:
            return abort(500)
    return send_from_directory(tdir, os.path.basename(out))


@bp.route("/api/book-studio/cmyk", methods=["POST"])
def api_cmyk():
    """화면 색(16진) → **인쇄 CMYK**.

    내지는 종이에 찍히므로 색은 CMYK 로 읽혀야 한다. 화면의 `#908400` 이
    인쇄에서 몇 %인지 모르면 색을 정할 수가 없다.

    ⚠ 눈대중 공식을 쓰지 않는다. 실제 마감(`prepress.py`)이 쓰는 **그 ICC
      프로파일**(Japan Color 2001 Coated 우선)로 변환한다 — 공식으로 낸 숫자는
      인쇄물과 다르고, 다르면 없느니만 못하다.

    ⚠ 먹으로 빠지는 색은 CMYK 가 아니라 **K 단색**이다. 본문 먹·품사·발음기호는
      마감 때 DeviceGray 로 바꾼다(리치 블랙으로 4도가 겹치면 글자가 번진다).
      그런 색은 그렇게 알려 준다.
    """
    from core.render_vivlio import prepress
    p = request.get_json(silent=True) or {}
    colors = p.get("colors")
    if not isinstance(colors, list) or len(colors) > 200:
        return jsonify({"error": "색 목록이 없다"}), 400

    gray = {k.lower(): v for k, v in prepress.DEFAULT_GRAY_MAP.items()}
    out, tr = {}, None
    prof = prepress.find_profile()
    if prof:
        try:
            from PIL import Image, ImageCms
            tr = ImageCms.buildTransform(
                ImageCms.createProfile("sRGB"), ImageCms.getOpenProfile(prof),
                "RGB", "CMYK",
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
        except Exception:
            tr = None
    for hx in colors:
        h = str(hx).strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", h):
            continue
        if h in gray:
            out[hx] = {"k": round(gray[h] * 100), "gray": True}
            continue
        if tr is None:
            continue
        from PIL import Image, ImageCms
        rgb = tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
        c, m, y, k = ImageCms.applyTransform(
            Image.new("RGB", (1, 1), rgb), tr).getpixel((0, 0))
        out[hx] = {"c": round(c * 100 / 255), "m": round(m * 100 / 255),
                   "y": round(y * 100 / 255), "k": round(k * 100 / 255)}
    return jsonify({"cmyk": out,
                    "profile": os.path.basename(prof) if prof else None})


@bp.route("/api/book-studio/find", methods=["POST"])
def api_find():
    """전권 검색 · 바꾸기 — **지면이 아니라 원고에서** 찾는다.

    지면에서 찾으면 지금 그려진 면만 보게 된다. 원고(data + 편집 이력)를 훑으면
    전권이 대상이고, 바꾸기는 **되돌릴 수 있는 편집 연산**으로 쌓인다.
    """
    from core.render_vivlio import book as bookmod
    from core.render_vivlio import edits as ed
    from core.render_vivlio import refs as rf
    from core.render_vivlio import richtext as rt
    p = request.get_json(silent=True) or {}
    d, meta = _book_dir(p.get("b"))
    if not d:
        return jsonify({"error": "모르는 책"}), 404
    q = p.get("q") or ""
    if not q:
        return jsonify({"error": "찾을 말이 없다"}), 400
    cfg0 = bookmod.load(d)
    # ⚠ 원고 자료 파일이 없는 계열(포켓북)은 찾을 대상이 없다. 조용히 0곳이
    #   나오면 "없는 말" 인지 "못 찾는 책" 인지 알 수 없다.
    if not os.path.exists(ed.data_path(cfg0)):
        return jsonify({"error": "이 교재는 원고에서 바로 조판해 "
                                 "여기서 찾을 원고 자료가 없습니다",
                        "kind": "nodata"}), 409
    # 정규식(인디자인의 GREP). 틀린 식은 **무엇이 틀렸는지** 말해 준다 —
    # 조용히 0건이 나오면 글이 없는 건지 식이 틀린 건지 알 수 없다.
    rx = None
    if p.get("regex"):
        try:
            rx = re.compile(q, 0 if p.get("case") else re.I)
        except re.error as e:
            return jsonify({"error": f"정규식이 틀렸습니다: {e}"}), 400
    cfg = bookmod.load(d)
    cur, _raw = ed.preview(cfg)
    # 자리표를 심는 것과 **같은 자리들**만 찾는다 — 찾은 것을 고칠 수 있어야 하니까
    hits = _scan(cur, q, bool(p.get("case")), rx=rx)
    rep = p.get("replace")
    if rep is None:
        return jsonify({"hits": hits[:300], "total": len(hits)})
    if not hits:
        return jsonify({"ok": True, "changed": 0})
    only = set(p.get("refs") or []) or None
    n = 0
    for h in hits:
        if only and h["ref"] not in only:
            continue
        old = ed.get(cur, h["ref"])
        txt = rt.to_text(old)
        if rx is not None:
            try:
                new = rx.sub(rep, txt)
            except re.error as e:
                return jsonify({"error": f"바꿀 말이 틀렸습니다: {e}"}), 400
        else:
            new = txt.replace(q, rep) if p.get("case") else _ireplace(txt, q, rep)
        if new == txt:
            continue
        ed.push(cfg, {"op": "set", "ref": h["ref"],
                      "v": rt.from_text(new, like=old), "note": "바꾸기"})
        n += 1
    st = ed.read(cfg)
    return jsonify({"ok": True, "changed": n,
                    "history": _hist(st)})


def _ireplace(s, a, b):
    import re as _re
    return _re.sub(_re.escape(a), lambda m: b, s, flags=_re.I)


# 서식 조각이 갖는 열쇠 — 글자와 굵기·밑줄·기울임, 그리고 역할(`k`).
_RICH_KEYS = {"t", "b", "u", "i", "k"}


def _is_rich_seg(x):
    """`{"t": "글", "u": true}` 인가.

    ⚠ `t` 하나로 가르면 안 된다. **특강은 `t` 를 '블록 종류'로 쓴다**
      (`{"t": "passage", "r": […]}`). 그래서 예전 판정은 특강의 모든 블록을
      서식 조각으로 보고 건너뛰었고, 찾기가 그 계열에서 **한 건도 못 찾았다**
      (오류가 아니라 0건이라 더 안 보였다). 다른 열쇠가 붙어 있으면 조각이
      아니라 자료다.
    """
    return (isinstance(x, dict) and isinstance(x.get("t"), str)
            and set(x) <= _RICH_KEYS)


def _scan(data, q, case=False, path="", out=None, depth=0, rx=None):
    """글자가 들어 있는 자리를 훑는다. 자리표와 같은 점 경로를 돌려준다."""
    from core.render_vivlio import richtext as rt
    if out is None:
        out = []
    if depth > 12 or len(out) > 2000:
        return out
    def hit(text):
        if rx is not None:
            return bool(rx.search(text))
        return (q in text) if case else (q.lower() in text.lower())
    if isinstance(data, str):
        if hit(data):
            out.append({"ref": path, "text": data[:120]})
        return out
    if isinstance(data, dict):
        if _is_rich_seg(data):                               # 서식 조각
            return out
        for k, v in data.items():
            _scan(v, q, case, f"{path}.{k}" if path else k, out, depth + 1, rx)
        return out
    if isinstance(data, list):
        # 서식 조각 목록이면 **그 목록 전체**가 한 자리다
        if data and all(isinstance(x, (str, dict)) for x in data) \
                and any(_is_rich_seg(x) for x in data):
            t = rt.plain(data)
            if hit(t):
                out.append({"ref": path, "text": t[:120]})
            return out
        for i, v in enumerate(data):
            _scan(v, q, case, f"{path}.{i}", out, depth + 1, rx)
    return out


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
    from core.render_vivlio import design_ops as dops
    OPNAME = {"set": "글 고침", "split": "문단 나눔", "merge": "문단 합침",
              "insert": "문단 넣음", "delete": "문단 지움",
              "style": "스타일", "knob": "값", "css": "직접 CSS"}
    rows = []
    for i, o in enumerate(st["ops"]):
        kind = o.get("op")
        rows.append({
            "i": i, "op": kind, "ref": o.get("ref"),
            # 이력은 사람이 읽는 자리다 — `set`·`style` 같은 말은 우리 용어다
            "label": OPNAME.get(kind, kind or ""),
            "what": (dops.label(o) if kind in ed.DESIGN_OPS else (o.get("ref") or "")),
            "design": kind in ed.DESIGN_OPS,
            "at": o.get("at", ""), "note": o.get("note", ""),
            "applied": i < st["head"]})
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
    p = os.path.join(_build_dir(d), "refs.json")
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
# 브라우저용으로 한 번 묶어 둔 조판 엔진 (`webcore/` — `npm` 없이도 이 파일만 있으면 된다)
CORE = os.path.join(REPO, "core", "render_vivlio", "webcore", "dist")


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


# 지면이 사는 **빈 문서**. 여기 CSS 는 이것뿐이고, 앱 스타일시트는 하나도 안 문다.
FRAME_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>지면</title>
<style>
/* ⚠ 여기에 **전칭 선택자를 쓰지 말 것.** 조판 결과가 이 문서 안에 그려지므로
   `*` 규칙 하나가 판면을 바꾼다(실제로 앱 리셋 때문에 본문 단이 167mm →
   118mm 로 좁아진 적이 있다). 아래 규칙은 전부 **우리가 심은 표식**에만 건다. */
html, body { margin: 0; padding: 0; background: #6b6b6b; }
#viv { min-height: 100vh; }

/* 고칠 수 있는 자리 — `vrefN` 은 우리 자리표라 교재 CSS 와 안 부딪힌다 */
[class*="vref"] { cursor: default; }
body.tool-text [class*="vref"], body.tool-para [class*="vref"] { cursor: text; }
body.tool-text [class*="vref"]:hover, body.tool-para [class*="vref"]:hover {
  outline: 1px dashed rgba(120,140,255,.6); outline-offset: 2px;
  background: rgba(120,140,255,.07);
}
/* 고치는 중 — **겉모습은 그대로 두고** 여기라는 것만 알린다.
   예전에는 바탕을 노랗게 칠하고 글꼴을 고정폭으로 바꿨는데, 그러면 누를 때마다
   글이 딴것처럼 보여서 조판을 보는 눈이 흐트러진다. 인디자인은 커서만 깜빡인다. */
/* ── 눈금자 (인디자인의 상단·좌측 눈금자) ─────────────────────────
   지면 위에 덧그린다. mm 단위로 5mm 마다 눈금, 10mm 마다 굵은 눈금.
   ⚠ 조판에 영향을 주면 안 되므로 `pointer-events:none` 이고 인쇄에 안 나간다. */
#viv.show-ruler [data-vivliostyle-page-container]::before {
  content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 8;
  background-image:
    repeating-linear-gradient(to right,
      rgba(0,0,0,.30) 0 0.2mm, transparent 0.2mm 10mm),
    repeating-linear-gradient(to right,
      rgba(0,0,0,.16) 0 0.15mm, transparent 0.15mm 5mm),
    repeating-linear-gradient(to bottom,
      rgba(0,0,0,.30) 0 0.2mm, transparent 0.2mm 10mm),
    repeating-linear-gradient(to bottom,
      rgba(0,0,0,.16) 0 0.15mm, transparent 0.15mm 5mm);
  background-size: 100% 4mm, 100% 2.5mm, 4mm 100%, 2.5mm 100%;
  background-position: left top, left top, left top, left top;
  background-repeat: no-repeat;
}

/* ── 안내선 — **진짜 요소**로 그린다(`.ide-gd`) ─────────────────
   ⚠ 예전에는 눈금자와 **같은 `::before`** 를 써서, 둘을 같이 켜면 눈금자가
     통째로 사라졌다(나중 규칙이 이긴다). 그리고 배경 그림이라 잡아 끌 수가
     없었다 — 인디자인은 눈금자에서 끌어다 놓는다. */
#viv .ide-gd { display: none; }
#viv.show-guide .ide-gd { display: block; }

/* ── 보기 보조 (인디자인의 안내선·재단선 보기) ────────────────────
   ⚠ 이건 **보기 위한 것**이라 조판에 영향을 주면 안 된다. 그래서 지면 위에
     덧그리기만 하고(`pointer-events:none`), 인쇄에는 안 나간다. */
#viv.show-margin [data-vivliostyle-page-container]::after,
#viv.show-bleed [data-vivliostyle-page-container]::after {
  content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 9;
}
#viv.show-bleed [data-vivliostyle-page-container]::after {
  outline: 1px dashed rgba(255,0,0,.55); outline-offset: -3mm;
}
#viv.show-margin [data-vivliostyle-page-container] > div > div:first-child {
  outline: 1px dashed rgba(0,140,255,.5);
}
#viv.show-base [data-vivliostyle-page-container] {
  background-image: repeating-linear-gradient(
    to bottom, rgba(0,160,255,.16) 0 1px, transparent 1px var(--base, 4.585mm));
}
.ide-editing {
  outline: 1px solid rgba(108,140,255,.85); outline-offset: 1px;
  caret-color: #2b62ff;
}
</style>
<script src="/book-studio/core/vivlio-core.js"></script>
</head><body><div id="viv"></div></body></html>
"""


@bp.route("/book-studio/frame")
def frame():
    """조판 결과가 사는 **빈 문서**.

    ## 왜 따로 문서를 두는가

    예전에는 작업대 화면 안 `div` 에 바로 조판했다. 그러면 **앱 CSS 가 조판에
    얹힌다** — `main.css` 첫 줄의 `*{box-sizing:border-box}` 가 Vivliostyle 의
    판면 래퍼까지 먹어 여백이 두 번 깎였고, 본문 단이 167mm 여야 하는데
    118mm 로 나왔다. 폭만 좁은 게 아니라 **줄바꿈도 면 나눔도 달라졌다** —
    디자인을 보라고 만든 화면이 다른 판을 보여 주고 있었던 것이다.

    같은 출처(same-origin)라 화면 쪽에서 이 문서 안을 그대로 만질 수 있다.
    클릭 편집도 선택 영역도 다 된다 — 잃는 것은 없고 오염만 끊긴다.
    """
    return Response(FRAME_HTML, mimetype="text/html; charset=utf-8")


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
    return send_from_directory(_build_dir(d), sub)
