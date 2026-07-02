# 4단계 (보류) — 크레딧 .ai GDrive 직접참조 → 로컬 경유 계획서

**상태: 2026-07-02 적용 완료** (커밋 76d64a6, `_resolve_credit_ai()`). 한영3 실조판에서 creditPage=ok(Vol1/Vol2) 확인. 아래는 원래 계획(참고용).

> ~~야간 자동 미실행.~~ final 엔진(3301줄, 최복잡)의 JSX 조립을 블라인드로
바꾸면 실패 시 크레딧 누락이 아니라 final 전체 렌더가 깨질 수 있고, 야간에
final 작업으로 검증할 수 없어 보류함. 사용자와 함께 final 1건 돌려 검증하며 적용.

## 문제
`engines/final/indesign_stepper.py` 두 곳(552, 3254)에서 InDesign이
`마지막페이지.ai`(크레딧)를 **Google Drive Stream 경로에서 직접 place(링크 배치)**.
- 렌더 중 GDrive 직접 read → EDEADLK 위험
- 배치 결과가 GDrive 경로 링크로 저장 → .indd 열 때마다 GDrive 의존 재발

## 추가 발견 — 이식성 버그 (각 장비 목표와 직결)
경로가 `/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/...`로
**하드코딩**. 따라서:
- nhj 아이맥이 아닌 다른 맥(조교/신규 디자이너/맥북)에서는 이 경로가 없어
  `lastAiFile.exists == false` → `aiNotFound` → **크레딧 페이지가 조용히 누락됨.**
- 즉 "각 장비에서 실행" 목표에서 final 산출물이 기계마다 달라지는 원인.

## 적용 계획 (awake 검증과 함께)
1. `_gdrive_safe_copy`(engines/final/extractor.py:122, 기존 자산) 재사용.
2. 헬퍼 `_resolve_credit_ai(log) -> str`:
   - GDrive 원본 경로 상수 정의(현행 경로).
   - 안정적 로컬 경로로 복사: `~/Library/Application Support/yone-design-web/assets/credit_lastpage.ai` (ASCII 파일명 — JSX 유니코드 이스케이프 회피).
   - 복사 성공 → 로컬 경로 반환 / 실패 → **원본 GDrive 경로 반환(폴백 = 현행과 동일, 절대 더 나빠지지 않음).**
3. `_build_vocab_jsx`, `_build_vol2_jsx` 상단에서 `credit_ai = _resolve_credit_ai(...)`,
   두 곳의 `var lastAiPath = "...gdrive..."`를 `var lastAiPath = "{credit_ai_escaped}"`로 교체
   (백슬래시/따옴표 이스케이프 필수).
4. **정적 검증**: py_compile + 생성된 JSX 문자열 렌더 후 `var lastAiPath = "..."` 유효성 확인.
5. **라이브 검증(사용자와 함께)**: final 작업 1건 실행 → 크레딧 페이지가 정상 배치되는지,
   링크가 로컬을 가리키는지 확인.
6. 롤백: env 플래그(YONE_CREDIT_AI_LOCAL=0)로 원본 경로 강제.

## 리스크
- 없음(복사 실패 시 현행 폴백). 유일한 신규 실패모드는 JSX 문자열 파손 → 4단계 정적검증으로 차단.
- 검증 필요 이유: final 엔진 크기/복잡도 + 크레딧 배치 시각 확인은 실제 렌더로만 가능.
