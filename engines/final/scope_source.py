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
    "sl": "교과서SL", "lesson": "교과서", "olpo": "올림포스", "rp": "리딩파워",
    "teuk": "수능특강", "bare": "강", "test": "Test", "mock": "모의고사",
}


def token_text(t):
    """토큰 → 사람이 읽는 한 마디."""
    if t[0] == "mock":
        return "%d년 %d월 모의고사" % (t[1], t[2])
    if t[0] == "sl":
        return "교과서 SL"
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


# 책의 차례 — 교과서 → 강 → 회차 → 모의. 범위 글의 **적힌 순서**를 그대로
# 따르면 안 된다: `17, 18, 21~30강` 은 범위가 먼저 풀려 21~30 이 앞에 오고,
# 그러면 어법·어휘 섹션만 21강부터 시작해 문장배열과 어긋난다(실증: 광문3).
_ORDER = {"lesson": 0, "sl": 0, "olpo": 1, "rp": 1, "teuk": 1, "bare": 1,
          "test": 2, "mock": 3}


def order_key(t):
    if t[0] == "mock":
        return (3, t[1], t[2])
    # 특별 단원은 일반 과 **뒤**다(완성본 차례)
    if t[0] == "sl":
        return (0, 99, 0)
    return (_ORDER.get(t[0], 9), t[1] if len(t) > 1 else 0, 0)


def _ordered(tokens):
    return sorted(_uniq(tokens), key=order_key)


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
# 같은 것을 영어로 적기도 한다 — `올림포스 … Unit 1, 3~5, 8~10` · `Unit 1-8`.
# ⚠ 반드시 `Unit` 이 **앞에** 붙은 숫자만 본다. 교재 이름의 숫자(`독해의 기본 2`)를
#   강 번호로 읽으면 범위가 통째로 틀어진다.
RE_UNIT_RUN_EN = re.compile(
    r"\bunits?\s*((?:\d{1,2}\s*[,~\-]\s*)*\d{1,2})", re.I)
# `8강 3번~12강` — **강에서 강까지**. 사이에 지문 번호가 끼어 있어 낱개 규칙으로는
# 8강과 12강 두 점만 잡히고 9·10·11강이 통째로 샌다(이의2 실측).
# ⚠ 사이에 올 수 있는 건 **지문 번호 하나**뿐이다. 아무거나 끼워 주면
#   `7강(2,4),  11~17강` 을 7~17강으로 읽어 8·9·10강을 없는 범위로 만든다
#   (명일3 실측 — 회귀에서 잡혔다).
RE_UNIT_SPAN = re.compile(
    r"(\d{1,2})\s*강\s*(?:\d{1,3}\s*번)?\s*[~\-–]\s*(\d{1,2})\s*강")
RE_LESSON_RUN = re.compile(r"((?:\d{1,2}\s*[,~\-]\s*)*\d{1,2})\s*과")
RE_MOCK_TXT = re.compile(r"(\d{2})\s*년\s*(\d{1,2})\s*월")
# `23-25년 9월` — 세 해의 같은 달. 낱개 규칙은 **한 해만** 잡는다(한영2 실측).
RE_MOCK_SPAN = re.compile(
    r"(\d{2})\s*[~\-–]\s*(\d{2})\s*년\s*(\d{1,2})\s*월")
RE_TEST_TXT = re.compile(r"[Tt][Ee][Ss][Tt]\s*(\d)")
# `*` 는 항목의 머리다 — `* 공통영어1 능률(민) 3과 * 공통영어2 YBM(김) 4과`
# 를 한 도막으로 보면 두 교과서가 뭉쳐 **뒤쪽 출판사를 잃는다**(명일1 실증).
RE_SPLIT = re.compile(r"[/·*\n;]+")


def _nums(run):
    """`3,6,7` · `15~18` → [3,6,7] · [15,16,17,18]."""
    out = []
    for a, b in re.findall(r"(\d{1,2})\s*[~\-]\s*(\d{1,2})", run):
        out += list(range(int(a), int(b) + 1))
    rest = re.sub(r"\d{1,2}\s*[~\-]\s*\d{1,2}", "", run)
    out += [int(u) for u in re.findall(r"\d{1,2}", rest)]
    return out


def _scan(text):
    """범위 글 → (토큰 목록, {토큰: 지문 번호들}).

    형식이 아니라 **자리**로 읽는다:
      · 계열은 토막 안에서 찾고, 없으면 앞 토막에서 승계한다
      · 강 번호는 **`강` 으로 끝나는 숫자 묶음**만 센다
        (`올림포스 독해기본1` 의 1 은 교재 이름이라 걸리지 않는다)
      · 강·회차·모의 **바로 뒤에 숫자**가 오면 그건 지문/문항 번호다
        (`18강 2, 4` · `Test1 20~25` · `고1 23년 9월 32, 34`).
        한글이나 괄호가 오면 뜻이 달라 손대지 않는다
        (`14~16강 분석~3` · `21~30강(24-3 제외)`)
    """
    out, only, meta, excl = [], {}, {}, {}
    last_kind = "bare"
    for seg in RE_SPLIT.split(text or ""):
        if not seg.strip():
            continue
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
        subj, pub = _subject_of(seg), _publisher_of(seg)
        notes = RE_NOTE.findall(seg)
        deep = "deep learning" in low or "DL" in seg
        here, _pos = [], {}

        # 강에서 강까지(`8강 3번~12강`) — 사이 강을 먼저 채운다. 낱개 규칙이
        # 양 끝 두 점만 잡고 가운데를 흘리기 때문이다.
        span_units = set()
        for m in RE_UNIT_SPAN.finditer(seg):
            a, b = int(m.group(1)), int(m.group(2))
            if a < b <= a + 20:
                span_units.update(range(a, b + 1))

        runs = list(RE_UNIT_RUN.finditer(seg)) + list(
            RE_UNIT_RUN_EN.finditer(seg))
        runs.sort(key=lambda m: m.start())
        for idx, m in enumerate(runs):
            kind = last_kind
            for i, k in marks:
                if i < m.start():
                    kind = k
                else:
                    break
            last_kind = kind
            nums = _nums(m.group(1))
            out += [(kind, u) for u in nums]
            here += [(kind, u) for u in nums]
            for u in nums:
                _pos.setdefault((kind, u), m.start())
            end = runs[idx + 1].start() if idx + 1 < len(runs) else len(seg)
            tail = seg[m.end():end]
            # ⚠ 구간을 **여는** 강(`8강 3번~12강` 의 8강)의 꼬리는 다음 강
            #   이름이지 지문 번호가 아니다. 그대로 읽으면 `8강 only=[3..12]`
            #   라는 헛것이 나온다. 다만 같은 도막의 **다른** 강까지 함께
            #   막으면 안 된다 — `unit 1강~11강 (11강 2번지문까지)` 의
            #   `11강 only=[2]` 를 잃는다(회귀에서 잡혔다).
            opens_span = re.match(
                r"^\s*\d{1,3}\s*번?\s*[~\-–]\s*\d{1,2}\s*강", tail)
            if re.match(r"^\s*\d", tail) and not opens_span:
                for u in nums:
                    only[(kind, u)] = _ranges(tail)

        if span_units:
            kind = last_kind
            for i, k in marks:
                if i < len(seg):
                    kind = k
            out += [(kind, u) for u in sorted(span_units)]
            here += [(kind, u) for u in sorted(span_units)]

        for m in RE_LESSON_RUN.finditer(seg):
            out += [("lesson", u) for u in _nums(m.group(1))]
            here += [("lesson", u) for u in _nums(m.group(1))]

        # `23-25년 9월` — 해가 구간이면 그 해를 다 편다
        span_mocks = []
        for m in RE_MOCK_SPAN.finditer(seg):
            a, b, mm = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if a < b <= a + 10:
                span_mocks += [("mock", y, mm) for y in range(a, b + 1)]

        mocks = list(RE_MOCK_TXT.finditer(seg))
        for idx, m in enumerate(mocks):
            t = ("mock", int(m.group(1)), int(m.group(2)))
            out.append(t); here.append(t)
            end = mocks[idx + 1].start() if idx + 1 < len(mocks) else len(seg)
            nums = _ranges(re.sub(r"\(([^)]*)\)", " ", seg[m.end():end]))
            if nums:
                only[t] = nums
        # 해 구간의 나머지 해는 같은 문항 몫을 받는다 — `23-25년 9월 21-24, 29-40`
        # 은 세 해 모두 그 번호들이다.
        for t in span_mocks:
            if t not in here:
                out.append(t); here.append(t)
            base = ("mock", int(t[1]), int(t[2]))
            src = next((only[x] for x in only
                        if x[0] == "mock" and x[2] == base[2]), None)
            if src and t not in only:
                only[t] = src

        tests = list(RE_TEST_TXT.finditer(seg))
        for idx, m in enumerate(tests):
            t = ("test", int(m.group(1)))
            out.append(t); here.append(t)
            _pos.setdefault(t, m.start())
            end = tests[idx + 1].start() if idx + 1 < len(tests) else len(seg)
            tail = seg[m.end():end]
            if re.match(r"^\s*\d", tail):
                only[t] = _ranges(tail)

        # `(24-3, 27-3 제외)` · `TEST 2 (1, 8, 10~11번 제외)` — 괄호 안의 '제외'.
        #   `강-지문` 짝이면 그 강의 그 지문만, 맨 숫자면 **바로 앞 토큰**의 것.
        for m in re.finditer(r"\(([^)]*제외[^)]*)\)", seg):
            inner = m.group(1)
            pairs = re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", inner)
            if pairs:
                for a, b in pairs:
                    for t0 in here:
                        if t0[0] != "mock" and t0[1] == int(a):
                            excl.setdefault(t0, set()).add(int(b))
            else:
                prev = [t0 for t0 in here if _pos.get(t0, -1) < m.start()]
                if prev:
                    excl.setdefault(prev[-1], set()).update(
                        _ranges(re.sub(r"제외", "", inner)))

        for t in here:
            d = meta.setdefault(t, {})
            if t[0] == "lesson":
                if subj:
                    d["subject"] = subj
                if pub:
                    d["publisher"] = pub
                if deep:
                    d["deeplearning"] = True
            if notes:
                d["notes"] = notes
    for t, nums in only.items():
        if nums:
            meta.setdefault(t, {})["only"] = nums
    for t, nums in excl.items():
        if nums:
            meta.setdefault(t, {})["exclude"] = sorted(nums)
    return _ordered(out), meta


def scope_text_tokens(text):
    """범위 글 → 토큰 목록."""
    return _scan(text)[0]


# ── 교과서: 과목·출판사도 범위 글이 말한다 ──────────────────────────────
#
# `공통영어1 능률(민) 3과` · `영어Ⅰ 미래엔(김) 4과` · `영어 독해와 작문 비상(황) 3과`
# 지금까지는 엔진 config 의 학교↔교과서 표를 봐야 했다. 범위 글이 정본이면
# 그 표가 필요 없다 — **학교마다 교과서를 따로 적어 두지 않아도 된다.**
SUBJECTS = ("공통영어1", "공통영어2", "영어 독해와 작문", "영어독해와작문",
            "영어Ⅰ", "영어Ⅱ", "영어1", "영어2", "실용영어", "진로영어")
RE_PUB = re.compile(r"([가-힣A-Za-z]{2,6}\s*\([가-힣]\)|[가-힣A-Za-z]{2,6})"
                    r"\s*(?:[\d,\s~\-]+)과")
# 괄호 안 단서 — `(추가본문X)` `(Read More 제외)` `(MR만)` `(Practice 1만)`
# `(Gateway 제외)` `(24-3, 27-3 제외)`. 여기서 다 풀지는 않는다.
# **버리지 않고 토큰에 붙여 둔다** — 조용히 사라지는 것이 가장 나쁘다.
RE_NOTE = re.compile(r"\(([^)]*(?:제외|만|X|포함|Practice|Gateway)[^)]*)\)")


def _subject_of(seg):
    for s0 in SUBJECTS:
        if s0.replace(" ", "") in seg.replace(" ", ""):
            return s0
    return ""


def _publisher_of(seg):
    m = RE_PUB.search(seg)
    if not m:
        return ""
    pub = re.sub(r"\s+", "", m.group(1))
    return "" if pub in ("과", "본문") else pub


def parse(text, grade=0):
    """범위 글 → {"tokens", "detail", "raw"}.

    `detail[token]` 에 그 토큰의 과목·출판사·지문 번호·괄호 단서를 담는다.
    """
    tokens, detail = _scan(text)
    return {"tokens": tokens, "detail": detail, "raw": text or "",
            "grade": grade, "source": "text"}


def folders(scope, base, grade=None, log=lambda m: None):
    """범위 → [(원고 폴더, spec)]. 워크북 파일 **없이** 원고를 찾는다.

    못 찾은 토큰은 조용히 넘기지 않고 `log` 로 알린다 — 범위에 있는데
    원고가 없으면 지문이 통째로 빠진다.
    """
    g = grade if grade is not None else scope.get("grade") or 0
    out, seen = [], set()
    for t in scope["tokens"]:
        d = scope.get("detail", {}).get(t, {})
        kind = t[0]
        path = spec = None
        if kind == "sl":
            subj, pub = d.get("subject") or "", d.get("publisher") or ""
            path = (L.textbook_sl(base, subj, pub, d.get("sl") or 1)
                    if subj and pub else None)
            spec = {"kind": "sl", "sl": d.get("sl"),
                    "subject": subj, "publisher": pub}
        elif kind == "lesson":
            subj = d.get("subject") or ""
            pub = d.get("publisher") or ""
            if subj and pub:
                path = L.textbook(base, subj, pub, t[1])
                spec = {"kind": "lesson", "lesson": t[1],
                        "subject": subj, "publisher": pub}
                dl = (L.textbook_deeplearning(base, subj, pub, t[1])
                      if d.get("deeplearning") else None)
        elif kind == "olpo":
            # ⚠ 판은 학년이 아니라 **교재 이름**이 정한다 — 고1 2학기가
            #   `독해 기본2` 를 쓴다(광문1 26-2-중간). 학년으로 찍으면
            #   기본1 을 뒤져 한 지문도 못 찾는다.
            book = d.get("book") or scope.get("raw", "")
            m = re.search(r"기본\s*([12])", book)
            path = L.olympos(base, t[1],
                             book=int(m.group(1)) if m else (1 if g == 1 else 2))
            spec = {"kind": "olpo", "unit": t[1]}
        elif kind == "rp":
            ed = "기본" if "기본" in scope["raw"] else "완성"
            path = L.reading_power(base, t[1], edition=ed)
            spec = {"kind": "rp", "unit": t[1]}
        elif kind in ("teuk", "bare"):
            path = L.suneung_teukgang(base, t[1])
            spec = {"kind": "teuk", "unit": t[1]}
        elif kind == "test":
            path = L.suneung_teukgang(base, t[1], test=True)
            spec = {"kind": "test", "unit": t[1]}
        elif kind == "mock":
            # 회차의 학년은 반의 학년과 다를 수 있다 — 고2 반이 고1 회차를 쓴다.
            path = L.mockexam(base, d.get("grade") or g, t[1], t[2])
            spec = {"kind": "mock", "year": t[1], "month": t[2]}
        if not path:
            log("[범위] 원고를 못 찾음 — %s" % token_text(t))
            continue
        if path in seen:
            continue
        seen.add(path)
        if d.get("notes"):
            spec = dict(spec, notes=d["notes"])
        out.append((path, spec))
        # 추가본문(딥러닝)은 본디 과 **뒤에** — 차례가 그렇고, 앞에 두면
        # 같은 파일이 딥러닝 몫으로 먼저 잡힌다.
        # ⚠ 추가본문 폴더는 `3, 4과` 처럼 **두 과가 한 폴더**다 — 과마다 한 번씩
        #   넣으면 같은 폴더를 두 번 읽어 지문이 두 벌 들어간다(실증).
        if kind == "lesson" and locals().get("dl") and dl not in seen:
            seen.add(dl)
            out.append((dl, dict(spec, deeplearning=True)))
    return out


# ── Y.OS 구조화 입력 ────────────────────────────────────────────────────
#
# Y.OS `/work/exam` 은 범위를 **글이 아니라 항목**으로 받는다:
#
#   교과서    공통영어2_NE능률민병천   Lesson 1. … 1~9, Lesson 2. … 1~12   21지문
#   모의고사  고1_2024_09월(인천시)    15~18, 20~24                        9지문
#   부교재    수능특강 Light 영어독해연습(2025.10)  08 1~5, 09 1~5         49지문
#   프린트    EBS 연계 외부지문         1~20                               20지문
#
# **여기에 지문 수준 제한이 들어 있다** — 글로 받던 시절의 마지막 구멍이
# 이걸로 막힌다. `직접 입력` 만 예전처럼 글이라 `parse()` 로 넘긴다.
PUBLISHERS = ("능률", "미래엔", "비상", "천재", "동아", "지학사", "금성",
              "YBM", "다락원", "케이", "教学")
RE_YOS_MOCK = re.compile(r"고(\d)_(\d{4})_(\d{1,2})월")
RE_LESSON_HEAD = re.compile(r"Lesson\s*(\d+)|(\d+)\s*과")
# `Special Lesson 2` 는 과가 아니라 **SL** 이다(완성본 라벨 `교과서SL2 …`).
# 일반 과보다 **먼저** 걸러야 `Lesson 2` 로 잘못 읽지 않는다.
RE_LESSON_HEAD_ANY = re.compile(
    r"(Special\s+Lesson|SL)\s*(\d+)|Lesson\s*(\d+)|(\d+)\s*과")


def normalize_book(name):
    """`공통영어2_NE능률민병천` → ("공통영어2", "능률(민)").

    출판사 표기가 Y.OS 와 원고 폴더에서 다르다. 폴더는 `능률(민)` 처럼
    **출판사(저자 성)** 이고 Y.OS 는 붙여 쓴다(`NE능률민병천`).
    앞의 로마자(`NE`)는 상표라 버린다.
    """
    subj, _, rest = (name or "").partition("_")
    subj = subj.replace("Ⅰ", "I").replace("Ⅱ", "II")
    subj = {"영어I": "영어Ⅰ", "영어II": "영어Ⅱ"}.get(subj.strip(), subj.strip())
    rest = (rest or "").strip()
    # 가장 **앞에서** 걸리는 출판사가 진짜다 — `NE능률민병천` 의 `NE` 는
    # 상표라 건너뛰지만 `YBM박준언` 의 `YBM` 은 출판사 그 자체다.
    hit = min((( rest.find(p0), -len(p0), p0) for p0 in PUBLISHERS
               if rest.find(p0) >= 0), default=None)
    if hit:
        i, _, pub = hit
        author = rest[i + len(pub):].strip()
        return subj, ("%s(%s)" % (pub, author[0]) if author else pub)
    return subj, rest


# 모의고사 41번부터는 **장문**이다 — `41~42`·`43~45` 는 묶어서 한 지문이고
# 원고 라벨도 `240941~42` 처럼 한 덩어리다. 번호를 다 펴면 지문 수가 부푼다.
MOCK_LONG_FROM = 41


def mock_ranges(text):
    """모의고사 범위 → (걸러 낼 번호들, 지문 수).

    `18~40, 41~42, 43~45` → 23 + 1 + 1 = **25지문**(Y.OS 가 센 값과 같다).
    """
    nums, count = [], 0
    for chunk in (text or "").split(","):
        c = chunk.strip()
        if not c:
            continue
        got = _ranges(c)
        if not got:
            continue
        nums += got
        m = re.match(r"^\s*(\d+)\s*[~\-–]", c)
        count += 1 if (m and int(m.group(1)) >= MOCK_LONG_FROM) else len(got)
    return sorted(set(nums)), count


def _ranges(text):
    """`15~18, 20~24` → [15,16,17,18,20,21,22,23,24]."""
    out = []
    for a, b in re.findall(r"(\d{1,3})\s*[~\-–]\s*(\d{1,3})", text or ""):
        out += list(range(int(a), int(b) + 1))
    rest = re.sub(r"\d{1,3}\s*[~\-–]\s*\d{1,3}", "", text or "")
    out += [int(u) for u in re.findall(r"\d{1,3}", rest)]
    return sorted(set(out))


# Y.OS 가 적는 항목 이름 → 파이널 라벨의 꼬리. 번호가 없는 지문들이다.
NAMED_TAIL = (
    ("수능 대비 ANALYSIS", "분석"), ("학평ANALYSIS", "분석"),
    ("ANALYSIS", "분석"), ("분석", "분석"),
    ("논술형", "논술형"), ("서술형", "서술형"),
    ("Read More", "RM"), ("Further Reading", "FR"),
)


def named_tail(s):
    """`수능 대비 ANALYSIS` → `분석`. 못 알아보면 None."""
    t = (s or "").strip()
    for word, tail in NAMED_TAIL:
        if word.lower() in t.lower():
            return tail
    return None


RE_PAGE_MARK = re.compile(r"p\.\s*\d+\s*")


def lesson_ranges(text):
    """`Lesson 1. … 1~9, Lesson 2. … 1~12` → {1: [1..9], 2: [1..12]}.

    과 이름이 사이에 있어도 된다 — **과 머리에서 다음 과 머리까지**를
    그 과의 몫으로 본다(자리로 읽는다).
    """
    text = text or ""
    heads = []
    for m in RE_LESSON_HEAD_ANY.finditer(text):
        sl = bool(m.group(1))
        no = int(m.group(2) or m.group(3) or m.group(4))
        heads.append((m.start(), m.end(), ("sl", no) if sl else no))
    out = {}
    for i, (pos, end0, key) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        seg = text[end0:end]
        # ⚠ `p. 100` 은 **쪽 표시**지 지문 번호가 아니다. 먼저 지운다 —
        #   안 지우면 100·101… 이 지문 번호로 잡혀 5지문이 10지문이 된다.
        seg = RE_PAGE_MARK.sub(" ", seg)
        nums, named = [], []
        if "본문" in seg:
            # `본문 1, 본문 2` 처럼 **항목 이름에 붙은 번호**만 센다
            nums = [int(x) for x in re.findall(r"본문\s*(\d+)", seg)]
        else:
            nums = _ranges(seg)
        for chunk in seg.split(","):
            tl = named_tail(chunk)
            if tl and tl not in named:
                named.append(tl)
        out[key] = {"nums": sorted(set(nums)), "named": named}
    return out


RE_TAIL_NUMS = re.compile(r"([\d]+(?:\s*[~\-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[~\-–]\s*\d+)?)*)\s*$")


def unit_ranges(text):
    """`08 1~5, 09 1~5, Mini Test 1 2~5, 12~17` → 강별 지문 번호.

    돌려주는 것: [{"name": "", "no": 8, "nums": [1..5]}, …]

    형식이 제각각이라(`08 1~5` · `(PART 01) 09 관계사 1~4` · `Mini Test 1 2~5`)
    글자로 맞추지 않고 **자리로** 읽는다:
      · 한 도막의 **맨 뒤 숫자 묶음**이 지문 번호다
      · 그 앞에 남은 것 중 **마지막 숫자**가 강 번호,
        그 앞의 글자가 이름이다(`Mini Test`, `PART`)
      · 앞에 숫자가 없으면 **앞 강의 뒷토막**이다(`, 12~17`)
    """
    out, cur = [], None
    for chunk in (text or "").split(","):
        c = chunk.strip()
        if not c:
            continue
        m = RE_TAIL_NUMS.search(c)
        if not m:
            # ⚠ 번호가 없는 항목도 **지문 하나**다 — `수능 대비 ANALYSIS`,
            #   `논술형 Practice`. 그냥 흘리면 올림포스 36지문이 24지문이 된다.
            tl = named_tail(c)
            if tl and cur is not None:
                if tl not in cur["named"]:
                    cur["named"].append(tl)
            elif not tl:
                cur = None
            continue
        nums = _ranges(m.group(1))
        head = c[:m.start()].strip()
        hn = re.findall(r"\d+", head)
        if not hn:
            if cur is not None:            # `, 12~17` — 앞 강이 이어진다
                cur["nums"] = sorted(set(cur["nums"] + nums))
            continue
        no = int(hn[-1])
        # 이름 = 강 번호 앞의 글자(괄호 머리말은 버린다)
        name = head[:head.rfind(hn[-1])]
        name = re.sub(r"\([^)]*\)", " ", name)
        name = re.sub(r"[\d.\-–~]+", " ", name).strip()
        cur = {"name": name, "no": no, "nums": nums, "named": []}
        out.append(cur)
    # 같은 이름·번호가 두 번 나오면 합친다
    merged = {}
    for u in out:
        k = (u["name"].lower(), u["no"])
        if k in merged:
            merged[k]["nums"] = sorted(set(merged[k]["nums"] + u["nums"]))
            for x in u["named"]:
                if x not in merged[k]["named"]:
                    merged[k]["named"].append(x)
        else:
            merged[k] = u
    return list(merged.values())


def from_yos_entries(entries, grade=0):
    """Y.OS 항목 목록 → Scope.

    `entries` = [(구분, 교재, 범위, 지문수), …] — 화면에 보이는 그대로.
    `직접 입력` 은 글이라 `parse()` 로 돌린다(예전 길).
    """
    tokens, detail, raw = [], {}, []
    for e in entries or []:
        kind = (e[0] or "").strip()
        book = (e[1] or "").strip() if len(e) > 1 else ""
        rng = (e[2] or "").strip() if len(e) > 2 else ""
        raw.append(" ".join(x for x in (kind, book, rng) if x))
        if kind == "직접 입력":
            sub = parse(book, grade)      # 이 칸이 곧 글이다
            for t in sub["tokens"]:
                if t not in detail:
                    tokens.append(t)
                    detail[t] = sub["detail"].get(t, {})
            continue
        if kind == "단어":
            continue                      # 단어장은 파이널이 아니라 딴 교재다
        if kind == "교과서":
            subj, pub = normalize_book(book)
            for n, got in lesson_ranges(rng).items():
                # 특별 단원은 라벨에 번호가 없다(`교과서SL 본문1`) — 토큰도
                # 번호를 안 쓰고, 폴더를 찾을 번호만 따로 들고 간다.
                t = ("sl", 0) if isinstance(n, tuple) else ("lesson", n)
                tokens.append(t)
                detail[t] = {"subject": subj, "publisher": pub,
                             "only": got["nums"], "named": got["named"]}
                if isinstance(n, tuple):
                    detail[t]["sl"] = n[1]
        elif kind == "모의고사":
            m = RE_YOS_MOCK.search(book)
            if m:
                t = ("mock", int(m.group(2)) % 100, int(m.group(3)))
                nums, cnt = mock_ranges(rng)
                tokens.append(t)
                detail[t] = {"grade": int(m.group(1)), "only": nums,
                             "count": cnt}
        elif kind == "부교재":
            k = "teuk" if "수능특강" in book else (
                "rp" if "Reading Power" in book or "리딩파워" in book else (
                    "olpo" if "올림포스" in book else "bare"))
            for u in unit_ranges(rng):
                # `Mini Test 1` · `Test 2` 는 강이 아니라 실전 회차다
                t = (("test", u["no"]) if "test" in u["name"].lower()
                     else (k, u["no"]))
                tokens.append(t)
                detail[t] = {"book": book, "only": u["nums"],
                             "named": u["named"], "label": u["name"] or None}
        elif kind == "프린트":
            t = ("print", len(tokens))
            tokens.append(t)
            detail[t] = {"book": book, "only": _ranges(rng)}
    # 적힌 차례가 아니라 **책의 차례**로 (교과서→SL→강→회차→모의)
    return {"tokens": _ordered(tokens), "detail": detail,
            "raw": " / ".join(raw), "grade": grade, "source": "yos"}


def count_gate(entries, scope):
    """Y.OS 가 적어 둔 **지문수**와 내가 읽어 낸 개수를 맞대 본다.

    그 숫자는 저장된 값이 아니라 Y.OS 가 범위 글에서 **직접 센** 값이다
    (9+12=21 · 4+5=9 · 25+15+9=49 로 확인). 그러니 서로 다른 두 구현이
    맞대 보는 진짜 대조다 — 실제로 이 대조가 `Mini Test` 누락(25 vs 49)과
    `(PART 01) 09 …` 오독(8 vs 16)을 잡아냈다.

    돌려주는 것: [{"book", "want", "got"}] — **빈 목록이면 통과**.
    """
    bad = []
    for e in entries or []:
        kind = (e[0] or "").strip()
        if kind in ("직접 입력", "단어"):
            continue        # 글은 Y.OS 도 못 센다(0지문) · 단어장은 딴 교재다
        want = _ranges(e[3])[-1] if len(e) > 3 and _ranges(e[3]) else 0
        one = from_yos_entries([e], scope.get("grade") or 0)
        got = sum((d.get("count") if d.get("count") is not None
                   else len(d.get("only") or [])) + len(d.get("named") or [])
                  for d in one["detail"].values())
        if want and got != want:
            bad.append({"book": (e[1] or "").strip(), "want": want, "got": got})
    return bad


# ── 다른 출처(폴백·교차검증) ────────────────────────────────────────
def from_workbook_names(names):
    out = []
    for n in sorted(set(names or [])):
        out += L.parse_tokens(n)
    return {"tokens": _uniq(out), "raw": " / ".join(sorted(set(names or []))),
            "source": "filename"}


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


# ── 지문 수준 걸기 ──────────────────────────────────────────────────────
RE_LAB_SL = re.compile(r"^교과서SL\s*(.*)$")
RE_LAB_TB = re.compile(r"^교과서(\d+)과\s*(.*)$")
RE_LAB_UNIT = re.compile(r"^(올포|리딩파워)\s*(\d+)강\s*(.*)$")
RE_LAB_MOCK = re.compile(r"^(\d{2})(\d{2})(\d{2})")
RE_LAB_G3 = re.compile(r"^(?:(\d+)강|[Tt]est\s*(\d))\s*(.*)$")
RE_LAB_NO = re.compile(r"(\d+)")


def label_token(label):
    """파이널 라벨 → (토큰, 꼬리). 모르면 (None, "")."""
    m = RE_LAB_SL.match(label or "")
    if m:
        return ("sl", 0), m.group(1)
    m = RE_LAB_TB.match(label or "")
    if m:
        return ("lesson", int(m.group(1))), m.group(2)
    m = RE_LAB_UNIT.match(label or "")
    if m:
        return ((("olpo" if m.group(1) == "올포" else "rp"),
                 int(m.group(2))), m.group(3))
    m = RE_LAB_MOCK.match(label or "")
    if m:
        return (("mock", int(m.group(1)), int(m.group(2))), m.group(3))
    m = RE_LAB_G3.match(label or "")
    if m:
        if m.group(1):
            return ("teuk", int(m.group(1))), m.group(3)
        return ("test", int(m.group(2))), m.group(3)
    return None, ""


def in_scope(label, scope):
    """이 지문이 시험범위 안인가 — **지문 번호까지** 본다.

    Y.OS 가 `Lesson 1 … 1~9` / `15~18, 20~24` 로 지문을 짚어 주므로 강·과가
    아니라 지문 단위로 걸 수 있다. 다만 꼬리에 번호가 없는 것(`RM`, `분석`,
    `서술형`, `딥러닝`)은 **거르지 않는다** — 부속물이라 번호로 셀 수 없고,
    조용히 빼는 쪽이 훨씬 나쁘다.
    """
    tok, tail = label_token(label)
    if tok is None:
        return True                       # 못 알아본 라벨은 남긴다
    keys = {_key(t): t for t in scope.get("tokens", [])}
    t = keys.get(_key(tok))
    if t is None:
        return False
    d = scope.get("detail", {}).get(t) or {}
    only, excl = d.get("only"), d.get("exclude")
    named = d.get("named")
    if not only and not excl and named is None:
        return True
    m = RE_LAB_NO.search(tail if tok[0] != "mock" else (label or "")[4:])
    if not m:
        # 번호 없는 꼬리(`분석`·`서술형`·`RM`) — 범위가 이름으로 짚어 줬으면
        # 그 목록을 따른다. 안 짚어 줬으면 부속물이라 거르지 않는다.
        return (tail.strip() in named) if named else True
    no = int(m.group(1))
    if excl and no in excl:
        return False
    return no in only if only else True


# ── 파일로 오가기 ───────────────────────────────────────────────────────
def to_json(scope):
    """토큰이 튜플이라 그대로는 JSON 이 안 된다 — 목록으로 편다."""
    return {"source": scope.get("source"), "grade": scope.get("grade", 0),
            "raw": scope.get("raw", ""),
            "school": scope.get("school"), "grade_text": scope.get("grade_text"),
            "items": [{"token": list(t),
                       "detail": scope.get("detail", {}).get(t, {})}
                      for t in scope.get("tokens", [])]}


def from_json(obj):
    toks = [tuple(x["token"]) for x in obj.get("items", [])]
    return {"source": obj.get("source"), "grade": obj.get("grade", 0),
            "raw": obj.get("raw", ""), "tokens": toks,
            "school": obj.get("school"), "grade_text": obj.get("grade_text"),
            "detail": {tuple(x["token"]): (x.get("detail") or {})
                       for x in obj.get("items", [])}}


def from_sheet(school, exam_period, grade=0, log=lambda m: None):
    """구글시트 시험범위 → Scope. **Y.OS 가 열리면 이 함수만 갈아 끼운다.**

    시트의 학교 칸은 `광문고2`·`상일여고1` 인데 조판이 쓰는 이름은 `광문2`·
    `상일1` 이다 — 그 짝짓기는 `vocab_fetcher._find_scope_row` 가 이미 안다.
    """
    from engines.final import vocab_fetcher as V
    rows = V._fetch_csv(V.SCOPE_SHEET_ID, V.SCOPE_GID)
    if not rows:
        log("[범위] 시험범위 시트에 닿지 못했습니다")
        return None
    row = V._find_scope_row(rows, school, exam_period)
    if not row:
        log("[범위] 시트에서 %s(%s) 를 찾지 못했습니다" % (school, exam_period))
        return None
    # 교과서·모의고사·부교재·프린트 칸을 한 글로 잇는다(칸 차례가 곧 차례다)
    text = " / ".join(x.strip().replace("\n", " ")
                      for x in row[1:5] if x and x.strip())
    sc = parse(text, grade=grade)
    sc["school"], sc["source"] = school, "sheet"
    return sc


# ── 지문 차례 ───────────────────────────────────────────────────────────
RE_TAIL_NO = re.compile(r"(\d+)")
TB_TAIL = {"RM": 90, "딥러닝": 95}
UNIT_TAIL = {"분석": 0, "서술형": 90, "논술형": 95}


def label_order(label):
    """파이널 라벨 → 차례 열쇠. **모든 섹션이 같은 순서**여야 한다.

    섹션마다 출처가 달라(원고·시트·폴더 순서) 그냥 두면 어휘만 차례가
    달라진다(실측: 상일1 18강이 `분석→서술형→논술형→본문1` 로 나갔다).
    """
    tok, tail = label_token(label)
    if tok is None:
        return (9, 0, 0, label)
    tail = (tail or "").strip()
    if tok[0] == "sl":
        n = TB_TAIL.get(tail)
        if n is None:
            m = RE_TAIL_NO.search(tail)
            n = int(m.group(1)) if m else 50
        return (0, 99, n, label)
    if tok[0] == "lesson":
        n = TB_TAIL.get(tail)
        if n is None:
            m = RE_TAIL_NO.search(tail)
            n = int(m.group(1)) if m else 50
        return (0, tok[1], n, label)
    if tok[0] == "mock":
        m = RE_TAIL_NO.search(label[4:])
        return (3, tok[1] * 100 + tok[2], int(m.group(1)) if m else 0, label)
    n = UNIT_TAIL.get(tail)
    if n is None:
        m = RE_TAIL_NO.search(tail)
        no = int(m.group(1)) if m else 0
        # `Ex01`·`Ex02` 가 `01` 앞에 온다(완성본 차례) — 숫자만 보면 섞인다.
        n = no if tail.lower().startswith("ex") else 10 + no
    return ({"test": 2}.get(tok[0], 1), tok[1], n, label)
