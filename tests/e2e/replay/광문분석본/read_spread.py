"""원본 분석 펼침면에서 원고를 읽는다 — 바깥 시스템이 보낼 꼴(꾸밈 조각)로. 견본 원고·다른 원고 넣기 시험에 쓴다.

왼쪽 면: 문장(번호 + 영어 — 글자색 · 형광 띠 · 밑줄 · 위/아래 표기 · 서술형★ · GRAMMAR POINT 메모) + 해석.
오른쪽 면: 주제 · 요약 · 발문 · 문제 지문 · 선지 · 답 · 어휘.
꾸밈은 문자 스타일 이름으로(브랜드에 같은 이름이 있어야 한다): 파랑 글자 · 빨강 글자 · 형광 민트 · 형광 노랑 · 형광 보라 · 밑줄 · 빨강 물결 · 서술형.
"""
import re
import pymupdf

MM = 25.4 / 72
HL = {"#ceeae0": "형광 민트", "#fef9c1": "형광 노랑", "#dbd4ea": "형광 보라"}
COL = {"#224e8e": "파랑 글자", "#d2232a": "빨강 글자"}
HANGUL = re.compile(r"[가-힣]")


def _hex(c):
    if isinstance(c, int):
        return "#%06x" % c
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c[:3])


def _chars(p, pred):
    """글자들 — 조각(span) 번호·조각 안 차례(k)를 달아 둔다. 합자(fi·fl)는 글자 상자가 겹쳐 x 로 늘어놓으면 순서가 뒤섞인다"""
    t = p.trimbox
    out, si = [], 0
    for b in p.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                si += 1
                if not pred(s):
                    continue
                for k, c in enumerate(s["chars"]):
                    out.append({"c": c["c"], "x0": (c["bbox"][0] - t.x0) * MM, "x1": (c["bbox"][2] - t.x0) * MM, "span": si, "k": k,
                                "sx": (s["chars"][0]["origin"][0] - t.x0) * MM,
                                "base": (c["origin"][1] - t.y0) * MM, "col": _hex(s["color"]), "size": s["size"], "font": s["font"]})
    return out


def _lines(chars, tol=0.6):
    rows = []
    for c in sorted(chars, key=lambda c: (c["base"], c["sx"], c["span"], c["k"])):
        if rows and abs(rows[-1][0]["base"] - c["base"]) < tol:
            rows[-1].append(c)
        else:
            rows.append([c])
    return [sorted(r, key=lambda c: (c["sx"], c["span"], c["k"])) for r in rows]   # 조각끼리는 왼쪽부터, 조각 안은 제 차례


def _text(row, gap=0.45):
    """한 줄 글자 → 글. 글자 사이가 띄어져 있으면(공백 글자가 빠진 조각 경계) 띄어 쓴다."""
    out, prev = "", None
    for c in row:
        if prev is not None and c["c"] != " " and prev["c"] != " " and c["x0"] - prev["x1"] > gap:
            out += " "
        out += c["c"]
        prev = c
    return re.sub(r" +", " ", out)


def _join(lines):
    """여러 줄 → 한 문단. 한글 낱말이 줄에서 갈렸으면 붙이고, 나머지는 띄어 잇는다."""
    out, sp = "", False
    for raw in lines:
        ln = raw.strip()
        if not out:
            out = ln
        elif not sp and HANGUL.search(out[-1]) and HANGUL.search(ln[:1]) and not out.endswith((".", ",")):
            out += ln
        else:
            out += " " + ln
        sp = raw.endswith(" ")                                          # 원본 줄 끝 빈칸 = 낱말 끝
    return out


def left(pdf, pno):
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    t = p.trimbox
    body = _chars(p, lambda s: 8.8 <= s["size"] <= 9.1 and not s["font"].startswith("Jalnan"))
    nums = [c for c in _chars(p, lambda s: s["font"].startswith("Jalnan") and s["size"] > 8) if c["c"].strip()]
    labels = [c for c in _chars(p, lambda s: round(s["size"], 1) == 7.0 and not s["font"].startswith("SKYBORI")) if c["x0"] < 140]
    tr = _chars(p, lambda s: round(s["size"], 1) == 6.3)
    notes = _chars(p, lambda s: s["font"].startswith("SKYBORI"))
    draws = p.get_drawings()
    hls, uls, marks = [], [], []
    for g in draws:
        r = g["rect"]
        x, y, w, h = (r.x0 - t.x0) * MM, (r.y0 - t.y0) * MM, r.width * MM, r.height * MM
        col = _hex(g["color"]) if g.get("color") else None
        if col in HL and (g.get("width") or 0) > 2:
            hls.append((x, x + w, y, HL[col]))
        elif col and h < 0.1 and 0.3 < (g.get("width") or 0) < 0.7 and x < 140:
            uls.append((x, x + w, y))
        elif g.get("fill") and _hex(g["fill"]) == "#d2232a" and w < 6 and h < 4:
            marks.append((x, y, w, h))
    rows = _lines(body)
    # 문장 = 번호가 앞에 선 줄부터 다음 번호 전까지
    sents = []
    for row in rows:
        b = row[0]["base"]
        n = [c for c in nums if abs(c["base"] - b) < 0.6]
        if n or not sents:
            sents.append({"no": "".join(c["c"] for c in sorted(n, key=lambda c: c["x0"])).strip(), "rows": []})
        sents[-1]["rows"].append(row)
    out = []
    for si, s in enumerate(sents):
        # 글자마다 꾸밈 — 글자색 · 형광 띠(기준선 위 1.1mm 가운데) · 밑줄(기준선 아래 0.4mm)
        chars = []
        for ri, row in enumerate(s["rows"]):
            if ri and chars and chars[-1]["c"] != " " and row[0]["c"] != " ":
                chars.append({"c": " ", "cs": None, "row": ri})
            prev = None
            for c in row:
                if prev is not None and c["c"] != " " and prev["c"] != " " and c["x0"] - prev["x1"] > 0.45:
                    chars.append({"c": " ", "cs": None, "row": ri})
                cx = (c["x0"] + c["x1"]) / 2
                cs = [COL[c["col"]]] if c["col"] in COL else []
                cs += [n for x0, x1, y, n in hls if x0 - 0.1 <= cx <= x1 + 0.1 and abs(y - (c["base"] - 1.1)) < 0.8]
                cs += ["밑줄" for x0, x1, y in uls if x0 - 0.1 <= cx <= x1 + 0.1 and abs(y - (c["base"] + 0.4)) < 0.5]
                chars.append(dict(c, cs=cs or None, row=ri, cx=cx))
                prev = c
        # 낱말(띄어쓰기 사이) — 표기는 가운데가 가장 가까운 낱말에
        words, cur = [], []
        for k, c in enumerate(chars):
            if c["c"] == " ":
                if cur:
                    words.append(cur)
                cur = []
            else:
                cur.append(k)
        if cur:
            words.append(cur)
        ruby = {}
        lines_b = [r[0]["base"] for r in s["rows"]]
        for lab in _lines(labels, 0.4):
            lb = lab[0]["base"]
            # 그 표기가 붙는 문장 줄 — 위 표기는 줄 기준선 위 1~4mm, 아래 표기는 아래 1.5~5mm
            for ri, b in enumerate(lines_b):
                pos = "above" if 0.8 < b - lb < 4.5 else ("below" if 1.5 < lb - b < 5.5 else None)
                if not pos:
                    continue
                # 표기 한 줄에 여러 개(띄어진 묶음) — 1mm 넘게 떨어지면 다른 표기
                groups, g = [], [lab[0]]
                for c in lab[1:]:
                    if c["x0"] - g[-1]["x1"] > 1.2:
                        groups.append(g)
                        g = [c]
                    else:
                        g.append(c)
                groups.append(g)
                for g in groups:
                    txt = _text(g, 0.6).strip()
                    if not txt:
                        continue
                    gx = (g[0]["x0"] + g[-1]["x1"]) / 2
                    cand = [w for w in words if chars[w[0]]["row"] == ri]
                    if not cand:
                        continue
                    w = min(cand, key=lambda w: abs((chars[w[0]]["x0"] + chars[w[-1]]["x1"]) / 2 - gx) if "x0" in chars[w[0]] else 99)
                    ruby.setdefault(w[0], []).append({"t": txt, "pos": pos})
                break
        for x, y, w_, h in marks:                                       # 서술형★ — 문장 위 빨간 손글씨
            mb = y + h + 0.5
            for ri, b in enumerate(lines_b):
                if 0 < b - mb < 4:
                    cand = [w for w in words if chars[w[0]]["row"] == ri]
                    if cand:
                        w = min(cand, key=lambda w: abs(chars[w[0]]["x0"] - x))
                        if not any(r.get("cs") == "서술형" for r in ruby.get(w[0], [])):
                            ruby.setdefault(w[0], []).append({"t": "서술형★", "pos": "above", "cs": "서술형"})
        # 조각 — 낱말 표기가 있으면 그 낱말을 한 조각으로, 나머지는 꾸밈이 같은 글자끼리
        runs = [s["no"] + " "] if s["no"] else []
        k = 0
        while k < len(chars):
            w = next((w for w in words if w[0] == k), None)
            if w and k in ruby:
                css = chars[w[0]]["cs"]
                rbs = ruby[k]
                rb = [r for r in rbs if r["pos"] == "above"][:1] + [r for r in rbs if r["pos"] == "below"][:1]
                run = {"t": "".join(chars[i]["c"] for i in w), "ruby": rb[0] if len(rb) == 1 else rb}
                if css:
                    run["cs"] = css[0] if len(css) == 1 else css
                runs.append(run)
                k = w[-1] + 1
                continue
            c = chars[k]
            cs = c.get("cs")
            cs = (cs[0] if len(cs) == 1 else cs) if cs else None
            if runs and isinstance(runs[-1], dict) and "ruby" not in runs[-1] and runs[-1].get("cs") == cs and cs:
                runs[-1]["t"] += c["c"]
            elif runs and isinstance(runs[-1], str) and not cs:
                runs[-1] += c["c"]
            else:
                runs.append({"t": c["c"], "cs": cs} if cs else c["c"])
            k += 1
        # 한 조각에 꾸밈이 둘 이상(색 + 형광)이면 첫 꾸밈만 남는다 — 형광을 밖으로: 색 글자는 그대로, 형광 띠 구간은 형광 문자 스타일로
        out.append({"문장": runs, "해석": "", "_b0": lines_b[0], "_b1": lines_b[-1]})
    # 해석 — 문장 사이 6.3pt 줄들
    trs = _lines(tr)
    for o_, nx in zip(out, out[1:] + [None]):
        ls = [r for r in trs if r[0]["base"] > o_["_b1"] and (nx is None or r[0]["base"] < nx["_b0"])]
        o_["해석"] = _join(_text(r) for r in ls)
    # GRAMMAR POINT 메모 — 줄 사이가 4mm 넘게 벌어지면 다음 메모. 첫 줄 기준선이 가장 가까운 문장 첫 줄에(옆 메모)
    nl = _lines(notes)
    groups = []
    for r in nl:
        if groups and r[0]["base"] - groups[-1][-1][0]["base"] < 4.5:
            groups[-1].append(r)
        else:
            groups.append([r])
    for g in groups:
        paras, cur = [], []                                              # 짧게 끝난 줄 = 문단 끝
        for r in g:
            cur.append(_text(r))
            if r[-1]["x1"] < 180:
                paras.append(_join(cur))
                cur = []
        if cur:
            paras.append(_join(cur))
        txt = "* " + "\n".join(paras)
        o_ = min(out, key=lambda o: abs(o["_b0"] - g[0][0]["base"]))
        o_["문장"].insert(0, {"t": "", "side": txt})
    for o_ in out:
        o_.pop("_b0")
        o_.pop("_b1")
    return out


def right(pdf, pno):
    d = pymupdf.open(pdf)
    p = d[pno - 1]
    ch = _chars(p, lambda s: True)
    rows = _lines([c for c in ch if c["c"].strip() or True])
    get = lambda y0, y1, x0, x1, size=None: [r for r in rows if y0 <= r[0]["base"] <= y1 and x0 <= r[0]["x0"] <= x1 and (size is None or abs(r[0]["size"] - size) < 0.3)]
    med = _lines([c for c in ch if abs(c["size"] - 8.37) < 0.2 and c["x0"] > 31])
    topic = _join(_text(r) for r in med if 20 <= r[0]["base"] <= 24)
    summ = _join(_text(r) for r in med if 25 <= r[0]["base"] <= 40)
    q = [r for r in get(50, 175, 24, 112) if abs(r[0]["size"] - 7.5) < 0.3 or abs(r[0]["size"] - 7.35) < 0.3]
    ans = [r for r in get(160, 178, 100, 112)]
    ans_t = _text(ans[-1]).strip() if ans else ""
    q = [r for r in q if _text(r).strip() != ans_t]
    paras, cur, last = [], [], None
    for r in q:                                                          # 빈 줄(5mm 넘는 간격)에서 문단
        if last is not None and r[0]["base"] - last > 7:
            paras.append(cur)
            cur = []
        cur.append(r)
        last = r[0]["base"]
    if cur:
        paras.append(cur)
    prompt = _join(_text(r).strip() for r in paras[0]) if paras else ""
    choices = []
    passage = []
    for para in paras[1:]:
        txt = [_text(r).strip() for r in para]
        if txt and txt[0][:1] in "①②③④⑤":
            for t in txt:
                if t[:1] in "①②③④⑤" or not choices:
                    choices.append(t)
                else:
                    choices[-1] += " " + t
        else:
            passage.append(_join(txt))
    voca_rows = get(210, 275, 20, 190, 7.0)
    cols = {}
    for r in voca_rows:                                                  # 6칸 — 낱말 x 23·79·135 · 뜻 x 51·107·163
        for c in _split_cells(r):
            cols.setdefault(round(c[0]), []).append((c[1], c[2]))
    pairs = []
    for wx in (23, 79, 135):
        ws = sorted(cols.get(wx, []))
        ms = dict((round(b, 1), t) for b, t in cols.get(wx + 28, []))
        for b, w in ws:
            pairs.append(f"{w}\t{ms.get(round(b, 1), '')}")
    return {"주제": topic, "요약": summ, "발문+문제지문+선지": [{"발문": prompt, "문제지문": "\n".join(passage), "선지": "\n".join(choices)}],
            "답": ans_t, "어휘": "\n".join(pairs)}


def _split_cells(row):
    """VOCA 한 줄 → [(칸 x, 기준선, 글)] — 글자 사이가 3mm 넘게 벌어지면 다른 칸"""
    out, cur = [], [row[0]]
    for c in row[1:]:
        if c["x0"] - cur[-1]["x1"] > 3:
            out.append(cur)
            cur = [c]
        else:
            cur.append(c)
    out.append(cur)
    return [(g[0]["x0"], g[0]["base"], _text(g).strip()) for g in out if _text(g).strip()]


if __name__ == "__main__":
    import json, sys
    pdf, lp = sys.argv[1], int(sys.argv[2])
    print(json.dumps({"왼쪽": left(pdf, lp), "오른쪽": right(pdf, lp + 1)}, ensure_ascii=False, indent=1)[:6000])
