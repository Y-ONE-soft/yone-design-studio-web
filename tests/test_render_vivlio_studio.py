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
    i = src.index(".ide-editing {")
    block = src[i:src.index("}", i)]        # ⚠ **그 규칙 한 벌만** 본다
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
    assert "viv-box" in src[i:i + 1400]


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


# ── 특수문자 · 상자 맞추기 ──────────────────────────────────────
def test_glyph_panel_inserts_at_the_caret():
    """교재는 기호를 많이 쓴다(① ㉠ ⓐ →) — 자판으로 못 치는 것들이다.

    ⚠ 글 편집기가 열려 있어야 넣을 자리가 있다. 안 열려 있으면 **그 말을
      한다** — 조용히 아무 일도 안 하면 고장으로 보인다.
    """
    src = _studio_src()
    assert "var GLYPHS" in src and "function putGlyph" in src
    i = src.index("function putGlyph")
    body = src[i:i + 700]
    assert "insertText" in body
    assert "글자 도구" in body, "안 열렸을 때 무엇을 해야 하는지 알려야 한다"


def test_align_moves_relative_instead_of_guessing_the_origin():
    """"면 왼쪽에 붙여라" 를 **"이만큼 옮겨라"** 로 바꿔 푼다.

    `left` 는 면이 아니라 조판이 만든 담고 있는 상자에서 잰 값이다 —
    면 기준으로 좌표를 지어내면 어긋난다(실측 42.99mm).
    """
    src = _studio_src()
    i = src.index("function alignBox")
    body = src[i:i + 1500]
    assert "getBoundingClientRect" in body and "pxPerMm" in body
    assert "cur.left" not in body
    assert "el.style.right" in body, "붙여 둔 변을 지켜야 한다"


def test_box_ref_is_found_from_the_page_not_the_name():
    """상자 자리표를 `…blocks.N` 으로 찾으면 계열마다 다르다.

    상자는 낱말 목록에도 어휘부에도 들어간다(`lessons.0.vocab.0.paras.1`).
    """
    src = _studio_src()
    i = src.index("function boxRefOf")
    body = src[i:i + 700]
    code = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith("//"))
    assert "blocks" not in code, "계열 이름이 박혀 있다"
    assert "vref" in code


# ── 표 모양 · 그림 상자 ─────────────────────────────────────────
def test_table_style_is_variables_so_plain_tables_do_not_change():
    """모양을 안 정한 표는 **한 글자도 달라지면 안 된다**(회귀 대조가 흐려진다).

    그래서 모양은 CSS 변수로 받고, 정한 것이 없으면 `style` 속성 자체를 안 단다.
    """
    from core.render_vivlio import table as T
    b = T.new(2, 2)
    assert 'class="viv-tbl">' in T.html(b), "빈 style= 도 남기면 안 된다"
    b["style"] = {"line": "0.7pt solid #333", "headbg": "#eef"}
    h = T.html(b)
    assert "--tb-line:0.7pt solid #333" in h and "--tb-headbg:#eef" in h
    assert "var(--tb-line" in T.CSS and "var(--tb-headbg" in T.CSS


def test_table_style_refuses_css_injection():
    from core.render_vivlio import table as T
    b = T.new(2, 2)
    b["style"] = {"line": "red;}body{display:none", "pad": "1mm"}
    h = T.html(b)
    assert "display:none" not in h and "--tb-pad:1mm" in h


def test_image_can_go_into_a_frame():
    """문단에 붙이는 그림(`::after`)은 잡을 수가 없다 — 인디자인은 프레임에 담는다."""
    src = _studio_src()
    assert "function placeImageBox" in src
    i = src.index("function placeImageBox")
    assert "kind: 'image'" in src[i:i + 400]
    rt = open(os.path.join(_ROOT, "routes", "book_studio.py"),
              encoding="utf-8").read()
    j = rt.index("b = bx.new(kind)")
    assert 'b["img"] = "assets/" + img' in rt[j:j + 700]
    assert "os.path.basename" in rt[j:j + 700], "경로를 받으면 안 된다"


def test_box_appearance_is_a_short_list_not_any_css():
    """상자 모양(바탕·테두리·둥근 모서리·그림자·투명도·회전)은 개체 속성이다.

    ⚠ 아무 CSS 나 받으면 조판이 통째로 흔들린다 — `position` 같은 것은 막는다.
    """
    from core.render_vivlio import box as B
    assert "background" in B.STYLE_KEYS and "transform" in B.STYLE_KEYS
    assert "position" not in B.STYLE_KEYS and "float" not in B.STYLE_KEYS
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index('if act == "style":')
    assert "bx.STYLE_KEYS" in src[i:i + 900]
    assert "json.loads(json.dumps(block))" in src[i:i + 900], \
        "원본을 그대로 고치면 안 된다(사본에 고친다)"


def test_arrow_keys_nudge_the_selected_box():
    """인디자인은 화살표로 민다 — 1mm · ⇧ 5mm · ⌥ 0.25mm.

    ⚠ 한 번 누를 때마다 다시 조판하면 못 쓴다. 지면에서 먼저 움직이고
      손을 뗀 뒤 **한 번만** 저장한다.
    """
    src = _studio_src()
    assert "function nudgeBox" in src
    i = src.index("function nudgeBox")
    body = src[i:i + 1800]
    assert "e.shiftKey ? 5" in body and "0.25" in body
    assert "setTimeout" in body, "누를 때마다 저장하면 안 된다"
    assert "action: 'delete'" in body, "Delete 로 지울 수 있어야 한다"


def test_swatches_also_come_from_the_page():
    """색 손잡이가 없는 계열(포켓북·워크북)은 견본 칸이 텅 빈다.

    그런데 색은 **지면에 이미 있다** — 조판된 면에서 모아 보여 준다.
    ⚠ 손잡이 색과 달리 이름이 없다(그 자리에 칠할 뿐 책 전체가 안 바뀐다).
    """
    src = _studio_src()
    assert "function usedColors" in src
    i = src.index("function usedColors")
    body = src[i:i + 1200]
    assert "getComputedStyle" in body and "backgroundColor" in body
    assert "pageEl()" in body, "지금 보는 면에서 모아야 한다"


# ── 글자 서식이 조판을 죽이지 않는다 ────────────────────────────
@pytest.mark.parametrize("mod,fn", [
    ("blackbook", "esc1"), ("whitebook", "esc1"), ("pocketbook", "ESC"),
    ("vocabook", "esc"), ("vocaunit", "esc"), ("special", "esc"),
])
def test_escaping_survives_rich_segments(mod, fn):
    """작업대에서 글자에 서식을 걸면 그 값이 **서식 조각 목록**이 된다.

    예전에는 그런 자리에 `html.escape()` 만 있어서 **조판이 통째로 죽었다**
    (실측: 라벨 칩에 자간을 줬더니 `'list' object has no attribute 'replace'`
    — 책 전체가 안 나왔다). 평문은 예전 그대로여야 한다.
    """
    import importlib
    r = importlib.import_module("core.render_vivlio.series.%s.render" % mod)
    esc = getattr(r, fn)
    assert "&lt;" in esc("가 <나>"), "평문은 예전처럼 이스케이프한다"
    out = esc([{"t": "AV", "st": {"letter-spacing": "-0.06em"}}, " ery"])
    assert "AV" in out and "ery" in out


def test_pair_kerning_is_possible_after_all():
    """커닝 쌍은 **웹의 한계가 아니었다** — 두 글자만 골라 자간을 주면 된다.

    글자 단위 서식이 `letter-spacing` 을 싣고, 조판본에 그대로 나간다.
    """
    from core.render_vivlio import richtext as rt
    assert "letter-spacing" in rt.ST_PROPS
    seg = [{"t": "AV", "st": {"letter-spacing": "-0.06em"}}, "ery"]
    assert "letter-spacing:-0.06em" in rt.to_html(seg)
    assert rt.from_html(rt.to_html(seg))[0]["st"]["letter-spacing"] == "-0.06em"


def test_word_lists_let_you_edit_the_word_itself():
    """항목(dict)에만 자리표를 달면 "덩어리라 글이 없습니다" 에서 막힌다.

    중등부는 실제로 낱말을 눌러도 못 고쳤다 — 항목 **안의 칸**(영어·뜻)에도
    자리표가 있어야 한다.
    """
    from core.render_vivlio.series import middle
    p = os.path.join(middle._auto_dir(), "render.py")
    if not os.path.exists(p):
        pytest.skip("automation 이 이 기계에 없다")
    src = open(p, encoding="utf-8").read()
    assert "def _mkf(" in src
    assert '_mkf(it, "en"' in src and '_mkf(it, "kr"' in src


def test_middle_escape_survives_rich_segments():
    """중등부도 서식 조각을 받아야 한다 — 안 그러면 책 전체가 안 나온다."""
    from core.render_vivlio.series import middle
    p = os.path.join(middle._auto_dir(), "render.py")
    if not os.path.exists(p):
        pytest.skip("automation 이 이 기계에 없다")
    src = open(p, encoding="utf-8").read()
    assert "E = html.escape" not in src, "그대로 두면 서식 조각에서 죽는다"
    assert "def E(s):" in src
    i = src.index("def fit_cls")
    assert "_rtx.plain" in src[i:i + 700], "폭을 잴 때는 글만 꺼내야 한다"


# ── 아홉 계열 모두 지면을 눌러 고칠 수 있다 ────────────────────
@pytest.mark.parametrize("mod", ["blackbook", "whitebook", "pocketbook",
                                 "vocabook", "vocaunit", "special",
                                 "final", "workbook"])
def test_every_series_marks_the_page(mod):
    """자리표가 없으면 지면을 눌러도 **조용히 아무 일이 안 난다.**

    파이널·워크북은 실제로 그랬다(둘 다 `refs.json` 이 안 나왔다).
    """
    import importlib
    r = importlib.import_module("core.render_vivlio.series.%s.render" % mod)
    src = open(r.__file__, encoding="utf-8").read()
    assert "refs" in src, f"{mod}: 자리표를 아예 안 쓴다"
    assert "_refs.mark(" in src or "_refs.stamp(" in src, f"{mod}: 찍는 데가 없다"


def test_refs_can_be_registered_by_hand():
    """`vols` 는 dict, 워크북 `units` 는 목록의 목록 — 목록만 따라가는
    `index_paths()` 로는 못 닿는다. 계열이 경로를 지어 등록한다."""
    from core.render_vivlio import refs
    refs.clear()
    o = {"a": 1}
    refs.put(o, "vols.1.sections.0")
    assert refs.of(o) == "vols.1.sections.0"
    assert refs.of(o, "header") == "vols.1.sections.0.header"


def test_workbook_edits_the_field_that_is_actually_drawn():
    """`runs` 가 있는데 `text` 를 가리키면 **고쳐도 지면이 그대로**다.

    `runs_html` 이 runs 를 먼저 보기 때문이다 — 조용해서 더 나쁘다.
    """
    from core.render_vivlio.series.workbook import render as R
    from core.render_vivlio import refs
    refs.clear()
    b = {"role": "x", "text": "가", "runs": [{"t": "가", "ul": 1}]}
    refs.put(b, "steps.0.groups.0.units.0.0")
    assert R._bref(b).endswith(".runs")
    b2 = {"role": "x", "text": "가"}
    refs.put(b2, "steps.0.groups.0.units.0.1")
    assert R._bref(b2).endswith(".text")


def test_workbook_runs_take_studio_formatting():
    """원고의 `ul` 과 작업대의 `u`·`b`·`st` 를 **둘 다** 그려야 한다."""
    from core.render_vivlio.series.workbook import render as R
    out = R.runs_html({"runs": [{"t": "밑", "ul": 1},
                                {"t": "굵", "b": 1},
                                {"t": "자", "st": {"letter-spacing": "-0.02em"}}]})
    assert "<u>밑</u>" in out and "<b>굵</b>" in out
    assert "letter-spacing:-0.02em" in out


# ── 이름 붙인 단락 스타일 (인디자인의 단락 스타일) ─────────────
def test_named_style_lands_on_the_page_for_every_series():
    """"이 자리에만" 은 그 한 곳뿐이다 — 인디자인의 단락 스타일은 **이름을
    고치면 걸린 곳이 전부** 바뀌는 것이다.

    조판 결과의 class 는 계열 렌더러가 정하므로, 사람이 더 다는 이름은
    `refs.mark()` 가 얹는다 — 계열 코드를 하나도 안 고쳐도 모든 계열에서 된다.
    """
    from core.render_vivlio import refs
    refs.clear()
    refs.set_classes({"a.0": "ps-강조"})
    o = {"x": 1}
    refs.put(o, "a.0")
    assert "ps-강조" in refs.mark(refs.of(o), "head")
    assert "ps-강조" in refs.stamp('<p class="t">글</p>', "a.0")
    refs.set_classes({})


def test_class_ops_are_collected_last_wins():
    """같은 자리를 두 번 지정하면 마지막이 이긴다. 빈 값은 **뗀 것**이다."""
    from core.render_vivlio import edits as ed
    st = {"head": 3, "ops": [
        {"op": "cls", "ref": "a.0", "v": "ps-하나"},
        {"op": "cls", "ref": "a.0", "v": "ps-둘"},
        {"op": "cls", "ref": "b.1", "v": ""},
    ]}
    assert ed.classes(st) == {"a.0": "ps-둘"}


def test_class_ops_do_not_touch_the_manuscript():
    """`cls` 는 글이 아니다 — `apply_all` 이 건드리면 안 된다."""
    from core.render_vivlio import edits as ed
    data = {"a": ["글"]}
    ed.apply_all(data, {"head": 1, "ops": [{"op": "cls", "ref": "a.0",
                                            "v": "ps-강조"}]})
    assert data == {"a": ["글"]}


def test_style_names_must_be_marked_as_ours():
    """계열이 쓰는 클래스(`.q`·`.head`)와 섞이면 어느 쪽이 사람 것인지 모른다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_paraclass")
    assert "^(ps|os|ts)-" in src[i:i + 1600], "이름 규칙이 없다"


def test_classes_survive_a_render_clear():
    """자리표 표는 렌더할 때마다 새로 만든다 — 그때 스타일까지 지우면
    **적용했는데 지면은 그대로**가 된다."""
    from core.render_vivlio import refs
    refs.set_classes({"a.0": "ps-강조"})
    refs.clear()
    assert refs.classes_of("a.0") == "ps-강조"
    refs.set_classes({})


# ── 표 줄·칸을 그 자리에 넣고 뺀다 ──────────────────────────────
def test_rows_and_cols_go_where_you_point():
    from core.render_vivlio import table as T
    b = T.new(3, 3)
    b["head"] = ["가", "나", "다"]
    b["rows"] = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]
    T.add_row(b, 1)
    assert b["rows"][1] == ["", "", ""] and len(b["rows"]) == 4
    T.del_row(b, 0)
    assert b["rows"][0] == ["", "", ""] and len(b["rows"]) == 3
    T.add_col(b, 1)
    assert b["head"][1] == "" and len(b["rows"][0]) == 4
    T.del_col(b, 1)
    assert b["head"] == ["가", "나", "다"]


def test_row_ops_refuse_to_break_a_merged_cell():
    """합친 칸을 가로지르면 칸 수가 어긋나 표가 통째로 밀린다."""
    from core.render_vivlio import table as T
    b = T.new(3, 3)
    b["head"] = None
    b["rows"] = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]
    T.merge(b, 0, 0, 1, 1)
    with pytest.raises(ValueError):
        T.del_row(b, 0)
    with pytest.raises(ValueError):
        T.add_row(b, 1)
    with pytest.raises(ValueError):
        T.del_col(b, 0)


def test_last_row_and_col_are_protected():
    from core.render_vivlio import table as T
    b = T.new(1, 1)
    b["head"] = None
    b["rows"] = [["하나"]]
    with pytest.raises(ValueError):
        T.del_row(b, 0)
    with pytest.raises(ValueError):
        T.del_col(b, 0)


def test_cell_style_keeps_the_text_and_the_merge():
    """칸 하나에 모양을 줘도 **글과 합침을 잃지 않는다**."""
    from core.render_vivlio import table as T
    b = T.new(2, 2)
    b["head"] = None
    b["rows"] = [["가", "나"], ["다", "라"]]
    T.merge(b, 0, 0, 0, 1)
    T.set_cell_style(b, 0, 0, {"background": "#eef"})
    c, r, v = T.span(b["rows"][0][0])
    assert c == 2 and "가" in v
    assert "background:#eef" in T.html(b)


def test_cell_style_comes_off_cleanly():
    """모양도 합침도 없어지면 **민 글로** 돌아간다(찌꺼기가 남으면 안 된다)."""
    from core.render_vivlio import table as T
    b = T.new(2, 1)
    b["head"] = None
    b["rows"] = [["가", "나"]]
    T.set_cell_style(b, 0, 0, {"background": "#eef"})
    T.set_cell_style(b, 0, 0, {"background": ""})
    assert b["rows"][0][0] == "가"


def test_cell_style_is_a_short_list():
    from core.render_vivlio import table as T
    assert "position" not in T.CELL_STYLE and "background" in T.CELL_STYLE
    b = T.new(1, 1)
    b["head"] = None
    b["rows"] = [["가"]]
    with pytest.raises(ValueError):
        T.set_cell_style(b, 0, 0, {"position": "fixed"})


def test_cell_style_refuses_a_covered_slot():
    """옆 칸에 먹힌 자리는 그릴 것이 없다 — 합친 칸을 골라야 한다."""
    from core.render_vivlio import table as T
    b = T.new(2, 1)
    b["head"] = None
    b["rows"] = [["가", "나"]]
    T.merge(b, 0, 0, 0, 1)
    with pytest.raises(ValueError):
        T.set_cell_style(b, 0, 1, {"background": "#eef"})


def test_style_can_be_applied_to_every_hit_at_once():
    """찾은 곳 **전부**에 단락 스타일을 건다(인디자인의 "모두 바꾸기 + 스타일").

    ⚠ 자리마다 연산이 쌓이므로 되돌리기도 한 곳씩 풀린다.
    """
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_paraclass")
    body = src[i:i + 2600]
    assert 'p.get("refs")' in body, "여러 자리를 못 받는다"
    assert "3000" in body, "한 번에 너무 많으면 막아야 한다"
    ui = _studio_src()
    assert "find-cls-go" in ui and "refs: refs" in ui


def test_find_buttons_are_bound_once():
    """두 번 걸려 있어서 "모두 바꾸기" 가 확인 창을 **두 번** 띄우고 두 번 돌았다."""
    ui = _studio_src()
    assert ui.count("$('find-all').addEventListener") == 1
    assert ui.count("$('find-go').addEventListener") == 1


def test_no_button_is_bound_twice():
    """두 번 걸린 단추는 **한 번 눌러도 두 번 돈다.**

    실측: "모두 바꾸기" 가 확인 창을 두 번 띄웠고, 클로드 단추는 같은 부탁을
    두 번 보냈다(돈도 두 배). 조용히 두 번 도는 것이라 여태 몰랐다.
    """
    import collections
    import re as _re
    ui = _studio_src()
    n = collections.Counter(_re.findall(r"\$\('([\w-]+)'\)\.addEventListener", ui))
    dup = {k: v for k, v in n.items() if v > 1}
    assert not dup, f"두 번 걸린 단추: {dup}"


def test_export_says_which_file_it_overwrites():
    """PDF 단추는 책 폴더의 그 PDF 를 **그대로 갈아 끼운다**.

    납품한 책이라면 그것이 바뀐다 — 무엇을 덮어쓰는지 이름을 말해야 한다.
    """
    ui = _studio_src()
    i = ui.index("function exportPdf")
    body = ui[i:i + 900]
    assert "덮어쓸 파일" in body and "thumbInfo.pdf" in body


def test_renaming_a_style_carries_the_places_it_is_applied():
    """스타일 이름만 바꾸고 걸린 자리를 안 바꾸면 **조용히 모양을 잃는다.**"""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_parastyle")
    body = src[i:i + 3000]
    assert 'act == "rename"' in body
    assert 'ed.push(cfg, {"op": "cls"' in body, "걸린 자리를 안 따라간다"


def test_deleting_a_style_takes_it_off_first():
    """규칙부터 지우면 잠깐 "없는 이름이 걸린" 상태가 생긴다 — 떼고 지운다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index('if act == "delete":', src.index("def api_parastyle"))
    body = src[i:i + 800]
    assert body.index('"op": "cls"') < body.index('"op": "style"')


# ── 상자 여러 개 (인디자인의 다중 선택) ────────────────────────
def test_shift_click_adds_to_the_selection():
    """인디자인은 ⇧누르면 더 고른다. 그냥 누른 것도 **묶음의 시작**이다 —
    안 담아 두면 ⇧로 하나 더 골라도 "1개" 가 되어 정렬 단추가 안 나온다."""
    ui = _studio_src()
    assert "function addPick" in ui and "var picks = []" in ui
    i = ui.index("if (ev.shiftKey) { addPick")
    assert "picks = [{ el: hit.el, ref: hit.ref }]" in ui[i:i + 400]


def test_group_align_moves_relatively_and_bakes_once():
    """묶음 정렬도 **기준을 짐작하지 않는다**(잰 자리에서 이만큼 옮겨라).

    ⚠ 상자마다 저장을 부르면 다시 조판이 그만큼 돈다 — 마지막 하나가 끝나면
      **한 번만** 굽는다.
    """
    ui = _studio_src()
    i = ui.index("function alignPicks")
    body = ui[i:i + 3400]
    assert "getBoundingClientRect" in body and "pxPerMm" in body
    assert "if (--left === 0)" in body, "상자마다 다시 굽고 있다"
    assert "el2.style.right" in body, "붙여 둔 변을 지켜야 한다"


def test_no_function_is_defined_twice():
    """같은 함수가 두 번 정의돼 있으면 **어느 것이 도는지** 알 수 없다.

    (실제로 클로드·찾기 묶음이 통째로 두 벌 있었다 — 단추도 두 번 걸렸다.)
    """
    import collections
    import re as _re
    names = _re.findall(r"\n  function (\w+)\(", _studio_src())
    dup = {k: v for k, v in collections.Counter(names).items() if v > 1}
    assert not dup, f"두 번 정의된 함수: {dup}"


def test_no_call_swallows_a_server_error():
    """실패를 삼키면 화면엔 "됐습니다" 만 뜨고 아무 일도 안 일어난다.

    묶음 정렬이 그랬다(이름이 가려져 404 였는데 "맞췄습니다" 만 떴다).
    """
    import re as _re
    ui = _studio_src()
    bad = []
    for m in _re.finditer(r"api\('(/api/book-studio/[a-z-]+)'[^\n]*", ui):
        tail = ui[m.end():m.end() + 420]
        if ".error" not in tail and "ready === false" not in tail:
            bad.append(m.group(1))
    assert not bad, f"응답의 error 를 안 보는 자리: {bad}"


# ── 썸네일이 **지금 보고 있는 판**을 따라온다 ──────────────────
def test_thumbnails_prefer_the_live_build():
    """예전엔 책 폴더의 납품 PDF 만 봤다 — 방금 고친 것이 안 나오고,
    견본일 때는 면 번호까지 어긋나(견본 15면 vs 전권 116면) 그림을 아예
    못 보여 줬다. 지금 판(`build/_thumbs.pdf`)이 있으면 그걸 먼저 본다.
    """
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    assert "def _thumb_pdf" in src and "def _bake_thumbs" in src
    i = src.index("def _thumb_pdf")
    body = src[i:i + 1400]
    assert "_thumbs.pdf" in body and "getmtime" in body, "낡았는지 봐야 한다"
    j = src.index("def _bake_thumbs")
    assert "build/index.html" in src[j:j + 900] or "index.html" in src[j:j + 900]
    assert "cli.run_build" in src[j:j + 900]


def test_thumbnail_bake_never_touches_the_delivered_pdf():
    """썸네일 때문에 납품본이 바뀌면 안 된다 — `build/` 안에만 쓴다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    j = src.index("def _bake_thumbs")
    body = src[j:j + 900]
    assert "out_pdf" not in body and "_build_dir(d)" in body


def test_sample_mode_shows_thumbnails_when_they_match():
    """지금 판에서 구운 그림이면 **견본이어도** 번호가 맞는다."""
    ui = _studio_src()
    i = ui.index("var sampleNow = (scope !== 'full')")
    assert "thumbInfo.live" in ui[i:i + 400]
    j = ui.index("function drawPageNo")
    assert "thumbInfo.live" in ui[j:j + 700], "면수도 지금 판을 따라야 한다"


def test_thumbnails_refresh_after_a_rebuild_but_not_on_every_keystroke():
    """고칠 때마다 구우면 못 쓴다 — 손을 뗀 뒤 한 번만."""
    ui = _studio_src()
    assert "function freshenThumbs" in ui
    i = ui.index("function freshenThumbs")
    assert "setTimeout" in ui[i:i + 400] and "clearTimeout" in ui[i:i + 400]


# ── 포켓북도 글을 고친다 ────────────────────────────────────────
def test_pocketbook_has_a_studio_data_file():
    """이 계열은 원고에서 바로 지면을 만들어 `data.json` 이 없었다 —
    그래서 글을 클릭하면 "여기서 못 고칩니다" 였다.

    조판할 때 **자리표가 가리키는 그 목록**을 남기면 그대로 고칠 수 있다.
    """
    from core.render_vivlio.series.pocketbook import PocketbookSeries
    from core.render_vivlio.series.base import Series
    assert PocketbookSeries.data_path is not Series.data_path
    src = open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                            "pocketbook", "__init__.py"), encoding="utf-8").read()
    assert "_studio_data.json" in src


def test_pocketbook_saves_the_data_before_applying_edits():
    """얹은 뒤를 남기면 다음 조판에서 **또 얹혀 두 번 먹는다**.

    (넣기·지우기는 특히 티가 크다 — 같은 문단이 둘이 된다.)
    """
    src = open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                            "pocketbook", "__init__.py"), encoding="utf-8").read()
    i = src.index('json.dump({"passages": rows}')
    j = src.index("_ed.apply_all", i - 400 if i > 400 else 0)
    assert i < j, "편집을 얹은 뒤에 저장하고 있다"


def test_pocketbook_writes_the_ref_table():
    """지면에 표를 찍어도 **파일로 내지 않으면** 작업대가 못 되짚는다."""
    src = open(os.path.join(_ROOT, "core", "render_vivlio", "series",
                            "pocketbook", "__init__.py"), encoding="utf-8").read()
    assert "_refs3.dump(build_dir)" in src


def test_render_all_is_not_described_as_minutes():
    """"몇 분" 은 **틀린 관찰**이었다(숨은 창의 스로틀링).

    보이는 창에서 재면 전권 116면 3.0초다 — 잘못된 설명은 사람을 막는다.
    """
    ui = _studio_src()
    i = ui.index('id="ide-all"')
    assert "몇 분" not in ui[i:i + 400]
    j = ui.index("veilOn(renderAll ?")
    assert "몇 분" not in ui[j:j + 200]


def test_scope_switch_clears_the_old_thumbnails():
    """견본과 전권은 면 수가 다르다 — 옛 그림이 남으면 번호가 거짓말을 한다
    (전권으로 바꿨는데 "15 / 15" 였다)."""
    ui = _studio_src()
    i = ui.index("function setScope")
    assert "thumbInfo = null" in ui[i:i + 500]


# ── 도형 · 변형 · 획 · 채우기 · 개체 스타일 ─────────────────────
def test_shapes_are_boxes_not_a_new_concept():
    """도형을 따로 만들면 옮기기·크기·정렬·되돌리기를 **또** 만들어야 한다.

    사각형·타원·선은 모양만 다른 **상자**다.
    """
    from core.render_vivlio import box as B
    assert set(B.SHAPES) == {"rect", "ellipse", "line"}
    e = B.new("ellipse")
    assert e["style"]["border-radius"] == "50%" and e["t"] == "box"
    ln = B.new("line")
    assert ln["at"]["height"] == "0mm" and "border-top" in ln["style"]
    assert B.new("text").get("shape") is None


def test_unknown_shape_is_refused():
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    assert "모르는 상자 종류" in src


def test_stroke_and_transform_keys_are_allowed():
    """획을 변마다 따로, 회전·기울이기는 `transform` 한 줄에 조립한다."""
    from core.render_vivlio import box as B
    for k in ("border-top", "border-left", "transform", "filter"):
        assert k in B.STYLE_KEYS
    ui = _studio_src()
    assert "skewX(" in ui and "rotate(" in ui
    assert "linear-gradient(" in ui and "radial-gradient(" in ui


def test_object_styles_ride_the_paragraph_style_road():
    """개체 스타일도 **같은 길**이다 — 이름만 `os-` 로 시작한다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    assert r"^(ps|os|ts)-" in src
    ui = _studio_src()
    i = ui.index("개체 스타일 (인디자인의 오브젝트 스타일)")
    body = ui[i:i + 3000]
    assert "os-" in body and "paraclass" in body


# ── 스포이드 · 자 · 서식으로 찾기 ──────────────────────────────
def test_eyedropper_puts_the_colour_at_the_front():
    """집은 색은 **색상 견본 맨 앞**에 서야 바로 쓴다.

    ⚠ 글자색이 먼저다 — 없으면 그 자리의 바탕을 집는다(둘 다 검정이면 사람이
      무엇을 집었는지 알 수 없다).
    """
    ui = _studio_src()
    assert "function pickColor" in ui and "var picked = []" in ui
    i = ui.index("function swatches")
    assert "picked.map" in ui[i:i + 300], "집은 색이 맨 앞에 안 선다"


def test_ruler_measures_in_mm_not_pixels():
    """확대·축소해도 값이 같아야 한다 — 화면 px 이 아니라 지면 mm."""
    ui = _studio_src()
    i = ui.index("function rulerClick")
    body = ui[i:i + 900]
    assert "pxPerMm(pg)" in body and "round2(" in body
    assert "clientX" in body


def test_tools_that_are_not_selectors_are_intercepted_first():
    """스포이드·자는 고르는 도구가 아니다 — 클릭을 먼저 가로챈다."""
    ui = _studio_src()
    i = ui.index("st.addEventListener('click'")
    body = ui[i:i + 500]
    assert "tool === 'pick'" in body and "tool === 'ruler'" in body


def test_find_by_style_reads_the_built_html_not_the_screen():
    """지면에서 찾으면 **지금 그려진 면만** 본다 — 조판한 HTML 을 훑는다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_findstyle")
    body = src[i:i + 2200]
    assert "index.html" in body and "data-ref=" in body
    assert "500" in body, "너무 많으면 끊어야 한다"


def test_place_rules_outweigh_the_series_theme():
    """`[data-ref="…"]` 은 클래스와 무게가 같다(0,1,0) — 테마의 `.pbox p`
    (0,1,1) 하나에도 진다. 그러면 "반영했습니다" 만 뜨고 지면은 그대로다.

    ⚠ `!important` 로 밀면 그 책에서 무엇으로도 못 덮는다 → **같은 선택자를
      세 번 겹쳐** 무게만 올린다(뜻은 그대로).
    """
    from core.render_vivlio import knobs as kn
    got = kn._strong('[data-ref="a.0"]')
    assert got.count('[data-ref="a.0"]') == 3
    assert kn._strong('[data-ref="a.0"]::after').endswith("::after")
    assert kn._strong(".pbox") == ".pbox", "다른 선택자는 건드리지 않는다"


def test_char_panel_covers_underline_kinds_and_emphasis():
    """밑줄은 한 종류가 아니다(물결·점선·겹줄·취소선), 굵기·색·내림도 따로."""
    ui = _studio_src()
    i = ui.index("var CHAR_PROPS")
    body = ui[i:i + 3000]
    for k in ("underline wavy", "line-through", "text-decoration-thickness",
              "text-underline-offset", "text-emphasis"):
        assert k in body, k


def test_para_panel_covers_korean_line_breaking():
    """한글 조판은 금칙·낱말 자르기·마지막 줄 정렬을 자주 손댄다."""
    ui = _studio_src()
    i = ui.index("var PARA_PROPS")
    body = ui[i:i + 2600]
    for k in ("line-break", "word-break", "text-align-last", "text-justify"):
        assert k in body, k


def test_new_length_props_are_unit_checked():
    """`text-underline-offset: 3` 은 CSS 가 통째로 무시한다 — 미리 잡는다."""
    from routes.book_studio import _needs_unit
    assert _needs_unit("text-underline-offset", "3")
    assert not _needs_unit("text-underline-offset", "0.16em")


# ── 각주 (인디자인의 각주) ──────────────────────────────────────
def test_footnote_rides_the_segment_and_comes_back():
    """각주는 **글이 아니라 딸린 것**이다 — 빈 조각에 실어 둔다.

    그 자리에는 번호만 서고 글은 면 아래로 내려간다(번호는 조판 엔진이 센다).
    """
    from core.render_vivlio import richtext as rt
    seg = [{"t": "본문 "}, {"t": "", "fn": "출처: 교과서"}, {"t": "이어서"}]
    h = rt.to_html(seg)
    assert 'class="viv-fn"' in h
    back = rt.from_html(h)
    assert back[1]["fn"] == "출처: 교과서"
    assert "출처" not in rt.plain(back), "각주는 본문 글이 아니다"


def test_footnote_css_only_for_books_that_use_it():
    """안 쓰는 책의 CSS 가 까닭 없이 달라지면 회귀 대조가 흐려진다."""
    src = open(os.path.join(_ROOT, "core", "render_vivlio", "knobs.py"),
               encoding="utf-8").read()
    assert 'foot_css() if _has(cfg, "fn")' in src
    from core.render_vivlio import richtext as rt
    assert "float: footnote" in rt.FOOT_CSS


@pytest.mark.parametrize("mod,fn", [("blackbook", "inl"), ("whitebook", "inl")])
def test_series_render_footnotes_too(mod, fn):
    """계열이 제 손으로 조각을 그리면 각주도 제 손으로 붙여야 한다."""
    import importlib
    r = importlib.import_module("core.render_vivlio.series.%s.render" % mod)
    out = getattr(r, fn)([{"t": "글", "fn": "출처"}])
    assert "viv-fn" in out


def test_workbook_runs_render_footnotes():
    from core.render_vivlio.series.workbook import render as R
    assert "viv-fn" in R.runs_html({"runs": [{"t": "글", "fn": "출처"}]})


# ── 빈 면 넣기 ────────────────────────────────────────────────────────────
def test_글목록과_블록목록을_다르게_본다():
    """낱말 기록 목록은 **블록은 받아도 글은 못 받는다**.

    실측: `lessons.0.vocab` 에 빈칸 한 글자를 넣었더니 렌더러가
    `unit["label"]` 에서 통째로 멎었다.
    """
    from core.render_vivlio.series.base import text_like, para_like
    rec = [{"en": "band", "kr": "밴드"}]
    assert para_like(rec) is True          # 표·상자는 끼울 수 있다
    assert text_like(rec) is False         # 글은 안 된다
    assert text_like(["가", "나"]) is True
    assert text_like([{"t": "가", "b": 1}]) is True   # 서식 조각도 글이다


def test_빈면은_원고를_안_건드린다():
    """빈 면은 `::before` 한 줄이다 — data 는 한 글자도 안 바뀐다."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_blankpage")
    body = src[i:i + 2500]
    assert '"op": "style"' in body
    assert "::before" in body
    assert '"op": "insert"' not in body, "빈 면이 원고에 글을 끼우면 안 된다"


def test_빈면_면머리면_앞나눔을_안_준다():
    """이미 면 꼭대기인 자리에 앞쪽 나눔을 주면 **두 면**이 생긴다(실측)."""
    src = open(os.path.join(_ROOT, "routes", "book_studio.py"),
               encoding="utf-8").read()
    i = src.index("def api_blankpage")
    body = src[i:i + 2500]
    assert "attop" in body
    j = body.index("if not at_top")
    assert "break-before" in body[j:j + 120]
    assert "break-after" in body[:j], "뒤쪽 나눔은 늘 준다"


def test_측정조판은_빈면을_끈다():
    """측정은 한 면에 한 항목 — 빈 면이 끼면 항목 수와 면 수가 어긋난다."""
    from core.render_vivlio import measure
    src = open(os.path.join(_ROOT, "core", "render_vivlio", "measure.py"),
               encoding="utf-8").read()
    assert "_mute_page_effects(html_path)" in src
    assert src.index("_mute_page_effects(html_path)") < src.index("cli.run_build")
    # 꾸밈은 살리고 **면을 만드는 성질만** 끈다
    assert "content:none" not in measure._MUTE
    for k in ("break-before:auto", "break-after:auto", "height:auto"):
        assert k in measure._MUTE
