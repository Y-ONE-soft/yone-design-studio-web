"""배재1 포켓북 — 「배재1 포켓북」 원본 PDF(118면, 배재1_포켓북(26-2-중간)_내지(수정5).pdf · 관리 pocketbook/x47abc561)를 보고
편집기로 손수 만든다. 등록 이름 「배재1 포켓북 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」(2026-10-12 면 나누기). 만드는 단위 = 면 하나(구성.json — 면 판정 6개).
모양이 같고 색만 다른 면은 색별로 따로(교과서 단원 하늘색 띠 · 모의고사 단원 베이지 띠). 값은 모두 원본 PDF(상태.json ref)에서 잰다.
원고 자리 · 원고 꼴은 원고자리_규약.md 「포켓북 원고 — yos-pocketbook-v1」(원고.json — 원본에서 뽑은 시험용 원고).

면(구성.json 번호) — 만드는 면:
  2 분석 면 — 교과서용(견본 2쪽) · 모의고사용(견본 42쪽)
  (3 FLOW NOTE · 4 암기 TEST + 정답 · 5 분석 면 삽화 · 1·6 앞·뒷면 — 차례로 더한다)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import _color                                               # noqa: E402
import mkpage
import pymupdf
import pagecmp                                                          # noqa: E402
# 공용 값(SPOT 120,250 · AWAY 205,294)은 A4 쪽 안이라 A5(148×210) 밖이다 — 끌기(가로 최대 60 · 세로 30mm)가 쪽 안에서 끝나는 자리,
# 글 확정용 빈 곳은 지문 칸(오른쪽 끝 130mm) 오른쪽 여백
mkpage.SPOT = {"mm": [80, 175]}
mkpage.AWAY = {"mm": [140, 120]}
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
W_MM, H_MM = 148.0, 210.0
NAME = "배재1 포켓북 (편집기 제작)"
SRC = json.load(open(os.path.join(HERE, "원고.json"), encoding="utf-8"))
NOTO, PRE, HUM, YD, HAK, EL = "Noto Sans CJK KR", "Pretendard", "휴먼범석체", "Yeongdo OTF", "Hakgyoansim UndongjangOTF", "Elice DX Neolli OTF"
BAND = {"교과서": "#93c4d4", "모의고사": "#eae6dc"}                         # 위·아래 띠 — 단원 구분마다 색이 다른 면(색별로 따로 만든다)

ELEMS, PAGES, CONTENT = {}, [], {}


def want(n):
    return not ONLY or str(n) in ONLY


def E(e):
    ELEMS[len(PAGES)].append(e)


def els(pno):
    return [e for e in pagecmp.elements(REF_PATH, pno) if e["x"] < W_MM and e["x"] + e["w"] > 0 and e["y"] < H_MM and e["y"] + e["h"] > 0]


def clip(e):
    x0, y0, x1, y1 = max(e["x"], 0), max(e["y"], 0), min(e["x"] + e["w"], W_MM), min(e["y"] + e["h"], H_MM)
    return dict(e, x=round(x0, 2), y=round(y0, 2), w=round(x1 - x0, 2), h=round(y1 - y0, 2))


def spans(pno):
    """원본 글 조각 — 첫 글자 기준점(x, base) · 끝 글자 오른쪽 · 크기 · 색 · 글"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                if ch:
                    out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                                "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "text": "".join(c["c"] for c in sp["chars"]).strip()})
    return out


def line_of(sps, base, tol=0.3):
    """기준선이 같은 조각들을 한 줄 글 조각으로(첫 글자 ~ 끝 글자)"""
    row = sorted([s for s in sps if abs(s["base"] - base) < tol], key=lambda s: s["x"])
    t = row[0]["text"]
    for a, b in zip(row, row[1:]):                                      # 조각 사이 틈이 0.4mm 넘을 때만 빈칸 — 원본은 글자마다 · 꾸밈마다 조각이 끊긴다
        t += (" " if b["x"] - a["x1"] > 0.4 else "") + b["text"]
    return dict(row[0], x1=row[-1]["x1"], text=t)


def pg_new(pno, label, name=None, rep=True):
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label) + [{"click": "#rail .pg.on", "wait": 1500}]   # 아래 쪽 목록에서 새 쪽을 눌러 화면을 그 쪽에(연속 보기는 새 쪽이 반쯤 잘려 보인다)
    st += [S(label, 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},
           {"pick": {"at": "#side #s-spec", "value": "a5"}, "wait": 1500}]           # 판형 A5 148×210
    if len(PAGES) == 1 and pno > 1:
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    if name:                                                             # 면 이름 (관리 지면 보기가 이 이름으로 묶는다)
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", name, 900)]
    if rep:                                                              # 원고마다 — 원고 덩어리 하나에 이 면 한 장(맨 앞 · 맨 뒤 고정 면은 한 번만)
        st += [{"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1200}]
    return st


_DONE = set()


def _brand_open():
    return [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1500}]


def need_pstyle(name, props, label=None):
    """단락 스타일 — 브랜드 패널 「＋ 단락 스타일」 → 이름 → 칸마다"""
    if ("p", name) in _DONE:
        return []
    _DONE.add(("p", name))
    sel = lambda k: f'#sbody [data-st="{name}:{k}"]'
    st = [S(label or f"단락 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#st-new", "wait": 1300}]
    for k, v in props.items():
        if k in ("font", "weight", "align"):
            st.append({"pick": {"at": sel(k), "value": str(v)}, "wait": 700})
        else:
            st.append(F(sel(k), v, 800))
    return st + [{"click": "#sheet-x", "wait": 1200}]


def need_cstyle(name, props, label=None):
    """문자 스타일 — 브랜드 패널 「＋ 문자 스타일」 → 이름 → 칸마다. 체크 칸(b·i·u)은 누른다"""
    if ("c", name) in _DONE:
        return []
    _DONE.add(("c", name))
    sel = lambda k: f'#sbody [data-cs="{name}:{k}"]'
    st = [S(label or f"문자 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#cs-new", "wait": 1300}]
    for k, v in props.items():
        if k in ("b", "i", "u"):
            st.append({"click": sel(k), "wait": 800})
        elif k in ("font", "weight", "u_style"):
            st.append({"pick": {"at": sel(k), "value": str(v)}, "wait": 700})
        else:
            st.append(F(sel(k), v, 800))
    return st + [{"click": "#sheet-x", "wait": 1200}]


def T(s, font, weight, label=None, slot_name=None, temp=None, align=None, w=None, leading=None, h=None, bind=None, measure=True):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서"""
    size = s["size"]
    track = 0
    if len(s["text"]) > 1:
        track = round(((s["x1"] - s["x"]) - chrome_extent(font, weight, size, s["text"]) - face(font, weight)[2](s["text"][-1]) * size * MM)
                      / (len(s["text"]) - 1) / (size * MM) * 1000)
    bw = w or round((s["x1"] - s["x"]) * 1.3 + size * 0.4, 1)
    bh = h or round((leading or size * 1.45) * MM * 1.03, 1)
    top = top_of(s["base"], size, font, weight, leading)
    x = s["x"]
    if align == "right":
        x = s["x1"] + track / 1000 * size * MM - bw
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - size * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
         "h": round(size * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.6, "search": 0.6, "text": s["text"], "size": size}
    if slot_name:
        m["원고"] = True
    if measure:
        E(m)
    st = text(round(x, 2), round(top, 2), bw, bh, temp if slot_name else s["text"], size, s["color"], label=label, font=font, weight=weight,
              track=track or None, align=align, leading=leading, bind=bind)
    if slot_name:
        st += slot(slot_name)
    return st


def Ebox(x, y, w, h, color, pad=0.6, ctol=30):
    c = clip({"x": x, "y": y, "w": w, "h": h})
    E({"id": f"e{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": color, "see": color, "pad": pad, "ctol": ctol})


def rbox(x, y, w, h, fill, label=None, r=0, measure=True):
    st = box(x, y, w, h, fill, label=label, radius=r)
    if measure:
        Ebox(x, y, w, h, fill)
    return st


def Eslot(sps, color, label=""):
    """원고 칸 전체를 원고 요소 하나로 — 원고는 「들어갔나」만 본다(절차 합격 기준)"""
    x0, x1 = min(s["x"] for s in sps), max(s["x1"] for s in sps)
    y0, y1 = min(s["base"] - s["size"] * MM * 0.95 for s in sps), max(s["base"] + s["size"] * MM * 0.3 for s in sps)
    E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
       "color": color, "see": color, "ctol": 40, "pad": 1.0, "search": 1.0, "text": label, "size": sps[0]["size"], "원고": True})


def find(el, k, x, y, tol=0.6, **kw):
    c = [e for e in el if e["k"] == k and abs(e["x"] - x) < tol and abs(e["y"] - y) < tol and all(e.get(a) == v for a, v in kw.items())]
    if not c:
        raise RuntimeError(f"원본 요소 없음 {k} {x},{y} {kw}")
    return c[0]


def track_of(row, font, weight):
    """자간 ‰ — 양끝맞춤이 안 된 줄(문단 끝 줄)의 첫 ~ 끝 글자 거리와 서체 글자 폭의 차이"""
    size = row["size"]
    return round(((row["x1"] - row["x"]) - chrome_extent(font, weight, size, row["text"]) - face(font, weight)[2](row["text"][-1]) * size * MM)
                 / (len(row["text"]) - 1) / (size * MM) * 1000)


def first(kind, gubun):
    """원고.json 에서 그 면이 받는 첫 덩어리 — 견본 원고(바깥 시스템이 보낼 꼴)"""
    for it in SRC["원고"]:
        if it.get("구분") == gubun and kind(it):
            return it
    raise RuntimeError(f"원고 없음 {gubun}")


# ── 문자 스타일 — 원본에서 잰 값(원고_뽑기 의 cs 이름과 같다) ──
CS = {
    "빨강 글자": {"color": "#d2232a"}, "파랑 글자": {"color": "#214e8e"},
    # 형광 = 글 뒤 가로 띠 — 원본 띠: 기준선 위 2.55mm ~ 아래 0.63mm(두께 3.18 · 가운데가 기준선 위 0.96mm)
    "형광 노랑": {"bg": "#fffdee", "bg_band": 3.18, "bg_off": 0.96}, "형광 분홍": {"bg": "#faf7f9", "bg_band": 3.18, "bg_off": 0.96},
    "형광 주황": {"bg": "#fff7f3", "bg_band": 3.18, "bg_off": 0.96}, "형광 민트": {"bg": "#f1f8f6", "bg_band": 3.18, "bg_off": 0.96},
    # 분홍 물결 — 원본 선: 기준선 아래 0.74 ~ 1.16mm, 굵기 0.55pt(0.19mm)
    "분홍 물결": {"u": True, "u_style": "wavy", "line": 0.19, "line_off": 0.95, "line_color": "#ee4d9b"},
    "구문 표기": {"font": HUM, "size": 7, "color": "#999999"},
    "서술형": {"font": HUM, "size": 6, "color": "#d2232a"},
}


def analysis(pno, gubun, cs_name, pic=False):
    """분석 면 — 출처 꼬리표 · 지문(꾸밈 조각 · 윗주) · TRANSLATION · 해석 · 꼬리. 원고 덩어리 = 출처 · 지문 · 해석.
    pic = 삽화 면 — 왼쪽 아래 그림 칸(원고 자리 「그림」) · PICTURE 꼬리표 · 해석은 그림 오른쪽"""
    face_name = f"분석 면 · {'삽화 · ' if pic else ''}{gubun}"
    st = pg_new(pno, f"{'⑤' if pic else '②'} {face_name} — 원본 {pno}쪽", name=face_name)
    for n, props in CS.items():
        st += need_cstyle(n, props)
    el, sp = els(pno), spans(pno)
    band = BAND[gubun]
    st += [S(f"위 · 아래 띠 — {gubun} 색", 1100)]
    top_band = find(el, "rect", -3, -3, fill=band)
    bot_band = find(el, "rect", -3, 204.5, fill=band)
    st += rbox(top_band["x"], top_band["y"], top_band["w"], top_band["h"], band) + rbox(bot_band["x"], bot_band["y"], bot_band["w"], bot_band["h"], band)
    # 출처 꼬리표 — 글상자 칠(남색) · 모서리 1.0mm · 안쪽 여백 · 자동 크기 「높이와 너비」(글 길이만큼 늘어난다). 맞대기는 왼쪽 고정 부분만
    tag = find(el, "path", 15.0, 15.0)
    s_src = line_of([s for s in sp if s["size"] == 9.5 and s["color"] == "#ffffff"], next(s["base"] for s in sp if s["size"] == 9.5 and s["color"] == "#ffffff"))
    Ebox(tag["x"], tag["y"], 4.0, tag["h"], tag["fill"])
    Eslot([s for s in sp if s["size"] == 9.5 and s["color"] == "#ffffff"], "#ffffff", label="출처")   # 출처 글 = 원고(「들어갔나」만)
    TL = round(tag["h"] / MM, 2)                                         # 행간 = 꼬리표 높이(한 줄)
    lpad, rpad = round(s_src["x"] - tag["x"], 2), round(tag["x"] + tag["w"] - s_src["x1"], 2)
    st += T(dict(s_src, base=s_src["base"]), YD, 400, label="출처 — 원고 자리 「출처」 (꼬리표 = 글상자 칠 · 글 길이만큼)", slot_name="출처", temp="출처 이름",
            w=round(W_MM - 15 - tag["x"], 1), leading=TL, measure=False)
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "both"}, "wait": 700},
           F('#side input[data-it="x"]', round(tag["x"], 2))]                # 칠은 상자 가장자리에 — 상자 = 꼬리표 왼쪽 끝, 글은 안쪽 여백만큼 안
    st += _color("frame.fill", tag["fill"]) + [F('#side input[data-a="frame.radius"]', 1.0), F('#side input[data-a="inset4"]', f"0 {rpad} 0 {lpad}")]
    # 지문 — 한 글상자. 단락 스타일 「분석 지문」(Noto Sans CJK KR 9pt · 양끝맞춤), 꾸밈은 조각의 문자 스타일, 문장 성분 · 서술형★ 은 윗주
    ln = next(e for e in el if e["k"] == "rect" and abs(e["w"] - 115) < 1 and e["h"] < 0.5 and e["y"] > 140)   # TRANSLATION 구분선(삽화 면은 더 위)
    lim = ln["y"] - 2
    rows = sorted({round(s["base"], 2) for s in sp if s["size"] == 9.0 and 20 < s["base"] < lim})
    lead = round(sorted(b - a for a, b in zip(rows, rows[1:]))[len(rows) // 2 - 1], 3)       # 줄 간격 가운데 값(mm)
    last = line_of(sp, rows[-1])
    LEAD = round(lead / MM, 2)
    st += need_pstyle("분석 지문", {"font": NOTO, "weight": 400, "size": 9.0, "leading": LEAD, "color": "#000000", "align": "justify",
                                 "tracking": track_of(dict(last, size=9.0), NOTO, 400)})
    body = [s for s in sp if 20 < s["base"] < lim]
    Eslot(body, "#000000", label="지문")
    ptop = round(top_of(rows[0], 9.0, NOTO, 400, LEAD), 2)
    st += text(15.0, ptop, 115.0, round(lim - ptop, 1), "Temporary passage text for styling the analysis page.", 9.0, "#000000",
               label="지문 — 한 글상자(원고만큼)", font=NOTO, leading=LEAD, align="justify")
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
    st += slot("지문", label="자리 — 지문(꾸밈 조각)")
    st += [{"pick": {"at": '#side select[data-a="style"]', "value": "분석 지문"}, "wait": 700}]
    # 윗주 기본값 — 원본 회색 표기의 기준선이 지문 기준선에서 얼마나 떨어졌나(가운데 값)
    marks = [s for s in sp if s["color"] == "#999999" and s["size"] == 7.0]
    below = sorted(m["base"] - max(r for r in rows if r < m["base"]) for m in marks if any(r < m["base"] for r in rows) and m["base"] - max(r for r in rows if r < m["base"]) < 5)
    above = sorted(min(r for r in rows if r > m["base"]) - m["base"] for m in marks if any(r > m["base"] for r in rows) and min(r for r in rows if r > m["base"]) - m["base"] < 5
                   and not (any(r < m["base"] for r in rows) and m["base"] - max(r for r in rows if r < m["base"]) < 5))
    ha, hd, _ = face(HUM, 400)
    sl = 7 * MM
    off_b = round(below[len(below) // 2] - ((sl - (ha + hd) * sl) / 2 + ha * sl), 2) if below else 0.6
    off_a = round(above[len(above) // 2] - ((sl - (ha + hd) * sl) / 2 + hd * sl), 2) if above else 0.4
    st += [S(f"윗주 기본값 — 「구문 표기」 · 위 {off_a} · 아래 {off_b}mm · 본문 가운데", 1200),
           {"pick": {"at": '#side select[data-a="ruby.cs"]', "value": "구문 표기"}, "wait": 700},
           F('#side input[data-a="ruby.off_above"]', off_a), F('#side input[data-a="ruby.off_below"]', off_b),
           {"pick": {"at": '#side select[data-a="ruby.align"]', "value": "center"}, "wait": 700}]
    # TRANSLATION — 구분선 · 꼬리표 칸 · 이름표(고정)
    st += [S("TRANSLATION — 구분선 · 꼬리표", 1000)]
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], ln["fill"])
    for tg in sorted([e for e in el if e["k"] == "rect" and abs(e["w"] - 16) < 0.5 and abs(e["h"] - 2.7) < 0.2], key=lambda e: e["x"]):
        st += rbox(tg["x"], tg["y"], tg["w"], tg["h"], tg["fill"])
    for word in (("PICTURE", "TRANSLATION") if pic else ("TRANSLATION",)):
        st += T(next(s for s in sp if s["text"] == word), HAK, 300)
        ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)                # 밝은 글 — 둘레를 넓게 보면 칸 색이 섞인다
    if pic:
        # 그림 칸 — 원고 자리 「그림」. 원본 그림 크기는 지문마다 다르다(44쪽 삽화 45.9 정사각 · 64쪽 그래프 59.6×35.5) — 둘 다 담는 칸
        # (12.9, 149.1 · 59.6×45.9)에 비율대로 맞추고 위 가운데에 붙인다(44쪽 삽화 x 19.8 = 칸 가운데, 64쪽 그래프 y = 칸 위)
        im = next(e for e in el if e["k"] == "image")
        FX, FY, FW, FH = 12.9, round(im["y"], 2), 59.6, 45.9
        E({"id": f"g{len(ELEMS[len(PAGES)])}", "x": round(im["x"], 2), "y": round(im["y"], 2), "w": round(im["w"], 2), "h": round(im["h"], 2),
           "color": "auto", "see": "auto", "pad": 1.0, "ctol": 40, "원고": True})
        st += [S("그림 칸 — 원고 자리 「그림」 · 틀 안에 다 보이게 · 기준점 위 가운데", 1300),
               {"draw": {"tool": "image", "from": mkpage.SPOT, "to": {"mm": [mkpage.SPOT["mm"][0] + 40, mkpage.SPOT["mm"][1] + 25]}}, "wait": 750}]
        st += [F('#side input[data-a="w"]', FW), F('#side input[data-a="h"]', FH), F('#side input[data-it="x"]', FX), F('#side input[data-it="y"]', FY),
               F('#side input[data-a="bind"]', "그림", 900), {"pick": {"at": '#side select[data-a="fit_at"]', "value": "t"}, "wait": 800}]
    # 해석 — 한 글상자, 「분석 해석」(Pretendard 500 5.9pt)
    trows = sorted({round(s["base"], 2) for s in sp if s["size"] == 5.9 and s["base"] > ln["y"]})
    tl = round(sorted(b - a for a, b in zip(trows, trows[1:]))[len(trows) // 2 - 1], 3) if len(trows) > 1 else 3.2
    TLD = round(tl / MM, 2)
    tlast = line_of(sp, trows[-2] if len(trows) > 1 else trows[-1])    # 끝 줄이 아주 짧으면 자간이 튄다 — 그 앞 줄은 양끝맞춤이라 끝 줄만
    tlast = line_of(sp, trows[-1])
    st += need_pstyle("분석 해석", {"font": PRE, "weight": 500, "size": 5.9, "leading": TLD, "color": "#4d4d4d", "align": "justify",
                                 "tracking": track_of(dict(tlast, size=5.9), PRE, 500) if len(tlast["text"]) > 6 else 0})
    tsp = [s for s in sp if s["size"] == 5.9 and s["base"] > ln["y"]]
    Eslot(tsp, "#4d4d4d", label="해석")
    ttop = round(top_of(trows[0], 5.9, PRE, 500, TLD), 2)
    tx = round(min(s["x"] for s in tsp), 2)                             # 삽화 면은 그림 오른쪽(74mm)부터
    # 아래 끝 199mm(아래 띠 위) — 편집기는 한글을 어절에서만 줄 바꿈해(원본은 글자 단위) 같은 원고가 한 줄 길어질 수 있다(단락 컴포저 전까지)
    st += text(tx, ttop, round(130.0 - tx, 1), round(199.0 - ttop, 1), "임시 해석 글이 이 칸에 들어온다.", 5.9, "#4d4d4d", label="해석 — 한 글상자", font=PRE, leading=TLD, align="justify")
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
    st += slot("해석", label="자리 — 해석")
    st += [{"pick": {"at": '#side select[data-a="style"]', "value": "분석 해석"}, "wait": 700}]
    # 꼬리 — 쪽 번호(남색 · 시스템 자리) · 책 이름(원고 자리 「책이름」)
    st += [S("꼬리 — 쪽 번호 · 책 이름", 1000)]
    s_no = next(s for s in sp if s["base"] > 190 and s["text"] == str(pno))
    st += T(s_no, EL, 700, label="쪽 번호 — 시스템 자리 (엘리스 DX 널리체 Bold)", bind="sys.page_no")
    if pno != 2 + len(PAGES) - 1:                                       # 견본 문서의 쪽 번호가 원본과 다른 면 — 쪽마다 바뀌는 값이라 원고처럼 「들어갔나」만
        ELEMS[len(PAGES)][-1]["원고"] = True
    s_bk = line_of([s for s in sp if s["base"] > 190 and s["color"] == "#000000"], next(s["base"] for s in sp if s["base"] > 190 and s["color"] == "#000000"))
    st += T(s_bk, EL, 500, label="책 이름 — 원고 자리 「책이름」", slot_name="책이름", temp="POCKET BOOK 책 이름", w=50)
    st += done(face_name, f"p{pno}.png")
    # 견본 원고 한 벌 — 원고 덩어리 그대로(면 이름 → [덩어리 …], 「원고마다」 면의 레코드). 덩어리 = 출처 · 지문(꾸밈 조각) · 해석 (· 그림)
    it = first(lambda x: "지문" in x and ("그림" in x) == pic and x["_원본쪽"][0] == pno, gubun)
    rec = {"출처": it["출처"], "지문": [it["지문"]], "해석": it["해석"], "책이름": SRC["book"]["책이름"]}   # 글 하나 자리에 조각 = [[조각 …]]
    if pic:                                                              # 그림 = 주소 — 시험용은 원고_뽑기 가 잘라 둔 그림 파일을 data: 로
        import base64
        rec["그림"] = "data:image/png;base64," + base64.b64encode(open(os.path.join(HERE, it["그림"]), "rb").read()).decode()
    CONTENT[face_name] = [rec]
    return st


def rframe(e, color, r, label=None):
    """테두리만 있는 둥근 칸(원본 도형 그대로) — 칠 없음 · 획 색 · 굵기(mm → pt)"""
    st = box(e["x"], e["y"], e["w"], e["h"], "#ffffff", label=label, radius=r)
    st += [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]
    st += _color("stroke.color", color) + [F('#side input[data-a="stroke.w"]', round(e["sw"] / MM, 3))]
    o = e["sw"] / 2
    Ebox(e["x"] - o, e["y"] - o, e["w"] + 2 * o, e["h"] + 2 * o, color)
    return st


def icon(pno, x, y, w, h, name):
    """원본의 작은 그림(연필 아이콘 — 도형 조각 10개)을 그 자리 그대로 그림 파일로 — 바탕(이름표 색)까지 같이 잘라 덮는다"""
    path = os.path.join(WORK, f"{name}.png")
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    r = pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM)
    p.get_pixmap(clip=r, dpi=600).save(path)
    E({"id": f"i{len(ELEMS[len(PAGES)])}", "x": x, "y": y, "w": w, "h": h, "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    return image(x, y, w, h, path, label=f"아이콘 — 원본 그림({name}.png)")


CS.update({
    "빈칸 번호": {"size": 5.5, "color": "#999999", "bshift": round(1.09 / MM, 2)},   # 원본: 번호 기준선이 글 기준선보다 1.09mm 위(기준선 칸은 pt)
    "빈칸": {"color": "#ffffff", "track": 65},                                # 답 글자를 감추고(흰 글) 글자당 0.6pt 넓게 — 원본 빈칸 폭 = 답 폭 + 글자당 0.55~1pt
    "정답": {"color": "#ea9149"},
})
TAB = {"교과서": "#4a9cb6"}


def memorize(pno, gubun):
    """암기 TEST + 정답 — 2쪽 면(펼침). 원고 덩어리 = 암기지문(「번호[답]」) · 단원 · 구분. 왼쪽은 답을 감추고 오른쪽은 답을 주황으로(GREP → 문자 스타일)"""
    st = []
    for side, rp in (("TEST", pno), ("정답", pno + 1)):
        nm = f"암기 TEST · {gubun}" if side == "TEST" else None             # 펼침면 오른쪽 쪽은 이름 없이 왼쪽 면을 따른다
        st += pg_new(rp, f"④ 암기 TEST + 정답 · {gubun} — 원본 {rp}쪽 ({side})", name=nm)
        for n in ("빈칸 번호", "빈칸", "정답"):
            st += need_cstyle(n, CS[n])
        el, sp = els(rp), spans(rp)
        band = BAND[gubun]
        st += [S(f"위 · 아래 띠 — {gubun} 색", 1100)]
        tb, bb = find(el, "rect", -3, -3, fill=band), find(el, "rect", -3, 204.5, fill=band)
        st += rbox(tb["x"], tb["y"], tb["w"], tb["h"], band) + rbox(bb["x"], bb["y"], bb["w"], bb["h"], band)
        lab = find(el, "rect", 18.0, 12.4)
        st += rbox(lab["x"], lab["y"], lab["w"], lab["h"], lab["fill"], label=f"이름표 칸 — {lab['fill']}")
        st += icon(rp, 19.9, 13.6, 3.6, 3.6, f"연필_{gubun}_{side}")
        s_lab = line_of([s for s in sp if s["size"] == 7.0 and s["base"] < 18], next(s["base"] for s in sp if s["size"] == 7.0 and s["base"] < 18))
        st += T(s_lab, HAK, 300, label=f"이름표 — 「{s_lab['text']}」")
        ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)
        fr = find(el, "path", 18.1, 20.5)
        st += rframe(fr, fr["stroke"], 0.9, label="테두리 칸 — 둥근 모서리 0.9mm")
        # 암기지문 — 한 글상자, 「암기 지문」(Noto 9pt · 양끝맞춤 · 행간 = 원본 줄 간격). 쪽마다 GREP → 문자 스타일
        rows = sorted({round(s["base"], 2) for s in sp if s["size"] == 9.0 and 22 < s["base"] < 195})
        lead = round(sorted(b - a for a, b in zip(rows, rows[1:]))[len(rows) // 2 - 1], 3)
        LEAD = round(lead / MM, 2)
        last = line_of([s for s in sp if s["size"] == 9.0], rows[-1])
        st += need_pstyle("암기 지문", {"font": NOTO, "weight": 400, "size": 9.0, "leading": LEAD, "color": "#000000", "align": "justify",
                                     "tracking": track_of(dict(last, size=9.0), NOTO, 400) if side == "정답" else 0})
        body = [s for s in sp if s["size"] in (9.0, 5.5) and 22 < s["base"] < 195]
        Eslot(body, "#000000", label="암기지문")
        x0 = min(s["x"] for s in body if s["size"] == 9.0)
        top = round(top_of(rows[0], 9.0, NOTO, 400, LEAD), 2)
        st += text(round(x0, 2), top, round(fr["x"] + fr["w"] - 4.0 - x0, 1), round(fr["y"] + fr["h"] - 2 - top, 1), "Temporary passage with 1[blank] answers.", 9.0, "#000000",
                   label=f"암기지문 — 한 글상자 ({side})", font=NOTO, leading=LEAD, align="justify")
        st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
        st += slot("암기지문", label="자리 — 암기지문(「번호[답]」)")
        st += [{"pick": {"at": '#side select[data-a="style"]', "value": "암기 지문"}, "wait": 700}]
        st += grep(0, r"\d+(?=\[)", bold=False, label="GREP — 빈칸 앞 번호는 「빈칸 번호」") + [{"pick": {"at": '#side select[data-a="grep.0.cs"]', "value": "빈칸 번호"}, "wait": 700}]
        st += grep(1, r"(?<=\[)[^\]]+(?=\])", bold=False, label=f"GREP — 대괄호 안 답은 「{'빈칸' if side == 'TEST' else '정답'}」") + \
            [{"pick": {"at": '#side select[data-a="grep.1.cs"]', "value": "빈칸" if side == "TEST" else "정답"}, "wait": 700}]
        # 꼬리 — 왼쪽: 쪽 번호 · POCKET BOOK(고정) / 오른쪽: 옆 탭(구분) · 단원 · 쪽 번호
        st += [S("꼬리", 1000)]
        s_no = next(s for s in sp if s["base"] > 190 and s["text"] == str(rp))
        if side == "TEST":
            st += T(s_no, EL, 700, label="쪽 번호 — 시스템 자리", bind="sys.page_no")
            if rp != 2 + len(PAGES) - 1:
                ELEMS[len(PAGES)][-1]["원고"] = True
            st += T(next(s for s in sp if s["base"] > 190 and "POCKET" in s["text"]), EL, 500)
        else:
            tab = next(e for e in el if e["k"] == "path" and abs(e["x"] - 139.0) < 0.5 and e["w"] > 10)
            st += rbox(tab["x"], tab["y"], 15.0, tab["h"], tab["fill"], r=1.6, label="옆 탭 — 왼쪽 모서리 1.6mm(오른쪽은 재단 밖)", measure=False)
            Ebox(tab["x"], tab["y"], W_MM - tab["x"], tab["h"], tab["fill"])
            ts = sorted([s for s in sp if s["size"] == 6.4 and s["color"] == "#ffffff"], key=lambda s: s["base"])
            Eslot(ts, "#ffffff", label="구분")
            st += text(round(ts[0]["x"] - 0.3, 2), round(top_of(ts[0]["base"], 6.4, EL, 700, round((ts[1]["base"] - ts[0]["base"]) / MM, 2)), 2), 3.0, 12.0, "구분",
                       6.4, "#ffffff", label="구분 — 원고 자리 「구분」 (한 글자씩 세로로 · 엘리스 DX 널리체 Bold)", font=EL, weight=700,
                       leading=round((ts[1]["base"] - ts[0]["base"]) / MM, 2))
            st += slot("구분")
            s_u = line_of([s for s in sp if s["base"] > 190 and s["color"] == "#000000"], next(s["base"] for s in sp if s["base"] > 190 and s["color"] == "#000000"))
            st += T(s_u, EL, 500, label="단원 — 원고 자리 「단원」 (오른쪽 맞춤)", slot_name="단원", temp="단원 이름", align="right", w=40)
            st += T(s_no, EL, 700, label="쪽 번호 — 시스템 자리(오른쪽 맞춤)", bind="sys.page_no", align="right")
            if rp != 2 + len(PAGES) - 1:
                ELEMS[len(PAGES)][-1]["원고"] = True
        st += done(f"암기 TEST {side} {gubun}", f"p{rp}.png")
    it = first(lambda x: "암기지문" in x, gubun)
    CONTENT[f"암기 TEST · {gubun}"] = [{"암기지문": [it["암기지문"], it["암기지문"]], "단원": it["단원"], "구분": it["구분"]}]   # 같은 원고가 두 쪽에
    return st


BODONI = "Bodoni Moda"


def el_line(sp, e):
    """맞대기 도구가 읽은 글 한 줄(띄어쓰기가 바른 문장) + 그 자리의 글자 조각들로 잰 기준선 · 첫 글자 · 끝 글자 — 글자마다 따로 찍힌 넓은 자간 글"""
    row = [s for s in sp if e["x"] - 0.5 <= s["x"] <= e["x"] + e["w"] + 0.5 and e["y"] - 1 <= s["base"] - s["size"] * MM * 0.8 <= e["y"] + e["h"] + 1
           and abs(s["size"] - e["size"]) < 0.3]
    base = sorted(row, key=lambda s: s["x"])[0]["base"]
    return dict(line_of(row, base), text=e["text"])


def cover(pno, name):
    """맨 앞 · 맨 뒤 면 — 종이 바탕 그림 · POCKET · 선 · Pocket Book.(Bodoni Moda 34pt) · 학교 칸(테두리 · 자리 「학교」「시험」) · 꼬리.
    뒷면은 만든 사람 목록(고정 글 — 책마다 바뀌면 편집기에서 고친다)"""
    st = pg_new(pno, f"{'①' if pno == 1 else '⑥'} {name} — 원본 {pno}쪽", name=name, rep=False)
    el, sp = els(pno), spans(pno)
    texts = [e for e in el if e["k"] == "text"]
    tx = lambda f: next(e for e in texts if f(e))
    # 바탕 — 원본에 박힌 그림(그러데이션 종이) 그대로
    xref = REF[pno - 1].get_images()[0][0]
    pix = pymupdf.Pixmap(REF, xref)
    if pix.n - pix.alpha >= 4:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    bg = os.path.join(WORK, f"바탕_{pno}.png")
    pix.save(bg)
    im = next(e for e in el if e["k"] == "image")
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", "x": 0, "y": 0, "w": W_MM, "h": H_MM, "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    st += image(round(im["x"], 2), round(im["y"], 2), round(im["w"], 2), round(im["h"], 2), bg, label="바탕 — 원본 그림(종이 그러데이션)")
    ln = find(el, "rect", 15.0, 27.5)
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], ln["fill"], label="POCKET 아래 선")
    st += T(el_line(sp, tx(lambda e: e["text"] == "POCKET")), NOTO, 700, label="POCKET")
    # Pocket Book. — PDF 에는 3.4pt 로 적히고 행렬로 키워 찍혔다. 잉크 높이로 잰 실제 크기 34pt(Bodoni Moda)
    for word in ("Pocket", "Book."):
        s0 = next(s for s in sp if s["text"].startswith(word.rstrip(".")))
        x1 = max(s["x1"] for s in sp if abs(s["base"] - s0["base"]) < 0.3 and s["size"] == s0["size"])
        st += T(dict(s0, size=34.0, text=word, x1=x1), BODONI, 400, label=f"{word} — Bodoni Moda 34pt")
    box = next(e for e in el if e["k"] == "path" and abs(e["y"] - 177.6) < 0.5)
    st += rframe(box, box["stroke"], 1.1, label="학교 칸 — 테두리 · 모서리 1.1mm")
    st += T(el_line(sp, tx(lambda e: e["size"] == 10.0)), NOTO, 700, label="학교 — 원고 자리 「학교」", slot_name="학교", temp="학교")
    st += T(el_line(sp, tx(lambda e: e["size"] == 7.5 and 175 < e["y"] < 186)), NOTO, 400, label="시험 — 원고 자리 「시험」 (오른쪽 맞춤)",
            slot_name="시험", temp="시험 이름", align="right", w=40)
    st += T(el_line(sp, tx(lambda e: e["y"] > 193)), NOTO, 700, label="꼬리 — 고정 글")
    if pno == 1:
        st += T(el_line(sp, tx(lambda e: e["size"] == 8.0)), NOTO, 500, label="포켓북 · 핵심 암기 노트")
    else:                                                                # 만든 사람 — 제목(Bodoni Moda 9pt) · 이름 줄(Noto 7.5pt) — 고정 글
        for e in [e for e in texts if e["size"] < 1.5]:
            s0 = el_line(sp, e)
            st += T(dict(s0, size=9.0), BODONI, 700, label=f"만든 사람 제목 — {e['text']}")
        heads = sorted([e for e in texts if e["size"] < 1.5], key=lambda e: (e["x"], e["y"]))
        for hd in heads:
            names = sorted([e for e in texts if e["size"] == 7.5 and abs(e["x"] - hd["x"]) < 1 and e["y"] > hd["y"]
                            and not any(h2 is not hd and abs(h2["x"] - hd["x"]) < 1 and hd["y"] < h2["y"] < e["y"] for h2 in heads)], key=lambda e: e["y"])
            names = [n for n in names if n["y"] < 170]
            if not names:
                continue
            rows = [el_line(sp, n) for n in names]
            lead = round((rows[1]["base"] - rows[0]["base"]) / MM, 2) if len(rows) > 1 else 11.0
            for r in rows:
                E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(r["x"], 2), "y": round(r["base"] - 7.5 * MM * 0.8, 2), "w": round(r["x1"] - r["x"], 2),
                   "h": round(7.5 * MM * 1.05, 2), "color": r["color"], "see": r["color"], "ctol": 24, "pad": 0.6, "search": 0.6, "text": r["text"], "size": 7.5})
            top = round(top_of(rows[0]["base"], 7.5, NOTO, 400, lead), 2)
            st += text(round(rows[0]["x"], 2), top, 38.0, round(lead * MM * len(rows) + 2, 1), "\n".join(r["text"] for r in rows), 7.5, rows[0]["color"],
                       label=f"「{hd['text']}」 이름 {len(rows)}줄", font=NOTO, leading=lead)
    st += done(name, f"p{pno}.png")
    return st


st = open_doc(NAME)
st += expect_pages(1)

if want(1):
    st += cover(1, "앞면")
    CONTENT.setdefault("학교", []).append("배재1")
    CONTENT.setdefault("시험", []).append("2학기 중간고사")

if want(6):
    st += cover(118, "뒷면")
    CONTENT.setdefault("학교", []).append("배재1")
    CONTENT.setdefault("시험", []).append("2학기 중간고사")

if want(2):
    st += analysis(2, "교과서", "분석 면")
    st += analysis(42, "모의고사", "분석 면")

if want(5):
    st += analysis(44, "모의고사", "분석 면", pic=True)

if want(4):
    st += memorize(12, "교과서")
    st += memorize(46, "모의고사")

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
