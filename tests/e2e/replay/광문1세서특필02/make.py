"""광문1 세서특필02 — 「gold_26-1-기말_광문1_세서특필02_내지.pdf」(110쪽, 210×297mm, 인디자인 판 · 관리 special-lecture/x8a9160ac)를 보고 편집기로 손수 만든다.
등록 이름 「광문1 세서특필02 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 맨 위 「★ 템플릿 등록 — 네 단계」 — 면 11개(구성.json · faces.json, 사용자 확인 2026-10-21).
값(자리 · 크기 · 색 · 서체)은 모두 목표 PDF 에서 잰다. 인디자인 판이라 서체 이름이 PDF 에 있다 — 시스템 서체 그대로
(Noto Sans CJK KR · Pretendard · Elice DX Neolli OTF · Myriad Pro · Ghanachocolate · designhouse OTF · Jalnan OTF · KCCDodamdodam).
시스템에 없는 서체(RixStraight · NIXGON · TTOmniGothic)로 찍힌 몇 글자 장식 제목은 원본 그림으로.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import mkpage
import pymupdf
import pagecmp                                                          # noqa: E402
import pdfsvg                                                           # noqa: E402
mkpage.SPOT = {"mm": [80, 1.5]}                                         # 머리 빈 곳(쪽 위 가운데) — 본문 칸들이 쪽 아래를 덮는다
mkpage.AWAY = {"mm": [205, 294]}
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
W_MM, H_MM = 210.0, 297.0
NAME = "광문1 세서특필02 (편집기 제작)"
NOTO, ELICE = "Noto Sans CJK KR", "Elice DX Neolli OTF"
BLACK, GRAY_BOX, GRAY_COL, ICON, RULE = "#000000", "#e3e3e3", "#efefef", "#999999", "#575757"

ELEMS, PAGES, CONTENT = {}, [], {}
STORY = [0]


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


def line_of(sps, base, tol=0.3, sep=" "):
    """기준선이 같은 조각들을 한 줄로(첫 글자 ~ 끝 글자)"""
    row = sorted([s for s in sps if abs(s["base"] - base) < tol], key=lambda s: s["x"])
    t = row[0]["text"]
    for a, b in zip(row, row[1:]):
        t += (sep if b["x"] - a["x1"] > 0.4 else "") + b["text"]
    bb = [min(s["bbox"][0] for s in row), min(s["bbox"][1] for s in row), max(s["bbox"][2] for s in row), max(s["bbox"][3] for s in row)]
    return dict(row[0], x1=row[-1]["x1"], text=t, bbox=bb)


def row_of(sp, base, x0=0, x1=W_MM, tol=0.3, sep=" "):
    r = [s for s in sp if abs(s["base"] - base) < tol and x0 <= s["x"] < x1]
    return line_of(r, r[0]["base"], sep=sep) if r else None


def lp(fam, wt, size, lead):
    """줄 상자에서 기준선 위 · 아래 몫(mm) — 행간 lead(pt)"""
    asc, desc, _ = face(fam, wt)
    s, L = size * MM, lead * MM
    a = (L - (asc + desc) * s) / 2 + asc * s
    return a, L - a


def pg_new(pno, label, name=None, rep=True):
    """rep — True: 원고마다 · False: 한 번만"""
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label) + [{"click": "#rail .pg.on", "wait": 1500}]
    st += [S(label, 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},
           {"pick": {"at": "#side #s-spec", "value": "a4"}, "wait": 1500}]           # 판형 A4 210×297
    if len(PAGES) == 1 and pno > 1:
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    if name:
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", name, 900)]
    if rep:
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


def T(s, font, weight, size=None, label=None, slot_name=None, temp=None, align=None, w=None, leading=None, h=None, bind=None, measure=True, track=True, running=False):
    """원본 글 조각 하나 — 기준선 = 원본 기준점, 자간은 원본 글자 자리에서. size 를 안 주면 원본 조각 크기"""
    size = size or s["size"]
    tr = track_of(s, font, weight, size) if track else 0
    bw = w or round((s["x1"] - s["x"]) * 1.3 + size * 0.4, 1)
    bh = h or round((leading or size * 1.45) * MM * 1.03, 1)
    top = top_of(s["base"], size, font, weight, leading)
    x = s["x"]
    if align == "right":                                                 # 크롬은 끝 글자 뒤에도 자간을 붙인다 — 그만큼 오른쪽으로
        x = s["x1"] + tr / 1000 * size * MM - bw
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(s["x"], 2), "y": round(s["base"] - size * MM * 0.8, 2), "w": round(s["x1"] - s["x"], 2),
         "h": round(size * MM * 1.05, 2), "color": s["color"], "see": s["color"], "ctol": 24, "pad": 0.6, "search": 0.6, "text": s["text"], "size": size}
    if slot_name or bind:
        m["원고"] = True
    if measure:
        E(m)
    st = text(round(x, 2), round(top, 2), bw, bh, temp if slot_name else s["text"], size, s["color"], label=label, font=font, weight=weight,
              track=tr or None, align=align, leading=leading, bind=bind)
    if slot_name:
        st += slot(slot_name)
    if running:
        st += [{"click": '#side input[data-a="running"]', "wait": 800}]
    return st


def Ebox(x, y, w, h, color, pad=0.6, ctol=30):
    c = clip({"x": x, "y": y, "w": w, "h": h})
    E({"id": f"e{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": color, "see": color, "pad": pad, "ctol": ctol})


def rbox(x, y, w, h, fill, label=None, measure=True):
    st = box(x, y, w, h, fill, label=label)
    if measure:
        Ebox(x, y, w, h, fill)
    return st


def art(pno, x, y, w, h, name, color, label):
    """원본 그림(로고)을 그림 파일(SVG — 원본 도형 그대로)로 꺼내 그 자리에(pdfsvg.py)"""
    path = os.path.join(WORK, f"{name}.svg")
    pdfsvg.export(REF_PATH, pno, x, y, w, h, path)
    if color:
        Ebox(x, y, w, h, color)
    return image(x, y, w, h, path, label=label)


def page_cont(i, target):
    return [S(f"스마트 텍스트 리플로우 — 더할 페이지 「{target}」", 1000), {"click": f'#rail .pg[data-i="{i}"]', "wait": 1500},
            {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, {"pick": {"at": "#side #s-cont", "text": target}, "wait": 900}]


def new_story():
    STORY[0] += 1
    return [S("텍스트 스레드 — 새 스토리(넘친 글은 다음 프레임 · 페이지로)", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]


def same_story():
    return [S("텍스트 스레드 — 같은 스토리를 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": f"이야기{STORY[0]}"}, "wait": 900}]


def frame(x, y, w, h, fbo, head_label, temp, label):
    """본문 텍스트 프레임 — 자리 · 크기 · 첫 번째 기준선 오프셋(고정 — 출처 · 본문 첫 줄 기준선)"""
    st = text(x, y, w, h, temp, 8.5, BLACK, font=NOTO, weight=400, label=label, auto="")
    st += [F('#side input[data-it="y"]', y, 550), F('#side input[data-a="h"]', h, 550)]
    if fbo is not None:
        st += [S(f"첫 번째 기준선 오프셋 — 고정 {fbo}mm", 700), pick_p("fbo.type", "fixed"), P_("fbo.min", fbo)]
    return st


PARTN, PART = [0], {}


def group_part(key, n, X0, Y0, w, h):
    """빈 자리(X0, Y0)에 그린 개체 n 개를 범위로 골라 그룹 → 부품, 지면에서는 지운다(부품은 라이브러리에 남는다)"""
    PARTN[0] += 1
    PART[key] = f"p_{PARTN[0]}"
    return [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1000), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
            S(f"범위로 {n}개를 골라 그룹 → 부품", 1200), {"key": "Escape", "wait": 600},   # 먼저 고른 것을 푼다 — 마지막에 그린 면이 골라진 채면 끌기가 그 면의 모퉁이 손잡이를 잡아 크기를 바꿨다(1개만 잡힘, 2026-10-20 1분 시험)
            {"drag": {"from": {"mm": [X0 - 2, Y0 - 1]}, "to": {"mm": [X0 + w + 2, Y0 + h + 1]}}, "wait": 900},
            {"js": f"(() => {{ if (sels.size !== {n}) throw new Error('고른 것 ' + sels.size + ' ({n} 이어야)'); return '고른 것 {n}'; }})()"},
            {"until": "!!document.querySelector('#side #s-group')", "wait": 400}, {"click": "#side #s-group", "wait": 1500},
            {"until": f"LIB.parts.length && LIB.parts[LIB.parts.length - 1].atoms.length === {n}", "wait": 300},
            {"js": f"(() => {{ const p = LIB.parts[LIB.parts.length - 1]; if (!p || p.atoms.length !== {n}) throw new Error('부품 안 생김'); return '부품 ' + p.id; }})()"},
            S("지면의 그룹은 지운다", 900), {"key": "Delete", "wait": 1200},
            {"drag": {"from": {"mm": [X0 - 2, Y0 - 1]}, "to": {"mm": [X0 + w + 2, Y0 + h + 1]}}, "wait": 900}, {"key": "Delete", "wait": 1200},
            {"js": f"(() => {{ const n = page.items.filter(i => i.x > {X0 - 2} && i.x < {X0 + w + 2} && i.y > {Y0 - 1} && i.y < {Y0 + h + 1}).length; "
                   f"if (n) throw new Error('그룹 자리에 남은 개체 ' + n); return '그룹 자리 비움'; }})()"},
            {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]


def ready(sel, opt=None):
    """그 칸이 화면에 다시 그려질 때까지(칸을 바꿀 때마다 옆 패널이 새로 그려진다 — 컴퓨터가 바쁘면 다음 조작이 옛 칸에 갔다)"""
    q = sel.replace("\\", "\\\\").replace("'", "\\'")
    cond = f"document.querySelector('{q}')" + (f" && [...document.querySelector('{q}').options].some(o => o.value === '{opt}')" if opt else "")
    return {"until": f"!!({cond})", "wait": 400}


def anchor(field, part, pos, at, **o):
    """데이터 필드 고정 개체(slot_anchor 와 같은 칸) — 칸마다 다시 그려질 때까지 기다린 뒤 친다"""
    out = []
    for stp in slot_anchor(field, part, pos, at, **o):
        tgt = (stp.get("pick") or stp.get("fill") or stp.get("click") and {"at": stp["click"]} or {}).get("at")
        if tgt:
            out.append(ready(tgt, (stp.get("pick") or {}).get("value")))
        out.append(stp)
    return out


def body_track(rows):
    """영문 본문 자간 ‰ — 양쪽 맞춤이 아닌 끝 줄(원본 글자 자리)에서 잰 값의 평균"""
    vs = [track_of(r, NOTO, 400, 8.5) for r in rows]
    return round(sum(vs) / len(vs))


GHANA, DESIGN, PRE, MYRIAD, KCC, JALNAN = "Ghanachocolate", "designhouse OTF", "Pretendard", "Myriad Pro", "KCCDodamdodam", "Jalnan OTF"


def pic_notext(pno, x, y, w, h, name, dpi=250):
    """원본 쪽 한 자리를 글 빼고 그림으로(바탕 그림 · 그러데이션 · 도형 그대로) — 글은 편집기 글상자로 따로 만든다"""
    tmp = pymupdf.open()
    tmp.insert_pdf(REF, from_page=pno - 1, to_page=pno - 1)
    p = tmp[0]
    t = p.trimbox
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    p.add_redact_annot(pymupdf.Rect(s["bbox"]))
    p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE, text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    r = pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM)
    path = os.path.join(WORK, f"{name}.png")
    p.get_pixmap(clip=r, dpi=dpi).save(path)
    return path


def page_art(pno, name, label):
    """쪽 전체 바탕(재단선 밖 3mm 까지) — 글 뺀 원본 그림 한 장"""
    path = pic_notext(pno, -3, -3, 216, 303, name)
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", "x": 0, "y": 0, "w": W_MM, "h": H_MM, "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    return image(-3, -3, 216, 303, path, label=label)


st = open_doc(NAME)
st += expect_pages(1)

# ── 1 표지 (1쪽) ──
if want(1):
    st += pg_new(1, "① 표지 — 원본 1쪽", name="표지", rep=False)
    st += page_art(1, "표지", "표지 — 바탕 · 달 · 구름 · 「세서특필」 글씨(원본 그림, 글 없음)")
    st += done("표지", "p1.png")

# ── 2 차례 펼침면 (2 · 3쪽) ──
if want(2):
    st += pg_new(2, "② 차례 펼침면 — 원본 2쪽 (왼쪽)", name="차례 펼침면")
    st += [S("펼침면 상위 페이지 — 2 · 3쪽이 한 레코드(차례)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += page_art(2, "차례_왼쪽", "차례 왼쪽 — 바탕 · 구름 · 로고(원본 그림)")
    sp = spans(2)
    st += T(row_of(sp, 69.24, 0, W_MM), GHANA, 400, label="CONTENTS — 고정 글(가나초콜릿)", w=110)
    st += done("차례 펼침면 왼쪽", "p2.png")
    st += pg_new(3, "② 차례 펼침면 — 원본 3쪽 (오른쪽)", name="차례 펼침면 오른쪽")
    st += page_art(3, "차례_오른쪽", "차례 오른쪽 — 바탕 · 구름 · 세로 선(원본 그림)")
    sp = spans(3)
    rows = sorted({round(s["base"], 1) for s in sp if 80 < s["base"] < 140 and s["size"] > 17})
    first = [s for s in sp if abs(s["base"] - rows[0]) < 0.6]
    lead = round((rows[1] - rows[0]) / MM, 2)
    bar = next(s for s in first if "|" in s["text"])
    strong = next(s for s in first if s["color"] == "#005ead")
    part = min(first, key=lambda s: s["x"])
    st += need_cstyle("차례 파트", {"font": GHANA, "weight": 400, "size": part["size"], "color": part["color"]}, "문자 스타일 「차례 파트」 — 필승법 PART n(가나초콜릿)")
    st += need_cstyle("차례 바", {"color": bar["color"]}, "문자 스타일 「차례 바」 — 「|」 색")
    st += need_cstyle("차례 강조", {"color": strong["color"]}, "문자 스타일 「차례 강조」 — 파트 이름 앞(파랑)")
    st += need_pstyle("차례", {"font": DESIGN, "weight": 300, "size": bar["size"], "leading": lead, "color": "#231f20"}, "단락 스타일 「차례」 — 디자인하우스 19pt · 줄 사이 17.6mm")
    st += text(round(part["x"], 2), round(top_of(rows[0], bar["size"], DESIGN, 300, lead), 2), 130, round(lead * MM * 2 + 2, 1), "차례", bar["size"], "#231f20",
               font=DESIGN, weight=300, leading=lead, label="차례 — 원고 자리 「차례」(파트마다 한 줄 · 꾸밈 조각)")
    st += slot("차례") + [slot_style("차례", "차례")]
    toc = []
    t = REF[2].trimbox
    for b0 in rows:
        r = sorted([s for s in sp if abs(s["base"] - b0) < 0.6], key=lambda s: s["x"])
        seg, x_end = [], None
        for s_ in r:
            cs = "차례 파트" if s_["size"] < bar["size"] - 1 else "차례 바" if "|" in s_["text"] else "차례 강조" if s_["color"] == strong["color"] else None
            if x_end is not None and s_["x"] - x_end > 0.5:                   # 조각 사이 빈 곳 = 띄어쓰기(디자인하우스 19pt 공백 ≈ 1.7mm — 「|」 앞뒤는 여러 칸)
                seg.append(" " * max(1, round((s_["x"] - x_end) / 1.7)))
            seg.append({"t": s_["text"], "cs": cs} if cs else s_["text"])
            x_end = s_["x1"]
        if toc:
            toc.append("\n")
        toc += seg
        bb = [min(s_["bbox"][0] for s_ in r), min(s_["bbox"][1] for s_ in r), max(s_["bbox"][2] for s_ in r), max(s_["bbox"][3] for s_ in r)]
        E({"id": f"toc{b0}", "x": round((bb[0] - t.x0) * MM, 2), "y": round((bb[1] - t.y0) * MM, 2), "w": round((bb[2] - bb[0]) * MM, 2),
           "h": round((bb[3] - bb[1]) * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 0.6, "search": 0.6, "원고": True})
    CONTENT.setdefault("차례 펼침면", []).append({"차례": [toc]})                                                 # 꾸밈 조각 한 벌 — 글 하나 자리에 목록을 그대로 주면 자리마다 하나씩으로 읽는다
    st += done("차례 펼침면 오른쪽", "p3.png")

# ── 3 PART 간지 펼침면 (4 · 5쪽) ──
if want(3):
    st += pg_new(4, "③ PART 간지 펼침면 — 원본 4쪽 (왼쪽)", name="PART 간지 펼침면")
    st += [S("펼침면 상위 페이지 — 4 · 5쪽이 한 레코드(PART 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += page_art(4, "간지_왼쪽", "간지 왼쪽 — 그러데이션 바탕 · 선 · 로고(원본 그림)")
    sp = spans(4)
    st += T(row_of(sp, 34.99, 0, W_MM), GHANA, 400, label="필승법 — 고정 글(가나초콜릿)", w=60)
    st += T(row_of(sp, 54.46, 0, W_MM), GHANA, 400, label="PART — 고정 글(가나초콜릿)", w=60)
    st += T(row_of(sp, 91.72, 0, W_MM), GHANA, 400, label="PART 번호 — 원고 자리 「파트번호」", slot_name="파트번호", temp="00", w=70)
    st += done("PART 간지 왼쪽", "p4.png")
    st += pg_new(5, "③ PART 간지 펼침면 — 원본 5쪽 (오른쪽)", name="PART 간지 펼침면 오른쪽")
    st += page_art(5, "간지_오른쪽", "간지 오른쪽 — 그러데이션 바탕 · 무늬 · 선(원본 그림)")
    sp = spans(5)
    a = row_of(sp, 160.78, 0, 144)
    b = row_of(sp, 160.78, 144, W_MM)
    whole = dict(a, color=b["color"], x1=b["x1"], text=a["text"] + " " + b["text"], bbox=[a["bbox"][0], min(a["bbox"][1], b["bbox"][1]), b["bbox"][2], max(a["bbox"][3], b["bbox"][3])])
    st += need_cstyle("간지 강조", {"color": a["color"]}, "문자 스타일 「간지 강조」 — 파트 이름 앞(파랑)")
    st += T(whole, GHANA, 400, label="PART 이름 — 원고 자리 「파트」(오른쪽 맞춤 · 앞 글은 문자 스타일 「간지 강조」)", slot_name="파트", temp="파트 이름",
            align="right", w=130)
    ELEMS[len(PAGES)][-1].update(color=b["color"], see=b["color"], ctol=60)
    st += done("PART 간지 오른쪽", "p5.png")
    CONTENT.setdefault("PART 간지 펼침면", []).append({"파트번호": row_of(spans(4), 91.72, 0, W_MM)["text"],
                                                    "파트": [[{"t": a["text"], "cs": "간지 강조"}, " " + b["text"]]]})

# ── 11 마지막 면 (110쪽) ──
if want(11):
    st += pg_new(110, "⑪ 마지막 면 — 원본 110쪽", name="마지막 면", rep=False)
    st += page_art(110, "마지막", "마지막 면 — 바탕 · 구름 · 글씨 · 로고(원본 그림, 글 없음)")
    st += done("마지막 면", "p110.png")


# ── 공통 — 본문 쪽 머리 · 꼬리 ──
def pic_box(pno, x, y, w, h, name, label, measure=True):
    """원본 한 자리(글 빼고)를 그림으로 그 자리에 — 둥근 선 머리 · PART 띠처럼 도형 묶음"""
    path = pic_notext(pno, x, y, w, h, name, dpi=400)
    if measure:
        c = clip({"x": x, "y": y, "w": w, "h": h})
        E({"id": f"art{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    return image(x, y, w, h, path, label=label)


def body_head(pno, right, h=20.5):
    """둥근 선 머리 — 도형은 그림, 오른쪽 쪽은 「세/서/특/필」 고정 글"""
    st = pic_box(pno, -3, 7.5, 216, h, f"머리_{'오른쪽' if right else '왼쪽'}_{pno}", "머리 — 둥근 선 · 점(원본 그림)", measure=False)
    E({"id": f"arc{len(ELEMS[len(PAGES)])}", "x": 40.0, "y": 9.0, "w": 120.0, "h": 2.5, "color": "auto", "see": "auto", "pad": 0.4, "ctol": 30})
    if right:
        s = row_of(spans(pno), 16.37, 150, W_MM)
        st += T(s, GHANA, 400, label="세/서/특/필 — 고정 글(가나초콜릿)", w=24)
    return st


def body_foot(pno, right):
    """꼬리 — 쪽 번호(시스템) · 「|」(원본 그림 — NIXGON 은 시스템 서체에 없다) · 왼쪽: 책 이름 원고 + 「세/서/특/필」 · 오른쪽: 파트 꼬리 원고(러닝 헤드)"""
    sp = [s for s in spans(pno) if s["base"] > 278]
    num = next(s for s in sp if s["text"].strip().isdigit())
    bar = next(s for s in sp if "|" in s["text"])
    st = T(num, NOTO, 500, label="쪽 번호 — 시스템 자리(Noto 500)", bind="sys.page_no", align="right" if right else None, w=8)
    bb = bar["bbox"]
    t = REF[pno - 1].trimbox
    st += pic_box(pno, round((bb[0] - t.x0) * MM, 2), round((bb[1] - t.y0) * MM, 2), round((bb[2] - bb[0]) * MM, 2), round((bb[3] - bb[1]) * MM, 2),
                  f"꼬리_막대_{pno}", "「|」 — 원본 그림(NIXGON)", measure=False)
    if right:
        nm = line_of([s for s in sp if s is not num and s is not bar], 281.19, sep=" ")
        nm = dict(nm, text=nm["text"].strip())
        st += T(nm, NOTO, 500, label="꼬리 — 원고 자리 「꼬리」 · 러닝 헤드 · 오른쪽 맞춤(필승법 PART. 01 …)", slot_name="꼬리", temp="필승법 PART 꼬리",
                align="right", w=70, track=False, running=True)
    else:
        rest = sorted([s for s in sp if s["x"] > bar["x1"] - 0.5 and s is not bar], key=lambda s: s["x"])
        bk = dict(rest[0], text=rest[0]["text"].strip())
        st += T(bk, ELICE, 500, label="책 이름 — 원고 자리 「책이름」 · 러닝 헤드(엘리스 500)", slot_name="책이름", temp="책 이름", w=30, running=True)
        ss = dict(rest[1], text=rest[1]["text"].strip())
        st += T(ss, ELICE, 700, label="세/서/특/필 — 고정 글(엘리스 700)", w=14)
    return st


def part_band(pno):
    """PART 띠(단원 첫 쪽 머리) — 띠 · 배지 · 알약은 원본 그림, PA RT 고정 글, 번호 · 이름은 원고"""
    sp = spans(pno)
    st = pic_box(pno, -3, -3, 216, 31.5, f"PART띠_{pno}", "PART 띠 — 바탕 · 배지 · 알약(원본 그림)")
    pa, rt = row_of(sp, 15.16, 25, 40), row_of(sp, 20.1, 25, 40)
    st += T(pa, ELICE, 700, label="PA — 고정 글(엘리스 700)", w=10, measure=False)
    st += T(rt, ELICE, 700, label="RT — 고정 글(엘리스 700)", w=10, measure=False)
    Ebox(pa["x"], pa["base"] - 13 * MM * 0.72, max(pa["x1"], rt["x1"]) - pa["x"], rt["base"] - pa["base"] + 13 * MM * 0.72, "#ffd67d", pad=0.6)
    no = next(s for s in sp if s["base"] < 25 and s["size"] > 20)
    st += T(no, ELICE, 500, label="PART 번호 — 원고 자리 「파트번호」(엘리스 500 흰색)", slot_name="파트번호", temp="00", w=14)
    tt = next(s for s in sp if s["base"] < 25 and 13 < s["size"] < 16)
    st += T(tt, ELICE, 500, label="단원 이름 — 원고 자리 「단원」(엘리스 500)", slot_name="단원", temp="단원 이름", w=100)
    return st


# ── 4 중요문장 첫 펼침면 (6 · 7쪽) · 5 중요문장 본문 펼침면 (8 · 9쪽) ──
S_BIND = "섹션+출처+문장+해석+문법+공식+설명"
SX = {False: 20.0, True: 23.0}                                           # 글상자 왼쪽 — 왼쪽 쪽 · 오른쪽 쪽
SW, SBOT = 167.0, 276.0
SG = {}


def s_styles():
    """중요문장 단락 · 문자 스타일 — 원본 6 · 8쪽에서 잰 값"""
    L = {"sec": 13.2, "tag": 10.8, "en": 14.0, "ko": 13.0, "gr": 13.2, "fo": 13.0}
    P = {"sec": lp(PRE, 400, 11, L["sec"]), "tag": lp(ELICE, 500, 9, L["tag"]), "en": lp(MYRIAD, 400, 10, L["en"]),
         "ko": lp(NOTO, 400, 9, L["ko"]), "gr": lp(PRE, 400, 11, L["gr"]), "fo": lp(ELICE, 500, 9, L["fo"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    en_sb = sb(9.64, "tag", "en")                                        # 출처 → 문장
    X = round(max(0.0, 11.75 - P["ko"][1] - en_sb - P["en"][0]), 2)       # 설명 뒤 공백 — 설명 → 문장
    after_ko = lambda gap, b: round(max(0.0, gap - P["ko"][1] - X - P[b][0]), 2)
    st = need_cstyle("섹션 강조", {"color": "#005ead"}, "문자 스타일 「섹션 강조」 — 단원 띠 앞 글(파랑)")
    # 섹션 띠 — 6쪽 34.37 ~ 43.00 · 기준선 40.08 · 글 32.89
    st += need_pstyle("섹션", {"font": PRE, "weight": 400, "size": 11, "leading": L["sec"], "color": "#231f20", "keep_next": True, "indent": 12.9,
                              "shade": "#d0e9f9", "shade_r": 4.3, "shade_ol": 11.9, "shade_or": -1.0,
                              "shade_ot": round(40.08 - P["sec"][0] - 34.37, 2), "shade_ob": round(34.37 + 8.63 - (40.08 + P["sec"][1]), 2)},
                      "단락 스타일 「섹션」 — 단원 띠(둥근 음영 #d0e9f9)")
    # 출처 꼬리표 — 6쪽 51.00 ~ 56.49 · 기준선 54.54 · 글 23.0 · 꼬리표 21.0 ~ 64.53
    st += need_pstyle("출처", {"font": ELICE, "weight": 500, "size": 9, "leading": L["tag"], "color": "#404041", "keep_next": True, "indent": 3.0,
                              "shade": "#fff1d4", "shade_fit": "1", "shade_ol": 2.0, "shade_or": 2.0,
                              "shade_ot": round(54.54 - P["tag"][0] - 51.0, 2), "shade_ob": round(51.0 + 5.49 - (54.54 + P["tag"][1]), 2),
                              "space_before": after_ko(14.33, "tag")},
                      "단락 스타일 「출처」 — 출처 꼬리표(맞춤 음영 #fff1d4)")
    # 문장 — 영어 · 음영 #f6f5ec(단 너비) · 6쪽 59.23 ~ 66.76 · 기준선 64.18 · 글 22.96 · 출처 → 문장 9.64
    st += need_pstyle("문장", {"font": MYRIAD, "weight": 400, "size": 10, "leading": L["en"], "color": "#231f20", "keep_next": True, "indent": 3.0, "indent_right": 3.0,
                              "shade": "#f6f5ec", "shade_ol": 3.0, "shade_or": 3.0,
                              "shade_ot": round(64.18 - P["en"][0] - 59.23, 2), "shade_ob": round(59.23 + 7.53 - (64.18 + P["en"][1]), 2),
                              "space_before": en_sb},
                      "단락 스타일 「문장」 — 영어(Myriad 10 · 음영 #f6f5ec)")
    st += need_pstyle("해석", {"font": NOTO, "weight": 400, "size": 9, "leading": L["ko"], "color": "#231f20", "keep_next": True, "indent": 3.0, "indent_right": 3.0,
                              "space_before": sb(6.78, "en", "ko")}, "단락 스타일 「해석」 — 우리말(Noto 9)")
    # 문법 이름 — 아래 반 음영 #dde9f7(맞춤) · 6쪽 99.34 ~ 103.97 · 기준선 103.04 · 글 23.97
    st += need_pstyle("문법", {"font": PRE, "weight": 400, "size": 11, "leading": L["gr"], "color": "#231f20", "keep_next": True, "indent": 3.97,
                              "shade": "#dde9f7", "shade_fit": "1", "shade_ol": 1.47, "shade_or": 1.4,
                              "shade_ot": round(103.04 - P["gr"][0] - 99.34, 2), "shade_ob": round(99.34 + 4.63 - (103.04 + P["gr"][1]), 2),
                              "space_before": after_ko(10.49, "gr")}, "단락 스타일 「문법」 — 문법 이름(Pretendard 11 · 아래 반 음영)")
    st += need_pstyle("공식", {"font": ELICE, "weight": 500, "size": 9, "leading": L["fo"], "color": "#005ead", "keep_next": True, "indent": 3.0,
                              "space_before": sb(6.19, "gr", "fo")}, "단락 스타일 「공식」 — <…>(엘리스 500 파랑)")
    st += need_pstyle("설명", {"font": NOTO, "weight": 400, "size": 9, "leading": L["ko"], "color": "#231f20", "indent": 3.0, "indent_right": 3.0, "align": "justify",
                              "space_before": sb(5.84, "fo", "ko"), "space_after": X}, "단락 스타일 「설명」 — 풀이(Noto 9 · 양쪽 맞춤)")
    SG.update(P=P, L=L, sb=sb)
    return st


def s_parts():
    """그룹 둘 — ① 쓰기 칸(파란 테두리 + 연필, 「해석」 끝 줄 위 고정 개체) ② 단원 띠 동그라미(「섹션」 앞 인라인 고정 개체)"""
    X0, Y0 = 20.0, 4.0                                                   # 쓰기 칸 그룹 자리 — 단 너비(167mm)가 쪽 안에 들게(120 에서 끌면 쪽 밖까지 나가 그룹이 안 됐다)
    el = els(8)
    box_ = next(e for e in el if e["k"] == "rect" and e.get("stroke") == "#61c1ed" and e["h"] > 15)
    pen = pic_notext(8, 176.0, box_["y"] - 2.0, 9.0, 6.0, "연필", dpi=600)
    st = [S("쓰기 칸 그룹 — 테두리 상자 + 연필 그림", 1200)]
    st += box(X0, Y0, box_["w"], box_["h"]) + [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]   # 채움 없음
    st += [S("테두리 — 획 #61c1ed 0.5pt", 600)] + mkpage._color("stroke.color", "#61c1ed") + [F('#side input[data-a="stroke.w"]', 0.5)]
    st += image(round(X0 + 176.0 - box_["x"], 2), round(Y0 - 2.0, 2), 9.0, 6.0, pen)
    st += group_part("쓰기", 2, X0, Y0 - 2.0, box_["w"] + 1.0, box_["h"] + 2.0)
    SG["write"] = box_
    # 동그라미 + >
    el6 = els(6)
    c = next(e for e in el6 if e.get("fill") == "#61c1ed" and e["w"] < 10)
    st += [S("단원 띠 동그라미 그룹 — 원 + 「>」", 1200)]
    X0, Y0 = 120.0, 3.0
    st += ellipse(X0, Y0 + 30, c["w"], fill="#61c1ed", h=c["h"])
    g = row_of(spans(6), 40.35, 25, 31)
    st += text(round(X0 + g["x"] - c["x"], 2), round(Y0 + 30 + top_of(g["base"], g["size"], JALNAN, 400) - c["y"], 2), 4.0, 5.0, ">", g["size"], g["color"],
               font=JALNAN, weight=400, auto="")
    st += group_part("섹션", 2, X0, Y0 + 30, c["w"] + 1.0, c["h"] + 1.0)
    SG["circle"] = c
    return st


def s_frames(right, head, top):
    x = SX[right]
    st = frame(x, top, SW, round(SBOT - top, 2), round(40.08 - top, 2) if head else None, head, "중요문장 글" if head else "이어 받는 글상자",
               "중요문장 글상자 — 스레드 첫 프레임(데이터 필드)" if head else "중요문장 글상자 — 같은 스레드")
    if head:
        st += slot(S_BIND, label="데이터 필드 — " + S_BIND + " (문장마다 원고 차례대로 한 줄기)")
        for f, sty in (("섹션", "섹션"), ("출처", "출처"), ("문장", "문장"), ("해석", "해석"), ("문법", "문법"), ("공식", "공식"), ("설명", "설명")):
            st.append(slot_style(f, sty))
        P = SG["P"]
        wb = SG["write"]
        before = round(wb["y"] - (39.05 + P["ko"][1]), 2)
        after = round(71.13 - P["gr"][0] - (wb["y"] + wb["h"]) - SG["sb"](10.49, "ko", "gr"), 2)
        st += [S(f"「해석」 끝 고정 개체 — 쓰기 칸(줄 위 · 앞 공백 {before} · 뒤 공백 {after}mm)", 900)]
        st += anchor("해석", PART["쓰기"], "above", "end", before=before, after=max(after, 0), x=0)
        st += [S("「섹션」 앞 고정 개체 — 동그라미(인라인)", 900)]
        st += anchor("섹션", PART["섹션"], "inline", "start", x=round(SG["circle"]["x"] - x - 12.9, 2), space=True)
        st += new_story()
    else:
        st += same_story()
    return st


if want(4) or want(5):                                                   # 첫 펼침면과 본문 펼침면은 한 스레드 — 늘 같이 만든다(본문 펼침면은 넘친 글을 받는 쪽)
    sys.path.insert(0, HERE)
    import entries as EN
    iL = len(PAGES)
    st += pg_new(6, "④ 중요문장 첫 펼침면 — 원본 6쪽 (왼쪽)", name="중요문장 첫 펼침면")
    st += [S("펼침면 상위 페이지 — 6 · 7쪽이 한 레코드(파트 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += s_styles() + s_parts()
    st += part_band(6) + body_foot(6, False)
    st += s_frames(False, True, 33.5)
    st += done("중요문장 첫 펼침면 왼쪽", "p6.png")
    iR = len(PAGES)
    st += pg_new(7, "④ 중요문장 첫 펼침면 — 원본 7쪽 (오른쪽)", name="중요문장 첫 펼침면 오른쪽")
    st += body_head(7, True) + body_foot(7, True)
    st += s_frames(True, False, 20.5)
    st += done("중요문장 첫 펼침면 오른쪽", "p7.png")
    jL = len(PAGES)
    st += pg_new(8, "⑤ 중요문장 본문 펼침면 — 원본 8쪽 (왼쪽 · 넘친 글을 받는 쪽)", name="중요문장 본문 펼침면", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(8, False) + body_foot(8, False)
    st += s_frames(False, False, 18.5)
    st += done("중요문장 본문 왼쪽", "p8.png")
    jR = len(PAGES)
    st += pg_new(9, "⑤ 중요문장 본문 펼침면 — 원본 9쪽 (오른쪽 · 넘친 글을 받는 쪽)", name="중요문장 본문 펼침면 오른쪽", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(9, True) + body_foot(9, True)
    st += s_frames(True, False, 20.5)
    st += done("중요문장 본문 오른쪽", "p9.png")
    st += page_cont(iR, "중요문장 본문 펼침면") + page_cont(jL, "중요문장 본문 펼침면 오른쪽") + page_cont(jR, "중요문장 본문 펼침면")
    sp6 = spans(6)
    rec = {"파트번호": next(s_ for s_ in sp6 if s_["base"] < 25 and s_["size"] > 20)["text"].strip(),
           "단원": next(s_ for s_ in sp6 if s_["base"] < 25 and 13 < s_["size"] < 16)["text"].strip(),
           "책이름": row_of([s_ for s_ in sp6 if s_["base"] > 278], 280.78, 24, 50.5)["text"].strip(),
           "꼬리": line_of([s_ for s_ in spans(7) if s_["base"] > 278 and s_["x"] < 185], 281.19, sep=" ")["text"].strip()}
    CONTENT.setdefault("중요문장 첫 펼침면", []).append(dict(rec, **{S_BIND: EN.items(REF_PATH, [6, 7, 8, 9])}))


# ── 7 실전문제 첫 펼침면 (42 · 43쪽) · 8 실전문제 본문 펼침면 (44 · 45쪽) ──
Q_BIND = "출처+지시+지문+번호+질문+소문항+보기제목+보기+대화"
QNUM_FONT = "Elice DigitalBaeum OTF"                                     # 문항 번호 — 원본 TTOmniGothic 은 시스템 서체에 없다(fontmatch 0.80 가장 가까움 · 허용)
QG = {}


def q_styles():
    """실전문제 단락 · 문자 스타일 — 원본 42쪽에서 잰 값"""
    L = {"tag": 10.8, "ins": 12.0, "pas": 14.0, "q": 14.5, "sub": 12.0, "box": 12.0, "dia": 13.0}
    P = {"tag": lp(PRE, 400, 9, L["tag"]), "ins": lp(NOTO, 500, 9, L["ins"]), "pas": lp(NOTO, 400, 9, L["pas"]), "q": lp(NOTO, 400, 10, L["q"]),
         "sub": lp(NOTO, 400, 9, L["sub"]), "bt": lp(ELICE, 500, 9, L["box"]), "bx": lp(NOTO, 500, 9, L["box"]), "dia": lp(NOTO, 400, 9, L["dia"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    st = need_cstyle("지시 번호", {"font": ELICE, "weight": 500, "color": "#58595b"}, "문자 스타일 「지시 번호」 — [1~3](엘리스 500 회색)")
    st += need_cstyle("문항 번호", {"font": QNUM_FONT, "weight": 400, "size": 15, "color": "#3c75ba"}, "문자 스타일 「문항 번호」 — 01(15pt 파랑)")
    # 묶음 출처 — 오른쪽 맞춤 · 둥근 맞춤 음영 #e8ecf0 · 아래 경계선 #a5b3c0(단 너비) · 다음 프레임에서 시작
    st += need_pstyle("묶음 출처", {"font": PRE, "weight": 400, "size": 9, "leading": L["tag"], "color": "#6d6e71", "align": "right", "indent_right": 3.0,
                                 "start": "frame", "keep_next": True, "shade": "#e8ecf0", "shade_fit": "1", "shade_r": 2.9, "shade_ol": 1.4, "shade_or": 1.4,
                                 "shade_ot": round(38.19 - P["tag"][0] - 34.17, 2), "shade_ob": round(34.17 + 5.79 - (38.19 + P["tag"][1]), 2)},
                      "단락 스타일 「묶음 출처」 — 오른쪽 위 꼬리표(맞춤 음영)")
    st += need_pstyle("지시", {"font": NOTO, "weight": 500, "size": 9, "leading": L["ins"], "color": "#231f20", "keep_next": True,
                              "rule_above": {"w": 0.5, "color": "#a5b3c0", "offset": round(46.06 - 39.62, 2)},
                              "space_before": sb(46.06 - 38.19, "tag", "ins")}, "단락 스타일 「지시」 — [1~3] 다음 글을 읽고 … · 위 경계선(단 너비 #a5b3c0)")
    # 지문 — 테두리 #b2ddf6 · 42쪽 49.10 ~ 104.72 · 첫 기준선 54.90 · 끝 100.35 · 문단 사이 +1mm
    st += need_pstyle("지문", {"font": NOTO, "weight": 400, "size": 9, "leading": L["pas"], "color": "#231f20", "align": "justify", "indent": 3.0, "indent_right": 2.2,
                              "border": "1", "border_color": "#b2ddf6", "border_ol": 3.0, "border_or": 2.2,
                              "border_ot": round(54.9 - P["pas"][0] - 49.1, 2), "border_ob": round(104.72 - (100.35 + P["pas"][1]), 2),
                              "space_before": sb(54.9 - 46.06, "ins", "pas"), "space_same": round(5.94 - 4.94, 2),
                              "space_after": round(max(0.0, 15.36 - P["pas"][1] - sb(12.71, "sub", "q") - P["q"][0]), 2)},
                      "단락 스타일 「지문」 — 테두리 상자(#b2ddf6)")
    st += need_pstyle("질문", {"font": NOTO, "weight": 400, "size": 10, "leading": L["q"], "color": "#231f20", "keep_next": True,
                              "indent": 11.03, "indent_first": -11.03, "tabs": [{"at": 11.03}], "space_before": sb(12.71, "sub", "q")},
                      "단락 스타일 「질문」 — 번호 ⇥ 질문(내어쓰기 11mm)")
    st += need_pstyle("소문항", {"font": NOTO, "weight": 400, "size": 9, "leading": L["sub"], "color": "#231f20",
                                "space_before": sb(124.83 - 115.71, "q", "sub"), "space_same": round(10.58 - 4.23, 2)}, "단락 스타일 「소문항」 — (A) … ____")
    bx = {"border": "1", "border_color": "#005ead", "border_fit": "1", "border_ol": 3.0, "border_or": 3.0}
    st += need_pstyle("보기 제목", dict(bx, font=ELICE, weight=500, size=9, leading=L["box"], color="#005ead", keep_next=True, indent=3.0,
                                      border_ot=round(172.49 - P["bt"][0] - 167.7, 2), border_ob=0, space_before=sb(172.49 - 163.82, "q", "bt")),
                      "단락 스타일 「보기 제목」 — <보기>(테두리 #005ead 맞춤)")
    st += need_pstyle("보기", dict(bx, font=NOTO, weight=500, size=9, leading=L["box"], color="#231f20", indent=3.0, border_ot=0,
                                   border_ob=round(181.72 - (178.33 + P["bx"][1]), 2), space_before=sb(178.33 - 172.49, "bt", "bx"),
                                   space_after=round(max(0.0, 202.34 - 181.72 - sb(12.71, "sub", "q") - P["q"][0]), 2)),
                      "단락 스타일 「보기」 — 낱말 목록(같은 테두리 상자)")
    st += need_pstyle("대화", {"font": NOTO, "weight": 400, "size": 9, "leading": L["dia"], "color": "#231f20", "indent": 7.0, "indent_first": -4.0,
                              "shade": "#f8f8f1", "shade_ol": 3.0, "shade_or": 0.0,
                              "shade_ot": round(215.38 - P["dia"][0] - 210.59, 2), "shade_ob": 1.2,
                              "space_before": sb(215.38 - 207.46, "q", "dia"), "space_same": round(5.89 - 4.59, 2)},
                      "단락 스타일 「대화」 — 회색 음영 #f8f8f1 · 내어쓰기")
    QG.update(P=P, L=L)
    return st


def q_frames(right, head, top, fbo=None):
    x = SX[right]
    st = frame(x, top, SW, round(SBOT - top, 2), fbo, head, "실전문제 글" if head else "이어 받는 글상자",
               "실전문제 글상자 — 스레드 첫 프레임(데이터 필드)" if head else "실전문제 글상자 — 같은 스레드")
    if head:
        st += slot(Q_BIND, label="데이터 필드 — " + Q_BIND + " (지문 묶음마다 한 줄기 · 묶음은 다음 프레임에서 시작)")
        for f, sty in (("출처", "묶음 출처"), ("지시", "지시"), ("지문", "지문"), ("질문", "질문"), ("소문항", "소문항"),
                       ("보기제목", "보기 제목"), ("보기", "보기"), ("대화", "대화")):
            st.append(slot_style(f, sty))
        st += slot_inline("번호", cs="문항 번호", sep="\t")
        st += new_story()
    else:
        st += same_story()
    return st


if want(7) or want(8):                                                   # 첫 펼침면 · 본문 펼침면은 한 스레드 — 같이 만든다
    sys.path.insert(0, HERE)
    import entries as EN
    iL = len(PAGES)
    st += pg_new(42, "⑦ 실전문제 첫 펼침면 — 원본 42쪽 (왼쪽)", name="실전문제 첫 펼침면")
    st += [S("펼침면 상위 페이지 — 42 · 43쪽이 한 레코드(파트 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += q_styles()
    st += part_band(42) + body_foot(42, False)
    st += q_frames(False, True, 33.5, round(38.19 - 33.5, 2))
    st += done("실전문제 첫 펼침면 왼쪽", "p42.png")
    iR = len(PAGES)
    st += pg_new(43, "⑦ 실전문제 첫 펼침면 — 원본 43쪽 (오른쪽)", name="실전문제 첫 펼침면 오른쪽")
    st += body_head(43, True, 15.4) + body_foot(43, True)
    st += q_frames(True, False, 22.5)
    st += done("실전문제 첫 펼침면 오른쪽", "p43.png")
    jL = len(PAGES)
    st += pg_new(44, "⑧ 실전문제 본문 펼침면 — 원본 44쪽 (왼쪽 · 넘친 글을 받는 쪽)", name="실전문제 본문 펼침면", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(44, False, 15.4) + body_foot(44, False)
    st += q_frames(False, False, 22.5)
    st += done("실전문제 본문 왼쪽", "p44.png")
    jR = len(PAGES)
    st += pg_new(45, "⑧ 실전문제 본문 펼침면 — 원본 45쪽 (오른쪽 · 넘친 글을 받는 쪽)", name="실전문제 본문 펼침면 오른쪽", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(45, True, 15.4) + body_foot(45, True)
    st += q_frames(True, False, 22.5)
    st += done("실전문제 본문 오른쪽", "p45.png")
    st += page_cont(iR, "실전문제 본문 펼침면") + page_cont(jL, "실전문제 본문 펼침면 오른쪽") + page_cont(jR, "실전문제 본문 펼침면")
    sp42 = spans(42)
    CONTENT.setdefault("실전문제 첫 펼침면", []).append({
        "파트번호": next(s_ for s_ in sp42 if s_["base"] < 25 and s_["size"] > 20)["text"].strip(),
        "단원": next(s_ for s_ in sp42 if s_["base"] < 25 and 13 < s_["size"] < 16)["text"].strip(),
        "책이름": "2026 광문고1 서술형 특강",
        "꼬리": line_of([s_ for s_ in spans(43) if s_["base"] > 278 and s_["x"] < 183.5], 281.19, sep=" ")["text"].strip(),
        Q_BIND: EN.sets(REF_PATH, [42, 43, 44, 45])})


# ── 9 정답 첫 펼침면 (94 · 95쪽) · 10 정답 펼침면 (96 · 97쪽) — 두 단 글상자 한 스레드 ──
A_BIND = "세트+번호+정답+해설"
AG = {}


def a_styles():
    """정답 및 해설 단락 · 문자 스타일 — 원본 94 · 96쪽에서 잰 값"""
    L = {"set": 10.8, "no": 18.0, "ans": 12.0, "exp": 12.0}
    P = {"set": lp(PRE, 400, 9, L["set"]), "no": lp(PRE, 400, 15, L["no"]), "ans": lp(NOTO, 400, 8, L["ans"]), "exp": lp(NOTO, 400, 8, L["exp"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    gray = "#58595b"
    st = need_cstyle("세트 번호", {"font": PRE, "weight": 400, "color": "#4791ce"}, "문자 스타일 「세트 번호」 — 1~3(파랑)")
    st += need_cstyle("정답 기호", {"font": PRE, "weight": 600}, "문자 스타일 「정답 기호」 — (A) · ⓐ(Pretendard 600)")
    st += need_cstyle("해설 표", {"font": PRE, "weight": 400, "color": "#1787c8"}, "문자 스타일 「해설 표」 — 「해설」(파랑)")
    marks = [(r"\([A-E]\)", "정답 기호")]
    # 세트 — 음영 #fff5e1(단 너비) · 위 경계선 #ffd67d · 94쪽 37.50 ~ 43.29 · 기준선 41.52 · 글 21.76
    st += need_pstyle("세트", {"font": NOTO, "weight": 400, "size": 9, "leading": L["set"], "color": gray, "keep_next": True, "indent": 1.76,
                              "shade": "#fff5e1", "shade_ol": 1.76, "shade_or": 0,
                              "shade_ot": round(41.52 - P["set"][0] - 37.5, 2), "shade_ob": round(37.5 + 5.79 - (41.52 + P["set"][1]), 2),
                              "rule_above": {"w": 0.5, "color": "#ffd67d", "offset": round(41.52 - 37.6, 2)},
                              "space_before": 6.0}, "단락 스타일 「세트」 — 지문 묶음 꼬리표(음영 #fff5e1 · 위 선)")
    # 번호 — 위 경계선(앞 묶음 · 문항과 가름) · 기준선 위 7.4mm
    st += need_pstyle("문항", {"font": PRE, "weight": 400, "size": 15, "leading": L["no"], "color": "#3c75ba", "keep_next": True,
                              "rule_above": {"w": 0.5, "color": "#ffd67d", "offset": round(50.67 - 43.4, 2)},
                              "space_before": sb(50.67 - 41.52, "set", "no")}, "단락 스타일 「문항」 — 번호(Pretendard 15 · 위 선)")
    st += need_pstyle("정답 줄", {"font": NOTO, "weight": 400, "size": 8, "leading": L["ans"], "color": gray, "keep_next": True, "grep": marks,
                              "space_before": sb(57.71 - 50.67, "no", "ans"), "space_same": 0}, "단락 스타일 「정답 줄」 — (A) 답(Noto 8 · 기호 GREP · 대표유형 「정답」과 한 문서라 이름을 달리)")
    st += need_pstyle("정답 해설", {"font": NOTO, "weight": 400, "size": 8, "leading": L["exp"], "color": gray, "align": "justify", "indent": 6.0, "indent_first": -5.8,
                              "list": {"type": "bullet", "char": "해설", "after": "\t", "cs": "해설 표"}, "grep": marks,
                              "space_before": sb(72.41 - 66.18, "ans", "exp"), "space_after": round(max(0.0, 111.3 - 97.61 - P["exp"][1] - sb(50.67 - 41.52, "set", "no") - P["no"][0]), 2)},
                      "단락 스타일 「정답 해설」 — 「해설」 글머리 · 내어쓰기 6mm")
    AG.update(P=P, L=L)
    return st


def a_frames(right, head, top, fbo=None):
    x = SX[right]
    st = frame(x, top, SW, round(SBOT - top, 2), fbo, head, "정답 해설 글" if head else "이어 받는 글상자",
               "정답 글상자 — 두 단 · 스레드 첫 프레임(데이터 필드)" if head else "정답 글상자 — 두 단 · 같은 스레드")
    st += [S("단 — 두 단 · 간격 5mm", 700), P_("columns", 2, 700), P_("gutter", 5.0, 700)]
    if head:
        st += slot(A_BIND, label="데이터 필드 — " + A_BIND + " (지문 묶음마다 한 줄기)")
        for f, sty in (("세트", "세트"), ("번호", "문항"), ("정답", "정답 줄"), ("해설", "정답 해설")):
            st.append(slot_style(f, sty))
        st += new_story()
    else:
        st += same_story()
    return st


if want(9) or want(10):                                                  # 첫 펼침면 · 정답 펼침면은 한 스레드 — 같이 만든다
    sys.path.insert(0, HERE)
    import entries as EN
    iL = len(PAGES)
    st += pg_new(94, "⑨ 정답 첫 펼침면 — 원본 94쪽 (왼쪽)", name="정답 첫 펼침면")
    st += [S("펼침면 상위 페이지 — 94 · 95쪽이 한 레코드", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += a_styles()
    st += part_band(94) + body_foot(94, False)
    st += a_frames(False, True, 36.0, round(41.52 - 36.0, 2))
    st += done("정답 첫 펼침면 왼쪽", "p94.png")
    iR = len(PAGES)
    st += pg_new(95, "⑨ 정답 첫 펼침면 — 원본 95쪽 (오른쪽)", name="정답 첫 펼침면 오른쪽")
    st += body_head(95, True, 15.4) + body_foot(95, True)
    st += a_frames(True, False, 22.5)
    st += done("정답 첫 펼침면 오른쪽", "p95.png")
    jL = len(PAGES)
    st += pg_new(96, "⑩ 정답 펼침면 — 원본 96쪽 (왼쪽 · 넘친 글을 받는 쪽)", name="정답 펼침면", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(96, False, 7.5) + body_foot(96, False)
    st += a_frames(False, False, 14.5)
    st += done("정답 왼쪽", "p96.png")
    jR = len(PAGES)
    st += pg_new(97, "⑩ 정답 펼침면 — 원본 97쪽 (오른쪽 · 넘친 글을 받는 쪽)", name="정답 펼침면 오른쪽", rep=False)
    st += [{"pick": {"at": "#side #s-rep", "value": "none"}, "wait": 1200}]
    st += body_head(97, True, 15.4) + body_foot(97, True)
    st += a_frames(True, False, 22.5)
    st += done("정답 오른쪽", "p97.png")
    st += page_cont(iR, "정답 펼침면") + page_cont(jL, "정답 펼침면 오른쪽") + page_cont(jR, "정답 펼침면")
    sp94 = spans(94)
    CONTENT.setdefault("정답 첫 펼침면", []).append({
        "파트번호": next(s_ for s_ in sp94 if s_["base"] < 25 and s_["size"] > 20)["text"].strip(),
        "단원": next(s_ for s_ in sp94 if s_["base"] < 25 and 13 < s_["size"] < 16)["text"].strip(),
        "책이름": "2026 광문고1 서술형 특강",
        "꼬리": line_of([s_ for s_ in spans(95) if s_["base"] > 278 and s_["x"] < 183.5], 281.19, sep=" ")["text"].strip(),
        A_BIND: EN.answers(REF_PATH, [94, 95, 96, 97])})


# ── 6 대표유형 펼침면 (36 · 37쪽) — 왼쪽 유형 풀이 · 오른쪽 연습(다음 프레임에서 시작) 한 스레드 ──
T_BIND = "소제목+요약+유형+유형설명+과정제목+단계번호+단계+단계설명+필승+연습+시험+지문+연습문항+해설+표머리+표+풀이+오답제목+오답+정답"
HEAD_FONT = "Elice DigitalBaeum OTF"                                     # 소제목 — 원본 RixStraight 는 시스템 서체에 없다(fontmatch 0.60 가장 가까움 · 허용)
TG = {}


def t_styles():
    """대표유형 단락 · 문자 스타일 — 원본 36 · 37쪽에서 잰 값"""
    L = {"h": 14.4, "sum": 14.0, "type": 13.2, "body": 14.0, "pt": 13.2, "step": 12.0, "tb": 12.0, "ans": 10.0}
    P = {"h": lp(HEAD_FONT, 700, 12, L["h"]), "sum": lp(NOTO, 500, 9, L["sum"]), "type": lp(PRE, 400, 11, L["type"]), "body": lp(NOTO, 400, 9, L["body"]),
         "pt": lp(PRE, 400, 11, L["pt"]), "step": lp(PRE, 400, 10, L["step"]), "md": lp(NOTO, 500, 9, L["body"]), "ex": lp(PRE, 400, 9.5, L["step"]),
         "tag": lp(PRE, 400, 9, 10.8), "tb": lp(NOTO, 400, 9, L["tb"]), "ans": lp(ELICE, 500, 8, L["ans"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    BLUE = "#0075bf"
    st = need_cstyle("연습 번호", {"font": PRE, "weight": 400, "size": 9.5, "color": "#005ead"}, "문자 스타일 「연습 번호」 — 연습 01(파랑)")
    st += need_cstyle("정답 머리", {"font": ELICE, "weight": 500, "color": "#6588c5"}, "문자 스타일 「정답 머리」 — [연습01 정답]")
    st += need_cstyle("풀이 강조", {"font": NOTO, "weight": 500, "u": True, "u_w": 5.0, "u_off": -3.6, "u_color": "#f1f5d5"},
                      "문자 스타일 「풀이 강조」 — 형광펜(굵은 밑줄 #f1f5d5)")
    st += need_cstyle("오답 점", {"color": "#c8da2b"}, "문자 스타일 「오답 점」 — • 연두")
    st += need_pstyle("소제목", {"font": HEAD_FONT, "weight": 700, "size": 12, "leading": L["h"], "color": BLUE, "keep_next": True,
                               "space_before": 6.0}, "단락 스타일 「소제목」 — ☞ · 🔥 · 🔎 머리(파랑)")
    st += need_pstyle("요약", {"font": NOTO, "weight": 500, "size": 9, "leading": L["sum"], "color": "#231f20", "indent": 5.0, "keep_next": True,
                              "shade": "#f1f5d5", "shade_fit": "1", "shade_ol": 0, "shade_or": 0, "shade_ot": round(-(P["sum"][0] - 2.2), 2), "shade_ob": round(-(P["sum"][1] - 0.6), 2),
                              "space_before": sb(44.79 - 38.39, "h", "sum"), "space_same": round(4.94 - 4.94, 2)}, "단락 스타일 「요약」 — 4줄 요약(형광 음영)")
    # 유형 띠 — 둥근 음영 #f0eedf · 36쪽 68.12 ~ 76.75 · 기준선 73.83
    st += need_pstyle("유형", {"font": PRE, "weight": 400, "size": 11, "leading": L["type"], "color": "#231f20", "keep_next": True, "indent": 13.0,
                              "shade": "#f0eedf", "shade_r": 4.3, "shade_ol": 15.0, "shade_or": -2.0,
                              "shade_ot": round(73.83 - P["type"][0] - 68.12, 2), "shade_ob": round(68.12 + 8.63 - (73.83 + P["type"][1]), 2),
                              "space_before": sb(73.83 - 60.02, "sum", "type")}, "단락 스타일 「유형」 — 유형 띠(둥근 음영 #f0eedf)")
    st += need_pstyle("유형설명", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 5.0, "keep_next": True,
                                "space_before": sb(82.54 - 73.83, "type", "body")}, "단락 스타일 「유형설명」")
    st += need_pstyle("과정제목", {"font": PRE, "weight": 400, "size": 11, "leading": L["pt"], "color": "#231f20", "keep_next": True,
                                "shade": "#dde9f7", "shade_fit": "1", "shade_ol": 0.5, "shade_or": 0.5,
                                "shade_ot": round(90.38 - P["pt"][0] - 86.69, 2), "shade_ob": round(86.69 + 4.63 - (90.38 + P["pt"][1]), 2),
                                "space_before": sb(90.38 - 82.54, "body", "pt")}, "단락 스타일 「과정제목」 — 💡 3단계 필승 프로세스(아래 음영)")
    # 단계 — 음영 #dff0fb(단 너비) · 36쪽 95.04 ~ 101.25 · 기준선 99.40 · STEP 칸은 인라인 고정 텍스트 프레임
    st += need_pstyle("단계", {"font": PRE, "weight": 400, "size": 10, "leading": L["step"], "color": "#231f20", "keep_next": True, "indent": 1.0,
                              "shade": "#dff0fb", "shade_ol": 1.0, "shade_or": 0,
                              "shade_ot": round(99.4 - P["step"][0] - 95.04, 2), "shade_ob": round(95.04 + 6.21 - (99.4 + P["step"][1]), 2),
                              "space_before": sb(99.4 - 90.38, "pt", "step")}, "단락 스타일 「단계」 — STEP 띠(음영 #dff0fb)")
    st += need_pstyle("단계설명", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 3.0, "indent_right": 3.0,
                                "border": "0.5", "border_color": "#b2ddf6", "border_ol": 3.0, "border_or": 3.0,
                                "border_ot": round(108.12 - P["body"][0] - 102.33, 2), "border_ob": round(102.33 + 10.18 - (108.12 + P["body"][1]), 2),
                                "space_before": sb(108.12 - 99.4, "step", "body"),
                                "space_after": round(max(0.0, 121.63 - 108.12 - 0 - P["body"][1] - sb(99.4 - 90.38, "pt", "step") - P["step"][0]), 2)},
                      "단락 스타일 「단계설명」 — 테두리 상자 #b2ddf6")
    st += need_pstyle("필승", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 5.0, "align": "justify",
                              "space_before": sb(179.4 - 174.41, "h", "body")}, "단락 스타일 「필승」 — 특별 필승법 글")
    st += need_pstyle("연습", {"font": NOTO, "weight": 500, "size": 9, "leading": L["step"], "color": "#231f20", "start": "frame", "keep_next": True},
                      "단락 스타일 「연습」 — 연습 01 …(다음 프레임에서 시작)")
    st += need_pstyle("시험", {"font": PRE, "weight": 400, "size": 9, "leading": 10.8, "color": "#4791ce", "align": "right", "keep_next": True,
                              "border": "0.5", "border_color": "#61c1ed", "border_fit": "1", "border_r": 1.5, "border_ol": 1.5, "border_or": 1.5,
                              "border_ot": round(33.02 - P["tag"][0] - 29.0, 2), "border_ob": round(29.0 + 5.54 - (33.02 + P["tag"][1]), 2),
                              "space_before": sb(33.02 - 27.19, "ex", "tag")}, "단락 스타일 「시험」 — 시험 꼬리표(오른쪽 · 둥근 테두리 맞춤)")
    st += need_pstyle("연습지문", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "align": "justify", "indent": 3.0, "indent_right": 2.2,
                                "border": "0.5", "border_color": "#61c1ed", "border_ol": 3.0, "border_or": 2.2,
                                "border_ot": round(41.14 - P["body"][0] - 34.35, 2), "border_ob": 3.4,
                                "space_before": sb(41.14 - 33.02, "tag", "body")}, "단락 스타일 「연습지문」 — 테두리 상자 #61c1ed")
    st += need_pstyle("연습문항", {"font": NOTO, "weight": 500, "size": 9, "leading": L["body"], "color": "#231f20",
                                "space_before": round(max(0.0, sb(93.59 - 80.65, "body", "md") - 3.4), 2), "space_same": round(11.59 - 4.94, 2)}, "단락 스타일 「연습문항」 — (A) … ____")
    st += need_pstyle("해설", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 5.0, "align": "justify",
                              "space_before": sb(141.52 - 136.53, "h", "body")}, "단락 스타일 「해설」 — 해설 및 풀이 사고과정 글")
    tabs = [{"at": round(41.8 - 23.0 + 1.0, 2)}, {"at": round(98.49 - 23.0 + 1.0, 2)}, {"at": round(155.18 - 23.0 + 1.0, 2)}]
    st += need_pstyle("표머리", {"font": NOTO, "weight": 400, "size": 9, "leading": L["tb"], "color": "#231f20", "indent": 9.0, "keep_next": True, "tabs": tabs,
                                "shade": "#c9ebfc", "shade_ol": 1.41, "shade_or": 0,
                                "shade_ot": round(156.66 - P["tb"][0] - 152.87, 2), "shade_ob": round(152.87 + 5.17 - (156.66 + P["tb"][1]), 2),
                                "rule_above": {"w": 0.5, "color": "#61c1ed", "offset": round(156.66 - 152.87, 2), "il": 7.59},
                                "space_before": sb(156.66 - 146.46, "body", "tb")}, "단락 스타일 「표머리」 — 표 머리 줄(탭 칸 · 음영 #c9ebfc)")
    st += need_pstyle("표", {"font": NOTO, "weight": 400, "size": 9, "leading": L["tb"], "color": "#231f20", "indent": 9.0, "tabs": tabs,
                            "rule_below": {"w": 0.5, "color": "#61c1ed", "offset": 1.6, "il": 7.59},
                            "space_before": 2.0}, "단락 스타일 「표」 — 표 행(탭 칸 · 아래 선)")
    st += need_pstyle("풀이", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "align": "justify", "indent": 10.0, "indent_first": -4.0,
                              "space_before": sb(188.33 - 182.07, "tb", "body"), "space_same": round(204.15 - 198.21 - 4.94, 2)},
                      "단락 스타일 「풀이」 — (A)는 …(형광 강조 · 내어쓰기)")
    st += need_pstyle("오답제목", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 6.0, "keep_next": True,
                                "space_before": sb(237.66 - 224.9, "body", "body")}, "단락 스타일 「오답제목」 — 🗯 오답 주의")
    st += need_pstyle("오답", {"font": NOTO, "weight": 400, "size": 9, "leading": L["body"], "color": "#231f20", "indent": 15.0, "indent_first": -2.5,
                              "list": {"type": "bullet", "char": "•", "after": "\t", "cs": "오답 점"},
                              "space_before": sb(244.72 - 237.66, "body", "body")}, "단락 스타일 「오답」 — • 연두 글머리")
    st += need_pstyle("정답", {"font": NOTO, "weight": 400, "size": 8, "leading": L["ans"], "color": "#58595b", "align": "right", "grep": [(r"\([A-E]\)", "정답 기호")],
                              "space_before": sb(274.54 - 259.53, "body", "ans")}, "단락 스타일 「정답」 — [연습01 정답] …(오른쪽)")
    if ("c", "정답 기호") not in _DONE:
        st = need_cstyle("정답 기호", {"font": PRE, "weight": 600}, "문자 스타일 「정답 기호」 — (A) · ⓐ(Pretendard 600)") + st
    TG.update(P=P, L=L)
    return st


def t_part():
    """유형 띠 동그라미 그룹 — 노란 원 + 흰 「>」(「유형」 앞 인라인 고정 개체)"""
    el = els(36)
    c = next(e for e in el if e.get("fill") == "#ffd67d" and e["w"] < 10 and e["y"] > 60)
    g = next(s_ for s_ in spans(36) if s_["text"].strip() == ">" and 70 < s_["base"] < 78)
    X0, Y0 = 120.0, 33.0
    st = [S("유형 띠 동그라미 그룹 — 노란 원 + 흰 「>」", 1200)]
    st += ellipse(X0, Y0, c["w"], fill="#ffd67d", h=c["h"])
    st += text(round(X0 + g["x"] - c["x"], 2), round(Y0 + top_of(g["base"], g["size"], JALNAN, 400) - c["y"], 2), 4.0, 5.0, ">", g["size"], "#ffffff",
               font=JALNAN, weight=400, auto="")
    st += group_part("유형", 2, X0, Y0, c["w"] + 1.0, c["h"] + 1.0)
    TG["circle"] = c
    return st


def t_frames(right, head, top, fbo):
    x = SX[right]
    st = frame(x, top, SW, round(SBOT - top, 2), fbo, head, "대표유형 글" if head else "이어 받는 글상자",
               "대표유형 글상자 — 스레드 첫 프레임(데이터 필드)" if head else "대표유형 글상자 — 같은 스레드(연습은 여기서 시작)")
    if head:
        st += slot(T_BIND, label="데이터 필드 — " + T_BIND + " (유형 하나 = 한 줄기 · 연습은 다음 프레임에서)")
        for f in ("소제목", "요약", "유형", "유형설명", "과정제목", "단계", "단계설명", "필승", "연습", "시험", "연습문항", "해설", "표머리", "표", "풀이",
                  "오답제목", "오답", "정답"):
            st.append(slot_style(f, f))
        st.append(slot_style("지문", "연습지문"))
        st += slot_inline("단계번호", sep=" ")
        st += [S("「단계번호」 — 인라인 고정 텍스트 프레임: 칠 #61c1ed · 둥근 모퉁이 · 흰 글", 900),
               {"pick": {"at": '#side select[data-p="slot_fmt.단계번호.cs"]', "value": "단계 칸"}, "wait": 700}] + color_p("slot_fmt.단계번호.frame.fill", "#61c1ed") + [
               P_("slot_fmt.단계번호.frame.r", 1.5, 600), P_("slot_fmt.단계번호.frame.inset", 0.6, 600)]
        st += [S("「유형」 앞 고정 개체 — 노란 동그라미(인라인)", 900)]
        st += anchor("유형", PART["유형"], "inline", "start", x=round(TG["circle"]["x"] - x - 13.0, 2), space=True)
        st += new_story()
    else:
        st += same_story()
    return st


if want(6):
    sys.path.insert(0, HERE)
    import entries as EN
    st += pg_new(36, "⑥ 대표유형 펼침면 — 원본 36쪽 (왼쪽)", name="대표유형 펼침면")
    st += [S("펼침면 상위 페이지 — 36 · 37쪽이 한 레코드(유형 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += need_cstyle("단계 칸", {"font": PRE, "weight": 400, "size": 9, "color": "#ffffff"}, "문자 스타일 「단계 칸」 — STEP n(흰 Pretendard 9)")
    st += t_styles() + t_part()
    st += part_band(36) + body_foot(36, False)
    st += t_frames(False, True, 34.5, round(38.39 - 34.5, 2))
    st += done("대표유형 펼침면 왼쪽", "p36.png")
    st += pg_new(37, "⑥ 대표유형 펼침면 — 원본 37쪽 (오른쪽)", name="대표유형 펼침면 오른쪽")
    st += body_head(37, True, 15.4) + body_foot(37, True)
    st += t_frames(True, False, 22.5, round(27.19 - 22.5, 2))
    st += done("대표유형 펼침면 오른쪽", "p37.png")
    sp36 = spans(36)
    CONTENT.setdefault("대표유형 펼침면", []).append({
        "파트번호": next(s_ for s_ in sp36 if s_["base"] < 25 and s_["size"] > 20)["text"].strip(),
        "단원": next(s_ for s_ in sp36 if s_["base"] < 25 and 13 < s_["size"] < 16)["text"].strip(),
        "책이름": "2026 광문고1 서술형 특강",
        "꼬리": line_of([s_ for s_ in spans(37) if s_["base"] > 278 and s_["x"] < 183.5], 281.19, sep=" ")["text"].strip(),
        T_BIND: [EN.types(REF_PATH, [36, 37])]})                                  # 항목 하나(유형 하나) = [자리, 글] 차례 목록


if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(CONTENT, open(os.path.join(WORK, "원고.json"), "w", encoding="utf-8"), ensure_ascii=False)          # 견본 원고 — 잇기(join.py)가 등록 때 넣는다
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
