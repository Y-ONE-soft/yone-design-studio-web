---
name: feedback-divider-pages-default
description: 비블리오 간지 기본 규칙 — 앞 간지 1P·크레딧 1P·파트 간지 2P 펼침면, 표지와 비슷한 느낌. 따로 지시 있으면 그것대로
metadata:
  type: feedback
---

2026-09-12 사용자: "간지는 표지와 비슷한 느낌으로 만든다. 1페이지(앞)와 마지막 페이지(크레딧)는
1P, 파트 사이 간지는 2P로 제작. 이게 기본이고 따로 어떻게 만들라는 내용이 있으면 그거대로."

**Why:** 계열마다 간지 면수·출처가 제각각(포켓북 1P+1P, 블랙북 아트워크 교체, 한끝 1/2/1)이라
새 책마다 다시 물어봐야 했다. 표지와 따로 노는 간지(본문 팔레트로 새로 지은 것)도 지적 대상.

**How to apply:** 정본은 `~/.claude/CLAUDE.md` 인쇄 납품 규약의 "간지 기본 규칙" 항목, 계열별
코드 대응은 리포 `.claude/rules/vivlio_print_spec.md` "간지" 절. 참조 구현은 `series/hankkeut`
(front 1P · divl+divr 2P · 뒤 1P, 표지 돌 바탕+이중 괘선+워드마크). 파트 간지는 왼쪽 면에서
열리게 앞을 MEMO 로 맞춘다. 관련: [[feedback-vivlio-print-default]] [[feedback-no-mirrored-page-art]]
