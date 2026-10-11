# CLAUDE.md

> **⚠ 2026-09-15 — 이 리포는 `Y-ONE-soft/yone-design-studio-web`(배포용, 이전 `YONE-DESIGN/YONE-DESIGN-WEB`에서 분리)이다.**
> 아래 본문은 이전 개발자(nhj) 아이맥 환경 기준이라 이 맥에서는 **다음이 없다**: `조판_자동화/`·`통합웹사이트/` 심볼릭 링크,
> launchd `com.yonestudio.flask`(:5010), InDesign. 이 맥에서의 실행은 `README_로컬실행.md` 기준 — `bin/studio` → http://127.0.0.1:5099/catalog
> (Vivliostyle 코드 조판 + 카탈로그, 로그인 없음). 인계 문서·작업 메모는 `docs/인계_20260914/`.
> 책 데이터는 `~/Documents/작업/Y.ONE STUDIO/조판/교재/`, 클로드 키는 `~/.config/yone/env`(리포·채팅에 적지 말 것).
> **웹 배포·Y.OS 연동(2026-09-15)**: `deploy/README.md`. Fly.io `yos-studio`(`Dockerfile`+`fly.toml`, yos-typeset 과 같은 방식),
> 인증 `core/webauth.py`(**2026-09-18 결정: 배포서버도 로그인 없음 `YONE_AUTH=off`**; 자체 로그인 `/auth/login`+`YONE_PASSWORD` 와 Y.OS HMAC 링크 토큰은 코드에 남아 있으나 안 씀 — yos-design-web 과 별개 프로젝트), 바깥 API `routes/api_v1.py`(`/api/v1`), 잡 `core/jobs.py`,
> Vercel Blob `core/blob.py`, 웹훅 `core/yos_hooks.py`, contents 데이터 어댑터 `core/sources/`, Y.OS 쪽 드롭인 `deploy/yos/*.ts`.
> (`core/notify.py` 는 예전 macOS 알림 모듈 — 웹훅과 다르다.) 테스트 `tests/test_webauth.py`·`tests/test_api_v1.py`.
> **디자인 단위(2026-09-21)**: 원자(인디자인 오브젝트) → 부품 → 블록 → 지면 → 구간 → 틀 · 옷 · 세트. 스키마 `core/schema/units.schema.json`, 설명 `docs/디자인_단위_스키마.md`,
> 코드 `core/units/`(store·render·decompose·sample), 화면 `/units` = 왼쪽 레일의 **「만들기」**(캔버스 — 지면·칸·블록 끌어 놓기) · `/units/library`(라이브러리·분해·JSON) (`routes/units.py`), 시드 `catalog/_units/`. 기존 계열 렌더러(`core/render_vivlio/series/*`)와 독립 — 납품 중인 책은 안 건드린다.

> **편집기 재현(기준 결과물을 「만들기」로 똑같이 만들며 녹화·비교·기능 수정)**: 절차 정본 `docs/편집기_재현/절차.md` — 작업 전에 처음부터 읽는다. **「작업 순서 — 확정」(2026-10-10) 절이 우선이고, 바꾸려면 사용자 승인부터.** 명령 `tests/e2e/replay.py`, 단위 폴더 `tests/e2e/replay/<단위>/`.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **완성본 PDF → 관리 등록 (2026-10-09, 병렬 세션 가능)** — 사용자가 PDF 와 라인업(관리 폴더: 포켓북·워크북·…)을 주면:
> 1. 워크트리(`EnterWorktree`)에서 `bin/register-design <PDF> <폴더> [이름]` (이름 없으면 파일 이름). 폴더에 틀이 여럿이면 틀 이름으로.
> 2. 출력된 **구성 목록**을 사용자에게 보인다 — 구성 = 서로 다른 면 모양, 되풀이되는 묶음(1면·펼침면·4면…)은 하나로, 한 번만 나와도 구성.
>    (편집기 재현은 2026-10-12 부터 **면 목록**이 만드는 단위 — 지면 보기 맨 위 「면」, 묶음은 「원본 차례 견본」. 절차 2단계 「면 나누기」)
>    대조: 출력의 `/design/…` 화면 + 「PDF 뷰어로 보기」·구성마다 「PDF에서 보기」. 틀린 곳은 사용자가 짚으면 `routes/catalog.py` `design_layouts`
>    기준을 고치고 **23개 전부 다시 돌려 전후 비교**(한 책만 맞추고 다른 책을 깨지 않게).
> 3. 커밋 → main 머지 → push → `deploy/fly-deploy.sh`(배포는 한 번에 하나 — 잠금이 알아서 기다린다, 네트워크 끊김도 재시도).
> - 디자인 폴더 이름은 무작위(`x…`)라 세션끼리 안 겹친다(d번호 안 셈). 공용 파일(catalog.json·dirs.json)은 안 건드린다.
> - 구성 기준(가정 금지): 표지·간지 같은 면 종류를 미리 정하지 않는다. 면 모양 = 구성 이름표(머리·바닥 라벨) · 맨 위/큰 제목 유무 · 삽화 갈래,
>   글이 적은 면·앞 구성과 생김새가 다른 면은 그림(색 무시)+글상자 배치+글자 수로 묶는다. 이름은 이름표나 가장 큰 글씨, '표지'라고 부르지 않는다.
> - 서버는 기동 때 모든 디자인의 구성을 미리 계산한다(`warm_layouts`) — 등록·배포 직후에도 「지면 보기」가 빠르다.
> - 화면에서는 관리 폴더의 **＋ → PDF 등록**(같은 함수 `routes/intake.register_pdf`, 잡으로 돈다).

> **편집기 제작 → 관리 등록 (2026-10-10)** — 디자인은 원래 편집기에서 만들어 관리로 들어온다(PDF 등록은 결과물용 임시).
> 관리 폴더 ＋ → **편집기 제작**(그 폴더 틀로 새 문서) → 편집기 문서 패널 **「관리에 등록」** → `catalog/<틀>/designs/x…/` =
> `units.json`(문서 묶음) + `참고/reference.pdf`(문서를 그린 결과) + 견본 그림 + `design.json`(`made: "editor"`). 다시 누르면 같은 카드를 새로 그린다.
> 카드 라벨 「PDF 등록」/「편집기 제작」(임시 구분). 편집기 카드의 「원고 넣기」 = `/units?design=<틀>/<id>`(그 편집기에 문서가 없으면 묶음을 들여옴).
> 문서 묶음(문서 파일 내보내기·가져오기) `core/units/package.py` · 「원고마다」 되풀이(구성 첫 쪽 이름 → 레코드 목록) `core/units/content.plan_pages`.
> ＋ → 간편 제작은 아직 자리만(`/easy`). **PDF 를 주거나 등록된 원본 PDF 를 지정하면** 편집기 재현 절차의 「작업 순서 — 확정」(2026-10-11 골자)을 그대로 돈다 — 원본 올리기(PDF 등록) → 면 나누기(지면 보기 「면」, `design_layouts` faces — 면 = 자리의 집합 · 1쪽/펼침면 · 이어짐 · 맨 앞/뒤, 되풀이 묶음은 원본 차례 견본으로만) → 대본 짜기(임시 글로 스타일 · 자리는 외부 연동 기준) → 가르기(처음 해 보는 동작) → 만들기+검사(고정 0.3mm · 원고는 바꿀 수 있나, 기능 안 되면 고치고 그 구성만 다시) → 원고 넣기(원고 덩어리를 순서대로, 자리가 맞는 면에) → 잇기 · 책 만들기 검사(원본 원고 전체 → 원본 PDF 차례·쪽 수) → 편집기 제작 등록 → 맞대기 → 반영. 단계마다 결과를 보여 확인받는다. 짜깁기 금지. 등록된 편집기 제작 카드는 관리에서 누르면 지면 보기(구성 = 면 이름·원고마다·이어 갈 면) → 「편집기에서 편집」. 체크포인트 태그 `1011-체크포인트1(워크북_기반_프로세스_정리)`.

> **참고자료(모든 세션 공용)**: `docs/참고자료/` — 외부에서 받은 자료를 원본 + 마크다운 README + JSON 으로 둔다(2026-10-09 교재 블록 지도는 지웠다 — 구성 이름·카드에 B1~B11 을 쓰지 않는다).

> 이 디렉터리(`조판_자동화/`)는 `통합웹사이트/` 심볼릭 링크와 동일합니다. launchd가 `통합웹사이트/app.py` 경로로 Flask를 spawn하므로 두 경로 어느 쪽으로 작업해도 같은 파일을 수정하는 것입니다.

## 프로젝트 개요

영어 교재 조판을 자동화하는 Flask 웹앱입니다. 사용자가 브라우저(localhost:5010 또는 yonestudio.com)에서 교재/단원/원고를 선택하면, 엔진이 원고를 파싱해 content.json을 만들고, JSX(ExtendScript)를 InDesign에 전달해 스타일을 적용한 .indd를 생성합니다. 빌드 도구나 테스트 프레임워크는 없고, 모든 동작은 Flask 라우트와 엔진 메소드의 호출로 이뤄집니다.

## 핵심 명령

| 작업 | 명령 |
|---|---|
| Flask 재시작 (코드 변경 반영) | `launchctl kickstart -k gui/$(id -u)/com.yonestudio.flask` |
| Flask 로그 (stdout/stderr) | `~/Library/Logs/yonestudio-flask.log` / `-error.log` |
| iCloud dataless 파일 강제 materialize | `find <dir> -type f -exec cat {} > /dev/null \;` |
| 의존성 설치 | `pip install -r requirements.txt` (현재 `flask>=2.3`만 명시) |
| 파서 단독 테스트 | `python3 -c "from engines.<id>.engine import <Cls>; ..."` |
| InDesign에 JSX 직접 전송 | `osascript -e 'tell application "Adobe InDesign 2026" to do script POSIX file "/path.jsx" language javascript'` (또는 `run-jsx-local` skill) |

코드가 변경됐는데 반영이 안 보이면 99%는 (a) Flask가 모듈 로드 시 캐시한 JSX/JSON이 stale, 또는 (b) iCloud Documents가 정적 파일을 dataless 상태로 evict했기 때문입니다. 위 두 명령(kickstart + materialize)을 같이 돌리면 해결됩니다.

## 아키텍처 빅 픽처

### 요청 흐름 (`/api/run/<material_id>` POST)
`routes/typeset.py:/api/run`이 `core/pipeline.py:run_pipeline`을 백그라운드 스레드로 실행해 다음을 순차 호출합니다 (C2-9 분리 — app.py는 앱 조립+블루프린트 등록만):

1. `engine.parse(uploaded, job_dir, log)` → 원고 → `content.json` + `step_*.json`
2. `engine.prepare_jsx(json_path, job_dir, log)` → 원본 .indd 복사 + `.settings.json` + `run.jsx` 임시 사본
3. `engine.run_indesign(job_dir, log)`가 있으면 호출, 없으면 `core.indesign.runner.run_jsx(jsx_path, ...)` — JSX는 osascript로 InDesign에 전달
4. `engine.verify(job_dir, log)` → 조판_로그.txt 파싱해 overflow/PDF 결과 반환

`core.job_manager`가 작업 ID 발급 + SSE 로그 스트리밍(`/api/stream/<job_id>`) + 결과 조회(`/api/result/<job_id>`)를 담당합니다.

### 엔진 시스템 (`engines/`)
모든 엔진은 `core.base.BaseEngine`을 상속하고 `engines/registry.py`에 한 줄 추가하면 등록됩니다. 각 엔진 디렉터리는 보통 `engine.py` + `config.json` + (옵션) `jsx/run.jsx`를 가집니다. config.json의 경로 키들은 `core.paths.resolve_config`가 STUDIO_ROOT 기준 절대경로로 변환합니다.

현재 등록 엔진(2026-05 기준): whitebook, blackbook, baenje, hanyoung, cover, cover_pocketbook, pocketbook, final, workbook, textbook_workbook, ebs_workbook, suneungteukgang_workbook, seseospecial, mockexam.

### 워크북 계열의 JSX 공유 구조
`workbook` / `textbook_workbook` / `ebs_workbook` / `suneungteukgang_workbook` 네 엔진은 **같은 `engines/workbook/jsx/run.jsx`를 공유**합니다. 차이는 `prepare_jsx`가 만드는 `.settings.json`의 내용 — 특히 `stepStoryMap`(각 STEP을 어느 페이지/마커의 스토리에 매핑할지)과 `workbook_type`("모의고사" / "교과서" / "EBS")으로 분기됩니다. JSX는 ExtendScript ES3이므로 `let`/`const`/화살표/템플릿 리터럴 사용 불가, JSON.parse는 `eval("(" + str + ")")`로 대체.

수능특강 엔진은 자체 `run_indesign`을 정의해 분석본(step1~2) + 문제본(step3) **두 단계로 순차 조판**하며, 다중 강 통합 시 `merge_lessons`가 두 번째 강 이후의 spread를 첫 강 indd 끝에 `spread.duplicate(LocationOptions.AT_END, dst)`로 추가합니다.

### 워크북 파서 (`engines/workbook/parser.py`)
docx/hwp/hwpx에서 단락 + 밑줄 정보를 추출하고, 발문/지문/선지/조건/보기 구조를 식별합니다. 핵심 정규식 `_RE_HEADER_NUM`은 의도적으로 라벨에 의존하지 않도록 일반화되어 있어(`p<page>` + 임의 영문 토큰 + 지문 번호), 새 발문 표현이 와도 패턴 매칭 룰을 추가할 필요가 거의 없습니다. Step3에서 footnote vs 표 셀 구분은 `step3_exclude_footnotes` cfg 옵션으로 제어 — 수능특강은 false (표 셀 본문 보존), 다른 엔진은 true (정답해설 footnote 제거).

### iCloud Documents / GDrive EDEADLK 회피
이 코드베이스의 모든 파일 I/O는 launchd-spawned Flask 컨텍스트에서 macOS APFS / iCloud Drive / Google Drive Stream의 EDEADLK(Errno 11)에 빠질 위험이 있습니다. 다음 패턴들이 적용되어 있습니다:

- **`core/webdata.py`의 JSON 캐시** (구 app.py): `read_json_cached`로 한 번만 디스크 read 후 메모리 보관, `save_*`에서 직접 캐시 갱신. EDEADLK/EAGAIN/EINTR은 5회 backoff 재시도. 사용자 계정도 여기서 로드(`load_users` — data/users.json + password_env, C2-8).
- **`core/webdata.py:RetryingFileSystemLoader`**: Jinja `get_source`도 동일한 retry로 감쌈 (TEMPLATES_AUTO_RELOAD=True 환경에서 동시 요청이 .html을 동시에 읽을 때).
- **`core.base.safe_copy_indd`**: 원본 .indd 복사 (raw read/write → /bin/cp -c → /tmp 경유 폴백).
- **`engines.final.extractor._gdrive_safe_copy`**: GDrive Stream 파일 안전 복사 — 로컬 미러 redirect(`~/Documents/yone-content-mirror/`) → `shutil.copy2` 단일 호출 + 지수 백오프(1+3+8+15+30초) 재시도. 새 GDrive 복사가 필요하면 직접 `shutil.copy2` 대신 이 함수를 사용해야 합니다.
- **JSX 템플릿 모듈 캐시**: `engines/cover/engine.py`, `engines/ebs_workbook/engine.py` 등은 모듈 로드 시 1회만 `_JSX_TEMPLATE_CONTENT`로 읽어 메모리에 보관. 템플릿 변경 시 Flask 재시작 필요.

자세한 건 `.claude/rules/gdrive_copy_robust.md` 참조 (자동 주입됨).

## 새 엔진 추가 절차

1. `engines/<id>/engine.py` — `BaseEngine` 상속, `material_id` / `display_name` / `upload_spec` / `parse` / `prepare_jsx` / `verify` 구현
2. `engines/<id>/config.json` — 경로 + 파일 매핑
3. `engines/<id>/__init__.py` (빈 파일)
4. `templates/typeset_<id>.html` — UI (slot 자동 생성은 `typeset.js`)
5. `engines/registry.py` — `_ENGINE_LIST`에 한 줄 추가 (기존 등록은 절대 삭제 안 함)
6. `data/subjects.json` — 인덱스 페이지에 카드 추가 (Read 후 Edit으로 append, 기존 항목 유지)
7. (필요 시) `routes/folders.py`에 폴더 탐색용 `/api/<id>/...` 엔드포인트 추가

`templates/typeset.html`(공용)을 그대로 쓰면 `engine.upload_spec`만으로 폼이 생성되고, 엔진별 자체 UI가 필요하면 `template_name` property로 별도 템플릿 지정.

## 데이터 파일 + 등록 수정 규칙 (필수)

- `data/subjects.json`, `data/schools.json`은 **Read 후 Edit**으로 부분 수정 — 전체 재작성 금지.
- 새 엔진을 추가할 때 `engines/registry.py`의 `_ENGINE_LIST`에서 기존 엔진을 삭제하지 않는다.
- subjects.json의 `engine_id`는 `material_id`와 정확히 일치해야 인덱스 카드 → 페이지 이동이 동작.

## 배포 규칙 — 로컬 반영 한 번 = 배포서버 반영 (MANDATORY, 2026-09-18)

배포서버는 **https://yos-studio.fly.dev** (Fly.io `yos-studio`, 도쿄 머신 1대, 볼륨 `/data`). 로컬 :5099 에 반영이 끝난 작업은 **같은 세션에서** 배포서버까지 올린다. 절차:

1. 워크트리에서 커밋 → `ExitWorktree(keep)` → 메인에서 `git merge --no-ff worktree-<이름>` (메인의 미커밋 파일과 겹치면 멈추고 사용자에게).
2. `bin/studio` 재기동 → http://127.0.0.1:5099 에서 바꾼 화면 확인.
3. `git push origin main`.
4. `deploy/fly-deploy.sh` — 메인 체크아웃에서. **커밋된 HEAD 만** 올라간다(`git archive`) — 다른 세션의 미커밋 파일은 섞이지 않는다. 빌드 5~10분. 비밀값은 없는 것만 채운다(클로드 키는 `~/.config/yone/env` 에서 자동).
   **배포는 한 번에 하나**(2026-10-07): 스크립트가 `/tmp/yos-studio-deploy.lock` 잠금 · 돌고 있는 `fly deploy` · `HEAD ≠ origin/main` 이면 멈춘다(exit 3). 멈추면 기다렸다 다시 — 잠금을 지우거나 우회하지 않는다. 배포 명령은 `run_in_background` 시간 제한(최대 2시간)을 넉넉히.
5. `curl -s https://yos-studio.fly.dev/api/v1/health` 가 `"ok":true,"claude":true` 이고, 바꾼 화면이 배포서버에서도 로컬과 같게 보여야 완료. 다르면 원인 해결 전까지 미완료.

- 건너뛰는 경우: 문서·CLAUDE.md·docs/ 만 바뀐 커밋. 사용자가 "로컬만"이라고 한 경우.
- 서버 확인만: `fly status -a yos-studio` · `fly logs -a yos-studio` · `fly secrets list -a yos-studio`(이름만 보임). 키 값은 리포·채팅에 적지 않는다.
- Claude Code 자동 모드는 `fly secrets set/import`·`fly ssh` 를 막는다. 비밀값이 새로 필요하면 사용자가 터미널에서 `deploy/fly-deploy.sh` 를 직접 돌린다(없는 것만 채우고 배포까지).
- 카탈로그(틀·디자인)는 볼륨 `/data/catalog` 이 정본. 기동마다 `deploy/catalog_sync.py` 가 리포에 **새로 생긴 틀·디자인만** 보탠다(있는 파일은 안 건드림). 기존 디자인의 config·css 를 고쳤으면 배포로는 안 옮겨진다 — `fly ssh` 로 따로.

## 운영 규칙 (MANDATORY)

- **yonestudio.com**은 Cloudflare Tunnel로 localhost:5010에 묶여 있어 **Flask 재시작 = 즉시 실서비스 배포**. 절차: 코드 수정 → Flask 재시작(kickstart) → (해당 시) export 실행 → **localhost:5010과 yonestudio.com 양쪽 모두** 실제 동작 확인 → 양쪽이 다르면 원인 해결 전까지 작업 미완료. 상세 절차는 `deploy-check` 스킬(`.claude/skills/deploy-check/`) 참조.
- **구글 드라이브 파일은 직접 수정 금지** — 반드시 로컬로 복사 후 작업 (`_gdrive_safe_copy` 사용).
- **버그 수정 격리**: A 케이스 수정이 B 케이스를 깨뜨리지 않도록 영향 범위를 최소화. 요청 범위 외 리팩터링 금지.
- **워크트리에서 작업할 때**: launchd Flask는 메인 체크아웃(`main`) 경로에서 뜨므로 워크트리(`.claude/worktrees/<name>`)의 변경은 **main에 머지(또는 체크아웃)한 뒤 kickstart**해야 반영된다. 워크트리 안에서 kickstart만 하고 "반영 안 됨"으로 판단하지 말 것. 배포 확인(localhost:5010 + yonestudio.com)은 머지 후 메인 체크아웃 기준으로 수행.

## 디버깅 팁

- 엔진 실행 후 `jobs/<job_id>/`에 `.settings.json`, `run.jsx`, `content.json`, `조판_로그.txt`가 남아있어 그대로 검사 가능.
- JSX 자체 디버깅이 필요하면 JSX 안에 `var f = File("/tmp/debug.txt"); f.encoding="UTF-8"; f.open("a"); f.writeln(...); f.close();` 패턴으로 로그 남기는 게 가장 안정적 (alert는 다이얼로그 떠서 자동화 막힘).
- `engines/workbook/jsx/run.jsx`의 `mapStepToStory`는 `settings.stepStoryMap`을 우선 사용, 없으면 모의고사 디폴트 매핑으로 fallback. 새 indd 템플릿은 `prepare_jsx`에서 stepStoryMap을 명시해 분기.

## 별도 JSX 모음 (참조)

`/조판/인디자인 스크립트/` 폴더에는 InDesign Scripts 패널에서 직접 더블클릭해 실행하는 단독 .jsx 파일들(`STEP1A1.jsx`, `MergeMockExam.jsx` 등)이 따로 있습니다. 이쪽은 Flask 시스템과 무관하며, 기존 운영자가 손으로 돌리던 흐름입니다. 단독 .jsx의 코딩 패턴(스토리 확보, Undo 그룹화, GREP 초기화, 기본 단락 스타일 로케일 처리, 인라인 아이콘 삽입, 프레임 브레이크 역순 처리)은 `engines/workbook/jsx/run.jsx`도 동일하게 따릅니다 — 둘 다 ExtendScript ES3이라 제약이 같습니다.

## 회고 / 가이드라인

새 엔진이 완성되거나 큰 버그를 잡았으면 `.claude/rules/development-guide.md`의 "과거 반복된 실수 목록" 섹션에 패턴을 추가합니다 (자동 주입됨). 다음 세션에서 같은 실수를 반복하지 않게 하기 위함.

## 응답 스타일 — caveman · ponytail · i-have-adhd (MANDATORY, 2026-09-16)

이 프로젝트의 모든 응답은 세 스킬 규칙을 **항상** 따른다. 전체 규칙은 `.claude/skills/{caveman,ponytail,i-have-adhd}/SKILL.md` — `.claude/settings.json` 의 SessionStart 훅이 세션 시작(startup/resume/clear/compact) 때 자동 주입한다. `.claude/` 는 gitignore 라 이 맥의 메인 체크아웃에만 있음(출처·버전·갱신법은 `.claude/skills/SOURCES.md`). 훅 출력이 컨텍스트에 없으면 첫 응답 전에 `/caveman` `/ponytail` `/i-have-adhd` 를 로드한다.

- **caveman (full)**: 서론·마무리 인사·군말·꾸밈(장식용 표·이모지) 없음. 도구 호출 전후 진행 설명 없음. 문장 짧게, 한 문장 한 뜻. 코드·명령·에러 문자열은 원문 그대로. 한국어 조사·어미는 유지(관사 삭제 규칙은 영어용). 보안 경고·되돌릴 수 없는 작업 확인·순서가 중요한 다단계 절차는 평문으로 쓴다.
- **ponytail (full)**: 코드는 사다리 순서로 — 필요한가(YAGNI) → 이 코드베이스에 이미 있나 → stdlib → 플랫폼 기능 → 이미 설치된 의존성 → 한 줄 → 그때서야 최소 구현. 요청 밖 추상화·스캐폴딩·리팩터링 금지. 버그는 증상 아닌 원인을, 호출자 전부 확인한 뒤 공유 지점에서 한 번 고친다. 트러스트 경계 검증·데이터 손실 방지·보안·접근성은 생략 금지.
- **i-have-adhd**: 첫 줄은 사용자가 바로 할 수 있는 행동 또는 답. 다단계는 번호 목록, 목록은 그룹당 5개 이하. 상태를 매 턴 다시 말한다("3/5 단계 완료"). 시간 추정은 분 단위로. 곁가지는 본론이 끝난 뒤 한 줄로. 끝은 2분 안에 할 수 있는 다음 행동 하나.
- 끄기: "stop caveman" / "stop ponytail" / "stop adhd mode" / "normal mode". 강도: `/caveman lite|full|ultra`, `/ponytail lite|full|ultra`.
- 예외: 커밋 메시지·PR·이슈·문서·코드 주석처럼 채팅 밖에 남는 글은 평문으로 쓴다(caveman Boundaries).
