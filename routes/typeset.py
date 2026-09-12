"""조판 실행 API — /api/run, /api/stream(SSE), /api/cancel, /api/result,
/download/<job_id>/pdf (app.py에서 분리, C2-9). 파이프라인 본체는 core/pipeline.py."""
import json
import os
import re
import shutil
import threading
import time
import unicodedata

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
            # 폴더째 업로드 — 프런트가 input.files 순서와 1:1로 상대경로를
            # 보낸다. '폴더 = 원고 한 세트'를 엔진이 복원하는 근거이며,
            # 없으면(낱개 파일 업로드) 빈 값이다.
            try:
                rel_paths = json.loads(request.form.get(f"{key}_relpaths", "")
                                       or "[]")
                if not isinstance(rel_paths, list):
                    rel_paths = []
            except (ValueError, TypeError):
                rel_paths = []
            # 원고의 원래 수정시각(브라우저 lastModified, ms) — 저장 파일의
            # mtime 으로 복원한다. 파서의 '같은 단계 원고 중 최신본' 규칙이
            # 이 시각을 본다 (없으면 저장 시각 = 전부 동률 → 개정 표기로만
            # 판정).
            try:
                mtimes = json.loads(request.form.get(f"{key}_mtimes", "")
                                    or "[]")
                if not isinstance(mtimes, list):
                    mtimes = []
            except (ValueError, TypeError):
                mtimes = []
            paths = []
            manifest = []
            used_names = set()
            for _i, f in enumerate(files):
                if f and f.filename:
                    # (C1-3) 확장자 화이트리스트 — 슬롯 accept가 진실
                    if not allowed_by_accept(f.filename, slot.get("accept", "")):
                        msg = (f"허용되지 않는 파일 형식: {f.filename} "
                               f"(허용: {slot.get('accept')})")
                        jm.fail(job_id, msg)
                        return jsonify({"job_id": job_id, "error": msg}), 400
                    base = f"{key}_{sanitize_filename(f.filename)}"
                    # 같은 이름이 여러 개 오면 덮어쓰지 않는다 — 원고가 여러
                    # 폴더로 나뉜 교재는 'Step1 A1 어휘선택.docx'가 폴더마다
                    # 있어서, 종전 규칙이면 마지막 하나만 남고 나머지가
                    # 조용히 사라졌다 (2026-09-08 사용자 실증).
                    safe_name = base
                    if safe_name in used_names:
                        stem, ext = os.path.splitext(base)
                        n = 2
                        while f"{stem}__{n}{ext}" in used_names:
                            n += 1
                        safe_name = f"{stem}__{n}{ext}"
                    used_names.add(safe_name)
                    path = os.path.join(upload_dir, safe_name)
                    f.save(path)
                    paths.append(path)
                    _mt = mtimes[_i] if _i < len(mtimes) else 0
                    if isinstance(_mt, (int, float)) and _mt > 0:
                        try:
                            os.utime(path, (_mt / 1000.0, _mt / 1000.0))
                        except OSError:
                            pass
                    rel = rel_paths[_i] if _i < len(rel_paths) else ""
                    manifest.append({"saved": safe_name,
                                     "rel": rel if isinstance(rel, str) else "",
                                     "name": f.filename})
            if paths:
                uploaded[key] = paths
                if any(m["rel"] for m in manifest):
                    with open(os.path.join(job_dir, f"{key}_manifest.json"),
                              "w", encoding="utf-8") as _mf:
                        json.dump(manifest, _mf, ensure_ascii=False, indent=1)
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
    if job:
        return jsonify({
            "status": job["status"],
            "result": job["result"],
        })

    # 인메모리 잡이 없다 = 서버가 그 사이 재시작됐다는 뜻(개발 자동 재시작·
    # 크래시·수동 재기동). 결과가 디스크에 남아 있으면 그것으로 되살리고,
    # 없으면 InDesign 이 아직 돌고 있는지 로그 갱신 시각으로 판별해 알려준다.
    # (종전에는 무조건 404 → "결과를 찾을 수 없습니다. 다시 실행하세요" 안내가
    #  나가서, 실제로는 조판이 계속 돌고 있는데 중복 실행을 유도했다.)
    saved = jm.load_result(job_id)
    if saved:
        return jsonify({"status": saved.get("status", "done"),
                        "result": saved.get("result")})

    job_dir = os.path.join(config.JOBS_DIR, job_id)
    if os.path.isdir(job_dir):
        last_line, age = _job_log_progress(job_dir)
        if age is not None and age < 300:
            msg = ("서버가 재시작되어 진행 표시가 끊겼습니다. "
                   "InDesign 은 계속 조판 중입니다"
                   + (f" (마지막 진행: {last_line})" if last_line else "")
                   + ". 다시 실행하지 말고 InDesign 이 끝날 때까지 기다리세요. "
                     "조판이 끝나도 검수·PDF 단계는 자동으로 이어지지 않습니다.")
        else:
            msg = ("서버가 재시작되어 작업이 중단됐습니다"
                   + (f" (마지막 진행: {last_line})" if last_line else "")
                   + ". InDesign 에 남은 작업이 없으면 다시 실행해 주세요.")
        return jsonify({"status": "error", "result": {"ok": False, "error": msg}})

    return jsonify({"error": "job not found"}), 404


def _job_log_progress(job_dir: str):
    """잡 폴더의 조판 로그에서 (마지막 줄, 갱신된 지 몇 초) 를 얻는다.
    로그 파일 이름은 엔진마다 다를 수 있어 폴더 안 *로그*.txt 중 최신을 본다."""
    try:
        # macOS 파일명은 NFD 로 분해돼 오므로 NFC 로 맞춰서 비교한다
        # (안 맞추면 '조판_로그.txt' 가 "로그" 검색에 걸리지 않는다).
        cands = [os.path.join(job_dir, f) for f in os.listdir(job_dir)
                 if f.endswith(".txt")
                 and "로그" in unicodedata.normalize("NFC", f)]
        if not cands:
            return None, None
        path = max(cands, key=os.path.getmtime)
        age = time.time() - os.path.getmtime(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()[-4000:]
        # JSX 로그는 \r 로 이어붙는 경우가 있어 둘 다 줄바꿈으로 본다.
        lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")
                 if ln.strip()]
        return (lines[-1] if lines else None), age
    except Exception:
        return None, None


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
