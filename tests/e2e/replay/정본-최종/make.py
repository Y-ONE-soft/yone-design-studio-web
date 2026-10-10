"""정본 — 「스텝바이스텝 워크북 정본 (블루·베이지·브릭, A4)」 원본 PDF(274면, 한영1_워크북01(마더텅11강)_내지(수정).pdf)를 보고
편집기로 손수 만든다. 등록 이름 「스텝바이스텝 워크북 정본 (편집기 제작 최종)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」. 이 대본 하나가 문서 하나를 처음부터 만든다 — 구성은 아래 차례대로 하나씩 덧붙인다.
값은 모두 원본 PDF(상태.json ref)에서 잰다. 예전 단위·문서의 결과물은 가져오지 않는다(만드는 방법·도구 함수는 쓴다).
구성마다 「검사 통과」 뒤에 다음 구성. 원고 자리 요소는 elems 에 "원고": true (상태.json 원고_허용_mm 안이면 통과).

구성 차례(원본 구성 판정 — 관리 지면 보기와 같다):
  1 STEPBYSTEP(속표지 1쪽) · 2 STEP 간지(2·124·196쪽) · 3 차례(3·125·197쪽)
  4 A어휘선택(4~23) · 5 A본문OX(24~43) · 6 B본문정리(44~63) · 7 B내용종합(64~83) · 8 C문장배열(84~103) · 9 C빈칸어휘(104~123)
  10 A어법선택(126~145) · 11 B어법OX(146~165) · 12 C빈칸어법(166~185) · 13 C영작배열(186~195)
  14 S실전문제(198~272, 흐르는 쪽 — 고정 부분도 요소 목록에) · 15 MEMO(273) · 16 뒤표지(274)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE                            # 만든 대본·요소 목록·상태를 쓸 곳 — 구성 하나만 돌릴 땐 그 판의 폴더(병렬로 안 섞이게)
ONLY = {x for x in (os.environ.get("GUSEONG") or "").split(",") if x}  # 구성 번호(들)만 — 빈 문서에서 그 구성만 처음부터. 없으면 책 전체


def want(n):
    return not ONLY or str(n) in ONLY
REF = pymupdf.open(os.path.join(REPO, STATE["ref"]))
NAME = "스텝바이스텝 워크북 정본 (편집기 제작 최종)"
ELEMS = {}                                                              # 지면 차례(1부터) → 맞댈 요소
PAGES = []                                                              # 지면 차례 → 원본 쪽 (상태.json pages 로 씀)
CONTENT = {}                                                            # 원고 — 자리 이름 → 원본에서 읽은 글(쪽 차례대로). 끝에 「원고 넣기」로 한 번에
FONTS = os.path.expanduser("~/Library/Fonts")                           # 등록할 서체 파일을 고를 폴더(사람이 파일 창에서 고르는 곳)
import pagecmp                                                          # noqa: E402 — 원본 요소 읽기(눈)
import re as _re                                                        # noqa: E402

MS, NOTO, SUIT = "Montserrat", "Noto Sans CJK KR", "SUIT"


def elems_of(pno):
    """원본 쪽의 요소(면·선·원·글) — 자리·크기는 재단선 기준 mm"""
    return pagecmp.elements(os.path.join(REPO, STATE["ref"]), pno)


def t3k(pno, box):
    """Type3(윤곽) 글의 실제 글자 배율 — 그 서체의 FontMatrix(원본 PDF 값). 없으면 1"""
    p = REF[pno - 1]
    t = p.trimbox
    x, y, w, h = box
    R = pymupdf.Rect(t.x0 + x / MM, t.y0 + y / MM, t.x0 + (x + w) / MM, t.y0 + (y + h) / MM)
    for b in p.get_text("dict", clip=R)["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                m = _re.search(r"\((\d+) 0 R\)", sp["font"])
                if m:
                    fm = _re.search(r"/FontMatrix \[ ([-\d.]+)", REF.xref_object(int(m.group(1))))
                    if fm:
                        return float(fm.group(1)) * 1000
    return 1.0


def pg_new(pno, label):
    """다음 지면 — 첫 지면은 새 문서의 빈 쪽, 그다음은 「＋ 쪽」"""
    PAGES.append(pno)
    ELEMS[len(PAGES)] = []
    st = [] if len(PAGES) == 1 else add_page(label)
    if len(PAGES) == 1 and pno > 1:                                     # 구성 하나만 — 문서 설정 「쪽 번호 시작」을 그 원본 쪽으로(쪽 번호 자리가 원본과 같게)
        st += [S(f"문서 설정 — 쪽 번호 시작 {pno}", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, F("#side #s-pstart", pno, 1200)]
    return st + [S(label, 1300)]


DOC_FONTS = set()


def need_font(fname):
    """서체가 이 문서 판에서 아직 등록 안 됐으면 「＋ 서체」로 등록 — 구성 하나만 돌려도 그 구성이 쓰는 서체를 스스로 갖춘다"""
    if fname in DOC_FONTS:
        return []
    DOC_FONTS.add(fname)
    return register_font(os.path.join(FONTS, fname))


def E(e):
    ELEMS[len(PAGES)].append(e)


def chars_of(pno, e):
    """원본 글 상자 안 글자들(가운데가 상자 안) — 기준점(origin)·상자. 회전 글은 진행 방향으로 늘어놓는다"""
    p = REF[pno - 1]
    t = p.trimbox
    R = pymupdf.Rect(t.x0 + (e["x"] - 0.3) / MM, t.y0 + (e["y"] - 0.3) / MM, t.x0 + (e["x"] + e["w"] + 0.3) / MM, t.y0 + (e["y"] + e["h"] + 0.3) / MM)
    inside = lambda c: e["x"] <= ((c["bbox"][0] + c["bbox"][2]) / 2 - t.x0) * MM <= e["x"] + e["w"] and e["y"] <= ((c["bbox"][1] + c["bbox"][3]) / 2 - t.y0) * MM <= e["y"] + e["h"]
    ch = [dict(c, ox=(c["origin"][0] - t.x0) * MM, oy=(c["origin"][1] - t.y0) * MM)
          for b in p.get_text("rawdict", clip=R)["blocks"] for l in b.get("lines", []) for sp in l["spans"] for c in sp["chars"] if c["c"].strip() and inside(c)]
    return ch


_ELS = {}


def search_of(pno, e, most=1.5):
    """잴 때 둘레를 얼마나 더 볼지(mm) — 기본 1.5, 옆 요소(글·면)가 그보다 가까우면 그 틈의 0.8 (옆 요소 잉크가 섞이지 않게).
    이 요소를 통째로 품은 것(바탕·원 안 숫자의 원)은 옆 요소가 아니다"""
    if pno not in _ELS:                                                  # 옆 요소 = 면·선·원(원본 요소) + 글 조각마다 글자 높이 창(기준선 위 0.95em · 아래 0.3em)
        p, t = REF[pno - 1], REF[pno - 1].trimbox
        boxes = [x for x in elems_of(pno) if onpage(x) and x["k"] != "text"]
        for bl in p.get_text("rawdict")["blocks"]:
            for l in bl.get("lines", []):
                for sp in l["spans"]:
                    ink = [c for c in sp["chars"] if c["c"].strip()]
                    if not ink:
                        continue
                    x0, y0, x1, y1 = sp["bbox"]
                    if l["dir"] == (1.0, 0.0) and not sp["font"].startswith("Type3"):
                        y0, y1 = sp["origin"][1] - 0.95 * sp["size"], sp["origin"][1] + desc_em("".join(c["c"] for c in ink)) * sp["size"]
                    bx = {"x": (x0 - t.x0) * MM, "y": (y0 - t.y0) * MM, "w": (x1 - x0) * MM, "h": (y1 - y0) * MM}
                    if onpage(bx):
                        boxes.append(bx)
        _ELS[pno] = boxes
    els = _ELS[pno]
    gap = most
    for o in els:
        same = abs(o["x"] - e["x"]) < 0.05 and abs(o["y"] - e["y"]) < 0.05 and abs(o["w"] - e["w"]) < 0.05
        if same or (o["x"] <= e["x"] and o["y"] <= e["y"] and o["x"] + o["w"] >= e["x"] + e["w"] and o["y"] + o["h"] >= e["y"] + e["h"]):
            continue
        dx = max(o["x"] - (e["x"] + e["w"]), e["x"] - (o["x"] + o["w"]), 0)
        dy = max(o["y"] - (e["y"] + e["h"]), e["y"] - (o["y"] + o["h"]), 0)
        if max(dx, dy) < gap / 0.8:                                      # 창이 겹치면(글자 높이 창은 넉넉하다) 가장 좁게
            gap = min(gap, round(max(dx, dy) * 0.8, 2))
    return max(gap, 0.2)


def T(e, font, weight, label=None, alpha=None, search=None, ctol=24, align=None, slot_name=None, temp=None, rot=0, s=None, leading=None, bind=None, shift=0, w=None, fold=None):
    """원본 글 하나 — 원본 글자 상자 · 크기 · 색 · 서체 · 굵기. 기준선·첫 글자 자리 = 원본 글자 기준점(origin), 자간은 원본 글자 자리에서.
    align="right" — 오른쪽 끝 = 끝 글자 기준점 + 그 글자 폭 + 자간(브라우저 letter-spacing 은 끝 글자 뒤에도 붙는다).
    slot_name — 원고 자리: 임시 글(temp)을 치고 자리 이름을 단다(원고자리_규약.md). 원본 글은 원고 넣기로 들어온다.
    rot=90 — 세로 글(위→아래로 읽힘) · rot=-90 — 아래→위로 읽힘: 상자를 가로로 그린 뒤 회전 칸에. 회전은 상자 가운데를 축으로.
    bind — 시스템 자리(sys.page_no 쪽 번호 등)를 「원고 자리」 목록에서 고른다. 글은 원본 글(그 자리를 책이 채운다).
    shift — 그리는 자리만 위로(mm): 위 글상자가 견본 원고만큼 자라 밀어 줄 양(설계 = 최소 높이). 재는 자리는 원본 그대로.
    w — 상자 폭(없으면 글 폭에 맞춰). fold — 접기 묶음 이름(원고가 비우면 묶음째 접힌다)."""
    pno = PAGES[-1]
    s = s or e["text"]
    search = search if search is not None else search_of(pno, e)          # pad = 원본·결과 둘 다 이만큼 둘레까지 본다(pagecmp.measure)
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"], "color": e["color"],
         "see": "auto" if alpha else e["color"], "ctol": ctol, "pad": search, "search": search, "text": s, "size": e["size"]}
    if slot_name:
        m["원고"] = True
    E(m)
    size = round(e["size"] * t3k(pno, (e["x"], e["y"], e["w"], e["h"])), 3)
    ch = sorted(chars_of(pno, e), key=lambda c: (c["oy"], c["ox"]) if rot == 90 else (-c["oy"], c["ox"]) if rot == -90 else (c["ox"], c["oy"]))
    if not ch:
        raise RuntimeError(f"원본 글자 못 찾음: {s}")
    ox, oy = ch[0]["ox"], ch[0]["oy"]
    track = 0
    if len(s) > 1 and len(ch) > 1:
        orig = abs(ch[-1]["oy"] - ch[0]["oy"]) if rot else (ch[-1]["ox"] - ch[0]["ox"])
        track = round((orig - chrome_extent(font, weight, size, s)) / (len(s) - 1) / (size * MM) * 1000)
    length = (e["h"] if rot else e["w"])
    bw = w or round(length * 1.25 + size * 0.35, 1)
    bh = round((leading or size * 1.45) * MM * 1.03, 1)                     # 한 줄 높이(행간)보다 조금 크게 — 면 밖으로 처지지 않게
    if rot:                                                              # 회전 전 상자에서 기준선까지 b — 돌린 뒤 첫 글자 기준점이 원본 기준점에 오게 가운데를 푼다
        b = oy - top_of(oy, size, font, weight, leading)
        cx, cy = (ox + b - bh / 2, oy + bw / 2) if rot == 90 else (ox - b + bh / 2, oy - bw / 2)
        x, top = cx - bw / 2, cy - bh / 2
    else:
        x, top = ox, top_of(oy, size, font, weight, leading)
        if align == "right":
            right = ox + chrome_extent(font, weight, size, s) + len(s) * track / 1000 * size * MM + face(font, weight)[2](s[-1]) * size * MM
            x = right - bw
    st = text(round(x, 2), round(top - shift, 2), bw, bh, temp if slot_name else s, size, e["color"], label=label, font=font, weight=weight,
              track=track or None, alpha=alpha, align=align, leading=leading, bind=bind)
    if rot:
        st.append(F('#side input[data-a="rotate"]', rot))
    if slot_name:
        st += slot(slot_name)
    if fold:
        st.append(F('#side input[data-a="fold"]', fold))
    return st


def desc_em(s):
    """글이 기준선 아래로 내려가는 깊이(em) — 내림 글자(g j p q y · 괄호 · 쉼표)나 한글·기호가 있으면 0.3, 숫자·대문자뿐이면 0.08.
    잴 창을 글자 모양에 맞춰 아래 줄 글자 가장자리(회색)가 섞이지 않게"""
    return 0.08 if all(c.isspace() or (c.isascii() and (c.isdigit() or c.isupper() or c in ".:-'\"!?&%#+=")) for c in s) and "Q" not in s else 0.3


def span_el(pno, text, nth=0, size=None):
    """원본 쪽에서 글 조각(span) 하나 — 줄로 묶인 요소(elements)에서 서체가 다른 조각을 떼어 잴 때. 글자 상자 = 조각 상자"""
    p = REF[pno - 1]
    t = p.trimbox
    got = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                if "".join(c["c"] for c in sp["chars"]).strip() == text and (size is None or round(sp["size"], 1) == size):
                    x0, y0, x1, y1 = sp["bbox"]
                    if not sp["font"].startswith("Type3") and l["dir"] == (1.0, 0.0):   # 보통 서체 조각 상자는 줄 높이째(영도 12pt = 16mm) — 잴 창을 글자 높이로:
                        b = sp["origin"][1]                                               # 기준선 위 0.95em · 아래 0.3em (옆 줄 글자 가장자리가 섞이지 않게)
                        y0, y1 = b - 0.95 * sp["size"], b + desc_em(text) * sp["size"]
                    got.append({"k": "text", "text": text, "x": round((x0 - t.x0) * MM, 2), "y": round((y0 - t.y0) * MM, 2), "w": round((x1 - x0) * MM, 2),
                                "h": round((y1 - y0) * MM, 2), "size": round(sp["size"], 1), "color": "#%06x" % sp["color"], "font": sp["font"]})
    got = [g for g in got if onpage(g)]
    return got[nth]


def onpage(e):
    return e["x"] < 210 and e["x"] + e["w"] > 0 and e["y"] < 297 and e["y"] + e["h"] > 0


def clip(e):
    """재단선 안 부분 — 재단 여백까지 그린 면은 보이는 데만 잰다"""
    x0, y0, x1, y1 = max(e["x"], 0), max(e["y"], 0), min(e["x"] + e["w"], 210), min(e["y"] + e["h"], 297)
    return dict(e, x=round(x0, 2), y=round(y0, 2), w=round(x1 - x0, 2), h=round(y1 - y0, 2))


def B(e, label=None, measure=True):
    if measure:
        c = clip(e)
        E({"id": f"b{len(ELEMS[len(PAGES)])}", "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"], "color": e["fill"],
           "see": "auto" if e.get("opacity") else e["fill"], "pad": 0.6, "ctol": 30})
    return box(e["x"], e["y"], e["w"], e["h"], e["fill"], label=label, alpha=e.get("opacity"))


def Cfill(e):
    E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"], "color": e["fill"], "see": e["fill"], "pad": 0.6, "ctol": 30})
    return ellipse(e["x"], e["y"], e["w"], fill=e["fill"], h=e["h"])


def Cring(e, alpha=None):
    """테두리만 있는 원 — 원본 경로 상자(획 가운데) 그대로 그리고 획 굵기. 재는 상자는 획 바깥까지"""
    sw = e["sw"]
    E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(e["x"] - sw / 2, 2), "y": round(e["y"] - sw / 2, 2), "w": round(e["w"] + sw, 2), "h": round(e["h"] + sw, 2),
       "color": e["stroke"], "see": "auto" if alpha else e["stroke"], "pad": 0.6, "ctol": 30})
    return ellipse(e["x"], e["y"], e["w"], stroke=e["stroke"], sw=round(sw / MM, 2), h=e["h"], alpha=alpha)      # 편집기 획 두께는 pt


def poly_d(pno, e):
    """원본 다각형(선 여럿) → 「경로 d」 (상자 0~1 비율) — 꼬리표처럼 비스듬한 면"""
    p = REF[pno - 1]
    t = p.trimbox
    for d in p.get_drawings():
        r = d["rect"]
        if abs((r.x0 - t.x0) * MM - e["x"]) < 0.05 and abs((r.y0 - t.y0) * MM - e["y"]) < 0.05 and d["items"] and d["items"][0][0] == "l":
            pts = [d["items"][0][1]] + [it[2] for it in d["items"]]
            fx = lambda v: (v.x - r.x0) / r.width
            fy = lambda v: (v.y - r.y0) / r.height
            return "M" + " L".join(f"{fx(v):.4f} {fy(v):.4f}" for v in pts[:-1]) + " Z"
    raise RuntimeError("다각형 못 찾음")


st = open_doc(NAME)
st += expect_pages(1)

# ── 구성 1 「STEPBYSTEP」 속표지 (원본 1쪽) ───────────────────────
if want(1):
    st += pg_new(1, "① 속표지 — 원본 1쪽")
    el = elems_of(1)
    rects = [e for e in el if e["k"] == "rect"]
    texts = {(e["text"], round(e["y"])): e for e in el if e["k"] == "text"}
    tx = lambda s, i=0: [e for e in el if e["k"] == "text" and e["text"] == s][i]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "왼쪽 파란 막대")
    tag = rects[2]
    E({"id": "tag", "x": tag["x"], "y": tag["y"], "w": round(210 - tag["x"], 2), "h": tag["h"], "color": tag["fill"]})
    st += shape(tag["x"], tag["y"], tag["w"], tag["h"], tag["fill"], d=poly_d(1, tag), label="오른쪽 위 꼬리표 — 원본 꼭짓점 그대로")
    st += T(tx("STEP BY STEP"), MS, 700, label="꼬리표 글 — Montserrat Bold (작은 글은 잉크 양으로 굵기)", search=0.25, ctol=12)
    st += [S("서체 등록 — 시스템에 없는 서체(원본 글자 모양으로 찾음): Montserrat ExtraBold, SUIT Regular", 1500)]
    st += need_font("Montserrat-ExtraBold.otf")
    st += need_font("SUIT-Regular.otf")
    st += T(tx("STEP", 0), MS, 800, label="큰 제목 — Montserrat ExtraBold")
    st += T(tx("BY"), MS, 800)
    st += T(tx("STEP", 1), MS, 800)
    st += B(rects[3], "밑줄 두 겹")
    st += B(rects[4])
    st += T(tx("스텝바이스텝 워크북"), SUIT, 400, label="한글 제목 — SUIT Regular")
    st += T(tx("MOCK TEST · WORKBOOK"), MS, 700)
    mask = [e for e in el if e["k"] == "rect" and e["fill"] == "#faf7f0" and e["w"] < 10][0]
    st += B(mask, "가림 면(원본 그대로 — 바탕색)", measure=False)
    st += [S("단계 셋 — 원 · 선 · 숫자 · 라벨", 1500)]
    for e in [e for e in el if e["k"] == "path" and abs(e["w"] - 11.12) < 0.1]:
        st += Cfill(e)
    for e in [e for e in rects if abs(e["y"] - 178.59) < 0.1]:
        st += B(e)
    for n in ("1", "2", "3"):
        st += T(tx(n), MS, 800, search=0.6)
    for lb in ("FRAME", "BUILD UP", "TEST"):
        st += T(tx(lb), MS, 700, search=1.2)
    st += [S("아래 색 점 셋", 1200)]
    for e in [e for e in rects if abs(e["y"] - 259.06) < 0.1]:
        st += B(e)
    logo = [e for e in el if e.get("fill") == "#2c292a"]
    lx0, ly0 = min(e["x"] for e in logo), min(e["y"] for e in logo)
    lx1, ly1 = max(e["x"] + e["w"] for e in logo), max(e["y"] + e["h"] for e in logo)
    E({"id": "logo", "x": round(lx0, 2), "y": round(ly0, 2), "w": round(lx1 - lx0, 2), "h": round(ly1 - ly0, 2), "color": "#2c292a"})
    st += image(25.6, 270.6, 31.8, 8.6, os.path.join(HERE, "logo.svg"), label="로고 — 원본에서 내보낸 그림 파일(logo.svg)을 올린다")
    st += done("속표지", "p1.png")

# ── 구성 2 「STEP 간지」 (원본 2쪽 — STEP 01. STEP 02·03 간지는 그 STEP 차례에서 이 쪽을 복제해 색·번호를 바꾼다) ──
if want(2):
    st += pg_new(2, "② STEP 간지 — 원본 2쪽 (STEP 01)")
    st += need_font("Montserrat-ExtraBold.otf")
    el = [e for e in elems_of(2) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    tx = lambda s, i=0: [e for e in el if e["k"] == "text" and e["text"] == s][i]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "위 크림 띠")
    st += B(rects[2], "띠 아래 선")
    st += B(rects[3], "왼쪽 위 세로 막대")
    st += T(tx("STEP"), MS, 700, label="STEP — Montserrat Bold (불투명 80%, 굵기는 잉크 양으로)", alpha=tx("STEP").get("opacity"), search=0.6)
    st += T(tx("01"), MS, 800, label="STEP 번호 — Montserrat ExtraBold")
    st += [S("단계 셋 — 원(지금 단계는 채움) · 선 · 숫자 · 라벨", 1500)]
    paths = [e for e in el if e["k"] == "path"]
    st += Cfill(paths[0])
    for e in paths[1:]:
        st += Cring(e, alpha=e.get("opacity"))
    for e in rects[4:]:
        st += B(e)
    for n in ("1", "2", "3"):
        st += T(tx(n), MS, 800, alpha=tx(n).get("opacity"), search=0.6)
    for lb in ("FRAME", "BUILD UP", "TEST"):
        st += T(tx(lb), MS, 700, alpha=tx(lb).get("opacity"), search=1.2)
    st += T(tx("STEP BY STEP"), MS, 800, label="아래 STEP BY STEP (불투명 90%)", alpha=tx("STEP BY STEP").get("opacity"))
    st += done("STEP 간지", "p2.png")

# ── 구성 3 「차례」 (원본 3쪽 — STEP 01) ── 교재 이름 · 단원은 원고 자리(책마다 바뀐다)
if want(3):
    st += pg_new(3, "③ 차례 — 원본 3쪽 (STEP 01)")
    st += need_font("Montserrat-ExtraBold.otf")
    el = [e for e in elems_of(3) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    tx = lambda s, i=0: [e for e in el if e["k"] == "text" and e["text"] == s][i]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "위 크림 띠")
    st += B(rects[2], "띠 아래 선")
    st += [S("오른쪽 STEP 탭 셋 — 지금 STEP 은 진하게", 1300)]
    for e in rects[3:]:
        st += B(e)
    big = tx("01")
    st += T(big, MS, 800, label="큰 STEP 번호 — 바탕에 옅게(불투명 14%) · 행간 = 글 크기(상자가 면 안에)", alpha=big.get("opacity"), leading=round(big["size"] * t3k(3, (big["x"], big["y"], big["w"], big["h"])), 3))
    st += T(tx("01EPST"), MS, 700, label="탭 글 — 세로(90° 회전)", rot=90, s="STEP 01", search=0.6, alpha=tx("01EPST").get("opacity"))
    st += T(tx("02"), MS, 700, rot=90, search=0.6, alpha=tx("02").get("opacity"))
    st += T(tx("03"), MS, 700, rot=90, search=0.6, alpha=tx("03").get("opacity"))
    title, unit = tx("마더텅 고1 영어 독해"), tx("11강")
    st += T(title, "Gmarket Sans", 500, label="교재 이름 — 원고 자리 「교재명」 (오른쪽 맞춤)", align="right", slot_name="교재명", temp="교재 이름")
    st += T(unit, "Gmarket Sans", 700, label="단원 — 원고 자리 「단원명」 (오른쪽 맞춤)", align="right", slot_name="단원명", temp="00강")
    CONTENT["교재명"] = CONTENT.get("교재명", []) + [title["text"]]
    CONTENT["단원명"] = CONTENT.get("단원명", []) + [unit["text"]]
    st += done("차례", "p3.png")

# ── 본문 지문 공통 (구성 4~13) ── 지문 = 원고 자리, 글은 원고로. 값은 원본 PDF 에서 잰다
NOTO, YD, EL, GMK, MAMA = "Noto Sans CJK KR", "Yeongdo OTF", "Elice DX Neolli OTF", "Gmarket Sans", "NUXZQS+TTMamablockB"
BODY, LEAD, TRACK_BODY = 8.5, 22, -40          # 지문 8.5pt · 행간 22pt(기준선 7.76mm) · 자간 −40 (원본 영문 글자 2만5천 쌍 중앙값, 공백 빼고)
BLUE_B = "#00559f"                             # [ ⓐ … / ⓑ … ] 굵은 파랑
TEMP = ("Temporary text for styling. A [ ⓐ word / ⓑ phrase ] sits in the line, and the passage keeps [ ⓐ going / ⓑ moving ] "
        "until the real content arrives from outside. ")


def temp_passage(n):
    """지문 자리의 임시 글 — 올 원고의 꼴([ ⓐ … / ⓑ … ] 이 섞인 영어 문단)을 흉내 낸다. 길이는 원본과 비슷하게"""
    return (TEMP * (n // len(TEMP) + 1))[:n].rsplit(" ", 1)[0] + "."


def passages(pno, size=BODY):
    """원본 쪽의 지문(그 크기 글 줄들) — 기준선 간격이 10mm 넘게 벌어지는 곳에서 나눈다.
    → [{x, base0, base1, text, top, bottom, right, lines}] · text = 원고(줄 나눔 없이 — 줄 끝 '-'(합성어)는 붙이고 나머지는 띄어 잇는다)"""
    p = REF[pno - 1]
    t = p.trimbox
    rows = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            sp = [x for x in l["spans"] if round(x["size"], 1) == size]
            ch = [c for x in sp for c in x["chars"]]
            ink = [c for c in ch if c["c"].strip()]
            if not ink or (ink[0]["origin"][0] - t.x0) * MM > 210:
                continue
            rows.append({"base": (ink[0]["origin"][1] - t.y0) * MM, "x": (ink[0]["origin"][0] - t.x0) * MM, "s": "".join(c["c"] for c in ch),
                         "top": (sp[0]["bbox"][1] - t.y0) * MM, "bottom": (sp[0]["bbox"][3] - t.y0) * MM, "right": (ink[-1]["bbox"][2] - t.x0) * MM})
    rows.sort(key=lambda r: r["base"])
    groups, cur = [], []
    for r in rows:
        if cur and r["base"] - cur[-1]["base"] > 10:
            groups.append(cur); cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        txt = ""
        for r in g:
            line = r["s"].strip()
            txt += line if (not txt or txt.endswith("-")) else " " + line
        out.append({"x": g[0]["x"], "base0": g[0]["base"], "base1": g[-1]["base"], "text": txt, "top": g[0]["top"], "bottom": g[-1]["bottom"],
                    "right": max(r["right"] for r in g), "lines": len(g)})
    return out


def P(ps, limit, label):
    """지문 한 덩어리 — 글상자(원고 자리 「지문」)에 임시 글, 양끝맞춤 · 행간 22pt · 자간 −40 · 균등 배치, GREP 스타일로 [ ⓐ … / ⓑ … ] 만 굵은 파랑.
    상자 = 첫 줄 위 끝 ~ limit(다음 것 바로 위) — 원고가 길어도 그 자리 안. 폭 = 원본 글자 끝 − 시작 − 끝 글자 뒤 자간(크롬은 줄 끝 글자 뒤에도 자간)"""
    x = round(ps["x"], 2)
    w = round(ps["right"] - x + TRACK_BODY / 1000 * BODY * MM, 2)
    for k, col in (("", "#231f20"), ("-b", BLUE_B)):
        y0, y1 = ps["base0"] - 0.95 * BODY * MM, ps["base1"] + 0.3 * BODY * MM   # 잴 창 = 첫 줄 글자 위 ~ 끝 줄 글자 아래(조각 상자는 줄 높이째라 위 번호와 겹친다)
        E({"id": f"p{len(ELEMS[len(PAGES)])}{k}", "x": x, "y": round(y0, 2), "w": round(ps["right"] - x, 2), "h": round(y1 - y0, 2),
           "color": col, "see": col, "ctol": 40, "pad": 1.0, "search": 1.0, "text": ps["text"][:30], "size": BODY, "원고": True,
           "shape_iou": 0.80})                                           # 문단은 양끝맞춤에서 낱말이 0.2mm 안팎 다르게 놓인다
    top = round(top_of(ps["base0"], BODY, NOTO, 400, LEAD), 2)
    st = text(x, top, w, round(limit - top, 1), temp_passage(len(ps["text"])), BODY, "#231f20", label=label, leading=LEAD, align="justify",
              font=NOTO, track=TRACK_BODY)
    st += slot("지문", label="자리 이름 「지문」")
    st += justify()                                                      # 균등 배치 — 낱말 100·133%, 자간 −8·250‰ (이 출판사 인디자인 설정)
    st += grep(0, r"\[[^\]]*\]", BLUE_B, label="GREP 스타일 — 대괄호 [ ] 안은 굵은 파랑")
    return st


def numbers(pno, size=12.0):
    """원본 쪽의 지문 번호 조각들(위 → 아래) — 그 크기 글 조각. → [span 요소]"""
    p = REF[pno - 1]
    t = p.trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                txt = "".join(c["c"] for c in sp["chars"]).strip()
                if round(sp["size"], 1) == size and txt and (sp["bbox"][0] - t.x0) * MM < 210:
                    out.append(span_el(pno, txt, sum(1 for o in out if o["text"] == txt), size=size))     # 같은 글의 쪽 번호(6pt)와 헷갈리지 않게 크기까지
    return sorted(out, key=lambda e: e["y"])


def rule(e, label=None):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면. 잴 때 옆 원 테두리(같은 색)가 섞이지 않게 둘레를 좁게"""
    y = round(e["y"] - e["sw"] / 2, 3)
    E({"id": f"r{len(ELEMS[len(PAGES)])}", **clip({"x": e["x"], "y": y, "w": e["w"], "h": e["sw"]}), "color": e["stroke"], "see": e["stroke"], "pad": 0.15, "ctol": 30})
    return box(e["x"], y, e["w"], e["sw"], e["stroke"], label=label)


def page_setup(name=None, rep=None):
    """쪽 설정 — Esc 로 선택을 풀면 쪽 패널: 이름(원고마다 묶음의 원고 이름) · 원고마다"""
    st = [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    if name:
        st.append(F("#side #s-pname", name, 800))
    if rep:
        st.append({"pick": {"at": "#side #s-rep", "value": rep}, "wait": 1200})
    return st


# ── 구성 4 「A어휘선택」 (원본 4~23쪽 = 펼침면 10벌 · 원고마다) — 견본 = 4·5쪽 ──
SPREADS_A1 = [(n, n + 1) for n in range(4, 24, 2)]


def spread_record(lp, rp, title_size=13.0):
    """펼침면 하나의 원고 — 제목 · 지문 번호 넷 · 지문 넷 (왼쪽 위·아래 → 오른쪽 위·아래)"""
    p = REF[lp - 1]
    title = next("".join(c["c"] for c in sp["chars"]).strip() for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", [])
                 for sp in l["spans"] if round(sp["size"], 1) == title_size)
    nums, texts = [], []
    for pg in (lp, rp):
        nums += [e["text"] for e in numbers(pg)]
        texts += [ps["text"] for ps in passages(pg)]
    return {"제목": title, "지문번호": nums, "지문": texts}


def header_left(pno, title_slot, code="A1"):
    el = [e for e in elems_of(pno) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    lines = [e for e in el if e["k"] == "line"]
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(rects[0])
    st += rule(max(lines, key=lambda e: clip(e)["w"]))                          # 펼침면에 걸친 선 중 이 쪽에 보이는 것
    st += B(rects[1])
    stp = dict(span_el(pno, "STEP"), text="STEP 01")
    stp["w"] = round(span_el(pno, "01")["x"] + span_el(pno, "01")["w"] - stp["x"], 2)
    st += T(stp, NOTO, 400, label="STEP 01 — 숫자만 굵게(GREP 스타일)")
    st += grep(0, r"\d+")
    st += T(span_el(pno, "FRAME"), NOTO, 700)
    st += T(span_el(pno, code, size=25.0), MAMA, 400, label=f"코드 {code} — TTMamablock")
    tt = span_el(pno, title_slot)
    st += T(tt, GMK, 500, label="제목 — 원고 자리 「제목」", slot_name="제목", temp="유형 이름 0")
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    ells = [e for e in el if e["k"] == "ellipse"]
    st += Cfill(ells[0])
    for e in ells[1:]:
        st += Cring(e)
    for e in lines[1:]:
        if e["w"] < 10:
            st += rule(e)
    for n in ("1", "2", "3"):
        st += T(span_el(pno, n, size=6.0), MS, 700)
    return st


class top_spot:
    """새 개체를 머리 빈 곳(110, 3)에 그려 옮긴다 — 본문 글상자가 원고만큼 자라는 쪽에서 아래쪽(기본 자리)에 그리면 밀려 면 밖으로 간다"""
    def __enter__(self):
        import mkpage as _mk
        self.mk, self.old = _mk, _mk.SPOT
        _mk.SPOT = {"mm": [110, 3]}

    def __exit__(self, *a):
        self.mk.SPOT = self.old


def body_pages(lp, code, title, key, label, body=None):
    """펼침면 두 쪽(본문 구성 견본) — 왼쪽: 머리·본문·꼬리 / 오른쪽: 머리(코드·꼬리표)·탭·본문·꼬리. 둘 다 「원고마다」(이름 = key).
    body(쪽) = 그 구성의 본문 대본(없으면 지문 둘 — 어휘 선택)"""
    body = body or passage_pair
    st = pg_new(lp, f"{label} — 원본 {lp}쪽 (펼침면 왼쪽)")
    st += header_left(lp, title, code)
    st += body(lp)
    st += [S("꼬리 — 쪽 번호(책이 채움) · STEP BY STEP", 1200)]
    with top_spot():
        st += T(span_el(lp, str(lp), size=6.0), EL, 700, label="쪽 번호 — 시스템 자리 「쪽 번호」", bind="sys.page_no")
        st += T(span_el(lp, "STEP BY STEP", size=6.0), EL, 700)
    st += page_setup(key, "each_set")
    st += done(f"{label} 왼쪽", f"p{lp}.png")

    rp = lp + 1
    st += pg_new(rp, f"{label} — 원본 {rp}쪽 (펼침면 오른쪽)")
    el = [e for e in elems_of(rp) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    st += [S("머리 — 크림 띠 · 선 · 꼬리표 · 큰 코드", 1500)]
    st += B(rects[0])
    st += rule(max((e for e in el if e["k"] == "line"), key=lambda e: clip(e)["w"]))     # 펼침면에 걸친 선이 둘 — 이 쪽에 보이는 것
    tag = [e for e in rects if e["n"] == 4][0]
    E({"id": "tag", **clip(tag), "color": tag["fill"], "see": tag["fill"], "pad": 0.6, "ctol": 30})
    st += shape(tag["x"], tag["y"], tag["w"], tag["h"], tag["fill"], d=poly_d(rp, tag), label="꼬리표 — 원본 꼭짓점 그대로")
    st += T(span_el(rp, "STEP BY STEP", size=6.0), MS, 700)
    st += T(span_el(rp, code, size=36.0), MS, 500, label=f"큰 코드 {code}")
    st += [S("오른쪽 STEP 탭 셋 — 면 · 세로 글(아래→위)", 1300)]
    for e in [e for e in rects if e["n"] == 1 and e["x"] > 200]:
        st += B(e)
    for t in ("STEP 01", "02", "03"):
        st += T(span_el(rp, t, size=6.5), MS, 700, rot=-90)
    st += body(rp)
    st += [S("꼬리 — STEP01 · 쪽 번호(책이 채움, 오른쪽 맞춤)", 1200)]
    with top_spot():
        st += T(span_el(rp, "STEP01", size=6.0), EL, 700)
        st += T(span_el(rp, str(rp), size=6.0), EL, 700, align="right", label="쪽 번호 — 시스템 자리 「쪽 번호」", bind="sys.page_no")
    st += page_setup(None, "each_set")
    st += done(f"{label} 오른쪽", f"p{rp}.png")
    return st


def passage_pair(pno):
    """쪽의 지문 둘 — 번호(자리 「지문번호」) + 지문(자리 「지문」). 위 지문 상자는 아래 번호 바로 위까지, 아래 지문은 꼬리 바로 위까지"""
    ps, nb = passages(pno), numbers(pno)
    assert len(ps) == len(nb) == 2, (pno, len(ps), len(nb))
    lim = (round(nb[1]["y"] - 1.0, 1), 281.0)
    st = []
    for k in range(2):
        st += T(nb[k], YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
        st += P(ps[k], lim[k], f"지문 — 원고 자리 「지문」 (임시 글로 스타일)")
    return st


if want(4):
    st += body_pages(4, "A1", "어휘 선택 1", "A어휘선택", "④ A어휘선택")
    CONTENT["A어휘선택"] = [spread_record(l, l + 1) for l in range(4, 24, 2)]          # 펼침면 10벌 = 레코드 10

# ── 구성 5 「A본문OX」 (원본 24~43쪽 = 펼침면 10벌 · 원고마다) — 견본 = 24·25쪽 ──
# 틀 하나로 통일(2026-10-10 사용자 결정): 원본은 쪽마다 문제 수·서체·크기가 섞여 있다 — 견본 쪽 모양 하나로, 문제가 하나뿐인 원고는 「접기 묶음」으로 문제 1을 접는다.
# 세로: 지문·선지·진술 글상자는 최소 높이로 그리고(원고만큼 자란다) 그 아래 것은 견본 원고가 자랄 만큼 위에 그린다(shift) — 견본 원고를 넣으면 원본 자리.
from mkpage import _color                                               # noqa: E402
LOTTE, ELB, LINK = "12LotteMartDreamBold", "Elice DigitalBaeum OTF", "#b5ac9c"
ELICE = {"EliceDXNeolliOTF-Md": (EL, 500), "EliceDigitalBaeumOTF": (ELB, 400)}
OXP = {}                                                                 # O/X 부품 — 문서에 한 번 만든다(부품 id)


def spans_of(pno):
    """원본 쪽 글 조각(가로) — 기준선 · 첫 글자 기준점 · 끝 글자 오른쪽 · 글자들"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    out = []
    for bl in p.get_text("rawdict")["blocks"]:
        for l in bl.get("lines", []):
            if l["dir"] != (1.0, 0.0):
                continue
            for sp in l["spans"]:
                ink = [c for c in sp["chars"] if c["c"].strip()]
                if not ink:
                    continue
                o = {"t": "".join(c["c"] for c in sp["chars"]), "font": sp["font"], "size": round(sp["size"], 1), "color": "#%06x" % sp["color"],
                     "x": (ink[0]["origin"][0] - t.x0) * MM, "x1": (ink[-1]["bbox"][2] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM,
                     "ink": [(c["c"], (c["origin"][0] - t.x0) * MM, (c["bbox"][2] - t.x0) * MM) for c in ink]}
                if 0 <= o["x"] < 205 and 24 < o["base"] < 280:                  # 이 쪽 안만 — 펼침면 옆 쪽에서 넘어온 조각(x 음수)은 빼고
                    out.append(o)
    return sorted(out, key=lambda o: (round(o["base"], 1), o["x"]))


def win_el(o, s, x0, x1, size=None, color=None):
    """잴 창 — 글자 높이(기준선 위 0.95em · 아래 desc_em)"""
    size = size or o["size"]
    em = size * MM
    return {"k": "text", "text": s, "x": round(x0, 2), "y": round(o["base"] - 0.95 * em, 2), "w": round(x1 - x0, 2),
            "h": round((0.95 + desc_em(s)) * em, 2), "size": size, "color": color or o["color"], "font": o["font"]}


def gaps_track(chs, size, fam=NOTO, weight=400):
    """글자 자리에서 자간(‰) — 이웃 글자(영문, 공백 빼고) 시작점 거리 - 서체 글자 폭, 중앙값"""
    import statistics
    _, _, adv = face(fam, weight)
    v = [((b[1] - a[1]) - adv(a[0]) * size * MM) / (size * MM) * 1000 for a, b in zip(chs, chs[1:]) if a[0].isascii() and b[0].isascii()]
    return round(statistics.median(v)) if v else 0


def line_track(lines, fam, wt):
    """줄들의 자간(‰) — 줄마다 (원본 첫~끝 글자 기준점 거리 - 크롬이 같은 서체 파일로 그린 거리) / 사이 수, 중앙값. 커닝·합자까지 맞는다(mkpage.track_from 과 같은 셈)"""
    import statistics
    v = []
    for o in lines:
        s = o["t"].strip()
        if len(s) < 8:
            continue
        orig = o["ink"][-1][1] - o["ink"][0][1]
        v.append((orig - chrome_extent(fam, wt, o["size"], s)) / (len(s) - 1) / (o["size"] * MM) * 1000)
    return round(statistics.median(v)) if v else 0


def drawings(pno):
    """원본 쪽 그림(면·선·경로) — 지면 mm, 칠·획 #hex"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    hx = lambda c: "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3]) if c else None
    return [{"x": (g["rect"].x0 - t.x0) * MM, "y": (g["rect"].y0 - t.y0) * MM, "w": g["rect"].width * MM, "h": g["rect"].height * MM,
             "fill": hx(g.get("fill")), "stroke": hx(g.get("color")), "sw": g.get("width"), "n": len(g["items"]), "items": g["items"]}
            for g in p.get_drawings()]


def make_ox_part(pno, X0=20.0, Y0=262.0):
    """O/X 부품 — 원본 첫 진술의 상자(둥근 네모 · 가운데 막대 · O · X)를 빈 자리에 그려 범위로 골라 그룹(부품)으로 묶고, 지면에서는 지운다"""
    dr = drawings(pno)
    bx = sorted([d for d in dr if d["n"] == 20 and d["fill"] == "#ffffff"], key=lambda d: d["y"])[0]
    bar = min([d for d in dr if d["fill"] == LINK and d["w"] < 1], key=lambda d: abs(d["y"] - bx["y"]) + abs(d["x"] - bx["x"]))
    it = bx["items"]
    r = round(abs(it[5][1].x - it[0][1].x) * MM, 3)                      # 왼쪽 세로 선 끝 → 위 가로 선 시작 = 모서리 둥글기
    sp = spans_of(pno)
    bot = bx["y"] + bx["h"]
    o_ = min([o for o in sp if o["t"] == "O" and o["font"].startswith("Type3")], key=lambda o: abs(o["base"] - bot) + abs(o["x"] - bx["x"]))
    x_ = min([o for o in sp if o["t"] == "X" and o["font"].startswith("Type3")], key=lambda o: abs(o["base"] - bot) + abs(o["x"] - bx["x"]))
    dx, dy = X0 - bx["x"], Y0 - bx["y"]
    st = [S("O/X 칸 부품 — 둥근 네모 · 막대 · O · X 를 그려 묶는다(진술 끝에 붙일 것)", 1500)]
    st += need_font("Montserrat-ExtraBold.otf")
    st += box(round(bx["x"] + dx, 3), round(bx["y"] + dy, 3), round(bx["w"], 3), round(bx["h"], 3), "#ffffff", radius=r)
    st += _color("stroke.color", LINK)
    st.append(F('#side input[data-a="stroke.w"]', round(bx["sw"], 3)))
    st += box(round(bar["x"] + dx, 3), round(bar["y"] + dy, 3), round(bar["w"], 3), round(bar["h"], 3), LINK)
    for g, col in ((o_, "#8aabc9"), (x_, "#bd7d70")):                    # O·X — Type3(윤곽), 잉크로 Montserrat ExtraBold. 행간 9pt · 폭 3mm 로 상자 안에
        y0 = top_of(g["base"], 9, MS, 800, 9)
        st += text(round(g["x"] + dx, 2), round(y0 + dy, 2), 3, round(9 * MM + 0.4, 1), g["t"], 9, col, font=MS, weight=800, leading=9)
    st += [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1200), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
           S("범위로 넷을 골라 그룹 → 부품", 1300),
           {"drag": {"from": {"mm": [X0 - 2, Y0 - 2]}, "to": {"mm": [X0 + bx["w"] + 2, Y0 + bx["h"] + 2]}}, "wait": 900},
           {"js": "(() => { if (sels.size !== 4) throw new Error('고른 것 ' + sels.size + ' (4 이어야)'); return '고른 것 4'; })()"},
           {"click": "#side #s-group", "wait": 1500},
           {"js": "(() => { const p = LIB.parts[LIB.parts.length - 1]; if (!p || p.atoms.length !== 4) throw new Error('부품 안 생김'); return '부품 ' + p.id + ' ' + p.w + '×' + p.h; })()"},
           S("지면의 그룹은 지운다 — 부품은 라이브러리에 남는다", 1100), {"key": "Delete", "wait": 900},
           {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]
    OXP["id"] = "p_1"                                                    # 문서의 첫 부품
    return st


def choice_paras(ln):
    paras = []
    for o in ln:
        if o["t"].strip()[:1] in "①②③④⑤" or not paras:
            paras.append([o])
        else:
            paras[-1].append(o)
    return paras


def ox_body(pno):
    """본문 O/X 한 쪽 — 지문 번호 · 바탕 지문 · (문제 1: 번호 | 발문 · 선지 — 접기 묶음) · 문제 2: 번호 | 발문 · 진술 다섯(번호 · 글 · 끝에 O/X 칸)"""
    sp, dr = spans_of(pno), drawings(pno)
    st = []
    if not OXP.get("id"):
        st += make_ox_part(pno)
    with top_spot():
        st += _ox_body(pno, sp, dr)
    return st


def _ox_body(pno, sp, dr):
    st = []
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    # 지문 — 바탕 칠 글상자(안쪽 여백), 최소 높이 한 줄
    ps = passages(pno)[0]
    bgs = [d for d in dr if d["fill"] and d["fill"] != "#ffffff" and d["n"] == 1 and d["w"] > 100 and ps["top"] - 8 < d["y"] < ps["top"] + 2]
    outer, inner = max(bgs, key=lambda d: d["w"]), min(bgs, key=lambda d: d["w"])
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    lead = round(lead_mm / MM, 2)
    rows = [o for o in sp if o["size"] == BODY and abs(o["base"] - ps["base1"]) < 0.5]     # 끝 줄(양끝 안 맞춘 줄)에서 자간
    trk = gaps_track([c for o in rows for c in o["ink"]], BODY)
    w_text = ps["right"] - ps["x"] + trk / 1000 * BODY * MM
    top_t = top_of(ps["base0"], BODY, NOTO, 400, lead)
    il, it_ = ps["x"] - outer["x"], top_t - outer["y"]
    ir = outer["w"] - il - w_text
    ib = outer["y"] + outer["h"] - (top_t + ps["lines"] * lead_mm)
    h0 = round(it_ + ib + lead_mm, 2)
    grow = [(outer["y"] + outer["h"], outer["h"] - h0)]                 # (원본 아래 끝, 견본 원고가 자랄 양) — 그 아래 것은 그만큼 위에 그린다
    shift = lambda y: sum(g for b, g in grow if y >= b - 0.3)
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(outer)[k] for k in ("x", "y", "w", "h")}, "color": inner["fill"], "see": inner["fill"], "pad": 0.6, "ctol": 12, "원고": True})
    E({"id": f"p{len(ELEMS[len(PAGES)])}", "x": round(ps["x"], 2), "y": round(ps["base0"] - 0.95 * BODY * MM, 2), "w": round(ps["right"] - ps["x"], 2),
       "h": round(ps["base1"] - ps["base0"] + 1.25 * BODY * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0,
       "text": ps["text"][:30], "size": BODY, "원고": True, "shape_iou": 0.80})
    st += text(round(outer["x"], 2), round(outer["y"], 2), round(outer["w"], 2), h0, temp_passage(len(ps["text"])), BODY, "#231f20",
               label="지문 — 바탕 칠 글상자(안쪽 여백) · 원고만큼 자란다", leading=lead, align="justify", font=NOTO, track=trk)
    st += _color("frame.fill", inner["fill"])                          # 글상자 칠 — 안쪽 여백까지, 글을 따라 자란다
    st.append(F('#side input[data-a="inset4"]', " ".join(f"{round(v, 2):g}" for v in (it_, ir, ib, il))))   # 편집기가 적는 꼴 그대로(3.00 → 3)
    st += slot("지문") + justify()
    # 문제 머리
    qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
    nums = [o for o in sp if LOTTE in o["font"]]
    right = max([o["x1"] for o in sp if o["font"].startswith("NotoSans") and o["base"] > qh[0]["base"] and o["x1"] > 180] or [188.0])
    for k, q in enumerate(qh):
        fold = "문제1" if len(qh) == 2 and k == 0 else None
        d0, d1 = q["ink"][0], q["ink"][1]
        bar = [c for c in q["ink"] if c[0] == "|"][0]
        sh = shift(q["base"] - 3)
        st += [S(f"문제 {k + 1} 머리 — 번호 | 발문" + (" (접기 묶음 「문제1」 — 원고가 문제 1을 비우면 접힌다)" if fold else ""), 1300)]
        # 번호·막대 상자는 오른쪽 끝까지 넓게 — 위 지문·선지 상자와 가로로 겹쳐야 그 상자가 자랄 때 같이 밀린다(안 겹치면 제자리)
        st += T(win_el(q, d0[0] + d1[0], d0[1], d1[2]), EL, 700, slot_name="문제번호", temp="00", shift=sh, fold=fold, w=round(right - d0[1], 1))
        st += T(win_el(q, "|", bar[1], bar[2]), EL, 700, shift=sh, fold=fold, w=round(right - bar[1], 1))
        qt = min([o for o in sp if o["font"] in ELICE and abs(o["base"] - q["base"]) < 1.5], key=lambda o: abs(o["base"] - q["base"]))
        fam, wt = ELICE[qt["font"]]
        st += T(win_el(qt, qt["t"].strip(), qt["x"], qt["x1"]), fam, wt, slot_name="발문", temp="임시 발문 — 다음 물음에 답하시오.", shift=sh, fold=fold,
                w=round(right - qt["x"], 1))
        ul = [d for d in dr if d["h"] < 0.3 and d["stroke"] and abs(d["y"] - q["base"]) < 2 and qt["x"] <= d["x"] <= qt["x1"]]
        if ul:                                                           # 발문의 부정어 밑줄(「않는」) — GREP 스타일(원본 선 굵기·자리)
            u = ul[0]
            st += grep(0, "않는|아닌|틀린|없는", bold=False, underline=True, line=round(u["sw"] * MM, 3), line_off=round(u["y"] - qt["base"], 2),
                       line_color=u["stroke"], label="GREP — 발문의 부정어(않는·아닌·틀린·없는)에 밑줄")
            E({"id": f"ul{len(ELEMS[len(PAGES)])}", "x": round(u["x"], 2), "y": round(u["y"] - 0.15, 2), "w": round(u["w"], 2), "h": 0.3,
               "color": u["stroke"], "see": u["stroke"], "pad": 0.15, "ctol": 30, "원고": True})
        if fold:                                                         # 선지 — 문단마다 ①…, 최소 높이 = 문단 수 × 행간
            ln = [o for o in sp if o["font"].startswith("NotoSans") and q["base"] + 2 < o["base"] < qh[1]["base"] - 2]
            paras = choice_paras(ln)
            csz = ln[0]["size"]
            cl_mm = min(b["base"] - a["base"] for a, b in zip(ln, ln[1:]))
            cl = round(cl_mm / MM, 2)
            ctrk = gaps_track([c for pa in paras for c in pa[-1]["ink"]], csz)            # 선지마다 끝 줄에서
            ctop = top_of(ln[0]["base"], csz, NOTO, 400, cl)
            ch0 = round(len(paras) * cl_mm, 2)
            E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(ln[0]["x"], 2), "y": round(ln[0]["base"] - 0.95 * csz * MM, 2),
               "w": round(max(o["x1"] for o in ln) - ln[0]["x"], 2), "h": round(ln[-1]["base"] - ln[0]["base"] + 1.25 * csz * MM, 2),
               "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "text": ln[0]["t"][:30], "size": csz, "원고": True, "shape_iou": 0.80})
            st += text(round(ln[0]["x"], 2), round(ctop - shift(ln[0]["base"] - 3), 2), round(right - ln[0]["x"] + ctrk / 1000 * csz * MM, 2), ch0,
                       "① 임시 선지 하나\n② 임시 선지 둘\n③ 임시 선지 셋\n④ 임시 선지 넷\n⑤ 임시 선지 다섯", csz, "#231f20",
                       label="선지 — 원고 자리 「선지」(문단마다 ①…) · 원고만큼 자란다", leading=cl, align="justify", font=NOTO, track=ctrk)
            st += slot("선지") + justify() + [F('#side input[data-a="fold"]', "문제1")]
            grow.append((ln[-1]["base"] + 1, len(ln) * cl_mm - ch0))
    # 진술 — 번호(넓은 상자: 위 글이 자라면 같이 밀린다) · 글(끝에 O/X 칸, 띄어 붙이기)
    stext = [o for o in sp if o["font"].startswith("NotoSans") and o["base"] > qh[-1]["base"] + 2]
    oxs = [d for d in dr if d["n"] == 20 and d["fill"] == "#ffffff"]
    bars = [d for d in dr if d["fill"] == LINK and d["w"] < 1]
    _, _, adv = face(NOTO, 400)
    last_lines = []                                                     # 자간은 문단 끝 줄에서만 — 양끝 맞춘 줄은 낱말·글자 사이가 늘어나 있다
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        last_lines.append([o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1][-1])
    strk = line_track(last_lines, NOTO, 400)                            # 끝 줄을 크롬(편집기와 같은 서체 파일)으로 재어 — 낱말 사이 커닝까지
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        ln = [o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1]
        ssz, first, cont = ln[0]["size"], ln[0], ln[1:]
        cx = cont[0]["x"] if cont else n["x"] + 6.0
        bx = min([d for d in oxs if n["base"] - 6 < d["y"] < nxt - 3], key=lambda d: d["y"])
        bbot = bx["y"] + bx["h"]
        last = ln[-1]
        same = abs(bbot - last["base"]) < 2.5                            # O/X 칸이 끝 줄 옆인가, 다음 줄로 넘어갔나
        slead_mm = (cont[0]["base"] - first["base"]) if cont else 22 * MM
        slead = round(slead_mm / MM, 2)
        lines = len(ln) + (0 if same else 1)
        sh = shift(n["base"] - 3)
        st += [S(f"진술 {k + 1:02d} — 번호 · 글 · 끝에 O/X 칸", 1100)]
        st += T(win_el(n, n["t"].strip(), n["x"], n["x1"]), LOTTE, 400, slot_name="진술번호", temp="00", shift=sh, w=round(right - n["x"], 1))
        txt = " ".join(o["t"].strip() for o in ln)
        stop = top_of(first["base"], ssz, NOTO, 400, slead)
        E({"id": f"s{len(ELEMS[len(PAGES)])}", "x": round(min(cx, first["x"]), 2), "y": round(first["base"] - 0.95 * ssz * MM, 2),
           "w": round(max(o["x1"] for o in ln) - min(cx, first["x"]), 2), "h": round(last["base"] - first["base"] + 1.25 * ssz * MM, 2),
           "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 0.8, "search": 0.8, "text": txt[:30], "size": ssz, "원고": True, "shape_iou": 0.80})
        ob = min(bars, key=lambda d: abs(d["x"] - bx["x"] - 10) + abs(d["y"] - bx["y"]))
        o = bx["sw"] * MM / 2
        E({"id": f"ox{len(ELEMS[len(PAGES)])}", "x": round(bx["x"] - o, 2), "y": round(bx["y"] - o, 2), "w": round(bx["w"] + 2 * o, 2), "h": round(bx["h"] + 2 * o, 2),
           "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30, "원고": True})
        E({"id": f"oxb{len(ELEMS[len(PAGES)])}", "x": round(ob["x"], 2), "y": round(ob["y"], 2), "w": round(ob["w"], 2), "h": round(ob["h"], 2),
           "color": LINK, "see": LINK, "pad": 0.15, "ctol": 30, "원고": True})
        # 칸 자리: 같은 줄이면 끝 글자 오른쪽 + 띄어쓰기 폭 + 자간(끝 글자 뒤 · 띄어쓰기 뒤) 다음, 기준선에서 칸 아래 끝까지 drop
        if same:
            gap = round(bx["x"] - last["x1"] - adv(" ") * ssz * MM - 2 * strk / 1000 * ssz * MM, 3)
            drop = round(bbot - last["base"], 3)
        else:                                                            # 다음 줄 첫머리 — 칸이 줄 시작에서 떨어진 만큼, 다음 줄 기준선 = 끝 줄 + 행간
            gap = round(bx["x"] - cx, 3)
            drop = round(bbot - (last["base"] + slead_mm), 3)
        st += text(round(cx, 2), round(stop - sh, 2), round(right - cx + strk / 1000 * ssz * MM, 2), round(slead_mm, 2), "임시 진술 — 바깥에서 온 문장이 이 자리에 들어온다.",
                   ssz, "#231f20", label="진술 — 원고 자리 「진술」 · 끝에 O/X 칸", leading=slead, align="justify", font=NOTO, track=strk)
        indent1 = round(first["x"] - cx, 2)
        if abs(indent1) > 0.05:
            st.append(F('#side input[data-a="indent_first"]', indent1))
        st += slot("진술") + justify()
        st += [{"pick": {"at": '#side select[data-a="tail.part"]', "value": OXP["id"]}, "wait": 800},
               F('#side input[data-a="tail.gap"]', gap), F('#side input[data-a="tail.drop"]', drop),
               {"click": '#side input[data-a="tail.space"]', "wait": 600}]
        grow.append((first["base"] + 1, (lines - 1) * slead_mm))
    return st


def ox_record(lp, rp):
    """본문 O/X 펼침면 하나의 원고 — 쪽마다: 지문 번호 · 지문 · 문제(1: 번호·발문·선지 — 없으면 비움, 2: 번호·발문) · 진술 번호·진술"""
    rec = {"제목": None, "지문번호": [], "지문": [], "문제번호": [], "발문": [], "선지": [], "진술번호": [], "진술": []}
    for pno in (lp, rp):
        sp = spans_of(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec["지문"].append(passages(pno)[0]["text"])
        qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
        qs = []
        for q in qh:
            qt = min([o for o in sp if o["font"] in ELICE and abs(o["base"] - q["base"]) < 1.5], key=lambda o: abs(o["base"] - q["base"]))
            qs.append(("".join(c[0] for c in q["ink"][:2]), qt["t"].strip()))
        if len(qh) == 2:
            ln = [o for o in sp if o["font"].startswith("NotoSans") and qh[0]["base"] + 2 < o["base"] < qh[1]["base"] - 2]
            rec["선지"].append("\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(ln)))
        else:
            qs = [("", "")] + qs                                           # 문제 1 없음 — 비운다(접기 묶음째 접힌다)
            rec["선지"].append("")
        rec["문제번호"] += [a for a, _ in qs]
        rec["발문"] += [b for _, b in qs]
        nums = [o for o in sp if LOTTE in o["font"]]
        stext = [o for o in sp if o["font"].startswith("NotoSans") and o["base"] > qh[-1]["base"] + 2]
        for k, n in enumerate(nums):
            nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
            rec["진술번호"].append(n["t"].strip())
            rec["진술"].append(" ".join(o["t"].strip() for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1))
    return rec


if want(5):
    st += body_pages(24, "A2", "본문 O/X", "A본문OX", "⑤ A본문OX", body=ox_body)
    CONTENT["A본문OX"] = [ox_record(l, l + 1) for l in range(24, 44, 2)]          # 펼침면 10벌 = 레코드 10

# ── 구성 6 「B본문정리」 (원본 44~63쪽 = 펼침면 10벌 · 원고마다) — 견본 = 44·45쪽 ──
# 쪽: 지문 번호 · 지문(바탕) · 꼬리표 「주제」 + 주제 문장들 · 꼬리표 「제목」 + 제목 문장들 · 체크 아이콘 + 발문 · 지문(바탕) · 주석(바탕, 없으면 접힌다) · 선지
# 쪽 설정 「자라면 아래 모두 밀기」 — 꼬리표·아이콘은 지문 상자 왼쪽 밖이라 가로로 안 겹친다.
TAGNAME = {"주제": "주제", "제목": "글제목"}                              # 꼬리표 글 → 원고 자리 이름(머리의 「제목」= 유형 이름과 겹치지 않게)
FOOT = {}                                                                # 주석 상자 꼴 — 주석이 있는 쪽에서 재서 없는 쪽에도 같은 상자(접힌다)


def bg_box(st, rect, rows, size, lead_mm, label, slot_name, temp, sh, fill, align="justify", fam=NOTO, wt=400, min_lines=1):
    """바탕 칠 글상자 — 원본 바탕 면(rect) 자리·크기, 글은 안쪽 여백으로. 최소 높이 = min_lines 줄(원고만큼 자란다). → 견본 원고가 자랄 양"""
    lead = round(lead_mm / MM, 2)
    trk = gaps_track([c for c in rows[-1]["ink"]], size, fam, wt)
    x_t, right = rows[0]["x"], max(o["x1"] for o in rows)
    w_text = right - x_t + trk / 1000 * size * MM
    top_t = top_of(rows[0]["base"], size, fam, wt, lead)
    il, it_ = x_t - rect["x"], top_t - rect["y"]
    ir = rect["w"] - il - w_text
    ib = rect["y"] + rect["h"] - (top_t + len(rows) * lead_mm)
    h0 = round(it_ + ib + min_lines * lead_mm, 2)
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(rect)[k] for k in ("x", "y", "w", "h")}, "color": fill, "see": fill, "pad": 0.6, "ctol": 8, "원고": True})
    E({"id": f"p{len(ELEMS[len(PAGES)])}", "x": round(min(o["x"] for o in rows), 2), "y": round(rows[0]["base"] - 0.95 * size * MM, 2),
       "w": round(right - min(o["x"] for o in rows), 2), "h": round(rows[-1]["base"] - rows[0]["base"] + 1.25 * size * MM, 2), "color": "#231f20", "see": "#231f20",
       "ctol": 40, "pad": 1.0, "search": 1.0, "text": rows[0]["t"][:30], "size": size, "원고": True, "shape_iou": 0.80})
    st += text(round(rect["x"], 2), round(rect["y"] - sh, 2), round(rect["w"], 2), h0, temp, size, "#231f20", label=label, leading=lead, align=align,
               font=fam, weight=wt if wt != 400 else None, track=trk)
    st += _color("frame.fill", fill)
    st.append(F('#side input[data-a="inset4"]', " ".join(f"{round(v, 2):g}" for v in (it_, ir, ib, il))))
    st += slot(slot_name)
    if align == "justify":
        st += justify()
    return rect["h"] - h0


def passage_bg(dr, ps):
    """지문 바탕 면 — 머리 아래에서 지문 첫 줄을 감싸는 칠한 면(머리 크림 띠 말고)"""
    return max([d for d in dr if d["fill"] and d["fill"] != "#ffffff" and d["n"] == 1 and d["w"] > 100 and 24 < d["y"] < ps["base0"]
                and d["y"] + d["h"] > ps["base0"]], key=lambda d: d["w"])


def sum_body(pno):
    with top_spot():
        return _sum_body(pno)


def _sum_body(pno):
    sp, dr = spans_of(pno), drawings(pno)
    st = [S("쪽 설정 — 자라면 아래 모두 밀기(옆 꼬리표·아이콘도 같이)", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-pushrow", "wait": 900}]
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    grow = []
    shift = lambda y: sum(g for b, g in grow if y >= b - 0.3)
    # 지문 1 — 바탕(#f9f9f2) 글상자
    ps = passages(pno)[0]
    rows = [o for o in sp if o["size"] == BODY and ps["base0"] - 0.5 <= o["base"] <= ps["base1"] + 0.5 and o["font"].endswith("Regular")]
    rect = passage_bg(dr, ps)
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    g = bg_box(st, rect, rows, BODY, lead_mm, "지문 — 바탕 칠 글상자 · 원고만큼 자란다", "지문", temp_passage(len(ps["text"])), 0, rect["fill"])
    grow.append((rect["y"] + rect["h"], g))
    # 꼬리표 둘 — 면 + (두꺼운 선) + 흰 글, 옆에 문장들(Noto Medium 9)
    tags = sorted([d for d in dr if d["n"] == 1 and d["fill"] and d["fill"] != "#ffffff" and 3 < d["h"] < 4 and 6 < d["w"] < 9], key=lambda d: d["y"])
    q_icon = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    for k, tg in enumerate(tags):
        nxt = tags[k + 1]["y"] if k + 1 < len(tags) else q_icon["y"]
        sh = shift(tg["y"])
        tt = min([o for o in sp if o["font"].startswith("EliceDigitalBaeumOTF-B") and o["color"] == "#ffffff"], key=lambda o: abs(o["base"] - tg["y"] - tg["h"]))
        name = TAGNAME.get(tt["t"].strip(), tt["t"].strip())
        st += [S(f"꼬리표 「{tt['t'].strip()}」 — 면 · 글 · 옆 문장(원고 자리 「{name}」)", 1200)]
        E({"id": f"tg{len(ELEMS[len(PAGES)])}", "x": round(tg["x"], 2), "y": round(tg["y"], 2), "w": round(tg["w"], 2), "h": round(tg["h"], 2),
           "color": tg["fill"], "see": tg["fill"], "pad": 0.3, "ctol": 30})
        st += box(round(tg["x"], 2), round(tg["y"] - sh, 2), round(tg["w"], 2), round(tg["h"], 2), tg["fill"])
        for ln in [d for d in dr if d["n"] == 1 and d["stroke"] == tg["fill"] and d["h"] < 0.1 and abs(d["y"] - tg["y"] - tg["h"] / 2) < 1]:
            t_ = ln["sw"] * MM                                           # 두꺼운 선(10pt) — 면과 거의 겹친다(위로 0.1mm 더). 얇은 면으로
            st += box(round(ln["x"], 2), round(ln["y"] - t_ / 2 - sh, 3), round(ln["w"], 2), round(t_, 3), tg["fill"])
        st += T(win_el(tt, tt["t"].strip(), tt["x"], tt["x1"]), ELB, 700, shift=sh, w=8, search=0.3)
        ln = [o for o in sp if o["font"] == "NotoSansCJKkr-Medium" and tg["y"] - 1 < o["base"] < nxt - 1]
        lmm = (ln[1]["base"] - ln[0]["base"]) if len(ln) > 1 else 6.75
        trk = gaps_track([c for o in ln for c in o["ink"]], 9, NOTO, 500)
        E({"id": f"tl{len(ELEMS[len(PAGES)])}", "x": round(min(o["x"] for o in ln), 2), "y": round(ln[0]["base"] - 0.95 * 9 * MM, 2),
           "w": round(max(o["x1"] for o in ln) - min(o["x"] for o in ln), 2), "h": round(ln[-1]["base"] - ln[0]["base"] + 1.25 * 9 * MM, 2),
           "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 0.8, "search": 0.8, "text": ln[0]["t"].strip()[:30], "size": 9.0, "원고": True, "shape_iou": 0.80})
        x0 = min(o["x"] for o in ln)
        st += text(round(x0, 2), round(top_of(ln[0]["base"], 9, NOTO, 500, round(lmm / MM, 2)) - sh, 2), round(185 - x0, 1), round(len(ln) * lmm, 2),
                   "\n".join(f"임시 {tt['t'].strip()} 문장 {i + 1}" for i in range(len(ln))), 9, "#231f20", label=f"{tt['t'].strip()} 문장 — 원고 자리 「{name}」(문단마다 하나)",
                   leading=round(lmm / MM, 2), font=NOTO, weight=500, track=trk or None)
        st += slot(name)
    # 체크 아이콘 + 발문
    sh = shift(q_icon["y"])
    o_ = q_icon["sw"] * MM / 2
    E({"id": f"ic{len(ELEMS[len(PAGES)])}", "x": round(q_icon["x"] - o_, 2), "y": round(q_icon["y"] - o_, 2), "w": round(q_icon["w"] + 2 * o_, 2),
       "h": round(q_icon["h"] + 2 * o_, 2), "color": q_icon["stroke"], "see": q_icon["stroke"], "pad": 0.3, "ctol": 30})
    st += image(round(q_icon["x"] - 0.3, 2), round(q_icon["y"] - 0.3 - sh, 2), 4.15, 4.15, os.path.join(HERE, "check.svg"),
                label="체크 아이콘 — 원본에서 내보낸 그림(check.svg)을 올린다")
    qt = [o for o in sp if o["font"] == "EliceDigitalBaeumOTF" and abs(o["base"] - q_icon["y"] - q_icon["h"]) < 2][0]
    st += T(win_el(qt, qt["t"].strip(), qt["x"], qt["x1"]), ELB, 400, slot_name="발문", temp="임시 발문 — 다음 물음에 답하시오.", shift=sh, w=round(185 - qt["x"], 1))
    # 지문 2 — 바탕(#eaf0f7) 글상자 + 주석(접기 묶음)
    p2 = [g_ for g_ in passages(pno) if g_["base0"] > qt["base"]][0]
    rows2 = [o for o in sp if o["size"] == BODY and o["font"].endswith("Regular") and p2["base0"] - 0.5 <= o["base"] <= p2["base1"] + 0.5 and not o["t"].strip().startswith("*")]
    rects = sorted([d for d in dr if d["fill"] == "#eaf0f7" and d["n"] == 1 and d["w"] > 100 and d["y"] > qt["base"]], key=lambda d: d["y"])
    r1 = rects[0]
    sh = shift(r1["y"])
    lead2 = (rows2[-1]["base"] - rows2[0]["base"]) / (len(rows2) - 1)
    g = bg_box(st, r1, rows2, BODY, lead2, "지문(문제) — 바탕 칠 글상자", "지문", temp_passage(len(" ".join(o["t"] for o in rows2))), sh, r1["fill"])
    grow.append((r1["y"] + r1["h"], g))
    foot = [o for o in sp if o["size"] == BODY and o["t"].strip().startswith("*")]
    if foot:                                                             # 주석이 있는 쪽 — 꼴을 잰다(아래 바탕 면들 = 주석 자리)
        f = foot[0]
        fb = max(d["y"] + d["h"] for d in rects)
        FOOT.update(h=fb - (r1["y"] + r1["h"]), base=f["base"] - (r1["y"] + r1["h"]), right=r1["x"] + r1["w"] - f["x1"])
    if FOOT:
        top_f = r1["y"] + r1["h"]
        sh = shift(top_f + 0.5)
        ftrk = gaps_track(foot[0]["ink"], BODY) if foot else -40
        ft = top_of(top_f + FOOT["base"], BODY, NOTO, 400, round(lead2 / MM, 2))
        ins = (round(ft - top_f, 2), round(FOOT["right"] + ftrk / 1000 * BODY * MM, 2), round(FOOT["h"] - (ft - top_f) - lead2, 2), 3)
        st += [S("주석 — 지문 바탕에 이어 붙인 오른쪽 맞춤 줄(원고 자리 「주석」 · 접기 묶음: 원고가 비우면 접힌다)", 1300)]
        st += text(round(r1["x"], 2), round(top_f - sh, 2), round(r1["w"], 2), round(FOOT["h"], 2), "* 임시 주석: 낱말 풀이", BODY, "#231f20", align="right",
                   leading=round(lead2 / MM, 2), font=NOTO, track=ftrk)
        st += _color("frame.fill", r1["fill"])
        st.append(F('#side input[data-a="inset4"]', " ".join(f"{v:g}" for v in ins)))
        st += slot("주석") + [F('#side input[data-a="fold"]', "주석")]
        if foot:
            E({"id": f"ft{len(ELEMS[len(PAGES)])}", "x": round(foot[0]["x"], 2), "y": round(foot[0]["base"] - 0.95 * BODY * MM, 2), "w": round(foot[0]["x1"] - foot[0]["x"], 2),
               "h": round(1.25 * BODY * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 0.8, "search": 0.8, "text": foot[0]["t"].strip()[:30],
               "size": BODY, "원고": True, "shape_iou": 0.80})
            for d in rects[1:]:
                E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(d)[k] for k in ("x", "y", "w", "h")}, "color": d["fill"], "see": d["fill"], "pad": 0.3, "ctol": 8, "원고": True})
        else:
            grow.append((top_f + 0.4, -FOOT["h"]))                       # 이 쪽 원고엔 주석이 없다 — 상자는 접히고 아래 것이 그만큼 올라온다(설계는 아래에)
    # 선지
    ln = [o for o in sp if o["font"] == "NotoSansCJKkr-Regular" and o["size"] == 9.0 and o["base"] > r1["y"] + r1["h"]]
    paras = choice_paras(ln)
    csz = 9.0
    cl_mm = min(b["base"] - a["base"] for a, b in zip(ln, ln[1:]))
    cl = round(cl_mm / MM, 2)
    ctrk = gaps_track([c for pa in paras for c in pa[-1]["ink"]], csz)
    ch0 = round(len(paras) * cl_mm, 2)
    sh = shift(ln[0]["base"] - 3)
    E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(ln[0]["x"], 2), "y": round(ln[0]["base"] - 0.95 * csz * MM, 2), "w": round(max(o["x1"] for o in ln) - ln[0]["x"], 2),
       "h": round(ln[-1]["base"] - ln[0]["base"] + 1.25 * csz * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0,
       "text": ln[0]["t"][:30], "size": csz, "원고": True, "shape_iou": 0.80})
    right = max(r["x"] + r["w"] for r in rects) - 3
    st += text(round(ln[0]["x"], 2), round(top_of(ln[0]["base"], csz, NOTO, 400, cl) - sh, 2), round(right - ln[0]["x"] + ctrk / 1000 * csz * MM, 2), ch0,
               "① 임시 선지 하나\n② 임시 선지 둘\n③ 임시 선지 셋\n④ 임시 선지 넷\n⑤ 임시 선지 다섯", csz, "#231f20",
               label="선지 — 원고 자리 「선지」(문단마다 ①…)", leading=cl, align="justify", font=NOTO, track=ctrk)
    st += slot("선지") + justify()
    return st


def sum_record(lp, rp):
    """본문 정리 펼침면 하나의 원고 — 쪽마다: 지문 번호 · 지문(위) · 주제 · 글제목 · 발문 · 지문(문제) · 주석 · 선지"""
    rec = {"제목": None, "지문번호": [], "지문": [], "주제": [], "글제목": [], "발문": [], "주석": [], "선지": []}
    for pno in (lp, rp):
        sp, dr = spans_of(pno), drawings(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        tags = sorted([o for o in sp if o["font"].startswith("EliceDigitalBaeumOTF-B") and o["color"] == "#ffffff"], key=lambda o: o["base"])
        qt = [o for o in sp if o["font"] == "EliceDigitalBaeumOTF"][0]
        for k, t_ in enumerate(tags):
            nxt = tags[k + 1]["base"] if k + 1 < len(tags) else qt["base"]
            rec[TAGNAME.get(t_["t"].strip(), t_["t"].strip())].append("\n".join(o["t"].strip() for o in sp if o["font"] == "NotoSansCJKkr-Medium" and t_["base"] - 1 < o["base"] < nxt - 3))
        rec["발문"].append(qt["t"].strip())
        pss = passages(pno)
        rec["지문"] += [pss[0]["text"], [g_ for g_ in pss if g_["base0"] > qt["base"]][0]["text"].split(" *")[0].strip()]
        foot = [o for o in sp if o["size"] == BODY and o["t"].strip().startswith("*")]
        rec["주석"].append(foot[0]["t"].strip() if foot else "")
        ln = [o for o in sp if o["font"] == "NotoSansCJKkr-Regular" and o["size"] == 9.0 and o["base"] > qt["base"]]
        rec["선지"].append("\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(ln)))
    return rec


if want(6):
    st += body_pages(44, "B1", "본문 정리", "B본문정리", "⑥ B본문정리", body=sum_body)
    CONTENT["B본문정리"] = [sum_record(l, l + 1) for l in range(44, 64, 2)]

# ── 구성 7 「B내용종합」 (원본 64~83쪽 = 펼침면 10벌 · 원고마다) — 견본 = 64·65쪽 ──
# 쪽: 지문 번호 · 지문(바탕) · 문제 셋(번호 | 발문 · 선지 넷). 문제마다 접기 묶음(원고가 문제를 비우면 접힌다), 자라면 아래 모두 밀기.


def q_block(st, sp, q, nxt_base, right, shift, grow, fold=None):
    """문제 하나 — 번호 | 발문(한 줄 넘으면 자란다) · 선지(문단마다 ①…, 최소 높이 = 문단 수 × 행간). 번호·막대·발문 상자는 오른쪽 끝까지 넓게(같이 밀리게)"""
    d0, d1 = q["ink"][0], q["ink"][1]
    bar = [c for c in q["ink"] if c[0] == "|"][0]
    sh = shift(q["base"] - 3)
    qts = [o for o in sp if o["font"] in ELICE and q["base"] - 1.5 < o["base"] < nxt_base - 2 and o["x"] > bar[2]]
    qt = qts[0]
    qlead = (qts[1]["base"] - qts[0]["base"]) if len(qts) > 1 else None
    st += [S("문제 — 번호 | 발문 · 선지" + (f" (접기 묶음 「{fold}」)" if fold else ""), 1100)]
    st += T(win_el(q, d0[0] + d1[0], d0[1], d1[2]), EL, 700, slot_name="문제번호", temp="00", shift=sh, fold=fold, w=round(right - d0[1], 1))
    st += T(win_el(q, "|", bar[1], bar[2]), EL, 700, shift=sh, fold=fold, w=round(right - bar[1], 1))
    fam, wt = ELICE[qt["font"]]
    qe = win_el(qt, " ".join(o["t"].strip() for o in qts), qt["x"], max(o["x1"] for o in qts))
    if qlead:
        qe["h"] = round(qe["h"] + qts[-1]["base"] - qt["base"], 2)
    st += T(qe, fam, wt, slot_name="발문", temp="임시 발문 — 다음 물음에 답하시오.", shift=sh, fold=fold, w=round(right - qt["x"], 1),
            leading=round(qlead / MM, 2) if qlead else None)
    if qlead:                                                            # 두 줄 발문 — 견본 원고만큼 자라 아래를 민다
        grow.append((qts[0]["base"] + 1, (len(qts) - 1) * qlead))
    ln = [o for o in sp if o["font"].startswith("NotoSans") and qts[-1]["base"] + 2 < o["base"] < nxt_base - 2]
    paras = choice_paras(ln)
    csz = ln[0]["size"]
    cl_mm = min(b["base"] - a["base"] for a, b in zip(ln, ln[1:]))
    cl = round(cl_mm / MM, 2)
    ctrk = gaps_track([c for pa in paras for c in pa[-1]["ink"]], csz)
    ch0 = round(len(paras) * cl_mm, 2)
    E({"id": f"c{len(ELEMS[len(PAGES)])}", "x": round(ln[0]["x"], 2), "y": round(ln[0]["base"] - 0.95 * csz * MM, 2), "w": round(max(o["x1"] for o in ln) - ln[0]["x"], 2),
       "h": round(ln[-1]["base"] - ln[0]["base"] + 1.25 * csz * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0,
       "text": ln[0]["t"][:30], "size": csz, "원고": True, "shape_iou": 0.80})
    st += text(round(ln[0]["x"], 2), round(top_of(ln[0]["base"], csz, NOTO, 400, cl) - shift(ln[0]["base"] - 3), 2), round(right - ln[0]["x"] + ctrk / 1000 * csz * MM, 2), ch0,
               "\n".join(f"{'①②③④⑤'[i]} 임시 선지" for i in range(len(paras))), csz, "#231f20",
               label="선지 — 원고 자리 「선지」(문단마다 ①…) · 원고만큼 자란다", leading=cl, align="justify", font=NOTO, track=ctrk)
    st += slot("선지") + justify()
    if fold:
        st.append(F('#side input[data-a="fold"]', fold))
    grow.append((ln[-1]["base"] + 1, len(ln) * cl_mm - ch0))
    return st


def mcq_body(pno):
    with top_spot():
        return _mcq_body(pno)


def _mcq_body(pno):
    sp, dr = spans_of(pno), drawings(pno)
    st = [S("쪽 설정 — 자라면 아래 모두 밀기", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-pushrow", "wait": 900}]
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    grow = []
    shift = lambda y: sum(g for b, g in grow if y >= b - 0.3)
    ps = passages(pno)[0]
    rows = [o for o in sp if o["size"] == BODY and ps["base0"] - 0.5 <= o["base"] <= ps["base1"] + 0.5 and o["font"].endswith("Regular")]
    rect = passage_bg(dr, ps)
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    g = bg_box(st, rect, rows, BODY, lead_mm, "지문 — 바탕 칠 글상자 · 원고만큼 자란다", "지문", temp_passage(len(ps["text"])), 0, rect["fill"])
    grow.append((rect["y"] + rect["h"], g))
    qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
    right = max([o["x1"] for o in sp if o["font"].startswith("NotoSans") and o["base"] > qh[0]["base"]] + [rect["x"] + rect["w"] - 2])
    for k, q in enumerate(qh):
        nxt = qh[k + 1]["base"] if k + 1 < len(qh) else 280
        st = q_block(st, sp, q, nxt, right, shift, grow, fold=f"문제{k + 1}" if k else None)
    return st


def mcq_record(lp, rp, key_title=13.0):
    """문제 셋 펼침면 하나의 원고 — 쪽마다: 지문 번호 · 지문 · 문제 번호 · 발문 · 선지(문제마다)"""
    rec = {"제목": None, "지문번호": [], "지문": [], "문제번호": [], "발문": [], "선지": []}
    for pno in (lp, rp):
        sp = spans_of(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == key_title)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec["지문"].append(passages(pno)[0]["text"])
        qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
        for k, q in enumerate(qh):
            nxt = qh[k + 1]["base"] if k + 1 < len(qh) else 280
            bar = [c for c in q["ink"] if c[0] == "|"][0]
            qts = [o for o in sp if o["font"] in ELICE and q["base"] - 1.5 < o["base"] < nxt - 2 and o["x"] > bar[2]]
            rec["문제번호"].append("".join(c[0] for c in q["ink"][:2]))
            rec["발문"].append(" ".join(o["t"].strip() for o in qts))
            ln = [o for o in sp if o["font"].startswith("NotoSans") and qts[-1]["base"] + 2 < o["base"] < nxt - 2]
            rec["선지"].append("\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(ln)))
    return rec


if want(7):
    st += body_pages(64, "B2", "내용 종합", "B내용종합", "⑦ B내용종합", body=mcq_body)
    CONTENT["B내용종합"] = [mcq_record(l, l + 1) for l in range(64, 84, 2)]

# ── 구성 8 「C문장배열」 (원본 84~103쪽 = 펼침면 10벌 · 원고마다) — 견본 = 84·85쪽 ──
# 쪽: 지문 번호 · 문장 (A)…(바탕, 이름표 GREP) · 답 줄(화살표 둘 · 선) · 체크 아이콘 + 발문 · 주어진 문장(바탕) · 지문(테두리 상자, 문단 여럿)


def para_box(st, rect, rows, size, label, slot_name, temp, sh, fill=None, stroke=None, sw=None, align="justify", grep_label=None, measure=True):
    """바탕·테두리 글상자 하나에 문단 여럿 — 원본 줄들(rows)에서 행간·문단 사이·첫 줄 들여쓰기·자간을 재서 친다. 최소 높이 한 줄(원고만큼 자란다).
    → (견본 원고가 자랄 양, 원고 글 — 문단은 줄바꿈)"""
    rows = sorted(rows, key=lambda o: o["base"])
    lines = []                                                           # 같은 기준선 조각은 한 줄
    for o in rows:
        if lines and abs(lines[-1][0]["base"] - o["base"]) < 0.3:
            lines[-1].append(o)
        else:
            lines.append([o])
    bases = [ln[0]["base"] for ln in lines]
    diffs = [b - a for a, b in zip(bases, bases[1:])]
    lead_mm = min(diffs) if diffs else size * 1.45 * MM
    paras = [[lines[0]]]
    for d, ln in zip(diffs, lines[1:]):
        if d > lead_mm * 1.25:
            paras.append([ln])
        else:
            paras[-1].append(ln)
    gap = (max(diffs) - lead_mm) if any(d > lead_mm * 1.25 for d in diffs) else 0.0
    xs = lambda ln: min(o["x"] for o in ln)
    cont = [xs(ln) for pa in paras for ln in pa[1:]]
    x_t = min(cont) if cont else min(xs(pa[0]) for pa in paras)
    ind1 = round(min(xs(pa[0]) for pa in paras) - x_t, 2) if cont else 0
    right = max(o["x1"] for o in rows)
    trk = gaps_track([c for pa in paras for o in pa[-1] for c in o["ink"]], size)
    lead = round(lead_mm / MM, 2)
    top_t = top_of(bases[0], size, NOTO, 400, lead)
    text_h = len(lines) * lead_mm + (len(paras) - 1) * gap
    il, it_ = x_t - rect["x"], top_t - rect["y"]
    ir = rect["w"] - il - (right - x_t + trk / 1000 * size * MM)
    ib = rect["y"] + rect["h"] - (top_t + text_h)
    h0 = round(it_ + ib + lead_mm, 2)
    txt = "\n".join(" ".join("".join(o["t"] for o in sorted(ln, key=lambda o: o["x"])).strip() for ln in pa) for pa in paras)
    if not measure:                                                      # 원고 글만 읽을 때
        return 0, txt
    if fill:
        E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(rect)[k] for k in ("x", "y", "w", "h")}, "color": fill, "see": fill, "pad": 0.6, "ctol": 8, "원고": True})
    if stroke:
        o_ = sw * MM / 2
        E({"id": f"fr{len(ELEMS[len(PAGES)])}", "x": round(rect["x"] - o_, 2), "y": round(rect["y"] - o_, 2), "w": round(rect["w"] + 2 * o_, 2), "h": round(rect["h"] + 2 * o_, 2),
           "color": stroke, "see": stroke, "pad": 0.3, "ctol": 30, "원고": True})
    x0 = min(o["x"] for o in rows)
    E({"id": f"p{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(bases[0] - 0.95 * size * MM, 2), "w": round(right - x0, 2),
       "h": round(bases[-1] - bases[0] + 1.25 * size * MM, 2), "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0,
       "text": txt[:30], "size": size, "원고": True, "shape_iou": 0.80})
    st += text(round(rect["x"], 2), round(rect["y"] - sh, 2), round(rect["w"], 2), h0, temp, size, "#231f20", label=label, leading=lead, align=align,
               font=NOTO, track=trk or None)
    if fill:
        st += _color("frame.fill", fill)
    if stroke:
        st += _color("frame.stroke.color", stroke)
        st.append(F('#side input[data-a="frame.stroke.w"]', round(sw, 2)))
    st.append(F('#side input[data-a="inset4"]', " ".join(f"{round(v, 2):g}" for v in (it_, ir, ib, il))))
    if ind1:
        st.append(F('#side input[data-a="indent_first"]', ind1))
    if gap:
        st.append(F('#side input[data-a="space_after"]', round(gap, 2)))
    st += slot(slot_name)
    if align == "justify":
        st += justify()
    if grep_label:
        st += grep(0, grep_label["re"], grep_label["color"], size=grep_label["size"], label="GREP — 문장 이름표 (A)(B)… 굵은 파랑")
    return rect["h"] - h0, txt


def union(rects):
    x0, y0 = min(r["x"] for r in rects), min(r["y"] for r in rects)
    x1, y1 = max(r["x"] + r["w"] for r in rects), max(r["y"] + r["h"] for r in rects)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "fill": rects[0]["fill"]}


def order_parts(pno):
    """C 문장 배열 한 쪽의 원본 읽기 — 문장 묶음 줄·바탕, 발문, 주어진 문장 줄·바탕, 지문 줄·테두리"""
    sp, dr = spans_of(pno), drawings(pno)
    qt = [o for o in sp if o["font"] == "EliceDigitalBaeumOTF"][0]
    top_rects = [d for d in dr if d["fill"] == "#f9f9f2" and d["n"] == 1 and d["w"] > 100]
    tb = union(top_rects)
    top_rows = [o for o in sp if o["font"].startswith("NotoSans") and tb["y"] < o["base"] < tb["y"] + tb["h"]]
    giv = [d for d in dr if d["fill"] == "#faf4f7" and d["w"] > 100][0]
    giv_rows = [o for o in sp if o["font"].startswith("NotoSans") and giv["y"] < o["base"] < giv["y"] + giv["h"]]
    frame = [d for d in dr if d["stroke"] and not d["fill"] and d["w"] > 100 and d["h"] > 5][0]        # 머리 가로선(높이 0) 말고 테두리 상자
    fr_rows = [o for o in sp if o["font"].startswith("NotoSans") and frame["y"] < o["base"] < frame["y"] + frame["h"]]
    return sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows


def order_body(pno):
    with top_spot():
        return _order_body(pno)


def _order_body(pno):
    sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
    st = [S("쪽 설정 — 자라면 아래 모두 밀기", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-pushrow", "wait": 900}]
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    grow = []
    shift = lambda y: sum(g for b, g in grow if y >= b - 0.3)
    labels = [o for o in top_rows if o["font"] == "NotoSansCJKkr-Bold"]
    lab_size = labels[0]["size"] if labels else BODY
    g, _ = para_box(st, tb, top_rows, BODY, "문장 묶음 — 바탕 칠 글상자(문단마다 (A)…) · 원고 자리 「보기문장」", "보기문장",
                    "(A) 임시 문장 하나.\n(B) 임시 문장 둘.\n(C) 임시 문장 셋.", 0, fill=tb["fill"],
                    grep_label={"re": r"^\([A-Z]\)", "color": labels[0]["color"], "size": lab_size} if labels else None)
    grow.append((tb["y"] + tb["h"], g))
    # 답 줄 — 화살표 둘 · 선 (원본 면 그대로, 위 글이 자라면 같이 밀린다)
    st += [S("답 쓰는 줄 — 화살표 둘 · 선", 1100)]
    for d in [d for d in dr if d["n"] == 3 and d["fill"] and d["y"] > tb["y"] + tb["h"] and d["y"] < qt["base"] - 5]:
        E({"id": f"ar{len(ELEMS[len(PAGES)])}", "x": round(d["x"], 2), "y": round(d["y"], 2), "w": round(d["w"], 2), "h": round(d["h"], 2), "color": d["fill"],
           "see": d["fill"], "pad": 0.2, "ctol": 20})
        st += shape(round(d["x"], 2), round(d["y"] - shift(d["y"]), 2), round(d["w"], 2), round(d["h"], 2), d["fill"], d=poly_d(pno, {"x": d["x"], "y": d["y"]}))
    for d in [d for d in dr if d["n"] == 1 and d["fill"] and d["h"] < 1 and d["w"] > 50 and tb["y"] + tb["h"] < d["y"] < qt["base"] - 5]:
        E({"id": f"ln{len(ELEMS[len(PAGES)])}", "x": round(d["x"], 2), "y": round(d["y"], 2), "w": round(d["w"], 2), "h": round(d["h"], 2), "color": d["fill"],
           "see": d["fill"], "pad": 0.2, "ctol": 20})
        st += box(round(d["x"], 2), round(d["y"] - shift(d["y"]), 3), round(d["w"], 2), round(d["h"], 3), d["fill"])
    # 체크 아이콘 + 발문
    q_icon = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    sh = shift(q_icon["y"])
    o_ = q_icon["sw"] * MM / 2
    E({"id": f"ic{len(ELEMS[len(PAGES)])}", "x": round(q_icon["x"] - o_, 2), "y": round(q_icon["y"] - o_, 2), "w": round(q_icon["w"] + 2 * o_, 2),
       "h": round(q_icon["h"] + 2 * o_, 2), "color": q_icon["stroke"], "see": q_icon["stroke"], "pad": 0.3, "ctol": 30})
    st += image(round(q_icon["x"] - 0.3, 2), round(q_icon["y"] - 0.3 - sh, 2), 4.15, 4.15, os.path.join(HERE, "check.svg"), label="체크 아이콘")
    st += T(win_el(qt, qt["t"].strip(), qt["x"], qt["x1"]), ELB, 400, slot_name="발문", temp="임시 발문 — 다음 물음에 답하시오.", shift=sh, w=round(185 - qt["x"], 1))
    # 주어진 문장 · 지문
    g, _ = para_box(st, giv, giv_rows, BODY, "주어진 문장 — 바탕 칠 글상자 · 원고 자리 「주어진문장」", "주어진문장", "임시 주어진 문장 — 바깥에서 온 문장.",
                    shift(giv["y"]), fill=giv["fill"])
    grow.append((giv["y"] + giv["h"], g))
    g, _ = para_box(st, frame, fr_rows, BODY, "지문 — 테두리 상자 · 원고 자리 「지문」", "지문", temp_passage(400), shift(frame["y"]), stroke=frame["stroke"], sw=frame["sw"])
    grow.append((frame["y"] + frame["h"], g))
    return st


def order_record(lp, rp):
    rec = {"제목": None, "지문번호": [], "보기문장": [], "발문": [], "주어진문장": [], "지문": []}
    for pno in (lp, rp):
        sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec["발문"].append(qt["t"].strip())
        for key, rows in (("보기문장", top_rows), ("주어진문장", giv_rows), ("지문", fr_rows)):
            rec[key].append(para_box([], {"x": 0, "y": 0, "w": 200, "h": 300}, rows, BODY, "", key, "", 0, measure=False)[1])
    return rec


if want(8):
    st += body_pages(84, "C1", "문장 배열", "C문장배열", "⑧ C문장배열", body=order_body)
    CONTENT["C문장배열"] = [order_record(l, l + 1) for l in range(84, 104, 2)]

# ── 원고 넣기 — 바깥 시스템이 보내는 꼴(자리 이름 → 글, 같은 자리가 여러 번이면 쪽 차례대로) ──
if CONTENT:
    st += put_content(CONTENT)

STATE["pages"] = PAGES
json.dump(STATE, open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("정본 단계", len(st), "· 잴 지면", len(ELEMS))
