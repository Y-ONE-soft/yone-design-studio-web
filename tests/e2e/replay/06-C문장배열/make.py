"""단위 06 C문장배열 — 원본 d1 reference.pdf 20·21쪽을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.
원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로 — 문항 번호·문장 목록·발문·주어진 문장·지문은 자리 + 임시 글 + 스타일, 끝에 원고를 넣는다.
견본: 02B-원고자리/make.py (같은 디자인 계열 — 머리 띠·단계 점·제목·옆 탭·쪽번호).

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표. 보정 파일 없음.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이) (mkpage.top_of). 자간 = (원본 첫~끝 글자 거리 - 브라우저 같은 거리) / 사이 수 —
그 글 조각 자기 글자만으로 잰다(위아래 줄이 가까운 목록에서 mkpage.track_from 의 잘라 읽기는 옆 줄 글자를 같이 집는다).
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import chrome_extent
import pymupdf

REF = os.path.join(REPO, "tests/e2e/replay/_원본/워크북_d1.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
BAEUM = "Elice DigitalBaeum OTF"


# ── 원본 읽기 ──────────────────────────────────────────────
def spans(pno):
    """원본 쪽의 글 조각 — 지면 좌표 mm. x = 첫 글자(공백 아닌) 시작점, x1 = 끝 글자 폭 끝, base = 기준선, top/bot = 조각 상자"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out, seen = [], set()
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ch = s["chars"]
                ink = [i for i, c in enumerate(ch) if c["c"].strip()]
                if not ink:
                    continue
                key = (round(s["origin"][0], 2), round(s["origin"][1], 2), s["font"])
                if key in seen:                                        # 탭 글은 두 번 찍혀 있다
                    continue
                seen.add(key)
                c0, c1 = ch[ink[0]], ch[ink[-1]]
                out.append({"t": "".join(c["c"] for c in ch[ink[0]:ink[-1] + 1]), "raw": "".join(c["c"] for c in ch),
                            "chars": ch[ink[0]:ink[-1] + 1], "x": (c0["origin"][0] - ox) * MM, "x1": (c1["bbox"][2] - ox) * MM,
                            "ox": (c0["origin"][0] - ox) * MM, "oy": (c0["origin"][1] - oy) * MM,
                            "base": (s["origin"][1] - oy) * MM, "top": (s["bbox"][1] - oy) * MM, "bot": (s["bbox"][3] - oy) * MM,
                            "size": round(s["size"], 1), "font": s["font"], "color": "#%06x" % s["color"], "dir": l["dir"]})
    return out


def trk(sp, family, weight, vertical=False):
    """자간(‰) — 이 조각 글자만으로. <·>·& 는 브라우저 측정 쪽지(HTML)에 못 넣어 양 끝에서 뺀다."""
    ch = sp["chars"]
    i0, i1 = 0, len(ch) - 1
    while i0 < i1 and (ch[i0]["c"] in "<>&" or not ch[i0]["c"].strip()):
        i0 += 1
    while i1 > i0 and (ch[i1]["c"] in "<>&" or not ch[i1]["c"].strip()):
        i1 -= 1
    s = "".join(c["c"] for c in ch[i0:i1 + 1])
    if len(s) < 2:
        return 0
    k = 1 if vertical else 0
    orig = abs(ch[i1]["origin"][k] - ch[i0]["origin"][k]) * MM
    t = round((orig - chrome_extent(family, weight, sp["size"], s)) / (len(s) - 1) / (sp["size"] * MM) * 1000)
    return t if abs(t) > 8 else 0


def find(sps, start, **kw):
    for s in sps:
        if s["t"].startswith(start) and all(abs(s[k] - v) < 0.6 for k, v in kw.items()):
            return s
    raise KeyError(start)


def ink_box(sp):
    return (round(sp["x"], 2), round(sp["top"], 2), round(sp["x1"] - sp["x"], 2), round(sp["bot"] - sp["top"], 2))


# ── 그리기 ──────────────────────────────────────────────────
def T(pg, id, x, base, s, size, color, family, weight, bbox, track, leading=None, label=None, search=1.5, w=None, align=None, temp=None, pad=None):
    """글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글 상자(잴 자리), track = 원본에서 잰 자간"""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s, "size": size, **({"pad": pad} if pad is not None else {})})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


def R(pg, id, sp, family, weight, color, bw=14, label=None):
    """돌린 글(아래에서 위로 읽는 탭 글) — 회전 -90°, 축 = 상자 가운데(편집기 기본).
    돌리기 전 상자의 (왼쪽 끝, 기준선)이 원본 첫 글자 시작점(기준선 x, 아래쪽 y)에 오도록 가운데를 푼다:
    돌린 뒤 기준선 x = cx + (기준선 - 상자 가운데) · 글 시작 y = cy + 폭/2."""
    size = sp["size"]
    lead = size * 1.45
    bh = round(lead * MM + 0.4, 1)
    d = sp["base"] - top_of(sp["base"], size, family, weight)              # 상자 위 끝 → 기준선
    cx = sp["ox"] - (d - bh / 2)
    cy = sp["oy"] - bw / 2
    tr = trk(sp, family, weight, vertical=True)
    ext = (sp["chars"][0]["bbox"][3] - sp["chars"][-1]["bbox"][1]) * MM     # 원본 글 길이(세로)
    xs = [(c["bbox"][0]) for c in sp["chars"]] + [(c["bbox"][2]) for c in sp["chars"]]
    p = REFDOC[PAGES[pg - 1] - 1]
    ELEMS[pg].append({"id": id, "x": round((min(xs) - p.trimbox.x0) * MM, 2), "y": round(sp["oy"] - ext, 2), "w": round((max(xs) - min(xs)) * MM, 2),
                      "h": round(ext, 2), "color": color, "see": color, "ctol": 30, "search": 0.8, "text": sp["t"], "size": size})
    st = text(round(cx - bw / 2, 2), round(cy - bh / 2, 2), bw, bh, sp["t"], size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=tr or None)
    st.append(F('#side input[data-a="rotate"]', -90, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30, radius=0):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": ctol})
    st = box(x, y, w, h, fill, label=label)
    if radius:
        st.append(F('#side input[data-a="radius"]', radius))
    return st


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


def frame(pg, id, x, y, w, h, color, sw, label=None):
    """테두리만 있는 면 — 칠 없음 · 획 색 · 획 두께(pt, 원본 mm 에서). 획은 가운데 정렬(편집기 기본 = 원본 PDF 와 같다)"""
    ELEMS[pg].append({"id": id, "x": round(x - sw / 2, 3), "y": round(y - sw / 2, 3), "w": round(w + sw, 3), "h": round(h + sw, 3),
                      "color": color, "see": color, "pad": 0.4, "ctol": 30})
    st = box(x, y, w, h, None, label=label)
    st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})       # 칠 없음
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', color, 750),
           F('#side input[data-a="stroke.w"]', round(sw / MM, 3))]
    return st


def seg(p0, p1, color, sw):
    """선 도구 한 토막 — 원본 꺾은선의 한 변. 가로로 그린 뒤 길이 = 변 길이, 회전 = 변 각도, 축 = 선 가운데(편집기)라
    시작점 = 가운데 - 길이/2. 끝모양 둥글게(원본 PDF lineCap 1) — 두 토막이 만나는 꼭짓점은 둥근 끝이 겹쳐 원본의 둥근 연결과 같다."""
    import math
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    ang = math.degrees(math.atan2(dy, dx))
    cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    st = [{"draw": {"tool": "line", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + 20, SPOT["mm"][1]]}}, "wait": 750},
          F('#side input[data-a="x2"]', round(ln, 3)),
          F('#side input[data-it="x"]', round(cx - ln / 2, 3)), F('#side input[data-it="y"]', round(cy, 3)),
          F('#side input[data-a="stroke.w"]', round(sw / MM, 3)),
          {"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
          F('#side input[type="text"][data-a="stroke.color"]', color, 750),
          {"pick": {"at": '#side select[data-a="stroke.cap"]', "value": "round"}, "wait": 550},
          F('#side input[data-a="rotate"]', round(ang, 2), 600)]
    return st


def checkbox(pg, pno):
    """발문 앞 체크 상자 — 둥근 네모(흰 칠 · 파란 획) + 체크 꺾은선(옅은 파랑, 둥근 끝) · 원본 경로 좌표 그대로"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    sq = ck = None
    for dr in p.get_drawings():
        r = dr["rect"]
        if r.width * MM < 4 and r.height * MM < 4:
            if dr["type"] == "fs":
                sq = dr
            elif dr["type"] == "s":
                ck = dr
    r = sq["rect"]
    x, y, w, h = (r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM
    corner = (sq["items"][4][4].x - sq["items"][0][1].x) * MM                # 첫 곡선 묶음(4토막)이 가로로 간 거리 = 모서리 반지름
    sw = sq["width"] * MM
    stroke = "#%02x%02x%02x" % tuple(round(c * 255) for c in sq["color"])
    st = [S("체크 상자 — 둥근 네모 · 체크 표시", 1300)]
    ELEMS[pg].append({"id": "chk-box", "x": round(x - sw / 2, 2), "y": round(y - sw / 2, 2), "w": round(w + sw, 2), "h": round(h + sw, 2),
                      "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30})
    st += box(round(x, 3), round(y, 3), round(w, 3), round(h, 3), "#ffffff")
    st.append(F('#side input[data-a="radius"]', round(corner, 2)))
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', stroke, 750),
           F('#side input[data-a="stroke.w"]', round(sw / MM, 3))]
    pts = [((it[1].x - ox) * MM, (it[1].y - oy) * MM) for it in ck["items"]] + [((ck["items"][-1][2].x - ox) * MM, (ck["items"][-1][2].y - oy) * MM)]
    csw = ck["width"] * MM
    ccol = "#%02x%02x%02x" % tuple(round(c * 255) for c in ck["color"])
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    ELEMS[pg].append({"id": "chk-mark", "x": round(min(xs) - csw / 2, 2), "y": round(min(ys) - csw / 2, 2),
                      "w": round(max(xs) - min(xs) + csw, 2), "h": round(max(ys) - min(ys) + csw, 2), "color": ccol, "see": ccol, "pad": 0.1, "ctol": 30})
    for a, b in zip(pts, pts[1:]):
        st += seg(a, b, ccol, csw)
    return st, corner


# ── 원고 자리 ────────────────────────────────────────────────
CONTENT = {"문항번호": [], "문장": [], "발문": [], "주어진문장": [], "지문": []}      # 끝에 넣을 원고 — 자리 이름 → 글(읽는 순서)
TEMP = ("Temporary text for styling, the real sentence arrives from outside later and keeps going "
        "until the paragraph is long enough to show the style. ")


def temp_of(n, start=""):
    return start + ((TEMP * (n // len(TEMP) + 2))[:max(n - len(start), 8)].rsplit(" ", 1)[0].rstrip(",") + ".")


def lines_in(sps, box, sizes):
    """상자 안 글 조각을 줄로 — 기준선이 0.15mm 안이면 한 줄. [(기준선, [조각…])]"""
    x, y, w, h = box
    got = sorted((s for s in sps if s["dir"][0] == 1 and x - 1 < s["x"] < x + w and y < s["base"] < y + h and s["size"] in sizes),
                 key=lambda s: (s["base"], s["x"]))
    rows = []
    for s in got:
        if rows and abs(s["base"] - rows[-1][0]) < 0.15:
            rows[-1][1].append(s)
        else:
            rows.append([s["base"], [s]])
    for r in rows:
        r[1].sort(key=lambda s: s["x"])
        r[0] = min(t["base"] for t in r[1] if t["size"] == 8.5)             # 줄 기준선 = 본문(8.5pt) 기준선
    return rows


def sentence_list(pno):
    """회색 상자 안 문장 목록 — 문장마다 한 단락: 기호 (A)~(J) 는 9pt 굵은 파랑, 본문 8.5pt. 줄마다 기호가 있으면 새 단락."""
    sps = spans(pno)
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    grey = next(d["rect"] for d in p.get_drawings() if d.get("fill") and "#%02x%02x%02x" % tuple(round(c * 255) for c in d["fill"]) == "#f5f4ef")
    gbox = ((grey.x0 - ox) * MM, (grey.y0 - oy) * MM, grey.width * MM, grey.height * MM)
    rows = lines_in(sps, gbox, (8.5, 9.0))
    paras, label_bases, lab_shift, wraps, rights, wrap_bases = [], [], [], [], [], []
    for k, (base, ss) in enumerate(rows):
        lab = [s for s in ss if s["size"] == 9.0]
        body = "".join(s["raw"] for s in ss if s["size"] == 8.5).strip()
        if lab:
            paras.append(lab[0]["t"] + " " + body)
            label_bases.append(base)
            lab_shift.append(lab[0]["base"] - base)
        else:
            paras[-1] += " " + body
            wraps.append(base - rows[k - 1][0])
            wrap_bases.append(base)
            rights.append(max(s["x1"] for s in rows[k - 1][1]))
    first = rows[0][1]
    return {"box": gbox, "x": min(s["x"] for s in first), "base0": rows[0][0], "base1": rows[-1][0], "paras": paras,
            "label_bases": label_bases, "lab_shift": lab_shift, "wraps": wraps, "wrap_bases": wrap_bases, "right": statistics.median(rights),
            "top": min(s["top"] for s in first), "bot": max(s["bot"] for s in rows[-1][1]), "n_lines": len(rows),
            "track": statistics.median(trk(s, NOTO, 400) for k, (_, ss) in enumerate(rows) for s in ss            # 양끝맞춤으로 안 늘어난 줄(다음 줄이 새 단락)만
                                       if s["size"] == 8.5 and len(s["t"]) > 20 and "<" not in s["t"]
                                       and (k == len(rows) - 1 or any(t["size"] == 9.0 for t in rows[k + 1][1])))}


def passage(pno):
    """테두리 상자 안 지문 — 줄 간격이 행간보다 크게 벌어지면 새 단락"""
    sps = spans(pno)
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    fr = next(d["rect"] for d in p.get_drawings() if d["type"] == "s" and d["rect"].height * MM > 30)
    fbox = ((fr.x0 - ox) * MM, (fr.y0 - oy) * MM, fr.width * MM, fr.height * MM)
    rows = lines_in(sps, fbox, (8.5,))
    gaps = [rows[k][0] - rows[k - 1][0] for k in range(1, len(rows))]
    lead = min(gaps)
    paras, space, rights = [], [], []
    for k, (base, ss) in enumerate(rows):
        body = "".join(s["raw"] for s in ss).strip()
        if k and gaps[k - 1] > lead * 1.5:
            paras.append(body)
            space.append(gaps[k - 1] - lead)
        elif k:
            paras[-1] += " " + body
            rights.append(max(s["x1"] for s in rows[k - 1][1]))
        else:
            paras.append(body)
    last = [rows[k] for k in range(len(rows)) if k == len(rows) - 1 or gaps[k] > lead * 1.5]   # 단락 끝 줄 — 양끝맞춤으로 안 늘어난 줄만 자간을 잰다
    return {"box": fbox, "x": min(s["x"] for s in rows[0][1]), "base0": rows[0][0], "base1": rows[-1][0], "paras": paras, "lead": lead,
            "space": space, "right": statistics.median(rights), "top": min(s["top"] for s in rows[0][1]), "bot": max(s["bot"] for s in rows[-1][1]),
            "n_lines": len(rows), "track": statistics.median(trk(s, NOTO, 400) for _, ss in last for s in ss if len(s["t"]) > 20 and "<" not in s["t"])}


WORD_MIN = -60       # 양끝 줄 낱말 간격 최소 — 02B 와 같은 틀 값(인디자인이 공백을 줄여 넣은 줄)
# 양끝 정렬 자간 최소 = 0‰ (줄이지 않음) — 원본 20·21쪽 목록·지문의 양끝 줄은 공백+자간이 모두 0.718mm 이상(안 늘린 줄 0.720)이라
# 줄인 줄이 하나도 없다. 그리고 21쪽 지문 첫 줄 「dead.」(크롬 자연 폭 161.27mm, 측정 160 → -3.4‰)·20쪽 (D) 「Forest.」처럼
# 기본 한계 -8‰ 안에서 줄이면 들어갈 낱말을 넣지 않고 다음 줄로 넘겼다. 기본값이면 컴포저가 줄여 넣어 줄 끝이 원본과 달라진다.
JC_LETTER_MIN = 0

LIST = {pn: sentence_list(pn) for pn in PAGES}
PASS = {pn: passage(pn) for pn in PAGES}
# 문장 목록 행간 — 꺾인 줄(기호 없는 둘째 줄)의 기준선 간격. 두 쪽 모두 같은 틀 스타일이라 함께 평균
L_MM = statistics.mean(w for pn in PAGES for w in LIST[pn]["wraps"])
L_PT = round(L_MM / MM, 2)
# 기호 줄이 한 줄 상자를 더 높인다(편집기 = CSS 줄 상자): 9pt 굵은 글의 줄 상자 위 끝이 8.5pt 기본 줄보다
# ((윗높이-아랫높이)_9pt - (윗높이-아랫높이)_8.5pt)/2 만큼 위로 나온다(같은 행간 px 을 물려받으므로). 그래서 기호 줄은 기준선이 E_MM 내려가고 줄이 그만큼 높다.
# (편집기 글 배치 해상도 TEXT_ZOOM=100 — 서체 높이 반올림은 0.01mm 라 반올림 없이 셈한다)
_a4, _d4, _ = face(NOTO, 400)
_a7, _d7, _ = face(NOTO, 700)
E_MM = max(0.0, ((_a7 - _d7) * 9 - (_a4 - _d4) * 8.5) / 2) * MM
# 단락 뒤 간격 = 기호 줄 사이 평균 간격 - 행간 - E_MM (꺾인 줄은 행간만큼)
_tr = [(LIST[pn]["label_bases"][-1] - LIST[pn]["label_bases"][0] - sum(1 for b in LIST[pn]["wrap_bases"] if b < LIST[pn]["label_bases"][-1]) * L_MM)
       / (len(LIST[pn]["label_bases"]) - 1) for pn in PAGES]                  # 첫 기호 줄 ~ 끝 기호 줄 사이의 꺾인 줄만 뺀다
SPACE_MM = round(statistics.mean(_tr) - L_MM - E_MM, 2)
BSHIFT = round(statistics.mean(v for pn in PAGES for v in LIST[pn]["lab_shift"]) / MM * -1, 1) or None   # 기호 기준선이 본문보다 아래(원본)
LTRACK = round(statistics.mean(LIST[pn]["track"] for pn in PAGES))
P_LEAD = round(statistics.mean(PASS[pn]["lead"] for pn in PAGES) / MM, 2)
P_SPACE = round(statistics.mean(v for pn in PAGES for v in PASS[pn]["space"]), 2)       # 단락 사이 기준선 간격 - 행간
PTRACK = round(statistics.mean(PASS[pn]["track"] for pn in PAGES))


def list_box(pg, pno):
    L = LIST[pno]
    st = [S(f"문장 목록 — 자리 「문장」 · 기호 (A)~(J) 는 GREP 으로 9pt 굵은 파랑", 1500)]
    st += B(pg, "grey", *[round(v, 2) for v in L["box"]], "#f5f4ef", ctol=8)
    x, right = round(L["x"], 2), L["right"]
    w = round(right - x + LTRACK / 1000 * 8.5 * MM, 2)
    for k, col in (("list", "#231f20"), ("list-b", "#00559f")):
        ELEMS[pg].append({"id": k, "x": x, "y": round(L["top"], 2), "w": round(right - x, 2), "h": round(L["bot"] - L["top"], 2), "color": col, "see": col,
                          "ctol": 40, "search": 1.0, "text": L["paras"][0][:30], "size": 8.5, "shape_iou": 0.80})
    y = top_of(L["base0"], 8.5, NOTO, 400, L_PT) - E_MM
    h = round(L["base1"] - y + 3, 1)
    CONTENT["문장"].append("\n".join(L["paras"]))
    temp = "\n".join(temp_of(len(t), t[:4]) for t in L["paras"])           # 「(A) 」 + 비슷한 길이의 임시 문장
    st += text(x, round(y, 2), w, h, temp, 8.5, "#231f20", label="문장 목록 글상자 — 임시 글", leading=L_PT, align="justify", font=NOTO, track=LTRACK or None)
    st += slot("문장", label="자리 이름 「문장」")
    st.append(F('#side input[data-a="space_after"]', SPACE_MM, 600))
    st.append(F('#side input[data-a="word_min"]', WORD_MIN, 600))
    st += justify(letter_min=JC_LETTER_MIN)                              # 균등 배치 — 낱말 100·133%, 자간 0(원본 줄이기 없음)·250‰
    st += grep(0, r"\([A-J]\)", "#00559f", size=9, bshift=BSHIFT, label="GREP 스타일 — 기호 (A)~(J) 만 9pt 굵은 파랑")
    return st


def answer(pg, pno):
    """답 쓰는 자리 — ➡ 표시 + 하늘색 선 (고정 디자인)"""
    sps = spans(pno)
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ar = find(sps, "➡")
    st = [S("답 자리 — ➡ · 선", 1300)]
    st += T(pg, "arrow", ar["x"], ar["base"], "➡", 9, ar["color"], NOTO, 400, ink_box(ar), 0, search=0.6)
    ln = next(d for d in p.get_drawings() if d["type"] == "s" and d["rect"].height < 0.1 and 50 < d["rect"].width * MM < 80)
    r = ln["rect"]
    st += rule(pg, "ans-line", round((r.x0 - ox) * MM, 2), round((r.y0 - oy) * MM, 3), round(r.width * MM, 2),
               "#%02x%02x%02x" % tuple(round(c * 255) for c in ln["color"]), round(ln["width"] * MM, 3))
    return st


def question(pg, pno):
    """발문 줄 — 체크 상자 + 발문(자리) · 주어진 문장 분홍 상자(자리) · 테두리 상자 지문(자리)"""
    sps = spans(pno)
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    st, _ = checkbox(pg, pno)
    q = next(s for s in sps if s["font"].startswith("EliceDigitalBaeum") and len(s["t"]) > 5)
    PB = PASS[pno]
    right = PB["right"]
    st += T(pg, "q", q["x"], q["base"], q["t"], 9, q["color"], BAEUM, 400, ink_box(q), trk(q, BAEUM, 400),
            w=round(right - q["x"], 1), temp="발문 임시 글 — 묻는 말 한 줄이 여기에 온다.", label="발문 자리")
    st += slot("발문")
    CONTENT["발문"].append(q["t"])
    pink = next(d["rect"] for d in p.get_drawings() if d.get("fill") and "#%02x%02x%02x" % tuple(round(c * 255) for c in d["fill"]) == "#faf4f7")
    st += B(pg, "pink", round((pink.x0 - ox) * MM, 2), round((pink.y0 - oy) * MM, 2), round(pink.width * MM, 2), round(pink.height * MM, 2),
            "#faf4f7", label="주어진 문장 — 분홍 상자", ctol=5)
    g = next(s for s in sps if s["size"] == 8.5 and (pink.y0 - oy) * MM < s["base"] < (pink.y1 - oy) * MM)
    gtr = trk(g, NOTO, 400)
    st += T(pg, "given", g["x"], g["base"], g["t"], 8.5, g["color"], NOTO, 400, ink_box(g), gtr,
            w=round(right - g["x"], 1), temp="Temporary given sentence for styling.", label="주어진 문장 자리")
    st += slot("주어진문장")
    CONTENT["주어진문장"].append(g["t"])
    st += [S("지문 — 테두리 상자 · 자리 「지문」", 1300)]
    st += frame(pg, "frame", *[round(v, 2) for v in PB["box"]], "#72bbda", round(next(d["width"] for d in p.get_drawings()
                if d["type"] == "s" and d["rect"].height * MM > 30) * MM, 3))
    x = round(PB["x"], 2)
    w = round(right - x + PTRACK / 1000 * 8.5 * MM, 2)
    ELEMS[pg].append({"id": "passage", "x": x, "y": round(PB["top"], 2), "w": round(right - x, 2), "h": round(PB["bot"] - PB["top"], 2),
                      "color": "#231f20", "see": "#231f20", "ctol": 40, "search": 1.0, "text": PB["paras"][0][:30], "size": 8.5, "shape_iou": 0.80})
    y = top_of(PB["base0"], 8.5, NOTO, 400, P_LEAD)
    CONTENT["지문"].append("\n".join(PB["paras"]))
    temp = "\n".join(temp_of(len(t), t[:4] if t.startswith("(") else "") for t in PB["paras"])
    st += text(x, round(y, 2), w, round(PB["base1"] - y + 3, 1), temp, 8.5, "#231f20", label="지문 글상자 — 임시 글",
               leading=P_LEAD, align="justify", font=NOTO, track=PTRACK or None)
    st += slot("지문")
    st.append(F('#side input[data-a="space_after"]', P_SPACE, 600))
    st.append(F('#side input[data-a="word_min"]', WORD_MIN, 600))
    st += justify(letter_min=JC_LETTER_MIN)                              # 균등 배치 — 낱말 100·133%, 자간 0(원본 줄이기 없음)·250‰
    return st


def number(pg, pno):
    sps = spans(pno)
    n = next(s for s in sps if s["font"].startswith("Yeongdo"))
    CONTENT["문항번호"].append(n["t"])
    st = T(pg, "no", n["x"], n["base"], n["t"], 12, n["color"], YD, 400, ink_box(n), trk(n, YD, 400), search=0.6,
           label="문항 번호 자리", temp="00")
    return st + slot("문항번호")


def folio(pg, pno):
    st = [S("꼬리 — 쪽번호", 1200)]
    for s in sorted((s for s in spans(pno) if s["size"] == 6.0 and s["base"] > 280), key=lambda s: s["x"]):
        st += T(pg, "f-no" if s["t"].isdigit() else "f-t", s["x"], s["base"], s["t"], 6, s["color"], EL, 700,
                (round(s["x"], 2), 283.62, round(s["x1"] - s["x"], 2), 2.62), trk(s, EL, 700), search=0.6)
    return st


# ── 20쪽 (왼쪽 면) ─────────────────────────────────────────
P0, P1 = PAGES
S0 = spans(P0)
st = open_doc("스텝바이스텝 워크북 C1 (A4)")
st += expect_pages(1)
st += [S("① 20쪽 — C1 문장 배열", 1500)]
st += [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
st += B(1, "band", -3, -3, 213, 26.5, "#f9f7ed")
st += rule(1, "rule", -3, 23.5, 216)
st += B(1, "bar", 11.2, -3, 2.2, 26.6, "#77a1c4")
s_step = next(s for s in S0 if s["t"] == "STEP")                            # 「STEP BY STEP」(꼬리)과 헷갈리지 않게
s_frame = find(S0, "FRAME")
st += T(1, "t-step", 20.0, s_step["base"], "STEP 01", 8, "#77a1c4", NOTO, 400, (20.0, 3.83, 10.87, 8.06), 0, label="STEP 01 · FRAME")
st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
st += T(1, "t-frame", s_frame["x"], s_frame["base"], "FRAME", 8, "#b4aa9a", NOTO, 700, ink_box(s_frame), trk(s_frame, NOTO, 700))
s_code = find(S0, "C1")
st += T(1, "t-code", s_code["x"], s_code["base"], "C1", 25, "#77a1c4", MAMA, 400, (20.0, 12.18, 7.72, 9.78), trk(s_code, MAMA, 400), label="제목 — 코드 · 이름")
s_title = next(s for s in S0 if s["font"].startswith("GmarketSans"))
TITLE_X = round(s_title["x"], 2)
_trt = trk(s_title, GM, 500)
st += T(1, "t-title", TITLE_X, s_title["base"], s_title["t"], 13, "#231f20", GM, 500,
        (TITLE_X, round(s_title["top"], 2), round(s_title["x1"] - TITLE_X, 2), round(s_title["bot"] - s_title["top"], 2)), _trt)
st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
st += C(1, "d1", 55.5, 13.06, 5.4, fill="#77a1c4")
st += rule(1, "dl1", 61.6, 15.76, 4.2)
st += C(1, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
st += rule(1, "dl2", 72.6, 15.76, 4.2)
st += C(1, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
for k, (nx, nw, col) in enumerate(((57.79, 0.83, "#ffffff"), (68.58, 1.25, "#b4aa9a"), (79.57, 1.25, "#b4aa9a"))):
    st += T(1, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), 0, search=0.6)
st += number(1, P0)
st += list_box(1, P0)
st += answer(1, P0)
st += question(1, P0)
st += folio(1, P0)
st += done("20쪽", "p1.png")

# ── 21쪽 (오른쪽 면) ───────────────────────────────────────
S1 = spans(P1)
st += add_page("② 21쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
s_tag = find(S1, "STEP BY STEP")
st += T(2, "tag-t", s_tag["x"], s_tag["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, (round(s_tag["x"], 2), 19.56, round(s_tag["x1"] - s_tag["x"], 2), 2.84),
        trk(s_tag, MS, 700), search=0.3, pad=0.3)   # 흰 글 — 잴 창을 꼬리표 안으로(창이 크면 띠 아래 흰 종이까지 「흰 잉크」로 센다)
s_big = next(s for s in S1 if s["size"] == 36.0)
st += T(2, "t-code", s_big["x"], s_big["base"], "C1", 36, "#77a1c4", MS, 500, (round(s_big["x"], 2), 2.62, round(s_big["x1"] - s_big["x"], 2), 16.71),
        trk(s_big, MS, 500), label="큰 코드 C1")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
tabs = sorted((s for s in S1 if s["dir"][1] != 0), key=lambda s: s["oy"])
for k, s in enumerate(tabs):
    st += R(2, f"tab{k + 1}-t", s, MS, 700, s["color"], label="탭 글 — 돌린 글" if k == 0 else None)
st += number(2, P1)
st += list_box(2, P1)
st += answer(2, P1)
st += question(2, P1)
st += folio(2, P1)
st += done("21쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("06 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
print(f"  문장 목록 행간 {L_PT}pt · 단락 뒤 {SPACE_MM}mm · 기호 줄 더 높음 {E_MM:.3f}mm · 기호 기준선 {BSHIFT}pt · 자간 {LTRACK}")
print(f"  지문 행간 {P_LEAD}pt · 단락 뒤 {P_SPACE}mm · 자간 {PTRACK}")
for pn in PAGES:
    L, P = LIST[pn], PASS[pn]
    print(f"  p{pn} 목록 x={L['x']:.2f}~{L['right']:.2f} 기준선 {L['base0']:.2f}~{L['base1']:.2f} 단락 {len(L['paras'])} 줄 {L['n_lines']}")
    print(f"  p{pn} 지문 x={P['x']:.2f}~{P['right']:.2f} 기준선 {P['base0']:.2f}~{P['base1']:.2f} 단락 {len(P['paras'])} 줄 {P['n_lines']}")
print(json.dumps(CONTENT, ensure_ascii=False)[:600])
