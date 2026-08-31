#!/usr/bin/env python3
"""파이널 `content.json` → Vivliostyle 책 폴더(Vol1·Vol2) 만들기.

파이널 엔진(`engines/final`)이 만든 content.json 하나면 두 권이 선다.
교재 폴더에는 **코드를 두지 않는다** — config.json + 원고뿐이다(3계층 규약).

    python3 scripts/final_viv_book.py <content.json|job_dir> [--art <완성본PDF폴더>]

만드는 것 (스튜디오 기준):
    조판/교재/파이널 직전보충/<학년>/<시험기간>/<학교>/
        원고/content.json      ← 두 권이 함께 본다
        참고/                  ← 간지·크레딧을 뜰 완성본 PDF(있으면)
        Vol1/config.json  Vol2/config.json

⚠ 산출 PDF 는 **각 Vol 폴더 안**에 놓는다. 학교 폴더에는 인디자인 납품본이
  같은 이름으로 있어서, 거기에 쓰면 납품본을 덮어쓴다.
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.render_vivlio import config as bookconfig  # noqa: E402

FONTS = [
    ("Noto", "NotoSansCJKkr-Regular.otf"), ("Noto", "NotoSansCJKkr-Medium.otf"),
    ("Noto", "NotoSansCJKkr-Bold.otf"), ("Neolli", "EliceDXNeolliOTF-Light.otf"),
    ("Neolli", "EliceDXNeolliOTF-Medium.otf"),
    ("Neolli", "EliceDXNeolliOTF-Bold.otf"), ("Jalnan", "JalnanOTF.otf"),
]
CHAPTER = {1: "Frame", 2: "Build Up"}
GRAY_MAP = {"#231f20": 1.0, "#6d6e71": 0.66, "#a7a9ac": 0.4,
            "#e2e3e4": 0.13, "#e6e7e8": 0.11, "#f2f2f3": 0.06, "#ffffff": 0.0}


def make_config(school, grade, period, vol, art_pdf, art_last):
    cfg = {
        "series": "final",
        "book": {"id": f"{school}_파이널_Vol{vol}",
                 "title": f"{school} 파이널 직전보충 Vol{vol}",
                 "brand": "FINAL STEP", "school": school, "grade": grade,
                 "period": period},
        "page": {"width": 210, "height": 297, "bleed": 3},
        "output": {"dir": ".", "stem": f"{school}_파이널"},
        "options": {"vol": vol},
        "manuscript": {"dir": "../원고", "files": {"content": "content.json"}},
        "fonts": [{"family": f, "file": n} for f, n in FONTS],
        "print": {"out": f"(Vol{vol})_내지_인쇄", "gray_map": dict(GRAY_MAP),
                  "_note": "전권 무채색 — 먹·회색을 DeviceGray 로 내려 K 단색으로 낸다"},
        "verify": {"suffix": f"(Vol{vol})_내지",
                   "frame": {"inner": 21, "outer": 25, "width": 170.7,
                             "top": 25, "bottom": 283},
                   "blank_ignore": "0123456789|FINALSTEPCHAPTER.",
                   "skip_pages": [1], "skip_last": 1,
                   "design": {"off": True}},
    }
    if art_pdf:
        cfg["finish"] = {
            "_note": "간지(1면)·크레딧(마지막 면)은 완성본 아트워크를 그대로 끼운다",
            "art_pdf": f"../참고/{os.path.basename(art_pdf)}",
            "inserts": [{"marker": "§ART1§", "page": 0, "mode": "replace"}],
            "append": [{"page": art_last}],
            "trim": {"bleed": 3},
        }
    else:
        cfg["finish"] = {"trim": {"bleed": 3}}
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="content.json 또는 그것이 든 job 폴더")
    ap.add_argument("--art", help="간지·크레딧을 뜰 완성본 PDF 폴더(선택)")
    ap.add_argument("--root", help="스튜디오 루트(기본: 자동 탐색)")
    a = ap.parse_args()

    src = a.src
    if os.path.isdir(src):
        src = os.path.join(src, "content.json")
    with open(src, encoding="utf-8") as f:
        c = json.load(f)
    school, grade = c["school"], c["grade"]
    period = c.get("exam_period") or "미상"

    root = a.root or bookconfig._studio_root()
    base = os.path.join(root, "조판", "교재", "파이널 직전보충",
                        grade, period, school)
    for d in ("원고", "참고", "Vol1", "Vol2"):
        os.makedirs(os.path.join(base, d), exist_ok=True)
    shutil.copy2(src, os.path.join(base, "원고", "content.json"))

    art = {}
    if a.art:
        import fitz
        for vol in (1, 2):
            for name in os.listdir(a.art):
                if f"(Vol{vol})" in name and name.endswith(".pdf"):
                    p = os.path.join(a.art, name)
                    shutil.copy2(p, os.path.join(base, "참고", name))
                    with fitz.open(p) as d:
                        art[vol] = (name, d.page_count - 1)
                    break
    for vol in (1, 2):
        name, last = art.get(vol, (None, 0))
        cfg = make_config(school, grade, period, vol, name, last)
        p = os.path.join(base, f"Vol{vol}", "config.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("  ", p.replace(root + os.sep, ""))
    print(f"■ {school} {grade} {period} — 책 두 권 준비 완료")
    print(f"   bin/viv \"{base.replace(root + os.sep, '')}/Vol1\" all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
