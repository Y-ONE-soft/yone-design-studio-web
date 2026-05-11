#!/usr/bin/env python3
"""
정밀 단락 단위 매핑 분석.

학교 1회 final indd의 각 단락에 대해:
- 페이지 / textframe / 단락 위치 / 단락 스타일 / 텍스트
- 페이스트보드 헤더와의 매칭 (박스 단락 옆에 어떤 헤더가 있어야 하는지)
- 원고 파싱 결과의 어떤 단락에 매칭되는지
- 자동 결과의 어떤 단락에 매칭되는지

산출: school_grade_round.precise.md (Markdown 표)
"""

import os
import re
import sys
import json
import unicodedata
from collections import defaultdict


def nfc(s):
    return unicodedata.normalize("NFC", s)


_RE_SCORE_TAIL = re.compile(r"\s*[\[\(]\s*(?:각\s*)?[\d.]+\s*점\s*[\]\)]\s*$")


def text_key(text, length=50):
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
                    "tf_bounds": tf.get("bounds", []),
                    "tf_threaded": tf.get("threaded_prev") or tf.get("threaded_next"),
                    "para_idx": p_idx,
                    "text": p["text"],
                    "pstyle": p.get("pstyle", ""),
                })
    return paras


def collect_pasteboard_headers(pb_data):
    headers = []
    for sp in pb_data.get("spreads", []):
        for it in sp.get("items_outside_pages", []):
            if it.get("type") != "TextFrame":
                continue
            preview = (it.get("text_preview") or "").strip()
            if not preview:
                continue
            headers.append({
                "spread": sp.get("index"),
                "bounds": it.get("bounds", []),
                "text": preview,
            })
    return headers


def header_category(text):
    """헤더 텍스트프레임의 박스 카테고리."""
    t = text or ""
    s = "".join(c for c in t if "가" <= c <= "힣")
    if "요약문" in s or "요약" in s:
        return "요약"
    if "보기" in s:
        return "보기"
    if "조건" in s:
        return "조건"
    if "우리말" in s:
        return "우리말"
    if any(c in t for c in "⇓↓⬇\x16"):
        return "화살표"
    return None


def classify_box_pstyle(pstyle):
    """단락 스타일 → 박스 카테고리."""
    if not pstyle:
        return None
    if "보기" in pstyle and "테두리" in pstyle:
        return "보기"
    if "조건" in pstyle and "테두리" in pstyle:
        return "조건"
    if "요약" in pstyle and "테두리" in pstyle:
        return "요약"
    if "순서" in pstyle and "테두리" in pstyle:
        return "보기"  # 순서삽입은 보기 헤더 재사용 가능
    if pstyle == "테두리":
        return "보기"  # 통합 테두리 — 보기/조건 어느 쪽이든
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 precise_mapping.py <school_grade_round>")
        print("예: python3 precise_mapping.py 명일여고_1_1")
        sys.exit(1)
    sgr = sys.argv[1]
    parts = sgr.split("_")
    school, grade, round_num = parts[0], parts[1], parts[2]
    short_map = {"강동고": "강동", "광문고": "광문", "명일여고": "명일",
                 "배재고": "배재", "상일여고": "상일", "성덕고": "성덕",
                 "한영고": "한영"}
    short = short_map.get(school)

    ROOT = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판"
    ANA = os.path.join(ROOT, "조판_자동화", "engines", "mockexam", "analysis")
    indd_json = os.path.join(ANA, "indd_data", f"{short}{grade}_동형모의고사({round_num}회).json")
    pb_json = os.path.join(ANA, "pasteboard_data2", f"{short}{grade}_동형모의고사({round_num}회).json")
    ms_json = os.path.join(ANA, "manuscript_data", f"{school}_{grade}_{round_num}.json")

    if not os.path.exists(indd_json):
        print(f"[오류] indd JSON 없음: {indd_json}")
        sys.exit(1)
    with open(indd_json, encoding="utf-8") as f:
        indd_data = json.load(f)
    pb_data = None
    if os.path.exists(pb_json):
        with open(pb_json, encoding="utf-8") as f:
            pb_data = json.load(f)
    ms_data = None
    if os.path.exists(ms_json):
        with open(ms_json, encoding="utf-8") as f:
            ms_data = json.load(f)

    indd_paras = collect_paragraphs(indd_data)
    headers = collect_pasteboard_headers(pb_data) if pb_data else []

    # 페이스트보드 헤더 카테고리 인덱싱
    headers_by_cat = {}
    for h in headers:
        cat = header_category(h["text"])
        if cat and cat not in headers_by_cat:
            headers_by_cat[cat] = h
    print(f"[헤더 인덱스] {list(headers_by_cat.keys())}")

    # 원고 단락 인덱싱
    ms_by_key = {}
    if ms_data:
        for q in ms_data.get("questions", []):
            for p in q.get("paragraphs", []):
                k = text_key(p["text"])
                if k:
                    ms_by_key[k] = p

    # 출력 파일
    out_path = os.path.join(ANA, f"{sgr}.precise.md")
    out = open(out_path, "w", encoding="utf-8")
    out.write(f"# {sgr} 정밀 단락 매핑\n\n")
    out.write(f"- final indd 페이지: {indd_data.get('page_count')}\n")
    out.write(f"- 단락 수: {len(indd_paras)}\n")
    out.write(f"- 페이스트보드 헤더: {len(headers)}개 (카테고리: {list(headers_by_cat.keys())})\n")
    out.write(f"- 원고 단락 수: {sum(len(q['paragraphs']) for q in ms_data.get('questions', [])) if ms_data else 0}\n\n")

    # 페이지/textframe 단위로 그룹화
    pages = defaultdict(lambda: defaultdict(list))
    for p in indd_paras:
        pages[p["page_idx"]][p["tf_idx"]].append(p)

    out.write("## 페이지/단락 매핑 표\n\n")
    out.write("| 페이지 | TF | TF bounds | 단락스타일 | 텍스트 (앞 60자) | 원고 매칭 | 박스헤더 |\n")
    out.write("|---|---|---|---|---|---|---|\n")

    for pi in sorted(pages.keys()):
        for tfi in sorted(pages[pi].keys()):
            for para in pages[pi][tfi]:
                t = para["text"][:60].replace("\n", " ").replace("|", "\\|")
                pstyle = para["pstyle"] or "—"
                bnds = para.get("tf_bounds", [])
                bnds_str = "[" + ",".join(f"{b:.0f}" for b in bnds[:4]) + "]" if bnds else "—"

                # 원고 매칭
                k = text_key(para["text"])
                ms_entry = ms_by_key.get(k)
                ms_pstyle = ms_entry["pstyle"] if ms_entry else "✗"

                # 박스 헤더 매칭
                cat = classify_box_pstyle(pstyle)
                hdr = ""
                if cat and cat in headers_by_cat:
                    h = headers_by_cat[cat]
                    hdr_bnds = "[" + ",".join(f"{b:.0f}" for b in h["bounds"][:4]) + "]"
                    hdr = f"{h['text']!r} {hdr_bnds}"

                out.write(f"| p{para['page_name']} | {tfi} | {bnds_str} | {pstyle} | {t} | {ms_pstyle} | {hdr} |\n")
        out.write("\n")

    out.write("\n## 페이스트보드 헤더 인벤토리\n\n")
    out.write("| 카테고리 | 텍스트 | 위치 (y1, x1, y2, x2) |\n")
    out.write("|---|---|---|\n")
    for h in headers:
        cat = header_category(h["text"])
        bnds_str = ",".join(f"{b:.2f}" for b in h["bounds"][:4])
        out.write(f"| {cat} | {h['text']!r} | [{bnds_str}] |\n")

    out.close()
    print(f"[저장] {out_path}")


if __name__ == "__main__":
    main()
