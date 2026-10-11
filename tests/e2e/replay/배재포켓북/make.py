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
    return dict(row[0], x1=row[-1]["x1"], text=" ".join(s["text"] for s in row))


def pg_new(pno, label, name=None):
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label)
    st += [S(label, 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},
           {"pick": {"at": "#side #s-spec", "value": "a5"}, "wait": 1500}]           # 판형 A5 148×210
    if len(PAGES) == 1 and pno > 1:
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    if name:                                                             # 면 이름 (관리 지면 보기가 이 이름으로 묶는다)
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", name, 900)]
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


def analysis(pno, gubun, cs_name):
    """분석 면 — 출처 꼬리표 · 지문(꾸밈 조각 · 윗주) · TRANSLATION · 해석 · 꼬리. 원고 덩어리 = 출처 · 지문 · 해석"""
    st = pg_new(pno, f"② 분석 면 · {gubun} — 원본 {pno}쪽", name=f"분석 면 · {gubun}")
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
    TL = round(tag["h"] / MM, 2)                                         # 행간 = 꼬리표 높이(한 줄)
    lpad, rpad = round(s_src["x"] - tag["x"], 2), round(tag["x"] + tag["w"] - s_src["x1"], 2)
    st += T(dict(s_src, base=s_src["base"]), YD, 400, label="출처 — 원고 자리 「출처」 (꼬리표 = 글상자 칠 · 글 길이만큼)", slot_name="출처", temp="출처 이름",
            w=round(W_MM - 15 - tag["x"], 1), leading=TL, measure=False)
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "both"}, "wait": 700}]
    st += _color("frame.fill", tag["fill"]) + [F('#side input[data-a="frame.radius"]', 1.0), F('#side input[data-a="inset4"]', f"0 {rpad} 0 {lpad}")]
    # 지문 — 한 글상자. 단락 스타일 「분석 지문」(Noto Sans CJK KR 9pt · 양끝맞춤), 꾸밈은 조각의 문자 스타일, 문장 성분 · 서술형★ 은 윗주
    rows = sorted({round(s["base"], 2) for s in sp if s["size"] == 9.0 and 20 < s["base"] < 150})
    lead = round(sorted(b - a for a, b in zip(rows, rows[1:]))[len(rows) // 2 - 1], 3)       # 줄 간격 가운데 값(mm)
    last = line_of(sp, rows[-1])
    LEAD = round(lead / MM, 2)
    st += need_pstyle("분석 지문", {"font": NOTO, "weight": 400, "size": 9.0, "leading": LEAD, "color": "#000000", "align": "justify",
                                 "tracking": track_of(dict(last, size=9.0), NOTO, 400)})
    body = [s for s in sp if 20 < s["base"] < 150]
    Eslot(body, "#000000", label="지문")
    ptop = round(top_of(rows[0], 9.0, NOTO, 400, LEAD), 2)
    st += text(15.0, ptop, 115.0, round(150.0 - ptop, 1), "Temporary passage text for styling the analysis page.", 9.0, "#000000",
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
    ln = find(el, "rect", 15.0, 155.4)
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], ln["fill"])
    tg = find(el, "rect", 114.0, 152.7)
    st += rbox(tg["x"], tg["y"], tg["w"], tg["h"], tg["fill"])
    st += T(next(s for s in sp if s["text"] == "TRANSLATION"), HAK, 300)
    ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)                    # 밝은 글 — 둘레를 넓게 보면 칸 색이 섞인다
    # 해석 — 한 글상자, 「분석 해석」(Pretendard 500 5.9pt)
    trows = sorted({round(s["base"], 2) for s in sp if s["size"] == 5.9 and s["base"] > 155})
    tl = round(sorted(b - a for a, b in zip(trows, trows[1:]))[len(trows) // 2 - 1], 3) if len(trows) > 1 else 3.2
    TLD = round(tl / MM, 2)
    tlast = line_of(sp, trows[-2] if len(trows) > 1 else trows[-1])    # 끝 줄이 아주 짧으면 자간이 튄다 — 그 앞 줄은 양끝맞춤이라 끝 줄만
    tlast = line_of(sp, trows[-1])
    st += need_pstyle("분석 해석", {"font": PRE, "weight": 500, "size": 5.9, "leading": TLD, "color": "#4d4d4d", "align": "justify",
                                 "tracking": track_of(dict(tlast, size=5.9), PRE, 500) if len(tlast["text"]) > 6 else 0})
    Eslot([s for s in sp if s["size"] == 5.9 and s["base"] > 155], "#4d4d4d", label="해석")
    ttop = round(top_of(trows[0], 5.9, PRE, 500, TLD), 2)
    st += text(15.0, ttop, 115.0, round(196.0 - ttop, 1), "임시 해석 글이 이 칸에 들어온다.", 5.9, "#4d4d4d", label="해석 — 한 글상자", font=PRE, leading=TLD, align="justify")
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
    st += slot("해석", label="자리 — 해석")
    st += [{"pick": {"at": '#side select[data-a="style"]', "value": "분석 해석"}, "wait": 700}]
    # 꼬리 — 쪽 번호(남색 · 시스템 자리) · 책 이름(원고 자리 「책이름」)
    st += [S("꼬리 — 쪽 번호 · 책 이름", 1000)]
    s_no = next(s for s in sp if s["base"] > 190 and s["text"] == str(pno))
    st += T(s_no, EL, 500, label="쪽 번호 — 시스템 자리", bind="sys.page_no")
    s_bk = line_of([s for s in sp if s["base"] > 190 and s["color"] == "#000000"], next(s["base"] for s in sp if s["base"] > 190 and s["color"] == "#000000"))
    st += T(s_bk, EL, 500, label="책 이름 — 원고 자리 「책이름」", slot_name="책이름", temp="POCKET BOOK 책 이름", w=50)
    st += done(f"분석 면 {gubun}", f"p{pno}.png")
    it = first(lambda x: "지문" in x and "그림" not in x, gubun)
    CONTENT.setdefault("출처", []).append(it["출처"])
    CONTENT.setdefault("지문", []).append([it["지문"]])         # 글 하나 자리에 조각 — [[조각 …]] (원고자리_규약)
    CONTENT.setdefault("해석", []).append(it["해석"])
    CONTENT.setdefault("책이름", []).append(SRC["book"]["책이름"])
    return st


st = open_doc(NAME)
st += expect_pages(1)

if want(2):
    st += analysis(2, "교과서", "분석 면")
    st += analysis(42, "모의고사", "분석 면")

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
