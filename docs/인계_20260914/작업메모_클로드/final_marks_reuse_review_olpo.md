---
name: final-marks-reuse-review-olpo
description: 파이널 직전보충 — 연구원 PDF 주석의 학교 넘은 재사용·조판 뒤 검수 자동화·올림포스 판 내용 대조·크레딧 명단 (2026-09-11)
metadata: 
  node_type: memory
  type: project
  originSessionId: 22f543b5-a851-4e81-994b-99e678faf645
  modified: 2026-09-10T17:26:18.634Z
---

리포는 `/Users/nhj/dev/yone-design-web` (통합웹 `.claude` 는 심링크).

**① 지문 정오표 = 학교를 넘는다** — `engines/final/marks.py` + `data/final_marks.json`.
책 폴더 편집이력(`core/render_vivlio/edits.py`)은 자리표가 그 책 차례(`lessons.0…`)에
매여 있어 **학교가 바뀌면 안 얹힌다**. 파이널은 학교마다 새 책이지만 지문은 같은
원고를 돌려 쓰므로, **지문 이름(`올포 3강 본문2`) + 글자**로 걸어 둔다. 얹는 자리는
`scripts/final_manuscript_build.build()` 끝 → 원고를 다시 뽑아도 살아남는다.
`scripts/final_marks_from_pdf.py` 가 PDF 주석을 읽되 **지면 좌표가 아니라 글자로**
지문을 찾는다(줄바꿈 무시 대조 후 원문에서 도로 자름). `A → B` 쪽지만 자동 적용,
"철자 확인 요망" 류는 목록에만(`--loose` 로 넘김). 한 지문 글은 배열·삽입·어법·영작에
되풀이되므로 **나오는 곳마다** 얹는다(`sec` 비움).

**② 범위 정본 한 자리** — `scope_source.resolve()` / `save()`. 조판은 Y.OS
`scope.json`, 검수는 구글시트를 보던 갈림이 실제로 어긋났다(광문1: 시트 `독해기본1
1~2강` vs 책 `독해기본2 1~8강`). 조판이 쓴 범위를 `<책폴더>/원고/scope.json` 에
남기고 검수가 그것을 읽는다. `scripts/final_viv_review.py` = ①범위↔원고 ②원고↔PDF
③눈(`core.review_agent`, `YONE_REVIEW_AGENT=1` 일 때만). `render_vivlio` 끝에 붙어 있다.
⚠ 로컬 `claude` CLI OAuth 만료 상태 — ③층은 `claude login` 전까지 못 돈다(fail-open).

**③ 올림포스는 판이 넷** (독해기본1·2·고2기출·전국연합기출 고1). 같은 `13강` 이 네
곳에 다 있다 — 이름으로 후보만 좁히고 **범위가 짚은 지문 번호**로 확정
(`manuscript_locate.olympos(want=...)`). 판마다 강별 지문이 달라 이것이 내용 대조다.
못 가리면 **판을 바꾸지 않고** 각 판이 가진 번호를 늘어놓는다.

**④ 크레딧** — `scripts/final_credits_build.py` 가 `assets/final/credits.pdf` 의
이름 단만 다시 앉힌다(아래 붙박고 위로 자람). 명단 정본은 그 파일의 `ROLES`.

**Y.OS 화면 긁는 셀렉터가 2026-09-11 에 바뀌었다**: 칸이 `tr.children[2]` → `[1]`,
항목이 `div > div` → `grid-cols-[auto_1fr_auto]` 3칸 묶음. 새 스니펫은
`scripts/final_scope_fetch.py` 머리말에. 로그인이 필요해 **인앱 브라우저로는 안 되고
`claude-in-chrome`(사용자 실제 크롬)** 으로 떠야 한다. `/api/projects` 는 여전히
로그인 없이 열린다(보안 문제, 이미 보고).

관련: [[project_final_vivliostyle]] [[final_scope_source_yos]]
