"""UNIT형 단어장 원고(xlsx) → data.json.

원고 = 시트 하나가 Unit 하나. 한 표제어는 **빈 행으로 끊기는 블록**이고, 블록 안의
행 역할은 열 위치가 아니라 **구조**로 읽는다(형식 화이트리스트 금지):

    B      C            D
    DAYnn  회독                     ← 블록 시작 마커 (문구는 무엇이든, 두 칸이 차 있고
                                        아래에 번호 행이 온다는 구조가 앵커)
    1      sensible     [형] 분별력…  ← 번호 · 표제어 · 뜻
           [ˈsɛnsəbəl]                ← 발음기호 (대괄호로 열고 닫는 한 줄)
           sensitivity [명] …  It was… ← 파생어(C) · 예문 첫 줄(D)
                              너무 늦은…  ← 예문 해석
                              This work…  ← 예문(영/한 번갈아)

인식 게이트: `options.expect` 의 기대 수량(unit 수·unit 당 표제어 수)과 어긋나면
**조판하지 않고 중단한다**(침묵 유실 금지).

파생어 셀은 여러 파생어가 한 칸에 이어 붙어 온다 —
`sensitivity [명] … sensibility [명] …`. `영단어 + [품사]` 를 경계로 잘라 줄을
나눈다(품사 대괄호가 앵커라 파생어 개수·순서에 의존하지 않는다).
"""
import json
import os
import re

# 발음기호 — 대괄호로 열고 닫히고 한글이 없는 한 줄
_RE_PRON = re.compile(r"^\[[^\]]*\]$")
# 품사 대괄호 — 뜻·파생어의 구조 앵커
_POS = "명동형부전접대감조"
_RE_POS = re.compile(rf"\[([{_POS}])\]")
# 파생어 경계 — 영단어(구) 다음에 바로 품사 대괄호가 오면 새 파생어가 시작된 것
_RE_DERIV_SPLIT = re.compile(rf"(?<=\S)\s+(?=[A-Za-z][A-Za-z'’\- ]*\[[{_POS}]\])")


def _rows(ws):
    """시트 → [(B, C, D)] 문자열 3튜플."""
    out = []
    for row in ws.iter_rows(values_only=True):
        vals = [("" if v is None else str(v).replace(" ", " ").strip())
                for v in row]
        while len(vals) < 4:
            vals.append("")
        out.append((vals[1], vals[2], vals[3]))
    return out


def split_deriv(cell):
    """파생어 셀 → 파생어 줄 목록."""
    cell = (cell or "").strip()
    if not cell:
        return []
    return [s.strip() for s in _RE_DERIV_SPLIT.split(cell) if s.strip()]


def parse_unit(rows, unit_label):
    """한 시트 → 표제어 블록 목록.

    블록 경계 = '번호 행'(B 열이 숫자). 마커 행("DAYnn / 회독")은 무시해도
    구조가 잡히므로 문구에 기대지 않는다.
    """
    blocks, cur = [], None
    for b, c, d in rows:
        if b.isdigit():                                   # ① 번호 · 표제어 · 뜻
            cur = {"no": int(b), "unit": unit_label, "word": c, "meaning": d,
                   "pron": "", "deriv": [], "ex": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        if c and _RE_PRON.match(c) and not cur["pron"]:    # ② 발음기호
            cur["pron"] = c
            if d:
                cur["ex"].append(d)
            continue
        if c and _RE_POS.search(c):                        # ③ 파생어
            cur["deriv"] += split_deriv(c)
            if d:
                cur["ex"].append(d)
            continue
        if d:                                              # ④ 예문 / 해석
            cur["ex"].append(d)
    for blk in blocks:
        # 예문은 영/한 짝 — 홀수로 끝나면 해석이 빈 짝으로 남는다(원고 그대로)
        lines = blk.pop("ex")
        blk["pairs"] = [[lines[i], lines[i + 1] if i + 1 < len(lines) else ""]
                        for i in range(0, len(lines), 2)]
    return blocks


def build(cfg, log=print):
    import openpyxl

    o = cfg.section("options") or {}
    path = cfg.manuscript("words")
    wb = openpyxl.load_workbook(path, data_only=True)

    units, total = [], 0
    for ws in wb:
        blocks = parse_unit(_rows(ws), ws.title)
        if not blocks:
            continue
        units.append({"sheet": ws.title,
                      "label": unit_label(ws.title, o),
                      "num": unit_num(ws.title),
                      "words": blocks})
        total += len(blocks)

    d = {"units": units, "counts": {"units": len(units), "words": total}}
    gate(d, o, log)

    out = os.path.join(cfg.root, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    log(f"[원고] Unit {len(units)}개 · 표제어 {total}개 → {os.path.basename(out)}")
    return out


_RE_NUM = re.compile(r"(\d+)")


def unit_num(sheet):
    m = _RE_NUM.search(sheet or "")
    return int(m.group(1)) if m else 0


def unit_label(sheet, o):
    """머리말·탭에 찍히는 이름 — 기본 `UNIT 15`. config 로 접두어를 바꾼다."""
    return f"{o.get('unit_word', 'UNIT')} {unit_num(sheet):02d}"


def gate(d, o, log):
    """인식 게이트 — 기대와 어긋나면 조판하지 않는다."""
    exp = o.get("expect") or {}
    bad = []
    if exp.get("units") and d["counts"]["units"] != exp["units"]:
        bad.append(f"Unit {d['counts']['units']}개 (기대 {exp['units']})")
    if exp.get("words") and d["counts"]["words"] != exp["words"]:
        bad.append(f"표제어 {d['counts']['words']}개 (기대 {exp['words']})")
    per = exp.get("words_per_unit")
    if per:
        off = [u["sheet"] for u in d["units"] if len(u["words"]) != per]
        if off:
            bad.append(f"표제어 수가 {per}개가 아닌 Unit: {', '.join(off)}")
    # 구조 결손 — 조용히 비면 조판 사고다
    for u in d["units"]:
        for w in u["words"]:
            where = f"{u['sheet']} {w['no']:02d} {w['word']}"
            if not w["word"] or not w["meaning"]:
                bad.append(f"표제어/뜻 없음: {where}")
            elif not w["pron"]:
                bad.append(f"발음기호 없음: {where}")
            elif not w["pairs"]:
                bad.append(f"예문 없음: {where}")
    if bad:
        for b in bad[:20]:
            log(f"  - {b}")
        raise SystemExit(f"[인식 게이트] 원고 인식 결함 {len(bad)}건 — 조판 중단")


def load(cfg):
    with open(os.path.join(cfg.root, "data.json"), encoding="utf-8") as f:
        return json.load(f)
