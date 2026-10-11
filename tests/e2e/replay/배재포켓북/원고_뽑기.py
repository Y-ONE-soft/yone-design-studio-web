"""배재1 포켓북 원고 — 원본 PDF 에서 시험용 원고(yos-pocketbook-v1)를 뽑는다.

contents 에 포켓북 저장소가 아직 없어(2026-10-12) 원본 PDF 의 글로 원고 한 벌을 만들어 둔다 — 원고 넣기 · 책 만들기 검사용.
꼴은 docs/편집기_재현/원고자리_규약.md 「포켓북」 — 원고 = 덩어리 목록(원본 차례 그대로), 덩어리 = {자리 이름: 값}.
면은 판정(면 목록)으로 가른다: 분석 면 → 분석 덩어리, FLOW NOTE 면 → 노트 덩어리, 암기 TEST + 정답(2쪽 면) → 암기 덩어리.

    python3 tests/e2e/replay/배재포켓북/원고_뽑기.py        → 같은 폴더 원고.json · 그림/
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)
CARD = ("pocketbook", "x47abc561")

RED, BLUE, ORANGE, GRAY = 0xd2232a, 0x214e8e, 0xea9149, 0x999999
CS = {RED: "빨강 글자", BLUE: "파랑 글자"}                  # 원본 글자색 → 문자 스타일 이름(틀의 브랜드에 같은 이름)


def spans(page):
    """글 조각 — 가로 끝은 빈칸이 아닌 글자 상자로(조각 끝 빈칸까지 재면 다음 조각과의 틈이 0 이 돼 띄어쓰기를 잃는다).
    sp = 조각 글이 빈칸으로 끝난다(원본이 그 뒤를 띄웠다)"""
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                ch = [c for c in s["chars"] if c["c"].strip()]
                if not ch:
                    continue
                t = "".join(c["c"] for c in s["chars"])
                out.append({"t": t, "size": round(s["size"], 1), "color": s["color"], "sp": t != t.rstrip(),
                            "x0": ch[0]["bbox"][0], "y0": s["bbox"][1], "x1": ch[-1]["bbox"][2], "y1": s["bbox"][3]})
    return out


def lines_of(ss, tol=3):
    """같은 줄(윗변이 tol 안)끼리 묶어 위 → 아래, 줄 안 왼쪽 → 오른쪽"""
    rows = []
    for s in sorted(ss, key=lambda s: (s["y0"], s["x0"])):
        if rows and abs(rows[-1][0]["y0"] - s["y0"]) <= tol:
            rows[-1].append(s)
        else:
            rows.append([s])
    return [sorted(r, key=lambda s: s["x0"]) for r in rows]


def join(row, gap=0.6):
    """한 줄 조각을 글로 — 틈이 gap 넘으면 띄운다. 원본 재 보니 글자 사이 -0.2 · 낱말 사이 1.5(5.9pt)~2.2(9pt)"""
    t, prev = "", None
    for s in row:
        if prev is not None and s["x0"] - prev > gap and not t.endswith(" ") and not s["t"].startswith(" "):
            t += " "
        t += s["t"]
        prev = s["x1"]
    return re.sub(r"\s+", " ", t).strip()


def para(rows):
    """줄들을 문단으로 — 원본의 줄 끝 꺾임은 원고에 넣지 않는다(원고자리_규약: 줄 끝은 편집기가 정한다).
    「→」·「[」로 시작하는 줄만 새 문단. 한글끼리 꺾인 줄은 붙이고(이 책은 글자 단위로 꺾는다) 나머지는 띄운다"""
    out = []
    for t in rows:
        if not out or t.startswith(("→", "[")):
            out.append(t)
        elif re.search(r"[가-힣]$", out[-1]) and re.match(r"[가-힣]", t):
            out[-1] += t
        else:
            out[-1] += " " + t
    return "\n".join(out)


def text(ss):
    return para([join(r) for r in lines_of(ss)])


def analysis(page, H):
    ss = spans(page)
    src = [s for s in ss if s["size"] == 9.5 and s["color"] == 0xffffff and s["y0"] < H * 0.12]
    words = [s for s in ss if s["size"] == 9.0 and s["y0"] > H * 0.11 and s["y1"] < H * 0.7]
    marks = [s for s in ss if s["color"] == GRAY and s["size"] < 9 and H * 0.11 < s["y0"] < H * 0.7]
    trans = [s for s in ss if s["size"] < 6.5 and s["color"] == 0x4d4d4d and s["y0"] > H * 0.69]   # 삽화 면은 해석이 151mm(72%)부터 — 72% 로는 첫 줄을 놓쳤다
    # 지문 = 조각 목록 — 글자색은 문자 스타일, 낱말 바로 아래 회색 작은 글은 아래 윗주(문장 성분), 바로 위는 위 윗주
    # 윗주 하나는 가장 가까운 낱말 하나에만 — 가운데가 그 낱말 폭(±1) 안이고 바로 아래·위(4pt 안)인 낱말 가운데 가운데끼리 가장 가까운 것
    owner = {}
    for mi, m in enumerate(marks):
        cx = (m["x0"] + m["x1"]) / 2
        best = None
        for wi, w in enumerate(words):
            if not (w["x0"] - 1 <= cx <= w["x1"] + 1):
                continue
            pos = "below" if -2 <= m["y0"] - w["y1"] <= 4 else "above" if -2 <= w["y0"] - m["y1"] <= 4 else None   # 낱말 상자와 2pt 까지 겹쳐도(「exciting (X)」)
            if pos:
                d = abs(cx - (w["x0"] + w["x1"]) / 2)
                if best is None or d < best[0]:
                    best = (d, wi, pos)
        if best:
            owner.setdefault(best[1], []).append({"t": m["t"].strip(), "pos": best[2]})

    def ruby_of(w):
        return owner.get(next(i for i, x in enumerate(words) if x is w), [])
    deco = decorations(page)
    # 서술형★ 하나는 낱말 하나에 — 표시 왼쪽 끝이 그 낱말 폭 안이고 표시 아래 끝이 기준선 위 3mm 쯤인 낱말 가운데 왼쪽 끝이 가장 가까운 것
    badge_owner = set()
    for d in (d for d in deco if d[0] == "badge"):
        c = [(abs(w["x0"] - d[1]), i) for i, w in enumerate(words) if w["x0"] - 1.5 <= d[1] <= w["x1"] and 0 < w["y1"] - d[2] < 16]
        if c:
            badge_owner.add(min(c)[1])
    pieces, prev = [], None
    for row in lines_of(words):
        for w in row:
            if prev is not None and (w["x0"] - prev["x1"] > 0.6 or prev["sp"] or w["y0"] - prev["y0"] > 3):
                pieces.append(" ")
            p = {"t": w["t"].strip()}
            cs = ([CS[w["color"]]] if w["color"] in CS else []) + deco_cs(w, deco)
            if cs:
                p["cs"] = cs
            r = ruby_of(w)
            if next((i for i, x in enumerate(words) if x is w), None) in badge_owner:                 # 표시 아래 끝 = 기준선 위 3mm
                r = [x for x in r if x["pos"] != "above"] + [{"t": "서술형★", "pos": "above", "cs": "서술형"}]
            if r:
                p["ruby"] = r[0] if len(r) == 1 else r
            pieces.append(p if len(p) > 1 else p["t"])
            prev = w
    # 이웃한 맨글 조각은 하나로
    merged = []
    for p in pieces:
        if isinstance(p, str) and merged and isinstance(merged[-1], str):
            merged[-1] += p
        else:
            merged.append(p)
    return {"출처": join(lines_of(src)[0]) if src else "", "지문": merged, "해석": para([join(r) for r in lines_of(trans)]).replace("\n", " ")}


HL = {0xfffdee: "형광 노랑", 0xfaf7f9: "형광 분홍", 0xfff7f3: "형광 주황", 0xf1f8f6: "형광 민트"}


def decorations(page):
    """원고를 따라 움직이는 꾸밈 — 형광 띠(면) · 분홍 물결(선) · 서술형★(빨강 손글씨 그림). 좌표는 pt(글 조각과 같은 자리)"""
    out = []
    for dr in page.get_drawings():
        col = dr.get("fill") or dr.get("color")
        if not col:
            continue
        c = (round(col[0] * 255) << 16) | (round(col[1] * 255) << 8) | round(col[2] * 255)
        r = dr["rect"]
        if c in HL and dr.get("fill"):
            out.append(("hl", r.x0, r.y0, r.x1, r.y1, HL[c]))
        elif c == 0xd2232a and dr.get("fill"):
            prev = next((i for i, d in enumerate(out) if d[0] == "badge" and abs(d[2] - r.y1) < 4 and r.x0 - d[3] < 4 and d[1] - r.x1 < 4), None)
            if prev is None:                              # 「서술형」 글자 그림과 「★」 그림이 따로 — 가까이 붙은 조각은 표시 하나
                out.append(("badge", r.x0, r.y1, r.x1))
            else:
                d = out[prev]
                out[prev] = ("badge", min(d[1], r.x0), max(d[2], r.y1), max(d[3], r.x1))
    pix = page.get_pixmap(dpi=150)                         # 물결은 경로 상자가 줄 끝까지 잡혀서(95mm) 분홍 점으로 찾는다
    import numpy as np
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
    pink = (abs(a[:, :, 0] - 0xee) < 40) & (abs(a[:, :, 1] - 0x4d) < 50) & (abs(a[:, :, 2] - 0x9b) < 50)
    out.append(("wave", pink, pix.width / page.rect.width))
    return out


def deco_cs(w, deco):
    out = []
    ww = w["x1"] - w["x0"]
    for d in deco:
        if d[0] == "hl":
            ov = min(w["x1"], d[3]) - max(w["x0"], d[1])
            if ov > ww * 0.4 and d[2] - 2 <= (w["y0"] + w["y1"]) / 2 <= d[4] + 2:      # 띠가 낱말 가운데 높이를 덮는다
                if d[5] not in out:
                    out.append(d[5])
        elif d[0] == "wave":
            pink, z = d[1], d[2]
            y0, y1 = int((w["y1"] - 1) * z), int((w["y1"] + 5) * z)
            x0, x1 = int((w["x0"] + ww * 0.2) * z), int((w["x1"] - ww * 0.2) * z)
            if x1 > x0 and pink[y0:y1, x0:x1].any(axis=0).mean() > 0.6:
                out.append("분홍 물결")
    return out


def note(page, H, W):
    ss = spans(page)
    heads = [s for s in ss if s["size"] == 7.0 and s["color"] == 0x0067b4 and s["y0"] < H * 0.16]
    words = []                                          # 칸 제목 — 한 글자씩 찍힌 것을 낱말로(틈 3 안)
    for h in sorted(heads, key=lambda s: s["x0"]):
        if words and h["x0"] - words[-1]["x1"] < 3:
            words[-1] = dict(words[-1], t=words[-1]["t"].strip() + h["t"].strip(), x1=h["x1"])
        else:
            words.append(dict(h))
    flow = []
    edge = [h["x0"] - 15 for h in words] + [W]           # 칸 = 이 칸 제목(번호 동그라미 앞)부터 다음 칸 제목 앞까지
    for k, h in enumerate(words):
        col = [s for s in ss if s["size"] == 9.5 and H * 0.14 < s["y0"] < H * 0.40 and edge[k] <= s["x0"] < edge[k + 1]]
        flow.append({"제목": h["t"].strip(), "글": text(col)})
    body = [s for s in ss if s["size"] == 8.0 and s["color"] == 0 and H * 0.40 < s["y0"] < H * 0.52]
    rows = lines_of(body)
    topic = join(rows[0]) if rows else ""
    summary = para([join(r) for r in rows[1:]]).replace("\n", " ")
    voca_ss = [s for s in ss if s["size"] == 7.0 and s["color"] in (0, 0x214e8e, 0xe14e6b) and s["y0"] > H * 0.57 and s["y0"] < H * 0.9]
    cards = {}
    for s in voca_ss:                                   # 카드 = 세 단 중 하나 · 위아래 칸 — 단은 가로 셋, 칸은 그 단의 낱말 줄(검정)에서 시작
        cards.setdefault(int((s["x0"] - W * 0.08) // (W * 0.27)), []).append(s)
    voca = []
    for c in sorted(cards):
        cur = None
        for row in lines_of(cards[c]):
            t = join(row)
            if row[0]["color"] == 0:
                w = t.split(" ", 1)
                cur = {"낱말": w[0], "뜻": w[1] if len(w) > 1 else "", "동의어": "", "반의어": ""}
                voca.append(cur)
            elif cur is not None and t.startswith("="):
                cur["동의어"] = (cur["동의어"] + " " + t[1:].strip()).strip()
            elif cur is not None and t.startswith("↔"):
                cur["반의어"] = (cur["반의어"] + " " + t[1:].strip()).strip()
            elif cur is not None:                       # 줄이 넘친 동의어
                key = "반의어" if cur["반의어"] else "동의어"
                cur[key] = (cur[key] + " " + t).strip()
    return {"흐름": flow, "주제": topic, "요약문": summary, "동반의어": voca}


def memorize(page, H):
    """정답 면에서 — 면에 「번호[답]」 꼴(contents 빈칸 꼴 그대로)로 찍혀 있다. 암기 TEST 면은 같은 원고에서 답을 숨긴 모양"""
    ss = [s for s in spans(page) if H * 0.11 < s["y0"] < H * 0.9 and s["size"] in (9.0, 5.5)]
    return re.sub(r"\s+", " ", " ".join(join(r) for r in lines_of(ss, tol=4))).strip()


def unit_of(page, H):
    """단원 표시 — 오른쪽 면 바닥 글(「교과서 1과」), 옆 탭(「교과서」)"""
    ss = spans(page)
    foot = [s for s in ss if s["y0"] > H * 0.91 and s["size"] == 6.0 and s["color"] == 0]
    tab = [s for s in ss if s["size"] == 6.4 and s["color"] == 0xffffff]
    f = join(sorted(foot, key=lambda s: s["x0"])) if foot else ""
    return {"단원": f if "POCKET" not in f else "", "구분": "".join(s["t"].strip() for s in sorted(tab, key=lambda s: s["y0"]))}


def main():
    import fitz
    from routes.catalog import _design_pdf, pdf_layouts
    pdf = _design_pdf(*CARD)
    doc = fitz.open(pdf)
    W, H = doc[0].rect.width, doc[0].rect.height
    face = {}
    for f in pdf_layouts(pdf, CARD[0], False)["faces"]:
        for p in f["pages"]:
            face[p] = f
    pics = os.path.join(HERE, "그림")
    os.makedirs(pics, exist_ok=True)
    items, n = [], 0
    p = 1
    while p <= doc.page_count:
        f, page = face[p], doc[p - 1]
        lab = f["label"]
        if f["kind"] == "간지":
            p += 1
            continue
        if f["size"] == 2:                               # 암기 TEST + 정답 — 정답 면에서 뽑는다
            it = {"암기지문": memorize(doc[p], H)}
            u = unit_of(doc[p], H)
            step = 2
        elif "FLOWNOTE" in lab:
            it, u, step = note(page, H, W), unit_of(page, H), 1
        else:
            it, u, step = analysis(page, H), unit_of(page, H), 1
            img = next((b for b in page.get_text("dict")["blocks"] if b["type"] == 1 and b["bbox"][1] < H * 0.92), None)
            if img:
                n += 1
                name = f"p{p:03d}.png"
                pix = page.get_pixmap(clip=fitz.Rect(img["bbox"]), dpi=200)
                pix.save(os.path.join(pics, name))
                it["그림"] = f"그림/{name}"
        it.update({k: v for k, v in u.items() if v})
        it["_원본쪽"] = list(range(p, p + step))
        items.append(it)
        p += step
    for order in (reversed(items), items):              # 단원 표시는 오른쪽 면에만 있다 — 없는 덩어리는 뒤에서 처음 나오는 표시를(맨 끝은 앞의 것을)
        got = {}
        for it in order:
            for k in ("단원", "구분"):
                if it.get(k):
                    got[k] = it[k]
                elif got.get(k):
                    it[k] = got[k]
    out = {"format": "yos-pocketbook-v1", "book": {"title": "배재1 포켓북", "책이름": "POCKET BOOK 배재1"}, "원고": items}
    json.dump(out, open(os.path.join(HERE, "원고.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    kinds = {}
    for it in items:
        k = "암기" if "암기지문" in it else "노트" if "흐름" in it else "분석" + (" · 그림" if "그림" in it else "")
        kinds[k] = kinds.get(k, 0) + 1
    print(f"덩어리 {len(items)}개 — " + " · ".join(f"{k} {v}" for k, v in kinds.items()) + f" · 그림 {n}장 → {os.path.join(HERE, '원고.json')}")


if __name__ == "__main__":
    main()
