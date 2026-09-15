---
name: vivlio-selfserve-studio
description: Vivliostyle 자립화(S0~S7) — 클로드 없이 조판을 굴리기 위한 안전망·게이트·손잡이·작업대·클릭편집. 브랜치 vivlio-studio
metadata: 
  node_type: memory
  type: project
  originSessionId: 5b1c6620-f1e9-446b-8eba-4cd72c1b06bb
  modified: 2026-08-28T18:06:23.514Z
---

**목표: 클로드 세션 없이 비블리오 조판을 굴린다.** 2026-08-29 새벽 S0~S7 구축.
작업 브랜치 `vivlio-studio` (단계마다 태그 `S0-안전망`…`S7-클릭편집`).
**설계·함정·다음 단계는 전부 `~/dev/yone-design-web/docs/vivliostyle_자립화_계획.md`
(432줄)에 있다 — 이어갈 때 그것부터 읽는다.**

## 진단 (이게 방향을 정했다)

- **인터넷 문제가 아니라 터미널 문제**다. `bin/viv` 는 이미 100% 오프라인
  (`@vivliostyle/cli`+뷰어가 node_modules 에 있다). 막는 건 "어디를 고쳐야
  하는지 모름".
- **손잡이가 선언돼 있지 않았다** → 사용자는 뭘 만질지 모르고, 편집기를 만들 수
  없고, 클로드조차 매번 코드를 읽는다.
- **디자인 수정은 두 종류**다: 취향 조정(손잡이로 해결) vs 컨셉 오류(게이트로 해결).
  광교관 10차 시안의 대부분이 후자였다.

## 만든 것

| | |
|---|---|
| S0 | `scripts/vivlio_baseline.py` 면별 픽셀·텍스트 해시 (10권 43PDF/4,100면) |
| S1 | `bin/viv <책> watch` 라이브 미리보기 — **재렌더 0.4초**, 오프라인 |
| S2 | `design_gate.py` G-크기/대비/색면/글리프/미러 — 기본 경고, `strict` 로 결함 |
| S3 | `knobs.py` 계열이 손잡이 선언 (blackbook 19·vocaunit 20·vocabook 34) |
| S4 | 책 폴더 `overrides.css` 탈출구(맨 마지막에 얹힘) |
| S5 | `/book-studio` 내지 작업대 — 폼 자동생성 + 뷰어 미리보기 |
| S6 | `variants --knob --values` 시안 여러 벌을 한 장에 |
| S7 | 클릭 편집 — 지면 클릭 → `errata.json` → 재렌더 |

## 반드시 기억할 함정

- **동시 세션**: 리포 워킹트리는 하나인데 클로드 세션은 여럿이다. `checkout -b` 하면
  **다른 세션까지 끌려가고** autosync(180초, `git add -A`)가 그 미완성 편집을 내
  브랜치로 커밋한다. → **워크트리로 격리**(`~/dev/yone-web-vivlio`). `node_modules`
  는 gitignore 라 심볼릭 링크로 빌려 온다. autosync 는 `cd $REPO` 가 박혀 있어
  워크트리를 자동 커밋하지 않는다(손으로 커밋). 교재 폴더는 못 가르므로 상대가
  만지는 책은 **작업에서 뺀다**.
- **autosync 가 브랜치를 안 봤다** → main 에 가드 커밋(`697cad7`). 원래 있던 잠복 결함.
- **빌드가 죽었는데 옛 PDF 가 남아 회귀 대조가 통과**했다 → `compare --newer-than`.
  회귀 게이트는 "무엇을 쟀나"만큼 **"그게 새 결과인가"** 를 봐야 한다.
- **Vivliostyle 은 조판 결과 DOM 에 임의 속성을 안 옮긴다**(`data-ref` 소멸).
  **class 는 남는다** → 자리표를 `vrefN` 클래스로 싣고 `build/refs.json` 로 표를 낸다.
- **클래스 하나 얹었다가 26·61면이 어긋났다** — 대화문 줄엔 원래 클래스가 없었다.
  글자는 하나도 안 틀려서 **회귀 대조가 아니면 못 봤다.**
- **`--sample` 이 블랙북에선 파일명만 바꿨다**(내용 전권) → 작업대가 116면을 브라우저에서
  조판하려다 멎었다. 진짜 견본 구현(393KB→31KB). 견본 측정값은 `heights_견본.json` 로
  분리(전권 표를 덮어써 "문항 높이 8" 사고).
- **config.json 을 통째로 다시 쓰면 손 서식이 사라진다** → `knobs.patch_text` 부분 치환
  (실제 책 왕복이 바이트 동일). 한 번 뒤집고 백업에서 되돌렸다.
- **디자인 게이트 오탐 다섯**: 엔진 표식(1pt 미만으로 거른다)·러닝 요소(판면 밖)·
  본문 최소 크기는 책마다 다름(A5 단어장 6pt, 기본은 끔)·WCAG 단일 임계(3.0 경고 /
  3.0~4.5 참고 한 줄, 색 조합으로 묶기)·평평한 색 띠는 장식이 아님(경계선 밀도).

## 기존 3권 디자인 위반 (고치지 않았다 — 납품 중)

상일보카 헤더 `SANGIL VOCA` **흰 글자가 파스텔 위 1.7:1**(우리 규칙 "흰 글자는
deep 위에만" 위반) · `·` 머리기호 66번. 블랙북 해설 간지 `Unit 01` 흰 글자 1.8:1.
광문보카 예문 강조 주황 2.4:1 (2,447곳). **신규 조판은 `verify.design.strict` 를 켠다.**

관련: [[project_blackbook_vivliostyle]] [[project_sangil_voca_vivliostyle]]
[[project_gwangmun_voca_vivliostyle]] [[project_gwanggyo_prehigh1_special]]
[[project_middle_regular_gachisaegim]] [[feedback_typeset_palette_three_tier]]
[[feedback_no_glyph_decoration]] [[feedback_no_mirrored_page_art]]
