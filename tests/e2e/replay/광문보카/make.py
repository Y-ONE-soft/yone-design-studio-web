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
    """rep — True: 원고마다(레코드 하나에 한 장) · "none": 찍지 않음(넘침을 이어 받는 페이지로만) · False: 한 번만"""
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
        st += [{"pick": {"at": "#side #s-rep", "value": "none" if rep == "none" else "each_set"}, "wait": 1200}]
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


def pic(pno, x, y, w, h, name, label, alone=False):
    """원본 그림 조각을 그 자리 그대로(600dpi PNG) — 이름 없는 서체로 찍힌 로고 글처럼 다른 길로 못 만드는 것"""
    path = os.path.join(WORK, f"{name}.png")
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    r = pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM)
    if alone:                                                            # 글만(뒤 모눈 · 띠 없이, 바탕 투명) — 사본 쪽에서 그 자리 도형을 지우고 그린다
        tmp = pymupdf.open()
        tmp.insert_pdf(REF, from_page=pno - 1, to_page=pno - 1)
        p = tmp[0]
        p.add_redact_annot(r)
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED, text=pymupdf.PDF_REDACT_TEXT_NONE)
    pix = p.get_pixmap(clip=r, dpi=600, alpha=alone)
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

# ── 4 UNIT 첫 면(4 · 5쪽 펼침) · 5 본문 왼쪽(6쪽) · 6 본문 오른쪽(7쪽) — 단어 항목이 흐르는 면 ──
# 단어 항목 = 인디자인 표 한 행(레코드 하나 = 한 행, 왼쪽 칸 · 오른쪽 칸 — 원고 {"칸": [왼쪽, 오른쪽]}). 표는 글 잇기 상자를 넘어 행 단위로 이어지고
# (4쪽 → 5쪽 → 넘치면 「본문 왼쪽」 · 「본문 오른쪽」 덧쪽이 번갈아 — 인디자인 스마트 텍스트 리플로우), 항목 사이 선 = 행 획, 첫 · 끝 선 = 표 테두리.
# 값은 원본 4~16쪽 항목들에서 잰 가장 흔한 값(entries.py). 알려진 차이(템플릿 값으로 하나로 정함): 원본은 뜻이 두 줄 · 둘이면 뜻 묶음을 위로 올려
# 예문 자리를 지킨다(가운데 맞춤 칸) — 인디자인 단락은 위에서 아래로 쌓이니 예문이 뜻 한 줄만큼 내려간다.
sys.path.insert(0, HERE)
from entries import entries as read_entries                             # noqa: E402
GM, HCR = "Gmarket Sans", "HCR Dotum"
BIND = "번호+표제어+발음+파생어+파생품사+파생뜻+품사+뜻+예문+해석"
X_L, X_R, TW, BOT = 14.99, 17.97, 114.99, 192.0                         # 표 왼쪽(왼쪽 · 오른쪽 면) · 폭 · 프레임 아래 끝(원본 4~73쪽 끝 항목 선 가장 아래 191.83 + 0.17)
C2X = 59.27                                                              # 4쪽 오른쪽 칸 왼쪽(예문 첫 글자) — 왼쪽 칸 폭 = C2X - X_L
RING_C, BOX_C, ORANGE = "#4d4d4d", "#e9bacb", "#f68b62"
UNIT = {}                                                                # 단어 항목 템플릿 값(한 번 재고 면마다 쓴다)


def lp(fam, wt, size, lead):
    """CSS 줄 상자 — 기준선 위 · 아래 몫(mm)"""
    asc, desc, _ = face(fam, wt)
    s, L = size * MM, lead * MM
    a = (L - (asc + desc) * s) / 2 + asc * s
    return a, L - a


def unit_values():
    """단어 항목 간격 · 크기 · 서체 — 원본 4~16쪽(UNIT 15) 항목들에서 가장 흔한 값"""
    import collections
    if UNIT:
        return UNIT
    G, LD = collections.defaultdict(list), collections.defaultdict(list)
    for pno in range(4, 17):
        m = []
        read_entries(REF_PATH, pno, m)
        for e in m:
            for col in ("c1", "c2"):
                fs = e[col]
                G[(col, "top")].append(round(fs[0][1] - e["rule"], 2))
                for a, b in zip(fs, fs[1:]):
                    G[(a[0], b[0])].append(round(b[1] - a[2], 2))
                for f in fs:
                    if f[2] > f[1]:
                        LD[f[0]].append(round(f[2] - f[1], 2))
            who = "c2" if e["c2"][-1][2] >= e["c1"][-1][2] else "c1"
            G[(who, "bottom")].append(round(e["next"] - max(e["c1"][-1][2], e["c2"][-1][2]), 2))
    mode = lambda v: collections.Counter(v).most_common(1)[0][0]
    g = {k: mode(v) for k, v in G.items()}
    ld = {k: min(x for x in v if x > 1) for k, v in LD.items()}           # 두 줄 단락의 줄 사이 = 행간
    m4 = []
    read_entries(REF_PATH, 4, m4)
    sp = spans(4)
    e0, e1, e2 = m4[0], m4[1], m4[2]
    at = lambda b, x0, x1, col=None: line_of([s for s in sp if x0 <= s["x"] < x1 and s["color"] != RING_C and (col is None or s["color"] == col)], b)
    s_no = at(e0["c1"][0][1], 0, 59)
    s_hw = at(e0["c1"][1][1], 0, 59)
    s_ex = at(e2["c2"][1][2], 59, 140, "#000000")                          # 「and pain.」 — 검정 한 줄(주황 강조 없는 줄)
    s_tr = at(e2["c2"][2][1], 59, 140, "#000000")
    mn = [s for s in sp if abs(s["base"] - e0["c2"][0][1]) < 0.2 and s["color"] == "#000000" and s["x"] > C2X + 1]
    pos = [s for s in sp if s["color"] == RING_C]
    pr = [s for s in sp if abs(s["base"] - e0["c1"][2][1]) < 0.2]
    rings = [e for e in els(4) if e["k"] == "path" and e.get("stroke") == RING_C]
    r_main = min((r for r in rings if r["x"] > C2X - 1), key=lambda r: r["y"])          # 첫 항목 뜻 둥근 네모
    r_der = min((r for r in rings if r["x"] < C2X - 1), key=lambda r: r["y"])           # 첫 파생어 둥근 네모
    p_main = min((s for s in pos if abs(s["x"] - r_main["x"]) < 1.5), key=lambda s: s["base"])
    t4 = REF[3].trimbox
    dm = next(d for d in REF[3].get_drawings() if d.get("color") and abs((d["rect"].x0 - t4.x0) * MM - r_main["x"]) < 0.02
              and abs((d["rect"].y0 - t4.y0) * MM - r_main["y"]) < 0.02)
    ring_r = round((dm["items"][0][2].y - dm["rect"].y0) * MM, 3)        # 둥근 네모 — 첫 세로 변 위 끝 ~ 위 가장자리 = 모퉁이 반지름(획 가운데)
    p_der = min((s for s in pos if abs(s["x"] - r_der["x"]) < 1.5), key=lambda s: s["base"])
    w_end = max(s["x1"] for s in sp if abs(s["base"] - e1["c1"][3][1]) < 0.2 and s["x"] < r_der["x"])   # 파생어 낱말 끝
    s_dv = line_of([s for s in sp if abs(s["base"] - e1["c1"][3][1]) < 0.2 and s["x"] < r_der["x"]], e1["c1"][3][1])   # 파생어 낱말만(둥근 네모 앞)
    boxes = sorted([e for e in els(4) if e["k"] == "path" and e.get("stroke") == BOX_C and e["y"] < e0["c1"][0][1]], key=lambda e: e["x"])
    q = lambda x: float(round(x * 2) / 2) if abs(x - round(x * 2) / 2) < 0.06 else float(x)    # 잰 크기가 0.5pt 눈금에 붙으면 그 값(6.02 → 6)
    rs = lambda *a: q(real_size(*a))
    v = dict(g=g, ld=ld,
             no=(PRE, 700, rs(4, s_no, PRE, 700), s_no["color"]),
             hw=(PRE, 700, rs(4, s_hw, PRE, 700), "#000000"),
             pr=(HCR, 700, pr[0]["size"], pr[0]["color"]),
             dv=(PRE, 500, rs(4, s_dv, PRE, 500), "#000000"),
             mn=(NOTO, 500, collections.Counter(s["size"] for s in mn).most_common(1)[0][0], "#000000"),
             pos=(PRE, 500, pos[0]["size"], RING_C),
             ex=(PRE, 500, rs(4, s_ex, PRE, 500), "#000000"),
             tr=(PRE, 500, rs(4, s_tr, PRE, 500), "#000000"),
             ring=r_main, ring_r=ring_r, boxes=boxes, mn_x=min(s["x"] for s in mn) - C2X, rule=e0["rule"],
             pos_dy=round(e0["c2"][0][1] - p_main["base"], 2), dpos_dy=round(e1["c1"][3][1] - p_der["base"], 2),
             dv_gap=(round(r_der["x"] - 0.07 - w_end, 2), round(next(s["x"] for s in sp if abs(s["base"] - e1["c1"][3][1]) < 0.2 and s["x"] > r_der["x"] + 2)
                                                                     - (r_der["x"] + r_der["w"] + 0.07), 2)))
    UNIT.update(v)
    return UNIT


def unit_styles():
    """단락 스타일 · 문자 스타일 — 단어 항목 칸 안 필드마다(인디자인 데이터 병합 필드 단락)"""
    v = unit_values()
    g, ld = v["g"], v["ld"]
    L = {k: round(v[k][2] * 1.2, 2) for k in ("no", "hw", "pr", "mn")}   # 한 줄 단락 — 행간 120%(자동)
    L["dv"], L["ex"], L["tr"] = round(ld["파생뜻"] / MM, 2), round(ld["예문"] / MM, 2), round(ld.get("해석", ld["예문"]) / MM, 2)
    P = {k: lp(v[k][0], v[k][1], v[k][2], L[k]) for k in L}                 # (위 몫, 아래 몫)
    sp = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    pst = lambda k, **o: dict({"font": v[k][0], "weight": v[k][1], "size": v[k][2], "leading": L[k], "color": v[k][3]}, **o)
    st = need_cstyle("품사", {"font": PRE, "weight": 500, "size": v["pos"][2], "color": RING_C}, "문자 스타일 「품사」 — 둥근 네모 안 글자")
    st += need_cstyle("뜻 번호", {"color": PINK}, "문자 스타일 「뜻 번호」 — 뜻의 ①② 분홍(단락 스타일 GREP)")
    st += need_cstyle("강조", {"color": ORANGE}, "문자 스타일 「강조」 — 예문 · 해석의 표제어 자리(원고가 준다)")
    st += need_cstyle("작은 글", {"size": 6.0}, "문자 스타일 「작은 글」 — 뜻 안 (상) · (의미 등이)")
    st += need_pstyle("단어 번호", pst("no"))
    st += need_pstyle("단어 표제어", pst("hw", space_before=sp(g[("번호", "표제어")], "no", "hw")))
    st += need_pstyle("단어 발음", pst("pr", space_before=sp(g[("표제어", "발음")], "hw", "pr")))
    st += need_pstyle("단어 파생뜻", pst("dv", space_before=sp(g[("발음", "파생뜻")], "pr", "dv"), space_same=sp(g[("파생뜻", "파생뜻")], "dv", "dv")))
    st += need_pstyle("단어 뜻", pst("mn", tabs=[{"at": round(v["mn_x"], 2)}], space_same=sp(g[("뜻", "뜻")], "mn", "mn"),
                                    space_after=sp(g[("뜻", "예문")], "mn", "ex"), grep=[("[①-⑳]", "뜻 번호")]))
    st += need_pstyle("단어 예문", pst("ex", align="justify"))
    st += need_pstyle("단어 해석", pst("tr", align="justify", space_before=sp(g[("예문", "해석")], "ex", "tr"),
                                      space_after=sp(g[("해석", "예문")], "tr", "ex")))
    top1 = round(g[("c1", "top")] - 0.17 - P["no"][0], 2)                   # 셀 인세트 위 — 행 획(0.17) 아래에서 첫 줄 위 끝까지
    top2 = round(g[("c2", "top")] - 0.17 - P["mn"][0], 2)
    bot2 = round(g[("c2", "bottom")] - P["tr"][1], 2)
    bot1 = round(g.get(("c1", "bottom"), g[("c2", "bottom")]) - P["dv"][1], 2)
    v.update(L=L, P=P, inset1=f"{top1},2,{bot1},0", inset2=f"{top2},0,{bot2},0")
    return st


PARTN = [0]                                                              # 이 대본이 만든 부품 차례 — 빈 문서에서 편집기가 p_1, p_2 … 로 붙인다


def check_part(pno=4, bx=None):
    """확인 칸 셋(둥근 네모) — 원본 도형 그림 + 같은 크기 빈 면을 묶어 부품(번호 단락의 고정 개체). → (대본, 부품 id, 왼쪽, 위)"""
    if bx is None:
        v = unit_values()
        bx = v["boxes"]
    x0, y0 = bx[0]["x"] - 0.2, bx[0]["y"] - 0.2
    w, h = round(bx[-1]["x"] + bx[-1]["w"] - x0 + 0.2, 2), round(bx[0]["h"] + 0.4, 2)
    path = os.path.join(WORK, f"확인칸{pno}.svg")
    pdfsvg.export(REF_PATH, pno, x0, y0, w, h, path)
    X0, Y0 = 60.0, 196.0
    st = [S("확인 칸 부품 — 원본에서 내보낸 그림 + 같은 크기 빈 면을 빈 자리에 그려 묶는다(번호 뒤 고정 개체)", 1300)]
    st += image(X0, Y0, w, h, path)
    st += box(X0, Y0, w, h, "#ffffff", alpha=0)
    st += [S("자석 끄기", 800), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
           S("범위로 2개를 골라 그룹 → 부품", 1000), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},   # 고른 것 위 도구 막대가 끌기 시작점을 가린다
           {"drag": {"from": {"mm": [X0 - 2, Y0 - 1.5]}, "to": {"mm": [X0 + w + 2, Y0 + h + 1.5]}}, "wait": 900},
           {"js": "(() => { if (sels.size !== 2) throw new Error('고른 것 ' + sels.size + ' (2 이어야)'); return '고른 것 2'; })()"},
           {"click": "#side #s-group", "wait": 1500},
           {"until": "LIB.parts.length && LIB.parts[LIB.parts.length - 1].atoms.length === 2", "wait": 300},
           {"js": "(() => { window.__part = LIB.parts[LIB.parts.length - 1].id; return '부품 ' + window.__part; })()"},
           S("지면의 그룹은 지운다", 800), {"key": "Delete", "wait": 900},
           {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]
    PARTN[0] += 1
    return st, f"p_{PARTN[0]}", round(x0, 2), round(y0, 2)


def content_elems(pno, x0):
    """원고 요소 — 항목 사이 선 · 확인 칸 · 둥근 네모 · 글줄(원고를 따라 움직인다 — 들어갔나 · 흐름 간격만 본다)"""
    el, sp = els(pno), spans(pno)
    t = REF[pno - 1].trimbox
    for e in el:
        if e["k"] in ("rect", "path") and abs(e["w"] - TW) < 0.2 and e["h"] < 0.3:       # 항목 사이 선(실선 · 점선)
            E({"id": f"rule{len(ELEMS[len(PAGES)])}", "x": round(e["x"], 2), "y": round(e["y"], 2), "w": round(e["w"], 2), "h": round(e["h"], 2),
               "color": e["fill"], "see": e["fill"], "pad": 0.15, "ctol": 20, "원고": True})
        elif e["k"] == "path" and e.get("stroke") and e["w"] < 3 and e["h"] < 3 and 20 < e["y"] < BOT:   # 확인 칸 · 품사 둥근 네모
            E({"id": f"ring{len(ELEMS[len(PAGES)])}", "x": round(e["x"], 2), "y": round(e["y"], 2), "w": round(e["w"], 2), "h": round(e["h"], 2),
               "color": e["stroke"], "see": e["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
        elif e["k"] == "path" and e.get("fill") and 3.5 < e["h"] < 5 and e["w"] < 40 and 20 < e["y"] < BOT:   # 지문 꼬리표 둥근 음영
            E({"id": f"tag{len(ELEMS[len(PAGES)])}", "x": round(e["x"], 2), "y": round(e["y"], 2), "w": round(e["w"], 2), "h": round(e["h"], 2),
               "color": e["fill"], "see": e["fill"], "pad": 0.3, "ctol": 20, "원고": True})
    rg = [e for e in el if e["k"] == "path" and e.get("stroke") == RING_C and e["w"] < 3]
    inring = lambda s: any(r["x"] - 0.3 < s["x"] < r["x"] + r["w"] and r["y"] < s["base"] < r["y"] + r["h"] + 0.5 for r in rg)   # 품사 글자(지문 문장도 같은 색)
    body = [s for s in sp if 20 < s["base"] < BOT and not inring(s)]
    for b in sorted({round(s["base"], 1) for s in body}):
        for lo, hi in ((0, x0 + 43.5), (x0 + 43.5, 200)):
            row = [s for s in body if abs(s["base"] - b) < 0.2 and lo <= s["x"] < hi]
            if not row:
                continue
            s = line_of(row, row[0]["base"])
            bb = s["bbox"]
            E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round((bb[0] - t.x0) * MM, 2), "y": round((bb[1] - t.y0) * MM, 2), "w": round((bb[2] - bb[0]) * MM, 2),
               "h": round((bb[3] - bb[1]) * MM, 2), "color": s["color"], "see": s["color"], "ctol": 30, "pad": 0.6, "search": 0.6, "text": s["text"], "원고": True})


def bands(pno, top):
    """위 · 아래 분홍 띠 — 띠 면 + 안쪽 가는 선"""
    el = els(pno)
    rs = [e for e in el if e["k"] == "rect" and e["w"] > 150]
    st = []
    for e in sorted([e for e in rs if (e["y"] < 20) == top], key=lambda e: -e["h"]):
        st += rbox(e["x"], e["y"], e["w"], e["h"], e["fill"], label=f"{'위' if top else '아래'} 띠 {e['fill']}")
    return st


def folio(pno, right):
    sp = spans(pno)
    s = next(s for s in sp if s["base"] > 195 and s["text"] == str(pno))
    return T(s, GM, 700, size=real_size(pno, s, GM, 700), label="쪽 번호 — 시스템 자리 「쪽 번호」 (지마켓 산스)", bind="sys.page_no",
             align="right" if right else None, w=8)


def logo(pno):
    """오른쪽 면 로고 — 하트(원본 도형 그림) · 2026 배지(원본 그림) · GWANGMUN VOCA(로고 글 — 서체 없음, 그림)"""
    el = els(pno)
    hx, hy, hw, hh = union([e for e in el if e["k"] == "path" and e.get("fill") == "#c0d5e1"])
    st = art(pno, round(hx - 0.2, 2), round(hy - 0.2, 2), round(hw + 0.4, 2), round(hh + 0.4, 2), f"로고_하트{pno}", None, "로고 하트 — 원본 도형 그림")
    Ebox(hx, hy, hw, hh, "#c0d5e1", pad=0.3)
    info = REF[pno - 1].get_image_info(xrefs=True)[0]
    im = next(e for e in el if e["k"] == "image")
    path = ref_image(REF, info["xref"], os.path.join(WORK, "로고_2026.png"))
    st += image(round(im["x"], 2), round(im["y"], 2), round(im["w"], 2), round(im["h"], 2), path, label="2026 배지 — 원본 그림")
    st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]
    E({"id": f"i{len(ELEMS[len(PAGES)])}", "x": round(im["x"], 2), "y": round(im["y"], 2), "w": round(im["w"], 2), "h": round(im["h"], 2),
       "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    lg = next(e for e in el if e["k"] == "text" and e["text"].replace(" ", "").startswith("GWANGMUN"))
    st += pic(pno, round(lg["x"] - 0.3, 2), round(lg["y"] - 0.3, 2), round(lg["w"] + 0.6, 2), round(lg["h"] + 0.6, 2), f"로고글{pno}",
              "GWANGMUN VOCA — 원본 로고 글 그림(서체 없음 · 글만, 바탕 투명)", alone=True)
    ELEMS[len(PAGES)][-1].update(x=lg["x"], y=lg["y"], w=lg["w"], h=lg["h"], color="#d995b3", see="#d995b3")
    return st


def ring_steps(f, y):
    """품사 둥근 네모 — 필드 인라인 고정 텍스트 프레임(획 · 모퉁이 · 인세트 · Y 오프셋). 크기는 원본 4쪽 첫 항목 품사 테두리에서"""
    v = unit_values()
    ring, d = v["ring"], round(v["ring"]["w"] + (v["ring"].get("sw") or 0.13), 3)       # 둥근 네모 바깥 지름 = 경로 지름 + 획
    sw_pt = round((v["ring"].get("sw") or 0.13) / MM, 3)
    ins = round((d - 2 * (sw_pt * MM) - v["pos"][2] * MM) / 2, 3)          # 글자 줄 상자(1em) 둘레 인세트
    rad = round(v["ring_r"] + sw_pt * MM / 2, 3)                          # 바깥 모퉁이 = 획 가운데 반지름 + 획 반
    return ([S(f"「{f}」 — 인라인 고정 텍스트 프레임: 획 {RING_C} {sw_pt}pt · 모퉁이 {rad}mm(둥근 네모) · 인세트 {ins}mm", 900)]
                        + color_p(f"slot_fmt.{f}.frame.stroke.color", RING_C) + [P_(f"slot_fmt.{f}.frame.stroke.w", sw_pt, 600),
                        P_(f"slot_fmt.{f}.frame.r", rad, 600), P_(f"slot_fmt.{f}.frame.inset", ins, 600), P_(f"slot_fmt.{f}.frame.y", y, 600)])


def story(x, top, head):
    """단어 항목 표 프레임 — 첫 프레임: 데이터 필드 · 필드마다 단락 스타일 · 같은 단락 필드 · 고정 개체 · 표(2열 · 열 너비 · 행 획 · 표 테두리 ·
    열마다 셀 인세트) · 새 스레드. 이어지는 프레임: 같은 스레드(빈 그릇)"""
    v = unit_values()
    h = round(BOT - top, 2)
    st = text(x, top, TW, h, "001 표제어 — 단어 항목이 표 행으로 흘러 들어온다" if head else "이어 받는 프레임", 8, "#000000", font=PRE, weight=500,
              label="단어 항목 표 프레임 — 한 스레드" if head else "이어 받는 표 프레임 — 같은 스레드", auto="")
    st += [F('#side input[data-it="y"]', top, 550), F('#side input[data-a="h"]', h, 550)]      # 표 — 프레임 위 끝 = 첫 항목 선(첫 번째 기준선 오프셋은 표에 안 쓴다)
    if not head:
        return st + [S("텍스트 스레드 — 같은 스토리를 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": "이야기1"}, "wait": 900}]
    st += slot(BIND, label="데이터 필드 — " + BIND + " (레코드 하나 = 표 한 행, 칸마다 필드)")
    for f, sty in (("번호", "단어 번호"), ("표제어", "단어 표제어"), ("발음", "단어 발음"), ("파생뜻", "단어 파생뜻"), ("뜻", "단어 뜻"),
                   ("예문", "단어 예문"), ("해석", "단어 해석")):
        st.append(slot_style(f, sty))
    rw = round(0.17 / MM, 3)
    two = ring_steps
    st += slot_inline("품사", cs="품사", sep="\t") + two("품사", v["pos_dy"])
    em = v["dv"][2] * MM
    near = lambda gap: min(((" ", 1.0), (" ", 0.5), (" ", space_em(PRE, 500)), (" ", 0.125), (" ", 1 / 24)), key=lambda c: abs(c[1] * em - gap))[0]
    st += slot_inline("파생어", sep=near(v["dv_gap"][0])) + slot_inline("파생품사", cs="품사", sep=near(v["dv_gap"][1])) + two("파생품사", v["dpos_dy"])
    st += [S("번호 뒤 고정 개체 — 확인 칸(사용자 정의 위치: X 텍스트 프레임 가장자리 · Y 기준선)", 900)]
    st += slot_anchor("번호", v["part"], pos="custom", at="end", xref="frame", yref="baseline",
                      x=round(v["part_x"] - X_L, 2), y=round(v["part_y"] - (v["rule"] + v["g"][("c1", "top")]), 2))
    st += [S(f"표 — 2열 · 열 너비 {round(C2X - X_L, 2)}mm · 행 획 {rw}pt {RULE} · 표 테두리 위 · 아래 · 열마다 셀 인세트", 1300),
           F('#side input[data-a="table.cols"]', 2, 900), P_("table.stroke.row_w", rw, 700)] + color_p("table.stroke.color", RULE) + [
           F('#side input[data-a="table.col_w"]', round(C2X - X_L, 2), 700), P_("table.edge.w", rw, 700)] + color_p("table.edge.color", RULE) + [
           F('#side input[data-a="table.col_inset"]', v["inset1"] + " ; " + v["inset2"], 800)]
    st += [S("텍스트 스레드 — 새 스토리(넘친 행은 다음 프레임 · 페이지로)", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    return st


def page_cont(i, target):
    """i 번째 페이지(0부터)로 가서 「넘치면 이어 갈 면」"""
    return [S(f"넘치면 더할 페이지 — 「{target}」", 1000), {"click": f'#rail .pg[data-i="{i}"]', "wait": 1500},
            {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-cont", "text": target}, "wait": 900}]


RULE = "#eac7d5"
if want(4) or want(5) or want(6):
    v = unit_values()
    i4 = len(PAGES)
    st += pg_new(4, "④ UNIT 첫 면 — 원본 4쪽 (펼침면 왼쪽)", name="UNIT 첫 면")
    st += [S("펼침면 상위 페이지 — 4 · 5쪽이 한 레코드(UNIT 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    s_cp, pid, px, py = check_part()
    v.update(part=pid, part_x=px, part_y=py)
    st += unit_styles() + s_cp
    el, sp = els(4), spans(4)
    st += art(4, -3.0, -3.0, 154.0, 22.6, "유닛_머리", None, "머리 — 모눈 띠 · 노란 반원(원본 도형 그림)")
    circ = next(e for e in el if e.get("fill") == "#f5e19e")
    Ebox(circ["x"], circ["y"], circ["w"], circ["h"], "#f5e19e")
    Ebox(70.0, 19.48, 75.0, 0.12, "#e4c0cd", pad=0.15, ctol=20)
    s_p = line_of(sp, next(s["base"] for s in sp if s["base"] < 6))
    st += T(s_p, JAL, 400, size=real_size(4, s_p, JAL, 400), label="파트 — 원고 자리 「파트」 (잘난체)", slot_name="파트", temp="파트", w=20)
    s_u = line_of(sp, next(s["base"] for s in sp if 8 < s["base"] < 11))
    st += T(s_u, JAL, 400, size=real_size(4, s_u, JAL, 400), label="단원 이름 — 원고 자리 「단원이름」 (잘난체 — 파트마다 UNIT · LESSON · 2024년)",
            slot_name="단원이름", temp="UNIT", w=20)
    s_n = line_of(sp, next(s["base"] for s in sp if 13 < s["base"] < 16))
    st += T(s_n, VITRO, 900, size=real_size(4, s_n, VITRO, 900), label="단원 번호 — 원고 자리 「단원번호」 (VITRO CORE)", slot_name="단원번호", temp="00", w=25)
    st += bands(4, False) + story(X_L, 25.08, True) + folio(4, False)
    content_elems(4, X_L)
    st += done("UNIT 첫 면", "p4.png")

    st += pg_new(5, "④ UNIT 첫 면 — 원본 5쪽 (펼침면 오른쪽)", name="UNIT 첫 면 오른쪽")
    st += art(5, -3.0, -3.0, 154.0, 22.6, "유닛_머리5", None, "머리 — 모눈 띠(원본 도형 그림)")
    Ebox(5.0, 19.48, 90.0, 0.12, "#e4c0cd", pad=0.15, ctol=20)
    st += logo(5) + bands(5, False) + story(X_R, 25.08, False) + folio(5, True)
    content_elems(5, X_R)
    st += done("UNIT 첫 면 오른쪽", "p5.png")

    i6 = len(PAGES)
    st += pg_new(6, "⑤ 본문 왼쪽 — 원본 6쪽 (넘친 행을 이어 받는 페이지)", name="본문 왼쪽", rep="none")
    el, sp = els(6), spans(6)
    st += bands(6, True)
    tab = next(e for e in el if e.get("fill") == "#f3da89")
    st += art(6, round(tab["x"] - 0.1, 2), round(tab["y"] - 0.1, 2), round(tab["w"] + 0.2, 2), round(tab["h"] + 0.2, 2), "탭", None, "단원 탭 — 원본 도형 그림")
    Ebox(tab["x"], 3.74, tab["w"], tab["y"] + tab["h"] - 3.74, "#f3da89")
    row = sorted([s for s in sp if s["base"] < 15], key=lambda s: s["x"])
    s_t = line_of(row, row[0]["base"])
    s_w = next(s for s in row if s["text"].strip().startswith("1"))          # 「15」 첫 글자
    s_a = [s for s in row if s["x"] < s_w["x"]]
    TS = real_size(6, dict(s_t, text=s_t["text"].replace(" ", "")), JAL, 400)
    gap = s_w["x"] - max(s["x1"] for s in s_a)
    em = TS * MM
    sep = min(((" ", 1.0), (" ", 0.5), (" ", space_em(JAL, 400)), (" ", 0.125)), key=lambda c: abs(c[1] * em - gap))[0]
    st += T(dict(s_t, text="어휘끝 15"), JAL, 400, size=TS, label="단원 탭 글 — 원고 자리 「파트+단원번호」 · 러닝 헤드(넘친 페이지마다 이 UNIT 값)",
            bind=None, w=26)
    ELEMS[len(PAGES)][-1]["원고"] = True
    st += slot("파트+단원번호") + slot_inline("파트", sep=sep)
    st += [S("러닝 헤드 — 넘치면 더한 페이지에도 이 UNIT 의 파트 · 단원 번호", 900), {"click": '#side input[data-a="running"]', "wait": 900}]
    st += bands(6, False) + story(X_L, 20.08, False) + folio(6, False)
    content_elems(6, X_L)
    st += done("본문 왼쪽", "p6.png")

    st += pg_new(7, "⑥ 본문 오른쪽 — 원본 7쪽 (넘친 행을 이어 받는 페이지)", name="본문 오른쪽", rep="none")
    st += bands(7, True) + logo(7) + bands(7, False) + story(X_R, 20.08, False) + folio(7, True)
    content_elems(7, X_R)
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-cont", "text": "본문 왼쪽"}, "wait": 900}]
    st += done("본문 오른쪽", "p7.png")
    st += page_cont(i6, "본문 오른쪽") + page_cont(i4 + 1, "본문 왼쪽")
    recs = [r for p in (4, 5, 6, 7) for r in read_entries(REF_PATH, p)]
    CONTENT.setdefault("UNIT 첫 면", []).append({"파트": s_p["text"], "단원이름": s_u["text"], "단원번호": s_n["text"], BIND: recs})

# ── 9 UNIT 첫 면 (지문형) (76 · 77쪽 펼침) — 2~4파트 단원 첫 면. 쪽 모양은 「UNIT 첫 면」과 같고 글상자는 단락 꼴(표 아님) ──
# 지문 꼬리표(둥근 음영 단락) · 낱말 줄(번호 ⇥ 낱말 ⇥ [품사] 뜻, 위 실선) · 지문 문장(들여쓰기, 위 점선). 값은 원본 76~159쪽 지문형 항목들에서 가장 흔한 값.
# 넘치면 「본문 왼쪽 · 오른쪽」(1파트와 같은 페이지)이 받는다 — 덧쪽의 기본 글상자. 색은 견본 쪽(76쪽, 2파트) 그대로 — 파트마다 색만 다른 면은 따로 만들지 않는다.
# 낱말 줄은 다음 단락과 함께(지문 문장까지 한 덩어리로 쪽을 넘긴다 — 원본 76쪽은 011~012 + 문장이 통째로 77쪽), 지문 문장은 행 분리 금지.
# 알려진 차이: 원본은 쪽이 끊기는 곳에만 맨 아래 실선이 있다(표 꼬리 행 같은) — 단락 경계선은 쪽 끝을 모른다.
from entries import compact as read_compact                            # noqa: E402
BIND9 = "꼬리표+번호+낱말+품사+뜻+예문"


def compact_values():
    import collections
    G, LD = collections.defaultdict(list), []
    pg = [p for p in range(76, 160) if read_compact(REF_PATH, p)]
    for pno in pg:
        m = []
        read_compact(REF_PATH, pno, m)
        for a, b in zip(m, m[1:]):
            G[(a[0], b[0])].append(round(b[1] - a[2], 2))
        LD += [round(f[2] - f[1], 2) for f in m if f[0] == "예문" and f[2] > f[1]]
    mode = lambda v: collections.Counter(v).most_common(1)[0][0]
    g = {k: mode(v) for k, v in G.items()}
    el, sp = els(76), spans(76)
    m76 = []
    read_compact(REF_PATH, 76, m76)
    wb = next(b for k, b, _ in m76 if k == "낱말")
    eb = next(b for k, b, _ in m76 if k == "예문")
    tb = next(b for k, b, _ in m76 if k == "꼬리표")
    rules = sorted([e for e in el if e["k"] in ("rect", "path") and abs(e["w"] - TW) < 0.2 and e["h"] < 0.3], key=lambda e: e["y"])
    solid = next(e for e in rules if e["y"] < wb)
    dot = next(e for e in rules if wb < e["y"] < eb)
    pill = next(e for e in el if e["k"] == "path" and e.get("fill") and 3.5 < e["h"] < 5 and e["y"] < tb < e["y"] + e["h"])
    t76 = REF[75].trimbox
    dp = next(d for d in REF[75].get_drawings() if d.get("fill") and abs((d["rect"].y0 - t76.y0) * MM - pill["y"]) < 0.02 and len(d["items"]) == 20)
    pill_r = round(min(abs(dp["items"][0][2].y - dp["rect"].y0), dp["rect"].height / 2) * MM, 3)   # 둥근 네모 — 첫 세로 변 위 끝 ~ 위 가장자리
    row = [s for s in sp if abs(s["base"] - wb) < 0.7]
    s_no = line_of([s for s in row if s["x"] < X_L + 6], min(s["base"] for s in row if s["x"] < X_L + 6))
    s_w = line_of([s for s in row if X_L + 6 <= s["x"] < X_L + 54], wb)
    mean = [s for s in row if s["x"] >= X_L + 54]
    s_t = line_of(sp, tb)
    exl = [s for s in sp if abs(s["base"] - eb) < 0.2 and s["color"] == "#4d4d4d"]
    s_e = line_of(exl, eb)
    q = lambda x: float(round(x * 2) / 2) if abs(x - round(x * 2) / 2) < 0.06 else float(x)
    boxes = sorted([e for e in el if e["k"] == "path" and e.get("stroke") and e["w"] < 2 and e["y"] < wb and e["y"] > solid["y"]], key=lambda e: e["x"])
    return dict(g=g, lead=min(x for x in LD if x > 1), wb=wb, eb=eb, tb=tb, solid=solid, dot=dot, pill=pill, pill_r=pill_r, boxes=boxes,
                no=(PRE, 700, q(real_size(76, s_no, PRE, 700)), s_no["color"]), w=(PRE, 700, q(real_size(76, s_w, PRE, 700)), "#000000"),
                mn=(NOTO, 500, mean[0]["size"], "#000000"), ex=(PRE, 500, q(real_size(76, s_e, PRE, 500)), "#4d4d4d"),
                tag=(JAL, 400, s_t["size"], s_t["color"]), no_up=round(wb - s_no["base"], 2), w_x=round(s_w["x"] - X_L, 2),
                mn_x=round(min(s["x"] for s in mean) - X_L, 2), tag_x=round(s_t["x"] - X_L, 2), tag_x1=s_t["x1"])


if want(9):
    c = compact_values()
    if os.environ.get("UNIT_DEBUG"):
        print({k: v for k, v in c.items() if k not in ("boxes", "solid", "dot", "pill")})
    g = c["g"]
    st += pg_new(76, "⑨ UNIT 첫 면 (지문형) — 원본 76쪽 (펼침면 왼쪽)", name="UNIT 첫 면 (지문형)")
    st += [S("펼침면 상위 페이지 — 76 · 77쪽이 한 레코드(단원 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    s_cp, pid9, px9, py9 = check_part(76, c["boxes"])
    LT, LW, LE = round(c["tag"][2] * 1.2, 2), round(c["w"][2] * 1.2, 2), round(c["lead"] / MM, 2)
    PT_, PW, PE = lp(*c["tag"][:3], LT), lp(NOTO, 500, c["mn"][2], LW), lp(*c["ex"][:3], LE)   # 낱말 줄 단락 = 뜻 서체 · 행간은 낱말 크기의 120%
    clamp = lambda x: round(max(0.0, x), 2)
    ex_sa = clamp(g[("예문", "낱말")] - PE[1] - PW[0])
    rw = round(c["solid"]["h"] / MM, 3)
    st += need_cstyle("지문 번호", {"font": PRE, "weight": 700, "size": c["no"][2], "color": c["no"][3], "bshift": round(c["no_up"] / MM, 2)},
                      "문자 스타일 「지문 번호」 — 낱말보다 기준선 위로")
    st += need_cstyle("지문 낱말", {"font": PRE, "weight": 700, "size": c["w"][2], "color": "#000000"})
    st += need_cstyle("품사", {"font": PRE, "weight": 500, "size": 5.2, "color": RING_C})
    st += need_cstyle("강조", {"color": ORANGE})
    st += need_cstyle("작은 글", {"size": 6.0})
    pill = c["pill"]
    st += need_pstyle("지문 꼬리표", {"font": JAL, "weight": 400, "size": c["tag"][2], "leading": LT, "color": c["tag"][3], "indent": c["tag_x"],
                                    "shade": pill["fill"], "shade_fit": True, "shade_r": c["pill_r"],
                                    "shade_ol": c["tag_x"], "shade_or": round(pill["x"] + pill["w"] - c["tag_x1"], 2),
                                    "shade_ot": round(c["tb"] - PT_[0] - pill["y"], 2), "shade_ob": round(pill["y"] + pill["h"] - (c["tb"] + PT_[1]), 2),
                                    "space_before": clamp(g.get(("예문", "꼬리표"), 10.5) - ex_sa - PE[1] - PT_[0]),
                                    "space_after": clamp(g[("꼬리표", "낱말")] - PT_[1] - PW[0]), "keep_next": True})
    st += need_pstyle("지문 낱말 줄", {"font": NOTO, "weight": 500, "size": c["mn"][2], "leading": LW, "color": "#000000",
                                     "space_same": clamp(g[("낱말", "낱말")] - PW[1] - PW[0]), "keep_next": True, "tabs": [{"at": c["w_x"]}, {"at": c["mn_x"]}],   # 간격 칸 먼저 — 탭 칸을 치면 다른 접힌 칸이 닫힌다
                                     "rule_above": {"w": rw, "color": c["solid"]["fill"], "offset": round(c["wb"] - (c["solid"]["y"] + c["solid"]["h"]), 2), "keep": True}})
    st += need_pstyle("지문 예문", {"font": PRE, "weight": 500, "size": c["ex"][2], "leading": LE, "color": c["ex"][3], "indent": c["w_x"], "align": "justify",
                                  "space_before": clamp(g[("낱말", "예문")] - PW[1] - PE[0]), "space_after": ex_sa, "keep_together": True,
                                  "rule_above": {"w": rw, "color": c["dot"]["fill"], "offset": round(c["eb"] - (c["dot"]["y"] + c["dot"]["h"]), 2), "type": "dotted"}})
    st += s_cp
    el, sp = els(76), spans(76)
    st += art(76, -3.0, -3.0, 154.0, 22.6, "지문형_머리", None, "머리 — 모눈 띠 · 노란 반원(원본 도형 그림)")
    circ = next(e for e in el if e.get("fill") == "#f5e19e")
    Ebox(circ["x"], circ["y"], circ["w"], circ["h"], "#f5e19e")
    s_p = line_of(sp, next(s["base"] for s in sp if s["base"] < 6))
    st += T(s_p, JAL, 400, size=real_size(76, s_p, JAL, 400), label="파트 — 원고 자리 「파트」 (잘난체)", slot_name="파트", temp="파트", w=20)
    s_u = line_of(sp, next(s["base"] for s in sp if 8 < s["base"] < 11))
    st += T(s_u, JAL, 400, size=real_size(76, s_u, JAL, 400), label="단원 이름 — 원고 자리 「단원이름」", slot_name="단원이름", temp="UNIT", w=20)
    s_n = line_of(sp, next(s["base"] for s in sp if 13 < s["base"] < 16))
    st += T(s_n, VITRO, 900, size=real_size(76, s_n, VITRO, 900), label="단원 번호 — 원고 자리 「단원번호」 (VITRO CORE)", slot_name="단원번호", temp="00", w=25)
    st += bands(76, False)
    top = 25.08
    h9 = round(BOT - top, 2)
    st += text(X_L, top, TW, h9, "Analysis\n001\tword\t뜻", c["mn"][2], "#000000", font=NOTO, weight=500, leading=LW,
               label="단어 항목 글상자 — 한 스레드(꼬리표 · 낱말 줄 · 지문 문장 단락)", auto="")
    st += [F('#side input[data-it="y"]', top, 550), F('#side input[data-a="h"]', h9, 550),
           S(f"첫 번째 기준선 오프셋 — 고정 {round(c['tb'] - top, 2)}mm(꼬리표 기준선)", 900), pick_p("fbo.type", "fixed"), P_("fbo.min", round(c["tb"] - top, 2))]
    st += slot(BIND9, label="데이터 필드 — " + BIND9 + " (원고에 나온 차례대로 한 줄기)")
    st += [slot_style("꼬리표", "지문 꼬리표"), slot_style("뜻", "지문 낱말 줄"), slot_style("예문", "지문 예문")]
    st += slot_inline("번호", cs="지문 번호", sep="\t") + slot_inline("낱말", cs="지문 낱말", sep="\t") + slot_inline("품사", cs="품사", sep=" ") + ring_steps("품사", unit_values()["pos_dy"])
    st += [S("뜻 앞 고정 개체 — 확인 칸(사용자 정의 위치: X 텍스트 프레임 가장자리 · Y 기준선)", 900)]
    st += slot_anchor("뜻", pid9, pos="custom", at="start", xref="frame", yref="baseline", x=round(px9 - X_L, 2), y=round(py9 - c["wb"], 2))
    st += [S("텍스트 스레드 — 새 스토리", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    st += folio(76, False)
    content_elems(76, X_L)
    st += done("UNIT 첫 면 (지문형)", "p76.png")

    st += pg_new(77, "⑨ UNIT 첫 면 (지문형) — 원본 77쪽 (펼침면 오른쪽)", name="UNIT 첫 면 (지문형) 오른쪽")
    st += art(77, -3.0, -3.0, 154.0, 22.6, "지문형_머리77", None, "머리 — 모눈 띠(원본 도형 그림)")
    st += logo(77) + bands(77, False)
    st += text(X_R, top, TW, h9, "이어 받는 프레임", c["mn"][2], "#000000", font=NOTO, weight=500, leading=LW, label="이어 받는 글상자 — 같은 스레드", auto="")
    st += [F('#side input[data-it="y"]', top, 550), F('#side input[data-a="h"]', h9, 550),
           S("텍스트 스레드 — 앞 프레임에 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": "이야기2" if want(4) else "이야기1"}, "wait": 900}]
    st += folio(77, True)
    content_elems(77, X_R)
    st += done("UNIT 첫 면 (지문형) 오른쪽", "p77.png")
    if want(5):                                                          # 넘치면 1파트와 같은 「본문 왼쪽」 · 「본문 오른쪽」
        st += page_cont(len(PAGES) - 1, "본문 왼쪽")
    recs9 = [r for p in (76, 77) for r in read_compact(REF_PATH, p)]
    CONTENT.setdefault("UNIT 첫 면 (지문형)", []).append({"파트": s_p["text"], "단원이름": s_u["text"], "단원번호": s_n["text"], BIND9: recs9})

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
if os.environ.get("UNIT_DEBUG") and UNIT:
    print({k: v for k, v in UNIT.items() if k not in ("boxes", "ring", "g", "ld")}, UNIT["g"], UNIT["ld"])
