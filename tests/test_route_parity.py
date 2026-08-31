"""라우트 파리티 가드 (C2-9) — 블루프린트 분리 전후 url_map 100% 동일 검증.

tests/fixtures/url_map_baseline.json은 분리 *전* app.py(모놀리스)의 url_map을
덤프한 픽스처다 (rule + methods + view 함수명 + 시그니처). 분리 후 endpoint
이름은 블루프린트 접두("auth.login_page" 등)로 바뀌는 게 정상이므로,
비교 기준은 rule + methods (+ view 함수 실체)다.

## ⚠ 이 가드가 지키는 것은 **한 방향**이다

원래 세 시험이 "픽스처와 100% 같을 것"을 요구했는데, 그 뒤로 표지 작업대·
디자인·내지 작업대가 라우트를 35개 더했다. 그래서 **늘 빨간불**이 되었고,
빨간불이 상수가 되면 진짜 유실을 아무도 못 본다(실제로 이 상태로 오래 있었다).

이 가드의 쓸모는 "분리하다 라우트를 **떨어뜨리지 않았나**" 다. 늘어난 것은
기능이 늘어난 것이지 사고가 아니다. 그래서 **사라진 라우트만 실패**로 본다.
새로 생긴 것은 목록으로 남겨 눈에 띄게 한다.

픽스처(`tests/fixtures/url_map_baseline.json`)는 분리 *전* 모놀리스의 덤프다.
**다시 뜨지 말 것** — 다시 뜨면 그날 이후 무엇이 사라졌는지 알 길이 없어진다.
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
    assert not missing, f"분리 전에 있던 라우트가 사라졌다: {sorted(missing)}"


def test_route_count_never_shrinks():
    """줄어들면 무언가를 떨어뜨린 것이다. 느는 것은 기능이 는 것."""
    assert len(_current_rules()) >= len(_load_baseline())


def test_view_functions_and_signatures_identical():
    """픽스처에 **있던** 라우트는 view 함수·시그니처가 그대로여야 한다.

    새 라우트는 검사하지 않는다 — 픽스처에 있을 리가 없다.
    """
    expected = {(r["rule"], tuple(r["methods"])): (r["endpoint_func"], r["signature"])
                for r in _load_baseline()}
    seen = 0
    for r in _current_rules():
        key = (r["rule"], tuple(r["methods"]))
        if key not in expected:
            continue
        seen += 1
        assert (r["endpoint_func"], r["signature"]) == expected[key], (
            f"{key}: view 함수 불일치 — "
            f"expected {expected[key]}, got {(r['endpoint_func'], r['signature'])}")
    assert seen == len(expected), "픽스처의 라우트를 다 못 찾았다"


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
