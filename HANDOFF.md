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
