"""단위 04 B본문정리 — 원본 d1 reference.pdf 12·13쪽을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.
원고가 들어가는 글상자는 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로 — 자리 이름 + 임시 글 + 스타일, 끝에 원고 넣기.

자리 (블록 지도 기준): 지문번호 · 지문(B1 원문지문 본문) · 주제 · 제목(B3 요약노트) · 발문 · 문항지문 · 선지(B6 문항).
고정 글(머리·STEP 점·꼬리표·탭·주제/제목 딱지·쪽번호)은 그냥 친다.

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표. 측정 보정(보정.json) 없음.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이) — mkpage.top_of. 자간 = 원본 글자 자리 - 서체 폭(mkpage.track_from, 낱말 안 글자 간격).
이 파일은 steps.json(녹화기 대본)과 elems.json(측정할 요소 목록)을 쓴다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from mkpage import *                                                    # noqa
from core.units.render import text_h                                    # 편집기가 글상자를 자라게 하는 어림 — 상자를 그보다 작게 두지 않으려고
import pymupdf

STATE = json.load(open(os.path.join(HERE, "상태.json")))
REF = os.path.join(REPO, STATE["ref"])
REFDOC = pymupdf.open(REF)
PAGES = STATE["pages"]
ELEMS = {1: [], 2: []}
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
BAEUM = "Elice DigitalBaeum OTF"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고른다 — TTF 집은 500 이 진짜 Medium (단위 02 에서 확인)
FONTS = {"NotoSansCJKkr-Regular": (NOTO, 400), "NotoSansCJKkr-Medium": (NOTO, 500), "NotoSansCJKkr-Bold": (NOTO, 700),
         "EliceDigitalBaeumOTF": (BAEUM, 400), "EliceDigitalBaeumOTF-Bd": (BAEUM, 700)}


# ── 원본 읽기 ────────────────────────────────────────────
def spans(pno):
    """원본 쪽의 글 조각 — 지면 좌표 mm. x0 = 첫 글자 상자 왼쪽(= 글자 원점), x1 = 끝 글자 상자 오른쪽, base = 기준선, y0·y1 = 조각 상자"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ch = [c for c in s["chars"]]
                ink = [c for c in ch if c["c"].strip()]
                if not ink:
                    continue
                out.append({"text": "".join(c["c"] for c in ch).strip(), "font": s["font"], "size": round(s["size"], 2),
                            "color": "#%06x" % s["color"], "dir": l["dir"],
                            "x0": (ink[0]["bbox"][0] - ox) * MM, "x1": (ink[-1]["bbox"][2] - ox) * MM,
                            "base": (s["origin"][1] - oy) * MM, "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM,
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM) for c in ink]})
    out.sort(key=lambda r: (round(r["base"], 1), r["x0"]))
    return out


SP = {pno: spans(pno) for pno in PAGES}


def fillrect(pno, color):
    """원본 쪽에서 그 색으로 칠한 면들 [(x, y, w, h)] — 지면 좌표 mm (pymupdf get_drawings)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for g in p.get_drawings():
        f = g.get("fill")
        if f and "#%02x%02x%02x" % tuple(round(v * 255) for v in f[:3]) == color:
            r = g["rect"]
            out.append((round((r.x0 - ox) * MM, 3), round((r.y0 - oy) * MM, 3), round(r.width * MM, 3), round(r.height * MM, 3)))
    return sorted(out, key=lambda r: (r[1], r[0]))


def find(pno, start, **kw):
    """글이 start 로 시작하는 첫 조각 (kw: size·font 로 거르기)"""
    for s in SP[pno]:
        if s["text"].startswith(start) and all(s.get(k) == v for k, v in kw.items()):
            return s
    raise KeyError(f"p{pno} 「{start}」 없음")


def region(pno, size, font, y0, y1):
    """크기·서체가 같고 기준선이 y0~y1 인 줄들 (위에서 아래로)"""
    return [s for s in SP[pno] if s["size"] == size and s["font"] == font and y0 <= s["base"] <= y1]


def inword_track(lines, family, weight):
    """낱말 안 글자 간격(원본 원점 차이 - 서체 폭)의 가장 흔한 값 → 자간 ‰. 양끝맞춤 줄도 낱말 안은 자간만 들어간다
    (인디자인이 글자 간격까지 바꿔 맞춘 줄이 섞여 가운데 값은 -39 처럼 흔들린다 — 흔한 값이 단락 스타일의 자간)"""
    _, _, adv = face(family, weight)
    ds = []
    for sp in lines:
        size_mm = sp["size"] * MM
        for (a, ax, _), (b, bx, _) in zip(sp["chars"], sp["chars"][1:]):
            ds.append(((bx - ax) - adv(a) * size_mm) / size_mm * 1000)
    from collections import Counter
    return Counter(round(v) for v in ds).most_common(1)[0][0]


# ── 그리기 + 잴 요소 ─────────────────────────────────────
def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, w=None, align=None, pad=None):
    """고정 글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 글자 자리에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    e = {"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
         "ctol": 30, "search": search, "text": s, "size": size}
    if pad is not None:
        e["pad"] = pad
    ELEMS[pg].append(e)
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return text(x, round(top_of(base, size, family, weight, leading), 2), bw, bh, s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


def TR(pg, id, sp, size, color, family, weight, w=14, label=None):
    """돌린 글(아래에서 위로 읽는 탭 글) — 편집기는 글상자를 가운데 기준으로 돌린다.
    자간 = (원본 첫~끝 글자 원점 거리 - 브라우저 거리) / 사이 수.
    가운데 정렬 줄은 끝 글자 뒤 자간까지 폭에 들어가 글자 묶음 가운데가 상자 가운데에서 자간/2 만큼 앞으로 온다 → 그만큼 뒤로.
    가로(돌린 뒤): 원본 기준선 x = 상자 가운데 + (기준선 깊이 - 상자 높이/2)."""
    s = sp["text"]
    _, _, adv = face(family, weight)
    ch = sp["chars"]
    n = len(s)
    first_y, last_y, base_x = ch[0][2], ch[-1][2], ch[0][1]
    orig = abs(first_y - last_y)
    t_mm = (orig - chrome_extent(family, weight, size, s)) / (n - 1)
    track = round(t_mm / (size * MM) * 1000)
    run_c = (first_y + last_y - adv(s[-1]) * size * MM) / 2                  # 원본 글자 묶음 가운데 (위로 읽으니 끝 글자는 위로 폭만큼)
    bh = round(size * 1.45 * MM + 0.4, 1)
    depth = top_of(10, size, family, weight)                                 # 기준선 10 일 때 상자 위 → 기준선 깊이 = 10 - 위
    depth = 10 - depth
    cx = base_x - (depth - bh / 2)
    cy = run_c - t_mm / 2
    ELEMS[pg].append({"id": id, "x": sp["x0"] - 0.0, "y": min(c[2] for c in ch) - adv(s[-1]) * size * MM, "w": 3.08,
                      "h": orig + adv(s[-1]) * size * MM, "color": color, "see": color, "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - w / 2, 2), round(cy - bh / 2, 2), w, bh, s, size, color, label=label, font=family,
              weight=weight if weight != 400 else None, track=track or None, align="center")
    st.append(F('#side input[data-a="rotate"]', -90, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": ctol})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.6 * MM):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, round(sw, 3), color, pad=0.15)


def stroked(kind, x, y, w, h, stroke, sw, fill=None, radius=None, d=None, label=None):
    """테두리 있는 면·경로 — 면(rect)은 모서리 둥글기, 경로(path)는 「경로 d」(0~1 비율). 채움 없으면 「칠 없음」"""
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": kind, "from": SPOT, "to": {"mm": [SPOT["mm"][0] + max(w, 8), SPOT["mm"][1] + max(h, 8)]}}, "wait": 750}]
    if d:
        st.append(F('#side input[type="text"][data-a="d"]', d, 800))
    st += [F('#side input[data-a="w"]', w), F('#side input[data-a="h"]', h),
           F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y)]
    if radius is not None:
        st.append(F('#side input[data-a="radius"]', radius))
    if fill:
        st += [{"pick": {"at": '#side select[data-a="fill"]', "value": "__raw"}, "wait": 650},
               F('#side input[type="text"][data-a="fill"]', fill, 750)]
    else:
        st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', stroke, 750),
           F('#side input[data-a="stroke.w"]', sw)]
    return st


CONTENT = {}                                                             # 끝에 넣을 원고 — 자리 이름 → [쪽마다 글] (읽는 순서)


def line_elems(pg, name, lines, size):
    """여러 줄 자리를 줄마다 잰다 — 창은 그 줄 글자 높이만(이웃 줄이 섞이지 않게)"""
    em = size * MM
    for k, sp in enumerate(lines):
        ELEMS[pg].append({"id": f"{name}{k + 1}", "x": sp["x0"], "y": sp["base"] - 0.85 * em, "w": sp["x1"] - sp["x0"], "h": 1.1 * em,
                          "color": sp["color"], "see": sp["color"], "ctol": 40, "pad": 0.5, "search": 0.5, "text": sp["text"][:30], "size": size})


def block_elem(pg, id, lines, right, iou=0.80):
    """문단 하나를 통째로 잰다 — 양끝맞춤에서 낱말이 0.2mm 안팎 다르게 놓여 겹침 기준을 낮춘다(단위 02 와 같이)"""
    x = lines[0]["x0"]
    ELEMS[pg].append({"id": id, "x": x, "y": lines[0]["y0"], "w": round(right - x, 2), "h": lines[-1]["y1"] - lines[0]["y0"],
                      "color": lines[0]["color"], "see": lines[0]["color"], "ctol": 40, "search": 1.0,
                      "text": lines[0]["text"][:30], "size": lines[0]["size"], "shape_iou": iou})


def slot_box(pg, name, x, base, w, lines, content, temp, size, color, family, weight, leading, track, align=None, label=None):
    """원고 자리 글상자 — 임시 글을 치고 자리 이름을 붙이고 스타일을 매긴다. 원고는 끝에 한꺼번에 넣는다.
    높이 = 원본 줄 수 × 행간과 편집기 어림(text_h) 중 큰 것 — 어림보다 작으면 편집기가 상자를 키우며 아래 것을 민다."""
    CONTENT.setdefault(name, []).append(content)
    a = {"tracking": track}
    h = max(len(lines) * leading * MM, text_h(content, w, size, leading, a), text_h(temp, w, size, leading, a))
    st = text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), round(w, 2), round(h + 0.4, 1), temp, size, color,
              label=label, font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)
    st += slot(name, label=f"자리 이름 「{name}」")
    if align == "justify":
        st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    return st


def passage(pno):
    """지문 문단 둘(상자 안 · 문항 상자 안) — 8.5pt 줄을 기준선 간격이 크게 벌어지는 곳에서 나눈다"""
    rows = [s for s in SP[pno] if s["size"] == 8.5 and s["font"] == "NotoSansCJKkr-Regular"]
    out, cur = [], []
    for r in rows:
        if cur and r["base"] - cur[-1]["base"] > 10:
            out.append(cur); cur = []
        cur.append(r)
    out.append(cur)
    return out


def joined(lines):
    return " ".join(l["text"] for l in lines)


TEMP = ("Temporary passage text for styling. The real story arrives from outside and replaces these words, "
        "while the box keeps its font, leading, tracking and justified edges. ")


def temp_passage(n):
    """지문 자리의 임시 글 — 영어 문단, 길이는 원본과 비슷하게"""
    return (TEMP * (n // len(TEMP) + 1))[:n].rsplit(" ", 1)[0] + "."


def header_left(pg, code, title):
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, "#77a1c4")
    pno = PAGES[pg - 1]
    s1, s2 = find(pno, "STEP"), find(pno, "FRAME")
    st += T(pg, "t-step", s1["x0"], s1["base"], "STEP 01", 8, "#77a1c4", NOTO, 400, (s1["x0"], s1["y0"], 10.87, s1["y1"] - s1["y0"]), label="STEP 01 · FRAME")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", s2["x0"], s2["base"], "FRAME", 8, "#b4aa9a", NOTO, 700, (s2["x0"], s2["y0"], s2["x1"] - s2["x0"], s2["y1"] - s2["y0"]))
    c, t = find(pno, code, font="TTMamablockB"), find(pno, title)
    st += T(pg, "t-code", c["x0"], c["base"], code, 25, "#77a1c4", MAMA, 400, (c["x0"], c["y0"], c["x1"] - c["x0"], c["y1"] - c["y0"]), label="제목 — 코드 · 이름")
    st += T(pg, "t-title", t["x0"], t["base"], title, 13, "#231f20", GM, 500, (t["x0"], t["y0"], t["x1"] - t["x0"], t["y1"] - t["y0"]))
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    st += C(pg, "d1", 55.5, 13.059, 5.4, fill="#77a1c4")
    st += rule(pg, "dl1", 61.6, 15.759, 4.2)
    st += C(pg, "d2", 66.5, 13.059, 5.4, stroke="#b4aa9a", sw=0.8)
    st += rule(pg, "dl2", 72.6, 15.759, 4.2)
    st += C(pg, "d3", 77.5, 13.059, 5.4, stroke="#b4aa9a", sw=0.8)
    for k in range(3):
        n = find(pno, str(k + 1), font="Montserrat-Bold", size=6.0)
        st += T(pg, f"n{k + 1}", n["x0"], n["base"], str(k + 1), 6, n["color"], MS, 700, (n["x0"], n["y0"], n["x1"] - n["x0"], n["y1"] - n["y0"]), search=0.6)
    return st


def body(pg, L):
    """본문 — 지문 번호 · 지문 상자 · 주제 · 제목 · 발문 · 문항 지문 상자 · 선지. L = 왼쪽 쪽과의 가로 차이(mm, 오른쪽 쪽 2)"""
    pno = PAGES[pg - 1]
    st = []
    no = find(pno, "0", font="YeongdoOTF-Rg")
    st += [S("지문 번호 자리", 1200)]
    ELEMS[pg].append({"id": "no", "x": no["x0"], "y": no["base"] - 3.2, "w": no["x1"] - no["x0"], "h": 3.6, "color": "#af9d81", "see": "#af9d81",
                      "ctol": 30, "search": 0.6, "text": no["text"], "size": 12})
    CONTENT.setdefault("지문번호", []).append(no["text"])
    st += text(round(no["x0"], 2), round(top_of(no["base"], 12, YD, 400), 2), 12, round(12 * 1.45 * MM + 0.4, 1), "00", 12, "#af9d81",
               label="지문 번호 — 임시 글 00", font=YD, track=None)
    st += slot("지문번호", label="자리 이름 「지문번호」")

    p1, p2 = passage(pno)
    gray = fillrect(pno, "#f5f4ef")[0]                                          # 원본 면 좌표
    st += B(pg, "gray", *gray, "#f5f4ef", label="지문 상자 — 회색 면", ctol=6)
    right = gray[0] + gray[2] - (p1[0]["x0"] - gray[0])                          # 상자 안쪽 여백은 양옆이 같다 (왼쪽 5mm)
    track = inword_track(p1, NOTO, 400)
    lead = round((p1[1]["base"] - p1[0]["base"]) / MM, 2)
    block_elem(pg, "p1", p1, max(l["x1"] for l in p1))
    w = right - p1[0]["x0"] + track / 1000 * 8.5 * MM                            # 크롬은 줄 끝 글자 뒤에도 자간을 둔다
    st += slot_box(pg, "지문", p1[0]["x0"], p1[0]["base"], w, p1, joined(p1), temp_passage(len(joined(p1))), 8.5, "#231f20", NOTO, 400, lead, track,
                   align="justify", label=f"지문 — 양끝맞춤 · 행간 {lead}pt · 자간 {track}")

    st += [S("주제 · 제목 — 딱지 면 · 딱지 글 · 두 줄 자리", 1400)]
    for name, col in (("주제", "#dd978a"), ("제목", "#5ea7a5")):
        rect = fillrect(pno, col)[0]
        fill_y = rect[1]
        st += B(pg, f"tag-{name}", *rect, col)
        lab = find(pno, name, font="EliceDigitalBaeumOTF-Bd")
        win = (rect[0] + 0.25, rect[1] + 0.25, rect[2] - 0.5, rect[3] - 0.5)      # 흰 글은 딱지 면 안에서만 잰다(바깥 흰 바탕이 섞이지 않게)
        st += T(pg, f"tag-{name}-t", lab["x0"], lab["base"], name, 8, "#ffffff", BAEUM, 700, win, search=0.2, pad=0.2)
        ls = [s for s in SP[pno] if s["font"] == "NotoSansCJKkr-Medium" and fill_y - 4 < s["base"] < fill_y + 10]
        tr = inword_track(ls, NOTO, 500)
        ld = round((ls[1]["base"] - ls[0]["base"]) / MM, 2)
        line_elems(pg, name, ls, 9)
        x0 = min(l["x0"] for l in ls)
        st += slot_box(pg, name, x0, ls[0]["base"], gray[0] + gray[2] - x0, ls, "\n".join(l["text"] for l in ls),
                       "Temporary statement for this passage\nAnother temporary statement line", 9, "#231f20", NOTO, 500, ld, tr,
                       label=f"{name} — 두 줄(문단 둘) · 행간 {ld}pt")

    st += [S("문항 — 확인 상자 · 발문 · 지문 상자 · 선지", 1400)]
    ELEMS[pg].append({"id": "chk-box", "x": 20.0 + L, "y": 154.75, "w": 4.1, "h": 4.1, "color": "#8aabc9", "see": "#8aabc9", "pad": 0.3, "ctol": 30})
    st += stroked("rect", 20.273 + L, 155.023, 3.553, 3.554, "#8aabc9", 1.55, fill="#ffffff", radius=0.76, label="확인 상자 — 둥근 면 · 테두리")
    ck = (21.234 + L, 156.189, 1.96, 1.444)                                      # 꺾은선 두 마디 (21.234,157.014)-(21.957,157.633)-(23.194,156.189)
    d = f"M0 {(157.014 - 156.189) / 1.444:.4f} L{(21.957 - 21.234) / 1.96:.4f} 1 L1 0"
    r = 1.462 * MM / 2
    ELEMS[pg].append({"id": "chk-v", "x": ck[0] - r, "y": ck[1] - r, "w": ck[2] + 2 * r, "h": ck[3] + 2 * r, "color": "#b4cce0", "see": "#b4cce0",
                      "pad": 0.08, "ctol": 20})
    st += stroked("path", *ck, "#b4cce0", 1.462, d=d, label="체크 — 경로(꺾은선) · 획만")

    q = find(pno, "다음", font="EliceDigitalBaeumOTF")
    trq = track_from(REFDOC[pno - 1], (q["x0"], q["y0"], q["x1"] - q["x0"], q["y1"] - q["y0"]), q["text"], BAEUM, 400, 9)
    line_elems(pg, "발문", [q], 9)
    st += slot_box(pg, "발문", q["x0"], q["base"], gray[0] + gray[2] - q["x0"], [q], q["text"], "다음 글의 임시 발문으로 적절한 것은?", 9, "#231f20",
                   BAEUM, 400, round(9 * 1.45, 2), trq, label=f"발문 — 자간 {trq}")

    blue = fillrect(pno, "#eaf0f7")[0]
    st += B(pg, "blue", *blue, "#eaf0f7", label="문항 지문 상자 — 파란 면", ctol=6)
    right2 = blue[0] + blue[2] - (p2[0]["x0"] - blue[0])
    track2 = inword_track(p2, NOTO, 400)
    lead2 = round((p2[1]["base"] - p2[0]["base"]) / MM, 2)
    block_elem(pg, "p2", p2, max(l["x1"] for l in p2))
    w2 = right2 - p2[0]["x0"] + track2 / 1000 * 8.5 * MM
    st += slot_box(pg, "문항지문", p2[0]["x0"], p2[0]["base"], w2, p2, joined(p2), temp_passage(len(joined(p2))), 8.5, "#231f20", NOTO, 400, lead2, track2,
                   align="justify", label=f"문항 지문 — 양끝맞춤 · 행간 {lead2}pt")

    ch = [s for s in SP[pno] if s["size"] == 9.0 and s["font"] == "NotoSansCJKkr-Regular"]
    trc = inword_track(ch, NOTO, 400)
    ldc = round((ch[1]["base"] - ch[0]["base"]) / MM, 2)
    line_elems(pg, "선지", ch, 9)
    temp = "\n".join(f"{c} temporary choice {k + 1} for styling" for k, c in enumerate("①②③④⑤"))
    st += slot_box(pg, "선지", ch[0]["x0"], ch[0]["base"], gray[0] + gray[2] - ch[0]["x0"], ch, "\n".join(c["text"] for c in ch), temp,
                   9, "#231f20", NOTO, 400, ldc, trc, label=f"선지 — 다섯 줄(문단 다섯) · 행간 {ldc}pt")
    return st


# ── 12쪽 (왼쪽 면) ─────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 B1 (A4)")
st += expect_pages(1)
st += [S("① 12쪽 — B1 본문 정리", 1500)]
st += header_left(1, "B1", "본문 정리")
st += body(1, 0)
st += [S("꼬리 — 쪽번호", 1200)]
f1, f2 = find(12, "12", font="EliceDXNeolliOTF-Bd"), find(12, "STEP BY STEP", font="EliceDXNeolliOTF-Bd")
st += T(1, "f-no", f1["x0"], f1["base"], "12", 6, "#3b4247", EL, 700, (f1["x0"], f1["y0"], f1["x1"] - f1["x0"], f1["y1"] - f1["y0"]), search=0.6)
st += T(1, "f-t", f2["x0"], f2["base"], "STEP BY STEP", 6, "#231f20", EL, 700, (f2["x0"], f2["y0"], f2["x1"] - f2["x0"], f2["y1"] - f2["y0"]))
st += done("12쪽", "p1.png")

# ── 13쪽 (오른쪽 면) ───────────────────────────────────────
st += add_page("② 13쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.794, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.794, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
tg = find(13, "STEP BY STEP", font="Montserrat-Bold")
st += T(2, "tag-t", tg["x0"], tg["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, (tg["x0"], tg["y0"], tg["x1"] - tg["x0"], tg["y1"] - tg["y0"]), search=0.6)
bc = find(13, "B1", font="Montserrat-Medium")
st += T(2, "t-code", bc["x0"], bc["base"], "B1", 36, "#77a1c4", MS, 500, (bc["x0"], bc["y0"], bc["x1"] - bc["x0"], bc["y1"] - bc["y0"]), label="큰 코드 B1")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
tabs = [s for s in SP[13] if s["dir"] == (0.0, -1.0)]
seen = set()
for s in tabs:
    if s["text"] in seen:                                                      # 원본은 탭 글이 두 번 겹쳐 있다
        continue
    seen.add(s["text"])
    st += TR(2, f"tab{len(seen)}-t", s, 6.5, s["color"], MS, 700)
st += body(2, 2.0)
st += [S("꼬리 — 쪽번호", 1200)]
f1, f2 = find(13, "STEP01", font="EliceDXNeolliOTF-Bd"), find(13, "13", font="EliceDXNeolliOTF-Bd")
st += T(2, "f-t", f1["x0"], f1["base"], "STEP01", 6, "#231f20", EL, 700, (f1["x0"], f1["y0"], f1["x1"] - f1["x0"], f1["y1"] - f1["y0"]))
st += T(2, "f-no", f2["x0"], f2["base"], "13", 6, "#3b4247", EL, 700, (f2["x0"], f2["y0"], f2["x1"] - f2["x0"], f2["y1"] - f2["y0"]), search=0.6)
st += done("13쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("04 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
