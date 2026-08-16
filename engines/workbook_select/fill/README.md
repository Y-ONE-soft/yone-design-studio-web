# 보충 데이터 (fill.json) 보관소

원고가 **아예 없는 칸**을 이전 산출물(.indd)에서 뽑아 채우는 데이터.
형식: `{step_key: {code: {"prompt": str, "paras": [{"text","runs"}]}}}`

## 조달 우선순위

| 순위 | 출처 | 언제 |
|---|---|---|
| 1 | 웹 업로드 슬롯 `fill` | 조판 화면에서 .json 을 직접 올렸을 때 |
| 2 | `job_dir/fill.json` | CLI `--fill` 로 넘겼을 때(job 폴더로 복사됨) |
| 3 | **이 보관소** (`index.json`) | job 의 **학년·강이 정확히 일치**하는 항목이 있을 때 |
| 4 | `config.fill_json` | 비워 두는 것이 정상. 값이 있을 때만 폴백 |

**보관소 자동 조달은 (학년, 강) 완전 일치일 때만** 한다. 부분일치·기본값·
폴백은 금지 — 특정 강 파일이 모든 job 의 기본값이라 남의 강 내용이 섞인
사고가 있었다(2026-08-13). 무엇을 왜 골랐는지는 항상 로그에 남는다.
강 번호가 없는 **코드 job 은 키가 없어 자동 조달 대상이 아니다** — 업로드나
`--fill` 을 쓴다.

```bash
python3 scripts/wbsel_build.py --gang 11 ...          # 보관소에서 자동
python3 scripts/wbsel_build.py --codes ... --fill <경로>   # 코드 job 은 명시
```

## 항목 추가 방법

1. `scripts/wbsel_extract_fill.py` 로 이전 산출물에서 뽑아 이 폴더에 저장
2. `index.json` 의 `entries` 에 `grade` / `gang` / `file` / `note` 추가
3. `python3 scripts/wbsel_test_mtgate.py` 로 색인 정합 확인 (적힌 파일이 실제로 있는지 검사한다)

### ⚠ 학교 전용 데이터는 `school` 을 반드시 넣는다

```json
{"grade": 1, "gang": 7, "school": "한영1", "file": "…json"}
```

`school` 이 있으면 그 학교 job 에만 조달된다. **비워 두면 학교 무관**으로
취급하므로, 기출 문항 코드(YYMMQQ)를 키로 쓰는 학교 무관 데이터만 비운다.
학교 전용 내용을 `school` 없이 등록하면 타 학교 job 으로 샌다.

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
