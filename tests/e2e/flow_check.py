"""흐름 틀 구조 비교 — 문항마다 「요소 사이 간격」(같은 단 안 잇닿은 줄의 기준선 차 중 행간이 아닌 것)과 들여쓰기를 원본과 맞댄다.
tests/e2e/flow_check.py <우리 PDF> <원본 첫 쪽> <쪽 수>   (원본 = d1 reference.pdf · ROWS=쪽,단 이면 그 단 줄 덤프)
줄바꿈 한 줄 차이는 뒤로 밀리므로 위치가 아니라 구조(문항 안 간격 · 문항 시작 쪽·단)를 본다."""
import os, sys, collections
import fitz
REF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "catalog/workbook/designs/d1/reference.pdf")
MM = 25.4 / 72
LEADS = (14.6 * MM, 14 * MM, 12 * MM)


def lines_of(doc, pnos, trim):
    out = []
    for qi, pno in enumerate(pnos):
        p = doc[pno]
        ox, oy = (p.trimbox.x0, p.trimbox.y0) if trim else (0, 0)
        rows = {}
        for b in p.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                if l["dir"] != (1.0, 0.0):
                    continue
                for s in l["spans"]:
                    ch = [c for c in s["chars"] if c["c"].strip()]
                    if not ch:
                        continue
                    x = (ch[0]["origin"][0] - ox) * MM
                    y = (s["origin"][1] - oy) * MM
                    if not (24 < y < 282) or x > 196:
                        continue
                    col = 0 if x < 104 else 1
                    key = next((k for k in rows if k[0] == col and abs(k[1] - y) < 1.0), (col, y))   # 1mm 안은 한 줄(번호는 발문보다 조금 아래)
                    r = rows.setdefault(key, {"page": qi, "col": col, "base": y, "x": x, "num": False, "t": ""})
                    if not (round(s["size"]) == 12 and "%06x" % s["color"] == "00559f"):
                        r["base"] = y                                     # 줄 기준선 = 글 쪽(번호 아닌)
                    r["x"] = min(r["x"], x)
                    r["t"] += "".join(c["c"] for c in s["chars"])
                    if round(s["size"]) == 12 and "%06x" % s["color"] == "00559f":
                        r["num"] = True
        out += sorted(rows.values(), key=lambda r: (r["col"], r["base"]))
    return out


def questions(lines):
    qs, cur = [], None
    for ln in lines:
        if ln["num"]:
            cur = []
            qs.append(cur)
        if cur is not None:
            cur.append(ln)
    return qs


def gaps(q):
    g = []
    for a, b in zip(q, q[1:]):
        if a["page"] != b["page"] or a["col"] != b["col"]:
            g.append("단")
            continue
        d = b["base"] - a["base"]
        if any(abs(d - L) < 0.12 for L in LEADS) or d < 0.3:
            continue                                                  # 행간(같은 요소 안 줄) — 줄 수와 상관
        g.append(round(d, 1))
    return g


me = fitz.open(sys.argv[1])
ref = fitz.open(REF)
p0, n = int(sys.argv[2]), int(sys.argv[3])
A = questions(lines_of(ref, range(p0 - 1, p0 - 1 + n), True))
B = questions(lines_of(me, range(me.page_count), False))
print("문항 원본", len(A), "우리", len(B))
ok = tot = 0
bad = collections.Counter()
for k, (qa, qb) in enumerate(zip(A, B)):
    ga, gb = [x for x in gaps(qa) if x != "단"], [x for x in gaps(qb) if x != "단"]
    m = sum(1 for x, y in zip(ga, gb) if abs(x - y) <= 0.3)
    ok += m
    tot += max(len(ga), len(gb))
    if m < max(len(ga), len(gb)):
        print(f"  {k + 1:02d} 원본 {ga}  우리 {gb}")
        for x, y in zip(ga, gb):
            if abs(x - y) > 0.3:
                bad[(x, y)] += 1
print(f"요소 사이 간격 {ok}/{tot} 같음(0.3mm 안)")
print("어긋난 쌍(원본, 우리)", bad.most_common(10))
# 단·쪽 나눔 — 문항마다 시작 쪽·단
sa = [(q[0]["page"], q[0]["col"]) for q in A]
sb = [(q[0]["page"], q[0]["col"]) for q in B]
print("문항 시작 자리(쪽·단) 같은 것", sum(1 for x, y in zip(sa, sb) if x == y), "/", len(sa))
print("원본", sa)
print("우리", sb)
LA = lines_of(ref, range(p0 - 1, p0 - 1 + n), True)
LB = lines_of(me, range(me.page_count), False)
for pg in range(n):
    for col in (0, 1):
        a = [l for l in LA if l["page"] == pg and l["col"] == col and l["base"] < 281]
        b = [l for l in LB if l["page"] == pg and l["col"] == col and l["base"] < 281]
        if a and b:
            print(f"쪽{pg + 1} 단{col}: 원본 {a[0]['base']:.1f}~{a[-1]['base']:.1f} ({a[-1]['t'][:16]}) · 우리 {b[0]['base']:.1f}~{b[-1]['base']:.1f} ({b[-1]['t'][:16]})")
if os.environ.get("ROWS"):
    pg, col = map(int, os.environ["ROWS"].split(","))
    a = [l for l in LA if l["page"] == pg and l["col"] == col]
    b = [l for l in LB if l["page"] == pg and l["col"] == col]
    for k in range(max(len(a), len(b))):
        x = a[k] if k < len(a) else None
        y = b[k] if k < len(b) else None
        print(f"  {x['base'] if x else 0:6.1f} {(x['t'][:22] if x else ''):22s} | {y['base'] if y else 0:6.1f} {(y['t'][:22] if y else '')}")
