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
# 앞 단락이 여럿이면 [(앞 스타일, 거리) …] — 단락 앞 공백은 하나라 그 가운데 값(94쪽: 낱말 사이 뜻 뒤 7.87 · 유반의어 뒤 8.13 ·
# 번호 줄은 뜻 뒤 6.15 · 해석 뒤 5.95)
GAP = {"뜻 첫": ("번호", 4.57), "다음 뜻 첫": [("뜻", 7.87), ("유반의어 첫", 8.13), ("유반의어 첫", 8.15)], "뜻": ("뜻", 3.4),
       "예문 첫": ("뜻", 4.02), "해석": ("예문", 3.51), "예문": ("해석", 3.6), "유반의어 첫": [("뜻", 4.03), ("해석", 3.84)],
       "풀이 첫": ("해석", 4.2), "번호": [("뜻", 6.15), ("해석", 5.95), ("뜻", 6.18)]}
# 위 어림(가운데 값)으로 만든 판을 원본 94 · 96쪽과 맞대 보니 앞 스타일마다 0.4mm 남짓 달랐다(편집기는 앞 단락 행간의 아래 몫이 들어가고 인디자인은
# 다음 줄 행간만) — 다음 뜻 첫: 뜻 뒤 +0.44 · 유반의어 뒤 0 · 해석 뒤 +0.43 / 번호: 뜻 뒤 0 · 유반의어 뒤 −0.44 · 해석 뒤 +0.41 / 유반의어 첫: 뜻 뒤 0 · 해석 뒤 +0.40.
# 유반의어 단락 뒤 공백 0.44 로 유반의어 뒤를 뜻 뒤와 같게 하고, 단락 앞 공백을 그 가운데로 내린다(남는 차이 ±0.21 — 0.3mm 안)
SA = {"유반의어 첫": 0.44}
ADJ = {"다음 뜻 첫": 0.44, "번호": 0.20, "유반의어 첫": 0.20}
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
        need = sorted(d - (P[prev][3] - fb(*P[prev][:3], P[prev][3] * MMPT)) - fb(f, w, s, L * MMPT)
                      for prev, d in (GAP[n] if isinstance(GAP[n], list) else [GAP[n]]))
        sb = round(need[len(need) // 2] - ADJ.get(n, 0), 2)
        v = {"font": f, "weight": w, "size": s, "leading": round(L * MMPT, 2), "color": c, "space_before": max(sb, 0)}
        if SA.get(n):
            v["space_after"] = SA[n]
        if n != "번호":
            v["indent"] = IND
            if n != "풀이 첫":
                v["keep_next"] = True
        v["keep_together"] = True                                        # 단락 분리 금지(모든 행) — 다음 단락과 함께와 이어 단어 하나가 통째로 다음 쪽으로
        if hang:
            v.update(indent_first=-IND, tabs=[{"at": IND}])
        if n == "번호":                                                  # 뿌리 낱말 = 오른쪽 탭(단 끝 0.3mm 안 — 단 끝 딱 맞추면 줄이 꺾여 번호 줄이 두 줄이 됐다) · 번호 줄 선 = 아래 경계선(기준선 위 0.23mm)
            v.update(tabs=[{"at": round(W0 - 0.3, 2), "align": "right"}], keep_next=True, rule_below={"w": round(0.1 * MMPT, 3), "color": TEAL, "offset": -0.23})
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
        # 뜻 번호 앞 공백을 먼저(GREP 차례) — 번호를 먼저 감싸면 「공백 + 번호」 앞보기가 안 맞는다
        st += grep(0, r" (?=\d{1,2}\. )", "뜻 사이", label="GREP 스타일 — 뜻 번호 앞 공백 넓게(자간)")
        st += grep(1, r"(?<![\d.])\d{1,2}\.(?= )", "파생 뜻 번호", label="GREP 스타일 — 뜻 번호(1. 2.) 파랑")
        st += story_pick(ENTRY, True)
    else:
        st += story_pick(ENTRY, False)
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
