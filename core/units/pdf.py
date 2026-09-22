"""지면 SVG 들 → PDF. 크로미움 헤드리스 인쇄(--print-to-pdf). 비블리오처럼 저장이 PDF 다.

브라우저: `YONE_VIV_BROWSER`(컨테이너 /usr/bin/chromium) → 이 맥의 크롬 → PATH 의 chromium/google-chrome.
서체는 브라우저가 가진 것으로 그린다 — 없는 서체는 폴백(컨테이너는 fonts-noto-cjk).
"""
import os
import shutil
import subprocess
import tempfile

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


def html_of(svgs, w_mm, h_mm, title="지면"):
    """면마다 한 장. @page 크기 = 판형, 여백 0. SVG 는 width/height 가 mm 로 박혀 있다."""
    pages = "".join(f'<div class="p">{s["svg"] if isinstance(s, dict) else s}</div>' for s in svgs)
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>'
            f'@page{{size:{w_mm}mm {h_mm}mm;margin:0}} html,body{{margin:0;padding:0}} '
            f'.p{{width:{w_mm}mm;height:{h_mm}mm;overflow:hidden;page-break-after:always;break-after:page}} '
            f'.p svg{{display:block;width:{w_mm}mm;height:{h_mm}mm}} .p svg .zone{{display:none}}'
            f'</style></head><body>{pages}</body></html>')


def to_pdf(svgs, w_mm, h_mm, out_path, title="지면", timeout=180):
    """svgs → PDF 파일. 브라우저가 없으면 RuntimeError."""
    b = browser()
    if not b:
        raise RuntimeError("크로미움이 없다 — YONE_VIV_BROWSER 또는 크롬 설치")
    d = tempfile.mkdtemp(prefix="units_pdf_")
    html = os.path.join(d, "index.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(html_of(svgs, w_mm, h_mm, title))
    # ⚠ --user-data-dir 를 주면 이 맥의 크롬이 멎는다(첫 실행 프로필 준비에서) — 실측. 플래그는 최소로.
    cmd = [b, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
           "--virtual-time-budget=3000", f"--print-to-pdf={out_path}", "file://" + html]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 100:
        raise RuntimeError("PDF 가 안 나왔다: " + (r.stderr or r.stdout or "")[-400:])
    shutil.rmtree(d, ignore_errors=True)
    return out_path
