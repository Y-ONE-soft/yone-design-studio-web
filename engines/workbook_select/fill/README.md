# 보충 데이터 (fill.json) 보관소

원고가 **아예 없는 칸**을 이전 산출물(.indd)에서 뽑아 채우는 데이터.
형식: `{step_key: {code: {"prompt": str, "paras": [{"text","runs"}]}}}`

## 자동 적용되지 않는다 (의도된 설계)

config 에 특정 강 파일을 기본값으로 박아두면 **다른 강 job 에 남의 강 내용이
섞인다**(2026-08-13 발견: `hanyoung1_11gang.json` 이 전 job 기본값이었다).
그래서 `config.fill_json` 은 비어 있고, 엔진은 **job 폴더의 `fill.json`** 만
읽는다. 여기 파일은 쓰려면 명시적으로 지정한다:

```bash
python3 scripts/wbsel_build.py --gang 11 --fill engines/workbook_select/fill/hanyoung1_gang11.json ...
python3 scripts/wbsel_preflight.py --gang 11 --fill engines/workbook_select/fill/hanyoung1_gang11.json
```

## 먼저 원고를 확인할 것

fill 은 최후 수단이다. 회차 폴더(`고N YY년 M월/워크북`)가 없는 옛 기출은
**마더텅 N강 폴더의 워크북 원고**에서 자동 조달되므로(engine
`_find_gang_manuscript_dirs`), 대부분의 "원고 없음"은 fill 없이 해결된다.
실제로 `hanyoung1_gang11.json` 의 `step1_a1`/`step1_a1_2` 6칸은 자동 조달로
불필요해졌다.

## 파일 목록

| 파일 | 내용 | 상태 |
|---|---|---|
| `hanyoung1_gang11.json` | 한영1 마더텅 11강 — step1_a1/step1_a1_2 (161131·190633·210632), step2_a1_btm (220632·220633·220932) | step1_a1 6칸은 자동 조달로 불필요. **step2_a1_btm 3칸은 여전히 원고에 없음** — 22년 6월·9월 어법선택(객관식) 원고 자체에 그 문항이 없다 (교재팀 재요청 대상) |
