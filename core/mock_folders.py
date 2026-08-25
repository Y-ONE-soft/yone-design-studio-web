# -*- coding: utf-8 -*-
"""모의고사 작업 폴더의 '회차 폴더' 열거 — 연도 묶음 폴더 흡수.

구조 (실측 2026-08-25):
    모의고사 작업/고2/고2 25년 3월/            ← 학년 폴더 바로 밑 (원래 구조)
    모의고사 작업/고1/고1 26년 3월/            ← 최근 회차는 아직 평면
    모의고사 작업/고1/고1 25년(3,6,9,10,11월)/고1 25년 3월/   ← 한 단계 내려감

고1 21~25년이 연도 묶음 폴더 안으로 들어가면서, 학년 폴더를 한 겹만
listdir 하던 코드가 전부 회차 폴더를 못 찾게 됐다. 게다가 묶음 폴더 이름
"고1 25년(3,6,9,10,11월)" 은 `"11월" in name` 을 만족해서 **11월 회차로
오인**된다 (analysis_merge 1차 매칭 실측) — 못 찾는 것보다 나쁘다.

그래서 판정을 이름 규칙이 아니라 **구조**로 한다: 학년 폴더 밑의 디렉터리
중 "회차 이름의 하위 디렉터리를 가진 것"은 묶음 폴더로 보고 그 자식들을
대신 내보낸다. 묶음 폴더 자체는 회차가 아니므로 목록에서 뺀다(위 오인 차단).
폴더명이 또 바뀌어도(`고1 21-25년` 등) 구조가 같으면 그대로 동작한다.

내려가는 깊이는 한 단계뿐이다 — GDrive 를 깊게 걷지 않는다.
"""

import os
import re
import unicodedata

__all__ = ["month_dir_entries", "is_round_name"]

# "고1 25년 3월" / "25년 3월" / "2025년 03월" — 회차 폴더 이름
_RE_ROUND = re.compile(r"^(?:고\s*\d\s*)?(\d{2,4})\s*년\s*(\d{1,2})\s*월$")


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def is_round_name(name):
    """'고1 25년 3월' 처럼 회차 하나를 가리키는 폴더 이름인가."""
    return bool(_RE_ROUND.match(_nfc(name).strip()))


def _plain_lister(folder):
    """기본 열거 — os.listdir + NFC. [(name_nfc, full_path)]"""
    try:
        raws = os.listdir(folder)
    except OSError:
        return []
    return [(_nfc(r), os.path.join(folder, r)) for r in raws
            if not r.startswith(".")]


def _dirs(folder, lister):
    return [(n, p) for n, p in (lister(folder) or []) if os.path.isdir(p)]


def month_dir_entries(grade_dir, lister=None, include_groups=False):
    """학년 폴더 밑의 회차 폴더 목록 — 연도 묶음 폴더는 한 단계 펼쳐서.

    Args:
        grade_dir: `모의고사 작업/고1` 같은 학년 폴더
        lister: (folder) -> [(name_nfc, src_path)] 열거자.
            None 이면 os.listdir. 호출부가 '미러 ∪ GDrive 합집합'
            (`engines.final.extractor.list_manuscript_entries`) 을 쓰던
            자리는 그대로 그 함수를 넘기면 된다.
        include_groups: True 면 묶음 폴더 자체도 목록에 남긴다(진단용).

    Returns:
        정렬된 [(name_nfc, path)] — 디렉터리만. 회차가 아닌 폴더
        ("한영고1 마더텅 예전 기출", "고2 20년 이전" 등)는 종전처럼 그대로
        포함된다 — 기존 호출부의 다른 탐색이 깨지지 않게 하기 위해서다.
    """
    if not grade_dir:
        return []
    lister = lister or _plain_lister

    out = {}
    for name, full in _dirs(grade_dir, lister):
        # 자식 열거는 학년 폴더 기준 경로로 — lister 가 미러 경로를 돌려주면
        # 그 밑을 다시 열거할 때 GDrive 정본과의 합집합이 끊긴다.
        probe = os.path.join(grade_dir, name)
        if not os.path.isdir(probe):
            probe = full
        children = _dirs(probe, lister) if not is_round_name(name) else []
        rounds = [(n, p) for n, p in children if is_round_name(n)]
        if rounds:
            if include_groups:
                out.setdefault(name, full)
            for n, p in rounds:
                out.setdefault(n, p)
        else:
            out.setdefault(name, full)
    return sorted(out.items())
