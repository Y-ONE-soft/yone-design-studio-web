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
    return ([] if len(PAGES) == 1 else add_page(label)) + [S(label, 1300)]


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
    els = _ELS.setdefault(pno, [x for x in elems_of(pno) if onpage(x)])
    gap = most
    for o in els:
        if o is e or (o["x"] <= e["x"] and o["y"] <= e["y"] and o["x"] + o["w"] >= e["x"] + e["w"] and o["y"] + o["h"] >= e["y"] + e["h"]):
            continue
        dx = max(o["x"] - (e["x"] + e["w"]), e["x"] - (o["x"] + o["w"]), 0)
        dy = max(o["y"] - (e["y"] + e["h"]), e["y"] - (o["y"] + o["h"]), 0)
        if (dx > 0 or dy > 0) and max(dx, dy) < gap / 0.8:
            gap = min(gap, round(max(dx, dy) * 0.8, 2))
    return max(gap, 0.2)


def T(e, font, weight, label=None, alpha=None, search=None, ctol=24, align=None, slot_name=None, temp=None, rot=0, s=None, leading=None):
    """원본 글 하나 — 원본 글자 상자 · 크기 · 색 · 서체 · 굵기. 기준선·첫 글자 자리 = 원본 글자 기준점(origin), 자간은 원본 글자 자리에서.
    align="right" — 오른쪽 끝 = 끝 글자 기준점 + 그 글자 폭 + 자간(브라우저 letter-spacing 은 끝 글자 뒤에도 붙는다).
    slot_name — 원고 자리: 임시 글(temp)을 치고 자리 이름을 단다(원고자리_규약.md). 원본 글은 원고 넣기로 들어온다.
    rot=90 — 세로 글(위→아래로 읽힘): 상자를 가로로 그린 뒤 회전 칸에 90. 회전은 상자 가운데를 축으로."""
    pno = PAGES[-1]
    s = s or e["text"]
    search = search if search is not None else search_of(pno, e)          # pad = 원본·결과 둘 다 이만큼 둘레까지 본다(pagecmp.measure)
    m = {"id": f"t{len(ELEMS[len(PAGES)])}", "x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"], "color": e["color"],
         "see": "auto" if alpha else e["color"], "ctol": ctol, "pad": search, "search": search, "text": s, "size": e["size"]}
    if slot_name:
        m["원고"] = True
    E(m)
    size = round(e["size"] * t3k(pno, (e["x"], e["y"], e["w"], e["h"])), 3)
    ch = sorted(chars_of(pno, e), key=lambda c: (c["oy"], c["ox"]) if rot else (c["ox"], c["oy"]))
    if not ch:
        raise RuntimeError(f"원본 글자 못 찾음: {s}")
    ox, oy = ch[0]["ox"], ch[0]["oy"]
    track = 0
    if len(s) > 1 and len(ch) > 1:
        orig = (ch[-1]["oy"] - ch[0]["oy"]) if rot else (ch[-1]["ox"] - ch[0]["ox"])
        track = round((orig - chrome_extent(font, weight, size, s)) / (len(s) - 1) / (size * MM) * 1000)
    length = (e["h"] if rot else e["w"])
    bw = round(length * 1.25 + size * 0.35, 1)
    bh = round((leading or size * 1.45) * MM * 1.03, 1)                     # 한 줄 높이(행간)보다 조금 크게 — 면 밖으로 처지지 않게
    if rot:                                                              # 회전 전 상자에서 기준선까지 b — 돌린 뒤 첫 글자 기준점이 원본 기준점에 오게 가운데를 푼다
        b = oy - top_of(oy, size, font, weight, leading)
        cx, cy = ox + b - bh / 2, oy + bw / 2
        x, top = cx - bw / 2, cy - bh / 2
    else:
        x, top = ox, top_of(oy, size, font, weight, leading)
        if align == "right":
            right = ox + chrome_extent(font, weight, size, s) + len(s) * track / 1000 * size * MM + face(font, weight)[2](s[-1]) * size * MM
            x = right - bw
    st = text(round(x, 2), round(top, 2), bw, bh, temp if slot_name else s, size, e["color"], label=label, font=font, weight=weight,
              track=track or None, alpha=alpha, align=align, leading=leading)
    if rot:
        st.append(F('#side input[data-a="rotate"]', rot))
    if slot_name:
        st += slot(slot_name)
    return st


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
st += register_font(os.path.join(FONTS, "Montserrat-ExtraBold.otf"))
st += register_font(os.path.join(FONTS, "SUIT-Regular.otf"))
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
st += pg_new(2, "② STEP 간지 — 원본 2쪽 (STEP 01)")
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
st += pg_new(3, "③ 차례 — 원본 3쪽 (STEP 01)")
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

# ── 원고 넣기 — 바깥 시스템이 보내는 꼴(자리 이름 → 글, 같은 자리가 여러 번이면 쪽 차례대로) ──
st += put_content(CONTENT)

STATE["pages"] = PAGES
json.dump(STATE, open(os.path.join(HERE, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("정본 단계", len(st), "· 잴 지면", len(ELEMS))
