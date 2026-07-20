# -*- coding: utf-8 -*-
"""파이널 어법수정 탐색기 공용 헬퍼 (W36 배치 E — 인식 전환).

docs/인식지점_전수감사.md §9 배치 E: `grammar_word_parser.py`의 find_* 8종이
리터럴 토큰 AND-체인이라 '어법 수정'(공백) 같은 토씨 변형에 탐색 0건·무로그로
침묵했다(감사 실증 #5, 2026-06-26 `.rsync-partial` 실사고의 무대).

전환 원칙 (W31 계승):
  1. 기존 리터럴 판정은 1선 그대로 (하위호환 하한 — 기존 매칭분 100% 유지).
  2. 리터럴이 못 읽은 파일만 정규화(NFC·공백/언더스코어/괄호 제거) +
     subsequence 폴백으로 추가 인식 (additive — `_find_manuscript_file`의
     LCS/subsequence 자산 재사용, engines/workbook/parser.py:1805).
  3. 침묵 금지 — 기대 소스(폴더)가 있는데 탐색 0건이면 후보 목록과 함께
     [경고] (파이널은 다중 소스라 부분 부재가 정상일 수 있어 [오류] 아님 —
     감사 §9 E안의 운영 판단).

안전 밸브: YONE_FINAL_FUZZY_FIND=0 이면 폴백 전체 무효 (리터럴 단독 =
기존 동작. W31 USE_STRUCT_HEADER_DETECT 패턴).
"""

import os
import re
import unicodedata

# 안전 밸브 환경변수 (기본 on)
_VALVE_ENV = "YONE_FINAL_FUZZY_FIND"

# 폴백 판정에서 제외할 답안류 토큰 (정규화된 이름 기준)
_EXCLUDE_TOKENS = ("정답", "해설")

# 정규화된 이름 기준 범위 변형 파일명 ("41~42번 어법수정" → "4142번어법수정")
_RE_NORM_RANGE_VARIANT = re.compile(r"^\d{1,4}번어법수정")


def fuzzy_enabled():
    """폴백 활성 여부 — YONE_FINAL_FUZZY_FIND=0/false/no 로 무효화."""
    return os.environ.get(_VALVE_ENV, "1").strip().lower() not in (
        "0", "false", "no", "off")


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def norm_token(name):
    """파일/폴더명 정규화 — NFC + 영숫자/한글 외 전부 제거 + 소문자.

    `_find_manuscript_file`(engines/workbook/parser.py)의 _normalize 재사용.
    확장자는 제거하지 않는다 — 호출부가 stem을 넘기거나 폴더명을 넘긴다.
    """
    return re.sub(r"[^A-Za-z0-9가-힣]", "", _nfc(name)).lower()


def _is_subseq(short, long_):
    """short가 long_의 subsequence인지 (_find_manuscript_file 동일 로직)."""
    if not short:
        return True
    i = 0
    slen = len(short)
    for ch in long_:
        if short[i] == ch:
            i += 1
            if i == slen:
                return True
    return False


def fuzzy_grammar_match(fn, require_probsheet=True, allow_range_variant=False):
    """어법수정 문제지 파일의 **폴백 전용** 판정 (additive).

    호출부의 기존 리터럴 판정이 실패한 파일에 대해서만 호출한다 —
    리터럴 매칭분은 이 함수와 무관하게 그대로 유지된다.

    판정 (전부 정규화된 이름 기준):
      - .docx (대소문자 무관) + 임시파일(~) 아님
      - 답안류 토큰(정답/해설) 미포함 — 폴백 경로에서는 정규화 기준으로
        판정하므로 '정 답' 같은 변형도 제외된다 (리터럴 매칭분은 무영향)
      - '어법수정' 정규화 substring (예: '어법 수정', '어법_수정', '어법(수정)',
        '어법 수정본'). subsequence 티어는 실 GDrive 전수 sweep에서
        'Step2 A1 어법선택(수정)'/'어법 OX(수정)' 워크북 파일 6건을 오탐해
        폐기 — 감사 실증 #5(공백)는 정규화 substring만으로 회복된다.
      - require_probsheet: '문제지' substring 또는 '…문제' 끝맺음
        (기존 '문제지' / '_문제.docx' 두 표기의 정규화 일반화)
      - allow_range_variant: '41~42번 어법수정' 류 범위 변형 파일명 허용
        (이 경우 문제지 표기는 불요 — 기존 is_range_variant 의미론)
    """
    if not fuzzy_enabled():
        return False
    fn = _nfc(fn)
    if fn.startswith("~") or fn.startswith("."):
        return False
    stem, ext = os.path.splitext(fn)
    if ext.lower() != ".docx":
        return False
    norm = norm_token(stem)
    if not norm:
        return False
    if any(t in norm for t in _EXCLUDE_TOKENS):
        return False
    # 키 토큰: 정규화 substring (subsequence 티어는 실측 오탐으로 폐기 — docstring)
    if "어법수정" not in norm:
        return False
    if allow_range_variant and _RE_NORM_RANGE_VARIANT.match(norm):
        return True
    if require_probsheet:
        return "문제지" in norm or norm.endswith("문제")
    return True


def folder_token_match(dirname, token):
    """폴더명 정규화 2차 매칭 — token(정규화)이 dirname(정규화)에 포함되는지.

    기존 리터럴 매칭(1차)이 실패했을 때만 호출한다.
    예: '공통영어1 능률(민)' ↔ '공통영어1_능률민' / '어법 수정 폴더'.
    """
    if not fuzzy_enabled():
        return False
    nt = norm_token(token)
    return bool(nt) and nt in norm_token(dirname)


def list_docx_candidates(folders, limit=24):
    """경고 리포트용 — 폴더(들) 아래 .docx 후보 파일명 나열 (재귀, dot-dir 제외).

    탐색 0건일 때 '무엇이 있었는지'를 로그에 남기기 위한 목록.
    OSError(GDrive EDEADLK 등)는 조용히 건너뛴다 (리포트 용도라 fail-safe).
    """
    if isinstance(folders, str):
        folders = [folders]
    out = []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            # .rsync-partial 등 숨김 dot-디렉토리 가지치기 (dev-guide 2026-06-26)
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            try:
                for f in files:
                    fn = _nfc(f)
                    if fn.startswith(("~", ".")):
                        continue
                    if fn.lower().endswith(".docx"):
                        out.append(fn)
                        if len(out) >= limit:
                            return out
            except OSError:
                continue
    return out


def warn_zero(log, label, folders, kind=".docx"):
    """탐색 0건 침묵 금지 — 후보 목록과 함께 [경고] 로그.

    label: 어떤 기대 소스가 0건인지 (예: '3과', '모의고사 25년 10월').
    folders: 탐색했던 폴더(들) — 후보 나열 대상.
    """
    if not log:
        return
    cands = list_docx_candidates(folders) if kind == ".docx" else []
    if cands:
        shown = ", ".join(cands[:8])
        more = f" 외 {len(cands) - 8}개" if len(cands) > 8 else ""
        log(f"  [경고] [어법수정] {label}: 매칭 0건 — 폴더 내 .docx 후보: "
            f"{shown}{more}")
    else:
        log(f"  [경고] [어법수정] {label}: 매칭 0건 — 폴더 내 .docx 후보 없음")
