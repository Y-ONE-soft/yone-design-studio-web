#!/bin/bash
# 자동 git pull — 5분 간격으로 launchd가 실행.
# 활성 작업(0이 아닌 jobs/)이 있으면 pull 건너뜀 (조교 작업 중단 방지).
# pull 결과 변경이 있으면 Flask가 auto-reload(debug 모드)로 자동 반영.

set -e
cd "/Users/nhj/dev/yone-design-web" || exit 1

LOG="$HOME/Library/Logs/yone-auto-pull.log"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

log() { echo "[$TS] $1" >> "$LOG"; }

# 1) 활성 작업 가드 — jobs/ 안에 최근 5분 내 수정된 폴더가 있으면 작업 중으로 간주
ACTIVE=$(find ./jobs -maxdepth 1 -type d -mmin -5 2>/dev/null | grep -v '^\./jobs$' | head -1)
if [ -n "$ACTIVE" ]; then
    log "활성 작업 감지 ($ACTIVE) — pull 건너뜀"
    exit 0
fi

# 2) git fetch — 원격에 변경 있는지 확인
git fetch origin main --quiet 2>>"$LOG" || { log "fetch 실패"; exit 1; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    # 변경 없음 — 조용히 종료 (로그도 안 남김, 너무 자주 호출되므로)
    exit 0
fi

# 3) pull — 변경 있을 때만
log "변경 감지: $LOCAL → $REMOTE / pull 시작"
git pull --ff-only origin main >>"$LOG" 2>&1 || { log "pull 실패 (충돌? rebase 필요?)"; exit 1; }
log "pull 완료 → Flask auto-reload 대기"

# 4) Flask는 debug+reloader라 파일 변경 감지하면 자동 재시작.
#    명시적으로 touch app.py 해서 reload 트리거 (만약을 위해).
touch app.py
log "Flask reload 트리거 완료"
