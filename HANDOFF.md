# HANDOFF — 기기 간 작업 인계 메모

> 맥북 ↔ 아이맥 작업 이어갈 때 사용. 이 파일은 git으로 동기화되니까,
> 다른 기기에서 `git pull` 받으면 즉시 보입니다.

## 사용법

**작업 끝낼 때 (마지막 기기에서)**

1. 무엇까지 했는지 한두 줄 적기 (아래 형식)
2. `git add HANDOFF.md && git commit -m "handoff: ..." && git push`

**작업 시작할 때 (다른 기기에서)**

1. `cd ~/dev/yone-design-web && git pull`
2. 이 파일 열어서 마지막 메모 확인
3. 그 지점부터 이어서 작업

---

## 최근 인계 메모 (최신이 위)

### 2026-08-20 (맥북) — Claude Code

**부교재 베타2(workbook_supp_v2) C1 문장배열 전면 수리** — job `a3d13ab3` (수능특강Light 영어 12강)

1차로 스타일·발문만 고쳤다가 사용자 지적("완전 엉망")으로 **배치가 근본 원인**임을 확인.
완제품 실측(광문2 워크북02 수특라이트영독3강 p28~30, 수특라이트11강 p25·p27)으로 계약 확정:

> **한 페이지 = 한 지문.** 상단 프레임 = 지문번호 + 문장배열 카드((A)~(Z) + 화살표 답란),
> 하단 프레임 = **지문번호 없이** 발문 + 주어진 문장 + 본문 박스.

- **W69 (스타일 층위)**: 4d 패스가 주어진 문장의 탭을 지워 4e 판정 근거(공백 3연속)를
  파괴 → [문단배열]의 (A)(B)(C)가 $BASIC 으로 인쇄되고 발문·답란 누락. 탭 제거 전에
  `_gap3` 플래그를 세워 4e 가 보게 함. BTM 단락 앞뒤 개행 트림(`_RE_C1_EDGE_BREAK`).
  Gateway 헤더 GREP 룰 추가 → `{gateway}`.
- **W70 (배치 층위)**: `_c1_group_slot_units` 신설. 블록을 카드/하단으로 판정하고 지문
  라벨로 묶어 상단·하단 슬롯에 배정, 하단 블록의 지문번호 단락은 출력하지 않는다.
  하단이 둘이면 문단배열 → 문장삽입 순(11강 p25→p27 실측).
  라벨 순서는 `_c1_order_labels` — **원고가 이미 지문번호 순이면 손대지 않는다**
  (job ea9c65b4 영어독해 8강의 `{05~06}` 을 앞으로 끌어내던 회귀를 이 조건으로 차단).
  12강처럼 유형 순환이라 번호가 흩어진 원고만 재배치(gateway 앞, 숫자 오름차순 —
  같은 교재 step1_a1/a2/b2 의 [12강 gateway] → [12강 1번] 순서와 일치).
- 회귀 대조: 실사용 원고 195케이스(jobs/*/content.json × 3 workbook_type) 전/후 —
  구조·스타일이 바뀐 건 대상 12강 원고 2건뿐, 나머지는 후행 공백 트림만.
- 재조판 검증: `워크북수특라이트영어_내지_v2_3.indd/pdf` (88p). C1 = p33~45,
  지문 gateway·01~06 순서로 각 2쪽(카드+문단배열 / 라벨만+문장삽입). 이전 산출물은
  `교재/워크북/_backup_20260820_1720/`.
- 남은 것: 검수 critical 1 — 미사용 원고 2개(`Step1 C1 문장배열 (1).docx` 중복 업로드분,
  `Step2 직보.docx`). gateway 지문은 원고에 배열 문항이 없어 상단 카드 자리가 빈다
  (11강 p27·p29 와 같은 형태). 맥북엔 pytest 없음 — 회귀는 위 195케이스 대조로 수행.

### 2026-05-14 03:30 (아이맥) — Claude Code (2차)

추가 자동 진행 완료:

- [x] **sharing.py 견고화** (commit `34c6644`):
  - `_run_pipeline`이 verify result의 `indd_path`를 직접 전달 → settings.json fallback 의존도 줄어듦
  - `.indd` 같은 폴더의 `Links/`, `Fonts/`, `Document fonts/` 폴더도 함께 복사
  - → 조교 PC에서 InDesign 열 때 링크 깨지지 않음
- [x] **/api/health 엔드포인트** (commit `e012440`):
  - 인증 우회 (외부 모니터링/Tailscale 폰 접속에서 사용)
  - 응답: `indesign_running`, `active_jobs`, `last_auto_pull`, env 설정 여부
  - 비밀번호 값은 노출 X (`bool`로만)

다음 액션 (사용자 결정 필요):
- Tailscale + macOS 화면 공유 (외부에서 아이맥 접속)
- Anthropic Remote Control (폰에서 Claude 세션 이어가기)
- 조교 온보딩 (구글드라이브 폴더 공유 + 조교 PC 설치)

### 2026-05-14 03:00 (아이맥) — Claude Code

조교 공유 폴더 핵심 수정 완료 (사용자님 자는 동안 진행):

- [x] 옛 33개 메타데이터 폴더 모두 삭제 (조판결과 폴더 깨끗하게 비움. 매니페스트 백업: `~/Backups/share_metadata_backup_20260514_*`)
- [x] `core/sharing.py` 수정 (commit `3167d14`):
  - `.settings.json`에서 `indd_path` 추출 → 실제 `.indd` 복사
  - PDF 복사
  - 핵심 메타 (school, issue_num, grade 등)만 복사
  - 노이즈 (content.json, run.jsx, 조판_로그.txt, uploads/) 제외
- [x] 단위 테스트 PASS, Flask 정상

**다음 작업 시 확인할 것**: 통합웹으로 새 조판 1건 트리거 → `Y.ONE WEB/조판결과/[학교]_[jobid]/` 폴더에:
- `*.indd` (조판된 인디자인 파일) ← 핵심
- `*.pdf`
- `school.txt`, `issue_num.txt` 등 1-2개 메타

가 잘 들어오는지 확인. 안 들어오면 settings.json에 indd_path 없는 엔진이라는 뜻 (현재 코드의 한계).

### 2026-05-12 14:10 (아이맥) — Claude Code

마스터 계획 자동 진행분 모두 완료. 진행한 것:

- [x] 단계 0: 비밀번호/secret_key `.env`로 분리 (평문 코드 제거)
- [x] 단계 1: `YONE_STUDIO_ROOT` 환경변수 등록, 심볼릭 링크 제거
- [x] 단계 3a: HANDOFF.md 인계 워크플로우 도입 (이 파일)
- [x] 단계 4: 자동 git pull launchd 등록 (5분 간격, 활성 작업 가드)
- [x] 단계 6: 조교 .indd 구글드라이브 비동기 공유 (`core/sharing.py`)
- [x] 조교용 가이드 작성 (`docs/조교_가이드.md`)

다음 단계 (사용자 액션 필요):
- [ ] 단계 2: Tailscale + macOS 화면 공유 (1.5시간, 계정 가입 + 앱 설치)
- [ ] 단계 3b: Anthropic Remote Control 활성화 (10분, 계정 설정)
- [ ] 단계 6 후속: 조교 이메일로 `Y.ONE WEB/조판결과/` 폴더 공유 권한 + 조교 PC에 Google Drive 데스크탑 앱 설치 안내

장기:
- [ ] iCloud 옛 폴더 정리 (5.3GB 회수, 1~2일 안정 운영 확인 후)
- [ ] InDesign watchdog / Webhook (1주 안정 확인 후 재평가)

운영 상태: ✅ 정상. yonestudio.com 가동 중.
GitHub: github.com/YONE-DESIGN/YONE-DESIGN-WEB (commit `0cf5166`).

---

(이전 메모는 git log로 확인: `git log --oneline HANDOFF.md`)
