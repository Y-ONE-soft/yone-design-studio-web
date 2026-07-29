# 파이널 직전보충(final) v2 전환계획 — W50 실측 정찰

작업 디렉터리: `/Users/nhj/dev/yone-design-web-summer` (브랜치 summer-2026).
이 문서는 **실제 전환 착수 전 정찰(recon)** 결과다 — 엔진 코드는 미수정, 실측·문서만.
검증: `engines/final/**` 전 파일 인벤토리 + parse/prepare_jsx/verify/run_indesign 정독,
`indesign_stepper.py`(JSX 생성기) 구조 실측, 과거 job 산출물(content.json·extracted.json·
scope_report) 실측, `core.template_spec`/코퍼스/픽스처 현황 확인. pytest 1053 passed(무회귀).

---

## 1. 구조 해부 (실측 인벤토리)

`engines/final/` 총 12개 소스 파일, **약 17,700줄** — 계열 최대.

| 파일 | 줄수 | 역할 | v2 분류 |
|---|--:|---|---|
| `parser.py` | 6,385 | extracted.json + 웹입력 → content.json(vol1/vol2 블록). 최대 파일 | **재사용(파서)** |
| `indesign_stepper.py` | 3,759 | **JSX 생성기** — vol1/vol2/vocab 3종 JSX를 파이썬 f-string으로 조립·실행 | **대체 대상(렌더)** |
| `engine.py` | 2,445 | BaseEngine 래퍼. `parse`(694–2229, ~1500줄)가 소스 수집 오케스트레이션. `prepare_jsx`/`run_indesign`/`verify` | 신규 v2 래퍼 |
| `vocab_fetcher.py` | 1,284 | 중요어휘 구글시트(시기별 워크시트) → Vol1 왼/오 어휘 | 재사용(소스) |
| `extractor.py` | 1,553 | **워크북 .indd를 InDesign으로 열어** 단락스타일 기준 텍스트 추출 → extracted.json | 재사용(소스, 별개 InDesign 패스) |
| `grammar_word_parser.py` | 1,058 | 어법수정 Word(.docx 2열 테이블) 파서 + `find_*` 8종 탐색기 | 재사용(파서) |
| `mothertongue_grammar_loader.py` | 462 | 마더텅 어법수정 Word 로더(YYMMQQ→원고) | 재사용(소스) |
| `olpo_mapper.py` | 306 | 고2 올림포스 기출 YYMMQQ↔(강,본문) 매핑 + 어휘시트 | 재사용(소스) |
| `scope_parser.py` | 220 | 시험범위 구글시트 파서 — `fetch_*_scope` 등 8종 | 재사용(소스) |
| `grammar_finder.py` | 166 | 어법 탐색 공용 헬퍼(W36 리터럴+정규화 폴백, 안전밸브) | 재사용 |
| `config.json` | 90 | GDrive 경로·추출 스타일·학교↔교과서 매핑·시트 URL | v2 config로 이관 |

**JSX 파일 없음** — `engines/final/jsx/`가 없고, 모든 JSX는 `indesign_stepper.py`
안에서 파이썬 f-string으로 **동적 생성**된다(`_build_vol1_jsx` ~1,800줄, `_build_vol2_jsx`
~1,000줄, `_build_vocab_jsx` ~680줄). 이것이 다른 엔진(고정 `run.jsx` + 데이터 주입)과
근본적으로 다른 점이다.

### 소스 탐색기 특성
`upload_spec`은 슬롯이 **단 1개(외부지문 어법수정 .docx, 선택)** — 나머지 소스는 전부
학교/학년/시험기간 메타로 **GDrive 폴더 자동탐색 + 구글시트 fetch**. 즉 파이널은
"업로드 엔진"이 아니라 "탐색·수집 엔진"이다. W48에서 `grammar_finder`가 리터럴 AND-체인을
정규화 subsequence 폴백으로 유연화(안전밸브 `YONE_FINAL_FUZZY_FIND`)했다.

---

## 2. 입력 소스 지도 (실측)

파이널 parse는 **두 부류의 외부 소스**를 병합한다.

### A. 워크북 .indd 추출분 (InDesign 패스 #1)
- `find_workbook_files`가 `config.gdrive_base/워크북/{학년}/{교재}`에서 워크북 .indd 탐색
  → 3단계 중복제거(`_drop_revised_duplicates`/`_drop_identical_duplicates`(MD5)/
  `_drop_superseded_workbook_versions`) → `extractor.extract`가 **InDesign으로 열어**
  `config.extract_styles`(문장배열 그랩/어법수정/영작배열 등 단락스타일)로 텍스트 추출
  → `extracted.json`(과거 job 실측: `{workbook_count, story_count, stories: list[174]}`).
- 즉 파이널은 **이미 조판된 워크북에서 지문을 역수확**한다.

### B. 웹시트·Word 소스 (네트워크/GDrive)
- **시험범위 구글시트**(`config.scope_sheet_url`, `scope_parser`): 학교별 문항범위/에디션/
  올포범위/영작제외/교과서과·제외과 — `fetch_scope_for_school`, `fetch_high3_scope`,
  `fetch_rp_edition/scope_lectures`, `fetch_olpo_scope_for_school`, `fetch_exclude_writing`,
  `fetch_textbook_limits/rm_lessons`.
- **중요어휘 구글시트**(`vocab_fetcher`): 시기별 워크시트(25-3/25-6/26-3/올포/마더텅) →
  Vol1 중요어휘 왼(빈칸)/오(원문).
- **어법수정 Word**(`grammar_word_parser`): 교과서작업 폴더 2열 테이블 .docx.
- **마더텅**(`mothertongue_grammar_loader`) / **딥러닝**(`find_deeplearning_grammar_files`) /
  **올포**(`olpo_mapper` xlsx) / **외부지문**(업로드 .docx).
- 모든 GDrive 접근은 `extractor._gdrive_safe_copy`(6-syscall 폴백) 경유 — 오늘 W48
  `coordinated_copy`로 근본 해결된 경로.

### content.json 구조 (실측 — job 2586a58a, 고3 55지문)
```
vol1: { 문장배열: [ {source, header:"18강 01", items:[6문장], passage} × 55 ],
        중요어휘_왼: str, 중요어휘_오: str }
vol2: { 어법수정:[110줄], 어법_헤더:[55], 서술형영작:[{korean,choices}×119],
        영작_헤더_상세:[54], 영작_헤더:[54] }
총_문장배열 / 총_어법수정 / 총_서술형영작 / _validation_warnings
```
과거 job 604건 중 다수가 `content.json`+`extracted.json`+`scope_report.txt` 보유 →
**중간산출이 디스크에 남아있다**(코퍼스 재료로 유효, §5).

---

## 3. 조판 방식 (v2化 난이도의 핵심)

**렌더 결정이 압도적으로 JSX 하드코딩**이다. `run_indesign` → `indesign_stepper.run_typeset`가
vol별로 `data`(content.json의 vol 블록)를 `/tmp/*.json`으로 떨구고, 파이썬이 조립한
거대 JSX를 `do script`로 실행. 그 JSX가 하는 일:

- **스토리 지목은 인덱스가 아니라 런타임 스캔** — 마스터 마커/`contents` 정규식으로
  문장삽입/요약/어휘 시작 페이지 오프셋을 찾음(`insertStartPageOff` 등). 스타일은 이름으로
  수집(`allParagraphStyles` 순회 — style_map 호환 ✓).
- **오버플로우 구동 레이아웃** — 블록을 흘려 넣다 오버플로우가 나면 런타임에 페이지 추가
  (`addFramePage`: anchorPage 계산→`pages.add`→마스터 상속→`geometricBounds`로 프레임 복제),
  프레임 하단 확장/축소(`expandBottom`/`topOv_keepContent`), 폰트 축소, **페이지 스왑**까지.
- **기하 조작** — 화살표 GraphicLine 앵커를 마스터에서 찾아 복제, pasteboard orphan 정리,
  rulerOrigin SPREAD_ORIGIN 강제, 크레딧 .ai 인입, GREP 폰트 보정(위첨자/Ž 등).
- vocab은 **별도 JSX 패스**로 새 페이지·프레임 생성.

핵심 판정: 워크북 v2(마커/마스터 스토리 데이터주입)·블랙북 v2(플랜 프레임기하)와 달리
**파이널의 레이아웃은 InDesign 조판 결과(오버플로우 여부)에 의존하는 런타임 피드백 루프**다.
"이 스토리가 넘치면 페이지를 더한다"는 결정은 파이썬 플랜 단계에서 선계산 불가 —
조판 후에야 알 수 있다. 이것이 **JSX 잔류가 불가피한 영역**이다.

---

## 4. 템플릿 (스타일 이식 가능성)

- 원본 2종: `config.template_vol1/vol2` = `조판/인디자인 원본/[원본]파이널(VolN)_내지.indd`
  (STUDIO_ROOT 상대 → 로컬 경로일 가능성 높음. GDrive면 `coordinated_copy`/`safe_copy_indd` 경유).
- `prepare_jsx`가 vol별로 `safe_copy_indd`로 로컬 복사 후 JSX가 in-place 편집·저장(PDF 미생성).
- `core.template_spec.extract_template_spec` 존재 → **파이널 템플릿 스펙 추출은 가능**.
  단 파이널 픽스처는 **아직 없음**(`tests/fixtures/template_spec_final*.json` 부재).
- 스타일 지목이 전부 **이름 기반**이라(§3) style_map 이식은 원리적으로 순탄. 다만 파이널은
  스타일 종류가 많고(config `extract_styles` 13종 + 고3 13종 + JSX 내 문자스타일) 마스터/
  마커 의미론이 복잡 → **인벤토리 픽스처를 먼저 뽑아 진실로 삼아야**(핸드북 1단계).

---

## 5. 검수 가능성 (코퍼스 성립 여부)

- **parse 오프라인 재실행: 부분 가능**. 최종 content.json은 (extracted.json + 웹시트 스냅샷)의
  결정함수. **과거 job에 extracted.json이 남아있어** 워크북 InDesign 추출을 재현하지 않고도
  파서 하류(parse→content.json)를 코퍼스화할 수 있다. 웹시트는 fetch 시점 의존이므로
  스냅샷 고정 필요(vocab/scope/olpo).
- 현행 verify는 **블록수 일관성 + 문장배열/삽입 1:1 + 중요어휘 시기별 카운트 + 오버플로우**로
  계열 중 최상세(`scope_report.txt` 산출). 완성본 역학습(W44)의 정답표 자동생성 대상이 될
  자격이 충분 — content.json 헤더/지문/어휘가 구조적으로 라벨링돼 있다.
- 결론: **하이브리드 코퍼스** — extracted.json(추출 스냅샷) + 웹시트 스냅샷을 픽스처로 고정하면
  GDrive 블라인드 없이 오프라인 검증 가능. `tests/corpus/final/` 신설.

---

## 6. v2 재사용 자산 (그대로 붙는 것 / 신규)

| 자산 | 파이널 적용 |
|---|---|
| 파서 재사용(핸드북 2단계) | ✅ `parser.py`+`grammar_word_parser.py`+소스로더 6종 전부 재사용. 파이널은 파서가 이미 완성도 최고 |
| `core.template_spec` | ✅ 도구 존재. 파이널 픽스처 신규 추출 필요 |
| `core/structure/style_map.json` | ⚠️ 파이널 섹션 신규 필요(스타일 이름 기반이라 이식 가능하나 종류 방대) |
| 렌더 실행기 3종(workbook_flow/blackbook_flow/render_flow) | ❌ 배치 의미론 불일치 — 파이널의 오버플로우 구동 레이아웃은 셋 중 어느 것도 안 맞음. §3 참조 |
| 검수 게이트(verify 단어보존/오버플로우/PDF) | 🔶 부분 — 파이널 verify가 이미 상세. 완제품 게이트·역학습 채점기 신규 접목 |
| 구조 인식기·블록 문법·슬롯 배정 | 🔶 content.json이 이미 구조화 → 슬롯 배정 개념 신규 매핑 필요 |

**신규 필요 핵심**: 파이널 전용 렌더 실행기(오버플로우 피드백 루프를 감당하는 `lib.jsxinc`
기반 `final_flow.body.jsx`) — 이것이 최대 신규 작업.

---

## v2化 난이도 판정: **★★★★★ (계열 최고 — 워크북 v2 이상)**

- **렌더 플랜化 가능 영역**(파이썬 이관 쉬움): 소스 수집·중복제거·파서·content.json 생성
  (이미 파이썬), 스타일 이름 매핑, 블록↔스토리 정적 배정, GREP 폰트 보정 규칙.
- **JSX 잔류 불가피 영역**(선계산 불가): 오버플로우 구동 페이지 추가/프레임 확장·축소/폰트
  축소/페이지 스왑, 화살표 앵커 복제, vocab 동적 페이지 생성. → **run.jsx를 데이터주입형
  고정 플로우로 완전 대체하기 어렵고**, "정적 배치는 플랜, 동적 맞춤(fit)은 JSX 헬퍼" 하이브리드가
  현실적. 핸드북의 "프레임브레이크=유닛분할" 모델이 파이널엔 부분적으로만 성립.

---

## 단계별 전환 배치 계획 (핸드북 10단계 매핑)

전제: **v1 완전 공존**(material_id `final_v2`, 출력 `_v2` 접미, registry append). 각 배치는
독립 커밋 + pytest 무회귀 + 사용자문서 무접촉.

| 배치 | 핸드북 | 내용 | 규모 | 검증법 | 리스크 |
|---|---|---|--:|---|---|
| **B0 안전망** | 8·골든 | 과거 job에서 extracted.json+content.json+웹시트 스냅샷을 `tests/corpus/final/`로 선별(고3/고1/교과서 각 1). `scripts/build_corpus.py` 시그니처 추가 | 소 | 코퍼스 로드 스모크 | 웹시트 스냅샷 누락 |
| **B1 템플릿 스펙** | 1 | `extract_template_spec`로 파이널 Vol1/Vol2 인벤토리 → `tests/fixtures/template_spec_final_vol1/2.json` 커밋. InDesign 1패스(무접촉·즉시닫기) | 소 | 픽스처 가드 테스트 | 스타일 종류 방대 |
| **B2 파서 하네스** | 2·7 | v1 파서 무수정 재사용 확인. `parse_extracted`를 extracted.json 픽스처로 오프라인 구동하는 테스트. content.json 골든 대조 | 중 | 오프라인 파서 유닛 | 웹fetch 의존 분리 |
| **B3 스타일맵** | 3 | style_map에 final 섹션 신설(이름 기반 이식) + 인벤토리 가드 확장 | 중 | `test_style_resolver` 확장 | 이름 오타/변형 |
| **B4 정적 플랜** | 3 | 블록→스토리/스타일 **정적** 배정을 파이썬 플랜化(오버플로우 무관 부분만). GREP 규칙 데이터화 | 대 | 플랜 유닛(코퍼스 유닛수/스타일/내용보존) | 정적/동적 경계 오판 |
| **B5 렌더 실행기** | 4 | `final_flow.body.jsx`(lib.jsxinc 기반) 신규 — **정적 배치는 플랜 소비, 동적 fit(페이지추가/프레임확장/스왑)은 JSX 헬퍼로 잔류**. vocab 서브패스 포함 | 대(최대) | 실 InDesign E2E, v1 산출 dump 대조 | 오버플로우 루프 재현, 회귀 |
| **B6 엔진 래퍼+게이트** | 5·6 | `final_v2/engine.py`, verify에 완제품 게이트+역학습 채점기 접목. registry/subjects append | 중 | `test_engine_registration` 확장 | v1 verify 상세도 계승 |
| **B7 E2E·스테이징** | 8·9 | 코퍼스 3종 전 파이프라인, data_corpus 리다이렉트. staging 카드/페이지 200 | 중 | E2E ok=true, 시각 게이트 | GDrive 실경로 안정성 |

---

## 파일럿 권고 (가장 단순한 소스 1종부터)

**고3(EBS 수능특강 분석편) Vol1 문장배열 단일 소스**를 파일럿으로 권고.
근거: ① job 2586a58a 실측처럼 고3은 소스가 워크북 추출분 중심으로 단순(교과서/올포/마더텅
혼합 없음), ② 문장배열 블록 구조가 가장 정형(`{source,header,items,passage}`), ③ Vol1만
먼저 세우면 vocab 서브패스·Vol2 어법/영작을 후속 분리 가능. 중요어휘·서술형영작·교과서
혼합·딥러닝은 파일럿 성공 후 순차 편입.

---

## 리스크 톱5

1. **오버플로우 구동 런타임 레이아웃(§3)** — 파이썬 선계산 불가 영역이 커, run.jsx 완전
   데이터주입화가 원리적으로 막힘. 하이브리드(정적 플랜+동적 JSX fit)로 타협해야 하며 이
   경계 설정이 최대 난제. **오판 시 오버플로우/페이지수 회귀.**
2. **다중 외부 소스 재현성** — 웹시트(scope/vocab/olpo) fetch가 시점 의존이라 코퍼스가
   스냅샷 고정에 의존. 스냅샷 누락 시 블라인드 검증으로 후퇴.
3. **워크북 추출 InDesign 패스(#1) 이중성** — 파이널은 조판 전에 **다른 InDesign 패스로
   워크북에서 지문을 역수확**. extracted.json 캐시로 우회 가능하나, 신규 케이스는 여전히
   GDrive 워크북 .indd 의존(코퍼스 밖 케이스 취약).
4. **규모 자체** — 17,700줄, parse만 1,500줄, JSX 생성기 3,759줄. 단일 배치로 불가,
   B4·B5가 각각 대규모. 부분 이관 중 v1/v2 동작 분기 관리 부담.
5. **스타일·마스터 의미론 방대** — extract_styles 13+13종 + 문자스타일 + 마커(section
   marker "2") + 마스터(D-마스터/A-chapter1) + 크레딧 .ai. style_map 이식은 가능하나
   누락 1건이 [경고]로 침묵 → 인벤토리 픽스처를 진실로 삼는 규율 필수.

---

## 결론

파이널 v2 전환은 **기술적으로 가능하나 계열 최고 난도**다. 파서·소스로더(약 1만 줄)는
이미 파이썬이라 **그대로 재사용**되어 실 이관 대상은 렌더(JSX 생성기 3,759줄)에 집중된다.
그러나 그 렌더가 **오버플로우 피드백 기반 동적 레이아웃**이라 워크북/블랙북식 "고정 플로우+
데이터주입" 패턴이 부분적으로만 성립 — **정적 배치는 플랜化, 동적 fit은 JSX 헬퍼로 잔류**하는
하이브리드가 유일하게 현실적인 v2 형태다. B0(코퍼스)·B1(템플릿 스펙)은 저위험 선행 가능하니
**여기서 착수**하고, 파일럿은 **고3 Vol1 문장배열 단일 소스**로 좁혀 오버플로우 루프의
플랜/JSX 경계를 실물로 검증한 뒤 소스를 순차 확장할 것을 권고한다.
