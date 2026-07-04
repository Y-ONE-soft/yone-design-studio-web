# 교과서 워크북 코퍼스 (content-only)

parse가 GDrive 워크북 폴더에 의존해 업로드 재실행이 불가하므로
(scripts/build_corpus.py "코퍼스 보류 엔진" 참조), 과거 job의
content.json(= v1 파서 실물 출력)과 메타를 그대로 고정한다.
플랜 빌더/E2E는 golden/content.json에서 시작한다 (parse 단계 생략).

- 80dd3fa2: 공통영어1 능률(오) 2과 (13스텝, step3 825단락)
- 20a3838b: 공통영어1 미래엔(김) Deep Learning 3, 4과 (그룹 폴더 케이스)

주의: 구버전 산출물이라 step3 단락에 kind 주석이 없다 —
engines/workbook_v2/plan.ensure_step3_kinds가 재주석한다.
