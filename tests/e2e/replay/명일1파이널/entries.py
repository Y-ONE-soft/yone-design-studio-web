"""명일1 파이널 원고 읽기 — 원본 PDF 쪽에서 지문 · 요약 레코드를 원고 꼴로(외부 연동이 보내는 꼴과 같게).

    python3 tests/e2e/replay/명일1파이널/entries.py <PDF> <쪽> [<쪽> …]      → 레코드 JSON

지문 면(2~12쪽) — 쪽마다 두 단, 지문 = 「출처」(12pt 줄)부터 다음 출처 전까지(단 · 쪽을 넘어 이어짐).
  문장 배열 지문: [["출처", …], ["문장", "(A) …"], …]  (지문 끝 답 줄은 템플릿 고정 개체 — 읽지 않는다)
  문장 삽입 · 순서 배열 지문: [["출처", …], ["발문", …], ["주어진문장", …], ["본문", …], …]
요약 면(13~24쪽) — 쪽마다 지문 하나: 왼쪽 단 = 빈칸 지문 · 빈칸 요약, 회색 단 = 정답 지문 · 정답 요약.
  [["출처", …], ["빈칸지문", 꾸밈 조각], ["빈칸요약", 꾸밈 조각], ["정답지문", 꾸밈 조각], ["정답요약", 꾸밈 조각]]
  꾸밈 조각 = [글 | {"t": 글, "cs": 문자 스타일}] — 굵은 글 → 「강조」, 빈칸 밑줄 → 「빈칸」(밑줄 2.05mm 마다 반각 공백 하나).
「>> 내용요약」 머리는 템플릿(고정 개체)이라 읽지 않는다.
"""
import json
import re
import sys

import pymupdf

MM = 25.4 / 72
SPLIT = {0: 103.4, 1: 107.4}                                             # 왼쪽 단 | 오른쪽 단 경계 — 짝수(왼쪽) 쪽 · 홀수(오른쪽) 쪽(단 자리가 4mm 다르다)
BLANK = 8.5 * MM / 2                                                     # 빈칸 밑줄 — 반각 공백(8.5pt 의 반 = 1.5mm) 몇 개. 원본 밑줄 길이(2.05mm 배수)에 가장 가깝게 · 자간을 주면 줄 나눔이 그 폭을 못 세어 넘쳤다
CIRCLED = "①②③④⑤"


def _spans(p):
    t = p.trimbox
    out = []
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                ch = [c for c in sp["chars"] if c["c"].strip()]
                if not ch:
                    continue
                out.append({"x": (ch[0]["origin"][0] - t.x0) * MM, "x1": (ch[-1]["bbox"][2] - t.x0) * MM, "base": (sp["origin"][1] - t.y0) * MM,
                            "size": round(sp["size"], 2), "color": "#%06x" % sp["color"], "font": sp["font"], "text": "".join(c["c"] for c in ch)})
    return out


def _unders(p):
    t = p.trimbox
    out = []
    for d in p.get_drawings():
        r = d["rect"]
        if d.get("fill") and r.height * MM < 0.3 and r.width * MM > 3 and all(abs(c) < 0.05 for c in d["fill"]):
            out.append({"x": (r.x0 - t.x0) * MM, "x1": (r.x1 - t.x0) * MM, "y": (r.y1 - t.y0) * MM})
    return out


def _lines(sps, tol=0.5):
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def _join(parts):
    """[(x, x1, 조각)] → 꾸밈 조각 목록. 조각 사이가 0.4mm 넘게 떨어지면 띄어쓰기"""
    out, prev = [], None
    for x, x1, seg in sorted(parts, key=lambda q: q[0]):
        if prev is not None and x - prev > 0.4:
            out.append(" ")
        out.append(seg)
        prev = x1
    return out


def _merge(rich):
    """옆 조각이 같은 꼴이면 합친다 · 글만이면 문자열로"""
    out = []
    for r in rich:
        if isinstance(r, str) and out and isinstance(out[-1], str):
            out[-1] += r
        elif isinstance(r, dict) and out and isinstance(out[-1], dict) and out[-1].get("cs") == r.get("cs"):
            out[-1] = dict(out[-1], t=out[-1]["t"] + r["t"])
        else:
            out.append(r)
    if len(out) == 1 and isinstance(out[0], str):
        return out[0]
    return out


def _cat(a, b):
    """두 줄 이어 붙이기 — 사이 띄어쓰기(앞 줄이 하이픈으로 끝나도 원본 줄 바꿈 하이픈 없음)"""
    if a == "" or a == []:
        return b
    la = a if isinstance(a, list) else [a]
    lb = b if isinstance(b, list) else [b]
    glue = isinstance(lb[0], str) and lb[0].startswith("_")               # 빈칸 첫 글자가 줄 끝 · 밑줄이 다음 줄 — 한 낱말(띄우지 않는다)
    return _merge(la + ([] if glue else [" "]) + lb)


BOLD = None


def _bold_font(doc):
    """굵은 영문 글꼴 — 2쪽 「(A)」의 A 와 같은 Type3 글꼴"""
    global BOLD
    if BOLD is None:
        for s in _spans(doc[1]):
            if s["text"] == "A" and s["size"] == 8.5:
                BOLD = s["font"]
                break
    return BOLD


def line_text(row, unders=(), bold=None, rich=False):
    parts = []
    for s in row:
        seg = s["text"]
        if rich and bold and s["font"] == bold:
            seg = {"t": seg, "cs": "강조"}
        parts.append((s["x"], s["x1"], seg))
    for u in unders:
        parts.append((u["x"], u["x1"], "_" * max(1, round((u["x1"] - u["x"]) / BLANK))))   # 빈칸 = 밑줄 글자(_) 몇 개 — 공백에 밑줄 문자 스타일을 주면 줄 나눔이 그 폭을 못 세어 회색 단까지 넘쳤다(편집기 고칠 목록)
    j = _join(parts)
    if not rich:                                                         # 동그라미 번호 칸 「(②)」 — 원본 글자 옆 여백(0.5~1mm)을 띄어쓰기로 읽지 않게 · 뒤 낱말과는 띄운다
        t = "".join(x if isinstance(x, str) else x["t"] for x in j)
        t = re.sub(r"\(\s*([①-⑤])\s*\)", r"(\1)", t)
        return re.sub(r"\(([①-⑤])\)(?=\w)", r"(\1) ", t)
    return _merge(j)


def passages(pdf, pages, carry=None):
    """지문 면 쪽들 → 지문 레코드 목록(쪽 · 단을 넘어 이어지는 지문은 하나로)"""
    doc = pymupdf.open(pdf)
    recs, cur = [], carry
    for pno in pages:
        p = doc[pno - 1]
        sp = [s for s in _spans(p) if 25 < s["base"] < 283]
        for col in (0, 1):
            cs = [s for s in sp if (s["x"] < SPLIT[pno % 2]) == (col == 0)]
            if not cs:
                continue
            x0 = min(s["x"] for s in cs if s["size"] == 12) if any(s["size"] == 12 for s in cs) else None
            for row in _lines(cs):
                s0 = row[0]
                txt = line_text(row)
                if s0["size"] == 12:
                    cur = [["출처", txt]]
                    recs.append(cur)
                    cx = s0["x"]
                    continue
                if cur is None:
                    continue
                if s0["text"] == "＞":
                    continue                                             # 답 줄(회색 칸 ＞ · 밑줄)은 템플릿(「문장」 끝 고정 개체) — 원고가 아니다
                cx = cur_x(cur, row, x0)
                k, val = cur[-1]
                if re.search(r"[가-힣]", txt) and k == "출처":
                    cur.append(["발문", txt])
                elif row[0]["x"] - cx > 2.5:                              # 회색 칸 안(글 왼쪽 3mm 안쪽) — 주어진 문장
                    if k == "주어진문장":
                        cur[-1][1] = _cat(val, txt)
                    else:
                        cur.append(["주어진문장", txt])
                elif re.match(r"^\([A-Z]\)", txt):                       # (A) — 새 단락
                    kind = "본문" if any(k2 == "발문" for k2, _ in cur) else "문장"
                    cur.append([kind, txt])
                elif k in ("문장", "본문"):
                    cur[-1][1] = _cat(val, txt)
                else:                                                    # 삽입 지문 본문 첫 줄
                    cur.append(["본문", txt])
    return recs


def cur_x(cur, row, x0):
    """그 단의 글 왼쪽(단 x) — 2쪽 왼쪽 17.97 · 오른쪽 104.98, 3쪽 21.97 · 108.99"""
    x = row[0]["x"]
    return max([c for c in (17.97, 21.97, 104.98, 108.99) if c <= x + 0.6] or [x])


def summaries(pdf, pages):
    """요약 면 쪽들 → 지문 레코드 목록(쪽마다 하나)"""
    doc = pymupdf.open(pdf)
    bold = _bold_font(doc)
    recs = []
    for pno in pages:
        p = doc[pno - 1]
        sp = [s for s in _spans(p) if 25 < s["base"] < 283]
        us = _unders(p)
        rec = []
        for col in (0, 1):
            cs = [s for s in sp if (s["x"] < SPLIT[pno % 2]) == (col == 0)]
            body, summ, in_sum = [], [], False
            for row in _lines(cs):
                if row[0]["size"] == 12:
                    rec.append(["출처", line_text(row)])
                    continue
                if row[0]["text"].startswith(">>"):
                    in_sum = True
                    continue
                b = row[0]["base"]
                u = [x for x in us if abs(x["y"] - b) < 0.6 and (x["x"] < SPLIT[pno % 2]) == (col == 0)]
                t = line_text(row, u, bold, rich=True)
                (summ if in_sum else body).append(t)
            jb, js = "", ""
            for t in body:
                jb = _cat(jb, t)
            for t in summ:
                js = _cat(js, t)
            rec += [["빈칸지문" if col == 0 else "정답지문", jb], ["빈칸요약" if col == 0 else "정답요약", js]]
        recs.append(sorted(rec, key=lambda r: ["출처", "빈칸지문", "빈칸요약", "정답지문", "정답요약"].index(r[0])))
    return recs


if __name__ == "__main__":
    pdf, ps = sys.argv[1], [int(x) for x in sys.argv[2:]]
    if ps and ps[0] >= 13:
        print(json.dumps(summaries(pdf, ps), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(passages(pdf, ps), ensure_ascii=False, indent=1))
