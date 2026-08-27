#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""분할 브레이크 규칙 실측 — 원본 사본에 대상 1건만 적용하고 결과를 로그로 본다.

사용: cv_probe_split.py <전체(C).indd> <page> <fid> <offset> [breaks]
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """인자: <indd> <targets_json> [probe_pages_csv]

    targets_json 은 [{"code","page","fid","offset"[,"breaks"]}, ...] 그대로.
    """
    src = sys.argv[1]
    targets = json.loads(sys.argv[2])
    probe = ([int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3
             else sorted({p for t in targets
                          for p in (t["page"]-1, t["page"], t["page"]+1, t["page"]+2)}))
    from core.indesign.jsxbuild import build_jsx
    from core.indesign.runner import run_jsx

    work = os.path.abspath(os.path.join("jobs", "cv_probe"))
    os.makedirs(work, exist_ok=True)
    doc = os.path.join(work, "probe.indd")
    shutil.copy2(os.path.abspath(os.path.expanduser(src)), doc)

    cfg = {"targets": targets, "probe_pages": probe}
    cfg_path = os.path.join(work, "cfg.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    log_path = os.path.join(work, "probe_로그.txt")
    for p in (log_path,):
        try:
            os.remove(p)
        except OSError:
            pass
    jsx = build_jsx(
        os.path.join("core", "jsx", "cv_split_exam.jsx"),
        {"__DOC_PATH__": doc, "__CFG_PATH__": cfg_path, "__LOG_PATH__": log_path},
        log_path=log_path, out_path=os.path.join(work, "probe.jsx"))
    run_jsx(jsx, print, poll_log_path=log_path, timeout=900,
            completion_marker="분할 완료")
    print("\n===== 실측 =====")
    print(open(log_path, encoding="utf-8").read())


if __name__ == "__main__":
    main()
