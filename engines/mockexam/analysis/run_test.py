#!/usr/bin/env python3
"""
mockexam 엔진을 학교/학년/회차 단위로 직접 실행하는 테스트 스크립트.

Usage:
    python3 run_test.py 명일여고 고1 1
"""

import os
import sys
import json
import tempfile
import shutil

ROOT = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판"
sys.path.insert(0, os.path.join(ROOT, "조판_자동화"))

from engines.mockexam.engine import MockexamEngine


# 원고 파일 매핑: 학교+학년 → 회차 → 파일경로
MS_DIR = os.path.join(ROOT, "교재", "동형모의고사", "원고")

# 학교+학년+회차 → 원고 파일명 매핑
MS_FILES = {
    ("강동고", "고1"): {
        1: "강동고1 동형 1회 원고.hwpx",
        2: "강동고1 동형 2회 원고.hwpx",
    },
    ("강동고", "고2"): {
        1: "강동고2 동형 1회 원고 최종.hwpx",
        2: "강동고2 동형 2회 원고_최종.hwpx",
    },
    ("강동고", "고3"): {
        1: "26-1-중간 강동고3 동형 1회 원고_단어 추가 최종.hwpx",
        2: "26-1-중간 강동고3 동형 2회 원고_단어 추가 최종.hwpx",
    },
    ("명일여고", "고1"): {
        1: "26-1-중간 명일1 동형 1회 원고.hwpx",
        2: "26-1-중간 명일1 동형 2회 원고.hwpx",
    },
    ("명일여고", "고2"): {
        1: "26-1-중간 명일2 동형 1회 원고.hwpx",
        2: "26-1-중간 명일2 동형 2회 원고.hwpx",
    },
    ("명일여고", "고3"): {
        1: "26-1-중간 명일여고3_동형 1회.hwpx",
        2: "26-1-중간 명일여고3_동형 2회.hwpx",
    },
    ("배재고", "고1"): {
        1: "배재1 동형 1회 원고.hwpx",
        2: "배재1 동형 2회 원고.hwpx",
    },
    ("배재고", "고2"): {
        1: "배재2 동형 1회 원고(수정).hwpx",
        2: "배재2 동형 2회 원고(수정).hwpx",
    },
    ("상일여고", "고1"): {
        1: "26-1-중간 상일1 동형 1회 원고.hwpx",
        2: "26-1-중간 상일1 동형 2회 원고.hwpx",
    },
    ("상일여고", "고2"): {
        1: "26-1-중간 상일2 동형 1회 원고.hwpx",
        2: "26-1-중간 상일2 동형 2회 원고.hwpx",
    },
    ("성덕고", "고1"): {
        1: "성덕1 동형 1회 원고.hwpx",
        2: "성덕1 동형 2회 원고.hwpx",
    },
    ("성덕고", "고2"): {
        1: "성덕고2 동형 1회 원고.hwpx",
        2: "성덕고2 동형 2회 원고.hwpx",
    },
    ("한영고", "고1"): {
        1: "한영고1 동형 1회 원고_최종.hwp",
        2: "한영고1 동형 2회 원고_최종.hwp",
    },
    ("한영고", "고2"): {
        1: "한영고2 동형 1회 원고 최종.hwp",
        2: "한영고2 동형 2회 원고 최종.hwp",
    },
    ("한영고", "고3"): {
        1: "26-1-중간 한영고3 동형 모의고사 1회 원고.hwpx",
        2: "26-1-중간 한영고3 동형 모의고사 2회 원고.hwpx",
    },
}


# 기본 메타정보 (시험날짜, 시험종류) — 학교별로 다를 수 있지만 일단 통일
DEFAULT_EXAM_DATE = "2026.5.7(목)"
DEFAULT_EXAM_TYPE = "1학기 중간고사"


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 run_test.py <학교> <학년> <회차[,회차...]>")
        print("예: python3 run_test.py 명일여고 고1 1")
        print("예: python3 run_test.py 명일여고 고1 1,2  (둘 다)")
        sys.exit(1)

    school = sys.argv[1]
    grade = sys.argv[2]
    rounds = [int(x) for x in sys.argv[3].split(",")]

    # 원고 파일 경로 수집
    files = []
    ms_map = MS_FILES.get((school, grade))
    if not ms_map:
        print(f"[오류] {school} {grade} 매핑 없음")
        sys.exit(1)
    for r in rounds:
        fname = ms_map.get(r)
        if not fname:
            print(f"[오류] {school} {grade} {r}회 원고 매핑 없음")
            sys.exit(1)
        path = os.path.join(MS_DIR, fname)
        if not os.path.exists(path):
            print(f"[오류] 파일 없음: {path}")
            sys.exit(1)
        files.append(path)
    print(f"[원고] {len(files)}개:")
    for f in files:
        print(f"  - {os.path.basename(f)}")

    # job_dir 생성
    job_dir = tempfile.mkdtemp(prefix="mockexam_test_")
    print(f"[작업] job_dir={job_dir}")

    # 메타정보 파일 생성
    for key, value in [
        ("school", school),
        ("grade", grade),
        ("exam_period", "26-1-중간"),
        ("exam_date", DEFAULT_EXAM_DATE),
        ("exam_type", DEFAULT_EXAM_TYPE),
    ]:
        with open(os.path.join(job_dir, f"{key}.txt"), "w", encoding="utf-8") as f:
            f.write(value)

    log_lines = []
    def log(msg):
        line = f"[run_test] {msg}"
        print(line)
        log_lines.append(line)

    engine = MockexamEngine()
    # 테스트 환경: InDesign 처리 시간이 길어 jsx_timeout 충분히 확보
    type(engine).jsx_timeout = property(lambda self: 1200)

    # 1) parse
    log("== Phase: parse ==")
    content_path = engine.parse({"manuscripts": files}, job_dir, log)
    log(f"content.json: {content_path}")

    # 2) prepare_jsx
    log("== Phase: prepare_jsx ==")
    settings_path = engine.prepare_jsx(content_path, job_dir, log)
    log(f".settings.json: {settings_path}")

    # 3) run_indesign
    log("== Phase: run_indesign ==")
    engine.run_indesign(job_dir, log)

    # 4) verify
    log("== Phase: verify ==")
    result = engine.verify(job_dir, log)
    log(f"verify: ok={result.get('ok')}, overflow={result.get('overflow')}, "
        f"warnings={result.get('warnings')}")
    log(f"PDF paths: {result.get('pdf_paths')}")

    # 작업 디렉터리 보존
    save_dir = os.path.join(ROOT, "조판_자동화", "engines", "mockexam", "analysis", "test_runs",
                            f"{school}_{grade}_{','.join(str(r) for r in rounds)}")
    os.makedirs(os.path.dirname(save_dir), exist_ok=True)
    if os.path.exists(save_dir):
        shutil.rmtree(save_dir)
    shutil.copytree(job_dir, save_dir)
    log(f"[저장] 작업 디렉터리 → {save_dir}")


if __name__ == "__main__":
    main()
