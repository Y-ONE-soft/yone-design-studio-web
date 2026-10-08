"""구성 01 표지 — 기준 reference.pdf 1쪽을 A4 로. 전부 마우스·키보드."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mkpage import *                                                    # noqa

K = 297 / 303.0
def X(v): return round(v, 1)          # 기준 좌표 그대로 — 왼쪽 여백 유지
def Y(v): return round(v * K, 1)      # A4 는 6mm 짧다 — 세로를 비례로 줄인다

st = open_doc("스텝바이스텝 워크북 (A4)")
st += [S("구성 ① 표지 — 바탕부터", 2000)]
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
st += image(X(28.3), Y(272.5), 34, 9.5, os.path.expanduser("~/Downloads/각인Books_로고.svg"),
            label="로고 — 「그림」 자리를 끌고 파일을 고른다 (SVG)")
st += done("표지", "c01.png")
json.dump(st, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "c01.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("c01 단계", len(st))
