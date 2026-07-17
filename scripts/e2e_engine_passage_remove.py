#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""passage_remove 엔진 실 InDesign E2E (W26).

코퍼스 전체(C) 산출물(0a5da924)에서 지문 2개(기본: 20, 37)를 제거하고
verify까지 전 파이프라인을 실행한다. 출력/인벤토리는 전부
data_corpus/passage_remove/ 리다이렉트 — 실서비스 경로 무접촉.

사용: python3 scripts/e2e_engine_passage_remove.py [라벨1,라벨2...]
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# .env 로드 (핸드북 철칙)
_envp = os.path.expanduser("~/dev/yone-design-web/.env")
if os.path.exists(_envp):
    for _line in open(_envp, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, v = _line.split("=", 1)
            os.environ.setdefault(k, v)

import engines.passage_remove.engine as pre  # noqa: E402

BASE = os.path.join(ROOT, "data_corpus", "passage_remove")
SRC = os.path.join(ROOT, "data_corpus", "wb_engine_e2e", "0a5da924",
                   "고1_26년_06월_전체(C)_v2.indd")


def main():
    labels = (sys.argv[1].split(",") if len(sys.argv) > 1 else ["20", "37"])
    os.makedirs(BASE, exist_ok=True)

    # 출력/인벤토리 리다이렉트 (config 로드 함수 패치 패턴 — 핸드북 8)
    pre.INVENTORY_BASE = os.path.join(BASE, "inventory")
    out_dir = os.path.join(BASE, "out")
    pre.PassageRemoveEngine._config = lambda self: {"output_base": out_dir}

    def log(msg):
        print(msg, flush=True)

    assert os.path.exists(SRC), "소스 없음: " + SRC
    log("=== 1) 인벤토리 추출 (dump + 매처 그룹핑) ===")
    inv_id, inv = pre.create_inventory(SRC, log)
    log("inventory_id: " + inv_id)
    by_label = {g["label"]: g for g in inv["groups"] if g["multi"]}
    for lb in labels:
        assert lb in by_label, "라벨 %s 그룹 없음 (있는 라벨: %s)" % (
            lb, sorted(by_label))
    sel = [by_label[lb]["gid"] for lb in labels]
    log("제거 대상: " + ", ".join(
        "[%s] gid=%d units=%d" % (lb, by_label[lb]["gid"],
                                  len(by_label[lb]["unit_uids"]))
        for lb in labels))

    job_dir = os.path.join(BASE, "job_" + inv_id)
    os.makedirs(job_dir, exist_ok=True)
    eng = pre.PassageRemoveEngine()

    log("=== 2) parse ===")
    json_path = eng.parse({"inventory_id": inv_id,
                           "selected": ",".join(str(g) for g in sel)},
                          job_dir, log)
    log("=== 3) prepare_jsx ===")
    eng.prepare_jsx(json_path, job_dir, log)
    log("=== 4) run_indesign ===")
    eng.run_indesign(job_dir, log)
    log("=== 5) verify ===")
    res = eng.verify(job_dir, log)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("VERIFY ok=%s" % res["ok"])
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
