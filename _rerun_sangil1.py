"""상일1 직전보충 재조판 — 프로덕션 환경변수 재현 + extracted.json 재사용.
parse(재파싱) → prepare_jsx → run_indesign(InDesign) → verify. (검증 후 삭제)
"""
import os, sys, time

# 프로덕션(start_flask.sh + .env) 환경 재현 — import 전에 설정해야 config.STUDIO_ROOT에 반영됨
os.environ["YONE_STUDIO_ROOT"] = "/Users/nhj/Documents/작업/Y.ONE STUDIO"
# 템플릿 '조판/인디자인 원본/' 리다이렉트 — GDrive EDEADLK 회피 위해 로컬 미러 사용
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

def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def main():
    import config
    log(f"STUDIO_ROOT={config.STUDIO_ROOT}")
    eng = FinalEngine()
    log("=== parse (재파싱, extracted.json 재사용) ===")
    json_path = eng.parse({}, JOB, log)
    log(f"parse 완료: {json_path}")
    log("=== prepare_jsx (.settings.json + 템플릿 복사) ===")
    eng.prepare_jsx(json_path, JOB, log)
    log("=== run_indesign (InDesign 조판) ===")
    eng.run_indesign(JOB, log)
    log("=== verify ===")
    result = eng.verify(JOB, log)
    log("RESULT: " + json.dumps(result, ensure_ascii=False)[:800])
    log("=== DONE ===")

if __name__ == "__main__":
    main()
