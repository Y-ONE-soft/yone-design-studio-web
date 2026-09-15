# 워크북 수능만만 기본 10강 — Vivliostyle 조판

InDesign 없이 **원고 렌더 플랜 → HTML/CSS → PDF** 로 낸 내지.

```bash
cd ~/dev/yone-design-web
bin/viv "조판/교재/워크북_비블리오/수능만만10강" all      # 데이터 → 조판 → 검수
bin/viv "조판/교재/워크북_비블리오/수능만만10강" watch    # 라이브 미리보기
```

- 계열 코드: `core/render_vivlio/series/workbook/` (리포)
- 디자인: `core/render_vivlio/themes/workbook.css` (리포) — 최신 완성본 실측 이식
- 이 폴더에는 **코드를 두지 않는다.** config.json + 원고 + 산출 PDF 뿐.

## 범위·스텝 골라 내기

`config.json` 에 `select` 를 넣으면 **그것만 조판된다**(지우는 게 아니라 안 만든다).

```jsonc
"select": {
  "passages": [2, 4, 6],                        // 지문 순번
  "steps": ["step1_a1", "step1_c1", "step3"],   // 슬림 판
  "renumber": true
}
```
