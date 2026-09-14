# -*- coding: utf-8 -*-
"""교과서 중요어휘·요약 — 구글시트 「직전보충 VOL2 원고정리 교과서」.

교과서도 중요어휘 면(빈칸 지문 + `>>내용요약`)을 싣기로 했다(2026-09-14).
정본은 아래 시트다. 탭이 과목(`공통영어2`·`영어Ⅱ`)이고, 한 줄에
`출판사 | 1과 본문1 | 1과 본문2 …`, 바로 아랫줄에 그 칸의 글이 있다.

## 칸 이름으로 짝짓지 않는다 — **글로 짝짓는다**

시트의 `본문N` 은 교과서 쪽 번호이고, 원고(=책의 다른 섹션)의 `본문N` 과
**다를 수 있다**. 실측(YBM(박) 2과): 원고는 `본문3-1 · 3-2` 로 나눴는데 시트는
`본문3 · 본문4` 로 적었고, 원고의 `본문5 · 본문6` 은 시트의 `본문6` 한 칸에
같이 들어 있다. 이름으로 붙이면 본문4 자리에 본문3-2 의 어휘가 실린다.

그래서 **원고 지문의 낱말이 시트 칸에 얼마나 들어 있는지**로 짝을 정한다
(같은 출판사 안에서만). 한 칸이 원고 두 지문을 품으면 머리를 `본문5~6`
으로 적고 말한다 — 시트를 나누는 게 맞지만 조용히 한쪽을 버리지는 않는다.

## 읽는 길

1. 시트를 곧장 받는다(링크 공개일 때만 된다 — 중요어휘 고1·고2 시트처럼).
2. 안 되면 `data/final_textbook_vocab.json` 사본을 쓴다. 사본은
   `scripts/final_textbook_vocab_snapshot.py <받은 xlsx>` 로 새로 뜬다.
   사본을 쓸 때는 **쓴다고 말한다** — 시트가 고쳐졌는데 옛 글이 실릴 수 있다.
"""
import io
import json
import os
import re
import unicodedata
import urllib.request

SHEET_ID = "1PB5B7dm80VH1pkZ-fVDhI9lJcpgcP5XxKFC5uD0oqm0"
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT = os.path.join(BASE, "data", "final_textbook_vocab.json")

MATCH_MIN = 0.6          # 원고 낱말의 60% 이상이 그 칸에 있어야 짝이다
RE_WORD = re.compile(r"[a-z]{4,}")
RE_HEAD = re.compile(r"\d+\s*과|SL|Special|Further|Read\s*More", re.I)


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _sq(s):
    s = nfc(s).replace("Ⅱ", "II").replace("Ⅰ", "I")
    return re.sub(r"[\s()（）]", "", s)


# ── 시트 읽기 ───────────────────────────────────────────────────────────
def rows_from_xlsx(data):
    """xlsx 바이트 → [{subject, pub, head, text}]."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        for i, r in enumerate(rows):
            if not r or not isinstance(r[0], str) or not r[0].strip():
                continue
            heads = [(j, h) for j, h in enumerate(r[1:], 1)
                     if isinstance(h, str) and RE_HEAD.search(h)]
            if not heads or i + 1 >= len(rows):
                continue
            body = rows[i + 1]
            for j, h in heads:
                t = body[j] if j < len(body) else None
                if isinstance(t, str) and t.strip():
                    out.append({"subject": nfc(ws.title), "pub": nfc(r[0].strip()),
                                "head": nfc(h.strip()), "text": nfc(t)})
    return out


def load(log=lambda m: None):
    url = ("https://docs.google.com/spreadsheets/d/%s/export?format=xlsx"
           % SHEET_ID)
    try:
        data = urllib.request.urlopen(url, timeout=20).read()
        if data[:2] == b"PK":
            rows = rows_from_xlsx(data)
            if rows:
                return rows
    except Exception:                                          # noqa: BLE001
        pass
    if os.path.exists(SNAPSHOT):
        d = json.load(open(SNAPSHOT, encoding="utf-8"))
        log("[교과서 어휘] ⚠ 시트에 곧장 닿지 못해 사본(%s, %s)을 씁니다 — "
            "시트를 고쳤다면 사본을 새로 떠야 합니다"
            % (os.path.relpath(SNAPSHOT, BASE), d.get("taken", "?")))
        return d.get("rows", [])
    log("[교과서 어휘] ★ 시트도 사본도 없습니다 — 교과서 중요어휘가 빠집니다")
    return []


# ── 글 다듬기 ───────────────────────────────────────────────────────────
def _is_summary(line):
    t = line.strip()
    return "내용요약" in t and len(t) <= 24


def block_text(header, text):
    """시트 칸 → 렌더러가 읽는 한 블록(머리 · 지문 줄들 · 빈 줄 · 요약).

    렌더러는 **빈 줄로 묶음을 가른다** — 지문 안에 빈 줄이 있으면 다음 문단이
    새 지문 머리로 읽힌다. 그래서 요약 표제 앞에만 빈 줄을 둔다.
    """
    body, summ, in_sum = [], [], False
    for ln in nfc(text).replace("\r", "").split("\n"):
        if _is_summary(ln):
            in_sum = True
            continue
        if ln.strip():
            (summ if in_sum else body).append(ln.strip())
    out = [header] + body
    if summ:
        out += ["", ">>내용요약"] + summ
    return "\n".join(out)


def _words(s):
    return set(RE_WORD.findall(nfc(s).lower()))


# ── 원고 지문과 짝짓기 ──────────────────────────────────────────────────
def passages(scope, base, grade, log=lambda m: None):
    """범위 안 교과서 지문 → [(라벨, 원고 글, spec)] (차례대로)."""
    from engines.final import manuscript as M, manuscript_locate as L
    from engines.final import scope_source as S
    out = []
    for d, spec in S.folders(scope, base, grade=grade, log=lambda m: None):
        if spec.get("kind") not in ("lesson", "sl") or spec.get("deeplearning"):
            continue
        for b in M.read(d, "arrange")[0]:
            lab = L.to_final_label(spec, b["raw"])
            if not lab or not S.in_scope(lab, scope):
                continue
            txt = " ".join(list(b.get("items") or []) + [b.get("passage") or ""])
            out.append((lab, txt, spec))
    return out


def vocab_text(scope, base, grade, log=lambda m: None, rows=None):
    """범위 안 교과서 지문의 중요어휘 글(블록을 빈 줄로 이은 것). 없으면 ""."""
    from engines.final import scope_source as S
    if not any(t[0] in ("lesson", "sl") for t in scope.get("tokens", [])):
        return ""
    ps = passages(scope, base, grade, log)
    if not ps:
        return ""
    rows = load(log) if rows is None else rows
    if not rows:
        return ""

    # 지문 → 가장 많이 겹치는 칸 (같은 과목·출판사 안에서)
    by_cell, missing = {}, []
    for lab, txt, spec in ps:
        cand = [r for r in rows
                if _sq(r["pub"]) == _sq(spec.get("publisher"))
                and (not spec.get("subject")
                     or _sq(r["subject"]) == _sq(spec["subject"]))]
        w = _words(txt)
        best, score = None, 0.0
        for i, r in enumerate(cand):
            sc = len(w & _words(r["text"])) / max(1, len(w))
            if sc > score:
                best, score = r, sc
        if best is None or score < MATCH_MIN:
            missing.append(lab)
            continue
        key = (best["subject"], best["pub"], best["head"])
        by_cell.setdefault(key, {"row": best, "labels": []})["labels"].append(lab)

    blocks = []
    for key, v in by_cell.items():
        labs = sorted(v["labels"], key=S.label_order)
        head = labs[0]
        if len(labs) > 1:
            # `교과서2과 본문5` + `본문6` → `교과서2과 본문5~6`
            tail = labs[-1].rsplit("본문", 1)[-1]
            head = labs[0] + "~" + tail if "본문" in labs[-1] else labs[0]
            log("[교과서 어휘] ⚠ 시트 한 칸(%s %s)에 원고 지문 %d개(%s)가 함께 있어 "
                "`%s` 한 면으로 싣습니다 — 시트를 나누면 따로 실립니다"
                % (key[1], key[2], len(labs), ", ".join(labs), head))
        if key[2].split()[-1] not in head:
            log("  [교과서 어휘] 시트 `%s %s` → 원고 `%s` (칸 이름과 원고 번호가 다름 — 글로 짝지음)"
                % (key[1], key[2], head))
        blocks.append((labs[0], block_text(head, v["row"]["text"])))
    for lab in missing:
        log("[교과서 어휘] ★ %s — 시트에서 이 지문의 글을 찾지 못했습니다" % lab)
    blocks.sort(key=lambda x: S.label_order(x[0]))
    if blocks:
        log("■ 교과서 중요어휘 %d지문 (원고 %d지문)" % (len(blocks), len(ps)))
    return "\n\n".join(b for _l, b in blocks)
