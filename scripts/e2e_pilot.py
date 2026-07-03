#!/usr/bin/env python3
"""검수 게이트 E2E 파일럿 — 코퍼스 케이스 1건을 실제 InDesign으로 조판 후 검수.

사용: python3 scripts/e2e_pilot.py workbook/134be69f

파이프라인: parse → prepare_jsx → run_jsx(InDesign) → dump_indd → inspect
안전장치:
  - 출력 .indd/PDF는 실서비스 폴더가 아닌 data_corpus/e2e/<case>/ 로 리다이렉트
  - 원본 템플릿(조판/인디자인 원본/)은 읽기(복사 소스)로만 사용
  - 사용자 InDesign 열린 문서는 건드리지 않음 (자체 사본만 열고 닫음)
"""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

# 실서비스 .env 로드 (YONE_STUDIO_ROOT / INDD_ORIGINAL_BASE 등 — config import 전에)
_ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.isfile(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import _replay  # noqa: E402


def main():
    case_rel = sys.argv[1] if len(sys.argv) > 1 else "workbook/134be69f"
    engine_id, case_id = case_rel.split("/")
    if engine_id != "workbook":
        print("파일럿은 workbook 전용 (Step3 비교기 기준)")
        return 2

    case_dir = os.path.join(REPO, "tests", "corpus", engine_id, case_id)
    out_root = os.path.join(REPO, "data_corpus", "e2e", case_id)
    job_dir = os.path.join(out_root, "job")
    os.makedirs(job_dir, exist_ok=True)

    # ── 출력 경로 리다이렉트: indd_output_dir → 스크래치 ──────────────────
    import engines.workbook.engine as wb
    _orig_load = wb._load_config

    def _patched_load():
        cfg = _orig_load()
        cfg["indd_output_dir"] = out_root
        return cfg

    wb._load_config = _patched_load

    from engines import registry
    engine = registry.get("workbook")
    log = lambda m: print(f"  {m}", flush=True)

    print(f"== 1/5 parse ({case_rel})")
    produced = _replay.replay(engine, case_dir, job_dir)
    json_path = os.path.join(job_dir, "content.json")

    print("== 2/5 prepare_jsx (출력 → data_corpus/e2e)")
    jsx_path = engine.prepare_jsx(json_path, job_dir, log)
    settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                              encoding="utf-8"))
    indd_path = settings["indd_path"]
    assert indd_path.startswith(out_root), f"리다이렉트 실패! {indd_path}"
    print(f"  출력 indd: {indd_path}")

    print("== 3/5 InDesign 조판")
    from core.indesign import runner
    t0 = time.time()
    runner.run_jsx(jsx_path, log,
                   poll_log_path=os.path.join(job_dir, "조판_로그.txt"),
                   timeout=getattr(engine, "jsx_timeout", 900))
    print(f"  조판 {time.time() - t0:.0f}초")

    print("== 4/5 스토리 덤프")
    from core.inspect import dump_indd, inspect_workbook_step3
    dump = dump_indd(indd_path, os.path.join(job_dir, "typeset_dump.json"), log)
    n_paras = sum(len(s.get("paragraphs", [])) for s in dump.get("stories", []))
    print(f"  스토리 {len(dump.get('stories', []))}개 / 단락 {n_paras}개")

    print("== 5/5 검수 대조")
    content = json.load(open(json_path, encoding="utf-8"))
    report = inspect_workbook_step3(content, dump)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    with open(os.path.join(job_dir, "inspect_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("\n검수:", "✅ 통과" if report["ok"] else "❌ 치명 항목 있음")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
