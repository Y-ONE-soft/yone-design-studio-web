"""이의고2 단어장 원고 → data.json.

입력(책 config 의 `manuscript.files.words`): xlsx 단일 시트 '단어장 원고'.
열 순서(원고 그대로) — 번호/구간/표제어/품사/뜻/예문/해석/연관어휘 · 유반의어/
파생어/주의 · 혼동/영영풀이.

`vocabook`(상일보카)과 달리 Day 가 없다. '구간' 열이 곧 그룹핑 단서다:
  "교과서 - 본문 3"                         → part=text, group="본문 3"
  "부교재 - 8강 Exercise 03 [순서 추론]"      → part=supp, group="8강 Exercise 03 [순서 추론]"
  "2026년 9월 고2 모의고사 - 21번 [함축적 의미]" → part=mock, group="21번 [함축적 의미]"

인식은 접두어 구조로만 판정한다(리터럴 전체 문자열에 기대지 않음) — '부교재'
쪽 수능특강 강·회차가 바뀌어도, 모의고사 회차가 바뀌어도 그대로 통한다.

**인식 게이트**: 기대 수량과 어긋나면 조판하지 않고 중단한다(침묵 유실 금지).
기대값은 책 config 의 `options.expect`.
"""
import json
import os
import re

import openpyxl

_RE_NOTE_LABEL = re.compile(r"^(주의|혼동)\.\s*")

SHEET = "단어장 원고"
PART_TITLE = {"text": "교과서", "supp": "부교재", "mock": "모의고사"}
PART_ORDER = ("text", "supp", "mock")


def _t(v):
    return "" if v is None else str(v).strip()


def _lines(v):
    return [ln.strip() for ln in _t(v).split("\n") if ln.strip()]


def classify(raw):
    """'구간' 열 한 칸 → (part, group). 구조 판정 — 접두어만 본다."""
    raw = _t(raw)
    head, _, sub = raw.partition(" - ")
    head, sub = head.strip(), sub.strip()
    if head.startswith("교과서"):
        return "text", sub or head
    if head.startswith("부교재"):
        return "supp", sub or head
    if "모의고사" in head:
        return "mock", sub or head
    return "etc", raw


def parse(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET]
    items = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not _t(r[0]):
            continue
        (no, raw_sec, word, pos, mean, ex_en, ex_kr,
         syn, deriv, note, defn) = (list(r) + [None] * 11)[:11]
        part, group = classify(raw_sec)
        rows = []
        if _t(ex_en):
            rows.append({"label": "예문", "lines": [_t(ex_en), _t(ex_kr)]})
        if _t(syn):
            rows.append({"label": "유반의어", "lines": _lines(syn)})
        if _t(deriv) and _t(deriv) != "없음":
            rows.append({"label": "파생어", "lines": _lines(deriv)})
        if _t(note):
            note_lines = _lines(note)
            # 원고 줄 자체가 '주의.'/'혼동.' 로 시작 — 그 접두어를 행 라벨로
            # 쓰고(둘을 구분해 보이게) 줄 안에서는 중복이라 지운다.
            lab = "혼동" if note_lines and note_lines[0].startswith("혼동") else "주의"
            note_lines = [_RE_NOTE_LABEL.sub("", ln) for ln in note_lines]
            rows.append({"label": lab, "lines": note_lines})
        if _t(defn):
            rows.append({"label": "영영풀이", "lines": [_t(defn)]})
        items.append({
            "no": int(no) if isinstance(no, (int, float)) else len(items) + 1,
            "part": part, "group": group,
            "word": _t(word), "pos": _t(pos), "meaning": _t(mean),
            "rows": rows,
        })
    return items


def gate(items, expect):
    errs = []
    n = len(items)
    if expect.get("words") is not None and n != expect["words"]:
        errs.append(f"낱말 {n} (기대 {expect['words']})")
    counts = {}
    for it in items:
        counts[it["part"]] = counts.get(it["part"], 0) + 1
    if counts.get("etc"):
        errs.append(f"구간 미분류 {counts['etc']}건 — data.py classify() 확인")
    for k, want in (expect.get("parts") or {}).items():
        got = counts.get(k, 0)
        if got != want:
            errs.append(f"{PART_TITLE.get(k, k)} {got} (기대 {want})")
    if errs:
        raise SystemExit("[오류] 원고 인식 불일치:\n  - " + "\n  - ".join(errs))
    return counts


def build(cfg, log=print):
    opts = cfg.section("options") or {}
    items = parse(cfg.manuscript("words"))
    counts = gate(items, opts.get("expect") or {})

    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False)
    summary = " · ".join(f"{PART_TITLE.get(k, k)} {counts.get(k, 0)}"
                         for k in PART_ORDER if counts.get(k))
    log(f"OK  낱말 {len(items)} · {summary} → {os.path.basename(out)}")
    return out


def load(cfg, log=None):
    """data.json + 정오표(errata.json) — 읽는 자리에서 얹는다."""
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
