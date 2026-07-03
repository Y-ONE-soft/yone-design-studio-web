#!/usr/bin/env python3
"""워크북 v2 E2E — 코퍼스 골든 steps → 플랜 → 실제 InDesign 조판 → 검수.

사용: python3 scripts/e2e_v2_workbook.py [0a5da924]
안전: 템플릿(data_corpus/template_test/워크북C_모의고사.indd)은 safe_copy로
스크래치 복사, 출력은 data_corpus/wb_e2e/. 기존 workbook(v1)은 관여하지 않는다.
검수: 지원 스텝별 플랜 단어 보존율 + 스타일 적용률 + 오버플로우.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

for _line in open(os.path.expanduser("~/dev/yone-design-web/.env")):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

_RE_WORD = re.compile(r"[A-Za-z가-힣]{2,}")


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "0a5da924"
    cdir = os.path.join(REPO, "tests", "corpus", "workbook", case)
    out = os.path.join(REPO, "data_corpus", "wb_e2e", case)
    os.makedirs(out, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    print(f"== 1/5 플랜 빌드 ({case})")
    from engines.workbook_v2.plan import steps_to_plan, unit_paras
    content = json.load(open(f"{cdir}/golden/content.json", encoding="utf-8"))
    plan = steps_to_plan(content["steps"])
    plan_path = os.path.abspath(f"{out}/render_plan.json")
    json.dump(plan, open(plan_path, "w", encoding="utf-8"), ensure_ascii=False)
    supported = [f["step"] for f in plan["flows"]]
    print(f"  지원 스텝 {len(supported)}: {supported}")
    print(f"  미지원: {plan['unsupported']}")

    print("== 2/5 템플릿 복사 + InDesign 조판")
    from core.base import safe_copy_indd
    from core.indesign.jsxbuild import build_jsx
    from core.indesign.runner import run_jsx
    src = os.path.join(REPO, "data_corpus", "template_test",
                       "워크북C_모의고사.indd")
    tpl = os.path.abspath(safe_copy_indd(src, f"{out}/template.indd"))
    out_indd = os.path.abspath(f"{out}/워크북_v2.indd")
    out_pdf = out_indd.replace(".indd", ".pdf")
    jsx_log = os.path.abspath(f"{out}/render.log")
    try:
        os.remove(jsx_log)
    except OSError:
        pass
    jsx = build_jsx(os.path.join(REPO, "core", "jsx",
                                 "workbook_flow.body.jsx"),
                    {"__TEMPLATE_PATH__": tpl, "__PLAN_PATH__": plan_path,
                     "__OUT_INDD__": out_indd, "__OUT_PDF__": out_pdf},
                    log_path=jsx_log)
    run_jsx(jsx, log, poll_log_path=jsx_log, timeout=1800,
            completion_marker="워크북 v2 조판 완료")

    print("== 3/5 스토리 덤프")
    from core.inspect import dump_indd
    dump = dump_indd(out_indd, f"{out}/typeset_dump.json", log)

    print("== 4/5 스텝별 플랜 단어 보존율")
    got = set()
    for st in dump["stories"]:
        for pp in st["paragraphs"]:
            got.update(w.lower() for w in _RE_WORD.findall(pp["t"]))
    per_step = {}
    for flow in plan["flows"]:
        want = set()
        for u in flow["units"]:
            for p in unit_paras(u):
                want.update(w.lower() for w in _RE_WORD.findall(p["t"]))
        missing = want - got
        per_step[flow["step"]] = {
            "units": len(flow["units"]),
            "plan_words": len(want),
            "missing_words": len(missing),
            "missing_sample": sorted(missing)[:8],
            "preserved_pct": round(100.0 * (len(want) - len(missing))
                                   / max(len(want), 1), 2),
        }

    print("== 5/5 리포트")
    # W3 아이콘 검증: 덤프에 ❮T/F❯ 토큰 잔존 금지 + 아이콘 삽입 카운트 로그
    re_tf = re.compile("❮\\s*T\\s*/\\s*F\\s*❯")
    tf_tokens = sum(len(re_tf.findall(pp["t"]))
                    for st in dump["stories"] for pp in st["paragraphs"])
    log_lines = [l.strip() for l in open(jsx_log, encoding="utf-8")]
    report = {
        "case": case,
        "supported_steps": supported,
        "unsupported_steps": plan["unsupported"],
        "per_step": per_step,
        "overflow_stories": dump.get("overflow_stories", 0),
        "tf_tokens_in_dump": tf_tokens,
        "icon_logs": [l for l in log_lines if "아이콘 삽입" in l],
        "render_warnings": [l for l in log_lines if "[경고]" in l],
    }
    json.dump(report, open(f"{out}/report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    ok = all(v["missing_words"] == 0 for v in per_step.values())
    icon_ok = (tf_tokens == 0
               and not any("아이콘" in w for w in report["render_warnings"]))
    print("\n결과:", "✅ 전 스텝 내용 보존 통과" if ok else "❌ 내용 누락",
          "/", "✅ 아이콘 검증 통과" if icon_ok else "❌ 아이콘 검증 실패")
    return 0 if (ok and icon_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
