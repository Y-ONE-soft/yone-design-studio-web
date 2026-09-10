#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이널 직전보충 — **조판 뒤 검수 한 벌**.

    python3 scripts/final_viv_review.py <책폴더> [--agent]

책폴더는 `…/파이널 직전보충/고1/26-2-중간/광문1` 처럼 `원고/`·`Vol1/`·`Vol2/`
가 있는 자리다. 시험범위는 **그 책이 조판될 때 쓴 것**(`원고/scope.json`)을
읽는다 — 구글시트가 아니다(`scope_source.resolve`). 조판과 검수가 서로 다른
범위를 보면 "책은 맞는데 검수가 틀렸다" 가 나기 때문이다.

세 겹으로 본다:

  ① 범위 ↔ 원고   범위가 짚은 지문이 원고에 있는가 (없으면 책에도 없다)
  ② 원고 ↔ PDF    읽어 낸 글이 책에 **다 실렸는가** (게이트가 못 보는 구멍)
  ③ 눈             `core.review_agent` — 표본 쪽을 실제로 보고 조판 결함 찾기

①②는 틀리면 **멈춘다**(붙일 수 없는 책이다). ③은 조언이라 판정을 바꾸지
않는다. 결과는 `<책폴더>/review.json`.
"""
import argparse
import json
import os
import re
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from engines.final import (manuscript as M, manuscript_locate as L,      # noqa
                           marks as MK, scope_source as S)

norm = lambda s: re.sub(r"[^a-z가-힣]", "", (s or "").lower())     # noqa: E731
# 지면에 찍히는 지문 이름 — 원고 대조가 지문 단위로 갈리게 해 준다
RE_LAB = re.compile(r"^(?:\d{6}(?:~\d{2})?|올포 \d+강 \S+|리딩파워 \d+강 \S+|"
                    r"교과서\S+ \S+|\d+강 \S+|[Tt]est\d+ \S+|외부지문 \S+)$")


# ── 책 폴더 읽기 ────────────────────────────────────────────────────────
def book_parts(book_dir):
    content = json.load(open(os.path.join(book_dir, "원고", "content.json"),
                             encoding="utf-8"))
    pdfs = []
    for vol in (1, 2):
        d = os.path.join(book_dir, "Vol%d" % vol)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".pdf") and "내지" in f and "인쇄" not in f:
                pdfs.append(os.path.join(d, f))
    return content, pdfs


def pdf_text(paths):
    out, labs = "", []
    for p in paths:
        d = fitz.open(p)
        for pg in d:
            t = pg.get_text()
            out += t
            for line in t.split("\n"):
                x = line.strip()
                if RE_LAB.match(x) and x not in labs:
                    labs.append(x)
        d.close()
    return norm(out), labs


# ── ① 범위 ↔ 원고 ───────────────────────────────────────────────────────
def check_scope(scope, grade, log):
    """범위가 짚은 지문 번호 중 **원고에 없는 것**. 있으면 책에서 빠진다."""
    cfg = json.load(open(os.path.join(BASE, "engines/final/config.json"),
                         encoding="utf-8"))
    base = os.path.expanduser(cfg["gdrive_content_base"])
    bad = []
    for d, spec in S.folders(scope, base, grade=grade, log=log):
        labs = [x for x in (L.to_final_label(spec, b["raw"])
                            for b in M.read(d, "arrange")[0]) if x]
        if not labs:
            bad.append({"where": os.path.basename(d), "why": "원고를 한 줄도 못 읽음"})
            continue
        tok = S._key(_tok_of(spec))
        for t in scope["tokens"]:
            if S._key(t) != tok:
                continue
            only = (scope.get("detail", {}).get(t) or {}).get("only") or []
            got = set()
            for lab in labs:
                tk, tail = S.label_token(lab)
                if tk is None or S._key(tk) != tok:
                    continue
                if t[0] == "mock":
                    # 장문은 라벨이 `240941~42` — **묶음 전체**가 실린 것이다.
                    # 앞 번호만 세면 42 가 없어진 것처럼 보인다.
                    ns = [int(x) for x in re.findall(r"\d+", lab[4:])]
                    got |= (set(range(ns[0], ns[-1] + 1)) if ns else set())
                    continue
                m = S.RE_LAB_NO.search(tail)
                if m:
                    got.add(int(m.group(1)))
            miss = [n for n in only if n not in got]
            if miss:
                bad.append({"where": S.token_text(t), "why": "원고에 없음",
                            "nums": miss})
    return bad


def _tok_of(spec):
    k = spec["kind"]
    if k == "sl":
        return ("sl", 0)
    if k == "lesson":
        return ("lesson", spec["lesson"])
    if k == "mock":
        return ("mock", spec["year"], spec["month"])
    return (k, spec.get("unit"))


# ── ② 원고 ↔ PDF ────────────────────────────────────────────────────────
def check_manuscript(content, txt, log):
    """content 의 글이 PDF 에 **다 실렸는가**. 지문 단위로 어디가 빠졌는지 말한다."""
    miss, tot = [], {"문장배열": 0, "문장삽입": 0, "서술형영작": 0, "어법수정": 0}
    for b in content["vol1"].get("문장배열", []):
        for it in b.get("items", []):
            if len(it) < 25:
                continue
            tot["문장배열"] += 1
            if norm(it)[:40] not in txt:
                miss.append(("문장배열", b["header"], it[:40]))
    for b in content["vol1"].get("문장삽입", []):
        # 하단 문제는 `paras`(발문·주어진 문장·본문) 로 들어 있다 — 그중
        # **주어진 문장**만 본다. 발문은 어느 지문에나 같아 대조가 안 된다.
        for pa in b.get("paras", []):
            t0 = (pa.get("text") or "") if isinstance(pa, dict) else str(pa)
            if len(t0) < 25 or "고르시오" in t0 or "쓰시오" in t0:
                continue
            tot["문장삽입"] += 1
            if norm(t0)[:40] not in txt:
                miss.append(("문장삽입", b["header"], t0[:40]))
    det = content["vol2"].get("영작_헤더_상세", [])
    pairs = content["vol2"].get("서술형영작", [])
    for i, h in enumerate(det):
        e = det[i + 1]["start_idx"] if i + 1 < len(det) else len(pairs)
        for p in pairs[h["start_idx"]:e]:
            k = p.get("korean") or ""
            if len(k) < 25:
                continue
            tot["서술형영작"] += 1
            if norm(k)[:40] not in txt:
                miss.append(("서술형영작", h["header"], k[:40]))
    g = content["vol2"].get("어법수정", [])
    for i in range(0, len(g) - 1, 2):
        body = g[i + 1] if isinstance(g[i + 1], str) else ""
        if len(body) < 25:
            continue
        tot["어법수정"] += 1
        if norm(body)[:40] not in txt:
            miss.append(("어법수정", g[i], body[:40]))
    return tot, miss


# ── ③ 눈 ────────────────────────────────────────────────────────────────
def run_agent(book_dir, pdfs, log):
    """`core.review_agent` — 표본 쪽을 실제로 보고 조판 결함을 찾는다.

    에이전트는 job 폴더 얼개를 기대하므로 책 폴더 안에 `_review/` 를 만들고
    PDF 를 가리키는 최소한의 `result` 를 넘긴다.
    """
    from core.review_agent import run_review_agent
    jd = os.path.join(book_dir, "_review")
    os.makedirs(jd, exist_ok=True)
    out = []
    for p in pdfs:
        r = run_review_agent(jd, log, result={"pdf_path": p, "ok": True})
        if r:
            r["pdf"] = os.path.basename(p)
            out.append(r)
        for f in ("visual_report.json", "review_result.json",
                  "review_input.json"):
            q = os.path.join(jd, f)
            if os.path.exists(q):
                os.replace(q, q[:-5] + "_" + os.path.basename(p)[:-4] + ".json")
    return out


# ── 한 벌 ───────────────────────────────────────────────────────────────
def review(book_dir, agent=False, log=print):
    content, pdfs = book_parts(book_dir)
    school = content.get("school", "")
    grade = content.get("grade", "")
    period = content.get("exam_period", "")
    g = int("".join(c for c in grade if c.isdigit()) or 0)
    log("=== 검수: %s / %s / %s ===" % (school, grade, period))
    if not pdfs:
        log("  ★ 내지 PDF 가 없습니다 — 먼저 조판하세요")
        return {"ok": False, "why": "PDF 없음"}

    scope = S.resolve(school, period, grade=g, book_dir=book_dir, log=log)
    out = {"school": school, "grade": grade, "period": period,
           "pdfs": [os.path.basename(p) for p in pdfs]}

    # ① 범위 ↔ 원고
    out["scope_gaps"] = check_scope(scope, g, log) if scope else []
    if not scope:
        log("  ★ 시험범위를 못 읽었습니다 — 원고↔PDF 대조만 합니다")
    for b in out["scope_gaps"]:
        log("  ★ [범위] %s — %s %s" % (b["where"], b["why"],
                                      b.get("nums") or ""))

    # ② 원고 ↔ PDF
    txt, labs = pdf_text(pdfs)
    tot, miss = check_manuscript(content, txt, log)
    out["counts"] = tot
    out["missing"] = [{"sec": s0, "label": l0, "text": t0}
                      for s0, l0, t0 in miss]
    log("■ 원고 → PDF   " + " · ".join(
        "%s %d/%d" % (k, tot[k] - len([1 for s0, _l, _t in miss if s0 == k]),
                      tot[k]) for k in tot))
    for s0, l0, t0 in miss[:20]:
        log("  ★ [%s] %s — 책에 없음: %s" % (s0, l0, t0))

    # 정오표가 얹혔는지 (원고를 다시 뽑아도 살아남아야 한다)
    out["marks"] = content.get("_marks") or {}
    if out["marks"].get("miss"):
        log("  ⚠ 정오표 %d건이 원문을 못 찾았습니다 — 원고가 바뀌었는지 볼 것"
            % len(out["marks"]["miss"]))

    out["labels"] = labs
    out["ok"] = not out["scope_gaps"] and not miss

    # ③ 눈 (조언 — 판정을 바꾸지 않는다)
    if agent:
        try:
            out["agent"] = run_agent(book_dir, pdfs, log)
        except Exception as e:                                 # noqa: BLE001
            log("  ⚠ 검수 에이전트가 돌지 못했습니다: %s" % e)
            out["agent_error"] = str(e)

    p = os.path.join(book_dir, "review.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("■ %s — %s" % ("통과" if out["ok"] else "★ 걸림", p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--agent", action="store_true",
                    help="눈으로 보는 검수 에이전트까지 돌린다(느리고 돈이 든다)")
    a = ap.parse_args()
    r = review(os.path.abspath(a.book), agent=a.agent)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
