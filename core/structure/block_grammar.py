"""문항 내부 블록 문법 (W38 — 사용자 근본 지적 "발문+지문+요약문/조건/선지
구조를 유형별로 확립하라"의 본선 구현).

문항 = 발문(Q) → (지문 P) → (조건|보기|요약문|선지|답란)* 블록 시퀀스.
블록 진입 마커(<조건>, [요약문], <보기>, 원문자 선지 …)가 열리면 **후속
단락의 라인 판정은 블록 문맥이 제약**한다:

  - <조건>/[조건] 블록 안의 번호 항목("1) 9단어로 빈칸을 완성하시오.")은
    종결어미(시오-체)와 무관하게 조건 항목이다 — W16 D3의 "시오-체 번호
    항목은 발문 유지(v1 관행)" 결정은 W38에서 사용자 기준으로 폐기.
  - [요약문] 헤더와 그 아래 요약 문장 단락은 배경(P-CONTEXT류) 처리.

블록 종료는 구조 신호로만 판정한다: 다음 블록 마커 / 진짜 발문(발문 어휘
선두 또는 항목 번호 시퀀스 이탈) / 그룹 헤더 / 답란(밑줄런·정답·→·우리말).

번호 항목 vs 진짜 발문의 구분 (전 골든 코퍼스 51지점 실측 — W38):
  - 괄호형 번호("1)")는 항상 블록 항목 — 이 파이프라인의 문항 번호 관행은
    점형("N. ", v1 pass 10의 _RE_S3_QNUM)이라 괄호형이 문항일 수 없다.
  - 점형 번호("N. ")는 (a) 발문 어휘 선두(다음/아래/위/윗 + 글/문장/시/…,
    윗글/글의/밑줄/주어진)면 발문(블록 종료), (b) 항목 번호 시퀀스 연속
    (직전 항목 +1)이면 항목 — ebs "1.(A)는 본문에서 찾아 … 쓰시오." /
    "2. 영문의 밑줄 친 부분의 … 영작하시오.", 교과서 "2. 아래의 우리말
    해석을 … 영작하시오."(← '아래의'는 '아래 글'이 아니다) 실증,
    (c) 시퀀스 이탈(다음 문항 번호 22 등)이면 발문(블록 종료) —
    workbook_supp "22. 다음 글의 내용을 한 문장으로 요약하고자 …" 실증.

유형별 기대 블록 시퀀스는 block_sequences.json (scripts/
collect_block_sequences.py가 전 골든 step3 코퍼스에서 실측 수집)에 있고,
validate_unit()이 하드 불변식 위반(발문 2연속·고아 조건 마커·요약문 뒤
배경 문장 0)을 [경고]로 지목한다.
"""
import json
import os
import re

from core.structure import rules as R

# ── 블록 마커 ────────────────────────────────────────────────────────────────
# 요약문 마커 — 대괄호형([요약문]/[요약])·꺾쇠형(<요약문>/<요약>)·단독
# 라인 모두 Sum. W38은 꺾쇠형을 Box(보기 테두리) 관행으로 유지했으나
# W39에서 사용자 확정으로 폐기 — 요약문 마커는 표기 형태와 무관하게
# 대괄호형과 동일한 배경(P-CONTEXT) 블록이다 (W38 미해결 (1) 종결).
SUM_MARKER = re.compile(
    r'^\s*(?:[\[<]\s*요\s*약\s*문?\s*[\]>]|요약문)\s*$')

# 조건 블록 항목 번호: "1)" / "1." (공백 허용) + 불릿 항목
COND_ITEM_NUM = re.compile(r'^\s*(\d{1,2})\s*([.)])\s*')
COND_ITEM_BULLET = re.compile(r'^\s*[•·◦⦁∙ㆍ*]')

# 진짜 발문의 어휘 선두 (번호 뒤) — 명사 결합까지 요구해 "아래의 우리말",
# "영문의 밑줄 친 부분" 같은 조건 항목 문구와 구분한다 (실측 §모듈 주석).
QUESTION_LEAD = re.compile(
    r'^\s*\d{1,3}\s*\.\s*(?:'
    r'(?:다음|아래|위|윗)\s*(?:글|문장|시|중|대화|도표|물음|빈칸|단어)'
    r'|윗\s*글|글의|밑줄\s*친|주어진'
    r'|\(주관식\)|\(서술형\)|서술형'
    r')')

# 영어 발문 (W38 결함 5 — "10. Choose True or False (T/F) …" 실증):
# 문항 번호 + 명령형 동사, 또는 문항 번호 + 대문자 WH-의문사 … ? 형태만.
# 번호 없는 영어 명령문은 지문 문장(Let's look at …)과 구분이 안 되므로
# 발문으로 보지 않는다 (위치·직후 구조 제약 — 문항 번호가 위치 신호).
# 동사 집합: 코퍼스 실측 Choose + 동일 계열 표준 지시동사 소집합.
Q_EN_IMPERATIVE = re.compile(
    r'^\d{1,3}\s*[.]\s*(?:'
    r'Choose|Select|Write|Fill|Complete|Answer|Match|Circle|Arrange'
    r'|Rearrange|Translate|Find|Identify|Underline|Correct|Rewrite'
    r'|Summarize|Read\s+and'
    r')\b')
Q_EN_WH = re.compile(
    r'^\d{1,3}\s*[.]\s*(?:What|Which|Who|Whose|Why|How|When|Where)\b')


def is_english_question(text):
    """영어 지시문 발문 판정 (번호 + 명령형 / 번호 + WH … ?)."""
    t = (text or "").strip()
    if R.HANGUL.search(t):
        return False
    if Q_EN_IMPERATIVE.match(t):
        return True
    if Q_EN_WH.match(t) and "?" in t:
        return True
    return False


def cond_item_take(text, expected_no):
    """<조건> 블록 안에서 발문(Q)으로 1차 판정된 번호 라인의 블록 귀속.

    Returns (take, next_expected):
      take=True  → 조건 항목 (블록 문맥 우선 — kind를 Cond로 강등)
      take=False → 진짜 발문 (블록 종료)
    expected_no: 블록의 다음 항목 번호 기대값 (마커 직후 1).
    """
    if COND_ITEM_BULLET.match(text or ""):
        # 불릿 항목 — 종결어미 무관 블록 항목 (r4c03essay "· 우리말과 같은
        # 의미가 되도록 영작하시오." 시오-체 불릿이 Q로 남던 실증 —
        # validate_sequence 고아 마커 경고가 검출한 잔존 결함)
        return True, expected_no
    m = COND_ITEM_NUM.match(text or "")
    if not m:
        return False, expected_no
    num, delim = int(m.group(1)), m.group(2)
    if delim == ")":
        # 괄호형 번호 = 항목 (문항 번호 관행은 점형 — 모듈 주석 실측)
        return True, num + 1
    # 점형: 발문 어휘 선두는 첫 항목 기대 시점에만 종료 신호로 쓴다 —
    # 시퀀스가 이미 진행 중이면(직전 항목 존재) 번호 연속이 더 강한 신호.
    if num == expected_no:
        if expected_no == 1 and QUESTION_LEAD.match(text):
            return False, expected_no
        return True, num + 1
    return False, expected_no


def cond_item_seen(text, expected_no):
    """비-Q 경로로 조건화된 항목의 번호 시퀀스 전진 (번호 없으면 유지)."""
    m = COND_ITEM_NUM.match(text or "")
    if m:
        return int(m.group(1)) + 1
    return expected_no


# ── 유형별 기대 블록 시퀀스 (실측 데이터 — 조회 전용) ───────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
_SEQ_PATH = os.path.join(_DIR, "block_sequences.json")
_seq_cache = None


def load_block_sequences():
    global _seq_cache
    if _seq_cache is None:
        try:
            with open(_SEQ_PATH, encoding="utf-8") as f:
                _seq_cache = json.load(f)
        except (OSError, ValueError):
            _seq_cache = {}
    return _seq_cache


# ── 블록 시퀀스 하드 불변식 검증 ([경고] 지목 — 침묵 금지) ──────────────────
_NUM_DOT = re.compile(r'^\s*(\d{1,3})\s*\.')
_NUM_PAREN = re.compile(r'^\s*\d{1,2}\s*\)')
# 조건 블록 종료로 보는 종류 (탐색 중단 — 항목 부재 판정 경계)
_COND_SCAN_STOP = ("Q", "Q-INTRO", "GH", "A", "Ans", "Box", "Sum")


def validate_sequence(entries):
    """단락 (kind, text) 시퀀스의 블록 문법 불변식 위반을 [경고]로 반환.

    entries: [(kind, text), ...] — 판정 완료된 시퀀스 (BLANK 포함 가능).
    검사(하드 불변식만 — 전 골든 코퍼스 재분류에서 소음 0 실측 후 채택):
      1. 발문 직후 번호 재시작 발문 — 발문 뒤 본문 없이 곧장 괄호형 번호
         또는 '1.' 재시작 발문 (조건/하위 항목 오분류의 대표 서명 —
         6b66b750 "1)/2) …시오." 실증. 연번 계속(n→n+1)의 정상 발문
         나열은 제외)
      2. 조건 마커 뒤 항목 0 (고아 조건 마커 — 어구 나열 건너뛰기 뒤에도
         항목이 하나도 없을 때만)
      3. 요약문 마커 뒤 배경 문장 0
    """
    warnings = []
    meaningful = [(k, (t or "").strip()) for k, t in entries
                  if k != "BLANK" and (t or "").strip()]
    for x in range(len(meaningful) - 1):
        k1, t1 = meaningful[x]
        k2, t2 = meaningful[x + 1]
        if k1 != "Q" or k2 != "Q":
            continue
        m1 = _NUM_DOT.match(t1)
        restart = bool(_NUM_PAREN.match(t2)) or (
            bool(_NUM_DOT.match(t2)) and _NUM_DOT.match(t2).group(1) == "1"
            and (not m1 or m1.group(1) != "1"))
        if restart:
            warnings.append(
                f"[블록문법] 발문 직후 번호 재시작 발문 — 조건/하위 항목 "
                f"오분류 의심: '{t1[:30]}' → '{t2[:30]}'")
    for x, (k, t) in enumerate(meaningful):
        if k == "Cond" and R.BOX_MARKERS["Cond"].match(t):
            has_item = False
            for k2, t2 in meaningful[x + 1:]:
                if k2 == "Cond":
                    has_item = True
                    break
                if k2 in _COND_SCAN_STOP:
                    break
            if not has_item:
                warnings.append(f"[블록문법] 조건 마커 뒤 항목 0 (고아 "
                                f"마커): '{t[:20]}'")
        if k == "Sum":
            nxt = meaningful[x + 1] if x + 1 < len(meaningful) else None
            if not nxt or nxt[0] != "P-CONTEXT":
                warnings.append(
                    f"[블록문법] 요약문 마커 뒤 배경 문장 0: 다음 라인 "
                    f"'{(nxt[1][:30] if nxt else '(없음)')}'")
    return warnings
