# -*- coding: utf-8 -*-
"""S1/S2 인벤토리 — 전체(C) 원본에서 지문별 슬롯/실전 블록을 확정한다.

SPEC.md 의 슬롯 규격을 구현한다. InDesign 없이 덤프 2개만으로 동작하므로
조판에 들어가기 전에 커버리지를 기계 검증할 수 있다 (파서 단독 검증).

입력
  frames_json : core/jsx/dump_frames.jsx 산출 (프레임 단위)
  stories_json: core/inspect.dump_indd 산출 (스토리 단위 — 스레드 내부 마커용)

지문 코드 규칙 (26년 6월 원본 실측)
  - 프레임 머리 `[NN]` / `{NN}` / `{YYMMQQ}`
  - 코드가 없으면 같은 페이지의 '숫자 전용' 프레임 (어법 O/X 섹션이 이 형태)
  - 이중지문 표기가 섹션마다 다르다: `41~42`(영작배열) vs `41-42`(빈칸어휘)
    → normalize_code 로 `41~42` 로 통일
  - 영작배열·실전은 스레드라 프레임 머리로는 일부만 잡힌다. 스토리 문단의
    **텍스트 안 마커**로 분할해야 전량이 잡힌다 (실전 21개, 영작배열 18개 실증).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

# 섹션 = (이름, 시작페이지, 끝페이지, 세로 슬롯 순번, 마스터)
# 페이지 범위는 sep 위치에서 유도하는 것이 원칙이나, 검증 단계에서는 실측값을
# 그대로 쓴다 (26년 6월 원본 기준 — 다른 회차는 build_sections 로 재계산).
SLOTS = [
    ("어휘",     1,  "A"),
    ("본문",     2,  "A"),
    ("내용정리", 3,  "B"),
    ("내용종합", 4,  "B"),
    ("문장배열", 5,  "C"),
    ("빈칸어휘", 6,  "C"),
    ("어법",     7,  "D"),
    ("어법OX",   8,  "D"),
    ("빈칸어법", 9,  "E"),
    ("영작배열", 10, "E"),
]

# 스레드 섹션 — 프레임 머리가 아니라 텍스트 내부 마커로 분할해야 하는 것
THREADED = {"영작배열", "실전"}

_RE_BRACKET = re.compile(r"^[\[\{]\s*(\d{1,2}(?:\s*[-~]\s*\d+)?)\s*[\]\}]")
_RE_CODE6 = re.compile(r"^\{\d{4}(\d{2}(?:\s*[-~]\s*\d+)?)\}")
_RE_BARE = re.compile(r"^\d{1,2}(?:\s*[-~]\s*\d+)?$")


def normalize_code(c):
    """`41-42` / `41 ~ 42` / `41~42` → `41~42`. 단일 지문은 그대로."""
    if not c:
        return None
    c = re.sub(r"\s+", "", str(c)).replace("-", "~")
    return c


def code_aliases(canon_code):
    """이중지문 표기 흔들림을 흡수한다.

    같은 지문이 섹션마다 다르게 적혀 있다 (26년 6월 실측):
      영작배열 `41~42` / 빈칸어휘 `41-42` / 실전 `41`
    canon `41~42` 는 위 셋을 모두 같은 지문으로 받아야 한다.
    """
    c = normalize_code(canon_code)
    out = {c}
    if "~" in c:
        a, b = c.split("~", 1)
        out.update({a, b})
    return out


def resolve_to_canon(code, canon):
    """검출 코드를 canon 코드로 정규화. 대응 없으면 None (= 짤지문)."""
    c = normalize_code(code)
    for cc in canon:
        if c in code_aliases(cc):
            return normalize_code(cc)
    return None


def _clean(t):
    return re.sub(r"[￼﻿\s]+", " ", t or "").strip()


def code_of(text):
    """프레임/문단 머리에서 지문 코드를 뽑는다. 없으면 None."""
    t = _clean(text)
    if not t:
        return None
    for rx in (_RE_BRACKET, _RE_CODE6):
        m = rx.match(t)
        if m:
            return normalize_code(m.group(1))
    if _RE_BARE.match(t):
        return normalize_code(t)
    return None


def master_runs(frames_json):
    """페이지 순서대로 [(마스터, 시작p, 끝p, 장수)]."""
    d = json.load(open(frames_json, encoding="utf-8"))
    m = {}
    for f in d["frames"]:
        m.setdefault(f["pidx"] + 1, f.get("master") or "")
    runs = []
    for pg in sorted(m):
        name = m[pg]
        if runs and runs[-1][0] == name and runs[-1][2] == pg - 1:
            runs[-1][2] = pg
            runs[-1][3] += 1
        else:
            runs.append([name, pg, pg, 1])
    return runs


def detect_sections(frames_json, n_problems):
    """섹션 페이지 범위를 자동 산출한다 (회차마다 페이지가 밀리므로 하드코딩 금지).

    구조: front → 어휘(2N/2) → A섹션 5종(각 N) → sep → C구간 4종(각 N) → sep → 실전
    A/C/O 마스터 구간과 지문 수 N 으로 나눈다.
    """
    runs = master_runs(frames_json)

    def span(prefix):
        """해당 마스터가 처음~마지막으로 쓰인 구간을 통째로 잡는다.

        마스터 필터로 페이지를 모으면 안 된다 — 원본에 마스터가 잘못 걸린
        페이지가 섞여 있다 (26년 6월 원본 p13 이 A 구간 한가운데인데 B-마스터).
        """
        hits = [(a, b) for name, a, b, _n in runs if name.startswith(prefix)]
        if not hits:
            return []
        return list(range(min(h[0] for h in hits), max(h[1] for h in hits) + 1))

    a_pages, c_pages = span("A-"), span("C-")
    if len(a_pages) < 6 * n_problems or len(c_pages) < 4 * n_problems:
        raise ValueError("섹션 페이지 부족: A=%d(필요 %d) C=%d(필요 %d)"
                         % (len(a_pages), 6 * n_problems,
                            len(c_pages), 4 * n_problems))
    out, i = {}, 0
    for name in ("어휘", "본문", "내용정리", "내용종합", "문장배열", "빈칸어휘"):
        chunk = a_pages[i:i + n_problems]
        out[name] = (chunk[0], chunk[-1])
        i += n_problems
    j = 0
    for name in ("어법", "어법OX", "빈칸어법", "영작배열"):
        chunk = c_pages[j:j + n_problems]
        out[name] = (chunk[0], chunk[-1])
        j += n_problems
    return out


def load_frames(frames_json):
    """본문 프레임만 (머리말 y<=0 제외, 빈 프레임 제외)."""
    d = json.load(open(frames_json, encoding="utf-8"))
    return [f for f in d["frames"] if f["gb"][0] > 0 and f["chars"] > 0], d["page_count"]


def page_codes(frames):
    """페이지 → 대표 코드 (위에서부터 첫 코드). 어법 O/X 처럼 코드가 별도
    숫자 프레임으로 있는 섹션을 위한 폴백."""
    by = defaultdict(list)
    for f in frames:
        by[f["pidx"]].append(f)
    out = {}
    for pi, fs in by.items():
        for f in sorted(fs, key=lambda x: x["gb"][0]):
            c = code_of(f["head"])
            if c:
                out[pi] = c
                break
    return out


def frame_code(f, pcodes):
    """프레임 코드 — 자기 머리 우선, 없으면 페이지 대표 코드."""
    return code_of(f["head"]) or pcodes.get(f["pidx"])


def section_index(frames, first_page, last_page):
    """섹션 구간의 프레임을 지문 코드별로 묶는다 (비스레드 섹션용)."""
    pcodes = page_codes(frames)
    got = defaultdict(list)
    for f in frames:
        pg = f["pidx"] + 1
        if not (first_page <= pg <= last_page):
            continue
        c = frame_code(f, pcodes)
        if c:
            got[c].append(f)
    return dict(got)


def thread_marks(stories_json, first_page):
    """스레드 스토리(영작배열/실전)의 **텍스트 내부** 코드 마커를 문단 순서대로.

    반환: [(문단 인덱스, 코드), ...]. 이 위치로 스레드를 분할하면 프레임
    머리로는 못 잡는 지문(26년 6월 실전의 30·33)까지 전량 분리된다.
    """
    d = json.load(open(stories_json, encoding="utf-8"))

    def pnum(x):
        s = re.sub(r"\D", "", str(x))
        return int(s) if s else -1

    # 섹션 시작 페이지에는 라벨 프레임 스토리('영작 배열' 1문단)도 함께 있다.
    # 마커가 가장 많은 스토리를 본문 스레드로 택한다 (문단수 최다가 아니라
    # 마커 최다 — 라벨/부속 스토리가 길어지는 회차에도 안전).
    best, best_marks = None, []
    for st in d.get("stories", []):
        ns = [pnum(p) for p in (st.get("pg") or [])]
        if not ns or min(ns) != first_page:
            continue
        marks = []
        for i, p in enumerate(st.get("paragraphs", [])):
            c = code_of(p.get("t"))
            if c:
                marks.append((i, c))
        if len(marks) > len(best_marks):
            best, best_marks = st, marks
    if best is None:
        return []
    return best_marks


def build_inventory(frames_json, stories_json, sections, canon, threaded=None):
    """threaded: 텍스트 내부 마커로 봐야 하는 섹션 집합.

    분할(Phase 1) 전에는 영작 배열이 스레드라 THREADED 기본값을 쓰고,
    분할 후에는 페이지 단위로 잡히므로 `threaded=set()` 을 넘긴다.
    """
    return _build_inventory(frames_json, stories_json, sections, canon,
                            THREADED if threaded is None else threaded)


def _build_inventory(frames_json, stories_json, sections, canon, threaded):
    """섹션 정의 + canon 지문 목록 → 지문별 슬롯 인벤토리 + 검증 리포트.

    sections: {섹션명: (first_page, last_page)}
    canon:    ['20','21',...] (normalize_code 적용된 코드)
    """
    frames, page_count = load_frames(frames_json)
    canon = [normalize_code(c) for c in canon]
    inv = {c: {} for c in canon}
    report = []

    for name, _slot, _master in SLOTS:
        rng = sections.get(name)
        if not rng:
            report.append({"section": name, "status": "범위 미정의"})
            continue
        first, last = rng
        if name in threaded:
            marks = thread_marks(stories_json, first)
            seen = set()
            extra = []
            for i, raw in marks:
                c = resolve_to_canon(raw, canon)
                if c:
                    seen.add(c)
                    inv[c][name] = {"kind": "thread", "para": i, "raw": normalize_code(raw)}
                else:
                    extra.append(normalize_code(raw))
            missing = [c for c in canon if c not in seen]
            report.append({"section": name, "kind": "thread",
                           "found": len(seen), "missing": missing, "extra": extra})
        else:
            got = section_index(frames, first, last)
            seen = {}
            extra = []
            for raw, fs in got.items():
                c = resolve_to_canon(raw, canon)
                if c:
                    seen.setdefault(c, []).extend(fs)
                else:
                    extra.append(raw)
            for c, fs in seen.items():
                inv[c][name] = {"kind": "frames",
                                "pages": sorted({f["pidx"] + 1 for f in fs}),
                                "frames": len(fs)}
            missing = [c for c in canon if c not in seen]
            report.append({"section": name, "kind": "frames",
                           "found": len(seen), "missing": missing, "extra": extra})

    return {"page_count": page_count, "inventory": inv, "report": report}


def gate(result, canon):
    """게이트 — 실패 사유 리스트를 반환한다 (빈 리스트 = 통과)."""
    fails = []
    canon = [normalize_code(c) for c in canon]
    for r in result["report"]:
        if r.get("status"):
            fails.append("%s: %s" % (r["section"], r["status"]))
            continue
        if r.get("missing"):
            fails.append("%s: 지문 %s 미검출" % (r["section"], r["missing"]))
    for c in canon:
        got = result["inventory"].get(c, {})
        lack = [n for n, _s, _m in SLOTS if n not in got]
        if lack:
            fails.append("지문 %s: 슬롯 %s 없음" % (c, lack))
    return fails
