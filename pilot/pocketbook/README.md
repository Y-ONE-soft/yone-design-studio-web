# 포켓북 Vivliostyle 파일럿

계획서: `docs/vivliostyle_포켓북_전환계획.md` — **먼저 읽을 것.**

이 폴더가 답한 질문은 하나다.
**낱말 위·아래에 주석이 붙은 구문분석 지문면을 HTML/CSS 로 그릴 수 있는가.**
답은 예이고, 실측 기준선까지 맞는다.

```bash
SRC="$HOME/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/상일2_포켓북(올포5_6_13강_미래엔김4_5과_외부지문)_내지.pdf"

# ① 완성 포켓북 PDF 2면 → 지문 JSON (줄 10 · 낱말 137 · 주석 50 · 미부착 0)
python3 harvest_pdf.py "$SRC" 2 passage_250923.json

# ② 삽화 추출 (파일럿이라 손으로 한 번)
python3 -c "import fitz;d=fitz.open('$SRC');p=d[1];i=p.get_images(True)[0];\
x=fitz.Pixmap(d,i[0]);x=fitz.Pixmap(fitz.csRGB,x) if x.n>4 else x;x.save('build/illust.png')"

# ③ JSON → HTML → PDF (약 4초)
python3 render.py passage_250923.json meta.json build/out.pdf
```

검증(원본 실측값과 대조):

| | 원본 | 파일럿 |
|---|---|---|
| 본문 기준선 | 76.0 / 100.0 / 124.0pt | 76.0 / 100.0 / 124.0 |
| 위 주석 | 66.6pt | 66.6 |
| 아래 주석 | 84.6pt | 84.7 |
| 판형 | 148×210mm | 148×210mm |

## 이 파일럿이 남긴 실측 상수

`render.py` 의 CSS 변수. 계열을 만들 때 그대로 가져간다.

```
--lead   24pt      본문 행간
--up-dy  4.3pt     위 주석 (원본 baseline −9.4pt 가 되는 보정값)
--dn-dy  6.8pt     아래 주석 (원본 baseline +8.6pt)
자간     -0.022em  이 값에서 원본과 행바꿈이 일치한다
본문 top 24mm − 7.7pt   InDesign 첫 행 '어센트' 기준 보정
색       #231F20 본문 · #224E8E 파랑 · #D2232A 빨강 · #A7A9AC 주석
띠 #EAE6DC · 배지 #54669E · 칩 #869CD0 · 형광펜 #FDF598
```

## 함정 (다시 밟지 말 것)

- **주석 런을 글자 간격으로 끊지 마라.** 서로 다른 앵커 프레임의 글자가 0.3pt
  만 떨어져 있다(`S` 와 `V`). PyMuPDF 의 **span 경계**로 끊어야 한다.
- **형광펜을 낱말마다 칠하지 마라.** 어절 사이가 비어 줄무늬가 된다.
  연속 구간을 `<mark>` 로 묶는다.
- 주석이 낱말 **안의 어느 글자**에 붙었는지는 PDF 에 없다. IDML 에는 있다 —
  그래서 정본은 IDML 이고 PDF 하베스트는 백카탈로그용이다.
