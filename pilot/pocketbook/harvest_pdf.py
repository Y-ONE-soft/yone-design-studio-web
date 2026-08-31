# -*- coding: utf-8 -*-
"""완성 포켓북 PDF → 지문 JSON (하베스트 파일럿).

포켓북의 값비싼 내용(구문분석 주석·플로우노트·동반의어)은 지금 **완성 .indd
안에만** 있다. 그래서 새 학기마다 '완성본에서 가져오기'를 해야 했다. 그 내용을
한 번 구조로 뽑아 두면 가져오기 자체가 사라진다.

이 파일럿은 그 추출이 **InDesign 없이 PDF 만으로 가능한지**를 확인한다.
발견한 규칙(상일2 26-2 포켓북 실측, 9pt 본문 기준):

    본문 글자        NotoSansCJKkr-Regular 8.9~9.0pt, 줄 간격 24pt
    위 주석          baseline − 9.4pt, 7pt
    아래 주석        baseline + 8.6pt, 7pt
    형광펜           굵기 9pt 스트로크(=InDesign 밑줄), 중심 baseline − 3pt
    밑줄             굵기 0.4pt 스트로크, baseline + 2pt 근처
    강조색           파랑 #224E8E · 빨강 #D2232A · 본문 #231F20

주석은 앵커된 텍스트 프레임이라 PDF 에서는 별도 줄로 떨어져 나온다. x 범위가
가장 많이 겹치는 본문 낱말에 도로 붙인다(인디자인이 낱말 중앙에 앵커한다).
"""
import json
import os
import sys

import fitz

MM = 25.4 / 72.0

BODY_SIZE = (8.4, 9.6)
ANNO_SIZE = (6.5, 7.4)
LINE_PITCH = 24.0
ABOVE_DY = -9.4
BELOW_DY = 8.6
TOL = 2.5

COLORS = {0x231F20: "", 0x224E8E: "blue", 0xD2232A: "red",
          0x58595B: "", 0xA7A9AC: "anno"}


def _hex(c):
    return "#%06X" % c


def _chars(page, clip=None):
    out = []
    raw = page.get_text("rawdict", clip=clip)
    for b in raw["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                for ch in s["chars"]:
                    out.append({
                        "c": ch["c"], "x0": ch["bbox"][0], "x1": ch["bbox"][2],
                        "y": round(ch["origin"][1], 1), "size": s["size"],
                        "color": s["color"], "font": s["font"].split("+")[-1],
                    })
    return out


def _strokes(page):
    """굵은 스트로크(형광펜)·얇은 스트로크(밑줄) 목록."""
    hl, ul = [], []
    for dr in page.get_drawings():
        if dr["type"] != "s":
            continue
        w = dr.get("width") or 0
        for item in dr["items"]:
            if item[0] != "l":
                continue
            p0, p1 = item[1], item[2]
            if abs(p0.y - p1.y) > 0.6:
                continue
            seg = {"x0": min(p0.x, p1.x), "x1": max(p0.x, p1.x),
                   "y": (p0.y + p1.y) / 2.0, "color": dr.get("color"),
                   "w": w}
            (hl if w > 4 else ul).append(seg)
    return hl, ul


def _rgb_hex(c):
    if not c:
        return None
    return "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in c)


def _group_lines(chars, lo, hi):
    lines = {}
    for ch in chars:
        if not (lo <= ch["size"] <= hi):
            continue
        lines.setdefault(ch["y"], []).append(ch)
    for y in lines:
        lines[y].sort(key=lambda c: c["x0"])
    return dict(sorted(lines.items()))


def _words(line_chars):
    """한 줄의 글자 → 낱말. 공백 문자 또는 큰 간격에서 끊는다."""
    words, cur = [], None
    prev_x1 = None
    for ch in line_chars:
        is_space = ch["c"].isspace()
        gap = (ch["x0"] - prev_x1) if prev_x1 is not None else 0
        if is_space or (cur and gap > 1.2):
            if cur:
                words.append(cur)
                cur = None
            if is_space:
                prev_x1 = ch["x1"]
                continue
        if cur is None:
            cur = {"t": "", "x0": ch["x0"], "x1": ch["x1"], "cols": []}
        cur["t"] += ch["c"]
        cur["x1"] = ch["x1"]
        cur["cols"].append(ch["color"])
        prev_x1 = ch["x1"]
    if cur:
        words.append(cur)
    for w in words:
        maj = max(set(w["cols"]), key=w["cols"].count)
        w["color"] = COLORS.get(maj, _hex(maj))
        del w["cols"]
    return words


def _anno_spans(page):
    """주석 런 = **PDF span 하나**.

    ⚠ 글자 간격으로 끊으면 안 된다. `S` 와 `V` 처럼 서로 다른 앵커 프레임의
      글자가 0.3pt 만 떨어져 붙어 있는 경우가 흔하다(실측). 그런데 PyMuPDF 는
      프레임마다 span 을 따로 준다 — 그 경계를 그대로 쓴다. 한 프레임 안에서
      색이 바뀌어 span 이 쪼개진 경우만(간격 ~0) 도로 붙인다.
    """
    runs = []
    raw = page.get_text("rawdict")
    for b in raw["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for sp in l["spans"]:
                if not (ANNO_SIZE[0] <= sp["size"] <= ANNO_SIZE[1]):
                    continue
                t = "".join(c["c"] for c in sp["chars"]).strip()
                if not t:
                    continue
                runs.append({"y": round(sp["chars"][0]["origin"][1], 1),
                             "x0": sp["bbox"][0], "x1": sp["bbox"][2],
                             "t": t, "color": sp["color"]})
    runs.sort(key=lambda r: (r["y"], r["x0"]))
    merged = []
    for r in runs:
        if merged and merged[-1]["y"] == r["y"] \
                and abs(r["x0"] - merged[-1]["x1"]) < 0.06:
            merged[-1]["t"] += r["t"]
            merged[-1]["x1"] = r["x1"]
        else:
            merged.append(r)
    return merged


def harvest_left(page):
    """왼쪽 면 → {passage_no, category, tokens(줄별 낱말+주석), translation, ...}"""
    chars = _chars(page)
    hl, ul = _strokes(page)

    body_lines = _group_lines(chars, *BODY_SIZE)
    # 본문 영역: 지문 프레임(위 24mm~) 안의 줄만. 번역/푸터는 글자 크기가 다르다.
    body_lines = {y: cs for y, cs in body_lines.items()
                  if 24 / MM > 0 and 60 <= y <= 420
                  and all(c["font"].startswith("NotoSans") for c in cs[:3])}

    annos = _anno_spans(page)
    baselines = sorted(body_lines)

    lines_out = []
    for y in baselines:
        ws = _words(body_lines[y])
        # 형광펜 / 밑줄
        for w in ws:
            for seg in hl:
                if abs(seg["y"] - (y - 3.0)) < 2.0 and \
                        seg["x0"] - 0.6 <= w["x0"] and w["x1"] <= seg["x1"] + 0.6:
                    w["hl"] = _rgb_hex(seg["color"])
            for seg in ul:
                if 0 < seg["y"] - y < 6 and \
                        seg["x0"] - 0.6 <= w["x0"] and w["x1"] <= seg["x1"] + 0.6:
                    w["ul"] = _rgb_hex(seg["color"])
        lines_out.append({"y": y, "words": ws})

    # 주석을 낱말에 붙인다
    unattached = []
    for a in annos:
        best, best_ov, slot = None, 0, None
        ac = (a["x0"] + a["x1"]) / 2.0
        for ln in lines_out:
            dy = a["y"] - ln["y"]
            if abs(dy - ABOVE_DY) < TOL:
                s = "up"
            elif abs(dy - BELOW_DY) < TOL:
                s = "dn"
            else:
                continue
            for i, w in enumerate(ln["words"]):
                ov = min(w["x1"], a["x1"]) - max(w["x0"], a["x0"])
                # 낱말 중앙과 주석 중앙의 거리로 고른다(주석이 더 넓을 수 있다)
                score = -abs((w["x0"] + w["x1"]) / 2.0 - ac)
                if best is None or score > best_ov:
                    best, best_ov, slot = (ln, i), score, s
        if best is None:
            unattached.append(a)
            continue
        ln, i = best
        ln["words"][i].setdefault(slot, []).append(
            {"t": a["t"]} if a["color"] in (0xA7A9AC,)
            else {"t": a["t"], "color": _hex(a["color"])})

    return {"lines": lines_out, "unattached": [u["t"] for u in unattached]}


def main(pdf, page_no, out):
    d = fitz.open(pdf)
    res = harvest_left(d[page_no - 1])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    n_w = sum(len(l["words"]) for l in res["lines"])
    n_a = sum(len(w.get("up", [])) + len(w.get("dn", []))
              for l in res["lines"] for w in l["words"])
    print("줄 %d · 낱말 %d · 주석 %d · 미부착 %d"
          % (len(res["lines"]), n_w, n_a, len(res["unattached"])))
    if res["unattached"]:
        print("  미부착:", res["unattached"][:10])


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
