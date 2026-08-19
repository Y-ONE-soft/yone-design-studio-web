"""빌드 디렉터리 배치 — 서체 / 테마 / 자산.

서체는 **리포에 넣지 않는다**(라이선스·용량). 로컬 설치본을 빌드 디렉터리로
복사해 `@font-face src: url("fonts/…")` 로 임베드한다. 그래서 서체는 '이름 목록'만
config 에 두고, 실제 파일은 여기서 찾는다.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(HERE, "themes")

# 로컬 서체 탐색 경로 (앞에서부터)
FONT_DIRS = [
    os.path.expanduser("~/Library/Fonts"),
    "/Library/Fonts",
    "/System/Library/Fonts",
]


def find_font(name):
    """서체 파일명(또는 절대경로/틸데경로) → 실제 경로 또는 None."""
    if os.sep in name or name.startswith("~"):
        p = os.path.expanduser(name)
        return p if os.path.exists(p) else None
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def stage_fonts(build_dir, fonts, log=None, required=True):
    """`fonts` (파일명 목록) → build_dir/fonts/. 변경분만 복사.

    required=True 면 하나라도 없을 때 예외(블랙북 정책 — 서체가 빠지면 판면이
    통째로 달라진다). False 면 경고만 하고 진행(상일보카 정책).
    Returns: 없는 서체 이름 목록.
    """
    fdir = os.path.join(build_dir, "fonts")
    os.makedirs(fdir, exist_ok=True)
    missing = []
    for name in fonts or ():
        src = find_font(name)
        base = os.path.basename(name)
        if src is None:
            missing.append(base)
            continue
        dst = os.path.join(fdir, base)
        if (not os.path.exists(dst)
                or os.path.getmtime(src) > os.path.getmtime(dst)):
            shutil.copy2(src, dst)
    if missing:
        msg = f"[서체 없음] {', '.join(missing)}"
        if required:
            raise FileNotFoundError(
                msg + f"\n  탐색 경로: {', '.join(FONT_DIRS)}")
        (log or print)(f"[경고] {msg} — 대체 폴백으로 진행")
    return missing


def stage_theme(build_dir, theme, log=None):
    """`themes/<theme>.css` → build_dir/theme.css (+ 공통 골격 `_base.css`).

    theme 이 절대경로/실파일이면 그 파일을 그대로 쓴다(계열 테마를 책에서
    생성해 넘기는 경우).
    """
    src = theme if os.path.isabs(theme) else os.path.join(
        THEMES_DIR, f"{theme}.css")
    if not os.path.exists(src):
        raise FileNotFoundError(f"테마 없음: {src}")
    os.makedirs(build_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(build_dir, "theme.css"))
    base = os.path.join(THEMES_DIR, "_base.css")
    if os.path.exists(base):
        shutil.copy2(base, os.path.join(build_dir, "_base.css"))
    return os.path.join(build_dir, "theme.css")


def stage_assets(build_dir, src_dir):
    """자산 폴더 통째 복사(있으면). 매번 지우고 다시 넣는다."""
    if not src_dir or not os.path.isdir(src_dir):
        return None
    dst = os.path.join(build_dir, "assets")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src_dir, dst)
    return dst


def write_css(build_dir, name, text=""):
    """생성 CSS(2패스 오버라이드 등) 기록. 1패스에선 빈 파일."""
    os.makedirs(build_dir, exist_ok=True)
    p = os.path.join(build_dir, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p
