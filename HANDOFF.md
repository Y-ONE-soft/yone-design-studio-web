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

### 2026-05-12 13:50 (아이맥) — Claude Code

운영 환경 정비 완료. 진행한 것:

- [x] 단계 0: 비밀번호/secret_key `.env`로 분리 (평문 코드 제거)
- [x] 단계 1: `YONE_STUDIO_ROOT` 환경변수 등록, 심볼릭 링크 제거
- [x] 단계 4: 자동 git pull launchd 등록 (5분 간격, 활성 작업 가드)

다음 단계 (사용자 결정 필요):
- [ ] 단계 2: Tailscale + macOS 화면 공유 (사용자 계정 가입/앱 설치 필요)
- [ ] 단계 3-b: Anthropic Remote Control 활성화 (사용자 계정 설정 필요)
- [ ] 단계 6: 조교 .indd 구글드라이브 공유 (사용자 폴더 결정 필요)

운영 상태: 정상. yonestudio.com 작동 중.

---

(이전 메모는 git log로 확인: `git log --oneline HANDOFF.md`)
