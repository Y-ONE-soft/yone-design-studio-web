#!/bin/bash
# Yone Design Web — GDrive 미러 자동 동기화 (launchd 호출용)
#
# launchd com.yonestudio.mirror-sync가 30분 간격으로 호출.
# Flask 작업 중일 때는 skip (GDrive 부하 회피).
#
# 동기화 대상: setup-mirror.sh의 SUBPATHS와 동일하게 유지.

set -u

GDRIVE_BASE="$HOME/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비"
# 미러는 iCloud "데스크탑 및 문서"(~/Documents) 밖에 둔다 — 안에 두면 iCloud가
# dataless로 evict해 읽을 때 EDEADLK 재발. ~/Library 는 iCloud 미동기화.
MIRROR_BASE="${YONE_MIRROR_BASE:-$HOME/Library/Application Support/yone-design-web/content-mirror}"
JOBS_DIR="$HOME/dev/yone-design-web/jobs"
LOG="$HOME/Library/Logs/yone-mirror-sync.log"

SUBPATHS=(
    "모의고사 작업/고1"
    "모의고사 작업/고2"
    "EBS 작업"
    "교과서 작업"
    "인디자인 파일/워크북/모의고사"
    # 직전보충 학교 워크북 — 시험기간별 폴더. 시험기간이 바뀌면 아래 줄을 갱신.
    "인디자인 파일/워크북/26-1-기말"
    # 직전보충 고3 워크북 — 학년도별 폴더. 학년도가 바뀌면 아래 줄을 갱신.
    "인디자인 파일/워크북/고3 EBS 수능특강/2027"
    "인디자인 파일/Y.ONE WEB/인디자인 원본"
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

    # rsync 자체 retry 루프 — GDrive Stream EDEADLK는 일시적이지만 단일 호출
    # 안에서 만나면 그 사이클 내내 못 풀린다. 대기 후 재시도하면 대부분 회복.
    # --partial: 일부 전송된 파일 보존 (재시도가 이어 받음)
    # --partial-dir: stale 부분 파일을 별도 폴더에 격리 (조판 코드가 안 읽도록)
    # --delete: GDrive에서 rename/삭제된 파일을 미러에서도 제거.
    #   (2026-08-07 사고: '전체(C)→전체' 일괄 rename 후 미러에 옛 이름이
    #    영구 잔존 → mockexam_sero_merge가 미러만 listdir 해서 옛 목록을 보고
    #    "세로버전 파일을 찾지 못한 회차" 오류. 미러 58개 중 49개가 유령이었다.)
    #   안전: rsync는 I/O 오류(EDEADLK 등)가 발생한 실행에서는 삭제를 스킵한다
    #   (--ignore-errors 미지정 시 기본 동작) → 부분 실패로 미러가 비는 일 없음.
    #   --exclude 대상은 --delete-excluded 없이는 삭제되지 않는다.
    attempt=0
    success=0
    while [ $attempt -lt 3 ]; do
        attempt=$((attempt + 1))
        # --fuzzy: rename된 파일은 목적지의 유사 이름 파일을 basis로 써서
        #   GDrive 재다운로드를 피한다 (전체(C)→전체 같은 일괄 rename 대비).
        if rsync -a --delete --fuzzy --exclude=".*" --partial \
                 --partial-dir=".rsync-partial" \
                 "$src" "$dst" >> "$LOG" 2>&1; then
            success=1
            break
        fi
        # 실패 — deadlock 풀리길 기다리고 재시도
        if [ $attempt -lt 3 ]; then
            sleep 10
        fi
    done

    if [ $success -eq 1 ]; then
        : # 성공 — 조용히
    else
        echo "[$(ts)] [실패] $sub (${attempt}회 시도)" >> "$LOG"
        FAIL=$((FAIL + 1))
    fi
done

if [ "$FAIL" -eq 0 ]; then
    echo "[$(ts)] sync 완료 ($(du -sh "$MIRROR_BASE" 2>/dev/null | cut -f1))" >> "$LOG"
else
    echo "[$(ts)] sync 완료 (${FAIL}개 실패)" >> "$LOG"
fi
