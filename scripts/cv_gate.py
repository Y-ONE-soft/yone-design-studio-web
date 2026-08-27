#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세로 변환 드라이런 — 조판 착수 전에 S1/S2 게이트와 분할 계획만 확인한다.

InDesign 은 **덤프에만** 쓰고 문서를 고치지 않는다. 마더텅 파이프라인의
--plan-only 와 같은 자리: 여기서 통과해야 실기에 들어간다.

  export PYTHONPATH="/Users/nhj/Library/Python/3.9/lib/python/site-packages"
  /usr/bin/python3 scripts/cv_gate.py <전체(C).indd> [--work DIR] [--reuse]
"""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("indd")
    ap.add_argument("--work", default=None, help="덤프를 둘 폴더")
    ap.add_argument("--reuse", action="store_true",
                    help="이미 있는 덤프를 재사용 (InDesign 무접촉)")
    a = ap.parse_args()

    from core.inspect import dump_frames, dump_indd
    from engines.convert_to_vertical import exam as exam_mod
    from engines.convert_to_vertical import inventory as inv_mod

    def log(m):
        print(m, flush=True)

    src = os.path.abspath(os.path.expanduser(a.indd))
    work = os.path.abspath(a.work or os.path.join("jobs", "cv_gate"))
    os.makedirs(work, exist_ok=True)
    frames_json = os.path.join(work, "src_frames.json")
    stories_json = os.path.join(work, "src_stories.json")

    # 원본 보호 — 덤프도 사본에서 (열린 원본 복사 금지 규칙은 호출자 책임)
    local = os.path.join(work, "source.indd")
    if not a.reuse:
        if not os.path.exists(local) or os.path.getmtime(local) < os.path.getmtime(src):
            shutil.copy2(src, local)
        log(f"[덤프] 프레임 — {os.path.basename(local)}")
        dump_frames(local, frames_json, log)
        log("[덤프] 스토리")
        dump_indd(local, stories_json, log, timeout=1800)

    n = inv_mod.detect_n_problems(frames_json)
    sections = inv_mod.detect_sections(frames_json, n)
    canon = inv_mod.detect_canon(frames_json, n, sections)
    log(f"\n지문 {n}개")
    log(f"canon: {canon}")
    for k, v in sections.items():
        log(f"  {k:8s} p{v[0]}~{v[1]} ({v[1]-v[0]+1}p)")

    result = inv_mod.build_inventory(frames_json, stories_json, sections, canon)
    fails = list(inv_mod.gate(result, canon))
    log("\n[S1] 슬롯 인벤토리")
    for r in result["report"]:
        log(f"  {r['section']:8s} {r.get('kind',''):6s} 검출 {r.get('found','?')}"
            f" 누락 {r.get('missing') or '없음'}"
            + (f" 잉여 {r['extra']}" if r.get("extra") else ""))

    arr_first, arr_last = sections["영작배열"]
    efs, page_count = exam_mod.exam_frames(frames_json, arr_last + 1, 10 ** 6)
    bounds = exam_mod.find_boundaries(efs)
    blocks = exam_mod.blocks_from_boundaries(bounds, page_count)
    info = exam_mod.page_info(frames_json)
    exam_blocks, tail_blocks = exam_mod.partition(blocks, canon, info)
    fails += exam_mod.gate(exam_blocks, tail_blocks, canon)
    exam_targets = exam_mod.split_targets(blocks)
    log(f"\n[S2] 실전 — canon {len(exam_blocks)}지문 / 짤지문 {len(tail_blocks)}개")
    for t in exam_targets:
        log(f"  분할: 지문 {t['code']} p{t['page']} offset {t['offset']}")
    for tb in tail_blocks:
        log(f"  짤지문 {tb['code']}: p{tb['src_pages'][0]}~{tb['src_pages'][-1]}")

    afs, _pc = exam_mod.arrange_frames(frames_json, arr_first, arr_last)
    abounds = exam_mod.arrange_boundaries(afs, canon)
    fails += exam_mod.arrange_gate(abounds, canon)
    arr_targets = exam_mod.arrange_split_targets(abounds, afs)
    log(f"\n[S2] 영작 배열 — 검출 {len(abounds)}지문, 분할 대상 {len(arr_targets)}건")

    add = len(exam_targets) + sum(1 for t in arr_targets
                                  if not t.get("break_only"))
    bo = len(arr_targets) - (len(arr_targets) - sum(
        1 for t in arr_targets if t.get("break_only")))
    log(f"\n분할 합계 {len(exam_targets) + len(arr_targets)}건 "
        f"(페이지 추가 {add} + 끊기만 {bo}) → 분할 후 예상 {page_count + add}p")
    with open(os.path.join(work, "cv_gate.json"), "w", encoding="utf-8") as f:
        json.dump({"canon": canon, "n": n,
                   "sections": {k: list(v) for k, v in sections.items()},
                   "exam_targets": exam_targets, "arrange_targets": arr_targets,
                   "tail_blocks": tail_blocks}, f, ensure_ascii=False, indent=1)

    if fails:
        log("\n❌ 게이트 실패 — 조판 착수 불가")
        for x in fails:
            log("  - " + x)
        return 1
    log("\n✅ 게이트 통과 — 조판 착수 가능")
    return 0


if __name__ == "__main__":
    sys.exit(main())
