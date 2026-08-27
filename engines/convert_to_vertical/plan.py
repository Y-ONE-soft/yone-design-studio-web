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


# ── 후처리(cv_finish.jsx) 사이클 ────────────────────────────────────────────
# build_cycles/build_order 는 "원본 페이지를 어디로 보낼까"의 플랜이다. 반면
# cv_finish.jsx 는 **재배치가 끝난 산출물**의 페이지 번호로 지시를 받는다:
#   {code, start, end, slot_masters:[마스터×슬롯페이지수], pad:bool}
# 그래서 산출물 프레임 덤프에서 사이클 경계를 다시 읽어 만든다. 원본 플랜으로
# 예측하지 않는 이유: body 의 재배치 결과와 어긋나면 마스터가 통째로 한 칸씩
# 밀려 적용되기 때문이다 (침묵 사고). 산출물이 유일한 진실이다.

def _slot_masters(inventory, code):
    """지문 하나의 슬롯 마스터 열 — 슬롯이 2p면 같은 마스터 2회 (SPEC 2장)."""
    out = []
    for name, _slot_no, master in SLOTS:
        got = (inventory.get(code) or {}).get(name) or {}
        n = len(got.get("pages") or [])
        if not n and got.get("kind") == "thread":
            # 스레드 슬롯(영작 배열)은 인벤토리에 페이지가 없다. body STEP4.4 가
            # 섹션마다 페이지 1개를 만들어 재배분하므로 지문당 1p 다.
            n = 1
        out.extend(["%s-마스터" % master] * n)
    return out


def cycle_spans(out_frames_json, canon):
    """산출물에서 지문별 사이클 구간 [(code, start, end)] — 문서 순."""
    from .inventory import load_frames, code_of

    frames, page_count = load_frames(out_frames_json)
    canon_n = [normalize_code(c) for c in canon]

    first_page = {}
    tail_start = None
    by_page = {}
    master_of = {}
    for f in frames:
        by_page.setdefault(f["pidx"] + 1, []).append(f)
        master_of.setdefault(f["pidx"] + 1, f.get("master") or "")
    for pg in sorted(by_page):
        fs = sorted(by_page[pg], key=lambda f: (f["gb"][0], f["gb"][1]))
        for f in fs:
            raw = code_of(f["head"])
            if not raw:
                continue
            c = resolve_to_canon(raw, canon_n)
            if c and c not in first_page:
                first_page[c] = pg
            break

    missing = [c for c in canon_n if c not in first_page]
    if missing:
        raise ValueError("산출물에서 지문 %s 의 사이클 시작을 찾지 못함" % missing)

    starts = [(c, first_page[c]) for c in canon_n]
    if [p for _c, p in starts] != sorted(p for _c, p in starts):
        raise ValueError("사이클 시작 순서가 canon 과 다름 — 재배치 불완전: %s"
                         % [(c, p) for c, p in starts])

    # 마지막 사이클의 끝 = 짤지문/뒤부속 시작 직전. canon 밖 코드가 처음
    # 나오는 페이지를 경계로 본다 (없으면 문서 끝).
    last_start = starts[-1][1]
    for pg in sorted(by_page):
        if pg <= last_start:
            continue
        fs = sorted(by_page[pg], key=lambda f: (f["gb"][0], f["gb"][1]))
        for f in fs:
            raw = code_of(f["head"])
            if raw and not resolve_to_canon(raw, canon_n):
                tail_start = pg
                break
            if raw:
                break
        if tail_start:
            break

    def _structural(pg):
        m = master_of.get(pg, "")
        return ("간지" in m) or not m

    spans = []
    for i, (c, s) in enumerate(starts):
        if i + 1 < len(starts):
            e = starts[i + 1][1] - 1
        else:
            # 마지막 사이클 끝에서 간지/무마스터 페이지를 걷어낸다. 안 그러면
            # 짤지문 앞 간지가 마지막 사이클에 붙어 길이 파리티가 어긋나고,
            # 슬롯 마스터가 간지 위에 덮여 쓰인다.
            e = (tail_start - 1) if tail_start else page_count
            while e > s and _structural(e):
                e -= 1
        spans.append((c, s, e))
    return spans, page_count


def build_finish_cycles(out_frames_json, inventory, canon):
    """cv_finish.jsx 용 cycles + 게이트 실패 사유."""
    spans, page_count = cycle_spans(out_frames_json, canon)
    cycles, fails = [], []
    for code, start, end in spans:
        length = end - start + 1
        masters = _slot_masters(inventory, code)
        if not masters:
            fails.append("지문 %s: 슬롯 인벤토리 비어 있음" % code)
        elif length < len(masters) + 1:
            fails.append("지문 %s: 사이클 %dp < 슬롯 %dp + 실전 1p"
                         % (code, length, len(masters)))
        cycles.append({"code": code, "start": start, "end": end,
                       "slot_masters": masters, "length": length,
                       "pad": bool(length % 2)})
    for a, b in zip(cycles, cycles[1:]):
        if a["end"] + 1 != b["start"]:
            fails.append("사이클 불연속: %s 끝 %d → %s 시작 %d"
                         % (a["code"], a["end"], b["code"], b["start"]))
    return {"cycles": cycles, "page_count": page_count}, fails
