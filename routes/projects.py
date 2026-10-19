# -*- coding: utf-8 -*-
"""관리 — 라인업(폴더) · 템플릿 카드 · 템플릿 보기.

    /projects                       모든 프로젝트 — 라인업 목록, `?dir=<라인업>` 이면 그 라인업의 템플릿 카드
    /design/<series>/<design>       템플릿 보기 — 상위 페이지 · 원본 페이지 차례(구성) + 큰 그림

(예전 조판 엔진으로 만든 책 목록 · 다시 조판 · 새 프로젝트 화면은 2026-10-19 엔진과 함께 지웠다 — routes/books.py)
"""
import re
import unicodedata as u

from flask import Blueprint, abort, render_template, request

bp = Blueprint("projects", __name__)


def _nfc(s):
    return u.normalize("NFC", s or "")


@bp.route("/projects")
def page_projects():
    """`?dir=<디렉토리>` 면 그 폴더 안의 템플릿 카드."""
    from routes.catalog import DEFAULT_DIR, _dir_of, _dirs, _meta, design_images, templates
    ids = {d["id"] for d in _dirs()}
    tcounts = {}
    for m in _meta().values():                       # 틀 수 — 지울 때 "안의 틀 n개는 기타로" 안내용
        tcounts[_dir_of(m, ids)] = tcounts.get(_dir_of(m, ids), 0) + 1
    dcounts = {}                                     # 디자인 수 — 카드 숫자는 폴더 안에 보이는 디자인 카드 수와 같아야 한다
    for t in templates():
        dcounts[t["dir"]] = dcounts.get(t["dir"], 0) + len(t["designs"])
    # 폴더 = 카탈로그 디렉토리(dirs.json 순서). 기타는 틀이 있을 때만.
    folders = [{**d, "n": 0, "t": tcounts.get(d["id"], 0), "dn": dcounts.get(d["id"], 0)}
               for d in _dirs() if d["id"] != DEFAULT_DIR or dcounts.get(d["id"])]
    did = _nfc(request.args.get("dir", "")).strip()
    folder = next((f for f in folders if f["id"] == did), None) if did else None
    designs, fseries = [], []
    if folder:
        fseries = [{"series": did, "name": folder["name"]}]       # ＋ 메뉴(편집기 제작·PDF 등록)가 이 라인업으로 — 템플릿 자리는 서버가 고른다(없으면 만든다)
        for t in templates():
            if t["dir"] != did:
                continue
            for d in t["designs"]:
                imgs = design_images(t["series"], d)      # 견본 > 페이지 틀 > 기준 PDF 앞 면
                designs.append({"series": t["series"], "tname": t["name"], "ready": t["ready"], "id": d["id"], "name": d["name"],
                                "draft": d.get("draft", False), "n": ((d.get("intake") or {}).get("measured") or {}).get("pages") or d.get("pages"),   # 기준 PDF 면 수 (견본 장수 아님)
                                "made": d.get("made") or ("pdf" if str(d.get("source", "")).startswith("PDF:") or (d.get("intake") or {}).get("measured") else ""),   # 라벨 — PDF 등록 · 편집기 제작
                                "img": imgs[0]["src"] if imgs else "",
                                "manuscript": t["manuscript"], "tags": d.get("tags") or {}})
    # 필터 — 디자인 tags(design.json, 예: 학교·년도·교재 유형)의 값을 키마다 모은다
    filters = {}
    for d in designs:
        for k, v in d["tags"].items():
            if v and v not in filters.setdefault(k, []):
                filters[k].append(v)
    filters = {k: sorted(v) for k, v in filters.items()}
    return render_template("projects.html", folders=folders, folder=folder, q="", designs=designs, filters=filters, fseries=fseries,
                           total=sum(dcounts.values()), active_nav="프로젝트")


@bp.route("/design/<series>/<design>")
def page_design(series, design):
    """디자인 상세 — 구성(기준 PDF 면 묶음) + 큰 그림. 편집기에서 편집 · 확인 완료 · 삭제."""
    from routes.catalog import _ID, design_layouts, template_info
    t = template_info(series)
    if not t or not _ID.match(design):
        abort(404)
    d = next((x for x in t["designs"] if x["id"] == design), None)
    if not d:
        abort(404)
    lay = design_layouts(series, design)          # 지면 형태(지문만 다른 면은 하나로) + 전체 면수
    if re.search(r"\d+면$", d.get("desc") or ""):    # 용어 바꾸기(2026-10-13) 전에 등록된 설명 「… · 12면」 — 화면에는 페이지로
        d = dict(d, desc=re.sub(r"(\d+)면$", r"\1페이지", d["desc"]))
    # 페이지 틀 · 견본 사진은 기준 PDF 가 없을 때만 큰 그림에 — 있으면 구성(실제 면)으로 충분하다
    pages = [] if lay["total"] else \
            [{"src": f"/catalog/master/{series}/{design}/{m['file']}", "label": m["label"], "kind": "상위 페이지", "page": m.get("page")} for m in d["masters"]] \
          + [{"src": f"/catalog/preview/{series}/{design}/{p}", "label": f"미리 보기 {i + 1}", "kind": "미리 보기"} for i, p in enumerate(d["previews"])]
    return render_template("design_detail.html", t=t, d=d, pages=pages, total=lay["total"], layouts=lay["layouts"],
                           faces=lay.get("faces"), origin=lay.get("origin"), active_nav="프로젝트")
