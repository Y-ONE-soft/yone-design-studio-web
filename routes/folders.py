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
    try:
        return jsonify(TextbookWorkbookEngine.list_files(
            subject, publisher, lesson_folder))
    except OSError as e:
        # GDrive Stream 일시 장애(EDEADLK 등)로 500이 나면 브라우저가
        # manuscript_folder hidden 필드를 못 채워 '0유닛' 조판으로 이어졌다.
        # 목록은 못 줘도 폴더 경로는 돌려주고, 실패를 화면에 노출한다.
        try:
            wb = TextbookWorkbookEngine.find_workbook_dir(
                subject, publisher, lesson_folder)
        except OSError:
            wb = None
        return jsonify({"workbook_dir": wb, "files": [],
                        "error": f"폴더 목록을 읽지 못했습니다 ({e.errno}) — "
                                 f"구글 드라이브 동기화 후 다시 시도하세요"})


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


# ── 포켓북(Vivliostyle) — 학기·학교 목록 ────────────────────────────────────
#   목록을 하드코딩하지 않는다. **분석본 IDML 이 나와 있는 것**만 보여 준다 —
#   그래야 고를 수 있는 것과 실제로 조판되는 것이 어긋나지 않는다.

@bp.route("/api/pocketbook-viv/terms")
def api_pbviv_terms():
    from engines.pocketbook_viv.engine import terms
    return jsonify(terms())


@bp.route("/api/pocketbook-viv/schools")
def api_pbviv_schools():
    from flask import request
    from engines.pocketbook_viv.engine import schools_for
    return jsonify(schools_for(request.args.get("term", "")))


@bp.route("/api/pocketbook-viv/scope")
def api_pbviv_scope():
    """그 학교·학기의 **시험범위**. 카드에 보여 주기만 한다(고르는 게 아니다)."""
    from flask import request
    from engines.pocketbook_viv.engine import PocketbookVivEngine as E
    school = request.args.get("school", "")
    term = request.args.get("term", "")
    return jsonify({"text": E._scope(school, term, lambda m: None)})


# ── 분석본 결합 v2 — 교과서/EBS 소스 탐색 API (W28-확장) ─────────────────────

@bp.route("/api/analysis-merge/tb-subjects")
def api_am_tb_subjects():
    from engines.analysis_merge_v2.engine import _load_config
    from engines.analysis_merge_v2 import sources as srcmod
    return jsonify(srcmod.list_textbook_subjects(_load_config()))


@bp.route("/api/analysis-merge/tb-publishers")
def api_am_tb_publishers():
    from engines.analysis_merge_v2.engine import _load_config
    from engines.analysis_merge_v2 import sources as srcmod
    subject = request.args.get("subject", "")
    return jsonify(srcmod.list_textbook_publishers(_load_config(), subject))


@bp.route("/api/analysis-merge/tb-lessons")
def api_am_tb_lessons():
    from engines.analysis_merge_v2.engine import _load_config
    from engines.analysis_merge_v2 import sources as srcmod
    subject = request.args.get("subject", "")
    publisher = request.args.get("publisher", "")
    return jsonify(srcmod.list_textbook_lessons(_load_config(),
                                                subject, publisher))


@bp.route("/api/analysis-merge/ebs-books")
def api_am_ebs_books():
    from engines.analysis_merge_v2.engine import _load_config
    from engines.analysis_merge_v2 import sources as srcmod
    return jsonify(srcmod.list_ebs_books(_load_config()))


@bp.route("/api/analysis-merge/ebs-units")
def api_am_ebs_units():
    from engines.analysis_merge_v2.engine import _load_config
    from engines.analysis_merge_v2 import sources as srcmod
    book = request.args.get("book", "")
    return jsonify(srcmod.list_ebs_units(_load_config(), book))


# ── 마더텅 결합 API ──────────────────────────────────────────────────────────

@bp.route("/api/mothertongue/lessons")
def api_mothertongue_lessons():
    from engines.mothertongue_merge.engine import MothertongueMergeEngine
    grade = request.args.get("grade", "고1")
    school = request.args.get("school", "한영고1")
    return jsonify(MothertongueMergeEngine.list_lessons(grade, school))


# ── 지문 제거 API (W26) ──────────────────────────────────────────────────────

@bp.route("/api/passage-remove/scan-dir", methods=["POST"])
def api_passage_remove_scan_dir():
    """폴더 내 .indd 파일 목록 (pocketbook scan-dir 패턴)."""
    import unicodedata as _ud
    data = request.get_json() or {}
    folder = os.path.abspath(os.path.expanduser(data.get("path", "")))
    if not os.path.isdir(folder):
        return jsonify({"error": "폴더를 찾을 수 없습니다", "path": folder})
    files = []
    try:
        for raw in sorted(os.listdir(folder)):
            if raw.startswith("."):
                continue
            nfc = _ud.normalize("NFC", raw)
            if nfc.lower().endswith(".indd"):
                files.append(nfc)
    except PermissionError:
        return jsonify({"error": "접근 권한 없음", "path": folder})
    return jsonify({"path": folder, "files": files})


@bp.route("/api/passage-remove/inventory", methods=["POST"])
def api_passage_remove_inventory():
    """.indd → 지문 인벤토리 추출 (InDesign dump + 매처 그룹핑).

    입력: multipart(indd 파일) 또는 form/json doc_path(서버 경로).
    원본은 수정하지 않는다 — 사본을 떠서 dump한다. 수 분 소요 가능.
    """
    from core.uploads import sanitize_filename
    from engines.passage_remove.engine import (
        INVENTORY_BASE, create_inventory)

    src = None
    if "indd" in request.files and request.files["indd"].filename:
        f = request.files["indd"]
        name = sanitize_filename(f.filename)
        if not name.lower().endswith(".indd"):
            return jsonify({"error": ".indd 파일만 지원"}), 400
        up_dir = os.path.join(INVENTORY_BASE, "_uploads")
        os.makedirs(up_dir, exist_ok=True)
        src = os.path.join(up_dir, name)
        f.save(src)
    else:
        data = request.get_json(silent=True) or request.form
        doc_path = (data.get("doc_path") or "").strip()
        if not doc_path:
            return jsonify({"error": "doc_path 또는 indd 파일 필요"}), 400
        src = os.path.abspath(os.path.expanduser(doc_path))
        if not (os.path.isfile(src) and src.lower().endswith(".indd")):
            return jsonify({"error": ".indd 파일을 찾을 수 없습니다",
                            "path": src}), 400

    logs = []
    try:
        inv_id, inv = create_inventory(src, logs.append)
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"error": f"인벤토리 추출 실패: {e}",
                        "log": logs[-5:]}), 500
    groups = [
        {"gid": g["gid"], "label": g["label"], "title": g["title"],
         "sections": g["sections"], "units": len(g["unit_uids"]),
         "hub": g["hub"], "multi": g["multi"]}
        for g in inv["groups"]
    ]
    return jsonify({"inventory_id": inv_id, "doc": inv["source_name"],
                    "groups": groups, "log": logs})


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
