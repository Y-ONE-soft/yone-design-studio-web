"""Vivliostyle CLI 위치·실행 — **단일 소스**.

지금까지 CLI 경로(`pilot/vivliostyle/node_modules/.bin/vivliostyle`)는 세 곳에
복사돼 있었다: `core/render_vivlio/build.py`, 상일보카 `automation/build.py`,
블랙북 `automation/build.py`. 계열이 늘 때마다 사본이 하나씩 늘어나므로 여기로
모은다. 탐색 순서는 아래 `_CANDIDATES` — 리포 소유 `core/render_vivlio/`(권장,
`npm ci` 대상)를 먼저 보고, 없으면 기존 파일럿 설치본으로 폴백한다.
"""
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

# ① 리포 소유(권장): core/render_vivlio/package.json + `npm ci`
OWN_DIR = HERE
# ② 파일럿 설치본(기존 경로) — 이관 전까지의 폴백
PILOT_DIR = os.path.join(REPO, "pilot", "vivliostyle")

CLI_VERSION = "11.1.0"          # 기록용 (@vivliostyle/cli, core 2.44.1)

_CANDIDATES = (
    os.path.join(OWN_DIR, "node_modules", ".bin", "vivliostyle"),
    os.path.join(PILOT_DIR, "node_modules", ".bin", "vivliostyle"),
)


class VivliostyleUnavailable(RuntimeError):
    """vivliostyle CLI 미설치 (opt-in 백엔드 전제 조건 미충족)."""


def cli_path():
    """설치된 CLI 절대경로 또는 None."""
    for p in _CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def cli_available():
    return cli_path() is not None


def require_cli():
    p = cli_path()
    if p is None:
        raise VivliostyleUnavailable(
            "vivliostyle CLI 없음 — 다음 중 한 곳에 설치해야 한다:\n"
            + "\n".join(f"  · {c}" for c in _CANDIDATES)
            + f"\n→ `cd {OWN_DIR} && npm ci` (권장) 또는 "
              f"`cd {PILOT_DIR} && npm ci`")
    return p


def run_build(html_path, out_pdf, log=None, timeout=900, extra=()):
    """`vivliostyle build <html> -o <pdf>` 를 html 이 있는 디렉터리에서 실행.

    Returns: 소요 초(float).
    """
    cli = require_cli()
    html_path = os.path.abspath(html_path)
    cwd = os.path.dirname(html_path)
    cmd = [cli, "build", os.path.basename(html_path),
           "-o", os.path.abspath(out_pdf)] + list(extra)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout,
                          env=dict(os.environ, PATH=os.environ.get("PATH", "")))
    dt = time.time() - t0
    if log:
        log(f"[vivlio] build {os.path.basename(html_path)} "
            f"{dt:.1f}s (exit {proc.returncode})")
    if proc.returncode != 0:
        if log:
            log((proc.stdout or "")[-3000:])
            log((proc.stderr or "")[-3000:])
        else:
            print((proc.stdout or "")[-3000:])
            print((proc.stderr or "")[-3000:])
        raise RuntimeError(f"vivliostyle build 실패 (exit {proc.returncode})")
    return dt
