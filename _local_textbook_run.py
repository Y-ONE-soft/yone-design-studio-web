#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 교과서 워크북 조판 러너 (통합웹 안 거치고 InDesign 직접).
사용: python3 _local_textbook_run.py <subject> <publisher> <lesson> <lesson_folder> <manuscript_folder>
"""
import os, sys, json, time, uuid

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
from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine  # noqa


def main():
    subject, publisher, lesson, lesson_folder, manuscript_folder = sys.argv[1:6]

    eng = TextbookWorkbookV2Engine()
    job_dir = os.path.join(config.JOBS_DIR, "tb_" + uuid.uuid4().hex[:8])
    os.makedirs(os.path.join(job_dir, "uploads"), exist_ok=True)

    for key, val in [("subject", subject), ("publisher", publisher),
                     ("lesson", lesson), ("lesson_folder", lesson_folder),
                     ("manuscript_folder", manuscript_folder),
                     ("workbook_type", "교과서")]:
        open(os.path.join(job_dir, key + ".txt"), "w", encoding="utf-8").write(val)

    lf = open(os.path.join(job_dir, "run_console.log"), "a", encoding="utf-8")
    def log(m):
        line = time.strftime("%H:%M:%S ") + str(m)
        print(line, flush=True); lf.write(line + "\n"); lf.flush()

    log("=== 교과서 워크북 조판: %s %s %s ===" % (subject, publisher, lesson))
    log("job_dir=" + job_dir)
    try:
        log("[1/4] 파싱...")
        json_path = eng.parse({"manuscripts": []}, job_dir, log)
        log("  content: " + str(json_path))
        log("[2/4] JSX 준비...")
        eng.prepare_jsx(json_path, job_dir, log)
        log("[3/4] InDesign 조판...")
        if hasattr(eng, "run_indesign"):
            eng.run_indesign(job_dir, log)
        else:
            from core.indesign.runner import run_jsx
            run_jsx(os.path.join(job_dir, "run.jsx"), log=log)
        log("[4/4] 검수...")
        result = eng.verify(job_dir, log)
        log("결과: " + json.dumps(result, ensure_ascii=False)[:2000])
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
