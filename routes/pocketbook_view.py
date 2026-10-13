# -*- coding: utf-8 -*-
"""포켓북 지면 보기 — contents 포켓북이 iframe 으로 끼워 쓰는 화면(지문 하나 · 고른 면만).

contents 가 지문 하나의 분석본 조판 문서 + 고른 면을 postMessage 로 넘기면 편집기 제작 포켓북 틀로 그려 보인다.
변환은 core/sources/yos_pocketbook 한 곳. 데이터 주인은 contents — 여기서는 그리기만 한다.

    GET  /pocketbook-view?design=<디자인 id>          화면(templates/pocketbook_view.html)
    POST /pocketbook-view/render {design, src}      → {pages: [{svg, face}], report}

틀은 디자인 폴더의 units.json 그대로. 원고 레코드의 칸으로 면이 골라지므로(자동 상위 페이지 적용) 문서를 줄이지 않고,
앞면 · 뒷면처럼 레코드를 안 받은 면과 고르지 않은 면은 그린 뒤 뺀다.
"""
import json
import os
import re
import tempfile

from flask import Blueprint, abort, jsonify, render_template, request

bp = Blueprint("pocketbook_view", __name__)
SERIES = "pocketbook"
_DESIGN = re.compile(r"^[a-z0-9_-]{1,32}$", re.I)


def _design(v):
    from routes.api_v1 import _editor_design
    if not isinstance(v, str) or not _DESIGN.match(v) or not _editor_design(SERIES, v):
        abort(400, "편집기 제작 포켓북 디자인이 아니다")
    return v


def _face(rec, seen):
    """그 면이 받은 레코드 → 면 이름. 암기 레코드는 두 페이지짜리 — 앞이 TEST, 뒤가 정답"""
    if not isinstance(rec, dict):
        return None
    if "암기지문" in rec:
        seen["memo"] = seen.get("memo", 0) + 1
        return "memo" if seen["memo"] % 2 else "answer"
    if "흐름제목+흐름글" in rec:
        return "flow"
    if "지문" in rec:
        return "passage"
    return None


@bp.route("/pocketbook-view")
def page():
    from core.units import fonts
    design = _design(request.args.get("design") or "")
    return render_template("pocketbook_view.html", design=design, font_css=fonts.fix_css() + fonts.face_css("url"))


@bp.route("/pocketbook-view/render", methods=["POST"])
def render_pages():
    from core.sources import yos_pocketbook
    from routes.api_v1 import _editor_lib
    from routes.catalog import _ddir
    from routes.units import _ctx, fill_svgs
    body = request.get_json(silent=True) or {}
    design = _design(body.get("design"))
    src = body.get("src")
    if not isinstance(src, dict) or not isinstance(src.get("doc"), dict):
        return jsonify({"error": "src.doc(분석본 조판 문서)가 필요하다"}), 400
    content, _faces, report = yos_pocketbook.to_content(src)
    want = set(src.get("faces") or yos_pocketbook.FACES)
    if not content["원고"]:
        return jsonify({"pages": [], "report": report})
    work = os.path.join(tempfile.gettempdir(), "pocketbook_view", design)  # 틀 그림 풀 자리 — 디자인마다 하나
    os.makedirs(work, exist_ok=True)
    lib, _plan, skin = _editor_lib({"book_dir": work, "series": SERIES, "design": design}, {})
    with open(os.path.join(_ddir(SERIES, design), "units.json"), encoding="utf-8") as f:
        plan = json.load(f)["plan"]                                      # 문서 그대로 — 레코드 칸이 면을 고른다
    lib["plans"] = [plan]
    recs = []
    svgs, _rep, _spec = fill_svgs(lib, plan, content, _ctx(lib, skin.get("id")), drop_empty=True, recs=recs)
    seen, pages = {}, []
    for s, rec in zip(svgs, recs):
        face = _face(rec, seen)
        if face and face in want:
            pages.append({"svg": s["svg"] if isinstance(s, dict) else s, "face": face})
    return jsonify({"pages": pages, "report": report})
