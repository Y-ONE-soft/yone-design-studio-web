"""단위 07 C빈칸어휘 — 원본 d1 reference.pdf 24·25쪽(펼침 두 면)을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.

면 구조 (원본 PDF 에서 읽은 것):
  머리(크림 띠·선·파란 막대·STEP 01 FRAME·C2 빈칸 어휘·단계 점) · 지문 번호(01 / 02)와 분홍 세로줄 · 쪽번호
  문항마다 — 번호(롯데마트드림 Bold 9pt 하늘색) · 빈칸 문장(Noto 8pt, 빈칸 = 분홍 굵은 9pt 첫 글자 + 17.3mm 밑줄) · 해석(Noto Medium 8pt 회색)
자리 이름: 지문번호 · 문항번호 · 빈칸문장 · 해석. 빈칸은 원고에 `m_____` 꼴(첫 글자 + 밑줄 문자)로 오고,
GREP 스타일 둘이 모양을 입힌다 — `[A-Za-z](?=_)` 분홍 굵은 9pt(기준선 -0.37pt) · `_+` 정한 폭(17.3mm) 밑줄 칸.

문항마다 글상자 셋(번호·문장·해석)은 첫 문항만 그려 스타일을 매기고, 나머지는 「⧉ 복제」 후 자리(x·y)만 친다(인디자인에서 복제하듯).
값은 모두 원본 PDF 에서 — 기준선·글자 위치·선 굵기·내림. 측정 보정(보정.json) 없음.
"""
import json, os, statistics, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)                                                # mkpage.chrome_extent 가 core.units.render 를 쓴다
from mkpage import *                                                    # noqa
import pagecmp
import pymupdf

REF = os.path.join(REPO, "tests/e2e/replay/_원본/워크북_d1.pdf")
REFDOC = pymupdf.open(REF)
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
LOTTE = "12LotteMartDreamBold"
INK, PINK, NUMC, KORC = "#231f20", "#c64a86", "#92b0d3", "#58595b"
RA = {pg: pagecmp.page_array(REF, PAGES[pg - 1]) for pg in (1, 2)}      # 원본 쪽 그림(300dpi) — 잴 요소의 잉크 상자를 여기서


def ink(pg, color, x, y, w, h, tol=40):
    """원본 쪽에서 그 색 잉크 상자(mm) — 잴 요소의 자리"""
    return pagecmp.color_box(RA[pg], color, x, y, w, h, pad=0, tol=tol)


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, rotate=None, at=None, w=None, align=None,
      temp=None, track=None):
    """원본 글 하나(02B 와 같다). x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 글자 위치에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    if track is None:
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s, "size": size})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    if at:                                                                  # 돌린 글 — 상자 가운데(돌리는 축)
        cx, cy = at
        bx, by = cx - bw / 2, cy - bh / 2
    else:
        bx, by = x, top_of(base, size, family, weight, leading)
    st = text(round(bx, 2), round(by, 2), bw, bh, temp or s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)
    if rotate:
        st.append(F('#side input[data-a="rotate"]', rotate, 600))
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


def tab_text(pg, id, s, color, y0, y1, bh_size=6.5):
    """오른쪽 탭의 돌린 글(아래에서 위로 읽는다). 원본: 기준선 X = 207.0, 첫 글자 기준점 Y = y0, 끝 글자 끝 Y = y1.
    돌리기는 상자 가운데가 축(render._wrap_atom) — 돌린 뒤 기준선이 원본 X 에, 글자 줄 가운데가 원본 가운데에 오게 상자 가운데를 푼다.
      편집기 글줄(돌리기 전): 기준선 = 위 끝 + 반 행간 + 윗높이 → 상자 가운데에서 (반 행간 + 윗높이 - 상자 높이/2) 아래.
      -90° 돌리면 그 거리가 X 로 간다: 기준선 X = cx + (반 행간 + 윗높이 - bh/2).
      가운데 정렬은 끝 글자 뒤 자간까지 넣어 가운데에 놓는다 → 글자 줄 가운데 = cy + 자간/2.
    자간 = (원본 첫~끝 글자 기준점 거리 - 브라우저 같은 거리) / 사이 수 (track_from 과 같은 식, 세로로)."""
    size = 6.5
    asc, desc, _ = face(MS, 700)
    p = REFDOC[PAGES[pg - 1] - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    ch = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                for c in sp["chars"]:
                    X, Y = (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM
                    if abs(X - 207.0) < 0.5 and y1 - 0.5 < Y < y0 + 0.5 and c["c"].strip():
                        ch.append(Y)
    ch = sorted(set(round(v, 3) for v in ch), reverse=True)
    track = round(((ch[0] - ch[-1]) - chrome_extent(MS, 700, size, s)) / (len(s) - 1) / (size * MM) * 1000) if len(s) > 1 else 0
    ls = track / 1000 * size * MM
    L = size * 1.45 * MM
    bh = round(L + 0.4, 1)
    hl = (L - (asc + desc) * size * MM) / 2
    cx = 207.0 - (hl + asc * size * MM - bh / 2)
    cy = (y0 + y1) / 2 - ls / 2
    ELEMS[pg].append({"id": id, "x": 204.54, "y": y1, "w": 3.08, "h": y0 - y1, "color": color, "see": color, "ctol": 30, "search": 0.8,
                      "text": s, "size": size})
    bw = 14
    st = text(round(cx - bw / 2, 2), round(cy - bh / 2, 2), bw, bh, s, size, color, font=MS, weight=700, track=track or None, align="center")
    st.append(F('#side input[data-a="rotate"]', -90, 600))
    return st


def header_left(pg, code, title, title_x, title_bbox, code_bbox):
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, "#77a1c4")
    st += T(pg, "t-step", 20.0, 8.93, "STEP 01", 8, "#77a1c4", NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 01 · FRAME")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", 32.35, 8.93, "FRAME", 8, "#b4aa9a", NOTO, 700, (32.35, 3.84, 9.62, 8.05))
    st += T(pg, "t-code", 20.0, 19.47, code, 25, "#77a1c4", MAMA, 400, code_bbox, label="제목 — 코드 · 이름")
    st += T(pg, "t-title", title_x, 17.58, title, 13, INK, GM, 500, title_bbox)
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, fill="#77a1c4")
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)          # 원본 획 0.28mm = 0.79pt
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    for k, (nx, nw, col) in enumerate(((57.79, 0.83, "#ffffff"), (68.58, 1.25, "#b4aa9a"), (79.57, 1.25, "#b4aa9a"))):
        st += T(pg, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), search=0.6)
    return st


# ── 원본 문항 읽기 ─────────────────────────────────────────
def items(pno):
    """원본 쪽의 문항 — [(번호 기준선, 번호 x, 번호 글, [(기준선, 글, 분홍 있나)] 영어 줄, [(기준선, 글)] 해석 줄)]
    영어 줄의 분홍 9pt 글자(빈칸 첫 글자) 뒤에는 원고 꼴 그대로 `_____` 를 붙인다(밑줄은 원본에서 선이다)."""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    chars = []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                for c in s["chars"]:
                    x = (c["origin"][0] - ox) * MM
                    if 24 < x < 200:                                        # 지문 번호(왼쪽)·탭 글(오른쪽) 빼고
                        chars.append(((s["origin"][1] - oy) * MM, x, c["c"], s["font"], round(s["size"], 1), len(chars), (c["bbox"][2] - ox) * MM))
    nums = sorted({round(t[0], 2) for t in chars if "LotteMart" in t[3]})
    out = []
    for i, nb in enumerate(nums):
        lo, hi = nb - 2, (nums[i + 1] - 2 if i + 1 < len(nums) else 260)
        ch = [t for t in chars if lo <= t[0] < hi]
        nch = sorted((t for t in ch if "LotteMart" in t[3]), key=lambda t: t[5])
        rows = {}
        for t in ch:
            if "LotteMart" in t[3]:
                continue
            kind = "k" if "Medium" in t[3] else "e"
            yb = t[0] - (0.13 if t[4] == 9 else 0)                         # 9pt 첫 글자는 기준선이 0.13mm 아래
            key = next((k for k in rows if k[0] == kind and abs(k[1] - yb) < 0.35), (kind, yb))
            rows.setdefault(key, []).append(t)
        eng, kor = [], []
        for (kind, _), ts in sorted(rows.items(), key=lambda kv: kv[0][1]):
            ts.sort(key=lambda t: t[5])
            txt = "".join(t[2] + ("_____" if t[4] == 9 else "") for t in ts)
            base = min(t[0] for t in ts if t[4] == 8)
            if kind == "e":
                eng.append((base, txt, any(t[4] == 9 for t in ts), [(t[1], t[6]) for t in ts if t[4] == 9]))
            else:
                kor.append((base, txt))
        out.append((nb, nch[0][1], "".join(t[2] for t in nch).strip(), eng, kor))
    return out


def join_en(lines):
    t = lines[0][1]
    for _, s, _, _ in lines[1:]:
        t = t.rstrip(" ") + " " + s                                          # 다음 줄이 공백으로 시작하면(원본 두 칸) 그대로 둔다
    return t.strip()


def join_kr(lines):
    return "".join(s for _, s in lines).strip()                             # 한글은 낱말 중간에서도 꺾인다 — 줄 끝 공백이 있으면 그대로


# 원본 밑줄 — 굵기·기준선 아래 거리(선 가운데)
def underline_stats():
    ws, offs = [], []
    for pno in PAGES:
        p = REFDOC[pno - 1]
        oy = p.trimbox.y0
        bases = [e[0] for it in items(pno) for e in it[3]]
        for g in p.get_drawings():
            if g.get("color") is not None and abs(g["rect"].width * MM - 17.3) < 0.05:
                ws.append(g["width"] * MM)
                yc = (g["rect"].y0 - oy) * MM
                b = min(bases, key=lambda v: abs(v - yc))
                offs.append(yc - b)
    return round(statistics.median(ws), 3), round(statistics.median(offs), 2)


LINE_W, LINE_OFF = underline_stats()
BLANK = 17.3                                                                # 원본 밑줄 길이(모두 같다)
TRACK = -40                                                                 # 영어·해석·번호 모두 글자 간격 - 서체 폭 = -40 (scratch a1/a6)
def word_spacing(medium):
    """낱말 사이(‰) = 원본 공백 폭(자간 포함, PDF 글자 기준점 사이 중앙값) - 브라우저 공백 폭(자간 없이, chrome_extent) - 자간.
    서체 파일 hmtx(0.224em)가 아니라 브라우저 값으로 — 크롬은 이 서체의 공백을 0.280em 으로 놓는다(scratch ws_test)."""
    gaps = []
    for pno in PAGES:
        for b in REFDOC[pno - 1].get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            for l in b.get("lines", []):
                ch = [(c, s) for s in l["spans"] for c in s["chars"]]
                for (c, s), (n, _) in zip(ch, ch[1:]):
                    if c["c"] == " " and "Noto" in s["font"] and (("Medium" in s["font"]) == medium) and "Bold" not in s["font"]:
                        gaps.append((n["origin"][0] - c["origin"][0]) / s["size"])
    w = 500 if medium else 400
    chrome_sp = (chrome_extent(NOTO, w, 8, "a b") - chrome_extent(NOTO, w, 8, "ab")) / (8 * MM)
    return round((statistics.median(gaps) - chrome_sp - TRACK / 1000) * 1000)


WS_EN, WS_KR = word_spacing(False), word_spacing(True)
LEAD_EN, LEAD_KR = 18.5, 12                                                 # 영어 줄 간격 6.52mm = 18.5pt · 해석 두 줄 4.23mm = 12pt
BSHIFT = -0.37                                                              # 빈칸 첫 글자 기준선 = 본문 기준선 + 0.13mm(=0.37pt) 아래
_asc, _desc, _ = face(NOTO, 400)
PINK_DROP = (_asc - _desc) / 2 * (9 - 8) * MM   # 9pt 글자가 든 줄: 행간 고정(px) 줄 상자가 위로 (윗높이-아랫높이)/2 × 1pt 자란다 → 기준선이 그만큼 내려간다
                                                # (원본도 분홍 줄은 0.18mm 아래 · 둘째 줄 간격 6.70 = 6.52 + 0.18)
TEMP_EN = "A w_____ sentence for s_____ the style."
TEMP_KR = "임시 해석 문장입니다."
CONTENT = {"지문번호": [], "문항번호": [], "빈칸문장": [], "해석": []}


def measure_en(pg, no, eng, x_en, right):
    """빈칸 문장의 잴 요소 — 줄마다 검은 글(기준선 +0.1mm 까지 — 밑줄은 따로), 밑줄 칸마다 선, 분홍 첫 글자마다 글자.
    한 줄 전체를 한 상자로 재면 모양 검사가 상자 안의 다른 색 가장자리(검은 글·밑줄의 회색 번짐)까지 세어
    분홍 글자는 같은데 잉크 0.77~1.53 이 나오고(scratch u07_ink: 글자별 화소 수는 1~3% 안), 1화소 남짓한 밑줄은 래스터 위치에 따라
    잉크가 반 줄씩 달라진다(같은 굵기·같은 자리인데). 그래서 글·선·첫 글자를 따로 잰다."""
    p = REFDOC[PAGES[pg - 1] - 1]
    oy = p.trimbox.y0
    ox = p.trimbox.x0
    lines = [g for g in p.get_drawings() if g.get("color") is not None and abs(g["rect"].width * MM - BLANK) < 0.05]
    for li, (base, txt, _, pinks) in enumerate(eng):
        e_ink = ink(pg, INK, x_en - 0.6, base - 3.0, right - x_en + 1.2, 3.1)   # 기준선 +0.1mm 까지 — 밑줄 번짐(+0.26mm~)이 안 닿게
        ELEMS[pg].append({"id": f"e{no}{li}", "x": e_ink[0], "y": e_ink[1], "w": e_ink[2], "h": e_ink[3], "color": INK, "see": INK, "ctol": 40,
                          "pad": 0, "search": 0.05, "text": txt[:30], "size": 8, "shape_iou": 0.80})
        for j, g in enumerate(sorted((g for g in lines if 0.2 < (g["rect"].y0 - oy) * MM - base < 0.7), key=lambda g: g["rect"].x0)):
            lw = g["width"] * MM
            ELEMS[pg].append({"id": f"u{no}{li}{j}", "x": round((g["rect"].x0 - ox) * MM, 2), "y": round((g["rect"].y0 - oy) * MM - lw / 2, 2),
                              "w": BLANK, "h": round(lw, 3), "color": INK, "see": INK, "ctol": 40 if lw > 0.15 else 110, "pad": 0.1, "search": 0.1})
            # 찾는 폭 0.1mm — 칸 바로 뒤 쉼표(검은 글, 기준선 아래로 내려온다)가 선 상자에 섞이지 않게.
            # 원본 24쪽 첫 칸만 선이 0.10mm(나머지 0.176) — 300dpi 에선 옅어 색 허용을 넓혀야 잡힌다(굵기 차이는 보고).
        for j, (x0, x1) in enumerate(pinks):
            b = ink(pg, PINK, x0 - 0.1, base - 2.8, x1 - x0 + 0.2, 3.7)
            ELEMS[pg].append({"id": f"b{no}{li}{j}", "x": b[0], "y": b[1], "w": b[2], "h": b[3], "color": PINK, "see": PINK, "ctol": 40,
                              "pad": 0.1, "search": 0.3, "size": 9, **({"text": "빈칸 첫 글자"} if b[2] > 1.2 else {})})
            # 폭 1.2mm 안 글자(l·i·t)는 모양 검사를 뺀다 — 화소 수는 원본과 같아도(scratch u07_ink: 155 대 155) 상자 폭이 1화소(8 대 7)
            # 다르면 잴 때 늘려 맞추며 잉크가 ±13~20% 흔들린다(t: 175 대 164 화소인데 0.87). 자리·크기(0.3mm)는 그대로 잰다.


def dup(x, y, h=None):
    """고른 글상자 「⧉ 복제」 → 자리(와 높이)만 새로"""
    return ([{"click": "#side #s-dup", "wait": 700}, F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]
            + ([F('#side input[data-a="h"]', h)] if h is not None else []))


def body(pg, its, x_num, x_en, right):
    """문항 글상자 — 번호 줄 · 문장 줄 · 해석 줄을 차례로. 첫 상자만 스타일을 매기고 나머지는 복제."""
    w_en = round(right - x_en + TRACK / 1000 * 8 * MM + 0.03, 2)         # 끝 글자 뒤 자간(크롬은 줄 끝에도 둔다)만큼 좁게
    x_kr = round(x_en + 0.5, 2)
    w_kr = round(right - x_kr + TRACK / 1000 * 8 * MM + 0.1, 2)
    st = [S("문항 번호 — 첫 번호를 그리고 복제", 1500)]
    for k, (nb, nx, no, eng, kor) in enumerate(its):
        CONTENT["문항번호"].append(no)
        box_ = ink(pg, NUMC, nx - 0.3, nb - 3.2, 6, 3.6)
        ELEMS[pg].append({"id": f"q{no}", "x": box_[0], "y": box_[1], "w": box_[2], "h": box_[3], "color": NUMC, "see": NUMC, "ctol": 30,
                          "pad": 0.6, "search": 0.8, "text": no, "size": 9})
        if k == 0:
            st += T(pg, f"q{no}-t", nx, nb, no, 9, NUMC, LOTTE, 400, (nx, nb - 2.73, 3.85, 3.63), temp="00.", label="문항 번호 자리")
            ELEMS[pg].pop()                                                  # 잴 자리는 위(잉크 상자)로
            st += slot("문항번호")
        else:
            st += dup(nx, round(top_of(nb, 9, LOTTE, 400), 2))
    st += [S("빈칸 문장 — 임시 글 · 자리 · 스타일 · GREP 둘(빈칸 첫 글자 · 밑줄 칸)", 1700)]
    for k, (nb, nx, no, eng, kor) in enumerate(its):
        CONTENT["빈칸문장"].append(join_en(eng))
        b0 = eng[0][0] - (PINK_DROP if eng[0][2] else 0)
        y = round(top_of(b0, 8, NOTO, 400, LEAD_EN), 2)
        measure_en(pg, no, eng, x_en, right)
        if k == 0:
            st += text(x_en, y, w_en, round(len(eng) * LEAD_EN * MM + 0.6, 2), TEMP_EN, 8, INK, label="빈칸 문장 자리 — 임시 글",   # 상자 높이 = 그 글의 줄 수(아래 해석·다음 문항이 상자 영역 안에 들지 않게 — 원고가 길어지면 아래를 민다)
                       leading=LEAD_EN, align="justify", font=NOTO, track=TRACK)
            st += slot("빈칸문장", label="자리 이름 「빈칸문장」")
            st += justify()                                              # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
            st += [F('#side input[data-a="indent"]', 0.5), F('#side input[data-a="indent_first"]', -0.5)]   # 둘째 줄부터 0.5mm 안(원본 30.5 / 첫 줄 30.0)
            if abs(WS_EN) > 5:
                st.append(F('#side input[data-a="word_spacing"]', WS_EN))
            st += grep(0, r"[A-Za-z](?=_)", PINK, size=9, bshift=BSHIFT, label="GREP — 빈칸 첫 글자: 분홍 굵은 9pt")
            st += grep(1, r"_+", bold=False, blank=BLANK, line=LINE_W, line_off=LINE_OFF, line_color=INK,
                       label=f"GREP — 밑줄 문자는 {BLANK}mm 밑줄 칸(선 {LINE_W}mm · 기준선 아래 {LINE_OFF}mm)")
        else:
            st += dup(x_en, y, round(len(eng) * LEAD_EN * MM + 0.6, 2))
    st += [S("해석 — 임시 글 · 자리 · 스타일, 나머지는 복제", 1500)]
    for k, (nb, nx, no, eng, kor) in enumerate(its):
        CONTENT["해석"].append(join_kr(kor))
        y = round(top_of(kor[0][0], 8, NOTO, 500, LEAD_KR), 2)
        lo, hi = kor[0][0] - 2.9, kor[-1][0] + 0.9
        k_ink = ink(pg, KORC, x_kr - 0.6, lo, right - x_kr + 1.2, hi - lo)
        ELEMS[pg].append({"id": f"k{no}", "x": k_ink[0], "y": k_ink[1], "w": k_ink[2], "h": k_ink[3], "color": KORC, "see": KORC, "ctol": 40,
                          "pad": 0.6, "search": 1.0, "text": join_kr(kor)[:30], "size": 8})
        if k == 0:
            st += text(x_kr, y, w_kr, round(len(kor) * LEAD_KR * MM + 0.6, 2), TEMP_KR, 8, KORC, label="해석 자리 — 임시 글",
                       leading=LEAD_KR, align="justify", font=NOTO, track=TRACK, weight=500)   # 원본 해석도 양끝맞춤(두 줄 23번 첫 줄)
            st += slot("해석", label="자리 이름 「해석」")
            st += justify()                                              # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
            if abs(WS_KR) > 5:
                st.append(F('#side input[data-a="word_spacing"]', WS_KR))
        else:
            st += dup(x_kr, y, round(len(kor) * LEAD_KR * MM + 0.6, 2))
    return st


def passage_no(pg, no, x, w_ink, bar_x):
    """지문 번호(영도 12pt) — 자리, 옆 분홍 세로줄(같은 서체의 │)은 고정 글"""
    st = T(pg, f"no{no}", x, 36.90, no, 12, "#af9d81", YD, 400, (x, 33.7, w_ink, 3.6), search=0.6, label="지문 번호 자리", temp="00")
    st += slot("지문번호")
    CONTENT["지문번호"].append(no + " ")                                  # 원본 그대로 「01 」 — 끝 공백이 영도체 1 의 끝 꼴(꼬리)을 정한다
    st += T(pg, f"bar{no}", bar_x, 36.90, "│", 12, "#da95b5", YD, 400, (bar_x, 33.4, 4.23, 4.6), label="분홍 세로줄")
    b = ink(pg, "#da95b5", bar_x + 1.5, 33.0, 1.5, 5.0, tol=20)
    ELEMS[pg][-1].update({"x": b[0], "y": b[1], "w": b[2], "h": b[3], "pad": 0.3, "search": 0.5, "ctol": 20})   # 가는 줄 — 옆 번호(갈색) 가장자리가 안 섞이게
    ELEMS[pg][-1].pop("text")         # 폭 0.1mm 남짓(300dpi 1화소) 세로줄 — 모양 검사 잉크가 래스터 위치에 따라 두 배까지 흔들린다(밑줄과 같은 이유) → 선처럼 자리·크기만
    return st


# ── 24쪽 (왼쪽 면) ──────────────────────────────────────────
_, _, adv_gm = face(GM, 500)
_TT, _TX, _TW = " 빈칸 어휘", 30.86, 18.5                                      # 원본 조각(공백으로 시작) — 자리·폭
_tr = (_TW - adv_gm(_TT) * 13 * MM) / len(_TT)                              # 글자마다 자간(mm) — 앞 공백에도 들어간다
TITLE_X = round(_TX + adv_gm(" ") * 13 * MM + _tr, 2)                     # 글자는 공백(자간 포함) 다음부터
st = open_doc("스텝바이스텝 워크북 C2 (A4)")
st += expect_pages(1)
# 오른쪽 속성 패널을 넓힌다(경계를 끌어서) — 기본 폭 240px 에선 4칸 줄(「낱말 사이 ‰」 등)의 숫자 칸이 좁아 가운데를 누르면
# 증감 단추(▼)가 눌려 값이 -10 으로 바뀌고 패널이 다시 그려진다(그 뒤 지우기 키가 글상자를 지운다). 넓히면 가운데가 글 칸이다.
st += [S("속성 패널 넓히기", 900), {"drag": {"from": '[data-rsz="r"]', "to": [1200, 500]}, "wait": 800}]
st += [S("① 24쪽 — C2 빈칸 어휘", 1500)]
st += header_left(1, "C2", "빈칸 어휘", TITLE_X, (TITLE_X, 13.70, _TW - (TITLE_X - _TX), 5.44), (20.0, 12.18, 9.39, 9.78))
st += passage_no(1, "01", 12.78, 3.41, 17.16)
st += body(1, items(PAGES[0]), 25.0, 30.0, 183.0)
st += [S("꼬리 — 쪽번호", 1200)]
st += T(1, "f-no", 15.23, 285.53, "24", 6, "#3b4247", EL, 700, (15.23, 283.62, 3.24, 2.62), search=0.6)
st += T(1, "f-t", 20.9, 285.53, "STEP BY STEP", 6, INK, EL, 700, (20.9, 283.62, 17.68, 2.62))
st += done("24쪽", "p1.png")

# ── 25쪽 (오른쪽 면) ────────────────────────────────────────
st += add_page("② 25쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(2, "tag-t", 187.05, 21.84, "STEP BY STEP", 6, "#ffffff", MS, 700, (187.05, 19.56, 15.43, 2.84), search=0.6)
ELEMS[2][-1].update({"pad": 0.3, "search": 0.3})                          # 흰 글 — 잴 창을 꼬리표 안으로(바깥 흰 바탕이 섞이지 않게)
st += T(2, "t-code", 186.67, 15.99, "C2", 36, "#77a1c4", MS, 500, (186.67, 2.62, 16.21, 16.71), label="큰 코드 C2")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
st += tab_text(2, "tab1-t", "STEP 01", "#ffffff", 77.07, 68.93)
st += tab_text(2, "tab2-t", "02", "#cba56f", 104.36, 101.64)
st += tab_text(2, "tab3-t", "03", "#bc736c", 134.36, 131.64)
st += passage_no(2, "02", 14.78, 3.84, 19.59)
st += body(2, items(PAGES[1]), 27.0, 32.0, 185.0)
st += [S("꼬리 — 쪽번호", 1200)]
st += T(2, "f-t", 179.16, 285.53, "STEP01", 6, INK, EL, 700, (179.16, 283.62, 9.59, 2.62))
st += T(2, "f-no", 191.75, 285.53, "25", 6, "#3b4247", EL, 700, (191.75, 283.62, 3.27, 2.62), search=0.6)
st += done("25쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("07 단계", len(st), f"· 낱말 사이 {WS_EN}/{WS_KR}‰", "· 잴 요소", sum(len(v) for v in ELEMS.values()), f"· 밑줄 {LINE_W}mm 내림 {LINE_OFF}mm · 분홍 줄 내림 {PINK_DROP:.3f}mm")
for k, v in CONTENT.items():
    print(" ", k, len(v), "·", v[:2] if k != "빈칸문장" else v[7])
