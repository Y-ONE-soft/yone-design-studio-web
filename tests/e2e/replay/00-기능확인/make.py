"""모르는 기능 확인 — ① 지면 바깥(재단 여백)까지 칠하기 ② 중간 굵기 글자 ③ 단 수·단 간격 입력. 전부 마우스·키보드."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa

st = open_doc("기능 확인")
st += [S("① 재단 여백까지 — 바탕 -3,-3 216×303", 1500)]
st += box(-3, -3, 216, 303, "#8aabc9", radius=0)
st += box(22.93, -3, 2.38, 29.9, "#faf7f0", radius=0)
st += [S("② 굵기 — 「굵기」 칸에서 고르기", 1500)]
for k, wt in enumerate((400, 500, 600, 700, 800)):
    st += text(20, 60 + k * 20, 170, 14, f"STEP 01 Montserrat {wt}", 30, "#ffffff", font="Montserrat", weight=wt)
st += text(20, 170, 170, 14, "STEP 01 Montserrat + 굵게", 30, "#ffffff", font="Montserrat", bold=True)
st += [S("③ 여백 및 단 — 단 수 · 단 간격을 차례로 쳐서 둘 다 들어가는지(Enter 로 확정)", 1500)]
st += columns(2, 4)
st += done("기능 확인", "t.png")
json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("00 단계", len(st))
