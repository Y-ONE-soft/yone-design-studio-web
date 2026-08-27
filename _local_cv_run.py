#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로컬 세로 변환 러너 — 웹과 같은 엔진 경로(parse→prepare→run→verify).

사용: /usr/bin/python3 _local_cv_run.py <전체(C).indd> [결과파일명] [pdf:on|off]
"""
import json
import os
import shutil
import sys
import time
import uuid

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
from engines.convert_to_vertical.engine import ConvertToVerticalEngine  # noqa


def main():
    src = os.path.abspath(os.path.expanduser(sys.argv[1]))
    result_name = sys.argv[2] if len(sys.argv) > 2 else ""
    export_pdf = sys.argv[3].split(":")[-1] if len(sys.argv) > 3 else "off"

    eng = ConvertToVerticalEngine()
    job_dir = os.path.join(config.JOBS_DIR, "cv_" + uuid.uuid4().hex[:8])
    up = os.path.join(job_dir, "uploads")
    os.makedirs(up, exist_ok=True)
    dst = os.path.join(up, os.path.basename(src))
    shutil.copy2(src, dst)
    if result_name:
        open(os.path.join(job_dir, "result_name.txt"), "w",
             encoding="utf-8").write(result_name)
    open(os.path.join(job_dir, "export_pdf.txt"), "w",
         encoding="utf-8").write(export_pdf)

    lf = open(os.path.join(job_dir, "run_console.log"), "a", encoding="utf-8")

    def log(m):
        line = time.strftime("%H:%M:%S ") + str(m)
        print(line, flush=True)
        lf.write(line + "\n")
        lf.flush()

    log(f"=== 세로 변환: {os.path.basename(src)} ===")
    log(f"job_dir={job_dir}")
    t0 = time.time()
    try:
        log("[1/4] parse")
        json_path = eng.parse({"indd": dst}, job_dir, log)
        log("[2/4] prepare_jsx")
        eng.prepare_jsx(json_path, job_dir, log)
        log("[3/4] run_indesign (S1/S2 → 재배치 → 후처리)")
        eng.run_indesign(job_dir, log)
        log("[4/4] verify")
        result = eng.verify(job_dir, log)
        log("결과: " + json.dumps(result, ensure_ascii=False)[:2000])
        log(f"총 소요 {int(time.time()-t0)//60}분")
        return 0 if result.get("ok") else 2
    except Exception as e:
        import traceback
        log("실패: " + repr(e))
        log(traceback.format_exc())
        log(f"소요 {int(time.time()-t0)//60}분")
        return 1


if __name__ == "__main__":
    sys.exit(main())
