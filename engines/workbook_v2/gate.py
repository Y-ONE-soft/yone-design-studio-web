"""워크북 v2 완제품 검수 게이트 (W11 — job 06f4b2c2 결함 6건의 자동 검출).

기준은 '조판사가 납품하는 완제품'이다 — 파싱 결과가 아니라 출력물 자체를
검사한다 (파서가 틀리면 게이트도 같이 틀리는 순환 금지):
  G1 [헤더잔존]   지문번호 헤더 원문이 출력 본문에 인쇄됨 (critical)
  G2 [정답잔존]   '정답' 블록/정답표 행이 출력에 인쇄됨 (critical)
  G3 [지문번호]   독립 지문번호 프레임이 원고 지문번호와 불일치
                  (passage_numbers op 사용 시 critical, 아니면 warning)
  G4 [잔여페이지] 원고에 없는 스텝/남는 사이클 페이지 잔존
                  (page_cleanup op 사용 시 critical, 아니면 warning)
  G5 [상하반전]   step2_a1(상단)과 step2_a1_btm(하단)의 기하 배치 반전
                  (step_map pos 힌트 사용 시 critical, 아니면 warning)
  G6 [헤더미인식] 원고(콘텐츠 단락)에 구조적 헤더 후보가 있는데 인식기가
                  하나도 못 잡음 — 파싱 계층 경고 (순환 측정 방지)
  G7 [빈플랜]     렌더 유닛이 0 — 업로드 원고가 어느 스텝에도 매핑되지
                  않았는데 조판이 '성공'으로 끝나는 침묵 유실 (critical, W12)
  G8 [구분선잔존] 원전 교재의 챕터/유닛 구분선("Chapter 03. ..." /
                  "Unit 10 긴 어구 빈칸")이 출력 본문에 인쇄됨 (critical, W12)
  G9 [미사용원고] 업로드/원고 폴더의 원고 파일이 어느 스텝에도 소비되지
                  않고 조용히 무시됨 (W13 c15 실증: "…STEP 2_박소원
                  완료.hwpx" 통합 원고 3종 침묵 무시). 정답/답지/해설
                  파일과 '정답지 짝' 파일은 의도된 미사용이라 stats로만
                  보고, 그 외는 warning (G7 전량 유실의 부분 유실 보완).
  G10 [특수문자]  hwp 사용자 영역(PUA) 문자가 출력에 인쇄됨 — InDesign
                  폰트에 글리프가 없어 tofu(빈 네모)로 찍힌다 (W14 c05/c06
                  실증: 요약 화살표 ⇩가 /\U000f0036으로 인코딩).
                  PUA 단독 단락은 critical, 본문 내 혼입은 warning.
  G10 확장 (W20): 인쇄 매핑 테이블(plan.PUA_PRINT_TABLE — 겹따옴표
                  U+F0852/F0853, 요약 화살표 U+F0036/F003B/F0EA) 등재
                  코드가 본문 혼입으로 잔존하면 critical — 현행 플랜은
                  이 코드들을 정자로 치환하므로 잔존 = 매핑 미적용
                  출력(구출력 소급 검출: c06 W14 최종 출력의 U+F0852/
                  F0853 혼입 2건). 미등재 코드 혼입은 warning 유지
                  (근거 없는 치환 금지 — U+F09F/F000/F081~F085 잠복).
  G11 [마커오염/마커스타일] 변형문제 출처 마커("[NHN_..._변형]")에 원문자
                  접두가 붙어 인쇄(파서 선지 오염) 또는 같은 마커가 복수
                  스타일로 인쇄(kind 오분류 — 발문/선지 스타일로 찍힘).
                  둘 다 critical (W15 c04 실증: 183개 중 9개 비일관 + 오염 1).
  G12 [문장삽입배경] 출처 마커가 있는 스토리에서 문장삽입 발문 뒤 배경
                  (주어진 문장 박스) 미부여 — warning (W15 c04 실증 12건).
  G13 [발문스타일] 발문 시그니처 단락([서술형 N] 접두 태그, 또는 발문
                  시작 신호 + 시오/세요-체 종결)이 발문 계열 스타일이
                  아닌 스타일로 인쇄됨 — critical (W16 c07 실증:
                  "[서술형 2] … 쓰세요." 해요체 발문이 지문 스타일).
  G14 [영단어오분류] 영단어 스타일 단락이 실제 어휘 항목("word: 한글 뜻")
                  이 아님 — 한글 뜻이 없거나 콜론 앞 머리가 1글자(대화문
                  화자 라벨 "A:"/"Minji:") — critical (W16 c10 실증 6건 +
                  c04/80dd3fa2 잠복. v1 실물: 이런 행은 전부 지문 스타일).
  G15 [조건항목]  <조건> 블록 안의 강신호 조건 항목(불릿 시작 또는
                  한글 + '것' 종결, 답란 이전)이 조건 스타일이 아닌
                  스타일로 인쇄됨 — critical (W16 c10 실증 3블록 +
                  c04/c05/0a5da924 잠복).
  G15 확장 (W38): 블록 문맥 우선 계약 — 조건 블록 안의 번호/불릿 항목은
                  종결어미(시오-체) 무관 조건 항목이다 (사용자 확정,
                  W16 D3 "시오-체 번호 항목 발문 유지" 폐기. 6b66b750
                  "1) 9단어로 빈칸을 완성하시오."가 발문 스타일+자동
                  번호로 인쇄된 실증). 진짜 발문(발문 어휘 선두 또는
                  번호 시퀀스 이탈)만 블록 종료로 인정.
  G16 [스텝원고미사용] 미사용 원고(G9 suspicious) 중 파일명 콘텐츠 토큰이
                  현행 스텝이 소화 가능한 종류(문장배열/영작배열/실전문제
                  등)인 파일 — 부분 침묵 유실의 강신호라 critical 승격
                  (W17 c11 실증: 구6스텝 폴더의 Step4 빈칸내용/Step5
                  영작배열/Step6 실전문제 3종 침묵 미사용). 대응 스텝이
                  없는 종류(교과서 계열의 어법수정 등)는 G9 warning 유지.
  G17 [워터마크잔존] 원고 선두의 학원 워터마크(URL 단독 라인, 무단도용/
                  무단전재/불법복제 경고 라인)가 출력에 인쇄됨 — critical
                  (W17 c16 실증: cafe.naver URL + "※ 본 자료는 무단도용
                  … 금합니다"가 지문 스타일로 인쇄).
  G18 [유형마커스타일] 문제 유형 구분 마커("[ Type A ]"류 단독 대괄호
                  라인)가 복수 스타일로 인쇄됨 — kind 오분류 (W17 c16
                  실증: [ Type C (2) ]만 Box 전파로 보기 스타일). critical.
  G19 [어법수정혼입] step3(실전문제) 스토리에 어법수정 원고 시그니처
                  (N[영단어] 괄호 표기)가 다량 인쇄됨 — 구6스텝
                  'Step3 어법수정' 파일명이 실전문제로 오라우팅된 상태
                  (W17 c11 실증: 6지문 45개 표기). critical.
  G20 [선두잔재]  스토리 선두 콘텐츠 단락이 날짜-only 라인("17. 11. 23") —
                  원고 표제 블록의 작업 날짜 메모가 표제 제거를 비껴가
                  본문 첫 단락으로 인쇄됨 (W18 c18 실증: 문항 번호 보호
                  규칙(숫자+점 시작)이 날짜를 문항 번호로 오인 보호). critical.
  G13 확장 (W18): 발문 시작 신호가 없어도 꼬리 [출처/태그] + 시오/세요-체
                  종결이면 발문 시그니처 ("영어로 번역하세요 [9강 1번]"이
                  지문 스타일로 인쇄된 c18 실증 + 세로 e79f8af9 기출력의
                  "11. (주관식) … 고르세요. [정답 2개]" 잠복 검출).
  G13 확장 (W38): 영어 지시문 발문 시그니처 — 문항 번호 + 명령형 동사
                  (Choose/Select/Write/…) 또는 번호 + WH-의문 … ? 가
                  발문 계열 스타일이 아니면 검출 ("10. Choose True or
                  False (T/F) …"가 지문 스타일로 인쇄된 6b66b750 실증.
                  정상 출력은 Q 스타일 + 번호 제거라 번호 접두 자체가
                  결함 서명이다).
  G32 [요약문배경] [요약문] 마커와 그 다음 문장 단락이 배경 스타일이
                  아님 — 마커+요약 문장 = 배경 처리(사용자 확정 스펙,
                  6b66b750 실증 9블록). 현행 플랜(마커를 배경으로 실은
                  플랜)은 critical, 구출력은 warning 소급.
  G33 [라벨프레임기하] 지문번호 라벨(비숫자 — 본문N/추가본문) 단일 프레임의
                  좌/우 페이지 기하 대조 — 오른쪽 프레임 크기가 같은
                  높이 계열의 왼쪽 프레임과 0.3mm 초과로 다르면 검출
                  (템플릿 유래 좌우 불일치: 6b66b750 실측 빈칸어휘/
                  빈칸어법 L 폭 8.9 vs R 7.72. 실행기 좌우 통일이 계약 —
                  delete 모드 critical, 아니면 warning. fb 있는 신형
                  덤프 한정).
  G21 [원문자중복] ①로 시작하면서 본문에 ①이 다시 등장하는 장문(200자+)
                  단락 — 선지 자동번호가 inline 번호 지문(도표/불일치류:
                  선지가 지문 문장에 ①~⑤로 박힘)에 원고에 없는 ①을
                  prepend해 기형 번호('①The graph … ① In Germany …')가
                  인쇄된 오염 (W19 c20 실증: ※ 다중 문항 아이템의 재인쇄
                  지문 + passage_above 우회 경로. 원고에 타이핑된 inline
                  번호 지문은 ①이 1회뿐이라 통과 — c19/0a5da924 실측).
                  critical.
  G22 [간지라벨] 간지의 '고N 모의고사 / YY년 M월' 라벨이 원고(content의
                  grade/year/month)와 불일치 — v1 run.jsx 16.7이 간지를
                  갱신하는데 v2 본가는 divider op 미적용이라 [원본] 템플릿
                  잔재('고2 모의고사 / 26년 3월')가 그대로 납품됐다
                  (W19 c20 실증 + c04/c05/c12/c14/06f4b2c2/세로 계열 등
                  소급 검출 — c05는 고1 25년 10월 책에 고2 26년 3월 간지).
                  '…월 짤지문' 단독 라벨은 v1도 미갱신(실물 잔존)이라 제외.
                  content에 grade/year/month가 없으면 검사 생략.
                  divider op 사용 플랜은 critical, 미사용은 warning
                  (G3/G4 패턴). 세로 실행기도 W20에서 divider op 지원
                  (라벨 내용 정확 매칭 방식 — c17 소급 해소).

  G23 [라벨스타일] 지문번호 라벨 단락([N]/{N})의 인쇄 스타일이 계약
                  (step_map.json label_contract — 플랜 flow.target에 실림)과
                  불일치 — critical (W21 r11 실증: v2가 [N]에 'A_어휘 선택
                  번호'를 입혔으나 v1 실물(워크북03(외부지문))은 [기본 단락]).
  G24 [프레임브레이크] ① 지문 다수 원고가 유닛 1개로 배치(per_passage_units
                  계약 스텝 — 헤더 미인식으로 프레임 분리가 통째로 실패한
                  상태. W21 r11 실증: '1. no.1' 무-p형 헤더 4스텝) ② 유닛
                  시작 단락이 실제 프레임 경계에 있지 않음 (덤프 fc 필드
                  실측 — 신형 덤프 한정). 둘 다 critical.
  G25 [발문빈단락] 발문(하단 문제 스타일) 바로 다음이 빈 단락 — 발문과
                  주어진 문장 사이 불필요한 빈 줄 (W21 r11 실증: C1 발문
                  삽입이 원고 잔여 빈 단락 위에 얹힘. v1 실물은 발문 바로
                  다음이 주어진 문장). critical.
  G26 [섹션마스터] 섹션 시작 페이지의 마스터가 좌/우 변형 계약(step_map
                  master_pair)과 불일치 — 페이지 정리로 시작이 밀렸는데
                  마스터가 그대로 (W21 r11 실증: [원본]워크북_C p13 어휘
                  선택 2 = 우측 시작 B-마스터). section_masters op 사용
                  플랜은 critical, 아니면 warning. 덤프 pages 필드 필요.
  G27 [간지적합] W22 r12 스펙 확정 (사용자 확정 — supp 계열): 간지는
                  업로드 시 입력한 간지 문구, 미입력이면 교재유형만 표기
                  (예: '외부지문'). plan.divider.source(user|type) 계약이
                  있으면 모의고사 라벨 잔재/기대 문구 불일치 = critical.
                  계약 없는 플랜(본가/구출력)은 기존 W21 warning 유지:
                  외부지문(무-p형 'N. no.M') 원고 + '모의고사' 라벨 →
                  사람 확인 지목 (v1 실물도 같은 라벨 유지 관행).
  G4 확장 (W22 r12): 반복 장식(페이지마다 얹히는 발문/섹션 탭)만 남은
                  장식-빈 페이지를 delete 모드 잔여로 합산 — 장식 텍스트가
                  '텍스트 있음'으로 빈 페이지 판정을 비껴가 잔존 (r11
                  재조판 p34 어법선택 발문 / p47 영작배열 탭, 사용자 지목).
  G28 [파트경계] 간지 라벨 페이지가 물리 왼쪽(L) — 페이지 삭제로 파트
                  경계 정렬이 깨졌는데 오른쪽 채움(M 마스터) 페이지 누락.
                  delete 모드의 M 페이지는 간지 직전 오른쪽 채움만 허용
                  (그 외 M 페이지 = 빈 페이지 잔재). delete 모드 critical,
                  아니면 warning (W22 r12 — 사용자 확정 스펙: 파트 경계
                  오른쪽 채움 페이지는 삭제가 아니라 M 마스터 삽입).

  G27 확장 (W23 r13 F1): supp 계약(plan.divider.source)에서 '모의고사'는
                  어떤 경우에도 자동(type)으로 나가면 안 된다 — 유형 판정
                  실패의 메타 기본값 추락이면 중립 '부교재'가 계약 (job
                  6c1430c3 실증: '[N과 추가지문]' 원고 간지가 '모의고사'로
                  인쇄). source=type + line1='모의고사' = critical.
  G28③ 고아 간지 (W23 r13 F2): 간지 라벨 뒤에 다음 간지/문서 끝까지 플로우
                  콘텐츠 페이지가 없으면 사용되지 않는 섹션의 간지 잔재 —
                  delete 모드 critical (스프레드 삭제가 실행기 계약), 아니면
                  warning (6c1430c3 실증: 짤지문 간지 p34~35 잔존 — 라벨
                  페이지에 섹션 마스터(O)가 적용돼 기존 간지 판정을 전부
                  비껴갔다).
  G29 [글리프커버리지] (W23 r13 F3): ① 아래첨자 인쇄 매핑(SUBSCRIPT_
                  PRINT_TABLE) 등재 문자 잔존 = critical (치환 미적용 출력
                  소급 — G10 확장 패턴), ② 스타일 적용 폰트의 cmap 실측
                  (core.fontcov)으로 글리프 미지원 문자 warning 지목 —
                  PUA(G10)와 별개의 '폰트 커버리지' 부류.
  G30 [문제단위킵] (W23 r13 F4): 한 문제(발문+지문+선지)가 오른쪽 페이지
                  에서 잘려 다음 장으로 이어짐 — question_keep 계약 플랜은
                  critical, 구출력은 warning 소급 지목. 스프레드 초과
                  문제(밀기로 해소 불가)는 warning.
  G27 확장 (W24 r14): 간지는 line1(교재유형)+line2(디테일 범위) 두 줄
                  분리 입력 (둘 다 선택 — 사용자 확정 스펙). 자동 판정
                  ('N과 추가지문' 감지 포함) 표기는 '외부지문'으로 통일 —
                  source=type + line1='추가지문'은 구 판정 사다리(r13 ③)
                  잔존 플랜 = critical.
  G1 확장 (W30-r15): 교과서 실전문제 출처 라인("공통영어2_YBM(김) 1과_03")
                  잔존 = critical — 플랜(build_step3)이 제거 (376b34d0
                  실증 25건: kind UNKNOWN → 지문 스타일 인쇄).
  G24①b (W30-r15): step1_c1 {헤더} 마커 수 < 지문 라벨 수 — 부분 미인식
                  지문이 앞 블록에 흡수된 상태 (376b34d0 실증: 'N. L1-
                  추가본문' 미정규화 → 유닛 10개라 ①을 비껴감).
                  per_passage_units 계약 스텝 한정, critical.
  G28④ 크레딧 (W30-r15, W38 정정 — 사용자 확정 스펙): 크레딧(판권)
                  페이지는 항상 왼쪽 + **문서의 마지막 페이지** — 책은
                  오른쪽에서 시작해 왼쪽(크레딧)에서 끝난다. W30의
                  "크레딧 뒤 오른쪽 메모(M) 추가"는 잘못된 스펙으로
                  폐기 (크레딧 뒤 잔여 페이지 = 위반). 크레딧 식별 =
                  문서 말미 비-M 페이지가 마스터 없음+텍스트 프레임 0
                  (전 코퍼스 sweep 실측 셰이프). delete 모드 critical
                  (실행기 alignCreditPage 계약), 구출력 warning.
  G31 [프레임결손] (W30-r15): 다단(모드 2+) 스토리의 중간 페이지 프레임
                  결손 — expandStoryOverflow가 마지막 프레임 1개만 복제해
                  2단 템플릿 페이지를 1단으로 만든 결함 (376b34d0 실증
                  p95~97). question_keep/delete 계약 플랜 critical.

  G38 [순서선지] (W40 결함 3): 순서배열 선지 순열 행("(A) － (C) － (B)")
                  이 원문자 없이 인쇄되거나 선지 스타일이 아님 — hwpx
                  2열 표(번호 셀|순열 셀)의 번호 셀이 정답 제거에 오인
                  삭제된 결함 (0a5da924 실증 90행). 현행 플랜(원문자+선지
                  순열 행이 실림)은 critical, 구출력 소급 warning.
  G39 [지문배경] (W40 결함 4): 네모/괄호 낱말·어법 선택형 발문 직후의
                  재인쇄 지문에 배경 스타일 오적용 — 지문은 지문 스타일
                  (215번 실증: 판정 2의 P_ORDER_LABEL 휴리스틱이 "(A)\t
                  (B)\t(C)" 선지 헤더를 순서배열 항목으로 오인). 현행
                  플랜은 critical, 구출력 소급 warning.
  G40 [괄호답란] (W40 결함 5): 보기/조건 블록 뒤 괄호 라벨 답란("(A)
                  ______")이 답란 계열(선지) 스타일이 아님 — W39 콜론형
                  (G35)의 괄호 라벨형 확장 (0a5da924 실증: <보기 B> 아래
                  답란이 Box 전파에 삼켜져 보기 스타일). 현행 플랜은
                  critical, 구출력 소급 warning.
  G41 [발문고아] (W40 결함 2): 프레임 하단에 발문만 남고 문제 본문이
                  다음 프레임에서 시작 — question_keep의 프레임판 (W23
                  스프레드 킵의 프레임 층. 0a5da924 실증: "다음 글에서
                  전체 흐름과 관계 없는 문장은?" 발문 단독 잔류). fc
                  실측 대조 — stem_keep 계약 플랜은 critical, 구출력
                  소급 warning. 발문+본문 1줄 케이스는 실행기
                  enforceStemKeep이 담당 (라인 정보는 덤프에 없음).
  G42 [선지열정렬] (W40 결함 1): 다열 선지 그룹("(A)(B)(C)" 헤더 +
                  "①x\ty\tz" 행)의 탭 셀 시작 오프셋이 행 간 불일치 —
                  덤프 W40 확장 필드 cx 실측 (±0.3mm). v1 실물 관행은
                  기본 12.7mm 탭 그리드 정렬 (배재2_워크북01 실측) —
                  실행기 applyChoiceTabs가 명시 탭스톱으로 재현.
                  choice_tabs 계약 플랜은 critical, 구덤프는 생략.
  G43 [빈칸경계] (W40 결함 6): 밑줄 빈칸 런 라인이 프레임 오른쪽 내변
                  초과 — 덤프 W40 확장 필드 hox 실측. 실행기 blank_fit이
                  자간(한도 -50)으로 수용하고, 한도 초과 잔존은 warning
                  지목 (과도 축소 금지 — 사용자 확정 스펙).
  G44 [답란스타일] (W45): 답란(콜론형 G35 / 괄호형 G40)은 답란 전용
                  스타일 `S_답란`(지문 스타일 복제 + 들여쓰기 0)으로
                  인쇄한다 — 사용자 확정 스펙. 완성본 다수가 답란을 지문
                  스타일로 갖고 있던 건 의도가 아니라 회피였다(선지
                  들여쓰기 때문에 손으로 바꿈 — 역학습 W44 61건/13문서).
                  fail-open: 템플릿에 S_답란이 없으면 선지 폴백 + 들여쓰기
                  0 로컬 오버라이드 브릿지 → warning. 있는데 미적용이면
                  critical.

G4/G5는 dump_stories.jsx의 W11 확장 필드(stale_pages / pg / b)가 필요하다.
G24②/G26은 W21 확장 필드(fc / pages)가 필요하다. G29②는 W23 확장 필드
(fonts / style_fonts), G30은 W23 확장 필드(fp — 프레임별 페이지, fc 병렬)가
필요하다. 구버전 덤프에는 경고로만 보고한다 (재덤프 안내). G9는 uploads_dir를
넘긴 경우에만 검사한다 (오프라인 플랜 테스트 호환).
"""
import os
import re
import unicodedata

from core.inspect import find_leaked_answers
from core.structure.header_detect import detect_headers
from engines.workbook_v2.plan import (GLYPH_PRINT_TABLE, PUA_PRINT_TABLE,
                                      SUBSCRIPT_PRINT_TABLE,
                                      is_header_line, is_a1_header,
                                      passage_labels, _norm_header)

# G44 (W45) — 답란 전용 단락스타일 이름 (그룹 안 마지막 토큰). 템플릿 생성은
# scripts/add_ansline_style.py, 매핑은 core/structure/style_map.json.
ANSLINE_STYLE_NAME = "S_답란"

_RE_BARE_NUM = re.compile(r"^\d{1,3}(?:\s*~\s*\d{1,3})?$")
# G21 — 원문자 선지 번호 (①~⑮: 지문 inline 번호도 같은 집합)
_CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
# G22 — 모의고사 간지 라벨 ('고N 모의고사' + 'YY년 M월' 연속 2단락)
_RE_DIVIDER_L1 = re.compile(r"^고(\d)\s*모의고사$")
_RE_DIVIDER_L2 = re.compile(r"^(\d{2})년\s*0?(\d{1,2})월$")
_RE_DIGIT = re.compile(r"\d")
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")

# G11 — 변형문제 출처 마커 (출력 검사용 독립 정의 — 파서/플랜과 순환 방지)
_RE_SRC_MARKER = re.compile(r"^\[[^\[\]]{2,}변형\]$")
# G1 확장 (W30-r15) — 교과서 실전문제 출처 라인 ("공통영어2_YBM(김) 1과_03"
# / "… 1과_01~02" — 밑줄 포함 과목_출판사 토큰 + 'N과_NN[~NN]' 전체 라인.
# 출력 검사용 독립 정의 — plan._RE_S3_TEXTBOOK_SRC와 순환 방지)
_RE_S3_SRC_LINE = re.compile(
    r"^\S+_\S+\s+\d+과_(?:\d+(?:\s*~\s*\d+)?|[\w가-힣]{1,12})$")
_RE_SRC_POLLUTED = re.compile(r"^[①-⑤]\[[^\[\]]{2,}변형\]$")
# G45 (W66) — 원고 편집용 대괄호 인덱스 (출력 검사용 독립 정의).
# 보존 계약: 내용 마커/기출 출처/배점·유형 태그/문장은 인쇄된다.
_RE_G45_LABEL = re.compile(r"^\[([^\[\]]{1,60})\]$")
_RE_G45_KEEP = re.compile(
    r"변형|수능특강|수능완성|수능|모의고사|학력평가|학평|모평|교육청|평가원|"
    r"기출|\d{2}\s*년\s*\d{1,2}\s*월|\d{6}\s*[A-Za-z]\s*\d")
_RE_G45_SENT = re.compile(r"[.?!。？]\s*$|시오|세요|십시오|합니다|입니다")
_RE_G45_TAG = re.compile(
    r"^\d+\s*점$|^(?:서술형|논술형|단답형|주관식|객관식)\s*\d*$|"
    r"^(?:보기|조건|요약문?|정답|해답|답|해설|해석)\s*[A-Za-z0-9]{0,2}$")
# G12 — 문장삽입 발문 (주어진 문장 배경 박스 기대)
_RE_INSERT_PROMPT = re.compile(r"주어진 문장이 들어가|들어갈 위치|"
                               r"들어가기에 가장 적절한 곳")

# G13 — 발문 시그니처 (출력 검사용 독립 정의 — 플랜 오버레이와 순환 방지)
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_Q_LEAD_TAG = re.compile(r"^\[(?:서술|논술)형\s*\d*\]")
_RE_Q_TRAIL_SRC = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
_RE_Q_START = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의\s*흐름|주어진)")
_RE_Q_END = re.compile(r"(?:시오|세요)\s*[.?!]?\s*$")
# 발문 계열 스타일 시그니처 — "실전 문제 지문"(지문 스타일)과 충돌하지
# 않도록 "하단 문제"/"OX문제"처럼 구체 명칭으로 한정
_Q_STYLE_KEYS = ("번호", "발문", "다음 글을 읽고", "하단 문제", "OX문제")

# G14 — 영단어 스타일 오용 (실제 어휘 항목은 "word: 한글 뜻" — 한글 필수,
# 콜론 앞 머리 2+글자. 1글자 머리는 대화문 화자 라벨 "A:")
_RE_WORD_BAD_HEAD = re.compile(r"^[A-Za-z]\s*[:：]")

# G15 — <조건> 블록 항목 (v1 실물 관행: 영어 어구 나열은 지문 유지.
# W38: "시오-체 번호 항목은 발문 유지" 관행 폐기 — 블록 문맥 우선,
# 번호/불릿 항목은 종결어미 무관 조건 항목. 진짜 발문은 발문 어휘 선두
# (번호 + 다음/아래/위/윗+글·문장류)나 번호 시퀀스 이탈로만 인정)
_RE_COND_BULLET = re.compile(r"^\s*[•⦁◦∙ㆍ·]")
_RE_COND_GEOT = re.compile(r"것\s*\.?\s*$")
_RE_COND_NUMSTART = re.compile(r"^\s*(\d{1,2})\s*([.)])")
# 답란 = 밑줄런으로 '끝나는' 줄 한정 — 본문 중간 빈칸 표기("보기의
# [_______]에서 … 할 것"은 조건 항목)와 구분 (c06 실증)
_RE_COND_BLOCK_END = re.compile(r"_{6,}\s*[.,)]?\s*$|^\s*(?:정답|→|우리말)")
_RE_COND_QHINT = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의|밑줄|주어진|"
                            r"\(주관식\)|서술형)")
# W38: 번호 뒤 발문 어휘 선두 (블록 종료 신호 — block_grammar.QUESTION_LEAD
# 준용, 출력 검사용 독립 정의)
_RE_COND_QLEAD = re.compile(
    r"^\s*\d{1,3}\s*\.\s*(?:(?:다음|아래|위|윗)\s*(?:글|문장|시|중|대화|"
    r"도표|물음|빈칸|단어)|윗\s*글|글의|밑줄\s*친|주어진|\(주관식\)|"
    r"\(서술형\)|서술형)")

# G34 (W39) — 조건 블록 안 단어 나열 (슬래시 구분 또는 쉼표 3+ 나열,
# 완결부호 없는 라인 한정 — 출력 검사용 독립 정의)
_RE_G34_WORDLIST = re.compile(
    r"^(?!.*[.!?][\"'’”)\]]?\s*$)"
    r".*(?:\S\s*/\s*\S|(?:,[^,]*){3,})")

# G35 (W39 결함 4) — 답란 쌍: "라벨:"(콜론 단독) + 밑줄 빈칸 라인은 답란
# 계열(선지/답) 스타일이어야 한다 (실물 v1 콜론형 답란 = S_선지 실측)
_RE_G35_LABEL = re.compile(r"^[\s가-힣A-Za-z()（）]{1,12}[:：]$")
_RE_G35_BLANK = re.compile(r"^[^_]{0,15}_{3,}[\s_]*[.,]?$")

# G36 (W39 결함 5) — 진위 선택 문항의 "N) 문장 (T/F)" 행 = 선지
# (출력 검사용 독립 정의)
_RE_G36_TFREF = re.compile(
    r"True\s+or\s+False|\(\s*T\s*/\s*F\s*\)|\(\s*O\s*/\s*X\s*\)", re.I)
_RE_G36_TFROW = re.compile(
    r"^\s*\d{1,2}\s*\)\s*.+\(\s*(?:T\s*/\s*F|O\s*/\s*X|True\s*/\s*False)"
    r"\s*\)\s*\.?\s*$", re.I)

# G37 (W39 결함 6) — 발문의 "밑줄 친 <영어구>" 인용은 밑줄 렌더 (플랜
# runs 검사 — 덤프에는 문자 서식이 없어 플랜 계층에서 검증. 독립 정의)
_RE_G37_QUOTE = re.compile(r"밑줄\s*친\s+([^가-힣]+)")

# G38 (W40 결함 3) — 순서배열 선지 순열 행("(A) － (C) － (B)")은 원문자
# 접두 + 선지 스타일이어야 한다 (출력 검사용 독립 정의 — 0a5da924 실증:
# hwpx 2열 표의 번호 셀이 정답 제거에 오인 삭제돼 번호 없이 지문 스타일로
# 인쇄. 세 라벨이 서로 다른 순열일 때만 매치 — 지문의 "(A) 문장" 배제).
_RE_G38_PERM_BARE = re.compile(
    r"^\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)$")
_RE_G38_PERM_NUMBERED = re.compile(
    r"^[①②③④⑤]\s*\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)"
    r"\s*[-–—−－]\s*\(([ABC])\)$")

# G39 (W40 결함 4) — 네모/괄호 낱말·어법 선택형 발문 직후의 재인쇄
# 지문은 배경 스타일이 아니다 (지문이다 — 215번 실증: 판정 2 오배정).
# 발문 시그니처: (A) 라벨 + 네모/괄호/[ ] 토큰 + '에서' + 낱말/표현 계열.
_RE_G39_TOKEN = re.compile(r"네모|괄호|\[\s*\]")
_RE_G39_SUBJECT = re.compile(r"낱말|표현|어법|문맥")

# G40 (W40 결함 5) — 보기/조건 블록 뒤 괄호 라벨 답란("(A) ______" /
# "(A) : ______")은 답란 계열(선지) 스타일이어야 한다 (출력 검사용 독립
# 정의 — 0a5da924 실증: <보기 B> 아래 답란이 보기 스타일로 인쇄).
_RE_G40_PAREN_BLANK = re.compile(
    r"^[(（]\s*[A-Za-z가-힣0-9]{1,3}\s*[)）]\s*[:：]?\s*_{3,}[\s_]*[.,]?$")

# G13/G32 (W38) — 영어 지시문 발문 시그니처 + 요약문 마커 (출력 검사용
# 독립 정의 — block_grammar와 순환 방지)
# 명령형만 — WH-의문형("N. Why don't we …?")은 외부지문 '지문 제목'과
# 텍스트만으론 구분 불가라 게이트에선 제외 (r11 외부지문 헤더 실측
# 반례: "7. Why don't we think different more often?"이 [기본 단락]으로
# 인쇄되는 게 정상. WH-발문은 분류기(step3 문항 문맥 한정)가 담당).
_RE_Q_EN_SIG = re.compile(
    r"^\d{1,3}\s*[.]\s*(?:Choose|Select|Write|Fill|Complete|Answer|Match"
    r"|Circle|Arrange|Rearrange|Translate|Find|Identify|Underline|Correct"
    r"|Rewrite|Summarize|Read\s+and)\b")
# W39 결함 1: 꺾쇠형(<요약문>/<요약>)도 배경 — 사용자 확정 (Box 관행 폐기)
# W50: CJK 꺾쇠(〈〉《》)·전각(＜＞)·모난 괄호(【】) 이형 포함 — 플랜/파서와
# 같은 정규화 폭 (이형 원고에서 G32가 동반 실명하던 것 봉합)
_RE_SUM_MARKER = re.compile(
    r"^\s*(?:[\[<〈《＜【]\s*요\s*약\s*문?\s*[\]>〉》＞】]|요약문)\s*$")

# G8 — 원전 교재 구분선 (파서 _RE_CHAPTER_DIVIDER/_RE_UNIT_DIVIDER 준용.
# 출력 검사용 독립 정의 — 파서가 틀리면 게이트도 같이 틀리는 순환 방지)
_DIVIDER_PATTERNS = [
    re.compile(r"^Chapter\s+\d+\.\s", re.I),
    re.compile(r"^Unit\s+\d+\s+[가-힣][가-힣0-9\s]{0,30}$"),
]

# G17 — 학원 워터마크 (W17 c16): URL '단독' 라인(본문 속 인용 URL과 구분)
# 또는 무단도용/무단전재 경고 문구 포함 라인. '불법복제'는 어휘 정의
# ("pirate : … 불법 복제하다" — 화이트북 실덤프 실증)와 충돌해 제외.
_RE_WATERMARK_URL = re.compile(r"^(?:https?://\S+|www\.\S+)$")
_RE_WATERMARK_WARN = re.compile(r"무단\s*도용|무단\s*전재")

# G18 — 문제 유형 구분 마커 (W17 c16): "[ Type A ]" / "[ Type C (1) ]" /
# "[ Type D (1) 어법 ]" 류 단독 대괄호 라인. 같은 가족 마커는 한 스타일로
# 일관 인쇄돼야 한다 (G11 SRC 마커의 유형 마커 확장).
_RE_TYPE_MARKER = re.compile(r"^\[\s*Type\b[^\[\]]{0,30}\]$", re.I)

# G19 — 어법수정 원고 시그니처 (W17 c11): "1[asked]" 정답 괄호 표기.
_RE_GRAMMAR_FIX_SIG = re.compile(r"\d\s*\[\s*[A-Za-z]")

# G20 — 스토리 선두 날짜-only 라인 (W18 c18): 원고 표제 블록의 작업 날짜
# 메모 ("17. 11. 23"). 본문 어디서나가 아니라 '스토리 첫 콘텐츠 단락'만
# 검사한다 (본문 속 날짜 표기 오탐 방지 — 양품 16종 sweep 0 확인).
_RE_LEAD_DATE = re.compile(r"^\d{2,4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?$")

# G2 — step3 말미 압축 정답표 행 (완제품 보존 관행 — W21 r11 v1 실물 실증)
_RE_ANSWER_KEY_ROW = re.compile(
    r"^\d{1,2}\s*\.\s*[①-⑤](?:\s+\d{1,2}\s*\.\s*[①-⑤])+")

# G23 — "$BASIC" 계약의 [기본 단락] 별칭 (실행기 basicParaOf 대응 +
# 플랜 문자열 그대로의 합성 덤프 호환)
_BASIC_ALIASES = {"[기본 단락]", "[Basic Paragraph]", "NormalParagraphStyle",
                  "$ID/NormalParagraphStyle", "$BASIC"}
# G25 — C1 자동 삽입 발문 텍스트 (B1의 '하단 문제_지문' 등 부분 일치 오탐
# 방지: 스타일 leaf 정확 일치 + 이 접두 텍스트만 검사)
_RE_C1_PROMPT_TEXT = re.compile(r"^아래 주어진 문장")
# G27 — 외부지문 무-p형 헤더 ("1. no.1")
_RE_NOP_HEADER = re.compile(r"^\s*\d+\s*[.)]\s*no\.?\s*\d+(?:~\d+)?\s*$",
                            re.I)

# G16 — 현행 스텝이 소화 가능한 콘텐츠 토큰 (파일명 정규화 기준 —
# _norm_fname: 공백 제거 + 소문자). EBS 계열은 어법수정도 스텝 원고
# (file_map step2_a1)라 토큰에 추가된다.
_STEP_CONTENT_TOKENS = ("어휘선택", "본문ox", "본문정리", "내용종합",
                        "문장배열", "빈칸어휘", "어휘완성", "빈칸내용",
                        "어법선택", "어법ox", "빈칸어법", "영작배열",
                        "낱말배열", "실전문제")
_STEP_CONTENT_TOKENS_EBS = _STEP_CONTENT_TOKENS + ("어법수정",)


# G10 — hwp 사용자 영역(PUA) 문자 (BMP U+E000~F8FF + plane 15/16).
# InDesign 본문 폰트에 글리프가 없어 tofu로 인쇄된다. ￼(U+FFFC 앵커)는
# PUA가 아니므로 무관.
def _is_pua(ch):
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


# W23 F3 — 플랜↔덤프 대조용 아래첨자 정규화: 플랜이 ₂→2(+sub run)로
# 치환하므로 구출력(₂ 그대로)과 신플랜(2)의 텍스트 매칭이 어긋난다.
# _clean에서 양쪽을 ASCII 숫자로 통일 (G29의 잔존 검출은 원문 p["t"]를
# 직접 스캔하므로 이 정규화와 무관). W30 후속 — 글리프 인쇄 매핑(❮❯→〈〉)
# 도 동일 이유로 정규화에 합류 (구출력 ❮ ↔ 신플랜 〈 매칭 유지).
_SUB_NORM_TABLE = str.maketrans({**SUBSCRIPT_PRINT_TABLE,
                                 **GLYPH_PRINT_TABLE})


def _clean(t):
    """덤프 단락 텍스트 정규화 — 앵커(￼)/개행 제거 + 공백 정리."""
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("￼", "").translate(_SUB_NORM_TABLE)
    return _norm_header(t)


def _dump_paras(dump):
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            yield p.get("t", ""), p.get("s", "")


def _flow_probe_text(flow):
    """플로우에서 가장 긴 단락 텍스트 — 덤프 스토리 식별용 (충분히 고유)."""
    best = ""
    for u in flow.get("units", []):
        paras = u["paras"] if isinstance(u, dict) else u
        for p in paras:
            if len(p.get("t") or "") > len(best):
                best = p["t"]
    return best


def _find_story_with_text(dump, text):
    key = _clean(text)
    if not key:
        return None
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            if _clean(p.get("t", "")) == key:
                return story
    return None


def _find_flow_story(dump, flow, max_probe=40):
    """플로우 → 덤프 스토리 매칭 (W21 r11 — 다수 단락 스코어링).

    단일 최장 단락 매칭(_flow_probe_text)은 같은 지문을 재인쇄하는 step3
    스토리로 오매핑될 수 있다 (0e3108fd 실증: step1_a2 최장 단락이 step3
    실전문제 지문과 동일). 플로우 단락 여러 개의 포함 수로 스코어링하고,
    동률이면 단락 수가 적은(초집합이 아닌) 스토리를 고른다."""
    probes = []
    seen = set()
    for u in flow.get("units", []):
        for p in (u["paras"] if isinstance(u, dict) else u):
            tt = _clean(p.get("t") or "")
            if len(tt) >= 8 and tt not in seen:
                seen.add(tt)
                probes.append(tt)
        if len(probes) >= max_probe:
            break
    if not probes:
        return _find_story_with_text(dump, _flow_probe_text(flow))
    probe_set = set(probes[:max_probe])
    best = None
    best_key = (-1, 0)
    for story in dump.get("stories", []):
        texts = {_clean(p.get("t", "")) for p in story.get("paragraphs", [])}
        score = len(probe_set & texts)
        if score == 0:
            continue
        key = (score, -len(story.get("paragraphs", [])))
        if key > best_key:
            best_key = key
            best = story
    return best


def _is_struct_header_candidate(paras, i):
    """구조적 헤더 후보 — 형식 무관 판정 (parser._is_passage_marker_struct
    준용). 짧고 숫자 포함, 영단어 적고, 뒤에 긴 영어 본문이 따라옴."""
    text = (paras[i].get("text") or "").strip()
    if not text or len(text) > 40:
        return False
    if not _RE_DIGIT.search(text):
        return False
    if len(_RE_ENG_WORD.findall(text)) >= 4:
        return False
    j = i + 1
    while j < len(paras) and not (paras[j].get("text") or "").strip():
        j += 1
    if j >= len(paras):
        return False
    return len(_RE_ENG_WORD.findall(paras[j].get("text") or "")) >= 5


# 헤더 기반 스텝 (헤더 제거/정규화가 빌더 책임인 스텝)
_HEADER_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_c1")

# ── G9: 미사용 업로드 원고 (W13) ─────────────────────────────────────────────
_MS_EXTS = (".docx", ".hwp", ".hwpx")
_RE_ANSWERISH = re.compile(r"정답|답지|답안|해설|answer", re.I)
_RE_S3_NUMFILE = re.compile(r"\d+(?:\s*~\s*\d+)?\s*번\s*\.(?:hwpx?|docx)",
                            re.I)
_RE_VARIANT = re.compile(r"변형\s*문제")


def _norm_fname(name):
    return unicodedata.normalize(
        "NFC", os.path.splitext(name)[0]).replace(" ", "").lower()


def find_unused_uploads(content, uploads_dir):
    """(expected_unused, suspicious) — 스텝에 소비되지 않은 원고 파일 분류.

    used 판정은 파서 소비 규칙의 근사 재현:
      - 루트: content steps의 filename (파서가 매칭·rename한 실명)
      - Step3 하위폴더: "N번" 파일(모의고사 번호 매칭), 변형문제 문제모음,
        교과서 경로(step3가 textbook 항목이면 비정답 후보 전부 소비)
    expected_unused = 정답/답지/해설 토큰 파일 + '정답지 짝' 파일(빈칸어휘
    스텝처럼 정답지 본이 소비되는 경우의 문제지 본) — 관행상 폴더에 늘
    존재하므로 stats로만 보고한다.
    """
    steps = (content.get("steps") or {}) if content else {}
    used = set()
    for sd in steps.values():
        if isinstance(sd, dict) and sd.get("filename"):
            used.add(_norm_fname(sd["filename"]))
    st3 = steps.get("step3") or {}
    st3_items = ((st3.get("normal") or []) + (st3.get("short") or [])
                 if isinstance(st3, dict) else [])
    st3_textbook = any(it.get("question_num") == "textbook"
                       for it in st3_items)
    st3_numbered = any(it.get("question_num") != "textbook"
                       for it in st3_items)

    # 전체 파일명 집합 (W21 r11): 업로드 슬롯 접두 사본("manuscripts_X")의
    # 원본 X가 라우팅으로 다른 하위 폴더(Step3/)에 스테이징된 경우도 중복
    # 사본으로 판정하기 위함 (0e3108fd 실측: "manuscripts_Step 3.hwpx"의
    # 원본 "Step 3.hwpx"가 Step3/로 라우팅돼 같은 폴더 존재 검사를 비껴감).
    all_names = set()
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            all_names.add(unicodedata.normalize("NFC", f))

    expected, suspicious = [], []
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        in_step3 = "step3" in unicodedata.normalize(
            "NFC", os.path.relpath(root, uploads_dir)).lower()
        for f in sorted(files):
            if f.startswith(".") or os.path.splitext(f)[1].lower() \
                    not in _MS_EXTS:
                continue
            nf = unicodedata.normalize("NFC", f)
            key = _norm_fname(nf)
            if key in used:
                continue
            # 업로드 슬롯 접두 사본("manuscripts_X")과 스테이징 사본(X)이
            # 같은 uploads 디렉터리에 공존 (W18 sero 실증: 26개 오탐) —
            # 접두 제거명이 소비됐거나 같은 폴더에 존재하면 중복 사본
            if nf.startswith("manuscripts_"):
                stripped = nf[len("manuscripts_"):]
                if (_norm_fname(stripped) in used
                        or stripped in all_names):
                    continue
            if in_step3:
                if st3_numbered and _RE_S3_NUMFILE.search(nf):
                    continue      # 모의고사 번호 매칭으로 소비
                if _RE_VARIANT.search(nf) and st3_items:
                    continue      # 변형문제 문제모음 (W12 라우팅)
                if (st3_textbook and not _RE_ANSWERISH.search(nf)):
                    continue      # 교과서 경로: 비정답 후보 전부 소비
            if _RE_ANSWERISH.search(nf) or any(u.startswith(key)
                                               for u in used):
                # 정답/답지류, 또는 소비된 변형본의 짝 파일 (예: 사용
                # "…빈칸어휘 정답지.docx"/"…영작배열(서술형).hwpx"의 짝
                # "…빈칸어휘.docx"/"…영작배열.docx") — 관행상 의도된 미사용
                expected.append(nf)
            else:
                suspicious.append(nf)
    return expected, suspicious


def inspect_workbook_finish(content, plan, dump, uploads_dir=None):
    """content(원고 파싱본) + plan + 출력 덤프 → 완제품 게이트 리포트."""
    critical = []
    warnings = []
    stats = {}
    plan = plan or {}
    steps = (content.get("steps") or {}) if content else {}

    strict_numbers = bool(plan.get("passage_numbers"))
    strict_pages = bool(plan.get("page_cleanup"))
    pos_used = any((fl.get("target") or {}).get("pos")
                   for fl in plan.get("flows", []))

    # ── G7 빈 플랜 — 업로드 원고가 렌더 유닛으로 전혀 이어지지 않음 ─────
    # (W12 실증: 변형문제 문제모음 hwp가 스텝 분류에 안 잡혀 조용히
    # 유실됐는데 verify ok=True로 끝나던 침묵 유실 차단)
    total_units = sum(len(fl.get("units") or [])
                     for fl in plan.get("flows", []))
    stats["plan_units"] = total_units
    if total_units == 0:
        critical.append("[빈플랜] 렌더 유닛 0 — 업로드 원고가 어느 스텝에도 "
                        "매핑되지 않음 (파일명/폴더 규칙 확인)")

    # ── G1 헤더 원문 잔존 + G8 구분선 잔존 ──────────────────────────────
    leaks = []
    divider_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if any(p.match(tt) for p in _DIVIDER_PATTERNS):
            divider_leaks.append(tt[:60])
            continue
        if not _RE_DIGIT.search(tt):
            continue
        if tt.startswith("{") or tt.startswith("["):
            continue    # {20}/{3과 추가지문}/[20] — 의도된 라벨 산출물
        if is_header_line(tt) or is_a1_header(tt):
            leaks.append(tt[:60])
    stats["header_leaks"] = len(leaks)
    if leaks:
        critical.append(f"[헤더잔존] {len(leaks)}개 단락이 지문번호 헤더 "
                        f"원문 그대로 인쇄됨: "
                        + " | ".join(sorted(set(leaks))[:5]))
    stats["divider_leaks"] = len(divider_leaks)
    if divider_leaks:
        critical.append(f"[구분선잔존] {len(divider_leaks)}개 단락이 원전 "
                        f"챕터/유닛 구분선 그대로 인쇄됨: "
                        + " | ".join(sorted(set(divider_leaks))[:5]))

    # ── G1 확장 (W30-r15): 교과서 실전문제 출처 라인 잔존 ────────────────
    # 꼼꼼변형 원고의 문항 말미 출처("공통영어2_YBM(김) 1과_03")가 지문
    # 스타일로 인쇄됨 (실서비스 376b34d0 실증 25건 — kind UNKNOWN 추락).
    # 완제품에 불필요 — 플랜(build_step3)이 제거하므로 잔존 = 미적용 출력.
    src_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if tt and _RE_S3_SRC_LINE.match(tt):
            src_leaks.append(tt[:60])
    stats["step3_source_leaks"] = len(src_leaks)
    if src_leaks:
        critical.append(f"[출처잔존] {len(src_leaks)}개 단락이 실전문제 "
                        f"출처 라인 그대로 인쇄됨: "
                        + " | ".join(sorted(set(src_leaks))[:5]))

    # ── G45 (W66): 원고 편집용 대괄호 인덱스 잔존 ────────────────────────
    # "[08강 - Exercise 05~06]" / "[Unit 17 - Practice 01~02]" / "[1]" 류.
    # 플랜(build_step3)이 구조 판정으로 제거하므로 출력 잔존 = 미적용.
    # 출력 검사용 독립 정의 (플랜과 순환 방지) — 보존 대상(내용 마커/기출
    # 출처/배점·유형 태그)은 같은 계약으로 면제한다.
    idx_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not _RE_G45_LABEL.match(tt):
            continue
        if _s in _BASIC_ALIASES or str(_s).rstrip().endswith("번호"):
            continue            # 엔진이 만든 지문번호 라벨([01]/[3과 추가
                                # 지문]) — G23 계약(기본 단락 또는 번호 스타일)
        inner = _RE_G45_LABEL.match(tt).group(1).strip()
        if not _RE_DIGIT.search(inner):
            continue            # 서수 없는 라벨은 인덱스로 보지 않는다
        if (_RE_G45_KEEP.search(inner) or _RE_G45_SENT.search(inner)
                or _RE_G45_TAG.match(inner)):
            continue
        idx_leaks.append(tt[:60])
    stats["step3_index_label_leaks"] = len(idx_leaks)
    if idx_leaks:
        critical.append(f"[인덱스잔존] {len(idx_leaks)}개 단락이 원고 "
                        f"편집용 대괄호 인덱스 그대로 인쇄됨: "
                        + " | ".join(sorted(set(idx_leaks))[:5]))

    # ── G46 (W66): 답표 헤더가 평문 두 줄로 잔존 ─────────────────────────
    # "틀린 부분"/"수정"은 원고 2열 표의 헤더 — 플랜이 표 op으로 바꾼다.
    # 평문 단락으로 남아 있으면 표 삽입이 안 된 것 (실행기 미적용).
    tbl_leaks = [
        _clean(t) for t, _s in _dump_paras(dump)
        if _clean(t) in ("틀린 부분", "틀린부분")]
    stats["answer_table_leaks"] = len(tbl_leaks)
    if tbl_leaks:
        critical.append(f"[답표미생성] 답표 헤더('틀린 부분')가 평문 "
                        f"단락으로 {len(tbl_leaks)}개 인쇄됨 — 표 삽입 "
                        f"미적용")

    # ── G2 정답 블록 잔존 ────────────────────────────────────────────────
    ans = find_leaked_answers(dump)
    # W21 r11: step3(문제 pool) 스토리의 압축 정답표 행("1. ①  2. ② …")은
    # 완제품 관행상 보존 — v1 실물(워크북03(외부지문) 스토리 53)도 실전문제
    # 지문 스타일로 유지한다 (문제책 말미 정답 모음). step3 플로우 스토리
    # 안의 해당 셰이프만 critical에서 제외하고 stats로 보고.
    st3_flow = next((fl for fl in plan.get("flows", [])
                     if fl.get("step") == "step3"), None)
    if ans and st3_flow:
        # 플랜에도 있는 행만 면제 (파서가 의도 보존한 정답 모음) — 파서가
        # 잘라야 했던 '정답' 마커 블록의 행(06f4b2c2)은 플랜에 없어 잔존
        # critical 유지. find_leaked_answers는 raw strip()[:60] — 동일 정규화.
        st3_plan_texts = {(p.get("t") or "").strip()[:60]
                          for u in st3_flow.get("units", [])
                          for p in (u["paras"] if isinstance(u, dict) else u)}
        st3_dump = _find_flow_story(dump, st3_flow)
        if st3_dump is not None:
            st3_texts = {(p.get("t") or "").strip()[:60]
                         for p in st3_dump.get("paragraphs", [])}
            kept = [a for a in ans
                    if _RE_ANSWER_KEY_ROW.match(a) and a in st3_texts
                    and a in st3_plan_texts]
            if kept:
                stats["answer_rows_step3_kept"] = len(kept)
                ans = [a for a in ans if a not in set(kept)]
    stats["answer_leaks"] = len(ans)
    if ans:
        critical.append(f"[정답잔존] {len(ans)}개 단락: "
                        + " | ".join(ans[:5]))

    # ── G10 hwp 사용자 영역(PUA) 문자 잔존 (W14, W20 확장) ───────────────
    pua_solo = []
    pua_inline = []
    pua_mapped = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not any(_is_pua(ch) for ch in tt):
            continue
        codes = sorted({f"U+{ord(ch):04X}" for ch in tt if _is_pua(ch)})
        if all(_is_pua(ch) or ch.isspace() for ch in tt):
            pua_solo.append(codes[0])
        elif any(_is_pua(ch) and ord(ch) in PUA_PRINT_TABLE for ch in tt):
            # W20 — 인쇄 매핑 등재 코드의 혼입 잔존은 critical (현행
            # 플랜은 치환하므로 잔존 = 매핑 미적용/구출력)
            pua_mapped.append(f"{codes[0]} ({tt[:30]})")
        else:
            pua_inline.append(f"{codes[0]} ({tt[:30]})")
    stats["pua_solo"] = len(pua_solo)
    stats["pua_inline"] = len(pua_inline)
    stats["pua_mapped_inline"] = len(pua_mapped)
    if pua_solo:
        critical.append(
            f"[특수문자] hwp 사용자 영역(PUA) 단독 단락 {len(pua_solo)}개 — "
            f"폰트 글리프 없음(tofu 인쇄): "
            + ", ".join(sorted(set(pua_solo))[:5]))
    if pua_mapped:
        critical.append(
            f"[특수문자] 인쇄 매핑 등재 PUA 코드가 본문에 잔존 "
            f"{len(pua_mapped)}개 단락 (플랜 매핑 미적용 출력): "
            + " | ".join(pua_mapped[:3]))
    if pua_inline:
        warnings.append(
            f"[특수문자] 본문 내 PUA 문자 혼입 {len(pua_inline)}개 단락: "
            + " | ".join(pua_inline[:3]))

    # ── G11 변형문제 출처 마커 인쇄 상태 (W15 c04) ───────────────────────
    # "[202506H2_18목적추론_변형]" 단독 단락은 관행상 지문 스타일로 일관
    # 인쇄된다 (v1 실물 고2 25-6 워크북 대조). ① 마커에 원문자 접두가 붙어
    # 인쇄 = 파서 선지 오염(원고에 없는 선지 번호), ② 같은 마커 셰이프가
    # 복수 스타일로 인쇄 = kind 오분류(발문/선지 스타일로 크게 찍힘) —
    # 둘 다 critical.
    src_styles = {}
    src_polluted = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if _RE_SRC_POLLUTED.match(tt):
            src_polluted.append(tt[:40])
            continue
        if _RE_SRC_MARKER.match(tt):
            src_styles.setdefault(s, []).append(tt)
    stats["src_markers"] = sum(len(v) for v in src_styles.values())
    stats["src_marker_styles"] = len(src_styles)
    stats["src_polluted"] = len(src_polluted)
    if src_polluted:
        critical.append(
            f"[마커오염] 출처 마커에 원고에 없는 원문자 접두 "
            f"{len(src_polluted)}개: " + " | ".join(src_polluted[:3]))
    if len(src_styles) > 1:
        major = max(src_styles, key=lambda k: len(src_styles[k]))
        minority = {k: v for k, v in src_styles.items() if k != major}
        critical.append(
            "[마커스타일] 출처 마커가 복수 스타일로 인쇄됨 (기준 "
            f"「{major}」 {len(src_styles[major])}개 외): "
            + " | ".join(f"「{k}」 {len(v)}개 (예: {v[0][:30]})"
                         for k, v in sorted(minority.items())[:3]))

    # ── G17 학원 워터마크 잔존 (W17 c16) ─────────────────────────────────
    watermark = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if _RE_WATERMARK_URL.match(tt) or _RE_WATERMARK_WARN.search(tt):
            watermark.append(tt[:50])
    stats["watermark_leaks"] = len(watermark)
    if watermark:
        critical.append(
            f"[워터마크잔존] 학원 워터마크/경고 라인 {len(watermark)}개가 "
            f"출력에 인쇄됨: " + " | ".join(watermark[:3]))

    # ── G18 유형 마커 스타일 일관성 (W17 c16) ────────────────────────────
    type_styles = {}
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if _RE_TYPE_MARKER.match(tt):
            type_styles.setdefault(s, []).append(tt)
    stats["type_markers"] = sum(len(v) for v in type_styles.values())
    stats["type_marker_styles"] = len(type_styles)
    if len(type_styles) > 1:
        major = max(type_styles, key=lambda k: len(type_styles[k]))
        minority = {k: v for k, v in type_styles.items() if k != major}
        critical.append(
            "[유형마커스타일] 유형 구분 마커가 복수 스타일로 인쇄됨 (기준 "
            f"「{major}」 {len(type_styles[major])}개 외): "
            + " | ".join(f"「{k}」 {len(v)}개 (예: {v[0][:30]})"
                         for k, v in sorted(minority.items())[:3]))

    # ── G12 문장삽입 '주어진 문장' 배경 (W15 c04, W39 결함 2 전 스토리
    # 확장) ──────────────────────────────────────────────────────────────
    # 문장삽입 발문 뒤 3단락 내에 배경 스타일 단락이 없으면 지목 — 주어진
    # 문장 박스 누락 (v2는 분류 계층 P-CONTEXT로 부여, v1 실물은 마커에
    # 배경을 줬음 — 어느 쪽이든 '배경 없음'은 결함). W15의 SRC 마커 스토리
    # 한정을 W39에서 폐기 (87번 "주어진 문장" ❮…❯이 지문 스타일로 인쇄된
    # 실증 — 마커 없는 실전문제 스토리는 침묵이었다). 현행 플랜(주어진
    # 블록을 배경으로 실은 플랜)은 critical, 구플랜 소급은 warning
    # (G32 패턴).
    plan_insert_bg = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        fps = [p for u in fl.get("units", [])
               for p in (u["paras"] if isinstance(u, dict) else u)]
        for i, p in enumerate(fps):
            if _RE_INSERT_PROMPT.search(_clean(p.get("t", ""))) \
                    and any("배경" in (q.get("s") or "")
                            for q in fps[i + 1:i + 3]):
                plan_insert_bg = True
                break
    insert_missing = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        # step3(실전문제) 스토리 한정 — step1_c1의 자동 발문("아래 주어진
        # 문장이 …")은 하단(BTM) 스타일 의미론이라 배경 기대가 없다
        if not any("STEP 03" in (p.get("s") or "") for p in ps):
            continue
        for i, p in enumerate(ps):
            if not _RE_INSERT_PROMPT.search(_clean(p.get("t", ""))):
                continue
            window = [q for q in ps[i + 1:i + 5]
                      if _clean(q.get("t", ""))][:3]
            # 주어진 문장 없이 곧장 선지로 가는 재사용 변형("Q C" — 실측
            # 2/49)은 슬롯 부재가 정상 — 첫 후속이 선지 스타일이면 제외
            if window and "선지" in (window[0].get("s") or ""):
                continue
            if not any("배경" in (q.get("s") or "") for q in window):
                insert_missing.append(_clean(p.get("t", ""))[:40])
    stats["insert_bg_missing"] = len(insert_missing)
    if insert_missing:
        msg = (f"[문장삽입배경] 문장삽입 발문 뒤 배경(주어진 문장 박스) "
               f"미부여 {len(insert_missing)}건: "
               + " | ".join(insert_missing[:3]))
        (critical if plan_insert_bg else warnings).append(msg)

    # ── G32 [요약문] 마커 + 요약 문장 배경 (W38 결함 4) ──────────────────
    # [요약문] 마커와 그 다음 문장 단락은 배경 스타일이어야 한다 (사용자
    # 확정 스펙 — 6b66b750 실증 9블록이 지문 스타일로 인쇄). 현행 플랜
    # (마커를 배경으로 실은 플랜)은 critical, 구출력(마커에 배경이 없는
    # 구플랜)은 warning 소급 (G29 ①b 패턴).
    plan_sum_bg = False
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if _RE_SUM_MARKER.match(_clean(p.get("t", ""))) \
                        and "배경" in (p.get("s") or ""):
                    plan_sum_bg = True
                    break
    sum_bg_miss = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps):
            if not _RE_SUM_MARKER.match(_clean(p.get("t", ""))):
                continue
            bad = "배경" not in (p.get("s") or "")
            nxt = next((q for q in ps[i + 1:]
                        if _clean(q.get("t", ""))), None)
            if nxt is not None and "배경" not in (nxt.get("s") or ""):
                bad = True
            if bad:
                sum_bg_miss.append(_clean(p.get("t", ""))[:20])
    stats["sum_bg_miss"] = len(sum_bg_miss)
    if sum_bg_miss:
        msg = (f"[요약문배경] [요약문] 마커/요약 문장 배경 스타일 누락 "
               f"{len(sum_bg_miss)}건")
        (critical if plan_sum_bg else warnings).append(msg)

    # ── G13 발문 스타일 누락 (W16 c07) ───────────────────────────────────
    # [서술형 N] 접두 태그, 또는 발문 시작 신호("다음/윗글/주어진…") +
    # 시오/세요-체 종결(꼬리 [출처] 태그 제거 후)이 발문 계열 스타일이
    # 아니면 검출 — 해요체("쓰세요") 발문이 지문 스타일로 인쇄되는 결함.
    q_style_miss = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if not _RE_HANGUL.search(tt):
            # W38 확장: 영어 지시문 발문 시그니처 (번호 + 명령형/WH-의문 —
            # 정상 출력은 Q 스타일+번호 제거이므로 번호 접두 잔존 자체가
            # 미인식 서명. 6b66b750 "10. Choose True or False …" 실증)
            if _RE_Q_EN_SIG.match(tt) and not any(
                    k in (s or "") for k in _Q_STYLE_KEYS):
                q_style_miss.append(tt[:45])
            continue
        core = tt
        while True:
            nx = _RE_Q_TRAIL_SRC.sub("", core)
            if nx == core:
                break
            core = nx
        body = _RE_Q_LEAD_TAG.sub("", core).strip()
        had_tail_tag = core != tt   # 꼬리 [출처/태그]가 있었음
        is_q_sig = bool(_RE_Q_LEAD_TAG.match(core)) or (
            _RE_Q_START.match(body) and _RE_Q_END.search(body)) or (
            had_tail_tag and bool(_RE_Q_END.search(body)))   # W18 확장
        if is_q_sig and body and not any(k in (s or "")
                                         for k in _Q_STYLE_KEYS):
            q_style_miss.append(tt[:45])
    stats["q_style_miss"] = len(q_style_miss)
    if q_style_miss:
        critical.append(
            f"[발문스타일] 발문 시그니처 단락 {len(q_style_miss)}개가 발문 "
            f"계열 스타일이 아님: " + " | ".join(q_style_miss[:3]))

    # ── G20 스토리 선두 날짜-only 잔재 (W18 c18) ─────────────────────────
    lead_junk = []
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            tt = _clean(p.get("t", ""))
            if not tt:
                continue
            if _RE_LEAD_DATE.match(tt):
                lead_junk.append(tt[:30])
            break               # 스토리 첫 콘텐츠 단락만 검사
    stats["leading_date_junk"] = len(lead_junk)
    if lead_junk:
        critical.append(
            f"[선두잔재] 스토리 선두에 날짜-only 라인 {len(lead_junk)}개 "
            f"인쇄됨 (표제 블록 잔재): " + " | ".join(lead_junk[:3]))

    # ── G14 영단어 스타일 오분류 (W16 c10) ───────────────────────────────
    word_bad = []
    for t, s in _dump_paras(dump):
        if "영단어" not in (s or ""):
            continue
        tt = _clean(t)
        if not tt:
            continue
        if not _RE_HANGUL.search(tt) or _RE_WORD_BAD_HEAD.match(tt):
            word_bad.append(tt[:45])
    stats["word_style_bad"] = len(word_bad)
    if word_bad:
        critical.append(
            f"[영단어오분류] 어휘 항목이 아닌 단락 {len(word_bad)}개가 "
            f"영단어 스타일로 인쇄됨: " + " | ".join(word_bad[:3]))

    # ── G21 원문자 ① 중복 오염 (W19 c20) ────────────────────────────────
    # ※ 다중 문항 아이템은 발문마다 지문을 재인쇄한다. 마지막 5지선다
    # 발문(도표/불일치류 — 선지가 지문 문장 inline ①~⑤) 뒤 재인쇄 지문에
    # 선지 자동번호가 원고에 없는 ①을 prepend → '①The graph … ① In
    # Germany …'처럼 한 단락에 ①이 2회 등장하는 기형 번호가 인쇄된다.
    # 원고에 타이핑된 inline 번호 지문('①Families … ②Gary …' c19 /
    # '① Remember …' 0a5da924)은 ①이 1회뿐이라 통과 (v1 관행 보존).
    choice_polluted = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if len(tt) < 200 or not tt or tt[0] != "①":
            continue
        if "①" in tt[1:]:
            choice_polluted.append(tt[:60])
    stats["choice_polluted_passages"] = len(choice_polluted)
    if choice_polluted:
        critical.append(
            f"[원문자중복] ①로 시작하면서 본문에 ①이 다시 등장하는 장문 "
            f"단락 {len(choice_polluted)}개 — 선지 자동번호가 inline 번호 "
            f"지문에 ①을 중복 부여한 오염: " + " | ".join(choice_polluted[:2]))

    # ── G22 간지 라벨 원고 불일치 (W19 c20 + 본가 소급) ──────────────────
    # v1 16.7은 간지의 '고N 모의고사 / YY년 M월'을 원고 값으로 갱신한다.
    # content에 grade/year/month가 전부 있을 때만 검사 (교과서 간지는
    # subject/publisher 형식이라 L1 패턴 자체가 안 잡힘).
    exp_g, exp_y, exp_m = (content or {}).get("grade"), \
        (content or {}).get("year"), (content or {}).get("month")
    divider_stale = []
    if exp_g and exp_y and exp_m:
        for story in dump.get("stories", []):
            ps = story.get("paragraphs", [])
            for i in range(len(ps) - 1):
                m1 = _RE_DIVIDER_L1.match(_clean(ps[i].get("t", "")))
                m2 = _RE_DIVIDER_L2.match(_clean(ps[i + 1].get("t", "")))
                if not (m1 and m2):
                    continue
                if (int(m1.group(1)) != int(exp_g)
                        or int(m2.group(1)) != int(exp_y) % 100
                        or int(m2.group(2)) != int(exp_m)):
                    divider_stale.append(
                        f"{m1.group(0)}/{m2.group(0)}")
    stats["divider_stale"] = len(divider_stale)
    if divider_stale:
        msg = (f"[간지라벨] 간지 라벨 {len(divider_stale)}개가 원고"
               f"(고{exp_g} {exp_y}년 {exp_m}월)와 불일치 — 템플릿 잔재: "
               + " | ".join(sorted(set(divider_stale))[:3]))
        # divider op 사용 플랜은 갱신이 계약 — critical. 미사용(과거 출력
        # /세로 실행기)은 warning 지목 (G3/G4 패턴).
        if plan.get("divider"):
            critical.append(msg)
        else:
            warnings.append(msg)

    # ── G15 <조건> 블록 항목 스타일 (W16 c10, W38 블록 문맥 우선 확장) ──
    # <조건> 마커부터 답란(밑줄런/정답/→/우리말) 이전까지 스캔. 강신호
    # 조건 항목(불릿 시작 / 한글 + '것' 종결 / 번호 항목 — W38: 종결어미
    # 무관)이 조건 스타일이 아니면 검출. 블록 종료는 구조 신호만: 답란/
    # 보기/배경/다음글읽고 스타일/발문 어휘 선두 번호(_RE_COND_QLEAD)/
    # 번호 시퀀스 이탈. ("시오-체 번호 항목 발문 유지" W16 D3 관행은
    # 사용자 확정으로 폐기 — 6b66b750 실증.)
    # G34 [조건내용] (W39 결함 3): 블록 안 단어 나열(슬래시/쉼표 나열,
    # 한글·완결부호 없음)은 조건 내용물 — v1 '지문 유지' 관행 폐기 (사용자
    # 확정). 현행 플랜(나열을 조건 스타일로 실은 플랜)은 critical, 구플랜
    # 소급은 warning (G32 패턴).
    plan_cond_content = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if "조건" in (p.get("s") or "") \
                        and _RE_G34_WORDLIST.search(_clean(p.get("t", ""))) \
                        and not _RE_HANGUL.search(p.get("t", "")):
                    plan_cond_content = True
                    break
    cond_content_miss = []
    cond_miss = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps):
            if _clean(p.get("t", "")) != "<조건>":
                continue
            cond_no = 1        # 블록 항목 번호 시퀀스 기대값
            for j in range(i + 1, len(ps)):
                qt = _clean(ps[j].get("t", ""))
                qs = ps[j].get("s") or ""
                if not qt:
                    continue
                if _RE_COND_BLOCK_END.search(qt):
                    break
                if qt.startswith("<보기>") or qt == "보기":
                    break
                if any(k in qs for k in ("다음 글을 읽고", "보기", "배경")):
                    break
                mnum = _RE_COND_NUMSTART.match(qt)
                is_item_num = False
                if mnum:
                    num, delim = int(mnum.group(1)), mnum.group(2)
                    if delim == ")":
                        is_item_num = True
                        cond_no = num + 1
                    elif num == cond_no and not (
                            cond_no == 1 and _RE_COND_QLEAD.match(qt)):
                        is_item_num = True
                        cond_no = num + 1
                if "번호" in qs and not is_item_num and (
                        _RE_COND_QHINT.match(qt) or _RE_COND_QLEAD.match(qt)
                        or "시오" in qt):
                    break       # 진짜 발문 (번호 스타일 + 비항목) — 종료
                strong = (_RE_COND_BULLET.match(qt) or is_item_num
                          or (_RE_COND_GEOT.search(qt)
                              and _RE_HANGUL.search(qt)))
                if strong and "조건" not in qs:
                    cond_miss.append(qt[:45])
                elif not (_RE_HANGUL.search(qt)
                          or _RE_COND_BULLET.match(qt)):
                    # W39 결함 3: 블록 안 단어 나열은 조건 내용물 —
                    # 조건 스타일이 아니면 G34 지목 (지문 유지 관행 폐기)
                    if _RE_G34_WORDLIST.search(qt) and "조건" not in qs:
                        cond_content_miss.append(qt[:45])
                    continue
                elif "조건" not in qs and not strong:
                    break       # 한글 비조건 문장 — 블록 종료로 간주
    # ── G37 [발문밑줄] (W39 결함 6): 발문 인용구 밑줄 (플랜 runs 검사) ──
    # 발문(번호 스타일)이 "밑줄 친 <영어구>"를 인용하면 인용구 구간에
    # 밑줄 run이 있어야 한다. 덤프에는 문자 서식 정보가 없어 플랜에서
    # 검증 — 플랜에 밑줄 인용 발문이 하나라도 있으면(현행) critical,
    # 전무하면(구플랜 소급) warning.
    ulq_miss = []
    ulq_ok = 0
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if "번호" not in (p.get("s") or ""):
                    continue
                mq = _RE_G37_QUOTE.search(p.get("t") or "")
                if not mq:
                    continue
                quote = mq.group(1).rstrip(" '\"’”")
                if len(quote) < 2 or not re.search(r"[A-Za-z]{2}", quote):
                    continue      # 표식 참조("(A)"/"ⓐ")는 인용이 아님
                qs, qe = mq.start(1), mq.start(1) + len(quote)
                off = 0
                has_ul = False
                for r in p.get("runs") or []:
                    t = r.get("t") or ""
                    if r.get("ul") and off < qe and off + len(t) > qs:
                        has_ul = True
                    off += len(t)
                if has_ul:
                    ulq_ok += 1
                else:
                    ulq_miss.append(quote[:30])
    stats["q_quote_ul_miss"] = len(ulq_miss)
    if ulq_miss:
        msg = (f"[발문밑줄] 발문 인용구 밑줄 미부여 {len(ulq_miss)}건: "
               + " | ".join(ulq_miss[:3]))
        (critical if ulq_ok else warnings).append(msg)

    # ── G36 [TF선지] (W39 결함 5): 진위 선택 행 = 선지 스타일 ────────────
    # 발문(번호 스타일 + True or False/(T/F) 지시) 뒤의 "N) 문장 (T/F)"
    # 행이 선지 스타일이 아니면 지목 (111번 실증 — 지문 스타일 인쇄).
    # 현행 플랜은 critical, 구플랜 소급 warning.
    plan_tf = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if _RE_G36_TFROW.match(_clean(p.get("t", ""))) \
                        and "선지" in (p.get("s") or ""):
                    plan_tf = True
                    break
    tf_miss = []
    for story in dump.get("stories", []):
        ps = [p for p in story.get("paragraphs", [])
              if _clean(p.get("t", ""))]
        in_tf = False
        for p in ps:
            t = _clean(p.get("t", ""))
            s = p.get("s") or ""
            if "번호" in s:
                in_tf = bool(_RE_G36_TFREF.search(t))
                continue
            if not in_tf:
                continue
            if any(k in s for k in ("배경", "조건", "보기", "다음 글을")):
                in_tf = False
                continue
            if _RE_G36_TFROW.match(t) and "선지" not in s:
                tf_miss.append(t[:40])
    stats["tf_choice_miss"] = len(tf_miss)
    if tf_miss:
        msg = (f"[TF선지] 진위 선택 행 {len(tf_miss)}개가 선지 스타일이 "
               f"아님: " + " | ".join(tf_miss[:3]))
        (critical if plan_tf else warnings).append(msg)

    # ── G35 [답란] (W39 결함 4): "라벨:" + 빈칸 쌍 = 답란 계열 ──────
    # ("주제문:" + "____."가 지문 스타일로 인쇄되던 실증 — 84/85번.
    # 현행 플랜(답란 스타일 실림)은 critical, 구플랜 소급 warning.)
    plan_ansl = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if _RE_G35_LABEL.match(_clean(p.get("t", ""))) \
                        and any(k in (p.get("s") or "")
                                for k in ("선지", "답")):
                    plan_ansl = True
                    break
    ansl_miss = []
    for story in dump.get("stories", []):
        ps = [p for p in story.get("paragraphs", [])
              if _clean(p.get("t", ""))]
        for i in range(len(ps) - 1):
            t1 = _clean(ps[i].get("t", ""))
            t2 = _clean(ps[i + 1].get("t", ""))
            if not (_RE_G35_LABEL.match(t1) and _RE_G35_BLANK.match(t2)):
                continue
            for q in (ps[i], ps[i + 1]):
                qs = q.get("s") or ""
                if not any(k in qs for k in ("선지", "답")):
                    ansl_miss.append(_clean(q.get("t", ""))[:25])
    stats["ansl_miss"] = len(ansl_miss)
    if ansl_miss:
        msg = (f"[답란] 라벨+빈칸 답란 쌍 {len(ansl_miss)}개 라인이 답란 "
               f"계열(선지) 스타일이 아님: " + " | ".join(ansl_miss[:3]))
        (critical if plan_ansl else warnings).append(msg)

    # ── G38 [순서선지] (W40 결함 3): 순열 행 = 원문자 + 선지 스타일 ─────
    # 현행 플랜(원문자+선지 순열 행이 실린 플랜)은 critical, 구출력 소급
    # warning (G36/G35 패턴).
    plan_perm = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if _RE_G38_PERM_NUMBERED.match(_clean(p.get("t", ""))) \
                        and "선지" in (p.get("s") or ""):
                    plan_perm = True
                    break
    perm_bad = []
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            t = _clean(p.get("t", ""))
            s = p.get("s") or ""
            m = _RE_G38_PERM_BARE.match(t)
            if m and len(set(m.groups())) == 3:
                perm_bad.append(f"원문자 누락 「{t[:24]}」")
                continue
            m = _RE_G38_PERM_NUMBERED.match(t)
            if m and len(set(m.groups())) == 3 and "선지" not in s:
                perm_bad.append(f"스타일 「{s[-20:]}」 「{t[:24]}」")
    stats["perm_row_bad"] = len(perm_bad)
    if perm_bad:
        msg = (f"[순서선지] 순서배열 선지 순열 행 {len(perm_bad)}개 결함 "
               f"(원문자 누락/선지 스타일 아님): " + " | ".join(perm_bad[:4]))
        (critical if plan_perm else warnings).append(msg)

    # ── G39 [지문배경] (W40 결함 4): 네모/괄호 선택형 지문 ≠ 배경 ───────
    # 발문(번호 스타일 + 네모/괄호 시그니처) 직후 유의 단락이 배경
    # 스타일이면 지목 — 재인쇄 지문은 지문 스타일이 계약 (215번 실증).
    def _g39_is_paren_q(t):
        return ("(A)" in t and _RE_G39_TOKEN.search(t)
                and "에서" in t and _RE_G39_SUBJECT.search(t))

    plan_paren_fixed = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        paras = [p for u in fl.get("units", [])
                 for p in (u["paras"] if isinstance(u, dict) else u)]
        for i, p in enumerate(paras):
            if "번호" not in (p.get("s") or "") \
                    or not _g39_is_paren_q(_clean(p.get("t", ""))):
                continue
            for q in paras[i + 1:]:
                if not _clean(q.get("t", "")):
                    continue
                if "배경" not in (q.get("s") or ""):
                    plan_paren_fixed = True
                break
            if plan_paren_fixed:
                break
    paren_bg = []
    for story in dump.get("stories", []):
        ps = [p for p in story.get("paragraphs", [])
              if _clean(p.get("t", ""))]
        for i, p in enumerate(ps):
            s = p.get("s") or ""
            if "번호" not in s or not _g39_is_paren_q(_clean(p.get("t", ""))):
                continue
            if i + 1 < len(ps) and "배경" in (ps[i + 1].get("s") or ""):
                paren_bg.append(_clean(ps[i + 1].get("t", ""))[:32])
    stats["paren_q_bg"] = len(paren_bg)
    if paren_bg:
        msg = (f"[지문배경] 네모/괄호 선택형 지문 {len(paren_bg)}개에 배경 "
               f"스타일 오적용 (지문이어야 함): " + " | ".join(paren_bg[:3]))
        (critical if plan_paren_fixed else warnings).append(msg)

    # ── G40 [괄호답란] (W40 결함 5): 보기/조건 뒤 "(A) ___" = 답란 ──────
    # 위치 신호(직전 유의 단락이 보기/조건 계열 또는 같은 답란 체인) +
    # 형태 신호(괄호 라벨 + 밑줄 런) — 선지 계열 스타일이 계약.
    plan_pblank = False
    for fl in plan.get("flows", []):
        if fl.get("step") != "step3":
            continue
        paras = [p for u in fl.get("units", [])
                 for p in (u["paras"] if isinstance(u, dict) else u)]
        prev_s = ""
        for p in paras:
            t = _clean(p.get("t", ""))
            if not t:
                continue
            if _RE_G40_PAREN_BLANK.match(t) \
                    and any(k in prev_s for k in ("보기", "조건")) \
                    and any(k in (p.get("s") or "")
                            for k in ("선지", "답")):
                # W45: 답란 계열 = 선지(구) 또는 S_답란(신). 둘 다 계약 충족
                plan_pblank = True
                break
            prev_s = p.get("s") or ""
    pblank_miss = []
    for story in dump.get("stories", []):
        ps = [p for p in story.get("paragraphs", [])
              if _clean(p.get("t", ""))]
        chain = False       # 보기/조건 뒤 답란 체인 진행 상태
        prev_s = ""
        for p in ps:
            t = _clean(p.get("t", ""))
            s = p.get("s") or ""
            if _RE_G40_PAREN_BLANK.match(t) and (
                    chain or any(k in prev_s for k in ("보기", "조건"))):
                chain = True
                if "선지" not in s and "답" not in s:
                    pblank_miss.append(t[:25])
            else:
                chain = False
            prev_s = s
    stats["paren_blank_miss"] = len(pblank_miss)
    if pblank_miss:
        msg = (f"[괄호답란] 보기/조건 뒤 괄호 라벨 답란 {len(pblank_miss)}"
               f"개가 답란 계열(선지) 스타일이 아님: "
               + " | ".join(pblank_miss[:3]))
        (critical if plan_pblank else warnings).append(msg)

    # ── G44 [답란스타일] (W45): 답란은 S_답란 (템플릿에 있으면) ──────────
    # 사용자 확정 스펙 — 답란 전용 스타일(지문 복제 + 들여쓰기 0). 완성본
    # 다수가 답란을 지문 스타일로 갖고 있던 건 의도가 아니라 회피였다
    # (선지 들여쓰기 때문에 손으로 바꿈 — 역학습 W44 61건/13문서).
    # fail-open: 템플릿에 S_답란이 없으면 선지 폴백 + 들여쓰기 0 브릿지 —
    # critical 아님(경고만). 있으면 답란 라인은 반드시 S_답란이어야 한다.
    plan_ansline = False
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if ANSLINE_STYLE_NAME in (p.get("s") or ""):
                    plan_ansline = True
                    break
    doc_has_ansline = any(
        ANSLINE_STYLE_NAME in (p.get("s") or "")
        for story in dump.get("stories", [])
        for p in story.get("paragraphs", []))
    ansline_miss = []
    if plan_ansline and doc_has_ansline:
        for story in dump.get("stories", []):
            ps = [p for p in story.get("paragraphs", [])
                  if _clean(p.get("t", ""))]
            chain = False
            prev_s = ""
            for i, p in enumerate(ps):
                t = _clean(p.get("t", ""))
                s = p.get("s") or ""
                is_ansline = False
                if _RE_G40_PAREN_BLANK.match(t) and (
                        chain or any(k in prev_s for k in ("보기", "조건"))):
                    is_ansline = True
                    chain = True
                else:
                    chain = False
                if (i + 1 < len(ps) and _RE_G35_LABEL.match(t)
                        and _RE_G35_BLANK.match(_clean(ps[i + 1].get("t", "")))):
                    is_ansline = True
                if is_ansline and ANSLINE_STYLE_NAME not in s:
                    ansline_miss.append(t[:25])
                prev_s = s
    stats["ansline_style_miss"] = len(ansline_miss)
    stats["ansline_style_present"] = bool(doc_has_ansline)
    if ansline_miss:
        critical.append(
            f"[답란스타일] 답란 {len(ansline_miss)}개가 {ANSLINE_STYLE_NAME} "
            f"스타일이 아님 (템플릿에 존재하는데 미적용): "
            + " | ".join(ansline_miss[:3]))
    elif plan_ansline and not doc_has_ansline:
        warnings.append(
            f"[답란스타일] 템플릿에 {ANSLINE_STYLE_NAME}이 없어 선지 스타일로 "
            f"폴백했습니다 (들여쓰기 0 로컬 오버라이드 브릿지 적용 — "
            f"scripts/add_ansline_style.py 로 템플릿에 스타일을 추가하세요)")

    stats["cond_item_miss"] = len(cond_miss)
    stats["cond_content_miss"] = len(cond_content_miss)
    if cond_content_miss:
        msg = (f"[조건내용] <조건> 블록 안 단어 나열 "
               f"{len(cond_content_miss)}개가 조건 스타일이 아님: "
               + " | ".join(cond_content_miss[:3]))
        (critical if plan_cond_content else warnings).append(msg)
    if cond_miss:
        critical.append(
            f"[조건항목] <조건> 블록 항목 {len(cond_miss)}개가 조건 스타일이 "
            f"아님: " + " | ".join(cond_miss[:3]))

    # ── G3 독립 지문번호 프레임 ↔ 원고 지문번호 ─────────────────────────
    labels = list((plan.get("passage_numbers") or {}).get("labels") or [])
    if not labels:
        labels = passage_labels(steps)
    expected = set(labels)
    for sd in steps.values():
        if isinstance(sd, dict):
            for n in sd.get("question_numbers") or []:
                expected.add(str(n))
    bare_frames = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if len(ps) != 1:
            continue
        # 마스터 스프레드의 프레임 제외 — 덤프 pg 값에는 문서 페이지 번호와
        # 마스터 이름(A/B/C/D/O/간지)이 섞인다. 마스터의 스텝 표시 원
        # ("1","2","3","01","02","03")은 템플릿 잔재가 아니라 디자인 요소인데
        # 이걸 잔재로 세고 있었다 (v17 실증: 실제 잔재 20~40 을 전부 없앤
        # 뒤에도 6종이 critical 로 남음 — G4b 잔여페이지와 같은 오탐 계열).
        pgs = story.get("pg") or []
        if pgs and not any(str(x).isdigit() for x in pgs):
            continue
        tt = _clean(ps[0].get("t", ""))
        if _RE_BARE_NUM.match(tt):
            bare_frames.append(tt)
    unknown = sorted(set(t for t in bare_frames if t not in expected))
    stats["number_frames"] = len(bare_frames)
    stats["number_frame_unknown"] = len(unknown)
    if unknown:
        msg = (f"[지문번호] 원고에 없는 번호 프레임 {len(unknown)}종 잔존"
               f" (템플릿 잔재): " + ", ".join(unknown[:10]))
        (critical if strict_numbers else warnings).append(msg)

    # ── G4b 고아 번호 페이지 (W14 c03/c15 실증) ─────────────────────────
    # 지문번호/문항번호 프레임은 있는데 콘텐츠 스토리가 전혀 없는 페이지 —
    # 원고 없는 스텝의 섹션 머리/예시 페이지(c03 '20' 3p), 또는 W13 스레드
    # 절단 이후 빈 프레임 페이지가 삭제 판정(다중 프레임 전부 빈)을
    # 벗어나며 남은 잔재(c15 '5' 3p). page_cleanup 사용 시 critical.
    # 콘텐츠 판정은 '플랜(원고) 단락과 겹치는 스토리'만 — 섹션 마커
    # (" 빈칸 어휘")/발문/예시 등 내지 장식 텍스트는 콘텐츠가 아니다
    # (c03 p6/p10/p11: 마커·예시 텍스트 때문에 '내용 있음'으로 오인 방지).
    plan_texts = set()
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                tt = _clean(p.get("t", ""))
                if len(tt) >= 4:
                    plan_texts.add(tt)
    num_pages = set()
    content_pages = set()
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        pgs = story.get("pg") or []
        if len(ps) == 1 and _RE_BARE_NUM.match(_clean(ps[0].get("t", ""))):
            num_pages.update(pgs)
        elif any(_clean(p.get("t", "")) in plan_texts
                 for p in ps if len(_clean(p.get("t", ""))) >= 4):
            content_pages.update(pgs)
    # 마스터 스프레드 페이지 제외 — 덤프의 pg 값에는 문서 페이지 번호와
    # 함께 마스터 페이지 이름(A/B/C/D/O/간지)이 섞여 들어온다. 마스터에
    # 있는 번호 프레임(지문번호 placeholder)은 원래 콘텐츠가 없으므로
    # 잔여 페이지가 아니다 (2026-08-07 실측: pA~pO 5개가 상시 critical).
    orphan_pages = sorted(
        (x for x in (num_pages - content_pages) if str(x).isdigit()),
        key=lambda x: int(x))
    stats["orphan_number_pages"] = len(orphan_pages)
    if orphan_pages:
        msg = (f"[잔여페이지] 번호 프레임만 있고 콘텐츠 없는 페이지 "
               f"{len(orphan_pages)}개: p" + ", p".join(
                   str(p) for p in orphan_pages[:10]))
        (critical if strict_pages else warnings).append(msg)

    # ── G4 잔여 페이지 (원고 없는 스텝/남는 사이클) ──────────────────────
    cleanup_op = (plan.get("page_cleanup")
                  if isinstance(plan.get("page_cleanup"), dict) else {})
    cleanup_delete = cleanup_op.get("empty") == "delete"
    stale = dump.get("stale_pages")
    if stale is None:
        warnings.append("[잔여페이지] 덤프에 페이지 정보 없음(구버전 덤프)"
                        " — 재덤프 필요")
    else:
        if cleanup_delete:
            # W21 delete 모드: 빈 페이지는 삭제가 계약 — M 마스터 면제 없음.
            # 페이지 인벤토리(pages)의 빈 페이지(프레임 있고 전부 공백 —
            # 스레드 절단 후 단일 프레임 꼬리 포함)도 잔여로 합산 (r11
            # 재조판 1차 실측: stale 판정 밖 p12/p21 잔존).
            residual = list(stale)
            seen_p = {str(e.get("p")) for e in residual}
            for pe in dump.get("pages") or []:
                if pe.get("empty") and str(pe.get("p")) not in seen_p:
                    residual.append({"p": pe.get("p"), "m": pe.get("m")})
                    seen_p.add(str(pe.get("p")))
            # W22 r12: 장식-빈 페이지 합산 — 반복 장식(페이지마다 얹히는
            # 발문/섹션 탭) 단일 프레임 텍스트만 남은 페이지는 pages의
            # empty 판정('텍스트 있음')을 비껴간다 (r11 재조판 실측:
            # p34 어법선택 발문 / p47 영작배열 탭 — 사용자 지목 결함).
            # 콘텐츠(플랜 단락) 페이지에서 수집한 단일 페이지 스토리
            # 텍스트와 같은 텍스트 + 공백/번호 프레임만 있는 페이지를
            # 잔여로 본다. 간지/표지(마스터 없음)와 M 채움 페이지(파트
            # 경계 — G28이 위치 검증)는 제외.
            page_texts = {}
            furn = set()
            for story in dump.get("stories", []):
                pgs = story.get("pg") or []
                txt = _clean("".join(p.get("t", "")
                                     for p in story.get("paragraphs", [])))
                for pg in pgs:
                    page_texts.setdefault(str(pg), []).append(txt)
                if len(pgs) == 1 and txt and str(pgs[0]) in content_pages:
                    furn.add(txt)
            for pe in dump.get("pages") or []:
                p = str(pe.get("p"))
                m = str(pe.get("m") or "")
                if (p in seen_p or p in content_pages
                        or m in ("", "[None]") or m.startswith("M")):
                    continue
                texts = page_texts.get(p)
                if texts and all((not t) or _RE_BARE_NUM.match(t)
                                 or t in furn for t in texts):
                    residual.append({"p": pe.get("p"), "m": pe.get("m")})
                    seen_p.add(p)
        else:
            empty_prefix = cleanup_op.get("empty_master", "M")
            residual = [e for e in stale
                        if not str(e.get("m", "")).startswith(empty_prefix)]
        stats["stale_pages"] = len(residual)
        if residual:
            names = [str(e.get("p")) for e in residual]
            msg = (f"[잔여페이지] 내용 없는 스텝/사이클 페이지 "
                   f"{len(residual)}개 잔존: p" + ", p".join(names[:12])
                   + ("…" if len(names) > 12 else ""))
            (critical if strict_pages else warnings).append(msg)

    # ── G23 지문번호 라벨 스타일 계약 (W21 r11) ──────────────────────────
    # step_map.json의 label_contract가 flow.target으로 플랜에 실린다.
    # 라벨 셰이프 단락(단독 [N]/{N})의 실측 스타일이 계약과 다르면 critical.
    label_style_bad = []
    for fl in plan.get("flows", []):
        contract = (fl.get("target") or {}).get("label_contract")
        if not contract or not contract.get("re"):
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        try:
            rx = re.compile(contract["re"])
        except re.error:
            continue
        want = contract.get("style") or "$BASIC"
        for p in story.get("paragraphs", []):
            tt = _clean(p.get("t", ""))
            if not tt or not rx.match(tt):
                continue
            s = p.get("s") or ""
            ok_style = (s in _BASIC_ALIASES if want == "$BASIC"
                        else s == want)
            if not ok_style:
                label_style_bad.append(
                    f"{fl['step']} {tt[:15]} 「{s}」≠「{want}」")
    stats["label_style_bad"] = len(label_style_bad)
    if label_style_bad:
        critical.append(
            f"[라벨스타일] 지문번호 라벨 {len(label_style_bad)}개가 계약 "
            f"스타일과 불일치: " + " | ".join(label_style_bad[:4]))

    # ── G24 프레임 브레이크 (W21 r11) ────────────────────────────────────
    # ① per_passage_units 계약 스텝이 지문 다수 원고에서 유닛 1개로 배치 —
    #    헤더 미인식으로 프레임 분리가 통째로 실패한 상태 (플랜 실측).
    labels_for_units = list((plan.get("passage_numbers") or {})
                            .get("labels") or []) or passage_labels(steps)
    break_fail = []
    for fl in plan.get("flows", []):
        if not (fl.get("target") or {}).get("per_passage_units"):
            continue
        if len(fl.get("units") or []) == 1 and len(labels_for_units) >= 2:
            break_fail.append(f"{fl['step']} (지문 {len(labels_for_units)}개 "
                              f"→ 유닛 1개)")
    stats["frame_break_plan_fail"] = len(break_fail)
    if break_fail:
        critical.append(
            f"[프레임브레이크] 지문 분리 미발생 {len(break_fail)}개 스텝: "
            + " | ".join(break_fail[:5]))

    # ①b (W30-r15): step1_c1 부분 미인식 — {헤더} 마커 수 < 지문 라벨 수.
    # 376b34d0 실증: 6지문 중 '6. L1-추가본문'만 GREP 미정규화 → 추가본문
    # 지문이 본문5 블록에 흡수(발문/프레임 분리 누락)됐는데 유닛이 10개라
    # ①(유닛 1개 판정)을 비껴갔다. per_passage_units 계약 스텝 한정.
    c1_deficit = []
    for fl in plan.get("flows", []):
        if fl.get("step") != "step1_c1":
            continue
        if not (fl.get("target") or {}).get("per_passage_units"):
            continue
        if len(labels_for_units) < 2:
            continue
        n_markers = sum(
            1 for u in fl.get("units") or []
            for p in (u["paras"] if isinstance(u, dict) else u)
            if re.match(r"^\{+[^{}]+\}+$", (p.get("t") or "").strip()))
        if n_markers < len(labels_for_units):
            c1_deficit.append(
                f"step1_c1 헤더 마커 {n_markers}개 < 지문 "
                f"{len(labels_for_units)}개")
    stats["c1_marker_deficit"] = len(c1_deficit)
    if c1_deficit:
        critical.append(
            "[프레임브레이크] 지문 헤더 부분 미인식 — 미인식 지문이 앞 "
            "블록에 흡수됨: " + " | ".join(c1_deficit))

    # ② 유닛 시작 단락이 실제 프레임 경계에 있는지 (덤프 fc 실측 — 신형
    #    덤프 한정. 단락↔플랜 1:1 정렬은 배치 방식(story.contents 치환)이
    #    보장, trimWsOverset로 꼬리 단락이 줄 수 있어 범위 밖은 생략).
    fc_missing_warned = False
    break_pos_bad = []
    for fl in plan.get("flows", []):
        units = fl.get("units") or []
        if not fl.get("break_per_unit") or len(units) < 2:
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        if "fc" not in story:
            if not fc_missing_warned:
                warnings.append("[프레임브레이크] 덤프에 프레임 문자 인덱스"
                                "(fc) 없음(구버전 덤프) — 실측 생략")
                fc_missing_warned = True
            continue
        fc_set = {c for c in story.get("fc") or [] if c >= 0}
        ps = story.get("paragraphs", [])
        offsets = []
        off = 0
        for p in ps:
            offsets.append(off)
            off += len(p.get("t") or "")
        upto = 0
        for k, u in enumerate(fl["units"]):
            n_paras = len(u["paras"] if isinstance(u, dict) else u)
            start = upto
            upto += n_paras
            if k == 0 or start >= len(offsets):
                continue
            if offsets[start] not in fc_set:
                break_pos_bad.append(f"{fl['step']} 유닛{k + 1}")
    stats["frame_break_pos_bad"] = len(break_pos_bad)
    if break_pos_bad:
        critical.append(
            f"[프레임브레이크] 유닛 시작이 프레임 경계에 있지 않음 "
            f"{len(break_pos_bad)}건: " + " | ".join(break_pos_bad[:5]))

    # ── G25 발문 다음 빈 단락 (W21 r11) ──────────────────────────────────
    # 발문(하단 문제 스타일) 바로 다음의 '진짜 빈'(앵커 없는) 단락 —
    # 발문과 주어진 문장 사이 불필요한 빈 줄. v1 실물은 발문 직후가 BTM.
    prompt_gap = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps[:-1]):
            leaf = (p.get("s") or "").split(" > ")[-1].strip()
            if leaf != "하단 문제":
                continue
            if not _RE_C1_PROMPT_TEXT.match(_clean(p.get("t", ""))):
                continue    # C1 자동 삽입 발문만 — B1 발문 등 오탐 방지
            nt = (ps[i + 1].get("t") or "")
            if "￼" in nt:
                continue          # 아이콘 앵커 단락은 빈 줄이 아님
            if not nt.replace("\r", "").strip():
                prompt_gap.append(_clean(p.get("t", ""))[:35])
    stats["prompt_gap_blanks"] = len(prompt_gap)
    if prompt_gap:
        critical.append(
            f"[발문빈단락] 발문 바로 다음 빈 단락 {len(prompt_gap)}건 "
            f"(발문-주어진 문장 사이 빈 줄): " + " | ".join(prompt_gap[:3]))

    # ── G26 섹션 시작 좌/우 마스터 (W21 r11) ─────────────────────────────
    pages_inv = {str(e.get("p")): e for e in dump.get("pages") or []}
    strict_masters = bool(plan.get("section_masters"))
    master_bad = []
    pages_missing_warned = False
    for fl in plan.get("flows", []):
        pair = (fl.get("target") or {}).get("master_pair")
        if not pair:
            continue
        if not pages_inv:
            if not pages_missing_warned and dump.get("stories"):
                warnings.append("[섹션마스터] 덤프에 페이지 인벤토리(pages) "
                                "없음(구버전 덤프) — 실측 생략")
                pages_missing_warned = True
            break
        story = _find_flow_story(dump, fl)
        if story is None or not story.get("pg"):
            continue
        entry = pages_inv.get(str(story["pg"][0]))
        if not entry:
            continue
        want = pair.get("right") if entry.get("side") == "R" \
            else pair.get("left")
        if want and entry.get("m") != want:
            master_bad.append(f"{fl['step']} p{entry.get('p')}"
                              f"({entry.get('side')}) 「{entry.get('m')}」"
                              f"≠「{want}」")
    stats["section_master_bad"] = len(master_bad)
    if master_bad:
        msg = (f"[섹션마스터] 섹션 시작 페이지 마스터가 좌/우 변형과 "
               f"불일치 {len(master_bad)}건: " + " | ".join(master_bad[:5]))
        (critical if strict_masters else warnings).append(msg)

    # ── G27 간지 적합성 (W21 r11 → W22 r12 스펙 확정) ────────────────────
    # 사용자 확정 스펙 (r12 피드백 3, supp 계열): 간지는 업로드 시 입력한
    # 간지 문구, 미입력이면 교재유형만 표기 (예: '외부지문'). 엔진이
    # plan.divider.source(user|type)로 계약을 실으면:
    #   ① '고N 모의고사 / YY년 M월' 잔재 = critical (기대 문구로 갱신됐어야 함)
    #   ② 간지 라벨 실측(마스터 없는 페이지의 단일 페이지 스토리)이 기대
    #      문구(line1)와 불일치 = critical (라벨 실측이 없으면 생략 —
    #      간지 없는 합성 덤프/내지 호환)
    # source 없는 플랜(본가 모의고사/구출력)은 기존 W21 warning 유지:
    # 외부지문 무-p형('N. no.M') 원고 + '모의고사' 라벨 → 사람 확인 지목
    # (v1 실물도 같은 라벨을 유지한 관행 — 자동 치환 근거가 없었다).
    is_nop_manuscript = any(
        _RE_NOP_HEADER.match(_norm_header(p.get("text") or ""))
        for sd in steps.values() if isinstance(sd, dict)
        for p in (sd.get("paragraphs") or []))
    divider_plan = plan.get("divider") or {}
    supp_divider = divider_plan.get("source") in ("user", "type")
    # W23 r13 (F1 — 사용자 확정 스펙 강화): supp 계열(source 계약)에서
    # '모의고사'는 어떤 경우에도 자동(type)으로 나가면 안 된다 — 유형 판정
    # 실패의 메타 기본값 추락 (job 6c1430c3 실증: '[N과 추가지문]' 헤더
    # 원고가 무-p형 감지에 안 잡혀 간지가 '모의고사'로 인쇄). 판정 불가면
    # 중립 '부교재'가 계약. 사용자가 직접 입력(source=user)한 문구는 무관.
    if (divider_plan.get("source") == "type"
            and _clean(divider_plan.get("line1") or "") == "모의고사"):
        critical.append(
            "[간지적합] supp 간지 계약 위반 — 교재유형 자동 판정이 "
            "'모의고사' (supp에서 '모의고사' 자동 라벨 금지 — 판정 불가면 "
            "'부교재', r13 F1)")
    # W24 r14 (사용자 확정 스펙): 자동 판정('N과 추가지문' 감지 포함)의
    # 표기는 '외부지문'이다 — source=type + '추가지문'은 구 판정 사다리
    # (r13 ③)의 잔존 플랜 (사용자 직접 입력 source=user는 무관).
    if (divider_plan.get("source") == "type"
            and _clean(divider_plan.get("line1") or "") == "추가지문"):
        critical.append(
            "[간지적합] supp 간지 계약 위반 — 교재유형 자동 판정 표기가 "
            "'추가지문' (자동 표기는 '외부지문'이 계약, r14)")
    if supp_divider or is_nop_manuscript:
        mock_dividers = []
        for story in dump.get("stories", []):
            ps = story.get("paragraphs", [])
            for i in range(len(ps) - 1):
                if (_RE_DIVIDER_L1.match(_clean(ps[i].get("t", "")))
                        and _RE_DIVIDER_L2.match(
                            _clean(ps[i + 1].get("t", "")))):
                    mock_dividers.append(_clean(ps[i].get("t", "")))
        stats["divider_type_mismatch"] = len(mock_dividers)
        if supp_divider:
            want_l1 = _clean(divider_plan.get("line1") or "")
            if mock_dividers:
                critical.append(
                    f"[간지적합] 간지 {len(mock_dividers)}개가 모의고사 "
                    f"라벨 잔재 — 기대 문구 「{want_l1}」 미적용: "
                    + mock_dividers[0])
            elif pages_inv and want_l1:
                # 간지 라벨 실측 대조 — 마스터 없는 페이지의 단일 페이지
                # 스토리(2단락+, 첫 단락 한글) = 간지 라벨 (실행기
                # updateDividerPages와 동일 판정 부류)
                divider_wrong = []
                for story in dump.get("stories", []):
                    pgs = story.get("pg") or []
                    if len(pgs) != 1:
                        continue
                    entry = pages_inv.get(str(pgs[0]))
                    if (not entry
                            or str(entry.get("m") or "") not in ("",
                                                                 "[None]")):
                        continue
                    ps = story.get("paragraphs", [])
                    if len(ps) < 2:
                        continue
                    t0 = _clean(ps[0].get("t", ""))
                    if not _RE_HANGUL.search(t0) and t0 != want_l1:
                        continue
                    if t0 != want_l1:
                        divider_wrong.append(f"p{entry.get('p')} 「{t0[:20]}」")
                stats["divider_label_wrong"] = len(divider_wrong)
                if divider_wrong:
                    critical.append(
                        f"[간지적합] 간지 라벨 {len(divider_wrong)}개가 기대 "
                        f"문구 「{want_l1}」와 불일치: "
                        + " | ".join(divider_wrong[:3]))
        elif is_nop_manuscript and mock_dividers:
            warnings.append(
                f"[간지적합] 외부지문 원고인데 간지 {len(mock_dividers)}개가 "
                f"'모의고사' 라벨 — 원고 유형과 불일치 의심 (사람 확인): "
                + mock_dividers[0])

    # ── G28 파트 경계 정렬 (W22 r12) ─────────────────────────────────────
    # [원본]워크북_C 실측: 간지 스프레드 = 왼쪽(빈 페이지) + 오른쪽(라벨).
    # ① 간지 라벨 페이지가 물리 왼쪽(L)이면 파트 경계 채움 페이지 누락 —
    #    delete 모드(정렬이 실행기 계약)는 critical, 아니면 warning
    #    (v1 실물도 밀린 간지를 방치한 관행 — W19 D5 주석. 완제품 기준
    #    으로 폐기, 사용자 확정 스펙: 오른쪽 채움 페이지 = M 마스터 삽입).
    # ② delete 모드의 M 마스터 페이지는 간지 직전 오른쪽 채움만 허용 —
    #    그 외 위치의 M 페이지는 빈 페이지 잔재 (W21 '완전 정리' 정책).
    if pages_inv:
        div_l1 = _clean((plan.get("divider") or {}).get("line1") or "")
        boundary_bad = []
        for story in dump.get("stories", []):
            pgs = story.get("pg") or []
            if len(pgs) != 1:
                continue
            entry = pages_inv.get(str(pgs[0]))
            if not entry or str(entry.get("m") or "") not in ("", "[None]"):
                continue
            ps = story.get("paragraphs", [])
            if not ps:
                continue
            t0 = _clean(ps[0].get("t", ""))
            is_label = (div_l1 and t0 == div_l1) or (
                len(ps) >= 2 and _RE_DIVIDER_L1.match(t0)
                and _RE_DIVIDER_L2.match(_clean(ps[1].get("t", ""))))
            if is_label and entry.get("side") == "L":
                boundary_bad.append(
                    f"간지 p{entry.get('p')}가 왼쪽 페이지 (오른쪽 채움 누락)")
        # W30-r15 (결함 7): 크레딧(판권) 페이지 식별 — 마스터 없음 + 텍스트
        # 프레임 0(그래픽 전용, dump 규약상 empty=False) + 문서 말미.
        # 간지 왼쪽 동반 페이지와 같은 셰이프지만 간지는 라벨 페이지가
        # 뒤따르므로 '말미'가 될 수 없다 (전 코퍼스 덤프 sweep: 모든 산출
        # 문서의 마지막 비-M 페이지가 이 셰이프 = [원본]워크북_C 판권).
        framed_pages = set()
        for story in dump.get("stories", []):
            for fpg in (story.get("fp") or story.get("pg") or []):
                framed_pages.add(str(fpg))

        def _credit_shape(pe):
            return (pe is not None
                    and str(pe.get("m") or "") in ("", "[None]")
                    and not pe.get("empty")
                    and str(pe.get("p")) not in framed_pages)

        plist = dump.get("pages") or []
        if cleanup_delete:
            for i, pe in enumerate(plist):
                if not str(pe.get("m") or "").startswith("M"):
                    continue
                nxt = plist[i + 1] if i + 1 < len(plist) else None
                ok_pos = (pe.get("side") == "R" and nxt
                          and str(nxt.get("m") or "") in ("", "[None]"))
                # W38: W30의 '크레딧 뒤 오른쪽 메모(M)' 허용 폐기 —
                # 책은 크레딧(왼쪽)에서 끝난다 (사용자 확정 스펙 정정).
                if not ok_pos:
                    boundary_bad.append(
                        f"M 페이지 p{pe.get('p')} 위치 이상 "
                        f"(간지 직전 오른쪽 채움만 허용)")
        stats["part_boundary_bad"] = len(boundary_bad)
        if boundary_bad:
            msg = (f"[파트경계] 파트 경계 정렬 이상 {len(boundary_bad)}건: "
                   + " | ".join(boundary_bad[:5]))
            (critical if cleanup_delete else warnings).append(msg)

        # ── G28④ 크레딧 페이지 정렬 (W30-r15 도입, W38 스펙 정정 — 사용자
        # 확정: 크레딧은 왼쪽 + 문서의 마지막 페이지. 책은 오른쪽 시작,
        # 왼쪽(크레딧) 끝 — W30의 '크레딧 뒤 메모(M) 추가'는 잘못된 스펙.
        # delete 모드(실행기 alignCreditPage가 계약)는 critical, 구출력은
        # warning 소급 지목) ──
        ci = len(plist) - 1
        while ci >= 0 and str(plist[ci].get("m") or "").startswith("M"):
            ci -= 1
        credit_bad = []
        if ci >= 0 and _credit_shape(plist[ci]):
            ce = plist[ci]
            if ce.get("side") == "R":
                credit_bad.append(
                    f"크레딧 p{ce.get('p')}가 오른쪽 페이지 (왼쪽 정렬 계약)")
            elif ci != len(plist) - 1:
                credit_bad.append(
                    f"크레딧 p{ce.get('p')} 뒤 잔여 페이지 {len(plist)-1-ci}장 "
                    f"(크레딧이 마지막 페이지 계약 — 책은 왼쪽 끝)")
        stats["credit_page_bad"] = len(credit_bad)
        if credit_bad:
            msg = "[파트경계] 크레딧 정렬 이상: " + " | ".join(credit_bad)
            (critical if cleanup_delete else warnings).append(msg)

        # ── G33 지문번호 라벨 프레임 좌/우 기하 대조 (W38 — 결함 2) ─────
        # 비숫자 지문번호 라벨(본문N/추가본문) 단일 프레임의 크기가 좌/우
        # 페이지에서 같아야 한다 (사용자 확정: 왼쪽 크기에 통일 — 실행기
        # updatePassageNumbers 좌우 정규화가 계약). 같은 높이 계열(±1mm —
        # 세로형/가로형 라벨 혼재 구분)의 왼쪽 프레임과 폭/높이 0.3mm 초과
        # 차이면 검출. fb 없는 구버전 덤프는 검사 생략 (G24② 전례).
        pn_labels = set(
            str(x) for x in
            (plan.get("passage_numbers") or {}).get("labels") or [])
        pn_labels = {x for x in pn_labels if not _RE_BARE_NUM.match(x)}
        if pn_labels:
            lab_geo = []       # (side, w, h, text, page)
            for story in dump.get("stories", []):
                ps = story.get("paragraphs", [])
                if len(ps) != 1:
                    continue
                tt = _clean(ps[0].get("t", ""))
                if tt not in pn_labels:
                    continue
                fbs = story.get("fb") or []
                pgs = story.get("pg") or []
                if len(fbs) != 1 or len(pgs) != 1:
                    continue
                pe2 = pages_inv.get(str(pgs[0]))
                if not pe2:
                    continue
                b = fbs[0]
                lab_geo.append((pe2.get("side"),
                                round(b[3] - b[1], 2), round(b[2] - b[0], 2),
                                tt, pe2.get("p")))
            lefts = [(w, h) for sd, w, h, _t, _p in lab_geo if sd == "L"]
            lr_bad = []
            for sd, w, h, tt, pnum in lab_geo:
                if sd != "R":
                    continue
                fam = [lw for lw, lh in lefts if abs(lh - h) <= 1.0]
                if fam and abs(fam[0] - w) > 0.3:
                    lr_bad.append(f"p{pnum} '{tt}' 폭 {w} vs 왼쪽 {fam[0]}")
                elif not fam:
                    fam_h = [(lw, lh) for lw, lh in lefts
                             if abs(lw - w) <= 1.0]
                    if fam_h and abs(fam_h[0][1] - h) > 0.3:
                        lr_bad.append(
                            f"p{pnum} '{tt}' 높이 {h} vs 왼쪽 {fam_h[0][1]}")
            stats["label_frame_lr_bad"] = len(lr_bad)
            if lr_bad:
                msg = (f"[라벨프레임기하] 지문번호 라벨 프레임 좌/우 크기 "
                       f"불일치 {len(lr_bad)}건: " + " | ".join(lr_bad[:4]))
                (critical if cleanup_delete else warnings).append(msg)

        # ── G28③ 고아 간지 스프레드 (W23 r13 — F2) ──────────────────────
        # 간지 라벨 뒤에 다음 간지/문서 끝까지 플로우 콘텐츠 페이지가 하나도
        # 없으면 그 간지는 사용되지 않는 섹션의 잔재다 (job 6c1430c3 실증:
        # '고2 모의고사/26년 3월 짤지문' 간지 스프레드 p34~35 — 짤지문
        # 섹션은 v2가 콘텐츠를 배치하지 않는 템플릿 영역이라 delete 모드가
        # 내용 페이지를 전부 지운 뒤에도 라벨만 남는다. 이 라벨 페이지는
        # 섹션 마스터(O)가 적용돼 있어 마스터-없음 기준의 간지 판정/갱신을
        # 전부 비껴간다 — [원본]워크북_C p263 실측). 라벨 후보 = 단일 페이지
        # 비-플로우 스토리 + 2단락 이상 + 첫 단락 한글 + 전체 40자 미만
        # (실행기 removeOrphanDividers와 동일 부류 — 마스터 불문).
        # delete 모드(스프레드 삭제가 실행기 계약)는 critical, 아니면
        # warning (v1/M-모드 실물도 잔존 관행 — 소급은 지목만).
        page_ord = {str(e.get("p")): i
                    for i, e in enumerate(dump.get("pages") or [])}
        # W24 r14 (수능특강 문제 내지 opt-in — page_cleanup.divider_solo):
        # 다강 셸 간지는 'N강' 단독 단락 1개 ([원본]수능특강(문제) p27
        # '2강' 실측) — opt-in 플랜에 한해 단락 1개 라벨도 후보로 본다
        # (실행기 isDividerLabelLike와 동일 판정 부류. supp/본가 무영향).
        allow_solo = bool(cleanup_op.get("divider_solo"))
        label_cands = {}
        for story in dump.get("stories", []):
            pgs = story.get("pg") or []
            if len(pgs) != 1 or str(pgs[0]) not in page_ord:
                continue
            ps = story.get("paragraphs", [])
            if len(ps) < 2 and not (
                    allow_solo and len(ps) == 1
                    and re.match(r"^\d+\s*강$",
                                 _clean(ps[0].get("t", "")))):
                continue
            whole = _clean("".join(p.get("t", "") for p in ps))
            if not whole or len(whole) > 40:
                continue
            t0 = _clean(ps[0].get("t", ""))
            if not _RE_HANGUL.search(t0):
                continue
            if any(_clean(p.get("t", "")) in plan_texts
                   for p in ps if len(_clean(p.get("t", ""))) >= 4):
                continue          # 플로우 콘텐츠(원고 단락)와 겹침 — 제외
            label_cands[page_ord[str(pgs[0])]] = (str(pgs[0]), t0)
        content_ord = sorted(page_ord[p] for p in content_pages
                             if p in page_ord)
        if not content_ord:
            label_cands = {}      # 콘텐츠 페이지 0 (합성 덤프/빈 플랜) — 생략
        orphan_div = []
        for oi in sorted(label_cands):
            nxt = [x for x in label_cands if x > oi]
            hi = min(nxt) if nxt else len(page_ord)
            if not any(oi < c < hi for c in content_ord):
                pname, t0 = label_cands[oi]
                orphan_div.append(f"p{pname} 「{t0[:20]}」")
        stats["orphan_dividers"] = len(orphan_div)
        if orphan_div:
            msg = (f"[파트경계] 고아 간지 {len(orphan_div)}개 — 뒤따르는 "
                   f"콘텐츠 없음 (스프레드 삭제 대상): "
                   + " | ".join(orphan_div[:5]))
            (critical if cleanup_delete else warnings).append(msg)

    # ── G29 글리프 커버리지 (W23 r13 — F3) ───────────────────────────────
    # ① 아래첨자 인쇄 매핑(plan.SUBSCRIPT_PRINT_TABLE) 등재 문자의 출력
    #    잔존 = critical — 현행 플랜은 이 문자를 ASCII 숫자+아래첨자 서식
    #    run으로 치환하므로 잔존 = 매핑 미적용 출력 (G10 확장의 PUA 테이블
    #    과 동일 패턴. job 6c1430c3 소급: CO₂의 U+2082 151건이 글리프 없는
    #    폰트로 인쇄 — 사용자 지목 결함).
    # ② 그 외 특수문자(U+2000~2BFF, PUA 제외)는 덤프의 스타일→폰트 매핑
    #    (style_fonts/fonts — W23 확장 필드)과 폰트 파일 cmap 실측으로
    #    '적용 폰트가 글리프 미지원'만 warning 지목 (근거 없는 자동 치환
    #    금지 — PUA(G10)와 별개의 '폰트 커버리지' 부류). 폰트 정보 없는
    #    구버전 덤프는 ②를 생략한다 (fail-open).
    sub_resid = {}
    for t, _s in _dump_paras(dump):
        for ch in t:
            if ch in SUBSCRIPT_PRINT_TABLE:
                sub_resid[ch] = sub_resid.get(ch, 0) + 1
    stats["subscript_residue"] = sum(sub_resid.values())
    if sub_resid:
        # 치환된 플랜(등재 문자 0)의 출력에 잔존 = 매핑 미적용 = critical.
        # 플랜 자체에 등재 문자가 남은 경우(구플랜 소급 / 치환 미지원 계열
        # — 세로 등)는 warning 지목 (G3/G4의 'op 사용 시 critical' 패턴 —
        # 다른 계열의 정당한 출력을 false-critical로 깨지 않는다).
        plan_has_registered = any(
            ch in (p.get("t") or "")
            for fl in plan.get("flows", [])
            for u in fl.get("units", [])
            for p in (u["paras"] if isinstance(u, dict) else u)
            for ch in SUBSCRIPT_PRINT_TABLE)
        det = ", ".join(f"'{c}'(U+{ord(c):04X}) {n}건"
                        for c, n in sorted(sub_resid.items()))
        msg = (f"[글리프커버리지] 아래첨자 인쇄 매핑 등재 문자 잔존 — "
               f"폰트 글리프 없음 = tofu/미표시: {det}")
        (warnings if plan_has_registered else critical).append(msg)
    # ①b 글리프 인쇄 매핑(plan.GLYPH_PRINT_TABLE — ❮❯→〈〉, W30 후속)
    #    등재 문자의 출력 잔존 — ①과 동일 패턴: 치환된 현행 플랜(등재
    #    문자 0)의 출력에 잔존 = 매핑 미적용 = critical, 플랜 자체에 등재
    #    문자가 남은 경우(구플랜/구출력 소급)는 warning 지목.
    glyph_resid = {}
    for t, _s in _dump_paras(dump):
        for ch in t:
            if ch in GLYPH_PRINT_TABLE:
                glyph_resid[ch] = glyph_resid.get(ch, 0) + 1
    stats["glyph_residue"] = sum(glyph_resid.values())
    if glyph_resid:
        plan_has_glyph = any(
            ch in (p.get("t") or "")
            for fl in plan.get("flows", [])
            for u in fl.get("units", [])
            for p in (u["paras"] if isinstance(u, dict) else u)
            for ch in GLYPH_PRINT_TABLE)
        det = ", ".join(f"'{c}'(U+{ord(c):04X}) {n}건"
                        for c, n in sorted(glyph_resid.items()))
        msg = (f"[글리프커버리지] 글리프 인쇄 매핑 등재 문자 잔존 — "
               f"폰트 글리프 없음 = tofu/미표시: {det}")
        (warnings if plan_has_glyph else critical).append(msg)
    style_fonts = {e.get("s"): (e.get("f") or "", e.get("fs") or "")
                   for e in dump.get("style_fonts") or []}
    font_locs = {}
    for e in dump.get("fonts") or []:
        font_locs[str(e.get("n") or "")] = e.get("loc") or ""
    if style_fonts and font_locs:
        from core.fontcov import font_covers
        uncov = {}
        for story in dump.get("stories", []):
            for p in story.get("paragraphs", []):
                t = p.get("t", "")
                risky = {ch for ch in t
                         if 0x2000 <= ord(ch) <= 0x2BFF
                         and not _is_pua(ch)
                         and ch not in SUBSCRIPT_PRINT_TABLE
                         and ch not in GLYPH_PRINT_TABLE}
                if not risky:
                    continue
                sname = p.get("s") or ""
                fam, fsty = style_fonts.get(sname, ("", ""))
                loc = (font_locs.get(f"{fam}\t{fsty}")
                       or font_locs.get(fam))
                if not loc:
                    continue
                for ch in risky:
                    if font_covers(loc, ch) is False:
                        key = (ch, sname, fam)
                        uncov[key] = uncov.get(key, 0) + t.count(ch)
        stats["font_uncovered"] = sum(uncov.values())
        if uncov:
            det = " | ".join(
                f"'{ch}'(U+{ord(ch):04X}) ×{n} — 스타일 「{sn}」 폰트 "
                f"「{fm}」" for (ch, sn, fm), n in sorted(uncov.items())[:3])
            warnings.append(
                f"[글리프커버리지] 적용 폰트가 글리프 미지원 "
                f"{sum(uncov.values())}건 (cmap 실측): {det}")

    # ── G30 문제단위킵 (W23 r13 — F4) ────────────────────────────────────
    # 사용자 확정 스펙: 한 문제(발문+지문+선지 전체)가 오른쪽 페이지에서
    # 잘려 다음 장(스프레드 넘김)으로 이어지면 안 된다 — 왼쪽→오른쪽은
    # 허용. 문제 경계 = question_keep 계약(q_styles)의 발문/인트로 스타일
    # 단락. 계약 없는 구출력은 스타일 leaf 휴리스틱('실전문제 번호'/'다음
    # 글을 읽고')으로 소급 지목 (warning). 단락→페이지는 덤프 W23 확장
    # 필드 fp(프레임별 페이지 이름 — fc와 병렬)로 독립 재계산. 시작이
    # 왼쪽인데 스프레드를 넘는 문제(한 문제가 2페이지 초과)는 밀어도 해소
    # 불가 — warning 지목 (실행기도 경고만).
    qk = (plan.get("question_keep")
          if isinstance(plan.get("question_keep"), dict) else {})
    qk_styles = set(qk.get("q_styles") or [])

    def _is_q_boundary_style(s):
        if qk_styles:
            return s in qk_styles
        return "실전문제 번호" in s or "다음 글을 읽고" in s

    qk_steps = sorted((qk.get("flows") or {}).keys()) or ["step3"]
    page_ord30 = {str(e.get("p")): i
                  for i, e in enumerate(dump.get("pages") or [])}
    pages_inv30 = {str(e.get("p")): e for e in dump.get("pages") or []}
    keep_viol = []
    keep_manual = []
    keep_nodump = False
    for fl in plan.get("flows", []):
        if fl.get("step") not in qk_steps:
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        ps = story.get("paragraphs", [])
        bounds = [i for i, p in enumerate(ps)
                  if _is_q_boundary_style(p.get("s") or "")]
        if not bounds:
            continue
        fc = story.get("fc") or []
        fp = story.get("fp") or []
        if not fc or not fp or not page_ord30:
            keep_nodump = True
            continue
        frames = sorted((c, str(pg)) for c, pg in zip(fc, fp)
                        if isinstance(c, int) and c >= 0 and pg)
        if not frames:
            continue
        offs = []
        cum = 0
        for p in ps:
            offs.append(cum)
            cum += len(p.get("t", ""))

        def _pg_of(off, _frames=frames):
            name = None
            for c, pg in _frames:
                if c <= off:
                    name = pg
                else:
                    break
            return name

        for bi, si in enumerate(bounds):
            ei = (bounds[bi + 1] - 1 if bi + 1 < len(bounds)
                  else len(ps) - 1)
            sp = _pg_of(offs[si])
            ep = _pg_of(offs[ei] + max(0, len(ps[ei].get("t", "")) - 1))
            if sp is None or ep is None:
                continue
            so, eo = page_ord30.get(sp), page_ord30.get(ep)
            if so is None or eo is None:
                continue
            if (eo + 1) // 2 <= (so + 1) // 2:
                continue          # 같은 스프레드 안 (L→R 허용 포함)
            head = _clean(ps[si].get("t", ""))[:28]
            entry = f"{fl['step']} p{sp}→p{ep} 「{head}」"
            if (pages_inv30.get(sp) or {}).get("side") == "R":
                keep_viol.append(entry)
            else:
                keep_manual.append(entry)
    stats["question_keep_viol"] = len(keep_viol)
    if keep_nodump and qk:
        warnings.append("[문제단위킵] 덤프에 프레임 페이지 정보 없음"
                        "(구버전 덤프) — 재덤프 필요")
    if keep_viol:
        msg = (f"[문제단위킵] 오른쪽 페이지→다음 장 걸침 문제 "
               f"{len(keep_viol)}건 (문제 전체를 다음 페이지로 밀어야 함): "
               + " | ".join(keep_viol[:5]))
        (critical if qk else warnings).append(msg)
    if keep_manual:
        warnings.append(
            f"[문제단위킵] 한 문제가 스프레드 초과 {len(keep_manual)}건 — "
            f"밀기로 해소 불가 (수동 확인): " + " | ".join(keep_manual[:3]))

    # ── G41 발문 고아 (W40 결함 2) ───────────────────────────────────────
    # 프레임 하단에 발문만 남고 문제 본문이 다음 프레임에서 시작 — 발문
    # 단락의 프레임과 다음 유의 단락의 프레임을 fc(프레임 첫 문자 인덱스)
    # 실측으로 대조한다 (발문+본문 1줄 케이스는 라인 정보가 덤프에 없어
    # 실행기 enforceStemKeep이 담당 — 게이트는 발문 단독 고아를 잡는다).
    # stem_keep 계약 플랜은 critical, 구출력 소급 warning.
    stem_keep_contract = bool(qk.get("stem_keep")) if qk else False
    stem_orphans = []
    for fl in plan.get("flows", []):
        if fl.get("step") not in qk_steps:
            continue
        story = _find_flow_story(dump, fl)
        if story is None:
            continue
        ps = story.get("paragraphs", [])
        fc = [c for c in story.get("fc") or []
              if isinstance(c, int) and c >= 0]
        if not fc or len(fc) < 2:
            continue
        fcs = sorted(fc)

        def _frame_of(off, _fcs=fcs):
            fi = -1
            for x, c in enumerate(_fcs):
                if c <= off:
                    fi = x
                else:
                    break
            return fi

        offs = []
        cum = 0
        for p in ps:
            offs.append(cum)
            cum += len(p.get("t", ""))
        for i, p in enumerate(ps):
            if not _is_q_boundary_style(p.get("s") or ""):
                continue
            body = next((j for j in range(i + 1, len(ps))
                         if _clean(ps[j].get("t", ""))
                         and not _is_q_boundary_style(
                             ps[j].get("s") or "")), None)
            if body is None:
                continue
            stem_last = offs[i] + max(0, len(ps[i].get("t", "")) - 1)
            f_stem = _frame_of(stem_last)
            f_body = _frame_of(offs[body])
            if f_stem >= 0 and f_body > f_stem:
                stem_orphans.append(_clean(p.get("t", ""))[:30])
    stats["stem_orphans"] = len(stem_orphans)
    if stem_orphans:
        msg = (f"[발문고아] 프레임 하단 발문 단독 잔류 "
               f"{len(stem_orphans)}건 (본문이 다음 프레임에서 시작): "
               + " | ".join(stem_orphans[:4]))
        (critical if stem_keep_contract else warnings).append(msg)

    # ── G42 다열 선지 열 정렬 (W40 결함 1) ───────────────────────────────
    # 연속 탭 선지 단락 그룹에서 항목 행(원문자 시작)의 탭 셀 시작 오프셋
    # (덤프 W40 확장 필드 cx)이 열별로 일치해야 한다 (±0.3mm). 그룹이
    # 프레임 경계에서 갈라질 수 있어 행 시작(cx[0])이 1mm 이내인 부분
    # 그룹끼리만 대조. choice_tabs 계약 플랜은 critical, 구덤프(cx 없음)는
    # 검사 생략 + 계약 시 재덤프 경고.
    tab_misaligned = []
    cx_seen = False
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        i = 0
        while i < len(ps):
            s = ps[i].get("s") or ""
            if "선지" not in s or "\t" not in ps[i].get("t", ""):
                i += 1
                continue
            j = i
            rows = []
            while j < len(ps):
                sj = ps[j].get("s") or ""
                if "선지" not in sj or "\t" not in ps[j].get("t", ""):
                    break
                t = _clean(ps[j].get("t", ""))
                cx = ps[j].get("cx")
                if cx:
                    cx_seen = True
                if t[:1] in "①②③④⑤" and cx and len(cx) >= 2:
                    rows.append((t, cx))
                j += 1
            # 부분 그룹 (cx[0] 1mm 이내) 별 열 오프셋 대조
            sub = {}
            for t, cx in rows:
                key = round(cx[0])
                sub.setdefault(key, []).append((t, cx))
            for key, srows in sub.items():
                if len(srows) < 2:
                    continue
                ncol = min(len(cx) for _, cx in srows)
                for c in range(1, ncol):
                    vals = [cx[c] for _, cx in srows]
                    if max(vals) - min(vals) > 0.3:
                        tab_misaligned.append(
                            f"「{srows[0][0][:20]}」열{c} 편차 "
                            f"{round(max(vals) - min(vals), 2)}mm")
                        break
            i = max(j, i + 1)
    stats["choice_tab_misaligned"] = len(tab_misaligned)
    ct_contract = bool(plan.get("choice_tabs"))
    if tab_misaligned:
        msg = (f"[선지열정렬] 다열 선지 열 불일치 {len(tab_misaligned)}그룹: "
               + " | ".join(tab_misaligned[:4]))
        (critical if ct_contract else warnings).append(msg)
    elif ct_contract and not cx_seen:
        warnings.append("[선지열정렬] 덤프에 탭 셀 오프셋(cx) 없음"
                        "(구버전 덤프) — 재덤프 필요")

    # ── G43 빈칸 프레임 경계 초과 (W40 결함 6) ───────────────────────────
    # 밑줄 빈칸 런 라인이 프레임 오른쪽 내변을 넘음 (덤프 W40 확장 필드
    # hox — 실측). blank_fit 계약 플랜에서 잔존은 자간 한도 초과분(실행기
    # [경고] 짝) 또는 보정 실패 — 사람 확인 지목 (warning. G33/시각 검수
    # 정합 — 경계 밖 텍스트는 시각층에서도 잡힌다).
    hox = dump.get("hox") or []
    stats["blank_overflow_lines"] = len(hox)
    if hox:
        det = " | ".join(
            f"p{e.get('p')} +{e.get('over')}mm 「{(e.get('t') or '')[:16]}」"
            for e in hox[:4])
        warnings.append(
            f"[빈칸경계] 밑줄 빈칸 라인 프레임 오른쪽 초과 {len(hox)}건"
            + (" (자간 한도 내 해소 불가 — 수동 확인)"
               if plan.get("blank_fit") else "") + ": " + det)

    # ── G31 프레임 결손 (W30-r15 — 결함 6) ───────────────────────────────
    # 스토리가 흐르는 페이지의 '그 스토리 프레임 수'가 스토리 대다수
    # 페이지(모드, 2 이상 = 다단 템플릿)보다 적은 '중간' 페이지 — 오버플로우
    # 페이지 확장(expandStoryOverflow)이 마지막 프레임 1개만 복제해 2단
    # 템플릿 페이지를 1단으로 만든 결함 (376b34d0 실증: p95~97 프레임 1개,
    # 템플릿 O-마스터는 페이지당 2단 2프레임). 첫/마지막 페이지는 제외 —
    # 섹션 중간 시작/스레드 절단(빈 꼬리 프레임 분리)의 정상 감소 (전체
    # 코퍼스 덤프 sweep에서 중간 결손은 376b34d0뿐임을 실측). 오버플로우
    # 확장이 동작하는 계약 플랜(question_keep/page_cleanup)은 critical.
    frame_deficit = []
    for story in dump.get("stories", []):
        fp = [str(p) for p in story.get("fp") or []]
        if not fp:
            continue
        order = []
        for p in fp:
            if p not in order:
                order.append(p)
        if len(order) < 3:
            continue
        cnt = {}
        for p in fp:
            cnt[p] = cnt.get(p, 0) + 1
        mode_cnt = {}
        for p in order:
            mode_cnt[cnt[p]] = mode_cnt.get(cnt[p], 0) + 1
        mode = max(mode_cnt, key=lambda k: (mode_cnt[k], k))
        if mode < 2:
            continue
        bad = [p for p in order[1:-1] if cnt[p] < mode]
        if bad:
            frame_deficit.append(
                f"스토리 {story.get('idx')} p" + ", p".join(bad[:6])
                + f" (프레임 {min(cnt[p] for p in bad)}개 < 모드 {mode}개)")
    stats["frame_deficit_stories"] = len(frame_deficit)
    if frame_deficit:
        msg = (f"[프레임결손] 다단 스토리 중간 페이지 프레임 결손 "
               f"{len(frame_deficit)}건: " + " | ".join(frame_deficit[:4]))
        (critical if (plan.get("question_keep") or cleanup_delete)
         else warnings).append(msg)

    # ── G5 step2_a1 상단 / step2_a1_btm 하단 기하 검사 ───────────────────
    flows = {fl["step"]: fl for fl in plan.get("flows", [])}
    if "step2_a1" in flows and "step2_a1_btm" in flows:
        st_top = _find_story_with_text(dump, _flow_probe_text(flows["step2_a1"]))
        st_btm = _find_story_with_text(dump,
                                       _flow_probe_text(flows["step2_a1_btm"]))
        if st_top and st_btm and st_top.get("b") and st_btm.get("b"):
            shared = set(st_top.get("pg") or []) & set(st_btm.get("pg") or [])
            if shared and st_top["b"][0] >= st_btm["b"][0]:
                msg = ("[상하반전] step2_a1(상단)이 step2_a1_btm(하단)보다 "
                       f"아래에 배치됨 (top {st_top['b'][0]} ≥ "
                       f"{st_btm['b'][0]})")
                (critical if pos_used else warnings).append(msg)
                stats["a1_swapped"] = True
            else:
                stats["a1_swapped"] = False
        elif st_top and st_btm:
            warnings.append("[상하배치] 덤프에 프레임 좌표 없음(구버전 덤프)"
                            " — 상/하단 검사 생략")

    # ── G19 어법수정 원고 step3 혼입 (W17 c11) ───────────────────────────
    # step3(실전문제) 스토리에 "1[asked]" 정답 괄호 표기가 다량이면
    # 구6스텝 'Step3 어법수정' 오라우팅 — 실전문제/변형 pool에는 이 표기가
    # 없다. step1_c2(빈칸어휘 정답지)는 같은 표기를 정당하게 쓰므로
    # 반드시 step3 플로우 스토리로 한정한다.
    if "step3" in flows:
        st3_story = _find_story_with_text(
            dump, _flow_probe_text(flows["step3"]))
        if st3_story is not None:
            sig_hits = sum(
                len(_RE_GRAMMAR_FIX_SIG.findall(_clean(p.get("t", ""))))
                for p in st3_story.get("paragraphs", []))
            stats["grammar_fix_sig_hits"] = sig_hits
            if sig_hits >= 5:
                critical.append(
                    f"[어법수정혼입] step3 스토리에 어법수정 정답 괄호 "
                    f"표기 {sig_hits}개 — 어법수정 원고가 실전문제로 "
                    f"오라우팅된 상태 (파일명 라우팅 확인)")

    # ── G9 미사용 업로드 원고 (W13 — 부분 침묵 유실 보고)
    #    + G16 스텝원고 미사용 critical 승격 (W17 c11) ─────────────────────
    if uploads_dir and os.path.isdir(uploads_dir):
        expected_unused, suspicious = find_unused_uploads(content,
                                                          uploads_dir)
        stats["unused_uploads_expected"] = expected_unused
        stats["unused_uploads"] = suspicious
        wt = ((content or {}).get("workbook_type") or "")
        tokens = (_STEP_CONTENT_TOKENS_EBS if wt == "EBS"
                  else _STEP_CONTENT_TOKENS)
        # W18 c17 — 같은 콘텐츠 가족의 파일이 이미 소비된 경우(예: 'Step1 C2
        # 빈칸어휘 정답지' 소비 + 'Step1 C2 빈칸어휘(개정)' 병존)는 부분
        # 침묵 유실이 아니라 변형본 짝 — critical 승격에서 제외(G9 warning
        # 유지). G16의 본래 표적은 '그 가족이 아예 미소비'(W17 c11).
        used_names = {_norm_fname(sd["filename"])
                      for sd in steps.values()
                      if isinstance(sd, dict) and sd.get("filename")}

        def _family_consumed(f):
            toks = [tok for tok in tokens if tok in _norm_fname(f)]
            return toks and all(any(tok in u for u in used_names)
                                for tok in toks)

        step_unused = [f for f in suspicious
                       if any(tok in _norm_fname(f) for tok in tokens)
                       and not _family_consumed(f)]
        other_unused = [f for f in suspicious if f not in step_unused]
        stats["unused_step_manuscripts"] = step_unused
        if step_unused:
            critical.append(
                f"[스텝원고미사용] 현행 스텝이 소화 가능한 원고 "
                f"{len(step_unused)}개가 사용되지 않음 (부분 침묵 유실): "
                + " | ".join(step_unused[:5]))
        # 배치 A (W33): warning → critical 승격 — 미라우팅 원고는 부분
        # 침묵 유실이므로 반침묵(경고 무시 가능)을 금지한다 (감사 §9,
        # 정답/답지류는 expected_unused로 이미 제외). 예외: 구6스텝
        # '(구6스텝 미대응)' 마커 — 현행 스텝이 소화 못 하는 종류임을
        # 선라우팅이 명시한 파일 (W17 설계: 운영 판단 위임, warning 유지).
        legacy_unmapped = [f for f in other_unused if "구6스텝 미대응" in f]
        promoted_unused = [f for f in other_unused
                           if f not in legacy_unmapped]
        if legacy_unmapped:
            warnings.append(
                f"[미사용원고] {len(legacy_unmapped)}개 파일이 어느 스텝에도 "
                f"사용되지 않음 (구6스텝 미대응 — 운영 판단): "
                + " | ".join(legacy_unmapped[:5]))
        if promoted_unused:
            critical.append(
                f"[미사용원고] {len(promoted_unused)}개 파일이 어느 스텝에도 "
                f"사용되지 않음 (침묵 유실 금지 — 파일명 규칙 확인): "
                + " | ".join(promoted_unused[:5]))

    # ── G6 파싱 계층: 구조적 헤더 후보 미인식 (W31 — 파서와 같은 눈) ─────
    # 플랜 빌더(plan._step_header_detection)와 동일한 구조 우선 인식기를
    # 사용한다. 침묵 실패(강한 후보 2+ / 인식 0~1)는 critical — 빌더가
    # 먼저 HeaderSilenceError로 조판을 중단하므로 여기 도달은 구플랜 재검사
    # 케이스다. 부분 미인식은 warning 유지.
    for key in _HEADER_STEPS:
        sd = steps.get(key)
        if not isinstance(sd, dict):
            continue
        texts = [(p.get("text") or "") for p in sd.get("paragraphs") or []]
        if not texts:
            continue
        det = detect_headers(
            texts,
            legacy=lambda t: (is_header_line(_norm_header(t))
                              or is_a1_header(t)
                              or _norm_header(t).startswith("[")))
        if not det.candidates and not det.suppressed_strong:
            continue    # W50: 필터 탈락 강신호(suppressed)는 침묵 검사 대상
        if det.silent():
            critical.append(
                f"[헤더미인식] {key}: 구조적 헤더 후보 "
                f"{len(det.candidates)}개(강한 후보 "
                f"{len(det.strong_candidates())}개) 중 인식 "
                f"{len(det.header_idx)}개 — 새 헤더 형식, 통짜 유닛 위험:\n"
                + det.describe())
        elif not det.recognized_candidates():
            warnings.append(
                f"[헤더미인식] {key}: 구조적 헤더 후보 "
                f"{len(det.candidates)}개 중 인식 0개 — 새 헤더 형식 의심: "
                + det.candidates[0]["t"][:40])

    # ── G35 [정답누출] (W53) — 해설/원문변형 마커가 출력에 인쇄됨 ────────
    # 인라인 정답형 원고(아잉카류)의 정답 표가 스트립을 비껴가면 '[해설]'
    # 블록·'⚹ 원문 변형' 표기·원문→수정(→) 쌍이 문제면에 그대로 인쇄된다
    # (475e4d58 2강 실증: 발문 '…문장은?'이 발문 판정을 비껴가 무관문장
    # 정답 표 누출 — AI 검수는 CLI 미로그인으로 죽어 있어 아무도 못 잡음).
    # AI 검수와 별개로 결정론 게이트가 마커를 직접 지목한다.
    ans_leak = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if ("[해설]" in tt or re.search(r"[⚹*✱]?\s*원문\s*변형", tt)
                or tt.startswith("모범답안") or "모범 답안" in tt[:12]):
            ans_leak.append(tt[:60])
            continue
        # 원문→수정 쌍의 수정문: '→' 시작 + 긴 영문 문장 (475e4d58 실증 —
        # [해설] 마커 셀은 각주 분류로 이미 제거되고 수정문만 살아남는다).
        # 답란 '→ m____'/'→\t' 류는 영단어가 적어 안 걸리고, 빈칸 라벨
        # ((ㄱ)/(A) 류)이 있는 줄은 채울 문제 재료라 제외.
        if tt.startswith("→") and "_" not in tt \
                and not re.search(r"\(\s*[ㄱ-ㅎA-E가-힣]\s*\)", tt) \
                and len(re.findall(r"[A-Za-z][A-Za-z']{2,}", tt)) >= 8:
            ans_leak.append(tt[:60])
    stats["answer_leak_markers"] = len(ans_leak)
    if ans_leak:
        critical.append(f"[정답누출] {len(ans_leak)}개 단락에 해설/원문변형 "
                        f"마커가 인쇄됨 — 문제면에 정답 노출: "
                        + " | ".join(sorted(set(ans_leak))[:5]))

    # ── G34 [아이콘누락] (W50) — 플랜 아이콘 지시 vs 출력 앵커(￼) 수 ────
    # place 모드 아이콘(어법OX TF 버튼)이 링크 파일 접근 실패로 문항마다
    # 조용히 0을 리턴해 90개 전부 빠졌는데 어떤 게이트도 안 잡았다
    # (2026-08-11 de909e4d 실증). 플로우별 아이콘 지시 수와 매핑 스토리의
    # 인라인 앵커 문자(U+FFFC) 수를 대조한다. 템플릿 유래 앵커가 이미
    # 있을 수 있어 초과는 허용, 미달만 지목한다.
    icon_missing = []
    for fl in plan.get("flows", []):
        want = 0
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                if p.get("icon"):
                    want += 1
        if not want:
            continue
        story = _find_flow_story(dump, fl)
        if not story:
            continue    # 스토리 미매핑은 다른 게이트(G7 등) 소관
        got = sum((p.get("t") or "").count("￼")
                  for p in story.get("paragraphs", []))
        stats[f"icons_{fl.get('step')}"] = f"{got}/{want}"
        if got < want:
            icon_missing.append(
                f"{fl.get('step')}: 앵커 {got}/{want}")
    if icon_missing:
        critical.append("[아이콘누락] 플랜 아이콘 지시 대비 출력 앵커 미달 "
                        "(place 실패/링크 파일 접근 불가 의심): "
                        + " | ".join(icon_missing))

    return {"ok": not critical, "critical": critical, "warnings": warnings,
            "stats": stats}


# ── W68: 원고 교차검증 (조판 '전' 단계 — 사용자 눈 대신 파이프라인이 잡는다) ──
# 사용자 지적 2026-08-15: "지문번호 인식을 못하는 건 언제까지 잡아야 하나."
# 라벨/파일 형식은 강마다 바뀌므로 형식을 맞추는 싸움은 끝나지 않는다.
# 대신 **형식과 무관한 불변식**을 조판 전에 검사해, 원고 사고와 인식 실패가
# 완제품이 아니라 로그에서 걸리게 한다:
#   M1 지문 기반 스텝인데 지문(긴 영어 본문)이 하나도 없다 → 잘못된 파일
#      (11강 실증: 빈칸어휘가 '단어 목록만 있는 정답지'로 조판됨)
#   M2 어떤 스텝의 지문 어휘가 다른 스텝들과 거의 안 겹친다 → 다른 교재/단원
#      원고 혼입 (11강 실증: 빈칸어휘 문제지가 '공통영어2 능률' 교과서 파일)
#   M3 스텝별 지문 수가 서로 크게 다르다 → 어느 한 스텝의 지문번호 인식 실패
#      (11강 실증: 어휘선택 5지문이 1유닛으로 뭉침)
_PASSAGE_STEPS = ("step1_a1", "step1_a1_2", "step1_a2", "step1_b1",
                  "step1_b2", "step1_c1", "step1_c2", "step2_a1",
                  "step2_b1", "step2_c1", "step2_c2")
_RE_M_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")


def _m_passages(step_data):
    """스텝 원고의 '지문 단락'(영어 12단어 이상) 목록."""
    out = []
    for p in (step_data or {}).get("paragraphs", []) or []:
        t = (p.get("text") or "")
        if len(_RE_M_WORD.findall(t)) >= 12:
            out.append(t)
    return out


def _m_vocab(texts):
    v = set()
    for t in texts:
        for w in _RE_M_WORD.findall(t):
            if len(w) >= 5:
                v.add(w.lower())
    return v


def inspect_manuscript_consistency(content, log=None):
    """원고 자체의 정합성 검사 (조판 전). → (critical, warnings, stats)"""
    steps = (content or {}).get("steps") or {}
    critical, warnings, stats = [], [], {}
    per = {}
    for key in _PASSAGE_STEPS:
        sd = steps.get(key)
        if not isinstance(sd, dict) or not sd.get("paragraphs"):
            continue
        per[key] = _m_passages(sd)

    # M1 — 지문이 하나도 없는 지문 기반 스텝
    empty = [k for k, v in per.items() if not v]
    stats["manuscript_no_passage"] = len(empty)
    for k in empty:
        critical.append(
            f"[원고이상] {k}: 원고에 지문(영어 본문)이 하나도 없습니다 — "
            f"파일 '{(steps.get(k) or {}).get('filename', '')}'이(가) "
            f"정답 목록/다른 자료일 수 있습니다 (원고 확인 필요)")

    # M2 — 다른 스텝들과 지문 어휘가 거의 안 겹치는 스텝
    vocab = {k: _m_vocab(v) for k, v in per.items() if v}
    if len(vocab) >= 3:
        for k, vk in vocab.items():
            others = set()
            for k2, v2 in vocab.items():
                if k2 != k:
                    others |= v2
            if not vk or not others:
                continue
            share = len(vk & others) / float(len(vk))
            stats[f"vocab_share_{k}"] = round(share, 3)
            if share < 0.15:
                critical.append(
                    f"[원고이상] {k}: 지문 어휘가 다른 스텝과 "
                    f"{int(share * 100)}%%밖에 겹치지 않습니다 — 다른 "
                    f"강/교재 원고 혼입 의심 (파일 "
                    f"'{(steps.get(k) or {}).get('filename', '')}')")

    if log:
        for m in critical:
            log("⚠️ " + m)
        for m in warnings:
            log("⚠️ " + m)
    return critical, warnings, stats


# M3 — 스텝별 '유닛 수'(=지문 수) 편차. 지문 1개당 유닛 1개인 스텝들만 본다
# (문장배열/본문정리/영작은 지문당 문항이 여러 개라 제외). 여기서 어긋나면
# 그 스텝의 지문번호/블록 인식이 깨진 것이다 — 11강 실증: 어휘선택 계열이
# 5지문인데 1유닛(라벨 미인식)이었고, 어법 계열은 4로 정상이었다.
_ONE_UNIT_PER_PASSAGE = ("step1_a1", "step1_a1_2", "step1_a2", "step1_b2",
                         "step2_a1", "step2_a1_btm", "step2_b1", "step2_c1")


def inspect_plan_units(plan, log=None):
    """플랜의 스텝별 유닛 수 교차검증 → (critical, warnings, stats)"""
    critical, warnings, stats = [], [], {}
    counts = {}
    for fl in (plan or {}).get("flows", []) or []:
        step = fl.get("step")
        if step in _ONE_UNIT_PER_PASSAGE:
            counts[step] = len(fl.get("units") or [])
    stats["unit_counts"] = dict(counts)
    if len(counts) >= 3:
        vals = sorted(counts.values())
        mode = max(set(vals), key=vals.count)
        stats["unit_count_mode"] = mode
        odd = {k: n for k, n in counts.items() if abs(n - mode) > 1}
        if odd:
            critical.append(
                "[지문수불일치] 이 강의 지문은 %d개인데 " % mode
                + ", ".join("%s=%d" % (k, n) for k, n in sorted(odd.items()))
                + " — 해당 스텝의 지문번호/블록 인식 실패 (라벨 형식 확인)")
    if log:
        for m in critical:
            log("⚠️ " + m)
    return critical, warnings, stats
