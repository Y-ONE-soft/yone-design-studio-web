---
name: feedback_print_pdf_cmyk
description: 인쇄 원고는 항상 CMYK — 비블리오 RGB 조판본은 book.print_pdf(prepress)로 무채색 K 1도 고정 후 변환
metadata:
  type: feedback
---

비블리오 조판본(DeviceRGB)을 인쇄로 넘기지 않는다. 사용자: *"rgb로 인쇄를 뽑는 사람이 어딨어 cmyk로 변환해"* (2026-09-11).

**Why:** Vivliostyle/Skia 는 무조건 RGB 로 쓴다. Ghostscript 로 그냥 ICC 변환하면 본문 먹 `#231f20` 이 **C68 M68 Y65 K74 리치블랙**이 되어 9pt 글자가 핀 어긋남으로 뭉갠다(실측). 기존 InDesign CMYK 납품본은 본문 **K100 1도**다.

**How to apply:** `core/render_vivlio/book.print_pdf(cfg)` → `_인쇄.pdf` (`bin/viv … all` 이 print 단계를 포함). **포켓북은 계열 기본값**(`series/pocketbook/theme.py` 의 `PRINT_GRAY`·`PRINT_CMYK`, 팔레트 **이름**으로 적음) — 학교 config 에 `print` 절을 적지 않는다(22권 전부 자동, 2026-09-11 승인). 책 config 의 `print` 절은 칸 단위로 덮고 `{"off": true}` 로 끈다(`book._print_section`). **2026-09-11 이후 전 계열 인쇄본 항상 켜짐** — 다른 세션이 `_print_section` 에 `prepress.default_print()` 바닥값과 계열별 `print_defaults`(블랙북·중등·단어장·워크북)를 얹었다. 끄려면 `"print": false` 또는 `{"off": true}`. 화이트북·광문보카가 이 방식으로 인쇄 완료. 원본 CMYK 를 아는 색은 cmyk_map 으로 못 박는다(테마 주석의 `(C/M/Y/K)` 값이 원본 IDML 과 일치). 검증: RGB 연산자 0 · 본문 `0 g` · 이미지 DeviceCMYK · TrimBox 사방 3mm · 주석 보존.

⚠ 판형·폰트는 문제 삼지 말 것 — 154×216(도련 3mm)·Type3 본문으로 상일보카·블랙북이 이미 무사히 인쇄됐다. 인디자인 파일 하나 보고 "기존 납품본은 도련 없음"이라 했다가 지적받음. 이어서 [[project_pocketbook_vivliostyle]] [[project_pocketbook_gwangmun_2609]]

⚠ **Ghostscript 가 글자층을 바꾼다(2026-09-11 발견·수리)**: 크로미움 ToUnicode 의 끝 바이트 넘치는 bfrange(`<8E> <8F> <B2FF>`)를 Ghostscript 가 규격대로 읽어 `대`→`눀`·`밀`→`묀`·`영`→`씁`(딱 0x100 차)으로 박는다. 인쇄 모양은 멀쩡 — 검색·복사·검수 주석 회수만 틀림. `prepress.fix_tounicode()` 가 GS 앞에서 쪼개고, `make()` 가 조판본↔인쇄본 한글 개수표를 대조해 **늘어난 글자가 있으면 `_불량.pdf` 로 떼고 멈춘다**. 수리 전에 만든 인쇄본 33개 중 12개가 오염(광문보카·상일보카·이의1·2보카·블랙북01·02·화이트북02·중2 천재소/동아윤 L5·파이널 광문1 Vol1·2·명일1 Vol2) — `print` 만 다시 돌리면 고쳐진다. ⚠ Ghostscript 는 **검수 쪽지(Text 주석)도 10배로 키운다**(5.6→56.4mm) — 인쇄엔 안 나오지만 뷰어에서 귀 딱지를 덮는다. `prepress._lift_notes/_restore_notes` 가 변환 밖으로 옮겨 원래대로 다시 붙인다. ⚠ **출력 의도**: 표지 PDF(인디자인)는 `Japan Color 2001 Coated` OutputIntent 를 달고, Ghostscript 인쇄본은 없다 → 같은 CMYK 인데 화면에서 12 단계 달라 보여 "표지 색이 다르다"는 지적이 된다. `prepress.add_output_intent` 가 변환에 쓴 ICC 를 박는다. ⚠ Ghostscript 는 CMYK 를 1/256 단위로 적는다(0.681 → 0.681641) — 잉크 대조는 ±0.005 로 볼 것(반올림 비교는 멀쩡한 고정을 '없음'으로 오판). ⚠ **면수: 4의 배수는 중철일 때만, 스프링·무선은 짝수**(사용자 지적 — 스프링인 광문1 에 MEMO 2면을 괜히 더함). 포켓북 `options.binding` 기본 spring.
