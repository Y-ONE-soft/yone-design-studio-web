# 수동 JSX ↔ 엔진 JSX 이원화 매핑 (C2-10)

> 리스크분석 C2-10 산출물 (2026-07-06 조사). `조판/인디자인 스크립트/`의 수동 실행 스크립트와
> Flask 엔진 JSX(v1 `engines/*/jsx/run.jsx` + v2 `core/jsx/*.body.jsx`)가 같은 패턴의 두 계보다.
> 이 문서는 "같은 기능의 두 계보 중 어느 쪽이 진실(최신 로직)인가"를 다음 세션들이 참조하기 위한 매핑이다.
> 판정 근거: 수동 스크립트 mtime ↔ 엔진 파일의 마지막 git 커밋일(summer-2026 기준) + 코드 패턴 교차 확인.
> 확신이 없는 항목은 **미확인**으로 명시했다 — 실제 diff 검증 없이 날짜만으로 단정하지 않았다.

## 요약

- 수동 스크립트 폴더: `/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/인디자인 스크립트/` — .jsx 약 100개 (git/버전관리 없음, 단일 사본)
- 3분류:
  - **v2 흡수**: 워크북 STEP1~2, 화이트북, 블랙북 — v2 플랜 빌더(`core/jsx/*_flow.body.jsx` + `engines/*_v2/`)가 최신 진실
  - **v1 엔진이 진실**: STEP3, 포켓북, 파이널/마스터 — 엔진 v1이 수동보다 최신
  - **수동 전용 / 수동이 최신**: ConvertToVertical, Merge 계열 일부, Voca/M_ 계열, 유틸리티 ~21개 — 엔진 대응이 없거나 수동 쪽에 미이식 수정이 남아 있을 수 있음
- **언더스코어 쌍(`STEP1A1.jsx` vs `STEP1_A1.jsx` 등)은 바이트 동일한 완전 중복** (샘플 diff 확인: STEP1A1/STEP1_A1, STEP1C1/STEP1_C1, STEP2A1/STEP2_A1)

## 기능군별 매핑 표

| 기능군 | 수동 스크립트 (mtime) | 대응 엔진/v2 (마지막 커밋) | 어느 쪽이 최신 | 분류 |
|---|---|---|---|---|
| 워크북 STEP1 (기본학습) | STEP1{A1,A2,B1,B2,C1,C1_New,C2}.jsx + `STEP1_*` 중복쌍 (2026-05-15) | v1: `engines/workbook/jsx/run.jsx` (06-26) / v2: `engines/workbook_v2/` + `core/jsx/workbook_flow.body.jsx` (07-05) | **v2 엔진** — 플랜 빌더(`engines/workbook_v2/plan.py`)로 재구현, v1 실물 dump 파리티 검증 이력 있음 | v2 흡수 |
| 워크북 STEP2 | STEP2{A1,A1Practice,B1,C1,C2}.jsx + `STEP2_*` 중복쌍 (2026-05-15, C2는 02-22) | 동일 | **v2 엔진** | v2 흡수 |
| 워크북 STEP3 (테이블/자동배치) | STEP3.jsx (04-08), STEP3_{RE,AutoLayout,TableFix,Diagnostic,BreakUp,Test2}.jsx (03-31) | `engines/workbook/jsx/run.jsx` 내 STEP3 로직 (06-26) | **엔진 v1** (날짜상) — 단 STEP3_AutoLayout/TableFix의 테이블 보정 로직이 엔진에 전부 이식됐는지 **미확인** | v1 엔진 |
| 화이트북 | WhiteBook_{A,B,E,E2}.jsx (03-18~20), 화이트북_조판자동화.jsx, 화이트북_검수및PDF.jsx (03-25) | v1: `engines/whitebook/jsx/run.jsx` (05-18) / v2: `core/jsx/whitebook_flow.body.jsx` + `engines/whitebook_v2/` (07-04) | **v2 엔진** | v2 흡수 |
| 블랙북 | BlackBook_E.jsx (03-20), BlackAnswer.jsx (03-31) | v1: `engines/blackbook/jsx/run.jsx` (07-03) / v2: `core/jsx/blackbook_flow.body.jsx` + `engines/blackbook_v2/` (07-04) | **v2 엔진** | v2 흡수 |
| 포켓북 | Pocketbook{Icon,BreakUp}.jsx (03-31 이전), PocketbookListening.jsx (04-08), Pocketbook{AddBox,RemoveBox}.jsx (06-04) | `engines/pocketbook/jsx/run.jsx` (06-20) + `engines/cover_pocketbook` | **엔진 v1** (06-20 > 수동 06-04) — v2 미이행 | v1 엔진 |
| 모의고사 분석본 merge | MergeMockExam.jsx (05-02), MergeMockExamSero.jsx (06-04) | `engines/mockexam_sero_merge/jsx/run.jsx` (06-14) | **엔진일 가능성 높음** (06-14 커밋이 수동 06-04 이후 — 수동을 이식한 스냅샷으로 추정) — 가로판 MergeMockExam.jsx의 엔진 대응은 **미확인** | 부분 흡수 (애매) |
| 교과서/마더텅 merge | MergeTextbook.jsx (03-05), Slim_Merge.jsx (05-26), Slim_Merge2.jsx (05-06), MergeRightToLeftBottom.jsx (05-20), frame_merge.jsx (03-31) | `engines/analysis_merge/jsx/run.jsx` (06-14), `engines/mothertongue_merge/jsx/run.jsx` (05-18), v2 `core/jsx/merge_spreads.body.jsx` | Slim_Merge.jsx(05-26)가 mothertongue_merge(05-18)보다 이후 수정 — **수동 쪽에 미이식 수정 가능성**, 대응 자체도 1:1이 아님 (**미확인**) | 부분 흡수 (애매) |
| 세로 변환 | **ConvertToVertical.jsx (06-17 — 수동 폴더에서 가장 최신)**, ConvertToVertical_OLD.jsx, 백업본 | 직접 대응 엔진 없음. 역방향(`engines/vert_to_horiz/jsx/run.jsx`, 06-14)과 세로 조판 v2(`core/jsx/workbook_sero_flow.body.jsx`)만 존재 | **수동이 유일본** — 가로→세로 일괄 변환은 엔진 미이식 | 수동 전용 |
| 가로 변환 (역방향) | ConvertVertToHoriz.jsx (05-17) | `engines/vert_to_horiz/jsx/run.jsx` (06-14) | **엔진** (06-14 > 05-17) | v1 엔진 |
| 파이널/마스터 | FinalVol{1,2}.jsx (03-27), Final_test.jsx (2025-12), Master_Applied{,2,(C)}.jsx (03-31), **Master_Source.jsx (06-19)**, Master_Source_Cancel.jsx | `engines/final/engine.py` + 파서 군 (07-02) — 단 Master_* 는 O-마스터 프레임 조작용으로 final 엔진과 목적이 다를 수 있음 (**미확인**) | final 조판 자체는 **엔진**. Master_Source.jsx(06-19)의 역할은 엔진 미대응 추정 | v1 엔진 + 수동 전용 혼재 |
| 마더텅 어휘 (M_ 계열) | M_{Words,Polysemy,SYN,Script}.jsx (03-31) | 직접 대응 없음 (`engines/final/mothertongue_grammar_loader.py`는 원고 파싱이지 이 JSX 기능 아님) | **수동이 유일본** | 수동 전용 |
| 어휘 (Voca 계열) | Voca{1,2,3}.jsx, Voca_Paichai{,2}.jsx (03-31) | 직접 대응 없음 | **수동이 유일본** | 수동 전용 |
| 시험범위 필터 | ExamScopeFilter.jsx (05-29) | 대응 없음 | **수동이 유일본** | 수동 전용 |
| 유틸리티 (~21개) | FrameBreak, AllSplitStory, DeleteEmptyParas, DeletePassageNum, CheckStyles, AnalyzeDoc, Links_Replace, Relink(06-05), RelinkKoreanToEnglish, PageInterleave, ReSection, RealignAnchoredFrames, ReviewTestReturn, SplitAndConnectOMaster(05-12), TableWidthFix, AlignToLayoutGuides(05-07), Frame_Omaster, STEP3BreakUp, pdf_resizing, get_bounds, _Debug_FolderCheck | 대응 없음 (일회성 수작업 보조 도구) | **수동이 유일본** | 수동 전용 |
| 진단/덤프 | AnalyzeDoc.jsx, STEP3_Diagnostic.jsx | `core/jsx/dump_stories.jsx`, `core/inspect.dump_indd`, `engines/mockexam/jsx/diagnose_styles.jsx` | **엔진** — v2 검수 인프라가 상위 호환 | v2 흡수 |

## 위험 항목 (계보 분기 의심 — 우선 확인 대상)

1. **ConvertToVertical.jsx (06-17)** — 수동 폴더 최신 파일인데 엔진 대응이 없다. 세로판 작업의 입구가 아직 수동. 06-16 백업본과 _OLD가 함께 있는 것으로 보아 활발히 수정 중이던 스크립트.
2. **Master_Source.jsx (06-19)** — 최근 수정인데 엔진 대응 미확인. 어떤 흐름에서 쓰이는지 운영자 확인 필요.
3. **Slim_Merge.jsx (05-26) vs mothertongue_merge (05-18)** — 수동이 8일 뒤 수정. 엔진에 미이식된 수정이 있는지 diff 필요.
4. **STEP3 계열** — v2 플랜 빌더가 아직 STEP3 테이블 로직을 커버하지 않음. `STEP3_AutoLayout.jsx`(35KB)·`STEP3_TableFix.jsx`의 로직이 v1 엔진에 완전 이식됐는지 미검증.

## 운영 결론

- **v2가 진실인 곳**: 워크북 STEP1~2, 화이트북, 블랙북, 세서스페셜/수능특강 계열. 수동 STEP* / WhiteBook_* / BlackBook_* 스크립트는 참조용 유산으로 취급 — 수정하지 말고, 로직 차이가 궁금하면 v1 실물 출력 dump 대조(development-guide.md의 교훈)로 확인.
- **수동이 진실인 곳**: ConvertToVertical, Voca/M_ 계열, ExamScopeFilter, 유틸리티 전부. **이 폴더는 git 미추적 단일 사본** — 유실 시 수동 전용 로직이 영구 소실된다 (재해복구_절차.md의 백업 공백 1순위와 연결).
- 장기 방향(리스크분석 C2-10): 수동 전용 중 반복 사용되는 것부터 엔진/스킬로 흡수하고, 수동 폴더 자체를 저장소에 스냅샷으로 추적하는 것을 권고.
