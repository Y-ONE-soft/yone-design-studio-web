"""엔진별 폴더 탐색/스캔 API + 학교 관리 API (app.py에서 분리, C2-9)."""
import os

from flask import Blueprint, jsonify, request

from core.webdata import load_schools, save_schools

bp = Blueprint("folders", __name__)


# ── 폴더 브라우저 API (웹 기반 — 원격 접속에서도 동작) ────────────────────────

@bp.route("/api/browse-folder", methods=["POST"])
def api_browse_folder():
    """서버 파일시스템의 폴더 목록을 반환. 어떤 기기에서 접속해도 동작."""
    import unicodedata as _ud
    data = request.get_json() or {}
    path = data.get("path", "")

    # 기본 경로: 구글드라이브 분석본/고1,고2(공통) 폴더
    if not path:
        path = os.path.expanduser(
            "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com"
            "/내 드라이브/콘텐츠 관리/내신대비"
            "/인디자인 파일/분석본/고1,고2(공통)"
        )
        if not os.path.isdir(path):
            path = os.path.expanduser(
                "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com"
                "/내 드라이브/콘텐츠 관리/내신대비"
            )
        if not os.path.isdir(path):
            path = os.path.expanduser("~")

    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return jsonify({"error": "폴더를 찾을 수 없습니다", "path": path})

    dirs = []
    has_indd = False
    try:
        for raw in sorted(os.listdir(path)):
            nfc = _ud.normalize("NFC", raw)
            full = os.path.join(path, raw)
            if raw.startswith("."):
                continue
            if os.path.isdir(full):
                dirs.append(nfc)
            elif nfc.endswith(".indd") and "분석본" in nfc:
                has_indd = True
    except PermissionError:
        return jsonify({"error": "접근 권한 없음", "path": path})

    parent = os.path.dirname(path) if path != "/" else None
    return jsonify({
        "path": path,
        "parent": parent,
        "dirs": dirs,
        "has_indd": has_indd,
    })


# ── 교과서 워크북 폴더 탐색 API ──────────────────────────────────────────────

@bp.route("/api/textbook-workbook/subjects")
def api_tw_subjects():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    return jsonify(TextbookWorkbookEngine.list_subjects())


@bp.route("/api/textbook-workbook/publishers")
def api_tw_publishers():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    return jsonify(TextbookWorkbookEngine.list_publishers(subject))


@bp.route("/api/textbook-workbook/lessons")
def api_tw_lessons():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    publisher = request.args.get("publisher", "")
    return jsonify(TextbookWorkbookEngine.list_lessons(subject, publisher))


@bp.route("/api/textbook-workbook/files")
def api_tw_files():
    from engines.textbook_workbook.engine import TextbookWorkbookEngine
    subject = request.args.get("subject", "")
    publisher = request.args.get("publisher", "")
    lesson_folder = request.args.get("lesson_folder", "")
    return jsonify(TextbookWorkbookEngine.list_files(subject, publisher, lesson_folder))


# ── EBS 리딩파워 워크북 폴더 탐색 API ─────────────────────────────────────────

@bp.route("/api/ebs-workbook/units")
def api_ebs_units():
    from engines.ebs_workbook.engine import EbsWorkbookEngine
    return jsonify(EbsWorkbookEngine.list_units())


@bp.route("/api/ebs-workbook/files")
def api_ebs_files():
    from engines.ebs_workbook.engine import EbsWorkbookEngine
    unit_folder = request.args.get("unit_folder", "")
    return jsonify(EbsWorkbookEngine.list_files(unit_folder))


# ── 수능특강 워크북 폴더 탐색 API ─────────────────────────────────────────────

@bp.route("/api/suneungteukgang-workbook/units")
def api_st_units():
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    return jsonify(SuneungteukgangWorkbookEngine.list_units())


@bp.route("/api/suneungteukgang-workbook/files")
def api_st_files():
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    unit_folder = request.args.get("unit_folder", "")
    return jsonify(SuneungteukgangWorkbookEngine.list_files(unit_folder))


@bp.route("/api/suneungteukgang-workbook/merge", methods=["POST"])
def api_st_merge():
    """다중 강 통합 — 강별 indd를 첫 indd 끝에 duplicate해서 한 파일로 합침."""
    from engines.suneungteukgang_workbook.engine import SuneungteukgangWorkbookEngine
    body = request.get_json() or {}
    lessons = body.get("lessons", [])
    if not isinstance(lessons, list) or len(lessons) < 2:
        return jsonify({"error": "lessons 배열(2개 이상) 필요"}), 400

    logs = []
    def _log(msg):
        logs.append(msg)
    result = SuneungteukgangWorkbookEngine.merge_lessons(lessons, _log)
    return jsonify({"result": result, "logs": logs})


@bp.route("/api/suneungteukgang-workbook-v2/merge", methods=["POST"])
def api_st_v2_merge():
    """다중 강 통합 (v2) — 강별 _v2 indd를 spread duplicate로 합치고
    검수 게이트(강별 단어셋 보존 + 스프레드 수 정합)까지 수행."""
    from engines.suneungteukgang_workbook_v2.engine import (
        SuneungteukgangWorkbookV2Engine)
    body = request.get_json() or {}
    lessons = body.get("lessons", [])
    if not isinstance(lessons, list) or len(lessons) < 2:
        return jsonify({"error": "lessons 배열(2개 이상) 필요"}), 400

    logs = []
    result = SuneungteukgangWorkbookV2Engine.merge_lessons(lessons,
                                                           logs.append)
    return jsonify({"result": result, "logs": logs})


# ── 포켓북 분석본 스캔 API ────────────────────────────────────────────────────

@bp.route("/api/pocketbook/scan-dir", methods=["POST"])
def api_pocketbook_scan():
    import re as _re
    import unicodedata as _ud
    data = request.get_json()
    folder = data.get("path", "")

    if not folder or not os.path.isdir(folder):
        return jsonify({"files": [], "error": "폴더를 찾을 수 없습니다"})

    # macOS NFD 파일명 대응: NFC 정규화 후 매칭
    raw_files = os.listdir(folder)
    analysis = []
    pocketbook = None
    for raw in raw_files:
        nfc = _ud.normalize("NFC", raw)
        if not nfc.endswith(".indd"):
            continue
        if "분석본" in nfc:
            if _re.search(r"\d{2}년\d{1,2}월", nfc) or "모의" in nfc or "마더텅" in nfc:
                stype = "모의고사"
            elif "올포" in nfc or "올림" in nfc:
                stype = "EBS"
            else:
                stype = "교과서"
            analysis.append({"name": nfc, "type": stype, "raw": raw})
        elif "포켓북" in nfc and "분석본" not in nfc and not pocketbook:
            pocketbook = os.path.join(folder, raw)

    analysis.sort(key=lambda x: (_re.search(r"(\d+)", x["name"]).group(1)
                                  if _re.search(r"(\d+)", x["name"]) else "99"))
    result = [{"name": a["name"], "type": a["type"]} for a in analysis]

    return jsonify({"files": result, "pocketbook": pocketbook, "folder": folder})


# ── 파이널 워크북 감지 API ────────────────────────────────────────────────────

@bp.route("/api/final/detect-workbooks", methods=["POST"])
def api_final_detect():
    data = request.get_json()
    school = data.get("school", "")
    grade = data.get("grade", "고1")
    exam_period = data.get("exam_period", "").strip()
    from engines.final.engine import (
        FinalEngine, _load_config as _load_final_config,
        scan_exam_periods, estimate_exam_period,
    )
    from engines.final.scope_parser import parse_all_scopes
    fcfg = _load_final_config()
    if not exam_period:
        exam_period = estimate_exam_period(scan_exam_periods(fcfg["gdrive_base"]))
    files, wb_dir, _ = FinalEngine.find_workbook_files(
        fcfg["gdrive_base"], exam_period, grade, school
    )
    scopes = parse_all_scopes(files) if files else []

    # 교재 매핑 정보
    textbook_info = fcfg.get("school_textbook_map", {}).get(
        exam_period, {}
    ).get(school)

    # 고3: 분석편에서 사용 가능한 강 목록 반환
    available_lectures = []
    if grade == "고3":
        available_lectures = FinalEngine.scan_lectures()

    return jsonify({
        "count": len(files),
        "files": [os.path.basename(f) for f in files],
        "path": wb_dir,
        "scopes": scopes,
        "textbook": textbook_info,
        "available_lectures": available_lectures,
    })


# ── 동형모의고사 API ──────────────────────────────────────────────────────────

@bp.route("/api/mockexam/schools")
def api_mockexam_schools():
    from engines.mockexam.engine import MockexamEngine
    schools = MockexamEngine.scan_schools()
    return jsonify(schools)


# ── 마더텅 결합 API ──────────────────────────────────────────────────────────

@bp.route("/api/mothertongue/lessons")
def api_mothertongue_lessons():
    from engines.mothertongue_merge.engine import MothertongueMergeEngine
    grade = request.args.get("grade", "고1")
    school = request.args.get("school", "한영고1")
    return jsonify(MothertongueMergeEngine.list_lessons(grade, school))


# ── 학교 관리 API ────────────────────────────────────────────────────────────

@bp.route("/api/schools")
def api_schools_get():
    return jsonify(load_schools())


@bp.route("/api/schools", methods=["POST"])
def api_schools_add():
    data = request.get_json()
    grade, name = data.get("grade", "").strip(), data.get("name", "").strip()
    if not grade or not name:
        return jsonify({"error": "grade/name 필요"}), 400
    schools = load_schools()
    if grade not in schools:
        schools[grade] = []
    if name not in schools[grade]:
        schools[grade].append(name)
        save_schools(schools)
    return jsonify({"ok": True})


@bp.route("/api/schools/<grade>/<school_name>", methods=["DELETE"])
def api_schools_delete(grade, school_name):
    schools = load_schools()
    if grade in schools and school_name in schools[grade]:
        schools[grade].remove(school_name)
        save_schools(schools)
    return jsonify({"ok": True})
