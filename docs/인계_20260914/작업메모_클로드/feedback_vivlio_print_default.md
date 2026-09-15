---
name: feedback-vivlio-print-default
description: 비블리오 조판은 별도 말 없으면 전부 오프셋 인쇄 납품용 — CMYK·도련 3mm 등 인쇄 규약을 매번 지시받지 않고 기본 적용
metadata:
  type: feedback
---

2026-09-11 사용자: "비블리오로 조판하는 거 내가 별도로 얘기 안 하면 전부 인쇄용으로 납품하는
건데, 할 때마다 이렇게 해라 저렇게 해라 할 필요 없이 항상 CMYK로 작업하고 도련 사방 3mm
넣어야 하고 이런 거 규약으로 정리해라."

**Why:** 인쇄 규격은 책마다 반복되는 상수인데 세션마다 새로 지시받으면 빠뜨린다(실제로
포켓북 21권 등 31/56권이 `print` 절 없이 RGB 조판본만 있었다).

2026-09-11 사용자 재확인: "진행하고, 내가 별도로 '이건 인쇄용 아니야'라고 말할 경우에만 빼면 돼."
→ 코드 기본값을 뒤집었다(`book._print_section` 항상 켜짐, `page.bleed` 기본 3). 빼는 법은
config `"print": false` 뿐. 유채색은 ICC 변환(포켓북만 원본 CMYK 고정). gs 통과 후 Type3
ToUnicode 가 깨져 인쇄본 텍스트 검색은 불가(외관 동일) — 텍스트 검수는 조판본에서.

**How to apply:** 규약 정본은 `~/.claude/CLAUDE.md` "비블리오 인쇄 납품 규약" 절(전 세션
자동 로드). 구현 대응표·config 템플릿·코드 틈은
`~/dev/yone-design-web/.claude/rules/vivlio_print_spec.md`. 새 책 config 에는 `page.bleed: 3`
+ `print` 절(JapanColor2001Coated, gray_map 에 팔레트 무채색 전부)을 처음부터 넣고, 납품은
`_인쇄.pdf` 만. 관련: [[feedback-compare-reference-file]] [[feedback-typeset-palette-three-tier]]
