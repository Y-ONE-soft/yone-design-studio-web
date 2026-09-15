---
name: feedback-binding-default-perfect
description: 제본은 기본 무선제본 — 총 면수는 짝수만 맞춘다. 중철(4의 배수)·스프링은 사용자가 말할 때만
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ec3aa692-74f4-40b7-b397-b543eef2f3bc
  modified: 2026-09-14T01:31:44.035Z
---

2026-09-14 사용자: "중철이나 스프링은 제본은 내가 얘기할 때만이고 평소에는 전부 무선제본이야."

한서끝을 제본 미확인이라며 중철로 가정해 4의 배수(56면, MEMO 3면)로 뽑았다가 "메모 3장이나 넣은
이유는?" 지적을 받았다.

**Why:** 모르는 제본을 가장 까다로운 쪽(중철)으로 가정하면 MEMO 면이 불필요하게 늘어난다.
기본값이 정해져 있으니 물을 일도, 가정할 일도 아니다.

**How to apply:** 새 책 config 는 짝수 맞춤이 기본(hankkeut `finish.multiple: 2`, 다른 계열은
`end_on_left`). 사용자가 "중철"이라고 할 때만 4의 배수로. 스프링도 짝수. 보고에서 제본을 미결 항목으로
올리지 않는다. 관련 [[feedback-vivlio-print-default]] [[project-hanseokkeut-vivliostyle]]
