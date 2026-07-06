#!/usr/bin/env python3
"""품질 루프 3라운드 E2E (W13) — 미학습 GDrive 원고 3종의 전체 파이프라인 검증.

케이스 (docs/원고_구조_인벤토리.md 다양성 후보):
  c13_ybm  후보⑬ 공통영어1 YBM(김) Project 1 워크북 (PROJECT N-본문N 헤더)
           → textbook_workbook_v2
  c15_sl2  후보⑮ 공통영어1 능률(민) SL2 워크북 ([본문 N]+정답해설 혼합)
           → textbook_workbook_v2
  c05_mock 후보⑤ 고1 25년 10월 모의고사 워크북 (STEP2 정답 hwpx 포함 전체
           업로드) → workbook_v2 본가 (상하반전 실기 확인 겸용)

사용: python3 scripts/e2e_round3.py <c13_ybm|c15_sl2|c05_mock>
        [--parse-only] [--from-content]
  --from-content: 기존 job의 content.json 재사용 (parse 생략 — c05 파서가
                  느려 재조판 루프에서 필수)

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round3/<case>/out/
  - 내지 → data_corpus/template_test/워크북C_모의고사.indd 로컬 사본
원고는 data_corpus/round3/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/실
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

_R3 = os.path.join(REPO, "data_corpus", "round3")
_TEMPLATE = os.path.join(REPO, "data_corpus", "template_test",
                         "워크북C_모의고사.indd")


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


def _make_textbook(case_dir, out_dir):
    import engines.textbook_workbook_v2.engine as eng_mod
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = {"_default": _TEMPLATE}
        return cfg

    eng_mod._load_v1_config = _patched
    return TextbookWorkbookV2Engine()


def _make_workbook(case_dir, out_dir):
    import engines.workbook_v2.engine as eng_mod
    from engines.workbook_v2.engine import WorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["모의고사"] = _TEMPLATE
        return cfg

    eng_mod._load_v1_config = _patched
    return WorkbookV2Engine()


_CASES = {
    # 교과서 워크북: parse가 manuscript_folder 메타(로컬 사본)를 읽는다.
    "c13_ybm": {
        "engine": _make_textbook, "folder_meta": True,
        "meta": {"subject": "공통영어1", "publisher": "공통영어1 YBM(김)",
                 "lesson": "Project 1"},
    },
    "c15_sl2": {
        "engine": _make_textbook, "folder_meta": True,
        "meta": {"subject": "공통영어1", "publisher": "공통영어1 능률(민)",
                 "lesson": "SL2"},
    },
    # 모의고사 본가: 운영자가 폴더 전체를 업로드하는 시나리오 (정답 hwpx 포함).
    "c05_mock": {
        "engine": _make_workbook, "folder_meta": False,
        "meta": {"grade": "1", "year": "25", "month": "10"},
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R3, case)
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    if not from_content:
        shutil.rmtree(job, ignore_errors=True)
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    engine = spec["engine"](case_dir, out)
    meta = dict(spec["meta"])
    src = os.path.join(case_dir, "원고")
    if spec["folder_meta"]:
        meta["manuscript_folder"] = src
        uploaded = {"manuscripts": []}
    else:
        manuscripts = _collect_files(src)
        assert manuscripts, f"원고 없음: {src}"
        uploaded = {"manuscripts": manuscripts}
    for k, v in meta.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)

    json_path = os.path.join(job, "content.json")
    if from_content and os.path.isfile(json_path):
        print(f"== 1/4 parse 생략 (--from-content: 기존 content.json 재사용)")
    else:
        print(f"== 1/4 parse ({case})")
        json_path = engine.parse(uploaded, job, log)

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
