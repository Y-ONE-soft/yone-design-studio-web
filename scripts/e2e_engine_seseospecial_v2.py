#!/usr/bin/env python3
"""세서특필 v2 '엔진' E2E — 엔진 클래스 전체 파이프라인 검증.

parse → prepare_jsx → run_indesign → verify 를 코퍼스 케이스로 실행한다.

사용: python3 scripts/e2e_engine_seseospecial_v2.py [71f664f1] [--template 광문2]

안전(출력 리다이렉트): 엔진의 _load_v1_config를 패치해
  - indd_output_dir → data_corpus/ss_engine_e2e/<case>/
  - templates       → data_corpus/template_test/세서특필_{키}.indd
    (없으면 실제 config 원본에서 safe_copy로 1회 확보)
실 운영 경로(조판/교재/특강교재/세서특필)와 GDrive 원본은 건드리지 않는다.

--template 광문2: 학교 키와 무관하게 지정 템플릿 사용 — 광문1 원고를
광문2 계열 문서에 조판하던 실운영 워크플로(2026-06-10 job 41198133)를 재현.
([원본]광문1 템플릿은 구세대 스타일 트리라 v1/v2 모두 스타일 적용 불가)
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

TEMPLATE_DIR = os.path.join(REPO, "data_corpus", "template_test")


def _ensure_local_template(key):
    local = os.path.join(TEMPLATE_DIR, f"세서특필_{key}.indd")
    if os.path.isfile(local) and os.path.getsize(local) > 0:
        return local
    from core.base import safe_copy
    import engines.seseospecial_v2.engine as eng_mod
    cfg = eng_mod._load_v1_config.__wrapped__() \
        if hasattr(eng_mod._load_v1_config, "__wrapped__") \
        else eng_mod._load_v1_config()
    src = cfg["templates"][key]
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    print(f"  템플릿 로컬 확보: {src}")
    safe_copy(src, local)
    return local


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    case = args[0] if args else "71f664f1"
    force_key = None
    if "--template" in sys.argv:
        force_key = sys.argv[sys.argv.index("--template") + 1]

    case_dir = os.path.join(REPO, "tests", "corpus", "seseospecial", case)
    out = os.path.abspath(os.path.join(REPO, "data_corpus",
                                       "ss_engine_e2e", case))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import _replay
    import engines.seseospecial_v2.engine as eng_mod
    from engines.seseospecial_v2.engine import SeseoSpecialV2Engine

    # 케이스 학교 키 → 필요한 로컬 템플릿 확보
    school = open(os.path.join(case_dir, "meta", "school.txt"),
                  encoding="utf-8").read().strip()
    key = force_key or eng_mod._school_key(school)
    local_template = _ensure_local_template(key)
    print(f"== 케이스 {case} (학교 {school}, 템플릿 {key})")

    # ── 출력 리다이렉트: v1 config 로더 패치 ────────────────────────────────
    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["templates"] = {k: local_template
                            for k in cfg.get("templates", {})}
        return cfg

    eng_mod._load_v1_config = _patched
    engine = SeseoSpecialV2Engine()

    print("== 1/4 parse")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded, "업로드 재구성 실패"
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    engine.prepare_jsx(json_path, job, log)

    print("== 3/4 run_indesign")
    engine.run_indesign(job, log)

    print("== 4/4 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print("\n결과:", "✅ verify ok=True" if result["ok"]
          else "❌ verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
