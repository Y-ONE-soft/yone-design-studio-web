#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""교과서 중요어휘 시트 → `data/final_textbook_vocab.json` 사본.

시트(「직전보충 VOL2 원고정리 교과서」)가 링크 공개가 아니면 조판이 곧장
못 읽는다. 그때를 위해 받은 xlsx 로 사본을 뜬다.

    python3 scripts/final_textbook_vocab_snapshot.py <받은.xlsx>
"""
import datetime
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from engines.final import textbook_vocab as TV              # noqa: E402

rows = TV.rows_from_xlsx(open(sys.argv[1], "rb").read())
json.dump({"sheet": TV.SHEET_ID, "taken": datetime.date.today().isoformat(),
           "rows": rows}, open(TV.SNAPSHOT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("■ %d칸 → %s" % (len(rows), os.path.relpath(TV.SNAPSHOT, BASE)))
for r in rows:
    print("  %-8s %-8s %-20s %s" % (r["subject"], r["pub"], r["head"],
                                    "요약" if "내용요약" in r["text"] else "★요약 없음"))
