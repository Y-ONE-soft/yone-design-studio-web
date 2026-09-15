# 비블리오스타일(Vivliostyle) 코드 조판 — 개발자 인계 (2026-09-14)

Y.ONE STUDIO 교재 내지를 InDesign 대신 **HTML + CSS + Vivliostyle CLI** 로 조판하는 시스템의
인계 자료다. 원고(docx·hwpx·xlsx)를 구조로 인식해 `data.json` 을 만들고, 계열별 HTML/CSS 로 조판한 뒤
PDF 마감(도련·재단 상자·간지), CMYK 인쇄본 변환, 자동 검수까지 한 명령으로 돈다.

## 읽는 순서

| 순서 | 파일 | 내용 |
|---|---|---|
| 1 | `00_README.md` | 이 문서 — 폴더 안내·실행 방법 |
| 2 | `01_아키텍처.md` | 3계층 구조(엔진·계열·책), 빌드 파이프라인, 명령어, 런타임, 작업대, 검수, 엔진 함정 |
| 3 | `02_계열별_현황.md` | 계열(blackbook·pocketbook·final·…)마다 원고 형식·지면 규칙·게이트·미결 |
| 4 | `03_책_목록.md` | 지금 config.json 이 있는 책 전부(계열·폴더·쪽수·최근 산출일) |
| 5 | `04_규칙_규약.md` | 인쇄 납품 규약, 간지·제본 기본값, 디자인 원칙, 개발 원칙 |
| 6 | `05_알려진_이슈_미결.md` | 코드가 못 지키는 틈, 책별 미결, 기술 부채 |

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `문서_리포/` | 리포 `docs/` 의 비블리오 문서 사본(엔진·자립화 계획·계열 전환 계획·작업 로그·동형 학교별 규칙), `vivlio_print_spec.md`(규약↔코드 대응표), webcore·mockexam 브리프. `vivliostyle_인수인계.md` 는 **7월 파일럿 시점 문서라 낡았다** — 역사 기록으로만 본다 |
| `문서_책폴더/` | 리포 밖 교재 폴더에 있던 문서(중등부 엔진 인계·레퍼런스 분석) |
| `책별_설정/<계열>/<책 폴더>/` | 각 책의 `config.json`·`README.md`·`overrides.css`·편집 이력 사본. 폴더 이름의 `__` 는 경로 구분자 |
| `작업메모_클로드/` | 작업하면서 쌓인 결정·사용자 피드백·함정 기록(클로드 작업 메모 원문). 규칙의 **왜**가 여기 있다 |
| `코드_스냅샷/` | `yone-design-web_vivlio.zip`(리포의 비블리오 관련 추적 파일, `COMMIT.txt` 의 커밋 기준) + `중등부_automation(리포밖).zip`(중등부 계열은 코드가 리포 밖 교재 폴더에 있다) |
| `책_목록.json` | `03_책_목록.md` 의 원본 데이터 |

**원본은 사본이 아니라 리포와 교재 폴더다.** 코드는 계속 바뀌므로 스냅샷은 인계 시점 확인용이고,
실제 작업은 리포에서 한다.

## 어디에 무엇이 있나

| 무엇 | 위치 |
|---|---|
| 리포 | `~/dev/yone-design-web` (GitHub `YONE-DESIGN/YONE-DESIGN-WEB`, 브랜치 `main`) |
| 엔진 | `core/render_vivlio/` (Vivliostyle CLI 는 이 안의 `node_modules`) |
| 계열 코드 | `core/render_vivlio/series/<계열>/` · 테마 `core/render_vivlio/themes/<계열>.css` |
| 실행기 | `bin/viv` |
| 웹 작업대 | `routes/book_studio.py` · `templates/book_studio.html` · 엔진 연결 `engines/vivlio_book/` |
| 교재(책) 폴더 | `~/Documents/작업/Y.ONE STUDIO/조판/교재/…` — 책마다 `config.json` 이 진실 |
| 원고 원본 | 구글 드라이브 → **반드시 로컬 `원고/` 로 복사해 쓴다**(드라이브 파일 직접 수정 금지) |

## 가장 짧은 실행

```bash
cd ~/dev/yone-design-web
bin/viv --list                                  # 책 목록
bin/viv "<책 폴더>" all                          # data → build → print → verify
bin/viv "<책 폴더>" watch                        # 라이브 미리보기
```

납품 파일은 `<stem>_인쇄.pdf`(CMYK) 하나다. `<stem>.pdf`(RGB 조판본)는 검수용.

## 인계 시점 규모 (2026-09-14)

- 책 59권 — pocketbook 23 · final 18 · middle 4 · workbook 3 · blackbook 2 · seseo 2 · vocacard 2 ·
  hankkeut · special · vocabook · vocaunit · whitebook 각 1
- 내지 인쇄본(`_인쇄.pdf`)이 있는 책 38권. 포켓북 19권·예비고1특강·세서특필 광문2(표지만)는 인쇄본 없음, 광문보카는 인쇄본이 조판본보다 오래됨(`03_책_목록.md` 비고)
- 계열 13개(등록 12 + 동형모의고사 `mockexam` 은 레지스트리 밖 — `bin/viv` 가 아니라 `series/mockexam/run.py` 로 돈다),
  엔진 파이썬 약 7천 줄 + 계열 파이썬 약 2만 8천 줄, 테마 CSS 약 4.5천 줄
- 중등부(`middle`)는 실제 조판 코드가 **리포 밖**(교재 폴더 automation, git 아님) — `코드_스냅샷/중등부_automation(리포밖).zip`
