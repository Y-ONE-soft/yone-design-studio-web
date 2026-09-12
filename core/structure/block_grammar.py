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
# [제목] 도 같은 층위다 — '제목 완성형' 서술형의 답 틀(빈칸 낀 제목 한 줄)이
# 마커 뒤에 온다. 요약문과 똑같이 본문과 구분되는 배경 블록이어야 한다
# (사용자 지적 2026-09-12 "여기도 배경 단락스타일로 본문이랑 구분지어야").
SUM_MARKER = re.compile(
    r'^\s*(?:[\[<]\s*요\s*약\s*문?\s*[\]>]|요약문'
    r'|[\[<]\s*제\s*목\s*[\]>])\s*$')
# 마커와 내용이 한 줄로 오는 형태 ("[제목] Attention Literacy: From (A) __ …").
# 단독 마커 줄만 보던 판정은 이 형태를 놓쳐 지문 스타일로 인쇄했다.
SUM_INLINE = re.compile(
    r'^\s*(?:[\[<]\s*요\s*약\s*문?\s*[\]>]|[\[<]\s*제\s*목\s*[\]>])\s*\S')

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


# ── 유형별 기대 블록 시퀀스 (실측 데이터) ───────────────────────────────────
# W38에서는 validate_sequence 전용이었으나 W39부터 **슬롯 배정의 입력**이다
# (사용자 근본 지적: "유형별 시퀀스를 만들어 놓고 왜 검증에만 쓰냐").
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


# ── 유형 주도 하향식 슬롯 배정 (W39) ────────────────────────────────────────
# 발문 taxonomy 유형 → 기대 블록 시퀀스(실측) → 발문 이후 단락을 기대
# 슬롯에 '형태 신호'로 배정한다. 마커 문구("주어진 글/문장/…")는 유형이
# 미분류일 때의 프라이어로 강등 — 미지의 마커 표현이어도 유형·위치·형태가
# 맞으면 배정된다 (실증: 87번 "주어진 문장" ❮…❯ — '주어진 글'은 되고
# '주어진 문장'은 안 되던 것이 어휘 매칭의 증거였다. W39 전환 케이스).

# 실측 신뢰 최소 표본 (이하이면 유형 실측을 신뢰하지 않고 폴백)
_SEQ_MIN_UNITS = 3
# '주어진 블록' 기대 판정: 관측 시퀀스 중 발문 직후 토큰이 PC인 비율
_GIVEN_MIN_FRACTION = 0.5
_given_cache = {}

# 유형 미분류 발문의 마커 프라이어 — '주어진 글/문장/문단/단락' 참조만.
# '주어진 표현/어구'는 <보기> 박스 내용물 참조(재배열·빈칸 완성 발문)라
# 주어진 블록이 아니고, 단독 '들어가기에'는 빈칸 발문("빈칸에 들어가기에
# 적절한 것은?")과 겹친다 (0a5da924/r2c02rp15 전수 diff 실측 오배정 3+1건).
GIVEN_PRIOR = re.compile(r'주어진\s*(?:글|문장|문단|단락)')


def _given_fraction(code):
    """해당 유형의 관측 시퀀스 중 'Q PC …' 시작 비율 (실측 부재 시 None)."""
    entry = (load_block_sequences().get("sequences") or {}).get(code)
    if not entry:
        return None
    total = hit = 0
    for seq, cnt in (entry.get("observed") or {}).items():
        toks = seq.split()
        total += cnt
        if len(toks) >= 2 and toks[0] == "Q" and toks[1] == "PC":
            hit += cnt
    if total < _SEQ_MIN_UNITS:
        return None
    return hit / total


def expects_given_block(q_code, q_text=""):
    """발문이 '주어진 블록'(발문 직후 배경 단락 슬롯)을 기대하는가.

    1차(유형 실측): block_sequences.json — 해당 leaf의 관측 시퀀스 중
      발문 직후 PC 비율 >= 0.5 (표본 3+). 2차(실측 부재 폴백): 문장삽입/
      순서배열 계열 코드 규칙. 3차(유형 미분류 프라이어): 발문 마커 문구.
    """
    if q_code:
        if q_code not in _given_cache:
            frac = _given_fraction(q_code)
            if frac is None:
                _given_cache[q_code] = bool(
                    R.P_CONTEXT_Q_CODES.match(q_code))
            else:
                _given_cache[q_code] = frac >= _GIVEN_MIN_FRACTION
        return _given_cache[q_code]
    return bool(GIVEN_PRIOR.search(q_text or ""))


# 주어진 블록 후보의 '형태' 신호: 장식 래퍼(❮❯/〈〉/따옴표류)를 벗긴
# 몸통이 영어 콘텐츠(한글 없음 + 영문 시작 + 완결부호 또는 충분 길이).
# W59: 주어진 문장 표기의 화살표/불릿 접두(▶ ► ▸ ➤ →)도 래퍼로 벗긴다 —
# 비상(황) 실증: "▶ This allowed me to…"가 _GIVEN_BODY_START(영문/숫자
# 시작)를 못 넘겨 문장삽입 배경(주어진 문장 박스) 미부여 [경고]가 났다.
_GIVEN_WRAP = '❮❯〈〉《》«»‹›<>[]()"\'“”‘’▶►▸➤➔→⇒• \t'
_GIVEN_BODY_START = re.compile(r'^[A-Za-z0-9"\'“‘]')


# W76: 주어진 문장을 **대괄호 라벨**로 표기하는 원고 ("[주어진 문장] If not, …").
# 라벨이 몸통 앞에 붙어 있어 한글 검사에 걸려 배경 배정이 통째로 실패했다
# (수특라이트 13강 실증 — 게이트 [문장삽입배경] 경고). 라벨은 마커지 내용이
# 아니므로 형태 판정 전에 벗긴다 (GIVEN_PRIOR 와 같은 어휘 계약).
GIVEN_LABEL_PREFIX = re.compile(
    r'^\s*[\[\(〈《<【]\s*주어진\s*(?:글|문장|문단|단락)\s*'
    r'[\]\)〉》>】]\s*')


def is_given_block_form(text, short_only=False):
    """주어진 블록(문장/글) 후보 형태 판정 — 문장 완결부호 필수 (구조
    라벨 "[Unit 09 - Practice 01]" 등 배제, r7c16 전수 diff 실측).
    short_only=True(마커 프라이어 경로)는 짧은 단문/래퍼 감싸짐만 수용 —
    지문 전체 오배정 방지."""
    raw = GIVEN_LABEL_PREFIX.sub("", (text or "").strip()).strip()
    if not raw:
        return False
    wrapped = raw[0] in '❮〈《«‹"“‘['
    t = raw.strip(_GIVEN_WRAP)
    if not t or R.HANGUL.search(t):
        return False
    if not _GIVEN_BODY_START.match(t):
        return False
    if short_only and not wrapped and len(t) > 220:
        return False
    return bool(R.P_SENTENCE_END.search(t))


# ── T/F 선택 행 (W39 결함 5) ────────────────────────────────────────────────
# 발문이 진위 선택(True or False / T,F / O,X)을 지시하면, 뒤따르는
# "N) 문장 (T/F)" 행들은 선지(C)다 — 유형(발문의 선택 지시) + 위치(발문
# 이후) + 형태(번호 괄호 + 선택 표기 꼬리)의 하향식 배정 (111번 실증:
# 지문 스타일로 인쇄되던 침묵 지점).
TF_Q_REF = re.compile(
    r'True\s+or\s+False|\(\s*T\s*/\s*F\s*\)|\(\s*O\s*/\s*X\s*\)'
    r'|T\s*/\s*F|O\s*/\s*X', re.I)
_TF_ROW = re.compile(
    r'^\s*\d{1,2}\s*\)\s*.+\(\s*(?:T\s*/\s*F|O\s*/\s*X|True\s*/\s*False)'
    r'\s*\)\s*\.?\s*$', re.I)


def is_tf_question(q_text):
    """발문의 진위 선택 지시 여부 (영/한 무관 — 유형 신호)."""
    return bool(TF_Q_REF.search(q_text or ""))


def is_tf_choice_row(text):
    """진위 선택 행 형태: 번호 괄호 + 문장 + (T/F)/(O/X) 꼬리."""
    return bool(_TF_ROW.match(text or ""))


# ── 조건 블록 내용물: 단어 나열 (W39 결함 3 — 사용자 확정) ─────────────────
# 조건 항목("다음 단어를 한 번씩 사용하여 배열하시오")이 참조하는 주어진
# 단어 나열은 조건 블록의 내용물이다 — v1 pass 15의 '어구 나열은 지문
# 유지' 관행(W16 D3 이식)은 W39에서 사용자 기준으로 폐기. 형태: 슬래시
# 구분 나열 또는 쉼표 3+ 나열, 한글 없음, 문장 완결부호 없음(영문 문장
# 오염 방지 — 나열은 마침표로 끝나지 않는다).
_COND_WORDLIST_SLASH = re.compile(r'\S\s*/\s*\S')
_COND_WORDLIST_COMMA = re.compile(r'(?:,[^,]*){3,}')


# 답란 라벨 라인 ("주제문:" / "요지:" — 콜론으로 끝나는 짧은 라벨 단독
# 라인, 내용 없음). W39 결함 4의 답란 쌍 식별 + 조건 블록 한글 흡수 제외.
ANS_LABEL = re.compile(r'^\s*[가-힣A-Za-z()（）\s]{1,12}[:：]\s*$')

# 괄호 라벨 답란 라인 ("(A) ______" / "(B) : ______") — W40 결함 5:
# W39 콜론형(ANS_LABEL 쌍) 한정을 괄호 라벨형까지 확장. 위치 신호(보기/
# 조건 블록 뒤) + 형태 신호(괄호 라벨 + 밑줄 빈칸 런)가 모두 맞을 때만
# 답란(AnsL)이다 — 0a5da924 실증: <보기 B> 아래 "(A) ___"가 Box 전파의
# 무한글 흡수에 삼켜져 보기 스타일로 인쇄됐다. 형태: 라벨 1~3자.
ANS_PAREN_BLANK = re.compile(
    r'^\s*[(（]\s*[A-Za-z가-힣0-9]{1,3}\s*[)）]\s*[:：]?'
    r'[\s ]*_{3,}[\s _]*[.,]?\s*$')


def is_cond_wordlist(text):
    t = (text or "").strip()
    if not t or R.HANGUL.search(t):
        return False
    if R.P_SENTENCE_END.search(t):
        return False
    if _COND_WORDLIST_SLASH.search(t):
        return True
    return bool(_COND_WORDLIST_COMMA.search(t))


# ── 후치 <보기> 캡션 (2026-08-25 실증) ──────────────────────────────────────
# 원고(hwp)의 보기 상자는 캡션이 표 **뒤**에 추출되는 경우가 있어 스트림이
#   confident / appreciate / stylish /     ← 보기 내용
#   the way / feel / help                  ← 보기 내용
#   보기                                   ← 마커 (내용 뒤!)
# 순서로 온다. 마커 뒤만 보는 전방 전파는 이 형태에서 세 가지를 동시에
# 틀린다: ① 앞의 어구 나열을 직전 <조건> 블록이 흡수해 조건 상자에 인쇄
# ② 보기 상자는 빈 채로 인쇄 ③ 마커 뒤 답란을 보기 스타일로 흡수.
# 방향은 표기가 아니라 내용의 위치로 정한다 — 마커 뒤에 보기 내용이 없고
# 앞에 붙어 있으면 그 앞이 이 마커의 내용이다.
BOX_CONTENT_MAX_LEN = 120


def is_box_content(text):
    """보기 상자 내용 줄인가 — 어구 나열(슬래시/쉼표 3+) 또는 (a) 항목."""
    t = (text or "").strip()
    if not t or len(t) > BOX_CONTENT_MAX_LEN:
        return False
    if R.COND_ITEM_START.match(t):
        return False          # 조건 항목(불릿/번호)은 보기 내용이 아니다
    if R.BOX_MARKERS["Box"].match(R.norm_brackets(t)) \
            or R.BOX_MARKERS["Cond"].match(R.norm_brackets(t)):
        return False
    if R.HANGUL.search(t):
        return bool(R.BOX_ITEM_LABEL.match(t))
    if "_" in t:
        return False          # 기입란(답란)은 보기 내용이 아니다
    return bool(R.BOX_WORDLIST.search(t))


def trailing_box_captions(texts):
    """후치 보기 캡션 위치 목록 [(marker_idx, start_idx)].

    texts: 유의 단락 텍스트 목록(빈 줄 제외한 것). marker_idx 의 '보기'
    라벨이 start_idx..marker_idx-1 을 내용으로 갖는다는 뜻 — 호출자는 그
    구간을 Box 로 되돌리고 라벨을 start_idx 앞으로 옮긴다."""
    out = []
    for i, t in enumerate(texts):
        bt = R.norm_brackets((t or "").strip())
        # BOX_MARKERS["Box"] 는 일반 꺾쇠 마커(<한글 1~4자>)까지 받는다 —
        # <조건>/<요약문>도 걸린다. 판정 순서(Cond·Sum 선점)를 여기서도
        # 그대로 지킨다 (585a48a5 실증: <조건>이 보기 캡션으로 옮겨졌다).
        if R.BOX_MARKERS["Cond"].match(bt) or SUM_MARKER.match(bt):
            continue
        if not R.BOX_MARKERS["Box"].match(bt):
            continue
        if i + 1 < len(texts) and is_box_content(texts[i + 1]):
            continue          # 정상(전치) 마커 — 기존 전방 전파에 맡긴다
        start = i
        while start - 1 >= 0 and is_box_content(texts[start - 1]):
            start -= 1
        if start != i:
            out.append((i, start))
    return out


# 요약 빈칸 선택형의 요약문 형태 (W40 결함 4 보조): 짧은 영어 문장 +
# 인라인 (A)·(B) 빈칸 — 라벨 뒤가 공백/NBSP(" (A) ") 또는 밑줄 런
# ("(A)__________"). 둘 다 코퍼스 실측 표기 (0a5da924 / r10c21rp11).
# 네모 어법 선택형 지문의 "(A)[many / far]"는 라벨 뒤 대괄호가 붙어
# 매치되지 않고, 전체 지문은 길이 상한(400)에 걸린다 — 요약문(배경)과
# 지문(P)을 형태로 구분하는 신호.
_SUM_BLANK_A = re.compile(r'\(\s*A\s*\)[\s_]')
_SUM_BLANK_B = re.compile(r'\(\s*B\s*\)(?:[\s_]|$)')


def is_summary_blank_form(text, max_len=400):
    """발문 직후 단락이 '요약문 + 인라인 (A)/(B) 빈칸' 형태인가."""
    t = (text or "").strip()
    if not t or len(t) > max_len or R.HANGUL.search(t):
        return False
    return bool(_SUM_BLANK_A.search(t) and _SUM_BLANK_B.search(t))


# 슬롯을 소비하지 않는 구조 라벨 (발문과 본문 사이에 끼는 단독 대괄호
# 라인 — SRC 마커/유형 마커와 같은 층위. [보기]/[조건]/[요약문]은 kind가
# Cond/Box/Sum이라 여기 오지 않는다)
BRACKET_LABEL = re.compile(r'^\[[^\[\]]{1,40}\]$')


def given_slot_scan(kind, text, prior_only=False):
    """발문 직후 첫 유의 단락의 주어진 슬롯 배정 판정.

    Returns: "assign"(배정) / "skip"(슬롯 부재 — 관측 변형: 선지/순서라벨/
    마커 직행. 프라이어 경로의 형태 불일치 포함 — 프라이어는 경고 없음) /
    "warn"(유형이 기대하는 슬롯의 배정 불가 — 침묵 강등 금지, [경고]).
    """
    t = (text or "").strip()
    if kind in ("P", "P-CONTEXT"):
        if prior_only and kind == "P" \
                and not is_given_block_form(t, short_only=True):
            return "skip"    # 프라이어만으론 지문 전체를 배경화하지 않음
        return "assign"
    if kind in ("UNKNOWN", "K", "Word") \
            and is_given_block_form(t, short_only=prior_only):
        return "assign"
    if kind in ("C", "Cond", "Box", "Sum", "Q", "Q-INTRO", "GH", "A",
                "Ans", "AnsL") or R.P_ORDER_LABEL.match(t) or prior_only:
        return "skip"
    return "warn"


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
        if k == "Cond" and R.BOX_MARKERS["Cond"].match(R.norm_brackets(t)):
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
