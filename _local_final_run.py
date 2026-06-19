#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 파이널 직전보충 조판 러너.

통합웹(Flask) 거치지 않고 로컬 InDesign으로 직접 조판.
사용: python3 _local_final_run.py <학교> <학년> <시험기간>
예:  python3 _local_final_run.py 한영3 고3 26-1-기말

_run_pipeline (app.py) 을 복제하되 GDrive 공유는 생략.
"""
import os
import sys
import json
import time
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# .env 로드 (python-dotenv 없이 수동)
envp = os.path.join(BASE, ".env")
if os.path.exists(envp):
    for line in open(envp, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)

from engines import registry  # noqa: E402
import config  # noqa: E402


def main():
    school = sys.argv[1]
    grade = sys.argv[2]
    exam_period = sys.argv[3]

    engine = registry.get("final")

    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(config.JOBS_DIR, "local_" + job_id)
    os.makedirs(job_dir, exist_ok=True)
    os.makedirs(os.path.join(job_dir, "uploads"), exist_ok=True)

    open(os.path.join(job_dir, "school.txt"), "w", encoding="utf-8").write(school)
    open(os.path.join(job_dir, "grade.txt"), "w", encoding="utf-8").write(grade)
    open(os.path.join(job_dir, "exam_period.txt"), "w", encoding="utf-8").write(exam_period)

    logfile = os.path.join(job_dir, "run_console.log")
    lf = open(logfile, "a", encoding="utf-8")

    def log(m):
        line = time.strftime("%H:%M:%S ") + str(m)
        print(line, flush=True)
        lf.write(line + "\n")
        lf.flush()

    log(f"=== 로컬 조판 시작: {school} / {grade} / {exam_period} ===")
    log(f"job_dir = {job_dir}")

    try:
        log("[1/3] 파싱...")
        json_path = engine.parse({}, job_dir, log)
        log(f"[1/3] 파싱 완료: {json_path}")

        log("[2/3] JSX 준비 + InDesign 조판...")
        engine.prepare_jsx(json_path, job_dir, log)
        engine.run_indesign(job_dir, log)
        log("[2/3] 조판 완료")

        log("[3/3] 검수...")
        result = engine.verify(job_dir, log)
        log(f"[3/3] 검수 결과: {json.dumps(result, ensure_ascii=False)[:2000]}")

        log("=== 완료 ===")
        # 결과 요약 파일
        open(os.path.join(job_dir, "result.json"), "w", encoding="utf-8").write(
            json.dumps(result, ensure_ascii=False, indent=2))
        print("JOB_DIR=" + job_dir)
    except Exception as e:
        import traceback
        log(f"[오류] {e}")
        log(traceback.format_exc())
        print("JOB_DIR=" + job_dir)
        sys.exit(1)


if __name__ == "__main__":
    main()
