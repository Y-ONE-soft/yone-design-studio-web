"""작업대가 조판에 얹는 세 가지 — 단락 스타일 · 그림 · 자산 배치. 오프라인.

여기서 지켜야 하는 것 하나: **작업대가 계열 코드를 안 건드린다.** 스타일도
그림도 쪽 나눔도 전부 `config.styles` → `build/knobs.css` 한 길로 나가야 한다.
그 길이 막히거나 계열마다 갈라지면, 결국 다시 클로드를 불러 계열을 고치게 되고
그러면 이미 납품한 다른 책이 같이 흔들린다.
"""
import io
import json
import os

import pytest

from core.render_vivlio import knobs as kn
from core.render_vivlio import stage


# ── 단락 스타일 → CSS ───────────────────────────────────────────
class FakeCfg(object):
    def __init__(self, data, root):
        self.data = data
        self.root = root
        self.book = data.get("book", {})

    def section(self, name):
        return self.data.get(name)

    def get(self, name, default=None):
        return self.data.get(name, default)

    def path(self, name):
        return os.path.join(self.root, name)

    def resolve(self, p):
        return p if os.path.isabs(p) else os.path.join(self.root, p)


def test_styles_text_emits_rules():
    cfg = FakeCfg({"styles": {".head": {"font-size": "9.5pt",
                                        "color": "#231f20"}}}, "/tmp")
    css = kn.styles_text(cfg)
    assert ".head {" in css
    assert "font-size: 9.5pt;" in css
    assert "color: #231f20;" in css


def test_styles_text_empty_when_no_styles():
    """스타일이 없으면 규칙도 없어야 한다 — 빈 규칙 하나도 판을 흔들 수 있다."""
    assert kn.styles_text(FakeCfg({}, "/tmp")).strip() == ""


def test_styles_text_takes_ref_selectors():
    """쪽 나눔·그림은 `[data-ref=…]` 로 나간다. 대괄호·따옴표가 살아야 한다."""
    sel = '[data-ref="lessons.0.problems.3"]'
    css = kn.styles_text(FakeCfg({"styles": {sel: {"break-before": "page"}}},
                                 "/tmp"))
    assert sel + " {" in css
    assert "break-before: page;" in css


def test_styles_text_pseudo_element():
    sel = '[data-ref="a.0"]::after'
    css = kn.styles_text(FakeCfg(
        {"styles": {sel: {"content": 'url("assets/g.png")'}}}, "/tmp"))
    assert sel + " {" in css
    assert 'content: url("assets/g.png");' in css


# ── 자산 배치 ──────────────────────────────────────────────────
def test_stage_book_assets_copies(tmp_path):
    root = tmp_path / "책"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "그림.png").write_bytes(b"\x89PNG")
    build = tmp_path / "build"
    build.mkdir()
    cfg = FakeCfg({}, str(root))
    stage.stage_book_assets(cfg, str(build))
    assert (build / "assets" / "그림.png").read_bytes() == b"\x89PNG"


def test_stage_book_assets_no_folder_is_quiet(tmp_path):
    """자산 폴더가 없는 책이 대부분이다. 거기서 터지면 안 된다."""
    build = tmp_path / "build"
    build.mkdir()
    assert stage.stage_book_assets(FakeCfg({}, str(tmp_path)),
                                   str(build)) is None
    assert not (build / "assets").exists()


def test_stage_book_assets_follows_config_dir(tmp_path):
    root = tmp_path / "책"
    (root / "그림모음").mkdir(parents=True)
    (root / "그림모음" / "a.png").write_bytes(b"x")
    build = tmp_path / "build"
    build.mkdir()
    cfg = FakeCfg({"assets": {"dir": "그림모음"}}, str(root))
    stage.stage_book_assets(cfg, str(build))
    assert (build / "assets" / "a.png").exists()


# ── 모든 계열이 같은 길을 지나는가 ──────────────────────────────
SERIES = ("blackbook", "vocabook", "vocaunit", "special")


@pytest.mark.parametrize("name", SERIES)
def test_every_series_stages_knobs_and_assets(name):
    """계열마다 갈라지면 작업대가 어떤 책에서는 조용히 안 먹는다.

    실제로 특강 계열만 손잡이·overrides 를 안 얹고 있어서, 작업대에서 색을
    바꿔도 그 책만 아무 일도 안 일어났다.
    """
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "render_vivlio", "series", name, "__init__.py")
    src = io.open(p, encoding="utf-8").read()
    assert "knobs.write(" in src, f"{name}: 손잡이를 안 얹는다"
    assert "stage_overrides(" in src, f"{name}: overrides.css 를 안 얹는다"
    assert "stage_book_assets(" in src, f"{name}: 책 자산을 안 옮긴다"


@pytest.mark.parametrize("name", SERIES)
def test_every_series_links_book_css(name):
    """`knobs.css`·`overrides.css` 를 HTML 이 안 물면 얹어도 소용없다."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "render_vivlio", "series", name, "render.py")
    src = io.open(p, encoding="utf-8").read()
    assert "BOOK_CSS_LINKS" in src, f"{name}: 책 CSS 를 안 문다"


# ── 자리표 ─────────────────────────────────────────────────────
# 자리표가 없는 자리는 작업대에서 클릭해도 **조용히** 아무 일이 안 일어난다.
# 그게 가장 나쁜 실패라, 계열마다 자리표가 실제로 나오는지 못박는다.
from core.render_vivlio import refs


def test_index_paths_walks_nested_lists():
    d = {"workbook": [{"sections": [{"items": [{"t": "가"}, {"t": "나"}]}]}]}
    refs.index_paths(d, [("workbook", "sections", "items")])
    sec = d["workbook"][0]["sections"][0]
    assert refs.of(sec) == "workbook.0.sections.0"
    assert refs.of(sec["items"][1], "t") == "workbook.0.sections.0.items.1.t"


def test_index_paths_ignores_missing_branch():
    """원고에 그 절이 없는 책도 있다. 없으면 없는 대로 지나가야 한다."""
    refs.index_paths({"head": [{"w": 1}]},
                     [("head",), ("workbook", "sections", "items")])
    assert len(refs.table()) == 0        # of() 를 안 부르면 번호도 안 매긴다


def test_stamp_merges_into_existing_class():
    """class 를 두 번 쓰면 브라우저가 앞의 것만 읽어 vrefN 을 버린다."""
    refs.clear()
    out = refs.stamp('<div class="x-passage">글</div>', "volumes.0.blocks.5.r")
    assert out.count("class=") == 1
    assert 'class="x-passage vref1"' in out
    assert 'data-ref="volumes.0.blocks.5.r"' in out
    assert 'id="vref1"' in out


def test_stamp_adds_class_when_none():
    refs.clear()
    out = refs.stamp("<p>글</p>", "a.0")
    assert out.startswith('<p class="vref1"')


def test_stamp_leaves_non_tag_alone():
    refs.clear()
    assert refs.stamp("글자만", "a.0") == "글자만"
    assert refs.stamp("", "a.0") == ""
    assert refs.stamp("<p>x</p>", "") == "<p>x</p>"


def test_stamp_is_idempotent():
    """한 블록이 조각을 여럿 내면 id 가 겹친다 — 이미 찍힌 것은 건드리지 않는다."""
    refs.clear()
    once = refs.stamp('<div class="a">x</div>', "a.0")
    assert refs.stamp(once, "a.1") == once


def test_stamp_keeps_self_closing():
    refs.clear()
    assert refs.stamp("<hr/>", "a.0").endswith("/>")


@pytest.mark.parametrize("name", ("blackbook", "vocabook", "vocaunit", "special"))
def test_every_series_makes_refs(name):
    """어떤 방법으로든 자리표 표를 만들고, 번호↔경로 표를 내야 한다.

    ⚠ 만드는 **함수 이름**을 시험하지 않는다 — `index()` 에서 `index_paths()`
      로 옮기자마자 시험이 깨졌는데, 바뀐 것은 방법이지 지켜야 할 것이 아니었다.
    """
    p = os.path.join(_ROOT, "core", "render_vivlio", "series", name, "render.py")
    src = io.open(p, encoding="utf-8").read()
    assert ("_refs.index" in src or "_refs.stamp" in src), \
        f"{name}: 자리표를 안 만든다"
    assert "_refs.dump(" in src, f"{name}: 번호↔경로 표를 안 낸다"


@pytest.mark.parametrize("name", ("blackbook", "vocabook", "vocaunit", "special"))
def test_every_series_marks_its_running_head(name):
    """머리 띠·꼬리말도 지면이다 — 예전엔 어느 계열에서도 안 잡혔다."""
    p = os.path.join(_ROOT, "core", "render_vivlio", "series", name, "render.py")
    src = io.open(p, encoding="utf-8").read()
    assert '_refs.mark("#' in src or '_mark("#' in src, \
        f"{name}: 머리·꼬리에 자리표가 없다"


def test_rich_segment_vs_block():
    """`t` 는 서식 조각의 '글자'이기도 하고 특강 블록의 '종류'이기도 하다.

    `t` 하나로 가르면 특강의 모든 블록이 서식 조각으로 보여 찾기가 그 계열에서
    **한 건도 못 찾는다** — 오류가 아니라 0건이라 더 안 보인다.
    """
    from routes.book_studio import _is_rich_seg
    assert _is_rich_seg({"t": "밑줄", "u": True})
    assert _is_rich_seg({"t": "글"})
    assert _is_rich_seg({"t": " [출처]", "k": "src"})
    assert not _is_rich_seg({"t": "passage", "r": ["글"]})
    assert not _is_rich_seg({"t": "word", "head": "specific"})
    assert not _is_rich_seg("글자")


def test_scan_finds_inside_special_blocks():
    from routes.book_studio import _scan
    d = {"volumes": [{"blocks": [
        {"t": "passage", "r": ["진화적 관점에서"]},
        {"t": "word", "head": "관점", "senses": [["① 관점, 시각"]]},
    ]}]}
    refs = {h["ref"] for h in _scan(d, "관점")}
    assert "volumes.0.blocks.0.r.0" in refs
    assert any(r.startswith("volumes.0.blocks.1") for r in refs)


def test_scan_keeps_rich_run_as_one_place():
    """서식이 섞인 줄은 조각마다가 아니라 **줄 하나**가 한 자리다."""
    from routes.book_studio import _scan
    d = {"lessons": [{"problems": [
        {"stem": ["다음 ", {"t": "밑줄 친", "u": True}, " 부분"]}]}]}
    hits = _scan(d, "밑줄")
    assert [h["ref"] for h in hits] == ["lessons.0.problems.0.stem"]


# ── 지면은 딴 문서에 격리되어 있는가 ───────────────────────────
# 지면을 작업대와 **같은 문서**에 그렸더니 앱 CSS 가 조판에 얹혔다.
# `main.css` 첫 줄의 전역 리셋(`*{box-sizing:border-box}`)이 Vivliostyle 의
# 판면 래퍼까지 먹어 **여백이 두 번 깎였고**, 본문 단이 167mm 여야 하는데
# 118mm 로 좁아져 줄바꿈도 면 나눔도 달라졌다 — 그걸 미리보기라고 보여 줬다.
#
# 보상용 CSS 로 막을 수도 있었지만, 그러면 앱 스타일시트에 규칙 하나 더할
# 때마다 같은 사고가 난다. 그래서 **문서를 갈랐다**(`/book-studio/frame`).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIO_HTML = os.path.join(_ROOT, "templates", "book_studio.html")


def _studio_src():
    return io.open(STUDIO_HTML, encoding="utf-8").read()


def _routes_src():
    return io.open(os.path.join(_ROOT, "routes", "book_studio.py"),
                   encoding="utf-8").read()


def test_page_lives_in_its_own_document():
    src = _studio_src()
    assert 'id="ide-frame"' in src and 'src="/book-studio/frame"' in src, \
        "지면이 작업대와 같은 문서로 돌아왔다 — 앱 CSS 가 조판에 얹힌다"


def test_engine_is_loaded_only_inside_the_frame():
    """화면 문서에도 엔진을 실으면 그쪽 기준으로 계산돼 판이 달라진다."""
    src = _studio_src()
    assert 'src="/book-studio/core/vivlio-core.js"' not in src
    assert "fwin() && fwin().VivlioCore" in src or "fwin().VivlioCore" in src


def test_frame_document_has_no_universal_rule():
    """지면 문서 안에서도 전칭 선택자는 금물이다 — 같은 사고가 난다."""
    import re as _re
    src = _routes_src()
    i = src.index("FRAME_HTML")
    css = src[i:src.index("</style>", i)]
    css = _re.sub(r"/\*.*?\*/", "", css, flags=_re.S)     # 주석은 뺀다
    for line in css.splitlines():
        sel = line.split("{")[0].strip()
        if not sel or "{" not in line:
            continue
        assert not _re.search(r"(^|[\s,>])\*", sel), f"전칭 규칙: {line.strip()}"


def test_frame_route_exists():
    assert '@bp.route("/book-studio/frame")' in _routes_src()


def test_frame_may_be_framed_and_may_eval():
    """CSP — 지면 문서는 우리가 물고(frame-ancestors), 엔진이 eval 을 쓴다."""
    auth = io.open(os.path.join(_ROOT, "routes", "auth.py"),
                   encoding="utf-8").read()
    assert '"/book-studio/frame"' in auth


def test_selection_uses_the_frame_document():
    """화면 문서의 `getSelection()` 은 지면 안 글을 모른다 — 서식이 안 먹는다."""
    src = _studio_src()
    assert "fwin().getSelection()" in src
    assert "document.createRange()" not in src, "화면 문서의 Range 를 쓰고 있다"


def test_keys_reach_the_frame():
    """글을 고치는 동안 커서는 지면 문서 안이다 — ⌘↵·⌘B·Esc 가 거기서 난다."""
    assert "fdoc().addEventListener('keydown'" in _studio_src()


def test_main_css_still_has_the_global_reset():
    """이 시험들이 지키는 전제 — 전역 리셋이 실제로 있다.

    리셋이 없어졌는데 시험만 남으면 무엇을 지키는지 모르게 된다.
    """
    css = io.open(os.path.join(_ROOT, "static", "css", "main.css"),
                  encoding="utf-8").read()
    assert "box-sizing: border-box" in "\n".join(css.splitlines()[:4])


# ── 알아볼 수 있는가 · 고를 수 있는가 ─────────────────────────
def test_click_does_not_steal_selection():
    """고치는 글 안을 눌렀을 때 다시 고르면 커서가 글 끝으로 튄다.

    그 바람에 드래그도 더블클릭도 소용없이 "문장은 안 잡히고 단락만 잡히는"
    상태가 됐다. 글을 고르는 것은 브라우저가 알아서 한다.
    """
    assert "editEl.contains(ev.target)" in _studio_src()


@pytest.mark.parametrize("name", ("blackbook", "vocabook", "vocaunit",
                                  "special", "middle"))
def test_series_names_its_styles(name):
    """`.pbox` 같은 CSS 이름만 보이면 무엇을 고르는지 알 수 없다."""
    from core.render_vivlio import series as _sreg
    names = _sreg.get(name).style_names
    assert isinstance(names, dict) and len(names) >= 10, f"{name}: 이름표가 없다"
    for k, v in names.items():
        assert not k.startswith("."), f"{name}: 점 없이 적을 것 ({k})"
        assert v.strip(), f"{name}: 빈 이름 ({k})"


def test_ref_source_namespaces():
    """자리표 머리글자가 곧 출처다 — 원고 · 책 설정 · 조판물."""
    from core.render_vivlio import refs
    assert refs.source_of("lessons.0.problems.3.stem") == "data"
    assert refs.source_of("book.subject") == "config"
    assert refs.source_of("#머리띠") == "fixed"
    assert refs.source_of("") == ""


def test_header_is_selectable():
    """머리 띠·탭·제목·기입칸이 다 잡혀야 한다 — 예전엔 하나도 안 잡혔다."""
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                               "blackbook", "render.py"), encoding="utf-8").read()
    for needle in ('_mark("#머리띠"', '_mark("book.subject"', '_mark("#기입칸"'):
        assert needle in src, f"머리 띠에 자리표가 없다: {needle}"


def test_fixed_ref_refuses_text_edit_with_a_reason():
    """조판이 만든 자리는 글이 없다. 그냥 실패하면 왜 안 되는지 알 수 없다."""
    src = _routes_src()
    assert 'src == "fixed"' in src and "단락 스타일" in src


def test_config_ref_edits_the_config():
    """머리 띠 제목은 원고가 아니라 책 설정이다 — 이력에 쌓으면 아무 일도 없다."""
    src = _routes_src()
    assert "_text_from_config" in src and 'src == "config"' in src


def test_cmyk_uses_the_press_profile():
    """눈대중 공식으로 낸 숫자는 인쇄물과 다르다 — 없느니만 못하다."""
    src = _routes_src()
    assert "prepress.find_profile()" in src
    assert "DEFAULT_GRAY_MAP" in src, "먹으로 빠지는 색을 CMYK 로 적으면 거짓말이다"


def test_cmyk_api_matches_prepress(client):
    """실제로 변환되는지 — 본문 먹은 K 단색이어야 한다."""
    r = client.post("/api/book-studio/cmyk", json={"colors": ["#231f20"]})
    assert r.status_code == 200
    d = r.get_json()["cmyk"].get("#231f20")
    if d is None:
        pytest.skip("이 기계에 인쇄 프로파일이 없다")
    assert d.get("gray") is True and d["k"] == 100


# ── 에디터로 쓸 수 있는가 ──────────────────────────────────────
def test_length_without_unit_is_refused():
    """`font-size: 20` 은 CSS 가 통째로 무시된다.

    그런데도 "저장했습니다" 가 떴다 — 조용히 아무 일도 안 하는 것이 제일 나쁘다.
    """
    from routes.book_studio import _needs_unit
    assert _needs_unit("font-size", "20")
    assert _needs_unit("margin-top", "3")
    assert not _needs_unit("font-size", "20pt")
    assert not _needs_unit("line-height", "1.5")   # 배수는 단위가 없다
    assert not _needs_unit("font-size", "0")
    assert not _needs_unit("color", "#fff")


def test_styles_api_refuses_unitless(client):
    r = client.post("/api/book-studio/styles",
                    json={"b": "없는책", "selector": ".chip",
                          "props": {"font-size": "20"}})
    assert r.status_code == 400
    assert "단위" in r.get_json()["error"]


def test_panels_are_the_same_for_every_book():
    """인디자인은 어떤 파일을 열어도 문자·단락 패널이 같다.

    예전에는 계열이 선언한 손잡이를 그대로 늘어놓아 **책마다 패널이 달랐다**
    (어떤 책은 "헤더 간격", 어떤 책은 "보는 권") — 그건 에디터가 아니다.
    """
    src = _studio_src()
    assert "var CHAR_PROPS" in src and "var PARA_PROPS" in src
    for need in ("font-size", "line-height", "letter-spacing", "color"):
        assert need in src.split("var CHAR_PROPS")[1][:1500], f"문자 패널에 {need} 없음"
    for need in ("text-align", "text-indent", "margin-top", "break-before"):
        assert need in src.split("var PARA_PROPS")[1][:1200], f"단락 패널에 {need} 없음"


def test_panel_builds_units_itself():
    """숫자와 단위를 따로 받아 **우리가** 붙인다 — 사람이 빠뜨리면 안 되니까."""
    src = _studio_src()
    assert "n + us.value" in src


def test_live_preview_uses_the_surviving_class():
    """`[data-ref=…]` 는 조판 결과 DOM 에 없다 — 그걸로는 미리보기가 안 걸린다.

    스타일시트도 안 통했다(엔진이 head 를 자기 식으로 다뤄 규칙이 0개로 들어갔다).
    그래서 **요소에 직접** `important` 로 얹는다.
    """
    src = _studio_src()
    assert "setProperty(k, props[k], 'important')" in src
    assert "liveClear" in src


def test_click_selects_block_dblclick_goes_inner():
    src = _studio_src()
    assert "dblclick" in src and "function deselect()" in src
    assert "c[c.length - 1]" in src, "한 번 누르면 가장 바깥이어야 한다"


def test_containers_are_marked():
    """지문 상자·문항이 통째로 잡혀야 한 번에 고칠 수 있다."""
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                               "blackbook", "render.py"), encoding="utf-8").read()
    assert '_mark(u, "vunit")' in src
    assert '"pbox")' in src and '_mark(q, "q")' in src


def test_editing_keeps_the_page_looking_the_same():
    """누를 때마다 바탕이 노래지고 글꼴이 바뀌면 조판을 보는 눈이 흐트러진다."""
    src = _routes_src()
    i = src.index(".ide-editing")
    block = src[i:i + 300]
    assert "background" not in block and "font-family" not in block
    assert "caret-color" in block


def test_page_panel_and_spread():
    src = _studio_src()
    assert "function drawPages()" in src and "function gotoPage(" in src
    assert "function setSpread(" in src and "'spread'" in src


# ── 글자 단위 서식 ────────────────────────────────────────────
# 에디터라면 **고른 몇 글자만** 12pt·빨강으로 만들 수 있어야 한다.
# 예전 방식(글 안에 `**굵게**` 표시를 끼움)으로는 굵기·밑줄·기울임 셋뿐이었고,
# 편집기를 열 때마다 글이 딴것처럼 보였다.
RICH_CASES = [
    "그냥 민글",
    ["앞 ", {"t": "밑줄", "u": True}, " 뒤"],
    [{"t": "굵고 밑줄", "b": True, "u": True}],
    ["a ", {"t": "b", "i": True}, " c"],
    ["빈칸 _____ 뒤"],
    ["앞 ", {"t": "큰 글자", "st": {"font-size": "12pt", "color": "#cc0000"}}, " 뒤"],
    ["앞 ", {"t": "강조", "cs": "강조"}, " 뒤"],
]


@pytest.mark.parametrize("rich", RICH_CASES)
def test_html_roundtrip_keeps_everything(rich):
    from core.render_vivlio import richtext as rt
    back = rt.from_html(rt.to_html(rich), like=rich)
    assert rt.plain(back) == rt.plain(rich), "글자가 달라졌다"
    assert rt.to_html(back) == rt.to_html(rich), "서식이 달라졌다"


def test_plain_stays_plain():
    """민글은 민글로 — 형태가 바뀌면 data.json 이 달라져 회귀가 시끄러워진다."""
    from core.render_vivlio import richtext as rt
    assert rt.from_html(rt.to_html("그냥 글")) == "그냥 글"
    assert isinstance(rt.from_html("<b>굵게</b>"), dict)


def test_blank_survives_the_editor():
    """빈칸(`_____`)은 편집기에서 빈칸처럼 보이면서 **정확히** 되돌아와야 한다."""
    from core.render_vivlio import richtext as rt
    h = rt.to_html(["답: _____ 이다"])
    assert "ed-blank" in h and 'data-raw="_____"' in h
    assert rt.from_html(h) == "답: _____ 이다"


def test_paste_junk_is_stripped():
    """붙여넣기로 들어온 남의 태그는 글자만 남긴다."""
    from core.render_vivlio import richtext as rt
    got = rt.from_html('<div class="x"><script>bad()</script>글<b>굵게</b></div>')
    assert rt.plain(got) == "bad()글굵게" or rt.plain(got) == "글굵게"
    assert "script" not in str(got)


@pytest.mark.parametrize("name", ("blackbook", "special"))
def test_renderer_emits_char_style(name):
    """세그먼트에 건 서식이 **조판까지** 가야 한다."""
    mod = __import__("core.render_vivlio.series." + name + ".render",
                     fromlist=["render"])
    got = mod.inl(["앞 ", {"t": "크게", "st": {"font-size": "12pt"}}, " 뒤"])
    assert "font-size:12pt" in got
    assert mod.inl(["그냥 글"]) == "그냥 글", "민글은 예전과 똑같아야 한다"


def test_container_ref_refuses_text_edit():
    """덩어리 자리표에는 글이 없다 — 빈 편집기가 뜨면 원인을 알 수 없다."""
    src = _routes_src()
    assert '"kind": "container"' in src


def test_char_panel_targets_the_selection():
    src = _studio_src()
    assert "function hasCharSel()" in src and "function fmtStyle(" in src
    assert "function charOrLive(" in src


def test_named_character_styles():
    src = _studio_src()
    assert "function applyCharStyle(" in src and "cs-" in src


def test_page_thumbnails_come_from_the_pdf():
    """지면을 다시 그려 만들려면 몇 분이 든다 — 마지막 PDF 에서 뽑는다."""
    src = _routes_src()
    assert "/book-studio/thumb/" in src and "get_pixmap" in src
    assert "마지막 조판본" in _studio_src(), "옛 그림임을 화면에 적어야 한다"


def test_view_guides_do_not_touch_layout():
    """안내선·재단선은 **보기**다 — 조판에 영향을 주면 안 된다."""
    src = _routes_src()
    i = src.index("show-margin")
    block = src[i - 400:i + 600]
    assert "pointer-events: none" in block


# ── 되돌리기는 하나여야 한다 ──────────────────────────────────
# 글은 편집 이력, 디자인은 `.bak` 으로 갈라져 있었다. 그러면 방금 한 일을
# 되돌리려고 **어느 단추를 눌러야 하는지** 사람이 알아야 한다. 인디자인은
# 무엇을 했든 ⌘Z 하나다.
def test_design_ops_share_the_history():
    from core.render_vivlio import edits
    assert set(edits.DESIGN_OPS) == {"style", "knob", "css"}
    assert set(edits.TEXT_OPS) <= set(edits.OPS)


def test_design_ops_are_not_applied_to_data():
    """디자인 연산은 이미 파일에 들어가 있다 — data 에 또 얹으면 두 번 먹는다."""
    from core.render_vivlio import edits
    data = {"a": ["x"]}
    edits.apply_all(data, {"head": 1, "ops": [
        {"op": "style", "sel": ".c", "v": {"color": "red"}}]})
    assert data == {"a": ["x"]}


def test_patch_text_can_add_a_top_level_key():
    """최상위에 새 절을 못 만들면 config 를 통째로 다시 써 모양을 잃는다."""
    raw = '{\n  "a": 1,\n\n  "b": { "x": 2 }\n}\n'
    out = kn.patch_text(raw, {"styles": {".c": {"color": "red"}}})
    assert json.loads(out)["styles"] == {".c": {"color": "red"}}
    assert '"b": { "x": 2 }' in out, "손으로 맞춘 모양이 그대로여야 한다"
    assert kn.patch_text(out, {"styles": None}) == raw, "지우면 원문으로"


def test_root_span_is_recorded():
    """루트가 `".{}"` 로 기록돼 최상위 추가 자리를 못 찾던 버그."""
    assert "{}" in kn.spans('{"a": 1}')


def test_undo_drops_empty_parent_sections():
    """`palette` 절이 없던 책에서 색을 바꿨다 되돌리면 `{}` 가 남았다."""
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio",
                               "design_ops.py"), encoding="utf-8").read()
    assert "_drop_empty_parents" in src


def test_history_is_readable():
    """이력은 사람이 읽는 자리다 — `set`·`style` 은 우리 용어다."""
    src = _routes_src()
    assert '"글 고침"' in src and '"label"' in src


# ── 인디자인 관례 ─────────────────────────────────────────────
def test_regex_find_reports_a_bad_pattern():
    """조용히 0건이면 글이 없는 건지 식이 틀린 건지 알 수 없다."""
    src = _routes_src()
    assert "정규식이 틀렸습니다" in src


def test_regex_scan_works():
    import re as _re
    from routes.book_studio import _scan
    d = {"a": ["2024년 3월", "그냥 글"]}
    assert len(_scan(d, "", rx=_re.compile(r"\d{4}년"))) == 1
    assert len(_scan(d, "", rx=_re.compile(r"^그냥"))) == 1


def test_shortcuts_follow_indesign():
    src = _studio_src()
    for need in ("k === 'f'", "k === 's'", "k === '0'", "k === '1'",
                 "k === ';'", "ArrowRight", "PageDown"):
        assert need in src, f"단축키 {need} 없음"


def test_undo_works_while_editing():
    """⌘Z 는 **어디서든** 먹어야 한다 — 글을 고치는 중이라도."""
    src = _studio_src()
    i = src.index("function onKey(e)")
    head = src[i:i + 1400]
    assert head.index("k === 'z'") < head.index("if (editEl) {"), \
        "되돌리기가 편집 블록 안에 갇혔다"


def test_zoom_shows_percent():
    """몇 %인지 보여야 '이 정도면 되겠다' 를 판단할 수 있다."""
    src = _studio_src()
    assert "function setZoom(" in src and "Math.round(zoom * 100)" in src
    assert "wheel" in src, "⌥휠 확대·축소"


# ── 단락 옵션 (인디자인의 단락 옵션) ──────────────────────────
# 조판 엔진이 이걸 다 해 내는지 **실측**으로 확인했다 — 표 · 자동 번호 ·
# 글머리표 · 단락 경계선 · 드롭캡 · 세로쓰기 · 각주 · 여러 단.
# 실제 책에 걸어 PDF 에 경계선과 드롭캡이 찍히는 것도 확인했다.
def test_para_options_exist():
    src = _studio_src()
    assert "var PARA_OPTS" in src
    block = src.split("var PARA_OPTS")[1][:2600]
    for need in ("자동 번호", "글머리표", "단락 경계선", "드롭캡",
                 "2단으로", "세로쓰기"):
        assert need in block, f"단락 옵션에 {need} 없음"


def test_para_options_use_pseudo_elements():
    """번호·글머리표·드롭캡은 가상 요소가 있어야 한다."""
    src = _studio_src()
    assert "'::before'" in src and "'::first-letter'" in src


def test_styles_api_accepts_pseudo_and_content(client):
    """`content: counter(...)` 같은 값이 검사에 걸리면 안 된다."""
    r = client.post("/api/book-studio/styles",
                    json={"b": "없는책", "selector": ".t::before",
                          "props": {"content": 'counter(p-n) ". "'}})
    assert r.status_code == 404, "검사는 통과하고 책에서만 걸려야 한다"


# ── 서체 · 레이어 ─────────────────────────────────────────────
def test_font_picker_only_offers_embedded_fonts():
    """PDF 에 들어가는 것은 이 책이 **임베드한** 서체뿐이다.

    아무 서체나 적게 두면 화면에서는 되는데 인쇄물이 딴 글씨가 된다.
    브라우저의 `queryLocalFonts` 를 쓰지 않는 이유이기도 하다(크로미움 전용인
    데다, 설치돼 있다고 PDF 에 들어가는 것이 아니다).
    """
    src = _studio_src()
    assert "kind: 'font'" in src and "bookFonts" in src
    assert "queryLocalFonts" not in src


def test_fonts_api_splits_used_and_available():
    src = _routes_src()
    assert '"used"' in src and '"available"' in src and '"missing"' in src


def test_layers_are_view_only():
    """레이어는 **보기**다 — 끈 채로 PDF 를 구우면 그건 다른 책이다."""
    src = _studio_src()
    assert "var LAYER_DEFS" in src and "function applyLayers(" in src
    i = src.index("function applyLayers(")
    assert "visibility" in src[i:i + 900]
    assert "조판은 안 바뀝니다" in src or "조판을 바꾸지 않는다" in src


def test_layers_redraw_on_page_change():
    """면마다 든 갈래가 다르다 — 한 번만 보면 그때 있던 것만 잡힌다."""
    src = _studio_src()
    i = src.index("function drawPageNo()")
    assert "drawLayers()" in src[i:i + 700]


# ── 표 ────────────────────────────────────────────────────────
# 표는 어느 계열에나 필요하고 모양도 같다 — 그래서 자료 모양과 HTML 을
# `core/table.py` 한 곳에 둔다. 계열은 한 줄로 꽂는다.
def test_table_html_marks_every_cell():
    """칸마다 자리표가 있어야 **그 칸만** 고칠 수 있다."""
    from core.render_vivlio import refs, table
    refs.clear()
    b = {"t": "table", "head": ["ㄱ", "ㄴ"], "rows": [["가", "나"]]}
    h = table.html(b, ref="lessons.0.problems.0.blocks.3")
    assert 'data-ref="lessons.0.problems.0.blocks.3.head.0"' in h
    assert 'data-ref="lessons.0.problems.0.blocks.3.rows.0.1"' in h


def test_table_repeats_the_header_across_pages():
    """표가 길면 면을 넘는다 — 머리줄이 다음 면에도 나와야 읽을 수 있다."""
    from core.render_vivlio import table
    assert "table-header-group" in table.CSS


def test_table_cells_are_rich():
    """칸에도 굵게·글자 서식이 들어가야 한다."""
    from core.render_vivlio import table
    h = table.html({"t": "table", "rows": [[{"t": "굵게", "b": True}]]})
    assert "<b>굵게</b>" in h


def test_table_plain_for_verification():
    """표도 글이다 — 검수 전수 대조에 들어가야 한다."""
    from core.render_vivlio import table
    assert table.plain({"head": ["ㄱ"], "rows": [["가", "나"]]}) == "ㄱ 가 나"


def test_series_renders_table_blocks():
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                               "blackbook", "render.py"), encoding="utf-8").read()
    assert "t == 'table'" in src and "_tbl.html(" in src


def test_table_css_sees_edits_not_just_data():
    """작업대에서 넣은 표는 `edits.json` 에 있다.

    `data.json` 만 보면 못 찾아, 표가 **괘선 없이 글자만** 늘어선 채로 나간다
    (실제로 그랬다).
    """
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "knobs.py"),
                  encoding="utf-8").read()
    i = src.index("def _has_table")
    assert "edits.json" in src[i:i + 900]


def test_table_ops_go_through_history():
    """표도 원고 자료다 — ⌘Z 로 되돌아가야 한다."""
    src = _routes_src()
    i = src.index("def api_table")
    assert "ed.push" in src[i:i + 3000]


# ── 면 이동 · 서체 기능 ───────────────────────────────────────
def test_render_all_is_passed_at_load_time():
    """`renderAllPages` 는 **문서를 실을 때** 주는 값이다.

    만들 때만 주거나 `setOptions` 로 바꾸면 안 먹어, 그대로 두 면만 그렸다.
    """
    src = _studio_src()
    i = src.index("viewer.loadDocument(")
    assert "renderAllPages: renderAll" in src[i:i + 400]


def test_ready_does_not_wait_only_for_loaded():
    """`renderAllPages` 면 `loaded` 가 한참 뒤에 오거나 안 온다.

    그동안 면을 못 넘기면 "아직 조판 중" 만 뜬다(실제로 그랬다).
    """
    src = _studio_src()
    assert "readystatechange" in src and "'interactive'" in src


def test_epage_jump_falls_back():
    """`epage` 는 다 그리기 전에는 어림값이다(실측: epage 24 → 10면)."""
    src = _studio_src()
    assert "function jumpTo(" in src and "function hopTo(" in src
    i = src.index("function jumpTo(")
    assert "hopTo(n)" in src[i:i + 900], "빗나가면 옛 길로 마저 가야 한다"


def test_page_panel_matches_the_scope():
    """썸네일은 전권 PDF 것이라 견본을 보고 있으면 번호가 어긋난다.

    실측: 견본(40면)에서 25번 썸네일을 눌렀더니 13면으로 갔다.
    """
    src = _studio_src()
    assert "sampleNow" in src and "scope !== 'full'" in src


def test_opentype_controls_exist():
    src = _studio_src()
    block = src.split("var CHAR_PROPS")[1][:3000]
    for need in ("font-variant-caps", "font-variant-numeric",
                 "font-variant-ligatures", "font-kerning",
                 "font-feature-settings"):
        assert need in block, f"문자 패널에 {need} 없음"


def test_paragraph_typography_controls_exist():
    src = _studio_src()
    block = src.split("var PARA_PROPS")[1][:2000]
    for need in ("hyphens", "text-wrap", "widows", "orphans", "break-after"):
        assert need in block, f"단락 패널에 {need} 없음"


# ── 자유 배치 상자 ────────────────────────────────────────────
# "흐르는 조판이라 좌표 배치는 못 한다" 고 적었던 것을 실측으로 뒤집었다 —
# 흐름 한가운데 둔 `position:absolute` 상자가 **그 면을 기준으로** 앉는다
# (둘째 면 top 20mm·right 6mm 확인). 실제 책에 넣어 8면에 앉는 것도 봤다.
def test_box_absolute_and_wrap():
    from core.render_vivlio import box
    a = box.html({"t": "box", "at": {"top": "20mm", "left": "8mm"},
                  "paras": ["글"]})
    assert "viv-box abs" in a and "top:20mm" in a and "left:8mm" in a
    w = box.html({"t": "box", "wrap": "right", "at": {"width": "34mm"},
                  "paras": ["글"]})
    assert "wrapR" in w and "abs" not in w


def test_box_rejects_junk_lengths():
    """좌표 칸에 아무 CSS 나 들어가면 조판이 깨진다."""
    from core.render_vivlio import box
    assert box._len("4mm") == "4mm"
    assert box._len("url(evil)") == ""
    assert box._len("12pt") == "12pt"
    assert box._len("") == ""


def test_box_marks_its_paragraphs():
    from core.render_vivlio import refs, box
    refs.clear()
    h = box.html({"t": "box", "paras": ["가", "나"]}, ref="a.blocks.5")
    assert 'data-ref="a.blocks.5.paras.1"' in h


def test_box_plain_for_verification():
    from core.render_vivlio import box
    assert box.plain({"paras": ["가", {"t": "나", "b": 1}]}) == "가 나"


def test_series_renders_box_blocks():
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                               "blackbook", "render.py"), encoding="utf-8").read()
    assert "t == 'box'" in src and "_box.html(" in src


def test_box_ops_go_through_history():
    src = _routes_src()
    i = src.index("def api_box")
    assert "ed.push" in src[i:i + 2600]


# ── 문서 설정 · 눈금자 · 안내선 ───────────────────────────────
@pytest.mark.parametrize("name", ("blackbook", "vocabook", "vocaunit",
                                  "special", "middle"))
def test_every_book_has_the_same_document_settings(name):
    """판형·도련은 **어느 책에나** 있다.

    계열이 저마다 선언하게 두면 인디자인의 「문서 설정」이 책마다 다른 꼴이 된다.
    """
    from core.render_vivlio import series as reg
    ks = reg.get(name).base_knobs()
    keys = {k.key for k in ks}
    assert {"page.width", "page.height", "page.bleed"} <= keys


def test_base_knobs_are_merged_first():
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "knobs.py"),
                  encoding="utf-8").read()
    i = src.index("def of(cfg, series)")
    assert "base_knobs" in src[i:i + 900]


def test_page_size_change_warns():
    """판형을 바꾸면 책이 통째로 다시 흐른다."""
    src = _studio_src()
    assert "page.width" in src and "다시 흐릅니다" in src


def test_ruler_and_guides_are_view_only():
    src = _routes_src()
    for k in ("show-ruler", "show-guide"):
        i = src.index(k)
        assert "pointer-events: none" in src[i:i + 500], f"{k} 가 조판을 건드린다"


def test_guides_land_on_exact_mm():
    """안내선은 **끌어다 놓되** 자리는 mm 로 딱 떨어져야 한다.

    "지면 좌표계가 면마다라 끌어 놓으면 흔들린다" 고 적어 두었는데 틀렸다 —
    면 상자에서 mm 로 정확히 되돌릴 수 있다(상자 끌기가 이미 그랬다).
    """
    src = _studio_src()
    i = src.index("function hookGuides")
    body = src[i:i + 3000]
    assert "bookPageW" in body, "면 폭으로 px↔mm 를 환산해야 한다"
    assert "round2(" in body, "자리를 0.01mm 로 떨어뜨린다"


# ── 마스터 페이지 (@page) ─────────────────────────────────────
# 단락 스타일로는 **면**을 못 건드린다. CSS 조판에서 `@page` 가 인디자인의
# 마스터 페이지 자리다. 실측: `:left` 왼쪽 여백을 23→33mm 로 바꾸니 짝수 면
# 본문이 33.0mm 에서 시작하고 면수가 116→122 로 늘었다.
def test_page_rules_become_css():
    class C:
        def section(self, n):
            return ({":left": {"margin-left": "23mm"}, "": {"margin-top": "30mm"}}
                    if n == "page_rules" else None)
    css = kn.page_rules_text(C())
    assert "@page :left {" in css and "margin-left: 23mm;" in css
    assert "@page  {" in css


def test_no_page_rules_no_css():
    """없으면 한 줄도 안 나가야 한다 — 빈 규칙도 판을 흔들 수 있다."""
    class D:
        def section(self, n):
            return None
    assert kn.page_rules_text(D()) == ""


def test_page_rules_go_through_history():
    src = _routes_src()
    i = src.index("def api_pagerules")
    assert "ed.push" in src[i:i + 2600]


def test_page_rules_check_units(client):
    r = client.post("/api/book-studio/pagerules",
                    json={"b": "없는책", "sel": "", "props": {"margin-top": "20"}})
    assert r.status_code == 400 and "단위" in r.get_json()["error"]


# ── 색상 견본 ─────────────────────────────────────────────────
def test_swatches_paint_the_selection():
    """색을 누르면 고른 자리(또는 고른 글자)에 칠해져야 한다.

    값 칸만 있으면 "이 색이 어디 쓰이나" 는 알아도 **칠할 수가 없다**.
    """
    src = _studio_src()
    assert "function drawSwatches()" in src and "function paintWith(" in src
    i = src.index("function paintWith(")
    assert "hasCharSel()" in src[i:i + 500], "고른 글자에도 칠해져야 한다"


def test_palette_does_not_overwrite_swatches():
    """색 팔레트를 두 곳에서 그리면 나중 것이 견본을 지운다."""
    src = _studio_src()
    i = src.index("function drawPalettes()")
    block = src[i:i + 700]
    assert "drawSwatches()" in block
    assert "kind !== 'color'" in block


# ── 어디에 넣을 수 있나 · 끌어서 옮기기 ───────────────────────
def test_list_slot_accepts_paragraph_lists():
    """표·상자는 `blocks` 뿐 아니라 **어느 단락 목록에나** 들어가야 한다.

    예전에는 `blocks` 만 찾아서 어휘부에서는 "넣을 자리가 아니다" 만 떴다.
    """
    from routes.book_studio import _list_slot
    d = {"lessons": [{"vocab": [{"paras": ["가", "나"]}],
                      "problems": [{"no": 1, "stem": "발문",
                                    "blocks": [{"t": "passage",
                                                "paras": ["글"]}]}]}]}
    assert _list_slot("lessons.0.vocab.0.paras.0", d)[0] == "lessons.0.vocab.0.paras"
    assert _list_slot("lessons.0.problems.0.blocks.0", d)[0] \
        == "lessons.0.problems.0.blocks"


def test_list_slot_refuses_the_problem_list():
    """`…problems.0.stem` 을 고르면 위로 올라가다 `problems` 를 만난다.

    거기 상자를 끼우면 **문항 자리에 상자가 들어가** 조판이 깨진다.
    이름이 아니라 **든 것**으로 가른다.
    """
    from routes.book_studio import _list_slot
    d = {"lessons": [{"problems": [{"no": 1, "stem": "발문", "blocks": []}]}]}
    assert _list_slot("lessons.0.problems.0.stem", d) == (None, 0)


def test_para_like():
    from routes.book_studio import _para_like
    assert _para_like(["글", "글"])
    assert _para_like([{"t": "passage"}])
    assert _para_like([["앞", {"t": "굵게", "b": 1}]])
    assert not _para_like([{"no": 1, "stem": "발문"}])


def test_paras_render_tables_and_boxes():
    """단락 목록 안에 든 표·상자도 조판돼야 한다."""
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                               "blackbook", "render.py"), encoding="utf-8").read()
    i = src.index("def paras_html")
    assert "('table', 'box')" in src[i:i + 1200]


def test_drag_keeps_the_anchor():
    """오른쪽·아래에 붙인 상자를 끌었다고 왼쪽·위 기준으로 바꾸면 안 된다.

    판형이 바뀔 때 딴 데로 간다.
    """
    src = _studio_src()
    assert "function hookDrag()" in src
    i = src.index("function hookDrag()")
    block = src[i:i + 2600]
    assert "useRight" in block and "useBottom" in block


def test_drag_converts_px_to_mm_with_the_book_page():
    """책마다 판형이 다르다 — 216mm 로 못 박으면 딴 책에서 어긋난다."""
    src = _studio_src()
    assert "bookPageW" in src and "pg.bleed" in src


@pytest.mark.parametrize("name", ("blackbook", "vocabook", "vocaunit", "special"))
def test_every_series_takes_tables_and_boxes(name):
    """표·상자는 어느 계열에서나 들어가야 한다 — 한 책만 되면 도구가 아니다."""
    p = os.path.join(_ROOT, "core", "render_vivlio", "series", name, "render.py")
    src = io.open(p, encoding="utf-8").read()
    assert "_tbl" in src and "_box" in src, f"{name}: 표·상자를 안 받는다"


def test_word_lists_accept_boxes_but_chunks_do_not():
    """단어장 낱말 목록에는 넣을 수 있고, 문항·단원 목록에는 못 넣는다."""
    from routes.book_studio import _para_like
    assert _para_like([{"day": 1, "word": "apple", "meaning": "사과"}])
    assert not _para_like([{"lesson": 1, "vocab": [], "problems": []}])
    assert not _para_like([{"no": 1, "stem": "발문", "blocks": []}])


# ── 클로드 칸 ─────────────────────────────────────────────────
# 모델에게 리포를 통째로 열어 주면 안 된다 — 계열 코드를 고치면 그 계열 책이
# 전부 흔들리고, 원고를 고치면 납품본과 글이 달라진다. 손댈 수 있는 곳은
# 셋뿐이고 셋 다 **그 책 폴더 안 파일**이다.
def test_assist_scope_is_three_places():
    src = io.open(os.path.join(_ROOT, "core", "render_vivlio", "assist.py"),
                  encoding="utf-8").read()
    for k in ("knobs", "styles", "overrides_css"):
        assert f'"{k}"' in src
    assert "data.json" not in src.split('"""', 2)[2], "원고를 만질 길이 열렸다"


def test_assist_vets_unknown_knob():
    from core.render_vivlio import assist
    got = assist.vet({"knobs": {"없는키": 1}, "note": ""},
                     [{"key": "palette.gold", "kind": "color"}])
    assert not got["knobs"] and got["refused"]


def test_assist_vets_color_and_range():
    from core.render_vivlio import assist
    spec = [{"key": "palette.gold", "kind": "color"},
            {"key": "metrics.qgap", "kind": "mm", "min": 0, "max": 20}]
    got = assist.vet({"knobs": {"palette.gold": "빨강",
                                "metrics.qgap": 999}, "note": ""}, spec)
    assert not got["knobs"] and len(got["refused"]) == 2
    ok = assist.vet({"knobs": {"palette.gold": "#112233",
                               "metrics.qgap": 4}, "note": ""}, spec)
    assert ok["knobs"] == {"palette.gold": "#112233", "metrics.qgap": 4.0}


def test_assist_vets_selector_and_css():
    from core.render_vivlio import assist
    got = assist.vet({"styles": {"a}b": {"x": "y"}, ".ok": {"color": "red;x"}},
                     "overrides_css": "@import url(http://x)", "note": ""}, [])
    assert not got["styles"] and got["overrides_css"] is None
    assert len(got["refused"]) >= 3


def test_assist_refuses_screen_only_effects_in_prompt():
    """인쇄물이라는 것을 모델에게 못박아 둔다."""
    from core.render_vivlio import assist
    assert "인쇄물" in assist.SYSTEM and "8pt" in assist.SYSTEM


def test_assist_says_how_to_set_the_key():
    """키가 없을 때 그냥 실패하면 무엇을 해야 하는지 알 수 없다."""
    from core.render_vivlio import assist
    if assist.have_key():
        pytest.skip("이 기계에는 키가 있다")
    try:
        assist.ask("x", {})
    except assist.Refused as e:
        assert "ANTHROPIC_API_KEY" in str(e)
    else:
        pytest.fail("키가 없는데 그냥 지나갔다")


def test_assist_undo_removes_files_it_created():
    """원래 **없던** 파일이면 `.bak` 이 없어 되돌릴 방법이 사라진다.

    '원래 없었다' 도 되돌릴 상태다 — 표식(`.none`)을 남겨 도로 없앤다.
    """
    src = _routes_src()
    assert '".none"' in src and "os.remove(f)" in src


# ── 중등부 다리 ────────────────────────────────────────────────
def test_middle_series_registered():
    from core.render_vivlio import series as reg
    assert "middle" in reg.names()


def test_middle_build_dir_is_outside_book_folder():
    """중등부는 `automation/work/<교재>/build<권>` 에 조판한다.

    작업대가 `<책폴더>/build` 로 못 박아 두면 이 계열은 **404 만 난다** —
    지면이 안 나오는데 로그는 조용해 원인을 찾기 어렵다.
    """
    from core.render_vivlio.series.middle import MiddleSeries

    class C:
        build_dir = "/책/build"
        def section(self, n):
            return {"book": "cheonjae", "vol": 2} if n == "middle" else None
    got = MiddleSeries().build_dir(C())
    assert got.endswith(os.path.join("work", "cheonjae", "build2"))
    assert "automation" in got


def test_middle_needs_book_key():
    from core.render_vivlio.series.middle import MiddleSeries

    class C:
        def section(self, n):
            return {}
    with pytest.raises(ValueError):
        MiddleSeries().build_dir(C())


def test_middle_passes_repo_on_pythonpath():
    """automation 은 리포 밖이라 길을 안 주면 자리표 import 가 조용히 실패한다.

    실패해도 조판은 되므로 **지면은 나오는데 클릭만 안 먹는다** — 실제로 그
    상태로 한참 갔다.
    """
    src = io.open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "core", "render_vivlio", "series", "middle", "__init__.py"),
        encoding="utf-8").read()
    assert 'env["PYTHONPATH"]' in src


def test_base_series_has_build_dir_hook():
    from core.render_vivlio.series.base import Series
    assert hasattr(Series, "build_dir")


# ── 없는 절을 만들어 넣기 ──────────────────────────────────────
RAW = """{
  "series": "special",
  "book": { "title": "가", "school": "나" },
  "verify": {
    "suffix": ""
  }
}
"""


def test_patch_text_creates_missing_parent():
    """`verify.design.strict` 는 대개 config 에 **절이 통째로 없다**.

    예전엔 여기서 포기했고, 부르는 쪽이 config 를 통째로 다시 써 손으로 맞춘
    모양(빈 줄·한 줄짜리 객체·주석 같은 `_note`)을 다 잃었다.
    """
    out = kn.patch_text(RAW, {"verify.design.strict": True})
    d = json.loads(out)
    assert d["verify"]["design"]["strict"] is True
    assert d["verify"]["suffix"] == ""          # 원래 있던 것은 그대로
    assert d["book"] == {"title": "가", "school": "나"}


def test_patch_text_keeps_shape():
    """바뀐 곳 말고는 글자 하나 안 건드려야 한다."""
    out = kn.patch_text(RAW, {"verify.design.strict": True})
    assert '"book": { "title": "가", "school": "나" },' in out
    assert kn.patch_text(RAW, {}) == RAW


def test_patch_text_two_levels_deep():
    out = kn.patch_text(RAW, {"verify.design.chroma.max": 3})
    assert json.loads(out)["verify"]["design"]["chroma"]["max"] == 3


def test_new_book_starts_strict():
    """신규 조판은 디자인 게이트를 켜고 시작한다 — 기존 책은 경고만."""
    src = io.open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engines", "vivlio_book", "engine.py"), encoding="utf-8").read()
    assert 'changes["verify.design.strict"] = True' in src


# ── 작업대 API 방어선 ───────────────────────────────────────────
@pytest.fixture()
def client():
    """인증만 잠깐 떼고 **반드시 되돌린다**.

    ⚠ Flask 의 `app` 은 모듈 전역이라 여기서 뗀 `check_auth` 가 같은 pytest
      프로세스의 **다른 시험까지** 따라간다. 처음엔 되돌리지 않아서
      `test_result_session_expiry` 3건과 `test_route_parity` 1건이 같이 깨졌다.
    """
    os.environ.setdefault("YONE_SECRET_KEY", "test-only")
    import app as A
    saved = {k: list(v) for k, v in A.app.before_request_funcs.items()}
    for key in list(A.app.before_request_funcs):
        A.app.before_request_funcs[key] = [
            f for f in A.app.before_request_funcs[key]
            if f.__name__ != "check_auth"]
    A.app.config["TESTING"] = True
    try:
        yield A.app.test_client()
    finally:
        A.app.before_request_funcs.clear()
        A.app.before_request_funcs.update(saved)


def test_book_key_matches_across_nfc_nfd(client):
    """맥 파일 이름은 NFD, 링크로 오는 글자는 NFC — 안 맞으면 **조용히 첫 책**.

    팔레트(API)는 이미 정규화하고 있어서 값은 맞는데 지면만 딴 책이 열려,
    화면만 보고는 원인을 못 찾는 종류의 어긋남이었다.
    """
    import re
    import unicodedata as u
    from routes.book_studio import _books
    bs = _books()
    if len(bs) < 2:
        pytest.skip("책이 둘 이상 있어야 가른다")
    target = bs[-1]["key"]                      # 첫 책이 아닌 것으로
    for form in ("NFC", "NFD"):
        h = client.get("/book-studio",
                       query_string={"b": u.normalize(form, target)}
                       ).get_data(as_text=True)
        m = re.search(r'<option value="([^"]*)"[^>]*selected', h)
        assert m, f"{form}: 고른 책이 없다"
        assert u.normalize("NFC", m.group(1)) == u.normalize("NFC", target), \
            f"{form}: 딴 책이 열렸다"


def test_styles_rejects_brace_injection(client):
    """선택자에 `}` 를 넣으면 knobs.css 를 통째로 갈아엎을 수 있다."""
    r = client.post("/api/book-studio/styles",
                    json={"b": "없는책", "selector": "a}body{display:none",
                          "props": {"color": "red"}})
    assert r.status_code == 400, "검사가 책 조회 뒤에 있으면 404 가 먼저 난다"


def test_styles_rejects_value_injection(client):
    r = client.post("/api/book-studio/styles",
                    json={"b": "없는책", "selector": ".a",
                          "props": {"color": "red;background:url(x)"}})
    assert r.status_code == 400


def test_op_rejects_path_traversal(client):
    r = client.post("/api/book-studio/op",
                    json={"b": "없는책", "op": "delete", "ref": "../../etc"})
    assert r.status_code == 400


def test_images_rejects_non_image(client):
    import io as _io
    r = client.post("/api/book-studio/images",
                    data={"b": "없는책",
                          "file": (_io.BytesIO(b"x"), "나쁜.sh")},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_styles_accepts_ref_selector(client):
    """`[data-ref="…"]::after` 는 통과해야 한다 — 쪽 나눔·그림이 이 길로 간다."""
    r = client.post("/api/book-studio/styles",
                    json={"b": "없는책",
                          "selector": '[data-ref="lessons.0.problems.3"]::after',
                          "props": {"content": 'url("assets/g.png")'}})
    assert r.status_code == 404, "검사는 통과하고 책에서만 걸려야 한다"


# ── 표 칸 합치기(인디자인의 셀 병합) ────────────────────────────
def test_merge_spans_and_hides_covered_cells():
    """합친 칸은 `colspan`/`rowspan` 으로 나가고, 먹힌 자리는 안 그린다.

    ⚠ 먹힌 자리를 **지우면** 뒤 칸이 앞으로 밀려 표가 어긋난다 — 그래서
      `null` 로 남겨 두고 그리지만 않는다.
    """
    from core.render_vivlio import table as T
    b = T.new(3, 3)
    b["head"] = ["가", "나", "다"]
    b["rows"] = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]
    T.merge(b, 1, 0, 2, 1)                 # 머리줄이 0행이다
    assert b["rows"][0][1] is None and b["rows"][1][0] is None
    assert [len(r) for r in b["rows"]] == [3, 3, 3], "칸 수가 줄면 안 된다"
    h = T.html(b)
    assert 'colspan="2" rowspan="2"' in h
    assert h.count("<td") == 6, "3+2+1 — 먹힌 자리 둘은 안 그린다"


def test_merge_keeps_text_and_refuses_overlap():
    """먹히는 칸의 글을 버리지 않는다. 이미 합쳐진 자리에 또 합치면 거절한다."""
    from core.render_vivlio import table as T
    b = T.new(2, 2)
    b["head"] = None
    b["rows"] = [["앞", "뒤"], ["아래", "옆"]]
    T.merge(b, 0, 0, 0, 1)
    assert "앞" in T.plain(b) and "뒤" in T.plain(b), "합치며 글이 사라졌다"
    with pytest.raises(ValueError):
        T.merge(b, 0, 0, 1, 1)


def test_merged_cell_is_not_mistaken_for_rich_segment():
    """`{"v": …}`(합친 칸)와 `{"t": …}`(서식 조각)를 갈라야 한다.

    헷갈리면 굵게 한 칸이 합쳐진 칸으로 읽혀 표가 통째로 어긋난다.
    """
    from core.render_vivlio import table as T
    assert T.span({"t": "굵게", "b": 1}) == (1, 1, {"t": "굵게", "b": 1})
    assert T.span({"v": "합친", "c": 2}) == (2, 1, "합친")


def test_unmerge_restores_cells():
    from core.render_vivlio import table as T
    b = T.new(3, 2)
    b["head"] = None
    b["rows"] = [["1", "2", "3"], ["4", "5", "6"]]
    T.merge(b, 0, 0, 1, 1)
    T.unmerge(b, 0, 0)
    assert all(x is not None for r in b["rows"] for x in r)


def test_merged_cell_text_stays_editable():
    """합치고 나면 그 칸을 못 고치게 되면 안 된다 — 안쪽 `…v` 로 내려간다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    assert 'ref += ".v"' in src, "합친 칸을 열면 '덩어리' 라고만 뜬다"


def test_table_ref_is_found_by_shape_not_by_name():
    """표 자리표를 `…blocks.N` 으로 찾으면 **계열마다 다르다.**

    단어장은 `head.3`, 중등부는 `parts.0.sections.0.blocks.3` 이다.
    칸의 모양(`head.<칸>` · `rows.<줄>.<칸>`)으로 찾아야 한 도구가 된다.
    """
    src = open(os.path.join(_ROOT, "templates", "book_studio.html"),
               encoding="utf-8").read()
    i = src.index("function tableRefOf")
    body = src[i:i + 500]
    code = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith("//"))
    assert "rows\\.\\d+\\.\\d+" in code
    assert "blocks" not in code, "계열 이름이 박혀 있다"


# ── 중등부도 같은 도구로 고쳐진다 ───────────────────────────────
def test_middle_data_lives_outside_the_book_folder():
    """중등부 자료는 automation 안에 있다 — 계열에게 물어야 한다.

    안 물으면 작업대에서 **글을 클릭하는 순간 500** 이다(`data.json` 이 없다).
    """
    from core.render_vivlio.series.middle import MiddleSeries
    from core.render_vivlio.series.base import Series
    assert MiddleSeries.data_path is not Series.data_path


def test_middle_refuses_question_lists_but_takes_blocks():
    """문항 목록(`items`)은 낱말 목록과 겉모양이 같아 공용 규칙을 통과한다.

    그런데 `r_qitems` 가 `x['lines']` 를 바로 읽어 **조판이 죽는다.**
    """
    from core.render_vivlio.series.middle import MiddleSeries
    from core.render_vivlio.series.base import para_like
    s = MiddleSeries()
    items = [{"no": "01", "text": "다음 뜻을 쓰시오", "lines": []}]
    assert para_like(items), "공용 규칙으로는 통과한다(그래서 계열이 막아야 한다)"
    assert not s.accepts_block("items", items)
    assert s.accepts_block("blocks", [{"kind": "words", "items": []}])


def test_middle_renderer_reads_the_studio_folder():
    """automation 이 `VIV_BOOK_DIR` 를 안 읽으면 고쳐도 지면이 그대로다."""
    from core.render_vivlio.series import middle
    p = os.path.join(middle._auto_dir(), "render.py")
    if not os.path.exists(p):
        pytest.skip("automation 이 이 기계에 없다")
    src = open(p, encoding="utf-8").read()
    assert "VIV_BOOK_DIR" in src
    assert "'table': r_table" in src and "'box': r_box" in src
    assert "studio_apply" in src


def test_middle_bridge_hands_over_the_book_folder():
    from core.render_vivlio.series import middle
    src = open(middle.__file__, encoding="utf-8").read()
    assert 'env["VIV_BOOK_DIR"] = bookdir' in src
    assert "studio_css(cfg)" in src, "스타일을 안 뽑으면 디자인 편집이 안 먹는다"


# ── 고친 것은 늘 되돌릴 수 있어야 한다 ──────────────────────────
def test_every_mutating_route_reports_history():
    """이력을 안 실으면 화면의 되돌리기 단추가 **꺼진 채로 남는다.**

    실제로 그랬다: 스타일 패널로 글자 크기를 바꾸면 지면은 바뀌는데 ⌘Z 가
    회색이라 되돌릴 수가 없었다. 고친 것을 알리는 응답은 모두 이력을 싣는다.
    """
    import re
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    bad = []
    for m in re.finditer(r'@bp\.route\("(/api/book-studio/[a-z-]+)"[^)]*\)\s*\ndef (\w+)',
                         src):
        i = m.end()
        j = src.find("@bp.route", i)
        body = src[i:j if j > 0 else len(src)]
        if ".push(cfg" in body and "_hist(" not in body:
            bad.append(m.group(1))
    assert not bad, f"이력을 안 싣는 곳: {bad}"


def test_client_reads_history_in_one_place():
    """자리마다 따로 부르면 반드시 빠뜨린다 — `api()` 한 곳에서 본다."""
    src = open(os.path.join(_ROOT, "templates", "book_studio.html"),
               encoding="utf-8").read()
    i = src.index("function api(u, body)")
    assert "d.history" in src[i:i + 700] and "setHist" in src[i:i + 700]


def test_page_never_goes_blank_while_retypesetting():
    """`loadDocument()` 는 지면을 비운다 — 그 몇 초가 **빈 회색 판**이었다.

    인디자인은 무슨 짓을 해도 지면이 사라지지 않는다. 직전 면을 덮어 두고
    새 면이 서면 걷는다. ⚠ 실패해도 걷어야 한다(안 걷으면 못 만진다).
    """
    src = open(os.path.join(_ROOT, "templates", "book_studio.html"),
               encoding="utf-8").read()
    assert "function veilOn" in src and "function veilOff" in src
    i = src.index("viewer.addListener('error'")
    assert "veilOff()" in src[i:i + 260], "조판이 실패하면 가리개가 남는다"
    i = src.index("function show(extraCss)")
    assert "veilOn(" in src[i - 500:i + 400], "조판을 다시 시작할 때 덮어야 한다"


def test_guides_are_dragged_not_typed():
    """인디자인은 눈금자에서 **끌어다 놓는다** — 자리를 적어 넣지 않는다.

    ⚠ 예전 안내선은 눈금자와 **같은 `::before`** 를 써서, 둘을 같이 켜면
      눈금자가 통째로 사라졌다(나중 규칙이 이긴다). 그리고 배경 그림이라
      잡을 수가 없었다.
    """
    src = open(os.path.join(_ROOT, "templates", "book_studio.html"),
               encoding="utf-8").read()
    i = src.index("$('ide-guide').addEventListener")
    assert "prompt(" not in src[i:i + 900], "아직도 적어 넣으라고 한다"
    assert "function hookGuides" in src and "function drawGuides" in src
    frame = open(os.path.join(_ROOT, "routes", "book_studio.py"),
                 encoding="utf-8").read()
    assert "#viv.show-guide .ide-gd" in frame
    assert "--gx1" not in frame, "눈금자와 같은 자리를 다투는 옛 규칙이 남았다"


def test_guides_show_up_when_dragged_out():
    """그리기만 하면 안 보인다 — 보이고 안 보이고는 판의 클래스가 정한다."""
    src = open(os.path.join(_ROOT, "templates", "book_studio.html"),
               encoding="utf-8").read()
    i = src.index("guides.push({ axis: axis")
    assert "applyViews()" in src[i:i + 500]


# ── 상자: 끌어서 옮기고, 모서리를 잡아 크기를 바꾼다 ────────────
def test_box_drag_adds_to_written_values_not_a_guessed_origin():
    """기준점을 찾으려 하면 틀린다 — **적힌 값에 움직인 만큼만** 더한다.

    상자를 담고 있는 것이 면인지 본문 상자인지는 조판이 정한다.
    `offsetParent` 는 그걸 그대로 알려 주지 않는다(실측: 면이라고 답하는데
    실제 기준은 본문 상자였고, `left:20mm` 짜리를 잡으면 42.99mm 로 튀었다).
    """
    src = _studio_src()
    i = src.index("function hookDrag")
    body = src[i:i + 4200]
    assert "mmOf(el, 'left'" in body, "지금 적힌 값에서 시작해야 한다"
    assert "pxPerMm(pg)" in body, "1mm 가 몇 px 인지는 재서 안다"
    assert "er.left - pr.left" not in body, "기준점을 다시 짐작하고 있다"


def test_box_handles_respect_which_edge_is_anchored():
    """오른쪽·아래에 붙여 둔 상자는 그 변을 지켜야 한다.

    안 그러면 판형이 바뀔 때 상자가 딴 데로 간다.
    """
    src = _studio_src()
    i = src.index("function hookDrag")
    body = src[i:i + 4200]
    assert "cur.useRight" in body and "cur.useBottom" in body
    assert "HANDLES" in src and "ide-hd" in src


def test_a_box_is_selected_as_an_object():
    """상자는 글이 아니라 **물건**이다 — 한 번 누르면 상자가 잡혀야 한다.

    바깥 덩어리가 잡히면 손잡이가 안 나와서 크기를 못 바꾼다(실제로 그랬다).
    """
    src = _studio_src()
    i = src.index("st.addEventListener('click'")
    assert "viv-box" in src[i:i + 900]


def test_text_tool_edits_the_line_you_clicked():
    """T 로 누르면 **그 줄**이 잡혀야 한다.

    인디자인에서 T 로 누르면 그 자리에 커서가 선다. 예전엔 바깥 덩어리를
    잡고 "덩어리라 글이 없다" 는 답을 받아 **엉뚱한 첫 줄**(라벨 칩)로
    들어갔다 — 본문을 눌렀는데 제목이 열렸다.
    """
    src = _studio_src()
    i = src.index("st.addEventListener('click'")
    body = src[i:i + 1200]
    assert "if (tool !== 'sel') { pick(c[0].el, c[0].ref); return; }" in body


def test_veil_is_lifted_even_if_the_engine_never_says_loaded():
    """`loaded` 가 늦거나 안 오는 경우가 실제로 있었다 — 그러면 못 만진다."""
    src = _studio_src()
    i = src.index("viewer.loadDocument(")
    assert "function watch()" in src[i:i + 900]
    assert "tries > (renderAll ? 600 : 120)" in src[i:i + 1200], \
        "끝내 안 오면 걷어야 한다"


# ── 면 넘기기 ───────────────────────────────────────────────────
def test_page_hop_rechecks_instead_of_counting_steps():
    """몇 번 뛸지 미리 세면 안 된다 — 조판 중이면 넘기라는 말이 무시된다.

    실측: 8면을 눌렀는데 4면에 섰다(세어 둔 횟수는 무시된 것도 한 번으로
    친다). 그리고 반영을 안 기다리고 연달아 넘기면 이번엔 9면까지 갔다.
    """
    src = _studio_src()
    i = src.index("function hopTo")
    body = src[i:i + 2200]
    assert "var left = Math.abs(step)" not in body, "아직도 횟수를 세고 있다"
    assert "function settle" in body, "반영을 기다렸다가 다시 봐야 한다"
    assert "++seeking" in body, "다른 이동과 겹치면 서로 넘긴다"


def test_page_number_has_one_source():
    """엔진의 자리와 `epage` 를 섞으면 면 번호가 널뛴다."""
    src = _studio_src()
    i = src.index("function pageNow")
    assert "curPage = pp.pageIndex + 1" in src[i:i + 600]
    j = src.index("viewer.addListener('nav'")
    assert "pp.pageIndex != null" in src[j:j + 600], "nav 알림이 덮어쓰면 안 된다"


def test_hop_waits_while_the_engine_is_still_composing():
    """무거운 면은 몇 초씩 걸린다 — 3초 만에 포기하면 안 된다.

    실측: 15면에서 "여기까지 갑니다" 하고 멈췄는데 실제로는 잘 가고 있었다.
    """
    src = _studio_src()
    i = src.index("function hopTo")
    body = src[i:i + 2600]
    assert "readyState === 'loading'" in body, "조판 중인지 보고 기다려야 한다"


def test_the_real_page_count_is_learned_from_the_end():
    """`epageCount` 는 어림값이다 — 견본 15면을 40면이라 했다.

    끝에 닿으면 그 자리를 참으로 삼는다(전권은 마지막 조판본 PDF 면수).
    """
    src = _studio_src()
    i = src.index("function hopTo")
    assert "pageCount = now" in src[i:i + 2600]
    j = src.index("function drawPageNo")
    assert "thumbInfo.pages" in src[j:j + 700], "전권은 PDF 면수가 참이다"


def test_page_panel_is_not_rebuilt_on_every_hop():
    """면마다 그림 116장을 새로 붙이면 넘기기가 느려진다 — 표시만 옮긴다."""
    src = _studio_src()
    assert "function markPage" in src
    i = src.index("function drawPages")
    assert "pagesDrawn" in src[i:i + 900]


def test_layers_do_not_clear_the_message_on_every_page():
    """면이 바뀔 때마다 부르는 것은 조용해야 한다 — 알림이 지워졌다."""
    src = _studio_src()
    i = src.index("function applyLayers")
    assert "function applyLayers(quiet)" in src[i - 30:i + 40]
    assert "applyLayers(true)" in src


def test_far_jump_shows_the_printed_page_meanwhile():
    """조판은 앞에서부터 흐른다 — 먼 면은 마지막 조판본 그림을 먼저 깐다.

    ⚠ 견본을 보는 중이면 면 번호가 PDF 와 달라 **엉뚱한 면**이 된다.
    """
    src = _studio_src()
    i = src.index("function hopTo")
    body = src[i:i + 2600]
    assert "/book-studio/thumb/" in body
    assert "scope === 'full'" in body, "견본에서는 깔면 안 된다"
