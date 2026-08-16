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


@bp.route("/api/cover2026/run", methods=["POST"])
def run():
    """지정 학교·권을 새 쪽수로 다시 렌더한다.

    apply=False → 미리보기만 만들고 납품 폴더는 건드리지 않는다(기본).
    apply=True  → 검사 통과 시 납품 폴더까지 교체한다(백업 자동).
    """
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

    env = dict(os.environ, COVER_SETTINGS=meta["설정"], COVER_ROOT=GEN_ROOT)
    cmd = [sys.executable, os.path.join(GEN, "web_spine.py"),
           "--school", vid, "--volume", vol, "--pages", str(pages)]
    if apply_:
        cmd.append("--apply")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=GEN, timeout=600)
    try:
        payload = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return jsonify({"ok": False, "error": "생성기 응답을 읽지 못했다",
                        "log": (r.stdout + r.stderr)[-4000:]}), 500
    payload["log"] = (r.stdout + r.stderr)[-4000:]
    return jsonify(payload), (200 if payload.get("ok") else 500)


@bp.route("/api/cover2026/file")
def file():
    """생성된 PDF/PNG 내려주기. 생성기 out 폴더 안으로만 제한한다."""
    rel = request.args.get("p", "")
    base = os.path.realpath(os.path.join(GEN_ROOT, "out"))
    full = os.path.realpath(os.path.join(base, u.normalize("NFC", rel)))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return "not found", 404
    return send_file(full, as_attachment=request.args.get("dl") == "1")
