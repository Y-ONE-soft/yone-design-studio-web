"""책 1권 빌드 오케스트레이터 — `config.json` 하나로 원고→PDF.

교재 폴더에서:
    python3 -m core.render_vivlio.book <책폴더> data      원고 → data.json
    python3 -m core.render_vivlio.book <책폴더> theme     팔레트 → 테마 재생성
    python3 -m core.render_vivlio.book <책폴더> render    조판 직전까지(HTML) — 빠름
    python3 -m core.render_vivlio.book <책폴더> watch     라이브 미리보기(브라우저)
    python3 -m core.render_vivlio.book <책폴더> build     조판 → PDF (+마감)
    python3 -m core.render_vivlio.book <책폴더> verify    검수 게이트
    python3 -m core.render_vivlio.book <책폴더> print     인쇄 원고(CMYK) 만들기
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


def render(cfg, log=print, **opts):
    """조판 직전까지 — build/ 를 채우고 HTML 경로를 준다(미리보기용).

    PDF 를 만들지 않으므로 빠르다. `watch` 가 파일이 바뀔 때마다 이걸 부른다.
    """
    return _series(cfg).render_only(cfg, log, **opts)


def print_pdf(cfg, log=print, **opts):
    """RGB 조판본 → CMYK 인쇄 원고. 계열과 무관해 백엔드가 직접 한다.

    config 의 `print` 절:
      suffix   원본 PDF 접미사(어느 산출을 변환할지) / out  결과 접미사
      profile  ICC 이름 또는 절대경로 / gray_map  화면색 → K 비율 표
      cmyk_map 화면색 → 고정 CMYK(이전 판과 색을 정확히 맞춰야 하는 것만)
    """
    from core.render_vivlio import prepress
    pc = cfg.section("print") or {}
    src = cfg.out_pdf(pc.get("suffix", cfg.section("verify").get("suffix", "")))
    if not os.path.exists(src):
        raise FileNotFoundError(f"조판본 없음: {src} — 먼저 build")
    dst = cfg.out_pdf(pc.get("out", "_인쇄"))
    res = prepress.make(src, dst, bleed=cfg.page["bleed"],
                        profile=pc.get("profile"),
                        gray_map=pc.get("gray_map"),
                        cmyk_map=pc.get("cmyk_map"), log=log)
    a = prepress.audit(dst)
    log(f"  판형 {a['media_mm'][2]}×{a['media_mm'][3]}mm · "
        f"재단 {a['trim_mm']} · 색연산자 {a['ops']}")
    if a["rgb_left"]:
        log(f"  [경고] DeviceRGB 연산자가 {a['rgb_left']}개 남았다")
    res["audit"] = a
    return res


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
    _check_print_fresh(cfg, pdf, report)
    s.verify(cfg, log, report)

    # 디자인 게이트 — 기본은 경고(납품 중인 책의 지면을 바꾸지 않기 위해).
    # `verify.design.off: true` 로 아예 끌 수 있고, `strict: true` 면 결함이 된다.
    if not (vcfg.get("design") or {}).get("off"):
        from core.render_vivlio import design_gate
        try:
            design_gate.run(cfg, pdf, report, log=log, skip_pages=skip)
        except Exception as e:      # 디자인 게이트가 본 게이트를 막지 않게
            report.note(f"[디자인] 검사 실패(건너뜀): {e}")
    return report


def _check_print_fresh(cfg, src, report):
    """인쇄 원고가 조판본보다 오래됐는가 — 조용히 뒤처지면 옛 색으로 납품된다."""
    pc = cfg.section("print") or {}
    if not pc:
        return
    out = cfg.out_pdf(pc.get("out", "_인쇄"))
    if not os.path.exists(out):
        return report.fail(f"인쇄 원고 없음: {os.path.basename(out)} — `print` 를 돌릴 것")
    if os.path.getmtime(out) < os.path.getmtime(src) - 1:
        return report.fail(
            f"인쇄 원고가 조판본보다 오래됐다 "
            f"({os.path.basename(out)}) — `print` 를 다시 돌릴 것")
    report.note(f"인쇄 원고 최신 ({os.path.basename(out)})")


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
        # ⚠ 인쇄본을 빼면 조판본만 갱신돼 **인쇄 원고가 조용히 뒤처진다**
        #    (실제로 겪음). `print` 절이 있는 책은 all 에 포함한다.
        steps = ["data", "build"] + (["print"] if cfg.get("print") else []) + ["verify"]
    if "watch" in steps:
        # 미리보기는 다른 단계와 섞지 않는다 — 끝나지 않는 명령이다.
        from core.render_vivlio import watch as watch_mod
        port = int(opts.pop("port", 13000) or 13000)
        host = str(opts.pop("host", "127.0.0.1") or "127.0.0.1")
        if opts.pop("data", False):
            gen_data(cfg, log)
        return watch_mod.run(cfg, book, log, port=port, host=host, **opts)

    rc = 0
    for st in steps:
        if st == "data":
            gen_data(cfg, log)
        elif st == "theme":
            gen_theme(cfg, log)
        elif st == "render":
            html = render(cfg, log, **opts)
            # watch 가 자식 프로세스의 출력에서 이 줄을 읽는다
            log(f"RENDER_HTML={html}")
        elif st == "build":
            build(cfg, log, **opts)
        elif st == "print":
            print_pdf(cfg, log, **opts)
        elif st == "verify":
            if not verify(cfg, log, **opts).print(log):
                rc = 1
        else:
            log(f"[오류] 알 수 없는 단계: {st}")
            rc = 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
