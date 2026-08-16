#!/usr/bin/env python3
"""배N제 v2 '엔진' E2E — 엔진 클래스 전체 파이프라인 검증.

parse → prepare_jsx → run_indesign → verify 를 실제 원고로 실행한다.

사용: python3 scripts/e2e_engine_baenje_v2.py [원고폴더]
기본 원고폴더: GDrive 배재고2 26-2-중간 배N제

안전(출력 리다이렉트): 엔진의 _load_v1_config를 패치해
  - indd_output_dir → data_corpus/bj_engine_e2e/
  - indd_original   → data_corpus/template_test/배N제_원본.indd
    (없으면 실제 config 원본에서 safe_copy로 1회 확보)
실 운영 경로(조판/교재/프리미엄북/배N제)와 GDrive 원본은 건드리지 않는다.
"""
import json
import os
import shutil
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.exists(_ENV):
    for _line in open(_ENV):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

TEMPLATE_DIR = os.path.join(REPO, "data_corpus", "template_test")
OUT_DIR = os.path.join(REPO, "data_corpus", "bj_engine_e2e")
DEFAULT_SRC = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
    "콘텐츠 관리/내신대비/2026년/고2/배재고2/3. 26-2-중간/배N제")


def _ensure_local_template():
    local = os.path.join(TEMPLATE_DIR, "배N제_원본.indd")
    if os.path.isfile(local) and os.path.getsize(local) > 0:
        return local
    from core.base import safe_copy
    import engines.baenje_v2.engine as eng_mod
    cfg = eng_mod._load_v1_config()
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    print(f"  템플릿 로컬 확보: {cfg['indd_original']}")
    safe_copy(cfg["indd_original"], local)
    return local


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    import engines.baenje_v2.engine as eng_mod

    template = _ensure_local_template()
    os.makedirs(OUT_DIR, exist_ok=True)
    _orig_cfg = eng_mod._load_v1_config

    def _patched():
        cfg = dict(_orig_cfg())
        cfg["indd_output_dir"] = OUT_DIR
        cfg["indd_original"] = template
        return cfg
    eng_mod._load_v1_config = _patched

    job_dir = os.path.join(OUT_DIR, "job")
    if os.path.isdir(job_dir):
        shutil.rmtree(job_dir)
    os.makedirs(job_dir)
    for key, val in (("school", "배재2"), ("issue_num", "01"),
                     ("subject", "영어Ⅱ YBM(박)")):
        with open(os.path.join(job_dir, f"{key}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(val)

    # macOS 파일명은 NFD로 오므로 정규화 후 매칭 (GDrive 경로 필수)
    files = sorted(os.listdir(src_dir))
    def _nfc(x):
        return unicodedata.normalize("NFC", x)
    problems = [os.path.join(src_dir, f) for f in files
                if "문제" in _nfc(f) and f.lower().endswith((".docx", ".hwpx"))]
    answers = [os.path.join(src_dir, f) for f in files
               if "해설" in _nfc(f) and f.lower().endswith((".docx", ".hwpx"))]
    print(f"원고: 문제 {len(problems)} / 해설 {len(answers)}  ({src_dir})")
    if not problems:
        print("문제 원고 없음 — 중단")
        return 1

    engine = eng_mod.BaenjeV2Engine()
    log = print

    print("\n[1] parse")
    json_path = engine.parse({"manuscript": problems, "answers": answers},
                             job_dir, log)

    print("\n[2] prepare_jsx")
    engine.prepare_jsx(json_path, job_dir, log)

    print("\n[3] run_indesign")
    engine.run_indesign(job_dir, log)

    print("\n[4] verify")
    res = engine.verify(job_dir, log)
    print(json.dumps({k: v for k, v in res.items() if k != "warnings"},
                     ensure_ascii=False, indent=1))
    for w in res["warnings"]:
        print("  " + w)
    print("\n결과:", "통과" if res["ok"] else "실패")
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
