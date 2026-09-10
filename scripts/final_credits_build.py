# -*- coding: utf-8 -*-
"""마지막 크레딧 면 — **이름만** 갈아 끼운다.

계열 자산 `assets/final/credits.pdf` 의 디자인(FINAL STEP 로고·각인북스 마크·
저작권 줄)은 그대로 두고, 가운데 이름 단만 다시 앉힌다. 이름이 늘고 줄면
단 높이가 바뀌므로 **아래를 붙박아 두고 위로 자란다** — 로고와의 사이가
변하지 않게.

    python3 scripts/final_credits_build.py            # 자산을 다시 만든다
    python3 scripts/final_credits_build.py -o out.pdf # 미리보기만

명단은 아래 `ROLES` 가 정본이다(연구원 배부본 `LastP.pdf` 기준).
"""
import argparse
import os
import sys

import fitz

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = os.path.join(BASE, "core/render_vivlio/assets/final/credits.pdf")
FONT = os.path.join(BASE, "pilot/pocketbook/build/fonts/EliceDXNeolliOTF-Medium.otf")

# ── 명단 (정본) ─────────────────────────────────────────────────────────
ROLES = [
    ("Writer", ["노윤기", "신현규", "이재훈", "윤지수", "안재희", "김지윤"]),
    ("Teacher", ["함태환", "송아영", "박세희", "표슬미", "김태림", "이우솔",
                 "정다니엘", "최아인"]),
    ("Assistant", ["박소원", "전민정", "정우주"]),
    ("Design", ["노혜진"]),
    ("Production", ["서동일", "김완중"]),
]

# ── 판짜기 상수 (원본 자산 실측) ────────────────────────────────────────
X = 61.28              # 왼쪽 기준선
CAP, REST, NAME = 11.0, 8.0, 9.0        # 머리 첫 글자 · 머리 나머지 · 이름
REST_DROP = 0.25       # 작은 글자 밑선이 0.25pt 아래(원본 그대로)
PITCH = 15.0           # 이름 줄 사이
GAP = 36.0             # 앞 단 마지막 이름 밑선 → 다음 단 머리 밑선
BOTTOM = 740.40        # **마지막 이름 밑선** — 각인북스 마크와의 사이를 지킨다
INK = (0.13691920, 0.09648280, 0.08461127)   # 원본 글자색
BAND = fitz.Rect(50, 260, 300, 758)          # 이름 단이 사는 자리(그 밖은 안 건드림)


def layout():
    """(밑선 y, 단 이름 또는 사람 이름) 목록. 아래를 붙박고 위로 자란다."""
    span = sum(PITCH * len(names) for _h, names in ROLES) + GAP * (len(ROLES) - 1)
    y = BOTTOM - span
    out = []
    for i, (head, names) in enumerate(ROLES):
        out.append((y, head, True))
        for n in names:
            y += PITCH
            out.append((y, n, False))
        if i < len(ROLES) - 1:
            y += GAP
    return out


def build(out_path):
    doc = fitz.open(ASSET)
    page = doc[0]

    # 1) 이름 단만 지운다 — 로고·마크·저작권 줄은 BAND 밖이라 그대로.
    #    (단을 통째로 지우고 다시 앉히므로 몇 번을 돌려도 같은 결과다.)
    page.add_redact_annot(BAND)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)

    font = fitz.Font(fontfile=FONT)
    page.insert_font(fontname="neolli", fontfile=FONT)
    for y, text, is_head in layout():
        if is_head:
            page.insert_text((X, y), text[0], fontname="neolli", fontsize=CAP,
                             color=INK)
            adv = font.text_length(text[0], CAP)
            page.insert_text((X + adv, y + REST_DROP), text[1:],
                             fontname="neolli", fontsize=REST, color=INK)
        else:
            page.insert_text((X, y), text, fontname="neolli", fontsize=NAME,
                             color=INK)

    tmp = out_path + ".tmp"
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    os.replace(tmp, out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=ASSET)
    a = ap.parse_args()
    p = build(a.out)
    d = fitz.open(p)
    print("■ %s" % p)
    print(d[0].get_text())
    d.close()


if __name__ == "__main__":
    sys.exit(main())
