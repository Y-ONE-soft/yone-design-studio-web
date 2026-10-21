"""상일보카 — 11 워크북 · 첫 펼침면(견본 162 · 163쪽) · 12 워크북 · 본문 펼침면(견본 164 · 165쪽).
쪽 틀(갈색 띠 · DAY 번호표 · 원 번호표 · 옆 탭 · 꼬리)은 common.py. 첫 펼침면 왼쪽 틀은 머리 제목이 없어 이 파일의 wb_first_left(common 의
frame_first_left 에서 머리 제목만 뺀 것).

본문 = DAY 하루치 문제 A~D.
  A 우리말 뜻 쓰기 — DAY 첫 쪽(첫 펼침면 왼쪽)에만 온다. 2단 낱말 목록이라 흐름과 따로: 발문 글상자(자리 「A 발문」) +
    낱말 글상자(자리 「A 번호+A 낱말」, 2단 · 단 균형 맞추기). 답 줄 = 단락 아래 경계선(너비 「텍스트」 — 낱말 왼쪽 ~ 단 오른쪽).
  B~D = 한 줄기 흐름(자리 FLOW) — 첫 펼침면 오른쪽에서 시작해 본문 펼침면 쪽마다 글상자 + 글 잇기.
    문제 머리 = 「B 발문」 · 「C 발문」 · 「D 발문」 단락 + 그 필드 앞 고정 개체(원 + 글자 그룹, 사용자 정의 위치).
    B 빈칸 문장 — 원고 꼴 「… c__ …」: GREP 「__」 → 문자 스타일 「워크·빈칸」(글자 색 없음 · 밑줄 · 자간 = 21mm 칸),
      GREP 「[A-Za-z](?=__)」 → 「워크·첫 글자」(분홍 굵게). 해석은 그 아래 단락.
    C 영영 풀이 — 보기 띠 = 단락 음영(열 너비 · 모퉁이 1mm), 답 칸 = 「C 풀이」 필드 뒤 인라인 고정 개체(베이지 둥근 상자).
    D 유반의어 — 보기 = 단락 음영(잇닿은 줄은 한 상자) + 탭 4칸(원고 = 줄마다 한 단락, 칸 사이 탭), 답 칸 = 「D 낱말」 뒤 인라인 고정 개체.
  번호(01 02 …)는 원고 — 다음 필드와 같은 단락(번호 ⇥ 글), 문자 스타일로 굵기 · 색 · 기준선 이동.

원고 꼴(바깥 시스템):
  「A 발문」: 글 하나 · 「A 번호+A 낱말」: [{A 번호, A 낱말} …]
  FLOW: 레코드 차례 — [[["B 발문", 글]], [["B 번호", "01"], ["B 문장", "Milan … c__ of …"], ["B 해석", 글]], …,
        [["C 발문", 글]], [["C 보기", "adequate / apology / …"]], [["C 번호", "01"], ["C 풀이", "to start … :"]], …,
        [["D 발문", 글]], [["D 보기", "① …\t② …\t③ …\t④ …\n⑤ …"]], [["D 번호", "01"], ["D 낱말", "chief [유의어] :"]], …]

허용(책에서 손보기) — 있는 기능으로 원본과 똑같이 안 되는 곳:
  ① (해결 2026-10-20) 문제(B · C · D)마다 새 쪽에서 시작 — 발문 단락 스타일 「단락 시작: 다음 페이지」(인디자인 분리 금지 옵션)로.
  ② D 낱말 2단(01~07 | 08~13) — 한 줄기 안에서 단 나누기(인디자인 단락 「단 분할」)가 없어 한 단(단 너비 52mm)으로 흐른다.
     낱말이 많은 DAY(14개 넘게 — 15권 중 6)는 다음 쪽으로 넘친다.
  ③ 답 칸 · 보기 띠 둥근 모퉁이는 맞춤, 빈칸 밑줄 뒤 틈(밑줄 끝 → 다음 낱말 1.0mm, 편집기는 공백 폭 0.6mm).
  ④ A 낱말 줄 간격은 견본 162쪽(13줄) 값 하나 — 원본은 DAY 마다 손으로 벌렸다(173쪽 12줄은 12.0mm).
  ⑤ DAY 첫 쪽이 오른쪽에 오는 곳(173 · 195 · 205 · 211 · 217 · 227 · 237쪽) — 이 면의 왼쪽 반쪽(A)을 오른쪽 쪽에 쓴 꼴(옆 탭 · 오른쪽 꼬리)은
     면 목록에 따로 없다. 그 쪽은 책에서 손보기.
  ⑥ 문제 머리 앞 간격(앞 문제 끝 → 머리) — 원본에 잇닿은 곳이 없어(늘 새 쪽) C 보기 앞 간격(같은 책 문제 묶음 사이)을 쓴다.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
import common
from face_pyo import fb, MMPT, X0, W0, BOT, Eslot, ENTRY as _PYO_FLOW
from face_pa import ENTRY as _PA_FLOW

PF = "워크·"                                                            # 스타일 이름 앞붙이 — 한 책에 다른 면 스타일과 같이 있다
FLOW = "B 발문+B 번호+B 문장+B 해석+C 발문+C 보기+C 번호+C 풀이+D 발문+D 보기+D 번호+D 낱말"
ALIST = "A 번호+A 낱말"
NUMC, PINK, TR, BAND, BOXC, ULC = "#ada294", "#e54196", "#4d4d4d", "#eceef2", "#efe7d5", "#d3c7a5"
SEC = {"A": 162, "B": 163, "C": 165, "D": 167}                           # 문제마다 머리를 재는 견본 쪽(DAY 31)
COL2 = 74.0                                                             # 2단(A · D) — 오른쪽 단 경계(왼쪽 단 끝 70.99 · 오른쪽 단 76.99)


# ── 원본 읽기 ─────────────────────────────────────────────────────────────────
def body_spans(pno):
    return [s for s in spans(pno) if 12 < s["base"] < 200 and s["x"] < 135]


def rows_of(sps, tol=0.45):
    out = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if out and abs(out[-1][0]["base"] - s["base"]) < tol:
            out[-1].append(s)
        else:
            out.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in out]


def join(row, blanks=()):
    """한 줄 글 — 조각 사이 틈 0.4mm 넘으면 빈칸. 빈칸 밑줄(blanks) 자리는 「__」(분홍 첫 글자 바로 뒤)"""
    toks = [dict(s) for s in row] + [{"x": d["x"], "x1": d["x"] + d["w"], "text": "__", "blank": True} for d in blanks]
    toks.sort(key=lambda s: s["x"])
    t = ""
    for k, s in enumerate(toks):
        if k:
            p = toks[k - 1]
            glue = s.get("blank") and p.get("color") == PINK
            t += s["text"] if glue or s["x"] - p["x1"] <= 0.4 else " " + s["text"]
        else:
            t = s["text"]
    return re.sub(r"\s+", " ", t).strip()


def heads(pno):
    """문제 머리 — [(글자, 기준선, 발문 줄, 원)]"""
    sp, dr = body_spans(pno), ref_draws(pno)
    out = []
    for h in (s for s in sp if s["color"] == "#ffffff" and s["size"] == 5.6):
        q = sp_line(sp, lambda s: abs(s["base"] - h["base"]) < 0.3 and s["size"] == 7.0)
        c = next(d for d in dr if not d["rect"] and 4 < d["w"] < 4.5 and abs(d["y"] + d["h"] / 2 - h["base"] + 0.8) < 2)
        out.append((h["text"], h["base"], q, c))
    return out


def nums(pno):
    return sorted((s for s in body_spans(pno) if s["color"] == NUMC and s["size"] == 5.6 and re.fullmatch(r"\d\d", s["text"])),
                  key=lambda s: (s["x"] > COL2, s["base"]))


def a_items(pno):
    sp = body_spans(pno)
    out = []
    for n in nums(pno):
        r = [s for s in sp if abs(s["base"] - n["base"]) < 0.4 and s["size"] == 6.4 and n["x"] < s["x"] < n["x"] + 52]
        out.append({"n": n, "w": line_of(r, r[0]["base"]) if r else None, "rec": [["A 번호", n["text"]], ["A 낱말", join(r)]]})
    return out


def b_items(pno):
    sp, dr = body_spans(pno), ref_draws(pno)
    ul = [d for d in dr if d["rect"] and d["h"] < 0.2 and d["fill"] == "#000000" and d["w"] > 15]
    ns = nums(pno)
    out = []
    for k, n in enumerate(ns):
        end = ns[k + 1]["base"] - 0.6 if k + 1 < len(ns) else 200
        en = rows_of([s for s in sp if s["size"] == 6.4 and n["base"] - 0.6 < s["base"] < end])
        ko = rows_of([s for s in sp if s["size"] == 5.6 and s["color"] == TR and n["base"] - 0.6 < s["base"] < end])
        sent = " ".join(join(r, [d for d in ul if 0 < d["y"] - r[0]["base"] < 1.0]) for r in en)
        out.append({"n": n, "en": [r[0]["base"] for r in en], "ko": [r[0]["base"] for r in ko], "rows": en + ko,
                    "rec": [["B 번호", n["text"]], ["B 문장", sent], ["B 해석", " ".join(join(r) for r in ko)]]})
    return out


def c_items(pno):
    """보기 띠 · 문항 — 차례대로 [("보기", 띠, 줄) | ("문항", 번호, 줄들)]"""
    sp, dr = body_spans(pno), ref_draws(pno)
    bands = [d for d in dr if d["fill"] == BAND and d["w"] > 100]
    ns = nums(pno)
    ev = sorted([("보기", b["y"], b) for b in bands] + [("문항", n["base"], n) for n in ns], key=lambda e: e[1])
    out = []
    for k, (kind, y, o) in enumerate(ev):
        end = ev[k + 1][1] - 0.6 if k + 1 < len(ev) else 200
        if kind == "보기":
            r = rows_of([s for s in sp if o["y"] < s["base"] < o["y"] + o["h"] and s["size"] == 6.2])[0]
            out.append({"k": kind, "band": o, "base": r[0]["base"], "line": line_of(r, r[0]["base"]), "rec": [["C 보기", join(r)]]})
        else:
            rs = rows_of([s for s in sp if s["size"] == 6.2 and s["color"] == "#000000" and o["base"] - 0.6 < s["base"] < end])
            out.append({"k": kind, "n": o, "bases": [r[0]["base"] for r in rs], "rows": rs,
                        "rec": [["C 번호", o["text"]], ["C 풀이", " ".join(join(r) for r in rs)]]})
    return out


def d_items(pno):
    sp, dr = body_spans(pno), ref_draws(pno)
    band = next(d for d in dr if d["fill"] == BAND and d["w"] > 100)
    brows = rows_of([s for s in sp if band["y"] < s["base"] < band["y"] + band["h"] and s["size"] == 6.2])
    cells = []
    for r in brows:                                                     # 칸 사이 = 틈 2mm 넘는 곳(탭)
        parts, cur = [], [r[0]]
        for a, b in zip(r, r[1:]):
            if b["x"] - a["x1"] > 2.0:
                parts.append(cur)
                cur = []
            cur.append(b)
        parts.append(cur)
        cells.append(parts)
    boga = "\n".join("\t".join(join(p) for p in parts) for parts in cells)
    ns = nums(pno)
    items = []
    for k, n in enumerate(ns):
        same = [m for m in ns if (m["x"] > COL2) == (n["x"] > COL2) and m["base"] > n["base"] + 0.5]
        end = min(m["base"] for m in same) - 0.6 if same else 200
        x0 = n["x"] + 2
        rs = rows_of([s for s in sp if s["size"] == 6.4 and x0 < s["x"] < x0 + 50 and n["base"] - 0.6 < s["base"] < end])
        items.append({"n": n, "bases": [r[0]["base"] for r in rs], "rows": rs, "rec": [["D 번호", n["text"]], ["D 낱말", " ".join(join(r) for r in rs)]]})
    return {"band": band, "rows": brows, "cells": cells, "rec": [["D 보기", boga]], "items": items}


def page_records(pno, sec):
    """원본 쪽 하나의 흐름 원고(레코드 차례). sec = 이 쪽이 이어 받는 문제(머리 없이 시작하는 쪽)"""
    hs = {h[0]: h for h in heads(pno)}
    sec = next(iter(hs), sec)
    recs = [[[f"{sec} 발문", hs[sec][2]["text"]]]] if sec in hs else []
    if sec == "B":
        recs += [it["rec"] for it in b_items(pno)]
    elif sec == "C":
        recs += [it["rec"] for it in c_items(pno)]
    elif sec == "D":
        d = d_items(pno)
        recs += [d["rec"]] + [it["rec"] for it in d["items"]]
    return recs


# ── 재기 — 스타일 값 · 단락 사이 ───────────────────────────────────────────────────
def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def track_of(ln, font, weight):
    """원본 한 줄의 자간(‰) — 첫 글자 ~ 끝 글자 거리 − 브라우저 같은 글 거리(T() 와 같은 셈)"""
    s, t = ln["size"], ln["text"]
    if len(t) < 2:
        return 0
    return round(((ln["x1"] - ln["x"]) - chrome_extent(font, weight, s, t) - face(font, weight)[2](t[-1]) * s * MM) / (len(t) - 1) / (s * MM) * 1000)


G = {}


def measure():
    if G:
        return G
    # 문제 머리 — 원(지름 · 색) · 글자 · 발문(왼쪽 들여쓰기)
    G["head"] = {}
    for L, pno in SEC.items():
        h = next(x for x in heads(pno) if x[0] == L)
        G["head"][L] = {"base": h[1], "line": h[2], "circle": h[3], "letter": next(s for s in body_spans(pno) if s["color"] == "#ffffff" and s["text"] == L)}
    hB = G["head"]["B"]
    G["q_ind"] = round(hB["line"]["x"] - X0, 2)                          # 발문 글 왼쪽 − 단 왼쪽
    G["q_trk"] = track_of(hB["line"], NOTO, 500)
    # A — 줄 간격 · 답 줄(단락 아래 경계선) · 번호 기준선
    a = a_items(162)
    left = [it for it in a if it["n"]["x"] < COL2]
    wb = [it["w"]["base"] for it in left]
    G["a_pitch"] = round((wb[-1] - wb[0]) / (len(wb) - 1), 3)
    ul = sorted((d for d in ref_draws(162) if d["rect"] and d["fill"] == ULC and d["h"] < 0.3), key=lambda d: (d["x"], d["y"]))
    G["a_rule"] = {"w": round(ul[0]["h"] / MM, 3), "color": ULC, "offset": round(ul[0]["y"] - wb[0], 2), "x": ul[0]["x"]}
    G["a_ind"] = round(left[0]["w"]["x"] - left[0]["n"]["x"], 2)
    right = [it for it in a if it["n"]["x"] > COL2]
    G["a_gutter"] = round(right[0]["n"]["x"] - (ul[0]["x"] + ul[0]["w"]), 2)
    G["a_first"] = wb[0]
    G["a_nshift"] = round(med([it["w"]["base"] - it["n"]["base"] for it in a]), 2)    # 낱말 기준선 − 번호 기준선(번호가 아래면 음수 = 기준선 이동 아래)
    G["a_trk"] = track_of(max((it["w"] for it in a), key=lambda w: len(w["text"])), NOTO, 400)
    # B — 문장 행간 · 해석 · 빈칸
    b = b_items(163) + b_items(164)
    two = [it["en"] for it in b if len(it["en"]) > 1]
    G["b_lead"] = round(med([e[1] - e[0] for e in two]), 3)
    G["b_ind"] = round(G["a_ind"], 2)
    G["b_nshift"] = round(med([it["en"][0] - it["n"]["base"] for it in b]), 2)  # 번호 기준선이 낱말보다 위(+)
    d = {}
    b163 = b_items(163)
    d[("발문", "B 문장")] = b163[0]["en"][0] - G["head"]["B"]["base"]
    d[("B 해석", "B 문장")] = med([y["en"][0] - x["ko"][-1] for x, y in zip(b163, b163[1:])])
    d[("B 문장", "B 해석")] = med([it["ko"][0] - it["en"][-1] for it in b163])
    ko2 = []
    for p in range(163, 242):                                           # 두 줄 해석(행간) — 워크북 B 쪽 어디든
        if p in (162,):
            continue
        sp = [s for s in spans(p) if s["color"] == TR and s["size"] == 5.6]
        bs = sorted({round(s["base"], 2) for s in sp})
        ko2 += [y - x for x, y in zip(bs, bs[1:]) if 1.5 < y - x < 3.6]
        if len(ko2) > 4:
            break
    G["b_ko_lead"] = round(med(ko2), 3) if ko2 else round(5.6 * 1.45 * MM, 3)
    ln = next(r for it in b163 for r in it["rows"][1:2] if len(it["en"]) > 1)        # 빈칸 없는 둘째 줄
    G["b_trk"] = track_of(line_of(ln, ln[0]["base"]), NOTO, 400)
    kl = max((r for it in b163 for r in it["rows"] if r[0]["color"] == TR), key=len)
    G["b_ko_trk"] = track_of(line_of(kl, kl[0]["base"]), NOTO, 400)
    # 빈칸 — 밑줄 폭 · 굵기 · 기준선 → 밑줄 위 끝 · 분홍 글자 뒤 틈
    dr = ref_draws(163)
    ul = [x for x in dr if x["rect"] and x["h"] < 0.2 and x["fill"] == "#000000" and x["w"] > 15]
    sp = body_spans(163)
    pk = []
    for u in ul:
        p = min((s for s in sp if s["color"] == PINK and abs(s["base"] - u["y"]) < 1.0), key=lambda s: abs(s["x1"] - u["x"]))
        pk.append((p, u))
    _, _, adv_b = face(NOTO, 700)
    G["blank"] = {"w": round(med([u["w"] for _, u in pk]), 2), "lw": round(ul[0]["h"] / MM, 3), "off": round(med([u["y"] - p["base"] for p, u in pk]) / MM, 2),
                  "pink_trk": round(med([((u["x"] - p["x"]) - adv_b(p["text"]) * 6.4 * MM) / (6.4 * MM) * 1000 for p, u in pk]))}
    # C — 보기 띠 · 풀이 행간 · 답 칸
    c = c_items(165)
    bandi = [it for it in c if it["k"] == "보기"]
    qi = [it for it in c if it["k"] == "문항"]
    G["c_band"] = {"x": bandi[0]["band"]["x"], "y": bandi[0]["band"]["y"], "h": bandi[0]["band"]["h"], "base": bandi[0]["base"],
                   "ind": round(bandi[0]["line"]["x"] - X0, 2), "trk": track_of(bandi[0]["line"], NOTO, 500)}
    G["c_lead"] = round(med([it["bases"][1] - it["bases"][0] for it in qi if len(it["bases"]) > 1]), 3)
    G["c_nshift"] = round(med([it["bases"][0] - it["n"]["base"] for it in qi]), 2)
    d[("발문", "C 보기")] = bandi[0]["base"] - G["head"]["C"]["base"]
    d[("C 풀이", "C 보기")] = med([c[k]["base"] - c[k - 1]["bases"][-1] for k in range(1, len(c)) if c[k]["k"] == "보기"])
    d[("C 보기", "C 풀이")] = med([c[k]["bases"][0] - c[k - 1]["base"] for k in range(1, len(c)) if c[k]["k"] == "문항" and c[k - 1]["k"] == "보기"])
    d[("C 풀이", "C 풀이")] = med([c[k]["bases"][0] - c[k - 1]["bases"][-1] for k in range(1, len(c)) if c[k]["k"] == "문항" and c[k - 1]["k"] == "문항"])
    one = next(it for it in qi if len(it["bases"]) == 1)
    G["c_trk"] = track_of(line_of(one["rows"][0], one["bases"][0]), NOTO, 400)
    boxes = [x for x in ref_draws(165) if x["fill"] == BOXC]
    G["box"] = {"w": round(med([x["w"] for x in boxes]), 2), "h": round(med([x["h"] for x in boxes]), 2), "r": 0.6}   # 모퉁이 0.6mm(원본 경로 꼭짓점)
    gaps, drops = [], []
    _, _, adv_r = face(NOTO, 400)
    for it in qi:
        last = it["rows"][-1]
        col = last[-1]
        bx = min(boxes, key=lambda x: abs(x["y"] + x["h"] - it["bases"][-1] - 0.8) + abs(x["x"] - col["x1"]))
        gaps.append(bx["x"] - (col["x"] + adv_r(col["text"]) * 6.2 * MM))
        drops.append(bx["y"] + bx["h"] - it["bases"][-1])
    G["box_gap"], G["box_drop"] = round(med(gaps), 2), round(med(drops), 2)
    # D — 보기 표(탭 4칸) · 낱말
    dd = d_items(167)
    rb = [r[0]["base"] for r in dd["rows"]]
    G["d_band"] = {"y": dd["band"]["y"], "h": dd["band"]["h"], "first": rb[0], "last": rb[-1], "pitch": round((rb[-1] - rb[0]) / (len(rb) - 1), 3),
                   "ind": round(dd["cells"][0][0][0]["x"] - X0, 2), "tabs": [round(p[0]["x"] - X0, 2) for p in dd["cells"][0][1:]],
                   "trk": track_of(line_of(dd["cells"][0][0], rb[0]), NOTO, 500)}
    di = dd["items"]
    G["d_lead"] = round(med([it["bases"][1] - it["bases"][0] for it in di if len(it["bases"]) > 1]), 3)
    G["d_nshift"] = round(med([it["bases"][0] - it["n"]["base"] for it in di]), 2)
    G["d_colw"] = round(next(it["n"]["x"] for it in di if it["n"]["x"] > COL2) - X0 - 6.0, 2)   # 단 너비 = 오른쪽 단 왼쪽 − 단 간격(A 와 같은 6mm)
    d[("발문", "D 보기")] = rb[0] - G["head"]["D"]["base"]
    d[("D 보기", "D 낱말")] = di[0]["bases"][0] - rb[-1]
    col0 = [it for it in di if it["n"]["x"] < COL2]
    d[("D 낱말", "D 낱말")] = med([y["bases"][0] - x["bases"][-1] for x, y in zip(col0, col0[1:])])
    G["d_trk"] = track_of(line_of(di[0]["rows"][0], di[0]["bases"][0]), NOTO, 400)
    dbox = [x for x in ref_draws(167) if x["fill"] == BOXC]
    G["d_box_gap"] = round(med([min(dbox, key=lambda x: abs(x["y"] + x["h"] - it["bases"][-1] - 0.8) + abs(x["x"] - it["rows"][-1][-1]["x1"]))["x"]
                                - (it["rows"][-1][-1]["x1"]) for it in di]), 2)
    G["d"] = {k: round(v, 3) for k, v in d.items()}
    return G


# 단락 스타일 — 이름: (서체, 굵기, 크기 pt, 행간 mm)
def pstyles():
    g = measure()
    return {"발문": (NOTO, 500, 7.0, round(7.0 * 1.45 * MM, 3)),           # 한 줄뿐 — 행간은 보이지 않는다(크기의 145%)
            "B 문장": (NOTO, 400, 6.4, g["b_lead"]), "B 해석": (NOTO, 400, 5.6, g["b_ko_lead"]),
            "C 보기": (NOTO, 500, 6.2, round(6.2 * 1.45 * MM, 3)), "C 풀이": (NOTO, 400, 6.2, g["c_lead"]),
            "D 보기": (NOTO, 500, 6.2, g["d_band"]["pitch"]), "D 낱말": (NOTO, 400, 6.4, g["d_lead"]),
            "A 낱말": (NOTO, 400, 6.4, g["a_pitch"])}


def spacing():
    """단락 앞 · 뒤 공백 — 원본 기준선 사이 d(앞 단락 끝 줄 → 이 단락 첫 줄) = 앞 줄 상자 아래(행간 − 첫 기준선) + 앞 「뒤 공백」 + 이 「앞 공백」 + 이 첫 기준선.
    잇닿는 차례마다 d 가 다르니(발문 → B 문장 6.55 · 해석 → 문장 5.75 …) 앞 공백 · 뒤 공백 둘로 푼다(묶음마다 가장 작은 쪽을 0)."""
    g, P = measure(), pstyles()
    A = {n: fb(f, w, s, L * MMPT) for n, (f, w, s, L) in P.items()}
    D = {n: P[n][3] - A[n] for n in P}
    d = dict(g["d"])
    d[("C 풀이", "발문")] = d[("C 풀이", "C 보기")] - A["C 보기"] + A["발문"]      # 허용 ⑥ — 머리 앞은 C 보기 앞 간격(원본에 잇닿은 곳 없음)
    # g_Q + h_P = d  (g = D + 뒤 공백, h = A + 앞 공백) — 묶음(이어진 차례)마다 g 하나를 0 기준으로 풀고 음수가 안 되게 옮긴다
    gv, hv = {}, {}
    edges = list(d.items())
    left = set(range(len(edges)))
    while left:
        k0 = min(left)
        (q, p), v = edges[k0]
        comp_g, comp_h = {q: 0.0}, {}
        changed = True
        while changed:
            changed = False
            for k in list(left):
                (q2, p2), v2 = edges[k]
                if q2 in comp_g and p2 not in comp_h:
                    comp_h[p2] = v2 - comp_g[q2]
                elif p2 in comp_h and q2 not in comp_g:
                    comp_g[q2] = v2 - comp_h[p2]
                elif q2 in comp_g and p2 in comp_h:
                    if abs(comp_g[q2] + comp_h[p2] - v2) > 0.02:
                        raise RuntimeError(f"단락 사이 셈이 안 맞음 {q2}→{p2}")
                else:
                    continue
                left.discard(k)
                changed = True
        c = max(D[n] - x for n, x in comp_g.items())                    # 뒤 공백이 음수가 안 되게
        if any(x - c - A[n] < -0.005 for n, x in comp_h.items()):
            raise RuntimeError(f"단락 사이를 음수 없이 못 푼다 {comp_g} {comp_h}")
        gv.update({n: x + c for n, x in comp_g.items()})
        hv.update({n: x - c for n, x in comp_h.items()})
    sa = {n: round(gv[n] - D[n], 2) for n in gv}
    sb = {n: round(hv[n] - A[n], 2) for n in hv}
    return sa, sb


def styles(a=True):
    """스타일 — a=False 면 A(우리말 뜻 쓰기) 스타일은 안 만든다: 본문 펼침면엔 A 글상자가 없다. 첫 펼침면과 한 문서면 그쪽이 만든다(_DONE 로 한 번만).
    (쓰지 않는 스타일을 만들면 그만큼 스타일 창 칸을 더 채운다 — 칸을 채우면 편집기가 0.8초 뒤 저장 → 그림 → 스타일 창을 다시 그려
    펼친 칸이 닫힌다. 그 사이에 걸린 칸은 「굴려도 안 보임」(2026-10-20 본문 펼침면 「워크·A 낱말」 아래 경계선 색))"""
    g = measure()
    P = pstyles()
    sa, sb = spacing()
    st = []
    st += need_cstyle(PF + "번호", {"font": NOTO, "weight": 700, "size": 5.6, "color": NUMC, "bshift": round(g["b_nshift"] * MMPT, 2)},
                      label=f"문자 스타일 「워크·번호」 — B 번호(기준선 {g['b_nshift']}mm 위)")
    if a:
        st += need_cstyle(PF + "A 번호", {"font": NOTO, "weight": 700, "size": 5.6, "color": NUMC, "bshift": round(g["a_nshift"] * MMPT, 2)},
                          label=f"문자 스타일 「워크·A 번호」 — 기준선 {-g['a_nshift']}mm 아래")
    for L in ("C", "D"):
        st += need_cstyle(PF + f"{L} 번호", {"font": NOTO, "weight": 700, "size": 5.6, "color": NUMC, "bshift": round(g[f"{L.lower()}_nshift"] * MMPT, 2)},
                          label=f"문자 스타일 「워크·{L} 번호」 — 기준선 {g[f'{L.lower()}_nshift']}mm 위")
    bl = g["blank"]
    _, _, adv = face(NOTO, 400)
    trk = round((bl["w"] / (6.4 * MM) - 2 * adv("_")) / 2 * 1000)      # 「__」 두 글자 + 자간 = 칸 폭(밑줄은 자간까지 긋는다)
    st += need_cstyle(PF + "첫 글자", {"font": NOTO, "weight": 700, "color": PINK, "track": bl["pink_trk"]}, label="문자 스타일 「워크·첫 글자」 — 빈칸 앞 분홍 굵은 글자")
    st += need_cstyle(PF + "빈칸", {"u": 1, "color": "none", "track": trk, "u_w": bl["lw"], "u_off": bl["off"], "u_color": "#000000"},
                      label=f"문자 스타일 「워크·빈칸」 — {bl['w']}mm 밑줄 칸(글자 색 없음 · 밑줄 · 자간)")
    trks = {"발문": g["q_trk"], "B 문장": g["b_trk"], "B 해석": g["b_ko_trk"], "C 보기": g["c_band"]["trk"], "C 풀이": g["c_trk"],
            "D 보기": g["d_band"]["trk"], "D 낱말": g["d_trk"], "A 낱말": g["a_trk"]}
    color = {"B 해석": TR}
    for n, (f, w, s, L) in P.items():
        if n.startswith("A ") and not a:
            continue
        v = {"font": f, "weight": w, "size": s, "leading": round(L * MMPT, 2), "color": color.get(n, "#000000")}
        if trks.get(n):
            v["tracking"] = trks[n]
        if sb.get(n):
            v["space_before"] = sb[n]
        if sa.get(n):
            v["space_after"] = sa[n]
        if n == "발문":
            v.update(indent=g["q_ind"], keep_next=True, start="page")    # 문제(B · C · D)마다 새 쪽 맨 위 — 분리 금지 옵션 「단락 시작: 다음 페이지」
        elif n in ("B 문장", "C 풀이", "D 낱말", "A 낱말"):                # 번호 ⇥ 글 — 내어쓰기 + 탭
            v.update(indent=g["b_ind"], indent_first=-g["b_ind"], tabs=[{"at": g["b_ind"]}])
            if n == "B 문장":
                v["keep_next"] = True                                    # 문장은 해석과 함께
            if n == "D 낱말":
                v["indent_right"] = round(W0 - g["d_colw"], 2)           # 허용 ② — 한 단을 원본 단 너비로
            if n == "A 낱말":
                r = g["a_rule"]
                v["rule_below"] = {"w": r["w"], "color": r["color"], "offset": r["offset"], "width": "text"}
        elif n == "B 해석":
            v["indent"] = g["b_ind"]
        elif n == "C 보기":
            cb = g["c_band"]
            top = cb["base"] - fb(f, w, s, L * MMPT)
            v.update(indent=cb["ind"], shade=BAND, shade_r=1.0, shade_ot=round(top - cb["y"], 2),
                     shade_ob=round(cb["y"] + cb["h"] - (cb["base"] + L - fb(f, w, s, L * MMPT)), 2), keep_next=True)
        elif n == "D 보기":
            db = g["d_band"]
            A_ = fb(f, w, s, L * MMPT)
            v.update(indent=db["ind"], tabs=[{"at": t} for t in db["tabs"]], shade=BAND, shade_r=1.0, shade_ot=round(db["first"] - A_ - db["y"], 2),
                     shade_ob=round(db["y"] + db["h"] - (db["last"] + L - A_), 2), space_same=0, keep_next=True)
        st += need_pstyle(PF + n, v)
    return st


# ── 부품(고정 개체) — 문제 머리 원 A~D · 답 칸 ────────────────────────────────────────
PARTS = {}
PX, PY = 30.0, 120.0                                                    # 부품을 그려 묶는 빈 자리(첫 쪽, 본문 글상자를 그리기 전)


def part_id():
    """이 대본이 만든 부품 차례 — 빈 라이브러리에서 시작하면 편집기가 p_1, p_2 … 로 붙인다(정본 대본과 같은 셈)"""
    return f"p_{len(PARTS) + 1}"


def group_part(st, n, w, h):
    """빈 자리에 그린 개체 n 개를 범위로 골라 그룹 → 부품, 지면에서는 지운다(부품은 라이브러리에 남는다) — 정본 대본과 같은 조작"""
    st += [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1000), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
           S(f"범위로 {n}개를 골라 그룹 → 부품", 1200),
           {"drag": {"from": {"mm": [PX - 2, PY - 2]}, "to": {"mm": [PX + w + 2, PY + h + 2]}}, "wait": 900},
           {"js": f"(() => {{ if (sels.size !== {n}) throw new Error('고른 것 ' + sels.size + ' ({n} 이어야)'); return '고른 것 {n}'; }})()"},
           {"click": "#side #s-group", "wait": 1500},
           {"until": f"LIB.parts.length && LIB.parts[LIB.parts.length - 1].atoms.length === {n}", "wait": 300},
           {"js": f"(() => {{ const p = LIB.parts[LIB.parts.length - 1]; if (!p || p.atoms.length !== {n}) throw new Error('부품 안 생김'); return '부품 ' + p.id; }})()"},
           S("지면의 그룹은 지운다", 900), {"key": "Delete", "wait": 900},
           {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]
    return st


def parts():
    if PARTS:
        return []
    g = measure()
    st = [S("부품 — 문제 머리 원(A · B · C · D) · 답 칸 — 빈 자리에 그려 묶는다", 1500)]
    for L in "ABCD":
        h = g["head"][L]
        c, lt = h["circle"], h["letter"]
        s_ = [S(f"문제 머리 원 「{L}」 — 지름 {c['w']}mm · 칠 {c['fill']} · 흰 글자(Noto Sans CJK KR Bold {lt['size']}pt)", 1100)]
        s_ += ellipse(PX, PY, c["w"], fill=c["fill"])
        top = top_of(lt["base"] - c["y"] + PY, lt["size"], NOTO, 700, lt["size"])
        s_ += text(PX, round(top, 2), c["w"], round(lt["size"] * MM + 0.3, 2), L, lt["size"], "#ffffff", font=NOTO, weight=700, align="center",
                   leading=lt["size"], auto="")
        st += group_part(s_, 2, c["w"], c["h"])
        PARTS[L] = part_id()
    b = g["box"]
    s_ = [S(f"답 칸 — {b['w']}×{b['h']}mm · 칠 {BOXC} · 모퉁이 {b['r']}mm (그룹은 둘 이상 — 안 보이는 짝 상자)", 1100)]
    s_ += box(PX, PY, b["w"], b["h"], BOXC, radius=b["r"])
    s_ += box(PX, PY, b["w"], b["h"], "#ffffff", alpha=0)
    st += group_part(s_, 2, b["w"], b["h"])
    PARTS["칸"] = part_id()
    return st


def head_anchor(field, L):
    """문제 머리 원 — 발문 필드 앞 고정 개체(사용자 정의 · 텍스트 프레임 가장자리 · 기준선). 원 위 끝 = 발문 기준선 − 2.91mm"""
    h = measure()["head"][L]
    return [S(f"「{field}」 필드 앞 고정 개체 — 원 {L}", 900)] + slot_anchor(field, PARTS[L], "custom", "start", xref="frame", yref="baseline",
                                                                       x=round(h["circle"]["x"] - X0, 2), y=round(h["circle"]["y"] - h["base"], 2))


def box_anchor(field, gap):
    g = measure()
    return [S(f"「{field}」 필드 뒤 인라인 고정 개체 — 답 칸(콜론 뒤 {gap}mm · 아래 끝 기준선 {g['box_drop']}mm 아래)", 900)] + \
        slot_anchor(field, PARTS["칸"], "inline", "end", x=gap, y=-g["box_drop"])


# ── 쪽 틀 — 첫 펼침면 왼쪽(머리 제목 없음) ─────────────────────────────────────────────
def wb_first_left(pno):
    """common.frame_first_left 와 같고 머리 제목만 없다(워크북 첫 쪽엔 머리 제목이 없다)"""
    sp, dr = spans(pno), ref_draws(pno)
    top = [e for e in dr if e["y"] < 8 and e["h"] > 8]
    band = max((e for e in top if e["alpha"] == 100 and e["w"] > 100), key=lambda e: e["w"])
    over = next(e for e in top if e["alpha"] < 100)
    tri = next(e for e in dr if e["w"] < 3 and e["h"] > 6 and e["y"] < 10)
    badge = next(e for e in dr if e["fill"] == "#ffffff" and e["y"] < 10 and e["w"] > 10)
    stroke = next(e for e in dr if e["stroke"] and not e["fill"] and abs(e["x"] - badge["x"]) < 0.3)
    st = [S("첫 펼침면 왼쪽 틀 — 띠 · 덧띠 · 번호표", 1200)]
    st += ref_shape(band, fill=band["fill"], label="높은 띠(왼쪽 아래 곡선)")
    st += ref_shape(over, fill=over["fill"], alpha=over["alpha"], label=f"덧띠 — 불투명 {over['alpha']}%")
    st += ref_shape(tri, fill=tri["fill"], label="번호표 옆 그림자")
    st += ref_shape(badge, fill="#ffffff", stroke=stroke["stroke"], sw=stroke["sw"], label="번호표(흰 칠 · 선 · 아래 두 귀 둥글게)")
    day = sp_line(sp, lambda s: s["text"].replace(" ", "") == "DAY" and s["base"] < 20)
    num = sp_line(sp, lambda s: s["size"] > 15 and s["base"] < 25)
    st += T(dict(day, text="DAY"), ELICE, 700, label="DAY — Elice DX Neolli Bold (겹침 0.96)")
    st += T(num, BEBAS, 700, label="DAY 번호 — 원고 자리 「DAY 번호」 (가운데 맞춤 · 맞는 서체 없음, 가장 닮은 Bebas Neue Bold)",
            slot_name="DAY 번호", temp="00", align="center", w=round(badge["w"], 2))
    st += [F('#side input[data-it="x"]', round(badge["x"], 2))]
    CONTENT.setdefault("DAY 번호", []).append(num["text"])
    st += foot_left(pno, sp)
    return st


# ── 원고 요소(맞대기 — 원고는 「들어갔나」만) ───────────────────────────────────────────
def Earea(ds, color, label):
    if not ds:
        return
    x0, y0 = min(d["x"] for d in ds), min(d["y"] for d in ds)
    x1, y1 = max(d["x"] + d["w"] for d in ds), max(d["y"] + d["h"] for d in ds)
    E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
       "color": color, "see": color, "ctol": 30, "pad": 1.0, "search": 1.0, "text": label, "원고": True})


def measure_page(pno, top, circles=True):
    """그 쪽 원고 요소 — 글(검정) · 머리 원 · 보기 띠 · 답 칸 · 답 줄.
    circles = 머리 원도 잰다 — 이야기 첫 상자 쪽만(다른 쪽 맨 위 머리는 「새 쪽에서 시작」이라 편집기에선 앞 쪽에 이어 온다 — 허용 ①)"""
    sp = [s for s in body_spans(pno) if s["base"] > top]
    blk = [s for s in sp if s["color"] == "#000000"]
    if blk:
        Eslot(blk, "#000000", label="문제 글")
    dr = [d for d in ref_draws(pno) if d["y"] > top - 3 and d["y"] < BOT and d["x"] < 135]
    for h in (heads(pno) if circles else []):
        Earea([h[3]], h[3]["fill"], f"문제 머리 원 {h[0]}")
    Earea([d for d in dr if d["fill"] == BAND], BAND, "보기 띠")
    Earea([d for d in dr if d["fill"] == BOXC], BOXC, "답 칸")
    Earea([d for d in dr if d["fill"] == ULC], ULC, "답 줄")


# ── 글상자 ───────────────────────────────────────────────────────────────────
STORY = []


def flow_frame(pno, head):
    """B~D 한 줄기 글상자 — 이 쪽 첫 줄(원본)의 기준선에 첫 단락 첫 줄이 오게. head = 이 이야기의 첫 상자(자리 · 스타일 · GREP · 고정 개체 · 새 이야기)"""
    g, P = measure(), pstyles()
    hs = heads(pno)
    if hs:
        first, nm = hs[0][1], "발문"
    else:
        ns = nums(pno)
        sp = body_spans(pno)
        first = min(s["base"] for s in sp if s["x"] > 23 and s["size"] in (6.2, 6.4) and s["base"] > ns[0]["base"] - 1.0)
        nm = "B 문장" if any(s["size"] == 6.4 for s in sp if abs(s["base"] - first) < 0.3) else "C 풀이"
    f, w, s, L = P[nm]
    top = round(top_of(first, s, f, w, L * MMPT), 2)
    st = text(X0, top, W0, round(BOT - top, 2), "B 발문 — 문제 머리\n01\t문제 B~D 가 이 글상자로 흘러 들어온다", s, "#000000", font=f, weight=w,
              leading=round(L * MMPT, 2), label="문제 글상자 — 한 줄기 B~D(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기",
              first=(f, w, s, round(L * MMPT, 2)), auto="")
    if head:
        st += slot(FLOW, label="자리 — 문제 B~D(원고 차례대로 한 줄기)")
        for fld in FLOW.split("+"):
            if "번호" not in fld:
                st.append(slot_style(fld, PF + ("발문" if fld.endswith("발문") else fld), 450))
        st += [S("번호 — 뒤 단락(문장 · 풀이 · 낱말) 첫머리에 붙는다(번호 ⇥ 글)", 900)]
        st += slot_inline("B 번호", PF + "번호", "\t") + slot_inline("C 번호", PF + "C 번호", "\t") + slot_inline("D 번호", PF + "D 번호", "\t")
        for L in "BCD":
            st += head_anchor(f"{L} 발문", L)
        st += box_anchor("C 풀이", g["box_gap"]) + box_anchor("D 낱말", g["d_box_gap"])
        st += grep(0, r"[A-Za-z](?=__)", PF + "첫 글자", label="GREP 스타일 — 빈칸 앞 글자 분홍 굵게")
        st += grep(1, r"__", PF + "빈칸", label="GREP 스타일 — 원고의 __ 는 밑줄 칸")
        st += story_pick(FLOW, True)
    else:
        st += story_pick(FLOW, False)
    measure_page(pno, top, circles=head)
    return st


def a_frames(pno):
    """A — 발문 글상자(자리 「A 발문」 + 원 A 고정 개체) · 낱말 글상자(2단 · 단 균형 맞추기)"""
    g, P = measure(), pstyles()
    h = g["head"]["A"]
    f, w, s, L = P["발문"]
    top = round(top_of(h["base"], s, f, w, L * MMPT), 2)
    st = text(X0, top, W0, round(L + 1.5, 2), "A 발문", s, "#000000", font=f, weight=w, leading=round(L * MMPT, 2),
              label="A 발문 글상자", first=(f, w, s, round(L * MMPT, 2)), auto="")
    st += slot("A 발문", label="자리 — A 발문") + [slot_style("A 발문", PF + "발문", 450)] + head_anchor("A 발문", "A")
    f, w, s, L = P["A 낱말"]
    top2 = round(top_of(g["a_first"], s, f, w, L * MMPT), 2)
    st += text(X0, top2, W0, round(BOT - top2, 2), "01\t낱말 — A 낱말 목록이 2단으로 흘러 들어온다", s, "#000000", font=f, weight=w,
               leading=round(L * MMPT, 2), label="A 낱말 글상자 — 2단(단 균형 맞추기)", first=(f, w, s, round(L * MMPT, 2)), auto="")
    st += slot(ALIST, label="자리 — A 번호 + A 낱말") + [slot_style("A 낱말", PF + "A 낱말", 450)] + slot_inline("A 번호", PF + "A 번호", "\t")
    st += [S(f"텍스트 프레임 옵션 — 2단 · 간격 {g['a_gutter']}mm · 단 균형 맞추기", 900), P_("columns", 2, 900), P_("gutter", g["a_gutter"], 700),
           {"click": '#side input[data-a="col_balance"]', "wait": 800}]
    measure_page(pno, top - 1)
    return st


# ── 면 ───────────────────────────────────────────────────────────────────────
def wb_first(lp=162):
    st = pg_new(lp, f"⑪ 워크북 · 첫 펼침면 — 원본 {lp}쪽(왼쪽)", name="워크북 · 첫 펼침면")
    st += parts()
    st += styles()
    st += wb_first_left(lp)
    st += a_frames(lp)
    st += done("워크북 · 첫 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑪ 워크북 · 첫 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += flow_frame(lp + 1, True)
    st += done("워크북 · 첫 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault("A 발문", []).append(measure()["head"]["A"]["line"]["text"])
    CONTENT.setdefault(ALIST, []).extend(it["rec"] for it in a_items(lp))
    CONTENT.setdefault(FLOW, []).extend(page_records(lp + 1, "B"))
    return st


def wb_body(lp=164):
    st = pg_new(lp, f"⑫ 워크북 · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="워크북 · 본문 펼침면")
    st += parts()
    st += styles(a=False)                                                # A 글상자 없음 — A 스타일은 첫 펼침면 몫
    st += frame_body_left(lp)
    st += flow_frame(lp, FLOW not in CONTENT)
    st += done("워크북 · 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑫ 워크북 · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_body_right(lp + 1)
    st += flow_frame(lp + 1, False)
    st += done("워크북 · 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(FLOW, []).extend(page_records(lp, "B") + page_records(lp + 1, "C"))
    return st


FACES = {11: (wb_first,), 12: (wb_body,)}


if __name__ == "__main__":                                              # 재기만 — python3 face_wb.py
    import json
    print(json.dumps(measure(), ensure_ascii=False, default=str, indent=1)[:6000])
    print("앞 · 뒤 공백", spacing())
    for p, sec in ((163, "B"), (164, "B"), (165, "C"), (167, "D")):
        r = page_records(p, sec)
        print(p, len(r), json.dumps(r[:3], ensure_ascii=False))
