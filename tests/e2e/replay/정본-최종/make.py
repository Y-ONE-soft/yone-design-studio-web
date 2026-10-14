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
    st = text(20.0, 3.0, 24.0, 9.0, "서체", 9, "#231f20", label=f"서체 등록 — 글상자 하나를 그려 고른 채 「＋ 서체」({fname}) → 등록되면 그 글상자는 지운다")
    st += register_font(os.path.join(FONTS, fname))                     # 「＋ 서체」는 글상자 패널에 있다 — 쪽 설정(Esc) 바로 뒤처럼 아무것도 안 고른 때도 되게
    return st + [{"click": "#side #s-x", "wait": 900}]


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
def divider(pno, num):
    """STEP 간지 한 쪽 — 쪽마다 바탕 색 · 큰 번호 · 지금 단계(채운 원)가 다르다. 값은 그 쪽 원본에서"""
    st = pg_new(pno, f"② STEP 간지 — 원본 {pno}쪽 (STEP {num})")
    st += need_font("Montserrat-ExtraBold.otf")
    el = [e for e in elems_of(pno) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    tx = lambda s, i=0: [e for e in el if e["k"] == "text" and e["text"] == s][i]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "위 크림 띠")
    st += B(rects[2], "띠 아래 선")
    st += B(rects[3], "왼쪽 위 세로 막대")
    st += T(tx("STEP"), MS, 700, label="STEP — Montserrat Bold (불투명 80%, 굵기는 잉크 양으로)", alpha=tx("STEP").get("opacity"), search=0.6)
    st += T(tx(num), MS, 800, label="STEP 번호 — Montserrat ExtraBold")
    st += [S("단계 셋 — 원(지금 단계는 채움) · 선 · 숫자 · 라벨", 1500)]
    for e in [e for e in el if e["k"] == "path"]:
        st += Cfill(e) if e.get("fill") else Cring(e, alpha=e.get("opacity"))
    for e in rects[4:]:
        st += B(e)
    for n in ("1", "2", "3"):
        st += T(tx(n), MS, 800, alpha=tx(n).get("opacity"), search=0.6)
    for lb in ("FRAME", "BUILD UP", "TEST"):
        st += T(tx(lb), MS, 700, alpha=tx(lb).get("opacity"), search=1.2)
    st += T(tx("STEP BY STEP"), MS, 800, label="아래 STEP BY STEP (불투명 90%)", alpha=tx("STEP BY STEP").get("opacity"))
    st += done(f"STEP 간지 {num}", f"p{pno}.png")
    return st


if want(2):
    st += divider(2, "01")

# ── 구성 3 「차례」 (원본 3쪽 — STEP 01) ── 교재 이름 · 단원은 원고 자리(책마다 바뀐다)
def toc(pno, num):
    """차례 한 쪽 — 쪽마다 바탕 색 · 큰 번호 · 진한 탭이 다르다. 교재 이름 · 단원은 원고 자리"""
    st = pg_new(pno, f"③ 차례 — 원본 {pno}쪽 (STEP {num})")
    st += need_font("Montserrat-ExtraBold.otf")
    el = [e for e in elems_of(pno) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    tx = lambda s, i=0: [e for e in el if e["k"] == "text" and e["text"] == s][i]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "위 크림 띠")
    st += B(rects[2], "띠 아래 선")
    st += [S("오른쪽 STEP 탭 셋 — 지금 STEP 은 진하게", 1300)]
    for e in rects[3:]:
        st += B(e)
    big = tx(num)
    st += T(big, MS, 800, label="큰 STEP 번호 — 바탕에 옅게(불투명 14%) · 행간 = 글 크기(상자가 면 안에)", alpha=big.get("opacity"), leading=round(big["size"] * t3k(pno, (big["x"], big["y"], big["w"], big["h"])), 3))
    for n in ("01", "02", "03"):                                         # 탭 글 — 세로(90° 회전), 지금 STEP 만 「STEP 0n」 진하게
        e = tx(n + "EPST") if n == num else tx(n, 1 if n == num else 0)
        st += T(e, MS, 700, label="탭 글 — 세로(90° 회전)" if n == num else None, rot=90, s=f"STEP {n}" if n == num else None, search=0.6, alpha=e.get("opacity"))
    title, unit = tx("마더텅 고1 영어 독해"), tx("11강")
    st += T(title, "Gmarket Sans", 500, label="교재 이름 — 원고 자리 「교재명」 (오른쪽 맞춤)", align="right", slot_name="교재명", temp="교재 이름")
    st += T(unit, "Gmarket Sans", 700, label="단원 — 원고 자리 「단원명」 (오른쪽 맞춤)", align="right", slot_name="단원명", temp="00강")
    CONTENT["교재명"] = CONTENT.get("교재명", []) + [title["text"]]
    CONTENT["단원명"] = CONTENT.get("단원명", []) + [unit["text"]]
    st += done(f"차례 {num}", f"p{pno}.png")
    return st


if want(3):
    st += toc(3, "01")

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


def header_left(pno, title_slot, code="A1", fixed_title=False):
    el = [e for e in elems_of(pno) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    lines = [e for e in el if e["k"] == "line"]
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(rects[0])
    st += rule(max(lines, key=lambda e: clip(e)["w"]))                          # 펼침면에 걸친 선 중 이 쪽에 보이는 것
    st += B(rects[1])
    num = step_no(pno)                                                   # 이 쪽의 STEP 번호(01·02·03)
    stp = dict(span_el(pno, "STEP"), text="STEP " + num)
    stp["w"] = round(span_el(pno, num, size=8.0)["x"] + span_el(pno, num, size=8.0)["w"] - stp["x"], 2)
    st += T(stp, NOTO, 400, label="STEP 01 — 숫자만 굵게(GREP 스타일)")
    st += grep(0, r"\d+")
    st += T(span_el(pno, stage_name(pno), size=8.0), NOTO, 700)        # 단계 이름(FRAME · BUILD UP · TEST)
    st += T(span_el(pno, code, size=25.0), MAMA, 400, label=f"코드 {code} — TTMamablock")
    tt = span_el(pno, title_slot)
    if fixed_title:                                                      # 덧쪽(넘친 글이 만든 쪽)에도 있어야 하는 제목 — 고정 글
        st += T(tt, GMK, 500, label="제목 — 고정 글")
    else:
        st += T(tt, GMK, 500, label="제목 — 원고 자리 「제목」", slot_name="제목", temp="유형 이름 0")
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    ells = [e for e in el if e["k"] == "ellipse"]
    for e in ells:                                                       # 지금 단계 점은 채움, 나머지는 테두리(STEP 마다 다른 점)
        st += Cfill(e) if e.get("fill") else Cring(e)
    for e in lines[1:]:
        if e["w"] < 10 and e["y"] < 24:                                  # 머리 안 짧은 선(단계 점 사이)만 — 본문 꼬리표의 두꺼운 선은 그 구성이 그린다
            st += rule(e)
    for n in ("1", "2", "3"):
        st += T(span_el(pno, n, size=6.0), MS, 700)
    p_, t_ = REF[pno - 1], REF[pno - 1].trimbox                          # 머리 오른쪽 안내 글(구성마다 있는 고정 글 — 「각 문장에서 …」)
    for b_ in p_.get_text("rawdict")["blocks"]:
        for l_ in b_.get("lines", []):
            for s_ in l_["spans"]:
                ink = [c for c in s_["chars"] if c["c"].strip()]
                if ink and round(s_["size"], 1) == 9.0 and (s_["origin"][1] - t_.y0) * MM < 24 and 85 < (ink[0]["origin"][0] - t_.x0) * MM < 205:
                    o = {"t": "".join(c["c"] for c in s_["chars"]), "font": s_["font"], "size": 9.0, "color": "#%06x" % s_["color"],
                         "x": (ink[0]["origin"][0] - t_.x0) * MM, "x1": (ink[-1]["bbox"][2] - t_.x0) * MM, "base": (s_["origin"][1] - t_.y0) * MM}
                    st += T(win_el(o, o["t"].strip(), o["x"], o["x1"]), ELB, 400, label="머리 안내 글")
    return st


def step_no(pno):
    """쪽의 STEP 번호 — 오른쪽 탭 중 「STEP 0n」, 없으면 머리 「STEP」 옆 숫자"""
    for t in tab_texts(pno):
        if t.startswith("STEP"):
            return t.split()[-1]
    sp = spans_of(pno)
    stp = [o for o in sp if o["t"].strip() == "STEP" and o["size"] == 8.0]
    if stp:
        nxt = [o for o in sp if abs(o["base"] - stp[0]["base"]) < 0.3 and o["x"] > stp[0]["x"] and o["t"].strip().isdigit()]
        if nxt:
            return nxt[0]["t"].strip()
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    for b in p.get_text("rawdict")["blocks"]:                            # 왼쪽 면 머리(STEP + 숫자) — 가로 글 아무 데서나
        for l in b.get("lines", []):
            for sp_ in l["spans"]:
                tx = "".join(c["c"] for c in sp_["chars"]).strip()
                if round(sp_["size"], 1) == 8.0 and tx.isdigit() and (sp_["origin"][1] - t.y0) * MM < 12:
                    return tx
    return "01"


def stage_name(pno):
    """머리의 단계 이름 — STEP 옆 8pt 굵은 글(숫자·STEP 말고)"""
    for o in spans_of_all(pno):
        tx = o["t"].strip()
        if o["size"] == 8.0 and "Bold" in o["font"] and tx and not tx.isdigit() and tx != "STEP":
            return tx
    return "FRAME"


def spans_of_all(pno):
    """머리까지 포함한 가로 글 조각(spans_of 는 본문 24mm 아래만)"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    return [{"t": "".join(c["c"] for c in sp["chars"]), "font": sp["font"], "size": round(sp["size"], 1)}
            for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", []) if l["dir"] == (1.0, 0.0) for sp in l["spans"]
            if 0 <= (sp["origin"][0] - t.x0) * MM < 205]


def tab_texts(pno):
    """오른쪽 면 탭 글(아래→위 세로 글, 6.5pt) — 원본은 같은 글이 두 벌 겹쳐 있어 한 번씩, 위에서 아래 차례"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    got = {}
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (0.0, -1.0):
                continue
            for sp_ in l["spans"]:
                tx = "".join(c["c"] for c in sp_["chars"]).strip()
                if round(sp_["size"], 1) == 6.5 and tx and (sp_["origin"][0] - t.x0) * MM < 212:
                    got.setdefault(tx, (sp_["origin"][1] - t.y0) * MM)
    return [k for k, _ in sorted(got.items(), key=lambda kv: kv[1])]


class top_spot:
    """새 개체를 머리 빈 곳(110, 3)에 그려 옮긴다 — 본문 글상자가 원고만큼 자라는 쪽에서 아래쪽(기본 자리)에 그리면 밀려 면 밖으로 간다"""
    def __enter__(self):
        import mkpage as _mk
        self.mk, self.old = _mk, _mk.SPOT
        _mk.SPOT = {"mm": [110, 3]}

    def __exit__(self, *a):
        self.mk.SPOT = self.old


def body_pages(lp, code, title, key, label, body=None, rep="each_set", cont=False, fixed_title=False):
    """펼침면 두 쪽(본문 구성 견본) — 왼쪽: 머리·본문·꼬리 / 오른쪽: 머리(코드·꼬리표)·탭·본문·꼬리. 둘 다 「원고마다」(이름 = key).
    body(쪽) = 그 구성의 본문 대본(없으면 지문 둘 — 어휘 선택). rep=None 이면 「한 번만」(흐르는 쪽), cont 면 두 면이 서로 「넘치면 이어 갈 면」"""
    body = body or passage_pair
    st = pg_new(lp, f"{label} — 원본 {lp}쪽 (펼침면 왼쪽)")
    st += header_left(lp, title, code, fixed_title)
    st += body(lp)
    st += [S("꼬리 — 쪽 번호(책이 채움) · STEP BY STEP", 1200)]
    with top_spot():
        st += T(span_el(lp, str(lp), size=6.0), EL, 700, label="쪽 번호 — 시스템 자리 「쪽 번호」", bind="sys.page_no")
        st += T(span_el(lp, "STEP BY STEP", size=6.0), EL, 700)
    st += page_setup(key, rep)
    st += done(f"{label} 왼쪽", f"p{lp}.png")
    li = len(PAGES) - 1                                                  # 왼쪽 면의 쪽 목록 차례(0부터)

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
    for t in tab_texts(rp):                                              # 탭 글 — 이 STEP 만 「STEP 0n」
        st += T(span_el(rp, t, size=6.5), MS, 700, rot=-90)
    st += body(rp)
    st += [S("꼬리 — STEP01 · 쪽 번호(책이 채움, 오른쪽 맞춤)", 1200)]
    with top_spot():
        foot = next(o["t"].strip() for o in spans_of_all(rp) if o["size"] == 6.0 and o["t"].strip().replace(" ", "").startswith("STEP0"))   # 꼬리 STEP 글(STEP01 · STEP 02)
        st += T(span_el(rp, foot, size=6.0), EL, 700)
        st += T(span_el(rp, str(rp), size=6.0), EL, 700, align="right", label="쪽 번호 — 시스템 자리 「쪽 번호」", bind="sys.page_no")
    st += page_setup(f"{key} 오른쪽" if cont else None, rep)
    if cont:                                                             # 넘친 글 — 오른쪽 면 → 왼쪽 면 → 오른쪽 면 … 덧쪽이 번갈아(인디자인 마스터 A·B)
        st += [S("넘치면 이어 갈 면 — 오른쪽 면은 왼쪽 면으로", 1000), {"pick": {"at": "#side #s-cont", "text": key}, "wait": 900}]
        st += [S("왼쪽 면으로 가서 — 넘치면 오른쪽 면으로", 1000), {"click": f'#rail .pg[data-i="{li}"]', "wait": 1500}]
        st += page_setup() + [{"pick": {"at": "#side #s-cont", "text": f"{key} 오른쪽"}, "wait": 900}]
        st += [{"js": f"(() => {{ const r = docPages(); const a = r[{li}], b = r[{li} + 1]; if (a.cont !== b.id || b.cont !== a.id) throw new Error('이어 갈 면 지정 실패'); return '이어 갈 면 서로 지정'; }})()"}]
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


# ── 구성 5 「A본문OX」 (원본 24~43쪽 = 펼침면 10벌 · 원고마다) — 견본 = 24·25쪽 ──
# 흐름 방식(2026-10-14 사용자 확정 — 인디자인처럼): 지문 · 문제 · 진술을 텍스트 프레임 하나에 흘린다(자리 A2_BIND). 원고에 없는 문제는 문단이 안 생긴다
# — 접기 묶음 · 아래 모두 밀기를 쓰지 않는다. 진술 끝 O/X 칸 = 데이터 필드 「진술」의 고정 개체(문단 끝).
from mkpage import _color                                               # noqa: E402
LOTTE, ELB, LINK = "12LotteMartDreamBold", "Elice DigitalBaeum OTF", "#b5ac9c"
ELICE = {"EliceDXNeolliOTF-Md": (EL, 500), "EliceDigitalBaeumOTF": (ELB, 400)}
OXP = {}                                                                 # O/X 부품 — 문서에 한 번 만든다(부품 id)
PARTN = [0]


UL = {"line": 0.176, "line_off": 0.71, "line_color": "#231f20"}              # 원본 밑줄(굵기 · 기준선 → 가운데 · 색) — 문자 스타일 「밑줄」 · 「밑줄 보통」(한 권에 하나)


def pst_steps(styles, label="단락 스타일"):
    """단락 스타일 — 스타일 · 색상 견본 창 「＋ 단락 스타일」 → 이름 → 칸마다(체크 칸은 누른다)"""
    st = [S(label + " — 스타일 · 색상 견본 창", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in styles:
        q = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together", "shade_fit"):
                st.append({"click": "input" + q(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    return st + [{"click": "#sheet-x", "wait": 900}]


def cs_steps(styles, label="문자 스타일"):
    """문자 스타일 — 스타일 · 색상 견본 창 「＋ 문자 스타일」 → 이름 → 칸마다(체크 칸 b · i · u 는 누른다 — 밑줄 칸은 u 를 켜야 나온다)"""
    st = [S(label + " — 스타일 · 색상 견본 창", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, props in styles:
        sel = lambda k: f'#sbody [data-cs="{name}:{k}"]'
        st += [S(f"문자 스타일 「{name}」", 800), {"answer": name}, {"click": "#cs-new", "wait": 1200}]
        for k, v in props.items():
            if k in ("b", "i", "u"):
                st.append({"click": sel(k), "wait": 700})
            elif k in ("weight", "u_style"):
                st.append({"pick": {"at": sel(k), "value": str(v)}, "wait": 600})
            else:
                st.append(F(sel(k), v, 600))
    return st + [{"click": "#sheet-x", "wait": 900}]


ULF = {}                                                                 # 밑줄 문자 스타일을 이 문서에 만들었나(한 번만)
UL_CS = [("밑줄", {"u": 1, "weight": 500, "line": UL["line"], "line_off": UL["line_off"], "line_color": UL["line_color"]}),
         ("밑줄 보통", {"u": 1, "line": UL["line"], "line_off": UL["line_off"], "line_color": UL["line_color"]})]


def marks_runs(t, hint_cs=None):
    """원고 글의 약속 표시 → 꾸밈 조각(인디자인 태그 텍스트처럼 — 표시를 감추는 GREP 대신): {글} 밑줄(Medium) · _{글} 밑줄 ·
    hint_cs 면 {첫 글자} 를 그 문자 스타일로(빈칸 힌트). 표시가 없으면 글 그대로"""
    if "{" not in t:
        return t
    out, k = [], 0
    for m in re.finditer(r"(_?)\{([^{}]*)\}", t):
        if m.start() > k:
            out.append(t[k:m.start()])
        out.append({"t": m.group(2), "cs": hint_cs or ("밑줄 보통" if m.group(1) else "밑줄")})
        k = m.end()
    if k < len(t):
        out.append(t[k:])
    return out


def new_part_id():
    """이 대본이 만든 부품 차례 — 빈 문서에서 시작하므로 편집기가 p_1, p_2 … 로 붙인다"""
    PARTN[0] += 1
    return f"p_{PARTN[0]}"


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
    OXP["id"] = new_part_id()
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


A2_BIND = "지문+문제번호+발문+선지+진술번호+진술"
A2 = {}


def a2_parts(pno):
    """원본 쪽 — 지문 · 바탕 · 문제 머리들(번호 · 막대 · 발문) · 선지 줄 · 진술(번호 · 줄들 · O/X 칸)"""
    sp, dr = spans_of(pno), drawings(pno)
    ps = passages(pno)[0]
    bgs = [d for d in dr if d["fill"] and d["fill"] != "#ffffff" and d["n"] == 1 and d["w"] > 100 and ps["top"] - 8 < d["y"] < ps["top"] + 2]
    outer, inner = max(bgs, key=lambda d: d["w"]), min(bgs, key=lambda d: d["w"])
    qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
    qs = []
    for k, q in enumerate(qh):
        qt = min([o for o in sp if o["font"] in ELICE and abs(o["base"] - q["base"]) < 1.5], key=lambda o: abs(o["base"] - q["base"]))
        bar = [c for c in q["ink"] if c[0] == "|"][0]
        ln = [o for o in sp if o["font"].startswith("NotoSans") and q["base"] + 2 < o["base"] < qh[k + 1]["base"] - 2] if k + 1 < len(qh) else []
        qs.append({"q": q, "qt": qt, "bar": bar, "ln": ln})
    nums = [o for o in sp if LOTTE in o["font"]]
    stext = [o for o in sp if o["font"].startswith("NotoSans") and o["base"] > qh[-1]["base"] + 2]
    oxs = [d for d in dr if d["n"] == 20 and d["fill"] == "#ffffff"]
    sts = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        ln = [o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1]
        bx = min([d for d in oxs if n["base"] - 6 < d["y"] < nxt - 3], key=lambda d: d["y"])
        sts.append({"n": n, "ln": ln, "bx": bx})
    return sp, dr, ps, outer, inner, qs, sts


def a2_style(pno):
    """견본 쪽 — 단락 스타일 값(줄 상자 기준 문단 사이 · 음영 여백 · 진술 들여쓰기 · O/X 칸 자리)"""
    sp, dr, ps, outer, inner, qs, sts = a2_parts(pno)
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    lead = lead_mm / MM
    rows = [o for o in sp if o["size"] == BODY and abs(o["base"] - ps["base1"]) < 0.5]
    trk = gaps_track([c for o in rows for c in o["ink"]], BODY)
    top_t = top_of(ps["base0"], BODY, NOTO, 400, lead)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))
    q0 = qs[0]
    # 텍스트 프레임 = 문제 번호 왼쪽 ~ 선지 · 진술 줄 오른쪽 끝(양끝 맞춘 줄). 지문은 그 안에서 왼쪽 · 오른쪽 들여쓰기 + 음영(너비 「텍스트」)
    x0 = min([q["q"]["x"] for q in qs] + [t["n"]["x"] for t in sts])
    x1 = max(o["x1"] for o in [o for q in qs for o in q["ln"]] + [o for t in sts for o in t["ln"]])
    qfam, qwt = ELICE[q0["qt"]["font"]]
    qsz = q0["qt"]["size"]
    qlead = 15.0
    pass_bot = outer["y"] + outer["h"]
    sb_q1 = top_of(q0["q"]["base"], qsz, qfam, qwt, qlead) - pass_bot
    ln0 = q0["ln"]
    csz = ln0[0]["size"]
    cl = min(b["base"] - a["base"] for a, b in zip(ln0, ln0[1:])) / MM
    ctrk = gaps_track([c for pa in choice_paras(ln0) for c in pa[-1]["ink"]], csz)
    sb_c = top_of(ln0[0]["base"], csz, NOTO, 400, cl) - (q0["q"]["base"] + below(q0["q"]["base"], qsz, qfam, qwt, qlead))
    lc = ln0[-1]
    q1 = qs[1]
    sb_q = top_of(q1["q"]["base"], qsz, qfam, qwt, qlead) - (lc["base"] + below(lc["base"], csz, NOTO, 400, cl))
    # 진술 — 첫 진술의 둘째 줄(이어지는 줄) x 가 들여쓰기, 번호는 내어쓰기로 첫 줄 앞에 붙인다
    s0 = next(t for t in sts if len(t["ln"]) > 1)
    first, cont = s0["ln"][0], s0["ln"][1]
    ssz = first["size"]
    slead_mm = cont["base"] - first["base"]
    slead = slead_mm / MM
    last_lines = [t["ln"][-1] for t in sts]
    strk = line_track(last_lines, NOTO, 400)
    sb_s1 = top_of(sts[0]["ln"][0]["base"], ssz, NOTO, 400, slead) - (q1["q"]["base"] + below(q1["q"]["base"], qsz, qfam, qwt, qlead))
    gaps = []
    for a_, b_ in zip(sts, sts[1:]):                                     # 진술 사이 — O/X 칸이 제 줄로 넘어간 진술은 그 줄까지가 문단
        same = abs(a_["bx"]["y"] + a_["bx"]["h"] - a_["ln"][-1]["base"]) < 2.5
        lb = a_["ln"][-1]["base"] + (0 if same else slead_mm)
        gaps.append(top_of(b_["ln"][0]["base"], ssz, NOTO, 400, slead) - (lb + below(lb, ssz, NOTO, 400, slead)))
    import statistics
    sb_s = statistics.median(gaps)
    t_same = next(t for t in sts if abs(t["bx"]["y"] + t["bx"]["h"] - t["ln"][-1]["base"]) < 2.5)   # O/X 칸이 끝 줄 옆인 진술 — 칸 자리
    _, _, adv = face(NOTO, 400)
    lst = t_same["ln"][-1]
    ox_gap = t_same["bx"]["x"] - lst["x1"] - adv(" ") * ssz * MM - 2 * strk / 1000 * ssz * MM
    ox_drop = t_same["bx"]["y"] + t_same["bx"]["h"] - lst["base"]
    A2.update(x=x0, ox=outer["x"], top=outer["y"], w=round(x1 - x0, 2), fill=inner["fill"], pad=round(ps["x"] - outer["x"], 2), pad_top=round(top_t - outer["y"], 2),
              p_ind=round(outer["x"] - x0, 2), p_ind_r=round(x1 - outer["x"] - outer["w"], 2),
              pad_bottom=round(pass_bot - (top_t + ps["lines"] * lead_mm), 2), lead=round(lead, 2), trk=trk,
              qfam=qfam, qwt=qwt, qsz=qsz, qlead=qlead, q_ind=round(q0["q"]["x"] - x0, 2), num_color=q0["q"]["color"],
              inline_w=round(q0["bar"][1] - q0["q"]["x"], 2), num_trk=gaps_track(q0["q"]["ink"][:2], 10, EL, 700) or 1,
              csz=csz, cl=round(cl, 2), ctrk=ctrk, c_ind=round(ln0[0]["x"] - x0, 2), sb_c=round(sb_c, 2),
              sb_q=round(sb_q, 2), after_p=round(sb_q1 - sb_q, 2),
              ssz=ssz, slead=round(slead, 2), strk=strk, s_ind=round(cont["x"] - x0, 2), s_first=round(s0["n"]["x"] - cont["x"], 2),
              s_inline_w=round(first["x"] - s0["n"]["x"], 2), s_num_color=s0["n"]["color"], s_num_size=s0["n"]["size"],
              sb_s1=round(sb_s1, 2), sb_s=round(sb_s, 2), ox_gap=round(ox_gap, 3), ox_drop=round(ox_drop, 3))


def a2_styles_steps():
    G = A2
    sty = [("OX·지문", {"font": NOTO, "size": BODY, "leading": G["lead"], "tracking": G["trk"], "color": "#231f20", "align": "justify",
                      "indent": G["p_ind"], "indent_right": G["p_ind_r"], "shade_fit": True,
                      "shade": G["fill"], "pad": G["pad"], "pad_top": G["pad_top"], "pad_bottom": G["pad_bottom"], "space_after": G["after_p"]}),
           ("OX·문제번호", {"font": EL, "weight": 700, "size": 10, "color": G["num_color"], "tracking": G["num_trk"]}),
           ("OX·발문", {"font": G["qfam"], "weight": G["qwt"], "size": G["qsz"], "leading": G["qlead"], "color": "#231f20",
                      "indent": G["q_ind"], "space_before": G["sb_q"], "keep_next": True}),
           ("OX·선지", {"font": NOTO, "size": G["csz"], "leading": G["cl"], "tracking": G["ctrk"], "color": "#231f20", "align": "justify",
                      "indent": G["c_ind"], "space_before": G["sb_c"], "space_same": 0.01, "keep_together": True}),
           ("OX·진술번호", {"font": LOTTE, "size": G["s_num_size"], "color": G["s_num_color"], "tracking": 1}),
           ("OX·진술", {"font": NOTO, "size": G["ssz"], "leading": G["slead"], "tracking": G["strk"], "color": "#231f20", "align": "justify",
                      "indent": G["s_ind"], "indent_first": G["s_first"], "space_before": G["sb_s1"], "space_same": G["sb_s"], "keep_together": True})]
    st = [S("단락 스타일 — 본문 O/X(자리마다 하나, 스타일 · 색상 견본 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        q = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together", "shade_fit"):
                st.append({"click": "input" + q(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def _ox_body(pno, sp, dr):
    st = []
    if "x" not in A2:
        a2_style(pno)
        st += a2_styles_steps()
    G = A2
    sp, dr, ps, outer, inner, qs, sts = a2_parts(pno)
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(outer)[k] for k in ("x", "y", "w", "h")}, "color": inner["fill"], "see": inner["fill"], "pad": 0.6, "ctol": 12, "원고": True})
    fx = G["x"] + outer["x"] - G["ox"]                                    # 이 쪽의 프레임 왼쪽(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    right = max([fx + G["w"]] + [t["bx"]["x"] + t["bx"]["w"] + 0.5 for t in sts])   # 원고 창 = 본문 + 줄 끝 O/X 칸까지
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(right - fx, 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    bars = [d for d in dr if d["fill"] == LINK and d["w"] < 1]
    for t in sts:                                                        # O/X 칸 — 진술 글을 따라 놓이는 원고 요소(줄 끝 · 다음 줄)
        bx = t["bx"]
        ob = min(bars, key=lambda d: abs(d["x"] - bx["x"] - 10) + abs(d["y"] - bx["y"]))
        o = bx["sw"] * MM / 2
        E({"id": f"ox{len(ELEMS[len(PAGES)])}", "x": round(bx["x"] - o, 2), "y": round(bx["y"] - o, 2), "w": round(bx["w"] + 2 * o, 2), "h": round(bx["h"] + 2 * o, 2),
           "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30, "원고": True})
        E({"id": f"oxb{len(ELEMS[len(PAGES)])}", "x": round(ob["x"], 2), "y": round(ob["y"], 2), "w": round(ob["w"], 2), "h": round(ob["h"], 2),
           "color": LINK, "see": LINK, "pad": 0.15, "ctol": 30, "원고": True})
    st += [S("본문 — 텍스트 프레임 하나(지문 · 문제 · 진술이 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), round(G["top"], 2), round(G["w"], 2), round(bot - G["top"], 2),
               "임시 지문 — 원고가 오면 지문 · 문제 · 진술이 이 프레임 하나에 차례로 흐른다.", BODY, "#231f20",
               label="본문 글상자 — 한 줄기(" + A2_BIND + ")", font=NOTO, leading=G["lead"])
    st += slot(A2_BIND, label="자리 — " + A2_BIND + " (원고에 나온 차례대로 한 줄기)")
    for nm in A2_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "OX·" + nm}, "wait": 450})
    st += [S("문제번호 · 진술번호는 첫 줄 앞에 붙인다 — 번호 칸 폭 · 발문 글머리 「|」", 900),
           {"click": '#side input[data-a="slotfmt.문제번호.inline"]', "wait": 600},
           F('#side input[data-a="slotfmt.문제번호.inline_w"]', G["inline_w"], 600),
           F('#side input[data-a="slotfmt.발문.bullet_text"]', "| ", 600),
           {"click": '#side input[data-a="slotfmt.진술번호.inline"]', "wait": 600},
           F('#side input[data-a="slotfmt.진술번호.inline_w"]', G["s_inline_w"], 600)]
    st += [S("진술 끝에 O/X 칸 — 데이터 필드 「진술」의 고정 개체(문단 끝, 띄어 붙이기)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.진술.anc.part"]', "value": OXP["id"]}, "wait": 900},
           F('#side input[data-a="slotfmt.진술.anc.gap"]', G["ox_gap"], 600), F('#side input[data-a="slotfmt.진술.anc.dy"]', G["ox_drop"], 600),
           {"click": '#side input[data-a="slotfmt.진술.anc.space"]', "wait": 600}]
    ul = [d for d in dr if d["h"] < 0.3 and d["stroke"] and any(abs(d["y"] - q["q"]["base"]) < 2 and q["qt"]["x"] <= d["x"] <= q["qt"]["x1"] for q in qs)]
    if ul:                                                               # 발문의 부정어 밑줄(「않는」) — GREP 스타일(원본 선 굵기·자리)
        u = ul[0]
        qb = next(q for q in qs if abs(u["y"] - q["q"]["base"]) < 2)
        st += grep(0, "않는|아닌|틀린|없는", bold=False, underline=True, line=round(u["sw"] * MM, 3), line_off=round(u["y"] - qb["qt"]["base"], 2),
                   line_color=u["stroke"], label="GREP — 발문의 부정어(않는·아닌·틀린·없는)에 밑줄")
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]   # 큰 본문 프레임 고른 것을 풀고 다음 개체를 그린다
    return st


def ox_record(lp, rp):
    """본문 O/X 펼침면 하나의 원고 — 쪽마다 지문 번호 + 한 줄기(지문 · 문제마다 번호 · 발문 · 선지 · 진술마다 번호 · 글). 없는 문제는 안 보낸다"""
    rec = {"제목": None, "지문번호": [], A2_BIND: []}
    for pno in (lp, rp):
        sp, dr, ps, outer, inner, qs, sts = a2_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        items = [[["지문", ps["text"]]]]
        for q in qs:
            it = [["문제번호", "".join(c[0] for c in q["q"]["ink"][:2])], ["발문", q["qt"]["t"].strip()]]
            if q["ln"]:
                it.append(["선지", "\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(q["ln"]))])
            items.append(it)
        for t in sts:
            items.append([["진술번호", t["n"]["t"].strip()], ["진술", " ".join(o["t"].strip() for o in t["ln"])]])
        rec[A2_BIND].append(items)
    return rec


if want(4):                                                             # 구성 5 의 글 읽기 함수(spans_of 등)를 머리 STEP 번호 읽기가 쓴다 — 그 정의 뒤에서 돈다(책 차례는 그대로 4 → 5)
    st += body_pages(4, "A1", "어휘 선택 1", "A어휘선택", "④ A어휘선택")
    CONTENT["A어휘선택"] = [spread_record(l, l + 1) for l in range(4, 24, 2)]          # 펼침면 10벌 = 레코드 10

if want(5):
    st += body_pages(24, "A2", "본문 O/X", "A본문OX", "⑤ A본문OX", body=ox_body)
    CONTENT["A본문OX"] = [ox_record(l, l + 1) for l in range(24, 44, 2)]          # 펼침면 10벌 = 레코드 10

# ── 구성 6 「B본문정리」 (원본 44~63쪽 = 펼침면 10벌 · 원고마다) — 견본 = 44·45쪽 ──
# 흐름 방식(2026-10-14): 텍스트 프레임 하나에 지문(음영) · 주제 · 글제목 · 발문 · 문제지문(음영) · 주석(같은 음영, 오른쪽 맞춤) · 선지.
# 꼬리표 「주제」 「제목」 · 체크 아이콘 = 그 필드 첫 문단의 고정 개체(사용자 정의 위치, 왼쪽 바깥). 주석이 없으면 문단이 안 생겨 상자가 줄어든다.
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


B1_TOP = "지문+주제+글제목"                                               # 위 프레임 — 원고만큼
B1_BIND = "발문+문제지문+주석+선지"                                        # 아래 문제 프레임 — 제자리(원본 20쪽 모두 같은 높이)
B1 = {}
B1P = {}                                                                 # 부품 — 꼬리표 「주제」 · 「제목」 · 체크 아이콘


def group_part(st, n, X0, Y0, w, h):
    """빈 자리(X0, Y0)에 그린 개체 n 개를 범위로 골라 그룹 → 부품, 지면에서는 지운다(부품은 라이브러리에 남는다)"""
    st += [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1000), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
           S(f"범위로 {n}개를 골라 그룹 → 부품", 1200),
           {"drag": {"from": {"mm": [X0 - 2, Y0 - 2]}, "to": {"mm": [X0 + w + 2, Y0 + h + 2]}}, "wait": 900},
           {"js": f"(() => {{ if (sels.size !== {n}) throw new Error('고른 것 ' + sels.size + ' ({n} 이어야)'); return '고른 것 {n}'; }})()"},
           {"click": "#side #s-group", "wait": 1500},
           {"js": f"(() => {{ const p = LIB.parts[LIB.parts.length - 1]; if (!p || p.atoms.length !== {n}) throw new Error('부품 안 생김'); return '부품 ' + p.id; }})()"},
           S("지면의 그룹은 지운다", 900), {"key": "Delete", "wait": 900},
           {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]
    return new_part_id()


def b1_parts(pno):
    sp, dr = spans_of(pno), drawings(pno)
    ps = passages(pno)[0]
    rows = [o for o in sp if o["size"] == BODY and ps["base0"] - 0.5 <= o["base"] <= ps["base1"] + 0.5 and o["font"].endswith("Regular")]
    rect = passage_bg(dr, ps)
    tags = sorted([d for d in dr if d["n"] == 1 and d["fill"] and d["fill"] != "#ffffff" and 3 < d["h"] < 4 and 6 < d["w"] < 9], key=lambda d: d["y"])
    q_icon = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    tg = []
    for k, t in enumerate(tags):
        nxt = tags[k + 1]["y"] if k + 1 < len(tags) else q_icon["y"]
        tt = min([o for o in sp if o["font"].startswith("EliceDigitalBaeumOTF-B") and o["color"] == "#ffffff"], key=lambda o: abs(o["base"] - t["y"] - t["h"]))
        thick = [d for d in dr if d["n"] == 1 and d["stroke"] == t["fill"] and d["h"] < 0.1 and abs(d["y"] - t["y"] - t["h"] / 2) < 1]
        ln = [o for o in sp if o["font"] == "NotoSansCJKkr-Medium" and t["y"] - 1 < o["base"] < nxt - 1]
        tg.append({"r": t, "tt": tt, "thick": thick, "ln": ln, "name": TAGNAME.get(tt["t"].strip(), tt["t"].strip())})
    qt = [o for o in sp if o["font"] == "EliceDigitalBaeumOTF" and abs(o["base"] - q_icon["y"] - q_icon["h"]) < 2][0]
    p2 = [g_ for g_ in passages(pno) if g_["base0"] > qt["base"]][0]
    rows2 = [o for o in sp if o["size"] == BODY and o["font"].endswith("Regular") and p2["base0"] - 0.5 <= o["base"] <= p2["base1"] + 0.5 and not o["t"].strip().startswith("*")]
    rects = sorted([d for d in dr if d["fill"] == "#eaf0f7" and d["n"] == 1 and d["w"] > 100 and d["y"] > qt["base"]], key=lambda d: d["y"])
    foot = [o for o in sp if o["size"] == BODY and o["t"].strip().startswith("*")]
    cl = [o for o in sp if o["font"] == "NotoSansCJKkr-Regular" and o["size"] == 9.0 and o["base"] > rects[0]["y"] + rects[0]["h"]]
    return sp, dr, ps, rows, rect, tg, q_icon, qt, p2, rows2, rects, foot, cl


def b1_style(pno):
    sp, dr, ps, rows, rect, tg, q_icon, qt, p2, rows2, rects, foot, cl = b1_parts(pno)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))
    # 텍스트 프레임 = 문제 지문 바탕 폭(가장 넓은 문단). 지문은 그 안에서 왼쪽 · 오른쪽 들여쓰기 + 음영(너비 「텍스트」), 꼬리표 · 체크는 프레임 왼쪽 바깥
    x0 = rects[0]["x"]
    x1 = max([rect["x"] + rect["w"]] + [d["x"] + d["w"] for d in rects])
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    lead = lead_mm / MM
    trk = gaps_track([c for c in rows[-1]["ink"]], BODY)
    top_t = top_of(rows[0]["base"], BODY, NOTO, 400, lead)
    G = dict(x=x0, ox=rect["x"], top=rect["y"], w=round(x1 - x0, 2), fill1=rect["fill"], pad1=round(rows[0]["x"] - rect["x"], 2), pad1_top=round(top_t - rect["y"], 2),
             p_ind=round(rect["x"] - x0, 2), p_ind_r=round(x1 - rect["x"] - rect["w"], 2),
             pad1_bottom=round(rect["y"] + rect["h"] - (top_t + ps["lines"] * lead_mm), 2), lead=round(lead, 2), trk=trk)
    prev_bot = rect["y"] + rect["h"]                                     # 앞 문단 줄 상자 아래 끝
    for t in tg:
        ln = t["ln"]
        lmm = (ln[1]["base"] - ln[0]["base"]) if len(ln) > 1 else 6.75
        G[t["name"]] = dict(lead=round(lmm / MM, 2), trk=gaps_track([c for o in ln for c in o["ink"]], 9, NOTO, 500) or 1,
                            ind=round(min(o["x"] for o in ln) - x0, 2), sb=round(top_of(ln[0]["base"], 9, NOTO, 500, lmm / MM) - prev_bot, 2),
                            tag_x=round(t["r"]["x"] - x0, 2), tag_dy=round(t["r"]["y"] - top_of(ln[0]["base"], 9, NOTO, 500, lmm / MM), 2))
        prev_bot = ln[-1]["base"] + below(ln[-1]["base"], 9, NOTO, 500, lmm / MM)
    qsz = qt["size"]
    qlead = 15.0
    G["발문"] = dict(size=qsz, ind=round(qt["x"] - x0, 2), sb=round(top_of(qt["base"], qsz, ELB, 400, qlead) - prev_bot, 2), lead=qlead,
                   ic_x=round(q_icon["x"] - 0.3 - x0, 2), ic_dy=round(q_icon["y"] - 0.3 - top_of(qt["base"], qsz, ELB, 400, qlead), 2))
    r1 = rects[0]
    lead2 = (rows2[-1]["base"] - rows2[0]["base"]) / (len(rows2) - 1)
    trk2 = gaps_track([c for c in rows2[-1]["ink"]], BODY)
    top2 = top_of(rows2[0]["base"], BODY, NOTO, 400, lead2 / MM)
    G["문제지문"] = dict(fill=r1["fill"], lead=round(lead2 / MM, 2), trk=trk2, pad=round(rows2[0]["x"] - r1["x"], 2), pad_top=round(top2 - r1["y"], 2),
                     pad_bottom=round(r1["y"] + r1["h"] - (top2 + len(rows2) * lead2), 2),
                     sb=round(r1["y"] - (qt["base"] + below(qt["base"], qsz, ELB, 400, qlead)), 2))
    box_bot = max(d["y"] + d["h"] for d in rects)
    if foot:                                                             # 주석 — 같은 바탕 상자에 이어 붙인 오른쪽 맞춤 줄
        f = foot[0]
        ftop = top_of(f["base"], BODY, NOTO, 400, lead2 / MM)
        G["주석"] = dict(trk=gaps_track(f["ink"], BODY) or -40, right=round(r1["x"] + r1["w"] - f["x1"], 2),
                       sb=round(ftop - (rows2[-1]["base"] + below(rows2[-1]["base"], BODY, NOTO, 400, lead2 / MM)), 2),
                       pad_bottom=round(box_bot - (ftop + lead2), 2))
    csz = 9.0
    cl_mm = min(b["base"] - a["base"] for a, b in zip(cl, cl[1:]))
    G["선지"] = dict(lead=round(cl_mm / MM, 2), trk=gaps_track([c for pa in choice_paras(cl) for c in pa[-1]["ink"]], csz), ind=round(cl[0]["x"] - x0, 2),
                   sb=round(top_of(cl[0]["base"], csz, NOTO, 400, cl_mm / MM) - box_bot, 2))
    B1.update(G)


def b1_styles_steps():
    G = B1
    B_ = {"font": NOTO, "size": BODY, "color": "#231f20", "align": "justify"}
    sty = [("정리·지문", dict(B_, leading=G["lead"], tracking=G["trk"], indent=G["p_ind"], indent_right=G["p_ind_r"], shade_fit=True,
                          shade=G["fill1"], pad=G["pad1"], pad_top=G["pad1_top"], pad_bottom=G["pad1_bottom"])),
           ("정리·주제", {"font": NOTO, "weight": 500, "size": 9, "color": "#231f20", "leading": G["주제"]["lead"], "tracking": G["주제"]["trk"],
                       "indent": G["주제"]["ind"], "space_before": G["주제"]["sb"], "space_same": 0.01}),
           ("정리·글제목", {"font": NOTO, "weight": 500, "size": 9, "color": "#231f20", "leading": G["글제목"]["lead"], "tracking": G["글제목"]["trk"],
                        "indent": G["글제목"]["ind"], "space_before": G["글제목"]["sb"], "space_same": 0.01}),
           ("정리·발문", {"font": ELB, "weight": 400, "size": G["발문"]["size"], "leading": G["발문"]["lead"], "color": "#231f20",
                       "indent": G["발문"]["ind"], "space_before": G["발문"]["sb"], "keep_next": True}),
           ("정리·문제지문", dict(B_, leading=G["문제지문"]["lead"], tracking=G["문제지문"]["trk"], shade=G["문제지문"]["fill"], pad=G["문제지문"]["pad"],
                            pad_top=G["문제지문"]["pad_top"], pad_bottom=G["문제지문"]["pad_bottom"], space_before=G["문제지문"]["sb"])),
           ("정리·주석", dict(B_, align="right", leading=G["문제지문"]["lead"], tracking=G["주석"]["trk"], shade=G["문제지문"]["fill"],
                          pad=G["문제지문"]["pad"], pad_bottom=G["주석"]["pad_bottom"], space_before=G["주석"]["sb"])),
           ("정리·선지", {"font": NOTO, "size": 9, "color": "#231f20", "align": "justify", "leading": G["선지"]["lead"], "tracking": G["선지"]["trk"],
                       "indent": G["선지"]["ind"], "space_before": G["선지"]["sb"], "space_same": 0.01, "keep_together": True})]
    st = [S("단락 스타일 — 본문 정리(자리마다 하나, 스타일 · 색상 견본 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        q = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together", "shade_fit"):
                st.append({"click": "input" + q(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def b1_make_parts(pno):
    """부품 — 꼬리표 「주제」 · 「제목」(면 · 두꺼운 선 · 흰 글) · 체크 아이콘(원본에서 내보낸 그림 + 같은 크기 빈 면)을 빈 자리에 그려 묶는다"""
    sp, dr, ps, rows, rect, tg, q_icon, qt, p2, rows2, rects, foot, cl = b1_parts(pno)
    st = []
    X0, Y0 = 20.0, 262.0
    for t in tg:
        r = t["r"]
        dx, dy = X0 - r["x"], Y0 - r["y"]
        st += [S(f"꼬리표 「{t['tt']['t'].strip()}」 부품 — 면 · 두꺼운 선 · 흰 글", 1200)]
        st += box(round(X0, 2), round(Y0, 2), round(r["w"], 2), round(r["h"], 2), r["fill"])
        n = 1
        for ln in t["thick"]:
            t_ = ln["sw"] * MM
            st += box(round(ln["x"] + dx, 2), round(ln["y"] - t_ / 2 + dy, 3), round(ln["w"], 2), round(t_, 3), r["fill"])
            n += 1
        tt = t["tt"]                                                     # 흰 글 — 부품 속이라 잴 목록에 안 넣는다(지면 꼬리표는 원고 요소로 따로 잰다)
        st += text(round(tt["x"] + dx, 2), round(top_of(tt["base"], tt["size"], ELB, 700, tt["size"]) + dy, 2), 8, round(tt["size"] * MM + 0.4, 1),
                   tt["t"].strip(), tt["size"], "#ffffff", font=ELB, weight=700, leading=tt["size"])
        n += 1
        B1P[t["name"]] = group_part(st, n, X0, Y0, max(r["w"], 8) + 1, r["h"] + 1)
    st += [S("체크 아이콘 부품 — 원본에서 내보낸 그림(check.svg) + 같은 크기 빈 면(그룹은 둘 이상)", 1200)]
    st += image(X0, Y0, 4.15, 4.15, os.path.join(HERE, "check.svg"))
    st += box(X0, Y0, 4.15, 4.15, "#ffffff", alpha=0)                  # 안 보이는 짝 — 그룹은 둘 이상이라
    B1P["발문"] = group_part(st, 2, X0, Y0, 4.15, 4.15)
    return st


def sum_body(pno):
    st = []
    if "x" not in B1:
        b1_style(pno)
        st += b1_make_parts(pno)
    with top_spot():
        st += _sum_body(pno)
    return st


def _sum_body(pno):
    st = []
    if not B1.get("made"):
        st += b1_styles_steps()
        B1["made"] = True
    G = B1
    sp, dr, ps, rows, rect, tg, q_icon, qt, p2, rows2, rects, foot, cl = b1_parts(pno)
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(rect)[k] for k in ("x", "y", "w", "h")}, "color": rect["fill"], "see": rect["fill"], "pad": 0.6, "ctol": 8, "원고": True})
    for d in rects:
        E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(d)[k] for k in ("x", "y", "w", "h")}, "color": d["fill"], "see": d["fill"], "pad": 0.6, "ctol": 8, "원고": True})
    for t in tg:                                                         # 꼬리표 — 주제 · 제목 문장을 따라 놓인다(원고 요소)
        E({"id": f"tg{len(ELEMS[len(PAGES)])}", "x": round(t["r"]["x"], 2), "y": round(t["r"]["y"], 2), "w": round(t["r"]["w"], 2), "h": round(t["r"]["h"], 2),
           "color": t["r"]["fill"], "see": t["r"]["fill"], "pad": 0.3, "ctol": 30, "원고": True})
    o_ = q_icon["sw"] * MM / 2
    E({"id": f"ic{len(ELEMS[len(PAGES)])}", "x": round(q_icon["x"] - o_, 2), "y": round(q_icon["y"] - o_, 2), "w": round(q_icon["w"] + 2 * o_, 2),
       "h": round(q_icon["h"] + 2 * o_, 2), "color": q_icon["stroke"], "see": q_icon["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
    fx = rects[0]["x"]                                                    # 이 쪽의 프레임 왼쪽 = 이 쪽 문제 지문 바탕(지문 바탕은 쪽마다 폭이 다르다 — 45쪽은 7mm 안쪽)
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(G["w"], 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    qtop = round(top_of(qt["base"], qt["size"], ELB, 400, G["발문"]["lead"]), 2)          # 문제 프레임 위 끝 — 원본 20쪽 모두 발문 기준선 157.2mm(제자리)
    anc = lambda nm, x_, dy_: [S(f"「{nm}」 첫 문단 왼쪽 바깥에 고정 개체(사용자 정의 위치)", 1000),
                               {"pick": {"at": f'#side select[data-a="slotfmt.{nm}.anc.part"]', "value": B1P[nm]}, "wait": 900},
                               {"pick": {"at": f'#side select[data-a="slotfmt.{nm}.anc.pos"]', "value": "side"}, "wait": 800},
                               F(f'#side input[data-a="slotfmt.{nm}.anc.x"]', x_, 600), F(f'#side input[data-a="slotfmt.{nm}.anc.dy"]', dy_, 600),
                               {"click": f'#side input[data-a="slotfmt.{nm}.anc.first"]', "wait": 600}]
    for bind, y0, y1, temp, what in ((B1_TOP, G["top"], qtop - 6.0, "임시 지문 — 원고가 오면 지문 · 주제 · 글제목이 이 프레임에 차례로 흐른다.", "위 — 지문 · 주제 · 글제목(원고만큼)"),
                                     (B1_BIND, qtop, bot, "임시 발문 — 원고가 오면 발문 · 문제지문 · 주석 · 선지가 이 프레임에 차례로 흐른다.", "아래 — 문제(제자리 · 발문 · 문제지문 · 주석 · 선지)")):
        st += [S(f"텍스트 프레임 {what}", 1200)]
        st += text(round(fx, 2), round(y0, 2), round(G["w"], 2), round(y1 - y0, 2), temp, BODY, "#231f20",
                   label="글상자 — 한 줄기(" + bind + ")", font=NOTO, leading=G["lead"])
        st += slot(bind, label="자리 — " + bind + " (원고에 나온 차례대로 한 줄기)")
        for nm in bind.split("+"):
            st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "정리·" + nm}, "wait": 450})
        if bind == B1_TOP:
            st += anc("주제", G["주제"]["tag_x"], G["주제"]["tag_dy"]) + anc("글제목", G["글제목"]["tag_x"], G["글제목"]["tag_dy"])
        else:
            st += anc("발문", G["발문"]["ic_x"], G["발문"]["ic_dy"])
        st += justify()
        st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    return st


def sum_record(lp, rp):
    """본문 정리 펼침면 하나의 원고 — 쪽마다 지문 번호 + 한 줄기(지문 · 주제 문장들 · 글제목 문장들 · 발문 · 문제지문 · 주석 · 선지)"""
    rec = {"제목": None, "지문번호": [], B1_TOP: [], B1_BIND: []}
    for pno in (lp, rp):
        sp, dr, ps, rows, rect, tg, q_icon, qt, p2, rows2, rects, foot, cl = b1_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        it = [["지문", ps["text"]]]
        for t in tg:
            it.append([t["name"], "\n".join(o["t"].strip() for o in t["ln"])])
        rec[B1_TOP].append([it])
        it = [["발문", qt["t"].strip()], ["문제지문", p2["text"].split(" *")[0].strip()]]
        if foot:
            it.append(["주석", foot[0]["t"].strip()])
        it.append(["선지", "\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(cl))])
        rec[B1_BIND].append([it])
    return rec


if want(6):
    st += body_pages(44, "B1", "본문 정리", "B본문정리", "⑥ B본문정리", body=sum_body)
    CONTENT["B본문정리"] = [sum_record(l, l + 1) for l in range(44, 64, 2)]

# ── 구성 7 「B내용종합」 (원본 64~83쪽 = 펼침면 10벌 · 원고마다) — 견본 = 64·65쪽 ──
# 쪽: 지문 번호 · 본문 텍스트 프레임 하나(지문 바탕 = 단락 음영 · 문제마다 번호 | 발문 · 선지).


# 흐름 방식(2026-10-14 사용자 확정 — 인디자인처럼): 지문 · 문제를 텍스트 프레임 하나에 차례로 흘린다(자리 B2_BIND).
# 지문 바탕 = 단락 음영, 문제 = 문제번호(발문 첫 줄 앞에 붙임) · 발문(글머리 「|」) · 선지. 원고에 없는 문제는 문단이 안 생기고 아래가 올라온다
# — 접기 묶음 · 아래 모두 밀기를 쓰지 않는다.
B2_BIND = "지문+문제번호+발문+선지"
B2 = {}


def b2_parts(pno):
    """원본 쪽 — 지문 줄 · 바탕 면 · 문제마다 {번호 조각, 막대, 발문 조각들, 선지 줄들}"""
    sp, dr = spans_of(pno), drawings(pno)
    ps = passages(pno)[0]
    rows = [o for o in sp if o["size"] == BODY and ps["base0"] - 0.5 <= o["base"] <= ps["base1"] + 0.5 and o["font"].endswith("Regular")]
    rect = passage_bg(dr, ps)
    qh = [o for o in sp if o["font"] == "EliceDXNeolliOTF-Bd" and o["size"] == 10.0]
    qs = []
    for k, q in enumerate(qh):
        nxt = qh[k + 1]["base"] if k + 1 < len(qh) else 280
        bar = [c for c in q["ink"] if c[0] == "|"][0]
        qts = [o for o in sp if o["font"] in ELICE and q["base"] - 1.5 < o["base"] < nxt - 2 and o["x"] > bar[2]]
        ln = [o for o in sp if o["font"].startswith("NotoSans") and qts[-1]["base"] + 2 < o["base"] < nxt - 2]
        qs.append({"q": q, "bar": bar, "qts": qts, "ln": ln})
    return sp, ps, rows, rect, qs


def b2_style(pno):
    """견본 쪽에서 단락 스타일 값 — 줄 상자(top_of) 기준으로 문단 사이 · 음영 여백을 잰다"""
    sp, ps, rows, rect, qs = b2_parts(pno)
    lead_mm = (ps["base1"] - ps["base0"]) / (ps["lines"] - 1)
    lead = lead_mm / MM
    trk = gaps_track([c for c in rows[-1]["ink"]], BODY)
    top_t = top_of(rows[0]["base"], BODY, NOTO, 400, lead)
    q0 = qs[0]
    qt = q0["qts"][0]
    qfam, qwt = ELICE[qt["font"]]
    qsz = qt["size"]
    qlead = ((q0["qts"][1]["base"] - qt["base"]) / MM) if len(q0["qts"]) > 1 else 15
    ln0 = q0["ln"]
    csz = ln0[0]["size"]
    cl = min(b["base"] - a["base"] for a, b in zip(ln0, ln0[1:])) / MM
    ctrk = gaps_track([c for pa in choice_paras(ln0) for c in pa[-1]["ink"]], csz)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))     # 줄 상자에서 기준선 아래
    # 텍스트 프레임 = 문제 번호 왼쪽 ~ 지문 바탕 · 선지 줄 오른쪽 끝. 지문은 그 안에서 왼쪽 · 오른쪽 들여쓰기 + 음영(너비 「텍스트」)
    x0 = min(q["q"]["x"] for q in qs)
    x1 = max([rect["x"] + rect["w"]] + [o["x1"] for q in qs for o in q["ln"]])
    pass_bot = rect["y"] + rect["h"]
    sb_q1 = top_of(q0["q"]["base"], qsz, qfam, qwt, qlead) - pass_bot                    # 지문 상자 아래 → 첫 발문 줄 상자
    q_last = q0["qts"][-1]
    sb_c = top_of(ln0[0]["base"], csz, NOTO, 400, cl) - (q_last["base"] + below(q_last["base"], qsz, qfam, qwt, qlead))
    if len(qs) > 1:
        lc = qs[0]["ln"][-1]
        sb_q = top_of(qs[1]["q"]["base"], qsz, qfam, qwt, qlead) - (lc["base"] + below(lc["base"], csz, NOTO, 400, cl))
    else:
        sb_q = sb_q1
    B2.update(x=x0, ox=rect["x"], top=rect["y"], w=round(x1 - x0, 2), fill=rect["fill"],
              p_ind=round(rect["x"] - x0, 2), p_ind_r=round(x1 - rect["x"] - rect["w"], 2),
              pad=round(rows[0]["x"] - rect["x"], 2), pad_top=round(top_t - rect["y"], 2),
              pad_bottom=round(pass_bot - (top_t + ps["lines"] * lead_mm), 2),
              lead=round(lead, 2), trk=trk, qfam=qfam, qwt=qwt, qsz=qsz, qlead=round(qlead, 2), q_ind=round(q0["q"]["x"] - x0, 2),
              num_color=q0["q"]["color"], inline_w=round(q0["bar"][1] - q0["q"]["x"], 2),
              num_trk=gaps_track(q0["q"]["ink"][:2], 10, EL, 700) or 1,                           # 자간 0 이면 이 글꼴이 「02」를 동그라미 숫자로 묶는다(합자)
              csz=csz, cl=round(cl, 2), ctrk=ctrk, c_ind=round(ln0[0]["x"] - x0, 2),
              sb_q=round(sb_q, 2), after_p=round(sb_q1 - sb_q, 2), sb_c=round(sb_c, 2))


def b2_styles_steps():
    G = B2
    sty = [("종합·지문", {"font": NOTO, "size": BODY, "leading": G["lead"], "tracking": G["trk"], "color": "#231f20", "align": "justify",
                      "indent": G["p_ind"], "indent_right": G["p_ind_r"], "shade_fit": True,
                      "shade": G["fill"], "pad": G["pad"], "pad_top": G["pad_top"], "pad_bottom": G["pad_bottom"], "space_after": G["after_p"]}),
           ("종합·문제번호", {"font": EL, "weight": 700, "size": 10, "color": G["num_color"], "tracking": G["num_trk"]}),
           ("종합·발문", {"font": G["qfam"], "weight": G["qwt"], "size": G["qsz"], "leading": G["qlead"], "color": "#231f20",
                      "indent": G["q_ind"], "space_before": G["sb_q"], "keep_next": True}),
           ("종합·선지", {"font": NOTO, "size": G["csz"], "leading": G["cl"], "tracking": G["ctrk"], "color": "#231f20", "align": "justify",
                      "indent": G["c_ind"], "space_before": G["sb_c"], "space_same": 0.01, "keep_together": True})]
    st = [S("단락 스타일 — 내용 종합(자리마다 하나, 스타일 · 색상 견본 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        q = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together", "shade_fit"):
                st.append({"click": "input" + q(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def mcq_body(pno):
    with top_spot():
        return _mcq_body(pno)


def _mcq_body(pno):
    st = []
    if "x" not in B2:
        b2_style(pno)
        st += b2_styles_steps()
    G = B2
    sp, ps, rows, rect, qs = b2_parts(pno)
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(rect)[k] for k in ("x", "y", "w", "h")}, "color": rect["fill"], "see": rect["fill"], "pad": 0.6, "ctol": 8, "원고": True})
    fx = G["x"] + rect["x"] - G["ox"]                                     # 이 쪽의 프레임 왼쪽(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(G["w"], 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("본문 — 텍스트 프레임 하나(지문 · 문제가 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), round(G["top"], 2), round(G["w"], 2), round(bot - G["top"], 2),
               "임시 지문 — 원고가 오면 지문 · 문제번호 · 발문 · 선지가 이 프레임 하나에 차례로 흐른다.", BODY, "#231f20",
               label="본문 글상자 — 한 줄기(" + B2_BIND + ")", font=NOTO, leading=G["lead"])
    st += slot(B2_BIND, label="자리 — " + B2_BIND + " (원고에 나온 차례대로 한 줄기)")
    for nm in B2_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "종합·" + nm}, "wait": 450})
    st += [S("문제번호는 발문 첫 줄 앞에 붙인다 — 번호 칸 폭 · 발문 글머리 「|」", 900),
           {"click": '#side input[data-a="slotfmt.문제번호.inline"]', "wait": 600},
           F('#side input[data-a="slotfmt.문제번호.inline_w"]', G["inline_w"], 600),
           F('#side input[data-a="slotfmt.발문.bullet_text"]', "| ", 600)]
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]   # 큰 본문 프레임 고른 것을 풀고 다음 개체를 그린다
    return st


def mcq_record(lp, rp, key_title=13.0):
    """펼침면 하나의 원고 — 쪽마다 지문 번호 + 한 줄기(지문 · 문제마다 번호 · 발문 · 선지). 원고에 없는 문제는 안 보낸다"""
    rec = {"제목": None, "지문번호": [], B2_BIND: []}
    for pno in (lp, rp):
        sp, ps, rows, rect, qs = b2_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == key_title)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        items = [[["지문", ps["text"]]]]
        for q in qs:
            items.append([["문제번호", "".join(c[0] for c in q["q"]["ink"][:2])], ["발문", " ".join(o["t"].strip() for o in q["qts"])],
                          ["선지", "\n".join(" ".join(o["t"].strip() for o in pa) for pa in choice_paras(q["ln"]))]])
        rec[B2_BIND].append(items)                                           # 쪽마다 제 몫
    return rec


if want(7):
    st += body_pages(64, "B2", "내용 종합", "B내용종합", "⑦ B내용종합", body=mcq_body)
    CONTENT["B내용종합"] = [mcq_record(l, l + 1) for l in range(64, 84, 2)]

# ── 구성 8 「C문장배열」 (원본 84~103쪽 = 펼침면 10벌 · 원고마다) — 견본 = 84·85쪽 ──
# 흐름 방식(2026-10-14): 텍스트 프레임 하나에 보기 문장(음영, 이름표 GREP) · 발문 · 주어진 문장(음영) · 지문(테두리 = 단락 음영 + 테두리, 문단 여럿).
# 답 쓰는 줄(화살표 둘 · 선) + 체크 아이콘 = 발문의 고정 개체(사용자 정의 위치). 아래 모두 밀기 없이 원고만큼 흐른다.


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


C1_BIND = "발문+주어진문장+지문"                                          # 아래 문제 프레임 — 제자리(원본 20쪽 모두 발문 기준선 157.1mm). 위 보기 문장은 바탕 칠한 텍스트 프레임 「보기문장」
C1 = {}


def para_metrics(rows, size=BODY):
    """문단 여럿인 줄들 → 행간 · 문단 사이 · 첫 줄 들여쓰기 · 이어지는 줄 x · 자간 · 오른쪽 끝 · 첫 기준선 · 줄 수 · 문단 수"""
    rows = sorted(rows, key=lambda o: o["base"])
    lines = []
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
    trk = gaps_track([c for pa in paras for o in pa[-1] for c in o["ink"]], size)
    return dict(lead_mm=lead_mm, gap=gap, x_t=x_t, ind1=ind1, trk=trk, right=max(o["x1"] for o in rows), base0=bases[0], base1=bases[-1], lines=len(lines),
                text="\n".join(" ".join("".join(o["t"] for o in sorted(ln, key=lambda o: o["x"])).strip() for ln in pa) for pa in paras))


def c1_style(pno):
    sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))
    x0 = min(tb["x"], giv["x"], frame["x"])
    mt, mg, mf = para_metrics(top_rows), para_metrics(giv_rows), para_metrics(fr_rows)
    box_pads = lambda r, m: (round(m["x_t"] - r["x"], 2), round(top_of(m["base0"], BODY, NOTO, 400, m["lead_mm"] / MM) - r["y"], 2),
                             round(r["y"] + r["h"] - (top_of(m["base0"], BODY, NOTO, 400, m["lead_mm"] / MM) + m["lines"] * m["lead_mm"]
                                                      + (len(m["text"].split("\n")) - 1) * m["gap"]), 2))
    labels = [o for o in top_rows if o["font"] == "NotoSansCJKkr-Bold"]
    qsz, qlead = qt["size"], 15.0
    q_top = top_of(qt["base"], qsz, ELB, 400, qlead)
    sw_mm = frame["sw"] * MM
    x1 = max(tb["x"] + tb["w"], giv["x"] + giv["w"], frame["x"] + frame["w"])
    off = lambda r: (round(x0 - r["x"], 2), round(r["x"] + r["w"] - x1, 2))   # 음영 오프셋 왼쪽 · 오른쪽(− = 프레임보다 안쪽) — 바탕마다 폭이 다르다
    C1.update(x=x0, ox=tb["x"], top=tb["y"], w=x1 - x0, offs={"t": off(tb), "g": off(giv), "f": off(frame)},
              t=dict(m=mt, pad=box_pads(tb, mt), fill=tb["fill"], ind=round(tb["x"] - x0, 2)),
              g=dict(m=mg, pad=box_pads(giv, mg), fill=giv["fill"], sb=round(giv["y"] - (qt["base"] + below(qt["base"], qsz, ELB, 400, qlead)), 2)),
              f=dict(m=mf, pad=box_pads(frame, mf), stroke=frame["stroke"], sw=frame["sw"], sb=round(frame["y"] - sw_mm / 2 - (giv["y"] + giv["h"]), 2)),
              q=dict(size=qsz, lead=qlead, ind=round(qt["x"] - x0, 2), sb=round(q_top - (tb["y"] + tb["h"]), 2)),
              lab=dict(color=labels[0]["color"], size=labels[0]["size"]) if labels else None)


def c1_styles_steps():
    G = C1
    B_ = {"font": NOTO, "size": BODY, "color": "#231f20", "align": "justify"}
    t, g, f, q = G["t"], G["g"], G["f"], G["q"]
    so = lambda k: {"shade_ol": G["offs"][k][0], "shade_or": G["offs"][k][1]}
    sty = [("배열·보기문장", dict(B_, **so("t"), leading=round(t["m"]["lead_mm"] / MM, 2), tracking=t["m"]["trk"], shade=t["fill"], pad=t["pad"][0], pad_top=t["pad"][1],
                              pad_bottom=t["pad"][2], indent_first=t["m"]["ind1"], space_same=round(t["m"]["gap"], 2) or 0.01)),
           ("배열·발문", {"font": ELB, "weight": 400, "size": q["size"], "leading": q["lead"], "color": "#231f20", "indent": q["ind"], "space_before": q["sb"],
                       "keep_next": True}),
           ("배열·주어진문장", dict(B_, **so("g"), leading=round(g["m"]["lead_mm"] / MM, 2), tracking=g["m"]["trk"], shade=g["fill"], pad=g["pad"][0], pad_top=g["pad"][1],
                               pad_bottom=g["pad"][2], indent_first=g["m"]["ind1"], space_before=g["sb"], space_same=round(g["m"]["gap"], 2) or 0.01)),
           ("배열·지문", dict(B_, **so("f"), leading=round(f["m"]["lead_mm"] / MM, 2), tracking=f["m"]["trk"], shade="#ffffff", border=f["sw"], border_color=f["stroke"],
                            pad=f["pad"][0], pad_top=f["pad"][1], pad_bottom=f["pad"][2], indent_first=f["m"]["ind1"], space_before=f["sb"],
                            space_same=round(f["m"]["gap"], 2) or 0.01))]
    st = [S("단락 스타일 — 문장 배열(자리마다 하나, 스타일 · 색상 견본 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        qq = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + qq(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together"):
                st.append({"click": "input" + qq(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + qq(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def c1_make_part(pno):
    """부품 둘 — 답 쓰는 줄(화살표 둘 · 선): 보기 문장 끝을 따라 내려간다(보기문장의 고정 개체 · 다음 줄 · 끝 문단만) /
    체크 아이콘: 발문 왼쪽(발문의 고정 개체). 빈 자리에 그려 묶는다"""
    sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
    arrows = [d for d in dr if d["n"] == 3 and d["fill"] and d["y"] > tb["y"] + tb["h"] and d["y"] < qt["base"] - 5]
    lines = [d for d in dr if d["n"] == 1 and d["fill"] and d["h"] < 1 and d["w"] > 50 and tb["y"] + tb["h"] < d["y"] < qt["base"] - 5]
    q_icon = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    ic = {"x": q_icon["x"] - 0.3, "y": q_icon["y"] - 0.3, "w": 4.15, "h": 4.15}
    comps = arrows + lines
    bx0, by0 = min(c["x"] for c in comps), min(c["y"] for c in comps)
    bx1, by1 = max(c["x"] + c["w"] for c in comps), max(c["y"] + c["h"] for c in comps)
    X0, Y0 = 20.0, 200.0
    dx, dy = X0 - bx0, Y0 - by0
    st = [S("답 쓰는 줄 부품 — 빈 자리에 그려 묶는다(보기 문장 끝의 고정 개체)", 1300)]
    for d in arrows:
        st += shape(round(d["x"] + dx, 2), round(d["y"] + dy, 2), round(d["w"], 2), round(d["h"], 2), d["fill"], d=poly_d(pno, {"x": d["x"], "y": d["y"]}))
    for d in lines:
        st += box(round(d["x"] + dx, 2), round(d["y"] + dy, 3), round(d["w"], 2), round(d["h"], 3), d["fill"])
    pid = group_part(st, len(comps), X0, Y0, bx1 - bx0, by1 - by0)
    st += [S("체크 아이콘 부품 — 원본에서 내보낸 그림 + 같은 크기 빈 면(그룹은 둘 이상)", 1200)]
    st += image(X0, 262.0, 4.15, 4.15, os.path.join(HERE, "check.svg"))
    st += box(X0, 262.0, 4.15, 4.15, "#ffffff", alpha=0)
    icp = group_part(st, 2, X0, 262.0, 4.15, 4.15)
    q_top = top_of(qt["base"], qt["size"], ELB, 400, 15.0)
    C1.update(part=pid, line_x=round(bx0 - C1["x"], 2), line_gap=round(by0 - (tb["y"] + tb["h"]), 2),
              icon=icp, anc_x=round(ic["x"] - C1["x"], 2), anc_dy=round(ic["y"] - q_top, 2))
    return st, arrows, lines, q_icon


def order_body(pno):
    st = []
    if "x" not in C1:
        c1_style(pno)
        s2, _, _, _ = c1_make_part(pno)
        st += s2
    with top_spot():
        st += _order_body(pno)
    return st


def _order_body(pno):
    st = []
    if not C1.get("made"):
        st += c1_styles_steps()
        C1["made"] = True
    G = C1
    sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    for r in (tb, giv):
        E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(r)[k] for k in ("x", "y", "w", "h")}, "color": r["fill"], "see": r["fill"], "pad": 0.6, "ctol": 8, "원고": True})
    o_ = frame["sw"] * MM / 2
    E({"id": f"fr{len(ELEMS[len(PAGES)])}", "x": round(frame["x"] - o_, 2), "y": round(frame["y"] - o_, 2), "w": round(frame["w"] + 2 * o_, 2), "h": round(frame["h"] + 2 * o_, 2),
       "color": frame["stroke"], "see": frame["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
    for d in [d for d in dr if (d["n"] == 3 and d["fill"] and d["y"] > tb["y"] + tb["h"] and d["y"] < qt["base"] - 5)
              or (d["n"] == 1 and d["fill"] and d["h"] < 1 and d["w"] > 50 and tb["y"] + tb["h"] < d["y"] < qt["base"] - 5)]:
        E({"id": f"ar{len(ELEMS[len(PAGES)])}", "x": round(d["x"], 2), "y": round(d["y"], 2), "w": round(d["w"], 2), "h": round(d["h"], 2), "color": d["fill"],
           "see": d["fill"], "pad": 0.2, "ctol": 20, "원고": True})
    q_icon = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    oi = q_icon["sw"] * MM / 2
    E({"id": f"ic{len(ELEMS[len(PAGES)])}", "x": round(q_icon["x"] - oi, 2), "y": round(q_icon["y"] - oi, 2), "w": round(q_icon["w"] + 2 * oi, 2),
       "h": round(q_icon["h"] + 2 * oi, 2), "color": q_icon["stroke"], "see": q_icon["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
    fx = G["x"] + tb["x"] - G["ox"]                                       # 이 쪽의 프레임 왼쪽(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(G["w"], 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("보기 문장 — 위 텍스트 프레임(바탕 칠 · 인세트 · 원고만큼 자란다)", 1200)]
    qtop = round(top_of(qt["base"], qt["size"], ELB, 400, G["q"]["lead"]), 2)
    st += text(round(fx, 2), round(G["top"], 2), round(G["w"], 2), round(qtop - 6.0 - G["top"], 2),
               "(A) 임시 문장 — 원고가 오면 보기 문장이 문단마다 들어온다.", BODY, "#231f20",
               label="보기 문장 글상자 — 원고 자리 「보기문장」(문단마다 · 바탕은 단락 음영)", font=NOTO, leading=round(G["t"]["m"]["lead_mm"] / MM, 2))
    st += slot("보기문장", label="자리 — 보기문장")
    st += [{"pick": {"at": '#side select[data-a="slotfmt.보기문장.style"]', "value": "배열·보기문장"}, "wait": 450},
           S("보기 문장 끝에 답 쓰는 줄 — 데이터 필드 「보기문장」의 고정 개체(다음 줄 · 끝 문단만)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.보기문장.anc.part"]', "value": G["part"]}, "wait": 900},
           {"pick": {"at": '#side select[data-a="slotfmt.보기문장.anc.pos"]', "value": "line"}, "wait": 800},
           F('#side input[data-a="slotfmt.보기문장.anc.x"]', G["line_x"], 600), F('#side input[data-a="slotfmt.보기문장.anc.gap"]', G["line_gap"], 600),
           {"click": '#side input[data-a="slotfmt.보기문장.anc.last"]', "wait": 600}]
    if G["lab"]:
        st += grep(0, r"^\([A-Z]\)", G["lab"]["color"], size=G["lab"]["size"], label="GREP — 문장 이름표 (A)(B)… 굵은 파랑")
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    st += [S("문제 — 아래 텍스트 프레임(제자리 · 발문 · 주어진 문장 · 지문이 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), qtop, round(G["w"], 2), round(bot - qtop, 2),
               "임시 발문 — 원고가 오면 발문 · 주어진 문장 · 지문이 이 프레임에 차례로 흐른다.", BODY, "#231f20",
               label="문제 글상자 — 한 줄기(" + C1_BIND + ")", font=NOTO, leading=round(G["t"]["m"]["lead_mm"] / MM, 2))
    st += slot(C1_BIND, label="자리 — " + C1_BIND + " (원고에 나온 차례대로 한 줄기)")
    for nm in C1_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "배열·" + nm}, "wait": 450})
    st += [S("발문의 고정 개체 — 체크 아이콘(사용자 정의 위치: 발문 왼쪽)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.발문.anc.part"]', "value": G["icon"]}, "wait": 900},
           {"pick": {"at": '#side select[data-a="slotfmt.발문.anc.pos"]', "value": "side"}, "wait": 800},
           F('#side input[data-a="slotfmt.발문.anc.x"]', G["anc_x"], 600), F('#side input[data-a="slotfmt.발문.anc.dy"]', G["anc_dy"], 600)]
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    return st


def order_record(lp, rp):
    """문장 배열 펼침면 하나의 원고 — 쪽마다 지문 번호 + 한 줄기(보기 문장 · 발문 · 주어진 문장 · 지문)"""
    rec = {"제목": None, "지문번호": [], "보기문장": [], C1_BIND: []}
    for pno in (lp, rp):
        sp, dr, qt, tb, top_rows, giv, giv_rows, frame, fr_rows = order_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec["보기문장"].append(para_metrics(top_rows)["text"])
        rec[C1_BIND].append([[["발문", qt["t"].strip()],
                              ["주어진문장", para_metrics(giv_rows)["text"]], ["지문", para_metrics(fr_rows)["text"]]]])
    return rec


if want(8):
    st += body_pages(84, "C1", "문장 배열", "C문장배열", "⑧ C문장배열", body=order_body)
    CONTENT["C문장배열"] = [order_record(l, l + 1) for l in range(84, 104, 2)]

# ── 구성 9 「C빈칸어휘」 (원본 104~123쪽 = 펼침면 10벌 · 원고마다) — 견본 = 104·105쪽 ──
# 쪽: 지문 번호 · 흐르는 글상자 하나(문항번호 + 빈칸문장 + 해석 — 원고만큼 이어 흐른다, 쪽마다 제 몫의 문항 목록).
# 글 모양 = 브랜드 단락 스타일(빈칸문장 · 해석 · 문항번호), 빈칸 = GREP(원고 꼴 「{s}__」 — 첫 글자 분홍 굵게 + 밑줄 칸).
# 원고 스타일은 견본 왼쪽 면에서 재서 오른쪽 면도 같게(원본 오른쪽 면의 다른 밑줄 길이 등은 따르지 않는다 — 원고 기준).
C2 = {"bind": "문항번호+빈칸문장+해석", "sfx": "", "key": "C빈칸어휘"}                                                                  # 견본 왼쪽 면에서 잰 스타일 — 오른쪽 면도 이것


def c2_items(pno, G=None):
    G = G or C2
    """원본 쪽의 문항들 — [{문항번호, 빈칸문장(빈칸 = {첫 글자}__), 해석}] 과 줄 자리"""
    sp = spans_of(pno)
    nums = [o for o in sp if LOTTE in o["font"]]
    out = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        en = [o for o in sp if o["font"].startswith("NotoSans") and o["color"] != "#58595b" and n["base"] - 1 <= o["base"] < nxt - 1]
        ko = [o for o in sp if o["color"] == "#58595b" and n["base"] - 1 <= o["base"] < nxt - 1]
        lines = {}
        for o in en:
            lines.setdefault(round(o["base"], 1), []).append(o)
        txt = ""
        ul = [d for d in drawings(pno) if d["stroke"] and d["h"] < 0.1 and 5 < d["w"] < 60]
        for b in sorted(lines):
            row = sorted(lines[b], key=lambda o: o["x"])
            if not any(o["color"] == "#c64a86" for o in row):            # 빈칸 어법 — 글자 없는 밑줄: 밑줄 자리에 「__」
                for d in [d for d in ul if 0 < d["y"] - b < 1.5]:
                    row.append({"x": d["x"], "t": " __ ", "color": "#231f20"})
                row.sort(key=lambda o: o["x"])
            for o in row:
                t = o["t"]
                if o["color"] == "#c64a86":                              # 빈칸 — 원본은 첫 글자(분홍 굵게) + 밑줄
                    t = (" " if txt.endswith("__") else "") + "{" + t.strip() + "}__"     # 빈칸 둘이 잇닿으면 사이 띄어쓰기(원본은 밑줄 칸 사이)
                txt += t
            txt += " "
        txt = re.sub(r"\s+", " ", txt).strip()
        out.append({"n": n, "en": en, "ko": ko, "rec": {"문항번호": n["t"].strip(), "빈칸문장": txt, "해석": " ".join(o["t"].strip() for o in sorted(ko, key=lambda o: o["base"]))}})
    return out


import re                                                                # noqa: E402


def c2_style(pno, G=None):
    G = G or C2
    """견본 왼쪽 면에서 단락 스타일 값 — 행간·문단 사이·자간·들여쓰기·빈칸 밑줄"""
    items = c2_items(pno, G)
    sp, dr = spans_of(pno), drawings(pno)
    en_b = sorted({round(o["base"], 2) for it in items for o in it["en"]})
    ko_b = sorted({round(o["base"], 2) for it in items for o in it["ko"]})
    two = next(it for it in items if len({round(o["base"], 1) for o in it["en"]}) > 1)     # 두 줄 넘는 첫 문항 — 그 두 줄 사이가 행간
    eb = sorted({round(o["base"], 2) for o in two["en"]})
    en_lead = eb[1] - eb[0]
    ko_lead = min([b - a for a, b in zip(ko_b, ko_b[1:]) if 1 < b - a < 6] or [13 * MM])
    it0 = items[0]
    e_last = max(o["base"] for o in it0["en"])
    k_first, k_last = min(o["base"] for o in it0["ko"]), max(o["base"] for o in it0["ko"])
    nxt_en = min(o["base"] for o in items[1]["en"])
    en_pt, ko_pt = round(en_lead / MM, 2), round(ko_lead / MM, 2)
    below = lambda base, pt, fam, wt: pt * MM - (base - top_of(base, 8, fam, wt, pt))          # 줄 상자에서 기준선 아래
    above = lambda base, pt, fam, wt: base - top_of(base, 8, fam, wt, pt)                     # 줄 상자 위 → 기준선
    ko_before = round((k_first - e_last) - below(e_last, en_pt, NOTO, 400) - above(k_first, ko_pt, NOTO, 500), 2)
    ko_after = round((nxt_en - k_last) - below(k_last, ko_pt, NOTO, 500) - above(nxt_en, en_pt, NOTO, 400), 2)
    cont = [o["x"] for it in items for o in it["en"] if abs(o["base"] - it["n"]["base"]) > 1 and o["x"] < it["n"]["x"] + 8]
    first = min(o["x"] for o in it0["en"] if abs(o["base"] - it0["n"]["base"]) < 1)
    ul = [d for d in dr if d["stroke"] and d["h"] < 0.1 and 5 < d["w"] < 50]
    pinks = [o for it in items for o in it["en"] if o["color"] == "#c64a86"]
    ref = pinks[0] if pinks else it0["en"][0]
    u0 = min(ul, key=lambda d: abs(d["y"] - ref["base"]) + (abs(d["x"] - ref["x1"]) if pinks else 0))
    pink = {"color": pinks[0]["color"] if pinks else None, "base": min((o["base"] for o in it0["en"] if abs(o["base"] - u0["y"]) < 1.5), default=u0["y"] - 0.4)}
    plain = [o for it in items for o in it["en"] if o["color"] != "#c64a86" and o["font"].endswith("Regular")]
    en_size = next(o["size"] for it in items for o in it["en"])           # 영어 글 크기 — 구성 9 는 8pt, 구성 12 견본은 9pt
    G.update(en_size=en_size, x0=it0["n"]["x"], inline_w=round(first - it0["n"]["x"], 2), indent=round((min(cont) if cont else first) - it0["n"]["x"], 2),
              en_pt=en_pt, ko_pt=ko_pt, ko_before=ko_before, ko_after=ko_after, en_trk=gaps_track([c for o in plain for c in o["ink"]], en_size),
              ko_trk=gaps_track([c for it in items for o in it["ko"] for c in o["ink"]], 8, NOTO, 500),
              blank=round(u0["w"], 2), line=round(u0["sw"] * MM, 3), line_off=round(u0["y"] - pink["base"], 2), right=max(o["x1"] for it in items for o in it["en"]),
              num_color=it0["n"]["color"], pink=pink["color"])


def c2_styles_steps(G=None):
    G = G or C2
    """브랜드 창 「＋ 단락 스타일」 → 이름(뜨는 창에 친다) → 칸마다 — 빈칸문장 · 해석 · 문항번호"""
    sty = [("빈칸문장" + G["sfx"], {"font": NOTO, "size": G.get("en_size", 8), "leading": G["en_pt"], "tracking": G["en_trk"], "color": "#231f20", "align": "justify",
                      "indent": G["indent"], "indent_first": -G["indent"]}),
           ("해석" + G["sfx"], {"font": NOTO, "weight": 500, "size": 8, "leading": G["ko_pt"], "tracking": G["ko_trk"], "color": "#58595b",
                    "indent": G["indent"], "space_before": G["ko_before"], "space_after": G["ko_after"]}),
           ("문항번호" + G["sfx"], {"font": LOTTE, "size": 9, "color": G["num_color"]})]
    st = [S("단락 스타일 셋 — 브랜드 창에서(빈칸문장 · 해석 · 문항번호)", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        q = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 1000), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def c2_body(pno, G=None):
    with top_spot():
        return _c2_body(pno, G or C2)


def _c2_body(pno, G):
    if "en_pt" not in G:
        c2_style(pno, G)                                                    # 견본 왼쪽 면에서 스타일
    st = []
    if not G.get("made"):
        st += c2_styles_steps(G)
        _, _, adv = face(NOTO, 400)
        trk = round((G["blank"] / (G.get("en_size", 8) * MM) - 2 * adv("_")) / 2 * 1000)    # 「__」 두 글자 + 자간 = 칸 폭(밑줄은 자간까지 긋는다)
        cs = [("빈칸" + G["sfx"], {"u": 1, "color": "none", "track": trk, "line": G["line"], "line_off": G["line_off"], "line_color": "#231f20"})]
        if G.get("pink"):
            cs.insert(0, ("첫 글자", {"b": 1, "color": G["pink"]}))
        st += cs_steps(cs, "빈칸 문자 스타일")
        G["made"] = True
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    items = c2_items(pno, G)
    x0 = items[0]["n"]["x"]
    top = top_of(items[0]["n"]["base"], 9, LOTTE, 400, G["en_pt"])
    right = max(o["x1"] for it in items for o in it["en"])
    w = round(right - x0 + G["en_trk"] / 1000 * G.get("en_size", 8) * MM, 2)
    for col, sel in ((G["num_color"], lambda it: [it["n"]]), ("#231f20", lambda it: [o for o in it["en"] if o["color"] == "#231f20"]),
                     (G["pink"], lambda it: [o for o in it["en"] if o["color"] == G["pink"]]), ("#58595b", lambda it: it["ko"])):
        os_ = [o for it in items for o in sel(it)]
        if os_ and col:
            E({"id": f"f{len(ELEMS[len(PAGES)])}", "x": round(min(o["x"] for o in os_), 2), "y": round(min(o["base"] for o in os_) - 3, 2),
               "w": round(max(o["x1"] for o in os_) - min(o["x"] for o in os_), 2), "h": round(max(o["base"] for o in os_) - min(o["base"] for o in os_) + 4, 2),
               "color": col, "see": col, "ctol": 30, "pad": 1.0, "search": 1.0, "원고": True})
    st += text(round(x0, 2), round(top, 2), w, round(281 - top, 1), "01. 임시 빈칸 {a}__ 문장이 이 자리에 흐른다.\n임시 해석이 이 줄에 들어온다.", 8, "#231f20",
               label="문항 글상자 — 한 줄기(문항번호 + 빈칸문장 + 해석, 원고만큼 흐른다)", font=NOTO, leading=G["en_pt"])
    st += slot(G["bind"], label=f"자리 — {G["bind"]} (원고에 나온 차례대로 한 줄기)")
    for n in ("문항번호", "빈칸문장", "해석"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{n}.style"]', "value": n + G["sfx"]}, "wait": 500})
    st += [S("문항번호는 빈칸문장 첫 줄 앞에 붙인다 — 번호 칸 폭", 1000), {"click": '#side input[data-a="slotfmt.문항번호.inline"]', "wait": 600},
           F('#side input[data-a="slotfmt.문항번호.inline_w"]', G["inline_w"], 600)]
    st += grep(0, r"__", bold=False, label=f"GREP — 원고의 __ 는 문자 스타일 「빈칸{G['sfx']}」({G['blank']}mm 밑줄 칸 — 글자 색 [없음] · 밑줄 · 자간)")
    st += [{"pick": {"at": '#side select[data-a="grep.0.cs"]', "value": "빈칸" + G["sfx"]}, "wait": 600}]
    return st


def c2_record(lp, rp, G=None):
    G = G or C2
    rec = {"제목": None, "지문번호": [], G["bind"]: []}
    for pno in (lp, rp):
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec[G["bind"]].append([dict(it["rec"], 빈칸문장=marks_runs(it["rec"]["빈칸문장"], "첫 글자")) for it in c2_items(pno, G)])   # 쪽마다 제 몫 — 힌트는 꾸밈 조각
    return rec


if want(9):
    st += body_pages(104, "C2", "빈칸 어휘", "C빈칸어휘", "⑨ C빈칸어휘", body=c2_body)
    CONTENT["C빈칸어휘"] = [c2_record(l, l + 1) for l in range(104, 124, 2)]

if want("2.2"):                                                         # STEP 02 간지·차례 — 구성 2·3 의 두 번째 회차(따로 돌릴 때 「2.2,3.2」)
    st += divider(124, "02")
if want("3.2"):
    st += toc(125, "02")

# ── 구성 10 「A어법선택」 (원본 126~145쪽 = 펼침면 10벌 · 원고마다) — 견본 = 126·127쪽 ──
# 흐름 방식(2026-10-14): 텍스트 프레임 하나에 지문([a / b] 굵은 파랑 GREP) · 발문(체크 아이콘 = 고정 개체) · 문제지문(테두리 = 단락 음영 + 테두리).
# 밑줄 친 곳 = 꾸밈 조각(문자 스타일 「밑줄」) — 표시 감추기 GREP 없이. 원고에 문제가 없으면 발문 · 문제지문 문단이 안 생긴다.


def check_icon(dr):
    """체크 아이콘 — 원본 상자 · STEP 색에 맞는 그림 파일(원본에서 내보낸 것)"""
    ic = [d for d in dr if d["n"] == 20 and d["stroke"] and d["w"] < 5][0]
    return ic, os.path.join(HERE, {"#8aabc9": "check.svg", "#bd7d70": "check_s2.svg"}.get(ic["stroke"], "check.svg"))


def underlined_text(pno, y0, y1, x0=0, x1=205):
    """원본 쪽 그 범위의 글 — 밑줄(검은 가는 선) 아래 글자 묶음은 {…} 로(원고 꼴, GREP 이 밑줄을 긋는다). 줄은 띄어 잇고 문단은 안 나눈다"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    segs = [d for d in drawings(pno) if d["stroke"] == "#231f20" and d["h"] < 0.1 and d["w"] > 1 and y0 < d["y"] < y1 + 2]
    lines = {}
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (1.0, 0.0):
                continue
            for sp in l["spans"]:
                base = (sp["origin"][1] - t.y0) * MM
                if not (y0 < base < y1):
                    continue
                sx = sp["chars"][0]["origin"][0] if sp["chars"] else 0
                key = next((b_ for b_ in lines if abs(b_ - base) < 0.3), round(base, 1))   # 같은 줄 — 기준선이 0.1mm 안팎 다른 조각(굵은 밑줄 낱말)도 한 줄로
                for k, c in enumerate(sp["chars"]):                    # 조각 안 글자 차례 그대로(합자 ff·fi 는 기준점이 겹쳐 x 로 늘어놓으면 섞인다)
                    cx = ((c["bbox"][0] + c["bbox"][2]) / 2 - t.x0) * MM
                    if x0 <= cx <= x1:
                        lines.setdefault(key, []).append(((sx, k), c["c"], cx, base))
    out = ""
    for b in sorted(lines):
        s, inside = "", False
        for _, ch, cx, base in sorted(lines[b]):
            u = ch.strip() and any(sg["x"] - 0.2 <= cx <= sg["x"] + sg["w"] + 0.2 and 0 < sg["y"] - base < 1.6 for sg in segs)
            if u and not inside:
                s += "{"; inside = True
            elif not u and inside and ch.strip():
                s = s.rstrip() + "}" + (" " if s.endswith(" ") else ""); inside = False
            s += ch
        if inside:
            s = s.rstrip() + "}"
        out += (" " if out and not out.endswith("-") else "") + s.strip()
    return re.sub(r"\s+", " ", out).strip()


A1G_BIND = "발문+문제지문"                                             # 아래 문제 프레임(제자리 — 원본 20쪽 모두 발문 기준선 157.2mm). 위 지문은 따로 선 프레임 「지문」
A1G = {}


def a1g_parts(pno):
    sp, dr = spans_of(pno), drawings(pno)
    ic, icon_file = check_icon(dr)
    ps = [g for g in passages(pno) if g["base0"] < ic["y"]][0]
    qt = [o for o in sp if o["font"] == "EliceDigitalBaeumOTF" and abs(o["base"] - ic["y"] - ic["h"]) < 2][0]
    frame = [d for d in dr if d["stroke"] and not d["fill"] and d["w"] > 100 and d["h"] > 5][0]
    rows = [o for o in sp if o["font"].startswith("NotoSans") and frame["y"] < o["base"] < frame["y"] + frame["h"]]
    return sp, dr, ic, icon_file, ps, qt, frame, rows


def a1g_style(pno):
    sp, dr, ic, icon_file, ps, qt, frame, rows = a1g_parts(pno)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))
    x0 = frame["x"]
    lead_mm = LEAD * MM
    qsz, qlead = qt["size"], 15.0
    q_top = top_of(qt["base"], qsz, ELB, 400, qlead)
    m = para_metrics(rows)
    t_top = top_of(m["base0"], BODY, NOTO, 400, m["lead_mm"] / MM)
    A1G.update(x=x0, ox=frame["x"], top=round(q_top, 2), w=frame["w"],
               q=dict(size=qsz, lead=qlead, ind=round(qt["x"] - x0, 2), sb=round(q_top - (ps["base1"] + below(ps["base1"], BODY, NOTO, 400, LEAD)), 2),
                      ic_x=round(ic["x"] - 0.3 - x0, 2), ic_dy=round(ic["y"] - 0.3 - q_top, 2)),
               f=dict(m=m, stroke=frame["stroke"], sw=frame["sw"], pad=round(m["x_t"] - frame["x"], 2), pad_top=round(t_top - frame["y"], 2),
                      pad_bottom=round(frame["y"] + frame["h"] - (t_top + m["lines"] * m["lead_mm"] + (len(m["text"].split("\n")) - 1) * m["gap"]), 2),
                      sb=round(frame["y"] - frame["sw"] * MM / 2 - (qt["base"] + below(qt["base"], qsz, ELB, 400, qlead)), 2)),
               icon_file=icon_file)


def a1g_styles_steps():
    G = A1G
    q, f = G["q"], G["f"]
    B_ = {"font": NOTO, "size": BODY, "color": "#231f20", "align": "justify"}
    sty = [("어법·발문", {"font": ELB, "weight": 400, "size": q["size"], "leading": q["lead"], "color": "#231f20", "indent": q["ind"], "space_before": q["sb"],
                       "keep_next": True}),
           ("어법·문제지문", dict(B_, leading=round(f["m"]["lead_mm"] / MM, 2), tracking=f["m"]["trk"], shade="#ffffff", border=f["sw"], border_color=f["stroke"],
                              pad=f["pad"], pad_top=f["pad_top"], pad_bottom=f["pad_bottom"], indent_first=f["m"]["ind1"], space_before=f["sb"],
                              space_same=round(f["m"]["gap"], 2) or 0.01))]
    st = [S("단락 스타일 — 어법 선택(자리마다 하나, 스타일 · 색상 견본 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        qq = lambda k: f'[data-st="{name}:{k}"]'
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + qq(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together"):
                st.append({"click": "input" + qq(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + qq(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def gram_body(pno):
    st = []
    if "x" not in A1G:
        a1g_style(pno)
        X0, Y0 = 20.0, 262.0
        st += [S("체크 아이콘 부품 — 원본에서 내보낸 그림 + 같은 크기 빈 면(그룹은 둘 이상)", 1200)]
        st += image(X0, Y0, 4.15, 4.15, A1G["icon_file"])
        st += box(X0, Y0, 4.15, 4.15, "#ffffff", alpha=0)
        A1G["part"] = group_part(st, 2, X0, Y0, 4.15, 4.15)
    with top_spot():
        st += _gram_body(pno)
    return st


def _gram_body(pno):
    st = []
    if not A1G.get("made"):
        st += a1g_styles_steps()
        if not ULF.get("done"):
            st += cs_steps(UL_CS, "밑줄 문자 스타일")                     # 원고의 밑줄(꾸밈 조각) — 「밑줄」 · 「밑줄 보통」
            ULF["done"] = True
        A1G["made"] = True
    G = A1G
    sp, dr, ic, icon_file, ps, qt, frame, rows = a1g_parts(pno)
    nb = numbers(pno)[0]
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    st += [S("지문 — 위 텍스트 프레임(원고만큼, 문제 프레임 바로 위까지)", 1200)]
    st += P(ps, round(G["top"] - 6.0, 1), "지문 — 원고 자리 「지문」 (임시 글로 스타일)")
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    o_ = ic["sw"] * MM / 2
    E({"id": f"ic{len(ELEMS[len(PAGES)])}", "x": round(ic["x"] - o_, 2), "y": round(ic["y"] - o_, 2), "w": round(ic["w"] + 2 * o_, 2),
       "h": round(ic["h"] + 2 * o_, 2), "color": ic["stroke"], "see": ic["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
    of = frame["sw"] * MM / 2
    E({"id": f"fr{len(ELEMS[len(PAGES)])}", "x": round(frame["x"] - of, 2), "y": round(frame["y"] - of, 2), "w": round(frame["w"] + 2 * of, 2), "h": round(frame["h"] + 2 * of, 2),
       "color": frame["stroke"], "see": frame["stroke"], "pad": 0.3, "ctol": 30, "원고": True})
    fx = G["x"] + frame["x"] - G["ox"]                                    # 이 쪽의 프레임 왼쪽(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(G["w"], 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("문제 — 아래 텍스트 프레임(제자리 · 발문 · 문제지문이 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), round(G["top"], 2), round(G["w"], 2), round(bot - G["top"], 2), "임시 발문 — 원고가 오면 발문 · 문제 지문이 이 프레임에 흐른다.", BODY, "#231f20",
               label="문제 글상자 — 한 줄기(" + A1G_BIND + ")", font=NOTO, leading=LEAD)
    st += slot(A1G_BIND, label="자리 — " + A1G_BIND + " (원고에 나온 차례대로 한 줄기)")
    for nm in A1G_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "어법·" + nm}, "wait": 450})
    st += [S("발문의 고정 개체 — 체크 아이콘(사용자 정의 위치: 발문 왼쪽)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.발문.anc.part"]', "value": G["part"]}, "wait": 900},
           {"pick": {"at": '#side select[data-a="slotfmt.발문.anc.pos"]', "value": "side"}, "wait": 800},
           F('#side input[data-a="slotfmt.발문.anc.x"]', G["q"]["ic_x"], 600), F('#side input[data-a="slotfmt.발문.anc.dy"]', G["q"]["ic_dy"], 600)]
    ul = [d for d in dr if d["h"] < 0.1 and d["stroke"] == "#231f20" and abs(d["y"] - qt["base"]) < 2 and qt["x"] <= d["x"] <= qt["x1"]]
    if ul:
        u = ul[0]
        st += grep(0, "않는|아닌|틀린|없는", bold=False, underline=True, line=round(u["sw"] * MM, 3), line_off=round(u["y"] - qt["base"], 2),
                   line_color=u["stroke"], label="GREP — 발문의 부정어에 밑줄")
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    return st


def gram_record(lp, rp):
    """어법 선택 펼침면 하나의 원고 — 쪽마다 지문 번호 · 지문 + 문제 한 줄기(발문 · 문제지문 — 밑줄 친 곳은 문자 스타일 조각)"""
    rec = {"제목": None, "지문번호": [], "지문": [], A1G_BIND: []}
    for pno in (lp, rp):
        sp, dr, ic, icon_file, ps, qt, frame, rows = a1g_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"] += [e["text"] for e in numbers(pno)]
        rec["지문"].append(ps["text"])
        rec[A1G_BIND].append([[["발문", qt["t"].strip()],
                               ["문제지문", marks_runs(underlined_text(pno, frame["y"], frame["y"] + frame["h"]))]]])
    return rec


if want(10):
    st += body_pages(126, "A1", "어법 선택", "A어법선택", "⑩ A어법선택", body=gram_body)
    CONTENT["A어법선택"] = [gram_record(l, l + 1) for l in range(126, 146, 2)]

# ── 구성 11 「B어법OX」 (원본 146~165쪽 = 펼침면 10벌 · 원고마다) — 견본 = 146·147쪽 ──
# 흐름 방식(2026-10-14): 지문 번호 · 텍스트 프레임 하나(문장마다 번호 「01.」 · 글 · 끝에 O/X 칸 = 데이터 필드 「문장」의 고정 개체).
# 첫 회차(146쪽)의 회색 보기 예문 상자는 그 회차만의 시범이라 템플릿에 두지 않는다(contents 도 안 보낸다) — 견본 = 148·149쪽.


def ox_rows(st, sp, dr, nums, stext, right, shift, grow, slot_no, slot_txt, fold=None, label="문장", nmax=0):
    """번호 + 문장(끝에 O/X 칸) 줄들 — 번호 상자는 넓게(위 글이 자라면 같이 밀린다), 문장 상자는 한 줄 높이로(원고만큼 자란다)"""
    oxs = [d for d in dr if d["n"] == 20 and d["fill"] == "#ffffff" and d["stroke"] == LINK]
    bars = [d for d in dr if d["fill"] == LINK and d["w"] < 1]
    _, _, adv = face(NOTO, 400)
    last_lines = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        ln = [o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1]
        if ln:
            last_lines.append(ln[-1])
    strk = line_track(last_lines, NOTO, 400) if last_lines else -40
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        ln = [o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1]
        ssz, first, cont, last = ln[0]["size"], ln[0], ln[1:], ln[-1]
        cx = cont[0]["x"] if cont else first["x"]
        bx = min([d for d in oxs if n["base"] - 6 < d["y"] < nxt - 3], key=lambda d: d["y"])
        bbot = bx["y"] + bx["h"]
        same = abs(bbot - last["base"]) < 2.5
        slead_mm = (cont[0]["base"] - first["base"]) if cont else 6.79
        lines = len(ln) + (0 if same else 1)
        sh = shift(n["base"] - 3)
        st += [S(f"{label} {k + 1:02d} — 번호 · 글 · 끝에 O/X 칸", 900)]
        fold = f"{label}{k + 1}" if nmax else fold                       # 줄마다 접기 묶음 — 원고에 그 줄이 없으면 접힌다
        st += T(win_el(n, n["t"].strip(), n["x"], n["x1"]), LOTTE, 400, slot_name=slot_no, temp="00.", shift=sh, w=round(right - n["x"], 1), fold=fold)
        stop = top_of(first["base"], ssz, NOTO, 400, round(slead_mm / MM, 2))
        E({"id": f"s{len(ELEMS[len(PAGES)])}", "x": round(min(cx, first["x"]), 2), "y": round(first["base"] - 0.95 * ssz * MM, 2),
           "w": round(max(o["x1"] for o in ln) - min(cx, first["x"]), 2), "h": round(last["base"] - first["base"] + 1.25 * ssz * MM, 2),
           "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 0.8, "search": 0.8, "text": first["t"].strip()[:30], "size": ssz, "원고": True, "shape_iou": 0.80})
        o = bx["sw"] * MM / 2
        E({"id": f"ox{len(ELEMS[len(PAGES)])}", "x": round(bx["x"] - o, 2), "y": round(bx["y"] - o, 2), "w": round(bx["w"] + 2 * o, 2), "h": round(bx["h"] + 2 * o, 2),
           "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30, "원고": True})
        if same:
            gap = round(bx["x"] - last["x1"] - adv(" ") * ssz * MM - 2 * strk / 1000 * ssz * MM, 3)
            drop = round(bbot - last["base"], 3)
        else:
            gap = round(bx["x"] - cx, 3)
            drop = round(bbot - (last["base"] + slead_mm), 3)
        st += text(round(cx, 2), round(stop - sh, 2), round(right - cx + strk / 1000 * ssz * MM, 2), round(slead_mm, 2), "임시 문장 — 바깥에서 온 문장이 이 자리에 들어온다.",
                   ssz, "#231f20", label=f"{label} — 원고 자리 「{slot_txt}」 · 끝에 O/X 칸", leading=round(slead_mm / MM, 2), align="justify", font=NOTO, track=strk)
        ind = round(first["x"] - cx, 2)
        if abs(ind) > 0.05:
            st.append(F('#side input[data-a="indent_first"]', ind))
        st += slot(slot_txt) + justify()
        st += [{"pick": {"at": '#side select[data-a="tail.part"]', "value": OXP["id"]}, "wait": 800},
               F('#side input[data-a="tail.gap"]', gap), F('#side input[data-a="tail.drop"]', drop),
               {"click": '#side input[data-a="tail.space"]', "wait": 600}]
        if fold:
            st.append(F('#side input[data-a="fold"]', fold))
        grow.append((first["base"] + 1, (lines - 1) * slead_mm))
    if nmax > len(nums) and nums:                                        # 더 둘 줄 — 견본 끝 줄 다음부터 한 줄 문장 간격으로(원고에 있으면 들어가고, 없으면 접힌다)
        pitch = min([b["base"] - a["base"] for a, b in zip(nums, nums[1:])] or [10.0])
        n0 = nums[-1]
        ssz = stext[-1]["size"] if stext else 8.0
        cx = min(o["x"] for o in stext if abs(o["base"] - n0["base"]) > 1) if any(abs(o["base"] - n0["base"]) > 1 for o in stext) else n0["x"] + 6.0
        for k in range(len(nums), nmax):
            base = n0["base"] + (k - len(nums) + 1) * pitch
            sh = shift(base - 3)
            fold = f"{label}{k + 1}"
            st += [S(f"{label} {k + 1:02d} — 더 둘 줄(접기 묶음 「{fold}」)", 600)]
            st += text(round(n0["x"], 2), round(top_of(base, 9, LOTTE, 400) - sh, 2), round(right - n0["x"], 1), round(9 * 1.45 * MM * 1.03, 1), "00.", 9, n0["color"],
                       font=LOTTE)
            st += slot(slot_no) + [F('#side input[data-a="fold"]', fold)]
            st += text(round(cx, 2), round(top_of(base, ssz, NOTO, 400, 19.25) - sh, 2), round(right - cx, 2), round(19.25 * MM, 2), "임시 문장.", ssz, "#231f20",
                       leading=19.25, align="justify", font=NOTO, track=strk)
            st += slot(slot_txt) + justify()
            st += [{"pick": {"at": '#side select[data-a="tail.part"]', "value": OXP["id"]}, "wait": 800},
                   F('#side input[data-a="tail.gap"]', 1.0), F('#side input[data-a="tail.drop"]', 1.0),
                   {"click": '#side input[data-a="tail.space"]', "wait": 600}, F('#side input[data-a="fold"]', fold)]
    return st


B11_BIND = "문장번호+문장"
B11 = {}


def b11_parts(pno):
    sp, dr = spans_of(pno), drawings(pno)
    nb = numbers(pno)[0]
    nums = [o for o in sp if LOTTE in o["font"]]
    stext = [o for o in sp if o["font"].startswith("NotoSans") and o["base"] > nb["y"] + 3]
    oxs = [d for d in dr if d["n"] == 20 and d["fill"] == "#ffffff" and d["stroke"] == LINK]
    rows = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        ln = [o for o in stext if n["base"] - 0.5 < o["base"] < nxt - 1]
        bx = min([d for d in oxs if n["base"] - 6 < d["y"] < nxt - 3], key=lambda d: d["y"])
        rows.append({"n": n, "ln": ln, "bx": bx})
    return sp, dr, nb, rows


def b11_style(pno):
    import statistics
    sp, dr, nb, rows = b11_parts(pno)
    below = lambda base, sz, pt: pt * MM - (base - top_of(base, sz, NOTO, 400, pt))
    r0 = next(r for r in rows if len(r["ln"]) > 1)
    first, cont = r0["ln"][0], r0["ln"][1]
    ssz = first["size"]
    slead_mm = cont["base"] - first["base"]
    slead = slead_mm / MM
    strk = line_track([r["ln"][-1] for r in rows], NOTO, 400)
    x0 = min(r["n"]["x"] for r in rows)
    gaps = []
    for a_, b_ in zip(rows, rows[1:]):
        same = abs(a_["bx"]["y"] + a_["bx"]["h"] - a_["ln"][-1]["base"]) < 2.5
        lb = a_["ln"][-1]["base"] + (0 if same else slead_mm)
        gaps.append(top_of(b_["ln"][0]["base"], ssz, NOTO, 400, slead) - (lb + below(lb, ssz, slead)))
    t_same = next(r for r in rows if abs(r["bx"]["y"] + r["bx"]["h"] - r["ln"][-1]["base"]) < 2.5)
    _, _, adv = face(NOTO, 400)
    lst = t_same["ln"][-1]
    B11.update(x=x0, top=round(top_of(rows[0]["ln"][0]["base"], ssz, NOTO, 400, slead), 2), w=round(max(o["x1"] for r in rows for o in r["ln"]) + 0.5 - x0, 2),
               ssz=ssz, slead=round(slead, 2), strk=strk, ind=round(cont["x"] - x0, 2), first=round(r0["n"]["x"] - cont["x"], 2),
               inline_w=round(first["x"] - r0["n"]["x"], 2), num_color=r0["n"]["color"], num_size=r0["n"]["size"], space=round(statistics.median(gaps), 2),
               ox_gap=round(t_same["bx"]["x"] - lst["x1"] - adv(" ") * ssz * MM - 2 * strk / 1000 * ssz * MM, 3),
               ox_drop=round(t_same["bx"]["y"] + t_same["bx"]["h"] - lst["base"], 3))


def bgox_body(pno):
    st = []
    if not OXP.get("id"):
        st += make_ox_part(pno)
    if "x" not in B11:
        b11_style(pno)
    with top_spot():
        st += _bgox_body(pno)
    return st


def _bgox_body(pno):
    st = []
    G = B11
    if not G.get("made"):
        st += pst_steps([("어법OX·문장번호", {"font": LOTTE, "size": G["num_size"], "color": G["num_color"], "tracking": 1}),
                         ("어법OX·문장", {"font": NOTO, "size": G["ssz"], "leading": G["slead"], "tracking": G["strk"], "color": "#231f20", "align": "justify",
                                       "indent": G["ind"], "indent_first": G["first"], "space_same": G["space"], "keep_together": True})], "단락 스타일 — 어법 O/X")
        G["made"] = True
    sp, dr, nb, rows = b11_parts(pno)
    st += T(nb, YD, 400, label="지문 번호 — 원고 자리 「지문번호」", slot_name="지문번호", temp="00")
    bot = 281.0
    bars = [d for d in dr if d["fill"] == LINK and d["w"] < 1]
    for r in rows:                                                       # O/X 칸 — 문장을 따라 놓이는 원고 요소
        bx = r["bx"]
        o = bx["sw"] * MM / 2
        E({"id": f"ox{len(ELEMS[len(PAGES)])}", "x": round(bx["x"] - o, 2), "y": round(bx["y"] - o, 2), "w": round(bx["w"] + 2 * o, 2), "h": round(bx["h"] + 2 * o, 2),
           "color": LINK, "see": LINK, "pad": 0.3, "ctol": 30, "원고": True})
        ob = min(bars, key=lambda d: abs(d["x"] - bx["x"] - 10) + abs(d["y"] - bx["y"]))
        E({"id": f"oxb{len(ELEMS[len(PAGES)])}", "x": round(ob["x"], 2), "y": round(ob["y"], 2), "w": round(ob["w"], 2), "h": round(ob["h"], 2),
           "color": LINK, "see": LINK, "pad": 0.15, "ctol": 30, "원고": True})
    fx = min(r["n"]["x"] for r in rows)                                   # 이 쪽의 프레임 왼쪽 = 이 쪽 문장 번호(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    right = max([fx + G["w"]] + [r["bx"]["x"] + r["bx"]["w"] + 0.5 for r in rows])
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(right - fx, 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("본문 — 텍스트 프레임 하나(문장마다 번호 · 글 · 끝에 O/X 칸이 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), round(G["top"], 2), round(G["w"], 2), round(bot - G["top"], 2), "임시 문장 — 원고가 오면 문장마다 번호 · 글이 차례로 흐른다.",
               G["ssz"], "#231f20", label="본문 글상자 — 한 줄기(" + B11_BIND + ")", font=NOTO, leading=G["slead"])
    st += slot(B11_BIND, label="자리 — " + B11_BIND)
    for nm in B11_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "어법OX·" + nm}, "wait": 450})
    st += [{"click": '#side input[data-a="slotfmt.문장번호.inline"]', "wait": 600}, F('#side input[data-a="slotfmt.문장번호.inline_w"]', G["inline_w"], 600),
           S("문장 끝에 O/X 칸 — 데이터 필드 「문장」의 고정 개체(문단 끝, 띄어 붙이기)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.문장.anc.part"]', "value": OXP["id"]}, "wait": 900},
           F('#side input[data-a="slotfmt.문장.anc.gap"]', G["ox_gap"], 600), F('#side input[data-a="slotfmt.문장.anc.dy"]', G["ox_drop"], 600),
           {"click": '#side input[data-a="slotfmt.문장.anc.space"]', "wait": 600}]
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    return st


def bgox_record(lp, rp):
    """어법 O/X 펼침면 하나의 원고 — 쪽마다 지문 번호 + 한 줄기(문장마다 번호 · 글). 보기 예문(첫 회차 시범)은 템플릿에 두지 않는다 — contents 도 안 보낸다"""
    rec = {"제목": None, "지문번호": [], B11_BIND: []}
    for pno in (lp, rp):
        sp, dr, nb, rows = b11_parts(pno)
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        rec["지문번호"].append(nb["text"])
        rec[B11_BIND].append([[["문장번호", r["n"]["t"].strip()], ["문장", " ".join(o["t"].strip() for o in r["ln"])]] for r in rows])
    return rec


if want(11):
    st += body_pages(148, "B1", "어법 O/X", "B어법OX", "⑪ B어법OX", body=bgox_body)      # 견본 = 148·149쪽 — 146쪽의 보기 예문(첫 회차 시범)은 템플릿에 두지 않는다
    CONTENT["B어법OX"] = [bgox_record(l, l + 1) for l in list(range(148, 166, 2)) + [146]]   # 첫 원고 = 견본(148·149쪽) — 견본 쪽과 맞대고 관리 견본도 이것

# ── 구성 12 「C빈칸어법」 (원본 166~185쪽 = 펼침면 10벌 · 원고마다) — 견본 = 166·167쪽 ──
# 구성 9 와 같은 흐름(문항번호 + 빈칸문장 + 해석) — 빈칸은 글자 없는 밑줄(원고 꼴 「__」), 영어 9pt. 단락 스타일 이름은 「…·어법」
C3 = {"bind": "문항번호+빈칸문장+해석", "sfx": "·어법", "key": "C빈칸어법"}

if want(12):
    st += body_pages(166, "C1", "빈칸 어법", "C빈칸어법", "⑫ C빈칸어법", body=lambda p: c2_body(p, C3))
    CONTENT["C빈칸어법"] = [c2_record(l, l + 1, C3) for l in range(166, 186, 2)]

# ── 구성 13 「C영작배열」 (원본 186~195쪽 = 펼침면 5벌 · 원고마다) — 견본 = 186·187쪽 ──
# 흐름 방식(2026-10-14): 텍스트 프레임 하나에 지문 번호 · 문항마다 번호(붙임) · 우리말 · 낱말(연보라 둥근 음영, 너비 「텍스트」).
# 답 쓰는 곳(화살표 둘 · 줄 둘) = 데이터 필드 「보기단어」의 고정 개체(다음 줄). 문항이 없으면 문단이 안 생긴다.


def corner_r(d):
    """둥근 네모 경로의 모서리 둥글기(mm) — 첫 곡선의 가로 폭"""
    c = next((it for it in d["items"] if it[0] == "c"), None)
    return round(abs(c[4].x - c[1].x) * MM, 2) if c else 0


def wo_parts(pno):
    sp, dr = spans_of(pno), drawings(pno)
    nums = [o for o in sp if LOTTE in o["font"]]
    boxes = [d for d in dr if d["fill"] and d["n"] == 8 and d["w"] > 50]
    out = []
    for k, n in enumerate(nums):
        nxt = nums[k + 1]["base"] if k + 1 < len(nums) else 280
        nxp = min([e["y"] for e in numbers(pno) if e["y"] > n["base"]] + [nxt])
        bx = min([d for d in boxes if n["base"] < d["y"] < nxt], key=lambda d: d["y"])
        ko = [o for o in sp if o["font"].endswith("Regular") and o["size"] == 8.5 and n["base"] - 0.5 < o["base"] < bx["y"]]
        wd = [o for o in sp if o["font"].endswith("Medium") and bx["y"] < o["base"] < bx["y"] + bx["h"] + 0.5]
        deco = [d for d in dr if bx["y"] + bx["h"] < d["y"] < min(nxt, nxp) and (d["n"] == 3 or (d["h"] < 0.5 and d["w"] > 100))]
        out.append({"n": n, "ko": ko, "wd": wd, "box": bx, "deco": deco,
                    "rec": {"문항번호": n["t"].strip(), "우리말": " ".join(o["t"].strip() for o in ko), "보기단어": " ".join(o["t"].strip() for o in wd)}})
    return out


def wo_starts(pno, items):
    """문항마다 그 위에서 시작하는 지문 번호(없으면 None)"""
    pn = numbers(pno)
    out = []
    for k, it in enumerate(items):
        prev = items[k - 1]["n"]["base"] if k else 0
        out.append(next((e for e in pn if prev < e["y"] + 3 < it["n"]["base"]), None))
    return out


C13_BIND = "지문번호+문항번호+우리말+보기단어"
C13 = {}


def c13_style(pno):
    import statistics
    items = wo_parts(pno)
    starts = wo_starts(pno, items)
    below = lambda base, sz, fam, wt, pt: pt * MM - (base - top_of(base, sz, fam, wt, pt))
    x0 = min([it["n"]["x"] for it in items] + [pe["x"] for pe in starts if pe])
    it0 = next(it for it in items if len(it["ko"]) > 1) if any(len(it["ko"]) > 1 for it in items) else items[0]
    ko = it0["ko"]
    kl_mm = (ko[1]["base"] - ko[0]["base"]) if len(ko) > 1 else 4.59
    cont_x = ko[1]["x"] if len(ko) > 1 else ko[0]["x"]
    bx, wd = it0["box"], sorted(it0["wd"], key=lambda o: o["base"])
    m = para_metrics(wd, 8.5)
    w_top = top_of(m["base0"], 8.5, NOTO, 500, m["lead_mm"] / MM)
    deco = it0["deco"]
    d_top, d_bot = min(d["y"] for d in deco), max(d["y"] + d["h"] for d in deco)
    k_top = lambda it: top_of(it["ko"][0]["base"], 8.5, NOTO, 400, kl_mm / MM)
    sb_k, sb_p = [], []
    for pg_ in (pno, pno + 1):                                           # 견본 펼침면 두 쪽 모두 — 원본은 지문 번호 앞 간격이 쪽마다 다르다(9.9 · 2.2 · 5.3mm) → 가운데 값
        its = items if pg_ == pno else wo_parts(pg_)
        sts = starts if pg_ == pno else wo_starts(pg_, its)
        for k, it in enumerate(its[1:], 1):                              # 앞 문항 답 줄 아래 → 이 문항 첫 줄(지문 번호가 있으면 지문 번호)
            pd = max(d["y"] + d["h"] for d in its[k - 1]["deco"])
            pe = sts[k]
            if pe:
                sb_p.append(top_of(pe["y"] + 0.95 * 12 * MM, 12, YD, 400) - pd)
            else:
                sb_k.append(k_top(it) - pd)
    pe0 = next((pe, it) for pe, it in zip(starts, items) if pe)
    pnb = pe0[0]["y"] + 0.95 * 12 * MM                                    # 지문 번호 기준선
    k_sb = statistics.median(sb_k) if sb_k else 3.0
    after_p = k_top(pe0[1]) - (pnb + below(pnb, 12, YD, 400, 12 * 1.45))   # 지문 번호 줄 아래 → 우리말 줄 위(원본)
    # 인디자인은 앞 문단 「뒤 간격」 + 이 문단 「앞 간격」을 더한다 — 우리말 앞 간격(k_sb)이 이 사이보다 크면 지문 번호 행간을 줄여 맞춘다(뒤 간격은 음수가 안 된다)
    cut = max(0.0, k_sb - after_p)
    p_lead = round(12 * 1.45 - 2 * cut / MM, 2)
    C13.update(x=x0, top=round(top_of(pnb, 12, YD, 400) if starts[0] else k_top(items[0]), 2), w=round(max(o["x1"] for it in items for o in it["ko"] + it["wd"]) + 1 - x0, 2), kw=round(max(o["x1"] for it in items for o in it["ko"]) - x0, 2),
               kl=round(kl_mm / MM, 2), ktrk=gaps_track([c for c in ko[-1]["ink"]], 8.5) or 1, k_ind=round(cont_x - x0, 2), k_first=round(it0["n"]["x"] - cont_x, 2),
               inline_w=round(ko[0]["x"] - it0["n"]["x"], 2), num_color=it0["n"]["color"], num_size=it0["n"]["size"],
               k_sb=round(k_sb, 2), p_sb=round((statistics.median(sb_p) if sb_p else 3.0) + cut, 2), p_lead=p_lead,
               k_after_p=round(max(0.0, after_p - k_sb), 2),
               ww=dict(fill=bx["fill"], r=corner_r(bx), ind=round(bx["x"] - x0, 2), pad=round(m["x_t"] - bx["x"], 2), pad_top=round(w_top - bx["y"], 2),
                      pad_bottom=round(bx["y"] + bx["h"] - (w_top + m["lines"] * m["lead_mm"]), 2), lead=round(m["lead_mm"] / MM, 2), trk=m["trk"] or 1,
                      sb=round(bx["y"] - (ko[-1]["base"] + below(ko[-1]["base"], 8.5, NOTO, 400, kl_mm / MM)), 2)),
               deco=dict(x=round(min(d["x"] for d in deco) - x0, 2), gap=round(d_top - (bx["y"] + bx["h"]), 2)))


def c13_make_part(pno):
    """부품 — 답 쓰는 곳(화살표 둘 · 가는 줄 둘): 낱말 상자 아래 제 줄. 빈 자리에 그려 묶는다"""
    it0 = next(it for it in wo_parts(pno) if it["deco"])
    deco = it0["deco"]
    bx0, by0 = min(d["x"] for d in deco), min(d["y"] for d in deco)
    bx1, by1 = max(d["x"] + d["w"] for d in deco), max(d["y"] + d["h"] for d in deco)
    X0, Y0 = 15.0, 262.0
    dx, dy = X0 - bx0, Y0 - by0
    st = [S("답 쓰는 곳 부품 — 화살표 둘 · 줄 둘을 빈 자리에 그려 묶는다(낱말 상자의 고정 개체)", 1300)]
    for d in deco:
        if d["n"] == 3:
            st += shape(round(d["x"] + dx, 2), round(d["y"] + dy, 2), round(d["w"], 2), round(d["h"], 2), d["fill"], d=poly_d(pno, {"x": d["x"], "y": d["y"]}))
        else:
            st += box(round(d["x"] + dx, 2), round(d["y"] + dy, 3), round(d["w"], 2), round(d["h"], 3), d["fill"])
    C13["part"] = group_part(st, len(deco), X0, Y0, bx1 - bx0, by1 - by0)
    return st


def wo_body(pno):
    st = []
    if "x" not in C13:
        c13_style(pno)
        st += c13_make_part(pno)
    with top_spot():
        st += _wo_body(pno)
    return st


def _wo_body(pno):
    st = []
    G = C13
    if not G.get("made"):
        W = G["ww"]
        st += pst_steps([("영작·지문번호", {"font": YD, "size": 12, "leading": G["p_lead"], "color": "#af9d81", "space_before": G["p_sb"], "space_after": G["k_after_p"], "keep_next": True}),
                         ("영작·문항번호", {"font": LOTTE, "size": G["num_size"], "color": G["num_color"], "tracking": 1}),
                         ("영작·우리말", {"font": NOTO, "size": 8.5, "leading": G["kl"], "tracking": G["ktrk"], "color": "#231f20", "align": "justify",
                                       "indent": G["k_ind"], "indent_first": G["k_first"], "space_before": G["k_sb"], "keep_next": True}),
                         ("영작·보기단어", {"font": NOTO, "weight": 500, "size": 8.5, "leading": W["lead"], "tracking": W["trk"], "color": "#231f20", "align": "left",
                                         "indent": W["ind"], "shade": W["fill"], "shade_fit": True, "shade_r": W["r"], "pad": W["pad"], "pad_top": W["pad_top"],
                                         "pad_bottom": W["pad_bottom"], "space_before": W["sb"], "keep_together": True})], "단락 스타일 — 영작 배열")
        G["made"] = True
    items = wo_parts(pno)
    bot = 281.0
    for it in items:                                                     # 낱말 상자 · 답 쓰는 곳 — 문항을 따라 놓이는 원고 요소
        b = it["box"]
        E({"id": f"bg{len(ELEMS[len(PAGES)])}", **{k: clip(b)[k] for k in ("x", "y", "w", "h")}, "color": b["fill"], "see": b["fill"], "pad": 0.6, "ctol": 8, "원고": True})
        for d in it["deco"]:
            E({"id": f"d{len(ELEMS[len(PAGES)])}", **{q: round(d[q], 2) for q in ("x", "y", "w", "h")}, "color": d["fill"], "see": d["fill"], "pad": 0.2, "ctol": 20, "원고": True})
    fx = min([it["n"]["x"] for it in items] + [pe["x"] for pe in wo_starts(pno, items) if pe])   # 이 쪽의 프레임 왼쪽(오른쪽 면은 펼침면 여백만큼 옮겨 있다)
    right = max([fx + G["kw"]] + [d["x"] + d["w"] for it in items for d in it["deco"]])
    E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(fx, 2), "y": round(G["top"], 2), "w": round(right - fx, 2), "h": round(bot - G["top"], 2),
       "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("본문 — 텍스트 프레임 하나(지문 번호 · 문항마다 번호 · 우리말 · 낱말 상자 · 답 쓰는 곳이 원고만큼 흐른다)", 1200)]
    st += text(round(fx, 2), round(G["top"], 2), round(right - fx, 2), round(bot - G["top"], 2), "임시 우리말 — 원고가 오면 문항마다 차례로 흐른다.",
               8.5, "#231f20", label="본문 글상자 — 한 줄기(" + C13_BIND + ")", font=NOTO, leading=G["kl"])
    st += slot(C13_BIND, label="자리 — " + C13_BIND)
    for nm in C13_BIND.split("+"):
        st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "영작·" + nm}, "wait": 450})
    st += [{"click": '#side input[data-a="slotfmt.문항번호.inline"]', "wait": 600}, F('#side input[data-a="slotfmt.문항번호.inline_w"]', G["inline_w"], 600),
           S("낱말 상자 아래 답 쓰는 곳 — 데이터 필드 「보기단어」의 고정 개체(다음 줄)", 1000),
           {"pick": {"at": '#side select[data-a="slotfmt.보기단어.anc.part"]', "value": G["part"]}, "wait": 900},
           {"pick": {"at": '#side select[data-a="slotfmt.보기단어.anc.pos"]', "value": "line"}, "wait": 800},
           F('#side input[data-a="slotfmt.보기단어.anc.x"]', G["deco"]["x"], 600), F('#side input[data-a="slotfmt.보기단어.anc.gap"]', G["deco"]["gap"], 600)]
    st += justify()
    st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    return st


def wo_record(lp, rp):
    """영작 배열 펼침면 하나의 원고 — 쪽마다 한 줄기(지문이 바뀌면 지문 번호 · 문항마다 번호 · 우리말 · 낱말)"""
    rec = {"제목": None, C13_BIND: []}
    for pno in (lp, rp):
        if pno == lp:
            rec["제목"] = next("".join(c["c"] for c in s_["chars"]).strip() for b in REF[pno - 1].get_text("rawdict")["blocks"]
                              for l in b.get("lines", []) for s_ in l["spans"] if round(s_["size"], 1) == 13.0)
        items = wo_parts(pno)
        starts = wo_starts(pno, items)
        out = []
        for pe, it in zip(starts, items):
            if pe:
                out.append([["지문번호", pe["text"]]])
            out.append([["문항번호", it["rec"]["문항번호"]], ["우리말", it["rec"]["우리말"]], ["보기단어", it["rec"]["보기단어"]]])
        rec[C13_BIND].append(out)
    return rec


if want(13):
    st += body_pages(186, "C2", "영작 배열", "C영작배열", "⑬ C영작배열", body=wo_body)
    CONTENT["C영작배열"] = [wo_record(l, l + 1) for l in range(186, 196, 2)]

if want("2.3"):                                                         # STEP 03 간지·차례 — 구성 2·3 의 세 번째 회차
    st += divider(196, "03")
if want("3.3"):
    st += toc(197, "03")

# ── 구성 14 「S실전문제」 (원본 198~272쪽 — 흐르는 쪽) ── 견본 = 198·199쪽 두 면, 나머지는 넘친 글이 덧쪽을 만든다(왼쪽·오른쪽 번갈아)
# 흐름 틀(인디자인 스토리): 문항 전체가 한 줄기 글(자리 S_BIND), 면마다 두 단 글상자를 글 잇기로 이어 흘린다. 자리마다 단락 스타일(브랜드 「실전·…」).
# 두 면 모두 「한 번만」 찍고, 서로 「넘치면 이어 갈 면」. 머리 제목은 덧쪽에도 있어야 해서 고정 글(원고 자리 아님).
# 원본 읽기 = 예전 실전 문제 대본(14a)의 묶음 나누기 · 글 잇기 · 글 꺼내기(방법만) — 값(행간·간격·색)은 이 원본에서 잰다.
S_BIND = "지문번호+번호+발문+보기+지문+요약문+선지+조건+주석"
SR = {}


def s_reader():
    """S 원본 읽기 — 묶음(GROUPS) · 글 꺼내기(gtext) · 글 잇기(chain). 14a 대본의 읽기 부분만(그 책 맞춤 계산은 빼고)"""
    if SR:
        return SR
    u14 = os.path.join(os.path.dirname(HERE), "14a-S실전문제", "make.py")
    src = open(u14, encoding="utf-8").read().split("# ── 문서 ─")[0]
    src = src.replace('REF = os.path.join(REPO, STATE["ref"])', 'REF = os.path.join(REPO, ' + repr(STATE["ref"]) + ')')
    src = src.replace("PAGES = list(range(48, 57))", "PAGES = list(range(198, 273))")
    src = src.replace('''                else:
                    cur["lines"].append(ln)
            elif r and r[0] == "bogi":''', '''                else:
                    if not (cur and cur["kind"] == "cond"):                       # 단 맨 위에서 이어지는 조건 상자
                        cur = {"kind": "cond", "lines": [], "left": left, "rect": r}
                        gs.append(cur)
                    cur["lines"].append(ln)
            elif r and r[0] == "bogi":''')
    src = src.replace("for _pno in PAGES + [PAGES[-1] + 1]:", "for _pno in PAGES:")
    i, j = src.index("\nALL = {}\n"), src.index("# ── 글 잇기")
    src = src[:i] + "\n" + src[j:]
    G_ = {"__file__": u14, "__name__": "s14"}
    exec(compile(src, u14, "exec"), G_)
    SR.update(G_)
    return SR


S_KIND = {"prompt": "발문", "passage": "지문", "opts": "선지", "stmt": "선지", "bogi": "보기", "cond": "조건", "answer": "지문"}


def s_paras():
    """단마다 문단 차례 [(자리, 첫 기준선, 끝 기준선, 줄 간격들)] — 번호 줄은 발문 첫 줄과 같은 기준선"""
    G_ = s_reader()
    out = []
    for pno in G_["PAGES"]:
        for ci in (0, 1):
            seq, has_txt = [], {}
            for g in G_["GROUPS"][pno][ci]:
                if not g["lines"]:
                    continue
                k = g["kind"]
                if k == "num":
                    has_txt = bool(g["lines"][0]["text"].strip())
                    if not has_txt:
                        seq.append(("지문번호", g["lines"][0]["base"], g["lines"][0]["base"], []))
                    continue
                if k == "prompt" and not g["lines"][0]["text"].strip():
                    continue
                s = S_KIND.get(k, "지문")
                if s == "보기" and any(x[0] == "지문" for x in seq[-3:]):
                    s = "요약문"
                bs = [l["base"] for l in g["lines"]]
                seq.append((s, bs[0], bs[-1], [b - a for a, b in zip(bs, bs[1:]) if 3 < b - a < 9]))
            out.append(seq)
    return out


def s_style():
    """단락 스타일 값 — 행간(문단 안 줄 간격) · 단락 앞 간격(앞 문단 끝 줄 → 이 문단 첫 줄 - 이 행간)"""
    import statistics
    lead, gap = {}, {}
    for seq in s_paras():
        for s, b0, b1, ds in seq:
            lead.setdefault(s, []).extend(ds)
        for a, b in zip(seq, seq[1:]):
            gap.setdefault(b[0], []).append(b[1] - a[2])
    L = {k: statistics.median(v) for k, v in lead.items() if v}
    L.setdefault("지문번호", 12 * 1.2 * MM)
    sb = {k: round(max(0.0, statistics.median(v) - L.get(k, 4.94)), 2) for k, v in gap.items() if v}
    return L, sb


def s_recs(pages=None):
    """원고 — 문항 목록 [[자리, 글], …] (문항 안 차례 그대로). 지문 번호(영도 12pt)는 그 지문 첫머리. 「*낱말: 뜻」 줄은 주석"""
    G_ = s_reader()
    recs, cur = [], None
    for pno in pages or G_["PAGES"]:
        for ci in (0, 1):
            for g in G_["GROUPS"][pno][ci]:
                k = g["kind"]
                if k == "num":
                    n = "".join(c["c"] for c in g["lines"][0]["num"]).strip().split("\t")[0].strip()
                    cur = [["번호" if g["lines"][0]["text"].strip() else "지문번호", n]]
                    recs.append(cur)
                    continue
                if g.get("cont_of") or cur is None or (k == "prompt" and not g["lines"][0]["text"].strip()):
                    continue
                lines = [ln for c in G_["chain"](g) for ln in c["lines"]] if g.get("story_next") else g["lines"]
                s = S_KIND.get(k, "지문")
                if s == "보기" and any(x[0] == "지문" for x in cur):
                    s = "요약문"
                body, notes = [], []
                for ln in G_["gtext"]({"kind": k, "left": g["left"], "lines": lines}).split("\n"):
                    (notes if ln.startswith("*") else body).append(ln)
                if body:
                    cur.append([s, "\n".join(body)])
                for ln in notes:
                    cur.append(["주석", ln])
    return recs


def s_styles_steps():
    L, sb = s_style()
    pt = lambda k, d=4.94: round(L.get(k, d) / MM, 2)
    G_ = s_reader()
    B_ = {"font": NOTO, "size": 8, "align": "justify", "tracking": -50, "color": "#231f20"}
    shade_b, shade_c, line_c = G_["BOGIF"], G_["CONDF"], G_["CONDS"]
    sty = [("지문번호", {"font": YD, "size": 12, "color": "#af9d81", "leading": pt("지문번호"), "space_before": sb.get("지문번호"), "keep_next": True}),
           ("번호", {"font": EL, "weight": 700, "size": 12, "color": "#00559f", "drop": 0.55}),
           ("발문", dict(B_, leading=pt("발문", 5.15), tracking=-40, space_before=sb.get("발문"), keep_next=True, keep_together=True)),
           ("지문", dict(B_, leading=pt("지문"), space_before=sb.get("지문"), keep_first=3, keep_last=2)),
           ("보기", dict(B_, leading=pt("보기"), shade=shade_b, pad=3, space_before=sb.get("보기"))),
           ("요약문", dict(B_, leading=pt("요약문"), shade=shade_b, pad=3, space_before=sb.get("요약문"))),
           ("선지", dict(B_, align="left", leading=12, indent=3.5, indent_first=-3.5, space_before=round(sb.get("선지", 0) + L.get("선지", 12 * MM) - 12 * MM, 2),
                        space_same=1.0, keep_together=True)),                # 선지 행간 12pt + 선지끼리 1mm = 잰 줄 간격
           ("조건", dict(B_, leading=pt("조건"), shade=shade_c, border=0.5, border_color=line_c, pad=3, space_before=sb.get("조건"))),
           ("주석", {"font": NOTO, "size": 6, "color": "#58595b", "align": "right", "space_before": 1.0})]
    st = [S("단락 스타일 — 실전 문제(자리마다 하나, 브랜드 창)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in sty:
        n = "실전·" + name
        q = lambda k: f'[data-st="{n}:{k}"]'
        st += [S(f"단락 스타일 「{n}」", 800), {"answer": n}, {"click": "#st-new", "wait": 900}]
        for k, val in v.items():
            if k in ("font", "align", "weight"):
                st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
            elif k in ("keep_next", "keep_together"):
                st.append({"click": "input" + q(k), "wait": 450})
            elif val not in (None, 0, ""):
                st.append(F("input" + q(k), val, 450))
    st += [{"click": "#sheet-x", "wait": 900}]
    return st


def s_story(x, top, bot, head, w):
    """단 글상자 — 첫 상자(head)는 자리 · 자리마다 스타일 · 번호 붙이기 · 밑줄 GREP · 새 이야기, 나머지는 같은 이야기를 이어 받는다"""
    st = text(round(x, 2), round(top, 2), w, round(bot - top, 2), "임시 문항 — 번호·발문·지문·선지가 이 글상자 하나에 흘러 들어온다." if head else "이어 받는 상자",
              8, "#231f20", font=NOTO, label="문항 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기")
    if head:
        st += slot(S_BIND, label="자리 — " + S_BIND + " (원고에 나온 차례대로 한 줄기)")
        for nm in S_BIND.split("+"):
            st.append({"pick": {"at": f'#side select[data-a="slotfmt.{nm}.style"]', "value": "실전·" + nm}, "wait": 450})
        st += [S("번호는 발문 첫 줄 앞에 붙인다 — 번호 칸 폭", 900), {"click": '#side input[data-a="slotfmt.번호.inline"]', "wait": 600},
               F('#side input[data-a="slotfmt.번호.inline_w"]', SR["S_INLINE"], 600)]
        st += [S("글 잇기 — 새 이야기(넘친 줄은 다음 단·쪽 상자로)", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    else:
        st += [S("글 잇기 — 같은 이야기를 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": "이야기1"}, "wait": 900}]
    return st


def s_body(pno):
    with top_spot():
        return _s_body(pno)


def _s_body(pno):
    import statistics
    G_ = s_reader()
    st = []
    if "S_INLINE" not in SR:
        firsts = [c["x"] - g["left"] for pg in G_["PAGES"] for ci in (0, 1) for g in G_["GROUPS"][pg][ci] if g["kind"] == "prompt" and g["lines"][0]["text"].strip()
                  for c in [next(c for c in g["lines"][0]["chars"] if c["c"].strip() and c["c"] != "\t")]]
        SR["S_INLINE"] = round(statistics.median(firsts), 2)               # 번호 칸 폭 = 발문 첫 글자 - 단 왼쪽(중앙값)
        st += s_styles_steps()
        if not ULF.get("done"):
            st += cs_steps(UL_CS, "밑줄 문자 스타일")                     # 원고의 밑줄(꾸밈 조각) — 「밑줄」 · 「밑줄 보통」
            ULF["done"] = True
    L, Rr = G_["cols_of"](pno)
    w = round(G_["COL_W"], 2)
    firsts = [min(l["base"] for g in G_["GROUPS"][pg][ci] for l in g["lines"]) for pg in G_["PAGES"] for ci in (0, 1) if G_["GROUPS"][pg][ci]]
    lasts = [max(l["base"] for g in G_["GROUPS"][pg][ci] for l in g["lines"]) for pg in G_["PAGES"] for ci in (0, 1) if G_["GROUPS"][pg][ci]]
    p0 = G_["PAGES"][0]                                                    # 단 위 끝 = 견본 첫 쪽 왼쪽 단 첫 줄(지문 번호 12pt)의 줄 상자 위
    top = round(top_of(min(l["base"] for g in G_["GROUPS"][p0][0] for l in g["lines"]), 12, YD, 400) - 0.3, 2)
    bot = round(max(lasts) + 1.5, 2)                                       # 단 아래 끝 = 가장 아래 끝 줄 기준선 + 내림
    for ci, x in ((0, L), (1, Rr)):                                        # 원고 판정 창 = 단 글상자 전체(원고가 흘러 줄 자리가 쪽마다 다르다)
        if G_["GROUPS"][pno][ci]:
            E({"id": f"col{len(ELEMS[len(PAGES)])}", "x": round(x, 2), "y": top, "w": w, "h": round(bot - top, 2),
               "color": "#231f20", "see": "#231f20", "ctol": 40, "pad": 1.0, "search": 1.0, "원고": True})
    st += [S("본문 — 두 단 글상자(글 잇기로 한 줄기)", 1200)]
    st += s_story(L, top, bot, SR.get("head_done") is None, w)
    SR["head_done"] = True
    st += s_story(Rr, top, bot, False, w)
    st += columns(2, round(Rr - L - w, 2))
    return st


if want(14):
    st += body_pages(198, "S", "실전 문제", "S실전문제", "⑭ S실전문제", body=s_body, rep=None, cont=True, fixed_title=True)
    CONTENT[S_BIND] = [[[k, marks_runs(v)] for k, v in it] for it in s_recs()]


# ── 구성 15 「MEMO」 (원본 273쪽) ── 흰 바탕 · 머리 크림 띠 · 막대 · 선 · MEMO · 점 무늬(원본에서 내보낸 그림 memo_dots.svg) · 아래 색 띠 셋
if want(15):
    st += pg_new(273, "⑮ MEMO — 원본 273쪽")
    st += need_font("Montserrat-ExtraBold.otf")
    el = [e for e in elems_of(273) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect"]
    st += B(rects[0], "바탕(아래 겹) — 재단 여백까지", measure=False)
    st += B(rects[1], "흰 바탕", measure=False)
    E({"id": "dots", "x": 1.96, "y": 27.7, "w": 208.4, "h": 266.0, "color": "#e0dad3", "see": "#e0dad3", "ctol": 16, "pad": 0.6})
    st += image(0.0, 22.93, 213.0, 277.0, os.path.join(HERE, "memo_dots.svg"), label="점 무늬 — 원본에서 내보낸 그림 파일(memo_dots.svg)을 올린다")
    for e in rects[2:]:
        st += B(e)
    for e in [e for e in el if e["k"] == "line"]:
        st += rule(e)
    st += T([e for e in el if e["k"] == "text" and e["text"] == "MEMO"][0], MS, 800, label="MEMO — Montserrat ExtraBold(자간 넓게 — Bold 는 잉크 87%)")
    st += done("MEMO", "p273.png")

# ── 구성 16 「뒤표지」 (원본 274쪽) ── 꼬리표 · 큰 제목 · 한글 제목 · 만든 사람(역할 · 이름) · 색 띠 셋 · 로고(logo_back.svg) · 저작권
if want(16):
    st += pg_new(274, "⑯ 뒤표지 — 원본 274쪽")
    st += need_font("Montserrat-ExtraBold.otf")
    st += need_font("SUIT-Regular.otf")
    el = [e for e in elems_of(274) if onpage(e)]
    rects = [e for e in el if e["k"] == "rect" and e["fill"] != "#2c292a"]
    st += B(rects[0], "바탕 — 재단 여백까지", measure=False)
    st += B(rects[1], "왼쪽 위 파란 막대")
    tag = [e for e in rects if e["n"] == 4][0]
    E({"id": "tag", "x": tag["x"], "y": tag["y"], "w": round(210 - tag["x"], 2), "h": tag["h"], "color": tag["fill"]})
    st += shape(tag["x"], tag["y"], tag["w"], tag["h"], tag["fill"], d=poly_d(274, tag), label="오른쪽 위 꼬리표 — 원본 꼭짓점 그대로")
    texts = [e for e in el if e["k"] == "text"]
    st += T(min((e for e in texts if e["text"] == "STEP BY STEP"), key=lambda e: e["size"]), MS, 700, label="꼬리표 글", search=0.25, ctol=12)
    st += [S("큰 제목 — STEP · BY(파랑) · STEP", 1200)]
    st += T(span_el(274, "STEP", 0, size=21.0), MS, 800)
    st += T(span_el(274, "BY", size=21.0), MS, 800)
    st += T(span_el(274, "STEP", 1, size=21.0), MS, 800)
    for e in [e for e in rects[2:] if e["n"] != 4]:
        st += B(e)
    st += [S("한글 제목 · 만든 사람 — 역할(Montserrat Bold 파랑) · 이름(SUIT)", 1200)]
    for e in texts:
        if e["size"] == 12.0:
            st += T(e, SUIT, 400)
        elif e["size"] == 10.5:
            st += T(e, MS, 700)
    logo = [e for e in el if e.get("fill") == "#2c292a"]
    lx0, ly0 = min(e["x"] for e in logo), min(e["y"] for e in logo)
    lx1, ly1 = max(e["x"] + e["w"] for e in logo), max(e["y"] + e["h"] for e in logo)
    E({"id": "logo", "x": round(lx0, 2), "y": round(ly0, 2), "w": round(lx1 - lx0, 2), "h": round(ly1 - ly0, 2), "color": "#2c292a"})
    st += image(round(lx0, 2), round(ly0, 2), round(lx1 - lx0, 2), round(ly1 - ly0, 2), os.path.join(HERE, "logo_back.svg"), label="로고 — 원본에서 내보낸 그림 파일(logo_back.svg)")
    st += T([e for e in texts if e["text"].startswith("COPYRIGHT")][0], MS, 700, label="저작권 — Montserrat Bold")
    st += done("뒤표지", "p274.png")

# ── 원고 넣기 — 바깥 시스템이 보내는 꼴(자리 이름 → 글, 같은 자리가 여러 번이면 쪽 차례대로) ──
if not ONLY:                                                            # 전체 한 판(관리 등록) — 견본 원고만: 구성마다 견본 쪽에 드는 첫 원고 하나(2026-10-10 사용자: 관리 디자인은 구성 견본 한 벌씩, 274쪽 전부 아님)
    for k, v in list(CONTENT.items()):
        if isinstance(v, list) and v and isinstance(v[0], dict):
            CONTENT[k] = v[:1]
    if S_BIND in CONTENT:
        CONTENT[S_BIND] = s_recs((198, 199))
if CONTENT:
    st += put_content(CONTENT)

# ── 관리에 등록 — 책 전체 판에서만(문서 패널 「관리에 등록」: 폴더(틀) 고르고 등록 → 쪽 전부 그려 카드) ──
if not ONLY:
    st += [S("관리에 등록 — 폴더 「워크북」 고르고 등록", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "workbook"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 30   # 쪽 전부 그리기 — 한 번에 최대 60초씩
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); return t; })()"}]

STATE["pages"] = PAGES
json.dump(STATE, open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("정본 단계", len(st), "· 잴 지면", len(ELEMS))
