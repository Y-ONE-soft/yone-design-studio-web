# -*- coding: utf-8 -*-
"""연구원이 PDF 에 단 **주석을 회수**해 오른쪽 면 창고에 넣는다.

왜 PDF 인가
    주석은 **자리를 갖고 있다**. 어느 면 어느 칸에 찍혔는지가 곧 "몇 강 몇 번
    지문의 동반의어 몇째 카드"다. 원고로 따로 받으면 그 짝짓기를 사람이 다시
    해야 한다.

어떻게 짚나
    면 번호로 세지 않는다(앞 간지·어휘 파트 때문에 어긋난다). 그 면에 찍힌
    **글**을 조판 기록과 맞대 지문을 찾고, 주석 자리에서 가장 가까운 글의
    상자를 찾아 어느 칸인지 정한다.

연구원이 쓰는 법 — 고칠 자리에 메모를 달고 이렇게만 적는다
    동반의어 카드   `evolution / 진화`
                    `evolution / 진화 / development, adaptation / stagnation`
    플로우노트 줄   고쳐 쓴 그 줄 한 줄
    주제            고쳐 쓴 주제 한 줄
    지우기          `삭제`

    (읽고 넘어가기만 할 메모는 앞에 `#` 를 붙인다.)

쓰는 법
    python3 annots.py <검수받은.pdf> <책폴더> [--쓰기]
    `--쓰기` 를 안 주면 **무엇을 바꿀지 보여만 주고** 아무것도 안 건드린다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from core.render_vivlio.series.pocketbook import store as pstore  # noqa: E402

STORE = ("/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_store")
_SKIP = "신규 작업분"          # 우리가 박아 둔 안내 쪽지 — 회수 대상이 아니다


def _rows(book):
    p = os.path.join(book, "build", "_studio_data.json")
    with open(p, encoding="utf-8") as f:
        rows = json.load(f)["passages"]
    return [r for r in rows if r.get("kind") != "memtest"]


def _text(r):
    return "".join(x.get("t", "") for x in (r.get("passage_runs") or []))


def _which(page, rows):
    """이 면이 어느 지문의 오른쪽 면인가 — 카드 표제어와 주제로 맞댄다."""
    txt = page.get_text()
    best, hi = None, 0
    for r in rows:
        marks = [c["w"] for c in (r.get("synonyms") or [])]
        if r.get("topic"):
            marks.append(r["topic"])
        if not marks:
            continue
        n = sum(1 for m in marks if m and m in txt)
        if n > hi:
            best, hi = r, n
    # 표제어가 절반 넘게 맞아야 그 지문이라고 본다
    return best if best and hi >= max(2, len(best.get("synonyms") or []) // 2) \
        else None


def _slots(page, r):
    """이 면에서 고칠 수 있는 칸들의 자리 → [(종류, 몇째, 상자)]."""
    out = []
    for j, c in enumerate(r.get("synonyms") or []):
        for b in page.search_for(c["w"]):
            out.append(("synonyms", j, b))
            break
    for j, ln in enumerate(r.get("flownote") or []):
        s = re.sub(r"^[\[\]→\s]+", "", ln)[:12]
        if len(s) < 4:
            continue
        for b in page.search_for(s):
            out.append(("flownote", j, b))
            break
    if r.get("topic"):
        for b in page.search_for(r["topic"][:16]):
            out.append(("topic", 0, b))
            break
    return out


def _near(slots, pt):
    """주석 자리에서 가장 가까운 칸. 세로를 더 무겁게 본다(칸이 가로로 넓다)."""
    if not slots:
        return None
    def d(b):
        dx = max(b.x0 - pt.x, 0, pt.x - b.x1)
        dy = max(b.y0 - pt.y, 0, pt.y - b.y1)
        return dy * 3 + dx
    kind, j, b = min(slots, key=lambda s: d(s[2]))
    return (kind, j) if d(b) < 90 else None


def _card(txt):
    """`표제어 / 뜻 / 유의어, 유의어 / 반의어` → 카드 한 장."""
    p = [x.strip() for x in txt.split("/")]
    if len(p) < 2 or not p[0] or not p[1]:
        return None
    def lst(i):
        return [w.strip() for w in re.split(r"[,·]", p[i]) if w.strip()] \
            if len(p) > i else []
    return {"w": p[0], "ko": p[1], "syn": lst(2), "ant": lst(3)}


def read(pdf, book, log=print):
    import fitz
    rows, doc = _rows(book), None
    doc = fitz.open(pdf)
    plan, bad = {}, []
    for page in doc:
        annots = [a for a in page.annots() or []
                  if _SKIP not in (a.info.get("content") or "")]
        if not annots:
            continue
        r = _which(page, rows)
        if r is None:
            bad.append((page.number + 1, "어느 지문인지 못 찾음", ""))
            continue
        slots = _slots(page, r)
        for a in annots:
            note = (a.info.get("content") or "").strip()
            if not note or note.startswith("#"):
                continue
            hit = _near(slots, a.rect.tl)
            if hit is None:
                bad.append((page.number + 1, "어느 칸인지 못 찾음", note[:40]))
                continue
            plan.setdefault(id(r), (r, []))[1].append((hit, note,
                                                       a.info.get("title")))
    doc.close()
    return [v for v in plan.values()], bad


def apply(hits, write=False, log=print):
    done = skipped = 0
    for r, edits in hits:
        f = {k: (json.loads(json.dumps(r[k])) if isinstance(r.get(k), list)
                 else r.get(k)) for k in pstore.FIELDS if r.get(k)}
        fixed, lab = set(), r.get("label") or r.get("key") or "?"
        who = ""
        for (kind, j), note, title in edits:
            who = who or (title or "")
            if kind == "synonyms":
                cur = f.get("synonyms") or []
                if note == "삭제":
                    if j < len(cur):
                        log("  %s 동반의어 %d번 «%s» 지움"
                            % (lab, j + 1, cur[j]["w"]))
                        del cur[j]
                    else:
                        skipped += 1
                        continue
                else:
                    c = _card(note)
                    if not c or j >= len(cur):
                        log("  ⚠ %s 동반의어 %d번 — 못 읽음: %s"
                            % (lab, j + 1, note[:50]))
                        skipped += 1
                        continue
                    log("  %s 동반의어 %d번 «%s» → «%s / %s»"
                        % (lab, j + 1, cur[j]["w"], c["w"], c["ko"]))
                    cur[j] = c
                f["synonyms"] = cur
            elif kind == "flownote":
                cur = f.get("flownote") or []
                if j >= len(cur):
                    skipped += 1
                    continue
                if note == "삭제":
                    log("  %s 플로우노트 %d줄 지움" % (lab, j + 1))
                    del cur[j]
                else:
                    log("  %s 플로우노트 %d줄 → %s" % (lab, j + 1, note[:40]))
                    cur[j] = note
                f["flownote"] = cur
            else:
                log("  %s 주제 → %s" % (lab, note[:40]))
                f["topic"] = note
            fixed.add(kind)
            done += 1
        if fixed and write:
            pstore.put(STORE, _text(r), f, label=lab, fixed=fixed, who=who)
    return done, skipped


def main(argv):
    if len(argv) < 3:
        return print(__doc__)
    pdf, book = argv[1], argv[2]
    write = "--쓰기" in argv or "--write" in argv
    hits, bad = read(pdf, book)
    n = sum(len(e) for _, e in hits)
    print("■ 주석 %d개 · 지문 %d개" % (n, len(hits)))
    done, skipped = apply(hits, write)
    for pg, why, what in bad:
        print("  ⚠ %d면 %s %s" % (pg, why, what))
    print("■ %s %d곳%s%s"
          % ("창고에 반영" if write else "반영할 것(미리보기)", done,
             " · 못 읽음 %d" % skipped if skipped else "",
             " · 자리 못 찾음 %d" % len(bad) if bad else ""))
    if not write:
        print("   실제로 넣으려면 뒤에 --쓰기 를 붙이세요.")


if __name__ == "__main__":
    main(sys.argv)
