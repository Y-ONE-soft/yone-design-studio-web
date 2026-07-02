#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 동형모의고사 조판 러너 (통합웹 안 거치고 InDesign 직접).
사용: python3 _local_mockexam_run.py <학교> <학년> <시험기간> <exam_date> <exam_type> <원고1> [원고2 ...]
예:  python3 _local_mockexam_run.py 세종고 고1 26-1-기말 2026-07-03 기말 /path/1회.hwpx
"""
import os, sys, json, time, uuid, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
envp = os.path.join(BASE, ".env")
if os.path.exists(envp):
    for line in open(envp, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import config  # noqa
from engines.mockexam.engine import MockexamEngine  # noqa


def main():
    school, grade, exam_period, exam_date, exam_type = sys.argv[1:6]
    manuscripts = sys.argv[6:]

    eng = MockexamEngine()
    job_dir = os.path.join(config.JOBS_DIR, "mock_" + uuid.uuid4().hex[:8])
    up = os.path.join(job_dir, "uploads")
    os.makedirs(up, exist_ok=True)

    # copy manuscripts into uploads
    local_files = []
    for m in manuscripts:
        dst = os.path.join(up, os.path.basename(m))
        shutil.copy(m, dst)
        local_files.append(dst)

    for key, val in [("school", school), ("grade", grade), ("exam_period", exam_period),
                     ("exam_date", exam_date), ("exam_type", exam_type)]:
        open(os.path.join(job_dir, key + ".txt"), "w", encoding="utf-8").write(val)

    lf = open(os.path.join(job_dir, "run_console.log"), "a", encoding="utf-8")
    def log(m):
        line = time.strftime("%H:%M:%S ") + str(m)
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    log(f"=== 동형모의고사 조판: {school}/{grade}/{exam_period} ===")
    log(f"job_dir={job_dir}")
    try:
        log("[1/4] 파싱...")
        json_path = eng.parse({"manuscripts": local_files}, job_dir, log)
        log(f"  content: {json_path}")
        log("[2/4] JSX 준비...")
        eng.prepare_jsx(json_path, job_dir, log)
        log("[3/4] InDesign 조판...")
        eng.run_indesign(job_dir, log)
        log("[4/4] 검수...")
        result = eng.verify(job_dir, log)
        log("결과: " + json.dumps(result, ensure_ascii=False)[:1500])
        open(os.path.join(job_dir, "result.json"), "w", encoding="utf-8").write(
            json.dumps(result, ensure_ascii=False, indent=2))
        log("=== 완료 ===")
        print("JOB_DIR=" + job_dir)
    except Exception as e:
        import traceback
        log("[오류] " + str(e)); log(traceback.format_exc())
        print("JOB_DIR=" + job_dir); sys.exit(1)


if __name__ == "__main__":
    main()
