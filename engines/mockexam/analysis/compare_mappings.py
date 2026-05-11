#!/usr/bin/env python3
"""
원고 파싱 결과 (manuscript_data/) vs 최종파일 분석 (indd_data/) 매칭/비교.

각 학교+학년+회차별로:
- 원고 단락의 parser_pstyle
- 최종파일 단락의 final_pstyle
을 텍스트로 매칭하여 (parser_pstyle → final_pstyle) 빈도 분석.

산출:
- analysis/comparison/{학교}_{학년}_{회차}.json: 단락별 매칭 + 미매칭
- analysis/comparison/_mapping_freq.json: 학교별 매핑 빈도
- analysis/comparison/_unmapped.json: 매칭 안 된 원고 단락 (분류 누락 신호)
- analysis/comparison/_extra_in_final.json: 최종에는 있지만 원고에 없는 단락 (별도 개체 후보)
"""

import os
import re
import sys
import json
import unicodedata
from collections import Counter, defaultdict

ROOT = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판"
ANALYSIS = os.path.join(ROOT, "조판_자동화", "engines", "mockexam", "analysis")
MS_DIR = os.path.join(ANALYSIS, "manuscript_data")
INDD_DIR = os.path.join(ANALYSIS, "indd_data")
OUT_DIR = os.path.join(ANALYSIS, "comparison")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def norm_for_match(text):
    """매칭용 정규화: 공백 압축, 좌우 strip, 길이 제한."""
    if not text:
        return ""
    # 비한글/영어/숫자 제거 안 함, 다만 양쪽 공백/제어문자 제거
    s = nfc(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def text_key(text, length=40):
    """텍스트 키: 정규화 후 앞 length자."""
    s = norm_for_match(text)
    if len(s) > length:
        return s[:length]
    return s


def find_indd_file(school, grade, round_num):
    """학교/학년/회차에 해당하는 indd_data JSON 파일 찾기."""
    short_map = {
        "강동고": "강동", "광문고": "광문", "명일여고": "명일",
        "배재고": "배재", "상일여고": "상일", "성덕고": "성덕",
        "한영고": "한영"
    }
    short = short_map.get(school)
    if not short:
        return None
    pattern = f"{short}{grade}_동형모의고사({round_num}회).json"
    candidates = [pattern]
    for p in candidates:
        full = os.path.join(INDD_DIR, p)
        if os.path.exists(full):
            return full
    # 부분 매칭
    for f in os.listdir(INDD_DIR):
        if not f.endswith(".json"):
            continue
        if f.startswith("_"):
            continue
        f_nfc = nfc(f)
        if (short in f_nfc and grade in f_nfc and
            f"({round_num}회)" in f_nfc):
            return os.path.join(INDD_DIR, f)
    return None


def collect_indd_paragraphs(indd_data):
    """최종파일 분석 데이터에서 단락 목록 추출 (페이지 순)."""
    paras = []
    for pg in indd_data.get("pages", []):
        for tf_idx, tf in enumerate(pg.get("text_frames", [])):
            for p_idx, p in enumerate(tf.get("paragraphs", [])):
                if "text" not in p:
                    continue
                paras.append({
                    "page_index": pg.get("page_index"),
                    "page_name": pg.get("page_name"),
                    "page_side": pg.get("side"),
                    "tf_idx": tf_idx,
                    "tf_bounds": tf.get("bounds"),
                    "tf_label": tf.get("label", ""),
                    "tf_threaded": tf.get("threaded_prev") or tf.get("threaded_next"),
                    "para_idx": p_idx,
                    "text": p["text"],
                    "pstyle": p.get("pstyle", ""),
                    "primary_cstyle": p.get("primary_cstyle", ""),
                })
    return paras


def collect_ms_paragraphs(content):
    """원고 content.json에서 단락 목록 추출."""
    paras = []
    qs = content.get("questions", [])
    for qi, q in enumerate(qs):
        for pi, p in enumerate(q.get("paragraphs", [])):
            paras.append({
                "q_idx": qi,
                "p_idx": pi,
                "source": q.get("source", ""),
                "text": p["text"],
                "pstyle": p.get("pstyle", ""),
            })
    return paras


def match_paragraphs(ms_paras, indd_paras):
    """원고 단락 ↔ 최종 단락 매칭 (텍스트 키 기반).

    Returns: list of (ms_para, indd_para or None)
            + extra_indd_paras (매칭 안 된 indd 단락들)
    """
    # indd 인덱스: 텍스트 키 → indd_para (중복은 리스트)
    indd_by_key = defaultdict(list)
    indd_used = [False] * len(indd_paras)
    for i, p in enumerate(indd_paras):
        k = text_key(p["text"])
        if k:
            indd_by_key[k].append((i, p))

    matches = []
    for mp in ms_paras:
        k = text_key(mp["text"])
        candidates = indd_by_key.get(k, [])
        chosen = None
        for (ci, cp) in candidates:
            if not indd_used[ci]:
                indd_used[ci] = True
                chosen = cp
                break
        matches.append((mp, chosen))

    extras = [(i, p) for i, p in enumerate(indd_paras) if not indd_used[i]]
    return matches, extras


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    summary_path = os.path.join(MS_DIR, "_summary.json")
    if not os.path.exists(summary_path):
        print(f"[오류] 원고 요약 없음: {summary_path}")
        sys.exit(1)
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    # 매핑 빈도: school → parser_pstyle → final_pstyle → count
    mapping_freq = defaultdict(lambda: defaultdict(Counter))
    # 학교별 미매칭 원고 단락
    unmapped = defaultdict(list)
    # 학교별 최종-only 단락 (별도 개체 후보)
    extras = defaultdict(list)

    overall_results = []

    for entry in summary:
        if entry.get("status") != "ok":
            continue
        school = entry["school"]
        grade = entry["grade"]
        grade_num = grade.replace("고", "")
        round_num = entry["round"]

        ms_path = os.path.join(MS_DIR, f"{school}_{grade_num}_{round_num}.json")
        indd_path = find_indd_file(school, grade_num, round_num)

        if not indd_path:
            print(f"[스킵] indd 매칭 실패: {school} {grade} {round_num}회")
            continue
        if os.path.getsize(indd_path) == 0:
            print(f"[스킵] indd 빈 파일: {school} {grade} {round_num}회")
            continue

        with open(ms_path, encoding="utf-8") as f:
            ms_content = json.load(f)
        try:
            with open(indd_path, encoding="utf-8") as f:
                indd_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[스킵] indd 파싱 실패 ({school} {grade} {round_num}): {e}")
            continue

        ms_paras = collect_ms_paragraphs(ms_content)
        indd_paras = collect_indd_paragraphs(indd_data)
        matches, extra_indds = match_paragraphs(ms_paras, indd_paras)

        # 빈도 누적
        matched_count = 0
        for (mp, ip) in matches:
            if ip is None:
                if mp["text"].strip():
                    unmapped[school].append({
                        "grade": grade, "round": round_num,
                        "parser_pstyle": mp["pstyle"],
                        "text": mp["text"][:120]
                    })
                continue
            mapping_freq[school][mp["pstyle"]][ip["pstyle"]] += 1
            matched_count += 1

        for (i, ip) in extra_indds:
            if ip["text"].strip():
                extras[school].append({
                    "grade": grade, "round": round_num,
                    "final_pstyle": ip["pstyle"],
                    "tf_label": ip["tf_label"],
                    "tf_bounds": ip["tf_bounds"],
                    "page_name": ip["page_name"],
                    "tf_threaded": ip["tf_threaded"],
                    "text": ip["text"][:120]
                })

        # 학교별 결과 저장
        per_file = {
            "school": school, "grade": grade, "round": round_num,
            "ms_paras": len(ms_paras),
            "indd_paras": len(indd_paras),
            "matched": matched_count,
            "unmatched_ms": len(ms_paras) - matched_count,
            "extra_indd": len(extra_indds),
            "matches": [
                {
                    "ms": {"q": mp["q_idx"], "p": mp["p_idx"], "pstyle": mp["pstyle"], "text": mp["text"][:80]},
                    "final": (None if ip is None else {
                        "page": ip["page_name"], "pstyle": ip["pstyle"], "tf_label": ip["tf_label"], "text": ip["text"][:80]
                    })
                }
                for (mp, ip) in matches
            ]
        }
        out_name = f"{school}_{grade_num}_{round_num}.json"
        with open(os.path.join(OUT_DIR, out_name), "w", encoding="utf-8") as f:
            json.dump(per_file, f, ensure_ascii=False, indent=2)

        print(f"[{school} {grade} {round_num}회] ms={len(ms_paras)}, indd={len(indd_paras)}, matched={matched_count} ({matched_count*100/max(1,len(ms_paras)):.0f}%)")
        overall_results.append(per_file)

    # 통합 매핑 빈도
    mapping_freq_serializable = {
        sch: {ps: dict(cnt) for ps, cnt in mp.items()}
        for sch, mp in mapping_freq.items()
    }
    with open(os.path.join(OUT_DIR, "_mapping_freq.json"), "w", encoding="utf-8") as f:
        json.dump(mapping_freq_serializable, f, ensure_ascii=False, indent=2)

    # 미매칭 원고 단락
    with open(os.path.join(OUT_DIR, "_unmapped_manuscript.json"), "w", encoding="utf-8") as f:
        json.dump(unmapped, f, ensure_ascii=False, indent=2)

    # 최종-only 단락 (별도 개체 후보)
    with open(os.path.join(OUT_DIR, "_extra_in_final.json"), "w", encoding="utf-8") as f:
        json.dump(extras, f, ensure_ascii=False, indent=2)

    # 통계 요약
    print("\n=== 학교별 매핑 빈도 (Top 5 per parser pstyle) ===")
    for sch in sorted(mapping_freq.keys()):
        print(f"\n[{sch}]")
        for parser_ps in sorted(mapping_freq[sch].keys()):
            c = mapping_freq[sch][parser_ps]
            top = c.most_common(5)
            tops = ", ".join(f"{fp}={n}" for fp, n in top)
            print(f"  {parser_ps:20} → {tops}")

    print(f"\n[저장] {OUT_DIR}")


if __name__ == "__main__":
    main()
