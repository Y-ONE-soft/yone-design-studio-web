"""가공/디자인 도구 — 워크북 가공 (페이지+API) + 목업 (페이지+API) (app.py에서 분리, C2-9)."""
import json
import os
import uuid

from flask import (Blueprint, Response, jsonify, render_template, request,
                   send_file)

from core import workbook_edit as wb_edit

bp = Blueprint("tools", __name__)

# 목업 세션 (token → {front_img, back_img})
_mockup_sessions = {}


# ── 가공: 워크북 가공 페이지 + API ──────────────────────────────────────

@bp.route("/processing/workbook_edit")
def processing_workbook_edit():
    return render_template("processing_workbook_edit.html",
                           active_nav="가공",
                           section_title="워크북 가공")


@bp.route("/api/processing/workbook/upload", methods=["POST"])
def api_wb_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"status": "err", "msg": "file 필드가 없습니다"})
    r = wb_edit.save_upload(f)
    return jsonify(r)


@bp.route("/api/processing/workbook/job-files")
def api_wb_job_files():
    job_dir = request.args.get("jobDir", "")
    if not job_dir or not os.path.isdir(job_dir):
        return jsonify({"status": "err", "msg": "잡 폴더 없음"})
    return jsonify({"status": "ok", "files": wb_edit.list_job_files(job_dir)})


@bp.route("/api/processing/workbook/active-info", methods=["POST"])
def api_wb_active_info():
    return jsonify(wb_edit.active_info())


@bp.route("/api/processing/workbook/list-candidates", methods=["POST"])
def api_wb_list_candidates():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.list_candidates(doc_path=data.get("docPath")))


@bp.route("/api/processing/workbook/identify-rounds", methods=["POST"])
def api_wb_identify_rounds():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.identify_rounds(
        doc_path=data.get("docPath"),
        story_indices=data.get("storyIndices"),
    ))


@bp.route("/api/processing/workbook/remove-seo", methods=["POST"])
def api_wb_remove_seo():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.remove_seo(
        doc_path=data.get("docPath"),
        backup=bool(data.get("backup", True)),
        extract=bool(data.get("extract", True)),
        story_indices=data.get("storyIndices"),
    ))


@bp.route("/api/processing/workbook/remove-rounds", methods=["POST"])
def api_wb_remove_rounds():
    data = request.get_json(silent=True) or {}
    spec = data.get("roundSpec") or {}
    if not isinstance(spec, dict) or not spec:
        return jsonify({"status": "err", "msg": "roundSpec 필요"})
    return jsonify(wb_edit.remove_rounds(
        round_spec=spec,
        doc_path=data.get("docPath"),
        backup=bool(data.get("backup", True)),
        extract=bool(data.get("extract", True)),
    ))


@bp.route("/api/processing/workbook/compare", methods=["POST"])
def api_wb_compare():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.compare(
        doc_path=data.get("docPath"),
        orig_path=data.get("origPath", ""),
    ))


@bp.route("/api/processing/workbook/save", methods=["POST"])
def api_wb_save():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.save_doc(doc_path=data.get("docPath")))


@bp.route("/api/processing/workbook/passage-detect", methods=["POST"])
def api_wb_passage_detect():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.passage_detect(
        doc_path=data.get("docPath"),
        readers=data.get("readers", ""),
    ))


@bp.route("/api/processing/workbook/passage-select", methods=["POST"])
def api_wb_passage_select():
    data = request.get_json(silent=True) or {}
    return jsonify(wb_edit.passage_select(
        doc_path=data.get("docPath"),
        nums=data.get("nums", ""),
        select_mode=data.get("selectMode", "keep"),
        backup=bool(data.get("backup", True)),
        relayout=bool(data.get("relayout", True)),
        leftover=data.get("leftover", "tight"),
        save=bool(data.get("save", True)),
        readers=data.get("readers", ""),
    ))


@bp.route("/api/processing/workbook/convert-docx", methods=["POST"])
def api_wb_convert_docx():
    data = request.get_json(silent=True) or {}
    txt_path = data.get("txtPath", "")
    return jsonify(wb_edit.convert_txt_to_docx(txt_path))


@bp.route("/api/processing/workbook/download")
def api_wb_download():
    """가공 결과 파일 다운로드. path는 절대경로 (작업 폴더 한정)."""
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        return "파일 없음", 404
    # 경로 보호: 워크북가공 작업 폴더 또는 _local 폴더만 허용
    real = os.path.realpath(path)
    allowed_prefixes = [
        os.path.expanduser("~/Documents/작업/Y.ONE STUDIO/"),
        "/tmp/",
    ]
    if not any(real.startswith(p) for p in allowed_prefixes):
        return "허용되지 않은 경로", 403
    return send_file(real, as_attachment=True, download_name=os.path.basename(real))


# ── 목업 ─────────────────────────────────────────────────────────────

@bp.route("/mockup")
def mockup_page():
    from core.mockup.renderer import DEFAULTS, SPECS
    return render_template("mockup.html", defaults=DEFAULTS, specs=SPECS,
                           active_nav="목업")


@bp.route("/api/mockup/upload", methods=["POST"])
def api_mockup_upload():
    from core.mockup import renderer
    front = request.files.get("front")
    back  = request.files.get("back")
    if not front:
        return jsonify({"error": "앞표지 필요"}), 400
    try:
        front_bytes = front.read()
        front_img = renderer.load_cover_bytes(front_bytes, front.filename)
        front_crop = renderer.default_crop_params(front_img, "front")
        # 중철펼침용: 앞 파일이 2페이지 PDF면 2페이지를 자동 추출
        front_p2 = renderer.load_cover_bytes(front_bytes, front.filename, page=1)
        back_img = None
        back_crop = None
        if back and back.filename:
            back_img = renderer.load_cover_bytes(back.read(), back.filename)
            back_crop = renderer.default_crop_params(back_img, "back")
        token = uuid.uuid4().hex[:10]
        _mockup_sessions[token] = {"front": front_img, "back": back_img, "front_p2": front_p2}
        return jsonify({"token": token, "front_crop": front_crop, "back_crop": back_crop,
                        "has_p2": front_p2 is not None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/mockup/render", methods=["POST"])
def api_mockup_render():
    from core.mockup import renderer
    token  = request.form.get("token")
    params = json.loads(request.form.get("params", "{}"))
    fmt    = request.form.get("fmt", "PNG")
    session = _mockup_sessions.get(token)
    if not session:
        return "세션 없음 — 표지를 다시 업로드해 주세요.", 400
    try:
        front = renderer.apply_crop(session["front"],
            params.pop("front_cx", 0), params.pop("front_cy", 0),
            params.pop("front_cw", renderer.COVER_W))
        back = None
        if session.get("back"):
            back = renderer.apply_crop(session["back"],
                params.pop("back_cx", 0), params.pop("back_cy", 0),
                params.pop("back_cw", renderer.COVER_W))
        data = renderer.render_to_bytes(front, back, params, fmt)
        mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
        return Response(data, mimetype=mime)
    except Exception as e:
        return str(e), 500


@bp.route("/api/mockup/render_binding", methods=["POST"])
def api_mockup_render_binding():
    """무선/스프링/중철 바인딩 목업 — 헤드리스 A/B 라이트맵 엔진 (Photoshop 불필요)."""
    from core.mockup import mockup_engine
    from PIL import Image as _Img
    import io as _io
    token   = request.form.get("token")
    binding = request.form.get("binding", "")
    fmt     = request.form.get("fmt", "PNG").upper()
    session = _mockup_sessions.get(token)
    if not session:
        return "세션 없음 — 표지를 다시 업로드해 주세요.", 400
    if binding not in mockup_engine.ALL_BINDINGS:
        return f"알 수 없는 바인딩: {binding}", 400
    try:
        fit = float(request.form.get("fit", "1.0"))
    except ValueError:
        fit = 1.0
    fit = max(0.7, min(1.3, fit))
    back_img = session.get("back") or session.get("front_p2")  # 뒷표지 없으면 2페이지 자동
    try:
        img = mockup_engine.render(session["front"], binding,
                                   back_img=back_img, long_edge=1500, fit=fit)
        buf = _io.BytesIO()
        if fmt == "PNG":
            img.save(buf, "PNG", optimize=True); mime = "image/png"
        else:
            bg = _Img.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1]); bg.save(buf, "JPEG", quality=92)
            mime = "image/jpeg"
        return Response(buf.getvalue(), mimetype=mime)
    except Exception as e:
        return str(e), 500
