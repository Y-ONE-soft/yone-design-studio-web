#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이널 검수 종합 체크 — 데이터 레벨.
사용: python3 _inspect_check.py <job_dir>
출력: 섹션별 헤더 수/일관성, 영작 best-match 오정렬, 누락 헤더, 헤더 목록.
"""
import sys, json, re

def toks(s):
    return set(w for w in re.findall(r"[a-zA-Z]{4,}", str(s).lower()))

def main():
    jd = sys.argv[1]
    d = json.load(open(jd + "/content.json", encoding="utf-8"))
    v1 = d.get("vol1", {}); v2 = d.get("vol2", {})
    arr = [b["header"] for b in v1.get("문장배열", [])]
    ins = [b["header"] for b in v1.get("문장삽입", [])]
    gh = v2.get("어법_헤더", [])
    wd = v2.get("영작_헤더_상세", [])
    wh = [h["header"] for h in wd]
    print(f"=== {d.get('school')} / {d.get('grade')} / {d.get('exam_period')} ===")
    print(f"문장배열 {len(arr)} | 문장삽입 {len(ins)} | 어법 {len(gh)} | 영작 {len(wh)}")
    # 섹션 일관성
    print("배열==삽입:", arr == ins, "| 배열==어법:", arr == gh)
    if arr != gh:
        print("  배열-어법 차:", [h for h in arr if h not in gh][:10], "| 어법-배열 차:", [h for h in gh if h not in arr][:10])
    print("영작에만 없는(배열-영작):", [h for h in arr if h not in wh])
    print("배열에만 없는(영작-배열):", [h for h in wh if h not in arr])
    # 영작 best-match
    g = v2.get("어법수정", []); gram = {}
    for i in range(0, len(g), 2):
        gram[g[i]] = g[i + 1] if i + 1 < len(g) else ""
    gt = {h: toks(b) for h, b in gram.items()}
    wp = v2.get("서술형영작", [])
    bad = []
    for i, h in enumerate(wd):
        hdr = h["header"]; s = h["start_idx"]
        e = wd[i + 1]["start_idx"] if i + 1 < len(wd) else len(wp)
        ct = toks(" ".join((p.get("choices") or "") for p in wp[s:e]))
        if not ct or not gt:
            continue
        best = max(gt, key=lambda k: len(ct & gt[k]))
        if best != hdr and len(ct & gt[best]) > len(ct & gt.get(hdr, set())):
            bad.append((hdr, best))
    print(f"\n영작 best-match 오정렬: {len(bad)}/{len(wh)}")
    for h, b in bad[:40]:
        print(f"  {h} -> 진짜 {b}")
    print("\n[배열 헤더]", " / ".join(arr))
    if wh != arr:
        print("[영작 헤더]", " / ".join(wh))

if __name__ == "__main__":
    main()
