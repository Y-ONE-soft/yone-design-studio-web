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
    assert len(exam) == 1 and exam[0]["svg"].count('data-set="') == 15   # 두 세트 15블록이 2단 한 면에 다 들어간다
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
