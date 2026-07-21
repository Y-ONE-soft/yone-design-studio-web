# -*- coding: utf-8 -*-
"""검수 에이전트 UI의 전 조판 템플릿 노출 계약 (W41 후속).

W41 미해결 (1)(2)의 마무리를 정적으로 가드한다:

(1) 체크박스: 모든 typeset*.html은 공용 partial(_review_agent_opt.html)을
    include — 폼 제출 시 review_agent=1 파라미터가 공용 typeset.html과 동일.
    수동 FormData 경로(convert_to_vertical/passage_remove/수능특강 다중 강)는
    JS에서 플래그를 명시 전파한다.
(2) 결과 카드: 렌더(판정 그룹 + 재조판 버튼)는 공용
    static/js/review_agent_ui.js — typeset.js는 위임하고, 인라인 폴링
    템플릿(result_session.js 그룹)은 showResultCard 말미에서
    ReviewAgentUI.append를 호출한다. 수능특강 다중 강 경로는 강별 결과
    fetch 후 append.

라우트 추가 없음(url_map 파리티 무영향) — 정적 파일과 템플릿만 검사한다.
"""
import io
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "templates")
PARTIAL_PATH = os.path.join(TEMPLATES_DIR, "_review_agent_opt.html")
RA_UI_PATH = os.path.join(ROOT, "static", "js", "review_agent_ui.js")
TYPESET_JS_PATH = os.path.join(ROOT, "static", "js", "typeset.js")

# 수동 FormData로 /api/run에 POST하는 템플릿 — 폼 직렬화를 안 쓰므로
# JS에서 review_agent 플래그를 명시 append해야 한다.
MANUAL_FORMDATA = {
    "typeset_convert_to_vertical.html",
    "typeset_passage_remove.html",
    "typeset_suneungteukgang_workbook.html",
    "typeset_suneungteukgang_workbook_v2.html",
}


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _typeset_templates():
    return sorted(
        n for n in os.listdir(TEMPLATES_DIR)
        if n.startswith("typeset") and n.endswith(".html"))


# ── 공용 partial / 공용 렌더 JS 계약 ─────────────────────────────────────

def test_partial_exists_with_form_contract():
    assert os.path.exists(PARTIAL_PATH), "templates/_review_agent_opt.html 누락"
    src = _read(PARTIAL_PATH)
    # 서버 계약: routes/typeset.py는 review_agent == "1"만 인정한다.
    assert 'name="review_agent"' in src
    assert 'value="1"' in src
    assert 'type="checkbox"' in src


def test_ra_ui_js_exists_with_render_contract():
    assert os.path.exists(RA_UI_PATH), "static/js/review_agent_ui.js 누락"
    src = _read(RA_UI_PATH)
    # 판정 3그룹 + 재조판 버튼 + 전역 노출
    for token in ("auto_fixable", "manuscript_error", "operator_judgment",
                  "rerun-btn", "/api/rerun/", "window.ReviewAgentUI",
                  "window.rerunJob"):
        assert token in src, "review_agent_ui.js 핵심 요소 누락: %s" % token


def test_typeset_js_delegates_to_shared_renderer():
    """typeset.js는 자체 사본 대신 공용 렌더를 쓴다 (이중 구현 금지)."""
    src = _read(TYPESET_JS_PATH)
    assert "ReviewAgentUI.html(jobId, result.review_agent)" in src
    assert "_reviewAgentHtml" not in src.replace(
        "// W41 후속: 렌더(_reviewAgentHtml)와 재조판(rerunJob)은 공용", ""), \
        "typeset.js에 구 렌더 사본 잔존"


# ── 템플릿 전수: 체크박스 include + 렌더 연결 ────────────────────────────

@pytest.mark.parametrize("name", _typeset_templates())
def test_template_includes_review_agent_checkbox(name):
    src = _read(os.path.join(TEMPLATES_DIR, name))
    assert '_review_agent_opt.html' in src, \
        "%s: 검수 에이전트 체크박스 partial include 누락" % name
    # partial 외 중복 마크업 금지 (include 단일화)
    assert 'name="review_agent"' not in src or name in MANUAL_FORMDATA, \
        "%s: partial 외 review_agent 마크업/참조 잔존" % name


@pytest.mark.parametrize("name", _typeset_templates())
def test_template_loads_shared_renderer(name):
    src = _read(os.path.join(TEMPLATES_DIR, name))
    assert "js/review_agent_ui.js" in src, \
        "%s: review_agent_ui.js include 누락" % name


@pytest.mark.parametrize("name", _typeset_templates())
def test_inline_polling_template_appends_ra_card(name):
    """자체 showResultCard/결과 fetch 사본을 가진 템플릿은 RA 카드를 붙인다."""
    src = _read(os.path.join(TEMPLATES_DIR, name))
    if "js/result_session.js" in src or "suneungteukgang" in name:
        assert "ReviewAgentUI.append" in src, \
            "%s: 결과 카드에 AI 검수 카드 연결(ReviewAgentUI.append) 누락" % name


@pytest.mark.parametrize("name", sorted(MANUAL_FORMDATA))
def test_manual_formdata_propagates_flag(name):
    src = _read(os.path.join(TEMPLATES_DIR, name))
    assert "append('review_agent', '1')" in src, \
        "%s: 수동 FormData 경로에 review_agent 플래그 전파 누락" % name
