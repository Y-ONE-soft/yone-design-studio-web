# 로컬 실행 (GitHub 리포 `Y-ONE-soft/yone-design-studio-web` main 기준)

이 폴더는 우리 배포용 리포 `Y-ONE-soft/yone-design-studio-web`의 작업 사본이다(2026-09-15, 이전 `YONE-DESIGN/YONE-DESIGN-WEB`에서 분리). 통합웹(`app.py`, 로그인)은 그대로 있고, 그와 별개로
로그인 없이 로컬에서 쓰는 **단독 실행기**(`bin/studio` → `studio_server.py`)를 얹었다.
단독 실행기는 `templates_local/base.html`(최소 머리띠)을 쓰고, 나머지 템플릿·엔진은 리포 것을 그대로 쓴다.

파이썬은 pyenv 3.14.3(`.python-version`). 추가 패키지는 `requirements-vivlio.txt`
(pymupdf·openpyxl·python-docx·numpy·pillow·fonttools·anthropic·flask·pyhwp·six·jsonschema·requests·beautifulsoup4·pyyaml).

| 무엇 | 명령 |
|---|---|
| 환경 점검 | `bin/viv-doctor` |
| CLI 조판 | `bin/viv --list` · `bin/viv "<책>" all` |
| **카탈로그** | `bin/studio` → http://127.0.0.1:5099/catalog — 디렉토리 → 틀 고르고 원고 올리면 새 책 |
| **웹 작업대** | `bin/studio` → http://127.0.0.1:5099/book-studio — 만든 책을 열어 값·글 수정 |
| 견본 이미지 | `bin/catalog snap <계열> <책>` · `bin/catalog snap-all` · `bin/catalog list` |

## 카탈로그(`/catalog`) — 디렉토리 → 틀 → 디자인 → 원고

```
디렉토리  교재 갈래. 분석본 · 워크북 · 포켓북 · 학교별 변형문제 · 동형모의고사 · 직전보충자료 · 리테 · 클리닉자료 · 단어장 · 기타. 카드의 **✎ 수정 · × 삭제**, 격자 끝 **+ 디렉토리** 로 고치고 늘리고 줄인다(`catalog/dirs.json`).
          새 것은 기타 앞에 들어간다. 지우면 안의 틀은 기타로 간다. 기타는 못 지운다.
틀        계열 코드 = 면 구성(레이아웃). 12개. 코드로만 늘어난다(새 디자인 개발 = 클로드 세션).
          틀은 디렉토리 하나에 속한다(`catalog/catalog.json` 의 `dir`, 없으면 기타). 화면에서 옮길 수 있다.
디자인    그 틀의 한 모습 = config(색·치수·서체) + overrides.css + 페이지 틀 이미지. 등록으로 늘어난다.
원고      디자인을 고르고 올리면 새 책.
```

네 화면:

1. `/catalog` — 디렉토리 카드만 (틀 수 · 점 색: 초록 바로 됨 / 주황 서체·자료 부족 / 회색 여기선 못 만듦 — 파이널은 Y.OS 접근이 필요). PDF 판정·결정 대기·새 틀 요청은 `/catalog/intake`(머리띠 **PDF 판정**, 처리할 게 있으면 개수 배지)
2. `/catalog/dir/<디렉토리>` — 그 디렉토리의 틀 타일들. 타일 아래 **📁 칸**을 바꾸면 틀이 그 디렉토리로 옮겨진다
   (`POST /api/catalog/series/<틀>/dir`). 지금은 12개 전부 **기타**에 있다.
3. `/catalog/<틀>` — 그 틀의 디자인 카드들 + **+ 디자인 등록**: 기본은 **완성본 PDF 올리기** → 재고 판정 → 이 틀의 초안 디자인
   (판정이 다른 틀을 가리키면 그쪽으로 등록하는 단추도 뜸 · 키 없으면 판정 없이 잰 값만으로). 보조 탭 **만든 책에서**: 이 틀로 만든 책을 골라 이름 붙이면 디자인이 됨
4. `/catalog/<틀>/<디자인>` — **페이지 틀**(원고 자리를 회색으로 비운 실제 지면 5장: 앞간지·시작면·본문 왼/오·뒤간지) +
   견본 사진 + 원고 넣기 → **[조판]** → PDF

디자인을 늘리는 순서: 디자인 하나로 책 만들기 → 작업대(`/book-studio`)나 `bin/viv <책> knobs --set=…` 로 색·여백 손보기
→ `bin/viv <책> build` → 그 틀 화면에서 **+ 디자인 등록**. 페이지 틀 이미지는 그 책에서 자동으로 뽑힌다.

- 폴더: `catalog/<틀>/designs/<id>/` (config.json · overrides.css · master_N.png · preview_N.png · design.json · **assets/ · 참고/**)
- **틀은 자기 재료를 디자인 폴더에 갖는다.** 로고·간지 조각(`assets/`)과 그것을 잘라낸 완성본 PDF(`참고/reference.pdf`)가
  디자인 폴더 안에 있고, config 의 `assets.src_pdf`·`finish.art_pdf` 는 그 상대경로다. nhj 맥 절대경로(`${STUDIO}/…`)에
  기대는 틀은 "서체·자료 부족"으로 뜬다(`routes/catalog.py` `_readiness` 가 디자인 폴더 안의 파일까지 본다).
  책을 만들 때 `assets/`·`참고/` 는 책 폴더로 같이 복사된다.
- 블랙북의 간지·MEMO·뒤 간지는 **코드가 그린다**(`core/render_vivlio/series/blackbook/art.py` → `build/art.pdf`).
  예전처럼 인디자인 완성본 면을 빌리지 않으므로 완성본 PDF 없이도 책이 나오고, 뒤 간지의 학교 이름은 config `cover`
  (`school_ko`·`school_en`)에서 온다. 화이트북은 아직 `참고/` 의 완성본 면을 끼운다(디자인 폴더 안에 있음).
- 명령줄: `bin/catalog list | add <틀> <이름> <책> | masters <틀> <디자인> <책> | snap <틀> <디자인> <책>`
- 디자인 config 에서 `options.expect`(책 고유 기대 수량)는 뺀다. 검수 엄격도는 디자인 config 를 따른다.
- **워크북**은 통합웹 파서(`engines/workbook_v2`)를 거친다 — Step1~3 원고(docx·hwp·hwpx)를 전부 올리고 학년·연도·월·유형을 적으면
  `원고/_job/` 에서 content.json → render_plan.json 을 만들고 조판한다. 파서 경고(미소비 원고·지문 수 불일치)는 조판 로그 앞에 붙는다.
- **포켓북·파이널**은 코드는 있으나 자료가 없다 — 포켓북은 코퍼스·분석본·삽화(nhj 맥 교재 폴더 + 드라이브), 파이널은 Y.OS 시험범위·되수확본.
  자료가 오면 `engines/pocketbook_viv`·`engines/final_viv` 카드 로직을 워크북처럼 붙인다(회색 점)


## PDF로 디자인 추가 (`/catalog/intake` · 머리띠 **PDF 판정**) — 클로드 키 필요

완성본 PDF(인디자인에서 내보낸 것)를 올리면:
1. PyMuPDF 로 잰다 — 판형·도련·여백·서체·글자 크기·색 (`routes/intake.py` `measure`)
2. 클로드가 틀 12개의 페이지 틀 이미지와 나란히 놓고 판정한다 — **design**(기존 틀, 값만 다름) / **new**(면 구성이 다름, 코드 필요) / **unsure**
3. design 이면 그 틀 밑에 **초안 디자인**을 만든다 — 기준 디자인 config 에 PDF 에서 읽은 손잡이 값(색·판형·도련)을 덮어쓰고,
   올린 PDF 의 면을 견본 사진으로 붙인다. 디자인 화면에 "초안" 표시가 뜨고, 조판해 보고 맞으면 **확인 완료**.
   올린 PDF 는 그 디자인의 **아트워크 원본**이 된다 — `참고/reference.pdf` 로 저장하고 config 의 `src_pdf`·`cover_pdf`·`art_pdf`
   (바깥 경로였던 것)를 그리로 돌린 뒤, 계열의 `theme` 단계로 로고·조각을 `assets/` 에 잘라 둔다(결과는 design.json `intake.artwork`).
   그래서 아무 자료가 없는 기기에서도 **완성본 PDF 하나 + 원고**로 책이 나온다.
4. new 면 `catalog/_intake/<id>/` 에 PDF 와 판정을 남긴다 → Claude Code 세션에서 "이 PDF 로 새 틀 만들어줘".

⚠ 초안은 색·판형은 잰 값이라 대체로 맞지만 **레이아웃은 틀 것**이다. 사람이 견본 사진과 대조해야 한다.

### 클로드 키 넣기

키는 **환경변수로만** 받는다. 리포·채팅·config 에 적지 않는다.

```bash
mkdir -p ~/.config/yone
echo 'export ANTHROPIC_API_KEY=sk-ant-...' > ~/.config/yone/env    # 본인이 직접
chmod 600 ~/.config/yone/env
bin/studio        # 이 파일을 읽어서 뜬다. 첫 줄에 "클로드: 켜짐" 이 찍히면 됨
```

모델은 `YONE_ASSIST_MODEL`(기본 `claude-opus-5`). 같은 키로 작업대의 클로드 칸도 켜진다.

## 웹 작업대(`bin/studio`)

- `studio_server.py` 가 `routes/book_studio.py` 의 blueprint 를 그대로 물려 Flask 로 띄운다.
  `templates/base.html` 은 이 실행기용 최소 껍데기다(원래 것은 통합웹 머리띠·로그인 포함).
- **인증이 없다.** 그래서 기본이 `127.0.0.1` 이다. 같은 네트워크에서 쓰려면
  `bin/studio --host 0.0.0.0 --port 5099` — 사무실 안에서만.
- 포트 바꾸기: `bin/studio --port 8080` 또는 `YONE_STUDIO_PORT=8080 bin/studio`.
- 작업대는 PDF 를 굽지 않고 `build/index.html` 만 만들어 브라우저(`@vivliostyle/core`)가 조판한다.
  PDF·인쇄본은 작업대의 **내보내기**(`export`) 또는 `bin/viv "<책>" build|print` 로 만든다.
- 클로드 칸을 쓰려면 `ANTHROPIC_API_KEY` 를 환경변수로 준 뒤 띄운다.

## 책이 보이려면

작업대와 `bin/viv --list` 는 **스튜디오 루트의 `조판/교재/` 트리**에서 `config.json` 이 있는
폴더를 책으로 잡는다. 지금 이 기기의 루트는 `~/Documents/작업/Y.ONE STUDIO` 이고 책은 0권이다.

책 한 권 = 폴더 하나:

```
~/Documents/작업/Y.ONE STUDIO/조판/교재/<계열 폴더>/<책 폴더>/
  config.json        ← 인계 폴더 책별_설정/<계열>/<책>/config.json 사본 (폴더 이름의 `__` 는 `/`)
  overrides.css      ← 있으면 같이
  원고/              ← 구글 드라이브 원고를 **복사**해 넣는다 (config.manuscript.files 의 파일명 그대로)
  assets/            ← 간지·표지 PDF 등 config 가 가리키는 자산
```

서체는 `~/Library/Fonts` 에서 **파일명 그대로** 찾는다(하위 폴더 안 봄). 전임자 서체 모음 1,607개를 거기 넣어 두었고
`bin/viv-doctor <책별_설정 폴더>` 가 37/37 이다. 새 서체는 파일을 `~/Library/Fonts` 에 넣기만 하면 된다. 루트를 다른 곳에 두려면 `YONE_STUDIO_ROOT=<경로>`.

## 통합웹(app.py)을 통째로 띄우려면

`python3 app.py` — `YONE_SECRET_KEY` 등 환경변수와 로그인 계정(`data/users.json`)이 필요하다. 로컬 단독 실행기만 쓸 거면 필요 없다.

## (참고) 인계 스냅샷에 없던 것

- 통합웹 **업로드 카드**(`templates/typeset_vivlio_book.html` + `engines/vivlio_book/engine.py`):
  `core.base.BaseEngine` 과 엔진 레지스트리가 통합웹에 있어 여기서는 돌지 않는다.
  새 책은 위처럼 폴더를 만들어 `bin/viv` 로 돌린다.
- 중등부(`middle`) 계열의 실제 조판 코드는 교재 폴더의 `automation/`(`코드_스냅샷/중등부_automation(리포밖).zip`).
- `scripts/studio_check/`(작업대 점검 도구), `tests/` 가 기대하는 통합웹 `app`.
