"""광문1 세서특필02 원고 읽기 — 원본 PDF(인디자인 판, 서체 이름 있음) 쪽에서 원고를 외부 연동 꼴로.

    python3 tests/e2e/replay/광문1세서특필02/entries.py <PDF> <쪽> [<쪽> …]      → 중요문장 항목 JSON

중요문장(PART 1, 6~33쪽) — 한 줄기 글. 항목 = 문장 하나:
  [["섹션", 꾸밈 조각]]?  (새 단원 띠 「> 교과서 공통영어1 능률(오) 2과」 — 그 단원 첫 문장 앞에만)
  [["출처", "공통영어1 능률(오) 2과 본문 1"]]?  (출처 꼬리표 — 같은 출처의 둘째 문장부터는 없음)
  ["문장", 영어] · ["해석", 우리말] · (["문법", 이름] · ["공식", <…>] · ["설명", 풀이])…
글자 꼴로 가른다 — 섹션 Pretendard 11(띠 위) · 출처 Elice Md 9 회색 · 문장 Myriad 10 · 해석/설명 Noto 9 · 문법 Pretendard 11 · 공식 Elice Md 9 파랑.
"""
import json
import re
import sys

import pymupdf

MM = 25.4 / 72
TOP, BOT = 15.0, 277.0                                                   # 머리 · 꼬리 밖


def _spans(p):
    t = p.trimbox
    out = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if not s["text"].strip():
                    continue
                out.append({"x": (s["origin"][0] - t.x0) * MM, "x1": (s["bbox"][2] - t.x0) * MM, "base": (s["origin"][1] - t.y0) * MM,
                            "size": round(s["size"], 1), "color": "#%06x" % s["color"], "font": s["font"], "text": s["text"]})
    return out


def _lines(sps, tol=0.5):
    rows = []
    for s in sorted(sps, key=lambda s: (s["base"], s["x"])):
        if rows and abs(rows[-1][0]["base"] - s["base"]) < tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x"]) for r in rows]


def _text(row):
    """줄 글 — 끝 띄어쓰기는 남긴다(인디자인 PDF 는 띄어쓰기에서 줄을 바꾸면 줄 끝에 공백이 남고, 낱말 가운데서 바꾸면 안 남는다 — 이을 때 그대로 붙인다)"""
    return re.sub(r"\s+", " ", "".join(s["text"] for s in row)).lstrip()


def kind(row):
    s = row[0]
    f = s["font"]
    if f.startswith("JalnanOTF") or (f.startswith("Pretendard") and any(x["color"] == "#005ead" for x in row)):
        return "섹션"
    if f.startswith("EliceDXNeolli") and s["color"] == "#404041":
        return "출처"
    if f.startswith("EliceDXNeolli") and s["color"] == "#005ead":
        return "공식"
    if f.startswith("MyriadPro"):
        return "문장"
    if f.startswith("Pretendard"):
        return "문법"
    if f.startswith("NotoSansCJK"):
        return "글"
    return None


def items(pdf, pages):
    doc = pymupdf.open(pdf)
    recs, cur, last = [], None, None
    for pno in pages:
        sp = [s for s in _spans(doc[pno - 1]) if TOP < s["base"] < BOT and not s["font"].startswith("ghanachoco") and not s["font"].startswith("KCCDodam")]
        sp = [s for s in sp if not (s["base"] < 30 and s["font"].startswith("EliceDXNeolli") and s["size"] >= 13)]   # 첫 쪽 PART 띠 글
        for row in _lines(sp):
            k = kind(row)
            if k is None:
                continue
            if k == "섹션":
                seg = []
                for s in row:
                    if s["font"].startswith("JalnanOTF"):
                        continue
                    t = s["text"]
                    seg.append({"t": t.strip(), "cs": "섹션 강조"} if s["color"] == "#005ead" else t)
                seg = [x for x in seg if x != ""]
                cur = [["섹션", seg]]
                recs.append(cur)
                last = "섹션"
                continue
            txt = _text(row)
            if k == "출처" or k == "문장" and last not in ("출처", "섹션", "문장"):
                if k == "출처" or cur is None or any(f == "문장" for f, _ in cur):
                    if cur is None or any(f == "문장" for f, _ in cur):
                        cur = []
                        recs.append(cur)
            if k == "글":
                k = "해석" if last in ("문장", "해석") else "설명"
            if cur is None:
                cur = []
                recs.append(cur)
            if k == last and k in ("문장", "해석", "설명"):
                cur[-1][1] += txt
            else:
                cur.append([k, txt])
            last = k
    for r in recs:
        for f in r:
            if isinstance(f[1], str):
                f[1] = f[1].strip()
    return recs


def _boxes(p, stroke=None, fill=None):
    t = p.trimbox
    out = []
    for d in p.get_drawings():
        c = d.get("color") if stroke else d.get("fill")
        want = stroke or fill
        if c and "#%02x%02x%02x" % tuple(round(v * 255) for v in c[:3]) == want:
            r = d["rect"]
            out.append(((r.y0 - t.y0) * MM, (r.y1 - t.y0) * MM))
    return out


def _in(b, boxes, pad=1.0):
    return any(y0 - pad < b < y1 + pad for y0, y1 in boxes)


def sets(pdf, pages):
    """실전문제(42~93쪽) — 쪽마다 지문 묶음 하나. 항목 = 묶음:
    [["출처", "<…-1>"], ["지시", 꾸밈 조각], ["지문", 문단\n문단…], (["번호", "01"], ["질문", …], (["소문항", …] | ["보기제목", "<보기>"], ["보기", …] | ["대화", 줄\n줄…])…)…]"""
    doc = pymupdf.open(pdf)
    recs = []
    for pno in pages:
        p = doc[pno - 1]
        sp = [x for x in _spans(p) if 24 < x["base"] < BOT]
        pas = _boxes(p, stroke="#b2ddf6")
        dia = _boxes(p, fill="#f8f8f1")
        cur, last, prev_b = None, None, None
        for row in _lines(sp, tol=1.0):                                  # 문항 번호(15pt)와 질문(10pt) 기준선이 0.8mm 다르다 — 한 줄로
            s0 = row[0]
            f, b = s0["font"], s0["base"]
            txt = _text(row)
            if f.startswith("Pretendard") and s0["color"] == "#6d6e71":
                cur = [["출처", txt.strip()]]
                recs.append(cur)
                last = "출처"
            elif f.startswith("EliceDXNeolli") and s0["color"] == "#58595b":
                cur.append(["지시", [{"t": s0["text"].strip(), "cs": "지시 번호"}, _text(row[1:]).rstrip()]])
                last = "지시"
            elif f.startswith("TTOmni"):
                cur.append(["번호", s0["text"].strip()])
                cur.append(["질문", _text(row[1:])])
                last = "질문"
            elif f.startswith("EliceDXNeolli") and s0["color"] == "#005ead":
                cur.append(["보기제목", txt.strip()])
                last = "보기제목"
            elif last in ("보기제목", "보기") and f.startswith("NotoSansCJKkr-Medium"):
                if last == "보기":
                    cur[-1][1] += txt
                else:
                    cur.append(["보기", txt])
                last = "보기"
            elif last == "질문" and s0["size"] >= 9.9 and s0["x"] > 28:
                cur[-1][1] += txt
            elif _in(b, pas, 0.5) and s0["x"] < 26:
                if last == "지문":
                    cur[-1][1] += ("\n" if b - prev_b > 5.4 else "") + txt
                else:
                    cur.append(["지문", txt])
                last = "지문"
            elif _in(b, dia, 0.5):
                if last == "대화":
                    cur[-1][1] += ("" if s0["x"] > 25 else "\n") + txt
                else:
                    cur.append(["대화", txt])
                last = "대화"
            elif s0["x"] < 22 and txt.startswith("("):
                cur.append(["소문항", txt])
                last = "소문항"
            elif last == "소문항":
                cur[-1][1] += txt
            prev_b = b
    for r in recs:
        for f in r:
            if isinstance(f[1], str):
                f[1] = "\n".join(x.strip() for x in f[1].split("\n"))
    return recs


def _join(a, b):
    """꺾인 줄 잇기 — 줄 끝 공백이 없을 때: 「(B)」 · 문장부호 뒤나 영어 낱말 사이면 띄우고, 그 밖(한글 · 영어 뒤 조사)은 붙인다"""
    if not a or a[-1].isspace() or not b or b[0].isspace():
        return a + b
    if re.search(r"[).,!?'’”]$", a) or (re.search(r"[A-Za-z]$", a) and re.match(r"[A-Za-z(]", b)):
        return a + " " + b
    return a + b


def answers(pdf, pages):
    """정답 및 해설(94~109쪽) — 두 단, 단 차례로 한 줄기. 항목 = 지문 묶음 하나:
    [["세트", 꾸밈 조각], (["번호", "01"], ["정답", 줄\n줄…], ["해설", …])…]"""
    doc = pymupdf.open(pdf)
    recs, cur, last = [], None, None
    for pno in pages:
        p = doc[pno - 1]
        sp = [x for x in _spans(p) if 15 < x["base"] < BOT and not (x["base"] < 25 and x["size"] > 16) and not x["font"].lower().startswith("ghanachoco")]   # 정답 펼침면 왼쪽 쪽은 글상자가 14.5mm 부터
        split = 104.0 if pno % 2 == 0 else 107.0
        for col in (0, 1):
            cs = [x for x in sp if (x["x"] < split) == (col == 0) and not x["font"].startswith("EliceDXNeolli")]
            if not cs:
                continue
            x0 = min(x["x"] for x in cs)
            for row in _lines(cs, tol=0.6):
                s0 = row[0]
                f = s0["font"]
                txt = _text(row)
                if f.startswith("Pretendard") and s0["color"] == "#4791ce":
                    cur = [["세트", [{"t": s0["text"].strip(), "cs": "세트 번호"}, " " + _text(row[1:]).strip()]]]
                    recs.append(cur)
                    last = "세트"
                elif f.startswith("Pretendard") and s0["size"] >= 14:
                    if cur is None:
                        cur = []
                        recs.append(cur)
                    cur.append(["번호", txt.strip()])
                    last = "번호"
                elif f.startswith("Pretendard") and s0["color"] == "#1787c8":
                    cur.append(["해설", _text(row[1:]).lstrip()])
                    last = "해설"
                elif last == "해설":
                    cur[-1][1] = _join(cur[-1][1], txt)
                elif last in ("번호", "정답"):
                    if last == "정답" and (s0["x"] - x0 > 2.5 or not re.match(r"^\s*(\([A-Z]\)|[ⓐ-ⓩ])", txt)):   # 정답 이어지는 줄(꺾인 줄 — 기호로 시작 안 함)
                        cur[-1][1] = cur[-1][1].rstrip() + " " + txt.lstrip()
                    elif last == "정답":
                        cur[-1][1] = cur[-1][1].rstrip() + "\n" + txt
                    else:
                        cur.append(["정답", txt])
                    last = "정답"
    for r in recs:
        for f in r:
            if isinstance(f[1], str):
                f[1] = "\n".join(x.strip() for x in f[1].split("\n"))
    return recs


TCOLS = (30.5, 41.8, 98.49, 155.18, 192.0)                              # 해설 표 칸 경계(37쪽) — 문항 · 질문 속 핵심어 · 본문 단서 · 정답


def types(pdf, pages):
    """대표유형(36~41쪽) — 펼침면마다 유형 하나. 항목 = 문단 하나 [자리, 글](원고 차례):
    소제목(☞ · 🔥 · 🔎 머리) · 요약 · 유형 · 유형설명 · 과정제목 · 단계번호 · 단계 · 단계설명 · 필승 · 연습 · 시험 · 지문 · 연습문항 · 해설 ·
    표머리 · 표(칸 사이 탭) · 풀이 · 오답제목 · 오답 · 정답"""
    doc = pymupdf.open(pdf)
    out = []
    for pno in pages:
        p = doc[pno - 1]
        sp = [x for x in _spans(p) if 24 < x["base"] < BOT and not x["font"].startswith("ghanachoco")]
        rows = _lines(sp, tol=0.8)
        cur, last = None, None
        t = p.trimbox
        hdr = [d for d in p.get_drawings() if d.get("fill") and "#%02x%02x%02x" % tuple(round(v * 255) for v in d["fill"][:3]) == "#c9ebfc"
               and 4.5 < d["rect"].height * MM < 6 and d["rect"].width * MM > 100]
        t0, cols = None, TCOLS
        if hdr:                                                           # 표 머리(하늘색 띠) — 그 안 줄이 머리 줄, 칸 경계는 머리 띠의 세로선
            hy0, hy1 = (hdr[0]["rect"].y0 - t.y0) * MM, (hdr[0]["rect"].y1 - t.y0) * MM
            hr = [r for r in rows if hy0 - 0.5 < r[0]["base"] < hy1 + 0.5]
            t0 = hr[0][0]["base"] if hr else None
            vx = sorted({round((d["rect"].x0 - t.x0) * MM, 1) for d in p.get_drawings() if d.get("color") and d["rect"].width < 1
                         and hy0 - 0.5 < (d["rect"].y0 - t.y0) * MM < hy1})
            if len(vx) >= 4:
                cols = tuple(vx[:4]) + (192.0,)
        trows = []
        if t0 is not None:                                                # 표 — 머리 줄 ~ 첫 풀이 줄 전. 칸 안 여러 줄은 가장 가까운 행(첫 칸 (A) 기준선)에
            t1 = next((r[0]["base"] for r in rows if r[0]["base"] > t0 and re.match(r"^\([A-Z]\)는", _text(r).strip())), t0 + 40)
            body = [r for r in rows if t0 - 0.5 <= r[0]["base"] < t1 - 0.5]
            heads = [r for r in body if any(x["x"] < cols[1] - 1.5 for x in r)]
            cells = {id(h): [[], [], [], []] for h in heads}                 # 칸마다 줄 목록 — 칸 안에서 꺾인 줄은 강제 줄 바꿈(U+2028)으로 다음 줄 같은 탭 자리에
            for r in body:
                h = min(heads, key=lambda h: abs(h[0]["base"] - r[0]["base"]))
                got = ["", "", "", ""]
                for x in sorted(r, key=lambda x: x["x"]):
                    k = max([i for i, x0 in enumerate(cols[:4]) if x["x"] >= x0 - 1.5] or [0])
                    got[k] += x["text"]
                for k, z in enumerate(got):
                    if z.strip():
                        cells[id(h)][k].append(re.sub(r"\s+", " ", z).strip())
            for i, h in enumerate(heads):
                cs = cells[id(h)]
                n = max(1, max(len(c) for c in cs))
                trows.append(["표머리" if i == 0 else "표", "\u2028".join("\t".join(c[j] if j < len(c) else "" for c in cs).rstrip("\t") for j in range(n))])
            skip = {id(r) for r in body}
        else:
            skip = set()
        for row in rows:
            if id(row) in skip:
                if trows:
                    out.extend(trows)
                    trows = []
                    last = "표"
                continue
            s0 = row[0]
            f, c, b = s0["font"], s0["color"], s0["base"]
            txt = _text(row)
            fonts = " ".join(x["font"] for x in row)
            if "RixStraight" in fonts:
                out.append(["소제목", txt.strip()])
                last = "소제목:" + txt
            elif f.startswith("JalnanOTF"):
                out.append(["유형", _text(row[1:]).strip()])
                last = "유형"
            elif "Type3" in f and "Pretendard" in fonts:
                out.append(["과정제목", txt.strip()])
                last = "과정제목"
            elif "Type3" in f:
                out.append(["오답제목", txt.strip()])
                last = "오답제목"
            elif f.startswith("Pretendard") and c == "#ffffff":
                out.append(["단계번호", s0["text"].strip()])
                out.append(["단계", _text(row[1:]).strip()])
                last = "단계"
            elif f.startswith("Pretendard") and c == "#005ead":
                out.append(["연습", [{"t": s0["text"].strip(), "cs": "연습 번호"}, " " + _text(row[1:]).strip()]])
                last = "연습"
            elif f.startswith("Pretendard") and c == "#4791ce":
                out.append(["시험", txt.strip()])
                last = "시험"
            elif f.startswith("EliceDXNeolli") and c == "#6588c5":
                out.append(["정답", [{"t": s0["text"].strip(), "cs": "정답 머리"}, " " + _text(row[1:]).strip()]])
                last = "정답"
            elif c == "#c8da2b" or (s0["text"].strip() == "•"):
                out.append(["오답", _text(row[1:]).strip()])
                last = "오답"
            elif f.startswith("NotoSansCJKkr-Medium") and re.match(r"^\d\.", txt.strip()):
                out.append(["요약", txt.strip()])
                last = "요약"
            elif f.startswith("NotoSansCJKkr-Medium") and re.match(r"^\([A-Z]\)는", txt.strip()):
                md = "".join(x["text"] for x in row if x["font"].startswith("NotoSansCJKkr-Medium"))
                rest = "".join(x["text"] for x in row if not x["font"].startswith("NotoSansCJKkr-Medium"))
                out.append(["풀이", [{"t": md.lstrip(), "cs": "풀이 강조"}] + ([rest] if rest.strip() else [])])
                last = "풀이"
            elif last == "풀이":
                md = "".join(x["text"] for x in row if x["font"].startswith("NotoSansCJKkr-Medium"))
                rest = "".join(x["text"] for x in row if not x["font"].startswith("NotoSansCJKkr-Medium"))
                v = out[-1][1]
                if md.strip():
                    v.append({"t": md, "cs": "풀이 강조"})
                if rest.strip():
                    v.append(rest)
            elif f.startswith("NotoSansCJKkr-Medium") and re.match(r"^\([A-Z]\)", txt.strip()):
                out.append(["연습문항", txt.strip()])
                last = "연습문항"
            elif last == "오답":
                out[-1][1] += txt
            else:                                                        # 보통 글 — 앞 자리에 따라
                k = {"유형": "유형설명", "단계": "단계설명", "시험": "지문", "연습": "지문"}.get(last)
                if k is None and last and last.startswith("소제목:"):
                    k = "해설" if "해설" in last else "필승"
                if k:
                    out.append([k, txt])
                    last = k
                elif last in ("유형설명", "단계설명", "필승", "해설", "지문"):
                    out[-1][1] += txt
    for f in out:
        if isinstance(f[1], str):
            f[1] = f[1].strip()
    return out


if __name__ == "__main__":
    print(json.dumps(items(sys.argv[1], [int(x) for x in sys.argv[2:]]), ensure_ascii=False, indent=1))
