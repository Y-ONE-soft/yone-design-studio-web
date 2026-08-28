#!/usr/bin/env python3
"""Vivliostyle 조판 회귀 기준선 — 면별 **픽셀·텍스트 해시**.

납품 중인 교재의 산출 PDF 가 **한 픽셀도 바뀌면 안 된다**는 것이 이 작업의 하드
게이트다(이미 납품한 책과 새 원고로 만든 신규 작업본이 달라지면 안 되기 때문).
손잡이를 뚫으려면 CSS 를 파라미터화해야 하는데, 그때 기본값이 현재값과 정확히
같은지를 사람 눈으로는 확인할 수 없다 — 그래서 기계가 잰다.

    python3 scripts/vivlio_baseline.py list
    python3 scripts/vivlio_baseline.py capture            # 전 교재 기준선 뜨기
    python3 scripts/vivlio_baseline.py capture --books blackbook,sangil
    python3 scripts/vivlio_baseline.py compare            # 지금 PDF ↔ 기준선
    python3 scripts/vivlio_baseline.py compare --books special -v

기준선은 `tests/baseline/vivlio/<키>.json` 에 쌓인다(리포에 커밋 — 기계가 바뀌어도
같은 자를 쓰기 위해). 교재 폴더는 git 이 아니므로 산출 PDF 자체는 별도 백업이다.

⚠ 픽셀 해시는 **MuPDF 판본에 딸린다**. 판본이 바뀌면 픽셀은 전부 다르게 나오므로
   그때는 텍스트 해시(`tx`)만 신뢰하고 기준선을 다시 떠야 한다 — 파일에 판본을
   적어 두고 compare 가 다르면 경고한다.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import sys
import unicodedata


def nfc(s):
    """한글 파일명은 macOS 파일시스템이 NFD 로 준다 — 쉘 인자·JSON 키는 NFC 다.

    정규화하지 않으면 '눈에 똑같은 이름'이 안 맞아 **기준선에 없다**고 나온다
    (실제로 여기서 데였다). 저장·조회 양쪽에서 NFC 로 맞춘다.
    """
    return unicodedata.normalize("NFC", s)


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "tests", "baseline", "vivlio")
DPI = 100                     # 면당 ~50ms. 조판 차이는 이 해상도로 충분히 드러난다.

# 교재 = (표시 이름, 스튜디오 루트 기준 상대경로, 엔진)
#   viv    = 3계층 엔진(core/render_vivlio) — `bin/viv <책폴더> …`
#   middle = 중등부 전용 automation — `python3 build.py <키> <권>`
BOOKS = {
    "blackbook": ("블랙북01 (배재고1 26-2-중간)",
                  "조판/교재/프리미엄북/블랙북/26-2-중간", "viv"),
    "sangil":    ("상일보카01 (상일여고1 26-2-중간)",
                  "조판/교재/단어장/상일보카/26-2-중간", "viv"),
    "gwangmun":  ("광문보카01 (광문고1 26-2-중간)",
                  "조판/교재/단어장/광문보카/26-2-중간", "viv"),
    "special":   ("예비고1특강 (광교관 26-여름)",
                  "조판/교재/특강교재/예비고1특강/26-여름", "viv"),
    "cheonjae":  ("중2 천재(소) L5 (1·2권)",
                  "조판/교재/중등부/내신 정규 교재/중2_천재소_L5", "middle"),
    "donga":     ("중2 동아(윤) L5 (1·2권)",
                  "조판/교재/중등부/내신 정규 교재/중2_동아윤_L5", "middle"),
    "bisang":    ("중2 비상(황) L5 (1·2권)",
                  "조판/교재/중등부/내신 정규 교재/중2_비상황_L5", "middle"),
}


# ── 스튜디오 루트 ────────────────────────────────────────────────
def studio_root():
    """core.render_vivlio.config 와 같은 규칙으로 찾는다(중복 구현하지 않는다)."""
    sys.path.insert(0, REPO)
    from core.render_vivlio.config import _studio_root
    return _studio_root()


def book_dir(key, root):
    return os.path.join(root, BOOKS[key][1])


# ── 해시 ────────────────────────────────────────────────────────
def _sha(b):
    return hashlib.sha256(b).hexdigest()[:24]


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def fingerprint_pdf(path, dpi=DPI):
    """PDF 한 개 → {sha256, bytes, pages, page:[{i, px, tx, w, h}]}"""
    import fitz
    d = fitz.open(path)
    pages = []
    try:
        for i, pg in enumerate(d):
            pm = pg.get_pixmap(dpi=dpi, alpha=False)
            # 텍스트는 공백 정규화 후 해시 — 줄바꿈 위치만 달라진 것은 차이가 아니다
            tx = " ".join(pg.get_text("text").split())
            r = pg.rect
            pages.append({"i": i + 1, "px": _sha(pm.samples),
                          "tx": _sha(tx.encode("utf-8")),
                          "w": round(r.width, 2), "h": round(r.height, 2)})
    finally:
        d.close()
    return {"sha256": file_sha(path), "bytes": os.path.getsize(path),
            "pages": len(pages), "page": pages}


def fingerprint_book(key, root, dpi=DPI, log=print, override_dir=None):
    """책 폴더 최상위의 모든 *.pdf. build/ 안의 중간 산출은 보지 않는다.

    `override_dir` 를 주면 그 폴더를 대신 본다 — **교재 폴더 사본에서 빌드해
    납품본을 건드리지 않고 대조**하기 위한 것이다(재현성 확인의 기본 절차).
    """
    import fitz
    d = override_dir or book_dir(key, root)
    if not os.path.isdir(d):
        raise SystemExit("교재 폴더 없음: %s" % d)
    pdfs = {}
    for p in sorted(glob.glob(os.path.join(d, "*.pdf"))):
        name = nfc(os.path.basename(p))
        try:
            pdfs[name] = fingerprint_pdf(p, dpi)
            log("      %-52s %4d면" % (name[:52], pdfs[name]["pages"]))
        except Exception as e:                      # 깨진 PDF 도 사실로 기록
            pdfs[name] = {"error": str(e)}
            log("      %-52s !! %s" % (name[:52], e))
    return {"key": key, "label": BOOKS[key][0], "engine": BOOKS[key][2],
            "dir": BOOKS[key][1], "dpi": dpi,
            "mupdf": fitz.VersionBind + "/" + fitz.VersionFitz,
            "captured": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pdfs": pdfs}


# ── 저장·비교 ───────────────────────────────────────────────────
def path_for(key):
    return os.path.join(OUT_DIR, key + ".json")


def load(key):
    p = path_for(key)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    # 옛 기준선은 NFD 키로 저장돼 있을 수 있다 — 읽을 때 맞춰 준다
    d["pdfs"] = {nfc(k): v for k, v in (d.get("pdfs") or {}).items()}
    return d


def save(key, data):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(path_for(key), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def diff_book(old, new, verbose=False):
    """기준선 ↔ 현재 → `(줄 목록, 결함 수)`.

    ⚠ **바이트만 다른 것은 결함이 아니다.** PDF 에는 생성 시각·ID 가 들어가므로
    같은 입력으로 다시 조판해도 파일 해시는 매번 달라진다. 우리가 지켜야 하는
    것은 **지면**(면수·판형·글자·픽셀)이다. 이걸 결함으로 세면 모든 대조가
    실패로 나와 게이트가 무의미해진다.
    """
    out, bad = [], 0
    if old.get("mupdf") != new.get("mupdf"):
        out.append("  ⚠ MuPDF 판본 다름 %s → %s — 픽셀 해시는 신뢰 불가, tx 만 볼 것"
                   % (old.get("mupdf"), new.get("mupdf")))
    o, n = old.get("pdfs", {}), new.get("pdfs", {})
    for name in sorted(set(o) - set(n)):
        out.append("  ✗ 사라짐  %s" % name)
        bad += 1
    for name in sorted(set(n) - set(o)):
        out.append("  + 새 파일 %s (%d면)" % (name, n[name].get("pages", 0)))
    for name in sorted(set(o) & set(n)):
        a, b = o[name], n[name]
        if "error" in a or "error" in b:
            if a.get("error") != b.get("error"):
                out.append("  ✗ %s 읽기 오류 변화: %s → %s"
                           % (name, a.get("error"), b.get("error")))
                bad += 1
            continue
        if a["sha256"] == b["sha256"]:
            continue                                # 파일 자체가 동일 — 볼 것 없음
        if a["pages"] != b["pages"]:
            out.append("  ✗ %s 면수 %d → %d" % (name, a["pages"], b["pages"]))
            bad += 1
        px = [p["i"] for p, q in zip(a["page"], b["page"]) if p["px"] != q["px"]]
        tx = [p["i"] for p, q in zip(a["page"], b["page"]) if p["tx"] != q["tx"]]
        sz = [p["i"] for p, q in zip(a["page"], b["page"])
              if (p["w"], p["h"]) != (q["w"], q["h"])]
        if not (px or tx or sz):
            out.append("  · %s 바이트만 다름(면 내용 동일 — 생성 시각 등)" % name)
            continue
        def brief(v):
            return (", ".join(map(str, v[:12])) + (" …외 %d면" % (len(v) - 12)
                                                   if len(v) > 12 else ""))
        if sz:
            out.append("  ✗ %s 판형 다른 면 %d개: %s" % (name, len(sz), brief(sz)))
        if tx:
            out.append("  ✗ %s **글자** 다른 면 %d개: %s" % (name, len(tx), brief(tx)))
        if px:
            out.append("  ✗ %s 픽셀 다른 면 %d개: %s" % (name, len(px), brief(px)))
        bad += 1
        if verbose and px:
            out.append("     (픽셀만 다르고 글자가 같으면 색·위치·굵기 변화다)")
    return out, bad


# ── CLI ─────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Vivliostyle 조판 회귀 기준선")
    ap.add_argument("cmd", choices=["list", "capture", "compare"])
    ap.add_argument("--books", help="쉼표로 구분한 교재 키 (기본: 전부)")
    ap.add_argument("--dpi", type=int, default=DPI)
    ap.add_argument("--dir", help="compare 전용 — 교재 폴더 대신 이 폴더의 PDF 를 본다"
                                  " (사본에서 빌드해 납품본을 안 건드리고 대조할 때)")
    ap.add_argument("--only", help="compare 전용 — 이 이름의 PDF 만 (사본에 일부만"
                                   " 있을 때 '사라짐'을 오탐하지 않게)")
    ap.add_argument("--newer-than", type=float, metavar="분",
                    help="compare 전용 — 이 분(minute) 안에 다시 만들어진 PDF 만"
                         " 인정한다. **빌드가 죽었는데 옛 PDF 가 남아 통과하는**"
                         " 거짓 합격을 막는다(실제로 겪었다).")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.dir and len(a.books.split(",") if a.books else BOOKS) != 1:
        raise SystemExit("--dir 는 --books 로 교재 하나를 지정해야 한다")

    keys = [k.strip() for k in a.books.split(",")] if a.books else list(BOOKS)
    for k in keys:
        if k not in BOOKS:
            raise SystemExit("모르는 교재 키: %s (가능: %s)" % (k, ", ".join(BOOKS)))
    root = studio_root()

    if a.cmd == "list":
        print("스튜디오 루트: %s\n" % root)
        for k in keys:
            label, rel, eng = BOOKS[k]
            d = os.path.join(root, rel)
            base = load(k)
            n = len(glob.glob(os.path.join(d, "*.pdf")))
            print("  %-10s %-32s %-7s PDF %2d개  기준선 %s"
                  % (k, label, eng, n,
                     base["captured"] if base else "— 없음"))
        return

    if a.cmd == "capture":
        for k in keys:
            print("● %s — %s" % (k, BOOKS[k][0]))
            data = fingerprint_book(k, root, a.dpi)
            save(k, data)
            tot = sum(v.get("pages", 0) for v in data["pdfs"].values())
            print("   → %s (PDF %d개 / %d면)\n"
                  % (os.path.relpath(path_for(k), REPO), len(data["pdfs"]), tot))
        return

    # compare
    bad = 0
    for k in keys:
        old = load(k)
        if not old:
            print("● %s — 기준선 없음 (capture 먼저)" % k)
            bad += 1
            continue
        if a.newer_than:
            import time
            d = a.dir or book_dir(k, root)
            stale = [nfc(os.path.basename(p))
                     for p in glob.glob(os.path.join(d, "*.pdf"))
                     if (not a.only
                         or nfc(os.path.basename(p)) in
                         set(nfc(x.strip()) for x in a.only.split(",")))
                     and time.time() - os.path.getmtime(p) > a.newer_than * 60]
            if stale:
                print("● %s — ✗ 다시 만들어지지 않은 PDF: %s "
                      "(빌드가 실패했는데 옛 파일로 통과하는 것을 막는다)"
                      % (k, ", ".join(stale)))
                bad += 1
                continue
        new = fingerprint_book(k, root, old.get("dpi", a.dpi),
                               log=lambda *_: None, override_dir=a.dir)
        if a.only:
            keep = set(nfc(x.strip()) for x in a.only.split(","))
            old = dict(old, pdfs={n: v for n, v in old["pdfs"].items() if n in keep})
            new = dict(new, pdfs={n: v for n, v in new["pdfs"].items() if n in keep})
            if not old["pdfs"]:
                print("● %s — 기준선에 %s 가 없다" % (k, a.only))
                bad += 1
                continue
        lines, prob = diff_book(old, new, a.verbose)
        if prob:
            bad += 1
            print("● %s — %s" % (k, BOOKS[k][0]))
        elif lines:
            print("● %s — 지면 불변 ✓ (아래는 참고)" % k)
        else:
            print("● %s — 불변 ✓" % k)
        for ln in lines:
            print(ln)
    print("\n%s" % ("전부 불변 ✓" if not bad else "차이 있는 교재 %d개 ✗" % bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
