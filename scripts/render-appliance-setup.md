# 렌더 어플라이언스 셋업 (데스크톱 InDesign을 서버처럼)

데스크톱 InDesign은 자동화용으로 설계되지 않았다. 아래 설정으로 한 맥을
"조판 전용 가전"처럼 고정하면 콜드스타트·기습 모달·절전 중단을 없앨 수 있다.
**사람이 상주하지 않는 렌더 전용 맥에만 적용한다.**

## 1. InDesign 상시가동(warm) — 콜드스타트 제거  [스크립트 제공]

launchd가 2분마다 InDesign warm 상태를 확인, 꺼져 있으면 실행(문서는 안 엶).
렌더 중이면 아무것도 안 하므로 작업을 방해하지 않는다.

```bash
# 설치(활성화)
cp /Users/nhj/dev/yone-design-web/scripts/com.yonestudio.indesign-keepalive.plist \
   "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" \
   "$HOME/Library/LaunchAgents/com.yonestudio.indesign-keepalive.plist"

# 상태 확인
launchctl list | grep indesign-keepalive
tail -f "$HOME/Library/Logs/yonestudio-indesign-keepalive.log"

# 제거(롤백)
launchctl bootout "gui/$(id -u)/com.yonestudio.indesign-keepalive"
rm "$HOME/Library/LaunchAgents/com.yonestudio.indesign-keepalive.plist"
```

## 2. Adobe 자동업데이트 OFF — "업데이트 있습니다" 모달 차단  [수동]

자동 업데이트 알림은 무인 자동화를 멈추는 대표 원인이다.
- Creative Cloud 데스크톱 앱 → 우측 상단 계정 → 환경설정 → 앱
  → **"자동 업데이트" 끄기**
- 같은 화면에서 개별 앱 자동 업데이트도 해제
- Adobe Genuine Software 무결성 알림이 뜨면 정품 로그인 유지로 억제

## 3. 절전/화면보호기 OFF — 렌더 중단 방지  [수동 또는 명령]

```bash
# 전원 연결 시 잠들지 않기 (sudo 필요)
sudo pmset -c sleep 0
sudo pmset -c displaysleep 0
sudo pmset -c disksleep 0
```
- 시스템 설정 → 잠금 화면 → 화면보호기 "안 함", 디스플레이 끄기 "안 함"

## 4. 자동 로그인 ON — 재부팅 후 GUI 세션 자동 확보  [수동]

InDesign은 로그인된 Aqua(GUI) 세션이 있어야 osascript로 제어된다.
- 시스템 설정 → 사용자 및 그룹 → 자동 로그인 → 렌더 계정 지정
- (FileVault가 켜져 있으면 최초 1회 로그인 필요 — 렌더 전용 맥은 FileVault 해제 고려)

## 5. App Nap OFF (선택) — 백그라운드 스로틀 방지  [명령]

```bash
defaults write NSGlobalDomain NSAppSleepDisabled -bool YES
```

## 6. (선택) 야간 InDesign 재시작 — 메모리 누수/좀비 청소

장시간 warm 상태로 두면 InDesign 메모리가 누적될 수 있다. 필요 시 새벽에
1회 재시작하는 launchd(StartCalendarInterval)를 추가한다. 렌더 중이 아닐 때만
재시작하도록 가드를 둘 것(향후 작업).

---

## 우선순위
1(keepalive) → 2(자동업데이트 OFF)가 안정성 체감이 가장 크다.
3~5는 재부팅/절전 환경에서만 필요.
