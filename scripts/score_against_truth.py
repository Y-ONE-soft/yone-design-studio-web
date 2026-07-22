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


# ── W45: "완성본 회피 관행" 태깅 ────────────────────────────────────────────
# 답란("(A): _____", "주제문:", "____.")을 완성본이 **지문 스타일**로 갖고
# 있는 건 조판 의도가 아니라 회피다 — 선지 스타일에 들여쓰기가 있어 답란
# 정렬이 깨지므로 사람이 손으로 지문 스타일로 바꾼 것(사용자 확인, W44에서
# 61건/13문서로 관측). 이런 행을 정답으로 채점하면 판정기가 회피를 학습한다.
# → 태깅 후 정답을 답란 전용 스타일(S_답란)로 재정의한다.
ANSLINE_STYLE_NAME = "S_답란"
AVOIDANCE_TAG = "ansline_avoidance"
LEGACY_CHOICE_TAG = "ansline_legacy_choice"
_RE_ANS_PAREN = re.compile(
    r"^[(（]\s*[A-Za-z가-힣0-9]{1,3}\s*[)）]\s*[:：]?\s*_{3,}[\s_]*[.,]?$")
_RE_ANS_LABEL = re.compile(r"^[\s가-힣A-Za-z()（）]{1,12}[:：]$")
_RE_ANS_BLANK = re.compile(r"^[^_]{0,15}_{3,}[\s_]*[.,]?$")


def is_ansline_text(text):
    t = re.sub(r"\s+", " ", (text or "").replace("\r", "")).strip()
    return bool(_RE_ANS_PAREN.match(t) or _RE_ANS_LABEL.match(t)
                or _RE_ANS_BLANK.match(t))


def ansline_avoidance(pred_style, gold_style, text):
    """이 행이 '완성본 회피 관행'(답란 → 지문 스타일)인가."""
    return (is_ansline_text(text)
            and "지문" in (gold_style or "")
            and any(k in (pred_style or "")
                    for k in ("선지", ANSLINE_STYLE_NAME)))


def ansline_legacy_choice(pred_style, gold_style, text):
    """완성본이 답란을 '선지 스타일'로 갖고 있는 구 관행 행 (W45).

    S_답란 신설 전에는 선지가 답란의 표준이었다 — 새 계약(S_답란)에서는
    이것도 정답 재정의 대상이다 (회피 관행과 달리 결함은 아니었다)."""
    return (is_ansline_text(text)
            and "선지" in (gold_style or "")
            and ANSLINE_STYLE_NAME in (pred_style or ""))


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


def score(rows, preds, min_conf=0.9, ansline_retag=True):
    """ansline_retag=True: 회피 관행 행의 정답을 S_답란(예측 답란 계열)로
    재정의해 채점한다 (W45). False면 W44와 동일한 원본 정답표 채점."""
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
        pred, gold = canon(got[1]), canon(r["gold_style"])
        tag = ""
        if ansline_legacy_choice(pred, gold, r["text"]):
            tag = LEGACY_CHOICE_TAG
            if ansline_retag:
                gold = pred
        elif ansline_avoidance(pred, gold, r["text"]):
            tag = AVOIDANCE_TAG
            if ansline_retag:
                # 정답 재정의 — 답란은 답란 전용 스타일이 정답이다.
                # (템플릿에 S_답란이 아직 없는 완성본이라 정답표에는
                #  존재할 수 없는 값 — 예측이 답란 계열이면 정답 처리)
                gold = pred if ANSLINE_STYLE_NAME in pred else \
                    canon(re.sub(r"[^>]+$", ANSLINE_STYLE_NAME, pred))
        res.append({**r, "pred_style": pred, "gold": gold, "tag": tag,
                    "ok": pred == gold})
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
        # W45 — 회피 관행(답란 → 지문 스타일) 태깅 결산
        "avoidance_rows": sum(1 for r in res if r.get("tag") == AVOIDANCE_TAG),
        "avoidance_docs": len({r["doc"] for r in res
                               if r.get("tag") == AVOIDANCE_TAG}),
        "legacy_choice_rows": sum(1 for r in res
                                  if r.get("tag") == LEGACY_CHOICE_TAG),
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
             f"({s['correct']}/{s['rows']})")
    L.append(f"- 회피 관행 태깅(답란 → 지문 스타일, W45): "
             f"{s.get('avoidance_rows', 0)}행 / "
             f"{s.get('avoidance_docs', 0)}문서 (+ 구 선지 관행 {s.get('legacy_choice_rows', 0)}행) — 정답 재정의 "
             f"{'적용' if meta.get('ansline_retag') else '미적용'}\n")

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
    ap.add_argument("--no-ansline-retag", action="store_true",
                    help="W45 회피 관행(답란 → 지문 스타일) 정답 재정의 끄기 "
                         "— W44와 같은 원본 정답표 채점")
    args = ap.parse_args()

    flags = apply_flags()
    rows = load_truth(args.truth)
    pdata = json.load(open(args.pairs, encoding="utf-8"))
    j2c = {p["job_id"]: p["content_json"] for p in pdata["pairs"]
           if p.get("job_id") and p.get("content_json")}
    jobs = {r["job"] for r in rows}
    preds = predict({j: j2c[j] for j in jobs if j in j2c})
    res, miss = score(rows, preds, min_conf=args.min_conf,
                      ansline_retag=not args.no_ansline_retag)
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
        "ansline_retag": not args.no_ansline_retag,
    }
    print(json.dumps({"accuracy": s["accuracy"], "rows": s["rows"],
                      "miss": miss,
                      "avoidance_rows": s.get("avoidance_rows"),
                      "avoidance_docs": s.get("avoidance_docs"),
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
