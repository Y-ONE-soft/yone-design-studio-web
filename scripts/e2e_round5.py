#!/usr/bin/env python3
"""품질 루프 5라운드 E2E (W15) — 미학습 GDrive 원고 2종의 전체 파이프라인 검증.

케이스 (docs/원고_구조_인벤토리.md 다양성 후보):
  c04_mock211  후보④ 모의고사_2학년_2025년_06월_변형문제_18_45_211문제_아잉카.hwp
               ([NHN_..._변형]형 문제모음, Step3 단독) → workbook_v2 (본가)
  c08_stg      후보⑧ 2026 수능특강 영어 03~14강 원고.hwpx (유형명 헤더 원고)
               → suneungteukgang_workbook_v2 (2단계 조판 — 분석본/문제본)
  c08_ref      수능특강 코퍼스 65cf0265(27강) 재조판 — 2단계 게이트 검증용
               (c08 원고는 스텝 원고가 아니라 실 콘텐츠 렌더는 이 케이스가 담당)

사용: python3 scripts/e2e_round5.py <c04_mock211|c08_stg|c08_ref>
        [--parse-only] [--from-content]

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round5/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본
원고는 data_corpus/round5/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/실
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

_R5 = os.path.join(REPO, "data_corpus", "round5")


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


def _make_workbook(case_dir, out_dir):
    import engines.workbook_v2.engine as eng_mod
    from engines.workbook_v2.engine import WorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = {"모의고사": os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")}
        return cfg

    eng_mod._load_v1_config = _patched
    return WorkbookV2Engine()


def _make_stg(case_dir, out_dir):
    import engines.suneungteukgang_workbook_v2.engine as eng_mod
    from engines.suneungteukgang_workbook_v2.engine import (
        SuneungteukgangWorkbookV2Engine)

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = {
            "analysis": os.path.join(REPO, "data_corpus", "template_test",
                                     "수능특강_분석_내지.indd"),
            "problem": os.path.join(REPO, "data_corpus", "template_test",
                                    "수능특강_문제_내지.indd"),
        }
        return cfg

    eng_mod._load_v1_config = _patched
    return SuneungteukgangWorkbookV2Engine()


_CASES = {
    # 본가 워크북: 업로드 파일 시나리오 (고2 25년 6월 모의고사 변형).
    "c04_mock211": {
        "engine": _make_workbook, "corpus_content": None,
        "meta": {"grade": "2", "year": "25", "month": "6"},
    },
    # 수능특강 v2: 원고 hwpx 단독 업로드 (단원 폴더 없음 시나리오).
    "c08_stg": {
        "engine": _make_stg, "corpus_content": None,
        "meta": {"lesson": "12강"},
    },
    # 수능특강 v2: 코퍼스 27강 재조판 (2단계 게이트 실증 — content.json 재사용).
    "c08_ref": {
        "engine": _make_stg,
        "corpus_content": os.path.join(
            REPO, "tests", "corpus", "suneungteukgang_workbook", "65cf0265"),
        "meta": {},
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R5, case)
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    if not from_content and not spec["corpus_content"]:
        shutil.rmtree(job, ignore_errors=True)
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    engine = spec["engine"](case_dir, out)
    json_path = os.path.join(job, "content.json")

    if spec["corpus_content"]:
        print(f"== 1/4 parse 생략 (코퍼스 content.json 재사용: {case})")
        for fn in os.listdir(os.path.join(spec["corpus_content"], "meta")):
            if fn.endswith(".txt"):
                shutil.copy2(
                    os.path.join(spec["corpus_content"], "meta", fn),
                    os.path.join(job, fn))
        shutil.copy2(os.path.join(spec["corpus_content"], "golden",
                                  "content.json"), json_path)
    else:
        for k, v in spec["meta"].items():
            with open(os.path.join(job, f"{k}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(v)
        if from_content and os.path.isfile(json_path):
            print("== 1/4 parse 생략 (--from-content)")
        else:
            print(f"== 1/4 parse ({case})")
            manuscripts = _collect_files(os.path.join(case_dir, "원고"))
            assert manuscripts, f"원고 없음: {case_dir}/원고"
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
