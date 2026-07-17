#!/usr/bin/env python3
"""수동 결합 2종 흡수 엔진 E2E — slim_merge / mockexam_horiz_merge (W25).

실 InDesign으로 parse → prepare_jsx → run_jsx → verify 전 과정을 돌린다.

안전:
  - 출력은 data_corpus/tools_onboard/ 로만 리다이렉트 (_load_config 패치)
  - GDrive 소스는 읽기(로컬 사본 복사)만 — 원본 무수정
  - JSX는 자기 사본만 창 없이 열고 닫음 — 사용자 열린 문서 무접촉

사용:
  python3 scripts/e2e_engine_tools_onboard.py horiz   # 가로판 결합
  python3 scripts/e2e_engine_tools_onboard.py slim    # 펼침면 압축 (ox)
  python3 scripts/e2e_engine_tools_onboard.py slim arrange
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

OUT_ROOT = os.path.join(REPO, "data_corpus", "tools_onboard")


def _run_engine(engine, job, uploaded, meta):
    log = lambda m: print(f"  {m}", flush=True)
    os.makedirs(job, exist_ok=True)
    for k, v in meta.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)

    print("== 1/4 parse")
    json_path = engine.parse(uploaded, job, log)

    print("== 2/4 prepare_jsx")
    jsx_path = engine.prepare_jsx(json_path, job, log)
    settings = json.load(open(os.path.join(job, ".settings.json"),
                              encoding="utf-8"))
    assert settings["output_dir"].startswith(OUT_ROOT), settings["output_dir"]

    print("== 3/4 run_indesign (실 InDesign — 블로킹 폴링, 파이프라인 동일 경로)")
    assert jsx_path == os.path.join(job, "run.jsx")
    engine.run_indesign(job, log)

    print("== 4/4 verify")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=2))
    return result


def run_horiz():
    """가로판 결합 — 과거 세로결합 job(bf7bac64) 입력 재사용: 260320, 240932."""
    import engines.mockexam_horiz_merge.engine as mod
    from engines.mockexam_horiz_merge.engine import MockexamHorizMergeEngine

    out = os.path.join(OUT_ROOT, "horiz")
    real = mod._load_config

    def patched():
        cfg = real()
        cfg["output_base"] = os.path.join(out, "out")
        return cfg
    mod._load_config = patched

    engine = MockexamHorizMergeEngine()
    job = os.path.join(out, "job")
    result = _run_engine(
        engine, job,
        uploaded={"codes": "260320, 240932", "result_name": "e2e_가로판결합_test"},
        meta={"grade": "고1", "school": "E2E테스트", "exam_period": "26-1-기말",
              "result_name": "e2e_가로판결합_test", "save_indd": "on"},
    )
    assert result["ok"], f"verify 실패: {result['warnings']}"
    print("HORIZ E2E OK:", result["pdf_path"])


def run_slim(mode="ox"):
    """펼침면 압축 — GDrive 고1_24년_9월_전체(C).indd 사본 입력."""
    import engines.slim_merge.engine as mod
    from engines.slim_merge.engine import SlimMergeEngine

    out = os.path.join(OUT_ROOT, f"slim_{mode}")
    real = mod._load_config

    def patched():
        cfg = real()
        cfg["output_base"] = os.path.join(out, "out")
        return cfg
    mod._load_config = patched

    src = os.path.expanduser(
        "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
        "콘텐츠 관리/내신대비/인디자인 파일/워크북/모의고사/고1/"
        "고1_24년_9월_전체(C).indd")
    assert os.path.exists(src), src

    engine = SlimMergeEngine()
    job = os.path.join(out, "job")
    result = _run_engine(
        engine, job,
        uploaded={"src_indd": src, "merge_mode": mode,
                  "result_name": f"e2e_펼침면압축_{mode}_test"},
        meta={},
    )
    assert result["ok"], f"verify 실패: {result['warnings']}"
    print("SLIM E2E OK:", result["indd_path"])


def run_convert(src_name="고2_23년_6월_전체(C).indd", grade_dir="고2"):
    """세로 변환 (W27) — GDrive 전체(C) 사본 입력, 수동 세로(C)와 파리티 대조는
    scripts/compare_convert_parity.py 별도 실행."""
    import engines.convert_to_vertical.engine as mod
    from engines.convert_to_vertical.engine import ConvertToVerticalEngine

    out = os.path.join(OUT_ROOT, "convert_vert")
    real = mod._load_config

    def patched():
        cfg = real()
        cfg["output_base"] = os.path.join(out, "out")
        return cfg
    mod._load_config = patched

    # GDrive 안전 사본 → data_corpus (엔진도 자체 사본을 뜨지만 이중 안전)
    local_src = os.path.join(out, "input", src_name)
    if not os.path.exists(local_src):
        gd = os.path.expanduser(
            "~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
            "콘텐츠 관리/내신대비/인디자인 파일/워크북/모의고사")
        src = os.path.join(gd, grade_dir, src_name)
        assert os.path.exists(src), src
        from engines.final.extractor import _gdrive_safe_copy
        os.makedirs(os.path.dirname(local_src), exist_ok=True)
        _gdrive_safe_copy(src, local_src,
                          log=lambda m: print(f"  {m}", flush=True))

    engine = ConvertToVerticalEngine()
    job = os.path.join(out, "job")
    result = _run_engine(
        engine, job,
        uploaded={"doc_path": local_src},
        meta={"result_name": "e2e_" + os.path.splitext(src_name)[0]
                             .replace("전체", "세로"),
              "export_pdf": "on"},
    )
    assert result["ok"], f"verify 실패: {result['warnings']}"
    print("CONVERT E2E OK:", result["indd_path"])


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "horiz"
    if which == "horiz":
        run_horiz()
    elif which == "convert":
        if len(sys.argv) > 2:
            run_convert(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "고2")
        else:
            run_convert()
    else:
        run_slim(sys.argv[2] if len(sys.argv) > 2 else "ox")
