# -*- coding: utf-8 -*-
"""시험범위의 **정본을 갈아 끼우는 자리**.

지금까지 워크북 파일 이름(`…(리딩파워12강,14강)…`)을 읽은 건 워크북이
필요해서가 **아니다**. 범위를 적어 둔 곳이 거기밖에 없었기 때문이다.
정본(Y.OS `/work/exam`)이 생기면 파일 이름을 읽는 자리는 통째로 없어진다.

그래서 범위를 **한 가지 모양**으로 좁혀 둔다 — 어디서 왔든 토큰 목록이다:

    ("lesson", 4)      교과서 4과
    ("olpo",  15)      올림포스 15강
    ("rp",    12)      리딩파워 12강
    ("teuk",  18)      수능특강 18강
    ("bare",  18)      접두 없는 18강(고3 분석편 파일 이름 방언)
    ("test",   2)      Test 2
    ("mock", 25, 3)    25년 3월 모의고사

`manuscript_locate.folders_for()` 가 이 토큰을 그대로 받아 원고 폴더를 찾고,
`manuscript.py` 가 그 폴더를 읽는다. 즉 **정본이 바뀌어도 아래쪽은 그대로**다.

출처는 셋이고 믿는 차례가 있다:

    1. yos       Y.OS 시험범위 (정본)
    2. filename  워크북 파일 이름 (지금까지 쓰던 것 — 정본이 없을 때만)
    3. content   이미 만든 content.json 의 섹션 합집합 (교차검증용)

두 출처가 어긋나면 **침묵하지 않는다** — `cross_check()` 가 차이를 돌려준다.
범위가 틀리면 지문이 조용히 빠지거나 남의 지문이 들어온다.
"""
import json
import os
import re
import urllib.request

from engines.final import manuscript_locate as L


# ── 모양 ────────────────────────────────────────────────────────────────
KIND_NAMES = {
    "lesson": "교과서", "olpo": "올림포스", "rp": "리딩파워",
    "teuk": "수능특강", "bare": "강", "test": "Test", "mock": "모의고사",
}


def token_text(t):
    """토큰 → 사람이 읽는 한 마디."""
    if t[0] == "mock":
        return "%d년 %d월 모의고사" % (t[1], t[2])
    if t[0] == "lesson":
        return "교과서 %d과" % t[1]
    if t[0] == "test":
        return "Test %d" % t[1]
    name = KIND_NAMES.get(t[0], t[0])
    return ("%s %d강" % (name, t[1])).strip() if name != "강" else "%d강" % t[1]


def _uniq(tokens):
    seen, out = set(), []
    for t in tokens:
        t = tuple(t)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ── 1. Y.OS(정본) ───────────────────────────────────────────────────────
#
# ⚠ 아직 붙이지 않았다. Y.OS 가 돌려주는 칸 이름을 확인하고 `_yos_tokens()`
#   한 함수만 채우면 된다 — 아래 `from_yos()` 는 이미 그 자리에 맞춰 뒀다.
#
YOS_BASE = os.environ.get("YOS_BASE", "https://yos-core-web.vercel.app")


def _yos_get(path, token=None, timeout=20):
    req = urllib.request.Request(YOS_BASE.rstrip("/") + path)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# 계열 이름 — 사람이 적는 말투를 다 받는다
SERIES = (
    ("teuk", ("수능특강", "수특")),
    ("rp", ("리딩파워", "reading power", "리딩 파워")),
    ("olpo", ("올림포스", "올포")),
)
# `18,19,21강` · `15~18강` · `3,6,7,11강` — **`강` 으로 끝나는 숫자 묶음**만
# 강 번호다. `독해기본1`·`유형편(40지문)` 의 숫자는 교재 이름이라 걸리지 않는다.
RE_UNIT_RUN = re.compile(r"((?:\d{1,2}\s*[,~\-]\s*)*\d{1,2})\s*강")
RE_LESSON_RUN = re.compile(r"((?:\d{1,2}\s*[,~\-]\s*)*\d{1,2})\s*과")
RE_MOCK_TXT = re.compile(r"(\d{2})\s*년\s*(\d{1,2})\s*월")
RE_TEST_TXT = re.compile(r"[Tt]est\s*(\d)")
RE_SPLIT = re.compile(r"[/·\n;]+")


def _nums(run):
    """`3,6,7` · `15~18` → [3,6,7] · [15,16,17,18]."""
    out = []
    for a, b in re.findall(r"(\d{1,2})\s*[~\-]\s*(\d{1,2})", run):
        out += list(range(int(a), int(b) + 1))
    rest = re.sub(r"\d{1,2}\s*[~\-]\s*\d{1,2}", "", run)
    out += [int(u) for u in re.findall(r"\d{1,2}", rest)]
    return out


def scope_text_tokens(text):
    """시험범위를 적은 **글**에서 토큰을 읽는다.

    파일 이름 파서를 그대로 쓸 수 없다 — 파일 이름은 괄호 안이 범위지만
    글에서는 괄호가 출판사(`미래엔(김)`)나 군더더기(`(40지문)`)이고,
    계열 이름과 숫자 사이에 교재 이름이 낀다(`올림포스 독해기본1 15~18강`).

    그래서 형식이 아니라 **자리**로 읽는다:
      · 계열은 토막(`/` 로 끊은 한 도막) 안에서 찾고,
      · 강 번호는 **`강` 으로 끝나는 숫자 묶음**만 센다
        (`독해기본1` 의 1 은 교재 이름이라 걸리지 않는다),
      · 계열 이름이 없으면 `bare` — 고3 분석편 방언이다.
    """
    out = []
    for seg in RE_SPLIT.split(text or ""):
        if not seg.strip():
            continue
        # 계열 표시가 나오는 자리를 적어 두고, 숫자 묶음마다 **바로 앞의**
        # 계열을 준다. 한 도막에 두 계열이 겹쳐 적혀 있어도 갈라진다.
        marks = []
        low = seg.lower()
        for k, words in SERIES:
            for w in words:
                i = 0
                while True:
                    i = low.find(w, i)
                    if i < 0:
                        break
                    marks.append((i, k))
                    i += 1
        marks.sort()
        for m in RE_UNIT_RUN.finditer(seg):
            kind = "bare"
            for i, k in marks:
                if i < m.start():
                    kind = k
                else:
                    break
            out += [(kind, u) for u in _nums(m.group(1))]
        for m in RE_LESSON_RUN.finditer(seg):
            out += [("lesson", u) for u in _nums(m.group(1))]
        for yy, mm in RE_MOCK_TXT.findall(seg):
            out.append(("mock", int(yy), int(mm)))
        for t in RE_TEST_TXT.findall(seg):
            out.append(("test", int(t)))
    return _uniq(out)


def from_yos(school, grade, period, token=None, fetch=None):
    """Y.OS 시험범위 → Scope. `fetch` 를 주면 그걸로 부른다(시험용).

    돌려주는 것: {"tokens": […], "raw": 원문, "source": "yos"}
    """
    get = fetch or (lambda p: _yos_get(p, token))
    rows = get("/api/exam-scopes?school=%s&grade=%s&period=%s"
               % (school, grade, period))
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or [rows]
    raw = " / ".join(
        str(r.get("scope") or r.get("range") or r.get("text") or "")
        for r in rows or [])
    return {"tokens": scope_text_tokens(raw), "raw": raw, "source": "yos"}


# ── 2. 워크북 파일 이름(폴백) ────────────────────────────────────────────
def from_workbook_names(names):
    out = []
    for n in sorted(set(names or [])):
        out += L.parse_tokens(n)
    return {"tokens": _uniq(out), "raw": " / ".join(sorted(set(names or []))),
            "source": "filename"}


# ── 3. 이미 만든 content.json(교차검증) ─────────────────────────────────
RE_TB = re.compile(r"^교과서(\d+)과")
RE_UNIT = re.compile(r"^(올포|리딩파워)\s*(\d+)강")
RE_MOCK = re.compile(r"^(\d{2})(\d{2})\d{2}")
RE_G3 = re.compile(r"^(?:(\d+)강|test(\d+))")


def from_labels(labels):
    """파이널 라벨 목록 → 토큰. 조판된 결과가 실제로 어느 범위인지 되읽는다."""
    out = []
    for lab in labels or []:
        m = RE_TB.match(lab)
        if m:
            out.append(("lesson", int(m.group(1))))
            continue
        m = RE_UNIT.match(lab)
        if m:
            out.append(("olpo" if m.group(1) == "올포" else "rp",
                        int(m.group(2))))
            continue
        m = RE_MOCK.match(lab)
        if m:
            out.append(("mock", int(m.group(1)), int(m.group(2))))
            continue
        m = RE_G3.match(lab)
        if m:
            if m.group(1):
                out.append(("bare", int(m.group(1))))
            else:
                out.append(("test", int(m.group(2))))
    return {"tokens": _uniq(out), "raw": "", "source": "content"}


# ── 교차검증 ────────────────────────────────────────────────────────────
_SAME = {"olpo": "unit", "rp": "unit", "teuk": "unit", "bare": "unit"}


def _key(t):
    """강 계열은 접두어가 출처마다 다르다 — 숫자로만 견준다."""
    if t[0] in _SAME:
        return ("unit", t[1])
    return tuple(t)


def cross_check(a, b):
    """두 범위의 차이. {"only_a": [...], "only_b": [...]} — 빈 값이면 같다."""
    ka = {_key(t): t for t in a.get("tokens", [])}
    kb = {_key(t): t for t in b.get("tokens", [])}
    return {"only_a": [ka[k] for k in ka if k not in kb],
            "only_b": [kb[k] for k in kb if k not in ka]}


def describe(scope):
    return "%s: %s" % (scope.get("source", "?"),
                       ", ".join(token_text(t) for t in scope["tokens"])
                       or "(없음)")
