"""구성 02 STEP 간지 — 기준 reference.pdf 2쪽을 A4 로."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mkpage import *                                                    # noqa

K = 297 / 303.0
def X(v): return round(v, 1)
def Y(v): return round(v * K, 1)

st = open_doc()                                     # 표지가 있는 문서에 쪽을 더한다
st += expect_pages(1)                               # 표지 한 장만 있는 상태에서 시작
st += add_page("구성 ② STEP 간지 — 새 쪽")
st += [S("바탕 전체를 블루로", 1800)]
st += box(0, 0, 210, 297, "#8aabc9")
st += box(0, 0, 210, Y(6.9), "#faf7f0", label="위쪽 크림 띠와 세로 막대")
st += box(X(25.9), 0, 2.4, Y(29.9), "#faf7f0")
st += text(X(26), Y(34.3), 30, 5, "STEP", 12, "#ffffff", font="Montserrat", track=380, label="STEP 과 큰 숫자")
st += text(X(25), Y(39.2), 90, 42, "01", 110, "#ffffff", font="Montserrat", bold=True)
st += [S("아래 단계 셋 — 흰 원과 라벨", 2200)]
for k, (x, lb, fill) in enumerate(((25.9, "FRAME", "#ffffff"), (70.3, "BUILD UP", None), (114.2, "TEST", None))):
    st += ellipse(X(x), Y(220), 13, fill=fill, stroke=None if fill else "#ffffff", sw=0.6)
    st += text(X(x), Y(223.5), 13, 6, str(k + 1), 16, "#8aabc9" if k == 0 else "#ffffff",
               align="center", font="Montserrat", bold=True)
    st += text(X(x + 0.1), Y(235.2), 30, 4, lb, 8.5, "#ffffff", font="Montserrat", track=250)
    if k < 2:
        st += box(X(x + 14.6), Y(226.5), 28, 0.5, "#ffffff")
st += text(X(26), Y(268.8), 130, 11, "STEP BY STEP", 26, "#ffffff", font="Montserrat", bold=True, track=370,
           label="아래 큰 로고 글")
st += done("STEP 간지", "c02.png")
json.dump(st, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "c02.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("c02 단계", len(st))
