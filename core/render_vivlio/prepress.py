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

def default_print(gray_map=None, cmyk_map=None):
    """계열이 따로 표를 주지 않을 때의 `print` 절 — **인쇄 납품 규약의 바닥값**.

    규약(~/.claude/CLAUDE.md "비블리오 인쇄 납품 규약"): 별도 말이 없으면 모든
    조판은 인쇄용이다. 그래서 어떤 책이든 `print` 절이 없어도 이 표로 CMYK 를
    만든다. 계열은 `Series.print_defaults` 로 자기 팔레트의 무채색을 얹는다.
    """
    gray = {"#000000": 1.0, "#ffffff": 0.0}
    gray.update(DEFAULT_GRAY_MAP)
    gray.update({str(k).lower(): v for k, v in (gray_map or {}).items()})
    return {"out": "_인쇄", "profile": DEFAULT_PROFILES[0],
            "gray_map": gray,
            "cmyk_map": {str(k).lower(): list(v)
                         for k, v in (cmyk_map or {}).items()}}


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


def neutralize_patterns(doc, gray_map=None, tol=2, log=None, cmyk_map=None):
    """**그러데이션 배경**(머리 띠·괘선)의 색도 표대로 바꾼다.

    CSS `background: linear-gradient(색, 같은 색)` 은 PDF 에서 `rg` 가 아니라
    **축 셰이딩 패턴**(PatternType 2)이 된다. `neutralize()` 의 `rg` 정규식에
    안 걸려서 머리 띠만 ICC 변환을 타 **다른 색으로 나간다** — 완성본과 나란히
    놓으면 띠 색만 어긋난다.

    양 끝 색이 같은(= 단색인) 셰이딩만 손댄다. 진짜 그러데이션은 건드리지 않는다.
    """
    fitz = __import__("fitz")
    table = {k.lower(): v for k, v in (gray_map or DEFAULT_GRAY_MAP).items()}
    want = [(tuple(int(k[i:i + 2], 16) for i in (1, 3, 5)), v)
            for k, v in table.items()]
    spot = [(tuple(int(k.lower()[i:i + 2], 16) for i in (1, 3, 5)), v)
            for k, v in (cmyk_map or DEFAULT_CMYK_MAP).items()]
    n = 0
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=True)
        except Exception:
            continue
        if "/PatternType 2" not in obj and "/ShadingType" not in obj:
            continue
        base = "Shading/" if "/PatternType 2" in obj else ""
        cs = doc.xref_get_key(xref, base + "ColorSpace")
        if not cs or cs[1] != "/DeviceRGB":
            continue
        c0 = doc.xref_get_key(xref, base + "Function/C0")
        c1 = doc.xref_get_key(xref, base + "Function/C1")
        if not c0 or not c1 or c0[1] != c1[1]:
            continue            # 진짜 그러데이션 — 손대지 않는다
        try:
            rgb = [float(x) for x in c0[1].strip("[] ").split()]
        except ValueError:
            continue
        if len(rgb) != 3:
            continue
        c = [round(v * 255) for v in rgb]
        new_cs = new_val = None
        for ref, k in want:
            if all(abs(c[i] - ref[i]) <= tol for i in range(3)):
                new_cs, new_val = "/DeviceGray", "[ %.6g ]" % (1.0 - k)
                break
        if new_cs is None:
            for ref, v in spot:
                if all(abs(c[i] - ref[i]) <= tol for i in range(3)):
                    new_cs = "/DeviceCMYK"
                    new_val = "[ %s ]" % " ".join(
                        "%.6g" % (x / 100.0) for x in v)
                    break
        if new_cs is None:
            continue
        doc.xref_set_key(xref, base + "ColorSpace", new_cs)
        doc.xref_set_key(xref, base + "Function/C0", new_val)
        doc.xref_set_key(xref, base + "Function/C1", new_val)
        n += 1
    if log and n:
        log(f"[인쇄] 단색 그러데이션(머리 띠·괘선) {n}개 색 고정")
    return n


def pin_flat_images(doc, cmyk_map=None, gray_map=None, tol=6, log=None):
    """**단색 로고 이미지**의 색도 표대로 못 박는다.

    완성본에서 떠 온 아트워크(상표·로고)는 "한 가지 색 + 알파" 구조다. 이걸
    그대로 두면 ICC 변환을 타서 **같은 청록인데 로고만 다른 값**으로 나간다
    (실측 C75M15Y20 → 화면 #17a5c0 vs 로고 #2dacc0).

    색이 한 가지뿐이면 그림 자체는 **1×1 CMYK 한 점**으로 줄이고 투명도
    (SMask)는 그대로 둔다 — 결과는 "알파 마스크로 칠한 단색"이라 완전히 같다.
    """
    fitz = __import__("fitz")
    spot = {tuple(int(k.lower()[i:i + 2], 16) for i in (1, 3, 5)): v
            for k, v in (cmyk_map or DEFAULT_CMYK_MAP).items()}
    grays = {tuple(int(k.lower()[i:i + 2], 16) for i in (1, 3, 5)):
             [0, 0, 0, round(v * 100)]
             for k, v in (gray_map or DEFAULT_GRAY_MAP).items()}
    table = dict(grays)
    table.update(spot)
    if not table:
        return 0
    seen, done = set(), 0
    for page in doc:
        for info in page.get_images(full=True):
            xref, smask = info[0], info[1]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                pix = fitz.Pixmap(doc, xref)
            except Exception:
                continue
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.n != 3 or pix.width * pix.height == 0:
                continue
            # ⚠ **투명한 자리의 RGB 는 쓰레기다.** 브라우저가 알파를 풀어 쓰면서
            #   알파 0 인 화소를 0 이나 255 로 흘려 놓는다 — 그대로 최소·최대를
            #   재면 "여러 색"으로 보여 단색 로고를 못 알아본다. 불투명한 화소만 본다.
            alpha = None
            if smask:
                try:
                    ap = fitz.Pixmap(doc, smask)
                    if ap.n == 1 and ap.width == pix.width \
                            and ap.height == pix.height:
                        alpha = ap.samples
                except Exception:
                    alpha = None
            b = pix.samples
            npx = pix.width * pix.height
            step = max(1, npx // 20000)
            lo, hi = [255, 255, 255], [0, 0, 0]
            hits = 0
            for j in range(0, npx, step):
                if alpha is not None and alpha[j] < 200:
                    continue
                hits += 1
                for i in range(3):
                    v = b[j * 3 + i]
                    if v < lo[i]:
                        lo[i] = v
                    if v > hi[i]:
                        hi[i] = v
            if hits < 8 or any(hi[i] - lo[i] > tol for i in range(3)):
                continue                       # 여러 색 — 손대지 않는다
            c = [(lo[i] + hi[i]) // 2 for i in range(3)]
            hit = next((v for ref, v in table.items()
                        if all(abs(c[i] - ref[i]) <= tol for i in range(3))),
                       None)
            if hit is None:
                continue
            data = bytes(round(x * 255 / 100.0) for x in hit)
            doc.update_stream(xref, data, new=True, compress=False)
            for k, v in (("Width", "1"), ("Height", "1"),
                         ("ColorSpace", "/DeviceCMYK"),
                         ("BitsPerComponent", "8"),
                         ("Filter", "null"), ("DecodeParms", "null"),
                         ("Decode", "null")):
                try:
                    doc.xref_set_key(xref, k, v)
                except Exception:
                    pass
            if smask:
                doc.xref_set_key(xref, "SMask", "%d 0 R" % smask)
            done += 1
    if log and done:
        log(f"[인쇄] 단색 로고 그림 {done}개 색 고정")
    return done


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


_RE_BFR_BLK = re.compile(rb"(\d+)\s+beginbfrange(.*?)endbfrange", re.S)
_RE_BFR_ENT = re.compile(
    rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])")


def _split_bfrange(cm):
    """ToUnicode CMap 의 `bfrange` 중 **목적 끝 바이트가 FF 를 넘는 것**을 쪼갠다.

    PDF 규격: bfrange 는 목적 글자의 **끝 바이트만** 올린다. 크로미움은
    `<8E> <8F> <B2FF>` 처럼 끝 바이트가 넘치는 범위를 쓴다 — MuPDF 는 올림을
    받아 주어 `대`(B300)로 읽지만, 규격대로 읽는 Ghostscript 는 `눀`(B200)으로
    읽고 인쇄본에 그렇게 박는다(광문1 인쇄본 `대` 422자 중 328자, `밀`→`묀`).
    Returns (새 CMap, 쪼갠 범위 수).
    """
    n = 0

    def one_block(mo):
        nonlocal n
        ents = []
        for lo, hi, dst in _RE_BFR_ENT.findall(mo.group(2)):
            if dst.startswith(b"["):          # 배열 꼴은 그대로 둔다
                ents.append(b"<%s> <%s> %s" % (lo, hi, dst))
                continue
            a, b, v = int(lo, 16), int(hi, 16), int(dst[1:-1], 16)
            w, dw = len(lo), len(dst) - 2
            fmt = lambda x, y, z: (b"<%0*X> <%0*X> <%0*X>" % (w, x, w, y, dw, z))
            last = v & 0xFF
            if last + (b - a) <= 0xFF:
                ents.append(fmt(a, b, v))
                continue
            n += 1
            while a <= b:                       # 끝 바이트가 FF 에 닿는 자리마다 자른다
                span = min(b - a, 0xFF - (v & 0xFF))
                ents.append(fmt(a, a + span, v))
                a, v = a + span + 1, v + span + 1
        out = []
        for i in range(0, len(ents), 100):     # 규격: 한 블록에 100개까지
            chunk = ents[i:i + 100]
            out.append(b"%d beginbfrange\n%s\nendbfrange"
                       % (len(chunk), b"\n".join(chunk)))
        return b"\n".join(out) if out else mo.group(0)

    return _RE_BFR_BLK.sub(one_block, cm), n


def fix_tounicode(doc, log=None):
    """문서의 ToUnicode 전부에서 넘치는 bfrange 를 쪼갠다 → 고친 범위 수.

    ⚠ **Ghostscript 에 넘기기 전에** 해야 한다. 넘긴 뒤에는 이미 틀린 글자로
      굳어 있다(Ghostscript 가 자기 CMap 을 새로 쓴다).
    """
    done, total = set(), 0
    for x in range(1, doc.xref_length()):
        try:
            o = doc.xref_object(x, compressed=True) or ""
        except Exception:
            continue
        m = re.search(r"/ToUnicode\s+(\d+)\s+0\s+R", o)
        if not m or int(m.group(1)) in done:
            continue
        sx = int(m.group(1))
        done.add(sx)
        try:
            cm = doc.xref_stream(sx)
        except Exception:
            continue
        new, k = _split_bfrange(cm)
        if k:
            doc.update_stream(sx, new)
            total += k
    if total:
        (log or print)(f"[인쇄] 글자층 수리 — 끝 바이트가 넘치는 ToUnicode 범위 {total}개를 쪼갬")
    return total


def _hangul_bag(path):
    """PDF 글자층의 한글 음절 개수표 — 인쇄본이 글자를 바꿨는지 대조용."""
    import collections
    import fitz
    c = collections.Counter()
    d = fitz.open(path)
    try:
        for pg in d:
            c.update(ch for ch in pg.get_text() if "\uac00" <= ch <= "\ud7a3")
    finally:
        d.close()
    return c


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
    fix_tounicode(doc, log=log)
    n = neutralize(doc, gray_map, log=log, cmyk_map=cmyk_map)
    n += neutralize_patterns(doc, gray_map, log=log, cmyk_map=cmyk_map)
    n += pin_flat_images(doc, cmyk_map=cmyk_map, gray_map=gray_map, log=log)
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
    # ⚠ **인쇄본 글자층은 조판본과 한 글자도 달라서는 안 된다.** 변환이 글자를
    #   바꿔도 인쇄 모양은 멀쩡해 눈으로는 안 보이고, 검색·복사·검수 주석 회수만
    #   조용히 틀린다(광문1: `대`→`눀` 328곳, 2차 검수본까지 그대로). 다르면 그
    #   파일을 `_불량` 으로 떼어 내고 멈춘다 — 최신처럼 보이는 불량본을 남기지 않는다.
    a_, b_ = _hangul_bag(src), _hangul_bag(dst)
    diff = {ch: (a_[ch], b_[ch]) for ch in set(a_) | set(b_) if a_[ch] != b_[ch]}
    if diff:
        bad = dst[:-4] + "_불량.pdf"
        os.replace(dst, bad)
        show = " ".join("%s %d→%d" % (ch, x, y) for ch, (x, y)
                        in sorted(diff.items(), key=lambda kv: -abs(kv[1][0] - kv[1][1]))[:8])
        raise RuntimeError(f"인쇄본 글자층이 조판본과 다르다({len(diff)}자: {show}) — "
                           f"납품 금지, {os.path.basename(bad)} 로 떼어 냄")
    log("[인쇄] 글자층 대조 — 조판본과 같음(한글 %d자)" % sum(a_.values()))
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
