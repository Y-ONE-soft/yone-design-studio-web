#!/usr/bin/env python3
"""파이널 Vivliostyle 산출 ↔ 인디자인 완성본 대조.

같은 원고를 두 엔진으로 조판했으니 **면·글줄이 같아야 한다.** 다르면 어디서
갈렸는지 짚어 준다.

  python3 scripts/final_viv_compare.py <완성본.pdf> <viv.pdf> [--pages]
"""
import argparse
import collections
import re
import sys

import fitz

MM = 25.4 / 72


def page_headers(doc, known=None, size=12.0, tol=0.4):
    """면마다 [지문 헤더…] — 사분면 자리(왼단 위→아래, 오른단 위→아래) 순서.

    ⚠ 활자 크기로만 고르면 **축소된 지문의 헤더를 놓친다**(인디자인이 넘치는
      지문의 활자를 줄이면 헤더도 12pt 가 아니다) — 있는데 없다고 나온다.
      `known`(원고의 헤더 목록)이 있으면 글자로 고른다.
    ⚠ x 는 **단으로 반올림**한다. 111.9 와 112.0 을 그냥 정렬하면 같은 단의
      두 지문이 뒤바뀐 것처럼 보인다(거짓 불일치를 실제로 만들었다).
    """
    out = []
    for p in doc:
        hs = []
        for b in p.get_text("dict")["blocks"]:
            if b["type"] != 0 or not b["lines"]:
                continue
            txt = "".join(x["text"] for x in b["lines"][0]["spans"]).strip()
            sz = b["lines"][0]["spans"][0]["size"]
            ok = (txt in known) if known else (abs(sz - size) < tol)
            if ok and txt:
                col = 0 if b["bbox"][0] * MM < 60 else 1
                hs.append((col, round(b["bbox"][1] * MM, 1), txt))
        out.append([h[2] for h in sorted(hs)])
    return out


def lines_of(doc):
    out = []
    for p in doc:
        ls = []
        for b in p.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                t = "".join(s["text"] for s in l["spans"]).strip()
                if t:
                    ls.append((round(l["bbox"][0] * MM, 2),
                               round(l["bbox"][1] * MM, 2),
                               round(l["bbox"][2] * MM, 2), t))
        out.append(ls)
    return out


def norm(t):
    return re.sub(r"\s+", "", t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--pages", action="store_true")
    ap.add_argument("--data", help="data.json — 헤더 목록(활자 축소분까지 잡는다)")
    a = ap.parse_args()
    A, B = fitz.open(a.ref), fitz.open(a.new)
    print(f"쪽수  완성본 {A.page_count}  viv {B.page_count}")

    known = None
    if a.data:
        import json
        d = json.load(open(a.data, encoding="utf-8"))
        known = {b["header"] for v in d["vols"].values()
                 for s in v["sections"] for b in s["blocks"]}
    ha, hb = page_headers(A, known), page_headers(B, known)
    if a.pages:
        for i in range(max(len(ha), len(hb))):
            x = ha[i] if i < len(ha) else []
            y = hb[i] if i < len(hb) else []
            mark = "   " if x == y else " ! "
            print(f"{i+1:>3}{mark}{x}\n    {'' if x==y else y}")
    same = sum(1 for i in range(min(len(ha), len(hb))) if ha[i] == hb[i])
    print(f"면별 지문 배치 일치 {same}/{min(len(ha), len(hb))}")

    # 글줄 — 완성본에 있는 줄이 viv 에도 같은 모양으로 있는가
    la = [t for pg in lines_of(A) for *_x, t in pg]
    lb = [t for pg in lines_of(B) for *_x, t in pg]
    sa, sb = collections.Counter(map(norm, la)), collections.Counter(map(norm, lb))
    only_a = [t for t in la if sa[norm(t)] > sb.get(norm(t), 0)]
    only_b = [t for t in lb if sb[norm(t)] > sa.get(norm(t), 0)]
    print(f"글줄  완성본 {len(la)}  viv {len(lb)}  "
          f"완성본에만 {len(only_a)}  viv에만 {len(only_b)}")
    for t in only_a[:12]:
        print("   -", t[:88])
    for t in only_b[:12]:
        print("   +", t[:88])

    # 글자 총량 — 내용 유실 감시(줄바꿈이 달라도 글자는 같아야 한다)
    ta = norm("".join(la))
    tb = norm("".join(lb))
    print(f"글자수 완성본 {len(ta):,}  viv {len(tb):,}  차 {len(tb)-len(ta):+,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
