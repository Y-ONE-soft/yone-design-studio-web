# -*- coding: utf-8 -*-
"""InDesign JSX 실행 — **.applescript 파일로** 넘긴다.

지나온 실패 셋을 다 피하려면 이 형태여야 한다.

  ① 인라인 `do script "…"` 은 스크립트가 길어지면 AppleEvent −609.
     → 짧은 한 줄(`$.evalFile`)만 보내고 본체는 파일로 둔다.
  ② `do script POSIX file …` 은 이 기계에서 −1708 로 거부됐다(실측).
     → `new File("…")` 를 쓴다.
  ③ `osascript -e` 는 **AppleEvent 기본 타임아웃 60초**가 걸려 무거운 문서에서
     −1712 로 죽는다(262권 중 39번째에서 멎었다). 그리고 따옴표를 이중으로
     이스케이프해야 해서 −2740(구문 오류)도 났다.
     → `with timeout` 을 넣은 **.applescript 파일**을 실행한다. 이스케이프 층이
       하나 줄어 두 문제가 같이 사라진다.
"""
import os
import subprocess

APP = "Adobe InDesign 2026"

_AS = '''with timeout of {sec} seconds
\ttell application "{app}" to do script "$.evalFile(new File(\\"{jsx}\\"));" language javascript
end timeout
'''


def run_file(jsx_path, timeout=1800, app=APP):
    jsx_path = os.path.abspath(jsx_path)
    if '"' in jsx_path or "\\" in jsx_path:
        raise ValueError("경로에 따옴표/역슬래시를 쓰지 말 것: %s" % jsx_path)
    as_path = jsx_path + ".applescript"
    with open(as_path, "w", encoding="utf-8") as f:
        f.write(_AS.format(sec=max(60, int(timeout) - 30), app=app,
                           jsx=jsx_path))
    r = subprocess.run(["osascript", as_path], capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[:800])
    return (r.stdout or "").strip()


def is_running(app=APP):
    r = subprocess.run(["pgrep", "-f", app], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def open_doc_count(app=APP, timeout=60):
    """열린 문서 수. **무응답이면 -1** — 예외를 던지면 호출부가 죽는다."""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "%s" to count of documents' % app],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1
    try:
        return int((r.stdout or "0").strip())
    except ValueError:
        return -1
