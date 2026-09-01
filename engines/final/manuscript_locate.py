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


def _pick(root, want_num=None, words=(), avoid=()):
    """`root` 아래에서 숫자와 낱말로 폴더 하나를 고른다.

    숫자는 **낱말 경계로** 본다 — `1강` 을 찾을 때 `11강` 이 걸리면 안 된다.
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
            nums = [int(x) for x in re.findall(r"\d+", n)]
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
    return _pick(pub, want_num=lesson, words=("과",), avoid=("추가본문",))


def olympos(base, unit, book=1):
    """올림포스 독해기본 N — `EBS 작업/올림포스 독해기본{book}/… M강`."""
    root = _pick(os.path.join(base, "EBS 작업"),
                 words=("올림포스독해기본%d" % book,))
    return _pick(root, want_num=unit, words=("강",)) if root else None


def reading_power(base, unit, edition="완성"):
    """리딩파워 — `EBS 작업/Reading Power 유형편(<판>)/Unit N …`."""
    root = _pick(os.path.join(base, "EBS 작업"),
                 words=("ReadingPower유형편", edition))
    return _pick(root, want_num=unit, words=("Unit",)) if root else None


def mockexam(base, grade, year, month):
    """모의고사 — `모의고사 작업/고N/고N YY년 M월`."""
    root = _pick(os.path.join(base, "모의고사 작업"), words=("고%d" % grade,))
    if not root:
        return None
    for name in _dirs(root):
        n = nfc(name)
        m = re.match(r"^고\d\s*(\d{2})년\s*(\d{1,2})월", n)
        if m and int(m.group(1)) == year % 100 and int(m.group(2)) == month:
            return os.path.join(root, name)
    return None


def suneung_teukgang(base, unit, year=2027):
    """고3 수능특강 — `EBS 작업/<year> 수능특강 영어/워크북/N강 워크북`."""
    root = _pick(os.path.join(base, "EBS 작업"),
                 words=("수능특강영어",), want_num=year)
    if not root:
        return None
    wb = _pick(root, words=("워크북",))
    return _pick(wb, want_num=unit, words=("강",)) if wb else None


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
    # 교과서: `미래엔3,4과` · `능률민1과`
    for seg in re.findall(r"[가-힣()]+\s*([\d,\s]+)과", inner):
        out += [("lesson", int(u)) for u in re.findall(r"\d{1,2}", seg)]
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq
