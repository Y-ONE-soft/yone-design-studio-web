"""이의1보카 단어 항목 읽기 — 원본 PDF 한 쪽의 단어 항목을 원고 레코드로(지문 꼬리표 · 번호 · 표제어 · 품사 · 뜻 · 예문 · 해석 · 유반의어 · 파생어 · 영영풀이).

    python3 tests/e2e/replay/이의1보카/entries.py <PDF> <쪽> [<쪽> …]      → 레코드 JSON

레코드 = 항목 하나 [[자리, 글], …](원고 차례 그대로 — 한 줄기 글). 지문이 새로 시작하는 항목 앞에 ["꼬리표", 꾸밈 조각](「본문 1⇥17 words」).
글 안 꾸밈(원고가 주는 글자 서식): 예문 · 해석의 초록 글 → 「강조」, 유반의어 안 작은 회색 말(유의어 · 문맥상 대조 …) → 「작은 말」, 꼬리표의 낱말 수 → 「낱말 수」.
유반의어 · 파생어처럼 줄마다 한 항목인 자리는 강제 줄 바꿈( )으로 한 단락 — 머리말(「유반의어」)이 첫 줄에만 붙는다(단락 스타일 글머리 기호).
쪽 위 「( 본문 1」(지문이 앞 쪽에서 이어짐 표시)는 읽지 않는다 — 템플릿에 만들지 않는다(상태.json 허용).
"""
import json
import re
import sys

import pymupdf

MM = 25.4 / 72
GREEN, GREEN2, GRAY, LABEL = "#2eab71", "#67c39a", "#636363", "#a1a1a1"
HAN = re.compile(r"[가-힣]")
ITEM = re.compile(r"^(유|반|구조|연관|관련|참고|cf)\.")
X0, XC = 18.99, 44.0                                                     # 표제어 · 머리말 왼쪽 / 내용 칸 왼쪽


def _spans(p):
    t = p.trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip() or (c["bbox"][2] - c["bbox"][0]) * MM > 0.2]
                if not ch:
                    continue
                out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM,
                            "size": round(sp["size"], 2), "color": "#%06x" % sp["color"],
                            "text": "".join(c["c"] for c in ch).replace("눀", "대")})   # 이 PDF 글자 표(ToUnicode)가 「대」를 「눀」로 적었다(1,254곳 — 그려진 글자는 「대」)
    return out


def _drawings(p):
    t = p.trimbox
    hx = lambda c: "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3]) if c else None
    return [{"x": (d["rect"].x0 - t.x0) * MM, "y": (d["rect"].y0 - t.y0) * MM, "w": d["rect"].width * MM, "h": d["rect"].height * MM,
             "fill": hx(d.get("fill")), "n": len(d["items"])} for d in p.get_drawings()]


def _lines(sps, tol=0.65):
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def _runs(row, mark):
    out = []
    for s in row:
        cs = mark(s)
        if out and out[-1][1] == cs:
            out[-1][0] += s["text"]
        else:
            out.append([s["text"], cs])
    return out


def _flat(parts, sep):
    """줄들(꾸밈 조각 목록) → 한 단락 꾸밈 조각 — 줄 사이는 sep(공백 · 강제 줄 바꿈)"""
    out = []
    for k, runs in enumerate(parts):
        if k:
            if out and out[-1][1] is None:
                out[-1][0] = out[-1][0].rstrip() + sep
            else:
                out.append([sep, None])
        for t, cs in runs:
            if out and out[-1][1] == cs:
                out[-1][0] += t
            else:
                out.append([t, cs])
    res = [{"t": re.sub(r" +", " ", t), "cs": cs} if cs else re.sub(r" +", " ", t) for t, cs in out]
    if res and isinstance(res[0], str):
        res[0] = res[0].lstrip()
    if res and isinstance(res[-1], str):
        res[-1] = res[-1].rstrip()
    return res if any(isinstance(r, dict) for r in res) else "".join(res)


def entries(pdf, pno, meta=None, top=None):
    """meta 에 목록을 주면 [(자리, 첫 줄 기준선, 끝 줄 기준선)] 차례를 담는다 — 간격 재기. top = 이보다 위는 머리(파트 첫 면)"""
    p = pymupdf.open(pdf)[pno - 1]
    sp, dr = _spans(p), _drawings(p)
    bars = [d for d in dr if d["fill"] and d["w"] > 100 and 6 < d["h"] < 9]            # 지문 꼬리표 띠(새 지문)
    small = [d for d in dr if d["fill"] and d["w"] > 100 and 4 < d["h"] < 6]           # 쪽 위 「( 본문 1」(이어짐 표시) — 읽지 않는다
    hi = max([d["y"] + d["h"] for d in dr if d["fill"] and d["w"] > 140 and d["y"] < 10] + [0])   # 쪽 머리 띠 아래
    body = [s for s in sp if (top or hi + 1) < s["base"] < 200 and not any(d["y"] < s["base"] < d["y"] + d["h"] + 0.5 for d in small)]
    rows = []
    for r in _lines(body):                                               # 긴 표제어는 작게 찍혀 기준선이 뜻보다 0.5mm 남짓 위 — 왼쪽 글 없는 줄이 바로 아래(1mm 안)면 한 줄로
        if rows and not any(s["x"] < XC for s in r) and any(s["x"] < XC for s in rows[-1]) and r[0]["base"] - rows[-1][0]["base"] < 1.0:
            rows[-1] = sorted(rows[-1] + r, key=lambda s: s["x"])
        else:
            rows.append(r)
    boxes = [d for d in dr if d["fill"] == "#f0f0f0" and d["w"] < 8 and d["h"] < 4]   # 품사 칸(둥근 회색 네모)
    recs, cur, field, ex = [], None, None, None
    pend = None

    def add(k, v, b0, b1):
        cur.append([k, v])
        if meta is not None:
            meta.append([k, b0, b1])
    for row in rows:
        b = row[0]["base"]
        bar = next((d for d in bars if d["y"] < b < d["y"] + d["h"]), None)
        if bar:
            name = [s for s in row if s["x"] < 100]
            cnt = [s for s in row if s["x"] >= 100]
            pend = ([["".join(s["text"] for s in name).strip(), None], ["\t", None]] + ([["".join(s["text"] for s in cnt).strip(), "낱말 수"]] if cnt else []), b)
            continue
        first = row[0]
        if first["x"] < XC and first["color"] not in ("#000000", GRAY, LABEL) and re.fullmatch(r"\d{3,4}", first["text"].strip()):   # 번호 — 새 항목(파트마다 색이 다르다)
            cur = []
            recs.append(cur)
            if pend:
                add("꼬리표", _flat([pend[0]], ""), pend[1], pend[1])
                pend = None
            add("번호", first["text"].strip(), b, b)
            field, ex = "번호", None
            continue
        if cur is None:
            continue                                                     # 쪽 첫머리가 앞 쪽 항목의 이어짐 — 그 쪽 레코드가 아니다
        left = [s for s in row if s["x"] < XC]
        right = [s for s in row if s["x"] >= XC]
        lab = "".join(s["text"] for s in left).strip()
        if field == "번호" and left:                                     # 표제어 줄 — 표제어 ⇥ [품사] 뜻
            add("표제어", lab, b, b)
            bx = next((d for d in boxes if abs(d["y"] + d["h"] / 2 - (b - 0.8)) < 2.5), None)
            pos = [s for s in right if bx and s["x"] < bx["x"] + bx["w"]]       # 품사 = 회색 네모 안 글
            if pos:
                add("품사", "".join(s["text"] for s in pos).strip(), b, b)
            mean = [s for s in right if s not in pos]
            add("뜻", _flat([_runs(mean, lambda s: None)], " "), b, b)
            field = "뜻"
            continue
        if lab in ("예문", "유반의어", "파생어", "영영풀이") or (left and lab):
            field = {"예문": "예문", "유반의어": "유반의어", "파생어": "파생어", "영영풀이": "영영풀이"}.get(lab, lab)
            ex = None
        if not right:
            continue
        b = right[0]["base"]                                             # 내용 글 기준선(머리말 「예문」은 0.37mm 위에 찍혀 있다)
        gray = all(s["color"] in (GRAY, LABEL) for s in right if s["text"].strip()) and any(HAN.search(s["text"]) for s in right)
        if field in ("예문", "해석"):
            kind = "해석" if gray else "예문"
            mark = lambda s: "강조" if s["color"] not in ("#000000", GRAY, LABEL) else None   # 파트 색 글 = 표제어 자리
            if ex and ex[0] == kind:
                ex[1].append(_runs(right, mark))
                meta is not None and meta[-1].__setitem__(2, b)
            else:
                ex = [kind, [_runs(right, mark)]]
                cur.append([kind, ex[1]])
                meta is not None and meta.append([kind, b, b])
            field = kind
            continue
        mark = (lambda s: "작은 말" if s["color"] == LABEL else None) if field == "유반의어" else (lambda s: None)
        txt = "".join(s["text"] for s in right).strip()
        if ex and ex[0] == field:
            new_item = field == "유반의어" and ITEM.match(txt) or field == "파생어" and abs(right[0]["x"] - XC) < 1.5 and re.match(r"^[A-Za-z]", txt) and " " in txt and False
            ex[2].append((bool(new_item), _runs(right, mark)))
            meta is not None and meta[-1].__setitem__(2, b)
        else:
            ex = [field, None, [(True, _runs(right, mark))]]
            cur.append([field, ex])
            meta is not None and meta.append([field, b, b])
    for r in recs:                                                       # 줄 묶기 — 예문 · 해석은 공백, 유반의어는 항목마다 강제 줄 바꿈
        for f in r:
            v = f[1]
            if f[0] in ("예문", "해석"):
                f[1] = _flat(v, " ")
            elif isinstance(v, list) and len(v) == 3 and isinstance(v[2], list):
                items = []
                for new, runs in v[2]:
                    if new or not items:
                        items.append([runs])
                    else:
                        items[-1].append(runs)
                if f[0] == "파생어":                                     # 파생어 — 줄마다 한 낱말
                    items = [[runs] for _, runs in v[2]]
                parts = []
                for it in items:
                    parts.append(_flat(it, " "))
                out = []
                for k, x in enumerate(parts):
                    if k:
                        out.append(" ")
                    out += x if isinstance(x, list) else [x]
                f[1] = out if any(isinstance(x, dict) for x in out) else "".join(out)
    return recs


if __name__ == "__main__":
    recs = [r for a in sys.argv[2:] for r in entries(sys.argv[1], int(a))]
    print(json.dumps(recs, ensure_ascii=False, indent=1))
