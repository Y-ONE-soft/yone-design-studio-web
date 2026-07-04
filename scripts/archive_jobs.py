#!/usr/bin/env python3
"""jobs/ 보존 정책 스크립트 — 90일 초과 job 디렉터리를 jobs_archive/로 이동.

리스크분석 C1-2 (jobs/ 6.2GB, 정리 로직 없음) 대응.

동작
----
- 대상: config.JOBS_DIR (기본: 리포 루트의 jobs/) 바로 아래의 job 디렉터리.
- 기준: 디렉터리 내 파일들의 가장 최근 수정 시각(mtime)이 --days(기본 90)일 초과.
- 처리: 삭제하지 않고 jobs_archive/<job_id>/ 로 **이동**(shutil.move).
  jobs_archive/ 는 gitignore 대상이라 저장소를 오염시키지 않음.
- 제외: 골든 코퍼스로 승격된 job — tests/corpus/*/*/manifest.json 의
  "source_job" 값과 일치하는 job_id 는 절대 이동하지 않음.
- 기본은 --dry-run (아무것도 이동하지 않고 목록만 출력). 실제 이동은 --apply.

사용
----
    python3 scripts/archive_jobs.py                 # dry-run (기본)
    python3 scripts/archive_jobs.py --apply         # 실제 이동
    python3 scripts/archive_jobs.py --days 30       # 기준일 변경
    python3 scripts/archive_jobs.py --jobs-dir /path/to/jobs --dry-run

자동화 제안 (launchd — 등록은 사용자 결정, 이 스크립트는 등록하지 않음)
----------------------------------------------------------------------
매주 1회 dry-run 결과를 로그로 남기고, 확인 후 수동 --apply 하는 운용을 권장.
자동 실행을 원하면 아래와 같은 LaunchAgent plist를 등록할 수 있다:

    ~/Library/LaunchAgents/com.yonestudio.archive-jobs.plist
    ProgramArguments: /usr/bin/python3 <repo>/scripts/archive_jobs.py --apply
    StartCalendarInterval: 매주 일요일 04:00
    StandardOutPath: ~/Library/Logs/yonestudio-archive-jobs.log

단, 실서비스 jobs/ 에 --apply 를 걸기 전에 반드시 dry-run 목록을 확인할 것.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_corpus_source_jobs(repo_root: str) -> set:
    """tests/corpus/*/*/manifest.json 의 source_job 값 수집 (아카이브 제외 대상)."""
    protected = set()
    pattern = os.path.join(repo_root, "tests", "corpus", "*", "*", "manifest.json")
    for path in glob.glob(pattern):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        src = data.get("source_job")
        if src:
            protected.add(str(src))
    return protected


def newest_mtime(path: str) -> float:
    """디렉터리 내 가장 최근 mtime (파일 없으면 디렉터리 자체 mtime)."""
    latest = os.path.getmtime(path)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            try:
                m = os.path.getmtime(os.path.join(root, name))
            except OSError:
                continue
            if m > latest:
                latest = m
    return latest


def collect_targets(jobs_dir: str, days: int, protected: set):
    """(이동 대상, 보호로 건너뛴 것) 목록 반환. 각 항목은 (job_id, age_days)."""
    cutoff = time.time() - days * 86400
    targets, skipped_protected = [], []
    if not os.path.isdir(jobs_dir):
        return targets, skipped_protected
    for name in sorted(os.listdir(jobs_dir)):
        path = os.path.join(jobs_dir, name)
        if name.startswith(".") or not os.path.isdir(path):
            continue
        mtime = newest_mtime(path)
        if mtime >= cutoff:
            continue
        age = (time.time() - mtime) / 86400
        if name in protected:
            skipped_protected.append((name, age))
        else:
            targets.append((name, age))
    return targets, skipped_protected


def dir_size(path: str) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="90일 초과 job 디렉터리를 jobs_archive/로 이동 (삭제 아님)")
    ap.add_argument("--days", type=int, default=90, help="보존 기간(일), 기본 90")
    ap.add_argument("--jobs-dir", default=None,
                    help="jobs 디렉터리 (기본: config.JOBS_DIR)")
    ap.add_argument("--archive-dir", default=None,
                    help="아카이브 디렉터리 (기본: <repo>/jobs_archive)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="이동하지 않고 목록만 출력 (기본)")
    mode.add_argument("--apply", action="store_true",
                      help="실제로 이동 수행")
    args = ap.parse_args(argv)

    jobs_dir = args.jobs_dir
    if not jobs_dir:
        sys.path.insert(0, REPO)
        import config
        jobs_dir = config.JOBS_DIR
    jobs_dir = os.path.abspath(jobs_dir)
    archive_dir = os.path.abspath(args.archive_dir
                                  or os.path.join(REPO, "jobs_archive"))

    protected = find_corpus_source_jobs(REPO)
    targets, skipped = collect_targets(jobs_dir, args.days, protected)

    mode_label = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode_label}] jobs_dir={jobs_dir}")
    print(f"[{mode_label}] archive_dir={archive_dir}")
    print(f"[{mode_label}] 기준: {args.days}일 초과 / 코퍼스 보호 job {len(protected)}개")

    if skipped:
        for name, age in skipped:
            print(f"  [보호] {name} ({age:.0f}일) — 골든 코퍼스 source_job, 이동 안 함")
    if not targets:
        print(f"[{mode_label}] 이동 대상 없음")
        return 0

    total_bytes = 0
    for name, age in targets:
        src = os.path.join(jobs_dir, name)
        size = dir_size(src)
        total_bytes += size
        print(f"  [대상] {name} ({age:.0f}일, {size / 1e6:.1f}MB)")
        if args.apply:
            os.makedirs(archive_dir, exist_ok=True)
            dst = os.path.join(archive_dir, name)
            if os.path.exists(dst):
                print(f"  [건너뜀] {name} — 아카이브에 이미 존재")
                continue
            shutil.move(src, dst)
            print(f"  [이동됨] {name} → {dst}")

    print(f"[{mode_label}] 대상 {len(targets)}개, 합계 {total_bytes / 1e6:.1f}MB"
          + ("" if args.apply else " — 실제 이동하려면 --apply"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
