"""content.json → 지문 단위 세그먼트 (매처 실측 검증용 정답 데이터).

같은 지문번호(헤더의 no./bracket 번호)를 가진 섹션 간 유닛 = 같은 지문(양성쌍),
다른 지문번호 = 음성쌍이라는 코퍼스 사실을 이용해 매처의 정밀도/재현율을
실측한다. 헤더 형식은 engines/workbook/parser.py의 _RE_HEADER_NUM 계열과
동일한 일반화 원칙 (라벨 토큰 비의존).

라벨 신뢰성 규칙 (eval에서 사용):
  - 케이스 내 모든 스텝에서 지문번호가 스텝당 유일하면 번호를 신뢰(key=번호 집합).
  - 스텝 안에서 번호가 중복되면(EBS 계열: 유닛별 1,2 재시작) 페이지 마커가 있는
    헤더만 신뢰(key=(페이지, 라벨, 번호)), bracket-only 유닛은 라벨 미상 처리.
"""

from __future__ import annotations

import re


_RE_BRACKET_NUM = re.compile(r"^\s*\[(\d+(?:\s*~\s*\d+)?)\]\s*$")
_RE_PAGE_MARKER = (
    r"(?:"
    r"L\d+(?:\s*[-–—]\s*(?:p\.?\d+|본문\d+))?"
    r"|p\.?\d+"
    r"|U\d+"
    r")"
)
_RE_HEADER_NUM = re.compile(
    r"^\s*"
    r"(?:\d+\s*[\.\)]\s*)?"
    r"(" + _RE_PAGE_MARKER + r")"
    r"\s*[-–—\.]?\s*"
    r"(?:no\.\s*|[A-Za-z]+\.?\s*)?"
    r"(\d+(?:\s*~\s*\d+)?)?"
    r"(?:\s*[가-힣][가-힣0-9A-Za-z\s]{0,30})?"
    r"(?:\s*\([^\)]*\))?"
    r"\s*$"
)
# 페이지 마커 없는 외부지문형 헤더: "1. no.1"
_RE_HEADER_NOP = re.compile(
    r"^\s*\d+\s*[\.\)]\s*no\.\s*(\d+(?:\s*~\s*\d+)?)"
    r"(?:\s*\([^\)]*\))?\s*$"
)


def _num_set(numtxt):
    if not numtxt:
        return frozenset()
    m = re.match(r"(\d+)\s*~\s*(\d+)", numtxt)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and b - a <= 10:
            return frozenset(range(a, b + 1))
    try:
        return frozenset([int(numtxt)])
    except ValueError:
        return frozenset()


class PassageItem(object):
    """한 섹션(스텝) 안의 한 지문 유닛."""
    __slots__ = ("step", "header", "page", "nums", "text", "start", "end")

    def __init__(self, step, header, page, nums, text, start, end):
        self.step = step
        self.header = header    # 헤더 원문 (없으면 None)
        self.page = page        # 페이지 마커 문자열 (없으면 None)
        self.nums = nums        # frozenset[int] 지문 번호 (미상은 빈 집합)
        self.text = text        # 본문 텍스트 (헤더 제외, 단락 join)
        self.start = start      # 헤더 단락 인덱스 (없으면 본문 시작)
        self.end = end          # 마지막 단락 인덱스 (inclusive)

    def __repr__(self):
        return "PassageItem(%s, page=%s, nums=%s, %d chars)" % (
            self.step, self.page, sorted(self.nums), len(self.text))


def _match_header(text):
    """헤더면 (page, nums) 반환, 아니면 None."""
    t = text.strip()
    if not t:
        return None
    m = _RE_BRACKET_NUM.match(t)
    if m:
        return (None, _num_set(m.group(1)))
    m = _RE_HEADER_NOP.match(t)
    if m:
        return (None, _num_set(m.group(1)))
    m = _RE_HEADER_NUM.match(t)
    if m:
        return (m.group(1), _num_set(m.group(2)))
    return None


def _segment_flat(step, paragraphs):
    """헤더 구분자로 flat 단락 리스트를 유닛으로 분할."""
    items = []
    cur = None  # [header, page, nums, texts, start]
    for i, p in enumerate(paragraphs):
        text = p.get("text", "")
        h = _match_header(text)
        if h is not None:
            if cur is not None:
                items.append(_flush(step, cur, i - 1))
            cur = [text.strip(), h[0], h[1], [], i]
            continue
        if cur is not None:
            cur[3].append(text)
    if cur is not None:
        items.append(_flush(step, cur, len(paragraphs) - 1))
    return items


def _flush(step, cur, end):
    header, page, nums, texts, start = cur
    body = "\n".join(t for t in texts if t.strip())
    return PassageItem(step, header, page, nums, body, start, end)


def segment_content_steps(steps):
    """content.json의 steps → PassageItem 리스트.

    step3는 normal/short 블록 단위(발문+지문+선지 통째, question_num을
    번호로 사용), 나머지 스텝은 헤더 구분자로 분할.
    """
    items = []
    for step_key, step in steps.items():
        if not isinstance(step, dict):
            continue
        if step_key == "step3":
            for kind in ("normal", "short"):
                for bi, blk in enumerate(step.get(kind) or []):
                    nums = _num_set(str(blk.get("question_num") or ""))
                    body = "\n".join(
                        p.get("text", "") for p in blk.get("paragraphs") or []
                        if (p.get("text") or "").strip())
                    items.append(PassageItem(
                        "step3_%s_%d" % (kind, bi), None, None, nums,
                        body, 0, 0))
            continue
        paras = step.get("paragraphs")
        if paras:
            items.extend(_segment_flat(step_key, paras))
    return items
