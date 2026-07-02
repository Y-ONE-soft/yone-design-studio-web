#!/usr/bin/env python3
"""조판 실패 이력 집계 — 5단계 관측성의 판단 도구.

app.py의 _persist_failure가 남긴 실패 레코드를 읽어 유형/단계/엔진별로 집계한다.
데이터 소스(둘 다 훑음):
  1) 중앙 JSONL: ~/Library/Logs/yonestudio-failures.jsonl  (재부팅에도 유지)
  2) job 디렉터리: <repo>/jobs/*/failure.json                (개별 traceback 포함)

사용:
  python3 scripts/failure-stats.py            # 전체 집계
  python3 scripts/failure-stats.py --recent 20  # 최근 20건 상세
"""
import json
import os
import sys
import glob
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CENTRAL = os.path.expanduser("~/Library/Logs/yonestudio-failures.jsonl")


def load_records():
    recs = []
    seen = set()
    # 1) 중앙 JSONL
    if os.path.exists(CENTRAL):
        for line in open(CENTRAL, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            key = (r.get("job_id"), r.get("ts"))
            if key in seen:
                continue
            seen.add(key)
            recs.append(r)
    # 2) job_dir/failure.json (중앙에 없는 것 보강)
    for fp in glob.glob(os.path.join(REPO, "jobs", "*", "failure.json")):
        try:
            r = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        key = (r.get("job_id"), r.get("ts"))
        if key in seen:
            continue
        seen.add(key)
        recs.append(r)
    return recs


def main():
    recs = load_records()
    if not recs:
        print("실패 레코드 없음.")
        print(f"  중앙 로그: {CENTRAL} {'(있음)' if os.path.exists(CENTRAL) else '(아직 없음)'}")
        print("  → 5단계 배포 후 실사용 중 실패가 쌓이면 여기 집계됨.")
        return

    print(f"총 실패 레코드: {len(recs)}건\n")

    def show(title, key):
        print(f"[{title}]")
        c = Counter((r.get(key) or "?") for r in recs)
        for name, n in c.most_common():
            bar = "#" * min(n, 40)
            print(f"  {name:20s} {n:4d}  {bar}")
        print()

    show("유형(category)", "category")
    show("단계(stage)", "stage")
    show("엔진(material_id)", "material_id")

    # 1단계 커버리지 요약
    total = len(recs)
    covered = sum(1 for r in recs if r.get("category") == "startup_delivery")
    print(f"[1단계(자동 재시도) 커버리지]")
    pct = (covered / total * 100) if total else 0
    print(f"  startup_delivery(재시도 대상): {covered}/{total} = {pct:.0f}%")
    print(f"  나머지 {total - covered}건은 hang/EDEADLK/데이터오류 등 → 별도 대책 필요 여부 판단\n")

    n = 0
    if "--recent" in sys.argv:
        try:
            n = int(sys.argv[sys.argv.index("--recent") + 1])
        except Exception:
            n = 10
    if n:
        print(f"[최근 {n}건]")
        for r in sorted(recs, key=lambda x: x.get("ts", ""), reverse=True)[:n]:
            print(f"  {r.get('ts','?')} | {r.get('material_id','?')} | {r.get('stage','?')} "
                  f"| {r.get('category','?')} | {(r.get('error','') or '')[:80]}")


if __name__ == "__main__":
    main()
