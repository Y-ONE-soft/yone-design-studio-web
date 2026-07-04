# 리딩파워(EBS) 워크북 코퍼스 (content-only)

parse가 GDrive 단원 폴더에 의존해 업로드 재실행이 불가하므로
과거 job의 content.json(= v1 파서 실물 출력)과 메타를 고정한다.
플랜 빌더/E2E는 golden/content.json에서 시작한다 (parse 단계 생략).

- 4ed24266: Unit 15 (8스텝 — v1 실물 출력 EBS_리딩파워_Unit15_전체(C).indd 잔존)
- fbb8dbc5: Unit 17

주의: 구버전 산출물이라 step3 단락에 kind 주석 없음 —
engines/workbook_v2/plan.ensure_step3_kinds가 재주석한다.
