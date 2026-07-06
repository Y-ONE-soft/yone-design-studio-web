# manual_jsx_mirror — 수동 InDesign 스크립트 미러본

이 디렉터리는 **읽기 전용 미러**입니다. 원본은 아래 경로이며, 수정은 반드시 원본에서 하세요.

- 원본: `~/Documents/작업/Y.ONE STUDIO/조판/인디자인 스크립트/`
- 동기화: `scripts/backup_assets.sh jsx` (launchd `com.yonestudio.jsx-mirror`, 매일 05:00)
  가 rsync --delete 로 원본 → 이곳을 미러하고, main autosync(3분)가 커밋·push합니다.
- 여기서 파일을 고쳐도 다음 동기화 때 원본 상태로 덮어써집니다.

버전 이력이 없던 iCloud 유일본(~100개 .jsx)에 git 버전관리를 부여하기 위한 장치입니다
(docs/재해복구_절차.md 4절 3번 백업 공백 해소, 2026-07-06).
