# Vivliostyle 단어장 계열 엔진화 — 계획 (2026-08-20) · **완료**

> 이 계획은 실행됐고, 단어장뿐 아니라 **블랙북까지 포함한 계열 엔진**으로 구축됐다.
> 결과 문서는 **[`docs/vivliostyle_엔진.md`](vivliostyle_엔진.md)** 이다 — 설계·실행·함정·
> 회귀 기준선이 거기 있다. 아래는 착수 시점의 계획으로 남긴다(왜 이렇게 나눴는지의 기록).
>
> 실제로 달라진 점: ② 계열이 `core/render_vivlio/series/vocabook/` **과**
> `series/blackbook/` 둘이 됐고, ① 공용 백엔드는 두 책의 교집합으로 잡혔다
> (`paged`·`bleed`·`verify` 에 더해 `cli`·`stage`·`probe`·`measure`·`svg`·`config`·`book`).
> npm 은 `core/render_vivlio/` 소유로 옮겼다.

---

상일보카(상일여고1 26-2-중간) **납품 완료**. 그 결과물을 시드로 단어장 계열을
통합웹 엔진으로 승격하는 것이 다음 단계다. 이 문서만 읽으면 이어받을 수 있게 정리한다.

## 지금 어디까지 되어 있나

| | 위치 | 상태 |
|---|---|---|
| 상일보카 조판 일체 | `조판/교재/단어장/상일보카/26-2-중간/automation/` | 납품 완료. **git 아님** |
| 공용 빌드 러너 | `core/render_vivlio/` (build/case/mockexam/themes) | 동형 계열만 사용 중 |
| Vivliostyle 엔진 선례 | `engines/mockexam_v2_viv/` | `render_backend="vivliostyle"` 분기, 부모에서 파서·플랜 상속 |
| CLI | `pilot/vivliostyle/node_modules` (@vivliostyle/cli 11.1.0) | 파일럿 폴더에 빌붙어 있음 |

상일보카 산출: A5+도련3mm(154×216), 메모면 포함 259p / 메모면 없음 234p,
간지 앞뒤 결합·TrimBox 전면 지정. 빌드 50초(2패스).

## 왜 옮겨야 하나

상일보카 `automation/`은 **git이 아닌 교재 폴더**에 있다. 다음 책에 복사하는 순간
포크가 늘고 롤백도 안 된다. 그리고 거기서 나온 것 중 **대부분이 책과 무관한 공용 자산**이다.

## 3계층

### ① 공용 백엔드 — `core/render_vivlio/`
상일보카에서 끌어올릴 것:

- `paged.py` — 보이지 않는 마커(`DAYOPEN`)로 특정 면 찾기 → `@page :nth()` 생성,
  좌/우면 판정, 미러 재렌더(3패스). **마진 박스 내용만 바꾸면 페이지 나눔이 불변**이라는
  계약이 핵심.
- `bleed.py` — 도련 상수, TrimBox 찍기, 간지 앞뒤 결합.
  ⚠ `set_cropbox` 를 먼저 부르면 TrimBox 가 되돌아간다. MediaBox 원점 기준으로 찍을 것.
- `verify.py` — 본문영역 초과 / 도련 미달 색면 / TrimBox / 준-빈면 검사.
  indd 덤프 기반 게이트 43종을 못 쓰는 자리를 이게 메운다.
- `themes/_base.css` — `@page` 골격 + 러닝 요소 규약(아래 제약 주석 포함)

### ② 계열 — `core/render_vivlio/series/vocabook/`
단어장 계열(상일·배재·광문·한영보카) 공통: 헤더 4면 체계, 단어 블록 표 구조,
도형 생성기(`gen_theme`), 워크북 A~D 렌더러, 정답 렌더러.

### ③ 책 1권 — 교재 폴더엔 `config.json` + 원고만
판형/도련 · 팔레트 6줄 · 섹션 구성 · 간지 PDF 경로 · Day 시작 규칙 · 메모면 유무.
현재 상일보카의 `theme.css` 팔레트와 `gen_theme.py` 상수(BAND_H/BAND_R/TAG/
FOLD_W/STRIP_H/TINT_W/BLEED)가 그대로 이 스키마다.

## 순서

1. ②를 상일보카 코드에서 추출 → **상일보카를 config-only 로 되돌리고 같은 PDF가
   나오는지 대조**(쪽수·주요 좌표 일치). 회귀 기준선 = `_backup/v2_최종/*.pdf`
2. **두 번째 책을 config 만으로** — 배재보카 04회차 권장(디자인 계보·원고 형식 동일).
   여기서 안 되는 게 계약의 구멍이다.
3. registry + subjects 카드 등록(`docs/v2_전환_핸드북.md` 절차 동일)

## 같이 정리할 것

- **npm**: `core/render_vivlio/package.json` 커밋 + `npm ci`. 지금은 `pilot/` 것을 빌려 씀
- **서체**: 리포에 넣지 말고 로컬 설치본 복사(Noto OFL·Elice DX 네올리·Bebas)
- **검수**: `core/visual_inspect`·검수 에이전트는 PDF 기반이라 그대로 붙는다
- **InDesign 잔류**: 기존 책 재판·수정, 표지·목업

## Vivliostyle 함정 (상일보카에서 실제로 데인 것)

마진 박스(러닝 요소):
- `position: relative` → `position: running()` 이 덮여 **본문에 그대로 그려진다**
- `transform: rotate()` / `visibility: hidden` **무시된다**
- 세로 음수 마진은 잘린다(가로 음수 마진 + 같은 크기 패딩만 통함)
- 박스 높이(=페이지 여백)를 넘는 요소는 잘린다
- → **마진 박스 안 도형은 전부 배경 SVG**(feDropShadow 포함)

본문/공통:
- `clip-path` + `filter: drop-shadow()` 동시 사용 시 **요소가 통째로 사라진다**
- `border-radius` 는 자식을 자르지 않는다 → 장식은 배경 SVG 로 구울 것
- `@page :nth(N)` 은 `@page <이름>` 규칙에 **명시도로 밀린다** → 이름과 함께 지정
- `@page` 배경의 `repeating-linear-gradient` 는 주기가 어긋난다 → SVG data URI
- 배경 SVG 는 좌표를 옮기면 **박스(width/height)도 같이 키울 것**.
  ⚠ `get_drawings()` 는 클리핑 전 bbox 라 "좌표는 맞는데 안 보이는" 상황이 생긴다.
  좌표 확인으로 끝내지 말고 **고해상도 렌더로 눈으로 볼 것**
- 도련은 **옮기는 게 아니라 늘리는 것**. 재단선에 닿는 색면을 3mm 더 그린다
  (요소를 페이지 끝에 붙이면 재단 후 폭이 3mm 줄어든다 — 측면 라벨에서 실제로 발생)
