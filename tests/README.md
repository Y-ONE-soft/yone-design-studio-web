# tests/ — Phase 0 회귀 안전망

## 실행

```bash
cd ~/dev/yone-design-web-summer   # (또는 리포 루트)
python3 -m pytest tests/ -q

# 실서비스와 동일한 인터프리터(3.9)로 확인 (merge/배포 전 필수 — deploy_to_prod.sh가 사용)
PYTHONPATH="$HOME/Library/Python/3.9/lib/python/site-packages" /usr/bin/python3 -m pytest tests/ -q
```

InDesign 불필요 — `engine.parse()`만 재실행한다. 전 케이스 수 초 내.
(실서비스 Flask는 /usr/bin/python3 3.9로 구동 — start_flask.sh 참조. 3.14/3.9 양쪽 23/23 통과 확인: 2026-07-03)

## 구조

```
tests/
  corpus/<engine>/<job_id>/
    inputs/        업로드 원본 (uploads/의 "<slot>_*" 파일)
    meta/          job 메타 *.txt (grade, year, month, school, ...)
    golden/        content.json — 선별 당시 "현행 파서 출력" 스냅샷
    manifest.json  엔진 id + 출처 job id
  test_parse_snapshot.py
```

코퍼스 추가: `python3 scripts/build_corpus.py --per-engine 5` (main 체크아웃의
`~/dev/yone-design-web/jobs/`에서 선별). 새 엔진은 스크립트의 `ENGINE_SLOTS` +
`_classify()`에 시그니처를 등록한다.

## 골든 승격 절차 (중요)

**골든은 정답이 아니라 "그 시점의 현행 출력"이다** (버그 포함 가능).
테스트가 빨간데 그 차이가 *의도된 개선*이면:

1. 실패 메시지의 "첫 불일치" 경로를 확인하고, 정말 의도된 변화인지 diff로 검토
   (`pytest -q` 실패 메시지 → 필요 시 produced/golden JSON을 직접 비교).
2. 개선이 맞으면 골든을 새 출력으로 교체하고, **왜 달라졌는지 커밋 메시지에 명시**:
   `test(corpus): workbook/f6f64554 골든 갱신 — 밑줄 누락 수정으로 marks 필드 증가`
3. 의도되지 않은 변화면 → 회귀. 코드를 고친다. 골든을 건드리지 않는다.

절대 하지 말 것: "테스트가 시끄러워서" 골든 일괄 재생성. 그 순간 안전망이 사라진다.
