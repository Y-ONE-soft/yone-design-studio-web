"""단위 08 간지 — 원본 d1 reference.pdf 28·29쪽(C빈칸어휘 다음 STEP 02 간지 펼침면)을 A4 한 문서 두 쪽으로. 전부 마우스·키보드.

값은 모두 원본 PDF 에서 뽑았다(pymupdf 그림·글 조각·ExtGState). 지면 좌표 mm = 원본 좌표 - 재단 여백 3mm.
- 28쪽 = 단위 01 의 2쪽(STEP 01 간지)과 같은 꼴 — 바탕 #cfa76b, 2단계(BUILD UP)가 활성.
- 29쪽 = 오른쪽 탭 셋(흰 면 16%·92%·16%) + 돌린 글(위→아래로 읽는다, 90°) + 큰 「02」(흰 14%, 지면 밖으로 넘친다)
  + 교재 이름·단원 이름(책마다 바뀌는 글 → 원고 자리 「교재명」「단원명」, 오른쪽 맞춤, 원고 넣기로 채운다).
불투명은 PDF 의 폼 XObject 가 쓰는 ExtGState(ca)에서 읽었다 — pymupdf 글 조각의 alpha 에는 안 나온다
(29쪽 큰 02 = GS2 0.14, 탭 글 01·03 = GS6 0.80, 28쪽 STEP BY STEP = GS1 0.90).
Type3(윤곽) 글은 기준선 = 글자 상자 위 + 0.9×크기. 굵기는 잉크 양을 재서 정했다(크롬에서 100~900 을 그려 원본 면적과 비교 —
STEP 600 · 02·숫자·STEP BY STEP 800 · 단계 라벨 600 · 탭 글 700 · Gmarket 교재명 700 · 단원명 500).
측정 보정은 쓰지 않는다. 이 파일은 steps.json(녹화기 대본)과 elems.json(측정할 요소 목록)을 쓴다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf
REF = pymupdf.open(os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf"))
PAGES = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))["pages"]

MS = "Montserrat"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 크롬이 Bold 를 고른다 — TTF 집은 500 이 진짜 Medium (단위 02B)
BG = "#cfa76b"
CREAM, RULE, WHITE = "#faf7f0", "#b5ac9c", "#ffffff"
ELEMS = {1: [], 2: []}


def mix(color, alpha, under=BG):
    """투명도가 있으면 밑색과 섞여 보이는 색 — 잴 때 쓴다"""
    if alpha is None or alpha >= 100:
        return color
    c, b = [int(color[i:i + 2], 16) for i in (1, 3, 5)], [int(under[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join("%02x" % round(bb + (cc - bb) * alpha / 100) for cc, bb in zip(c, b))


def t3scale(pdf_page, box):
    """Type3 글의 실제 글자 배율 — 폰트의 FontMatrix(원본 PDF 값). d1 의 Type3 는 모두 0.00100708 → 글자가 크기보다 0.708% 크다.
    (단위 08 1판: 300pt 큰 02 가 원본보다 0.59mm 낮게 나와 찾음 — 서체 상자는 Montserrat ExtraBold 와 같고 배율만 다르다)"""
    import re
    t = pdf_page.trimbox
    x, y, w, h = box
    R = pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM)
    for b in pdf_page.get_text("dict", clip=R)["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                m = re.search(r"\((\d+) 0 R\)", sp["font"])
                if m:
                    return float(re.search(r"/FontMatrix \[ ([-\d.]+)", REF.xref_object(int(m.group(1)))).group(1)) * 1000
    return 1.0


def track_v(pdf_page, box, s, family, weight, size):
    """돌린 글의 자간(‰) — mkpage.track_from 과 같은 계산을 세로 글자 위치(origin y)로"""
    if len(s) < 2:
        return 0
    t = pdf_page.trimbox
    x, y, w, h = box
    R = pymupdf.Rect(t.x0 + (x - 0.3) / MM, t.y0 + (y - 0.3) / MM, t.x0 + (x + w + 0.3) / MM, t.y0 + (y + h + 0.3) / MM)
    ch = [c for b in pdf_page.get_text("rawdict", clip=R)["blocks"] for l in b.get("lines", []) for sp in l["spans"] for c in sp["chars"] if c["c"].strip()]
    orig = (ch[-1]["origin"][1] - ch[0]["origin"][1]) * MM
    return round((orig - chrome_extent(family, weight, size, s)) / (len(s) - 1) / (size * MM) * 1000)


def T(pg, id, x, y, w, h, s, size, color, weight, font=MS, label=None, search=2, alpha=None, see=None, ctol=24, leading=None, pad=None):
    """Type3 글 하나 — 원본 글자 상자(x,y,w,h) · 크기 pt · 색 · 굵기 · 불투명. 기준선 = 상자 위 + 0.9×크기"""
    e = {"id": id, "x": x, "y": y, "w": w, "h": h, "color": color, "see": see or mix(color, alpha), "ctol": ctol,
         "search": search, "text": s, "size": size}
    if pad is not None:
        e["pad"] = pad
    ELEMS[pg].append(e)
    bw = round(w * 1.25 + size * 0.35, 1) if size < 100 else round(w + size * MM * 0.3, 1)   # 줄바꿈 없게 · 큰 글은 지면 밖으로 너무 안 나가게
    k = t3scale(REF[PAGES[pg - 1] - 1], (x, y, w, h))
    base, size = y + 0.9 * size * MM, round(size * k, 2)                 # 기준선은 원본 크기로(글자 상자 위 + 0.9em), 그리는 크기는 배율째
    leading = leading and round(leading * k, 2)
    bh = round(leading * MM + 0.4, 1) if leading else round(size * 0.3528 * 1.5, 1)   # 큰 02 는 행간 = 크기 — 상자가 지면 아래로 안 나가게
    top = top_of(base, size, font, weight, leading)
    track = track_from(REF[PAGES[pg - 1] - 1], (x, y, w, h), s, font, weight, size)
    return text(x, round(top, 2), bw, bh, s, size, color, label=label, font=font, weight=weight, track=track or None, alpha=alpha, leading=leading)


def V(pg, id, base_x, y0, s, size, color, weight, box, alpha=None, see=None, label=None):
    """돌린 글(90°, 위에서 아래로 읽는다) — base_x = 기준선 x, y0 = 첫 글자 시작 y, box = 원본 글자 상자(잴 자리).
    편집기는 상자 가운데를 축으로 돌린다: 왼쪽 맞춤 글의 첫 글자 기준선 점 (bx, by+b) 가
    (cx + cy - by - b, cy + bx - cx) 로 간다 → bx = X - bw/2 - bh/2 + b, by = Y - bh/2 + bw/2 (b = 반 행간 + 서체 윗높이)."""
    ELEMS[pg].append({"id": id, "x": box[0], "y": box[1], "w": box[2], "h": box[3], "color": color, "see": see or mix(color, alpha),
                      "ctol": 24, "search": 0.8, "pad": 0.8, "text": s, "size": size})
    size = round(size * t3scale(REF[PAGES[pg - 1] - 1], box), 2)
    track = track_v(REF[PAGES[pg - 1] - 1], box, s, MS, weight, size)
    bw = round(box[3] * 1.25 + size * 0.35, 1)
    bh = round(size * 0.3528 * 1.5, 1)
    b = 50 - top_of(50, size, MS, weight)
    bx, by = base_x - bw / 2 - bh / 2 + b, y0 - bh / 2 + bw / 2
    st = text(round(bx, 2), round(by, 2), bw, bh, s, size, color, label=label, font=MS, weight=weight, track=track or None, alpha=alpha)
    return st + [F('#side input[data-a="rotate"]', 90, 600)]


def B(pg, id, x, y, w, h, fill, label=None, measure=True, alpha=None, ctol=None, see=None):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": see or mix(fill, alpha), "pad": 0.6,
                          "ctol": ctol or (24 if alpha else 30)})
    return box(x, y, w, h, fill, label=label, alpha=alpha)


def C(pg, id, x, y, w, h, fill=None, stroke=None, sw=None, alpha=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill or stroke, "see": mix(fill or stroke, alpha), "pad": 0.6,
                      "ctol": 24 if alpha else 30})
    return ellipse(x, y, w, fill=fill, stroke=stroke, sw=sw, h=h, alpha=alpha)


def head(pg):
    """두 쪽 공통 — 바탕(재단 여백까지) · 위 크림 띠 · 가는 선"""
    st = B(pg, "bg", -3, -3, 216, 303, BG, label="바탕 — 재단 여백까지", measure=False)
    st += B(pg, "band", -3, -3, 216, 6.88, CREAM, label="위 크림 띠 · 가는 선")
    st += B(pg, "band-ln", -3, 3.88, 216, 0.53, RULE)
    return st


# ── 28쪽 STEP 02 간지 (왼쪽 면) ────────────────────────────────
st = open_doc("스텝바이스텝 워크북 STEP 02 간지 (A4)")
st += expect_pages(1)
st += [S("① 28쪽 — STEP 02 간지", 1500)]
st += head(1)
st += B(1, "bar", 22.93, -3, 2.38, 29.9, CREAM, label="세로 막대")
st += T(1, "t-step", 23.0, 31.29, 16.57, 4.23, "STEP", 12, WHITE, 600, label="STEP 과 큰 숫자", alpha=80, search=1.5)
st += T(1, "t-02", 22.0, 36.16, 49.28, 38.81, "02", 110, WHITE, 800, search=1, ctol=12)
st += [S("단계 셋 — 테두리 원 · 흰 원(활성) · 선 · 숫자 · 라벨", 1500)]
st += C(1, "c1", 23.06, 217.01, 12.7, 12.97, stroke=WHITE, sw=0.75, alpha=55)
st += C(1, "c2", 67.12, 216.88, 12.97, 13.23, fill=WHITE)
st += C(1, "c3", 111.17, 217.01, 12.7, 12.97, stroke=WHITE, sw=0.75, alpha=55)
st += B(1, "ln1", 37.48, 223.49, 28.05, 0.53, WHITE, alpha=50)
st += B(1, "ln2", 81.41, 223.49, 28.05, 0.53, WHITE, alpha=50)
for k, (nx, nw, col, na, lx, lw, lb) in enumerate(((28.35, 2.3, WHITE, 75, 22.96, 12.74, "FRAME"),
                                                   (71.81, 3.4, BG, None, 64.39, 17.86, "BUILD UP"),
                                                   (115.8, 3.43, WHITE, 75, 112.98, 8.69, "TEST"))):
    st += T(1, f"n{k + 1}", nx, 220.53, nw, 5.64, str(k + 1), 16, col, 800, search=0.6, alpha=na)
    st += T(1, f"lb{k + 1}", lx, 232.17, lw, 3.0, lb, 8.5, WHITE, 600, search=1.5, alpha=85)
st += T(1, "t-sbs", 23.0, 265.78, 116.25, 9.17, "STEP BY STEP", 26, WHITE, 800, label="아래 큰 로고 글", alpha=90)
st += done("28쪽 STEP 02 간지", "p1.png")

# ── 29쪽 (오른쪽 면) ──────────────────────────────────────────
st += add_page("② 29쪽 — 새 쪽")
st += head(2)
st += [S("오른쪽 탭 셋 — 흰 면 16% · 92% · 16% (재단 여백까지)", 1500)]
TAB1 = mix(WHITE, 16)
st += B(2, "tab1", 202.15, 57.06, 10.85, 25.93, WHITE, alpha=16, ctol=8)
st += B(2, "tab2", 202.15, 86.96, 10.85, 25.93, WHITE, alpha=92)
st += B(2, "tab3", 202.15, 117.13, 10.85, 25.93, WHITE, alpha=16, ctol=8)
st += [S("탭 글 — 90° 돌린 글", 1500)]
BASE_X = round((594.4935 - REF[PAGES[1] - 1].trimbox.x0) * MM, 2)        # 원본 Tm 의 기준선 x
st += V(2, "tab1-t", BASE_X, 68.44, "01", 6.5, WHITE, 700, (206.49, 68.44, 2.29, 2.67), alpha=80, see=mix(WHITE, 80, TAB1))
st += V(2, "tab2-t", BASE_X, 94.37, "STEP 02", 6.5, BG, 700, (206.49, 94.37, 2.29, 10.99))
st += V(2, "tab3-t", BASE_X, 128.24, "03", 6.5, WHITE, 700, (206.49, 128.24, 2.29, 3.13), alpha=80, see=mix(WHITE, 80, TAB1))
st += [S("큰 02 — 흰 14%, 지면 밖으로 넘친다", 1500)]
st += T(2, "big-02", 87.01, 176.4, 133.36, 105.84, "02", 300, WHITE, 800, alpha=14, ctol=7, search=1.5, leading=300)
st += [S("교재 이름 · 단원 이름 — 책마다 바뀌는 글이라 원고 자리로", 1500)]
CONTENT = {}
RIGHT = 170.0                                                              # 두 줄 다 끝 글자 끝이 170.0mm (원본 오른쪽 맞춤)


def title(id, slot_name, temp, s, base, size, weight, box):
    """오른쪽 맞춤 글 자리 — 임시 글로 그리고 자리 이름을 붙인 뒤 스타일. 원고는 끝에 넣는다.
    크롬은 줄 끝 글자 뒤에도 자간을 두므로 상자 오른쪽 = 원본 끝 글자 끝 + 자간(mm)."""
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
st += done("29쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("08 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
