#!/usr/bin/env python3
"""지문 매처 실측 평가 — 코퍼스 content.json 전수.

정답 데이터: 같은 케이스 안에서 같은 지문번호를 가진 섹션 간 유닛 = 양성쌍,
다른 지문번호 = 음성쌍. EBS류(스텝 내 번호 중복 = 유닛별 재시작 번호) 케이스는
페이지 마커 있는 헤더만 신뢰하고 bracket-only 유닛은 평가에서 제외.

사용: python3 scripts/passage_match_eval.py [--verbose] [--dump-fails]
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.passage_match import (  # noqa: E402
    fingerprint, build_idf, is_same_passage, pair_score,
    segment_content_steps,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_FAMILIES = (
    "workbook", "workbook_v2", "workbook_supp", "workbook_sero",
    "textbook_workbook", "ebs_workbook", "ebs_workbook_v2",
    "suneungteukgang_workbook",
)
MIN_EVAL_TOKENS = 10  # 이보다 짧은 유닛(정답 스텁 등)은 평가 제외


def load_cases():
    cases = []
    for fam in CORPUS_FAMILIES:
        for p in sorted(glob.glob(os.path.join(
                ROOT, "tests", "corpus", fam, "*", "golden", "content.json"))):
            case_id = "%s/%s" % (fam, p.split(os.sep)[-3])
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            cases.append((case_id, data.get("steps") or {}))
    return cases


def label_items(items):
    """유닛에 평가 라벨 부여 → (평가 대상 리스트, 제외 수).

    반환 항목: (item, key) — key는 해시 가능 라벨.
    양성 판정은 key 함수가 아니라 truth_same()으로 (범위 번호 교집합).
    """
    # 비-step3 스텝에서 번호 중복 검사 (유닛별 재시작 번호 감지)
    dup = False
    per_step = {}
    for it in items:
        if it.step.startswith("step3_"):
            continue
        per_step.setdefault(it.step, []).append(it.nums)
    for step, numsets in per_step.items():
        seen = set()
        for ns in numsets:
            if not ns:
                continue
            if ns in seen:
                dup = True
            seen.add(ns)

    labeled = []
    excluded = 0
    for it in items:
        toks = len(it.text.split())
        if toks < MIN_EVAL_TOKENS:
            excluded += 1
            continue
        if dup and not it.step.startswith("step3_"):
            # 번호 신뢰 불가 케이스: 페이지 마커 있는 헤더만
            if it.page:
                labeled.append((it, ("pg", it.page, it.nums)))
            else:
                excluded += 1
        else:
            if it.nums:
                labeled.append((it, ("num", it.nums)))
            else:
                excluded += 1
    return labeled, excluded, dup


def truth_same(ka, kb):
    if ka[0] != kb[0]:
        return None  # 라벨 체계 다름 — 판정 불가, 쌍 제외
    if ka[0] == "num":
        return bool(ka[1] & kb[1])
    # 페이지 키: 같은 페이지+번호 = 양성, 페이지 다르면 음성,
    # 같은 페이지 다른 번호 = 음성
    return ka[1] == kb[1] and bool(ka[2] & kb[2] or (not ka[2] and not kb[2]))


def eval_case(case_id, steps, verbose=False, dump_fails=None):
    items = segment_content_steps(steps)
    labeled, excluded, dup = label_items(items)
    fps = [fingerprint(it.text) for it, _ in labeled]
    idf = build_idf(fps)
    n = len(labeled)
    tp = fp_ = fn = tn = 0
    fails = []
    # 그룹(추이적 폐포) 지표용 union-find — 실사용(제거 그룹핑)과 동일 의미
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pred_mat = {}
    for i in range(n):
        for j in range(i + 1, n):
            pred = is_same_passage(fps[i], fps[j], idf)
            pred_mat[(i, j)] = pred
            if pred:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

    g_tp = g_fp = g_fn = g_tn = 0
    for i in range(n):
        for j in range(i + 1, n):
            t = truth_same(labeled[i][1], labeled[j][1])
            if t is None:
                continue
            pred = pred_mat[(i, j)]
            gpred = find(i) == find(j)
            if t and gpred:
                g_tp += 1
            elif t:
                g_fn += 1
            elif gpred:
                g_fp += 1
            else:
                g_tn += 1
            if t and pred:
                tp += 1
            elif t and not pred:
                fn += 1
                fails.append(("FN", labeled[i][0], labeled[j][0],
                              pair_score(fps[i], fps[j], idf)))
            elif not t and pred:
                fp_ += 1
                fails.append(("FP", labeled[i][0], labeled[j][0],
                              pair_score(fps[i], fps[j], idf)))
            else:
                tn += 1
    if verbose or fails:
        for kind, a, b, sc in fails[:12 if not dump_fails else 9999]:
            print("  %s %s: %s(%s|%s) ~ %s(%s|%s) %s" % (
                case_id, kind,
                a.step, a.page, sorted(a.nums),
                b.step, b.page, sorted(b.nums), sc))
            if dump_fails:
                print("    A:", a.text[:160].replace("\n", " "))
                print("    B:", b.text[:160].replace("\n", " "))
    return {"case": case_id, "items": len(items), "eval_items": len(labeled),
            "excluded": excluded, "dup_numbering": dup,
            "tp": tp, "fp": fp_, "fn": fn, "tn": tn,
            "g_tp": g_tp, "g_fp": g_fp, "g_fn": g_fn, "g_tn": g_tn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--dump-fails", action="store_true")
    args = ap.parse_args()

    rows = []
    for case_id, steps in load_cases():
        rows.append(eval_case(case_id, steps, args.verbose, args.dump_fails))

    TP = sum(r["tp"] for r in rows)
    FP = sum(r["fp"] for r in rows)
    FN = sum(r["fn"] for r in rows)
    TN = sum(r["tn"] for r in rows)
    prec = TP / (TP + FP) if (TP + FP) else 1.0
    rec = TP / (TP + FN) if (TP + FN) else 1.0
    print()
    print("%-42s %5s %5s %5s %5s %5s %5s" % (
        "case", "items", "eval", "tp", "fp", "fn", "tn"))
    for r in rows:
        flag = " DUP" if r["dup_numbering"] else ""
        print("%-42s %5d %5d %5d %5d %5d %5d%s" % (
            r["case"], r["items"], r["eval_items"],
            r["tp"], r["fp"], r["fn"], r["tn"], flag))
    GTP = sum(r["g_tp"] for r in rows)
    GFP = sum(r["g_fp"] for r in rows)
    GFN = sum(r["g_fn"] for r in rows)
    gprec = GTP / (GTP + GFP) if (GTP + GFP) else 1.0
    grec = GTP / (GTP + GFN) if (GTP + GFN) else 1.0
    print()
    print("pairs: pos=%d neg=%d  TP=%d FP=%d FN=%d TN=%d" % (
        TP + FN, FP + TN, TP, FP, FN, TN))
    print("PAIRWISE  PRECISION = %.4f   RECALL = %.4f" % (prec, rec))
    print("GROUPED   PRECISION = %.4f   RECALL = %.4f   (추이적 폐포 — 실사용 그룹핑 기준)"
          % (gprec, grec))
    ok = gprec >= 0.98 and grec >= 0.98 and prec >= 0.98 and rec >= 0.98
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
