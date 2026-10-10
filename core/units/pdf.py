"""지면 SVG 들 → PDF. 크로미움 헤드리스 인쇄(--print-to-pdf). 비블리오처럼 저장이 PDF 다.

브라우저: `YONE_VIV_BROWSER`(컨테이너 /usr/bin/chromium) → 이 맥의 크롬 → PATH 의 chromium/google-chrome.
서체는 브라우저가 가진 것으로 그린다 — 없는 서체는 폴백(컨테이너는 fonts-noto-cjk).
"""
import os
import shutil
import subprocess
import tempfile

from core.units import fonts

PT = 72 / 25.4
_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def browser():
    b = (os.environ.get("YONE_VIV_BROWSER") or "").strip()
    if b and os.path.exists(b):
        return b
    if os.path.exists(_MAC_CHROME):
        return _MAC_CHROME
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def html_of(svgs, w_mm, h_mm, title="지면", keep=None, pad=0):
    """면마다 한 장. @page 크기 = 판형(+ pad mm), 여백 0. SVG 는 width/height 가 mm 로 박혀 있다.
    keep — 낼 면 번호들(없으면 전부). 나머지 면은 함께 그려 글 잇기를 흘린 뒤 인쇄 전에 뺀다(쪽 하나 PDF 에 앞 쪽 이야기가 흘러오게)."""
    pages = "".join(f'<div class="p{"" if keep is None or i in keep else " drop"}">{s["svg"] if isinstance(s, dict) else s}</div>'
                    for i, s in enumerate(svgs))
    drop = ("<script>(document.fonts ? document.fonts.ready : Promise.resolve()).then(() => setTimeout(() => "
            "document.querySelectorAll('.p.drop').forEach(e => e.remove()), 0));</script>") if keep is not None else ""
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>'
            f'@page{{size:{w_mm + pad}mm {h_mm + pad}mm;margin:0}} html,body{{margin:0;padding:0}} '
            f'.p{{width:{w_mm}mm;height:{h_mm}mm;overflow:visible;page-break-after:always;break-after:page;clip-path:inset(0 -{pad}mm -{pad}mm 0)}} '   # 면 위·왼쪽 밖(재단 여백까지 그린 머리 띠)이 앞 면 아래로 비치지 않게
            f'.p > svg{{display:block;width:{w_mm}mm;height:{h_mm}mm;overflow:visible}} .p svg .zone{{display:none}} '
            f'.story-hint,.story-over{{display:none}}{fonts.fix_css()}{fonts.face_css("file")}'                     # 글 잇기 — 「앞 상자에서 이어짐」·넘침 표시는 화면에만
            f'</style></head><body>{pages}<script>{_compose_js()}</script>{drop}</body></html>')


def _compose_js():
    """단락 컴포저 — 인쇄 전에 양끝맞춤 단락의 줄 끝을 고른다(편집기 화면과 같은 코드)."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "js", "units_compose.js")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().replace("</script", "<\\/script")
    except OSError:
        return ""


def to_pdf(svgs, w_mm, h_mm, out_path, title="지면", timeout=180, keep=None):
    """svgs → PDF 파일. 브라우저가 없으면 RuntimeError."""
    b = browser()
    if not b:
        raise RuntimeError("크로미움이 없다 — YONE_VIV_BROWSER 또는 크롬 설치")
    d = tempfile.mkdtemp(prefix="units_pdf_")
    html = os.path.join(d, "index.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(html_of(svgs, w_mm, h_mm, title, keep, pad=1))
    # ⚠ --user-data-dir 를 주면 이 맥의 크롬이 멎는다(첫 실행 프로필 준비에서) — 실측. 플래그는 최소로.
    cmd = [b, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
           "--virtual-time-budget=3000", f"--print-to-pdf={out_path}", "file://" + html]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 100:
        raise RuntimeError("PDF 가 안 나왔다: " + (r.stderr or r.stdout or "")[-400:])
    shutil.rmtree(d, ignore_errors=True)
    exact_pages(out_path, w_mm, h_mm)
    return out_path


def exact_pages(path, w_mm, h_mm):
    """쪽 크기를 판형 그대로 — 크롬은 @page 크기를 1/300 인치로 내린다(A4 210mm → 594.96pt, 0.11mm 좁다).
    판형보다 1mm 크게 그려 두고(html_of pad) 쪽마다 MediaBox·CropBox 를 왼쪽 위에서 판형 크기로 자른다."""
    import fitz
    doc = fitz.open(path)
    w, h = float(w_mm) * PT, float(h_mm) * PT
    for pg in doc:
        mb = pg.mediabox                                                  # PDF 좌표(아래가 0) — 글은 위에서부터 놓였다
        r = fitz.Rect(mb.x0, mb.y1 - h, mb.x0 + w, mb.y1)
        pg.set_cropbox(r)                                                 # 자른 상자가 매체 안이어야 해서 매체를 먼저 줄이지 않는다
        pg.set_mediabox(r)
    tmp = path + ".exact"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, path)


# ── 인쇄용 ──────────────────────────────────────────────────────────────

def gray_map_of(skin):
    """옷의 무채색 토큰 → 인쇄 K 값. r≈g≈b 인 색만(유채색은 ICC 변환). 아주 어두우면 K100, 흰색은 0.

    옷에 `print.gray: {"#hex": k}` 가 있으면 그것을 얹는다 — 화면 표기값과 인쇄 값이 다른 색(ink #231f20 = K100).
    """
    out = {"#000000": 1.0, "#ffffff": 0.0}
    for hexv in (((skin or {}).get("tokens") or {}).get("color") or {}).values():
        try:
            r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        except (ValueError, TypeError):
            continue
        if max(r, g, b) - min(r, g, b) > 10:
            continue
        lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
        out[hexv.lower()] = 1.0 if lum < 0.16 else round(1.0 - lum, 2)
    out.update({str(k).lower(): float(v) for k, v in (((skin or {}).get("print") or {}).get("gray") or {}).items()})
    return out


def stamp_boxes(path, trim_w, trim_h, bleed, marks, log=None):
    """MediaBox(매체) 안에 BleedBox·TrimBox 를 박는다. 매체 = 재단 + 2×(도련 + 재단선 자리 5mm)."""
    import fitz
    doc = fitz.open(path)
    tw, th, b = float(trim_w) * PT, float(trim_h) * PT, float(bleed) * PT
    for pg in doc:
        mb = pg.mediabox                                             # 크로미움이 매체를 0.1mm 쯤 반올림한다 — 재단은 정확히 판형 크기로, 가운데에
        cx, cy = (mb.x0 + mb.x1) / 2, (mb.y0 + mb.y1) / 2
        trim = fitz.Rect(cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)
        pg.set_bleedbox(fitz.Rect(trim.x0 - b, trim.y0 - b, trim.x1 + b, trim.y1 + b) & mb)   # 재단선 없이(도련 = 매체)면 반올림만큼 매체 밖 — 매체 안으로
        pg.set_trimbox(trim)
    tmp = path + ".box"
    doc.save(tmp, garbage=3, deflate=True)
    n = doc.page_count
    doc.close()
    os.replace(tmp, path)
    if log:
        log(f"[인쇄] {n}p · 재단 {trim_w:g}×{trim_h:g}mm · 도련 {bleed:g}mm · TrimBox/BleedBox 박음")
    return n


def to_print_pdf(svgs, trim_w, trim_h, out_path, bleed=3.0, marks=True, skin=None, cmyk=True, title="인쇄", log=None):
    """인쇄용 PDF — 도련·재단선이 든 SVG(render.Ctx.print) → PDF → (Ghostscript 있으면) CMYK + 무채색은 K 단색 → 상자 박기.

    Returns {"pdf", "pages", "cmyk": bool, "note": str}
    """
    log = log or (lambda *_: None)
    m = float(bleed) + (5.0 if marks else 0.0)
    mw, mh = float(trim_w) + 2 * m, float(trim_h) + 2 * m
    rgb = out_path + ".rgb.pdf"
    to_pdf(svgs, mw, mh, rgb, title=title)
    note = ""
    done = False
    if cmyk:
        try:
            from core.render_vivlio import prepress
            prepress.make(rgb, out_path, bleed=m, gray_map=gray_map_of(skin), log=log)
            done = True
        except Exception as e:                                        # gs 없음·ICC 없음·글자층 불량
            note = f"CMYK 변환 못 함 — RGB 그대로 ({str(e).splitlines()[0][:160]})"
            log("[인쇄] " + note)
    if not done:
        os.replace(rgb, out_path)
    elif os.path.exists(rgb):
        os.remove(rgb)
    pages = stamp_boxes(out_path, trim_w, trim_h, bleed, marks, log=log)
    return {"pdf": out_path, "pages": pages, "cmyk": done, "note": note}
