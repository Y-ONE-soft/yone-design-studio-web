"""단위 03 A본문OX — 원본 d1 reference.pdf 8·9쪽(A2 본문 O/X)을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.
원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로 — 원고가 들어갈 글상자(지문 번호·지문·문제 번호·발문·진술 번호·진술)는
자리 이름 + 임시 글로 만들고 스타일을 매긴 뒤, 끝에 원고(자리 이름 → 글)를 넣어 원본과 비교한다. 견본: 02B-원고자리/make.py.

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표·경로. 보정 파일은 쓰지 않는다.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이)(mkpage.top_of). 자간 = 원본 글자 자리 - 브라우저 글자 자리(mkpage.track_from).
돌린 글(오른쪽 탭)은 회전 축(상자 가운데)에서 거꾸로 풀어 상자 자리를 정한다 — rot_text 설명.
O·X 는 원본이 Type3(윤곽)이라 서체 이름이 없다 — 후보 서체로 같은 크기 글을 그려 잉크 양·글자 상자를 맞대 Montserrat 800 으로 정했다
(원본 O 잉크 3.37mm² · 2.50×2.33 / Montserrat ExtraBold 3.32 · 2.48×2.31, X 2.81 / 2.77).
O/X 상자는 원본에서 진술 끝에 붙어 흐르는 개체지만, 편집기 앵커 개체는 글 끝을 어림(text_end)으로 잡아 0.3mm 안에 못 세운다 — 원본 자리에 고정해 그린다.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from mkpage import *                                                    # noqa
from mkpage import _color
from core.units.render import text_h                                    # 서버가 글 높이를 어림하는 식 — 상자가 저절로 자라지 않게(읽기만)
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
LOTTE = "12LotteMartDreamBold"
LINK = "#b5ac9c"               # O/X 상자 테두리 · 가운데 막대


def ref_page(pg):
    return REFDOC[PAGES[pg - 1] - 1]


def win(base, size):
    """글 잴 창 — 기준선 둘레(윗높이 0.95em · 아랫높이 0.3em). 원본 조각 상자는 행간째라 위아래 줄을 물어 온다"""
    return base - 0.95 * size * MM, 1.25 * size * MM


def T(pg, id, x, base, s, size, color, family, weight, x1, label=None, w=None, temp=None, leading=None, search=0.8, ctol=30, shape_iou=None, pad=0.5):
    """원본 글 하나. x = 첫 글자 자리(원점), base = 기준선, x1 = 끝 글자 오른쪽(원본). 자간은 원본 글자 자리에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    y0, h0 = win(base, size)
    track = track_from(ref_page(pg), (x, y0, x1 - x, h0), s, family, weight, size)
    track = track if abs(track) > 8 else 0
    e = {"id": id, "x": x, "y": round(y0, 2), "w": round(x1 - x, 2), "h": round(h0, 2), "color": color, "see": color,
         "ctol": ctol, "pad": pad, "search": search, "text": s, "size": size}
    if shape_iou:
        e["shape_iou"] = shape_iou
    ELEMS[pg].append(e)
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading)


def rot_text(pg, id, s, size, color, family, weight, xb, y_first, y_last, bbox, w=14):
    """아래에서 위로 읽는 글(회전 -90°). 원본: 기준선 x = xb, 첫 글자 원점 y = y_first, 끝 글자 원점 y = y_last.
    편집기: 상자(w × bh)를 가운데 축으로 -90° 돌린다 → 상자 안 가로(u)가 지면 위쪽(-y), 상자 안 세로(v)가 지면 x.
      기준선 = 상자 위 + q (q = 반 행간 + 윗높이) → 지면 x = cx + (q - bh/2) = xb
      가운데 정렬 글 줄 폭 Wr(크롬은 끝 글자 뒤에도 자간) → 첫 글자 원점 = cy + Wr/2 = y_first"""
    asc, desc, adv = face(family, weight)
    sm = size * MM
    ext = chrome_extent(family, weight, size, s)
    track = round(((y_first - y_last) - ext) / (len(s) - 1) / sm * 1000) if len(s) > 1 else 0
    tr = track / 1000 * sm
    wr = ext + adv(s[-1]) * sm + len(s) * tr
    lead = size * 1.45 * MM
    bh = round(lead + 0.4, 1)
    q = (lead - (asc + desc) * sm) / 2 + asc * sm
    cx, cy = xb + bh / 2 - q, y_first - wr / 2
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - w / 2, 2), round(cy - bh / 2, 2), w, bh, s, size, color, font=family, weight=weight if weight != 400 else None,
              track=track or None, align="center")
    st.append(F('#side input[data-a="rotate"]', -90, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": ctol})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


def ox_box(pg, id, x, y, w, h, r, sw_pt):
    """O/X 상자 — 둥근 네모(흰 칠 · 테두리 가운데 정렬). 원본 경로 그대로: x·y·w·h = 경로(획 가운데), r = 모서리 둥글기"""
    o = sw_pt * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - o, 2), "y": round(y - o, 2), "w": round(w + 2 * o, 2), "h": round(h + 2 * o, 2),
                      "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30})       # 테두리 색 — 진술 끝 글자의 흐린 가장자리를 물지 않게 좁게
    st = box(round(x, 3), round(y, 3), round(w, 3), round(h, 3), "#ffffff", radius=round(r, 3))
    st += _color("stroke.color", LINK)
    st.append(F('#side input[data-a="stroke.w"]', round(sw_pt, 3)))
    return st


# ── 원본 읽기 ──────────────────────────────────────────────
def spans(pg):
    p = ref_page(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ch = s["chars"]
                ink = [c for c in ch if c["c"].strip()]
                if not ink:
                    continue
                out.append({"t": "".join(c["c"] for c in ch), "font": s["font"], "size": round(s["size"], 2), "color": "#%06x" % s["color"],
                            "x": (ink[0]["origin"][0] - ox) * MM, "x1": (ink[-1]["bbox"][2] - ox) * MM, "base": (s["origin"][1] - oy) * MM,
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM, (c["bbox"][2] - ox) * MM) for c in ch],
                            "dir": l["dir"], "bb": ((s["bbox"][0] - ox) * MM, (s["bbox"][1] - oy) * MM, (s["bbox"][2] - s["bbox"][0]) * MM, (s["bbox"][3] - s["bbox"][1]) * MM)})
    return out


def passage(pg):
    """지문(8.5pt) — 글자를 기준선(원점 y)별로 모은다. 원본은 두 줄 글자가 한 조각에 섞여 나온다(내용 흐름 순서는 줄마다 맞다).
    → (x, 첫 기준선, 줄 수, 글(줄 나눔 없이), (위, 아래), 오른쪽 끝, 공백 뺀 글자 간격 중앙값 ‰)"""
    p = ref_page(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    rows = {}
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if round(s["size"], 1) == 8.5:
                    for c in s["chars"]:
                        rows.setdefault(round(c["origin"][1], 1), []).append(c)
    _, _, adv = face(NOTO, 400)
    lines, rights, gaps = [], [], []
    for y in sorted(rows):
        ch = rows[y]
        ink = [c for c in ch if c["c"].strip()]
        lines.append(("".join(c["c"] for c in ch).strip(), (y - oy) * MM, (ink[0]["origin"][0] - ox) * MM, (ink[-1]["bbox"][2] - ox) * MM))
        for a, b_ in zip(ch, ch[1:]):
            if a["c"].strip() and b_["c"].strip():
                gaps.append(((b_["origin"][0] - a["origin"][0]) - adv(a["c"]) * 8.5) / 8.5 * 1000)
    right = statistics.median(r[3] for r in lines[:-1])                      # 양끝 맞춘 줄의 끝 = 글상자 오른쪽
    txt = " ".join(r[0] for r in lines)
    top, bot = lines[0][1] - 0.95 * 8.5 * MM, lines[-1][1] + 0.3 * 8.5 * MM
    return lines[0][2], lines[0][1], len(lines), txt, (top, bot), round(right, 2), round(statistics.median(gaps))


def rows_of(pg):
    """진술 줄 — 번호(롯데마트드림 9pt) · 글(Noto 9.5pt) · O · X 조각, 그리고 O/X 상자 경로 · 가운데 막대"""
    sp = spans(pg)
    nums = [s for s in sp if s["font"].endswith("LotteMartDreamBold")]
    stm = [s for s in sp if s["size"] == 9.5 and s["t"].strip()]
    os_ = [s for s in sp if s["t"] == "O" and s["font"].startswith("Type3")]
    xs = [s for s in sp if s["t"] == "X" and s["font"].startswith("Type3")]
    p = ref_page(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    boxes, bars = [], []
    for g in p.get_drawings():
        r = g["rect"]
        rr = ((r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM)
        if len(g["items"]) == 20 and g.get("fill") == (1.0, 1.0, 1.0):
            first = g["items"][0]                                                # 첫 획 = 왼쪽 세로 선 → 모서리 = 위 가로 선 시작 - 왼쪽
            top = [it for it in g["items"] if it[0] == "l" and abs(it[1].y - it[2].y) < 1e-3][0]
            boxes.append(rr + ((top[1].x - first[1].x) * MM, g["width"]))
        elif g.get("fill") and "#%02x%02x%02x" % tuple(round(v * 255) for v in g["fill"][:3]) == LINK and rr[2] < 1:
            bars.append(rr)
    out = []
    for n in sorted(nums, key=lambda s: s["base"]):
        near = lambda L: min(L, key=lambda s: abs(s["base"] - n["base"]))
        t, o, x = near(stm), near(os_), near(xs)
        bx = min(boxes, key=lambda b: abs(b[1] + b[3] / 2 - n["base"] + 1))
        br = min(bars, key=lambda b: abs(b[1] + b[3] / 2 - n["base"] + 1))
        out.append((n, t, o, x, bx, br))
    return out


TEMP = ("Temporary text for styling. The passage keeps going in plain sentences until the real content arrives from outside, "
        "and the paragraph composer picks the line ends. ")
TEMP_S = "A temporary statement sits here until the real one arrives from outside and fills the row. "


def temp_of(base, n):
    """임시 글 — 올 원고의 꼴(영어 문장)을 흉내 낸다. 길이는 원본과 비슷하게"""
    return (base * (n // len(base) + 1))[:n].rsplit(" ", 1)[0] + "."


CONTENT = {"지문번호": [], "지문": [], "문제번호": [], "발문": [], "진술번호": [], "진술": []}


def P(pg, id, label):
    """지문 — 연파랑 바탕 위 글상자 하나. 양끝맞춤 · 행간 15pt · 자간(원본 글자 간격 중앙값). 줄 끝은 단락 컴포저가.
    글상자 폭 = 원본 줄 끝 - 시작 + 끝 글자 뒤 자간(크롬은 줄 끝 글자 뒤에도 자간을 둔다)"""
    x, base, n, txt, yb, right, track = passage(pg)
    w = round(right - x + track / 1000 * 8.5 * MM, 2)
    ELEMS[pg].append({"id": id, "x": round(x, 2), "y": round(yb[0], 2), "w": round(right - x, 2), "h": round(yb[1] - yb[0], 2), "color": "#231f20",
                      "see": "#231f20", "ctol": 40, "search": 1.0, "text": txt[:30], "size": 8.5,
                      "shape_iou": 0.80})          # 문단은 양끝맞춤에서 단어가 0.2mm 안팎 다르게 놓인다 — 겹침 기준을 낮춘다
    CONTENT["지문"].append(txt)
    temp = temp_of(TEMP, len(txt))
    h = round(max(n * 15 * MM, text_h(txt, w, 8.5, 15, {"tracking": track}), text_h(temp, w, 8.5, 15, {"tracking": track})) + 0.5, 1)
    st = text(round(x, 2), round(top_of(base, 8.5, NOTO, 400, 15), 2), w, h, temp, 8.5, "#231f20",
              label=label, leading=15, align="justify", font=NOTO, track=track)
    st += slot("지문", label="자리 이름 「지문」")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    return st


def body(pg, no, label_no):
    """지문 번호 · 연파랑 바탕 · 지문 · 문제 머리(번호 | 발문) · 진술 다섯 줄(번호 · 글 · O/X 상자)"""
    sp = spans(pg)
    st = [S(f"지문 {no} — 번호 · 바탕 · 본문", 1500)]
    pn = [s for s in sp if s["font"].startswith("YeongdoOTF")][0]
    st += T(pg, "no", pn["x"], pn["base"], no, 12, "#af9d81", YD, 400, pn["x1"], label="지문 번호 자리", temp="00", search=0.6)
    st += slot("지문번호")
    CONTENT["지문번호"].append(pn["t"])          # 원본 글 그대로 「01 」 — 끝 공백을 보고 영도체가 끝 숫자 꼴을 고른다(렌더러가 끝 공백을 지킨다)
    p = ref_page(pg)
    bg = [g for g in p.get_drawings() if g.get("fill") and "#%02x%02x%02x" % tuple(round(v * 255) for v in g["fill"][:3]) == "#e5f2f9"][0]["rect"]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    st += B(pg, "bg", round((bg.x0 - ox) * MM, 2), round((bg.y0 - oy) * MM, 2), round(bg.width * MM, 2), round(bg.height * MM, 2), "#e5f2f9",
            label="지문 바탕 — 연파랑 면", ctol=10)                               # 흰 바탕과 26 차이 — 너그러우면 흰 곳까지 잡는다
    st += P(pg, "p", f"지문 {no} 본문 — 임시 글")

    st += [S("문제 머리 — 번호 | 발문", 1400)]
    qn = [s for s in sp if s["font"].endswith("EliceDXNeolliOTF-Bd") and s["size"] == 10][0]
    c = qn["chars"]                                                           # '0' '1' ' ' '|' '\t'
    bar = [k for k in c if k[0] == "|"][0]
    one = [k for k in c if k[0].strip()][1]
    st += T(pg, "q-no", c[0][1], qn["base"], no, 10, "#8d7cba", EL, 700, one[3], label="문제 번호 자리", temp="00", search=0.3, pad=0.3)
    st += slot("문제번호")
    CONTENT["문제번호"].append(no)
    st += T(pg, "q-bar", bar[1], qn["base"], "|", 10, "#8d7cba", EL, 700, bar[3], label="막대 — 고정 글", search=0.3, pad=0.3)
    qi = [s for s in sp if s["font"].endswith("EliceDXNeolliOTF-Md")][0]
    st += T(pg, "q-t", qi["x"], qi["base"], qi["t"].strip(), 7.5, "#231f20", EL, 500, qi["x1"], label="발문 자리", w=round(qi["x1"] - qi["x"] + 12, 1),
            temp="임시 발문 — 다음 글을 읽고 물음에 답하시오. 맞으면 O, 틀리면 X 를 고르시오.")
    st += slot("발문")
    CONTENT["발문"].append(qi["t"].strip())

    for k, (n, t, o, x, bx, br) in enumerate(rows_of(pg)):
        st += [S(f"진술 {k + 1:02d} — 번호 · 글 · O/X 상자", 1200)]
        num = n["t"].strip()
        st += T(pg, f"s{k + 1}-no", n["x"], n["base"], num, 9, "#92b0d3", LOTTE, 400, n["x1"], temp="00", search=0.6)
        st += slot("진술번호")
        CONTENT["진술번호"].append(num)
        s = t["t"].strip()
        st += T(pg, f"s{k + 1}", t["x"], t["base"], s, 9.5, "#231f20", NOTO, 400, t["x1"], w=round(min(180 - t["x"], (t["x1"] - t["x"]) * 1.3 + 10), 1),
                temp=temp_of(TEMP_S, len(s)))
        st += slot("진술")
        CONTENT["진술"].append(s)
        st += ox_box(pg, f"s{k + 1}-box", *bx)
        st += B(pg, f"s{k + 1}-bar", round(br[0], 3), round(br[1], 3), round(br[2], 3), round(br[3], 3), LINK, pad=0.15)
        st += T(pg, f"s{k + 1}-o", o["x"], o["base"], "O", 9, "#8aabc9", MS, 800, o["x1"], search=0.6)
        st += T(pg, f"s{k + 1}-x", x["x"], x["base"], "X", 9, "#bd7d70", MS, 800, x["x1"], search=0.6)
    return st


def header_left(pg, code, title):
    sp = spans(pg)
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(pg, "band", -3, -5.5, 213, 29, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -4.5, 2.2, 28.1, "#77a1c4")
    stp = [s for s in sp if s["t"] == "STEP" and s["size"] == 8][0]
    num = [s for s in sp if s["t"].strip() == "01" and s["size"] == 8][0]
    st += T(pg, "t-step", stp["x"], stp["base"], "STEP 01", 8, "#77a1c4", NOTO, 400, num["x1"], label="STEP 01 · FRAME")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    fr = [s for s in sp if s["t"] == "FRAME"][0]
    st += T(pg, "t-frame", fr["x"], fr["base"], "FRAME", 8, "#b4aa9a", NOTO, 700, fr["x1"])
    cd = [s for s in sp if s["font"] == "TTMamablockB"][0]
    st += T(pg, "t-code", cd["x"], cd["base"], code, 25, "#77a1c4", MAMA, 400, cd["x1"], label="제목 — 코드 · 이름")
    tt = [s for s in sp if s["font"] == "GmarketSansMedium"][0]
    st += T(pg, "t-title", tt["x"], tt["base"], title, 13, "#231f20", GM, 500, tt["x1"])
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, fill="#77a1c4")
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    for k, (d, col) in enumerate((("1", "#ffffff"), ("2", "#b4aa9a"), ("3", "#b4aa9a"))):
        s = [s for s in sp if s["t"] == d and s["font"] == "Montserrat-Bold"][0]
        st += T(pg, f"n{k + 1}", s["x"], s["base"], d, 6, col, MS, 700, s["x1"], search=0.6)
    return st


def footer(pg):
    sp = spans(pg)
    st = [S("꼬리 — 쪽번호", 1200)]
    for s in sorted([s for s in sp if s["font"] == "EliceDXNeolliOTF-Bd" and s["size"] == 6], key=lambda s: s["x"]):
        col = "#3b4247" if s["t"].strip().isdigit() else "#231f20"
        st += T(pg, "f-" + ("no" if col == "#3b4247" else "t"), s["x"], s["base"], s["t"].strip(), 6, col, EL, 700, s["x1"], search=0.6)
    return st


# ── 8쪽 (왼쪽 면) ──────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 A2 (A4)")
st += expect_pages(1)
st += [S("① 8쪽 — A2 본문 O/X", 1500)]
st += header_left(1, "A2", "본문 O/X")
st += body(1, "01", "01")
st += footer(1)
st += done("8쪽", "p1.png")

# ── 9쪽 (오른쪽 면) ────────────────────────────────────────
st += add_page("② 9쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", 0, -3, 213, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
SP9 = spans(2)
tg = [s for s in SP9 if s["t"] == "STEP BY STEP" and s["font"] == "Montserrat-Bold"][0]
st += T(2, "tag-t", tg["x"], tg["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, tg["x1"], search=0.6)
cd = [s for s in SP9 if s["font"] == "Montserrat-Medium"][0]
st += T(2, "t-code", cd["x"], cd["base"], "A2", 36, "#77a1c4", MS, 500, cd["x1"], label="큰 코드 A2")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
seen = set()
for s in [s for s in SP9 if s["size"] == 6.5]:
    if s["t"] in seen:
        continue                                                              # 원본은 탭 글이 두 벌 겹쳐 있다
    seen.add(s["t"])
    k = len(seen)
    ch = s["chars"]
    ys = [c[2] for c in ch]
    st += rot_text(2, f"tab{k}-t", s["t"], 6.5, s["color"], MS, 700, ch[0][1], ys[0], ys[-1], tuple(round(v, 2) for v in s["bb"]))
st += body(2, "02", "02")
st += footer(2)
st += done("9쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("03 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
