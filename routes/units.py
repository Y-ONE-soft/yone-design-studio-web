# -*- coding: utf-8 -*-
"""단위 — 원자로 부품을, 부품으로 블록을, 블록으로 지면·틀을 만든다. 옷을 갈아입히고 세트(콘텐츠)를 흘려 본다.

    /units                         화면 — 왼쪽 분해·라이브러리, 가운데 미리보기(SVG), 오른쪽 JSON 편집
    /api/units/library             전부
    /api/units/<kind>  POST        하나 저장(스키마 대조) · DELETE {id}
    /api/units/preview POST        {kind, item|id, skin, sets} → {svgs:[{svg,label}], warnings}
    /api/units/upload  POST        PDF·이미지 올리기 → {id, pages}
    /api/units/decompose POST      {upload, page} | {upload(이미지)} | {prompt} → decomposed (+ 임시 옷 src_<id> 저장)
    /api/units/part_from POST      {dec, atoms:[번호], id, name} → 부품 저장

화면은 얇다 — 그리는 일은 전부 core/units/render, 분해는 core/units/decompose.
"""
import json
import os
import re
import uuid

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from core.units import decompose, render, store

bp = Blueprint("units", __name__)
_RE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_RE_UP = re.compile(r"^[0-9a-f]{12}$")


def _updir():
    d = os.path.join(store.udir(), "_in")
    os.makedirs(d, exist_ok=True)
    return d


@bp.route("/units")
def page():
    lib = store.library()
    return render_template("units.html", library=lib, kinds=store.KINDS, active_nav="단위")


@bp.route("/api/units/library")
def api_library():
    return jsonify(store.library())


@bp.route("/api/units/<kind>", methods=["POST"])
def api_put(kind):
    if kind not in store.KINDS:
        abort(404)
    item = request.get_json(silent=True)
    err = store.validate(kind, item)
    if err:
        return jsonify({"error": err}), 400
    store.put(kind, item)
    return jsonify({"ok": True, "item": item})


@bp.route("/api/units/<kind>", methods=["DELETE"])
def api_delete(kind):
    if kind not in store.KINDS:
        abort(404)
    uid = (request.get_json(silent=True) or {}).get("id") or request.args.get("id")
    if not uid:
        return jsonify({"error": "id 없음"}), 400
    return jsonify({"ok": store.delete(kind, uid)})


def _ctx(lib, skin_id, sys=None):
    skins = store.by_id(lib["skins"])
    skin = skins.get(skin_id) or (lib["skins"][0] if lib["skins"] else {"id": "", "tokens": {}})
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
            spec = store.by_id(lib["specs"]).get(body.get("spec") or "a4") or render.DEFAULT_SPEC
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
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        return jsonify({"error": "PDF·PNG·JPG·WEBP 만"}), 400
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
    skin = {"id": sid, "name": "분해 · " + dec.get("from", ""), "tokens": dec.get("tokens") or {"color": {}, "font": {}}, "variants": {}, "images": {}}
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


@bp.route("/api/units/image/<sid>/<key>")
def api_image(sid, key):
    skin = store.get("skins", sid) or {}
    p = (skin.get("images") or {}).get(key)
    if not p:
        abort(404)
    if not os.path.isabs(p):
        p = os.path.join(store.udir(), p)
    if not os.path.exists(p):
        abort(404)
    return send_file(p)
