"""Vivliostyle CLI 위치·실행 — **단일 소스**.

지금까지 CLI 경로(`pilot/vivliostyle/node_modules/.bin/vivliostyle`)는 세 곳에
복사돼 있었다: `core/render_vivlio/build.py`, 상일보카 `automation/build.py`,
블랙북 `automation/build.py`. 계열이 늘 때마다 사본이 하나씩 늘어나므로 여기로
모은다. 탐색 순서는 아래 `_CANDIDATES` — 리포 소유 `core/render_vivlio/`(권장,
`npm ci` 대상)를 먼저 보고, 없으면 기존 파일럿 설치본으로 폴백한다.
"""
import contextlib
import os
import re
import subprocess
import threading
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


def _browser_args():
    """`YONE_VIV_BROWSER=/usr/bin/chromium` 이면 CLI 가 크롬을 내려받지 않고 그것을 쓴다(컨테이너)."""
    b = (os.environ.get("YONE_VIV_BROWSER") or "").strip()
    return ["--executable-browser", b] if b else []


# ── 조판 건너뛰기 (라이브 미리보기 전용) ─────────────────────────────
class RenderOnly(Exception):
    """"HTML 까지만 만들고 멈춘다"는 신호. `html_path` 를 달고 온다.

    미리보기는 PDF 가 필요 없다 — 뷰어가 HTML 을 직접 조판한다. 그런데 계열마다
    `build()` 앞부분(서체·자산·테마·HTML 쓰기)이 제각각이라 "HTML 까지만"을
    계열별로 다시 짜면 사본이 네 벌 늘어난다. 그래서 **모든 계열이 반드시
    지나가는 한 지점**(조판 호출)에서 멈추는 방식으로 한 벌만 둔다.
    """

    def __init__(self, html_path):
        super(RenderOnly, self).__init__(html_path)
        self.html_path = html_path


_SKIP_BUILD = False


@contextlib.contextmanager
def skip_build():
    """이 블록 안에서 `run_build` 는 조판하지 않고 `RenderOnly` 를 던진다."""
    global _SKIP_BUILD
    old = _SKIP_BUILD
    _SKIP_BUILD = True
    try:
        yield
    finally:
        _SKIP_BUILD = old


_PREVIEW_URL = re.compile(r"Preview URL:\s*(\S+)")


def run_preview(html_path, port=13000, host="127.0.0.1", log=None, timeout=90):
    """`vivliostyle preview` 서버를 띄운다(백그라운드). `(proc, url)`.

    `--no-open-viewer` 로 **Playwright 브라우저를 띄우지 않는다** — 사용자가
    쓰던 브라우저에서 열게 하는 편이 낫고, 브라우저 설치에도 안 딸린다.
    서버는 HTML 을 지켜보다 바뀌면 화면을 스스로 새로 그린다.

    ⚠ 주소를 **직접 조립하지 않는다.** 뷰어는 `/__vivliostyle-viewer/index.html`
      에 있고 문서는 `/vivliostyle/…` 로 서빙되며 해시에 `src=` 가 붙는다 —
      판본이 바뀌면 규칙도 바뀔 수 있어, CLI 가 찍어 주는 줄을 읽는다.
    ⚠ stdout 을 안 읽고 두면 파이프가 차서 **서버가 멎는다** → 남은 출력은
      데몬 스레드가 계속 비운다.
    """
    cli = require_cli()
    html_path = os.path.abspath(html_path)
    cmd = [cli, "preview", os.path.basename(html_path),
           "--no-open-viewer", "--host", host, "--port", str(port),
           "--log-level", "info"] + _browser_args()
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(html_path),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env=dict(os.environ))

    url, deadline, tail = None, time.time() + timeout, []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        tail.append(line.rstrip())
        m = _PREVIEW_URL.search(line)
        if m:
            url = m.group(1)
            break
    if url is None:
        try:
            proc.terminate()
        except Exception:
            pass
        raise RuntimeError("preview 서버가 주소를 알려 주지 않았다 "
                           f"(포트 {port} 가 이미 쓰이는지 확인)\n"
                           + "\n".join(tail[-15:]))

    def _drain():
        try:
            for _ in proc.stdout:
                pass
        except Exception:
            pass
    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    if log:
        log(f"[vivlio] preview :{port} (pid {proc.pid})")
    return proc, url


def run_build(html_path, out_pdf, log=None, timeout=900, extra=(), final=True):
    """`vivliostyle build <html> -o <pdf>` 를 html 이 있는 디렉터리에서 실행.

    `final=False` 는 **산출물이 아닌 내부 조판**(높이 측정 패스 등)이라는 뜻이다.
    미리보기가 조판을 건너뛸 때 이런 패스에서 멈춰 버리면 엉뚱한 HTML 을 미리보기로
    삼게 되므로, 건너뛰기는 최종 조판에만 걸린다.

    Returns: 소요 초(float).
    """
    if _SKIP_BUILD and final:
        raise RenderOnly(os.path.abspath(html_path))
    cli = require_cli()
    html_path = os.path.abspath(html_path)
    # 정규식 스타일 — 꼴이 맞는 글자에 문자 스타일을 건다(인디자인의 GREP 스타일).
    # ⚠ 계열마다 HTML 을 제 손으로 짜므로 **여기서 한 번** 한다. 측정 조판도
    #   같은 길을 지나가니 잰 높이와 실제 조판이 어긋나지 않는다.
    try:
        from core.render_vivlio import grepstyle as _gs
        n = _gs.apply_file(html_path)
        if n and log:
            log(f"  [정규식 스타일] {n}곳")
    except Exception as e:                      # 조판을 막지는 않는다
        if log:
            log(f"  [정규식 스타일] 건너뜀 — {e}")
    cwd = os.path.dirname(html_path)
    cmd = [cli, "build", os.path.basename(html_path),
           "-o", os.path.abspath(out_pdf)] + _browser_args() + list(extra)
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
