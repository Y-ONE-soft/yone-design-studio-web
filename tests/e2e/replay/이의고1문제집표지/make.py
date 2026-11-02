"""이의고1 2학기 기말 문제집01 표지 — 「②송아영T_이의고1_문제집01.pdf」(펼침 1쪽 424×297mm = 뒤 210 + 책등 4 + 앞 210, 관리 cover/x0cdccd6a)를
보고 편집기로 손수 만든다. 등록 이름 「이의고1 문제집 표지 (편집기 제작)」 — 관리 「표지」 폴더.

절차: docs/편집기_재현/절차.md 「★ 템플릿 등록 — 네 단계」. 면은 하나(펼침 표지 — 구성.json).
값(자리 · 크기 · 색)은 모두 목표 PDF(상태.json ref)에서 잰다. 목표 PDF 는 크롬으로 뽑은 판 — 글자는 이름 없는 윤곽(Type3)이고
이름이 남은 글(책등 「EEGOEEGO」 · 「01」 · 「SONG AHYOUNG」 · 「| EEGO UP SERIES」)은 Paperlogy 9Black. 생성기 본문 서체는 Pretendard(인계 문서 05).
서체(fontmatch.py, 2026-11-02 · 후보 = 시스템 서체): 학교 · 시험 Pretendard 700 0.892 · 강사 600 0.943 · 경력 · 시리즈 설명 500 0.874~0.937 ·
UPGRADE 600 0.985 · 시리즈 이름 · 뱃지 700 0.86~0.92 · 큰 「EEGOEEGO」 Pretendard 900 0.915~0.920 · 「포켓북」 800 0.903
(800 · 900 은 시스템 서체 묶음에 없어 「＋ 서체」로 등록) · 「01」 은 책등에 이름이 남은 Paperlogy 900.
원고 자리(바깥 시스템이 권마다 바꾸는 글): 「표지제목」 = 학교 · 학년 · 시험(뒤 · 앞 · 책등 세 곳) · 「권번호」 = 01(세 곳). 나머지는 강사 · 시리즈 고정 글.
바탕(그러데이션 · 질감)은 원본 바탕 그림만 떼어(글 · 도형 · 사진 · UP 그림 빼고) 그림 하나로 — 원본도 구운 그림이다.

    REGISTER=1 이면 끝에 원고를 넣고 「관리에 등록」(표지 폴더)까지.
"""
import io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import mkpage
import pymupdf
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pdfsvg                                                          # noqa: E402

mkpage.SPOT = {"mm": [300, 150]}                                        # 앞표지 가운데 — 끌어 그리는 빈 자리
mkpage.AWAY = {"mm": [420, 293]}
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
WORK = os.environ.get("REPLAY_WORK") or HERE
REF_PATH = os.path.join(REPO, STATE["ref"])
REF = pymupdf.open(REF_PATH)
W_MM, H_MM = 424.0, 297.0
NAME = "이의고1 문제집 표지 (편집기 제작)"
SPEC = ("cover_eego424", "424x297")                                    # 새 페이지 크기 — 펼침(뒤 + 책등 4mm + 앞)
PRE, PAPER = "Pretendard", "Paperlogy"
INK, BLUE, YEL, WHITE = "#14161a", "#1e8fe8", "#f2e63c", "#ffffff"

ELEMS, PAGES, CONTENT = {1: []}, [1], {}


def E(e):
    ELEMS[1].append(e)


def runs():
    """원본 글 — 글자를 같은 방향 · 기준선끼리 한 줄로. 크롬이 넣은 진짜 빈칸 글자만(MuPDF 가 끼우는 빈칸은 뺀다)"""
    p, t = REF[0], REF[0].trimbox
    out = []
    for b in p.get_text("rawdict", flags=pymupdf.TEXT_INHIBIT_SPACES)["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                d = tuple(round(v) for v in l["dir"])
                for c in sp["chars"]:
                    out.append({"c": c["c"], "dir": d, "ox": (c["origin"][0] - t.x0) * MM, "oy": (c["origin"][1] - t.y0) * MM,
                                "bb": [(c["bbox"][0] - t.x0) * MM, (c["bbox"][1] - t.y0) * MM, (c["bbox"][2] - t.x0) * MM, (c["bbox"][3] - t.y0) * MM],
                                "size": round(sp["size"], 2), "color": "#%06x" % sp["color"]})
    return out


CH = runs()


def line(base, x0, x1, d=(1, 0), tol=0.15):
    """기준선(가로 글 = y, 세로 글 = x)이 base 인 글자 중 축 위치가 x0 ~ x1 인 것 — 한 줄. along = 글 진행 축의 시작 · 끝(끝 글자 상자 끝)"""
    if d == (0, 1):
        cs = sorted([c for c in CH if c["dir"] == d and abs(c["ox"] - base) < tol and x0 <= c["oy"] < x1], key=lambda c: c["oy"])
        a0, a1 = cs[0]["oy"], cs[-1]["bb"][3]
    elif d == (-1, 0):
        cs = sorted([c for c in CH if c["dir"] == d and abs(c["oy"] - base) < tol and x0 <= c["ox"] < x1], key=lambda c: -c["ox"])
        a0, a1 = cs[0]["ox"], cs[-1]["bb"][0]
    else:
        cs = sorted([c for c in CH if c["dir"] == d and abs(c["oy"] - base) < tol and x0 <= c["ox"] < x1], key=lambda c: c["ox"])
        a0, a1 = cs[0]["ox"], cs[-1]["bb"][2]
    txt = "".join(c["c"] for c in cs).strip()
    bb = [min(c["bb"][0] for c in cs), min(c["bb"][1] for c in cs), max(c["bb"][2] for c in cs), max(c["bb"][3] for c in cs)]
    return {"text": txt, "base": base, "x": a0, "x1": a1, "size": cs[0]["size"], "color": cs[0]["color"], "bb": bb, "dir": d}


def track_of(s, font, weight, size):
    """자간 ‰ — 원본 첫 ~ 끝 글자 거리와 서체 글자 폭의 차이(글자 사이 수로 나눔). 거꾸로 가는 글도 거리는 절댓값"""
    t = s["text"]
    if len(t) < 2:
        return 0
    return round((abs(s["x1"] - s["x"]) - chrome_extent(font, weight, size, t) - face(font, weight)[2](t[-1]) * size * MM) / (len(t) - 1) / (size * MM) * 1000)


def blend(fg, bg, alpha):
    """불투명도 alpha% 글이 바탕 위에 보이는 색 — 잴 색"""
    f, b = int(fg[1:], 16), int(bg[1:], 16)
    return "#" + "".join("%02x" % round(((f >> k) & 255) * alpha / 100 + ((b >> k) & 255) * (1 - alpha / 100)) for k in (16, 8, 0))


def measure(s, slot_name=None, alpha=None, on=YEL):
    """잴 자리 — 원본 글 잉크 쪽(진행 축 = 첫 ~ 끝 글자, 옆 축 = 기준선에서 글자 높이만큼)"""
    size, d = s["size"], s["dir"]
    cap = size * MM * 0.8
    if d == (0, 1):
        box = (s["base"], s["x"], cap, s["x1"] - s["x"])
    elif d == (-1, 0):
        box = (s["x1"], s["base"], s["x"] - s["x1"], cap)
    else:
        box = (s["x"], s["base"] - cap, s["x1"] - s["x"], size * MM * 1.05)
    m = {"id": f"t{len(ELEMS[1])}", "x": round(box[0], 2), "y": round(box[1], 2), "w": round(box[2], 2), "h": round(box[3], 2), "color": s["color"], "see": s["color"],
         "ctol": 24, "pad": 0.6, "search": 0.6, "text": s["text"], "size": size}
    if alpha:
        m["see"] = blend(s["color"], on, alpha)
    if slot_name:
        m["원고"] = True
    E(m)


def ink_size(s, font, weight):
    """글 크기 pt — 원본 잉크 높이(1200dpi) ÷ 그 서체로 같은 글을 그린 잉크 높이(em 비율). 이름 없는 윤곽(Type3) 큰 제목은 적힌 크기로 그리면
    잉크가 1.2배 컸다(2026-11-02) — 가로 글 · 거꾸로 글만(잉크 높이 = 세로)"""
    t = REF[0].trimbox
    bb = pymupdf.Rect(t.x0 + s["bb"][0] / MM, t.y0 + s["bb"][1] / MM, t.x0 + s["bb"][2] / MM, t.y0 + s["bb"][3] / MM)
    pix = REF[0].get_pixmap(clip=bb, dpi=1200)
    L = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")).astype(int)
    bg = int(np.median(np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]])))
    ys = np.where((L < bg - max(bg - int(L.min()), 1) // 2).any(axis=1))[0]
    ref_mm = (ys.max() - ys.min() + 1) / 1200 * 25.4
    px = 1000
    img = Image.new("L", (int(px * (len(s["text"]) + 2)), px * 2), 255)
    ImageDraw.Draw(img).text((px // 2, px // 4), s["text"], font=ImageFont.truetype(font_file(font, weight), px), fill=0)
    ys2 = np.where((np.asarray(img) < 128).any(axis=1))[0]
    return round(ref_mm / ((ys2.max() - ys2.min() + 1) / px) / MM, 2)


def T(s, font, weight, label, slot_name=None, temp=None, align=None, w=None, rotate=None, alpha=None, on=YEL, size=None):
    """원본 글 한 줄 — 가로 글은 기준선 = 원본 기준점(오른쪽 맞춤은 끝 글자 자리). 돌린 글(책등 90° · 거꾸로 180°)은 돌린 뒤 기준선 · 글 시작이 원본 자리에 오게
    상자 가운데를 잡는다(편집기는 상자 가운데로 돌린다). 상자 높이 = 줄 높이(크기 × 1.45)"""
    size = size or s["size"]
    track = track_of(s, font, weight, size)
    length = abs(s["x1"] - s["x"])
    bw = w or round(length * 1.3 + size * 0.4, 1)
    lead = round(size * 1.45, 3)
    bh = round(lead * MM * 1.03, 1)
    measure(s, slot_name, alpha, on)
    if rotate:
        top = top_of(s["base"], size, font, weight)
        A = s["base"] - top                                              # 글상자 위(top_of) → 첫 기준선
        sh = fb_shift(font, weight, size, lead)
        H = bh - sh                                                      # text() 가 첫 기준선 오프셋만큼 내린 실제 상자 높이
        dy0 = A - sh - H / 2                                             # 상자 가운데 → 기준선(돌리기 전, 아래로 +)
        if rotate == 90:                                                 # 시계 방향 90° — 글이 위에서 아래로, 기준선은 세로줄 x = 가운데 - dy0
            cx, cy = s["base"] + dy0, s["x"] + bw / 2
        else:                                                            # 180° — 글이 오른쪽에서 왼쪽으로, 기준선 y = 가운데 - dy0
            cx, cy = s["x"] - bw / 2, s["base"] + dy0
        bx, by = cx - bw / 2, cy - H / 2 - sh
    else:
        bx, by = s["x"], top_of(s["base"], size, font, weight)
        if align == "right":                                             # 크롬은 끝 글자 뒤에도 자간을 붙인다 — 그만큼 오른쪽으로
            bx = s["x1"] + track / 1000 * size * MM - bw
        elif align == "center":
            bx = (s["x"] + s["x1"]) / 2 - bw / 2
    st = text(round(bx, 2), round(by, 2), bw, bh, temp if slot_name else s["text"], size, s["color"], label=label, font=font, weight=weight,
              track=track or None, align=align, leading=lead, auto="" if rotate else "height", alpha=alpha)
    if slot_name:
        st += slot(slot_name)
        CONTENT[slot_name] = s["text"]
    if rotate:
        st.append(F('#side input[data-a="rotate"]', rotate, 600))
    return st


def rbox(x, y, w, h, fill=None, label=None, radius=0, stroke=None, sw=None):
    """사각형 · 둥근 뱃지 — 칠 또는 획(원본 CSS 테두리, pt)"""
    st = box(x, y, w, h, fill, label=label, radius=radius)
    if not fill:
        st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})
    if stroke:
        st += mkpage._color("stroke.color", stroke)
        st.append(F('#side input[data-a="stroke.w"]', sw))
    else:
        st.append({"pick": {"at": '#side select[data-a="stroke.color"]', "value": ""}, "wait": 550})
    E({"id": f"b{len(ELEMS[1])}", "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return st


def dot(x, y, d, fill, label):
    E({"id": f"c{len(ELEMS[1])}", "x": round(x, 2), "y": round(y, 2), "w": round(d, 2), "h": round(d, 2), "color": fill, "see": fill, "pad": 0.6, "ctol": 30})
    return [S(label)] + ellipse(round(x, 2), round(y, 2), round(d, 2), fill=fill)


def pic_xref(xref, nth, name, label, see="auto"):
    """원본에 박힌 그림(사진 · UP 그림)을 투명 마스크까지 그대로 — 원본이 놓은 자리 · 크기에"""
    info = [i for i in REF[0].get_image_info(xrefs=True) if i["xref"] == xref][nth]
    t = REF[0].trimbox
    b = info["bbox"]
    x, y, w, h = (b[0] - t.x0) * MM, (b[1] - t.y0) * MM, (b[2] - b[0]) * MM, (b[3] - b[1]) * MM
    path = ref_image(REF, xref, os.path.join(WORK, f"{name}.png"))
    E({"id": f"i{len(ELEMS[1])}", "x": round(max(x, 0), 2), "y": round(max(y, 0), 2), "w": round(min(x + w, W_MM) - max(x, 0), 2), "h": round(min(y + h, H_MM) - max(y, 0), 2),
       "color": see, "see": see, "pad": 0.6, "ctol": 30 if see == "auto" else 40})
    return image(round(x, 2), round(y, 2), round(w, 2), round(h, 2), path, label=label) + [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]


def background():
    """바탕 그림 — 크롬이 쪽 안에 바로 박은 그림(쪽 높이를 다 덮는 것) 셋: 앞표지 그러데이션(불투명) · 뒤 · 앞 질감(회색 + 투명 마스크,
    원본은 곱하기 10% — 토너 가로 줄을 깨는 알갱이, 인계 문서 03). 원본 그림 그대로 PNG 로 꺼내 그 자리에, 질감은 곱하기 · 불투명도 10%"""
    src, t = REF[0], REF[0].trimbox
    st = []
    for b in src.get_text("dict")["blocks"]:
        r = pymupdf.Rect(b["bbox"])
        if b["type"] != 1 or r.height < src.mediabox.height * 0.9:          # 사진 · UP 그림 · 1화소 띠는 뺀다
            continue
        im = Image.open(io.BytesIO(b["image"])).convert("RGB")
        grain = bool(b.get("mask"))
        if grain:
            im.putalpha(Image.open(io.BytesIO(b["mask"])).convert("L"))
        side = "앞" if r.x0 > src.mediabox.width / 3 else "뒤"
        path = os.path.join(WORK, f"바탕_{side}_{'질감' if grain else '그러데이션'}.png")
        im.save(path)
        x, y, w, h = (r.x0 - t.x0) * MM, (r.y0 - t.y0) * MM, r.width * MM, r.height * MM
        st += image(round(x, 2), round(y, 2), round(w, 2), round(h, 2), path,
                    label=f"{side}표지 {'질감 — 곱하기 · 불투명도 10%' if grain else '그러데이션'} — 원본 그림")
        st += [{"pick": {"at": '#side select[data-a="fit"]', "value": "fill"}, "wait": 900}]
        if grain:
            st += [{"pick": {"at": '#side select[data-a="fx.blend"]', "value": "multiply"}, "wait": 700}] + opacity(10)
    return st


# ── 면 ────────────────────────────────────────────────────────────────
st = open_doc(NAME)
st += expect_pages(1)
st += [S("① 표지 펼침 — 뒤 · 책등 · 앞 (원본 1쪽)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700},
       S(f"새 페이지 크기 「{SPEC[0]}」 {SPEC[1]}mm — 뒤 210 + 책등 4 + 앞 210", 1200), {"answer": list(SPEC)},
       {"pick": {"at": "#side #s-spec", "value": "__new"}, "wait": 2500},
       {"js": f"(() => {{ if (page.spec !== '{SPEC[0]}') throw new Error('페이지 크기 안 바뀜 ' + page.spec); return '페이지 크기 ' + page.spec; }})()"},
       {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 700}, F("#side #s-pname", "표지", 900)]

FONTS = os.path.expanduser("~/Library/Fonts")
for fname in ("Pretendard-ExtraBold.otf", "Pretendard-Black.otf"):          # 시스템 서체 묶음에 Pretendard 는 300~700 만 — 큰 제목(Black) · 「포켓북」(ExtraBold)용
    st += text(20.0, 3.0, 24.0, 9.0, "서체", 9, INK, label=f"서체 등록 — 글상자를 그려 고른 채 「＋ 서체」({fname}) → 등록 뒤 그 글상자는 지운다")
    st += register_font(os.path.join(FONTS, fname)) + [{"click": "#side #s-x", "wait": 900}]
st += [S("바탕 — 뒤표지 노랑(원본 면) · 바탕 그림 · 책등 파랑", 1200)]
st += rbox(-3.0, -3.0, 215.9, 303.0, YEL, label="뒤표지 노랑 면")
ELEMS[1].pop()                                                           # 바탕 그림이 위에 겹쳐 노랑이 그대로 안 보인다 — 바탕 그림으로 잰다
st += background()
st += rbox(209.98, -3.0, 3.97, 303.0, BLUE, label="책등 파랑 띠")

# 뒤표지
s_ = line(26.06, 0, 120)
st += T(s_, PRE, 900, "EEGOEEGO — 고정 글(Pretendard 900 · 잉크 높이로 크기)", size=ink_size(s_, PRE, 900))
st += T(line(17.1, 160, 200), PRE, 700, "학교 · 시험 — 원고 자리 「표지제목」(오른쪽 맞춤 — 원 끝에)", slot_name="표지제목", temp="학교 학기 시험", align="right", w=40)
st += rbox(170.95, 21.99, 14.55, 6.61, None, "「문제집」 테두리 뱃지", radius=1.17, stroke=INK, sw=0.75)
st += T(line(26.36, 170, 186), PRE, 700, "문제집 — 고정 글")
st += dot(187.75, 20.8, 9.26, BLUE, "권 번호 원")
st += T(line(26.89, 186, 200), PAPER, 900, "권 번호 — 원고 자리 「권번호」(원 가운데)", slot_name="권번호", temp="00", align="center", w=9.26)
st += T(line(45.14, 0, 120), PRE, 700, "강사 문구 — 고정 글")
st += rbox(12.86, 62.87, 0.26, 40.48, INK, "강사 소개 왼쪽 세로줄")
st += T(line(66.57, 15, 24), PRE, 600, "「강사」 — 고정 글(불투명도 85%)", alpha=85)
st += T(line(66.57, 24, 45), PRE, 700, "강사 이름 — 고정 글")
for b in (75.83, 82.18, 88.8, 95.15, 101.5):
    st += T(line(b, 15, 80), PRE, 500, "강사 경력 — 고정 글")
st += pic_xref(15, 0, "강사_사진", "강사 사진 — 원본 그림")
st += T(line(195.96, 0, 120), PAPER, 900, "| EEGO UP SERIES — 고정 글(Paperlogy 900)")
for lab_b, x0b, (bx, by, bw_, bh_, fill, stroke, r), txt_b, dsc_b in (
        (206.27, 12, (30.06, 202.31, 7.67, 5.82, INK, None, 1.15), 206.01, 206.27),
        (218.18, 12, (30.19, 214.34, 12.96, 5.82, None, INK, 1.02), 218.18, 218.45),
        (230.35, 12, (30.06, 226.12, 10.32, 6.09, "#19a86b", None, 1.15), 230.09, 230.35),
        (242.26, 12, (30.06, 238.29, 13.23, 5.82, "#4fc3f7", None, 1.15), 241.99, 242.26)):
    st += T(line(lab_b, x0b, 29), PRE, 700, "시리즈 이름 — 고정 글")
    st += rbox(bx, by, bw_, bh_, fill, "시리즈 뱃지", radius=r, stroke=stroke, sw=0.75 if stroke else None)
    st += T(line(txt_b, 30, 48), PRE, 800 if txt_b == 241.99 else 700, "시리즈 뱃지 글 — 고정 글(뱃지 가운데)", align="center", w=round(bw_, 2))   # 「포켓북」 700 은 잉크 0.87 — 800(겹침 0.903)
    st += T(line(dsc_b, 48, 130), PRE, 500, "시리즈 설명 — 고정 글(불투명도 68%)", alpha=68)
st += pic_xref(174, 0, "UP_작은", "UP 그림(작은) — 원본 그림")
st += T(line(282.74, 100, 200), PAPER, 900, "SONG AHYOUNG — 고정 글")

# 책등
st += T(line(210.52, 0, 40, (0, 1)), PAPER, 900, "책등 EEGOEEGO — 고정 글(90° 돌림)", rotate=90)
logo = os.path.join(WORK, "책등_UP.svg")
pdfsvg.export(REF_PATH, 1, 210.75, 38.41, 2.45, 4.39, logo)
st += image(210.75, 38.41, 2.45, 4.39, logo, label="책등 UP 표시 — 원본 도형 그림")
E({"id": "logo", "x": 210.95, "y": 38.61, "w": 2.05, "h": 3.99, "color": WHITE, "see": WHITE, "pad": 0.4, "ctol": 30})
st += T(line(210.79, 40, 80, (0, 1)), PRE, 700, "책등 학교 · 시험 — 원고 자리 「표지제목」(90° 돌림)", slot_name="표지제목", temp="학교 학기 시험", rotate=90)
st += rbox(210.51, 81.13, 2.91, 9.79, WHITE, "책등 「문제집」 흰 뱃지", radius=1.4)
st += T(line(211.28, 80, 92, (0, 1)), PRE, 700, "책등 문제집 — 고정 글(90° 돌림)", rotate=90)
st += rbox(210.64, 94.22, 2.65, 9.52, None, "책등 권 번호 흰 테두리 뱃지", radius=1.27, stroke=WHITE, sw=0.75)
st += T(line(211.14, 92, 110, (0, 1)), PAPER, 900, "책등 권 번호 — 원고 자리 「권번호」(90° 돌림)", slot_name="권번호", temp="00", rotate=90)
st += T(line(210.59, 240, 297, (0, 1)), PAPER, 900, "책등 SONG AHYOUNG — 고정 글(90° 돌림 · 불투명도 90%)", rotate=90, alpha=90, on=BLUE)

# 앞표지
s_ = line(35.32, 214, 380)
st += T(s_, PRE, 900, "EEGOEEGO — 고정 글(Pretendard 900 · 잉크 높이로 크기)", size=ink_size(s_, PRE, 900))
st += T(line(19.21, 370, 420), PRE, 700, "학교 · 시험 — 원고 자리 「표지제목」(오른쪽 맞춤 — 원 끝에)", slot_name="표지제목", temp="학교 학기 시험", align="right", w=45)
st += rbox(377.06, 26.49, 16.93, 7.67, None, "「문제집」 테두리 뱃지", radius=1.38, stroke=INK, sw=0.75)
st += T(line(31.65, 370, 395), PRE, 700, "문제집 — 고정 글")
st += dot(396.25, 22.92, 14.82, BLUE, "권 번호 원")
st += T(line(32.97, 395, 420), PAPER, 900, "권 번호 — 원고 자리 「권번호」(원 가운데)", slot_name="권번호", temp="00", align="center", w=14.82)
st += pic_xref(174, 1, "UP_큰", "UP 그림 — 원본 그림", see="#2c79cc")   # 큰 그림은 「auto」 색이 명암 끝 색을 골라 아래로 3.9mm 더 잡았다(그림은 같은 파일 · 같은 자리) — 몸통 파랑으로 잰다
st += T(line(234.32, 280, 360), PRE, 600, "UPGRADE YOUR ENGLISH — 고정 글(가운데 · 불투명도 72%)", align="center", w=70, alpha=72)
st += T(line(239.88, 280, 360), PRE, 600, "ELEVATE YOUR FUTURE — 고정 글(가운데 · 불투명도 72%)", align="center", w=70, alpha=72)
s_ = line(265.01, 214, 420, (-1, 0))
st += T(s_, PRE, 900, "거꾸로 EEGOEEGO — 고정 글(Pretendard 900 · 180° 돌림 · 잉크 높이로 크기)", rotate=180, size=ink_size(s_, PRE, 900))
st += T(line(268.19, 214, 300), PAPER, 900, "SONG AHYOUNG — 고정 글")
st += done("표지", "p1.png")

st += put_content(CONTENT)
if os.environ.get("REGISTER") == "1":                                    # 관리 「표지」 폴더에 등록
    st += [S("관리에 등록 — 표지 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "cover"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 40
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]

json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 요소", len(ELEMS[1]))
