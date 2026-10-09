"""단위 14c S실전문제 (뒤 9면) — 원본 d1 reference.pdf 66~74쪽을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
14-S실전문제는 27면(48~74)이라 셋으로 나눠 동시에 한다 — 이 단위는 66~74(문항 79~112 + 판권 면).

면 구조 (원본 PDF 에서 읽은 것):
  왼쪽 면(66·68·70·72) 머리 — 크림 띠·선·벽돌 막대·STEP 03 TEST·S 실전 문제·단계 점(3이 찬 원)
  오른쪽 면(67·69·71·73) 머리 — 크림 띠·선·꼬리표·큰 S·옆 탭 셋(STEP 03 이 벽돌)
  두 단(왼쪽 면 20·106mm, 오른쪽 면 21.5·108mm, 폭 82mm)에 문항이 흐른다. 문항마다:
    번호(엘리스 DX널리 Bold 12pt 파랑) · 발문(본고딕 8pt, 첫 줄은 번호 뒤 탭 자리부터, 둘째 줄은 단 왼쪽부터)
    지문(본고딕 8pt 행간 14pt 양끝, 자간 -50) · 선지(행간 12pt · 단락 뒤 1mm · 내어쓰기 3.5mm)
    부속 — 조건 상자(하늘 면 + 테두리, 제목 「< 조건>」/「[조건]」 + 조건 줄) · 요약문 상자 · 주어진 글 상자(연한 면)
  74쪽 — 판권 면(바탕·막대·꼬리표·STEP BY STEP·교재명·만든 사람·색 띠 셋·로고·COPYRIGHT)

자리 이름 — 블록 지도 B6 문항(발문·지문·선지·부속) 기준:
  문항번호 · 발문 · 지문 · 선지 · 조건 · 요약문 · 주어진글 · (판권) 교재명 · 집필 · 검토 · 보조 · 디자인 · 제작
원고 약속 표시(원고자리_규약 「강조·선택 표시는 약속한 꼴로」):
  {…} = 밑줄 칠 곳(원본 0.5pt 선). 지문에서는 Medium + 밑줄, 발문에서는 밑줄만(「않은」 은 GREP 로 Medium).
  [ … / … ] = 어법 고르기(Medium) · (A)(B)(C) = 배열 문단 머리(Medium) — 원고 글 그대로, GREP 이 꼴을 찾는다.
같은 종류 글상자는 쪽마다 첫 상자만 그려 스타일을 매기고 나머지는 「⧉ 복제」 후 자리·높이만(인디자인에서 복제하듯).
값은 모두 원본 PDF 에서 — 기준선·글자 위치·선·상자 좌표. 측정 보정(보정.json) 없음.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from mkpage import *                                                    # noqa
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
ELEMS = {k + 1: [] for k in range(len(PAGES))}
MM = 25.4 / 72
NOTO, MS, EL, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
SDG = "Apple SD Gothic Neo"
INK, BRICK, QBLUE = "#231f20", "#bc736c", "#00559f"
COND_FILL, SOFT_FILL = "#dbecf2", "#f9fcf3"
TRACK = -50            # 본문 자간 — 원본 8pt 글자 간격 - 서체 폭(공백 제외): 줄이지 않은 줄 2967쌍 중앙값 -50.0 (scratch stats2)
                       # 낱말 사이는 따로 안 준다 — 원본 공백(줄이지 않은 줄) 230‰ = 크롬 한국어 꼴 공백 280 + 자간 -50
LEAD_P, LEAD_O, LEAD_Q = 14, 12, 14.6   # 지문·요약·주어진 글 4.94mm · 선지·조건 4.23mm · 발문 두 줄 5.15mm
O_GAP = 1.0            # 선지 단락 뒤 간격 — 선지 사이 5.23mm - 행간 4.23mm
O_HANG = 3.5           # 선지 둘째 줄 — 23.5 / 첫 줄 20.0
UL_W = round(0.5 * MM, 3)                                                   # 밑줄 획 0.5pt
CIRC = "①②③④⑤"
JC = (100, 133, -5, 250)  # 양끝맞춤 글상자마다 균등 배치 네 칸 — 낱말 최소·최대 % · 자간 최소·최대 ‰ (2026-10-09 편집기 기본이 인디자인 공장값 80·133·0 으로
                          # 바뀐 뒤 이 책 값은 글상자 칸으로). 지문 자간 최소 -5 와 -2 를 렌더러로 그려 원본 줄 끝과 맞대면 다른 줄 41 대 65/635 → -5
US_TRACK = -36         # 밑줄 문자 _ 사이 — 원본 100쌍 모두 원점 간격 - 서체 폭 = -36‰ (다른 글자는 -50). 서체 kern·locl 로는 안 나온다 → GREP 자간
C_TRACK = -40          # 조건 줄 자간 — 원본 조건 줄(66·68쪽) 모두 -40.0 (크롬 글 폭과 원본 첫~끝 글자 거리로)


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


def hangul(s):
    return any(0xAC00 <= ord(c) <= 0xD7A3 for c in s)


# ── 원본 읽기 ─────────────────────────────────────────────
def spans(pno):
    """원본 쪽의 글 조각 — 지면 mm. x = 첫 글자(공백 아닌) 원점, x0/x1 = 첫·끝 글자 상자, y0/y1 = 조각 상자(서체 위아래)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out = []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                ch = s["chars"]
                ink = [c for c in ch if c["c"].strip()]
                if not ink:
                    continue
                out.append({"t": "".join(c["c"] for c in ch), "font": s["font"], "size": round(s["size"], 1), "color": "#%06x" % s["color"],
                            "base": (s["origin"][1] - oy) * MM, "x": (ink[0]["origin"][0] - ox) * MM,
                            "x0": (ink[0]["bbox"][0] - ox) * MM, "x1": (ink[-1]["bbox"][2] - ox) * MM,
                            "y0": (s["bbox"][1] - oy) * MM, "y1": (s["bbox"][3] - oy) * MM, "rot": l["dir"] != (1.0, 0.0),
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["bbox"][0] - ox) * MM, (c["bbox"][2] - ox) * MM) for c in ch]})
    return out


def draws(pno):
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    return [dict(dr, mm=[(dr["rect"].x0 - ox) * MM, (dr["rect"].y0 - oy) * MM, dr["rect"].width * MM, dr["rect"].height * MM])
            for dr in p.get_drawings()]


def bbox_of(s, tight=False):
    """잴 창. tight — 기준선에서 위 0.95em · 아래 0.32em(밑줄 포함): 본고딕 CJK·애플 산돌고딕은 조각 상자(서체 윗·아랫높이)가
    2.85em 이라 위아래 줄까지 덮어 옆 줄 잉크를 같이 쟀다(판 2 의 조건 제목·이름 끝 줄·지문 위 끝)."""
    if tight:
        em = s["size"] * MM
        return (round(s["x0"], 2), round(s["base"] - 0.95 * em, 2), round(s["x1"] - s["x0"], 2), round(1.27 * em, 2))
    return (round(s["x0"], 2), round(s["y0"], 2), round(s["x1"] - s["x0"], 2), round(s["y1"] - s["y0"], 2))


def rows(pno):
    """본문 글줄 — 단(0 왼쪽 · 1 오른쪽)마다 기준선이 같은 조각을 한 줄로"""
    sp = [s for s in spans(pno) if not s["rot"] and 25 < s["base"] < 280 and s["x"] < 196]
    out = []
    for s in sorted(sp, key=lambda s: (s["base"], s["x"])):
        col = 0 if s["x"] < 104.5 else 1
        r = next((r for r in out if r["col"] == col and abs(r["base"] - s["base"]) < 0.3), None)
        if r is None:
            r = {"col": col, "base": s["base"], "spans": []}
            out.append(r)
        r["spans"].append(s)
    for r in out:
        r["spans"].sort(key=lambda s: s["x"])
        r["x"] = r["spans"][0]["x"]
        r["x0"] = r["spans"][0]["x0"]
        r["x1"] = max(s["x1"] for s in r["spans"])
        em = max(s["size"] for s in r["spans"]) * MM                   # 잴 창 — 기준선 위 0.95em · 아래 0.32em (bbox_of tight 와 같다)
        r["y0"] = r["base"] - 0.95 * em
        r["y1"] = r["base"] + 0.32 * em
        r["text"] = "".join(s["t"] for s in r["spans"])
    return out


def marked_text(pno, rr, hang=False, para_start=None):
    """줄들을 원고 글로 — 원본 밑줄(0.5pt 선, 기준선 0.7mm 아래)이 덮는 글자는 {…} 로 감싼다(약속 괄호).
    영어 줄은 줄 끝 공백 하나로 잇고, 한글 줄(발문)은 그대로 잇는다(원본은 낱말 가운데서도 꺾고 낱말 끝이면 공백을 남긴다).
    para_start(줄) 이 참이면 그 줄 앞에서 새 문단(\\n)."""
    uls = [d for d in draws(pno) if d["type"] == "s" and d["items"][0][0] == "l" and d["mm"][3] < 0.01 and d["width"] < 1.6
           and hexc(d["color"]) == INK]
    pieces = []                                                         # (글, 밑줄?) — 줄 사이엔 ("J", None) 이음표
    for k, r in enumerate(rr):
        if k:
            if para_start and para_start(r):
                pieces.append(("\n", None))
            elif hang:
                pieces.append(("", None))
            else:
                pieces.append(("J", None))
        lines = [d for d in uls if 0.4 < d["mm"][1] - r["base"] < 1.0]
        for s in r["spans"]:
            for c, ox_, bx0, bx1 in s["chars"]:
                cx = (bx0 + bx1) / 2
                m = c.strip() != "" and any(d["mm"][0] - 0.05 <= cx <= d["mm"][0] + d["mm"][2] + 0.05 for d in lines)
                m = m or (c == " " and any(d["mm"][0] < bx0 and bx1 < d["mm"][0] + d["mm"][2] for d in lines))
                if pieces and pieces[-1][1] is m and pieces[-1][0] not in ("J", "\n", ""):
                    pieces[-1] = (pieces[-1][0] + c, m)
                else:
                    pieces.append((c, m))
    # 줄 끝 공백 · 이음표 정리
    out = []
    for i, (t, m) in enumerate(pieces):
        if m is None:
            gap = ""                                                    # 줄 끝 공백(밑줄 밖)
            while out and not out[-1][1] and not out[-1][0].strip(" "):
                gap = out.pop()[0] + gap
            if out and not out[-1][1] and out[-1][0].endswith(" "):
                gap = out[-1][0][len(out[-1][0].rstrip(" ")):] + gap
                out[-1] = (out[-1][0].rstrip(" "), False)
            nxt = pieces[i + 1] if i + 1 < len(pieces) else None
            prev_c = next((ch for p_ in reversed(out) for ch in reversed(p_[0]) if ch.strip()), "")
            join = {"J": "" if (not gap and prev_c in CIRC) else " ", "\n": "\n", "": gap}[t]
            # 영어 줄 사이는 공백 하나 — 원본은 원문자 「③」 바로 뒤에서도 꺾는다(공백 없이 「③shouting」). 줄 끝 공백이 따로 조각이면
            # 읽히지 않으니(「[that / if]」 뒤) 공백 유무 대신 원문자인지로 가른다. 한글 줄(발문)은 원본 공백 그대로.
            if out and out[-1][1] and nxt and nxt[1] and t != "\n":      # 밑줄이 줄을 넘어 이어진다 — 한 괄호로
                out[-1] = (out[-1][0].rstrip(" ") + (join if join.strip() == "" and join else ""), True)
                continue
            if join:
                out.append((join, False))
            continue
        if out and out[-1][1] is m:
            out[-1] = (out[-1][0] + t, m)
        else:
            out.append((t, m))
    txt = ""
    for t, m in out:
        if m:
            a, b = len(t) - len(t.lstrip(" ")), len(t) - len(t.rstrip(" "))
            txt += t[:a] + "{" + t.strip(" ") + "}" + (t[len(t) - b:] if b else "")
        else:
            txt += t
    return txt.strip(" ")


def boxes(pno):
    """상자 — 조건(하늘 면 + 테두리) · 연한 면(요약문·주어진 글)"""
    out = []
    for d in draws(pno):
        f = hexc(d["fill"]) if d.get("fill") else None
        if f in (COND_FILL, SOFT_FILL) and d["items"][0][0] == "re":
            out.append({"fill": f, "mm": [round(v, 2) for v in d["mm"]],
                        "stroke": hexc(d["color"]) if d.get("color") else None, "sw": round(d["width"], 2) if d.get("width") else None})
    return out


def items(pno):
    """쪽의 문항 — 단마다 번호 줄로 나누고, 번호 뒤 발문 줄, 나머지는 6mm 넘는 틈·상자로 덩어리를 나눠 종류를 붙인다"""
    R = rows(pno)
    BX = boxes(pno)

    def inbox(r):
        return next((b for b in BX if b["mm"][1] < r["base"] < b["mm"][1] + b["mm"][3] and b["mm"][0] < r["x"] < b["mm"][0] + b["mm"][2]), None)
    out = []
    for col in (0, 1):
        cr = sorted((r for r in R if r["col"] == col), key=lambda r: r["base"])
        nums = [r for r in cr if any("Elice" in s["font"] and s["size"] == 12 for s in r["spans"])]
        for i, n in enumerate(nums):
            lo, hi = n["base"] - 1, (nums[i + 1]["base"] - 1 if i + 1 < len(nums) else 999)
            ir = [r for r in cr if lo <= r["base"] < hi and r is not n]
            q = [r for r in ir if abs(r["base"] - n["base"]) < 1.0]
            rest = [r for r in ir if r not in q]
            while rest and hangul(rest[0]["text"]) and rest[0]["base"] - q[-1]["base"] < 5.5 and not inbox(rest[0]):
                q.append(rest.pop(0))
            segs = []
            for r in rest:
                b = inbox(r)
                if segs and r["base"] - segs[-1]["rows"][-1]["base"] < 6 and segs[-1]["box"] is b:
                    segs[-1]["rows"].append(r)
                else:
                    segs.append({"rows": [r], "box": b})
            seen_p = False
            for s in segs:
                if s["box"] and s["box"]["fill"] == COND_FILL:
                    s["kind"] = "조건"
                elif s["box"]:
                    s["kind"] = "요약문" if seen_p else "주어진글"
                elif s["rows"][0]["text"].strip()[:1] in CIRC:
                    s["kind"] = "선지"
                else:
                    s["kind"] = "지문"
                    seen_p = True
            out.append({"col": col, "num": n, "q": q, "segs": segs})
    return out


# ── 그리기 도구 (09 와 같은 꼴) ──────────────────────────────
def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, pad=None, w=None, align=None,
      temp=None, track=None, measure=True):
    """원본 글 하나. x = 글자 시작(원점), base = 기준선, bbox = 원본 글자 상자(잴 자리·자간 계산). 자간은 원본 글자 위치에서."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    if track is None:
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    if measure:
        ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                          "ctol": 30, "search": search, "text": s, "size": size, **({"pad": pad} if pad is not None else {})})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


def ST(pg, id, s, family, weight, label=None, search=1.5, pad=None, temp=None, text_=None, w=None):
    """원본 조각 그대로 한 글상자"""
    t = text_ or s["t"].strip()
    return T(pg, id, s["x"], s["base"], t, s["size"], s["color"], family, weight, bbox_of(s), label=label, search=search, pad=pad,
             temp=temp, w=w)


def rot_spans(pno):
    """원본 쪽의 돌린 글(아래에서 위로 읽는 탭 글) — 같은 글이 두 번 겹쳐 있어 한 번만 (09 와 같다)"""
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
                out.append({"text": t, "color": "#%06x" % sp["color"], "x0": (ink[0]["bbox"][0] - ox) * MM,
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM) for c in ink]})
    return sorted(out, key=lambda r: r["chars"][0][2])


def TR(pg, id, sp, size, color, family, weight, w=14, label=None):
    """돌린 글 — 단위 04·09 의 TR 과 같은 계산(편집기는 글상자를 가운데 기준으로 돌린다)"""
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


def frame(pg, id, x, y, w, h, stroke, sw, fill=None, radius=0, label=None):
    """테두리 면 — 원본 사각형(x, y, w, h mm) · 획 색 · 획 두께 pt(가운데) · 채움 (09 와 같다)"""
    hw = sw * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2), "h": round(h + 2 * hw, 2),
                      "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30})
    if fill:
        ELEMS[pg].append({"id": id + "-f", "x": round(x + hw, 2), "y": round(y + hw, 2), "w": round(w - 2 * hw, 2), "h": round(h - 2 * hw, 2),
                          "color": fill, "see": fill, "pad": 0.1, "ctol": 12})
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "rect", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750}]
    st += [F('#side input[data-a="w"]', w), F('#side input[data-a="h"]', h), F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y)]
    st.append(F('#side input[data-a="radius"]', radius))
    if fill:
        st += [{"pick": {"at": '#side select[data-a="fill"]', "value": "__raw"}, "wait": 650}, F('#side input[type="text"][data-a="fill"]', fill, 750)]
    else:
        st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', stroke, 750), F('#side input[data-a="stroke.w"]', sw)]
    return st


def jc4(vals=JC):
    """고른 글상자의 균등 배치 네 칸(패널 단락) — 낱말 최소·최대 % · 자간 최소·최대 ‰"""
    return [F(f'#side input[data-a="jc.{k}"]', v, 600) for k, v in zip(("word_min", "word_max", "letter_min", "letter_max"), vals)]


def dup(x, y, h=None, extra=()):
    """고른 것 「⧉ 복제」 → 자리(·높이)만 새로"""
    st = [{"click": "#side #s-dup", "wait": 700}]
    if h is not None:
        st.append(F('#side input[data-a="h"]', h))
    st += list(extra)
    return st + [F('#side input[data-it="x"]', round(x, 2)), F('#side input[data-it="y"]', round(y, 2), 550)]


# ── 머리 · 꼬리 ─────────────────────────────────────────────
def header_left(pg, pno):
    sp = spans(pno)
    title = next(s for s in sp if s["t"].strip() == "실전 문제")
    code = next(s for s in sp if "Mamablock" in s["font"])
    st = [S("머리 — 크림 띠 · 선 · 벽돌 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    bar = next(d for d in draws(pno) if d.get("fill") and hexc(d["fill"]) == BRICK and d["mm"][3] > 20)
    st += B(pg, "bar", round(bar["mm"][0], 2), -3, round(bar["mm"][2], 2), round(bar["mm"][1] + bar["mm"][3] + 3, 2), BRICK)
    st += T(pg, "t-step", 20.0, 8.93, "STEP 03", 8, BRICK, NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 03 · TEST")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    test = next(s for s in sp if s["t"].strip() == "TEST")
    st += ST(pg, "t-test", test, NOTO, 700)
    st += ST(pg, "t-code", code, MAMA, 400, label="제목 — 코드 · 이름")
    st += ST(pg, "t-title", title, GM, 500)
    st += [S("단계 점 셋 — 지금 단계(3)가 찬 원", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, fill=BRICK)
    for k, n in enumerate(s for s in sp if "Montserrat-Bold" in s["font"] and s["size"] == 6.0 and s["base"] < 20):
        st += ST(pg, f"n{k + 1}", n, MS, 700, search=0.6)
    return st


def header_right(pg, pno):
    sp = spans(pno)
    st = [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
    st += B(pg, "band", -3, -3, 216, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    ELEMS[pg].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
    st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
    tag = next(s for s in sp if s["t"].strip() == "STEP BY STEP" and s["size"] == 6.0)
    st += ST(pg, "tag-t", tag, MS, 700, search=0.2, pad=0.2)                # 흰 글 — 잴 창을 꼬리표 안으로
    big = next(s for s in sp if s["size"] == 36.0)
    st += ST(pg, "t-code", big, MS, 500, label="큰 코드 S")
    st += [S("오른쪽 탭 셋 — 지금 단계(STEP 03)가 벽돌", 1500)]
    tabs = sorted((d for d in draws(pno) if d.get("fill") and abs(d["mm"][0] - 201.5) < 0.1), key=lambda d: d["mm"][1])
    for k, d in enumerate(tabs):
        st += B(pg, f"tab{k + 1}", 201.5, round(d["mm"][1], 2), 11.5, round(d["mm"][3], 2), hexc(d["fill"]))
    for k, r in enumerate(rot_spans(pno)):
        st += TR(pg, f"tab{k + 1}-t", r, 6.5, r["color"], MS, 700)
    return st


def footer(pg, pno):
    st = [S("꼬리 — 쪽번호", 1200)]
    for k, s in enumerate(sorted((s for s in spans(pno) if s["base"] > 280), key=lambda s: s["x"])):
        st += ST(pg, f"f{k + 1}", s, EL, 700, search=0.6)
    return st


# ── 문항 ────────────────────────────────────────────────────
W_BODY = round(82 + TRACK / 1000 * 8 * MM, 2)        # 단 폭 82mm — 크롬은 줄 끝 글자 뒤에도 자간을 둔다
W_BOX = round(76 + TRACK / 1000 * 8 * MM, 2)         # 상자 안 글 — 상자 82mm 에서 양쪽 3mm
SLOTS = []                                           # (쪽, 위 끝, 왼쪽, 자리, 원고) — 원고 넣는 순서(쪽 → 위 → 왼쪽)
TEMP = {
    "문항번호": "00",
    "발문": "다음 글의 {임시 밑줄} 발문 자리입니다. 적절하지 않은 것은?",
    "지문": ("(A) Temporary passage text for styling. The real story arrives later from outside, and this paragraph has "
             "{marked words} and a [ choice / option ] so that the style can be set while it is still empty."),
    "선지": "① Temporary choice one\n② Temporary choice two that is a little longer than the others\n③ Temporary choice three\n"
            "④ Temporary choice four\n⑤ Temporary choice five",
    "조건": "1. 임시 조건 하나\n2. 임시 조건 둘\n- word, word, word\n(임시 안내 줄)\n3. 임시 조건 셋",
    "요약문": "A (A)__________ temporary summary sentence keeps the (B)__________ shape of the box.",
    "주어진글": "Temporary given text for the order question, a sentence or two that comes from outside.",
}


def text_ink(rr):
    """잴 창 — 줄들의 조각 상자를 합친 것"""
    x0, x1 = min(r["x0"] for r in rr), max(r["x1"] for r in rr)
    y0, y1 = min(r["y0"] for r in rr), max(r["y1"] for r in rr)
    return round(x0, 2), round(y0, 2), round(x1 - x0, 2), round(y1 - y0, 2)


def meas_block(pg, id, rr, txt, color=INK, iou=0.80, search=0.8, pad=0.5):
    x, y, w, h = text_ink(rr)
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": color, "see": color, "ctol": 40, "pad": pad, "search": search,
                      "text": txt[:30], "size": 8, "shape_iou": iou})


def para_rows(rr):
    """선지 줄 → 선지마다 [줄]"""
    out = []
    for r in rr:
        if r["text"].strip()[:1] in CIRC or not out:
            out.append([r])
        else:
            out[-1].append(r)
    return out


def title_track(t, w):
    """조건 제목의 자간 — 원본 글자 원점 간격 - 크롬 글자 폭(한 글자씩, 공백은 한국어 꼴). 글자마다 같으면 한 값,
    다르면 가장 많은 값을 상자 자간으로 하고 나머지 글자는 GREP 자간으로 → (상자 자간, [(패턴, 자간)])"""
    ch = [c for c in t["chars"]]
    while ch and not ch[-1][0].strip():
        ch = ch[:-1]
    em = t["size"] * MM
    v = []
    for a, b in zip(ch, ch[1:]):
        wa = chrome_extent(NOTO, w, t["size"], a[0] + "x") if a[0].strip() else (chrome_extent(NOTO, w, t["size"], "x x") - chrome_extent(NOTO, w, t["size"], "xx"))
        v.append((a[0], round(((b[1] - a[1]) - wa) / em * 1000)))
    vals = [x for _, x in v]
    base = 0 if any(abs(x) <= 8 for x in vals) else statistics.mode(vals)    # GREP 자간 0 은 칸에 못 넣는다(빈 칸 = 없음) — 0 인 글자가 있으면 상자를 0 으로
    groups = {}
    for c, x in v:
        if abs(x - base) > 8:
            groups.setdefault(x, []).append(c)
    pats = [(" " if cs == [" "] else "[" + "".join(sorted(set(cs))) + "]", x) for x, cs in groups.items()]
    return base, pats


Q_TRACK, Q_TSUME = -40, 40   # 발문 — 원본 글자 쌍마다 간격 = 자간 −40‰ − 0.4 × (앞 글자 오른쪽 + 뒤 글자 왼쪽 빈 곳): 인디자인 「자간 축소」 40% (2026-10-09, 2,384쌍 3‰ 안)


def qpage(pg, pno, colx):
    its = items(pno)
    BX = boxes(pno)
    st = []
    full = lambda rr: rr[-1]["x1"] > colx[rr[-1]["col"]] + 82 - 1.5             # 꽉 찬 줄(양끝으로 늘린 줄)

    # 상자 먼저(글 아래에 깔린다) — 조건 상자, 연한 면
    for kind, lab in ((COND_FILL, "조건 상자 — 하늘 면 + 테두리 0.5pt"), (SOFT_FILL, "연한 면 — 요약문 · 주어진 글 상자")):
        bs = [b for b in BX if b["fill"] == kind]
        for k, b in enumerate(bs):
            x, y, w, h = b["mm"]
            if k == 0:
                if b["stroke"]:
                    st += frame(pg, f"cb{k}", x, y, w, h, b["stroke"], b["sw"], fill=kind, label=lab)
                else:
                    st += B(pg, f"sb{k}", x, y, w, h, kind, label=lab, pad=0.4, ctol=4)    # 흰 바탕과 6~12 차이 — 색 허용을 좁게
            else:
                if b["stroke"]:
                    hw = b["sw"] * MM / 2
                    ELEMS[pg].append({"id": f"cb{k}", "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2),
                                      "h": round(h + 2 * hw, 2), "color": b["stroke"], "see": b["stroke"], "pad": 0.3, "ctol": 30})
                    ELEMS[pg].append({"id": f"cb{k}-f", "x": round(x + hw, 2), "y": round(y + hw, 2), "w": round(w - 2 * hw, 2),
                                      "h": round(h - 2 * hw, 2), "color": kind, "see": kind, "pad": 0.1, "ctol": 12})
                else:
                    ELEMS[pg].append({"id": f"sb{k}", "x": x, "y": y, "w": w, "h": h, "color": kind, "see": kind, "pad": 0.4, "ctol": 4})
                st += dup(x, y, h=h)

    # 문항 번호
    st += [S("문항 번호 — 첫 번호를 그리고 복제", 1400)]
    for k, it in enumerate(its):
        n = next(s for s in it["num"]["spans"] if "Elice" in s["font"])
        no = n["t"].strip()
        SLOTS.append((pg, round(top_of(n["base"], 12, EL, 700), 2), n["x"], "문항번호", no))
        if k == 0:
            st += T(pg, f"q{no}", n["x"], n["base"], no, 12, QBLUE, EL, 700, bbox_of(n), search=0.8, temp="00", label="문항 번호 자리")
            st += slot("문항번호")
        else:
            ELEMS[pg].append({"id": f"q{no}", "x": bbox_of(n)[0], "y": bbox_of(n)[1], "w": bbox_of(n)[2], "h": bbox_of(n)[3], "color": QBLUE,
                              "see": QBLUE, "ctol": 30, "search": 0.8, "text": no, "size": 12})
            st += dup(n["x"], top_of(n["base"], 12, EL, 700))

    # 발문 — 첫 줄은 번호 뒤 탭 자리부터(첫 줄 들여쓰기), 둘째 줄은 단 왼쪽부터
    st += [S("발문 — 임시 글 · 자리 · 스타일(양끝 · 밑줄 GREP), 나머지는 복제", 1600)]
    first_ind = None
    for k, it in enumerate(its):
        q = it["q"]
        cx = colx[it["col"]]
        first = next(c for c in q[0]["spans"][0]["chars"] if c[0].strip())
        ind = round(first[1] - cx, 2)                                  # 첫 글자 원점 - 단 왼쪽 (번호 「100」 은 탭이 다음 자리로 가서 12.7)
        txt = marked_text(pno, q, hang=True)
        no = it["num"]["text"].strip()
        y = round(top_of(q[0]["base"], 8, NOTO, 400, LEAD_Q), 2)
        h = round(2 * LEAD_Q * MM + 0.6, 1)                             # 발문 틀은 모두 두 줄 높이(원본 발문은 한두 줄)
        SLOTS.append((pg, y, cx, "발문", txt))
        for j, r in enumerate(q):
            ELEMS[pg].append({"id": f"q{no}-p{j}", "x": round(r["x0"], 2), "y": round(r["y0"], 2), "w": round(r["x1"] - r["x0"], 2),
                              "h": round(r["y1"] - r["y0"], 2), "color": INK, "see": INK, "ctol": 40, "pad": 0.5, "search": 0.5,
                              "text": r["text"].strip()[:30], "size": 8, **({"shape_iou": 0.80} if j < len(q) - 1 else {})})
        if k == 0:
            first_ind = ind
            st += text(cx, y, round(82 + Q_TRACK / 1000 * 8 * MM, 2), h, TEMP["발문"], 8, INK,
                       label=f"발문 자리 — 임시 글 · 자간 {Q_TRACK} · 자간 축소 {Q_TSUME}%", leading=LEAD_Q, align="justify", font=NOTO, track=Q_TRACK, tsume=Q_TSUME)
            st += slot("발문", label="자리 이름 「발문」")
            st += jc4()
            st.append(F('#side input[data-a="indent_first"]', ind))
            st += grep(0, r"\{(.+?)\}", bold=False, underline=True, line=UL_W, line_off=0.70, hide=True,
                       label="GREP — 약속 괄호 { } 는 감추고 안쪽만 밑줄(0.5pt · 기준선 0.7mm 아래)")
            st += grep(1, "않은", bold=False, weight=500, label="GREP — 「않은」 은 Medium")
        else:
            st += dup(cx, y, extra=[F('#side input[data-a="indent_first"]', ind)] if ind != first_ind else [])

    # 지문
    st += [S("지문 — 임시 글 · 자리 · 스타일(양끝 · 행간 14pt · 자간 -50 · GREP 셋), 나머지는 복제", 1700)]
    k = 0
    for it in its:
        for s in it["segs"]:
            if s["kind"] != "지문":
                continue
            rr = s["rows"]
            cx = colx[it["col"]]
            txt = marked_text(pno, rr, para_start=lambda r: r["spans"][0]["t"].strip()[:3] in ("(A)", "(B)", "(C)") and "Medium" in r["spans"][0]["font"])
            y = round(top_of(rr[0]["base"], 8, NOTO, 400, LEAD_P), 2)
            h = round(len(rr) * LEAD_P * MM + 0.6, 1)
            SLOTS.append((pg, y, cx, "지문", txt))
            meas_block(pg, f"p{it['num']['text'].strip()}", rr, txt)
            if k == 0:
                st += text(cx, y, W_BODY, h, TEMP["지문"], 8, INK, label="지문 자리 — 임시 글", leading=LEAD_P, align="justify", font=NOTO, track=TRACK)
                st += slot("지문", label="자리 이름 「지문」")
                st += jc4()
                st += grep(0, r"\{(.+?)\}", bold=False, weight=500, underline=True, line=UL_W, line_off=0.70, hide=True,
                           label="GREP — 약속 괄호 { } 는 감추고 안쪽만 Medium + 밑줄")
                st += grep(1, r"\[[^\]]*\]", bold=False, weight=500, label="GREP — 어법 고르기 [ … / … ] 는 Medium")
                st += grep(2, r"\([A-C]\)", bold=False, weight=500, label="GREP — 배열 문단 머리 (A)(B)(C) 는 Medium")
                st += grep(3, "_+", bold=False, label=f"GREP — 빈칸 밑줄 문자 _ 자간 {US_TRACK}")
                st.append(F('#side input[data-a="grep.3.track"]', US_TRACK, 600))
            else:
                st += dup(cx, y, h=h)
            k += 1

    # 선지
    st += [S("선지 — 임시 글 · 자리 · 스타일(행간 12pt · 단락 뒤 1mm · 내어쓰기 3.5mm), 나머지는 복제", 1700)]
    k = 0
    for it in its:
        for s in it["segs"]:
            if s["kind"] != "선지":
                continue
            rr = s["rows"]
            cx = colx[it["col"]]
            paras = para_rows(rr)
            txt = "\n".join(" ".join(r["text"].strip() for r in p) for p in paras)
            y = round(top_of(rr[0]["base"], 8, NOTO, 400, LEAD_O), 2)
            h = round(len(rr) * LEAD_O * MM + len(paras) * O_GAP + 0.6, 1)
            SLOTS.append((pg, y, cx, "선지", txt))
            no = it["num"]["text"].strip()
            for j, p in enumerate(paras):
                meas_block(pg, f"o{no}-{j + 1}", p, p[0]["text"].strip(), iou=0.80 if (len(p) > 1 or full(p)) else 0.90, search=0.5)
            if k == 0:
                st += text(cx, y, W_BODY, h, TEMP["선지"], 8, INK, label="선지 자리 — 임시 글", leading=LEAD_O, align="justify", font=NOTO, track=TRACK)
                st += slot("선지", label="자리 이름 「선지」")
                st += jc4()
                st += [F('#side input[data-a="indent"]', O_HANG), F('#side input[data-a="indent_first"]', -O_HANG),
                       F('#side input[data-a="space_after"]', O_GAP)]
            else:
                st += dup(cx, y, h=h)
            k += 1

    # 조건 — 제목(고정 글, 꼴이 둘) · 조건 줄(자리)
    conds = [(it, s) for it in its for s in it["segs"] if s["kind"] == "조건"]
    if conds:
        st += [S("조건 제목 — 고정 글(문항마다 「< 조건>」 / 「[조건]」 두 꼴)", 1400)]
        prev = None
        for it, s in conds:
            t = s["rows"][0]["spans"][0]
            key = (t["t"].strip(), t["font"], t["size"])
            fam_w = 700 if "Bold" in t["font"] else 500
            no = it["num"]["text"].strip()
            if key != prev:
                tt = t["t"].strip()
                tr = title_track(t, fam_w)
                st += T(pg, f"ct{no}", t["x"], t["base"], tt, t["size"], t["color"], NOTO, fam_w, bbox_of(t, 1), search=0.6, pad=0.4,
                        track=tr[0])
                for j, (pat, v) in enumerate(tr[1]):                    # 글자마다 다른 간격 — 「< 조건>」 은 「조건」 만 +200(낱자 띄움)
                    st += grep(j, pat, bold=False, label=f"GREP — 「{pat}」 자간 {v}")
                    st.append(F(f'#side input[data-a="grep.{j}.track"]', v, 600))
            else:
                ELEMS[pg].append({"id": f"ct{no}", "x": bbox_of(t, 1)[0], "y": bbox_of(t, 1)[1], "w": bbox_of(t, 1)[2], "h": bbox_of(t, 1)[3],
                                  "color": t["color"], "see": t["color"], "ctol": 30, "search": 0.6, "pad": 0.4, "text": t["t"].strip(), "size": t["size"]})
                st += dup(t["x"], top_of(t["base"], t["size"], NOTO, fam_w))
            prev = key
        st += [S("조건 줄 — 임시 글 · 자리 · 스타일(행간 12pt), 나머지는 복제", 1500)]
        for k, (it, s) in enumerate(conds):
            rr = s["rows"][1:]
            x = rr[0]["x"]
            txt = "\n".join(r["text"].strip() for r in rr)
            y = round(top_of(rr[0]["base"], 8, NOTO, 400, LEAD_O), 2)
            h = round(len(rr) * LEAD_O * MM + 0.6, 1)
            SLOTS.append((pg, y, x, "조건", txt))
            meas_block(pg, f"c{it['num']['text'].strip()}", rr, txt, iou=0.90, search=0.5, pad=0.4)
            if k == 0:
                st += text(round(x, 2), y, round(76 + C_TRACK / 1000 * 8 * MM, 2), h, TEMP["조건"], 8, INK, label="조건 자리 — 임시 글", leading=LEAD_O, font=NOTO, track=C_TRACK)
                st += slot("조건", label="자리 이름 「조건」")
            else:
                st += dup(x, y, h=h)

    # 연한 상자 속 글 — 요약문 · 주어진 글
    for kind in ("요약문", "주어진글"):
        segs = [(it, s) for it in its for s in it["segs"] if s["kind"] == kind]
        if not segs:
            continue
        st += [S(f"{kind} — 임시 글 · 자리 · 스타일(양끝 · 행간 14pt), 나머지는 복제", 1500)]
        for k, (it, s) in enumerate(segs):
            rr = s["rows"]
            x = s["box"]["mm"][0] + 3
            txt = marked_text(pno, rr)
            y = round(top_of(rr[0]["base"], 8, NOTO, 400, LEAD_P), 2)
            h = round(len(rr) * LEAD_P * MM + 0.6, 1)
            SLOTS.append((pg, y, x, kind, txt))
            meas_block(pg, f"{'s' if kind == '요약문' else 'g'}{it['num']['text'].strip()}", rr, txt, search=0.5, pad=0.4)
            if k == 0:
                st += text(round(x, 2), y, W_BOX, h, TEMP[kind], 8, INK, label=f"{kind} 자리 — 임시 글", leading=LEAD_P, align="justify",
                           font=NOTO, track=TRACK)
                st += slot(kind, label=f"자리 이름 「{kind}」")
                st += jc4()
                if kind == "요약문":
                    st += grep(0, "_+", bold=False, label=f"GREP — 빈칸 밑줄 문자 _ 자간 {US_TRACK}")
                    st.append(F('#side input[data-a="grep.0.track"]', US_TRACK, 600))
            else:
                st += dup(x, y, h=h)
    return st


# ── 74쪽 판권 면 ─────────────────────────────────────────────
def logo_svg(pno):
    """원본 로고(벡터 경로) → SVG 파일 — 경로 꼭짓점 그대로(pt). 그림 틀에 올린다(단위 01 과 같은 길)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ds = [d for d in p.get_drawings() if d.get("fill") and hexc(d["fill"]) == "#2d2a2c"]
    X0 = min(d["rect"].x0 for d in ds); Y0 = min(d["rect"].y0 for d in ds)
    X1 = max(d["rect"].x1 for d in ds); Y1 = max(d["rect"].y1 for d in ds)
    paths = []
    for d in ds:
        cmd, cur = [], None
        for it in d["items"]:
            if it[0] == "re":
                r = it[1]
                cmd.append(f"M{r.x0 - X0:.3f} {r.y0 - Y0:.3f}H{r.x1 - X0:.3f}V{r.y1 - Y0:.3f}H{r.x0 - X0:.3f}Z")
                cur = None
                continue
            a = it[1]
            if cur is None or abs(cur.x - a.x) > 1e-3 or abs(cur.y - a.y) > 1e-3:
                cmd.append(f"M{a.x - X0:.3f} {a.y - Y0:.3f}")
            if it[0] == "l":
                b = it[2]
                cmd.append(f"L{b.x - X0:.3f} {b.y - Y0:.3f}")
                cur = b
            elif it[0] == "c":
                c1, c2, b = it[2], it[3], it[4]
                cmd.append(f"C{c1.x - X0:.3f} {c1.y - Y0:.3f} {c2.x - X0:.3f} {c2.y - Y0:.3f} {b.x - X0:.3f} {b.y - Y0:.3f}")
                cur = b
        if d.get("closePath"):
            cmd.append("Z")
        paths.append(f'<path d="{"".join(cmd)}" fill="#2d2a2c" fill-rule="{"evenodd" if d.get("even_odd") else "nonzero"}"/>')
    w, h = X1 - X0, Y1 - Y0
    path = os.path.join(HERE, "logo.svg")
    open(path, "w").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.4f}" height="{h:.4f}" viewBox="0 0 {w:.4f} {h:.4f}">'
                          + "".join(paths) + "</svg>\n")
    return path, round((X0 - ox) * MM, 2), round((Y0 - oy) * MM, 2), round(w * MM, 2), round(h * MM, 2)


def colophon(pg, pno):
    sp = spans(pno)
    dr = draws(pno)
    st = [S("판권 면 — 바탕 · 막대 · 꼬리표", 1500)]
    st += B(pg, "bg", -3, -3, 216, 303, "#f6f1e8", label="바탕 — 재단 여백까지", measure=False)
    bar = next(d for d in dr if d.get("fill") and hexc(d["fill"]) == "#80a2be" and d["mm"][3] > 20)
    st += B(pg, "bar", round(bar["mm"][0], 2), -3, round(bar["mm"][2], 2), round(bar["mm"][1] + bar["mm"][3] + 3, 2), "#80a2be")
    tg = next(d for d in dr if d.get("fill") and hexc(d["fill"]) == "#b1ac9f")
    tx, ty, tw, th = tg["mm"]
    p = REFDOC[pno - 1]
    pts = [(((q.x - p.trimbox.x0) * MM - tx) / tw, ((q.y - p.trimbox.y0) * MM - ty) / th) for it in tg["items"] for q in it[1:2]]
    dpath = " ".join(("M" if k == 0 else "L") + f"{min(max(a, 0), 1):.4f} {min(max(b, 0), 1):.4f}" for k, (a, b) in enumerate(pts)) + " Z"
    ELEMS[pg].append({"id": "tag", "x": round(tx, 2), "y": round(ty, 2), "w": round(min(tw, 213 - tx), 2), "h": round(th, 2), "color": "#b1ac9f"})
    st += shape(round(tx, 2), round(ty, 2), round(tw, 2), round(th, 2), "#b1ac9f", d=dpath, label="꼬리표 — 도형, 원본 꼭짓점 그대로")
    tag = next(s for s in sp if s["size"] == 6.5)
    st += T(pg, "tag-t", tag["x"], tag["base"], "STEP BY STEP", 6.5, tag["color"], MS, 700, bbox_of(tag), search=0.2, pad=0.2)
    st += [S("시리즈 이름 · 교재명 · 선", 1400)]
    s1 = [s for s in sp if s["size"] == 21.0]
    bb = (round(s1[0]["x0"], 2), round(s1[0]["y0"], 2), round(s1[-1]["x1"] - s1[0]["x0"], 2), round(s1[0]["y1"] - s1[0]["y0"], 2))
    for s in s1:                                                            # 잴 것 — 색마다
        ELEMS[pg].append({"id": "series-" + s["t"].strip(), "x": bbox_of(s)[0], "y": bbox_of(s)[1], "w": bbox_of(s)[2], "h": bbox_of(s)[3],
                          "color": s["color"], "see": s["color"], "ctol": 30, "search": 1.0, "text": s["t"].strip(), "size": 21})
    st += T(pg, "series", s1[0]["x"], s1[0]["base"], "STEP BY STEP", 21, s1[0]["color"], MS, 800, bb, measure=False, label="STEP BY STEP — 고정 글")
    st += grep(0, "BY", s1[1]["color"], bold=False, label="GREP — 「BY」 만 파랑")
    t2 = [s for s in sp if abs(s["base"] - 51.53) < 0.1]
    bb2 = (round(t2[0]["x0"], 2), round(t2[0]["y0"], 2), round(t2[-1]["x1"] - t2[0]["x0"], 2), round(t2[0]["y1"] - t2[0]["y0"], 2))
    name = " ".join(s["t"].strip() for s in t2)
    st += T(pg, "book", t2[0]["x"], t2[0]["base"], name, 12, t2[0]["color"], SDG, 400, bb2, temp="교재 이름", label="교재명 자리")
    st += slot("교재명")
    SLOTS.append((pg, round(top_of(t2[0]["base"], 12, SDG, 400), 2), t2[0]["x"], "교재명", name))
    ln = next(d for d in dr if d.get("fill") and hexc(d["fill"]) == "#aca49a")
    st += B(pg, "rule", *[round(v, 2) for v in ln["mm"]], "#aca49a", pad=0.2)
    st += [S("만든 사람 — 역할(고정 글) · 이름(자리)", 1400)]
    labels = [s for s in sp if s["size"] == 10.5]
    names = [s for s in sp if s["size"] == 12.0 and s["base"] > 60]
    slot_of = {"Writer": "집필", "Teacher": "검토", "Assistant": "보조", "Design": "디자인", "Production": "제작"}
    lead = None
    for k, lb in enumerate(labels):
        st += ST(pg, f"l{k}", lb, MS, 700, search=0.8)
    for k, lb in enumerate(labels):
        nxt = labels[k + 1]["base"] if k + 1 < len(labels) else 260
        ns = [s for s in names if lb["base"] < s["base"] < nxt]
        if lead is None:
            lead = round((ns[1]["base"] - ns[0]["base"]) / MM, 1)           # 이름 줄 간격 5.29mm = 15pt (끝 줄만 5.08mm — 아래 주석)
        txt = "\n".join(s["t"].strip() for s in ns)
        y = round(top_of(ns[0]["base"], 12, SDG, 400, lead), 2)
        for j, s in enumerate(ns):
            em = 12 * MM                                                       # 이름 줄 사이 1.25em — 창은 위 0.92em · 아래 0.15em(받침 없는 아래 끝)
            ELEMS[pg].append({"id": f"nm{k}-{j}", "x": round(s["x0"], 2), "y": round(s["base"] - 0.92 * em, 2), "w": round(s["x1"] - s["x0"], 2),
                              "h": round(1.07 * em, 2), "color": s["color"], "see": s["color"], "ctol": 40, "search": 0.2, "pad": 0.2,
                              "text": s["t"].strip(), "size": 12})
        SLOTS.append((pg, y, ns[0]["x"], slot_of[lb["t"].strip()], txt))
        # 원본은 역할마다 끝 이름 줄만 앞 줄과 5.08mm(자동 행간 14.4pt), 나머지는 5.29mm(15pt) — 끝 줄이 0.21mm 위에 있다.
        # 한 글상자 한 행간이라 끝 줄이 0.21mm 아래로 온다(허용 0.3mm 안). 줄마다 잰다.
        if k == 0:
            st += text(round(ns[0]["x"], 2), y, 40, round(len(ns) * lead * MM + 1, 1), "이름 하나\n이름 둘\n이름 셋", 12, ns[0]["color"],
                       label="이름 자리 — 임시 글", leading=lead, font=SDG)
            st += slot(slot_of[lb["t"].strip()], label=f"자리 이름 「{slot_of[lb['t'].strip()]}」")
        else:
            st += [{"click": "#side #s-dup", "wait": 700}, F('#side input[data-a="h"]', round(len(ns) * lead * MM + 1, 1)),
                   F('#side input[data-it="x"]', round(ns[0]["x"], 2)), F('#side input[data-it="y"]', y, 550)]
            st += slot(slot_of[lb["t"].strip()])
    st +=[S("색 띠 셋 · 로고 · COPYRIGHT", 1400)]
    for k, d in enumerate(sorted((d for d in dr if d.get("fill") and abs(d["mm"][1] - 255.09) < 0.1), key=lambda d: d["mm"][0])):
        st += B(pg, f"chip{k}", *[round(v, 2) for v in d["mm"]], hexc(d["fill"]), pad=0.3)
    path, lx, ly, lw, lh = logo_svg(pno)
    ELEMS[pg].append({"id": "logo", "x": lx, "y": ly, "w": lw, "h": lh, "color": "#2d2a2c", "see": "#2d2a2c", "pad": 0.4, "ctol": 30})
    st += image(lx, ly, lw, lh, path, label="로고 — 「그림」에 SVG(원본 경로 그대로)")
    cp = next(s for s in sp if s["t"].startswith("COPYRIGHT"))
    st += ST(pg, "copy", cp, MS, 700)
    return st


def free_spot(pno):
    """그리기 빈 자리 — 새 상자를 끌어 그리고 두 번 눌러 글을 치는 곳. 시작점과 두 번 누를 곳(시작 + 글상자 반, 최대 30×12mm)이 원본 글·상자에 안 닿는 34×26mm 를 찾는다.
    (기본 자리 120,250 은 이 면들에선 글상자 위라, 두 번 누르기가 있던 글상자를 열어 글을 덮어썼다 — 판 1 의 69쪽)"""
    occ = [(s["x0"] - 1, s["y0"] - 1, s["x1"] + 1, s["y1"] + 1) for s in spans(pno)]
    occ += [(d["mm"][0] - 1, d["mm"][1] - 1, d["mm"][0] + d["mm"][2] + 1, d["mm"][1] + d["mm"][3] + 1) for d in draws(pno)
            if d["mm"][2] < 150 and d["mm"][3] < 150]
    for y in range(264, 30, -2):
        for x in (120, 106, 130, 100, 80, 60, 45, 22):
            r = (x, y, x + 34, y + 26)
            if r[3] <= 296 and not any(a < r[2] and r[0] < c and b < r[3] and r[1] < d for a, b, c, d in occ):
                return [x, y]
    raise RuntimeError(f"{pno}쪽 빈 자리 없음")


def set_spot(xy):
    global SPOT
    import mkpage
    mkpage.SPOT = SPOT = {"mm": xy}                                         # 새 사전으로 — 앞 단계가 쥔 자리는 그대로


# ── 대본 ────────────────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 S 실전문제 79~112 (A4)")
st += expect_pages(1)
st += [S("속성 패널 넓히기", 900), {"drag": {"from": '[data-rsz="r"]', "to": [1200, 500]}, "wait": 800}]
for k, pno in enumerate(PAGES):
    pg = k + 1
    set_spot(free_spot(pno))
    if k:
        st += add_page(f"{'①②③④⑤⑥⑦⑧⑨'[k]} {pno}쪽 — 새 쪽")
    else:
        st += [S(f"① {pno}쪽 — S 실전 문제", 1500)]
    if pno == 74:
        st += colophon(pg, pno)
    else:
        st += header_left(pg, pno) if pno % 2 == 0 else header_right(pg, pno)
        st += qpage(pg, pno, (20.0, 106.0) if pno % 2 == 0 else (21.5, 108.0))
        st += footer(pg, pno)
    st += done(f"{pno}쪽", f"p{pg}.png")

CONTENT = {}
for p_, y_, x_, name, txt in sorted(SLOTS, key=lambda t: (t[0], round(t[1], 1), t[2])):
    CONTENT.setdefault(name, []).append(txt)
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(CONTENT, open(os.path.join(HERE, "원고.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("14c 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()), "· 자리", {k: len(v) for k, v in CONTENT.items()})
