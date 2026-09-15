---
name: vivlio-studio-editor
description: "내지 작업대를 \"웹 인디자인\"으로 — 통일된 에디터·표/상자·목차/색인·정규식 스타일·마스터 머리말. 아홉 계열 전부 32/32"
metadata: 
  node_type: memory
  type: project
  originSessionId: 079621eb-5a0d-4f5b-ac1b-4fa07e181f58
  modified: 2026-09-01T17:02:24.148Z
---

**한 문장: 교재가 달라도 도구는 같아야 한다.** `/book-studio` 는 계열을 가리지
않는 에디터다. 설계·함정은 `~/dev/yone-design-web/docs/vivliostyle_자립화_계획.md`
⑫~㉞ 에 있다 — 이어갈 때 그것부터 읽는다. [[vivlio_selfserve_studio]] 의 다음 장.

## 무엇이 되나

문자·단락·단락 옵션·문자/단락 스타일·레이어·페이지·상자·표·목차·정규식 스타일·
그림·찾기·색상 견본·마스터 페이지·문서 설정·편집 이력·특수문자·클로드·직접 손보기.
표 셀 병합·상자 손잡이·묶기(그룹)·잠금·화살표 밀기·안내선·각주·하이퍼링크·
빈 면 넣기·면 번호 다시 매기기·머리말/꼬리말(면번호·전체면수·장 제목)·색인.

## 확인한 방법 (이게 핵심이다)

    python3 scripts/studio_check/serve.py &          # 인증 없는 사본, 5099
    BOOK=광문보카 node scripts/studio_check/audit.mjs # 32가지
    node scripts/studio_check/edit.mjs               # 고치고 되돌리기 9가지
    python3 scripts/studio_check/richfuzz.py         # 고칠 수 있는 자리 전부에 서식
    python3 -m pytest tests/test_render_vivlio_studio.py   # 288개

## 반드시 기억할 함정

- **회귀 그물(`vivlio_baseline.py compare`)은 다시 굽지 않는다.** 폴더의 PDF 를
  잰다 → ① 시험하느라 구운 것을 두면 그게 "차이" 로 잡히고(실제로 겪음)
  ② 코드만 고치고 대조하면 **아무것도 검증되지 않는다.** 반드시 다시 굽고 대조.
  중등부는 교재 폴더 `automation/` 이 굽는다 — 다시 구우면 납품본을 덮어쓴다.
  `_backup/` 에 기준선과 같은 PDF 가 있는지 **먼저** 확인할 것.
- **`replace(…, 1)` 로 세 번 잘못 고쳤다.** 파일 안에 똑같은 두 줄이 있으면
  첫 번째가 잡힌다(검사 코드가 딴 라우트로, 정규식 걸기가 `run_preview` 로,
  새 함수가 `@bp.route` 와 `def` 사이로). 앵커에 **그 함수 안이라는 것**까지 넣자.
- **글 넣기와 블록 넣기는 다른 질문이다.** 낱말·문항 기록 목록은 표·상자는 받아도
  글은 못 받는다(`unit["label"]` 에서 조판이 통째로 멎었다) → `text_like`/`para_like`.
- **빈 면은 원고를 건드리지 않는다**(`::before`). `break-before`+`after` 를 같이
  주면 두 면이 생긴다 → 그 자리가 면 꼭대기인지는 **화면이** 재서 알려 준다.
  측정 조판에서는 꺼야 한다(`항목 130 vs 측정 면 131`).
- **면 번호는 사람이 적지 않는다** — `target-counter`. 목차는 **재는 자리(문항)에
  못 넣는다**(측정이 멎는다) → 계열이 `MEASURED` 로 말한다.
- **「모든 면」에 꼬리말을 적어도 아무 일이 안 난다** — 계열이 `@page voca` 처럼
  **이름 있는 면**을 쓰면 그쪽이 세다(= 인디자인의 마스터 A·B·C). `@bottom-outside`
  (안/바깥)는 조판이 무시한다 → `:left`/`:right` 로 갈라 적는다.
- **정규식 스타일은 조판 직전 HTML 에** 건다(`cli.run_build` 한 곳). 계열마다
  걸면 빠뜨린다. 태그 안·`<style>` 은 안 건드리고 `<!--grep-done-->` 로 한 번만.
- 덩어리(표·상자·목차)를 가르는 자리는 `core/blocks.py` **한 곳**이다.
- **`offsetParent` 를 믿지 말 것**(상자 끌기는 적힌 mm 에 움직인 mm 을 더한다).
- **`epageCount` 는 어림값**, 전권 면수는 마지막 PDF 로 안다.
- **브라우저 패널이 숨겨져 있으면 성능 측정이 전부 거짓**이다(스로틀링).
- 점검 스크립트에서 서식 단추를 **자리로 세지 말 것** — 각주가 앞에 붙은 뒤
  `button[0]` 이 `prompt()` 를 띄워 점검이 15분 멎었다(대화상자도 받아 닫는다).

## 아직

벡터 패스·불리언 연산은 그래픽 프로그램의 일이라 뺐다. 클로드 패널은
`ANTHROPIC_API_KEY` 가 있어야 켜진다.

관련: [[vivlio_selfserve_studio]] [[project_blackbook_vivliostyle]]
[[project_middle_regular_gachisaegim]] [[feedback_auto_commit_on_edit]]
