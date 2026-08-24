"""원고 편집용 잔재(worksheet 부속물) 구조 판정.

원고는 '편집용 워크시트'이고 조판물은 '완제품'이다. 원고에는 완제품이
자기 계약으로 다시 만드는 부속물이 섞여 있다 — 페이지 머리글, 유형 발문,
답 기입란. 형식(리터럴)이 아니라 **구조**로 가른다: 원고마다 문구·번호·
구분자가 매번 다르기 때문이다 (2026-08-24 능률(민) SL1 실증 — 기존
`^Q[.:]` 화이트리스트가 '01  문장배열   …쓰시오.' 형식을 통과시켜 발문·
답란·머리글이 11개 페이지에 그대로 인쇄됐다).

세 부류 모두 "완제품이 같은 자리를 자기 스타일로 채운다"는 공통 성질을
가진다. 판정은 각 부류의 **불변 구조**만 본다:

  RUNNING_HEAD  파이프(|)로 필드를 나눈 메타 정보 막대. 문장이 아니고
                (종결 문장부호·서술어 없음) 짧다. 본문/선지에는 파이프가
                쓰이지 않는다.
  PROMPT        한국어 지시문 — '…하시오/하세요'로 끝나는 명령형 한 줄.
                유형 번호("01 문장배열")가 앞에 붙든 말든 종결형이 정체다.
  ANSWER_BLANK  라벨 + 밑줄 런으로만 이뤄진 기입란. 밑줄을 걷어내면
                남는 것이 짧은 라벨뿐이다(=쓸 내용이 없는 줄). 문장 속
                빈칸("the p______ of an octopus")은 남는 텍스트가 문장이라
                걸리지 않는다.
"""
import re

RUNNING_HEAD = "running_head"
PROMPT = "prompt"
ANSWER_BLANK = "answer_blank"

_RE_PIPE = re.compile(r"[|｜¦]")
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_SENT_END = re.compile(r"[.?!。？！]\s*$")
# 한국어 지시문 종결형 — '쓰시오/고르시오/하시오/…하세요/…십시오'
_RE_PROMPT_END = re.compile(r"(?:시오|세요|십시오)\s*[.?!]?\s*$")
_RE_CHOICE_LEAD = re.compile(r"^\s*[(\[]?\s*[A-Za-z가-힣]\s*[)\]]")
_RE_MARKER_LEAD = re.compile(r"^\s*[①-⑳ⓐ-ⓩⒶ-Ⓩ㉠-㉭]")
_RE_UNDERSCORE_RUN = re.compile(r"[_＿]{6,}|[‾﹍﹎＿]{6,}")
_RE_ENG_WORD3 = re.compile(r"[A-Za-z]{3,}")

_MAX_HEAD_LEN = 150
_MAX_BLANK_LABEL_LEN = 24


def _fields(text):
    return [f.strip() for f in _RE_PIPE.split(text) if f.strip()]


def is_running_head(text):
    """원고 페이지 머리글 — 파이프로 나뉜 메타 필드 막대.

    "공통영어2 NE능률(민병천)  |  Special Lesson 1. …  |  본문 1"
    "WORKSHEET  |  문장배열 + 문장삽입"
    문장(종결부호)·선지 마커가 있으면 본문이므로 제외한다."""
    t = (text or "").strip()
    if not t or len(t) > _MAX_HEAD_LEN:
        return False
    if len(_RE_PIPE.findall(t)) < 1:
        return False
    fields = _fields(t)
    if len(fields) < 2:
        return False
    # 머리글은 '메타 정보'라 최소 한 필드가 이름 길이를 갖는다. 한두 글자
    # 필드만 있는 줄은 표의 열 머리다 ("O | X" — 본문 O/X 선택지, 실측
    # 오탐). 내용 표를 머리글로 오인하지 않도록 길이 하한을 둔다.
    if max(len(f) for f in fields) < 4 or len(t) < 8:
        return False
    if _RE_SENT_END.search(t) or _RE_PROMPT_END.search(t):
        return False
    return not _RE_MARKER_LEAD.match(t)


def is_prompt(text):
    """한국어 지시문 한 줄 — '…시오/…세요'로 끝나는 명령형.

    유형 번호·유형명 접두("01  문장배열   …")는 있어도 되고 없어도 된다.
    영어 지문·선지는 종결형이 다르므로 걸리지 않는다."""
    t = (text or "").strip()
    if not t or not _RE_PROMPT_END.search(t):
        return False
    if not _RE_HANGUL.search(t):
        return False
    return not _RE_CHOICE_LEAD.match(t)


def is_answer_blank(text):
    """답 기입란 — 라벨 + 밑줄 런만으로 이뤄진 줄.

    "정답 순서  ______________" / "정답 번호  ______________"
    밑줄을 지우고 남는 것이 짧은 라벨(한글)뿐일 때만 참. 문장 안의 밑줄
    빈칸은 남는 텍스트가 문장이라 거짓."""
    t = (text or "").strip()
    if not t or not _RE_UNDERSCORE_RUN.search(t):
        return False
    rest = _RE_UNDERSCORE_RUN.sub(" ", t).strip()
    rest = re.sub(r"\s+", " ", rest)
    if len(rest) > _MAX_BLANK_LABEL_LEN:
        return False
    if _RE_ENG_WORD3.search(rest):
        return False
    if _RE_SENT_END.search(rest):
        return False
    return bool(_RE_HANGUL.search(rest)) or rest == ""


def classify(text):
    """세 부류 중 하나면 그 이름, 아니면 None."""
    if is_running_head(text):
        return RUNNING_HEAD
    if is_answer_blank(text):
        return ANSWER_BLANK
    if is_prompt(text):
        return PROMPT
    return None
