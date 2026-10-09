"""단위 14b S실전문제 — 원본 d1 reference.pdf 57~65쪽(9면)을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
(단위 14 는 27면이라 세 작업자가 48~56 · 57~65 · 66~74 로 나눴다.)

면 구조 (원본 PDF 에서 읽은 것):
  홀수 쪽(오른쪽 면) 머리 — 크림 띠 · 선 · 큰 「S」 · 꼬리표 STEP BY STEP · 오른쪽 탭 셋(01 · 02 · STEP 03 찬 벽돌색)
  짝수 쪽(왼쪽 면) 머리 — 크림 띠 · 선 · 벽돌색 막대 · STEP 03 TEST · 「S 실전 문제」 · 단계 점(3 이 찬 원)
  본문 — 두 단(82mm). 문항마다 번호(엘리스 굵게 12pt 파랑) · 발문(본고딕 8pt, 둘째 줄은 단 왼쪽으로) ·
         [보기 상자(연두빛 바탕)] · 지문(본고딕 8pt 양끝맞춤 행간 14pt) · 선지/진술(내어쓰기 3.5mm 행간 12pt) ·
         [조건 상자(하늘색 바탕 + 테두리) + 「주제문: ___.」]
자리 이름 — 블록 지도 B6 문항 기준: 문항번호 · 발문 · 보기 · 지문 · 선지 · 조건 · 답칸.
  밑줄 친 곳은 원고에 약속 괄호로 — `{…}` = Medium + 밑줄(문항 지문의 ①{was troubled} · 발문의 적절하지 {않은}),
  `_{…}` = 밑줄만(발문 「밑줄 친 _{Kuo's unusual skills}가」). GREP 가 괄호는 감추고 서식만 입힌다.
  (A)(B)(C) 순서 문항의 문단 머리 「(A)」 는 GREP 로 Medium.
  「[조건]」 머리는 상자마다 같은 고정 글.

단·쪽을 넘어 이어지는 글은 글 잇기(인디자인 텍스트 스레드, fd881cde)로 — 원고는 하나로 넣고 첫 상자 높이를 원본 줄 수만큼 두면
넘친 줄이 다음 상자로 흐른다: 49번 선지(59쪽 두 단) · 57번 선지(60→61쪽) · 59번 선지(61쪽 두 단) · 66번 지문(62→63쪽) · 74번 지문(64→65쪽).
57쪽 왼쪽 위 38번 지문 끝은 첫 상자가 56쪽(단위 14a)이라 이 문서에선 따로 자리로 둔다.

값은 모두 원본 PDF 에서 — 글 조각(서체·크기·색·기준선·글자 자리)·도형 좌표·밑줄 선. 측정 보정 없음.
글상자 위 끝 = top_of(기준선 공식), 자간 = 원본 글자 간격 - 서체 폭의 중앙값.
종류마다 첫 글상자만 스타일을 매기고 나머지는 「⧉ 복제」 후 자리·높이만 친다(단위 07 과 같이).
"""
import json, os, re, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)                                                # mkpage.chrome_extent 가 core.units.render 를 쓴다
from mkpage import *                                                    # noqa
import pagecmp
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
ELEMS = {k + 1: [] for k in range(len(PAGES))}
MM = 25.4 / 72
NOTO, MS, EL, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
INK, BRICK, TAB, NUMC = "#231f20", "#bc736c", "#b4aa9a", "#00559f"
CONDF, CONDS, BOGIF = "#dbecf2", "#6ab3c7", "#f9fcf3"                 # 조건 상자 바탕·테두리, 보기 상자 바탕
COL_W = 82.0                                                            # 단 폭 (조건·보기 상자 폭과 같다)
BOX_IN = 3.0                                                            # 상자 안 글 들여 — 원본 상자 x + 3.0
BODY_BOTTOM = 279.0                                                     # 본문 글상자가 자랄 수 있는 아래 끝 (꼬리 쪽번호 위)
CIRC = "①②③④⑤"
RA = {}
SPOT["mm"] = [1.0, 140.0]      # 임시로 그리는 자리 — 왼쪽 여백(단 왼쪽 20mm 앞)은 어느 쪽에도 비어 있다.
# 그린 상자가 다른 상자와 겹친 자리를 두 번 누르면 편집기는 「고른 것을 또 누르면 그 아래 것」으로 넘어가 글을 엉뚱한 상자에 친다(61쪽 첫 판)


def small_draw(st):
    """글상자 임시 크기를 16×9mm 로 — 두 번 누를 가운데가 왼쪽 여백 안에 머물게(본문 상자와 안 겹치게)"""
    for x in st:
        if "draw" in x and x["draw"]["tool"] == "text":
            x["draw"]["to"] = {"mm": [SPOT["mm"][0] + 16, SPOT["mm"][1] + 9]}
        if "write" in x:
            x["write"]["at"] = {"mm": [SPOT["mm"][0] + 8, SPOT["mm"][1] + 4.5]}
    return st


def ref_arr(pg):
    if pg not in RA:
        RA[pg] = pagecmp.page_array(REF, PAGES[pg - 1])
    return RA[pg]


def ink(pg, color, x, y, w, h, tol=40):
    """원본 쪽에서 그 색 잉크 상자(mm) — 잴 요소의 자리"""
    return pagecmp.color_box(ref_arr(pg), color, x, y, w, h, pad=0, tol=tol)


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, w=None, align=None, temp=None,
      pad=None, track=None):
    """원본 글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 글자 자리에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    if track is None:
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    e = {"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
         "ctol": 30, "search": search, "text": s, "size": size}
    if pad is not None:
        e["pad"] = pad
    ELEMS[pg].append(e)
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    st = text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)
    return st


def R(pg, id, pno, s, color, size=6.5, family=MS, weight=700, bw=14):
    """돌린 글(아래에서 위로 읽는 옆 탭) — 단위 05 의 R 과 같은 계산(원본 글자 원점에서 바로)."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ch = next([c for c in sp["chars"]] for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]
              if l["dir"][1] < -0.5 and "".join(c["c"] for c in sp["chars"]) == s)
    bx_base = (ch[0]["origin"][0] - ox) * MM
    y_first, y_last = (ch[0]["origin"][1] - oy) * MM, (ch[-1]["origin"][1] - oy) * MM
    asc, desc, adv = face(family, weight)
    em = size * MM
    track = round(((y_first - y_last) - chrome_extent(family, weight, size, s)) / (len(s) - 1) / em * 1000)
    run = chrome_extent(family, weight, size, s) + adv(s[-1]) * em + len(s) * track / 1000 * em
    lead = size * 1.45 * MM
    bh = round(lead + 0.4, 1)
    base_off = (lead - (asc + desc) * em) / 2 + asc * em - bh / 2
    cx, cy = bx_base - base_off, y_first - run / 2
    ink_ = [c for c in ch if c["c"].strip()]
    top = (ink_[-1]["origin"][1] - oy) * MM - adv(s[-1]) * em
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


def rule(pg, id, x, y, w, color=TAB, sw=0.21):
    """원본 선(획 굵기 0.6pt = 0.21mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


def frame(pg, id, x, y, w, h, stroke, sw, fill=None, label=None):
    """테두리 면 — 원본 사각형 경로(x, y, w, h mm) · 획 색 · 획 두께 pt(가운데 정렬 = 인디자인 기본)"""
    hw = sw * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2), "h": round(h + 2 * hw, 2),
                      "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30})
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "rect", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750}]
    st += [F('#side input[data-a="w"]', round(w, 2)), F('#side input[data-a="h"]', round(h, 2)),
           F('#side input[data-it="x"]', round(x, 2)), F('#side input[data-it="y"]', round(y, 2))]
    st.append(F('#side input[data-a="radius"]', 0))
    if fill:
        st += [{"pick": {"at": '#side select[data-a="fill"]', "value": "__raw"}, "wait": 650}, F('#side input[type="text"][data-a="fill"]', fill, 750)]
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', stroke, 750), F('#side input[data-a="stroke.w"]', sw)]
    return st


def dup(x, y, h=None, extra=()):
    """고른 개체 「⧉ 복제」 → 자리(·높이)만 새로"""
    st = [{"click": "#side #s-dup", "wait": 700}]
    if h is not None:
        st.append(F('#side input[data-a="h"]', h))
    st += list(extra)
    return st + [F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]


# ── 원본 쪽 읽기 ─────────────────────────────────────────
def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3])


def cols_of(pno):
    """단 왼쪽 끝 — 홀수 쪽(오른쪽 면) 21.5 / 108, 짝수 쪽 20 / 106"""
    return (21.5, 108.0) if pno % 2 else (20.0, 106.0)


def read_page(pno):
    """원본 쪽 본문 → 단마다 줄 목록. 줄 = {base, x0, x1, chars[(c, x, w_end, weight, size, ul)], num, size, y0, y1}.
    번호(12pt)와 발문(8pt)은 기준선이 0.55mm 달라 한 줄로 묶는다."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    uls = []                                                             # 밑줄 선 (x0, x1, y)
    rects = []                                                           # (종류, x, y, w, h)
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
    raw = []                                                             # 조각(span) 단위 — 합자(ffi)는 조각 안 순서를 지켜야 글이 바르다
    for b in p.get_text("rawdict")["blocks"]:
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
                     "wt": wt, "size": round(s["size"], 1), "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM,
                     "color": "#%06x" % s["color"]} for c in s["chars"]]})
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
        for ln in lines:
            ln["chars"] = [c for sp in sorted(ln["spans"], key=lambda sp: sp["x"]) for c in sp["chars"]]
        res = []
        for ln in lines:
            ch = ln["chars"]
            num = [c for c in ch if c["size"] == 12.0]
            body = [c for c in ch if c["size"] != 12.0]
            base = statistics.median(c["base"] for c in body) if body else num[0]["base"]
            for c in body:                                               # 밑줄 — 선 가운데가 기준선 아래 0.71mm
                c["ul"] = any(abs(u[2] - (c["base"] + 0.71)) < 0.3 and u[0] <= (c["x"] + c["x1"]) / 2 <= u[1] for u in uls)
            ink_ = [c for c in body if c["c"].strip()]
            res.append({"base": base, "num": num, "chars": body, "x0": ink_[0]["x"] if ink_ else None,
                        "x1": ink_[-1]["x1"] if ink_ else None, "size": statistics.mode(c["size"] for c in ink_) if ink_ else 12,
                        "y0": min(c["y0"] for c in ink_) if ink_ else None, "y1": max(c["y1"] for c in ink_) if ink_ else None,
                        "text": "".join(c["c"] for c in body)})
        out[ci] = res
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
        if c.get("ul"):
            j = k
            while j < len(chars) and chars[j].get("ul") and chars[j]["wt"] == c["wt"]:
                j += 1
            run = "".join(x["c"] for x in chars[k:j])
            out += ("{" if c["wt"] == 500 else "_{") + run + "}"
            k = j
        else:
            out += c["c"]
            k += 1
    return out


def groups(pno):
    """단마다 요소 묶음 — [{kind, lines, ...}] 읽는 순서. kind: num · prompt · bogi · passage · opts · condlabel · cond · answer"""
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
            elif dx < 0.3 and (t[:1] in CIRC or re.match(r"\d\)?\s", t)) and not (cur and cur["kind"] == "passage" and gap < 6):
                if not (cur and cur["kind"] == "opts" and gap < 7):
                    cur = {"kind": "opts", "lines": [], "left": left}
                    gs.append(cur)
                cur["lines"].append(ln)
                ln["para"] = True
            elif 2.5 < dx < 4.5 and cur and cur["kind"] == "opts":
                cur["lines"].append(ln)
            else:
                if not (cur and cur["kind"] == "passage" and gap < 6):
                    cur = {"kind": "passage", "lines": [], "left": left}
                    gs.append(cur)
                cur["lines"].append(ln)
            prev = ln
        res[ci] = [g for g in gs if g["lines"]]
    return res, rects, uls


def gtext(g):
    """묶음 → 원고 글. 줄은 낱말 사이 하나로 잇고, 문단(선지 하나 · 짧게 끝난 줄 뒤)은 줄바꿈."""
    ls = g["lines"]
    right = g["left"] + (COL_W - BOX_IN if g["kind"] in ("bogi", "cond") else COL_W)
    out = ""
    for k, ln in enumerate(ls):
        chars = ln["chars"]
        if g["kind"] == "prompt":
            chars = [c for c in chars if c["c"] != "\t"]
        t = marked(chars).strip()
        if k == 0:
            out = t
            continue
        if g["kind"] == "opts":
            brk = ln.get("para")
        else:
            brk = ls[k - 1]["x1"] < right - 3
        hang = lambda c: "\uac00" <= c <= "\ud7a3"
        out += "\n" if brk else "" if out and hang(out[-1]) and hang(t[:1] or " ") else " "      # 한글 낱말 안에서 꺾인 줄(「고르/시오」)은 붙인다
        out += t
    return out


def gaps_track(lines, size, weights=(400,)):
    """글자 간격 - 서체 폭 (‰ em) — 같은 줄 안 이웃 글자(공백 끼지 않은)"""
    _, _, adv = face(NOTO, 400)
    d = []
    for ln in lines:
        ch = [c for c in ln["chars"] if c["size"] == size and c["wt"] in weights]
        for a, b in zip(ch, ch[1:]):
            if a["c"] != " " and b["c"] != " " and a["c"] != "\t" and 0 < b["x"] - a["x"] < 3:
                d.append(((b["x"] - a["x"]) - adv(a["c"]) * size * MM) / (size * MM) * 1000)
    return d


def lead_of(g, default):
    """묶음 행간 pt — 같은 문단 안 기준선 간격의 가장 흔한 값"""
    ls = g["lines"]
    d = [round((b["base"] - a["base"]) / MM, 1) for a, b in zip(ls, ls[1:]) if not b.get("para")]
    return statistics.mode(d) if d else default


if os.environ.get("DUMP") and __name__ == "__main__":
    for pno in PAGES:
        gs, rects, _ = groups(pno)
        print("=== 쪽", pno, [r[:5] for r in rects])
        for ci in (0, 1):
            for g in gs[ci]:
                ls = g["lines"]
                print(f"  단{ci} {g['kind']:9s} b {ls[0]['base']:6.2f}~{ls[-1]['base']:6.2f} n{len(ls):2d} lead {lead_of(g, 0)} | "
                      f"{gtext(g)[:90]!r}")
    sys.exit()


# ── 쪽 만들기 ─────────────────────────────────────────────
TR_OPT = -50         # 선지 자간 — 원본 선지 끝 줄 글자 간격 3,747쌍이 모두 −50
TR_PAS = -50         # 지문·보기 자간 — 선지와 같은 −50
JC_PAS = -5          # 지문·보기 양끝맞춤 자간 최소(‰) — 원본 꽉 찬 줄 441개의 가장 좁은 글자 간격 −55.5 = −50 −5.5.
#                      편집기 컴포저로 57~65쪽 지문·보기 47개 줄 끝을 원본과 맞대 보니 (−50, −5) 가 35/47 로 가장 많다
#                      (−53·−3 은 29/47, 낱말 최소·최대·자간 최대를 바꿔도 35 를 못 넘는다 — 남은 12개는 컴포저가 꽉 맞는 줄을 피하는 것)
JC_OPT = 0           # 선지 양끝맞춤 자간 최소 — 원본 선지 끝 줄은 모두 −50 그대로(줄이지 않는다). 줄 끝 35/36 (−1 이면 34/36)
TR_COND = -40        # 조건 글 자간 — 원본 조건 끝 줄 글자 간격(한글·로마자 모두) −40
LEAD_P, LEAD_O, LEAD_C = 14, 12, 12      # 행간 pt — 지문·보기 4.94mm · 선지 4.23mm · 조건 4.23mm (원본 기준선 간격)
UL_W, UL_OFF = round(0.5 * MM, 3), 0.71  # 밑줄 선 0.5pt · 기준선 → 선 가운데 0.71mm (원본 밑줄 선 모두)
SLOTS = []                               # (쪽, y, x, 자리, 원고) — 편집기가 원고를 나눠 넣는 순서(쪽 → 위 → 왼쪽)대로 줄 세운다
TEMP_P = ("Temporary passage text for styling. The real passage comes later from outside, ①{marked words} keep the "
          "underline style, and this paragraph only keeps the shape of the content while the frame is still empty. ")
TEMP_Q = "다음 글을 읽고, 물음에 가장 {알맞은} 것을 고르시오."
TEMP_O = ("① Temporary choice text one\n② Temporary choice text two\n③ Temporary choice text three\n"
          "④ Temporary choice text four\n⑤ Temporary choice text five")
TEMP_B = "Temporary given sentence for the box. It shows the shape of the text that comes later."
TEMP_C = "1) 0단어로 빈칸을 완성하시오.\n2) 다음 단어를 한 번씩 사용하여 배열하시오.\nword / word / word / word"
TEMP_A = "주제문: ____________________."
SLOT_NAME = {"num": "문항번호", "prompt": "발문", "passage": "지문", "opts": "선지", "bogi": "보기", "cond": "조건", "answer": "답칸"}


def span_of(pno, t):
    """원본 쪽에서 글 조각 하나 — x = 첫 글자 원점, x1 = 끝 글자 끝, base, y0·y1 = 조각 상자 (지면 mm)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"][0] < 0.5:
                continue
            for s in l["spans"]:
                if "".join(c["c"] for c in s["chars"]).strip() == t:
                    ink_ = [c for c in s["chars"] if c["c"].strip()]
                    return {"x": (ink_[0]["origin"][0] - ox) * MM, "x1": (ink_[-1]["bbox"][2] - ox) * MM, "base": (s["origin"][1] - oy) * MM,
                            "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM, "color": "#%06x" % s["color"]}
    raise KeyError(t)


def ST(pg, pno, id, t, size, color, family, weight, **kw):
    """원본 조각 그대로 한 줄 고정 글"""
    s = span_of(pno, t)
    return T(pg, id, s["x"], s["base"], t, size, color, family, weight, (s["x"], s["y0"], s["x1"] - s["x"], s["y1"] - s["y0"]), **kw)


def header_right(pg, pno):
    st = [S("머리 — 크림 띠 · 선 · 꼬리표 · 큰 S", 1500)]
    st += B(pg, "band", -3, -3, 216, 26.5, CREAM)
    st += rule(pg, "rule", -3, 23.5, 216)
    ELEMS[pg].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
    st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
    st += ST(pg, pno, "tag-t", "STEP BY STEP", 6, WHITE, MS, 700, search=0.6, pad=0.3)   # 잴 창은 꼬리표 안만
    st += ST(pg, pno, "t-S", "S", 36, BRICK, MS, 500, label="큰 S")
    st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
    for k, fill in enumerate(("#e1eaf3", "#f9efda", BRICK)):
        st += B(pg, f"tab{k + 1}", 201.5, 60 + 30 * k, 11.5, 26, fill)
    for k, (s, col) in enumerate((("01", BLUE), ("02", "#cba56f"), ("STEP 03", WHITE))):
        st += R(pg, f"tab{k + 1}-t", pno, s, col)
    return st


def header_left(pg, pno):
    st = [S("머리 — 크림 띠 · 선 · 벽돌색 막대", 1500)]
    st += B(pg, "band", -3, -3, 216, 26.5, CREAM)
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.25, -3, 2.2, 26.61, BRICK)
    s0, s1 = span_of(pno, "STEP"), span_of(pno, "03")
    st += T(pg, "t-step", s0["x"], s0["base"], "STEP 03", 8, BRICK, NOTO, 400, (s0["x"], s0["y0"], s1["x1"] - s0["x"], s0["y1"] - s0["y0"]),
            label="STEP 03 · TEST")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += ST(pg, pno, "t-test", "TEST", 8, TAB, NOTO, 700)
    st += ST(pg, pno, "t-S", "S", 25, BRICK, MAMA, 400, label="제목 — S · 실전 문제")
    st += ST(pg, pno, "t-title", "실전 문제", 13, INK, GM, 500)
    st += [S("단계 점 셋 — 원 · 선 · 숫자 (3 이 찬 원)", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, stroke=TAB, sw=0.79)                # 원본 획 0.8pt
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke=TAB, sw=0.79)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, fill=BRICK)
    for k, col in enumerate((TAB, TAB, WHITE)):
        s = span_of(pno, str(k + 1))
        st += T(pg, f"n{k + 1}", s["x"], s["base"], str(k + 1), 6, col, MS, 700, (s["x"], 14.22, s["x1"] - s["x"], 2.84), search=0.6, pad=0.3)
    return st


def footer(pg, pno):
    st = [S("꼬리 — 쪽번호", 1200)]
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = "".join(c["c"] for c in s["chars"]).strip()
                if t and round(s["size"], 1) == 6.0 and (s["origin"][1] - oy) * MM > 280:
                    ink_ = [c for c in s["chars"] if c["c"].strip()]
                    x, x1 = (ink_[0]["origin"][0] - ox) * MM, (ink_[-1]["bbox"][2] - ox) * MM
                    st += T(pg, "f-no" if t.isdigit() else "f-t", x, (s["origin"][1] - oy) * MM, t, 6, "#%06x" % s["color"], EL, 700,
                            (x, 283.62, x1 - x, 2.62), search=0.6)
    return st


def wbox(track, inner=COL_W):
    return round(inner + track / 1000 * 8 * MM, 2)        # Chrome 은 줄 끝 글자 뒤에도 자간을 둔다 — 그만큼 좁게


def measure_text(pg, id, g, x0, x1):
    """잴 요소 — 원본 쪽에서 그 묶음의 먹색 잉크 상자"""
    b0, b1 = g["lines"][0]["base"], g["lines"][-1]["base"]
    bb = ink(pg, INK, x0, b0 - 3.4, x1 - x0, b1 - b0 + 3.4 + 1.2)
    e = {"id": id, "x": bb[0], "y": bb[1], "w": bb[2], "h": bb[3], "color": INK, "see": INK, "ctol": 40, "search": 1.0, "pad": 0.6,
         "text": gtext(g)[:30], "size": 8}
    if len(g["lines"]) > 1:
        e["shape_iou"] = 0.80          # 문단은 양끝맞춤에서 단어가 0.2mm 안팎 다르게 놓인다 — 겹침 기준을 낮춘다(02B~07 과 같다)
    ELEMS[pg].append(e)


def story_chains():
    """단·쪽을 넘어 이어지는 글 — 단 맨 위 묶음이 번호 없이 시작하고(지문·선지), 바로 앞 단의 끝 묶음이 같은 종류면 한 글이 이어진 것.
    → {(쪽, 단): {"head"|"cont": 이야기 이름}} · 이름은 편집기가 「＋ 새 이야기」로 매기는 차례(이야기1, 2 …) 그대로.
    57쪽 왼쪽 위 38번 지문 끝은 첫 상자가 56쪽(단위 14a)에 있어 이 문서에선 잇지 않고 따로 자리로 둔다."""
    cols = [(pno, ci) for pno in PAGES for ci in (0, 1)]
    out, n = {}, 0
    for (pa, ca), (pb, cb) in zip(cols, cols[1:]):
        ga, gb = groups(pa)[0][ca], groups(pb)[0][cb]
        if ga and gb and gb[0]["kind"] in ("passage", "opts") and ga[-1]["kind"] == gb[0]["kind"]:
            n += 1
            out.setdefault((pa, ca), {})["head"] = f"이야기{n}"
            out.setdefault((pb, cb), {})["cont"] = f"이야기{n}"
    return out


def build_page(pg, pno):
    """원본 쪽 → 그릴 것 목록(단마다 읽는 순서). 자리 글상자 높이는 같은 단 다음 요소 위 끝까지."""
    gs, rects, _ = groups(pno)
    specs = []
    for ci in (0, 1):
        col = []
        for g in gs[ci]:
            k, ls = g["kind"], g["lines"]
            L = g["left"]
            b0 = ls[0]["base"]
            tag = f"{ci}{len(col)}"
            if k == "num":
                num = [c for c in ls[0]["num"] if c["c"].strip()]
                s = "".join(c["c"] for c in num)
                x = num[0]["x"]
                bb = ink(pg, NUMC, x - 0.4, num[0]["base"] - 3.6, 7.5, 4.2)
                col.append({"kind": k, "x": x, "y": top_of(num[0]["base"], 12, EL, 700), "value": s, "base": num[0]["base"], "bb": bb})
            elif k == "prompt":
                first = next(c for c in ls[0]["chars"] if c["c"].strip())
                tr = TR_Q
                col.append({"kind": k, "x": L, "y": top_of(b0, 8, NOTO, 400, LEAD_Q), "value": gtext(g), "n": len(ls), "lead": LEAD_Q,
                            "ind": round(first["x"] - L, 2), "tr": tr})
                measure_text(pg, "q" + tag, g, L - 0.5, L + COL_W + 0.5)
            elif k in ("passage", "opts"):
                lead = LEAD_P if k == "passage" else LEAD_O
                sp = {"kind": k, "x": L, "y": top_of(b0, 8, NOTO, 400, lead), "value": gtext(g), "n": len(ls), "lead": lead}
                ch = CHAINS.get((pno, ci), {})
                if g is gs[ci][-1] and "head" in ch:                 # 글 잇기 첫 상자 — 원고는 이어지는 상자 몫까지 하나로
                    pn, cn = (pno, 1) if ci == 0 else (pno + 1, 0)
                    nxt_g = groups(pn)[0][cn][0]
                    sp["head"] = ch["head"]
                    sp["value"] += ("\n" if nxt_g["lines"][0].get("para") else " ") + gtext(nxt_g)
                    gaps = sum(1 for ln in ls[1:] if ln.get("para")) * (OPT_GAP if k == "opts" else 0)
                    sp["fixh"] = round(len(ls) * lead * MM + gaps + 0.5 * lead * MM, 2)   # 원본 줄 수만 담고 다음 줄은 넘쳐 다음 상자로
                if g is gs[ci][0] and "cont" in ch:
                    sp["cont"] = ch["cont"]                           # 이어지는 상자 — 자리가 아니다(원고는 첫 상자에)
                col.append(sp)
                measure_text(pg, k[0] + tag, g, L - 0.5, L + COL_W + 0.5)
            elif k == "bogi":
                r = g["rect"]
                col.append({"kind": "bogirect", "x": r[1], "y": r[2], "w": r[3], "h": r[4]})
                col.append({"kind": k, "x": r[1] + BOX_IN, "y": top_of(b0, 8, NOTO, 400, LEAD_P), "value": gtext(g), "n": len(ls), "lead": LEAD_P})
                measure_text(pg, "b" + tag, g, r[1] + 1, r[1] + r[3] - 1)
            elif k == "condlabel":
                r = g["rect"]
                col.append({"kind": "condrect", "x": r[1], "y": r[2], "w": r[3], "h": r[4], "sw": r[6]})
                first = [c for c in ls[0]["chars"] if c["c"].strip()]
                col.append({"kind": k, "x": first[0]["x"], "y": top_of(b0, 9.5, NOTO, 500), "base": b0,
                            "bb": (first[0]["x"], min(c["y0"] for c in first), first[-1]["x1"] - first[0]["x"],
                                   max(c["y1"] for c in first) - min(c["y0"] for c in first))})
            elif k == "cond":
                r = g["rect"]
                col.append({"kind": k, "x": r[1] + BOX_IN, "y": top_of(b0, 8, NOTO, 400, LEAD_C), "value": gtext(g), "n": len(ls), "lead": LEAD_C})
                measure_text(pg, "c" + tag, g, r[1] + 1, r[1] + r[3] - 1)
            elif k == "answer":
                col.append({"kind": k, "x": ls[0]["x0"], "y": top_of(b0, 8, NOTO, 400), "value": gtext(g), "n": 1, "lead": 8 * 1.45, "base": b0})
                # 잴 요소 둘 — 「주제문:」 글(모양까지)과 밑줄 문자 줄(자리·크기만). 밑줄 문자는 2화소 높이라 1화소 어긋남에 잉크 양이 크게 흔들린다
                u0 = next(c["x"] for c in ls[0]["chars"] if c["c"] == "_")
                measure_text(pg, "a" + tag, g, L - 0.5, u0 - 0.3)
                ELEMS[pg][-1].update(search=0.2, pad=0.2)                     # 창이 밑줄 문자에 닿지 않게
                bb = ink(pg, INK, u0 - 0.3, b0 - 0.5, L + COL_W - u0, 1.5)
                ELEMS[pg].append({"id": "u" + tag, "x": bb[0], "y": bb[1], "w": bb[2], "h": bb[3], "color": INK, "see": INK, "ctol": 40,
                                  "search": 0.6, "pad": 0.3})
        for i, sp in enumerate(col):
            if "value" in sp and sp["kind"] != "num":
                nxt = next((o["y"] for o in col[i + 1:] if o["y"] > sp["y"] + 1 and o["kind"] != "num"), BODY_BOTTOM)
                need = max(sp["n"] * sp["lead"] * MM, need_h(sp)) + 0.5            # 편집기가 원고 길이로 어림한 높이보다 낮으면 자라서 아래를 민다
                sp["h"] = round(max(need, nxt - sp["y"] - 0.2), 1)
                if sp.get("fixh"):
                    sp["h"] = sp["fixh"]
        specs += col
    for sp in specs:
        if "value" in sp and not sp.get("cont"):
            SLOTS.append((pg, round(sp["y"], 2), round(sp["x"], 2), SLOT_NAME[sp["kind"]], sp["value"]))
    return specs


def story_steps(specs):
    """글 잇기 — 첫 상자: 누르고 「이야기」 칸에서 ＋ 새 이야기 · 이어지는 상자: 누르고 같은 이야기를 고른다(순서는 편집기가 다음 번호로)"""
    st = []
    for sp in specs:
        role = "head" if sp.get("head") else "cont" if sp.get("cont") else None
        if not role:
            continue
        name = sp[role]
        at = [round(sp["x"] + 30, 2), round(sp["y"] + 2.0, 2)]               # 첫 줄 가운데 — 다른 상자와 안 겹치는 자리
        st += [S(f"글 잇기 — {name} {'첫 상자' if role == 'head' else '이어지는 상자'}", 1500), {"click": {"mm": at}, "wait": 800},
               {"js": f"(() => {{ const it = page.items[sel]; if (!it || !it.atom || Math.abs(it.y - {round(sp['y'], 2)}) > 0.05) "
                      f"throw new Error('잇기 — 엉뚱한 상자를 골랐다 ' + (it && it.y)); return '고름 y ' + it.y; }})()"},
               {"pick": {"at": '#side select[data-a="story"]', "value": "__new" if role == "head" else name}, "wait": 1200},
               {"js": f"(() => {{ const a = page.items[sel].atom; if (a.story !== {name!r} || (+a.story_seq || 1) !== {1 if role == 'head' else 2}) "
                      f"throw new Error('잇기 실패 ' + a.story + ' ' + a.story_seq); return a.story + ' · ' + (a.story_seq || 1); }})()"}]
    return st


def need_h(sp):
    """편집기(render.text_h)가 원고 글로 어림하는 글상자 높이 — 이보다 낮게 그리면 원고를 넣을 때 자라며 아래 요소를 민다"""
    from core.units import render
    k = sp["kind"]
    a = {"tracking": sp.get("tr", {"cond": TR_COND, "opts": TR_OPT}.get(k, TR_PAS))}
    w = wbox(a["tracking"], COL_W - 2 * BOX_IN if k in ("bogi", "cond") else COL_W)
    if k == "opts":
        a.update(indent=OPT_IND, indent_first=-OPT_IND, space_after=OPT_GAP)
    if k == "prompt":
        a["indent_first"] = sp["ind"]                                # 편집기 어림은 첫 줄 들여쓰기도 센다(fd881cde)
    return render.text_h(sp["value"], w, 8, sp["lead"], a)


def jc4(letter_min):
    """양끝 정렬 「균등 배치」 네 칸을 모두 친다 — 빈 칸은 편집기 기본(인디자인 공장값 80·133·0, 6ee0b6f2)이 되니까.
    낱말 100~133%(원본 줄 441개: 낱말은 100% 아래로 안 간다) · 자간 최소(지문 −5 / 선지 0, 원본 실측) · 자간 최대 250"""
    return [S(f"양끝 정렬 — 낱말 100~133% · 자간 {letter_min}~250‰", 900),
            F('#side input[data-a="jc.word_min"]', 100, 500), F('#side input[data-a="jc.word_max"]', 133, 500),
            F('#side input[data-a="jc.letter_min"]', letter_min, 500), F('#side input[data-a="jc.letter_max"]', 250, 500)]


def texts(sps, name, temp, w, lead, track, align, extra=None):
    """자리 글상자 한 종류 — 첫 상자: 임시 글 · 자리 이름 · 스타일, 나머지: 복제 후 자리·높이"""
    st = []
    for i, sp in enumerate(sps):
        if i == 0:
            st += [S(f"{name} — 임시 글 · 자리 · 스타일, 나머지는 복제", 1500)]
            st += text(round(sp["x"], 2), round(sp["y"], 2), w, sp["h"], temp, 8, INK, label=f"{name} 자리 — 임시 글", leading=lead, align=align,
                       font=NOTO, track=track)
            st += slot(name, label=f"자리 이름 「{name}」")
            if align == "justify":
                st += jc4(JC_OPT if name == "선지" else JC_PAS)
            if extra:
                st += extra()
        else:
            st += dup(round(sp["x"], 2), round(sp["y"], 2), sp["h"])
    return st


def body(pg, pno, specs):
    st = []
    by = lambda k: [sp for sp in specs if sp["kind"] == k]
    for i, sp in enumerate(by("num")):                                   # 문항 번호 — 엘리스 굵게 12pt 파랑
        if i == 0:
            st += [S("문항 번호 — 첫 번호를 그리고 복제", 1500)]
            st += T(pg, f"no{sp['value']}", sp["x"], sp["base"], sp["value"], 12, NUMC, EL, 700, sp["bb"], search=0.8, pad=0.6,
                    temp="00", label="문항 번호 자리")
            st += slot("문항번호")
        else:
            bb = sp["bb"]
            ELEMS[pg].append({"id": f"no{sp['value']}", "x": bb[0], "y": bb[1], "w": bb[2], "h": bb[3], "color": NUMC, "see": NUMC,
                              "ctol": 30, "search": 0.8, "pad": 0.6, "text": sp["value"], "size": 12})
            st += dup(round(sp["x"], 2), round(sp["y"], 2))
    ind0 = tr0 = None
    for i, sp in enumerate(by("prompt")):                                # 발문 — 첫 줄은 번호 뒤(첫 줄 들여), 둘째 줄은 단 왼쪽부터
        if i == 0:
            st += [S("발문 — 임시 글 · 자리 · 스타일(첫 줄 들여 · 양끝맞춤) · GREP 둘(밑줄 · Medium 밑줄)", 1700)]
            st += text(round(sp["x"], 2), round(sp["y"], 2), wbox(sp["tr"]), sp["h"], TEMP_Q, 8, INK, label="발문 자리 — 임시 글", leading=LEAD_Q,
                       align="justify", font=NOTO, track=sp["tr"], tsume=Q_TSUME)
            st += slot("발문", label="자리 이름 「발문」")
            st += jc4(JC_PAS)
            st.append(F('#side input[data-a="indent_first"]', sp["ind"]))
            st += grep(0, r"_\{(.+?)\}", bold=False, underline=True, line=UL_W, line_off=UL_OFF, hide=True,
                       label="GREP — 약속 괄호 _{ } 는 감추고 밑줄만")
            st += grep(1, r"\{(.+?)\}", bold=False, weight=500, underline=True, line=UL_W, line_off=UL_OFF, hide=True,
                       label="GREP — 약속 괄호 { } 는 감추고 Medium + 밑줄")
        else:
            ex = [F('#side input[data-a="indent_first"]', sp["ind"])] if sp["ind"] != ind0 else []
            ex += [F('#side input[data-a="tracking"]', sp["tr"]), F('#side input[data-it="w"]', wbox(sp["tr"]))] if sp["tr"] != tr0 else []
            st += dup(round(sp["x"], 2), round(sp["y"], 2), sp["h"], extra=ex)
        ind0, tr0 = sp["ind"], sp["tr"]
    for i, sp in enumerate(by("bogirect")):                              # 보기 상자 — 연두빛 바탕
        if i == 0:
            st += B(pg, f"bogi{i}", round(sp["x"], 2), round(sp["y"], 2), round(sp["w"], 2), round(sp["h"], 2), BOGIF, label="보기 상자 — 바탕")
        else:
            ELEMS[pg].append({"id": f"bogi{i}", "x": sp["x"], "y": sp["y"], "w": sp["w"], "h": sp["h"], "color": BOGIF, "see": BOGIF, "pad": 0.6, "ctol": 30})
            st += dup(round(sp["x"], 2), round(sp["y"], 2), round(sp["h"], 2))
    st += texts(by("bogi"), "보기", TEMP_B, wbox(TR_PAS, COL_W - 2 * BOX_IN), LEAD_P, TR_PAS, "justify",
                )
    st += texts(by("passage"), "지문", TEMP_P, wbox(TR_PAS), LEAD_P, TR_PAS, "justify", extra=lambda: (   # 지문 — 양끝맞춤 행간 14pt
        grep(0, r"\{(.+?)\}", bold=False, weight=500, underline=True, line=UL_W, line_off=UL_OFF, hide=True,
             label="GREP — 약속 괄호 { } 는 감추고 Medium + 밑줄")
        + grep(1, r"\([A-E]\)(?= )", bold=False, weight=500, label="GREP — 문단 머리 (A) (B) (C) 는 Medium")))
    st += texts(by("opts"), "선지", TEMP_O, wbox(TR_OPT), LEAD_O, TR_OPT, "justify", extra=lambda: [       # 선지·진술 — 내어쓰기 · 문단 뒤 간격
        F('#side input[data-a="indent"]', OPT_IND), F('#side input[data-a="indent_first"]', -OPT_IND), F('#side input[data-a="space_after"]', OPT_GAP)])
    for i, sp in enumerate(by("condrect")):                              # 조건 상자 — 하늘색 바탕 · 테두리
        if i == 0:
            st += frame(pg, f"cond{i}", sp["x"], sp["y"], sp["w"], sp["h"], CONDS, sp["sw"], fill=CONDF, label="조건 상자 — 하늘색 바탕 · 테두리 0.5pt")
        else:
            hw = sp["sw"] * MM / 2
            ELEMS[pg].append({"id": f"cond{i}", "x": round(sp["x"] - hw, 2), "y": round(sp["y"] - hw, 2), "w": round(sp["w"] + 2 * hw, 2),
                              "h": round(sp["h"] + 2 * hw, 2), "color": CONDS, "see": CONDS, "pad": 0.3, "ctol": 30})
            st += dup(round(sp["x"], 2), round(sp["y"], 2), round(sp["h"], 2))
    for i, sp in enumerate(by("condlabel")):                             # [조건] — 상자마다 같은 고정 글
        if i == 0:
            st += T(pg, f"cl{i}", sp["x"], sp["base"], "[조건]", 9.5, INK, NOTO, 500, sp["bb"], search=0.6, pad=0.6, label="[조건] — 고정 글")
        else:
            bb = sp["bb"]
            ELEMS[pg].append({"id": f"cl{i}", "x": bb[0], "y": bb[1], "w": bb[2], "h": bb[3], "color": INK, "see": INK, "ctol": 30,
                              "search": 0.6, "pad": 0.6, "text": "[조건]", "size": 9.5})
            st += dup(round(sp["x"], 2), round(sp["y"], 2))
    st += texts(by("cond"), "조건", TEMP_C, wbox(TR_COND, COL_W - 2 * BOX_IN), LEAD_C, TR_COND, "justify")    # 조건 글도 양끝맞춤(원본 꽉 찬 줄 낱말 사이가 넓다)
    st += texts(by("answer"), "답칸", TEMP_A, wbox(TR_A), None, TR_A, None)
    return st


def track_med(kind, size=8.0, short_only=True, weights=(400,)):
    """그 종류 글의 자간 — 원본 끝 줄(양끝맞춤이 안 건드린 줄) 글자 간격 - 서체 폭의 중앙값(5 단위)"""
    v = []
    for pno in PAGES:
        gs, _, _ = groups(pno)
        for ci in (0, 1):
            for g in gs[ci]:
                if g["kind"] != kind:
                    continue
                right = g["left"] + (COL_W - BOX_IN if kind in ("bogi", "cond") else COL_W)
                v += gaps_track([ln for ln in g["lines"] if not short_only or ln["x1"] < right - 3], size, weights)
    return round(statistics.median(v) / 5) * 5 if v else 0


def opts_metrics():
    """선지 — 문단 뒤 간격(mm) = 원본 선지 첫 줄 기준선 간격 - 행간 · 내어쓰기 = 둘째 줄 시작 - 단 왼쪽"""
    gap, ind = [], []
    for pno in PAGES:
        gs, _, _ = groups(pno)
        for ci in (0, 1):
            for g in gs[ci]:
                if g["kind"] == "opts":
                    gap += [b["base"] - a["base"] - LEAD_O * MM for a, b in zip(g["lines"], g["lines"][1:]) if b.get("para")]
                    ind += [ln["x0"] - g["left"] for ln in g["lines"] if not ln.get("para")]
    return round(statistics.median(gap), 2), round(statistics.median(ind), 2)


LEAD_Q = 14.6        # 발문 행간 — 둘째 줄 기준선 간격 5.15mm (58·59·60쪽 발문 넷)
TR_Q, Q_TSUME = -40, 40   # 발문 — 원본 글자 쌍마다 간격 = 자간 −40‰ − 0.4 × (앞 글자 오른쪽 + 뒤 글자 왼쪽 빈 곳): 인디자인 「자간 축소」 40% (2026-10-09, 2,384쌍 3‰ 안)
TR_A = track_med("answer")
OPT_GAP, OPT_IND = opts_metrics()
CHAINS = story_chains()

if __name__ == "__main__":
    print("자간 발문", TR_Q, "답칸", TR_A, "· 선지 문단 뒤", OPT_GAP, "mm 내어쓰기", OPT_IND, "mm")
    st = open_doc("스텝바이스텝 워크북 S 실전문제 57~65 (A4)")
    st += expect_pages(1)
    for k, pno in enumerate(PAGES):
        pg = k + 1
        if k:
            st += add_page(f"{pno}쪽 — 새 쪽")
            st += [{"js": f"(() => {{ const k = docPages().length; if (k !== {pg}) throw new Error('쪽 수가 {pg} 이 아니라 ' + k); return '쪽 {pg} 확인'; }})()", "wait": 300}]
        st += [S(f"{pno}쪽 — S 실전 문제", 1500)]
        specs = build_page(pg, pno)
        st += header_right(pg, pno) if pno % 2 else header_left(pg, pno)
        st += body(pg, pno, specs)
        st += story_steps(specs)
        st += footer(pg, pno)
        st += done(f"{pno}쪽", f"p{pg}.png")
    CONTENT = {}
    for pg, y, x, name, val in sorted(SLOTS, key=lambda t: (t[0], round(t[1], 1), t[2])):
        CONTENT.setdefault(name, []).append(val)
    small_draw(st)
    st += put_content(CONTENT)                                           # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
    st += [{"shot": "p_content.png", "wait": 800}]
    json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("14b 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
