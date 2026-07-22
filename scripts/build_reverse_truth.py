#!/usr/bin/env python3
"""정답표 생성 — 완성 조판본 덤프 ↔ 현행 파이프라인 플랜 정렬 (역학습 W44).

절차 (쌍 하나당)
  1) 완성 .indd 덤프  — core.inspect.dump_indd (InDesign 필요).
     캐시: data_corpus/reverse_learn/dumps/<job>.json (indd mtime이 캐시보다
     새 것일 때만 재덤프). job에 이미 typeset_dump.json이 있고 그것이 완성본
     보다 새 것이면 그대로 재사용 (InDesign 미기동).
  2) 현행 판정기 플랜 — engines.workbook_v2.plan.steps_to_plan(content.json)
     (파서 kind → 슬롯 배정 → style_map 해석까지 전부 통과한 예측)
  3) core.reverse_learn.align.align_document 로 단락 단위 정렬
  4) 신뢰도 임계 이상 쌍만 정답표(jsonl)로 — 완성본은 사람이 문장을 고치거나
     더/빼기 때문에 미정렬은 정상이다 (비율을 리포트에 기록).

산출: data_corpus/reverse_learn/ground_truth.jsonl  (+ build_report.json)

InDesign 사용 규칙 (핸드북 철칙): 우리 사본만 열고 저장 없이 즉시 닫는다
(dump_stories.jsx는 showingWindow=false + SaveOptions.NO). 사용자 문서는
건드리지 않는다. 실패는 건너뛰고 기록만 — 킬 루프 금지.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(REPO, "data_corpus", "reverse_learn")
DUMPS = os.path.join(CORPUS, "dumps")

MIN_CONF = 0.85          # 정답표 채택 신뢰도 임계


def _load_env():
    env = os.path.expanduser("~/dev/yone-design-web/.env")
    if not os.path.isfile(env):
        return
    with open(env, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def apply_flags():
    """YONE_W44_PROMOTE=0 → step1_c1 부분 인식 보강 끄기 (베이스라인 인덱스)."""
    from engines.workbook_v2 import plan as _plan
    if os.environ.get("YONE_W44_PROMOTE") == "0":
        _plan.PROMOTE_C1_MISSED_HDR = False


def build_plan(content, series="", job_dir=None):
    """현행 파이프라인 예측 — 계열별 어댑터 (W46: 워크북 외 계열 편입)."""
    from core.reverse_learn.adapters import build_plan as _bp
    plan, _name = _bp(content, series=series, job_dir=job_dir)
    return plan


# 계열별 step_map — 정렬 지면 특정(align.story_scope)에만 쓴다. 예측(플랜)은
# 기존과 같이 기본 STEP_MAP으로 만들어 채점 비교 가능성을 유지한다.
_MAP_FILES = {
    "기본": "engines/workbook_v2/step_map.json",
    "교과서": "engines/textbook_workbook_v2/step_map.json",
    "EBS": "engines/ebs_workbook_v2/step_map.json",
    "supp": "engines/workbook_supp_v2/step_map.json",
}
_STG = "engines/suneungteukgang_workbook_v2/step_map.json"


def _load_map(rel):
    try:
        return json.load(open(os.path.join(REPO, rel), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def step_targets(workbook_type):
    """스텝 → {"markers": [...], "masters": [...]} — 계열별 표기 차를 우선순위
    리스트로 합친다 (앞쪽이 우선). align.story_scope가 지면을 특정하는 근거."""
    order = ["기본"]
    if workbook_type == "교과서":
        order = ["교과서", "기본", "supp"]
    elif workbook_type == "EBS":
        order = ["EBS", "stg", "기본"]
    else:
        order = ["기본", "supp", "교과서"]
    maps = []
    for name in order:
        if name == "stg":
            stg = _load_map(_STG)
            maps.append(stg.get("analysis") or {})
            maps.append(stg.get("problem") or {})
        else:
            maps.append(_load_map(_MAP_FILES[name]))
    out = {}
    for m in maps:
        for step, t in m.items():
            if step.startswith("_") or not isinstance(t, dict):
                continue
            d = out.setdefault(step, {"markers": [], "masters": []})
            if t.get("marker") and t["marker"] not in d["markers"]:
                d["markers"].append(t["marker"])
            if t.get("master") and t["master"] not in d["masters"]:
                d["masters"].append(t["master"])
    return out


def get_dump(pair, log, force=False, timeout=900):
    """완성본 덤프 (캐시/재사용/신규 덤프)."""
    indd = pair["indd_path"]
    jid = pair.get("job_id") or os.path.splitext(
        os.path.basename(indd))[0].replace("/", "_")
    cache = os.path.join(DUMPS, jid + ".json")
    i_m = os.path.getmtime(indd)
    if not force and os.path.isfile(cache) \
            and os.path.getmtime(cache) >= i_m:
        return json.load(open(cache, encoding="utf-8")), "cache"
    jd = pair.get("job_dir") or ""
    old = os.path.join(jd, "typeset_dump.json") if jd else ""
    if not force and old and os.path.isfile(old) \
            and os.path.getmtime(old) >= i_m:
        d = json.load(open(old, encoding="utf-8"))
        os.makedirs(DUMPS, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return d, "job_dump"
    from core.inspect import dump_indd
    os.makedirs(DUMPS, exist_ok=True)
    d = dump_indd(indd, cache, log, timeout=timeout)
    return d, "indesign"


def process(pair, log, min_conf=MIN_CONF, force=False):
    from core.reverse_learn.align import (align_document, flatten_dump,
                                          flatten_plan, norm_key, story_scope)
    t0 = time.time()
    content = json.load(open(pair["content_json"], encoding="utf-8"))
    plan = build_plan(content, series=pair.get("series") or "",
                      job_dir=pair.get("job_dir"))
    pp = flatten_plan(plan)
    dump, how = get_dump(pair, log, force=force)
    gg = flatten_dump(dump)
    scope = {}
    if os.environ.get("YONE_W46_TARGET_SCOPE") != "0":
        scope = story_scope(dump, step_targets(
            pair.get("workbook_type") or content.get("workbook_type") or ""))
    res = align_document(pp, gg, step_stories=scope)
    doc = os.path.basename(pair["indd_path"])
    recs = []
    for x in res["pairs"]:
        if x["conf"] < min_conf:
            continue
        p, g = pp[x["p"]], gg[x["g"]]
        if not norm_key(g["text"]):
            continue
        recs.append({
            "job": pair.get("job_id"),
            "doc": doc,
            "series": pair["series"],
            "workbook_type": pair.get("workbook_type") or "",
            "subject": pair.get("subject") or "",
            "publisher": pair.get("publisher") or "",
            "lesson": pair.get("lesson") or "",
            "school": pair.get("school") or "",
            "human_edited": pair.get("human_edited"),
            "step": p["step"],
            "unit": p["unit"],
            "idx": p["idx"],
            "text": p["text"],
            "gold_text": g["text"],
            "gold_style": g["style"],
            "pred_style_at_build": p["style"],
            "align_conf": x["conf"],
            "align_how": x["how"],
        })
    stats = dict(res["stats"])
    steps_stat = stats.pop("steps", None) or []
    stats["scope_target"] = sum(1 for s in steps_stat
                                if s.get("scope") == "target")
    stats["scope_vote"] = sum(1 for s in steps_stat if not s.get("scope"))
    stats["scope_target_empty"] = sum(1 for s in steps_stat
                                      if s.get("scope") == "target_empty")
    return recs, {
        "job": pair.get("job_id"), "doc": doc, "series": pair["series"],
        "human_edited": pair.get("human_edited"), "dump_source": how,
        "elapsed_s": round(time.time() - t0, 1),
        "kept(conf>=%.2f)" % min_conf: len(recs), **stats,
    }


def select(pairs, limit, series_cap=None):
    """파일럿 표본 — 사람 손마무리본 우선 + 계열 다양성."""
    usable = [p for p in pairs if p.get("plan_ready")
              and p.get("confidence", 0) >= 0.85 and p.get("indd_exists")]
    usable.sort(key=lambda p: (not p.get("human_edited"),
                               -(p.get("indd_mtime_delta_h") or 0)))
    out, per = [], {}
    for p in usable:
        s = p["series"]
        if series_cap and per.get(s, 0) >= series_cap:
            continue
        out.append(p)
        per[s] = per.get(s, 0) + 1
        if limit and len(out) >= limit:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(CORPUS, "pairs.json"))
    ap.add_argument("--out", default=os.path.join(CORPUS, "ground_truth.jsonl"))
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--series-cap", type=int, default=14)
    ap.add_argument("--min-conf", type=float, default=MIN_CONF)
    ap.add_argument("--no-indesign", action="store_true",
                    help="캐시/기존 덤프가 있는 쌍만 처리 (InDesign 미기동)")
    ap.add_argument("--force-dump", action="store_true")
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()

    _load_env()
    apply_flags()
    data = json.load(open(args.pairs, encoding="utf-8"))
    picks = select(data["pairs"], args.limit, args.series_cap)

    def log(msg):
        print(msg, flush=True)

    os.makedirs(CORPUS, exist_ok=True)
    mode = "a" if args.append else "w"
    reports, n = [], 0
    with open(args.out, mode, encoding="utf-8") as fo:
        for i, pair in enumerate(picks, 1):
            jid = pair.get("job_id")
            log(f"[{i}/{len(picks)}] {jid} {os.path.basename(pair['indd_path'])}")
            if args.no_indesign:
                cache = os.path.join(DUMPS, str(jid) + ".json")
                old = os.path.join(pair.get("job_dir") or "",
                                   "typeset_dump.json")
                if not (os.path.isfile(cache) or os.path.isfile(old)):
                    log("    · 덤프 없음 — 건너뜀 (--no-indesign)")
                    continue
            try:
                recs, rep = process(pair, log, min_conf=args.min_conf,
                                    force=args.force_dump)
            except Exception as e:                             # noqa: BLE001
                log(f"    [실패] {type(e).__name__}: {str(e)[:200]}")
                reports.append({"job": jid, "error": str(e)[:300]})
                continue
            for r in recs:
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += len(recs)
            reports.append(rep)
            log("    · " + json.dumps(
                {k: v for k, v in rep.items()
                 if k in ("dump_source", "align_rate", "aligned",
                          "plan_paragraphs", "elapsed_s")},
                ensure_ascii=False))

    ok = [r for r in reports if "error" not in r]
    summary = {
        "pairs_attempted": len(picks),
        "pairs_ok": len(ok),
        "pairs_failed": len(reports) - len(ok),
        "ground_truth_rows": n,
        "align_rate_mean": round(
            sum(r.get("align_rate", 0) for r in ok) / len(ok), 4) if ok else 0,
        "by_series": {},
        "human_edited_pairs": sum(1 for r in ok if r.get("human_edited")),
    }
    for r in ok:
        s = r.get("series", "?")
        summary["by_series"][s] = summary["by_series"].get(s, 0) + 1
    with open(os.path.join(CORPUS, "build_report.json"), "w",
              encoding="utf-8") as f:
        json.dump({"summary": summary, "pairs": reports}, f,
                  ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
