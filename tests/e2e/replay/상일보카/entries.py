"""상일보카 단어 항목 읽기 — 원본 PDF 한 쪽의 단어 항목을 원고 레코드로(흐름 자리 「번호+표제어+품사+뜻 첫+뜻+칸 이름+…」의 문항).

    python3 tests/e2e/replay/상일보카/entries.py <PDF> <쪽> [<쪽> …]      → 레코드 JSON

레코드 하나 = 단어 하나 = [[자리, 글], …] (문항 안 차례):
  번호 · 표제어 · 품사 · 뜻 첫 · (품사 · 뜻)… · 칸 이름(예문) · 예문 첫 · 해석 · (예문 · 해석)… · 칸 이름(유반의어) · 유반의어 첫 · 칸 이름(영영풀이) · 풀이 첫
  왼쪽 칸 글(표제어 · 칸 이름)은 오른쪽 칸 첫 단락 앞에 붙는다(탭) — 그 단락은 「… 첫」 스타일(내어쓰기), 이어지는 단락은 들여쓰기만.
글 안 꾸밈: 예문 · 해석의 분홍 글(표제어 자리 · 뜻 자리) → 문자 스타일 「강조」(꾸밈 조각 {"t", "cs"}).
뜻 번호(1. 2.)의 파랑은 원고가 아니라 단락 GREP(템플릿).
"""
import json
import re
import sys

import pymupdf

MM = 25.4 / 72
HAN = re.compile(r"[가-힣]")
PINK = "#f37875"
LEFT_X = 40.0                                                          # 왼쪽 칸(표제어 · 칸 이름)과 오른쪽 칸의 경계(오른쪽 칸 44.2mm)


def spans(p):
    t = p.trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] != (1.0, 0.0):
                continue
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip() or (c["bbox"][2] - c["bbox"][0]) * MM > 0.2]
                if not ch or sp["size"] < 2 or sp.get("alpha", 255) == 0:
                    continue
                out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM,
                            "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "text": "".join(c["c"] for c in ch)})
    return out


def lines(sps, tol=0.5):
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def text_of(row):
    t = ""
    for k, s in enumerate(row):
        if k and s["x"] - row[k - 1]["x1"] > 0.4 and not t.endswith(" "):
            t += " "
        t += s["text"]
    return re.sub(r"\s+", " ", t).strip()


def runs(rows):
    """줄들 → 꾸밈 조각(분홍 = 「강조」). 줄 사이 공백(한글 줄은 원본이 낱말 사이에서 꺾였다)"""
    out = []
    for i, row in enumerate(rows):
        for k, s in enumerate(row):
            gap = (k and s["x"] - row[k - 1]["x1"] > 0.4) or (i and k == 0)
            cs = "강조" if s["color"] == PINK else None
            t = (" " if gap else "") + s["text"]
            if out and out[-1][1] == cs:
                out[-1][0] += t
            else:
                out.append([t, cs])
    res = []
    for t, cs in out:
        t = re.sub(r"\s+", " ", t)
        res.append({"t": t, "cs": cs} if cs else t)
    if res and isinstance(res[0], str):
        res[0] = res[0].lstrip()
    if res and isinstance(res[-1], str):
        res[-1] = res[-1].rstrip()
    return res if any(isinstance(r, dict) for r in res) else "".join(res)


def entries(pdf, pno):
    p = pymupdf.open(pdf)[pno - 1]
    sp = [s for s in spans(p) if 8 < s["base"] < 200]                  # 머리 띠 · 꼬리 빼고
    nums = sorted((s for s in sp if s["size"] == 6.0 and s["color"] == "#274f7e" and s["x"] < 21 and re.fullmatch(r"\d{4}", s["text"])),
                  key=lambda s: s["base"])
    out = []
    for i, n in enumerate(nums):
        end = nums[i + 1]["base"] - 0.5 if i + 1 < len(nums) else 200
        body = [s for s in sp if n["base"] + 0.5 < s["base"] < end]
        left = lines([s for s in body if s["x"] < LEFT_X])
        right = lines([s for s in body if s["x"] >= LEFT_X])
        rec = [["번호", n["text"]]]
        heads = [r for r in left if r[0]["size"] >= 9]
        labels = [r for r in left if r[0]["color"] == "#999999"]
        word = text_of(heads[0]) if heads else ""
        lab_at = [(r[0]["base"], text_of(r)) for r in labels]
        # 오른쪽 칸 줄을 칸 이름(예문 · 유반의어 · 영영풀이)으로 나눈다 — 첫 칸 이름 앞 줄들 = 뜻
        cuts = [b - 0.6 for b, _ in lab_at]
        sect = lambda b: max([k for k, c in enumerate(cuts) if b >= c], default=-1)
        groups = {}
        for r in right:
            groups.setdefault(sect(r[0]["base"]), []).append(r)
        mean = groups.get(-1, [])
        first = True
        cur = None
        for r in mean:                                                   # 품사 칩(5pt 남색) 이 있는 줄 = 새 뜻 단락
            chip = [s for s in r if s["size"] == 5.0]
            rest = [s for s in r if s["size"] != 5.0]
            if chip or cur is None:
                if first:
                    rec.append(["표제어", word])
                if chip:
                    rec.append(["품사", text_of(chip)])
                rec.append(["뜻 첫" if first else "뜻", [rest]])
                cur = rec[-1]
                first = False
            else:
                cur[1].append(r)
        for k, (b, lab) in enumerate(lab_at):
            rows = groups.get(k, [])
            if not rows:
                continue
            rec.append(["칸 이름", lab])
            if lab == "예문":
                ex = None
                for r in rows:
                    ko = any(HAN.search(s["text"]) for s in r if s["color"] != PINK) or all(s["color"] == "#4d4d4d" or s["color"] == PINK and HAN.search(s["text"]) for s in r)
                    kind = "해석" if ko else ("예문 첫" if not any(x[0] in ("예문 첫", "예문") for x in rec) else "예문")
                    if ex is not None and ex[0] == kind.split()[0] or (ex is not None and ex[0] in ("예문 첫", "예문") and kind in ("예문 첫", "예문")):
                        ex[1].append(r)
                    else:
                        rec.append([kind, [r]])
                        ex = rec[-1]
            else:
                nm = {"영영풀이": "풀이 첫", "유반의어": "유반의어 첫"}.get(lab, lab + " 첫")
                rec.append([nm, rows])
        for f in rec:
            if isinstance(f[1], list):
                f[1] = runs(f[1])
        out.append(rec)
    return out


DLEFT_X = 50.0                                                         # 파생어 면 — 왼쪽 칸(낱말 · 칸 이름)과 오른쪽 칸(53.0mm) 경계


def derived(pdf, pno):
    """파생어 & 연관어휘 면 — 번호 줄(번호 · 오른쪽 끝 회색 뿌리 낱말) 아래 낱말 여럿(낱말 · 품사 · 뜻 · 예문 · 해석 · 유반의어).
    레코드 = 번호 하나 = [[번호, …], [뿌리, …], [낱말 | 구, …], [품사, …], [뜻 첫, …], … 다음 낱말 …]"""
    p = pymupdf.open(pdf)[pno - 1]
    sp = [s for s in spans(p) if 8 < s["base"] < 200]
    nums = sorted((s for s in sp if s["size"] == 6.0 and s["x"] < 21 and re.fullmatch(r"\d{4}", s["text"])), key=lambda s: s["base"])
    out = []
    for i, n in enumerate(nums):
        end = nums[i + 1]["base"] - 0.5 if i + 1 < len(nums) else 200
        root = text_of([s for s in sp if abs(s["base"] - n["base"]) < 0.5 and s["x"] > 100 and s["color"] == "#999999"])
        body = [s for s in sp if n["base"] + 0.5 < s["base"] < end]
        left = lines([s for s in body if s["x"] < DLEFT_X])
        right = lines([s for s in body if s["x"] >= DLEFT_X], tol=0.6)
        rec = [["번호", n["text"]], ["뿌리", root]]
        heads = [(r[0]["base"], r) for r in left]
        # 오른쪽 줄을 그 위(또는 같은 높이)의 가장 가까운 왼쪽 칸 글에 붙인다
        owner = lambda b: max((k for k, (hb, _) in enumerate(heads) if hb <= b + 0.8), default=0)
        groups = {}
        for r in right:
            groups.setdefault(owner(r[0]["base"]), []).append(r)
        for k, (hb, hr) in enumerate(heads):
            rows = groups.get(k, [])
            if hr[0]["color"] != "#999999" and not rows and k and heads[k - 1][1][0]["color"] != "#999999" and hb - heads[k - 1][0] < 3.2:
                last = next(f for f in reversed(rec) if f[0] in ("낱말", "구"))     # 꺾인 구(두 줄) — 앞 구에 잇는다
                last[1] += " " + text_of(hr)
                continue
            if hr[0]["color"] != "#999999":
                nth = sum(1 for f in rec if f[0] in ("낱말", "구"))           # 번호 아래 둘째 낱말부터는 「다음 뜻 첫」(낱말 사이가 넓다 — 단락 앞 공백이 다른 스타일)
                rec.append(["낱말" if hr[0]["size"] >= 8 else "구", text_of(hr)])
                cur, first = None, True
                for r in rows:
                    chip = [s for s in r if s["size"] == 5.0]
                    rest = [s for s in r if s["size"] != 5.0]
                    if chip or cur is None:
                        if chip:
                            rec.append(["품사", text_of(chip)])
                        rec.append([("뜻 첫" if not nth else "다음 뜻 첫") if first else "뜻", [rest]])
                        cur, first = rec[-1], False
                    else:
                        cur[1].append(r)
                continue
            lab = text_of(hr)
            rec.append(["칸 이름", lab])
            if lab == "예문":
                ex = None
                for r in rows:
                    ko = all(s["color"] == "#4d4d4d" or (s["color"] == PINK and HAN.search(s["text"])) or not s["text"].strip() for s in r)
                    kind = "해석" if ko else ("예문 첫" if ex is None else "예문")
                    if ex is not None and (ex[0] == kind or ex[0] in ("예문 첫", "예문") and kind in ("예문 첫", "예문")):
                        ex[1].append(r)
                    else:
                        rec.append([kind, [r]])
                        ex = rec[-1]
            else:
                rec.append([{"영영풀이": "풀이 첫", "유반의어": "유반의어 첫"}.get(lab, lab + " 첫"), rows])
        for f in rec:
            if isinstance(f[1], list):
                f[1] = runs(f[1])
        out.append(rec)
    return out


if __name__ == "__main__":
    pdf = sys.argv[1]
    res = []
    for a in sys.argv[2:]:
        res += entries(pdf, int(a))
    print(json.dumps(res, ensure_ascii=False, indent=1))
