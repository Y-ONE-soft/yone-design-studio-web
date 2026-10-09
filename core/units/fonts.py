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
