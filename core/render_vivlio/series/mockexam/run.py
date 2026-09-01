# -*- coding: utf-8 -*-
"""동형모의고사 — **원고만 주면 조판된다.**

    python3 -m core.render_vivlio.series.mockexam.run <원고파일 또는 폴더> [-o 출력폴더]
    python3 -m core.render_vivlio.series.mockexam.run --all      # 원고 폴더 통째로

학교키는 파일명에서 알아낸다. 원고 이름은 사람이 붙이는 것이라 표기가 흔들리므로
(`명일여고3_동형 2회`, `26-1-중간 상일2 동형 1회 원고`, `강동고2 동형 1회 원고 최종`)
학교 이름과 학년 숫자를 따로 잡아 맞춘다. 못 고르면 **묻지 말고 건너뛴다** — 엉뚱한
학교 프로파일로 조판하느니 안 하는 게 낫다.
"""
import os
import re
import sys
import unicodedata

from core.render_vivlio.series.mockexam import build, profile as P

NFC = lambda s: unicodedata.normalize("NFC", s or "")          # noqa: E731

SRC_DIR = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/동형모의고사/원고")
OUT_DIR = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/동형모의고사/_비블리오_시안")
# 원고 폴더 밖에 있는 것들(업로드 자리에 남은 원고)
EXTRA = {
    ("세종1", "1회"): "jobs/cu_5b499f/uploads/세종1_동형_1회_원고.hwpx",
    ("세종1", "2회"): "jobs/mock_6caa3ad1/uploads/세종1_동형_2회_원고.hwpx",
}

# 학교 이름 표기 흔들림 → 학교 short 이름
_ALIAS = {
    "강동고": "강동", "강동": "강동",
    "명일여고": "명일", "명일여자고": "명일", "명일": "명일",
    "배재고": "배재", "배재": "배재",
    "상일여고": "상일", "상일여자고": "상일", "상일": "상일",
    "성덕고": "성덕", "성덕": "성덕",
    "세종고": "세종", "세종": "세종",
    "한영고": "한영", "한영": "한영",
    "광문고": "광문", "광문": "광문",
}
_RE_SCHOOL = re.compile("(" + "|".join(sorted(_ALIAS, key=len, reverse=True))
                        + r")\s*(\d)")
_RE_ROUND = re.compile(r"(\d)\s*회")
_EXT = (".hwp", ".hwpx", ".docx")


def school_key(name):
    """원고 파일명 → 학교키. 못 정하면 None."""
    n = NFC(os.path.basename(name))
    n = re.sub(r"\d{2}-\d-(중간|기말)", " ", n)      # 회차 표기는 학년이 아니다
    for m in _RE_SCHOOL.finditer(n):
        key = _ALIAS[m.group(1)] + m.group(2)
        if key in P.available():
            return key
    return None


def round_no(name):
    m = _RE_ROUND.search(NFC(os.path.basename(name)))
    return f"{m.group(1)}회" if m else "1회"


def discover(target=None):
    """조판할 원고 목록 [(학교키, 회차, 경로)]."""
    paths = []
    if target and os.path.isfile(target):
        paths = [target]
    else:
        root = target or SRC_DIR
        for n in sorted(os.listdir(root)):
            if os.path.splitext(n)[1].lower() in _EXT and not n.startswith("~"):
                paths.append(os.path.join(root, n))
    out = []
    for p in paths:
        k = school_key(p)
        if k:
            out.append((k, round_no(p), p))
    if not target:
        here = os.path.abspath(__file__)
        for _ in range(5):          # mockexam → series → render_vivlio → core → 저장소
            here = os.path.dirname(here)
        for (k, rd), rel in EXTRA.items():
            full = os.path.join(here, rel)
            if os.path.exists(full) and not any(
                    a == k and b == rd for a, b, _c in out):
                out.append((k, rd, full))
    return sorted(out)


def render_all(target=None, out_dir=None, keys=None, log=print):
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    jobs = [j for j in discover(target) if not keys or j[0] in keys]
    if not jobs:
        log("조판할 원고가 없다.")
        return []
    done = []
    for key, rd, path in jobs:
        pdf = os.path.join(out_dir, f"{key}_{rd}.pdf")
        try:
            r = build.render_manuscript(path, key, pdf, log=lambda *a: None)
        except Exception as e:                                  # noqa: BLE001
            log(f"✘ {key} {rd} — {type(e).__name__}: {str(e)[:90]}")
            done.append({"key": key, "round": rd, "ok": False,
                         "error": f"{type(e).__name__}: {e}"})
            continue
        warn = [w for w in r["warnings"] if "정본" not in w and "근사" not in w]
        log(f"✔ {key:5s} {rd} {r['pages']:2d}쪽 {r['seconds']:4.1f}s"
            + (f"  ⚠ {warn[0][:60]}" if warn else ""))
        done.append({"key": key, "round": rd, "ok": True, "pdf": r["pdf"],
                     "pages": r["pages"], "warnings": r["warnings"]})
    return done


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="동형모의고사 조판 — 원고 파일/폴더를 주면 전부 조판한다")
    ap.add_argument("target", nargs="?", help="원고 파일 또는 폴더(생략하면 기본 원고 폴더)")
    ap.add_argument("-o", "--out", help="출력 폴더")
    ap.add_argument("-k", "--keys", nargs="*", help="학교키로 골라서")
    ap.add_argument("--list", action="store_true", help="찾은 원고만 보여 준다")
    a = ap.parse_args(argv)
    if a.list:
        for key, rd, path in discover(a.target):
            print(f"{key:5s} {rd}  {NFC(os.path.basename(path))}")
        return 0
    res = render_all(a.target, a.out, a.keys)
    bad = [r for r in res if not r["ok"]]
    print(f"\n조판 {len(res)}부 · 실패 {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
