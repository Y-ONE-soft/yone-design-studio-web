# -*- coding: utf-8 -*-
"""선택 워크북 착수 전 커버리지 프리플라이트 (G0) — InDesign 무접촉.

조판을 시작하기 전에 **어느 칸이 비어 있는지 숫자로** 본다. 이 측정을
건너뛰면 "원고가 부실하다"는 인상만으로 노선을 고르게 되고, 그게 2026-08-08
한영1 표류의 원인이었다 (실제 결손은 221칸 중 8칸, 그중 4칸은 파서 버그였다).

사용:
    python3 scripts/wbsel_preflight.py --gang 11
    python3 scripts/wbsel_preflight.py --codes 231133,211132,...
    python3 scripts/wbsel_preflight.py --gang 11 --grade 고1 --keep

출력: 커버리지 격자 / 결손 목록 / 파일 선택 근거 / 노선 권고
종료코드: 0 = 원고 기반 전량 재조판 가능, 1 = 결손 과다(검토 필요)
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook_select.engine import WorkbookSelectEngine  # noqa: E402

# 결손률이 이 값을 넘으면 "원고 기반 전량 재조판" 권고를 보류한다.
_DEFECT_LIMIT = 0.10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gang", help="마더텅 강 번호 (코드 자동 조달)")
    ap.add_argument("--codes", help="6자리 코드 직접 지정 (콤마/줄바꿈)")
    ap.add_argument("--grade", default="고1")
    ap.add_argument("--keep", action="store_true",
                    help="작업 폴더를 지우지 않고 남긴다 (content.json 확인용)")
    ap.add_argument("--fill", default="",
                    help="보충 데이터 fill.json 경로 (원고에 아예 없는 칸용). "
                         "지정한 job 에만 적용된다 — config 기본값은 없다")
    args = ap.parse_args()
    if not args.gang and not args.codes:
        ap.error("--gang 또는 --codes 중 하나는 필요합니다")

    job = tempfile.mkdtemp(prefix="wbsel_preflight_")
    with open(os.path.join(job, "grade.txt"), "w", encoding="utf-8") as f:
        f.write(args.grade)
    if args.gang:
        with open(os.path.join(job, "mt_gang.txt"), "w", encoding="utf-8") as f:
            f.write(str(args.gang))
    if args.fill:
        src = os.path.expanduser(args.fill)
        if not os.path.exists(src):
            ap.error("--fill 파일 없음: %s" % src)
        shutil.copy2(src, os.path.join(job, "fill.json"))

    picks = []

    def log(msg):
        msg = str(msg)
        if msg.startswith("[선택]"):
            picks.append(msg)
            return
        print(msg, flush=True)

    eng = WorkbookSelectEngine()
    try:
        eng.parse({"codes": args.codes or "", "mt_gang": args.gang or ""},
                  job, log)
    except Exception as e:                                  # noqa: BLE001
        print("\n[중단] parse 실패: %s" % e)
        print("작업 폴더: %s" % job)
        return 2

    cov = json.load(open(os.path.join(job, "coverage.json"), encoding="utf-8"))
    codes = cov["codes"]
    grid = cov["coverage"]
    defects = cov.get("defects") or []

    print("\n===== 커버리지 격자 (%d문항) =====" % len(codes))
    print("step".ljust(15) + " ".join(c[-4:] for c in codes))
    total = hole = 0
    holes = {}
    for step in grid:
        row = ""
        miss = []
        for c in codes:
            ok = grid[step].get(c)
            row += " OK " if ok else " .. "
            total += 1
            if not ok:
                hole += 1
                miss.append(c)
        if miss:
            holes[step] = miss
        print("%-15s%s  %d/%d" % (step, row, len(codes) - len(miss),
                                  len(codes)))

    rate = (hole / total) if total else 0
    print("\n채워진 칸 %d/%d (%.1f%%) — 빈 칸 %d, 내용 미달 %d"
          % (total - hole, total, 100 * (1 - rate), hole, len(defects)))

    if holes:
        print("\n===== 빈 칸 =====")
        for step, miss in holes.items():
            print("  %-15s %s" % (step, ", ".join(miss)))
    if defects:
        print("\n===== 내용 미달 (코드는 있는데 내용이 모자람) =====")
        for d in defects:
            print("  %s %s — %s" % (d["step"], d["code"], d["reason"]))
        print("  ※ 파서가 정답지를 골랐을 수 있다. 아래 선택 근거를 확인할 것.")

    if picks:
        print("\n===== 원고 파일 선택 근거 (G1) =====")
        for p in sorted(set(picks)):
            print("  " + p[len("[선택] "):])

    print("\n===== 권고 =====")
    if rate <= _DEFECT_LIMIT:
        print("  원고 기반 전량 재조판으로 진행 가능 (결손 %.1f%%)." % (100 * rate))
        print("  빈 칸은 교재팀 통합 원고 또는 fill.json 으로 조달한다.")
        rc = 0
    else:
        print("  결손 %.1f%% — 원고 조달부터 확인할 것." % (100 * rate))
        print("  섹션이 통째로 비었으면 파서 오선택일 수 있다(위 선택 근거 확인).")
        rc = 1

    if args.keep:
        print("\n작업 폴더: %s" % job)
    else:
        shutil.rmtree(job, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
