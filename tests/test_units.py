# -*- coding: utf-8 -*-
"""디자인 단위 — 시드가 스키마에 맞고, 원자 → SVG 가 그려지고, PDF 한 면이 원자로 분해된다."""
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """리포 시드를 임시 카탈로그로 복사해 읽는다 — 저장 시험이 리포 파일을 건드리지 않게."""
    import shutil
    src = os.path.join(REPO, "catalog", "_units")
    dst = tmp_path / "catalog" / "_units"
    shutil.copytree(src, dst)
    from core.units import store
    monkeypatch.setattr(store, "CATALOG", str(tmp_path / "catalog"))
    return store.library()


def test_seed_matches_schema(lib):
    from core.units import store
    for kind, items in lib.items():
        assert items, kind
        for it in items:
            assert store.validate(kind, it) is None, (kind, it.get("id"), store.validate(kind, it))


def test_validate_rejects(lib):
    from core.units import store
    assert store.validate("blocks", {"id": "x", "name": "x", "source": "content", "fields": {}, "variants": []})
    assert store.validate("parts", {"id": "Bad-Id", "name": "x", "w": 1, "h": 1, "atoms": []})
    assert "토큰" not in (store.validate("parts", {"id": "p", "name": "x", "w": 10, "h": 5, "atoms": [
        {"t": "text", "x": 0, "y": 0, "w": 10, "h": 5, "font": "$body", "size": 8}]}) or "")


def test_store_put_delete(lib):
    from core.units import store
    store.put("specs", {"id": "zz", "w": 100, "h": 100})
    assert store.get("specs", "zz")["w"] == 100
    assert store.delete("specs", "zz")
    assert store.get("specs", "zz") is None


def test_part_render_grows_and_keeps_circles(lib):
    from core.units import render, store
    skin = store.by_id(lib["skins"])["d2"]
    ctx = render.Ctx(skin, lib)
    part = store.by_id(lib["parts"])["gox_row"]
    frag, h = render.part_svg(ctx, part, {"no": 1, "sentence": "short"}, {"sentence": "rich"})
    assert h == part["h"]
    long = "word " * 80
    frag2, h2 = render.part_svg(ctx, part, {"no": 1, "sentence": long}, {"sentence": "rich"})
    assert h2 > h                                           # 글이 길면 부품이 자란다
    assert 'rx="2.500" ry="2.500"' in frag2                 # 옆의 O/X 원은 늘어나지 않는다
    assert not ctx.warnings


def test_missing_token_warns(lib):
    from core.units import render
    ctx = render.Ctx({"id": "empty", "tokens": {}}, lib)
    part = {"id": "p", "name": "p", "w": 10, "h": 5, "atoms": [{"t": "rect", "x": 0, "y": 0, "w": 10, "h": 5, "fill": "$nope"}]}
    svg = render.part_standalone(ctx, part)
    assert "#ff00ff" in svg and any("$nope" in w for w in ctx.warnings)


def test_plan_pages_and_columns(lib):
    from core.units import render, store
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib, {"title": "T", "tag": "TAG"})
    pages = render.plan_svgs(ctx, store.by_id(lib["plans"])["workbook_mini"], lib["sets"], lib)
    assert [p["label"] for p in pages] == ["앞", "STEP 2 간지", "STEP 2 · 20", "STEP 2 · 21"]
    assert pages[2]["page_no"] == 3 and ">3<" in pages[2]["svg"]          # 쪽번호가 이어진다
    exam = render.plan_svgs(ctx, store.by_id(lib["plans"])["exam_sheet"], lib["sets"], lib)
    assert len(exam) == 2 and "creativity" in exam[0]["svg"] and "cars" in exam[1]["svg"]   # 슬롯 모드: 세트마다 한 면, 값이 자리에 들어간다
    assert not ctx.warnings, ctx.warnings


def test_skin_variant_switch(lib):
    from core.units import render, store
    blk = store.by_id(lib["blocks"])["gram_ox"]
    d2 = render.block_standalone(render.Ctx(store.by_id(lib["skins"])["d2"], lib), blk)
    mono = render.block_standalone(render.Ctx(store.by_id(lib["skins"])["mono"], lib), blk)
    assert "<ellipse" in d2 and "고쳐 쓰기" in mono                       # 옷이 모양(v2)을 고른다


def test_decompose_pdf(tmp_path):
    import fitz
    from core.units import decompose
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)                            # A4 pt
    page.draw_rect(fitz.Rect(56, 100, 540, 200), color=None, fill=(0.96, 0.95, 0.9))
    page.draw_line(fitz.Point(56, 220), fitz.Point(540, 220), color=(0.7, 0.7, 0.7), width=0.8)
    page.insert_text(fitz.Point(60, 130), "Many people believe that creativity is a gift.", fontsize=9, color=(0.1, 0.1, 0.1))
    page.insert_text(fitz.Point(60, 143), "Research shows it can be trained like any skill.", fontsize=9, color=(0.1, 0.1, 0.1))
    page.insert_text(fitz.Point(60, 250), "01", fontsize=11, color=(0, 0.33, 0.62))
    p = tmp_path / "t.pdf"
    doc.save(str(p))
    dec = decompose.from_pdf(str(p), 1)
    kinds = sorted(a["t"] for a in dec["atoms"])
    assert kinds == ["line", "rect", "text", "text"]                      # 두 줄이 한 단락으로 합쳐진다
    assert abs(dec["w"] - 210) < 0.5 and abs(dec["h"] - 297) < 0.5
    para = next(a for a in dec["atoms"] if a["t"] == "text" and "creativity" in a["text"])
    assert "trained" in para["text"] and para["font"].startswith("$f") and para["color"].startswith("$c")
    assert dec["tokens"]["color"] and dec["tokens"]["font"]
    assert len(dec["parts"]) == 3                                         # 상자+단락 / 선 / 번호 (세로 3mm 넘게 떨어지면 다른 후보)
    part = decompose.to_part(dec, dec["parts"][0]["atoms"], "cand", "후보")
    assert part["atoms"][0]["x"] == 0 and part["atoms"][0]["y"] == 0


def test_free_items_canvas_vs_flow(lib):
    """자유 배치 요소: 캔버스는 견본 값, 책(세트)에선 슬롯에 세트 값, 세트가 없으면 system 블록만."""
    from core.units import render, store
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib, {"title": "T", "tag": "TAG"})
    pg = store.by_id(lib["pages"])["pair"]
    assert any(it.get("block") == "passage" for it in pg["items"])
    canvas = render.page_canvas_svgs(ctx, pg, render.DEFAULT_SPEC)[0]["svg"]
    flow = render.page_svgs(ctx, pg, lib["sets"][:1], render.DEFAULT_SPEC)[0]["svg"]
    assert canvas.count("data-fi=") == len(pg["items"]) and 'class="zone"' not in canvas
    assert flow.count("data-fi=") == len(pg["items"]) and "creativity" in flow   # 세트 20의 값이 자리에 끼워진다
    empty = render.page_svgs(ctx, pg, [], render.DEFAULT_SPEC)[0]["svg"]
    assert empty.count("data-fi=") == 2                                        # 세트가 없으면 머리말·쪽번호만
    assert not ctx.warnings, ctx.warnings


def test_atom_kinds_cover_indesign_objects(lib):
    """원자 = 인디자인 오브젝트 전부: 도형(path)·회전·불투명·선 끝·그림 맞춤·글 안의 서식 조각이 스키마에 맞고 SVG 로 그려진다."""
    from core.units import render, store
    part = {"id": "all", "name": "all", "w": 60, "h": 40, "atoms": [
        {"t": "path", "x": 0, "y": 0, "w": 12, "h": 8, "d": "M0 0.3 L0.6 0.3 L0.6 0 L1 0.5 L0.6 1 L0.6 0.7 L0 0.7 Z", "fill": "$sel", "rotate": 45, "opacity": 0.5},
        {"t": "line", "x1": 0, "y1": 12, "x2": 30, "y2": 12, "stroke": {"w": 1, "color": "$rule", "cap": "round"}},
        {"t": "image", "x": 20, "y": 0, "w": 10, "h": 10, "src": "logo", "fit": "cover", "rotate": -90},
        {"t": "text", "x": 0, "y": 15, "w": 60, "h": 5, "font": "$body", "size": 8, "color": "$ink",
         "text": ["The ", {"t": "boy", "b": True, "color": "$sel"}, {"t": "2", "sup": True}, " who"]},
    ]}
    assert store.validate("parts", part) is None
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib)
    frag, _h = render.part_svg(ctx, part)
    assert '<path d="M 0.000 2.400 L 7.200 2.400' in frag and 'rotate(45.00 6.000 4.000)' in frag and 'opacity="0.500"' in frag
    assert 'stroke-linecap="round"' in frag
    assert 'rotate(-90.00 25.000 5.000)' in frag
    assert "<b>boy</b>" in frag and "<sup>2</sup>" in frag and "color:#00559f" in frag
    assert not [w for w in ctx.warnings if "이미지 없음" not in w], ctx.warnings


def test_decompose_keeps_indesign_objects(tmp_path):
    """인디자인 PDF 에 실제로 있는 것을 잃지 않는다 — 삼각형은 path 로, 둥근 모서리는 반지름으로, 반투명·둥근 선 끝·회전한 글·그림·굵은 조각까지."""
    import fitz
    from core.units import decompose, store
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(56, 100, 300, 200), color=None, fill=(0.2, 0.4, 0.8), fill_opacity=0.5)
    page.draw_polyline([fitz.Point(320, 100), fitz.Point(400, 150), fitz.Point(320, 200)], color=None, fill=(1, 0, 0), closePath=True)
    page.draw_line(fitz.Point(56, 220), fitz.Point(300, 220), color=(0.7, 0.7, 0.7), width=2, lineCap=1)
    page.draw_rect(fitz.Rect(56, 240, 300, 300), color=(0, 0, 0), width=1, radius=0.2)
    page.draw_oval(fitz.Rect(320, 240, 420, 300), color=(0, 0, 1), width=1)
    tw = fitz.TextWriter(page.rect)
    tw.append(fitz.Point(60, 130), "Plain ", font=fitz.Font("helv"), fontsize=9)
    tw.append(fitz.Point(60 + fitz.Font("helv").text_length("Plain ", 9), 130), "Bold", font=fitz.Font("hebo"), fontsize=9)   # 한 줄에 잇달아
    tw.write_text(page, color=(0.1, 0.1, 0.1))
    page.insert_text(fitz.Point(500, 400), "Vertical tab", fontsize=10, rotate=90)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), 0)
    page.insert_image(fitz.Rect(100, 500, 200, 550), pixmap=pix, rotate=90)
    p = tmp_path / "t.pdf"
    doc.save(str(p))
    dec = decompose.from_pdf(str(p), 1)
    by = {}
    for a in dec["atoms"]:
        by.setdefault(a["t"], []).append(a)
    assert sorted(by) == ["ellipse", "image", "line", "path", "rect", "text"]
    assert by["rect"][0]["opacity"] == 0.5 and "radius" in by["rect"][1] and abs(by["rect"][1]["radius"] - 4.23) < 0.1
    tri = by["path"][0]
    assert tri["d"].startswith("M 0.0000 0.0000 L 1.0000 0.5000 L 0.0000 1.0000") and tri["fill"].startswith("$c")
    assert by["line"][0]["stroke"]["cap"] == "round"
    assert by["image"][0]["rotate"] == -90.0 and abs(by["image"][0]["w"] - 17.64) < 0.1     # 돌린 그림은 원래 폭·높이 + 회전
    vert = next(a for a in by["text"] if a.get("rotate"))
    assert vert["rotate"] == -90.0 and vert["w"] > vert["h"]                                 # 세로 글도 원래 폭·높이 + 회전
    mixed = next(a for a in by["text"] if isinstance(a["text"], list))
    assert mixed["text"][0] == "Plain " and mixed["text"][1]["t"] == "Bold" and mixed["text"][1]["b"] is True
    part = decompose.to_part(dec, list(range(len(dec["atoms"]))), "all", "all")
    assert store.validate("parts", part) is None


def test_text_atom_paragraph_and_frame_options(lib):
    """글 원자 = 인디자인 단락·문자 스타일 + 텍스트 프레임 옵션: 자간·들여쓰기·내어쓰기·단락 간격·안쪽 여백·세로 정렬·다단·취소선."""
    from core.units import render, store
    a = {"t": "text", "x": 0, "y": 0, "w": 60, "h": 20, "font": "$body", "size": 8, "color": "$ink",
         "text": ["① The boy ", {"t": "who", "u": True}, " I met\n② ", {"t": "gone", "s": True}, " away"],
         "tracking": 50, "indent": 4, "indent_first": -4, "indent_right": 1, "space_before": 1, "space_after": 0.5,
         "inset": [1, 2, 1, 2], "valign": "center", "columns": 2, "gutter": 3}
    part = {"id": "t", "name": "t", "w": 60, "h": 20, "atoms": [a]}
    assert store.validate("parts", part) is None
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib)
    frag, _h = render.part_svg(ctx, part)
    assert "white-space:normal;letter-spacing:0.0500em" in frag
    assert frag.count("<p ") == 2 and "padding-left:4.000px;padding-right:1.000px;text-indent:-4.000px;margin-top:1.000px;margin-bottom:0.500px" in frag
    assert "padding:1.000px 2.000px 1.000px 2.000px" in frag and "justify-content:center" in frag
    assert "column-count:2;column-gap:3.000px" in frag
    assert "<u>who</u>" in frag and "<s>gone</s>" in frag
    assert not ctx.warnings, ctx.warnings
    # 높이 어림: 여백·단락 간격이 더해진다
    assert render.text_h("a\nb", 60, 8, None, {"space_after": 2, "inset": 1}) == render.text_h("a\nb", 60, 8) + 2 + 2


def test_decompose_underline_paragraph_hanging(tmp_path):
    """밑줄은 선 원자가 아니라 글 조각(u), 끝이 이른 줄 다음은 새 단락, 둘째 줄부터 들여 있으면 내어쓰기. 제목 밑 긴 괘선은 그대로 선."""
    import fitz
    from core.units import decompose
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    font = fitz.Font("helv")
    # 1) 밑줄 친 단어 — 글자 바로 밑 얇은 선
    page.insert_text(fitz.Point(60, 100), "Choose the wrong one here.", fontsize=9, fontname="helv")
    x0 = 60 + font.text_length("Choose the ", 9)
    x1 = x0 + font.text_length("wrong", 9)
    page.draw_line(fitz.Point(x0, 101.2), fitz.Point(x1, 101.2), color=(0, 0, 0), width=0.5)
    # 2) 제목 밑 긴 괘선 — 밑줄 아님
    page.insert_text(fitz.Point(60, 130), "STEP 1", fontsize=9, fontname="helv")
    page.draw_line(fitz.Point(56, 132), fitz.Point(540, 132), color=(0.5, 0.5, 0.5), width=0.5)
    # 3) 내어쓰기 + 단락: 첫 줄은 번호부터, 둘째 줄은 들여서. 짧게 끝난 뒤 다음 줄은 새 단락
    page.insert_text(fitz.Point(60, 200), "1. The quick brown fox jumps over the lazy dog and keeps running far", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(72, 212), "beyond the hill.", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(60, 224), "2. Second item that is short.", fontsize=9, fontname="helv")
    p = tmp_path / "t.pdf"
    doc.save(str(p))
    dec = decompose.from_pdf(str(p), 1)
    texts = [a for a in dec["atoms"] if a["t"] == "text"]
    ul = next(a for a in texts if "Choose" in (a["text"] if isinstance(a["text"], str) else "".join(r if isinstance(r, str) else r["t"] for r in a["text"])))
    assert isinstance(ul["text"], list) and {"t": "wrong", "u": True} in ul["text"]
    assert sum(1 for a in dec["atoms"] if a["t"] == "line") == 1                       # 밑줄은 사라지고 괘선만 남는다
    hang = next(a for a in texts if a.get("indent"))
    assert hang["indent_first"] == -hang["indent"] and abs(hang["indent"] - 12 * 25.4 / 72) < 0.3
    assert hang["text"].count("\n") == 1 and hang["text"].split("\n")[1].startswith("2.")   # 짧게 끝난 줄 다음 = 새 단락
    assert hang["x"] == pytest.approx(60 * 25.4 / 72, abs=0.1)
