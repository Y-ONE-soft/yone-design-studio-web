"""라우트 파리티 가드 (C2-9) — 블루프린트 분리 전후 url_map 100% 동일 검증.

tests/fixtures/url_map_baseline.json은 분리 *전* app.py(모놀리스)의 url_map을
덤프한 픽스처다 (rule + methods + view 함수명 + 시그니처). 분리 후 endpoint
이름은 블루프린트 접두("auth.login_page" 등)로 바뀌는 게 정상이므로,
비교 기준은 rule + methods (+ view 함수 실체)다.

새 라우트를 의도적으로 추가/삭제했다면 픽스처를 재생성할 것:
    YONE_SECRET_KEY=dump python3 -c "위 덤프 스크립트"  (커밋 메시지에 사유 명시)
"""
import inspect
import json
import os

os.environ.setdefault("YONE_SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                        "url_map_baseline.json")


def _load_baseline():
    with open(_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _current_rules():
    rows = []
    for r in app_module.app.url_map.iter_rules():
        view = app_module.app.view_functions[r.endpoint]
        rows.append({
            "rule": r.rule,
            "methods": sorted(r.methods - {"HEAD", "OPTIONS"}),
            "endpoint_func": view.__name__,
            "signature": str(inspect.signature(view)),
        })
    return rows


def test_rule_method_set_identical():
    """rule + methods 집합이 분리 전과 100% 동일해야 한다."""
    expected = {(r["rule"], tuple(r["methods"])) for r in _load_baseline()}
    actual = {(r["rule"], tuple(r["methods"])) for r in _current_rules()}
    missing = expected - actual
    added = actual - expected
    assert not missing and not added, (
        f"라우트 파리티 깨짐 — 사라진 라우트: {sorted(missing)}, "
        f"새로 생긴 라우트: {sorted(added)}")


def test_route_count_identical():
    assert len(_current_rules()) == len(_load_baseline())


def test_view_functions_and_signatures_identical():
    """각 rule+methods의 view 함수명/시그니처가 분리 전과 동일해야 한다
    (endpoint 이름의 블루프린트 접두만 바뀌고 함수 실체는 그대로)."""
    expected = {(r["rule"], tuple(r["methods"])): (r["endpoint_func"], r["signature"])
                for r in _load_baseline()}
    for r in _current_rules():
        key = (r["rule"], tuple(r["methods"]))
        assert key in expected, f"픽스처에 없는 라우트: {key}"
        assert (r["endpoint_func"], r["signature"]) == expected[key], (
            f"{key}: view 함수 불일치 — "
            f"expected {expected[key]}, got {(r['endpoint_func'], r['signature'])}")


def test_key_config_preserved():
    """분리 과정에서 보존 필수인 앱 설정."""
    cfg = app_module.app.config
    assert cfg["MAX_CONTENT_LENGTH"] == 1024 * 1024 * 1024
    assert cfg["MAX_FORM_MEMORY_SIZE"] == 64 * 1024 * 1024
    assert cfg["MAX_FORM_PARTS"] == 10000
    assert cfg["SESSION_PERMANENT"] is False
    assert cfg["TEMPLATES_AUTO_RELOAD"] is True
    # Jinja 로더는 EDEADLK-retry 로더여야 함
    from core.webdata import RetryingFileSystemLoader
    assert isinstance(app_module.app.jinja_loader, RetryingFileSystemLoader)


def test_global_hooks_registered():
    """auth의 인증 훅(before)과 보안 헤더 훅(after)이 앱 전역으로 등록됐는지."""
    before = [f.__name__ for f in app_module.app.before_request_funcs.get(None, [])]
    after = [f.__name__ for f in app_module.app.after_request_funcs.get(None, [])]
    assert "check_auth" in before
    assert "add_no_cache" in after
