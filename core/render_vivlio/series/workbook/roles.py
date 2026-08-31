"""워크북 단락 스타일 → **역할** 해석 — 구조로 판정한다.

InDesign 단락 스타일 이름은 계열마다 꼬리가 다르다. 같은 '실전 문제 지문'이

    STEP 03 > 실전 문제 지문 올림포스_      (올포기출)
    STEP 03 > 실전 문제 지문               (본가)
    STEP 03 > 실전 문제 지문 리딩파워        (리딩파워)

처럼 나온다. 파일럿(`pilot/vivliostyle/workbook/render_workbook.py`)은 이 이름을
**리터럴 상수**로 박았고, 그러면 계열이 하나 늘 때마다 상수를 늘려야 한다 —
파서에서 이미 백 번 겪은 그 실패다(`docs/…/feedback_parser_structural_not_pattern`).

여기서는 이렇게 본다:

    ① `STEP NN > ` 접두를 벗겨 **꼬리**만 남긴다 (스텝 번호는 따로 챙긴다)
    ② 꼬리에서 공백·`_`·`S_` 잡음을 지우고 `O/X`→`OX` 로 통일한다
    ③ **역할 어휘가 꼬리 안에 들어 있는지**만 본다 (구체적인 것부터)

교재 이름 같은 변종 꼬리(`올림포스`, `리딩파워`, `수특라이트` …)는 역할 어휘가
아니므로 자연히 무시된다 — **새 방언이 와도 코드를 고치지 않는다.**

못 알아본 스타일은 **조용히 넘기지 않는다.** `resolve()` 가 None 을 돌려주고
호출부(데이터 게이트)가 조판을 세운다. 침묵 유실이 워크북에서 반복된 사고다.
"""
import re
import unicodedata

# `STEP 01 > …` / `STEP01>…` / `Step 3 > …`
_RE_STEP = re.compile(r"^\s*STEP\s*0?(\d)\s*>\s*(.*)$", re.I)

# 라벨(지문 번호) 단락 — `[20]` `{20}` `[실전01]` `{20번}`
_RE_LABEL = re.compile(r"^[\[{]\s*([^\[\]{}]{1,24}?)\s*[\]}]$")


def _norm(s):
    """비교용 정규화 — NFC · 소문자 · 공백/밑줄 제거 · O/X 통일."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("O/X", "OX").replace("o/x", "ox")
    s = re.sub(r"[\s_/·．.]+", "", s)
    return s.lower()


# 역할 어휘 — **구체적인 것부터.** 꼬리에 이 말이 들어 있으면 그 역할이다.
# 새 방언이 생기면 코드가 아니라 이 표에 한 줄 늘린다.
ROLE_WORDS = [
    # ── 하단 문제(공용 3종) ── '선지'·'지문' 이 다른 역할에도 쓰이므로 먼저 본다
    ("q_choice",    ["하단문제선지"]),
    ("q_passage",   ["하단문제지문"]),
    ("q_prompt",    ["하단문제"]),
    # ── STEP1 ──
    ("vocab_sel",   ["어휘선택"]),
    ("box_body",    ["본문박스"]),
    ("ox_item",     ["ox문제"]),
    ("sum_topic",   ["내용정리주제"]),
    ("sum_title",   ["내용정리제목"]),
    ("sum_line",    ["내용정리"]),
    ("b2_q",        ["내용종합번호"]),
    ("b2_choice",   ["내용종합선지"]),
    ("arr_bottom",  ["문장배열하단지문"]),
    ("arr_given",   ["문장배열하단"]),
    ("arr_line",    ["문장배열"]),
    ("blank_kr",    ["빈칸어휘한글", "빈칸어법한글"]),
    ("blank_vocab", ["빈칸어휘"]),
    # ── STEP2 ──
    ("gram_bottom", ["어법선택하단"]),   # 하단 주황 상자(밑줄 친 지문)
    ("gram_sel",    ["어법선택"]),
    ("gram_ox",     ["어법ox"]),
    ("blank_gram",  ["빈칸어법"]),
    ("write_kr",    ["영작배열번호"]),
    ("write_box",   ["영작배열보기"]),
    # ── STEP3 (실전) ──
    ("s3_q",        ["실전문제번호"]),
    ("s3_passage",  ["실전문제지문"]),
    ("s3_bg",       ["배경"]),
    ("s3_cond",     ["조건"]),
    ("s3_bogi",     ["보기"]),
    ("s3_answer",   ["답란"]),
    ("s3_word",     ["영단어"]),
    ("s3_choice",   ["선지"]),
]

# 역할별 성격 — 렌더러가 묻는 것들
KIND = {
    "q_choice": "choice", "b2_choice": "choice", "s3_choice": "choice",
    "q_prompt": "prompt", "b2_q": "prompt", "s3_q": "prompt",
    "blank_kr": "korean", "write_kr": "korean",
}

BASIC = "basic"          # `$BASIC` — 라벨·빈 줄·아이콘 자리
UNKNOWN = None

# 스타일 **이름이 문장인** 경우 — 원고가 안내문을 그대로 스타일명으로 만든 것.
# 실측: `STEP 03 > 다음 글을 읽고` 1,272건(148개 플랜 중 유일한 미인식).
# 리터럴로 박으면 다음 안내문에서 또 걸리므로 **모양으로** 본다:
#   역할 어휘가 하나도 없고 · 한글이 있고 · 띄어쓰기가 있는 긴 꼬리 = 안내문.
_RE_HANGUL = re.compile(r"[가-힣]")


def _looks_like_sentence(tail_raw):
    t = (tail_raw or "").strip()
    return (len(t) >= 6 and " " in t and bool(_RE_HANGUL.search(t)))


def step_of(style):
    """스타일 이름이 말하는 STEP 번호(1·2·3). 없으면 None."""
    m = _RE_STEP.match(style or "")
    return int(m.group(1)) if m else None


def tail_of(style):
    m = _RE_STEP.match(style or "")
    return m.group(2) if m else (style or "")


def resolve(style):
    """스타일 이름 → 역할. 못 알아보면 None(호출부가 세운다)."""
    if not style:
        return BASIC
    s = unicodedata.normalize("NFC", style)
    if s == "$BASIC":
        return BASIC
    tail = _norm(tail_of(s))
    if not tail:
        return BASIC
    # 'S_' 같은 접두 잡음은 _norm 이 이미 지웠다
    for role, words in ROLE_WORDS:
        for w in words:
            if w in tail:
                return role
    if _looks_like_sentence(tail_of(s)):
        return "intro"          # 안내문 — 게이트가 '무름(soft)' 으로 보고한다
    return UNKNOWN


def is_soft(style):
    """모양으로 짚은 것(안내문)인가 — 게이트가 따로 세어 보고하라고."""
    if not style or unicodedata.normalize("NFC", style) == "$BASIC":
        return False
    tail = _norm(tail_of(style))
    for _role, words in ROLE_WORDS:
        if any(w in tail for w in words):
            return False
    return _looks_like_sentence(tail_of(style))


def label_text(text):
    """`[20]` `{실전01}` 같은 **라벨 단락**이면 알맹이를, 아니면 None.

    스타일이 아니라 **모양**으로 본다 — 본가는 `$BASIC` 에 `[20]` 을 담고
    step2_a1 은 `어법 선택` 스타일에 `{20}` 을 담는다(실측). 스타일로 가르면
    둘 중 하나를 놓친다.
    """
    t = (text or "").strip()
    if not t:
        return None
    m = _RE_LABEL.match(t)
    if not m:
        return None
    inner = m.group(1).strip()
    # 알맹이가 문장이면 라벨이 아니다 (예: `[다음 글을 읽고 …]`)
    if len(inner) > 12 or inner.count(" ") >= 3:
        return None
    return inner
