#!/bin/sh
# 컨테이너 기동: /data(Fly 볼륨) 폴더 준비 → 카탈로그가 비어 있으면 리포 것으로 채움 → gunicorn
set -e
cd /app

for d in "$YONE_STUDIO_ROOT/조판/교재" "$YONE_STUDIO_ROOT/_jobs" "$YONE_CATALOG_DIR" /data/fonts /data/icc; do
  mkdir -p "$d"
done

# 카탈로그(틀·디자인)는 볼륨이 정본. 처음 한 번만 리포 사본으로 채우고,
# 그 뒤 기동마다 리포에 **새로 생긴 틀·디자인만** 보탠다(있는 파일은 안 건드림 — deploy/catalog_sync.py).
if [ ! -f "$YONE_CATALOG_DIR/catalog.json" ]; then
  echo "■ 카탈로그 볼륨이 비어 있다 → 리포의 catalog/ 로 채운다"
  cp -a /app/catalog.seed/. "$YONE_CATALOG_DIR/"
else
  python3 /app/deploy/catalog_sync.py /app/catalog.seed "$YONE_CATALOG_DIR" || echo "■ 카탈로그 보탬 실패(무시)"
fi

# 서체 캐시(chromium 폴백용) — 우리 조판은 build/ 에 서체를 복사해 @font-face 로 쓰므로 필수는 아니다
fc-cache -f >/dev/null 2>&1 || true

FONTS=$(find /data/fonts -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
echo "■ 스튜디오 루트: $YONE_STUDIO_ROOT   서체: ${FONTS}개 (/data/fonts)   카탈로그: $YONE_CATALOG_DIR"
python3 -c "from core import webauth; print('■ 인증:', webauth.describe())"

if [ "$1" = "shell" ]; then shift; exec "${@:-sh}"; fi
if [ "$1" = "doctor" ]; then exec bin/viv-doctor; fi

# ⚠ 워커 1개 — 잡 등록부·카탈로그 잡이 프로세스 메모리에 있다. 동시 요청은 스레드로 받는다.
exec gunicorn "studio_server:create_app()" \
  --bind "0.0.0.0:${YONE_STUDIO_PORT:-5099}" \
  --workers 1 --threads "${YONE_THREADS:-16}" --worker-class gthread \
  --timeout "${YONE_REQUEST_TIMEOUT:-600}" --graceful-timeout 30 --keep-alive 5 \
  --access-logfile - --error-logfile - --log-level "${YONE_LOG_LEVEL:-info}" \
  "$@"
