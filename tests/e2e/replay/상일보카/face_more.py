"""상일보카 — 8 more with · 펼침면(견본 150 · 151쪽).
쪽 틀: 왼쪽은 이 파일 frame_part_left(번호표 글이 「DAY」 가 아니라 「PART 1」 — common.frame_first_left 를 본떴다), 오른쪽은 common.frame_first_right.
본문 = 한 줄기 글(흐름 자리 MORE) — 쪽마다 글상자 하나, 글 잇기로 이어 흐른다(face_pyo 와 같은 짜임).

짜임(상자 하나 = 레코드 하나 = 뿌리 하나):
  낱말 줄마다 단락 하나(데이터 필드 「뜻」) — 첫머리에 같은 단락 필드 「낱말 앞」 · 「낱말 뿌리」(굵게) · 「낱말 뒤」 · 「품사」(인라인 고정 텍스트 프레임 = 칩).
  레코드 끝에 단락 「뿌리」(13pt 굵게, 왼쪽 칸 가운데 맞춤, 행간 1pt — 앞 낱말 줄들 옆으로 겹쳐 놓인다) + 고정 개체 「more with」 알약(그룹, 사용자 정의 위치).
  상자 = 「뜻」 단락들의 단락 테두리(잇닿은 같은 값은 한 상자, 모퉁이 둥글게). 「뿌리」 단락은 테두리가 없어 다음 레코드 상자와 갈라진다.
원고 레코드(외부 연동 꼴, 차례대로): [["낱말 앞", "pro"], ["낱말 뿌리", "log"], ["낱말 뒤", "ue"], ["품사", "명"], ["뜻", "1. 머리말, 서막 2. 전조, 발단"], …, ["뿌리", "log"]]
  낱말 줄마다 낱말 앞 · 낱말 뿌리 · 낱말 뒤(빈 것은 뺀다) → 품사(여럿이면 차례로) → 뜻. 뿌리는 레코드 맨 끝.
  한 줄 가운데 품사가 또 나오면(150쪽 pant 「동 숨을 헐떡이다 명 숨참, 헐떡임」) 그 앞 뜻은 「뜻 앞」(같은 단락 필드, 뒤 글자 없음 — 원본 뜻 끝 ~ 칩 틈 0):
  [["낱말 앞", "pant"], ["품사", "동"], ["뜻 앞", "숨을 헐떡이다"], ["품사", "명"], ["뜻", "숨참, 헐떡임"]]

허용(책에서 손보기) — 있는 기능으로 원본과 똑같이 안 되는 곳:
  · 상자 칠 #fbfbfb 없음(테두리만) — 뿌리 단락이 상자 단락들 뒤에 겹쳐 놓이는데, 칠을 넣으면 편집기가 칠을 뿌리 글 위에 그린다(인디자인은 음영이 늘 글 아래).
  · 뿌리 · 알약 자리: 2줄 상자는 상자 · 알약 · 뿌리가 원본 자리, 낱말 줄이 2.7mm 위. 3 · 4줄 상자는 상자가 3.7mm 크고 뿌리 · 알약이 아래쪽(원본은 상자 세로 가운데).
    — 뿌리를 낱말 줄 옆에 놓는 것이 「끝 단락 뒤 행간 1pt 단락」뿐이라 끝 줄 기준으로만 놓인다.
  · 낱말 끝 ~ 품사 칩 틈 0.54mm 없음(낱말 필드 뒤 글자 「없음」 — 굵은 부분이 끝인 낱말이 있어 틈을 줄 필드가 정해지지 않는다) · 칩 폭 0.26mm 좁음(인세트 한 값).
  · 상자가 쪽 끝에 걸리면 원본보다 일찍 다음 쪽으로(3 · 4줄 상자가 커서 150쪽 끝 상자 phan 이 151쪽으로 갈 수 있다).
"""
import os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *                                                    # noqa
import common
from mkpage import _color                                               # noqa: E402
sys.path.insert(0, REPO)
from core.units import render as _render

MMPT = 1 / MM
PRE = "Pretendard"
LINE_C, PILL_C, CHIP_F, BOX_S = "#4d4d4d", "#3f548c", "#e3e5eb", "#d2d5db"
BOT = 197.0                                                             # 본문 글상자 아래 끝(꼬리 위) — face_pyo 와 같다
R_LEAD = 1.0                                                            # 뿌리 단락 행간 pt — 앞 끝 줄 바로 아래에 겹쳐 놓이게(뿌리 기준선이 끝 줄에 가장 가깝게)
PX, PY = 40.0, 110.0                                                    # 고정 개체(그룹)를 그려 묶을 빈 자리 — 쪽 틀을 그리기 전


# ── 공용(face_vv 도 쓴다) ──────────────────────────────────────────────────────────────
def fb(font, weight, size, lead_pt):
    """줄 상자 위 끝 → 첫 기준선(mm) — 크롬 줄 상자(반 행간 + 윗높이)"""
    m = _render.font_metrics(font, weight)
    s, L = size * MM, lead_pt * MM
    return (L - (m["asc"] + m["desc"]) * s) / 2 + m["asc"] * s


def fspans(pno):
    """원본 글 조각(가로) — 첫 글자 기준점 · 끝 글자 오른쪽 · 기준선 · 크기 · 색 · 서체 이름(Type3 번호 — 굵은 부분 가르기)"""
    p, t = REF[pno - 1], REF[pno - 1].trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (1.0, 0.0):
                continue
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                if not ch or sp["size"] < 2 or sp.get("alpha", 255) == 0:
                    continue
                out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM,
                            "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "font": sp["font"],
                            "text": "".join(c["c"] for c in sp["chars"])})
    return out


def rows_of(sps, tol=0.6):
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def join(row):
    """조각들 → 글(조각 사이 틈이 0.4mm 넘으면 빈칸)"""
    t = ""
    for k, s in enumerate(row):
        if k and s["x"] - row[k - 1]["x1"] > 0.4 and not t.endswith(" "):
            t += " "
        t += s["text"]
    t = re.sub(r"(?<![\d.])(\d{1,2}\.)(?=[^\s\d])", r"\1 ", t)          # 뜻 번호 「1.」 뒤 — 원본은 마침표 글자 폭이 넓어 틈이 조각 사이로 안 잡힌다
    return re.sub(r"\s+", " ", t).strip()


def corner(d, h):
    """원본 둥근 상자 경로 d(0~1) 첫 두 점 「M0 a L0 b」 → 모퉁이 크기 mm"""
    v = [float(x) for x in re.findall(r"[-\d.]+", d)[:4]]
    return round(v[3] * h, 2)


def track_of(s, font, weight):
    """원본 글 조각 자간(‰) — common.T 와 같은 셈"""
    if len(s["text"]) < 2:
        return 0
    size = s["size"]
    return round(((s["x1"] - s["x"]) - chrome_extent(font, weight, size, s["text"]) - face(font, weight)[2](s["text"][-1]) * size * MM)
                 / (len(s["text"]) - 1) / (size * MM) * 1000)


def boxes_of(pno):
    """본문 둥근 상자(회색 선) — 위에서부터"""
    return sorted((d for d in ref_draws(pno) if d["stroke"] == BOX_S and d["w"] > 100), key=lambda d: d["y"])


def group_part(n, w, h, what):
    """빈 자리(PX, PY)에 그린 개체 n 개를 범위로 골라 그룹 → 부품(고정 개체로 쓸 그룹), 쪽에서는 지운다(그룹은 라이브러리에 남는다).
    부품 이름은 편집기가 차례로 붙인다(p_1, p_2 …) — 이 대본 판에서 만든 수를 common.PARTN 에 센다(다른 면 파일도 같이 쓰게)"""
    if not hasattr(common, "PARTN"):
        common.PARTN = [0]
    common.PARTN[0] += 1
    pid = f"p_{common.PARTN[0]}"
    return pid, [S("자석 끄기 — 켜 두면 묶을 때 0.5mm 격자로 반올림된다", 1000), {"clickif": {"at": "#tg-snap", "when": "view.snap"}, "wait": 600},
                 S(f"범위로 {n}개를 골라 그룹 — {what}", 1200),
                 {"drag": {"from": {"mm": [PX - 2, PY - 2]}, "to": {"mm": [PX + w + 2, PY + h + 2]}}, "wait": 900},
                 {"js": f"(() => {{ if (sels.size !== {n}) throw new Error('고른 것 ' + sels.size + ' ({n} 이어야)'); return '고른 것 {n}'; }})()"},
                 {"click": "#side #s-group", "wait": 1500},
                 {"until": f"LIB.parts.length && LIB.parts[LIB.parts.length - 1].atoms.length === {n}", "wait": 300},
                 {"js": f"(() => {{ const p = LIB.parts[LIB.parts.length - 1]; if (!p || p.id !== '{pid}') throw new Error('그룹 이름이 {pid} 가 아니라 ' + (p && p.id)); return '그룹 ' + p.id; }})()"},
                 S("쪽의 그룹은 지운다 — 고정 개체로 쓴다", 900), {"key": "Delete", "wait": 900},
                 {"clickif": {"at": "#tg-snap", "when": "!view.snap"}, "wait": 600}]


def part_text(s, dx, dbase, font, weight, label=None):
    """그룹 속 글 — 원본 글 조각을 그룹 왼쪽 위(PX, PY)에서 (dx, dbase) 자리에. 자간은 원본 글자 자리에서"""
    size = s["size"]
    lead = round(size * 1.2, 2)
    top = top_of(PY + dbase, size, font, weight, lead)
    return text(round(PX + dx, 2), round(top, 2), round(s["x1"] - s["x"] + 3, 1), round(lead * MM + 0.5, 2), s["text"], size, s["color"], label=label,
                font=font, weight=weight, leading=lead, track=track_of(s, font, weight) or None, auto="")


def frame_part_left(pno):
    """첫 펼침면 왼쪽(구간 첫 쪽) — 높은 띠 · 덧띠 · 번호표 · 그림자 삼각 · 「PART 1」(고정 글) · 구간 번호(원고 자리 「구간 번호」) · 머리 제목(이 면 고정 글) · 왼쪽 꼬리.
    common.frame_first_left 를 본떴다 — 번호표 글이 「DAY」 가 아니라 「PART 1」"""
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
    part = sp_line(sp, lambda s: s["text"].replace(" ", "") == "PART1" and s["base"] < 20)
    num = sp_line(sp, lambda s: s["size"] > 15 and s["base"] < 25)
    ttl = sp_line(sp, lambda s: s["size"] == 12.0 and s["base"] < 20)
    st += T(dict(part, text="PART 1"), ELICE, 700, label="PART 1 — Elice DX Neolli Bold (겹침 0.95) · 고정 글")
    st += T(num, BEBAS, 700, label="구간 번호 — 원고 자리 「구간 번호」 (가운데 맞춤 · 맞는 서체 없음, 가장 닮은 Bebas Neue Bold — DAY 번호와 같다)",
            slot_name="구간 번호", temp="00", align="center", w=round(badge["w"], 2))
    st += [F('#side input[data-it="x"]', round(badge["x"], 2))]
    CONTENT.setdefault("구간 번호", []).append(num["text"])
    st += T(ttl, ELICE, 700, label="머리 제목 — Elice DX Neolli Bold (겹침 0.96) · 이 면 고정 글", w=60)
    st += foot_left(pno, sp)
    return st


THREAD = {}                                                             # 흐름 자리 → 그 이야기 이름(편집기가 붙인 「이야기N」)


def thread(bind, head):
    """글 잇기 — common.story_pick(이 문서의 이야기 차례로 센다)"""
    return story_pick(bind, head)


def ebody(pno, sps, label):
    """원고 칸 전체를 원고 요소 하나로 — 원고는 「들어갔나」만 본다(절차 합격 기준, face_pyo Eslot 과 같은 셈)"""
    x0, x1 = min(s["x"] for s in sps), max(s["x1"] for s in sps)
    y0, y1 = min(s["base"] - s["size"] * MM * 0.95 for s in sps), max(s["base"] + s["size"] * MM * 0.3 for s in sps)
    E({"id": f"w{len(ELEMS[len(PAGES)])}", "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
       "color": "#000000", "see": "#000000", "ctol": 40, "pad": 1.0, "search": 1.0, "text": label, "size": sps[0]["size"], "원고": True})


# ── 8 more with ────────────────────────────────────────────────────────────────────
MORE = "낱말 앞+낱말 뿌리+낱말 뒤+품사+뜻 앞+뜻+뿌리"
PF = "모어·"                                                            # 스타일 이름 앞붙이
G = {}


def measure():
    """원본 150 · 151쪽에서 잰다 — 2줄 상자(가장 많다)가 원본 자리에 오게"""
    if G:
        return G
    boxes, two, lines_gap, gaps = [], [], [], []
    for pno in (150, 151):
        sp, dr = fspans(pno), ref_draws(pno)
        bx = boxes_of(pno)
        for k, b in enumerate(bx):
            inn = [s for s in sp if b["y"] < s["base"] < b["y"] + b["h"]]
            pill = next(d for d in dr if d["stroke"] == PILL_C and not d["fill"] and b["y"] < d["y"] < b["y"] + b["h"])
            ptxt = next(s for s in inn if s["color"] == PILL_C and s["size"] > 5.2)
            root = [s for s in inn if s["size"] == 13.0]
            ln = [r[0]["base"] for r in rows_of([s for s in inn if s["size"] == 6.0 and s["x"] > 50])]
            chips = [d for d in dr if d["fill"] == CHIP_F and b["y"] < d["y"] < b["y"] + b["h"]]
            boxes.append(dict(b=b, pill=pill, ptxt=ptxt, root=root, lines=ln, chips=chips, inn=inn))
            lines_gap += [y - x for x, y in zip(ln, ln[1:])]
            if k:
                gaps.append(b["y"] - (bx[k - 1]["y"] + bx[k - 1]["h"]))
    two = [b for b in boxes if len(b["lines"]) == 2]
    med = statistics.median
    b0 = boxes[0]
    word = min(s["x"] for b in boxes for s in b["inn"] if s["size"] == 6.0 and s["color"] == "#000000")
    chip_txt = [s for b in boxes for s in b["inn"] if s["size"] == 5.0]
    ch = [(d, min((s for s in chip_txt if d["x"] < s["x"] < d["x"] + d["w"]), key=lambda s: abs(s["base"] - d["y"] - 2.3))) for b in boxes for d in b["chips"]]
    G.update(
        X0=b0["b"]["x"], W=b0["b"]["w"], sw=b0["b"]["sw"], r=corner(b0["b"]["d"], b0["b"]["h"]),
        L=med(lines_gap), IND=word - b0["b"]["x"],
        cx=med((b["root"][0]["x"] + b["root"][-1]["x1"]) / 2 for b in boxes),
        pill_x=b0["pill"]["x"], pill_w=b0["pill"]["w"], pill_h=med(b["pill"]["h"] for b in boxes), pill_sw=b0["pill"]["sw"],
        pill_y=med(b["pill"]["y"] - b["root"][0]["base"] for b in boxes),                     # 알약 위 끝 − 뿌리 기준선
        ptxt=b0["ptxt"], ptxt_dx=b0["ptxt"]["x"] - b0["pill"]["x"], ptxt_db=med(b["ptxt"]["base"] - b["pill"]["y"] for b in boxes),
        top_root=med(b["b"]["y"] - b["root"][0]["base"] for b in two),                       # 상자 위 끝 − 뿌리 기준선(2줄 상자)
        bot_root=med(b["b"]["y"] + b["b"]["h"] - b["root"][0]["base"] for b in two),         # 상자 아래 끝 − 뿌리 기준선
        gap=med(gaps),
        chip_r=corner(ch[0][0]["d"], ch[0][0]["h"]), chip_h=med(d["h"] for d, _ in ch),
        chip_top=med(d["y"] - s["base"] for d, s in ch),                                     # 칩 위 끝 − 칩 글 기준선
        chip_rise=med(r_[0]["base"] - s["base"] for b in boxes for r_ in rows_of([x for x in b["inn"] if x["size"] == 6.0 and x["x"] > 50])
                      for s in chip_txt if abs(s["base"] - r_[0]["base"]) < 0.6),               # 낱말 기준선 − 칩 글 기준선(칩 글이 위)
        boxes=boxes)
    g = G
    Lpt = g["L"] * MMPT
    fbL, fbR = fb(NOTO, 400, 6.0, Lpt), fb(NOTO, 700, 13.0, R_LEAD)
    g["Lpt"], g["fbL"], g["fbR"] = round(Lpt, 2), fbL, fbR
    g["delta"] = (g["L"] - fbL) + fbR                                     # 뿌리 기준선 − 끝 낱말 줄 기준선(뿌리 단락이 끝 줄 바로 아래)
    g["top_L1"] = -(g["L"] + g["delta"] + g["top_root"])                  # 2줄 상자: 첫 낱말 줄 기준선 − 상자 위 끝
    o = g["sw"] / 2
    g["ot"] = round(g["top_L1"] + o - fbL, 2)                             # 테두리 위 오프셋 — 첫 줄 줄 상자 위에서(선 바깥 끝까지)
    g["ob"] = round(g["delta"] + g["bot_root"] + o - (g["L"] - fbL), 2)   # 테두리 아래 오프셋 — 끝 줄 줄 상자 아래에서
    nxt = g["bot_root"] + g["gap"] + g["top_L1"]                          # 뿌리 기준선 → 다음 상자 첫 줄 기준선
    g["sb"] = round(nxt - (R_LEAD * MM - fbR) - fbL, 2)
    g["ir"] = round(g["W"] - 2 * (g["cx"] - g["X0"]), 2)                  # 뿌리 가운데 맞춤 — 왼쪽 칸 가운데(원본 뿌리 가운데 x)
    inset = (g["chip_h"] - 5.0 * MM) / 2                                  # 칩 = 인라인 고정 텍스트 프레임(줄 높이 1 · 인세트) — 높이를 원본에
    m = _render.font_metrics(NOTO, 500)
    b_in = 5.0 * MM * (1 + m["asc"] - m["desc"]) / 2                      # 프레임 위 끝 → 칩 글 기준선(인세트 안)
    g["chip_inset"], g["chip_y"] = round(inset, 2), round(g["chip_rise"], 2)
    g["chip_err"] = round(-(inset + b_in) - g["chip_top"], 2)
    return g


def more_styles():
    g = measure()
    st = []
    st += need_cstyle(PF + "낱말", {"color": "#000000"})
    st += need_cstyle(PF + "낱말 뿌리", {"weight": 700, "color": "#000000"})                 # 굵은 부분 — Noto Sans CJK KR Bold(겹침 0.83, 가장 닮음)
    st += need_cstyle(PF + "품사", {"font": NOTO, "weight": 500, "size": 5.0, "color": PILL_C})  # Noto Sans CJK KR Medium(0.92 — Pretendard 500 0.93 보다 칩 세로 자리가 원본에 맞는다)
    st += need_cstyle(PF + "뜻 사이", {"track": 630})                                         # 뜻 번호 앞 틈 1.87mm(보통 0.54) — 그 공백에 자간
    sw_pt = round(g["sw"] * MMPT, 3)
    border = {"border": sw_pt, "border_color": BOX_S, "border_r": g["r"], "border_ot": g["ot"], "border_ob": g["ob"],
              "border_ol": round(g["sw"] / 2, 3), "border_or": round(g["sw"] / 2, 3)}
    st += need_pstyle(PF + "뜻", dict({"font": NOTO, "weight": 400, "size": 6.0, "leading": g["Lpt"], "color": LINE_C, "indent": round(g["IND"], 2),
                                      "space_before": g["sb"], "space_same": 0, "keep_next": True}, **border),
                      label=f"단락 스타일 「{PF}뜻」 — 낱말 줄(테두리 = 상자, 잇닿은 줄은 한 상자)")
    st += need_pstyle(PF + "뿌리", {"font": NOTO, "weight": 700, "size": 13.0, "leading": R_LEAD, "color": "#000000", "align": "center",
                                    "indent_right": g["ir"]},
                      label=f"단락 스타일 「{PF}뿌리」 — 행간 1pt · 왼쪽 칸 가운데(테두리 없음 — 다음 상자와 갈라진다)")
    return st


def pill_part():
    """「more with」 알약 — 둥근 선 상자 + 글을 그려 묶는다(뿌리 필드의 고정 개체)"""
    if "pill" in G:
        return []
    g = measure()
    st = [S("「more with」 알약 그룹 — 둥근 선 상자 · 글", 1300)]
    st += box(PX, PY, round(g["pill_w"], 2), round(g["pill_h"], 2), None, label="알약 상자(칠 없음 · 선)", radius=round(g["pill_h"] / 2, 2))
    st += [{"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550}]
    st += _color("stroke.color", PILL_C) + [F('#side input[data-a="stroke.w"]', round(g["pill_sw"] * MMPT, 3))]
    st += part_text(g["ptxt"], round(g["ptxt_dx"], 2), round(g["ptxt_db"], 2), ELICE, 500, label="알약 글 — Elice DX Neolli Medium(겹침 0.92)")
    pid, s2 = group_part(2, g["pill_w"], g["pill_h"], "「more with」 알약")
    G["pill"] = pid
    return st + s2


def more_frame(pno, head):
    """쪽 글상자 — 첫 상자 위 끝이 원본 첫 상자 위 끝에 오게(2줄 상자 기준 첫 줄 기준선 = 상자 위 + top_L1)"""
    g = measure()
    sp = fspans(pno)
    bx = boxes_of(pno)
    base0 = bx[0]["y"] + g["top_L1"]
    top = round(top_of(base0, 6.0, NOTO, 400, g["Lpt"]), 2)
    st = text(round(g["X0"], 2), top, round(g["W"], 2), round(BOT - top, 2), "pro log ue 명 뜻 — 낱말 줄이 이 글상자로 흘러 들어온다\nlog", 6.0, LINE_C,
              font=NOTO, weight=400, leading=g["Lpt"], first=(NOTO, 400, 6.0, g["Lpt"]), auto="",
              label="낱말 줄 글상자 — 한 줄기(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기")
    if head:
        st += slot(MORE, label="자리 — more with(레코드 = 뿌리 하나, 원고 차례대로 한 줄기)")
        st += [slot_style("뜻", PF + "뜻"), slot_style("뿌리", PF + "뿌리")]
        st += [S("낱말 · 품사 — 뜻 단락 첫머리에 붙는다(낱말 세 조각은 붙여서, 품사는 칩 + 엔 공백)", 900)]
        st += slot_inline("낱말 앞", PF + "낱말", "") + slot_inline("낱말 뿌리", PF + "낱말 뿌리", "") + slot_inline("낱말 뒤", PF + "낱말", "")
        st += slot_inline("품사", PF + "품사", " ")
        st += [S("뜻 앞 — 한 줄 가운데 품사가 또 나올 때 그 앞 뜻(같은 단락, 뒤 글자 없음 — 다음 칩이 바로 붙는다)", 900)] + slot_inline("뜻 앞", None, "")
        st += [S("품사 칩 — 인라인 고정 텍스트 프레임(칠 · 모퉁이 · 인세트 · Y 오프셋)", 900)]
        st += color_p("slot_fmt.품사.frame.fill", CHIP_F)
        st += [P_("slot_fmt.품사.frame.r", g["chip_r"]), P_("slot_fmt.품사.frame.inset", g["chip_inset"]), P_("slot_fmt.품사.frame.y", g["chip_y"])]
        st += [S("「more with」 알약 — 뿌리 필드 앞 고정 개체(사용자 정의 — 텍스트 프레임 가장자리 · 라인(기준선))", 1000)]
        st += slot_anchor("뿌리", G["pill"], "custom", "start", xref="frame", yref="baseline",
                          x=round(g["pill_x"] - g["X0"], 2), y=round(g["pill_y"], 2))
        st += grep(0, r" (?=\d{1,2}\. )", PF + "뜻 사이", label="GREP 스타일 — 뜻 번호 앞 공백 넓게(자간)")
    st += thread(MORE, head)
    body = [s for s in sp if bx[0]["y"] < s["base"] < bx[-1]["y"] + bx[-1]["h"] and s["x"] < 135]
    ebody(pno, body, "more with 상자")
    return st


def more_records(pno):
    """원본 쪽 → 레코드(상자마다) — 낱말 줄: 검은 6pt 조각(뿌리와 같은 서체 = 굵은 부분) · 5pt 칩 · 회색 뜻"""
    sp, out = fspans(pno), []
    for b in boxes_of(pno):
        inn = [s for s in sp if b["y"] < s["base"] < b["y"] + b["h"]]
        root = sorted((s for s in inn if s["size"] == 13.0), key=lambda s: s["x"])
        bold = {s["font"] for s in root}
        rec = []
        for row in rows_of([s for s in inn if s["x"] > 50 and s["size"] in (5.0, 6.0)]):
            k = 0
            word = []
            while k < len(row) and row[k]["size"] == 6.0 and row[k]["color"] == "#000000":
                word.append(row[k])
                k += 1
            parts = {"낱말 앞": "", "낱말 뿌리": "", "낱말 뒤": ""}
            for s in word:
                if s["font"] in bold:
                    parts["낱말 뿌리"] += s["text"]
                else:
                    parts["낱말 " + ("뒤" if parts["낱말 뿌리"] else "앞")] += s["text"]
            rec += [[n, v.strip()] for n, v in parts.items() if v.strip()]
            mean = []
            for s in row[k:]:
                if s["size"] == 5.0:
                    if mean:                                            # 줄 가운데 품사 — 그 앞 뜻은 같은 단락(「뜻 앞」)
                        rec.append(["뜻 앞", join(mean)])
                        mean = []
                    rec.append(["품사", s["text"].strip()])
                else:
                    mean.append(s)
            if mean:
                rec.append(["뜻", join(mean)])
        rec.append(["뿌리", join(root)])
        out.append(rec)
    return out


def more_face(lp=150):
    st = pg_new(lp, f"⑧ more with · 펼침면 — 원본 {lp}쪽(왼쪽)", name="more with · 펼침면")
    st += more_styles()
    st += pill_part()
    st += frame_part_left(lp)
    st += more_frame(lp, True)
    st += done("more with 왼쪽", f"p{lp}.png")
    st += pg_new(lp + 1, f"⑧ more with · 펼침면 — 원본 {lp + 1}쪽(오른쪽)", name=None)
    st += frame_first_right(lp + 1)
    st += more_frame(lp + 1, False)
    st += done("more with 오른쪽", f"p{lp + 1}.png")
    CONTENT.setdefault(MORE, []).extend(more_records(lp) + more_records(lp + 1))
    return st


FACES = {8: (more_face,)}


if __name__ == "__main__":                                              # 잰 값 · 레코드 보기
    import json
    g = measure()
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in g.items() if k not in ("boxes", "ptxt")}, ensure_ascii=False))
    print(json.dumps(more_records(150)[:2] + more_records(150)[-1:], ensure_ascii=False))
