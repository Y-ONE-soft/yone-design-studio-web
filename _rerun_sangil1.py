"""상일1 직전보충 재조판 — 영작/어휘 수정 검증. (검증 후 삭제)"""
import os, sys, time
os.environ["YONE_STUDIO_ROOT"] = "/Users/nhj/Documents/작업/Y.ONE STUDIO"
os.environ["INDD_ORIGINAL_BASE"] = (
    "/Users/nhj/Library/Application Support/yone-design-web/"
    "content-mirror/인디자인 파일/Y.ONE WEB/인디자인 원본"
)
os.environ["_REUSE_EXTRACTED"] = "1"
os.chdir("/Users/nhj/dev/yone-design-web")
sys.path.insert(0, "/Users/nhj/dev/yone-design-web")
import json
from engines.final.engine import FinalEngine
JOB = "/Users/nhj/dev/yone-design-web/jobs/1b36f0a8"
def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
def main():
    eng = FinalEngine()
    log("=== parse ===")
    jp = eng.parse({}, JOB, log)
    log("=== prepare_jsx ===")
    eng.prepare_jsx(jp, JOB, log)
    log("=== run_indesign ===")
    eng.run_indesign(JOB, log)
    log("=== verify ===")
    r = eng.verify(JOB, log)
    log("RESULT: " + json.dumps(r, ensure_ascii=False)[:600])
    log("=== DONE ===")
if __name__ == "__main__":
    main()
