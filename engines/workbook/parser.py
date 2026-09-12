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

import hashlib
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
from core.extract.pdf import (  # PDF Step3 원고 (사용자 지시 2026-09-12)
    _pdf_extract_paragraphs,
    PdfTextUnreadable,
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
# '번' 꼬리 허용 — 회차마다 원고 세대가 달라 [36] / [36번] 이 섞인다
# (실측 2026-08-20: 고1 21년 9월 36-37번 워크북. '번'이 붙으면 마커가
#  통째로 미인식돼 그 파일의 지문이 0개로 잡혔다).
_RE_BRACKET_NUM = re.compile(r'^\s*\[(\d+)\s*번?\]\s*$')      # [20], [36번]
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
    r'L\d+(?:\s*[-–—]\s*(?:p\.?\s*\d+|본문\s*\d+))?'
    r'|p\.?\s*\d+'
    r'|U\d+'
    r')'
)
# W73 (능률(민) SL1 실증): 페이지 마커 앞에 붙는 **강 이름 접두**.
#   "1. Special Lesson 1-p. 52 본문 1"  → 접두 "Special Lesson 1-"
# 기존 교재는 이 자리를 축약 코드로 쓰지만(L1-p.17) 원전마다 풀네임을 쓰기도
# 한다. 접두가 미인식이면 헤더 전체가 미인식 → 유닛 미분할 + 헤더 원문 인쇄 +
# 지문번호 라벨이 헤더 전문("Special Lesson 1-p. 52 본문 1")이 되어 프레임을
# 넘치고 줄임말 규칙이 전 지문을 "Special" 하나로 뭉갠다(실증).
# 영문 단어 1~3개 + 선택 숫자 + 하이픈으로만 한정하고, 뒤에 반드시 페이지
# 마커가 와야 하며 줄 끝($)까지 헤더 꼴이어야 하므로 본문 문장은 안 걸린다.
_RE_LESSON_PREFIX = (
    r'(?:[A-Za-z][A-Za-z]{0,14}(?:\s+[A-Za-z][A-Za-z]{0,14}){0,2}'
    r'\s*\d{0,3}\s*[-–—]\s*)?'
)
# W71: 헤더 끝에 붙는 문항 유형 표기 — "3. p80-no.01  [문장배열]" (수능특강
# 라이트 12강 최종본 원고). 이게 없으면 헤더 자체가 인식되지 않아, 지문번호가
# 없는 Gateway 헤더("1. p78-Gateway  [문장배열]")를 첫 본문 마커로 못 잡고
# _strip_manuscript_headers 가 그 앞 블록을 통째로 잘라낸다(실측: 151단락
# 원고가 105단락으로, gateway 2문항 침묵 유실). 인식 대상을 C1 유형 표기로만
# 한정해 다른 원고의 헤더 판정은 건드리지 않는다.
_RE_TYPE_SUFFIX = (r'(?:\s*\[\s*(?:문단\s*배열|순서\s*배열|문장\s*배열|'
                   r'문장\s*삽입)\s*\])?')
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
    + _RE_LESSON_PREFIX                                       # 강 이름 접두 "Special Lesson 1-" (선택, W73)
    + _RE_PAGE_MARKER +                                       # 페이지/레슨 마커
    r'\s*[-–—\.]?\s*'                                        # 구분자 (선택)
    r'(?:no\.\s*|Example\s+|Practice\s+|[A-Za-z]+\.?\s*)?'   # 라벨 (선택)
    r'(\d+(?:\s*~\s*\d+)?)?'                                 # 지문 번호 (캡처, 선택)
    r'(?:\s*[가-힣][가-힣0-9A-Za-z\s]{0,30})?'               # 한글 라벨 꼬리 "과 추가지문"/"수능 Analysis" 등 (선택)
    r'(?:\s*\([^\)]*\))?'                                    # 트레일링 부가정보 "(정답 1개)" 등 (선택)
    + _RE_TYPE_SUFFIX +                                       # 트레일링 유형 표기 "[문장배열]" (선택)
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
# W68 (수특라이트 11강 실증 — 사용자 지적 "영작배열도 기출 로그 노출"):
# 정답부 제목이 "11강. 흐름에 무관한 문장 찾기  —  정답"처럼 **유형명이
# 앞에 붙은** 형태로 와서 위 열거 패턴이 전부 빗나갔다(→ 정답부가 문제지에
# 그대로 인쇄 + 지문이 2배). 형태를 더 열거하는 대신 의미로 본다:
# '한글이 있는 짧은 단독 줄이 정답/해설로 끝나면 그 아래는 정답부'.
# 발문(…시오/…것은?)·본문 문장은 종결형/길이로 배제한다.
_RE_ANSWER_TITLE_TAIL = re.compile(
    r'^(?=.*[가-힣])(?!.*(?:시오|세요|것은|하시오)\s*[.?]?\s*$)'
    r'.{0,40}?[\s\-–—:·,]*(?:정답|해설)\s*(?:지|표)?\s*$', re.UNICODE
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
        if _RE_ANSWER_TITLE_TAIL.match(text):
            if log:
                log(f"[파서] 정답부 절단: {text[:40]!r} 이후 제거")
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


from core.structure.rules import A_SECTION_HEADER as _A_SECTION_HEADER

# A1 지문 블록 라벨 — 선행 순번으로 시작하는 짧은 줄
_RE_A1_BLOCK_LABEL = re.compile(r'^\d{1,3}\s*[.)]\s+\S')


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

    def _stash():
        # W74 (올포기출 13강 실증 — 사용자 지적 "어휘선택 2지문 빼고 전부
        # 누락"): 예전 코드는 `sections[key] = paras` 대입이라 같은 키가
        # 다시 나오면 앞 섹션이 통째로 사라졌다. 이 원고는 지문마다
        # "1. 어휘1단계 / 2. 어휘2단계"를 번갈아 적어(지문 17개 × 2단계)
        # 마지막 지문 하나만 남았다. 단계별로 **누적**한다 — 단계 블록이
        # 한 번씩만 나오는 기존 원고는 결과가 같다 (append == 대입).
        if current_key and current_paras:
            sections.setdefault(current_key, []).extend(current_paras)

    for p in paras:
        text = p['text'].strip()
        # W74: 정답부 표제("정답 및 해설" / "빠른 정답 찾기") 단독 줄도
        # 섹션 종료다. 누적 저장으로 바꾸기 전에는 뒤따르는 "N. 어휘M단계
        # _정답" 마커가 앞 섹션을 통째로 덮어써서 이 줄이 저절로 사라졌다.
        if _A_SECTION_HEADER.match(text):
            _stash()
            current_key = None
            current_paras = []
            continue
        if _RE_A1_SECTION.match(text):
            # 이전 섹션 저장
            _stash()

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
    _stash()

    # 빈 결과면 원본 그대로 step1_a1에 넣기
    if not sections:
        sections["step1_a1"] = paras

    # W74: 누적 저장의 부작용 차단 — 한 원고에 같은 지문 블록이 두 벌
    # 들어 있는 재-export 본(코퍼스 dce9c922 실측: 지문 3~17이 두 번)은
    # 예전엔 마지막 대입이 앞을 덮어써 저절로 하나만 남았다. 지문 라벨
    # ("N. …" 선행 순번 줄)로 블록을 갈라 **내용까지 똑같은 블록의
    # 재등장만** 버린다 (라벨이 2개 미만이면 판정 근거가 없으니 무변경.
    # 라벨만 같고 내용이 다르면 개정본이므로 둘 다 남긴다).
    for key in list(sections):
        items = sections[key]
        heads = [i for i, q in enumerate(items)
                 if _RE_A1_BLOCK_LABEL.match((q.get('text') or '').strip())]
        if len(heads) < 2:
            continue
        seen = set()
        keep = []
        bounds = heads + [len(items)]
        if heads[0] > 0:
            keep.extend(items[:heads[0]])
        for b in range(len(bounds) - 1):
            blk = tuple((items[q].get('text') or '').strip()
                        for q in range(bounds[b], bounds[b + 1]))
            key_blk = tuple(t for t in blk if t)
            if key_blk in seen:
                continue        # 내용까지 같은 블록만 중복으로 본다
            seen.add(key_blk)
            keep.extend(items[bounds[b]:bounds[b + 1]])
        if len(keep) != len(items):
            sections[key] = keep

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


# ── W80: 정답부 절단은 '뒤에 문항이 더 없을 때'만 ──────────────────────────
# 2026-08-28 사용자 지적(수특라이트영독 10강): "스텝3 문제가 71번까지밖에
# 안 들어갔는데" — 원고는 80문항인데 71번까지만 조판됐다. 원인은 문항 71의
# 영작 배열에 딸린 인라인 `<해설>` 한 줄이 정답부 섹션 헤더로 매치돼, 거기서
# **문서 끝까지 115줄(문항 72~80)** 이 통째로 잘린 것. 절단은 원고의 11%를
# 침묵으로 버리는 동작인데 '헤더 한 줄'만 보고 실행됐다.
#
# 정답부는 정의상 **문항이 끝난 뒤**에 온다. 헤더 뒤에 문항 번호 시퀀스가
# 이어지면(직전까지의 최대 번호 + 1이 뒤에 나타나면) 그 헤더는 섹션 시작이
# 아니라 문항 안의 인라인 표기다. 정답표의 "1. ①  2. ②"는 번호가 1부터
# 다시 시작하므로 이 검사에 걸리지 않는다.
_RE_S3_QNUM_LINE = re.compile(r'^\s*(\d{1,3})\s*[.)]\s')


def _s3_qnums(paras, lo=None, hi=None):
    out = []
    for p in paras[lo:hi]:
        t = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        m = _RE_S3_QNUM_LINE.match(t)
        if m:
            out.append(int(m.group(1)))
    return out


def _s3_answer_cut_idx(paras, is_header):
    """정답부 절단 위치 — 뒤에 문항이 이어지는 헤더는 건너뛴다 (W80).

    is_header(text) -> bool. 없으면 None (절단 안 함)."""
    for i, p in enumerate(paras):
        t = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        if not is_header(t):
            continue
        before = _s3_qnums(paras, None, i)
        if before:
            nxt = max(before) + 1
            if nxt in _s3_qnums(paras, i + 1, None):
                continue      # 문항이 더 있다 — 섹션 시작이 아니다
        return i
    return None


# ── W77: 원고 그림 중 '지문에 딸린 그림'만 남긴다 ──────────────────────────
# 원고에는 도표/실용문 삽화(=조판해야 할 내용)와 편집용 장식(난이도 ★★★,
# 교재 로고/표지)이 섞여 있다. 형식(크기·파일명)이 아니라 **구조**로 가른다:
#   내용 그림은 언제나 지문 옆에 있다 — 바로 앞이나 뒤의 실질 단락이
#   영어 산문(=지문)이다. 장식은 선지와 발문 사이, 표제 블록 안에 있다.
# (실증: 스텝3 실전문제.hwp 의 ★★★ 20개는 전부 '선지 → 그림 → 한글 발문'
#  자리, 도표 그림은 전부 '라벨/발문 → 그림 → 영어 지문' 자리였다.)
_RE_S3_IMG_ENGWORD = re.compile(r'[A-Za-z]{2,}')
_S3_IMG_QKINDS = ("Q", "Q-INTRO")


def _s3_img_is_prose(text):
    return len(_RE_S3_IMG_ENGWORD.findall(text or '')) >= 6


def _s3_img_kinds(paras):
    """이웃 단락 종류(kind) — 구조 판정기(core.structure)와 같은 눈을 쓴다."""
    try:
        from core.structure import classify_paragraphs
        return [r["kind"] for r in classify_paragraphs(paras)]
    except Exception:                                          # noqa: BLE001
        return [""] * len(paras)       # fail-open: 아래 산문 판정만으로 진행


def _strip_step3_decorative_images(paras, label='', log=None):
    """지문에 딸리지 않은 그림(장식) 제거. 남긴/버린 수를 로그로 남긴다."""
    idx = [i for i, p in enumerate(paras)
           if isinstance(p, dict) and p.get('image')]
    if not idx:
        return paras
    kinds = _s3_img_kinds(paras)
    n = len(paras)

    def _real(rng):
        for k in rng:
            if (paras[k].get('text') or '').strip():
                return k
        return None

    stat = {}          # 그림 파일 경로 -> [총 개수, 발문 앞 개수, 지문 인접 개수]
    per = {}
    for i in idx:
        a = _real(range(i - 1, -1, -1))
        b = _real(range(i + 1, n))
        ka = kinds[a] if (a is not None and a < len(kinds)) else ""
        kb = kinds[b] if (b is not None and b < len(kinds)) else ""
        ta = (paras[a].get('text') or '') if a is not None else ''
        tb = (paras[b].get('text') or '') if b is not None else ''
        q_before = kb in _S3_IMG_QKINDS
        near_passage = (ka == "P" or kb == "P"
                        or _s3_img_is_prose(ta) or _s3_img_is_prose(tb))
        key = paras[i]['image'].get('path') or str(i)
        st = stat.setdefault(key, [0, 0, 0])
        st[0] += 1
        st[1] += 1 if q_before else 0
        st[2] += 1 if near_passage else 0
        per[i] = (key, near_passage)

    # 같은 그림이 여러 번 나오면 **그림 단위**로 판정한다: 대다수가 발문
    # 바로 앞자리면(난이도 ★★★처럼 문항마다 찍히는 표식) 전부 장식이다.
    # 지문에 한 번도 안 붙는 그림(표지/로고)도 장식.
    deco = set()
    for key, (tot, q, near) in stat.items():
        if near == 0 or q * 2 > tot:
            deco.add(key)

    out, dropped, kept = [], 0, 0
    for i, p in enumerate(paras):
        if i in per:
            key, near_passage = per[i]
            if key in deco or not near_passage:
                dropped += 1
                continue
            kept += 1
        out.append(p)
    if callable(log) and (kept or dropped):
        log("[파서] step3 원고 그림 %s: 지문 그림 %d개 배치 / 장식 %d개 제외"
            % (label, kept, dropped))
    return out


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
        if p.get('image'):
            # 선두 표제 블록의 그림 = 교재 로고/표지 (첫 실질 라인 앞에만
            # 있다). 본문 도표는 발문/지문 사이라 이 루프가 닿기 전에
            # break 된다 — 문서 중간 무접촉 원칙 그대로.
            i += 1
            continue
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
    cut_idx = _s3_answer_cut_idx(
        paras,
        lambda t: bool(_RE_S3_SECTION_HEADER.match(t)
                       or _RE_S3_ANSWER_TITLE.match(t)))
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
# 단독 대괄호 라벨 줄 — 선지 prepend 경계. 발문 직후에 라벨이 오는
# 문제모음(발문→라벨→지문 순)에서 라벨이 선지 1번으로 오인돼 원고에 없는
# ①이 붙는 것을 막는다 (W15 c04 실증).
#
# W77 (사용자 지적 2026-08-27 — 올림포스 영어독해 6강 부교재):
#   구 규칙은 "…변형]" 으로 **끝나는 표기만** 인정하는 화이트리스트였다.
#   같은 자리에 출처를 "[Unit 06 - Analysis]" 로 적는 원고가 오자 그대로
#   뚫려 "①[Unit 06 - Analysis]" 가 선지 스타일로 인쇄됐다.
#   구조로 판정한다 — **줄 전체가 대괄호 하나인 단락은 선지가 아니다**
#   (선지는 내용이지 라벨이 아니다). 어떤 새 라벨 표기가 와도 여기서 막힌다.
#   (이 자리를 통과한 라벨은 플랜의 W66 인덱스 라벨 규칙이 제거한다.)
_RE_STEP3_SRC_MARKER = re.compile(r'^\[[^\[\]]{2,}\]$')


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


# ── W75: 원고 문항 번호 줄 제거 ─────────────────────────────────────────────
# 사용자 지적 2026-08-26 "스텝3에 문제 번호인지 뭔지 쓸데없는 거 들어갔어".
# 수특라이트 13강 통합변형문제 원고는 문항마다 번호를 **단독 줄**로 적는다:
#     01
#     23번 주제  다음 글의 주제로 가장 적절한 것은?
#     <지문> …
# 조판은 문제 번호를 자기 스타일(자동 번호)로 매기므로 이 줄은 중복이다.
# 게다가 _add_step3_choice_numbers 가 "※ ①~⑤ 중 …" 발문 다음의 이 숫자
# 줄을 선지로 오인해 ①을 붙여 "①07" 같은 기형까지 만들었다.
# 형식(점 유무·자릿수)이 아니라 **구조**로 판정한다: 단독 숫자 줄이고 바로
# 다음 유의 단락이 한글 지시문인 쌍이, 문서 순으로 1씩 증가하는 계열을
# 이룰 때만(5개 이상) 그 계열을 지운다. 낱개 숫자 줄(표 셀·정답)은 계열을
# 못 이루므로 영향 없다.
_RE_STEP3_ITEM_NUM = re.compile(r'^\s*(\d{1,3})\s*$')


# ── W83: 원고 워크시트 잔재 + 줄바꿈 쪼개짐 정규화 ─────────────────────────
# 부교재 Step3 원고(수능만만 09강 실증)는 편집용 워크시트라 완제품이 자기
# 스타일로 다시 만드는 부속물이 섞여 있고, PDF/HWP 변환 흔적으로 한 문단이
# 줄 단위로 쪼개져 있다. 형식(문구 화이트리스트)이 아니라 구조로 가른다.
_RE_S3_SENT_END = re.compile(r'[.!?:;”"’\')\]】」』]\s*$')
# 새 구조 단위의 머리 — 여기서 시작하는 줄은 앞 줄의 이어짐이 아니다
_RE_S3_UNIT_HEAD = re.compile(
    r'^\s*(?:\d{1,3}\s*[.)]'          # 문항 번호
    r'|[①-⑳⓪ⓐ-ⓩⒶ-Ⓩ㉠-㉭]'          # 선지/보기 마커
    r'|\(\s*[A-Ea-e]\s*\)'            # (A)(B)(C) 라벨
    r'|[※◆▶●■□▷▸☞]|<|\[|【'
    r'|[•·‧∙◦▪▫‣⁃\uf000-\uf0ff]'      # 조건 상자 글머리표(윙딩 포함)
    r'|[-–—]\s'                        # 대시 글머리 조건 항목
    r'|[━─═＝]{2,}'                     # 구분선 표제 ('━━ [ 정답 ] ━━')
    r'|[*＊→⇒]'                        # 어휘 주석·화살표 줄
    r'|다음\s*글을\s*읽고\s*물음에)')    # 묶음 도입문
_RE_S3_RIGHTS_NOTICE = re.compile(
    r'(?:저작권|무단\s*(?:배포|전재|복제|전송|도용)|재판매)')
# 발문 각주 참조 — 문항 번호와 같은 수가 발문 끝에 '155)' 로 남는다
_RE_S3_ITEM_HEAD = re.compile(r'^\s*(\d{1,3})\s*\.\s')
_RE_S3_QINTRO = re.compile(r'다음\s*글을\s*읽고\s*물음에')
_RE_S3_ANY_MARKER = re.compile(r'[①-⑳⓪ⓐ-ⓩⒶ-Ⓩ㉠-㉭]')
_RE_S3_HANGUL_ANY = re.compile(r'[가-힣]')
# 한글 줄이 끊긴 자리는 낱말 사이일 수도, 낱말 **한가운데**일 수도 있다
# (원고에 공백 흔적이 남지 않아 텍스트만으로는 알 수 없다). 뒷줄이 조사로
# 시작하거나('것'+'은?'), 앞줄이 낱말이 아닌 한 음절로 끝나면('변'+'형하여')
# 붙여 쓰고, 그밖에는 띄어 쓴다('위'+'글에서').
# 문장삽입 발문 — 바로 다음 단락이 '주어진 문장' 상자다
_RE_S3_INSERT_PROMPT = re.compile(r'주어진\s*문장이\s*들어가기')
_RE_S3_JOSA_HEAD = re.compile(r'^[은는이가을를의에로와과도만][\s?.,]|^[은는이가을를의에로와과도만]$')
# ── W90: 생성 원고(LLM 변형문제)의 문항 머리 부속물 ────────────────────────
# 사용자 지적 2026-09-05 (수능만만 09~10강 어법Practice 40제): 완제품이
# 자기 디자인으로 매기는 문항 번호("01") 위에 원고의 '문항 1' 줄과 출처·
# 난이도 막대가 그대로 인쇄되고, 문항 사이 괘선("──…")이 단 폭을 넘어
# 석 줄로 흘렀다. 셋 다 워크시트 편집용 부속물이라 지면에 올 것이 아니다.
_RE_S3_GEN_ITEM_LABEL = re.compile(r'^\s*문\s*(?:항|제)\s*0*\d{1,3}\s*$')
# 괘선 한 줄 — 괘선/대시/등호만으로 이루어진 단독 줄. 밑줄(_)은 답 기입란
# 이므로 제외한다 (본문의 빈칸 '____'을 지우면 안 된다).
_RE_S3_RULE_LINE = re.compile(
    r'^[\s\u2500-\u257f\u2010-\u2015\u2212=~·•∙]{3,}$')
# 머리 안내문의 합쇼체 종결 — 교재 본문은 이 종결형을 쓰지 않는다
# (해석은 '…다.', 발문은 '…것은?/…쓰시오.').
_RE_S3_POLITE_END = re.compile(r'(?:습니다|합니다|입니다|됩니다)\s*[.!]?\s*$')
_S3_ONE_SYLLABLE_WORDS = set(
    "위 글 것 수 말 등 및 안 밖 앞 뒤 옆 내 각 두 세 네 그 이 저 나 너 때 곳 "
    "점 줄 중 후 전 년 월 일 시 분 초 개 명 장 쪽 면 문 답 반 별 술 물 불".split())


def _s3_join_glue(prev_text, cur_text):
    """두 조각을 이을 때 사이에 넣을 것 — 공백 또는 없음."""
    if not (_RE_S3_HANGUL_ANY.match(prev_text[-1:])
            and _RE_S3_HANGUL_ANY.match(cur_text[:1])):
        return " "
    if _RE_S3_JOSA_HEAD.match(cur_text):
        return ""
    # 두 글자 이하 꼬리는 낱말 한가운데서 끊긴 것이다 ('적으시'+'오.')
    if len(re.sub(r'\d+\)\s*(?:\[[^\]]*\])?\s*$', '', cur_text).strip()) <= 2:
        return ""
    last = prev_text.split()[-1] if prev_text.split() else ""
    if len(last) == 1 and last not in _S3_ONE_SYLLABLE_WORDS:
        return ""
    return " "
# 문장 한가운데서 끊긴 줄 — 낱말/숫자/쉼표로 끝난다. 밑줄·화살표·마커로
# 끝나는 줄(기입란·표 셀)은 '끊김'이 아니라 그 자체로 완결된 줄이다.
_RE_S3_MID_SENTENCE = re.compile(r'[A-Za-z0-9가-힣,，]\s*$')
# 끊긴 자리의 양쪽 — 앞줄이 영문/한글 어느 쪽으로 끝났는지와 뒷줄이 같은 말로
# 이어지는지를 함께 본다. 선지 마지막 항목처럼 낱말로 끝나는 줄 다음에 **새
# 문장**(대문자/한글 새 문장)이 오는 경우를 이어붙이지 않기 위한 조건이다.
# 발문이 끝났음을 알리는 꼬리 — 물음표 또는 '…시오/세요' 명령형
_RE_S3_PROMPT_END = re.compile(r'[?？]|(?:시오|세요|십시오)\s*[.]?\s*\d*\)?\s*$')
# 시각 줄 하나가 끊긴 자리는 **꽉 찬 줄** 다음이다. 표 셀(영작 배열 낱말 조각,
# <보기> 낱말 묶음)은 짧은 조각이라 여기서 걸러진다 (코퍼스 실측: 이 하한이
# 없으면 hwp 표 원고 39개 잡의 낱말 조각이 줄줄이 붙는다).
_S3_WRAP_MIN_LEN = 60
# 발문 머리 신호 (core.structure.rules.Q_START_HINT 의 한글 부분) — 이 말로
# 시작하는 줄은 그 자체로 온전한 발문이라 앞줄의 이어짐이 아니다
# ('3. 단어 수: 15단어' + '위 글의 밑줄 친 …것은?' 을 붙이던 오작동 차단)
_RE_S3_Q_OPENER = re.compile(
    r'^(?:서술형|다음|위\s*글|윗\s*글|윗글|아래\s*글|글의|밑줄|주어진|각\s*괄호)')
_RE_S3_PREV_EN = re.compile(r'[A-Za-z0-9,，]\s*$')
_RE_S3_PREV_KO = re.compile(r'[가-힣,，]\s*$')
_RE_S3_CONT_EN = re.compile(r'^[\'"“”‘’(\[]*[a-z]')
_RE_S3_CONT_KO = re.compile(r'^[\'"“”‘’(\[]*[가-힣]')
# 이어붙이면 안 되는 줄 — 정답/해설 섹션 표제와 책 헤더. 이 줄들은 뒤 단계가
# 앵커로 삼아 통째로 잘라내므로, 붙어 버리면 정답이 그대로 인쇄된다.
_RE_S3_NO_JOIN = re.compile(
    r'정답\s*(?:및|과)?\s*해설|빠른\s*정답|정답지|해설지|^\s*정답\s*$'
    r'|변형\s*문제|수능특강|전국연합|학력평가|기출문제집')


def _s3_text(p):
    return (p.get('text', '') if isinstance(p, dict) else str(p)).strip()


def _s3_set_text(p, text):
    """단락 텍스트 교체 — runs(밑줄 정보)도 같은 규칙으로 맞춘다."""
    if not isinstance(p, dict):
        return text
    p['text'] = text
    return p


def _is_step3_head_junk(text):
    """문서 머리의 워크시트 부속물인가 — 표제/머리글 막대/기입란.

    완제품이 같은 자리를 자기 디자인으로 채우는 것들이다 (W47 구조 판정
    재사용). 원고마다 문구가 다르므로 형태만 본다:
      · 머리글 막대 — 파이프로 필드를 나눈 메타 정보
        ('외부지문 1~5번 | 객관식 50문항 | 학생용')
      · 기입란     — 라벨 + 밑줄만 ('학교  ______________')
      · 표제       — 종결부호도 물음표도 없는 짧은 제목 줄
    """
    t = (text or "").strip()
    if not t:
        return False
    try:
        from core.structure import manuscript_noise as _MN
        if _MN.is_running_head(t) or _MN.is_answer_blank(t):
            return True
    except Exception:                                          # noqa: BLE001
        pass
    if (len(t) <= 80 and "?" not in t
            and not _RE_S3_SENT_END.search(t)
            and not _RE_S3_UNIT_HEAD.match(t)):
        return True
    # W90: 머리 블록의 편집 안내문 한 줄 ('원문을 보존하고 … 적용했습니다.').
    # 종결부호가 있어 표제 규칙에는 안 걸리지만 본문이 아니다 — 합쇼체는
    # 원고 편집자가 사람에게 하는 말이라 교재 지면 문장에는 쓰이지 않는다.
    # 머리 블록 스캔(첫 콘텐츠 줄에서 중단)에서만 쓰이므로 본문 중간의
    # 존댓말 대화 지문에는 닿지 않는다.
    return bool(len(t) <= 80 and _RE_S3_POLITE_END.search(t))


def _is_step3_content_line(text):
    """실전문제의 실질 콘텐츠 줄인가 — 세트 안내·발문·선지·문항 번호·지문 문장."""
    from core.structure import rules as R
    t = (text or "").strip()
    if not t:
        return False
    if any(r.search(t) for r in R.Q_INTRO_FALLBACK):
        return True
    if R.C_START.match(t) or _RE_S3_ITEM_HEAD.match(t):
        return True
    if (R.Q_HEAD_HINT.search(t[:R.Q_HEAD_WINDOW])
            and any(r.search(t) for r in R.Q_FALLBACK_PATTERNS)):
        return True
    # 지문 문장 — 길고 종결부호로 끝난다
    return bool(len(t) > 80 and _RE_S3_SENT_END.search(t))


def _strip_step3_front_matter(paras, log=None):
    """원고 앞머리(표지·학습 플랜 표·기획/검수 크레딧) 통째 제거.

    아잉카 Step 01 원고(2026-09-12 사용자 지시 '이걸로 다시 조판') 앞에는
    학습 플랜 표와 크레딧이 31줄 붙어 있다. 머리 블록 걷기
    (_strip_step3_rights_and_title)는 '문항 구성 (총 334문항)' 처럼 괄호로
    끝나는 표 칸을 종결부호 규칙 때문에 본문으로 보고 멈춰, 나머지가 실전문제
    첫 지면에 그대로 인쇄된다.

    **첫 콘텐츠 줄**(세트 안내·발문·선지·문항 번호·긴 지문 문장) 앞을 통째로
    뗀다. 두 조건이 다 맞을 때만 — ① 그 앞이 여섯 줄 이상이고 ② 그 앞에
    지문다운 줄(긴 로마자 문장)이 하나도 없을 때. 지문이나 짧은 지문 라벨로
    시작하는 원고는 그대로 둔다.
    """
    first = next((k for k, p in enumerate(paras)
                  if _is_step3_content_line(_s3_text(p))), None)
    if first is None or first < 6:
        return paras
    for p in paras[:first]:
        t = _s3_text(p).strip()
        if not t or len(t) <= 25:
            continue
        letters = [c for c in t if c.isalpha()]
        ko = sum(1 for c in letters if '가' <= c <= '힣')
        if letters and ko / len(letters) < 0.3:
            return paras          # 로마자 본문이 섞여 있다 — 앞머리가 아니다
    if callable(log):
        log(f"[파서] step3 원고 앞머리(표지·플랜·크레딧) 제거: {first}줄")
    return paras[first:]


def _strip_step3_rights_and_title(paras, log=None):
    """원고 워크시트 잔재 1단계 — 권리 고지 + 문서 **머리 블록**.

    권리 고지(저작권/무단 배포)는 원고 페이지마다 반복되는 워터마크라 어느
    위치에 있든 본문이 아니다.

    문서 머리에는 표제·머리글 막대·기입란이 한 덩어리로 붙어 있다 (사용자
    지적 2026-08-31, 성덕고2 EBS 연계): 첫 줄 하나만 벗기면 나머지가 그대로
    실전문제 첫 지면에 인쇄된다. 첫 **실질 콘텐츠 줄**(발문/지문/마커)을
    만날 때까지 이어서 걷어낸다 — 문서 중간은 건드리지 않는다.
    """
    drop = set()
    n = len(paras)
    i = 0
    while i < n:                       # 머리 블록 (첫 콘텐츠 줄에서 중단)
        t = _s3_text(paras[i])
        if not t:
            i += 1
            continue
        if not _is_step3_head_junk(t):
            break
        drop.add(i)
        i += 1
    for k in range(i, n):              # 문서 전체 — 권리 고지만
        t = _s3_text(paras[k])
        if t and _RE_S3_RIGHTS_NOTICE.search(t) \
                and not _RE_S3_ITEM_HEAD.match(t):
            drop.add(k)
    if drop and callable(log):
        log(f"[파서] step3 머리 잔재/권리 고지 제거: {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


def _strip_step3_type_labels(paras, log=None):
    """원고 워크시트 잔재 2단계 — 문제 묶음의 유형 섹션 라벨.

    짧고 종결부호 없는 한 줄인데 **바로 다음 실질 줄이 문항 번호 발문이거나
    '다음 글을 읽고 물음에…' 도입문**이면 유형 표기다 ('문법', '빈칸 추론',
    '주어진 문장 넣기', '서술형'). 완제품은 같은 자리를 자기 섹션 디자인으로
    채우므로 인쇄되면 안 된다.

    반드시 _join_step3_split_paragraphs **뒤**에 부른다 — 쪼개진 지문 꼬리
    ('“descending dragon.” ⑤')가 붙기 전에는 짧은 독립 줄과 구분되지 않는다.
    """
    n = len(paras)

    def _next_real(i):
        j = i + 1
        while j < n and not _s3_text(paras[j]):
            j += 1
        return _s3_text(paras[j]) if j < n else ""

    def _prev_real(i):
        j = i - 1
        while j >= 0 and not _s3_text(paras[j]):
            j -= 1
        return _s3_text(paras[j]) if j >= 0 else ""

    drop = set()
    maybe = set()
    for i in range(n):
        t = _s3_text(paras[i])
        if not t or len(t) > 40:
            continue
        if len(t) > 30 and _RE_S3_HANGUL_ANY.search(t):
            continue                      # 한글 라벨은 30자까지
        if _RE_S3_SENT_END.search(t) or _RE_S3_UNIT_HEAD.match(t):
            continue
        if _RE_S3_ANY_MARKER.search(t) or _RE_S3_NO_JOIN.search(t):
            continue
        # 유형 라벨은 **앞 문항이 끝난 자리**에 선다 — 앞줄이 선지이거나
        # 문장으로 끝나야 한다. 조건 항목('필요시 어형 변화 가능')은 앞줄이
        # 또 다른 조건 항목이라 여기서 걸러진다 (앞 문항에 딸린 줄이다).
        prv = _prev_real(i)
        if prv and not (_RE_S3_SENT_END.search(prv)
                        or _RE_S3_ANY_MARKER.match(prv)):
            continue
        # 라벨은 유형을 가리키는 이름씨 마디다 — 쉼표/마침표가 있으면 문장의
        # 조각이고('Best regards, John Smith'), 숫자/밑줄이 있으면 원고
        # 페이지 머리글이다('공통영어2_미래김 1과_01~02')
        if re.search(r'[,，.。0-9_~／/]', t):
            continue
        nxt = _next_real(i)
        if not (_RE_S3_ITEM_HEAD.match(nxt) or _RE_S3_QINTRO.search(nxt)):
            continue
        (drop if _RE_S3_HANGUL_ANY.search(t) else maybe).add(i)
    # 영문만인 줄은 한글 유형 라벨이 이미 둘 이상 확인된 문서에서만 라벨로
    # 본다 ('Implication & Content Understanding'). 관행이 없는 문서의 영문
    # 짧은 줄은 지문 조각일 수 있다 ('Transformation').
    if len(drop) >= 2:
        drop |= maybe
    if drop and callable(log):
        log(f"[파서] step3 유형 섹션 라벨 제거: {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


def _join_step3_split_paragraphs(paras, log=None):
    """줄 단위로 쪼개진 한 문단을 되붙인다.

    원고가 PDF/HWP 변환본이면 한 문단이 시각 줄마다 별개 단락으로 끊겨 있다.
    끊긴 자리는 구조로 알아본다 — 앞줄이 **종결부호 없이** 끝나고, 뒷줄이
    새 구조 단위(문항 번호/선지 마커/괄호 라벨)로 시작하지 않으며, 둘 사이에
    빈 단락(문단 경계)이 없으면 한 문단이다.

    이걸 안 붙이면 ①발문이 두 조각 나 조판 번호가 두 번 붙고(‘103 …필요시
    변 / 104 형하여 적으시오’), ②지문이 중간에서 끊겨 보이며, ③앞 조각이
    발문으로 안 잡혀 문항 수가 원고보다 모자란다 (수능만만 09강 실증:
    157문항 → 번호 153개, 그중 11개가 뒷조각).
    """
    out = []
    joined = 0
    last_idx = None
    prompt_seen = False        # 직전에 남긴 줄이 문장삽입 발문인가
    given_box = False          # 지금 잇고 있는 줄이 '주어진 문장' 상자인가
    for i, p in enumerate(paras):
        t = _s3_text(p)
        if not t:
            out.append(p)
            last_idx = None                   # 빈 단락 = 문단 경계
            prompt_seen = False
            given_box = False
            continue
        if out and last_idx is not None:
            prev = out[-1]
            pt = _s3_text(prev)
            # 문장삽입의 '주어진 문장' 상자는 한두 줄짜리 짧은 문장이라
            # 줄바꿈 하한(_S3_WRAP_MIN_LEN)에 걸린다 — 발문이 앵커라 안전하게
            # 예외로 둔다 ('However, the Jade Emperor sent Mother Dragon' +
            # 'and her children to protect them.')
            # 발문(문항 번호로 시작하고 아직 안 끝난 줄)도 앵커가 확실하다 —
            # 길이 하한 없이 잇는다 ('125. 위 글에서 … living and' 59자)
            open_prompt = bool(_RE_S3_ITEM_HEAD.match(pt or "")
                               and not _RE_S3_PROMPT_END.search(pt or ""))
            floor = 0 if (given_box or open_prompt) else _S3_WRAP_MIN_LEN
            # 뒷조각이 앞줄의 **문항 번호와 같은 각주 번호**로 끝나면 그 줄이
            # 발문의 나머지라는 결정적 증거다 ('118. …적으시' + '오.118)')
            _hd = _RE_S3_ITEM_HEAD.match(pt or "")
            tail_ref = bool(_hd and re.search(
                r'(?<![0-9])' + _hd.group(1) + r'\)\s*(?:\[[^\]]*\])?\s*$', t))
            # 영어(지문·선지)는 '소문자로 이어짐'이 곧 한 문장이라는 증거다.
            # 한국어는 그런 증거가 없어(조건 줄·어휘 주석도 한글로 끝난다)
            # **문항 번호로 시작한 발문이 아직 안 끝난 경우**로만 좁힌다 —
            # '90. …가장 적절한 것' + '은?90)' 같은 발문 중간 끊김.
            cont = ((len(pt or "") >= floor
                     and _RE_S3_PREV_EN.search(pt or "")
                     and _RE_S3_CONT_EN.match(t))
                    or (_RE_S3_ITEM_HEAD.match(pt or "")
                        and not _RE_S3_PROMPT_END.search(pt or "")
                        and (_RE_S3_PROMPT_END.search(t) or tail_ref)
                        and not _RE_S3_Q_OPENER.match(t)
                        and _RE_S3_PREV_KO.search(pt or "")
                        and _RE_S3_CONT_KO.match(t)))
            if (pt and cont
                    and not _RE_S3_UNIT_HEAD.match(t)
                    and not _RE_S3_NO_JOIN.search(pt)
                    and not _RE_S3_NO_JOIN.search(t)):
                glue = _s3_join_glue(pt, t)
                merged = pt + glue + t
                _s3_set_text(prev, merged)
                if isinstance(prev, dict) and isinstance(p, dict):
                    pr, cr = prev.get('runs'), p.get('runs')
                    if isinstance(pr, list) and isinstance(cr, list):
                        mid = [{"t": glue, "ul": False}] if glue else []
                        prev['runs'] = pr + mid + cr
                joined += 1
                continue
        out.append(p)
        last_idx = i
        given_box = prompt_seen
        prompt_seen = bool(_RE_S3_INSERT_PROMPT.search(t))
    if joined and callable(log):
        log(f"[파서] step3 쪼개진 단락 되붙임: {joined}건")
    return out


def _strip_step3_footnote_refs(paras, log=None):
    """발문 끝의 각주 참조 번호 제거 ('…적절한 것은?155)').

    문항 번호로 시작하는 줄에서, **줄 머리 번호와 같은 수**가 끝에 'N)' 로
    붙어 있을 때만 벗긴다 (꼬리 태그 '[045]'는 그대로 둔다) — 같은 수라는
    조건이 본문 괄호 번호와 각주 참조를 갈라준다.
    """
    hit = 0
    for p in paras:
        t = _s3_text(p)
        m = _RE_S3_ITEM_HEAD.match(t)
        if not m:
            continue
        num = m.group(1)
        new = re.sub(r'(?<=[.?!])\s*' + num + r'\)(?=\s*(?:\[[^\]]*\])?\s*$)',
                     '', t)
        if new != t:
            _s3_set_text(p, new)
            if isinstance(p, dict) and isinstance(p.get('runs'), list):
                tail = num + ')'
                for r in reversed(p['runs']):
                    if isinstance(r.get('t'), str) and tail in r['t']:
                        r['t'] = r['t'].replace(tail, '', 1)
                        break
            hit += 1
    if hit and callable(log):
        log(f"[파서] step3 발문 각주 번호 제거: {hit}건")
    return paras


# W88 (사용자 지적 2026-09-04, 고2 26년 6월 부산 모의고사): 여러 변형
# 섹션을 한 파일에 이어붙인 원고는 섹션 경계마다 편집용 태그 묶음이
# 반복된다 — "19번"(문항 자기 번호) / "심경"(유형 표기, W83과 같은 부류지만
# 자리가 다르다) / "Section ❶"(변형 구획 표시). 그리고 정답 시작 직전에는
# 시험 출처 헤더("고2 2026년 6월 부산광역시 교육청")가 반복된다. 넷 다
# 원고 편집 관행이고 완제품에 인쇄될 자리가 없다.
_RE_S3_SECTION_MARKER = re.compile(
    r'^Section\s*[①-⑳❶-❿⓵-⓾㉠-㉭]\s*$', re.I)
# 시험 출처(교육청/평가원 등) 키워드 — engines/workbook_v2/plan.py K3와
# 같은 어휘 계열(모듈이 달라 직접 import 대신 국소 복제 — 기존 관행).
_RE_S3_EXAM_ORIGIN_KW = re.compile(
    r'교육청|학력평가|평가원|수능특강|수능완성|학평|모평')


def _strip_step3_generated_item_meta(paras, log=None):
    """W90 — 생성 원고의 문항 머리 부속물 3종 (괘선 / '문항 N' / 메타 막대).

    완제품은 문항 번호를 자기 스타일로 매기고(S_실전문제 번호), 문항 사이는
    지면 디자인으로 나눈다. 원고의 다음 셋은 그 자리를 두 번 채운다:
      · 괘선 구분줄 '──────…' — 단 폭을 넘어 석 줄로 흐른다 (실측)
      · 문항 머리 '문항 1'     — 완제품 자동 번호 '01'과 중복
      · 메타 막대 '09강 A | 난이도 상' — 출처·난이도는 편집용 정보

    메타 막대는 **'문항 N' 바로 뒤 자리**에서만 지운다 (머리글 막대 판정은
    manuscript_noise 재사용). 문서 어디서나 지우면 파이프가 든 본문 표를
    건드릴 수 있다 — 이 자리는 이미 확정된 노이즈의 이웃이라 안전하다.
    """
    try:
        from core.structure import manuscript_noise as _MN
    except Exception:                                          # noqa: BLE001
        _MN = None
    n = len(paras)
    drop = set()
    rules = 0
    for i in range(n):
        t = _s3_text(paras[i])
        if not t:
            continue
        if _RE_S3_RULE_LINE.match(t):
            drop.add(i)
            rules += 1
            continue
        if not _RE_S3_GEN_ITEM_LABEL.match(t):
            continue
        drop.add(i)
        j = i + 1
        while j < n and not _s3_text(paras[j]):
            j += 1
        if j < n and _MN is not None and _MN.is_running_head(_s3_text(paras[j])):
            drop.add(j)
    if drop and callable(log):
        log("[파서] step3 생성 원고 문항 머리 제거: %d줄 (괘선 %d)"
            % (len(drop), rules))
    return [p for k, p in enumerate(paras) if k not in drop]


def _strip_step3_section_markers(paras, log=None):
    """변형 섹션 구획 표시("Section ❶/❷/…") 단독 줄 제거.

    어떤 형태로도 발문·지문·선지가 될 수 없는 고정 서식이라 위치 무관하게
    안전하게 지운다(코퍼스 실측: 이 정확한 형태로 등장한 자리 전부가 노이즈).
    """
    drop = {i for i, p in enumerate(paras)
           if _RE_S3_SECTION_MARKER.match(_s3_text(p))}
    if drop and callable(log):
        log(f"[파서] step3 변형 섹션 마커 제거: {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


def _s3_own_item_number_pat(item_num):
    return re.compile(r'^\s*0*' + re.escape(str(int(item_num))) + r'\s*번\s*$')


def _s3_own_item_number_merged_pat(item_num):
    """섹션 경계의 **끝** 태그는 'N번'과 유형 표기가 파이프로 한 줄에
    합쳐지기도 한다('19번｜심경' — 시작 태그는 3줄로 흩어져 있는데 끝
    태그는 왜 한 줄인지는 원고 편집자 재량, 구조만 본다). 파이프 뒤는
    숫자/문장부호 없는 짧은 이름씨 마디여야 한다(유형 표기 형태)."""
    return re.compile(r'^\s*0*' + re.escape(str(int(item_num)))
                      + r'\s*번\s*[|｜]\s*[가-힣]{1,10}\s*$')


def _strip_step3_own_item_number_tag(paras, item_num=None, log=None):
    """문항 자신의 파일 번호가 본문 중간에 태그로 반복된 단독 줄 제거
    ('19번' 또는 유형 표기와 합쳐진 '19번｜심경' — 원본 파일명
    '…19번.hwp'와 같은 번호).

    item_num과 **정확히 일치할 때만** 지운다 — 다른 문항을 가리키는 진짜
    본문 숫자('1번 사진처럼')까지 건드리지 않기 위한 안전장치. item_num이
    없으면(번호 매칭이 확정 안 된 경로) 아무것도 하지 않는다.
    """
    if not item_num:
        return paras
    pat = _s3_own_item_number_pat(item_num)
    pat_merged = _s3_own_item_number_merged_pat(item_num)
    drop = {i for i, p in enumerate(paras)
           if pat.match(_s3_text(p)) or pat_merged.match(_s3_text(p))}
    if drop and callable(log):
        log(f"[파서] step3 문항번호 태그 제거({item_num}번): {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


def _strip_step3_variant_type_tag(paras, item_num=None, log=None):
    """자기 번호 태그와 Section 마커 **사이에 낀** 짧은 유형 표기 한 줄 제거
    ('심경'/'도표'/'안내문' 등 — 원고마다 문항 갈래를 나타내는 말이 달라
    낱말로는 못 잡는다).

    W83 유형 라벨 제거(발문 바로 앞/뒤)와 자리가 달라 그 규칙에 안 걸린다 —
    여기서는 낱말이 아니라 **두 확실한 이웃**(자기 문항 번호 태그, Section
    마커)으로 감싸인 자리만 본다. 이 두 이웃 자체가 이미 안전하게 확정된
    노이즈라, 그 사이에 남는 짧은 한글 단독 줄은 무엇이 와도 같은 편집용
    표기다 — 실제 문항 내용이 이 자리(자기 번호와 Section 마커 사이)에
    올 일은 없다. 반드시 _strip_step3_section_markers/_strip_step3_own_
    item_number_tag **이전**에 불러 두 이웃이 아직 남아 있어야 한다.
    """
    if not item_num:
        return paras
    num_pat = _s3_own_item_number_pat(item_num)
    n = len(paras)

    def _next_real_idx(i):
        j = i + 1
        while j < n and not _s3_text(paras[j]):
            j += 1
        return j

    drop = set()
    for i in range(n):
        if not num_pat.match(_s3_text(paras[i])):
            continue
        j = _next_real_idx(i)
        if j >= n:
            continue
        cand = _s3_text(paras[j])
        if (len(cand) > 10 or not _RE_S3_HANGUL_ANY.search(cand)
                or re.search(r'[,，.。0-9_~／/①-⑳]', cand)):
            continue
        k = _next_real_idx(j)
        if k >= n or not _RE_S3_SECTION_MARKER.match(_s3_text(paras[k])):
            continue
        drop.add(j)
    if drop and callable(log):
        log(f"[파서] step3 변형 유형 표기 제거: {len(drop)}줄")
    return [p for x, p in enumerate(paras) if x not in drop]


def _strip_step3_exam_source_line(paras, log=None):
    """시험 출처 헤더 단독 줄 제거('고2 2026년 6월 부산광역시 교육청').

    정답/해설 시작 직전 등 경계마다 반복 인쇄된다. 문장이 아니고(종결부호
    없음) 연도 표기와 출처 키워드가 함께 있어야만 걸린다 — 실제 발문/지문
    문장은 이 조합을 갖지 않는다.
    """
    drop = set()
    for i, p in enumerate(paras):
        t = _s3_text(p)
        if not t or len(t) > 40:
            continue
        if _RE_S3_SENT_END.search(t) or _RE_S3_UNIT_HEAD.match(t):
            continue
        if not re.search(r'\d{4}\s*년', t):
            continue
        if not _RE_S3_EXAM_ORIGIN_KW.search(t):
            continue
        drop.add(i)
    if drop and callable(log):
        log(f"[파서] step3 시험 출처 헤더 제거: {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


# W89 (사용자 지적 2026-09-05, 고1 26년 9월 "학평 변형" 연습용 원고): 지문별
# 문제 파일(예: '지문33_문제.docx')마다 맨 앞에 표제·설명 두 줄이 반복된다
# — "고1 2026년 9월 학평 변형 — 지문 33 (모방론과 폴록) 【문제】" /
# "연습용 · 독립 문항 15개. …정답·해설: 지문33_정답해설.docx". 낱말로는
# 원고마다(제목·지문 번호·정답 파일명) 다 달라 못 잡지만, 둘 다 진짜
# 발문/지문 문장에는 나올 수 없는 표식을 갖는다 — 표제 줄은 전각 괄호
# 【문제】로 끝나고, 설명 줄은 파일명(.docx)을 그대로 노출한다. 각각
# 단독으로도 안전해 위치 무관하게 지운다.
_RE_S3_PRACTICE_SET_TITLE = re.compile(r'【문제】\s*$')
_RE_S3_DOCX_FILENAME = re.compile(r'\.docx\b', re.I)


def _strip_step3_practice_set_header(paras, log=None):
    """연습용 문제 세트 표제/설명 줄 제거('…【문제】' / '…정답·해설: *.docx')."""
    drop = {i for i, p in enumerate(paras)
           if (lambda t: bool(t) and (_RE_S3_PRACTICE_SET_TITLE.search(t)
                                       or _RE_S3_DOCX_FILENAME.search(t)))(
               _s3_text(p))}
    if drop and callable(log):
        log(f"[파서] step3 연습용 문제 세트 표제/설명 제거: {len(drop)}줄")
    return [p for k, p in enumerate(paras) if k not in drop]


# W89 (같은 잡 — 사용자 지적 "여긴 조건인데 조건 안입혀지고"): core.structure의
# Cond 마커 판정(BOX_MARKERS["Cond"])은 "＜조건＞"만 있는 **단독** 줄이어야
# 조건 블록을 연다. 이 원고는 마커와 조건 문구가 한 줄에 붙어 있어
# ("＜조건＞ 글에 쓰인 형태 그대로 쓸 것.") 마커로 인식되지 못하고 그냥
# 본문처럼 지나갔다. 공용 분류기 정규식을 넓히는 대신(다른 모든 계열에
# 영향) — W73(_split_bracket_title_headers)과 같은 방식으로 **원고 단계에서
# 두 단락으로 쪼갠다**: 마커는 이미 검증된 단독-줄 규약을 그대로 타고,
# 남은 조건 문구는 그다음 줄로 분류기에 들어간다.
_RE_S3_INLINE_COND = re.compile(
    r'^\s*(?P<marker><\s*조\s*건\s*>|＜\s*조\s*건\s*＞|〈\s*조\s*건\s*〉'
    r'|《\s*조\s*건\s*》|\[\s*조\s*건\s*\])\s*(?P<rest>\S.*)$')
# W90 (2026-09-08 성덕2 EBS 외부지문 — 사용자 지적 "요약문/조건인데 단락
# 스타일이 안 입혀졌다"): 마커와 내용이 **한 줄**인 원고는 마커 규칙
# (core/structure/rules.py BOX_MARKERS — `^…마커…$` 단독 줄 전제)에 안 걸려
# kind=UNKNOWN → 지문 스타일로 인쇄된다. 위 조건 마커는 이미 분리하고
# 있었으나 ①요약문 ②괄호 없는 맨 '조건' 두 갈래가 빠져 있었다.
# 코퍼스 실측(step3 있는 잡 203개): 단독 줄이 표준이고(요약문 434줄/52잡,
# 조건 2056줄/170잡) 인라인은 소수 변형(요약문 4줄/2잡, 조건 16줄/14잡)이라
# **인라인을 단독 줄로 정규화**하면 다수 경로에 그대로 합류한다.
_RE_S3_INLINE_SUM = re.compile(
    r'^\s*(?P<marker>[<＜〈《\[]\s*요\s*약\s*문?\s*[>＞〉》\]])'
    r'\s*(?P<rest>\S.*)$')
# 괄호 없는 맨 '조건'. 공백 **2칸 이상**일 때만 — 한 칸까지 허용하면
# '조건 반사는 …' 같은 평범한 문장을 쪼갠다 (원고 관행은 탭/여러 칸).
_RE_S3_INLINE_BARE_COND = re.compile(
    r'^\s*(?P<marker>조\s?건)\s{2,}(?P<rest>\S.*)$')


# W90 — 요약문 본문의 (A)/(B) 빈칸. 코퍼스 실측: 요약문 본문 434줄 중
# 431줄이 원고에 이미 밑줄을 갖고 있다(`(A)__________`, 힌트 첨자형
# `(A)h________` 포함) — **원고에 있는 것이 표준**이라 엔진은 빠진 것만
# 채운다. 성덕2 EBS 외부지문 원고가 맨 `(A)`로 와서 빈칸으로 안 보였다.
_RE_S3_SUM_MARK = re.compile(
    r'^\s*[<＜〈《\[]\s*요\s*약\s*문?\s*[>＞〉》\]]\s*$')
# 이미 빈칸인 표기는 무접촉 — (A) 뒤 짧은 힌트 글자까지 허용해서 본다.
_RE_S3_SUM_SLOT = re.compile(r'\((A|B)\)(?!\s*[A-Za-z]?\s*_{3,})')
_S3_SUM_BLANK = "_" * 10


def _fill_step3_summary_blanks(paras, log=None):
    """요약문 마커 바로 뒤 본문의 (A)/(B)를 빈칸 표기로 채운다."""
    filled = 0
    for i, p in enumerate(paras):
        if i == 0 or not _RE_S3_SUM_MARK.match(_s3_text(paras[i - 1]) or ""):
            continue
        t = _s3_text(p)
        if not t or not _RE_S3_SUM_SLOT.search(t):
            continue
        rep = lambda m: "(%s)%s" % (m.group(1), _S3_SUM_BLANK)
        new_t = _RE_S3_SUM_SLOT.sub(rep, t)
        runs = p.get("runs") if isinstance(p, dict) else None
        new_runs = None
        if runs:
            cand = [dict(r, t=_RE_S3_SUM_SLOT.sub(rep, r.get("t") or ""))
                    for r in runs]
            if "".join(r["t"] for r in cand) == new_t:
                new_runs = cand          # 런 경계를 안 넘은 경우만 서식 보존
        p["text"] = new_t
        p["runs"] = new_runs or [{"t": new_t, "ul": False}]
        filled += 1
    if filled and callable(log):
        log(f"[파서] step3 요약문 (A)/(B) 빈칸 표기 보완: {filled}줄")
    return paras


# 조건 항목 꼬리에 요약문이 이어붙은 단락 (실측 2026-09-12 고2 26년 9월):
#   "② 본문에서 쓰인 단어를 있는 그대로 사용할 것. (어형 변화불가)
#    Organizational exclusion can have a ______(A) impact …"
# 원고가 표 셀을 합치며 붙인 것으로, 그대로 두면 **요약문이 조건 상자 안에**
# 인쇄된다. 한국어 조건 종결("…할 것." / "…불가)") 뒤에 영문 문장이 시작되는
# 자리에서 자른다 — 조건 항목은 한국어, 요약문은 영어라 경계가 분명하다.
_RE_S3_COND_TAIL_EN = re.compile(
    r'^(.*?(?:할\s*것\.|쓸\s*것\.|불가\s*\)|가능\s*\)))\s+'
    r'([A-Z][A-Za-z][^\n]{20,})$')


def _split_step3_cond_tail_summary(paras, log=None):
    """조건 항목 + 이어붙은 요약문을 두 단락으로 (runs 보존)."""
    out = []
    n = 0
    for p in paras:
        t = _s3_text(p)
        m = _RE_S3_COND_TAIL_EN.match(t) if t else None
        if not m or "_" not in m.group(2):
            out.append(p)
            continue
        head, tail = m.group(1), m.group(2)
        runs = p.get("runs") if isinstance(p, dict) else None
        hi = t.index(head)
        ti = t.index(tail, hi + len(head))
        out.append({"text": head,
                    "runs": _slice_runs(runs, t, hi, hi + len(head))})
        out.append({"text": tail,
                    "runs": _slice_runs(runs, t, ti, ti + len(tail))})
        n += 1
    if n and callable(log):
        log("[파서] step3: 조건 항목에 이어붙은 요약문 %d건 분리" % n)
    return out


def _split_step3_inline_cond_marker(paras, log=None):
    """'＜조건＞ 조건 문구' 한 줄 → '＜조건＞' + '조건 문구' 두 줄로 분리.

    W90: 요약문('<요약문> 본문…')과 괄호 없는 맨 '조건'도 같은 처리.
    항목 불릿(·/-)은 원고가 가진 것이므로 **주입하지 않는다** (코퍼스
    확인: 조건 항목의 불릿은 전부 원고 표기).
    """
    out = []
    split_n = 0
    for p in paras:
        t = _s3_text(p)
        m = bare = None
        if t:
            m = (_RE_S3_INLINE_COND.match(t) or _RE_S3_INLINE_SUM.match(t))
            if not m:
                bare = _RE_S3_INLINE_BARE_COND.match(t)
                m = bare
        if not m:
            out.append(p)
            continue
        marker, rest = m.group('marker'), m.group('rest')
        mi = t.index(marker)
        ri = t.index(rest, mi + len(marker))
        runs = p.get('runs') if isinstance(p, dict) else None
        if bare:
            # 맨 '조건'은 꺾쇠 표기로 통일 — 엔진 표준형(_S3_GREPS 가
            # '[조건]'도 '<조건>'으로 맞춘다)이자 완성본 관행이다.
            out.append({"text": "<조건>",
                        "runs": [{"t": "<조건>", "ul": False}]})
        else:
            out.append({"text": marker,
                        "runs": _slice_runs(runs, t, mi, mi + len(marker))})
        out.append({"text": rest,
                   "runs": _slice_runs(runs, t, ri, ri + len(rest))})
        split_n += 1
    if split_n and callable(log):
        log(f"[파서] step3 인라인 마커 분리(조건/요약문): {split_n}줄")
    return out


def _s3_join_cells(cell_paras, sep="\t"):
    """표 셀이 낱개 단락으로 쪼개진 것을 탭으로 이어붙여 한 단락으로."""
    texts = [_s3_text(p) for p in cell_paras]
    runs = []
    for k, p in enumerate(cell_paras):
        if k:
            runs.append({"t": sep, "ul": False})
        p_runs = p.get('runs') if isinstance(p, dict) else None
        runs.extend(p_runs or [{"t": texts[k], "ul": False}])
    return {"text": sep.join(texts), "runs": runs}


# W89 (같은 잡 — 사용자 지적 "선지 정렬 엉망"/"이건 뭐야"): docx 표로 만든
# (A)/(B) 짝단어 선택지("① memory\tsharpens" 형태)가 표 추출에서 행/열
# 구조를 잃고 원문자·단어1·단어2가 각각 낱개 단락이 됐다 — 분류기는
# "① 텍스트" 한 줄이어야 선지로 알아본다(골든 r5c04mock211 관행: 같은
# 내용이 한 줄이면 정상 인식). 원문자 단독 줄 + 뒤따르는 짧은 무구두점
# 셀들을 다시 한 줄로 잇는다. 우연한 단독 원문자 줄 오탐 방지 — **같은
# 열 수의 행이 연속 2개 이상**일 때만 표로 인정(반복이 신뢰 신호).
_RE_S3_LONE_CIRCLED = re.compile(r'^[①-⑩]$')
_RE_S3_TABLE_CELL = re.compile(r'^[^.!?~。！？_]{1,40}$')
_RE_S3_COL_LABEL_CELL = re.compile(r'^\(?[A-Za-z0-9]{1,2}\)?$')


def _merge_step3_table_choice_cells(paras, log=None):
    """원문자 단독 줄 + 셀 n개 (연속 2행+) → '①\\t셀1\\t셀2' 한 줄로 재결합.
    바로 앞의 열 라벨 줄(n개, 예 '(A)' '(B)')도 함께 이어붙인다."""
    n = len(paras)

    def _t(i):
        return _s3_text(paras[i]) if 0 <= i < n else None

    def _row_cells(start):
        cells = []
        k = start + 1
        while k < n:
            ct = _t(k)
            if not ct or _RE_S3_LONE_CIRCLED.match(ct) \
                    or not _RE_S3_TABLE_CELL.match(ct):
                break
            cells.append(k)
            k += 1
        return cells

    out = []
    merged_rows = 0
    i = 0
    while i < n:
        ti = _t(i)
        if ti and _RE_S3_LONE_CIRCLED.match(ti):
            cells = _row_cells(i)
            nxt_start = cells[-1] + 1 if cells else i + 1
            nxt_t = _t(nxt_start)
            nxt_cells = (_row_cells(nxt_start)
                        if nxt_t and _RE_S3_LONE_CIRCLED.match(nxt_t) else [])
            if len(cells) >= 2 and len(nxt_cells) == len(cells):
                n_cols = len(cells)
                if (len(out) >= n_cols and all(
                        _RE_S3_COL_LABEL_CELL.match(_s3_text(p) or '')
                        for p in out[-n_cols:])):
                    header_paras = out[-n_cols:]
                    del out[-n_cols:]
                    out.append(_s3_join_cells(header_paras))
                pos = i
                while True:
                    row_cells = _row_cells(pos)
                    if len(row_cells) != n_cols:
                        break
                    out.append(_s3_join_cells(
                        [paras[pos]] + [paras[c] for c in row_cells]))
                    merged_rows += 1
                    pos = row_cells[-1] + 1
                    pt = _t(pos)
                    if not (pt and _RE_S3_LONE_CIRCLED.match(pt)):
                        break
                i = pos
                continue
        out.append(paras[i])
        i += 1
    if merged_rows and callable(log):
        log(f"[파서] step3 표 선지 셀 재결합: {merged_rows}행")
    return out


# W89: 답표(정답 기입 표) 열 머리('기호'/'고친 표현' 등)도 같은 이유로
# 셀마다 쪼개진다. engines/workbook_v2/plan.py의 답표 열 머리 승격
# (_is_anslabel_head)은 두 라벨이 **한 줄**에 있어야 인식하므로 미리
# 합친다 — 닫힌 어휘(rules.ANS_TABLE_HEAD_WORDS, plan.py와 공유 관행)로
# 최소 한 셀이 답표 라벨임을 확인한 후에만 합쳐 오탐을 막는다.
#
# 오탐 실증(af602035 고2 25년 6월 18번): 표 헤더 바로 앞에 편지 맺음말
# "James Martin" / "Principal" 이 짧은 영문 단독 줄로 연달아 와서, 예전
# 구현(어휘 매치 지점과 무관하게 **뒤로도** 이어붙임)이 이 무관한 두 줄까지
# 통째로 삼켰다. 그래서 지금은 어휘가 실제로 걸린 셀에서만 시작해
# **앞으로는 절대 확장하지 않고 뒤로만**(열 개수 상한 있음) 잇는다.
_RE_S3_SHORT_LABEL_CELL = re.compile(r'^[가-힣A-Za-z][가-힣A-Za-z ]{0,14}$')
_S3_ANS_TABLE_HEAD_MAX_COLS = 3


def _merge_step3_ans_table_header_cells(paras, log=None):
    """'기호' + '고친 표현' 같은 답표 열 머리 셀들을 한 줄로 재결합."""
    from core.structure import rules as R
    n = len(paras)
    out = []
    merged = 0
    i = 0
    while i < n:
        t = _s3_text(paras[i])
        if (t and _RE_S3_SHORT_LABEL_CELL.match(t)
                and R.ANS_TABLE_HEAD_WORDS.search(t)):
            run = [i]
            j = i + 1
            while j < n and len(run) < _S3_ANS_TABLE_HEAD_MAX_COLS:
                tj = _s3_text(paras[j])
                if tj and _RE_S3_SHORT_LABEL_CELL.match(tj):
                    run.append(j)
                    j += 1
                    continue
                break
            if len(run) >= 2:
                # S_답란 스타일엔 탭스톱이 없다(다열 선지 스타일과 달리) —
                # 탭은 폭 0으로 붙어버려 골든 관행처럼 여러 칸 공백으로 잇는다.
                out.append(_s3_join_cells([paras[k] for k in run],
                                          sep="        "))
                merged += 1
                i = j
                continue
        out.append(paras[i])
        i += 1
    if merged and callable(log):
        log(f"[파서] step3 답표 열 머리 셀 재결합: {merged}건")
    return out


# W89 (같은 잡 — 사용자 지적 "13/14 두 번호가 붙는다" → 이어서 "서답형2.
# 서답형3. 이런 거 발문에서 삭제해"): "서답형 N." 이 발문과 따로 떨어진
# 단독 줄이면, 자동 채번 스타일이 둘 다에 붙어 한 문항인데 번호가 두 개
# (13/14, 15/16, 17/18) 매겨졌다. 객관식 문항은 원고에 이미 "1. 발문…"
# 처럼 번호와 발문이 한 줄이라 이 문제가 없다 — 서답형만 라벨과 발문이
# 원고에서 갈라져 있다. 완제품에 "서답형 N."이 인쇄될 자리가 없다는
# 사용자 확정 스펙 — 발문과 합치지 않고 라벨 줄 자체를 지운다.
_RE_S3_SUBJECTIVE_LABEL = re.compile(r'^서답형\s*\d+\s*\.?\s*$')


def _strip_step3_subjective_label_line(paras, log=None):
    """'서답형 N.' 단독 줄 제거 — 발문/번호와 무관하게 완제품엔 없다."""
    drop = {i for i, p in enumerate(paras)
           if _RE_S3_SUBJECTIVE_LABEL.match(_s3_text(p))}
    if drop and callable(log):
        log(f"[파서] step3 서답형 라벨 줄 제거: {len(drop)}건")
    return [p for k, p in enumerate(paras) if k not in drop]


def _normalize_step3_manuscript(paras, item_num=None, log=None):
    """Step3 원고 정규화 1단계 — 권리 고지/책 표제 + 변형 섹션 잔재
    (보존 스냅샷 전에).

    순서 중요: 유형 표기 제거(_strip_step3_variant_type_tag)는 자기 번호
    태그·Section 마커를 **이웃**으로 삼아 자리를 잡으므로, 그 둘을 실제로
    지우는 함수보다 반드시 먼저 불러야 한다.
    """
    paras = _strip_step3_rights_and_title(paras, log)
    paras = _strip_step3_front_matter(paras, log)
    paras = _strip_step3_generated_item_meta(paras, log)
    paras = _strip_step3_practice_set_header(paras, log)
    paras = _split_step3_inline_cond_marker(paras, log)
    paras = _split_step3_cond_tail_summary(paras, log)
    paras = _fill_step3_summary_blanks(paras, log)
    paras = _strip_step3_variant_type_tag(paras, item_num, log)
    paras = _strip_step3_section_markers(paras, log)
    paras = _strip_step3_own_item_number_tag(paras, item_num, log)
    paras = _strip_step3_exam_source_line(paras, log)
    paras = _merge_step3_table_choice_cells(paras, log)
    paras = _merge_step3_ans_table_header_cells(paras, log)
    paras = _strip_step3_subjective_label_line(paras, log)
    return paras


def _normalize_step3_lines(paras, log=None):
    """Step3 원고 2단계 — 쪼개짐 되붙임 → 유형 라벨 제거 → 각주 번호 제거.

    선지 자동번호(_add_step3_choice_numbers) **뒤**에 부른다. 그 전에는
    hwp 표형 5지선다가 마커 없는 맨 문장 다섯 줄이라, 줄 이어붙임이 선지를
    줄줄이 하나로 붙여 버린다 (코퍼스 실측 39개 잡).
    """
    paras = _join_step3_split_paragraphs(paras, log)
    paras = _strip_step3_type_labels(paras, log)
    paras = _strip_step3_footnote_refs(paras, log)
    return paras


def _strip_step3_item_numbers(paras):
    def _txt(p):
        return (p.get('text', '') if isinstance(p, dict) else str(p)).strip()

    n = len(paras)
    cand = []           # (idx, value)
    for i in range(n):
        m = _RE_STEP3_ITEM_NUM.match(_txt(paras[i]))
        if not m:
            continue
        j = i + 1
        while j < n and not _txt(paras[j]):
            j += 1
        if j >= n:
            continue
        nxt = _txt(paras[j])
        if not re.search(r'[가-힣]', nxt):
            continue        # 다음 줄이 한글 지시문이 아니면 문항 번호 아님
        if _RE_STEP3_ITEM_NUM.match(nxt):
            continue        # 숫자 줄이 이어지면 표 셀 계열
        cand.append((i, int(m.group(1))))
    if len(cand) < 5:
        return paras
    best, run = [], [cand[0]]
    for prev, cur in zip(cand, cand[1:]):
        if cur[1] == prev[1] + 1:
            run.append(cur)
        else:
            if len(run) > len(best):
                best = run
            run = [cur]
    if len(run) > len(best):
        best = run
    if len(best) < 5:
        return paras
    drop = set(i for i, _v in best)
    return [p for k, p in enumerate(paras) if k not in drop]


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
    cut_idx = _s3_answer_cut_idx(
        paras,
        lambda t: any(pat.match(t) for pat in _STEP3_ANS_SECTION_PATTERNS))
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


# 복수 지문 1파일 원고의 지문 헤더. 강 표기가 번호형/이름형 두 가지이고
# 숫자와 단위 사이에 공백이 섞인다 (실측 2026-08-07):
#   "11강 20번 – 고1 16년 11월 31번"
#   "빈칸 추론 40 번 – 고 1 21 년 6 월 32 번"
# 앞부분(강 표기)은 형태가 제각각이라 고정하지 않고, "NN번 – 고G YY년 M월
# QQ번" 꼬리만 확정 패턴으로 잡는다. group(1)=마더텅 번호.
_RE_STEP3_MULTI_HEAD = re.compile(
    r"^\s*(?:\d{1,2}\s*강|[^\d\n]*?)\s*(\d{1,3})\s*번\s*[–\-—~]\s*"
    r"고\s*(\d)\s*(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,3})\s*번")

# 회차 통합 Step3 원고 방언 ② — 지문 구분 헤더가 **"QQ번 · 지문 제목"**
# (실측 2026-09-12 '고2 26년 9월 변형문제.docx', 사용자 지적 "모의고사인데
# 스텝3에 지문번호는 왜 안 넣었어"):
#   "18번 · 브로슈어 인쇄 견적 문의 이메일"
#   "41~42번 · 선택 설계와 알고리즘 (장문)"
# 회차(YY·MM)가 헤더에 없어 위 두 방언에 안 걸리고, 파일명에도 문항번호가
# 없어 파일명 매칭에도 안 걸린다 → 345문항이 question_num="textbook" **단일
# 통짜**로 흘러 지문 경계가 사라졌다. 경계가 없으니 지문번호 `{YYMMQQ}`
# (plan.build_step3 의 code 삽입)도, 지문 단위 페이지 나눔도 전부 무력화.
# 회차는 폴더 연·월(job 의 year/month)에서 받는다.
_RE_STEP3_DOTTED_HEAD = re.compile(
    r"^\s*(\d{1,3})\s*(?:[~〜～]\s*(\d{1,3})\s*)?번\s*[·・ㆍ•]\s*(\S.*)$")
# 이 방언은 회차를 스스로 못 읽어 검증이 약하다 — 한 파일에 **여러 개**가
# 규칙적으로 있을 때만 지문 헤더로 본다 (본문 한 줄의 우연 매칭 차단).
_S3_DOTTED_HEAD_MIN = 3


# 회차 통합 Step3 원고 헤더 방언 — "2021년_고1_9월_인천광역시 교육청_학력평가_36번"
# 한 파일에 36·37번이 같이 들어 있고, 같은 헤더가 변형문제마다 반복된다
# (실측 2026-08-20: 고1 21년 9월 '2021년 9월 36-37번 변형문제.hwpx' — 헤더 14개,
#  36번 8블록 + 37번 6블록). 파일명 규칙(고1 25년 9월 20번.hwp)에도,
# 기존 보충 방언(_RE_STEP3_MULTI_HEAD)에도 안 걸려 그 회차 step3 가 통째로 빈다.
_RE_STEP3_YM_HEAD = re.compile(
    r"^\s*(?:19|20)?(\d{2})\s*년\s*[_\s]*고\s*\d\s*[_\s]*"
    r"(\d{1,2})\s*월[^\n]*?[_\s](\d{1,3})\s*번\s*$")

# 파일명 방언 — "고1 16년 6월 36번.hwpx" 가 **폴더 회차와 다른** 회차일 때.
# 보충 원고 폴더(마더텅 N강)는 회차가 섞여 있어 폴더 연·월(0년 0월)로
# 코드를 만들 수 없다 (실측 2026-08-21: 13강 Step3 = 16년 6월·17년 9월·19년 9월).
_RE_STEP3_FNAME_YM = re.compile(
    r"고\s*\d\s*(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,3})(?:~\d{1,3})?\s*번")

# 발문 꼬리에 붙은 정답 — "…가장 적절한 것은? ⑤",
# "…적절하지 않은 것은? ④: prevent → create", "…쓰시오. ⓓ which → where".
# 별도 줄 정답만 지우는 _strip_step3_answers 로는 안 걸려 학생용에 정답이
# 그대로 인쇄된다. 회차 통합 원고 흡수 경로에서만 적용한다.
_RE_STEP3_TAIL_ANSWER = re.compile(
    r"(?<=[?？])\s*(?:\d{1,3}\s*번)?\s*[①-⑳ⓐ-ⓩ][^\n]*$"
    r"|(?<=[?？])\s*\d{1,3}\s*번\s*$"
    r"|(?<=시오[.])\s*[①-⑳ⓐ-ⓩ][^\n]*$")


def _strip_step3_tail_answers(paras):
    """발문 줄 끝에 붙은 정답 꼬리를 잘라낸다 (runs 도 같이 자름)."""
    out = []
    for p in paras or []:
        if not isinstance(p, dict):
            out.append(p)
            continue
        text = p.get("text") or ""
        cut = _RE_STEP3_TAIL_ANSWER.sub("", text).rstrip()
        if cut == text or not cut:
            out.append(p)
            continue
        # runs 를 새 길이에 맞춰 자른다 (오프셋 정합 유지)
        runs, off = [], 0
        for r in p.get("runs") or []:
            t = r.get("t") or ""
            if off >= len(cut):
                break
            keep = t[:max(0, len(cut) - off)]
            if keep:
                runs.append(dict(r, t=keep))
            off += len(t)
        q = dict(p)
        q["text"] = cut
        q["runs"] = runs or [{"t": cut, "ul": False}]
        out.append(q)
    return out


# ── PDF Step3 원고 (사용자 지시 2026-09-12) ─────────────────────────────────
# PDF 는 Step3 원고로만 받는다. 추출은 core/extract/pdf.py — docx/hwp 와 같은
# 단락·밑줄 모양으로 낸다. 같은 파싱 안에서 한 PDF 를 여러 번(제외 판정·
# 흡수 두 곳·본 경로) 읽으므로 캐시한다.
_S3_PDF_CACHE = {}
_S3_PDF_EXCL_CACHE = {}
_RE_S3_ANSWER_NAME = re.compile(r"정답|해설|답지|답안")
_S3_EDIT_EXTS = (".docx", ".hwp", ".hwpx")


def _is_pdf_name(name):
    return _nfc(name or "").lower().endswith(".pdf")


def _step3_pdf_paragraphs(fpath, extract_underline=True, image_dir=None,
                          log=None):
    """PDF Step3 원고 → 단락. 읽을 수 없으면 PdfTextUnreadable(이유 포함)."""
    try:
        st = os.stat(fpath)
        key = (os.path.abspath(fpath), st.st_mtime, st.st_size,
               bool(extract_underline), image_dir or "")
    except OSError:
        key = None
    if key is not None and key in _S3_PDF_CACHE:
        ent = _S3_PDF_CACHE[key]
    else:
        lines = []
        paras = _pdf_extract_paragraphs(fpath, extract_underline,
                                        exclude_footnotes=True,
                                        image_dir=image_dir, log=lines.append)
        ent = {"paras": json.dumps(paras, ensure_ascii=False),
               "logs": lines, "told": set()}
        if key is not None:
            _S3_PDF_CACHE[key] = ent
    # 추출 요약('[PDF] … 미주 제외 · 공백 복원')은 로그를 받는 첫 호출에서
    # 한 번 내보낸다 — 첫 추출이 로그 없는 경로(흡수 함수)에서 일어나도
    # 잡 로그에 남도록 (같은 잡에서 두 번 찍지 않게 로그 함수별로 기억).
    if callable(log) and id(log) not in ent["told"]:
        ent["told"].add(id(log))
        for line in ent["logs"]:
            log(line)
    return json.loads(ent["paras"])


_RE_S3_KEY_LESSON = re.compile(r"(\d+)\s*강\s*(\d+(?:\s*~\s*\d+)?)\s*번")
_RE_S3_KEY_NUM = re.compile(r"(\d+(?:\s*~\s*\d+)?)\s*번")


def _s3_name_key(name):
    """파일 이름의 문항 번호 열쇠 — ('강', 1, '3') · ('번', '20') · None."""
    n = _nfc(name or "")
    m = _RE_S3_KEY_LESSON.search(n)
    if m:
        return ("강", m.group(1), re.sub(r"\s+", "", m.group(2)))
    m = _RE_S3_KEY_NUM.search(n)
    if m:
        return ("번", re.sub(r"\s+", "", m.group(1)))
    return None


def _step3_pdf_exclusions(step3_dir, log=None):
    """Step3 폴더의 PDF 중 조판에 쓰지 않을 것 → {원래 파일명: 이유}.

    PDF 는 편집 원고(hwp/hwpx/docx)의 인쇄본이거나 참고본인 경우가 많다
    (2026-09-12 GDrive Step3 폴더 44개 실측): 같은 이름의 hwp+pdf 짝
    (수특라이트 12강·능률(민) 4과·명일여고1 '1강 1번'), 업체 원본 PDF 에서
    문항을 골라 만든 hwp 옆의 원본 PDF(배재고 '너른터'), 조판본 .indd 를 뽑은
    PDF(서문여고). 둘 다 읽으면 문항이 두 번 들어간다. 그래서
      · 정답/해설본 PDF — 제외 (문제 원고가 아님)
      · 같은 이름의 편집 원고가 있는 PDF — 제외 (그 원고의 인쇄본)
      · 문항 번호('N번'·'N강 M번')가 같은 편집 원고가 있는 PDF — 제외
      · 번호 없는 PDF 인데 폴더에 편집 원고가 있으면 — 제외 (참고본)
    편집 원고가 없는 폴더의 PDF 와, 편집 원고와 번호가 겹치지 않는 번호
    PDF 만 쓴다. 내용 겹침(낱말 80%)으로 가르던 첫 판은 '업체 원본에서
    골라 만든 hwp' 옆 원본 PDF 를 못 걸렀다(원본 쪽이 더 많다) — 파일
    목록만으로 판정하고 PDF 는 열지 않는다(깨진 참고본 PDF 로 멈추지 않게)."""
    try:
        names = sorted(os.listdir(step3_dir))
    except OSError:
        return {}
    pdfs = [n for n in names
            if _is_pdf_name(n) and not n.startswith((".", "~$"))]
    if not pdfs:
        return {}
    sig = []
    for n in names:
        try:
            sig.append((n, os.path.getmtime(os.path.join(step3_dir, n))))
        except OSError:
            sig.append((n, 0))
    key = (os.path.abspath(step3_dir), tuple(sig))
    if key in _S3_PDF_EXCL_CACHE:
        return _S3_PDF_EXCL_CACHE[key]
    srcs = [n for n in names
            if os.path.splitext(n)[1].lower() in _S3_EDIT_EXTS
            and not n.startswith((".", "~$"))]
    src_stems = {os.path.splitext(_nfc(n))[0].strip().lower() for n in srcs}
    src_keys = {_s3_name_key(n) for n in srcs} - {None}
    excl = {}
    for n in pdfs:
        nn = _nfc(n)
        stem = os.path.splitext(nn)[0].strip().lower()
        nkey = _s3_name_key(nn)
        if _RE_S3_ANSWER_NAME.search(nn):
            excl[n] = "정답/해설본 — 문제 원고가 아님"
        elif stem in src_stems:
            excl[n] = "같은 이름의 편집 원고(hwp/docx)가 있음 — 그 원고의 인쇄본"
        elif nkey and nkey in src_keys:
            excl[n] = "같은 문항 번호의 편집 원고가 있음 — 편집 원고 우선"
        elif not nkey and srcs:
            excl[n] = ("번호 없는 PDF — 같은 폴더에 편집 원고(hwp/docx)가 있어 "
                       "참고본으로 봄. PDF 로 조판하려면 편집 원고 없이 넣을 것")
    if log:
        for n, why in excl.items():
            log(f"[파서] step3 PDF 제외: {_nfc(n)} — {why}")
    _S3_PDF_EXCL_CACHE[key] = excl
    return excl


def _absorb_step3_ym(step3_dir, used_files, normal_items, log=None,
                     extract_underline=True, short_items=None, image_dir=None):
    """회차 표기가 **파일 안 헤더**나 **파일명**에 있는 Step3 원고를 흡수한다.

    두 방언을 처리한다 — 어느 쪽도 폴더 연·월로는 코드를 만들 수 없다:
      (1) 파일 안 헤더: "2021년_고1_9월_…_36번" 이 변형문제마다 반복.
          같은 코드의 연속 블록은 **한 문항으로 합친다** (헤더 줄만 제거).
      (2) 파일명: "고1 16년 6월 36번.hwpx" — 보충 폴더처럼 회차가 섞인 경우.

    이미 코드가 잡힌 문항은 건드리지 않는다(정규 경로 우선).
    """
    import unicodedata
    used = {unicodedata.normalize("NFC", p) for p in (used_files or {}).values()}
    have = {str(it.get("code") or "") for it in normal_items}
    have |= {str(it.get("code") or "") for it in (short_items or [])}
    try:
        names = sorted(os.listdir(step3_dir))
    except OSError:
        return

    def _finish(paras):
        paras = _strip_step3_tail_answers(paras)
        paras = _strip_step3_item_numbers(paras)
        paras = _merge_step3_split_choice_numbers(paras)
        paras = _strip_step3_answers_section(paras)
        paras = _strip_step3_answers(paras)
        paras = _strip_step3_type_tags(paras)
        paras = _add_step3_choice_numbers(paras)
        paras = _strip_step3_book_markers(paras)
        paras = _fix_step3_order_label_position(paras)
        paras = _merge_step3_ab_pairs(paras)
        paras = _merge_step3_column_table(paras)
        return paras

    for raw in names:
        fpath = os.path.join(step3_dir, raw)
        if not os.path.isfile(fpath):
            continue
        fname = _nfc(raw)
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".docx", ".hwp", ".hwpx", ".pdf"):
            continue
        if ext == ".pdf" and raw in _step3_pdf_exclusions(step3_dir):
            continue
        # 파일명 방언은 **이미 다른 코드로 쓰인 파일도** 봐야 한다 — 보충
        # 폴더는 회차가 섞여 있어 "36번" 파일이 여러 개고, 폴더 연·월 기준
        # 파일 키(files["36"])는 그중 하나만 남긴다.
        m_fn = _RE_STEP3_FNAME_YM.search(fname)
        fn_code = ("%s%02d%02d" % (m_fn.group(1), int(m_fn.group(2)),
                                   int(m_fn.group(3)))) if m_fn else None
        is_used = unicodedata.normalize("NFC", fpath) in used
        if is_used and (not fn_code or fn_code in have):
            continue    # 정규 경로가 이미 처리 — 내용 추출 생략(비용)
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, extract_underline)
            elif ext == ".pdf":
                paras = _step3_pdf_paragraphs(fpath, extract_underline,
                                              image_dir)
            else:
                paras = _hwp_extract_paragraphs(
                    fpath, extract_underline, exclude_footnotes=True,
                    strip_inline_answers=True, image_dir=image_dir)
        except Exception:
            continue
        if not paras:
            continue

        # (1) 파일 안 헤더 방언 — 같은 코드 연속 블록은 한 문항으로 합친다
        heads = []
        for i, p in enumerate(paras):
            t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
            m = _RE_STEP3_YM_HEAD.match(t.strip())
            if m:
                code = "%s%02d%02d" % (m.group(1), int(m.group(2)),
                                       int(m.group(3)))
                heads.append((i, code))
        if heads:
            for k, (i, code) in enumerate(heads):
                end = heads[k + 1][0] if k + 1 < len(heads) else len(paras)
                if code in have:
                    # 같은 코드가 이어지면 앞 블록에 이어붙인다 (변형문제 묶음)
                    for it in normal_items:
                        if str(it.get("code")) == code and it.get("_ym_absorb"):
                            it["paragraphs"].extend(_finish(paras[i + 1:end]))
                            break
                    continue
                have.add(code)
                normal_items.append({
                    "question_num": code[4:],
                    "code": code,
                    "paragraphs": _finish(paras[i + 1:end]),
                    "_ym_absorb": True,
                })
                if log:
                    log("[파서] step3: 회차통합 '%s' → %s" % (fname, code))
            continue

        # (2) 파일명 방언
        if not fn_code or fn_code in have:
            continue
        have.add(fn_code)
        normal_items.append({
            "question_num": m_fn.group(3),
            "code": fn_code,
            "paragraphs": _finish(paras),
        })
        if log:
            log("[파서] step3: 파일명 회차 '%s' → %s" % (fname, fn_code))

    for it in normal_items:
        it.pop("_ym_absorb", None)


def _normalize_step3_file(paras, fname_nfc, log=None, image_dir=None):
    """회차 통합 Step3 원고 1파일 정규화 — 통짜(textbook) 경로와 같은 순서.

    지문 헤더로 자르기 **전에** 돌린다. 자른 뒤 지문별로 돌리면 머리 블록
    제거(_strip_step3_rights_and_title)가 각 지문의 첫 줄을 워크시트 잔재로
    오인할 수 있다 — 파일 단위가 이 함수들의 전제다.

    2026-09-12 실측(사용자 지적 "서답형 필요 없어"): 분할 경로가 이 정규화를
    통째로 건너뛰어 원고의 유형 섹션 라벨('서 답 형')이 지문 스타일로
    인쇄됐다. 줄 되붙임·각주 번호·표형 선지 병합도 전부 미적용이었다."""
    paras = _strip_step3_decorative_images(paras, fname_nfc, log)
    paras = _strip_step3_leading_junk(paras)
    paras = _strip_step3_trailing_junk(paras)
    paras = _normalize_step3_manuscript(paras, log=log)
    paras = _strip_step3_item_numbers(paras)
    paras = _merge_step3_split_choice_numbers(paras)
    paras = _strip_step3_answers(paras)
    paras = _strip_step3_type_tags(paras)
    paras = _add_step3_choice_numbers(paras)
    paras = _normalize_step3_lines(paras, log)
    paras = _strip_step3_book_markers(paras)
    paras = _fix_step3_order_label_position(paras)
    paras = _merge_step3_ab_pairs(paras)
    paras = _merge_step3_column_table(paras)
    return paras


def _absorb_step3_multi(step3_dir, used_files, normal_items, log=None,
                        image_dir=None, yy=None, mm=None):
    """한 파일에 지문 여러 개가 든 Step3 원고를 헤더로 잘라 항목화.

    yy/mm: 폴더 회차(2자리). 헤더가 회차를 갖지 않는 방언
    (_RE_STEP3_DOTTED_HEAD)에서 지문번호 코드 YYMMQQ 를 만드는 데 쓴다."""
    import unicodedata
    used = {unicodedata.normalize("NFC", p) for p in (used_files or {}).values()}
    have = {str(it.get("code") or "") for it in normal_items}
    try:
        names = sorted(os.listdir(step3_dir))
    except OSError:
        return
    for raw in names:
        fpath = os.path.join(step3_dir, raw)
        if unicodedata.normalize("NFC", fpath) in used:
            continue
        ext = os.path.splitext(raw)[1].lower()
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, True)
            elif ext in (".hwp", ".hwpx"):
                paras = _hwp_extract_paragraphs(fpath, True,
                                                image_dir=image_dir)
            elif ext == ".pdf" and raw not in _step3_pdf_exclusions(step3_dir):
                paras = _step3_pdf_paragraphs(fpath, True, image_dir)
            else:
                continue
        except Exception:
            continue
        heads = []
        for i, p in enumerate(paras or []):
            t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
            m = _RE_STEP3_MULTI_HEAD.match(t.strip())
            if m:
                heads.append((i, m))
        dotted = False
        if not heads and yy and mm:
            # 방언 ② — "QQ번 · 제목". 회차는 폴더 연·월에서 온다.
            def _dotted_heads(rows):
                out = []
                for i, p in enumerate(rows or []):
                    t = (p.get("text") if isinstance(p, dict)
                         else str(p)) or ""
                    m = _RE_STEP3_DOTTED_HEAD.match(t.strip())
                    if m:
                        out.append((i, m))
                return out
            heads = _dotted_heads(paras)
            if len(heads) < _S3_DOTTED_HEAD_MIN:
                heads = []
            else:
                dotted = True
                # 자르기 전에 통짜 경로와 같은 원고 정규화를 태운다 (헤더는
                # 숫자를 포함해 유형 라벨 제거에 걸리지 않는다 — 실측 25/25
                # 생존). 자른 뒤에 돌리면 머리 블록 제거가 지문 첫 줄을 먹는다.
                paras = _normalize_step3_file(paras, _nfc(raw), log, image_dir)
                heads = _dotted_heads(paras)
                if len(heads) < _S3_DOTTED_HEAD_MIN:
                    if log:
                        log("[파서] ⚠️ step3: 정규화 후 지문 헤더가 %d개로 "
                            "줄었다 — 분할 취소(통짜 경로로 넘김)"
                            % len(heads))
                    heads = []
                    dotted = False
        if not heads:
            continue
        for k, (i, m) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(paras)
            if dotted:
                # 장문 묶음("41~42번")은 앞 번호가 지문번호 — 세로 완성본·
                # 가로 병합이 쓰는 대표 코드 관행과 같다.
                q_num = m.group(1)
                code = "%s%s%02d" % (yy, mm, int(q_num))
                label = m.group(3).strip()
            else:
                q_num = m.group(5)
                code = "%s%02d%02d" % (m.group(3), int(m.group(4)),
                                       int(q_num))
                label = "마더텅 %s번" % m.group(1)
            if code in have:
                continue
            have.add(code)
            entry = {
                "question_num": q_num,
                "code": code,
                "paragraphs": paras[i + 1:end],   # 헤더 줄 제외
            }
            if dotted:
                # 쌍방 대조(routing.reconcile_step3)에 '이 파일이 소비됐다'는
                # 신호. 파일명에 문항 번호가 없는 회차 통합 원고라 파일명
                # 기준 대조 말고는 소비를 증명할 길이 없다.
                entry["filename"] = _nfc(raw)
            normal_items.append(entry)
            if log:
                log("[파서] step3: 복수지문 파일 '%s' → %s (%s)"
                    % (_nfc(raw), code, label))
        if dotted and log:
            log("[파서] step3: 회차 통합 원고 '%s' 를 지문 %d개로 분할 "
                "(헤더 'QQ번 · 제목'). 첫 헤더 앞 표제·안내·목차 %d줄은 "
                "지문에 속하지 않아 제외" % (_nfc(raw), len(heads),
                                             heads[0][0]))


# 아잉카 회차 통합 원고의 지문 머리 — "[202609H1_18목적추론_변형]"
# (시험 코드 YYYYMM + 학년 + 문항번호). 지문별 파일("고1 26년 9월 20번.hwp")
# 대신 한 파일에 회차 전체가 오는 원고를 지문 단위로 가르는 앵커다.
_RE_S3_MOCK_CODE = re.compile(
    r'^\[\s*(\d{4})(\d{2})\s*(?:[A-Za-z]\d{0,2})?\s*[_\-]\s*'
    r'(\d{1,3})(?:\s*[~-]\s*(\d{1,3}))?')
_RE_S3_SET_INTRO = re.compile(r'글을\s*읽고|물음에\s*답')


def _split_step3_combined(paras, yy, mm, normal_questions, short_questions,
                          num_to_combined, log=None):
    """회차 전체가 한 파일인 Step3 원고 → 지문별 항목.

    모의고사 Step3 관행은 지문별 파일("고1 26년 9월 20번.hwp")이고, 조판은
    지문마다 유닛을 만들어 `{YYMMQQ}` 지문번호를 얹는다(plan `code`).
    아잉카 변형문제 원고는 25지문이 한 파일에 들어와 파일명 번호 매칭이
    실패했고, 통짜 1유닛이 되어 지문번호도 지문별 묶음도 사라졌다
    (사용자 지적 2026-09-12 "스텝3 지문별로 {260920} 이렇게 들어가고
    지문별로 묶여야지"). 지문 머리의 시험 코드를 앵커로 갈라 같은 모양의
    항목을 만든다 — 코드 줄 자체는 출력에서 뺀다(편집용 표기).

    반환: (normal_items, short_items) 또는 None (앵커 2개 미만).
    """
    heads = []
    for i, p in enumerate(paras):
        m = _RE_S3_MOCK_CODE.match(_s3_text(p))
        if m:
            heads.append((i, m))
    if len(heads) < 2:
        return None
    # 같은 문항번호가 되풀이되는 원고(유형별 변형 8벌씩 — 고2 25년 6월
    # 211문제 아잉카 실측 183줄/25번호)는 '지문 하나 = 코드 하나'가 아니다.
    # 그 관행의 묶음 규칙은 확정된 바 없으니 손대지 않고 통짜로 넘긴다.
    firsts = [int(m.group(3)) for _, m in heads]
    if len(set(firsts)) != len(firsts):
        if callable(log):
            log(f"[파서] step3 지문 코드 {len(heads)}개 중 문항번호 중복 — "
                f"유형별 변형 모음으로 보고 지문별 분할 생략")
        return None
    norm_set = {int(q) for q in (normal_questions or [])}
    short_set = {int(q) for q in (short_questions or [])}
    normal_items, short_items, skipped = [], [], []
    for k, (idx, m) in enumerate(heads):
        # 세트 안내문("※ 다음 글을 읽고, 물음에 답하시오.")은 지문의 일부다
        start = idx
        j = idx - 1
        while j >= 0 and not _s3_text(paras[j]):
            j -= 1
        if j >= 0 and _RE_S3_SET_INTRO.search(_s3_text(paras[j])) \
                and (k == 0 or j > heads[k - 1][0]):
            start = j
        end = heads[k + 1][0] if k + 1 < len(heads) else len(paras)
        # 다음 지문의 안내문은 그쪽 몫
        if k + 1 < len(heads):
            j2 = heads[k + 1][0] - 1
            while j2 > idx and not _s3_text(paras[j2]):
                j2 -= 1
            if j2 > idx and _RE_S3_SET_INTRO.search(_s3_text(paras[j2])):
                end = j2
        body = [p for n, p in enumerate(paras[start:end], start)
                if n != idx]          # 코드 줄 제거
        q1 = int(m.group(3))
        q2 = int(m.group(4)) if m.group(4) else None
        nums = list(range(q1, (q2 or q1) + 1))
        file_key = num_to_combined.get(q1) or (
            f"{q1}~{q2}" if q2 else str(q1))
        item = {"question_num": file_key,
                "code": f"{yy}{mm}{str(q1).zfill(2)}",
                "paragraphs": body}
        if any(n in norm_set for n in nums):
            normal_items.append(item)
        elif any(n in short_set for n in nums):
            short_items.append(item)
        else:
            skipped.append(file_key)
    if not normal_items and not short_items:
        return None
    if callable(log):
        log(f"[파서] step3 회차 통합 원고 지문별 분할: 일반 "
            f"{len(normal_items)}개 / 짤지문 {len(short_items)}개"
            + (f" / 워크북 범위 밖 {len(skipped)}개 제외: "
               f"{', '.join(skipped)}" if skipped else ""))
    return normal_items, short_items


_RE_S3_CHOICE_LEAD = re.compile(r'^[\s\u00a0]*[①-⑮]')


def _normalize_step3_choice_tabs(paras, log=None):
    """선지·열 머리 줄의 탭을 한 칸씩으로 (선행 탭 제거).

    원고가 이중 탭·선행 탭으로 눈대중 정렬한 줄은 행마다 셀 수가 달라
    (같은 문항에서 2개/3개/4개) 조판 열정렬이 열을 어긋나게 잡는다
    (사용자 지적 2026-09-12 "선지 헤더 정렬이 틀어졌어"). 셀 경계를
    한 칸 탭으로 통일해 행마다 같은 열 수가 되게 한다."""
    from core.structure import rules as R
    fixed = 0
    for p in paras:
        if not isinstance(p, dict):
            continue
        t = p.get("text") or ""
        if "\t" not in t:
            continue
        if not (_RE_S3_CHOICE_LEAD.match(t) or R.choice_header_marks(t)):
            continue
        # 선행 공백은 **탭이 섞인 경우에만** 벗긴다 — 공백만으로 눈대중
        # 정렬한 기존 원고(EBS 리딩파워 골든 '   (A)   (B) \t   (C)')의
        # 출력을 바꾸지 않기 위해서다.
        lead = len(t) - len(t.lstrip(" \t\u00a0"))
        drop_lead = "\t" in t[:lead]
        keep, prev_tab = [], False
        for i, c in enumerate(t):
            if i < lead:
                keep.append(not drop_lead)
                continue
            if c == "\t":
                if prev_tab:
                    keep.append(False)      # 이중 탭
                    continue
                prev_tab = True
                keep.append(True)
                continue
            prev_tab = False
            keep.append(True)
        if all(keep):
            continue
        runs = p.get("runs") or []
        if runs and "".join(r.get("t", "") for r in runs) == t:
            out, pos = [], 0
            for r in runs:
                rt = "".join(ch for n, ch in enumerate(r["t"], pos)
                             if keep[n])
                pos += len(r["t"])
                if rt:
                    out.append({**r, "t": rt})
            p["runs"] = out
        p["text"] = "".join(c for c, k in zip(t, keep) if k)
        fixed += 1
    if fixed and callable(log):
        log(f"[파서] step3 선지 탭 정규화: {fixed}줄")
    return paras


def _parse_step3_folder(step3_dir, grade, year, month, normal_questions,
                        short_questions, combined_questions, extract_underline=True,
                        step3_exclude_footnotes=True, log=None, image_dir=None):
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
    # PDF 원고 — 정답본·편집 원고와 중복인 것은 제외 (로그 남김)
    pdf_excl = _step3_pdf_exclusions(step3_dir, log)
    files = {}
    for fname_raw in os.listdir(step3_dir):
        fname = _nfc(fname_raw)
        is_pdf = _is_pdf_name(fname)
        if not is_pdf and not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
            continue
        if is_pdf and fname_raw in pdf_excl:
            continue
        # "고1 25년 9월 20번.hwp" 또는 "고1 25년 9월 41~42번.docx"
        # "번" 뒤 공백 허용 (예: "18번 .hwpx" 사용자 입력 오타 대응)
        m = re.search(r'(\d+(?:~\d+)?)번\s*\.(?:hwpx?|docx|pdf)', fname, re.I)
        if m:
            num_str = m.group(1)
            prev = files.get(num_str)
            if is_pdf and prev and not _is_pdf_name(prev):
                continue    # 같은 번호의 편집 원고(hwp/docx)가 있으면 PDF 는 안 쓴다
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
        elif _is_pdf_name(fpath):
            paras = _step3_pdf_paragraphs(fpath, extract_underline, image_dir,
                                          log)
        else:
            paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                            exclude_footnotes=step3_exclude_footnotes,
                                            strip_inline_answers=True,
                                            image_dir=image_dir)
        paras = _strip_step3_decorative_images(paras, str(file_key), log)  # W77
        paras = _normalize_step3_manuscript(paras, q_num, log)            # W83/W88
        # 보존 가드 스냅샷 — 책 헤더(변형문제/수능특강)는 의도적 제거이므로
        # 스냅샷에서도 제외해 허위 "내용 손실" 경고를 막는다(헤더 외 손실은 그대로 감지).
        paras = _strip_step3_item_numbers(paras)        # W75
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
        paras = _normalize_step3_lines(paras, log)                        # W83
        paras = _normalize_step3_choice_tabs(paras, log)
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

    # 회차 미지정(보충 원고 폴더: year=0, month=0)에서는 폴더 연·월로 만든
    # 코드가 "00036" 같은 쓰레기라 아무 데도 매칭되지 않는다. 그런 항목이
    # 섞이면 코드로 거르는 가로 병합에서는 조용히 무시되지만, q_num 으로
    # 사이클을 만드는 세로 파서에서는 **빈 사이클**로 실체화된다
    # (실측 2026-08-24: 13강 보충 3지문이 5사이클로 조판).
    # 회차 표기는 아래 _absorb_step3_ym 이 파일명/헤더에서 읽는다.
    _no_round = str(year) in ("0", "00") or str(month) in ("0", "00")
    if _no_round:
        if log:
            log("[파서] step3: 회차 미지정 폴더 — 파일명 번호 매칭 생략 "
                "(회차는 파일명/헤더에서 읽는다)")
    else:
        for q in sorted(normal_questions):
            _process_question(q, normal_items)

        for q in sorted(short_questions):
            _process_question(q, short_items)

    # 복수 지문 1파일 형식 (보충 원고) — 파일명에 문항번호가 없고 한 파일에
    # 여러 지문이 들어 있다. 실측 2026-08-07: '11강 없는 지문 변형문제.docx'
    # 안에 "11강 20번 – 고1 16년 11월 31번" 헤더로 지문 2개가 이어져 있어
    # 파일명 규칙(고1 25년 9월 20번.hwp) 기반 탐색으로는 0개가 나온다.
    _absorb_step3_multi(step3_dir, files, normal_items, log,
                        image_dir=image_dir,
                        yy=(None if _no_round else yy),
                        mm=(None if _no_round else mm))

    # 회차 표기가 파일 안 헤더/파일명에만 있는 원고 (폴더 연·월로는 코드를
    # 못 만드는 경우) — 보충 폴더와 회차 통합 원고.
    _absorb_step3_ym(step3_dir, files, normal_items, log,
                     extract_underline=extract_underline,
                     short_items=short_items, image_dir=image_dir)

    # 마더텅 Step3: 파일명에 "N강 M번 YYMMQQ" 형태 (한영고1 마더텅 예전 기출)
    # — 정규 모의고사 normal/short 매칭에 안 잡혔지만 파일은 있을 때
    if not normal_items and not short_items:
        for fname_raw in sorted(os.listdir(step3_dir)):
            fname = _nfc(fname_raw)
            if not (fname.endswith('.hwp') or fname.endswith('.hwpx') or fname.endswith('.docx')
                    or (_is_pdf_name(fname) and fname_raw not in pdf_excl)):
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
            elif _is_pdf_name(fpath):
                paras = _step3_pdf_paragraphs(fpath, extract_underline, None,
                                              log)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                                exclude_footnotes=step3_exclude_footnotes,
                                                strip_inline_answers=True)
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
            if _is_pdf_name(fname):
                if fname_raw in pdf_excl:
                    continue    # 정답본·편집 원고와 중복 (위에서 로그)
            elif not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
                continue
            if _had_number_matching and re.search(r'\d+번\.(?:hwpx?|docx|pdf)', fname, re.I):
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
            elif _is_pdf_name(fpath):
                paras = _step3_pdf_paragraphs(fpath, extract_underline,
                                              image_dir, log)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                                exclude_footnotes=step3_exclude_footnotes,
                                                strip_inline_answers=True,
                                                image_dir=image_dir)
            # W77: 지문에 딸리지 않은 그림(장식) 제외
            paras = _strip_step3_decorative_images(paras, _nfc(fname_raw), log)
            # 선두/꼬리 표제·워터마크 제거 (W17 c16/c11 — 스냅샷 전에)
            paras = _strip_step3_leading_junk(paras)
            paras = _strip_step3_trailing_junk(paras)
            # W83: 원고 워크시트 잔재 + 줄 단위 쪼개짐 + 발문 각주 번호.
            # item_num 없음 — 번호 매칭이 확정 안 된 경로라 '자기 번호' 태그
            # 제거(W88)는 안전하게 생략된다.
            paras = _normalize_step3_manuscript(paras, log=log)
            # W75: 원고 문항 번호 줄 제거 — 스냅샷 **앞**에서 (조판이
            # 번호를 매기므로 의도된 제거. 책 헤더 제거와 같은 취급)
            paras = _strip_step3_item_numbers(paras)
            _raw_words = _step3_content_words(_strip_step3_book_markers(paras))  # 보존 가드 스냅샷(헤더 제외)
            # 표형 선지 번호 셀(①~⑤) 병합 — _strip_step3_answers가 단독 ①~⑤를 제거하기 전에 수행
            paras = _merge_step3_split_choice_numbers(paras)
            paras = _strip_step3_answers(paras)
            paras = _strip_step3_type_tags(paras)
            paras = _add_step3_choice_numbers(paras)
            paras = _normalize_step3_lines(paras, log)                    # W83
            paras = _normalize_step3_choice_tabs(paras, log)
            paras = _strip_step3_book_markers(paras)
            paras = _fix_step3_order_label_position(paras)
            paras = _merge_step3_ab_pairs(paras)
            paras = _merge_step3_column_table(paras)
            _warn_step3_content_loss(_raw_words, paras, _nfc(fname_raw), log)
            # 회차 전체가 한 파일인 원고 — 지문 코드로 지문별 유닛 분할
            split = (_split_step3_combined(
                paras, yy, mm, normal_questions, short_questions,
                num_to_combined, log)
                if (normal_questions or short_questions) else None)
            if split:
                for it in split[0]:
                    it["filename"] = _nfc(fname_raw)
                    normal_items.append(it)
                for it in split[1]:
                    it["filename"] = _nfc(fname_raw)
                    short_items.append(it)
                continue
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
    out = {"normal": normal_items, "short": short_items}
    if pdf_excl:
        # 쌍방 대조(reconcile_step3)·미사용 원고 게이트가 '의도된 제외'로 읽는다
        out["excluded_pdfs"] = sorted(_nfc(n) for n in pdf_excl)
    return out


def _annotate_step3_kinds(items, log=None):
    """core.structure 판정 결과를 단락 dict에 kind/q_code로 병기.

    blank_fill_answer: 괄호 기입란형 줄("(1) 어색한 곳 (____) → 올바르게
    고치기 (____)")을 답란(AnsL)으로. 2026-09-12 사용자 지적 "답란에 답란
    단락스타일 없고" — 이런 줄이 UNKNOWN 으로 남아 지문 스타일로 인쇄됐다
    (고2 26년 9월 실측 128줄 중 서술형 답란 다수). Step3 는 '발문 + 지문 +
    답 쓰는 자리'가 전부인 섹션이라 기입 줄은 답란이 관행이다."""
    try:
        from core.structure import classify_paragraphs
    except Exception as e:
        _LOG.warning("[구조] core.structure 로드 실패 — 주석 생략: %s", e)
        return
    for item in items:
        try:
            results = classify_paragraphs(item.get("paragraphs", []),
                                          {"blank_fill_answer": True})
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


# 파일명이 아니라 **내용(발문)** 으로 스텝을 판별하는 서명 테이블.
# 사용자 지시(2026-08-07): "파일명 토씨 하나에 집착하지 마라. 분석을 해라."
# 실증: 어법선택 하단 문제 원고를 config 는 'Step2 A1 어법선택(객관식).docx'
# 로 기대하는데 회차 폴더는 전부 'Step2 B2 문법 기본 문제.docx' 다. 두 이름은
# 정규화해도 공통 글자가 거의 없어(LCS 비율 0.45 < 0.70) 이름 매칭으로는
# 원리적으로 못 잇는다 — 10개 회차에서 하단 문제가 통째로 누락된 원인.
# 각 항목: (필수 키워드 전부 포함, 제외 키워드 하나도 없음) 을 앞부분에서 검사.
# 값은 시그니처 1개(dict) 또는 후보 여러 개(list) — 앞에서부터 먼저 맞는 것 채택.
_STEP_CONTENT_SIGNATURES = {
    # 하단 문제 발문: "다음 글의 밑줄 친 부분 중, 어법 상 틀린 것을 모두 고르시오"
    # 배제 대상은 어법선택 본문("[ ] 안에서 어법 상 알맞은 것을 고르시오").
    # avoid 에 "[" 를 쓰면 안 된다 — 원고 첫 줄의 회차 표기
    # "고1_2023_11월(경기도)[12월시행]" 에 걸려 10개 중 5개를 놓쳤다.
    "step2_a1_btm": [
        {
            "need": ["밑줄", "어법", "틀린"],
            "avoid": ["알맞은 것을 고르"],
        },
        # 문항별 발문형 원고(23년 6월·9월 'Step2 A1 어법선택에 들어갈 문법 기본
        # 문제.hwpx')는 1번 문항이 네모형("(A), (B), (C)의 각 네모 안에서 어법에
        # 맞는 표현으로…")이라 앞 6단락에 '밑줄/틀린'이 없다 — 위 시그니처만
        # 쓰면 파일이 실재하는데도 '파일 없음'으로 건너뛴다(23년 9월 실측).
        {
            "need": ["네모", "어법"],
            "avoid": ["알맞은 것을 고르"],
        },
    ],
}


# W73 (능률(민) SL1 실증 — 사용자 지적 "지문번호 인식을 못해서 조판이 엉망"):
# 이 원고의 A형 지문 라벨은 대괄호 뒤에 본문 제목이 직결돼 있다 —
# "[본문1]<A Wonder under the Waves>". _RE_KOREAN_BRACKET은 줄 전체가
# 대괄호일 때만("^\[...\]$") 매칭하므로 이 형태를 헤더로 못 봤고,
# _strip_manuscript_headers가 구조 인식 폴백으로 넘어가 **본문1·2를 통째로
# 잘라냈다**(실측: step1_a1 16단락 → 10단락, 5지문 중 3지문만 조판).
# 정규식을 넓히는 대신 **한 단락을 두 단락으로 분리**한다 — 라벨은
# "[본문1]" 단독이 되어 기존 경로가 100% 그대로 소비하고, "<제목>"은
# 다른 스텝(step2_a1/c1)에서 이미 본문 첫 줄로 오는 것과 같은 자리에 선다.
# 대괄호 안이 짧은 라벨일 때만 — 발문형 대괄호("[다음 글의 …]")는 제외.
_RE_BRACKET_TITLE = re.compile(r'^\s*(\[[^\]]{1,20}\])\s*(<[^>]{1,120}>)\s*$')


def _slice_runs(runs, text, start, end):
    """runs를 문자 오프셋 [start, end) 구간으로 잘라 재구성 (밑줄 정보 보존)."""
    out, pos = [], 0
    for r in runs or []:
        t = r.get("t") or ""
        if not t:
            continue
        a, b = pos, pos + len(t)
        pos = b
        lo, hi = max(a, start), min(b, end)
        if lo >= hi:
            continue
        piece = dict(r)
        piece["t"] = t[lo - a:hi - a]
        out.append(piece)
    if not out:
        out = [{"t": text[start:end], "ul": False}]
    return out


def _split_bracket_title_headers(paragraphs):
    """`[본문N]<제목>` 한 단락 → `[본문N]` + `<제목>` 두 단락 (W73).

    매칭되지 않는 단락은 객체 그대로 통과 — 기존 원고에는 영향이 없다."""
    result = []
    for p in paragraphs:
        text = p.get("text") or ""
        m = _RE_BRACKET_TITLE.match(text)
        if not m:
            result.append(p)
            continue
        label, title = m.group(1), m.group(2)
        runs = p.get("runs") or []
        li, ti = text.index(label), text.index(title, m.start(2))
        result.append({"text": label,
                       "runs": _slice_runs(runs, text, li, li + len(label))})
        result.append({"text": title,
                       "runs": _slice_runs(runs, text, ti, ti + len(title))})
    return result


# 문항별 발문형 하단 문제 헤더: "1. 다음 글의 밑줄 친 부분 중, 어법상 틀린 것은? [20]"
# 표준형("1. p2-no.20  (정답 1개)")과 달리 순번·발문·지문번호가 한 줄에 붙어
# 있고 지문번호가 줄 끝 대괄호다. 표준 헤더 정규식(_RE_HEADER_NUM)이 못 잡아
# 파일 전체가 "지문 0개"로 읽혔다(23년 6월 실측).
_RE_BTM_TAIL_HEADER = re.compile(
    r'^\s*(\d{1,2})\s*[\.\)]\s*(.+?)\s*\[(\d{1,3})\]\s*$')
# 발문 안의 정답 개수 표기 "(정답 2개)" → 표준 헤더 꼬리로 옮긴다
_RE_BTM_ANSWER_COUNT = re.compile(r'\(\s*정답\s*(\d+)\s*개\s*\)')


def _normalize_bracket_tail_headers(paragraphs):
    """문항별 발문형 하단 문제 헤더를 표준 형식으로 정규화.

    변환:
        "1. 다음 글의 밑줄 친 부분 중, 어법상 틀린 것은? [20]"
            → "1. p0-no.20"
        "2. … 틀린 것을 모두 고르면? (정답 2개) [21]"
            → "2. p0-no.21  (정답 2개)"

    밑줄형 발문은 섹션 고정 발문과 같은 말이라 버리고, 네모형 등 **다른 유형**의
    발문만 본문으로 남긴다 — 완성본(세로중간본 p167·p196)이 네모형에만 발문을
    따로 인쇄한 것과 같은 구성.

    step2_a1_btm 에서만 호출한다 (다른 섹션 원고의 대괄호 줄에 영향 없음).
    """
    result = []
    for p in paragraphs:
        text = (p.get('text') or '').strip()
        m = _RE_BTM_TAIL_HEADER.match(text)
        if not m:
            result.append(p)
            continue
        prompt = m.group(2).strip()
        if '어법' not in prompt and '밑줄' not in prompt:
            result.append(p)
            continue

        m_cnt = _RE_BTM_ANSWER_COUNT.search(prompt)
        header = "%s. p0-no.%s" % (m.group(1), m.group(3))
        if m_cnt:
            header += "  (정답 %s개)" % m_cnt.group(1)
            prompt = _RE_BTM_ANSWER_COUNT.sub('', prompt).strip()
        result.append({
            "text": header,
            "runs": [{"t": header, "ul": False}],
        })

        # 밑줄형은 고정 발문과 중복 → 버림. 그 외(네모형 등)는 본문으로 유지.
        if '밑줄' in prompt and '네모' not in prompt:
            continue
        result.append({
            "text": prompt,
            "runs": [{"t": prompt, "ul": False}],
        })
    return result


def _same_content_as_used(fpath, used_files):
    """이미 소비한 원고와 **내용이 같은 파일**인가 (W67).

    통합웹 업로드는 원본을 'manuscripts_<원래이름>'으로 저장하고, 엔진이
    같은 폴더에 접두를 뗀 사본('<원래이름>')을 또 만든다 — 폴더에 같은
    원고가 두 벌 있게 된다. 이름이 다르니 '남은 파일'로 보여 A1 보충
    흡수가 통째로 한 번 더 먹었고, 지문이 정확히 2배가 됐다 (사용자 지적
    2026-08-14: "어휘선택1 어휘선택2 어휘선택1"). 이름 규칙이 아니라
    **바이트 동일성**으로 판정한다 — 접두 규칙이 바뀌어도 안 깨진다."""
    try:
        size = os.path.getsize(fpath)
    except OSError:
        return False
    digest = None
    for u in used_files or ():
        try:
            if os.path.getsize(u) != size:
                continue
        except OSError:
            continue
        if digest is None:
            digest = hashlib.md5(open(fpath, "rb").read()).hexdigest()
        try:
            if hashlib.md5(open(u, "rb").read()).hexdigest() == digest:
                return True
        except OSError:
            continue
    return False


def _absorb_a1_supplements(manuscript_dir, used_files, result, short_nums,
                           log=None):
    """A1(어휘선택) 보충 원고를 같은 섹션 키에 이어붙인다.

    본 파일에 빠진 문항을 'Step1 A1 어휘선택(2단계 34번).docx' 처럼 별도
    파일로 덧붙이는 관행 대응. 파일명이 아니라 **첫 줄이 A1 섹션 헤더**
    (`1. 어휘1단계_Hard` / `2. 어휘2단계`)인지로 판별한다."""
    import unicodedata
    used = used_files if used_files is not None else set()
    # 경로 비교는 반드시 NFC 정규화 후 — os.listdir 은 NFD, config 유래
    # 경로는 NFC 라 그냥 비교하면 이미 소비한 본 파일을 '남은 파일'로 보고
    # 통째로 다시 흡수한다 (단락 2배).
    _n = lambda s: unicodedata.normalize("NFC", s)
    used_n = {_n(u) for u in used}
    try:
        names = sorted(os.listdir(manuscript_dir))
    except OSError:
        return
    for name in names:
        fpath = os.path.join(manuscript_dir, name)
        if _n(fpath) in used_n or not os.path.isfile(fpath):
            continue
        if _same_content_as_used(fpath, used):
            continue    # W67: 업로드 원본/엔진 사본 두 벌 — 같은 원고 재흡수 금지
        ext = os.path.splitext(name)[1].lower()
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, False)
            elif ext in (".hwp", ".hwpx"):
                paras = _hwp_extract_paragraphs(fpath, False)
            else:
                continue
        except Exception:
            continue
        if not paras:
            continue
        head = (paras[0].get("text") if isinstance(paras[0], dict)
                else str(paras[0])) or ""
        if not _RE_A1_SECTION.match(head.strip()):
            continue
        for sec_key, sec_paras in _split_a1_sections(paras).items():
            sec_paras = _strip_manuscript_headers(sec_paras, log=None)
            sec_paras = _remove_answer_section(sec_paras, log=None)
            sec_paras = _filter_short_questions(sec_paras, short_nums, log=None)
            cleaned = _clean_empty_lines(sec_paras)
            if not cleaned:
                continue
            tgt = result["steps"].setdefault(
                sec_key, {"filename": name, "question_numbers": [],
                          "paragraph_count": 0, "paragraphs": []})
            tgt["paragraphs"] = (tgt.get("paragraphs") or []) + cleaned
            tgt["paragraph_count"] = len(tgt["paragraphs"])
            tgt["question_numbers"] = _extract_question_numbers(
                tgt["paragraphs"], sec_key)
            if log:
                log(f"[파서] {sec_key}: 보충 원고 '{name}' 흡수 "
                    f"(+{len(cleaned)}단락 → 지문 "
                    f"{len(tgt['question_numbers'])}개)")
        used.add(fpath)
        used_n.add(_n(fpath))


# W68 (11강 실증): 이름으로 고른 파일에 '지문'이 아예 없으면 잘못 고른
# 것이다 — 같은 스텝의 다른 후보 중 지문이 있는 파일로 갈아탄다.
# (11강 빈칸어휘: config가 가리키는 '정답지'에는 정답 단어 목록만 있고,
#  실제 지문+빈칸은 나중에 올라온 '해설지'에 있었다. 파일명 규칙을 또
#  늘리는 대신 '내용에 지문이 있는가'로 자가 교정한다.)
_RE_MANU_ENG_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_MANU_PASSAGE_STEPS = {"step1_a1", "step1_a2", "step1_b1", "step1_b2",
                       "step1_c1", "step1_c2", "step2_a1", "step2_a1_btm",
                       "step2_b1", "step2_c1", "step2_c2"}


def _manu_passage_count(paras):
    n = 0
    for p in paras or []:
        t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
        if len(_RE_MANU_ENG_WORD.findall(t)) >= 12:
            n += 1
    return n


def _manu_core_name(filename):
    """'Step1 C2 빈칸어휘 정답지.docx' → 'step1c2빈칸어휘'.

    업로드 접두(manuscripts_)와 이중 확장자('… 정답지. docx.docx'),
    정답/해설/문제 꼬리를 모두 벗겨 스텝 계열 이름만 남긴다."""
    base = os.path.splitext(unicodedata.normalize("NFC", filename))[0]
    base = re.sub(r"^manuscripts_", "", base)
    base = re.sub(r"(정답지?|해설지?|문제지?)", "", base)
    base = re.sub(r"[^A-Za-z0-9가-힣]", "", base).lower()
    return re.sub(r"docx?$", "", base)


def _find_passage_alternative(manuscript_dir, expected_filename, used_files,
                              extract_ul, log=None):
    """같은 스텝 이름 계열 파일 중 '지문이 있는' 대체 후보 → (path, paras)"""
    core = _manu_core_name(expected_filename)
    if len(core) < 6:
        return None, None
    used = {unicodedata.normalize("NFC", u) for u in (used_files or set())}
    best = None
    try:
        names = sorted(os.listdir(manuscript_dir))
    except OSError:
        return None, None
    for name in names:
        fpath = os.path.join(manuscript_dir, name)
        if unicodedata.normalize("NFC", fpath) in used:
            continue
        if not os.path.isfile(fpath):
            continue
        cand_core = _manu_core_name(name)
        if not (core in cand_core or cand_core in core):
            continue
        ext = os.path.splitext(name)[1].lower()
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, extract_ul)
            elif ext in (".hwp", ".hwpx"):
                paras = _hwp_extract_paragraphs(fpath, extract_ul)
            else:
                continue
        except Exception:                                      # noqa: BLE001
            continue
        n = _manu_passage_count(paras)
        if n == 0:
            continue
        # 정답/해설 표기가 붙은 원고 우선 (config가 그 계열을 가리킨다)
        rank = (1 if re.search(r"(해설|정답)", name) else 0, n)
        if best is None or rank > best[0]:
            best = (rank, fpath, paras)
    if best is None:
        return None, None
    if log:
        log("[선택] 지문 없는 원고 교체: '%s' → '%s' (지문 %d개)"
            % (expected_filename, os.path.basename(best[1]), best[0][1]))
    return best[1], best[2]


# W69 (올포기출 13강 실증): 같은 스텝의 '답안 원고'가 두 세대 공존할 때 —
# 구세대 export는 지문 문장 일부가 통째로 빠지고 "264. perform" 같은 정답
# 목록 줄로 대체돼 있다. config가 가리키는 이름("… 정답지")이 구세대에
# 정확히 일치하면 그쪽이 뽑히고, 새로 올린 온전한 답안 원고("… 해설지")는
# 답지류로 분류돼 조판에서 제외된다 (13강: 빈칸어휘 178줄 / 빈칸어법 416줄이
# 지문 대신 인쇄됨). 파일명이 아니라 **구조**로 고른다 — 정답 목록 줄이
# 있으면 퇴화본, 인라인 빈칸(`125[partial]`) 단락이 온전한 답안본.
_RE_ANS_LIST_LINE = re.compile(
    r"^\s*\d+\s*[.)]\s*[A-Za-z][A-Za-z'\u2019\-]*\s*$")
_RE_INLINE_BLANK = re.compile(r"\d+\s*\[[^\]]{1,40}\]")
_RE_ANSWER_TOKEN = re.compile(r"(정답|해설|답안)")


def _manu_blank_shape(paras):
    """(정답목록줄 수, 인라인 빈칸 단락 수) — 답안 원고의 온전성 지표."""
    n_list = n_inline = 0
    for p in paras or []:
        t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
        if _RE_ANS_LIST_LINE.match(t):
            n_list += 1
        elif _RE_INLINE_BLANK.search(t):
            n_inline += 1
    return n_list, n_inline


def _find_filled_answer_alternative(manuscript_dir, expected_filename,
                                    used_files, extract_ul, cur_inline,
                                    log=None):
    """정답 목록 줄로 퇴화한 답안 원고 → 같은 계열의 온전한 답안 원고.

    후보 조건 (전부 구조 판정):
      - 같은 스텝 계열 이름 (_manu_core_name 포함 관계)
      - 파일명에 답안 토큰(정답/해설/답안) — 문제지로 갈아타 정답이
        통째로 빠지는 사고 방지
      - 정답 목록 줄 0개 + 인라인 빈칸 단락이 현재본 이상
    """
    core = _manu_core_name(expected_filename)
    if len(core) < 6:
        return None, None
    used = {unicodedata.normalize("NFC", u) for u in (used_files or set())}
    best = None
    try:
        names = sorted(os.listdir(manuscript_dir))
    except OSError:
        return None, None
    for name in names:
        fpath = os.path.join(manuscript_dir, name)
        if unicodedata.normalize("NFC", fpath) in used:
            continue
        if not os.path.isfile(fpath):
            continue
        if not _RE_ANSWER_TOKEN.search(unicodedata.normalize("NFC", name)):
            continue
        cand_core = _manu_core_name(name)
        if not (core in cand_core or cand_core in core):
            continue
        ext = os.path.splitext(name)[1].lower()
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, extract_ul)
            elif ext in (".hwp", ".hwpx"):
                paras = _hwp_extract_paragraphs(fpath, extract_ul)
            else:
                continue
        except Exception:                                      # noqa: BLE001
            continue
        n_list, n_inline = _manu_blank_shape(paras)
        if n_list or n_inline < max(cur_inline, 1):
            continue
        if best is None or n_inline > best[0]:
            best = (n_inline, fpath, paras)
    if best is None:
        return None, None
    if log:
        log("[선택] 정답목록 퇴화본 교체: '%s' → '%s' "
            "(인라인 빈칸 단락 %d → %d)"
            % (expected_filename, os.path.basename(best[1]),
               cur_inline, best[0]))
    return best[1], best[2]


def _find_manuscript_file_by_content(manuscript_dir, step_key, used_files,
                                     log=None):
    """이름 매칭이 실패했을 때 폴더의 남은 원고를 **내용**으로 골라낸다."""
    sig = _STEP_CONTENT_SIGNATURES.get(step_key)
    if not sig:
        return None
    sigs = sig if isinstance(sig, list) else [sig]
    used = used_files or set()
    try:
        names = sorted(os.listdir(manuscript_dir))
    except OSError:
        return None
    for name in names:
        fpath = os.path.join(manuscript_dir, name)
        if fpath in used or not os.path.isfile(fpath):
            continue
        if _same_content_as_used(fpath, used):
            continue    # W67: 업로드 원본/엔진 사본 두 벌 — 같은 원고 재선택 금지
        ext = os.path.splitext(name)[1].lower()
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, False)
            elif ext in (".hwp", ".hwpx"):
                paras = _hwp_extract_paragraphs(fpath, False)
            else:
                continue
        except Exception:
            continue
        head = " ".join(
            (p.get("text") if isinstance(p, dict) else str(p)) or ""
            for p in (paras or [])[:6])
        if not head:
            continue
        matched = False
        for s in sigs:
            if any(k not in head for k in s["need"]):
                continue
            if any(k in head for k in s.get("avoid", [])):
                continue
            matched = True
            break
        if not matched:
            continue
        if log:
            log(f"[파서] {step_key}: 내용 매칭으로 '{name}' 채택 "
                f"(파일명 불일치 — 발문 기준)")
        return fpath
    return None


# 직전 _find_manuscript_file 호출의 채택/탈락 근거 (G1 침묵 금지).
# 호출부가 로그로 남긴다 — "어떤 후보가 있었고 왜 이걸 골랐나"가 없으면
# 오선택을 사람이 못 잡는다 (2026-08-08: 정답지를 문제지 대신 골라
# 선지 본문이 통째로 빠졌는데 "원고 결손"으로 보고됨).
_LAST_PICK = {}


# ── 같은 단계 원고가 여럿일 때 최신본 채택 (사용자 지시 2026-09-10) ──────────
# 'Step1 C2 빈칸어휘 정답지.docx' 와 'Step1 C2 빈칸어휘 정답지(개정).docx' 처럼
# 같은 슬롯의 변형본이 폴더에 함께 있으면 **더 최근에 올라온(수정시각이 늦은)**
# 파일로 조판한다. 종전에는 config 파일명과 정확히 같은 파일이 있으면 그것을
# 그대로 써서, 개정본이 옆에 있어도 그대로 구판이 조판됐다 (2026-09-10 실측:
# 모의고사 워크북 26개 회차의 빈칸어휘가 전부 구판 — (개정) 파일은 한 번도
# 채택된 적이 없다).
# 가족 판정은 파일명 구조로 — 개정 표기 토큰(개정/수정/최신/최종/rev/new/v2…)
# 만 벗기고, 슬롯을 가르는 말(정답지/객관식/서술형 등)은 그대로 둔다. 그래서
# '어법선택.docx' 와 '어법선택(객관식).docx' 는 가족이 아니다(상·하단 슬롯).
_RE_REVISION_TOKEN = re.compile(
    r"(?<![A-Za-z0-9가-힣])"
    r"(?:재|\d+\s*차\s*)?"
    r"(?:개정판?|수정본?|최신본?|최종본?|revised|rev|new|final|v\d+|ver\d+)"
    r"\s*\d*"
    r"(?![A-Za-z가-힣])", re.I)


def _manu_family_key(filename):
    """'Step1 C2 빈칸어휘 정답지(개정).docx' → 'step1c2빈칸어휘정답지'.
    개정 표기·공백·괄호·업로드 접두(manuscripts_)만 제거. 확장자 제외."""
    nfc = unicodedata.normalize("NFC", filename or "")
    stem = os.path.splitext(nfc)[0]
    if stem.startswith("manuscripts_"):
        stem = stem[len("manuscripts_"):]
    stem = _RE_REVISION_TOKEN.sub(" ", stem)
    return re.sub(r"[^A-Za-z0-9가-힣]", "", stem).lower()


def _has_revision_token(filename):
    stem = os.path.splitext(unicodedata.normalize("NFC", filename or ""))[0]
    return bool(_RE_REVISION_TOKEN.search(stem))


def _prefer_latest_variant(manuscript_dir, chosen_path, used_files, log=None,
                           step_key=""):
    """chosen_path 와 같은 가족(개정 표기만 다른 파일)이 폴더에 더 있으면
    가장 최근에 수정된 파일을 고른다. → (채택 경로, 밀려난 경로 목록)

    - 후보: 같은 폴더·같은 확장자의 원고 파일 중 가족 키가 같고, 아직 다른
      슬롯에 쓰이지 않은 것. Office 잠금 파일('~$…')·숨김 파일 제외.
      확장자가 다른 쌍(hwp↔docx 재수출)은 밑줄 추출 등 형식 의존 동작이
      바뀔 수 있어 가족으로 보지 않는다 — 종전 동작 유지.
    - 수정시각(mtime)이 가장 늦은 파일 채택. 폴더째 업로드처럼 2초 이내
      동률이면 개정 표기가 있는 쪽, 그래도 같으면 원래 채택본 유지.
    - 밀려난 파일은 호출부가 used_files 에 넣는다 — A1 보충흡수·대체 탐색이
      구판을 다시 먹어 지문이 2배가 되는 사고(W67 변형) 방지.
    """
    import time
    _n = lambda p: unicodedata.normalize("NFC", p)
    used_n = {_n(u) for u in (used_files or set())}
    chosen_n = _n(chosen_path)
    key = _manu_family_key(os.path.basename(chosen_path))
    ext = os.path.splitext(chosen_path)[1].lower()
    if len(key) < 4:
        return chosen_path, []
    try:
        names = os.listdir(manuscript_dir)
    except OSError:
        return chosen_path, []
    fam = []
    for name in names:
        if name.startswith(".") or name.startswith("~$"):
            continue
        if os.path.splitext(name)[1].lower() != ext:
            continue
        fp = os.path.join(manuscript_dir, name)
        if not os.path.isfile(fp):
            continue
        if _manu_family_key(name) != key:
            continue
        if _n(fp) != chosen_n and _n(fp) in used_n:
            continue
        try:
            mt = os.stat(fp).st_mtime
        except OSError:
            continue
        fam.append((fp, mt))
    # 바이트가 같은 사본은 변형본이 아니다 — 업로드 폴더에는 원래 업로드본
    # ('manuscripts_X')과 엔진이 만든 사본('X')이 함께 있다(W67). 이 둘을
    # '같은 단계 원고 2개'로 세면 모든 업로드 잡이 스텝마다 오해를 부르는
    # 로그를 남긴다(2026-09-12 고1 26년 9월 E2E 실측).
    def _md5(fp):
        try:
            with open(fp, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except OSError:
            return None
    ch_md5 = _md5(chosen_path)
    fam = [(fp, mt) for fp, mt in fam
           if _n(fp) == chosen_n or ch_md5 is None or _md5(fp) != ch_md5]
    if len(fam) <= 1 or not any(_n(fp) == chosen_n for fp, _ in fam):
        return chosen_path, []
    newest = max(mt for _, mt in fam)
    top = [fp for fp, mt in fam if newest - mt <= 2.0]
    if len(top) > 1:
        marked = [fp for fp in top
                  if _has_revision_token(os.path.basename(fp))]
        if marked:
            top = marked
    if any(_n(fp) == chosen_n for fp in top):
        pick = chosen_path
    else:
        pick = sorted(top)[0]
    losers = [fp for fp, _ in fam if _n(fp) != _n(pick)]
    if log:
        def _d(fp):
            try:
                return time.strftime("%Y-%m-%d %H:%M",
                                     time.localtime(os.stat(fp).st_mtime))
            except OSError:
                return "?"
        log("[선택] %s: 같은 단계 원고 %d개 → 최신 '%s'(%s) 채택 / 제외: %s"
            % (step_key, len(fam), os.path.basename(pick), _d(pick),
               ", ".join("'%s'(%s)" % (os.path.basename(x), _d(x))
                         for x in losers)))
    return pick, losers


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
        # 원고 세대 방언 — 22년 11월 이후 일부 회차는 섹션 표기를
        # "STEP2 Build Up A. 어법선택.docx" 로 쓴다. 기대 파일명
        # ("Step2 A1 어법선택.docx") 과 공통 토큰이 모자라 매칭 후보 0개가
        # 되고, 그러면 그 회차의 어법 OX·빈칸어법이 통째로 빠진다
        # (실측 2026-08-20: 고1 22년 11월 — 37번이 3개 스텝에서 결손,
        #  게다가 하단용 '(문법 기본 문제)' 파일이 상단 슬롯에 잘못 매칭).
        base = re.sub(r'(?i)build\s*[-_]?\s*up\s*([A-Za-z])\b',
                      r'\1 1', base)
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
        # 반대 방향 — '문제' 슬롯(기대명에 답안 토큰 없음)에는 정답/해설본을
        # 쓰지 않는다. 이 검사가 ratio 분기에만 있어서, 정답지 파일명이 기대명을
        # subsequence 로 품으면 partial 1순위로 뽑혔다.
        #   실측 2026-08-08: 24년 9월 폴더에 '문장배열(순서, 삽입).docx'(문제지)와
        #   '문장배열(순서, 삽입) 정답지.docx' 가 함께 있는데 정답지가 선택돼,
        #   (A)~(G) 선지 본문이 통째로 빠지고 정답만 조판됐다.
        if cand_has_ans and not exp_has_ans:
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

    def _pick(path, why):
        _LAST_PICK.clear()
        _LAST_PICK.update({
            "picked": os.path.basename(path), "why": why,
            "candidates": sorted(
                os.path.basename(x) for x in
                (exact + paren_variant + [c[0] for c in partial]
                 + [c[0] for c in ratio_match])),
        })
        return path

    if exact:
        for c in exact:
            if os.path.splitext(c)[1].lower() == ext_expected:
                return _pick(c, "파일명 일치")
        return _pick(exact[0], "파일명 일치(확장자 다름)")
    # 괄호 변형(같은 base + 양쪽 괄호 있음)을 subsequence partial보다 우선.
    # 예: expected '...(객관식)' 있을 때 폴더에 '...(문법 기본 문제)'와 '...어법선택(괄호 없음)' 둘 다
    # 있으면, 괄호 변형인 '(문법 기본 문제)'가 정답이지 괄호 없는 본체가 아님.
    if paren_variant:
        for fp in paren_variant:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return _pick(fp, "괄호 변형(같은 base)")
        return _pick(paren_variant[0], "괄호 변형(확장자 다름)")
    if partial:
        partial.sort(key=lambda x: (
            -x[1],
            0 if os.path.splitext(x[0])[1].lower() == ext_expected else 1,
        ))
        for fp, sc in partial:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return _pick(fp, "부분 일치 LCS=%d (후보 %d개)"
                             % (sc, len(partial)))
        return _pick(partial[0][0], "부분 일치 LCS=%d (확장자 다름)"
                     % partial[0][1])
    # LCS 비율 매칭 — 파일명에 토씨/공백/단어가 빠지거나 바뀌어도 의미 토큰이 충분히 겹치면 매칭.
    # 예: 기대 '어법선택(객관식)' ↔ 후보 '어법 객관식 문제' (공통 '어법객관식', 비율 86%)
    if ratio_match:
        ratio_match.sort(key=lambda x: (
            -x[2],
            -x[1],
            0 if os.path.splitext(x[0])[1].lower() == ext_expected else 1,
        ))
        for fp, sc, ra in ratio_match:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return _pick(fp, "유사도 %.2f (후보 %d개)"
                             % (ra, len(ratio_match)))
        return _pick(ratio_match[0][0], "유사도 %.2f (확장자 다름)"
                     % ratio_match[0][2])
    _LAST_PICK.clear()
    return None


# ── 공개 API ────────────────────────────────────────────────────────────────

def parse_manuscript_folder(manuscript_dir, config, grade, year, month, log=None,
                            image_dir=None):
    """
    원고 폴더 → content.json dict.

    Args:
        manuscript_dir: 워크북 원고 폴더 경로
        config: config.json dict
        grade: 1 또는 2
        year: 25 (2자리) 또는 2025 (4자리)
        month: 10 등
        log: callable(str) 로그 콜백
        image_dir: 원고 그림(도표/그래프) 추출 폴더. 지정하면 Step3 원고의
            본문 그림을 이 폴더로 뽑아 단락 자리에 그대로 끼운다
            (사용자 지시 2026-08-27). None이면 그림 처리 없음 — 기존 동작.
            **반드시 잡 폴더 등 쓰기 가능한 로컬 경로**를 줄 것 (원고
            폴더가 구글 드라이브일 수 있다).
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
            if found and _LAST_PICK:
                # G1 침묵 금지 — 어떤 후보 중 무엇을 왜 골랐는지 남긴다
                log("[선택] %s: '%s' — %s / 후보: %s"
                    % (step_key, _LAST_PICK.get("picked"),
                       _LAST_PICK.get("why"),
                       ", ".join(_LAST_PICK.get("candidates") or []) or "없음"))
            if not found:
                # 이름으로 못 찾으면 내용(발문)으로 판별 — 파일명 방언 흡수
                found = _find_manuscript_file_by_content(
                    manuscript_dir, step_key, used_files, log)
            if found:
                fpath = found
                filename = os.path.basename(found)
                used_files.add(found)
            else:
                log(f"[파서] 파일 없음, 건너뜀: {filename} "
                    f"(기대 파일명 기준 매칭 후보 0개)")
                continue

        # 같은 단계 원고가 여럿(개정본 등)이면 최신본으로 — 사용자 지시
        # 2026-09-10. 밀려난 구판은 used 에 넣어 뒤 단계(보충흡수·대체
        # 탐색)가 다시 먹지 못하게 하고, 게이트가 '미사용 원고'로 오인하지
        # 않도록 content 에 기록한다.
        fpath, superseded = _prefer_latest_variant(
            manuscript_dir, fpath, used_files, log, step_key)
        filename = os.path.basename(fpath)
        used_files.add(fpath)
        for _sp in superseded:
            used_files.add(_sp)
            result.setdefault("superseded_manuscripts", []).append(
                os.path.basename(_sp))

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

        # W68: 고른 원고에 지문이 하나도 없으면 같은 계열의 다른 파일로 교체
        if (step_key in _MANU_PASSAGE_STEPS
                and _manu_passage_count(paras) == 0):
            alt_path, alt_paras = _find_passage_alternative(
                manuscript_dir, filename, used_files, extract_ul, log)
            if alt_path:
                used_files.add(alt_path)
                fpath, filename, paras = (alt_path,
                                          os.path.basename(alt_path),
                                          alt_paras)
            else:
                log(f"⚠️ [원고이상] {step_key}: '{filename}'에 지문이 없고 "
                    f"대체 원고도 없습니다 — 원고 확인 필요")

        # W69: 답안 원고가 '정답 목록 줄'로 퇴화한 구세대 export면 같은
        # 계열의 온전한 답안 원고로 교체 (13강 빈칸어휘/빈칸어법 실증 —
        # 정답 목록이 지문 대신 조판되던 침묵 사고).
        if (step_key in _MANU_PASSAGE_STEPS
                and _RE_ANSWER_TOKEN.search(
                    unicodedata.normalize("NFC", filename))):
            _n_list, _n_inline = _manu_blank_shape(paras)
            if _n_list >= 3:
                alt_path, alt_paras = _find_filled_answer_alternative(
                    manuscript_dir, filename, used_files, extract_ul,
                    _n_inline, log)
                if alt_path:
                    used_files.add(alt_path)
                    fpath, filename, paras = (alt_path,
                                              os.path.basename(alt_path),
                                              alt_paras)
                else:
                    log(f"⚠️ [원고이상] {step_key}: '{filename}'에 정답 목록 "
                        f"줄 {_n_list}개 — 지문이 정답 목록으로 대체된 "
                        f"원고일 수 있습니다 (대체본 없음, 원고 확인 필요)")

        # 문항별 발문형 하단 문제 헤더("1. …틀린 것은? [20]") → 표준 형식
        # 하단 문제 섹션에서만 — 다른 섹션 원고의 대괄호 줄은 건드리지 않는다
        if step_key == 'step2_a1_btm':
            paras = _normalize_bracket_tail_headers(paras)

        # W73: "[본문1]<A Wonder under the Waves>" → "[본문1]" + "<제목>"
        # 두 단락으로 분리 (정상 원고에는 매치되지 않으므로 안전)
        paras = _split_bracket_title_headers(paras)

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
            # 보충 원고 흡수 — 본 A1 파일에 없는 문항이 별도 파일로 추가되는
            # 관행이 있다 (실증: 고1 23년 11월 'Step1 A1 어휘선택(2단계
            # 34번).docx' — 본 파일의 2단계 섹션에 34번이 없어 어휘선택2에서
            # 통째로 누락됐다). 폴더에 남은 파일 중 첫 줄이 A1 섹션 헤더인
            # 것을 찾아 같은 섹션 키에 이어붙인다.
            _absorb_a1_supplements(manuscript_dir, used_files, result,
                                   short_nums, log)
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
            log=log, image_dir=image_dir,
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
