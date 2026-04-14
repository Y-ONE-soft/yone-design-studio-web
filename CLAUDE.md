# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

영어 워크북 조판 자동화를 위한 **InDesign ExtendScript (.jsx)** 스크립트 모음입니다.
스크립트는 Adobe InDesign의 Scripts 패널 또는 `File > Scripts`에서 직접 실행됩니다.
빌드 도구, 패키지 매니저, 테스트 프레임워크가 없으며, 스크립트 자체가 곧 실행 단위입니다.

## 실행 환경

- **런타임**: Adobe InDesign ExtendScript (ES3 호환 JavaScript)
- **실행 방법**: InDesign 내 `Window > Utilities > Scripts` 패널에서 스크립트 더블클릭
- **디버그**: `#target indesign` 지시어가 있는 스크립트는 ExtendScript Toolkit(ESTK)에서도 실행 가능
- `.claude/settings.local.json`에 `osascript`, `python3` Bash 권한 허용됨

## 디렉터리 구조

```
워크북 조판 자동화/
├── 인디자인 스크립트/   ← 모든 .jsx 스크립트 (편집 대상)
├── 인디자인 파일/        ← .indd 소스 파일 (스크립트 실행 대상)
├── 원고/                 ← 원고 텍스트 파일
└── 테스트 파일/          ← 테스트용 PDF
```

## 스크립트 명명 규칙

`STEP{단계}{유형}{번호}.jsx`

- **단계**: `1` = STEP 01 단원, `2` = STEP 02 단원
- **유형**: `A`=어휘/어법 선택, `B`=내용정리/OX, `C`=빈칸/문장배열/영작
- 단락 스타일 그룹과 대응: `STEP 01` / `STEP 02`

## 스크립트별 역할

### STEP 1

| 스크립트 | 적용 스타일 그룹 | 주요 동작 |
|---|---|---|
| `STEP1A1.jsx` | STEP 01 | ❮/❯ 기호 → \[\], 프레임 브레이크, `A1_어휘 선택` 스타일 |
| `STEP1A2.jsx` | STEP 01 | `A2_OX문제` / `A2_본문 박스` + TF버튼 인라인 삽입 |
| `STEP1B1.jsx` | STEP 01 | `B1_내용 정리` 전체 적용, 하단 문제/선지/지문, 아이콘 인라인 |
| `STEP1B2.jsx` | STEP 01 | `B2_내용 종합 번호` / `B2_내용 종합 선지` / `A2_본문 박스` |
| `STEP1C1.jsx` | STEP 01 | 헤더 정규화, 문장 배열/하단/하단 지문 스타일, 화살표 아이콘 (완전판) |
| `STEP1C1_New.jsx` | STEP 01 | C1 간소판 — 하단·지문 처리 없이 배열 스타일 + 화살표만 |
| `STEP1C2.jsx` | STEP 01 | 머리말 제거 + 프레임 브레이크, `C2_빈칸 어휘` / `C2_빈칸 어휘 한글` |

### STEP 2

| 스크립트 | 적용 스타일 그룹 | 주요 동작 |
|---|---|---|
| `STEP2A1.jsx` | STEP 02 | 헤더 → `{…}` 형식 변환 + 프레임 브레이크, `A1_어법 선택` |
| `STEP2A1Practice.jsx` | STEP 02 | 헤더 삭제(변환 없음) + 프레임 브레이크, `A1_어법 선택 하단` |
| `STEP2B1.jsx` | STEP 02 | `B1_어법 OX` 전체 적용, 프레임 브레이크, TF버튼 인라인(링크 파일 방식) |
| `STEP2C1.jsx` | STEP 02 | 머리말 제거, `C1_빈칸 어법` / `C2_빈칸 어휘 한글` |
| `STEP2C2.jsx` | STEP 02 | `C2_영작 배열 번호` / `C2_영작 배열 보기`, 슬래시 기반 분류, 아이콘 |

### 유틸리티

| 스크립트 | 주요 동작 |
|---|---|
| `MergeTextbook.jsx` | .indd 파일 여러 개 페이지 병합 → PDF 내보내기 (UI 다이얼로그, `#target indesign`) |
| `MergeMockExam.jsx` | 모의고사 세로버전에서 6자리 문제코드(YYMMQQ) 기준 페이지 추출 → PDF |
| `_Debug_FolderCheck.jsx` | MergeMockExam 진단용 — 폴더 내 .indd 파일 파싱 결과 출력 |

## 공통 코딩 패턴

### 스토리 확보
모든 처리 단위는 InDesign Story입니다. 스크립트 진입부에서 반드시 확인:
```js
var story = app.selection[0].parentStory;
```

### Undo 그룹화
모든 변경은 단일 Undo 단위로 묶어야 합니다:
```js
app.doScript(function(){ /* 작업 */ },
    ScriptLanguage.JAVASCRIPT, undefined,
    UndoModes.ENTIRE_SCRIPT, "작업 이름");
```

### GREP 초기화 — 반드시 전후로 리셋
```js
app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
app.findGrepPreferences.findWhat = "...";
app.changeGrepPreferences.changeTo = "...";
story.changeGrep();
app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
```

### 단락 스타일 참조
```js
var g = doc.paragraphStyleGroups.itemByName("STEP 01");
var st = g.paragraphStyles.itemByName("A1_어휘 선택");
```

### 기본 단락 스타일 (로케일 안전)
한국어/영문 InDesign 양쪽 지원이 필요하므로 여러 이름으로 순차 탐색:
```js
// "$ID/NormalParagraphStyle" → "[기본 단락]" → "[Basic Paragraph]" 순으로 시도
```

### 문자 스타일 초기화
```js
story.characters.everyItem().appliedCharacterStyle = doc.characterStyles[0]; // [없음]
```

### 인라인 아이콘 삽입 패턴
문서 내 숨김 객체(`.label` 속성으로 식별)를 복제해 앵커로 삽입:
```js
var src = doc.allPageItems[i]; // label 확인
var clone = src.duplicate();
clone.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.INLINE_POSITION);
```
삽입 전 반드시 `src.locked = false`, 레이어 잠금 해제 후 복구 패턴 사용.

### 프레임 브레이크 삽입
```js
para.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
```
문단 배열은 삽입 후 인덱스가 변동되므로 **뒤에서 앞으로(역순)** 처리.

## 템플릿 레이블 목록

스크립트가 인라인 삽입에 사용하는 문서 내 숨김 객체의 `.label`:

| 레이블 | 사용 스크립트 | 용도 |
|---|---|---|
| `"TF 버튼"` | STEP1A2, STEP2B1 | T/F 버튼 이미지 (PNG 또는 링크 파일) |
| `"STEP1 문제아이콘"` | STEP1B1, STEP1C1 | 문제 번호 아이콘 |
| `"화살표 답지"` | STEP1C1, STEP1C1_New | 화살표 답지 아이콘 |
| `"STEP2 영작 답지"` | STEP2C2 | 영작 답지 아이콘 |

## 헤더 패턴 (머리말 정규식)

스크립트들이 공통으로 감지해 프레임 브레이크 후 삭제하는 머리말 형식:
- `1. L3-본문2` / `2. L1-p.17`
- `3. p22-no.01` / `4. p38-논술형 Practice`
- `5. p46-수능 대비 ANALYSIS`
- `Supplementary Reading`

STEP1C1/STEP2A1은 헤더를 **삭제하지 않고 `{본문1}` 형식으로 변환**합니다.

## 알려진 특이사항

- **`STEP1C2.jsx`**: 파일 내 동일 코드가 185번째 줄부터 중복 삽입되어 있음 (스크립트 실행에는 문제 없으나 관리상 주의)
- **`STEP1C1.jsx` vs `STEP1C1_New.jsx`**: 두 버전이 공존. `STEP1C1_New.jsx`는 하단/지문/발문 처리를 제거한 간소 버전
- **`STEP2B1.jsx`**: TF버튼을 `src.duplicate()` 방식이 아닌 `story.insertionPoints[ip.index].place(File(tfLinkPath))` 링크 배치 방식 사용 (다른 스크립트와 다름)
- ExtendScript는 ES3이므로 `let`/`const`/화살표 함수/템플릿 리터럴 사용 불가

---

## 수정 시 기존 로직 영향 금지 (필수)

**버그 수정 시 해당 문제 외의 기존 로직에 영향을 줘서는 안 된다.**

- 전체 로직을 재계획하는 경우가 아니라면, 현재 발생한 문제에 대한 수정만 추가
- 수정 전후로 다른 케이스(다른 원고, 다른 스크립트)가 영향받지 않는지 확인 후 적용
- A 원고로 동작하던 로직이 B 원고 수정으로 깨지는 패턴을 반복하지 않는다
- 수정 범위를 넘어서는 리팩터링/구조 변경은 사용자 승인 없이 금지

## 조판 엔진 개발 가이드라인

> 상세 가이드라인은 `/조판/CLAUDE.md`에 있음. 여기서는 핵심만 기술.

### 필수 순서

1. **원본 분석** → InDesign 원본 열어서 스타일/스토리 확인 (추측 금지)
2. **샘플 3개 프로토타입** → 전체가 아닌 소량으로 한 사이클 검증
3. **Phase 분할 개발** → 한 번에 전체 구현하지 않음
4. **수정 시 영향 확인** → 한 곳 고치면 다른 곳 깨지는지 확인

### 완료 후 회고 (필수)

모든 엔진 완료 시 대화 내역을 분석하여:
- 병목/반복 오류 → `/조판/CLAUDE.md`의 "과거 반복된 실수 목록"에 추가
- 효과적이었던 접근법 → 가이드라인에 반영
- 검증 기준 기록 (overflow, 페이지 수, 실행 시간, 수정 횟수)
