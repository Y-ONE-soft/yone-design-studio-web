#!/usr/bin/env python3
"""시각 검수(1층) 임계 캘리브레이션 — 양품 코퍼스에서 false-critical 0 실증 (W29).

양품 세트(덤프 overflow_stories:0 실증 PDF들)를 렌더→검사해 페이지 지표 분포와
플래그 수를 기록한다. 합격선: 모든 양품 문서 critical 0. review 플래그는 2층
검토 후보라 0일 필요는 없지만 문서당 소수여야 한다(알람 피로 방지).

사용: python3 scripts/calibrate_visual_inspect.py [--out data_corpus/visual_review/calibration.json]
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.visual_inspect import inspect_pages, render_pdf_pages  # noqa: E402

# 양품: 각 job/typeset_dump.json 이 overflow_stories:0 (탐색 실증 2026-07-18)
GOOD_SET = [
    ("round13_wb", "data_corpus/round13/out/워크북1_내지_v2.pdf",
     "data_corpus/round13/out/job/typeset_dump.json"),
    ("round11_wb", "data_corpus/round11/out/워크북1_내지_v2_2.pdf",
     "data_corpus/round11/out/job/typeset_dump.json"),
    ("c14_wb3", "data_corpus/round2/c14_wb3/out/워크북외부지문3_내지_v2_2.pdf",
     "data_corpus/round2/c14_wb3/out/job/typeset_dump.json"),
    ("c05_mock", "data_corpus/round3/c05_mock/out/고1_25년_10월_전체(C)_v2_7.pdf",
     "data_corpus/round3/c05_mock/out/job/typeset_dump.json"),
    ("c20_mock", "data_corpus/round9/c20_mock2503/out/고2_25년_03월_전체(C)_v2_6.pdf",
     "data_corpus/round9/c20_mock2503/out/job/typeset_dump.json"),
]

# 불량: 덤프 overflow_stories:1 — V4(OVERSET) critical 검출돼야 함
BAD_SET = [
    ("c21_rp11", "data_corpus/round10/c21_rp11/out/EBS_리딩파워_11강기출_전체(C)_v2_2.pdf",
     "data_corpus/round10/c21_rp11/out/job/typeset_dump.json"),
]


def run_one(name, pdf, dump_path, work_dir):
    t0 = time.time()
    pngs, backend = render_pdf_pages(
        os.path.join(ROOT, pdf), os.path.join(work_dir, name))
    dump = None
    dp = os.path.join(ROOT, dump_path)
    if os.path.isfile(dp):
        dump = json.load(open(dp, encoding="utf-8"))
    rep = inspect_pages(pngs, dump=dump)
    s = rep["summary"]
    return {
        "name": name, "pdf": pdf, "pages": rep["page_count"],
        "backend": backend, "sec": round(time.time() - t0, 1),
        "critical": s["critical"], "review": s["review"],
        "flagged_pages": s["flagged_pages"],
        "doc_flags": rep["doc_flags"],
        "flags_detail": [
            {"page": p["page"], "flags": p["flags"]}
            for p in rep["pages"]
            if any(f["level"] in ("critical", "review") for f in p["flags"])],
        "ok": rep["ok"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_corpus/visual_review/calibration.json")
    ap.add_argument("--work", default=os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "visual_calib"))
    args = ap.parse_args()

    results = {"good": [], "bad": []}
    for name, pdf, dp in GOOD_SET:
        r = run_one(name, pdf, dp, args.work)
        results["good"].append(r)
        print(f"[양품] {name}: {r['pages']}p critical={r['critical']} "
              f"review={r['review']} ({r['sec']}s, {r['backend']})")
    for name, pdf, dp in BAD_SET:
        r = run_one(name, pdf, dp, args.work)
        results["bad"].append(r)
        print(f"[불량] {name}: {r['pages']}p critical={r['critical']} "
              f"review={r['review']}")

    false_crit = sum(r["critical"] for r in results["good"])
    detected = sum(1 for r in results["bad"] if r["critical"] >= 1)
    results["verdict"] = {
        "good_false_critical": false_crit,
        "bad_detected": detected,
        "bad_total": len(results["bad"]),
        "pass": false_crit == 0 and detected == len(results["bad"]),
    }
    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n판정: 양품 false-critical {false_crit} / "
          f"불량 검출 {detected}/{len(results['bad'])} → "
          f"{'합격' if results['verdict']['pass'] else '불합격'}")
    print(f"기록: {out}")
    return 0 if results["verdict"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
