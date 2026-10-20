"""상일보카 — 4 표제어 · 첫 펼침면(견본 4 · 5쪽) · 5 표제어 · 본문 펼침면(견본 6 · 7쪽).
쪽 틀은 common.py(구간 공통). 단어 항목 = 한 줄기 글(흐름 자리 ENTRY) — 쪽마다 글상자 하나, 글 잇기로 이어 흐른다.

단어 항목 꼴(원본 4쪽): 왼쪽 칸(표제어 · 「예문」 같은 칸 이름)과 오른쪽 칸(뜻 · 예문 · 해석 · 풀이)이 줄을 맞춘다 —
인디자인 내어쓰기 + 탭: 오른쪽 칸 단락은 왼쪽 들여쓰기 25.24mm, 왼쪽 칸 글이 붙는 첫 단락(「… 첫」)만 첫 줄 −25.24mm 에 탭 25.24mm.
왼쪽 칸 글은 그 단락 첫머리에 붙는 자리(인라인, 뒤에 탭 · 문자 스타일). 품사 칩은 뜻 앞에 붙는 자리(엔 공백 · 문자 스타일 「품사 칩」).
있는 기능으로 안 되는 차이(허용 — 책에서 손보기): 번호 뒤 가로선이 번호 아래부터 시작(원본은 번호 뒤 7.5mm부터 — 단락 경계선 왼쪽 들여쓰기 칸 없음) ·
품사 칩 둥근 귀 · 칩 좌우 여백.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
from entries import entries
sys.path.insert(0, REPO)
from core.units import render as _render

ENTRY = "번호+표제어+품사+뜻 첫+뜻+칸 이름+예문 첫+예문+해석+유반의어 첫+풀이 첫"
IND = 25.24                                                             # 오른쪽 칸 들여쓰기 = 품사 칩 왼쪽 44.23 − 단 왼쪽 18.99
X0, W0, BOT = 18.99, 110.0, 197.0                                       # 글상자 — 단 왼쪽 · 폭(오른쪽 129) · 아래 끝(꼬리 위)
MMPT = 1 / MM                                                           # mm → pt


def fb(font, weight, size, lead_pt):
    """줄 상자 위 끝 → 첫 기준선(mm) — 크롬 줄 상자(반 행간 + 윗높이)"""
    m = _render.font_metrics(font, weight)
    s, L = size * MM, lead_pt * MM
    return (L - (m["asc"] + m["desc"]) * s) / 2 + m["asc"] * s


# 단락 스타일 — (서체, 굵기, 크기, 행간 mm, 색, 내어쓰기)
P = {"번호": (NOTO, 700, 6.0, 3.0, "#274f7e", False),
     "뜻 첫": (NOTO, 500, 7.0, 3.37, "#000000", True), "뜻": (NOTO, 500, 7.0, 3.37, "#000000", False),   # 뜻 줄 사이 3.37mm(6쪽 꺾인 줄)
     "예문 첫": (NOTO, 400, 6.0, 3.2, "#000000", True), "예문": (NOTO, 400, 6.0, 3.2, "#000000", False),
     "해석": (NOTO, 400, 6.0, 3.2, "#4d4d4d", False),
     "유반의어 첫": (NOTO, 400, 6.0, 2.7, "#4d4d4d", True), "풀이 첫": (NOTO, 400, 6.0, 2.7, "#000000", True)}
# 단락 앞 공백 — 원본 4쪽 기준선 사이(앞 단락 끝 줄 → 이 단락 첫 줄, mm): 그 앞에 오는 단락 스타일과 함께
GAP = {"뜻 첫": ("번호", 4.6), "뜻": ("뜻", 3.8), "예문 첫": ("뜻", 4.4), "해석": ("예문", 3.2), "예문": ("해석", 3.6),
       "유반의어 첫": ("해석", 4.2), "풀이 첫": ("해석", 4.2), "번호": ("풀이 첫", 6.0)}
CS = {"표제어": {"font": NOTO, "weight": 700, "size": 10.0, "color": "#000000"},
      "칸 이름": {"font": ELICE, "weight": 500, "size": 5.5, "color": "#999999"},
      "품사 칩": {"font": NOTO, "weight": 500, "size": 5.0, "color": "#274f7e", "bg": "#e3e5eb", "bg_band": 2.98, "bg_off": 0.6,
                "bshift": round(0.4 * MMPT, 2)},
      "강조": {"font": NOTO, "weight": 500, "color": "#f37875"},
      "뜻 번호": {"color": "#4383c4"},
      # 뜻 번호 앞 틈 = 원본 1.87mm(28곳 모두) — 보통 낱말 틈 0.64mm 보다 1.23mm(7pt 엔 공백) 넓다 → 그 공백에 자간 +500
      "뜻 사이": {"track": 500}}


def styles():
    st = []
    for n, props in CS.items():
        st += need_cstyle(n, props)
    for n, (f, w, s, L, c, hang) in P.items():
        prev, d = GAP[n]
        pf, pw, ps, pL = P[prev][:4]
        sb = round(d - (pL - fb(pf, pw, ps, pL * MMPT)) - fb(f, w, s, L * MMPT), 2)
        v = {"font": f, "weight": w, "size": s, "leading": round(L * MMPT, 2), "color": c, "space_before": max(sb, 0)}
        if n != "번호":
            v["indent"] = IND
        if hang:
            v.update(indent_first=-IND, tabs=[{"at": IND}])
        if n != "풀이 첫":                                               # 단어 하나는 한 쪽에 — 다음 단락과 함께 유지(인디자인 분리 금지 옵션), 끝 단락(영영풀이)만 빼고
            v["keep_next"] = True
        v["keep_together"] = True                                        # 단락 분리 금지(모든 행) — 다음 단락과 함께와 이어 단어 하나가 통째로 다음 쪽으로
        if n == "번호":                                                  # 번호 줄 가로선 — 단락 아래 경계선(기준선 위 0.18mm, 단 너비)
            v["rule_below"] = {"w": round(0.1 * MMPT, 3), "color": "#274f7e", "offset": -0.18}
        st += need_pstyle(n, v)
    return st


def story_frame(pno, head, lead_first):
    """쪽 글상자 — 첫 단락(번호)의 첫 기준선이 원본 첫 번호 기준선에 오게. head = 이 이야기의 첫 상자(자리 · 스타일 · 새 이야기)"""
    sp = spans(pno)
    first = min((s for s in sp if s["size"] == 6.0 and s["color"] == "#274f7e" and s["x"] < 21 and 15 < s["base"] < 200), key=lambda s: s["base"])
    f, w, s, L = P["번호"][:4]
    top = round(top_of(first["base"], s, f, w, L * MMPT), 2)
    st = text(X0, top, W0, round(BOT - top, 2), "0000\n표제어\t뜻 — 단어 항목이 이 글상자로 흘러 들어온다", s, P["번호"][4], font=f, weight=w,
              leading=round(L * MMPT, 2), label="단어 항목 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기",
              first=(f, w, s, round(L * MMPT, 2)), auto="")
    if head:
        st += slot(ENTRY, label="자리 — 단어 항목(원고 차례대로 한 줄기)")
        for nm in ENTRY.split("+"):
            if nm in P:
                st.append(slot_style(nm, nm, 450))
        st += [S("왼쪽 칸 글 · 품사 — 뒤 단락 첫머리에 붙는다", 900)]
        st += slot_inline("표제어", "표제어", "\t") + slot_inline("품사", "품사 칩", " ") + slot_inline("칸 이름", "칸 이름", "\t")
        # 뜻 번호 앞 공백을 먼저(GREP 차례) — 번호를 먼저 감싸면 「공백 + 번호」 앞보기가 안 맞는다
        st += grep(0, r" (?=\d{1,2}\. )", "뜻 사이", label="GREP 스타일 — 뜻 번호 앞 공백 넓게(자간)")
        st += grep(1, r"(?<![\d.])\d{1,2}\.(?= )", "뜻 번호", label="GREP 스타일 — 뜻 번호(1. 2.) 파랑")
        st += story_pick(ENTRY, True)
    else:
        st += story_pick(ENTRY, False)
    body = [s for s in sp if top < s["base"] < BOT and s["x"] < 135]
    Eslot(body, "#000000", label="단어 항목")
    return st


def Eslot(sps, color, label=""):
    """원고 칸 전체를 원고 요소 하나로 — 원고는 「들어갔나」만 본다(절차 합격 기준)"""
    x0, x1 = min(s["x"] for s in sps), max(s["x1"] for s in sps)
    y0, y1 = min(s["base"] - s["size"] * MM * 0.95 for s in sps), max(s["base"] + s["size"] * MM * 0.3 for s in sps)
    E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
       "color": color, "see": color, "ctol": 40, "pad": 1.0, "search": 1.0, "text": label, "size": sps[0]["size"], "원고": True})


def pyo_first(lp=4):
    st = pg_new(lp, f"④ 표제어 · 첫 펼침면 — 원본 {lp}쪽(왼쪽)", name="표제어 · 첫 펼침면")
    st += styles()
    st += frame_first_left(lp)
    st += story_frame(lp, True, None)
    st += done("표제어 · 첫 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"④ 표제어 · 첫 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += story_frame(lp + 1, False, None)
    st += done("표제어 · 첫 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(ENTRY, []).extend(entries(REF_PATH, lp) + entries(REF_PATH, lp + 1))
    return st


def pyo_body(lp=6):
    st = pg_new(lp, f"⑤ 표제어 · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="표제어 · 본문 펼침면")
    st += styles()
    st += frame_body_left(lp)
    st += story_frame(lp, ENTRY not in CONTENT, None)
    st += done("표제어 · 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑤ 표제어 · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_body_right(lp + 1)
    st += story_frame(lp + 1, False, None)
    st += done("표제어 · 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(ENTRY, []).extend(entries(REF_PATH, lp) + entries(REF_PATH, lp + 1))
    return st


FACES = {4: (pyo_first,), 5: (pyo_body,)}
