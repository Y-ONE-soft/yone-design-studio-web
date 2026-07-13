#!/usr/bin/env python3
"""품질 루프 8라운드 E2E (W18) — 미학습 GDrive 원고 2종의 전체 파이프라인 검증.

케이스 (inventory.jsonl 신규 선정 — 소화 완료 케이스 전체 대비 Jaccard 최원거리):
  c17_sero_2311   고1 23년 11월 모의고사 워크북 폴더 (모의고사 작업/고1/고1 23년
                  11월/워크북 — STEP 원고 + 스텝3/NN번.hwp 문항별 파일 +
                  오토큐엠 pool docx + 어휘 2단계 + (개정) 병존)
                  → workbook_sero_v2 (세로 — 품질 루프 최초 투입 경로)
                  ※ 선정 사유: 케이스(폴더) 단위 Jaccard 최원거리(0.507,
                    최근접 c05) + sero 경로가 W5 이후 품질 루프 미커버.
  c18_rp_step3pool  리딩파워(Reading power) 유형편 완성 기출문제(Step 3에
                  사용함).hwp (EBS 작업/Reading Power 유형편(완성)/4스텝 문제)
                  → ebs_workbook_v2 (업로드 파일 시나리오)
                  ※ 선정 사유: 단일 원고 기준 전 소화분 대비 Jaccard
                    최원거리 1위(0.885/0.821). [N강-EN]/[N강 N번] 전권 기출
                    pool + 파일명에 변형문제/N문제 토큰 없음(라우팅 신규).

사용: python3 scripts/e2e_round8.py <c17_sero_2311|c18_rp_step3pool>
        [--parse-only] [--from-content]

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round8/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본
원고는 data_corpus/round8/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/실
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

_R8 = os.path.join(REPO, "data_corpus", "round8")


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


def _make_sero(case_dir, out_dir):
    import engines.workbook_sero_v2.engine as eng_mod
    from engines.workbook_sero_v2.engine import WorkbookSeroV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["모의고사"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북세로_모의고사.indd")
        cfg["indd_original_gdrive_fallback"] = {}
        return cfg

    eng_mod._load_v1_config = _patched
    return WorkbookSeroV2Engine()


_CASES = {
    # 고1 23년 11월 모의고사 워크북 폴더 통째 업로드 → 세로 v2.
    "c17_sero_2311": {
        "engine": _make_sero,
        "meta": {"grade": "1", "year": "23", "month": "11"},
    },
    # 리딩파워 유형편 완성 기출 pool 단일 hwp → EBS v2.
    "c18_rp_step3pool": {
        "engine": _make_ebs,
        "meta": {"lesson": "유형완성기출"},
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R8, case)
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    if not from_content:
        shutil.rmtree(job, ignore_errors=True)
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    engine = spec["engine"](case_dir, out)
    meta = dict(spec["meta"])
    src = os.path.join(case_dir, "원고")
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
