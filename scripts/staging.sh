#!/bin/bash
# 스테이징 Flask — summer-2026 워크트리를 포트 5011로 기동.
#
# 사용:
#   scripts/staging.sh          # 포그라운드 실행 (Ctrl-C로 종료)
#   scripts/staging.sh stop     # 백그라운드 기동분 종료
#
# 실서비스(5010, main 체크아웃)와 완전 분리:
#   - 코드: 이 워크트리 (summer-2026)
#   - jobs/: 워크트리 자체 jobs/ (config.JOBS_DIR = BASE_DIR/jobs)
#   - 포트: YONE_PORT=5011
# 비밀번호/경로(.env)는 실서비스 것을 공유한다 (읽기 전용 사용).

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROD_ENV="$HOME/dev/yone-design-web/.env"
PIDFILE="/tmp/yone-staging-5011.pid"

if [ "$1" = "stop" ]; then
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        kill "$(cat "$PIDFILE")" && rm -f "$PIDFILE"
        echo "스테이징(5011) 종료"
    else
        pkill -f "YONE_STAGING_MARK" 2>/dev/null && echo "스테이징 종료(pkill)" \
            || echo "실행 중인 스테이징 없음"
    fi
    exit 0
fi

cd "$REPO" || exit 1

if [ -f "$PROD_ENV" ]; then
    set -a
    . "$PROD_ENV"
    set +a
fi

export YONE_PORT=5011
export YONE_STAGING_MARK=1   # pkill 식별용

# 실서비스와 동일한 인터프리터/site-packages (충실도)
export PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages"
echo "스테이징 기동: http://localhost:5011 (워크트리: $REPO)"
echo $$ > "$PIDFILE"
exec /usr/bin/python3 app.py
