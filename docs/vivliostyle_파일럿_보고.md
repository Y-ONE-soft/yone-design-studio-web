# Vivliostyle 파일럿 보고 (W42)

동형모의고사 1교재(한영3, 코퍼스 029c4385)를 Vivliostyle(HTML/CSS 조판)로 재현해
InDesign 실물과 대조 — "원고 → 출판 품질 PDF"의 InDesign 대안 실현 가능성 실측.

- 실행일: 2026-07-22, 순수 오프라인 (실서비스·InDesign 완전 무접촉)
- 환경: @vivliostyle/cli **11.1.0** (core 2.44.1), Node v25.8.0, macOS
- 파이프라인: `engines/mockexam_v2` parser.build_ir → render.ir_to_render_plan
  (기존 코드 무수정 — 플랜 소비만. 라이브 재생성 플랜 214단락 = 저장본과 100% 동일 확인)
- 비교 기준(실물): `data_corpus/e2e_v2/029c4385/한영3_동형_v2.pdf`
  (mockexam_v2 E2E InDesign 출력, 8p 263×370mm)
- 산출물: `data_corpus/pilot_vivlio/hanyoung3/exam_vivlio.pdf` (8p, 동일 판형)
- 코드: `pilot/vivliostyle/` (render_html.py + theme.css + build.py + case_hanyoung3.json)

## 판정 요약: **조건부 전환 가능**

| 기준 | 실측 | 판정 |
|---|---|---|
| 1. 육안 구분 가능성 | 페이지 수 8=8, 1층 기계검사 양쪽 critical 0, 2층 체크리스트 양쪽 pass. 단, 줄바꿈 위치가 달라 p2부터 페이지 경계 내용이 최대 반 단 이동 | **나란히 놓으면 구분됨(줄바꿈), 단독으로는 동일 품질** |
| 2. 템플릿 재현 비용 | 케이스가 실제 사용하는 스타일 8종 **8/8 충실 재현**, 전체 인벤토리 18종 기준 충실 8 / 근사 1(조건) / 미실증 9(이 원고 미사용). 구현 실측 약 3시간(1세션) | **저비용 — 실측 기하 있으면 스타일당 ~10분** |
| 3. 속도 | Vivliostyle **6.0초**(원커맨드 2패스 전체, 웜) / 첫 실행 27.7초 vs InDesign **191초**(동일 케이스 typeset_log 실측 17:31:59→17:35:10) | **약 30배 빠름** |

## 1. 육안 구분 가능성 — 숫자

블라인드 대조 세트: `data_corpus/pilot_vivlio/hanyoung3/compare/blind_p1~8.png`
(좌우 무작위 배치, 매핑 `blind_mapping.json`) + 상세 크롭 7종(`crop_*.png`:
머리표/발문+지문/선지/요약박스/푸터/끝./서답형).

| 지표 | InDesign 실물 | Vivliostyle | 비고 |
|---|---|---|---|
| 페이지 수 | 8 | 8 | 동일 |
| 본문 총 행 수 | 822 | 809 | −1.6% |
| 지문 평균 자수/행 (p1) | 51.6 | 55.1 | +6.8% — 핵심 차이 |
| Q1 지문 행 수 | 14 | 13 | |
| 행간 실측 | 지문 14.0pt / 선지 15.0pt | 14.0pt / 15.0pt | 동일 |
| 행두 금칙 위반 | 0 | 0 | |
| 행말 금칙 위반 | **1** (여는 괄호로 행 끝) | **0** | Vivliostyle이 오히려 무결 |
| 1층 기계검사 (core.visual_inspect) | critical 0 / review 0 | critical 0 / review 0 | |
| 2층 체크리스트 (visual-review) | pass (suspect 2: 계속마커가 본문과 겹침, 행말 금칙 1) | pass (suspect 1: 빈 단 괘선 미표시) | 양쪽 review_result.json |

### 결정적 차이 톱5

1. **줄바꿈 위치** — InDesign 문단 컴포저는 어절 간격을 넓게 분배해 행당 자수가
   적고(51.6 vs 55.1), 그 누적으로 p2부터 페이지 경계 내용이 이동(최대 반 단).
   같은 원고를 "다시 조판"하는 용도로는 무해하나 **v1 실물과 행 단위 파리티는 불가**.
2. **양끝 정렬 질감** — InDesign은 단어 간격이 고르게 넓음, Chromium(greedy)은
   행마다 밀도 편차. 비조판자 육안으로는 근소, 나란히 보면 식별 가능.
   한글 자연폭도 실물이 4~6% 넓음(같은 폰트, 컴포저 차이).
3. **'다음 쪽에 계속 ☞' 앵커** — 실물은 본문 영역(339.1mm)이라 **본문과 겹침
   발생**(p3·p5), 파일럿은 여백 영역(342mm)이라 겹침 없음. 재현 위치 오차 ~3mm.
4. **머리표/푸터 미세 위치** — 저작권 줄 +1.5mm, 푸터 텍스트 +2.5mm, 머리표
   행높이 근사(전 항목 3mm 이내). 표 괘선 두께·셀 폭은 실측 반영.
5. **단 구분 괘선** — 실물은 마스터 개체(빈 단에도 전체 높이), CSS column-rule은
   콘텐츠 높이까지만(마지막 페이지 빈 단에서 미표시).

### 한국어 조판 세부 (실측)

- **원문자 ①~⑤**: 선지·본문 인라인(어법 밑줄형) 모두 실물과 동일 렌더 ✓
- **밑줄 runs**: IR marks → `<u>` 6단락 재현, 원문자+밑줄 결합(어법) ✓
- **HWP 사설영역 글리프**: `U+F003B`(요약 화살표)는 매핑 테이블로 ⬇ 변환 필요
  (실물은 InDesign 폰트 폴백) — 파일럿에 PUA_MAP 구현, 신규 글리프는 항목 추가 필요
- **금칙/줄바꿈**: `line-break: strict` + `hyphens: none`으로 위반 0
  (실물 1건보다 오히려 무결). `word-break: keep-all`은 실물이 한글을 어절 중간에서
  꺾으므로 쓰지 않음
- **탭 정렬**: InDesign 탭 스톱 → CSS `tab-size: 34.4pt` 근사(±2mm), 표기 정렬
  요구가 엄격한 템플릿이면 스팬 분해 방식 필요
- **자동 번호 이중 표기**: 실물의 "1.   1. 다음…"(스타일 자동번호 HY견고딕 +
  원고 번호) 그대로 재현 — 파이썬 카운터로 생성해 데이터에 박제됨

### 인쇄 적합성

- 전 서체 서브셋 임베드 확인(pdffonts): HCR돋움/바탕(R+B), HY견고딕(H2gtrE),
  바탕체, 나눔명조OTF — **실물과 동일 서체**(로컬 설치본). 나눔명조OTF는 Type 3으로
  임베드됨(Chromium CFF 처리) — 출력소 RIP에 따라 확인 필요, 나머지는 CID TrueType.
- 라이선스: 함초롬(HCR)·나눔은 임베드 허용 무료 서체. HY견고딕은 한컴오피스 번들
  상용 서체 — InDesign 출력과 동일하게 서브셋 임베드이나, 상업 인쇄 대량 전환 시
  라이선스 범위 확인 권장.
- PDF 1.7, 230KB(실물 601KB). PDF/X 변환은 미실측(후처리 ghostscript로 가능).

## 2. 템플릿 재현 비용

실측 방법: 실물 PDF를 PyMuPDF로 계측(폰트/크기/행간/들여쓰기/단 기하)해
`theme.css`로 번역. `tests/fixtures/template_spec_dh_hanyoung3.json`은 스타일
이름·프레임 좌표 제공(폰트 수치는 미포함 → PDF 실측으로 보완).

| 구분 | 스타일 | 판정 |
|---|---|---|
| 충실 재현 (8) | 문제 번호, 지문, 선지, 서술형 번호, 서술형답지, 다음 글을 읽고, 영어지문_순서, 테두리 | 폰트·크기·행간·들여쓰기·자동번호·볼드까지 실측 일치 |
| 근사 구현 (1) | 조건 | CSS 작성했으나 이 원고 미사용 — 실증 불가 |
| 미실증 (9) | 영단어, 점수, 영어지문 번호, 보스조건박스, 테두리 대화문, 영어지문 사본, 단락 스타일 1·2, 스타일 그룹 1>영어지문 | 케이스 미사용 (대부분 v2 플랜이 쓰지 않는 잔존 스타일) |

- 페이지 골격(263×370mm, 2단 108.2mm+간격 5.2mm, 본문 시작 52.15mm), 러닝 헤더
  (저작권+머리표 매 페이지), 러닝 푸터(계속 마커/괘선/쪽번호 counter(page)/학교명),
  마지막 페이지 '끝.'(@page :nth 2차 패스) 전부 CSS Paged Media로 재현.
- 소요: 분석+구현+튜닝 1세션 약 3시간. 스타일 자체는 실측값만 있으면 스타일당
  ~10분. **큰 비용은 스타일이 아니라 페이지 골격/러닝 요소** (학교별 머리표가
  제각각이면 학교당 헤더 테이블 1개 작성 필요).

## 3. 속도

| 단계 | Vivliostyle | InDesign (실측 로그) |
|---|---|---|
| 파싱+HTML | 0.06s | (파싱 포함) |
| PDF 생성 | 3.5s + 2차 패스 2.6s | 조판 179s + PDF 12s |
| **전체** | **6.0s** (첫 실행 27.7s — 브라우저 기동) | **191s** |

- InDesign 수치: 같은 케이스의 `meta/typeset_log.txt` (17:31:59 시작 → 17:34:58
  조판 → 17:35:10 PDF).
- 부수 효과: InDesign 앱 상태(유령 모달·행 판정·킬 금지)와 무관한 순수 CLI —
  병렬 실행·CI 가능. 오버플로우는 페이지가 늘어나는 것으로 흡수(오버셋 개념 없음).

## 결론과 다음 단계

**판정: 조건부 전환 가능.** "원고 → 신규 시험지 PDF" 용도로는 품질(기계·육안
검수 통과, 금칙 무결)·속도(30배)·운영성(무헤드 CLI) 모두 성립. 조건:

1. **행 단위 파리티는 목표로 삼지 말 것** — 컴포저 차이로 원리적으로 불가.
   신규 조판 용도(재조판·증분 수정 없는 흐름)부터 적용.
2. 학교별 머리표/푸터 골격 재현 비용(학교당 1회)과 미실증 스타일 10종의 검증이
   남음 — 다른 학교 케이스(성덕1·상일2 등 template_spec 보유)로 확대 필요.
3. HY견고딕 등 상용 서체 임베드 라이선스 확인, PDF/X(출력소 요구 시) 후처리 검증.

**2차 파일럿 권고 범위**: ① 동형모의고사 나머지 코퍼스 4케이스(성덕1/상일2/한영2)
자동 빌드 + 오버플로우·페이지 증감 거동 관찰, ② 조건/영단어 등 미실증 스타일이
있는 원고 1건, ③ 워크북 계열 1교재(STEP 구조·프레임 다수 — 난도 상승 지점:
stepStoryMap식 다중 영역을 CSS named page/region으로 옮길 수 있는지가 관건),
④ PDF/X-1a 후처리 + 출력소 시험 인쇄 1회.

## 재현 방법

```bash
cd pilot/vivliostyle && npm ci          # @vivliostyle/cli 11.1.0 (커밋된 lock)
python3 pilot/vivliostyle/build.py tests/corpus/mockexam/029c4385 \
    --case pilot/vivliostyle/case_hanyoung3.json \
    --out data_corpus/pilot_vivlio/hanyoung3
```

산출: `exam_vivlio.pdf`, `report_build.json`(단계별 시간), `build/exam.html`.
대조 이미지: `data_corpus/pilot_vivlio/hanyoung3/compare/` (blind_p1~8, crop 7종),
2층 리포트: `data_corpus/visual_review/{exam_vivlio,한영3_동형_v2}/review_result.json`.

---

# Vivliostyle 2차 파일럿 보고 (W43) — 워크북 내지 디자인 전면 검증

부교재 워크북 0a5da924("워크북E2E테스트", W40 수리 완료 실물 298p)의 **디자인 요소
유형 전수를 커버하는 대표 구간 13p**를 Vivliostyle로 재현해 실물과 대조 —
"시중 출판 수준 내지 디자인"의 재현 가능성 실측.

- 실행일: 2026-07-22, 순수 오프라인. **InDesign 완전 무접촉(0회)** — 아이콘·장식
  자산은 실물 PDF에 배치된 원본 래스터/임베드 폰트를 무손실 추출(예정했던 1회
  export조차 불필요했음)
- 비교 기준(실물): `data_corpus/round18/supp_0a5da924/워크북E2E테스트_내지_v2_2.pdf`
  중 p2·3(간지), 4·5(어휘선택), 22(본문O/X), 76(문장배열), 94(빈칸어휘),
  114(어법선택), 168(영작배열), 206~209(실전문제) — 렌더 플랜도 같은 job의
  `render_plan.json`(wb-flows-v1)을 소비만 함 (기존 코드 무수정)
- 산출물: `data_corpus/pilot_vivlio/workbook_supp/workbook_vivlio.pdf` (13p, 216×303mm)
- 코드: `pilot/vivliostyle/workbook/` (render_workbook.py + workbook_theme.css +
  build_workbook.py), 자산: `pilot/vivliostyle/assets/` (8종)

## 판정 요약: **워크북급 내지에서 전환 가능 (조건부)**

| 기준 | 실측 | 판정 |
|---|---|---|
| 디자인 요소 재현 | 13유형 중 **충실 11 / 근사 2 / 불가 0** (아래 판정표) | 전 유형 재현 |
| 기하 오차 | 매칭 109행 평균 \|dy\| **0.97mm** — 고정 시트 구간 0.0~0.7mm, 자동 흘림(STEP3) 구간만 최대 +6mm(행 나눔 누적, 비목표) | 고정 구간 사실상 일치 |
| 1층 기계검사 | 실물 발췌·파일럿 양쪽 **critical 0 / review 0** | 동급 |
| 2층 체크리스트 | pass (suspect 3: 서체 근사 2 + 흐름 이동 1) | pass |
| 속도 | 대표 구간 13p **4.0초** (플랜→HTML 0.01s + PDF 4.0s). 실물 전권 298p InDesign 조판+PDF **437초**(01:30:40→01:37:57 mtime 실측) | 비교 스코프 다름(13p vs 298p) — 페이지당 0.31s vs 1.47s |
| 구현 소요 | 실측·구현·튜닝 1세션 (측정 스크립트 포함) | 1차와 동급 |

## 디자인 요소 유형별 재현 판정표

| # | 요소 | 방식 | 판정 | 비고 (오차 실측) |
|---|---|---|---|---|
| 1 | 간지 색면+라벨 (STEP.01, 점선, 뒷면 목차·부교재) | CSS 색면 + 점선 border + 절대배치 | **충실** | 라벨 dy +0.11mm, 뒷면 텍스트 dy ±0.7mm |
| 2 | 간지 뒷면 플로럴 스트립 | 실물 배치 원본 래스터(2552×150) 90° 회전 | **충실** | 위치 실측 일치 |
| 3 | 상단 밴드+리본(화살촉)+스텝 로고+제목 | CSS clip-path polygon + TTMamablock(실물 PDF 임베드 서브셋 TTF) | **충실** | 리본·로고 실측 일치. 제목 자간만 근소 차이 |
| 4 | 홀수쪽 플로럴 밴드 | 원본 래스터(2552×213) 우측정렬 | **충실** | bbox 실측 일치(-0.4mm y 포함) |
| 5 | 지문 번호 (Yeongdo 12pt) + 사이드 프레임(빈칸어휘) | 로컬 동일 서체 + 절대배치(left:-13.4mm) | **충실** | x 12.6mm 일치, dy ±1mm |
| 6 | 어휘/어법 선택 괄호(파란 볼드, 번호 은닉) | 정규식 → span (실물 GREP 동작 재현) | **충실** | 행 나눔까지 일치(a1 매칭 11행 dy -0.25mm) |
| 7 | A2 본문 박스 + TF 버튼(O\|X) + 문항번호(LotteMartDream) | 박스 CSS + 원본 래스터 인라인 | **충실** | 박스 (23,39.3,168×36.4) vs 실물 36.5 |
| 8 | C1 문장배열 박스 + 화살표 답지 + 문제아이콘(체크박스) | 단락 음영 박스 + 원본 래스터 + 인라인 SVG | **충실** | 박스 y ±0.3mm; 아이콘은 SVG 재작도(외형 동일) |
| 9 | 빈칸 어휘: 프레임 브레이크(지문당 1페이지) + 번호 문자스타일 + 첫글자 핑크+비례 밑줄 | 시트 분리 + span 마크업 | **충실** | 18행 dy +0.12mm. 밑줄 폭은 근사식(2.4+2.95×자수) |
| 10 | 어법선택 상(선택)/하(밑줄 박스, 주황 괘선) + 영작 답지 | 상/하 프레임 시트 + 원본 래스터 | **충실** | 하단 박스 (20.1,164.0) vs 실물 (20,164) |
| 11 | 실전문제: 발문 번호 디자인(Elice Bd 12pt 파랑) + 2단 + 선지 + [요약문] 배경 + 조건/보기 박스 + 러닝 헤더/푸터 + 쪽번호 206~209 | CSS Paged Media(named page :left/:right, running(), counter-reset) | **충실** | Q01 dy +0.08mm; 페이지 배분 4p 동일. 흐름 내 위치는 행 나눔 누적으로 최대 +6~10mm |
| 12 | 간지 뒷면 A1~C2 토큰 서체(URWDIN-Medium) | 로컬 DIN Medium(Dinmed) 대체 | **근사** | 실물 임베드 서브셋이 bare CFF(690B)라 재사용 불가 |
| 13 | 본문 장평/자간 압축 (하단 박스류 ~86%, 실전 2단 자간) | transform:scaleX(0.86)+width 116% 근사, 전역 letter-spacing -0.025em | **근사** | 박스 행 수·높이는 일치시킴. 아래 "정직한 한계" 참조 |

## CSS로 안 되는(어려운) 지점 — 정직한 기록

1. **장평(가로 축소)**: 실물 하단 박스류·실전 2단은 같은 서체를 자연폭 대비
   최대 -12~-14%까지 좁혀 앉힘(자연폭 실측 0.44~0.47em/자 vs Chromium 0.53).
   CSS 표준에는 장평이 없음(NotoSans에 폭 가변축 없음) —
   `transform: scaleX(0.86)+width 116.28%` 근사는 고정 시트 안에서는 성립하지만
   **페이지 분할(2단 흘림) 구간에는 적용 위험**이 있어 전역 자간 보정(-0.025em)으로만
   근사. 그 결과 STEP3 흐름의 행 나눔 파리티는 원리적으로 불가(1차 결론과 동일).
2. **컬럼 흘림 내 margin-top 소실**: Vivliostyle 2단 fragmentainer에서 단락
   margin-top이 실측상 소실됨 → **spacing은 전부 padding-top으로** 구현해야 함
   (q3/p3/박스 wrapper 패턴). 재사용 시 필수 주의점.
3. **running 요소는 반드시 섹션 안에**: `position: running()` 블록을 named-page
   섹션 밖에 두면 무명 페이지가 생기고 named page가 첫 페이지에 안 붙음(1차 빌드
   실증) — 섹션 선두에 넣어야 함.
4. **`counter-reset: page N`은 리셋 페이지 자신이 N**: 첫 흐름 페이지를 206으로
   만들려면 205가 아니라 206으로 리셋 (실측).
5. **기본 p 마진**: 리셋 없는 `<p>` 마진이 박스 패딩 유무에 따라 붕괴/비붕괴를
   오가며 ±3mm 오프셋을 만듦 — 전역 `p{margin:0}` 리셋 필수.
6. **아이콘 앵커의 흐름 재배치**: 실물 TF 버튼은 JSX가 앵커로 삽입 — HTML 인라인
   `<img>`로 등가 재현되나, 답지처럼 '문항 뒤 고정 간격' 배치는 플랜의 icon 마커
   순서를 그대로 소비해야 함 (본 파일럿은 wb-flows-v1의 icon 필드 소비).

## 아이콘·장식 자산화 (InDesign 무접촉)

실물 PDF에 배치된 아이콘이 **원본 래스터 그대로 임베드**되어 있어 xref 추출로
무손실 자산화 — InDesign export가 불필요했음 (사용자 문서 접촉 0회):

| 자산 | 원본 해상도 | 용도 |
|---|---|---|
| `assets/tf_button.png` | 249×57 (알파X) | O\|X 버튼 (21.1×4.8mm) |
| `assets/arrow_answer.png` | 1121×59 (알파O) | C1 화살표 답지 |
| `assets/writing_answer.png` | 1974×141 (알파O) | STEP2 영작 답지 |
| `assets/floral_step12.png` / `floral_step3.png` | 2552×213 / 2541×213 | 홀수쪽 상단 장식 (스텝별 톤) |
| `assets/divider_strip.png` | 2552×150 | 간지 뒷면 우측 스트립 |
| `assets/TTMamablockB.ttf` / `TTMamablockL.ttf` | 임베드 서브셋 (~100KB) | 스텝 로고 A1/A2/…/S (미설치 상용 서체 — 내부 파일럿 한정 사용, 상용 전환 시 라이선스 확인 필요) |
| 문제아이콘(체크박스) | — | 벡터 실측값으로 인라인 SVG 재작도 |

색상 13종은 전부 실물 PDF 실측값을 CSS 변수(디자인 토큰)로 정의
(`workbook_theme.css :root`) — 채널 오차 <0.4%.

## 실측 세부

- 기하 대조: `data_corpus/pilot_vivlio/workbook_supp/geometry_deltas.json`
  (동일 텍스트 행 109쌍 매칭, 페이지별 dy 평균/최악). 고정 시트 구간(간지·STEP1·
  STEP2) 평균 |dy| 0.0~1.1mm, 자동 흘림(STEP3 p206 상당) +1.68mm/최대 +5.95mm.
- 블라인드 세트: `data_corpus/pilot_vivlio/workbook_supp/compare/blind_p01~13.png`
  (좌우 무작위, `blind_mapping.json`) + 좌실물/우파일럿 `pair_p01~13.png` +
  요소 확대 크롭 10종(`crop_header_logo/divider/tf_button/arrow_answer/checkbox/
  pnum_side/writing_answer/orange_box/q_number/summary_cond.png`).
- 1층: `data_corpus/pilot_vivlio/workbook_supp/inspect/machine_report.json`
  (양쪽 critical 0 / review 0). 2층: `data_corpus/visual_review/workbook_vivlio_supp/
  review_result.json` (pass, suspect 3).
- 구조 재현 방식: InDesign stepStoryMap의 "유닛 → 마스터 고정 프레임" 구조는
  **절대배치 시트**(간지·STEP1·STEP2 — 프레임 기하 실측 이식)로, 실전문제의
  연속 흘림은 **CSS Paged Media 2단**(named page + running + counter-reset)으로
  1:1 대응됨 — 1차 보고의 관건이던 "stepStoryMap식 다중 영역의 CSS 이식"은 성립.

### 결정적 차이 톱5

1. **행 나눔(자동 흘림 구간)** — InDesign이 같은 서체를 자간·장평으로 더 좁게
   앉혀 행당 자수가 많음. 전역 -0.025em 보정 후에도 STEP3 문항 위치가 최대
   +6~10mm 이동(문항 배분·페이지 수는 동일). 고정 프레임 구간은 행 나눔까지
   일치(a1 매칭 11행).
2. **장평 압축 박스** — 하단 박스류의 ~86% 장평은 scaleX 근사로 행 수·박스
   높이를 맞췄으나 글리프 형태가 실물(폭 축소)과 미세하게 다름(확대 크롭에서 식별).
3. **서체 2종 근사** — URWDIN-Medium(간지 토큰) → DIN Medium 대체,
   TTMamablock은 PDF 서브셋 재사용(내부 한정, 라이선스 미해결).
4. **스텝 제목 자간** — GmarketSans 한글 제목이 실물보다 1~2mm 넓음(실물 자간
   압축 미보정 — 헤더류는 보정 제외 영역).
5. **빈칸 밑줄 폭** — 실물은 단어별 실측 폭, 파일럿은 근사식(2.4+2.95×자수)mm —
   행 나눔에 ±1행 영향(빈칸어휘 페이지 내 흡수, dy +0.12mm).

## 결론과 다음 단계

**판정: 워크북급 내지에서 전환 가능(조건부).** 간지·고정 프레임 스텝·아이콘·
배경 박스·2단 실전문제까지 디자인 요소 전 유형이 재현되고(불가 0), 고정 구간
기하는 1mm 미만으로 실물과 일치한다. 조건은 1차와 동일 + 2가지 추가:

1. (1차와 동일) 행 단위 파리티 비목표 — 신규 조판 용도부터.
2. **장평**: 출판 품질 관점에서 장평이 필수인 템플릿은 scaleX 근사의 품질 한계를
   교정 담당자가 확인해야 함. 폭 가변축(wdth) 있는 서체로의 교체가 정공법.
3. **상용 서체 라이선스**: TTMamablock(로고)·URWDIN — 웹폰트/임베드 라이선스
   확보 또는 대체 서체 확정 필요.
4. 잔여 관문: ① 전권(298p) 규모 빌드의 속도·메모리 실측(대표 구간은 4초),
   ② 나머지 스텝(B1/B2/어법OX/빈칸어법/어휘선택2)의 시트 빌더 확장(구조는 동일
   패턴 — 스텝당 ~30분 예상), ③ 오버플로우 거동(실물은 '페이지 확장 +18' 로직 —
   Vivliostyle은 자동 페이지 증가로 흡수되나 고정 시트 구간은 넘침 검출 게이트
   필요), ④ PDF/X·출력소 시험 인쇄(1차와 공통).

## 재현 방법

```bash
cd pilot/vivliostyle && npm ci   # 1차와 동일 (커밋된 lock)
python3 pilot/vivliostyle/workbook/build_workbook.py \
    data_corpus/round18/supp_0a5da924/job/render_plan.json \
    --out data_corpus/pilot_vivlio/workbook_supp
```

산출: `workbook_vivlio.pdf`(13p), `report_build.json`, `build/workbook.html`.
