"""이의1보카 01 — 「이의1_이의1보카01_내지_인쇄.pdf」(199쪽, 148×210mm · 관리 vocab/xc9398645)를 보고 편집기로 손수 만든다.
등록 이름 「이의1보카 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」 + CLAUDE.md 「교재 등록 작업표」.
만드는 면 = 확인받은 면 목록 5개 그대로(구성.json · faces.json) — 파트마다 색만 다른 면은 따로 만들지 않는다(첫 견본 쪽 색, 초록).
값(자리 · 크기 · 색)은 모두 목표 PDF(상태.json ref)에서 잰다. 목표 PDF 는 예전 코드(Vivliostyle) 판(글자는 이름 없는 윤곽 Type3, 글자 표에서 「대」가 「눀」 —
entries.py 가 바로잡는다).

면(구성.json 번호):
  1 표지 · 5 마지막 면 — 바탕 · 로고 그림 · 고정 글
  2 파트 첫 면 · 3 본문 왼쪽 면 · 4 본문 오른쪽 면 — 단어 항목이 한 스레드로 흐르는 면(파트 첫 면에서 시작, 넘치면 오른쪽 · 왼쪽 번갈아)
허용(상태.json): 영영풀이 기울임(Noto 에 기울임 글꼴 없음) · 쪽 위 「( 본문 1」(지문이 앞 쪽에서 이어짐 표시)은 만들지 않는다 · 긴 표제어를 작게 줄이는 것 없음 · 꼬리표 띠 왼쪽 진한 줄 없음.
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
NAME = "이의1보카 (편집기 제작)"
# 서체(fontmatch.py 글자마다 겹침, 2026-10-20 · 후보 = 책 설정 config.json 서체 Noto · Elice · Bebas · Paperlogy):
# 표제어 · 번호 Noto Sans CJK KR 700 0.912 · 0.949 · 뜻 Noto 500 0.921 · 머리말(예문 …) Elice 500 0.933 · 파트 이름 · PART · 꼬리표 Elice 700 0.965 · 0.954 · 0.961 ·
# 예문(영어) Noto 400 0.79(0.9 미만 — 설정 서체 중 가장 닮음, 크롬 · 예전 코드 판 영문 그리기 차이) · 해석 Noto 400 0.926 · 쪽 번호 Noto 400 0.961 · 책 이름 Elice 500 0.963
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


# ── 이의1보카 면 ───────────────────────────────────────────────────────
sys.path.insert(0, HERE)
from entries import entries as read_entries                             # noqa: E402
ELICE, BEBAS, PAPER = "Elice DX Neolli OTF", "Bebas Neue", "Paperlogy"
GREEN, GREEN2, GRAY, LABEL = "#2eab71", "#67c39a", "#636363", "#a1a1a1"
BIND = "꼬리표+번호+표제어+품사+뜻+예문+해석+유반의어+파생어+주의+영영풀이"
X0, TW = 18.99, 110.0                                                    # 글상자 왼쪽 · 폭(지문 꼬리표 띠 · 번호 줄 오른쪽 끝 128.99)
TOP2, TOPC = 31.0, 25.5                                                  # 파트 첫 면 글상자 위(꼬리표 띠 위) · 이어 받는 면 위(쪽 위 「( 본문 1」 표시 자리 아래)
V = {}


def lp(fam, wt, size, lead):
    asc, desc, _ = face(fam, wt)
    s, L = size * MM, lead * MM
    a = (L - (asc + desc) * s) / 2 + asc * s
    return a, L - a


def row_of(sp, base, x0=0, x1=200, tol=0.3):
    r = [s for s in sp if abs(s["base"] - base) < tol and x0 <= s["x"] < x1]
    return line_of(r, r[0]["base"]) if r else None


def values():
    """항목 간격 · 크기 · 색 — 원본 2~198쪽 항목들에서 가장 흔한 값(entries.py)"""
    import collections
    if V:
        return V
    G = collections.defaultdict(list)
    for pno in range(2, 199):
        m = []
        read_entries(REF_PATH, pno, m)
        for a, b in zip(m, m[1:]):
            if not (a[0] in ("품사", "뜻", "표제어") and b[0] in ("품사", "뜻")):
                G[(a[0], b[0])].append(round(b[1] - a[2], 2))
    mode = lambda v: collections.Counter(v).most_common(1)[0][0]
    g = {k: mode(v) for k, v in G.items() if len(v) >= 3}
    sp, el = spans(2), els(2)
    s_no = row_of(sp, 45.09, 0, 40)
    s_hw = row_of(sp, 50.28, 0, 40)
    s_mn = row_of(sp, 50.25, 48, 140)
    s_pos = row_of(sp, 49.85, 44, 48)
    s_lab = row_of(sp, 54.31, 0, 40)
    s_ex = row_of(sp, 57.39, 44, 140)                                    # 「Angeles National Forest.」 — 검정 한 줄
    s_tr = row_of(sp, 63.24, 44, 140)
    s_ex1 = row_of(sp, 54.68, 44, 140)                                   # 꽉 찬 줄 — 자간(글자 사이)은 줄 첫 ~ 끝 글자 거리에서
    s_tr1 = row_of(sp, 60.53, 44, 140)
    syn = [s for s in sp if 66 < s["base"] < 88 and s["x"] >= 44]
    syn_b = sorted({round(s["base"], 2) for s in syn if s["color"] == GRAY})
    s_small = next(s for s in syn if s["color"] == LABEL)
    s_tag = row_of(sp, 35.53, 0, 100)
    s_cnt = row_of(sp, 35.53, 100, 140)
    bar = next(e for e in el if e.get("fill") == "#d6ede2" and 6 < e["h"] < 9 and e["y"] > 20)
    rule = next(e for e in el if e["k"] in ("rect", "line") and e["w"] > 100 and e["h"] < 0.3 and abs(e["y"] - 44.86) < 0.5)
    box = next(e for e in el if e.get("fill") == "#f0f0f0")
    V.update(g=g, no=(NOTO, 700, s_no["size"], s_no["color"]), hw=(NOTO, 700, s_hw["size"], "#000000"), mn=(NOTO, 500, s_mn["size"], "#000000"),
             pos=(NOTO, 500, s_pos["size"], s_pos["color"]), lab=(ELICE, 500, s_lab["size"], LABEL), ex=(NOTO, 400, s_ex["size"], "#000000"),
             tr=(NOTO, 400, s_tr["size"], GRAY), small=(NOTO, 400, s_small["size"], LABEL), tag=(ELICE, 700, s_tag["size"], s_tag["color"]),
             cnt=(ELICE, 500, s_cnt["size"], s_cnt["color"]), ex_track=track_of(s_ex1, NOTO, 400, s_ex["size"]), tr_track=track_of(s_tr1, NOTO, 400, s_tr["size"]), lab_up=round(s_ex["base"] - 57.39 + (54.68 - s_lab["base"]), 2) if False else round(54.68 - s_lab["base"], 2),
             ex_lead=round(57.39 - 54.68, 2), syn_lead=round(syn_b[1] - syn_b[0], 2), bar=bar, rule=rule, box=box,
             tag_x=round(s_tag["x"] - X0, 2), cnt_x1=round(s_cnt["x1"] - X0, 2), mn_x=round(box["x"] - X0, 2), mn_x2=round(s_mn["x"] - (box["x"] + box["w"]), 2),
             pos_up=round(s_mn["base"] - s_pos["base"], 2), hw_b=s_hw["base"], tag_b=s_tag["base"])
    return V


def styles():
    v = values()
    g = v["g"]
    L = {"no": round(v["no"][2] * 1.2, 2), "hw": round(v["hw"][2] * 1.2, 2), "ex": round(v["ex_lead"] / MM, 2), "tr": round(v["ex_lead"] / MM, 2),
         "syn": round(v["syn_lead"] / MM, 2), "tag": round(v["tag"][2] * 1.2, 2)}
    P = {"no": lp(NOTO, 700, v["no"][2], L["no"]), "tag": lp(ELICE, 700, v["tag"][2], L["tag"]),
         "ex": lp(NOTO, 400, v["ex"][2], L["ex"]), "tr": lp(NOTO, 400, v["tr"][2], L["tr"]), "syn": lp(NOTO, 400, v["ex"][2], L["syn"])}
    a_hw, d_hw = lp(NOTO, 700, v["hw"][2], L["hw"])                     # 표제어 줄 — 큰 표제어(같은 줄 높이)와 뜻 글자 중 더 큰 위 · 아래 몫
    a_mn, d_mn = lp(NOTO, 500, v["mn"][2], L["hw"])
    P["mn"] = (a_mn, max(d_hw, d_mn))                                     # 위 몫은 단락 글자(뜻) 기준 — 편집기 줄 위치는 단락 스타일 글꼴로 정해진다(2쪽 번호→표제어 0.45mm 짧았음)
    clamp = lambda x: round(max(0.0, x), 2)
    gap = lambda k, d: g.get(k, d)
    sp_ = lambda gp_, a, b: clamp(gp_ - P[a][1] - P[b][0])
    no_sb = sp_(gap(("영영풀이", "번호"), 7.94), "syn", "no")
    lab_gap = gap(("유반의어", "파생어"), 4.3)
    bul = lambda t: {"type": "bullet", "char": t, "after": "\t", "cs": "머리말"}
    ind = round(v["mn_x"] + 0.01, 2)
    st = need_cstyle("머리말", {"font": ELICE, "weight": 500, "size": v["lab"][2], "color": LABEL, "bshift": round(v["lab_up"] / MM, 2)},
                     "문자 스타일 「머리말」 — 예문 · 유반의어 · 파생어 · 영영풀이(글머리 기호 글)")
    st += need_cstyle("표제어", {"font": NOTO, "weight": 700, "size": v["hw"][2], "color": "#000000"})
    st += need_cstyle("품사", {"font": NOTO, "weight": 500, "size": v["pos"][2], "color": v["pos"][3]})
    st += need_cstyle("강조", {"color": v["no"][3]})
    st += need_cstyle("작은 말", {"size": v["small"][2], "color": LABEL})
    st += need_cstyle("낱말 수", {"font": ELICE, "weight": 500, "size": v["cnt"][2], "color": v["cnt"][3]})
    bar = v["bar"]
    st += need_pstyle("꼬리표", {"font": ELICE, "weight": 700, "size": v["tag"][2], "leading": L["tag"], "color": v["tag"][3], "indent": v["tag_x"],
                               "tabs": [{"at": round(v["cnt_x1"] - v["tag_x"], 2), "align": "right"}],   # 탭 자리는 단락 글 왼쪽(들여쓰기)에서 "shade": bar["fill"], "shade_r": 1.0,
                               "shade_ot": round(v["tag_b"] - P["tag"][0] - bar["y"], 2), "shade_ob": round(bar["y"] + bar["h"] - (v["tag_b"] + P["tag"][1]), 2),
                               "start": "frame", "keep_next": True,
                               "space_after": clamp(gap(("꼬리표", "번호"), 9.52) - P["tag"][1] - P["no"][0] - no_sb)})
    r = v["rule"]
    st += need_pstyle("단어 번호", {"font": NOTO, "weight": 700, "size": v["no"][2], "leading": L["no"], "color": v["no"][3], "space_before": no_sb, "keep_next": True,
                                  "rule_above": {"w": round(max(r["h"], 0.1) / MM, 3), "color": r.get("fill") or r.get("stroke") or v["no"][3],
                                                 "offset": round(45.09 - (r["y"] + max(r["h"], 0.1)), 2), "il": round(r["x"] - X0, 2)}})
    st += need_pstyle("단어 뜻", {"font": NOTO, "weight": 500, "size": v["mn"][2], "leading": L["hw"], "color": "#000000", "keep_next": True,
                                "space_before": sp_(gap(("번호", "표제어"), 5.21), "no", "mn"), "tabs": [{"at": v["mn_x"]}]})
    body = lambda k, col, lead, **o: dict({"font": NOTO, "weight": 400, "size": v[k][2], "leading": lead, "color": col, "indent": ind, "indent_first": -ind,
                                           "keep_next": True, "keep_together": True, "tracking": v["ex_track"]}, **o)   # 자간 = 예문 꽉 찬 줄에서 잰 값(본문 글 모두 같은 자간) · 항목은 쪽을 넘어 갈라지지 않는다(원본 — 항목이 늘 쪽 안에 통째로)
    st += need_pstyle("단어 예문", body("ex", "#000000", L["ex"], list=bul("예문"), space_before=sp_(gap(("뜻", "예문"), 4.37), "mn", "ex")))
    st += need_pstyle("단어 해석", dict(body("tr", GRAY, L["tr"], tracking=v["tr_track"], space_before=sp_(gap(("예문", "해석"), 3.14), "ex", "tr")), indent_first=0))
    st += need_pstyle("단어 유반의어", body("ex", GRAY, L["syn"], list=bul("유반의어"), space_before=sp_(gap(("해석", "유반의어"), 4.2), "tr", "syn")))
    st += need_pstyle("단어 파생어", body("ex", "#000000", L["syn"], list=bul("파생어"), space_before=sp_(lab_gap, "syn", "syn")))
    st += need_pstyle("단어 주의", body("ex", "#000000", L["syn"], list=bul("주의"), space_before=sp_(lab_gap, "syn", "syn")))
    st += need_pstyle("단어 영영풀이", body("ex", GRAY, L["syn"], list=bul("영영풀이"), keep_next=False, space_before=sp_(gap(("유반의어", "영영풀이"), 4.3), "syn", "syn")))
    v.update(L=L, P=P)
    return st


def story(x, top, head, bot):
    v = values()
    h = round(bot - top, 2)
    st = text(x, top, TW, h, "본문 1\t17 words" if head else "이어 받는 프레임", 6, "#000000", font=NOTO, weight=400,
              label="단어 항목 글상자 — 한 스레드(지문 꼬리표 · 번호 · 표제어 줄 · 예문 …)" if head else "이어 받는 글상자 — 같은 스레드", auto="")
    st += [F('#side input[data-it="y"]', top, 550), F('#side input[data-a="h"]', h, 550)]
    if not head:
        return st + [S("텍스트 스레드 — 같은 스토리를 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": "이야기1"}, "wait": 900}]
    st += [S(f"첫 번째 기준선 오프셋 — 고정 {round(v['tag_b'] - top, 2)}mm(꼬리표 기준선)", 900), pick_p("fbo.type", "fixed"), P_("fbo.min", round(v["tag_b"] - top, 2))]
    st += slot(BIND, label="데이터 필드 — " + BIND + " (항목마다 원고에 나온 차례대로 한 줄기)")
    for f, sty in (("꼬리표", "꼬리표"), ("번호", "단어 번호"), ("뜻", "단어 뜻"), ("예문", "단어 예문"), ("해석", "단어 해석"), ("유반의어", "단어 유반의어"),
                   ("파생어", "단어 파생어"), ("주의", "단어 주의"), ("영영풀이", "단어 영영풀이")):
        st.append(slot_style(f, sty))
    box = v["box"]
    em = v["mn"][2] * MM
    near = lambda gap: min(((" ", space_em(NOTO, 500)), (" ", 0.5), (" ", 0.125), (" ", 1 / 24)), key=lambda c: abs(c[1] * em - gap))[0]
    ins = round(max(0.1, (box["h"] - v["pos"][2] * MM) / 2), 2)
    st += slot_inline("표제어", cs="표제어", sep="\t") + slot_inline("품사", cs="품사", sep=near(v["mn_x2"]))
    st += [S(f"「품사」 — 인라인 고정 텍스트 프레임: 칠 {box['fill']} · 모퉁이 · 인세트 {ins}mm", 900)] + color_p("slot_fmt.품사.frame.fill", box["fill"]) + [
        P_("slot_fmt.품사.frame.r", 0.5, 600), P_("slot_fmt.품사.frame.inset", ins, 600), P_("slot_fmt.품사.frame.y", v["pos_up"], 600)]
    st += [S("텍스트 스레드 — 새 스토리(넘친 글은 다음 프레임 · 페이지로)", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    return st


def content_elems(pno, x0):
    """원고 요소 — 번호 줄 선 · 품사 칸 · 꼬리표 띠 · 글줄(들어갔나 · 흐름 간격만)"""
    el, sp = els(pno), spans(pno)
    t = REF[pno - 1].trimbox
    for e in el:
        if e["y"] < 18 or e["y"] > 200:
            continue
        if (e.get("fill") in ("#f0f0f0",) and e["w"] < 8) or (e["w"] > 100 and (e["h"] < 0.3 or 6 < e["h"] < 9)):
            E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(e["x"], 2), "y": round(e["y"], 2), "w": round(e["w"], 2), "h": round(max(e["h"], 0.1), 2),
               "color": e.get("fill") or e.get("stroke"), "see": e.get("fill") or e.get("stroke"), "pad": 0.3, "ctol": 25, "원고": True})
    body = [s for s in sp if 18 < s["base"] < 200]
    for b in sorted({round(s["base"], 1) for s in body}):
        for lo, hi in ((0, 44), (44, 200)):
            row = [s for s in body if abs(s["base"] - b) < 0.2 and lo <= s["x"] < hi]
            if not row:
                continue
            s = line_of(row, row[0]["base"])
            bb = s["bbox"]
            E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round((bb[0] - t.x0) * MM, 2), "y": round((bb[1] - t.y0) * MM, 2), "w": round((bb[2] - bb[0]) * MM, 2),
               "h": round((bb[3] - bb[1]) * MM, 2), "color": s["color"], "see": s["color"], "ctol": 30, "pad": 0.6, "search": 0.6, "text": s["text"], "원고": True})


def folio(pno, right, part_bind=None):
    """쪽 꼬리 — 쪽 번호(시스템 자리) · 「|」 · 책 이름(왼쪽) 또는 파트 이름(오른쪽) — 원고 자리, 넘친 페이지에도(러닝 헤드)"""
    sp = spans(pno)
    row = sorted([s for s in sp if s["base"] > 200], key=lambda s: s["x"])
    num = next(s for s in row if s["text"].strip().isdigit())
    bar = next(s for s in row if "|" in s["text"])
    name = [s for s in row if s is not num and s is not bar]
    st = T(num, ELICE, 700, size=num["size"], label="쪽 번호 — 시스템 자리(엘리스 700 0.953)", bind="sys.page_no", align="right" if right else None, w=8)
    st += T(dict(bar, text="|"), ELICE, 300, size=bar["size"], label="「|」 — 고정 글(엘리스 300 — 높이 원본과 같음, Noto 는 15% 길다 · 500 은 잉크 1.2~1.5배)", w=3)
    ELEMS[len(PAGES)][-1].pop("text", None)                              # 폭 0.17mm 글자 — 검사 해상도에서 1화소 차이로 잉크 비가 흔들린다(2쪽 1.25 · 4쪽 0.93, 1200dpi 로 재면 원본 · 결과 잉크 같음 396.8) — 자리 · 크기만 맞댄다
    nm = line_of(name, name[0]["base"])
    st += T(nm, ELICE, 500, size=nm["size"], label=("파트 이름" if right else "책 이름") + " — 원고 자리 · 러닝 헤드", slot_name=part_bind or "책이름",
            temp="파트" if right else "책 이름", align="right" if right else None, w=25)
    ELEMS[len(PAGES)][-1]["원고"] = True
    st += [{"click": '#side input[data-a="running"]', "wait": 800}] if pno not in (2,) else []
    return st


def bands(pno):
    el = els(pno)
    st = []
    for e in sorted([e for e in el if e["k"] == "rect" and e["w"] > 140 and e["y"] < 10], key=lambda e: -e["h"]):
        st += rbox(e["x"], e["y"], e["w"], e["h"], e["fill"], label=f"위 띠 {e['fill']}", measure=False)
        Ebox(40.0, e["y"], 80.0, e["h"], e["fill"], pad=0.3, ctol=15)   # 탭 그림과 떨어진 가운데만 — 쪽 전체 폭으로 재면 측정 창이 탭(초록)까지 잡아 선 높이가 2mm 로 잡혔다(600dpi 로 재면 띠 · 선 경계 원본과 같음 4.82 · 5.54)
    return st


def page_cont(i, target):
    return [S(f"넘치면 더할 페이지 — 「{target}」", 1000), {"click": f'#rail .pg[data-i="{i}"]', "wait": 1500},
            {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-cont", "text": target}, "wait": 900}]


BOT = 194.0

# ── 1 표지 (1쪽) ──
if want(1):
    st += pg_new(1, "① 표지 — 원본 1쪽", name="표지", rep=False)
    el, sp = els(1), spans(1)
    info = sorted(REF[0].get_image_info(xrefs=True), key=lambda i: -(i["bbox"][2] - i["bbox"][0]))
    t = REF[0].trimbox
    for k, im in enumerate(info):
        b = im["bbox"]
        x, y, w, h = round((b[0] - t.x0) * MM, 2), round((b[1] - t.y0) * MM, 2), round((b[2] - b[0]) * MM, 2), round((b[3] - b[1]) * MM, 2)
        path = ref_image(REF, im["xref"], os.path.join(WORK, f"표지_그림{k}.png"))
        if im["transform"][3] < 0:                                           # 원본이 위아래 뒤집어 놓은 그림(바탕 그러데이션) — 놓인 그대로
            Image.open(path).transpose(Image.FLIP_TOP_BOTTOM).save(path)
        st += image(x, y, w, h, path, label=["바탕 그림 — 원본 그림", "로고 그림 — 원본 그림"][min(k, 1)])
        st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]
        c = clip({"x": x, "y": y, "w": w, "h": h})
        E({"id": f"img{k}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    shp = [e for e in el if e["k"] in ("path", "rect") and e.get("fill") == GREEN]
    hx, hy, hw, hh = union(shp)
    st += art(1, round(hx - 0.2, 2), round(hy - 0.2, 2), round(hw + 0.4, 2), round(hh + 0.4, 2), "표지_도형", None, "선 · 어휘 칸 — 원본 도형 그림")
    for e in shp:
        Ebox(e["x"], e["y"], e["w"], e["h"], GREEN, pad=0.3)
    for b0, font, wt, lab, slot_n in ((41.15, PAPER, 900, "EEGOEEGO — 고정 글", None), (149.41, ELICE, 700, "학교 · 시험 — 원고 자리 「표지제목」", "표지제목"),
                                      (149.40, ELICE, 700, "어휘 — 고정 글", None), (179.43, PAPER, 900, "SONG AHYOUNG — 고정 글", None)):
        lo, hi = (0, 84) if b0 == 149.41 else (84, 200) if b0 == 149.40 else (0, 200)
        s = row_of(sp, b0, lo, hi, 0.05)
        st += T(s, font, wt, size=real_size(1, s, font, wt) if font == ELICE else s["size"], label=lab, slot_name=slot_n, temp="학교 학기 시험" if slot_n else None, w=45)
        if slot_n:
            CONTENT["표지제목"] = s["text"]
    # 「| 1」은 PDF 글에만 있고 바탕 그림에 가려 안 보인다 — 만들지 않는다
    st += done("표지", "p1.png")

# ── 2 파트 첫 면(2쪽) · 3 본문 왼쪽(4쪽) · 4 본문 오른쪽(3쪽) — 단어 항목이 흐르는 면 ──
if want(2) or want(3) or want(4):
    v = values()
    i2 = len(PAGES)
    st += pg_new(2, "② 파트 첫 면 — 원본 2쪽", name="파트 첫 면")
    st += styles()
    el, sp = els(2), spans(2)
    hd = [e for e in el if e["y"] < 27 and e["k"] in ("rect", "path") and (e.get("fill") or e.get("stroke"))]
    st += art(2, -3.0, -3.0, 154.0, 29.0, "파트_머리", None, "머리 — 띠 · 세모 · PART 칸(원본 도형 그림)")
    for e in hd:
        if e["k"] == "rect" and e["w"] > 100 and e.get("fill"):
            Ebox(e["x"], e["y"], e["w"], e["h"], e["fill"], pad=0.4)
    s_pt = row_of(sp, 12.77, 0, 40, 0.05)
    st += T(s_pt, ELICE, 700, size=s_pt["size"], label="P A R T — 고정 글(엘리스)", w=12)
    s_no = row_of(sp, 19.22, 0, 40, 0.05)
    st += T(s_no, BEBAS, 700, size=s_no["size"], label="파트 번호 — 원고 자리 「파트번호」 (베바스)", slot_name="파트번호", temp="0", w=10)
    s_nm = row_of(sp, 12.54, 40, 140, 0.05)
    st += T(s_nm, ELICE, 700, size=s_nm["size"], label="파트 이름 — 원고 자리 「파트」 (엘리스)", slot_name="파트", temp="파트 이름", w=40)
    st += folio(2, False)
    st += story(X0, TOP2, True, BOT)
    content_elems(2, X0)
    st += done("파트 첫 면", "p2.png")

    i3 = len(PAGES)
    st += pg_new(4, "③ 본문 왼쪽 — 원본 4쪽 (넘친 글을 이어 받는 페이지)", name="본문 왼쪽", rep="none")
    el, sp = els(4), spans(4)
    st += bands(4)
    tab = [e for e in el if e["y"] < 15 and 5 < e["x"] < 20 and e["w"] < 15]
    hx, hy, hw, hh = union(tab)
    st += art(4, round(hx - 0.6, 2), round(hy - 0.6, 2), round(hw + 1.2, 2), round(hh + 1.2, 2), "왼쪽_탭", None, "파트 번호 탭 — 원본 도형 그림")
    Ebox(hx, hy, hw, hh, GREEN, pad=0.6)
    s_t = row_of(sp, 9.57, 0, 20, 0.05)
    st += T(s_t, ELICE, 700, size=s_t["size"], label="탭 파트 번호 — 원고 자리 「파트번호」 · 러닝 헤드", slot_name="파트번호", temp="0", w=6)
    ELEMS[len(PAGES)][-1]["원고"] = True
    st += [{"click": '#side input[data-a="running"]', "wait": 800}]
    st += folio(4, False) + story(X0, TOPC, False, BOT)
    content_elems(4, X0)
    st += done("본문 왼쪽", "p4.png")

    i4 = len(PAGES)
    st += pg_new(3, "④ 본문 오른쪽 — 원본 3쪽 (넘친 글을 이어 받는 페이지)", name="본문 오른쪽", rep="none")
    el, sp = els(3), spans(3)
    st += bands(3)
    tab = [e for e in el if e["x"] > 140 and 15 < e["y"] < 40]
    hx, hy, hw, hh = union(tab)
    lite = next(e for e in tab if e.get("fill") == GREEN2)                # 탭 위 옅은 면 — 원본은 진한 탭 위에 겹쳐 그리고 잘라서(clip) 위 0.93mm(19.98~20.91)만 보인다
    dark = next(e for e in tab if e.get("fill") == GREEN)
    path = os.path.join(WORK, "오른쪽_탭.svg")
    pdfsvg.export(REF_PATH, 3, round(hx - 0.3, 2), round(hy - 0.3, 2), round(min(hw + 0.6, 151 - hx), 2), round(hh + 0.6, 2), path,
                  skip=lambda d: d.get("fill") and len(d["items"]) == 1 and d["rect"].height * MM > 10)
    st += image(round(hx - 0.3, 2), round(hy - 0.3, 2), round(min(hw + 0.6, 151 - hx), 2), round(hh + 0.6, 2), path, label="파트 탭 — 원본 도형 그림(잘린 옅은 면 빼고)")
    st += rbox(lite["x"], lite["y"], lite["w"], 0.93, GREEN2, label="탭 위 옅은 띠 — 진한 탭 위에 겹침(보이는 0.93mm)", measure=False)
    Ebox(dark["x"], dark["y"], min(dark["w"], W_MM - dark["x"]), dark["h"], GREEN, pad=0.6)
    vt = sorted([s for s in sp if s["x"] > 140 and s["color"] == "#ffffff"], key=lambda s: s["base"])
    lead = round((vt[1]["base"] - vt[0]["base"]) / MM, 2)
    sz = vt[0]["size"]
    st += text(round(vt[0]["x"] - 0.1, 2), round(top_of(vt[0]["base"], sz, NOTO, 700, lead), 2), round(vt[0]["x1"] - vt[0]["x"] + 0.6, 2),
               round(lead * MM * len(vt) + 1, 1), "파트", sz, "#ffffff", font=NOTO, weight=700, leading=lead,
               label="세로 파트 이름 — 원고 자리 「파트」 · 러닝 헤드(좁은 글상자 — 한 글자씩 줄)")
    st += slot("파트")
    E({"id": "vt", "x": round(vt[0]["x"], 2), "y": round(vt[0]["base"] - sz * MM * 0.8, 2), "w": round(vt[0]["x1"] - vt[0]["x"], 2),
       "h": round(vt[-1]["base"] - vt[0]["base"] + sz * MM, 2), "color": "#ffffff", "see": "#ffffff", "ctol": 30, "pad": 0.6, "원고": True})
    st += [{"click": '#side input[data-a="running"]', "wait": 800}]
    st += folio(3, True, "파트") + story(X0, TOPC, False, BOT)
    content_elems(3, X0)
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-cont", "text": "본문 왼쪽"}, "wait": 900}]
    st += done("본문 오른쪽", "p3.png")
    st += page_cont(i3, "본문 오른쪽") + page_cont(i2, "본문 오른쪽")
    CONTENT.setdefault("파트 첫 면", []).append({"파트번호": s_no["text"], "파트": s_nm["text"], "책이름": "이의1보카",
                                             BIND: [r for p in (2, 3, 4) for r in read_entries(REF_PATH, p, top=TOP2 if p == 2 else None)]})

# ── 5 마지막 면 (199쪽) ──
if want(5):
    st += pg_new(199, "⑤ 마지막 면 — 원본 199쪽", name="마지막 면", rep=False)
    el, sp = els(199), spans(199)
    info = sorted(REF[198].get_image_info(xrefs=True), key=lambda i: -(i["bbox"][2] - i["bbox"][0]))
    t = REF[198].trimbox
    for k, im in enumerate(info):
        b = im["bbox"]
        x, y, w, h = round((b[0] - t.x0) * MM, 2), round((b[1] - t.y0) * MM, 2), round((b[2] - b[0]) * MM, 2), round((b[3] - b[1]) * MM, 2)
        path = ref_image(REF, im["xref"], os.path.join(WORK, f"끝_그림{k}.png"))
        if im["transform"][3] < 0:
            Image.open(path).transpose(Image.FLIP_TOP_BOTTOM).save(path)
        st += image(x, y, w, h, path, label=["바탕 그림 — 원본 그림", "로고 그림 — 원본 그림"][min(k, 1)])
        st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]
        c = clip({"x": x, "y": y, "w": w, "h": h})
        E({"id": f"img{k}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    for b0, font, wt, lab in ((120.26, PAPER, 900, "EEGOEEGO — 고정 글"), (125.32, ELICE, 700, "UPGRADE YOUR ENGLISH — 고정 글"),
                              (130.02, ELICE, 700, "ELEVATE YOUR FUTURE — 고정 글"), (147.28, PAPER, 900, "SONG AHYOUNG — 고정 글")):
        s = row_of(sp, b0, 0, 200, 0.05)
        st += T(s, font, wt, size=s["size"], label=lab, w=45)
    # 「| 199」는 PDF 글에만 있고 바탕 그림에 가려 안 보인다 — 만들지 않는다
    st += done("마지막 면", "p199.png")

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
if os.environ.get("UNIT_DEBUG") and V:
    print({k: v for k, v in V.items() if k not in ("bar", "rule", "box")})
