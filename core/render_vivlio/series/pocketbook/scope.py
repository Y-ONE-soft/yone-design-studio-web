# -*- coding: utf-8 -*-
"""수록 범위 = **Y.OS 시험범위**. 그 범위의 지문은 전부 들어간다.

## 왜 이 파일이 생겼나

처음엔 카드에 "기존 지문도 넣기"라는 **선택**을 뒀다. 잘못이었다.
포켓북의 수록 범위는 사람이 고르는 것이 아니라 **정해져 있다** — 그 학교
그 시험의 범위다. 지문이 분석본에서 오든 코퍼스에서 오든 그건 **안쪽 사정**이지
사용자가 알 바가 아니다. 사용자가 고르게 두면 두 가지가 조용히 망가진다:

  · 켜는 걸 잊으면 **범위 안 지문이 빠진 책**이 나간다(겉으로 멀쩡하다)
  · 켜면 범위 밖 지문까지 들어온다

그래서 범위를 **정본에서 읽고**, 있는 것을 채우고, **없는 것을 말한다.**

## 범위는 지문 번호까지 온다

`engines/final/scope_source.py` 가 이미 Y.OS 를 읽는다(파이널이 쓰던 것).
토큰과 함께 `detail[token]["only"]` 로 지문 번호까지 짚어 준다:

    ("lesson", 1)              교과서 1과 (지문 지정 없음 = 전부)
    ("mock", 26, 6)  only[20, 29, 30, …]   26년 6월 모의고사 그 번호만

## 포켓북 라벨 → 토큰

파이널과 포켓북은 라벨 방언이 다르다(`4과 본문1` vs `1과 01`, `250923`).
그래서 `scope_source.in_scope` 를 그대로 쓰지 않고 여기서 다시 읽는다.
강 계열(`11강 02`)은 올포·리딩파워·수능특강·맨숫자를 **가리지 않는다** —
포켓북 라벨에는 그 구분이 없고, 한 시험에 같은 번호의 다른 교재가 겹치는 일은
사실상 없다. 겹치면 `missing()` 이 말해 준다.
"""
import re

RE_LESSON = re.compile(r"^\s*(\d{1,2})\s*과\s*(\d{1,3})?")
RE_UNIT = re.compile(r"^\s*(\d{1,2})\s*강\s*(\d{1,3})?")
RE_PNO = re.compile(r"^(\d{2})(\d{2})(\d{2})")
_UNIT_KINDS = ("olpo", "rp", "teuk", "bare")


def load(school, term, grade, log=lambda m: None):
    """Y.OS 시험범위. 못 읽으면 None (조판은 멈추지 않고, 대신 말한다)."""
    try:
        from engines.final import scope_source as S
    except ImportError:
        log("[범위] 시험범위 모듈을 못 불러왔다 — 범위 없이 조판한다")
        return None
    try:
        sc = S.from_sheet(school, term, grade=_grade_num(grade), log=log)
    except Exception as e:
        log("[범위] 시험범위를 못 읽었다 (%s) — 범위 없이 조판한다" % str(e)[:60])
        return None
    if not sc or not sc.get("tokens"):
        return None
    sc["_text"] = ", ".join(S.token_text(t) for t in sc["tokens"])
    return sc


def _grade_num(grade):
    d = "".join(c for c in str(grade or "") if c.isdigit())
    return int(d) if d else 0


# ── 지문 → (토큰 후보, 번호) ────────────────────────────────────────
def token_of(row):
    """포켓북 지문 → (토큰 후보 목록, 지문 번호). 모르면 ([], None)."""
    pno = str(row.get("pno") or row.get("no") or "")
    m = RE_PNO.match(pno)
    if m:
        yy, mm, nn = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return [("mock", yy, mm)], nn
    label = str(row.get("label") or row.get("key") or "")
    m = RE_LESSON.search(label)
    if m:
        return [("lesson", int(m.group(1)))], _int(m.group(2))
    m = RE_UNIT.search(label)
    if m:
        n = int(m.group(1))
        return [(k, n) for k in _UNIT_KINDS], _int(m.group(2))
    return [], None


def _int(v):
    return int(v) if v and str(v).isdigit() else None


def _key(t):
    return tuple(t)


def matches(row, scope):
    """이 지문이 범위 안인가.

    ⚠ 못 알아본 라벨은 **남긴다**. 조용히 빼는 쪽이 훨씬 나쁘기 때문이다
      (부속물·외부지문은 라벨 규칙 밖에 있다).
    """
    if not scope:
        return True
    cands, no = token_of(row)
    if not cands:
        return True
    detail = scope.get("detail") or {}
    keys = {_key(t): t for t in scope.get("tokens", [])}
    for c in cands:
        t = keys.get(_key(c))
        if t is None:
            continue
        d = detail.get(t) or {}
        only, excl = d.get("only"), d.get("exclude")
        if no is None:                       # 번호 없는 지문 — 부속물, 남긴다
            return True
        if excl and no in excl:
            return False
        return (no in only) if only else True
    return False


def sort_key(row, scope):
    """범위가 적힌 차례를 따른다 — 범위가 곧 책의 차례다."""
    cands, no = token_of(row)
    order = {_key(t): i for i, t in enumerate(scope.get("tokens", []))} \
        if scope else {}
    pos = min([order.get(_key(c), 10 ** 6) for c in cands] or [10 ** 6])
    return (pos, no if no is not None else 10 ** 6,
            str(row.get("label") or row.get("key") or ""))


def missing(scope, rows):
    """범위가 부르는데 **없는** 지문. 사람이 읽는 말로 돌려준다.

    지문 번호를 짚어 준 토큰(`only`)만 셀 수 있다. 번호를 안 짚은 토큰
    (`교과서 1과`)은 몇 개가 맞는지 알 길이 없으므로 **지문이 하나도 없을 때만**
    말한다 — 모르는 것을 아는 척하지 않는다.
    """
    if not scope:
        return []
    try:
        from engines.final import scope_source as S
        name = S.token_text
    except ImportError:
        name = lambda t: str(t)            # noqa: E731
    have = {}
    for r in rows:
        cands, no = token_of(r)
        for c in cands:
            have.setdefault(_key(c), set()).add(no)
    out = []
    detail = scope.get("detail") or {}
    for t in scope.get("tokens", []):
        got = have.get(_key(t), set())
        only = (detail.get(t) or {}).get("only")
        if only:
            gap = [n for n in only if n not in got]
            if gap:
                out.append("%s — %s번 없음"
                           % (name(t), ", ".join(str(n) for n in gap)))
        elif not got:
            out.append("%s — 지문이 하나도 없음" % name(t))
    return out
