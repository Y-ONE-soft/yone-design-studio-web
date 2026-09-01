# -*- coding: utf-8 -*-
"""동형모의고사 조판 — IR + 학교 프로파일 → PDF.

    원고 → (engines.mockexam_v2.parser) → IR
                                           ↓
                     profiles/<학교키>.json + _결정.json
                                           ↓
                     markup.build_html  +  theme.build_css
                                           ↓
                     Vivliostyle CLI → PDF

기존 경로(`core/render_vivlio/mockexam.py` + `themes/mockexam.css`)와 다른 점:
한영3 InDesign 산출물 하나를 실측해 만든 **고정 테마**가 아니라, 학교마다 실제
기출에서 뽑은 **프로파일이 조판을 구동**한다.
"""
import json
import os

from core.render_vivlio import cli as _cli
from core.render_vivlio import stage as _stage
from core.render_vivlio.series.mockexam import markup, profile as P, score, theme


def render(ir, key, out_pdf, log=print, build_dir=None, case=None,
           timeout=600):
    """IR 문서 + 학교키 → PDF.

    Returns:
        {"pdf", "pages", "seconds", "warnings", "notes", "spec"}
    """
    spec = P.get(key)
    out_pdf = os.path.abspath(out_pdf)
    build_dir = build_dir or os.path.join(os.path.dirname(out_pdf),
                                          f"_build_{key}")
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)

    # ── 배점: 학교 총점을 원고 문항 수에 배분 (사용자 결정) ──
    n_sel = sum(1 for it in ir.get("items", []) if it.get("kind") != "서술형")
    n_ess = sum(1 for it in ir.get("items", []) if it.get("kind") == "서술형")
    alloc = score.allocate(P.raw(key), n_sel, n_ess)
    for n in alloc["notes"]:
        log(f"[배점] {n}")

    # ── HTML / CSS ──
    html_text, warns = markup.build_html(ir, spec, case=case, scores=alloc)
    css = theme.build_css(spec)
    with open(os.path.join(build_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_text)
    with open(os.path.join(build_dir, "theme.css"), "w", encoding="utf-8") as f:
        f.write(css)

    # ── 서체 ──
    fonts = theme.font_files_for(spec)
    missing = _stage.stage_fonts(build_dir, fonts, log=log, required=False)
    if missing:
        warns.append(f"서체 없음(폴백 사용): {', '.join(missing)}")

    # ── 조판 ──
    if not _cli.cli_available():
        raise RuntimeError(
            f"Vivliostyle CLI 미설치 — `cd {_cli.PILOT_DIR} && npm ci` 후 재시도")
    log(f"[조판] {key} — {n_sel}선택형 + {n_ess}서답형, "
        f"정본 {spec.ref_exam}{' (대체)' if spec.is_fallback else ''}")
    secs = _cli.run_build(os.path.join(build_dir, "index.html"), out_pdf,
                          log=log, timeout=timeout)

    from core.render_vivlio import probe
    pages = probe.page_count(out_pdf)
    log(f"[조판] 완료 {os.path.basename(out_pdf)} ({pages}쪽, {round(secs,1)}s)")

    # 프로파일이 못 채운 자리는 조용히 넘기지 않는다
    for m in spec.missing:
        warns.append(f"프로파일 미확정: {m}")
    if spec.is_fallback:
        warns.append(f"정본이 직전 회차가 아니다({spec.ref_exam}) — {spec.ref_fallback}")
    if spec.approx:
        warns.append("수치가 근사값이다(정본이 스캔) — 판형·글자 크기 미확정")

    return {"pdf": out_pdf, "pages": pages, "seconds": round(secs, 1),
            "warnings": warns, "notes": alloc["notes"], "spec": spec,
            "build_dir": build_dir}


def render_manuscript(path, key, out_pdf, log=print, **kw):
    """원고 파일 하나 → PDF (파서까지 포함한 편의 경로)."""
    from engines.mockexam_v2.parser import build_ir, extract_file_paragraphs
    paras = extract_file_paragraphs(path)
    ir = build_ir(paras)
    return render(ir, key, out_pdf, log=log, **kw)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="동형모의고사 프로파일 조판")
    ap.add_argument("key", help="학교키 (배재1, 한영2 …)")
    ap.add_argument("src", help="원고 파일 또는 IR json")
    ap.add_argument("-o", "--out", required=True, help="산출 PDF")
    a = ap.parse_args()
    if a.src.endswith(".json"):
        res = render(json.load(open(a.src, encoding="utf-8")), a.key, a.out)
    else:
        res = render_manuscript(a.src, a.key, a.out)
    for w in res["warnings"]:
        print("⚠", w)
    print(f"→ {res['pdf']} ({res['pages']}쪽)")
