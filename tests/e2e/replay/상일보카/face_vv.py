"""상일보카 — 9 VOCA vs. VOCA · 첫 펼침면(견본 152 · 153쪽) · 10 VOCA vs. VOCA · 본문 펼침면(견본 154 · 155쪽).
쪽 틀: 9 왼쪽 = face_more.frame_part_left(「PART 1」 번호표), 9 오른쪽 = common.frame_first_right, 10 = common.frame_body_left/right.
본문 = 한 줄기 글(흐름 자리 VV) — 쪽마다 글상자 하나, 글 잇기로 이어 흐른다. 9 와 10 을 같이 돌리면 10 이 9 의 이야기를 이어 받는다(face_pyo 4 · 5 와 같다).

짜임(상자 하나 = 레코드 하나 = 비교 묶음 하나):
  단락 「머리」(뜻 — 보라 7pt) + 고정 개체 「VOCA vs. VOCA」 딱지(그룹, 사용자 정의 위치 — 머리 단락 왼쪽).
  낱말마다 단락 「풀이」(첫머리에 같은 단락 필드 「낱말」 — 굵은 7pt, 뒤 공백) + 고정 개체 「·」(그룹, 사용자 정의 — 낱말 왼쪽) · 단락 「예문」 · 단락 「해석」.
  상자 = 풀이 · 예문 · 해석 단락의 단락 테두리(잇닿은 같은 값은 한 상자) — 위 오프셋이 머리 단락까지 덮는다. 머리 단락은 테두리가 없어 앞 상자와 갈라진다.
원고 레코드(외부 연동 꼴, 차례대로): [["머리", "기억하다, 생각해내다"], ["낱말", "remember"], ["풀이", "(의식적인 노력 없이) 기억하다; …"],
  ["예문", ["I have a hard time ", {"t": "remembering", "cs": "강조"}, " names."]], ["해석", [...]], …낱말마다 반복…]
  예문 · 해석의 분홍 글 = 문자 스타일 「강조」(entries.py 와 같은 꾸밈 조각).

허용(책에서 손보기):
  · (해결 2026-10-20) 상자는 통째로 다음 쪽으로 — 원본 152~159쪽은 상자를 한 번도 나누지 않는다(154쪽 177.2mm · 156쪽 190.2mm 에 자리가 있어도).
    상자 안 단락 모두 「다음 행과 함께 유지」 · 「행 분리 금지」, 레코드 끝 해석은 자리 「끝 해석」(같은 모양, 다음 상자와 묶지 않음).
  · 딱지 · 「·」 은 그룹(고정 개체) — 글은 그룹 속 고정 글.
"""
import os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
from face_more import (fb, fspans, rows_of, join, corner, boxes_of, group_part, part_text, frame_part_left, thread, ebody,
                       MMPT, PRE, BOX_S, BOT, PX, PY)
from entries import runs

VV = "머리+낱말+풀이+예문+해석+끝 해석"
PF = "VV·"
HEAD_C, LAB_F, BUL_C, INK, GRAY, PINK = "#886eab", "#523e74", "#523e74", "#000000", "#4d4d4d", "#f37875"
HAN = lambda t: any("가" <= c <= "힣" for c in t)
BUL_DB = 2.6                                                            # 「·」 그룹 위 끝 → 「·」 기준선(그룹 안)
G = {}


def boxes(pno):
    """쪽 → 상자마다 {b: 상자, lab: 딱지, lt: 딱지 글, hd: 머리 글 조각들, rows: [(갈래, 기준선, 조각들)]} — 갈래: item(「·」 줄) · ex(예문) · ko(해석)"""
    sp, dr = fspans(pno), ref_draws(pno)
    labs = [d for d in dr if d["fill"] == LAB_F and d["w"] > 20]
    out = []
    for b in boxes_of(pno):
        inn = [s for s in sp if b["y"] < s["base"] < b["y"] + b["h"]]
        lab = next(d for d in labs if b["y"] < d["y"] < b["y"] + b["h"])
        rows = []
        for r in rows_of([s for s in inn if s["color"] not in ("#ffffff", HEAD_C)]):
            if r[0]["text"].strip() == "·":
                k = "item"
            elif all(s["color"] == GRAY or (s["color"] == PINK and HAN(s["text"])) for s in r):
                k = "ko"
            else:
                k = "ex"
            rows.append((k, r[0]["base"], r))
        out.append(dict(b=b, lab=lab, lt=next(s for s in inn if s["color"] == "#ffffff"),
                        hd=sorted((s for s in inn if s["color"] == HEAD_C), key=lambda s: s["x"]), rows=rows))
    return out


def measure():
    if G:
        return G
    med = statistics.median
    D = {}
    bs, gaps = [], []
    for pno in (152, 153, 154, 155):
        bb = boxes(pno)
        bs += bb
        gaps += [y["b"]["y"] - (x["b"]["y"] + x["b"]["h"]) for x, y in zip(bb, bb[1:])]
        for x in bb:
            prev = ("hd", x["hd"][0]["base"])
            for k, base, r in x["rows"]:
                if k == prev[0] and k != "item":                           # 꺾인 줄(같은 단락) — 행간
                    D.setdefault("wrap", []).append(base - prev[1])
                else:
                    D.setdefault((prev[0], k), []).append(base - prev[1])
                prev = (k, base)
    b0 = bs[0]
    items = [r for x in bs for k, _, r in x["rows"] if k == "item"]
    word = [[s for s in r if s["size"] == 7.0] for r in items]
    G.update(
        X0=b0["b"]["x"], W=b0["b"]["w"], sw=b0["b"]["sw"], r=corner(b0["b"]["d"], b0["b"]["h"]),
        lab=b0["lab"], lab_r=corner(b0["lab"]["d"], b0["lab"]["h"]), lab_h=med(x["lab"]["h"] for x in bs),
        lab_y=med(x["lab"]["y"] - x["hd"][0]["base"] for x in bs),                       # 딱지 위 끝 − 머리 기준선
        lt=b0["lt"], lt_dx=b0["lt"]["x"] - b0["lab"]["x"], lt_db=med(x["lt"]["base"] - x["lab"]["y"] for x in bs),
        hd_x=b0["hd"][0]["x"], top_hd=med(x["hd"][0]["base"] - x["b"]["y"] for x in bs),  # 상자 위 끝 → 머리 기준선
        bot_last=med(x["b"]["y"] + x["b"]["h"] - x["rows"][-1][1] for x in bs),           # 끝 줄 기준선 → 상자 아래 끝
        gap=med(gaps),
        bul_x=med(r[0]["x"] for r in items), word_x=med(w[0]["x"] for w in word),
        ex_x=med(r[0]["x"] for x in bs for k, _, r in x["rows"] if k != "item"),
        bul=next(s for s in items[0] if s["text"].strip() == "·"),
        **{f"d_{a}_{b}": med(v) for (a, b), v in ((k, v) for k, v in D.items() if k != "wrap")})
    g = G
    L = g["d_ex_ko"]                                                      # 행간 = 예문 → 해석 기준선 사이(꺾인 줄도 이 행간)
    g["L"], g["Lpt"] = L, round(L * MMPT, 2)
    g["Lh"] = round(7.0 * 1.2, 2)                                         # 머리 — 한 줄(자동 행간)
    fbI = fbE = fbK = fb(NOTO, 400, 6.0, g["Lpt"])
    fbH = fb(PRE, 700, 7.0, g["Lh"])
    below = L - fbK
    g["sb_i"] = round(g["d_ko_item"] - below - fbI, 2)                   # 해석 → 다음 낱말
    g["sa_h"] = round(g["d_hd_item"] - (g["Lh"] * MM - fbH) - g["sb_i"] - fbI, 2)   # 머리 → 첫 낱말은 그보다 넓다 — 머리 「단락 뒤 공백」
    g["sb_e"] = round(g["d_item_ex"] - (L - fbI) - fbE, 2)
    g["sb_k"] = round(g["d_ex_ko"] - (L - fbE) - fbK, 2)
    g["sb_h"] = round(g["bot_last"] + g["gap"] + g["top_hd"] - below - fbH, 2)       # 앞 상자 끝 해석 → 머리
    o = g["sw"] / 2
    g["ot"] = round(g["d_hd_item"] + g["top_hd"] - fbI + o, 2)          # 첫 낱말 줄 상자 위에서 상자 위 끝(선 바깥)까지 — 머리를 덮는다
    g["ob"] = round(g["bot_last"] - below + o, 2)
    g["fbH"] = fbH
    return g


def vv_styles():
    g = measure()
    st = []
    st += need_cstyle(PF + "낱말", {"font": NOTO, "weight": 700, "size": 7.0, "color": INK})            # Noto Sans CJK KR Bold(겹침 0.90)
    st += need_cstyle("강조", {"font": NOTO, "weight": 500, "color": PINK})                              # 원고 꾸밈 조각 — face_pyo 「강조」와 같은 값
    sw_pt = round(g["sw"] * MMPT, 3)
    border = {"border": sw_pt, "border_color": BOX_S, "border_r": g["r"], "border_ot": g["ot"], "border_ob": g["ob"],
              "border_ol": round(g["sw"] / 2, 3), "border_or": round(g["sw"] / 2, 3)}
    body = {"font": NOTO, "weight": 400, "size": 6.0, "leading": g["Lpt"]}
    st += need_pstyle(PF + "머리", {"font": PRE, "weight": 700, "size": 7.0, "leading": g["Lh"], "color": HEAD_C, "indent": round(g["hd_x"] - g["X0"], 2),
                                    "space_before": g["sb_h"], "space_after": max(g["sa_h"], 0), "keep_next": True},
                      label=f"단락 스타일 「{PF}머리」 — Pretendard Bold(겹침 0.93) · 테두리 없음(앞 상자와 갈라진다)")
    # 상자(레코드) 하나는 통째로 — 원본 152~159쪽은 상자를 한 번도 나누지 않는다(154쪽 177.2mm · 156쪽 190.2mm 에 자리가 있어도 다음 쪽으로).
    # 상자 안 단락은 모두 「다음 행과 함께 유지」 · 「행 분리 금지」, 레코드 끝 해석만 「끝 해석」(같은 모양 · 다음 상자와 묶지 않음)
    keep = {"keep_next": True, "keep_together": True}
    st += need_pstyle(PF + "풀이", dict(body, color=GRAY, indent=round(g["word_x"] - g["X0"], 2), space_before=g["sb_i"], **keep, **border),
                      label=f"단락 스타일 「{PF}풀이」 — 낱말 줄(테두리 = 상자, 위 오프셋이 머리까지)")
    st += need_pstyle(PF + "예문", dict(body, color=INK, indent=round(g["ex_x"] - g["X0"], 2), space_before=g["sb_e"], **keep, **border))
    st += need_pstyle(PF + "해석", dict(body, color=GRAY, indent=round(g["ex_x"] - g["X0"], 2), space_before=g["sb_k"], **keep, **border))
    st += need_pstyle(PF + "끝 해석", dict(body, color=GRAY, indent=round(g["ex_x"] - g["X0"], 2), space_before=g["sb_k"], keep_together=True, **border))
    return calm(st)


def vv_parts():
    """딱지 「VOCA vs. VOCA」(둥근 면 + 흰 글) · 「·」(글 + 안 보이는 짝 — 그룹은 둘 이상)를 그려 묶는다"""
    if "lab" in G.get("parts", {}):
        return []
    g = measure()
    G["parts"] = {}
    lab = g["lab"]
    st = [S("「VOCA vs. VOCA」 딱지 그룹 — 둥근 면 · 흰 글", 1300)]
    st += box(PX, PY, round(lab["w"], 2), round(g["lab_h"], 2), LAB_F, label="딱지 면", radius=g["lab_r"])
    st += part_text(dict(g["lt"], text=g["lt"]["text"].strip()), round(g["lt_dx"], 2), round(g["lt_db"], 2), ELICE, 700,
                    label="딱지 글 — Elice DX Neolli Bold(겹침 0.94)")
    G["parts"]["lab"], s2 = group_part(2, lab["w"], g["lab_h"], "「VOCA vs. VOCA」 딱지")
    st += s2
    st += [S("「·」 그룹 — 낱말 앞 점(글 + 안 보이는 짝)", 1300)]
    b = g["bul"]
    st += box(PX, PY, 1.6, 3.2, "#ffffff", alpha=0, label="안 보이는 짝(불투명 0)")
    st += part_text(dict(b, text="·"), 0, BUL_DB, NOTO, 400, label="「·」 — 보라 6pt")
    G["parts"]["bul"], s3 = group_part(2, 1.6, 3.2, "「·」")
    return st + s3


def vv_frame(pno, head):
    """쪽 글상자 — 첫 단락(머리)의 기준선이 원본 첫 머리 기준선에"""
    g = measure()
    bb = boxes(pno)
    base0 = bb[0]["hd"][0]["base"]
    top = round(top_of(base0, 7.0, PRE, 700, g["Lh"]), 2)
    st = text(round(g["X0"], 2), top, round(g["W"], 2), round(BOT - top, 2),
              "머리 뜻\nword 낱말 풀이\nExample sentence comes here.\n예문 해석", 7.0, HEAD_C, font=PRE, weight=700, leading=g["Lh"],
              first=(PRE, 700, 7.0, g["Lh"]), auto="", label="VOCA vs. VOCA 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기")
    if head:
        st += slot(VV, label="자리 — VOCA vs. VOCA(레코드 = 비교 묶음 하나, 원고 차례대로 한 줄기)")
        st += [slot_style(n, PF + n) for n in ("머리", "풀이", "예문", "해석", "끝 해석")]
        st += [S("낱말 — 풀이 단락 첫머리에 붙는다(굵은 7pt, 뒤 공백)", 900)] + slot_inline("낱말", PF + "낱말", " ")
        st += [S("딱지 — 머리 필드 앞 고정 개체(사용자 정의 — 텍스트 프레임 가장자리 · 라인(기준선))", 1000)]
        st += slot_anchor("머리", G["parts"]["lab"], "custom", "start", xref="frame", yref="baseline",
                          x=round(g["lab"]["x"] - g["X0"], 2), y=round(g["lab_y"], 2))
        st += [S("「·」 — 풀이 필드 앞 고정 개체(사용자 정의)", 1000)]
        st += slot_anchor("풀이", G["parts"]["bul"], "custom", "start", xref="frame", yref="baseline",
                          x=round(g["bul_x"] - g["X0"], 2), y=-BUL_DB)
    st += thread(VV, head)
    sp = fspans(pno)
    ebody(pno, [s for s in sp if bb[0]["b"]["y"] < s["base"] < bb[-1]["b"]["y"] + bb[-1]["b"]["h"]], "VOCA vs. VOCA 상자")
    return st


def vv_records(pno):
    out = []
    for x in boxes(pno):
        rec = [["머리", join(x["hd"])]]
        cur = None
        for k, _, r in x["rows"]:
            if k == "item":
                w = [s for s in r if s["size"] == 7.0]
                rec += [["낱말", join(w)], ["풀이", join([s for s in r if s["size"] == 6.0 and s["x"] > w[-1]["x1"]])]]
                cur = None
            elif cur is not None and cur[0] == k:                         # 꺾인 줄 — 같은 단락에
                cur[1].append(r)
            else:
                cur = [k, [r]]
                rec.append(cur)
        for f in rec:
            if isinstance(f[1], list):
                f[0] = {"ex": "예문", "ko": "해석"}[f[0]]
                f[1] = runs(f[1])
        if rec[-1][0] == "해석":                                          # 레코드 끝 해석 — 다음 상자와 묶지 않는 자리
            rec[-1][0] = "끝 해석"
        out.append(rec)
    return out


def vv_first(lp=152):
    st = pg_new(lp, f"⑨ VOCA vs. VOCA · 첫 펼침면 — 원본 {lp}쪽(왼쪽)", name="VOCA vs. VOCA · 첫 펼침면")
    st += vv_styles()
    st += vv_parts()
    st += frame_part_left(lp)
    st += vv_frame(lp, True)
    st += done("VOCA vs. VOCA 첫 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑨ VOCA vs. VOCA · 첫 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += vv_frame(lp + 1, False)
    st += done("VOCA vs. VOCA 첫 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(VV, []).extend(vv_records(lp) + vv_records(lp + 1))
    return st


def vv_body(lp=154):
    head = VV not in CONTENT
    st = pg_new(lp, f"⑩ VOCA vs. VOCA · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="VOCA vs. VOCA · 본문 펼침면")
    st += vv_styles()
    st += vv_parts()
    st += frame_body_left(lp)
    st += vv_frame(lp, head)
    st += done("VOCA vs. VOCA 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑩ VOCA vs. VOCA · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_body_right(lp + 1)
    st += vv_frame(lp + 1, False)
    st += done("VOCA vs. VOCA 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(VV, []).extend(vv_records(lp) + vv_records(lp + 1))
    return st


FACES = {9: (vv_first,), 10: (vv_body,)}


if __name__ == "__main__":
    import json
    g = measure()
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in g.items() if k not in ("lab", "lt", "bul")}, ensure_ascii=False))
    r = vv_records(152)
    print(json.dumps(r[0], ensure_ascii=False))
    print(len(r), [len(x) for x in r], [len(x) for x in vv_records(155)])
