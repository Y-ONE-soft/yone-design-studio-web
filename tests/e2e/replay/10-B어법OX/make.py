"""단위 10 B어법OX — 원본 d1 reference.pdf 34·35쪽(B1 어법 O/X)을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.
단위 03(A본문OX) 대본을 바탕으로 했다 — 같은 꼴(진술 + O/X 상자). 다른 점: 지문이 없고, 머리에 발문과 예시 상자(빨간 표시)가 있으며,
진술이 두 줄로 넘어가는 것이 있다(양끝맞춤).

원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로 — 원고가 들어갈 글상자(지문번호·발문·진술번호·진술)는 자리 이름 + 임시 글로
만들고 스타일을 매긴 뒤, 끝에 원고(자리 이름 → 글)를 넣어 원본과 비교한다. 예시 상자(문장·O|X·✓·밑줄·화살표·고친 말)는 이 꼴의
보기라 고정 글로 친다.

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표·경로. 보정 파일은 쓰지 않는다.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이)(mkpage.top_of). 자간 = 원본 글자 자리 - 브라우저 글자 자리(mkpage.track_from).
낱말 사이가 글자 사이보다 넓은 글(진술·예시 문장·BUILD UP — 원본 단락의 낱말 간격 125%)은 자간을 낱말 안 글자 간격에서,
낱말 사이(‰)를 공백 간격 - 공백 폭 - 자간에서 따로 잡는다(spacing).
돌린 글: 오른쪽 탭(-90°)은 03 그대로, 예시의 화살표 ⤴(+90°, 위→아래로 읽음)는 같은 식을 반대로 — rot_text 설명.
O·X 는 원본이 Type3(윤곽) — 03 에서 잉크 양으로 정한 Montserrat 800. O/X 상자는 원본 경로 그대로 원본 자리에 고정해 그린다.
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

STATE = json.load(open(os.path.join(HERE, "상태.json")))
REF = os.path.join(REPO, STATE["ref"])
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = STATE["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
LOTTE, BAEUM, CAFE = "12LotteMartDreamBold", "Elice DigitalBaeum OTF", "Cafe24 Supermagic"
INK, GOLD, RED = "#231f20", "#cba56f", "#d2232a"
LINK = "#b5ac9c"               # O/X 상자 테두리 · 가운데 막대
FAM = {"NotoSansCJKkr-Regular": (NOTO, 400), "NotoSansCJKkr-Medium": (NOTO, 500), "NotoSansCJKkr-Bold": (NOTO, 700)}


def ref_page(pg):
    return REFDOC[PAGES[pg - 1] - 1]


def hx(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3])


def win(base, size):
    """글 잴 창 — 기준선 둘레(윗높이 0.95em · 아랫높이 0.3em)"""
    return base - 0.95 * size * MM, 1.25 * size * MM


def spacing(sp, family, weight):
    """낱말 안 글자 간격 → 자간 ‰, 공백 뒤 간격 - 공백 폭 - 자간 → 낱말 사이 ‰ (원본 조각 하나의 글자 원점으로)"""
    _, _, adv = face(family, weight)
    size = sp["size"]
    ins, sps = [], []
    for (a, ax, _, _), (b, bx, _, _) in zip(sp["chars"], sp["chars"][1:]):
        if b.strip():
            (sps if a == " " else ins).append(((bx - ax) - adv(a) * size * MM) / (size * MM) * 1000)
    tr = round(statistics.median(ins))
    if not sps:
        return tr, 0
    sp_em = 0.280 if "CJK" in family else adv(" ")          # 렌더러는 Noto CJK 공백을 한국어 꼴 0.280em 으로 그린다
    ws = round(statistics.median(sps) + adv(" ") * 1000 - tr - sp_em * 1000)     # 낱말 사이 = 원본 공백 간격 - 자간 - 그려지는 공백 폭
    return tr, (ws if abs(ws) > 8 else 0)


def T(pg, id, x, base, s, size, color, family, weight, x1, label=None, w=None, temp=None, leading=None, search=0.8, ctol=30,
      shape_iou=None, pad=0.5, track=None, ws=0, measure=True, align=None):
    """원본 글 하나. x = 첫 글자 자리(원점), base = 기준선, x1 = 끝 글자 오른쪽(원본). 자간을 안 주면 원본 글자 자리에서 계산한다.
    ws = 낱말 사이 ‰(「글자 더 보기 → 낱말 사이」)"""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    y0, h0 = win(base, size)
    if track is None:
        track = track_from(ref_page(pg), (x, y0, x1 - x, h0), s, family, weight, size)
        track = track if abs(track) > 8 else 0
    if measure:
        e = {"id": id, "x": round(x, 2), "y": round(y0, 2), "w": round(x1 - x, 2), "h": round(h0, 2), "color": color, "see": color,
             "ctol": ctol, "pad": pad, "search": search, "size": size, **({"text": s} if x1 - x >= 1.2 else {})}
        # 폭 1.2mm 안 글자(「|」 막대 등)는 모양 검사를 뺀다(단위 07 과 같은 측정 한계 규칙) — 300dpi 에선 상자 폭이 1화소만 달라도
        # 잉크가 ±18% 흔들린다(ex1-bar: 600dpi 로 보면 꼴·굵기는 같고 0.04mm 밀린 것뿐인데 잉크 0.82). 자리·크기(0.3mm)는 그대로 잰다.
        if shape_iou:
            e["shape_iou"] = shape_iou
        ELEMS[pg].append(e)
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000 + max(ws, 0) * s.count(" ") * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    st = text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)
    if ws:
        st.append(F('#side input[data-a="word_spacing"]', ws))
    return st


def rot_text(pg, id, s, size, color, family, weight, xb, y_first, y_last, bbox, w=14, turn=-90, measure=True):
    """돌린 글. 원본: 기준선 x = xb, 첫 글자 원점 y = y_first, 끝 글자 원점 y = y_last.
    편집기: 상자(w × bh)를 가운데 축으로 돌린다. q = 상자 위 → 기준선(반 행간 + 윗높이), 가운데 정렬 글 줄 폭 Wr(크롬은 끝 글자 뒤에도 자간).
      -90°(아래→위로 읽음, 오른쪽 탭): 상자 안 가로 → 지면 -y, 세로 → 지면 +x
          기준선 x = cx + (q - bh/2) = xb,  첫 글자 원점 y = cy + Wr/2 = y_first
      +90°(위→아래로 읽음, 예시 화살표): 상자 안 가로 → 지면 +y, 세로 → 지면 -x
          기준선 x = cx - (q - bh/2) = xb,  첫 글자 원점 y = cy - Wr/2 = y_first"""
    asc, desc, adv = face(family, weight)
    sm = size * MM
    if len(s) > 1:
        ext = chrome_extent(family, weight, size, s)
        track = round((abs(y_first - y_last) - ext) / (len(s) - 1) / sm * 1000)
    else:
        ext, track = 0.0, 0
    tr = track / 1000 * sm
    wr = ext + adv(s[-1]) * sm + len(s) * tr
    lead = size * 1.45 * MM
    bh = round(lead + 0.4, 1)
    q = (lead - (asc + desc) * sm) / 2 + asc * sm
    if turn == -90:
        cx, cy = xb + bh / 2 - q, y_first - wr / 2
    else:
        cx, cy = xb - bh / 2 + q, y_first + wr / 2
    if measure:
        ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                          "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - w / 2, 2), round(cy - bh / 2, 2), w, bh, s, size, color, font=family, weight=weight if weight != 400 else None,
              track=track or None, align="center")
    st.append(F('#side input[data-a="rotate"]', turn, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": ctol})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None, ctol=30):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": ctol})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.6 * MM, measure=True):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, round(sw, 3), color, pad=0.15, measure=measure)


def ox_box(pg, id, x, y, w, h, r, sw_pt):
    """O/X 상자 — 둥근 네모(흰 칠 · 테두리 가운데 정렬). 원본 경로 그대로: x·y·w·h = 경로(획 가운데), r = 모서리 둥글기"""
    o = sw_pt * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - o, 2), "y": round(y - o, 2), "w": round(w + 2 * o, 2), "h": round(h + 2 * o, 2),
                      "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30})
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
                            "cb": [((c["bbox"][0] - ox) * MM, (c["bbox"][1] - oy) * MM, (c["bbox"][2] - ox) * MM, (c["bbox"][3] - oy) * MM) for c in ch],
                            "dir": l["dir"], "bb": ((s["bbox"][0] - ox) * MM, (s["bbox"][1] - oy) * MM, (s["bbox"][2] - s["bbox"][0]) * MM, (s["bbox"][3] - s["bbox"][1]) * MM)})
    return out


def fills(pg, color):
    """그 색으로 칠한 도형들 [(x, y, w, h, 그림)]"""
    p = ref_page(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for g in p.get_drawings():
        if g.get("fill") and hx(g["fill"]) == color:
            r = g["rect"]
            out.append(((r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM, g))
    return sorted(out, key=lambda r: (round(r[1], 2), r[0]))


def strokes(pg, color):
    p = ref_page(pg)
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for g in p.get_drawings():
        if g.get("color") and not g.get("fill") and hx(g["color"]) == color:
            r = g["rect"]
            out.append(((r.x0 - ox) * MM, (r.y0 - oy) * MM, r.width * MM, r.height * MM, g))
    return sorted(out, key=lambda r: (round(r[1], 2), r[0]))


def rows_of(pg):
    """진술 — 번호(롯데마트드림 9pt, 「01.⇥」) 하나에 글 줄(Noto 9pt, 두 줄도) · O · X 조각, O 를 품은 O/X 상자 경로 · 가운데 막대"""
    sp = spans(pg)
    nums = sorted([s for s in sp if s["font"].endswith("LotteMartDreamBold") and s["t"].endswith("\t")], key=lambda s: s["base"])
    stm = [s for s in sp if s["font"] == "NotoSansCJKkr-Regular" and s["color"] == INK and s["size"] < 9.5 and s["base"] > nums[0]["base"] - 1]
    os_ = [s for s in sp if s["t"] == "O" and s["font"].startswith("Type3")]
    xs = [s for s in sp if s["t"] == "X" and s["font"].startswith("Type3")]
    boxes, bars = [], []
    for x, y, w, h, g in fills(pg, "#ffffff"):
        if len(g["items"]) == 20:
            first = g["items"][0]                                                # 첫 획 = 왼쪽 세로 선 → 모서리 = 위 가로 선 시작 - 왼쪽
            top = [it for it in g["items"] if it[0] == "l" and abs(it[1].y - it[2].y) < 1e-3][0]
            boxes.append((x, y, w, h, (top[1].x - first[1].x) * MM, g["width"]))
    bars = [r[:4] for r in fills(pg, LINK) if r[2] < 1]
    out = []
    for k, n in enumerate(nums):
        nb = nums[k + 1]["base"] - 1 if k + 1 < len(nums) else 999
        inr = lambda L: [s for s in L if n["base"] - 1 <= s["base"] < nb]
        lines = {}
        for s in inr(stm):
            lines.setdefault(round(s["base"], 1), []).append(s)
        lines = [sorted(v, key=lambda s: s["x"]) for _, v in sorted(lines.items())]
        o, x = inr(os_)[0], inr(xs)[0]
        bx = [b for b in boxes if b[0] < o["x"] < b[0] + b[2] and b[1] < o["base"] < b[1] + b[3] + 1][0]
        br = [b for b in bars if bx[0] < b[0] < bx[0] + bx[2] and bx[1] < b[1] < bx[1] + bx[3]][0]
        out.append((n, lines, o, x, bx, br))
    return out


ROWS = {1: rows_of(1), 2: rows_of(2)}
NUMTR = round(statistics.median(track_from(ref_page(pg), (n["x"], win(n["base"], 9)[0], n["x1"] - n["x"], win(n["base"], 9)[1]),
                                           n["t"].strip(), LOTTE, 400, 9) for pg in (1, 2) for n, *_ in ROWS[pg]))
_two = [ls for pg in (1, 2) for _, ls, *_ in ROWS[pg] if len(ls) == 2]
LEAD = round(statistics.median(ls[1][0]["base"] - ls[0][0]["base"] for ls in _two) / MM, 2)          # 두 줄 진술의 줄 간격 = 행간
_trs = [spacing(ls[0], NOTO, 400) for pg in (1, 2) for _, lines, *_ in ROWS[pg] for ls in lines if len(lines) == 1]
STR, SWS = statistics.median(t for t, _ in _trs), statistics.median(w for _, w in _trs)
STR, SWS = round(STR), round(SWS)              # 한 줄 진술(늘어나지 않은 줄)에서

def _nb_words():
    """붙임 공백(\xa0) 뒤 끝 낱말 — 원본은 글자 크기·자간을 줄여 놓았다(「12」「by」「Compean」 7.92pt · 자간 -120‰).
    한 GREP 규칙으로 쓴다: 크기 = 원본 조각 크기, 자간 = 원본 글자 자리 - 크롬 글자 자리(커닝 포함)"""
    out = []
    for pg in (1, 2):
        for t in ref_page(pg).get_texttrace():
            w = "".join(chr(c[0]) for c in t["chars"])
            if not w.strip() or round(t["size"], 2) >= 9 or t["font"] != "NotoSansCJKkr-Regular":
                continue
            xs = [c[2][0] for c in t["chars"]]
            ext = (xs[-1] - xs[0]) * MM
            out.append((round(t["size"], 2), (ext - chrome_extent(NOTO, 400, round(t["size"], 2), w)) / (len(w) - 1) / (t["size"] * MM) * 1000))
    return statistics.median(o[0] for o in out), round(statistics.median(o[1] for o in out))


NB_SIZE, NB_TRACK = _nb_words()
NB_RE = r"(?<=\xa0)[^\s.]+"


TEMP_S = "A temporary statement sits here until the real one arrives from outside and fills the row. "


def temp_of(base, n):
    """임시 글 — 올 원고의 꼴(영어 문장)을 흉내 낸다. 길이는 원본과 비슷하게"""
    return (base * (n // len(base) + 1))[:n].rsplit(" ", 1)[0] + "."


CONTENT = {"지문번호": [], "발문": [], "진술번호": [], "진술": []}


# O/X 상자 = 부품 — 상자(둥근 면)·막대·O·X 넷을 그려 범위로 골라 「그룹」 → 부품 「그룹 1」(p_1). 진술 글상자마다 「글 끝에 붙이기」로 단다
# (인디자인 인라인 앵커처럼 글자처럼 흐른다: 자리가 모자라면 마지막 낱말과 함께 다음 줄로).
_n0, _l0, _o0, _x0, _b0, _r0 = ROWS[1][0]
TAIL_PART = "p_1"
TAIL_GAP = round(statistics.median(bx[0] - ls[-1][-1]["x1"] for pg in (1, 2) for _, ls, _, _, bx, _ in ROWS[pg]) - 1.5 * STR / 1000 * 9 * MM, 3)
#   상자 경로 왼쪽 - 끝 글자 오른쪽 - 크롬이 끝 글자·붙임 문자 뒤에 두는 자간(1~2칸 → 1.5칸)
TAIL_DROP = round(statistics.median(bx[1] + bx[3] - ls[-1][0]["base"] for pg in (1, 2) for _, ls, _, _, bx, _ in ROWS[pg]), 3)
#   기준선 → 상자 경로 아래 끝 (상자는 경로 상자 = 부품 상자, 테두리는 바깥으로 반씩 넘친다)
TAIL_W = _b0[2]


def ox_part(pg, X0=20.0, Y0=262.0):
    """O/X 부품 만들기 — 원본 첫 진술의 상자 하나를 빈 자리(X0, Y0)로 옮겨 그리고, 범위로 골라 그룹(부품)으로 묶은 뒤 지면에서는 지운다"""
    dx, dy = X0 - _b0[0], Y0 - _b0[1]
    st = [S("O/X 상자 부품 — 상자 · 막대 · O · X 를 그려 묶는다", 1500)]
    x, y, w, h, r, sw = _b0
    st += box(round(x + dx, 3), round(y + dy, 3), round(w, 3), round(h, 3), "#ffffff", radius=round(r, 3))
    st += _color("stroke.color", LINK)
    st.append(F('#side input[data-a="stroke.w"]', round(sw, 3)))
    st += B(pg, "_bar", round(_r0[0] + dx, 3), round(_r0[1] + dy, 3), round(_r0[2], 3), round(_r0[3], 3), LINK, measure=False)
    for g, col in ((_o0, "#8aabc9"), (_x0, "#bd7d70")):                              # 글상자는 상자 안에 들도록 행간 9pt · 폭 3mm
        st += T(pg, "_" + g["t"], g["x"] + dx, g["base"] + dy, g["t"], 9, col, MS, 800, g["x1"] + dx, w=3, leading=9, measure=False)
    st += [S("자석 끄기 — 켜 두면 묶을 때 원자 자리가 0.5mm 격자로 반올림된다(O 가 0.2mm 밀림)", 1300),
           {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
           S("범위로 넷을 골라 그룹 → 부품", 1300),
           {"drag": {"from": {"mm": [X0 - 2, Y0 - 2]}, "to": {"mm": [X0 + w + 2, Y0 + h + 2]}}, "wait": 900},
           {"js": "(() => '고른 것 ' + sels.size)()"},
           {"click": "#side #s-group", "wait": 1500},
           {"js": "(() => { const p = LIB.parts.find(p => p.id === '" + TAIL_PART + "'); if (!p) throw new Error('부품 " + TAIL_PART + " 없음'); "
                  "return '부품 ' + p.id + ' ' + p.w + '×' + p.h + ' 원자 ' + p.atoms.length; })()"},
           S("지면의 그룹은 지운다 — 부품은 라이브러리에 남는다", 1100), {"key": "Delete", "wait": 900},
           {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]                  # 자석 다시 켜기
    return st


def statements(pg):
    """진술 줄 — 번호 · 글(양끝맞춤, 두 줄도) + 글 끝에 붙인 O/X 상자(부품)"""
    rows = ROWS[pg]
    rights = [ls[0][-1]["x1"] for _, ls, *_ in rows if len(ls) == 2]
    right = statistics.median(rights)                                                 # 양끝 맞춘 줄의 끝 = 글상자 오른쪽
    st = []
    for k, (n, lines, o, x, bx, br) in enumerate(rows):
        st += [S(f"진술 {n['t'].strip()} — 번호 · 글 · 글 끝 O/X 상자", 1200)]
        num = n["t"].strip()
        st += T(pg, f"s{k + 1}-no", n["x"], n["base"], num, 9, n["color"], LOTTE, 400, n["x1"], temp="00.", search=0.6, track=NUMTR)
        st += slot("진술번호")
        CONTENT["진술번호"].append(num)
        txt = ""
        for ls in lines:
            seg = "".join(s["t"] for s in ls)
            txt += seg if (not txt or txt.endswith((" ", "\xa0"))) else " " + seg
        txt = txt.rstrip(" ")                                                         # 끝 공백은 원고에 안 싣는다 — 상자와의 사이는 「간격」
        CONTENT["진술"].append(txt)                                                  # 원본 글 그대로(붙임 공백 \xa0 도)
        x0, b0 = lines[0][0]["x"], lines[0][0]["base"]
        w = round(right - x0 + STR / 1000 * 9 * MM, 2)                                # 크롬은 줄 끝 글자 뒤에도 자간을 둔다
        if len(lines) == 1:
            y0, h0 = win(b0, 9)
            ELEMS[pg].append({"id": f"s{k + 1}", "x": round(x0, 2), "y": round(y0, 2), "w": round(lines[0][-1]["x1"] - x0, 2), "h": round(h0, 2),
                              "color": INK, "see": INK, "ctol": 30, "pad": 0.5, "search": 0.8, "text": txt.strip(), "size": 9})
        else:
            y0 = b0 - 0.95 * 9 * MM
            y1 = lines[-1][0]["base"] + 0.3 * 9 * MM
            ELEMS[pg].append({"id": f"s{k + 1}", "x": round(x0, 2), "y": round(y0, 2), "w": round(right - x0, 2), "h": round(y1 - y0, 2),
                              "color": INK, "see": INK, "ctol": 40, "pad": 0.5, "search": 1.0, "text": txt[:30], "size": 9,
                              "shape_iou": 0.80})        # 두 줄 문단 — 양끝맞춤에서 낱말이 0.2mm 안팎 다르게 놓인다(03 지문과 같이)
        o_ = sw_o = bx[5] * MM / 2                                                    # 잴 것: 원본 자리의 상자·막대·O·X (글 끝에 붙어 흘러온 결과)
        ELEMS[pg].append({"id": f"s{k + 1}-box", "x": round(bx[0] - o_, 2), "y": round(bx[1] - o_, 2), "w": round(bx[2] + 2 * o_, 2),
                          "h": round(bx[3] + 2 * o_, 2), "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30})
        ELEMS[pg].append({"id": f"s{k + 1}-bar", "x": round(br[0], 3), "y": round(br[1], 3), "w": round(br[2], 3), "h": round(br[3], 3),
                          "color": LINK, "see": LINK, "pad": 0.15, "ctol": 30})
        for g, col, nm in ((o, "#8aabc9", "o"), (x, "#bd7d70", "x")):
            gy, gh = win(g["base"], 9)
            ELEMS[pg].append({"id": f"s{k + 1}-{nm}", "x": round(g["x"], 2), "y": round(gy, 2), "w": round(g["x1"] - g["x"], 2), "h": round(gh, 2),
                              "color": col, "see": col, "ctol": 30, "pad": 0.5, "search": 0.6, "text": g["t"], "size": 9})
        temp = temp_of(TEMP_S, len(txt))
        a = {"tracking": STR}
        more = "M" * int((TAIL_W + TAIL_GAP) / (9 * MM * 0.6) + 1)                     # 서버 높이 어림에도 상자 폭만큼(렌더러와 같은 셈)
        h = round(max(len(lines) * LEAD * MM, text_h(txt + more, w, 9, LEAD, a), text_h(temp + more, w, 9, LEAD, a)) + 0.5, 1)
        st += text(round(x0, 2), round(top_of(b0, 9, NOTO, 400, LEAD), 2), w, h, temp, 9, INK, leading=LEAD, align="justify",
                   font=NOTO, track=STR)
        if SWS:
            st.append(F('#side input[data-a="word_spacing"]', SWS))
        st += slot("진술")
        st += justify()                                                  # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
        st += grep(0, NB_RE, bold=False, size=NB_SIZE, label=None if k else f"붙임 공백 뒤 끝 낱말 — 크기 {NB_SIZE}pt · 자간 {NB_TRACK}‰ (GREP)")
        st.append(F('#side input[data-a="grep.0.track"]', NB_TRACK, 600))
        st += [{"pick": {"at": '#side select[data-a="tail.part"]', "value": TAIL_PART}, "wait": 800},
               F('#side input[data-a="tail.gap"]', TAIL_GAP), F('#side input[data-a="tail.drop"]', TAIL_DROP)]
    return st


def number(pg):
    """지문 번호 「01 |」 — 번호는 자리(영도체), 막대는 고정 글"""
    sp = spans(pg)
    pn = [s for s in sp if s["font"].startswith("YeongdoOTF")][0]
    st = [S("번호 자리 「00」 · 막대", 1300)]
    st += T(pg, "no", pn["x"], pn["base"], pn["t"].strip(), 12, pn["color"], YD, 400, pn["x1"], label="지문 번호 자리", temp="00", search=0.6)
    st += slot("지문번호")
    CONTENT["지문번호"].append(pn["t"])          # 원본 글 그대로 「01 」 — 끝 공백을 보고 영도체가 끝 숫자 꼴을 고른다
    bar = [s for s in sp if s["t"] == "|" and s["size"] == 12][0]
    st += T(pg, "no-bar", bar["x"], bar["base"], "|", 12, bar["color"], NOTO, 400, bar["x1"], search=0.4, pad=0.3)
    return st


def header_left(pg, code, title):
    sp = spans(pg)
    st = [S("머리 — 크림 띠 · 선 · 금색 막대", 1500)]
    band = [r for r in fills(pg, "#f9f7ed") if r[0] < 0][0]
    st += B(pg, "band", round(band[0], 2), round(band[1], 2), round(band[2], 2), round(band[3], 2), "#f9f7ed")
    ln = [r for r in strokes(pg, "#b4aa9a") if r[2] > 100 and r[0] < 0][0]
    st += rule(pg, "rule", round(ln[0], 2), round(ln[1], 3), round(ln[2], 2), sw=ln[4]["width"] * MM)
    bar = [r for r in fills(pg, GOLD) if r[3] > 20][0]
    st += B(pg, "bar", round(bar[0], 2), round(bar[1], 2), round(bar[2], 2), round(bar[3], 2), GOLD)
    stp = [s for s in sp if s["t"] == "STEP" and s["size"] == 8][0]
    num = [s for s in sp if s["t"].strip() == "02" and s["size"] == 8][0]
    st += T(pg, "t-step", stp["x"], stp["base"], "STEP 02", 8, GOLD, NOTO, 400, num["x1"], label="STEP 02 · BUILD UP")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    bu = [s for s in sp if s["t"] == "BUILD UP"][0]
    tr, ws = spacing(bu, NOTO, 700)
    st += T(pg, "t-build", bu["x"], bu["base"], "BUILD UP", 8, "#b4aa9a", NOTO, 700, bu["x1"], track=tr, ws=ws)
    cd = [s for s in sp if s["font"] == "TTMamablockB"][0]
    st += T(pg, "t-code", cd["x"], cd["base"], code, 25, GOLD, MAMA, 400, cd["x1"], label="제목 — 코드 · 이름")
    tt = [s for s in sp if s["font"] == "GmarketSansMedium"][0]
    st += T(pg, "t-title", tt["x"], tt["base"], title, 13, INK, GM, 500, tt["x1"])
    st += [S("단계 점 셋 — 원 · 선 · 숫자 (지금 단계 2)", 1400)]
    circ = sorted([r for r in strokes(pg, "#b4aa9a") if len(r[4]["items"]) == 4] + [r for r in fills(pg, GOLD) if len(r[4]["items"]) == 4],
                  key=lambda r: r[0])
    lines = [r for r in strokes(pg, "#b4aa9a") if 3 < r[2] < 6 and r[3] < 0.5]
    for k, r in enumerate(circ):
        g = r[4]
        if g.get("fill"):
            st += C(pg, f"d{k + 1}", round(r[0], 3), round(r[1], 3), round(r[2], 3), fill=GOLD)
        else:
            st += C(pg, f"d{k + 1}", round(r[0], 3), round(r[1], 3), round(r[2], 3), stroke="#b4aa9a", sw=round(g["width"], 3))
        if k < len(lines):
            l = sorted(lines, key=lambda r: r[0])[k]
            st += rule(pg, f"dl{k + 1}", round(l[0], 3), round(l[1], 3), round(l[2], 3))
    od = [r for r in fills(pg, "#e5aa7e")][0]
    st += C(pg, "dot", round(od[0], 3), round(od[1], 3), round(od[2], 3), fill="#e5aa7e", ctol=20)
    for k, d in enumerate("123"):
        s = [s for s in sp if s["t"] == d and s["font"] == "Montserrat-Bold"][0]
        st += T(pg, f"n{k + 1}", s["x"], s["base"], d, 6, s["color"], MS, 700, s["x1"], search=0.1, measure=False)
        sm = 6 * MM                                                              # 잴 창 = 숫자 높이만 — 바로 아래 발문 글 가장자리가 섞이지 않게
        ELEMS[pg].append({"id": f"n{k + 1}", "x": round(s["x"], 2), "y": round(s["base"] - 0.8 * sm, 2), "w": round(s["x1"] - s["x"], 2),
                          "h": round(0.82 * sm, 2), "color": s["color"], "see": s["color"], "ctol": 30, "pad": 0.1, "search": 0.1, "size": 6,
                          **({"text": d} if s["x1"] - s["x"] >= 1.2 else {})})          # 폭 1.2mm 안은 모양 검사 뺌(위 T 와 같은 규칙)
    st += [S("발문 자리 — 임시 발문", 1300)]
    q = [s for s in sp if s["font"] == "EliceDigitalBaeumOTF"][0]
    st += T(pg, "q", q["x"], q["base"], q["t"].strip(), 9, INK, BAEUM, 400, q["x1"], label="발문 자리", w=round(q["x1"] - q["x"] + 15, 1),
            temp="임시 발문 — 각 문장을 읽고 틀린 곳을 고치시오")
    st += slot("발문")
    CONTENT["발문"].append(q["t"].strip())
    return st


def example(pg):
    """예시 상자 — 회색 면 · 문장 둘(고정 글) · O|X 작은 면 · 빨간 ✓ · 빨간 밑줄 · 돌린 화살표 ⤴ · 고친 말(카페24 슈퍼매직)"""
    sp = spans(pg)
    st = [S("예시 상자 — 회색 면", 1400)]
    gr = fills(pg, "#eff0f0")[0]
    st += B(pg, "ex-bg", round(gr[0], 3), round(gr[1], 3), round(gr[2], 3), round(gr[3], 3), "#eff0f0", label="예시 상자 — 회색 면", ctol=8)
    for k, r in enumerate(fills(pg, "#f9fcf3")):
        o = r[4]["width"] * MM / 2                                                   # 칠과 같은 색 테두리 — 바깥 끝까지 면으로
        st += B(pg, f"ex-ox{k + 1}", round(r[0] - o, 3), round(r[1] - o, 3), round(r[2] + 2 * o, 3), round(r[3] + 2 * o, 3), "#f9fcf3",
                ctol=5, pad=0.3, label="O|X 자리 — 작은 면" if not k else None)
    sents = sorted([s for s in sp if s["font"] == "NotoSansCJKkr-Regular" and s["size"] == 9 and s["base"] < 50], key=lambda s: s["base"])
    for k, s in enumerate(sents):
        st += [S(f"예시 문장 {k + 1}", 1100)]
        tr, ws = spacing(s, NOTO, 400)
        st += T(pg, f"ex{k + 1}", s["x"], s["base"], s["t"].strip(), 9, INK, NOTO, 400, s["x1"], track=tr, ws=ws)
        near = lambda L: min(L, key=lambda t: abs(t["base"] - s["base"]))
        o = near([t for t in sp if t["font"] == "NotoSansCJKkr-Medium" and t["t"].strip() == "O"])
        b = near([t for t in sp if t["t"] == "|" and t["font"].endswith("LotteMartDreamBold")])
        x = near([t for t in sp if t["font"] == "NotoSansCJKkr-Medium" and t["t"].strip() == "X"])
        st += T(pg, f"ex{k + 1}-o", o["x"], o["base"], "O", 9, o["color"], NOTO, 500, o["x1"], search=0.4, pad=0.3)
        st += T(pg, f"ex{k + 1}-bar", b["x"], b["base"], "|", 9, b["color"], LOTTE, 400, b["x1"], search=0.4, pad=0.3)
        st += T(pg, f"ex{k + 1}-x", x["x"], x["base"], "X", 9, x["color"], NOTO, 500, x["x1"], search=0.4, pad=0.3)
    st += [S("빨간 ✓ 둘", 1100)]
    for k, s in enumerate(sorted([s for s in sp if s["t"] == "✓"], key=lambda s: s["base"])):
        st += T(pg, f"ck{k + 1}", s["x"], s["base"], "✓", 10, RED, NOTO, 700, s["x1"], search=0.4, pad=0.3)
    st += [S("고친 곳 셋 — 밑줄 · 화살표(돌린 글) · 고친 말", 1300)]
    unders = sorted(strokes(pg, RED), key=lambda r: r[0])
    arrows = sorted([s for s in sp if s["t"] == "⤴"], key=lambda s: s["x"])
    words = sorted([s for s in sp if s["font"].startswith("Cafe24")], key=lambda s: s["x"])
    for k, (u, a, wd) in enumerate(zip(unders, arrows, words)):
        sw = u[4]["width"] * MM
        st += rule(pg, f"ul{k + 1}", round(u[0], 3), round(u[1], 3), round(u[2], 3), color=RED, sw=sw, measure=False)
        ax, ay = a["chars"][0][1], a["chars"][0][2]
        st += rot_text(pg, f"ar{k + 1}", "⤴", 10, RED, NOTO, 700, ax, ay, ay, None, turn=90, measure=False)
        tr, ws = spacing(wd, CAFE, 700) if " " in wd["t"] else (None, 0)
        st += T(pg, f"fix{k + 1}", wd["x"], wd["base"], wd["t"].strip(), 9, RED, CAFE, 700, wd["x1"], track=tr, ws=ws, measure=False)
        y0 = u[1] - sw / 2                                                           # 밑줄 · 화살표 · 고친 말을 한 덩어리로 잰다(같은 빨강이 맞붙어 있다)
        y1 = max(c[3] for c in wd["cb"])
        ELEMS[pg].append({"id": f"fix{k + 1}", "x": round(u[0], 2), "y": round(y0, 2), "w": round(wd["x1"] - u[0], 2), "h": round(y1 - y0, 2),
                          "color": RED, "see": RED, "ctol": 30, "pad": 0.3, "search": 0.4, "text": wd["t"].strip(), "size": 9})
    return st


def footer(pg):
    sp = spans(pg)
    st = [S("꼬리 — 쪽번호", 1200)]
    for s in sorted([s for s in sp if s["font"] == "EliceDXNeolliOTF-Bd" and s["size"] == 6], key=lambda s: s["x"]):
        col = s["color"]
        st += T(pg, "f-" + ("no" if s["t"].strip().isdigit() else "t"), s["x"], s["base"], s["t"].strip(), 6, col, EL, 700, s["x1"], search=0.6)
    return st


# ── 34쪽 (왼쪽 면) ─────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 B1 어법 OX (A4)")
st += expect_pages(1)
st += [S("① 34쪽 — B1 어법 O/X", 1500)]
st += header_left(1, "B1", "어법 O/X")
st += example(1)
st += number(1)
st += ox_part(1)
st += statements(1)
st += footer(1)
st += done("34쪽", "p1.png")

# ── 35쪽 (오른쪽 면) ───────────────────────────────────────
st += add_page("② 35쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
band = [r for r in fills(2, "#f9f7ed") if r[0] >= 0][0]
st += B(2, "band", round(band[0], 2), round(band[1], 2), round(band[2], 2), round(band[3], 2), "#f9f7ed")
ln = [r for r in strokes(2, "#b4aa9a") if r[2] > 100 and r[0] > -10][0]
st += rule(2, "rule", round(ln[0], 2), round(ln[1], 3), round(ln[2], 2), sw=ln[4]["width"] * MM)
tag = fills(2, "#bdafa2")[0]
pts = [(it[1].x, it[1].y) for it in tag[4]["items"]]
P0 = ref_page(2)
xs_ = [(px - P0.trimbox.x0) * MM for px, _ in pts]
d = f"M{(xs_[3] - tag[0]) / tag[2]:.4f} 0 L1 0 L1 1 L0 1 Z"                         # 원본 꼭짓점: 왼쪽 위만 안으로 들어간 사다리꼴
ELEMS[2].append({"id": "tag", "x": round(tag[0], 2), "y": round(tag[1], 2), "w": round(210 - tag[0], 2), "h": round(tag[3], 3), "color": "#bdafa2"})
st += shape(round(tag[0], 2), round(tag[1], 2), round(tag[2], 2), round(tag[3], 3), "#bdafa2", d=d, label="꼬리표 — 도형, 원본 꼭짓점 그대로")
SP2 = spans(2)
tg = [s for s in SP2 if s["t"] == "STEP BY STEP" and s["font"] == "Montserrat-Bold"][0]
st += T(2, "tag-t", tg["x"], tg["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, tg["x1"], search=0.2, pad=0.2)   # 흰 글 — 잴 창을 꼬리표 안으로
cd = [s for s in SP2 if s["font"] == "Montserrat-Medium"][0]
st += T(2, "t-code", cd["x"], cd["base"], "B1", 36, GOLD, MS, 500, cd["x1"], label="큰 코드 B1")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글 (지금 단계 STEP 02)", 1500)]
tabs = sorted([r for c in ("#e1eaf3", GOLD, "#f8e1da") for r in fills(2, c) if r[0] > 200], key=lambda r: r[1])
for k, r in enumerate(tabs):
    st += B(2, f"tab{k + 1}", round(r[0], 2), round(r[1], 2), round(r[2], 2), round(r[3], 2), hx(r[4]["fill"]))
seen = set()
for s in [s for s in SP2 if s["size"] == 6.5]:
    if s["t"] in seen:
        continue                                                              # 원본은 탭 글이 두 벌 겹쳐 있다
    seen.add(s["t"])
    ch = s["chars"]
    ys = [c[2] for c in ch]
    st += rot_text(2, f"tab{len(seen)}-t", s["t"], 6.5, s["color"], MS, 700, ch[0][1], ys[0], ys[-1], tuple(round(v, 2) for v in s["bb"]))
st += number(2)
st += statements(2)
st += footer(2)
st += done("35쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("10 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()},
      f"· 진술 행간 {LEAD} 자간 {STR} 낱말 사이 {SWS} · 번호 자간 {NUMTR} · 붙임 뒤 낱말 {NB_SIZE}pt {NB_TRACK}‰")
