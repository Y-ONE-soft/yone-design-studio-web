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

**부교재 베타2(workbook_supp_v2) 문장배열 결함 수리** — job `a3d13ab3` (수능특강Light 영어 12강)

- 증상: [문단배열] 7문항 전부 (A)(B)(C)가 $BASIC 큰 글씨로 인쇄 + 발문·답란 누락,
  주어진 문장 박스 안 글자 벌어짐, "9. [문장삽입] p78-Gateway" 헤더가 본문에 그대로 인쇄.
- 원인: `engines/workbook_v2/plan.py` `build_step1_c1` 의 4d 패스가 주어진 문장의 탭을
  지워, 바로 뒤 4e 패스의 판정 근거(공백 3연속)가 사라짐. docx 표 셀 원고는
  `\n + 탭8 + 문장` 형태라 탭을 지우면 개행 하나만 남는다.
- 수정 (W69):
  - 4d 가 탭을 지우기 **전에** `_gap3` 플래그를 세우고 4e 가 그것을 본다 (판정 집합은
    기존의 상위집합 — 기존 통과 케이스 불변).
  - BTM 단락 앞뒤 개행·공백 트림 (`_RE_C1_EDGE_BREAK`) — 박스 안 강제 개행/양쪽정렬 늘어짐 제거.
  - Gateway 헤더 GREP 룰 추가 → `{gateway}` 로 정규화 (사용자 확정: 다른 스텝의
    [12강 gateway] 라벨 관행과 일치). 문항번호가 지문번호로 승격되던 {14} 도 해소.
- 회귀 대조: 실사용 원고 195케이스(jobs/*/content.json × 3 workbook_type) 전/후 비교 —
  스타일 변화는 대상 원고 2건뿐, 나머지 168건은 후행 공백 트림만. 회귀 없음.
- 재조판 검증: `워크북수특라이트영어_내지_v2_2.indd/pdf` (86p, 이전과 동일 쪽수).
  p33·34·36·38 문단배열 정상, p37·40 gateway 라벨 정상. 이전 산출물은
  `교재/워크북/_backup_20260820_1720/` 에 보존.
- 남은 것: 검수 게이트 critical 1 — 미사용 원고 2개
  (`Step1 C1 문장배열 (1).docx` 중복 업로드분, `Step2 직보.docx`). 원고 업로드 쪽 확인 필요.
  맥북엔 pytest 미설치 — 회귀는 위 195케이스 대조 스크립트로 수행했다.

### 2026-08-20 (아이맥) — Claude Code

**Vivliostyle 조판 엔진 3계층 구축 완료** — 문서: `docs/vivliostyle_엔진.md`

- 교재 폴더의 `automation/` 두 벌(상일보카·블랙북)을 리포로 승격:
  `core/render_vivlio/`(공용 백엔드: cli·stage·probe·paged·measure·bleed·verify·svg·config·book)
  + `series/vocabook/`·`series/blackbook/`(계열) + 교재 폴더 `config.json`(책 1권).
- 교재 폴더에는 이제 **config.json + 원고만** 있다. 실행은 `bin/viv "<책폴더>" all`,
  목록은 `bin/viv --list`. 납품 시점 코드·PDF 는 각 책 `_backup/` 에 보존.
- **회귀 대조 통과**: 상일보카 4종(견본/전권/메모없음/최종) + 블랙북 1종을 config 만으로
  다시 조판해 납품본과 쪽수·쪽별 텍스트·블록 좌표 전부 일치(좌표 차 0.000mm).
- npm 을 `core/render_vivlio/` 소유로 이관(`npm --prefix core/render_vivlio ci`).
  `pilot/vivliostyle` 는 폴백으로만 남음.
- 테스트 `tests/test_render_vivlio_engine.py` 19개 추가. 전체 스위트 실패 47건은
  **착수 전(c0346f1)과 동일한 기존 실패**(workbook_v2 계열) — 이번 작업과 무관.
- 남은 것: 두 번째 단어장(배재보카, InDesign→Vivliostyle 이식 선행 필요) /
  두 번째 블랙북 / 통합웹 카드 등록(업로드→config 합성 매핑이 아직 미정).

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
