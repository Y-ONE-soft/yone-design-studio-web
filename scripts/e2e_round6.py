#!/usr/bin/env python3
"""품질 루프 6라운드 E2E (W16) — 미학습 GDrive 원고 2종의 전체 파이프라인 검증.

케이스 (docs/원고_구조_인벤토리.md 다양성 후보):
  c07_rp_review   후보⑦ EBS Reading Power 유형편(완성) Unit 17 워크북/Step3.hwp
                  ([EBS리딩파워유형편완성 N강 N번] / [REVIEW N강-N번]형)
                  → ebs_workbook_v2 (업로드 파일 시나리오)
  c10_tb_cheonjae 후보⑩ 영어 천재(이) 8과 타학교 기출 서술형.hwpx
                  (15개정 구교과서, 대화문 요약 발문형 Step3 단독)
                  → textbook_workbook_v2 (manuscript_folder 시나리오)
                  ※ 후보⑨(명일여고1_파이널_Vol1_문장배열_정답지.docx)는 파이널
                    v1 관할(engines/final content의 vol1.문장배열 블록)이라
                    워크북 계열이 아님 — 인벤토리 미사용 후보 ⑩으로 대체.

사용: python3 scripts/e2e_round6.py <c07_rp_review|c10_tb_cheonjae>
        [--parse-only] [--from-content]

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round6/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본
원고는 data_corpus/round6/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/실
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

_R6 = os.path.join(REPO, "data_corpus", "round6")


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


def _make_ebs(case_dir, out_dir):
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


def _make_textbook(case_dir, out_dir):
    import engines.textbook_workbook_v2.engine as eng_mod
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = {"_default": os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")}
        return cfg

    eng_mod._load_v1_config = _patched
    return TextbookWorkbookV2Engine()


_CASES = {
    # 리딩파워 유형편(완성) Unit17 Step3: 업로드 파일 시나리오.
    "c07_rp_review": {
        "engine": _make_ebs, "folder_meta": False,
        "meta": {"lesson": "Unit17"},
    },
    # 교과서(15개정 천재(이)) 서술형 Step3 단독: manuscript_folder 시나리오.
    "c10_tb_cheonjae": {
        "engine": _make_textbook, "folder_meta": True,
        "meta": {"subject": "영어", "publisher": "영어 천재(이)",
                 "lesson": "8과"},
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R6, case)
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
        print("== 1/4 parse 생략 (--from-content: 기존 content.json 재사용)")
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
