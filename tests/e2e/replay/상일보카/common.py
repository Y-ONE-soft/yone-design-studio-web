"""상일보카 대본 공용 — 원본 읽기 · 그리기 도우미 · 상태(ELEMS · PAGES · CONTENT). 면 대본(make.py · face_*.py)이 함께 쓴다."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
from mkpage import _color                                               # noqa: E402
import mkpage
import pymupdf
import pagecmp                                                          # noqa: E402
mkpage.SPOT = {"mm": [80, 175]}                                         # A5 쪽 안에서 끌어 그릴 빈 자리 · 글 확정용 빈 곳(오른쪽 여백)
mkpage.AWAY = {"mm": [140, 190]}
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
W_MM, H_MM = 148.0, 210.0
NAME = "상일보카 (편집기 제작)"
ELICE, NOTO = "Elice DX Neolli OTF", "Noto Sans CJK KR"

ELEMS, PAGES, CONTENT = {}, [], {}


def want(n):
    return not ONLY or str(n) in ONLY


def E(e):
    ELEMS[len(PAGES)].append(e)


def els(pno):
    """원본 요소(쪽 안에 걸친 것) — 숨은 글(투명 · 0.5pt)은 뺀다"""
    return [e for e in pagecmp.elements(REF_PATH, pno) if e["x"] < W_MM and e["x"] + e["w"] > 0 and e["y"] < H_MM and e["y"] + e["h"] > 0
            and not (e["k"] == "text" and (e.get("opacity") == 0 or e["size"] < 2))]


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
                if ch and sp["size"] >= 2 and sp.get("alpha", 255) > 0:
                    out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                                "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "text": "".join(c["c"] for c in sp["chars"]).strip()})
    return out


def line_of(sps, base, tol=0.3):
    """기준선이 같은 조각들을 한 줄 글 조각으로(첫 글자 ~ 끝 글자)"""
    row = sorted([s for s in sps if abs(s["base"] - base) < tol], key=lambda s: s["x"])
    t = row[0]["text"]
    for a, b in zip(row, row[1:]):                                      # 조각 사이 틈이 0.4mm 넘을 때만 빈칸 — 원본은 글자마다 조각이 끊긴다
        t += (" " if b["x"] - a["x1"] > 0.4 else "") + b["text"]
    return dict(row[0], x1=row[-1]["x1"], text=t)


def el_line(sp, e):
    """맞대기 도구가 읽은 글 한 줄(띄어쓰기가 바른 글) + 그 자리 글자 조각들로 잰 기준선 · 첫 글자 · 끝 글자"""
    row = [s for s in sp if e["x"] - 0.5 <= s["x"] <= e["x"] + e["w"] + 0.5 and e["y"] - 1 <= s["base"] - s["size"] * MM * 0.8 <= e["y"] + e["h"] + 1
           and abs(s["size"] - e["size"]) < 0.3]
    base = sorted(row, key=lambda s: s["x"])[0]["base"]
    return dict(line_of(row, base), text=e["text"])


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
    if rep:                                                              # 원고마다 — 원고 덩어리 하나에 이 면 한 장
        st += [{"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1200}]
    return st


def T(s, font, weight, label=None, slot_name=None, temp=None, align=None, w=None, leading=None, h=None, measure=True, bind=None):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서(원본 첫 글자 ~ 끝 글자 거리 - 서체 글자 폭)"""
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


def rbox(x, y, w, h, fill, label=None, r=0, measure=True, alpha=None):
    st = box(round(x, 2), round(y, 2), round(w, 2), round(h, 2), fill, label=label, radius=r, alpha=alpha)
    if measure:
        Ebox(x, y, w, h, fill)
    return st


def find(el, k, x, y, tol=0.6, **kw):
    c = [e for e in el if e["k"] == k and abs(e["x"] - x) < tol and abs(e["y"] - y) < tol and all(e.get(a) == v for a, v in kw.items())]
    if not c:
        raise RuntimeError(f"원본 요소 없음 {k} {x},{y} {kw}")
    return c[0]


def mix(fg, bg, a):
    """불투명 a(0~1) 로 겹친 색 — 원본 차례 구분선(흰 35%)은 단락 경계선 색으로 겹친 색을 쓴다"""
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * a + y * (1 - a)) for x, y in zip(f, b))


def full_bg(el, label):
    """쪽 전체 바탕(도련까지) — 원본 바탕 상자 그대로"""
    bg = next(e for e in el if e["k"] == "rect" and e["x"] < -2.5 and e["y"] < -2.5 and e["w"] > W_MM and e["h"] > H_MM)
    # 도련(3mm) 밖으로 나간 몫은 자른다 — 표지 바탕은 원본에서 도련 밖 0.4mm 더 나가 편집기가 「면 아래로 넘침」으로 본다
    x0, y0, x1, y1 = max(bg["x"], -3), max(bg["y"], -3), min(bg["x"] + bg["w"], W_MM + 3), min(bg["y"] + bg["h"], H_MM + 3)
    return rbox(x0, y0, x1 - x0, y1 - y0, bg["fill"], label=label), bg["fill"]


def crop_image(pno, e, name, label):
    """원본의 그림(벡터 로고 — 수백 · 수천 조각)을 그 자리 그대로 그림 파일로(바탕색까지 같이 잘라 덮는다)"""
    path = os.path.join(WORK, f"{name}.png")
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    r = pymupdf.Rect(t.x0 + e["x"] / MM, t.y0 + e["y"] / MM, t.x0 + (e["x"] + e["w"]) / MM, t.y0 + (e["y"] + e["h"]) / MM)
    pix = p.get_pixmap(clip=r, dpi=600)
    # 바탕색은 빼고(투명) 로고만 — 원본 인쇄판 바탕은 출력 색 프로필로 조금 다른 색이라 그대로 자르면 상자 자국이 보인다.
    # 잘라 낸 네 귀의 색 = 바탕, 바탕과의 색 거리로 불투명도를 매긴다(가장자리 부드럽게)
    import numpy as _np
    from PIL import Image as _Im
    a = _np.asarray(_Im.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(float)
    bg = _np.median(_np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]]), axis=0)
    dist = _np.sqrt(((a - bg) ** 2).sum(-1))
    alpha = _np.clip(dist / 60.0, 0, 1)
    fg = _np.where(alpha[..., None] > 0, bg + (a - bg) / _np.maximum(alpha[..., None], 1e-3), a)   # 바탕을 덜어 낸 본래 색
    _Im.fromarray(_np.dstack([_np.clip(fg, 0, 255), alpha * 255]).astype("uint8"), "RGBA").save(path)
    E({"id": f"i{len(ELEMS[len(PAGES)])}", "x": round(e["x"], 2), "y": round(e["y"], 2), "w": round(e["w"], 2), "h": round(e["h"], 2),
       "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    # 끌어 그리는 자리가 작으면(세로 10mm 밑) 그림 도구가 누르기로 보고 칸을 안 만든다 — 크게 그려 넣고 마지막에 원본 크기로
    h = round(e["h"], 2)
    st = image(round(e["x"], 2), round(e["y"], 2), round(e["w"], 2), max(h, 12), path, label=label)
    return st + ([F('#side input[data-a="h"]', h), F('#side input[data-it="y"]', round(e["y"], 2))] if h < 12 else [])


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


# ── 쪽 틀(구간 공통) — 첫 펼침면 왼쪽 · 오른쪽, 본문 펼침면 왼쪽 · 오른쪽. 구간마다 같은 틀(색만 다름 — 이 면의 견본 쪽 색) ───────────
BEBAS = "Bebas Neue"


def ref_draws(pno):
    """원본 도형 — mm 상자 · 칠 · 칠 불투명 · 선 · 경로 d(상자 안 0~1, 편집기 「경로 d」 칸 꼴 — 곡선 C 포함)"""
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
        if d:
            d.append("Z")
        out.append({"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "fill": hexc(dr.get("fill")),
                    "alpha": round((dr.get("fill_opacity") or 1) * 100), "stroke": hexc(dr.get("color")), "sw": (dr.get("width") or 0) * MM,
                    "d": " ".join(d), "rect": dr["items"][0][0] == "re"})
    return out


def ref_shape(e, fill=None, stroke=None, sw=None, label=None, measure=True, alpha=None):
    """원본 도형 그대로 — 「도형」 도구 + 경로 d(원본 꼭짓점 · 곡선) · 칠 · 칠 불투명 · 선"""
    st = shape(e["x"], e["y"], e["w"], e["h"], fill or "#ffffff", label=label, d=e["d"])
    if not fill:
        st += [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]
    if stroke:
        st += _color("stroke.color", stroke) + [F('#side input[data-a="stroke.w"]', round(sw / MM, 3))]
    st += opacity(alpha)
    if measure:
        o = (sw or 0) / 2
        Ebox(e["x"] - o, e["y"] - o, e["w"] + 2 * o, e["h"] + 2 * o, (mix(fill, "#ffffff", alpha / 100) if alpha and alpha < 100 else fill) or stroke)
    return st


def sp_line(sp, pred):
    """조건에 맞는 원본 글 조각들을 한 줄로(첫 조각 기준선) — 글자마다 끊긴 조각을 잇는다"""
    row = sorted((s for s in sp if pred(s)), key=lambda s: s["x"])
    if not row:
        raise RuntimeError("원본 글 조각 없음")
    return line_of(row, row[0]["base"])


def foot_left(pno, sp):
    """왼쪽 꼬리 — 쪽 번호(책이 채움) · 「|」 · 책 이름(원고 자리 「책 이름」)"""
    st = [S("왼쪽 꼬리 — 쪽 번호 · | · 책 이름", 1000)]
    num = sp_line(sp, lambda s: s["base"] > 200 and s["x"] < 21 and s["size"] == 6.0)
    bar = sp_line(sp, lambda s: s["base"] > 200 and s["text"] == "|")
    book = sp_line(sp, lambda s: s["base"] > 200 and 23 < s["x"] < 60 and s["size"] == 6.0)
    st += T(num, ELICE, 700, label="쪽 번호 — 시스템 자리 「쪽 번호」", w=6, bind="sys.page_no")
    st += T(bar, ELICE, 500, label="|")
    st += T(book, ELICE, 500, label="책 이름 — 원고 자리 「책 이름」", slot_name="책 이름", temp="책 이름", w=30)
    CONTENT.setdefault("책 이름", []).append(book["text"])
    return st


def foot_right(pno, sp):
    """오른쪽 꼬리 — DAY(원고 자리 「꼬리 DAY」) · 「|」 · 쪽 번호(오른쪽 맞춤)"""
    st = [S("오른쪽 꼬리 — DAY · | · 쪽 번호", 1000)]
    dd = sp_line(sp, lambda s: s["base"] > 200 and 100 < s["x"] < 124 and s["size"] == 6.0)
    bar = sp_line(sp, lambda s: s["base"] > 200 and s["text"] == "|")
    num = sp_line(sp, lambda s: s["base"] > 200 and s["x"] > 126 and s["size"] == 6.0)
    st += T(dd, ELICE, 500, label="꼬리 DAY — 원고 자리 「꼬리 DAY」", slot_name="꼬리 DAY", temp="DAY 00", w=round(dd["x1"] - dd["x"] + 3, 1))
    st += T(bar, ELICE, 500, label="|")
    st += T(num, ELICE, 700, label="쪽 번호 — 시스템 자리 「쪽 번호」 (오른쪽 맞춤)", w=6, align="right", bind="sys.page_no")
    CONTENT.setdefault("꼬리 DAY", []).append(dd["text"])
    return st


def side_tab(pno, sp, dr):
    """오른쪽 옆 탭 — 파랑 상자 위에 진한 둥근 탭 · 세로 글 「DAY 31」(원고 자리 「옆 탭」, 90° 돌림). 자리는 첫 견본(DAY 31) —
    DAY 마다 내려가는 자리는 책에서 손보기(인디자인: 상위 페이지 항목 재정의 후 옮기기)"""
    st = [S("옆 탭 — 첫 견본 자리(DAY 마다 다른 자리는 책에서 손보기)", 1200)]
    back = next(e for e in dr if e["x"] > 140 and e["rect"] and e["h"] > 15)
    front = next(e for e in dr if e["x"] > 140 and not e["rect"] and e["h"] > 15)
    st += rbox(back["x"], back["y"], back["w"], back["h"], back["fill"], label="옆 탭 바탕(파랑)")
    st += ref_shape(front, fill=front["fill"], label="옆 탭(진한 둥근 탭)")
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    tab = next((sp_["bbox"], sp_["size"], "#%06x" % sp_["color"], "".join(c["c"] for c in sp_["chars"]))
               for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) if l["dir"] == (0.0, 1.0) for sp_ in l["spans"])
    bb, size, col, txt = tab
    x0, y0, x1, y1 = (bb[0] - t.x0) * MM, (bb[1] - t.y0) * MM, (bb[2] - t.x0) * MM, (bb[3] - t.y0) * MM
    # 90° 돌린 글상자 — 돌리기 전 상자(가로 = 글 길이 · 세로 = 한 줄)를 탭 가운데에 두고 돌린다(편집기 회전은 상자 가운데 기준)
    L, Hh = round(y1 - y0 + 2, 2), round(size * 1.45 * MM, 2)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    st += text(round(cx - L / 2, 2), round(cy - Hh / 2, 2), L, Hh, "DAY 00", size, col, label="옆 탭 글 — 원고 자리 「옆 탭」 · 90° 돌림 · 가운데 맞춤",
               font=ELICE, weight=700, align="center", leading=round(size * 1.45, 2), auto="")
    st += slot("옆 탭") + [F('#side input[data-a="rotate"]', 90, 700)]
    E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2), "color": col, "see": col,
       "ctol": 40, "pad": 1.0, "search": 1.0, "text": txt, "size": size, "원고": True})
    CONTENT.setdefault("옆 탭", []).append(txt.strip())
    return st


def frame_first_left(pno):
    """첫 펼침면 왼쪽 — 높은 띠(왼쪽 아래 곡선) · 어두운 덧띠(28%) · 번호표(흰 칠 + 남색 선, 아래 두 귀 둥글게) · 번호표 옆 그림자 삼각 ·
    「DAY」 · DAY 번호(원고 자리 「DAY 번호」) · 머리 제목(이 면 고정 글) · 왼쪽 꼬리"""
    sp, dr = spans(pno), ref_draws(pno)
    top = [e for e in dr if e["y"] < 8 and e["h"] > 8]
    band = max((e for e in top if e["alpha"] == 100 and e["w"] > 100), key=lambda e: e["w"])
    over = next(e for e in top if e["alpha"] < 100)
    tri = next(e for e in dr if e["w"] < 3 and e["h"] > 6 and e["y"] < 10)
    badge = next(e for e in dr if e["fill"] == "#ffffff" and e["y"] < 10 and e["w"] > 10)
    stroke = next(e for e in dr if e["stroke"] and not e["fill"] and abs(e["x"] - badge["x"]) < 0.3)
    st = [S("첫 펼침면 왼쪽 틀 — 띠 · 덧띠 · 번호표", 1200)]
    st += ref_shape(band, fill=band["fill"], label="높은 띠(왼쪽 아래 곡선)")
    st += ref_shape(over, fill=over["fill"], alpha=over["alpha"], label=f"덧띠 — 불투명 {over['alpha']}%")
    st += ref_shape(tri, fill=tri["fill"], label="번호표 옆 그림자")
    st += ref_shape(badge, fill="#ffffff", stroke=stroke["stroke"], sw=stroke["sw"], label="번호표(흰 칠 · 남색 선 · 아래 두 귀 둥글게)")
    day = sp_line(sp, lambda s: s["text"].replace(" ", "") == "DAY" and s["base"] < 20)
    num = sp_line(sp, lambda s: s["size"] > 15 and s["base"] < 25)
    ttl = sp_line(sp, lambda s: s["size"] == 12.0 and s["base"] < 20)
    st += T(dict(day, text="DAY"), ELICE, 700, label="DAY — Elice DX Neolli Bold (겹침 0.96)")
    st += T(num, BEBAS, 700, label="DAY 번호 — 원고 자리 「DAY 번호」 (가운데 맞춤 · 맞는 서체 없음, 가장 닮은 Bebas Neue Bold)",
            slot_name="DAY 번호", temp="00", align="center", w=round(badge["w"], 2))
    st += [F('#side input[data-it="x"]', round(badge["x"], 2))]          # 번호표 폭에 가운데
    CONTENT.setdefault("DAY 번호", []).append(num["text"])
    st += T(ttl, ELICE, 700, label="머리 제목 — 이 면 고정 글", w=60)
    st += foot_left(pno, sp)
    return st


def frame_first_right(pno):
    """첫 펼침면 오른쪽 — 높은 띠(오른쪽 아래 곡선) · 덧띠(28%) · SANGIL VOCA · 옆 탭 · 오른쪽 꼬리"""
    sp, dr = spans(pno), ref_draws(pno)
    top = [e for e in dr if e["y"] < 8 and e["h"] > 8]
    band = max((e for e in top if e["alpha"] == 100 and e["w"] > 100), key=lambda e: e["w"])
    over = next(e for e in top if e["alpha"] < 100)
    st = [S("첫 펼침면 오른쪽 틀 — 띠 · 덧띠 · SANGIL VOCA · 옆 탭", 1200)]
    st += ref_shape(band, fill=band["fill"], label="높은 띠(오른쪽 아래 곡선)")
    st += ref_shape(over, fill=over["fill"], alpha=over["alpha"], label=f"덧띠 — 불투명 {over['alpha']}%")
    sv = sp_line(sp, lambda s: s["text"].replace(" ", "").startswith("SANGIL"))
    st += T(dict(sv, text="SANGIL VOCA"), ELICE, 700, label="SANGIL VOCA — 고정 글(자간 넓게)")
    st += side_tab(pno, sp, dr)
    st += foot_right(pno, sp)
    return st


def frame_body_left(pno):
    """본문 펼침면 왼쪽 — 얇은 띠 · 띠 아래 파랑 줄 · 원 번호표(흰 칠 + 남색 선) · 번호표 옆 그림자 · DAY 번호(원고 자리 「작은 DAY 번호」) · 왼쪽 꼬리"""
    el, sp, dr = els(pno), spans(pno), ref_draws(pno)
    band, bline = find(el, "rect", -3, -3), find(el, "rect", -3, 4.8)
    tri = next(e for e in dr if e["w"] < 2 and e["h"] > 2 and e["y"] < 5)
    badge = next(e for e in dr if e["fill"] == "#ffffff" and e["y"] < 5 and e["w"] > 5)
    stroke = next(e for e in dr if e["stroke"] and not e["fill"] and abs(e["x"] - badge["x"]) < 0.3)
    st = [S("본문 펼침면 왼쪽 틀 — 얇은 띠 · 원 번호표", 1200)]
    st += rbox(band["x"], band["y"], band["w"], band["h"], band["fill"], label="얇은 띠")
    st += rbox(bline["x"], bline["y"], bline["w"], bline["h"], bline["fill"], label="띠 아래 파랑 줄")
    st += ref_shape(tri, fill=tri["fill"], label="번호표 옆 그림자")
    st += ref_shape(badge, fill="#ffffff", stroke=stroke["stroke"], sw=stroke["sw"], label="원 번호표(흰 칠 · 남색 선)")
    num = sp_line(sp, lambda s: s["size"] == 10.0 and s["base"] < 12)
    st += T(num, BEBAS, 700, label="작은 DAY 번호 — 원고 자리 「작은 DAY 번호」 (Bebas Neue Bold 0.97 · 가운데 맞춤)", slot_name="작은 DAY 번호",
            temp="00", align="center", w=round(badge["w"], 2))
    st += [F('#side input[data-it="x"]', round(badge["x"], 2))]
    CONTENT.setdefault("작은 DAY 번호", []).append(num["text"])
    st += foot_left(pno, sp)
    return st


def frame_body_right(pno):
    """본문 펼침면 오른쪽 — 얇은 띠 · 띠 아래 파랑 줄 · 옆 탭 · 오른쪽 꼬리"""
    el, sp, dr = els(pno), spans(pno), ref_draws(pno)
    band, bline = find(el, "rect", -3, -3), find(el, "rect", -3, 4.8)
    st = [S("본문 펼침면 오른쪽 틀 — 얇은 띠 · 옆 탭", 1200)]
    st += rbox(band["x"], band["y"], band["w"], band["h"], band["fill"], label="얇은 띠")
    st += rbox(bline["x"], bline["y"], bline["w"], bline["h"], bline["fill"], label="띠 아래 파랑 줄")
    st += side_tab(pno, sp, dr)
    st += foot_right(pno, sp)
    return st
