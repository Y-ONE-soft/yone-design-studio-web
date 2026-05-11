#!/usr/bin/env python3
"""
자동 실행 결과 .indd vs 최종파일 .indd 비교.

각 단락별로:
- 텍스트는 같지만 단락스타일이 다른 경우 → STYLE_ALIAS 필요
- 자동에는 있는데 최종에 없는 단락 → 자동이 더 추가됨 (오류)
- 최종에는 있는데 자동에 없는 단락 → 최종에서 별도 추가됨 (페이스트보드 헤더 등)

Usage:
    python3 compare_auto_vs_final.py <auto_json> <final_json>
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict


def nfc(s):
    return unicodedata.normalize("NFC", s)


_RE_SCORE_TAIL = re.compile(r"\s*[\[\(]\s*(?:각\s*)?[\d.]+\s*점\s*[\]\)]\s*$")


def text_key(text, length=60):
    if not text:
        return ""
    s = nfc(text).strip()
    s = re.sub(r"\s+", " ", s)
    s = _RE_SCORE_TAIL.sub("", s).strip()
    if len(s) > length:
        return s[:length]
    return s


def collect_paragraphs(indd_data):
    paras = []
    for pi, pg in enumerate(indd_data.get("pages", [])):
        for tfi, tf in enumerate(pg.get("text_frames", [])):
            for p_idx, p in enumerate(tf.get("paragraphs", [])):
                if "text" not in p:
                    continue
                t = p["text"].strip()
                if not t:
                    continue
                paras.append({
                    "page_idx": pi,
                    "page_name": pg.get("page_name"),
                    "page_side": pg.get("side"),
                    "tf_idx": tfi,
                    "tf_label": tf.get("label", ""),
                    "tf_threaded": tf.get("threaded_prev") or tf.get("threaded_next"),
                    "para_idx": p_idx,
                    "text": p["text"],
                    "pstyle": p.get("pstyle", ""),
                })
    return paras


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 compare_auto_vs_final.py <auto_json> <final_json>")
        sys.exit(1)

    auto_path = sys.argv[1]
    final_path = sys.argv[2]
    with open(auto_path, encoding="utf-8") as f:
        auto = json.load(f)
    with open(final_path, encoding="utf-8") as f:
        final = json.load(f)

    auto_paras = collect_paragraphs(auto)
    final_paras = collect_paragraphs(final)

    print(f"AUTO: {auto.get('basename')} - {auto.get('page_count')}페이지, {len(auto_paras)}단락")
    print(f"FINAL: {final.get('basename')} - {final.get('page_count')}페이지, {len(final_paras)}단락")

    # 텍스트 키 인덱스
    auto_by_key = defaultdict(list)
    for p in auto_paras:
        k = text_key(p["text"])
        if k:
            auto_by_key[k].append(p)
    final_by_key = defaultdict(list)
    for p in final_paras:
        k = text_key(p["text"])
        if k:
            final_by_key[k].append(p)

    # 매칭: auto와 final 단락 한 번씩
    auto_used = set()
    final_used = set()
    matches = []  # (auto_para, final_para)
    for i, p in enumerate(auto_paras):
        k = text_key(p["text"])
        cands = final_by_key.get(k, [])
        for cp in cands:
            cid = id(cp)
            if cid not in final_used:
                matches.append((p, cp))
                auto_used.add(i)
                final_used.add(cid)
                break

    matched = len(matches)
    print(f"매칭: {matched}/{len(auto_paras)} ({matched*100/max(1,len(auto_paras)):.0f}% of auto), "
          f"{matched*100/max(1,len(final_paras)):.0f}% of final")

    # 매핑 빈도 (auto pstyle → final pstyle)
    style_freq = defaultdict(Counter)
    style_diff = []
    for (a, f) in matches:
        style_freq[a["pstyle"]][f["pstyle"]] += 1
        if a["pstyle"] != f["pstyle"]:
            style_diff.append((a, f))

    print(f"\n=== 스타일 매핑 ===")
    for ap in sorted(style_freq.keys()):
        c = style_freq[ap]
        tops = c.most_common(8)
        print(f"  {ap:25} → " + ", ".join(f"{fp}={n}" for fp, n in tops))

    # 같지 않은 케이스 샘플
    print(f"\n=== AUTO ↔ FINAL 단락스타일 차이 (총 {len(style_diff)}개, 샘플 20개) ===")
    for (a, f) in style_diff[:20]:
        t = a["text"][:80].replace("\n", " ")
        print(f"  [auto:{a['pstyle']}] → [final:{f['pstyle']}]")
        print(f"     {t!r}")

    # final에만 있는 단락 (자동이 못 만든 것)
    final_only = [p for p in final_paras if id(p) not in final_used]
    print(f"\n=== FINAL에만 있는 단락 (자동 누락, 총 {len(final_only)}개) — 샘플 ===")
    fo_styles = Counter(p["pstyle"] for p in final_only)
    for ps, n in fo_styles.most_common(10):
        print(f"  {ps}: {n}개")
    for p in final_only[:10]:
        t = p["text"][:80].replace("\n", " ")
        print(f"  [{p['pstyle']}] page={p['page_name']} tf_lbl={p['tf_label']!r} {t!r}")

    # auto에만 있는 단락 (자동이 추가로 만든 것)
    auto_only = [p for i, p in enumerate(auto_paras) if i not in auto_used]
    print(f"\n=== AUTO에만 있는 단락 (자동이 추가, 총 {len(auto_only)}개) — 샘플 ===")
    ao_styles = Counter(p["pstyle"] for p in auto_only)
    for ps, n in ao_styles.most_common(10):
        print(f"  {ps}: {n}개")
    for p in auto_only[:10]:
        t = p["text"][:80].replace("\n", " ")
        print(f"  [{p['pstyle']}] page={p['page_name']} {t!r}")


if __name__ == "__main__":
    main()
