#!/usr/bin/env python3
"""골든 재생성 — 현행 코드의 parse 출력을 코퍼스 골든으로 저장한다.

사용:
    python3 scripts/regen_golden.py                    # 전체
    python3 scripts/regen_golden.py workbook/01accf5a  # 특정 케이스만

골든은 canonicalize(경로 토큰화 + NFC) 후 저장되며, manifest에 재생성
시점/커밋을 기록한다. 남용 금지: 의도된 변경의 승격에만 사용하고,
왜 달라졌는지 커밋 메시지에 반드시 명시할 것 (tests/README.md).
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import _replay  # noqa: E402
from engines import registry  # noqa: E402

CORPUS = os.path.join(REPO, "tests", "corpus")


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
            text=True).strip()
    except Exception:
        return "unknown"


def regen(case_rel: str) -> bool:
    case_dir = os.path.join(CORPUS, case_rel)
    engine_id = case_rel.split("/")[0]
    engine = registry.get(engine_id)
    with tempfile.TemporaryDirectory() as tmp:
        job_dir = os.path.join(tmp, "job")
        try:
            produced = _replay.replay(engine, case_dir, job_dir)
        except Exception as e:
            print(f"  ! {case_rel}: 재실행 실패 — {e}")
            return False
        produced = _replay.canonicalize(produced, [job_dir])
    out = os.path.join(case_dir, "golden", "content.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(produced, f, ensure_ascii=False, indent=1)
    mf_path = os.path.join(case_dir, "manifest.json")
    mf = json.load(open(mf_path, encoding="utf-8"))
    mf["golden_regenerated"] = {"commit": _git_head()}
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(mf, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {case_rel}")
    return True


def main():
    targets = sys.argv[1:]
    if not targets:
        targets = [
            f"{e}/{j}"
            for e in sorted(os.listdir(CORPUS))
            if os.path.isdir(os.path.join(CORPUS, e))
            for j in sorted(os.listdir(os.path.join(CORPUS, e)))
            if os.path.isfile(os.path.join(CORPUS, e, j, "manifest.json"))
        ]
    ok = sum(regen(t) for t in targets)
    print(f"골든 재생성: {ok}/{len(targets)}")
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
