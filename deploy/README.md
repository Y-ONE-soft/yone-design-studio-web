# 디자인 스튜디오 배포 + Y.OS 연동 (최종 구성)

> 대상: 스튜디오를 올리는 사람 + core·contents·design(Vercel, Next.js) 쪽 개발자.
> 코드 기준 2026-09-15. 스튜디오 쪽 구현: `core/webauth.py` · `core/jobs.py` · `core/blob.py` · `core/yos_hooks.py` · `routes/api_v1.py` · `core/sources/`.
> Y.OS 쪽에 넣을 파일: `deploy/yos/*.ts` (복사해서 쓰면 된다).
> 그림: [`docs/인프라_구성도.drawio`](../docs/인프라_구성도.drawio) · [`docs/인프라_구성도.png`](../docs/인프라_구성도.png)

## 0. Y.OS 가 이미 쓰는 것 위에 얹는다

| 항목 | Y.OS 현행 (core · contents · design) | 스튜디오 |
|---|---|---|
| 앱 호스팅 | Vercel (`sin1`) | — (화면은 Vercel 앱들이 담당) |
| 조판 컨테이너 | **Fly.io** `yos-typeset` · `yos-design-typeset` (도쿄 `nrt`, `scripts/typeset`) | **Fly.io `yos-studio`** — 같은 플랫폼·리전, 머신 1대 + 볼륨 |
| 로그인 | Auth.js(구글) + 앱 간 **HMAC 링크 토큰**(`CHAT_LINK_SECRET`, `signWidgetToken`) | **같은 꼴의 표** — `STUDIO_LINK_SECRET`. 스튜디오엔 로그인 화면 없음 |
| 서비스 호출 | `TYPESET_SERVICE_URL` + `SERVICE_TOKEN` | `STUDIO_SERVICE_URL` + `SERVICE_TOKEN` |
| 파일 | **Vercel Blob** (`@vercel/blob`, private + `presignUrl`) | PDF·미리보기를 **같은 스토어**에 (`BLOB_READ_WRITE_TOKEN`) |
| DB | Neon Postgres (앱별 스키마) | 안 씀 — 책·디자인·잡은 Fly 볼륨의 파일 |
| 클로드 | `ANTHROPIC_API_KEY` | 같은 키 (PDF 판정·작업대 클로드 칸) |

```
 사용자 ─▶ core / contents / design (Vercel)   ← 로그인·데이터·사용자 화면
              │ 링크 토큰(사람) · SERVICE_TOKEN(시스템)
              ▼
 yos-studio.fly.dev  (Fly.io nrt · 머신 1대 · 볼륨 /data)
   /catalog · /book-studio   디자이너 화면            /api/v1   contents·design·앱이 부르는 계약
   조판: data.json + 디자인 → Vivliostyle → Chromium → PDF → Ghostscript CMYK → verify
              │
              ├─▶ Vercel Blob   PDF(private) · 디자인 미리보기(public)
              └─▶ 웹훅          render.finished · design.changed  (x-studio-signature)
```

역할: **contents = 데이터의 주인**(지문·문항·단어·시험범위), **스튜디오 = 지면의 주인**(틀·디자인·조판).
서로 복사하지 않고 API 로 읽는다. 조판은 어느 화면에서 눌러도 `POST /api/v1/renders` 하나.

## 1. Fly.io 에 올리기 (yos-typeset 과 같은 순서)

한 명령: `fly auth login` 뒤 **`deploy/fly-deploy.sh`** (앱·볼륨·비밀값·배포·헬스) → **`deploy/fly-deploy.sh fonts`** (서체). 아래는 그 안에서 하는 일이다.

```bash
brew install flyctl && fly auth login                 # 최초 1회 (yos-typeset 을 올린 계정)
cd yone-design-studio-web

# ① 앱 + 볼륨 (fly.toml 이 있으니 이름·리전만 확인)
fly apps create yos-studio --org personal                # fly.toml 의 app 이름과 같게
fly volumes create studio_data --region nrt --size 10   # 책·디자인·잡·서체. 10GB 면 수백 권

# ② 비밀값 — 2절
fly secrets set \
  YONE_PASSWORD=<스튜디오 로그인 비밀번호> \
  SERVICE_TOKEN=$(openssl rand -base64 24 | tr -d '=+/') \
  YONE_SECRET_KEY=$(openssl rand -hex 32) \
  YOS_ORIGINS=https://yos-contents-web.vercel.app,https://yos-design-web.vercel.app,https://yos-core-web.vercel.app \
  BLOB_READ_WRITE_TOKEN=<contents 의 Blob 스토어 토큰> \
  ANTHROPIC_API_KEY=<키>
fly secrets list                                       # 값은 안 보인다. 이름만 확인

# ③ 배포 (첫 빌드 5~10분: chromium·node·pip)
fly deploy
fly scale count 1                                      # ★ 볼륨 달린 단일 머신. 늘리지 않는다
curl -s https://yos-studio.fly.dev/api/v1/health       # {"ok":true,"auth":"link","vivliostyle":true,...}

# ④ 서체 — 상용 서체는 리포·이미지에 넣지 않고 볼륨에만 (37개 · 137MB, 카탈로그 디자인이 쓰는 것만)
deploy/fonts-pack.sh                                   # 이 맥의 ~/Library/Fonts 에서 골라 fonts.tgz
fly ssh sftp put fonts.tgz /data/fonts.tgz
fly ssh console -C "sh -c 'tar xzf /data/fonts.tgz -C /data/fonts && rm /data/fonts.tgz'"
fly ssh console -C "/app/deploy/entrypoint.sh doctor"  # 서체 37/37 · gs · CLI 점검
# (선택) ICC — 납품 인쇄 색. Adobe CC 가 있는 맥의 JapanColor2001Coated.icc 를 /data/icc 에
#   fly ssh sftp put "/Library/Application Support/Adobe/Color/Profiles/Recommended/JapanColor2001Coated.icc" /data/icc/JapanColor2001Coated.icc
```

- 주소는 `https://yos-studio.fly.dev`. 도메인을 붙이려면 `fly certs add studio.<도메인>` + `fly.toml` 의 `YONE_PUBLIC_URL`.
- 업데이트: `deploy/fly-deploy.sh` (커밋된 HEAD 만 올라간다 — `git archive`; 비밀값은 없는 것만 채움). 돌던 조판은 끊기고 `lost` 로 표시된다(다시 누르면 됨). 볼륨(/data)은 그대로. 규칙: 리포 `CLAUDE.md` "배포 규칙".
- 카탈로그(틀·디자인)는 첫 기동 때 리포의 `catalog/` 가 `/data/catalog` 로 복사되고 **그 뒤로는 볼륨이 정본**이다.
  기동마다 `deploy/catalog_sync.py` 가 리포에 새로 생긴 틀(catalog.json 키)·디자인 폴더만 보탠다 — 있는 파일은 손대지 않는다.
- 백업: `fly volumes snapshots list studio_data` (Fly 가 매일 자동 스냅샷). 파일로 받으려면 `fly ssh sftp get`.
- 운영: `fly logs` · `fly status` · `fly machine restart <id>` · `fly ssh console`.
- 로컬 개발은 그대로 `bin/studio`(인증 꺼짐). 인증까지 로컬에서 보려면 `YOS_LINK_SECRET=… YONE_SECRET_KEY=… bin/studio`
  로 띄우고 `python3 -c "from core import webauth; print(webauth.make_link_token({'sub':'u1','name':'나','role':'designer'}))"` 로 표를 만들어 `/auth/callback?token=…`.
- 맥(Apple Silicon)에서 컨테이너를 시험하려면 `docker build -t yone/design-studio:local .` (호스트 아키텍처 그대로).
  `--platform linux/amd64` 는 qemu 라 chromium 이 못 뜬다(SSE3). Fly 의 x86 머신에선 문제없다.

## 2. 비밀값 (fly secrets)

| 키 | 뜻 | Y.OS 쪽 짝 |
|---|---|---|
| `YONE_PASSWORD` | **스튜디오 자체 로그인 비밀번호** (`/auth/login`). `fly.toml` 의 `YONE_AUTH=password` 와 짝 — 2026-09-18 부터 이게 기본 | — |
| `YOS_LINK_SECRET` | (안 씀 — Y.OS 계정으로 들어오게 할 때만, 3절) 사람 표 서명 + 웹훅 서명 | `STUDIO_LINK_SECRET` (같은 값) |
| `SERVICE_TOKEN` | contents·design·core → 스튜디오 호출 토큰(콤마로 여러 개) | `STUDIO_SERVICE_TOKEN` (같은 값) |
| `YONE_SECRET_KEY` | 세션 쿠키·임베드 토큰 서명. `openssl rand -hex 32` | — |
| `YOS_LOGIN_URL` | (안 씀 — link 방식일 때만) 미인증 브라우저를 보낼 Y.OS 진입 라우트(3절) | `deploy/yos/studio-entry-route.ts` |
| `YOS_ORIGINS` | CORS · iframe 허용 출처(콤마) | — |
| `BLOB_READ_WRITE_TOKEN` | contents 와 **같은 Blob 스토어**의 토큰 (Vercel → Storage → Blob → 토큰). 없으면 Blob 안 씀 | contents 의 같은 변수 |
| `YOS_WEBHOOK_URL` | 조판 끝·디자인 바뀜 알림 받는 곳 (없으면 안 보냄) | `deploy/yos/studio-webhook-route.ts` |
| `YOS_CONTENTS_API` / `YOS_CONTENTS_TOKEN` | "contents 에서 가져오기"가 읽는 곳 (6절). 없으면 그 출처만 꺼짐 | contents 읽기 API |
| `ANTHROPIC_API_KEY` | PDF 판정·작업대 클로드 칸 | 같은 키 |
| `YONE_ALLOWED_ROLES` | (선택) 이 역할만. 비우면 로그인한 누구나 | Auth.js user.role |

## 3. 로그인

**기본(2026-09-18~): 스튜디오 자체 로그인.** yos-design-web 과는 별개 프로젝트로 본다 — Y.OS 쪽에 넣을 것 없음.
`fly.toml` 의 `YONE_AUTH=password` + 비밀값 `YONE_PASSWORD` 하나. 미인증 브라우저는 `/auth/login?next=…` 로 가고,
비밀번호가 맞으면 세션 쿠키(12h). 실패 5회면 10분 잠금. `YONE_PASSWORD` 가 비어 있으면 아무도 못 들어간다(503).
```
디자이너 → https://yos-studio.fly.dev/catalog → 302 /auth/login?next=/catalog → 비밀번호 → /catalog
```
확인: `GET /auth/me` → `{"mode":"password",…}`. 비밀번호 바꾸기: `fly secrets set YONE_PASSWORD=… -a yos-studio`.
API·시스템은 아래와 같이 `Authorization: Bearer <SERVICE_TOKEN>`.

**(안 씀) link — Y.OS 가 ID 제공자, 표는 `signWidgetToken` 과 같은 꼴.** 나중에 Y.OS 계정으로 들어오게 하려면 `YONE_AUTH=link` 로 바꾸고 아래대로.

```
표 = base64url(JSON {u: 사용자id, e: 만료ms, n?: 이름, m?: 이메일, r?: 역할}) + "." + base64url(HMAC-SHA256(STUDIO_LINK_SECRET, payload))
```

**Y.OS 쪽 (진입을 맡을 앱 하나 — design 앱이 자연스럽다):**
1. `deploy/yos/studio-link.ts` → `src/server/studio/link.ts`
2. `deploy/yos/studio-entry-route.ts` → `src/app/studio/route.ts`
3. Vercel 환경변수 `STUDIO_URL=https://yos-studio.fly.dev`, `STUDIO_LINK_SECRET=<YOS_LINK_SECRET 과 같은 값>`
4. 메뉴에 링크: `/studio` (또는 `/studio?next=/book-studio?b=…`)

**흐름**
```
디자이너 → https://yos-studio.fly.dev/catalog
  → (세션 없음) 302 → https://yos-design-web.vercel.app/studio?next=https://yos-studio.fly.dev/catalog
  → (Auth.js 로그인) → 표 발급 → 302 → https://yos-studio.fly.dev/auth/callback?token=…&next=/catalog
  → 스튜디오 세션 쿠키(12h) → /catalog
```
API·앱은 매 요청 `Authorization: Bearer <표>`. 시스템은 `Authorization: Bearer <SERVICE_TOKEN>` → role=service.
확인: `GET /auth/me` → `{"mode":"link","user":{…},"authenticated":true}`.

## 4. 카탈로그 — contents·design 이 "디자인 고르기"에 쓰는 것

```
GET /api/v1/catalog                                    (SERVICE_TOKEN 또는 사용자 표)
{ "dirs": [ { "id":"etc", "name":"기타", "templates": [
    { "series":"workbook", "name":"STEP BY STEP 워크북", "ready":"auto", "pipeline":"workbook_v2", "fields":[…], "slots":{…},
      "designs":[ { "id":"d1", "name":"스텝바이스텝 워크북 (블루·베이지·브릭, A4)", "draft":false, "version":"3f9a1c02be",
                    "masters":[{"file":"master_first.png","label":"앞 간지","page":2,"url":"https://….public.blob.vercel-storage.com/studio/catalog/workbook/d1/master_first-xxxx.png"},…],
                    "previews":[{"file":"preview_1.png","url":"…"}] } ] } ] } ] }
GET /api/v1/catalog/<series>/<design>                  + config 요약(page·palette·fonts·print)
GET /api/v1/catalog/<series>/schema                    그 틀의 data.json JSON Schema (파일이 있는 계열만, 8절)
```
- 이미지 `url` 은 **Blob(public)** 주소다 — contents 화면에서 `<img>` 로 바로 쓴다. (Blob 토큰이 없으면 스튜디오 주소가 오고 인증이 필요하다.)
- `version` 은 config·css·design.json 의 해시 → 렌더 기록에 박힌다. 디자인을 고쳐도 이미 만든 책은 그대로.
- 캐시: `unstable_cache(studioCatalog, ["studio-catalog"], {tags:["studio-catalog"]})` 로 감싸고 **`design.changed` 웹훅에서 `revalidateTag`**. 그게 "실시간 반영".

## 5. 조판 — `POST /api/v1/renders` (클라이언트: `deploy/yos/studio-client.ts`)

```jsonc
POST /api/v1/renders                Authorization: Bearer <SERVICE_TOKEN | 표>
{ "series": "vocabook", "design": "d2",
  "book":   { "name": "이의1보카", "period": "27-1-중간", "school": "이의고", "title": "이의고 1학년 VOCA" },
  "source": { "type": "data", "data": { …그 틀의 data.json… } },
  //        { "type": "plan", "plan": { …워크북 v2 render_plan.json… } }
  //        { "type": "yos",  "school": "명일여고", "grade": "고1", "week": 3 }   ← 스튜디오가 contents 에서 읽어 옴 (6절)
  "knobs": { "palette.s1": "#77a1c4" }, "fields": { "grade": "고1" },
  "print": true, "replace": false, "callback": { "bookId": "cmsg…" } }
→ 202 { "job": "a1b2c3d4e5f6", "book": { "key": "조판/교재/단어장/이의1보카/27-1-중간", "bid": "9f0c…" }, "status_url": "/api/v1/renders/a1b2c3d4e5f6" }

GET /api/v1/renders/<job>?since=0
{ "status": "running" | "done" | "done_warn" | "failed" | "lost", "log": [...], "n": 41, "elapsed": 23, "rc": 0,
  "meta": { "series": "vocabook", "design": "d2", "design_version": "3f9a…", "steps": ["build","print","verify"], "bid": "…" },
  "result": { "pdfs": ["이의고_이의1보카_내지.pdf", "이의고_이의1보카_내지_인쇄.pdf"], "main_pdf": "…", "pages": 132, "verify_ok": true,
              "blob": { "이의고_이의1보카_내지.pdf": { "pathname": "studio/renders/a1b2…/이의고_이의1보카_내지.pdf", "url": "…", "access": "private" } } },
  "urls": { "이의고_이의1보카_내지.pdf": "https://yos-studio.fly.dev/api/v1/renders/a1b2…/files/…", "page": "…/pages/{n}.png", "studio": "…/book-studio?b=9f0c…" } }

GET /api/v1/renders/<job>/files/<name>       PDF(?download=1) · 조판_로그.txt · data.json · config.json   (스튜디오 인증)
GET /api/v1/renders/<job>/pages/<n>.png      면 그림
```
- 원고 **파일**(docx·hwp)로 만들려면 같은 주소에 `multipart/form-data` (`/api/catalog/create` 와 같은 필드) — 파서를 거친다.
- 끝나면 PDF 가 **Blob 에 private** 로 올라간다(`result.blob`). contents 는 `pathname` 을 저장하고 `presignUrl` 로 연다 — exam-files 와 같은 방식. `YOS_BLOB_PDF_ACCESS=public` 이면 URL 그대로.
- `done_warn` = PDF 는 나왔지만 검수(verify) 경고. 로그 끝에 게이트 결과.
- 상태는 `since=N` 폴링(1.5초) 또는 웹훅(7절).

## 6. contents 데이터 API — `source.type: "yos"` 가 읽는 것

스튜디오 어댑터(`core/sources/yos_contents.py`)가 부른다. **매핑 코드는 스튜디오에만** — contents 는 이 하나만 유지한다.

```
GET {YOS_CONTENTS_API}/api/typeset/data?series=<틀>&school=…&grade=…&week=…     Authorization: Bearer <YOS_CONTENTS_TOKEN>
200 { "kind": "data" | "plan", "data": { … }, "meta": { "title": "…", "school": "…", "period": "…" } }
4xx { "error": "범위가 아직 확정되지 않았다 (scopeStatus=DRAFT)" }     ← 그 말이 그대로 조판 로그에 뜬다
```
지켜 줄 것은 `docs/yos_시험범위_읽기API_요청서.md` 와 같다 — 가공하지 말 것, count 실을 것, 미확정이면 거절, 읽기 전용.
(초기엔 `type:"data"` 로 contents 가 data.json 을 본문에 실어 보내도 된다 — 어댑터 없이 바로 된다.)

**워크북 — contents 가 자기 모양 그대로 보내는 길 (2026-09-18, 돌아감).** contents 의 「워크북 · 교재별 제작 현황 → 지문 →
유형별 등록 현황」에서 「등록됨 → 지면」/「지면 만들기」를 누르면 contents 가 `POST /api/v1/renders` 에
`source: {"type":"data","data":{"format":"yos-workbook-v1","book":{…},"passages":[{"no":"20","content":"…","items":[{"key":"vocab-choice","label":"…","content":{…원고 색인 그대로…}}]}]}}`
를 보낸다. `format` 표시를 보고 스튜디오가 `core/sources/yos_workbook.py` 로 워크북 data.json 을 만든다 — **매핑은 그 파일 한 곳**
(어느 항목 key 가 어느 스텝인지, 어법선택 5지선다 판본은 하단 상자 등). contents 쪽 코드: `src/server/studio/{client,workbook-payload}.ts` ·
`src/app/api/passages/[passageId]/studio-workbook/route.ts` (Vercel 환경변수 `STUDIO_SERVICE_URL` · `STUDIO_SERVICE_TOKEN`).

## 7. 웹훅 — 스튜디오 → Y.OS (`deploy/yos/studio-webhook-route.ts`)

`YOS_WEBHOOK_URL` 로 POST JSON. 헤더 `x-studio-event`, `x-studio-signature: <hex HMAC-SHA256(STUDIO_LINK_SECRET, 본문)>` —
core 의 `src/server/chat/link.ts` `verifySignature` 와 같은 규칙. 3회 재시도(2·6초).

```jsonc
{ "event": "render.finished", "sent_at": 1789…,
  "render": { "id": "a1b2…", "status": "done", "rc": 0, "book": {…}, "series": "vocabook", "design": "d2", "design_version": "3f9a…",
              "result": { …5절과 같음, "blob": {…} }, "files": { "….pdf": "https://yos-studio.fly.dev/api/v1/renders/…" },
              "status_url": "…", "callback": { "bookId": "cmsg…" } } }
{ "event": "design.changed", "series": "workbook", "design": "d1", "action": "added" | "deleted" }
```

## 8. 틀별 data.json 스키마 (첫 계열 연동의 첫 작업)

`core/render_vivlio/series/<틀>/data.schema.json` 이 있으면 `GET /api/v1/catalog/<틀>/schema` 로 나간다. **지금은 없다** —
파서 출력이 사실상의 스키마다. 첫 계열을 정하면 그 계열 `data.py` 출력에서 스키마를 뽑아 이 자리에 두는 것이
contents 쪽 조립 코드의 계약서가 된다. 워크북(v2)은 `render_plan.json` 이 입력이고 `core/schema/content_v2.schema.json` 이 있다.

## 9. 임베드 — contents 화면 안에 작업대

`studioEmbedUrl(user, "/book-studio?b=<bid>")` → `{url}` → `<iframe src={url}>`. 처음 한 번 그 주소를 열면 스튜디오 세션 쿠키가 생긴다.
스튜디오는 `/book-studio*` · `/api/v1/renders/*` 에만 `frame-ancestors <YOS_ORIGINS>` 를 연다. (core 의 CHAT 위젯과 같은 방식.)
결과 화면(진행·PDF·면 그림)은 임베드 없이 5절 API 로 contents 가 직접 그리는 편이 낫다.

## 10. 다음 단계

1. Fly 배포(1절) → Y.OS 진입 라우트 + 환경변수(3절) → 디자이너가 Y.OS 계정으로 `/catalog` 여는 것 확인.
2. 첫 연동 계열 결정 → `data.schema.json` → contents 데이터 API 또는 `type:"data"` 로 `POST /renders` 끝까지 한 번.
3. contents 에 디자인 고르기(4절) + 조판 단추(5절) + 웹훅(7절).
4. 작업대는 임베드로 두고, 필요할 때 화면 단위로 API 위에 옮긴다.
