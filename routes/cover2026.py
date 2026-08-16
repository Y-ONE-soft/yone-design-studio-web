# -*- coding: utf-8 -*-
"""2026 표지 세네카 조정 — 쪽수만 넣으면 워크북 스프레드를 다시 뽑는다.

기존 `/cover` (세네카 조정) 와 다른 점:
  기존 = Illustrator + ExtendScript 로 **.ai 파일**을 조정한다. 업로드가 필요하다.
  여기 = 2026 리뉴얼 표지는 HTML→Chrome→PDF 로 생성돼 .ai 가 없다. 원본이 서버에
         있으므로 업로드 없이 **학교·권·쪽수만 고르면** 생성기가 다시 렌더한다.

학교 목록·쪽수는 표지설정.json 이 유일한 진실이라, 파일에 학교를 추가하면
여기 목록에도 자동으로 나타난다. 하드코딩이 없다.
프로젝트(2026 리뉴얼 / 이후 2027 …)는 PROJECTS 에 한 줄 추가하면 늘어난다.
"""
import json
import os
import subprocess
import sys
import unicodedata as u

from flask import Blueprint, jsonify, render_template, request, send_file

bp = Blueprint("cover2026", __name__)

GEN_ROOT = os.path.expanduser("~/dev/yone-cover2026")
GEN = os.path.join(GEN_ROOT, "gen")

# 생성기를 돌릴 파이썬을 **직접 찾는다**. `sys.executable` 을 쓰면 안 된다 —
# Flask 는 /usr/bin/python3(3.9) 로 뜨는데 생성기는 pypdf·PyMuPDF·numpy·skimage 를
# 쓰고 그 3.9 환경엔 없다. (2026-08-17: 이것 때문에 웹 버튼이 아무 반응도 없었다)
_PY_CANDIDATES = [
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    sys.executable,
]
_NEEDED = "import fitz, pypdf, numpy, PIL"
_py_cache = None


def _python():
    """생성기 의존성이 설치된 파이썬 경로. 없으면 무엇이 없는지 알려준다."""
    global _py_cache
    if _py_cache:
        return _py_cache
    # 탐색할 때도 PYTHONPATH 를 비운다 — Flask 가 물고 있는 3.9 site-packages 가
    # 후보 파이썬에 섞이면 numpy import 가 깨져 멀쩡한 인터프리터가 탈락한다.
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    tried = []
    for p in _PY_CANDIDATES:
        if not p or not os.path.exists(p):
            continue
        r = subprocess.run([p, "-c", _NEEDED], capture_output=True, text=True, env=clean)
        if r.returncode == 0:
            _py_cache = p
            return p
        tried.append(f"{p}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '실패'}")
    raise RuntimeError("생성기를 돌릴 파이썬을 찾지 못했다 (fitz·pypdf·numpy·PIL 필요)\n"
                       + "\n".join(tried))

# 프로젝트 = 표지 시안 한 벌. 새 시안이 생기면 여기에 한 줄 추가한다.
PROJECTS = {
    "2026": {
        "표기": "2026 리뉴얼 (시안A GLASS RIBBON)",
        "설정": ("/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/"
                "2026_리뉴얼_1차시안/표지설정.json"),
    },
}


def _settings(project):
    p = PROJECTS.get(project)
    if not p:
        raise KeyError(f"모르는 프로젝트: {project}")
    with open(p["설정"], encoding="utf-8") as f:
        return p, json.load(f)


def _spine_mm(pages, mult):
    import math
    raw = (pages / 2) * mult
    return math.ceil(math.ceil(raw * 2) / 2 + 0.5)


@bp.route("/cover2026")
def page():
    return render_template("typeset_cover2026.html", projects=PROJECTS)


@bp.route("/api/cover2026/schools")
def schools():
    """학교·권·현재 쪽수 목록. 설정 파일을 그대로 읽으므로 항상 최신이다."""
    project = request.args.get("project", "2026")
    try:
        meta, cfg = _settings(project)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    vols = cfg.get("워크북쪽수", {})
    out = []
    for s in cfg["학교"]:
        for g in s["학년"]:
            vid = f"{s['id']}{g}"
            v = vols.get(vid, {})
            out.append({
                "id": vid,
                "label": f"{s['표기']} {g}",
                "branch": s["관"],
                "volumes": [{"vol": k, "pages": v[k],
                             "spine": _spine_mm(v[k], cfg["용지계수"]["newplus"])}
                            for k in sorted(v)],
            })
    return jsonify({"ok": True, "project": meta["표기"],
                    "paper": cfg["용지계수"], "schools": out})


LOG = os.path.join(GEN_ROOT, "out", "web.log")


def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{__import__('datetime').datetime.now():%H:%M:%S} {msg}\n")
    except Exception:
        pass


@bp.route("/api/cover2026/run", methods=["POST"])
def run():
    """지정 학교·권을 새 쪽수로 다시 렌더한다.

    apply=False → 미리보기만 만들고 납품 폴더는 건드리지 않는다(기본).
    apply=True  → 검사 통과 시 납품 폴더까지 교체한다(백업 자동).

    **어떤 예외도 밖으로 내보내지 않는다.** 디버그 모드 Flask 는 예외가 나면 HTML
    트레이스백을 돌려주는데, 그러면 브라우저에서 `Unexpected token '<'` 만 보이고
    원인을 알 수 없다(2026-08-17). 무슨 일이 있어도 JSON 으로 답한다.
    """
    try:
        return _run_inner()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _log("run 실패\n" + tb)
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}",
                        "log": tb[-3000:]}), 500


def _run_inner():
    d = request.get_json(force=True) or {}
    project = d.get("project", "2026")
    vid = (d.get("school") or "").strip()
    vol = (d.get("volume") or "01").strip()
    pages = d.get("pages")
    apply_ = bool(d.get("apply"))
    if not vid or not isinstance(pages, int) or pages <= 0:
        return jsonify({"ok": False, "error": "학교와 쪽수를 확인하라"}), 400
    try:
        meta, cfg = _settings(project)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        py = _python()
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    env = dict(os.environ, COVER_SETTINGS=meta["설정"], COVER_ROOT=GEN_ROOT)
    env.pop("PYTHONPATH", None)      # Flask 의 3.9 site-packages 가 섞이면 import 가 꼬인다
    cmd = [py, os.path.join(GEN, "web_spine.py"),
           "--school", vid, "--volume", vol, "--pages", str(pages)]
    if apply_:
        cmd.append("--apply")
    _log(f"실행 {vid} {vol} {pages}p apply={apply_} py={py}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=GEN, timeout=600)
    except subprocess.TimeoutExpired:
        _log("시간초과")
        return jsonify({"ok": False, "error": "시간이 너무 오래 걸려 중단했습니다(10분)"}), 500
    except Exception as e:
        _log(f"생성기 실행 자체가 실패: {type(e).__name__}: {e}")
        return jsonify({"ok": False,
                        "error": f"생성기를 실행하지 못했습니다: {type(e).__name__}: {e}"}), 500
    _log(f"종료코드 {r.returncode} · stdout {len(r.stdout)}B · stderr {len(r.stderr)}B")
    try:
        payload = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        _log("응답 파싱 실패\n" + (r.stdout + r.stderr)[-2000:])
        return jsonify({"ok": False, "error": "생성기 응답을 읽지 못했다",
                        "log": (r.stdout + r.stderr)[-4000:]}), 500
    payload["log"] = (r.stdout + r.stderr)[-4000:]
    return jsonify(payload), (200 if payload.get("ok") else 500)


@bp.route("/api/cover2026/selftest")
def selftest():
    """단계별 자가진단. 브라우저에서 그냥 열면 어디서 막히는지 JSON 으로 나온다.

    웹 버튼이 안 될 때 원인을 층별로 가른다: 설정 읽기 / 파이썬 탐색 /
    자식 프로세스 실행 / 자식이 Documents 를 읽을 수 있는지(macOS 권한) / Chrome.
    """
    out = []

    def step(name, fn):
        try:
            out.append({"단계": name, "ok": True, "결과": fn()})
        except Exception as e:
            out.append({"단계": name, "ok": False, "결과": f"{type(e).__name__}: {e}"})

    step("Flask 파이썬", lambda: sys.version.split()[0] + " @ " + sys.executable)
    step("설정 파일 읽기", lambda: f"{len(_settings('2026')[1]['학교'])}개교")
    step("생성기 파이썬 탐색", _python)

    def child_check():
        py = _python()
        clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        code = ("import json,sys;"
                "p=r'" + PROJECTS['2026']['설정'] + "';"
                "open(p,encoding='utf-8').read();"
                "import fitz,pypdf,numpy,PIL;"
                "print('OK', sys.version.split()[0])")
        r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                           env=clean, timeout=60)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[-500:])
        return r.stdout.strip()
    step("자식 프로세스 + Documents 읽기", child_check)

    def chrome_check():
        c = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not os.path.exists(c):
            raise FileNotFoundError(c)
        r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or "버전 확인 실패"
    step("Chrome", chrome_check)

    step("출력 폴더 쓰기", lambda: (os.makedirs(os.path.join(GEN_ROOT, "out"), exist_ok=True),
                               open(os.path.join(GEN_ROOT, "out", ".probe"), "w").write("1"),
                               "OK")[-1])
    bad = [o for o in out if not o["ok"]]
    return jsonify({"ok": not bad, "요약": "모두 정상" if not bad else f"{len(bad)}단계 실패",
                    "단계별": out})


@bp.route("/api/cover2026/file")
def file():
    """생성된 PDF/PNG 내려주기. 생성기 out 폴더 안으로만 제한한다."""
    rel = request.args.get("p", "")
    base = os.path.realpath(os.path.join(GEN_ROOT, "out"))
    full = os.path.realpath(os.path.join(base, u.normalize("NFC", rel)))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return "not found", 404
    return send_file(full, as_attachment=request.args.get("dl") == "1")
