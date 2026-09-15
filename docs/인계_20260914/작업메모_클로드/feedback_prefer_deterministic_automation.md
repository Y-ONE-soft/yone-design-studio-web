---
name: feedback-prefer-deterministic-automation
description: 동일 패턴이 반복되는 수작업은 결정론적 파서+스크립트로 자동화하길 선호(정확성은 카운트 일치 안전망으로 담보)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a277cd89-79ea-4a77-8ca9-2cf2bd3f8d20
---

사용자는 동일 패턴이 반복되는 수작업(예: 워크북 PDF '밑줄 추가' 검수)을 매번 손으로 처리하기보다 **결정론적 도구(파서 + 통합 스크립트)로 자동화**하길 선호한다. "방식이 비슷한데 시간이 오래 걸린다"며 자동화를 직접 요청·승인했다 (2026-06-11, workbook-pdf-revise 스킬에 `parse_underline_targets.py` + `apply_underline.jsx` 신설).

**Why:** 반복 작업의 손작업(매번 JSX를 새로 작성, 전수 시각검증)이 시간을 잡아먹는다. LLM이 매번 즉흥 생성하는 것보다 고정 도구가 빠르고 반복 가능하며 실수가 적다.

**How to apply:** 비슷한 반복 수작업을 보면 먼저 "도구로 자동화할까요?"를 제안한다. 정확성은 "자동 생성 결과 == 기대 카운트" 같은 **안전망(불일치 시 자동 중단)**으로 담보하고, 시각/수동 검증은 전수가 아닌 샘플 1~2개로 축소. 단 자동화는 **확정 패턴에만** 적용하고 모호/혼합 케이스는 기존대로 사용자에게 질의(스킬의 "모호한 것만 묻는다" 설계 유지). 워크북 검수 자동화 상세는 workbook-pdf-revise 스킬의 SKILL.md '빠른 경로' + learned_patterns.md 참조.
