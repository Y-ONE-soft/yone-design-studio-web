"""단위 09 A어법선택 — 원본 d1 reference.pdf 30·31쪽을 A4 한 문서 두 쪽으로. 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
견본: 02B-원고자리/make.py (같은 디자인 집 — 머리 띠·단계 점·제목·옆 탭·쪽번호·지문 자리).
02B 와 다른 점: STEP 02 색(베이지 #cba56f) · 「BUILD UP」 · 단계 점 2가 찬 원 · 쪽마다 지문 하나 + 문항(아이콘·발문·테두리 상자·문항 지문).

자리(원고가 들어가는 글상자) — 이름은 블록 지도 기준:
  지문번호 · 지문(B7 변형지문 본문, [ ⓐ / ⓑ ] 선택 괄호) · 발문(B6) · 문항지문(B6 지문 — ①~⑤ + 밑줄 친 곳)
값은 모두 원본 PDF 에서 — 글 조각(서체·크기·색·기준선)·도형 좌표·자간(글자 간격 중앙값). 눈대중 없음.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
BAEUM = "Elice DigitalBaeum OTF"
BEIGE = "#cba56f"              # STEP 02 색 — 원본 막대·코드·찬 원 (0.7947, 0.6485, 0.4358)

UL = 0.5 * MM                  # 원본 밑줄 획 0.5pt (발문 「틀린」 · 문항 지문 밑줄 친 곳)


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, rotate=None, at=None, w=None, align=None, temp=None):
    """원본 글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 폭에서 계산한다."""
    f = {}
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    if rotate:                                                              # 돌린 글은 글자 위치가 세로 — 상자 길이로
        track = round((bbox[3] - nat) / max(len(s), 1) / (size * MM) * 1000) if len(s) > 1 else 0
    else:                                                                   # 원본 글자 위치 - 브라우저(커닝·대체 글자 포함) 거리
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s, "size": size})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    if at:                                                                  # 돌린 글 — 상자 가운데를 원본 글 가운데에
        cx, cy = at
        bx, by = cx - bw / 2, cy - bh / 2
    else:
        bx, by = x, top_of(base, size, family, weight, leading)
    st = text(round(bx - f.get("dx", 0), 2), round(by - f.get("dy", 0), 2), bw, bh, temp or s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=round(track - f.get("dtr", 0)) or None, leading=leading, align=align)
    if rotate:
        st.append(F('#side input[data-a="rotate"]', rotate, 600))
    return st


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
                out.append({"text": t, "color": "#%06x" % sp["color"], "x0": (ink[0]["bbox"][0] - ox) * MM,
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM) for c in ink]})
    return sorted(out, key=lambda r: r["chars"][0][2])


def TR(pg, id, sp, size, color, family, weight, w=14, label=None):
    """돌린 글 — 단위 04 의 TR 과 같은 계산. 편집기는 글상자를 가운데 기준으로 돌린다.
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


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": 30})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)


def frame(pg, id, x, y, w, h, stroke, sw, fill=None, radius=0, label=None):
    """테두리 면 — 원본 사각형 경로(x, y, w, h mm) · 획 색 · 획 두께 pt(가운데 정렬 = 인디자인 기본). 채움 없으면 「없음」"""
    hw = sw * MM / 2
    ELEMS[pg].append({"id": id, "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2), "h": round(h + 2 * hw, 2),
                      "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30})
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


def tick(pg, id, pts, stroke, sw, label=None):
    """체크 표시 — 「도형」에 원본 꺾은선 꼭짓점(0~1 비율 경로 d) · 채움 없음 · 획 · 연결·끝모양 둥글게(원본 lineJoin 1 · lineCap 1)"""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    d = " ".join(("M" if k == 0 else "L") + f"{(px - x) / w:.4f} {(py - y) / h:.4f}" for k, (px, py) in enumerate(pts))
    hw = sw * MM / 2                                                        # 둥근 끝 — 끝점에서 반 획만큼 나간다
    ELEMS[pg].append({"id": id, "x": round(x - hw, 2), "y": round(y - hw, 2), "w": round(w + 2 * hw, 2), "h": round(h + 2 * hw, 2),
                      "color": stroke, "see": stroke, "pad": 0.03, "ctol": 30})
    # 창을 체크 획에 딱 맞게(0.03mm): 넓으면 둘레 아이콘 획(#bd7d70)의 흐린 가장자리 화소가 이 색(#e2afa4)과 30 안으로 잡혀
    # 체크가 아니라 아이콘 테두리를 잰다(판 3: 원본·결과 모두 상자가 2.54mm 로 부풀었다)
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "path", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + 20, SPOT["mm"][1] + 15]}}, "wait": 750},
           F('#side input[data-a="d"]', d, 800)]
    st += [F('#side input[data-a="w"]', round(w, 3)), F('#side input[data-a="h"]', round(h, 3)),
           F('#side input[data-it="x"]', round(x, 3)), F('#side input[data-it="y"]', round(y, 3))]
    st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})
    st += [{"pick": {"at": '#side select[data-a="stroke.color"]', "value": "__raw"}, "wait": 650},
           F('#side input[type="text"][data-a="stroke.color"]', stroke, 750), F('#side input[data-a="stroke.w"]', sw),
           {"pick": {"at": '#side select[data-a="stroke.join"]', "value": "round"}, "wait": 550},
           {"pick": {"at": '#side select[data-a="stroke.cap"]', "value": "round"}, "wait": 550}]
    return st


def blocks(pno):
    """원본 쪽의 8.5pt 글 — 기준선 간격이 10mm 넘게 벌어지는 곳에서 나눈다(지문 / 문항 지문).
    [(x, 첫 기준선, 마지막 기준선, 조각들[(글, 굵기 이름)], (위, 아래), 오른쪽 끝, 행간 pt, 자간)]"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    _, _, adv = face(NOTO, 400)
    rows = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if round(s["size"], 1) == 8.5]
            if not sp:
                continue
            ch = [c for s in sp for c in s["chars"]]
            ink = [c for c in ch if c["c"].strip()]
            gaps = [((c["origin"][0] - a["origin"][0]) - adv(a["c"]) * 8.5) / 8.5 * 1000          # 같은 조각 안 글자 사이 - 서체 폭
                    for s in sp if "Regular" in s["font"] for a, c in zip(s["chars"], s["chars"][1:]) if a["c"] != " " and c["c"] != " "]
            rows.append(((sp[0]["origin"][1] - oy) * MM, (ink[0]["bbox"][0] - ox) * MM,
                         [("".join(c["c"] for c in s["chars"]), s["font"].split("-")[-1]) for s in sp],
                         (sp[0]["bbox"][1] - oy) * MM, (sp[0]["bbox"][3] - oy) * MM, (ink[-1]["bbox"][2] - ox) * MM, gaps))
    out, cur = [], []
    for r in rows:
        if cur and r[0] - cur[-1][0] > 10:
            out.append(cur); cur = []
        cur.append(r)
    out.append(cur)
    res = []
    for g in out:
        rights = [round(r[5], 1) for r in g[:-1]] or [round(g[0][5], 1)]
        right = statistics.mode(rights)                     # 글상자 오른쪽 = 꽉 찬 줄 끝의 가장 흔한 값 (글자 잉크가 0.1mm 넘는 줄은 빼고)
        segs = []
        for k, r in enumerate(g):
            for j, (t, wt) in enumerate(r[2]):
                if k < len(g) - 1 and j == len(r[2]) - 1:
                    t = t.rstrip(" ") + " "                 # 줄 끝 공백은 낱말 사이 하나로 (원고는 줄 나눔 없이)
                segs.append((t, wt))
        segs[-1] = (segs[-1][0].rstrip(" "), segs[-1][1])
        lead = round((g[1][0] - g[0][0]) / MM) if len(g) > 1 else 22
        track = round(statistics.median([v for r in g for v in r[6]]) / 5) * 5
        res.append((g[0][1], g[0][0], g[-1][0], segs, (g[0][3], g[-1][4]), right, lead, track))
    return res


CONTENT = {"지문번호": [], "지문": [], "발문": [], "문항지문": []}         # 끝에 넣을 원고 — 자리 이름 → 글(읽는 순서)
TEMP = ("Temporary text for styling. A [ ⓐ word / ⓑ phrase ] sits in the line, and the passage keeps [ ⓐ going / ⓑ moving ] "
        "until the real content arrives from outside. ")
QTEMP = ("Temporary text for styling. The question passage has ①{marked words} and ②{another phrase} in the line, and it keeps "
         "③{going} until the real content arrives from ④{outside} the editor ⑤{later}. ")
PROMPT_TEMP = "다음 글의 밑줄 친 부분 중 어법상 {틀린} 것은?"
WORD_MIN = -60       # 양끝 줄 낱말 간격 최소 — 02B 와 같은 값(인디자인이 공백을 줄여 넣은 줄이 다 들어가는 값)


def temp_of(tmpl, n):
    """자리의 임시 글 — 올 원고의 꼴을 흉내 낸 글. 길이는 원본과 비슷하게"""
    return (tmpl * (n // len(tmpl) + 1))[:n].rsplit(" ", 1)[0] + "."


def P(pg, id, blk, label):
    """지문 한 덩어리 — 양끝맞춤 · 행간(원본 기준선 간격) · 자간(원본 글자 간격 중앙값) · GREP 로 [ … / … ] 만 굵은 파랑."""
    x, b0, b1, segs, yb, right, lead, track = blk
    txt = "".join(t for t, _ in segs)
    w = round(right - x + track / 1000 * 8.5 * MM, 2)                 # Chrome 은 줄 끝 글자 뒤에도 자간을 둔다
    for k, col in (("", "#231f20"), ("-b", "#00559f")):
        ELEMS[pg].append({"id": id + k, "x": x, "y": yb[0], "w": round(right - x, 2), "h": yb[1] - yb[0], "color": col, "see": col,
                          "ctol": 40, "search": 1.0, "text": txt[:30], "size": 8.5,
                          "shape_iou": 0.80})          # 문단은 양끝맞춤에서 단어가 0.2mm 안팎 다르게 놓인다 — 겹침 기준을 낮춘다
    lines = round((b1 - b0) / (lead * MM)) + 1
    CONTENT["지문"].append(txt)
    st = text(x, round(top_of(b0, 8.5, NOTO, 400, lead), 2), w, round(lines * lead * MM, 1), temp_of(TEMP, len(txt)), 8.5, "#231f20",
              label=label, leading=lead, align="justify", font=NOTO, track=track)
    st += slot("지문", label="자리 이름 「지문」")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    st.append(F('#side input[data-a="word_min"]', WORD_MIN, 600))
    st += grep(0, r"\[[^\]]*\]", "#00559f", label="GREP 스타일 — 대괄호 [ ] 안은 굵은 파랑")
    return st


def Q(pg, id, blk, label, ul_off):
    """문항 지문 — 양끝맞춤 · 행간 20pt · 자간. 원본은 ①~⑤ 뒤 밑줄 친 낱말이 Noto Medium(500) + 밑줄 0.5pt.
    원고는 글만 — 밑줄 칠 곳은 약속 괄호 {…} 로 (예 「⑤{were turned off}」). GREP 가 괄호는 감추고 안쪽만 Medium + 밑줄.
    ul_off = 원본 밑줄 선 가운데 - 기준선(mm)."""
    x, b0, b1, segs, yb, right, lead, track = blk
    plain = "".join(t for t, _ in segs)
    marked = "".join("{" + t + "}" if wt == "Medium" else t for t, wt in segs)
    w = round(right - x + track / 1000 * 8.5 * MM, 2)
    ELEMS[pg].append({"id": id, "x": x, "y": yb[0], "w": round(right - x, 2), "h": yb[1] - yb[0], "color": "#231f20", "see": "#231f20",
                      "ctol": 40, "search": 1.0, "text": plain[:30], "size": 8.5, "shape_iou": 0.80})
    lines = round((b1 - b0) / (lead * MM)) + 1
    CONTENT["문항지문"].append(marked)
    st = text(x, round(top_of(b0, 8.5, NOTO, 400, lead), 2), w, round(lines * lead * MM, 1), temp_of(QTEMP, len(plain)), 8.5, "#231f20",
              label=label, leading=lead, align="justify", font=NOTO, track=track)
    st += slot("문항지문", label="자리 이름 「문항지문」")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    st.append(F('#side input[data-a="word_min"]', WORD_MIN, 600))
    st += grep(0, r"\{(.+?)\}", bold=False, weight=500, underline=True, line=round(UL, 3), line_off=ul_off, hide=True,
               label="GREP — 약속 괄호 { } 는 감추고 안쪽만 Medium + 밑줄")
    return st


def draws(pno):
    """원본 쪽 그림 경로 → mm (재단 여백 뺀 지면 좌표)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    return [dict(dr, mm=[(dr["rect"].x0 - ox) * MM, (dr["rect"].y0 - oy) * MM, dr["rect"].width * MM, dr["rect"].height * MM],
                 pts=[((q.x - ox) * MM, (q.y - oy) * MM) for it in dr["items"] for q in it[1:2] + it[-1:] if hasattr(q, "x")])
            for dr in p.get_drawings()]


def question(pg, pno, q_blk, label):
    """문항 — 아이콘(둥근 네모 + 체크) · 발문(밑줄 친 「틀린」) · 테두리 상자 · 문항 지문. 값은 원본 경로·글 조각에서."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    dr = draws(pno)
    icon = next(d for d in dr if d["type"] == "fs" and len(d["items"]) == 20)
    chk = next(d for d in dr if d["type"] == "s" and len(d["items"]) == 2 and d["mm"][1] > 140)
    qbox = next(d for d in dr if d["type"] == "s" and d["items"][0][0] == "re" and d["mm"][2] > 100)
    ul = next(d for d in dr if d["type"] == "s" and d["items"][0][0] == "l" and 150 < d["mm"][1] < 160 and d["width"] < 1)
    ix, iy, iw, ih = icon["mm"]
    rad = icon["pts"][1][1] - iy                                           # 왼쪽 직선 위 끝 - 상자 위 끝 = 모서리 반지름
    st = [S(label, 1500)]
    st += frame(pg, "icon", round(ix, 2), round(iy, 2), round(iw, 2), round(ih, 2), hexc(icon["color"]), round(icon["width"], 2),
                fill=hexc(icon["fill"]), radius=round(rad, 2), label="문항 아이콘 — 둥근 네모(흰 채움 · 획)")
    seg = [(it[1], it[2]) for it in chk["items"]]
    pts = [((seg[0][0].x - ox) * MM, (seg[0][0].y - oy) * MM)] + [((b.x - ox) * MM, (b.y - oy) * MM) for _, b in seg]
    st += tick(pg, "tick", pts, hexc(chk["color"]), round(chk["width"], 2), label="체크 — 원본 꺾은선 그대로")
    # 발문 — 원본 9pt 엘리스 디지털배움 · 「틀린」 밑에 0.5pt 선(원본: 30쪽 검정, 31쪽 빨강)
    sp = next(s for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
              if round(s["size"]) == 9 and "".join(c["c"] for c in s["chars"]).strip())     # 앞의 전각 공백·탭 조각은 빼고
    s = "".join(c["c"] for c in sp["chars"])
    px = (sp["chars"][0]["origin"][0] - ox) * MM
    ink = [c for c in sp["chars"] if c["c"].strip()]
    bb = (round((ink[0]["bbox"][0] - ox) * MM, 2), round((sp["bbox"][1] - oy) * MM, 2),
          round((ink[-1]["bbox"][2] - ink[0]["bbox"][0]) * MM, 2), round((sp["bbox"][3] - sp["bbox"][1]) * MM, 2))
    st += T(pg, "prompt", round(px, 2), (sp["origin"][1] - oy) * MM, s, 9, "#%06x" % sp["color"],
            BAEUM, 400, bb, label="발문 자리", temp=PROMPT_TEMP)
    st += slot("발문")
    ux0, ux1 = ul["pts"][0][0], ul["pts"][-1][0]                        # 원본 밑줄이 덮는 글자 = 밑줄 친 곳 → 약속 괄호
    ch = sp["chars"]
    k0 = next(i for i, c in enumerate(ch) if abs((c["origin"][0] - ox) * MM - ux0) < 0.05)
    k1 = next(i for i, c in enumerate(ch) if abs((c["origin"][0] - ox) * MM - ux1) < 0.05)
    CONTENT["발문"].append(s[:k0] + "{" + s[k0:k1] + "}" + s[k1:])
    base = (sp["origin"][1] - oy) * MM
    ucol = hexc(ul["color"])
    if ucol != "#231f20":                                  # 글과 다른 색 밑줄(31쪽 빨강) — 따로 잰다
        ELEMS[pg].append({"id": "ul", "x": round(ul["mm"][0], 2), "y": round(ul["mm"][1] - 0.09, 2), "w": round(ul["mm"][2], 2), "h": 0.18,
                          "color": ucol, "see": ucol, "pad": 0.3, "ctol": 40})
    st += grep(0, r"\{(.+?)\}", bold=False, underline=True, line=round(ul["width"] * MM, 3), line_off=round(ul["mm"][1] - base, 3),
               line_color=ucol if ucol != "#231f20" else None, hide=True,
               label="GREP — 약속 괄호 { } 는 감추고 안쪽만 밑줄" + (" (밑줄만 빨강)" if ucol != "#231f20" else ""))
    st += frame(pg, "qbox", *[round(v, 2) for v in qbox["mm"]], hexc(qbox["color"]), round(qbox["width"], 2),
                label="문항 테두리 상자 — 획만")
    qul = [d for d in dr if d["type"] == "s" and d["items"][0][0] == "l" and d["mm"][1] > q_blk[1] - 1 and d["width"] < 1]
    off = statistics.median(round(d["mm"][1] - min((q_blk[1] + k * q_blk[6] * MM for k in range(20)), key=lambda b: abs(b - d["mm"][1])), 3)
                            for d in qul)                                # 밑줄 가운데 - 그 줄 기준선
    st += Q(pg, "qp", q_blk, "문항 지문 — 자리 + 임시 글", off)
    return st


def header_left(pg, code, title_seg):
    """왼쪽 면 머리 — 02B 와 같은 꼴, 색·글은 원본 30쪽에서"""
    o, wd = title_seg                                                       # 제목 조각(공백으로 시작) 시작 x · 폭
    _, _, adv_gm = face(GM, 500)
    tt = " 어법 선택"
    tr = (wd - adv_gm(tt) * 13 * MM) / len(tt)                              # 글자마다 자간(mm) — 앞 공백에도 들어간다
    tx = round(o + adv_gm(" ") * 13 * MM + tr, 2)                           # 글자는 공백(자간 포함) 다음부터
    st = [S("머리 — 크림 띠 · 선 · 베이지 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, BEIGE)
    st += T(pg, "t-step", 20.0, 8.93, "STEP 02", 8, BEIGE, NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 02 · BUILD UP")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", 32.35, 8.93, "BUILD UP", 8, "#b4aa9a", NOTO, 700, (32.35, 3.84, 13.59, 8.05))
    st += T(pg, "t-code", 20.0, 19.47, code, 25, BEIGE, MAMA, 400, (20.0, 12.18, 7.98, 9.78), label="제목 — 코드 · 이름")
    st += T(pg, "t-title", tx, 17.58, tt.strip(), 13, "#231f20", GM, 500, (tx, 13.70, wd - (tx - o), 5.44))
    st += [S("단계 점 셋 — 지금 단계(2)가 찬 원", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, fill=BEIGE)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    for k, (nx, nw, col) in enumerate(((57.79, 0.82, "#b4aa9a"), (68.58, 1.24, "#ffffff"), (79.57, 1.26, "#b4aa9a"))):
        st += T(pg, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), search=0.6)
    return st


def title_seg(pno):
    p = REFDOC[pno - 1]
    sp = next(s for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if "선택" in "".join(c["c"] for c in s["chars"]))
    return round((sp["origin"][0] - p.trimbox.x0) * MM, 3), round((sp["bbox"][2] - sp["bbox"][0]) * MM, 3)


# ── 30쪽 (왼쪽 면) ──────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 A1 어법선택 (A4)")
st += expect_pages(1)
st += [S("① 30쪽 — A1 어법 선택", 1500)]
st += header_left(1, "A1", title_seg(30))
B30 = blocks(30)
st += T(1, "no1", 20.0, 35.90, "01", 12, "#af9d81", YD, 400, (20.0, 35.90 - 3.2, 3.40, 3.6), search=0.6, label="지문 번호 자리", temp="00")
st += slot("지문번호")
CONTENT["지문번호"].append("01")
st += P(1, "p1", B30[0], "지문 01 본문 — 자리 + 임시 글")
st += question(1, 30, B30[1], "문항 — 아이콘 · 발문 · 상자 · 문항 지문")
st += [S("꼬리 — 쪽번호", 1200)]
st += T(1, "f-no", 15.23, 285.53, "30", 6, "#3b4247", EL, 700, (15.23, 283.62, 3.56, 2.62), search=0.6)
st += T(1, "f-t", 20.9, 285.53, "STEP BY STEP", 6, "#231f20", EL, 700, (20.9, 283.62, 17.68, 2.62))
st += done("30쪽", "p1.png")

# ── 31쪽 (오른쪽 면) ────────────────────────────────────────
st += add_page("② 31쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(2, "tag-t", 187.05, 21.84, "STEP BY STEP", 6, "#ffffff", MS, 700, (187.05, 19.56, 15.43, 2.84), search=0.2)
ELEMS[2][-1]["pad"] = 0.2      # 흰 글 창을 꼬리표 안으로: 1.5mm 면 위 지면 흰 바탕과 큰 「A1」(이 단위는 베이지) 끝이 섞여 글이 아니라 창을 잰다
st += T(2, "t-code", 188.04, 15.99, "A1", 36, BEIGE, MS, 500, (188.04, 2.62, 13.46, 16.71), label="큰 코드 A1")
st += [S("오른쪽 탭 셋 — 지금 단계(STEP 02)가 베이지", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#e1eaf3")
st += B(2, "tab2", 201.5, 90, 11.5, 26, BEIGE)
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
for k, sp in enumerate(rot_spans(31)):                                     # 원본은 아래에서 위로 읽는 글 — 위에서 아래 순서로
    st += TR(2, f"tab{k + 1}-t", sp, 6.5, sp["color"], MS, 700)
B31 = blocks(31)
st += T(2, "no2", 22.0, 35.90, "02", 12, "#af9d81", YD, 400, (22.0, 35.90 - 3.2, 3.84, 3.6), search=0.6, label="지문 번호 자리", temp="00")
st += slot("지문번호")
CONTENT["지문번호"].append("02")
st += P(2, "p2", B31[0], "지문 02 본문 — 자리 + 임시 글")
st += question(2, 31, B31[1], "문항 — 아이콘 · 발문 · 상자 · 문항 지문")
st += [S("꼬리 — 쪽번호", 1200)]
st += T(2, "f-t", 178.27, 285.53, "STEP 02", 6, "#231f20", EL, 700, (178.27, 283.62, 10.48, 2.62))
st += T(2, "f-no", 191.99, 285.53, "31", 6, "#3b4247", EL, 700, (191.99, 283.62, 3.03, 2.62), search=0.6)
st += done("31쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("09 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
for b in B30 + B31:
    print(f"  글 x={b[0]:.2f}~{b[5]:.2f} 기준선 {b[1]:.2f}~{b[2]:.2f} · 행간 {b[6]}pt · 자간 {b[7]} · {sum(len(t) for t, _ in b[3])}자")
