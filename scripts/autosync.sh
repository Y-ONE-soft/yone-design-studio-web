#!/bin/bash
# yone-design-web 자동 동기화: 로컬 변경 커밋 -> pull(rebase) -> push
# launchd(StartInterval)에서 주기 실행. 한 번에 한 기계에서만 같은 파일을 수정한다는 전제.
REPO="$HOME/dev/yone-design-web"
LOG="$HOME/Library/Logs/yone-web-autosync.log"
cd "$REPO" || exit 0
exec >> "$LOG" 2>&1

NAME="$(scutil --get ComputerName 2>/dev/null || hostname -s)"
echo "=== $(date '+%F %T') [$NAME] autosync ==="

# 이전 rebase/merge가 미해결이면 사람이 풀 때까지 중단 (찌꺼기 자동커밋 방지)
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ]; then
    echo "!! 미해결 rebase/merge 존재 - 스킵 (수동 개입 필요)"
    exit 1
fi

# 1) 로컬 변경 커밋 (있을 때만)
git add -A
if ! git diff --cached --quiet; then
    # 변경 파일 요약을 커밋 본문에 포함 (git log만으로 무엇이 바뀌었는지 추적 가능)
    SUMMARY=$(git diff --cached --name-status | head -20)
    N_FILES=$(git diff --cached --name-status | wc -l | tr -d ' ')
    git commit -m "auto($NAME): $(date '+%F %T') (${N_FILES}개 파일)" -m "$SUMMARY" || true
    echo "  -> 로컬 변경 커밋함 (${N_FILES}개 파일)"
fi

# 2) 원격 변경 가져오기 (rebase + autostash로 divergence 흡수)
if ! git pull --rebase --autostash origin main; then
    echo "!! pull 실패 (코드 충돌 가능) - rebase 중단하고 중지"
    git rebase --abort 2>/dev/null || true
    exit 1
fi

# 3) 푸쉬 (로컬이 앞서 있을 때만 실제 전송됨)
git push origin main || echo "!! push 실패 (인증/네트워크 확인)"

echo "=== $(date '+%F %T') [$NAME] 완료 ==="
