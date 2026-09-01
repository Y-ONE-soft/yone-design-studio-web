#!/usr/bin/env python3
"""조판본 ↔ 완성본 **자로 재서** 대조 — 섹션마다 행간·단 폭·시작 자리.

    python3 scripts/final_viv_geomdiff.py

⚠ 두 PDF 를 bbox 로 견주면 안 된다 — 폰트 메트릭이 달라 top 이 어긋난다.
  행간은 **연속 줄 y 차이의 최빈값**, 자리는 **잉크 열**로 잰다.
⚠ 완성본은 책마다 도련이 있기도 없기도 하다(고3 은 210×297) — 판형에서
  도련을 빼고 견준다.
"""
import collections
import os
import re
import sys
import unicodedata as U

import fitz

nfc = lambda s: U.normalize("NFC", s)
MM = lambda v: v * 25.4 / 72
B = ("/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/파이널 직전보충")
BOOKS = [("광문2", "고2"), ("상일1", "고1"), ("광문3", "고3")]


def bleed_of(doc):
    return 3.0 if round(MM(doc[0].rect.width)) > 213 else 0.0


def survey(path):
    d = fitz.open(path)
    bl = bleed_of(d)
    out = {}
    for pg in d:
        m = re.search(r"CHAPTER\.\d+\s+([가-힣][가-힣/ ]*)", pg.get_text())
        if not m:
            continue
        sec = m.group(1).strip()
        rec = out.setdefault(sec, {"lead": collections.Counter(),
                                   "x": collections.Counter(),
                                   "w": [], "pt": collections.Counter()})
        cols = collections.defaultdict(list)
        for b in pg.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = "".join(s["text"] for s in l["spans"]).strip()
                if len(t) < 40:
                    continue
                x0, y0, x1 = MM(l["bbox"][0]) - bl, MM(l["bbox"][1]) - bl, MM(l["bbox"][2]) - bl
                cols[round(x0 / 40)].append(y0)
                rec["x"][round(x0, 1)] += 1
                rec["w"].append(round(x1 - x0, 2))
                if l["spans"]:
                    rec["pt"][round(l["spans"][0]["size"], 2)] += 1
        for ys in cols.values():
            ys.sort()
            for i in range(len(ys) - 1):
                dz = round(ys[i + 1] - ys[i], 2)
                if 2 < dz < 12:
                    rec["lead"][dz] += 1
    d.close()
    return out


def delivered(base, vol):
    fs = [f for f in os.listdir(base) if nfc(f).endswith(".pdf")
          and ("Vol%d" % vol) in nfc(f) and "내지" in nfc(f) and "인쇄" not in nfc(f)]
    if not fs:
        return None
    key = lambda f: (int(re.search(r"_(\d+)\.pdf$", nfc(f)).group(1))
                     if re.search(r"_(\d+)\.pdf$", nfc(f)) else 0)
    return os.path.join(base, max(fs, key=key))


def main():
    bad = 0
    for s, g in BOOKS:
        base = os.path.join(B, g, "26-1-기말", s)
        for v in (1, 2):
            old = delivered(base, v)
            new = os.path.join(base, "Vol%d" % v,
                               "%s_파이널(Vol%d)_내지.pdf" % (s, v))
            if not old or not os.path.exists(new):
                continue
            A, N = survey(old), survey(new)
            for sec in sorted(set(A) & set(N)):
                a, n = A[sec], N[sec]
                la = a["lead"].most_common(1)[0][0] if a["lead"] else None
                ln = n["lead"].most_common(1)[0][0] if n["lead"] else None
                xa = a["x"].most_common(1)[0][0] if a["x"] else None
                xn = n["x"].most_common(1)[0][0] if n["x"] else None
                wa = max(a["w"]) if a["w"] else None
                wn = max(n["w"]) if n["w"] else None
                pa = a["pt"].most_common(1)[0][0] if a["pt"] else None
                pn = n["pt"].most_common(1)[0][0] if n["pt"] else None
                flags = []
                if la and ln and abs(la - ln) > 0.1:
                    flags.append("행간 %s→%s" % (la, ln))
                if xa and xn and abs(xa - xn) > 0.5:
                    flags.append("시작x %s→%s" % (xa, xn))
                if wa and wn and abs(wa - wn) > 0.5:
                    flags.append("단폭 %s→%s" % (wa, wn))
                if pa and pn and abs(pa - pn) > 0.05:
                    flags.append("활자 %s→%s" % (pa, pn))
                if flags:
                    bad += 1
                    print("★ %-5s Vol%d %-16s %s" % (s, v, sec, " · ".join(flags)))
    print("\n어긋난 섹션:", bad)


if __name__ == "__main__":
    main()
