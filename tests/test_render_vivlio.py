"""Vivliostyle 렌더 백엔드 + mockexam_v2_viv 엔진 (W51).

오프라인 검사(CLI/InDesign 미실행). E2E PDF 생성 검증은 별도 실측으로 수행.
"""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


# ── 백엔드 선택 계층 ─────────────────────────────────────────────────────
# Vivliostyle 백엔드를 **일부러** 쓰는 카드들. 새 카드를 여기 적지 않으면
# 이 검사가 막는다 — 기존 엔진이 슬그머니 백엔드를 바꾸는 것을 잡으려는 것이다.
VIVLIO_OPT_IN = {"mockexam_v2_viv", "final_viv"}


def test_base_engine_default_backend_is_indesign():
    """BaseEngine 기본 render_backend = 'indesign' — 기존 엔진 전부 무변경."""
    from engines import registry
    for e in registry.all_engines():
        if e.material_id in VIVLIO_OPT_IN:
            continue
        assert getattr(e, "render_backend", "indesign") == "indesign", e.material_id


def test_vivlio_engine_backend_is_vivliostyle():
    from engines import registry
    e = registry.get("mockexam_v2_viv")
    assert e.render_backend == "vivliostyle"


def test_pipeline_render_backend_resolver(tmp_path):
    """_render_backend: 엔진 속성 기본 + job override 파일 우선순위."""
    from core.pipeline import _render_backend
    from engines import registry

    idn = registry.get("mockexam_v2")     # indesign
    viv = registry.get("mockexam_v2_viv")  # vivliostyle
    job = str(tmp_path)
    assert _render_backend(idn, job) == "indesign"
    assert _render_backend(viv, job) == "vivliostyle"

    # job override 파일이 우선
    with open(os.path.join(job, "render_backend.txt"), "w") as f:
        f.write("vivliostyle")
    assert _render_backend(idn, job) == "vivliostyle"
    with open(os.path.join(job, "render_backend.txt"), "w") as f:
        f.write("indesign")
    assert _render_backend(viv, job) == "indesign"
    # 알 수 없는 값은 무시하고 엔진 기본으로
    with open(os.path.join(job, "render_backend.txt"), "w") as f:
        f.write("garbage")
    assert _render_backend(viv, job) == "vivliostyle"


# ── 엔진 등록 정합성 ─────────────────────────────────────────────────────
def test_vivlio_engine_registration():
    from engines import registry
    from engines.mockexam_v2.engine import MockexamV2Engine
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "mockexam_v2_viv" in engines
    assert "mockexam_v2" in engines        # 기존 엔진 유지 (삭제 금지 규칙)
    assert "mockexam" in engines

    e = engines["mockexam_v2_viv"]
    # 파서/플랜/구조 인식은 mockexam_v2 상속 (같은 플랜, 다른 백엔드)
    assert isinstance(e, MockexamV2Engine)
    # 업로드 슬롯은 부모와 동일 (같은 원고)
    assert e.upload_spec == engines["mockexam_v2"].upload_spec

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "mockexam_v2_viv"' in raw
    assert '"engine_id": "mockexam_v2"' in raw     # 기존 카드 유지

    tpl = os.path.join(REPO, "templates", e.template_name)
    assert e.template_name == "typeset_mockexam_v2_viv.html"
    assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
    src = open(tpl, encoding="utf-8").read()
    assert 'const MATERIAL_ID = "mockexam_v2_viv"' in src


# ── HTML 빌더 (플랜 → 시맨틱 HTML) ──────────────────────────────────────
def test_style_class_covers_flow_styles():
    """style_map 의 mockexam_v2 FLOW 스타일명이 STYLE_CLASS 로 매핑되는가."""
    from core.render_vivlio.mockexam import STYLE_CLASS
    smap = json.load(open(os.path.join(REPO, "core", "structure",
                                       "style_map.json"), encoding="utf-8"))
    flow = smap["mockexam_v2"]["FLOW"]
    for kind, style_name in flow.items():
        assert style_name in STYLE_CLASS, f"미매핑 스타일: {kind}={style_name}"


def test_plan_to_body_numbering_and_markup():
    from core.render_vivlio.mockexam import plan_to_body
    plan = [
        {"t": "다음 글을 읽고 물음에 답하시오.", "s": "다음 글을 읽고", "runs": []},
        {"t": "첫 발문", "s": "문제 번호", "runs": []},
        {"t": "This is a passage with (A) here.", "s": "지문",
         "runs": [{"t": "This is a ", "ul": False},
                  {"t": "passage", "ul": True},
                  {"t": " with (A) here.", "ul": False}]},
        {"t": "① one", "s": "선지", "runs": []},
        {"t": "② two", "s": "선지", "runs": []},
        {"t": "둘째 발문", "s": "문제 번호", "runs": []},
        {"t": "서술형 발문", "s": "서술형 번호", "runs": []},
    ]
    body = plan_to_body(plan)
    joined = "\n".join(body)
    # 자동 번호: 1., 2.
    assert '<p class="q"><span class="qnum">1.' in joined
    assert '<p class="q"><span class="qnum">2.' in joined
    # 서술형 번호
    assert "[서술형 1]" in joined
    # 밑줄 run
    assert "<u>passage</u>" in joined
    # GREP 볼드 (지문 안 (A))
    assert "<b>(A)</b>" in joined
    # 선지 첫 항목 choice-first
    assert "choice-first" in joined


def test_box_grouping():
    from core.render_vivlio.mockexam import plan_to_body
    plan = [
        {"t": "박스1", "s": "테두리", "runs": []},
        {"t": "박스2", "s": "테두리", "runs": []},
        {"t": "지문", "s": "지문", "runs": []},
    ]
    body = "\n".join(plan_to_body(plan))
    assert body.count('<div class="box">') == 1
    assert body.count("</div>") == 1


def test_build_html_has_header_footer_and_theme_link():
    from core.render_vivlio.mockexam import build_html
    case = {"subject_title": "영어독해와작문", "school_full": "한영고등학교",
            "copyright_line": "저작권 문구", "qtype_box": {"select_items": 27}}
    doc = build_html([{"t": "x", "s": "지문", "runs": []}], case)
    assert '<link rel="stylesheet" href="theme.css">' in doc
    assert 'class="page-header"' in doc
    assert 'position: running' not in doc      # 러닝 위치는 CSS 소관
    assert "영어독해와작문" in doc
    assert "다음 쪽에 계속" in doc
    assert "한영고등학교" in doc


# ── 테마/자산 존재 ──────────────────────────────────────────────────────
def test_theme_files_exist():
    themes = os.path.join(REPO, "core", "render_vivlio", "themes")
    assert os.path.isfile(os.path.join(themes, "mockexam.css"))
    assert os.path.isfile(os.path.join(themes, "_base.css"))


def test_case_builder_overrides_school():
    from core.render_vivlio.case import build_case
    c = build_case({"school": "성덕고등학교", "grade": "고3"})
    assert c["school_full"] == "성덕고등학교"
    assert "성덕고등학교" in c["copyright_line"]
    # 픽스처의 템플릿 비품(문제유형 박스)은 기본값으로 남는다
    assert "qtype_box" in c
