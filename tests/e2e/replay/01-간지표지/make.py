"""단위 01 간지·표지 — 원본 d1 reference.pdf 1·2쪽(표지 · STEP 01 간지)을 A4 한 문서 두 쪽으로. 전부 마우스·키보드."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa

K = 297 / 303.0                       # 원본 303mm → A4 297mm
def X(v): return round(v, 1)          # 가로는 원본 좌표 그대로
def Y(v): return round(v * K, 1)      # 세로는 비례로 줄인다

# ── 1쪽 표지 ──
st = open_doc("스텝바이스텝 워크북 (A4)")
st += [S("① 표지 — 바탕부터", 2000)]
st += box(0, 0, 210, 297, "#faf7f0")
st += box(X(28.1), 0, 2.1, Y(42.1), "#8aabc9", label="왼쪽 파란 막대")
st += shape(210 - 30.4, Y(18), 30.4, 5.6, "#bab4a2", name="평행사변형", label="오른쪽 위 꼬리표 — 「도형」에서 평행사변형")
st += text(177.8, Y(19.2), 30, 3.4, "STEP BY STEP", 6.5, WHITE, align="center", font="Montserrat", track=340)
st += text(X(28), Y(56.3), 80, 17, "STEP", 46, "#333b3d", label="큰 제목 — 글꼴 Montserrat · 굵게", bold=True, font="Montserrat", track=20)
st += text(X(28), Y(74.3), 80, 17, "BY", 46, "#8aabc9", bold=True, font="Montserrat", track=30)
st += text(X(28), Y(92.6), 80, 17, "STEP", 46, "#333b3d", bold=True, font="Montserrat", track=20)
st += box(X(28.3), Y(126), 51.9, 0.5, "#b5ac9c", label="밑줄 — 베이지 가는 선 위에 파란 굵은 선")
st += box(X(28.3), Y(126), 15.9, 1.6, "#8aabc9")
st += text(X(28.3), Y(131.7), 80, 6, "스텝바이스텝 워크북", 12, INK, font="GmarketSans", track=-90)
st += text(X(28.3), Y(139.6), 90, 4, "MOCK TEST · WORKBOOK", 8, "#b5ac9c", font="Montserrat", track=239)
st += [S("단계 셋 — 원 · 숫자 · 라벨", 2200)]
for k, (x, lb, col) in enumerate(((28.3, "FRAME", "#8aabc9"), (62.2, "BUILD UP", "#cfa76b"), (96.4, "TEST", "#bd7d70"))):
    st += ellipse(X(x), Y(176), 11.1, col)
    st += text(X(x), Y(178.7), 11.1, 6, str(k + 1), 14, WHITE, align="center", font="Montserrat", bold=True)
    st += text(X(x - 9.5), Y(189.3), 30, 4, lb, 7.5, "#b5ac9c", font="Montserrat", track=160, align="center")
    if k < 2:
        st += box(X(x + 12.5), Y(181), 20.5, 0.4, "#b5ac9c")
st += [S("아래 색 점 셋", 1700)]
for x, col in ((28.3, "#8aabc9"), (36.5, "#cfa76b"), (44.7, "#bd7d70")):
    st += box(X(x), Y(262.1), 6.9, 2.6, col)
st += image(X(28.3), Y(272.5), 34, 9.5, os.path.join(HERE, "logo.svg"), label="로고 — 「그림」 자리를 끌고 파일을 고른다 (SVG)")
st += done("표지", "p1.png")

# ── 2쪽 STEP 01 간지 ──
st += add_page("② STEP 간지 — 새 쪽")
st += [S("바탕 전체를 블루로", 1800)]
st += box(0, 0, 210, 297, "#8aabc9")
st += box(0, 0, 210, Y(6.9), "#faf7f0", label="위쪽 크림 띠와 세로 막대")
st += box(X(25.9), 0, 2.4, Y(29.9), "#faf7f0")
st += text(X(26), Y(34.3), 30, 5, "STEP", 12, "#ffffff", font="Montserrat", track=380, label="STEP 과 큰 숫자")
st += text(X(25), Y(39.2), 90, 42, "01", 110, "#ffffff", font="Montserrat", bold=True)
st += [S("아래 단계 셋 — 흰 원과 라벨", 2200)]
for k, (x, lb, fill) in enumerate(((25.9, "FRAME", "#ffffff"), (70.3, "BUILD UP", None), (114.2, "TEST", None))):
    st += ellipse(X(x), Y(220), 13, fill=fill, stroke=None if fill else "#ffffff", sw=0.6)
    st += text(X(x), Y(223.5), 13, 6, str(k + 1), 16, "#8aabc9" if k == 0 else "#ffffff", align="center", font="Montserrat", bold=True)
    st += text(X(x + 0.1), Y(235.2), 30, 4, lb, 8.5, "#ffffff", font="Montserrat", track=250)
    if k < 2:
        st += box(X(x + 14.6), Y(226.5), 28, 0.5, "#ffffff")
st += text(X(26), Y(268.8), 130, 11, "STEP BY STEP", 26, "#ffffff", font="Montserrat", bold=True, track=370, label="아래 큰 로고 글")
st += done("STEP 간지", "p2.png")

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("01 단계", len(st))
