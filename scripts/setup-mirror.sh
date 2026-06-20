#!/bin/bash
# Yone Design Web — GDrive 콘텐츠 로컬 미러 셋업
#
# 사용법:
#   bash scripts/setup-mirror.sh
#
# 목적: Google Drive NSFileProvider 데몬 EDEADLK 회피.
#   자주 쓰는 GDrive 콘텐츠 폴더를 로컬 미러(아래 MIRROR_BASE)로 복사. 이후
#   _gdrive_safe_copy(engines/final/extractor.py)가 자동으로 미러 우회 →
#   deadlock 자체가 발생하지 않음.
#   ※ 미러는 iCloud "데스크탑 및 문서"(~/Documents) 밖에 둔다 — 안에 두면
#     iCloud가 dataless로 evict해 이번엔 iCloud 경유 EDEADLK가 재발한다.
#
# 실행 시점:
#   1) 새 맥북/조교 컴 셋업 시 1회
#   2) GDrive 원본이 변경됐을 때 (rsync는 변경분만 전송하므로 두 번째부터 빠름)

set -e

GDRIVE_BASE="$HOME/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비"
MIRROR_BASE="${YONE_MIRROR_BASE:-$HOME/Library/Application Support/yone-design-web/content-mirror}"

# 미러할 폴더 — "내신대비/" 다음부터의 상대경로.
# 코드는 GDrive 경로의 "/내 드라이브/콘텐츠 관리/내신대비/" 뒤 경로를 그대로
# 미러 베이스에 붙여 lookup하므로, 여기 등록한 폴더는 자동으로 우회됨.
SUBPATHS=(
    "모의고사 작업/고1"
    "모의고사 작업/고2"
    "EBS 작업"
    "교과서 작업"
    "인디자인 파일/워크북/모의고사"
<<<<<<< Updated upstream
    # 직전보충 학교 워크북 — 시험기간별 폴더. 시험기간이 바뀌면 아래 줄을 갱신.
    "인디자인 파일/워크북/26-1-기말"
    # 직전보충 고3 워크북 — 학년도별 폴더. 학년도가 바뀌면 아래 줄을 갱신.
    "인디자인 파일/워크북/고3 EBS 수능특강/2027"
=======
>>>>>>> Stashed changes
    "인디자인 파일/Y.ONE WEB/인디자인 원본"
)

# 1) GDrive 마운트 확인
if [ ! -d "$GDRIVE_BASE" ]; then
    echo "[오류] GDrive 폴더를 찾을 수 없습니다:"
    echo "  $GDRIVE_BASE"
    echo "  Google Drive 앱 설치 + 로그인(etyrano11@gmail.com) 후 다시 실행하세요."
    exit 1
fi

# 2) 디스크 여유 확인
AVAIL_GB=$(df -g "$HOME" | tail -1 | awk '{print $4}')
echo "[정보] 디스크 여유: ${AVAIL_GB}GB"
if [ "$AVAIL_GB" -lt 5 ]; then
    echo "[경고] 디스크 여유 5GB 미만 — 미러 셋업 위험."
    read -r -p "그래도 계속? (y/N): " confirm
    if [ "$confirm" != "y" ]; then
        echo "중단됨."
        exit 0
    fi
fi

# 3) 미러 베이스 생성
mkdir -p "$MIRROR_BASE"

# 4) 각 폴더 rsync (변경분만 전송)
FAIL_COUNT=0
for sub in "${SUBPATHS[@]}"; do
    src="$GDRIVE_BASE/$sub/"
    dst="$MIRROR_BASE/$sub/"

    if [ ! -d "$src" ]; then
        echo "[스킵] 소스 없음: $sub"
        continue
    fi

    SIZE=$(du -sh "$src" 2>/dev/null | awk '{print $1}')
    echo ""
    echo "[복사] $sub  (소스 사이즈: $SIZE)"
    mkdir -p "$dst"

    # 옛 macOS rsync(2.6.9)는 --info=stats2 미지원이라 단순 -av 사용.
    # --exclude=".*"로 .DS_Store/.com.google.Drive 등 hidden 파일 제외.
    if rsync -a --exclude=".*" "$src" "$dst"; then
        echo "[완료] $sub"
    else
        echo "[실패] $sub — Drive 데몬 stuck 가능. 다음 시도:"
        echo "  killall 'Google Drive' && sleep 5 && open -a 'Google Drive' && sleep 15"
        echo "  그 후: bash $0"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo ""
echo "================================================================"
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "[셋업 부분 실패] $FAIL_COUNT개 폴더 미러 실패 — 위 안내대로 재시도"
    exit 1
fi

echo "[셋업 완료]"
echo "  미러 위치: $MIRROR_BASE"
du -sh "$MIRROR_BASE"
echo ""

# 5) launchd 자동 sync 등록 (30분 간격)
PLIST="$HOME/Library/LaunchAgents/com.yonestudio.mirror-sync.plist"
SYNC_SCRIPT="$HOME/dev/yone-design-web/scripts/mirror-sync.sh"

if [ ! -f "$SYNC_SCRIPT" ]; then
    echo "[안내] mirror-sync.sh 미설치 — 자동 sync launchd 등록 skip"
    echo "       git pull 후 재실행하면 launchd 자동 등록됨"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/Library/Logs"

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.yonestudio.mirror-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SYNC_SCRIPT</string>
    </array>
    <key>WorkingDirectory</key><string>$HOME/dev/yone-design-web</string>
    <key>StartInterval</key><integer>1800</integer>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>$HOME/Library/Logs/yone-mirror-sync-stdout.log</string>
    <key>StandardErrorPath</key><string>$HOME/Library/Logs/yone-mirror-sync-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key><string>$HOME</string>
        <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "[자동 sync] 30분 간격 launchd 등록 완료"
echo "  plist: $PLIST"
echo "  log:   ~/Library/Logs/yone-mirror-sync.log"
echo "  중지:  launchctl unload $PLIST"
echo ""
echo "추후 GDrive 원본이 변경되면 30분 안에 자동 sync. 수동 갱신 불필요."
