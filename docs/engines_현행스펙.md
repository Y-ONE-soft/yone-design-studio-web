# 엔진 현행 스펙 (pre-overhaul 동결, 2026-07-03)

> Phase 0 산출물. 개편 전 "지금 실제로 되는 것"의 스냅샷 — 개편 후 회귀 판단의 기준선.
> 코드 전수 조사 기반 초안이며, 각 엔진 담당 작업 시 오류 발견하면 이 문서를 갱신할 것.

## whitebook — 화이트북 워크북

**용도**: 프리미엄북 화이트북 고정 조판 (Day 1–10, 주 3회)

**입력**: upload_spec 슬롯 w1-3_main (필수 .hwpx), w1-3_practice (선택 .docx), w1-3_main_ans, w1-3_prac_ans (선택). 파서는 외부 source 미사용.

**출력**: content.json (주 3개 Day 구조 + practices 배열), PDF 1개.

**검수**: 스토리 수 (config verify.expected_stories) + 오버플로우 ≤ max_overflow (기본 0) + PDF 생성 확인.

**특이사항**: 연습문제 해설(docx)은 별도 파서(practice_parser)로 리스트화되어 content.json 'practices' 키에 통합.

## blackbook — 블랙북

**용도**: 프리미엄북 블랙북 조판 (PART1 문제·어휘 + PART2 문제 + 해설)

**입력**: manuscript (다중, .docx/.hwpx) — 파일명 키워드(part1_problem, part2_problem 등)로 5종 섹션 분류. answers (선택 다중). 외부 source 미사용.

**출력**: content.json (sections dict: part1_problem/vocab, part2_problem, part1/2_answer). PDF 1개.

**검수**: 본문 스토리 수(기본 3개) + 정답 스토리 수(기본 2개) + 오버플로우 확인.

**특이사항**: jsx_timeout=1200초, 파일명 접두사 제거 후 분류(kind_parser.classify_filename).

## baenje — 배N제

**용도**: 프리미엄북 배N제 원고→RTF→InDesign (1000단락+ 처리)

**입력**: manuscript (필수, .hwpx/.docx) + answers (선택) 각 1개. parse()는 HWPX/DOCX→RTF 변환만 수행. 외부 source 미사용.

**출력**: RTF 2개 (manuscript.rtf, answers.rtf) — **content.json 없음**. PDF 1개.

**검수**: 오버플로우 ≤ max_overflow(기본 0) + 문제 수 매칭 + PDF 생성.

**특이사항**: jsx_timeout=900초, RTF를 InDesign이 직접 place.

## hanyoung — 한영보카

**용도**: 한영보카 단어장 자동 조판 (세로형+가로형 2종 분리)

**입력**: manuscripts (다중, .xlsx/.csv/.txt/.hwp/.docx/.pdf). 외부 source 미사용(로컬만).

**출력**: content_sero.json / content_garo.json (장당 단어 수 포함). PDF 2개(또는 1개).

**JSX**: run_indesign 오버라이드 — indesign_stepper.run_typeset()으로 Python 단계별 제어(AppleEvents -609 회피).

**검수**: 배치 완료 단어 수 ≥ 총수, 오버플로우=0, PDF ≥ 1개.

## cover — 세네카 조정

**용도**: 표지 AI 파일 세네카(책등) 크기 조정 후 PDF 출력

**입력**: ai_file (필수, .ai) + spine_mm + issue_num/out_name(선택).

**출력**: PDF 1개 (cover 폴더에 사본). **skip_indesign=True** — Illustrator를 osascript로 제어. verify()는 PDF 생성 여부만.

**특이사항**: 세네카 ≤3mm면 delete_spine=True.

## cover_pocketbook — 포켓북 표지

**용도**: 분석본 .ai에서 색상 3종(포인트/보조/배경) 자동 추출 → 학교별 포켓북 표지 PDF

**입력**: analysis_pdfs (다중 필수, .ai). parse()가 CMYK 색상 추출(fitz + numpy).

**출력**: 학교별 PDF+AI (다중이면 zip). verify(): PDF ≥ 1개.

**특이사항**: CMYK 벡터색 find-and-replace 기반. 템플릿 AI 고정(강동1).

## final_cover — 파이널 직전보충 표지

**용도**: 시험기간/학교/학년/Vol 선택 → 4페이지 CMYK A4 PDF (표지+빈면2+뒤표지)

**입력**: exam + school + grade + vols (드롭다운/다중, 커스텀 UI).

**출력**: Vol별 PDF (다중 시 zip). skip_indesign=True, Illustrator 직접 실행. 학교별 전용 .ai 템플릿(세종/광문/배재 등 매핑).

## pocketbook — 포켓북

**용도**: 분석본 .indd(GDrive) → JSX 스토리 복제 → 포켓북 내지 + PDF

**입력**: analysis_dir (필수 텍스트, 학교 폴더 경로) + review_tests(선택 다중 .docx) + listening_file(선택 .hwpx). parse()는 파일 목록 준비(조판은 JSX).

**외부 의존**: GDrive 분석본 폴더, 리뷰테스트 해설지(GDrive), 완성 포켓북 .indd(GDrive), 듣기 HWP.

**검수**: PDF ≥ 1개, 배치 완료 수, 오버플로우=0.

**특이사항**: jsx_timeout=1800초, GDrive zombie(EDEADLK) 대응, 혼합 파일 JSX 내 재분류.

## final — 파이널 직전보충(내지)

**용도**: GDrive 워크북 .indd 폴더 → JSX 지문 추출·병합 → 파이널 내지 + PDF (고1/고2)

**입력**: 업로드 아닌 **GDrive 폴더 탐색** ("워크북/{학년}/{교재명}") — 미러 redirect로 zombie 회피.

**출력**: content.json (vol1/vol2 블록 구조). verify()는 블록 수 일관성 + validation_warnings 통합 (엔진 중 가장 상세).

**특이사항**: 3단계 중복 제거(_drop_identical/_revised/_superseded), MD5 체크, 파서 6,352줄(최대).

## workbook — 워크북

**용도**: 고1·고2 STEP 1~3 원고(.hwpx/.docx) → 모의고사/교과서/EBS 자동 분류·조판

**입력**: manuscripts (다중). Step3 여부 파일명 정규식 판정. **외부 source 미사용** (전량 업로드).

**출력**: content.json + content_meta.json + step_*.json 분할(ExtendScript 1MB 제한 회피). PDF 1개.

**검수**: PDF 생성 확인 수준. jsx_timeout=600초. 학교 전용 템플릿 우선 lookup, exclude.txt로 섹션 제외.

## workbook_sero — 워크북 세로

**용도**: 세로버전 워크북 — 문제별 사이클 자동 복제/삭제

**입력**: manuscripts (다중). 출력: content.json(사이클 배열) + cycle_*.json 분할. PDF 1개.

**특이사항**: jsx_timeout=1500초 (사이클 복제+페이지 채우기).

## workbook_supp — 부교재 워크북

**용도**: WorkbookEngine 상속 — 학교 전용 내지만 다름. filename_stem.txt로 출력명 지정. indd lookup은 학교명 키(없으면 _default).

## textbook_workbook — 교과서 워크북

**용도**: 교과서 기반 워크북 (과목/출판사/과 선택)

**외부 의존**: **GDrive 교과서 작업 폴더** — parse가 manuscript_folder 메타의 GDrive 경로에서 원고를 직접 복사(_gdrive_safe_copy). list_subjects/publishers/lessons API로 UI 폴더 선택.

**출력**: content.json(STEP 구조) + 분할 + PDF. JSX는 workbook/run.jsx 공유.

## ebs_workbook — 리딩파워 워크북

**용도**: EBS 리딩파워 워크북 — Unit별 구조. **외부 의존**: ebs_base 고정 시리즈 경로에서 Unit 폴더 자동 탐색. JSX는 workbook/run.jsx 공유(모듈 로드 시 템플릿 캐시 — 변경 시 Flask 재시작 필요).

## suneungteukgang_workbook — 수능특강 워크북

**용도**: EBS 수능특강 워크북 — 강별 구조. **외부 의존**: ebs_base(series_subdir). 자체 run_indesign — **분석본(step1~2) + 문제본(step3) 2단계 순차 조판**, 다중 강 통합 시 spread duplicate 병합.

## seseospecial — 세서특필

**용도**: 특강교재 세서특필 (PART1 중요문장 + PART2 실전문제+정답)

**입력**: part1(.hwpx 필수) + part2(.hwpx 필수) + answers(다중 선택). 외부 source 미사용.

**출력**: content.json (school/part1/part2). 검수: PART1 단락 수 + PART2 문항 수 + 정답 수 + 오버플로우.

**특이사항**: 학교 키(광문1/2/3) 템플릿 lookup, 재실행 시 열린 indd 자동 닫음.

## mockexam — 동형모의고사

**용도**: 회차별 동형모의고사 조판 (학교+학년 템플릿)

**입력**: manuscripts (다중) + 메타(school/grade/exam_period/exam_date/exam_type). **외부 의존**: GDrive 템플릿 경로(학교별 패턴 lookup — 조판 단계만, parse는 업로드만).

**출력**: content.json(questions 배열) + settings.jobs[](회차별 indd). 검수: 회차별 PDF + 오버플로우.

## mockexam_sero_merge — 모의고사 세로 결합

**용도**: 문제 코드(YYMMQQ/자연어/범위) → 여러 회차 세로 .indd에서 페이지 추출·병합. **외부 의존**: GDrive 워크북 폴더. content.json 없음. jsx_timeout=900초, 장문(41~42) 중복 제거.

## analysis_merge — 분석본 결합

**용도**: 문제 코드 기준 분석본 .indd 페이지 추출·병합. **외부 의존**: GDrive 모의고사 작업 폴더. 변형 분석본(메인/보조/짤지문) 자동 매칭.

## mothertongue_merge — 마더텅 결합

**용도**: 엑셀(강별 지문 출처, YYMMQQ) → 분석본 병합. **외부 의존**: GDrive 분석본 + fallback_base(강 폴더 고정 인덱스). settings.jobs[]에 vol 키.

## vert_to_horiz — 세로→가로 본문 복제

**용도**: 세로 .indd 본문 → 가로 .indd 1:1 매핑 (엑셀 출처 순서 검증). **외부 의존**: 가로 원본(GDrive), sources_json. 출력은 가로 .indd in-place 수정. jsx_timeout=900초.

## 요약 표

| 엔진 ID | parse 오프라인 재실행 | GDrive 의존 | content.json | verify 범위 | 코퍼스 |
|---------|:---:|:---:|:---:|---|:---:|
| workbook | ✓ | ✗ | ✓ | PDF | ✓ 5건 |
| workbook_sero | ✓ | ✗ | ✓ | PDF | ✓ 3건 |
| mockexam | ✓(parse만) | 조판만 | ✓ | 회차 PDF/오버플로우 | ✓ 5건 |
| blackbook | ✓ | ✗ | ✓ | 스토리수/오버플로우/PDF | ✓ 5건 |
| seseospecial | ✓ | ✗ | ✓ | 문항수/정답수/오버플로우 | ✓ 5건 |
| whitebook | ✓ | ✗ | ✓ | 스토리수/오버플로우/PDF | 후보 |
| baenje | ✓ | ✗ | ✗(RTF) | 오버플로우/문제수/PDF | RTF 스냅샷 필요 |
| hanyoung | ✓ | ✗ | ✓(2종) | 배치수/오버플로우/PDF | 후보 |
| workbook_supp | ✓ | ✗ | ✓ | PDF | (workbook과 동일) |
| textbook_workbook | ✗ | ✓ | ✓ | PDF | 보류 |
| ebs_workbook | ✗ | ✓ | ✓ | PDF | 보류 |
| suneungteukgang_workbook | ✗ | ✓ | ✓ | PDF | 보류 |
| final | ✗ | ✓ | ✓ | 블록수+경고(최상세) | 보류 |
| pocketbook | ✗ | ✓ | ✓(목록) | PDF/배치수 | 보류 |
| mockexam_sero_merge | ✗ | ✓ | ✗ | PDF | 보류 |
| analysis_merge | ✗ | ✓ | ✗ | PDF | 보류 |
| mothertongue_merge | ✗ | ✓ | ✗ | PDF | 보류 |
| vert_to_horiz | ✗ | ✓ | ✗ | 로그 | 보류 |
| cover / cover_pocketbook / final_cover | ✓ | 일부 | ✗(PDF) | PDF 생성 | 보류(Illustrator) |
