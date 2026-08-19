# -*- coding: utf-8 -*-
"""표지 작업대 — 보면서 고치는 화면.

기존 표지 화면들과 다른 점:
  `/cover`      = .ai 업로드 → 세네카만 조정 → PDF 다운로드
  `/cover2026`  = 쪽수 고르면 생성기가 다시 렌더 (업로드 없음)
  여기          = **값을 만지는 동안 미리보기가 계속 바뀐다.** 마음에 들면 저장.

생성기를 이 프로세스에서 import 하지 않고 subprocess 로 부른다. 생성기가 모듈
전역 상수로 돌아가서, 한 요청의 오버라이드가 다음 요청에 남기 때문이다.
프로세스를 매번 새로 띄우면 그 오염이 원천적으로 없다 (실측 70ms).

조절 항목은 교재 폴더의 `params.py` 가 정한다 — 항목을 추가해도 이 파일과
템플릿은 안 고친다. 새 교재를 붙일 때도 그쪽에 `studio.py`·`params.py` 만
만들면 되고, PROJECTS 에 한 줄 추가한다.
"""
import json
import os
import subprocess
import sys

from flask import Blueprint, Response, jsonify, render_template, request

bp = Blueprint("cover_studio", __name__)

STUDIO_ROOT = os.path.expanduser("~/Documents/작업/Y.ONE STUDIO")

# 교재 = 작업대 한 벌. 새 선생님 표지가 생기면 여기에 한 줄 추가한다.
PROJECTS = {
    "ansc": {
        "표기": "안성찬T · 영동고 (2학기 중간)",
        "폴더": os.path.join(STUDIO_ROOT, "디자인/표지/안성찬T/일러스트_교복"),
    },
}
DEFAULT = "ansc"

# 미리보기는 순수 파이썬이라 Flask 가 뜬 3.9 로도 돈다. 내보내기(PDF)는
# fitz·pypdf·PIL 이 필요해 그때만 무거운 파이썬을 찾는다.
_PY_CANDIDATES = [
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    sys.executable,
]
_py_cache = None


def _heavy_python():
    """PDF 를 뽑을 수 있는 파이썬. 없으면 무엇이 없는지 알려준다."""
    global _py_cache
    if _py_cache:
        return _py_cache
    # 탐색할 때 PYTHONPATH 를 비운다 — Flask 가 물고 있는 3.9 site-packages 가
    # 후보 파이썬에 섞이면 멀쩡한 인터프리터가 탈락한다 (cover2026 에서 겪음).
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    tried = []
    for p in _PY_CANDIDATES:
        if not p or not os.path.exists(p):
            continue
        r = subprocess.run([p, "-c", "import fitz, pypdf, PIL"],
                           capture_output=True, text=True, env=clean)
        if r.returncode == 0:
            _py_cache = p
            return p
        tail = r.stderr.strip().splitlines()
        tried.append(f"{p}: {tail[-1] if tail else '실패'}")
    raise RuntimeError("PDF 를 뽑을 파이썬을 찾지 못했다 (fitz·pypdf·PIL 필요)\n"
                       + "\n".join(tried))


def _project(key=None):
    p = PROJECTS.get(key or request.args.get("p") or DEFAULT)
    if not p:
        raise ValueError("모르는 교재")
    return p


def _run(proj, args, stdin_data=None, python=None, timeout=120):
    """교재 폴더의 studio.py 를 부른다."""
    cmd = [python or sys.executable, os.path.join(proj["폴더"], "studio.py")] + args
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(cmd, input=stdin_data, capture_output=True, text=True,
                          cwd=proj["폴더"], env=env, timeout=timeout)


@bp.route("/cover-studio")
def studio():
    key = request.args.get("p") or DEFAULT
    return render_template("cover_studio.html",
                           projects=PROJECTS, project_key=key,
                           project=PROJECTS.get(key, {}), active_nav="표지")


@bp.route("/api/cover-studio/spec")
def api_spec():
    try:
        r = _run(_project(), ["spec"])
    except (ValueError, subprocess.TimeoutExpired) as e:
        return jsonify({"error": str(e)}), 400
    if r.returncode != 0:
        return jsonify({"error": r.stderr[-800:] or "spec 실패"}), 500
    return Response(r.stdout, mimetype="application/json")


@bp.route("/api/cover-studio/preview", methods=["POST"])
def api_preview():
    d = request.get_json(silent=True) or {}
    book, week = d.get("book", ""), str(d.get("week", ""))
    if not book.isalnum() or not week.isdigit():
        return jsonify({"error": "학년·주차 값이 이상하다"}), 400
    try:
        r = _run(_project(d.get("project")), ["preview", book, week],
                 stdin_data=json.dumps(d.get("ov") or {}, ensure_ascii=False),
                 timeout=60)
    except (ValueError, subprocess.TimeoutExpired) as e:
        return jsonify({"error": str(e)}), 400
    if r.returncode != 0:
        return jsonify({"error": r.stderr[-800:] or "미리보기 실패"}), 500
    return Response(r.stdout, mimetype="image/svg+xml")


@bp.route("/api/cover-studio/save", methods=["POST"])
def api_save():
    d = request.get_json(silent=True) or {}
    try:
        r = _run(_project(d.get("project")), ["save"],
                 stdin_data=json.dumps(d.get("ov") or {}, ensure_ascii=False))
    except (ValueError, subprocess.TimeoutExpired) as e:
        return jsonify({"error": str(e)}), 400
    if r.returncode != 0:
        return jsonify({"error": r.stderr[-800:] or "저장 실패"}), 500
    return Response(r.stdout, mimetype="application/json")
