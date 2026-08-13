# -*- coding: utf-8 -*-
"""빈칸어휘/빈칸어법 빈칸 개수 ↔ 원고 대조 (CLI).

로직은 engines/workbook_select/blankcheck.py 에 있다 — 엔진 verify 도 같은
코드를 쓴다(검수 기준이 갈리지 않게).

사용:
    python3 scripts/wbsel_check_blanks.py --gang 11              (열려 있는 문서)
    python3 scripts/wbsel_check_blanks.py --gang 11 --indd <경로>
"""
import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook_select import blankcheck  # noqa: E402
from engines.workbook_select import motherteng as _mt  # noqa: E402
from engines.workbook_select.engine import _load_config as _sel  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gang", required=True)
    ap.add_argument("--grade", default="고1")
    ap.add_argument("--indd", default="", help="비우면 열려 있는 문서")
    args = ap.parse_args()

    cfg = _sel()
    codes, numbers, col = _mt.codes_for_gang(cfg.get("motherteng_xlsx"),
                                             int(args.gang))
    if not codes:
        print("엑셀에서 %s강을 찾지 못했습니다" % args.gang)
        return 2
    num2code = {numbers[c]: c for c in codes if c in numbers}
    print("마더텅 %s강 — %d문항 (엑셀 '%s')" % (args.gang, len(codes), col))
    print("InDesign 덤프 중…")

    checked, fails = blankcheck.run(
        args.indd, num2code, cfg["manuscript_base"],
        args.grade.replace("고", "").strip() or "1", log=print)

    print("\n===== 판정 =====")
    print("  지문 %d개 대조" % checked)
    if fails:
        for f in fails:
            print("  실패: " + f)
        return 1
    print("  빈칸 개수 전부 원고와 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
