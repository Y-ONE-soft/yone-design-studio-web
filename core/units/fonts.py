"""서체 굵기 바로잡기 — 스타일 이름(Medium·Bold…)으로 서체 파일을 고르게 한다(인디자인처럼).

크롬은 font-weight 를 서체 파일의 굵기 값(OS/2 usWeightClass)으로 맞춘다. 그 값이 스타일 이름과 어긋난 서체가 있다 —
이 맥의 Gmarket Sans(OTF)는 Light 300 · Medium 400 · Bold 500 이라 굵기 500(Medium)을 고르면 Bold 파일이 나왔다.
설치된 서체를 fc-list 로 읽어, 스타일 이름의 굵기로 골랐을 때 다른 파일이 걸리는 집안만 @font-face(local)로
스타일 이름 굵기에 다시 묶는다. 어긋나지 않은 집안(Noto CJK 등)은 건드리지 않는다.
"""
import functools
import os
import shutil
import subprocess

# 스타일 이름 → CSS 굵기 (긴 이름 먼저)
_STYLE_W = (("extralight", 200), ("ultralight", 200), ("semibold", 600), ("demibold", 600), ("extrabold", 800),
            ("ultrabold", 800), ("demilight", 350), ("hairline", 100), ("thin", 100), ("light", 300), ("medium", 500),
            ("bold", 700), ("black", 900), ("heavy", 900), ("regular", 400), ("normal", 400), ("book", 400), ("roman", 400))
# fontconfig 굵기 → CSS 굵기 (FcWeightToOpenType 표)
_FC_CSS = ((0, 100), (40, 200), (50, 300), (55, 350), (75, 380), (80, 400), (100, 500), (180, 600), (200, 700), (205, 800), (210, 900), (215, 1000))


def _style_weight(style):
    """스타일 이름이 굵기 낱말뿐일 때만(Medium · Bold Italic …) 그 굵기 — 폭·변형이 붙은 스타일(Light Condensed · Bold G1)은 None"""
    s = style.lower().replace(" ", "").replace("-", "").replace("italic", "").replace("oblique", "")
    if not s:
        return 400
    return dict(_STYLE_W).get(s)


def _fc_css(fw):
    for (a, x), (b, y) in zip(_FC_CSS, _FC_CSS[1:]):
        if a <= fw <= b:
            return x + (y - x) * (fw - a) / (b - a)
    return 400.0


def _match(want, have):
    """CSS 굵기 맞추기(CSS Fonts 4) — have 중 고를 굵기"""
    if want in have:
        return want
    up = sorted(w for w in have if w > want)
    down = sorted((w for w in have if w < want), reverse=True)
    if 400 <= want <= 500:
        mid = [w for w in up if w <= 500]
        return (mid or down or up)[0]
    return ((down or up) if want < 400 else (up or down))[0]


def _fc_list():
    exe = shutil.which("fc-list") or next((p for p in ("/opt/homebrew/bin/fc-list", "/usr/local/bin/fc-list", "/usr/bin/fc-list") if os.path.exists(p)), None)
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "-f", "%{family[0]}|%{style[0]}|%{postscriptname}|%{fullname[0]}|%{weight}\\n"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for ln in out.splitlines():
        p = ln.split("|")
        if len(p) == 5 and p[0] and p[4].replace(".", "").isdigit():
            rows.append(p)
    return rows


@functools.lru_cache(maxsize=1)
def fix_css():
    """어긋난 집안의 @font-face 규칙(문자열). 없으면 빈 문자열."""
    fams = {}
    for fam, style, ps, full, fw in _fc_list():
        if fam.startswith("."):                                                 # 맥 시스템 내부 서체 — 이름으로 못 쓴다
            continue
        w = _style_weight(style)
        if w is None:
            continue
        it = "italic" in style.lower() or "oblique" in style.lower()
        fams.setdefault((fam, it), []).append((w, _fc_css(float(fw)), ps, full))
    css = []
    for (fam, it), faces in sorted(fams.items()):
        have = {}
        for w, real, ps, full in faces:
            have.setdefault(real, (w, ps, full))
        if all(abs(have[_match(w, list(have))][0] - w) < 200 for w, _, _, _ in faces):
            continue                                                        # 스타일 이름 굵기로 고르면 그 파일(또는 바로 옆 굵기)이 걸린다 — 그대로
        seen = set()
        for w, _, ps, full in sorted(faces):
            if w in seen:
                continue
            seen.add(w)
            src = ",".join(f'local("{n}")' for n in (ps, full) if n)
            css.append(f'@font-face{{font-family:"{fam}";font-weight:{w};font-style:{"italic" if it else "normal"};src:{src}}}')
    return "".join(css)


# ── 시스템 서체 (2026-10-10) ──────────────────────────────────────────────
# 편집기·PDF 는 **시스템 서체만** 쓴다 — 컴퓨터에 깔린 서체에 기대면 이 맥에서만 맞고 서버에선 다르게 나온다.
# 시스템 서체 = ① 시스템이 함께 싣는 서체(디자인 config 의 fonts + 계열 코드의 FONTS — 서버 서체 묶음 deploy/fonts-pack.sh 와 같은 목록)
#              ② 편집기에서 올려 등록한 서체(catalog/_fonts/ — 서버는 /data/catalog/_fonts)
# 그리기는 이 파일들을 @font-face 로 직접 부른다(face_css). 편집기 서체 칸은 이 목록에서만 고른다. 검사는 목록 밖 서체를 실패로.
FONT_EXT = (".otf", ".ttf")


def store_dir():
    from routes.catalog import CATALOG
    return os.path.join(CATALOG, "_fonts")


def pack_files():
    """시스템이 함께 싣는 서체 파일 이름 — 디자인 config fonts + 계열 코드 FONTS (deploy/fonts-pack.sh 와 같은 출처)"""
    import glob
    import json
    import re
    from routes.catalog import CATALOG
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    want = set()
    for p in glob.glob(os.path.join(CATALOG, "**", "config.json"), recursive=True):
        try:
            c = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for f in c.get("fonts") or []:
            fn = f.get("file") if isinstance(f, dict) else f
            if isinstance(fn, str) and fn.lower().endswith(FONT_EXT):
                want.add(os.path.basename(fn))
    for p in glob.glob(os.path.join(repo, "core", "render_vivlio", "series", "*", "*.py")):
        want.update(re.findall(r'"([^"/]+\.(?:otf|ttf|OTF|TTF))"', open(p, encoding="utf-8").read()))
    return sorted(want)


def _meta(path):
    """서체 파일 → (집 이름, 굵기, 기울임) — 이름표(ID16·ID1, ID17·ID2)에서. 굵기는 스타일 이름으로(인디자인처럼)"""
    from fontTools.ttLib import TTFont
    try:
        f = TTFont(path, lazy=True, fontNumber=0)
        nm = f["name"]
    except Exception:
        return None

    def name(*ids):
        for i in ids:
            for r in nm.names:
                if r.nameID == i:
                    try:
                        s = r.toUnicode().strip()
                    except Exception:
                        continue
                    if s and s.isascii():
                        return s
        for i in ids:                                                   # 한글 이름만 있는 서체 — 그 이름 그대로
            for r in nm.names:
                if r.nameID == i:
                    try:
                        s = r.toUnicode().strip()
                    except Exception:
                        continue
                    if s:
                        return s
        return ""
    fam, sty = name(16, 1), name(17, 2) or "Regular"
    w = _style_weight(sty)
    if w is None:
        try:
            w = int(f["OS/2"].usWeightClass)
        except Exception:
            w = 400
    return fam, w, "italic" in sty.lower() or "oblique" in sty.lower()


_SYS = {}


def system_fonts():
    """→ [{file, path, family, weight, italic, src: "pack"|"upload"}] — 못 찾은 묶음 서체는 빠진다(missing_pack)"""
    from core.render_vivlio.stage import find_font
    sd = store_dir()
    up = sorted(n for n in (os.listdir(sd) if os.path.isdir(sd) else []) if n.lower().endswith(FONT_EXT))
    key = (tuple(pack_files()), tuple((n, os.path.getmtime(os.path.join(sd, n))) for n in up))
    if _SYS.get("key") == key:
        return _SYS["fonts"]
    out = []
    for n in key[0]:
        p = find_font(n)
        m = _meta(p) if p else None
        if m:
            out.append({"file": n, "path": p, "family": m[0], "weight": m[1], "italic": m[2], "src": "pack"})
    for n in up:
        p = os.path.join(sd, n)
        m = _meta(p)
        if m:
            out.append({"file": n, "path": p, "family": m[0], "weight": m[1], "italic": m[2], "src": "upload"})
    _SYS.update(key=key, fonts=out)
    return out


def missing_pack():
    from core.render_vivlio.stage import find_font
    return [n for n in pack_files() if not find_font(n)]


def families():
    """→ {집 이름: [굵기…]} — 편집기 서체 칸 목록"""
    fams = {}
    for f in system_fonts():
        fams.setdefault(f["family"], set()).add(f["weight"])
    return {k: sorted(v) for k, v in sorted(fams.items())}


def faces():
    """→ {집 이름: ["400", "400i", "700", …]} — 인디자인 글꼴 스타일 목록(굵기 + 기울임꼴)"""
    out = {}
    for f in system_fonts():
        out.setdefault(f["family"], set()).add(f"{f['weight']}{'i' if f['italic'] else ''}")
    return {k: sorted(v, key=lambda x: (int(x.rstrip("i")), x.endswith("i"))) for k, v in sorted(out.items())}


def face_css(mode="url"):
    """시스템 서체 @font-face — 컴퓨터에 깔린 서체 대신 이 파일을 쓴다. mode url = 편집기(서버 주소) · file = PDF(파일 주소)"""
    css = []
    for f in system_fonts():
        src = f"url('/api/units/fontfile/{f['file']}')" if mode == "url" else f"url('file://{safe_path(f['path'])}')"
        fmt = "opentype" if f["file"].lower().endswith(".otf") else "truetype"
        css.append(f'@font-face{{font-family:"{f["family"]}";font-weight:{f["weight"]};font-style:{"italic" if f["italic"] else "normal"};'
                   f'src:{src} format("{fmt}");font-display:block}}')
    return "".join(css)


def font_file(name):
    """등록된 서체 파일의 경로 — 목록에 없는 이름은 None (아무 파일이나 내주지 않는다)"""
    p = next((f["path"] for f in system_fonts() if f["file"] == name), None)
    return safe_path(p) if p else None                                  # 크롬 서체 검사(OTS)에 걸리는 곳을 고친 사본


def _cff_ascii_names(data):
    """CFF 서체 이름(Name INDEX)이 영문이 아니면 같은 길이의 영문으로 — 크롬 서체 검사(OTS)가 「CFF : Failed to parse table」로
    파일째 거부한다(하늘보리체 SKYBORI.otf 의 이름이 UTF-8 한글, 2026-10-11). 맥은 같은 이름의 설치 서체로 대신 그려 몰랐고
    배포서버는 대체 서체(DejaVu)로 나왔다. 같은 길이로 바꾸니 다른 자리(오프셋)는 그대로다. 고칠 것이 없으면 data 그대로."""
    import struct
    try:
        if data[:4] != b"OTTO":
            return data
        n = struct.unpack(">H", data[4:6])[0]
        rec = next((struct.unpack(">II", data[12 + 16 * i + 8:12 + 16 * i + 16]) for i in range(n)
                    if data[12 + 16 * i:12 + 16 * i + 4] == b"CFF "), None)
        if not rec:
            return data
        off = rec[0]
        p = off + data[off + 2]                                          # 머리(hdrSize) 다음이 Name INDEX
        count, osz = struct.unpack(">H", data[p:p + 2])[0], data[p + 2]
        offs = [int.from_bytes(data[p + 3 + k * osz:p + 3 + (k + 1) * osz], "big") for k in range(count + 1)]
        base = p + 3 + (count + 1) * osz - 1
        out = bytearray(data)
        for k in range(count):
            a, b = base + offs[k], base + offs[k + 1]
            if all(33 <= c <= 126 and chr(c) not in "[](){}<>/%" for c in data[a:b]):
                continue
            out[a:b] = (b"Font" + b"_" * (b - a))[:b - a]
        return bytes(out)
    except (struct.error, IndexError, ValueError):
        return data


def _kern_len_fix(data):
    """옛 kern 표(버전 0 · 형식 0)의 부분 표 길이가 실제보다 크게 적힌 TTF — 크롬 서체 검사(OTS)가 파일째 거부한다
    (12롯데마트드림Bold: 65530 · 실제 5120, 2026-10-14 — 맥은 설치 서체로 대신 그려 몰랐고 배포서버는 DejaVu 로 나왔다).
    길이 칸만 14 + 쌍 수 × 6 으로 바로 적는다(커닝 값은 그대로). 고칠 것이 없으면 data 그대로."""
    import struct
    try:
        n = struct.unpack(">H", data[4:6])[0]
        rec = next((struct.unpack(">II", data[12 + 16 * i + 8:12 + 16 * i + 16]) for i in range(n)
                    if data[12 + 16 * i:12 + 16 * i + 4] == b"kern"), None)
        if not rec:
            return data
        off, size = rec
        ver, cnt = struct.unpack(">HH", data[off:off + 4])
        if ver != 0:
            return data
        out, p = bytearray(data), off + 4
        for _ in range(cnt):
            ln, cov = struct.unpack(">HH", data[p + 2:p + 6])
            if cov >> 8 != 0:                                            # 형식 0 만
                return data
            need = 14 + struct.unpack(">H", data[p + 6:p + 8])[0] * 6
            if ln != need and p + need <= off + size:
                out[p + 2:p + 4] = struct.pack(">H", need)
            p += need
        return bytes(out)
    except (struct.error, IndexError, ValueError):
        return data


_SAFE = {}


def safe_path(path):
    """그릴 때 쓰는 서체 파일 — 크롬 서체 검사(OTS)에 걸리는 곳을 고친 사본(임시 폴더), 고칠 것이 없으면 그 파일 그대로.
    파일마다 한 번만 읽는다(경로 · 수정 시각이 같으면 앞 결과)"""
    import hashlib
    import tempfile
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return path
    if key in _SAFE and os.path.exists(_SAFE[key]):
        return _SAFE[key]
    data = open(path, "rb").read()
    fixed = _kern_len_fix(_cff_ascii_names(data))
    out = path
    if fixed != data:
        d = os.path.join(tempfile.gettempdir(), "yone-fonts-ots")
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, hashlib.sha1(fixed).hexdigest()[:12] + os.path.splitext(path)[1].lower())
        if not os.path.exists(out):
            with open(out, "wb") as fh:
                fh.write(fixed)
    _SAFE[key] = out
    return out


def register(filename, data):
    """서체 올려 등록 — catalog/_fonts/ 에 두고 목록에 든다. → 등록된 항목(같은 파일 이름이면 덮어씀)"""
    base = os.path.basename(filename or "").strip()
    if not base.lower().endswith(FONT_EXT) or base.startswith("."):
        raise ValueError("OTF·TTF 서체 파일만")
    data = _cff_ascii_names(data)
    sd = store_dir()
    os.makedirs(sd, exist_ok=True)
    path = os.path.join(sd, base)
    with open(path, "wb") as fh:
        fh.write(data)
    m = _meta(path)
    if not m:
        os.remove(path)
        raise ValueError("서체 파일을 읽지 못했다")
    _SYS.clear()
    return {"file": base, "family": m[0], "weight": m[1], "italic": m[2]}
