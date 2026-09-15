---
name: workbook_vivlio_turn_fit
description: 워크북 비블리오 — 장 넘김/당겨붙이기 마감 패스의 함정과 대가
metadata:
  type: project
---

워크북 Vivliostyle 계열(`core/render_vivlio/series/workbook`)의 **마감 측정 패스**.
조판을 굽고 흰 표식을 재서 고친다 — CSS 로는 어디서 끊겼는지 알 수 없다.

- 자간만으로는 한 줄이 안 당겨진다 → **행간도 mm 값으로** 3%(2단계 6%) 함께
- `break-before: page` 는 면 머리에서 시작하는 세트에 **아무 일도 안 한다** → `verso`
- 표식 정렬 타이브레이크: 앞 끝과 뒤 시작이 같은 y → `sbeg`<`send` 라 세트가 사라진다
- **단**을 넘어 갈라지는 것은 정상(완성본 단의 22%가 선지로 시작). 다 묶으면 단 40% 증가.
  **장**을 넘어 갈라진 것만 묶는다(완성본은 0개)
- 면보다 큰 덩어리는 묶어도 못 담는다(브라우저가 무시) → 높이 재서 건너뛰기
- 셋이 서로 밀고 당겨 수렴 안 함 → 바퀴마다 점수(결함 수, 면 수) 매겨 **최선의 판** 보관
- 면 머리에서 시작하는 세트를 밀면 그 오른쪽 면이 통째로 빈다(77면→88면) → 안 민다, 경고만
- 대가: 규칙 준수로 면이 는다(수능만만 77→86, 한영1 293→300). `options.turn_push`
  / `options.leaf_keep` 로 끌 수 있다

기준 완성본 대조가 판정의 근거였다 — 완성본 PDF 를 재서 관행을 확인했다.
관련: [[feedback_match_reference_not_ask]] [[feedback_compare_reference_file]]
