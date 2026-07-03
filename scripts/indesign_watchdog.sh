#!/bin/bash
# InDesign watchdog — 야간 E2E 배치/조판 전 InDesign 가용성 보장.
#
# 사용:
#   scripts/indesign_watchdog.sh status   # running | hung | stopped (+종료코드 0/1/2)
#   scripts/indesign_watchdog.sh ensure   # 꺼져 있으면 백그라운드로 실행 후 응답 대기
#
# 정책 (CLAUDE.md 작업 중 파일 보호 규칙):
#   - 자동으로 실행(open)은 하되, 절대 자동으로 종료/강제재시작하지 않는다.
#     hung 상태는 보고만 한다 — 열려 있는 작업 파일을 백업 없이 죽이지 않기 위함.

APP="Adobe InDesign 2026"
WAIT_LIMIT=120   # ensure 시 응답 대기 상한 (초)

# 메인 프로세스만 매칭 (CEPHtmlEngine 등 헬퍼 잔존 프로세스 오인 방지)
_running() { pgrep -fq "Contents/MacOS/Adobe InDesign" ; }

_ping() {
    # 10초 안에 name 응답 없으면 hung으로 간주
    osascript -e "with timeout of 10 seconds" \
              -e "tell application \"$APP\" to get name" \
              -e "end timeout" >/dev/null 2>&1
}

case "${1:-status}" in
  status)
    if ! _running; then echo "stopped"; exit 2; fi
    if _ping; then echo "running"; exit 0; fi
    echo "hung"; exit 1
    ;;
  ensure)
    if _running; then
        if _ping; then echo "running (응답 정상)"; exit 0; fi
        echo "!! InDesign이 떠 있으나 무응답(hung). 자동 재시작하지 않음 —" \
             "열린 파일 확인 후 수동 재시작 필요." >&2
        exit 1
    fi
    echo "InDesign 미실행 — 백그라운드 기동: $APP"
    open -gja "$APP" || { echo "!! open 실패" >&2; exit 1; }
    for i in $(seq 1 $WAIT_LIMIT); do
        sleep 1
        if _ping; then echo "기동 완료 (${i}s)"; exit 0; fi
    done
    echo "!! ${WAIT_LIMIT}s 내 응답 없음" >&2
    exit 1
    ;;
  *)
    echo "사용법: $0 {status|ensure}" >&2; exit 64
    ;;
esac
