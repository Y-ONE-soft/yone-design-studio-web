#!/usr/bin/env python3
"""**원고 직독 content.json 빌더** (B6 교체).

지금 파이널이 워크북 `.indd` 에서 되수확하던 자리를 원고로 갈아 끼운다.

    python3 scripts/final_manuscript_build.py <job> [-o content_원고.json]

바꾸는 것 (원고에서 직접):
    · 문장배열      `Step1 C1 문장배열` — 라벨도 원고가 말한다
    · 서술형영작    `Step2 C2 영작배열`

그대로 두는 것 (원래 원고·시트가 정본이라 바꿀 게 없다):
    · 어법수정      이미 교과서작업/EBS작업의 2열 표 docx 를 읽는다
    · 중요어휘      구글시트(고1·고2) — 선생님이 고른 부분집합이라 유도 불가
    · 문장삽입      **아직 되수확**. 원고 출처가 확정되지 않았다(§ 남은 것)

시험범위는 **워크북 파일 이름**이 말한다(`…(리딩파워12강,14강)…`). 그 강·과의
지문은 전부 싣는다 — 되수확본이 흘린 것(리딩파워 14강 6지문)이 여기서 돌아온다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.final import manuscript as M          # noqa: E402
from engines.final import manuscript_locate as L   # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from final_manuscript_diff import auto_sources, words as _words  # noqa: E402


# ── 차례(canonical) ─────────────────────────────────────────────────────
RE_TB = re.compile(r"^교과서(\d+)과\s*(.+)$")
RE_UNIT = re.compile(r"^(올포|리딩파워)\s*(\d+)강\s*(.+)$")
RE_MOCK = re.compile(r"^(\d{2})(\d{2})(\d{2})(?:~\d{2})?$")
RE_G3 = re.compile(r"^(?:(\d+)강|test(\d+))\s*(.+)$")
TB_TAIL = {"RM": 90, "딥러닝": 95}
UNIT_TAIL = {"분석": 0, "서술형": 90, "논술형": 95}


def order_key(label):
    """파이널의 차례 — 교과서 → 강(올포·리딩파워) → 모의(날짜) → 고3."""
    m = RE_TB.match(label)
    if m:
        tail = m.group(2)
        n = TB_TAIL.get(tail)
        if n is None:
            mm = re.search(r"(\d+)", tail)
            n = int(mm.group(1)) if mm else 50
        return (0, int(m.group(1)), n, label)
    m = RE_UNIT.match(label)
    if m:
        tail = m.group(3)
        n = UNIT_TAIL.get(tail)
        if n is None:
            if tail.startswith("Ex"):
                n = int(re.sub(r"\D", "", tail) or 0)
            elif tail.startswith("본문"):
                n = 10 + int(re.sub(r"\D", "", tail) or 0)
            else:
                n = 10 + int(re.sub(r"\D", "", tail) or 0)
        return (1, int(m.group(2)), n, label)
    m = RE_MOCK.match(label)
    if m:
        return (2, int(m.group(1)) * 100 + int(m.group(2)),
                int(m.group(3)), label)
    m = RE_G3.match(label)
    if m:
        unit = int(m.group(1)) if m.group(1) else 100 + int(m.group(2))
        return (3, unit, int(re.sub(r"\D", "", m.group(3)) or 0), label)
    return (9, 0, 0, label)


# ── 시험범위 ────────────────────────────────────────────────────────────
def scope_labels(content):
    """시험범위 = **어느 한 섹션에라도 있는 지문**.

    어법수정(교재 docx)·중요어휘(구글시트)·영작은 워크북 `.indd` 와 **다른
    출처**다. 한 섹션에서 빠진 지문이 다른 섹션에는 살아 있는 일이 흔하고
    (광문2 리딩파워 14강은 어법·영작에만 있었다), 그 합집합이 실제 범위다.
    시트를 다시 부르지 않아도 되고, 비대칭 자체가 근거가 된다.
    """
    out = set()
    v1, v2 = content.get("vol1") or {}, content.get("vol2") or {}
    for sec in ("문장배열", "문장삽입"):
        out |= {b["header"] for b in v1.get(sec) or []}
    out |= set(v2.get("어법_헤더") or [])
    out |= {d["header"] for d in v2.get("영작_헤더_상세") or []}
    # 중요어휘는 한 덩어리 문자열 — 빈 줄로 끊고 요약 표제가 아닌 머리만
    text = v1.get("중요어휘_왼") or ""
    group, first = [], True
    for ln in text.split("\n"):
        if ln.strip():
            if first:
                group.append(ln.strip())
                first = False
        else:
            first = True
    from core.render_vivlio.series.final import data as _d
    out |= {_d.norm_header(g) for g in group if not _d.is_summary_mark(g)}
    return out


# ── 빌드 ────────────────────────────────────────────────────────────────
def build(content, log=print, keep_all=False):
    srcs = auto_sources(content, log)
    scope = None if keep_all else scope_labels(content)
    arrange, writing, seen = [], [], set()
    for d, spec in srcs:
        if not spec:
            continue
        name = os.path.basename(d)
        blocks, path = M.read(d, "arrange")
        for b in blocks:
            lab = L.to_final_label(spec, b["raw"])
            if not lab:
                log(f"  [라벨 없음] {b['raw']} [{name}]")
                continue
            if lab in seen or (scope is not None and lab not in scope):
                continue
            seen.add(lab)
            items = list(b["items"])
            # 첫 항목이 표기 없는 줄이면 그것이 **주어진 문장**이다
            given = ""
            if items and not re.match(r"^\s*\([A-Z]\)", items[0]):
                given = items.pop(0)
            arrange.append({"source": os.path.basename(path or name),
                            "header": lab, "items": items,
                            **({"passage": given} if given else {})})
        wb, wpath = M.read(d, "writing")
        for b in wb:
            lab = L.to_final_label(spec, b["raw"])
            if not lab or not b["pairs"]:
                continue
            if scope is not None and lab not in scope:
                continue
            writing.append({"header": lab, "pairs": b["pairs"]})

    # 원고가 없는 지문(외부지문 업로드본 등)은 **되수확본을 그대로 데려온다** —
    # 갈아 끼우면서 잃는 것이 하나도 없어야 한다.
    # ⚠ 다만 **내용이 이미 들어와 있으면** 데려오지 않는다. 되수확본에는 같은
    #   글이 엉뚱한 라벨로 한 번 더 들어 있는 자리가 있어서(광문2 영작
    #   `리딩파워 2강 02` 등 7건), 그대로 데려오면 중복이 된다.
    def _n(t):
        # 공백을 통째로 지운다 — 되수확본은 같은 문장을 띄어쓰기만 달리
        # 담아 둔 자리가 있어서, 한 칸 차이로 '중복 아님'이 된다.
        return re.sub(r"\s+", "", re.sub(r"^\s*\([A-Z]\)\s*", "", t or ""))

    def _covered(lines, pool):
        """이 글이 이미 들어와 있는가 — **문장 단위 완전 일치**로 본다.

        낱말 겹침으로 보면 짧은 글이 엉뚱하게 '중복'이 된다(명일1 외부지문
        본문1 이 그렇게 버려졌다).
        """
        got = [_n(x) for x in lines if len(_n(x)) > 15]
        return bool(got) and all(g in pool for g in got)

    have = {b["header"] for b in arrange}
    pool_a = {_n(x) for b in arrange
              for x in [b.get("passage", "")] + b["items"]}
    for b in content["vol1"].get("문장배열") or []:
        if b["header"] in have:
            continue
        if _covered([b.get("passage", "")] + (b.get("items") or []), pool_a):
            log(f"  [중복 — 버림] 문장배열 {b['header']}")
            continue
        arrange.append(dict(b, source=(b.get("source", "") + " [되수확]")))
        log(f"  [원고 없음 → 되수확 유지] 문장배열 {b['header']}")

    havew = {b["header"] for b in writing}
    pool_w = {_n(p["korean"]) for b in writing for p in b["pairs"]}
    old_pairs = content["vol2"].get("서술형영작") or []
    det = sorted(content["vol2"].get("영작_헤더_상세") or [],
                 key=lambda d: d["start_idx"])
    for k, d in enumerate(det):
        if d["header"] in havew:
            continue
        e = det[k + 1]["start_idx"] if k + 1 < len(det) else len(old_pairs)
        chunk = old_pairs[d["start_idx"]:e]
        if not chunk:
            continue
        if _covered([p["korean"] for p in chunk], pool_w):
            log(f"  [중복 — 버림] 영작 {d['header']}")
            continue
        writing.append({"header": d["header"], "pairs": chunk})
        log(f"  [원고 없음 → 되수확 유지] 영작 {d['header']}")

    arrange.sort(key=lambda b: order_key(b["header"]))
    writing.sort(key=lambda b: order_key(b["header"]))

    out = json.loads(json.dumps(content, ensure_ascii=False))
    out["vol1"]["문장배열"] = arrange
    pairs, det = [], []
    for b in writing:
        det.append({"header": b["header"], "start_idx": len(pairs)})
        pairs += b["pairs"]
    out["vol2"]["서술형영작"] = pairs
    out["vol2"]["영작_헤더_상세"] = det
    out["vol2"]["영작_헤더"] = [d["header"] for d in det]
    out["총_문장배열"] = sum(len(b["items"]) for b in arrange)
    out["총_서술형영작"] = len(pairs)
    out["_source"] = "manuscript"
    # 어디서 읽었는지 남긴다 — 이 파일만으로 다시 대조·재빌드가 된다
    out["_manuscript_sources"] = [{"dir": d, "spec": spec}
                                  for d, spec in srcs if spec]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("-o", "--out")
    ap.add_argument("--all", action="store_true",
                    help="시험범위를 무시하고 그 강·과의 지문을 전부 싣는다")
    a = ap.parse_args()
    p = a.job
    if os.path.isdir(p):
        p = os.path.join(p, "content.json")
    with open(p, encoding="utf-8") as f:
        content = json.load(f)
    old_a = {b["header"] for b in content["vol1"]["문장배열"]}
    old_w = {d["header"] for d in content["vol2"]["영작_헤더_상세"]}
    out = build(content, keep_all=a.all)
    new_a = {b["header"] for b in out["vol1"]["문장배열"]}
    new_w = {d["header"] for d in out["vol2"]["영작_헤더_상세"]}
    print(f"■ 문장배열 {len(old_a)} → {len(new_a)}"
          f"  (되찾음 {len(new_a - old_a)} · 사라짐 {len(old_a - new_a)})")
    if new_a - old_a:
        print("   + " + ", ".join(sorted(new_a - old_a)[:12]))
    if old_a - new_a:
        print("   - " + ", ".join(sorted(old_a - new_a)[:12]))
    print(f"■ 서술형영작 {len(old_w)} → {len(new_w)}"
          f"  (되찾음 {len(new_w - old_w)} · 사라짐 {len(old_w - new_w)})")
    if old_w - new_w:
        print("   - " + ", ".join(sorted(old_w - new_w)[:12]))
    dest = a.out or os.path.join(os.path.dirname(p), "content_원고.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("→", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
