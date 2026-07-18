# -*- coding: utf-8 -*-
"""시각 검수 1층(core.visual_inspect) 오프라인 테스트 — 합성 페이지/덤프 (W29).

InDesign·코퍼스 비의존. PIL로 합성 페이지를 만들어 픽셀 검사(V1~V3)와
지오메트리 검사(V4~V6), 패턴 병합(단면 공백), job 진입점을 검증한다.
임계 실측 근거는 scripts/calibrate_visual_inspect.py (양품 false-critical 0).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from core.visual_inspect import (  # noqa: E402
    THRESHOLDS, geometry_checks, inspect_job_visual, inspect_pages,
    overset_pages, page_metrics,
)

W, H = 400, 560


def _page(draw_fn=None, bg=(255, 255, 255)):
    im = Image.new("RGB", (W, H), bg)
    if draw_fn:
        draw_fn(ImageDraw.Draw(im))
    return im


def _textlike(d):
    """본문 흉내 — 일정 여백 안에 줄 블록."""
    for y in range(60, 500, 14):
        d.rectangle([40, y, 360, y + 6], fill=(30, 30, 30))


def _save(tmp_path, images):
    paths = []
    for i, im in enumerate(images):
        p = str(tmp_path / f"page-{i + 1:04d}.png")
        im.save(p)
        paths.append(p)
    return paths


# ── 픽셀 지표 ────────────────────────────────────────────────────────────────

def test_page_metrics_blank_vs_dense(tmp_path):
    blank = _page()
    dense = _page(bg=(0, 0, 0))
    normal = _page(_textlike)
    pb, pd, pn = _save(tmp_path, [blank, dense, normal])
    assert page_metrics(pb)["ink_ratio"] == 0.0
    assert page_metrics(pd)["ink_ratio"] > 0.99
    m = page_metrics(pn)
    assert 0.05 < m["ink_ratio"] < 0.42
    assert m["margins"]["left"] == pytest.approx(40 / W, abs=0.01)
    assert m["red_px_frac"] == 0.0


def test_red_mark_detected(tmp_path):
    def draw(d):
        _textlike(d)
        d.rectangle([180, 250, 220, 290], fill=(255, 0, 0))   # 순적색 덩어리
    p, = _save(tmp_path, [_page(draw)])
    m = page_metrics(p)
    assert m["red_px_frac"] > THRESHOLDS["red_px_frac"]
    assert m["red_bbox"] is not None


# ── inspect_pages 픽셀 플래그 ────────────────────────────────────────────────

def test_inspect_flags_blank_dense_red(tmp_path):
    def red(d):
        _textlike(d)
        d.rectangle([180, 250, 240, 310], fill=(255, 0, 0))

    def dense(d):
        # 과밀(~60% 잉크) — 전면 간지(>95%)와 구분되는 비정상 과밀
        d.rectangle([0, 0, W, int(H * 0.6)], fill=(20, 20, 20))
    imgs = [_page(_textlike), _page(), _page(dense), _page(red)]
    rep = inspect_pages(_save(tmp_path, imgs))
    codes = {p["page"]: {f["code"] for f in p["flags"]} for p in rep["pages"]}
    assert codes[1] == set()
    assert "NEAR_BLANK" in codes[2]
    assert "OVERDENSE" in codes[3]
    assert "RED_MARK" in codes[4]
    assert rep["summary"]["critical"] == 0          # 픽셀 검사는 review까지만
    assert rep["ok"] is True
    assert set(rep["summary"]["flagged_pages"]) == {2, 3, 4}


def test_fullbleed_not_overdense(tmp_path):
    """전면 간지(전부 잉크)는 정상 디자인 — OVERDENSE 아님 (양품 실측 반영)."""
    rep = inspect_pages(_save(tmp_path, [_page(_textlike), _page(bg=(0, 0, 0))]))
    assert all(not p["flags"] for p in rep["pages"])


def test_near_blank_same_side_pattern_consolidated(tmp_path):
    """같은 면 공백 3장+ → 페이지별 info + 문서 review 1건 (배면 인쇄 패턴)."""
    imgs = []
    for i in range(8):
        imgs.append(_page() if i % 2 == 1 else _page(_textlike))  # L면 공백 4장
    rep = inspect_pages(_save(tmp_path, imgs))
    nb = [f for p in rep["pages"] for f in p["flags"] if f["code"] == "NEAR_BLANK"]
    assert nb and all(f["level"] == "info" for f in nb)
    assert [d["code"] for d in rep["doc_flags"]] == ["NEAR_BLANK_PATTERN"]
    assert rep["summary"]["review"] == 1


# ── 덤프 결합 검사 (V4~V7) ───────────────────────────────────────────────────

def _dump(stories, pages):
    return {"stories": stories, "pages": pages,
            "overflow_stories": sum(1 for s in stories if s.get("overflow"))}


def test_overset_mapped_to_page_critical(tmp_path):
    imgs = [_page(_textlike), _page(_textlike)]
    dump = _dump(
        [{"idx": 0, "overflow": True, "fp": ["1", "2"], "pg": ["1", "2"]}],
        [{"p": "1", "m": "A-마스터", "side": "R", "empty": False},
         {"p": "2", "m": "A-마스터", "side": "L", "empty": False}])
    rep = inspect_pages(_save(tmp_path, imgs), dump=dump)
    assert rep["ok"] is False
    p2 = rep["pages"][1]
    assert any(f["code"] == "OVERSET" and f["level"] == "critical"
               for f in p2["flags"])


def test_overset_unknown_page_doc_flag(tmp_path):
    rep = inspect_pages(
        _save(tmp_path, [_page(_textlike)]),
        dump=_dump([{"idx": 3, "overflow": True, "fp": [""], "pg": []}], []))
    assert rep["ok"] is False
    assert any(f["code"] == "OVERSET" for f in rep["doc_flags"])


def test_geometry_oob_and_overlap():
    pages = [{"p": "1", "b": [0, 0, 280, 210]}]
    stories = [
        # 페이지를 6% 이탈 (아래로) → critical
        {"idx": 0, "fp": ["1"], "fb": [[250, 20, 297, 190]]},
        # 프레임 겹침 (스토리 1 × 2, 교차 > 30%) → review
        {"idx": 1, "fp": ["1"], "fb": [[50, 20, 120, 190]]},
        {"idx": 2, "fp": ["1"], "fb": [[80, 20, 150, 190]]},
    ]
    flags = geometry_checks(_dump(stories, pages))
    codes = {(f["code"], f["level"]) for f in flags["1"]}
    assert ("GEOM_OOB", "critical") in codes
    assert ("GEOM_OVERLAP", "review") in codes


def test_geometry_absent_fields_noop():
    """구버전 덤프(fb/b 없음) — 지오메트리 검사는 조용히 빈 결과 (fail-open)."""
    dump = _dump([{"idx": 0, "fp": ["1"], "pg": ["1"]}],
                 [{"p": "1", "m": "", "side": "R", "empty": False}])
    assert geometry_checks(dump) == {}


def test_overset_pages_last_frame():
    d = _dump([{"idx": 5, "overflow": True, "fp": ["3", "4", ""], "pg": ["3", "4"]},
               {"idx": 6, "overflow": False, "fp": ["1"]}], [])
    assert overset_pages(d) == [{"story": 5, "page": "4"}]


def test_layout_outlier_requires_master_inventory(tmp_path):
    """마스터 인벤토리 없으면 V7 비활성 (좌우 단독 그룹핑 오탐 실측로 봉인)."""
    def shifted(d):
        for y in range(60, 500, 14):
            d.rectangle([120, y, 360, y + 6], fill=(30, 30, 30))
    imgs = [_page(_textlike) for _ in range(6)] + [_page(shifted)]
    rep = inspect_pages(_save(tmp_path, imgs))          # 덤프 없음
    assert not any(f["code"] == "LAYOUT_OUTLIER"
                   for p in rep["pages"] for f in p["flags"])
    pages_inv = [{"p": str(i + 1), "m": "A-마스터",
                  "side": "R" if i % 2 == 0 else "L", "empty": False}
                 for i in range(7)]
    rep2 = inspect_pages(_save(tmp_path, imgs), dump=_dump([], pages_inv))
    out = [p["page"] for p in rep2["pages"]
           if any(f["code"] == "LAYOUT_OUTLIER" for f in p["flags"])]
    assert out == [7]


# ── job 진입점 ───────────────────────────────────────────────────────────────

def test_inspect_job_visual_discovers_pdf(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    pdf = str(tmp_path / "out.pdf")
    # mode "1"(bilevel)로 저장 — 이 환경 PIL은 RGB→PDF(JPEG 인코더) 미지원
    bw = [_page(_textlike).convert("1"), _page(_textlike).convert("1"),
          _page().convert("1")]
    bw[0].save(pdf, save_all=True, append_images=bw[1:])
    (job / ".settings.json").write_text(
        json.dumps({"output_pdf": pdf, "output_dir": str(tmp_path)}),
        encoding="utf-8")
    logs = []
    rep = inspect_job_visual(str(job), logs.append)
    assert rep is not None
    assert rep["page_count"] == 3
    assert rep["ok"] is True
    assert os.path.isfile(os.path.join(str(job), "visual_report.json"))
    assert any("[시각검수]" in m for m in logs)


def test_inspect_job_visual_no_target(tmp_path):
    job = tmp_path / "empty"
    job.mkdir()
    assert inspect_job_visual(str(job), lambda m: None) is None
    # .indd만 있고 allow_indesign=False → InDesign 강제 기동 없이 None
    indd = tmp_path / "결과.indd"
    indd.write_bytes(b"stub")
    (job / ".settings.json").write_text(
        json.dumps({"output_indd": str(indd)}), encoding="utf-8")
    assert inspect_job_visual(str(job), lambda m: None) is None
