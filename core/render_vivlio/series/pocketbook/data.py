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


_MT = re.compile(r"(\d+)\s*\[([^\]]*)\]")


def format_memtest(runs, answer):
    """암기테스트 본문 → 번호·정답이 구분된 런.

    ⚠ 원본 스토리에는 **문자 스타일이 없다** — `138[famous]` 라는 글자만 있고
      위첨자·주황색은 로컬 서식이라 IDML 런에 안 남는 책이 있다(실측: 런 2개로
      1,761자). 그래서 서식을 읽지 말고 **표기에서 되만든다**.
      `숫자[낱말]` 은 이 교재의 고정 표기이고, 리뷰테스트 원고도 같은 표기를 쓴다.
    """
    text = "".join(r["t"] for r in runs)
    out, at = [], 0
    for m in _MT.finditer(text):
        if m.start() > at:
            out.append({"t": text[at:m.start()]})
        out.append({"t": m.group(1), "mark": "num"})
        out.append({"t": "["})
        word = m.group(2)
        if word:
            out.append({"t": word, "mark": None if answer else "blank",
                        "color": None} if not answer else
                       {"t": word, "mark": "red"})
        out.append({"t": "]"})
        at = m.end()
    if at < len(text):
        out.append({"t": text[at:]})
    return out or list(runs)


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
            ans = bool(p.get("answer"))
            src = p.get("body_runs") or _flatten(p.get("body"))
            out.append({"kind": "memtest", "answer": ans,
                        "key": p.get("key") or "",
                        "runs": format_memtest(src, ans),
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
