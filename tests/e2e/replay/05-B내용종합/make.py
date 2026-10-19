"""단위 05 B내용종합 — 원본 d1 reference.pdf 16·17쪽을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
견본 대본 02B-원고자리 와 같은 디자인 집(머리 띠·단계 점·제목·옆 탭·쪽번호)에, 지문(하늘색 상자) + 문항 셋(번호·발문·선지 넷).

원고가 들어가는 글상자 — 지문번호 · 지문 · 문항번호 · 발문 · 선지 — 는 임시 글 + 자리 이름 + 스타일로 만들고,
끝에 원고(자리 이름 → 글, 원본 PDF 에서 읽은 글)를 넣어 원본과 비교한다. 고정 글(머리·탭·쪽번호)은 그냥 친다.
값은 모두 원본 PDF 에서 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표. 글상자 위 끝 = top_of(기준선 공식), 자간 = track_from.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf

REF = os.path.join(REPO, "tests/e2e/replay/_원본/워크북_d1.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
INK, PURPLE, SKYBOX = "#231f20", "#8d7cba", "#e5f2f9"


def spans(pno):
    """원본 쪽의 글 조각 — 빈칸만인 조각은 뺀다. x = 첫 글자 시작(글자 원점), x1 = 끝 글자 끝, base = 기준선 (지면 mm)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ink = [c for c in s["chars"] if c["c"].strip()]
                if not ink:
                    continue
                out.append({"t": "".join(c["c"] for c in s["chars"]).strip(), "size": round(s["size"], 1), "font": s["font"],
                            "color": "#%06x" % s["color"], "x": (ink[0]["origin"][0] - ox) * MM, "x1": (ink[-1]["bbox"][2] - ox) * MM,
                            "base": (s["origin"][1] - oy) * MM, "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM})
    return out


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, rotate=None, at=None, w=None,
      align=None, temp=None, pad=None):
    """원본 글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 글자 자리에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    length = bbox[3] if rotate else bbox[2]                                 # 돌린 글은 원본 상자의 세로가 글 길이
    if rotate:
        track = round((length - nat) / max(len(s), 1) / (size * MM) * 1000) if len(s) > 1 else 0
    else:                                                                   # 원본 글자 위치 - 브라우저(커닝·대체 글자 포함) 거리
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    e = {"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
         "ctol": 30, "search": search, "text": s, "size": size}
    if pad is not None:
        e["pad"] = pad
    ELEMS[pg].append(e)
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    if at:                                                                  # 돌린 글 — 상자 가운데를 원본 글 가운데에
        cx, cy = at
        bx, by = cx - bw / 2, cy - bh / 2
    else:
        bx, by = x, top_of(base, size, family, weight, leading)
    st = text(round(bx, 2), round(by, 2), bw, bh, temp or s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)
    if rotate:
        st.append(F('#side input[data-a="rotate"]', rotate, 600))
    return st


def R(pg, id, pno, s, color, size=6.5, family=MS, weight=700, bw=14):
    """돌린 글(아래에서 위로 읽는 옆 탭) — 원본 글자 원점에서 바로 계산한다(02B 는 이 글을 보정.json 으로 맞췄다).
    자간 = (원본 첫~끝 글자 원점 거리 - 브라우저 같은 거리) / 사이 수 (track_from 과 같은 식, 세로로).
    상자는 -90° 로 돌면 가운데 기준으로 「위 → 오른쪽」이 된다: 기준선(상자 위에서 반 행간 + 윗높이)이 원본 기준선 x 에 오게,
    가운데 정렬 줄(글자 폭 + 글자마다 자간 — Chrome 은 끝 글자 뒤에도 둔다)의 시작이 원본 첫 글자 원점 y 에 오게."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ch = next([c for c in sp["chars"]] for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]
              if l["dir"][1] < -0.5 and "".join(c["c"] for c in sp["chars"]) == s)
    bx_base = (ch[0]["origin"][0] - ox) * MM                                 # 기준선 x (돌린 글)
    y_first, y_last = (ch[0]["origin"][1] - oy) * MM, (ch[-1]["origin"][1] - oy) * MM
    asc, desc, adv = face(family, weight)
    em = size * MM
    track = round(((y_first - y_last) - chrome_extent(family, weight, size, s)) / (len(s) - 1) / em * 1000)
    run = chrome_extent(family, weight, size, s) + adv(s[-1]) * em + len(s) * track / 1000 * em
    lead = size * 1.45 * MM
    bh = round(lead + 0.4, 1)
    base_off = (lead - (asc + desc) * em) / 2 + asc * em - bh / 2       # 기준선 - 상자 가운데 (글줄은 상자 위 끝부터 — top_of 와 같은 식)
    cx, cy = bx_base - base_off, y_first - run / 2
    ink = [c for c in ch if c["c"].strip()]
    top = (ink[-1]["origin"][1] - oy) * MM - adv(s[-1]) * em
    ELEMS[pg].append({"id": id, "x": bx_base - 0.75 * em, "y": round(top, 2), "w": round(0.75 * em, 2), "h": round(y_first - top, 2),
                      "color": color, "see": color, "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - bw / 2, 2), round(cy - bh / 2, 2), bw, bh, s, size, color, font=family, weight=weight, track=track or None, align="center")
    return st + [F('#side input[data-a="rotate"]', -90, 600)]


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": 30})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 0.6pt = 0.21mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


CONTENT = {"지문번호": [], "지문": [], "문항번호": [], "발문": [], "선지": []}     # 끝에 넣을 원고 — 자리 이름 → 글(읽는 순서)
TEMP = ("Temporary passage text for styling. The real story arrives later from outside, and this paragraph only keeps "
        "the shape of the content so that the style can be set while it is still empty. ")


def temp_passage(n):
    """지문 자리의 임시 글 — 올 원고의 꼴(영어 문단)을 흉내 낸다. 길이는 원본과 비슷하게"""
    return (TEMP * (n // len(TEMP) + 1))[:n].rsplit(" ", 1)[0] + "."


TRACK = -40          # 지문 자간: 원본 글자 간격 - 서체 폭 (공백 제외 중앙값 — 16·17쪽 8.5pt 글자 1134쌍 모두 -40)


def passage(pg, pno, sky, label):
    """지문 — 하늘색 상자 + 글상자 하나(양끝맞춤 · 원본 행간 · 자간 -40), 자리 「지문」. 원고는 원본 줄을 이은 글(줄 나눔 없이)."""
    rows = [s for s in spans(pno) if s["size"] == 8.5]
    x, right = rows[0]["x"], max(r["x1"] for r in rows)
    lead = round((rows[1]["base"] - rows[0]["base"]) / MM)                   # 기준선 간격 → 행간 pt (16쪽 15 · 17쪽 13)
    txt = " ".join(r["t"] for r in rows)
    CONTENT["지문"].append(txt)
    st = [S(label, 1400)]
    st += B(pg, "sky", *sky, SKYBOX)
    ELEMS[pg].append({"id": "passage", "x": x, "y": rows[0]["y0"], "w": round(right - x, 2), "h": rows[-1]["y1"] - rows[0]["y0"],
                      "color": INK, "see": INK, "ctol": 40, "search": 1.0, "text": txt[:30], "size": 8.5,
                      "shape_iou": 0.80})          # 문단은 양끝맞춤에서 단어가 0.2mm 안팎 다르게 놓인다 — 겹침 기준을 낮춘다
    w = round(right - x + TRACK / 1000 * 8.5 * MM, 2)                       # Chrome 은 줄 끝 글자 뒤에도 자간을 둔다
    y = top_of(rows[0]["base"], 8.5, NOTO, 400, lead)
    st += text(round(x, 2), round(y, 2), w, round(len(rows) * lead * MM + 0.5, 1), temp_passage(len(txt)), 8.5, INK,
               label="지문 자리 — 임시 글 · 양끝맞춤 · 행간 %dpt" % lead, leading=lead, align="justify", font=NOTO, track=TRACK)
    st += slot("지문", label="자리 이름 「지문」")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    # 「양끝 줄 낱말 최소」(word_min)는 쓰지 않는다 — 줄 나눔(Shift+Enter)으로 꺾인 줄에만 먹는 값인데 원고는 줄 나눔 없는 문단이라
    # 줄 끝·낱말 간격은 단락 컴포저(인디자인 양끝 정렬 규칙: 낱말 100~133% 먼저, 남는 폭만 자간)가 정한다.
    return st


def passage_no(pg, pno):
    s = next(s for s in spans(pno) if s["size"] == 12.0)
    _, _, adv = face(YD, 400)
    st = T(pg, "no", s["x"], s["base"], s["t"], 12, s["color"], YD, 400, (s["x"], s["base"] - 3.2, s["x1"] - s["x"], 3.6),
           search=0.6, label="지문 번호 자리", temp="00")
    CONTENT["지문번호"].append(s["t"] + " ")      # 원본 원고 그대로 「01 」 — 끝 공백 뒤에서 영도체 「1」 이 밑줄 긴 꼴(문맥 대체)로 바뀐다
    return st + slot("지문번호")


def opt_track(pno):
    """선지 자간 — 원본 8pt 글자 사이(공백 제외)의 「원점 간격 - 서체 폭」 중앙값 (16·17쪽 모두 -30).
    줄마다 track_from 의 중앙값은 17쪽 문항 3 에서 -28 이 나와 줄이 0.4mm 길어졌다 — 한 스타일이니 쪽 전체 글자로."""
    p = REFDOC[pno - 1]
    _, _, adv = face(NOTO, 400)
    d = [((b2["origin"][0] - a["origin"][0]) - adv(a["c"]) * 8) / 8 * 1000
         for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if round(sp["size"], 1) == 8.0
         for a, b2 in zip(sp["chars"], sp["chars"][1:]) if a["c"] != " " and b2["c"] != " "]
    return round(statistics.median(d))


OPT_TEMP = "① Temporary choice text one\n② Temporary choice text two\n③ Temporary choice text three\n④ Temporary choice text four"


def questions(pg, pno):
    """문항 셋 — 번호(엘리스 굵게 10pt 보라, 「01 |」) · 발문(엘리스 중간 7.5pt) · 선지 넷(본고딕 8pt, 한 글상자에 문단 넷)"""
    sp = spans(pno)
    nums = [s for s in sp if s["size"] == 10.0]
    st = []
    for k, n in enumerate(nums):
        q = next(s for s in sp if s["size"] == 7.5 and abs(s["base"] - n["base"]) < 1.5)
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 1e9
        opts = [s for s in sp if s["size"] == 8.0 and n["base"] < s["base"] < nxt]
        no = n["t"].replace("\t", "").strip()                                # 「01 |」 — 번호 뒤 막대까지 한 조각(번호 폭에 따라 막대가 밀린다)
        st += [S(f"문항 {no[:2]} — 번호 · 발문 · 선지", 1300)]
        st += T(pg, f"q{k + 1}-no", n["x"], n["base"], no, 10, PURPLE, EL, 700, (n["x"], n["y0"], n["x1"] - n["x"], n["y1"] - n["y0"]),
                search=0.8, pad=0.8, temp="00 |", label="문항 번호 자리")
        st += slot("문항번호")
        CONTENT["문항번호"].append(no)
        st += T(pg, f"q{k + 1}-q", q["x"], q["base"], q["t"], 7.5, INK, EL, 500, (q["x"], q["y0"], q["x1"] - q["x"], q["y1"] - q["y0"]),
                search=0.8, pad=0.8, w=160, temp="What is the question about the passage above?", label="발문 자리")
        st += slot("발문")
        CONTENT["발문"].append(q["t"])
        lead = round((opts[1]["base"] - opts[0]["base"]) / MM)              # 선지 기준선 간격 → 행간 pt (15)
        tr = opt_track(pno)
        # 색 허용 30 — 예전엔 비교 도구가 결과 PDF 를 원본 화소 크기로 늘려 ①~④ 의 가는 원 테두리가 흐려져 80 을 썼다.
        # 비교가 늘리지 않게 바뀐 뒤(pagecmp.measure) 다른 글과 같은 30 으로 잰다.
        for j, o in enumerate(opts):
            ELEMS[pg].append({"id": f"q{k + 1}-o{j + 1}", "x": o["x"], "y": round(o["base"] - 0.8 * 8 * MM, 2), "w": round(o["x1"] - o["x"], 2),
                              "h": round(8 * MM * 1.05, 2), "color": INK, "see": INK, "ctol": 30, "search": 1.0, "pad": 0.6,
                              "text": o["t"], "size": 8})
        st += text(round(opts[0]["x"], 2), round(top_of(opts[0]["base"], 8, NOTO, 400, lead), 2), 150, round(len(opts) * lead * MM + 0.5, 1),
                   OPT_TEMP, 8, INK, label=f"선지 자리 — 문단 넷 · 행간 {lead}pt · 자간 {tr}", leading=lead, font=NOTO, track=tr or None)
        st += slot("선지")
        CONTENT["선지"].append("\n".join(o["t"] for o in opts))
    return st


def header_left(pg, code, code_w, title, title_x, title_w):
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, "#77a1c4")
    st += T(pg, "t-step", 20.0, 8.93, "STEP 01", 8, "#77a1c4", NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 01 · FRAME")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", 32.35, 8.93, "FRAME", 8, "#b4aa9a", NOTO, 700, (32.35, 3.84, 9.62, 8.05))
    st += T(pg, "t-code", 20.0, 19.47, code, 25, "#77a1c4", MAMA, 400, (20.0, 12.18, code_w, 9.78), label="제목 — 코드 · 이름")
    st += T(pg, "t-title", title_x, 17.58, title, 13, INK, GM, 500, (title_x, 13.70, title_w, 5.44))
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, fill="#77a1c4")
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    for k, (nx, nw, col) in enumerate(((57.79, 0.83, "#ffffff"), (68.58, 1.25, "#b4aa9a"), (79.57, 1.25, "#b4aa9a"))):
        st += T(pg, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), search=0.6, pad=0.3)   # 잴 창은 원 안만(크림 띠·테두리가 섞이지 않게)
    return st


# ── 16쪽 (왼쪽 면) ──────────────────────────────────────────
S16 = spans(16)
code16 = next(s for s in S16 if s["size"] == 25.0)
title16 = next(s for s in S16 if s["size"] == 13.0)
st = open_doc("스텝바이스텝 워크북 B2 (A4)")
st += expect_pages(1)
st += [S("① 16쪽 — B2 내용 종합", 1500)]
st += header_left(1, code16["t"], round(code16["x1"] - code16["x"], 2), title16["t"], round(title16["x"], 2), round(title16["x1"] - title16["x"], 2))
st += passage_no(1, 16)
st += passage(1, 16, (28.33, 35.91, 151.33, 46.04), "지문 01 — 하늘색 상자 · 지문 자리")
st += questions(1, 16)
st += [S("꼬리 — 쪽번호", 1200)]
f16 = [s for s in S16 if s["size"] == 6.0 and s["base"] > 280]
for s in f16:
    st += T(1, "f-no" if s["t"].isdigit() else "f-t", s["x"], s["base"], s["t"], 6, s["color"], EL, 700, (s["x"], 283.62, s["x1"] - s["x"], 2.62), search=0.6)
st += done("16쪽", "p1.png")

# ── 17쪽 (오른쪽 면) ────────────────────────────────────────
S17 = spans(17)
code17 = next(s for s in S17 if s["size"] == 36.0)
st += add_page("② 17쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(2, "tag-t", 187.05, 21.84, "STEP BY STEP", 6, "#ffffff", MS, 700, (187.05, 19.56, 15.43, 2.84), search=0.6,
        pad=0.3)       # 잴 창은 꼬리표 안만 — 기본 1.5mm 면 크림 띠(흰색 허용 30 안)·선 아래 흰 지면까지 흰 글로 잰다
st += T(2, "t-code", code17["x"], code17["base"], code17["t"], 36, "#77a1c4", MS, 500,
        (code17["x"], 2.62, round(code17["x1"] - code17["x"], 2), 16.71), label="큰 코드 B2")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
for k, (s, col) in enumerate((("STEP 01", "#ffffff"), ("02", "#cba56f"), ("03", "#bc736c"))):
    st += R(2, f"tab{k + 1}-t", 17, s, col)                              # 원본은 아래에서 위로 읽는 글 · 돌려도 가운데가 남게 가운데 정렬
st += passage_no(2, 17)
st += passage(2, 17, (30.33, 35.91, 151.33, 45.69), "지문 02 — 하늘색 상자 · 지문 자리")
st += questions(2, 17)
st += [S("꼬리 — 쪽번호", 1200)]
f17 = [s for s in S17 if s["size"] == 6.0 and s["base"] > 280]
for s in sorted(f17, key=lambda s: s["x"]):
    st += T(2, "f-no" if s["t"].isdigit() else "f-t", s["x"], s["base"], s["t"], 6, s["color"], EL, 700, (s["x"], 283.62, s["x1"] - s["x"], 2.62), search=0.6)
st += done("17쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("05 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
