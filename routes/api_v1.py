# -*- coding: utf-8 -*-
"""`/api/v1` — **contents · core · 앱이 부르는 바깥용 API.**

화면용 `/api/catalog/*`·`/api/book-studio/*` 와 달리 이쪽은 계약이다: 모양을 바꾸면 v2 로.

    GET  /api/v1/health                              살아 있나 (인증 없음)
    GET  /api/v1/catalog                             디렉토리 → 틀 → 디자인 (미리보기 URL·version 포함)
    GET  /api/v1/catalog/<series>/<design>           디자인 하나 + config 요약
    GET  /api/v1/catalog/<series>/<design>/image/<name>   master_N.png · preview_N.png
    GET  /api/v1/catalog/<series>/schema             그 틀의 data.json 스키마 (있는 계열만)
    GET  /api/v1/books                               조판된 책 목록
    POST /api/v1/renders                             조판 잡 만들기 (아래)
    GET  /api/v1/renders                             최근 잡
    GET  /api/v1/renders/<id>?since=N                상태·로그·산출
    GET  /api/v1/renders/<id>/files/<name>           PDF · 로그 · data.json
    GET  /api/v1/renders/<id>/pages/<n>.png?dpi=72   면 그림
    POST /api/v1/embed-token                         contents iframe 용 짧은 주소

POST /renders 본문 (JSON):
    {
      "series": "vocabook", "design": "d1",
      "book":   {"name": "이의1보카", "period": "27-1-중간", "school": "이의고", "title": "…"},
      "source": {"type": "data", "data": {…}}          ← 또는 {"type":"plan","plan":{…}}
                                                          또는 {"type":"yos", "school":…, "grade":…, "week":…}
      "knobs":  {"palette.s1": "#77a1c4"},              ← (선택) 디자인 손잡이 덮어쓰기
      "print":  true,                                   ← (선택) 인쇄본(CMYK) 도 (기본 true)
      "replace": false,                                 ← (선택) 같은 책 폴더가 있으면 그 위에 다시
      "callback": {"ref": "…"}                          ← (선택) 웹훅에 그대로 되돌려 줄 값
    }
    multipart/form-data 로 원고 **파일**을 보내면 카탈로그의 "원고 넣기"와 같은 길(파서)을 탄다
    — 필드 이름은 `/api/catalog/create` 와 같다(series·design·name·period·school·slot_*).

응답: {"job": "<id>", "book": {"key": …, "bid": …}, "status_url": "/api/v1/renders/<id>"}
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time

from flask import Blueprint, abort, jsonify, request, send_file, send_from_directory, url_for

from core import blob, jobs, yos_hooks
from core.sources import SourceError, resolve as resolve_source
from core.webauth import current_user, is_service, make_embed_token

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1"
_IMG = re.compile(r"^(master|preview)_\d+\.png$")
_FILE_OK = re.compile(r"^[^/\\]+\.(pdf|json|txt)$")


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
    from core.render_vivlio import cli as vcli
    from core.webauth import mode
    from routes.intake import have_key
    running = [j.id for j in jobs.recent(limit=200) if j.status == "running"]
    return jsonify({"ok": True, "api": VERSION, "auth": mode(), "vivliostyle": vcli.cli_available(),
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
    p = os.path.join(REPO, "core", "render_vivlio", "series", t["series"], "data.schema.json")
    out["schema_url"] = (_public_base() + url_for("api_v1.series_schema", series=t["series"])
                         if os.path.exists(p) else None)
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
    return jsonify(out)


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


@bp.route("/catalog/<series>/schema")
def series_schema(series):
    p = os.path.join(REPO, "core", "render_vivlio", "series", series, "data.schema.json")
    if not re.match(r"^[a-z][a-z0-9_]*$", series) or not os.path.exists(p):
        return jsonify({"error": "이 틀은 아직 data.json 스키마 파일이 없다",
                        "hint": f"core/render_vivlio/series/{series}/data.schema.json"}), 404
    return send_file(p, mimetype="application/schema+json")


# ── 책 ──────────────────────────────────────────────────────────
@bp.route("/books")
def books():
    from routes.books import books as _books
    return jsonify({"books": _books()})


# ── 렌더 ────────────────────────────────────────────────────────
def _python():
    return _cat()._python()


def _print_wanted(cfg, body):
    if body.get("print") is False:
        return False
    raw = cfg.get("print")
    if raw is False or (isinstance(raw, dict) and raw.get("off")):
        return False
    return True


def _prepare_book(series, design, book, knobs_over, fields, replace):
    """디자인 → 새 책 폴더(config·css·자산). 카탈로그의 create 와 같은 규칙, 원고만 없다.

    돌려주는 것: (out_dir, rel, stem, cfg_dict)
    """
    from core.render_vivlio import knobs as kn
    cat = _cat()
    meta = cat._meta().get(series)
    if not meta or not cat._ID.match(design):
        raise ValueError("모르는 틀·디자인")
    cfg_p = os.path.join(cat._ddir(series, design), "config.json")
    if not os.path.exists(cfg_p):
        raise ValueError("디자인 설정이 없다")
    if meta.get("ready") == "manual":
        raise ValueError("이 틀은 API 로 못 만든다 (README_로컬실행.md)")
    name = cat._safe_name(book.get("name", ""))
    period = cat._safe_name(book.get("period", ""))
    school = cat._nfc(book.get("school", "")).strip()
    title = cat._nfc(book.get("title", "")).strip() or name
    if not name or not period:
        raise ValueError("book.name 과 book.period 는 꼭 있어야 한다 (예: 이의1보카 / 27-1-중간)")
    rel = os.path.join("조판", "교재", meta.get("root", series), name, period)
    out_dir = os.path.join(cat._studio(), rel)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not replace:
        raise FileExistsError(f"이미 있는 책이다: {rel} — replace:true 로 그 위에 다시 만들거나 period 를 바꿀 것")
    os.makedirs(os.path.join(out_dir, "원고"), exist_ok=True)
    raw = open(cfg_p, encoding="utf-8").read()
    changes = {"book.title": title, "book.period": period, "output.dir": "."}
    if school:
        changes["book.school"] = school
    stem = f"{school}_{name}_내지" if school else f"{name}_내지"
    changes["output.stem"] = stem
    for k, v in (knobs_over or {}).items():
        if isinstance(k, str) and re.match(r"^[a-z_][a-z0-9_.-]*$", k):
            changes[k] = v
    try:
        raw = kn.patch_text(raw, changes)
    except Exception:
        raw = json.dumps(kn.apply(json.loads(raw), changes), ensure_ascii=False, indent=2) + "\n"
    cfg_out = json.loads(raw)
    try:
        dj = json.load(open(os.path.join(cat._ddir(series, design), "design.json"), encoding="utf-8"))
        dname = dj.get("name", design)
    except Exception:
        dname = design
    cfg_out["_카탈로그"] = {"series": series, "design": design, "design_name": dname,
                           "design_version": _version(series, design),
                           "made": datetime.date.today().isoformat(), "via": "api_v1"}
    return out_dir, rel, stem, cfg_out, meta


def _write_book(out_dir, cfg_out, series, design, fields, meta, kind, obj):
    cat = _cat()
    if kind == "plan":
        os.makedirs(os.path.join(out_dir, "원고"), exist_ok=True)
        with open(os.path.join(out_dir, "원고", "render_plan.json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        cfg_out.setdefault("manuscript", {})
        if isinstance(cfg_out["manuscript"], dict):
            cfg_out["manuscript"]["plan"] = "${BOOK}/원고/render_plan.json"
    with open(os.path.join(out_dir, "config.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg_out, ensure_ascii=False, indent=2) + "\n")
    ov = os.path.join(cat._ddir(series, design), "overrides.css")
    if os.path.exists(ov):
        shutil.copy2(ov, os.path.join(out_dir, "overrides.css"))
    for sub in ("assets", "참고"):
        src = os.path.join(cat._ddir(series, design), sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(out_dir, sub), dirs_exist_ok=True)
    job_dir = os.path.join(out_dir, "원고", "_job")
    os.makedirs(job_dir, exist_ok=True)
    for fld in meta.get("fields") or []:
        v = cat._nfc(str((fields or {}).get(fld["key"], ""))).strip() or fld.get("default", "")
        with open(os.path.join(job_dir, fld["key"] + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(v)
    if kind == "data":
        # 계열이 data 자리를 다르게 둘 수 있다(중등부·포켓북) — 계열에게 묻는다
        from core.render_vivlio import book as bookmod
        try:
            p = bookmod._series(bookmod.load(out_dir)).data_path(bookmod.load(out_dir))
        except Exception:
            p = os.path.join(out_dir, "data.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)


def _run_render(job, log):
    d = job.meta["book_dir"]
    cmd = [_python(), "-u", "-m", "core.render_vivlio.book", d] + job.meta["steps"]
    job.rc = jobs.run_cmd(job, cmd, cwd=REPO, timeout=1800)
    pdfs = sorted(f for f in os.listdir(d)
                  if f.lower().endswith(".pdf") and "measure" not in f and "_시안_" not in f)
    main = next((f for f in pdfs if f.startswith(job.meta["stem"]) and "인쇄" not in f and "CMYK" not in f),
                pdfs[0] if pdfs else None)
    pages = None
    if main:
        try:
            import fitz
            pages = len(fitz.open(os.path.join(d, main)))
        except Exception:
            pass
    uploaded = {}
    if pdfs and blob.enabled():
        # contents·core 와 같은 Blob 스토어에 — contents 는 pathname 을 저장하고 presignUrl 로 연다
        for f in pdfs:
            try:
                r = blob.put_file(os.path.join(d, f), f"renders/{job.id}/{f}", "application/pdf",
                                  access=blob.pdf_access())
                if r:
                    uploaded[f] = {"url": r["url"], "pathname": r["pathname"], "access": r["access"]}
                    log(f"[blob] {f} → {r['pathname']}")
            except Exception as e:                        # noqa: BLE001 — 업로드 실패가 조판 결과를 지우면 안 된다
                log(f"[blob] {f} 업로드 실패: {e}")
    with open(os.path.join(d, "조판_로그.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(job.log) + "\n")
    if not pdfs:
        job.status = "failed"
        job.error = job.error or "PDF 가 나오지 않았다"
    return {"pdfs": pdfs, "main_pdf": main, "pages": pages, "verify_ok": job.rc == 0, "blob": uploaded}


def _job_out(job, since=0):
    d = job.to_dict(since=since)
    base = _public_base()
    d["urls"] = {"status": base + url_for("api_v1.render_status", jid=job.id)}
    for f in (d.get("result") or {}).get("pdfs") or []:
        d["urls"][f] = base + url_for("api_v1.render_file", jid=job.id, name=f)
    if (d.get("result") or {}).get("main_pdf"):
        d["urls"]["page"] = base + url_for("api_v1.render_page", jid=job.id, n=1)[:-5] + "{n}.png"
    bid = (d.get("meta") or {}).get("bid")
    if bid:
        d["urls"]["studio"] = base + "/book-studio?b=" + bid
    return d


def _from_catalog_job(jid):
    """카탈로그 화면(원고 파일)으로 만든 잡도 같은 모양으로."""
    j = _cat().JOBS.get(jid)
    if not j:
        return None
    job = jobs.Job("render", {"book_dir": j["book_dir"], "key": j["key"], "bid": j["bid"],
                              "stem": j["stem"], "series": j["series"], "design": j["design"],
                              "steps": ["all"], "via": "catalog"})
    job.id, job.status, job.log, job.started = jid, j["status"], j["log"], j["started"]
    job.rc = j.get("rc")
    if j.get("pdfs"):
        job.result = {"pdfs": j["pdfs"], "main_pdf": j["pdfs"][0], "verify_ok": j.get("rc") == 0}
    return job


def _find_job(jid):
    if not re.match(r"^[a-f0-9]{8,12}$", jid or ""):
        return None
    return jobs.get(jid) or _from_catalog_job(jid)


@bp.route("/renders", methods=["POST"])
def render_create():
    cat = _cat()
    if request.files or (request.form and not request.is_json):
        # 원고 파일 — 카탈로그의 "원고 넣기"와 같은 길
        resp = cat.create()
        payload, code = (resp if isinstance(resp, tuple) else (resp, 200))
        data = payload.get_json(silent=True) or {}
        if code != 200 or "job" not in data:
            return payload, code
        return jsonify({"job": data["job"], "book": {"key": data.get("key"), "bid": data.get("bid")},
                        "status_url": url_for("api_v1.render_status", jid=data["job"])}), 202

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
    try:
        kind, obj = resolve_source(body.get("source"), series, log=None)
    except SourceError as e:
        return jsonify({"error": str(e)}), 400
    if kind == "plan" and meta.get("pipeline") != "workbook_v2":
        return jsonify({"error": f"plan 은 워크북 계열에만 쓴다 (이 틀: {series})"}), 400
    try:
        out_dir, rel, stem, cfg_out, meta = _prepare_book(series, design, book, body.get("knobs"),
                                                          body.get("fields"), bool(body.get("replace")))
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except OSError as e:
        return jsonify({"error": f"책 폴더를 못 만들었다 (스튜디오 루트 권한·용량 확인): {e}"}), 500
    try:
        _write_book(out_dir, cfg_out, series, design, body.get("fields"), meta, kind, obj)
    except Exception as e:                                    # noqa: BLE001
        return jsonify({"error": f"책 폴더를 못 만들었다: {e}"}), 500
    steps = ["build"] + (["print"] if _print_wanted(cfg_out, body) else []) + ["verify"]
    u = current_user() or {}
    job = jobs.start("render", _run_render,
                     meta={"book_dir": out_dir, "key": rel, "bid": cat._bid(rel), "stem": stem,
                           "series": series, "design": design,
                           "design_version": cfg_out["_카탈로그"]["design_version"],
                           "steps": steps, "source": (body.get("source") or {}).get("type"),
                           "callback": body.get("callback"), "via": "api_v1",
                           "created_by": u.get("sub")})
    return jsonify({"job": job.id, "book": {"key": rel, "bid": job.meta["bid"]},
                    "status_url": url_for("api_v1.render_status", jid=job.id)}), 202


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


# ── 임베드 ──────────────────────────────────────────────────────
@bp.route("/embed-token", methods=["POST"])
def embed_token():
    """contents 가 iframe 에 넣을 주소. {next:"/book-studio?b=<bid>", ttl:300, user:{…}}"""
    body = request.get_json(silent=True) or {}
    nxt = str(body.get("next") or "/book-studio")
    ttl = int(body.get("ttl") or 300)
    user = current_user() or {}
    if is_service():
        # 시스템이 대신 발급할 때는 누구 세션인지 적어 준다
        user = body.get("user") or {"sub": "contents", "name": "contents", "role": "user"}
    try:
        t = make_embed_token(nxt, user, ttl=ttl)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    url = _public_base() + url_for("webauth.embed") + "?t=" + t
    return jsonify({"url": url, "expires_in": ttl})


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
