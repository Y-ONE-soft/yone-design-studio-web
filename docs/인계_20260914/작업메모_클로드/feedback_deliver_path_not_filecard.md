---
name: feedback-deliver-path-not-filecard
description: 완성 파일은 절대경로 마크다운 링크로 — 전역 ~/.claude/CLAUDE.md 에 규칙으로 박혀 있다
metadata:
  type: feedback
---

**완성 파일은 `[파일명](/Users/... 절대경로)` 마크다운 링크로 전달한다.**
SendUserFile 파일 카드로만 주거나, 경로를 코드 블록·평문으로만 적고 끝내지 않는다.
상대경로·폴더 경로도 안 된다.

**Why:** 사용자는 받은 걸 곧바로 Finder 에서 열어 다른 파일과 같이 다룬다. 카드는
우클릭 "다음에서 열기 > Finder" 가 안 되고 다운로드 사본만 생겨, 정작 작업 중인
원본 위치를 다시 찾아야 한다. 상대경로 링크도 같은 이유로 동작하지 않는다.

**How to apply:** 규칙은 이제 **전역 `~/.claude/CLAUDE.md`** 의
"파일 전달 규칙 (MANDATORY)" 에 있다(백업 `CLAUDE.md.bak.20260825`).
`Y.ONE STUDIO/CLAUDE.md` 46행에도 같은 규칙이 있지만 **그건 그 폴더에서 시작한
세션에만 붙는다** — 작업 폴더가 `~/dev/조판` 처럼 다른 곳이면 안 읽힌다. 그래서
"모든 세션" 요구는 디렉터리 CLAUDE.md 가 아니라 전역 파일로 풀어야 한다.
같은 함정: 이미 진행 중인 세션은 시작 시점의 CLAUDE.md 를 들고 있어 도중 수정이
반영되지 않는다(새 세션부터 적용).

관련: [[feedback_compare_reference_file]], [[project_gwangmun_voca_vivliostyle]]
