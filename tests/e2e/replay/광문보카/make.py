"""광문보카 01 — 「광문1_광문보카01_내지_인쇄.pdf」(160쪽, 148×210mm · 관리 vocab/xe164a0e5)를 보고 편집기로 손수 만든다.
등록 이름 「광문보카 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」 + CLAUDE.md 「교재 등록 작업표」(2026-10-19).
만드는 면 = 확인받은 면 목록 8개 그대로(구성.json · faces.json) — 파트마다 색만 다른 면은 따로 만들지 않는다(첫 견본 쪽 색).
값(자리 · 크기 · 색)은 모두 목표 PDF(상태.json ref)에서 잰다. 목표 PDF 는 예전 코드(Vivliostyle) 판이라 글자가 이름 없는 윤곽(Type3)이고
PDF 에 적힌 크기가 틀린 조각이 있다(0.6 · 0.95pt 등) — 크기는 잉크 높이를 서체 글자 높이로 나눠 잰다(real_size). 서체는 fontmatch.py 로 고른
시스템 서체(겹침 — 아래 FONT 주석), 후보 이름은 같은 책 인디자인 판(_기준_광문보카_내지(샘플).pdf)에서.

면(구성.json 번호):
  1 표지 · 2 PART 간지 · 3 PART 차례 · 7 MEMO 면 · 8 마지막 면 — 고정 그림 · 고정 글 · 원고 자리(파트 이름 등)
  4 UNIT 첫 면(펼침 2쪽) · 5 본문 왼쪽 면 · 6 본문 오른쪽 면 — 단어 항목이 흐르는 면(다음 차례)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import _color                                               # noqa: E402
import mkpage
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont
import pagecmp                                                          # noqa: E402
import pdfsvg                                                           # noqa: E402
mkpage.SPOT = {"mm": [80, 175]}                                         # A5 쪽 안 — 끌어 그리는 빈 자리 · 글 확정용 빈 곳(배재1 포켓북과 같은 판형)
mkpage.AWAY = {"mm": [140, 120]}
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
W_MM, H_MM = 148.0, 210.0
NAME = "광문보카 (편집기 제작)"
# 서체(fontmatch.py 글자마다 겹침, 2026-10-19): 파트 이름 30pt VITRO CORE 900 0.987 · PART 번호 · 차례 파트 이름 잘난체 0.973 · 0.976 ·
# 차례 UNIT Pretendard 700 0.963 · 파트 설명 · 낱말 수 Noto Sans CJK KR 500 0.825(줄) · 0.934 · COPYRIGHT Noto 500 0.831(6.6pt 작은 글)
VITRO, JAL, PRE, NOTO = "VITRO CORE OTF", "Jalnan OTF", "Pretendard", "Noto Sans CJK KR"
PINK, PINK_BG = "#d1679b", "#f7dce5"

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
    """원본 글 조각 — 첫 글자 기준점(x, base) · 끝 글자 오른쪽 · 크기 · 색 · 글 · 잉크 상자(pt)"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                if ch:
                    out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                                "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "text": "".join(c["c"] for c in sp["chars"]).strip(),
                                "bbox": [min(c["bbox"][0] for c in ch), min(c["bbox"][1] for c in ch), max(c["bbox"][2] for c in ch), max(c["bbox"][3] for c in ch)]})
    return out


def line_of(sps, base, tol=0.3):
    """기준선이 같은 조각들을 한 줄로(첫 글자 ~ 끝 글자) — 자간 넓은 글은 글자마다 조각이 끊긴다"""
    row = sorted([s for s in sps if abs(s["base"] - base) < tol], key=lambda s: s["x"])
    t = row[0]["text"]
    for a, b in zip(row, row[1:]):
        t += (" " if b["x"] - a["x1"] > 0.4 else "") + b["text"]
    bb = [min(s["bbox"][0] for s in row), min(s["bbox"][1] for s in row), max(s["bbox"][2] for s in row), max(s["bbox"][3] for s in row)]
    return dict(row[0], x1=row[-1]["x1"], text=t, bbox=bb)


def _ink_rows(L, light):
    bg = int(np.median(np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]])))
    a = L > bg + (255 - bg) // 2 if light else L < bg - max(bg - int(L.min()), 1) // 2
    return np.where(a.any(axis=1))[0]


def real_size(pno, s, family, weight):
    """글 크기 pt — 원본 잉크 높이(1200dpi) ÷ 그 서체로 같은 글을 그린 잉크 높이(em 비율). PDF 에 적힌 크기를 믿지 않는다(Type3)"""
    p = REF[pno - 1]
    pix = p.get_pixmap(clip=pymupdf.Rect(*s["bbox"]), dpi=1200)
    L = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")).astype(int)
    c = int(s["color"][1:], 16)
    ys = _ink_rows(L, (c >> 16) + (c >> 8 & 255) + (c & 255) > 600)
    ref_mm = (ys.max() - ys.min() + 1) / 1200 * 25.4
    px = 1000
    f = ImageFont.truetype(font_file(family, weight), px)
    img = Image.new("L", (int(px * (len(s["text"]) + 2)), px * 2), 255)
    ImageDraw.Draw(img).text((px // 2, px // 4), s["text"].replace(" ", ""), font=f, fill=0)
    ys2 = np.where((np.asarray(img) < 128).any(axis=1))[0]
    return round(ref_mm / ((ys2.max() - ys2.min() + 1) / px) / MM, 2)


def pg_new(pno, label, name=None, rep=True):
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label) + [{"click": "#rail .pg.on", "wait": 1500}]
    st += [S(label, 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},
           {"pick": {"at": "#side #s-spec", "value": "a5"}, "wait": 1500}]           # 판형 A5 148×210
    if len(PAGES) == 1 and pno > 1:
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    if name:                                                             # 면 이름 (관리 지면 보기가 이 이름으로 묶는다)
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", name, 900)]
    if rep:                                                              # 원고마다 — 원고 덩어리 하나에 이 면(맨 앞 · 맨 뒤 고정 면은 한 번만)
        st += [{"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1200}]
    return st


_DONE = set()


def _brand_open():
    return [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1500}]


def need_pstyle(name, props, label=None):
    if ("p", name) in _DONE:
        return []
    _DONE.add(("p", name))
    st = [S(label or f"단락 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#st-new", "wait": 1300}]
    return st + pstyle_fields(name, props) + [{"click": "#sheet-x", "wait": 1200}]


def need_cstyle(name, props, label=None):
    if ("c", name) in _DONE:
        return []
    _DONE.add(("c", name))
    st = [S(label or f"문자 스타일 「{name}」", 1200)] + _brand_open() + [{"answer": name}, {"click": "#cs-new", "wait": 1300}]
    return st + cstyle_fields(name, props) + [{"click": "#sheet-x", "wait": 1200}]


def track_of(s, font, weight, size):
    """자간 ‰ — 원본 첫 ~ 끝 글자 거리와 서체 글자 폭의 차이(글자 사이 수로 나눔)"""
    t = s["text"]
    if len(t) < 2:
        return 0
    return round(((s["x1"] - s["x"]) - chrome_extent(font, weight, size, t) - face(font, weight)[2](t[-1]) * size * MM) / (len(t) - 1) / (size * MM) * 1000)


def T(s, font, weight, size=None, label=None, slot_name=None, temp=None, align=None, w=None, leading=None, h=None, bind=None, measure=True, alpha=None):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서. size 를 안 주면 원본 조각 크기"""
    size = size or s["size"]
    track = track_of(s, font, weight, size)
    bw = w or round((s["x1"] - s["x"]) * 1.3 + size * 0.4, 1)
    bh = h or round((leading or size * 1.45) * MM * 1.03, 1)
    top = top_of(s["base"], size, font, weight, leading)
    x = s["x"]
    if align == "right":                                                 # 크롬은 끝 글자 뒤에도 자간을 붙인다 — 그만큼 오른쪽으로
        x = s["x1"] + track / 1000 * size * MM - bw
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - size * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
         "h": round(size * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.6, "search": 0.6, "text": s["text"], "size": size}
    if slot_name:
        m["원고"] = True
    if alpha:                                                            # 불투명도 글 — 바탕과 섞여 보이는 색으로 잰다
        m["see"] = blend(s["color"], PINK_BG, alpha)
    if measure:
        E(m)
    st = text(round(x, 2), round(top, 2), bw, bh, temp if slot_name else s["text"], size, s["color"], label=label, font=font, weight=weight,
              track=track or None, align=align, leading=leading, bind=bind, alpha=alpha)
    if slot_name:
        st += slot(slot_name)
    return st


def blend(fg, bg, alpha):
    """불투명도 alpha% 글이 바탕 위에 보이는 색 — 잴 색"""
    f, b = int(fg[1:], 16), int(bg[1:], 16)
    return "#" + "".join("%02x" % round(((f >> k) & 255) * alpha / 100 + ((b >> k) & 255) * (1 - alpha / 100)) for k in (16, 8, 0))


def union(es):
    x0, y0 = min(e["x"] for e in es), min(e["y"] for e in es)
    return x0, y0, max(e["x"] + e["w"] for e in es) - x0, max(e["y"] + e["h"] for e in es) - y0


def Ebox(x, y, w, h, color, pad=0.6, ctol=30):
    c = clip({"x": x, "y": y, "w": w, "h": h})
    E({"id": f"e{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": color, "see": color, "pad": pad, "ctol": ctol})


def rbox(x, y, w, h, fill, label=None, measure=True):
    st = box(x, y, w, h, fill, label=label)
    if measure:
        Ebox(x, y, w, h, fill)
    return st


def find(el, k, x, y, tol=0.6, **kw):
    c = [e for e in el if e["k"] == k and abs(e["x"] - x) < tol and abs(e["y"] - y) < tol and all(e.get(a) == v for a, v in kw.items())]
    if not c:
        raise RuntimeError(f"원본 요소 없음 {k} {x},{y} {kw}")
    return c[0]


def art(pno, x, y, w, h, name, color, label):
    """원본 그림(로고 · 모눈)을 그림 파일(SVG — 원본 도형 그대로)로 꺼내 그 자리에 — 디자이너가 원본에서 로고를 내보내 올리는 것과 같다(pdfsvg.py)"""
    path = os.path.join(WORK, f"{name}.svg")
    pdfsvg.export(REF_PATH, pno, x, y, w, h, path)
    if color:
        Ebox(x, y, w, h, color)
    return image(x, y, w, h, path, label=label)


def pic(pno, x, y, w, h, name, label):
    """원본 그림 조각을 그 자리 그대로(600dpi PNG) — 이름 없는 서체로 찍힌 로고 글처럼 다른 길로 못 만드는 것"""
    path = os.path.join(WORK, f"{name}.png")
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    pix = p.get_pixmap(clip=pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM), dpi=600)
    pix.save(path)
    ir = pymupdf.IRect(pix.x, pix.y, pix.x + pix.width, pix.y + pix.height)   # 600dpi 화소 칸에 맞춰 바깥으로 넓어진 실제 자리 — 그 자리 · 크기로 놓아야 0.25mm 밀리지 않는다
    x, y = round(ir.x0 * 72 / 600 * MM - t.x0 * MM, 3), round(ir.y0 * 72 / 600 * MM - t.y0 * MM, 3)
    w, h = round(pix.width / 600 * 25.4, 3), round(pix.height / 600 * 25.4, 3)
    E({"id": f"i{len(ELEMS[len(PAGES)])}", "x": x, "y": y, "w": w, "h": h, "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    return image(x, y, w, h, path, label=label)


st = open_doc(NAME)
st += expect_pages(1)

# ── 1 표지 (1쪽) — 분홍 바탕 · 하트 로고(도형) · GWANGMUN VOCA(로고 글) ──
if want(1):
    st += pg_new(1, "① 표지 — 원본 1쪽", name="표지", rep=False)
    el = els(1)
    bg = find(el, "rect", -3, -3)
    st += [S("바탕 — 재단 여백까지", 1100)] + rbox(bg["x"], bg["y"], bg["w"], bg["h"], bg["fill"])
    hx, hy, hw, hh = union([e for e in el if e["k"] == "path" and e.get("fill") == "#ffffff"])
    st += art(1, round(hx - 0.2, 2), round(hy - 0.2, 2), round(hw + 0.4, 2), round(hh + 0.4, 2), "표지_하트", None, "하트 로고 — 원본 도형 그림(표지_하트.svg)")
    Ebox(hx, hy, hw, hh, "#ffffff")
    # GWANGMUN VOCA — 원본 서체(인디자인 판 TT Supersize)가 시스템 서체에 없고 가장 닮은 VITRO CORE 도 글자마다 겹침 0.80(0.9 미만) → 로고 글 그대로 그림
    lg = find(el, "text", 28.95, 131.89)
    st += pic(1, 28.6, 131.6, 93.8, 11.2, "표지_로고글", "GWANGMUN VOCA — 원본 로고 글 그림(서체 없음)")
    ELEMS[len(PAGES)][-1].update(x=lg["x"], y=lg["y"], w=lg["w"], h=lg["h"], color="#ffffff", see="#ffffff")   # 잴 데 = 로고 글(그림 칸이 아니라)
    st += done("표지", "p1.png")

# ── 2 PART 간지 (2쪽) — 파트 번호 · 파트 이름 · 파트 설명은 원고(파트마다 바뀜), 하트 · 연구소 로고는 고정 ──
if want(2):
    st += pg_new(2, "② PART 간지 — 원본 2쪽", name="PART 간지")
    el, sp = els(2), spans(2)
    bg = find(el, "rect", -3, -3)
    st += [S("바탕", 1100)] + rbox(bg["x"], bg["y"], bg["w"], bg["h"], bg["fill"])
    hx, hy, hw, hh = union([e for e in el if e["k"] == "path" and e.get("fill") == "#ffffff"])
    st += art(2, round(hx - 0.2, 2), round(hy - 0.2, 2), round(hw + 0.4, 2), round(hh + 0.4, 2), "간지_하트", None, "하트 로고 — 원본 도형 그림")
    Ebox(hx, hy, hw, hh, "#ffffff")
    st += art(2, 17.9, 178.7, 28.4, 5.4, "간지_연구소", None, "연구소 로고 — 원본 도형 그림")
    Ebox(18.0, 178.8, 27.9, 5.2, PINK, pad=0.3)
    s_no = line_of(sp, next(s["base"] for s in sp if s["text"].startswith("P")))
    s_no = dict(s_no, text="PART 1")
    st += T(s_no, JAL, 400, size=real_size(2, s_no, JAL, 400), label="파트 번호 — 원고 자리 「파트번호」 (잘난체 · 불투명 75%)",
            slot_name="파트번호", temp="PART 0", alpha=75)
    s_nm = line_of(sp, 54.38)
    st += T(s_nm, VITRO, 900, size=real_size(2, s_nm, VITRO, 900), label="파트 이름 — 원고 자리 「파트」 (VITRO CORE)", slot_name="파트", temp="파트 이름", w=110)
    s_ds = line_of(sp, 64.24)
    st += T(s_ds, NOTO, 500, size=real_size(2, dict(s_ds, text="어휘끝"), NOTO, 500), label="파트 설명 — 원고 자리 「파트설명」 (불투명 60%)",
            slot_name="파트설명", temp="파트 설명 Unit 00~00", w=110, alpha=60)
    CONTENT.setdefault("PART 간지", []).append({"파트번호": "PART 1", "파트": "어휘끝", "파트설명": s_ds["text"]})
    st += done("PART 간지", "p2.png")

# ── 3 PART 차례 (3쪽) — 파트 이름 · 단원 줄(단원 · 낱말 수, 줄 아래 선) · 합계 ──
if want(3):
    st += pg_new(3, "③ PART 차례 — 원본 3쪽", name="PART 차례")
    el, sp = els(3), spans(3)
    bg = find(el, "rect", -3, -3)
    st += [S("바탕", 1100)] + rbox(bg["x"], bg["y"], bg["w"], bg["h"], bg["fill"])
    s_nm = line_of(sp, 44.62)
    st += T(s_nm, JAL, 400, size=real_size(3, s_nm, JAL, 400), label="파트 이름 — 원고 자리 「파트」 (잘난체)", slot_name="파트", temp="파트", w=40)
    rows = sorted({round(s["base"], 2) for s in sp if s["text"] == "U"})
    units = [line_of([s for s in sp if s["x"] < 100], b) for b in rows]
    counts = [next(s for s in sp if abs(s["base"] - b) < 0.3 and s["x"] > 100) for b in rows]
    u0 = dict(units[0], text=units[0]["text"].replace(" ", "").replace("UNIT", "UNIT "))
    US = real_size(3, dict(next(s for s in sp if s["text"] == "NIT")), PRE, 700)
    CS_ = real_size(3, counts[0], NOTO, 500)
    lead = round(sorted(b - a for a, b in zip(rows, rows[1:]))[len(rows) // 2 - 1], 3)
    LEAD = round(lead / MM, 2)
    rules = sorted([e for e in el if e["k"] == "rect" and abs(e["w"] - 101.4) < 0.2 and e["h"] < 0.3], key=lambda e: e["y"])
    r0 = rules[0]
    off = round(r0["y"] - rows[0], 2)                                    # 끝 줄 기준선에서 경계선 위 끝까지
    x_r = counts[0]["x1"]                                                # 낱말 수 오른쪽 끝(오른쪽 탭)
    st += need_cstyle("차례 단원", {"font": PRE, "weight": 700, "size": US, "color": "#000000", "track": track_of(u0, PRE, 700, US)})
    st += need_pstyle("차례 줄", {"font": NOTO, "weight": 500, "size": CS_, "leading": LEAD, "color": counts[0]["color"],
                                "tabs": [{"at": round(x_r - u0["x"], 2), "align": "right"}],
                                "rule_below": {"w": round(r0["h"] / MM, 3), "color": r0["fill"], "offset": off}})
    for e in rules:
        Ebox(e["x"], e["y"], e["w"], e["h"], e["fill"], pad=0.15)
    body = units + counts
    for s in body:
        E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - 2.6, 2), "w": round(s["x1"] - s["x"], 2), "h": 2.8,
           "color": s["color"], "see": s["color"], "ctol": 30, "pad": 0.6, "search": 0.6, "text": s["text"], "size": US, "원고": True})
    top = round(top_of(rows[0], CS_, NOTO, 500, LEAD), 2)
    st += text(round(u0["x"], 2), top, round(x_r - u0["x"] + 0.5, 2), round(rows[-1] - top + 4, 1), "UNIT 00\t00", CS_, counts[0]["color"],
               label="단원 줄 — 데이터 필드 「단원+낱말수」 (줄마다 단원 · 오른쪽 탭 · 낱말 수, 줄 아래 경계선)", font=NOTO, weight=500, leading=LEAD, auto="")
    st += slot("단원+낱말수", label="데이터 필드 — 단원+낱말수(레코드만큼 줄)")
    st += [slot_style("단원", "차례 줄"), slot_style("낱말수", "차례 줄")]
    st += slot_inline("단원", cs="차례 단원", sep="\t")
    s_sum = line_of(sp, 136.96)
    st += T(s_sum, NOTO, 500, size=CS_, label="합계 — 원고 자리 「합계」 (오른쪽 맞춤)", slot_name="합계", temp="모두 000개", align="right", w=30)
    CONTENT.setdefault("PART 차례", []).append({"파트": "어휘끝",
                                              "단원+낱말수": [{"단원": u["text"].replace(" ", "").replace("UNIT", "UNIT "), "낱말수": c["text"]} for u, c in zip(units, counts)],
                                              "합계": s_sum["text"]})
    st += done("PART 차례", "p3.png")

# ── 7 MEMO 면 (17쪽) — 모눈 · 위아래 띠 · MEMO 탭 그림 ──
if want(7):
    st += pg_new(17, "⑦ MEMO 면 — 원본 17쪽", name="MEMO 면")
    el = els(17)
    st += art(17, -3.0, -3.0, 154.0, 216.0, "메모_모눈", None, "모눈 — 원본 도형 그림(가는 선 2.79mm 칸)")
    hl = min((e for e in el if e["k"] == "line" and e["h"] < 0.01), key=lambda e: abs(e["y"] - 100))
    vl = min((e for e in el if e["k"] == "line" and e["w"] < 0.01), key=lambda e: abs(e["x"] - 70))
    Ebox(20.0, hl["y"] - 0.06, 100.0, 0.12, hl["stroke"], pad=0.15, ctol=20)          # 띠에 덮인 선(쪽 위 끝)은 안 본다
    Ebox(vl["x"] - 0.06, 30.0, 0.12, 150.0, vl["stroke"], pad=0.15, ctol=20)
    for e in sorted([e for e in el if e["k"] == "rect"], key=lambda e: (e["y"], -e["h"])):
        st += rbox(e["x"], e["y"], e["w"], e["h"], e["fill"], label=f"띠 {e['fill']}")
    im = next(e for e in el if e["k"] == "image")
    info = REF[16].get_image_info(xrefs=True)[0]
    path = ref_image(REF, info["xref"], os.path.join(WORK, "메모_탭.png"))
    E({"id": "memo_tab", "x": round(im["x"], 2), "y": round(im["y"], 2), "w": round(min(im["w"], W_MM - im["x"]), 2), "h": round(im["h"], 2),
       "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    st += image(round(im["x"], 2), round(im["y"], 2), round(im["w"], 2), round(im["h"], 2), path, label="MEMO 탭 — 원본 그림")
    st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]
    st += done("MEMO 면", "p17.png")

# ── 8 마지막 면 (160쪽) — 분홍 바탕 · 연구소 로고 · COPYRIGHT ──
if want(8):
    st += pg_new(160, "⑧ 마지막 면 — 원본 160쪽", name="마지막 면", rep=False)
    el, sp = els(160), spans(160)
    bg = find(el, "rect", -3, -3)
    st += [S("바탕", 1100)] + rbox(bg["x"], bg["y"], bg["w"], bg["h"], bg["fill"])
    st += art(160, 14.9, 183.9, 28.5, 5.4, "끝_연구소", None, "연구소 로고 — 원본 도형 그림")
    Ebox(15.0, 184.0, 27.9, 5.2, PINK, pad=0.3)
    s_c = line_of(sp, 194.71)
    st += T(s_c, NOTO, 500, size=real_size(160, dict(s_c, text="COPYRIGHT"), NOTO, 500), label="COPYRIGHT — 고정 글", w=50)
    st += done("마지막 면", "p160.png")

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
