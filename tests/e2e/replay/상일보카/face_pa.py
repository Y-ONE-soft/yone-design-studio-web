"""상일보카 — 6 파생어 & 연관어휘 · 첫 펼침면(견본 94 · 95쪽) · 7 파생어 & 연관어휘 · 본문 펼침면(견본 96 · 97쪽).
쪽 틀은 common.py(구간 공통 — 청록). 낱말 항목 = 한 줄기 글(흐름 자리 ENTRY) — 표제어 면과 같은 짜임(내어쓰기 + 탭, face_pyo.py).

번호 줄 = 번호(인라인, 탭) + 뿌리 낱말(오른쪽 탭, 회색 5pt) · 단락 아래 경계선. 번호 아래 낱말 여럿 — 낱말(8.4pt) · 구(6.6pt)는 뜻 첫 단락 앞에 붙는다.
둘째 낱말부터는 「다음 뜻 첫」(낱말 사이가 넓다). 오른쪽 칸 들여쓰기 34.0mm(53.0 − 19.0).
있는 기능으로 안 되는 차이(허용 — 책에서 손보기): 번호 줄 선이 번호 아래 · 뿌리 낱말 밑까지 이어짐(원본은 번호 뒤 7.5mm ~ 뿌리 앞) · 품사 칩 귀 · 여백.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
from entries import derived
from face_pyo import fb, MMPT, X0, W0, BOT, Eslot

ENTRY = "번호+뿌리+낱말+구+품사+뜻 첫+다음 뜻 첫+뜻+칸 이름+예문 첫+예문+해석+유반의어 첫+풀이 첫"
IND = 34.0
TEAL, NUMC = "#2c5d72", "#4694b6"
PF = "파생·"                                                            # 스타일 이름 앞붙이 — 한 책에 표제어 면 스타일과 같이 있다

P = {"번호": (NOTO, 500, 5.0, 3.0, "#999999", False),                    # 번호 줄 = 뿌리 낱말 단락(번호는 앞에 붙는 자리)
     "뜻 첫": (NOTO, 500, 7.0, 3.37, "#000000", True), "다음 뜻 첫": (NOTO, 500, 7.0, 3.37, "#000000", True),
     "뜻": (NOTO, 500, 7.0, 3.37, "#000000", False),
     "예문 첫": (NOTO, 400, 6.0, 3.5, "#000000", True), "예문": (NOTO, 400, 6.0, 3.5, "#000000", False),
     "해석": (NOTO, 400, 6.0, 3.5, "#4d4d4d", False),
     "유반의어 첫": (NOTO, 400, 6.0, 2.7, "#4d4d4d", True), "풀이 첫": (NOTO, 400, 6.0, 2.7, "#000000", True)}
# 단락 앞 공백 — 원본 94쪽 기준선 사이(mm)
GAP = {"뜻 첫": ("번호", 4.57), "다음 뜻 첫": ("뜻", 7.87), "뜻": ("뜻", 3.4), "예문 첫": ("뜻", 4.02), "해석": ("예문", 3.51),
       "예문": ("해석", 3.6), "유반의어 첫": ("뜻", 4.03), "풀이 첫": ("해석", 4.2), "번호": ("뜻", 6.15)}
CS = {"파생 번호": {"font": NOTO, "weight": 700, "size": 6.0, "color": TEAL},
      "파생 낱말": {"font": NOTO, "weight": 700, "size": 8.4, "color": "#000000", "bshift": round(0.54 * MMPT, 2)},
      "파생 구": {"font": NOTO, "weight": 700, "size": 6.6, "color": "#000000", "bshift": round(1.1 * MMPT, 2)},
      "칸 이름": {"font": ELICE, "weight": 500, "size": 5.5, "color": "#999999"},
      "파생 품사 칩": {"font": NOTO, "weight": 500, "size": 5.0, "color": TEAL, "bg": "#e3e5eb", "bg_band": 2.94, "bg_off": 0.6,
                    "bshift": round(0.4 * MMPT, 2)},
      "강조": {"font": NOTO, "weight": 500, "color": "#f37875"},
      "파생 뜻 번호": {"color": NUMC},
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
            if n != "풀이 첫":
                v["keep_next"] = True
        if hang:
            v.update(indent_first=-IND, tabs=[{"at": IND}])
        if n == "번호":                                                  # 뿌리 낱말 = 오른쪽 탭(단 끝) · 번호 줄 선 = 아래 경계선(기준선 위 0.23mm)
            v.update(tabs=[{"at": W0, "align": "right"}], keep_next=True, rule_below={"w": round(0.1 * MMPT, 3), "color": TEAL, "offset": -0.23})
        st += need_pstyle(PF + n, v)
    return st


def story_frame(pno, head):
    sp = spans(pno)
    first = min((s for s in sp if s["size"] == 6.0 and s["x"] < 21 and 15 < s["base"] < 200 and s["text"].isdecimal()), key=lambda s: s["base"])
    f, w, s, L = P["번호"][:4]
    top = round(top_of(first["base"], s, f, w, L * MMPT), 2)
    st = text(X0, top, W0, round(BOT - top, 2), "0000\t뿌리\n낱말\t뜻 — 낱말 항목이 이 글상자로 흘러 들어온다", s, P["번호"][4], font=f, weight=w,
              leading=round(L * MMPT, 2), label="낱말 항목 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기",
              first=(f, w, s, round(L * MMPT, 2)), auto="")
    if head:
        st += slot(ENTRY, label="자리 — 낱말 항목(원고 차례대로 한 줄기)")
        st.append(slot_style("뿌리", PF + "번호", 450))
        for nm in ENTRY.split("+"):
            if nm in P and nm != "번호":
                st.append(slot_style(nm, PF + nm, 450))
        st += [S("번호 · 낱말 · 구 · 칸 이름 · 품사 — 뒤 단락 첫머리에 붙는다", 900)]
        st += slot_inline("번호", "파생 번호", "\t") + slot_inline("낱말", "파생 낱말", "\t") + slot_inline("구", "파생 구", "\t")
        st += slot_inline("품사", "파생 품사 칩", " ") + slot_inline("칸 이름", "칸 이름", "\t")
        st += grep(0, r"(?<![\d.])\d{1,2}\.(?= )", "파생 뜻 번호", label="GREP 스타일 — 뜻 번호(1. 2.) 파랑")
        st += grep(1, r" (?=\d{1,2}\. )", "뜻 사이", label="GREP 스타일 — 뜻 번호 앞 공백 넓게(자간)")
        st += [S("글 잇기 — 새 이야기", 900), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    else:
        st += [S("글 잇기 — 같은 이야기를 이어 받는다", 700), {"pick": {"at": '#side select[data-a="story"]', "value": "이야기1"}, "wait": 900}]
    body = [s for s in sp if top < s["base"] < BOT and s["x"] < 135]
    Eslot(body, "#000000", label="낱말 항목")
    return st


def pa_first(lp=94):
    st = pg_new(lp, f"⑥ 파생어 & 연관어휘 · 첫 펼침면 — 원본 {lp}쪽(왼쪽)", name="파생어 & 연관어휘 · 첫 펼침면")
    st += styles()
    st += frame_first_left(lp)
    st += story_frame(lp, True)
    st += done("파생어 · 첫 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑥ 파생어 & 연관어휘 · 첫 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += story_frame(lp + 1, False)
    st += done("파생어 · 첫 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(ENTRY, []).extend(derived(REF_PATH, lp) + derived(REF_PATH, lp + 1))
    return st


def pa_body(lp=96):
    st = pg_new(lp, f"⑦ 파생어 & 연관어휘 · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="파생어 & 연관어휘 · 본문 펼침면")
    st += styles()
    st += frame_body_left(lp)
    st += story_frame(lp, ENTRY not in CONTENT)
    st += done("파생어 · 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑦ 파생어 & 연관어휘 · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_body_right(lp + 1)
    st += story_frame(lp + 1, False)
    st += done("파생어 · 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(ENTRY, []).extend(derived(REF_PATH, lp) + derived(REF_PATH, lp + 1))
    return st


FACES = {6: (pa_first,), 7: (pa_body,)}
