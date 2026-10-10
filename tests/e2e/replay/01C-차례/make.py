"""단위 01C 간지·차례 — 원본 d1 reference.pdf 2·3쪽(STEP 01 간지 펼침면)을 A4 한 문서 두 쪽으로. 전부 마우스·키보드.
단위 13(46·47쪽 STEP 03)과 같은 꼴 — 13 의 그리기 함수를 그대로 쓰고 원본 2·3쪽에서 다른 값만 바꿨다.
- 2쪽 = 첫 단계(FRAME)가 활성 — 흰 원은 첫째(22.93), 둘째·셋째는 테두리 원, 숫자 1 = 바탕색, 2·3 = 흰 75%. 큰 숫자 「01」.
- 바탕 #8aabc9(파랑) · 탭 첫째가 활성(흰 92%, 둘째·셋째 16%) · 탭 글 「STEP 01」= 바탕색, 02·03 = 흰 80% · 큰 「01」(흰 14%).
- 교재 이름·단원 이름은 원고 자리 「교재명」「단원명」 — 13 과 같은 자리·같은 값 자리(오른쪽 끝 170.0mm).
정본(문서 「스텝바이스텝 워크북 정본」)에 STEP 01 차례 면이 없어서 만든 단위(2026-10-10).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
U13 = os.path.join(os.path.dirname(HERE), "13-간지", "make.py")
G = {"__file__": os.path.join(HERE, "make.py"), "__name__": "u01c"}
src = open(U13, encoding="utf-8").read().split("# ── 46쪽")[0].replace('BG = "#bd7d70"', 'BG = "#8aabc9"')
exec(compile(src, U13, "exec"), G)                                       # 13 의 도구(T·V·B·head·mix…) — PAGES 는 이 단위 상태.json(3쪽)
G["ELEMS"] = {1: [], 2: []}
S, F, slot, text, done, put_content, open_doc, expect_pages, MM = (G[k] for k in ("S", "F", "slot", "text", "done", "put_content", "open_doc", "expect_pages", "MM"))
T, V, B, C, head, track_from, top_of, REF, PAGES = (G[k] for k in ("T", "V", "B", "C", "head", "track_from", "top_of", "REF", "PAGES"))
add_page = G["add_page"]
WHITE, GM, BG = G["WHITE"], G["GM"], G["BG"]
ELEMS = G["ELEMS"]

st = open_doc("스텝바이스텝 워크북 STEP 01 간지 (A4)")
st += expect_pages(1)
st += [S("① 2쪽 — STEP 01 간지", 1500)]
st += head(1)
st += B(1, "bar", 22.93, -3, 2.38, 29.9, G["CREAM"], label="세로 막대")
st += T(1, "t-step", 23.0, 31.29, 16.57, 4.23, "STEP", 12, WHITE, 700, label="STEP 과 큰 숫자", alpha=80, search=1.5)
st += T(1, "t-01", 22.0, 36.16, 41.68, 38.81, "01", 110, WHITE, 800, search=1, ctol=12)
st += [S("단계 셋 — 흰 원(첫째 활성) · 테두리 원 둘 · 선 · 숫자 · 라벨", 1500)]
st += C(1, "c1", 22.93, 216.88, 12.97, 13.23, fill=WHITE)
st += C(1, "c2", 67.25, 217.01, 12.7, 12.97, stroke=WHITE, sw=0.75, alpha=55)
st += C(1, "c3", 111.17, 217.01, 12.7, 12.97, stroke=WHITE, sw=0.75, alpha=55)
st += B(1, "ln1", 37.48, 223.49, 28.05, 0.53, WHITE, alpha=50)
st += B(1, "ln2", 81.41, 223.49, 28.05, 0.53, WHITE, alpha=50)
for k, (nx, nw, col, na, lx, lw, lb) in enumerate(((28.35, 2.3, BG, None, 22.96, 12.74, "FRAME"),
                                                   (71.81, 3.4, WHITE, 75, 64.39, 17.86, "BUILD UP"),
                                                   (115.8, 3.43, WHITE, 75, 112.98, 8.69, "TEST"))):
    st += T(1, f"n{k + 1}", nx, 220.53, nw, 5.64, str(k + 1), 16, col, 800, search=0.6, alpha=na)
    st += T(1, f"lb{k + 1}", lx, 232.17, lw, 3.0, lb, 8.5, WHITE, 600, search=1.5, alpha=85)
st += T(1, "t-sbs", 23.0, 265.78, 116.25, 9.17, "STEP BY STEP", 26, WHITE, 800, label="아래 큰 로고 글", alpha=90)
st += done("2쪽 STEP 01 간지", "p1.png")

st += add_page("② 3쪽 — 새 쪽")
st += head(2)
st += [S("오른쪽 탭 셋 — 흰 면 92% · 16% · 16% (첫째가 활성)", 1500)]
st += B(2, "tab1", 202.15, 57.06, 10.85, 25.93, WHITE, alpha=92)
st += B(2, "tab2", 202.15, 86.96, 10.85, 25.93, WHITE, alpha=16, ctol=8)
st += B(2, "tab3", 202.15, 117.13, 10.85, 25.93, WHITE, alpha=16, ctol=8)
st += [S("탭 글 — 90° 돌린 글", 1500)]
BASE_X = round((594.4935 - REF[PAGES[1] - 1].trimbox.x0) * MM, 2)        # 원본 Tm 의 기준선 x (13 과 같은 자리)
st += V(2, "tab1-t", BASE_X, 64.74, "STEP 01", 6.5, BG, 700, (206.49, 64.74, 2.29, 10.53))
st += V(2, "tab2-t", BASE_X, 98.34, "02", 6.5, WHITE, 700, (206.49, 98.34, 2.29, 3.13), alpha=80)
st += V(2, "tab3-t", BASE_X, 128.24, "03", 6.5, WHITE, 700, (206.49, 128.24, 2.29, 3.13), alpha=80)
st += [S("큰 01 — 흰 14%, 지면 밖으로 넘친다", 1500)]
st += T(2, "big-01", 87.01, 176.4, 112.61, 105.84, "01", 300, WHITE, 800, alpha=14, ctol=7, search=1.5, leading=300)
st += [S("교재 이름 · 단원 이름 — 책마다 바뀌는 글이라 원고 자리로", 1500)]
CONTENT = {}
RIGHT = 170.0


def title(id, slot_name, temp, s, base, size, weight, box):
    """13 의 title 과 같다 — 오른쪽 맞춤 글 자리(임시 글 → 자리 이름 → 원고는 끝에)"""
    ELEMS[2].append({"id": id, "x": box[0], "y": box[1], "w": box[2], "h": box[3], "color": WHITE, "see": WHITE, "ctol": 24,
                     "search": 1.0, "pad": 1.0, "text": s, "size": size})
    track = track_from(REF[PAGES[1] - 1], box, s, GM, weight, size)
    w = 120
    right = RIGHT + track / 1000 * size * MM
    top = top_of(base, size, GM, weight)
    CONTENT[slot_name] = s
    st = text(round(right - w, 2), round(top, 2), w, round(size * 0.3528 * 1.5, 1), temp, size, WHITE, label=f"자리 「{slot_name}」 — 임시 글",
              font=GM, weight=weight, track=track or None, align="right")
    return st + slot(slot_name)


st += title("t-book", "교재명", "교재 이름(출판사)", "공통영어2 능률(민)", 86.16, 36, 700, (65.24, 75.15, 104.76, 15.43))
st += title("t-unit", "단원명", "Unit.0", "Unit.1", 103.09, 36, 500, (136.13, 92.34, 33.87, 15.07))
st += done("3쪽", "p2.png")
st += put_content(CONTENT)
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("01C 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
