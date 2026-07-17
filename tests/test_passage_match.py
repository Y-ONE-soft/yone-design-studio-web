# -*- coding: utf-8 -*-
"""지문 동일성 매처 리그레션 (W26).

1. 사용자 예시 3변형 합성 테스트 (스펙 고정).
2. 코퍼스 전수 정밀도/재현율 게이트 (같은 지문번호 = 양성쌍 정답 데이터).
3. 대표 케이스 그룹핑 스냅샷 (tests/fixtures/passage_match_groups.json).
   재생성: 스냅샷 생성 블록은 이 파일 하단 주석 참조.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.passage_match import (  # noqa: E402
    fingerprint, build_idf, is_same_passage,
    group_items, group_fingerprints, detect_hubs, build_match_graph,
    segment_content_steps,
)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "passage_match_groups.json")

SNAPSHOT_CASES = [
    ("workbook", "0a5da924"),
    ("ebs_workbook", "4ed24266"),
    ("workbook_supp", "r11c23ext1"),
    ("suneungteukgang_workbook", "65cf0265"),
]


# ── 1. 사용자 예시 3변형 (스펙) ─────────────────────────────────────────────

ORIG = "hello this is yone design studio. please do not follow me."
VAR_BLANK = "hello ____ is yone design"            # 빈칸 변형
VAR_PREFIX = "(A) hello this is yone design studio."  # 선지 접두 변형
VAR_SUFFIX = "please do not follow me..."          # 첫 문장 생략 변형
NEG1 = "the quick brown fox jumps over the lazy dog near the riverbank every morning."
NEG2 = "climate change accelerates glacial melting across polar regions during summer."


def test_user_example_three_variants_group_together():
    texts = [ORIG, VAR_BLANK, VAR_PREFIX, VAR_SUFFIX, NEG1, NEG2]
    groups = group_items(texts)
    by_idx = {}
    for gi, g in enumerate(groups):
        for i in g:
            by_idx[i] = gi
    # 3변형 전부 원문과 같은 그룹
    assert by_idx[1] == by_idx[0]
    assert by_idx[2] == by_idx[0]
    assert by_idx[3] == by_idx[0]
    # 음성은 분리
    assert by_idx[4] != by_idx[0]
    assert by_idx[5] != by_idx[0]
    assert by_idx[4] != by_idx[5]


def test_variant_containment_is_asymmetric_safe():
    # 변형 ⊂ 원문 방향 containment — 원문이 더 길어도 매치
    fa = fingerprint(ORIG)
    fb = fingerprint(VAR_SUFFIX)
    assert is_same_passage(fa, fb)
    # 무관 지문은 불매치
    assert not is_same_passage(fa, fingerprint(NEG1))


# ── 2. 코퍼스 전수 정밀도/재현율 게이트 ─────────────────────────────────────

def test_corpus_precision_recall_gate():
    from scripts.passage_match_eval import load_cases, label_items, truth_same

    TP = FP = FN = TN = 0
    GTP = GFP = GFN = 0
    for case_id, steps in load_cases():
        items = segment_content_steps(steps)
        labeled, _, _ = label_items(items)
        fps = [fingerprint(it.text) for it, _ in labeled]
        idf = build_idf(fps)
        n = len(labeled)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        preds = {}
        for i in range(n):
            for j in range(i + 1, n):
                pred = is_same_passage(fps[i], fps[j], idf)
                preds[(i, j)] = pred
                if pred:
                    ra, rb = find(i), find(j)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
        for i in range(n):
            for j in range(i + 1, n):
                t = truth_same(labeled[i][1], labeled[j][1])
                if t is None:
                    continue
                pred = preds[(i, j)]
                gpred = find(i) == find(j)
                if t:
                    TP += pred
                    FN += not pred
                    GTP += gpred
                    GFN += not gpred
                else:
                    FP += pred
                    TN += not pred
                    GFP += gpred

    assert TP + FN > 4000, "정답 양성쌍 규모 이상 (코퍼스 축소?)"
    prec = TP / float(TP + FP)
    rec = TP / float(TP + FN)
    gprec = GTP / float(GTP + GFP)
    grec = GTP / float(GTP + GFN)
    # 스펙 목표 98%+ (실측 2026-07: pairwise 99.87/99.73, grouped 99.12/100)
    assert prec >= 0.98, "pairwise precision %.4f < 0.98" % prec
    assert rec >= 0.98, "pairwise recall %.4f < 0.98" % rec
    assert gprec >= 0.98, "grouped precision %.4f < 0.98" % gprec
    assert grec >= 0.99, "grouped recall %.4f < 0.99" % grec


# ── 3. 대표 케이스 그룹핑 스냅샷 ────────────────────────────────────────────

def _case_groups(fam, cid):
    path = os.path.join(ROOT, "tests", "corpus", fam, cid,
                        "golden", "content.json")
    with open(path, encoding="utf-8") as f:
        steps = json.load(f)["steps"]
    items = segment_content_steps(steps)
    groups = group_items([it.text for it in items])
    return [
        [[items[i].step, sorted(items[i].nums), items[i].page] for i in g]
        for g in groups
    ]


@pytest.mark.parametrize("fam,cid", SNAPSHOT_CASES)
def test_grouping_snapshot(fam, cid):
    with open(FIXTURE, encoding="utf-8") as f:
        snap = json.load(f)
    key = "%s/%s" % (fam, cid)
    assert key in snap, "스냅샷 픽스처에 %s 없음" % key
    got = _case_groups(fam, cid)
    want = snap[key]
    assert got == want, (
        "그룹핑 스냅샷 불일치 (%s) — 의도된 매처 변경이면 픽스처 재생성:\n"
        "  python3 -c \"import tests.test_passage_match as t; t.regen()\"" % key)


def test_hub_detection_ebs_step3_blob():
    """전체 step3 blob(여러 지문 포함)은 허브로 배제 — 그룹 붕괴 방지."""
    path = os.path.join(ROOT, "tests", "corpus", "ebs_workbook",
                        "4ed24266", "golden", "content.json")
    with open(path, encoding="utf-8") as f:
        steps = json.load(f)["steps"]
    items = segment_content_steps(steps)
    fps = [fingerprint(it.text) for it in items]
    idf = build_idf(fps)
    adj = build_match_graph(fps, idf)
    hubs = detect_hubs(adj)
    # step3 통짜 blob이 허브로 잡힌다
    hub_steps = {items[i].step for i in hubs}
    assert any(s.startswith("step3") for s in hub_steps)
    # 허브 배제 후 6개 지문 그룹 (7-clique×4 + 5-clique×2)
    groups, hubs2 = group_fingerprints(fps, idf)
    multi = [g for g in groups if len(g) > 1]
    assert sorted(len(g) for g in multi) == [5, 5, 7, 7, 7, 7]


def regen():
    """스냅샷 픽스처 재생성 (의도된 매처 변경 시에만)."""
    snap = {}
    for fam, cid in SNAPSHOT_CASES:
        snap["%s/%s" % (fam, cid)] = _case_groups(fam, cid)
    with open(FIXTURE, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print("wrote", FIXTURE)
