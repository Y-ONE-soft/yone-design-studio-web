#!/usr/bin/env python3
"""W43 Vivliostyle 2차 파일럿 — 워크북 대표 구간 원커맨드 빌드 (플랜 → HTML → PDF).

사용:
    python3 pilot/vivliostyle/workbook/build_workbook.py \
        data_corpus/round18/supp_0a5da924/job/render_plan.json \
        --out data_corpus/pilot_vivlio/workbook_supp

절차: HTML 생성 → theme/assets/fonts 복사 → vivliostyle build 1회 → report_build.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PILOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PILOT))
sys.path.insert(0, HERE)

# 실물이 쓰는 서체의 로컬 설치 파일 (실측: PDF 폰트 인벤토리 + fc-list)
FONT_FILES = [
    "~/Library/Fonts/EliceDXNeolliOTF-Medium.otf",
    "~/Library/Fonts/EliceDXNeolliOTF-Bold.otf",
    "~/Library/Fonts/NotoSansCJKkr-Regular.otf",
    "~/Library/Fonts/NotoSansCJKkr-Medium.otf",
    "~/Library/Fonts/NotoSansCJKkr-Bold.otf",
    "~/Library/Fonts/GmarketSansMedium.otf",
    "~/Library/Fonts/GmarketSansBold.otf",
    "~/Library/Fonts/YeongdoOTF.otf",
    "~/Library/Fonts/12롯데마트드림Bold.ttf",
    "~/Library/Fonts/EliceDigitalBaeumOTF_Regular.otf",
    "~/Library/Fonts/Dinmed Regular_0.ttf",  # URWDIN-Medium 근사 (간지 뒷면 토큰)
]
# 실물 PDF 임베드 서브셋 (TTMamablock — 로컬 미설치, assets/ 에 자산화)
ASSET_FONTS = ["TTMamablockB.ttf", "TTMamablockL.ttf"]


def count_pdf_pages(path):
    try:
        import fitz
        with fitz.open(path) as doc:
            return len(doc)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", required=True, help="출력 디렉터리")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    build_dir = os.path.join(out_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    report = {"plan": args.plan, "steps": {}}

    # 1. 플랜 → HTML
    t0 = time.time()
    import render_workbook
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    html_text = render_workbook.build_html(plan)
    html_path = os.path.join(build_dir, "workbook.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    report["steps"]["plan_to_html_s"] = round(time.time() - t0, 2)
    print(f"1) 플랜 → HTML ({report['steps']['plan_to_html_s']}s)")

    # 2. CSS + 자산 + 폰트
    shutil.copy2(os.path.join(HERE, "workbook_theme.css"), build_dir)
    assets_src = os.path.join(PILOT, "assets")
    assets_dst = os.path.join(build_dir, "assets")
    os.makedirs(assets_dst, exist_ok=True)
    for f_ in os.listdir(assets_src):
        if not f_.startswith("."):
            shutil.copy2(os.path.join(assets_src, f_), assets_dst)
    fonts_dir = os.path.join(build_dir, "fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    for f_ in FONT_FILES:
        src = os.path.expanduser(f_)
        if os.path.exists(src):
            dst_name = os.path.basename(src)
            if dst_name == "12롯데마트드림Bold.ttf":
                dst_name = "12LotteMartDreamBold.ttf"  # CSS 참조명 (ASCII)
            shutil.copy2(src, os.path.join(fonts_dir, dst_name))
        else:
            print(f"[경고] 폰트 없음: {f_}")
    for f_ in ASSET_FONTS:
        src = os.path.join(assets_src, f_)
        if os.path.exists(src):
            shutil.copy2(src, fonts_dir)

    # 3. 빌드
    vs_bin = os.path.join(PILOT, "node_modules", ".bin", "vivliostyle")
    pdf_path = os.path.join(out_dir, "workbook_vivlio.pdf")
    t0 = time.time()
    proc = subprocess.run([vs_bin, "build", "workbook.html", "-o", pdf_path],
                          cwd=build_dir, capture_output=True, text=True)
    dt = time.time() - t0
    report["steps"]["vivliostyle_s"] = round(dt, 1)
    print(f"2) vivliostyle build: {dt:.1f}s (exit {proc.returncode})")
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        raise SystemExit("vivliostyle build 실패")
    report["pages"] = count_pdf_pages(pdf_path)
    report["total_s"] = round(sum(report["steps"].values()), 1)
    with open(os.path.join(out_dir, "report_build.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"완료: {pdf_path} ({report['pages']}p)")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
