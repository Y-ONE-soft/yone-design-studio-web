#!/bin/bash
# Yone Design Web — GDrive 콘텐츠 로컬 미러 셋업
#
# 사용법:
#   bash scripts/setup-mirror.sh
#
# 목적: Google Drive NSFileProvider 데몬 EDEADLK 회피.
#   자주 쓰는 GDrive 콘텐츠 폴더를 ~/Documents/yone-content-mirror/ 아래
#   로컬 미러로 복사. 이후 _gdrive_safe_copy(engines/final/extractor.py)가
#   자동으로 미러 우회 → deadlock 자체가 발생하지 않음.
#
# 실행 시점:
#   1) 새 맥북/조교 컴 셋업 시 1회
#   2) GDrive 원본이 변경됐을 때 (rsync는 변경분만 전송하므로 두 번째부터 빠름)

set -e

GDRIVE_BASE="$HOME/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비"
MIRROR_BASE="$HOME/Documents/yone-content-mirror"

# 미러할 폴더 — "내신대비/" 다음부터의 상대경로.
# 코드는 GDrive 경로의 "/내 드라이브/콘텐츠 관리/내신대비/" 뒤 경로를 그대로
# 미러 베이스에 붙여 lookup하므로, 여기 등록한 폴더는 자동으로 우회됨.
SUBPATHS=(
    "모의고사 작업/고1"
    "모의고사 작업/고2"
    "EBS 작업"
    "교과서 작업"
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
echo "추후 GDrive 원본이 변경되면 같은 스크립트 재실행하여 sync 갱신."
