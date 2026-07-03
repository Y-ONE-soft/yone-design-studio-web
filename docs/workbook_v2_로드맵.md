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
