---
name: project-sangil-voca-vivliostyle
description: 상일보카(상일여고1 26-2-중간) Vivliostyle 코드조판 — 납품 완료. 다음은 단어장 계열 엔진화(통합웹 리포)
metadata:
  type: project
---

**상일보카 = 상일여고1 26-2-중간 능률VOCA 어원편 Day31~45.** Part1 단어장(배재보카 계보, 우측 메모칸 없음) + Part2 워크북(배재 화이트북 A~D와 원고 형식 동일) 합본. **✅ 2026-08-20 납품 완료.**

**백엔드 = Vivliostyle(코드 조판). InDesign 아님.** 스크립트 = `조판/교재/단어장/상일보카/26-2-중간/automation/` (**README.md 먼저**, 맨 끝 "납품 완료·다음 단계" 항목 포함). gen_data.py(원고→data.json, 인식 게이트) → gen_theme.py(팔레트→배경 SVG 재생성) → render.py → build.py(2~3패스 + 간지 결합). 산출 = **A5+도련3mm(154×216)**, 메모면 포함 **259p** / `--nomemo` **234p**, 빌드 50초. 회귀 기준선 = `_backup/v2_최종/`.

**다음 단계 = 단어장 계열 엔진화** — 계획서를 **통합웹 리포에 커밋해 뒀다**: `~/dev/yone-design-web/docs/vivliostyle_단어장_엔진화_계획.md` (c0346f1). 요지: 교재 폴더는 git이 아니므로 코드를 거기 두지 말고, ①`core/render_vivlio/`(paged·bleed·verify·_base.css) ②`series/vocabook/`(계열 테마·렌더러) ③교재 폴더엔 config.json+원고만 으로 3계층 분리. 선례 = `engines/mockexam_v2_viv`(render_backend="vivliostyle"). 검증 = 상일보카를 config-only로 되돌려 같은 PDF → 배재보카 04로 계약 확인.

**디자인 근거**: 헤더는 사용자 제공 `automation/자료/내지헤더샘플.ai`를 **벡터 좌표로 실측 이식**(밴드 h15.27·좌하단 R15.27·태그 16.78×17.86 위각/아래R3.49·오른쪽 접힌 꼬리 2.23). 사진만 보고 추정하다 네 번 어긋났다 — **도형은 AI/SVG 원본을 받아 좌표로 옮길 것**. 본문 치수는 배재보카03 PDF 실측 이식.

**4면 헤더 체계**: ①Day시작(왼쪽)=밴드+큰 태그 ②그 다음 오른쪽=밴드+SANGIL VOCA ③이후 왼쪽=5.5mm 띠+작은 태그 ④이후 오른쪽=띠만. 측면 라벨은 오른쪽 면만·Day마다 8mm씩 하강. ①② 지정은 **2패스 빌드**가 보이지 않는 마커(DAYOPEN)로 면을 찾아 `@page :nth()`로 넣는다(마진 박스 내용만 바꾸므로 페이지 나눔 불변). `--nomemo`는 3패스(오른쪽 시작면 검출→미러 재렌더).

**Vivliostyle 함정**(전부 실측): 마진 박스에서 `position:relative`는 running()을 덮어 본문에 그려짐·`transform`/`visibility:hidden` 무시·세로 음수마진 잘림·여백 높이 초과 요소 잘림 → **도형은 전부 배경 SVG**. 본문에서도 `clip-path`+`drop-shadow` 동시 사용 시 요소 소실, `border-radius`는 자식을 안 자름. `@page :nth()`는 이름 규칙에 명시도로 밀림. **도련은 옮기는 게 아니라 늘리는 것**(요소를 페이지 끝에 붙이면 재단 후 폭이 줄어듦 — 측면 라벨에서 발생). **배경 SVG는 좌표 이동 시 박스도 키울 것** — `get_drawings()`는 클리핑 전 bbox라 "좌표는 맞는데 안 보임"이 생긴다, 고해상도 렌더로 눈으로 볼 것.

**데이터 처리**: 파생어→표제어 귀속은 **DP 단조정렬**(LCS/표제어길이, 접두어 매칭 불가 — corruption·disruption은 rupt만 공유). 475항목→242묶음, 단독 112개는 원고 구조상 정상. 원고에 없는 more with 어근·VOCA vs 묶음제목은 gen_data 상단 데이터 표.

관련: [[project_baejae_voca_wordbook]](디자인 계보), [[project_whitebook_problem]](워크북 원고 형식)
