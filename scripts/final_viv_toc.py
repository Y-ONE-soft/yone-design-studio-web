#!/usr/bin/env python3
"""책의 **차례를 그대로 찍어 본다** — 뭐가 어떤 순서로 들어갔는지 확인용.

    python3 scripts/final_viv_toc.py "<책 폴더>"        # Vol1 또는 Vol2
    python3 scripts/final_viv_toc.py "<책 폴더>" -v     # 지문 전부

`bin/viv … data` 가 만든 `data.json` 을 읽는다(조판 전에 확인할 수 있다).
"""
import argparse
import json
import os


def show(path, full=False):
    d = json.load(open(path, encoding="utf-8"))
    print("%s %s %s" % (d["grade"], d["school"], d["period"]))
    for _k, v in sorted(d["vols"].items()):
        ch = v["chapter"]
        print("\nVol%d  Chapter.%02d %s" % (v["vol"], ch["no"], ch["en"]))
        for s in v["sections"]:
            print("  %d. %-14s %3d지문" % (s["no"], s["toc"], len(s["blocks"])))
            hs = [b["header"] for b in s["blocks"]]
            if full:
                for h in hs:
                    print("       ", h)
            else:
                print("       " + " · ".join(hs[:6])
                      + (" …" if len(hs) > 6 else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    p = a.book if a.book.endswith(".json") else os.path.join(a.book, "data.json")
    show(p, a.verbose)
