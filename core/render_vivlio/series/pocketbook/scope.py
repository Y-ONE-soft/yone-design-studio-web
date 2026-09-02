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

# 라벨 방언은 학교마다 다르다 — 코퍼스 실측 기준(1,352지문):
#   교과서  `4과 01` `1과 본문2` `2과 FR` `3과 RC1` `1과 DL` `2과 추가`
#   강      `11강 02` `11강 분석` `올포 15강 1` `마더텅 5강 3번` `올림포스 9강`
#   리딩파워 `Unit 13 - 2` `Unit 13 Ex 1` `Unit 13 Example 1` `Unit 14 01`
#   모의고사 `231124`(6자리)
RE_LESSON = re.compile(r"(\d{1,2})\s*과")
RE_UNIT = re.compile(r"(?:(\d{1,2})\s*강|\bUnit\s*(\d{1,2}))", re.I)
RE_PNO = re.compile(r"(\d{2})(\d{2})(\d{2})")
RE_FIRST_NO = re.compile(r"\d{1,3}")
RE_YM = re.compile(r"(\d{2})\s*년\s*(\d{1,2})\s*월")
RE_NO = re.compile(r"(\d{1,3})\s*번")
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


# ── 지문 → [(토큰, 번호), …] ─────────────────────────────────────
#
# ⚠ 한 지문이 **두 군데 소속**일 수 있다. 마더텅 11강 2번은 동시에 고1 23년
#   11월 33번 기출이다(한영1 실측: `label='고1 23년 11월 33번'` +
#   `chapter='11강 2번'`). 하나만 고르면 나머지 하나로 적힌 시험범위와 못 만나
#   멀쩡히 있는 지문이 "없다"고 나온다. 그래서 짝을 **여러 개** 돌려준다.
def pairs_of(row):
    """포켓북 지문 → [(토큰, 지문 번호), …]. 못 알아보면 []."""
    if row.get("_tok") is not None:
        return row["_tok"]
    return own_pairs(row)


def own_pairs(row):
    out = []
    label = str(row.get("label") or row.get("key") or "")
    for cand in (str(row.get("pno") or row.get("no") or ""), label):
        m = RE_PNO.fullmatch(cand.strip())
        if m:
            out.append((("mock", int(m.group(1)), int(m.group(2))),
                        int(m.group(3))))
            break
    if not out:                       # 회차를 풀어 적은 꼴 — `고1 23년 11월 33번`
        for src in (label, str(row.get("chapter") or "")):
            ym, no = RE_YM.search(src), RE_NO.search(label)
            if ym and no:
                out.append((("mock", int(ym.group(1)), int(ym.group(2))),
                            int(no.group(1))))
                break
    for i, src in enumerate((label, str(row.get("chapter") or ""),
                             str(row.get("unit") or ""))):
        m = RE_UNIT.search(src)       # 강이 먼저다 — `올포 15강` 은 과가 아니다
        if m:
            n = int(m.group(1) or m.group(2))
            no = _tail_no(src, m.end())
            if no is None and i:
                no = _tail_no(label, 0)
            out += [((k, n), no) for k in _UNIT_KINDS]
            break
        m = RE_LESSON.search(src)
        if m:
            no = _tail_no(src, m.end())
            if no is None and i:
                no = _tail_no(label, 0)
            out.append((("lesson", int(m.group(1))), no))
            break
    return out


def annotate(rows):
    """앞 지문의 단원을 **이어받아** 각 지문의 토큰을 정한다.

    분석본은 회차·단원을 묶음 **첫 지문에만** 적는다 — 뒤 지문은 머리말이
    빈칸이라 `Exercise 02`·`MR4`·`22번` 만 남는다. 이대로 범위와 대면 멀쩡히
    있는 지문이 "없다"고 나온다(실측: 서울여고1 수능특강 11강, 명일2 교과서
    1과, 한영2 25년 9월 — 전부 헛경보였다).

    ⚠ 라벨·머리말 자체는 **건드리지 않는다**. 배지에 찍히는 글이라 손대면
      이미 나간 책과 달라진다. 이어받은 결과는 `_tok` 에만 담는다.
    """
    last = None
    for r in rows:
        got = own_pairs(r)
        if got:
            last = [t for t, _n in got]
        elif last:
            no = _tail_no(str(r.get("label") or ""), 0)
            got = [(t, no) for t in last]
        r["_tok"] = got


def _tail_no(label, at):
    """단원 표기 **뒤에** 처음 나오는 수 = 지문 번호.

    사이에 무엇이 끼든(`- 2` `Ex 1` `본문2` `RC1` `01`) 상관없이 잡힌다.
    뒤에 수가 없으면(`11강 분석` `Unit 13 Ex`) 번호 없는 지문이다.
    """
    m = RE_FIRST_NO.search(label, at)
    return int(m.group(0)) if m else None


def _key(t):
    return tuple(t)


def match(row, scope):
    """이 지문이 **어느 이름으로** 범위에 드는가 → 토큰, 아니면 None."""
    if not scope:
        return None
    detail = scope.get("detail") or {}
    keys = {_key(t): t for t in scope.get("tokens", [])}
    for c, no in pairs_of(row):
        t = keys.get(_key(c))
        if t is None:
            continue
        d = detail.get(t) or {}
        only, excl = d.get("only"), d.get("exclude")
        if no is None:                   # 번호 없는 지문 — 부속물, 남긴다
            return t
        if excl and no in excl:
            continue
        if only and no not in only:
            continue
        return t
    return None


def matches(row, scope):
    """이 지문이 범위 안인가.

    ⚠ 못 알아본 라벨은 **남긴다**. 조용히 빼는 쪽이 훨씬 나쁘기 때문이다
      (부속물·외부지문은 라벨 규칙 밖에 있다).
    """
    if not scope or not pairs_of(row):
        return True
    return match(row, scope) is not None


BIG = 10 ** 6


def sort_key(row, scope):
    """범위가 적힌 차례를 따른다 — 범위가 곧 책의 차례다.

    ⚠ 범위 **밖** 지문은 (BIG, BIG) 을 돌려준다. 여기서 번호를 섞어 내보내면
      범위와 무관한 지문들이 번호순으로 재배열돼 원래 차례가 무너진다
      (실측: 한영1 은 범위 안 지문이 하나도 없어 52지문이 통째로 뒤섞였다).
      부르는 쪽이 원래 자리를 마지막 열쇠로 붙여 안정 정렬을 만든다.
    """
    t = match(row, scope)
    if t is None:
        return (BIG, BIG)
    order = {_key(x): i for i, x in enumerate(scope.get("tokens", []))}
    no = next((n for c, n in pairs_of(row) if _key(c) == _key(t)), None)
    return (order.get(_key(t), BIG), no if no is not None else BIG)


def missing(scope, rows):
    """범위가 부르는데 **없는** 지문 → [{"text":…, "hard":True/False}].

    지문 번호를 짚어 준 토큰(`only`)만 낱낱이 셀 수 있다. 번호를 안 짚은
    토큰(`교과서 1과`)은 몇 개가 맞는지 알 길이 없으므로 **하나도 없을 때만**
    말한다 — 모르는 것을 아는 척하지 않는다.

    무게가 다르다:
      hard  단원이 **통째로** 비었다 → 의심의 여지가 없다(막는다)
      soft  번호 몇 개가 빈다 → 시험범위 표의 번호 매김이 우리와 다를 수 있다
            (실측: 상일1 `26년 9월 1~17번`). 알리되 막지는 않는다.
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
        if not got:
            out.append({"text": "%s — 지문이 하나도 없음" % name(t),
                        "hard": True})
        elif only:
            gap = [n for n in only if n not in got]
            if gap:
                out.append({"text": "%s — %s번 없음"
                                    % (name(t), ", ".join(str(n) for n in gap)),
                            "hard": False})
    return out
