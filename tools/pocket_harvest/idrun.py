# -*- coding: utf-8 -*-
"""InDesign JSX 실행 — 파일로 넘긴다.

인라인 `do script "…"` 은 스크립트가 조금만 길어져도 AppleEvent -609 가 난다.
그래서 **짧은 인라인 한 줄**로 파일을 평가시킨다. `do script POSIX file …` 은
이 기계에서 -1708 로 거부됐다(실측) — 쓰지 않는다.
"""
import os
import subprocess

APP = "Adobe InDesign 2026"


def run_file(jsx_path, timeout=1800, app=APP):
    jsx_path = os.path.abspath(jsx_path)
    js = '$.evalFile(new File("%s"));' % jsx_path.replace('"', '\\"')
    script = 'tell application "%s" to do script "%s" language javascript' % (
        app, js.replace("\\", "\\\\").replace('"', '\\"'))
    r = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip()[:800])
    return (r.stdout or "").strip()


def is_running(app=APP):
    r = subprocess.run(["pgrep", "-f", app], capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def open_doc_count(app=APP):
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "%s" to count of documents' % app],
        capture_output=True, text=True, timeout=60)
    try:
        return int((r.stdout or "0").strip())
    except ValueError:
        return -1
