"""인쇄 원고 만들기 — RGB 조판 결과 → CMYK PDF (고품질 인쇄).

조판 백엔드(Vivliostyle/Skia)는 **무조건 DeviceRGB 로 쓴다.** 순수 검정을 넣어도
`0 0 0 rg` 다. 이걸 그대로 ICC 로 CMYK 변환하면 본문 먹이 **C80 M80 Y77 K60 리치
블랙**이 된다 — 7pt 본문에 4도 먹을 쓰면 핀 어긋남으로 글자가 뭉갠다. 실제 납품본
(InDesign)은 본문이 **K100 단색**이고 회색도 K70·K50 단색이다.

그래서 두 단계로 나눈다.

  ① 먹·회색만 **DeviceGray 로 미리 바꾼다**(`gray_map`).
     Ghostscript 는 DeviceGray 를 CMYK 로 변환하지 않고 **그대로 둔다** — RIP 에서
     K 단색으로 나간다(실측 확인). 화면 표기값(#231f20)과 인쇄 값(K100)이 다르므로
     자동 판정하지 않고 **표를 명시**한다.
  ② 나머지(유채색·이미지·그러데이션·투명)는 Ghostscript 가 ICC 로 변환한다.

TrimBox/BleedBox 는 Ghostscript 가 흘려버리므로 **마지막에 다시 찍는다**
(→ `bleed.stamp_trimbox`). 도련은 조판 단계에서 이미 들어가 있다.
"""
import os
import re
import shutil
import subprocess

PT = 72 / 25.4

# 화면 표기색 → 인쇄 CMYK(0~100). 이전 판과 **색을 정확히 맞춰야 하는** 색만 넣는다.
# ICC 변환은 값이 미묘하게 달라지므로, 지정한 색은 아예 변환을 거치지 않게 한다.
DEFAULT_CMYK_MAP = {}

# 화면 표기색 → K 비율. 조판 팔레트의 무채색을 인쇄 값으로 옮기는 표다.
DEFAULT_GRAY_MAP = {
    "#231f20": 1.00,     # 본문 먹  (완성본 K100)
    "#6d6e71": 0.70,     # 품사     (완성본 K70)
    "#939598": 0.50,     # 발음기호 (완성본 K50)
    "#ffffff": 0.00,     # 흰 글자·흰 도형 — 0% 로 확실히 빼 둔다
}

# 인쇄용 CMYK 프로파일 후보 (앞에서부터). 한국 상업 인쇄 관행상 Japan Color 우선.
PROFILE_DIRS = ("/Library/Application Support/Adobe/Color/Profiles/Recommended",
                "/System/Library/ColorSync/Profiles",
                "/Library/ColorSync/Profiles")
DEFAULT_PROFILES = ("JapanColor2001Coated.icc", "USWebCoatedSWOP.icc",
                    "CoatedFOGRA39.icc")

_RE_RG = re.compile(rb"(?<![\w.])(\d*\.?\d+)\s+(\d*\.?\d+)\s+(\d*\.?\d+)\s+(rg|RG)(?![A-Za-z])")


def find_profile(name=None):
    """ICC 경로. 이름을 주면 그것만, 없으면 기본 후보를 앞에서부터."""
    names = [name] if name else list(DEFAULT_PROFILES)
    for n in names:
        if n and os.path.isabs(n) and os.path.exists(n):
            return n
        for d in PROFILE_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def _hex(r, g, b):
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def neutralize(doc, gray_map=None, tol=2, log=None, cmyk_map=None):
    """`r g b rg|RG` 를 표대로 `gray g|G`(무채색) 또는 `c m y k k`(지정색)로 바꾼다.

    tol 은 8비트 채널 허용 오차 — 조판 결과의 반올림(0.137255 …)을 흡수한다.
    `cmyk_map` 은 **이전 판과 정확히 같아야 하는 색**용이다(예: 예문 강조어를
    완성본과 동일한 C0 M56 Y64 로). 여기 넣은 색은 ICC 변환을 타지 않는다.
    """
    table = {k.lower(): v for k, v in (gray_map or DEFAULT_GRAY_MAP).items()}
    want = [(tuple(int(k[i:i + 2], 16) for i in (1, 3, 5)), v)
            for k, v in table.items()]
    spot = [(tuple(int(k.lower()[i:i + 2], 16) for i in (1, 3, 5)), v)
            for k, v in (cmyk_map or DEFAULT_CMYK_MAP).items()]
    n = 0

    def sub(m):
        nonlocal n
        try:
            rgb = [float(m.group(i)) for i in (1, 2, 3)]
        except ValueError:
            return m.group(0)
        c = [round(v * 255) for v in rgb]
        for ref, k in want:
            if all(abs(c[i] - ref[i]) <= tol for i in range(3)):
                n += 1
                op = b"g" if m.group(4) == b"rg" else b"G"
                return b"%s %s" % (f"{1.0 - k:.6g}".encode(), op)
        for ref, v in spot:
            if all(abs(c[i] - ref[i]) <= tol for i in range(3)):
                n += 1
                op = b"k" if m.group(4) == b"rg" else b"K"
                vals = " ".join(f"{x / 100.0:.6g}" for x in v)
                return b"%s %s" % (vals.encode(), op)
        return m.group(0)

    seen = set()
    for page in doc:
        for xref in page.get_contents():
            if xref in seen:
                continue
            seen.add(xref)
            data = doc.xref_stream(xref)
            if not data:
                continue
            out = _RE_RG.sub(sub, data)
            if out != data:
                doc.update_stream(xref, out)
        # 폼 XObject 안에도 색 연산자가 있을 수 있다
        for item in page.get_xobjects():
            xref = item[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                data = doc.xref_stream(xref)
            except Exception:
                continue
            if not data:
                continue
            out = _RE_RG.sub(sub, data)
            if out != data:
                doc.update_stream(xref, out)
    if log:
        note = ", ".join(f"{k}=K{int(v * 100)}" for k, v in table.items())
        if cmyk_map:
            note += " | " + ", ".join(
                f"{k}=C{v[0]:g}M{v[1]:g}Y{v[2]:g}K{v[3]:g}"
                for k, v in cmyk_map.items())
        log(f"[인쇄] 색 고정 {n}곳 ({note})")
    return n


_RE_GS = re.compile(rb"/([A-Za-z0-9]+)\s+gs")


def _alpha_zero_names(doc, page):
    """이 면의 ExtGState 중 `ca == 0`(완전 투명)인 이름들."""
    eg = doc.xref_get_key(page.xref, "Resources/ExtGState")
    if not eg or eg[0] not in ("dict", "xref"):
        return set()
    body = eg[1] if eg[0] == "dict" else doc.xref_object(int(eg[1].split()[0]))
    out = set()
    for m in re.finditer(r"/(\w+)\s+(?:(\d+)\s+0\s+R|<<(.*?)>>)", body, re.S):
        d = m.group(3) or doc.xref_object(int(m.group(2)))
        if re.search(r"/ca\s+0(?![\d.])", d):
            out.add(m.group(1).encode())
    return out


def strip_invisible(doc, log=None):
    """`ca 0` (잉크가 전혀 안 나가는) 그리기를 지운다.

    2패스용 DAYOPEN 마커가 `color: transparent` 라 **완전 투명한 검정 글자**로 남는다.
    잉크는 안 나가지만 인쇄 원고 색 점검에 리치블랙으로 잡히고 투명도까지 끌고
    들어와, 인쇄소 프리플라이트에서 불필요한 확인이 생긴다.

    ⚠ `/Gxx gs` 는 **자기 q/Q 블록 안에 있지 않다.** 클리핑 블록 한가운데서 상태만
    바꾸고 바로 뒤 `/G3 gs` 가 되돌린다 — 앞쪽 `q` 를 찾아 통째로 지우면 같은 블록에
    있는 **보이는 내용까지 날아간다**(실측). 그래서 "색 지정 + gs + 바로 뒤 BT…ET"
    딱 그만큼만 지운다. 호출한 쪽이 지우기 전후 렌더를 비교해 안전망을 건다(→ `make`).
    """
    n = 0
    for page in doc:
        names = _alpha_zero_names(doc, page)
        if not names:
            continue
        pat = re.compile(
            rb"(?:(?:[\d.]+\s+){3}(?:RG|rg)\s*){0,2}"      # 앞선 색 지정(있으면)
            rb"/(" + b"|".join(re.escape(x) for x in sorted(names)) + rb")\s+gs"
            rb"(?:(?!\bgs\b).)*?\bET\b",                   # 다음 gs 전까지의 BT…ET
            re.S)
        for xref in page.get_contents():
            data = doc.xref_stream(xref)
            if not data:
                continue
            out, cnt = pat.subn(b"", data)
            if cnt:
                doc.update_stream(xref, out)
                n += cnt
    if log and n:
        log(f"[인쇄] 완전 투명(잉크 0) 그리기 {n}곳 제거")
    return n


def run_gs(src, dst, profile=None, log=None, timeout=900):
    """Ghostscript 로 CMYK 변환(고품질 인쇄). DeviceGray 는 건드리지 않는다."""
    gs = shutil.which("gs")
    if not gs:
        raise RuntimeError("Ghostscript(gs) 없음 — `brew install ghostscript`")
    cmd = [gs, "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER",
           "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/prepress",
           "-dCompatibilityLevel=1.4",
           "-sColorConversionStrategy=CMYK", "-dProcessColorModel=/DeviceCMYK",
           "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dCompressFonts=true",
           # 이미지는 300dpi 아래로 깎지 않는다(고품질 인쇄)
           "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false",
           "-dDownsampleMonoImages=false",
           "-dAutoFilterColorImages=false", "-dAutoFilterGrayImages=false",
           "-dColorImageFilter=/FlateEncode", "-dGrayImageFilter=/FlateEncode",
           "-dDetectDuplicateImages=true"]
    if profile:
        # ⚠ `-dSAFER` 는 입출력 밖 파일 읽기를 막는다 — ICC 는 대개 시스템 폴더에
        #    있어 그냥 두면 "Permission denied" 로 죽는다. 그 파일만 열어 준다.
        cmd += [f"--permit-file-read={profile}",
                f"-sOutputICCProfile={profile}"]
    cmd += ["-sOutputFile=" + dst, src]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    msg = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode != 0:
        raise RuntimeError(f"gs 변환 실패 (exit {p.returncode})\n{msg[-2000:]}")
    if msg and log:
        log(f"[gs] {msg[-500:]}")
    return dst


def make(src, dst, bleed=3.0, profile=None, gray_map=None, log=None,
         cmyk_map=None):
    """RGB 조판본 → CMYK 인쇄 원고. Returns: {"pdf", "gray_ops", "profile"}."""
    import fitz

    log = log or print
    icc = find_profile(profile)
    if profile and not icc:
        log(f"[경고] ICC 프로파일 못 찾음: {profile} — 기본 변환으로 진행")

    # ① 무채색 → DeviceGray
    tmp_gray = dst + ".gray.pdf"
    doc = fitz.open(src)
    n = neutralize(doc, gray_map, log=log, cmyk_map=cmyk_map)
    doc.save(tmp_gray, garbage=3, deflate=True)
    doc.close()

    # ② 잉크 0 블록 제거 — **①의 결과와** 비교해야 한다(①은 색을 바꾸므로)
    tmp_rgb = tmp_gray
    doc = fitz.open(tmp_gray)
    if strip_invisible(doc, log=log):
        tmp_strip = dst + ".strip.pdf"
        doc.save(tmp_strip, garbage=3, deflate=True)
        doc.close()
        if _same_render(tmp_gray, tmp_strip):
            tmp_rgb = tmp_strip
        else:
            log("[경고] 투명 블록 제거가 지면을 바꿨다 — 제거하지 않고 진행")
            os.remove(tmp_strip)
    else:
        doc.close()

    tmp_cmyk = dst + ".cmyk.pdf"
    try:
        run_gs(tmp_rgb, tmp_cmyk, icc, log=log)
        # ⚠ Ghostscript 는 TrimBox/BleedBox 를 흘려버린다 → 마지막에 다시 찍는다
        from core.render_vivlio import bleed as bleed_mod
        doc = fitz.open(tmp_cmyk)
        stamp_boxes(doc, bleed)
        tmp = dst + ".tmp"
        doc.save(tmp, garbage=3, deflate=True)
        pages = doc.page_count
        doc.close()
        os.replace(tmp, dst)
    finally:
        for f in (tmp_gray, tmp_rgb, tmp_cmyk):
            if os.path.exists(f):
                os.remove(f)
    log(f"[인쇄] {pages}p · CMYK({os.path.basename(icc) if icc else '기본'}) · "
        f"도련 {bleed}mm → {os.path.basename(dst)}")
    return {"pdf": dst, "pages": pages, "gray_ops": n, "profile": icc}


def _same_render(a, b, dpi=120):
    """두 PDF 를 렌더해 픽셀이 같은지. 투명 블록 제거의 안전망."""
    import fitz
    da, db = fitz.open(a), fitz.open(b)
    try:
        if da.page_count != db.page_count:
            return False
        for i in range(da.page_count):
            if (da[i].get_pixmap(dpi=dpi).samples
                    != db[i].get_pixmap(dpi=dpi).samples):
                return False
        return True
    finally:
        da.close()
        db.close()


def stamp_boxes(doc, bleed=3.0):
    """BleedBox = MediaBox(도련 포함), TrimBox = 사방 `bleed` 안쪽."""
    import fitz
    for pg in doc:
        mb = pg.mediabox
        pg.set_bleedbox(fitz.Rect(mb.x0, mb.y0, mb.x1, mb.y1))
        pg.set_trimbox(fitz.Rect(mb.x0 + bleed * PT, mb.y0 + bleed * PT,
                                 mb.x1 - bleed * PT, mb.y1 - bleed * PT))
    return doc.page_count


def audit(path, limit=14):
    """인쇄 원고 점검 — 색공간·상자·서체를 사람이 읽는 형태로."""
    import collections
    import fitz

    doc = fitz.open(path)
    ops = collections.Counter()
    colors = collections.Counter()
    for pg in doc:
        cs = pg.read_contents().decode("latin-1", "ignore")
        for m in re.finditer(r"(?m)(?:^|\s)(rg|RG|g|G|k|K)(?=\s|$)", cs):
            ops[m.group(1)] += 1
        for m in re.finditer(r"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) k(?=\s)", cs):
            colors[tuple(round(float(x) * 100, 1) for x in m.groups())] += 1
        for m in re.finditer(r"(?m)(?:^|\s)([\d.]+)\s+g(?=\s|$)", cs):
            colors[("K", round((1 - float(m.group(1))) * 100, 1))] += 1
    p0 = doc[0]
    out = {
        "pages": doc.page_count,
        "media_mm": [round(v / PT, 2) for v in p0.mediabox],
        "trim_mm": [round(v / PT, 2) for v in p0.trimbox],
        "bleed_mm": [round(v / PT, 2) for v in p0.bleedbox],
        "ops": dict(ops),
        "rgb_left": ops.get("rg", 0) + ops.get("RG", 0),
        "colors": colors.most_common(limit),
        "fonts": sorted({f[3] for pg in doc for f in pg.get_fonts(full=True)}),
    }
    doc.close()
    return out
