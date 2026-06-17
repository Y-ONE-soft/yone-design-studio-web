"""상일1 직전보충 재조판 — 저장된 extracted.json 재사용(_REUSE_EXTRACTED), 파서 수정 검증.
parse(재파싱) → prepare_jsx(.settings.json) → run_indesign(InDesign 조판) → verify.
(검증 후 삭제 예정)
"""
import os, sys, json, time
os.environ["_REUSE_EXTRACTED"] = "1"
sys.path.insert(0, "/Users/nhj/dev/yone-design-web")

from engines.final.engine import FinalEngine

JOB = "/Users/nhj/dev/yone-design-web/jobs/1b36f0a8"

def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def main():
    eng = FinalEngine()
    log("=== parse (재파싱, extracted.json 재사용) ===")
    json_path = eng.parse({}, JOB, log)
    log(f"parse 완료: {json_path}")
    log("=== prepare_jsx (.settings.json) ===")
    eng.prepare_jsx(json_path, JOB, log)
    log("=== run_indesign (InDesign 조판) ===")
    eng.run_indesign(JOB, log)
    log("=== verify ===")
    result = eng.verify(JOB, log)
    log("RESULT: " + json.dumps(result, ensure_ascii=False)[:500])
    log("=== DONE ===")

if __name__ == "__main__":
    main()
