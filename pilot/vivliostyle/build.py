#!/usr/bin/env python3
"""W42 Vivliostyle 파일럿 — 원커맨드 빌드 (플랜 → HTML → PDF) + 생성 시간 측정.

사용:
    python3 pilot/vivliostyle/build.py tests/corpus/mockexam/029c4385 \
        --case pilot/vivliostyle/case_hanyoung3.json \
        --out data_corpus/pilot_vivlio/hanyoung3

절차:
  1. render_html.py 로직으로 HTML 생성 (라이브 파이프라인 소비)
  2. theme.css + 폰트 복사 (로컬 설치 폰트 → 빌드 디렉터리, 리포에 커밋 안 함)
  3. vivliostyle build 1차 (페이지 수 확정)
  4. 마지막 페이지 '끝.' 오버라이드 CSS 주입 후 2차 빌드 (최종본)
  - 시간은 각 단계별 실측 기록 (report_build.json)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

# 실물이 쓰는 서체의 로컬 설치 파일 (실측: pdffonts + fc-list)
FONT_FILES = [
    "~/Library/Fonts/HANDotum.ttf",
    "~/Library/Fonts/HANDotumB.ttf",
    "~/Library/Fonts/HANBatang.ttf",
    "~/Library/Fonts/HANBatangB.ttf",
    "~/Library/Fonts/H2GTRE.TTF",
    "~/Library/Fonts/NanumMyeongjo.otf",
    "~/Library/Fonts/NanumMyeongjoBold.otf",
]


def count_pdf_pages(path):
    try:
        import fitz
        with fitz.open(path) as doc:
            return len(doc)
    except Exception:
        return None


def run_vivliostyle(html_path, pdf_path, log):
    vs_bin = os.path.join(HERE, "node_modules", ".bin", "vivliostyle")
    cmd = [vs_bin, "build", os.path.basename(html_path),
           "-o", os.path.abspath(pdf_path)]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(html_path)),
                          capture_output=True, text=True,
                          env=dict(os.environ, PATH=os.environ["PATH"]))
    dt = time.time() - t0
    log(f"vivliostyle build: {dt:.1f}s (exit {proc.returncode})")
    if proc.returncode != 0:
        log(proc.stdout[-2000:])
        log(proc.stderr[-2000:])
        raise SystemExit("vivliostyle build 실패")
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True, help="출력 디렉터리")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    build_dir = os.path.join(out_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    report = {"case_dir": args.case_dir, "steps": {}}

    def log(msg):
        print(msg, flush=True)

    # 1. 플랜 → HTML
    t0 = time.time()
    import render_html
    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)
    plan = render_html.load_plan_from_corpus(os.path.join(REPO, args.case_dir)
                                             if not os.path.isabs(args.case_dir)
                                             else args.case_dir)
    html_text = render_html.build_html(plan, case)
    html_path = os.path.join(build_dir, "exam.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    report["steps"]["parse_and_html_s"] = round(time.time() - t0, 2)
    report["plan_paragraphs"] = len(plan)
    log(f"1) 플랜 {len(plan)}단락 → HTML ({report['steps']['parse_and_html_s']}s)")

    # 2. CSS + 폰트
    shutil.copy2(os.path.join(HERE, "theme.css"), build_dir)
    fonts_dir = os.path.join(build_dir, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    for f_ in FONT_FILES:
        src = os.path.expanduser(f_)
        if os.path.exists(src):
            shutil.copy2(src, fonts_dir)
        else:
            log(f"[경고] 폰트 없음: {f_}")

    # 마지막 페이지 오버라이드 자리 (1차는 빈 파일)
    override = os.path.join(build_dir, "lastpage.css")
    open(override, "w").close()
    with open(html_path, encoding="utf-8") as f:
        txt = f.read()
    txt = txt.replace('<link rel="stylesheet" href="theme.css">',
                      '<link rel="stylesheet" href="theme.css">\n'
                      '<link rel="stylesheet" href="lastpage.css">')
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(txt)

    # 3. 1차 빌드 (단일 실행 생성 시간 = 속도 판정 기준)
    pdf_path = os.path.join(out_dir, "exam_vivlio.pdf")
    dt1 = run_vivliostyle(html_path, pdf_path, log)
    report["steps"]["vivliostyle_pass1_s"] = round(dt1, 1)
    n_pages = count_pdf_pages(pdf_path)
    report["pages_pass1"] = n_pages
    log(f"3) 1차 빌드 {n_pages}p")

    # 4. 마지막 페이지 '끝.' 주입 후 2차 빌드
    if n_pages:
        with open(override, "w", encoding="utf-8") as f:
            f.write(f"@page :nth({n_pages}) {{\n"
                    f"  @bottom-center {{ content: element(pageFooterLast); }}\n"
                    f"}}\n")
        dt2 = run_vivliostyle(html_path, pdf_path, log)
        report["steps"]["vivliostyle_pass2_s"] = round(dt2, 1)
        report["pages_final"] = count_pdf_pages(pdf_path)

    report["total_s"] = round(sum(v for v in report["steps"].values()), 1)
    with open(os.path.join(out_dir, "report_build.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"완료: {pdf_path}")
    log(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
