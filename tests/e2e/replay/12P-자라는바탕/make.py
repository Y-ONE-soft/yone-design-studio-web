"""단위 12P 자라는 바탕 — 단위 12(C영작배열) 42쪽 한 면을 다시, 연보라 바탕을 따로 그린 면 대신 「배열 글상자의 칠·모서리 + 자동 크기(높이와 너비)」로.
전부 마우스·키보드, 블록 없이 빈 데이터에서. 글 언어는 글상자 패널 「언어」에서 고른다(한국어 — 공백·문장부호가 Noto CJK 한국어 꼴).

원본(인디자인)의 배열 바탕 = 텍스트 프레임 칠(#e4dfed, 모서리 1.0mm) + 자동 크기 조정(높이와 너비, 최대 폭 166mm):
  바탕 왼쪽 → 글 3.00mm · 위 → 첫 기준선 5.64mm · 끝 기준선 → 아래 3.36mm, 한 줄 문항은 글 폭만큼 줄고 두 줄 문항은 166mm.
→ 글상자 안쪽 여백(위 오른쪽 아래 왼쪽)을 원본에서 재서 치고, 바탕은 브라우저가 실제로 그린 글 크기를 따른다.
끝에 원본과 길이가 다른 배열 원고(짧은 것·긴 것)를 넣어 바탕이 따라 바뀌는 것을 보이고, 마지막에 원본 원고로 되돌려 비교한다.

값을 읽는 함수(원본 PDF 글 조각·도형·자간·행간)는 단위 12 대본의 것을 그대로 쓴다 — 42·43쪽 둘로 재야 하는 값(해석 행간은 43쪽 문항 08)이 있어 12 폴더 기준으로 읽는다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
U12 = os.path.join(os.path.dirname(HERE), "12-C영작배열", "make.py")
_src = open(U12, encoding="utf-8").read().split("# ── 42쪽 (왼쪽 면)")[0]
G = {"__file__": U12, "__name__": "u12"}
exec(compile(_src, U12, "exec"), G)                                       # 원본 읽기·그리기 함수 (ELEMS·CONTENT 도 거기 것)
globals().update({k: v for k, v in G.items() if not k.startswith("__") and k not in ("HERE", "PAGES")})   # HERE 는 이 폴더 그대로
from mkpage import _color                                                 # noqa — 색 칸: 「직접 고르기…」 → 색 번호

P0 = 42
CONTENT = {"지문이름": [], "문장번호": [], "해석": [], "배열": []}
G["CONTENT"] = CONTENT                                                    # label_of 가 이 원고에 넣는다


def item2(pg, pno, k, it):
    """문항 — 단위 12 의 item 과 같고, 연보라 면 + 배열 글상자 대신 「바탕 있는 배열 글상자」 하나"""
    st = [S(f"문항 {it['no']['t']} — 번호 · 해석 · 바탕 있는 배열 글상자 · 쓰기 선", 1300)]
    n = it["no"]
    first = k == 0
    CONTENT["문장번호"].append(n["t"])
    st += T(pg, f"no{k}", n["x"], n["base"], n["t"], n["size"], n["color"], LOTTE, 400, ink_box(n), N_TRACK, search=0.6, pad=0.6,
            temp="00.", label="문장 번호 자리" if first else None)
    st += slot("문장번호")
    right = RIGHT[pno]
    kor = it["kor"]
    kt = "".join(s["raw"] for s in kor)
    CONTENT["해석"].append(kt)
    kx = round(kor[0]["x0"], 2)
    for j, s in enumerate(kor):
        ELEMS[pg].append({"id": f"kor{k}" + (f"-{j}" if j else ""), **dict(zip("xywh", ink_box(s))), "color": "#231f20", "see": "#231f20",
                          "ctol": 40, "pad": 0.6, "search": 0.6, "text": s["t"], "size": 8.5})
    kw = round(right - kx + K_TRACK / 1000 * 8.5 * MM, 2)
    ky = top_of(kor[0]["base"], 8.5, NOTO, 400, K_LEAD)
    st += text(kx, round(ky, 2), kw, max(14, round(len(kor) * K_LEAD * MM + 3, 1)), temp_of(KTEMP, len(kt)), 8.5, "#231f20",
               label="해석 글상자 — 임시 글" if first else None, leading=K_LEAD, align="justify", font=NOTO, track=K_TRACK or None)
    st.append({"pick": {"at": '#side select[data-a="lang"]', "value": "ko"}, "wait": 550})   # 글 언어 — 한국어
    st += slot("해석")
    st += justify()                                                      # 균등 배치 — 이 출판사 책: 낱말 100·133%, 자간 −8·250‰ (인디자인 원본 실측)
    # 배열 — 글상자 자리 = 원본 바탕 자리. 안쪽 여백 = 원본 바탕 ↔ 글(기준선 공식 · 글 시작 · 양끝 줄 끝)
    bx = it["box"]
    x0, y0, bw = [round(v, 2) for v in bx["mm"][:3]]
    c0 = bx["items"][0]
    rad = round(abs(c0[1].x - c0[4].x) * MM, 2)
    ELEMS[pg].append({"id": f"lav{k}", "x": bx["mm"][0], "y": bx["mm"][1], "w": bx["mm"][2], "h": bx["mm"][3], "color": "#e4dfed", "see": "#e4dfed",
                      "pad": 0.6, "ctol": 8})
    chk = it["chk"]
    ct = "".join(s["raw"] for s in chk)
    CONTENT["배열"].append(ct)
    cx = round(min(s["x0"] for s in chk), 2)
    for j, s in enumerate(chk):
        ELEMS[pg].append({"id": f"chk{k}" + (f"-{j}" if j else ""), **dict(zip("xywh", ink_box(s))), "color": "#231f20", "see": "#231f20",
                          "ctol": 40, "pad": 0.6, "search": 0.6, "text": s["t"], "size": 8.5})
    cw = right - cx + C_TRACK / 1000 * 8.5 * MM                           # 양끝 줄의 글 폭(단위 12 와 같은 식)
    ins = [round(top_of(chk[0]["base"], 8.5, NOTO, 500, C_LEAD) - y0, 2),  # 위 = 첫 줄 상자 위 끝 - 바탕 위
           round(x0 + MAXW - (cx + cw), 2),                                # 오른쪽 = 최대 폭 바탕 오른쪽 - 양끝 줄 끝
           0, round(cx - x0, 2)]                                           # 왼쪽 = 글 시작 - 바탕 왼쪽
    ins[2] = round(bx["mm"][3] - ins[0] - len(chk) * C_LEAD * MM, 2)       # 아래 = 바탕 높이 - 위 - 줄 수 × 행간
    st += text(x0, y0, MAXW, 14, temp_of(CTEMP, len(ct)), 8.5, "#231f20",
               label="배열 글상자 — 임시 글" if first else None, leading=C_LEAD, align="justify", font=NOTO, track=C_TRACK or None, weight=500)
    st.append({"pick": {"at": '#side select[data-a="lang"]', "value": "ko"}, "wait": 550})
    st += slot("배열")
    st += justify(word_min=JC_WORD_MIN, letter_min=-8 if JC_LETTER_MIN is None else JC_LETTER_MIN)   # 균등 배치 — 원본 잰 값(낱말 최소 100·자간 최소 0) + 늘림 133%·250‰
    st += ([S("상자 칠 · 모서리 · 안쪽 여백 · 자동 크기(높이와 너비) — 바탕이 글을 따라간다", 1800)] if first else [])
    st += _color("frame.fill", "#e4dfed")
    st.append(F('#side input[data-a="frame.radius"]', rad, 600))
    st.append(F('#side input[data-a="inset4"]', " ".join(f"{v:g}" for v in ins), 700))
    st.append({"pick": {"at": '#side select[data-a="auto_size"]', "value": "both"}, "wait": 900})
    INSETS.append(ins)
    a = it["arrow"]
    st += T(pg, f"arr{k}", a["x"], a["base"], a["t"], a["size"], a["color"], MYRIAD, 400, ink_box(a), 0, search=0.6, pad=0.6, h=12)
    for j, d in enumerate(it["lines"]):
        st += rule(pg, f"ln{k}-{j}", round(d["mm"][0], 2), round(d["mm"][1], 3), round(d["mm"][2], 2), hexc(d["color"]), round(d["width"] * MM, 3))
    return st


MAXW = round(max(it["box"]["mm"][2] for it in ITEMS[P0]), 2)                         # 바탕 최대 폭 = 두 줄 문항의 바탕 폭(166mm)
INSETS = []
S0 = spans(P0)
st = open_doc("스텝바이스텝 워크북 C2 영작배열 — 자라는 바탕 (A4)")
st += expect_pages(1)
st += [S("42쪽 — C2 영작 배열 · 배열 바탕은 글상자의 칠", 1500)]
st += [S("머리 — 크림 띠 · 선 · 베이지 막대", 1500)]
st += B(1, "band", -3, -3, 213, 26.5, "#f9f7ed")
st += rule(1, "rule", -3, 23.5, 216)
st += B(1, "bar", 11.2, -3, 2.2, 26.6, BEIGE)
s_step = next(s for s in S0 if s["t"] == "STEP")
s_build = next(s for s in S0 if s["t"] == "BUILD UP")
st += T(1, "t-step", s_step["x"], s_step["base"], "STEP 02", 8, BEIGE, NOTO, 400, (20.0, 3.83, 10.87, 8.06), 0, label="STEP 02 · BUILD UP")
st += grep(0, r"\d+", label="숫자만 굵게 — GREP 스타일")
st += T(1, "t-frame", s_build["x"], s_build["base"], "BUILD UP", 8, "#b4aa9a", NOTO, 700, ink_box(s_build), trk(s_build, NOTO, 700))
s_code = next(s for s in S0 if s["font"].startswith("TTMamablockB"))
st += T(1, "t-code", s_code["x"], s_code["base"], s_code["t"], 25, BEIGE, MAMA, 400, ink_box(s_code), trk(s_code, MAMA, 400), label="제목 — 코드 · 이름")
s_title = next(s for s in S0 if s["font"].startswith("GmarketSans"))
st += T(1, "t-title", round(s_title["x"], 2), s_title["base"], s_title["t"], 13, "#231f20", GM, 500, ink_box(s_title), trk(s_title, GM, 500))
st += [S("단계 점 셋 — 지금 단계(2)가 찬 원", 1400)]
st += C(1, "d1", 55.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
st += rule(1, "dl1", 61.6, 15.76, 4.2)
st += C(1, "d2", 66.5, 13.06, 5.4, fill=BEIGE)
st += rule(1, "dl2", 72.6, 15.76, 4.2)
st += C(1, "d3", 77.5, 13.06, 5.4, stroke="#b4aa9a", sw=0.8)
for k, s in enumerate(sorted((s for s in S0 if s["font"] == "Montserrat-Bold" and s["size"] == 6.0), key=lambda s: s["x"])):
    st += T(1, f"n{k + 1}", s["x"], s["base"], s["t"], 6, s["color"], MS, 700, (round(s["x"], 2), 14.22, round(s["x1"] - s["x"], 2), 2.84), 0, search=0.6)
st += label_of(1, P0)
for k, it in enumerate(ITEMS[P0]):
    st += item2(1, P0, k, it)
st += folio(1, P0)
st += done("42쪽", "p1.png")

# 다른 길이의 배열 원고 — 바탕이 따라 줄고 자란다(시연). 비교는 끝에 다시 넣는 원본 원고로
SHORT = dict(CONTENT, 배열=["a key / found", "on / was", "the door / opened", "kept / it", "to / we / went"])
LONG = dict(CONTENT, 배열=[c.strip() + " / " + c.strip() for c in CONTENT["배열"]])
st += put_content(SHORT, "짧은 배열 원고를 넣는다 — 바탕이 글 폭만큼 준다")
st += [{"shot": "p1_short.png", "wait": 1500}]
st += put_content(LONG, "긴 배열 원고를 넣는다 — 바탕이 상자 폭까지 늘고 줄이 늘면 아래로 자란다")
st += [{"shot": "p1_long.png", "wait": 1500}]
st += put_content(CONTENT, "원본 원고로 되돌린다 — 이 상태를 원본과 비교")
st += [{"shot": "p1_content.png", "wait": 1200}]

ELEMS = {1: ELEMS[1]}
json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("12P 단계", len(st), "· 잴 요소", len(ELEMS[1]))
print("  배열 안쪽 여백(위 오른쪽 아래 왼쪽) 문항별", INSETS, "· 최대 폭", MAXW)
