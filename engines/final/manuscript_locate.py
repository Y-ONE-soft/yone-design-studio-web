# -*- coding: utf-8 -*-
"""파이널 원고 직독 — **시험범위 토큰 → 원고 폴더** 찾기.

워크북 파일 이름이 시험범위를 말한다:

    광문2_워크북01(리딩파워12강,14강)_내지.indd
    상일1_워크북03(올림포스15,16,17,18강,미래엔3,4과DL)_내지.indd
    광문2_워크북04(25년3월)_내지.indd

그 토큰 하나가 원고 폴더 하나를 가리킨다. 폴더 이름은 계열마다 다르지만
**구조는 같다** — 교재 폴더 아래 `… 워크북/` 이 있고 그 안에 `문장배열`·
`영작배열`·`빈칸어휘` 원고가 있다(`manuscript.py`).

이름을 글자 그대로 맞추지 않는다. 폴더 목록을 훑어 **숫자와 낱말**로 고른다 —
`올림포스 독해기본1 12강` · `Unit 12 워크북` · `고2 25년 3월` 처럼 표기가
제각각이고, 해마다 또 바뀐다.
"""
import os
import re
import unicodedata


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _squash(s):
    """비교용 — 공백·괄호·점을 지운다."""
    return re.sub(r"[\s().·,]", "", nfc(s))


def _dirs(path):
    if not path or not os.path.isdir(path):
        return []
    return [n for n in sorted(os.listdir(path))
            if os.path.isdir(os.path.join(path, n))
            and not n.startswith((".", "_", "~"))]


def _pick(root, want_num=None, words=(), avoid=(), num_unit=None):
    """`root` 아래에서 숫자와 낱말로 폴더 하나를 고른다.

    숫자는 **낱말 경계로** 본다 — `1강` 을 찾을 때 `11강` 이 걸리면 안 된다.

    `num_unit` 을 주면 그 단위에 **붙은** 숫자만 센다. 과목 이름에 숫자가
    들어가는 교과서에서 꼭 필요하다 — `공통영어2 능률(민) 1과` 에는 2 가
    들어 있어서, 아무 숫자나 세면 **2과를 찾다가 1과를 집는다**(실증).
    """
    best = None
    for name in _dirs(root):
        n = nfc(name)
        sq = _squash(n)
        if any(_squash(a) in sq for a in avoid):
            continue
        if words and not all(_squash(w) in sq for w in words):
            continue
        if want_num is not None:
            pat = r"(\d+)\s*" + re.escape(num_unit) if num_unit else r"\d+"
            nums = [int(x) for x in re.findall(pat, n)]
            if want_num not in nums:
                continue
        score = len(sq)                      # 짧은 이름이 더 정확한 짝
        if best is None or score < best[0]:
            best = (score, os.path.join(root, name))
    return best[1] if best else None


# ── 계열별 찾기 ──────────────────────────────────────────────────────────
def textbook(base, subject, publisher, lesson):
    """교과서 — `교과서 작업/<과목>/<과목 출판사>/<… N과>`."""
    root = os.path.join(base, "교과서 작업")
    subj = _pick(root, words=(subject,)) or _pick(root, words=(subject[:3],))
    if not subj:
        return None
    pub = _pick(subj, words=(publisher,))
    if not pub:
        # `미래엔(김)` ↔ `미래엔김` 같은 표기 차 — 괄호를 지우고 다시
        pub = _pick(subj, words=(re.sub(r"[()]", "", publisher),))
    if not pub:
        return None
    return _pick(pub, want_num=lesson, words=("과",), avoid=("추가본문",),
                 num_unit="과")


def textbook_sl(base, subject, publisher, no):
    """교과서 특별 단원 — `… SL2` 처럼 과가 아니라 SL 로 적힌 폴더.

    완성본 라벨은 번호 없이 `교과서SL 본문1` 이다(완성본 8권 실측).
    """
    root = os.path.join(base, "교과서 작업")
    subj = _pick(root, words=(subject,)) or _pick(root, words=(subject[:3],))
    if not subj:
        return None
    pub = _pick(subj, words=(publisher,)) or \
        _pick(subj, words=(re.sub(r"[()]", "", publisher),))
    if not pub:
        return None
    # ⚠ 여기는 번호가 **단위 뒤**에 온다(`SL2`) — `2과` 와 반대라 `_pick` 의
    #   `num_unit`(숫자가 앞) 으로는 못 잡는다. 이름으로 곧장 고른다.
    want = re.compile(r"SL\s*%d(?!\d)" % no, re.I)
    for name in _dirs(pub):
        if want.search(nfc(name)):
            return os.path.join(pub, name)
    return None


def textbook_deeplearning(base, subject, publisher, lesson):
    """교과서 추가본문(Deep Learning) — 과 폴더 **밖**에 따로 있다.

    `공통영어1 미래엔(김)/공통영어1 미래엔 Deep Learning/3, 4과/… 워크북`
    처럼 두 과를 묶어 두므로, 폴더 이름의 숫자에 그 과가 들어 있으면 맞다.
    """
    root = os.path.join(base, "교과서 작업")
    subj = _pick(root, words=(subject,)) or _pick(root, words=(subject[:3],))
    if not subj:
        return None
    pub = (_pick(subj, words=(publisher,))
           or _pick(subj, words=(re.sub(r"[()]", "", publisher),)))
    if not pub:
        return None
    dl = _pick(pub, words=("DeepLearning",))
    return _pick(dl, want_num=lesson, words=("과",)) if dl else None


# ── 올림포스: **여러 판이 있다** ─────────────────────────────────────────
#
#   EBS 작업/올림포스 독해기본1
#            올림포스 독해기본2
#            올림포스 고2 기출
#            2026 올림포스 전국연합학력평가 기출 영어독해 고1(2025.10)
#
# 이름만 보고 고르면 `올림포스 13강` 이 네 곳 다에 있어 **아무거나 집는다**.
# 그래서 이름으로는 **후보를 좁히기만** 하고, 마지막은 **지문 번호로** 고른다 —
# 시험범위가 `13강 1~5` 라고 짚었으면 그 강에 no.01~05 가 실제로 있는 판이
# 맞는 판이다. 판마다 강별 지문 수가 다르므로 이것이 곧 내용 대조다.
#
# 판을 가르는 낱말. 앞의 것이 더 좁다(둘 다 걸리면 좁은 쪽이 이긴다).
OLPO_MARKS = (
    ("전국연합", ("전국연합", "학력평가기출", "기출문제집")),
    ("기출", ("기출",)),
    ("독해기본2", ("독해기본2",)),
    ("독해기본1", ("독해기본1",)),
    ("유형편", ("유형편",)),
)


def olympos_roots(base):
    """`EBS 작업` 아래 올림포스 판 폴더 전부."""
    root = os.path.join(base, "EBS 작업")
    return [os.path.join(root, n) for n in _dirs(root)
            if "올림포스" in _squash(n)]


def _olpo_score(dir_name, book_name, grade=0):
    """폴더 이름 ↔ 시험범위가 적은 교재 이름의 겹침. 클수록 그럴듯하다."""
    dn, bn = _squash(dir_name), _squash(book_name)
    score = 0
    for _tag, words in OLPO_MARKS:
        ind = any(w in dn for w in words)
        inb = any(w in bn for w in words)
        if ind and inb:
            score += 10
        elif ind != inb:
            score -= 6              # 한쪽에만 있는 표지는 다른 판이라는 뜻
    for g in (1, 2, 3):
        if ("고%d" % g) in dn:
            if ("고%d" % g) in bn:
                score += 4
            elif grade and g != grade:
                score -= 4
    return score


def olympos_units(base, unit, book_name="", grade=0):
    """`(점수, 강 폴더)` 목록 — 이름으로 매긴 순서. 내용 대조는 부르는 쪽에서."""
    out = []
    for root in olympos_roots(base):
        # ⚠ 교재 이름에도 숫자가 있다(`올림포스 독해기본2 1강`) — 아무 숫자나
        #   세면 **2강을 찾다 1강을 집는다**(실측). `강` 에 붙은 숫자만 센다.
        d = _pick(root, want_num=unit, words=("강",), num_unit="강")
        if d:
            out.append((_olpo_score(os.path.basename(root), book_name, grade), d))
    out.sort(key=lambda x: -x[0])
    return out


_NUM_CACHE = {}


def passage_numbers(folder):
    """그 강 원고에 실제로 있는 지문 번호 집합(`no.01` → 1). 못 읽으면 빈 집합."""
    if folder in _NUM_CACHE:
        return _NUM_CACHE[folder]
    got = set()
    try:
        from engines.final import manuscript as M
        for b in M.read(folder, "arrange")[0]:
            key = parse_label(b.get("raw", ""))["key"]
            n = _no(key)
            if n:
                got.add(int(n.split("~")[0]))
    except Exception:                                          # noqa: BLE001
        got = set()
    _NUM_CACHE[folder] = got
    return got


def olympos(base, unit, book=1, book_name="", want=(), grade=0,
            log=lambda m: None):
    """올림포스 N강 원고 폴더. **이름으로 좁히고 지문 번호로 확정한다.**

    `want` 는 시험범위가 짚은 지문 번호다. 그 번호를 다 갖고 있는 판만 맞다 —
    같은 `13강` 이라도 판마다 지문이 다르므로 이것이 내용 대조가 된다.
    번호를 안 주면(옛 호출부) 예전처럼 이름으로만 고른다.
    """
    name = book_name or ("올림포스 독해기본%d" % book)
    cands = olympos_units(base, unit, name, grade)
    if not cands:
        return None
    if not want:
        return cands[0][1]
    ok = [(sc, d) for sc, d in cands if set(want) <= passage_numbers(d)]
    if len(ok) == 1:
        return ok[0][1]
    if not ok:
        # 어느 판도 범위가 짚은 번호를 다 갖고 있지 않다 — 조용히 넘기지 않는다.
        log("[범위] ★ 올림포스 %d강 — 범위가 짚은 지문 %s 를 가진 판이 없습니다: %s"
            % (unit, ",".join(str(n) for n in want),
               " / ".join("%s(원고 %s)" % (os.path.basename(os.path.dirname(d)),
                                          ",".join(str(n) for n in
                                                   sorted(passage_numbers(d))) or "없음")
                          for _sc, d in cands)))
        return cands[0][1]
    if ok[0][0] > ok[1][0]:
        return ok[0][1]
    log("[범위] ★ 올림포스 %d강 — 판이 갈리지 않습니다(%s). 교재 이름을 더 적어 주세요."
        % (unit, " / ".join(os.path.basename(os.path.dirname(d))
                            for _sc, d in ok)))
    return ok[0][1]


def reading_power(base, unit, edition="완성"):
    """리딩파워 — `EBS 작업/Reading Power 유형편(<판>)/Unit N …`."""
    root = _pick(os.path.join(base, "EBS 작업"),
                 words=("ReadingPower유형편", edition))
    return _pick(root, want_num=unit, words=("Unit",)) if root else None


def _month_dir(root, year, month):
    for name in _dirs(root):
        n = nfc(name)
        m = re.match(r"^고?\d?\s*(\d{2})년\s*(\d{1,2})월", n)
        if m and int(m.group(1)) == year % 100 and int(m.group(2)) == month:
            return os.path.join(root, name)
    return None


def mockexam(base, grade, year, month):
    """모의고사 — `모의고사 작업/고N/고N YY년 M월`.

    ⚠ 고1·고2 는 회차가 **연도 묶음** 아래로 한 단 내려가 있다
      (`고1 23년(3,6,9,10,11월)/고1 23년 9월`). 묶음 이름의 '11월' 이
      11월 회차로 오인되지 않도록, 묶음은 **연도만** 보고 고른다.
    """
    root = _pick(os.path.join(base, "모의고사 작업"), words=("고%d" % grade,))
    if not root:
        return None
    d = _month_dir(root, year, month)
    if d:
        return d
    for name in _dirs(root):
        n = nfc(name)
        m = re.match(r"^고?\d?\s*(\d{2})년\s*\(", n)
        if m and int(m.group(1)) == year % 100:
            d = _month_dir(os.path.join(root, name), year, month)
            if d:
                return d
    return None


def suneung_teukgang(base, unit, year=2027, test=False):
    """고3 수능특강 — `EBS 작업/<year> 수능특강 영어/워크북/N강 워크북`.

    실전 회차는 `Test 1 워크북` 처럼 '강' 이 아니라 'Test' 로 적힌다.
    """
    root = _pick(os.path.join(base, "EBS 작업"),
                 words=("수능특강영어",), want_num=year)
    if not root:
        return None
    wb = _pick(root, words=("워크북",))
    if not wb:
        return None
    # 교재 이름의 연도(`2027 수능특강 …`)에 걸리지 않게 `강` 에 붙은 숫자만
    if test:
        return _pick(wb, want_num=unit, words=("Test",))
    return _pick(wb, want_num=unit, words=("강",), avoid=("Test",))


# ── 시험범위 토큰 읽기 ───────────────────────────────────────────────────
RE_MOCK = re.compile(r"(\d{2})년\s*(\d{1,2})월")
RE_RP = re.compile(r"리딩파워\s*(\d{1,2})")
RE_OLPO = re.compile(r"올림포스\s*(\d{1,2})")
RE_TEUK = re.compile(r"수능특강\s*(\d{1,2})")
RE_LESSON = re.compile(r"(\d{1,2})과")


def parse_tokens(text):
    """워크북 파일 이름의 괄호 안 → [(kind, 숫자…)] 목록.

    `올림포스15,16,17,18강` 처럼 숫자가 이어 붙은 표기도 편다.
    """
    inner = text
    m = re.search(r"\(([^)]*)\)", text)
    if m:
        inner = m.group(1)
    out = []
    for mm in RE_MOCK.finditer(inner):
        out.append(("mock", int(mm.group(1)), int(mm.group(2))))
    for name, kind in (("리딩파워", "rp"), ("올림포스", "olpo"),
                       ("수능특강", "teuk")):
        # ⚠ `리딩파워12강,14강` 처럼 **강이 여러 번 나오는** 표기가 흔하다.
        #   `…([\d,~-]+)강` 로 한 번만 잡으면 뒤가 통째로 없어진다(14강 소실).
        #   접두 뒤로 숫자·쉼표·물결·'강' 이 이어지는 **구간 전체**를 가져온다.
        for m0 in re.finditer(re.escape(name) + r"\s*((?:[\d,\s~\-]|강)+)",
                              inner):
            seg = m0.group(1)
            for a, b in re.findall(r"(\d{1,2})\s*[~\-]\s*(\d{1,2})", seg):
                out += [(kind, u) for u in range(int(a), int(b) + 1)]
            seg2 = re.sub(r"\d{1,2}\s*[~\-]\s*\d{1,2}", "", seg)
            out += [(kind, int(u)) for u in re.findall(r"\d{1,2}", seg2)]
    # 접두 없는 `18,19,20,21강` — 고3 분석편 파일 이름이 이 꼴이다.
    if not any(t[0] in ("rp", "olpo", "teuk") for t in out):
        head = re.split(r"[가-힣]{2,}", inner)[0] if inner else ""
        for seg in re.findall(r"((?:[\d,\s~\-]|강)+강)", inner):
            for a, b in re.findall(r"(\d{1,2})\s*[~\-]\s*(\d{1,2})", seg):
                out += [("bare", u) for u in range(int(a), int(b) + 1)]
            seg2 = re.sub(r"\d{1,2}\s*[~\-]\s*\d{1,2}", "", seg)
            out += [("bare", int(u)) for u in re.findall(r"\d{1,2}", seg2)]
    for t in re.findall(r"[Tt]est\s*(\d)", inner):
        out.append(("test", int(t)))
    # 교과서: `미래엔3,4과` · `능률민1과`
    for seg in re.findall(r"[가-힣()]+\s*([\d,\s]+)과", inner):
        out += [("lesson", int(u)) for u in re.findall(r"\d{1,2}", seg)]
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


# ── 원고 라벨 → 파이널 라벨 ──────────────────────────────────────────────
# 원고는 `p108-no.01` · `L4-본문1(p.94)` · `p106-Example 1` 처럼 **쪽 표시 +
# 지문 이름**으로 적는다. 파이널 라벨은 출처(과·강·연월)를 앞에 붙인 것이다.
# 아래 표는 다섯 학교 180지문을 **내용으로 짝지어** 읽어 낸 것이다.
RE_NO = re.compile(r"^no\.?\s*(\d{1,2})(?:\s*[~\-]\s*(\d{1,2}))?$", re.I)
RE_EXAMPLE = re.compile(r"^Example\s*(\d+)$", re.I)
# `본문3-1` · `본문3-2` — 분석본이 긴 본문을 **둘로 나눈** 과(YBM(박) 2과).
# 번호만 보면 3-1 을 버리고 3-2 도 버린다 — 그 과에서 두 지문이 통째로 빠진다.
RE_BONMUN = re.compile(r"^본문\s*(\d{1,2})(?:\s*-\s*(\d))?$")


def _bonmun(m):
    return "본문%d" % int(m.group(1)) + ("-%s" % m.group(2) if m.group(2) else "")
RE_LESSON_PREFIX = re.compile(r"^L\s*(\d{1,2})$", re.I)


def parse_label(text):
    """`manuscript.parse_label` 재수출 — 라벨 규칙과 같은 자리에 둔다."""
    from engines.final.manuscript import parse_label as _p
    return _p(text)


def _no(key):
    """`no.03` · `no.24~25` → ("03", "24~25") 꼴의 원문 숫자(자리수 보존)."""
    m = RE_NO.match(key)
    if not m:
        return None
    return m.group(1) if not m.group(2) else f"{m.group(1)}~{m.group(2)}"


def to_final_label(src, raw_label):
    """(출처, 원고 라벨) → 파이널 라벨. 모르면 None.

    src = {"kind": …, "unit": N, "lesson": N, "year": YY, "month": M,
           "deeplearning": bool}
    """
    lab = parse_label(raw_label) if isinstance(raw_label, str) else raw_label
    key, page = lab["key"], lab["page"]
    kind = src["kind"]

    if kind == "sl":
        # 특별 단원은 **번호를 붙이지 않는다** — `교과서SL 본문1`(완성본 실측).
        if RE_BONMUN.match(key):
            return "교과서SL " + _bonmun(RE_BONMUN.match(key))
        if "Read More" in key:
            return "교과서SL RM"
        return None

    if kind == "lesson":
        lesson = src.get("lesson")
        m = RE_LESSON_PREFIX.match(page)
        if m:
            lesson = int(m.group(1))
        if src.get("deeplearning"):
            return f"교과서{lesson}과 딥러닝"
        if RE_BONMUN.match(key):
            return f"교과서{lesson}과 " + _bonmun(RE_BONMUN.match(key))
        if "Read More" in key:
            return f"교과서{lesson}과 RM"
        return None

    if kind == "olpo":
        u = src["unit"]
        if "ANALYSIS" in key.upper():
            return f"올포 {u}강 분석"
        if "서술형" in key:
            return f"올포 {u}강 서술형"
        if "논술형" in key:
            return f"올포 {u}강 논술형"
        n = _no(key)
        if not n:
            return None
        # 장문(1지문 2~3문항)은 원고가 `no.01~02` 로 적지만 파이널은 첫 번호를
        # 쓴다(실측: 올포 17강 `no.01~02` → `올포 17강 본문1`).
        return f"올포 {u}강 본문{int(n.split('~')[0])}"

    if kind == "rp":
        u = src["unit"]
        m = RE_EXAMPLE.match(key)
        if m:
            return f"리딩파워 {u}강 Ex{int(m.group(1)):02d}"
        n = _no(key)
        return f"리딩파워 {u}강 {int(n):02d}" if n and "~" not in n else None

    if kind == "mock":
        n = _no(key)
        if not n:
            return None
        yy, mm = src["year"] % 100, src["month"]
        return f"{yy:02d}{mm:02d}{n}"

    if kind in ("teuk", "test"):
        n = _no(key)
        if not n:
            return None
        head = (f"test{src['unit']}" if kind == "test"
                else f"{src['unit']}강")
        return f"{head} {n}"

    return None
