"""
워크북 원고 파서

docx/hwp 원고 → 단락 목록 → STEP별 분류 → content.json

지원 형식:
  - docx: python-docx (zipfile + XML) 직접 파싱
  - hwp:  블랙북 방식 (hwpx ZIP → section XML + header XML)

원고 파일별 처리:
  Step1 A1~C2, Step2 B1~C2: 텍스트만 추출
  Step2 A1 어법선택: 텍스트 + 밑줄 추출 (runs[].ul)
  Step3 실전문제 (hwp): 텍스트 + 밑줄 추출

단락 데이터 구조:
  {"text": str, "runs": [{"t": str, "ul": bool}]}
"""

import html
import json
import logging
import os
import re
import struct
import sys
import unicodedata
import zipfile

_LOG = logging.getLogger(__name__)


from core.extract.extractors import (  # Phase 1: 추출 계층 core 이동 (동작 동일)
    _NS_W,
    _nfc,
    _docx_extract_paragraphs,
    _parse_underline_ids,
    _hwpx_extract_segments,
    _hwpx_extract_paragraphs,
    _hwp_is_hwpx,
    _hwp_decode_paratext,
    _hwp_decode_para_charshape,
    _hwp_build_charshape_ul,
    _hwp_text_with_underline,
    _DINGBAT_TO_STD,
    _normalize_circled_numbers,
    _RE_SRC_BAR,
    _hwp_extract_paragraphs,
)


# ── 원고 공통 전처리 ────────────────────────────────────────────────────────

# 원고 헤더 패턴 (스킵할 줄)
_RE_MANUSCRIPT_HEADER = re.compile(
    r'^(?:'
    r'고[12]_\d{4}_\d+월'     # "고1_2025_10월(경기도) - 읽기영역..."
    r'|[가-힣].*\s\d+\s*지문\s*$'  # "성덕2 EBS 4지문" 류 책/출처 제목 (… N지문)
    r'|Q\.\s'                  # "Q. 문맥 상..."
    r'|어휘[선완]'              # "어휘선택(문제지)", "어휘완성(문제지)"
    r'|어법[선수]'              # "어법선택(문제지)", "어법수정..."
    r'|빈칸어'                  # "빈칸어휘(문제지)"
    r'|낱말배열'                # "낱말배열(문제지)"
    r'|문장배열'                # "문장배열(문제지)"
    r'|틀린어법'                # "틀린어법(문제지)" — EBS A1 객관식
    r'|\d+\.\s+어휘\d+단계'    # "1. 어휘1단계_Hard"
    r'|\d+\.\s+내용[일종]'     # "1. 내용일치_Normal", "1. 내용종합_Normal"
    r'|마더텅\s+고[12]'        # "마더텅 고1 6강 옛날지문" (옛날 워크북 식별 헤더)
    r'|Reading\s*Power'        # "ReadingPower 유형편완성..." — EBS 리딩파워
    r'|\d{4}\s*수능특강'        # "2027수능특강 영어(2026) - ..." — EBS 수능특강
    r'|Exercises\s*$'          # 수능특강 발문 직후 "Exercises" 단독 줄
    r')'
)

# 지문 번호 구분자
_RE_BRACKET_NUM = re.compile(r'^\s*\[(\d+)\]\s*$')           # [20]
# 한글이 들어간 대괄호 발문: "[본문1]", "[다음 글의 ...]"
_RE_KOREAN_BRACKET = re.compile(r'^\s*\[[^\]]+\]\s*$')
# 페이지/레슨 마커: 출판사·교재 종류 무관하게 다양한 형식 매칭
#   p<n>, p.<n>           (모의고사/EBS:  p2, p.82)
#   L<n>                  (교과서 단순:  L1)
#   L<n>-p<n>, L<n>-p.<n> (교과서:       L4-p.82)
#   L<n>-본문<n>           (교과서:       L1-본문1)
#   U<n>                  (EBS Unit:     U6)
_RE_PAGE_MARKER = (
    r'(?:'
    r'L\d+(?:\s*[-–—]\s*(?:p\.?\d+|본문\d+))?'
    r'|p\.?\d+'
    r'|U\d+'
    r')'
)
# 지문 헤더: "[순서.] <페이지/레슨 마커>[-/구분자] [라벨] [<지문번호>][한글 꼬리][(부가정보)]"
#   예) "1. p2-no.18", "18. p8-no.41~42",
#       "1. p8-Example 1", "p66-Example 1",
#       "3. p86-no.1", "1. p8-Example 1  (정답 1개)",
#       "1. L4-p.82", "1. L4-p.82  (정답 1개)",
#       "1. L1-본문1  (정답 1개)",
#       "1. p1-no.3과 추가지문" (교과서 추가지문형 — 지문번호 뒤 한글 라벨 꼬리)
#       "1. p80-수능 Analysis" (부교재 코너명형 — 한글 코너명 + 영문 토큰, W12)
# 라벨은 no., Example, Test 등 임의의 영문 토큰 허용 (특정 단어에 의존하지 않음).
# 한글 꼬리는 선택 그룹이라 기존 형식 매칭에는 영향이 없다 (2026-07 W11).
# W12: 꼬리에 영문 혼용 허용 ("수능 Analysis") — 꼬리 시작은 여전히 한글이라
# 순수 영문 본문/제목 줄에는 영향 없음.
_RE_HEADER_NUM = re.compile(
    r'^\s*'
    r'(?:\d+\s*[\.\)]\s*)?'                                  # 선행 순번 "N." 또는 "N)" (있으면)
    + _RE_PAGE_MARKER +                                       # 페이지/레슨 마커
    r'\s*[-–—\.]?\s*'                                        # 구분자 (선택)
    r'(?:no\.\s*|Example\s+|Practice\s+|[A-Za-z]+\.?\s*)?'   # 라벨 (선택)
    r'(\d+(?:\s*~\s*\d+)?)?'                                 # 지문 번호 (캡처, 선택)
    r'(?:\s*[가-힣][가-힣0-9A-Za-z\s]{0,30})?'               # 한글 라벨 꼬리 "과 추가지문"/"수능 Analysis" 등 (선택)
    r'(?:\s*\([^\)]*\))?'                                    # 트레일링 부가정보 "(정답 1개)" 등 (선택)
    r'\s*$'
)
# Chapter 구분선 (EBS 등): "Chapter 03. 추론적 이해 - 09 빈칸 추론 (1)"
_RE_CHAPTER_DIVIDER = re.compile(r'^\s*Chapter\s+\d+\.\s', re.IGNORECASE)
# Unit 구분선 (부교재 코너명형, W12): "Unit 10 긴 어구 빈칸" / "Unit 13 문장 삽입"
# — 원전 교재의 단원+유형명 구분선. 숫자 뒤가 한글 유형명일 때만 매치
# (영문 본문 "Unit 15 ..."류 문장은 제외).
_RE_UNIT_DIVIDER = re.compile(r'^\s*Unit\s+\d+\s+[가-힣][가-힣0-9\s]{0,30}$')

# 옛 형식 워크북 헤더 (마더텅 옛 기출 등)
# "9번" 단독 줄 + "17년 11월 21번" 단독 줄 → "9. p0-no.21" 표준 형식으로 정규화
_RE_OLD_WB_NUM = re.compile(r'^\s*(\d+)\s*번\s*$')
_RE_OLD_WB_SOURCE = re.compile(r'^\s*\d+\s*년\s*\d+\s*월\s*(\d+)\s*번\s*$')


def _normalize_old_workbook_headers(paragraphs):
    """
    옛 마더텅 워크북 형식 헤더를 표준 형식으로 정규화.

    변환:
        "9번"               → 두 줄 합쳐 "9. p0-no.21" 한 줄로
        "17년 11월 21번"

    빈 단락이 사이에 끼어있어도 처리. 정상 원고(이미 "1. p2-no.20" 형식)에는
    매치되지 않으므로 영향 없음.
    """
    result = []
    i = 0
    n = len(paragraphs)
    while i < n:
        m_num = _RE_OLD_WB_NUM.match(paragraphs[i]['text'].strip())
        if m_num:
            # 다음 비빈 단락에서 출처(YY년 M월 K번) 패턴 찾기
            j = i + 1
            while j < n and not paragraphs[j]['text'].strip():
                j += 1
            if j < n:
                m_src = _RE_OLD_WB_SOURCE.match(paragraphs[j]['text'].strip())
                if m_src:
                    wb_num = m_num.group(1)
                    mock_num = m_src.group(1)
                    new_text = "%s. p0-no.%s" % (wb_num, mock_num)
                    result.append({
                        "text": new_text,
                        "runs": [{"t": new_text, "ul": False}],
                    })
                    i = j + 1
                    continue
        result.append(paragraphs[i])
        i += 1
    return result


# 옛 헤더 정규화 산출물 패턴 ("9. p0-no.21")
_RE_OLD_NORMALIZED_HEADER = re.compile(r'^\s*\d+\.\s*p0-no\.\d+', re.UNICODE)
# 정상(잡) 헤더 패턴 ("1. p3-no.21" 등, p0이 아닌 페이지 번호)
_RE_PRIMARY_HEADER_NONZERO = re.compile(r'^\s*\d+\.\s*p[1-9]\d*-no\.\d+', re.UNICODE)


def _strip_secondary_headers_after_old(paragraphs):
    """
    옛 헤더가 변환된 이후 본문 안에 끼어있는 정상 형식 헤더("1. p3-no.21" 등)를 제거.

    옛 마더텅 원고에는 본 보기 다음에 의미 없는 추가 헤더가 끼어있어 두 번째
    프레임브레이크가 잘못 들어가는 문제가 있다. 옛 헤더가 한 번이라도 변환된
    원고에서만 동작하므로 정상 원고("1. p2-no.20" 형식만 있음)에는 매치되지 않음.
    """
    has_old = False
    result = []
    for p in paragraphs:
        text = p['text'].strip()
        if _RE_OLD_NORMALIZED_HEADER.match(text):
            has_old = True
            result.append(p)
            continue
        if has_old and _RE_PRIMARY_HEADER_NONZERO.match(text):
            # 옛 블록 안에 끼어있는 잡 헤더 제거
            continue
        result.append(p)
    return result


# 본 보기 (A)~(Z) 패턴
_RE_CHOICE = re.compile(r'^\s*\([A-Z]\)\s')
# 원문자 ① ~ ⑳ 시작 또는 포함
_RE_CIRCLED_START = re.compile(r'^[\s\(]*[①-⑳⓵-⓿❶-❿]')


def _wrap_hadan_with_spaces(paragraphs):
    """
    옛 헤더 변환된 원고에서 본 보기 블록이 끝난 직후의 첫 비빈 영어 단락
    (= 문장 배열 하단의 '주어진 문장')에 양쪽 9칸 공백을 둘러싼다.

    정상 원고는 원본 .docx 단계에서 이미 양쪽 공백이 있어 has3PlusGaps을 트리거
    하지만, 옛 마더텅 원고는 공백 없이 평문으로 들어있어 BTM 인식이 안 된다.
    이 함수는 옛 헤더가 한 번이라도 변환된 원고에서만 동작하므로 정상 원고에
    영향이 없다.

    상태:
        IDLE / AFTER_HEADER / IN_CHOICES / AFTER_CHOICES
    """
    if not any(_RE_OLD_NORMALIZED_HEADER.match(p['text'].strip()) for p in paragraphs):
        return paragraphs

    result = []
    state = 'IDLE'

    for p in paragraphs:
        text = p['text'].strip()
        is_header = bool(_RE_OLD_NORMALIZED_HEADER.match(text)) or \
                    bool(_RE_PRIMARY_HEADER_NONZERO.match(text))
        is_choice = bool(_RE_CHOICE.match(text))
        is_empty = not text
        is_circled_start = bool(_RE_CIRCLED_START.match(text))

        if is_header:
            state = 'AFTER_HEADER'
            result.append(p)
            continue

        if state == 'AFTER_HEADER' and is_choice:
            state = 'IN_CHOICES'
            result.append(p)
            continue

        if state == 'IN_CHOICES':
            if is_choice:
                result.append(p)
                continue
            if is_empty:
                state = 'AFTER_CHOICES'
                result.append(p)
                continue
            # 보기 블록 안에 갑자기 다른 패턴 → 안전하게 종료
            state = 'AFTER_CHOICES'

        if state == 'AFTER_CHOICES':
            if is_empty:
                result.append(p)
                continue
            # 헤더면 다음 지문 시작 — wrap 없이 통과
            if is_header:
                state = 'AFTER_HEADER'
                result.append(p)
                continue
            # 원문자(①②) 시작 단락은 주어진 문장 아니라 BTM_T 본문 — 그대로
            if is_circled_start:
                state = 'IDLE'
                result.append(p)
                continue
            # (A)~(Z) — 주어진 문장 없이 바로 변형 보기 시작 — 그대로 BTM_T 처리에 맡김
            if is_choice:
                state = 'IDLE'
                result.append(p)
                continue
            # 그 외 영어 평문 단락 → 주어진 문장. 양쪽 9칸 공백 추가해 has3PlusGaps 트리거
            wrapped_text = "         " + p['text'] + "        "
            new_runs = ([{"t": "         ", "ul": False}] +
                        list(p.get('runs', [])) +
                        [{"t": "        ", "ul": False}])
            result.append({"text": wrapped_text, "runs": new_runs})
            state = 'IDLE'
            continue

        result.append(p)

    return result


_RE_ENG_WORD = re.compile(r'[A-Za-z]+')


def _eng_word_count(text):
    return len(_RE_ENG_WORD.findall(text))


def _is_body_line(text):
    """긴 영어 콘텐츠(지문 본문/제목 등) — 짧은 번호 마커와 구분하는 기준."""
    return _eng_word_count(text) >= 5


def _is_passage_marker_struct(paragraphs, i):
    """지문번호 마커를 '형식'이 아니라 '구조'로 판정.

    특정 출판사 형식(L1-본문1 / p2-no.20 / [본문1] / PROJECT 2-본문1 …)에
    의존하지 않고, 보편 구조 특징으로 인식한다:
      - 짧은 줄 (헤더/본문보다 훨씬 짧음)
      - 숫자를 포함 (번호 성격)
      - 영단어가 적음 (영어 문장=본문/제목이 아님)
      - 바로 뒤에 본문(긴 영어)이 따라옴 (책 제목 등 헤더와 구분)
    지문번호 형식이 무엇으로 바뀌든(앞에 숫자·기호·단원명 무엇이 오든) 견고하다.
    """
    text = paragraphs[i]['text'].strip()
    if not text or len(text) > 40:
        return False
    if not re.search(r'\d', text):
        return False
    if _eng_word_count(text) >= 4:
        return False
    j = i + 1
    while j < len(paragraphs) and not paragraphs[j]['text'].strip():
        j += 1
    return j < len(paragraphs) and _is_body_line(paragraphs[j]['text'].strip())


# ── W34 배치 D: 구조 우선 헤더 인식 합류 (W31 core/structure/header_detect) ──
# v1 공유 파서의 헤더 판정 경로에 문서 단위 구조 인식기를 '합류'시킨다.
# 안전 계약 (docs/인식지점_전수감사.md §9 D안):
#   ① 정규식(_RE_HEADER_NUM 계열)이 인식하던 것은 전부 기존 경로 그대로
#      (하위호환 하한 — 골든 전 코퍼스 diff 0 계약)
#   ② 구조 인식기 추가 인식분은 additive — 정규식 미인식 라인만 승격
#   ③ 안전 밸브: 환경변수 YONE_PARSER_STRUCT_HEADERS=0 이면 합류 전체 무효
#      (정규식 단독 — 기존 동작). W31 plan.py USE_STRUCT_HEADER_DETECT 패턴.
# 침묵 금지(HeaderSilenceError) 승격은 여기서 하지 않는다 — v1 실서비스
# 파서에서 예외 승격은 배치 D 범위 밖이고, v2 계열은 플랜/게이트 계층
# (G6)이 같은 인식기로 이미 감시한다. 파서 합류는 '보강'만 (fail-open).
USE_STRUCT_HEADER_DETECT = (
    os.environ.get("YONE_PARSER_STRUCT_HEADERS", "1") != "0"
)


def _legacy_header_marker(text):
    """기존 정규식 헤더/마커 판정 — detect_headers의 legacy 프라이어.

    이 함수가 True인 라인은 기존 경로가 이미 소비하는 표기이므로 구조
    승격 대상에서 제외한다 (additive 계약의 경계). 옛 마더텅 형식
    (`9번`/`17년 11월 21번`)은 _normalize_old_workbook_headers가 표준형으로
    변환하는 기존 경로가 있어 함께 legacy로 취급한다."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        _RE_BRACKET_NUM.match(t) or _RE_HEADER_NUM.match(t)
        or _RE_KOREAN_BRACKET.match(t)
        or _RE_OLD_WB_NUM.match(t) or _RE_OLD_WB_SOURCE.match(t)
    )


def _struct_header_extras(paragraphs):
    """정규식 미인식 → 구조 인식 성공으로 '승격'된 라인 인덱스 집합.

    W31 인식기(core/structure/header_detect.detect_headers)를 문서 단위로
    돌리되, legacy 정규식이 이미 인식하는 라인은 결과에서 제외한다 —
    그 라인들의 처리는 기존 경로 100% 그대로 (additive 계약).
    밸브 off 또는 인식기 예외 시 빈 집합 (기존 동작으로 폴백)."""
    if not USE_STRUCT_HEADER_DETECT:
        return set()
    try:
        from core.structure.header_detect import detect_headers
        texts = [p['text'] for p in paragraphs]
        det = detect_headers(texts, legacy=_legacy_header_marker)
        return {i for i in det.header_idx
                if not _legacy_header_marker(texts[i])}
    except Exception:
        _LOG.warning("struct header detect 실패 — 정규식 단독 폴백",
                     exc_info=True)
        return set()


# 구조 승격 헤더에서 지문 번호 추출 (확신 가능한 표기만 — 모호하면 None):
#   no.N / N번(범위 N~M번 포함, 마지막 발생) / 본문N / (괄호부 제거 후) 유일 숫자
_RE_SQ_PARENS = re.compile(r'\([^)]*\)')
_RE_SQ_NO = re.compile(r'no\.?\s*(\d{1,3})(?:\s*~\s*\d{1,3})?', re.IGNORECASE)
_RE_SQ_BEON = re.compile(r'(\d{1,3})(?:\s*~\s*\d{1,3})?\s*번')
_RE_SQ_BONMUN = re.compile(r'본문\s*(\d{1,3})')
_RE_SQ_ANYNUM = re.compile(r'\d+')


def _struct_header_qnum(text):
    """구조 승격 헤더 라인 → 지문 번호 (int) 또는 None.

    정규식 헤더의 캡처 그룹이 선택이듯(예: '1. L4-p.82'는 번호 없음),
    확신할 수 없는 라인은 번호를 추측하지 않고 None을 반환한다 —
    헤더 인식(제거/분할)과 번호 추출을 분리하는 기존 의미론 유지.
    범위(41~42번)는 기존 규약대로 첫 번호만."""
    t = _RE_SQ_PARENS.sub(' ', (text or '').strip())
    m = _RE_SQ_NO.search(t)
    if m:
        return int(m.group(1))
    hits = _RE_SQ_BEON.findall(t)
    if hits:
        # 마지막 발생 — "1강 18번"의 18, "17년 11월 21번"의 21
        return int(hits[-1])
    m = _RE_SQ_BONMUN.search(t)
    if m:
        return int(m.group(1))
    nums = _RE_SQ_ANYNUM.findall(t)
    if len(nums) == 1 and len(nums[0]) <= 3:
        # 괄호부 제거 후 유일 숫자 — "지문 1 (p. 24)"의 1
        return int(nums[0])
    return None


def _strip_manuscript_headers(paragraphs, log=None):
    """원고 앞부분의 헤더 줄 제거.

    원고 구조: [책 제목 + 발문 + 섹션 라벨 + (선택적 부제목)] → [본문 마커 + 본문] 반복
    본문 마커 = 지문 헤더(`1. L4-p.82`, `1. p2-no.20`, `1. L1-본문1` 등) 또는 대괄호 발문(`[본문1]`, `[20]`).

    첫 본문 마커가 나오기 전까지의 모든 단락 = 헤더 영역으로 간주하고 제거.
    이렇게 단순화하면 책 제목/발문/섹션 라벨/부제목이 어떤 형식이든 (출판사/교재 변경 무관) 자동 처리됨.
    본문 마커가 끝까지 없는 STEP은 fallback으로 헤더 패턴 매칭을 사용.
    """
    starts = []

    # 1) 정규식 마커 우선 — 기존 검증된 형식(L1-본문1/p2-no.20/p20-Example 1/[본문1] 등).
    #    이게 잡는 한 예전과 100% 동일하게 동작하므로 회귀가 없다. (구조 판정 단독은
    #    EBS의 'Example' 형식이나 짧은 본문 첫 줄/한글 문장에서 첫 지문을 놓치거나
    #    오인할 수 있어, 검증된 정규식을 먼저 적용한다.)
    regex_idx = None
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        if not text:
            continue
        if (_RE_BRACKET_NUM.match(text) or _RE_HEADER_NUM.match(text)
                or _RE_KOREAN_BRACKET.match(text)):
            regex_idx = i
            break
    if regex_idx is not None:
        starts.append(regex_idx)

    # 1.5) W34 배치 D: 문서 단위 구조 승격 헤더 — 정규식 첫 마커보다 앞선
    #      승격 헤더가 있으면 그 지점부터 (첫 지문 침묵 유실 방지). 정규식
    #      첫 마커가 더 앞서면 기존과 동일 (additive — 시작점은 앞으로만 이동).
    extras = _struct_header_extras(paragraphs)
    if extras:
        starts.append(min(extras))

    # 2) 정규식이 못 잡는 새 형식(예: 'PROJECT 2-본문1') → 구조 인식으로 보강.
    #    정규식 화이트리스트에 형식을 계속 추가하지 않아도(땜질 회피) 새 형식을 잡는다.
    #    (기존 단계 순서 유지 — 정규식 미발견 시에만 소비하던 경로.)
    if regex_idx is None:
        for i, p in enumerate(paragraphs):
            if p['text'].strip() and _is_passage_marker_struct(paragraphs, i):
                starts.append(i)
                break

    if starts:
        return paragraphs[min(starts):]

    # 2) 본문 마커가 끝까지 없음 → fallback: 헤더 패턴 매칭으로 스킵
    start_idx = 0
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        if not text:
            continue
        if _RE_MANUSCRIPT_HEADER.match(text):
            start_idx = i + 1
            continue
        start_idx = i
        break

    # 배치 G (W37): 3계층(정규식/W34 구조 승격/구조 마커) 전부 미발견 상태에서
    # 헤더 라벨 패턴이 실제로 선두 단락을 버릴 때만 [경고] — 라벨 오판 시 본문이
    # 조용히 유실되던 지점의 가시화 (아무것도 안 버리는 no-op 폴백은 무해라 제외.
    # 예: 세로 C2 'NN번' 헤더 원고 — 코퍼스 실측으로 소음 배제). 동작 무변경.
    if log is not None and start_idx > 0:
        try:
            _dropped = [p['text'].strip() for p in paragraphs[:start_idx]
                        if p['text'].strip()]
            log(f"[경고] 본문 마커(지문 헤더) 미발견 — 헤더 라벨 패턴 폴백으로 "
                f"선두 {len(_dropped)}개 단락을 제거했습니다 (라벨 오판 시 본문 "
                f"유실). 제거 첫 단락: {(_dropped[0] if _dropped else '')[:50]!r}")
        except Exception:
            pass

    return paragraphs[start_idx:]


def _extract_question_numbers(paragraphs, step_key):
    """원고에서 지문번호 목록 추출.

    정규식 인식 라인은 기존 경로 그대로 (하위호환 하한). W34 배치 D:
    정규식 미인식 라인 중 구조 인식기(_struct_header_extras)가 헤더로
    승격한 라인은 확신 가능한 표기(_struct_header_qnum)에서만 번호를
    additive로 추가한다."""
    numbers = []
    extras = _struct_header_extras(paragraphs)
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        m = _RE_BRACKET_NUM.match(text)
        if m:
            numbers.append(int(m.group(1)))
            continue
        m = _RE_HEADER_NUM.match(text)
        if m:
            captured = m.group(1)
            if captured:
                # "41~42" 같은 범위는 첫 번호만 사용
                num_str = captured.split('~')[0]
                numbers.append(int(num_str))
            continue
        if i in extras:
            n = _struct_header_qnum(text)
            if n is not None:
                numbers.append(n)
    return numbers


def _clean_empty_lines(paras):
    """연속 빈줄 제거, 단일 빈줄은 유지."""
    cleaned = []
    prev_empty = False
    for p in paras:
        is_empty = not p['text'].strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(p)
        prev_empty = is_empty
    return cleaned


_RE_LESSON_MARKER = re.compile(r'^\s*\[L\d+[-—]\d+\]\s*$')  # [L1-9], [L2-3] 등


def _strip_lesson_markers(paras):
    """교과서 원고의 [L1-9] 형식 단원 구분 마커 제거."""
    return [p for p in paras if not _RE_LESSON_MARKER.match(p['text'])]


def _strip_chapter_dividers(paras):
    """EBS 리딩파워 등의 챕터/유닛 구분선을 모두 제거.

    "Chapter 03. ..."(기존) + "Unit 10 긴 어구 빈칸"(부교재 코너명형, W12).
    원고 곳곳에 끼어있는 단순 구분선이며 지문 본문이 아니라서 그대로 두면
    프레임 브레이크가 잘못 들어가거나 본문에 흡수된다.
    """
    return [p for p in paras
            if not _RE_CHAPTER_DIVIDER.match(p['text'])
            and not _RE_UNIT_DIVIDER.match(p['text'].strip())]


# 정답 구간 감지 패턴
_RE_ANSWER_SECTION = re.compile(
    r'^\s*\d+\.\s*(?:어휘|내용[일종]|어법|빈칸|영작|문장).*(?:정답|_정답)', re.UNICODE
)
_RE_ANSWER_HEADER = re.compile(r'^\s*(?:번호|정답)\s*$')
_RE_ANSWER_AND_EXPLANATION = re.compile(
    r'^\s*정답\s*(?:과|및|&)\s*해설\s*$', re.UNICODE
)
_RE_QUICK_ANSWER = re.compile(
    r'^\s*빠른\s*정답\s*찾기\s*$', re.UNICODE
)


def _remove_answer_section(paras, log=None):
    """
    원고에서 정답 섹션 제거.
    감지 패턴:
    - "1. 내용일치_Normal_정답" 등
    - "정답 및 해설" / "정답과 해설" 단독 줄
    - "빠른 정답 찾기" 단독 줄
    패턴이 나타나면 그 이후 모든 단락을 제거.

    배치 G (W37): log 콜백이 오면, 구 눈(위 패턴)이 절단하지 못했는데
    공유 rules.A_SECTION_HEADER(배치 B의 눈)가 정답부 헤더로 보는 라인이
    남아 있으면 [경고]를 남긴다 — '서로 다른 눈' 침묵의 가시화 (동작 무변경).
    """
    for i, p in enumerate(paras):
        text = p['text'].strip()
        if _RE_ANSWER_SECTION.match(text):
            return paras[:i]
        if _RE_ANSWER_AND_EXPLANATION.match(text):
            return paras[:i]
        if _RE_QUICK_ANSWER.match(text):
            return paras[:i]
        # "번호" 단독 줄 + "정답" 단독 줄 연속 = 정답 테이블 시작
        if _RE_ANSWER_HEADER.match(text) and i > 0:
            prev = paras[i - 1]['text'].strip()
            if _RE_ANSWER_SECTION.match(prev) or _RE_ANSWER_HEADER.match(prev):
                return paras[:i - 1]

    # 절단 없음 — 같은 눈(rules)으로 재검사해 침묵 통과를 가시화 (로그만, fail-open)
    if log is not None:
        try:
            from core.structure.rules import A_SECTION_HEADER as _A_HDR
            for p in paras:
                t = p['text'].strip()
                # "번호/정답" 단독 줄은 위 연속 조건 전용 — 단독 출현은 오탐이 많아 제외
                if t and _A_HDR.match(t) and not _RE_ANSWER_HEADER.match(t):
                    log(f"[경고] STEP1/2 정답부 헤더 후보 미절단: {t[:40]!r} — "
                        "구 감지 패턴이 못 읽는 표기입니다. 정답부가 문제지에 "
                        "인쇄될 수 있으니 원고를 확인하세요.")
                    break
        except Exception:
            pass
    return paras


def _filter_short_questions(paras, short_numbers, log=None):
    """
    짤지문 번호에 해당하는 지문 구간을 제거.
    [18], [19], [25]~[28], [43]~[45] 번호의 지문과 그 내용을 삭제.
    헤더 패턴(p2-no.18 등)도 동일하게 처리.

    배치 G (W37): log 콜백이 오면, 필터 후에도 짤지문 번호가 헤더 표기
    (no.N / [N])로 잔존하는 라인을 [경고]로 가시화 — 정규식이 못 읽은
    헤더 형식이면 짤지문이 조용히 인쇄되던 침묵 지점 (동작 무변경, 로그만).
    """
    if not short_numbers:
        return paras

    short_set = set(short_numbers)
    # 41~42, 43~45 같은 복합 번호도 처리
    combined_short = set()
    for n in short_numbers:
        combined_short.add(str(n))
    combined_short.add('41~42')  # 이건 일반지문이지만 일단 보존
    combined_short.add('43~45')

    result = []
    skip = False

    for p in paras:
        text = p['text'].strip()

        # 브래킷 패턴: [18]
        m = _RE_BRACKET_NUM.match(text)
        if m:
            num = int(m.group(1))
            if num in short_set:
                skip = True
                continue
            else:
                skip = False
                result.append(p)
                continue

        # 헤더 패턴: "1. p2-no.18", "25. p8-no.43~45", "1. p8-Example 1" 등
        m2 = _RE_HEADER_NUM.match(text)
        if m2:
            num_str = m2.group(1)
            if num_str is None:
                # 지문 번호가 캡처되지 않는 새 형식 헤더 (예: "1. L4-p.82") — 짤지문 매칭 대상 아님
                skip = False
                result.append(p)
                continue
            if '~' in num_str:
                first_num = int(num_str.split('~')[0])
            else:
                first_num = int(num_str)
            if first_num in short_set:
                skip = True
                continue
            else:
                skip = False
                result.append(p)
                continue

        if not skip:
            result.append(p)

    # 배치 G: 짤지문 번호가 헤더 표기로 잔존하면 [경고] (fail-open, 로그만).
    # 대상 표기는 확신 표기(no.N / [N])만 — 본문 속 우연한 숫자는 오탐이라 제외.
    if log is not None:
        try:
            leftover = set()
            for p in result:
                t = p['text'].strip()
                for m in re.finditer(
                        r'(?<![A-Za-z])no\.?\s*0*(\d+)|^\[\s*0*(\d+)\s*\]', t,
                        re.IGNORECASE | re.MULTILINE):
                    n_str = m.group(1) or m.group(2)
                    n = int(n_str)
                    if n in short_set:
                        leftover.add(n)
            if leftover:
                log(f"[경고] 짤지문 필터 미제거 의심: 번호 {sorted(leftover)} 가 "
                    "필터 후에도 헤더 표기(no.N/[N])로 잔존 — 헤더 형식이 "
                    "짤지문 매칭 정규식과 달라 해당 지문이 인쇄될 수 있습니다.")
        except Exception:
            pass

    return result


# A1 구분자 패턴
_RE_A1_SECTION = re.compile(
    r'^\s*\d+\.\s*어휘\s*\d+\s*단계', re.UNICODE
)


def _split_a1_sections(paras):
    """
    A1 원고를 섹션별로 분리.
    "1. 어휘1단계_Hard" → step1_a1
    "2. 어휘2단계_Hard" → step1_a1_2
    정답 섹션(_정답)은 제외.
    """
    sections = {}
    current_key = None
    current_paras = []

    for p in paras:
        text = p['text'].strip()
        if _RE_A1_SECTION.match(text):
            # 이전 섹션 저장
            if current_key and current_paras:
                sections[current_key] = current_paras

            # 정답 섹션 판별
            is_answer = '정답' in text
            if is_answer:
                current_key = None
                current_paras = []
                continue

            # 섹션 키 결정
            if '2단계' in text:
                current_key = "step1_a1_2"
            else:
                current_key = "step1_a1"
            current_paras = []
            continue

        if current_key:
            current_paras.append(p)

    # 마지막 섹션 저장
    if current_key and current_paras:
        sections[current_key] = current_paras

    # 빈 결과면 원본 그대로 step1_a1에 넣기
    if not sections:
        sections["step1_a1"] = paras

    return sections


# ── Step3 파싱 ───────────────────────────────────────────────────────────────

# 정답/해설 패턴 (Step3 hwp)
# "②: ⓑ making → make (...)" 또는 "③, ④" 뒤에 ": " + 해설
_RE_STEP3_ANSWER = re.compile(
    r'^\s*[①②③④⑤]\s*(?:,\s*[①②③④⑤]\s*)*:\s*.+'
)


_RE_STEP3_SINGLE_ANSWER = re.compile(
    r'^\s*[①②③④⑤](?:\s*,\s*[①②③④⑤])*\s*$'
)

# Step3 유형 태그: "[유형 1] 내용파악 & 대의파악" / "[유형 3] 빈칸추론" 등 섹션 라벨
_RE_STEP3_TYPE_TAG = re.compile(r'^\s*\[\s*유형\s*\d+\s*\]')
# 유형 부제: "(심경, 분위기, 지칭, 주제, ...)" 같이 한글 콤마 나열만 있는 한 줄
# - 괄호로 둘러싸이고
# - 한글 + 콤마(,)로만 구성된 부제
_RE_STEP3_TYPE_SUBTAG = re.compile(
    r'^\s*\(\s*[가-힣\s,/&·]+\s*\)\s*$'
)


# W17 c16 — Step3 문제모음(pool/교과서 통합) 선두의 학원 표제/워터마크 블록.
#   'EBS 변형문제'/'영어독해 기본 02'(짧은 표제), cafe.naver URL,
#   '※ 본 자료는 무단도용 … 금합니다'(권리 경고)가 지문 스타일로 인쇄됐다.
#   v1 골든 0807ebd8/0e3844d2(APEX 리딩파워 pool)에도 동일 블록 잠복.
_RE_S3_JUNK_URL = re.compile(r'^(?:https?://\S+|www\.\S+)$')
_RE_S3_JUNK_RIGHTS = re.compile(
    r'무단\s*도용|무단\s*전재|무단\s*복제|무단\s*전송|저작권|출판권|전송권')
# 표제로 간주하지 않는 선두 라인 (문항/지시문 시작 신호)
_RE_S3_JUNK_PROTECT = re.compile(r'^(?:\d+\s*[.)]|서술형|논술형|Q\b|Q\.|※\s*다음)')
# 표제 블록 내 날짜-only 메모 ("17. 11. 23" — W18 c18 실증: 문항 번호
# 보호 규칙(^\d+.)이 날짜를 문항 번호로 오인 보호 → 본문 첫 단락 인쇄)
_RE_S3_JUNK_DATE = re.compile(
    r'^\d{2,4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?$')
# 꼬리 정답 섹션 표제: "<표제> 정답" (물음표 없음 + 공백/대시 뒤 '정답' 종결)
_RE_S3_ANSWER_TITLE = re.compile(r'^[^?？]{0,40}[\s\-–—]정답$')

# 배치 B (W33): Step3 정답부 섹션 헤더를 core/structure/rules.A_SECTION_HEADER
# 와 공유 — 단락종류 판정기(taxonomy 09)와 같은 눈. 구 리터럴 튜플
# ('정답 및 해설','빠른 정답 찾기','정답지','정답')은 '정답과 해설'/'정답 ·
# 해설'/'[정답 및 해설]'을 못 잘라 정답표가 문제지에 인쇄됐다 (감사 실증 #3
# — 판정기는 아는 표기, 서로 다른 눈 재현). 구 튜플이 공유 패턴의 부분집합
# 임은 tests/test_answer_header_batch_b.py가 가드. rules 로드 실패 시 구
# 튜플 등가 정규식 폴백 (fail-open — 조판을 막지 않는다).
try:
    from core.structure.rules import A_SECTION_HEADER as _RE_S3_SECTION_HEADER
except Exception:                                            # noqa: BLE001
    _RE_S3_SECTION_HEADER = re.compile(
        r'^\s*(?:정답\s*및\s*해설|빠른\s*정답\s*찾기|정답지|정답)\s*$')


def _strip_step3_leading_junk(paras):
    """Step3 문제모음 선두의 표제/워터마크 블록 제거 (W17 c16).

    문서 맨 앞에서부터 스캔하며 URL 단독 라인·권리 경고 라인·짧은 표제
    라인(30자 이하, 물음표 없음)만 제거한다. 빈 단락은 보존(골든 안정),
    표제도 경고도 아닌 첫 실질 라인(발문/마커/본문)에서 즉시 중단 —
    문서 중간에는 절대 손대지 않는다. 40자+ 문서 타이틀(수능특강
    '2027년 … 더변형문제')은 표제 기준 밖이라 보존된다 (kind 계층 관행).
    """
    out = []
    i = 0
    n = len(paras)
    while i < n:
        p = paras[i]
        text = p['text'].strip()
        if not text:
            out.append(p)          # 빈 단락 보존
            i += 1
            continue
        if _RE_S3_JUNK_URL.match(text) or _RE_S3_JUNK_RIGHTS.search(text):
            i += 1
            continue
        if _RE_S3_JUNK_DATE.match(text):
            i += 1                 # 표제 블록 내 날짜 메모 (W18 c18)
            continue
        if (len(text) <= 30 and '?' not in text and '？' not in text
                and not _RE_S3_JUNK_PROTECT.match(text)
                and not (text.startswith('[') and text.endswith(']'))):
            i += 1                 # 짧은 표제 라인 ('EBS 변형문제' 등)
            continue
        break                      # 첫 실질 라인 — 이후 무접촉
    out.extend(paras[i:])
    return out


def _strip_step3_trailing_junk(paras):
    """Step3 문제모음 꼬리의 권리/워터마크 라인 제거 (W17 c11 실증 —
    '본 콘텐츠는 … 라이센스를 획득하여 이그잼포유에서 제작 … 저작권은 …
    무단 전재 …'가 실전문제 마지막 단락으로 인쇄됨, G17 검출).

    문서 맨 끝에서부터 스캔하며 URL 단독 라인·권리 문구 라인만 제거한다.
    빈 단락은 보존, 첫 실질 라인에서 즉시 중단 — 문서 중간 무접촉."""
    drop = set()
    i = len(paras) - 1
    while i >= 0:
        text = paras[i]['text'].strip()
        if not text:
            i -= 1
            continue
        if _RE_S3_JUNK_URL.match(text) or _RE_S3_JUNK_RIGHTS.search(text):
            drop.add(i)
            i -= 1
            continue
        break
    if not drop:
        return paras
    return [p for k, p in enumerate(paras) if k not in drop]


def _strip_step3_type_tags(paras):
    """Step3 원고에서 유형 섹션 태그/부제를 모두 제거.

    예) "[유형 1] 내용파악 & 대의파악", "(심경, 분위기, 지칭, 주제, 제목, 주장, 요지, 내용일치)",
         "[유형 4] 지문 흐름파악", "(순서배열, 문장넣기, 무관한문장)" 등.
    이 줄들은 문제와 무관한 분류 라벨이므로 발문/지문/선지/조건/보기 구조에 끼어
    잘못된 단락스타일이 매핑되지 않도록 사전에 제거한다.
    """
    out = []
    for p in paras:
        text = p['text'].strip()
        if _RE_STEP3_TYPE_TAG.match(text):
            continue
        if _RE_STEP3_TYPE_SUBTAG.match(text):
            # 단, 짧고 (괄호 안에 한글 토큰 2개 이상 콤마로 나열) 구조여야만 부제로 간주
            inner = text.strip()[1:-1]
            tokens = [t.strip() for t in inner.replace('/', ',').split(',') if t.strip()]
            # 한글 토큰이 두 개 이상이면 부제로 판단 (단일 어휘 주석은 보존)
            kor_tokens = [t for t in tokens if any('가' <= c <= '힣' for c in t)]
            if len(kor_tokens) >= 2:
                continue
        out.append(p)
    return out


def _strip_step3_answers(paras):
    """
    Step3 hwp에서 정답+해설 줄 제거.
    제거 대상:
    1. "정답 및 해설" / "빠른 정답 찾기" / "정답지" 단독 헤더 → 그 이후 모든 단락 cut
       (MIXED 원고는 후반부에 정답해설 섹션이 통째로 붙어 있음)
    2. "②: ⓑ making → make (해설...)" — 원문자+콜론+해설
    3. ": (B) broken → alive..." — 콜론으로 시작하는 해설 이어짐
    4. "⑤" 또는 "②, ③" — 단독 정답번호 (문제 바로 다음 줄)
    """
    # 섹션 절단: 정답해설 섹션 헤더 발견 시 그 위치부터 끝까지 drop
    # '정답' 단독 줄도 섹션 헤더로 인식 (2026-07 W11 — 부교재 워크북 Step3가
    # "정답" 한 줄 뒤에 정답표를 붙이는 형식. 문항 사이 정답 표기는 원문자
    # 단독/콜론 형식이라 아래 개별 제거 룰이 담당 — 골든 코퍼스에 '정답'
    # 단독 본문 줄 없음 확인).
    # W17: "<표제> 정답" 꼬리 표제도 섹션 헤더 — "2025년 06월 모의고사
    # <고2> 정답"/"★ 객관식 빠른 정답"(c04 잠복, 정답표+제작진 크레딧
    # 블록이 통째로 인쇄됐음) / "EBS 올림포스 - … 정답"(c16). 발문은
    # '?'로 끝나 매치되지 않고, "■ 정답: …" 문항별 정답은 콜론 뒤 내용이
    # 있어 매치되지 않음 (골든 전수 sweep: c04 2건 외 매치 없음 확인).
    # 배치 B (W33): 리터럴 튜플 → rules.A_SECTION_HEADER 공유 (모듈 상단
    # _RE_S3_SECTION_HEADER 주석 참조 — 판정기와 같은 눈, 실증 #3 해소).
    cut_idx = None
    for i, p in enumerate(paras):
        text = p['text'].strip()
        if _RE_S3_SECTION_HEADER.match(text) or _RE_S3_ANSWER_TITLE.match(text):
            cut_idx = i
            break
    if cut_idx is not None:
        paras = paras[:cut_idx]

    result = []
    for p in paras:
        text = p['text'].strip()
        if _RE_STEP3_ANSWER.match(text):
            continue
        if text.startswith(': ') and len(text) > 10:
            continue
        if _RE_STEP3_SINGLE_ANSWER.match(text):
            continue
        result.append(p)
    return result


# Step3 5지선다 발문 패턴: '... 것은?' / '... 것을 두 개 고르시오' / '... 옳은 것은?' 등
_RE_STEP3_CHOICE_QUESTION = re.compile(
    r'^\s*\d+\.\s.*?(?:것은\??|것을\s+두\s*개\s*고르시오\.?|옳은\s*것은\??|적절한\s*곳은\??)\s*$'
)
# 5지선다에서 제외할 발문 (빈칸 채우기/영작 서술형/어법 객관식)
_RE_STEP3_NON_CHOICE = re.compile(
    r'요약하고자\s*한다|영어로\s*완성|찾아\s*쓰시오|바르게\s*고치시오|어형\s*변화'
)
# 선지가 지문 inline에 ①②③④⑤로 박혀 있는 발문 (자동 prepend skip)
# - "다음 글의 밑줄 친 부분 중 ... 어법상/문맥상 ... 적절하지 않은 것은?"
# - "다음 글의 흐름과 관계 없는 문장은?"
# - "글의 흐름상 주어진 문장이 들어가기에 가장 적절한 곳은?" (문장삽입: 주어진 문장은 보기, 선지 ①②③④⑤는 지문 inline 위치 마커)
# - "윗글의 (A), (B)에 들어갈 ... 바른 것은?" ((A)/(B) 매칭형: 선지가 표 형태 2개씩 짝)
# 이런 발문은 파서가 자동으로 ①~⑤를 추가하면 지문/보기/표 헤더 첫 글자에 ① 중복 발생
_RE_STEP3_INLINE_CHOICE = re.compile(
    r'밑줄\s*친\s*부분\s*중|흐름과\s*관계\s*없는\s*문장|어법상\s*틀린\s*것'
    r'|주어진\s*(?:문장|글)|들어갈\s*위치'
    r'|\(\s*A\s*\).{0,5}\(\s*B\s*\)'
)
# 단순 번호 발문 감지 (다음 발문 만나면 중단)
_RE_STEP3_QUESTION_LIKE = re.compile(r'^\s*\d+\.\s')
_CIRCLED_DIGITS = ['①', '②', '③', '④', '⑤']

# ── 단열 5지선다 발문 구조 판정 (겉모습/앞번호에 의존하지 않음) ──────────────
# 5지선다 어미: "…것은?" / "…것을 (모두) 고르시오" / "…곳은?" / "…옳은 것은?"
# 앞 문항번호("1.") 유무, 꼬리표("- 1차") 유무와 무관 — 원고 표기가 바뀌어도 견딘다.
_RE_STEP3_CHOICE_END = re.compile(
    r'(?:것은|옳은\s*것은|것을\s*(?:모두\s*)?고르(?:시오|십시오)?|곳은)'
    r'\s*[\?\.]?\s*(?:[-–—]\s*\d+\s*차\s*)?$'
)
# 단열 ①~⑤ prepend 대상이 '아닌' 5지선다(선지 구조가 다름):
# 순서배열(①이 (A)-(C)-(B) 식 순열), (A)(B) 매칭표, 괄호/네모 안 어법선택.
_RE_STEP3_NOT_SINGLE_COL = re.compile(
    r'순서로\s*(?:가장\s*)?적절|이어질\s*글의\s*순서|괄호\s*안|네모\s*안'
    r'|\(\s*A\s*\).{0,5}\(\s*B\s*\)'
)
# 다음 발문 경계(번호 유무 무관): "1." 형태 또는 한글 지시문+지시어미 라인.
# 선지 prepend 루프가 다음 문제로 넘어가 ④⑤를 잘못 붙이는 것을 막는다.
_RE_STEP3_PROMPT_BOUNDARY = re.compile(
    r'^\s*\d+\.\s'
    r'|[가-힣].*(?:것은|곳은|고르시오|고르십시오|쓰시오|완성하시오|고치시오|'
    r'문장은|배열하)\s*[\?\.]?\s*(?:[-–—]\s*\d+\s*차\s*)?$'
)
# 변형문제 출처 마커 단독 단락 ("[202506H2_25도표_변형]") — 선지 prepend
# 경계. 발문 직후에 마커가 오는 문제모음(발문→마커→지문 순)에서 마커가
# 선지 1번으로 오인돼 원고에 없는 ①이 붙는 것을 막는다 (W15 c04 실증).
_RE_STEP3_SRC_MARKER = re.compile(r'^\[[^\[\]]{2,}변형\]$')


def _add_step3_choice_numbers(paras):
    """Step3 hwp의 5지선다 자동번호(①②③④⑤) 텍스트화.

    hwp 파일은 5지선다 선지에 ①②③④⑤를 AutoNumbering 컨트롤로 표시하므로
    텍스트만 추출하면 번호가 누락된다 (어법 객관식처럼 본문에 직접 타이핑한 경우는
    이미 텍스트에 ①이 들어와 있어 영향 없음).

    구조 인식 방식:
    1. "밑줄 친 부분 중" / "흐름과 관계 없는 문장" 류 발문 → 선지가 지문 inline에
       ①~⑤로 박혀 있음 → 자동 prepend skip (지문 첫 글자에 ① 중복 방지)
    2. 그 외 5지선다 발문 → 발문 직후 시퀀스: 지문(영문 통문장) + 선지×5
       → 첫 영문 단락(지문)은 skip, 그 다음 5개 단락에 ①②③④⑤ prepend
    3. 빈칸 요약/영작 서술형/어법 고치기 등은 제외.
    """
    i = 0
    n = len(paras)
    while i < n:
        text = (paras[i].get('text', '') or '').strip()
        # 단열 5지선다 발문 판정 — 겉모습(앞번호)이 아니라 구조/의미로:
        #   ① 한글 지시문이면서 5지선다 어미("것은?"/"것을 고르시오"/"곳은?")로 끝나고
        #   ② 제외형(서술/요약/순서/(A)(B)표/괄호·네모 어법/지문 inline)이 아닐 때만.
        if not (re.search(r'[가-힣]', text) and _RE_STEP3_CHOICE_END.search(text)):
            i += 1
            continue
        if _RE_STEP3_NON_CHOICE.search(text):
            i += 1
            continue
        # 선지가 지문 inline에 박힌 발문 → 자동 prepend skip
        if _RE_STEP3_INLINE_CHOICE.search(text):
            i += 1
            continue
        # 순서/(A)(B)표/괄호·네모 어법 = 단열 선지가 아님 → prepend skip
        if _RE_STEP3_NOT_SINGLE_COL.search(text):
            i += 1
            continue

        # 발문 직후 후보 단락에 이미 ①~⑤로 시작하는 단락이 있으면 prepend skip.
        # (안내문/도표/광고 류 — 영문 본문 여러 단락 + 한국어 선지가 ①로 시작.
        # 기존 "첫 영문 단락만 skip" 로직은 영문 본문 2번째부터를 선지로 오인해 본문에
        # ②③④⑤를 잘못 prepend함. 이미 텍스트에 ①가 있으면 hwp AutoNumbering 누락
        # 케이스가 아니므로 자동 prepend 불필요.)
        already_has_circled = False
        for j_peek in range(i + 1, min(n, i + 30)):
            t_peek = (paras[j_peek].get('text', '') or '').strip()
            if not t_peek:
                continue
            if _RE_STEP3_PROMPT_BOUNDARY.search(t_peek):
                break
            if re.match(r'^\[(?:[Gg]ateway|\d+)\]$', t_peek):
                break
            if _RE_STEP3_SRC_MARKER.match(t_peek):
                continue    # 출처 마커는 선지 후보가 아님 — 건너뛰고 계속
            if t_peek.startswith('※'):
                break
            if t_peek[0] in _CIRCLED_DIGITS:
                already_has_circled = True
                break
        if already_has_circled:
            i += 1
            continue

        # 발문 위에 묶음 마커(※/[Gateway]/[숫자])가 있으면 지문은 마커 아래에
        # 이미 존재 → 발문 직후는 바로 선지. 다른 발문은 건너뛰며 마커까지 거슬러 올라감.
        # 마커가 없으면 (예: 동아박 MIXED) 발문 직후 첫 영문 단락이 자기 지문.
        passage_above = False
        for k in range(i - 1, -1, -1):
            t_k = (paras[k].get('text', '') or '').strip()
            if not t_k:
                continue
            if t_k.startswith('※') or re.match(r'^\[(?:[Gg]ateway|\d+)\]$', t_k):
                passage_above = True
                break

        # 발문 직후 첫 영문 단락(지문) skip 후 5개 단락에 ①②③④⑤ prepend
        # (지문은 영문 알파벳 시작 + 한글 미포함 단락. 단락 1개만 skip)
        # passage_above=True면 지문은 발문 위에 이미 있으므로 skip 단계 우회.
        saw_passage = passage_above
        added = 0
        j = i + 1
        while j < n and added < 5:
            t_j = (paras[j].get('text', '') or '').strip()
            if not t_j:
                j += 1
                continue
            # 이미 ①~⑤로 시작하면 중단 (어법 객관식이거나 정상 입력된 경우)
            if t_j[0] in _CIRCLED_DIGITS:
                break
            # 다음 발문(번호 유무 무관), 본문 마커([Gateway]/[숫자]), 본문 시작 ※ 만나면 중단
            if _RE_STEP3_PROMPT_BOUNDARY.search(t_j):
                break
            if re.match(r'^\[(?:[Gg]ateway|\d+)\]$', t_j):
                break
            if _RE_STEP3_SRC_MARKER.match(t_j):
                j += 1
                continue    # 출처 마커 — 선지 아님 (①이 붙으면 원고 오염, W15)
            if t_j.startswith('※'):
                break
            # 첫 영문 단락 = 지문 → 1회 skip
            if not saw_passage and re.match(r'^[A-Za-z]', t_j) and not re.search(r'[가-힣]', t_j):
                saw_passage = True
                j += 1
                continue
            # 지문 inline 번호 통단락(도표/불일치류 — 선지가 지문 문장에
            # ①~⑤로 박힘)에는 prepend 금지: ①을 중복 부여해 기형 번호가
            # 된다 (W19 c20 실증 — ※ 다중 문항 아이템은 passage_above가
            # True라 위 지문 skip을 우회해, 발문 뒤 재인쇄 지문이 선지
            # 후보로 잡혔음). 정상 선지는 짧고 본문에 원문자가 없다.
            if len(t_j) > 120 and any(ch in _CIRCLED_DIGITS for ch in t_j):
                break
            mark = _CIRCLED_DIGITS[added]
            paras[j]['text'] = mark + paras[j]['text']
            runs = paras[j].get('runs')
            if isinstance(runs, list):
                runs.insert(0, {'t': mark, 'ul': False})
            added += 1
            j += 1
        i = j if added > 0 else i + 1
    return paras


# 표형 5지선다 번호 셀 — 단독 ①~⑤ 한 글자 단락 (정답 "②, ③"는 제외)
_RE_STEP3_LONE_CIRCLED = re.compile(r'^\s*([①②③④⑤])\s*$')


def _merge_step3_split_choice_numbers(paras):
    """표형 5지선다에서 번호 칸(①~⑤)이 선지 텍스트와 분리 추출된 경우 병합.

    "개수는?" / "모두 고르면?" 류 발문의 선지는 원고에서 2열 표(①|1개, ②|2개 …)로
    작성된다. hwpx 표 평탄화 시 번호 셀과 텍스트 셀이 각각 별도 단락(①, 1개, ②, 2개 …)
    으로 추출되고, 직후 _strip_step3_answers가 단독 ①~⑤를 정답 번호로 오인해 제거 →
    선지에서 번호 글리프가 사라진다. 추출 직후(= _strip_step3_answers 이전)에 번호 셀을
    다음 선지 텍스트에 prepend("① 1개")해 번호 유실을 막는다.

    엄격 매칭: ①②③④⑤가 순서대로, 각각 단독 단락이고 사이에 비어있지 않은 선지가 1개씩
    올 때만 병합. (단독 정답 "①"나 "②, ③"는 시퀀스를 못 이루므로 영향 없음.)
    """
    if not paras:
        return paras

    def _txt(p):
        return (p.get('text', '') if isinstance(p, dict) else str(p)).strip()

    n = len(paras)
    to_merge = {}   # choice_idx -> 원문자
    drop = set()    # 번호 셀 idx
    i = 0
    while i < n:
        m0 = _RE_STEP3_LONE_CIRCLED.match(_txt(paras[i]))
        if not (m0 and m0.group(1) == '①'):
            i += 1
            continue
        seq = []        # (num_idx, choice_idx)
        cur = i
        ok = True
        for d in _CIRCLED_DIGITS:
            md = _RE_STEP3_LONE_CIRCLED.match(_txt(paras[cur])) if cur < n else None
            if not (md and md.group(1) == d):
                ok = False
                break
            j = cur + 1
            while j < n and not _txt(paras[j]):
                j += 1
            if j >= n or _RE_STEP3_LONE_CIRCLED.match(_txt(paras[j])):
                ok = False
                break
            seq.append((cur, j))
            cur = j + 1
        if ok and len(seq) == 5:
            for (num_idx, choice_idx), d in zip(seq, _CIRCLED_DIGITS):
                drop.add(num_idx)
                to_merge[choice_idx] = d
            i = cur
        else:
            i += 1

    if not drop:
        return paras

    out = []
    for idx, p in enumerate(paras):
        if idx in drop:
            continue
        if idx in to_merge:
            d = to_merge[idx]
            if isinstance(p, dict):
                merged = dict(p)
                merged['text'] = d + ' ' + p.get('text', '')
                runs = p.get('runs')
                if isinstance(runs, list):
                    merged['runs'] = [{'t': d + ' ', 'ul': False}] + list(runs)
                out.append(merged)
            else:
                out.append(d + ' ' + str(p))
        else:
            out.append(p)
    return out


# Step3 책 헤더 / 묶음 마커 — 출력에서 제거
# - "2027년 수능특강 영어    더변형문제    27강 컴퓨터,인터넷" 류 책 제목 라인 (수능특강 워크북)
# - "- 2606 변형문제 -" / "[2606 변형문제]" 변형문제 부제 + 바로 위 책제목 (모의고사 등 변형문제 원고)
# - "[Gateway]" 묶음 마커 (passage_above 판정에 사용된 후 출력에서 제거)
_RE_STEP3_BOOK_HEADER = re.compile(r'^\d{4}\s*년?\s*수능특강')
_RE_STEP3_GROUP_MARKER = re.compile(r'^\[\s*Gateway\s*\]$', re.I)
# 변형문제 부제 — 책 이름이 아니라 "변형문제"를 앵커로 잡는다(책 이름 무관 일반화).
# 예) "- 2606 변형문제 -", "[2606 변형문제]", "변형 문제"
_RE_STEP3_VARIANT_SUBTITLE = re.compile(
    r'^[\[\(\-–—\s]*\d{0,4}\s*변형\s*문제\s*[\]\)\-–—\s]*$'
)


def _strip_step3_book_markers(paras):
    """책 헤더 + [Gateway] 묶음 마커 단락 제거.

    제거 대상:
    1. "2027년 수능특강 ..." 책 헤더 (수능특강 워크북 — 기존 동작 유지)
    2. "- NNNN 변형문제 -" 부제 + 그 바로 위 책제목 줄(파일 맨 위 헤더).
       부제를 앵커로 잡으므로 책 이름이 무엇이든("ENGLISH for High N" 등) 무관하게 제거된다.
       수능특강 원고에는 이 부제가 없으므로 영향 없음.
    3. "[Gateway]" 묶음 마커 (_add_step3_choice_numbers의 passage_above 판정에 쓰인 후 제거)

    원고 구조 예:
        ENGLISH for High 1        ← 책제목 (부제 앵커로 함께 제거)
        - 2606 변형문제 -          ← 변형문제 부제
        다음 글의 주제로 ... 것은?   ← 발문 (여기부터 본문)
    """
    drop = set()
    # 변형문제 부제를 앵커로: 부제 줄 + 바로 위 '책제목' 줄을 제거
    for i, p in enumerate(paras):
        text = (p.get('text', '') or '').strip()
        if not _RE_STEP3_VARIANT_SUBTITLE.match(text):
            continue
        drop.add(i)
        for j in range(i - 1, -1, -1):
            tj = (paras[j].get('text', '') or '').strip()
            if not tj:
                continue
            # 바로 위 비빈 단락이 '책제목'(발문/지문/선지/보기 아님 + 짧은 제목)이면 함께 제거
            if (not _RE_STEP3_CHOICE_END.search(tj)
                    and tj[0] not in _CIRCLED_DIGITS
                    and not tj.startswith('※')
                    and not tj.startswith('<')
                    and len(tj) <= 40):
                drop.add(j)
            break

    out = []
    for i, p in enumerate(paras):
        if i in drop:
            continue
        text = (p.get('text', '') or '').strip()
        if _RE_STEP3_GROUP_MARKER.match(text):
            continue
        if _RE_STEP3_BOOK_HEADER.match(text):
            continue
        out.append(p)
    return out


# (A)/(B) 매칭형 발문 직후의 표 평탄 단락을 5쌍으로 합치기
_RE_STEP3_AB_QUESTION = re.compile(r'\(\s*A\s*\).{0,5}\(\s*B\s*\)')
_RE_STEP3_AB_HEADER = re.compile(r'^\(\s*[AB]\s*\)$')

# 순서배열 발문 — "주어진 글 다음에 이어질 글의 순서로 적절한 것은?"
_RE_STEP3_ORDER_QUESTION = re.compile(r'순서로\s*(?:가장\s*)?적절한|이어질\s*글의\s*순서')


def _fix_step3_order_label_position(paras):
    """순서배열 본문에서 (A) 라벨이 도입부 박스 위로 잘못 추출된 케이스 수정.

    HWP 박스 추출이 박스 구조를 인식 못하면서 첫 (A) 라벨이 시각 순서와 다르게
    도입부 박스 *위*로 추출되는 케이스:

    추출:
        ※ 다음 글을 읽고 물음에 답하시오.
        (A)               ← 잘못된 위치 (도입부 박스 위)
        <도입부 박스>
        <(A) 박스>        ← 라벨 누락된 채 등장
        (B)
        <(B) 박스>
        (C)
        <(C) 박스>
        7. ... 순서로 적절한 것은?

    수정:
        ※ 다음 글을 읽고 물음에 답하시오.
        <도입부 박스>     ← 라벨 없음 (도입부)
        (A)               ← (A) 박스 위로 이동
        <(A) 박스>
        (B)
        ...

    조건 (모두 만족 시에만):
    - (A) 라벨 직전 비빈 단락이 ※/[Gateway]/번호발문
    - 30단락 이내에 (B)/(C) 라벨 + 영문 박스 본문 4개 이상 + 순서배열 발문 모두 존재
    """
    if not paras:
        return paras
    out = list(paras)
    i = 0
    while i < len(out):
        text = (out[i].get('text') or '').strip()
        if text != '(A)':
            i += 1
            continue
        # 직전 비빈 단락이 발문/Gateway/※ 인지
        prev_marker = False
        for jj in range(i - 1, -1, -1):
            pt = (out[jj].get('text') or '').strip()
            if not pt:
                continue
            if pt.startswith('※') or pt == '[Gateway]' or _RE_STEP3_QUESTION_LIKE.match(pt):
                prev_marker = True
            break
        if not prev_marker:
            i += 1
            continue
        # 후속 30단락 이내: (B)/(C) 라벨 + 영문 본문 4개 이상 + 순서배열 발문
        scan_end = min(len(out), i + 30)
        b_idx = c_idx = first_body_idx = -1
        body_count = 0
        order_q_found = False
        for k in range(i + 1, scan_end):
            tk = (out[k].get('text') or '').strip()
            if not tk:
                continue
            if tk == '(B)' and b_idx < 0:
                b_idx = k
                continue
            if tk == '(C)' and c_idx < 0:
                c_idx = k
                continue
            if _RE_STEP3_ORDER_QUESTION.search(tk):
                order_q_found = True
                break
            if re.match(r'^[A-Za-z]', tk) and not re.search(r'[가-힣]', tk):
                body_count += 1
                if first_body_idx < 0:
                    first_body_idx = k
        if not (order_q_found and b_idx > 0 and c_idx > 0 and body_count >= 4 and first_body_idx > 0):
            i += 1
            continue
        # (A) 라벨을 첫 박스 본문 *다음* 위치로 이동
        a_para = out.pop(i)
        # pop으로 first_body_idx는 1 감소 → 새 인덱스 (first_body_idx - 1)이 도입부 박스 위치
        # 그 *다음*에 (A) 삽입 → insert(first_body_idx)
        out.insert(first_body_idx, a_para)
        i = first_body_idx + 1
    return out


def _merge_step3_ab_pairs(paras):
    """(A)/(B) 매칭 발문 직후의 표 평탄 단락을 5쌍으로 합쳐 ①~⑤ 부여.

    hwp/hwpx 표는 셀 단위로 평탄화되어 추출됨:
        입력:
            10. 윗글의 ... (A), (B)에 들어갈 연결사로 바른 것은?
            (A)                ← 컬럼 헤더 (제거)
            (B)                ← 컬럼 헤더 (제거)
            However            ← 1쌍 (A)값
            As a result        ← 1쌍 (B)값
            However
            Otherwise
            ...
            Therefore
            What is worse
        출력:
            10. ... 바른 것은?
            ①However\\tAs a result
            ②However\\tOtherwise
            ③For example\\tLikewise
            ④For example\\tNevertheless
            ⑤Therefore\\tWhat is worse

    영문 단락이 정확히 10개 모이지 않으면(추출 누락 등) 안전하게 원본 그대로 반환.
    """
    out = []
    i = 0
    n = len(paras)
    while i < n:
        text = (paras[i].get('text', '') or '').strip()
        # 5지선다 발문("…것은?")이고 (A)/(B) 매칭 패턴 포함 + NON_CHOICE(쓰시오/요약/영작/어법) 아닐 때만 처리.
        # 빈칸 채우기 서술형 발문에는 적용하면 안 됨 (그 발문에도 (A)/(B) 라벨이 등장하지만
        # 표 매칭이 아니라 본문 안 빈칸 표시이므로).
        is_match = (_RE_STEP3_CHOICE_QUESTION.match(text)
                    and _RE_STEP3_AB_QUESTION.search(text)
                    and not _RE_STEP3_NON_CHOICE.search(text))
        if not is_match:
            out.append(paras[i])
            i += 1
            continue
        # (A)/(B) 매칭 5지선다 발문 — 발문 단락은 그대로 유지
        out.append(paras[i])
        i += 1
        # 후속 단락 수집: 빈 줄/(A)·(B) 헤더는 따로 보관, 영문 셀만 cells에 모음
        cells = []
        passed = []  # 매칭 실패 시 복원용 (빈 줄 + (A)/(B) 헤더)
        while i < n and len(cells) < 10:
            tj = (paras[i].get('text', '') or '').strip()
            if not tj:
                passed.append(paras[i])
                i += 1
                continue
            if _RE_STEP3_AB_HEADER.match(tj):
                # (A) 또는 (B) 단독 헤더 — 5쌍 매칭 성공 시 제거, 실패 시 복원
                passed.append(paras[i])
                i += 1
                continue
            if _RE_STEP3_QUESTION_LIKE.match(tj):
                break  # 다음 발문 만나면 중단
            cells.append(paras[i])
            i += 1
        if len(cells) < 10:
            # 매칭 실패 — (A)/(B) 헤더 + 빈 줄 + cells 모두 복원
            out.extend(passed)
            out.extend(cells)
            continue
        # (A)(B) 헤더 행 복원 — 선지 위에 컬럼 라벨 표시 (버리지 않음)
        out.append({"text": "(A)\t(B)",
                    "runs": [{"t": "(A)", "ul": False},
                             {"t": "\t", "ul": False},
                             {"t": "(B)", "ul": False}]})
        # 5쌍 합치기: ① + (A)값 + 탭 + (B)값
        for k in range(5):
            t1 = (cells[2 * k].get('text') or '').rstrip()
            t2 = (cells[2 * k + 1].get('text') or '').rstrip()
            mark = _CIRCLED_DIGITS[k]
            merged_text = mark + t1 + '\t' + t2
            runs_a = cells[2 * k].get('runs') or [{"t": t1, "ul": False}]
            runs_b = cells[2 * k + 1].get('runs') or [{"t": t2, "ul": False}]
            new_runs = [{"t": mark, "ul": False}]
            new_runs.extend(runs_a)
            new_runs.append({"t": "\t", "ul": False})
            new_runs.extend(runs_b)
            out.append({"text": merged_text, "runs": new_runs})
    return out


# 컬럼 헤더 셀: "(A)" / "(B)" / "(C)"
_RE_STEP3_COL_HDR = re.compile(r'^\(\s*([ABC])\s*\)$')
# 표 구분자 셀: "……" / "⋯" / 가운뎃점·마침표만 있는 한 줄
_RE_STEP3_DOTS_CELL = re.compile(r'^[\s.·…⋯‧]+$')


def _merge_step3_column_table(paras):
    r"""(A)(B)[(C)] 컬럼표를 ①c1\tc2[\tc3] 선지로 병합 — 구조로만 판정(발문 안 봄).

    hwp 표가 셀 단위로 평탄화되고 _strip_step3_answers가 행 번호(①~⑤)를 제거하면,
    컬럼 헤더 + 값 셀만 세로로 줄줄이 남는다. 이를 5행으로 묶어 ①~⑤를 다시 부여한다.

      2열 요약 선택형:  (A)(B) + [A값 …… B값]×5   → ①A\tB      (…… 구분자 필수)
      3열 네모 어법:    (A)(B)(C) + [A B C]×5      → ①A\tB\tC    (구분자 없음)

    엄격 판정: 연속 컬럼 헤더 (A)(B)[(C)] 직후, (……·빈줄 제외) 짧은 값 셀이 정확히
    5×열수만큼 모일 때만 병합. 2열은 연결사형(_merge_step3_ab_pairs 담당)과 겹치지
    않도록 …… 구분자가 있을 때만. 조건 미달이면 원본 그대로 둔다(안전).
    """
    out = []
    i = 0
    n = len(paras)
    while i < n:
        t = (paras[i].get('text', '') or '').strip()
        m = _RE_STEP3_COL_HDR.match(t)
        if m and m.group(1) == 'A':
            # 연속 컬럼 헤더 (A)(B)[(C)] 수집 (사이 빈줄 허용)
            cols = 1
            j = i + 1
            while j < n:
                tj = (paras[j].get('text', '') or '').strip()
                if not tj:
                    j += 1
                    continue
                mj = _RE_STEP3_COL_HDR.match(tj)
                if mj and mj.group(1) == chr(ord('A') + cols):
                    cols += 1
                    j += 1
                    continue
                break
            if cols >= 2:
                # 값 셀 수집 (……·빈줄 skip, 원문자·발문경계·긴 단락 만나면 중단)
                cells = []
                seps = 0
                k = j
                need = 5 * cols
                while k < n and len(cells) < need:
                    tk = (paras[k].get('text', '') or '').strip()
                    if not tk:
                        k += 1
                        continue
                    if _RE_STEP3_DOTS_CELL.match(tk):
                        seps += 1
                        k += 1
                        continue
                    if tk[0] in _CIRCLED_DIGITS or _RE_STEP3_PROMPT_BOUNDARY.search(tk):
                        break
                    if len(tk) > 60:  # 긴 단락(지문) → 표 셀 아님
                        break
                    cells.append(paras[k])
                    k += 1
                ok = ((cols == 3 and len(cells) == 15)
                      or (cols == 2 and len(cells) == 10 and seps >= 1))
                if ok:
                    # (A)(B)[(C)] 헤더 행 복원 — 선지 위에 컬럼 라벨 표시 (버리지 않음).
                    # JSX는 "(A)\t..." 단락을 선지 위 헤더로 렌더한다.
                    hdr_labels = ['(' + chr(ord('A') + ci) + ')' for ci in range(cols)]
                    hdr_runs = []
                    for ci, lab in enumerate(hdr_labels):
                        if ci > 0:
                            hdr_runs.append({"t": "\t", "ul": False})
                        hdr_runs.append({"t": lab, "ul": False})
                    out.append({"text": '\t'.join(hdr_labels), "runs": hdr_runs})
                    for r in range(5):
                        row = cells[r * cols:(r + 1) * cols]
                        parts = [(c.get('text') or '').strip() for c in row]
                        mark = _CIRCLED_DIGITS[r]
                        new_runs = [{"t": mark, "ul": False}]
                        for ci, c in enumerate(row):
                            if ci > 0:
                                new_runs.append({"t": "\t", "ul": False})
                            new_runs.extend(c.get('runs') or [{"t": parts[ci], "ul": False}])
                        out.append({"text": mark + '\t'.join(parts), "runs": new_runs})
                    i = k
                    continue
        out.append(paras[i])
        i += 1
    return out


_STEP3_ANS_SECTION_PATTERNS = [
    re.compile(r'^\s*\[\s*정답\s*\]\s*$'),
    re.compile(r'^\s*【\s*정답\s*】\s*$'),
    re.compile(r'^\s*<\s*정답\s*>\s*$'),
    re.compile(r'^\s*정답\s*및\s*해설\s*$'),
]


def _strip_step3_answers_section(paras):
    """[정답] 류 헤더 이후 모든 paragraphs 제거."""
    if not paras:
        return paras
    cut_idx = None
    for i, p in enumerate(paras):
        t = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        if any(pat.match(t) for pat in _STEP3_ANS_SECTION_PATTERNS):
            cut_idx = i
            break
    if cut_idx is not None:
        return paras[:cut_idx]
    return paras


_STEP3_INSERT_PATTERN = re.compile(
    r'주어진\s*(?:문장|글)|들어갈\s*위치|이어질\s*순서|다음에\s*이어질'
)


def _split_step3_insert_passage_inline(paras):
    """문장삽입 발문 다음 paragraph가 "주어진 문장" + 본문 한 paragraph로 합쳐 추출된
    경우 두 paragraph로 split. (docx 줄바꿈 누락 케이스 대응)."""
    out = []
    i = 0
    while i < len(paras):
        p = paras[i]
        text = p.get("text", "") if isinstance(p, dict) else str(p)
        out.append(p)
        if _STEP3_INSERT_PATTERN.search(text) and i + 1 < len(paras):
            next_p = paras[i + 1]
            next_text = (next_p.get("text", "") if isinstance(next_p, dict) else str(next_p))
            m = re.match(r'^\s*("[^"]+")\s*([A-Za-z(].*)$', next_text, re.DOTALL)
            if m:
                first_text = m.group(1)
                rest_text = m.group(2)
                out.append({"text": first_text, "runs": []})
                out.append({"text": rest_text, "runs": []})
                i += 2
                continue
        i += 1
    return out


def _augment_step1_c1_passage(paras):
    """step1_c1 본문 도입부 paragraph에 trailing 3+ space 추가.

    가로 워크북의 processStep1C1이 has3PlusGaps 매치 → S1_C1_BTM → 다음 (A)(B)(C)에
    S1_C1_BTM_T 적용 → 발문 자동 삽입. 마더텅처럼 (A)(B)(C) 분할 본문 케이스 대응.

    식별: 영문/한글없음 paragraph + 그 다음 비빈 paragraph가 "(A)" 시작이면 도입부.
    paragraph 안에 이미 3+ space 있으면 skip.
    """
    if not paras:
        return paras
    out = list(paras)
    for i in range(len(out) - 1):
        p = out[i]
        text = (p.get("text", "") if isinstance(p, dict) else str(p))
        stripped = text.strip()
        if not stripped:
            continue
        if not re.match(r'^[A-Za-z]', stripped):
            continue
        if re.search(r'[가-힣]', stripped):
            continue
        if re.match(r'^\([A-Z]\)', stripped):
            continue
        # 이미 3+ space 있으면 skip (정규 모의고사 형식)
        if re.search(r' {3,}', text) or '\t' in text:
            continue
        # 다음 비빈 paragraph가 (A)인지
        for j in range(i + 1, len(out)):
            next_text = (out[j].get("text", "") if isinstance(out[j], dict) else str(out[j])).strip()
            if not next_text:
                continue
            if re.match(r'^\(A\)', next_text):
                new_p = dict(p)
                new_p["text"] = text + "   "
                if isinstance(new_p.get("runs"), list) and new_p["runs"]:
                    new_p["runs"] = list(new_p["runs"]) + [{"t": "   ", "ul": False}]
                out[i] = new_p
            break
    return out


# ── Step3 내용 보존 가드 ────────────────────────────────────────────────────
# 원고(raw)의 실질 영어 단어(4자+)가 출력에서 사라지면 경고한다. 이 클래스의 버그
# (구조 가정에서 비롯된 silent drop)를 — 알려진 2종뿐 아니라 앞으로 어떤 원고에서든 —
# 즉시 가시화하는 안전망. 비파괴(경고만, 파싱 흐름은 그대로).
_RE_STEP3_CONTENT_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
_RE_STEP3_ANS_HEADER_ANY = re.compile(
    r'^\s*(?:\[?\s*정답\s*\]?|【\s*정답\s*】|<\s*정답\s*>|정답\s*(?:및|과)?\s*해설'
    r'|빠른\s*정답\s*찾기|정답지|해설)\s*$'
)


def _step3_content_words(paras):
    """정답섹션/인라인 정답줄을 제외한 실질 영어 단어(4자+) 집합.

    _strip_step3_answers와 동일한 '정당한 제거' 기준을 적용해(정답섹션 헤더 이후 절단 +
    원문자+콜론 해설줄 + ': ' 해설줄 제외) 오탐을 막는다.
    """
    words = set()
    for p in paras:
        t = ((p.get('text', '') if isinstance(p, dict) else str(p)) or '').strip()
        if _RE_STEP3_ANS_HEADER_ANY.match(t):
            break  # 정답섹션 진입 → 이후는 정당 제거 영역
        # 정당하게 제거되는 줄(정답/해설·[Gateway]·책 헤더·유형 태그)은 보존 대상 아님 → 오탐 방지
        if (_RE_STEP3_ANSWER.match(t) or (t.startswith(': ') and len(t) > 10)
                or _RE_STEP3_GROUP_MARKER.match(t) or _RE_STEP3_BOOK_HEADER.match(t)
                or _RE_STEP3_TYPE_TAG.match(t)):
            continue
        for w in _RE_STEP3_CONTENT_WORD.findall(t):
            words.add(w.lower())
    return words


def _warn_step3_content_loss(raw_words, out_paras, label, log=None):
    """core.extract.guard.warn_content_loss로 위임 (Phase 1 승격 — 동작 동일)."""
    from core.extract.guard import warn_content_loss
    return warn_content_loss(raw_words, out_paras, f"Step3 {label}", log=log,
                             word_re=_RE_STEP3_CONTENT_WORD)


def _parse_step3_folder(step3_dir, grade, year, month, normal_questions,
                        short_questions, combined_questions, extract_underline=True,
                        step3_exclude_footnotes=True, log=None):
    """
    Step3 폴더 → 지문별 단락 목록.
    파일명: "고1 25년 9월 20번.hwp" 형태.
    반환: {"normal": [...], "short": [...]}
    각 항목: {"question_num": "20", "code": "250920", "paragraphs": [...]}

    step3_exclude_footnotes: True(기본) → level 1만 (정답/해설 footnote 완전 제거).
                             False → footnote_l3_set만 제외하고 level 3 (표 셀 본문 등) 유지.
                             수능특강 21강+처럼 표 셀에 본문이 있는 케이스에 False 사용.
    """
    if not os.path.isdir(step3_dir):
        return {"normal": [], "short": []}

    # 연도 2자리, 월 2자리
    yy = str(year)[-2:]
    mm = str(month).zfill(2)

    # 파일 목록 수집 (NFD→NFC 정규화 필수)
    files = {}
    for fname_raw in os.listdir(step3_dir):
        fname = _nfc(fname_raw)
        if not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
            continue
        # "고1 25년 9월 20번.hwp" 또는 "고1 25년 9월 41~42번.docx"
        # "번" 뒤 공백 허용 (예: "18번 .hwpx" 사용자 입력 오타 대응)
        m = re.search(r'(\d+(?:~\d+)?)번\s*\.(?:hwpx?|docx)', fname, re.I)
        if m:
            num_str = m.group(1)
            files[num_str] = os.path.join(step3_dir, fname_raw)  # 원본 경로 사용

    normal_items = []
    short_items = []

    # 복합 문제 번호 역매핑 (41 → "41~42")
    num_to_combined = {}
    for key, nums in combined_questions.items():
        file_key = key.replace('-', '~')
        for n in nums:
            num_to_combined[n] = file_key

    processed_file_keys = set()

    def _process_question(q_num, target_list):
        # 복합 문제 확인
        file_key = str(q_num)
        if q_num in num_to_combined:
            file_key = num_to_combined[q_num]

        if file_key in processed_file_keys:
            return
        processed_file_keys.add(file_key)

        fpath = files.get(file_key)
        if not fpath:
            # 단일 번호로도 시도
            fpath = files.get(str(q_num))

        if not fpath:
            return

        if fpath.lower().endswith('.docx'):
            paras = _docx_extract_paragraphs(fpath, extract_underline)
        else:
            paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                            exclude_footnotes=step3_exclude_footnotes)
        # 보존 가드 스냅샷 — 책 헤더(변형문제/수능특강)는 의도적 제거이므로
        # 스냅샷에서도 제외해 허위 "내용 손실" 경고를 막는다(헤더 외 손실은 그대로 감지).
        _raw_words = _step3_content_words(_strip_step3_book_markers(paras))
        # 표형 선지 번호 셀(①~⑤) 병합 — 반드시 _strip_step3_answers *이전*
        # (W40 결함 3: 순서배열 선지가 hwpx 2열 표(번호 셀|순열 셀)로
        # 작성된 원고에서, 아래 answers 제거가 단독 ①~⑤ 셀을 정답 번호로
        # 오인 제거해 "(A) － (C) － (B)" 행이 번호 없이 인쇄됨 —
        # 0a5da924 '고1 26년 6월 N번.hwpx' 실증. 교과서(textbook) 경로는
        # 이미 같은 순서로 호출한다 — 번호 매칭 경로만 빠져 있었다.)
        paras = _merge_step3_split_choice_numbers(paras)
        # Step3 정답/해설 줄 제거 (level 3 제외 후에도 level 1에 남은 정답 줄 처리)
        paras = _strip_step3_answers(paras)
        # Step3 유형 섹션 태그 제거 ("[유형 1] ...", "(심경, 분위기, ...)")
        paras = _strip_step3_type_tags(paras)
        # 5지선다 자동번호(①②③④⑤) 텍스트화 — hwp AutoNumbering 누락 보완
        paras = _add_step3_choice_numbers(paras)
        # 책 헤더("2027년 수능특강 ...") + [Gateway] 묶음 마커 제거
        # ※ _add_step3_choice_numbers의 passage_above 판정이 [Gateway]를 참조하므로
        #   반드시 그 호출 *후*에 실행해야 함
        paras = _strip_step3_book_markers(paras)
        # 순서배열 본문: (A) 라벨이 도입부 박스 위로 잘못 추출된 경우 정규화
        paras = _fix_step3_order_label_position(paras)
        # (A)/(B) 매칭 발문 → 표 5쌍 합치기 (①단어A\t단어B 형식)
        paras = _merge_step3_ab_pairs(paras)
        # 요약 선택형 (A)(B)…… 짝표 → ①A\tB (연결사형과 구분: 구분자 …… 유무)
        paras = _merge_step3_column_table(paras)
        _warn_step3_content_loss(_raw_words, paras, f"{file_key}번", log)
        code = f"{yy}{mm}{str(q_num).zfill(2)}"

        target_list.append({
            "question_num": file_key,
            "code": code,
            "paragraphs": paras,
        })

    for q in sorted(normal_questions):
        _process_question(q, normal_items)

    for q in sorted(short_questions):
        _process_question(q, short_items)

    # 마더텅 Step3: 파일명에 "N강 M번 YYMMQQ" 형태 (한영고1 마더텅 예전 기출)
    # — 정규 모의고사 normal/short 매칭에 안 잡혔지만 파일은 있을 때
    if not normal_items and not short_items:
        for fname_raw in sorted(os.listdir(step3_dir)):
            fname = _nfc(fname_raw)
            if not (fname.endswith('.hwp') or fname.endswith('.hwpx') or fname.endswith('.docx')):
                continue
            m = re.search(r'(\d+)\s*강\s*(\d+)(?:~(\d+))?\s*번(?:\s*(\d{6}))?', fname)
            if not m:
                continue
            q_num_lesson = m.group(2)
            q_end_lesson = m.group(3)
            file_code = m.group(4) or ""
            fpath = os.path.join(step3_dir, fname_raw)
            if fpath.lower().endswith('.docx'):
                paras = _docx_extract_paragraphs(fpath, extract_underline)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                                exclude_footnotes=step3_exclude_footnotes)
            _raw_words = _step3_content_words(_strip_step3_book_markers(paras))  # 보존 가드 스냅샷(헤더 제외)
            # 첫 단락 "N강 M번 YYMMQQ" 헤더 제거
            if paras:
                first_text = (paras[0].get("text", "") if isinstance(paras[0], dict) else str(paras[0])).strip()
                if re.match(r'^\d+\s*강\s*\d+(?:~\d+)?\s*번(?:\s*\d{6})?\s*(?:\([^)]*\))?$', first_text):
                    paras = paras[1:]
            # [정답] 이후 cut
            paras = _strip_step3_answers_section(paras)
            paras = _strip_step3_answers(paras)
            paras = _strip_step3_type_tags(paras)
            # 문장삽입 paragraph 합쳐짐 split
            paras = _split_step3_insert_passage_inline(paras)
            # docx 원고는 이미 ① 포함이므로 자동 prepend skip (가로/마더텅 공통)
            # paras = _add_step3_choice_numbers(paras)
            paras = _strip_step3_book_markers(paras)
            paras = _fix_step3_order_label_position(paras)
            paras = _merge_step3_ab_pairs(paras)
            paras = _merge_step3_column_table(paras)
            _warn_step3_content_loss(_raw_words, paras, f"{q_num_lesson}번", log)
            normal_items.append({
                "question_num": q_num_lesson,
                "code": file_code,
                "paragraphs": paras,
            })

    # 교과서 Step3: 번호 없는 hwpx 파일 처리 (normal/short가 모두 비어있을 때)
    if not normal_items and not short_items:
        # mockexam 번호 매칭을 실제로 수행한 경우(normal/short 지정)에만 "N번" 파일을
        # '위에서 이미 처리됨'으로 간주해 제외한다. 수능특강/EBS처럼 mockexam이 비어
        # 번호 매칭 자체를 하지 않은 경우에는 "...37번.hwpx" / "...41~42번.hwpx" 같은
        # 파일도 번호 루프에서 소비된 적이 없으므로 본문(textbook) 후보로 포함해야 한다.
        # (이 가드가 없으면 수능특강 Step3 모의고사형 분리파일이 전부 누락 → 빈 결과)
        _had_number_matching = bool(normal_questions or short_questions)
        # 후보 파일 수집
        candidate_files = []
        for fname_raw in sorted(os.listdir(step3_dir)):
            fname = _nfc(fname_raw)
            if not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
                continue
            if _had_number_matching and re.search(r'\d+번\.(?:hwpx?|docx)', fname, re.I):
                continue  # 번호 매칭으로 이미 처리 대상이었던 파일
            if fname_raw.startswith('.'):
                continue
            candidate_files.append(fname_raw)
        # MIXED 파일이 있으면 그것만 사용 (통합본 우선)
        mixed_files = [f for f in candidate_files if 'MIXED' in _nfc(f).upper()]
        if mixed_files:
            candidate_files = mixed_files

        textbook_paras = []
        for fname_raw in candidate_files:
            fpath = os.path.join(step3_dir, fname_raw)
            if fpath.lower().endswith('.docx'):
                paras = _docx_extract_paragraphs(fpath, extract_underline)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                                exclude_footnotes=step3_exclude_footnotes)
            # 선두/꼬리 표제·워터마크 제거 (W17 c16/c11 — 스냅샷 전에)
            paras = _strip_step3_leading_junk(paras)
            paras = _strip_step3_trailing_junk(paras)
            _raw_words = _step3_content_words(_strip_step3_book_markers(paras))  # 보존 가드 스냅샷(헤더 제외)
            # 표형 선지 번호 셀(①~⑤) 병합 — _strip_step3_answers가 단독 ①~⑤를 제거하기 전에 수행
            paras = _merge_step3_split_choice_numbers(paras)
            paras = _strip_step3_answers(paras)
            paras = _strip_step3_type_tags(paras)
            paras = _add_step3_choice_numbers(paras)
            paras = _strip_step3_book_markers(paras)
            paras = _fix_step3_order_label_position(paras)
            paras = _merge_step3_ab_pairs(paras)
            paras = _merge_step3_column_table(paras)
            _warn_step3_content_loss(_raw_words, paras, _nfc(fname_raw), log)
            textbook_paras.extend(paras)
        if textbook_paras:
            normal_items.append({
                "question_num": "textbook",
                "code": "",
                "paragraphs": textbook_paras,
            })

    # ── Phase 2 파일럿: 단락종류(kind)/발문유형(q_code) 주석 ──────────────────
    # additive 필드 — 기존 JSX는 모르는 키를 무시하므로 v1 경로 무영향.
    # 판정 실패 시 주석 없이 통과 (fail-open: 조판을 막지 않는다).
    _annotate_step3_kinds(normal_items + short_items, log)
    return {"normal": normal_items, "short": short_items}


def _annotate_step3_kinds(items, log=None):
    """core.structure 판정 결과를 단락 dict에 kind/q_code로 병기."""
    try:
        from core.structure import classify_paragraphs
    except Exception as e:
        _LOG.warning("[구조] core.structure 로드 실패 — 주석 생략: %s", e)
        return
    for item in items:
        try:
            results = classify_paragraphs(item.get("paragraphs", []))
        except Exception as e:
            msg = f"[구조] 단락종류 주석 실패({item.get('question_num')}): {e}"
            _LOG.warning(msg)
            if callable(log):
                log(msg)
            continue
        for r in results:
            para = r["para"]
            if isinstance(para, dict):
                para["kind"] = r["kind"]
                if r.get("q_code"):
                    para["q_code"] = r["q_code"]


def _find_manuscript_file(manuscript_dir, expected_filename, used_files=None):
    """config에 지정된 파일명이 없을 때 유사 파일을 찾는 fallback.

    매칭 전략 — 파일명의 구조(의미 토큰)를 기준으로 비교:
    1. 정규화: 영문/숫자/한글만 남기고 공백·괄호·특수문자 모두 제거, 소문자, NFC
       (예: 'Step2 A1 어법선택(객관식).docx' → 'step2a1어법선택객관식')
    2. 정확 매칭 우선
    3. 괄호 변형(양쪽 다 괄호 있고 base 동일)
    4. 한쪽 정규화 문자열이 다른 쪽의 subsequence면 부분 매칭으로 인정
       (예: '어법객관식'은 '어법선택객관식'의 subsequence → 매칭)
    5. 부분 매칭 후보들은 LCS(공통 부분 수열) 길이가 긴 것 우선
       (예: 기대 '빈칸어법정답지' → 후보 '빈칸어법정답'(LCS=9) > '빈칸어법'(LCS=7))
    6. 동일 LCS면 확장자 일치 우선
    7. 위 모두 실패 시 LCS 비율 (LCS_len / max(len_a, len_b)) ≥ 0.70 매칭
       (예: '어법 객관식 문제' ↔ '어법선택(객관식)' — '선택'/'문제'가 비공통이어도
        공통 토큰이 충분하면 매칭. 토씨가 빠지거나 바뀐 변형 대응.)

    used_files: 이미 다른 step_key에 매칭된 파일 경로 set. 후보에서 제외.
    """
    import unicodedata
    import re

    def _normalize(name):
        nfc = unicodedata.normalize("NFC", name)
        base = os.path.splitext(nfc)[0]
        cleaned = re.sub(r'[^A-Za-z0-9가-힣]', '', base).lower()
        return cleaned

    def _is_subseq(short, long_):
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

    def _lcs_len(a, b):
        if not a or not b:
            return 0
        la, lb = len(a), len(b)
        if la > lb:
            a, b = b, a
            la, lb = lb, la
        prev = [0] * (la + 1)
        for j in range(1, lb + 1):
            curr = [0] * (la + 1)
            bj = b[j-1]
            for i in range(1, la + 1):
                if a[i-1] == bj:
                    curr[i] = prev[i-1] + 1
                else:
                    curr[i] = max(prev[i], curr[i-1])
            prev = curr
        return prev[la]

    def _split_paren(name):
        """파일명을 (괄호 빼고 정규화된 base, 괄호 존재 여부)로 분리.
        예: 'Step2 A1 어법선택(객관식).docx' → ('step2a1어법선택', True)
        예: 'Step2 A1 어법선택.docx'         → ('step2a1어법선택', False)
        예: ' Step2 A1 어법선택(문법 기본 문제).docx' → ('step2a1어법선택', True)
        괄호 안 내용이 달라도 base가 같고 둘 다 괄호 있으면 변형으로 간주 가능.
        """
        nfc = unicodedata.normalize("NFC", name)
        stem = os.path.splitext(nfc)[0]
        has_paren = bool(re.search(r'\([^)]+\)', stem))
        stem_no_paren = re.sub(r'\([^)]*\)', '', stem)
        base = re.sub(r'[^A-Za-z0-9가-힣]', '', stem_no_paren).lower()
        return base, has_paren

    used_files = used_files or set()
    # macOS APFS/GDrive는 한글 파일명을 NFD로 저장. listdir 결과(NFD)와
    # used_files에 등록된 경로(NFC)를 비교하려면 양쪽 다 NFC로 통일.
    used_files_nfc = {unicodedata.normalize("NFC", p) for p in used_files}
    ext_expected = os.path.splitext(expected_filename)[1].lower()
    norm_expected = _normalize(expected_filename)
    exp_base, exp_has_paren = _split_paren(expected_filename)
    # 답안 토큰: 파일명이 '문제'본인지 '정답/해설/답안'본인지 구분하는 기준.
    _ANSWER_TOKENS = ('정답', '해설', '답안')
    exp_has_ans = any(t in norm_expected for t in _ANSWER_TOKENS)

    exact = []
    partial = []        # (file_path, lcs_score)
    paren_variant = []  # base 동일 + 양쪽 다 괄호 있는 변형 (괄호 안 내용은 달라도 OK)
    ratio_match = []    # (file_path, lcs_score, lcs_ratio) — subseq/paren 실패 시 fallback
    for f in os.listdir(manuscript_dir):
        fp = os.path.join(manuscript_dir, f)
        if not os.path.isfile(fp):
            continue
        if unicodedata.normalize("NFC", fp) in used_files_nfc:
            continue
        f_ext = os.path.splitext(f)[1].lower()
        if f_ext not in ('.docx', '.hwp', '.hwpx'):
            continue
        f_norm = _normalize(f)
        if not f_norm:
            continue
        if f_norm == norm_expected:
            exact.append(fp)
            continue
        cand_has_ans = any(t in f_norm for t in _ANSWER_TOKENS)
        # 답안 슬롯(기대명에 정답/해설/답안 포함)에는 답안 토큰이 없는 '문제' 파일을
        # 매칭 후보에서 제외. 예: 기대 '빈칸어법 정답지'에 대해 '빈칸어법'(문제)이
        # prefix subsequence라 partial 1순위로 잡혀 '빈칸어법 해설'(ratio 후보)을
        # 제치고 선택되던 버그 차단. 답안본 명명이 해설/정답지/답안 어느 쪽이든 답안본 우선.
        if exp_has_ans and not cand_has_ans:
            continue
        if _is_subseq(f_norm, norm_expected) or _is_subseq(norm_expected, f_norm):
            partial.append((fp, _lcs_len(f_norm, norm_expected)))
            continue
        # 괄호 변형 — base가 같고 둘 다 괄호 있을 때
        cand_base, cand_has_paren = _split_paren(f)
        if exp_has_paren and cand_has_paren and cand_base and cand_base == exp_base:
            paren_variant.append(fp)
            continue
        # LCS 비율 매칭 (위 모두 실패 시 fallback 후보로만 보관).
        # 정답지 휴리스틱(반대 방향): expected에 답안 토큰이 없는데 후보에는 있으면 제외.
        # (정답/해설 파일을 '문제' 슬롯에 잘못 매칭하는 것을 막음)
        if cand_has_ans and not exp_has_ans:
            continue
        lcs = _lcs_len(f_norm, norm_expected)
        denom = max(len(f_norm), len(norm_expected))
        ratio = lcs / denom if denom else 0.0
        if ratio >= 0.70:
            ratio_match.append((fp, lcs, ratio))

    if exact:
        for c in exact:
            if os.path.splitext(c)[1].lower() == ext_expected:
                return c
        return exact[0]
    # 괄호 변형(같은 base + 양쪽 괄호 있음)을 subsequence partial보다 우선.
    # 예: expected '...(객관식)' 있을 때 폴더에 '...(문법 기본 문제)'와 '...어법선택(괄호 없음)' 둘 다
    # 있으면, 괄호 변형인 '(문법 기본 문제)'가 정답이지 괄호 없는 본체가 아님.
    if paren_variant:
        for fp in paren_variant:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return fp
        return paren_variant[0]
    if partial:
        partial.sort(key=lambda x: (
            -x[1],
            0 if os.path.splitext(x[0])[1].lower() == ext_expected else 1,
        ))
        for fp, _ in partial:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return fp
        return partial[0][0]
    # LCS 비율 매칭 — 파일명에 토씨/공백/단어가 빠지거나 바뀌어도 의미 토큰이 충분히 겹치면 매칭.
    # 예: 기대 '어법선택(객관식)' ↔ 후보 '어법 객관식 문제' (공통 '어법객관식', 비율 86%)
    if ratio_match:
        ratio_match.sort(key=lambda x: (
            -x[2],
            -x[1],
            0 if os.path.splitext(x[0])[1].lower() == ext_expected else 1,
        ))
        for fp, _, _ in ratio_match:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return fp
        return ratio_match[0][0]
    return None


# ── 공개 API ────────────────────────────────────────────────────────────────

def parse_manuscript_folder(manuscript_dir, config, grade, year, month, log=None):
    """
    원고 폴더 → content.json dict.

    Args:
        manuscript_dir: 워크북 원고 폴더 경로
        config: config.json dict
        grade: 1 또는 2
        year: 25 (2자리) 또는 2025 (4자리)
        month: 10 등
        log: callable(str) 로그 콜백
    Returns:
        dict (content.json 구조)
    """
    if log is None:
        log = lambda s: None

    file_map = config['manuscript_file_map']
    needs_ul = set(config.get('needs_underline', []))
    mockexam = config.get('mockexam', {})

    result = {
        "grade": grade,
        "year": year,
        "month": month,
        "steps": {},
    }

    # 1차 pre-scan: file_map의 expected와 정확히 일치하는 파일을 used에 미리 등록.
    # fallback 매칭이 정확 매칭 대상 파일을 빼앗아가지 못하게 함.
    # 예: step2_a1=어법선택.docx가 폴더에 있고 step2_a1_btm=어법선택(객관식).docx의
    # fallback 후보로 어법선택.docx가 잡힐 수 있는데, 1차 pre-scan으로 차단.
    used_files = set()
    for _sk, _fn in file_map.items():
        _fp = os.path.join(manuscript_dir, _fn)
        if os.path.exists(_fp):
            used_files.add(_fp)

    # STEP1, STEP2 파싱
    for step_key, filename in file_map.items():
        fpath = os.path.join(manuscript_dir, filename)
        if not os.path.exists(fpath):
            # fallback: 파일명 공백/확장자 유연 매칭 (used_files 제외)
            found = _find_manuscript_file(manuscript_dir, filename, used_files)
            if found:
                fpath = found
                filename = os.path.basename(found)
                used_files.add(found)
            else:
                log(f"[파서] 파일 없음, 건너뜀: {filename}")
                continue

        extract_ul = step_key in needs_ul
        ext = os.path.splitext(filename)[1].lower()

        log(f"[파서] {step_key}: {filename}" + (" (밑줄 추출)" if extract_ul else ""))

        if ext == '.docx':
            paras = _docx_extract_paragraphs(fpath, extract_ul)
        elif ext in ('.hwp', '.hwpx'):
            paras = _hwp_extract_paragraphs(fpath, extract_ul)
        else:
            log(f"[파서] 미지원 형식: {ext}")
            continue

        # 옛 형식 워크북 헤더("9번"/"17년 11월 21번") → 표준 형식으로 정규화
        # 정상 원고에는 매치되지 않으므로 안전
        paras = _normalize_old_workbook_headers(paras)
        # 옛 헤더 변환 후 본문에 끼어있는 잡 헤더 제거
        paras = _strip_secondary_headers_after_old(paras)
        # 챕터 구분선 제거 (EBS 리딩파워 등). 다른 원고에는 매치되지 않음
        paras = _strip_chapter_dividers(paras)
        # 본 보기 다음 주어진 문장에 양쪽 공백 둘러싸기 (정상 원고 형태 매칭)
        paras = _wrap_hadan_with_spaces(paras)

        short_nums = mockexam.get('short_questions', [])

        # A1 특수 처리: "어휘1단계" / "어휘2단계" 로 분리
        if step_key == "step1_a1":
            sections = _split_a1_sections(paras)
            for sec_key, sec_paras in sections.items():
                sec_paras = _strip_manuscript_headers(sec_paras, log=log)
                sec_paras = _remove_answer_section(sec_paras, log=log)
                sec_paras = _filter_short_questions(sec_paras, short_nums, log=log)
                cleaned = _clean_empty_lines(sec_paras)
                q_nums = _extract_question_numbers(cleaned, sec_key)
                result["steps"][sec_key] = {
                    "filename": filename,
                    "question_numbers": q_nums,
                    "paragraph_count": len(cleaned),
                    "paragraphs": cleaned,
                }
                log(f"[파서] → {sec_key}: {len(cleaned)}개 단락, 지문 {len(q_nums)}개")
            continue

        # 정답 구간 제거
        paras = _remove_answer_section(paras, log=log)

        # 헤더 제거
        paras = _strip_manuscript_headers(paras, log=log)

        # 짤지문 필터링 (STEP1~2만, STEP3는 별도 처리)
        paras = _filter_short_questions(paras, short_nums, log=log)

        # [L1-9] 마커 제거 (교과서 원고)
        paras = _strip_lesson_markers(paras)

        # 빈 단락 필터
        cleaned = _clean_empty_lines(paras)

        # step1_c1: 마더텅 형태(본문 도입부 + (A)(B)(C) 분할 본문)에서 도입부 paragraph에
        # trailing 3+ space 추가 → processStep1C1이 BTM/BTM_T 분류 + 발문 자동 삽입.
        # ※ 수능특강/EBS는 JSX가 도입부=본문 / (A)(B)(C)=일반 선지로 처리하도록 설계돼 있어
        #   (run.jsx: "EBS처럼 헤더 다음 본문이 BTM이면 (A)(B)(C)도 일반 선지여야 하므로 건너뜀"),
        #   이 augment가 적용되면 모의고사처럼 발문이 하단에 잘못 삽입된다. 따라서 config의
        #   step1_c1_augment_passage=false인 엔진(수능특강 등)에서는 적용하지 않는다. 기본 True.
        if step_key == "step1_c1" and config.get("step1_c1_augment_passage", True):
            cleaned = _augment_step1_c1_passage(cleaned)

        # 지문번호 추출
        q_nums = _extract_question_numbers(cleaned, step_key)

        result["steps"][step_key] = {
            "filename": filename,
            "question_numbers": q_nums,
            "paragraph_count": len(cleaned),
            "paragraphs": cleaned,
        }
        log(f"[파서] → {len(cleaned)}개 단락, 지문 {len(q_nums)}개")

    # STEP3 파싱
    step3_dir = os.path.join(manuscript_dir, "Step3")
    if os.path.isdir(step3_dir):
        log(f"[파서] Step3 폴더 파싱 중...")
        step3_data = _parse_step3_folder(
            step3_dir, grade, year, month,
            mockexam.get('normal_questions', []),
            mockexam.get('short_questions', []),
            mockexam.get('combined_questions', {}),
            step3_exclude_footnotes=config.get('step3_exclude_footnotes', True),
            log=log,
        )
        result["steps"]["step3"] = {
            "normal": step3_data["normal"],
            "short": step3_data["short"],
            "normal_count": len(step3_data["normal"]),
            "short_count": len(step3_data["short"]),
        }
        log(f"[파서] → Step3 일반: {len(step3_data['normal'])}개, "
            f"짤지문: {len(step3_data['short'])}개")
    else:
        log(f"[파서] Step3 폴더 없음: {step3_dir}")

    return result


def main():
    """CLI: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>"""
    if len(sys.argv) < 6:
        print("사용법: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>")
        sys.exit(1)

    output_path = sys.argv[1]
    manuscript_dir = sys.argv[2]
    grade = int(sys.argv[3])
    year = int(sys.argv[4])
    month = int(sys.argv[5])

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    def log(msg):
        print(msg)

    data = parse_manuscript_folder(manuscript_dir, config, grade, year, month, log)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_paras = sum(
        s.get('paragraph_count', 0) for k, s in data['steps'].items()
        if k != 'step3'
    )
    print(f"[파서] 완료: {len(data['steps'])}개 STEP, {total_paras}개 단락 → {output_path}")


if __name__ == '__main__':
    main()
