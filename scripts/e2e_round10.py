#!/usr/bin/env python3
"""품질 루프 10라운드 E2E (W20) — 미해소 잠복 2건 우선 타격 원고 2종.

케이스 (inventory.jsonl 시그니처 스캔 선정 — 미해소 잠복 우선 타격이
거리 기준을 오버라이드. 선정 상세는 docs/workbook_v2_로드맵.md W20):
  c21_rp11        EBS 작업/Reading Power 유형편(완성)/4스텝 문제/
                  리딩파워 유형완성 기출문제-11강(133문제).hwp
                  → ebs_workbook_v2 (업로드 파일 시나리오)
                  ※ 선정 사유: 잠복 ①(W14 (1) c06 인라인 PUA 매핑) 지정
                    타격 — 전수 스캔(pyhwp 경로, 1037+741파일)에서 인라인
                    겹따옴표 U+F0852/F0853 보유 실증("the ␦land of
                    opportunity␦ nevertheless" ×2쌍). Jaccard 최근접
                    c06(0.609) — 같은 pool 계열이나 잠복 보유 실증 파일이
                    이 계열뿐(11강/13강/16강). 13강(U+F081~F085 문장
                    마커)은 매핑 근거 부족으로 미투입 기록.
  c22_mock2503g1  모의고사 작업/고1/고1 25년 3월/고1 25년 3월 워크북
                  (45파일 — Step1/2 docx + 스텝3/NN번.hwp 25개 + 박소원
                  통합원고 + 어법선택(문법 기본 문제) 변형)
                  → workbook_v2 (본가 가로, manuscript_folder 시나리오)
                  ※ 선정 사유: 잠복 ②(W14 (2) mockexam U+F003B) 지정
                    타격 — 전수 스캔에서 스텝3 U+F003B 단독 단락 14건
                    보유(미소화 폴더 중 최다·유일 순수 F003B). Jaccard
                    최근접 c20(0.068 — 정규 모의고사 워크북 폴더 동형):
                    거리 기준으론 부적격이나 시그니처 타격 지정 우선.

사용: python3 scripts/e2e_round10.py <c21_rp11|c22_mock2503g1>
        [--parse-only] [--from-content]

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round10/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본
원고는 data_corpus/round10/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/
실운영 경로 무접촉.
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

_R10 = os.path.join(REPO, "data_corpus", "round10")


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


def _make_workbook(case_dir, out_dir):
    import engines.workbook_v2.engine as base_mod
    from engines.workbook_v2.engine import WorkbookV2Engine

    real_load = base_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["_default"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        cfg["indd_original"]["모의고사"] = cfg["indd_original"]["_default"]
        return cfg

    base_mod._load_v1_config = _patched
    return WorkbookV2Engine()


_CASES = {
    # RP 유형완성 기출 11강 pool 단일 hwp → EBS v2 (인라인 PUA 잠복 ①).
    "c21_rp11": {
        "engine": _make_ebs,
        "meta": {"lesson": "11강기출"},
        "expect_indd": "EBS_리딩파워_11강기출_전체(C)_v2",
    },
    # 고1 25년 3월 모의고사 워크북 폴더 → 본가 v2 (U+F003B 잠복 ②).
    "c22_mock2503g1": {
        "engine": _make_workbook,
        "meta": {"grade": "1", "year": "25", "month": "3"},
        "expect_indd": "고1_25년_03월_전체(C)_v2",
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R10, case)
    out = os.path.join(case_dir, "out")
    job = os.path.join(out, "job")
    if not from_content:
        shutil.rmtree(job, ignore_errors=True)
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    engine = spec["engine"](case_dir, out)
    src = os.path.join(case_dir, "원고")
    manuscripts = _collect_files(src)
    assert manuscripts, f"원고 없음: {src}"
    uploaded = {"manuscripts": manuscripts}
    for k, v in spec["meta"].items():
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
    settings = json.load(open(os.path.join(job, ".settings.json"),
                              encoding="utf-8"))
    assert spec["expect_indd"] in settings["indd_path"], settings["indd_path"]
    print("  indd:", os.path.basename(settings["indd_path"]))
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
