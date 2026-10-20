"""광문보카 단어 항목 읽기 — 원본 PDF 한 쪽의 단어 항목(항목 사이 선으로 나뉜 표 행)을 원고 레코드로.

    python3 tests/e2e/replay/광문보카/entries.py <PDF> <쪽> [<쪽> …]      → 레코드 JSON

레코드 하나 = 표 한 행 {"칸": [왼쪽 칸, 오른쪽 칸]} (content.story_cells — 표 레코드 = 한 행):
  왼쪽 칸 = [["번호", "001"], ["표제어", "sensible"], ["발음", "[ˈsɛnsəbəl]"], ["파생어", "sensitivity"], ["파생품사", "명"], ["파생뜻", "…"], …]
  오른쪽 칸 = [["품사", "형"], ["뜻", "…"], …, ["예문", 꾸밈 조각], ["해석", 꾸밈 조각], …]
글 안 꾸밈(원고가 주는 글자 서식): 예문 · 해석의 주황 글(표제어 자리) → 문자 스타일 「강조」, 뜻 안 6pt 글((상) · (의미 동이)) → 「작은 글」.
뜻의 ①② 분홍은 원고가 아니라 단락 스타일 GREP(템플릿).
"""
import json
import re
import sys

import pymupdf

MM = 25.4 / 72
RING = "#4d4d4d"
ORANGE = "#f68b62"
HAN = re.compile(r"[가-힣]")


def _spans(p):
    t = p.trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip() or (c["bbox"][2] - c["bbox"][0]) * MM > 0.2]   # 폭 없는 공백(줄 첫 낱말 안 「ear thquake」)은 뺀다
                if not ch:
                    continue
                out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM,
                            "base": (sp["origin"][1] - t.y0) * MM, "size": round(sp["size"], 2),
                            "color": "#%06x" % sp["color"], "text": "".join(c["c"] for c in ch)})
    return out


def _drawings(p):
    t = p.trimbox
    out = []
    for d in p.get_drawings():
        r = d["rect"]
        hx = lambda c: "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3]) if c else None
        out.append({"x": (r.x0 - t.x0) * MM, "y": (r.y0 - t.y0) * MM, "w": r.width * MM, "h": r.height * MM,
                    "fill": hx(d.get("fill")), "stroke": hx(d.get("color")), "n": len(d["items"])})
    return out


def _lines(sps, tol=0.3):
    """기준선이 같은 조각들을 줄로 — 줄 = 조각 목록(왼쪽부터)"""
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def _runs(row, mark):
    """줄 → 꾸밈 조각(글 · 문자 스타일). mark(조각) = 문자 스타일 이름 또는 None"""
    out = []
    for s in row:
        cs = mark(s)
        if out and out[-1][1] == cs:
            out[-1][0] += s["text"]
        else:
            out.append([s["text"], cs])
    return out


def _join(paras):
    """줄들의 꾸밈 조각을 한 단락으로 — 줄 사이는 공백(영어) · 한 줄 끝 공백 정리"""
    out = []
    for k, runs in enumerate(paras):
        for t, cs in runs:
            if out and out[-1][1] == cs:
                out[-1][0] += t
            else:
                out.append([t, cs])
        if k + 1 < len(paras) and out and not out[-1][0].endswith(" "):
            out[-1][0] += " "
    res = []
    for t, cs in out:
        t = re.sub(r"\s+", " ", t)
        if cs:
            res.append({"t": t, "cs": cs})
        else:
            res.append(t)
    if res and isinstance(res[0], str):
        res[0] = res[0].lstrip()
    if res and isinstance(res[-1], str):
        res[-1] = res[-1].rstrip()
    return res if any(isinstance(r, dict) for r in res) else "".join(res)


def entries(pdf, pno, meta=None):
    """meta 에 목록을 주면 항목마다 {"rule": 위 선 y, "next": 아래 선 y, "c1": [(필드, 첫 줄 기준선, 끝 줄 기준선), …], "c2": […]} 를 담는다 — 간격 재기"""
    p = pymupdf.open(pdf)[pno - 1]
    sp, dr = _spans(p), _drawings(p)
    x0 = 14.99 if pno % 2 == 0 else 17.97
    rules = sorted(d["y"] for d in dr if d["fill"] and abs(d["w"] - 114.99) < 0.1 and d["h"] < 0.3)
    rings = [d for d in dr if d["stroke"] == RING and d["n"] == 20]
    out = []
    for y0, y1 in zip(rules, rules[1:]):
        rs = [s for s in sp if y0 < s["base"] < y1 + 0.2]
        pos = [s for s in rs if s["color"] == RING]                       # 둥근 네모 안 품사 글자 — 줄 기준선보다 0.46mm 위
        body = [s for s in rs if s["color"] != RING]
        c1 = _lines([s for s in body if s["x"] < x0 + 43.5])
        c2 = _lines([s for s in body if s["x"] >= x0 + 43.5])
        left = [["번호", "".join(s["text"] for s in c1[0]).strip()],
                ["표제어", "".join(s["text"] for s in c1[1]).strip()],
                ["발음", "".join(s["text"] for s in c1[2]).strip()]]
        m1 = [[k, c1[i][0]["base"], c1[i][0]["base"]] for i, k in enumerate(("번호", "표제어", "발음"))]
        m2 = []
        cur = None
        for row in c1[3:]:                                                # 파생어 — 둥근 네모가 있는 줄이 새 파생어
            b = row[0]["base"]
            ring = next((r for r in rings if r["x"] < x0 + 43.5 and abs(r["y"] + r["h"] - 0.7 - b) < 1.2), None)
            if ring:
                word = "".join(s["text"] for s in row if s["x"] < ring["x"]).strip()
                ch = next(s["text"].strip() for s in pos if abs(s["x"] - ring["x"]) < 1.5 and abs(s["base"] - b) < 1.0)
                cur = [_runs([s for s in row if s["x"] > ring["x"]], lambda s: None)]
                left += [["파생어", word], ["파생품사", ch], ["파생뜻", cur]]
                m1.append(["파생뜻", b, b])
            elif cur is not None:
                cur.append(_runs(row, lambda s: None))
                m1[-1][2] = b
        for f in left:
            if isinstance(f[1], list):
                f[1] = _join(f[1])
        right, ex = [], None
        for row in c2:
            b = row[0]["base"]
            ring = next((r for r in rings if r["x"] >= x0 + 43.5 and abs(r["y"] + r["h"] - 0.7 - b) < 1.2), None)
            if ring:
                ch = next(s["text"].strip() for s in pos if abs(s["x"] - ring["x"]) < 1.5 and abs(s["base"] - b) < 1.0)
                right += [["품사", ch], ["뜻", [_runs(row, lambda s: "작은 글" if s["size"] < 7 else None)]]]
                m2.append(["뜻", b, b])
                ex = None
                continue
            txt = "".join(s["text"] for s in row)
            kind = "해석" if HAN.search(txt) else "예문"
            runs = _runs(row, lambda s: "강조" if s["color"] == ORANGE else None)
            if right and right[-1][0] == kind and ex is not None and b - ex < 3.6:   # 같은 단락의 다음 줄(행간 3.37mm)
                right[-1][1].append(runs)
                m2[-1][2] = b
            else:
                right.append([kind, [runs]])
                m2.append([kind, b, b])
            ex = b
        for f in right:
            if isinstance(f[1], list):
                f[1] = _join(f[1])
        out.append({"칸": [left, right]})
        if meta is not None:
            meta.append({"rule": y0, "next": y1, "c1": m1, "c2": m2})
    return out


def compact(pdf, pno, meta=None):
    """2~4파트 지문형 — 지문 꼬리표(둥근 음영) · 낱말 줄(번호 ⇥ 낱말 ⇥ [품사] 뜻) · 지문 문장(들여쓰기, 위 점선). 레코드 = 낱말 줄 하나(+ 지문 문장),
    꼬리표는 그 아래 첫 레코드 앞에: [["꼬리표", "Analysis"], ["번호", "001"], ["낱말", "lease"], ["뜻", "임대 계약"], ["예문", 꾸밈 조각]].
    meta 에 목록을 주면 [(종류, 첫 줄 기준선, 끝 줄 기준선, 글)] 차례를 담는다 — 간격 재기"""
    p = pymupdf.open(pdf)[pno - 1]
    sp, dr = _spans(p), _drawings(p)
    x0 = 14.99 if pno % 2 == 0 else 17.97
    if not any(d["fill"] and abs(d["w"] - 114.99) < 0.2 and d["h"] < 0.3 for d in dr):   # 단어 항목 쪽이 아니다(간지 · 차례 · MEMO)
        return []
    pills = [d for d in dr if d["fill"] and d["n"] == 20 and 3.5 < d["h"] < 5 and d["x"] < x0 + 1 and d["y"] > 20]
    rings = [d for d in dr if d["stroke"] == RING and d["n"] == 20]
    pos = [s for s in sp if s["color"] == RING and any(r["x"] - 0.3 < s["x"] < r["x"] + r["w"] and r["y"] < s["base"] < r["y"] + r["h"] + 0.5 for r in rings)]   # 둥근 네모 안 품사 글자(지문 문장도 같은 색이라 자리로 가른다)
    body = [s for s in sp if s not in pos and 20 < s["base"] < 195]
    rows = _lines(body, 0.6)                                             # 번호는 낱말보다 0.4mm 위(기준선 이동) — 한 줄로
    out, cur, tag, ex = [], None, None, None
    for row in rows:
        b = row[0]["base"]
        pill = next((d for d in pills if d["y"] < b < d["y"] + d["h"]), None)
        if pill:
            tag = "".join(s["text"] for s in row).strip()
            meta is not None and meta.append(["꼬리표", b, b])
            continue
        if row[0]["x"] < x0 + 6 and any(x0 + 6 <= s["x"] < x0 + 54 for s in row):   # 낱말 줄 — 번호로 시작, 낱말이 있다
            num = "".join(s["text"] for s in row if s["x"] < x0 + 6).strip()
            word = "".join(s["text"] for s in row if x0 + 6 <= s["x"] < x0 + 54).strip()
            mean = [s for s in row if s["x"] >= x0 + 54]
            cur = ([["꼬리표", tag]] if tag else []) + [["번호", num], ["낱말", word]]
            ring = next((r for r in rings if r["x"] >= x0 + 54 and abs(r["y"] + r["h"] - 0.7 - b) < 1.2), None)
            if ring:
                cur.append(["품사", next(s["text"].strip() for s in pos if abs(s["x"] - ring["x"]) < 1.5 and abs(s["base"] - b) < 1.0)])
            cur.append(["뜻", _join([_runs(mean, lambda s: "작은 글" if s["size"] < 7 else None)])])
            out.append(cur)
            tag, ex = None, None
            wb = max(s["base"] for s in row if x0 + 6 <= s["x"] < x0 + 54)          # 낱말 기준선(번호는 0.4mm 위)
            meta is not None and meta.append(["낱말", wb, wb])
            continue
        if cur is None:                                                  # 쪽 첫머리가 앞 쪽 지문 문장의 이어짐 — 그 쪽 레코드가 아니다
            continue
        runs = _runs(row, lambda s: "강조" if s["color"] == ORANGE else None)   # 지문 문장 — 앞 낱말 줄 아래로 이어지는 줄들
        if ex is None:
            ex = [runs]
            cur.append(["예문", ex])
            meta is not None and meta.append(["예문", b, b])
        else:
            ex.append(runs)
            meta is not None and meta[-1].__setitem__(2, b)
    for r in out:
        for f in r:
            if f[0] == "예문":
                f[1] = _join(f[1])
    return out


if __name__ == "__main__":
    fn = compact if "--compact" in sys.argv else entries
    recs = [r for a in sys.argv[2:] if a != "--compact" for r in fn(sys.argv[1], int(a))]
    print(json.dumps(recs, ensure_ascii=False, indent=1))
