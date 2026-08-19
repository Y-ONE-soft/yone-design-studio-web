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


@bp.route("/api/cover-studio/prompt", methods=["POST"])
def api_prompt():
    """자연어 → 파라미터 변경안. 값을 정하기만 하고 적용은 사람이 미리보기로 본다.

    AI 검수(core/review_agent.py)와 같은 `claude -p` 방식이라 API 키가 필요 없다.
    다만 여기서는 **도구를 전부 막는다** — 파일을 읽을 일이 없고, 표지 폴더에
    쓰기가 일어나면 안 된다.
    """
    from core.review_agent import find_claude_bin

    d = request.get_json(silent=True) or {}
    ask = (d.get("ask") or "").strip()
    if not ask:
        return jsonify({"error": "무엇을 바꿀지 적어주세요"}), 400

    try:
        proj = _project(d.get("project"))
        spec = _run(proj, ["spec"])
    except (ValueError, subprocess.TimeoutExpired) as e:
        return jsonify({"error": str(e)}), 400
    if spec.returncode != 0:
        return jsonify({"error": spec.stderr[-800:] or "spec 실패"}), 500

    info = json.loads(spec.stdout)
    saved = info["values"]                       # 파일에 저장된 값
    now = dict(saved, **(d.get("ov") or {}))     # 화면에서 만지는 중인 값
    # saved 를 같이 준다 — 이게 없으면 "원래대로 되돌려" 를 모델이 지어낸다.
    knobs = [{k: p[k] for k in ("key", "label", "group", "type", "min", "max",
                                "step", "hint") if k in p}
             | {"now": now.get(p["key"]), "saved": saved.get(p["key"])}
             for p in info["params"]]

    bin_ = find_claude_bin()
    if not bin_:
        return jsonify({"error": "claude CLI 를 찾을 수 없습니다. "
                                 "터미널에서 `claude` 실행 후 /login 하세요."}), 503

    schema = {
        "type": "object",
        "properties": {
            "changes": {"type": "object", "description": "바꿀 값 {key: value}",
                        "additionalProperties": True},
            "note": {"type": "string", "description": "무엇을 왜 바꿨는지 한 줄"},
        },
        "required": ["changes", "note"],
    }
    prompt = (
        "너는 교재 표지 디자인 도구의 조절판을 대신 만져주는 역할이다.\n"
        "아래는 지금 조절할 수 있는 값의 목록이다.\n"
        "now = 화면에서 만지는 중인 값 · saved = 파일에 저장된 값"
        " ('원래대로 되돌려' 는 saved 를 쓴다).\n\n"
        + json.dumps(knobs, ensure_ascii=False, indent=1)
        + f"\n\n사용자 요청: {ask}\n\n"
        "요청에 맞게 바꿀 값만 골라 changes 에 담아라. 규칙:\n"
        "- key 는 위 목록에 있는 것만 쓴다. 없는 값은 만들지 않는다.\n"
        "- range 는 min~max 안의 숫자, color 는 #RRGGBB, text 는 문자열.\n"
        "- 요청과 무관한 값은 건드리지 않는다. 애매하면 적게 바꾼다.\n"
        "- '조금'은 현재값의 5~10%, '많이'는 20~30% 정도로 본다.\n"
        "- 바꿀 게 없으면 changes 를 비우고 note 에 이유를 적는다.\n"
        "- note 는 한국어 한 줄."
    )
    cmd = [bin_, "-p", prompt,
           "--model", os.environ.get("YONE_COVER_STUDIO_MODEL", "sonnet"),
           "--output-format", "json",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--tools", "", "--allowedTools", "",
           "--disallowedTools", "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task",
           "--permission-mode", "default",
           "--no-session-persistence",
           "--max-budget-usd", os.environ.get("YONE_COVER_STUDIO_BUDGET_USD", "0.5")]
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [os.path.dirname(bin_), env.get("PATH", ""), "/usr/bin", "/bin"])
    try:
        cp = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "응답이 너무 오래 걸립니다"}), 504
    if cp.returncode != 0:
        tail = (cp.stderr or cp.stdout or "").strip()[-400:]
        hint = (" — 서버에서 claude CLI 로그인 필요 (터미널에서 `claude` 실행 후 /login)"
                if "Not logged in" in tail else "")
        return jsonify({"error": f"프롬프트 처리 실패{hint}\n{tail}"}), 502

    out = _structured(cp.stdout)
    if out is None:
        return jsonify({"error": "응답을 이해하지 못했습니다"}), 502

    # 모르는 key·범위 밖 값은 버린다 — 화면이 만들지 않은 값이 들어오면 안 된다
    by_key = {p["key"]: p for p in info["params"]}
    clean = {}
    for k, v in (out.get("changes") or {}).items():
        p = by_key.get(k)
        if not p:
            continue
        if p["type"] == "range":
            try:
                v = min(float(p["max"]), max(float(p["min"]), float(v)))
            except (TypeError, ValueError):
                continue
        elif p["type"] == "color":
            v = str(v).strip()
            if not (v.startswith("#") and len(v) == 7):
                continue
        else:
            v = str(v)
        clean[k] = v
    return jsonify({"changes": clean, "note": out.get("note", "")})


def _structured(stdout):
    """claude -p --output-format json 응답에서 구조화 결과를 꺼낸다."""
    try:
        top = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    for key in ("structured_output", "structuredOutput", "result", "content"):
        v = top.get(key) if isinstance(top, dict) else None
        if isinstance(v, dict) and "changes" in v:
            return v
        if isinstance(v, str):
            try:
                d = json.loads(v)
                if isinstance(d, dict) and "changes" in d:
                    return d
            except json.JSONDecodeError:
                pass
    return top if isinstance(top, dict) and "changes" in top else None


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
