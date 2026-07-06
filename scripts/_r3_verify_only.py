#!/usr/bin/env python3
"""W13 라운드3 — 기존 job의 verify(검수 게이트)만 재실행.

run_indesign이 러너 timeout으로 조기 반환했지만 InDesign이 export를
정상 완료한 경우(PDF 실재) 검수만 다시 돈다.
사용: python3 scripts/_r3_verify_only.py <c13_ybm|c15_sl2|c05_mock>
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from scripts.e2e_round3 import _CASES, _R3  # noqa: E402


def main():
    case = sys.argv[1]
    spec = _CASES[case]
    case_dir = os.path.join(_R3, case)
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    engine = spec["engine"](case_dir, out)
    log = lambda m: print(f"  {m}", flush=True)
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
