"""단위 01 간지·표지 — 원본 d1 reference.pdf 1·2쪽을 A4 한 문서 두 쪽으로. 전부 마우스·키보드.

값은 모두 원본에서 뽑은 것(pagecmp.py elements · fonts). 지면 좌표 mm = 원본 좌표 - 재단 여백 3mm.
글 자리는 원본의 글자 상자 기준 — 편집기 글상자 위 끝과의 차이는 보정.json(측정해서 채움)으로 맞춘다.
이 파일은 steps.json(녹화기 대본)과 elems.json(측정할 요소 목록)을 같이 쓴다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa

FIX = json.load(open(os.path.join(HERE, "보정.json"))) if os.path.exists(os.path.join(HERE, "보정.json")) else {}
MS = "Montserrat"
ELEMS = {1: [], 2: []}


BG = {1: "#faf7f0", 2: "#8aabc9"}


def see(pg, color, alpha):
    """투명도가 있으면 바탕과 섞여 보이는 색 — 잴 때 쓴다."""
    if not alpha or alpha >= 100:
        return color
    c, b = [int(color[i:i + 2], 16) for i in (1, 3, 5)], [int(BG[pg][i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join("%02x" % round(bb + (cc - bb) * alpha / 100) for cc, bb in zip(c, b))


def T(pg, id, x, y, w, h, s, size, color, weight, track=0, font=MS, label=None, search=2, alpha=None, ctol=24):
    """원본 글 하나 — 원본 글자 상자(x,y,w,h) · 크기 pt · 색 · 굵기 · 자간 · 불투명. 보정(dx,dy,dtr)을 빼서 친다."""
    f = FIX.get(id if pg == 1 else f"p{pg}:{id}", {})
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": color, "see": see(pg, color, alpha), "ctol": ctol,
                      "search": search, "text": s, "size": size})
    bw = round(w * 1.25 + size * 0.35, 1)                                  # 글상자는 넉넉히 — 줄바꿈 없게
    bh = round(size * 0.3528 * 1.5, 1)
    return text(round(x - f.get("dx", 0), 2), round(y - f.get("dy", 0), 2), bw, bh, s, size, color, label=label,
                font=font, weight=weight, track=round(track - f.get("dtr", 0)), alpha=alpha)


def B(pg, id, x, y, w, h, fill, label=None, measure=True, alpha=None):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": see(pg, fill, alpha), "pad": 0.6,
                          "ctol": 24 if alpha else 30})
    return box(x, y, w, h, fill, label=label, alpha=alpha)


def C(pg, id, x, y, w, h, fill=None, stroke=None, sw=None, alpha=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill or stroke, "see": see(pg, fill or stroke, alpha), "pad": 0.6,
                      "ctol": 24 if alpha else 30})
    return ellipse(x, y, w, fill=fill, stroke=stroke, sw=sw, h=h, alpha=alpha)


# ── 1쪽 표지 ──────────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 (A4)")
st += [S("① 표지 — 바탕은 재단 여백까지", 1500)]
st += B(1, "bg", -3, -3, 216, 303, "#faf7f0", measure=False)
st += B(1, "bar", 25.06, -3, 2.12, 42.09, "#8aabc9", label="왼쪽 파란 막대")
ELEMS[1].append({"id": "tag", "x": 176.58, "y": 15.01, "w": 36.42, "h": 5.7, "color": "#bab4a2"})
st += shape(176.58, 15.01, 36.42, 5.7, "#bab4a2", d="M0.1403 0 L1 0 L1 1 L0 1 Z", label="오른쪽 위 꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(1, "tag-t", 184.59, 16.38, 22.27, 2.29, "STEP BY STEP", 6.5, "#ffffff", 500, 232, search=0.6)
st += T(1, "t-step1", 25.01, 53.33, 44.09, 16.23, "STEP", 46, "#333b3d", 800, 7, label="큰 제목 — Montserrat ExtraBold")
st += T(1, "t-by", 25.01, 71.33, 23.72, 16.23, "BY", 46, "#8aabc9", 800, -10)
st += T(1, "t-step2", 25.01, 89.6, 44.09, 16.23, "STEP", 46, "#333b3d", 800, 7)
st += B(1, "ul-thin", 25.32, 123.0, 51.88, 0.53, "#b5ac9c", label="밑줄 두 겹")
st += B(1, "ul-bold", 25.32, 123.0, 15.88, 1.59, "#8aabc9")
st += T(1, "t-ko", 25.31, 128.72, 34.11, 4.24, "스텝바이스텝 워크북", 12, "#000000", 400, -2, font="SUIT", label="한글 제목 — SUIT")
st += T(1, "t-mock", 25.31, 136.61, 51.29, 2.82, "MOCK TEST · WORKBOOK", 8, "#b5ac9c", 600, 251)
st += [S("단계 셋 — 원 · 숫자 · 선 · 라벨", 1500)]
for k, (x, col, nx, nw, lx, lw, lb) in enumerate(((25.32, "#8aabc9", 29.81, 2.01, 25.03, 11.25, "FRAME"),
                                                   (59.21, "#cfa76b", 63.35, 2.98, 56.79, 15.77, "BUILD UP"),
                                                   (93.35, "#bd7d70", 97.35, 3.0, 94.85, 7.67, "TEST"))):
    st += C(1, f"c{k + 1}", x, 173.03, 11.12, 11.12, fill=col)
    st += T(1, f"n{k + 1}", nx, 175.73, nw, 4.94, str(k + 1), 14, "#ffffff", 700, 0, search=0.6)
    st += T(1, f"lb{k + 1}", lx, 186.26, lw, 2.65, lb, 7.5, "#b5ac9c", 500, 134, search=1.2)
st += B(1, "ln1", 37.76, 178.59, 20.12, 0.53, "#b5ac9c")
st += B(1, "ln2", 71.91, 178.59, 19.85, 0.53, "#b5ac9c")
st += [S("아래 색 점 셋", 1200)]
for k, (x, col) in enumerate(((25.32, "#8aabc9"), (33.53, "#cfa76b"), (41.74, "#bd7d70"))):
    st += B(1, f"dot{k + 1}", x, 259.06, 6.88, 2.65, col)
ELEMS[1].append({"id": "logo", "x": 25.88, "y": 270.96, "w": 31.13, "h": 7.82, "color": "#2c292a"})
st += image(25.03, 269.48, 34.01, 9.5, os.path.join(HERE, "logo.svg"), label="로고 — 「그림」에 SVG")
st += done("표지", "p1.png")

# ── 2쪽 STEP 01 간지 ──────────────────────────────────────
st += add_page("② STEP 01 간지 — 새 쪽")
st += B(2, "bg", -3, -3, 216, 303, "#8aabc9", label="바탕 블루 — 재단 여백까지", measure=False)
st += B(2, "band", -3, -3, 216, 6.88, "#faf7f0", label="위 크림 띠 · 가는 선 · 세로 막대")
st += B(2, "band-ln", -3, 3.88, 216, 0.53, "#b5ac9c")
st += B(2, "bar", 22.93, -3, 2.38, 29.9, "#faf7f0")
st += T(2, "t-step", 23.0, 31.29, 16.57, 4.23, "STEP", 12, "#ffffff", 600, 420, label="STEP 과 큰 숫자", alpha=80, search=1.5)
st += T(2, "t-01", 22.0, 36.16, 41.68, 38.81, "01", 110, "#ffffff", 800, -15, search=1, ctol=12)
st += [S("단계 셋 — 흰 원 · 테두리 원 · 선 · 숫자 · 라벨", 1500)]
st += C(2, "c1", 22.93, 216.88, 12.97, 13.23, fill="#ffffff")
st += C(2, "c2", 67.25, 217.01, 12.7, 12.97, stroke="#ffffff", sw=0.74, alpha=55)
st += C(2, "c3", 111.17, 217.01, 12.7, 12.97, stroke="#ffffff", sw=0.74, alpha=55)
st += B(2, "ln1", 37.48, 223.49, 28.05, 0.53, "#ffffff", alpha=50)
st += B(2, "ln2", 81.41, 223.49, 28.05, 0.53, "#ffffff", alpha=50)
for k, (nx, nw, col, na, lx, lw, lb) in enumerate(((28.35, 2.3, "#8aabc9", None, 22.96, 12.74, "FRAME"),
                                                   (71.81, 3.4, "#ffffff", 75, 64.39, 17.86, "BUILD UP"),
                                                   (115.8, 3.43, "#ffffff", 75, 112.98, 8.69, "TEST"))):
    st += T(2, f"n{k + 1}", nx, 220.53, nw, 5.64, str(k + 1), 16, col, 700, 0, search=0.6, alpha=na)
    st += T(2, f"lb{k + 1}", lx, 232.17, lw, 3.0, lb, 8.5, "#ffffff", 500, 138, search=1.5, alpha=85)
st += T(2, "t-sbs", 23.0, 265.78, 116.25, 9.17, "STEP BY STEP", 26, "#ffffff", 800, 478, label="아래 큰 로고 글")
st += done("STEP 01 간지", "p2.png")

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("01 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
