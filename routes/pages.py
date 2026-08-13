"""페이지 라우트 — 인덱스 (조판/표지/가공) + /typeset/<material_id> (app.py에서 분리, C2-9)."""
import os

from flask import Blueprint, redirect, render_template, request, send_from_directory

from core.webdata import load_schools, load_subjects
from engines import registry

bp = Blueprint("pages", __name__)

_SECTION_CONFIG = {
    "조판": {
        "title": "조판",
        "hero_title": "Y.ONE 조판",
        "hero_desc": "교재를 선택하고 원고를 업로드하면 InDesign 조판 → PDF까지 자동으로 처리됩니다.",
        "hero_tip": "원하는 <strong>교재 카드</strong>를 클릭하면 원고 업로드 화면으로 이동합니다.",
        "cta_text": "시작",
    },
    "표지": {
        "title": "표지",
        "hero_title": "Y.ONE 표지",
        "hero_desc": "세네카 조정, 아웃라인 변환, PDF 출력까지 표지 작업을 자동화합니다.",
        "hero_tip": "원하는 <strong>표지 종류</strong>를 선택하면 작업 화면으로 이동합니다.",
        "cta_text": "시작",
    },
    "가공": {
        "title": "가공",
        "hero_title": "Y.ONE 가공",
        "hero_desc": "조판이 완료된 교재에서 시험범위 외 회차/유형별 문항을 일괄 정리합니다.",
        "hero_tip": "가공할 <strong>교재 종류</strong>를 선택하세요.",
        "cta_text": "시작",
    },
}


def _subjects_by_section(section):
    return [c for c in load_subjects() if c.get("section") == section]


@bp.route("/")
def index():
    cfg = _SECTION_CONFIG["조판"]
    return render_template("index.html",
                           subjects=_subjects_by_section("조판"),
                           active_nav="조판",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"])


@bp.route("/cover")
def cover_index():
    cfg = _SECTION_CONFIG["표지"]
    return render_template("index.html",
                           subjects=_subjects_by_section("표지"),
                           active_nav="표지",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"])


@bp.route("/processing")
def processing_index():
    cfg = _SECTION_CONFIG["가공"]
    subjects = _subjects_by_section("가공")
    # "가공" 섹션은 engine_id 카드를 직접 라우트로 사용 (typeset이 아닌 processing)
    return render_template("index.html",
                           subjects=subjects,
                           active_nav="가공",
                           section_title=cfg["title"],
                           hero_title=cfg["hero_title"],
                           hero_desc=cfg["hero_desc"],
                           hero_tip=cfg.get("hero_tip"),
                           cta_text=cfg["cta_text"],
                           card_url_prefix="/processing/")


def _section_for_engine(material_id):
    for cat in load_subjects():
        for item in cat.get("items", []):
            if item.get("engine_id") == material_id:
                return cat.get("section", "조판")
    return "조판"


@bp.route("/typeset/<material_id>")
def typeset_page(material_id):
    try:
        engine = registry.get(material_id)
    except KeyError:
        return "교재를 찾을 수 없습니다.", 404
    tmpl = getattr(engine, "template_name", "typeset.html")
    nav = _section_for_engine(material_id)

    # 파이널 엔진: 워크북 폴더에서 학교 목록 자동 스캔
    exam_periods = []
    current_period = ""
    if material_id == "final":
        from engines.final.engine import (
            _load_config as _load_final_config,
            scan_exam_periods, estimate_exam_period, resolve_exam_period,
        )
        fcfg = _load_final_config()
        exam_periods = scan_exam_periods(fcfg["gdrive_base"])
        # 드롭다운으로 명시 선택 시 URL 파라미터 우선, 없으면 날짜 기반 자동 추정
        sel = request.args.get("exam_period", "").strip()
        if sel and sel in exam_periods:
            current_period = sel
        else:
            current_period = (estimate_exam_period(exam_periods)
                              or resolve_exam_period(fcfg))
        schools = engine.scan_schools(fcfg["gdrive_base"], current_period)
        if not schools:
            schools = load_schools()
    else:
        schools = load_schools()

    return render_template(tmpl, engine=engine, schools=schools,
                           active_nav=nav, exam_periods=exam_periods,
                           current_period=current_period)


# ── 외부 공개 소개 페이지 (단가표에서 견적계산·가격 섹션 제외판) ──────────
# 인증 예외는 routes/auth.py check_auth의 /design 허용 참조.
# 원본: 디자인/기타/제작단가표(외부용_3라인).html (가격 포함 백업: 같은 폴더 .bak-with-pricing-20260813)
_DESIGN_INTRO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "design_intro")


@bp.route("/design")
def design_intro_redirect():
    # 상대경로(portfolio/...)가 /design/ 기준으로 풀리도록 슬래시로 고정
    return redirect("/design/", code=308)


@bp.route("/design/")
def design_intro_index():
    return send_from_directory(_DESIGN_INTRO_DIR, "index.html")


@bp.route("/design/<path:asset_path>")
def design_intro_asset(asset_path):
    return send_from_directory(_DESIGN_INTRO_DIR, asset_path)
