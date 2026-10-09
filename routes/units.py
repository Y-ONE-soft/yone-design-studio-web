# -*- coding: utf-8 -*-
"""단위 — 원자로 부품을, 부품으로 블록을, 블록으로 지면·틀을 만든다. 옷을 갈아입히고 세트(콘텐츠)를 흘려 본다.

    /units                         캔버스 — 지면 고르기·칸 그리기·블록/부품 끌어 놓기·옷 바꾸기 (사용자 화면)
    /units/library                 라이브러리·분해·JSON — 왼쪽 분해·라이브러리, 가운데 미리보기(SVG), 오른쪽 JSON 편집
    /api/units/thumbs              팔레트 썸네일 {blocks:{id:svg}, parts:{id:svg}}
    /api/units/library             전부
    /api/units/<kind>  POST        하나 저장(스키마 대조) · DELETE {id}
    /api/units/preview POST        {kind, item|id, skin, sets} → {svgs:[{svg,label}], warnings}
    /api/units/upload  POST        PDF·이미지 올리기 → {id, pages}
    /api/units/decompose POST      {upload, page} | {upload(이미지)} | {prompt} → decomposed (+ 임시 옷 src_<id> 저장)
    /api/units/part_from POST      {dec, atoms:[번호], id, name} → 부품 저장
    /api/units/make POST           {prompt, skin} → 클로드가 그린 부품 + 블록 저장 (캔버스의 "설명으로 만들기")
    /api/units/pdf?plan=|page=     PDF 저장 — 크로미움 인쇄 (core/units/pdf.py). ?skin= ?set= ?dl=1
                                   ?print=1 인쇄용 — 도련(spec.bleed)·재단선·CMYK(Ghostscript, 무채색은 K 단색)·TrimBox/BleedBox. ?marks=0 재단선 없이
    /api/units/check?plan=&skin=   검수 — 책을 그려 보고 error/warn/info 목록 (core/units/check.py)
    /api/units/manuscript POST     원고 → 세트. {text} | {contents: yos-workbook-v1} | 파일(docx·hwpx·txt·json). ?save=1 이면 저장. → {sets, log}

화면은 얇다 — 그리는 일은 전부 core/units/render, 분해는 core/units/decompose.
"""
import json
import os
import re
import unicodedata
import uuid

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from core.units import content, decompose, fonts, manuscript, render, store

bp = Blueprint("units", __name__)
_RE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_RE_UP = re.compile(r"^[0-9a-f]{12}$")


def _updir():
    d = os.path.join(store.udir(), "_in")
    os.makedirs(d, exist_ok=True)
    return d


def _lib_json(lib):
    # tojson 필터는 키를 정렬한다 — 편집기에 id·name 이 앞에 오도록 적은 순서 그대로 내보낸다
    return json.dumps(lib, ensure_ascii=False).replace("</", "<\\/")


@bp.route("/units")
def canvas():
    """캔버스 — 지면을 고르고, 칸을 그리고, 블록·부품을 끌어다 놓는다. 사용자가 쓰는 화면."""
    from core.units import formats
    lib = store.library()
    lib["formats"] = formats.catalog()                # 원고 형식 목록 — 원고를 넣기 전에도 유형·자리를 고를 수 있게(틀 먼저, 원고는 나중)
    return render_template("units_canvas.html", library_json=_lib_json(lib), active_nav="만들기", font_css=fonts.fix_css())


@bp.route("/units/library")
def page():
    """라이브러리·분해·JSON — 데이터를 들여다보는 화면."""
    lib = store.library()
    return render_template("units.html", library_json=_lib_json(lib), kinds=store.KINDS, active_nav="만들기", font_css=fonts.fix_css())


@bp.route("/api/units/thumbs")
def api_thumbs():
    """팔레트 썸네일 — 블록은 견본 값으로, 부품은 그대로. 옷은 ?skin="""
    lib = store.library()
    ctx = _ctx(lib, request.args.get("skin"))
    out = {"blocks": {}, "parts": {}}
    for b in lib["blocks"]:
        out["blocks"][b["id"]] = render.block_standalone(ctx, b)
    for p in lib["parts"]:
        out["parts"][p["id"]] = render.part_standalone(ctx, p)
    return jsonify(out)


@bp.route("/api/units/library")
def api_library():
    from core.units import formats
    lib = store.library()
    lib["formats"] = formats.catalog()                # 원고 형식 목록 — 원고를 넣기 전에도 유형·자리를 고를 수 있게
    return jsonify(lib)


@bp.route("/api/units/<kind>", methods=["POST"])
def api_put(kind):
    if kind not in store.KINDS:
        abort(404)
    item = request.get_json(silent=True)
    err = store.validate(kind, item)
    if err:
        return jsonify({"error": err}), 400
    store.put(kind, item, after=request.args.get("after"))      # ?after=<id> 그 뒤로 · ?after= 맨 앞
    return jsonify({"ok": True, "item": item})


@bp.route("/api/units/check")
def api_check():
    from core.units import check
    lib = store.library()
    plan = store.by_id(lib["plans"]).get(request.args.get("plan") or "")
    if not plan:
        return jsonify({"error": "plan 없음"}), 404
    try:
        return jsonify(check.report(lib, plan, request.args.get("skin")))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@bp.route("/api/units/manuscript", methods=["POST"])
def api_manuscript():
    """원고 → 세트. 원고 형식(core/units/formats — 문서가 고른 form.format, 없으면 파일 이름으로 알아봄)이 있으면 그 형식으로,
    아니면 기본 파서(core/units/manuscript): 파일이면 docx·hwpx·txt·json, 아니면 JSON {text} 또는 {contents}."""
    from core.units import formats
    blocks = store.load("blocks")
    fs = [x for x in request.files.getlist("file") if x and x.filename]
    f = fs[0] if fs else None
    names = [unicodedata.normalize("NFC", os.path.basename(x.filename)) for x in fs]
    fid = (request.form.get("format") or "").strip() or (formats.detect(names) if fs else None)
    if fid and fid not in formats.BY_ID:
        return jsonify({"error": f"모르는 원고 형식 {fid}"}), 400
    try:
        if fs and fid:
            # 원고 형식 — 형식이 파일 이름을 읽을 수 있게(스텝·회차) 원래 이름으로 둔다
            if any(os.path.splitext(n)[1].lower() not in (".docx", ".hwpx", ".hwp") for n in names):
                return jsonify({"error": "원고 형식은 docx·hwpx 만"}), 400
            d = os.path.join(_updir(), uuid.uuid4().hex[:12])
            os.makedirs(d)
            paths = []
            for x, n in zip(fs, names):
                p = os.path.join(d, n)
                x.save(p)
                paths.append(p)
            sets, log = formats.parse(fid, paths)
        elif len(fs) > 1:
            return jsonify({"error": "여러 파일은 원고 형식(워크북·모의고사 …)을 알아볼 수 있을 때만 — 문서의 「원고 형식」을 고르거나 파일 이름을 확인"}), 400
        elif f:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in (".docx", ".hwpx", ".txt", ".md", ".json"):
                return jsonify({"error": "docx·hwpx·txt·json 만"}), 400
            path = os.path.join(_updir(), uuid.uuid4().hex[:12] + ext)
            f.save(path)
            if ext == ".json":
                with open(path, encoding="utf-8") as fh:
                    sets, log = manuscript.from_contents(json.load(fh), blocks)
            else:
                sets, log = manuscript.from_file(path, blocks, request.form.get("kind") or "passage")
        else:
            body = request.get_json(silent=True) or {}
            if body.get("contents"):
                sets, log = manuscript.from_contents(body["contents"], blocks)
            else:
                sets, log = manuscript.from_text(body.get("text") or "", blocks, body.get("kind") or "passage")
    except (ValueError, KeyError, OSError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 400
    if not sets:
        return jsonify({"error": "세트를 하나도 못 만들었다", "log": log}), 400
    for st in sets:
        err = store.validate("sets", st)
        if err:
            return jsonify({"error": err, "log": log}), 400
    if request.args.get("save"):
        for st in sets:
            store.put("sets", st)
    return jsonify({"sets": sets, "log": log})


@bp.route("/api/units/<kind>", methods=["DELETE"])
def api_delete(kind):
    if kind not in store.KINDS:
        abort(404)
    uid = (request.get_json(silent=True) or {}).get("id") or request.args.get("id")
    if not uid:
        return jsonify({"error": "id 없음"}), 400
    return jsonify({"ok": store.delete(kind, uid)})


def _ctx(lib, skin_id, sys=None, skin_item=None):
    skins = store.by_id(lib["skins"])
    skin = skin_item if isinstance(skin_item, dict) and skin_item.get("tokens") else (skins.get(skin_id) or (lib["skins"][0] if lib["skins"] else render.DEFAULT_SKIN))
    return render.Ctx(skin, lib, sys or {"title": "STEP BY STEP", "tag": "BUILD UP"})


@bp.route("/api/units/preview", methods=["POST"])
def api_preview():
    """kind 별로: part → 부품 하나, block → 견본 값으로, page → 세트를 흘려, plan → 책 전체, skin → 블록 전부 그 옷으로."""
    body = request.get_json(silent=True) or {}
    kind = body.get("kind")
    lib = store.library()
    item = body.get("item")
    if item is None and body.get("id"):
        item = store.get(kind, body["id"])
    if kind not in store.KINDS or (item is None and kind != "skins"):
        return jsonify({"error": "kind 또는 item 없음"}), 400
    # 임시 옷(분해 직후)은 body.skin_item 으로 같이 온다
    if body.get("skin_item"):
        lib["skins"] = [body["skin_item"]] + [s for s in lib["skins"] if s.get("id") != body["skin_item"].get("id")]
        skin_id = body["skin_item"].get("id")
    else:
        skin_id = body.get("skin")
    if kind == "skins" and item:
        lib["skins"] = [item] + [s for s in lib["skins"] if s.get("id") != item.get("id")]
        skin_id = item["id"]
    ctx = _ctx(lib, skin_id)
    sets = lib["sets"]
    want = body.get("sets")
    if want:
        sets = [s for s in sets if s.get("id") in want]
    out = []
    try:
        if kind == "parts":
            out.append({"svg": render.part_standalone(ctx, item), "label": item.get("name", "")})
        elif kind == "blocks":
            for v in item.get("variants") or []:
                c2 = render.Ctx(dict(ctx.skin, variants={item["id"]: v["id"]}), lib, ctx.sys)
                out.append({"svg": render.block_standalone(c2, item), "label": f"모양 {v.get('id')} · {v.get('name', '')}"})
                ctx.warnings.extend(w for w in c2.warnings if w not in ctx.warnings)
        elif kind == "pages":
            spec = store.by_id(lib["specs"]).get(body.get("spec") or item.get("spec") or "a4") or render.DEFAULT_SPEC
            if body.get("mode") == "canvas" and body.get("fill"):     # 원고 보기 — 문서의 원고를 자리에 넣어(이 쪽은 지금 고치는 그대로)
                pl = store.by_id(lib["plans"]).get(body["fill"])
                if pl:
                    pgs = [item if p.get("id") == item.get("id") else p for p in _plan_pages(lib, pl)]
                    filled, rep = content.fill(pgs, pl.get("content") or {}, _width_of(lib, pl))
                    item = next((p for p in filled if p.get("id") == item.get("id")), item)
                    ctx.board = max(0.0, min(float(body.get("board") or 0), 200.0))
                    return jsonify({"svgs": render.page_canvas_svgs(ctx, item, spec), "warnings": ctx.warnings, "fill_report": rep})
            if body.get("mode") == "canvas":            # 자유 배치 요소를 견본(또는 고른 세트) 값으로
                ss = store.get("sets", body["set"]) if body.get("set") else None
                if body.get("set") == "answers" and not ss:          # 정답지 면 — 모든 원고의 정답을 모은 한 흐름으로 보인다
                    from core.units import answers as _answers
                    rows = _answers.answer_sets(lib.get("sets") or [], lib.get("blocks") or [])
                    ss = {"kind": "answers", "id": "answers", "blocks": [b for s in rows for b in s["blocks"]]} if rows else None
                ctx.board =max(0.0, min(float(body.get("board") or 0), 200.0))     # 대지(지면 둘레)
                ctx.map = body.get("map") or {}                                     # 문서의 원고 연결표
                out.extend(render.page_canvas_svgs(ctx, item, spec, sample_set=ss))
            else:
                out.extend(render.page_svgs(ctx, item, sets, spec, 1, item.get("name", "")))
        elif kind == "plans":
            out.extend(render.plan_svgs(ctx, item, sets, lib))
        elif kind == "sets":
            spec = render.DEFAULT_SPEC
            pg = store.by_id(lib["pages"]).get(body.get("page") or "sheet") or {"id": "_", "zones": [{"id": "z", "x": 20, "y": 20, "w": 170, "h": 257, "flow": "continue"}]}
            out.extend(render.page_svgs(ctx, pg, [item], spec, 1, item.get("id", "")))
        elif kind == "specs":
            out.append({"svg": render.wrap("", float(item["w"]), float(item["h"]), "#ffffff"), "label": f"{item['w']}×{item['h']}mm"})
        elif kind == "skins":
            for b in lib["blocks"]:
                out.append({"svg": render.block_standalone(ctx, b), "label": b.get("name", b["id"])})
    except Exception as e:                      # 그리다 죽으면 원인을 화면에
        return jsonify({"error": f"{type(e).__name__}: {e}", "warnings": ctx.warnings}), 500
    return jsonify({"svgs": out, "warnings": ctx.warnings})


# ── 분해 ─────────────────────────────────────────────────────────────
@bp.route("/api/units/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "파일 없음"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".svg"):
        return jsonify({"error": "PDF·PNG·JPG·WEBP·SVG 만"}), 400
    uid = uuid.uuid4().hex[:12]
    path = os.path.join(_updir(), uid + ext)
    f.save(path)
    with open(os.path.join(_updir(), uid + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"name": f.filename, "ext": ext}, fh, ensure_ascii=False)
    pages = 1
    if ext == ".pdf":
        import fitz
        pages = len(fitz.open(path))
    return jsonify({"id": uid, "name": f.filename, "pages": pages, "kind": "pdf" if ext == ".pdf" else "image"})


def _upload(uid):
    if not _RE_UP.match(uid or ""):
        abort(404)
    try:
        with open(os.path.join(_updir(), uid + ".json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except OSError:
        abort(404)
    return os.path.join(_updir(), uid + meta["ext"]), meta


@bp.route("/api/units/upload/<uid>/page/<int:pno>.png")
def api_upload_page(uid, pno):
    """올린 PDF 의 면 그림 — 분해 결과와 나란히 본다."""
    path, meta = _upload(uid)
    import io
    if meta["ext"] != ".pdf":
        return send_file(path)
    import fitz
    doc = fitz.open(path)
    if not (1 <= pno <= len(doc)):
        abort(404)
    pix = doc[pno - 1].get_pixmap(dpi=int(request.args.get("dpi", 60)))
    return send_file(io.BytesIO(pix.tobytes("png")), mimetype="image/png")


@bp.route("/api/units/decompose", methods=["POST"])
def api_decompose():
    body = request.get_json(silent=True) or {}
    try:
        if body.get("upload"):
            path, meta = _upload(body["upload"])
            if meta["ext"] == ".pdf":
                dec = decompose.from_pdf(path, int(body.get("page") or 1))
            else:
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    return jsonify({"error": "이미지 분해는 클로드가 한다 — ANTHROPIC_API_KEY 필요"}), 400
                with open(path, "rb") as fh:
                    data = fh.read()
                mt = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[meta["ext"]]
                dec = decompose.from_ai(body.get("prompt") or "", image=data, media_type=mt, name=meta["name"])
        elif (body.get("prompt") or "").strip():
            if not os.environ.get("ANTHROPIC_API_KEY"):
                return jsonify({"error": "프롬프트 분해는 클로드가 한다 — ANTHROPIC_API_KEY 필요"}), 400
            dec = decompose.from_ai(body["prompt"].strip())
        else:
            return jsonify({"error": "올린 파일 또는 프롬프트가 있어야 한다"}), 400
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    # 잰 색·서체 → 임시 옷. 부품이 이 토큰을 쓰므로 같이 저장해 둔다
    sid = "src_" + re.sub(r"[^a-z0-9_]", "_", (body.get("upload") or "prompt").lower())[:20]
    images = {}
    if body.get("upload") and dec.get("imgmap"):                    # PDF 안 그림도 꺼내 둔다 — 안 그러면 자리만 남는다
        try:
            path, meta = _upload(body["upload"])
            if meta["ext"] == ".pdf":
                got = decompose.save_images(path, dec["imgmap"], os.path.join(store.udir(), "_img"), prefix=sid + "_")
                images = {k: os.path.join("_img", v) for k, v in got.items()}
        except Exception as e:
            dec.setdefault("warnings", []).append(f"그림 꺼내기 실패: {e}")
    old = store.get("skins", sid) or {}
    tok = dec.get("tokens") or {"color": {}, "font": {}}
    ot = old.get("tokens") or {}
    tok = {"color": dict(ot.get("color") or {}, **(tok.get("color") or {})),   # 면마다 쌓는다 — 이름에 면 번호가 붙어 안 겹친다
           "font": dict(ot.get("font") or {}, **(tok.get("font") or {}))}
    skin = {"id": sid, "name": "분해 · " + dec.get("from", ""), "tokens": tok, "variants": {}, "images": {}}
    skin["images"] = dict(old.get("images") or {}, **images)        # 여러 면을 분해해도 쌓인다
    store.put("skins", skin)
    dec["skin"] = sid
    # 면 전체 그림 (원자 그대로)
    ctx = render.Ctx(skin, {"parts": [], "blocks": []})
    whole = {"id": "whole", "name": "전체", "w": dec["w"], "h": dec["h"], "atoms": dec["atoms"]}
    dec["svg"] = render.part_standalone(ctx, whole, pad=0)
    dec["warnings"] = ctx.warnings
    return jsonify(dec)


@bp.route("/api/units/part_from", methods=["POST"])
def api_part_from():
    body = request.get_json(silent=True) or {}
    dec, idx = body.get("dec") or {}, body.get("atoms") or []
    pid, name = (body.get("id") or "").strip(), (body.get("name") or "").strip() or "새 부품"
    if not _RE_ID.match(pid):
        return jsonify({"error": "id 는 영문 소문자로 시작, [a-z0-9_]"}), 400
    try:
        idx = [int(i) for i in idx if 0 <= int(i) < len(dec.get("atoms") or [])]
        part = decompose.to_part(dec, idx, pid, name)
    except (ValueError, TypeError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
    err = store.validate("parts", part)
    if err:
        return jsonify({"error": err}), 400
    store.put("parts", part)
    return jsonify({"ok": True, "item": part})


@bp.route("/api/units/make", methods=["POST"])
def api_make():
    """프롬프트 한 줄 → 클로드가 원자로 그림 → 부품 + 블록으로 저장 → 캔버스가 바로 넣는다. body {prompt, skin}."""
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "설명이 비었다"}), 400
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "클로드가 그린다 — ANTHROPIC_API_KEY 필요"}), 400
    skin = store.get("skins", body.get("skin") or "") or (store.load("skins") or [{}])[0]
    try:
        dec = decompose.from_ai(prompt, tokens=skin.get("tokens"))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    if not dec.get("atoms"):
        return jsonify({"error": "원자가 하나도 안 나왔다 — 설명을 더 구체적으로"}), 500
    n = 1
    have = store.by_id(store.load("parts")) | store.by_id(store.load("blocks"))
    while f"ai_{n}" in have:
        n += 1
    uid = f"ai_{n}"
    name = prompt[:16] + ("…" if len(prompt) > 16 else "")
    part = decompose.to_part(dec, list(range(len(dec["atoms"]))), uid, name)
    fields = {}
    for a in part["atoms"]:
        b = a.get("bind")
        if b and not b.startswith("sys."):
            fields[b] = {"type": "number" if b == "no" else ("choices" if b == "choices" else ("answer" if b == "answer" else "rich"))}
    block = {"id": uid, "name": name, "source": "content" if fields else "system", "fields": fields,
             "variants": [{"id": "v1", "name": "기본", "part": uid}]}
    for kind, it in (("parts", part), ("blocks", block)):
        err = store.validate(kind, it)
        if err:
            return jsonify({"error": f"{kind}: {err}"}), 500
    # 클로드가 새 토큰 이름을 썼으면 옷에 값을 보탠다(있는 이름은 안 건드림)
    if skin.get("id"):
        tk = skin.setdefault("tokens", {})
        added = False
        for k in ("color", "font"):
            for nm, val in (dec.get("tokens") or {}).get(k, {}).items():
                if nm not in tk.setdefault(k, {}):
                    tk[k][nm] = val
                    added = True
        if added:
            store.put("skins", skin)
    store.put("parts", part)
    store.put("blocks", block)
    return jsonify({"ok": True, "block": block, "part": part, "note": dec.get("note", "")})


# ── 원고 넣기 — 틀(자리·임시 글·스타일)에 원고(자리 이름 → 글)를 넣는다. 규약: docs/편집기_재현/원고자리_규약.md ──

def _plan_pages(lib, plan):
    pages = store.by_id(lib["pages"])
    return [pages[i] for i in content.plan_page_ids(plan) if i in pages]


def _width_of(lib, plan):
    """쪽 폭 mm — 원고 읽는 순서의 단 나누기에(content.slots)"""
    specs = store.by_id(lib["specs"])
    return lambda pg: float((specs.get(pg.get("spec") or (plan or {}).get("spec") or "a4") or render.DEFAULT_SPEC)["w"])


@bp.route("/api/units/schema")
def api_schema():
    """?plan=<문서> — 자리 표: 자리 이름마다 몇 번 나오는지와 임시 글. 바깥 시스템이 무엇을 보낼지 안다."""
    lib = store.library()
    plan = store.by_id(lib["plans"]).get(request.args.get("plan") or "")
    if not plan:
        return jsonify({"error": "plan 없음"}), 404
    return jsonify({"plan": plan["id"], "name": plan.get("name"), "slots": content.schema(_plan_pages(lib, plan), _width_of(lib, plan)),
                    "rule": "원고 = {자리 이름: 글 | [글…]} — 같은 자리가 여러 번이면 쪽 순서 → 쪽 안 위에서 아래(같은 높이면 왼쪽부터). 단이 있는 쪽은 왼쪽 단 위→아래, 다음 단(여러 단에 걸친 상자는 그 높이에서 먼저)"})


@bp.route("/api/units/fill", methods=["POST"])
def api_fill():
    """원고를 넣은 결과 — JSON {plan, content, skin?, as?: "pdf"(기본)|"svg"}. 틀의 임시 글 대신 원고 글이 나온다.
    content 를 안 주면 문서에 저장된 원고(plan.content). 넣은 보고는 X-Fill-Report 머리(pdf) 또는 report(svg)."""
    from core.units import pdf as _pdf
    body = request.get_json(silent=True) or {}
    lib = store.library()
    plan = store.by_id(lib["plans"]).get(body.get("plan") or "")
    if not plan:
        return jsonify({"error": "plan 없음"}), 404
    data = body.get("content") if body.get("content") is not None else plan.get("content") or {}
    if not isinstance(data, dict):
        return jsonify({"error": "content 는 {자리 이름: 글 | [글…]}"}), 400
    pages, report = content.fill(_plan_pages(lib, plan), data, _width_of(lib, plan))
    ctx = _ctx(lib, body.get("skin"))
    spec = store.by_id(lib["specs"]).get(plan.get("spec")) or render.DEFAULT_SPEC
    svgs = []
    for pg in pages:
        sp = store.by_id(lib["specs"]).get(pg.get("spec") or plan.get("spec") or "a4") or spec
        svgs.extend(render.page_canvas_svgs(ctx, pg, sp)[:1])                  # 쪽 하나 = 면 하나 (캔버스와 같게)
    if body.get("as") == "svg":
        return jsonify({"svgs": svgs, "report": report, "warnings": ctx.warnings})
    out = os.path.join(store.udir(), "_pdf")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, re.sub(r"[^a-z0-9_]", "_", plan["id"].lower()) + "_fill.pdf")
    try:
        _pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), path, title=plan.get("name") or plan["id"])
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}", "report": report}), 500
    r = send_file(path, mimetype="application/pdf", max_age=0)
    r.headers["X-Fill-Report"] = json.dumps(report, ensure_ascii=True)
    return r


@bp.route("/api/units/pdf")
def api_pdf():
    """PDF 저장 — ?plan=<틀> (세트 전부) 또는 ?page=<지면> (견본 값·?set=). ?skin= 옷. 크로미움 인쇄."""
    from core.units import pdf as _pdf
    lib = store.library()
    ctx = _ctx(lib, request.args.get("skin"))
    plan_id, page_id = request.args.get("plan"), request.args.get("page")
    printing = request.args.get("print") == "1"
    if printing:
        pl = store.by_id(lib["plans"]).get(plan_id or "") or {}
        pg0 = store.by_id(lib["pages"]).get(page_id or "") or {}
        sp0 = store.by_id(lib["specs"]).get(pl.get("spec") or pg0.get("spec") or "a4") or render.DEFAULT_SPEC
        ctx.print = {"bleed": float(sp0.get("bleed") or 3.0), "marks": request.args.get("marks") != "0"}
    keep = None
    if plan_id:
        plan = store.by_id(lib["plans"]).get(plan_id)
        if not plan:
            abort(404)
        spec = store.by_id(lib["specs"]).get(plan.get("spec")) or render.DEFAULT_SPEC
        svgs = render.plan_svgs(ctx, plan, lib["sets"], lib)
        title = plan.get("name") or plan_id
    elif page_id:
        pg = store.by_id(lib["pages"]).get(page_id)
        if not pg:
            abort(404)
        spec = store.by_id(lib["specs"]).get(pg.get("spec") or "a4") or render.DEFAULT_SPEC
        ss = store.get("sets", request.args["set"]) if request.args.get("set") else None
        fid = request.args.get("fill")                                         # 원고 보기 — ?fill=<문서> 또는 auto(이 쪽이 든 문서)
        before = []
        if fid:
            pl = next((p for p in lib["plans"] if (p["id"] == fid or fid == "auto") and page_id in content.plan_page_ids(p)), None)
            if pl:
                filled, _rep = content.fill(_plan_pages(lib, pl), pl.get("content") or {}, _width_of(lib, pl))
                k = next((i for i, p in enumerate(filled) if p.get("id") == page_id), None)
                if k is not None:
                    pg, before = filled[k], filled[:k]                         # 앞 쪽들도 함께 그린다 — 글 잇기가 앞 쪽 이야기를 이 쪽으로 흘린다
                ss = None
        pre = [s for p in before for s in render.page_canvas_svgs(ctx, p, spec)] if any(
            (it.get("atom") or {}).get("story") for p in before + [pg] for it in p.get("items") or []) else []
        svgs = pre + render.page_canvas_svgs(ctx, pg, spec, sample_set=ss)
        keep = set(range(len(pre), len(svgs))) if pre else None
        title = pg.get("name") or page_id
    else:
        return jsonify({"error": "plan 또는 page"}), 400
    if not svgs:
        return jsonify({"error": "그릴 면이 없다"}), 400
    out = os.path.join(store.udir(), "_pdf")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, re.sub(r"[^a-z0-9_]", "_", (plan_id or page_id).lower()) + ("_print" if printing else "") + ".pdf")
    try:
        if printing:
            r = _pdf.to_print_pdf(svgs, float(spec["w"]), float(spec["h"]), path, bleed=ctx.print["bleed"], marks=ctx.print["marks"],
                                  skin=ctx.skin, title=title + " (인쇄)")
            if request.args.get("json") == "1":
                return jsonify({"pages": r["pages"], "cmyk": r["cmyk"], "note": r["note"], "warnings": ctx.warnings})
        else:
            _pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), path, title=title, keep=keep)
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}", "warnings": ctx.warnings}), 500
    return send_file(path, mimetype="application/pdf", as_attachment=request.args.get("dl") == "1",
                     download_name=f"{title}{'_인쇄' if printing else ''}.pdf", max_age=0)


@bp.route("/api/units/part_from_preview", methods=["POST"])
def api_part_from_preview():
    """고른 원자만 부품으로 그려 본다 — 저장하지 않는다."""
    body = request.get_json(silent=True) or {}
    dec, idx = body.get("dec") or {}, body.get("atoms") or []
    try:
        idx = [int(i) for i in idx if 0 <= int(i) < len(dec.get("atoms") or [])]
        part = decompose.to_part(dec, idx, "preview", "미리보기")
    except (ValueError, TypeError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
    skin = body.get("skin_item") or {"id": "", "tokens": {}}
    ctx = render.Ctx(skin, {"parts": [], "blocks": []})
    return jsonify({"item": part, "svg": render.part_standalone(ctx, part), "warnings": ctx.warnings})


@bp.route("/api/units/image", methods=["POST"])
def api_image_put():
    """그림 파일 → 옷(브랜드)의 그림 목록에 키로 등록. 지면의 그림 원자는 그 키를 쓴다."""
    f = request.files.get("file")
    sid = (request.form.get("skin") or "").strip()
    key = (request.form.get("key") or "").strip() or (os.path.splitext(f.filename)[0] if f else "")
    key = re.sub(r"[^a-zA-Z0-9_가-힣]", "_", key)[:40] or "img"
    if not f or not f.filename:
        return jsonify({"error": "파일 없음"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        return jsonify({"error": "PNG·JPG·WEBP·SVG 만"}), 400
    skin = store.get("skins", sid)
    if not skin:
        return jsonify({"error": f"옷 {sid} 없음"}), 404
    d = os.path.join(store.udir(), "_img")
    os.makedirs(d, exist_ok=True)
    name = f"{key}{ext}"
    f.save(os.path.join(d, name))
    skin.setdefault("images", {})[key] = os.path.join("_img", name)
    err = store.validate("skins", skin)
    if err:
        return jsonify({"error": err}), 400
    store.put("skins", skin)
    return jsonify({"ok": True, "key": key, "skin": sid})


@bp.route("/api/units/image/<sid>/<key>")
def api_image(sid, key):
    skin = store.get("skins", sid) or {}
    p = (skin.get("images") or {}).get(key)
    if not p:                                                   # 다른 옷에 등록돼 있어도 찾는다
        for sk in store.load("skins"):
            p = (sk.get("images") or {}).get(key)
            if p:
                break
    if not p:
        abort(404)
    if not os.path.isabs(p):
        p = os.path.join(store.udir(), p)
    if not os.path.exists(p):
        abort(404)
    return send_file(p)
