#!/bin/bash
# 로컬 파이널 직전보충 1개 학교 깨끗하게 조판.
# 사용: _run_school.sh <학교> <학년> <시험기간>
# - InDesign 열린 문서 모두 닫기(저장 안 함) → 락 충돌 방지
# - 출력 폴더 기존 indd/idlk 제거 → _2 중복 네이밍 방지
# - 파이프라인 실행 (로그: /tmp/run_<학교>.log)
set -u
SCHOOL="$1"; GRADE="$2"; EXAM="$3"
ROOT="/Users/nhj/Documents/작업/Y.ONE STUDIO"
OUTDIR="$ROOT/조판/교재/파이널 직전보충/$GRADE/$EXAM/$SCHOOL"
APP="Adobe InDesign 2026"

# 1) InDesign 문서 모두 닫기 (저장 안 함)
osascript -e "tell application \"$APP\"
set uil to user interaction level of script preferences
set user interaction level of script preferences to never interact
try
 close every document saving no
end try
set user interaction level of script preferences to uil
end tell" >/dev/null 2>&1

# 2) 출력 폴더 정리
if [ -d "$OUTDIR" ]; then
  find "$OUTDIR" -maxdepth 1 -name '*.indd' -delete 2>/dev/null
  find "$OUTDIR" -maxdepth 1 -name '*.idlk' -delete 2>/dev/null
fi

# 3) 실행
cd /Users/nhj/dev/yone-design-web || exit 1
export PYTHONPATH="/Users/nhj/Library/Python/3.9/lib/python/site-packages"
exec /usr/bin/python3 _local_final_run.py "$SCHOOL" "$GRADE" "$EXAM"
