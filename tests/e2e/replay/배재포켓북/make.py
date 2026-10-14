"""배재1 포켓북 — 「배재1 포켓북」 원본 PDF(118면, 배재1_포켓북(26-2-중간)_내지(수정5).pdf · 관리 pocketbook/x47abc561 — 2026-10-12 지움, 원본은 같은 폴더 원본.pdf)를 보고
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
    """단락 스타일 — 스타일 · 색상 견본 창 「＋ 새 단락 스타일」 → 이름 → 칸마다(단락 스타일 옵션)"""
    if ("p", name) in _DONE:
        return []
    _DONE.add(("p", name))
    st = [S(label or f"단락 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#st-new", "wait": 1300}]
    st += pstyle_fields(name, props)
    return st + [{"click": "#sheet-x", "wait": 1200}]


def need_cstyle(name, props, label=None):
    """문자 스타일 — 스타일 · 색상 견본 창 「＋ 새 문자 스타일」 → 이름 → 칸마다(문자 스타일 옵션)"""
    if ("c", name) in _DONE:
        return []
    _DONE.add(("c", name))
    st = [S(label or f"문자 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#cs-new", "wait": 1300}]
    st += cstyle_fields(name, props)
    return st + [{"click": "#sheet-x", "wait": 1200}]


def T(s, font, weight, label=None, slot_name=None, temp=None, align=None, w=None, leading=None, h=None, bind=None, measure=True, opsz=None):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서.
    opsz = 그 글상자에 줄 광학 크기 — 자간도 그 광학 크기의 글자 폭으로 잰다(안 주면 브라우저 자동 광학 크기 폭이라 넓게 나왔다)"""
    size = s["size"]
    track = 0
    if len(s["text"]) > 1:
        track = round(((s["x1"] - s["x"]) - chrome_extent(font, weight, size, s["text"], opsz=opsz) - face(font, weight)[2](s["text"][-1]) * size * MM)
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
    # 형광 = 굵은 밑줄 — 원본 띠: 기준선 위 2.55mm ~ 아래 0.63mm(두께 3.18 · 가운데가 기준선 위 0.96mm) → 밑줄 옵션 두께 · 오프셋 · 색상(mkpage.cstyle_id)
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
    from core.units import render as _render
    tpad = round(s_src["base"] - tag["y"] - _render.font_metrics(YD, 400)["d"] * s_src["size"] * MM, 2)   # 첫 번째 기준선(어센트)이 원본 기준선에 오게 인세트 위쪽
    st += [pick_p("auto_size", "width"), F('#side input[data-a="h"]', round(tag["h"], 2)),
           F('#side input[data-it="x"]', round(tag["x"], 2)), F('#side input[data-it="y"]', round(tag["y"], 2))]   # 프레임 = 꼬리표(칠은 프레임 가장자리) · 글 길이만큼 너비만 자란다
    st += _color("frame.fill", tag["fill"]) + [F('#side input[data-a="frame.radius"]', 1.0), F('#side input[data-a="inset4"]', f"{tpad} {rpad} 0 {lpad}")]
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
    st += [pick_p("auto_size", "")]
    st += slot("지문", label="자리 — 지문(꾸밈 조각)")
    st += [{"pick": {"at": '#side select[data-a="style"]', "value": "분석 지문"}, "wait": 700}]
    # 윗주 기본값 — 원본 회색 표기의 기준선이 지문 기준선에서 얼마나 떨어졌나(가운데 값)
    marks = [s for s in sp if s["color"] == "#999999" and s["size"] == 7.0]
    below = sorted(m["base"] - max(r for r in rows if r < m["base"]) for m in marks if any(r < m["base"] for r in rows) and m["base"] - max(r for r in rows if r < m["base"]) < 5)
    above = sorted(min(r for r in rows if r > m["base"]) - m["base"] for m in marks if any(r > m["base"] for r in rows) and min(r for r in rows if r > m["base"]) - m["base"] < 5
                   and not (any(r < m["base"] for r in rows) and m["base"] - max(r for r in rows if r < m["base"]) < 5))
    ha, hd, _ = face(HUM, 400)
    sl = 7 * MM
    bs = 9.0 * MM                                                        # 윗주 오프셋 Y = 본문 글자 상자(기준선 위 0.88em · 아래 0.12em) 끝에서 윗주 글 상자까지
    oy_b = round((below[len(below) // 2] - ((sl - (ha + hd) * sl) / 2 + ha * sl) if below else 0.6) - 0.12 * bs, 2)
    oy_a = round((above[len(above) // 2] - ((sl - (ha + hd) * sl) / 2 + hd * sl) if above else 0.4) - 0.88 * bs, 2)
    rb = CS["구문 표기"]
    st += [S(f"윗주 기본값 — 글꼴 {rb['font']} {rb['size']}pt · 위 {oy_a} · 아래 {oy_b}mm · 가운데", 1200),
           pick_p("ruby.font", rb["font"]), P_("ruby.size", rb["size"])] + color_p("ruby.color", rb["color"]) + [
           P_("ruby.oy_above", oy_a), P_("ruby.oy_below", oy_b), pick_p("ruby.align", "center")]
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
    st += [pick_p("auto_size", "")]
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
                                     "tracking": track_of(dict(last, size=9.0), NOTO, 400) if side == "정답" else 0,
                                     # 균등 배치 — 이 출판사 책 공통 범위(단어 100 · 133%, 문자 −8 · 250‰). 원본 첫 줄은 문자 간격을 −7‰ 줄여 「has an」까지 넣었다(줄 자간 실측)
                                     "jc": {"word_min": 100, "word_max": 133, "letter_min": -8, "letter_max": 250}})
        body = [s for s in sp if s["size"] in (9.0, 5.5) and 22 < s["base"] < 195]
        Eslot(body, "#000000", label="암기지문")
        x0 = min(s["x"] for s in body if s["size"] == 9.0)
        top = round(top_of(rows[0], 9.0, NOTO, 400, LEAD), 2)
        st += text(round(x0, 2), top, round(fr["x"] + fr["w"] - 4.0 - x0, 1), round(fr["y"] + fr["h"] - 2 - top, 1), "Temporary passage with 1[blank] answers.", 9.0, "#000000",
                   label=f"암기지문 — 한 글상자 ({side})", font=NOTO, leading=LEAD, align="justify")
        st += [pick_p("auto_size", "")]
        st += slot("암기지문", label="자리 — 암기지문(「번호[답]」)")
        st += [{"pick": {"at": '#side select[data-a="style"]', "value": "암기 지문"}, "wait": 700}]
        st += grep(0, r"\d+(?=\[)", "빈칸 번호", label="GREP 스타일 — 빈칸 앞 번호에 「빈칸 번호」")
        st += grep(1, r"(?<=\[)[^\]]+(?=\])", "빈칸" if side == "TEST" else "정답", label=f"GREP 스타일 — 대괄호 안 답에 「{'빈칸' if side == 'TEST' else '정답'}」")
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
FONTS = os.path.expanduser("~/Library/Fonts")
DOC_FONTS = set()


def need_font(fname):
    """시스템 서체 목록에 없는 굵기 — 글상자 「＋ 서체」로 올려 등록(공식 배포처에서 받은 파일). 등록 뒤 그 글상자는 지운다"""
    if fname in DOC_FONTS:
        return []
    DOC_FONTS.add(fname)
    st = text(20.0, 3.0, 24.0, 9.0, "서체", 9, "#231f20", label=f"서체 등록 — 「＋ 서체」({fname})")
    st += register_font(os.path.join(FONTS, fname))
    return st + [{"click": "#side #s-x", "wait": 900}]


def el_line(sp, e):
    """맞대기 도구가 읽은 글 한 줄(띄어쓰기가 바른 문장) + 그 자리의 글자 조각들로 잰 기준선 · 첫 글자 · 끝 글자 — 글자마다 따로 찍힌 넓은 자간 글"""
    row = [s for s in sp if e["x"] - 0.5 <= s["x"] <= e["x"] + e["w"] + 0.5 and e["y"] - 1 <= s["base"] - s["size"] * MM * 0.8 <= e["y"] + e["h"] + 1
           and abs(s["size"] - e["size"]) < 0.3]
    base = sorted(row, key=lambda s: s["x"])[0]["base"]
    return dict(line_of(row, base), text=e["text"])


# Bodoni 글(Pocket Book. · 만든 사람 제목) 색 허용 — 첫 글자 머리카락 세리프가 원본 300dpi 판에서 가장 진해도 142(글 색 78 과 64 차)라
# 「같은 색」에서 빠져 원본 상자가 1mm 좁게 잡혔다. 600dpi 직접 맞대기: 잉크 왼쪽 끝 차 0.04mm, P · B 글자 겹침 0.95 · 0.97, 잉크 1.03.
# 통과 기준(0.3mm · 모양)은 그대로 — 원본을 재는 색 범위만(바탕 237 과는 159 차라 섞이지 않는다)
BODONI_CTOL = 70
# 9pt 만든 사람 제목은 세리프가 더 가늘어 300dpi 에서 글 색과 87 · 바탕과 81 차(가운데)다 — 90. 1200dpi 맞대기: Assistant 겹침 0.92 · 잉크 1.00 · 폭 차 0.02mm
BODONI_CTOL_SMALL = 90


def cover(pno, name):
    """맨 앞 · 맨 뒤 면 — 종이 바탕 그림 · POCKET · 선 · Pocket Book.(Bodoni Moda 34pt) · 학교 칸(테두리 · 자리 「학교」「시험」) · 꼬리.
    뒷면은 만든 사람 목록(고정 글 — 책마다 바뀌면 편집기에서 고친다)"""
    st = pg_new(pno, f"{'①' if pno == 1 else '⑥'} {name} — 원본 {pno}쪽", name=name, rep=False)
    el, sp = els(pno), spans(pno)
    texts = [e for e in el if e["k"] == "text"]
    tx = lambda f: next(e for e in texts if f(e))
    # 바탕 — 원본에 박힌 그림(그러데이션 종이) 그대로
    bg = ref_image(REF, REF[pno - 1].get_images()[0][0], os.path.join(WORK, f"바탕_{pno}.png"))
    im = next(e for e in el if e["k"] == "image")
    # 바탕 그림은 요소 목록(색 상자 맞대기)에 넣지 않는다 — 그러데이션 종이라 「한 색 상자」로 잴 수 없다. 빠지거나 어긋나면 「목록 밖 차이」(쪽 전체 화소)가 잡는다
    st += image(round(im["x"], 2), round(im["y"], 2), round(im["w"], 2), round(im["h"], 2), bg, label="바탕 — 원본 그림(종이 그러데이션)")
    st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]   # 원본은 가로 그림(273×191)을 세로 쪽에 비율 무시하고 늘였다
    st += [{"pick": {"at": '#side select[data-a="flip"]', "value": "v"}, "wait": 900}]    # 그리고 상하로 뒤집었다(원본 그림 변환 행렬 세로 -611.2) — 그러데이션 밝은 쪽이 위
    ln = find(el, "rect", 15.0, 27.5)
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], ln["fill"], label="POCKET 아래 선")
    st += T(el_line(sp, tx(lambda e: e["text"] == "POCKET")), NOTO, 700, label="POCKET")
    # Pocket Book. — PDF 에는 3.4pt 로 적히고 행렬로 키워 찍혔다. 잉크 높이로 잰 실제 크기 34pt(Bodoni Moda)
    for word in ("Pocket", "Book."):
        s0 = next(s for s in sp if s["text"].startswith(word.rstrip(".")))
        x1 = max(s["x1"] for s in sp if abs(s["base"] - s0["base"]) < 0.3 and s["size"] == s0["size"])
        st += T(dict(s0, size=34.0, text=word, x1=x1), BODONI, 400, label=f"{word} — Bodoni Moda 34pt · 광학 크기 24", opsz=24)
        st += [{"js": "(() => { document.querySelectorAll('#side details.more').forEach(d => d.open = true); return '칸 펼침'; })()"},
               P_("opsz", 24, 800)]                                     # 원본 글자 모양 = 광학 크기 24(겹침 0.90 — 브라우저 자동은 34)
        ELEMS[len(PAGES)][-1].update(ctol=BODONI_CTOL)
    box = next(e for e in el if e["k"] == "path" and abs(e["y"] - 177.6) < 0.5)
    st += rframe(box, box["stroke"], 1.1, label="학교 칸 — 테두리 · 모서리 1.1mm")
    st += T(el_line(sp, tx(lambda e: e["size"] == 10.0)), NOTO, 700, label="학교 — 원고 자리 「학교」", slot_name="학교", temp="학교")
    st += T(el_line(sp, tx(lambda e: e["size"] == 7.5 and 175 < e["y"] < 186)), NOTO, 400, label="시험 — 원고 자리 「시험」 (오른쪽 맞춤)",
            slot_name="시험", temp="시험 이름", align="right", w=40)
    st += T(el_line(sp, tx(lambda e: e["y"] > 193)), NOTO, 700, label="꼬리 — 고정 글")
    if pno == 1:
        st += T(el_line(sp, tx(lambda e: e["size"] == 8.0)), NOTO, 700, label="포켓북 · 핵심 암기 노트 (Noto Bold — 서체 맞대기 0.72 · 500 은 21% 옅었다)")
    else:                                                                # 만든 사람 — 제목(Bodoni Moda Bold 9pt) · 이름 줄(Noto 350 7.5pt) — 고정 글
        st += need_font("BodoniModa-Bold.ttf")
        for e in [e for e in texts if e["size"] < 1.5]:
            s0 = el_line(sp, e)
            st += T(dict(s0, size=9.0), BODONI, 700, label=f"만든 사람 제목 — {e['text']}")
            ELEMS[len(PAGES)][-1].update(ctol=BODONI_CTOL_SMALL)
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
                       label=f"「{hd['text']}」 이름 {len(rows)}줄", font=NOTO, weight=400, leading=lead)   # 서체 맞대기 다섯 이름 모두 400 상위(350 은 13~15% 옅었다)
    st += done(name, f"p{pno}.png")
    return st


st = open_doc(NAME)
st += expect_pages(1)

# ── FLOWNOTE — 흐름 칸(3칸 한 줄 · 2×2 네 칸) · 주제 · 요약문 · 동반의어(표) ──
JAL, KCC = "Jalnan OTF", "KCCDodamdodam"


def ref_draws(pno):
    """원본 도형 — mm 상자 · 칠 · 선 · 경로 d(상자 안 0~1, 편집기 「경로 d」 칸 꼴)"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    hexc = lambda c: "#%02x%02x%02x" % tuple(round(v * 255) for v in c) if c else None
    out = []
    for dr in p.get_drawings():
        r = dr["rect"]
        x, y, w, h = (r.x0 - t.x0) * MM, (r.y0 - t.y0) * MM, r.width * MM, r.height * MM
        if w <= 0 or h <= 0:
            continue
        nx = lambda pt: f"{(pt.x - r.x0) / r.width:.4f} {(pt.y - r.y0) / r.height:.4f}"
        d, cur = [], None
        for it in dr["items"]:
            if it[0] == "l":
                if cur is None or abs(cur.x - it[1].x) > 1e-3 or abs(cur.y - it[1].y) > 1e-3:
                    d.append("M" + nx(it[1]))
                d.append("L" + nx(it[2]))
                cur = it[2]
            elif it[0] == "c":
                if cur is None or abs(cur.x - it[1].x) > 1e-3 or abs(cur.y - it[1].y) > 1e-3:
                    d.append("M" + nx(it[1]))
                d.append("C" + nx(it[2]) + " " + nx(it[3]) + " " + nx(it[4]))
                cur = it[4]
        if dr.get("closePath") or (d and d[0][1:] == d[-1].split(" ", 0)[0][1:]):
            d.append("Z")
        out.append({"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "fill": hexc(dr.get("fill")),
                    "stroke": hexc(dr.get("color")), "sw": (dr.get("width") or 0) * MM, "d": " ".join(d), "n": len(dr["items"])})
    return out


def ref_shape(e, fill=None, stroke=None, sw=None, label=None, measure=True):
    """원본 도형 그대로 — 「도형」 도구 + 경로 d(원본 꼭짓점 · 곡선) · 칠 · 선"""
    st = shape(e["x"], e["y"], e["w"], e["h"], fill or "#ffffff", label=label, d=e["d"])
    if not fill:
        st += [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]
    if stroke:
        st += _color("stroke.color", stroke) + [F('#side input[data-a="stroke.w"]', round(sw / MM, 3))]
    if measure:
        o = (sw or 0) / 2
        Ebox(e["x"] - o, e["y"] - o, e["w"] + 2 * o, e["h"] + 2 * o, fill or stroke)
    return st


def ref_pic(pno, info, name, box=None):
    """원본에 박힌 그림 한 장(모눈 바탕 등) — 출력 색 프로필로 꺼내 그 자리에(그림 칸 · 틀에 맞게 늘이기).
    box = 그 그림에서 이 자리만 잘라 쓴다(원본은 큰 그림 한 장을 칸 모양으로 잘라 보였다 — 3칸 흐름 바탕)"""
    from PIL import Image as _Im
    path = ref_image(REF, info["xref"], os.path.join(WORK, f"{name}.png"))
    t = REF[pno - 1].trimbox
    b = info["bbox"]
    x, y, w, h = (b[0] - t.x0) * MM, (b[1] - t.y0) * MM, (b[2] - b[0]) * MM, (b[3] - b[1]) * MM
    if box:
        im = _Im.open(path)
        kx, ky = im.width / w, im.height / h
        im.crop((round((box["x"] - x) * kx), round((box["y"] - y) * ky), round((box["x"] + box["w"] - x) * kx), round((box["y"] + box["h"] - y) * ky))).save(path)
        x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    return image(round(x, 2), round(y, 2), round(w, 2), round(h, 2), path, label=f"그림 — 원본 {name}") + [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]


def flownote(pno, gubun):
    """FLOWNOTE 면 — 흐름 칸(칸 수는 원고 흐름 단계 수: 3칸 한 줄 · 4칸 2×2) · 주제 · 요약문 · 동반의어 카드(표 — 원고 수만큼 칸).
    원고 덩어리 = 흐름(단계마다 제목 · 글) · 주제 · 요약문 · 동반의어(낱말 · 뜻 · 동의어 · 반의어) · 단원 · 구분"""
    el, sp, dr = els(pno), spans(pno), ref_draws(pno)
    cards = sorted([d for d in dr if d["fill"] == "#ffffff" and d["stroke"] and d["w"] > 30 and d["h"] > 25 and d["y"] < 90],   # 흐름 칸 = 흰 칠 + 테두리 한 도형
                   key=lambda d: (d["x"], d["y"]))
    n = len(cards)
    face_name = f"FLOWNOTE · {gubun} · {n}칸"
    st = pg_new(pno, f"③ {face_name} — 원본 {pno}쪽", name=face_name)
    st += need_cstyle("주황 화살표", {"color": "#f39857"}) + need_cstyle("파랑 꼬리표", {"color": "#0067b4"})   # GREP 스타일이 쓴다
    if n == 4:                                                           # 2×2 — 흐름 칸 차례는 왼쪽 단 위 → 아래, 오른쪽 단(① ② / ③ ④)
        st += columns(2, 4.0, label="여백 및 단 — 2단(흐름 칸 넷을 왼쪽 단 위→아래, 다음 단 차례로 받는다)")
    band = BAND[gubun]
    st += [S(f"위 · 아래 띠 — {gubun} 색", 1100)]
    tb, bb = find(el, "rect", -3, -3, fill=band), find(el, "rect", -3, 204.5, fill=band)
    st += rbox(tb["x"], tb["y"], tb["w"], tb["h"], band) + rbox(bb["x"], bb["y"], bb["w"], bb["h"], band)
    # FLOW NOTE 이름표 — 탭 모양(원본 경로) · 전구 아이콘 · 글(학교안심 운동장 L 8pt)
    tab = next(d for d in dr if abs(d["x"] - 104.0) < 0.5 and abs(d["y"] - 12.87) < 0.5)
    st += ref_shape(tab, fill=tab["fill"], label="FLOW NOTE 탭 — 원본 경로")
    area = find(el, "rect", 18.0, 18.3)
    st += rbox(area["x"], area["y"], area["w"], area["h"], area["fill"], label="흐름 바탕")
    ELEMS[len(PAGES)][-1].update(ctol=20)                                # 더 엄격하게 — 아래 요약 바탕 색(차 18 · 14 · 28)이 허용 30 안이라 결과에서만 상자가 0.6mm 길게 잡혔다
    for d in [d for d in dr if 108.0 < d["x"] < 111.5 and 13.8 < d["y"] < 17.5 and d["w"] < 3]:   # 전구 — 원본 도형 조각 그대로(잘라 붙이면 탭 색과 둘레가 달라 네모가 보였다)
        st += ref_shape(d, fill=d["fill"], measure=d["w"] > 1)
    st += T(next(s for s in sp if s["text"] == "FLOW NOTE"), HAK, 300, label="FLOW NOTE — 학교안심 운동장 L")
    ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)
    # 흐름 칸 — 흰 둥근 칸(테두리) · 모눈 그림 · 번호 동그라미 · 칸 글상자(자리 「흐름제목+흐름글」 — 칸마다 단계 하나)
    imgs = sorted([i for i in REF[pno - 1].get_image_info(xrefs=True)], key=lambda i: (i["bbox"][0], i["bbox"][1]))
    ttl = sorted([s for s in sp if s["size"] == 7.0 and s["color"] == "#0067b4"], key=lambda s: s["base"])
    body = [s for s in sp if s["size"] == 9.5]
    rows = sorted({round(s["base"], 2) for s in body if s["base"] < cards[0]["y"] + cards[0]["h"]})
    lead = round(sorted(b - a for a, b in zip(rows, rows[1:]))[len(rows) // 2 - 1], 3)
    BL = round(lead / MM, 2)
    TLD = 10.0                                                           # 제목 줄 행간 — 제목 · 첫 글 줄 사이는 「흐름 글」 단락 앞 간격으로
    t_base = min(s["base"] for s in ttl)
    b_base = min(s["base"] for s in body if s["x"] < cards[0]["x"] + cards[0]["w"] and s["base"] < cards[0]["y"] + cards[0]["h"])
    gap = round(top_of(b_base, 9.5, KCC, 700, BL) - (top_of(t_base, 7.0, JAL, 400, TLD) + TLD * MM), 2)
    first_line = line_of([s for s in body if s["x"] < cards[0]["x"] + cards[0]["w"]], b_base)
    t1 = line_of([s for s in ttl if cards[0]["x"] < s["x"] < cards[0]["x"] + cards[0]["w"]], t_base)    # 첫 칸 제목만 — 같은 기준선에 옆 칸 제목도 있다
    st += need_pstyle("흐름 제목", {"font": JAL, "weight": 400, "size": 7.0, "leading": TLD, "color": "#0067b4", "indent": round(t1["x"] - (cards[0]["x"] + 2.11), 2),
                                 "tracking": track_of(t1, JAL, 400) if len(t1["text"]) > 1 else 0})
    st += need_pstyle("흐름 글", {"font": KCC, "weight": 700, "size": 9.5, "leading": BL, "color": "#000000", "space_before": gap, "space_same": 0,
                                "tracking": track_of(dict(first_line, size=9.5), KCC, 700)})
    for k, c in enumerate(cards):
        st += [S(f"흐름 칸 {k + 1} — 흰 둥근 칸 · 테두리", 900)]
        rim = c                                                          # 테두리는 모눈 그림 위에 — 칠 칸 · 그림 · 테두리 칸 차례
        st += ref_shape(c, fill="#ffffff", measure=False)
        t0 = REF[pno - 1].trimbox
        cover = [i for i in imgs if (i["bbox"][0] - t0.x0) * MM <= c["x"] + 0.5 and (i["bbox"][1] - t0.y0) * MM <= c["y"] + 0.5
                 and (i["bbox"][2] - t0.x0) * MM >= c["x"] + c["w"] - 0.5 and (i["bbox"][3] - t0.y0) * MM >= c["y"] + c["h"] - 0.5]
        im = min(cover, key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]))     # 칸을 덮는 가장 작은 그림
        inset = round(rim["sw"] / 2, 2)
        st += ref_pic(pno, im, f"모눈_{gubun}_{n}_{k + 1}", box={"x": c["x"] + inset, "y": c["y"] + inset, "w": c["w"] - 2 * inset, "h": c["h"] - 2 * inset})
        st += ref_shape(rim, stroke=rim["stroke"], sw=rim["sw"])
        badge = next(d for d in dr if d["fill"] == "#0067b4" and c["x"] < d["x"] < c["x"] + 4 and c["y"] < d["y"] < c["y"] + 5)
        st += ellipse(badge["x"], badge["y"], badge["w"], fill=badge["fill"], h=badge["h"])
        Ebox(badge["x"], badge["y"], badge["w"], badge["h"], badge["fill"])
        dig = next(s for s in sp if s["size"] == 5.5 and badge["x"] < s["x"] < badge["x"] + badge["w"] and abs(s["base"] - (badge["y"] + badge["h"] * 0.7)) < 1.5)
        st += T(dig, JAL, 400, label=f"칸 번호 {dig['text']} — 잘난체")
        ELEMS[len(PAGES)][-1].update(pad=0.0, search=0.0)               # 둘레를 보면 동그라미 밖 흰 칸이 들어온다(1200dpi 맞대기: 위치 차 0 · 잉크 0.998)
        inner = [s for s in sp if (s["size"] == 9.5 or (s["size"] == 7.0 and s["color"] == "#0067b4")) and c["x"] < s["x"] < c["x"] + c["w"] and c["y"] < s["base"] < c["y"] + c["h"]]
        Eslot(inner, "#000000", label=f"흐름 칸 {k + 1}")
        x0 = round(c["x"] + 2.11, 2)
        top = round(top_of(t_base, 7.0, JAL, 400, TLD), 2)
        top = round(top + (c["y"] - cards[0]["y"]), 2)
        st += text(x0, top, round(c["w"] - 4.2, 1), round(c["y"] + c["h"] - 1.0 - top, 1), "흐름 제목\n흐름 글 임시", 9.5, "#000000",
                   label=f"흐름 칸 {k + 1} 텍스트 프레임 — 데이터 필드 「흐름제목+흐름글」(칸마다 단계 하나)", font=KCC, weight=700, leading=BL,
                   first=(JAL, 400, 7.0, TLD))
        st += [pick_p("auto_size", "")]
        st += slot("흐름제목+흐름글")
        st += [slot_style("흐름제목", "흐름 제목"), slot_style("흐름글", "흐름 글")]
        st += grep(0, r"^→", "주황 화살표", label="GREP 스타일 — 줄 앞 「→」에 「주황 화살표」")
        st += grep(1, r"\[[^\]]*\]", "파랑 꼬리표", label="GREP 스타일 — 「[꼬리표]」에 「파랑 꼬리표」")
    # 칸 사이 화살표 — 원본 경로 그대로, 흐름 칸 위에(원본 차례)
    for d in [d for d in dr if d["fill"] == "#b9c1a6" and d["y"] > area["y"] and d["y"] < area["y"] + area["h"] and d["w"] < 12]:
        st += ref_shape(d, fill=d["fill"], label="화살표 — 원본 경로")
        ELEMS[len(PAGES)][-1].update(ctol=18)                            # 화살표 색(원본 화면에서 차 9) · 모눈 줄(차 26~27) 사이 — 30 이면 결과에서만 모눈 줄이 같이 잡혔다
    # 주제 · 요약문 — 바탕 · 꼬리표(KCC도담도담) · 글(Noto 8pt, 원고 자리)
    st += [S("주제 · 요약문", 1000)]
    sbg = find(el, "rect", 18.0, 89.47)
    st += rbox(sbg["x"], sbg["y"], sbg["w"], sbg["h"], sbg["fill"])
    for pill in sorted([d for d in dr if d["fill"] in ("#54669f", "#e5aa7e") and abs(d["w"] - 11.61) < 0.3], key=lambda d: d["y"]):
        st += ref_shape(pill, fill=pill["fill"])
        lab = line_of([s for s in sp if s["size"] == 9.0 and s["color"] == "#ffffff" and pill["y"] < s["base"] < pill["y"] + pill["h"]],
                      next(s["base"] for s in sp if s["size"] == 9.0 and s["color"] == "#ffffff" and pill["y"] < s["base"] < pill["y"] + pill["h"]))
        st += T(lab, KCC, 700, label=f"꼬리표 「{lab['text']}」 — KCC도담도담")
        ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)
    tsp = sorted([s for s in sp if s["size"] == 8.0 and s["color"] == "#000000"], key=lambda s: (round(s["base"], 1), s["x"]))
    srows = sorted({round(s["base"], 2) for s in tsp})
    topic = [s for s in tsp if abs(s["base"] - srows[0]) < 0.3]
    summ = [s for s in tsp if s["base"] > srows[0] + 0.3]
    sl = round(sorted(b - a for a, b in zip(srows[1:], srows[2:]))[max(len(srows) - 2, 1) // 2 - 1] if len(srows) > 2 else 4.0, 3)
    SL = round(sl / MM, 2)
    Eslot(topic, "#000000", label="주제")
    Eslot(summ, "#000000", label="요약문")
    tx = round(min(s["x"] for s in tsp), 2)
    st += need_pstyle("노트 글", {"font": NOTO, "weight": 400, "size": 8.0, "leading": SL, "color": "#000000", "align": "justify",
                                "tracking": track_of(dict(line_of(tsp, srows[-1]), size=8.0), NOTO, 400) if len(line_of(tsp, srows[-1])["text"]) > 6 else 0})
    for nm, base, h in (("주제", srows[0], round(SL * MM * 1.05, 1)), ("요약문", srows[1], round(sbg["y"] + sbg["h"] - 0.5 - top_of(srows[1], 8.0, NOTO, 400, SL), 1))):
        y0 = round(top_of(base, 8.0, NOTO, 400, SL), 2)
        st += text(tx, y0, round(sbg["x"] + sbg["w"] - 2.0 - tx, 1), h, f"{nm} 임시 글", 8.0, "#000000", label=f"{nm} — 원고 자리 「{nm}」", font=NOTO, leading=SL, align="justify")
        st += [pick_p("auto_size", "")]
        st += slot(nm) + [{"pick": {"at": '#side select[data-a="style"]', "value": "노트 글"}, "wait": 700}]
    # 동반의어 — 둥근 테두리 · 머리(흰 바탕 · 주사위 아이콘 · 점 둘 · 글) · 카드 표(원고 수만큼 칸, 3열 · 열마다 색)
    st += [S("동반의어 — 테두리 · 머리", 1000)]
    fr = next(d for d in dr if d["stroke"] and not d["fill"] and d["w"] > 100 and d["y"] > 110)
    st += ref_shape(fr, stroke=fr["stroke"], sw=fr["sw"], label="동반의어 테두리 — 원본 경로")
    hd = find(el, "rect", 20.71, 114.77)
    st += rbox(hd["x"], hd["y"], hd["w"], hd["h"], hd["fill"], label="머리 흰 바탕(테두리를 끊는다)", measure=False)
    st += icon(pno, 24.6, 115.1, 5.5, 5.9, f"주사위_{gubun}_{n}")
    for dot in [d for d in dr if d["fill"] == "#bfc9e6"]:
        st += ellipse(dot["x"], dot["y"], dot["w"], fill=dot["fill"], h=dot["h"])
        Ebox(dot["x"], dot["y"], dot["w"], dot["h"], dot["fill"])
    hsp = [s for s in sp if s["size"] == 7.0 and s["color"] == "#54669f"]
    st += T(line_of(hsp, hsp[0]["base"]), JAL, 400, label="「동반의어」 — 잘난체")
    vc = sorted([d for d in dr if d["fill"] and abs(d["w"] - 34.59) < 0.3 and d["y"] > 118], key=lambda d: (round(d["y"]), d["x"]))
    fills = [d["fill"] for d in vc[:3]]
    gx = round(vc[1]["x"] - (vc[0]["x"] + vc[0]["w"]), 2)
    row2 = [d for d in vc if d["y"] > vc[0]["y"] + 5]
    gy = round(row2[0]["y"] - (vc[0]["y"] + vc[0]["h"]), 2) if row2 else 2.12
    # 알려진 차이(2026-10-12 사용자 확정 「추천하는대로 최대한 보편적이게 인디자인 중심으로」): 원본 카드 오른쪽 아래 접힘 삼각형(카드 색과 밝기 차 6)은
    # 만들지 않는다 — 인디자인 표도 칸마다 장식을 붙일 수 없다. 표(원고 수만큼 칸)를 쓴다
    for d in vc[:3]:                                                     # 첫 줄 칸 — 위 끝 · 폭 · 색 · 칸 사이(표 설정). 높이는 원고 따라 자라니(줄 최소 높이) 위 3mm 띠만
        Ebox(d["x"], d["y"], d["w"], 3.0, d["fill"], pad=0.3)
    vsp = [s for s in sp if s["size"] == 7.0 and s["color"] in ("#000000", "#214e8e", "#e14e6b") and s["base"] > vc[0]["y"]]
    Eslot(vsp, "#000000", label="동반의어 카드")
    vrows = sorted({round(s["base"], 2) for s in vsp if vc[0]["x"] < s["x"] < vc[0]["x"] + vc[0]["w"] and s["base"] < vc[0]["y"] + vc[0]["h"]})
    VL = round((vrows[1] - vrows[0]) / MM, 2)
    word = next(s for s in vsp if s["color"] == "#000000" and abs(s["base"] - vrows[0]) < 0.2 and s["x"] < vc[0]["x"] + 3)
    mean = min((s for s in vsp if s["color"] == "#000000" and abs(s["base"] - vrows[0]) < 0.2 and s["x"] > word["x1"]), key=lambda s: s["x"])
    il = round(word["x"] - vc[0]["x"], 2)
    it_ = round(top_of(vrows[0], 7.0, NOTO, 400, VL) - vc[0]["y"], 2)
    st += need_pstyle("동반의어 동의어", {"font": NOTO, "weight": 400, "size": 7.0, "leading": VL, "color": "#214e8e",
                                     "list": {"type": "bullet", "char": "=", "after": " "}})      # 「= 」 — 글머리 기호 문자 · 텍스트 뒤 공백
    st += need_pstyle("동반의어 반의어", {"font": NOTO, "weight": 400, "size": 7.0, "leading": VL, "color": "#e14e6b",
                                     "list": {"type": "bullet", "char": "↔", "after": " "}})
    tw = round(vc[2]["x"] + vc[2]["w"] - vc[0]["x"], 2)
    st += text(vc[0]["x"], vc[0]["y"], tw, round(vc[0]["h"], 1), "낱말 뜻\n= 동의어\n↔ 반의어", 7.0, "#000000",
               label="동반의어 카드 — 표 글상자 · 자리 「낱말+뜻+동의어+반의어」(항목 하나가 한 칸)", font=NOTO, leading=VL)
    st += [F('#side input[data-it="y"]', vc[0]["y"], 550)]               # 표 — 칸 글 자리는 셀 인세트로(프레임 = 첫 줄 칸 위 끝)
    st += slot("낱말+뜻+동의어+반의어")
    sw = max(gx, gy)                                                     # 칸 사이 = 셀 획(흰색) 두께
    st += [S(f"표 — 3열 · 열 칠 {', '.join(fills)} · 셀 획 흰색 {sw}mm · 셀 인세트 · 행 높이 최소 {vc[0]['h']}mm", 1300),
           F('#side input[data-a="table.cols"]', 3, 900), P_("table.stroke.w", round(sw / MM, 3), 700)] + color_p("table.stroke.color", "#ffffff") + [
           F('#side input[data-a="table.inset"]', f"{it_},{il},0,{il}", 700), F('#side input[data-a="table.row_h"]', round(vc[0]["h"], 2), 700),
           F('#side input[data-a="table.fills"]', ", ".join(fills), 800)]
    gap = mean["x"] - word["x1"]                                         # 낱말 뒤 — 원본 간격에 가장 가까운 공백 문자(인디자인 특수 문자)
    em = 7.0 * MM
    sep = min((("\u2003", 1.0), ("\u2002", 0.5), (" ", space_em(NOTO, 400)), ("\u2009", 0.125), ("\u200a", 1 / 24)), key=lambda c: abs(c[1] * em - gap))[0]
    st += slot_inline("낱말", sep=sep)
    st += [slot_style("동의어", "동반의어 동의어"), slot_style("반의어", "동반의어 반의어")]
    # 옆 탭 · 꼬리 — 암기 정답 면과 같은 꼴
    st += [S("옆 탭 · 꼬리", 1000)]
    stab = next(e for e in el if e["k"] == "path" and abs(e["x"] - 139.0) < 0.5 and e["w"] > 10)
    st += rbox(stab["x"], stab["y"], 15.0, stab["h"], stab["fill"], r=1.6, label="옆 탭 — 왼쪽 모서리 1.6mm(오른쪽은 재단 밖)", measure=False)
    Ebox(stab["x"], stab["y"], W_MM - stab["x"], stab["h"], stab["fill"])
    ts = sorted([s for s in sp if s["size"] == 6.4 and s["color"] == "#ffffff"], key=lambda s: s["base"])
    Eslot(ts, "#ffffff", label="구분")
    st += text(round(ts[0]["x"] - 0.3, 2), round(top_of(ts[0]["base"], 6.4, EL, 700, round((ts[1]["base"] - ts[0]["base"]) / MM, 2)), 2), 3.0, 12.0, "구분",
               6.4, "#ffffff", label="구분 — 원고 자리 「구분」", font=EL, weight=700, leading=round((ts[1]["base"] - ts[0]["base"]) / MM, 2))
    st += slot("구분")
    s_u = line_of([s for s in sp if s["base"] > 190 and s["color"] == "#000000"], next(s["base"] for s in sp if s["base"] > 190 and s["color"] == "#000000"))
    st += T(s_u, EL, 500, label="단원 — 원고 자리 「단원」 (오른쪽 맞춤)", slot_name="단원", temp="단원 이름", align="right", w=40)
    s_no = next(s for s in sp if s["base"] > 190 and s["text"] == str(pno))
    st += T(s_no, EL, 700, label="쪽 번호 — 시스템 자리(오른쪽 맞춤)", bind="sys.page_no", align="right")
    if pno != 2 + len(PAGES) - 1:
        ELEMS[len(PAGES)][-1]["원고"] = True
    st += done(face_name, f"p{pno}.png")
    it = first(lambda x: "흐름" in x and x["_원본쪽"][0] == pno, gubun)
    CONTENT[face_name] = [{"흐름제목+흐름글": [[{"흐름제목": f["제목"], "흐름글": f["글"]}] for f in it["흐름"]],     # 칸마다 제 몫(단계 하나)
                           "주제": it["주제"], "요약문": it["요약문"],
                           "낱말+뜻+동의어+반의어": [[{"낱말": v["낱말"], "뜻": v["뜻"], "동의어": v["동의어"], "반의어": v["반의어"]} for v in it["동반의어"]]],
                           "단원": it["단원"], "구분": it["구분"]}]
    return st




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

if want(3):                                                              # NOTE_PAGES=5 — 막힌 곳 찾을 때 한 쪽만(판정 통과는 세 쪽 다)
    for pno, gb in ((3, "교과서"), (5, "교과서"), (45, "모의고사")):
        if not os.environ.get("NOTE_PAGES") or str(pno) in os.environ["NOTE_PAGES"].split(","):
            st += flownote(pno, gb)

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
