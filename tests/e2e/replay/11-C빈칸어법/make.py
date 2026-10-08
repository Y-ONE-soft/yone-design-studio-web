"""단위 11 C빈칸어법 — 원본 d1 reference.pdf 38·39쪽(펼침 두 면)을 원고 자리 규약(docs/편집기_재현/원고자리_규약.md)대로.
짝 단위: 07-C빈칸어휘(같은 C 빈칸 꼴 — 문항마다 번호·빈칸 문장·해석) · 09-A어법선택(STEP 02 머리·탭·GREP 약속 괄호).

면 구조 (원본 PDF 에서 읽은 것):
  머리(크림 띠·선·베이지 막대·STEP 02 BUILD UP·C1 빈칸 어법·단계 점 2 찬 원) · 지문 번호(01 / 02)와 같은 색 세로줄 · 쪽번호
  문항마다 — 번호(롯데마트드림 Bold 9pt 청록 「1.」) · 빈칸 문장(Noto 8pt 양끝맞춤 행간 20pt) · 해석(Noto Medium 8pt 회색 행간 12pt)
  빈칸 = 정답 낱말 자리의 밑줄(0.5pt). 밑줄 길이는 정답마다 다르다 — 원본 71칸 실측:
      길이 = 정답 글 폭(8.5pt) + 글자 수 × 0.969mm + 1.99mm  (최대 오차 0.098mm, scratch fit2)
  → 인디자인에서 정답 글을 「칠 없음」으로 감추고 밑줄만 남긴 꼴(글 PDF 에 정답 글자가 없다 — 칠 없는 글은 안 찍힌다).
자리 이름: 지문번호 · 문항번호 · 빈칸문장 · 해석. 빈칸문장 원고는 정답을 약속 괄호로 — `A {missing} hiker {named} …`.
정답은 같은 책 원본 8·9쪽(A본문OX 지문)에서 빈칸 문장의 앞뒤 글로 찾는다(71칸 모두 찾음).

값은 모두 원본 PDF 에서 — 기준선·글자 위치·선 굵기·내림·자간. 측정 보정(보정.json) 없음.
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
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium
LOTTE = "12LotteMartDreamBold"
BEIGE = "#cba56f"              # STEP 02 색
INK, NUMC, KORC, PNO = "#231f20", "#75abab", "#58595b", "#af9d81"
RA = {pg: pagecmp.page_array(REF, PAGES[pg - 1]) for pg in (1, 2)}      # 원본 쪽 그림(300dpi) — 잴 요소의 잉크 상자를 여기서


def hexc(c):
    return "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


def ink(pg, color, x, y, w, h, tol=40):
    """원본 쪽에서 그 색 잉크 상자(mm) — 잴 요소의 자리"""
    return pagecmp.color_box(RA[pg], color, x, y, w, h, pad=0, tol=tol)


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, w=None, align=None, temp=None, track=None):
    """원본 글 하나(07 과 같다). x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 글자 위치에서 계산한다."""
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    if track is None:
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s, "size": size})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    return text(round(x, 2), round(top_of(base, size, family, weight, leading), 2), bw, bh, temp or s, size, color, label=label,
                font=family, weight=weight if weight != 400 else None, track=track or None, leading=leading, align=align)


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


def rot_spans(pno):
    """원본 쪽의 돌린 글(아래에서 위로 읽는 탭 글) 조각 — 09 와 같다. 원본은 같은 글이 두 번 겹쳐 있어 한 번만"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    out, seen = [], set()
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (0.0, -1.0):
                continue
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                t = "".join(c["c"] for c in sp["chars"]).strip()
                if not ch or t in seen:
                    continue
                seen.add(t)
                out.append({"text": t, "color": "#%06x" % sp["color"], "x0": (ch[0]["bbox"][0] - ox) * MM,
                            "chars": [(c["c"], (c["origin"][0] - ox) * MM, (c["origin"][1] - oy) * MM) for c in ch]})
    return sorted(out, key=lambda r: r["chars"][0][2])


def TR(pg, id, sp, size, color, family, weight, w=14, label=None):
    """돌린 글 — 09 의 TR 과 같은 계산(편집기는 글상자를 가운데 기준으로 돌린다)."""
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


def title_seg(pno):
    p = REFDOC[pno - 1]
    sp = next(s for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if "어법" in "".join(c["c"] for c in s["chars"]))
    return round((sp["origin"][0] - p.trimbox.x0) * MM, 3), round((sp["bbox"][2] - sp["bbox"][0]) * MM, 3)


def header_left(pg, code, tt, seg):
    """왼쪽 면 머리 — 09 와 같은 꼴(STEP 02 · BUILD UP · 단계 점 2 찬 원), 코드·제목은 원본 38쪽에서"""
    o, wd = seg                                                             # 제목 조각(공백으로 시작) 시작 x · 폭
    _, _, adv_gm = face(GM, 500)
    tr = (wd - adv_gm(tt) * 13 * MM) / len(tt)                              # 글자마다 자간(mm) — 앞 공백에도 들어간다
    tx = round(o + adv_gm(" ") * 13 * MM + tr, 2)                           # 글자는 공백(자간 포함) 다음부터
    cb = ink(pg, BEIGE, 19.0, 11.0, 10.5, 12.0)                             # 원본 코드 「C1」 잉크 상자
    st = [S("머리 — 크림 띠 · 선 · 베이지 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, BEIGE)
    st += T(pg, "t-step", 20.0, 8.93, "STEP 02", 8, BEIGE, NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 02 · BUILD UP")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", 32.35, 8.93, "BUILD UP", 8, "#b4aa9a", NOTO, 700, (32.35, 3.84, 13.59, 8.05))
    st += T(pg, "t-code", 20.0, 19.47, code, 25, BEIGE, MAMA, 400, tuple(cb), label="제목 — 코드 · 이름")
    st += T(pg, "t-title", tx, 17.58, tt.strip(), 13, INK, GM, 500, (tx, 13.70, wd - (tx - o), 5.44))
    st += [S("단계 점 셋 — 지금 단계(2)가 찬 원", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, fill=BEIGE)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
    for k, (nx, nw, col) in enumerate(((57.79, 0.82, "#b4aa9a"), (68.58, 1.24, "#ffffff"), (79.57, 1.26, "#b4aa9a"))):
        st += T(pg, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), search=0.6)
    return st


# ── 원본 문항 읽기 ─────────────────────────────────────────
PASSAGE = " ".join(" ".join(REFDOC[p - 1].get_text().split()) for p in (8, 9))   # 같은 책 A본문OX 지문(01·02) — 정답 찾기
LINE_W = None                                                               # 원본 밑줄 굵기(mm) — 아래 items 에서


def underlines(pno):
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    return [((g["rect"].x0 - ox) * MM, (g["rect"].x1 - ox) * MM, (g["rect"].y0 - oy) * MM, g["width"] * MM)
            for g in p.get_drawings() if g["type"] == "s" and g["rect"].height == 0 and g.get("color") and hexc(g["color"]) == INK
            and 0.15 < g["width"] * MM < 0.2]


def items(pno):
    """원본 쪽의 문항 — [(번호 기준선, 번호 x, 번호 글, 영어 줄[(기준선, 글(빈칸=\\x00), [(x0, x1, 선 y, 선 굵기)])], 해석 줄[(기준선, 글)], 정답[])]"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    nums, eng, kor = [], [], []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = "".join(c["c"] for c in s["chars"])
                base, x = (s["origin"][1] - oy) * MM, (s["origin"][0] - ox) * MM
                if "LotteMart" in s["font"]:
                    nums.append((base, x, t.strip()))
                elif "Medium" in s["font"] and "Noto" in s["font"]:
                    kor.append((base, x, t))
                elif "Noto" in s["font"] and "Regular" in s["font"] and s["size"] < 8 and t.strip() or ("Noto" in s["font"] and t == " " and x > 32.5 and s["size"] < 8):
                    eng.append((base, x, t))
    uls = underlines(pno)
    nums.sort()
    out = []
    for i, (nb, nx, no) in enumerate(nums):
        lo, hi = nb - 2, (nums[i + 1][0] - 2 if i + 1 < len(nums) else 260)
        x_en = min(e[1] for e in eng if lo <= e[0] < hi and e[2].strip())
        toks = [(e[0], e[1], e[2]) for e in eng if lo <= e[0] < hi and e[1] >= x_en - 0.1]
        toks += [(u[2] - 0.77, u[0], u) for u in uls if lo <= u[2] - 0.77 < hi]
        rows = []
        for t in sorted(toks, key=lambda t: t[0]):
            r = next((r for r in rows if abs(r[0] - t[0]) < 0.6), None)
            if r is None:
                rows.append([t[0], [t]])
            else:
                r[1].append(t)
        en = []
        for _, ts in rows:
            ts.sort(key=lambda t: t[1])
            txt = "".join(t[2] if isinstance(t[2], str) else "\x00" for t in ts)
            texts = [t[0] for t in ts if isinstance(t[2], str)]
            base = min(texts) if texts else ts[0][0]
            en.append((base, txt, [t[2] for t in ts if not isinstance(t[2], str)]))
        ko = sorted((k[0], k[2]) for k in kor if lo <= k[0] < hi)
        sent = en[0][1]
        for _, s, _ in en[1:]:
            sent = sent.rstrip(" ") + " " + s.lstrip(" ")
        sent = sent.strip()
        answers = []
        if "\x00" in sent:
            rx = re.escape(sent).replace("\x00", "([A-Za-z']+)").replace("\\ ", r"\s+")
            m = re.search(rx, PASSAGE)
            if not m:
                raise RuntimeError(f"정답 못 찾음: {pno}쪽 {no} {sent!r}")
            answers = list(m.groups())
        out.append((nb, nx, no, en, ko, answers, sent))
    return out


def marked(sent, answers):
    """원고 꼴 — 빈칸 자리에 정답을 약속 괄호로: `A {missing} hiker …`"""
    it = iter(answers)
    return re.sub("\x00", lambda m: "{" + next(it) + "}", sent)


HS = 99                         # 장평(가로 %) — 원본 영어·번호는 가로 99%(PDF 글자 행렬 `7.92 0 0 8` · `8.91 0 0 9`), 해석은 100%


def word_track(pred, size, family, weight, scale=1.0, minlen=6, alpha=True):
    """낱말 안 글자 간격(‰) — (원본 첫~끝 글자 원점 거리 / 장평 - 크롬 거리) / 사이 수 의 중앙값.
    장평은 글자·자간을 함께 가로로 줄이므로 원본 거리를 장평으로 나눠 100% 거리로 되돌린다.
    양끝맞춤으로 늘어난 줄의 낱말은 중앙값에서 빠진다(원본 38·39쪽)."""
    tr = []
    for pno in PAGES:
        for b in REFDOC[pno - 1].get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            for l in b.get("lines", []):
                for sp in l["spans"]:
                    if not pred(sp):
                        continue
                    words, cur = [], []
                    for c in sp["chars"]:
                        if c["c"] in " \t":
                            if cur: words.append(cur)
                            cur = []
                        else:
                            cur.append(c)
                    if cur: words.append(cur)
                    for w in words:
                        t = "".join(c["c"] for c in w)
                        if len(t) >= minlen and (t.isascii() and t.isalpha() if alpha else True) and len(tr) < 40:
                            o = (w[-1]["origin"][0] - w[0]["origin"][0]) * MM / scale
                            tr.append((o - chrome_extent(family, weight, size, t)) / (len(t) - 1) / (size * MM) * 1000)
    return round(statistics.median(tr))


TRACK_EN = word_track(lambda sp: "Noto" in sp["font"] and "Regular" in sp["font"] and sp["size"] < 8, 8, NOTO, 400, HS / 100)
TRACK_KR = word_track(lambda sp: "Noto" in sp["font"] and "Medium" in sp["font"], 8, NOTO, 500)
TRACK_NO = word_track(lambda sp: "LotteMart" in sp["font"], 9, LOTTE, 400, HS / 100, minlen=3, alpha=False)   # 「10.」~「23.」


def word_spacing(medium):
    """낱말 사이(‰) = 원본 공백 폭(자간 포함, 글자 기준점 사이 중앙값) - 브라우저 공백 폭(자간 없이) - 자간 — 07 과 같은 식"""
    gaps = []
    for pno in PAGES:
        for b in REFDOC[pno - 1].get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    if "Noto" not in s["font"] or ("Medium" in s["font"]) != medium or "Bold" in s["font"]:
                        continue
                    for c, n in zip(s["chars"], s["chars"][1:]):
                        if c["c"] == " " and n["c"] != " ":
                            gaps.append((n["origin"][0] - c["origin"][0]) / 8 / (1 if medium else HS / 100))
    w = 500 if medium else 400
    chrome_sp = (chrome_extent(NOTO, w, 8, "a b") - chrome_extent(NOTO, w, 8, "ab")) / (8 * MM)
    return round((statistics.median(gaps) - chrome_sp - (TRACK_KR if medium else TRACK_EN) / 1000) * 1000)


WS_EN, WS_KR = word_spacing(False), word_spacing(True)
LEAD_EN, LEAD_KR = 20, 12                                                   # 영어 줄 간격 7.05mm = 20pt · 해석 두 줄 4.23mm = 12pt (23번)
LINE_OFF = 0.77                                                             # 밑줄 가운데 - 기준선 (원본 모든 칸 0.77mm)
_asc, _desc, _ = face(NOTO, 400)
HID = HID_TRACK = HID_PAD = DROP = None          # 감춘 정답 글 크기·자간·더할 폭 · 빈칸 줄 내림 — 아래 blank_rule() 이 원본 71칸에서
TEMP_EN = "A {word} sentence for {styling} the blank."
TEMP_KR = "임시 해석 문장입니다."
CONTENT = {"지문번호": [], "문항번호": [], "빈칸문장": [], "해석": []}


def measure_en(pg, no, en, x_en, right):
    """빈칸 문장의 잴 요소 — 줄마다 검은 글(기준선 +0.1mm 까지 — 밑줄은 따로), 밑줄 칸마다 선(07 과 같은 까닭으로 따로 잰다)"""
    for li, (base, txt, uls) in enumerate(en):
        e_ink = ink(pg, INK, x_en - 0.6, base - 3.0, right - x_en + 1.2, 3.1)
        if e_ink and txt.replace("\x00", "").strip(" .,"):
            ELEMS[pg].append({"id": f"e{no}{li}", "x": e_ink[0], "y": e_ink[1], "w": e_ink[2], "h": e_ink[3], "color": INK, "see": INK, "ctol": 40,
                              "pad": 0, "search": 0.05, "text": txt.replace("\x00", "_")[:30], "size": 8, "shape_iou": 0.80})
        for j, (x0, x1, yc, lw) in enumerate(sorted(uls)):
            ELEMS[pg].append({"id": f"u{no}{li}{j}", "x": round(x0, 2), "y": round(yc - lw / 2, 2), "w": round(x1 - x0, 2), "h": round(lw, 3),
                              "color": INK, "see": INK, "ctol": 40, "pad": 0.1, "search": 0.1})


def dup(x, y):
    """고른 글상자 「⧉ 복제」 → 자리만 새로"""
    return [{"click": "#side #s-dup", "wait": 700}, F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]


def body(pg, its, right):
    """문항 글상자 — 번호 · 문장 · 해석을 차례로. 첫 상자만 스타일을 매기고 나머지는 복제."""
    x_num = its[0][1]
    x_en = round(x_num + 6.0, 2)                                            # 원본: 번호 25.0 → 글 31.0 (39쪽 27.0 → 33.0) — 탭
    x_kr = round(x_en - 0.5, 2)                                             # 해석은 0.5mm 앞(30.5 / 32.5)
    w_en = round(right - x_en + TRACK_EN / 1000 * 8 * MM + 0.03, 2)         # 끝 글자 뒤 자간(크롬은 줄 끝에도 둔다)만큼 좁게
    w_kr = round(right - KR_IN - x_kr + TRACK_KR / 1000 * 8 * MM + 0.1, 2)
    st = [S("문항 번호 — 첫 번호를 그리고 복제", 1500)]
    for k, (nb, nx, no, en, ko, ans, sent) in enumerate(its):
        CONTENT["문항번호"].append(no)
        b_ = ink(pg, NUMC, nx - 0.3, nb - 3.2, 6, 3.6)
        ELEMS[pg].append({"id": f"q{no}", "x": b_[0], "y": b_[1], "w": b_[2], "h": b_[3], "color": NUMC, "see": NUMC, "ctol": 30,
                          "pad": 0.6, "search": 0.8, "text": no, "size": 9})
        if k == 0:
            st += T(pg, f"q{no}-t", nx, nb, no, 9, NUMC, LOTTE, 400, tuple(b_), temp="00.", label="문항 번호 자리", track=TRACK_NO)
            st.append(F('#side input[data-a="h_scale"]', HS))
            ELEMS[pg].pop()                                                  # 잴 자리는 위(잉크 상자)로
            st += slot("문항번호")
        else:
            st += dup(nx, round(top_of(nb, 9, LOTTE, 400), 2))
    st += [S("빈칸 문장 — 임시 글 · 자리 · 스타일 · GREP(약속 괄호 → 밑줄 칸)", 1700)]
    for k, (nb, nx, no, en, ko, ans, sent) in enumerate(its):
        CONTENT["빈칸문장"].append(marked(sent, ans))
        b0 = en[0][0] - (DROP if en[0][2] else 0)
        y = round(top_of(b0, 8, NOTO, 400, LEAD_EN), 2)
        measure_en(pg, no, en, x_en, right)
        if k == 0:
            st += text(x_en, y, w_en, round(2 * LEAD_EN * MM + 0.6, 2), TEMP_EN, 8, INK, label="빈칸 문장 자리 — 임시 글",
                       leading=LEAD_EN, align="justify", font=NOTO, track=TRACK_EN)
            st.append(F('#side input[data-a="h_scale"]', HS))
            st += slot("빈칸문장", label="자리 이름 「빈칸문장」")
            if abs(WS_EN) > 5:
                st.append(F('#side input[data-a="word_spacing"]', WS_EN))
            st += grep(0, r"\{([^}]*)\}", bold=False, size=HID, blank=HID_PAD, line=LINE_W, line_off=LINE_OFF, line_color=INK, hide=True,
                       label=f"GREP — 약속 괄호 {{정답}}: 정답은 감추고 그 글 폭({HID}pt · 자간 {HID_TRACK}‰) + {HID_PAD}mm 만큼 밑줄(선 {LINE_W}mm · 기준선 아래 {LINE_OFF}mm)")
            st += [F('#side input[data-a="grep.0.track"]', HID_TRACK, 600), {"click": '#side input[data-a="grep.0.fit"]', "wait": 600}]
        else:
            st += dup(x_en, y)
    st += [S("해석 — 임시 글 · 자리 · 스타일, 나머지는 복제", 1500)]
    for k, (nb, nx, no, en, ko, ans, sent) in enumerate(its):
        CONTENT["해석"].append("".join(s for _, s in ko).strip())
        y = round(top_of(ko[0][0], 8, NOTO, 500, LEAD_KR), 2)
        lo, hi = ko[0][0] - 2.9, ko[-1][0] + 0.9
        k_ink = ink(pg, KORC, x_kr - 0.6, lo, right - x_kr + 1.2, hi - lo)
        ELEMS[pg].append({"id": f"k{no}", "x": k_ink[0], "y": k_ink[1], "w": k_ink[2], "h": k_ink[3], "color": KORC, "see": KORC, "ctol": 40,
                          "pad": 0.6, "search": 1.0, "text": CONTENT["해석"][-1][:30], "size": 8})
        if k == 0:
            st += text(x_kr, y, w_kr, round(2 * LEAD_KR * MM + 0.6, 2), TEMP_KR, 8, KORC, label="해석 자리 — 임시 글",
                       leading=LEAD_KR, align="justify", font=NOTO, track=TRACK_KR, weight=500)
            st += slot("해석", label="자리 이름 「해석」")
            if abs(WS_KR) > 5:
                st.append(F('#side input[data-a="word_spacing"]', WS_KR))
        else:
            st += dup(x_kr, y)
    return st


def passage_no(pg, pno):
    """지문 번호(영도 12pt) — 자리, 옆 세로줄(같은 서체·같은 색 │)은 고정 글. 원본 38쪽 「01 │」, 39쪽 「02│」(공백 없음)"""
    p = REFDOC[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    sp = next(s for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"] for l in b.get("lines", [])
              for s in l["spans"] if "Yeongdo" in s["font"])
    ch = sp["chars"]
    base = (sp["origin"][1] - oy) * MM
    k = next(i for i, c in enumerate(ch) if c["c"] == "│")
    no = "".join(c["c"] for c in ch[:k])                                   # 「01 」 / 「02」 — 끝 공백은 원본 그대로(영도체 끝 꼴)
    x = (ch[0]["origin"][0] - ox) * MM
    bar_x = (ch[k]["origin"][0] - ox) * MM
    nb = ink(pg, PNO, x - 0.2, base - 3.6, bar_x - x, 4.2)
    # 자간은 잉크 상자 안 글자(「01」)로 잰다 — 끝 공백까지 넣어 세면 사이 수가 늘어 -195 처럼 틀어진다(1판)
    st = T(pg, f"no{no.strip()}", round(x, 2), base, no.strip(), 12, PNO, YD, 400, tuple(nb), search=0.6, label="지문 번호 자리", temp="00" + no[2:])
    st += slot("지문번호")
    CONTENT["지문번호"].append(no)
    st += T(pg, f"bar{no.strip()}", round(bar_x, 2), base, "│", 12, PNO, YD, 400, (bar_x, base - 3.4, 4.23, 4.6), label="세로줄 — 고정 글")
    b = ink(pg, PNO, bar_x + 1.5, base - 4.0, 1.5, 5.5, tol=20)
    ELEMS[pg][-1].update({"x": b[0], "y": b[1], "w": b[2], "h": b[3], "pad": 0.3, "search": 0.5, "ctol": 20})
    ELEMS[pg][-1].pop("text")         # 폭 0.1mm 남짓(1화소) 세로줄 — 선처럼 자리·크기만(07 과 같다)
    return st


# 해석 글상자 오른쪽 = 영어와 같다 — 원본 39쪽 23번 해석 첫 줄 끝 185.00 = 영어 양끝 줄 끝 185.00
KR_IN = 0


# 원본 밑줄 굵기 — 모든 칸 같은 값
LINE_W = round(statistics.median(u[3] for pno in PAGES for u in underlines(pno)), 3)
I38, I39 = items(PAGES[0]), items(PAGES[1])


def blank_rule():
    """빈칸 밑줄 길이 = 정답 글 폭 × a + 글자 수 × b + c (원본 71칸 최소제곱) → 감춘 글 크기 8a pt · 자간 b/(크기) ‰ · 더할 폭 c mm.
    정답 글 폭은 서체 hmtx(8pt) — 원본 71칸 최대 오차 0.1mm(scratch fit2)."""
    import numpy as np
    _, _, adv = face(NOTO, 400)
    A, y = [], []
    for its in (I38, I39):
        for nb, nx, no, en, ko, ans, sent in its:
            uls = sorted((u for _, _, us in en for u in us), key=lambda u: (round(u[2], 1), u[0]))
            for a, u in zip(ans, uls):
                A.append([adv(a) * 8 * MM, len(a), 1]); y.append((u[1] - u[0]) / (HS / 100))   # 장평 99% 글상자 안 — 100% 폭으로 되돌려 맞춘다
    (ka, kb, kc), *_ = np.linalg.lstsq(np.array(A), np.array(y), rcond=None)
    size = round(ka * 8, 1)
    return size, round(kb / (size * MM) * 1000), round(float(kc), 2), len(y)


HID, HID_TRACK, HID_PAD, N_BLANK = blank_rule()
DROP = (_asc - _desc) / 2 * (HID - 8) * MM      # 8.5pt 글이 든 줄은 기준선이 내려간다(07 PINK_DROP 과 같은 이유) — 원본도 빈칸 줄은 번호보다 0.09mm 아래


def span_right(pno):
    """글상자 오른쪽 = 양끝맞춤 줄 끝 글자(공백 말고) 오른쪽 — 원본 줄마다 마지막 잉크 글자 x1 의 최빈값.
    조각 x1 은 줄 끝 공백까지 들어가 0.78mm 넓다(1판: 183.73 으로 잡아 양끝 줄 공백이 0.06mm 씩 넓어졌다)"""
    p = REFDOC[pno - 1]
    ox = p.trimbox.x0
    xs = []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for l in b.get("lines", []):
            ch = [c for s in l["spans"] if "Noto" in s["font"] for c in s["chars"] if c["c"].strip()]
            if ch:
                xs.append(round((ch[-1]["bbox"][2] - ox) * MM, 1))
    return statistics.mode([x for x in xs if x > 170])


# ── 38쪽 (왼쪽 면) ──────────────────────────────────────────
st = open_doc("스텝바이스텝 워크북 C1 빈칸어법 (A4)")
st += expect_pages(1)
# 오른쪽 속성 패널을 넓힌다(07 과 같은 까닭 — 좁으면 4칸 줄의 숫자 칸 가운데가 증감 단추)
st += [S("속성 패널 넓히기", 900), {"drag": {"from": '[data-rsz="r"]', "to": [1200, 500]}, "wait": 800}]
st += [S("① 38쪽 — C1 빈칸 어법", 1500)]
st += header_left(1, "C1", " 빈칸 어법", title_seg(PAGES[0]))
st += passage_no(1, PAGES[0])
st += body(1, I38, span_right(PAGES[0]))
st += [S("꼬리 — 쪽번호", 1200)]
st += T(1, "f-no", 15.23, 285.53, "38", 6, "#3b4247", EL, 700, (15.23, 283.62, 3.4, 2.62), search=0.6)
st += T(1, "f-t", 20.9, 285.53, "STEP BY STEP", 6, INK, EL, 700, (20.9, 283.62, 17.68, 2.62))
st += done("38쪽", "p1.png")

# ── 39쪽 (오른쪽 면) ────────────────────────────────────────
st += add_page("② 39쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(2, "tag-t", 187.05, 21.84, "STEP BY STEP", 6, "#ffffff", MS, 700, (187.05, 19.56, 15.43, 2.84), search=0.2)
ELEMS[2][-1]["pad"] = 0.2      # 흰 글 창을 꼬리표 안으로(09 와 같다)
cb2 = ink(2, BEIGE, 186.0, 1.5, 18.0, 18.5)
st += T(2, "t-code", 187.76, 15.99, "C1", 36, BEIGE, MS, 500, tuple(cb2), label="큰 코드 C1")
st += [S("오른쪽 탭 셋 — 지금 단계(STEP 02)가 베이지", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#e1eaf3")
st += B(2, "tab2", 201.5, 90, 11.5, 26, BEIGE)
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
for k, sp in enumerate(rot_spans(PAGES[1])):
    st += TR(2, f"tab{k + 1}-t", sp, 6.5, sp["color"], MS, 700)
st += passage_no(2, PAGES[1])
st += body(2, I39, span_right(PAGES[1]))
st += [S("꼬리 — 쪽번호", 1200)]
st += T(2, "f-t", 178.27, 285.53, "STEP 02", 6, INK, EL, 700, (178.27, 283.62, 10.48, 2.62))
st += T(2, "f-no", 191.62, 285.53, "39", 6, "#3b4247", EL, 700, (191.62, 283.62, 3.4, 2.62), search=0.6)
st += done("39쪽", "p2.png")
st += put_content(CONTENT)                                                  # 바깥 시스템이 보내는 꼴 — 임시 글이 원고 글로 바뀐다
st += [{"shot": "p2_content.png", "wait": 800}]

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("11 단계", len(st), f"· 낱말 사이 {WS_EN}/{WS_KR}‰", "· 잴 요소", sum(len(v) for v in ELEMS.values()),
      f"· 자간 {TRACK_EN}/{TRACK_KR}/{TRACK_NO}‰ · 빈칸 {N_BLANK}칸 = {HID}pt 자간 {HID_TRACK}‰ + {HID_PAD}mm · 밑줄 {LINE_W}mm 내림 {LINE_OFF}mm · 빈칸 줄 내림 {DROP:.3f}mm · 오른쪽 {span_right(PAGES[0])}/{span_right(PAGES[1])}")
for k, v in CONTENT.items():
    print(" ", k, len(v), "·", v[:2] if k != "빈칸문장" else v[1])
