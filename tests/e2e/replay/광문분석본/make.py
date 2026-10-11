"""광문 스텝업 분석본 — 「광문 스텝업 분석본 (네이비·베이지, A4)」 원본 PDF(21면, 광문1_분석본02(올포7,8강)_내지.pdf)를 보고
편집기로 손수 만든다. 등록 이름 「광문 스텝업 분석본 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」. 이 대본 하나가 문서 하나를 처음부터 만든다 — 구성은 아래 차례대로 덧붙인다.
값은 모두 원본 PDF(상태.json ref)에서 잰다. 원고 자리·원고 꼴은 원고자리_규약.md(2026-10-11 — 꾸밈 조각 · 약속 표시 · 문자 스타일).

구성 차례(원본 구성 판정 — 관리 지면 보기와 같다):
  1 간지(1쪽) · 2 분석 펼침면(2~21쪽, 견본 2·3쪽)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import _color                                               # noqa: E402 — 색 고르기(밑줄 이름이라 * 로 안 온다)
import pymupdf
import pagecmp                                                          # noqa: E402
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
NAME = "광문 스텝업 분석본 (편집기 제작)"
FONTS = os.path.expanduser("~/Library/Fonts")
GM, MY, NOTO, JAL = "Gmarket Sans", "Myriad Pro", "Noto Sans CJK KR", "Jalnan OTF"
NAVY, CREAM, LINE = "#3e4c5a", "#f9f7ed", "#b4aa9a"

ELEMS, PAGES, CONTENT = {}, [], {}


def want(n):
    return not ONLY or str(n) in ONLY


def E(e):
    ELEMS[len(PAGES)].append(e)


def els(pno):
    return [e for e in pagecmp.elements(REF_PATH, pno) if e["x"] < 210 and e["x"] + e["w"] > 0 and e["y"] < 297 and e["y"] + e["h"] > 0]


def clip(e):
    x0, y0, x1, y1 = max(e["x"], 0), max(e["y"], 0), min(e["x"] + e["w"], 210), min(e["y"] + e["h"], 297)
    return dict(e, x=round(x0, 2), y=round(y0, 2), w=round(x1 - x0, 2), h=round(y1 - y0, 2))


def spans(pno):
    """원본 글 조각 — 첫 글자 기준점(x, base) · 끝 글자 오른쪽 · 크기 · 색 · 서체 · 글"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                if ch:
                    out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                                "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "font": sp["font"], "text": "".join(c["c"] for c in sp["chars"]).strip()})
    return out


def sp_of(pno, text, nth=0):
    return [s for s in spans(pno) if s["text"] == text][nth]


def pg_new(pno, label, name=None):
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label)
    if len(PAGES) == 1 and pno > 1:
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    st += [S(label, 1300)]
    if name:                                                             # 면 이름 = 구성 이름 (관리 지면 보기가 이 이름으로 묶는다)
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", name, 900)]
    return st


# ── 브랜드 — 단락 스타일 · 문자 스타일 (구성 하나만 돌려도 그 구성이 쓰는 것을 스스로 갖춘다) ──
_DONE = set()


def _brand_open():
    return [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1500}]


def need_pstyle(name, props, label=None):
    """단락 스타일 — 브랜드 패널 「＋ 단락 스타일」 → 이름 → 칸마다. props: font·weight·size·leading·color·align·tracking·space_after …"""
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


DOC_FONTS = set()


def need_font(fname):
    if fname in DOC_FONTS:
        return []
    DOC_FONTS.add(fname)
    st = text(20.0, 3.0, 24.0, 9.0, "서체", 9, "#231f20", label=f"서체 등록 — 글상자를 그려 고른 채 「＋ 서체」({fname}) → 등록 뒤 그 글상자는 지운다")
    st += register_font(os.path.join(FONTS, fname))
    return st + [{"click": "#side #s-x", "wait": 900}]


def T(s, font, weight, label=None, slot_name=None, temp=None, align=None, cx=None, w=None, leading=None, italic=False, h=None, bind=None, measure=True):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서. align=center 면 가운데 축 cx(mm), right 면 오른쪽 끝 = 원본 끝 글자.
    bind = 시스템 자리(sys.page_no) · measure=False 면 잴 요소를 따로 적는다(두 색 글)"""
    size = s["size"]
    track = 0
    if len(s["text"]) > 1:
        track = round(((s["x1"] - s["x"]) - chrome_extent(font, weight, size, s["text"]) - face(font, weight)[2](s["text"][-1]) * size * MM)
                      / (len(s["text"]) - 1) / (size * MM) * 1000)
    bw = w or round((s["x1"] - s["x"]) * 1.3 + size * 0.4, 1)
    bh = h or round((leading or size * 1.45) * MM * 1.03, 1)
    top = top_of(s["base"], size, font, weight, leading)
    x = s["x"]
    if align == "center":
        x = (cx if cx is not None else (s["x"] + s["x1"]) / 2) - bw / 2
    elif align == "right":                                               # 크롬은 끝 글자 뒤에도 자간을 붙인다 — 그만큼 오른쪽으로
        x = s["x1"] + track / 1000 * size * MM - bw
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - size * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
         "h": round(size * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.6, "search": 0.6, "text": s["text"], "size": size}
    if slot_name:
        m["원고"] = True
    if measure:
        E(m)
    st = text(round(x, 2), round(top, 2), bw, bh, temp if slot_name else s["text"], size, s["color"], label=label, font=font, weight=weight,
              track=track or None, align=align, leading=leading, bind=bind)
    if italic:
        st.append({"click": '#side input[data-a="i"]', "wait": 500})
    if slot_name:
        st += slot(slot_name)
    return st


def B(e, label=None, measure=True, alpha=None):
    if measure:
        c = clip(e)
        E({"id": f"b{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": e["fill"], "see": "auto" if alpha else e["fill"], "pad": 0.6, "ctol": 30})
    return box(e["x"], e["y"], e["w"], e["h"], e["fill"], label=label, alpha=alpha)


def Ebox(x, y, w, h, color, pad=0.6, ctol=30):
    """맞댈 고정 요소 하나 — 재단선 안만"""
    c = clip({"x": x, "y": y, "w": w, "h": h})
    E({"id": f"e{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": color, "see": color, "pad": pad, "ctol": ctol})


def stroke_of(color, sw):
    """획 — 색 · 굵기(원본 mm → 편집기 pt)"""
    return _color("stroke.color", color) + [F('#side input[data-a="stroke.w"]', round(sw / MM, 3))]


def nofill():
    return [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]


def rbox(x, y, w, h, fill=None, stroke=None, sw=0.18, r=0, r4=None, label=None, see=None, ctol=30):
    """면 — 칠 · 획 · 모서리(r4 = 왼위, 오위, 오아래, 왼아래). see = 잴 색(흰 칠에 색 획이면 획 색으로)"""
    st = box(x, y, w, h, fill, label=label, radius=r)
    if r4:
        st.append(F('#side input[data-a="radius4"]', r4))
    if not fill:
        st += nofill()
    if stroke:
        st += stroke_of(stroke, sw)
    col = see or fill or stroke
    if col:
        o = (sw / 2) if (stroke and col == stroke) else 0
        Ebox(x - o, y - o, w + 2 * o, h + 2 * o, col, ctol=ctol)
    return st


def hrule(x, y, w, sw, color, label=None, measure=True, ctol=30):
    """가로 선(획 가운데 y) → 선 굵기만 한 얇은 면"""
    if measure:
        Ebox(x, y - sw / 2, w, sw, color, pad=0.15, ctol=ctol)
    return box(x, round(y - sw / 2, 3), w, sw, color, label=label)


def vrule(x, y, h, sw, color, label=None, measure=True, ctol=30):
    if measure:
        Ebox(x - sw / 2, y, sw, h, color, pad=0.15, ctol=ctol)
    return box(round(x - sw / 2, 3), y, sw, h, color, label=label)


def oval(x, y, w, h, fill=None, stroke=None, sw=None, label=None):
    o = (sw or 0) / 2
    Ebox(x - o, y - o, w + 2 * o, h + 2 * o, stroke or fill)
    return ([S(label)] if label else []) + ellipse(x, y, w, fill=fill, stroke=stroke, sw=round(sw / MM, 3) if sw else None, h=h)


def poly(pts, fill=None, stroke=None, sw=None, label=None):
    """도형 — 원본 꼭짓점 그대로 「경로 d」(상자 0~1)"""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    d = "M" + " L".join(f"{(px - x0) / w:.4f} {(py - y0) / h:.4f}" for px, py in pts) + " Z"
    st = shape(round(x0, 3), round(y0, 3), round(w, 3), round(h, 3), fill or "#ffffff", d=d, label=label)
    if not fill:
        st += nofill()
    if stroke:
        st += stroke_of(stroke, sw)
    return st


def find(el, k, x, y, tol=0.6, **kw):
    """원본 요소표에서 종류 · 자리(왼쪽 위)로 하나"""
    c = [e for e in el if e["k"] == k and abs(e["x"] - x) < tol and abs(e["y"] - y) < tol and all(e.get(a) == v for a, v in kw.items())]
    if not c:
        raise RuntimeError(f"원본 요소 없음 {k} {x},{y} {kw}")
    return c[0]


def Eslot(sps, color="#231f20", label=""):
    """원고 칸 전체를 원고 요소 하나로 — 그 칸 원본 글 조각들의 둘레. 원고는 「들어갔나」만 본다(절차 합격 기준)"""
    x0, x1 = min(s["x"] for s in sps), max(s["x1"] for s in sps)
    y0, y1 = min(s["base"] - s["size"] * MM * 0.95 for s in sps), max(s["base"] + s["size"] * MM * 0.3 for s in sps)
    E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
       "color": color, "see": color, "ctol": 40, "pad": 1.0, "search": 1.0, "text": label, "size": sps[0]["size"], "원고": True})


def recolor(s_all, s_part, cs, label=None):
    """고정 글 일부만 다른 색 — 글상자를 두 번 눌러 고치기 창에서 그 글자를 끌어 고르고 문자 스타일을 입힌다(사람처럼)"""
    cx, cy = (s_all["x"] + s_all["x1"]) / 2, s_all["base"] - s_all["size"] * MM * 0.35
    return ([S(label)] if label else []) + [{"dbl": {"mm": [round(cx, 2), round(cy, 2)]}, "wait": 1200}, {"select": {"text": s_part}, "wait": 600},
                                            {"pick": {"at": "#rt-cs", "value": cs}, "wait": 900}, {"click": AWAY, "wait": 1200}]


def ring(e, label=None):
    sw = e["sw"]
    E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(e["x"] - sw / 2, 2), "y": round(e["y"] - sw / 2, 2), "w": round(e["w"] + sw, 2), "h": round(e["h"] + sw, 2),
       "color": e["stroke"], "see": e["stroke"], "pad": 0.6, "ctol": 30})
    return ([S(label)] if label else []) + ellipse(e["x"], e["y"], e["w"], stroke=e["stroke"], sw=round(sw / MM, 2), h=e["h"])


st = open_doc(NAME)
st += expect_pages(1)

# ── 구성 1 「간지」 (원본 1쪽) ── 학교 · 권 번호 · 교재명+강제목 은 원고, 나머지는 고정
if want(1):
    st += pg_new(1, "① 간지 — 원본 1쪽", name="간지")
    el = els(1)
    rects = [e for e in el if e["k"] == "rect"]
    st += [S("바탕 — 재단 여백까지", 1200)] + box(-3, -3, 216, 303, "#f9f7ed") + box(-3, -3, 216, 303, "#f6f2e9")
    # 대각 면 둘 — 원본은 직사각형을 삼각형으로 잘라 불투명 55% · 60% (원본 잘라내기 꼭짓점 그대로)
    # 잴 색 = 원본에서 겹친 색(55% 흰색 + 바탕 #f6f2e9 = #fbf9f5 · 60% #dfe1e3 + 바탕 = #e8e8e5) — 「색 자동」은 뾰족한 끝 흐린 데만 잡았다
    E({"id": "tri1", "x": 0, "y": 0, "w": 119.3, "h": 87.9, "color": "#fbf9f5", "see": "#fbf9f5", "pad": 0.6, "ctol": 4})
    st += shape(-3, -3, 125.3, 90.9, "#ffffff", d="M0 0 L0 1 L1 0 Z", label="왼쪽 위 대각 면 — 흰색 불투명 55%") + opacity(55)
    E({"id": "tri2", "x": 118.2, "y": 233.5, "w": 91.8, "h": 63.5, "color": "#e8e8e5", "see": "#e8e8e5", "pad": 0.6, "ctol": 6})
    st += shape(118.2, 233.5, 94.8, 66.5, "#dfe1e3", d="M0 1 L1 1 L1 0 Z", label="오른쪽 아래 대각 면 — 회색 불투명 60%") + opacity(60)
    # 오른쪽 위 탭 — 왼쪽만 둥근 띠(둥근 반지름 = 높이 반). 오른쪽 둥근 데는 재단 여백 밖으로 늘려 안 보이게
    E({"id": "tab", "x": 151.1, "y": 13.4, "w": 58.9, "h": 11.1, "color": NAVY, "see": NAVY, "pad": 0.6, "ctol": 30})
    st += box(151.1, 13.4, 68.0, 11.1, NAVY, label="오른쪽 위 탭 — 왼쪽 둥근 띠") + [F('#side input[data-a="radius"]', 5.55)]
    st += need_cstyle("연도 굵게", {"weight": 700}, label="문자 스타일 「연도 굵게」 — 학교 자리의 앞 연도만 굵게")
    s = sp_of(1, "2026")
    s = dict(s, text="2026 광문고1", x1=sp_of(1, "광문고1")["x1"])
    st += T(s, GM, 500, label="학교 — 원고 자리 「학교」 (연도는 GREP → 「연도 굵게」)", slot_name="학교", temp="0000 학교 이름")
    st += grep(0, r"^\d{4}", label="GREP — 앞 네 자리 연도", bold=False) + [{"pick": {"at": '#side select[data-a="grep.0.cs"]', "value": "연도 굵게"}, "wait": 700}]
    CONTENT["학교"] = ["2026 광문고1"]
    # STEP UP · 스텝업 분석본 — 원본은 글자 윤곽(도형)이라 그 윤곽을 그림 파일로 올린다(정본 로고와 같은 방법)
    E({"id": "stepup", "x": 22.1, "y": 58.3, "w": 39.4, "h": 3.9, "color": "#363c3f", "see": "#363c3f", "pad": 0.6, "ctol": 30})
    st += image(22.0, 58.2, 39.6, 4.1, os.path.join(HERE, "step_up.svg"), label="STEP UP — 원본 윤곽 그림(step_up.svg)")
    E({"id": "stepup_ko", "x": 22.4, "y": 70.6, "w": 22.7, "h": 3.7, "color": "#010101", "see": "#010101", "pad": 0.6, "ctol": 30})
    st += image(22.3, 70.5, 22.9, 3.9, os.path.join(HERE, "stepup_ko.svg"), label="스텝업 분석본 — 원본 윤곽 그림(stepup_ko.svg)")
    thin, thick = [e for e in rects if abs(e["y"] - 66.1) < 0.2 and e["w"] > 40][0], [e for e in rects if abs(e["y"] - 66.1) < 0.2 and e["w"] < 20][0]
    vis = thick["x"] + thick["w"] + 1.0                                 # 가는 선의 왼쪽은 굵은 남색 선에 덮인다 — 보이는 데만, 남색 끝 흐림(인디자인·크롬이 점 하나 다르게)에서 1mm 떨어져
                                                                         # 왼쪽 끝 = 남색 선 끝이라 그쪽(thick)에서 맞댄다
    E({"id": "thin", "x": round(vis, 2), "y": thin["y"], "w": round(thin["x"] + thin["w"] - vis, 2), "h": thin["h"], "color": thin["fill"], "see": thin["fill"], "pad": 0.6, "ctol": 30})
    st += B(thin, "제목 아래 선 — 가는 선", measure=False)
    st += B(thick, "제목 아래 선 — 굵은 남색")
    rings = sorted([e for e in el if e["k"] == "path" and e.get("stroke") and e["w"] > 20], key=lambda e: -e["w"])
    st += ring(rings[0], "권 번호 원 — 바깥(남색)") + ring(rings[1], "권 번호 원 — 안(금색)")
    st += need_font("MyriadPro-BoldIt.otf")
    cx = rings[0]["x"] + rings[0]["w"] / 2
    st += T(sp_of(1, "2"), MY, 700, label="권 번호 — 원고 자리 「권번호」 (Myriad Pro 굵은 기울임, 원 가운데)", slot_name="권번호", temp="0",
            align="center", cx=cx, w=24, italic=True)
    CONTENT["권번호"] = ["2"]
    # 교재명 + 강제목 — 한 글상자에 번갈아(쌍 수는 책마다). 행간·단락 뒤 간격은 원본 기준선 간격에서
    b1, k1, b2 = sp_of(1, "올림포스 영어독해 기본2", 0), sp_of(1, "7강 학술문 내용 불일치"), sp_of(1, "올림포스 영어독해 기본2", 1)
    asc, desc, _ = face(GM, 700)
    r = asc - desc
    s1, s2 = b1["size"] * MM, k1["size"] * MM
    lead = (k1["base"] - b1["base"]) - r * (s2 - s1) / 2                 # 같은 행간 L: 기준선 간격 = L + (a−d)(s뒤 − s앞)/2 + 앞 단락 뒤 간격
    after = round((b2["base"] - k1["base"]) - lead - r * (s1 - s2) / 2, 2)
    LP = round(lead / MM, 2)
    st += need_pstyle("교재명", {"font": GM, "weight": 700, "size": b1["size"], "leading": LP, "color": b1["color"], "align": "center"})
    st += need_pstyle("강제목", {"font": GM, "weight": 500, "size": k1["size"], "leading": LP, "color": k1["color"], "align": "center", "space_after": after})
    for s, nm in ((b1, "교재명"), (k1, "강제목"), (b2, "교재명"), (sp_of(1, "8강 어법 정확성"), "강제목")):
        E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - s["size"] * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
           "h": round(s["size"] * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 1.0, "search": 1.0, "text": s["text"], "size": s["size"], "원고": True})
    axis = (b1["x"] + b1["x1"]) / 2
    top = top_of(b1["base"], b1["size"], GM, 700, LP)
    st += text(round(axis - 60, 2), round(top, 2), 120, round(270 - top, 1), "교재 이름\n00강 강 제목", b1["size"], b1["color"],
               label="교재명 + 강제목 — 한 글상자에 번갈아 흐른다(쌍 수는 원고만큼)", font=GM, weight=700, align="center", leading=LP)
    st += slot("교재명+강제목", label="자리 — 교재명+강제목 (원고의 쌍 차례대로)")
    for n in ("교재명", "강제목"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{n}.style"]', "value": n}, "wait": 600})
    CONTENT["교재명+강제목"] = [{"교재명": "올림포스 영어독해 기본2", "강제목": "7강 학술문 내용 불일치"},
                              {"교재명": "올림포스 영어독해 기본2", "강제목": "8강 어법 정확성"}]
    st += [S("아래 색 막대 셋", 1000)]
    for e in sorted([e for e in rects if abs(e["y"] - 280.2) < 0.2], key=lambda e: e["x"]):
        st += B(e)
    st += done("간지", "p1.png")

# ── 구성 2 「분석 펼침면」 (원본 2~21쪽 = 펼침면 10벌 · 원고마다) — 견본 = 2·3쪽 ──
# 원고 한 건(지문 하나) = 펼침면 한 벌. 왼쪽: 강 · 회차 · 지문제목 · 문장+해석(꾸밈 조각 · 옆 메모) / 오른쪽: 주제 · 요약 · 발문+문제지문+선지 · 답 · 어휘.
# 꼬리 「7강  분석」 = 강+회차(같은 레코드의 두 자리를 한 줄로).
CS = {                                                                   # 문자 스타일 — 원본에서 잰 값
    "번호 배지": {"font": JAL, "size": 9, "color": "#ffffff", "bg": "#426893", "bg_pad": 0.45, "bg_r": 0.5},
    "파랑 글자": {"color": "#224e8e"}, "빨강 글자": {"color": "#d2232a"},
    # 형광 = 글 뒤 가로 띠(원본은 굵은 밑줄 9pt = 3.17mm, 가운데가 기준선 위 1.05mm) — 문자 스타일 「바탕 · 띠 두께 · 띠 높이」
    "형광 민트": {"bg": "#ceeae0", "bg_band": 3.17, "bg_off": 1.05},
    "형광 노랑": {"bg": "#fef9c1", "bg_band": 3.17, "bg_off": 1.05},
    "형광 보라": {"bg": "#dbd4ea", "bg_band": 3.17, "bg_off": 1.05},
    "밑줄": {"u": True, "line": 0.16, "line_off": 0.4},
    "빨강 물결": {"u": True, "u_style": "wavy", "line": 0.18, "line_off": 0.9, "line_color": "#d2232a"},
    "구문 표기": {"font": "휴먼범석체", "size": 7, "color": "#132961"},
    "서술형": {"font": "휴먼범석체", "size": 6, "color": "#d2232a"},
    "메모": {"font": "SKYBORI", "size": 6.96, "color": "#231f20"},
}
EL = "Elice DX Neolli OTF"


def spread(lp):
    from read_spread import left, right
    rp = lp + 1
    st = pg_new(lp, f"② 분석 펼침면 — 원본 {lp}쪽 (왼쪽 · 문장 분석)", name="분석 펼침면")
    st += [{"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1200}]
    st += need_font("SKYBORI.otf")
    for n, props in CS.items():
        st += need_cstyle(n, props)
    st += need_cstyle("포인트 연한", {"color": "#a7bcbc"}) + need_cstyle("기출문제 회색", {"color": "#7c8193"})
    el = els(lp)
    sp = spans(lp)
    # 머리 — 크림 띠 · 선 · 남색 탭(위 두 모서리만 둥글다) · 흰 타원 테 · 흰 세로 선
    band = find(el, "rect", -3, -3, fill=CREAM)
    st += [S("머리 — 크림 띠 · 선", 1200)] + rbox(band["x"], band["y"], band["w"], band["h"], CREAM)
    ln = find(el, "line", -3, 18.0)
    st += hrule(ln["x"], ln["y"], ln["w"], ln["sw"], ln["stroke"])
    tab = find(el, "path", 8.0, 4.8)
    st += rbox(tab["x"], tab["y"], tab["w"], tab["h"], tab["fill"], r4="6.65, 6.65, 0, 0", label="남색 탭 — 위 두 모서리 둥글게(6.65mm)")
    # 흰 타원 테(11, 7.7)는 원본에서 남색 탭보다 먼저 그려져 탭에 덮인다 — 보이지 않으니 그리지 않는다
    dv = find(el, "line", 52.3, 9.0)
    st += vrule(dv["x"], dv["y"], dv["h"], dv["sw"], dv["stroke"])
    s_k = next(s for s in sp if s["base"] < 16 and s["size"] > 18)
    s_r = next(s for s in sp if s["base"] < 16 and abs(s["size"] - 12) < 0.3)
    s_t = next(s for s in sp if s["base"] < 16 and abs(s["size"] - 8) < 0.3)
    st += T(s_k, GM, 700, label="강 — 원고 자리 「강」", slot_name="강", temp="00강")
    st += T(s_r, GM, 500, label="회차 — 원고 자리 「회차」", slot_name="회차", temp="회차")
    st += T(s_t, NOTO, 500, label="지문 제목 — 원고 자리 「지문제목」", slot_name="지문제목", temp="지문 제목", w=100)
    # GRAMMAR POINT — 흰 타원 · 청록 테 · 두 색 글(뒤 POINT 는 고치기 창에서 골라 「포인트 연한」)
    gp = find(el, "path", 144.1, 22.4)
    st += oval(gp["x"], gp["y"], gp["w"], gp["h"], fill=gp["fill"], stroke=gp["stroke"], sw=gp["sw"], label="GRAMMAR POINT 타원")
    g1, g2 = next(s for s in sp if s["text"] == "GRAMMAR"), next(s for s in sp if s["text"] == "POINT")
    gall = dict(g1, text="GRAMMAR POINT", x1=g2["x1"])
    for s in (g1, g2):
        E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - s["size"] * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
           "h": round(s["size"] * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.5, "search": 0.5, "text": s["text"], "size": s["size"]})
    st += T(gall, GM, 700, label="GRAMMAR POINT — 한 글상자", measure=False)
    st += recolor(gall, "POINT", "포인트 연한", label="POINT 만 연한 청록 — 고치기 창에서 골라 문자 스타일")
    vl = find(el, "line", 143.0, 31.4)
    st += vrule(vl["x"], vl["y"], vl["h"], vl["sw"], vl["stroke"], label="세로 구분선", ctol=6)
    # 문장 + 해석 — 한 글상자에 번갈아. 번호 배지 = GREP → 문자 스타일, 표기 = 윗주, GRAMMAR POINT 메모 = 옆 메모(고정 개체)
    rows = [s for s in sp if 8.8 <= s["size"] <= 9.0 and s["x"] < 140]
    b0 = min(s["base"] for s in rows)
    LEAD_S, LEAD_K = 24.1, round(4.3 / MM, 2)                            # 문장 행간 8.5mm · 해석 행간 4.3mm
    asc, desc, _ = face(NOTO, 400)
    r_ = asc - desc
    s1, s2 = 8.95 * MM, 6.3 * MM
    sp1 = round(8.0 - (LEAD_S * MM / 2 - r_ * s1 / 2 + LEAD_K * MM / 2 + r_ * s2 / 2), 2)   # 문장 끝 줄 → 해석 첫 줄 8.0mm
    sp2 = round(8.8 - (LEAD_K * MM / 2 - r_ * s2 / 2 + LEAD_S * MM / 2 + r_ * s1 / 2), 2)   # 해석 끝 줄 → 다음 문장 8.8mm
    # 자간 — 원본 문단 끝 줄(양끝맞춤 안 된 줄)의 첫~끝 글자 거리에서: 문장 −13‰ · 해석 −47‰
    st += need_pstyle("분석 문장", {"font": NOTO, "weight": 400, "size": 8.95, "leading": LEAD_S, "color": "#231f20", "align": "justify", "tracking": -13, "space_after": sp1})
    st += need_pstyle("분석 해석", {"font": NOTO, "weight": 400, "size": 6.3, "leading": LEAD_K, "color": "#6d6e71", "align": "justify", "tracking": -47, "space_after": sp2})
    ha, hd, _ = face("휴먼범석체", 400)
    sl = 7 * MM
    off_a = round(2.64 - ((sl - (ha + hd) * sl) / 2 + hd * sl), 2)        # 위 표기 기준선 = 문장 기준선 위 2.64mm (원본 「단 S」)
    off_b = round(3.36 - ((sl - (ha + hd) * sl) / 2 + ha * sl), 2)        # 아래 표기 기준선 = 문장 기준선 아래 3.36mm (원본 「동격」)
    from fontTools.ttLib import TTFont                                  # SKYBORI 는 fontTools 가 글자표를 못 읽는다(글리프 이름) — 높이만 hhea 에서
    _hh = TTFont(os.path.join(FONTS, "SKYBORI.otf"))
    ka, kd = _hh["hhea"].ascent / _hh["head"].unitsPerEm, -_hh["hhea"].descent / _hh["head"].unitsPerEm
    ks, klead = 6.96 * MM, 3.5
    off_m = round(-0.5 - ((klead - (ka + kd) * ks) / 2 + ka * ks), 2)    # 메모 첫 기준선 = 그 문장 첫 기준선 위 0.5mm
    top = round(top_of(b0, 8.95, NOTO, 400, LEAD_S), 2)
    body = [s for s in sp if s["x"] < 140 and 26 < s["base"] < 280 and s["size"] < 9.2]      # 문장 · 해석 · 표기 · 번호
    Eslot(body, label="문장+해석")
    memo = [s for s in sp if s["x"] > 145 and 30 < s["base"] < 280]
    if memo:
        Eslot(memo, label="옆 메모")
    st += text(22.0, top, 115.0, round(277.0 - top, 1), "0 Temporary sentence for styling the analysis line.\n임시 해석이 이 줄에 들어온다.", 8.95, "#231f20",
               label="문장 + 해석 — 한 글상자(원고만큼 번갈아)", font=NOTO, leading=LEAD_S, align="justify")
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
    st += slot("문장+해석", label="자리 — 문장+해석")
    st += [{"pick": {"at": '#side select[data-a="slotfmt.문장.style"]', "value": "분석 문장"}, "wait": 600},
           {"pick": {"at": '#side select[data-a="slotfmt.해석.style"]', "value": "분석 해석"}, "wait": 600}]
    st += grep(0, r"^\d{1,2}(?= )", bold=False, label="GREP — 문장 앞 번호는 「번호 배지」") + [{"pick": {"at": '#side select[data-a="grep.0.cs"]', "value": "번호 배지"}, "wait": 700}]
    st += [S("윗주 기본값 — 「구문 표기」 · 위 · 아래 거리 · 본문 가운데", 1200),
           {"pick": {"at": '#side select[data-a="ruby.cs"]', "value": "구문 표기"}, "wait": 700},
           F('#side input[data-a="ruby.off_above"]', off_a), F('#side input[data-a="ruby.off_below"]', off_b),
           {"pick": {"at": '#side select[data-a="ruby.align"]', "value": "center"}, "wait": 700},
           S("옆 메모 — GRAMMAR POINT 칸(x 125.3 · 폭 40.2mm) · 「메모」 · 행간 3.5mm", 1200),
           F('#side input[data-a="side.x"]', 125.3), F('#side input[data-a="side.w"]', 40.2), F('#side input[data-a="side.off"]', off_m),
           F('#side input[data-a="side.lead"]', round(klead / MM, 2)),
           {"pick": {"at": '#side select[data-a="side.cs"]', "value": "메모"}, "wait": 700}]
    # 꼬리 — 쪽 번호(책이 채움) · STEP UP
    st += [S("꼬리 — 쪽 번호 · STEP UP", 1000)]
    st += T(next(s for s in sp if s["base"] > 280 and s["text"] == str(lp)), EL, 700, label="쪽 번호 — 시스템 자리", bind="sys.page_no")
    st += T(next(s for s in sp if s["base"] > 280 and s["text"] == "STEP UP"), EL, 700)
    st += done("분석 펼침면 왼쪽", f"p{lp}.png")

    # ── 오른쪽 면 ──
    st += pg_new(rp, f"② 분석 펼침면 — 원본 {rp}쪽 (오른쪽 · 문항 · VOCA)")
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1200}]
    el = els(rp)
    sp = spans(rp)
    band = find(el, "rect", -3, -3, fill=CREAM)
    st += [S("머리 — 크림 띠 · 선 · 꺾인 흰 면(폴더 탭)", 1300)] + rbox(band["x"], band["y"], band["w"], band["h"], CREAM)
    ln = find(el, "line", 0, 18.0)
    Ebox(0, ln["y"] - ln["sw"] / 2, 18.3, ln["sw"], ln["stroke"], pad=0.15)    # 보이는 데 — 꺾인 흰 면 왼쪽까지
    st += hrule(0, ln["y"], 210.0, ln["sw"], ln["stroke"], measure=False)
    Ebox(22.6, 14.24 - 0.105, 187.4, 0.21, LINE, pad=0.15)                   # 꺾인 흰 면의 윗선
    st += poly([(22.51, 14.24), (18.51, 18.24), (18.51, 24.64), (213.13, 24.64), (213.13, 14.24)], fill="#ffffff", stroke=LINE, sw=0.21,
               label="꺾인 흰 면 — 원본 꼭짓점 · 테두리 0.21mm")
    st += rbox(18.4, 18.1, 194.6, 8.8, "#ffffff", see=None, label="흰 면 — 아래 테두리를 덮는다")
    ELEMS[len(PAGES)].pop()                                              # 흰 면은 재지 않는다(흰 바탕)
    for e, lab in ((find(el, "path", 22.0, 20.0), "주제"), (find(el, "path", 22.0, 25.5), "요약")):
        st += rbox(e["x"], e["y"], e["w"], e["h"], e["fill"], r=1.4, label=f"「{lab}」 둥근 이름표")
        st += T(next(s for s in sp if s["text"] == lab and s["size"] < 8), EL, 700)
        ELEMS[len(PAGES)][-1].update(pad=0.2, search=0.2)                # 흰 글 — 둘레를 넓게 보면 이름표 사이 흰 바탕이 섞인다
    s_top = next(s for s in sp if abs(s["size"] - 8.37) < 0.1 and s["base"] < 24)
    s_sum = next(s for s in sp if abs(s["size"] - 8.37) < 0.1 and 25 < s["base"] < 29)
    st += T(s_top, NOTO, 500, label="주제 — 원고 자리 「주제」", slot_name="주제", temp="Topic of the passage", w=157.0)
    st += T(s_sum, NOTO, 500, label="요약 — 원고 자리 「요약」 (길면 아래로)", slot_name="요약", temp="Summary of the passage in one or two lines.", w=157.2,
            leading=round(4.5 / MM, 2))
    # 핵심기출문제 · NOTE — 타원 이름표 · 상자
    o1, o2 = find(el, "path", 23.8, 40.7), find(el, "path", 119.2, 40.7)
    st += oval(o1["x"], o1["y"], o1["w"], o1["h"], fill="#ffffff", stroke=o1["stroke"], sw=o1["sw"], label="핵심기출문제 타원")
    h1, h2 = next(s for s in sp if s["text"] == "핵심"), next(s for s in sp if s["text"] == "기출문제")
    hall = dict(h1, text="핵심기출문제", x1=h2["x1"])
    for s in (h1, h2):
        E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - s["size"] * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
           "h": round(s["size"] * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.5, "search": 0.5, "text": s["text"], "size": s["size"]})
    for e in ELEMS[len(PAGES)][-2:]:                                    # 같은 남색 타원 테가 둘레에 섞이지 않게
        e.update(pad=0.2, search=0.2)
    st += T(hall, GM, 700, measure=False)
    st += recolor(hall, "기출문제", "기출문제 회색", label="「기출문제」 만 회색")
    st += oval(o2["x"], o2["y"], o2["w"], o2["h"], fill="#ffffff", stroke=o2["stroke"], sw=o2["sw"], label="NOTE 타원")
    st += T(next(s for s in sp if s["text"] == "NOTE"), GM, 700)
    qb = find(el, "path", 22.0, 48.2)
    st += rbox(qb["x"], qb["y"], qb["w"], qb["h"], None, stroke=LINE, sw=qb.get("sw") or 0.18, r=2.0, label="문제 상자 — 둥근 테")
    nb = find(el, "path", 117.4, 48.2)
    st += rbox(nb["x"], nb["y"], nb["w"], nb["h"], "#ffffff", stroke=LINE, sw=nb.get("sw") or 0.18, r=2.0, see=LINE, label="NOTE 상자")
    # 문제 — 발문+문제지문+선지 한 글상자(문단 사이 빈 줄 5.1mm) · 답(오른쪽 아래)
    QL = round(5.1 / MM, 2)
    # 자간 −32‰ (원본 문단 끝 줄 셋에서 −32.1 ~ −32.7)
    st += need_pstyle("문제 발문", {"font": NOTO, "weight": 400, "size": 7.5, "leading": QL, "color": "#231f20", "tracking": -32, "space_after": 5.1})
    st += need_pstyle("문제 지문", {"font": NOTO, "weight": 400, "size": 7.5, "leading": QL, "color": "#231f20", "align": "justify", "indent_first": 1.73, "tracking": -32, "space_after": 5.1})
    st += need_pstyle("문제 선지", {"font": NOTO, "weight": 400, "size": 7.5, "leading": QL, "color": "#231f20", "tracking": -32})
    qrows = [s for s in sp if abs(s["size"] - 7.5) < 0.1 and 50 < s["base"] < 168 and s["x"] < 112]
    Eslot([s for s in sp if 50 < s["base"] < 168 and s["x"] < 112 and 7.0 < s["size"] < 7.6], label="발문+문제지문+선지")
    qtop = round(top_of(min(s["base"] for s in qrows), 7.5, NOTO, 400, QL), 2)
    st += text(25.03, qtop, 85.9, round(168.5 - qtop, 1), "다음 글의 임시 발문은?\nTemporary passage text for styling.\n① choice one\n② choice two", 7.5, "#231f20",
               label="문제 — 발문+문제지문+선지 한 글상자", font=NOTO, leading=QL)
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700}]
    st += slot("발문+문제지문+선지", label="자리 — 발문+문제지문+선지")
    for n, sty in (("발문", "문제 발문"), ("문제지문", "문제 지문"), ("선지", "문제 선지")):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{n}.style"]', "value": sty}, "wait": 600})
    s_ans = next(s for s in sp if s["text"].startswith("답:"))
    st += T(s_ans, NOTO, 400, label="답 — 원고 자리 「답」 (오른쪽 맞춤)", slot_name="답", temp="답: ⑤", align="right", w=30)
    # 기출 포인트 — 이름표 · 꺾인 상자 · 그림자 선 · 체크 칸 10 · 이름 10
    st += [S("기출 포인트 — 이름표 · 상자 · 체크 칸", 1300)]
    tg = [(21.9, 182.7), (21.9, 186.1), (41.6, 186.1), (41.6, 184.4), (39.6, 182.7)]
    Ebox(21.9, 182.7, 19.7, 3.4, LINE)
    st += poly(tg, fill=LINE, label="기출 포인트 이름표 — 오른쪽 위 비스듬히")
    st += T(next(s for s in sp if s["text"] == "기출 포인트"), GM, 700)
    bx = [(22.0, 185.96), (187.25, 185.96), (187.25, 187.59), (189.25, 187.59), (189.25, 198.2), (22.0, 198.2)]
    Ebox(22.0 - 0.09, 185.96 - 0.09, 167.25 + 0.18, 12.24 + 0.18, LINE, pad=0.15)   # 눈에 보이는 경계 = 테두리
    st += poly(bx, fill="#fcf8ef", stroke=LINE, sw=0.18, label="기출 포인트 상자 — 오른쪽 위 꺾임")
    st += hrule(23.0, 199.1, 167.0, 0.18, LINE, label="그림자 선") + vrule(190.0, 187.9, 11.2, 0.18, LINE)
    for e in sorted([e for e in el if e["k"] == "path" and abs(e["w"] - 2.9) < 0.15 and abs(e["h"] - 3.1) < 0.15], key=lambda e: (e["y"], e["x"])):
        st += rbox(e["x"], e["y"], e["w"], e["h"], "#ffffff", stroke=e["stroke"], sw=e["sw"], r=0.6, see=e["stroke"])
    for s in [s for s in sp if abs(s["size"] - 6.89) < 0.05]:
        st += T(s, GM, 500)
    # VOCA — 회색 띠 · 머리 이름표(테 · 글) · 흰 바탕 · 줄 16
    st += [S("VOCA — 띠 · 머리 칸 · 줄", 1300)]
    vb = find(el, "rect", 22.0, 200.7)
    st += rbox(vb["x"], vb["y"], vb["w"], vb["h"], vb["fill"])
    st += T(next(s for s in sp if s["text"].replace(" ", "") == "VOCA"), GM, 700)
    for e in sorted([e for e in el if e["k"] == "path" and abs(e["y"] - 206.8) < 0.2 and e.get("stroke")], key=lambda e: e["x"]):
        rx, ry = round(0.5 / e["w"], 4), round(0.5 / e["h"], 4)          # 아래가 트인 둥근 꺾쇠(∩) — 원본 열린 선 그대로(모서리 0.5mm)
        d = f"M0 1 L0 {ry} Q0 0 {rx} 0 L{1 - rx:.4f} 0 Q1 0 1 {ry} L1 1"
        # 잴 데 = 위 1.5mm(윗선 · 모서리 · 양옆) — 트인 아래 끝은 0.1mm 선 끝이 흐려 원본·결과 모두 점 하나(0.23mm)씩 들쭉날쭉 잡힌다
        Ebox(e["x"] - e["sw"] / 2, e["y"] - e["sw"] / 2, e["w"] + e["sw"], 1.5, e["stroke"], pad=0.15)
        st += shape(e["x"], e["y"], e["w"], e["h"], "#ffffff", d=d) + nofill() + stroke_of(e["stroke"], e["sw"])
    for s in [s for s in sp if abs(s["size"] - 5.91) < 0.05]:
        st += T(s, GM, 500)
    st += rbox(22.0, 210.6, 168.0, 62.6, "#ffffff")
    ELEMS[len(PAGES)].pop()
    vy = sorted({round(e["y"], 2) for e in el if e["k"] == "line" and e.get("stroke") == "#e0e0f1"})
    sw_v = next(e["sw"] for e in el if e["k"] == "line" and e.get("stroke") == "#e0e0f1")
    for y in vy:
        st += hrule(22.0, y, 168.0, sw_v, "#e0e0f1", ctol=20)              # 아주 연한 선 — 점 하나 폭이라 흐려진다
    # 어휘 — 3단(차례로 채우기) · 탭(뜻은 28mm) · 행간 4.47mm · 높이 14줄
    VL = round(4.47 / MM, 2)
    vrows = [s for s in sp if abs(s["size"] - 7.0) < 0.05 and s["base"] > 210]
    Eslot(vrows, label="어휘")
    vtop = round(top_of(min(s["base"] for s in vrows), 7.0, NOTO, 400, VL), 2)
    st += text(23.0, vtop, 168.0, round(14 * 4.47, 2), "word\t뜻\nword\t뜻", 7.0, "#231f20", label="어휘 — 원고 자리 「어휘」 (3단 · 탭)", font=NOTO, leading=VL)
    st += [{"pick": {"at": '#side select[data-a="auto_size"]', "value": "off"}, "wait": 700},
           {"clickif": {"at": "#side details.more > summary", "when": "!document.querySelector('#side details.more').open"}, "wait": 700},
           F('#side input[data-a="tabspec"]', "28 left"), F('#side input[data-a="columns"]', 3, 900), F('#side input[data-a="gutter"]', 0, 700),
           {"click": '#side input[data-a="col_seq"]', "wait": 700}]
    st += slot("어휘", label="자리 — 어휘(줄마다 「낱말<탭>뜻」)")
    # 꼬리 — 「7강  분석」 = 강+회차(오른쪽 맞춤) · 쪽 번호
    st += [S("꼬리 — 강+회차 · 쪽 번호", 1000)]
    st += need_pstyle("꼬리 글", {"font": EL, "weight": 700, "size": 6.0, "leading": 8.0, "color": "#231f20", "align": "right"})
    s_f = next(s for s in sp if s["base"] > 280 and "강" in s["text"])
    gap = round(face(EL, 700)[2]("  ") * 6.0 * MM, 2)                    # 「7강」 뒤 빈칸 둘
    E({"id": f"f{len(ELEMS[len(PAGES)])}", "x": round(s_f["x"], 2), "y": round(s_f["base"] - 1.8, 2), "w": round(s_f["x1"] - s_f["x"], 2), "h": 2.2,
       "color": "#231f20", "see": "#231f20", "ctol": 24, "pad": 0.6, "search": 0.6, "text": s_f["text"], "size": 6.0, "원고": True})
    st += T(dict(s_f), EL, 700, label="꼬리 — 강+회차 한 줄(오른쪽 맞춤)", slot_name="강+회차", temp="00강  회차", align="right", w=40, leading=8.0, measure=False)
    st += [{"pick": {"at": '#side select[data-a="slotfmt.강.style"]', "value": "꼬리 글"}, "wait": 600},
           {"pick": {"at": '#side select[data-a="slotfmt.회차.style"]', "value": "꼬리 글"}, "wait": 600},
           {"click": '#side input[data-a="slotfmt.강.inline"]', "wait": 700}, F('#side input[data-a="slotfmt.강.inline_gap"]', gap)]
    st += T(next(s for s in sp if s["base"] > 280 and s["text"] == str(rp)), EL, 700, label="쪽 번호 — 시스템 자리(오른쪽 맞춤)", bind="sys.page_no", align="right")
    st += done("분석 펼침면 오른쪽", f"p{rp}.png")
    # 견본 원고 한 벌 — 원본 이 펼침면에서 읽은 것(바깥 시스템이 보낼 꼴)
    rec = {"강": s_k["text"], "회차": s_r["text"], "지문제목": s_t["text"], "문장+해석": left(REF_PATH, lp)}
    rec.update(right(REF_PATH, rp))
    CONTENT.setdefault("분석 펼침면", []).append(rec)
    return st


if want(2):
    sys.path.insert(0, HERE)
    st += spread(2)

# ── 원고 넣기 — 바깥 시스템이 보내는 꼴(자리 이름 → 글 · 꾸밈 조각) ──
if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
