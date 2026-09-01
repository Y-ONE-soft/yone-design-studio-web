# -*- coding: utf-8 -*-
"""조판본 검수 ① — 납품본 지문 목록 대조 + 원고(content) ↔ PDF 글자 대조.

    python3 scripts/final_viv_audit.py

납품본이 있으면 지문 목록을 견주고, 없으면 원고 대조만 한다.
"""
import sys, os, re, json, unicodedata as U
sys.path.insert(0, '/Users/nhj/dev/yone-design-web')
import fitz
n = lambda s: U.normalize("NFC", s)
B = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/파이널 직전보충"
LAB = re.compile(r"^(?:\d{6}(?:~\d{2})?|올포 \d+강 \S+|리딩파워 \d+강 \S+|"
                 r"교과서\S+ \S+|\d+강 \d+|test\d+ \d+|외부지문 \S+)$")
norm = lambda s: re.sub(r"[^a-z]", "", (s or "").lower())

def pdf_labels(p):
    d = fitz.open(p); out = []
    for pg in d:
        for l in pg.get_text().split("\n"):
            t = l.strip()
            if LAB.match(t) and t not in out: out.append(t)
    d.close(); return out

def pdf_text(p):
    d = fitz.open(p); t = "".join(pg.get_text() for pg in d); d.close()
    return norm(t)

def delivered(base, v):
    fs = [f for f in os.listdir(base) if n(f).endswith(".pdf")
          and ("Vol%d" % v) in n(f) and "내지" in n(f) and "인쇄" not in n(f)]
    if not fs: return None
    key = lambda f: (int(re.search(r"_(\d+)\.pdf$", n(f)).group(1))
                     if re.search(r"_(\d+)\.pdf$", n(f)) else 0)
    return os.path.join(base, max(fs, key=key))

JOBS = {"광문2": ("고2", "jobs/ea099102"), "상일1": ("고1", "jobs/batch_상일1"),
        "명일1": ("고1", "jobs/batch_명일1"), "명일3": ("고3", "jobs/batch_명일3"),
        "광문3": ("고3", "jobs/batch_광문3")}
SEC = {1: [("문장배열", "items"), ("문장삽입", "paras")],
       2: [("어법수정", None), ("서술형영작", "pairs")]}
bad = 0
for s, (g, job) in JOBS.items():
    base = os.path.join(B, g, "26-1-기말", s)
    src = json.load(open(os.path.join(base, "원고", "content.json"), encoding="utf-8"))
    for v in (1, 2):
        new = os.path.join(base, "Vol%d" % v, "%s_파이널(Vol%d)_내지.pdf" % (s, v))
        if not os.path.exists(new): print("%s Vol%d 없음" % (s, v)); continue
        txt = pdf_text(new)
        # ① 납품본 대조
        old = delivered(base, v)
        line = "■ %-5s Vol%d" % (s, v)
        if old:
            a, b = pdf_labels(old), pdf_labels(new)
            plus = [x for x in b if x not in a]; minus = [x for x in a if x not in b]
            line += "  납품대조 ＋%d －%d" % (len(plus), minus and len(minus) or 0)
            if minus: line += " (－%s)" % ", ".join(minus[:4])
        else:
            line += "  납품대조 (PDF 없음)"
        # ② 원고 ↔ PDF — 지문마다 가장 긴 문장이 PDF 안에 있는가
        miss = []
        vol = src.get("vol%d" % v) or {}
        for key, sub in SEC[v]:
            for blk in vol.get(key) or []:
                if key == "어법수정":  # [헤더, 본문, …] 평평한 목록
                    continue
                hdr = blk.get("header", "?")
                if sub == "pairs":
                    cand = [p.get("english") or p.get("en") or "" for p in blk.get("pairs") or []]
                elif sub == "paras":
                    cand = [p.get("text", "") for p in blk.get("paras") or []]
                else:
                    cand = list(blk.get("items") or []) + [blk.get("passage", "")]
                cand = [c for c in cand if len(c) > 40]
                if not cand: continue
                longest = max(cand, key=len)
                if norm(longest)[:60] not in txt:
                    miss.append("%s/%s" % (key, hdr))
        gl = vol.get("어법수정") or []
        for i in range(1, len(gl), 2):
            t = gl[i]
            if len(t) > 40 and norm(t)[:60] not in txt:
                miss.append("어법수정/%s" % gl[i-1])
        line += " · 원고대조 %s" % ("전부 있음" if not miss else "★없음 %d건 %s" % (len(miss), miss[:4]))
        if miss: bad += 1
        print(line)
print("\n원고대조 실패 권수:", bad)
