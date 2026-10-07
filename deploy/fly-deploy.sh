#!/bin/sh
# Fly.io 에 스튜디오를 올린다 — 최초 배포와 이후 갱신 모두 이 한 명령. (설명: deploy/README.md 1절)
#
#   fly auth login                       # 최초 1회 (yos-typeset 을 올린 계정)
#   deploy/fly-deploy.sh                 # 앱·볼륨·비밀값(없는 것만 생성)·배포·헬스
#   deploy/fly-deploy.sh fonts           # 서체 올리기 (fonts.tgz → /data/fonts)  — 최초 1회
#
# 비밀값은 없는 것만 만든다. 이미 있으면 건드리지 않는다. 밖에서 줄 수 있는 것:
#   YONE_PASSWORD  BLOB_READ_WRITE_TOKEN  ANTHROPIC_API_KEY  YOS_ORIGINS  YOS_WEBHOOK_URL  (환경변수로)
#   YONE_PASSWORD(스튜디오 로그인 비밀번호)를 안 주면 만들어서 한 번 보여 준다 — 그때 적어 둘 것.
#   ANTHROPIC_API_KEY 는 이 맥의 ~/.config/yone/env (로컬 bin/studio 가 쓰는 같은 키) 에서 읽는다.
# 올라가는 것은 **커밋된 HEAD** 뿐이다 (git archive). 다른 세션의 커밋 안 된 변경이 메인에 있어도 섞이지 않는다.
set -e
cd "$(dirname "$0")/.."
[ -f "$HOME/.config/yone/env" ] && . "$HOME/.config/yone/env"
APP=${FLY_APP:-yos-studio}
REGION=${FLY_REGION:-nrt}

fly auth whoami >/dev/null 2>&1 || { echo "✗ 먼저 fly auth login"; exit 2; }

if [ "$1" = "fonts" ]; then
  [ -f fonts.tgz ] || deploy/fonts-pack.sh
  fly ssh sftp put -a "$APP" fonts.tgz /data/fonts.tgz
  fly ssh console -a "$APP" -C "sh -c 'tar xzf /data/fonts.tgz -C /data/fonts && rm /data/fonts.tgz && ls /data/fonts | wc -l'"
  fly ssh console -a "$APP" -C "/app/deploy/entrypoint.sh doctor"
  exit 0
fi

# ── 한 번에 하나만 (2026-10-07: 세션 둘이 동시에 배포 → 빌더 충돌·고아 fly deploy·옛 코드로 되돌림) ──
# 1) 잠금: 이 맥에서 배포는 한 번에 하나. 주인이 죽은 잠금은 넘겨받는다.
LOCK=/tmp/$APP-deploy.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  owner=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    echo "✗ 다른 배포가 진행 중 — $(cat "$LOCK/info" 2>/dev/null). 끝난 뒤 다시."; exit 3
  fi
  echo "■ 주인 없는 잠금 정리 ($(cat "$LOCK/info" 2>/dev/null))"
  rm -rf "$LOCK"; mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"
echo "pid $$ · $(git rev-parse --short HEAD) · $(date '+%H:%M') 시작 · $(pwd)" > "$LOCK/info"
src=""; child=""
trap 'rm -rf "$LOCK"; [ -n "$src" ] && rm -rf "$src"' EXIT
trap '[ -n "$child" ] && kill "$child" 2>/dev/null; exit 130' INT TERM HUP   # 스크립트가 죽으면 fly deploy 도 같이 — 고아 방지
# 2) 잠금 밖에서 돈 fly deploy(다른 맥·고아 프로세스)가 있으면 멈춘다.
if pgrep -f "fly deploy .* -a $APP" >/dev/null; then
  echo "✗ 이미 돌고 있는 fly deploy -a $APP 가 있다 (pgrep -fl 'fly deploy'). 끝나거나 멈춘 뒤 다시."; exit 3
fi
# 3) origin/main 과 같은 커밋만 올린다 — 옛 HEAD(다른 워크트리·푸시 전)로 배포서버를 되돌리지 않게.
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "✗ HEAD($(git rev-parse --short HEAD)) ≠ origin/main($(git rev-parse --short origin/main)). main 을 push/pull 해 맞춘 뒤 다시."; exit 3
fi

# ── 앱 · 볼륨 ──
if ! fly apps list --json 2>/dev/null | grep -q "\"$APP\""; then
  echo "■ 앱 만들기: $APP ($REGION)"
  fly apps create "$APP" --org "${FLY_ORG:-personal}"
fi
if ! fly volumes list -a "$APP" --json 2>/dev/null | grep -q '"studio_data"'; then
  echo "■ 볼륨 만들기: studio_data 10GB"
  fly volumes create studio_data -a "$APP" --region "$REGION" --size 10 --yes
fi

# ── 비밀값 (없는 것만) ──
have=" $(fly secrets list -a "$APP" --json | python3 -c 'import json,sys; print(" ".join(x.get("name") or x["Name"] for x in json.load(sys.stdin)))') "
staged=0
set_if_missing() {
  case "$have" in *" $1 "*) return 0 ;; esac
  [ -n "$2" ] || return 0
  fly secrets set -a "$APP" --stage "$1=$2" >/dev/null && staged=1
  case "$1" in
    YONE_PASSWORD)
      echo "■ 새로 만든 $1 (스튜디오 로그인 비밀번호 — 지금만 보인다, 적어 둘 것):"
      echo "    $2" ;;
    SERVICE_TOKEN)
      echo "■ 새로 만든 $1 (contents 의 STUDIO_SERVICE_TOKEN 에 같은 값을 넣는다 — 지금만 보인다):"
      echo "    $2" ;;
    *) echo "■ 비밀값 설정: $1" ;;
  esac
}
set_if_missing YONE_PASSWORD     "${YONE_PASSWORD:-$(openssl rand -base64 12 | tr -d '=+/')}"
set_if_missing SERVICE_TOKEN     "$(openssl rand -base64 24 | tr -d '=+/')"
set_if_missing YONE_SECRET_KEY   "$(openssl rand -hex 32)"
set_if_missing YOS_ORIGINS       "${YOS_ORIGINS:-https://yos-contents-web.vercel.app,https://yos-design-web.vercel.app,https://yos-core-web.vercel.app}"
set_if_missing BLOB_READ_WRITE_TOKEN "$BLOB_READ_WRITE_TOKEN"
set_if_missing ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY"
set_if_missing YOS_WEBHOOK_URL   "$YOS_WEBHOOK_URL"

# ── 배포 (단일 머신 · 볼륨) — 커밋된 HEAD 만 ──
[ -z "$(git status --porcelain --untracked-files=no)" ] || echo "■ 주의: 커밋 안 된 변경은 올라가지 않는다 (HEAD 만 배포)"
src=$(mktemp -d)
git archive HEAD | tar -x -C "$src"
echo "■ fly deploy  $(git rev-parse --short HEAD)  $(git log -1 --format=%s | cut -c1-60)"
# --depot=false: Depot 빌더는 158MB 컨텍스트 업로드("transferring context")에서 두 번 멈췄다(2026-10-07).
# fly 자체 원격 빌더는 같은 날 끝까지 올라갔다.
fly deploy "$src" -a "$APP" --ha=false --depot=false &
child=$!
wait "$child"; child=""
fly scale count 1 -a "$APP" --yes >/dev/null 2>&1 || true
echo "■ 헬스:"
curl -fsS "https://$APP.fly.dev/api/v1/health" && echo
echo "■ 다음: deploy/fly-deploy.sh fonts   (서체 올리기, 최초 1회)"
