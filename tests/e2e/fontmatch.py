"""서체 고르기 — 원본 PDF 글 조각의 글자 모양을 편집기 시스템 서체마다 겹쳐 가장 닮은 서체를 찾는다.
절차: docs/편집기_재현/절차.md 「서체 이름이 PDF 에 없으면(Type3 윤곽) — 글자 모양을 후보 서체와 겹쳐 고른다」.

    python3 tests/e2e/fontmatch.py <PDF> <쪽> "<조각 글>" [몇 번째=0]
    python3 tests/e2e/fontmatch.py <PDF> "<쪽>:<글>" "<쪽>:<글>" …      여럿을 한 번에(위 3개씩)

원본 조각(같은 글의 span)을 600dpi 로 그려 잉크 상자를 자르고, 서체 파일마다 같은 글을 그려 같은 크기로 맞춘 뒤 겹침(IoU)을 잰다.
결과는 겹침이 큰 순서 — 서체 이름 · 굵기 · 파일. 그 글의 글자가 없는 서체는 뺀다.
"""
import sys

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))))


def ink(img, thr=140):
    a = np.asarray(img.convert("L")) < thr
    ys, xs = np.where(a)
    if not len(xs):
        return None
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def ref_crop(pdf, pno, text, nth=0):
    page = pymupdf.open(pdf)[pno - 1]
    hits = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if sp["text"].strip() == text:
                    hits.append(sp)
    if len(hits) <= nth:                                   # 한 글자씩 찍힌 글 — 같은 줄에서 잇닿은 조각을 이어 그 글만큼만 자른다
        want = text.replace(" ", "")
        allsp = sorted((sp for b in page.get_text("dict")["blocks"] for ln in b.get("lines", []) for sp in ln["spans"] if sp["text"].strip()),
                       key=lambda sp: (round(sp["bbox"][1]), sp["bbox"][0]))
        for i in range(len(allsp)):
            acc, bb = "", pymupdf.Rect()
            for sp in allsp[i:]:
                if abs(sp["bbox"][1] - allsp[i]["bbox"][1]) > 2 or sp["size"] != allsp[i]["size"]:
                    break
                acc += sp["text"].replace(" ", "")
                bb |= pymupdf.Rect(sp["bbox"])
                if not want.startswith(acc):
                    break
                if acc == want:
                    hits.append({"bbox": tuple(bb), "size": sp["size"], "color": sp["color"]})
                    break
    sp = hits[nth]
    pix = page.get_pixmap(clip=pymupdf.Rect(sp["bbox"]), dpi=600)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    c = sp.get("color", 0)
    L = np.asarray(img.convert("L")).astype(int)
    bg = int(np.median(np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]])))   # 바탕 = 테두리 줄 — 굵고 큰 글은 글자가 칸의 절반을 넘어 전체 가운데 값이 글자 색이 된다(광문보카 간지 「어휘끝」 30pt)
    if (c >> 16 & 255) + (c >> 8 & 255) + (c & 255) > 600:   # 흰 · 밝은 글(색 바탕 위) — 바탕보다 밝은 쪽이 글자
        a = L > bg + (255 - bg) // 2
    else:                                                  # 어두운 · 색 글 — 바탕보다 어두운 쪽이 글자
        a = L < bg - max(bg - int(L.min()), 1) // 2
    ys, xs = np.where(a)
    REF_AT.update(page=page, bbox=pymupdf.Rect(sp["bbox"]), light=(c >> 16 & 255) + (c >> 8 & 255) + (c & 255) > 600)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1], sp["size"]


REF_AT = {}


def ref_glyphs():
    """방금 자른 조각의 글자마다 잉크 — 자간 · 글자 사이를 넓힌 글(「P A R T 1」 · 「GWANGMUNVOCA」)은 줄 통째 겹침이 낮게 나온다.
    글자 하나씩 잘라 서체 글자 하나와 겹치면 자간과 상관없다(2026-10-19 광문보카)."""
    page, box, light = REF_AT["page"], REF_AT["bbox"], REF_AT["light"]
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                for ch in sp["chars"]:
                    r = pymupdf.Rect(ch["bbox"])
                    if not ch["c"].strip() or not box.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
                        continue
                    pix = page.get_pixmap(clip=r, dpi=600)
                    L = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")).astype(int)
                    bg = int(np.median(np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]])))
                    a = L > bg + (255 - bg) // 2 if light else L < bg - max(bg - int(L.min()), 1) // 2
                    ys, xs = np.where(a)
                    if len(xs):
                        out.append((ch["c"], a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]))
    return out


def cand_crop(path, text, px):
    try:
        f = ImageFont.truetype(path, px)
    except Exception:
        return None
    w = int(px * (len(text) + 2))
    img = Image.new("L", (w, int(px * 2)), 255)
    ImageDraw.Draw(img).text((px // 2, px // 4), text, font=f, fill=0)
    return ink(img)


def has_glyphs(path, text):
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(path, fontNumber=0, lazy=True).getBestCmap() or {}
        return all(ord(ch) in cmap for ch in text if not ch.isspace())
    except Exception:
        return True


def iou(a, b):
    h, w = a.shape
    bb = np.asarray(Image.fromarray((b * 255).astype("uint8")).resize((w, h))) > 127
    return (a & bb).sum() / max((a | bb).sum(), 1), abs(b.shape[1] / b.shape[0] - w / h) / (w / h)


def main(pdf, pno, text, nth=0, top=8):
    from core.units.fonts import system_fonts
    ref, size = ref_crop(pdf, pno, text, nth)
    glyphs = ref_glyphs()
    px = 200
    rows = []
    for f in system_fonts():
        if not has_glyphs(f["path"], text):
            continue
        c = cand_crop(f["path"], text, px)
        if c is None:
            continue
        s, ar = iou(ref, c)
        gs = []                                            # 글자 하나씩 — 자간과 상관없는 겹침
        for ch, g in glyphs:
            cg = cand_crop(f["path"], ch, px)
            if cg is not None and g.shape[0] > 3 and g.shape[1] > 1:
                gi, gar = iou(g, cg)
                gs.append(gi - gar * 0.5)
        gm = sum(gs) / len(gs) if gs else 0.0
        rows.append((max(s - ar * 0.5, gm), s, ar, gm, f["family"], f.get("weight"), f["file"]))
    rows.sort(reverse=True)
    print(f"「{text}」 {pdf} {pno}쪽 · 원본 {size:.1f}pt · 후보 {len(rows)} · 글자 {len(glyphs)}")
    for r in rows[:top]:
        print(f"  {r[0]:.3f}  겹침 {r[1]:.3f} · 가로세로 차 {r[2]:.2f} · 글자마다 {r[3]:.3f}  {r[4]} {r[5]}  ({r[6]})")


if __name__ == "__main__":
    a = sys.argv[1:]
    if ":" in a[1]:
        for q in a[1:]:
            pn, t = q.split(":", 1)
            try:
                main(a[0], int(pn), t, 0, 3)
            except IndexError:
                print(f"「{t}」 {pn}쪽 — 그 글 조각을 못 찾음")
    else:
        main(a[0], int(a[1]), a[2], int(a[3]) if len(a) > 3 else 0)
