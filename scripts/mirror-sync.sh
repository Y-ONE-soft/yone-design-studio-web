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

# rsync 바이너리 — macOS 기본 /usr/bin/rsync 는 2.6.9(2006년판)라 경로가 길면
# "skipping overly long name"으로 파일을 조용히 빠뜨리고(2026-09-12 실측 276개),
# --max-delete 옵션도 없다. Homebrew 3.x 를 우선 쓰고 없으면 기본으로 되돌린다.
# launchd plist 의 PATH 에 /opt/homebrew/bin 이 없으므로 절대경로로 지정한다.
RSYNC=/opt/homebrew/bin/rsync
[ -x "$RSYNC" ] || RSYNC=/usr/bin/rsync

# 삭제 상한 — GDrive 스트리밍 마운트는 폴더 내용을 요청받을 때 지연 열거한다.
# rsync 가 훑는 순간 아직 열거되지 않은 폴더는 '비어 있음'으로 보이고, 거기에
# --delete 가 붙으면 멀쩡한 미러를 통째로 지운다.
#   (2026-09-12 사고: '한영고1 마더텅 예전 기출' 313개 → 0개 전멸 후 재다운로드.
#    그 전까지는 EDEADLK 오류 덕분에 rsync 가 삭제를 스킵해 우연히 가려져 있었다.
#    디스크 부족을 해소해 EDEADLK 가 사라지자 곧바로 드러났다.)
# 상한을 넘으면 rsync 는 이후 삭제를 전부 건너뛰고 exit 25 를 낸다 — 전송 자체는
# 정상 진행되므로, 정상적인 rename/삭제 정리는 통과하고 대량 몰살만 막힌다.
# 상한 200 — 50 은 너무 빡빡했다. rsync 의 삭제 예정 집계에는 빈 디렉터리도
# 포함돼서, 폴더 구조가 한 번 개편되면(예: '고1 21년 6월' → '고1 21년(3,6,9,10,11월)')
# 실파일 삭제가 0건이어도 수십 건이 잡힌다. 2026-09-12 실측: 고1 59건·EBS 160건이
# 걸렸지만 실파일 삭제 대상은 양쪽 다 0개였다.
MAX_DELETE=${YONE_MAX_DELETE:-200}

# 로그 로테이션 — 로테이션이 없어서 로그가 71GB까지 불어나 디스크를 99%까지
# 채운 사고가 있었다(2026-09-12). GDrive EDEADLK가 나면 한 사이클에 rsync가
# 파일마다 오류 줄을 쏟아내므로, 매 실행 앞에서 크기를 보고 잘라낸다.
LOG_MAX_BYTES=${YONE_LOG_MAX_BYTES:-52428800}   # 50MB
if [ -f "$LOG" ]; then
    log_size=$(stat -f%z "$LOG" 2>/dev/null || echo 0)
    if [ "$log_size" -gt "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG" "$LOG.1"
        : > "$LOG"
    fi
fi

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

    # 열거 예열 — rsync 를 돌리기 전에 소스를 한 번 전부 훑어 GDrive 가 지연
    # 열거를 끝내게 만든다. 이러면 rsync 가 불완전한 목록을 보고 삭제를 판단하는
    # 일이 줄어든다. 예열은 보조 수단이고 최종 방어선은 --max-delete 다.
    # 실패해도 무시한다(예열 실패가 동기화를 막을 이유는 없다).
    find "$src" -type f >/dev/null 2>&1 || true

    # rsync 자체 retry 루프 — GDrive Stream EDEADLK는 일시적이지만 단일 호출
    # 안에서 만나면 그 사이클 내내 못 풀린다. 대기 후 재시도하면 대부분 회복.
    # --partial: 일부 전송된 파일 보존 (재시도가 이어 받음)
    # --partial-dir: stale 부분 파일을 별도 폴더에 격리 (조판 코드가 안 읽도록)
    # --delete: GDrive에서 rename/삭제된 파일을 미러에서도 제거.
    #   (2026-08-07 사고: '전체(C)→전체' 일괄 rename 후 미러에 옛 이름이
    #    영구 잔존 → mockexam_sero_merge가 미러만 listdir 해서 옛 목록을 보고
    #    "세로버전 파일을 찾지 못한 회차" 오류. 미러 58개 중 49개가 유령이었다.)
    #   안전장치: rsync는 I/O 오류(EDEADLK 등)가 난 실행에서는 삭제를 스킵한다
    #   (--ignore-errors 미지정 시 기본 동작). 단 이건 오류가 날 때만 도는 우연한
    #   방어라 믿으면 안 된다 — 2026-09-12 에 EDEADLK 를 없애자 곧바로 대량 삭제가
    #   터졌다. 실제 방어선은 위의 --max-delete 와 예열용 find 다.
    #   --exclude 대상은 --delete-excluded 없이는 삭제되지 않는다.
    # 삭제 사전 점검 — dry-run 으로 삭제 예정 건수를 먼저 센다.
    # --max-delete 만 쓰면 상한까지(기본 50개)는 실제로 지우고 멈추므로 '한 번에
    # 50개 손실'이 남는다. 그래서 상한을 넘으면 아예 --delete 를 빼고 전송만 한다
    # (삭제 0건). 상한 이내면 평소대로 삭제까지 수행한다.
    # DEL_OPTS 는 값에 공백이 없으므로 비따옴표 전개로 단어 분리시킨다
    # (bash 3.2 에서 빈 배열 전개가 set -u 와 충돌하는 것을 피하려는 의도).
    DEL_OPTS="--delete-after --max-delete=$MAX_DELETE"
    pending_del=$("$RSYNC" -ani --delete-after --fuzzy --exclude=".*" --partial \
                  --partial-dir=".rsync-partial" \
                  "$src" "$dst" 2>/dev/null | grep -c '^\*deleting' || true)
    if [ "$pending_del" -gt "$MAX_DELETE" ]; then
        echo "[$(ts)] [경고] $sub — 삭제 예정 ${pending_del}건이 상한 ${MAX_DELETE} 초과." \
             "GDrive 열거 불안정 의심 → 이번 사이클은 삭제 없이 전송만 수행." >> "$LOG"
        DEL_OPTS=""
    fi

    attempt=0
    success=0
    while [ $attempt -lt 3 ]; do
        attempt=$((attempt + 1))
        # --fuzzy + --delete-after: rename된 파일은 목적지의 유사 이름 파일을
        #   basis로 재구성해 GDrive 재다운로드를 피한다. 삭제를 전송 뒤로
        #   미루는 --delete-after 가 필수 — 기본 --delete-during 이면 basis가
        #   먼저 지워져 fuzzy가 무력화되고 전량 재다운로드가 된다
        #   (2026-08-07 실측: 모의고사 폴더 9GB 전량 재전송).
        "$RSYNC" -a $DEL_OPTS --fuzzy --exclude=".*" --partial \
                 --partial-dir=".rsync-partial" \
                 "$src" "$dst" >> "$LOG" 2>&1
        rc=$?
        if [ $rc -eq 0 ]; then
            success=1
            break
        fi
        if [ $rc -eq 25 ]; then
            # 삭제 상한 초과 — 전송은 끝났고 삭제만 건너뛴 상태다. 재시도해도
            # 같은 결과이므로 경고만 남기고 다음 경로로 넘어간다. 이 경고가 뜨면
            # GDrive 열거가 불안정했다는 뜻이니 미러를 눈으로 확인할 것.
            echo "[$(ts)] [경고] $sub — 삭제 ${MAX_DELETE}건 상한 초과로 삭제 중단(전송은 완료)" >> "$LOG"
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
