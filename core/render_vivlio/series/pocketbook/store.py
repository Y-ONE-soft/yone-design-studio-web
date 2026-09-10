# -*- coding: utf-8 -*-
"""포켓북 오른쪽 면 **창고** — 지문 하나가 파일 하나다.

왜 따로 두나
    `_authored/` 는 이름이 `26-2-중간_광문1__올림포스 5강 5강 01.json` 이라
    **책에 묶여 있었다**. 같은 지문이 다른 학교 포켓북에 또 나오면 이름이
    달라져 못 찾는다 — 연구원이 고쳐 놓은 것이 그 책 한 권에서만 살고
    다음 학교에서 처음부터 다시 나왔다.

    창고는 **글로 찾는다**. 기존 완성본을 가져오는 `_corpus` 와 같은 방식이라
    학교·학기·라벨이 달라도 같은 지문이면 같은 칸을 연다.

무엇이 이기나
    `fixed` 에 적힌 자리는 **사람이 손본 자리**다 — 무엇으로도 덮지 않는다.
    나머지는 빈 곳만 채운다(기계가 지은 것이므로 원고·완성본이 이긴다).
"""
import hashlib
import json
import os
import re
import time

_LET = re.compile(r"[^a-z]")


def letters(t):
    return _LET.sub("", (t or "").lower())


def key_of(text):
    """지문 글에서 뽑은 **열쇠** — 앞 400자로 낸 짧은 지문(指紋)."""
    s = letters(text)[:400]
    return hashlib.sha1(s.encode()).hexdigest()[:16] if len(s) >= 200 else ""


DEFAULT = "${STUDIO}/조판/교재/포켓북/_store"
# ⚠ `cfg` 없이 부를 때가 있다(주석 회수 같은 딸림 연장). 빈 문자열을 돌려
#   주면 조용히 아무 데도 안 쓴다 — 실제로 그랬다. 기본 자리를 못 박는다.
_HOME = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_store")


def root(cfg=None, opt=None):
    p = (opt or {}).get("store") if opt else None
    p = cfg.resolve(p or DEFAULT) if cfg else (p or _HOME)
    if isinstance(p, (list, tuple)):
        p = p[0] if p else ""
    return p or _HOME


FIELDS = ("flownote", "topic", "summary", "synonyms")

# 왼쪽 면(지문·해석·성분 태그)을 **분석본을 안 고치고** 바로잡는 자리.
#   ⚠ 창고 열쇠는 **고치기 전 지문 글**로 낸다. 그래야 분석본이 그대로인 한
#     다음 조판에서도 같은 칸이 열려 고친 게 따라온다. 나중에 분석본이 고쳐지면
#     글이 달라져 열쇠가 안 맞고 — 덧붙임이 두 번 먹지 않는다(저절로 풀린다).
PATCH = (
    "passage_tail",   # 지문 끝에 이어 붙일 글(원고에서 빠진 문장)
    "translation",    # 해석 전체를 갈아 끼움
    "ruby_fix",       # 성분 태그 고침 [{"w":낱말,"from":옛,"to":새}]
)


def index(path):
    """창고를 한 번 읽어 `[(글자열, 기록)]` 로 돌려준다.

    글 앞 120자가 들어 있는지로 맞댄다 — `_corpus` 와 같은 규칙이다.
    """
    out = []
    if not path or not os.path.isdir(path):
        return out
    for f in sorted(os.listdir(path)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(path, f), encoding="utf-8") as fh:
                r = json.load(fh)
        except Exception:
            continue
        t = letters(r.get("passage_text") or "")
        if len(t) >= 200:
            out.append((t[:400], r))
    return out


def find(idx, text):
    need = letters(text)
    if len(need) < 200:
        return None
    return next((r for k, r in idx if need[:120] in k), None)


def load(path, text):
    return find(index(path), text)


def put(path, text, fields, book="", label="", fixed=(), who=""):
    """창고에 넣는다. 이미 있으면 **적힌 자리만** 갈아 끼운다.

    `fixed` 에 적은 자리는 사람이 손본 것으로 새겨 둔다 — 다음부터 아무것도
    그 자리를 못 덮는다.
    """
    k = key_of(text)
    if not k:
        return ""
    os.makedirs(path, exist_ok=True)
    fp = os.path.join(path, k + ".json")
    rec = {}
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:
            rec = {}
    rec.setdefault("passage_text", text)
    rec.setdefault("label", label)
    rec.setdefault("first", book)
    books = rec.setdefault("books", [])
    if book and book not in books:
        books.append(book)
    for f in FIELDS + PATCH:
        if f in fields and fields[f]:
            rec[f] = fields[f]
    was = set(rec.get("fixed") or [])
    if fixed:
        was |= set(fixed)
        rec["by"] = who or rec.get("by") or ""
    rec["fixed"] = sorted(was)
    rec["at"] = time.strftime("%Y-%m-%d %H:%M")
    with open(fp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    return k
