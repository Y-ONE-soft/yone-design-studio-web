"""책 1권 빌드 오케스트레이터 — `config.json` 하나로 원고→PDF.

교재 폴더에서:
    python3 -m core.render_vivlio.book <책폴더> data      원고 → data.json
    python3 -m core.render_vivlio.book <책폴더> theme     팔레트 → 테마 재생성
    python3 -m core.render_vivlio.book <책폴더> build     조판 → PDF (+마감)
    python3 -m core.render_vivlio.book <책폴더> verify    검수 게이트
    python3 -m core.render_vivlio.book <책폴더> all       data → build → verify
    python3 -m core.render_vivlio.book --list            교재 트리의 책 목록

계열별 옵션은 `--키` / `--키=값` 으로 그대로 흘려보낸다(예: `--sample`, `--nomemo`).
"""
import os
import sys

from core.render_vivlio import config as bookconfig
from core.render_vivlio import series as series_registry
from core.render_vivlio import verify as gate


def _series(cfg):
    return series_registry.get(cfg.series)


def load(path):
    return bookconfig.load(path)


def gen_data(cfg, log=print):
    return _series(cfg).gen_data(cfg, log)


def gen_theme(cfg, log=print):
    return _series(cfg).gen_theme(cfg, log)


def build(cfg, log=print, **opts):
    return _series(cfg).build(cfg, log, **opts)


def verify(cfg, log=print, pdf=None, **opts):
    """공용 게이트 + 계열 게이트. Report 를 돌려준다."""
    s = _series(cfg)
    vcfg = cfg.section("verify") or {}
    pdf = pdf or cfg.out_pdf(vcfg.get("suffix", ""))
    report = gate.Report(f"{cfg.book.get('title', cfg.series)} — {os.path.basename(pdf)}")
    if not os.path.exists(pdf):
        return report.fail(f"PDF 없음: {pdf}")

    from core.render_vivlio import probe
    texts = probe.page_texts(pdf)
    report.note(f"쪽수 {len(texts)}")

    # 뒤에 붙인 원본 아트워크(간지·MEMO)는 우리가 조판한 면이 아니다 →
    # 판면·도련 검사에서 뺀다. `skip_last` 는 "마지막 N 면".
    skip = list(vcfg.get("skip_pages") or ())
    n_last = vcfg.get("skip_last") or 0
    skip += [len(texts) - k for k in range(n_last)]
    skip = tuple(sorted(set(p for p in skip if 1 <= p <= len(texts))))
    if vcfg.get("frame"):
        gate.check_overflow(pdf, vcfg["frame"], report, skip_pages=skip)
    if cfg.page["bleed"]:
        gate.check_trimbox(pdf, report, bleed=cfg.page["bleed"])
        gate.check_bleed_coverage(pdf, report, bleed=cfg.page["bleed"],
                                  skip_pages=skip)
    gate.check_blanks(texts, report, ignore_chars=vcfg.get("blank_ignore", ""))
    s.verify(cfg, log, report)
    return report


# ── 책 목록 ─────────────────────────────────────────────────────────────
def discover(root=None, max_depth=6):
    """교재 트리에서 `config.json`(series 키가 있는 것)을 찾는다.

    책 목록을 따로 관리하는 표를 두지 않는다 — 표와 실제 폴더가 어긋나는 순간
    쓸모가 없어지기 때문이다. 진실은 교재 폴더에 있는 config.json 이다.
    """
    root = root or os.path.join(bookconfig._studio_root(), "조판", "교재")
    out = []
    if not os.path.isdir(root):
        return out
    base = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - base >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(("_", ".")) and d != "build"]
        if "config.json" not in filenames:
            continue
        try:
            cfg = bookconfig.load(os.path.join(dirpath, "config.json"))
        except Exception:
            continue
        out.append(cfg)
    return sorted(out, key=lambda c: (c.series, c.root))


def print_books(log=print, root=None):
    books = discover(root)
    log(f"■ Vivliostyle 책 {len(books)}권 "
        f"(계열: {', '.join(series_registry.names())})")
    for c in books:
        rel = c.root.replace(bookconfig._studio_root() + os.sep, "")
        log(f"  [{c.series}] {c.book.get('title', '?')} — {rel}")
    return books


# ── CLI ─────────────────────────────────────────────────────────────────
def _parse_opts(argv):
    opts = {}
    for a in argv:
        if not a.startswith("--"):
            continue
        k, _, v = a[2:].partition("=")
        opts[k.replace("-", "_")] = v if v else True
    return opts


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] in ("--list", "-l", "list"):
        print_books()
        return 0
    book = argv[0]
    steps = [a for a in argv[1:] if not a.startswith("--")] or ["build"]
    opts = _parse_opts(argv[1:])
    cfg = load(book)
    log = print
    log(f"■ {cfg.book.get('title', '')} · 계열 {cfg.series} · {cfg.root}")

    if "all" in steps:
        steps = ["data", "build", "verify"]
    rc = 0
    for st in steps:
        if st == "data":
            gen_data(cfg, log)
        elif st == "theme":
            gen_theme(cfg, log)
        elif st == "build":
            build(cfg, log, **opts)
        elif st == "verify":
            if not verify(cfg, log, **opts).print(log):
                rc = 1
        else:
            log(f"[오류] 알 수 없는 단계: {st}")
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
