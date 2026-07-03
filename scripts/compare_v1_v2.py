#!/usr/bin/env python3
"""v1(기존 mockexam) vs v2(mockexam_v2) 나란히 조판 비교.

같은 원고를 v1 파이프라인으로 실조판 → 덤프 → 기존 v2 덤프와 대조:
  - 내용(영문 실질 단어셋) 상호 차집합
  - 단락 수/스타일 분포
안전: v1 출력은 STUDIO_ROOT 패치로 data_corpus/e2e_v1/로 리다이렉트
(실서비스 조판/교재 폴더 무오염). v1 코드는 무수정 — 모듈 변수만 주입.
"""
import collections
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def words_of(dump):
    w = set()
    for st in dump["stories"]:
        for p in st["paragraphs"]:
            for m in _RE_WORD.findall(p["t"]):
                w.add(m.lower())
    return w


def style_dist(dump):
    d = collections.Counter()
    for st in dump["stories"]:
        for p in st["paragraphs"]:
            if p["t"].strip():
                d[p["s"]] += 1
    return d


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "029c4385"
    cdir = os.path.join(REPO, "tests", "corpus", "mockexam", case)
    out1 = os.path.join(REPO, "data_corpus", "e2e_v1", case)
    out2 = os.path.join(REPO, "data_corpus", "e2e_v2", case)
    os.makedirs(out1, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    # ── v1 파이프라인 (STUDIO_ROOT 리다이렉트) ──────────────────────────
    import engines.mockexam.engine as me
    me.STUDIO_ROOT = out1          # 출력: out1/조판/교재/동형모의고사/...
    import _replay
    from engines import registry
    engine = registry.get("mockexam")

    job = os.path.join(out1, "job")
    os.makedirs(job, exist_ok=True)
    print("== 1/4 v1 parse")
    _replay.build_job(cdir, job)
    uploaded = _replay.build_uploaded(engine, job)
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 v1 prepare + 조판")
    engine.prepare_jsx(json_path, job, log)
    engine.run_indesign(job, log)
    settings = json.load(open(os.path.join(job, ".settings.json"),
                              encoding="utf-8"))
    v1_indd = settings["jobs"][0]["indd_path"]
    assert v1_indd.startswith(out1), f"리다이렉트 실패: {v1_indd}"
    print(f"  v1 출력: {v1_indd}")

    print("== 3/4 v1 덤프")
    from core.inspect import dump_indd
    d1 = dump_indd(v1_indd, os.path.join(out1, "typeset_dump.json"), log)
    d2 = json.load(open(os.path.join(out2, "typeset_dump.json"),
                        encoding="utf-8"))

    print("== 4/4 대조")
    w1, w2 = words_of(d1), words_of(d2)
    plan = json.load(open(os.path.join(out2, "render_plan.json"),
                          encoding="utf-8"))
    src_words = {w.lower() for p in plan for w in _RE_WORD.findall(p["t"])}
    report = {
        "v1_paragraphs": sum(len(s["paragraphs"]) for s in d1["stories"]),
        "v2_paragraphs": sum(len(s["paragraphs"]) for s in d2["stories"]),
        "v1_overflow": d1.get("overflow_stories"),
        "v2_overflow": d2.get("overflow_stories"),
        "원고단어_v1누락": sorted(src_words - w1)[:20],
        "원고단어_v2누락": sorted(src_words - w2)[:20],
        "v1에만_있는_단어": len(w1 - w2),
        "v2에만_있는_단어": len(w2 - w1),
        "v1_스타일분포": dict(style_dist(d1).most_common(12)),
        "v2_스타일분포": dict(style_dist(d2).most_common(12)),
    }
    with open(os.path.join(out2, "compare_v1_v2.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
