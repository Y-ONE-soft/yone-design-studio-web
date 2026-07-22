#!/usr/bin/env python3
"""현행 판정기 채점 — 정답표(완성 조판본에서 역으로 뽑은 스타일) 대조 (W44).

예측: content.json → engines.workbook_v2.plan.steps_to_plan
      (파서 kind 주석 → 스텝 빌더 슬롯 배정 → core.structure.style_map 해석)
정답: data_corpus/reverse_learn/ground_truth.jsonl 의 gold_style
      (= 사람 손마무리까지 끝난 완성 .indd에서 그 단락에 실제로 적용된 스타일)

정답표는 "예측 인덱스(step/unit/idx) + 원문"을 함께 갖고 있으므로, 규칙을
고친 뒤 **다시 채점만** 하면 개선 수치가 바로 나온다 (재덤프/재정렬 불필요).
인덱스가 밀린 경우(유닛 분할 변화)는 스텝 안 정규화 키 재탐색으로 복구한다.

산출: docs/역학습_채점리포트.md (--report) / stdout 요약
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "data_corpus", "reverse_learn")

STEP_UNIT = {
    "step1_a1": "STEP1A1", "step1_a1_2": "STEP1A1", "step1_a2": "STEP1A2",
    "step1_b1": "STEP1B1", "step1_b2": "STEP1B2", "step1_c1": "STEP1C1",
    "step1_c2": "STEP1C2", "step2_a1": "STEP2A1",
    "step2_a1_btm": "STEP2A1Practice", "step2_b1": "STEP2B1",
    "step2_c1": "STEP2C1", "step2_c2": "STEP2C2", "step3": "STEP3",
}

# 기본 단락 스타일의 여러 표기 — 같은 것으로 본다
_BASIC = {"$basic", "[기본 단락]", "[basic paragraph]", "[기본단락]",
          "[no paragraph style]", "기본 단락"}


def canon(style):
    s = unicodedata.normalize("NFC", (style or "").strip())
    if s.lower() in _BASIC or s in _BASIC:
        return "$BASIC"
    return re.sub(r"\s+", " ", s)


def load_truth(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def apply_flags():
    """실험 스위치 — 규칙 보강 전/후 채점을 같은 정답표로 비교하기 위한 토글.

    YONE_W44_PROMOTE=0 → step1_c1 헤더 부분 인식 보강 끄기 (W43 이전 동작)
    """
    from engines.workbook_v2 import plan as _plan
    if os.environ.get("YONE_W44_PROMOTE") == "0":
        _plan.PROMOTE_C1_MISSED_HDR = False
    return {"PROMOTE_C1_MISSED_HDR": _plan.PROMOTE_C1_MISSED_HDR}


def predict(job_to_content):
    """job → {(step, unit, idx): style, "_bykey": {step: {key: [styles]}}}"""
    from core.reverse_learn.align import norm_key
    from engines.workbook_v2.plan import ensure_step3_kinds, steps_to_plan
    out = {}
    for job, cpath in job_to_content.items():
        try:
            content = json.load(open(cpath, encoding="utf-8"))
            steps = content.get("steps") or {}
            ensure_step3_kinds(steps.get("step3"))
            plan = steps_to_plan(
                steps, workbook_type=content.get("workbook_type") or "모의고사")
        except Exception as e:                                 # noqa: BLE001
            out[job] = {"_error": str(e)[:200]}
            continue
        idx, bykey = {}, defaultdict(lambda: defaultdict(list))
        for flow in plan.get("flows", []):
            step = flow.get("step")
            for ui, unit in enumerate(flow.get("units", [])):
                paras = unit if isinstance(unit, list) else (unit.get("paras") or [])
                for pi, p in enumerate(paras):
                    if not isinstance(p, dict):
                        continue
                    t, s = p.get("t") or "", p.get("s") or ""
                    idx[(step, ui, pi)] = (t, s)
                    bykey[step][norm_key(t)].append(s)
        out[job] = {"idx": idx, "bykey": bykey}
    return out


def score(rows, preds, min_conf=0.9):
    from core.reverse_learn.align import norm_key
    res = []
    miss = 0
    for r in rows:
        if r.get("align_conf", 1.0) < min_conf:
            continue
        pr = preds.get(r["job"]) or {}
        if "_error" in pr:
            miss += 1
            continue
        key = (r["step"], r["unit"], r["idx"])
        got = pr["idx"].get(key)
        nk = norm_key(r["text"])
        if not got or norm_key(got[0]) != nk:
            cands = pr["bykey"].get(r["step"], {}).get(nk) or []
            if len(set(cands)) == 1:
                got = (r["text"], cands[0])
            else:
                miss += 1
                continue
        res.append({**r, "pred_style": canon(got[1]),
                    "gold": canon(r["gold_style"]),
                    "ok": canon(got[1]) == canon(r["gold_style"])})
    return res, miss


def summarize(res):
    n = len(res)
    ok = sum(1 for r in res if r["ok"])
    by = lambda k: {  # noqa: E731
        v: (
            sum(1 for r in res if r[k] == v and r["ok"]),
            sum(1 for r in res if r[k] == v),
        )
        for v in sorted({r[k] for r in res}, key=str)
    }
    clusters = Counter((r["step"], r["pred_style"], r["gold"])
                       for r in res if not r["ok"])
    examples = defaultdict(list)
    for r in res:
        if r["ok"]:
            continue
        k = (r["step"], r["pred_style"], r["gold"])
        if len(examples[k]) < 3:
            examples[k].append({"doc": r["doc"], "text": r["text"][:110],
                                "gold_text": r["gold_text"][:110]})
    return {
        "rows": n,
        "correct": ok,
        "accuracy": round(ok / n, 4) if n else 0.0,
        "by_series": by("series"),
        "by_step": by("step"),
        "by_human_edited": by("human_edited"),
        "by_doc_worst": sorted(
            [(d, c[0], c[1]) for d, c in by("doc").items()],
            key=lambda t: (t[1] / t[2]) if t[2] else 1)[:8],
        "clusters": clusters.most_common(20),
        "examples": {str(k): v for k, v in examples.items()},
    }


def fmt_report(s, meta):
    L = []
    L.append("# 역학습 채점 리포트 (완성 조판본 → 정답표 → 현행 판정기 채점)\n")
    L.append(f"- 생성: {meta.get('generated')}")
    L.append(f"- 정답표: {meta.get('truth_rows')}행 "
             f"(쌍 {meta.get('pairs_ok')}개, 정렬률 평균 "
             f"{meta.get('align_rate_mean')})")
    L.append(f"- 채점 대상(신뢰도 {meta.get('min_conf')} 이상): {s['rows']}행 "
             f"/ 예측 재매칭 실패 {meta.get('miss')}행")
    L.append(f"- **정확도: {s['accuracy'] * 100:.2f}%** "
             f"({s['correct']}/{s['rows']})\n")
    L.append("## 계열별\n")
    L.append("| 계열 | 정확도 | 맞음/전체 |\n|---|---|---|")
    for k, (a, b) in s["by_series"].items():
        L.append(f"| {k} | {a / b * 100:.2f}% | {a}/{b} |")
    L.append("\n## 손마무리 여부별\n")
    L.append("| 사람 손마무리 | 정확도 | 맞음/전체 |\n|---|---|---|")
    for k, (a, b) in s["by_human_edited"].items():
        L.append(f"| {k} | {a / b * 100:.2f}% | {a}/{b} |")
    L.append("\n## 스텝별\n")
    L.append("| STEP | 정확도 | 맞음/전체 |\n|---|---|---|")
    for k, (a, b) in sorted(s["by_step"].items(),
                            key=lambda kv: kv[1][0] / kv[1][1]):
        L.append(f"| {k} | {a / b * 100:.2f}% | {a}/{b} |")
    L.append("\n## 오답 유형 (예측 → 완성본 실제)\n")
    L.append("| # | STEP | 현행 예측 | 완성본 정답 | 건수 |\n|---|---|---|---|---|")
    for i, ((st, p, g), c) in enumerate(s["clusters"], 1):
        L.append(f"| {i} | {st} | `{p}` | `{g}` | {c} |")
    L.append("\n### 대표 사례 (상위 8유형)\n")
    for (st, p, g), c in s["clusters"][:8]:
        L.append(f"**{st}: `{p}` → `{g}` ({c}건)**\n")
        for ex in s["examples"].get(str((st, p, g)), []):
            L.append(f"- ({ex['doc']}) {ex['text']}")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(CORPUS, "ground_truth.jsonl"))
    ap.add_argument("--pairs", default=os.path.join(CORPUS, "pairs.json"))
    ap.add_argument("--min-conf", type=float, default=0.9)
    ap.add_argument("--report", default="")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    flags = apply_flags()
    rows = load_truth(args.truth)
    pdata = json.load(open(args.pairs, encoding="utf-8"))
    j2c = {p["job_id"]: p["content_json"] for p in pdata["pairs"]
           if p.get("job_id") and p.get("content_json")}
    jobs = {r["job"] for r in rows}
    preds = predict({j: j2c[j] for j in jobs if j in j2c})
    res, miss = score(rows, preds, min_conf=args.min_conf)
    s = summarize(res)

    brep = {}
    bp = os.path.join(CORPUS, "build_report.json")
    if os.path.isfile(bp):
        brep = json.load(open(bp, encoding="utf-8")).get("summary", {})
    meta = {
        "generated": __import__("datetime").datetime.now().strftime(
            "%Y-%m-%d %H:%M"),
        "truth_rows": len(rows), "miss": miss, "min_conf": args.min_conf,
        "pairs_ok": brep.get("pairs_ok"),
        "align_rate_mean": brep.get("align_rate_mean"),
        "flags": flags,
    }
    print(json.dumps({"accuracy": s["accuracy"], "rows": s["rows"],
                      "miss": miss,
                      "top": s["clusters"][:8]}, ensure_ascii=False, indent=1))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(fmt_report(s, meta))
        print("→", args.report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "summary": s}, f, ensure_ascii=False,
                      indent=1, default=str)
        print("→", args.json_out)


if __name__ == "__main__":
    main()
