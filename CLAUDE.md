# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
`app.py:_run_pipeline`이 백그라운드 스레드로 다음을 순차 호출합니다:

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

- **`app.py`의 JSON 캐시**: `_read_json_cached`로 한 번만 디스크 read 후 메모리 보관, `_save_*`에서 직접 캐시 갱신. EDEADLK/EAGAIN/EINTR은 5회 backoff 재시도.
- **`_RetryingFileSystemLoader`**: Jinja `get_source`도 동일한 retry로 감쌈 (TEMPLATES_AUTO_RELOAD=True 환경에서 동시 요청이 .html을 동시에 읽을 때).
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
7. (필요 시) `app.py`에 폴더 탐색용 `/api/<id>/...` 엔드포인트 추가

`templates/typeset.html`(공용)을 그대로 쓰면 `engine.upload_spec`만으로 폼이 생성되고, 엔진별 자체 UI가 필요하면 `template_name` property로 별도 템플릿 지정.

## 데이터 파일 + 등록 수정 규칙 (필수)

- `data/subjects.json`, `data/schools.json`은 **Read 후 Edit**으로 부분 수정 — 전체 재작성 금지.
- 새 엔진을 추가할 때 `engines/registry.py`의 `_ENGINE_LIST`에서 기존 엔진을 삭제하지 않는다.
- subjects.json의 `engine_id`는 `material_id`와 정확히 일치해야 인덱스 카드 → 페이지 이동이 동작.

## 운영 규칙 (상위 CLAUDE.md에서 강제 — 자동 주입됨)

- **yonestudio.com**은 Cloudflare Tunnel로 localhost:5010에 묶여 있어 **Flask 재시작 = 즉시 실서비스 배포**. 코드 수정 → Flask 재시작 → localhost와 yonestudio.com 양쪽 모두 동작 확인까지가 작업 완료의 정의.
- **구글 드라이브 파일은 직접 수정 금지** — 반드시 로컬로 복사 후 작업 (`_gdrive_safe_copy` 사용).
- **버그 수정 격리**: A 케이스 수정이 B 케이스를 깨뜨리지 않도록 영향 범위를 최소화. 요청 범위 외 리팩터링 금지.

## 디버깅 팁

- 엔진 실행 후 `jobs/<job_id>/`에 `.settings.json`, `run.jsx`, `content.json`, `조판_로그.txt`가 남아있어 그대로 검사 가능.
- JSX 자체 디버깅이 필요하면 JSX 안에 `var f = File("/tmp/debug.txt"); f.encoding="UTF-8"; f.open("a"); f.writeln(...); f.close();` 패턴으로 로그 남기는 게 가장 안정적 (alert는 다이얼로그 떠서 자동화 막힘).
- `engines/workbook/jsx/run.jsx`의 `mapStepToStory`는 `settings.stepStoryMap`을 우선 사용, 없으면 모의고사 디폴트 매핑으로 fallback. 새 indd 템플릿은 `prepare_jsx`에서 stepStoryMap을 명시해 분기.

## 별도 JSX 모음 (참조)

`/조판/인디자인 스크립트/` 폴더에는 InDesign Scripts 패널에서 직접 더블클릭해 실행하는 단독 .jsx 파일들(`STEP1A1.jsx`, `MergeMockExam.jsx` 등)이 따로 있습니다. 이쪽은 Flask 시스템과 무관하며, 기존 운영자가 손으로 돌리던 흐름입니다. 단독 .jsx의 코딩 패턴(스토리 확보, Undo 그룹화, GREP 초기화, 기본 단락 스타일 로케일 처리, 인라인 아이콘 삽입, 프레임 브레이크 역순 처리)은 `engines/workbook/jsx/run.jsx`도 동일하게 따릅니다 — 둘 다 ExtendScript ES3이라 제약이 같습니다.

## 회고 / 가이드라인

새 엔진이 완성되거나 큰 버그를 잡았으면 `.claude/rules/development-guide.md`의 "과거 반복된 실수 목록" 섹션에 패턴을 추가합니다 (자동 주입됨). 다음 세션에서 같은 실수를 반복하지 않게 하기 위함.
