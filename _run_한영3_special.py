#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한영3 1회성 조판 — 교과서 4과 '어법X'(이번 시험범위 한정) 후처리.
parse → content.json에서 교과서 어법(어법수정/어법_헤더) 제거 → prepare_jsx → run_indesign → verify.
빌더 전역은 건드리지 않음. 교과서 배열/영작은 그대로 둠.
"""
import os, sys, json, time, uuid, re

BASE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, BASE)
envp = os.path.join(BASE, ".env")
for line in open(envp, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
import config
from engines.final.engine import FinalEngine


def strip_textbook_grammar(content_path, log):
    d = json.load(open(content_path, encoding="utf-8"))
    v2 = d.get("vol2", {})
    g = v2.get("어법수정", [])
    # [헤더, 본문] 페어 순회하며 '교과서' 헤더 페어 제거
    new_g = []
    removed = 0
    i = 0
    while i < len(g):
        h = g[i]
        body = g[i + 1] if i + 1 < len(g) else ""
        if isinstance(h, str) and h.strip().startswith("교과서"):
            removed += 1
            i += 2
            continue
        new_g.append(h)
        if i + 1 < len(g):
            new_g.append(body)
        i += 2
    v2["어법수정"] = new_g
    v2["어법_헤더"] = [h for h in v2.get("어법_헤더", []) if not str(h).startswith("교과서")]
    json.dump(d, open(content_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"[어법X] 교과서 어법 {removed}개 지문 제거 → 어법수정 {len(new_g)}줄")


def main():
    school, grade, exam = "한영3", "고3", "26-1-기말"
    engine = FinalEngine()
    job_dir = os.path.join(config.JOBS_DIR, "special_" + uuid.uuid4().hex[:8])
    os.makedirs(os.path.join(job_dir, "uploads"), exist_ok=True)
    open(job_dir + "/school.txt", "w").write(school)
    open(job_dir + "/grade.txt", "w").write(grade)
    open(job_dir + "/exam_period.txt", "w").write(exam)

    def log(m):
        print(time.strftime("%H:%M:%S "), m, flush=True)

    log(f"=== 한영3 1회성 (교과서 어법X) ===")
    jp = engine.parse({}, job_dir, log)
    strip_textbook_grammar(jp, log)
    engine.prepare_jsx(jp, job_dir, log)
    engine.run_indesign(job_dir, log)
    r = engine.verify(job_dir, log)
    log("=== 완료 ===")
    print("JOB_DIR=" + job_dir)


if __name__ == "__main__":
    main()
