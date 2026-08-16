# -*- coding: utf-8 -*-
"""S3~S5 배치 플랜 — 세로 페이지 순서·마스터·M 패딩을 결정론적으로 계산한다.

판정은 전부 Python 에서 끝내고, JSX 에는 "몇 번 페이지를 어디로 옮기고 어떤
마스터를 걸어라"는 지시만 넘긴다. 그래야 InDesign 없이 플랜을 검증할 수 있다
(현행 엔진은 판정이 JSX 안에 있어 실패해도 로그 한 줄로만 드러났다).

플랜 스키마
  {
    "cycles": [
       {"code": "20",
        "slots": [{"slot":1,"section":"어휘","src_pages":[4],"master":"A-마스터"}, ...],
        "exam":  {"src_pages":[176,177,178,179], "master":"O-마스터"},
        "pad":   0 or 1},
       ...],
    "tail": [{"code":"18","src_pages":[...]}, ...],   # canon 밖 짤지문
    "order": [ {"src":4,  "master":"A-마스터"},        # 최종 페이지 순서
               {"src":None,"master":"M-마스터"} ... ]  # src=None → 신규 메모 페이지
  }
"""

from __future__ import annotations

from .inventory import SLOTS, normalize_code, resolve_to_canon

MASTER_OF_SLOT = {n: "%s-마스터" % m for n, _s, m in SLOTS}
EXAM_MASTER = "O-마스터"
PAD_MASTER = "M-마스터"


def build_cycles(inventory, canon, exam_blocks):
    """지문별 사이클 구성.

    inventory : inventory.build_inventory()["inventory"]
    exam_blocks: {canon코드: [원본 페이지, ...]}  (S2 산출)
    """
    cycles = []
    for code in canon:
        code = normalize_code(code)
        slots = []
        for name, slot_no, master in SLOTS:
            got = inventory.get(code, {}).get(name)
            pages = list(got.get("pages") or []) if got else []
            slots.append({"slot": slot_no, "section": name,
                          "src_pages": pages, "master": "%s-마스터" % master})
        exam = {"src_pages": list(exam_blocks.get(code) or []),
                "master": EXAM_MASTER}
        n = sum(len(s["src_pages"]) for s in slots) + len(exam["src_pages"])
        cycles.append({"code": code, "slots": slots, "exam": exam,
                       "pad": 1 if n % 2 else 0, "length": n + (1 if n % 2 else 0)})
    return cycles


def build_order(cycles, tail_blocks, front_pages):
    """최종 페이지 순서. src=None 은 신규 삽입할 M 메모 페이지."""
    order = [{"src": p, "master": None, "role": "front"} for p in front_pages]
    for cy in cycles:
        for s in cy["slots"]:
            for p in s["src_pages"]:
                order.append({"src": p, "master": s["master"],
                              "role": "slot%d" % s["slot"], "code": cy["code"]})
        for p in cy["exam"]["src_pages"]:
            order.append({"src": p, "master": EXAM_MASTER,
                          "role": "exam", "code": cy["code"]})
        if cy["pad"]:
            order.append({"src": None, "master": PAD_MASTER,
                          "role": "pad", "code": cy["code"]})
    for tb in tail_blocks:
        for p in tb["src_pages"]:
            order.append({"src": p, "master": EXAM_MASTER,
                          "role": "tail", "code": tb["code"]})
    return order


def build_plan(inventory, canon, exam_blocks, tail_blocks, front_pages):
    cycles = build_cycles(inventory, canon, exam_blocks)
    order = build_order(cycles, tail_blocks, front_pages)
    return {"cycles": cycles, "tail": tail_blocks, "order": order}


def gate(plan, src_page_count, canon):
    """플랜 게이트 — 실패 사유 리스트 (빈 리스트 = 통과)."""
    fails = []
    canon = [normalize_code(c) for c in canon]

    # 1) 사이클별 슬롯 10개 전원 + 실전 1블록 이상
    for cy in plan["cycles"]:
        empty = [s["section"] for s in cy["slots"] if not s["src_pages"]]
        if empty:
            fails.append("지문 %s: 슬롯 %s 비어 있음" % (cy["code"], empty))
        if not cy["exam"]["src_pages"]:
            fails.append("지문 %s: 실전 블록 없음" % cy["code"])
        if cy["length"] % 2:
            fails.append("지문 %s: 사이클 길이 %d (홀수)" % (cy["code"], cy["length"]))

    # 2) canon 전원 존재
    have = {cy["code"] for cy in plan["cycles"]}
    miss = [c for c in canon if c not in have]
    if miss:
        fails.append("canon 지문 누락: %s" % miss)

    # 3) 원본 페이지가 중복 배치되거나 유실되지 않았는지
    used = [o["src"] for o in plan["order"] if o["src"] is not None]
    dup = sorted({p for p in used if used.count(p) > 1})
    if dup:
        fails.append("원본 페이지 중복 배치: %s" % dup[:10])
    return fails


def coverage(plan, src_page_count):
    """원본 페이지 사용 현황 — 어느 페이지가 어디에도 안 실렸는지."""
    used = {o["src"] for o in plan["order"] if o["src"] is not None}
    unused = [p for p in range(1, src_page_count + 1) if p not in used]
    return {"used": len(used), "unused": unused,
            "total_out": len(plan["order"])}
