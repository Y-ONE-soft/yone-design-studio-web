# -*- coding: utf-8 -*-
"""조판본 검수 ② — **원고 → PDF** 전수 대조.

    python3 scripts/final_viv_audit_src.py

시험범위 안의 원고 지문·영작 쌍·삽입 주어진 문장이 책에 **다 들어갔는지**
센다. 게이트는 '내가 만든 것'이 다 실렸는지만 보므로, 원고에서 애초에
못 읽은 것은 잡지 못한다 — 그 구멍을 메우는 자리다.
"""
import sys, os, re, json
sys.path.insert(0, '/Users/nhj/dev/yone-design-web')
import fitz
from engines.final import manuscript as M, manuscript_locate as L, scope_source as S
norm = lambda s: re.sub(r"[^a-z가-힣]", "", (s or "").lower())
base = os.path.expanduser(json.load(open("engines/final/config.json", encoding="utf-8"))["gdrive_content_base"])
B = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/파이널 직전보충"
SCHOOLS = [("광문2", "고2", 2), ("상일1", "고1", 1), ("명일1", "고1", 1),
           ("명일3", "고3", 3), ("광문3", "고3", 3)]
for s, g, gn in SCHOOLS:
    sc = S.from_sheet(s, "26-1-기말", grade=gn)
    txt = ""
    for v in (1, 2):
        p = os.path.join(B, g, "26-1-기말", s, "Vol%d" % v, "%s_파이널(Vol%d)_내지.pdf" % (s, v))
        if os.path.exists(p):
            d = fitz.open(p); txt += "".join(pg.get_text() for pg in d); d.close()
    txt = norm(txt)
    tot = {"arrange": 0, "writing": 0, "insert": 0}
    miss = {"arrange": [], "writing": [], "insert": []}
    for d, spec in S.folders(sc, base, grade=gn):
        for kind in ("arrange", "writing", "insert"):
            for b in M.read(d, kind)[0]:
                lab = L.to_final_label(spec, b["raw"])
                if not lab or not S.in_scope(lab, sc):
                    continue
                if kind == "writing":
                    cands = [p.get("korean") or "" for p in b["pairs"]]
                elif kind == "insert":
                    cands = [b.get("given", "")]
                else:
                    cands = [max(b["items"], key=len)] if b["items"] else []
                for c in cands:
                    if len(c) < 25: continue
                    tot[kind] += 1
                    if norm(c)[:40] not in txt:
                        miss[kind].append("%s %s" % (lab, norm(c)[:18]))
    print("■ %-5s 배열 %3d/%-3d · 영작 %3d/%-3d · 삽입 %3d/%-3d %s" % (
        s, tot["arrange"] - len(miss["arrange"]), tot["arrange"],
        tot["writing"] - len(miss["writing"]), tot["writing"],
        tot["insert"] - len(miss["insert"]), tot["insert"],
        "" if not any(miss.values()) else "★"))
    for k, v in miss.items():
        if v: print("     [%s] 책에 없음 %d건: %s" % (k, len(v), v[:5]))
