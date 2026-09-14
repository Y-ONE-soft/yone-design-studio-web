#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파이널 직전보충 — 표지 + 내지 합본 (학원 출력 · 중철).

    python3 scripts/final_merge_cover.py <책폴더> [--cover-dir <표지 OUTPUT>]

면 차례(사용자 지시 2026-09-14):

    앞표지 · 빈 면 · 내지(차례 … 크레딧 직전) · MEMO … · 크레딧 · 빈 면 · 뒤표지

- 중철이라 **총 면수는 4의 배수**. 모자라면 크레딧 앞에 MEMO 면을 넣어 채운다.
- 내지의 짝 맞춤 빈 면(글자 없는 면)은 빼고 다시 센다 — 그 자리는 MEMO 가 맡는다.
- 표지 PDF(일러스트 자동화 산출)는 `앞 · 빈 · 빈 · 뒤` 4면이다. 가운데 두 빈 면을
  표지 안쪽 빈 면으로 쓴다.
- 도련 없음(재단 크기 210×297). 내지 인쇄본은 MediaBox 원점이 (8.5, 8.5) 라
  **원점을 0 으로 옮긴다**(내용 앞에 이동 행렬을 넣고 상자를 [0 0 W H] 로) — 일부
  출력기가 원점이 0 이 아닌 면을 어긋나게 찍는다.
- 결과: `<학교>_파이널(VolN)_인쇄.pdf` 하나. 내지만 있던 `_내지_인쇄.pdf` 는 지운다.
"""
import argparse
import glob
import os
import re
import sys
import unicodedata

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COVER_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/파이널 직전보충/OUTPUT"
FONT_B = os.path.join(BASE, "pilot/pocketbook/build/fonts/EliceDXNeolliOTF-Bold.otf")
FONT_M = os.path.join(BASE, "pilot/pocketbook/build/fonts/EliceDXNeolliOTF-Medium.otf")
PT = 72 / 25.4
W, H = 210 * PT, 297 * PT
K = lambda k: (0, 0, 0, k)          # noqa: E731  CMYK 먹 k(0~1)

EXAM = {"1-중간": "1학기중간고사", "1-기말": "1학기기말고사",
        "2-중간": "2학기중간고사", "2-기말": "2학기기말고사"}


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── MEMO 면 ─────────────────────────────────────────────────────────────
def memo_page(doc, at):
    """내지와 같은 결의 MEMO 면. 머리 괘선·제목·쪽 선 — 먹 1도, 선 0.35pt 이상."""
    pg = doc.new_page(pno=at, width=W, height=H)
    pg.insert_font(fontname="nb", fontfile=FONT_B)
    pg.insert_font(fontname="nm", fontfile=FONT_M)
    # 머리 괘선 — 내지와 같은 높이(재단 기준 20mm), 사방 끝까지
    pg.draw_line((0, 20 * PT), (W, 20 * PT), color=K(1), width=0.75)
    # 제목
    pg.insert_text((22 * PT, 34.5 * PT), "MEMO", fontname="nb", fontsize=20,
                   color=K(1))
    # 쪽 선 — 판면 안(좌우 22mm · 위 44mm · 아래 272mm), 9mm 간격, 먹 25%
    y = 44.0
    while y <= 272.0 + 1e-6:
        pg.draw_line((22 * PT, y * PT), (W - 22 * PT, y * PT), color=K(0.25),
                     width=0.4)
        y += 9.0
    # 꼬리말 — 내지와 같은 자리의 브랜드
    pg.insert_text((22 * PT, 286 * PT), "FINAL STEP", fontname="nb", fontsize=7,
                   color=K(1))
    return pg


# ── 원점 옮기기 ─────────────────────────────────────────────────────────
def _box(doc, pg, key):
    kind, val = doc.xref_get_key(pg.xref, key)
    if kind != "array":
        return None
    return [float(v) for v in re.findall(r"-?[\d.]+", val)]


def normalize_origin(doc):
    """MediaBox 원점이 0 이 아닌 면 → 내용 앞에 `cm` 이동을 넣고 상자를 [0 0 w h]."""
    moved = 0
    for pg in doc:
        mb = _box(doc, pg, "MediaBox")
        if not mb:
            continue
        x0, y0, x1, y1 = mb
        if abs(x0) < 0.01 and abs(y0) < 0.01:
            continue
        pg.clean_contents(sanitize=False)          # 내용 스트림을 하나로
        kind, cont = doc.xref_get_key(pg.xref, "Contents")
        xref = int(re.match(r"(\d+)", cont).group(1))
        body = doc.xref_stream(xref) or b""
        doc.update_stream(xref, b"q 1 0 0 1 %.6f %.6f cm\n" % (-x0, -y0)
                          + body + b"\nQ")
        box = "[0 0 %.6f %.6f]" % (x1 - x0, y1 - y0)
        for key in ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"):
            if key == "MediaBox" or doc.xref_get_key(pg.xref, key)[0] == "array":
                doc.xref_set_key(pg.xref, key, box)
        moved += 1
    return moved


# ── 합본 ────────────────────────────────────────────────────────────────
def find_cover(cover_dir, school, grade, period, vol):
    """`파이널_표지_배재고1_2학기중간고사_Vol1.pdf` — 학교 이름은 `배재1` → `배재고1`."""
    m = re.match(r"^(\D+?)(\d)$", school)
    base, g = (m.group(1), m.group(2)) if m else (school, grade[-1:])
    exam = EXAM.get(period.split("-", 1)[1] if period.count("-") >= 1 else "",
                    None)
    exam = EXAM.get("-".join(period.split("-")[1:]), exam)
    cands = []
    for f in os.listdir(cover_dir):
        n = nfc(f)
        if not n.endswith("_Vol%d.pdf" % vol) or exam not in n:
            continue
        if re.search(r"_%s(고|여고|중)?%s_" % (re.escape(base), g), n):
            cands.append(os.path.join(cover_dir, f))
    if len(cands) != 1:
        raise SystemExit("[표지] %s %s Vol%d 표지를 하나로 못 골랐습니다: %s"
                         % (school, exam, vol, [os.path.basename(c) for c in cands]))
    return cands[0]


def merge(book_dir, vol, cover_dir=COVER_DIR, log=print):
    school = nfc(os.path.basename(os.path.normpath(book_dir)))
    period = nfc(os.path.basename(os.path.dirname(os.path.normpath(book_dir))))
    grade = nfc(os.path.basename(os.path.dirname(os.path.dirname(
        os.path.normpath(book_dir)))))
    inner = os.path.join(book_dir, "%s_파이널(Vol%d)_내지_인쇄.pdf" % (school, vol))
    if not os.path.exists(inner):
        raise SystemExit("[합본] 내지 인쇄본이 없습니다: %s" % inner)
    cover = find_cover(cover_dir, school, grade, period, vol)

    doc = fitz.open(inner)                   # 출력 의도(ICC)가 이 문서에 있다 — 바탕으로 쓴다
    cov = fitz.open(cover)
    if cov.page_count != 4:
        raise SystemExit("[표지] 4면(앞·빈·빈·뒤)이 아닙니다: %d면 %s"
                         % (cov.page_count, os.path.basename(cover)))

    # ① 짝 맞춤 빈 면 빼기 (글자 없는 면 — 차례·크레딧은 글자가 있다)
    blanks = [i for i in range(doc.page_count)
              if not doc[i].get_text().strip() and not doc[i].get_drawings()
              and not doc[i].get_images()]
    for i in reversed(blanks):
        doc.delete_page(i)
    n_inner = doc.page_count                 # 크레딧 포함

    # ② 원점 0 으로(내지)
    moved = normalize_origin(doc)

    # ③ MEMO — 표지 4면 + 내지 + MEMO = 4의 배수
    memo = (-(n_inner + 4)) % 4
    for _ in range(memo):
        memo_page(doc, doc.page_count - 1)   # 크레딧 **앞**에

    # ④ 표지: 앞·빈 을 맨 앞에, 빈·뒤 를 맨 뒤에
    doc.insert_pdf(cov, from_page=0, to_page=1, start_at=0)
    doc.insert_pdf(cov, from_page=2, to_page=3)
    normalize_origin(doc)                    # 표지가 원점 0 이 아니어도 맞춘다

    out = os.path.join(book_dir, "%s_파이널(Vol%d)_인쇄.pdf" % (school, vol))
    doc.set_metadata({**(doc.metadata or {}),
                      "title": "%s 파이널 직전보충 Vol%d" % (school, vol)})
    tmp = out + ".tmp"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    cov.close()
    os.replace(tmp, out)

    # 확인
    d = fitz.open(out)
    sizes = {(round(p.rect.width / PT, 1), round(p.rect.height / PT, 1)) for p in d}
    origin = {tuple(_box(d, p, "MediaBox")[:2]) for p in d}
    cs = "".join(p.read_contents().decode("latin-1", "ignore") for p in d)
    rgb = len(re.findall(r"(?m)(?:^|\s)(rg|RG)(?=\s|$)", cs))
    first = " ".join(d[0].get_text().split())[:30]
    last2 = " ".join(d[-3].get_text().split())[:24]
    res = {"out": out, "pages": d.page_count, "sizes": sorted(sizes),
           "origins": sorted(origin), "rgb": rgb, "memo": memo,
           "removed_blank": len(blanks), "inner": n_inner, "moved": moved,
           "cover": os.path.basename(cover)}
    d.close()
    ok = (res["pages"] % 4 == 0 and res["sizes"] == [(210.0, 297.0)]
          and res["origins"] == [(0.0, 0.0)])
    log("■ Vol%d %d면 = 표지 4 + 내지 %d + MEMO %d (뺀 빈 면 %d) · %s · 원점 %s · "
        "RGB 연산자 %d · 표지 %s → %s"
        % (vol, res["pages"], n_inner, memo, len(blanks), res["sizes"],
           res["origins"], rgb, res["cover"], os.path.basename(out)))
    log("   끝에서 셋째 면(크레딧): %s" % last2)
    res["ok"] = ok
    if ok:
        os.remove(inner)
    else:
        log("   ★ 확인 실패 — 내지 인쇄본을 지우지 않았습니다")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--cover-dir", default=COVER_DIR)
    a = ap.parse_args()
    bad = 0
    for vol in (1, 2):
        r = merge(os.path.abspath(a.book), vol, a.cover_dir)
        bad += 0 if r["ok"] else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
