"""단위 14a S실전문제 — 원본 d1 reference.pdf 48~56쪽(9면)을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
(단위 14 는 27면이라 세 작업자가 48~56 · 57~65 · 66~74 로 나눴다 — 자리 이름·원고 약속은 14b 와 같게.)

면 구조 (원본 PDF 에서 읽은 것):
  짝수 쪽(왼쪽 면) 머리 — 크림 띠 · 선 · 벽돌색 막대 · STEP 03 TEST · 「S 실전 문제」 · 단계 점(3 이 찬 원)
  홀수 쪽(오른쪽 면) 머리 — 크림 띠 · 선 · 꼬리표 STEP BY STEP · 큰 「S」 · 오른쪽 탭 셋(01 · 02 · STEP 03 찬 벽돌색)
  본문 — 두 단(82mm). 문항마다 번호(엘리스 굵게 12pt 파랑) · 발문(본고딕 8pt, 둘째 줄은 단 왼쪽으로) ·
         [보기 상자(연두빛 바탕)] · 지문(본고딕 8pt 양끝맞춤 행간 14pt) · 선지/진술(내어쓰기 3.5mm 행간 12pt) ·
         [조건 상자(하늘색 바탕 + 테두리) + 「주제문: ___.」]
자리 이름 — 블록 지도 B6 문항 기준: 문항번호 · 발문 · 보기 · 지문 · 선지 · 조건 · 답칸.
  밑줄 친 곳은 원고에 약속 괄호로 — `{…}` = Medium + 밑줄(지문의 ①{found} · 발문의 적절하지 {않은}),
  `_{…}` = 밑줄만(발문 「밑줄 친 _{a photo played …}가」). GREP 가 괄호는 감추고 서식만 입힌다.
  (A)(B)(C) 순서 문항의 문단 머리 「(A)」 는 GREP 로 Medium. 「[조건]」 머리는 상자마다 같은 고정 글.

단·쪽을 넘어 이어지는 글(48쪽 3번 지문 · 50쪽 12번 · 51쪽 17번 · 54쪽 29·31번 · 55쪽 33번 · 56쪽 38번)은 글 잇기(인디자인 텍스트 스레드)로
잇는다 — 앞 상자(이야기 첫 상자)가 글·원고 자리를 갖고 원본 줄 수만큼만 담으며, 넘친 줄이 다음 단·쪽 상자로 흐른다.
원고도 문항마다 한 글(나누지 않는다). 56쪽 38번은 57쪽(다음 단위)으로 이어져 원고는 57쪽 몫까지 넣고 56쪽 상자만 그린다.

종류마다 쪽의 첫 글상자만 스타일을 매기고 나머지는 「⧉ 복제」 후 자리·높이만 친다(단위 07 과 같이).
값은 모두 원본 PDF 에서 — 글 조각(서체·크기·색·기준선·글자 자리)·도형 좌표·밑줄 선. 측정 보정 없음.
글상자 위 끝 = top_of(기준선 공식), 자간 = 원본 글자 간격 - 서체 폭의 중앙값(낱말 안 글자 쌍).
"""
import json, os, re, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)                                                # mkpage.chrome_extent 가 core.units.render 를 쓴다
from mkpage import *                                                    # noqa
from mkpage import _color
import mkpage
import pagecmp
import pymupdf
from core.units.render import text_h                                    # 서버가 글 높이를 어림하는 식 — 자리가 자라 아래를 밀지 않게(읽기만)

# 임시로 끌어 그리는 자리 — 꼬리 아래 빈 띠(모든 쪽에서 비어 있다). 본문이 꽉 찬 면이라 기본 자리(120, 250)는 다른 글상자 위라
# 두 번 누르기가 아래 글상자로 가서 엉뚱한 글상자를 고쳤다(1판 54쪽). 그리는 높이도 이 띠 안으로(9mm) — 실제 높이는 칸에 친다.
mkpage.SPOT["mm"][:] = [50, 287.5]

STATE = json.load(open(os.path.join(HERE, "상태.json")))
REF = os.path.join(REPO, STATE["ref"])
REFDOC = pymupdf.open(REF)
PAGES = list(range(48, 57))                                              # 이 단위가 만드는 원본 쪽 (상태.json 은 고칠 때 몇 쪽만 맞댈 수 있다 — ONLY)
ELEMS = {k + 1: [] for k in range(len(PAGES))}
MM = 25.4 / 72
NOTO, MS, EL, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
INK, BRICK, TAB, NUMC, CREAM = "#231f20", "#bc736c", "#b4aa9a", "#00559f", "#f9f7ed"
CONDF, CONDS, BOGIF = "#dbecf2", "#6ab3c7", "#f9fcf3"                 # 조건 상자 바탕·테두리, 보기 상자 바탕
COL_W = 82.0                                                            # 단 폭 (조건·보기 상자 폭과 같다)
BOX_IN = 3.0                                                            # 상자 안 글 들여 — 원본 상자 x + 3.0
CIRC = "①②③④⑤"
RA = {}


def ref_arr(pg):
    if pg not in RA:
        RA[pg] = pagecmp.page_array(REF, PAGES[pg - 1])
    return RA[pg]


def ink(pg, color, x, y, w, h, tol=40):
    """원본 쪽에서 그 색 잉크 상자(mm) — 잴 요소의 자리"""
    return pagecmp.color_box(ref_arr(pg), color, x, y, w, h, pad=0, tol=tol)


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3])


def rp(pg):
    return REFDOC[PAGES[pg - 1] - 1]


# ── 원본 쪽 읽기 (머리·꼬리) ─────────────────────────────────
def spans(pg):
    """원본 쪽의 글 조각 — 빈칸만인 조각은 뺀다. x = 첫 글자 원점, x1 = 끝 글자 끝, base = 기준선 (지면 mm)"""
    p = rp(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ink_ = [c for c in s["chars"] if c["c"].strip()]
                if not ink_:
                    continue
                out.append({"t": "".join(c["c"] for c in s["chars"]), "size": round(s["size"], 1), "font": s["font"], "dir": l["dir"],
                            "color": "#%06x" % s["color"], "x": (ink_[0]["origin"][0] - ox) * MM, "x1": (ink_[-1]["bbox"][2] - ox) * MM,
                            "base": (s["origin"][1] - oy) * MM, "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM})
    return out


def draws(pg):
    p = rp(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for g in p.get_drawings():
        r = g["rect"]
        out.append(((r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM, g))
    return out


def fills(pg, color):
    return [d for d in draws(pg) if d[4].get("fill") and hexc(d[4]["fill"]) == color]


def strokes(pg, color):
    return [d for d in draws(pg) if d[4].get("color") and hexc(d[4]["color"]) == color]


def win(base, size):
    """글 잴 창 — 기준선 둘레(윗높이 0.95em · 아랫높이 0.3em)"""
    return base - 0.95 * size * MM, 1.25 * size * MM


def T(pg, id, x, base, s, size, color, family, weight, x1, label=None, w=None, temp=None, leading=None, search=0.8, ctol=30,
      pad=0.5, track=None, measure=True, align=None):
    """원본 글 하나(고정 글). x = 첫 글자 자리(원점), base = 기준선, x1 = 끝 글자 오른쪽(원본). 자간은 원본 글자 자리에서."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    y0, h0 = win(base, size)
    if track is None:
        track = track_from(rp(pg), (x, y0, x1 - x, h0), s, family, weight, size)
        track = track if abs(track) > 8 else 0
    if measure:
        ELEMS[pg].append({"id": id, "x": round(x, 2), "y": round(y0, 2), "w": round(x1 - x, 2), "h": round(h0, 2), "color": color, "see": color,
                          "ctol": ctol, "pad": pad, "search": search, "text": s, "size": size})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return tx(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


def R(pg, id, s, color, size=6.5, family=MS, weight=700, bw=14):
    """돌린 글(아래에서 위로 읽는 옆 탭) — 단위 05 의 R 과 같은 계산(원본 글자 원점에서 바로). 원본은 탭 글이 두 벌 겹쳐 있다(첫 벌만)."""
    p = rp(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ch = next([c for c in sp["chars"]] for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]
              if l["dir"][1] < -0.5 and "".join(c["c"] for c in sp["chars"]) == s)
    bx_base = (ch[0]["origin"][0] - ox) * MM
    y_first = (ch[0]["origin"][1] - oy) * MM
    y_last = (ch[-1]["origin"][1] - oy) * MM
    asc, desc, adv = face(family, weight)
    em = size * MM
    track = round(((y_first - y_last) - chrome_extent(family, weight, size, s)) / (len(s) - 1) / em * 1000) if len(s) > 1 else 0
    run = chrome_extent(family, weight, size, s) + adv(s[-1]) * em + len(s) * track / 1000 * em
    lead = size * 1.45 * MM
    bh = round(lead + 0.4, 1)
    base_off = (lead - (asc + desc) * em) / 2 + asc * em - bh / 2
    cx, cy = bx_base - base_off, y_first - run / 2
    ink_ = [c for c in ch if c["c"].strip()]
    top = (ink_[-1]["origin"][1] - oy) * MM - adv(s[-1]) * em
    ELEMS[pg].append({"id": id, "x": round(bx_base - 0.75 * em, 2), "y": round(top, 2), "w": round(0.75 * em, 2), "h": round(y_first - top, 2),
                      "color": color, "see": color, "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - bw / 2, 2), round(cy - bh / 2, 2), bw, bh, s, size, color, font=family, weight=weight, track=track or None, align="center")
    return st + [F('#side input[data-a="rotate"]', -90, 600)]


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30):
    if measure:
        ELEMS[pg].append({"id": id, "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "color": fill, "see": fill,
                          "pad": pad, "ctol": ctol})
    return box(round(x, 3), round(y, 3), round(w, 3), round(h, 3), fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": round(x, 2), "y": round(y, 2), "w": round(d, 2), "h": round(d, 2), "color": fill or stroke,
                      "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(round(x, 3), round(y, 3), round(d, 3), fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color=TAB, sw=0.6 * MM, measure=True):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, y - sw / 2, w, sw, color, pad=0.15, measure=measure)


def frame(pg, id, x, y, w, h, stroke, sw, fill=None, label=None):
    """테두리 면 — 원본 사각형 경로(x, y, w, h mm) · 획 색 · 획 두께 pt(가운데 정렬 = 인디자인 기본)"""
    hw = sw * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2), "h": round(h + 2 * hw, 2),
                      "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30})
    st = box(round(x, 3), round(y, 3), round(w, 3), round(h, 3), fill, label=label)
    st += _color("stroke.color", stroke)
    st.append(F('#side input[data-a="stroke.w"]', sw))
    return st


def box(x, y, w, h, fill=None, label=None, radius=0, alpha=None):
    """면 — mkpage.box 와 같고 끌어 그리는 크기만 빈 띠 안으로(높이 8mm)"""
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "rect", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 8)]}}, "wait": 750}]
    st += [F('#side input[data-a="w"]', w), F('#side input[data-a="h"]', h), F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y),
           F('#side input[data-a="radius"]', radius)]
    if fill:
        st += _color("fill", fill)
    return st + opacity(alpha)


def tx(x, y, w, h, s, size, color, **kw):
    """글상자 — mkpage.text 로 그리되 끌어 그리는 높이는 빈 띠 안(9mm), 실제 높이는 뒤에 친다"""
    st = text(x, y, w, min(h, 9), s, size, color, **kw)
    return st + ([F('#side input[data-a="h"]', h)] if h > 9 else [])


def dup(x, y, h=None):
    """고른 개체 「⧉ 복제」 → 자리(·높이)만 새로"""
    st = [{"click": "#side #s-dup", "wait": 700}]
    if h is not None:
        st.append(F('#side input[data-a="h"]', h))
    return st + [F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]


# ── 머리 · 꼬리 ─────────────────────────────────────────────
def header_left(pg):
    sp = spans(pg)
    st = [S("머리 — 크림 띠 · 선 · 벽돌색 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, CREAM)
    ln = [r for r in strokes(pg, TAB) if r[2] > 100][0]
    st += rule(pg, "rule", -3, ln[1], 216, sw=ln[4]["width"] * MM)
    bar = [r for r in fills(pg, BRICK) if r[3] > 20][0]
    st += B(pg, "bar", bar[0], -3, bar[2], bar[1] + bar[3] + 3, BRICK)
    stp = [s for s in sp if s["t"] == "STEP" and s["size"] == 8][0]
    num = [s for s in sp if s["t"].strip() == "03" and s["size"] == 8][0]
    st += T(pg, "t-step", stp["x"], stp["base"], "STEP 03", 8, BRICK, NOTO, 400, num["x1"], label="STEP 03 · TEST")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    te = [s for s in sp if s["t"] == "TEST"][0]
    st += T(pg, "t-test", te["x"], te["base"], "TEST", 8, TAB, NOTO, 700, te["x1"])
    cd = [s for s in sp if s["font"] == "TTMamablockB"][0]
    st += T(pg, "t-code", cd["x"], cd["base"], cd["t"].strip(), 25, BRICK, MAMA, 400, cd["x1"], label="제목 — 코드 · 이름")
    tt = [s for s in sp if s["font"] == "GmarketSansMedium"][0]
    st += T(pg, "t-title", tt["x"], tt["base"], tt["t"].strip(), 13, INK, GM, 500, tt["x1"])
    st += [S("단계 점 셋 — 원 · 선 · 숫자 (지금 단계 3)", 1400)]
    circ = sorted([r for r in strokes(pg, TAB) if len(r[4]["items"]) == 4] + [r for r in fills(pg, BRICK) if len(r[4]["items"]) == 4],
                  key=lambda r: r[0])
    lines = sorted([r for r in strokes(pg, TAB) if 3 < r[2] < 6 and r[3] < 0.5], key=lambda r: r[0])
    for k, r in enumerate(circ):
        g = r[4]
        if g.get("fill"):
            st += C(pg, f"d{k + 1}", r[0], r[1], r[2], fill=BRICK)
        else:
            st += C(pg, f"d{k + 1}", r[0], r[1], r[2], stroke=TAB, sw=round(g["width"], 3))
        if k < len(lines):
            l = lines[k]
            st += rule(pg, f"dl{k + 1}", l[0], l[1], l[2], sw=l[4]["width"] * MM)
    for k, d in enumerate("123"):
        s = [s for s in sp if s["t"] == d and s["font"] == "Montserrat-Bold"][0]
        st += T(pg, f"n{k + 1}", s["x"], s["base"], d, 6, s["color"], MS, 700, s["x1"], search=0.1, measure=False)
        sm = 6 * MM                                                              # 잴 창 = 숫자 높이만 — 원 테두리가 섞이지 않게
        ELEMS[pg].append({"id": f"n{k + 1}", "x": round(s["x"], 2), "y": round(s["base"] - 0.8 * sm, 2), "w": round(s["x1"] - s["x"], 2),
                          "h": round(0.82 * sm, 2), "color": s["color"], "see": s["color"], "ctol": 30, "pad": 0.1, "search": 0.1, "text": d, "size": 6})
    return st


def header_right(pg):
    sp = spans(pg)
    st = [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
    st += B(pg, "band", 0, -3, 213, 26.5, CREAM)
    ln = [r for r in strokes(pg, TAB) if r[2] > 100][0]
    st += rule(pg, "rule", -3, ln[1], 216, sw=ln[4]["width"] * MM)
    tag = fills(pg, "#bdafa2")[0]
    p = rp(pg)
    xs_ = [(it[1].x - p.trimbox.x0) * MM for it in tag[4]["items"]]
    d = f"M{(xs_[3] - tag[0]) / tag[2]:.4f} 0 L1 0 L1 1 L0 1 Z"                     # 원본 꼭짓점: 왼쪽 위만 안으로 들어간 사다리꼴
    ELEMS[pg].append({"id": "tag", "x": round(tag[0], 2), "y": round(tag[1], 2), "w": round(210 - tag[0], 2), "h": round(tag[3], 3), "color": "#bdafa2"})
    st += shape(round(tag[0], 2), round(tag[1], 2), round(tag[2], 2), round(tag[3], 3), "#bdafa2", d=d, label="꼬리표 — 도형, 원본 꼭짓점 그대로")
    tg = [s for s in sp if s["t"] == "STEP BY STEP" and s["font"] == "Montserrat-Bold"][0]
    st += T(pg, "tag-t", tg["x"], tg["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, tg["x1"], search=0.2, pad=0.2)   # 흰 글 — 잴 창을 꼬리표 안으로
    cd = [s for s in sp if s["font"] == "Montserrat-Medium"][0]
    st += T(pg, "t-code", cd["x"], cd["base"], cd["t"].strip(), 36, BRICK, MS, 500, cd["x1"], label="큰 코드 S")
    st += [S("오른쪽 탭 셋 — 면 · 돌린 글 (지금 단계 STEP 03)", 1500)]
    tabs = sorted([r for r in draws(pg) if r[0] > 200 and r[4].get("fill") and r[2] < 15 and r[3] > 20], key=lambda r: r[1])
    for k, r in enumerate(tabs):
        st += B(pg, f"tab{k + 1}", r[0], r[1], r[2], r[3], hexc(r[4]["fill"]), ctol=8 if k < 2 else 30)
    seen = []
    for s in sorted([s for s in sp if s["size"] == 6.5 and s["dir"][1] < -0.5], key=lambda s: -s["base"]):
        if s["t"] in seen:
            continue
        seen.append(s["t"])
    for s in sorted(seen, key=lambda t: [x for x in sp if x["t"] == t][0]["base"]):
        c = [x for x in sp if x["t"] == s][0]["color"]
        st += R(pg, f"tab-{s}", s, c)
    return st


def footer(pg):
    sp = spans(pg)
    st = [S("꼬리 — 쪽번호", 1200)]
    for s in sorted([s for s in sp if s["font"] == "EliceDXNeolliOTF-Bd" and s["size"] == 6], key=lambda s: s["x"]):
        st += T(pg, "f-" + ("no" if s["t"].strip().isdigit() else "t"), s["x"], s["base"], s["t"].strip(), 6, s["color"], EL, 700, s["x1"], search=0.6)
    return st


# ── 원본 쪽 읽기 (본문) ─────────────────────────────────────
def cols_of(pno):
    """단 왼쪽 끝 — 홀수 쪽(오른쪽 면) 21.5 / 108, 짝수 쪽 20 / 106"""
    return (21.5, 108.0) if pno % 2 else (20.0, 106.0)


def read_page(pno):
    """원본 쪽 본문 → 단마다 줄 목록. 줄 = {base, x0, x1, chars[{c, x, x1, wt, size, ul}], num, size, text}.
    번호(12pt)와 발문(8pt)은 기준선이 0.55mm 달라 한 줄로 묶는다. 밑줄 = 원본 선(가운데가 기준선 아래 0.71mm)."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    uls, rects = [], []
    for g in p.get_drawings():
        r = g["rect"]
        x, y, w, h = (r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM
        if y < 25 or x > 200:
            continue
        if g["type"] == "s" and h < 0.01 and g.get("color") and hexc(g["color"]) == INK:
            uls.append((x, x + w, y, g["width"]))
        elif g.get("fill") and hexc(g["fill"]) in (CONDF, BOGIF):
            rects.append(("cond" if hexc(g["fill"]) == CONDF else "bogi", x, y, w, h,
                          hexc(g["color"]) if g.get("color") else None, g.get("width")))
    raw = []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for l in b.get("lines", []):
            if l["dir"][0] < 0.5:
                continue
            for s in l["spans"]:
                base = (s["origin"][1] - oy) * MM
                if base < 25 or base > 280 or not s["chars"]:
                    continue
                wt = 500 if "Medium" in s["font"] else 700 if ("Bd" in s["font"] or "Bold" in s["font"]) else 400
                raw.append({"x": (s["chars"][0]["origin"][0] - ox) * MM, "base": base, "chars": [
                    {"c": c["c"], "x": (c["origin"][0] - ox) * MM, "x1": (c["bbox"][2] - ox) * MM, "base": base,
                     "wt": wt, "size": round(s["size"], 1)} for c in s["chars"]]})
    L, Rr = cols_of(pno)
    cols = {0: [], 1: []}
    for sp in raw:
        cols[0 if sp["x"] < Rr - 2 else 1].append(sp)
    out = {}
    for ci, sps in cols.items():
        sps.sort(key=lambda sp: (round(sp["base"], 1), sp["x"]))
        lines = []
        for sp in sps:
            if lines and abs(sp["base"] - lines[-1]["ref"]) < 1.0:
                lines[-1]["spans"].append(sp)
            else:
                lines.append({"ref": sp["base"], "spans": [sp]})
        res = []
        for ln in lines:
            ch = [c for sp in sorted(ln["spans"], key=lambda sp: sp["x"]) for c in sp["chars"]]
            num = [c for c in ch if c["size"] == 12.0]
            body = [c for c in ch if c["size"] != 12.0]
            base = statistics.median(c["base"] for c in body if c["size"] == 8.0) if any(c["size"] == 8.0 for c in body) else \
                (body[0]["base"] if body else num[0]["base"])
            for c in body:
                c["ul"] = any(abs(u[2] - (c["base"] + 0.71)) < 0.3 and u[0] <= (c["x"] + c["x1"]) / 2 <= u[1] for u in uls)
            ink_ = [c for c in body if c["c"].strip()]
            res.append({"base": base, "num": num, "chars": body, "x0": ink_[0]["x"] if ink_ else None,
                        "x1": ink_[-1]["x1"] if ink_ else None, "text": "".join(c["c"] for c in body)})
        out[ci] = [r for r in res if r["x0"] is not None or r["num"]]
    return out, rects, uls


def in_rect(rects, x, base):
    for r in rects:
        if r[1] - 0.5 <= x <= r[1] + r[3] + 0.5 and r[2] <= base <= r[2] + r[4]:
            return r
    return None


def marked(chars):
    """줄 글자 → 원고 글. 밑줄 + Medium = {…}, 밑줄만 = _{…}"""
    out, k = "", 0
    while k < len(chars):
        c = chars[k]
        if c.get("ul") and c["c"].strip():
            j = k
            while j < len(chars) and chars[j].get("ul") and chars[j]["wt"] == c["wt"]:
                j += 1
            while j > k and not chars[j - 1]["c"].strip():                   # 밑줄 끝 공백은 괄호 밖으로
                j -= 1
            out += ("{" if c["wt"] == 500 else "_{") + "".join(x["c"] for x in chars[k:j]) + "}"
            k = j
        else:
            out += c["c"]
            k += 1
    return out


OPTL = ("opts", "stmt")                                                       # 선지 · 진술 — 같은 모양(내어쓰기·단락 뒤 간격), 균등 배치만 다르다


def groups(pno):
    """단마다 요소 묶음 — [{kind, lines, left, rect?}] 읽는 순서. kind: num · prompt · bogi · passage · opts · condlabel · cond · answer"""
    cols, rects, uls = read_page(pno)
    L, Rr = cols_of(pno)
    res = {}
    for ci, lines in cols.items():
        left = (L, Rr)[ci]
        gs, cur, prev = [], None, None
        for ln in lines:
            gap = ln["base"] - prev["base"] if prev else 99
            r = in_rect(rects, ln["x0"] if ln["x0"] is not None else left, ln["base"])
            t = ln["text"].strip()
            dx = (ln["x0"] - left) if ln["x0"] is not None else 0
            if ln["num"]:
                gs.append({"kind": "num", "lines": [ln], "left": left})
                cur = {"kind": "prompt", "lines": [ln], "left": left}
                gs.append(cur)
            elif r and r[0] == "cond":
                if t.startswith("[조건]"):
                    gs.append({"kind": "condlabel", "lines": [ln], "left": left, "rect": r})
                    cur = {"kind": "cond", "lines": [], "left": left, "rect": r}
                    gs.append(cur)
                else:
                    cur["lines"].append(ln)
            elif r and r[0] == "bogi":
                if not (cur and cur["kind"] == "bogi" and cur["rect"] is r):
                    cur = {"kind": "bogi", "lines": [], "left": left, "rect": r}
                    gs.append(cur)
                cur["lines"].append(ln)
            elif t.startswith("주제문"):
                cur = {"kind": "answer", "lines": [ln], "left": left}
                gs.append(cur)
            elif cur and cur["kind"] == "prompt" and len(cur["lines"]) < 2 and 5.05 < gap < 5.6:            # 발문 둘째 줄 (기준선 간격 5.15 — 지문 줄은 4.94)
                cur["lines"].append(ln)
            elif dx < 0.3 and (t[:1] in CIRC or re.match(r"\d\)\s", t)) and not (cur and cur["kind"] == "passage" and gap < 6):
                kd = "opts" if t[:1] in CIRC else "stmt"                    # 진술 「1) … (T/F)」 은 선지와 다른 단락 스타일(원본: 진술 줄은 자간을 3‰ 줄이고 선지는 1‰ 넘게 안 줄인다)
                if not (cur and cur["kind"] == kd and gap < 7):
                    cur = {"kind": kd, "lines": [], "left": left}
                    gs.append(cur)
                cur["lines"].append(ln)
                ln["para"] = True
            elif 2.5 < dx < 4.5 and cur and cur["kind"] in OPTL:
                cur["lines"].append(ln)
            else:
                if not (cur and cur["kind"] == "passage" and gap < 6):
                    cur = {"kind": "passage", "lines": [], "left": left}
                    gs.append(cur)
                cur["lines"].append(ln)
            prev = ln
        res[ci] = [g for g in gs if g["lines"]]
        for g in res[ci]:
            for ln in g["lines"]:
                ln["right"] = right_of(g)                                  # 줄마다 단 오른쪽 — 잇기로 단을 넘는 글도 문단 끝을 바르게 센다
    return res, rects, uls


def right_of(g):
    return g["left"] + (COL_W - 2 * BOX_IN if g["kind"] in ("bogi", "cond") else COL_W)


def gtext(g):
    """묶음 → 원고 글. 줄은 낱말 사이 하나로 잇고, 문단(선지 하나 · 짧게 끝난 줄 뒤)은 줄바꿈."""
    ls = g["lines"]
    right = right_of(g)
    out = ""
    for k, ln in enumerate(ls):
        chars = ln["chars"]
        if g["kind"] == "prompt":
            chars = [c for c in chars if c["c"] != "\t"]
        t = marked(chars).strip()
        if k == 0:
            out = t
            continue
        brk = ln.get("para") if g["kind"] in OPTL else ls[k - 1]["x1"] < ls[k - 1].get("right", right) - 3
        if brk:
            out += "\n" + t
            continue
        sep = " " if ls[k - 1]["text"].endswith(" ") else ""                 # 한글은 낱말 중간에서도 꺾인다(「의 / 미하는」) — 줄 끝 공백이 없으면 붙인다
        m = re.match(r"(_?\{)", t)
        if m and out.endswith("}") and re.search(r"(?<![_{])" if m.group(1) == "{" else r"_\{[^{}]*\}$", out):
            out = out[:-1] + sep + t[len(m.group(1)):]                        # 줄을 넘는 밑줄은 한 괄호로
        else:
            out += sep + t
    return out


def gaps_track(groups_, size=8.0, weights=(400,), hangul=None, short=False):
    """글자 간격 - 서체 폭 (‰ em) — 같은 줄 안 이웃 글자(공백 끼지 않은) 중앙값. hangul: True = 한글끼리만, False = 한글 아닌 것만.
    short: 양끝맞춤으로 늘거나 준 줄은 빼고 짧게 끝난 줄(문단 끝 줄)만 — 스타일 자간"""
    _, _, adv = face(NOTO, 400)
    d = []
    for g in groups_:
        for ln in g["lines"]:
            if short and ln["x1"] >= right_of(g) - 3:
                continue
            ch = [c for c in ln["chars"] if c["size"] == size and c["wt"] in weights]
            for a, b in zip(ch, ch[1:]):
                if a["c"] in " \t" or b["c"] in " \t" or not (0 < b["x"] - a["x"] < 3):
                    continue
                if hangul is not None and (("가" <= a["c"] <= "힣") != hangul):
                    continue
                d.append(((b["x"] - a["x"]) - adv(a["c"]) * size * MM) / (size * MM) * 1000)
    return round(statistics.median(d)) if d else 0


def lead_of(gs, default):
    """행간 pt — 같은 문단 안 기준선 간격의 가장 흔한 값"""
    d = [round((b["base"] - a["base"]) / MM, 1) for g in gs for a, b in zip(g["lines"], g["lines"][1:]) if not b.get("para")]
    return statistics.mode(d) if d else default


if os.environ.get("DUMP"):                                                   # 묶음 확인용 — DUMP=1 python3 make.py
    for _pno in PAGES:
        _gs, _rects, _ = groups(_pno)
        print("=== 쪽", _pno)
        for _ci in (0, 1):
            for _g in _gs[_ci]:
                _ls = _g["lines"]
                print(f"  단{_ci} {_g['kind']:9s} b {_ls[0]['base']:6.2f}~{_ls[-1]['base']:6.2f} n{len(_ls):2d} | {gtext(_g)[:110]!r}")
    sys.exit()

# ── 문서 전체에서 스타일 값 읽기 (종류마다 한 스타일) ──────────
ALL = {}
for _pg in range(1, len(PAGES) + 1):
    _gs, _, _ = groups(PAGES[_pg - 1])
    for _ci in (0, 1):
        for _g in _gs[_ci]:
            ALL.setdefault(_g["kind"], []).append(_g)
def chrome_track(kind, n=8):
    """스타일 자간 — 짧게 끝난 줄(양끝맞춤으로 안 늘어난 줄)마다 원본 글자 자리 - 크롬 글자 자리(커닝 포함, track_from)의 중앙값.
    서체 폭만으로 재면(gaps_track) 커닝 쌍이 섞여 -3 쯤 더 좁게 나온다."""
    v = []
    for pg, pno in enumerate(PAGES, 1):
        gsp, _, _ = groups(pno)
        for ci in (0, 1):
            for g in gsp[ci]:
                if g["kind"] != kind or len(v) >= n:
                    continue
                for ln in g["lines"]:
                    if ln["x1"] < right_of(g) - 3 and len([c for c in ln["chars"] if c["c"].strip()]) > 15 and all(c["wt"] == 400 for c in ln["chars"]):
                        t = "".join(c["c"] for c in ln["chars"]).strip()
                        v.append(track_from(rp(pg), (ln["x0"], ln["base"] - 3.0, ln["x1"] - ln["x0"], 4.0), t, NOTO, 400, 8))
                        break
    return round(statistics.median(v))


TR = {"passage": chrome_track("passage"), "opts": chrome_track("opts"), "stmt": chrome_track("opts"), "bogi": chrome_track("bogi"),
      "cond": gaps_track(ALL["cond"]), "answer": gaps_track(ALL["answer"]), "prompt": -40}
Q_TSUME = 40   # 발문 — 원본 글자 쌍마다 간격 = 자간 −40‰ − 0.4 × (앞 글자 오른쪽 + 뒤 글자 왼쪽 빈 곳): 인디자인 「자간 축소」 40% (2026-10-09, 2,384쌍 3‰ 안)
LEAD = {"passage": lead_of(ALL["passage"], 14), "opts": lead_of(ALL["opts"], 12), "stmt": lead_of(ALL["opts"], 12), "bogi": lead_of(ALL["bogi"], 14),
        "cond": lead_of(ALL["cond"], 12), "prompt": lead_of(ALL["prompt"], 14.6)}
_opara = [b["base"] - a["base"] for g in ALL["opts"] for a, b in zip(g["lines"], g["lines"][1:]) if b.get("para")]
OPT_SPACE = round(statistics.median(_opara) - LEAD["opts"] * MM, 2)         # 선지 사이 단락 뒤 간격 mm
_hang = [ln["x0"] - g["left"] for g in ALL["opts"] for ln in g["lines"] if not ln.get("para")]
HANG = round(statistics.median(_hang), 2)                                    # 선지 둘째 줄 내어쓰기
_full = [ln["x1"] - g["left"] for k in ("passage", "opts", "stmt", "prompt") for g in ALL.get(k, []) for ln in g["lines"][:-1] if ln["x1"] > g["left"] + 80]
RIGHT = round(statistics.median(_full), 2)                                   # 꽉 찬 줄 끝(끝 글자 끝) — 단 왼쪽에서
_ul = [g for g in draws(1) if False]
UL_W, UL_OFF = round(0.5 * MM, 3), 0.71                                      # 밑줄 0.5pt · 기준선 아래 0.71mm(선 가운데) — read_page 와 같은 값


# ── 글 잇기 — 단·쪽을 넘는 글(인디자인 텍스트 스레드) ───────────────
# 단 위에서 번호 없이 시작하는 지문·선지 묶음이 바로 앞 묶음(앞 단 끝 · 앞 쪽 끝)과 같은 종류면 그 글이 이어진 것.
# 앞 묶음 = 이야기의 첫 상자(글·원고 자리), 이 묶음 = 이어지는 상자. 원고는 이야기 하나에 한 번(나누지 않는다).
# 56쪽 끝 38번 지문은 57쪽(다음 단위)으로 이어진다 — 원고는 57쪽 몫까지 다 넣고 56쪽 상자는 들어가는 줄만 보인다.
GROUPS = {}
_prev = None
for _pno in PAGES + [PAGES[-1] + 1]:
    _gs, _, _ = groups(_pno)
    GROUPS[_pno] = _gs
    for _ci in (0, 1):
        for _j, _g in enumerate(_gs[_ci]):
            if _j == 0 and _prev is not None and _g["kind"] in ("passage", "opts", "stmt") and _prev["kind"] == _g["kind"]:
                _g["cont_of"] = _prev
                _prev["story_next"] = _g
            _prev = _g
        if _pno > PAGES[-1]:
            break
STORY_N = [0]


def chain(g):
    """이야기의 상자들(첫 상자부터)"""
    while g.get("cont_of"):
        g = g["cont_of"]
    out = [g]
    while g.get("story_next"):
        g = g["story_next"]
        out.append(g)
    return out


def body_w(kind, track):
    """글상자 폭 — 원본 꽉 찬 줄 끝까지, 크롬은 줄 끝 글자 뒤에도 자간을 두므로 그만큼 좁게"""
    base = RIGHT - (2 * BOX_IN if kind in ("bogi", "cond") else 0)
    return round(base + track / 1000 * 8 * MM, 2)


TEMP = {"num": "00",
        "prompt": "임시 발문 — 다음 글의 _{밑줄 친 곳} 중 적절하지 {않은} 것은?",
        "passage": ("(A) Temporary passage text for styling. The real passage arrives later from outside, and this paragraph only keeps "
                    "the shape of the content with {marked words} so that the style can be set while it is still empty."),
        "opts": "① Temporary choice one\n② Temporary choice two that is a little longer than the others to wrap\n③ Temporary choice three\n④ Temporary choice four\n⑤ Temporary choice five",
        "stmt": "1) Temporary statement one. (T/F)\n2) Temporary statement two that is a little longer than the others so that it wraps. (T/F)",
        "bogi": "Temporary given text with (A)__________ and (B)__________ blanks for the style.",
        "cond": "1) 임시 조건 하나\n2) 임시 조건 둘\nword / word / word / word",
        "answer": "주제문: ______________________."}
SLOT = {"num": "문항번호", "prompt": "발문", "passage": "지문", "opts": "선지", "stmt": "진술", "bogi": "보기", "cond": "조건", "answer": "답칸"}
CONT = []                                                                    # (자리, 쪽, y, x, 글) — 끝에 편집기 자리 순서(쪽 → 위 → 왼쪽)로


def text_elem(pg, id, lines, x0, x1, multi_iou=0.80, color=INK, size=8):
    """글 묶음의 잴 요소 — 원본 그림에서 그 색 잉크 상자(첫 줄 기준선 -3.0 ~ 끝 줄 +1.0, 단 폭 안)"""
    b0, b1 = lines[0]["base"], lines[-1]["base"]
    bx = ink(pg, color, x0 - 0.6, b0 - 3.0, x1 - x0 + 1.2, b1 - b0 + 4.0)
    e = {"id": id, "x": bx[0], "y": bx[1], "w": bx[2], "h": bx[3], "color": color, "see": color, "ctol": 40, "pad": 0.3, "search": 0.8,
         "text": "".join(c["c"] for c in lines[0]["chars"]).strip()[:30], "size": size}
    if len(lines) > 1:
        e["shape_iou"] = multi_iou
    ELEMS[pg].append(e)


def body(pg):
    pno = PAGES[pg - 1]
    _, rects, uls = groups(pno)
    gs = GROUPS[pno]                                                         # 잇기 표시(cont_of · story_next)가 붙은 묶음
    items = [g for ci in (0, 1) for g in gs[ci]]
    st = []
    # 1) 상자 바탕 — 글보다 먼저(아래에) 그린다
    for k, r in enumerate(sorted(rects, key=lambda r: (r[1], r[2]))):
        kind, x, y, w, h, scol, sw = r
        if kind == "bogi":
            st += B(pg, f"bogi{k}", x, y, w, h, BOGIF, pad=0.3, ctol=5, label="보기 상자 — 연두빛 면" if k == 0 else None)
        else:
            st += frame(pg, f"cond{k}", x, y, w, h, CONDS, sw, fill=CONDF, label="조건 상자 — 하늘색 면 + 테두리")
    # 2) 종류마다 — 첫 상자를 그려 스타일·자리, 나머지는 복제
    for kind in ("num", "prompt", "passage", "opts", "stmt", "bogi", "condlabel", "cond", "answer"):
        gk = [g for g in items if g["kind"] == kind]
        inherited = False                                                    # 복제한 앞 상자에 이야기가 있었나(복제는 이야기도 옮긴다)
        for k, g in enumerate(gk):
            st += box_of(pg, kind, g, k)
            if g.get("story_next") or g.get("cont_of"):
                if not g.get("cont_of"):
                    STORY_N[0] += 1
                    g["story"] = f"이야기{STORY_N[0]}"
                    st += [S(f"글 잇기 — 이 상자가 {g['story']} 의 첫 상자(넘친 줄은 다음 단·쪽 상자로)", 1300),
                           {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 800}]
                else:
                    g["story"] = g["cont_of"]["story"]
                    st += [S(f"글 잇기 — {g['story']} 를 골라 이어 받는 상자로", 1300),
                           {"pick": {"at": '#side select[data-a="story"]', "value": g["story"]}, "wait": 800}]
                inherited = True
            elif inherited and k:
                st.append({"pick": {"at": '#side select[data-a="story"]', "value": ""}, "wait": 700})    # 복제로 따라온 이야기를 뗀다
                inherited = False
    return st


def box_of(pg, kind, g, k):
    ls = g["lines"]
    left = g["left"]
    tag = f"{kind}{k}"
    if kind == "num":
        n = ls[0]["num"]
        no = "".join(c["c"] for c in n).strip()
        base = n[0]["base"]
        bx = ink(pg, NUMC, n[0]["x"] - 0.4, base - 3.6, 8, 4.4)
        ELEMS[pg].append({"id": f"q{no}", "x": bx[0], "y": bx[1], "w": bx[2], "h": bx[3], "color": NUMC, "see": NUMC, "ctol": 30,
                          "pad": 0.4, "search": 0.8, "text": no, "size": 12})
        y = round(top_of(base, 12, EL, 700), 2)
        CONT.append(("문항번호", pg, y, left, no))
        if k == 0:
            tr = track_from(rp(pg), (n[0]["x"], base - 3.4, n[-1]["x1"] - n[0]["x"], 4.2), no, EL, 700, 12)
            tr = tr if abs(tr) > 8 else 0
            return ([S("문항 번호 — 첫 번호를 그리고 복제", 1300)] +
                    tx(left, y, 9, 6.6, TEMP["num"], 12, NUMC, label="문항 번호 자리", font=EL, weight=700, track=tr or None) + slot("문항번호"))
        return dup(left, y)
    if kind in ("prompt", "passage", "opts", "stmt", "bogi", "cond", "answer"):
        x = g["rect"][1] + BOX_IN if kind in ("bogi", "cond") else left
        x1 = g["rect"][1] + g["rect"][3] - BOX_IN if kind in ("bogi", "cond") else left + COL_W
        lead = LEAD.get(kind, 14)
        tr = TR[kind]
        base0 = ls[0]["base"]
        y = round(top_of(base0, 8, NOTO, 400, lead if kind != "answer" else None), 2)
        n_lines = len(ls)
        if g.get("story_next"):                                              # 이야기 첫 상자 — 원고는 이어지는 상자 몫까지 한 글
            txt = gtext({"kind": kind, "left": left, "lines": [ln for c in chain(g) for ln in c["lines"]]})
        else:
            txt = gtext(g)
        w = body_w(kind, tr) if kind != "answer" else round(x1 - x, 2)
        c0 = next(c for c in ls[0]["chars"] if c["c"].strip())
        first = round(c0["x"] - left, 2) if kind == "prompt" else (-HANG if kind in OPTL else 0)      # 발문 첫 줄 들여쓰기 · 선지 내어쓰기
        am = {"tracking": tr, "indent": HANG if kind in OPTL else 0, "indent_first": first,     # 글상자에 친 값 그대로 — 서버 높이 어림(text_h)과 같게
              "space_after": OPT_SPACE if kind in OPTL else 0}
        h = round(max(n_lines * lead * MM + (OPT_SPACE * n_lines if kind in OPTL else 0),
                      text_h(re.sub(r"_?\{([^}]*)\}", r"\1", txt), w, 8, lead, am), text_h(TEMP[kind], w, 8, lead, am)) + 0.6, 1)
        if g.get("story_next"):                                              # 첫 상자는 자라지 않는다 — 원본 줄 수만큼만 담고 나머지는 다음 상자로
            h = round(n_lines * lead * MM + 0.3, 2)
        if not g.get("cont_of"):                                             # 이어지는 상자는 자리가 아니다(이야기 하나 = 자리 하나)
            CONT.append((SLOT[kind], pg, y, round(x, 2), txt))
        # 잴 요소
        if kind in OPTL:
            paras, cur = [], []
            for ln in ls:
                if ln.get("para") and cur:
                    paras.append(cur)
                    cur = []
                cur.append(ln)
            paras.append(cur)
            for j, pl in enumerate(paras):
                text_elem(pg, f"{tag}-{j + 1}", pl, x, x1)
        else:
            text_elem(pg, tag, ls, x, x1)
        if k:
            return dup(round(x, 2), y, h)
        name = SLOT[kind]
        st = [S(f"{name} — 첫 글상자를 그려 스타일, 나머지는 복제", 1500)]
        st += tx(round(x, 2), y, w, h, TEMP[kind], 8, INK, label=f"{name} 자리 — 임시 글", leading=lead if kind != "answer" else None,
                   align="justify" if kind != "answer" else None, font=NOTO, track=tr or None, tsume=Q_TSUME if kind == "prompt" else None)
        if kind != "answer":                                                 # 양끝 정렬 균등 배치 — 낱말 100~133% · 자간 -5~250‰ (편집기 기본은 인디자인 공장값 80·133·0·0)
            lmin = -1 if kind == "opts" else -5                              # 진술은 지문처럼 -5(원본 50쪽 「forest. (T/」 줄이 -3‰) · 선지는 자간을 거의 안 줄인다(아래)
            st += [F('#side input[data-a="jc.word_min"]', 100), F('#side input[data-a="jc.word_max"]', 133),
                   F('#side input[data-a="jc.letter_min"]', lmin), F('#side input[data-a="jc.letter_max"]', 250)]
        if kind == "prompt":                                                 # 번호 다음 칸부터 — 둘째 줄은 단 왼쪽으로
            st.append(F('#side input[data-a="indent_first"]', first))
            st += grep(0, r"_\{([^}]*)\}", bold=False, underline=True, line=UL_W, line_off=UL_OFF, line_color=INK, hide=True,
                       label="GREP — 원고의 _{…} 는 밑줄만")
            st += grep(1, r"\{([^}]*)\}", bold=False, weight=500, underline=True, line=UL_W, line_off=UL_OFF, line_color=INK, hide=True,
                       label="GREP — 원고의 {…} 는 Medium + 밑줄")
        if kind == "passage":
            st += grep(0, r"\{([^}]*)\}", bold=False, weight=500, underline=True, line=UL_W, line_off=UL_OFF, line_color=INK, hide=True,
                       label="GREP — 원고의 {…} 는 Medium + 밑줄")
            st += grep(1, r"\([A-C]\)", bold=False, weight=500, label="GREP — 문단 머리 (A)(B)(C) 는 Medium")
        if kind in OPTL:
            st += [F('#side input[data-a="indent"]', HANG), F('#side input[data-a="indent_first"]', -HANG),
                   F('#side input[data-a="space_after"]', OPT_SPACE)]
            # (위 균등 배치에서) 선지 자간 최소 -1‰ — 원본 선지는 자간을 거의 줄이지 않는다(꽉 찬 선지 줄은 모두 기본 -50‰ 이상, 48·51·52·55쪽).
            # 크롬 폭으로 재면 원본이 한 줄에 넣은 48쪽 ⑤ 는 0.17‰ 줄여야 들어가고, 다음 줄로 보낸 52쪽 ③ 은 1.99‰ · 55쪽 ① 은 2.61‰ — 그 사이.
            # (05ee3e83 부터 끝 줄도 자간 최소까지만 줄인다.)
        st += slot(name, label=f"자리 이름 「{name}」")
        return st
    if kind == "condlabel":
        r = g["rect"]
        ch = [c for c in ls[0]["chars"] if c["c"].strip()]
        lx, lx1, base = ch[0]["x"], ch[-1]["x1"], ch[0]["base"]
        y0, h0 = win(base, 9.5)
        ELEMS[pg].append({"id": tag, "x": round(lx, 2), "y": round(y0, 2), "w": round(lx1 - lx, 2), "h": round(h0, 2), "color": INK, "see": INK,
                          "ctol": 40, "pad": 0.3, "search": 0.6, "text": "[조건]", "size": 9.5})
        if k:
            return dup(round(r[1] + BOX_IN, 2), round(top_of(base, 9.5, NOTO, 500), 2))
        return T(pg, tag, r[1] + BOX_IN, base, "[조건]", 9.5, INK, NOTO, 500, lx1, label="조건 머리 — 고정 글", measure=False)
    return []


# ── 문서 ────────────────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 S 실전문제 48-56 (A4)")
st += expect_pages(1)
# 오른쪽 속성 패널을 넓힌다 — 기본 폭에선 4칸 줄의 숫자 칸이 좁아 증감 단추가 눌린다(단위 07)
st += [S("속성 패널 넓히기", 900), {"drag": {"from": '[data-rsz="r"]', "to": [1200, 500]}, "wait": 800}]
SEL = [int(v) for v in os.environ["ONLY"].split(",")] if os.environ.get("ONLY") else list(range(1, len(PAGES) + 1))   # 고칠 때 몇 쪽만(상태.json 쪽도 같이)
for pg, pno in enumerate(PAGES, 1):
    if pg not in SEL:
        continue
    if pg != SEL[0]:
        st += add_page(f"{pno}쪽 — 새 쪽")
    st += [S(f"{pno}쪽 — S 실전 문제", 1500)]
    st += header_left(pg) if pno % 2 == 0 else header_right(pg)
    st += body(pg)
    st += footer(pg)
    st += done(f"{pno}쪽", f"p{pg}.png")

CONT.sort(key=lambda c: (c[1], round(c[2], 1), c[3]))                      # 편집기 자리 순서 = 쪽 → 위(y) → 왼쪽(x)
CONTENT = {}
for name, *_, t in CONT:
    CONTENT.setdefault(name, []).append(t)
st += put_content(CONTENT)                                                   # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({str(i + 1): ELEMS[pg] for i, pg in enumerate(SEL)}, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("14a 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
print("  자간", TR, "· 행간", LEAD, f"· 선지 간격 {OPT_SPACE} 내어쓰기 {HANG} · 줄 끝 {RIGHT}")
