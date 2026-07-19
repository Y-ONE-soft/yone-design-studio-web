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
        if (R.GH_SUBTITLE_MIN_TOKENS <= len(tokens)
                <= R.GH_SUBTITLE_MAX_TOKENS):
            # 상한(W30-r15): 조건 블록의 긴 괄호 부연은 부제가 아니다
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
    # 변형문제 출처 마커 — taxonomy보다 먼저 (마커 안의 유형명 "심경추론"
    # 등이 발문으로 오매칭되는 것을 차단, W15 c04). 스타일은 style_map
    # STEP3.SRC(지문 — v1 실물 관행)로 인쇄.
    if R.SRC_MARKER.match(text):
        return "SRC", None
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
        #   출처 마커(SRC)는 발문과 본문 사이에 끼는 구조 요소라 건너뛴다
        #   (W15 c04: 발문→[마커]→주어진 문장 순서에서 배경 미부여 실증).
        prev_meaning = next(
            (out[j] for j in range(i - 1, -1, -1)
             if out[j]["kind"] not in ("BLANK", "SRC")),
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
    # Cond는 W16 c10에서 v1 pass 15/16 의미론으로 재구성 —
    #   (a) 비항목(영어 어구 나열)은 중단이 아니라 '건너뛰고 계속'
    #       (v1 pass 15: DEFAULT run 전체를 스캔하며 마커 항목만 조건화.
    #        어구 나열 자체는 지문 유지 = v1 실물 관행),
    #   (b) 답란(밑줄런/정답/→/우리말)이 블록의 실질 종료,
    #   (c) 조건 문구가 taxonomy 발문으로 오매칭된 Q(시작 힌트 없음 +
    #       '것' 종결)는 조건으로 강등 ("반드시 빈칸은 … 쓸 것" 실증.
    #        시오-체 번호 항목은 발문 유지 = v1 실물 4ed24266 관행),
    #   (d) 건너뛴 뒤에는 마커 항목(불릿/번호)만 조건화 — 한글 비율
    #       단독 신호는 인접 항목에만 (원거리 오염 방지).
    for i, item in enumerate(out):
        if item["kind"] not in ("Cond", "Box"):
            continue
        j = i + 1
        skipped = False
        while j < len(out):
            nxt = out[j]
            if nxt["kind"] == "BLANK":
                j += 1
                continue
            t = nxt["text"]
            if item["kind"] == "Box":
                if nxt["kind"] in ("Q", "Q-INTRO", "GH", "A", "Cond", "Box"):
                    break
                # 단독 대괄호 마커 라인("[ Type C (2) ]" 유형 구분 마커 등)은
                # 보기 어구가 아니다 — 전파 차단 (W17 c16: Box 전파가 무한글
                # 판정으로 유형 마커를 보기 스타일로 오염). 어구 나열
                # 대괄호("[ pleased / pleasing ]")는 구분자(/ ,)로 통과.
                if (t.startswith("[") and t.endswith("]")
                        and "/" not in t and "," not in t):
                    break
                if R.BOX_WORDLIST.search(t) or not R.HANGUL.search(t):
                    nxt["kind"] = "Box"
                    j += 1
                    continue
                break
            # ── Cond ──
            if nxt["kind"] in ("Q-INTRO", "GH", "A", "Cond", "Box", "Ans",
                               "SRC", "P-CONTEXT"):
                break
            if R.COND_BLOCK_END.search(t):
                break
            marker_item = bool(R.COND_ITEM_START.match(t))
            if nxt["kind"] == "Q":
                if not R.Q_START_HINT.search(t) \
                        and R.COND_ITEM_END.search(t):
                    nxt["kind"] = "Cond"
                    j += 1
                    continue
                break
            if nxt["kind"] in ("UNKNOWN", "K") and (
                    marker_item or R.COND_ITEM_END.search(t)
                    or R.COND_ITEM_LEAD.match(t)
                    or (not skipped and _korean_ratio(t) >= 0.3)):
                nxt["kind"] = "Cond"
                j += 1
                continue
            if nxt["kind"] in ("C", "Word") and marker_item:
                # v1 pass 9/16: 오분류된 선지·영단어(★불릿 조건)도 재분류
                nxt["kind"] = "Cond"
                j += 1
                continue
            skipped = True
            j += 1

    # 밑줄 변형 정보 (P-NOUL / P-WITH-UL은 스타일 매핑 차원 — kind는 P 유지)
    for item in out:
        if item["kind"] in ("P", "P-CONTEXT") and isinstance(item["para"], dict):
            item["has_underline"] = any(
                r.get("ul") for r in item["para"].get("runs", [])
            )

    return out
