#!/usr/bin/env python3
"""답란 전용 단락스타일 `S_답란` 일괄 생성 (W45).

배경 (역학습 W44):
    답란("(A): _____", "주제문: ____")을 현행 판정기는 **선지 스타일**로
    처리하는데, 완성 조판본 다수(61건/13문서)는 **지문 스타일**이었다.
    사용자 확인 결과 그건 의도가 아니라 회피다 — "선지 스타일엔 들여쓰기가
    있어 답란이 이상하게 정렬돼서 손으로 지문 스타일로 바꾼 것".
    확정 해법: 지문 스타일을 복제하고 들여쓰기만 0으로 내린 **답란 전용
    스타일 `S_답란`**을 조판 템플릿에 신설하고, 매핑을 그쪽으로 돌린다.

이 스크립트가 하는 일:
    engines/*/config.json의 .indd 원본(= 조판 템플릿)에 `S_답란`을 만든다.
    - 원본 스타일(보통 그 템플릿의 지문 스타일)을 InDesign duplicate()로
      복제 → firstLineIndent/leftIndent만 0 → 그 외 속성 전부 승계
    - 이미 있으면 스킵(멱등), 원본 스타일을 못 찾으면 생성 없이 [오류] 보고

안전 (기본값이 안전 — 원본은 손대지 않는다):
    --mode copy   (기본) 템플릿을 작업 사본으로 복사한 뒤 사본에만 적용.
                  사본 위치: data_corpus/template_ansline/<대상>.indd
                  (이미 로컬 실증 사본이 있으면 --use-existing-copy로 재사용)
    --mode dry    문서를 열어 원본/대상 스타일 존재 여부만 보고 (저장 없음)
    --mode apply  **원본 템플릿 직접 수정**. 사용자 승인 없이는 금지 —
                  `--i-have-user-approval` 를 같이 주지 않으면 거부한다.
                  적용 전 원본을 <파일>.bak-YYYYmmddHHMM.indd 로 백업한다.

사용:
    # 워크북 계열만 사본 실증 (이번 W45 범위)
    python3 scripts/add_ansline_style.py --targets workbook,textbook_workbook
    # 전 템플릿 목록/현황만 확인
    python3 scripts/add_ansline_style.py --mode dry --targets all
    # (사용자 승인 후) 원본 일괄 적용
    python3 scripts/add_ansline_style.py --mode apply --targets all \
        --i-have-user-approval

InDesign 철칙: 사용자가 열어둔 문서는 건드리지 않는다 (사전/사후 문서
목록을 대조해 보고). 프로세스는 절대 kill 하지 않는다 (runner 규약).
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# 답란 스타일의 이름(그룹 안 마지막 토큰). 그룹은 원본 스타일과 같은 곳.
ANSLINE_NAME = "S_답란"

# ── 대상 템플릿 표 ──────────────────────────────────────────────────────────
# engine: engines/<engine>/config.json
# key   : config 안의 경로 (슬래시 구분 — 예 "indd_original/_default")
# src   : 복제할 원본 단락스타일 전체 경로 (그 템플릿의 지문 스타일)
# dst   : 만들 스타일 전체 경로 (그룹 + S_답란)
#
# src/dst는 style_map.json의 실물 인벤토리와 일치해야 한다. 워크북 계열은
# STEP3 지문 스타일("STEP 03 > 실전 문제 지문 올림포스_")이 기준.
_WB_SRC = "STEP 03 > 실전 문제 지문 올림포스_"
_WB_DST = "STEP 03 > " + ANSLINE_NAME

TARGETS = [
    # ── 워크북 계열 (style_map "workbook" 공유 — W45 1차 범위) ─────────
    {"name": "workbook", "engine": "workbook",
     "key": "indd_original/_default", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "workbook_세종", "engine": "workbook",
     "key": "indd_original/세종1", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "textbook_workbook", "engine": "textbook_workbook",
     "key": "indd_original/_default", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "textbook_workbook_세종", "engine": "textbook_workbook",
     "key": "indd_original/세종", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "ebs_workbook", "engine": "ebs_workbook",
     "key": "indd_original", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "workbook_sero", "engine": "workbook_sero",
     "key": "indd_original/모의고사", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "suneungteukgang_analysis", "engine": "suneungteukgang_workbook",
     "key": "indd_original/analysis", "src": _WB_SRC, "dst": _WB_DST},
    {"name": "suneungteukgang_problem", "engine": "suneungteukgang_workbook",
     "key": "indd_original/problem", "src": _WB_SRC, "dst": _WB_DST},
    # ── 그 밖의 계열 (2차 — 지문 스타일 경로 확인 후 활성화) ────────────
    # 아래는 style_map에 AnsL 매핑이 아직 없어 이번 전환 대상이 아니다.
    # 활성화하려면 src를 그 템플릿의 실물 지문 스타일로 채우고 주석 해제.
    # {"name": "blackbook", "engine": "blackbook", "key": "indd_original",
    #  "src": "...", "dst": "..."},
    # {"name": "whitebook", "engine": "whitebook", "key": "indd_original",
    #  "src": "...", "dst": "..."},
    # {"name": "seseospecial_광문1", "engine": "seseospecial",
    #  "key": "templates/광문1", "src": "...", "dst": "..."},
]

# 이미 있는 로컬 실증 사본 (data_corpus/template_test/) — --use-existing-copy
EXISTING_COPIES = {
    "workbook": "워크북C_모의고사.indd",
    "workbook_세종": "워크북세종_내지.indd",
    "textbook_workbook": "워크북C_모의고사.indd",
    "textbook_workbook_세종": "워크북세종_내지.indd",
    "ebs_workbook": "EBS리딩파워_내지.indd",
    "workbook_sero": "워크북세로_모의고사.indd",
    "suneungteukgang_analysis": "수능특강_분석_내지.indd",
    "suneungteukgang_problem": "수능특강_문제_내지.indd",
}

COPY_DIR = os.path.join(REPO, "data_corpus", "template_ansline")


def _load_env():
    env = os.path.expanduser("~/dev/yone-design-web/.env")
    if os.path.exists(env):
        for line in open(env):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _dig(cfg, key):
    node = cfg
    for part in key.split("/"):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def resolve_target(t):
    """대상 → 원본 .indd 절대경로 (없으면 None)."""
    from core.paths import resolve
    cpath = os.path.join(REPO, "engines", t["engine"], "config.json")
    if not os.path.isfile(cpath):
        return None
    cfg = json.load(open(cpath, encoding="utf-8"))
    raw = _dig(cfg, t["key"])
    if not raw:
        return None
    return resolve(raw)


def indesign_docs():
    """현재 InDesign에 열린 문서 이름 (사용자 작업 문서 무접촉 확인용)."""
    try:
        return subprocess.check_output(
            ["osascript", "-e",
             'tell application "Adobe InDesign 2026" to get name of documents'],
            text=True, timeout=20).strip()
    except Exception:                                        # noqa: BLE001
        return "(조회 실패)"


def run_on(indd_path, src_style, dst_style, do_save, log):
    """한 .indd에 S_답란 생성 (또는 dry 검사). 리포트 dict 반환."""
    from core.indesign.jsxbuild import build_jsx
    from core.indesign.runner import run_jsx
    out_json = os.path.join(
        COPY_DIR, "_report_%d.json" % abs(hash(indd_path)))
    jsx_log = out_json + ".log"
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    for p in (out_json, jsx_log):
        try:
            os.remove(p)
        except OSError:
            pass
    body = os.path.join(REPO, "core", "jsx", "add_paragraph_style.body.jsx")
    jsx = build_jsx(body, {
        "__INDD_PATH__": indd_path,
        "__OUT_PATH__": out_json,
        "__SRC_STYLE__": src_style,
        "__DST_STYLE__": dst_style,
        "__DO_SAVE__": "1" if do_save else "0",
    }, log_path=jsx_log)
    try:
        run_jsx(jsx, log, poll_log_path=jsx_log, timeout=900,
                completion_marker="답란 스타일 작업 완료")
    finally:
        try:
            os.remove(jsx)
        except OSError:
            pass
    if not os.path.isfile(out_json):
        return {"error": "리포트 미생성 (JSX 로그: %s)" % jsx_log}
    return json.load(open(out_json, encoding="utf-8"))


def prepare_copy(t, orig, use_existing, log):
    """작업 사본 경로 반환 (원본 무수정)."""
    from core.base import safe_copy_indd
    os.makedirs(COPY_DIR, exist_ok=True)
    if use_existing and t["name"] in EXISTING_COPIES:
        cand = os.path.join(REPO, "data_corpus", "template_test",
                            EXISTING_COPIES[t["name"]])
        if os.path.isfile(cand):
            dst = os.path.join(COPY_DIR, os.path.basename(cand))
            if not os.path.isfile(dst):
                safe_copy_indd(cand, dst)
                log(f"  기존 로컬 사본 재사용 복사: {cand} → {dst}")
            return dst
    dst = os.path.join(COPY_DIR, t["name"] + ".indd")
    if os.path.isfile(dst):
        log(f"  사본 이미 존재 (재사용): {dst}")
        return dst
    real = safe_copy_indd(orig, dst)
    log(f"  사본 생성: {real}")
    return real


def backup_original(orig, log):
    from core.base import safe_copy_indd
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
    bak = f"{os.path.splitext(orig)[0]}.bak-{stamp}.indd"
    real = safe_copy_indd(orig, bak)
    log(f"  원본 백업: {real}")
    return real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("copy", "dry", "apply"), default="copy")
    ap.add_argument("--targets", default="workbook",
                    help="쉼표 구분 대상 이름 또는 all")
    ap.add_argument("--use-existing-copy", action="store_true",
                    help="data_corpus/template_test의 기존 로컬 사본 재사용")
    ap.add_argument("--i-have-user-approval", action="store_true",
                    help="--mode apply(원본 수정)에 필수")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    _load_env()
    log = lambda m: print(m, flush=True)                      # noqa: E731

    if args.mode == "apply" and not args.i_have_user_approval:
        log("[거부] --mode apply 는 원본 조판 템플릿을 수정합니다. "
            "사용자 승인 후 --i-have-user-approval 을 함께 주세요.")
        return 2

    names = [s.strip() for s in args.targets.split(",") if s.strip()]
    targets = TARGETS if "all" in names else \
        [t for t in TARGETS if t["name"] in names]
    if not targets:
        log(f"[오류] 대상 없음: {args.targets} "
            f"(가능: {', '.join(t['name'] for t in TARGETS)}, all)")
        return 2

    before = indesign_docs()
    log(f"[사전] InDesign 열린 문서: {before}")

    results = []
    for t in targets:
        log(f"\n== {t['name']} ({t['engine']}:{t['key']})")
        orig = resolve_target(t)
        if not orig or not os.path.isfile(orig):
            log(f"  [건너뜀] 템플릿 없음: {orig}")
            results.append({"target": t["name"], "skipped_missing": True,
                            "path": orig})
            continue
        if args.mode == "apply":
            backup_original(orig, log)
            path, do_save = orig, True
        elif args.mode == "dry":
            path, do_save = orig, False
        else:
            path = prepare_copy(t, orig, args.use_existing_copy, log)
            do_save = True
        rep = run_on(path, t["src"], t["dst"], do_save, log)
        rep["target"] = t["name"]
        rep["mode"] = args.mode
        rep["source_template"] = orig
        results.append(rep)
        if rep.get("error"):
            log(f"  [오류] {rep['error']}")
        elif rep.get("skipped"):
            log(f"  이미 있음 — 건너뜀 ({t['dst']})")
        else:
            log(f"  생성 완료 ({t['dst']}) 저장={rep.get('saved')} "
                f"들여쓰기 {rep.get('before', {}).get('firstLineIndent')}/"
                f"{rep.get('before', {}).get('leftIndent')} → 0/0")

    after = indesign_docs()
    log(f"\n[사후] InDesign 열린 문서: {after}")
    log(f"[문서 무접촉] {'OK' if after == before else '불일치 — 확인 필요'}")

    ok = sum(1 for r in results if not r.get("error")
             and not r.get("skipped_missing"))
    log(f"\n결과: {ok}/{len(results)} 성공 (모드 {args.mode})")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "results": results}, f,
                      ensure_ascii=False, indent=1)
        log(f"→ {args.json_out}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
