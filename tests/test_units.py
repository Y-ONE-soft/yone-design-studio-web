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
    assert [p["label"] for p in pages] == ["앞", "STEP 2 간지", "STEP 2 · 20", "STEP 2 · 21", "정답 간지", "정답"]
    assert pages[2]["page_no"] == 3 and ">3<" in pages[2]["svg"]          # 쪽번호가 이어진다
    ans = pages[-1]["svg"]
    assert ans.count("data-fi=") == 5 and "replaced" in ans and "④" in ans    # 정답지: 세트 2개의 정답 줄이 쌓인다 (머리말·쪽번호·제목 + 2)
    exam = render.plan_svgs(ctx, store.by_id(lib["plans"])["exam_sheet"], lib["sets"], lib)
    assert len(exam) == 2 and "creativity" in exam[0]["svg"] and "cars" in exam[1]["svg"]   # 슬롯 모드: 세트마다 한 면, 값이 자리에 들어간다
    assert not [w for w in ctx.warnings if not w.startswith("원고")], ctx.warnings          # 원고↔자리 불일치는 검수 항목(시드는 두 종류를 섞어 둠)


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
    assert not [w for w in ctx.warnings if not w.startswith("원고")], ctx.warnings
    # 세트 20 엔 빈칸·본문 O/X 가 없다 → 그 자리는 견본 글이 아니라 **빈 채** + 검수 error. 어법 O/X 3줄은 자리가 없어 안 실림
    assert "r_____" not in flow and "Wide roads" not in flow
    assert any("빈칸 줄 자리에 넣을 원고가 없다" in w for w in ctx.warnings) and any("어법 O/X 줄 3개가" in w for w in ctx.warnings)


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


def test_gradient_corners_and_image_crop_render(lib):
    """그라디언트·모서리 4개·틀 안 그림 자리(자르기)가 스키마에 맞고 SVG 로 그려진다."""
    from core.units import render, store
    part = {"id": "g", "name": "g", "w": 60, "h": 40, "atoms": [
        {"t": "rect", "x": 0, "y": 0, "w": 30, "h": 10, "radius": [2, 0, 2, 0], "gradient": {"angle": 90, "stops": [{"c": "$s1"}, {"c": "$white"}]}},
        {"t": "ellipse", "x": 32, "y": 0, "w": 10, "h": 10, "gradient": {"type": "radial", "stops": [{"c": "$white", "at": 0}, {"c": "$sel", "at": 1}]}},
        {"t": "image", "x": 0, "y": 15, "w": 20, "h": 10, "src": "logo", "img": {"x": -5, "y": -2, "w": 30, "h": 14}},
    ]}
    assert store.validate("parts", part) is None
    skin = dict(store.by_id(lib["skins"])["d2"])
    skin["images"] = {"logo": "x.png"}
    ctx = render.Ctx(skin, lib)
    frag, _h = render.part_svg(ctx, part)
    assert '<linearGradient id="u1" gradientTransform="rotate(90.0 0.5 0.5)">' in frag and 'fill="url(#u1)"' in frag
    assert '<path d="M 2.000 0.000' in frag                                   # 모서리가 다르면 path
    assert '<radialGradient id="u2">' in frag and 'offset="100.0%" stop-color="#00559f"' in frag
    assert '<clipPath id="u3"><rect x="0" y="15.000" width="20" height="10.000"/></clipPath>' in frag
    assert '<image x="-5.000" y="13.000" width="30.000" height="14.000"' in frag and 'clip-path="url(#u3)"' in frag
    assert not ctx.warnings, ctx.warnings


def test_decompose_corner_radii_and_cropped_image(tmp_path):
    """둥근 네모는 모서리마다 재고(다르면 4개), 틀로 잘린 그림은 틀 + 그림 전체 자리(img)로."""
    import fitz
    from core.units import decompose
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(56, 240, 300, 300), color=(0, 0, 0), width=1, radius=(0.05, 0.2))   # 가로 5% · 세로 20% → 네 모서리 같은 값
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), 0)
    page.insert_image(fitz.Rect(100, 500, 200, 550), pixmap=pix)
    xref = page.get_contents()[-1]                                                   # 그림을 그린 스트림
    src = doc.xref_stream(xref).decode("latin-1")
    assert "Do" in src
    doc.update_stream(xref, ("q 120 292 60 35 re W n " + src + " Q").encode("latin-1"))   # 틀 120..180 × (842-327)..(842-292) 로 자른다
    p = tmp_path / "t.pdf"
    doc.save(str(p))
    dec = decompose.from_pdf(str(p), 1)
    rect = next(a for a in dec["atoms"] if a["t"] == "rect")
    assert isinstance(rect["radius"], (int, float)) and abs(rect["radius"] - 12 * 25.4 / 72) < 0.3
    img = next(a for a in dec["atoms"] if a["t"] == "image")
    assert abs(img["w"] - 60 * 25.4 / 72) < 0.2 and abs(img["h"] - 35 * 25.4 / 72) < 0.2        # 틀 = 보이는 자리
    assert abs(img["img"]["x"] - (-20 * 25.4 / 72)) < 0.2 and abs(img["img"]["w"] - 100 * 25.4 / 72) < 0.2   # 그림 전체는 틀 왼쪽 위 기준


def test_group_by_box_row_and_column():
    """후보 묶기: 상자 안에 든 것 · 같은 줄(문장 + O/X) · 가까이 쌓인 것은 하나로, 단(세로 괘선 건너·키 큰 것끼리)과 가장자리 장식은 갈라진다."""
    from core.units import decompose
    atoms = [
        {"t": "rect", "x": 20, "y": 20, "w": 170, "h": 30, "fill": "$cream"},                        # 0 지문 상자
        {"t": "text", "x": 22, "y": 22, "w": 160, "h": 20, "font": "$body", "size": 9, "text": "passage"},   # 1 안의 글
        {"t": "text", "x": 20, "y": 60, "w": 120, "h": 4, "font": "$body", "size": 9, "text": "sentence 1"},  # 2 문장
        {"t": "rect", "x": 150, "y": 60, "w": 20, "h": 4, "stroke": {"w": 0.3, "color": "$rule"}},   # 3 O/X 상자
        {"t": "text", "x": 152, "y": 60, "w": 5, "h": 4, "font": "$body", "size": 8, "text": "O"},        # 4 그 안
        {"t": "text", "x": 20, "y": 72, "w": 120, "h": 4, "font": "$body", "size": 9, "text": "sentence 2"},  # 5 다음 줄(8mm 아래)
        {"t": "text", "x": 20, "y": 90, "w": 60, "h": 4, "font": "$body", "size": 9, "text": "prompt"},      # 6 발문
        {"t": "text", "x": 20, "y": 95, "w": 60, "h": 12, "font": "$body", "size": 9, "text": "choices"},    # 7 바로 밑 선지(1mm)
        {"t": "line", "x1": 105, "y1": 85, "x2": 105, "y2": 130, "stroke": {"w": 0.3, "color": "$rule"}},  # 8 단 나눔 세로 괘선
        {"t": "text", "x": 110, "y": 90, "w": 60, "h": 4, "font": "$body", "size": 9, "text": "right col"},  # 9 오른쪽 단, 같은 높이
        {"t": "rect", "x": 200, "y": 60, "w": 10, "h": 30, "fill": "$s1"},                          # 10 오른쪽 가장자리 탭
    ]
    parts = decompose.group({"w": 210, "h": 297, "atoms": atoms})
    sets = [set(p["atoms"]) for p in parts]
    assert {0, 1} in sets and {2, 3, 4} in sets and {5} in sets and {6, 7} in sets
    assert {9} in sets and {8} in sets and {10} in sets


def test_overflow_threads_to_next_page(lib):
    """긴 지문 → 면 아래로 넘치면 다음 면으로 이어 흐른다 (인디자인 스레드)."""
    import copy
    from core.units import render, store
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib, {"title": "T", "tag": "TAG"})
    pg = store.by_id(lib["pages"])["pair"]
    s = copy.deepcopy(lib["sets"][1])
    for b in s["blocks"]:
        if b["block"] == "passage":
            b["fields"]["passage"] = (render.rich_plain(b["fields"]["passage"]) + " ") * 12
    out = render.page_svgs(ctx, pg, [s], render.DEFAULT_SPEC)
    assert len(out) >= 2 and "이어서" in out[1]["label"]
    assert not any("넘친다" in w for w in ctx.warnings)
    # 첫 면 = 머리말·쪽번호·번호·지문 앞부분, 다음 면 = 지문 뒷부분 + 문항들 (전부 한 번씩)
    assert out[0]["svg"].count("data-fi=") == 4 and out[1]["svg"].count("data-fi=") == 9
    assert "planners" in out[-1]["svg"]
    # 짧은 지문은 한 면
    assert len(render.page_svgs(ctx, pg, lib["sets"][1:2], render.DEFAULT_SPEC)) == 1


def test_manuscript_text_to_sets(lib):
    """붙여넣은 원고 → 블록 자리 이름에 맞춘 세트."""
    from core.units import manuscript, store
    with open(os.path.join(REPO, "tests", "fixtures", "manuscript_sample.txt"), encoding="utf-8") as fh:
        sets, log = manuscript.from_text(fh.read(), lib["blocks"])
    assert log == [] and [s["id"] for s in sets] == ["21", "22"]
    b = {x["block"]: x["fields"] for x in sets[0]["blocks"]}
    assert b["pnum"]["pnum"] == "21" and b["passage"]["passage"].startswith("The idea") and "\n" in b["passage"]["passage"]
    assert b["prompt"]["prompt"].endswith("?") and len(b["choices"]["choices"]) == 5 and b["choices"]["answer"] == "③"
    assert b["blank"]["kr"].startswith("넓은") and b["blank"]["answer"] == "replaced"
    ox = [x["fields"] for x in sets[0]["blocks"] if x["block"] == "ox"]
    assert [o["answer"] for o in ox] == [False, True]
    b2 = {x["block"]: x["fields"] for x in sets[1]["blocks"]}
    assert b2["prompt"]["no"] == 2 and b2["gram_ox"]["answer"] == "X"
    for s in sets:
        assert store.validate("sets", s) is None


def test_manuscript_contents_to_sets(lib):
    """contents JSON(yos-workbook-v1) → 항목마다 세트, 못 맞춘 항목은 log."""
    from core.units import manuscript
    with open(os.path.join(REPO, "tests", "fixtures", "yos_workbook_v1.json"), encoding="utf-8") as fh:
        sets, log = manuscript.from_contents(json.load(fh), lib["blocks"])
    kinds = [s["kind"] for s in sets]
    assert kinds[0] == "passage" and "content-ox" in kinds and "vocab-blank" in kinds and "grammar-fix" in kinds
    assert len({s["id"] for s in sets}) == len(sets)                       # id 유일
    ox = next(s for s in sets if s["kind"] == "content-ox")
    assert [b["fields"]["answer"] for b in ox["blocks"] if b["block"] == "ox"][:2] == [True, False]
    fix = next(s for s in sets if s["kind"] == "grammar-fix")
    assert any(isinstance(b["fields"]["sentence"], list) for b in fix["blocks"] if b["block"] == "gram_ox")   # 밑줄 조각
    assert any("순서배열" in x for x in log)


def test_manuscript_api(lib, monkeypatch, tmp_path):
    monkeypatch.setenv("YONE_STUDIO_ROOT", str(tmp_path))
    import importlib
    import studio_server
    importlib.reload(studio_server)
    c = studio_server.create_app().test_client()
    r = c.post("/api/units/manuscript?save=1", json={"text": "# 7\nThis is a passage long enough to be recognised as the English body text of a set.\n윗글의 주제는?\n① a ② b\n답: ②"})
    j = r.get_json()
    assert r.status_code == 200 and j["sets"][0]["id"] == "7" and j["log"] == []
    from core.units import store
    assert store.get("sets", "7")["blocks"][-1]["fields"]["answer"] == "②"


def _mini_docx(path, paras):
    """[(스타일 id, [(글, {u,b})])] → 최소 docx (styles.xml 에 이름 = id 로 등록)."""
    import zipfile
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = ""
    for sid, runs in paras:
        rr = "".join(f"<w:r><w:rPr>{'<w:u w:val=\"single\"/>' if f.get('u') else ''}{'<w:b/>' if f.get('b') else ''}</w:rPr><w:t xml:space=\"preserve\">{t}</w:t></w:r>" for t, f in runs)
        body += f"<w:p>{f'<w:pPr><w:pStyle w:val=\"{sid}\"/></w:pPr>' if sid else ''}{rr}</w:p>"
    styles = "".join(f'<w:style w:styleId="{sid}"><w:name w:val="{sid}"/></w:style>' for sid, _ in paras if sid)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/styles.xml", f'<?xml version="1.0"?><w:styles {W}>{styles}</w:styles>')


def test_manuscript_docx_styles_map_to_slots(lib, tmp_path):
    """docx 단락 스타일 이름(지문·발문·선지·빈칸 줄)이 블록·자리 이름과 맞으면 규칙 없이도 그 자리로. 밑줄·굵게는 서식 조각."""
    from core.units import manuscript
    p = tmp_path / "m.docx"
    _mini_docx(str(p), [
        ("Normal", [("# 5", {})]),
        ("지문", [("Cities were built around cars. ", {}), ("However", {"b": True}), (", planners are reversing this.", {})]),
        ("지문", [("Second paragraph of the passage.", {})]),
        ("발문", [("윗글의 요지로 가장 적절한 것은?", {})]),
        ("선지", [("① one", {})]), ("선지", [("② two", {})]), ("선지", [("③ three", {})]),
        ("Normal", [("답: ②", {})]),
        ("빈칸 줄", [("1. Wide roads ", {}), ("replaced", {"u": True}), (" neighborhoods.", {})]),
        ("해석", [("넓은 도로가 동네를 대체했다.", {})]),
    ])
    sets, log = manuscript.from_file(str(p), lib["blocks"])
    assert log == [] and len(sets) == 1 and sets[0]["id"] == "5"
    b = {x["block"]: x["fields"] for x in sets[0]["blocks"]}
    passage = b["passage"]["passage"]
    assert isinstance(passage, list) and {"t": "However", "b": True} in passage and "Second paragraph" in "".join(x if isinstance(x, str) else x["t"] for x in passage)
    assert b["prompt"]["prompt"].endswith("?") and b["choices"]["choices"] == ["one", "two", "three"] and b["choices"]["answer"] == "②"
    assert b["blank"]["no"] == 1 and {"t": "replaced", "u": True} in b["blank"]["sentence"] and b["blank"]["kr"].startswith("넓은")


def test_paragraph_style_from_skin(lib):
    """글 원자의 style → 옷의 styles 값이 원자 값보다 우선. 옷을 바꾸면 그 스타일의 글이 다 바뀐다."""
    from core.units import render, store
    skin = json.loads(json.dumps(store.by_id(lib["skins"])["d2"]))
    part = {"id": "p", "name": "p", "w": 60, "h": 10, "atoms": [{"t": "text", "x": 0, "y": 0, "w": 60, "h": 10, "font": "$body", "size": 8, "style": "prompt", "text": "hello"}]}
    ctx = render.Ctx(skin, lib)
    frag, _ = render.part_svg(ctx, part)
    assert "font-size:2.999px" in frag                                   # prompt 스타일 8.5pt (원자 8pt 아님)
    skin["styles"]["prompt"] = {"size": 12, "b": True}
    frag2, _ = render.part_svg(render.Ctx(skin, lib), part)
    assert "font-size:4.233px" in frag2 and "font-weight:700" in frag2
    ctx3 = render.Ctx({"id": "x", "tokens": skin["tokens"]}, lib)
    render.part_svg(ctx3, part)
    assert any("단락 스타일 없음 prompt" in w for w in ctx3.warnings)


def test_stack_flow_pages(lib):
    """쌓기 자리(flow): 세트를 아래로 쌓고 면이 차면 다음 면에 이어 쌓는다."""
    from core.units import answers, render, store
    ctx = render.Ctx(store.by_id(lib["skins"])["d2"], lib, {"title": "T", "tag": "TAG"})
    pg = store.by_id(lib["pages"])["answers"]
    many = []
    for i in range(80):
        s = json.loads(json.dumps(lib["sets"][i % 2]))
        s["id"] = str(i + 1)
        many.append(s)
    asets = answers.answer_sets(many, lib["blocks"])
    assert len(asets) == 80 and asets[0]["blocks"][0]["fields"]["no"] == "1"
    out = render.page_svgs(ctx, pg, asets, render.DEFAULT_SPEC, 1, "정답")
    assert len(out) >= 3 and out[1]["label"] == "정답 (2)"
    rows = [o["svg"].count("data-fi=") - 3 for o in out]
    assert sum(rows) == 80 and all(r > 10 for r in rows[:-1])
    assert not any("넘친다" in w for w in ctx.warnings), ctx.warnings


def test_check_report(lib):
    """검수 — 원고 빠진 자리·안 실린 원고는 error, 넘침은 info, 어느 구간도 안 받는 kind 는 warn."""
    from core.units import check, store
    plan = store.by_id(lib["plans"])["workbook_mini"]
    r = check.report(lib, plan, "d2")
    assert r["pages"] == 6 and r["errors"] >= 2 and not r["ok"]
    msgs = [i["msg"] for i in r["issues"]]
    assert any("안 실린다" in m for m in msgs) and any("6면" in m for m in msgs)
    # 맞는 원고만 넣으면 ok
    good = [s for s in lib["sets"] if s["id"] == "21"]
    r2 = check.report(lib, plan, "d2", good)
    assert r2["ok"], r2["issues"]
    # 안 받는 kind
    stray = good + [{"kind": "vocab", "id": "9", "blocks": [{"block": "passage", "fields": {"passage": "x"}}]}]
    r3 = check.report(lib, plan, "d2", stray)
    assert any("어느 구간도 받지 않아" in i["msg"] and i["level"] == "warn" for i in r3["issues"])


def test_print_mode_bleed_marks_and_gray_map(lib):
    """인쇄 모드: 매체 = 재단 + 2×(도련+재단선 5mm), 가장자리 상자는 도련까지 늘고, 재단선 8줄, 무채색 토큰 → K."""
    from core.units import pdf, render, store
    skin = store.by_id(lib["skins"])["d2"]
    ctx = render.Ctx(skin, lib, {"title": "T", "tag": "TAG"})
    ctx.print = {"bleed": 3.0, "marks": True}
    cover = store.by_id(lib["pages"])["cover"]
    svg = render.page_svgs(ctx, cover, [], render.DEFAULT_SPEC)[0]["svg"]
    assert 'viewBox="0 0 226.000 313.000"' in svg and 'data-trim="210.000 297.000"' in svg
    assert svg.count("stroke-width=\"0.09\"") == 8                                   # 재단선
    assert 'x="-3.000" y="-3.000" width="216.000"' in svg                            # 가장자리 상자가 도련까지
    plain = render.page_svgs(render.Ctx(skin, lib), cover, [], render.DEFAULT_SPEC)[0]["svg"]
    assert 'viewBox="0 0 210.000 297.000"' in plain and "-3.000" not in plain           # 화면용은 그대로
    g = pdf.gray_map_of(skin)
    assert g["#231f20"] == 1.0 and g["#ffffff"] == 0.0 and 0.2 < g["#b8b8b8"] < 0.35 and "#667fb4" not in g


def test_seed_upgrade_adds_only_new(tmp_path):
    """시드 보태기: 라이브에 없는 항목·스타일·구간만 더하고, 있는 것은 손대지 않는다."""
    import shutil
    from core.units import seed
    live = tmp_path / "live"
    shutil.copytree(os.path.join(REPO, "catalog", "_units"), live)
    # 라이브를 "옛날" 상태로: 정답 줄·정답 지면·스타일·정답 구간 없음, 지면 이름 바꿈
    for kind, drop in (("parts", "answer_row"), ("blocks", "answer_row"), ("pages", "answers")):
        p = live / f"{kind}.json"
        items = [x for x in json.load(open(p, encoding="utf-8")) if x["id"] != drop]
        if kind == "pages":
            items[0]["name"] = "내가 고친 이름"
        if kind == "parts":
            for x in items:
                for a in x["atoms"]:
                    a.pop("style", None)
        json.dump(items, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    sk = json.load(open(live / "skins.json", encoding="utf-8"))
    for x in sk:
        x.pop("styles", None)
    json.dump(sk, open(live / "skins.json", "w", encoding="utf-8"), ensure_ascii=False)
    pl = json.load(open(live / "plans.json", encoding="utf-8"))
    pl[0]["sections"] = [s for s in pl[0]["sections"] if s["id"] != "answers"]
    json.dump(pl, open(live / "plans.json", "w", encoding="utf-8"), ensure_ascii=False)
    ch = seed.upgrade(str(live), os.path.join(REPO, "catalog", "_units"))
    assert "parts/answer_row" in ch and "pages/answers" in ch and "plans/workbook_mini.sections.answers" in ch
    assert any(c.startswith("skins/d2.styles.") for c in ch) and any(c.endswith(".style") for c in ch)
    pages = json.load(open(live / "pages.json", encoding="utf-8"))
    assert pages[0]["name"] == "내가 고친 이름" and any(p["id"] == "answers" for p in pages)      # 있는 건 그대로, 새것만
    assert seed.upgrade(str(live), os.path.join(REPO, "catalog", "_units")) == []                 # 두 번째는 할 일 없음
