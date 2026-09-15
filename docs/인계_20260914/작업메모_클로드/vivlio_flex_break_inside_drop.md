---
name: vivlio-flex-break-inside-drop
description: Vivliostyle에서 break-inside:avoid를 flex 컨테이너에 직접 걸면 그 덩어리가 조용히 사라진다 — 두 단 덩어리는 display:table로
metadata:
  type: reference
---

Vivliostyle(CLI 11 / core 2.44)에서 **`break-inside: avoid` 를 flex 컨테이너에
직접 걸면**, 뒤에 강제 나눔(`break-before: page`)이 있고 남은 자리에 안 들어갈 때
다음 면으로 밀리는 대신 **덩어리가 통째로 없어진다.** 최소 재현 확인:
flex + avoid → 사라짐 / 블록 + avoid → 정상 / `display:table` + avoid → 정상 /
avoid 블록 **안에** 든 flex → 정상(단, 그 블록의 유일한 자식이 flex 면 사라짐).

실측 사고: 예비고1 특강 어휘 Week 4 no.10(novel) 낱말 카드가 통째로 빠졌다.
**육안 검수로는 못 잡는다** — 원고↔PDF 전수 대조 게이트가 잡았다.

**두 단짜리 덩어리(낱말 카드·부록 행·정답 행)는 `display: table; table-layout: fixed`
+ `display: table-cell` 로 짠다.** flex 는 avoid 가 붙지 않는 곳에만.

같이 겪은 형제 함정: **머리 기호를 `position:absolute` 로 얹으면** 그 단락이 뒤
레이어로 밀려 **PDF 글자 추출 순서가 읽는 순서와 어긋난다**(순서 대조 1,186건
실패). 들여쓰기(`text-indent` + `::before`)로 그릴 것.

[[project_gwanggyo_prehigh1_special]] 에서 나왔고 `core/render_vivlio/themes/special.css`
머리말에 적어 뒀다.
