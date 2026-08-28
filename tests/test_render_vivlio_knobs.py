"""손잡이 선언의 **계약** 검사 — 오프라인(교재 폴더도 PDF 도 필요 없다).

손잡이가 위험한 자리는 하나다: **선언한 기본값이 실제 기본값과 다른 것.**
그러면 사용자가 값을 바꿨다가 되돌렸을 때(=config 에서 키를 지웠을 때) 지면이
원래대로 안 돌아온다. 사람 눈으로는 절대 못 잡으므로 여기서 못박는다.

    · css 손잡이  → `themes/<계열>.css` 의 `:root` 값과 같아야 한다
    · 계열 기본값 → 계열이 들고 있는 DEFAULT_* 표와 같아야 한다
    · 손잡이가 없어도 되지만, 있으면 키·묶음·종류가 스키마를 지켜야 한다
"""
import os
import re

import pytest

from core.render_vivlio import knobs as kn
from core.render_vivlio import series as registry
from core.render_vivlio.config import BookConfig

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = os.path.join(HERE, "core", "render_vivlio", "themes")

RE_VAR = re.compile(r"^\s*(--[\w-]+)\s*:\s*([^;]+);", re.M)


def _root_vars(theme):
    """`themes/<theme>.css` 의 `:root { … }` 안 변수 표."""
    p = os.path.join(THEMES, theme + ".css")
    if not os.path.exists(p):
        return {}
    css = open(p, encoding="utf-8").read()
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    return {k: v.strip() for k, v in RE_VAR.findall(m.group(1))} if m else {}


def _series_objs():
    out = []
    for name in registry.names():
        s = registry.get(name)
        out.append((name, s() if isinstance(s, type) else s))
    return out


def _empty_cfg(series_name):
    """config 가 비어 있는 책 — 선언과 기본값만 보기 위한 것."""
    return BookConfig({"series": series_name, "page": {"width": 210,
                                                       "height": 297}},
                      os.path.join(HERE, "_nonexistent_book"))


@pytest.mark.parametrize("name,series", _series_objs())
def test_knob_schema(name, series):
    """선언이 있으면 스키마를 지켜야 한다."""
    ks = kn.of(_empty_cfg(name), series)
    keys = set()
    for k in ks:
        assert k.key and "." in k.key, f"{name}: 손잡이 키는 점 경로여야 한다 ({k.key})"
        assert k.key not in keys, f"{name}: 손잡이 키 중복 {k.key}"
        keys.add(k.key)
        assert k.kind in ("color", "mm", "pt", "number", "enum", "bool"), \
            f"{name}: 모르는 종류 {k.kind} ({k.key})"
        assert k.group in kn.GROUPS, f"{name}: 모르는 묶음 {k.group} ({k.key})"
        assert k.label, f"{name}: 라벨 없음 ({k.key})"
        if k.kind == "enum":
            assert k.values, f"{name}: enum 인데 values 가 없다 ({k.key})"


@pytest.mark.parametrize("name,series", _series_objs())
def test_css_knob_default_matches_theme(name, series):
    """**css 손잡이의 기본값 = 테마 CSS 의 `:root` 값.**

    이게 어긋나면 '되돌리기'가 원래 색으로 안 돌아간다.
    """
    theme = getattr(series, "theme", "") or ""
    root = _root_vars(theme) if theme else {}
    for k in kn.of(_empty_cfg(name), series):
        if not k.css:
            continue
        assert root, (f"{name}: css 손잡이가 있는데 themes/{theme}.css 의 "
                      f":root 를 못 읽었다")
        assert k.css in root, f"{name}: 테마에 {k.css} 가 없다 ({k.key})"
        assert k.default is not None, f"{name}: {k.key} 기본값 미선언"
        assert str(k.default).lower() == root[k.css].lower(), (
            f"{name}: {k.key} 기본값이 테마와 다르다 — "
            f"선언 {k.default} vs 테마 {root[k.css]}")


def test_blackbook_metric_defaults():
    """치수 손잡이 기본값 = 계열이 들고 있는 DEFAULT_METRICS."""
    from core.render_vivlio.series.blackbook import BlackbookSeries
    from core.render_vivlio.series.blackbook.render import DEFAULT_METRICS
    for k in kn.of(_empty_cfg("blackbook"), BlackbookSeries()):
        if not k.key.startswith("metrics."):
            continue
        name = k.key.split(".", 1)[1]
        assert name in DEFAULT_METRICS, f"모르는 치수 {name}"
        assert float(k.default) == float(DEFAULT_METRICS[name]), (
            f"{k.key} 기본값이 다르다 — 선언 {k.default} vs "
            f"DEFAULT_METRICS {DEFAULT_METRICS[name]}")


def test_css_only_emits_overrides():
    """**config 에 없는 키는 내보내지 않는다** — 손잡이를 뚫어도 지면이 안 바뀐다."""
    from core.render_vivlio.series.blackbook import BlackbookSeries
    s = BlackbookSeries()
    assert kn.css_text(_empty_cfg("blackbook"), s) == ""
    cfg = BookConfig({"series": "blackbook", "palette": {"gold": "#c0392b"}},
                     HERE)
    css = kn.css_text(cfg, s)
    assert "--gold: #c0392b" in css
    assert "--band" not in css, "덮어쓰지 않은 키가 새어 나왔다"


def test_put_get_unset():
    d = {}
    kn.put(d, "palette.gold", "#fff")
    assert kn.get(d, "palette.gold") == "#fff"
    assert kn.has(d, "palette.gold")
    kn.unset(d, "palette.gold")
    assert not kn.has(d, "palette.gold")
    assert kn.get(d, "없는.키", "기본") == "기본"


def test_apply_none_resets():
    d = {"palette": {"gold": "#000", "band": "#111"}}
    out = kn.apply(d, {"palette.gold": None, "palette.band": "#222"})
    assert not kn.has(out, "palette.gold")
    assert kn.get(out, "palette.band") == "#222"
    assert kn.get(d, "palette.gold") == "#000", "원본을 건드리면 안 된다"
