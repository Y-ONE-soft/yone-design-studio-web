# -*- coding: utf-8 -*-
"""지문 코퍼스 → 조판용 data.

입력은 `tools/pocket_harvest/idml.py` 가 내는 모양(완성본 수확)이거나 코퍼스
JSON 이다. 둘의 필드 이름을 같게 맞춰 뒀으므로 여기서는 **지면이 바로 쓸 수 있는
꼴**로만 눕힌다(문단 → 런 목록, 링크 → 파일 경로).
"""
import os
import re
import shutil
import unicodedata


def _flatten(paras):
    """문단 목록 → 런 하나짜리 흐름. 문단 사이에는 공백을 넣는다.

    포켓북 지문은 한 덩이로 흐른다(분석본처럼 문장마다 끊지 않는다).
    """
    out = []
    for i, p in enumerate(paras or ()):
        if i:
            out.append({"t": " ", "mark": None, "hl": None, "ruby": None})
        out.extend(p["runs"])
    return out


def _plain(paras):
    return " ".join(
        "".join(r["t"] for r in p["runs"]).strip() for p in (paras or ())).strip()


_URI = re.compile(r"^file://")


def _resolve_link(uri, search_dirs):
    """IDML LinkResourceURI → 실제 파일. 없으면 파일명으로 찾아본다."""
    if not uri:
        return None
    path = _URI.sub("", uri)
    path = unicodedata.normalize("NFC", path)
    if os.path.exists(path):
        return path
    base = os.path.basename(path)
    for d in search_dirs or ():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if unicodedata.normalize("NFC", f) == base:
                    return os.path.join(root, f)
    return None


def prepare(items, build_dir, illust_dirs=(), category=""):
    """수확 결과 → 지면 항목. 그림은 build 로 복사한다.

    입력은 **지면 순서 목록**이다(지문과 암기테스트가 섞여 있다). 암기테스트를
    직전 지문에 매달면 교과서처럼 여러 지문을 묶는 책에서 어긋난다.
    """
    assets = os.path.join(build_dir, "img")
    os.makedirs(assets, exist_ok=True)
    out = []
    for i, p in enumerate(items):
        if p.get("kind") == "memtest":
            out.append({"kind": "memtest", "answer": bool(p.get("answer")),
                        "runs": _flatten(p.get("body")),
                        "category": p.get("category") or category})
            continue
        illust = None
        for uri in p.get("links") or ():
            src = _resolve_link(uri, illust_dirs)
            if src and os.path.splitext(src)[1].lower() in (
                    ".jpg", ".jpeg", ".png"):
                dst = os.path.join(assets, "p%03d%s" % (i, os.path.splitext(src)[1]))
                try:
                    shutil.copyfile(src, dst)
                    illust = "img/" + os.path.basename(dst)
                except OSError:
                    illust = None
                break
        mt = p.get("memtest") or {}
        out.append({
            "kind": "passage",
            "key": p.get("key") or p.get("pno") or p.get("label") or "",
            "no": p.get("pno") or "",
            "label": p.get("label") or "",
            "category": p.get("category") or category,
            "passage_runs": _flatten(p.get("passage")),
            "translation": _plain(p.get("translation")),
            "flownote": p.get("flownote") or [],
            "topic": p.get("topic") or "",
            "summary": p.get("summary") or "",
            "synonyms": p.get("synonyms") or [],
            "illust": illust,
            "memtest": {k: _flatten(v) for k, v in mt.items() if v} or None,
        })
    return out
