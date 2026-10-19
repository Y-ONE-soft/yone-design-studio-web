# -*- coding: utf-8 -*-
"""카탈로그 — **디렉토리(라인업) → 틀 → 디자인(템플릿 카드).**

    디렉토리(dir)  교재 갈래. 두 묶음(`group`) — OJT 라인업 8종(분석본·워크북·포켓북·학교별 변형문제·동형모의고사·직전보충·리테·클리닉)
                   · 교재 폴더 계열(프리미엄북·특강교재·단어장·중등부) + 기타. `catalog/dirs.json` 으로 늘어난다.
                   틀은 디렉토리 하나에 속하고(`catalog.json` 의 `dir`), 화면에서 옮길 수 있다.
    틀(series)     라인업 안의 한 갈래(워크북 · 분석본 · 포켓북 …).
    디자인(design) 그 틀의 템플릿 카드 — 편집기 제작(units.json, made: editor) 또는 PDF 등록(참고/reference.pdf, made: pdf).

    /catalog                              디렉토리 목록
    /catalog/dir/<dir>                    그 디렉토리의 틀들 (+ 틀 옮기기)
    /catalog/<series>                     → 관리 그 라인업(/projects?dir=)
    /catalog/<series>/<design>            → 템플릿 보기(/design/<틀>/<디자인>)
    POST /api/catalog/series/<series>/dir 틀을 다른 디렉토리로 옮긴다 {"dir": id}
    POST /api/catalog/dirs                디렉토리 추가 {name, en, desc, icon, color, group} — 기타 앞에 끼운다
    PUT  /api/catalog/dirs/<dir>          디렉토리 수정 (같은 필드; id·순서·안의 틀은 그대로)
    DELETE /api/catalog/dirs/<dir>        디렉토리 삭제 — 안의 틀은 기타로. 기타는 못 지운다
    DELETE /api/catalog/design/<series>/<design>
    POST /api/catalog/design/<series>/<design>/origin  편집기 템플릿에 원본 PDF 붙이기 (file 또는 from=<같은 틀 PDF 등록 카드>)

폴더:
    catalog/dirs.json                           디렉토리 목록(순서·이름·설명·색)
    catalog/catalog.json                        틀 목록(이름·설명·루트 폴더·dir)
    catalog/<series>/designs/<id>/design.json   {name, desc, source, date, made}
    catalog/<series>/designs/<id>/config.json   판형 · 서체
    catalog/<series>/designs/<id>/preview_N.png 견본 사진(보기용)

(예전 조판 엔진으로 책을 만들던 길 — 원고 넣기 · 책 목록 · 책에서 디자인 등록 · 견본 다시 찍기 · PDF 판정 화면 — 은 2026-10-19 지웠다.)
"""
import json
import os
import re
import shutil
import threading
import unicodedata as u

from flask import (Blueprint, abort, jsonify, redirect, render_template, request,
                   send_from_directory)

bp = Blueprint("catalog", __name__)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.environ.get("YONE_CATALOG_DIR") or os.path.join(REPO, "catalog")   # 컨테이너: 볼륨
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")


def _nfc(s):
    return u.normalize("NFC", s or "")


def _studio():
    from core.studio import studio_root
    return studio_root()


# ── 디렉토리 · 틀 ───────────────────────────────────────────────
DEFAULT_DIR = "etc"                      # 어느 갈래도 아닌 틀은 "기타"
_META_LOCK = threading.Lock()


DIR_GROUPS = ("ojt", "folder")            # 묶음: OJT 라인업 8종 · 교재 폴더 계열
DIR_COLORS = ("#3b7ddd", "#2fa47a", "#7b6cf6", "#f0863b", "#e0567b", "#2bb3c0", "#c9a227", "#8b91a5")


def _dirs():
    """디렉토리 목록 — `catalog/dirs.json` 순서 그대로."""
    return json.load(open(os.path.join(CATALOG, "dirs.json"), encoding="utf-8"))


def _save_dirs(dirs):
    """순서 그대로 저장. 기타는 항상 맨 뒤."""
    dirs = [d for d in dirs if d["id"] != DEFAULT_DIR] + [d for d in dirs if d["id"] == DEFAULT_DIR]
    for d in dirs:
        d.pop("no", None)
    p = os.path.join(CATALOG, "dirs.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dirs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return dirs


def _new_dir_id(en, taken):
    """영문 라벨을 슬러그로, 없거나 겹치면 dir1·dir2…"""
    base = re.sub(r"[^a-z0-9]+", "-", (en or "").lower()).strip("-")[:24]
    if base and base[0].isalpha() and base not in taken and base != "dir":
        return base
    n = 1
    while f"dir{n}" in taken:
        n += 1
    return f"dir{n}"


def _dir_of(meta, ids=None):
    """틀이 속한 디렉토리 id. 적혀 있지 않거나 모르는 id 면 기타."""
    ids = ids if ids is not None else {d["id"] for d in _dirs()}
    return meta.get("dir") if meta.get("dir") in ids else DEFAULT_DIR


def _meta():
    return json.load(open(os.path.join(CATALOG, "catalog.json"), encoding="utf-8"))


def _save_meta(meta):
    p = os.path.join(CATALOG, "catalog.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


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
    out.sort(key=lambda i: i.get("date") or "")          # 등록한 날 순(같은 날은 위 순서) — 폴더 이름은 번호가 아니다
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


def _readiness(cfg, ddir=None):
    """이 디자인으로 지금 책을 만들 수 있나 — 서체 · 바깥 경로 · **디자인 폴더 안의 아트워크**.

    틀은 자기 재료를 디자인 폴더(`assets/`·`참고/`)에 갖고 있어야 한다. 바깥 경로
    (`${STUDIO}`·`~`)는 다른 기기에 없기 마련이라 그대로 "부족"이고, 디자인 폴더 상대경로는
    실제로 파일이 있는지 본다. 자산 조각(`assets.jobs`)이 이미 잘려 있으면 원본 PDF 는
    없어도 된다 — 원본은 조각을 다시 자를 때만 필요하다.
    """
    from core.units.fonts import find_font
    missing = []
    for f in cfg.get("fonts") or []:
        name = f["file"] if isinstance(f, dict) else f
        if find_font(name) is None:
            missing.append(name)
    ext = []
    for m in re.findall(r'"((?:\$\{STUDIO\}|~/)[^"]+)"', json.dumps(cfg, ensure_ascii=False)):
        p = os.path.expanduser(m.replace("${STUDIO}", _studio()))
        if not os.path.exists(p):
            ext.append(m)
    if ddir:
        ext += _local_artwork_missing(cfg, ddir)
    return {"fonts_missing": missing, "paths_missing": ext}


def _local_artwork_missing(cfg, ddir):
    """디자인 폴더 기준 상대경로 아트워크 중 없는 것."""
    out = []
    is_rel = lambda v: isinstance(v, str) and v and not v.startswith(("${", "~", "/"))
    a = cfg.get("assets") or {}
    if isinstance(a, dict):
        adir = os.path.join(ddir, a.get("dir") or "assets")
        have = set(os.listdir(adir)) if os.path.isdir(adir) else set()
        jobs = [j for j in (a.get("jobs") or []) if isinstance(j, dict) and j.get("name")]
        cut = [j["name"] for j in jobs if not any(f.startswith(j["name"] + ".") for f in have)]
        if cut:
            for k in ("src_pdf", "cover_pdf"):
                v = a.get(k)
                if is_rel(v) and not os.path.exists(os.path.join(ddir, v)):
                    out.append(f"{v}  (자산 {', '.join(cut)} 을 잘라낼 원본)")
    f = cfg.get("finish") or {}
    if isinstance(f, dict):
        v = f.get("art_pdf")
        if is_rel(v) and not os.path.exists(os.path.join(ddir, v)):
            out.append(f"{v}  (간지 아트워크)")
        for key in ("inserts", "append"):
            for it in f.get(key) or []:
                v = it.get("pdf") if isinstance(it, dict) else None
                if is_rel(v) and not os.path.exists(os.path.join(ddir, v)) and v not in out:
                    out.append(v)
    return out


def template_info(series):
    meta = _meta().get(series)
    if not meta:
        return None
    designs = _designs(series)
    cfg = _design_cfg(series, designs[0]["id"]) if designs else None
    r = _readiness(cfg, _ddir(series, designs[0]["id"])) if cfg else {"fonts_missing": [], "paths_missing": []}
    ready = meta.get("ready", "auto")
    if ready == "auto" and (r["fonts_missing"] or r["paths_missing"] or not designs):
        ready = "blocked"
    dirs = {d["id"]: d for d in _dirs()}
    did = _dir_of(meta, set(dirs))
    return {"series": series, "name": meta["name"], "desc": meta.get("desc", ""),
            "root": meta.get("root", series), "ready": ready, "designs": designs,
            "dir": did, "dir_name": dirs[did]["name"] if did in dirs else did,
            "pipeline": meta.get("pipeline"), "fields": meta.get("fields") or [],
            "slot_hint": meta.get("slot_hint", ""), "manuscript": meta.get("manuscript", True),   # false = 원고 넣는 틀이 아님(표지 등)
            "fonts_missing": r["fonts_missing"], "paths_missing": r["paths_missing"],
            "page": (cfg or {}).get("page")}


def templates():
    return [t for t in (template_info(s) for s in _meta()) if t]


def directories():
    """디렉토리마다 그 안의 틀을 붙여 돌려준다 (dirs.json 순서)."""
    ts = templates()
    return [{**d, "templates": [t for t in ts if t["dir"] == d["id"]]} for d in _dirs()]


# ── 화면 ────────────────────────────────────────────────────────
@bp.route("/catalog")
def gallery():
    return render_template("catalog.html", dirs=directories(), colors=DIR_COLORS, active_nav="틀")


@bp.route("/catalog/dir/<did>")
def dir_page(did):
    dirs = directories()
    d = next((x for x in dirs if x["id"] == did), None)
    if not d:
        abort(404)
    return render_template("catalog_dir.html", d=d, dirs=dirs, active_nav="틀")


@bp.route("/api/catalog/dirs")
def api_dirs():
    return jsonify(directories())


@bp.route("/api/catalog/series/<series>/dir", methods=["POST"])
def series_move(series):
    """틀을 다른 디렉토리로 옮긴다 — catalog.json 의 `dir` 만 바꾼다."""
    did = ((request.get_json(silent=True) or {}).get("dir") or request.form.get("dir") or "").strip()
    dirs = {d["id"]: d for d in _dirs()}
    if did not in dirs:
        return jsonify({"error": "모르는 디렉토리"}), 400
    with _META_LOCK:
        meta = _meta()
        if series not in meta:
            return jsonify({"error": "모르는 틀"}), 404
        meta[series]["dir"] = did
        _save_meta(meta)
    return jsonify({"ok": True, "series": series, "dir": did, "dir_name": dirs[did]["name"]})


@bp.route("/api/catalog/dirs", methods=["POST"])
def dir_add():
    b = request.get_json(silent=True) or request.form
    name = _nfc(b.get("name", "")).strip()
    if not name:
        return jsonify({"error": "디렉토리 이름을 적어야 한다"}), 400
    en = _nfc(b.get("en", "")).strip().upper()
    color = (b.get("color") or "").strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
        color = DIR_COLORS[0]
    icon = _nfc(b.get("icon", "")).strip()[:4] or "📁"
    with _META_LOCK:
        dirs = _dirs()
        if any(d["name"] == name for d in dirs):
            return jsonify({"error": "같은 이름의 디렉토리가 있다"}), 400
        d = {"id": _new_dir_id(en, {x["id"] for x in dirs}), "name": name, "en": en,
             "icon": icon, "color": color, "desc": _nfc(b.get("desc", "")).strip(),
             "group": b.get("group") if b.get("group") in DIR_GROUPS else "folder"}
        dirs.append(d)                 # _save_dirs 가 기타를 뒤로 보낸다
        _save_dirs(dirs)
    return jsonify({"ok": True, "dir": d})


@bp.route("/api/catalog/dirs/<did>", methods=["PUT"])
def dir_edit(did):
    """이름·영문·설명·아이콘·색만 바꾼다. id·순서·안의 틀은 그대로."""
    b = request.get_json(silent=True) or request.form
    name = _nfc(b.get("name", "")).strip()
    if not name:
        return jsonify({"error": "디렉토리 이름을 적어야 한다"}), 400
    color = (b.get("color") or "").strip()
    with _META_LOCK:
        dirs = _dirs()
        d = next((x for x in dirs if x["id"] == did), None)
        if not d:
            return jsonify({"error": "모르는 디렉토리"}), 404
        if any(x["name"] == name and x["id"] != did for x in dirs):
            return jsonify({"error": "같은 이름의 디렉토리가 있다"}), 400
        d.update({"name": name, "en": _nfc(b.get("en", "")).strip().upper(), "desc": _nfc(b.get("desc", "")).strip(),
                  "icon": _nfc(b.get("icon", "")).strip()[:4] or d.get("icon") or "📁",
                  "color": color if re.match(r"^#[0-9a-fA-F]{6}$", color) else d.get("color", DIR_COLORS[0]),
                  "group": b.get("group") if b.get("group") in DIR_GROUPS else d.get("group", "folder")})
        _save_dirs(dirs)
    return jsonify({"ok": True, "dir": d})


@bp.route("/api/catalog/dirs/<did>", methods=["DELETE"])
def dir_del(did):
    if did == DEFAULT_DIR:
        return jsonify({"error": "기타는 지울 수 없다 — 갈래 없는 틀이 모이는 곳"}), 400
    with _META_LOCK:
        dirs = _dirs()
        if not any(d["id"] == did for d in dirs):
            return jsonify({"error": "모르는 디렉토리"}), 404
        meta = _meta()
        moved = [k for k, v in meta.items() if v.get("dir") == did]
        for k in moved:
            meta[k]["dir"] = DEFAULT_DIR
        if moved:
            _save_meta(meta)
        _save_dirs([d for d in dirs if d["id"] != did])
    return jsonify({"ok": True, "moved": moved})


@bp.route("/catalog/<series>")
def series_page(series):
    """예전 틀 화면 — 관리의 그 라인업으로"""
    t = template_info(series)
    if not t:
        abort(404)
    return redirect(f"/projects?dir={t['dir']}")


@bp.route("/catalog/<series>/<design>")
def design_page(series, design):
    """예전 원고 넣기 화면 — 템플릿 보기로"""
    if not _ID.match(design):
        abort(404)
    return redirect(f"/design/{series}/{design}")


@bp.route("/catalog/master/<series>/<design>/<name>")
def master_img(series, design, name):
    if not _ID.match(design) or not re.match(r"^master_\d+\.png$", name):
        abort(404)
    return send_from_directory(_ddir(series, design), name)


def _design_pdf(series, design):
    """디자인의 기준 PDF — 디자인 폴더의 reference.pdf(참고/ 포함)."""
    d = _ddir(series, design)
    for c in (os.path.join(d, "reference.pdf"), os.path.join(d, "참고", "reference.pdf")):
        if os.path.exists(c):
            return c
    return None


def _origin_pdf(series, design):
    """편집기 템플릿이 따라 만든 원본 PDF(참고/원본.pdf) — 템플릿 보기의 「원본 페이지 차례」. 없으면 None.
    다시 등록해도 지우지 않는다(register_design 은 reference.pdf · 견본 그림만 새로 그린다)."""
    p = os.path.join(_ddir(series, design), "참고", "원본.pdf")
    return p if os.path.exists(p) else None


def design_pages(series, design):
    """기준 PDF 의 총 면수 (없으면 0). 상세 화면이 지면 전체를 늘어놓을 때 쓴다."""
    pdf = _design_pdf(series, design)
    if not pdf:
        return 0
    try:
        import fitz
        return fitz.open(pdf).page_count
    except Exception:
        return 0


def _in_head(b, H):
    """머리 띠의 글덩어리 — 머리 10% 안에서 시작해 12% 안에서 끝난다. 끝까지 10% 안이어야 하던 때는 조금 아래 붙은
    이름표 칸(배재1 포켓북 분석 면 '능률(오) 2과 본문1' 8.9~10.8%)을 못 읽어, 그 면이 앞 면 이름을 이어받았다(2026-10-12)."""
    return b[1] < H * 0.10 and b[3] < H * 0.12


def _page_labels(page):
    """러닝 요소의 이름표 — 머리 10%·바닥 7% 안의 짧은 라벨(한글·대문자 위주). 본문 문장(영어 소문자)은 뺀다."""
    W, H = page.rect.width, page.rect.height
    out = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, t = b[:5]
        if not (_in_head(b, H) or y0 > H * 0.93):
            continue
        out += _page_labels_in(t)
    return out


def _page_labels_in(t):
    """글덩어리 하나에서 이름표 후보 — 숫자·기호·띄어쓰기를 뺀 짧은 줄."""
    out = []
    for line in t.split("\n"):
        t2 = re.sub(r"[\d\s.·:/()\-~|_,'\"!?]+", "", line)
        if not t2 or len(t2) > 20 or sum(c.islower() for c in t2) > len(t2) * 0.5:   # 20: '능률보카수능고난도어휘PRACTICE'(19)
            continue
        out.append(t2)
    return out


# 틀별 구성 규칙 — 면 머리(위 22%) 글에서 이 순서로 처음 맞는 것이 그 면의 구성. 없으면 직전 구성이 이어진다.
# 워크북은 러닝 헤드에 STEP 이름이 있어 규칙 없이 된다.
SECTION_RULES = {
    "blackbook": [(r"Exercise", "문항 (Exercise)"), (r"정답\s*및\s*해설", "정답 및 해설"),
                  (r"Unit\s*\d+|\d+과\s*본문", "원문 지문 · 연관어휘")],
    "whitebook": [(r"DAY\s*\d+\s*EXERCISE", "DAY 실전문제 (EXERCISE)"), (r"^정답", "정답")],
    "pocketbook": [(r"FLOW\s*NOTE", "요약노트 FLOW NOTE"), (r"암기\s*TEST", "암기 TEST"), (r"^정답", "정답"),
                   (r"어휘\s*고교기본|Unit\s*\d+", "어휘 목록"), (r"주제\s*:|본문\s*\d|모의고사\s*\d+|\d강\s*(\d+|분석)", "지문 분석")],
    "final": [(r"문장\s*삽입", "문장 삽입 / 순서 배열"), (r"문장\s*배열", "문장 배열"),
              (r"중요\s*어휘", "중요 어휘 / 요약문"), (r"내용\s*요약", "내용 요약")],
    "special": [(r"WEEK\s*VOCABULARY", "WEEK 어휘"), (r"APPENDIX|부록", "부록 어근·접두사·접미사"),
                (r"구문\s*연습문제", "구문 연습문제"), (r"어법\s*연습문제", "어법 연습문제"),
                (r"LESSON", "구문·어법 LESSON 개념"), (r"WEEK\s*READING|EXAMPLE", "WEEK 독해 예제"),
                (r"배경지식\s*노트", "배경지식 노트"), (r"ANSWERS|정답\s*및", "정답")],
    "hankkeut": [(r"빠른\s*정답", "빠른 정답"), (r"문항별\s*정답|정답\s*및\s*풀이", "문항별 정답 및 풀이"),
                 (r"PART\s*0?1|서답형\s*\d+제", "서답형 문항")],
    "seseo": [(r"중요문장|PICK", "PART 1 중요문장 분석"), (r"대표유형", "PART 2 대표유형 풀이 전략"),
              (r"§P\d|연습\s*\d", "PART 2 연습"), (r"실전문제|§B\d|§Q\d", "PART 2 실전문제 세트"),
              (r"정답\s*및\s*해설", "정답 및 해설")],
    "vocaunit": [(r"어휘끝", "PART 1 어휘끝 UNIT 어휘"), (r"올림포스", "PART 2 올림포스 지문 어휘"),
                 (r"교과서", "PART 3 교과서 지문 어휘"), (r"모의고사", "PART 4 모의고사 지문 어휘")],
    "vocabook": [(r"표제어", "DAY 표제어"), (r"파생어", "DAY 파생어 & 연관어휘"), (r"VOCA\s*vs", "VOCA vs. VOCA"),
                 (r"워크북|주어진 단어에 해당하는|우리말 해석을 참고", "워크북 빈칸 드릴"), (r"^정답|정 답", "정답")],
}


# 같은 섹션 안에서 형태가 갈리는 면 — 본문에 이 말이 있으면 따로 묶는다 (포켓북: 삽화 칸 PICTURE 가 있는 지문 분석 면)
VARIANT_RULES = {"pocketbook": [(r"\bPICTURE\b", "삽화 있음")]}


def _head_text(page):
    """면 머리(위 22%)의 글 — 띄어 쓴 로마자(W E E K)는 붙이고 공백은 하나로."""
    H = page.rect.height
    blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1] / 8), b[0]))
    t = " | ".join(b[4] for b in blocks if b[1] < H * 0.22)
    t = re.sub(r"(?<=[A-Z])\s+(?=[A-Z])", "", t)          # W E E K VO CA B U L A RY → WEEKVOCABULARY
    return re.sub(r"\s+", " ", t).strip()


def _mock_section(page):
    """동형모의고사 시험지 면 — 형태가 다른 면만 나눈다: 첫 면(시험 제목·머리표) / 문항 면 / 끝 면(문항 수·점수 표).
    선택형·서답형은 같은 2단 시험지 면이라 하나로 둔다(2026-10-09 사용자: 문항 종류로 나눈 건 의미 없음)."""
    t = page.get_text()
    if page.number == 0:
        return "첫 면 · 시험 제목"
    if page.number == page.parent.page_count - 1 and re.search(r"확인\s*사항|문항\s*수", t):
        return "끝 면 · 점수 표"
    return "문항 면"


def _section_of(series, page, prev, skip=(), rules=True):
    """이 면의 구성 이름. 규칙(틀별) → 중등부 PART 머리 → 러닝 헤드 라벨(워크북) 순. 못 찾으면 직전 것.
    skip = 책 전체에서 한쪽 면마다 붙는 러닝 라벨(책 이름 등) — 구성 이름이 아니다.
    rules=False 면 틀별 규칙(SECTION_RULES·중등부 PART)을 쓰지 않고 그 면에 인쇄된 라벨만 본다 — 규칙은 그 틀의
    첫 책에 맞춰 쓴 것이라 다른 책에 대면 본문 낱말('파생어' 등)에 걸려 엉뚱하게 묶인다(2026-10-09 배재보카)."""
    if series == "mockexam":
        return _mock_section(page)
    head = _head_text(page)
    if rules and series in SECTION_RULES:
        for pat, name in SECTION_RULES[series]:
            if re.search(pat, head, re.I | re.M):
                return name
        return prev
    if rules and series == "middle":
        m = re.search(r"PART\s*(\d)\s*([가-힣\d ]+?)(?:\s*(STEP\s*\d)\s*([가-힣 /()TF]+?))?\s*(?:[A-Z]{3,}|\||—|$)", head)
        if m:
            name = f"PART {m.group(1)} {re.sub(r'\s*\d+\s*$', '', m.group(2).strip())}"
            if m.group(3):
                name += f" · {m.group(3).replace(' ', '')} {m.group(4).strip()}"
            return re.sub(r"\s+", " ", name)
        return prev
    cand = [l for l in _page_labels(page) if l not in ("STEP", "STEPBYSTEP") and l not in skip]
    ko = [l for l in cand if re.search(r"[가-힣]", l) and len(l) >= 3]      # '주제' 같은 두 글자 칸 이름은 구성 이름이 아니다
    if ko:
        return max(ko, key=len)
    if cand and not prev:
        return max(cand, key=len)
    return prev


def design_images(series, d, limit=6):
    """디자인 타일·지면에 보일 그림 [{src, label}] — 견본 사진 > 페이지 틀 > 기준 PDF 앞 면들(limit)."""
    if d.get("previews"):
        return [{"src": f"/catalog/preview/{series}/{d['id']}/{p}", "label": f"견본 {i + 1}"} for i, p in enumerate(d["previews"])]
    if d.get("masters"):
        return [{"src": f"/catalog/master/{series}/{d['id']}/{m['file']}", "label": m["label"]} for m in d["masters"]]
    n = min(design_pages(series, d["id"]), limit)
    return [{"src": f"/catalog/page/{series}/{d['id']}/{k}.png?dpi=40", "label": f"p{k}"} for k in range(1, n + 1)]


def _head_title(page):
    """면 맨 위(6.5% 안에서 시작하는 줄)에 짧은 한글 제목이 있나 — 워크북 'A1 어휘 선택 1'(5%) 처럼.
    본문 글줄(단어 뜻·세서특필 문장 머리 '분사구문' 7.3% 등)은 안 센다."""
    H = page.rect.height
    return any(b[1] < H * 0.065 and b[3] < H * 0.10 and
               any(re.search(r"[가-힣]{2,}", ln) and len(ln.strip()) <= 30 for ln in b[4].split("\n"))
               for b in page.get_text("blocks"))


def _big_heading(page):
    """위 35% 안에 본문 글씨의 1.8배 이상인 큰 제목이 있나 — 특강 '01 spect / spic' 처럼 항목 첫 면에만 오는 제목."""
    H = page.rect.height
    spans = [sp for b in page.get_text("dict")["blocks"] for ln in b.get("lines", []) for sp in ln["spans"] if sp["text"].strip()]
    if not spans:
        return False
    # 본문 글씨 = 글자 수가 가장 많은 크기. 가운데 값은 작은 주석 글자(분석본 S·V 표시)가 많은 면에서 흔들려
    # 같은 모양 면인데 큰 제목이 있다 없다 했다(2026-10-11 광문 분석본 '7강' 18.3pt — 가운데 값 7.0 / 7.6)
    cnt = {}
    for sp in spans:
        cnt[round(sp["size"], 1)] = cnt.get(round(sp["size"], 1), 0) + len(sp["text"].strip())
    # 더 큰 크기가 가장 많은 크기의 절반 넘게 쓰였으면 그 큰 크기가 본문이다 — 작은 주석 글자가 본문보다 많은 쪽(광문 분석본 20쪽:
    # 7pt 1192자 · 9pt 803자)에서 주석 크기를 본문으로 잡아 '8강'(18.3pt)이 큰 제목이 돼 같은 면이 갈라졌다(2026-10-12)
    most = max(cnt.values())
    body = max(s for s, c in cnt.items() if c >= most * 0.5)
    top = [sp for sp in spans if sp["bbox"][1] < H * 0.35]
    # 글자가 든 큰 제목(1.8배+, 글자가 칸마다 쪼개진 것도 모아서 센다) 또는 아주 큰 숫자(2.6배+, 단어장 DAY 번호).
    # 문항 번호('66.' 2배)처럼 숫자만 조금 큰 건 제목이 아니다
    letters = sum(len(re.findall(r"[A-Za-z가-힣]", sp["text"])) for sp in top if sp["size"] >= body * 1.8)
    return letters >= 2 or any(sp["size"] >= body * 2.6 for sp in top)


def _running_labels(doc):
    """바닥 띠에서 한쪽 면(짝·홀)의 40% 이상에 붙는 한글 라벨 — 책 이름 같은 러닝 푸터. 구성 이름으로 쓰지 않는다.
    머리 라벨은 안 센다(분석본 왼쪽 면마다 붙는 '모의고사' 는 그 구성의 제목이다)."""
    cnt, n = ({}, {}), [0, 0]
    for p in doc:
        side = (p.number + 1) % 2
        n[side] += 1
        H = p.rect.height
        foot = {re.sub(r"[\d\s.·:/()\-~|_,'\"!?]+", "", ln) for b in p.get_text("blocks") if b[1] > H * 0.93
                for ln in b[4].split("\n")}
        for l in set(_page_labels(p)) & foot:
            if re.search(r"[가-힣]", l):
                cnt[side][l] = cnt[side].get(l, 0) + 1
    run = {l for side in (0, 1) for l, c in cnt[side].items() if n[side] and c >= n[side] * 0.4}
    return run | _content_labels(doc)


def _content_labels(doc):
    """머리·바닥 같은 자리에 회차마다 다른 글이 오는 라벨 — 지문 제목('중국 고대 공놀이 Cuju') 같은 원고. 구성 이름이 아니다.
    한쪽 면(짝·홀)의 같은 자리(가로 10칸·세로 20칸)에 라벨이 3가지 이상 오고 그 가짓수가 붙은 면 수의 40% 이상이면,
    그 자리 라벨 가운데 책 전체에서 한 면에만 나오는 것. 한 번씩 오는 PART 간지 이름(교과서·모의고사·부교재)은
    바닥 띠에 되풀이되니 남는다(2026-10-11 광문 분석본 · 단어 카드).

    숫자까지 보면 면마다 글이 다른 라벨도 원고다 — 지문 출처('능률(오) 1과 본문1' · '고1 23년 11월 모의고사 18번')는
    숫자를 빼면 같은 말이 수십 면에 되풀이돼 구성 이름처럼 보였다(2026-10-12 배재1 포켓북). 쪽 번호는 숫자 비교에서 뺀다."""
    at, pages, raw = {}, {}, {}
    lines = []
    for p in doc:
        W, H = p.rect.width, p.rect.height
        for b in p.get_text("blocks"):
            if not (_in_head(b, H) or b[1] > H * 0.93):
                continue
            for line in b[4].split("\n"):
                for l in _page_labels_in(line):
                    at.setdefault((p.number % 2, round(b[0] / W * 10), round(b[1] / H * 20)), []).append(l)
                    pages.setdefault(l, set()).add(p.number)
                    lines.append((l, p.number, re.sub(r"\s+", "", line)))
    # 쪽 번호 = 머리·바닥 숫자 가운데 (숫자 - 면 차례)가 같은 값으로 절반 넘는 면에 나오는 것
    off = {}
    for _, pn, t in {(None, pn, t) for _, pn, t in lines}:
        for d in set(re.findall(r"\d+", t)):
            off.setdefault(int(d) - pn, set()).add(pn)
    pg = max(off, key=lambda k: len(off[k]), default=None)
    if pg is not None and len(off[pg]) < len(doc) * 0.5:
        pg = None
    for l, pn, t in lines:
        raw.setdefault(l, {})[pn] = re.sub(r"\d+", lambda m: "" if int(m.group()) - pn == pg else m.group(), t)
    numbered = {l for l, r in raw.items() if len(r) >= 3 and len(set(r.values())) >= len(r) * 0.8}
    return {l for labs in at.values() if len(set(labs)) >= 3 and len(set(labs)) >= len(labs) * 0.4
            for l in labs if len(pages[l]) == 1} | numbered


def _divider_vec(page):
    """간지 생김새 — 폭 36px 회색 그림을 밝기 정규화한 값. 색만 다른 간지(STEP 01·02·03)·번호만 다른 간지(UNIT 4·5)는
    상관이 0.9 넘게, 다른 간지끼리는 0.5 아래로 나온다(2026-10-09 워크북·단어장 실측). 글상자 위치 비교는 번호·글자
    길이만 달라도 갈라져서 쓰지 않는다."""
    import fitz
    z = 36 / page.rect.width
    v = list(page.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csGRAY).samples)
    m = sum(v) / len(v)
    sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
    return [(x - m) / sd for x in v] if sd > 1 else None          # None = 거의 한 색(빈 면)


def _divider_boxes(page):
    """간지 글상자·그림 배치 — 면을 8×10 칸으로 나눠 덮인 칸. 그림 비교로 안 갈리는 것(세서특필: 같은 그러데이션 위
    'PART 01' 면 / 소제목 면)을 가른다."""
    W, H = page.rect.width, page.rect.height
    return frozenset((gx, gy) for b in page.get_text("blocks") if b[4].strip() or b[6] == 1
                     for gx in range(int(b[0] / W * 8), min(int(b[2] / W * 8 - 1e-6), 7) + 1)
                     for gy in range(int(b[1] / H * 10), min(int(b[3] / H * 10 - 1e-6), 9) + 1))


def _vec_corr(a, b):
    if a is None or b is None:
        return 1.0 if a is None and b is None else 0.0
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n)) / n


def _divider_name(page):
    """간지 이름 — 가장 큰 글씨가 든 글덩어리('11강' → '마더텅 고1 영어 독해 11강'). 띄어 쓴 로마자는 붙인다."""
    best = None
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if re.search(r"[A-Za-z가-힣]", sp["text"]) and (best is None or sp["size"] > best[0]):
                    best = (sp["size"], b)
    if not best:
        return ""
    t = re.sub(r"\s+", " ", " ".join(sp["text"] for ln in best[1]["lines"] for sp in ln["spans"])).strip()
    w = t.split()
    if len(w) >= 3 and sum(len(x) == 1 for x in w) >= len(w) * 0.6:     # 한 글자씩 띄운 제목('어 휘 끝') → 붙인다
        t = "".join(w)
    return re.sub(r"(?<=[A-Z]) (?=[A-Z])", "", t)[:24]


def _page_tokens(series, doc, rules=True):
    """면마다 모양 표 (간지/본문, 구성 이름, 맨 위 제목 유무, 삽화 같은 갈래). 내용(지문 글)은 안 본다."""
    skip = _running_labels(doc)
    content = _content_labels(doc)
    out, section, lead, fresh, owns = [], "", [], set(), set()
    for page in doc:
        prev = section
        section = _section_of(series, page, prev, skip, rules)
        own = _section_of(series, page, "", skip, rules)
        if len(own) >= 3 and re.search(r"[가-힣]", own) or len(own) >= 4 and own.isupper():
            owns.add(page.number)                         # 제 이름표(한글 · 영문 대문자)가 찍힌 면
        # 제 이름표 없이 원고 머리표(지문 출처·제목)만 있는 면은 새 원고의 첫 면이다 — 앞 면 구성을 이어받지 않는다
        # (배재1 포켓북 분석 면이 바로 앞 '암기 TEST 정답' 면 이름을 받던 것, 2026-10-12)
        if not own and any(l in content for l in _page_labels(page)):
            section = ""
            fresh.add(page.number)
        H = page.rect.height
        blocks = page.get_text("blocks")
        body = sum(1 for b in blocks if H * 0.10 <= b[1] <= H * 0.93 and len(b[4].strip()) > 20)
        txt = page.get_text()
        if re.search(r"M\s*E\s*M\s*O", txt) and body < 2:                  # 단원 끝 MEMO 면 — 반복 묶음의 일부
            out.append(("MEMO", section, 0, ""))
            continue
        # 글이 적은 면이라도 바로 앞 본문 면들(최대 3면)과 생김새가 아주 닮으면(0.6+) 그 구성의 짧은 끝 면이다
        # (단어장 단원 끝 단어 하나 면 0.62~0.73, 본문 옆 간지는 0.52 이하 — 2026-10-09 실측)
        # 글이 적은 면 = 본문 글상자가 2개 미만이면서 글자도 150자 미만(표 하나에 글이 꽉 찬 면은 글상자 1개라도 본문)
        low = body < 2 and len(txt.strip()) < 150
        short_end = False
        if low and out and out[-1][0] == "본문" and txt.strip():
            v = _divider_vec(page)
            back = [j for j in range(page.number - 1, max(-1, page.number - 4), -1) if out[j][0] == "본문"]
            short_end = any(_vec_corr(v, _divider_vec(doc[j])) >= 0.6 for j in back)
        if low and not short_end:
            out.append(("간지", section, 0, ""))
            section = prev                    # 간지 이름표(표지의 학교 이름 등)는 다음 본문 면으로 넘기지 않는다
            continue
        # 제 이름표가 없는 첫 본문 면. 원고 첫 면 바로 뒤 면은 앞 구성이 비어도 첫 면이 아니다(배재1 포켓북 'FLOW NOTE')
        if page.number in fresh or not prev and page.number - 1 not in fresh and \
                not (len(section) >= 3 and re.search(r"[가-힣]", section)):
            lead.append(page.number)
        var = "".join(f" · {v}" for pat, v in VARIANT_RULES.get(series, []) if re.search(pat, txt))
        # 제목 표시 — 1: 맨 위 짧은 한글 제목, 2: 큰 제목 글씨. 0 이면 이어지는 면. 시험지 머리는 홀짝 면 문구라 안 본다
        title = 0 if series == "mockexam" else int(_head_title(page)) + 2 * int(_big_heading(page))
        out.append(("본문", section, title, var))
    # 이름표가 없어 앞 구성을 이어받은 본문 면은, 같은 구성의 가까운 면들(앞뒤로 최대 8면, 2면 이상 있을 때) 중 가장
    # 닮은 면과의 생김새 상관이 0.25 미만이면 그 구성이 아니다(포켓북·워크북 마지막 면, 특강 PART 간지처럼 글이 있는 면).
    # 23개 디자인 실측: 진짜 이어지는 면은 0.29 이상, 아닌 면은 0.22 이하(2026-10-09).
    if series != "mockexam":
        vec, members = {}, {}
        V = lambda i: vec.setdefault(i, _divider_vec(doc[i]))
        for i, t in enumerate(out):
            if t[0] == "본문":
                members.setdefault(t[1], []).append(i)
        for i, t in enumerate(out):
            if t[0] != "본문":
                continue
            # 이름표가 있는 면은 더 엄하게(0.1) — 같은 유형 제목 면도 문항 수에 따라 생김새가 0.15 까지 떨어진다(워크북 C2).
            # 이름표를 단 채 모양이 아주 다른 면(한끝 'PART 01 서답형 40제' 간지 0.03)만 뗀다.
            cut = 0.1 if _section_of(series, doc[i], "", skip, rules) else 0.25
            near = sorted((j for j in members[t[1]] if j != i), key=lambda j: abs(j - i))[:8]
            if len(near) >= 2 and max(_vec_corr(V(i), V(j)) for j in near) < cut:
                out[i] = ("간지", t[1], 0, "")
    # 앞에 본문 면이 없는 첫 본문 면(간지 바로 뒤)은 이어받을 구성이 없다 — 뒤 4면 안에 생김새가 아주 닮은(0.6+) 본문 면이
    # 있으면 그 구성이다(위에서 떨어져 나온 면은 빼고). 광문 분석본 첫 분석 면은 머리에 지문 제목뿐이라 이름표가 없고,
    # 셋째 면부터 '7강 분석'을 이어받는다(2026-10-11)
    # 원고 머리표가 있는 첫 면은 처음 나오는 이름표 면까지만 본다(다음 원고 첫 면 앞에서 멈춤) — 그 이름표 면이 다른
    # 구성(배재1 포켓북 'FLOW NOTE')이면 더 뒤의 면('암기 TEST')을 빌려 오지 않는다
    for i in (i for i in lead if out[i][0] == "본문"):
        v = _divider_vec(doc[i])
        stop = len(out)
        if i in fresh:
            stop = next((j + (j in owns) for j in range(i + 1, len(out)) if j in fresh or j in owns), len(out))
        nxt = [j for j in range(i + 1, min(stop, i + 5)) if out[j][0] == "본문" and j not in lead]
        j = next((j for j in nxt if _vec_corr(v, _divider_vec(doc[j])) >= 0.6), None)
        if j is not None:
            out[i] = (out[i][0], out[j][1], out[i][2], out[i][3])
    # 라벨도 앞 구성도 없는 본문 면(책 첫 본문 면 등)은 이름이 없으니 생김새로만 묶는다 — 배재보카 DAY 21 시작 면이
    # 'DAY 22' 이후 시작 면들과 한 구성이 되게(2026-10-09). 원고 머리표가 있는 면은 글이 꽉 찬 본문 면이라 본문으로
    # 두고 이름만 비운다(머리표 글은 원고라 이름이 아니다)
    for i, t in enumerate(out):
        if t[0] == "본문" and not t[1]:
            out[i] = ("본문", "이름 없는 면", t[2], t[3]) if i in fresh else ("간지", "", 0, "")
    # 글이 적은 면·위에서 떨어져 나온 면은 생김새끼리 나눈다 — STEP 간지 · 단원 간지 · 빈 면 · 마지막 면 … 은 다른 구성.
    # 첫 면·마지막 면이라고 표지로 정하지 않는다(내지만 있는 PDF 도 있다).
    reps = []                                             # [((그림, 배치), 이름)]
    # 같은 생김새 = 그림 상관 0.9+ 이고, 글상자 배치가 30% 넘게 겹치고, 글자 수가 2.1배 넘게 차이 나지 않을 것
    # (포켓북 마지막 면은 첫 면과 그림·배치가 비슷해도 만든 사람 목록 때문에 글자가 189 대 70 — 다른 면이다)
    # 그림 상관 0.9: 같은 간지끼리 0.92~1.0, 간지와 그 옆 목차 면(같은 바탕색)은 0.86~0.88 (2026-10-09 단어장 실측)
    same = lambda x, y: _vec_corr(x[0], y[0]) >= 0.9 and (
        not x[1] or not y[1] or len(x[1] & y[1]) / len(x[1] | y[1]) >= 0.3) and \
        max(x[2] + 20, y[2] + 20) / min(x[2] + 20, y[2] + 20) < 2.1
    for i, t in enumerate(out):
        if t[0] != "간지":
            continue
        v = (_divider_vec(doc[i]), _divider_boxes(doc[i]), len(doc[i].get_text().strip()))
        nm = next((n for r, n in reps if same(v, r)), None)      # 이미 묶인 면 어느 하나와 같으면 그 묶음
        if nm is not None:
            reps.append((v, nm))
        if nm is None:                                    # 새 생김새 — 이름이 겹쳐도 다른 구성이다(이름 뒤에 번호)
            base = "빈 면" if v[0] is None else _divider_name(doc[i]) or "이름 없는 면"
            nm, k = base, 2
            while any(n == nm for _, n in reps):
                nm, k = f"{base} ({k})", k + 1
            reps.append((v, nm))
        out[i] = ("간지", nm, 0, "")
    return out


def _repeat_runs(tok, kmax=6):
    """앞에서부터 같은 모양 묶음(1~kmax 면)이 되풀이되는 구간 [(시작, 묶음 길이, 덮은 면 수)].
    가장 많이 덮는 길이를 고르고, 같으면 짧은 쪽. 끝에 묶음 앞부분만 온 면도 그 구간에 넣는다.
    되풀이가 없는 짧은 구성(워크북 C영작배열 '제목 면 + 이어짐' 한 번 + MEMO)은 이 책에서 이미 찾은 묶음 모양
    (구성 이름 빼고 간지/본문·제목 유무·갈래)과 같으면 그 묶음으로 본다."""
    shape = lambda ts: tuple((t[0], t[2], t[3]) for t in ts)
    cont = lambda t: t[0] == "MEMO" or (t[0] == "본문" and not t[2])
    # 같은 자리: 똑같거나, 같은 구성 안에서 '이어지는 면' 자리에 MEMO 가 온 것(단어장 DAY 끝 면)
    same = lambda a, b: a == b or (a[1] == b[1] and cont(a) and cont(b) and "MEMO" in (a[0], b[0]))
    eq = lambda xs, ys: len(xs) == len(ys) and all(same(x, y) for x, y in zip(xs, ys))
    shapes = []
    i, runs, n = 0, [], len(tok)
    while i < n:
        bk, bcov = 1, 1
        for k in range(1, kmax + 1):
            if i + 2 * k > n:
                break
            m = tok[i:i + k]
            r = 1
            while eq(tok[i + r * k:i + (r + 1) * k], m):
                r += 1
            if r < 2:
                continue
            j = i + r * k
            while j < n and j - i - r * k < k and same(tok[j], m[j - i - r * k]):
                j += 1
            if j - i > bcov or (j - i == bcov and k < bk):
                bk, bcov = k, j - i
        if bcov == 1:
            for sh in sorted(shapes, key=len, reverse=True):
                seg = tok[i:i + len(sh)]
                if len(sh) > 1 and len(seg) == len(sh) and shape(seg) == sh and len({t[1] for t in seg}) == 1:
                    bk = bcov = len(sh)
                    break
        elif bk > 1 and shape(tok[i:i + bk]) not in shapes:
            shapes.append(shape(tok[i:i + bk]))
        runs.append((i, bk, bcov))
        i += bcov
    return runs


def _unit_name(unit):
    """묶음 이름 — 구성 이름들을 + 로. 본문이 있는 묶음에서 MEMO 는 채움 면이라 이름에 안 넣는다."""
    names = []
    has_body = any(t[0] == "본문" for t in unit)
    for kind, sec, _, var in unit:
        if kind == "MEMO" and has_body:
            continue
        nm = (sec or "이름 없는 면") + var if kind == "본문" else (sec or "간지") if kind == "간지" else kind
        if nm not in names:
            names.append(nm)
    return " + ".join(names)


def design_layouts(series, design):
    """기준 PDF 의 면을 **구성** 으로 묶는다 — 내용이 아니라 모양이 되풀이되는 묶음 하나가 구성 하나.

    면마다 모양 표(_page_tokens: 구성 이름 · 맨 위 제목 유무 · 삽화 갈래 · 간지)를 만들고, 같은 모양 묶음이
    되풀이되는 구간을 찾는다(_repeat_runs). 묶음은 1면일 수도(블랙북 문항), 펼침면 2면일 수도(워크북
    '제목 면 + 이어지는 면', 포켓북 '지문 분석 + 요약노트'), 그 이상일 수도 있다. 이름이 같은 묶음은 한 구성.
    show = 그 구성을 가장 많이 덮은 묶음의 첫 회. 결과는 `_pages/layouts15_<stamp>.json`(15 = 면 목록 faces 를 더한 판) 에 둔다.
    """
    pdf = _design_pdf(series, design)
    if not pdf:
        return {"total": 0, "layouts": []}
    tdir = os.path.join(_ddir(series, design), "_pages")
    os.makedirs(tdir, exist_ok=True)
    # 틀별 구성 규칙은 그 틀의 원래 책용 — bin/register-design 으로 새로 등록한 책(design.json layout_rules: false)은 안 쓴다
    try:
        dj = json.load(open(os.path.join(_ddir(series, design), "design.json"), encoding="utf-8"))
    except (OSError, ValueError):
        dj = {}
    editor = dj.get("made") == "editor"
    origin = _origin_pdf(series, design) if editor else None
    stamp = f"{int(os.path.getmtime(pdf))}" + (f"_o{int(os.path.getmtime(origin))}" if origin else "")
    cache = os.path.join(tdir, f"layouts15{'e' if editor else ''}_{stamp}.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    out = (editor_layouts(series, design, dj, pdf) if editor else None) or pdf_layouts(pdf, series, dj.get("layout_rules", True))
    if origin:                                            # 원본 페이지 차례 — PDF 등록 카드와 같은 판정(새 PDF 라 틀 규칙 없이)
        o = pdf_layouts(origin, series, False)
        out["origin"] = {"total": o["total"], "layouts": o["layouts"]}
    json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def editor_layouts(series, design, dj, pdf):
    """편집기 제작 디자인 — 구성을 PDF 에서 짐작하지 않고 편집기 문서(units.json)에서 읽는다.
    구성 견본은 한 벌씩이라 되풀이가 없어 PDF 판정은 펼침면을 알아보지 못한다(정본 2026-10-11: 2면 구성이 첫 면만 보였다).
    묶음: 「원고마다」 면은 이름 있는 면부터 다음 이름 있는 면 전까지(펼침면 오른쪽 면은 이름 없음) · 「넘치면 이어 갈 면」으로 묶인 면 ·
    나머지 「한 번만」 면은 하나씩. 이름: 면 이름, 없으면 PDF 판정이 그 면에서 읽은 이름표. 이름·종류·면 수가 같은 묶음은 한 구성(STEP 간지 셋).
    면 수가 문서 쪽과 안 맞으면(원고 여럿 · 흐르는 쪽 여럿) None — PDF 판정으로."""
    import fitz
    try:
        u = json.load(open(os.path.join(_ddir(series, design), dj.get("units") or "units.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pages_by = {p["id"]: p for p in u.get("pages") or []}
    plan = u.get("plan") or {}
    ents = [e if isinstance(e, dict) else {"page": e, "repeat": "once"} for s in plan.get("sections") or [] for e in s.get("pages") or []]
    ents = [e for e in ents if e.get("page") in pages_by and e.get("repeat") != "none"]
    plain = lambda nm: not nm or re.fullmatch(r"빈 면 \d+", nm)
    units = []                                            # [[문서 쪽 id …]]
    for e in ents:
        p = pages_by[e["page"]]
        prev = units[-1] if units else None
        last = pages_by[prev[-1]] if prev else None
        linked = last is not None and (p.get("cont") in prev or last.get("cont") == p["id"])
        run = last is not None and e.get("repeat") == "each_set" and plain(p.get("name")) and \
            next(x for x in ents if x["page"] == prev[-1]).get("repeat") == "each_set"
        if linked or run:
            prev.append(p["id"])
        else:
            units.append([p["id"]])
    doc = fitz.open(pdf)
    total = doc.page_count
    extra = total - len(ents)                             # 흐르는 쪽이 만든 덧쪽 — 넘치면 이어 갈 면 묶음 하나가 받는다
    flows = [k for k, un in enumerate(units) if any(pages_by[i].get("cont") for i in un)]
    if extra < 0 or (extra and len(flows) != 1):
        doc.close()
        return None
    tok = _page_tokens(series, doc, False)
    doc.close()
    groups, order, at = {}, [], 0
    for k, un in enumerate(units):
        n = len(un) + (extra if flows and k == flows[0] else 0)
        span = list(range(at + 1, at + n + 1))
        seg = tok[at:at + n]
        at += n
        nm0 = (pages_by[un[0]].get("name") or "").removesuffix(" 오른쪽")
        kind = "본문" if any(t[0] == "본문" for t in seg) else "간지"
        nm = nm0 if not plain(nm0) else _unit_name(seg) or "이름 없는 면"
        key = (nm, kind, len(un))
        if key not in groups:
            label = nm
            while any(groups[q]["label"] == label for q in order):          # 이름이 같아도 종류·면 수가 다르면 다른 구성
                label += " ·"
            groups[key] = {"pages": [], "show": span[:len(un)], "kind": kind, "label": label}
            order.append(key)
        groups[key]["pages"] += span
    return {"total": total, "from": "editor",
            "layouts": [{"n": groups[q]["pages"][0], "pages": groups[q]["pages"], "count": len(groups[q]["pages"]), "kind": groups[q]["kind"],
                         "section": groups[q]["label"], "show": groups[q]["show"], "unit": len(groups[q]["show"]), "label": groups[q]["label"]}
                        for q in order]}


def pdf_layouts(pdf, series=None, rules=False):
    """PDF 파일 하나 → 구성 목록. design_layouts 와 같은 판정을 등록 없이 부르는 입구(편집기로 만들기 1단계 — 구성 나누기).
    rules = 그 틀의 구성 규칙(SECTION_RULES)을 쓸지 — 새 PDF 는 False(면에 인쇄된 이름표·생김새로만, PDF 등록과 같다)."""
    import fitz
    doc = fitz.open(pdf)
    tok = _page_tokens(series, doc, rules)
    groups, order = {}, []
    names = {}                                            # 이름 → 모양 종류(간지/본문). 이름이 같아도 종류가 다르면 다른 구성
    for i, k, cov in _repeat_runs(tok):
        unit = tok[i:i + k]
        nm = _unit_name(unit)
        kind = "본문" if any(t[0] == "본문" for t in unit) else "간지"
        if names.setdefault(nm, kind) != kind:
            nm = f"{nm} · {'본문' if kind == '본문' else '간지'}"
        g = groups.get(nm)
        if not g:
            g = groups[nm] = {"pages": [], "best": 0, "show": [],
                              "kind": "본문" if any(t[0] == "본문" for t in unit) else "간지"}
            order.append(nm)
        g["pages"] += range(i + 1, i + cov + 1)
        if cov > g["best"]:
            g["best"], g["show"] = cov, list(range(i + 1, i + k + 1))
    # 길이가 다른 회차가 남긴 조각(특강 LESSON 이 4면·5면) — 구성 이름이 모두 더 큰 묶음 안에 있으면 그 묶음에 넣는다.
    # 제 묶음이 연달아 되풀이된 것은 조각이 아니라 따로 된 구성이다(배재1 포켓북 '암기 TEST + 정답' 2면 × 5, 2026-10-12)
    parts = lambda nm: set(nm.split(" + "))
    for nm in list(order):
        g = groups[nm]
        if g["kind"] != "본문" or g["best"] > len(g["show"]):
            continue
        big = [o for o in order if o != nm and groups[o]["kind"] == "본문" and len(groups[o]["show"]) > len(g["show"])
               and parts(nm) < parts(o)]
        if big:
            to = max(big, key=lambda o: groups[o]["best"])
            groups[to]["pages"] = sorted(groups[to]["pages"] + g["pages"])
            order.remove(nm)
    out = {"total": doc.page_count,
           "layouts": [{"n": groups[nm]["pages"][0], "pages": groups[nm]["pages"], "count": len(groups[nm]["pages"]),
                        "kind": groups[nm]["kind"], "section": nm, "show": groups[nm]["show"], "unit": len(groups[nm]["show"]),
                        "label": nm}
                       for nm in order]}
    # 면 목록 — 만드는 단위(인디자인 상위 페이지). 서로 다른 면 모양마다 하나, 묶음은 「원본 차례 견본」일 뿐이다
    # (지문마다 붙는 면은 원고가 정한다 — 절차 2단계 「면 나누기」, 2026-10-12). 이름이 같은 면이 둘이면(제목 면 · 이어지는 면) 뒤에 붙여 가른다
    faces = {}
    for p, t in enumerate(tok, 1):
        faces.setdefault(t, []).append(p)
    named = {}
    for t in faces:
        named.setdefault(_unit_name([t]), []).append(t)
    label = {}
    for nm, ts in named.items():
        side = lambda t: {p % 2 for p in faces[t]}
        for k, t in enumerate(ts):
            if len(ts) == 1:
                label[t] = nm
            elif len({bool(x[2]) for x in ts}) > 1:               # 제목 있는 면 / 없는 면
                label[t] = f"{nm} · {'첫 면' if t[2] else '이어지는 면'}"
            elif all(len(side(x)) == 1 for x in ts) and len({min(side(x)) for x in ts}) > 1:   # 왼쪽 / 오른쪽 면
                label[t] = f"{nm} · {'왼쪽 면' if not min(side(t)) else '오른쪽 면'}"
            else:
                label[t] = nm if k == 0 else f"{nm} ({k + 1})"
    # 펼침면 — 왼쪽(짝수 쪽) 면 A 뒤에 늘 면 B 가 오고 B 는 늘 A 뒤에만 온다(2번 넘게) → 두 쪽 한 벌을 면 하나로
    # (배재1 포켓북 암기 TEST + 정답, 워크북 유형 제목 면 + 이어지는 면 — 인디자인 2쪽 상위 페이지)
    pair = {}
    for a, pa in faces.items():
        if a[0] != "본문" or len(pa) < 2 or any(p % 2 for p in pa) or any(p >= len(tok) for p in pa):
            continue
        b = tok[pa[0]]                                    # pa[0] 은 1부터 센 쪽 → tok[pa[0]] 이 바로 다음 쪽
        if b != a and b[0] == "본문" and all(tok[p] == b for p in pa) and len(faces[b]) == len(pa) and b not in pair.values():
            pair[a] = b
    rows = []
    for t, ps in faces.items():
        if t in pair.values():
            continue
        b = pair.get(t)
        nm = label[t] if not b else _unit_name([t]) if _unit_name([t]) == _unit_name([b]) else f"{label[t]} + {label[b]}"
        rows.append({"label": nm, "kind": t[0], "size": 2 if b else 1,
                     "pages": sorted(ps + faces[b]) if b else ps, "count": len(ps), "show": [ps[0], ps[0] + 1] if b else [ps[0]]})
    out["faces"] = sorted(rows, key=lambda f: f["pages"][0])
    doc.close()
    return out


def warm_layouts():
    """모든 디자인의 구성을 계산해 캐시에 둔다(서버 기동 때 뒤에서). 실패한 디자인은 건너뛴다."""
    n = 0
    for t in templates():
        for d in t["designs"]:
            try:
                if design_layouts(t["series"], d["id"])["total"]:
                    n += 1
            except Exception as e:
                print(f"■ 구성 미리 계산 실패 {t['series']}/{d['id']}: {e}", flush=True)
    print(f"■ 구성 미리 계산 끝 — 디자인 {n}개", flush=True)


@bp.route("/catalog/pdf/<series>/<design>")
def design_pdf_view(series, design):
    """기준 PDF 원본 — 브라우저 PDF 뷰어로 연다(내려받기 아님). 구성과 나란히 대조용, 주소 뒤 #page=N 으로 그 면부터."""
    if series not in _meta() or not _ID.match(design):
        abort(404)
    pdf = _origin_pdf(series, design) if request.args.get("src") == "origin" else _design_pdf(series, design)
    if not pdf:
        abort(404)
    return send_from_directory(os.path.dirname(pdf), os.path.basename(pdf), mimetype="application/pdf")


@bp.route("/catalog/page/<series>/<design>/<int:n>.png")
def design_page_img(series, design, n):
    """기준 PDF 의 n 면 그림(1부터). `_pages/` 에 두고 다시 안 그린다. ?dpi= 24~120. ?src=origin = 편집기 템플릿의 원본 PDF."""
    if not _ID.match(design) or n < 1:
        abort(404)
    org = request.args.get("src") == "origin"
    pdf = _origin_pdf(series, design) if org else _design_pdf(series, design)
    if not pdf:
        abort(404)
    try:
        dpi = max(24, min(int(request.args.get("dpi") or 36), 120))
    except ValueError:
        dpi = 36
    tdir = os.path.join(_ddir(series, design), "_pages")
    os.makedirs(tdir, exist_ok=True)
    out = f"{'o' if org else ''}{int(os.path.getmtime(pdf))}_{n}_{dpi}.png"
    if not os.path.exists(os.path.join(tdir, out)):
        try:
            import fitz
            doc = fitz.open(pdf)
            ok = n <= doc.page_count
            if ok:
                doc[n - 1].get_pixmap(dpi=dpi).save(os.path.join(tdir, out))
            doc.close()
        except Exception:
            abort(500)
        if not ok:
            abort(404)
    return send_from_directory(tdir, out)


@bp.route("/catalog/preview/<series>/<design>/<name>")
def preview_img(series, design, name):
    if not _ID.match(design) or not re.match(r"^preview_\d+\.png$", name):
        abort(404)
    return send_from_directory(_ddir(series, design), name)


@bp.route("/api/catalog/templates")
def api_templates():
    return jsonify(templates())


# ── 디자인 ──────────────────────────────────────────────────────
def _new_id(series):
    """새 디자인 폴더 이름 — 번호를 세지 않는 무작위 이름이라 여러 세션이 동시에 등록해도 안 겹친다.
    화면에는 이름(design.json name)만 보인다. 예전 d1·d2… 는 그대로 둔다."""
    import secrets
    while True:
        did = "x" + secrets.token_hex(4)
        if not os.path.exists(_ddir(series, did)):
            return did


@bp.route("/api/catalog/design/<series>/<design>/origin", methods=["POST"])
def design_origin(series, design):
    """편집기 템플릿에 원본 PDF 붙이기(절차 8단계 템플릿 등록 뒤) — 템플릿 보기 「원본 페이지 차례」.
    form file=<PDF> 또는 from=<같은 틀의 PDF 등록 카드 id>(그 카드의 기준 PDF 를 복사). → {ok, pages}"""
    if not _ID.match(design) or series not in _meta():
        abort(404)
    d = _ddir(series, design)
    try:
        dj = json.load(open(os.path.join(d, "design.json"), encoding="utf-8"))
    except (OSError, ValueError):
        abort(404)
    if dj.get("made") != "editor":
        return jsonify({"error": "편집기 템플릿에만 붙인다"}), 400
    import fitz
    dst = os.path.join(d, "참고", "원본.pdf")
    tmp = dst + ".part"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src = (request.form.get("from") or "").strip()
    if src:
        if not _ID.match(src) or src == design:
            return jsonify({"error": "원본 카드 id 가 틀렸다"}), 400
        pdf = _design_pdf(series, src)
        if not pdf:
            return jsonify({"error": f"{series}/{src} 에 기준 PDF 가 없다"}), 404
        shutil.copyfile(pdf, tmp)
    elif request.files.get("file"):
        request.files["file"].save(tmp)
    else:
        return jsonify({"error": "file 또는 from 이 있어야 한다"}), 400
    try:
        n = fitz.open(tmp).page_count
    except Exception:
        os.remove(tmp)
        return jsonify({"error": "PDF 가 아니다"}), 400
    os.replace(tmp, dst)
    return jsonify({"ok": True, "pages": n, "layouts": len(design_layouts(series, design).get("origin", {}).get("layouts") or [])})


@bp.route("/api/catalog/design/<series>/<design>", methods=["DELETE"])
def design_del(series, design):
    if not _ID.match(design):
        abort(404)
    d = _ddir(series, design)
    if os.path.isdir(d):
        shutil.rmtree(d)
    from core import yos_hooks
    yos_hooks.design_changed(series, design, "deleted")
    return jsonify({"ok": True})


# ── 견본 사진 ───────────────────────────────────────────────────
@bp.route("/api/catalog/preview/<series>/<design>/<name>", methods=["DELETE"])
def preview_del(series, design, name):
    if not _ID.match(design) or not re.match(r"^preview_\d+\.png$", name):
        abort(404)
    p = os.path.join(_ddir(series, design), name)
    if os.path.exists(p):
        os.remove(p)
    return jsonify({"ok": True})
