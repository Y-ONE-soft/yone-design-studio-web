"""Vivliostyle 책 엔진 (3계층) — 오프라인 검사.

CLI 를 돌리지 않는다(E2E 조판 대조는 별도 실측). 여기서 잡는 것은 **계약**이다:
계층 경계, config 해석, 2패스 CSS 의 명시도, 도련·TrimBox 계산, 검수 게이트의
판정 방향.
"""
import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


# ── 계층 경계 ───────────────────────────────────────────────────────────
def test_series_registry_has_both_series():
    from core.render_vivlio import series
    assert set(series.names()) >= {"vocabook", "blackbook"}
    for name in ("vocabook", "blackbook"):
        s = series.get(name)
        assert s.name == name and s.display


def test_series_implements_hooks():
    """계열은 네 훅만 채운다 — 조판 실행·마감·공용 검수는 백엔드 소관."""
    from core.render_vivlio import series
    from core.render_vivlio.series.base import Series
    for name in series.names():
        s = series.get(name)
        assert isinstance(s, Series)
        for hook in ("gen_data", "build", "verify"):
            assert getattr(type(s), hook) is not getattr(Series, hook), \
                f"{name}.{hook} 미구현"


def test_cli_single_source():
    """CLI 경로는 cli.py 한 곳 — build.py 는 별칭만 재수출한다."""
    from core.render_vivlio import build, cli
    assert build.VivliostyleUnavailable is cli.VivliostyleUnavailable
    assert build.cli_available() == cli.cli_available()


def test_repo_owns_npm():
    """`npm ci` 대상이 리포 안에 있어야 한다(파일럿에 빌붙지 않는다)."""
    pkg = os.path.join(REPO, "core", "render_vivlio", "package.json")
    assert os.path.isfile(pkg)
    d = json.load(open(pkg, encoding="utf-8"))
    assert d["dependencies"]["@vivliostyle/cli"]
    assert os.path.isfile(os.path.join(REPO, "core", "render_vivlio",
                                       "package-lock.json"))


# ── ③ config ───────────────────────────────────────────────────────────
@pytest.fixture()
def cfg(tmp_path):
    from core.render_vivlio import config
    (tmp_path / "config.json").write_text(json.dumps({
        "series": "vocabook",
        "book": {"title": "테스트북"},
        "page": {"width": 148, "height": 210, "bleed": 3},
        "output": {"dir": "out", "stem": "테스트_내지"},
        "manuscript": {"dir": "원고", "files": {"part1": "a.xlsx"}},
        "finish": {"suffix": "_최종",
                   "append": [{"pdf": "간지/뒤.pdf", "page": 0}]},
    }, ensure_ascii=False), encoding="utf-8")
    return config.load(str(tmp_path))


def test_config_page_adds_bleed(cfg):
    p = cfg.page
    assert (p["media_w"], p["media_h"]) == (154, 216)


def test_config_paths_are_book_relative(cfg):
    assert cfg.manuscript("part1").endswith(
        os.path.join("원고", "a.xlsx"))
    assert os.path.isabs(cfg.manuscript("part1"))
    assert cfg.out_pdf("_최종").endswith(
        os.path.join("out", "테스트_내지_최종.pdf"))


def test_config_finish_resolves_paths_and_defaults_trim(cfg):
    spec = cfg.finish_spec()
    assert os.path.isabs(spec["append"][0]["pdf"])
    assert spec["trim"] == {"bleed": 3}       # page.bleed 에서 기본값


def test_config_requires_series(tmp_path):
    from core.render_vivlio import config
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        config.load(str(tmp_path))


# ── 2패스 면 지정 ──────────────────────────────────────────────────────
def test_nth_rule_names_pages_for_specificity():
    """`@page :nth(N)` 은 이름 규칙에 명시도로 밀린다 → 이름과 함께 나와야 한다."""
    from core.render_vivlio import paged
    r = paged.nth_rule(["p-head", "p-wb"], 12, "background: none;")
    assert "p-head:nth(12)" in r and "p-wb:nth(12)" in r
    assert not r.startswith("@page :nth(")


def test_right_start_indices():
    from core.render_vivlio import paged
    # 4(왼) 7(오) 10(왼) 13(오) → 2번째·4번째 시작면이 오른쪽
    assert paged.right_start_indices([4, 7, 10, 13]) == [2, 4]


def test_page_rules_text_has_generated_header(tmp_path):
    from core.render_vivlio import paged
    p = paged.PageRules(["p-a"]).nth(3, "background: none;").write(
        str(tmp_path / "pages.css"))
    text = open(p, encoding="utf-8").read()
    assert "자동 생성" in text and "p-a:nth(3)" in text


# ── 계열 테마 생성 ─────────────────────────────────────────────────────
def _vocabook_cfg():
    from core.render_vivlio import config
    book = os.path.join(config._studio_root(), "조판", "교재", "단어장",
                        "상일보카", "26-2-중간")
    if not os.path.isfile(os.path.join(book, "config.json")):
        pytest.skip("상일보카 config 없음(다른 기계)")
    return config.load(book)


def test_theme_is_deterministic_and_bakes_palette():
    """색은 배경 SVG 안에 **구워진다** → 팔레트를 바꾸면 CSS 도 반드시 바뀐다."""
    from core.render_vivlio.series.vocabook import theme
    cfg = _vocabook_cfg()
    a = theme.build_css(cfg)
    assert a == theme.build_css(cfg)            # 결정적
    assert "@PRELUDE@" not in a and "@GENERATED@" not in a
    main = cfg.section("palette")["sections"]["s-head"]["main"]
    assert main.replace("#", "%23") in a        # SVG 에 구워짐

    cfg.data["palette"]["sections"]["s-head"]["main"] = "#123456"
    b = theme.build_css(cfg)
    assert "%23123456" in b and b != a


def test_theme_emits_band2_comment_for_second_pass():
    """② 오른쪽 면 밴드는 2패스가 주석에서 꺼내 페이지 배경으로 깐다."""
    import re
    from core.render_vivlio.series.vocabook import theme
    from core.render_vivlio.series.vocabook import RE_BAND2 as _  # noqa: F401
    css = theme.build_css(_vocabook_cfg())
    from core.render_vivlio.series.vocabook import _RE_BAND2
    found = dict(_RE_BAND2.findall(css))
    assert set(found) == {"p-head", "p-deriv", "p-mw", "p-vs", "p-wb", "p-ans"}
    assert all(v.startswith("url(") for v in found.values())


# ── 도련 / TrimBox ─────────────────────────────────────────────────────
def test_trimbox_is_mediabox_relative(tmp_path):
    """MediaBox 원점이 0 이 아니어도 재단선은 사방 3mm 여야 한다."""
    fitz = pytest.importorskip("fitz")
    from core.render_vivlio import bleed, probe
    doc = fitz.open()
    doc.new_page(width=154 * probe.PT, height=216 * probe.PT)
    p = str(tmp_path / "a.pdf")
    doc.save(p)
    doc.close()
    with probe.open_pdf(p) as d:
        bleed.stamp_trimbox(d, bleed=3.0)
        mb, _cb, tb = probe.boxes(d[0])
        assert abs(tb[0] - (mb[0] + 3)) < .01
        assert abs(tb[2] - (mb[2] - 3)) < .01


def test_finish_never_leaves_half_written_target(tmp_path, monkeypatch):
    """저장이 끊겨도 **납품본이 반쪽으로 덮이지 않는다**(클라우드 경로 대응)."""
    fitz = pytest.importorskip("fitz")
    from core.render_vivlio import bleed
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(src))
    doc.close()
    target = tmp_path / "in_최종.pdf"
    target.write_bytes(b"OLD")

    def boom(self, *a, **k):
        raise OSError("Operation timed out")
    monkeypatch.setattr(fitz.Document, "save", boom)
    with pytest.raises(OSError):
        bleed.finish(str(src), {"suffix": "_최종", "trim": {"bleed": 3}})
    assert target.read_bytes() == b"OLD"
    assert not (tmp_path / "in_최종.pdf.tmp").exists()


# ── 검수 게이트 ────────────────────────────────────────────────────────
def test_sequence_gate_separates_missing_from_disorder():
    from core.render_vivlio import verify
    texts = ["가나", "다라"]
    r = verify.Report()
    missing, disorder = verify.check_sequence(
        texts, [("A", "가나"), ("B", "다라")], r)
    assert not missing and not disorder and r.ok

    r2 = verify.Report()
    missing, disorder = verify.check_sequence(
        texts, [("B", "다라"), ("A", "가나"), ("C", "없는말")], r2)
    assert disorder == ["A"] and missing == ["C"] and not r2.ok


def test_gap_gate_counts_both_underline_and_space_blanks():
    from core.render_vivlio import verify
    assert verify.count_gaps("a____b") == 1
    assert verify.count_gaps("a   b") == 1
    assert verify.count_gaps("a__b") == 0


def test_report_ok_flips_on_failure():
    from core.render_vivlio import verify
    r = verify.Report("t")
    assert r.ok
    r.note("메모")
    assert r.ok
    r.fail("결함")
    assert not r.ok


# ── 책 발견 ────────────────────────────────────────────────────────────
def test_discover_finds_config_books():
    from core.render_vivlio import book
    books = book.discover()
    if not books:
        pytest.skip("교재 트리 없음(다른 기계)")
    assert all(c.series for c in books)
    assert {c.series for c in books} <= set(
        __import__("core.render_vivlio.series", fromlist=["x"]).names())
