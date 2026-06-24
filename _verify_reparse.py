#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검증용: 기존 extracted.json 재사용(_REUSE_EXTRACTED)으로 parse만 재실행."""
import os, sys, time
os.environ["_REUSE_EXTRACTED"] = "1"
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
envp = os.path.join(BASE, ".env")
if os.path.exists(envp):
    for line in open(envp, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import config
from engines.final.engine import FinalEngine

job_dir = os.path.join(BASE, "jobs", "verify_e0ab94a0")

def log(m):
    print(time.strftime("%H:%M:%S "), str(m), flush=True)

eng = FinalEngine()
try:
    p = eng.parse({}, job_dir, log)
    log("PARSE_DONE: " + str(p))
except Exception as e:
    import traceback
    log("PARSE_ERROR: " + str(e))
    log(traceback.format_exc())
    sys.exit(1)
