#!/bin/bash
# 배포 게이트 — "테스트 통과 없이는 실서비스 반영 없음"을 스크립트로 강제.
#
# 절차 (마일스톤 단위로만 실행):
#   1) summer-2026 워크트리에서 스냅샷 테스트 (실서비스와 같은 python 3.9)
#   2) 통과 시 main으로 merge + push
#   3) 실서비스 Flask 재시작 (kickstart)
#   4) localhost:5010 /api/health 확인 (yonestudio.com은 deploy-check 절차로 별도 확인)
#
# 어느 단계든 실패하면 즉시 중단한다.
set -euo pipefail

WORKTREE="$HOME/dev/yone-design-web-summer"
MAIN="$HOME/dev/yone-design-web"

echo "== 1/4 스냅샷 테스트 (python 3.9) =="
cd "$WORKTREE"
PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages" \
    /usr/bin/python3 -m pytest tests/ -q

echo "== 2/4 main merge + push =="
cd "$MAIN"
git pull --rebase origin main
git merge --no-ff summer-2026 -m "merge: summer-2026 마일스톤 반영 (테스트 게이트 통과)"
git push origin main

echo "== 3/4 실서비스 Flask 재시작 =="
launchctl kickstart -k "gui/$(id -u)/com.yonestudio.flask"
sleep 3

echo "== 4/4 헬스체크 =="
curl -sf http://localhost:5010/api/health | head -c 300
echo
echo "완료. yonestudio.com 쪽도 deploy-check 절차로 확인할 것."
