"""어법수정 원고 스왑 — STEP2 A1 슬롯 원고를 어법수정본으로 교체.

광문고 슬림처럼 "어법 선택"을 "어법 수정"으로 바꾸는 학교는, 헤더 표기
(단원 마커)뿐 아니라 **지문 내용도 어법수정 원고**로 조판해야 한다.

어법수정 원고는 어법선택 원고와 헤더 체계가 같고(`N. p2-no.20`,
`N. L1-p. 17 본문 1`) 대괄호 형식만 다르다:
    어법 선택  1[holds / hold]   (2지선다)
    어법 수정  1[what]           (고칠 대상 단일)
그래서 **파일명만 STEP2 A1 슬롯 이름으로 바꿔 끼우면** 기존 파서·조판
경로가 그대로 처리한다 (라우팅은 파일명 기반).

원고 위치가 계열마다 달라 파일명도 완전히 일치하지 않는다 (실측):
    모의고사  고2 26년 6월/고2_2026_06월-읽기영역(18~45번)_어법수정_문제지.docx
    모의고사  고2 22년 9월/고2 22년 9월 직전보충/..._어법수정_문제지.docx
    교과서    공통영어2 능률(민) 1과/공통영어2_NE능률민병천-...._어법수정_문제지.docx
    교과서    공통영어1 YBM(김) 1과/... 직전보충/공통영어1_YBM김은형-...._어법수정_문제지.docx
    올포      올림포스 독해기본2 7강/올림포스...Unit07..._어법수정_문제지.docx
    수특라이트 1강/* 직전 보충 자료.docx          ← 유일하게 '어법수정' 미포함
공통 규칙: 정규화 후 '어법수정' + '문제지' 를 포함하거나, '직전보충자료'
계열. 해설지/정답지는 제외.
"""

import os
import re
import shutil
import unicodedata

# 어법수정 문제지 판정에 쓰는 정규화 토큰
_TOK_GRAMMAR = "어법수정"
_TOK_PROBLEM = "문제지"
_TOK_SUPPLEMENT = "직전보충자료"

# 답안류 — 문제지 자리에 들어가면 정답이 그대로 인쇄된다 (절대 제외)
_ANSWER_TOKENS = ("정답", "해설", "답지", "답안")

# STEP2 A1 슬롯으로 라우팅되는 기존 원고 (교체 대상)
_RE_STEP2_A1 = re.compile(r"step2.*a1.*어법", re.I)

_DEFAULT_SLOT_NAME = "Step2 A1 어법선택.docx"


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def norm(name):
    """NFC + 영숫자/한글 외 제거 + 소문자 (공백·언더스코어·괄호 흡수)."""
    return re.sub(r"[^A-Za-z0-9가-힣]", "", _nfc(name)).lower()


def is_answer_file(name):
    n = norm(name)
    return any(tok in n for tok in _ANSWER_TOKENS)


def is_grammar_fix_manuscript(name):
    """어법수정 '문제지'인가 (해설지/정답지는 False)."""
    n = norm(name)
    if is_answer_file(name):
        return False
    if _TOK_GRAMMAR in n and _TOK_PROBLEM in n:
        return True
    # EBS 수특라이트 예외 — '* 직전 보충 자료.docx' (파일명에 어법수정 없음)
    if _TOK_SUPPLEMENT in n:
        return True
    return False


def find_grammar_fix(paths):
    """업로드 목록에서 어법수정 문제지 1개를 고른다 (없으면 None)."""
    hits = [p for p in paths
            if is_grammar_fix_manuscript(os.path.basename(p))]
    if not hits:
        return None
    # 여러 개면 '어법수정+문제지'가 명시된 쪽을 우선 (직전보충자료는 폴백)
    explicit = [p for p in hits
                if _TOK_GRAMMAR in norm(os.path.basename(p))]
    return sorted(explicit or hits)[0]


def _slot_targets(paths):
    """교체 대상 — STEP2 A1 어법 슬롯으로 라우팅되는 기존 원고들."""
    out = []
    for p in paths:
        base = _nfc(os.path.basename(p))
        # routes 가 붙인 슬롯 접두어(manuscripts_) 제거 후 판정
        stem = base.split("_", 1)[1] if base.startswith("manuscripts_") else base
        if _RE_STEP2_A1.search(stem) and not is_answer_file(stem):
            out.append(p)
    return out


def wanted(job_dir):
    """어법 교체가 요청됐는지 — 슬림 마커 교체 체크박스와 같은 신호."""
    for key in ("slim_rename", "rename_markers"):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            try:
                if "어법" in open(path, encoding="utf-8").read():
                    return True
            except OSError:
                pass
    return False


def swap_grammar_manuscript(job_dir, uploaded, log):
    """업로드 원고 중 어법수정본을 STEP2 A1 슬롯 이름으로 바꿔 끼운다.

    요청이 없거나 어법수정 원고가 업로드에 없으면 no-op (마커 표기만 바뀐다).
    uploaded 를 제자리에서 수정한다.
    """
    if not wanted(job_dir):
        return None

    key = None
    for cand in ("manuscripts", "manuscript_files", "files"):
        if isinstance(uploaded.get(cand), list):
            key = cand
            break
    if not key:
        return None

    paths = uploaded[key]
    src = find_grammar_fix(paths)
    if not src:
        log("[어법교체] 업로드에 어법수정 문제지가 없습니다 — 표기만 변경됩니다")
        return None

    targets = _slot_targets(paths)
    # 교체 대상의 파일명을 그대로 물려받는다 (계열별 슬롯 명칭 차이 흡수).
    if targets:
        slot_base = _nfc(os.path.basename(targets[0]))
    else:
        prefix = "manuscripts_" if os.path.basename(
            paths[0]).startswith("manuscripts_") else ""
        slot_base = prefix + _DEFAULT_SLOT_NAME
        log("[어법교체] [경고] 기존 어법선택 원고를 못 찾아 기본 슬롯명 사용: "
            f"{_DEFAULT_SLOT_NAME}")

    # 기존 어법선택 원고는 목록에서 제외 (파일은 남겨 두되 조판에서 뺀다)
    for t in targets:
        paths.remove(t)
        log(f"[어법교체] 제외: {os.path.basename(t)}")

    dst = os.path.join(os.path.dirname(src), slot_base)
    if os.path.abspath(dst) != os.path.abspath(src):
        if os.path.exists(dst):
            os.remove(dst)
        shutil.copy2(src, dst)
        if src in paths:
            paths.remove(src)
    if dst not in paths:
        paths.append(dst)

    log(f"[어법교체] {os.path.basename(src)} → {slot_base} 슬롯으로 투입")

    # 지문만 어법수정본으로 바뀌고 정답지는 어법선택 것이 남으면 불일치 —
    # 조판에서 정답을 쓰는 경로가 있으면 틀린 답이 실린다. 고지만 한다
    # (정답지 슬롯 명칭이 계열마다 달라 자동 교체는 하지 않는다).
    stale_answers = [p for p in paths
                     if _RE_STEP2_A1.search(_nfc(os.path.basename(p)))
                     and is_answer_file(os.path.basename(p))]
    for p in stale_answers:
        log(f"[어법교체] [경고] 어법선택 정답지가 남아 있습니다 — 지문과 "
            f"불일치 가능: {os.path.basename(p)}")

    return {"src": src, "slot": slot_base, "removed": targets,
            "stale_answers": stale_answers}
