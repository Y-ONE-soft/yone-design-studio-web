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

# 50MB 초과 파일은 커밋에서 제외 — GitHub가 100MB에서 push를 거부해 이후 모든
# push가 조용히 마비됨 (2026-07-04 bake PNG 145MB로 실증, 07-05 filter-repo로 수습).
# 신규 파일은 .git/info/exclude 등록으로 재발 차단, 알림으로 사람에게 알린다.
while IFS= read -r f; do
    [ -f "$f" ] || continue
    sz=$(stat -f%z "$f" 2>/dev/null || echo 0)
    if [ "$sz" -gt 52428800 ]; then
        git restore --staged -- "$f" 2>/dev/null || git reset -q HEAD -- "$f"
        grep -qxF "$f" .git/info/exclude 2>/dev/null || echo "$f" >> .git/info/exclude
        echo "!! 50MB 초과 커밋 제외: $f ($((sz/1048576))MB)"
        osascript -e "display notification \"$f ($((sz/1048576))MB) 커밋에서 제외됨\" with title \"autosync: 대용량 파일\"" 2>/dev/null || true
    fi
done < <(git diff --cached --name-only)

if ! git diff --cached --quiet; then
    # 변경 파일 요약을 커밋 본문에 포함 (git log만으로 무엇이 바뀌었는지 추적 가능)
    SUMMARY=$(git diff --cached --name-status | head -20)
    N_FILES=$(git diff --cached --name-status | wc -l | tr -d ' ')
    git commit -m "auto($NAME): $(date '+%F %T') (${N_FILES}개 파일)" -m "$SUMMARY" || true
    echo "  -> 로컬 변경 커밋함 (${N_FILES}개 파일)"
fi

# ── 브랜치 가드 ────────────────────────────────────────────────
# 이 스크립트는 원래 브랜치를 보지 않고 언제나 `origin main` 으로 pull/push 했다.
# 그래서 **작업 브랜치를 체크아웃한 채로 두면 그 브랜치의 커밋이 main 으로
# 밀려나가** 브랜치를 판 의미가 사라진다(2026-08-29 실증). 커밋(1단계)은 어느
# 브랜치에서든 계속 해서 작업을 잃지 않게 하고, 동기화 대상만 현재 브랜치로 맞춘다.
BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo '')"
if [ -z "$BRANCH" ]; then
    echo "!! detached HEAD - 동기화 스킵 (커밋만 함)"
    echo "=== $(date '+%F %T') [$NAME] 완료 ==="
    exit 0
fi

# 2) 원격 변경 가져오기 (rebase + autostash로 divergence 흡수)
if ! git pull --rebase --autostash origin "$BRANCH"; then
    echo "!! pull 실패 (원격에 $BRANCH 가 없거나 코드 충돌) - rebase 중단하고 중지"
    git rebase --abort 2>/dev/null || true
    # 원격에 아직 없는 새 브랜치면 push 로 만들어 준다 (백업 공백 방지)
    if ! git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
        echo "  -> 원격에 $BRANCH 없음: 새로 push 시도"
        git push -u origin "$BRANCH" || echo "!! 신규 브랜치 push 실패"
    fi
    echo "=== $(date '+%F %T') [$NAME] 완료 ==="
    exit 1
fi

# 3) 푸쉬 (로컬이 앞서 있을 때만 실제 전송됨)
# 실패를 로그에만 남기면 아무도 모른 채 백업 공백이 누적된다 (2026-07-04 실증) — 알림 필수.
if ! git push origin "$BRANCH"; then
    echo "!! push 실패 (인증/네트워크/원격 거부 확인)"
    osascript -e 'display notification "git push 실패 — ~/Library/Logs/yone-web-autosync.log 확인" with title "autosync 경고"' 2>/dev/null || true
fi

echo "=== $(date '+%F %T') [$NAME] 완료 ==="
