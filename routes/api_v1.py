# -*- coding: utf-8 -*-
"""`/api/v1` — **contents · core · 앱이 부르는 바깥용 API.**

화면용 `/api/catalog/*` 와 달리 이쪽은 계약이다: 모양을 바꾸면 v2 로.

    GET  /api/v1/health                              살아 있나 (인증 없음)
    GET  /api/v1/catalog                             디렉토리 → 틀 → 디자인 (미리보기 URL·version 포함)
    GET  /api/v1/catalog/<series>/<design>           디자인 하나 + config 요약 (편집기 제작이면 상위 페이지 자리)
    GET  /api/v1/catalog/<series>/<design>/image/<name>   master_N.png · preview_N.png
    POST /api/v1/renders                             찍기 잡 만들기 — 편집기 제작 디자인만 (아래)
    GET  /api/v1/renders                             최근 잡
    GET  /api/v1/renders/<id>?since=N                상태·로그·산출
    GET  /api/v1/renders/<id>/files/<name>           PDF · 로그 · data.json
    GET  /api/v1/renders/<id>/pages/<n>.png?dpi=72   면 그림

POST /renders 본문 (JSON):
    {
      "series": "workbook", "design": "x…",            ← 편집기 제작 디자인(design.json made: editor)
      "book":   {"title": "…"},
      "source": {"type": "data", "data": {"format": "yos-workbook-v1" | "yos-analysis-v1", …}},
      "print":  false,                                  ← (선택) 인쇄본
      "order":  "data",                                 ← (선택, 워크북) 원고 지문 칸 차례 그대로 · 틀 앞뒤 쪽(속표지 · 간지 · 차례 · MEMO · 뒤표지) 없이 — contents 책 구성 미리보기
      "callback": {"ref": "…"}                          ← (선택) 웹훅에 그대로 되돌려 줄 값
    }
(예전 조판 엔진으로 찍던 길 — 원고 파일 · data · plan · 책 목록 · 스키마 · embed-token — 은 2026-10-19 뺐다.)

응답: {"job": "<id>", "book": {"key": …, "bid": …}, "status_url": "/api/v1/renders/<id>"}
"""
import hashlib
import json
import os
import re
import time

from flask import Blueprint, abort, jsonify, request, send_file, send_from_directory, url_for

from core import blob, jobs, yos_hooks
from core.webauth import current_user

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1"
_IMG = re.compile(r"^(master|preview)_\d+\.png$")
_FILE_OK = re.compile(r"^[^/\\]+\.(pdf|json|txt)$")
VIVLIOSTYLE = os.path.join(REPO, "vivliostyle", "node_modules", ".bin", "vivliostyle")   # 나중에 뽑을 때 쓴다(배포 이미지에 설치)


def _cat():
    from routes import catalog
    return catalog


def _public_base():
    """웹훅·바깥 링크용 절대 주소. 요청 안이면 그 호스트, 아니면 YONE_PUBLIC_URL."""
    env = (os.environ.get("YONE_PUBLIC_URL") or "").strip().rstrip("/")
    if env:
        return env
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return ""


# ── health ──────────────────────────────────────────────────────
@bp.route("/health")
def health():
    from core.webauth import mode
    from routes.intake import have_key
    running = [j.id for j in jobs.recent(limit=200) if j.status == "running"]
    return jsonify({"ok": True, "api": VERSION, "auth": mode(), "vivliostyle": os.path.exists(VIVLIOSTYLE),
                    "claude": have_key(), "jobs_running": len(running), "time": time.time()})


# ── 카탈로그 ────────────────────────────────────────────────────
def _version(series, design):
    """디자인의 판본 — config·css·design.json 이 바뀌면 바뀐다. 렌더 기록에 박아 둔다."""
    h = hashlib.sha1()
    d = _cat()._ddir(series, design)
    for fn in ("config.json", "overrides.css", "design.json"):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(fn.encode()); h.update(f.read())
    return h.hexdigest()[:10]


def _img_url(series, design, name):
    u = _blob_image(series, design, name)
    return u or (_public_base() + url_for("api_v1.design_image", series=series, design=design, name=name))


def _blob_image(series, design, name):
    """디자인 이미지의 공개 Blob URL. 처음 요청 때 올리고 `<디자인>/blob.json` 에 적어 둔다(파일이 바뀌면 다시)."""
    if not blob.enabled():
        return None
    d = _cat()._ddir(series, design)
    src = os.path.join(d, name)
    if not os.path.exists(src):
        return None
    cache_p = os.path.join(d, "blob.json")
    try:
        cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
    except Exception:
        cache = {}
    key = f"{name}@{int(os.path.getmtime(src))}"
    if cache.get(name, {}).get("key") == key:
        return cache[name]["url"]
    try:
        r = blob.put_file(src, f"catalog/{series}/{design}/{name}", "image/png", access="public")
    except Exception:
        return None                     # Blob 이 잠시 안 되면 스튜디오 URL 로 떨어진다
    if not r:
        return None
    cache[name] = {"key": key, "url": r["url"], "pathname": r["pathname"]}
    try:
        with open(cache_p, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return r["url"]


def _design_out(series, d):
    """화면용 디자인 dict → 바깥용. PDF 판정 원문(intake)은 뺀다 — 크고, 계약이 아니다."""
    out = {k: v for k, v in d.items() if k not in ("intake", "masters", "previews")}
    out["version"] = _version(series, d["id"])
    out["masters"] = [{**m, "url": _img_url(series, d["id"], m["file"])} for m in d.get("masters", [])]
    out["previews"] = [{"file": p, "url": _img_url(series, d["id"], p)} for p in d.get("previews", [])]
    return out


def _template_out(t):
    cat = _cat()
    out = {k: v for k, v in t.items() if k != "designs"}
    out["designs"] = [_design_out(t["series"], d) for d in t["designs"]]
    cfg = cat._design_cfg(t["series"], t["designs"][0]["id"]) if t["designs"] else None
    out["slots"] = cat._slots(cfg) if cfg else None
    out["schema_url"] = None                    # 예전 조판 틀의 data.json 스키마 — 2026-10-19 뺐다(계약 칸은 남김)
    return out


@bp.route("/catalog")
def catalog():
    dirs = _cat().directories()
    return jsonify({"dirs": [{**d, "templates": [_template_out(t) for t in d["templates"]]} for d in dirs],
                    "generated": time.time()})


@bp.route("/catalog/<series>/<design>")
def design_detail(series, design):
    cat = _cat()
    t = cat.template_info(series)
    if not t or not cat._ID.match(design):
        abort(404)
    d = next((x for x in t["designs"] if x["id"] == design), None)
    if not d:
        abort(404)
    cfg = cat._design_cfg(series, design) or {}
    out = _design_out(series, d)
    out["template"] = {k: t[k] for k in ("series", "name", "desc", "root", "ready", "dir", "dir_name",
                                         "pipeline", "fields", "slot_hint")}
    out["config"] = {k: cfg.get(k) for k in ("page", "palette", "fonts", "typeface", "print", "options")
                     if k in cfg}
    out["slots"] = cat._slots(cfg)
    if _editor_design(series, design):
        out["pages"] = _editor_fields(series, design)
    return jsonify(out)


def _editor_fields(series, design):
    """편집기 제작 디자인의 상위 페이지마다 데이터 필드 자리 — 바깥 화면이 그린 지면 위에 고치기 칸을 겹칠 때(contents 분석본 간지).
    → [{id, name, w, h, fields: [{bind, x, y, w, h, size, align}]}] — mm, 재단선 왼쪽 위가 0(도련 없이 찍은 그림과 같은 좌표)"""
    from routes.catalog import _ddir
    try:
        with open(os.path.join(_ddir(series, design), "units.json"), encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, ValueError):
        return []
    specs = {s.get("id"): s for s in pkg.get("specs") or []}
    out = []
    for pg in pkg.get("pages") or []:
        sp = specs.get(pg.get("spec")) or {}
        fields = []
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            b = a.get("bind")
            if not b or str(b).startswith("sys."):
                continue
            fields.append({"bind": b, "x": it.get("x", 0), "y": it.get("y", 0), "w": it.get("w") or a.get("w"), "h": it.get("h") or a.get("h"),
                           "size": a.get("size"), "align": a.get("align") or "left"})
        out.append({"id": pg.get("id"), "name": pg.get("name"), "w": sp.get("w"), "h": sp.get("h"), "fields": fields})
    return out


@bp.route("/catalog/<series>/<design>/image/<name>")
def design_image(series, design, name):
    cat = _cat()
    if not cat._ID.match(design) or not _IMG.match(name):
        abort(404)
    d = cat._ddir(series, design)
    if not os.path.exists(os.path.join(d, name)):
        abort(404)
    resp = send_from_directory(d, name)
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


# ── 편집기 제작 디자인 찍기 ─────────────────────────────────────
# 틀 = 디자인 폴더의 units.json(편집기 문서 묶음). 찍을 때 그 자리에서만 쓴다 — 편집기 데이터(라이브러리)에 들여오지 않고, 틀을 바꾸지 않는다.
# 원고 = contents 의 yos-workbook-v1 → core/sources/yos_editor 가 자리 원고로. 원고가 온 구성(「원고마다」 묶음)만 찍는다.
def _editor_design(series, design):
    from routes.catalog import _ddir
    try:
        with open(os.path.join(_ddir(series, design), "design.json"), encoding="utf-8") as f:
            return json.load(f).get("made") == "editor"
    except (OSError, ValueError):
        return False


def _editor_dir():
    """편집기 제작 디자인 찍기 폴더 — 스튜디오 루트의 _jobs/editor 아래(볼륨). 임시 폴더(/tmp)에 두면 배포·재시작 때 찍은 PDF 가
    사라져, 잡 기록은 남는데 쪽 그림·PDF 를 못 내줬다(contents 가 찍어 둔 지면을 다시 쓰려면 남아 있어야 한다, 2026-10-12)."""
    import tempfile
    root = os.path.join(jobs._dir(), "editor")
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix="editor_render_", dir=root)


def _render_editor(series, design, body, book):
    import tempfile
    from core.sources import yos_analysis, yos_editor
    from routes.catalog import _ddir
    src = body.get("source") or {}
    data = src.get("data") if isinstance(src, dict) and src.get("type") == "data" else None
    conv = {"yos-workbook-v1": yos_editor, "yos-analysis-v1": yos_analysis}.get((data or {}).get("format") if isinstance(data, dict) else None)
    if not conv:                                                         # 워크북 원고 · 분석본 조판 문서(contents 분석본 NEW)
        return jsonify({"error": "편집기 제작 디자인은 source.data(format yos-workbook-v1 · yos-analysis-v1)만 받는다"}), 400
    try:
        with open(os.path.join(_ddir(series, design), "units.json"), encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, ValueError):
        return jsonify({"error": "디자인 문서(units.json)가 없다"}), 400
    sample = (pkg.get("plan") or {}).get("content") or {}
    if isinstance(sample.get("원고"), list):                             # 레코드 차례 샘플 — 어댑터는 옛 꼴 샘플(책 머리 데이터 필드 · 유형 제목)을 읽는다
        from core.units import content as _content
        sample = _content.from_records(pkg.get("plan") or {}, {p["id"]: p for p in pkg.get("pages") or []}, sample)
    bare = conv is yos_editor and body.get("order") == "data"
    if bare:                                                             # 바깥이 정한 차례 그대로(contents 책 구성) — 틀의 앞뒤 쪽 없이
        content, rep = data_records(data, sample, yos_editor.template_caps(pkg))
    elif conv is yos_editor:                                             # 워크북 — 한 벌의 칸 수는 틀의 자리 수로
        content, rep = conv.to_content(data, sample, yos_editor.template_caps(pkg))
    else:
        content, rep = conv.to_content(data, sample)
    if content and not bare:
        content = records_for(pkg, content)
    if not content:
        return jsonify({"error": "이 디자인에 넣을 원고가 없다 — " + ", ".join(sorted({str(s.get("label") or s.get("key")) for s in rep["skipped"]})) + " 은(는) 아직 자리가 없다",
                        "report": rep}), 400
    d = _editor_dir()
    with open(os.path.join(d, "content.json"), "w", encoding="utf-8") as f:
        json.dump({"content": content, "report": rep}, f, ensure_ascii=False)
    with open(os.path.join(d, "source.json"), "w", encoding="utf-8") as f:   # 받은 원고 그대로 — 유형별 꼴을 실물로 대 볼 때(/renders/<jid>/source)
        json.dump(data, f, ensure_ascii=False)
    stem = re.sub(r"[^\w가-힣·() -]+", "_", str(book.get("title") or book.get("name") or design)).strip()[:80] or design
    u = current_user() or {}
    job = jobs.start("render", _run_editor_render,
                     meta={"book_dir": d, "key": f"editor/{series}/{design}", "bid": "", "stem": stem,
                           "series": series, "design": design, "design_version": _version(series, design),
                           "steps": ["editor"], "source": "data", "callback": body.get("callback"), "via": "api_v1",
                           "created_by": u.get("sub"), "report": rep, "print": body.get("print") is True, "bare": bare,
                           "web": body.get("pdf") is False})
    job.meta["bid"] = job.id
    return jsonify({"job": job.id, "book": {"key": job.meta["key"], "bid": job.id},
                    "status_url": url_for("api_v1.render_status", jid=job.id), "report": rep}), 202


def data_records(data, sample, caps):
    """워크북 원고를 **원고가 온 차례 그대로** 레코드 차례 원고로(order: data) — 틀의 쪽 차례(STEP 1 전부 → STEP 2 …)를 따르지 않는다.

    원고의 지문 칸(passages[i])이 곧 차례다. 지문 칸 하나 = 원고 유형 하나(contents 책 구성의 칸 갈래 — 본문정리(주제) = 본문정리 + 주제).
    지문 칸에 title(유형 이름)이 있으면 면 머리 제목 자리(「제목」)에 그 이름을 넣는다.
    잇닿은 지문 칸이 같은 항목 꼴이고 지문이 이어지면 한 덩어리(한 벌에 지문 여럿이 들어가는 면을 채우게).
    덩어리는 항목 전부를 한 번에 바꾼다 — 여러 항목이 한 면을 같이 채운다(B본문정리 = 본문정리 + 주제 · 제목 객관식).
    덩어리에서 면이 여럿 나오면 그 면을 채우는 항목이 처음 나온 차례로. 레코드마다 「_면」(구성 이름)을 달아 그 면으로 찍는다.
    지문 번호는 처음 나온 차례(같은 지문이 다시 오면 같은 번호). 면이 없는 원고(실전 한 줄기 등)는 report.skipped 로."""
    from core.sources import yos_editor
    ps = (data or {}).get("passages") or []
    num = {}
    for p in ps:
        num.setdefault((p.get("no"), p.get("content")), len(num) + 1)
    keys_of = lambda p: tuple(it.get("key") for it in p.get("items") or [])
    sig = lambda p: (p.get("title"), keys_of(p))                         # 같은 유형(이름 · 항목)끼리만 묶는다
    groups = []
    for p in ps:
        if groups and sig(groups[-1][-1]) == sig(p) and num[(p.get("no"), p.get("content"))] == num[(groups[-1][-1].get("no"), groups[-1][-1].get("content"))] + 1:
            groups[-1].append(p)
        else:
            groups.append([p])
    recs, rep = [], {"sent": [], "skipped": []}
    for g in groups:
        content, r = yos_editor.to_content(dict(data, passages=g), sample, caps, start=num[(g[0].get("no"), g[0].get("content"))])
        rep["sent"] += r["sent"]
        rep["skipped"] += r["skipped"]
        first = {}                                                       # 면 → 그 면을 채우는 항목이 처음 나온 차례
        for i, k in enumerate(dict.fromkeys(keys_of(g[0]))):
            one, _ = yos_editor.to_content(dict(data, passages=[dict(g[0], items=[it for it in g[0].get("items") or [] if it.get("key") == k])]), sample, caps)
            for face in one:
                first.setdefault(face, i)
        for face in sorted(content, key=lambda f: first.get(f, len(first))):
            v = content[face]
            if face not in caps:
                # 한 줄기 자리(실전 문제 「지문번호+번호+발문+…」) — 그 자리가 있는 쪽을 면으로(content._faces_by_chunk bare 가 「한 번만」 쪽도 면으로 본다)
                home = next((nm for nm, c in caps.items() if face in c), None) if "+" in face else None
                if home and isinstance(v, list) and v:
                    recs.append({face: v, "_면": home})
                elif "+" in face and v:
                    rep["skipped"].append({"passage": g[0].get("no"), "label": face, "why": "이 틀에 이 원고를 넣을 쪽이 없음"})
                continue
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                # 면 머리 제목 = 지문 칸의 원고 유형 이름(contents 책 구성 — 본문정리(주제)) — 틀 견본 제목(「본문 정리」)을 그대로 두지 않는다
                title = (g[0].get("title") or "").strip()
                recs += [dict(x, _면=face, **({"제목": title} if title and "제목" in x else {})) for x in v]
            elif v:
                rep["skipped"].append({"passage": g[0].get("no"), "label": face, "why": "이 틀에서 「원고마다」 면이 아니라 차례대로 못 넣음"})
    return ({"원고": recs} if recs else {}), rep


def records_for(pkg, content):
    """템플릿 샘플 레코드가 레코드 차례 꼴({원고: […]})이면 원고도 레코드 차례로(데이터 병합 원고 꼴 통일 — content.to_records). 아니면 그대로"""
    if not isinstance(((pkg.get("plan") or {}).get("content") or {}).get("원고"), list):
        return content
    from core.units import content as _content
    return _content.to_records(pkg.get("plan") or {}, {p["id"]: p for p in pkg.get("pages") or []}, content)


def _content_plan(pkg, content):
    """틀 문서에서 원고가 온 것만 남긴 문서 사본 — 책처럼(속표지 · 간지 · 차례 · 뒤붙이까지).

    - 「원고마다」 묶음: 원고가 온 구성만(이름 있는 면부터 다음 이름 있는 면 전까지)
    - 원고 자리가 있는 「한 번만」 면(실전 문제 한 줄기): 그 자리에 원고가 왔을 때만 — 그 글이 이어지는 면(같은 이야기)도 같이
    - 원고 자리가 없는 「한 번만」 면(꾸밈 면): 여러 번 나오는 꾸밈 면 중 맨 앞 것(STEP 간지)이 장(章)을 연다.
      장 안에 남는 원고 면이 있으면 그 장의 꾸밈 면(간지 · 차례)을 남기고, 없으면 장째 뺀다.
      첫 장 앞(속표지)과 맨 끝 꾸밈 면들(MEMO · 뒤표지)은 늘 남긴다"""
    import copy
    plan = copy.deepcopy(pkg.get("plan") or {})
    if isinstance(content.get("원고"), list):                            # 레코드 차례 원고 — 레코드마다 상위 페이지를 고른다(자동 상위 페이지 적용). 원고가 안 온 상위 페이지는 안 찍힌다
        return plan
    pages_by = {p["id"]: p for p in pkg.get("pages") or []}
    parts = {p["id"]: p for p in pkg.get("parts") or []}
    plain = lambda nm: not nm or re.fullmatch(r"빈 면 \d+", nm)
    atoms = lambda pg: [it.get("atom") or {} for it in pg.get("items") or []] + [a for it in pg.get("items") or [] for a in (parts.get(it.get("part")) or {}).get("atoms") or []]
    recs = lambda k: isinstance(content.get(k), list) and content[k] and isinstance(content[k][0], (dict, list))   # 문제 원고(레코드 · 한 줄기)
    flat = []                                                             # [(구간 번호, 항목, 쪽, 꾸밈 면인가)]
    for si, sec in enumerate(plan.get("sections") or []):
        for e in sec.get("pages") or []:
            e = e if isinstance(e, dict) else {"page": e, "repeat": "once"}
            pg = pages_by.get(e["page"]) or {}
            ats = atoms(pg)
            decor = e.get("repeat") != "each_set" and not any(a.get("story") or "+" in str(a.get("bind") or "") or recs(a.get("bind")) for a in ats)   # 꾸밈 면 — 책 이름(교재명) 정도만 받는다
            flat.append((si, e, pg, decor))
    keep, on, stories = [False] * len(flat), False, set()
    for i, (_, e, pg, decor) in enumerate(flat):
        nm = pg.get("name") or ""
        if e.get("repeat") == "each_set":
            if not plain(nm):
                on = isinstance(content.get(nm), list)
            keep[i] = on
        elif not decor:
            on = False
            st = {a["story"] for a in atoms(pg) if a.get("story")}
            if any(isinstance(content.get(a.get("bind")), list) for a in atoms(pg)) or st & stories:
                keep[i] = True
                stories |= st
        else:
            on = False
    names = [pg.get("name") or "" for _, _, pg, d in flat if d]
    opener = next((n for n in names if names.count(n) > 1), None)         # 장을 여는 꾸밈 면(STEP 간지)
    starts = [i for i, (_, _, pg, d) in enumerate(flat) if d and (pg.get("name") or "") == opener]
    if starts:
        tail = len(flat)
        while tail > starts[-1] + 1 and flat[tail - 1][3] and (flat[tail - 1][2].get("name") or "") != opener:
            tail -= 1                                                     # 맨 끝 꾸밈 면(MEMO · 뒤표지)
        for i in range(starts[0]):
            keep[i] = keep[i] or flat[i][3]                               # 속표지
        for i in range(tail, len(flat)):
            keep[i] = True
        for c, a in enumerate(starts):
            b = starts[c + 1] if c + 1 < len(starts) else tail
            if any(keep[i] and not flat[i][3] for i in range(a, b)):
                for i in range(a, b):
                    keep[i] = keep[i] or flat[i][3]
    for si, sec in enumerate(plan.get("sections") or []):
        sec["pages"] = [e for (s2, e, _, _), k in zip(flat, keep) if s2 == si and k]
        sec.pop("divider", None)
    return plan                                                           # 틀의 앞붙이 · 뒷붙이(front · back)는 그대로


@bp.route("/renders/<jid>/edit")
def render_edit(jid):
    """조판 결과 확인 — 찍은 쪽을 화면에 그리고(SVG), 원고 자리 글을 그 자리에서 바로 고친다. 고치면 /svgs 로 다시 짠다(틀·contents 원고는 안 바뀐다)."""
    from flask import render_template
    job = _find_job(jid)
    if not job or "editor" not in (job.meta.get("steps") or []):
        abort(404)
    if not os.path.exists(os.path.join(job.meta["book_dir"], "content.json")):
        abort(410)                                                        # 찍기 폴더가 없다(서버 다시 켜짐 등) — contents 에서 다시 찍어야 한다
    from core.units import fonts
    return render_template("render_edit.html", jid=jid, title=job.meta.get("stem") or "조판 결과",
                           font_css=fonts.fix_css() + fonts.face_css("url"))


@bp.route("/renders/<jid>/view")
def render_view(jid):
    """웹 보기 — pdf: false 로 찍은 쪽을 화면에 그린다(PDF 없이). 두 쪽씩(펼침면처럼) 창 폭에 맞추고, 좁으면 한 쪽씩.
    서체 · 단락 컴포저는 PDF 와 같다. 다 그리면 부모 창에 높이 · 쪽 수를 알린다(postMessage {yosView: {height, pages}}) — contents 가 iframe 높이를 맞춘다."""
    from core.units import fonts, pdf as _pdf
    job = _find_job(jid)
    if not job:
        abort(404)
    try:
        with open(os.path.join(job.meta.get("book_dir") or "", "svgs.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        abort(410)                                                        # pdf: false 로 찍지 않았거나 찍기 폴더가 없다(서버 다시 켜짐)
    w, h = float(data["w"]), float(data["h"])
    pages = "".join(f'<div class="p">{s}</div>' for s in data["svgs"])          # 쪽 하나 = 칸 하나 — 글이 안 닿은 이어 받는 쪽은 컴포저가 칸째 지운다
    fit = ("const W=" + f"{w * 96 / 25.4:.3f}" + ";"
           "function fit(){const g=document.querySelector('.g'),two=innerWidth>=700,cw=two?(innerWidth-6)/2:innerWidth,z=cw/W;"
           "g.style.gridTemplateColumns=two?'max-content max-content':'max-content';document.querySelectorAll('.p').forEach(p=>{p.style.zoom=z;});"
           "parent.postMessage({yosView:{height:document.documentElement.scrollHeight,pages:document.querySelectorAll('.p').length}},'*');}"
           "document.addEventListener('DOMContentLoaded',()=>(document.fonts?document.fonts.ready:Promise.resolve()).then(()=>setTimeout(fit,0)));"
           "addEventListener('resize',fit);")
    html = (f'<!doctype html><html><head><meta charset="utf-8"><title>{job.meta.get("stem") or "지면"}</title><style>'
            f'html,body{{margin:0;padding:0;background:transparent}} .g{{display:grid;column-gap:6px;row-gap:16px}} '
            f'.p{{width:{w}mm;height:{h}mm;overflow:hidden;background:#fff;box-shadow:0 0 0 1px #e3e6eb}} .p > svg{{display:block;width:{w}mm;height:{h}mm;overflow:hidden}} '
            f'.p svg .zone{{display:none}} .story-hint,.story-over{{display:none}}{fonts.fix_css()}{fonts.face_css("url")}'
            f'</style></head><body><div class="g">{pages}</div><script>{_pdf._compose_js()}</script><script>{fit}</script></body></html>')
    return html, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "private, max-age=600"}


@bp.route("/renders/<jid>/source")
def render_source(jid):
    """편집기 제작 디자인으로 찍을 때 받은 원고(yos-workbook-v1) 그대로 — 유형별 꼴 확인용"""
    job = _find_job(jid)
    if not job or "editor" not in (job.meta.get("steps") or []):
        abort(404)
    p = os.path.join(job.meta["book_dir"], "source.json")
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="application/json")


@bp.route("/renders/<jid>/merge", methods=["POST"])
def render_merge(jid):
    """조판 결과 → 편집기 문서(인디자인 「병합된 문서 만들기」) — 원고 글을 박은 보통 쪽들로 펼쳐 편집기에서 쪽마다 손본다.
    틀(정본 카드)과는 끊긴 새 문서다. 같은 원고로 다시 누르면 만든 문서로 간다. → {plan, url}"""
    import hashlib
    from core.units import package, pdf as _pdf, store
    from routes.units import _ctx, fill_svgs, merged_pages
    from routes.catalog import _ddir
    job = _find_job(jid)
    if not job or "editor" not in (job.meta.get("steps") or []):
        abort(404)
    try:
        with open(os.path.join(job.meta["book_dir"], "content.json"), encoding="utf-8") as f:
            content = json.load(f)["content"]
        with open(os.path.join(_ddir(job.meta["series"], job.meta["design"]), "units.json"), encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, ValueError, KeyError):
        abort(410)
    key = hashlib.sha1(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    done = job.meta.get("merged") or {}
    if done.get("key") == key and store.by_id(store.load("plans")).get(done.get("plan")):
        return jsonify({"plan": done["plan"], "url": f"/units?plan={done['plan']}"})
    lib, plan, skin = _editor_lib(job.meta, content)
    svgs, _rep, spec = fill_svgs(lib, plan, content, _ctx(lib, skin.get("id")), drop_empty=True)
    tmp = os.path.join(job.meta["book_dir"], "_merge_count.pdf")             # 크롬이 빈 덧쪽을 지운 뒤 몇 쪽인가 — 펼칠 때 덧쪽을 그만큼만
    _pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), tmp, title="count")
    import fitz
    used = len(fitz.open(tmp))
    pages = merged_pages(lib, plan, content, _ctx(lib, skin.get("id")), drop_empty=True, used=used)
    for i, p in enumerate(pages):
        p["id"] = f"merged_{i + 1}"
        p.pop("cont", None)
    doc = {k: v for k, v in plan.items() if k not in ("content", "catalog")}
    doc["front"], doc["back"] = [], []
    doc["from"] = {"series": job.meta["series"], "design": job.meta["design"]}   # 만든 템플릿 — 바뀐 레코드를 다시 흘려 넣을 때(books/<plan>/records)
    doc["sections"] = [{"id": "s1", "name": "본문", "pages": [{"page": p["id"], "repeat": "once"} for p in pages]}]
    try:
        with open(os.path.join(_ddir(job.meta["series"], job.meta["design"]), "design.json"), encoding="utf-8") as f:
            dname = json.load(f).get("name") or job.meta["design"]
    except (OSError, ValueError):
        dname = job.meta["design"]
    skin = dict(pkg.get("skin") or {}, id=f"{(pkg.get('skin') or {}).get('id') or 'base'}_{job.meta['design']}",   # 틀 브랜드 그대로 — 이 편집기의 같은 이름 브랜드 값이 끼어들지 않게
                name=f"{dname} 브랜드")
    doc["skin"] = skin["id"]
    pid, _r = package.load(dict(pkg, plan=doc, pages=pages, skin=skin), name=f"조판 결과 · {job.meta.get('stem') or jid}")
    job.meta["merged"] = {"key": key, "plan": pid}
    return jsonify({"plan": pid, "url": f"/units?plan={pid}"})


@bp.route("/renders/<jid>/svgs", methods=["POST"])
def render_svgs(jid):
    """조판 결과 화면의 쪽 그림 — {content?} 를 주면 그 원고로 바꿔 두고(찍기 폴더 content.json) 다시 짠다.
    → {svgs, recs, content}: recs = 면마다 [구성, 몇째 벌] 또는 null(덧쪽·원고 없는 면) — 화면이 고친 글을 원고 자리로 되돌릴 때"""
    from routes.units import _ctx, fill_svgs
    job = _find_job(jid)
    if not job or "editor" not in (job.meta.get("steps") or []):
        abort(404)
    p = os.path.join(job.meta["book_dir"], "content.json")
    try:
        with open(p, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        abort(410)
    content = (request.get_json(silent=True) or {}).get("content")
    if content is not None:
        if not isinstance(content, dict) or set(content) != set(saved["content"]):
            return jsonify({"error": "원고 꼴이 처음 찍은 것과 다르다"}), 400
        saved["content"] = content
        with open(p, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False)
    content = saved["content"]
    lib, plan, skin = _editor_lib(job.meta, content)
    recs = []
    svgs, _rep, _spec = fill_svgs(lib, plan, content, _ctx(lib, skin.get("id")), drop_empty=True, recs=recs)
    where = lambda rec: next(([k, i] for k, v in content.items() if isinstance(v, list) for i, r in enumerate(v) if r == rec), None)
    return jsonify({"svgs": svgs, "recs": [where(r) if r is not None else None for r in recs], "content": content})


@bp.route("/renders/<jid>/content", methods=["POST"])
def render_redraw(jid):
    """고친 원고로 다시 찍기 → {job} (새 찍기). 원고 꼴(구성 → 레코드 → 자리)은 처음 찍은 것과 같아야 한다."""
    import tempfile
    job = _find_job(jid)
    if not job or "editor" not in (job.meta.get("steps") or []):
        abort(404)
    content = (request.get_json(silent=True) or {}).get("content")
    if not isinstance(content, dict) or not content:
        return jsonify({"error": "content 가 필요하다"}), 400
    d = _editor_dir()                                                    # 새 폴더 — 쪽 그림 캐시가 예전 결과를 내주지 않게
    with open(os.path.join(d, "content.json"), "w", encoding="utf-8") as f:
        json.dump({"content": content, "report": job.meta.get("report")}, f, ensure_ascii=False)
    meta = {k: v for k, v in job.meta.items() if k not in ("book_dir", "bid", "callback", "plan")}   # 다시 그리기는 contents 에 웹훅을 안 보낸다
    new = jobs.start("render", _run_editor_render, meta=dict(meta, book_dir=d, bid="", redraw_of=jid))
    new.meta["bid"] = new.id
    return jsonify({"job": new.id}), 202


def _editor_lib(meta, content):
    """찍기의 틀(디자인 폴더 units.json) → (그리기 라이브러리, 원고가 온 구성만 남긴 문서, 브랜드). 틀 그림은 찍기 폴더에 풀어 절대 경로로"""
    import base64
    import copy
    from core.units import fonts as _fonts, store
    from routes.catalog import _ddir
    d = meta["book_dir"]
    with open(os.path.join(_ddir(meta["series"], meta["design"]), "units.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    skin = copy.deepcopy(pkg.get("skin") or {})
    img_dir = os.path.join(d, "_img")                                    # 틀 그림 — 이 작업 폴더에만 풀고 절대 경로로(편집기 그림 폴더와 섞지 않는다)
    os.makedirs(img_dir, exist_ok=True)
    for key, im in (pkg.get("images") or {}).items():
        p = os.path.join(img_dir, os.path.basename(im.get("name") or key))
        with open(p, "wb") as fh:
            fh.write(base64.b64decode(im.get("b64") or ""))
        skin.setdefault("images", {})[key] = p
    have = {x["file"] for x in _fonts.system_fonts()}
    for fn, b64 in (pkg.get("fonts") or {}).items():                    # 틀이 쓰는 올린 서체 — 이 서버에 없으면 등록
        if fn not in have:
            _fonts.register(fn, base64.b64decode(b64))
    specs = {s.get("id"): s for s in store.load("specs")}
    specs.update({s.get("id"): s for s in pkg.get("specs") or []})
    plan = _content_plan(pkg, content)
    pages_by = {p["id"]: p for p in pkg.get("pages") or []}
    lib = {"pages": list(pages_by.values()), "parts": pkg.get("parts") or [], "blocks": pkg.get("blocks") or [],
           "skins": [skin], "specs": list(specs.values()), "plans": [plan], "sets": []}
    return lib, plan, skin


def _run_editor_render(job, log):
    from routes.units import _ctx, fill_svgs
    d, series, design = job.meta["book_dir"], job.meta["series"], job.meta["design"]
    with open(os.path.join(d, "content.json"), encoding="utf-8") as f:
        content = json.load(f)["content"]
    t0 = time.time()
    lib, plan, skin = _editor_lib(job.meta, content)
    log(f"[편집기] 틀 읽기 {time.time() - t0:.1f}초")
    if job.meta.get("bare"):                                           # order: data — 앞뒤 쪽(속표지 · 간지 · 차례 · MEMO · 뒤표지) 없이 원고가 고른 면만
        plan["bare"] = True
    log(f"[편집기] {series}/{design} · 구성 {', '.join(content)} · 쪽 {sum(len(s['pages']) for s in plan.get('sections') or [])}")
    ctx = _ctx(lib, skin.get("id"))
    sp = next((s for s in lib["specs"] if s.get("id") == plan.get("spec")), None) or {}
    if job.meta.get("print"):                                          # print: true — 종이 = 판형 + 도련(재단선 없음, RGB). 다른 조판 PDF 와 이어 붙일 때(contents 분석본 간지)
        ctx.print = {"bleed": float(sp.get("bleed") or 3.0), "marks": False}
    t0 = time.time()
    svgs, rep, spec = fill_svgs(lib, plan, content, ctx, drop_empty=True)
    log(f"[편집기] 면 {len(svgs)} · 원고 {rep.get('filled')}자리" + (f" · 빈 자리 {rep['unfilled']}" if rep.get("unfilled") else "") + f" · 그리기 {time.time() - t0:.1f}초")
    if job.meta.get("web"):                                            # pdf: false — 웹에서만 본다(/renders/<id>/view). PDF(크롬) 없이 쪽 그림만 남긴다
        with open(os.path.join(d, "svgs.json"), "w", encoding="utf-8") as f:
            json.dump({"svgs": [s["svg"] if isinstance(s, dict) else s for s in svgs], "w": spec["w"], "h": spec["h"]}, f, ensure_ascii=False)
        job.rc = 0
        return {"pdfs": [], "main_pdf": None, "pages": len(svgs), "view": True, "report": job.meta.get("report"),
                "fill": {"filled": rep.get("filled"), "unfilled": rep.get("unfilled")}}
    res = _print_pdf(job, svgs, spec, ctx, log)
    res.update(report=job.meta.get("report"), fill={"filled": rep.get("filled"), "unfilled": rep.get("unfilled")})
    return res


def _print_pdf(job, svgs, spec, ctx, log):
    """면 SVG → 잡 폴더 PDF(+ blob) — 조판(원고 넣기)과 책(병합된 문서) 찍기가 같이 쓴다. 넘침(크롬이 그린 빨간 +)은 경고로."""
    from core.units import pdf as _pdf
    d = job.meta["book_dir"]
    main = job.meta["stem"] + ".pdf"
    seen = {}                                                          # 크롬이 그린 넘침 — pdf.to_pdf 가 채운다
    t0 = time.time()
    if job.meta.get("print"):
        _pdf.to_print_pdf(svgs, float(spec["w"]), float(spec["h"]), os.path.join(d, main), bleed=ctx.print["bleed"], marks=False,
                          cmyk=False, title=job.meta["stem"], log=log, report=seen)
    else:
        _pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), os.path.join(d, main), title=job.meta["stem"], report=seen)
    log(f"[PDF] {time.time() - t0:.1f}초")
    pages = None
    try:
        import fitz
        pages = len(fitz.open(os.path.join(d, main)))
    except Exception:                                                  # noqa: BLE001
        pass
    uploaded = {}
    if blob.enabled():
        t0 = time.time()
        try:
            r = blob.put_file(os.path.join(d, main), f"renders/{job.id}/{main}", "application/pdf", access=blob.pdf_access())
            if r:
                uploaded[main] = {"url": r["url"], "pathname": r["pathname"], "access": r["access"]}
        except Exception as e:                                         # noqa: BLE001 — 업로드 실패가 조판 결과를 지우면 안 된다
            log(f"[blob] {main} 업로드 실패: {e}")
        log(f"[blob] {time.time() - t0:.1f}초")
    over = [{"page": n, "text": t} for n, ts in seen.get("overset") or [] for t in ts]
    for o in over:                                                     # 넘침 — 글상자에 다 안 들어가 잘린 글(인디자인 빨간 +). 산출은 내되 경고로
        log(f"[넘침] {o['page']}쪽 · {o['text']}…")
    job.rc = 1 if over else 0
    return {"pdfs": [main], "main_pdf": main, "pages": pages, "verify_ok": not over, "overset": over, "blob": uploaded}


@bp.route("/books/<pid>/renders", methods=["POST"])
def book_render(pid):
    """책(병합된 문서, /renders/<jid>/merge 가 만든 것)을 편집기에서 손본 그대로 찍는다. {print?: true} 면 판형 + 도련.
    → {job, status_url} — 상태 · 파일 · 쪽 그림은 조판과 같은 /renders/<job>/…"""
    from core.units import store
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", pid or "") or not store.by_id(store.load("plans")).get(pid):
        abort(404)
    body = request.get_json(silent=True) or {}
    plan = store.by_id(store.load("plans"))[pid]
    stem = re.sub(r"[^\w가-힣·() -]+", "_", str(plan.get("name") or pid)).strip()[:80] or pid
    u = current_user() or {}
    job = jobs.start("render", _run_book_render,
                     meta={"book_dir": _editor_dir(), "key": f"book/{pid}", "bid": "", "stem": stem, "plan": pid,
                           "steps": ["book"], "source": "book", "callback": body.get("callback"), "via": "api_v1",
                           "created_by": u.get("sub"), "print": body.get("print") is True})
    job.meta["bid"] = job.id
    return jsonify({"job": job.id, "status_url": url_for("api_v1.render_status", jid=job.id)}), 202


@bp.route("/books/<pid>", methods=["DELETE"])
def book_delete(pid):
    """책(병합된 문서) 지우기 — 바깥 시스템이 책을 다시 만들 때 예전 책을 치운다. 템플릿 문서(관리 카드에 이어진 것)는 안 지운다."""
    from core.units import store
    plan = store.by_id(store.load("plans")).get(pid) if re.match(r"^[A-Za-z0-9_-]{1,64}$", pid or "") else None
    if not plan:
        abort(404)
    if plan.get("catalog"):
        return jsonify({"error": "템플릿 문서는 지울 수 없다"}), 400
    store.delete("plans", pid)
    return jsonify({"ok": True})


def _book_plan(pid):
    from core.units import store
    plan = store.by_id(store.load("plans")).get(pid) if re.match(r"^[A-Za-z0-9_-]{1,64}$", pid or "") else None
    if not plan or plan.get("catalog"):
        abort(404)
    return plan


def _book_records(plan):
    """병합된 문서의 태그(데이터 필드였던 프레임의 레코드 id · 데이터 필드) → 레코드들(인디자인 XML 내보내기).
    한 줄기 글(문단 첫머리 자리 표시)은 content.story_records 로 [{자리: 값}, …] 에 되돌린다. 같은 데이터 필드가 여러 프레임이면 먼저 나온 것.
    → (레코드 id 차례, {id: {데이터 필드: 값}}, {id: [페이지 id …]})"""
    from core.units import content, store
    pages = store.by_id(store.load("pages"))
    order, recs, where = [], {}, {}
    for pid in content.plan_page_ids(plan):
        pg = pages.get(pid) or {}
        t = pg.get("tag") or {}
        if t.get("rec") is not None:
            rid = str(t["rec"])
            if rid not in recs:
                order.append(rid)
                recs[rid] = {}
            where.setdefault(rid, []).append(pid)
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            tg = a.get("tag") or {}
            if tg.get("rec") is None or not tg.get("field"):
                continue
            rid, f = str(tg["rec"]), tg["field"]
            if rid not in recs:
                order.append(rid)
                recs[rid] = {}
            if f in recs[rid]:
                continue
            v = a.get("text")
            if "+" in f:
                recs[rid][f] = content.story_records(f, v)
            elif isinstance(v, list) and any(isinstance(x, dict) and "ps" in x for x in v):
                rs = content.story_records(f, v)
                recs[rid][f] = rs[0].get(f, "") if rs else ""
            else:
                recs[rid][f] = v
    return order, recs, where


@bp.route("/books/<pid>/records")
def book_records(pid):
    """병합된 문서에서 고친 글 → 레코드(XML 내보내기). → {order, records: {id: {데이터 필드: 값}}, pages: {id: [페이지 id]}}"""
    order, recs, where = _book_records(_book_plan(pid))
    return jsonify({"order": order, "records": recs, "pages": where})


@bp.route("/books/<pid>/docs", methods=["POST"])
def book_docs(pid):
    """분석본 병합된 문서 → contents 조판 문서(사본) — {bases: {레코드 id: 보냈던 사본}} → {docs: {id: {doc, changed}}, missing: [id]}
    문서에서 고친 글 · 문자 스타일 · 윗주를 사본의 문장(태깅본 · 역할) · 해석 · 주제 · 문제 · 어휘로 되돌린다(core/sources/yos_analysis.to_doc —
    문자 스타일이 곧 역할). 레코드 페이지 재정의(사본 overrides)는 그대로 둔다 — 배치는 문서 몫."""
    from core.sources import yos_analysis
    plan = _book_plan(pid)
    if (plan.get("from") or {}).get("series") != "analysis":
        return jsonify({"error": "분석본으로 만든 병합된 문서가 아니다"}), 400
    bases = (request.get_json(silent=True) or {}).get("bases") or {}
    if not isinstance(bases, dict):
        return jsonify({"error": "bases 는 {레코드 id: 사본}"}), 400
    _, recs, _ = _book_records(plan)
    out, missing = {}, []
    for rid, base in bases.items():
        rec = recs.get(str(rid))
        if not isinstance(base, dict) or rec is None:
            missing.append(rid)
            continue
        rec = dict(rec)
        rows = rec.get(yos_analysis.ROWS)
        if isinstance(rows, list):
            rec[yos_analysis.ROWS] = [dict(r, 문장=r.get("문장") if isinstance(r.get("문장"), list) else [r.get("문장") or ""]) for r in rows]
        if isinstance(base.get("overrides"), dict):
            rec["_overrides"] = base["overrides"]
        doc, changed = yos_analysis.to_doc(rec, base)
        out[str(rid)] = {"doc": doc, "changed": changed}
    return jsonify({"docs": out, "missing": missing})


@bp.route("/books/<pid>/records/<rid>", methods=["POST"])
def book_record_put(pid, rid):
    """바뀐 레코드를 병합된 문서의 그 태그 프레임에 다시 흘려 넣는다(인디자인 XML 가져오기 · 내용 병합) — 프레임 자리 · 크기 · 페이지는 그대로.
    {doc}(분석본 사본) 또는 {record}. 만든 템플릿(plan.from)에 그 레코드만 넣어 데이터 필드 값을 짓고, 같은 레코드 · 같은 페이지 차례 · 같은 데이터 필드 프레임의 글을 바꾼다.
    → {ok, frames: 바꾼 프레임 수}"""
    import tempfile
    from core.sources import yos_analysis
    from core.units import store
    from routes.units import _ctx, _filled
    plan = _book_plan(pid)
    src = plan.get("from") or {}
    body = request.get_json(silent=True) or {}
    if isinstance(body.get("record"), dict):
        rec = dict(body["record"])
    elif isinstance(body.get("doc"), dict) and src.get("series") == "analysis":
        rec = yos_analysis.record(body["doc"])
    else:
        return jsonify({"error": "doc(분석본 사본) 또는 record 가 필요하다"}), 400
    rec["_id"] = str(rid)
    try:
        with open(os.path.join(_cat()._ddir(src.get("series") or "", src.get("design") or ""), "units.json"), encoding="utf-8") as f:
            pkg = json.load(f)
    except (OSError, ValueError, TypeError):
        return jsonify({"error": "만든 템플릿을 찾을 수 없다(예전 병합된 문서는 다시 만든다)"}), 400
    content = {"원고": [rec]}                                              # 레코드 차례 — 자동 상위 페이지 적용이 데이터 필드가 맞는 상위 페이지를 고른다
    with tempfile.TemporaryDirectory() as td:
        lib, tplan, skin = _editor_lib({"book_dir": td, "series": src["series"], "design": src["design"]}, content)
        seq, _rep, _so, _sp = _filled(lib, tplan, content, _ctx(lib, skin.get("id")), drop_empty=True)
    vals = {}
    for pg, r, _ in seq:
        if not isinstance(r, dict) or str(r.get("_id")) != str(rid):
            continue
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            if a.get("bind") and not str(a["bind"]).startswith("sys.") and a["bind"] in (it.get("fields") or {}):
                vals.setdefault((str(pg.get("_rk")), a["bind"]), it["fields"][a["bind"]])
    pages = store.by_id(store.load("pages"))
    n = 0
    for pgid in _book_records(plan)[2].get(str(rid), []):
        pg = pages.get(pgid)
        rk = str((pg.get("tag") or {}).get("rk"))
        hit = False
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            tg = a.get("tag") or {}
            if str(tg.get("rec")) == str(rid) and (rk, tg.get("field")) in vals:
                a["text"] = vals[(rk, tg["field"])]
                n += 1
                hit = True
        if hit:
            store.put("pages", pg)
    return jsonify({"ok": True, "frames": n})


def _run_book_render(job, log):
    from core.units import render, store
    from routes.units import _ctx
    lib = store.library()
    plan = store.by_id(lib["plans"]).get(job.meta["plan"])
    if not plan:
        raise RuntimeError("책 문서가 없다 — " + job.meta["plan"])
    ctx = _ctx(lib, plan.get("skin"))
    spec = store.by_id(lib["specs"]).get(plan.get("spec")) or render.DEFAULT_SPEC
    if job.meta.get("print"):
        ctx.print = {"bleed": float(spec.get("bleed") or 3.0), "marks": False}
    svgs = render.plan_svgs(ctx, plan, lib["sets"], lib)
    log(f"[책] {plan.get('name') or plan['id']} · 면 {len(svgs)}")
    if not svgs:
        raise RuntimeError("그릴 면이 없다")
    return _print_pdf(job, svgs, spec, ctx, log)


def _job_out(job, since=0):
    d = job.to_dict(since=since)
    base = _public_base()
    d["urls"] = {"status": base + url_for("api_v1.render_status", jid=job.id)}
    for f in (d.get("result") or {}).get("pdfs") or []:
        d["urls"][f] = base + url_for("api_v1.render_file", jid=job.id, name=f)
    if (d.get("result") or {}).get("main_pdf"):
        d["urls"]["page"] = base + url_for("api_v1.render_page", jid=job.id, n=1)[:-5] + "{n}.png"
    return d


def _find_job(jid):
    if not re.match(r"^[a-f0-9]{8,12}$", jid or ""):
        return None
    return jobs.get(jid)


@bp.route("/renders", methods=["POST"])
def render_create():
    cat = _cat()
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON 본문이 필요하다"}), 400
    series, design = str(body.get("series", "")), str(body.get("design", ""))
    book = body.get("book") or {}
    if not isinstance(book, dict):
        return jsonify({"error": "book 은 객체여야 한다"}), 400
    meta = cat._meta().get(series)
    if not meta:
        return jsonify({"error": "모르는 틀"}), 400
    if not _editor_design(series, design):
        return jsonify({"error": "편집기 제작 디자인만 찍는다 — 예전 조판 디자인은 2026-10-19 뺐다"}), 400
    return _render_editor(series, design, body, book)


@bp.route("/renders")
def render_list():
    return jsonify({"renders": [_job_out(j) for j in jobs.recent(kind="render", limit=50)]})


@bp.route("/renders/<jid>")
def render_status(jid):
    job = _find_job(jid)
    if not job:
        abort(404)
    since = int(request.args.get("since", 0) or 0)
    return jsonify(_job_out(job, since=since))


@bp.route("/renders/<jid>/files/<name>")
def render_file(jid, name):
    job = _find_job(jid)
    if not job or not _FILE_OK.match(name) or ".." in name:
        abort(404)
    d = job.meta["book_dir"]
    if not os.path.exists(os.path.join(d, name)):
        abort(404)
    return send_from_directory(d, name, as_attachment=name.endswith(".pdf") and
                               request.args.get("download") == "1")


@bp.route("/renders/<jid>/pages/<int:n>.png")
def render_page(jid, n):
    job = _find_job(jid)
    if not job or n < 1:
        abort(404)
    main = (job.result or {}).get("main_pdf")
    if not main:
        abort(404)
    dpi = max(36, min(int(request.args.get("dpi", 72) or 72), 200))
    d = job.meta["book_dir"]
    cache = os.path.join(d, "build", "_pages")
    os.makedirs(cache, exist_ok=True)
    out = os.path.join(cache, f"{os.path.splitext(main)[0]}_{n}_{dpi}.png")
    if not os.path.exists(out):
        import fitz
        doc = fitz.open(os.path.join(d, main))
        if n > len(doc):
            abort(404)
        doc[n - 1].get_pixmap(dpi=dpi).save(out)
    resp = send_file(out, mimetype="image/png")
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


# ── 웹훅 ────────────────────────────────────────────────────────
def _on_finish(job):
    if job.kind != "render":
        return
    base = (os.environ.get("YONE_PUBLIC_URL") or "").strip().rstrip("/")
    files = {f: f"{base}/api/v1/renders/{job.id}/files/{f}" for f in (job.result or {}).get("pdfs") or []}
    yos_hooks.send("render.finished",
                {"render": {"id": job.id, "status": job.status, "rc": job.rc, "error": job.error,
                            "book": {"key": job.meta.get("key"), "bid": job.meta.get("bid")},
                            "series": job.meta.get("series"), "design": job.meta.get("design"),
                            "design_version": job.meta.get("design_version"),
                            "result": job.result, "files": files,
                            "status_url": f"{base}/api/v1/renders/{job.id}",
                            "callback": job.meta.get("callback")}},
                log=job.add)


def install(app):
    app.register_blueprint(bp)
    jobs.on_finish(_on_finish)
    return app
