---
name: pocketbook-analysis-pdf-intake
description: 분석본이 IDML 없이 Y.OS(비블리오) PDF로만 올 때 포켓북 왼쪽 면을 PDF에서 되읽는 경로(analysis_pdf) — 번호 충돌·iCloud dataless·macOS timeout 함정 포함
metadata: 
  node_type: memory
  type: project
  originSessionId: 58431e35-1942-4ebe-a7d0-7d20c66e751f
  modified: 2026-09-11T18:11:29.717Z
---

일부 분석본은 인디자인이 아니라 **Y.OS design(`~/dev/yos-design`, 크롬→pdf-lib)** 으로 조판돼 PDF 만 온다(2026-09-12 명일2 `명일여고2_분석본05(추가 읽기자료).pdf`). 원천은 Y.OS contents 의 output JSON(`sentences[].tagged` `word[TAG]`·`ko`·`gps`·`marks` — `proto/contract.json`)이지만 **이 기계엔 없다** → PDF 가 유일한 원본.

구현: `tools/pocket_harvest/analysis_pdf.py`(`read_book` = analysis.read_book 과 같은 모양) + 포켓북 `_pdf_sources`(PDF 가림)·`_subject_unit`(과목명 머리말 → `교과서 추가 읽기 자료`)·G-P13(기출 상자 = 깨끗한 사본)·G-P9(`source_count`). 회귀 시험 `tests/test_pocket_analysis_pdf.py`. 렌더에 `wave` 플래그·주석 아랫줄 `dn2`/`ruby2` 추가(기존 런 HTML 불변).

**Why:** 실측 오답 6개 — ① 주석 가운데가 긴 구간과 우연히 같다(`zero` V1 → `likely…on`) → **낱말 수 적은 것 먼저**(허용 1.5pt) ② 정리 면 기출 사본이 본문에 붙음 → 정리 면 먼저 판정 ③ VOCA 칸 쪼개짐 → 덩이로 묶고 머리 기준 ④ 물결은 **SMask** 에 있다 ⑤ 해석이 낱말 가운데서 줄바꿈, 줄 끝 공백 글리프 없음 → 코퍼스 어절 빈도 + 경계 음절쌍으로 잇기 ⑥ 분석본 **번호 충돌**(공유 폴더 05=추가읽기 PDF, 인디자인 폴더 05=25년10월) → IDML 양보는 번호가 아니라 **글(지문 머리)이 그 IDML 에 있을 때만**.

**How to apply:**
- 인디자인이 만든 PDF 는 읽지 않는다 — IDML 을 내보내라고 로그가 운다(명일2 분석본04·05(25년10월) 가 IDML 없이 PDF/INDD 만 있었다).
- 포켓북 `_corpus`·`_idml` 이 **iCloud dataless** 가 된다(1,878개 실측). 읽기 하나에 3분 — 조판 전 `brctl download` 파일 단위로. `find -flags dataless` 는 정확 일치라 `compressed,dataless` 를 놓친다 → `st_flags & 0x40000000`.
- macOS 에 `timeout` 명령이 없다 — `timeout 90 rg …` 는 조용히 아무것도 안 한다(첫 검색이 헛돌았다).
- 관련: [[project-pocketbook-gwangmun-2609]] [[feedback-gate-regression-proof]] [[feedback-parser-structural-not-pattern]]

**오른쪽 면도 읽는다(2026-09-12).** 분석본마다 다르다 — NOTE 상자가 빈 판(학생이 쓴다)도 있고 글이 든 판도 있고, 어휘표에 유의어·반의어 칸이 있는 판도 있다(강동 2024). 있으면 그게 정본이라 `_authored`·코퍼스로 다시 쓰지 않는다(`_fill_from` 이 빈 곳만 채운다). `_voca_table`(머리글 **이름**으로 칸을 가른다 — 강동 2024 유의어·반의어 vs 배재 반의어·동의어로 **순서가 다르다**) · `_flow_note`(상자 경계 = **그려진 네모**. 단 가운데로 어림하면 옆 단 `[정답] : ②` x283 이 딸려 온다). 머리글을 크기(5.9 vs 9pt)나 색(강동 머리글이 구문분석 파랑 `#557abc`)으로 가르면 표가 통째로 안 읽힌다. `핵심기출문제`와 `FLOW NOTE`는 **기준선이 같아** 한 줄로 묶인다 → 이름표는 줄이 아니라 **조각**(`_label_bits`)으로 찾는다. 표본은 Y.OS 실제 엔진으로 찍어 리포에 뒀다(`tests/corpus/pocket_analysis_pdf/`, 시험 `tests/test_pocket_analysis_pdf_right.py`) — 프리셋만 갈아 `proto/build.py` 의 prerender → 우리 vivliostyle 로 찍으면 판을 더 만들 수 있다(그 리포 파일은 건드리지 않는다).
