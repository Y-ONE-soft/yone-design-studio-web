"""라이브 미리보기 — 고치면 브라우저가 스스로 새로 그린다.

    bin/viv "<책폴더>" watch            # http://127.0.0.1:13000 열어 두고 작업
    bin/viv "<책폴더>" watch --port=13100

인디자인의 "고치고 바로 본다"에 해당하는 자리다. 지금까지는 값 하나를 바꿔도
전권 조판(20~50초)을 돌리고 PDF 뷰어를 다시 열어야 했다 — 그 왕복이 클로드를
부르게 만드는 가장 큰 이유였다.

**완전히 로컬·오프라인이다.** `@vivliostyle/cli` 와 뷰어가 `node_modules` 에
이미 들어 있어 새로 설치할 것도, 인터넷도 필요 없다.

## 어떻게 도는가

1. 한 번 렌더해 `build/` 를 채운다(HTML·테마·서체·자산). **PDF 는 만들지 않는다**
   — 뷰어가 HTML 을 직접 조판하기 때문에 필요가 없고, 그래서 빠르다.
2. `vivliostyle preview` 서버를 띄운다(`--no-open-viewer`: Playwright 브라우저를
   띄우지 않고 서버만. 쓰던 브라우저로 열면 된다).
3. 소스 파일들의 mtime 을 지켜보다 바뀌면 **다시 렌더**한다. 뷰어가 알아서 새로 그린다.

## ⚠ 편집 지점은 `build/` 가 아니다

`build/theme.css` · `build/index.html` 은 렌더할 때마다 덮어써지는 **사본**이다.
거기 고친 것은 다음 렌더에 사라진다. 고칠 곳은

  · `config.json`                     — 색·치수·옵션(손잡이)
  · `core/render_vivlio/series/<계열>/`  — 마크업·테마 생성
  · `core/render_vivlio/themes/<계열>.css` — 계열 스타일시트
  · `<책폴더>/overrides.css`            — 손잡이 밖 임시 덮어쓰기(있으면)

원고를 고쳤으면 `--data` 를 주거나 따로 `bin/viv <책> data` 를 돌린다
(원고 → data.json 은 인식 게이트가 걸려 있어 렌더보다 무겁다).

## ⚠ 렌더는 **별도 프로세스**로 돈다

계열 코드(.py)를 고치면 이미 불러 둔 모듈은 안 바뀐다. `importlib.reload` 로
얽힌 모듈 그래프를 다시 얹는 것은 조용히 어긋나기 쉬워서, 아예 `bin/viv <책>
render` 를 자식 프로세스로 부른다. 늘 새 코드로 돈다.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

POLL = 0.4                      # 초. 사람이 저장하고 눈 돌리는 사이보다 짧으면 된다
SETTLE = 0.25                   # 저장이 여러 파일에 걸칠 때 몰아서 한 번만 렌더


def _watch_files(cfg):
    """지켜볼 파일 목록 — 고치면 지면이 달라지는 것 전부."""
    out = []

    def add(p):
        if p and os.path.exists(p):
            out.append(p)

    # ① 책 — 손잡이와 탈출구
    add(cfg.path("config.json"))
    add(cfg.path("data.json"))
    add(cfg.path("overrides.css"))

    # ② 계열 — 마크업·테마 생성
    sdir = os.path.join(HERE, "series", cfg.series)
    for dirpath, dirnames, filenames in os.walk(sdir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in filenames:
            if f.endswith(".py"):
                add(os.path.join(dirpath, f))

    # ③ 계열 스타일시트 + 공통 골격
    tdir = os.path.join(HERE, "themes")
    add(os.path.join(tdir, "_base.css"))
    add(os.path.join(tdir, f"{cfg.series}.css"))

    # ④ 공용 백엔드 (렌더·페이지 규칙에 걸린다)
    for f in os.listdir(HERE):
        if f.endswith(".py") and f != "watch.py":
            add(os.path.join(HERE, f))
    return out


def _stamp(paths):
    s = {}
    for p in paths:
        try:
            s[p] = os.path.getmtime(p)
        except OSError:
            pass
    return s


def _render(book, opts, log):
    """`bin/viv <책> render` 를 자식 프로세스로. (성공?, html 경로 또는 메시지)"""
    cmd = [sys.executable, "-m", "core.render_vivlio.book", book, "render"]
    cmd += [f"--{k}" if v is True else f"--{k}={v}" for k, v in opts.items()]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    dt = time.time() - t0
    if p.returncode != 0:
        tail = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
        log(f"  ✗ 렌더 실패 ({dt:.1f}s) — 고치면 다시 시도한다")
        for ln in tail[-12:]:
            log("    " + ln)
        return False, None
    html = None
    for ln in (p.stdout or "").splitlines():
        if ln.startswith("RENDER_HTML="):
            html = ln.split("=", 1)[1].strip()
    log(f"  ✓ 렌더 {dt:.1f}s")
    return True, html


def run(cfg, book, log=print, port=13000, host="127.0.0.1", **opts):
    """미리보기 서버를 띄우고 소스를 지켜본다. Ctrl-C 로 끝낸다."""
    from core.render_vivlio import cli

    opts = {k: v for k, v in opts.items() if k not in ("port", "host")}
    log(f"■ 라이브 미리보기 — {cfg.book.get('title', cfg.series)}")
    ok, html = _render(book, opts, log)
    if not ok:
        log("  첫 렌더가 실패해 미리보기를 띄우지 못했다.")
        return 1
    html = html or os.path.join(cfg.build_dir, "index.html")

    try:
        proc, url = cli.run_preview(html, port=port, host=host, log=log)
    except RuntimeError as e:
        log(f"  ✗ {e}")
        return 1
    log("")
    log(f"  ▶ 브라우저에서 열 것:")
    log(f"    {url}")
    log(f"  ▶ 지켜보는 파일 {len(_watch_files(cfg))}개 — 고쳐 저장하면 다시 그린다")
    log(f"  ▶ 편집 지점은 build/ 가 아니다: config.json · series/{cfg.series}/ · "
        f"themes/{cfg.series}.css")
    log("  ▶ 끝내려면 Ctrl-C")
    log("")

    files = _watch_files(cfg)
    seen = _stamp(files)
    try:
        while True:
            time.sleep(POLL)
            if proc.poll() is not None:
                log("[미리보기 서버가 멎었다] — 포트가 이미 쓰이는지 확인할 것")
                return 1
            # 목록 자체가 늘 수도 있다(새 파일) → 매번 다시 훑는다. 비용은 무시할 수준.
            files = _watch_files(cfg)
            now = _stamp(files)
            changed = [p for p, m in now.items() if seen.get(p) != m]
            if not changed:
                seen = now
                continue
            time.sleep(SETTLE)                       # 연달아 저장되는 것 몰아 받기
            now = _stamp(_watch_files(cfg))
            names = ", ".join(sorted(os.path.basename(p) for p in changed)[:4])
            extra = f" 외 {len(changed) - 4}개" if len(changed) > 4 else ""
            log(f"[바뀜] {names}{extra}")
            _render(book, opts, log)
            seen = now
    except KeyboardInterrupt:
        log("\n미리보기를 끝낸다.")
        return 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
