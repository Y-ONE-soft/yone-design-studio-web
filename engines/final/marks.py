# -*- coding: utf-8 -*-
"""지문 정오표 — 한 학교에서 고친 것이 **같은 지문을 쓰는 다른 학교에도** 간다.

## 왜 책 폴더의 정오표로는 안 되는가

`core/render_vivlio/edits.py` 의 편집 이력은 **책 한 권**의 것이다. 자리표가
`lessons.0.problems.3.stem` 처럼 그 책의 차례에 매여 있어서, 같은 지문이라도
학교가 다르면 자리가 달라 얹히지 않는다. 파이널 직전보충은 학교마다 새 책을
만들지만 **지문은 같은 원고를 돌려 쓴다** — 연구원이 광문1에서 잡은 오탈자는
같은 올포 3강을 쓰는 상일1에서도 그대로 나온다.

그래서 여기는 자리가 아니라 **글자와 지문 이름**으로 적는다.

    { "올포 3강 본문2": { "book": "올림포스 독해기본2", "fixes": [
        {"sec": "문장배열", "from": "recieve", "to": "receive",
         "why": "철자", "at": "2026-09-11", "src": "광문1 26-2-중간"} ]}}

`from` 이 그 지문 안에 있으면 어느 책이든 얹힌다. 학교·시험기간·권 번호와
무관하다. 지문 이름(`올포 3강 본문2`)은 원고에서 나오므로 학교가 달라도 같다.

## 얹는 자리

`scripts/final_manuscript_build.build()` 끝 — 원고를 다 읽어 content 를 세운
직후다. 조판도 검수도 얹힌 뒤의 글을 본다.

⚠ 정오표는 **원고가 틀렸을 때의 임시 처방**이다. 교재팀이 원고를 고치면 그
  줄을 지우는 것이 맞다. 그래서 `from` 을 못 찾으면 조용히 넘기지 않고
  **말한다** — 원고가 고쳐졌다는 뜻일 수 있기 때문이다.
"""
import datetime
import json
import os
import re
import unicodedata

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
PATH = os.path.join(BASE, "data", "final_marks.json")

NOTE = ("파이널 직전보충 지문 정오표. 지문 이름과 글자로 걸어 두므로 "
        "같은 지문을 쓰는 다른 학교 책에도 그대로 얹힌다. "
        "교재팀이 원고를 고치면 해당 줄을 지울 것.")

# 어디를 뒤지는가 — (권, 칸, 블록 안에서 글이 사는 열쇠들)
FIELDS = (
    ("vol1", "문장배열", ("items", "passage")),
    ("vol1", "문장삽입", ("paras", "given")),
    ("vol2", "서술형영작", ("korean", "english", "choices")),
)


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── 파일 ────────────────────────────────────────────────────────────────
def read(path=None):
    p = path or PATH
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
    except ValueError:
        return {}
    return {k: v for k, v in d.items() if not k.startswith("_")}


def write(table, path=None, log=None):
    p = path or PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    out = {"_note": NOTE}
    out.update({k: table[k] for k in sorted(table)})
    json.dump(out, open(p, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if log:
        log("  지문 정오표 %d지문 → %s" % (len(table), os.path.relpath(p, BASE)))
    return p


def add(label, frm, to, why="", src="", book="", sec="", path=None):
    """한 건 쌓기. 같은 `from` 이 이미 있으면 덮어쓴다(마지막 판단이 이긴다)."""
    t = read(path)
    ent = t.setdefault(nfc(label), {"book": book, "fixes": []})
    if book and not ent.get("book"):
        ent["book"] = book
    fix = {"sec": sec, "from": nfc(frm), "to": nfc(to), "why": why,
           "at": datetime.date.today().isoformat(), "src": src}
    ent["fixes"] = [f for f in ent["fixes"] if f["from"] != fix["from"]]
    ent["fixes"].append(fix)
    write(t, path)
    return fix


# ── 얹기 ────────────────────────────────────────────────────────────────
def _sub(val, frm, to):
    """글 하나 또는 글 목록에서 `frm` → `to`. (바뀐 값, 바꾼 횟수)."""
    if isinstance(val, list):
        out, n = [], 0
        for x in val:
            y, k = _sub(x, frm, to)
            out.append(y)
            n += k
        return out, n
    if not isinstance(val, str):
        return val, 0
    if frm not in nfc(val):
        return val, 0
    s = nfc(val)
    return s.replace(frm, to), s.count(frm)


def _blocks(content):
    """(지문 이름, 담고 있는 dict, 뒤질 열쇠들) 훑기."""
    for vol, sec, keys in FIELDS:
        for b in (content.get(vol) or {}).get(sec) or []:
            if isinstance(b, dict):
                yield nfc(b.get("header", "")), sec, b, keys
    # 어법수정은 [머리, 몸, 머리, 몸, …] 로 납작하다 — 짝으로 훑는다.
    g = (content.get("vol2") or {}).get("어법수정") or []
    for i in range(0, len(g) - 1, 2):
        yield nfc(g[i]), "어법수정", g, (i + 1,)


def apply(content, table=None, log=None, src=""):
    """정오표를 content 에 얹는다. 얹힌 수와 못 찾은 목록을 돌려준다.

    지문 이름이 그 책에 없으면 **그냥 넘긴다** — 그 학교 범위가 아닐 뿐이다.
    이름은 있는데 글자를 못 찾으면 **말한다** — 원고가 바뀌었다는 뜻이다.
    """
    table = read() if table is None else table
    if not table:
        return {"hit": 0, "miss": [], "labels": 0}
    # 한 지문의 글은 배열·삽입·어법·영작에 되풀이해 실린다. 고침은 **나오는
    # 곳마다** 얹어야 한다 — 한 군데만 고치면 같은 지문 안에서 글이 갈린다.
    # 그래서 못 찾음은 칸마다가 아니라 **고침 한 건 단위**로 센다.
    hit, labels = 0, set()
    tried = {}                      # (지문, 원문) → 얹힌 횟수
    for label, sec, holder, keys in _blocks(content):
        ent = table.get(label)
        if not ent:
            continue
        for fix in ent.get("fixes", []):
            if fix.get("sec") and fix["sec"] != sec:
                continue
            k0 = (label, fix["from"])
            tried.setdefault(k0, 0)
            for k in keys:
                try:
                    val = holder[k]
                except (KeyError, IndexError, TypeError):
                    continue
                new, c = _sub(val, fix["from"], fix["to"])
                if c:
                    holder[k] = new
                    hit += c
                    tried[k0] += c
                    labels.add(label)
    miss = [k for k, n in tried.items() if not n]
    if log and hit:
        log("■ 지문 정오표 %d곳 얹음 (%d지문)" % (hit, len(labels)))
    if log and miss:
        # 이름은 책에 있는데 글자가 없다 — 원고가 고쳐졌는지 볼 것.
        for lab, frm in miss:
            log("  [정오표 경고] %s — 원문을 못 찾음: %s" % (lab, frm[:40]))
    return {"hit": hit, "miss": miss, "labels": len(labels)}


# ── 지문 찾기 (PDF 주석 → 어느 지문인가) ────────────────────────────────
def _norm(s):
    return re.sub(r"\s+", " ", nfc(s)).strip()


def _loose(s):
    """줄바꿈·공백·붙임표를 지운 비교용 — PDF 에서 뜬 글은 줄이 잘려 온다."""
    return re.sub(r"[\s­\-‐-―]+", "", nfc(s))


def locate(content, text):
    """글 한 조각이 **어느 지문의 어느 칸**에 있는지. [(지문, 칸, 원문)] 목록.

    PDF 에서 뜬 글은 줄바꿈으로 잘려 있어 그대로는 안 맞는다 — 공백을 지우고
    맞춘 뒤, 원문 쪽에서 그 자리를 도로 잘라 돌려준다(그래야 `from` 이 된다).
    """
    want = _loose(text)
    if len(want) < 6:
        return []
    out = []
    for label, sec, holder, keys in _blocks(content):
        for k in keys:
            try:
                val = holder[k]
            except (KeyError, IndexError, TypeError):
                continue
            for s in (val if isinstance(val, list) else [val]):
                if not isinstance(s, str):
                    continue
                cut = _cut(s, want)
                if cut:
                    out.append((label, sec, cut))
    return out


def _cut(hay, want_loose):
    """`hay` 안에서 공백 무시 일치 구간을 찾아 **원문 그대로** 돌려준다."""
    idx, keep = [], []
    for i, ch in enumerate(nfc(hay)):
        if not re.match(r"[\s­\-‐-―]", ch):
            keep.append(ch)
            idx.append(i)
    j = "".join(keep).find(want_loose)
    if j < 0:
        return None
    return nfc(hay)[idx[j]:idx[j + len(want_loose) - 1] + 1]
