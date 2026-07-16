#!/usr/bin/env python3
"""품질 루프 14라운드 E2E — 리딩파워(EBS) 워크북 v2 레이아웃 정책 확산.

케이스: r7c16olympos (올림포스 독해기본2 9강 스텝3 — W17 코퍼스).

  main 모드: 엔진 활성 구성 실기 검증 — question_keep + delete
    (기지 warning 'EBS 내지 대지 밖 템플릿 overset'은 유지 — W12 (2)).
  probe 모드: delete 모드를 플랜에 강제 주입한 활성 전 사전 실측 —
    r14 실측 결과 critical 0/warning 0, 간지 라벨 전부 오른쪽(R) +
    내장 M 채움(p5) 위치 정상, 24p→23p (delete가 M-모드와 다른 구간은
    마지막 간지 이후뿐이라 간지 정렬이 구조적으로 보존됨을 확인 —
    이 근거로 엔진 기본을 delete로 활성).

사용: python3 scripts/e2e_round14_ebs.py [main|probe]

안전(출력 리다이렉트): _load_v1_config 패치 — 출력은
data_corpus/round14/c16_ebs{,_probe}/, 내지는 data_corpus/template_test/
EBS리딩파워_내지.indd 로컬 사본. 실 운영 경로/사용자 문서 무접촉.
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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    case_dir = os.path.join(REPO, "tests", "corpus", "ebs_workbook_v2",
                            "r7c16olympos")
    sub = "c16_ebs" if mode == "main" else "c16_ebs_probe"
    out = os.path.abspath(os.path.join(REPO, "data_corpus", "round14", sub))
    job = os.path.join(out, "job")
    os.makedirs(job, exist_ok=True)
    log = lambda m: print(f"  {m}", flush=True)

    import engines.ebs_workbook_v2.engine as eng_mod
    from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine

    real_load = eng_mod._load_v1_config

    def _patched():
        cfg = real_load()
        cfg["indd_output_dir"] = out
        cfg["indd_original"] = os.path.join(
            REPO, "data_corpus", "template_test", "EBS리딩파워_내지.indd")
        return cfg

    eng_mod._load_v1_config = _patched
    engine = EbsWorkbookV2Engine()
    if mode == "probe":
        # delete 모드 강제 주입 (엔진 코드 무변경 프로브 — 보류 근거 실측)
        real_deco = engine._plan_decorations

        def _probe_deco(job_dir, cfg):
            deco = real_deco(job_dir, cfg)
            deco["page_cleanup"] = {"empty": "delete"}
            return deco
        engine._plan_decorations = _probe_deco

    print(f"== 1/3 prepare_jsx (r7c16olympos, mode={mode})")
    for fn in os.listdir(os.path.join(case_dir, "meta")):
        if fn.endswith(".txt"):
            shutil.copy2(os.path.join(case_dir, "meta", fn),
                         os.path.join(job, fn))
    json_path = os.path.join(job, "content.json")
    shutil.copy2(os.path.join(case_dir, "golden", "content.json"), json_path)
    engine.prepare_jsx(json_path, job, log)
    plan = json.load(open(os.path.join(job, "render_plan.json"),
                          encoding="utf-8"))
    qk = plan.get("question_keep") or {}
    print("  [플랜] page_cleanup:", plan.get("page_cleanup"),
          "/ 문제단위킵 시작점",
          sum(len(v.get("starts") or [])
              for v in (qk.get("flows") or {}).values()))

    print("== 2/3 run_indesign")
    engine.run_indesign(job, log)

    print("== 3/3 verify (검수 게이트)")
    result = engine.verify(job, log)
    print(json.dumps({k: v for k, v in result.items() if k != "stories"},
                     ensure_ascii=False, indent=1))

    dump = json.load(open(os.path.join(job, "typeset_dump.json"),
                          encoding="utf-8"))
    pages = dump.get("pages") or []
    inv = {str(e.get("p")): e for e in pages}
    print(f"\n페이지 수: {dump.get('page_count')}")
    for st in dump.get("stories", []):
        ps = st.get("paragraphs", [])
        if ps and (ps[0].get("t") or "").strip().startswith(
                "EBS Reading Power"):
            pgs = st.get("pg") or []
            side = inv.get(str(pgs[0]), {}).get("side") if pgs else "?"
            print(f"  간지 라벨 스토리 idx{st['idx']} pg={pgs} side={side}")
    m_pages = [(e.get("p"), e.get("side")) for e in pages
               if str(e.get("m") or "").startswith("M")]
    print("M 페이지:", m_pages)
    print("\n결과:", "OK verify ok=True" if result["ok"]
          else "FAIL verify ok=False")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
