"""
동형모의고사 원고 파서

hwpx/docx 원고 -> 단락 분류 -> content.json

원고 구조:
  첫 줄: "객관식 25, 서술형 6" (메타 정보)
  [14강 4번] / [Test 1 13번] / [2027수능특강(영어) 3강 1번]  (헤더)
  도입문 (다음 글을 읽고...)
  지문 (영어 본문)
  선지 (①②③④⑤)
  서술형: <조건>, <보기>, 답란

단락 데이터 구조:
  {"text": str, "runs": [{"t": str, "ul": bool}], "pstyle": str}
"""

import json
import os
import re
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s)


# Dingbat 원문자(U+2780~U+2784) → 표준 원문자(U+2460~U+2464)
# 둘 다 BMP 1글자라 길이 동일 → runs 오프셋/text 동기 안전
_DINGBAT_CIRCLED_TABLE = {
    0x2780: "\u2460",  # ➀ → ①
    0x2781: "\u2461",  # ➁ → ②
    0x2782: "\u2462",  # ➂ → ③
    0x2783: "\u2463",  # ➃ → ④
    0x2784: "\u2464",  # ➄ → ⑤
}


def _normalize_text(s):
    """원문자/불릿 메타문자 정규화. 길이 보존(runs 오프셋 안전)."""
    if not s:
        return s
    s = s.translate(_DINGBAT_CIRCLED_TABLE)
    # InDesign 메타문자 '^8' → '• ' (불릿 + 공백 1칸). 2글자 → 2글자.
    s = s.replace("^8", "\u2022 ")
    return s


def _normalize_paragraphs_text(paras):
    """단락의 text와 runs[].t에 텍스트 정규화 적용."""
    for p in paras:
        if "text" in p:
            p["text"] = _normalize_text(p["text"])
        runs = p.get("runs")
        if runs:
            for r in runs:
                if "t" in r:
                    r["t"] = _normalize_text(r["t"])
    return paras


# ── 외부 파서 임포트 ──────────────────────────────────────────────────────────

def _extract_paragraphs(filepath, extract_underline=True):
    """hwpx/docx 파일에서 단락 추출 (밑줄 포함).

    동형모의고사는 문제지이므로 미주/각주(정답+해설)는 항상 제외.
    """
    filepath = os.path.abspath(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".hwpx":
        from engines.workbook.parser import _hwpx_extract_paragraphs
        return _hwpx_extract_paragraphs(filepath, extract_underline=extract_underline, exclude_footnotes=True)
    elif ext == ".docx":
        from engines.workbook.parser import _docx_extract_paragraphs
        return _docx_extract_paragraphs(filepath, extract_underline=extract_underline)
    elif ext == ".hwp":
        from engines.workbook.parser import _hwp_is_hwpx, _hwpx_extract_paragraphs
        if _hwp_is_hwpx(filepath):
            return _hwpx_extract_paragraphs(filepath, extract_underline=extract_underline, exclude_footnotes=True)
        from engines.workbook.parser import _hwp_extract_paragraphs
        return _hwp_extract_paragraphs(filepath, extract_underline=extract_underline, exclude_footnotes=True)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")


# ── 단락 분류 ─────────────────────────────────────────────────────────────────

# 헤더 패턴: [14강 4번], [Test 1 13번], [2027수능특강(영어) 3강 1번], [4과]
# 워크북 형식만 — 출처 표기 ([올림포스...], [22번] 등)는 헤더 아님.
_RE_HEADER = re.compile(
    r"^\[(?:\d+강|\s*Test\s*\d+|\d+과|2\d{3}수능|수능특강)[^\]]*\d[^\]]*\]\s*$",
    re.UNICODE
)

# 출처 표기 단독 단락 (skip) — 상일/배재 원고에서 발문 다음 줄에 단독으로 등장
# 예: [올림포스 영어독해 기본1 UNIT 03 Practice 02], [22번], [31번]
_RE_SOURCE_LINE = re.compile(
    r"^\s*\[(?:올림포스|마더텅|수능특강|EBS|능률|\d+년|\d+월|\d+번)[^\]]*\]\s*\.?\s*$",
    re.UNICODE
)

# 메타 정보: "객관식 25, 서술형 6" / "객 24 / 서 6" (학교별 약식 표기)
_RE_META = re.compile(r"^객(?:관식)?\s*\d+\s*[/,]?\s*서", re.UNICODE)

# 원고 제목 줄: "한영고 1학년 동형 모의고사 1회" 등 — 본문 아닌 스캐폴딩 (skip)
_RE_DOC_TITLE = re.compile(r"^.{0,20}동형\s*모의고사\s*\d*\s*회\s*$", re.UNICODE)

# 서답형/서술형 명시 마커: "[서답형1]", "[서술형 2]" 등 — 이게 있으면 무조건 서술형.
# (객관식/서술형 구분의 가장 신뢰할 수 있는 신호. "~시오" 어미 휴리스틱보다 우선)
_RE_DESC_MARKER = re.compile(r"^\s*\[\s*서[답술]형\s*\d*\s*\]", re.UNICODE)

# 발문 분류 패턴 (Final_test.jsx 기반)
# 1) "다음 글을 읽고 (물음/질문)에 답하시오" + 변형 (공백/쉼표/마침표)
#    → 지문 묶음 발문(passage intro). 뒤의 "윗글…것은?" 들이 실제 객관식 문항.
#    "물음에"뿐 아니라 "질문에 답하시오"도 인식해야 함(원고마다 다름).
#    [N~M] / [N-M] / [선택형 N~M] 같은 prefix 허용 (명일/성덕 케이스)
_RE_INTRO_READ = re.compile(
    r"(?:^\[[^\]]*\d[^\]]*\]\s*)?다음\s*글을\s*읽고[,]?\s*(?:물음|질문)에\s*답하시오\.?",
    re.UNICODE
)
# 2) 객관식 "고르시오" 발문 (서술형 시오 검사보다 먼저 — 대부분 객관식)
#    "...고르시오." + 후행 [출처] 또는 (점수) 같은 표기 허용
_RE_INTRO_CHOOSE = re.compile(
    r"고르시오\.?(?:\s*[\[\(][^\]\)]*[\]\)])*\s*$", re.UNICODE
)
# 3) 서술형 발문: 진짜 서술형 어미(쓰시오/고치시오/배열/영작/서술/완성/채우)로 끝.
#    ⚠ "답하시오"(지문 묶음 intro)·"고르시오"(객관식)는 서술형이 아님 → 제외.
#    (예전엔 generic "시오"라서 "질문에 답하시오"가 서술형으로 오분류됐음)
_RE_INTRO_DESC = re.compile(
    r"(?:쓰시오|고치시오|배열하시오|영작하시오|서술하시오|완성하시오|채우시오)"
    r"\.?(?:\s*[\[\(][^\]\)]*[\]\)])*\s*$", re.UNICODE
)
# 4) 객관식 발문: 한글 + ?로 끝남, 후행 [출처]·(점수) 허용
#    예: "...것은? [21년 6월 22번]" / "...곳은? (1.2점)"
_RE_INTRO_OBJ = re.compile(
    r"[가-힣]\?(?:\s*[\[\(][^\]\)]*[\]\)])*\s*$", re.UNICODE
)

# 발문에서 후속 박스 단락 카테고리를 결정하는 키워드
# - "주어진 문장이 들어가기에 가장 적절한 곳" → 다음 단락은 박스(테두리_순서삽입)
# - "글의 순서로 가장 적절한 것" → 다음 단락은 박스(테두리_순서) [순서 첫 문단]
# - "요약문" 발문 → 지문 + 영단어 + ↓ 후 박스(테두리_요약)
_RE_BOX_INTRO_INSERT = re.compile(
    r"주어진\s*문장이?\s*들어가기에\s*가장\s*적절한", re.UNICODE
)
_RE_BOX_INTRO_SUMMARY = re.compile(
    r"(?:한\s*문장으로\s*요약|요약문|요약하?고자\s*한다)", re.UNICODE
)
_RE_BOX_INTRO_ORDER = re.compile(
    r"(?:이어질\s*글의?\s*순서로\s*가장\s*적절|"
    r"주어진\s*글\s*다음에\s*이어질)", re.UNICODE
)

# ↓ 등 화살표 마커 (요약 박스 등장 신호)
_ARROW_MARKERS = {"↓", "▼", "⬇"}  # ↓ ▼ ⬇

# 요약 박스 텍스트 패턴: 단락 안에 ( A ) / (A) 와 ( B ) / (B) 빈칸 둘 다 포함
# (직전이 요약 발문일 때만 박스로 분류)
_RE_SUMMARY_BLANK_AB = re.compile(
    r"\(\s*A\s*\)[^\(]*\(\s*B\s*\)|"
    r"\(\s*A\s*\)\s*_+|"
    r"\(\s*A\s*\)__",
    re.UNICODE
)

# Q&A 박스: "Q:" 시작 단락
_RE_QA_QUESTION = re.compile(r"^\s*Q\s*[:：]", re.UNICODE)

# 발문에서 Q&A 박스를 기대하는 패턴
_RE_INTRO_QA = re.compile(r"질문의?\s*답", re.UNICODE)

# [요약문] 마커 (텍스트 라벨)
_RE_SUMMARY_LABEL_TEXT = re.compile(r"^\s*\[\s*요약문?\s*\]\s*$", re.UNICODE)

# [Answer] 마커 (Q&A 답변 시작)
_RE_ANSWER_LABEL = re.compile(r"^\s*\[\s*Answer\s*\]", re.UNICODE | re.IGNORECASE)

# 선지 패턴: ①② 등으로 시작하는 경우만 (지문 내 삽입 마커 ① 구분)
_RE_CHOICE = re.compile(r"^\s*[①-⑩]")
# 탭으로 구분된 인라인 선지: ① ... \t ② ... (한 줄에 여러 선지)
_RE_CHOICE_TAB = re.compile(r"[①-⑩][^\t]*\t[^\t]*[①-⑤]")

# 조건/보기 — 단락 전체가 박스 마커일 때만 매칭 (발문 인용 제외)
# 예: "<보기>", "< 보 기 >", "[보기]", "ㅣ보 기ㅣ" 등 단독 마커
# 발문 안 인용 ("다음 중 <보기>의 의미를 모두 지닌...") 은 제외
_RE_CONDITION = re.compile(
    r"^\s*[<\[\(ㅣ│\|]?\s*조\s*건\s*[>\]\)ㅣ│\|]?\s*\.?\s*$",
    re.UNICODE
)
_RE_EXAMPLE = re.compile(
    r"^\s*[<\[\(ㅣ│\|]?\s*보\s*기\s*[>\]\)ㅣ│\|]?\s*\.?\s*$",
    re.UNICODE
)
# 요약문 / 우리말 박스 마커도 추가 (학교별 다양)
_RE_SUMMARY_LABEL = re.compile(
    r"^\s*[<\[\(ㅣ│\|]?\s*(?:요\s*약(?:\s*문)?|우리말)\s*[>\]\)ㅣ│\|]?\s*\.?\s*$",
    re.UNICODE
)

# 영단어 (* 시작)
_RE_VOCAB = re.compile(r"^\s*\*")

# 답란 ("답:" 으로 시작하고 빈칸(_) 포함)
_RE_ANSWER_LINE = re.compile(r"^\s*답\s*:.*_")

# 답란: 단락 전체가 답란인 경우만 (예: "(A)____________ (2단어)")
# 본문 안 (A)____ 같은 중간 빈칸은 제외 — 단락 끝까지 빈칸/단어수 표기만 있어야 매칭
_RE_BLANK_ANSWER = re.compile(
    r"^\s*[\(\[]?[A-Eⓐⓑⓒⓓⓔⓕ]+[\)\]]?\s*[_]{3,}"
    r"(?:\s*[,，]\s*[\(\[]?[A-Eⓐⓑⓒⓓⓔⓕ]+[\)\]]?\s*[_]{3,})*"
    r"\s*(?:\(\d+\s*단어\))?\s*\.?\s*$",
    re.UNICODE
)

# 박스 안 채점기준 / 조건 텍스트 (보기/조건 박스 다음에 자주 등장)
# - "변형 없이 그대로 쓸 것"
# - "단어를 활용하여"
# - "(필요 시 변형 가능)"
# - "조건에 맞게 영작할 것"
# - "주어진 어구를 제외하고 N단어로 영작할 것"
_RE_CONDITION_TEXT = re.compile(
    r"(?:변형\s*없이|조건에\s*맞|단어를\s*활용|어구를\s*활용|"
    r"필요\s*시\s*변형|반드시\s*사용할\s*것|문맥과\s*어법에\s*맞|"
    r"\d+\s*단어로\s*영작|영작할\s*것|\d+단어\s*이내|\d+단어\s*이상)", re.UNICODE
)

# 정답 잔재 (각주/미주에서 본문으로 흘러나온 [정답] 단락 — 본문 노이즈)
_RE_ANSWER_LEAK = re.compile(r"^\s*\[정답\]")

# 요약문 박스 특수문자
_SUMMARY_CHARS = {"\uf03b", "\uf044"}

# (A), (B), (C) 순서 지문
_RE_ORDER_PARA = re.compile(r"^\s*\([A-C]\)\s")

# 다중 세트 선지: (A)    (B) 형태 (탭 구분)
_RE_MULTI_CHOICE_HEADER = re.compile(r"^\s*\(A\)\s+\(B\)")

# 문제 번호 단독: [숫자~숫자] 또는 숫자.  으로 시작 (한국어 포함)
_RE_QNUM_PREFIX = re.compile(
    r"^\s*\[?\s*(선택형|서답형|서술형)?\s*\d+\s*[~\-]\s*\d+\s*\]?\s*"
)

# 묶음 발문 prefix가 이미 붙어있는지 확인 ([1~4], [11-12] 등)
_RE_HAS_GROUP_PREFIX = re.compile(r"^\s*\[\s*\d+\s*[~\-]\s*\d+\s*\]")

# '윗글~' 패턴: 같은 지문을 공유하는 후속 발문 표지
# (예: '윗글의 밑줄 친...', '윗글의 내용과...', '윗글에서 전체 흐름...')
_RE_INTRO_REFER_PREV = re.compile(r"^\s*윗글", re.UNICODE)


def _set_box_expectation(ctx, stripped):
    """객관식 발문에서 박스 종류를 감지하여 ctx에 설정."""
    if ctx is None:
        return
    ctx["expect_box"] = None
    ctx["pending_summary"] = False
    ctx["after_insert_box"] = False
    ctx["pending_qa"] = False
    ctx["in_qa_box"] = False
    if _RE_BOX_INTRO_INSERT.search(stripped):
        ctx["expect_box"] = "테두리_순서삽입"
    elif _RE_BOX_INTRO_ORDER.search(stripped):
        ctx["expect_box"] = "테두리_순서"
    elif _RE_BOX_INTRO_SUMMARY.search(stripped):
        # 요약 박스는 ↓ 마커 또는 (A)/(B) 빈칸 패턴 단락 등장 시 활성화
        ctx["pending_summary"] = True
    elif _RE_INTRO_QA.search(stripped):
        # Q&A 박스: "Q:" 시작 단락 만나면 활성화
        ctx["pending_qa"] = True


def _classify_paragraph(text, prev_style, in_descriptive_block, ctx=None):
    """단락 텍스트를 분석하여 스타일 이름을 반환.

    ctx (optional): 컨텍스트 dict — 이전 발문이 어떤 박스를 기대하는지 추적.
        ctx["expect_box"]: "테두리_순서삽입" | "테두리_요약" | "테두리_순서" | None
            (다음 단락 1개를 박스로 분류하면 즉시 None으로 reset)
        ctx["pending_summary"]: 요약 발문 후 ↓ 마커 대기 중
        ctx["after_insert_box"]: 직전이 테두리_순서삽입이었음 — 다음 (A) 마커는 지문
        ctx["in_box"]: 현재 박스 단락 묶음 안에 있는지 추적
    """
    stripped = text.strip()
    if not stripped:
        return prev_style  # 빈 줄은 이전 스타일 유지

    # 메타 정보
    if _RE_META.match(stripped):
        return "_meta"

    # 원고 제목 줄 (동형 모의고사 N회) — 본문 스캐폴딩, 제외
    if _RE_DOC_TITLE.match(stripped):
        return "_skip"

    # 헤더
    if _RE_HEADER.match(stripped):
        return "_header"

    # 정답 잔재 ([정답] 시작 본문 단락 — 각주/미주에서 흘러나온 것)
    if _RE_ANSWER_LEAK.match(stripped):
        return "_skip"

    # 출처 표기 단독 단락 (상일/배재 원고에서 발문 다음 줄에 단독 등장)
    if _RE_SOURCE_LINE.match(stripped):
        return "_skip"

    # 조건
    if _RE_CONDITION.search(stripped):
        if ctx is not None:
            ctx["in_box"] = "조건"
        return "테두리_조건"

    # 보기
    if _RE_EXAMPLE.search(stripped):
        if ctx is not None:
            ctx["in_box"] = "보기"
        return "테두리_보기"

    # 요약문 박스 구분자
    if any(c in stripped for c in _SUMMARY_CHARS):
        if ctx is not None:
            ctx["in_box"] = "요약"
        return "테두리_요약"

    # 영단어
    if _RE_VOCAB.match(stripped):
        return "영단어"

    # 답란 (밑줄 빈칸)
    if _RE_ANSWER_LINE.search(stripped):
        return "서술형답지"

    # (A) ____ / ⓐ ____ 같은 답란 — 단락 전체가 답란 형태일 때만
    if _RE_BLANK_ANSWER.match(stripped):
        return "서술형답지"

    # 발문 분류 (우선순위 순) — 모든 발문은 in_box / expect_box reset
    # 0) 서답형/서술형 명시 마커([서답형N]) — 가장 신뢰도 높은 신호, 최우선
    if _RE_DESC_MARKER.match(stripped):
        if ctx is not None:
            ctx["expect_box"] = None
            ctx["pending_summary"] = False
            ctx["after_insert_box"] = False
            ctx["pending_qa"] = False
            ctx["in_qa_box"] = False
            ctx["expect_first_passage"] = False
            ctx["in_box"] = None
        return "서술형 번호"
    # 1) "다음 글을 읽고 (물음/질문)에 답하시오" — 지문 묶음 intro (객관식)
    if _RE_INTRO_READ.search(stripped):
        if ctx is not None:
            ctx["expect_box"] = None
            ctx["pending_summary"] = False
            ctx["after_insert_box"] = False
            ctx["in_box"] = None
            ctx["pending_qa"] = False
            ctx["in_qa_box"] = False
            # 직후 첫 본문 단락이 박스(주어진 글)일 가능성
            ctx["expect_first_passage"] = True
        return "다음 글을 읽고"
    # 2) 객관식 "고르시오" — 서술형 시오 검사보다 먼저
    if _RE_INTRO_CHOOSE.search(stripped):
        if ctx is not None:
            ctx["in_box"] = None
            ctx["expect_first_passage"] = False
            _set_box_expectation(ctx, stripped)
        return "문제 번호"
    # 3) 서술형 발문: "~시오"로 끝남
    if _RE_INTRO_DESC.search(stripped):
        if ctx is not None:
            ctx["expect_box"] = None
            ctx["pending_summary"] = False
            ctx["after_insert_box"] = False
            ctx["pending_qa"] = False
            ctx["in_qa_box"] = False
            ctx["expect_first_passage"] = False
            ctx["in_box"] = None
        return "서술형 번호"
    # 4) 객관식 발문: 한글 + "?"로 끝남
    if _RE_INTRO_OBJ.search(stripped):
        if ctx is not None:
            ctx["in_box"] = None
            ctx["expect_first_passage"] = False
            _set_box_expectation(ctx, stripped)
        return "문제 번호"

    # 화살표 마커 (↓ 등): pending_summary가 있으면 다음 단락이 요약 박스
    if stripped in _ARROW_MARKERS:
        if ctx is not None and ctx.get("pending_summary"):
            ctx["pending_summary"] = False
            ctx["expect_box"] = "테두리_요약"
        return "지문"

    # [요약문] 라벨 (텍스트 마커) — pending_summary 활성화 시 다음 단락이 요약 박스
    if _RE_SUMMARY_LABEL_TEXT.match(stripped):
        if ctx is not None and ctx.get("pending_summary"):
            ctx["pending_summary"] = False
            ctx["expect_box"] = "테두리_요약"
        return "_skip"  # 라벨 자체는 자동 결과에 두지 않음 (사용자가 박스 단락에 자동 표시)

    # 요약 박스: pending_summary 상태 + (A)/(B) 빈칸 패턴 단락 → 요약 박스
    if (ctx is not None and ctx.get("pending_summary")
            and _RE_SUMMARY_BLANK_AB.search(stripped)):
        ctx["pending_summary"] = False
        return "테두리_요약"

    # Q&A 박스: pending_qa 상태에서 "Q:" 시작 단락 → 박스 시작
    if (ctx is not None and ctx.get("pending_qa")
            and _RE_QA_QUESTION.match(stripped)):
        ctx["pending_qa"] = False
        ctx["in_qa_box"] = True
        return "테두리_요약"  # 명일/상일 alias로 학교별 테두리 매핑

    # Q&A 박스 안 단락 (in_qa_box 활성화 시 박스)
    # 단, 선지 패턴(① 등)을 만나면 박스 종료 — 아래 선지 분류로 fall through
    if ctx is not None and ctx.get("in_qa_box"):
        if _RE_CHOICE.match(stripped) or _RE_CHOICE_TAB.search(stripped):
            ctx["in_qa_box"] = False
            # fall through to 선지 분류
        else:
            return "테두리_요약"

    # 문제 번호 세트 prefix: [선택형 1~6], [서답형 1~3] 등
    if _RE_QNUM_PREFIX.match(stripped):
        if ctx is not None:
            ctx["in_box"] = None
            ctx["expect_box"] = None
        return "문제 번호"

    # 선지
    if _RE_CHOICE.match(stripped):
        if ctx is not None:
            ctx["in_box"] = None  # 선지 시작 → 박스 종료
            ctx["expect_box"] = None
            ctx["in_qa_box"] = False
            ctx["pending_qa"] = False
            ctx["pending_summary"] = False
        return "선지"
    if _RE_CHOICE_TAB.search(stripped):
        if ctx is not None:
            ctx["in_box"] = None
            ctx["expect_box"] = None
            ctx["in_qa_box"] = False
            ctx["pending_qa"] = False
            ctx["pending_summary"] = False
        return "선지"

    # 다중 선택 헤더 (A)  (B)
    if _RE_MULTI_CHOICE_HEADER.match(stripped):
        return "선지"

    # 박스 안 단락 (in_box 활성화 — 마커가 reset되기 전까지 모두 박스)
    # 위에서 발문/선지/마커 등은 이미 처리되어 reset됐을 수 있으므로,
    # 여기 도달했다면 박스 안 일반 단락임.
    if ctx is not None and ctx.get("in_box"):
        cat_map = {"조건": "테두리_조건", "보기": "테두리_보기", "요약": "테두리_요약"}
        return cat_map.get(ctx["in_box"], "지문")

    # 발문이 박스 단락을 기대하는 경우 (직전이 발문)
    if ctx is not None and ctx.get("expect_box"):
        cat = ctx["expect_box"]
        ctx["expect_box"] = None
        if cat == "테두리_순서삽입":
            # 삽입 박스 직후의 (A)/(B)/(C) 마커는 인라인 지문 (지문_순서가 아님)
            ctx["after_insert_box"] = True
        return cat

    # 삽입 박스 직후: (A) 마커는 인라인 삽입점 → 지문 (지문_순서 아님)
    if ctx is not None and ctx.get("after_insert_box"):
        ctx["after_insert_box"] = False
        if _RE_ORDER_PARA.match(stripped):
            return "지문"

    # 서술형 블록 내의 보기/조건 내용
    if in_descriptive_block and prev_style in ("테두리_조건", "테두리_보기"):
        return "테두리_보기"

    # 순서 지문: (A), (B), (C) 시작 — 단, 발문이 없거나 직전이 지문이 아닐 때
    if _RE_ORDER_PARA.match(stripped):
        return "지문_순서"

    # 기본: 지문
    return "지문"


# 후행 [출처] 또는 (점수) — 발문 끝 정리용
_RE_TRAILING_SOURCE = re.compile(r"(?:\s*[\[\(][^\]\)]*[\]\)])+\s*$")


def _strip_trailing_source(para):
    """발문 뒤 출처 표기 [...] / 점수 (...) 제거 (text + runs 동기).

    점수 표기 (1.2점) 등도 함께 제거하여 묶음 발문 통합 시 텍스트 비교 정확화.
    """
    text = para.get("text", "")
    m = _RE_TRAILING_SOURCE.search(text)
    if not m:
        return
    suffix_len = len(text) - m.start()
    para["text"] = text[:m.start()]

    runs = para.get("runs", [])
    remaining = suffix_len
    while runs and remaining > 0:
        last = runs[-1]
        t = last.get("t", "")
        if len(t) <= remaining:
            remaining -= len(t)
            runs.pop()
        else:
            last["t"] = t[:-remaining]
            remaining = 0


def classify_paragraphs(raw_paras):
    """원시 단락 목록을 분류하여 pstyle 필드 추가."""
    result = []
    prev_style = "지문"
    in_descriptive_block = False
    ctx = {
        "expect_box": None,
        "in_box": None,
        "pending_summary": False,
        "after_insert_box": False,
        "pending_qa": False,
        "in_qa_box": False,
        "expect_first_passage": False,
    }

    for para in raw_paras:
        text = para["text"]
        style = _classify_paragraph(text, prev_style, in_descriptive_block, ctx)

        # 서술형 번호 이후 블록 추적
        if style == "서술형 번호":
            in_descriptive_block = True
        elif style == "_header":
            in_descriptive_block = False
            ctx["expect_box"] = None
            ctx["in_box"] = None
            ctx["pending_summary"] = False
            ctx["after_insert_box"] = False
            ctx["pending_qa"] = False
            ctx["in_qa_box"] = False

        # 발문 뒤 출처 표기 제거 (문제 번호/서술형 번호/다음 글을 읽고)
        if style in ("문제 번호", "서술형 번호", "다음 글을 읽고"):
            _strip_trailing_source(para)

        para["pstyle"] = style
        prev_style = style
        result.append(para)

    return result


# ── 묶음 발문 통합 ──────────────────────────────────────────────────────────────

def _add_text_prefix(para, prefix):
    """단락의 text와 runs[0]에 prefix 추가 (서식 보존)."""
    old_text = para.get("text", "")
    para["text"] = prefix + old_text.lstrip()
    runs = para.get("runs")
    if runs:
        old_t = runs[0].get("t", "")
        runs[0]["t"] = prefix + old_t.lstrip()


def _merge_grouped_intros(paragraphs):
    """묶음 발문 통합 (parser 후처리).

    Pattern 1: 같은 텍스트의 '문제 번호' N개 연속 → 첫 번째만 유지하고 [N~M] prefix 추가,
               스타일을 '다음 글을 읽고'로 변경. 나머지 발문 단락은 제거 (선지/지문은 유지).

    Pattern 2: '다음 글을 읽고' 단락 (예: '다음 글을 읽고 물음에 답하시오.') 중
               [N~M] prefix가 없는 것 → 다음 '다음 글을 읽고' 또는 끝까지의
               '문제 번호'/'서술형 번호' 개수로 [N~M] prefix 자동 추가.

    질문 번호(_q_num)는 원본 순서 기준으로 부여되며, 통합 후에도 보존됨.
    """
    if not paragraphs:
        return paragraphs

    # Step 0: 원본 순서 기준 질문 번호 부여
    q_count = 0
    for p in paragraphs:
        if p["pstyle"] in ("문제 번호", "서술형 번호"):
            q_count += 1
            p["_q_num"] = q_count

    result = list(paragraphs)

    # Pattern 1: 연속 동일 '문제 번호' 통합
    # 단, 사이에 본문성 단락(지문/영단어/순서지문/박스 등)이 있으면 묶지 않음.
    # 같은 발문이라도 각각 다른 본문에 적용되는 경우(상일 등)는 개별 문제이므로
    # 묶음 통합 X. 단어 영영풀이처럼 발문 사이에 선지만 있는 경우만 묶음.
    _BREAK_BY_INTRO = ("서술형 번호", "다음 글을 읽고")
    _BREAK_BY_PASSAGE = (
        "지문", "지문_순서", "영단어",
        "테두리_요약", "테두리_순서", "테두리_순서삽입",
        "테두리_조건", "테두리_보기", "서술형답지",
    )
    intro_indices = [i for i, p in enumerate(result) if p["pstyle"] == "문제 번호"]
    runs = []
    i = 0
    while i < len(intro_indices):
        base = result[intro_indices[i]]["text"].strip()
        if not base:
            i += 1
            continue
        j = i + 1
        while j < len(intro_indices):
            mid = result[intro_indices[j-1]+1 : intro_indices[j]]
            has_break = any(
                p["pstyle"] in _BREAK_BY_INTRO or p["pstyle"] in _BREAK_BY_PASSAGE
                for p in mid
            )
            if has_break:
                break
            if result[intro_indices[j]]["text"].strip() == base:
                j += 1
            else:
                break
        if j - i >= 2:
            runs.append((i, j))
        i = j

    # 역순 적용 (인덱스 보존)
    for start, end in reversed(runs):
        first_idx = intro_indices[start]
        last_idx = intro_indices[end-1]

        n = result[first_idx].get("_q_num")
        m = result[last_idx].get("_q_num")
        if n is None or m is None:
            continue

        # 묶음 발문 텍스트
        base_text = result[first_idx].get("text", "").strip()
        grouped_text = "[" + str(n) + "~" + str(m) + "] " + base_text

        # 모든 기존 발문 단락을 빈 placeholder("문제 번호" 스타일)로 변환.
        # InDesign 자동 번호매김으로 q1~qN 번호 부여 → 다음 일반 발문 = q(N+1).
        for k in range(start, end):
            p = result[intro_indices[k]]
            p["text"] = ""
            p["runs"] = [{"t": "", "ul": False}]
            # pstyle "문제 번호" 그대로 유지

        # 첫 placeholder 앞에 묶음 발문 단락 INSERT ('다음 글을 읽고' 스타일)
        grouped_para = {
            "text": grouped_text,
            "runs": [{"t": grouped_text, "ul": False}],
            "pstyle": "다음 글을 읽고",
        }
        result.insert(first_idx, grouped_para)

    # Pattern 2: '다음 글을 읽고' 단락에 [N~M] prefix 자동 부여
    # 같은 지문을 공유하는 후속 발문(윗글~)만 그룹에 포함.
    # 첫 발문이 '윗글~'이 아니면 단독 지문으로 보고 prefix 미부여.
    intro_indices_2 = [i for i, p in enumerate(result) if p["pstyle"] == "다음 글을 읽고"]
    for k, idx in enumerate(intro_indices_2):
        text = result[idx].get("text", "")
        if _RE_HAS_GROUP_PREFIX.match(text):
            continue

        next_intro_idx = (
            intro_indices_2[k+1] if k+1 < len(intro_indices_2) else len(result)
        )

        # 후속 '문제 번호' 단락 중 '윗글~'로 시작하는 것만 카운트
        # 첫 비-'윗글' 발문에서 끊김
        q_nums_in_block = []
        for j in range(idx+1, next_intro_idx):
            p = result[j]
            if p["pstyle"] in ("문제 번호", "서술형 번호"):
                if not _RE_INTRO_REFER_PREV.match(p.get("text", "")):
                    break  # 새 지문 발문 → 그룹 종료
                qn = p.get("_q_num")
                if qn is not None:
                    q_nums_in_block.append(qn)

        if len(q_nums_in_block) < 2:
            continue

        n = q_nums_in_block[0]
        m = q_nums_in_block[-1]
        prefix = "[" + str(n) + "~" + str(m) + "] "
        _add_text_prefix(result[idx], prefix)

    # _q_num annotation cleanup
    for p in result:
        p.pop("_q_num", None)

    return result


def _mark_post_read_box(paragraphs):
    """후처리: '다음 글을 읽고' 후 본문이 박스인 경우 표시.

    조건:
    - '다음 글을 읽고' 단락 발견
    - 직후 N개 본문 단락 (지문/지문_순서)
    - 본문 후 첫 발문이 '주어진 글~' 또는 '글의 순서~' 같은 순서 발문이면
      → 첫 본문 단락을 '테두리_순서'로 표시
    - 본문 후 발문이 윗글~ 등 일반이면 변경 없음 (지문 그대로)
    """
    if not paragraphs:
        return paragraphs

    n = len(paragraphs)
    for i in range(n):
        if paragraphs[i].get("pstyle") != "다음 글을 읽고":
            continue

        # 직후 본문 단락 범위 찾기
        body_start = i + 1
        body_end = body_start
        while body_end < n and paragraphs[body_end].get("pstyle") in ("지문", "지문_순서"):
            body_end += 1
        if body_end == body_start:
            continue  # 본문 없음 (직후가 발문)

        if body_end >= n:
            continue
        next_para = paragraphs[body_end]
        if next_para.get("pstyle") != "문제 번호":
            continue

        next_text = next_para.get("text", "").lstrip()
        # 윗글~ 발문이면 변경 없음 (명일 케이스 — 본문은 그냥 지문)
        if next_text.startswith("윗글"):
            continue

        # 순서/주어진 글 패턴이면 첫 본문 = 박스 (상일 케이스)
        if (_RE_BOX_INTRO_ORDER.search(next_text)
                or _RE_BOX_INTRO_INSERT.search(next_text)):
            paragraphs[body_start]["pstyle"] = "테두리_순서"

    return paragraphs


# ── 어법 매트릭스(선지 표) 재조립 ────────────────────────────────────────────────
# 일부 어법 문제는 [I]~[V] 행 × ①~⑤ 열 표인데, 원고가 셀을 단락 하나씩(열 우선)으로
# 풀어놓아 조판 시 세로로 깨진다. 패턴을 감지해 탭 구분 행 단락으로 재조립한다.
# 예: 행라벨 [I][II][III][IV][V] + (① + 행수만큼 셀) × 열수 → 탭 표 (1회 (A)(B)(C)식 렌더)
_RE_MATRIX_ROWLABEL = re.compile(r"^\[(?:[IVXLC]+|\d{1,2})\]$", re.UNICODE)
_RE_MATRIX_CHOICE = re.compile(r"^[①-⑩]$", re.UNICODE)
_RE_MATRIX_CELL = re.compile(r"^\([a-zA-Z]\)$", re.UNICODE)


def _merge_choice_matrix(paragraphs):
    """행라벨+선지셀로 평탄화된 어법 매트릭스를 탭 구분 표 행으로 재조립."""
    if not paragraphs:
        return paragraphs

    n = len(paragraphs)
    out = []
    i = 0
    while i < n:
        # 1) 연속 행라벨 수집 ([I][II]...)
        j = i
        labels = []
        while j < n and _RE_MATRIX_ROWLABEL.match(paragraphs[j].get("text", "").strip()):
            labels.append(paragraphs[j]["text"].strip())
            j += 1

        if len(labels) >= 3:
            m = len(labels)
            # 2) (선지마커 + m개 셀) 그룹 반복 수집
            cols = []
            k = j
            while k < n and _RE_MATRIX_CHOICE.match(paragraphs[k].get("text", "").strip()):
                marker = paragraphs[k]["text"].strip()
                cells = []
                kk = k + 1
                while kk < n and len(cells) < m and \
                        _RE_MATRIX_CELL.match(paragraphs[kk].get("text", "").strip()):
                    cells.append(paragraphs[kk]["text"].strip())
                    kk += 1
                if len(cells) != m:
                    break  # 깔끔한 매트릭스 아님
                cols.append((marker, cells))
                k = kk

            if len(cols) >= 2:
                # 3) 행 우선 탭 표로 재구성 (헤더: 빈칸+①②… / 각 행: 라벨+셀들)
                def _mkpara(text):
                    return {"text": text,
                            "runs": [{"t": text, "ul": False}],
                            "pstyle": "선지"}

                header = "\t" + "\t".join(c[0] for c in cols)
                out.append(_mkpara(header))
                for r in range(m):
                    row = labels[r] + "\t" + "\t".join(c[1][r] for c in cols)
                    out.append(_mkpara(row))
                i = k
                continue

        out.append(paragraphs[i])
        i += 1

    return out


# ── 지시문형 묶음 발문 펼치기 ─────────────────────────────────────────────────
# "[3~4] 다음 글의 내용과 일치하지 않는 것을 고르시오." 처럼 한 지시문에 N개 지문이
# 묶인 경우: 지시문은 비번호 헤더로 두고, 각 지문 앞에 빈 '문제 번호' placeholder를
# 삽입해 InDesign 자동번호가 N..M으로 매겨지게 한다. (안 그러면 둘째 지문이 번호 없이
# 지문+선지만 떠서 "발문 없는 블록"이 됨)
# ※ 지문묶음 intro("다음 글을 읽고 …답하시오")는 '문제 번호'가 아니라 별도 하위 발문이
#   있으므로 여기 해당 안 됨.
_RE_RANGE_PREFIX = re.compile(r"^\s*\[\s*(\d+)\s*[~\-]\s*(\d+)\s*\]")
_PASSAGE_START_STYLES = (
    "지문", "지문_순서", "영단어",
    "테두리_순서", "테두리_요약", "테두리_순서삽입", "테두리_조건", "테두리_보기",
)


def _expand_instruction_groups(paragraphs):
    if not paragraphs:
        return paragraphs
    n = len(paragraphs)
    out = []
    i = 0
    while i < n:
        p = paragraphs[i]
        m = _RE_RANGE_PREFIX.match(p.get("text", "")) if p.get("pstyle") == "문제 번호" else None
        if not m:
            out.append(p)
            i += 1
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        count = hi - lo + 1
        if count < 2:
            out.append(p)
            i += 1
            continue

        # 지시문 → 비번호 헤더
        header = dict(p)
        header["pstyle"] = "다음 글을 읽고"
        out.append(header)

        # 그룹 본문 수집(다음 진짜 발문 전까지)
        j = i + 1
        group = []
        while j < n and paragraphs[j].get("pstyle") not in (
                "문제 번호", "서술형 번호", "다음 글을 읽고"):
            group.append(paragraphs[j])
            j += 1

        # 각 지문블록 시작 앞에 번호 placeholder 삽입
        def _prev_meaningful(gi):
            k = gi - 1
            while k >= 0 and group[k].get("pstyle") == "_skip":
                k -= 1
            return group[k].get("pstyle") if k >= 0 else None

        made = 0
        rebuilt = []
        for gi in range(len(group)):
            cs = group[gi].get("pstyle")
            is_start = (cs in _PASSAGE_START_STYLES and made < count and
                        _prev_meaningful(gi) in (None, "선지", "_header"))
            if is_start:
                rebuilt.append({"text": "", "runs": [{"t": "", "ul": False}],
                                "pstyle": "문제 번호"})
                made += 1
            rebuilt.append(group[gi])
        out.extend(rebuilt)
        i = j
    return out


# ── 문제 단위 분할 ────────────────────────────────────────────────────────────

def _split_into_questions(classified_paras):
    """분류된 단락을 문제 단위로 분할."""
    questions = []
    current_q = None
    meta = {}

    for para in classified_paras:
        style = para["pstyle"]

        if style == "_skip":
            # 정답 잔재 등 본문에서 제외할 단락
            continue

        if style == "_meta":
            # 메타 정보 파싱: "객관식 25, 서술형 6"
            m_obj = re.search(r"객관식\s*(\d+)", para["text"])
            m_desc = re.search(r"서술형\s*(\d+)", para["text"])
            if m_obj:
                meta["objective"] = int(m_obj.group(1))
            if m_desc:
                meta["descriptive"] = int(m_desc.group(1))
            continue

        if style == "_header":
            # 새 문제 시작
            if current_q is not None:
                questions.append(current_q)
            current_q = {
                "source": para["text"].strip(),
                "paragraphs": [],
            }
            continue

        # 헤더 없이 시작하는 경우 (드문 케이스)
        if current_q is None:
            current_q = {
                "source": "",
                "paragraphs": [],
            }

        # _header, _meta 스타일은 이미 처리됨
        current_q["paragraphs"].append({
            "text": para["text"],
            "runs": para["runs"],
            "pstyle": style,
        })

    if current_q is not None:
        questions.append(current_q)

    return questions, meta


# ── 메인 파싱 함수 ────────────────────────────────────────────────────────────

def parse_manuscript(filepath, school, grade, exam_period, exam_date,
                     exam_type, round_num, log=None):
    """원고 파일을 파싱하여 content dict 반환.

    Args:
        filepath: hwpx/docx 파일 경로
        school: 학교명 (예: "명일여고")
        grade: 학년 (예: "고3")
        exam_period: 시험 기간 (예: "26-1-중간")
        exam_date: 시험 날짜 (예: "2026.4.23(수)")
        exam_type: 시험 종류 (예: "1학기 중간고사")
        round_num: 회차 (1 또는 2)
        log: 로그 콜백

    Returns:
        content dict (content.json 구조)
    """
    if log is None:
        log = lambda x: None

    log(f"[파싱] 파일: {os.path.basename(filepath)}")

    # 1) 텍스트 + 밑줄 추출
    raw_paras = _extract_paragraphs(filepath, extract_underline=True)
    log(f"[파싱] 총 {len(raw_paras)}개 단락 추출")

    # 빈 단락 제거 (연속 빈 줄은 하나만 유지)
    cleaned = []
    prev_empty = False
    for p in raw_paras:
        is_empty = not p["text"].strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(p)
        prev_empty = is_empty
    raw_paras = cleaned

    # 텍스트 정규화(분류 전 선행 치환)
    # - Dingbat 원문자(➀~➄) → 표준 원문자(①~⑤): 분류 정규식 [①-⑩] 매칭 위해
    # - '^8' → '• ': InDesign 메타문자 리터럴을 실제 불릿+공백으로
    raw_paras = _normalize_paragraphs_text(raw_paras)

    # 2) 단락 분류
    classified = classify_paragraphs(raw_paras)

    # 2.5) 묶음 발문 통합
    classified = _merge_grouped_intros(classified)

    # 2.6) 후처리: '다음 글을 읽고' 후 박스 본문 표시
    classified = _mark_post_read_box(classified)

    # 2.7) 어법 매트릭스(평탄화된 [I]~[V]×①~⑤ 표) 탭 표로 재조립
    classified = _merge_choice_matrix(classified)

    # 2.8) 지시문형 묶음([3~4] 등) 펼치기 — 각 지문 앞 번호 placeholder
    classified = _expand_instruction_groups(classified)

    # 3) 문제 단위 분할
    questions, meta = _split_into_questions(classified)
    log(f"[파싱] {len(questions)}개 문제 감지, 메타: {meta}")

    # 4) content 구성
    content = {
        "school": school,
        "grade": grade,
        "exam_period": exam_period,
        "exam_date": exam_date,
        "exam_type": exam_type,
        "round": round_num,
        "meta": meta,
        "questions": questions,
    }

    return content


def parse_manuscripts(filepaths, school, grade, exam_period, exam_date,
                      exam_type, job_dir, log=None):
    """여러 원고 파일을 파싱하여 content.json 저장.

    파일명에서 회차를 자동 감지 (예: "동형 1회" → round=1).
    """
    if log is None:
        log = lambda x: None

    results = []
    for fp in filepaths:
        basename = _nfc(os.path.basename(fp))

        # 회차 감지
        m_round = re.search(r"(\d+)\s*회", basename)
        round_num = int(m_round.group(1)) if m_round else len(results) + 1

        content = parse_manuscript(
            fp, school, grade, exam_period, exam_date,
            exam_type, round_num, log
        )
        results.append(content)

    # 단일 파일이면 그대로, 복수면 리스트
    if len(results) == 1:
        output = results[0]
    else:
        output = {"rounds": results}

    content_path = os.path.join(job_dir, "content.json")
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log(f"[파싱] content.json 저장: {content_path}")
    return content_path
