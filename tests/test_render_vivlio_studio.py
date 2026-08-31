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


# ── 작업대 API 방어선 ───────────────────────────────────────────
@pytest.fixture()
def client():
    os.environ.setdefault("YONE_SECRET_KEY", "test-only")
    import app as A
    for key in list(A.app.before_request_funcs):
        A.app.before_request_funcs[key] = [
            f for f in A.app.before_request_funcs[key]
            if f.__name__ != "check_auth"]
    A.app.config["TESTING"] = True
    return A.app.test_client()


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
