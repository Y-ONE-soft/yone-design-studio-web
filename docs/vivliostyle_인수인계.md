# Vivliostyle 실사용 착수 — 인수인계 (2026-07-23)

사용자 지시: **"Vivliostyle을 지금 바로 이용하려고 한다"** — 파일럿(W42/W43) 단계를 끝내고 실제 조판 용도로 쓰기 시작하는 단계. 이 문서만 읽으면 이어받을 수 있게 정리한다.

## 1. 현재 무엇이 있나 (실측 확인됨)

| 항목 | 경로 / 값 |
|---|---|
| 파일럿 코드 | `pilot/vivliostyle/` — `render_html.py`(동형), `theme.css`, `build.py`, `case_hanyoung3.json` |
| 워크북 확장 | `pilot/vivliostyle/workbook/` — `render_workbook.py`, `workbook_theme.css`, `build_workbook.py` |
| 자산 | `pilot/vivliostyle/assets/` (아이콘·장식 — 실물 PDF에서 무손실 추출) |
| 런타임 | Node v25.8.0 / `@vivliostyle/cli` **11.1.0** (core 2.44.1) — `pilot/vivliostyle/node_modules`에 설치됨 |
| 산출물 | `data_corpus/pilot_vivlio/hanyoung3/exam_vivlio.pdf`(동형 8p), `.../workbook_supp/workbook_vivlio.pdf`(워크북 13p) |
| 대조 자료 | 각 폴더 `compare/` — 블라인드 크롭·요소 확대·`blind_mapping.json`, `geometry_deltas.json` |
| 보고서 | `docs/vivliostyle_파일럿_보고.md` (1차 동형 + 2차 워크북 판정표) |

## 2. 파일럿 실측 결론 (근거 수치)

- **동형**: 페이지 8=8, 스타일 8/8 재현, 금칙 위반 viv 0 vs 실물 1, **빌드 6초 vs InDesign 191초**
- **워크북**: 디자인 요소 13유형 중 **충실 11 / 근사 2 / 불가 0**, 동일 텍스트 109행 기하 평균 **0.97mm**, **4초 vs 437초**
- 원리적 비목표: **행 나눔 파리티**(엔진이 다르면 줄바꿈 위치가 다름 — 기존 책 복제는 불가, 신규 조판은 무해)
- 근사 2: **장평**(CSS에 개념 없음 → scaleX 근사), **상용 서체 2종**(URWDIN→DIN Medium 대체, 로고 서체는 PDF 서브셋 재사용 — **라이선스 미해결**)

## 3. 결정된 전략 (사용자 확인됨)

- 장기적으로 새 구조(코드 조판)로 수렴, InDesign은 ① 기존 책 재판·수정 ② 표지·목업 등 디자인 작업으로 잔류
- **파서·구조 인식·게이트 43종·검수 에이전트는 백엔드 무관 자산** — 같은 원고면 인식 결과가 양쪽 동일(파일럿은 기존 job의 `render_plan.json`을 소비)
- 규칙 계층은 기존과 동일: 공통 → 교재별 → 학교별 → job 오버라이드

## 4. 실사용 착수 시 해야 할 일 (권장 순서)

1. **엔진 편입 설계**: 파일럿 코드를 `pilot/`에서 `engines/<계열>_viv/` 또는 공용 렌더 백엔드로 승격. **렌더 플랜 소비 인터페이스는 이미 동일**하므로 엔진 래퍼 + registry + subjects 카드 + 템플릿(html)만 추가하면 웹에서 선택 가능(기존 v2 전환 절차 = `docs/v2_전환_핸드북.md`와 동형).
2. **백엔드 선택 UI**: 조판 페이지에서 "InDesign / Vivliostyle" 선택(또는 계열별 기본값). 산출물 경로·파일명 규칙은 기존 유지.
3. **잔여 스텝 빌더**: 워크북 5종 스텝이 미구현(동일 패턴 — `render_workbook.py` 참조). 전권(298p) 규모 빌드 미검증.
4. **검수 연결**: `core/visual_inspect` 1층·visual-review 2층·검수 에이전트는 PDF 기반이라 **그대로 붙는다**. 게이트 43종 중 덤프(indd) 기반은 미적용 → PDF/HTML 기반 대체 검사 설계 필요.
5. **관문 3종**: 서체 라이선스 정리(상용 2종), PDF/X 및 **출력소 시험 인쇄 1회**, 고정 시트 넘침 게이트.
6. **선택 기능**(사용자 관심 표명): 대화형 수정 루프(지목→6초 재생성), HTML편집기 연결(중간 HTML 직접 편집 → 오버라이드로 기록해 재생성에도 유지), 완성본 PDF 캘리브레이션(픽셀 대조 자동 수렴).

## 5. 즉시 실행 명령 (검증됨)

```bash
cd ~/dev/yone-design-web-summer/pilot/vivliostyle
python3 build.py                    # 동형 한영3 → data_corpus/pilot_vivlio/hanyoung3/
python3 workbook/build_workbook.py  # 부교재 워크북 대표구간 → .../workbook_supp/
```

## 6. 주의

- 파일럿은 **실서비스 미연결**(웹 카드 없음). 통합웹에 배포된 개선(구조 인식·S_답란·역학습·검수 에이전트)은 전부 **InDesign 경로**에 적용된 것.
- 브랜치 `summer-2026`, 실서비스 반영은 `scripts/deploy_to_prod.sh`.
- 파일럿 산출물은 `data_corpus/`(gitignore) — 코드·CSS·문서만 추적.
