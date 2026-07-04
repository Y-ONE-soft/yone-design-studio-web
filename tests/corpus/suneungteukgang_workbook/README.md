# 수능특강 워크북 코퍼스 (content-only)

parse가 GDrive 단원 폴더에 의존해 업로드 재실행이 불가하므로
과거 job의 content.json(= v1 파서 실물 출력)과 메타를 고정한다.
플랜 빌더/E2E는 golden/content.json에서 시작한다 (parse 단계 생략).

- 65cf0265: 27강 (일반 강 — v1 실물 출력 EBS_수능특강_27강_분석/문제_3.indd)
- 4fa1510e: Test 2 (대형 원고 1.8MB — 실전 모의 유형)

주의: 구버전 산출물이라 step3 단락에 kind 주석 없음 —
engines/workbook_v2/plan.ensure_step3_kinds가 재주석한다.
