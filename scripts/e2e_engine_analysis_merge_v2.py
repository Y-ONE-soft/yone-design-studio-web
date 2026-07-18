#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""분석본 결합 v2 엔진 E2E — parse → prepare_jsx → run_jsx → verify 전체.

사용:
  python3 scripts/e2e_engine_analysis_merge_v2.py            # 코퍼스 모드 (기본)
  python3 scripts/e2e_engine_analysis_merge_v2.py --real     # 실 GDrive 저장 모드

코퍼스 모드 (안전 — 기본):
  - GDrive 저장 base를 data_corpus/analysis_merge_v2/e2e/gdrive_out/ 으로
    리다이렉트. 실서비스/GDrive 경로 무접촉.
실 모드 (--real):
  - 실제 GDrive 분석본/고1,고2(공통)/ 아래 저장하되, 시험기간을
    "검증-테스트"(신규 폴더)로 강제 — 기존 폴더/파일 무접촉
    (신규 폴더/파일 생성만 한다는 스펙 검증용).

소스 강 폴더 탐색은 실제 GDrive '모의고사 작업'을 읽는다 (읽기 전용).
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

ENV = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.isfile(ENV):
    for _line in open(ENV):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def close_indesign_docs_under(prefix, log):
    """열린 InDesign 문서 중 백킹 파일이 prefix 아래인 것을 **저장 없이** 닫는다.

    W28 하네스 사고 재발 방지: 열린 문서의 백킹 파일을 rm 하면 InDesign이
    같은 경로의 낡은 문서를 재사용해 save 행/wedge에 빠진다 — **rm 전 반드시
    close**. 닫기가 확인되지 않으면(무응답 포함) RuntimeError로 중단해
    rm이 실행되지 않게 한다. InDesign 미실행이면 no-op (실행 유발 금지).
    사용자 문서는 prefix 밖이므로 접촉하지 않는다.
    """
    try:
        running = subprocess.run(
            ["pgrep", "-f", "Adobe InDesign"],
            capture_output=True).returncode == 0
    except OSError:
        running = False
    if not running:
        return 0
    prefix = os.path.join(os.path.abspath(prefix), "")
    js = (
        "var pfx=%s; var n=0;"
        " for (var i=app.documents.length-1;i>=0;i--){"
        "  var d=app.documents[i]; var fp=\"\";"
        "  try{fp=d.fullName.fsName;}catch(e){}"
        "  if (fp.indexOf(pfx)===0){d.close(SaveOptions.NO); n++;}}"
        " String(n);" % json.dumps(prefix, ensure_ascii=False))
    osa = ('tell application "Adobe InDesign 2026" to do script "%s" '
           "language javascript"
           % js.replace("\\", "\\\\").replace('"', '\\"'))
    try:
        proc = subprocess.run(["osascript", "-e", osa],
                              capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "InDesign 문서 닫기 무응답(180s) — do script wedge 가능성. "
            "백킹 파일 삭제 금지: 사람이 InDesign 상태 확인 후 재시도.")
    if proc.returncode != 0:
        raise RuntimeError(
            f"InDesign 문서 닫기 실패 — 백킹 파일 삭제 금지: "
            f"{(proc.stderr or '').strip()[:200]}")
    n = int(proc.stdout.strip() or "0")
    if n:
        log(f"[하네스] e2e 잔여 InDesign 문서 {n}개 저장 없이 닫음")
    return n


def main():
    real = "--real" in sys.argv
    out_root = os.path.join(REPO, "data_corpus", "analysis_merge_v2", "e2e")
    job = os.path.join(out_root, "job")
    log = lambda m: print(f"  {m}", flush=True)

    # ── 하네스 안전 가드: 클린 재실행 — 반드시 close 후 rm ────────────
    close_indesign_docs_under(out_root, log)
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    os.makedirs(job, exist_ok=True)

    import engines.analysis_merge_v2.engine as eng_mod
    from engines.analysis_merge_v2.engine import AnalysisMergeV2Engine

    if not real:
        gdrive_out = os.path.join(out_root, "gdrive_out")
        os.makedirs(gdrive_out, exist_ok=True)
        real_load = eng_mod._load_config

        def _patched():
            cfg = real_load()
            cfg["save_base"] = gdrive_out
            return cfg

        eng_mod._load_config = _patched

    engine = AnalysisMergeV2Engine()

    # ── 입력 (기존 결합 실물과 동일 계열: 고2 25년 6월 + 22년 3월) ──────────
    meta = {
        "grade": "고2",
        "school": "검증1",
        "exam_period": "검증-테스트",
        "issue_num": "1",
        "ganji_school": "2026 검증고2",
        "ranges": json.dumps(
            [{"title": "고2 25년 6월 모의고사", "detail": "33번"},
             {"title": "고2 22년 3월 모의고사", "detail": "33-34번"}],
            ensure_ascii=False),
        "result_name": "",
    }
    for k, v in meta.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)
    uploaded = {"codes": "25년 6월 33번, 22년 3월 33-34번"}

    try:
        print("== 1/4 parse")
        json_path = engine.parse(uploaded, job, log)

        print("== 2/4 prepare_jsx")
        jsx_path = engine.prepare_jsx(json_path, job, log)

        print("== 3/4 run_indesign (파이프라인과 동일 경로)")
        assert jsx_path == os.path.join(job, "run.jsx")
        engine.run_indesign(job, log)

        print("== 4/4 verify")
        result = engine.verify(job, log)
    finally:
        # 철칙(2026-07-18): 끝난 문서는 즉시 닫기 — JSX가 결과 확인용으로
        # 열어둔 산출물(save 완료)·크래시 잔여 소스 사본을 저장 없이 정리.
        try:
            close_indesign_docs_under(out_root, log)
        except RuntimeError as e:
            log(f"[하네스] 사후 문서 정리 실패(수동 확인 필요): {e}")
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=2))
    assert "pdf_path" not in result, "스펙1 위반: pdf_path 반환됨"
    if not result["ok"]:
        print("E2E FAIL — 게이트 미통과", file=sys.stderr)
        sys.exit(1)
    print(f"E2E OK — 저장: {result['gdrive_path']}")


if __name__ == "__main__":
    main()
