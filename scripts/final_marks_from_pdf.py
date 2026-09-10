#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연구원이 PDF 에 단 주석 → **지문 정오표**.

    python3 scripts/final_marks_from_pdf.py <주석 단 PDF …> --book <책폴더>
    python3 scripts/final_marks_from_pdf.py … --apply        # 정오표에 쌓기

연구원은 완성 PDF 에 형광펜·밑줄·취소선을 긋고 쪽지를 붙여 보낸다. 그 자리를
**지면 좌표가 아니라 글자로** 찾는다 — 그래야 같은 지문을 쓰는 다른 학교 책에
그대로 얹힌다(`engines/final/marks.py`).

쪽지 글이 `틀린 것 → 고친 것` 꼴이면 그대로 고침이 되고, 아니면 **사람이
읽을 목록**으로만 남긴다. 무엇을 하라는 말인지 기계가 지어내지 않는다.

    recieve → receive          ← 바로 고침
    철자 틀림                   ← 목록에만 (무엇으로 고칠지 안 적혀 있다)
    삭제                        ← 목록에만
"""
import argparse
import json
import os
import re
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from engines.final import marks as MK                        # noqa: E402

MARKUP = {fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE,
          fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY}
# `틀린 것 → 고친 것` — 화살표는 사람마다 다르게 적는다
RE_ARROW = re.compile(r"\s*(?:→|->|=>|⇒|>>)\s*")


def quad_text(page, annot):
    """형광펜이 덮은 글. 사각형 하나로 떠 오면 옆 글자까지 딸려 온다 —
    네 점 묶음(quad)마다 따로 떠서 잇는다."""
    v = annot.vertices or []
    if len(v) >= 4 and len(v) % 4 == 0:
        out = []
        for i in range(0, len(v), 4):
            q = fitz.Quad(v[i], v[i + 1], v[i + 2], v[i + 3])
            out.append(page.get_textbox(q.rect).strip())
        return " ".join(x for x in out if x)
    return page.get_textbox(annot.rect).strip()


def read_pdf(path):
    """[(쪽, 종류, 덮은 글, 쪽지 글)] — 주석이 없으면 빈 목록."""
    out = []
    doc = fitz.open(path)
    for pno, page in enumerate(doc, 1):
        for a in page.annots() or []:
            t = a.type[0]
            note = (a.info.get("content") or "").strip()
            body = quad_text(page, a) if t in MARKUP else ""
            if t == fitz.PDF_ANNOT_FREE_TEXT and not note:
                note = (a.get_text() or "").strip()
            if not note and not body:
                continue
            out.append({"page": pno, "kind": a.type[1], "text": body,
                        "note": note, "file": os.path.basename(path)})
    doc.close()
    return out


def content_of(book_dir):
    p = os.path.join(book_dir, "원고", "content.json")
    if not os.path.exists(p):
        p = os.path.join(book_dir, "content.json")
    return json.load(open(p, encoding="utf-8"))


def resolve(content, mark):
    """주석 하나 → {label, sec, from, to, why} 또는 사유가 담긴 미결."""
    text = mark["text"]
    note = mark["note"]
    # 쪽지에 `틀린 것 → 고친 것` 이 통째로 적혀 있으면 덮은 글이 없어도 된다.
    # **화살표가 있을 때만 확실하다** — 그 밖의 쪽지는 고칠 글일 수도 있고
    # "철자 확인 요망" 같은 지시일 수도 있어서, 기계가 갈라서는 안 된다.
    frm = to = None
    sure = False
    if RE_ARROW.search(note):
        left, right = RE_ARROW.split(note, 1)
        frm, to, sure = left.strip(), right.strip(), True
    elif text:
        frm, to = text, note
    if not frm:
        return dict(mark, why="무엇을 고칠지 못 읽었습니다", hits=[], sure=False)

    hits = MK.locate(content, frm)
    if not hits:
        return dict(mark, why="이 글이 어느 지문인지 못 찾았습니다",
                    frm=frm, to=to, hits=[], sure=False)
    labs = sorted({h[0] for h in hits})
    if len(labs) > 1:
        # 지문이 갈리면 사람이 봐야 한다. 같은 지문 안에서 칸만 여럿인 것은
        # 갈린 게 아니다 — 한 지문의 글은 배열·삽입·어법·영작에 되풀이된다.
        return dict(mark, why="여러 지문에 같은 글이 있습니다: %s"
                    % ", ".join(labs), frm=frm, to=to, hits=labs)
    label = labs[0]
    exact = max((h[2] for h in hits), key=len)
    if to is None or to == "":
        return dict(mark, why="고칠 글이 안 적혀 있습니다", frm=exact,
                    to=None, label=label, sec="", hits=labs, sure=False)
    # `sec` 을 비워 두면 그 지문이 실린 **모든 칸**에 얹힌다(같은 글이니까).
    why = "" if sure else ("쪽지가 고칠 글인지 지시인지 알 수 없습니다 "
                           "— 맞으면 --loose")
    return dict(mark, label=label, sec="", frm=exact, to=to, why=why,
                sure=sure)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--book", required=True,
                    help="그 책 폴더(원고/content.json 이 있는 곳)")
    ap.add_argument("--src", default="", help="어느 책에서 온 것인지(기록용)")
    ap.add_argument("--apply", action="store_true",
                    help="바로 고칠 수 있는 것을 정오표에 쌓는다")
    ap.add_argument("--loose", action="store_true",
                    help="쪽지 글을 곧 고칠 글로 본다(화살표가 없어도)")
    ap.add_argument("-o", "--out", default="", help="미결 목록을 쓸 자리")
    a = ap.parse_args()

    content = content_of(a.book)
    src = a.src or os.path.basename(os.path.normpath(a.book))
    ready, pending = [], []
    for p in a.pdfs:
        for m in read_pdf(p):
            r = resolve(content, m)
            ok = r.get("label") and r.get("to") and (r.get("sure") or a.loose)
            (ready if ok else pending).append(r)

    print("■ 주석 %d건 — 바로 고칠 수 있는 것 %d · 사람이 볼 것 %d"
          % (len(ready) + len(pending), len(ready), len(pending)))
    for r in ready:
        print("  ✓ %-18s %s → %s"
              % (r["label"], r["frm"][:34], r["to"][:34]))
    for r in pending:
        print("  · p%-3d %-10s %s\n        %s"
              % (r["page"], r["kind"], (r["note"] or r["text"])[:52], r["why"]))

    if a.apply:
        for r in ready:
            MK.add(r["label"], r["frm"], r["to"], why=r["note"][:60],
                   src=src, sec=r["sec"])
        print("■ 정오표에 %d건 쌓았습니다 — %s"
              % (len(ready), os.path.relpath(MK.PATH, BASE)))
    if a.out:
        json.dump({"ready": ready, "pending": pending},
                  open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("■ 목록 → %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
