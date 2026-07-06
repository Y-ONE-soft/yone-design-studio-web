#!/usr/bin/env python3
"""품질 루프 2라운드 E2E — 미학습 GDrive 원고 3종의 전체 파이프라인 검증.

케이스 (docs/원고_구조_인벤토리.md 다양성 후보):
  c12_wb2  후보⑫ 명일여고1 외부지문2 워크북 (pN-Practice/수능 Analysis 헤더)
           → workbook_supp_v2
  c14_wb3  후보⑭ 명일여고1 외부지문3 워크북 (올림포스 스텝3 [올독기N N-A])
           → workbook_supp_v2
  c02_rp   후보② 리딩파워 유형(기본) 변형문제 문제모음 hwp
           → ebs_workbook_v2

사용: python3 scripts/e2e_round2.py <c12_wb2|c14_wb3|c02_rp> [--parse-only]

안전(출력 리다이렉트): 엔진 config 로더를 패치해
  - 출력 → data_corpus/round2/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본 (supp: 워크북C_모의고사,
    ebs: EBS리딩파워_내지)
원고는 data_corpus/round2/<case>/ 아래 GDrive 사전 사본만 사용 — GDrive/실
운영 경로 무접촉.
"""
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_R2 = os.path.join(REPO, "data_corpus", "round2")


def _collect_files(src_dir):
    out = []
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in sorted(files):
            if f.startswith("."):
                continue
            if os.path.splitext(f)[1].lower() in (".docx", ".hwp", ".hwpx"):
                out.append(os.path.abspath(os.path.join(root, f)))
    return out


def _make_supp(case, out_dir):
    import engines.workbook_v2.engine as base_mod
    from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine

    real_load = base_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["_default"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        return cfg

    base_mod._load_v1_config = _patched
    return WorkbookSuppV2Engine()


def _make_ebs(case, out_dir):
    import engines.ebs_workbook_v2.engine as eng_mod
    from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = os.path.join(
            REPO, "data_corpus", "template_test", "EBS리딩파워_내지.indd")
        return cfg

    eng_mod._load_v1_config = _patched
    return EbsWorkbookV2Engine()


_CASES = {
    "c12_wb2": {"engine": _make_supp, "src": "원고",
                "meta": {"grade": "1", "filename_stem": "외부지문2"}},
    "c14_wb3": {"engine": _make_supp, "src": "원고",
                "meta": {"grade": "1", "filename_stem": "외부지문3"}},
    "c02_rp": {"engine": _make_ebs, "src": ".",
               "meta": {"lesson": "Unit15기본"}},
}
# c02 디렉터리 실명 (원고 하위 폴더 없이 hwp 단일 파일)
_CASE_DIRS = {"c02_rp": "c02_rp_basic"}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R2, _CASE_DIRS.get(case, case))
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    shutil.rmtree(job, ignore_errors=True)
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    engine = spec["engine"](case, out)
    for k, v in spec["meta"].items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)

    src = os.path.join(case_dir, spec["src"])
    manuscripts = _collect_files(src)
    assert manuscripts, f"원고 없음: {src}"

    print(f"== 1/4 parse ({case}: {len(manuscripts)}개 파일)")
    json_path = engine.parse({"manuscripts": manuscripts}, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)
    if parse_only:
        print("(--parse-only) 종료")
        return 0

    print("== 3/4 run_indesign")
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
