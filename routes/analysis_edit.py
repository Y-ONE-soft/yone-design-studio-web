# -*- coding: utf-8 -*-
"""분석본 지면 위 고치기 — contents(분석본 NEW)가 iframe 으로 끼워 쓰는 화면.

contents 가 조판 문서(TypesetDoc) 하나를 postMessage 로 넘기면 편집기 제작 분석본 틀로 그려 보이고,
사람이 지면에서 글·표기·윗주·서술형★·문법 포인트·해석·우면 칸을 고친다. 「저장」 하면 고친 레코드를
contents 조판 문서 모양으로 되돌려(core/sources/yos_analysis.to_doc) contents 에 넘긴다 — 데이터 주인은 contents.

    GET  /analysis-edit?design=<디자인 id>        화면(templates/analysis_edit.html)
    POST /analysis-edit/render {design, doc?, rec?} → {svgs, rec}     rec 없으면 doc 로 레코드를 짓는다
    POST /analysis-edit/doc    {rec, base}           → {doc, changed}  고친 레코드 → 조판 문서

틀은 디자인 폴더의 units.json 그대로(찍기와 같은 _editor_lib). 틀 그림은 디자인마다 임시 폴더 하나에 푼다.
"""
import json
import os
import re
import tempfile

from flask import Blueprint, abort, jsonify, render_template, request

bp = Blueprint("analysis_edit", __name__)
SERIES = "analysis"
_DESIGN = re.compile(r"^[a-z0-9_-]{1,32}$", re.I)


def _design(v):
    from routes.api_v1 import _editor_design
    if not isinstance(v, str) or not _DESIGN.match(v) or not _editor_design(SERIES, v):
        abort(400, "편집기 제작 분석본 디자인이 아니다")
    return v


@bp.route("/analysis-edit")
def page():
    from core.units import fonts
    design = _design(request.args.get("design") or "")
    return render_template("analysis_edit.html", design=design, font_css=fonts.fix_css() + fonts.face_css("url"))


@bp.route("/analysis-edit/render", methods=["POST"])
def render_pages():
    from core.sources import yos_analysis
    from routes.api_v1 import _editor_lib
    from routes.units import _ctx, fill_svgs
    body = request.get_json(silent=True) or {}
    design = _design(body.get("design"))
    rec = body.get("rec")
    if not isinstance(rec, dict):
        doc = body.get("doc")
        if not isinstance(doc, dict) or not doc.get("sentences"):
            return jsonify({"error": "조판 문서(doc)나 레코드(rec)가 필요하다"}), 400
        rec = yos_analysis.record(doc)
    content = {"분석 펼침면": [rec]}
    from routes.api_v1 import records_for
    from routes.catalog import _ddir
    with open(os.path.join(_ddir(SERIES, design), "units.json"), encoding="utf-8") as f:
        content = records_for(json.load(f), content)                      # 템플릿이 레코드 차례 꼴이면 레코드 차례로
    work = os.path.join(tempfile.gettempdir(), "analysis_edit", design)   # 틀 그림 풀 자리 — 디자인마다 하나
    os.makedirs(work, exist_ok=True)
    lib, plan, skin = _editor_lib({"book_dir": work, "series": SERIES, "design": design}, content)
    svgs, _rep, _spec = fill_svgs(lib, plan, content, _ctx(lib, skin.get("id")), drop_empty=True)
    return jsonify({"svgs": svgs, "rec": rec})


@bp.route("/analysis-edit/doc", methods=["POST"])
def to_doc():
    from core.sources import yos_analysis
    body = request.get_json(silent=True) or {}
    rec, base = body.get("rec"), body.get("base")
    if not isinstance(rec, dict) or not isinstance(base, dict):
        return jsonify({"error": "rec · base 가 필요하다"}), 400
    doc, changed = yos_analysis.to_doc(rec, base)
    return jsonify({"doc": doc, "changed": changed})
