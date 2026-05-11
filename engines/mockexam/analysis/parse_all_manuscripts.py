#!/usr/bin/env python3
"""
모든 동형 원고를 파싱하여 학교/학년/회차별 content.json 생성.

원고 폴더의 모든 hwpx/hwp 파일을 대상으로:
- 파일명에서 학교/학년/회차 추출
- parser.parse_manuscript()로 파싱
- 결과를 manuscript_data/{학교}_{학년}_{회차}.json으로 저장
"""

import os
import re
import sys
import json
import unicodedata

# 경로 추가
ROOT = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판"
sys.path.insert(0, os.path.join(ROOT, "조판_자동화"))

from engines.mockexam.parser import parse_manuscript


def nfc(s):
    return unicodedata.normalize("NFC", s)


SOURCE = os.path.join(ROOT, "교재", "동형모의고사", "원고")
OUTPUT = os.path.join(ROOT, "조판_자동화", "engines", "mockexam", "analysis", "manuscript_data")


def detect_school_grade(filename):
    """파일명에서 (학교, 학년) 추출.

    예시:
    - "26-1-중간 명일1 동형 1회 원고.hwpx" → ("명일여고", "고1")
    - "강동고2 동형 1회 원고 최종.hwpx" → ("강동고", "고2")
    - "한영고1 동형 1회 원고_최종.hwp" → ("한영고", "고1")
    - "26-1-중간 명일여고3_동형 1회.hwpx" → ("명일여고", "고3")
    - "26-1-중간 강동고3 동형 1회 원고_단어 추가 최종.hwpx" → ("강동고", "고3")
    - "26-1-중간 한영고3 동형 모의고사 1회 원고.hwpx" → ("한영고", "고3")
    """
    f = nfc(filename)
    # 학교
    school = None
    if "강동" in f:
        school = "강동고"
    elif "광문" in f:
        school = "광문고"
    elif "명일" in f:
        school = "명일여고"
    elif "배재" in f:
        school = "배재고"
    elif "상일" in f:
        school = "상일여고"
    elif "성덕" in f:
        school = "성덕고"
    elif "한영" in f:
        school = "한영고"

    # 학년: 학교명 뒤 숫자, "고N" 또는 "여고N"
    grade = None
    # 패턴 1: 학교명 + (고)? + 숫자 + (공백|_)
    m = re.search(r"(?:강동|광문|명일|배재|상일|성덕|한영)\s*(?:여)?\s*고?\s*([123])", f)
    if m:
        grade = "고" + m.group(1)

    return school, grade


def detect_round(filename):
    """파일명에서 회차 추출."""
    f = nfc(filename)
    m = re.search(r"(\d+)\s*회", f)
    return int(m.group(1)) if m else None


def main():
    if not os.path.isdir(SOURCE):
        print(f"[오류] 원고 폴더 없음: {SOURCE}")
        sys.exit(1)
    os.makedirs(OUTPUT, exist_ok=True)

    files = sorted(os.listdir(SOURCE))
    files = [f for f in files if f.lower().endswith((".hwpx", ".hwp", ".docx"))]

    summary = []
    log = print
    for fname in files:
        fpath = os.path.join(SOURCE, fname)
        school, grade = detect_school_grade(fname)
        round_num = detect_round(fname)

        if not (school and grade and round_num):
            print(f"[스킵] 파일명 파싱 실패: {fname} → (school={school}, grade={grade}, round={round_num})")
            summary.append({
                "file": fname, "school": school, "grade": grade, "round": round_num,
                "status": "skip_filename_parse_failed"
            })
            continue

        try:
            print(f"[파싱] {fname} → {school} {grade} {round_num}회")
            content = parse_manuscript(
                fpath, school, grade,
                exam_period="26-1-중간",
                exam_date="",
                exam_type="",
                round_num=round_num,
                log=lambda x: None  # 노이즈 줄임
            )
            grade_num = grade.replace("고", "")
            out_name = f"{school}_{grade_num}_{round_num}.json"
            out_path = os.path.join(OUTPUT, out_name)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)

            n_questions = len(content.get("questions", []))
            n_paras = sum(len(q.get("paragraphs", [])) for q in content.get("questions", []))
            print(f"  → {out_name}: {n_questions}문제, {n_paras}단락")
            summary.append({
                "file": fname, "school": school, "grade": grade, "round": round_num,
                "status": "ok", "questions": n_questions, "paragraphs": n_paras,
                "output": out_name
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  → 오류: {e}")
            summary.append({
                "file": fname, "school": school, "grade": grade, "round": round_num,
                "status": "error", "error": str(e)
            })

    # 요약 저장
    with open(os.path.join(OUTPUT, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 총 {len(files)}개 → 처리 {sum(1 for x in summary if x['status']=='ok')}개")


if __name__ == "__main__":
    main()
