# -*- coding: utf-8 -*-
"""인라인 /api/result 폴링 템플릿의 세션 만료(401) 처리 계약 (W30-후속).

1c55e6e가 공용 static/js/typeset.js의 fetchResult에 401(세션 12h 절대 만료)
명시 처리를 넣었지만, 자체 fetchResult 사본을 인라인으로 가진 템플릿 19곳은
같은 오분류(게이트 경고·결과 미전달)가 잠복해 있었다. 이 파일은 그 이식이
전수 유지됨을 정적으로 가드한다:

- 공용 헬퍼 static/js/result_session.js 존재 + 핵심 요소(401/404 분기,
  typeset.js와 동일한 localStorage 키/복원 한도, /login 링크).
- /api/result를 인라인으로 fetch하는 모든 템플릿은 401 처리 경로를 가진다
  (그룹 A: ResultSession.handle + 헬퍼 include / 그룹 B(수능특강):
  r.status === 401 분기 + typeset.js showSessionExpiredCard 재사용).
- 향후 새 템플릿이 /api/result 인라인 폴링을 무가드로 추가하면 즉시 실패.

라우트 추가 없음(url_map 파리티 무영향) — 정적 파일과 템플릿만 검사한다.
"""
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "templates")
HELPER_PATH = os.path.join(ROOT, "static", "js", "result_session.js")
TYPESET_JS_PATH = os.path.join(ROOT, "static", "js", "typeset.js")

# 수능특강 v1/v2 — typeset.js를 함께 로드하므로 헬퍼 대신 typeset.js의
# showSessionExpiredCard + 복원 IIFE를 재사용한다 (이중 복원 방지).
TYPESET_JS_DELEGATED = {
    "typeset_suneungteukgang_workbook.html",
    "typeset_suneungteukgang_workbook_v2.html",
}


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _inline_polling_templates():
    """/api/result를 인라인 스크립트로 fetch하는 템플릿 전수."""
    found = []
    for name in sorted(os.listdir(TEMPLATES_DIR)):
        if not name.endswith(".html"):
            continue
        if "api/result" in _read(os.path.join(TEMPLATES_DIR, name)):
            found.append(name)
    return found


# ── 공용 헬퍼 계약 ────────────────────────────────────────────────────────

def test_helper_exists_with_core_contract():
    assert os.path.exists(HELPER_PATH), "static/js/result_session.js 누락"
    src = _read(HELPER_PATH)
    assert "res.status === 401" in src, "401 명시 분기 누락"
    assert "res.status === 404" in src, "404(job 소멸) 분기 누락"
    assert "'/login'" in src or '"/login"' in src, "재로그인 링크 누락"
    assert "24 * 3600 * 1000" in src, "복원 24h 한도 누락"
    assert "window.ResultSession" in src


def test_helper_shares_localstorage_schema_with_typeset_js():
    """복원 키·스키마가 typeset.js와 동일해야 페이지 간 간섭 없이 공존한다."""
    helper = _read(HELPER_PATH)
    typeset = _read(TYPESET_JS_PATH)
    assert "'ts_pending_result'" in helper
    assert "'ts_pending_result'" in typeset
    for field in ("jobId:", "path:", "ts:"):
        assert field in helper, "pending 스키마 필드 누락: %s" % field
        assert field in typeset


def test_helper_resume_yields_to_typeset_js():
    """typeset.js가 로드된 페이지에서는 헬퍼 복원이 양보해야 이중 발화가 없다."""
    src = _read(HELPER_PATH)
    assert "window._savePendingResult" in src, \
        "typeset.js 공존 가드(_savePendingResult 감지) 누락"


# ── 템플릿 전수: 무가드 /api/result 인라인 폴링 금지 ─────────────────────

def test_inventory_matches_known_set():
    """전수 목록이 변하면(추가/제거) 이 테스트가 알린다 — 새 템플릿이
    무가드로 폴링을 추가하는 것을 아래 401 테스트와 함께 이중 가드."""
    names = _inline_polling_templates()
    assert len(names) == 20, "인라인 /api/result 폴링 템플릿 수 변동: %r" % names


@pytest.mark.parametrize("name", _inline_polling_templates())
def test_template_handles_session_expiry_401(name):
    src = _read(os.path.join(TEMPLATES_DIR, name))
    if name in TYPESET_JS_DELEGATED:
        assert "r.status === 401" in src, "%s: [DONE] 결과 fetch 401 분기 누락" % name
        assert "showSessionExpiredCard" in src, \
            "%s: 세션 만료 카드(typeset.js 재사용) 누락" % name
        assert "js/typeset.js" in src, "%s: typeset.js include 전제 깨짐" % name
        # merge POST 401도 침묵 금지 — [통합 실패]로 가시화
        assert "mResp.status === 401" in src, "%s: merge 401 침묵 가드 누락" % name
    else:
        assert "ResultSession.handle(res, jobId, showErrorCard)" in src, \
            "%s: 401/404 공용 처리(ResultSession.handle) 누락" % name
        assert "ResultSession.clear()" in src, \
            "%s: 정상 전달 시 pending 정리 누락" % name
        assert re.search(r"js/result_session\.js", src), \
            "%s: result_session.js include 누락" % name
        # 헬퍼가 fetch 직후·json 파싱 전에 개입해야 401 본문 오분류가 없다.
        m = re.search(
            r"fetch\((?:`/api/result/\$\{jobId\}`|'/api/result/' \+ jobId)\);\n"
            r"\s*if \(window\.ResultSession && ResultSession\.handle", src)
        assert m, "%s: handle 호출이 fetch 직후에 있지 않음" % name
