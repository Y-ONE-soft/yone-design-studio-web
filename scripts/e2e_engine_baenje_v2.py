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
# 결과물은 리포(dev) 밖 — 교재 폴더로 내보낸다. 환경변수로 지정하지 않으면
# 종전대로 data_corpus 아래(E2E 검증용)를 쓴다.
OUT_DIR = os.environ.get("BJ_OUT_DIR") or os.path.join(
    REPO, "data_corpus", "bj_engine_e2e")
DEFAULT_SRC = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
    "콘텐츠 관리/내신대비/2026년/고2/배재고2/3. 26-2-중간/배N제")


def _ensure_local_template():
    env = os.environ.get("BJ_TEMPLATE")
    if env and os.path.isfile(os.path.expanduser(env)):
        return os.path.expanduser(env)
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


def _split_manuscripts(paths):
    """문제/해설 원고 분류 — GDrive 파일명은 NFD라 정규화 후 매칭."""
    def _nfc(x):
        return unicodedata.normalize("NFC", x)
    problems = [p for p in paths if "문제" in _nfc(os.path.basename(p))]
    # 해설 원고 파일명은 '해설' 또는 '정답'으로 온다
    answers = [p for p in paths if ("해설" in _nfc(os.path.basename(p))
                                    or "정답" in _nfc(os.path.basename(p)))]
    return problems, answers


def main():
    args = sys.argv[1:]
    # 인자가 원고 파일들이면 그 파일만 조판한다(한 폴더에 여러 호가 섞여 있을 때)
    explicit = [a for a in args if os.path.isfile(a)]
    src_dir = next((a for a in args if os.path.isdir(a)), DEFAULT_SRC)
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
    for key, val in (("school", os.environ.get("BJ_SCHOOL", "배재2")),
                     ("issue_num", os.environ.get("BJ_ISSUE", "01")),
                     ("subject", os.environ.get("BJ_SUBJECT", "영어Ⅱ YBM(박)"))):
        with open(os.path.join(job_dir, f"{key}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(val)

    # 유닛(머리말) 라벨을 직접 줄 때 — 파일명에 'N과'가 없는 원고(모의고사 변형 등)
    labels = os.environ.get("BJ_LABELS")
    if labels:
        with open(os.path.join(job_dir, "unit_labels.json"), "w",
                  encoding="utf-8") as f:
            f.write(labels)
        print(f"유닛 라벨 지정: {labels}")

    if explicit:
        problems, answers = _split_manuscripts(explicit)
        src_dir = os.path.dirname(explicit[0])
    else:
        files = sorted(os.listdir(src_dir))
        cand = [os.path.join(src_dir, f) for f in files
                if f.lower().endswith((".docx", ".hwpx"))]
        problems, answers = _split_manuscripts(cand)
    problems, answers = sorted(problems), sorted(answers)
    print(f"원고: 문제 {len(problems)} / 해설 {len(answers)}  ({src_dir})")
    for f in problems + answers:
        print("   " + os.path.basename(f))
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
