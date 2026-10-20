"""상일보카 — 14 정답 첫 면(견본 244쪽, 1쪽 면) · 15 정답 · 본문 펼침면(견본 246 · 247쪽).
쪽 틀: 얇은 띠(회색) + 띠 아래 줄 — 첫 면만 그 위에 높은 띠 · 덧띠(28%) · 번호표(흰 칠 + 선) · 「정답」.
꼬리: 왼쪽 = 쪽 번호 | 책 이름(common.foot_left), 오른쪽 = 「정답」(이 면 고정 글) | 쪽 번호. 옆 탭 · 원 번호표 없음.

정답 = 한 줄기 글(흐름 자리 ENTRY) — 쪽마다 글상자 하나(단 왼쪽 18.99 · 폭 110), 글 잇기로 이어 흐른다(face_pyo.py 와 같은 짜임).
레코드 하나 = Day 하나 = [[자리, 글], …] 차례대로:
  ["Day", "Day 31"] · ["구역 첫", "A"] · ["A 줄", 낱말 : 뜻 줄들] · ["구역", "B"] · ["3단 줄", 줄들] · ["구역", "C"] · ["3단 줄", …] · ["구역", "D"] · ["3단 줄", …]
  A 줄 = 항목마다 한 단락 「번호⇥낱말 : 뜻」(낱말은 꾸밈 조각 {"t", "cs": "정답·낱말"}), 단락 사이 \n.
  3단 줄 = 원본 한 줄마다 한 단락, 칸 셋을 탭으로 — 칸 = 「번호⇥답」 · 단 안에서 꺾인 줄은 「⇥이어지는 글」 · 빈 칸은 「⇥」.
  번호 색(회청)은 원고가 아니라 GREP 스타일(템플릿).
단락 스타일(정답·Day · 정답·구역 첫 · 정답·A 줄 · 정답·구역 · 정답·3단 줄) · 문자 스타일(정답·낱말 · 정답·번호) — 값은 원본 244 · 245 · 246쪽에서 잼.
서체(fontmatch.py, 글자마다 겹침): 정답 13pt Elice DX Neolli 700 0.97 · 꼬리 「정답」 Elice 500 0.94 · 구역 글자 Noto Sans CJK KR 700 0.95~0.98 ·
  번호 Noto 500 0.95 · 뜻(한글) Noto 400 0.96(Pretendard 400 0.96 — 영문 낱말이 Noto 쪽이 닮아 Noto) ·
  원고 글(가장 닮은 것): Day 31 Elice 700 0.89~0.90 · 낱말 Noto 500 0.74~0.80 · B · C 답 Noto 400 0.75.

허용(책에서 손보기 — 있는 기능으로 원본과 똑같이 안 되는 곳):
  1. 3단 구역(B · C · D) — 편집기에 단락 「단 걸치기 · 단 분할」이 없어 한 줄기 안에서 1단(A)과 3단을 섞을 수 없다. 탭 세 칸(4.0 · 38.34 · 42.34 · 76.67 · 80.67mm)으로
     줄을 짠다 → 원고가 원본 줄 차례(줄마다 왼쪽 · 가운데 · 오른쪽 칸)로 와야 하고, 단 안에서 꺾이는 D 항목은 원고에서 줄을 나눠 보낸다(「⇥이어지는 글」).
     원본은 구역마다 단 균형 맞추기로 위→아래 · 왼쪽→오른쪽 차례 — 원고 쪽에서 그 차례를 줄로 바꿔 보내야 같다. 칸 글이 단 폭(33.3mm)을 넘으면 다음 칸과 겹친다.
     쪽이 넘어가면 원본은 그 쪽 몫만 다시 균형을 맞춘다(244 → 245 D) — 탭 줄은 그대로 이어진다.
  2. 구역 사이 점선(0.1mm 네모 점 555개, 0.165mm 간격, #d2d5db) — 단락 경계선에 점선 모양이 없어 같은 색 실선(0.1mm)으로. 원본보다 조금 진해 보인다.
  3. 번호 색 GREP — 편집기는 탭을 칸(글 조각)으로 바꾼 뒤 GREP 를 돌려 「⇥」를 못 본다. 「다른 글 바로 뒤가 아닌 1~2자리 수로 끝나는 조각」
     (?<![ \\w.])\\d{1,2}(?=\\t|$) 으로 번호 칸만 잡는다(탭이 글에 남는 인디자인에서도 같게 맞는 꼴).
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
from entries import spans as _esp, lines as _lines, text_of as _text_of
from face_pyo import fb, MMPT, X0, W0, BOT, Eslot

ENTRY = "Day+구역 첫+A 줄+구역+3단 줄+끝 줄"
PF = "정답·"                                                            # 스타일 이름 앞붙이 — 한 책에 다른 면 스타일과 같이 있다
HEADC, NUMC, INKC, WORDC = "#5a646e", "#96a0ab", "#4d4d4d", "#000000"
COLS = (18.99, 57.33, 95.66)                                           # 3단 칸 왼쪽(번호) — 244 · 246쪽 모두 같다
NUM_W = 4.0                                                             # 번호 → 답 글 시작 (22.99 − 18.99)
TABS3 = [round(c - X0 + d, 2) for c in COLS for d in (0, NUM_W)][1:]  # 4.0 · 38.34 · 42.34 · 76.67 · 80.67
ROW_L = 8.2                                                             # 줄 사이 2.893mm(244쪽 A 25줄 69.42mm / 24) = 8.2pt
# 단락 스타일 — (서체, 굵기, 크기, 행간 pt, 색)
P = {"Day": (ELICE, 700, 7.0, 8.4, HEADC), "구역 첫": (NOTO, 700, 6.0, 7.2, HEADC), "구역": (NOTO, 700, 6.0, 7.2, HEADC),
     "A 줄": (NOTO, 400, 5.6, ROW_L, INKC), "3단 줄": (NOTO, 400, 5.6, ROW_L, INKC), "끝 줄": (NOTO, 400, 5.6, ROW_L, INKC)}
# 단락 앞 공백 — 원본 기준선 사이(앞 단락 끝 줄 → 이 단락 첫 줄, mm)와 그 앞에 오는 단락
GAP = {"구역 첫": ("Day", 4.40),                                        # 244: 34.34 → 38.74 · 246: 12.34 → 16.74
       "A 줄": ("구역 첫", 4.10), "3단 줄": ("구역", 4.10),               # 38.74 → 42.84 · 118.64 → 122.74
       "구역": ("3단 줄", 6.38),                                        # 112.26 → 118.64 · 151.68 → 158.06 · 185.32 → 191.70 (A 끝 줄 뒤도 같다)
       "Day": ("3단 줄", 7.01)}                                          # 245: D 끝 줄 22.80 → Day 32 29.81
CS = {"낱말": {"font": NOTO, "weight": 500, "color": WORDC},            # A · D 의 낱말(검정) — 원고 꾸밈 조각
      "번호": {"font": NOTO, "weight": 500, "color": NUMC}}             # 항목 번호(회청) — GREP
NUM_RE = r"(?<![ \w.])\d{1,2}(?=\t|$)"


def styles():
    st = []
    for n, props in CS.items():
        st += need_cstyle(PF + n, props)
    for n, (f, w, s, L, c) in P.items():
        v = {"font": f, "weight": w, "size": s, "leading": L, "color": c}
        if n in GAP:
            prev, d = GAP[n]
            pf, pw, ps, pL = P[prev][:4]
            v["space_before"] = max(round(d - (pL / MMPT - fb(pf, pw, ps, pL)) - fb(f, w, s, L), 2), 0)
        if n in ("A 줄", "3단 줄"):
            v["space_same"] = 0                                          # 같은 자리 단락끼리 = 행간만
            # Day 하나 = 통째로(원본 246 → 247: Day 34 가 246 아래에 다 안 들어가 247 맨 위로) — 줄마다 다음 단락과 함께 유지 · 단락 분리 금지,
            # Day 마지막 줄(끝 줄)만 풀어 둔다. 상자 맨 위 Day 가 한 쪽을 넘으면(244 Day 31) 그때는 쪽 끝에서 나뉜다(인디자인과 같다)
            v.update(keep_next=True, keep_together=True)
        if n == "끝 줄":                                                 # Day 마지막 줄 — 3단 줄과 같은 모양, 다음 Day 와 묶지 않는다
            v["space_before"] = 0
        if n == "A 줄":                                                  # 번호 내어쓰기 — 꺾인 줄은 낱말 자리(4.0mm)에
            v.update(indent=NUM_W, indent_first=-NUM_W, tabs=[{"at": NUM_W}])
        if n in ("3단 줄", "끝 줄"):
            v["tabs"] = [{"at": t} for t in TABS3]
        if n in ("Day", "구역 첫", "구역"):                               # 머리는 다음 줄과 함께(단 · 쪽 끝에 혼자 남지 않게)
            v["keep_next"] = True
        if n == "Day":                                                   # Day 위 실선 — 244: 선 30.96~31.16, 기준선 34.34
            v["rule_above"] = {"w": round(0.2 * MMPT, 3), "color": HEADC, "offset": 3.18}
        if n == "구역":                                                  # 구역 사이 점선 → 실선(허용 2) — 244: 점 114.90~115.00, B 기준선 118.64
            v["rule_above"] = {"w": round(0.1 * MMPT, 3), "color": "#d2d5db", "offset": 3.64}
        st += need_pstyle(PF + n, v)
    return st


# ── 원고 읽기 — 원본 쪽들의 정답을 Day 레코드로 ─────────────────────────────────────────────
def _pieces(row):
    """글 조각들 → [(글, 문자 스타일 | None)] — 검정 = 정답·낱말, 조각 사이 0.4mm 넘게 벌면 빈칸"""
    out = []
    for k, s in enumerate(row):
        t = s["text"]
        if k and s["x"] - row[k - 1]["x1"] > 0.4 and not t.startswith(" ") and not out[-1][0].endswith(" "):
            t = " " + t
        out.append((t, PF + "낱말" if s["color"] == WORDC else None))
    return out


def _rich(pieces):
    """조각 목록 → 원고 값(글 하나, 또는 꾸밈 조각 목록). 꾸밈 조각 끝 빈칸은 뒤 글로 넘긴다"""
    merged = []
    for t, cs in pieces:
        t = re.sub(r" {2,}", " ", t)
        if merged and merged[-1][1] == cs:
            merged[-1][0] += t
        else:
            merged.append([t, cs])
    for i, (t, cs) in enumerate(merged):
        if cs and t.endswith(" ") and i + 1 < len(merged):
            merged[i][0] = t.rstrip()
            merged[i + 1][0] = " " + merged[i + 1][0].lstrip(" ")
        merged[i][0] = re.sub(r" *([\t\n]) *", r"\1", merged[i][0])
    if not any(cs for _, cs in merged):
        return "".join(t for t, _ in merged)
    return [{"t": t, "cs": cs} if cs else t for t, cs in merged if t]


def _col(x):
    return max(i for i, c in enumerate(COLS) if x >= c - 0.5)


def dap_records(pages):
    """원본 쪽들 → Day 레코드 목록. 쪽 첫머리가 앞 Day 의 이어짐이면(245쪽 D) 앞 레코드에 잇는다"""
    recs, cur = [], None                                                 # cur = 지금 쌓는 줄 자리 [자리, [조각 …]]
    for pno in pages:
        sp = [s for s in _esp(REF[pno - 1]) if 8 < s["base"] < 200 and s["size"] < 10]
        for row in _lines(sp):
            s0 = row[0]
            if s0["color"] == HEADC and s0["size"] == 7.0:              # Day 머리
                recs.append([["Day", _text_of(row)]])
                cur = None
                continue
            if s0["color"] == HEADC and s0["size"] == 6.0:              # 구역 글자(A · B · C · D)
                rec = recs[-1]
                first = not any(f[0] in ("구역 첫", "구역") for f in rec)
                rec.append(["구역 첫" if first else "구역", s0["text"].strip()])
                cur = ["A 줄" if first else "3단 줄", []]
                rec.append(cur)
                continue
            if cur is None:                                              # 처음 쪽이 Day 가운데서 시작 — 이 면 원고에는 넣지 않는다
                continue
            if cur[0] == "A 줄":
                if s0["color"] == NUMC and s0["x"] < COLS[0] + 0.5:      # 새 항목
                    if cur[1]:
                        cur[1].append(("\n", None))
                    cur[1] += [(s0["text"].strip() + "\t", None)] + _pieces(row[1:])
                else:                                                    # 꺾인 줄 — 앞 항목에 빈칸으로 잇는다
                    cur[1] += [(" ", None)] + _pieces(row)
                continue
            cells = []
            for i in range(3):
                cs_ = [s for s in row if _col(s["x"]) == i]
                if not cs_:
                    cells.append([("\t", None)])
                elif cs_[0]["color"] == NUMC and abs(cs_[0]["x"] - COLS[i]) < 0.5:
                    cells.append([(cs_[0]["text"].strip() + "\t", None)] + _pieces(cs_[1:]))
                else:                                                    # 단 안에서 꺾인 줄
                    cells.append([("\t", None)] + _pieces(cs_))
            while len(cells) > 1 and cells[-1] == [("\t", None)]:
                cells.pop()
            if cur[1]:
                cur[1].append(("\n", None))
            for i, c in enumerate(cells):
                cur[1] += ([("\t", None)] if i else []) + c
    for rec in recs:                                                     # 마지막 3단 줄의 끝 줄 → 「끝 줄」(줄이 둘 이상일 때 — 하나뿐이면 구역 바로 뒤라 간격이 다르다)
        f = rec[-1]
        if f[0] == "3단 줄" and ("\n", None) in f[1]:
            k = len(f[1]) - 1 - f[1][::-1].index(("\n", None))
            rec.append(["끝 줄", f[1][k + 1:]])
            f[1] = f[1][:k]
        for f in rec:
            if isinstance(f[1], list):
                f[1] = _rich(f[1])
    return recs


# ── 쪽 틀 ───────────────────────────────────────────────────────────────────────────────
def thin_band(pno):
    el = els(pno)
    band, bline = find(el, "rect", -3, -3), find(el, "rect", -3, 4.8)
    st = rbox(band["x"], band["y"], band["w"], band["h"], band["fill"], label="얇은 띠")
    return st + rbox(bline["x"], bline["y"], bline["w"], bline["h"], bline["fill"], label="띠 아래 줄")


def frame_dap_first(pno):
    """정답 첫 면 — 얇은 띠 · 띠 아래 줄(앞) 위에 높은 띠(왼쪽 아래 곡선) · 덧띠(28%) · 번호표 옆 그림자 · 번호표 · 「정답」 · 왼쪽 꼬리"""
    sp, dr = spans(pno), ref_draws(pno)
    top = [e for e in dr if e["y"] < 8 and e["h"] > 8]
    band = max((e for e in top if e["alpha"] == 100 and e["w"] > 100), key=lambda e: e["w"])
    over = next(e for e in top if e["alpha"] < 100)
    tri = next(e for e in dr if e["w"] < 3 and e["h"] > 6 and e["y"] < 10)
    badge = next(e for e in dr if e["fill"] == "#ffffff" and e["y"] < 10 and e["w"] > 10)
    stroke = next(e for e in dr if e["stroke"] and not e["fill"] and abs(e["x"] - badge["x"]) < 0.3)
    st = [S("정답 첫 면 틀 — 얇은 띠 위에 높은 띠 · 덧띠 · 번호표", 1200)]
    st += thin_band(pno)
    st += ref_shape(band, fill=band["fill"], label="높은 띠(왼쪽 아래 곡선 — 얇은 띠 위에)")
    st += ref_shape(over, fill=over["fill"], alpha=over["alpha"], label=f"덧띠 — 불투명 {over['alpha']}%", measure=False)
    Ebox(over["x"], over["y"], over["w"], over["h"], mix(over["fill"], band["fill"], over["alpha"] / 100))   # 보이는 색 = 높은 띠 위에 겹친 색
    st += ref_shape(tri, fill=tri["fill"], label="번호표 옆 그림자")
    st += ref_shape(badge, fill="#ffffff", stroke=stroke["stroke"], sw=stroke["sw"], label="번호표(흰 칠 · 선 · 아래 두 귀 둥글게)")
    ttl = sp_line(sp, lambda s: s["size"] == 13.0 and s["base"] < 25)
    st += T(dict(ttl, text="정답"), ELICE, 700, label="정답 — 이 면 고정 글 · Elice DX Neolli Bold (겹침 0.97)")
    st += foot_left(pno, sp)
    return st


def frame_dap_left(pno):
    st = [S("정답 본문 펼침면 왼쪽 틀 — 얇은 띠", 1200)] + thin_band(pno)
    return st + foot_left(pno, spans(pno))


def frame_dap_right(pno):
    """오른쪽 — 얇은 띠 · 꼬리 「정답 | 쪽 번호」(정답 = 이 면 고정 글)"""
    sp = spans(pno)
    st = [S("정답 본문 펼침면 오른쪽 틀 — 얇은 띠 · 꼬리", 1200)] + thin_band(pno)
    bar = sp_line(sp, lambda s: s["base"] > 200 and s["text"] == "|" and s["x"] > 90)
    nm = sp_line(sp, lambda s: s["base"] > 200 and 90 < s["x"] < bar["x"] and s["size"] == 6.0)
    num = sp_line(sp, lambda s: s["base"] > 200 and s["x"] > bar["x1"] and s["size"] == 6.0)
    st += [S("오른쪽 꼬리 — 정답 · | · 쪽 번호", 1000)]
    st += T(dict(nm, text="정답"), ELICE, 500, label="꼬리 「정답」 — 이 면 고정 글 · Elice DX Neolli Medium (겹침 0.94)")
    st += T(bar, ELICE, 300, label="| — Elice DX Neolli Light")
    st += T(num, ELICE, 700, label="쪽 번호 — 시스템 자리 「쪽 번호」 (오른쪽 맞춤)", w=6, align="right", bind="sys.page_no")
    return st


# ── 정답 글상자(한 줄기) ──────────────────────────────────────────────────────────────────
def story_frame(pno, head):
    """쪽 글상자 — 견본 쪽 첫 단락(Day 머리)의 첫 기준선이 원본 자리에 오게. Day 위 실선이 상자 안에 들게 상자를 4mm 올리고 위 인세트 4mm"""
    sp = spans(pno)
    day = min((s for s in sp if s["size"] == 7.0 and s["color"] == HEADC), key=lambda s: s["base"])
    f, w, s, L, c = P["Day"]
    top = round(top_of(day["base"], s, f, w, L), 2)
    st = text(X0, top, W0, round(BOT - top + 4, 2), "Day 00\nA\n1\t낱말 : 뜻 — 정답이 이 글상자로 흘러 들어온다", s, c, font=f, weight=w, leading=L,
              label="정답 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기", first=(f, w, s, L), auto="")
    st += [F('#side input[data-it="y"]', round(top + fb_shift(f, w, s, L) - 4, 3)), F('#side input[data-a="inset4"]', "4 0 0 0")]
    if head:
        st += slot(ENTRY, label="자리 — 정답(Day 마다 원고 차례대로 한 줄기)")
        for nm in ENTRY.split("+"):
            st.append(slot_style(nm, PF + nm, 450))
        st += grep(0, NUM_RE, PF + "번호", label="GREP 스타일 — 항목 번호(줄 첫머리 · 칸 첫머리 수) 회청")
        st += story_pick(ENTRY, True)
    else:
        st += story_pick(ENTRY, False)
    body = [x for x in sp if top < x["base"] < BOT and x["x"] < 135]
    Eslot(body, "#000000", label="정답")
    return st


def dap_first(pno=244):
    st = pg_new(pno, f"⑭ 정답 첫 면 — 원본 {pno}쪽", name="정답 첫 면")
    st += styles()
    st += frame_dap_first(pno)
    st += story_frame(pno, True)
    st += done("정답 첫 면", f"p{pno}.png")
    CONTENT.setdefault(ENTRY, []).extend(dap_records([pno]))
    return st


def dap_body(lp=246):
    st = pg_new(lp, f"⑮ 정답 · 본문 펼침면 — 원본 {lp}쪽(왼쪽)", name="정답 · 본문 펼침면")
    st += styles()
    st += frame_dap_left(lp)
    st += story_frame(lp, ENTRY not in CONTENT)
    st += done("정답 본문 펼침면 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑮ 정답 · 본문 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_dap_right(lp + 1)
    st += story_frame(lp + 1, False)
    st += done("정답 본문 펼침면 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(ENTRY, []).extend(dap_records([lp, lp + 1]))
    return st


FACES = {14: (dap_first,), 15: (dap_body,)}


if __name__ == "__main__":                                              # 원고 읽기 확인 — python3 face_dap.py <쪽> …
    import json
    print(json.dumps(dap_records([int(a) for a in sys.argv[1:]] or [244]), ensure_ascii=False, indent=1))
