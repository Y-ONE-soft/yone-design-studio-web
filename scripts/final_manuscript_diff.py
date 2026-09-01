#!/usr/bin/env python3
"""원고 직독 ↔ 워크북 되수확 **대조 하네스** (B1).

지금 파이널이 쓰는 `content.json`(워크북 `.indd` 에서 되수확)과, 같은 지문을
**원고에서 바로 읽은 것**을 나란히 놓는다. 라벨을 믿지 않고 **내용으로** 짝을
지어, 라벨 규칙은 그 결과에서 읽어 낸다.

    python3 scripts/final_manuscript_diff.py <job|content.json> \
        --src "<교재 폴더>" [--src …] [--kind arrange|writing] [-v]

보고:
  · 짝지어진 지문 — 되수확 라벨 ↔ 원고 라벨, 일치도, **글자 차이**
  · 되수확에만 있는 지문 — 원고를 못 찾았다(폴더 누락이거나 다른 출처)
  · 원고에만 있는 지문 — 시험범위 밖이거나 되수확이 흘렸다
"""
import argparse
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.final import manuscript as M  # noqa: E402

RE_WS = re.compile(r"\s+")
RE_MARK = re.compile(r"^\s*\([A-Z]\)\s*")


def norm(s):
    s = unicodedata.normalize("NFC", s or "")
    return RE_WS.sub(" ", s).strip()


def words(s):
    return set(re.findall(r"[a-z']{3,}", norm(s).lower()))


def sig(items):
    """지문 하나의 낱말 집합 — 항목 표시·순서·줄바꿈에 흔들리지 않는다."""
    out = set()
    for it in items:
        out |= words(RE_MARK.sub("", it))
    return out


def jac(a, b):
    return len(a & b) / max(1, len(a | b))


def content_blocks(content, kind):
    if kind == "arrange":
        # ⚠ 되수확본은 '주어진 문장'을 items 밖(`passage`)에 따로 담는다 —
        #   원고에서는 그것도 한 항목이다. 붙여서 비교해야 같은 것이 같다.
        out = []
        for b in content["vol1"].get("문장배열") or []:
            items = ([b["passage"]] if b.get("passage") else []) \
                + list(b.get("items") or [])
            out.append((b["header"], items))
        return out
    if kind == "writing":
        out = []
        v2 = content["vol2"]
        pairs = v2.get("서술형영작") or []
        det = sorted(v2.get("영작_헤더_상세") or [],
                     key=lambda d: d["start_idx"])
        for k, d in enumerate(det):
            s = d["start_idx"]
            e = det[k + 1]["start_idx"] if k + 1 < len(det) else len(pairs)
            out.append((d["header"],
                        [p["choices"] for p in pairs[s:e]]))
        return out
    raise SystemExit(f"모르는 종류: {kind}")


def manuscript_blocks(dirs, kind):
    out = []
    for d in dirs:
        blocks, path = M.read(d, kind)
        if not blocks:
            print(f"  [원고 없음] {d}")
            continue
        for b in blocks:
            items = (b["items"] if kind == "arrange"
                     else [p["choices"] for p in b["pairs"]])
            out.append((b["raw"], items, os.path.basename(d)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--src", action="append", default=[],
                    help="원고가 있는 교재 폴더(반복)")
    ap.add_argument("--kind", default="arrange",
                    choices=["arrange", "writing"])
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    p = a.job
    if os.path.isdir(p):
        p = os.path.join(p, "content.json")
    with open(p, encoding="utf-8") as f:
        content = json.load(f)

    cb = content_blocks(content, a.kind)
    mb = manuscript_blocks(a.src, a.kind)
    print(f"■ 되수확 {len(cb)}지문 · 원고 {len(mb)}지문 ({a.kind})")

    csig = [(h, sig(i), i) for h, i in cb]
    msig = [(r, sig(i), i, d) for r, i, d in mb]
    used, rows, orphan = set(), [], []
    for h, s, items in csig:
        best, bi = 0.0, None
        for k, (r, ms, mi, d) in enumerate(msig):
            v = jac(s, ms)
            if v > best:
                best, bi = v, k
        if bi is None or best < 0.5:
            orphan.append((h, round(best, 2)))
            continue
        used.add(bi)
        r, ms, mi, d = msig[bi]
        same = norm(" ".join(items)) == norm(" ".join(mi))
        rows.append((h, r, d, round(best, 3), same, items, mi))

    exact = sum(1 for x in rows if x[4])
    print(f"  짝 {len(rows)} · 글자까지 같음 {exact} · "
          f"짝 못 찾음 {len(orphan)} · 원고에만 {len(msig) - len(used)}")
    for h, r, d, v, same, items, mi in rows:
        mark = "=" if same else "~"
        if a.verbose or not same:
            print(f"   {mark} {h:<18} ← {r:<26} [{d[:22]}] jac {v}")
        if not same and a.verbose:
            for x, y in zip(items, mi):
                if norm(x) != norm(y):
                    print(f"       되수확: {norm(x)[:96]}")
                    print(f"       원고  : {norm(y)[:96]}")
    for h, v in orphan:
        print(f"   ! 짝 못 찾음: {h} (최대 jac {v})")
    for k, (r, ms, mi, d) in enumerate(msig):
        if k not in used:
            print(f"   + 원고에만: {r} [{d[:26]}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
