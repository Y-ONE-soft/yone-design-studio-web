# 블랙북 01 (배재고1 26-2-중간) — 내지 조판

**코드는 이 폴더에 없다.** 통합웹 리포의 Vivliostyle 엔진이 조판한다.
여기 있는 것은 `config.json` + `원고/` + `assets/`(완성본에서 추출한 아트워크) 뿐이다.

```bash
cd ~/dev/yone-design-web
bin/viv "…/프리미엄북/블랙북/26-2-중간" data          # 원고 docx 6종 → data.json
bin/viv "…/프리미엄북/블랙북/26-2-중간" build         # 높이 측정 → 조판 → 마감
bin/viv "…/프리미엄북/블랙북/26-2-중간" build --nomeasure   # 높이 재측정 없이
bin/viv "…/프리미엄북/블랙북/26-2-중간" theme         # 아트워크 재추출(디자인 변경 시)
bin/viv "…/프리미엄북/블랙북/26-2-중간" verify        # 원고 ↔ PDF 전수 대조 게이트
```

- 계열 코드: `core/render_vivlio/series/blackbook/`
- 공용 백엔드: `core/render_vivlio/`
- 계열 스타일시트: `core/render_vivlio/themes/blackbook.css`
- 설계·함정: `docs/vivliostyle_엔진.md`

## 조판 순서

1과 연관어휘 → 1과 문제 → 2과 연관어휘 → 2과 문제 → 1과 해설 → 2과 해설.
간지·MEMO 면은 인디자인 완성본(`블랙북_1_v2_9.pdf`)의 아트워크 면을 그대로 끼운다
(`config.json` 의 `finish`). 마지막 면은 언제나 왼쪽(짝수), 뒤 간지는 1장.

## 산출 (2026-08-20)

`배재1_블랙북01_내지.pdf` 116p · A4+도련 3mm · TrimBox 전면.
납품 시점 코드는 `_backup/automation_납품시점_20260820/` 에 그대로 있다.

⚠ **미리보기로 결과 PDF를 열어 둔 채 다시 빌드하면** 몇 면만 남고 나머지가 흰 종이로
보인다. 파일이 통째로 교체돼(inode 교체) 뷰어 캐시가 깨진 것이지 조판이 깨진 게 아니다.
