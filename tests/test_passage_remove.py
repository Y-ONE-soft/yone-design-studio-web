# -*- coding: utf-8 -*-
"""지문 제거 엔진 오프라인 리그레션 (W26).

실물 전체(C) 덤프 픽스처(0a5da924 — 18지문 × 13섹션, gzip)로 인벤토리
추출/그룹핑/배정/제거 스펙을 검증한다. InDesign 불필요.
"""

import gzip
import json
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

FIXTURE = os.path.join(TESTS_DIR, "fixtures",
                       "passage_remove_dump_0a5da924.json.gz")


@pytest.fixture(scope="module")
def dump():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def inventory(dump):
    from engines.passage_remove.inventory import build_inventory
    return build_inventory(dump)


# ── 인벤토리 그룹핑 ─────────────────────────────────────────────────────────

EXPECTED_LABELS = ["20", "21", "22", "23", "24", "29", "30", "31", "32",
                   "33", "34", "35", "36", "37", "38", "39", "40", "41~42"]


def test_full_passages_grouped_across_all_sections(inventory):
    """18개 지문이 각각 13개 스토리(섹션) 전부에 걸쳐 묶인다."""
    units = {u["uid"]: u for u in inventory["units"]}
    multi = [g for g in inventory["groups"] if g["multi"] and g["label"]]
    by_label = {g["label"]: g for g in multi}
    for lb in EXPECTED_LABELS:
        assert lb in by_label, f"지문 {lb} 그룹 없음"
        g = by_label[lb]
        stories = {units[u]["story"] for u in g["unit_uids"]}
        assert len(stories) == 13, (
            f"지문 {lb}: {len(stories)}개 스토리만 커버 (13 기대)")
        assert not g["hub"]


def test_no_cross_label_contamination(inventory):
    """헤더 라벨이 있는 유닛은 자기 라벨 그룹에만 속한다."""
    units = {u["uid"]: u for u in inventory["units"]}
    for g in inventory["groups"]:
        if not g["multi"]:
            continue
        labels = {units[u]["label"] for u in g["unit_uids"]
                  if units[u]["label"]}
        assert len(labels) <= 1, f"그룹 {g['gid']} 라벨 혼합: {labels}"


def test_assignment_runs_ordered_and_complete(inventory):
    """무헤더 스토리(65/78/68/66)의 배정 런: 시험 순서·연속·무결손."""
    units = {u["uid"]: u for u in inventory["units"]}
    gid_of = {}
    for g in inventory["groups"]:
        for u in g["unit_uids"]:
            gid_of[u] = g["gid"]
    label_of_gid = {g["gid"]: g["label"] for g in inventory["groups"]}
    for story in (65, 78, 68, 66):
        runs = sorted(
            (u["start"], u["end"], label_of_gid.get(gid_of[u["uid"]], ""))
            for u in inventory["units"]
            if u["story"] == story and u["mode"] == "assign")
        assert [r[2] for r in runs] == EXPECTED_LABELS, (
            f"story {story} 런 순서 불일치: {[r[2] for r in runs]}")
        # 연속(무결손) — 첫 런은 0에서 시작, 이후 이전 end+1
        assert runs[0][0] == 0
        for k in range(1, len(runs)):
            assert runs[k][0] == runs[k - 1][1] + 1, (
                f"story {story} 런 {k} 불연속")


def test_step3_questions_attached_to_passages(inventory):
    """step3 문제 블록이 지문 그룹에 붙는다 (라벨 없는 유닛의 매칭)."""
    units = {u["uid"]: u for u in inventory["units"]}
    by_label = {g["label"]: g for g in inventory["groups"]
                if g["multi"] and g["label"]}
    g20 = by_label["20"]
    step3_units = [u for u in g20["unit_uids"]
                   if units[u]["mode"] == "step3"]
    assert len(step3_units) >= 5, "지문 20의 step3 문제 블록이 그룹에 미부착"


# ── 제거 스펙 ───────────────────────────────────────────────────────────────

def _gid_by_label(inventory, label):
    for g in inventory["groups"]:
        if g["label"] == label and g["multi"]:
            return g["gid"]
    raise AssertionError(f"라벨 {label} 그룹 없음")


def test_removal_spec_covers_all_sections(inventory):
    from engines.passage_remove.inventory import build_removal_spec
    g20 = _gid_by_label(inventory, "20")
    g37 = _gid_by_label(inventory, "37")
    spec = build_removal_spec(inventory, [g20, g37])
    # 13개 스토리 전부 영향
    assert len(spec["stories"]) == 13
    assert set(spec["clear_numbers"]) == {"20", "37"}
    for st in spec["stories"]:
        assert st["remove"], f"story {st['story']} 제거 범위 없음"
        # 범위 정렬·비중첩
        prev_end = -1
        for r in st["remove"]:
            assert r["start"] > prev_end
            assert r["end"] >= r["start"]
            prev_end = r["end"]
        # 번호 갱신 목록에 제거 라벨 없음
        for rn in st["renumber"]:
            assert rn["label"] not in ("20", "37")


def test_removal_spec_rejects_hub():
    from engines.passage_remove.inventory import build_removal_spec
    inv = {
        "groups": [{"gid": 0, "label": "", "unit_uids": [0], "hub": True,
                    "multi": False}],
        "units": [{"uid": 0, "story": 1, "start": 0, "end": 5, "p0": "x",
                   "label": ""}],
    }
    with pytest.raises(ValueError):
        build_removal_spec(inv, [0])


def test_verify_line_sets_disjoint(inventory, dump):
    from engines.passage_remove.inventory import (
        build_removal_spec, verify_line_sets)
    g20 = _gid_by_label(inventory, "20")
    spec = build_removal_spec(inventory, [g20])
    removed_only, kept = verify_line_sets(inventory, dump,
                                          spec["removed_uids"])
    assert removed_only, "제거 판별 라인 없음"
    assert not (removed_only & kept)
    # 지문 20의 첫 문장이 제거 판별 라인에 포함
    assert any("Remember how you learned to drive" in l
               for l in removed_only)
    # 다른 지문(21)의 문장은 잔존 쪽
    assert any("A classical ideal of truth" in l for l in kept)


# ── 등록 정합 ───────────────────────────────────────────────────────────────

def test_passage_remove_registration():
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "passage_remove" in engines
    assert "workbook" in engines            # 기존 엔진 유지 (삭제 금지 규칙)
    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "passage_remove"' in raw
    assert '"engine_id": "workbook_edit"' in raw   # 기존 가공 카드 유지
    e = engines["passage_remove"]
    tpl = os.path.join(REPO, "templates", e.template_name)
    assert os.path.isfile(tpl)
    src = open(tpl, encoding="utf-8").read()
    assert "const MATERIAL_ID = 'passage_remove'" in src
    assert "/api/passage-remove/inventory" in src


def test_jsx_body_es3_safe():
    """passage_remove.body.jsx — ES3 금지 구문 부재 + 완료 마커."""
    p = os.path.join(REPO, "core", "jsx", "passage_remove.body.jsx")
    src = open(p, encoding="utf-8").read()
    import re
    # 주석의 '금지 목록' 언급은 허용 — 실제 선언/화살표 코드만 잡는다
    assert not re.search(r"\b(?:let|const)\s+[A-Za-z_$]|=>", src)
    assert "지문 제거 완료" in src
    assert "PageRange.ALL_PAGES" in src          # export 프리퍼런스 정규화
    assert "everyItem().getElements()" in src    # 컬렉션 캐시 규칙
