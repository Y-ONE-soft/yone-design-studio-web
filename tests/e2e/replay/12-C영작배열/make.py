"""단위 12 C영작배열 — 원본 d1 reference.pdf 42·43쪽을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.
원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로 — 지문 이름·문장 번호·해석·배열 조각은 자리 + 임시 글 + 스타일, 끝에 원고를 넣는다.
견본: 06-C문장배열/make.py (머리 띠·제목·쪽번호) · 09-A어법선택 (STEP 02 색 · 돌린 탭 글 TR).

자리 이름 — 블록 지도 B8 문장드릴(문장 번호 + 해석 + 과제):
  지문이름(「본문1」) · 문장번호(「01.」) · 해석(우리말 문장) · 배열(영작 배열 조각 「on / was found / …」)
문항마다: 문장 번호 · 해석 · 연보라 둥근 면(배열 조각 바탕 — 원본 크기 그대로) · 배열 조각 · 「»」 · 쓰기 선 두 줄.
해석·배열은 원본이 양끝맞춤(두 줄 문항의 앞줄 끝이 모두 글상자 오른쪽 188.00mm 에 붙는다) — 단락 컴포저가 줄 끝을 고른다.

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선·글자 자리)과 도형 좌표. 보정 파일 없음.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이) (mkpage.top_of). 자간 = (원본 첫~끝 글자 거리 - 브라우저 같은 거리) / 사이 수.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import chrome_extent
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
LOTTE = "12LotteMartDreamBold"
MYRIAD = "Myriad Pro"
BEIGE = "#cba56f"              # STEP 02 색 — 원본 막대·코드·찬 원


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


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
                            "ox": (c0["origin"][0] - ox) * MM, "oy": (c0["origin"][1] - oy) * MM, "x0": (ch[0]["origin"][0] - ox) * MM,
                            "base": (s["origin"][1] - oy) * MM, "top": (s["bbox"][1] - oy) * MM, "bot": (s["bbox"][3] - oy) * MM,
                            "size": round(s["size"], 1), "font": s["font"], "color": "#%06x" % s["color"], "dir": l["dir"]})
    return out


def draws(pno):
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    return [dict(dr, mm=[(dr["rect"].x0 - ox) * MM, (dr["rect"].y0 - oy) * MM, dr["rect"].width * MM, dr["rect"].height * MM])
            for dr in p.get_drawings()]


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


def ink_box(sp):
    return (round(sp["x"], 2), round(sp["top"], 2), round(sp["x1"] - sp["x"], 2), round(sp["bot"] - sp["top"], 2))


# ── 그리기 ──────────────────────────────────────────────────
def T(pg, id, x, base, s, size, color, family, weight, bbox, track, leading=None, label=None, search=1.5, w=None, h=None, align=None,
      temp=None, pad=None):
    """글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글 상자(잴 자리), track = 원본에서 잰 자간"""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s.strip(), "size": size, **({"pad": pad} if pad is not None else {})})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = h or round((leading or size * 1.45) * MM + 0.4, 1)
    return text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


def rot_spans(pno):
    """원본 쪽의 돌린 글(아래에서 위로 읽는 탭 글) 조각 — 글자 원점 mm. 원본은 같은 글이 두 번 겹쳐 있어 한 번만"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out, seen = [], set()
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (0.0, -1.0):
                continue
            for sp in l["spans"]:
                ink = [c for c in sp["chars"] if c["c"].strip()]
                t = "".join(c["c"] for c in sp["chars"]).strip()
                if not ink or t in seen:
                    continue
                seen.add(t)
                out.append({"text": t, "color": "#%06x" % sp["color"], "x0": (ink[0]["bbox"][0] - ox) * MM, "size": round(sp["size"], 1),
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM) for c in ink]})
    return sorted(out, key=lambda r: r["chars"][0][2])


def TR(pg, id, sp, size, color, family, weight, w=14, label=None):
    """돌린 글 — 단위 04·09 의 TR 과 같은 계산. 편집기는 글상자를 가운데 기준으로 돌린다.
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
    run_c = (first_y + last_y - adv(s[-1]) * size * MM) / 2
    bh = round(size * 1.45 * MM + 0.4, 1)
    depth = 10 - top_of(10, size, family, weight)
    cx = base_x - (depth - bh / 2)
    cy = run_c - t_mm / 2
    ELEMS[pg].append({"id": id, "x": sp["x0"], "y": min(c[2] for c in ch) - adv(s[-1]) * size * MM, "w": 3.08,
                      "h": orig + adv(s[-1]) * size * MM, "color": color, "see": color, "ctol": 30, "search": 0.8, "text": s, "size": size})
    st = text(round(cx - w / 2, 2), round(cy - bh / 2, 2), w, bh, s, size, color, label=label, font=family,
              weight=weight if weight != 400 else None, track=track or None, align="center")
    st.append(F('#side input[data-a="rotate"]', -90, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6, ctol=30, radius=0):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": ctol})
    return box(x, y, w, h, fill, label=label, radius=radius)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


# ── 원고 자리 ────────────────────────────────────────────────
CONTENT = {"지문이름": [], "문장번호": [], "해석": [], "배열": []}      # 끝에 넣을 원고 — 자리 이름 → 글(읽는 순서)
KTEMP = "임시 해석 글입니다 — 우리말 문장 한 줄이 여기에 오고, 길면 다음 줄로 넘어가며 스타일을 보여 줍니다. "
CTEMP = "word / a phrase / temporary / chunk text / for styling / the real chunks / arrive / later / from outside / "


def temp_of(tmpl, n):
    """자리의 임시 글 — 올 원고의 꼴을 흉내 낸 글. 길이는 원본과 비슷하게"""
    return (tmpl * (n // len(tmpl) + 2))[:n].rsplit(" ", 1)[0]


def items(pno):
    """문항 — 문장 번호(롯데마트드림) 하나마다: 해석 줄 · 연보라 면 · 배열 줄 · 「»」 · 쓰기 선"""
    sps = spans(pno)
    dr = draws(pno)
    nums = sorted((s for s in sps if s["font"].startswith("12LotteMart")), key=lambda s: s["base"])
    lav = sorted((d for d in dr if d.get("fill") and hexc(d["fill"]) == "#e4dfed"), key=lambda d: d["mm"][1])
    rules = [d for d in dr if d["type"] == "s" and hexc(d["color"]) == "#92b0d3"]
    out = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 1e9
        bx = next(d for d in lav if n["base"] < d["mm"][1] < nxt)
        by0, by1 = bx["mm"][1], bx["mm"][1] + bx["mm"][3]
        kor = sorted((s for s in sps if "Regular" in s["font"] and s["size"] == 8.5 and n["base"] - 1 < s["base"] < by0), key=lambda s: s["base"])
        chk = sorted((s for s in sps if "Medium" in s["font"] and s["size"] == 8.5 and by0 < s["base"] < by1), key=lambda s: s["base"])
        arr = next(s for s in sps if s["font"].startswith("MyriadPro") and by1 < s["base"] < nxt)
        ln = sorted((d for d in rules if by1 < d["mm"][1] < nxt), key=lambda d: d["mm"][1])
        out.append({"no": n, "kor": kor, "box": bx, "chk": chk, "arrow": arr, "lines": ln})
    return out


ITEMS = {pn: items(pn) for pn in PAGES}
ALL = [it for pn in PAGES for it in ITEMS[pn]]
# 행간 — 두 줄 문항의 기준선 간격(원본). 해석은 문항 08 하나, 배열은 01·04·08
K_LEAD = round(statistics.mean(b["base"] - a["base"] for it in ALL for a, b in zip(it["kor"], it["kor"][1:])) / MM, 2)
C_LEAD = round(statistics.mean(b["base"] - a["base"] for it in ALL for a, b in zip(it["chk"], it["chk"][1:])) / MM, 2)
# 자간 — 양끝맞춤으로 안 늘어난 줄(단락 끝 줄)만, 20자 넘는 것
K_TRACK = round(statistics.median(trk(it["kor"][-1], NOTO, 400) for it in ALL if len(it["kor"][-1]["t"]) > 20))
C_TRACK = round(statistics.median(trk(it["chk"][-1], NOTO, 500) for it in ALL if len(it["chk"][-1]["t"]) > 20))
N_TRACK = round(statistics.median(trk(it["no"], LOTTE, 400) for it in ALL))
# 글상자 오른쪽 = 양끝맞춤 앞줄 끝(원본 글자 폭 끝) — 쪽마다(43쪽은 2.02mm 오른쪽)
def right_of(pno):
    ends = [it["chk"][0]["x1"] for it in ITEMS[pno] if len(it["chk"]) > 1] + [it["kor"][0]["x1"] for it in ITEMS[pno] if len(it["kor"]) > 1]
    return statistics.median(ends)


RIGHT = {pn: right_of(pn) for pn in PAGES}


def space_runs(sp):
    """조각 안 공백 폭(다음 글자 원점 - 공백 원점, mm)"""
    ch = sp["chars"]
    return [(ch[i + 1]["origin"][0] - ch[i]["origin"][0]) * MM for i in range(len(ch) - 1) if ch[i]["c"] == " "]


# 배열 문단 양끝 정렬(인디자인 「균등 배치」) — 원본에서 잰다. 끝 줄(안 늘어난 줄) 공백 = 자연 폭, 양끝 줄 공백 / 자연 폭 = 늘린 비율.
# 원본 양끝 줄은 모두 자연 폭 이상(106~134%) — 줄인 줄이 없다. 04번은 끝 줄 「get」을 줄여 넣지 않고 앞줄을 110% 늘렸다
# → 자간 최소 0‰(끝 줄도 줄이지 않음) · 낱말 최소 100%. 늘림 쪽은 기본(낱말 133% · 자간 120‰)으로 둔다.
C_NAT = statistics.median(v for it in ALL for v in space_runs(it["chk"][-1]))
C_JUST = [statistics.median(space_runs(s)) / C_NAT for it in ALL for s in it["chk"][:-1]]
JC_LETTER_MIN = 0 if min(C_JUST) >= 0.999 else None
JC_WORD_MIN = 100


def item(pg, pno, k, it):
    st = [S(f"문항 {it['no']['t']} — 번호 · 해석 · 배열 조각 · 쓰기 선", 1300)]
    n = it["no"]
    first = k == 0 and pg == 1
    CONTENT["문장번호"].append(n["t"])
    st += T(pg, f"no{k}", n["x"], n["base"], n["t"], n["size"], n["color"], LOTTE, 400, ink_box(n), N_TRACK, search=0.6, pad=0.6,
            temp="00.", label="문장 번호 자리" if first else None)
    st += slot("문장번호")
    right = RIGHT[pno]
    # 해석 — 양끝맞춤 · 자리 「해석」
    kor = it["kor"]
    kt = "".join(s["raw"] for s in kor)
    CONTENT["해석"].append(kt)
    kx = round(kor[0]["x0"], 2)
    for j, s in enumerate(kor):
        ELEMS[pg].append({"id": f"kor{k}" + (f"-{j}" if j else ""), **dict(zip("xywh", ink_box(s))), "color": "#231f20", "see": "#231f20",
                          "ctol": 40, "pad": 0.6, "search": 0.6, "text": s["t"], "size": 8.5})
    # 글상자 높이는 14mm 넘게 — 대본이 SPOT 에 끌어 그린 임시 상자가 낮으면(9mm) 두 번 누르는 가운데가 위 변 가운데 손잡이(selbox .hd)에
    # 걸려 글 편집칸이 안 열린다(판 1·2: 42쪽 문항 05 배열 상자 — elementFromPoint = SPAN.hd). 글은 위에서부터 놓이므로 모양은 같다.
    kw = round(right - kx + K_TRACK / 1000 * 8.5 * MM, 2)           # 상자 오른쪽 = 원본 줄 끝 + 끝 글자 뒤 자간(음수) — 양끝 줄 끝 글자 폭 끝이 원본 줄 끝에 온다
    ky = top_of(kor[0]["base"], 8.5, NOTO, 400, K_LEAD)
    st += text(kx, round(ky, 2), kw, max(14, round(len(kor) * K_LEAD * MM + 3, 1)), temp_of(KTEMP, len(kt)), 8.5, "#231f20",
               label="해석 글상자 — 임시 글" if first else None, leading=K_LEAD, align="justify", font=NOTO, track=K_TRACK or None)
    st += slot("해석")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    # 배열 조각 바탕 — 연보라 둥근 면(원본 경로: 모서리 반지름 = 첫 곡선의 가로 거리)
    bx = it["box"]
    p = REFDOC[pno - 1]
    c0 = bx["items"][0]
    rad = round(abs(c0[1].x - c0[4].x) * MM, 2)
    st += B(pg, f"lav{k}", *[round(v, 2) for v in bx["mm"]], "#e4dfed", label="배열 바탕 — 연보라 둥근 면" if first else None, ctol=8, radius=rad)
    # 배열 조각 — Noto Medium · 양끝맞춤 · 자리 「배열」
    chk = it["chk"]
    ct = "".join(s["raw"] for s in chk)
    CONTENT["배열"].append(ct)
    cx = round(min(s["x0"] for s in chk), 2)
    for j, s in enumerate(chk):
        ELEMS[pg].append({"id": f"chk{k}" + (f"-{j}" if j else ""), **dict(zip("xywh", ink_box(s))), "color": "#231f20", "see": "#231f20",
                          "ctol": 40, "pad": 0.6, "search": 0.6, "text": s["t"], "size": 8.5})
    cw = round(right - cx + C_TRACK / 1000 * 8.5 * MM, 2)
    cy = top_of(chk[0]["base"], 8.5, NOTO, 500, C_LEAD)
    st += text(cx, round(cy, 2), cw, max(14, round(len(chk) * C_LEAD * MM + 3, 1)), temp_of(CTEMP, len(ct)), 8.5, "#231f20",
               label="배열 글상자 — 임시 글" if first else None, leading=C_LEAD, align="justify", font=NOTO, track=C_TRACK or None, weight=500)
    st += slot("배열")
    st += justify(word_min=JC_WORD_MIN, letter_min=-8 if JC_LETTER_MIN is None else JC_LETTER_MIN)   # 균등 배치 — 원본 잰 값(낱말 최소 100·자간 최소 0) + 늘림 133%·250‰
    # 「»」 + 쓰기 선 두 줄 (고정 디자인)
    a = it["arrow"]
    st += T(pg, f"arr{k}", a["x"], a["base"], a["t"], a["size"], a["color"], MYRIAD, 400, ink_box(a), 0, search=0.6, pad=0.6, h=12)
    for j, d in enumerate(it["lines"]):
        st += rule(pg, f"ln{k}-{j}", round(d["mm"][0], 2), round(d["mm"][1], 3), round(d["mm"][2], 2), hexc(d["color"]), round(d["width"] * MM, 3))
    return st


def label_of(pg, pno):
    """지문 이름 「본문1」 — 영도체 12pt · 자리 「지문이름」"""
    s = next(s for s in spans(pno) if s["font"].startswith("Yeongdo"))
    CONTENT["지문이름"].append(s["t"])
    # 잴 창 — 글자 위 끝 ~ 기준선 아래 0.8mm: 창이 아래로 크면 바로 밑 해석 글(검정)의 흐린 가장자리 화소(회색)가 이 색(#af9d81) 30 안으로 잡힌다
    win = (round(s["x"], 2), round(s["top"], 2), round(s["x1"] - s["x"], 2), round(s["base"] + 0.8 - s["top"], 2))
    st = T(pg, "name", s["x"], s["base"], s["t"], 12, s["color"], YD, 400, win, trk(s, YD, 400), search=0.3, pad=0.3,
           label="지문 이름 자리", temp="본문0")
    return st + slot("지문이름")


def folio(pg, pno):
    st = [S("꼬리 — 쪽번호", 1200)]
    for s in sorted((s for s in spans(pno) if s["size"] == 6.0 and s["base"] > 280), key=lambda s: s["x"]):
        st += T(pg, "f-no" if s["t"].isdigit() else "f-t", s["x"], s["base"], s["t"], 6, s["color"], EL, 700,
                (round(s["x"], 2), 283.62, round(s["x1"] - s["x"], 2), 2.62), trk(s, EL, 700), search=0.6)
    return st


# ── 42쪽 (왼쪽 면) ─────────────────────────────────────────
P0, P1 = PAGES
S0 = spans(P0)
st = open_doc("스텝바이스텝 워크북 C2 영작배열 (A4)")
st += expect_pages(1)
st += [S("① 42쪽 — C2 영작 배열", 1500)]
st += [S("머리 — 크림 띠 · 선 · 베이지 막대", 1500)]
st += B(1, "band", -3, -3, 213, 26.5, "#f9f7ed")
st += rule(1, "rule", -3, 23.5, 216)
st += B(1, "bar", 11.2, -3, 2.2, 26.6, BEIGE)
s_step = next(s for s in S0 if s["t"] == "STEP")
s_build = next(s for s in S0 if s["t"] == "BUILD UP")
st += T(1, "t-step", s_step["x"], s_step["base"], "STEP 02", 8, BEIGE, NOTO, 400, (20.0, 3.83, 10.87, 8.06), 0, label="STEP 02 · BUILD UP")
st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
st += T(1, "t-frame", s_build["x"], s_build["base"], "BUILD UP", 8, "#b4aa9a", NOTO, 700, ink_box(s_build), trk(s_build, NOTO, 700))
s_code = next(s for s in S0 if s["font"].startswith("TTMamablockB"))
st += T(1, "t-code", s_code["x"], s_code["base"], s_code["t"], 25, BEIGE, MAMA, 400, ink_box(s_code), trk(s_code, MAMA, 400), label="제목 — 코드 · 이름")
s_title = next(s for s in S0 if s["font"].startswith("GmarketSans"))
st += T(1, "t-title", round(s_title["x"], 2), s_title["base"], s_title["t"], 13, "#231f20", GM, 500, ink_box(s_title), trk(s_title, GM, 500))
st += [S("단계 점 셋 — 지금 단계(2)가 찬 원", 1400)]
st += C(1, "d1", 55.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
st += rule(1, "dl1", 61.6, 15.76, 4.2)
st += C(1, "d2", 66.5, 13.06, 5.4, fill=BEIGE)
st += rule(1, "dl2", 72.6, 15.76, 4.2)
st += C(1, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
for k, s in enumerate(sorted((s for s in S0 if s["font"] == "Montserrat-Bold" and s["size"] == 6.0), key=lambda s: s["x"])):
    st += T(1, f"n{k + 1}", s["x"], s["base"], s["t"], 6, s["color"], MS, 700, (round(s["x"], 2), 14.22, round(s["x1"] - s["x"], 2), 2.84), 0, search=0.6)
st += label_of(1, P0)
for k, it in enumerate(ITEMS[P0]):
    st += item(1, P0, k, it)
st += folio(1, P0)
st += done("42쪽", "p1.png")

# ── 43쪽 (오른쪽 면) ───────────────────────────────────────
S1 = spans(P1)
st += add_page("② 43쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
s_tag = next(s for s in S1 if s["t"] == "STEP BY STEP")
st += T(2, "tag-t", s_tag["x"], s_tag["base"], "STEP BY STEP", 6, "#ffffff", MS, 700, (round(s_tag["x"], 2), 19.56, round(s_tag["x1"] - s_tag["x"], 2), 2.84),
        trk(s_tag, MS, 700), search=0.2, pad=0.2)   # 흰 글 — 잴 창을 꼬리표 안으로
s_big = next(s for s in S1 if s["size"] == 36.0)
st += T(2, "t-code", s_big["x"], s_big["base"], s_big["t"], 36, BEIGE, MS, 500, (round(s_big["x"], 2), 2.62, round(s_big["x1"] - s_big["x"], 2), 16.71),
        trk(s_big, MS, 500), label="큰 코드 C2")
st += [S("오른쪽 탭 셋 — 지금 단계(STEP 02)가 베이지", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#e1eaf3")
st += B(2, "tab2", 201.5, 90, 11.5, 26, BEIGE)
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
for k, sp in enumerate(rot_spans(P1)):                                     # 원본은 아래에서 위로 읽는 글 — 위에서 아래 순서로
    st += TR(2, f"tab{k + 1}-t", sp, sp["size"], sp["color"], MS, 700, label="탭 글 — 돌린 글" if k == 0 else None)
st += label_of(2, P1)
for k, it in enumerate(ITEMS[P1]):
    st += item(2, P1, k, it)
st += folio(2, P1)
st += done("43쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("12 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
print(f"  해석 행간 {K_LEAD}pt · 자간 {K_TRACK} · 배열 행간 {C_LEAD}pt · 자간 {C_TRACK} · 번호 자간 {N_TRACK}")
print(f"  글상자 오른쪽 {RIGHT}")
print(f"  배열 공백 자연 {C_NAT:.3f}mm · 양끝 줄 늘림 {[round(v * 100) for v in C_JUST]}% → 낱말 최소 {JC_WORD_MIN}% · 자간 최소 {JC_LETTER_MIN}‰")
print(json.dumps(CONTENT, ensure_ascii=False)[:900])
