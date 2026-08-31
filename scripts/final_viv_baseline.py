#!/usr/bin/env python3
"""파이널 직전보충 완성본(InDesign 산출 PDF) 실측 → 베이스라인 JSON.

Vivliostyle 전환의 **진실**은 납품된 완성본이다. 자를 대고 눈으로 맞추지 말고
여기서 뽑은 값으로 CSS 를 역산한다(단어장·블랙북·화이트북이 쓴 방법).

사용:
    python3 scripts/final_viv_baseline.py <Vol1.pdf> <Vol2.pdf> [-o out.json]

기본 출력: tests/fixtures/final_viv_baseline.json

측정 항목
  page      판형·도련·재단
  margins   면 좌우(홀/짝) 판면 경계 — 안쪽/바깥쪽 여백
  grid      섹션별 슬롯 격자(열 시작 x, 행 시작 y, 행 피치)
  type      서체·크기·행간(블록 내 baseline 간격 최빈값)
  color     먹색·바탕상자 회색 3종
  boxes     섹션별 바탕상자 좌우 경계(본문 대비 넘침폭)
"""
import argparse
import collections
import json
import re
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    sys.exit("PyMuPDF 필요: pip install pymupdf")

MM = 25.4 / 72.0


def mm(v):
    return round(v * MM, 2)


def _hex(rgb):
    if rgb is None:
        return None
    return "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in rgb)


def _lines(page):
    """(baseline_y, size, font, x0_mm, text) 목록."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            if not ln["spans"]:
                continue
            s = ln["spans"][0]
            out.append((s["origin"][1], round(s["size"], 2), s["font"],
                        mm(ln["bbox"][0]),
                        "".join(x["text"] for x in ln["spans"])))
    return sorted(out)


def _block_pitch(page):
    """블록 안 baseline 간격(mm) 최빈값 — 본문 행간."""
    c = collections.Counter()
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        ys = [ln["spans"][0]["origin"][1] for ln in b["lines"] if ln["spans"]]
        for a, z in zip(ys, ys[1:]):
            d = round((z - a) * MM, 2)
            if 1 < d < 20:
                c[d] += 1
    return c.most_common(4)


def _line_pitch(page, x_lo, x_hi, size):
    """한 열 안에서 같은 크기 글줄의 baseline 간격 최빈값 — 넓은 행간 섹션용."""
    ys = [o for o, sz, f, x, t in _lines(page)
          if abs(sz - size) < 0.3 and x_lo <= x <= x_hi]
    c = collections.Counter(round((z - a) * MM, 2)
                            for a, z in zip(ys, ys[1:]) if 0 < z - a < 40)
    return c.most_common(4)


def _type_inventory(page):
    c = collections.Counter()
    for o, sz, f, x, t in _lines(page):
        c[(sz, f)] += len(t)
    return [{"size_pt": sz, "font": f, "chars": n}
            for (sz, f), n in c.most_common(8)]


def _fills(page, min_w=3, min_h=1):
    out = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.width * MM < min_w or r.height * MM < min_h:
            continue
        out.append({"fill": _hex(dr.get("fill")),
                    "rect_mm": [mm(r.x0), mm(r.y0), mm(r.x1), mm(r.y1)]})
    return out


def _headers(page, size, tol=0.3):
    """지문 헤더(굵은 큰 글자) 위치 — 슬롯 격자의 고정점."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0 or not b["lines"] or not b["lines"][0]["spans"]:
            continue
        s = b["lines"][0]["spans"][0]
        if abs(s["size"] - size) < tol:
            out.append({"x_mm": mm(b["bbox"][0]), "y_mm": mm(b["bbox"][1]),
                        "text": s["text"][:24]})
    return sorted(out, key=lambda h: (h["y_mm"], h["x_mm"]))


_RE_FOOT = re.compile(r"CHAPTER\.\d+\s+([가-힣][가-힣/ ]*)")
_RE_BAND = re.compile(r"^\s*(\d)\s*\n\s*([가-힣/ ]+)\s*$", re.M)


def _section_of(page, first, last):
    """면 섹션 판정 — 러닝 꼬리말("CHAPTER.01 문장 배열  3")이 1순위.

    간지·크레딧은 순서로 안다(첫 면·마지막 면). 섹션 띠 문구로 판정하면
    간지의 "문장 - 요약 - 어법 - 서술형" 표제가 걸린다(실측 오분류).
    """
    if first:
        return "간지"
    t = page.get_text()
    if "Writer" in t and last:
        return "크레딧"
    m = _RE_FOOT.search(t)
    if m:
        return m.group(1).strip().replace(" ", "")
    m = _RE_BAND.search(t)
    if m:
        return m.group(2).replace(" ", "")
    return "미분류"


def measure(pdf_path, vol):
    doc = fitz.open(pdf_path)
    p0 = doc[0]
    res = {
        "file": os.path.basename(pdf_path),
        "vol": vol,
        "pages": doc.page_count,
        "page_mm": [mm(p0.rect.width), mm(p0.rect.height)],
        "sections": {},
    }

    by_sec = collections.OrderedDict()
    for i in range(doc.page_count):
        sec = _section_of(doc[i], i == 0, i == doc.page_count - 1)
        by_sec.setdefault(sec, []).append(i)

    for sec, idxs in by_sec.items():
        # 홀/짝 각각 대표 면 하나씩 — 좌우 미러링을 잡기 위해
        sample = {}
        for i in idxs:
            par = "odd" if (i + 1) % 2 else "even"
            sample.setdefault(par, i)
        entry = {"page_count": len(idxs),
                 "page_range": [idxs[0] + 1, idxs[-1] + 1], "parity": {}}
        for par, i in sample.items():
            page = doc[i]
            hdr = _headers(page, 12.0)
            xs, ys = [], []
            for b in page.get_text("dict")["blocks"]:
                if b["type"] == 0:
                    xs += [mm(b["bbox"][0]), mm(b["bbox"][2])]
                    ys += [mm(b["bbox"][1]), mm(b["bbox"][3])]
            entry["parity"][par] = {
                "sample_page": i + 1,
                "text_extent_mm": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
                "slot_headers": hdr,
                "col_x_mm": sorted({h["x_mm"] for h in hdr}),
                "row_y_mm": sorted({h["y_mm"] for h in hdr}),
                "fills": _fills(page),
                "block_pitch_mm": _block_pitch(page),
                "col_pitch_mm": _line_pitch(page, 20, 60, 8.5)
                + _line_pitch(page, 20, 60, 8.46),
                "type": _type_inventory(page),
            }
        res["sections"][sec] = entry
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vol1")
    ap.add_argument("vol2")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "final_viv_baseline.json"))
    a = ap.parse_args()
    out = {"source": "InDesign 완성본 실측",
           "vols": [measure(a.vol1, "Vol1"), measure(a.vol2, "Vol2")]}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
