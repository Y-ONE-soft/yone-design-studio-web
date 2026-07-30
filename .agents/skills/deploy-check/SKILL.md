---
name: deploy-check
description: 통합웹사이트(yonestudio.com) 코드 수정 후 반영·배포 검증 절차. Flask 재시작이 곧 실서비스 배포이므로 수정 완료 보고 전 반드시 실행. 트리거 - 통합웹 코드 수정 완료 시, "배포 확인", "반영됐는지 확인", 수정했는데 반영이 안 보일 때.
---

# 통합웹 배포 검증 절차

`yonestudio.com`은 Cloudflare Tunnel로 `localhost:5010`에 묶여 있어 **Flask 재시작 = 즉시 실서비스 배포**다. localhost와 yonestudio.com은 항상 동일한 상태여야 한다.

## 절차 (전부 완료해야 작업 완료)

1. 코드 수정
2. Flask 재시작 (이 시점에 yonestudio.com에 즉시 반영):
   ```bash
   launchctl kickstart -k gui/$(id -u)/com.yonestudio.flask
   ```
3. 내보내기(export)가 있는 작업이면 export 실행
4. **양쪽 모두** 실제 동작 확인:
   ```bash
   curl -sI http://localhost:5010/<수정한 페이지>
   curl -sI https://yonestudio.com/<수정한 페이지>
   ```
   화면 확인이 필요하면 브라우저에서 양쪽 hard-refresh (Cmd+Shift+R).
5. 양쪽 결과가 다르면 원인 파악 후 해결할 때까지 **작업 미완료** — 완료 보고 금지

## 반영이 안 보일 때

1. Flask 재시작 (위 kickstart 명령)
2. iCloud dataless 파일 materialize: `find <dir> -type f -exec cat {} > /dev/null \;`
3. 브라우저 hard-refresh (Cmd+Shift+R)
4. Flask 로그 확인: `~/Library/Logs/yonestudio-flask.log` / `-error.log`

## 주의

- 서버를 `python3 app.py`로 수동 실행하지 않는다 — launchd(`com.yonestudio.flask`)가 관리하므로 반드시 kickstart로 재시작 (수동 실행 시 이중 인스턴스/권한 컨텍스트 문제 발생)
- 사용자가 "서버 재시작하지 마"라고 명시하지 않는 한 수정 후 재시작은 항상 수행
