# 워크북 v2 전환 로드맵 (2026-07-05, v1 JSX 전수 인벤토리 기반)

## 스텝별 이식 난이도 (에이전트 전수 분석 — 상세는 세션 기록)

| 스텝 | GREP | 아이콘 | 브레이크 | 판정 | 이식 방법 |
|---|---|---|---|---|---|
| step3 | 5+ | - | - | **W1 완료** | kind 주석 + style_map (v1 480줄 휴리스틱 대체) |
| 1A1 | 2 | - | ✓ | 순수텍스트 O | GREP→파이썬 전처리, 브레이크→유닛 경계 |
| 1B2 | 2 | - | ✓ | 순수텍스트 O | 패턴 스타일→플랜 |
| 1C2 | 1 | - | - | 순수텍스트 O | 탭→줄바꿈 + 한글감지 스타일 |
| 2A1 | 3 | - | ✓ | 순수텍스트 O | 헤더→{tail} 정규화 파이썬 |
| 2A1Btm | - | - | ✓ | 순수텍스트 O | 원문자 필터 |
| 2C1 | 1 | - | - | 순수텍스트 O | 1C2와 동일 |
| 1A2 | 1 | TF버튼 | ✓ | 아이콘 op | 인라인 duplicate 삽입 |
| 1B1 | 5+ | 문제아이콘 | ✓ | 아이콘 op | + 주제/제목 빈줄 로직 |
| 2B1 | - | TF(링크) | ✓ | 아이콘 op | itemLink place |
| 2C2 | 3 | 영작답지 | ✓ | 아이콘 op | + 빈줄 관리 |
| 1C1 | 15+ | 화살표 | 복합 | **최난** | NEXT_PAGE/FRAME 분기 + 발문 삽입 |

## 단계 계획
- **W1 (완료)**: 스켈레톤(step_map/plan/실행기) + step3 빌더 + E2E
- **W2**: 순수 텍스트 6스텝 — GREP·삭제·패턴스타일을 파이썬 플랜 전처리로 이식
- **W3**: 실행기에 generic 아이콘 op ({"icon": {label, where}}) + 4스텝 (1A2/1B1/2B1/2C2)
- **W4**: 1C1(최난) + 엔진 래퍼 + v1/v2 전 스텝 나란히 대조 + registry

## 실행기/플랜 위치
- 플랜 빌더: engines/workbook_v2/plan.py (STEP_BUILDERS 레지스트리)
- 실행기: core/jsx/workbook_flow.body.jsx (marker/master 스토리 탐색 + 오버플로우 페이지 확장)
- 스토리 매핑 데이터: engines/workbook_v2/step_map.json

## 진행 로그 (자율 진행 — 2026-07-05 야간)
- W1 완료: step3 (누락0/오버플로우0, 커밋됨)
- 이하 각 단계 에이전트가 완료 시 여기에 결과를 추가한다.
- **W2 완료**: 순수 텍스트 6스텝 이식 (1A1/1A1_2/1B2/1C2/2A1/2A1Btm/2C1 — GREP·삭제·패턴스타일을 파이썬 전처리로, v1 판정 정규식 그대로 이식). E2E(0a5da924, 실 InDesign): 지원 8스텝 전부 내용 보존 누락 0 ✅. 함정 해결: 2,000+단락 스토리에서 story.paragraphs 컬렉션 인덱싱 행 → everyItem().getElements() 1회 캐시 필수 (v1 blackbook 주석의 함정 실증).
- **W3 완료**: 아이콘 4스텝 이식 (1A2/1B1/2B1/2C2). 실행기에 generic 아이콘 op({"icon":{label,pos}} — findLabeledItem duplicate/링크 place, 역순 삽입) 추가. E2E(0a5da924): 12스텝 전부 내용 보존 0누락 + 아이콘 검증 통과 (TF 버튼 90+133, 문제아이콘 18, 영작답지 70). 함정: 구버전 렌더가 InDesign 점유 시 반드시 정리 후 재실행 (락 /tmp/indesign_exec.lock).
- **W4 완료**: step1_c1(최난) 이식 + 엔진 래퍼 + registry 등록.
  - **step1_c1 빌더** (plan.py build_step1_c1): v1 processStep1C1(run.jsx 1136~1648)을 패스 순서 그대로 이식 — 공백 bracket 제거 → 헤더 정규화 GREP 11종+레지듀얼 3종×3회(_sub_runs로 밑줄 runs 오프셋 보존) → 프리앰블 제거((A) 안전장치 포함) → 스타일 패스(기본/헤더 뒤 BTM/선지 C1/3+공백 BTM+탭·선행공백 제거/(A|B|C) BTM_T/원문자 BTM_T/BTM~BTM_T 갭 빈줄 제거/교과서 분기) → 화살표 답지 아이콘(비EBS \r\r 2단락, EBS 빈 단락 재사용) → 발문 삽입(원문자→위치/(A-Z)→순서, 하단 문제 스타일+STEP1 문제아이콘+탭) → { 안전망 → 헤더 잔재 정리 → step1_c1_btm 제외 지원.
  - **프레임 분리**: v1 "FRAME BREAK 재적용"(2026 회귀 대응 최종 패스)의 실효 동작을 유닛화 — 헤더(2번째+) = 유닛 {"page_break": true}(실행기 NEXT_PAGE, EBS는 NEXT_FRAME), 블록 내 첫 하단 스타일 단락 = NEXT_FRAME. 실행기(workbook_flow.body.jsx)에 유닛 dict 형식({"paras","page_break"}) + NEXT_PAGE 지원 추가 (기존 list 유닛과 하위호환).
  - **style_map**: workbook.STEP1C1에 BTM("C1_문장 배열 하단")/BTM_T("C1_문장 배열 하단 지문") 추가 — 실물 인벤토리 가드 통과.
  - **엔진 래퍼** (engines/workbook_v2/engine.py): parse = v1 parse_manuscript_folder 재사용(Step3 파일명 판정 포함), prepare_jsx = steps_to_plan(exclude.txt 반영) + v1 config indd_original[workbook_type] safe_copy(학교 전용 lookup 포함, 출력명 v1 규칙+_v2 접미), run_indesign(마커 "워크북 v2 조판 완료", 1800s), verify = 검수 게이트 내장(스텝별 플랜 단어 보존/미지원 스텝 보고/오버플로우 경고/PDF, 타이포그래피 정규화). registry 24번째 append + subjects.json 워크북 v1 카드 뒤 v2 카드.
  - **검증**: pytest 전체 71개(기본 python3 + py3.9 실서비스 인터프리터) 통과 — step1_c1 플랜 6종(유닛/스타일/발문·화살표/보존 4코퍼스/EBS 분기/하단 제외) + 엔진 parse 스모크(0a5da924 → 13스텝 재현) + 등록 정합성. 스테이징(5011): 로그인 → 인덱스 "워크북 v2 (베타)" 카드 + /typeset/workbook_v2 200 + v1 페이지 무회귀 확인.
  - **실 InDesign 엔진 E2E (부분 성공 + 보류)**: scripts/e2e_engine_workbook_v2.py(코퍼스 0a5da924, 출력 data_corpus/wb_engine_e2e 리다이렉트, config 패치로 운영 경로 무접촉). 1차 실행에서 **렌더 전 과정 성공 확인**: 13스텝 전부 배치(미지원 0), step1_c1 292단락/36유닛 + NEXT_PAGE 프레임 분리 + 문제아이콘 18 + 화살표 답지 18 삽입, 문서 저장(17MB), 오버플로우 1(기존 step2_c2). 그러나 PDF export 단계에서 runner의 행 판정 오탐(아래)으로 InDesign이 강제 종료 → 이후 재시도는 InDesign의 유령 모달 상태(아래 보류)로 미완. **verify ok=True 최종 확인은 보류 상태.**
  - **함정 해결 (runner stall 오탐)**: 전체(C) 문서(250p+)의 doc.save+PDF export가 로그 무갱신 5분을 초과 → runner의 행(hang) 판정(STALL_LIMIT 300초)이 정상 export 중 InDesign을 강제 종료. core/indesign/runner.py에 opt-in `stall_limit` 파라미터 추가(기본 300 무변경 — 다른 엔진 영향 0), workbook_v2만 900으로 상향.
  - **⚠️ 보류 (InDesign 유령 모달 — 환경 이슈, 코드 무관)**: 강제 종료 이후 InDesign 2026이 재기동될 때마다 보이지 않는 모달 상태에 갇힘 — `do script` 파일IO는 동작하나 `app.scriptPreferences.userInteractionLevel` 대입과 `app.open()`이 30486("다른 대화 상자 또는 경고가 활성화") 오류. 창 0개(System Events), 화면에 다이얼로그 없음, activate 불가. RecoveryData/ProtectiveShutdownLog/InDesign SavedData 제거(백업: /tmp/indesign_recovery_backup_*, /tmp/indesign_saveddata_backup_*)와 graceful 재기동 + 5분 settle로도 미해소. 3회 실패 후 킬 루프 금지 규칙에 따라 중단. **후속 조치**: 사람이 InDesign GUI를 직접 열어 상태 확인(숨은 경고 해제 또는 재부팅) 후 `python3 scripts/e2e_engine_workbook_v2.py 0a5da924` 1회 재실행으로 verify ok=True 확인. 곁들여 runner의 콜드스타트 `open -a /Applications/<폴더>` 경로 버그(kLSNoExecutableErr, 별도 백그라운드 태스크 칩 발행됨)도 이 과정에서 드러남.
- **W4 미해결 목록 (이식 타협 지점)**:
  1. **EBS ~M(FRAME_BREAK 문자) GREP 미이식** — v1은 EBS에서 startParagraph 외에 ~M 메타문자를 헤더 앞에 추가(이중 안전장치). v2는 유닛 경계 NEXT_FRAME만 사용. EBS 실기(리딩파워 내지)에서 frame 분리가 깨지면 실행기에 FRAME_BREAK 문자 삽입 op 추가 필요.
  2. **조건(주어진 문장) NEXT_FRAME 엣지** — v1의 conditionIdxList는 2026 회귀로 스타일 재적용 시 지워져, '어떤 스타일 패스도 안 건드린' 조건 단락만 실효. v2는 그 실효 동작만 이식(_cond+미스타일 단락 유닛 분리). 코퍼스 4케이스에선 모두 BTM으로 스타일링돼 미발동 — 실기 검증 없음.
  3. **스텝 전체 제외 시 페이지 삭제 미이식** — v1 JSX는 excluded 스텝의 페이지를 삭제. v2는 렌더만 생략(템플릿 자리 유지). step1_c1_btm(하단만 제외)은 v1과 동일(빈 프레임 유지)이나, 스텝 전체 제외 UI 사용 시 페이지가 남는다.
  4. **교과서(《제목》 하단)/동아박 실기 미검증** — 교과서 분기(pass G)는 v1 로직 그대로 이식했으나 교과서형 step1_c1 코퍼스가 없어 mockexam/리딩파워 원고로만 단위 검증. 교과서 워크북 실전 투입 전 1회 실기 대조 필요.
  5. **step2_c2 오버플로우(W3부터 존재)** — 모의고사 템플릿에서 영작 배열 스토리 오버플로우 페이지 확장 +10에도 1스토리 잔존 → verify 경고로 지목(수동 처리). v1도 동일 원고에서 오버플로우 발생하는 초장문 케이스.
- **W4 완료 + 최종 E2E 통과**: step1_c1 이식(GREP 11종+화살표+NEXT_PAGE 분기+발문 삽입), 엔진 래퍼(workbook_v2, registry 24번째, 검수 게이트 내장), 스테이징 확인. 최종 엔진 E2E: **verify ok=True — 13스텝 플랜, 플랜 단어 누락 0, PDF OK, 오버플로우 1(step2_c2 기지 1건, 경고)**. 미해결 4건은 위 W4 항목 참조 (EBS ~M 브레이크, 조건 엣지, 스텝 제외 페이지 삭제, 교과서 분기 실기).
- **야간 운영 사건 기록**: 강제종료 누적 → InDesign 복구 데이터가 재기동마다 비가시 모달(30486)로 스크립팅 차단. 해법: 복구 폴더(~/Library/Caches/Adobe InDesign/Version 21.0-J/ko_KR/InDesign Recovery) 내용물 백업 이동(~/Backups/indesign_recovery_backup_20260704_0542, 41개 — 전부 자동 실행 스크래치) 후 재기동. PDF export의 300초 행 오탐은 runner opt-in stall_limit(워크북 900초)로 해결.
- **W5 완료 (2026-07-04): 워크북 가족 2엔진 v2 전환 — workbook_supp_v2 + workbook_sero_v2.**
  - **workbook_supp_v2**: WorkbookV2Engine 100% 상속 (v1 supp의 상속 구조 재현). WorkbookV2Engine.prepare_jsx를 훅 2개(_output_name/_select_template — 기본 구현은 기존 동작 그대로, 회귀 가드 테스트 포함)로 리팩터링하고 supp는 훅만 오버라이드: 내지 = 학교명 키 lookup → "_default" 폴백, 출력명 = {학교}_워크북{stem}_내지_v2.indd (filename_stem 필수). 실 InDesign E2E(워크북 코퍼스 0a5da924): verify ok=True — 13스텝 누락 0, 훅 경로 실증(워크북E2E테스트_내지_v2.indd), 오버플로우 1(기지 step2_c2, 경고).
  - **workbook_sero_v2 (신규 능력 = 사이클 복제)**: 파서 = v1 workbook_sero.parser 재사용(사이클 분할). 플랜 = engines/workbook_sero_v2/plan.py — 사이클×슬롯(페이지 프레임) 재편성, workbook_v2 STEP_BUILDERS 전부 재사용 + v1 seroAugment 마커 prepend([N]/[code]/{N}/{code}) + step3 kind 주석(classify_paragraphs, 세로 파서엔 없음) + {code} $BASIC 선두. 실행기 = core/jsx/workbook_sero_flow.body.jsx 신설: 사이클 수 조정(14p 사이클 복제/삭제 — v1 seroAdjustCycles 이식), 슬롯 기하 해석(p0 top/bot, p6 sel/btm, pN main/num — v1 seroBodyFrames), STEP3 페이지 통째 복제+프레임 연결 오버플로우 해소, 빈 STEP3 페이지 M 마스터, q_num 소형 프레임 표기, clear 슬롯(원고 없는 프레임 잔존 데이터 비움). 배치부는 workbook_flow와 동일 의미론(스타일/밑줄 runs/유닛 브레이크/아이콘 op). 플랜은 사이클별 분할 파일(cycle_plan_NN.json — eval 1MB 회피).
  - **E2E 3회 전부 verify ok=True** (템플릿 [원본]워크북(세로)_내지 → data_corpus 사본, 스펙 픽스처 tests/fixtures/template_spec_workbook_sero.json): ① 7사이클(삭제 경로, 258→103p) 누락 0/오버플로우 1(아래), ② 19사이클(--expand, **복제 경로** 258→271p) 누락 0, ③ C1 보강 후 재실행. v1 실물 출력(같은 코퍼스 job의 조판 결과 indd를 dump)과 오버플로우 1:1 대조 — 잔존 1건([41~42] 합본 스토리 overset)은 v1에도 동일(템플릿 유래, 경고로 지목).
  - **함정 1 (조건 NEXT_FRAME — W4 미해결 2번의 실증)**: v2의 step1_c1 _cond 유닛 분리가 세로 코퍼스에서 최초 발동 → 사이클 C1 페이지(프레임 2개)가 3프레임을 요구해 오버플로우 3건. v1 실물 출력 dump로 확인: v1의 FRAME BREAK 재적용은 헤더+하단 첫 단락만 복원하고 조건 분리는 복원하지 않는다. → build_step1_c1에 opt-out `split_condition`(기본 True — 가로 무변경) 추가, 세로만 False. **가로 workbook_v2도 실기에서 _cond 발동 시 v1과 다르게 렌더될 수 있음** (칩 발행 없음 — 가로 템플릿은 프레임이 많아 오버플로우 대신 배치 이동으로 나타날 것, 실기 확인 필요).
  - **함정 2 (문장삽입 C1 조건 방치)**: v1 세로 파서 helper(_augment_step1_c1_passage)는 '(A)-다음' 변형만 커버 — ①-번호 본문 변형(문장삽입)에서 v1 실물 출력은 조건 무스타일 + 발문 미삽입 + 빈 박스(열화). 세로 v2는 plan의 _augment_c1_condition_gap으로 일반화(조건에 3+공백 부여 → BTM 분홍 박스 + 발문 자동 삽입 — 템플릿 레퍼런스 레이아웃 복원). v1보다 개선된 지점으로 기록.
  - **함정 3 (step3 kind 공백)**: 문장삽입 발문("들어갈 위치" 등)이 taxonomy 미등록 → q_code 없음 → P-CONTEXT(배경) 미부여. 세로 v2는 plan에서 v1 processStep3 규칙(주어진 문장/글·들어갈 위치 → 다음 첫 지문 배경)을 후처리 보강. **가로 workbook_v2에 동일 공백 존재 — 백그라운드 태스크 칩 발행됨.**
  - **검증**: pytest 89개(기본 python3 + py3.9) 통과 — 세로 플랜 9종(슬롯/마커/step3 kind/보존/게이트/C1) + supp 훅 6종 + 등록 정합 확장 + parse 스모크. 스테이징(5011): 로그인 → 인덱스 카드 2개 + /typeset/workbook_supp_v2·workbook_sero_v2 200 + v1 페이지 무회귀.
- **W6 완료 (2026-07-04): whitebook v2 전환 (registry 27번째) — 실 E2E verify ok=True + v1 실물 덤프 0 diff.**
  - **구성**: 파서 = v1 완전 위임(WhitebookEngine.parse — 외부 parse_whitebook.py + practice_parser, 골든 파리티 자동). 플랜 = engines/whitebook_v2/plan.py(wbwt-flows-v1): v1 run.jsx v3의 Day 루프/buildAnswerItems/postProcessAnswerStory를 데이터로 — GREP 2종은 파이썬 전처리(D박스 ①앞 공백→단락 분할 `_split_ones`, `<u>`마커→밑줄 runs `_ul_runs`), 정답 ops(번호 재시작 인덱스/'정답' 문자스타일/섹션 아이콘 sec0~4/2번째 프레임 기하)를 플랜에서 계산. 실행기 = core/jsx/whitebook_flow.body.jsx 신설(기존 3종과 배치 의미론 상이 — 첫 단락 스타일/정답 시그니처/F·C-마스터 기하로 스토리 탐색 → 유닛 i↔스토리 i 통째 교체 + ops: expand_last/expand_move/numbering_restart/ans_char/icons(색상 프레임 생성+앵커)/ans_frame_fix + 주차 GREP). 엔진 래퍼 whitebook_v2(출력 {학교}_화이트북{NN}_내지_v2.indd, stall_limit 900), 공용 typeset.html(v1과 동일 슬롯), subjects 카드.
  - **코퍼스**: tests/corpus/whitebook 2건 — jobs 이력에 whitebook job이 딱 2건뿐(3~5건 목표 미달, 확대 불가). build_corpus에 시그니처 추가(blackbook과 settings 키 동일 → content "days"로 구분) + 구 슬롯명(week2~4/ans2~4→w*_main/w*_main_ans) 개명 이식(LEGACY_SLOT_ALIASES). _replay.build_uploaded에 슬롯 접두사 충돌 수정(w1_main vs w1_main_ans — 실서비스는 무관, replay 전용 버그).
  - **검수 게이트(v1 계승+강화)**: 플랜 단어 보존 + **유닛 1:1 대조**(각 유닛의 (정규화 텍스트, 단락스타일) 열이 실제 스토리로 존재 — ￼/개행 제거+타이포 정규화) + v1 expected_stories 계승(스토리수 로그 파싱, D항목은 v1 config의 8이 stale → 실물 10으로 보정) + 배치 유닛 수/아이콘 수 로그 대조 + 오버플로우 경고(앵커 아이콘 의사 오버플로우 제외).
  - **E2E (1회 통과)**: e41f1c70(Day11~20 + 연습문제 3주) — 스토리수 전부 예상 일치, 누락 0, 유닛 불일치 0, 아이콘 50/50, PDF OK, 오버플로우 1(D박스 '① for the benefit of' — v1 실물·템플릿에도 동일 존재, 경고 지목). **v2 출력 덤프 ↔ v1 실물 출력(2026-05-13 배재1_화이트북01) 덤프 스토리 단위 완전 일치(양방향 0 diff)** — 텍스트+단락스타일 기준.
  - **실물이 가르쳐준 것**: (1) **[원본] GDrive 템플릿은 이미 조판된 출력물**(Day11~20 콘텐츠+아이콘 100개 baked) — replaceContent가 옛 앵커 아이콘을 자동 소거하므로 동작엔 문제없으나, 코퍼스와 템플릿 내용이 같아 단어 보존 게이트만으론 무력 → 유닛 1:1 대조+실행기 로그 파싱을 게이트에 추가한 이유. (2) v1 config expected_stories의 D항목 8은 구템플릿 기준 stale(현행 10) — v1 verify는 현행 템플릿에서 항상 ok=False였던 셈. (3) 앵커된 섹션 아이콘 프레임(6.3mm)은 dump에서 50개 전부 overflow로 잡힘(v1 자체 카운트는 doc.textFrames라 미포함) — v2 실행기는 doc.textFrames(v1 파리티), verify는 아이콘 스토리 제외.
  - **테스트**: 106개(양 인터프리터) — 플랜 9종(v1 로그 파리티 앵커: Day11 정답 136단락/D항목 24개 등)+엔진 4종+스냅샷 2건+인벤토리 가드(template_spec_whitebook.json, 그룹 경로 "정답 > 정답_" 등 — v1 getStyle의 그룹 1단계 탐색을 전체 경로로 표기). 스테이징(5011): 카드+/typeset/whitebook_v2 200+v1 무회귀.
  - **미해결/주의**: (1) 코퍼스 2건 모두 같은 원고(워드마스터 Day11~20) — 다른 호(issue)의 원고 실기 검증 없음. (2) 템플릿이 조판물이라 새 호 조판 시 잔여 콘텐츠 위 덮어쓰기 구조는 v1과 동일(진짜 깨끗한 원본 아님 — 템플릿 정비는 별도 과제). (3) D박스 오버플로우 1건은 템플릿 유래(v1 동일) — 수동 처리 관행 유지. (4) 3b3ddc5a(구 슬롯 job)의 practices는 빈 배열로 재생성됨(당시 UI에 연습문제 슬롯 없었음 — 원본 content.json에는 키 자체가 없던 것을 현행 파서가 빈 값으로 채움, 골든은 현행 출력 기준).
- **W5 미해결 (세로/부교재)**: (1) 세로 원본 로컬 사본 부재 — v1 config의 로컬 경로(조판/인디자인 원본/[원본]워크북(세로)_내지.indd)가 실기기에 없어 GDrive 폴백으로 동작(v1과 동일 조건). (2) [41~42] 합본 잔존 overset 스토리 — 사이클 삭제 후 프레임 없는 스토리가 남음(v1 동일), 검수가 경고로 지목하나 InDesign에서 스토리 삭제 정리는 미구현. (3) 세로 exclude UI quirk 보존 — step1_a1 제외가 P+0 전체(어휘 1+2단계)를 게이트 (v1 동일). (4) 다중 지문(41~42 합본) 원고 코퍼스 부재 — q_num_end 경로는 파서 재사용으로 커버되나 실기 미검증.
