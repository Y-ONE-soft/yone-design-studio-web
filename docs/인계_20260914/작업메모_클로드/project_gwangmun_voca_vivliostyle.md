---
name: project-gwangmun-voca-vivliostyle
description: 광문보카(광문고1 26-2-중간) Vivliostyle 조판 — 통합웹 엔진에 vocaunit 계열 신설, 72p 조판 완료
metadata:
  type: project
---

**광문보카 = 광문고1 26-2-중간, 어휘끝 고교기본 Unit 15~23**(9 Unit × 표제어 30 = 270).
**InDesign 아님 = Vivliostyle 코드 조판.** 2026-08-25 1차 조판 완료(72p, 빌드 약 20초,
검수 게이트 통과). 사용자 피드백 대기.

- 책 폴더 = `조판/교재/단어장/광문보카/26-2-중간/` — **README.md 먼저**. config.json +
  원고 + `_기준_…(샘플).pdf`(디자인 기준본) 뿐, 코드는 없다.
- 실행 = `cd ~/dev/yone-design-web && bin/viv "<책폴더>" all`
- 계열 코드 = `core/render_vivlio/series/vocaunit/` + `themes/vocaunit.css`
  + `assets/vocaunit/`(2026 알약·MEMO 탭 PNG). 커밋 a45e593.

**`vocaunit` 은 `vocabook`(상일·배재보카)과 다른 계열이다** — 판형은 같은 A5지만
디자인 계보(마름모 탭 vs 모눈+둥근 탭)와 원고 형식(섹션 시트 4개 vs Unit 시트별 블록)이
달라 겹치는 게 백엔드뿐. 계열을 쪼갠 기준은 "무엇이 달라지면 코드가 바뀌는가".

**디자인은 기존 완성본 PDF 에서 베이스라인 실측 이식.** bbox 윗변은 글리프마다
±2mm 흔들려 못 쓴다 — `span['origin']` 으로 상수를 뽑아 CSS 를 역산할 것. 항목
리듬(괘선 기준): 번호 3.95 · 표제어 9.03 · 발음 12.75 · 파생어 17.28(줄간 4.18) /
뜻은 8.90 축으로 위아래 가운데 · 예문 첫 영문 16.90. 완성본은 오른쪽 열에 세로
균등배분이 걸려 ±1mm 흔들리는데 여기선 고정 간격(의도적 차이).
크레스트는 `get_drawings()` items → SVG path 로 벡터 추출(`art.py`), 서체 없는
글자(TTSupersizeBk "2026", MEMO 탭)만 고해상도 PNG.

**함정 4종(전부 실제로 데임)**
- 배경 축약형에 `no-repeat` 가 두 번 들어가면 **선언이 통째로 무시**된다 —
  `svg.data_uri()` 가 이미 붙여 준다. 도형이 조용히 사라진다.
- **러닝 요소 배경은 요소 상자 안에서만** 그려진다 → `height: <상단 여백>` 필수
  (안 주면 탭·크레스트 아래가 잘리고, 여백보다 크면 마진 박스가 자른다).
- **2열 항목을 flex 로 짜면 `break-inside: avoid` 가 마지막 항목에서 무시**돼 판면
  아래 띠까지 넘친다 → `display: table` + `table-cell`. 아래 괘선은 음수 마진 대신
  **배경 상자**로 깔면 다음 항목 border-top 과 정확히 겹친다.
- config 키 밑줄(`cover_mark`) ↔ CSS 변수 하이픈(`--c-cover-mark`) 어긋나면 **색만
  조용히 검정**으로 떨어진다.

**2패스 계약이 한 발 넘어간 자리**: ②면(Unit 시작 다음 오른쪽)은 배경뿐 아니라 상단
여백도 5mm 내려간다 → 페이지 나눔이 움직일 수 있어 **시작 면 목록이 고정점에
닿을 때까지 반복**(최대 4패스, 안 멎으면 경고). `vocabook` 의 "덧칠만 하는 2패스"와
섞지 말 것.

**판단이 갈린 곳(사용자 확인 필요)**: 원고의 `(= thoughtful)` `(↔ senseless …)` 는
완성본 샘플에 사례가 없어 6pt 회색으로 새로 정했다(`render.py::_paren` 한 곳).
간지도 엔진이 그린다(별도 간지 PDF 없음) — 바꾸려면 `finish.inserts`.

관련: [[project_sangil_voca_vivliostyle]](vocabook 계열),
[[project_blackbook_vivliostyle]](Vivliostyle 함정),
[[feedback_compare_reference_file]](기준 완성본 대조), [[feedback_parser_structural_not_pattern]]
