#!/bin/bash
# ============================================================
# InDesign 상시가동(warm) keepalive
#   - InDesign이 꺼져 있으면 최신 설치 버전을 실행해 warm 상태 유지
#   - 이미 실행 중이면(렌더 중 포함) 아무것도 하지 않음 → 렌더 방해 없음
#   - 문서를 열지 않음(빈 InDesign만 warm). 콜드스타트(최대 120초) 제거 목적
#
# launchd(com.yonestudio.indesign-keepalive)가 주기 실행.
# 렌더 어플라이언스 맥에서만 활성화(사람이 상주하는 맥에서는 불필요).
# ============================================================
set -u

LOG="$HOME/Library/Logs/yonestudio-indesign-keepalive.log"
VERSIONS=(2026 2025 2024 2023 2022)

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 실행 중 여부는 System Events로 확인(앱을 실제 론치시키지 않는 방식).
# tell application "AppName" 방식은 앱을 켜버리므로 사용 금지.
is_running() {
    local app_name="$1"
    local r
    r=$(osascript -e "tell application \"System Events\" to (name of processes) contains \"$app_name\"" 2>/dev/null)
    [ "$r" = "true" ]
}

# 설치된 최신 InDesign 선택
APP=""
for v in "${VERSIONS[@]}"; do
    if [ -d "/Applications/Adobe InDesign $v" ]; then
        APP="Adobe InDesign $v"
        break
    fi
done

if [ -z "$APP" ]; then
    echo "[$(ts)] InDesign 미설치 — skip" >> "$LOG"
    exit 0
fi

# 이미 실행 중이면 건드리지 않음(렌더 중일 수 있으므로 절대 재실행/종료 안 함)
if is_running "$APP"; then
    exit 0
fi

# 꺼져 있으면 warm하게 실행(문서 없이). open -a는 이미 실행 중이어도 안전하지만
# 위에서 이미 미실행 확인함.
echo "[$(ts)] $APP 미실행 감지 — warm 실행" >> "$LOG"
open -a "/Applications/$APP" >> "$LOG" 2>&1 || echo "[$(ts)] 실행 실패" >> "$LOG"
