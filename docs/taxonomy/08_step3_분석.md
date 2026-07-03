# 08. 워크북 STEP3 분류 체계 매핑 분석

작성일: 2026-05-26
대상: `yone-design-web/engines/workbook/parser.py` line 977~1933 (STEP3 파싱 영역)

## 결론 요약

STEP3 파서의 **약 60%는 분류 체계 leaf 코드와 1:1 매핑 가능**. 나머지 40%는 STEP3 특화 보정 로직 (정답 제거 / 표 평탄화 / 자동번호 prepend 등)이라 분류 체계로 대체 불가.

수정 가능한 부분이 명확히 존재하지만, **지금 수정은 권장하지 않음**. 사유: 분류기를 통한 leaf 코드 분기 로직이 신규 → 회귀 테스트 부담. 분류기 자체가 1~2주 운영 후 안정화되면 그때 점진 적용.

수정 가능 부분 식별만 정리 (Tier 1~3).

---

## STEP3 파서 구조

```
_parse_step3_folder()  ← 진입점 (parser.py:1460)
├── 파일 수집 (.hwp/.hwpx/.docx, NFD→NFC)
├── 추출 (_docx_extract_paragraphs / _hwp_extract_paragraphs)
└── 정리 파이프라인 (순서 중요):
    1. _strip_step3_answers()          ← 정답/해설 줄 제거
    2. _strip_step3_type_tags()        ← [유형 1] 섹션 라벨 제거
    3. _add_step3_choice_numbers()     ← ①②③④⑤ 자동번호 prepend ★
    4. _strip_step3_book_markers()     ← 책 헤더 + [Gateway] 제거
    5. _fix_step3_order_label_position() ← (A) 라벨 위치 정규화
    6. _merge_step3_ab_pairs()         ← (A)/(B) 매칭 표 5쌍 합치기 ★
```

★ = 분류 체계와 직접 연결되는 핵심 함수

---

## STEP3 정규식 vs 분류 체계 leaf 코드 매핑

### 직접 매핑 가능 (1:1)

| STEP3 정규식 | 정규식 패턴 | 분류 체계 leaf 코드 | 위치 |
|---|---|---|---|
| `_RE_STEP3_ORDER_QUESTION` | `순서로 적절한\|이어질 글의 순서` | `OBJ-FLW-ORDER` | parser.py:1197 |
| `_RE_STEP3_AB_QUESTION` | `\(A\).{0,5}\(B\)` | `OBJ-VOC-PAREN` (어휘) 또는 `OBJ-GRM-PAREN` (어법) | parser.py:1193 |
| `_STEP3_INSERT_PATTERN` | `주어진 (문장\|글)\|들어갈 위치\|이어질 순서` | `OBJ-FLW-INSERT` 또는 `OBJ-FLW-ORDER` | parser.py:1389 |
| `_RE_STEP3_CHOICE_QUESTION` | `^\d+\..*것은?\|것을 두 개 고르시오` | 객관식 발문 일반 (분기 필요) | parser.py:1060 |

### 키워드 묶음 → 정밀 분기 가능

#### A. `_RE_STEP3_NON_CHOICE` (자동 ① prepend skip 발문)

현재 5개 키워드를 OR로 묶어 단일 처리:
```python
r'요약하고자\s*한다|영어로\s*완성|찾아\s*쓰시오|바르게\s*고치시오|어형\s*변화'
```

분류 체계로 분기하면:

| 현재 키워드 | 분류 체계 코드 (정밀) |
|---|---|
| "요약하고자 한다" | `OBJ-FLW-BLANK-AB` (객관식 요약 빈칸) / `SRV-WRT-SUMM` (서술형) |
| "영어로 완성" | `SRV-WRT-KO-EN` / `SRV-EXT-MEAN-SENT` |
| "찾아 쓰시오" | `SRV-EXT-PHRASE` / `SRV-WRD-FROM-TEXT` |
| "바르게 고치시오" | `SRV-GRM-FIX-MARKED` / `SRV-GRM-FIX-FIND-K` / `SRV-GRM-FIX-ALL` |
| "어형 변화" | `SRV-WRD-FROM-TEXT-VAR` / `SRV-WRT-COND-VAR` |

**효과**: 키워드 OR 매칭 → "발문이 서술형인가" 1줄로 단순화 가능.

```python
# 현재
if _RE_STEP3_NON_CHOICE.search(text):
    i += 1
    continue

# 분류 체계로 대체 가능
from engines._taxonomy import classify
code, _, kind = classify(text)
if kind == "서술형":   # 모든 SRV-* 코드 자동 포함
    i += 1
    continue
```

#### B. `_RE_STEP3_INLINE_CHOICE` (선지가 본문 inline에 박힌 발문)

```python
r'밑줄\s*친\s*부분\s*중|흐름과\s*관계\s*없는\s*문장|어법상\s*틀린\s*것'
r'|주어진\s*(?:문장|글)|들어갈\s*위치'
r'|\(\s*A\s*\).{0,5}\(\s*B\s*\)'
```

| 현재 키워드 | 분류 체계 코드 |
|---|---|
| "밑줄 친 부분 중" | `OBJ-VOC-UND-WRONG` / `OBJ-GRM-UND-WRONG` |
| "흐름과 관계 없는 문장" | `OBJ-FLW-IRRELEVANT` |
| "어법상 틀린 것" | `OBJ-GRM-UND-WRONG` |
| "주어진 문장/글" | `OBJ-FLW-INSERT` / `OBJ-FLW-ORDER` |
| "들어갈 위치" | `OBJ-FLW-INSERT` |
| "(A)...(B)" | `OBJ-VOC-PAREN` / `OBJ-GRM-PAREN` |

**효과**: 동일하게 "발문 코드가 inline-marker 유형인지" 한 줄로 판정 가능.

```python
INLINE_MARKER_CODES = {
    "OBJ-VOC-UND-WRONG", "OBJ-VOC-UND-WRONG-MULTI", "OBJ-VOC-UND-MEAN",
    "OBJ-GRM-UND-WRONG", "OBJ-GRM-UND-WRONG-MULTI",
    "OBJ-FLW-IRRELEVANT", "OBJ-FLW-INSERT", "OBJ-FLW-ORDER",
    "OBJ-VOC-PAREN", "OBJ-GRM-PAREN", "OBJ-FLW-PAREN", "OBJ-GRM-PAREN-CONN",
}
if code in INLINE_MARKER_CODES:
    i += 1
    continue
```

### 분류 체계로 대체 불가 (STEP3 특화 보정)

| 함수 | 역할 | 대체 불가 이유 |
|---|---|---|
| `_strip_step3_answers()` | "②: ⓑ making → make ..." 정답 줄 제거 | 분류 체계와 무관, hwp 특수 케이스 |
| `_strip_step3_type_tags()` | "[유형 1]" 섹션 라벨 제거 | STEP3 원고 형식 특화 |
| `_strip_step3_book_markers()` | "2027년 수능특강 ..." 책 헤더 제거 | 책 메타데이터, 분류 외 영역 |
| `_fix_step3_order_label_position()` | (A) 라벨이 도입부 박스 위로 잘못 추출된 케이스 정규화 | hwp 표 추출 버그 보정 |
| `_merge_step3_ab_pairs()` 합치기 부분 | 평탄화된 표 셀을 5쌍으로 합치기 | 분류 후 후처리 (분류 자체는 분류 체계로 가능) |

이 부분들은 STEP3 hwp/docx의 특수 추출 케이스 보정이라 분류 체계의 leaf 코드만으로는 대체 X.

---

## Tier별 수정 권장 (수정은 추후, 식별만)

### Tier 1 — 안전, 점진, 큰 효과 (분류기 안정화 후 추천)

**대상**: `_add_step3_choice_numbers()` 내 NON_CHOICE/INLINE_CHOICE 판정

**변경 범위**: 30~40줄 정도

**효과**:
- 룰 추가 시 STEP3 파서 수정 불필요 — `engines/_taxonomy/rules.py`에만 룰 추가
- 새 서술형 변형이 들어와도 자동 인식 (현재는 키워드 5개로 한계)
- 코드 중복 제거 (`_RE_STEP3_NON_CHOICE`, `_RE_STEP3_INLINE_CHOICE`는 분류 체계와 부분 중복)

**위험**: 중. 새 로직 도입으로 회귀 테스트 필요.

**검증 방법**: 기존 STEP3 원고 10개 정도로 before/after 비교 (paragraphs 동일성 확인)

### Tier 2 — 중간 위험, 중기

**대상**:
- `_merge_step3_ab_pairs()`의 매칭 발문 식별 부분
- `_fix_step3_order_label_position()`의 순서배열 발문 식별

**변경 범위**: 각 함수당 5~10줄

**효과**: 어휘/어법 (A)/(B)를 코드별로 정확히 분기. 순서배열 명확 식별.

**위험**: 중간. 다만 표 합치기/라벨 이동 로직 자체는 유지하므로 동작 영향은 작음.

### Tier 3 — 지금 보류 (회귀 위험 큼)

**대상**:
- STEP3 파서를 "발문 → leaf 코드 → 처리 핸들러" dispatch 구조로 재설계
- 모든 정규식 / 휴리스틱을 분류기 결과로 통일

**변경 범위**: parser.py 977~1933 전체 (약 950줄)

**효과**: 코드 일관성. 새 유형 추가가 룰 한 줄 + 핸들러 등록으로 끝.

**위험**: 매우 큼. 워크북은 통합웹사이트 핵심 엔진. 회귀 시 작업 일정 전체 영향.

**조건**: 분류기를 다른 카테고리(동형/세미모의 등)에서 충분히 검증한 뒤에만 검토.

---

## 즉시 수정 가능한 사소한 부분 (Tier 0)

이건 분류 체계 도입과 무관하고 그냥 발견된 사소한 미스매치:

### 1. "어형 변화" vs "어형 변형" 표기 불일치

**위치**: `_RE_STEP3_NON_CHOICE` (parser.py:1064)

```python
r'요약하고자\s*한다|영어로\s*완성|찾아\s*쓰시오|바르게\s*고치시오|어형\s*변화'
                                                          ↑
                                                          분류 체계는 "어형 변형"
```

분류 체계 룰: `r"본문에(서)?.*변형 (가능|허용)|어형|어법에 맞게"` — 어형 단어만 사용.
STEP3 파서: "어형 변화" — 단어 결합 다름.

원고에 "어형 변화" 표기가 실제로 있는지 확인 필요. 있다면 둘 다 보강 / 없다면 STEP3에서 "어형"만 쓰도록 단순화 가능.

(영향 작음, 일단 보류 권장)

### 2. INLINE_CHOICE 누락 패턴

분류 체계 발문 추출에서 STEP3 원고의 한 미분류 패턴이 발견됨:
- `"다음 글의 밑줄 친 ⓐ~ⓓ 중 어법상 오류가 있는 문장만을 고른 것은?"` (현재 STEP3에서 `_RE_STEP3_INLINE_CHOICE`로 안 잡힘 — "밑줄 친 부분 중"이 아니라 "밑줄 친 ⓐ~ⓓ 중"이고, "어법상 오류가 있는"이 "어법상 틀린 것"과 미스매치)

이런 변형은 분류 체계가 잡으므로 분류기 통합 후 자동 해결.

---

## 권장 순서 (사용자 결정 사항)

1. **지금**: 분류기 모듈 이식만 완료 (이미 끝남 — Task #9)
2. **1~2주 후**: 분류기를 신규 엔진/디버깅에서 활용 → 안정성 검증
3. **그 후 Tier 1 적용**: `_add_step3_choice_numbers()`만 분류 체계 호출로 변경 + 회귀 테스트
4. **Tier 2/3은 더 나중**: 다른 엔진에서 분류기 충분히 검증된 후

당장은 **STEP3 파서 무수정 유지**가 작업 일정에 가장 안전.

---

## 관련 파일

- 분석 대상: `yone-design-web/engines/workbook/parser.py` line 977~1933
- 분류 체계: `yone-design-web/engines/_taxonomy/` (이식 완료)
- 원본 분류 문서: `조판/원고_분류체계/03_분류체계_v1.md` 외
