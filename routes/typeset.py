"""조판 실행 API — /api/run, /api/stream(SSE), /api/cancel, /api/result,
/download/<job_id>/pdf (app.py에서 분리, C2-9). 파이프라인 본체는 core/pipeline.py."""
import json
import os
import re
import shutil
import threading

from flask import (Blueprint, Response, jsonify, request, send_file,
                   stream_with_context)

import config
import core.job_manager as jm
from core.pipeline import run_pipeline
from core.uploads import sanitize_filename, allowed_by_accept
from engines import registry

bp = Blueprint("typeset", __name__)


@bp.route("/api/run/<material_id>", methods=["POST"])
def api_run(material_id):
    try:
        engine = registry.get(material_id)
    except KeyError:
        print(f"[ERROR] 교재 없음: material_id='{material_id}'")
        return jsonify({"error": f"교재 없음 (id: {material_id})"}), 404

    job_id = jm.create_job(material_id)
    job_dir = jm.get_job(job_id)["dir"]
    upload_dir = os.path.join(job_dir, "uploads")

    # 학교 저장 (공통 메타데이터)
    school = request.form.get("school", "").strip()
    if school:
        open(os.path.join(job_dir, "school.txt"), "w").write(school)

    # issue_num 저장 (공통 메타데이터)
    issue_num = request.form.get("issue_num", "").strip()
    if issue_num:
        open(os.path.join(job_dir, "issue_num.txt"), "w").write(issue_num)

    # grade 저장 (단어장 등 학년 선택이 필요한 교재)
    grade = request.form.get("grade", "").strip()
    if grade:
        open(os.path.join(job_dir, "grade.txt"), "w").write(grade)

    # year/month 저장 (워크북 등 시험 연도/월 선택이 필요한 교재)
    year = request.form.get("year", "").strip()
    if year:
        open(os.path.join(job_dir, "year.txt"), "w").write(year)
    month = request.form.get("month", "").strip()
    if month:
        open(os.path.join(job_dir, "month.txt"), "w").write(month)

    # 고3 선택된 강 목록 저장
    lectures = request.form.get("lectures", "").strip()
    if lectures:
        open(os.path.join(job_dir, "lectures.txt"), "w",
             encoding="utf-8").write(lectures)

    # 동형모의고사 메타데이터 저장
    for meta_key in ("exam_period", "exam_date", "exam_type", "round"):
        val = request.form.get(meta_key, "").strip()
        if val:
            open(os.path.join(job_dir, f"{meta_key}.txt"), "w",
                 encoding="utf-8").write(val)

    # 교과서 워크북 메타데이터 저장
    for meta_key in ("subject", "publisher", "lesson", "lesson_folder",
                     "manuscript_folder", "workbook_type"):
        val = request.form.get(meta_key, "").strip()
        if val:
            open(os.path.join(job_dir, f"{meta_key}.txt"), "w",
                 encoding="utf-8").write(val)

    # 검수 에이전트 opt-in (UI 체크박스, W41) — 파이프라인 훅이 이 파일 존재로 판단
    if request.form.get("review_agent", "").strip() == "1":
        open(os.path.join(job_dir, "review_agent.txt"), "w").write("1")

    # 부교재 워크북: 파일명 stem (학교명_{stem}_내지.indd 의 stem 부분)
    filename_stem = request.form.get("filename_stem", "").strip()
    if filename_stem:
        open(os.path.join(job_dir, "filename_stem.txt"), "w",
             encoding="utf-8").write(filename_stem)

    # 워크북 조판 제외 섹션 (체크박스 그룹 — multi-value)
    exclude_list = request.form.getlist("exclude")
    if exclude_list:
        open(os.path.join(job_dir, "exclude.txt"), "w",
             encoding="utf-8").write(",".join(exclude_list))

    # 조판 시점 슬림 변환 (core/slim_post.py) — 업로드 슬롯이 아니라
    # 공통 폼 필드로 받는다 (엔진별 upload_spec 무변경). 값이 없으면
    # 파일을 만들지 않으므로 후처리는 no-op.
    from core.slim_post import FORM_KEYS as _SLIM_KEYS
    for _key in _SLIM_KEYS:
        _val = request.form.get(_key, "").strip()
        if _val:
            open(os.path.join(job_dir, f"{_key}.txt"), "w",
                 encoding="utf-8").write(_val)

    # 업로드 파일 및 텍스트 필드 저장
    # — 진단 로그: multipart 파싱 결과 (Werkzeug 3.x form 한도 디버그용)
    try:
        _form_keys = list(request.form.keys())
        _file_keys = list(request.files.keys())
        _file_counts = {k: len(request.files.getlist(k)) for k in _file_keys}
        print(f"[upload-debug] job={job_id} form_keys={_form_keys} "
              f"file_keys={_file_keys} file_counts={_file_counts} "
              f"content_length={request.content_length}", flush=True)
    except Exception as _e:
        print(f"[upload-debug-error] {_e}", flush=True)

    uploaded = {}
    for slot in engine.upload_spec["slots"]:
        key = slot["key"]
        # 학년 필터: 슬롯에 grade가 지정되어 있고 선택 학년과 다르면 건너뛰기
        slot_grade = slot.get("grade")
        if slot_grade and grade and slot_grade != grade:
            continue
        if slot.get("type") in ("text", "textarea"):
            val = request.form.get(key, "").strip()
            if val:
                # 텍스트 값은 job_dir/{key}.txt 로 저장
                txt_path = os.path.join(job_dir, f"{key}.txt")
                open(txt_path, "w", encoding="utf-8").write(val)
                uploaded[key] = val
            elif slot.get("required"):
                jm.fail(job_id, f"필수 입력 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 입력 누락: {slot['label']}"}), 400
        elif slot.get("multiple"):
            files = request.files.getlist(key)
            paths = []
            for f in files:
                if f and f.filename:
                    # (C1-3) 확장자 화이트리스트 — 슬롯 accept가 진실
                    if not allowed_by_accept(f.filename, slot.get("accept", "")):
                        msg = (f"허용되지 않는 파일 형식: {f.filename} "
                               f"(허용: {slot.get('accept')})")
                        jm.fail(job_id, msg)
                        return jsonify({"job_id": job_id, "error": msg}), 400
                    safe_name = f"{key}_{sanitize_filename(f.filename)}"
                    path = os.path.join(upload_dir, safe_name)
                    f.save(path)
                    paths.append(path)
            if paths:
                uploaded[key] = paths
            elif slot.get("required"):
                jm.fail(job_id, f"필수 파일 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 파일 누락: {slot['label']}"}), 400
        else:
            f = request.files.get(key)
            if f and f.filename:
                # (C1-3) 확장자 화이트리스트 — 슬롯 accept가 진실
                if not allowed_by_accept(f.filename, slot.get("accept", "")):
                    msg = (f"허용되지 않는 파일 형식: {f.filename} "
                           f"(허용: {slot.get('accept')})")
                    jm.fail(job_id, msg)
                    return jsonify({"job_id": job_id, "error": msg}), 400
                safe_name = f"{key}_{sanitize_filename(f.filename)}"
                path = os.path.join(upload_dir, safe_name)
                f.save(path)
                uploaded[key] = path
            elif slot.get("required"):
                jm.fail(job_id, f"필수 파일 누락: {slot['label']}")
                return jsonify({"job_id": job_id, "error": f"필수 파일 누락: {slot['label']}"}), 400

    # 재조판(/api/rerun) 재료 영속화 (W41) — uploaded 매핑 + material_id.
    # 실패해도 본 조판에는 영향 없음 (fail-open).
    try:
        with open(os.path.join(job_dir, "uploaded.json"), "w",
                  encoding="utf-8") as _uf:
            json.dump(uploaded, _uf, ensure_ascii=False, indent=1)
        open(os.path.join(job_dir, "material_id.txt"), "w").write(material_id)
    except Exception as _pe:
        print(f"[rerun-persist-error] {_pe}", flush=True)

    threading.Thread(
        target=run_pipeline,
        args=(engine, job_id, job_dir, uploaded),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})


@bp.route("/api/rerun/<job_id>", methods=["POST"])
def api_rerun(job_id):
    """검수 에이전트 auto_fixable 제안에 대한 사용자 승인 재조판 (W41).

    같은 원고(uploads)와 메타데이터로 새 job을 만들어 파이프라인을 다시
    실행한다 — 검수 에이전트는 제안만 하고, 실제 재조판은 이 라우트를
    호출하는 사용자 클릭으로만 일어난다 (무단 재조판 금지).
    """
    # job_id는 uuid 앞 8자리 hex — 경로 조작 차단
    if not re.fullmatch(r"[0-9a-f]{8}", job_id or ""):
        return jsonify({"error": "잘못된 job id"}), 400
    old_dir = os.path.join(config.JOBS_DIR, job_id)
    mid_path = os.path.join(old_dir, "material_id.txt")
    up_path = os.path.join(old_dir, "uploaded.json")
    if not (os.path.isdir(old_dir) and os.path.isfile(mid_path)
            and os.path.isfile(up_path)):
        return jsonify({"error": "재조판 재료 없음 (원 job 소멸)"}), 404
    material_id = open(mid_path).read().strip()
    try:
        engine = registry.get(material_id)
    except KeyError:
        return jsonify({"error": f"교재 없음 (id: {material_id})"}), 404
    with open(up_path, encoding="utf-8") as f:
        old_uploaded = json.load(f)

    new_id = jm.create_job(material_id)
    new_dir = jm.get_job(new_id)["dir"]
    new_upload_dir = os.path.join(new_dir, "uploads")

    # 메타데이터(.txt) 복사 — school/issue_num/exclude/review_agent 등 전부.
    # (재조판 재료 파일 자체는 새 실행이 다시 쓰므로 제외)
    for name in sorted(os.listdir(old_dir)):
        if name.endswith(".txt") and name != "조판_로그.txt":
            shutil.copy2(os.path.join(old_dir, name),
                         os.path.join(new_dir, name))
    # 업로드 파일 복사 + uploaded 매핑 경로 재작성
    old_up_prefix = os.path.join(old_dir, "uploads")

    def _carry(p):
        if isinstance(p, str) and p.startswith(old_up_prefix):
            dst = os.path.join(new_upload_dir, os.path.basename(p))
            shutil.copy2(p, dst)
            return dst
        return p

    uploaded = {}
    for key, val in old_uploaded.items():
        if isinstance(val, list):
            uploaded[key] = [_carry(v) for v in val]
        else:
            uploaded[key] = _carry(val)

    # 연쇄 재조판 대비 — 새 job에도 재료 영속화 (fail-open)
    try:
        with open(os.path.join(new_dir, "uploaded.json"), "w",
                  encoding="utf-8") as f:
            json.dump(uploaded, f, ensure_ascii=False, indent=1)
    except Exception as _pe:
        print(f"[rerun-persist-error] {_pe}", flush=True)

    threading.Thread(
        target=run_pipeline,
        args=(engine, new_id, new_dir, uploaded),
        daemon=True
    ).start()

    return jsonify({"job_id": new_id, "rerun_of": job_id})


@bp.route("/api/stream/<job_id>")
def api_stream(job_id):
    if not jm.get_job(job_id):
        return "job not found", 404

    return Response(
        stream_with_context(jm.stream(job_id)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@bp.route("/api/cancel/<job_id>", methods=["POST"])
def api_cancel(job_id):
    if not jm.get_job(job_id):
        return jsonify({"error": "job not found"}), 404
    jm.cancel_job(job_id)
    return jsonify({"ok": True})


@bp.route("/api/result/<job_id>")
def api_result(job_id):
    job = jm.get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify({
        "status": job["status"],
        "result": job["result"],
    })


@bp.route("/download/<job_id>/pdf")
def download_pdf(job_id):
    job = jm.get_job(job_id)
    if not job or not job.get("result"):
        return "결과 없음", 404
    pdf_path = job["result"].get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        return "PDF 없음", 404
    return send_file(pdf_path, as_attachment=True,
                     download_name=os.path.basename(pdf_path))
