# -*- coding: utf-8 -*-
"""선택 워크북 조판 — Flask 없이 전 파이프라인 실행.

parse → prepare_jsx(+구조 불변식) → InDesign 조판 → 짝 정리 → trim →
PDF 재출력 → verify 까지 한 번에.

사용:
    python3 scripts/wbsel_build.py --gang 11 --school 한영1 \
        --exam-period 26-2-중간 --name "한영1_워크북01(마더텅11강)_내지"
    python3 scripts/wbsel_build.py --codes 231133,211132,... --name 테스트

⚠ 코드를 고친 뒤에는 반드시 parse 부터 다시 돌린다. 이전 job 의 content.json
   으로 JSX 만 재실행하면 수정이 반영되지 않은 결과가 나온다.
"""
import argparse
import json
import os
import sys
import time
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Flask 가 start_flask.sh 에서 읽는 .env 를 그대로 로드한다 —
# INDD_ORIGINAL_BASE(템플릿이 GDrive 미러에 있음) 가 없으면 prepare_jsx 가
# "워크북 원본 템플릿 없음" 으로 죽는다.
_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook_select.engine import WorkbookSelectEngine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gang", default="", help="마더텅 강 번호")
    ap.add_argument("--codes", default="", help="6자리 코드 직접 지정")
    ap.add_argument("--grade", default="고1")
    ap.add_argument("--school", default="학교미지정")
    ap.add_argument("--exam-period", default="기간미지정")
    ap.add_argument("--name", required=True, help="결과 파일명(확장자 제외)")
    ap.add_argument("--job", default="", help="job 폴더 이름 (기본: 자동)")
    args = ap.parse_args()
    if not args.gang and not args.codes:
        ap.error("--gang 또는 --codes 중 하나는 필요합니다")

    job_name = args.job or ("local_wbsel_" + args.name.replace(" ", "_")[:40])
    job = os.path.join(_ROOT, "jobs", job_name)
    os.makedirs(job, exist_ok=True)
    meta = {"grade": args.grade, "school": args.school,
            "exam_period": args.exam_period, "result_name": args.name}
    if args.gang:
        meta["mt_gang"] = args.gang
    if args.codes:
        meta["codes"] = args.codes
    for k, v in meta.items():
        with open(os.path.join(job, "%s.txt" % k), "w", encoding="utf-8") as f:
            f.write(v)

    t0 = time.time()

    def log(msg):
        print("[%6.1fs] %s" % (time.time() - t0, msg), flush=True)

    eng = WorkbookSelectEngine()
    try:
        log("=== 1/3 parse ===")
        json_path = eng.parse({"codes": args.codes, "mt_gang": args.gang},
                              job, log)
        log("=== 2/3 prepare_jsx (+구조 불변식) ===")
        eng.prepare_jsx(json_path, job, log)
        log("=== 2/3 InDesign 조판 → 짝 정리 → trim → PDF 재출력 ===")
        eng.run_indesign(job, log)
        log("=== 3/3 verify ===")
        try:
            res = eng.verify(job, log)
            log("verify: %s" % json.dumps(res, ensure_ascii=False)[:1500])
        except Exception:                                    # noqa: BLE001
            log("verify 예외:\n" + traceback.format_exc())

        st = os.path.join(job, ".settings.json")
        if os.path.exists(st):
            s = json.load(open(st, encoding="utf-8"))
            log("INDD: %s" % s.get("indd_path"))
            log("PDF : %s" % s.get("pdf_path"))
            print("\n다음: 산출물 교차검증(G3)")
            print("  python3 scripts/wbsel_verify_output.py '%s' --codes N "
                  "--indd-pages N" % s.get("pdf_path"))
        log("=== DONE ===")
        return 0
    except Exception:                                        # noqa: BLE001
        log("!!! 실패\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
