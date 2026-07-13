#!/usr/bin/env python3
"""품질 루프 9라운드 E2E (W19) — 미학습 GDrive 원고 2종의 전체 파이프라인 검증.

케이스 (inventory.jsonl 신규 선정 — 소화 완료 케이스 전체 대비 Jaccard 거리
+ W19 우선 경로. 선정 상세는 docs/workbook_v2_로드맵.md W19):
  c19_supp_sejong  EBS 작업/Reading Power 유형편(기본)/Unit 22 Example, 1~3/
                   Unit 22 Example, 1~3 워크북 (20파일 — 정답 접미 '정답'(지 없음),
                   'Step2 A1 어법 객관식 문제', 'Step2 B1 어법OX'(무공백),
                   단일 Step3.hwpx)
                   → workbook_supp_v2 + school=세종1 (**학교 전용 내지 lookup
                   경로 첫 실기** — r1은 _default 폴백. 실운영 재현: v1 job
                   0807ebd8/a095f849 = 세종1_워크북리딩파워NN강).
                   ※ 선정 사유: supp 학교 템플릿 경로 미검증(W19 우선 경로).
                     미소화 RP기본 Unit 중 케이스 거리 최대(0.263, Unit 22 =
                     Example 1~3 구성 변형).
  c20_mock2503     모의고사 작업/고2/고2 25년 3월/고2 25년 3월 워크북 (49파일)
                   → workbook_v2 (본가 가로, 정규 모의고사 워크북 폴더)
                   ※ 선정 사유: mockexam 계열 U+F003B 잠복 확인 겸(W19 우선
                     경로) — 사전 스캔에서 스텝3 hwpx 25개 중 11개가 U+F003B
                     (요약 화살표 ⇩ 변형) 보유 실증. 거리 1위 후보(고1 26년
                     6월 워크북/Step3, 0.571)는 PUA 0건이라 목표 미충족 →
                     보유 실증 폴더(0.370) 우선, 사유 기록.

사용: python3 scripts/e2e_round9.py <c19_supp_sejong|c20_mock2503>
        [--parse-only] [--from-content]

안전(출력 리다이렉트): 엔진 v2 config 로더를 패치해
  - 출력 → data_corpus/round9/<case>/out/
  - 내지 → data_corpus/template_test/ 로컬 사본 (세종1 = 워크북세종_내지.indd)
원고는 data_corpus/round9/<case>/원고/ GDrive 사전 사본만 사용 — GDrive/실
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

_R9 = os.path.join(REPO, "data_corpus", "round9")


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


def _patch_cfg(out_dir, sejong=False):
    import engines.workbook_v2.engine as base_mod
    real_load = base_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out_dir
        cfg["indd_original"] = dict(cfg.get("indd_original", {}))
        cfg["indd_original"]["_default"] = os.path.join(
            REPO, "data_corpus", "template_test", "워크북C_모의고사.indd")
        cfg["indd_original"]["모의고사"] = cfg["indd_original"]["_default"]
        if sejong:
            cfg["indd_original"]["세종1"] = os.path.join(
                REPO, "data_corpus", "template_test", "워크북세종_내지.indd")
        return cfg

    base_mod._load_v1_config = _patched


def _make_supp(case_dir, out_dir):
    _patch_cfg(out_dir, sejong=True)
    from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine
    return WorkbookSuppV2Engine()


def _make_workbook(case_dir, out_dir):
    _patch_cfg(out_dir)
    from engines.workbook_v2.engine import WorkbookV2Engine
    return WorkbookV2Engine()


_CASES = {
    # RP 유형편(기본) Unit 22 워크북 (업로드 시나리오) → supp v2 + 세종1 내지.
    "c19_supp_sejong": {
        "engine": _make_supp,
        "meta": {"school": "세종1", "filename_stem": "리딩파워22강",
                 "grade": "1"},
        "expect_indd": "세종1_워크북리딩파워22강_내지_v2",
    },
    # 고2 25년 3월 모의고사 워크북 폴더 (manuscript_folder 시나리오) → 본가 v2.
    "c20_mock2503": {
        "engine": _make_workbook,
        "meta": {"grade": "2", "year": "25", "month": "3"},
        "expect_indd": "고2_25년_03월_전체(C)_v2",
    },
}


def main():
    case = sys.argv[1]
    parse_only = "--parse-only" in sys.argv
    from_content = "--from-content" in sys.argv
    spec = _CASES[case]
    case_dir = os.path.join(_R9, case)
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
