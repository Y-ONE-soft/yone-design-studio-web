#!/bin/bash
# =============================================================================
# backup_assets.sh — 재해복구 백업 공백 톱3 해소 (docs/재해복구_절차.md 4절)
#
#   ① config : 서비스 기동 구성(.env / launchd plist / start_flask.sh / ~/.cloudflared)
#               → tar.gz(600) 로컬 ~/Backups/config/ + GDrive yone_backups/config/
#   ② jsx    : 수동 InDesign 스크립트(조판/인디자인 스크립트/)
#               → main 체크아웃 manual_jsx_mirror/ 로 rsync 미러 (autosync가 커밋·push)
#   ③ data   : data_corpus(814M, summer 워크트리) + jobs(6.2G, main 체크아웃)
#               → GDrive yone_backups/data/ 로 rsync 증분 (--delete 없음, 누적 보존)
#
# 사용법:  backup_assets.sh [all|config|jsx|data]   (기본 all)
# launchd: com.yonestudio.backup(주간 일 04:00, all) / com.yonestudio.jsx-mirror(매일 05:00, jsx)
#
# 원칙 (2026-07-04 autosync 사고 교훈):
#   - 조용한 실패 금지 — 섹션 실패 시 macOS 알림(osascript, fail-open) + 로그.
#   - 기존 파일 이동/수정 금지 — 백업은 전부 신규 사본 생성. GDrive 기존 폴더 불가침,
#     전용 신규 폴더 yone_backups/ 만 사용. 보관 개수 초과 삭제도 자기가 만든
#     config_*.tar.gz 만 대상.
#   - 비밀값(.env 등) 내용은 로그에 절대 출력하지 않는다 — 경로/크기만.
# =============================================================================
set -u

MODE="${1:-all}"
LOG="$HOME/Library/Logs/yone-backup.log"
MAIN_REPO="$HOME/dev/yone-design-web"
SUMMER_REPO="$HOME/dev/yone-design-web-summer"
GDRIVE_BASE="$HOME/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/yone_backups"
LOCAL_CONFIG_DIR="$HOME/Backups/config"
JSX_SRC="$HOME/Documents/작업/Y.ONE STUDIO/조판/인디자인 스크립트"
JSX_MIRROR="$MAIN_REPO/manual_jsx_mirror"
KEEP_LOCAL=8   # 로컬 config tar 보관 개수
KEEP_GDRIVE=4  # GDrive config tar 보관 개수

mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1

log() { echo "[$(date '+%F %T')] $*"; }

notify() {  # fail-open: 알림 실패해도 백업 흐름은 계속
    osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null || true
}

FAIL=0
fail() {  # $1=섹션 $2=메시지 — 로그 + 알림, 종료는 하지 않음(다른 섹션 계속)
    log "!! [$1] $2"
    notify "yone 백업 실패: $1" "$2 — $LOG 확인"
    FAIL=1
}

# GDrive 마운트 확인 (미마운트 상태에서 mkdir하면 로컬 유령 폴더가 생김)
gdrive_ok() {
    [ -d "$(dirname "$GDRIVE_BASE")" ]
}

# ---------------------------------------------------------------- ① config --
backup_config() {
    log "-- [config] 서비스 기동 구성 백업 시작"
    local stamp out
    stamp=$(date '+%Y%m%d_%H%M')
    out="$LOCAL_CONFIG_DIR/config_${stamp}.tar.gz"
    mkdir -p "$LOCAL_CONFIG_DIR"

    # 대상 수집 (존재하는 것만, / 기준 상대 경로로 tar)
    local items=() f
    [ -f "$MAIN_REPO/.env" ] && items+=("${MAIN_REPO#/}/.env")
    for f in "$HOME"/Library/LaunchAgents/com.yone*.plist; do
        [ -f "$f" ] && items+=("${f#/}")
    done
    [ -f "$HOME/start_flask.sh" ] && items+=("${HOME#/}/start_flask.sh")
    [ -d "$HOME/.cloudflared" ] && items+=("${HOME#/}/.cloudflared")

    if [ ${#items[@]} -eq 0 ]; then
        fail "config" "백업 대상이 하나도 없음 (경로 확인 필요)"
        return 1
    fi

    if ! tar czf "$out" -C / "${items[@]}"; then
        rm -f "$out"
        fail "config" "tar 생성 실패: $out"
        return 1
    fi
    chmod 600 "$out"
    log "   tar 생성: $out ($(stat -f%z "$out") bytes, 항목 ${#items[@]}개)"

    # GDrive 사본 (신규 파일 생성만)
    if gdrive_ok; then
        mkdir -p "$GDRIVE_BASE/config"
        if cp "$out" "$GDRIVE_BASE/config/"; then
            log "   GDrive 사본: $GDRIVE_BASE/config/config_${stamp}.tar.gz"
        else
            fail "config" "GDrive 사본 복사 실패 (로컬 tar는 생성됨)"
        fi
    else
        fail "config" "GDrive 미마운트 — GDrive 사본 생략 (로컬 tar는 생성됨)"
    fi

    # 보관 개수 정리 — 자기가 만든 config_*.tar.gz 만 삭제 (다른 파일 불가침)
    ls -t "$LOCAL_CONFIG_DIR"/config_*.tar.gz 2>/dev/null | tail -n +$((KEEP_LOCAL + 1)) \
        | while IFS= read -r old; do rm -f "$old" && log "   로컬 보관 초과 삭제: $old"; done
    if gdrive_ok && [ -d "$GDRIVE_BASE/config" ]; then
        ls -t "$GDRIVE_BASE/config"/config_*.tar.gz 2>/dev/null | tail -n +$((KEEP_GDRIVE + 1)) \
            | while IFS= read -r old; do rm -f "$old" && log "   GDrive 보관 초과 삭제: $old"; done
    fi
    log "-- [config] 완료"
}

# ------------------------------------------------------------------- ② jsx --
backup_jsx() {
    log "-- [jsx] 수동 JSX 미러 시작 ($JSX_SRC → $JSX_MIRROR)"
    if [ ! -d "$JSX_SRC" ]; then
        fail "jsx" "원본 폴더 없음: $JSX_SRC"
        return 1
    fi

    # iCloud dataless 파일 강제 materialize (원본은 읽기만)
    find "$JSX_SRC" -type f -exec cat {} + > /dev/null 2>&1 || true

    mkdir -p "$JSX_MIRROR"
    # README는 미러 전용 파일 — rsync --delete 로부터 보호(exclude는 수신측 삭제도 제외)
    if [ ! -f "$JSX_MIRROR/README.md" ]; then
        cat > "$JSX_MIRROR/README.md" <<'EOF'
# manual_jsx_mirror — 수동 InDesign 스크립트 미러본

이 디렉터리는 **읽기 전용 미러**입니다. 원본은 아래 경로이며, 수정은 반드시 원본에서 하세요.

- 원본: `~/Documents/작업/Y.ONE STUDIO/조판/인디자인 스크립트/`
- 동기화: `scripts/backup_assets.sh jsx` (launchd `com.yonestudio.jsx-mirror`, 매일 05:00)
  가 rsync --delete 로 원본 → 이곳을 미러하고, main autosync(3분)가 커밋·push합니다.
- 여기서 파일을 고쳐도 다음 동기화 때 원본 상태로 덮어써집니다.

버전 이력이 없던 iCloud 유일본(~100개 .jsx)에 git 버전관리를 부여하기 위한 장치입니다
(docs/재해복구_절차.md 4절 3번 백업 공백 해소, 2026-07-06).
EOF
        log "   README.md 생성"
    fi

    if rsync -a --delete --exclude '.DS_Store' --exclude 'README.md' \
             "$JSX_SRC/" "$JSX_MIRROR/"; then
        local n
        n=$(find "$JSX_MIRROR" -type f ! -name 'README.md' | wc -l | tr -d ' ')
        log "   미러 완료: ${n}개 파일 (커밋·push는 main autosync가 3분 내 수행)"
    else
        fail "jsx" "rsync 미러 실패 (exit $?)"
        return 1
    fi
    log "-- [jsx] 완료"
}

# ------------------------------------------------------------------ ③ data --
# rsync 한 쌍 실행 + exit code / 파일 수 대조를 로그에 남긴다.
_rsync_to_gdrive() {  # $1=이름 $2=원본dir $3=대상dir
    local name="$1" src="$2" dst="$3" rc src_n dst_n
    log "   [$name] rsync 시작: $src → $dst"
    mkdir -p "$dst"
    # GDrive FUSE는 perms/owner 설정을 거부할 수 있어 내용+시간만 동기화(-rt).
    # --delete 없음: 원본에서 지워져도 백업본은 누적 보존.
    rsync -rt --partial --exclude '.DS_Store' "$src/" "$dst/"
    rc=$?
    src_n=$(find "$src" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
    dst_n=$(find "$dst" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
    log "   [$name] rsync 종료: exit=$rc, 원본 ${src_n}개 / 백업 ${dst_n}개 파일"
    if [ "$rc" -ne 0 ]; then
        fail "data/$name" "rsync exit $rc (원본 ${src_n} vs 백업 ${dst_n})"
        return 1
    fi
    if [ "$dst_n" -lt "$src_n" ]; then
        fail "data/$name" "파일 수 부족: 원본 ${src_n} vs 백업 ${dst_n}"
        return 1
    fi
    log "   [$name] 검증 통과 (백업 ${dst_n} >= 원본 ${src_n})"
}

backup_data() {
    log "-- [data] data_corpus + jobs GDrive 백업 시작"
    if ! gdrive_ok; then
        fail "data" "GDrive 미마운트 — data 백업 전체 생략"
        return 1
    fi
    mkdir -p "$GDRIVE_BASE/data"
    local ok=0
    _rsync_to_gdrive "data_corpus" "$SUMMER_REPO/data_corpus" "$GDRIVE_BASE/data/data_corpus" || ok=1
    _rsync_to_gdrive "jobs"        "$MAIN_REPO/jobs"          "$GDRIVE_BASE/data/jobs"        || ok=1
    [ "$ok" -eq 0 ] && log "-- [data] 완료" || log "-- [data] 일부 실패 (위 로그 참조)"
    return "$ok"
}

# ------------------------------------------------------------------- main ---
log "===== backup_assets.sh 시작 (mode=$MODE) ====="
case "$MODE" in
    config) backup_config ;;
    jsx)    backup_jsx ;;
    data)   backup_data ;;
    all)
        backup_config
        backup_jsx
        backup_data
        ;;
    *)
        log "!! 알 수 없는 모드: $MODE (all|config|jsx|data)"
        FAIL=1
        ;;
esac
log "===== backup_assets.sh 종료 (mode=$MODE, fail=$FAIL) ====="
exit "$FAIL"
