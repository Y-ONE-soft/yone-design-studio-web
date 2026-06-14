# engines/_taxonomy — 원고 분류 체계 모듈

조판 자동화의 표준 입력 스펙. 한국 영어 내신/모의 원고의 문제 유형을 126개 leaf 코드로 분류.

밑줄 prefix(`_taxonomy`)는 **공유 모듈(엔진 아님)** 관례 표시. `registry.py`에 등록되지 않으며 기존 엔진들은 이 모듈을 import하지 않는다 — **기존 자동화 흐름 0 영향**.

## 출처

- 원본 문서: `/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/원고_분류체계/`
- 광범위 추출 기반: 126,312건 발문, 분류 성공률 86.1%
- v1.0.0 작성: 2026-05-25

## 파일 구성

| 파일 | 역할 |
|---|---|
| `__init__.py` | 공개 API |
| `rules.py` | 126개 leaf 코드 + 정규식 룰 |
| `classify.py` | 발문 → 코드 매핑 함수 |
| `extract.py` | hwp/hwpx/docx 텍스트/발문 추출 |
| `cli.py` | 명령줄 도구 |
| `schema.json` | 기계 가독 분류 스키마 (변형 차원 + 카테고리 메타 포함) |

## 사용법

### Python 코드에서

```python
from engines._taxonomy import classify, extract_and_classify

# 발문 1개 분류
code, label, kind = classify("다음 글의 제목으로 가장 적절한 것은?")
# → ('OBJ-CTN-TITLE', '제목', '객관식')

# 원고 한 파일 통째로
results = extract_and_classify("/path/to/manuscript.hwpx")
# → [{"q": "...", "code": "OBJ-FLW-ORDER", "label": "순서 배열", "kind": "객관식", "line_idx": 12}, ...]
```

### CLI

```bash
# 단일 발문
python3 -m engines._taxonomy.cli classify "다음 글의 제목으로 가장 적절한 것은?"
# 출력: OBJ-CTN-TITLE   제목    객관식

# 원고 한 파일
python3 -m engines._taxonomy.cli file /path/to/manuscript.hwpx

# JSON 출력
python3 -m engines._taxonomy.cli file /path/to/manuscript.hwpx --json
```

## 룰 추가/수정

새 발문 패턴이 발견되면 `rules.py`의 `RULES` 리스트 끝에 추가:

```python
RULES = [
    ...
    ("OBJ-NEW-TYPE", "새 유형 라벨", r"정규식 패턴"),
]
```

순서 중요: 구체적인 규칙을 먼저, 일반적인 규칙을 나중에.

## 코드 체계

- `OBJ-*` = 객관식, `SRV-*` = 서술형
- `OBJ-VOC-*` = 어휘, `OBJ-GRM-*` = 어법, `OBJ-CTN-*` = 내용,
  `OBJ-FLW-*` = 글의 흐름, `OBJ-DTL-*` = 세부, `OBJ-LNG-*` = 장문
- `SRV-WRD-*` = 단어 채우기, `SRV-GRM-*` = 어법 수정, `SRV-KOR-*` = 우리말,
  `SRV-WRT-*` = 영작, `SRV-EXT-*` = 본문 발췌

전체 코드 + 변형 차원 정의: `schema.json`

## 변경 정책

- 기존 엔진(workbook/mockexam/blackbook 등)은 이 모듈을 **import 안 함**
- 신규 엔진 / 디버깅 / 분석 작업에서만 사용
- 모듈 폐기 시 `engines/_taxonomy/` 폴더만 삭제하면 끝 (롤백 비용 0)
