# 상일보카 01 (상일여고1 26-2-중간) — 내지 조판

**코드는 이 폴더에 없다.** 통합웹 리포의 Vivliostyle 엔진이 조판한다.
여기 있는 것은 `config.json`(책 1권치 설정) + `원고/`(GDrive 원본의 로컬 복사본)뿐이다.

```bash
cd ~/dev/yone-design-web
bin/viv "…/단어장/상일보카/26-2-중간" data      # 원고 → data.json (+ 인식 게이트)
bin/viv "…/단어장/상일보카/26-2-중간" build     # 전권 → 상일1_상일보카01_내지(_최종).pdf
bin/viv "…/단어장/상일보카/26-2-중간" build --sample    # 견본
bin/viv "…/단어장/상일보카/26-2-중간" build --nomemo    # 메모면 없는 판
bin/viv "…/단어장/상일보카/26-2-중간" verify    # 검수 게이트
```

- 계열 코드: `core/render_vivlio/series/vocabook/`
- 공용 백엔드: `core/render_vivlio/` (도련·TrimBox·간지·2패스·검수)
- 계열 스타일시트: `core/render_vivlio/themes/vocabook.css`
- 설계·함정: `docs/vivliostyle_엔진.md`

## 이 책의 값 (config.json)

A5 148×210 + 도련 3mm(재단 154×216) · 팔레트 6섹션 · Day 31~45 ·
간지 = `디자인/표지/상일보카/상일1_상일보카01_간지_{앞,뒤}.pdf`.
**색을 바꾸면 `palette` 만 고치면 된다** — 배경 SVG(4mm 띠·밴드·마름모)는 빌드마다
자동으로 다시 구워진다.

원고에 없어서 config 가 들고 있는 데이터: `options.more_with_roots`(9묶음),
`options.vs_groups`(18묶음 제목), `options.deriv_fix`. 실물 표기를 확정하면 여기만 고친다.

## 산출 (2026-08-20 납품)

`상일1_상일보카01_내지_최종.pdf` 259p(메모면 포함) /
`상일1_상일보카01_내지_메모없음_최종.pdf` 234p. 둘 다 간지 앞뒤 결합 + TrimBox 전면.
납품 시점 코드는 `_backup/automation_납품시점_20260820/` 에 그대로 있다.
