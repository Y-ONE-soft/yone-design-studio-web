"""단락 종류 판정 파이프라인 (docs/taxonomy/09 의사코드 구현).

입력: core.extract 단락 목록 [{"text": str, "runs": [{"t","ul"}]}]
출력: [{"kind": str, "q_code": str|None, "text": str, "para": 원본}]

종류: GH / A / Q / Q-INTRO / P / P-CONTEXT / C / K / Cond / Box / Word
      / BLANK / UNKNOWN
우선순위와 컨텍스트 규칙은 09 문서 "우선순위 규칙" 절을 따른다.

다층 방어: 발문은 (1) _taxonomy 분류기 → (2) 구조 폴백(번호+종결어미) 순으로
판정하므로, 분류기 룰이 한 발문을 놓쳐도 구조 신호가 있으면 Q로 잡힌다.
"""
from core.structure import rules as R


def _korean_ratio(text):
    if not text:
        return 0.0
    hangul = len(R.HANGUL.findall(text))
    return hangul / len(text)


def _is_group_header(text):
    for pat in R.GH_PATTERNS:
        if pat.match(text):
            return True
    m = R.GH_SUBTITLE.match(text)
    if m:
        tokens = [t for t in __import__("re").split(r'[\s,/&·]+', text.strip('()（） '))
                  if t]
        if len(tokens) >= R.GH_SUBTITLE_MIN_TOKENS:
            return True
    return False


def _is_answer(text):
    return any(p.match(text) for p in R.A_PATTERNS)


def _box_kind(text):
    for kind, pat in R.BOX_MARKERS.items():
        if pat.match(text):
            return kind
    return None


def _classify_question(text):
    """(kind, code) — _taxonomy 분류기 우선, 실패 시 구조 폴백.

    꼬리 태그([ep1]/[pr1]/[3점] 등)는 판정 전에 반복 제거 — 태그가 붙어도
    발문 인식이 깨지지 않게 (다층 방어의 '정규화' 층).
    """
    while True:
        stripped = R.Q_TRAILING_TAG.sub("", text)
        if stripped == text:
            break
        text = stripped
    # 판정용 보조 텍스트: 꼬리 괄호 주석 제거본 (원문 발문이 괄호로 끝나는 경우)
    text_np = R.Q_TRAILING_PAREN.sub("", text)
    try:
        from engines._taxonomy import classify
        code, _label, _kind = classify(text)
    except Exception:
        code = None
    if code == "OBJ-LNG-HEADER":
        return "Q-INTRO", code
    if code:
        return "Q", code
    for pat in R.Q_INTRO_FALLBACK:
        if pat.search(text):
            return "Q-INTRO", None
    for pi, pat in enumerate(R.Q_FALLBACK_PATTERNS):
        if pat.search(text) or pat.search(text_np):
            # 종결어미 단독 폴백(마지막 패턴)은 발문 시작 신호와 AND
            if pi == len(R.Q_FALLBACK_PATTERNS) - 1 \
                    and not R.Q_START_HINT.search(text):
                continue
            return "Q", None
    return None, None


def _is_english_passage(text, min_len=R.P_MIN_LEN):
    if R.HANGUL.search(text):
        return False
    if not R.P_ENGLISH_START.match(text):
        if not R.P_LEADING_NOISE.match(text):
            return False
    if len(text) >= min_len or R.P_ORDER_LABEL.match(text):
        return True
    # 짧은 영어 완결문 (주어진 문장/요약문 — 종결부호 필수)
    return len(text) >= R.P_SHORT_MIN_LEN and bool(R.P_SENTENCE_END.search(text))


def _base_kind(text):
    """컨텍스트 없이 단락 하나의 1차 종류. (idx 무관 부분)"""
    if not text:
        return "BLANK", None
    if _is_group_header(text):
        return "GH", None
    if _is_answer(text):
        return "A", None
    if R.SYM_LINE.match(text):
        return "Sym", None
    if any(p.match(text) for p in R.ANS_PATTERNS):
        return "Ans", None
    bk = _box_kind(text)
    if bk:
        return bk, None
    if R.BOX_INLINE.match(text):
        return "Box", None
    qk, code = _classify_question(text)
    if qk:
        return qk, code
    if R.C_START.match(text) or R.C_AB_HEADER.match(text):
        return "C", None
    if _is_english_passage(text):
        return "P", None
    if _korean_ratio(text) >= R.K_MIN_RATIO and len(text) >= R.K_MIN_LEN:
        return "K", None
    if len(text) < R.WORD_MAX_LEN and (R.WORD_MARKER.search(text)
                                       or R.WORD_DEF.match(text)):
        return "Word", None
    return "UNKNOWN", None


def classify_paragraphs(paras):
    """단락 목록 전체 판정 (2-pass: 1차 종류 → 컨텍스트 보정)."""
    out = []
    for p in paras:
        text = (p.get("text") or "").strip() if isinstance(p, dict) else str(p).strip()
        kind, code = _base_kind(text)
        out.append({"kind": kind, "q_code": code, "text": text, "para": p})

    # ── 컨텍스트 패스 ────────────────────────────────────────────────────
    last_q_code = None
    for i, item in enumerate(out):
        kind = item["kind"]
        if kind in ("Q", "Q-INTRO"):
            last_q_code = item["q_code"]
            continue
        if kind != "P":
            continue

        # P-CONTEXT 판정 1: 직전 발문이 문장삽입/순서배열 계열이고
        #   이 단락이 그 발문 뒤 첫 비빈 본문이면 배경/씨앗 단락.
        prev_meaning = next(
            (out[j] for j in range(i - 1, -1, -1) if out[j]["kind"] != "BLANK"),
            None,
        )
        if (prev_meaning and prev_meaning["kind"] in ("Q", "Q-INTRO")
                and last_q_code and R.P_CONTEXT_Q_CODES.match(last_q_code)):
            item["kind"] = "P-CONTEXT"
            continue

        # P-CONTEXT 판정 2: 다음 비빈 단락이 (A)로 시작하는 순서배열 구성.
        nxt = next(
            (out[j] for j in range(i + 1, len(out)) if out[j]["kind"] != "BLANK"),
            None,
        )
        if (prev_meaning and prev_meaning["kind"] in ("Q", "Q-INTRO")
                and nxt and R.P_ORDER_LABEL.match(nxt["text"])):
            item["kind"] = "P-CONTEXT"

    # 본문 인라인 번호 문장 보정: P 사이에 낀 1~2개짜리 C 연쇄가 "긴 영어
    # 완결문"이면 선지가 아니라 ①~⑤ 마커가 문장 앞에 붙은 지문 단락이다
    # (어법 문제 변형 — 선지는 항상 5개 연쇄 또는 인라인 분할형).
    i = 0
    while i < len(out):
        if out[i]["kind"] != "C":
            i += 1
            continue
        j = i
        while j < len(out) and out[j]["kind"] in ("C", "BLANK"):
            j += 1
        run = [k for k in range(i, j) if out[k]["kind"] == "C"]
        if 1 <= len(run) <= 2:
            prev = next((out[k] for k in range(i - 1, -1, -1)
                         if out[k]["kind"] != "BLANK"), None)
            nxt = out[j] if j < len(out) else None
            neighbor_p = ((prev and prev["kind"] in ("P", "P-CONTEXT"))
                          or (nxt and nxt["kind"] in ("P", "P-CONTEXT")))
            if neighbor_p and all(
                    len(out[k]["text"]) >= 80
                    and not R.HANGUL.search(out[k]["text"])
                    for k in run):
                for k in run:
                    out[k]["kind"] = "P"
        i = j

    # Cond/Box propagation: 마커 뒤 이어지는 항목 단락을 같은 종류로.
    for i, item in enumerate(out):
        if item["kind"] not in ("Cond", "Box"):
            continue
        j = i + 1
        while j < len(out):
            nxt = out[j]
            if nxt["kind"] == "BLANK":
                j += 1
                continue
            if nxt["kind"] in ("Q", "Q-INTRO", "GH", "A", "Cond", "Box"):
                break
            t = nxt["text"]
            if item["kind"] == "Cond" and (R.COND_ITEM_START.match(t)
                                           or _korean_ratio(t) >= 0.3):
                nxt["kind"] = "Cond"
                j += 1
                continue
            if item["kind"] == "Box" and (R.BOX_WORDLIST.search(t)
                                          or not R.HANGUL.search(t)):
                nxt["kind"] = "Box"
                j += 1
                continue
            break

    # 밑줄 변형 정보 (P-NOUL / P-WITH-UL은 스타일 매핑 차원 — kind는 P 유지)
    for item in out:
        if item["kind"] in ("P", "P-CONTEXT") and isinstance(item["para"], dict):
            item["has_underline"] = any(
                r.get("ul") for r in item["para"].get("runs", [])
            )

    return out
