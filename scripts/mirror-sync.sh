#!/bin/bash
# Yone Design Web — GDrive 미러 자동 동기화 (launchd 호출용)
#
# launchd com.yonestudio.mirror-sync가 30분 간격으로 호출.
# Flask 작업 중일 때는 skip (GDrive 부하 회피).
#
# 동기화 대상: setup-mirror.sh의 SUBPATHS와 동일하게 유지.

set -u

GDRIVE_BASE="$HOME/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비"
MIRROR_BASE="$HOME/Documents/yone-content-mirror"
JOBS_DIR="$HOME/dev/yone-design-web/jobs"
LOG="$HOME/Library/Logs/yone-mirror-sync.log"

SUBPATHS=(
    "모의고사 작업/고1"
    "모의고사 작업/고2"
    "EBS 작업"
    "교과서 작업"
)

ts() { date +'%Y-%m-%d %H:%M:%S'; }

# 활성 작업 감지 — 최근 5분 내 modified된 jobs/ 하위 파일 있으면 sync skip
# (Flask가 조판 중이면 GDrive 동시 access로 EDEADLK 위험)
if [ -d "$JOBS_DIR" ]; then
    if find "$JOBS_DIR" -mmin -5 -type f 2>/dev/null | head -1 | grep -q .; then
        echo "[$(ts)] 활성 작업 감지 — sync skip" >> "$LOG"
        exit 0
    fi
fi

# GDrive 마운트 확인
if [ ! -d "$GDRIVE_BASE" ]; then
    echo "[$(ts)] ERROR: GDrive 마운트 없음" >> "$LOG"
    exit 1
fi

mkdir -p "$MIRROR_BASE"

echo "[$(ts)] sync 시작" >> "$LOG"

FAIL=0
for sub in "${SUBPATHS[@]}"; do
    src="$GDRIVE_BASE/$sub/"
    dst="$MIRROR_BASE/$sub/"

    if [ ! -d "$src" ]; then
        continue
    fi

    mkdir -p "$dst"

    # rsync 단일 호출, 변경분만. EDEADLK는 set -u 없이 자동 무시 (다음 사이클에 재시도).
    if rsync -a --exclude=".*" "$src" "$dst" >> "$LOG" 2>&1; then
        : # 성공 — 조용히
    else
        echo "[$(ts)] [실패] $sub" >> "$LOG"
        FAIL=$((FAIL + 1))
    fi
done

if [ "$FAIL" -eq 0 ]; then
    echo "[$(ts)] sync 완료 ($(du -sh "$MIRROR_BASE" 2>/dev/null | cut -f1))" >> "$LOG"
else
    echo "[$(ts)] sync 완료 (${FAIL}개 실패)" >> "$LOG"
fi
