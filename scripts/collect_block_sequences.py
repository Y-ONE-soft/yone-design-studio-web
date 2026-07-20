#!/usr/bin/env python3
"""유형별 문항 블록 시퀀스 실측 수집 (W38 — 추측 금지, 코퍼스 실측).

전 골든 step3 코퍼스를 현행 분류기(core.structure.classify_paragraphs)로
재판정해 문항 단위 블록 시퀀스를 수집하고, 발문 유형(taxonomy leaf 코드)별
관측 시퀀스/빈도를 core/structure/block_sequences.json 으로 저장한다.

문항 경계 = 번호형 발문(Q, "N." / "N)" 접두) 또는 Q-INTRO.
블록 토큰 = 연속 압축: Q / INTRO / P / PC(배경) / SUM / COND(마커+항목) /
            BOX / C(선지 run) / ANS / WORD / K / SYM / SRC / UNK

사용:
    python3 scripts/collect_block_sequences.py          # 수집 + 저장
"""
import collections
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.structure import classify_paragraphs  # noqa: E402

OUT = os.path.join(REPO, "core", "structure", "block_sequences.json")
_NUM_Q = re.compile(r"^\s*\d{1,3}\s*[.)]")

_TOKEN = {
    "Q": "Q", "Q-INTRO": "INTRO", "P": "P", "P-CONTEXT": "PC",
    "Sum": "SUM", "Cond": "COND", "Box": "BOX", "C": "C", "Ans": "ANS",
    "AnsL": "ANSL",
    "Word": "WORD", "K": "K", "Sym": "SYM", "SRC": "SRC",
    "UNKNOWN": "UNK", "GH": None, "A": None, "BLANK": None,
}


def unit_sequences(paras):
    """분류 결과 → [(q_code, 블록 시퀀스 튜플)] (문항 단위)."""
    out = classify_paragraphs(paras)
    units = []
    cur = None
    for item in out:
        k, t = item["kind"], item["text"]
        is_q_start = (k == "Q" and _NUM_Q.match(t)) or k == "Q-INTRO"
        if is_q_start:
            if cur:
                units.append(cur)
            cur = {"q_code": item.get("q_code"), "seq": []}
        if cur is None:
            continue
        tok = _TOKEN.get(k, k)
        if tok is None:
            continue
        if not cur["seq"] or cur["seq"][-1] != tok:
            cur["seq"].append(tok)
    if cur:
        units.append(cur)
    return units


def main():
    per_code = collections.defaultdict(collections.Counter)
    files = sorted(glob.glob(os.path.join(
        REPO, "tests", "corpus", "*", "*", "golden", "content.json")))
    n_units = 0
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        s3 = (d.get("steps") or {}).get("step3")
        if not isinstance(s3, dict):
            continue
        for grp in ("normal", "short"):
            for it in s3.get(grp) or []:
                ps = [{"text": p.get("text", ""), "runs": p.get("runs")}
                      for p in it.get("paragraphs", [])]
                if not ps:
                    continue
                for u in unit_sequences(ps):
                    code = u["q_code"] or "(미분류)"
                    per_code[code][" ".join(u["seq"])] += 1
                    n_units += 1
    data = {
        "_doc": ("유형(taxonomy leaf)별 문항 블록 시퀀스 실측 분포 — "
                 "scripts/collect_block_sequences.py 산출 (전 골든 step3 "
                 "코퍼스 재판정). 시퀀스 = 연속 압축 블록 토큰. 판정이 "
                 "기대 시퀀스와 어긋나는 하드 불변식 위반은 "
                 "block_grammar.validate_sequence가 [경고]로 지목한다."),
        "_source": {"golden_files": len(files), "units": n_units},
        "sequences": {
            code: {"count": sum(cnt.values()),
                   "observed": dict(cnt.most_common())}
            for code, cnt in sorted(per_code.items())
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"저장: {OUT}")
    print(f"골든 {len(files)}개 / 문항 {n_units}개 / "
          f"유형 {len(per_code)}종")
    top = sorted(per_code.items(), key=lambda kv: -sum(kv[1].values()))[:12]
    for code, cnt in top:
        best = cnt.most_common(2)
        print(f"  {sum(cnt.values()):5d} {code:24s} "
              + " | ".join(f"[{s}]×{c}" for s, c in best))


if __name__ == "__main__":
    main()
