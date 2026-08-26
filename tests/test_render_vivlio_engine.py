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
def test_series_registry_has_all_series():
    from core.render_vivlio import series
    assert set(series.names()) >= {"vocabook", "vocaunit", "blackbook"}
    for name in ("vocabook", "vocaunit", "blackbook"):
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
    assert "/*@PRELUDE@*/" not in a and "/*@GENERATED@*/" not in a
    main = cfg.section("palette")["sections"]["s-head"]["main"]
    assert main.replace("#", "%23") in a        # SVG 에 구워짐

    cfg.data["palette"]["sections"]["s-head"]["main"] = "#123456"
    b = theme.build_css(cfg)
    assert "%23123456" in b and b != a


def test_theme_emits_band2_comment_for_second_pass():
    """② 오른쪽 면 밴드는 2패스가 주석에서 꺼내 페이지 배경으로 깐다."""
    from core.render_vivlio.series.vocabook import _RE_BAND2, theme
    css = theme.build_css(_vocabook_cfg())
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


# ── 계열 vocaunit (광문보카) ─────────────────────────────────────────────
@pytest.fixture()
def unit_cfg(tmp_path):
    from core.render_vivlio import config
    (tmp_path / "config.json").write_text(json.dumps({
        "series": "vocaunit",
        "book": {"title": "광문보카", "brand": "GWANGMUN VOCA"},
        "page": {"width": 148, "height": 210, "bleed": 3},
        "palette": {"ink": "#231f20", "accent": "#6f7dbd", "pron": "#939598",
                    "pos": "#6d6e71", "hl": "#f68b62", "rule": "#cbcee8",
                    "chk": "#d9cbde", "band": "#d9cbde", "rule2": "#c7b9db",
                    "logo": "#c7b9db", "crest": "#cbcee8", "tab": "#a0b0d7",
                    "circle": "#cab6d4", "unitnum": "#8094cb", "grid": "#d2d2d2",
                    "cover_bg": "#f4f0f6", "cover_mark": "#ffffff"},
        "fonts": [], "options": {}, "metrics": {},
    }, ensure_ascii=False), encoding="utf-8")
    return config.load(str(tmp_path))


def test_vocaunit_parses_manuscript_by_structure():
    """블록 인식은 '번호 행'이 앵커 — 마커 문구('DAY15 / 회독')에 기대지 않는다."""
    from core.render_vivlio.series.vocaunit import data
    rows = [("", "아무말", "무엇이든", ""),
            ("", "1", "sensible", "[형] 분별력 있는 (↔ senseless 어리석은)"),
            ("", "", "[ˈsɛnsəbəl]", ""),
            ("", "", "sensibility [명] 감수성", "It wasn't [sensible] to go out."),
            ("", "", "", "밖에 나간 것은 [현명하지] 않았다."),
            ("", "", "", "")]
    blocks = data.parse_unit(rows, "Unit 15")
    assert len(blocks) == 1
    b = blocks[0]
    assert b["word"] == "sensible" and b["pron"] == "[ˈsɛnsəbəl]"
    assert b["deriv"] == ["sensibility [명] 감수성"]
    assert b["pairs"] == [["It wasn't [sensible] to go out.",
                           "밖에 나간 것은 [현명하지] 않았다."]]


def test_vocaunit_keeps_derivative_without_pos():
    """품사 대괄호는 파생어를 **자르는 경계**일 뿐 조건이 아니다.
    (`legally 법률적으로` 가 조용히 사라졌던 자리 — 마커 행만 구조로 거른다.)"""
    from core.render_vivlio.series.vocaunit import data
    rows = [("", "DAY17", "회독", ""),
            ("", "17", "legal", "[형] 법적인"),
            ("", "", "[ˈligəl]", ""),
            ("", "", "legally 법률적으로", "He needed [legal] advice."),
            ("", "", "", "")]
    b = data.parse_unit(rows, "Unit 17")[0]
    assert b["deriv"] == ["legally 법률적으로"]
    assert b["pairs"] == [["He needed [legal] advice.", ""]]


def test_vocaunit_reads_flat_manuscript_by_column_role():
    """표형 원고는 열 **이름**이 아니라 값의 성질로 역할을 가른다."""
    from core.render_vivlio.series.vocaunit import data
    rows = [("No", "word", "단원", "meaning", "예문"),
            ("1", "lease", "Unit 01 - Analysis", "임대 계약",
             "With our lease coming to an end."),
            ("2", "location", "Unit 01 - Analysis", "장소, 위치",
             "We wanted a location with more space."),
            ("3", "community", "Unit 01 - Analysis", "지역 사회",
             "We wanted a location with more space."),
            ("4", "valued", "Unit 01 - 1번", "소중한", "Dear valued players,")]
    assert data.is_flat(rows)
    units = data.parse_flat(rows, "전체", log=lambda *_: None)
    assert len(units) == 1 and units[0]["head"] == "Unit 01"
    g = units[0]["groups"]
    assert [x["label"] for x in g] == ["Analysis", "1번"]
    # 같은 예문이 이어지는 낱말은 **한 묶음** — 예문을 되풀이하지 않는다
    assert [[w["word"] for w in r["words"]] for r in g[0]["runs"]] == \
        [["lease"], ["location", "community"]]
    assert len(units[0]["words"]) == 4


def test_vocaunit_part_palettes_keep_tone_and_rotate_hue():
    """대단원 색은 **색상만** 돈다 — 밝기와 최대채도 대비는 그대로다."""
    from core.render_vivlio import color
    base = "#d06397"
    L0, C0, H0 = color.hex2oklch(base)
    for hue in (318, 288, 258):
        L, C, H = color.hex2oklch(color.rotate(base, hue))
        assert abs(L - L0) < 0.01
        assert abs(C / color.max_c(L, H) - C0 / color.max_c(L0, H0)) < 0.02
        assert abs(((H - hue + 180) % 360) - 180) < 1.0


def test_vocaunit_highlights_run_words_longest_first():
    """묶음 예문 강조 — 겹치면 긴 쪽을 남긴다(`ticket office` vs `office`)."""
    from core.render_vivlio.series.vocaunit import render
    got = render.highlight("The station had ticket offices with staff.",
                           ["ticket office", "station"])
    assert "<em>station</em>" in got and "<em>ticket offices</em>" in got


def test_vocaunit_splits_run_on_derivatives():
    """파생어 칸은 여러 개가 이어 붙어 온다 — `영단어 + [품사]` 가 경계."""
    from core.render_vivlio.series.vocaunit import data
    got = data.split_deriv(
        "sensitivity [명] 1. 민감함; (예술적) 감수성 sensibility [명] 감정")
    assert got == ["sensitivity [명] 1. 민감함; (예술적) 감수성",
                   "sensibility [명] 감정"]
    # 한 파생어 안의 두 번째 품사는 자르지 않는다(앞이 영단어가 아니다)
    assert data.split_deriv("finance [명] 재정, 재무 [동] 자금을 대다") == \
        ["finance [명] 재정, 재무 [동] 자금을 대다"]


def test_vocaunit_gate_stops_on_missing_pieces():
    """인식 게이트 — 기대 수량/구조가 어긋나면 조판하지 않고 중단."""
    from core.render_vivlio.series.vocaunit import data
    d = {"units": [{"sheet": "Unit 15", "words": [
        {"no": 1, "word": "x", "meaning": "[형] 뜻", "pron": "", "pairs": [1]}]}],
        "counts": {"units": 1, "words": 1}}
    with pytest.raises(SystemExit):
        data.gate(d, {"expect": {"units": 1, "words": 1}}, lambda *_: None)


def test_vocaunit_meaning_marks_pos_sense_and_notes():
    """뜻 표기 변환 — 품사 배지 · 줄바꿈 · 1. → ① · (= …) 와 (한글만) 은 작은 글자."""
    from core.render_vivlio.series.vocaunit import render
    html = render.meaning("[형] 1. 민감한 (↔ insensitive 둔감한) 2. (과실의) 섬세한")
    assert html.count("<p>") == 1                      # 품사 하나 → 한 줄
    assert '<b class="pos">형</b>' in html
    assert '<span class="n">①</span>' in html and '<span class="n">②</span>' in html
    assert '<span class="note">(↔ insensitive 둔감한)</span>' in html
    assert '<span class="q">(과실의)</span>' in html
    assert render.meaning("[명] 뜻 [동] 뜻").count("<p>") == 2


def test_vocaunit_theme_bakes_palette_and_keeps_page_names(unit_cfg):
    """팔레트는 배경 SVG 안에 구워진다 → 색을 바꾸면 테마를 다시 만들어야 한다."""
    from core.render_vivlio.series.vocaunit import theme
    css = theme.build_css(unit_cfg)
    assert "%23cab6d4" in css            # ① 큰 원
    assert "%23a0b0d7" in css            # ③ 탭
    assert "--c-cover-mark: #ffffff;" in css   # config 의 밑줄 → CSS 하이픈
    assert "@page p-body" in css and "@page p-memo" in css
    # 도련은 옮기는 게 아니라 늘리는 것 — 여백에 도련이 더해져 있다
    assert "margin: 23.09mm 21.0mm 20.0mm 18.0mm;" in css


def test_vocaunit_second_pass_names_pages_and_lowers_open_margin(unit_cfg,
                                                                 tmp_path):
    """②(모눈 헤더 면)는 배경뿐 아니라 상단 여백도 내려간다 — 이름과 함께 지정."""
    from core.render_vivlio.series.vocaunit import VocaunitSeries
    out = tmp_path / "pages.css"
    VocaunitSeries._write_pages_css(unit_cfg, [2, 8], [""] * 20, str(out))
    css = out.read_text(encoding="utf-8")
    assert "@page p-body:nth(2)" in css and "@page p-body:nth(3)" in css
    assert "margin-top: 28.09mm" in css
    assert "@top-left { content: none; }" in css


def test_vocaunit_pos_is_badge_glyph_not_brackets():
    """품사는 대괄호가 아니라 네모 배지 — 마크업에 `[` `]` 가 남으면 안 된다."""
    from core.render_vivlio.series.vocaunit import render
    html = render.meaning("[형] 분별력 있는")
    assert '<b class="pos">형</b>' in html and "[형]" not in html
    assert '<b class="pos">명</b>' in render.deriv("sensibility [명] 감수성")


def test_vocaunit_badge_stops_inherited_text_indent():
    """⚠ text-indent 는 inline-block 안까지 상속된다 — 배지에서 끊어야 글자가
    상자 안에 남는다(안 끊으면 뜻 문단의 내어쓰기만큼 글자가 밖으로 밀린다)."""
    import os
    css = open(os.path.join(REPO, "core", "render_vivlio", "themes",
                            "vocaunit.css"), encoding="utf-8").read()
    badge = css[css.index("\nb.pos {"):]     # `.w-deriv b.pos` 가 아니라 본 규칙
    badge = badge[:badge.index("}")]
    assert "text-indent: 0" in badge


def test_vocaunit_retints_asset_pngs_from_palette(unit_cfg, tmp_path):
    """자산 PNG 는 색이 파일에 박혀 있다 → 팔레트를 바꾸면 다시 구워야 한다."""
    pytest.importorskip("PIL")
    pytest.importorskip("numpy")
    import numpy as np
    from PIL import Image
    from core.render_vivlio.series.vocaunit import assets

    src = tmp_path / "src"
    src.mkdir()
    base = (0xc7, 0xb9, 0xdb)
    a = np.zeros((4, 4, 4), dtype=np.uint8)
    a[..., :3] = base
    a[0, 0, :3] = 255                    # 흰 글자 한 점
    a[..., 3] = 255
    a[3, 3, 3] = 0                       # 투명 한 점
    Image.fromarray(a).save(src / "pill2026.png")

    build = tmp_path / "build"
    assets.retint(unit_cfg, str(build), str(src))
    got = np.asarray(Image.open(build / "assets" / "pill2026.png").convert("RGBA"))
    assert tuple(got[1, 1, :3]) == (0xc7, 0xb9, 0xdb)   # 픽스처 팔레트의 logo 색
    assert tuple(got[0, 0, :3]) == (255, 255, 255)      # 흰 글자는 그대로
    assert got[3, 3, 3] == 0                            # 알파 보존


def test_vocaunit_drops_synonym_notes_including_nested_parens():
    """`(= …)` `(↔ …)` 빼기 — ⚠ 주석 안에 괄호가 또 들어온다(`(= judg(e)ment)`).
    `\\([^()]*\\)` 류 정규식은 이 셋을 조용히 남긴다."""
    from core.render_vivlio.series.vocaunit import render
    cases = [
        ("[형] 사려 깊은, 이해심이 있는 (= thoughtful)(↔ inconsiderate 사려 깊지 못한)",
         "[형] 사려 깊은, 이해심이 있는"),
        ("succession [명] 1. 연속, 잇따름 (= series); 연쇄 2. 계승(권)",
         "succession [명] 1. 연속, 잇따름; 연쇄 2. 계승(권)"),
        ("[명] 1. 문장 2. 선고, 판결 (= judg(e)ment) [동] 선고하다",
         "[명] 1. 문장 2. 선고, 판결 [동] 선고하다"),
        ("miraculous [형] 기적적인 (= marvel(l)ous)", "miraculous [형] 기적적인"),
    ]
    for src, want in cases:
        got = render.drop_notes(src)
        assert got == want, f"{src!r} → {got!r} (기대 {want!r})"
        assert not render.has_note(got)
    # 기본값은 남긴다(작은 글자) — 빼는 것은 책이 고르는 것
    assert "thoughtful" in render.meaning("[형] 깊은 (= thoughtful)")
    assert "thoughtful" not in render.meaning("[형] 깊은 (= thoughtful)", notes="drop")


def test_vocaunit_badge_is_outline_not_filled():
    """품사 배지는 라인형 — 바탕을 채우지 않고 테두리로 그린다."""
    import os
    css = open(os.path.join(REPO, "core", "render_vivlio", "themes",
                            "vocaunit.css"), encoding="utf-8").read()
    badge = css[css.index("\nb.pos {"):]
    badge = badge[:badge.index("}")]
    assert "border: var(--pos-line-w) solid var(--c-pos-line)" in badge
    assert "background" not in badge
    # 파생어 배지는 무채색으로, 세로 정렬은 7pt 줄에 맞춰 따로 덮어쓴다
    deriv = css[css.index(".w-deriv b.pos {"):]
    deriv = deriv[:deriv.index("}")]
    assert "color: var(--c-pos)" in deriv and "border-color: var(--c-pos)" in deriv
    assert "vertical-align: var(--pos-va-deriv)" in deriv


def test_vocaunit_uses_complement_for_content_emphasis():
    """구조는 주색, 내용 강조는 보색 — 의미 번호·강조어가 주색을 그대로 쓰면
    지면이 2도 인쇄처럼 보인다."""
    import os
    css = open(os.path.join(REPO, "core", "render_vivlio", "themes",
                            "vocaunit.css"), encoding="utf-8").read()
    assert "color: var(--c-sense)" in css      # ①②③ 는 accent 가 아니라 sense
    assert "color: var(--c-hl)" in css or "var(--c-hl)" in css


def test_vocaunit_sense_number_never_ends_a_line():
    """의미 번호는 뒤 낱말과 줄바꿈 불가 공백으로 묶는다 —
    안 묶으면 `… 연쇄 ②` 로 줄이 끊기고 다음 줄이 `계승(권)` 이 된다."""
    from core.render_vivlio.series.vocaunit import render
    html = render.meaning("[명] 1. 연속, 잇따름 2. 계승(권)")
    assert '<span class="n">①</span> 연속' in html
    assert '<span class="n">②</span> 계승' in html


def test_vocaunit_derivative_badge_eats_following_space():
    """파생어의 품사 뒤 공백은 배지가 먹는다 — 배지 자체 여백과 겹치면 벌어진다."""
    from core.render_vivlio.series.vocaunit import render
    assert render.deriv("successor [명] 후계자") == \
        'successor <b class="pos">명</b>후계자'


# ── 인쇄 원고(prepress) ─────────────────────────────────────────────────
def test_prepress_maps_neutrals_to_devicegray():
    """조판 백엔드는 무조건 DeviceRGB 로 쓴다 — 먹·회색은 K 단색이 되게 미리 바꾼다.
    그냥 ICC 로 넘기면 본문 먹이 리치블랙(C80 M80 Y77 K60)이 된다."""
    import fitz
    from core.render_vivlio import prepress
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.draw_rect(fitz.Rect(0, 0, 1, 1), color=(0, 0, 0))   # 콘텐츠 스트림 생성
    xref = page.get_contents()[0]
    doc.update_stream(xref, (
        b"0.137255 0.121569 0.12549 rg 0 0 10 10 re f\n"      # #231f20 → K100
        b"0.427451 0.431373 0.443137 RG 0 0 m 5 5 l S\n"      # #6d6e71 → K70
        b"0.811765 0.282353 0.533333 rg 0 0 5 5 re f\n"))     # 유채색 → 그대로
    n = prepress.neutralize(doc)
    out = doc.xref_stream(xref).decode("latin-1")
    assert n == 2
    assert "0 g" in out and "0.3 G" in out
    assert "0.811765 0.282353 0.533333 rg" in out    # 유채색은 건드리지 않는다
    doc.close()


def test_prepress_stamps_trim_and_bleed_boxes():
    """Ghostscript 는 TrimBox/BleedBox 를 흘려버린다 → 마지막에 다시 찍는다."""
    import fitz
    from core.render_vivlio import prepress
    doc = fitz.open()
    doc.new_page(width=154 * prepress.PT, height=216 * prepress.PT)
    prepress.stamp_boxes(doc, bleed=3.0)
    p = doc[0]
    trim = [round(v / prepress.PT, 2) for v in p.trimbox]
    bleed = [round(v / prepress.PT, 2) for v in p.bleedbox]
    assert trim == [3.0, 3.0, 151.0, 213.0]
    assert bleed == [0.0, 0.0, 154.0, 216.0]
    doc.close()


def test_vocaunit_page_closing_rule_is_drawn_once():
    """항목마다 위·아래 border 를 다 그리면 이웃과 겹쳐 굵어진다(실측 70곳).
    아래 괘선은 흐름 상자에 `box-decoration-break: clone` 으로 **면마다 한 번**."""
    import os
    css = open(os.path.join(REPO, "core", "render_vivlio", "themes",
                            "vocaunit.css"), encoding="utf-8").read()
    entry = css[css.index("\n.w {"):]
    entry = entry[:entry.index("}")]
    assert "border-top" in entry and "border-bottom" not in entry
    assert "box-decoration-break: clone" in css


def test_prepress_pins_exact_cmyk_for_matched_colors():
    """이전 판과 색을 정확히 맞춰야 하는 것은 ICC 를 태우지 않고 CMYK 로 못 박는다
    (예문 강조어 = 완성본과 같은 C0 M56 Y64 K0)."""
    import fitz
    from core.render_vivlio import prepress
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.draw_rect(fitz.Rect(0, 0, 1, 1), color=(0, 0, 0))
    xref = page.get_contents()[0]
    doc.update_stream(xref, b"0.964706 0.545098 0.384314 rg 0 0 9 9 re f\n")
    n = prepress.neutralize(doc, gray_map={},
                            cmyk_map={"#f68b62": [0, 56, 64, 0]})
    out = doc.xref_stream(xref).decode("latin-1")
    assert n == 1 and "0 0.56 0.64 0 k" in out
    doc.close()


def test_verify_flags_stale_print_pdf(tmp_path, monkeypatch):
    """인쇄 원고가 조판본보다 오래되면 결함 — 조용히 뒤처지면 옛 색으로 납품된다."""
    import os
    import time
    from core.render_vivlio import book, verify as gate
    (tmp_path / "config.json").write_text(json.dumps({
        "series": "vocaunit", "page": {"width": 148, "height": 210, "bleed": 3},
        "output": {"dir": ".", "stem": "책"},
        "print": {"out": "_인쇄"},
    }, ensure_ascii=False), encoding="utf-8")
    from core.render_vivlio import config as bookconfig
    cfg = bookconfig.load(str(tmp_path))
    src, out = tmp_path / "책.pdf", tmp_path / "책_인쇄.pdf"
    out.write_bytes(b"old")
    time.sleep(0.01)
    src.write_bytes(b"new")
    os.utime(out, (0, 0))
    rep = gate.Report()
    book._check_print_fresh(cfg, str(src), rep)
    assert rep.fails and "오래됐다" in rep.fails[0]
    os.utime(out, None)                       # 다시 최신으로
    rep2 = gate.Report()
    book._check_print_fresh(cfg, str(src), rep2)
    assert rep2.ok
