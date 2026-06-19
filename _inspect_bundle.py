#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검수 번들 생성기 — content.json 을 검수 에이전트가 읽기 좋은 형태로 변환.

사용: python3 _inspect_bundle.py <job_dir>
출력: <job_dir>/inspect_bundle.md
"""
import os
import sys
import json
import re


def snip(s, n=160):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:n] + ("…" if len(s) > n else "")


def hdr_key(h):
    """헤더 정렬키. '21강 01' / 'test1 23' 등."""
    m = re.match(r"(?:(\d+)강|test(\d+)|TEST(\d+))\s*0*(\d+)", str(h))
    if not m:
        return (9999, 9999, str(h))
    if m.group(1):
        return (0, int(m.group(1)), int(m.group(4)))
    t = m.group(2) or m.group(3)
    return (1, int(t), int(m.group(4)))


def main():
    jd = sys.argv[1]
    d = json.load(open(os.path.join(jd, "content.json"), encoding="utf-8"))
    school = d.get("school")
    grade = d.get("grade")
    exam = d.get("exam_period")
    v1 = d.get("vol1", {})
    v2 = d.get("vol2", {})

    arr = v1.get("문장배열", [])
    gram = v2.get("어법수정", [])
    gram_hdrs = v2.get("어법_헤더", [])
    wr = v2.get("서술형영작", [])
    wr_hdrs = v2.get("영작_헤더_상세", [])

    # 어법수정: [헤더, 본문, 헤더, 본문, ...] 페어로 묶기
    gram_map = {}
    i = 0
    gram_order = []
    while i < len(gram):
        h = gram[i]
        body = gram[i + 1] if i + 1 < len(gram) else ""
        gram_map[h] = body
        gram_order.append(h)
        i += 2

    # 영작: 헤더별 그룹화 (헤더 리스트와 pair 리스트가 평행 정렬이 아닐 수 있어
    # 영작_헤더_상세가 dict면 header/count, 아니면 문자열 리스트로 처리)
    wr_by_hdr = {}
    wr_hdr_order = []
    if wr_hdrs and isinstance(wr_hdrs[0], dict):
        # 각 헤더는 start_idx 를 가짐 → 다음 헤더 start_idx 까지가 해당 헤더의 pair 범위
        for k, hd in enumerate(wr_hdrs):
            hname = hd.get("header")
            s = hd.get("start_idx", 0)
            e = wr_hdrs[k + 1].get("start_idx", len(wr)) if k + 1 < len(wr_hdrs) else len(wr)
            wr_hdr_order.append(hname)
            wr_by_hdr[hname] = wr[s:e]
    else:
        for k, hname in enumerate(wr_hdrs):
            wr_hdr_order.append(hname)
            wr_by_hdr.setdefault(hname, [])
            if k < len(wr):
                wr_by_hdr[hname].append(wr[k])

    out = []
    out.append(f"# 검수 번들 — {school} / {grade} / {exam}\n")
    out.append(f"job_dir: {jd}\n")
    out.append(f"## 섹션별 개수\n")
    out.append(f"- 문장배열 블록: {len(arr)}")
    out.append(f"- 어법수정 지문: {len(gram_order)} (총 {len(gram)}줄)")
    out.append(f"- 서술형영작 헤더: {len(wr_hdr_order)} (총 pair {len(wr)})")
    out.append("")

    # 섹션별 헤더 순서 나열
    out.append("## 문장배열 헤더 순서")
    out.append(" / ".join(str(b.get("header")) for b in arr))
    out.append("")
    out.append("## 어법수정 헤더 순서")
    out.append(" / ".join(str(h) for h in gram_order))
    out.append("")
    out.append("## 서술형영작 헤더 순서")
    out.append(" / ".join(str(h) for h in wr_hdr_order))
    out.append("")

    # 헤더 통합 — 3섹션 교차 비교 (같은 헤더 = 같은 지문이어야 함)
    all_hdrs = []
    seen = set()
    for h in [b.get("header") for b in arr] + gram_order + wr_hdr_order:
        if h not in seen:
            seen.add(h)
            all_hdrs.append(h)
    all_hdrs.sort(key=hdr_key)

    arr_by_hdr = {}
    for b in arr:
        arr_by_hdr.setdefault(b.get("header"), b)

    out.append("## 헤더별 교차 대조 (문장배열 passage / 어법수정 본문 / 영작 한글)")
    out.append("같은 헤더는 동일 지문이어야 함. 세 섹션의 영어/한글 내용이 같은 글인지 확인.\n")
    for h in all_hdrs:
        out.append(f"### {h}")
        b = arr_by_hdr.get(h)
        if b:
            psg = b.get("passage") or " ".join(b.get("items", []))
            out.append(f"- [배열] ({len(b.get('items',[]))}문장) {snip(psg, 240)}")
        else:
            out.append("- [배열] ❌ 없음")
        if h in gram_map:
            out.append(f"- [어법] {snip(gram_map[h], 240)}")
        else:
            out.append("- [어법] ❌ 없음")
        if h in wr_by_hdr and wr_by_hdr[h]:
            ks = []
            for p in wr_by_hdr[h][:3]:
                ko = p.get("korean") if isinstance(p, dict) else str(p)
                ks.append(snip(ko, 90))
            out.append(f"- [영작] ({len(wr_by_hdr[h])}문장) " + " | ".join(ks))
        else:
            out.append("- [영작] ❌ 없음")
        out.append("")

    rep = os.path.join(jd, "inspect_bundle.md")
    open(rep, "w", encoding="utf-8").write("\n".join(out))
    print(rep)


if __name__ == "__main__":
    main()
