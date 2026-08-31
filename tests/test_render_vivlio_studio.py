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


@pytest.mark.parametrize("name,needle", [
    ("blackbook", "_refs.index("),
    ("vocabook", "_refs.index_paths("),
    ("vocaunit", "_refs.index("),
    ("special", "_refs.dump("),
])
def test_every_series_makes_refs(name, needle):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "core", "render_vivlio", "series", name, "render.py")
    src = io.open(p, encoding="utf-8").read()
    assert needle in src, f"{name}: 자리표를 안 만든다"
    assert "_refs.dump(" in src, f"{name}: 번호↔경로 표를 안 낸다"


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
