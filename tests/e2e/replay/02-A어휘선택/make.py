"""단위 02 A어휘선택 — 원본 d1 reference.pdf 4·5쪽을 A4 한 문서 두 쪽으로. 전부 마우스·키보드, 블록 없이 그리기만.

값은 모두 원본 PDF 에서 뽑는다 — 글 조각(서체·크기·색·기준선)과 도형 좌표. 지문 글도 PDF 에서 그대로 읽어 친다.
글상자 위 끝 = 원본 기준선 - (반 행간 + 서체 윗높이) — 서체 파일의 hhea 값으로 계산(측정 보정 없이 첫 판에 맞추려고).
그래도 남는 차이는 보정.json(측정해서 채움)으로. 이 파일은 steps.json(녹화기 대본)과 elems.json(측정할 요소 목록)을 쓴다.
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf

REF = os.path.join(REPO, "catalog/workbook/designs/d1/reference.pdf")
REFDOC = pymupdf.open(REF)
FIX = json.load(open(os.path.join(HERE, "보정.json"))) if os.path.exists(os.path.join(HERE, "보정.json")) else {}
ELEMS = {1: [], 2: []}
PAGES = json.load(open(os.path.join(HERE, "상태.json")))["pages"]
MM = 25.4 / 72
NOTO, MS, EL, YD, MAMA = "Noto Sans CJK KR", "Montserrat", "Elice DX Neolli OTF", "Yeongdo OTF", "NUXZQS+TTMamablockB"
GM = "Gmarket Sans TTF"        # 「Gmarket Sans」+500 은 Chrome 이 Bold 를 고르고 한 번 더 굵힌다 — TTF 집은 500 이 진짜 Medium


def T(pg, id, x, base, s, size, color, family, weight, bbox, leading=None, label=None, search=1.5, rotate=None, at=None, w=None, align=None):
    """원본 글 하나. x = 글자 시작, base = 기준선, bbox = 원본 글자 상자(잴 자리). 자간은 원본 폭에서 계산한다."""
    f = FIX.get(id if pg == 1 else f"p{PAGES[pg - 1]}:{id}", {})   # 보정 이름표 = 원본 쪽 번호 (측정이 그렇게 쓴다)
    _, _, adv = face(family, weight)
    nat = adv(s) * size * MM
    length = bbox[3] if rotate else bbox[2]                                 # 돌린 글은 원본 상자의 세로가 글 길이
    if rotate:                                                              # 돌린 글은 글자 위치가 세로 — 상자 길이로
        track = round((length - nat) / max(len(s), 1) / (size * MM) * 1000) if len(s) > 1 else 0
    else:                                                                   # 원본 글자 위치 - 브라우저(커닝·대체 글자 포함) 거리
        track = track_from(REFDOC[PAGES[pg - 1] - 1], bbox, s, family, weight, size)
    track = track if abs(track) > 8 else 0
    ELEMS[pg].append({"id": id, "x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3], "color": color, "see": color,
                      "ctol": 30, "search": search, "text": s, "size": size})
    bw = w or round(nat * 1.3 + size * 0.5 + max(track, 0) * len(s) * size * MM / 1000, 1)
    bh = round((leading or size * 1.45) * MM + 0.4, 1)
    if at:                                                                  # 돌린 글 — 상자 가운데를 원본 글 가운데에
        cx, cy = at
        bx, by = cx - bw / 2, cy - bh / 2
    else:
        bx, by = x, top_of(base, size, family, weight, leading)
    st = text(round(bx - f.get("dx", 0), 2), round(by - f.get("dy", 0), 2), bw, bh, s, size, color, label=label,
              font=family, weight=weight if weight != 400 else None, track=round(track - f.get("dtr", 0)) or None, leading=leading, align=align)
    if rotate:
        st.append(F('#side input[data-a="rotate"]', rotate, 600))
    return st


def B(pg, id, x, y, w, h, fill, label=None, measure=True, pad=0.6):
    if measure:
        ELEMS[pg].append({"id": id, "x": x, "y": y, "w": w, "h": h, "color": fill, "see": fill, "pad": pad, "ctol": 30})
    return box(x, y, w, h, fill, label=label)


def C(pg, id, x, y, d, fill=None, stroke=None, sw=None):
    ELEMS[pg].append({"id": id, "x": x, "y": y, "w": d, "h": d, "color": fill or stroke, "see": fill or stroke, "pad": 0.6, "ctol": 30})
    return ellipse(x, y, d, fill=fill, stroke=stroke, sw=sw)


def passages(pno):
    """원본 쪽의 지문(8.5pt) — 기준선 간격이 크게 벌어지는 곳에서 나눈다. [(x, 첫 기준선, 마지막 기준선, 글, (위, 아래), 오른쪽 끝)]
    원본 줄 끝마다 줄 나눔(U+2028 = Shift+Enter) — 인디자인 단락 컴포저가 고른 줄 끝을 그대로 (편집기는 한 줄씩 채운다).
    마지막 줄이 오른쪽 끝까지 꽉 찼으면(인디자인이 공백을 줄여 넣은 줄) 끝에도 줄 나눔 — 그 줄도 양끝을 맞춘다."""
    p = pymupdf.open(REF)[pno - 1]
    ox, oy = p.trimbox.x0, p.trimbox.y0
    rows = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if round(s["size"], 1) == 8.5]
            if sp:
                ch = [c for s in sp for c in s["chars"]]
                ink = [c for c in ch if c["c"].strip()]
                rows.append(((sp[0]["origin"][1] - oy) * MM, (ink[0]["bbox"][0] - ox) * MM, "".join(c["c"] for c in ch),
                             (sp[0]["bbox"][1] - oy) * MM, (sp[0]["bbox"][3] - oy) * MM, (ink[-1]["bbox"][2] - ox) * MM))
    out, cur = [], []
    for r in rows:
        if cur and r[0] - cur[-1][0] > 10:
            out.append(cur); cur = []
        cur.append(r)
    out.append(cur)
    res = []
    for g in out:
        right = max(r[5] for r in g)
        txt = "\u2028".join(r[2].rstrip(" ") for r in g) + ("\u2028" if g[-1][5] > right - 0.05 else "")
        res.append((g[0][1], g[0][0], g[-1][0], txt, (g[0][3], g[-1][4]), right))
    return res


TRACK = -40          # 자간: 원본 글자 간격 - 서체 폭 (공백 제외 중앙값, scratch track.py)
WORD_MIN = -60       # 양끝 줄 낱말 간격 최소 — 원본 줄이 다 들어가는 값(인디자인이 공백을 줄여 넣은 줄)


def P(pg, id, x, base, txt, lines, yb, right, label):
    """지문 한 덩어리 — 글상자 하나에 원본 글 그대로, 양끝맞춤 · 행간 22pt · 자간 -40 · 줄 나눔, GREP 스타일로 [ ⓐ … / ⓑ … ] 만 굵은 파랑.
    글상자 폭 = 원본 글자 끝 - 시작 - 끝 글자 뒤 자간(Chrome 은 줄 끝 글자 뒤에도 자간을 둔다)"""
    f = FIX.get(id if pg == 1 else f"p{PAGES[pg - 1]}:{id}", {})   # 보정 이름표 = 원본 쪽 번호 (측정이 그렇게 쓴다)
    w = round(right - x + TRACK / 1000 * 8.5 * MM, 2)
    for k, col in (("", "#231f20"), ("-b", "#00559f")):
        ELEMS[pg].append({"id": id + k, "x": x, "y": yb[0], "w": round(right - x, 2), "h": yb[1] - yb[0], "color": col, "see": col,
                          "ctol": 40, "search": 1.0, "text": txt[:30], "size": 8.5,
                          "shape_iou": 0.80})          # 문단은 양끝맞춤에서 단어가 0.2mm 안팎 다르게 놓인다 — 겹침 기준을 낮춘다
    y = top_of(base, 8.5, NOTO, 400, 22)
    st = text(round(x - f.get("dx", 0), 2), round(y - f.get("dy", 0), 2), w, round(lines * 22 * MM, 1), txt, 8.5, "#231f20",
              label=label, leading=22, align="justify", font=NOTO, track=TRACK)
    st.append(F('#side input[data-a="word_min"]', WORD_MIN, 600))
    st += grep(0, r"\[[^\]]*\]", "#00559f", label="GREP 스타일 — 대괄호 [ ] 안은 굵은 파랑")
    return st


def rule(pg, id, x, y, w, color="#b4aa9a", sw=0.21):
    """원본 선(획 굵기 sw mm, 가운데 y) → 얇은 면"""
    return B(pg, id, x, round(y - sw / 2, 3), w, sw, color, pad=0.15)        # 잴 때 옆 원 테두리(같은 색)가 섞이지 않게 좁게


def header_left(pg, code, title, title_x):
    st = [S("머리 — 크림 띠 · 선 · 파란 막대", 1500)]
    st += B(pg, "band", -3, -3, 213, 26.5, "#f9f7ed")
    st += rule(pg, "rule", -3, 23.5, 216)
    st += B(pg, "bar", 11.2, -3, 2.2, 26.6, "#77a1c4")
    st += T(pg, "t-step", 20.0, 8.93, "STEP 01", 8, "#77a1c4", NOTO, 400, (20.0, 3.83, 10.87, 8.06), label="STEP 01 · FRAME")
    st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
    st += T(pg, "t-frame", 32.35, 8.93, "FRAME", 8, "#b4aa9a", NOTO, 700, (32.35, 3.84, 9.62, 8.05))
    st += T(pg, "t-code", 20.0, 19.47, code, 25, "#77a1c4", MAMA, 400, (20.0, 12.18, 7.98, 9.78), label="제목 — 코드 · 이름")
    st += T(pg, "t-title", title_x, 17.58, title, 13, "#231f20", GM, 500, (title_x, 13.70, 21.16 - (title_x - 29.45), 5.44))
    st += [S("단계 점 셋 — 원 · 선 · 숫자", 1400)]
    st += C(pg, "d1", 55.5, 13.06, 5.4, fill="#77a1c4")
    st += rule(pg, "dl1", 61.6, 15.76, 4.2)
    st += C(pg, "d2", 66.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    st += rule(pg, "dl2", 72.6, 15.76, 4.2)
    st += C(pg, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.79)
    for k, (nx, nw, col) in enumerate(((57.79, 0.83, "#ffffff"), (68.58, 1.25, "#b4aa9a"), (79.57, 1.25, "#b4aa9a"))):
        st += T(pg, f"n{k + 1}", nx, 16.50, str(k + 1), 6, col, MS, 700, (nx, 14.22, nw, 2.84), search=0.6)
    return st


# ── 4쪽 (왼쪽 면) ──────────────────────────────────────────
_, _, adv_gm = face(GM, 500)
_TT = " 어휘 선택 1"                                                         # 원본 조각(공백으로 시작) — 폭 21.16mm
_tr = (21.16 - adv_gm(_TT) * 13 * MM) / len(_TT)                            # 글자마다 자간(mm) — 앞 공백에도 들어간다
TITLE_X = round(29.45 + adv_gm(" ") * 13 * MM + _tr, 2)                   # 글자는 공백(자간 포함) 다음부터
st = open_doc("스텝바이스텝 워크북 A1 (A4)")
st += expect_pages(1)
st += [S("① 4쪽 — A1 어휘 선택 1", 1500)]
st += header_left(1, "A1", "어휘 선택 1", TITLE_X)
P4 = passages(4)
NO4 = ((20.0, 35.90, 26.04, 3.40), (20.0, 157.90, 148.04, 3.84))          # 원본 지문 번호 — x · 기준선 · 상자 위 · 폭
for k, (x, b0, b1, txt, yb, right) in enumerate(P4):
    no = f"0{k + 1}"
    nx, nb, ny, nw = NO4[k]
    st += T(1, f"no{k + 1}", nx, nb, no, 12, "#af9d81", YD, 400, (nx, nb - 3.2, nw, 3.6), search=0.6, label=f"지문 {no}")   # 잴 칸은 숫자 높이만 — 아래 지문 글 가장자리가 섞이지 않게
    st += P(1, f"p{k + 1}", x, b0, txt, round((b1 - b0) / (22 * MM)) + 1, yb, right, f"지문 {no} 본문 — 원본 글 그대로")
st += [S("꼬리 — 쪽번호", 1200)]
st += T(1, "f-no", 15.23, 285.53, "4", 6, "#3b4247", EL, 700, (15.23, 283.62, 1.52, 2.62), search=0.6)
st += T(1, "f-t", 20.9, 285.53, "STEP BY STEP", 6, "#231f20", EL, 700, (20.9, 283.62, 17.68, 2.62))
st += done("4쪽", "p1.png")

# ── 5쪽 (오른쪽 면) ────────────────────────────────────────
st += add_page("② 5쪽 — 새 쪽")
st += [S("머리 — 크림 띠 · 선 · 꼬리표", 1500)]
st += B(2, "band", -3, -3, 216, 26.5, "#f9f7ed")
st += rule(2, "rule", -3, 23.5, 216)
ELEMS[2].append({"id": "tag", "x": 176.6, "y": 18.6, "w": 33.4, "h": 4.79, "color": "#bdafa2"})
st += shape(176.6, 18.6, 36.5, 4.79, "#bdafa2", d="M0.1512 0 L1 0 L1 1 L0 1 Z", label="꼬리표 — 도형, 원본 꼭짓점 그대로")
st += T(2, "tag-t", 187.05, 21.84, "STEP BY STEP", 6, "#ffffff", MS, 700, (187.05, 19.56, 15.43, 2.84), search=0.6)
st += T(2, "t-code", 188.04, 15.99, "A1", 36, "#77a1c4", MS, 500, (188.04, 2.62, 13.46, 16.71), label="큰 코드 A1")
st += [S("오른쪽 탭 셋 — 면 · 돌린 글", 1500)]
st += B(2, "tab1", 201.5, 60, 11.5, 26, "#77a1c4")
st += B(2, "tab2", 201.5, 90, 11.5, 26, "#f9efda")
st += B(2, "tab3", 201.5, 120, 11.5, 26, "#f8e1da")
for k, (s, y, h, col) in enumerate((("STEP 01", 68.93, 8.13, "#ffffff"), ("02", 101.64, 2.72, "#cba56f"), ("03", 131.64, 2.72, "#bc736c"))):
    st += T(2, f"tab{k + 1}-t", 204.54, 0, s, 6.5, col, MS, 700, (204.54, y, 3.08, h), search=0.8, rotate=-90,
            at=(204.54 + 3.08 / 2, y + h / 2), w=14, align="center")     # 원본은 아래에서 위로 읽는 글 · 돌려도 가운데가 남게 가운데 정렬
P5 = passages(5)
NO5 = ((22.0, 35.90, 26.04, 4.03), (22.02, 157.90, 148.04, 4.07))
for k, (x, b0, b1, txt, yb, right) in enumerate(P5):
    no = f"0{k + 3}"
    nx, nb, ny, nw = NO5[k]
    st += T(2, f"no{k + 3}", nx, nb, no, 12, "#af9d81", YD, 400, (nx, nb - 3.2, nw, 3.6), search=0.6, label=f"지문 {no}")
    st += P(2, f"p{k + 3}", round(x, 2), b0, txt, round((b1 - b0) / (22 * MM)) + 1, yb, right, f"지문 {no} 본문 — 원본 글 그대로")
st += [S("꼬리 — 쪽번호", 1200)]
st += T(2, "f-t", 179.16, 285.53, "STEP01", 6, "#231f20", EL, 700, (179.16, 283.62, 9.59, 2.62))
st += T(2, "f-no", 193.47, 285.53, "5", 6, "#3b4247", EL, 700, (193.47, 283.62, 1.55, 2.62), search=0.6)
st += done("5쪽", "p2.png")

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("02 단계", len(st), "· 잴 요소", sum(len(v) for v in ELEMS.values()))
for x, b0, b1, txt, yb, right in P4 + P5:
    print(f"  지문 x={x:.2f}~{right:.2f} 기준선 {b0:.2f}~{b1:.2f} · {len(txt)}자 · 줄 나눔 {txt.count(chr(0x2028))} · 끝 꽉 참 {txt.endswith(chr(0x2028))}")
