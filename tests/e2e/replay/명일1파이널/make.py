"""명일1 파이널(Vol1) — 「명일1_파이널(Vol1)_내지_인쇄.pdf」(25쪽, 210×297mm · 관리 final/x93773c9f)를 보고 편집기로 손수 만든다.
등록 이름 「명일1 파이널 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」 + CLAUDE.md 「교재 등록 작업표」.
만드는 면 = 사용자가 확인한 면 4개 그대로(구성.json · faces.json) — 왼쪽 · 오른쪽 쪽이 늘 짝인 펼침면 둘.
값(자리 · 크기 · 색)은 모두 목표 PDF(상태.json ref)에서 잰다. 목표 PDF 는 예전 코드(Vivliostyle) 판(글자는 이름 없는 윤곽 Type3).

면(구성.json 번호):
  1 표지 · 4 마지막 면 — 선 · 로고 · 고정 글 · 차례(원고)
  2 지문 펼침면 — 쪽마다 지문 칸 넷(텍스트 프레임 넷, 단 왼쪽 위 → 아래 → 오른쪽 위 → 아래) 한 스레드, 지문마다 다음 프레임에서 시작.
    문장 배열 지문(출처 · (A)… 문장 · 답 줄)과 문장 삽입 · 순서 배열 지문(출처 · 발문 · 주어진 문장 음영 · 본문)이 같은 면.
  3 요약 펼침면 — 쪽마다 지문 하나: 왼쪽 단 빈칸 지문 · 회색 단 정답 지문(같은 스레드, 정답은 다음 프레임에서 시작). 「>> 내용요약」은 고정 개체(줄 위).
  펼침면은 넘치면 같은 펼침면이 다시 붙는다(왼쪽 → 오른쪽 → 왼쪽, 「넘치면 이어 갈 면」을 서로).
서체(fontmatch.py, 후보 = 책 설정 config.json 서체 Noto · Elice Neolli · Jalnan):
  출처 · 머리 번호 · 쪽 번호 · FINAL STEP Elice 700(0.91~0.98) · 머리 제목 Elice 500 0.967 · 탭 글 · 띄운 FINAL STEP Elice 500 0.979 ·
  (A) 기호 · 굵은 글 · 내용요약 Noto 700(0.94 · 0.93) · 영문 본문 Noto 400 0.84(0.9 미만 — 설정 서체 중 가장 닮음, 예전 코드 판 영문 그리기 차이) ·
  발문 Noto 400 0.86 · 표지 차례 번호 Noto 900 0.942 · 차례 글 Noto 500 0.927 · 마지막 면 글은 PDF 에 서체 이름(Elice Md · Lt · Bd).
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
NAME = "명일1 파이널 (편집기 제작)"
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
    st += [S(f"첫 번째 기준선 오프셋 — 고정 {fbo}mm", 700), pick_p("fbo.type", "fixed"), P_("fbo.min", fbo)]
    return st


# ── 공통 머리 · 꼬리 ────────────────────────────────────────────────
def header_left(pno):
    """왼쪽 쪽 머리 — 검은 번호 칸 · 흰 단원 번호 · 단원 제목 · 쪽 너비 선"""
    el, sp = els(pno), spans(pno)
    st = []
    blk = next(e for e in el if (e["k"] == "image" or e.get("fill") == BLACK) and e["y"] < 0 and e["x"] < 20 and e["w"] < 20)   # 검은 칸 — 쪽에 따라 면 또는 그림
    st += rbox(blk["x"], blk["y"], blk["w"], blk["h"], BLACK, label="번호 칸 — 검은 면")
    ln = next(e for e in el if e["k"] == "image" and e["w"] > 200 and 15 < e["y"] < 25)
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], BLACK, label="머리 선 — 쪽 너비(재단선 밖까지)", measure=False)
    Ebox(20.0, ln["y"], 170.0, ln["h"], BLACK, pad=0.3)
    s_no = row_of(sp, 13.04, 0, 30)
    st += T(s_no, ELICE, 700, label="단원 번호 — 원고 자리 「단원번호」 · 러닝 헤드(엘리스 700)", slot_name="단원번호", temp="0", w=10, running=True)
    s_tt = row_of(sp, 15.26, 30, 140)
    st += T(s_tt, ELICE, 500, label="단원 제목 — 원고 자리 「단원」 · 러닝 헤드(엘리스 500)", slot_name="단원", temp="단원 제목", w=80, running=True)
    return st


def header_right(pno):
    """오른쪽 쪽 머리 — 검은 Chapter 탭 · 흰 탭 글(원고) · 띄운 FINAL STEP · 쪽 너비 선"""
    el, sp = els(pno), spans(pno)
    st = []
    tab = next(e for e in el if e["k"] == "image" and e["x"] > 140 and e["y"] < 0)
    st += rbox(tab["x"], tab["y"], tab["w"], tab["h"], BLACK, label="Chapter 탭 — 검은 면")
    ln = next(e for e in el if e["k"] == "image" and e["w"] > 200 and 15 < e["y"] < 25)
    st += rbox(ln["x"], ln["y"], ln["w"], ln["h"], BLACK, label="머리 선 — 쪽 너비(재단선 밖까지)", measure=False)
    Ebox(20.0, ln["y"], 120.0, ln["h"], BLACK, pad=0.3)
    s_ch = row_of(sp, 5.73, 140, W_MM, sep="  ")
    st += T(s_ch, ELICE, 500, label="탭 글 — 원고 자리 「챕터」 · 러닝 헤드(엘리스 500)", slot_name="챕터", temp="Chapter", w=40, running=True)
    s_fs = row_of(sp, 15.62, 140, W_MM, sep="")
    s_fs = dict(s_fs, text="FINAL STEP")
    st += T(s_fs, ELICE, 500, label="FINAL STEP — 고정 글(엘리스 500 · 넓은 자간)", w=46)
    return st


def folio(pno, right):
    """쪽 꼬리 — 쪽 번호(시스템 자리) · 왼쪽: FINAL STEP(고정) · 오른쪽: CHAPTER.01 + 단원(원고 · 러닝 헤드)"""
    sp = [s for s in spans(pno) if s["base"] > 284]
    num = next(s for s in sorted(sp, key=lambda s: s["x"], reverse=right) if s["text"].isdigit())
    st = T(num, ELICE, 700, label="쪽 번호 — 시스템 자리(엘리스 700)", bind="sys.page_no", align="right" if right else None, w=8)
    if not right:
        fs = row_of(sp, num["base"], 12, 60)
        st += T(fs, ELICE, 700, label="FINAL STEP — 고정 글(엘리스 700)", w=22)
        return st
    rest = sorted([s for s in sp if s is not num], key=lambda s: s["x"])
    ch = rest[0]
    nm = line_of(rest[1:], rest[1]["base"])
    whole = dict(ch, x1=nm["x1"], text=ch["text"] + " " + nm["text"], bbox=[ch["bbox"][0], min(ch["bbox"][1], nm["bbox"][1]), nm["bbox"][2], max(ch["bbox"][3], nm["bbox"][3])])
    st += need_cstyle("꼬리 굵게", {"font": ELICE, "weight": 700}, "문자 스타일 「꼬리 굵게」 — 꼬리의 CHAPTER.01(엘리스 700)")
    st += T(whole, ELICE, 500, label="꼬리 — 원고 자리 「챕터번호+단원」(한 줄에 둘) · 러닝 헤드 · 오른쪽 맞춤", slot_name="챕터번호+단원",
            temp="CHAPTER 단원", align="right", w=50, track=False, running=True)
    st += slot_inline("챕터번호", cs="꼬리 굵게", sep=" ")                     # 다음 필드와 같은 단락(한 줄) · 「CHAPTER.01」 은 문자 스타일 「꼬리 굵게」(엘리스 700)
    return st


st = open_doc(NAME)
st += expect_pages(1)

# ── 1 표지 (1쪽) ──
if want(1):
    st += pg_new(1, "① 표지 — 원본 1쪽", name="표지", rep=False)
    el, sp = els(1), spans(1)
    for e in [e for e in el if e["k"] == "rect" and e.get("fill") == BLACK and e["w"] > 100]:
        st += rbox(e["x"], e["y"], e["w"], e["h"], BLACK, label="가로선 — 검은 선")
    info = sorted(REF[0].get_image_info(xrefs=True), key=lambda i: -(i["bbox"][2] - i["bbox"][0]))
    t = REF[0].trimbox
    b = info[0]["bbox"]
    x, y, w, h = round((b[0] - t.x0) * MM, 2), round((b[1] - t.y0) * MM, 2), round((b[2] - b[0]) * MM, 2), round((b[3] - b[1]) * MM, 2)
    path = ref_image(REF, info[0]["xref"], os.path.join(WORK, "표지_로고.png"))
    st += image(x, y, w, h, path, label="FINAL STEP 로고 · 부제 — 원본 그림")
    c = clip({"x": x, "y": y, "w": w, "h": h})
    E({"id": "img0", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": "auto", "see": "auto", "pad": 0.6, "ctol": 30})
    tab = next(e for e in el if e["k"] == "rect" and e.get("fill") == BLACK and e["w"] < 60)
    st += rbox(tab["x"], tab["y"], tab["w"], tab["h"], BLACK, label="Chapter 칸 — 검은 면")
    s_ch = row_of(sp, 200.73, 100, W_MM, sep="  ")
    st += T(s_ch, ELICE, 500, label="Chapter 글 — 원고 자리 「챕터」(엘리스 500)", slot_name="챕터", temp="Chapter", w=40)
    CONTENT["챕터"] = s_ch["text"]
    # 차례 — 원고 자리 「차례」(번호 ⇥ 단원 이름, 단원끼리 빈 줄). 번호는 GREP 스타일로 Noto 900
    rows = sorted({round(s["base"], 2) for s in sp if 205 < s["base"] < 230})
    first = row_of(sp, rows[0], 120, W_MM)
    toc, prev_no = [], None
    for b0 in rows:
        no = [s for s in sp if abs(s["base"] - b0) < 0.2 and s["x"] < 133]
        nm = row_of([s for s in sp if s["x"] >= 133], b0, sep=" ")
        if no and prev_no is not None:
            toc.append("")
        toc.append((no[0]["text"] if no else "") + "\t" + nm["text"])
        prev_no = no[0]["text"] if no else prev_no
    lead = round((rows[1] - rows[0]) / MM, 2)
    tab_at = round(min(s["x"] for s in sp if 205 < s["base"] < 230 and s["x"] >= 133) - first["x"], 2)
    st += need_cstyle("차례 번호", {"font": NOTO, "weight": 900}, "문자 스타일 「차례 번호」 — 표지 차례 번호(Noto 900)")
    st += need_pstyle("차례", {"font": NOTO, "weight": 500, "size": first["size"], "leading": lead, "color": BLACK, "tabs": [{"at": tab_at}],
                              "grep": [(r"^\d+", "차례 번호")]}, "단락 스타일 「차례」 — 번호 ⇥ 단원 이름(번호는 GREP → 문자 스타일)")
    st += text(round(first["x"], 2), round(top_of(rows[0], first["size"], NOTO, 500, lead), 2), 60, round(lead * MM * (len(toc) + 1), 1), "차례",
               first["size"], BLACK, font=NOTO, weight=500, leading=lead, label="차례 — 원고 자리 「차례」")
    st += slot("차례") + [slot_style("차례", "차례")]
    CONTENT["차례"] = "\n".join(toc)
    for b0 in rows:
        r = row_of(sp, b0, 120, W_MM)
        bb = r["bbox"]
        E({"id": f"toc{b0}", "x": round((bb[0] - t.x0) * MM, 2), "y": round((bb[1] - t.y0) * MM, 2), "w": round((bb[2] - bb[0]) * MM, 2),
           "h": round((bb[3] - bb[1]) * MM, 2), "color": BLACK, "see": BLACK, "ctol": 30, "pad": 0.6, "search": 0.6, "원고": True})
    st += done("표지", "p1.png")


PARTN, PART = [0], {}


def group_part(key, n, X0, Y0, w, h):
    """빈 자리(X0, Y0)에 그린 개체 n 개를 범위로 골라 그룹 → 부품, 지면에서는 지운다(부품은 라이브러리에 남는다)"""
    PARTN[0] += 1
    PART[key] = f"p_{PARTN[0]}"
    return [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1000), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
            S(f"범위로 {n}개를 골라 그룹 → 부품", 1200),
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


# ── 2 지문 펼침면 (2 · 3쪽) ──
J_BIND = "출처+발문+주어진문장+본문+문장"
COLW = 83.82                                                             # 단 너비 — 2쪽 왼쪽 단 17.97 ~ 101.79(양쪽 맞춤 줄 끝)
TOP1, TOP2, BOTJ = 26.5, 152.48, 283.0                                   # 칸 위(위 칸 · 아래 칸) · 아래 — 출처 기준선 30.40 · 156.38(쪽마다 같다)
LAB_LEAD = 12.0                                                          # 출처 행간 pt — 한 줄짜리, 아래 몫이 요약 면 출처 → 본문 5.56mm 안에 들게


def j_styles():
    sp2, el8, el2 = spans(2), els(8), els(2)
    lab = row_of(sp2, 30.4, 0, 60)
    L = {"lab": LAB_LEAD, "body": round(4.23 / MM, 2), "ins": round(5.29 / MM, 2)}
    P = {"lab": lp(ELICE, 700, 12, L["lab"]), "body": lp(NOTO, 400, 8.5, L["body"]), "ins": lp(NOTO, 400, 8.5, L["ins"]), "q": lp(NOTO, 400, 8.5, L["body"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    gbox = next(e for e in el8 if e.get("fill") == GRAY_BOX and e["y"] < 60 and e["x"] < 30)
    icon = next(e for e in el2 if e.get("fill") == ICON and e["y"] < 140 and e["x"] < 30)
    rule = next(e for e in el2 if e.get("fill") == RULE and e["y"] < 140 and e["x"] < 30)
    tr = body_track([row_of(sp2, 46.44, 0, 103), row_of(sp2, 70.62, 0, 103)])
    gap1 = 1.0                                                           # 문장끼리 — 5.23 − 4.23(행간)
    after_lab = round(sb(37.98 - 30.4, "lab", "body") - gap1, 2)          # 출처 뒤 공백 — 첫 문장 앞 공백(1mm)과 더해 7.58mm
    st = need_cstyle("기호", {"font": NOTO, "weight": 700}, "문자 스타일 「기호」 — 문장 앞 (A) (B) …(Noto 700)")
    st += need_pstyle("출처", {"font": ELICE, "weight": 700, "size": lab["size"], "leading": L["lab"], "color": BLACK, "keep_next": True, "start": "frame",
                              "space_after": after_lab}, "단락 스타일 「출처」 — 지문 이름(엘리스 700 12pt) · 단락 시작: 다음 프레임")
    st += need_pstyle("발문", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["body"], "color": BLACK, "keep_next": True,
                              "space_before": round(sb(37.98 - 30.4, "lab", "q") - after_lab, 2)}, "단락 스타일 「발문」")
    pt, pb = round(46.81 - P["ins"][0] - gbox["y"], 2), round(gbox["y"] + gbox["h"] - (52.1 + P["ins"][1]), 2)
    st += need_pstyle("주어진 문장", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["ins"], "color": BLACK, "keep_next": True, "align": "left",
                                  "tracking": tr, "indent": 3.0, "indent_right": 3.0, "shade": GRAY_BOX, "shade_ot": pt, "shade_ob": pb, "shade_ol": 3.0,
                                  "shade_or": round(3.0 - (17.97 + COLW - (gbox["x"] + gbox["w"])), 2),
                                  "space_before": sb(46.81 - 37.98, "q", "ins"), "space_after": 0},
                      "단락 스타일 「주어진 문장」 — 회색 음영(단락 음영 · 오프셋)")
    st += need_pstyle("본문", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["ins"], "color": BLACK, "align": "justify", "indent": 1.0, "indent_right": 0.9,
                              "tracking": tr, "space_before": sb(62.58 - 52.1, "ins", "ins"), "grep": [(r"^\([A-Z]\)", "기호")]},
                      "단락 스타일 「본문」 — 삽입 · 순서 지문(행간 15pt · 양쪽 맞춤)")
    st += need_pstyle("문장", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["body"], "color": BLACK, "align": "justify",
                              "tracking": tr, "space_before": gap1, "grep": [(r"^\([A-Z]\)", "기호")]},
                      f"단락 스타일 「문장」 — 배열 지문 (A) … 문장(행간 12pt · 문장마다 1mm · 자간 {tr}‰)")
    J.update(P=P, L=L, icon=icon, rule=rule, before=round(icon["y"] - (123.21 + P["body"][1]), 2))
    return st


J = {}


def j_part():
    """답 줄 그룹 — 원본 2쪽 지문 끝 답 줄(회색 칸 · 흰 ＞ · 밑줄)을 그림(SVG — 원본 도형 그대로)으로 꺼내 + 같은 크기 빈 면 → 그룹 → 부품.
    「문장」 필드 끝에 줄 위 고정 개체로(정본 체크 아이콘과 같은 방식 — 0.17mm 밑줄은 끌어 그리기로 못 그린다)"""
    ic, ru = J["icon"], J["rule"]
    x, y = ic["x"] - 0.2, ic["y"] - 0.2
    w, h = round(ru["x"] + ru["w"] - ic["x"] + 0.4, 2), round(ic["h"] + 0.4, 2)
    path = os.path.join(WORK, "답_줄.svg")
    pdfsvg.export(REF_PATH, 2, round(x, 2), round(y, 2), w, h, path)
    X0, Y0 = 120.0, 3.0
    st = [S("답 줄 그룹 — 원본에서 내보낸 그림 + 같은 크기 빈 면(그룹은 둘 이상)", 1200)]
    st += image(X0, Y0, w, h, path)
    st += box(X0, Y0, w, h, "#ffffff", alpha=0)
    J["before"] = round(J["before"] - 0.2, 2)                            # 그림 위 0.2mm 여유만큼 위로
    return st + group_part("답", 2, X0, Y0, w, h)


def j_frames(cols, head):
    """한 쪽의 지문 칸 넷 — 단 왼쪽 위 · 아래 → 오른쪽 위 · 아래(스레드 차례)"""
    st = []
    fbo = round(30.4 - TOP1, 2)
    for k, (cx, top, bot) in enumerate([(c, t, b) for c in cols for t, b in ((TOP1, TOP2 - 0.5), (TOP2, BOTJ))]):
        first = head and k == 0
        st += frame(round(cx, 2), top, COLW, round(bot - top, 2), fbo, first, "교과서3과 본문1" if first else "이어 받는 칸",
                    "지문 칸 — 스레드 첫 프레임(데이터 필드)" if first else f"지문 칸 {k + 1} — 같은 스레드")
        if first:
            st += slot(J_BIND, label="데이터 필드 — " + J_BIND + " (지문마다 원고에 나온 차례대로 한 줄기)")
            for f, sty in (("출처", "출처"), ("발문", "발문"), ("주어진문장", "주어진 문장"), ("본문", "본문"), ("문장", "문장")):
                st.append(slot_style(f, sty))
            st += [S(f"「문장」 뒤 고정 개체 — 답 줄(줄 위 · 앞 공백 {J['before']}mm)", 900)]
            st += anchor("문장", PART["답"], "above", "end", before=J["before"], after=0, x=0)
            st += new_story()
        else:
            st += same_story()
    return st


if want(2):
    iL = len(PAGES)
    st += pg_new(2, "② 지문 펼침면 — 원본 2쪽 (펼침면 왼쪽)", name="지문 펼침면")
    st += [S("펼침면 상위 페이지 — 2 · 3쪽이 한 레코드(단원 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += j_styles() + j_part()
    st += header_left(2) + folio(2, False)
    st += j_frames((17.97, 104.98), True)
    st += done("지문 펼침면 왼쪽", "p2.png")
    iR = len(PAGES)
    st += pg_new(3, "② 지문 펼침면 — 원본 3쪽 (펼침면 오른쪽)", name="지문 펼침면 오른쪽", rep=True)
    st += header_right(3) + folio(3, True)
    st += j_frames((21.97, 108.99), False)
    st += done("지문 펼침면 오른쪽", "p3.png")
    st += page_cont(iL, "지문 펼침면 오른쪽") + page_cont(iR, "지문 펼침면")
    sys.path.insert(0, HERE)
    import entries as EN
    sp2 = spans(2)
    CONTENT.setdefault("지문 펼침면", []).append({"단원번호": row_of(sp2, 13.04, 0, 30)["text"], "단원": row_of(sp2, 15.26, 30, 140)["text"],
                                             "챕터": row_of(spans(3), 5.73, 140, W_MM, sep="  ")["text"], "챕터번호": "CHAPTER.01",
                                             J_BIND: EN.passages(REF_PATH, [2, 3])})


# ── 3 요약 펼침면 (14 · 15쪽) ──
Y_BIND = "출처+빈칸지문+빈칸요약+정답지문+정답요약"
TOPY = 29.0


def y_styles():
    sp = spans(14)
    L = {"lab": LAB_LEAD, "body": round(7.04 / MM, 2)}
    P = {"lab": lp(ELICE, 700, 12, L["lab"]), "body": lp(NOTO, 400, 8.5, L["body"])}
    sb = lambda gap, a, b: round(max(0.0, gap - P[a][1] - P[b][0]), 2)
    tr = body_track([row_of(sp, 144.44, 0, 103)])
    st = need_cstyle("강조", {"font": NOTO, "weight": 700}, "문자 스타일 「강조」 — 굵은 낱말 · 빈칸 첫 글자(Noto 700)")
    st += need_cstyle("빈칸", {"u": True, "u_w": round(0.17 / MM, 2), "u_off": round(-0.17 / MM, 2)},
                      "문자 스타일 「빈칸」 — 밑줄(반각 공백 몇 개 — 원고가 길이를 정한다)")
    st += need_pstyle("요약 출처", {"font": ELICE, "weight": 700, "size": 12, "leading": L["lab"], "color": BLACK, "keep_next": True, "start": "frame"},
                      "단락 스타일 「요약 출처」 — 지문 이름(엘리스 700 12pt) · 단락 시작: 다음 프레임")
    st += need_pstyle("요약 지문", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["body"], "color": BLACK, "align": "justify", "tracking": tr,
                                 "space_before": sb(38.94 - 33.38, "lab", "body")}, f"단락 스타일 「요약 지문」 — 행간 7.04mm · 양쪽 맞춤 · 자간 {tr}‰")
    st += need_pstyle("요약 정답", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["body"], "color": BLACK, "align": "justify", "tracking": tr, "start": "frame"},
                      "단락 스타일 「요약 정답」 — 회색 단(다음 프레임에서 시작)")
    st += need_pstyle("내용 요약", {"font": NOTO, "weight": 400, "size": 8.5, "leading": L["body"], "color": BLACK, "align": "justify", "tracking": tr},
                      "단락 스타일 「내용 요약」")
    Y.update(P=P, L=L)
    return st


Y = {}


def y_part():
    """「>> 내용요약」 그룹 — 빈 곳에 글 둘 + 투명 면을 그려 범위로 골라 그룹 → 부품(고정 개체로 쓴다)"""
    sp = spans(14)
    a = row_of(sp, 161.07, 0, 24)
    b = row_of(sp, 161.07, 24, 60, sep="")
    X0, Y0 = 120.0, 3.0
    H = 4.5
    base = Y0 + 3.3
    W = round(b["x1"] - a["x"] + 4.0, 2)
    st = [S("「>> 내용요약」 그룹 — 고정 개체로 쓸 부품", 1200)]
    for s_ in (a, b):
        st += text(round(X0 + (s_["x"] - a["x"]), 2), round(top_of(base, 8.5, NOTO, 700), 2), round(s_["x1"] - s_["x"] + 3.0, 2), 4.0, s_["text"], 8.5, BLACK,
                   font=NOTO, weight=700, track=track_of(s_, NOTO, 700, 8.5) or None, auto="")
    st += box(X0, Y0, W, H, "#ffffff", alpha=0)
    Y["part_h"], Y["part_base"] = H, base - Y0
    return st + group_part("요약", 3, X0, Y0, W, H)


def y_frames(c1, c2, w2, head):
    """한 쪽의 요약 칸 둘 — 왼쪽 단(출처 · 빈칸 지문 · 요약) → 회색 단(정답 지문 · 요약)"""
    st = frame(round(c1, 2), TOPY, 83.91, round(BOTJ - TOPY, 2), round(33.38 - TOPY, 2), head, "230934" if head else "이어 받는 칸",
               "요약 왼쪽 단 — 스레드 첫 프레임(데이터 필드)" if head else "요약 왼쪽 단 — 같은 스레드")
    if head:
        st += slot(Y_BIND, label="데이터 필드 — " + Y_BIND)
        for f, sty in (("출처", "요약 출처"), ("빈칸지문", "요약 지문"), ("빈칸요약", "내용 요약"), ("정답지문", "요약 정답"), ("정답요약", "내용 요약")):
            st.append(slot_style(f, sty))
        P, L = Y["P"], Y["L"]
        body_last, head_b, sum_b = 144.44, 161.07, 168.12
        before = round(head_b - Y["part_base"] - (body_last + P["body"][1]), 2)
        after = round(sum_b - P["body"][0] - (head_b - Y["part_base"] + Y["part_h"]), 2)
        for f in ("빈칸요약", "정답요약"):
            st += [S(f"「{f}」 앞 고정 개체 — 「>> 내용요약」 줄 위(앞 공백 {before} · 뒤 공백 {after}mm)", 900)]
            st += anchor(f, PART["요약"], "above", "start", before=before, after=after, x=0)
        st += new_story()
    else:
        st += same_story()
    top2 = round(38.94 - (33.38 - TOPY), 2)
    st += frame(round(c2, 2), top2, w2, round(BOTJ - 4 - top2, 2), round(33.38 - TOPY, 2), False, "이어 받는 칸", "요약 회색 단 — 같은 스레드(정답은 여기서 시작)")
    st += same_story()
    return st


if want(3):
    iL = len(PAGES)
    st += pg_new(14, "③ 요약 펼침면 — 원본 14쪽 (펼침면 왼쪽)", name="요약 펼침면")
    st += [S("펼침면 상위 페이지 — 14 · 15쪽이 한 레코드(단원 하나)", 1000), {"click": "#side #s-spread2", "wait": 1200}]
    st += y_styles() + y_part()
    el = els(14)
    g = next(e for e in el if e["k"] == "image" and e["h"] > 200)
    st += rbox(g["x"], g["y"], g["w"], g["h"], GRAY_COL, label="회색 단 — 정답 바탕")
    st += header_left(14) + folio(14, False)
    st += y_frames(17.97, 106.96, 79.14, True)
    st += done("요약 펼침면 왼쪽", "p14.png")
    iR = len(PAGES)
    st += pg_new(15, "③ 요약 펼침면 — 원본 15쪽 (펼침면 오른쪽)", name="요약 펼침면 오른쪽", rep=True)
    el = els(15)
    g = next(e for e in el if e["k"] == "image" and e["h"] > 200)
    st += rbox(g["x"], g["y"], g["w"], g["h"], GRAY_COL, label="회색 단 — 정답 바탕")
    st += header_right(15) + folio(15, True)
    st += y_frames(21.97, 110.96, 79.14, False)
    st += done("요약 펼침면 오른쪽", "p15.png")
    st += page_cont(iL, "요약 펼침면 오른쪽") + page_cont(iR, "요약 펼침면")
    sys.path.insert(0, HERE)
    import entries as EN
    sp = spans(14)
    CONTENT.setdefault("요약 펼침면", []).append({"단원번호": row_of(sp, 13.04, 0, 30)["text"], "단원": row_of(sp, 15.26, 30, 140)["text"],
                                             "챕터": row_of(spans(15), 5.73, 140, W_MM, sep="  ")["text"], "챕터번호": "CHAPTER.01",
                                             Y_BIND: EN.summaries(REF_PATH, [14, 15])})


# ── 4 마지막 면 (25쪽) ──
if want(4):
    st += pg_new(25, "④ 마지막 면 — 원본 25쪽", name="마지막 면", rep=False)
    el, sp = els(25), spans(25)
    logo = [e for e in el if e["k"] in ("path", "rect", "ellipse") and e.get("fill") == BLACK and e["y"] < 100]
    x0, y0 = min(e["x"] for e in logo), min(e["y"] for e in logo)
    x1, y1 = max(e["x"] + e["w"] for e in logo), max(e["y"] + e["h"] for e in logo)
    st += art(25, round(x0 - 0.3, 2), round(y0 - 0.3, 2), round(x1 - x0 + 0.6, 2), round(y1 - y0 + 0.6, 2), "끝_로고", None, "FINAL STEP 로고 — 원본 도형 그림")
    Ebox(x0, y0, x1 - x0, y1 - y0, BLACK, pad=0.3)                         # 로고 한 그림 — 조각마다 재면 0.25mm 떨어진 조각(STEP 의 P 와 마침표)이 이웃과 붙어 잡힌다
    mk = [e for e in el if e.get("fill") == BLACK and e["y"] > 260 and e["w"] < 10]
    x0, y0 = min(e["x"] for e in mk), min(e["y"] for e in mk)
    x1, y1 = max(e["x"] + e["w"] for e in mk), max(e["y"] + e["h"] for e in mk)
    st += art(25, round(x0 - 0.3, 2), round(y0 - 0.3, 2), round(x1 - x0 + 0.6, 2), round(y1 - y0 + 0.6, 2), "끝_출판사", None, "출판사 로고 — 원본 도형 그림")
    Ebox(x0, y0, x1 - x0, y1 - y0, BLACK, pad=0.3)
    raw = REF[24].get_text("rawdict")["blocks"]
    t = REF[24].trimbox
    for b in raw:
        for l in b.get("lines", []):
            for s0 in l["spans"]:
                ch = [c for c in s0["chars"] if c["c"].strip()]
                if not ch:
                    continue
                wt = 300 if s0["font"].endswith("Lt") else 700 if s0["font"].endswith("Bd") else 500
                s = {"x": (ch[0]["origin"][0] - t.x0) * MM, "base": (s0["origin"][1] - t.y0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                     "size": round(s0["size"], 2), "color": "#%06x" % s0["color"], "text": "".join(c["c"] for c in s0["chars"]).strip(),
                     "bbox": [min(c["bbox"][0] for c in ch), min(c["bbox"][1] for c in ch), max(c["bbox"][2] for c in ch), max(c["bbox"][3] for c in ch)]}
                st += T(s, ELICE, wt, label=f"「{s['text']}」 — 고정 글(엘리스 {wt})", w=round((s["x1"] - s["x"]) * 1.3 + 4, 1))
    st += done("마지막 면", "p25.png")

if CONTENT:
    st += put_content(CONTENT)

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
