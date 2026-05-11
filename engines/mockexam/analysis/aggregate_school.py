#!/usr/bin/env python3
"""
학교 단위로 모든 회차의 ms/indd를 풀링하여 매핑 빈도 추출.

회차가 잘못 매핑된 케이스 (1회 ms vs 2회 indd 등)도 학교 단위에서는 매칭됨.

산출:
- analysis/comparison/_school_mapping.json: 학교별 (parser_pstyle, final_pstyle) → count
- 콘솔: 학교별 표 출력
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

ROOT = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판"
ANALYSIS = os.path.join(ROOT, "조판_자동화", "engines", "mockexam", "analysis")
MS_DIR = os.path.join(ANALYSIS, "manuscript_data")
INDD_DIR = os.path.join(ANALYSIS, "indd_data")
OUT_DIR = os.path.join(ANALYSIS, "comparison")


def nfc(s):
    return unicodedata.normalize("NFC", s)


_RE_SCORE_TAIL = re.compile(r"\s*[\[\(]\s*(?:각\s*)?[\d.]+\s*점\s*[\]\)]\s*$")


def text_key(text, length=50):
    """매칭용 정규화: 공백 압축, 끝의 점수 표기 제거, 길이 제한.

    indd는 단락 끝에 [2.6점] / (1.3점) / [각 1.5점] 같은 점수 표기가 추가됨.
    ms 원고에는 없으므로 매칭 키에서 제거.
    """
    if not text:
        return ""
    s = nfc(text).strip()
    s = re.sub(r"\s+", " ", s)
    s = _RE_SCORE_TAIL.sub("", s).strip()
    if len(s) > length:
        return s[:length]
    return s


SHORT_MAP = {
    "강동고": "강동", "광문고": "광문", "명일여고": "명일",
    "배재고": "배재", "상일여고": "상일", "성덕고": "성덕",
    "한영고": "한영"
}


def collect_school_ms(school):
    """학교의 모든 회차 ms 단락 풀링."""
    paras = []
    grade_num = None
    for fname in sorted(os.listdir(MS_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        if not fname.startswith(school + "_"):
            continue
        m = re.match(r"(.+?)_(\d)_(\d)\.json$", fname)
        if not m or m.group(1) != school:
            continue
        grade = m.group(2)
        round_num = m.group(3)
        with open(os.path.join(MS_DIR, fname), encoding="utf-8") as f:
            d = json.load(f)
        for q in d.get("questions", []):
            for p in q.get("paragraphs", []):
                paras.append({
                    "grade": grade,
                    "round": round_num,
                    "pstyle": p.get("pstyle", ""),
                    "text": p["text"]
                })
    return paras


def collect_school_indd(school):
    """학교의 모든 회차 indd 단락 풀링."""
    short = SHORT_MAP.get(school)
    if not short:
        return []
    paras = []
    for fname in sorted(os.listdir(INDD_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        if not nfc(fname).startswith(short):
            continue
        full = os.path.join(INDD_DIR, fname)
        if os.path.getsize(full) == 0:
            continue
        try:
            with open(full, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        # 학년/회차 추출
        m = re.match(r"(.+?)(\d)_동형모의고사\((\d)회\)\.json$", nfc(fname))
        grade = m.group(2) if m else "?"
        round_num = m.group(3) if m else "?"
        for pg in d.get("pages", []):
            for tf in pg.get("text_frames", []):
                for p in tf.get("paragraphs", []):
                    if "text" not in p:
                        continue
                    paras.append({
                        "grade": grade,
                        "round": round_num,
                        "page_name": pg.get("page_name"),
                        "tf_label": tf.get("label", ""),
                        "tf_threaded": tf.get("threaded_prev") or tf.get("threaded_next"),
                        "pstyle": p.get("pstyle", ""),
                        "text": p["text"]
                    })
    return paras


def match_pool(ms_paras, indd_paras):
    """학교 단위 풀에서 텍스트 매칭. 같은 키의 indd 단락을 한 번씩만 사용."""
    indd_by_key = defaultdict(list)
    for i, p in enumerate(indd_paras):
        k = text_key(p["text"])
        if k:
            indd_by_key[k].append(i)
    used = [False] * len(indd_paras)

    matches = []  # (ms_para, indd_para or None)
    for mp in ms_paras:
        k = text_key(mp["text"])
        cands = indd_by_key.get(k, [])
        chosen = None
        for ci in cands:
            if not used[ci]:
                used[ci] = True
                chosen = indd_paras[ci]
                break
        matches.append((mp, chosen))

    extras = [(i, p) for i, p in enumerate(indd_paras) if not used[i]]
    return matches, extras


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 학교별 매핑 빈도: school → (parser_pstyle, ms_grade) → final_pstyle → count
    by_school = {}

    for school in SHORT_MAP.keys():
        ms = collect_school_ms(school)
        indd = collect_school_indd(school)
        if not ms or not indd:
            continue
        matches, extras = match_pool(ms, indd)

        # 학년 단위로 더 분석 (학년별 단락 스타일이 다를 수 있음)
        # 먼저 전체 카운트
        freq = defaultdict(Counter)  # parser_ps → final_ps → count
        unmatched = Counter()
        # 학년별 카운트
        by_grade = defaultdict(lambda: defaultdict(Counter))

        for (mp, ip) in matches:
            ps_parser = mp["pstyle"]
            grade = mp["grade"]
            if ip is None:
                unmatched[ps_parser] += 1
                continue
            freq[ps_parser][ip["pstyle"]] += 1
            by_grade[grade][ps_parser][ip["pstyle"]] += 1

        matched_count = sum(1 for (m, i) in matches if i is not None)
        rate = matched_count * 100 / max(1, len(ms))
        print(f"\n=== {school} ===")
        print(f"  ms={len(ms)}, indd={len(indd)}, matched={matched_count} ({rate:.0f}%)")
        print(f"  학년별 ms: {Counter(p['grade'] for p in ms)}")

        print(f"  parser_pstyle → final_pstyle (학교 통합):")
        for ps in sorted(freq.keys()):
            tops = freq[ps].most_common(8)
            print(f"    {ps:18}: " + ", ".join(f"{fp}={n}" for fp, n in tops))

        # 학년별 (영어교재 학년이 다르면 매핑 다를 가능성)
        for grade in sorted(by_grade.keys()):
            print(f"  학년 {grade}:")
            for ps in sorted(by_grade[grade].keys()):
                tops = by_grade[grade][ps].most_common(5)
                print(f"    {ps:18}: " + ", ".join(f"{fp}={n}" for fp, n in tops))

        by_school[school] = {
            "ms_total": len(ms),
            "indd_total": len(indd),
            "matched": matched_count,
            "match_rate": rate,
            "freq_all": {ps: dict(c) for ps, c in freq.items()},
            "unmatched": dict(unmatched),
            "freq_by_grade": {g: {ps: dict(c) for ps, c in v.items()} for g, v in by_grade.items()}
        }

    out_path = os.path.join(OUT_DIR, "_school_mapping.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(by_school, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] {out_path}")


if __name__ == "__main__":
    main()
