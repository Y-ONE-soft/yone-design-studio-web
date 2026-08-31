"""단락 종류 판정 파이프라인 (docs/taxonomy/09 의사코드 구현).

입력: core.extract 단락 목록 [{"text": str, "runs": [{"t","ul"}]}]
출력: [{"kind": str, "q_code": str|None, "text": str, "para": 원본}]

종류: GH / A / Q / Q-INTRO / P / P-CONTEXT / C / K / Cond / Box / Word
      / BLANK / UNKNOWN / Sum / Ans / AnsL(라벨+빈칸 답란 쌍 — W39)
우선순위와 컨텍스트 규칙은 09 문서 "우선순위 규칙" 절을 따른다.

다층 방어: 발문은 (1) _taxonomy 분류기 → (2) 구조 폴백(번호+종결어미) 순으로
판정하므로, 분류기 룰이 한 발문을 놓쳐도 구조 신호가 있으면 Q로 잡힌다.
"""
import re
from core.structure import block_grammar as BG
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
    # 영어 지시문 발문 (W38 결함 5 — "10. Choose True or False (T/F) …"이
    # 지문으로 인쇄된 실증): 문항 번호 + 명령형/WH-의문 형태만 — 지문 속
    # 명령문(Let's look at …)은 번호가 없어 오탐하지 않는다.
    if BG.is_english_question(text):
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


# 영작 문항의 지문은 영어 산문 안에 '(B) 우리말…' 구간을 품는다. 그 한글
# 구절의 낱말이 발문 분류기에 매칭돼("…부정적인 **태도**를…" → 어조/태도)
# 지문 전체가 발문(Q)으로 튀면, 문항 번호가 하나 더 붙고 지문이 발문
# 스타일로 인쇄된다 (2026-08-28 실증: 80문항 원고가 82번까지 번호가 붙음).
# 발문은 한국어 지시문이다 — 영어로 시작하는 긴 산문에 한글이 조금 섞인
# 것은 지문이다 (W78 "지시문은 한국어다"의 역방향 가드).
_Q_KOR_MIN_RATIO = 0.3


def _is_english_prose(text):
    t = (text or "").strip()
    if len(t) < R.P_MIN_LEN or not R.P_ENGLISH_START.match(t):
        return False
    return _korean_ratio(t) < _Q_KOR_MIN_RATIO


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
    # W57: 밑줄런 답란 ("▶ ______"/"______") — Ans 패턴(지문 스타일 인쇄)
    # 보다 먼저 확정해야 S_답란이 되고, Box 전파 종료 목록에 AnsL이 있어
    # 보기 블록 뒤 무한글 흡수(보기 스타일)도 막힌다 (미래엔김 실증:
    # 같은 ▶ 답란이 보기/지문 스타일로 갈라짐).
    if R.ANS_UL_ROW.match(text):
        return "AnsL", None
    # 2026-08-25: 한 줄에 마커+기입란이 여러 쌍("ⓐ ____  ⓑ ____")인 답란.
    # 기존 답란 정규식은 마커 1개짜리만 봐서 UNKNOWN 으로 남고, 앞의 <보기>
    # 마커 전파에 흡수돼 보기 스타일로 인쇄됐다.
    if R.ANS_MARK_BLANK_ROW.match(text):
        return "AnsL", None
    if any(p.match(text) for p in R.ANS_PATTERNS):
        return "Ans", None
    # 요약문 블록 마커 (W38 결함 4, W39 결함 1) — 대괄호형·꺾쇠형 모두
    # Sum. 일반 꺾쇠 마커(Box)가 <요약문>을 삼키지 않도록 Box보다 먼저.
    # W50: 괄호 이형(〈〉《》【】…)은 마커 판정 직전에 정규화 — 표기 보존.
    bt = R.norm_brackets(text)
    if BG.SUM_MARKER.match(bt):
        return "Sum", None
    bk = _box_kind(bt)
    if bk:
        return bk, None
    if R.BOX_INLINE.match(bt):
        return "Box", None
    if not _is_english_prose(text):
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


_RE_CHOICE_LEAD = re.compile(r'^\s*[①②③④⑤⑥⑦⑧⑨⑩]')


def classify_paragraphs(paras):
    """단락 목록 전체 판정 (2-pass: 1차 종류 → 컨텍스트 보정)."""
    out = []
    for p in paras:
        text = (p.get("text") or "").strip() if isinstance(p, dict) else str(p).strip()
        kind, code = _base_kind(text)
        out.append({"kind": kind, "q_code": code, "text": text, "para": p})

    # W61 (비상(황) 실증 — 사용자 지적 "선지에 왜 발문 단락스타일"):
    # 원문자 선지 중 서술 종결("…태도다." / "…바꾸었다.")이 발문 분류기에
    # 걸려 Q로 튀었다. 원문자 선지는 형제와 함께 온다 — 앞뒤 비빈 이웃에
    # 다른 원문자 선지가 있으면 그 라인은 선지(C)다 (형제 문맥이 개별
    # 어미 판정보다 강한 신호).
    for i, item in enumerate(out):
        if item["kind"] != "Q" or not _RE_CHOICE_LEAD.match(item["text"]):
            continue
        sib = False
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(out) and out[j]["kind"] == "BLANK":
                j += step
            if 0 <= j < len(out) and out[j]["kind"] == "C" \
                    and _RE_CHOICE_LEAD.match(out[j]["text"]):
                sib = True
                break
        if sib:
            item["kind"] = "C"
            item["q_code"] = None

    # 다열 선지 열 머리 (2026-08-25 사용자 지적 "선지 헤더인데 지문으로
    # 처리되고 밑줄까지 붙는다"): 열 라벨만으로 이뤄진 줄 + 바로 다음이
    # 같은 열 수의 원문자 선지 = 선지 헤더(C). 기존 R.C_AB_HEADER 는
    # `(A)` 리터럴만 봐서 ⓐ/㉠/(a) 표기를 전부 놓쳤다 — 표기가 아니라
    # 위치+형태로 잡는다. 뒤에 기입 줄이 오는 경우는 답란(AnsL) 그대로.
    for i, item in enumerate(out):
        if item["kind"] not in ("UNKNOWN", "P", "K", "Word", "Ans", "AnsL"):
            continue
        marks = R.choice_header_marks(item["text"])
        if not marks:
            continue
        nxt = next((out[j] for j in range(i + 1, len(out))
                    if out[j]["kind"] != "BLANK"), None)
        if not nxt or nxt["kind"] != "C":
            continue
        if R.choice_columns(nxt["text"]) != len(marks):
            continue
        item["kind"] = "C"
        item["q_code"] = None
        item["choice_header"] = True

    # 후치 <보기> 캡션 (2026-08-25 실증 — 원고 hwp 표 캡션이 내용 뒤에
    # 추출되는 형태). 마커 뒤에 보기 내용이 없고 앞의 어구 나열이 이
    # 마커의 내용이면, 그 나열을 Box 로 되돌리고 **전방 전파는 하지
    # 않는다** (마커 뒤 답란을 보기 스타일로 삼키던 결함까지 같이 닫힘).
    # 아래 Cond/Box 전파 루프보다 먼저 — 그래야 앞선 <조건> 블록이 이
    # 나열을 조건으로 흡수하지 못하고 Box 에서 멈춘다.
    _meaning = [i for i, it in enumerate(out) if it["kind"] != "BLANK"]
    _trailing_caption = set()
    for _mi, _si in BG.trailing_box_captions(
            [out[i]["text"] for i in _meaning]):
        marker_idx = _meaning[_mi]
        if out[marker_idx]["kind"] != "Box":
            continue
        for _y in range(_si, _mi):
            out[_meaning[_y]]["kind"] = "Box"
        out[marker_idx]["box_caption_start"] = _meaning[_si]
        _trailing_caption.add(marker_idx)
        # 마커 뒤 기입란은 **답란**이다 (보기 내용은 앞에 있었다) — 구
        # 전방 전파가 보기 스타일로 삼키던 줄. 위치+형태로 답란 확정.
        for _y in range(_mi + 1, len(_meaning)):
            _j = _meaning[_y]
            if BG.is_box_content(out[_j]["text"]):
                break
            if out[_j]["kind"] not in ("UNKNOWN", "P", "K", "Word", "Box",
                                       "Ans"):
                break
            if not R.ANS_UL_RUN.search(out[_j]["text"]):
                break
            out[_j]["kind"] = "AnsL"

    # ── 컨텍스트 패스 ────────────────────────────────────────────────────
    # 주어진 블록 슬롯 (W39 하향식 전환): 발문 유형(taxonomy leaf)의 실측
    # 시퀀스(block_sequences.json)가 '발문 직후 배경 단락'을 기대하면, 그
    # 자리의 단락을 형태 신호로 배정한다. 마커 어휘("주어진 글/문장")는
    # 유형 미분류일 때의 프라이어 — kind가 P가 아니어도(❮…❯ 래퍼로
    # UNKNOWN이 된 주어진 문장 등) 유형·위치·형태가 맞으면 배정 (87 실증).
    last_q_code = None
    last_q_text = ""
    last_q_kind = None
    for i, item in enumerate(out):
        kind = item["kind"]
        if kind in ("Q", "Q-INTRO"):
            last_q_code = item["q_code"]
            last_q_text = item["text"]
            last_q_kind = kind
            continue
        if kind not in ("P", "UNKNOWN", "K", "Word"):
            continue

        # T/F 선택 행 (W39 결함 5): 발문이 진위 선택을 지시하는 문항의
        # "N) 문장 (T/F)" 행 = 선지 (111번 실증 — 유형+위치+형태 배정).
        if (last_q_text and BG.is_tf_question(last_q_text)
                and BG.is_tf_choice_row(item["text"])):
            item["kind"] = "C"
            continue

        # 발문 직후 첫 유의 단락인가 — 출처 마커(SRC)와 단독 대괄호 구조
        # 라벨("[Unit 09 - Practice 01]" 등)은 발문과 본문 사이에 끼는
        # 구조 요소라 건너뛴다 (W15 c04 / W39 r7c16 실증).
        prev_meaning = next(
            (out[j] for j in range(i - 1, -1, -1)
             if out[j]["kind"] not in ("BLANK", "SRC")
             and not (out[j]["kind"] == "UNKNOWN"
                      and BG.BRACKET_LABEL.match(out[j]["text"]))),
            None,
        )
        first_after_q = (prev_meaning
                         and prev_meaning["kind"] in ("Q", "Q-INTRO"))
        if first_after_q and BG.expects_given_block(last_q_code,
                                                    last_q_text):
            if BG.given_slot_scan(kind, item["text"],
                                  prior_only=not last_q_code) == "assign":
                item["kind"] = "P-CONTEXT"
                continue

        if kind != "P":
            continue

        # P-CONTEXT 판정 2: 다음 비빈 단락이 (A)로 시작하는 순서배열 구성.
        # W40 결함 4: "(A)\t(B)\t(C)" 다열 선지 헤더(kind C)도
        # P_ORDER_LABEL에 걸려 네모 어법 선택형 지문이 배경으로 오배정
        # (0a5da924 215번 실증) — 순서배열 항목은 "(A) 문장…"(kind P)만.
        # 유형이 분류됐고 그 유형이 주어진 블록을 기대하지 않으면
        # (OBJ-GRM-PAREN 등 선지 직행 실측) 발동 금지 (유형 신호 우선).
        nxt = next(
            (out[j] for j in range(i + 1, len(out)) if out[j]["kind"] != "BLANK"),
            None,
        )
        if (prev_meaning and prev_meaning["kind"] in ("Q", "Q-INTRO")
                and nxt and R.P_ORDER_LABEL.match(nxt["text"])):
            if (nxt["kind"] == "P"
                    and not (last_q_kind == "Q" and last_q_code
                             and not BG.expects_given_block(last_q_code,
                                                            last_q_text))):
                # 순서배열 주어진 글. 유형 veto는 Q 한정 — Q-INTRO(묶음
                # 인트로) 뒤 장문 배열형(r9c20 41~42)은 기존 판정 유지.
                item["kind"] = "P-CONTEXT"
            elif (nxt["kind"] in ("C", "Ans", "AnsL")
                    and BG.is_summary_blank_form(item["text"])):
                # 요약 빈칸형: 발문 직후 요약문 + "(A) (B)" 선지 헤더
                # (선택형) 또는 "(A) ___" 답란(서술형) — 요약문은 배경
                # (r10c21rp11/r2c02rp15 골든 관행 보존). 긴 재인쇄
                # 지문(빈칸 (A),(B) 유형)은 형태 판정(길이 상한)에서
                # 걸러져 지문 유지 (W40 결함 4).
                item["kind"] = "P-CONTEXT"
            continue

        # W85 (사용자 지적 2026-08-31, 성덕고2 EBS 연계 — 반복 지적):
        # 요약문은 **지문 뒤**에 온다. 위 판정은 '발문 직후'만 봐서, 원고가
        # 발문 → 지문 → 요약문 → 선지 순서면 요약문이 지문 스타일로 인쇄됐다.
        # 자리(지문과 선지 사이)와 형태(한글 없는 한 문장 + 인라인 (A)/(B)
        # 빈칸, 길이 상한)로 판정한다 — 재인쇄된 긴 지문은 형태에서 걸린다.
        _sum_t = (item["text"] or "").strip()
        if (prev_meaning and prev_meaning["kind"] in ("P", "P-CONTEXT")
                and nxt and nxt["kind"] in ("C", "Ans", "AnsL")
                and len(_sum_t) >= 30 and len(_sum_t.split()) >= 6
                and BG.is_summary_blank_form(_sum_t)):
            # 길이/낱말 하한 — 두 열 선지 머리("(A)   (B)")도 형태 판정을
            # 통과한다. 요약문은 문장이다 (수능만만 9강 실측).
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
                    # W39: 보정 대상은 원문자(①)/AB헤더형 오분류만 —
                    # T/F 선택 행("N) … (T/F)" — 슬롯 배정 C)은 선지 유지
                    and (R.C_START.match(out[k]["text"])
                         or R.C_AB_HEADER.match(out[k]["text"]))
                    for k in run):
                for k in run:
                    out[k]["kind"] = "P"
        i = j

    # 답란 쌍 (W39 결함 4): "라벨:"(콜론 단독 라벨) + 밑줄 빈칸 라인 =
    # 답란(AnsL — 답 쓰는 곳). 실물 v1 관행 실측(20a3838b): 콜론형 답란은
    # 선지 계열 스타일. 단독 빈칸(Ans)은 기존 지문 관행 유지 — 쌍만 승격.
    # Cond 전파보다 먼저 판정해 라벨이 조건으로 흡수되지 않게 한다.
    for i, item in enumerate(out):
        if item["kind"] not in ("UNKNOWN", "K"):
            continue
        if not BG.ANS_LABEL.match(item["text"]):
            continue
        nxt = next((out[j] for j in range(i + 1, len(out))
                    if out[j]["kind"] != "BLANK"), None)
        if nxt and nxt["kind"] == "Ans":
            item["kind"] = "AnsL"
            nxt["kind"] = "AnsL"

    # Cond/Box propagation: 마커 뒤 이어지는 항목 단락을 같은 종류로.
    # Cond는 W16 c10에서 v1 pass 15/16 의미론으로 재구성 —
    #   (a) 비항목(영어 어구 나열)은 중단이 아니라 '건너뛰고 계속'
    #       (v1 pass 15: DEFAULT run 전체를 스캔하며 마커 항목만 조건화.
    #        어구 나열 자체는 지문 유지 = v1 실물 관행),
    #   (b) 답란(밑줄런/정답/→/우리말)이 블록의 실질 종료,
    #   (c) 조건 문구가 taxonomy 발문으로 오매칭된 Q(시작 힌트 없음 +
    #       '것' 종결)는 조건으로 강등 ("반드시 빈칸은 … 쓸 것" 실증),
    #   (c2) W38 블록 문맥 우선 — 조건 블록 안의 번호 항목("1) 9단어로
    #        빈칸을 완성하시오.")은 종결어미 무관 조건 항목. W16 D3의
    #        "시오-체 번호 항목 발문 유지(v1 관행)"는 사용자 기준으로
    #        폐기. 진짜 발문(발문 어휘 선두 / 항목 번호 시퀀스 이탈)은
    #        블록 종료 (block_grammar.cond_item_take — 실측 규칙),
    #   (d) 건너뛴 뒤에는 마커 항목(불릿/번호)만 조건화 — 한글 비율
    #       단독 신호는 인접 항목에만 (원거리 오염 방지).
    for i, item in enumerate(out):
        if item["kind"] not in ("Cond", "Box"):
            continue
        if i in _trailing_caption:
            continue        # 후치 캡션 — 내용은 이미 앞에서 흡수했다
        j = i + 1
        skipped = False
        cond_no = 1          # W38: 조건 항목 번호 시퀀스 (마커 직후 1 기대)
        # 한글 비율 단독 흡수는 마커 시작 루프에서만 (W39: 항목 시작
        # 재루프가 답란 라벨("주제문:")을 원거리 흡수하는 것 방지)
        from_marker = bool(R.BOX_MARKERS["Cond"].match(
            R.norm_brackets(item["text"])))
        while j < len(out):
            nxt = out[j]
            if nxt["kind"] == "BLANK":
                j += 1
                continue
            t = nxt["text"]
            if item["kind"] == "Box":
                if nxt["kind"] in ("Q", "Q-INTRO", "GH", "A", "Cond", "Box",
                                   "AnsL"):
                    break
                # W40 결함 5: 보기 블록 뒤 괄호 라벨 답란("(A) ______") —
                # 무한글 흡수가 답란을 보기 스타일로 삼키던 것 차단.
                # 연속 답란 라인을 AnsL로 승격하고 블록 종료 (답란 =
                # 블록의 실질 종료 — Cond의 (b) 규칙과 같은 의미론).
                if BG.ANS_PAREN_BLANK.match(t):
                    while j < len(out):
                        if out[j]["kind"] == "BLANK":
                            j += 1
                            continue
                        if BG.ANS_PAREN_BLANK.match(out[j]["text"]):
                            out[j]["kind"] = "AnsL"
                            j += 1
                            continue
                        break
                    break
                # 단독 대괄호 마커 라인("[ Type C (2) ]" 유형 구분 마커 등)은
                # 보기 어구가 아니다 — 전파 차단 (W17 c16: Box 전파가 무한글
                # 판정으로 유형 마커를 보기 스타일로 오염). 어구 나열
                # 대괄호("[ pleased / pleasing ]")는 구분자(/ ,)로 통과.
                if (t.startswith("[") and t.endswith("]")
                        and "/" not in t and "," not in t):
                    break
                # W52 (0645d4a7 v2_6 사용자 지적 2): 화살표 답란("→ m_____")
                # — 보기 블록 뒤 기입 줄이다. 무한글 흡수가 보기 스타일로
                # 삼키던 것을 답란(AnsL) 승격 후 블록 종료 (ANS_PAREN_BLANK
                # 와 같은 의미론 — 답란 = 블록의 실질 종료).
                if t.lstrip().startswith("→"):
                    nxt["kind"] = "AnsL"
                    break
                if (R.BOX_WORDLIST.search(t) or not R.HANGUL.search(t)
                        or R.BOX_ITEM_LABEL.match(t)):
                    # W59: `(a) 한글 문장` 형태의 보기 항목 — 한글 비율만 보고
                    # 끊으면 보기 상자가 첫 줄만 남고 갈라진다(블랙북 실증).
                    nxt["kind"] = "Box"
                    j += 1
                    continue
                break
            # ── Cond ──
            # W40 결함 5: 조건 블록 뒤 괄호 라벨 답란("(A) : ______")도
            # 보기와 동일하게 AnsL 승격 후 블록 종료 (위치+형태 신호).
            if BG.ANS_PAREN_BLANK.match(t):
                while j < len(out):
                    if out[j]["kind"] == "BLANK":
                        j += 1
                        continue
                    if BG.ANS_PAREN_BLANK.match(out[j]["text"]):
                        out[j]["kind"] = "AnsL"
                        j += 1
                        continue
                    break
                break
            if nxt["kind"] in ("Q-INTRO", "GH", "A", "Cond", "Box", "Ans",
                               "AnsL", "SRC", "P-CONTEXT"):
                break
            if R.COND_BLOCK_END.search(t):
                break
            # W39 결함 3: 조건 블록 안 단어 나열은 조건 내용물 (v1 '지문
            # 유지' 관행 폐기 — 사용자 확정). 나열 뒤 괄호 부연("(필요시
            # …)")의 인접 흡수는 계속되므로 skipped를 세우지 않는다.
            if nxt["kind"] in ("P", "UNKNOWN", "Word", "C", "K") \
                    and BG.is_cond_wordlist(t):
                nxt["kind"] = "Cond"
                j += 1
                continue
            marker_item = bool(R.COND_ITEM_START.match(t))
            if nxt["kind"] == "Q":
                # (c2) W38: 블록 문맥 우선 — 번호 항목이면 조건 항목
                take, cond_no = BG.cond_item_take(t, cond_no)
                if take:
                    nxt["kind"] = "Cond"
                    j += 1
                    continue
                if not R.Q_START_HINT.search(t) \
                        and R.COND_ITEM_END.search(t):
                    nxt["kind"] = "Cond"
                    j += 1
                    continue
                break
            # 답란 라벨("주제문:")은 조건이 아니다 — 한글 비율 흡수 제외
            # (W39 결함 4: 단어 나열 뒤 라벨이 조건으로 오염되는 것 방지)
            if nxt["kind"] in ("UNKNOWN", "K") and (
                    marker_item or R.COND_ITEM_END.search(t)
                    or R.COND_ITEM_LEAD.match(t)
                    or (from_marker and not skipped
                        and not BG.ANS_LABEL.match(t)
                        and _korean_ratio(t) >= 0.3)):
                nxt["kind"] = "Cond"
                cond_no = BG.cond_item_seen(t, cond_no)
                j += 1
                continue
            if nxt["kind"] in ("C", "Word") and marker_item:
                # v1 pass 9/16: 오분류된 선지·영단어(★불릿 조건)도 재분류
                nxt["kind"] = "Cond"
                cond_no = BG.cond_item_seen(t, cond_no)
                j += 1
                continue
            skipped = True
            j += 1

    # Sum propagation (W38 결함 4): [요약문] 마커 뒤 이어지는 요약 문장
    # 단락(P/K/UNKNOWN 연속 구간)은 배경(P-CONTEXT) — 선지(C)/발문/마커
    # 등 구조 신호에서 종료. ("[요약문] 헤더 + 그 아래 요약 문장 = 배경"
    # 사용자 확정 스펙 — 6b66b750 실증 12건.)
    for i, item in enumerate(out):
        if item["kind"] != "Sum":
            continue
        j = i + 1
        while j < len(out):
            nxt = out[j]
            if nxt["kind"] == "BLANK":
                j += 1
                continue
            if nxt["kind"] in ("P", "K", "UNKNOWN") and nxt["text"]:
                nxt["kind"] = "P-CONTEXT"
                j += 1
                continue
            break

    # 답란 줄바꿈 연속 (W68 — 2026-08-21 비상(홍) 2과 실증, 사용자 지적
    # "다음 글을 읽고 아래에 지문이 없고 서술형 답란이 혼입"): 서술형 답란이
    # 여러 줄로 접히면 2번째 줄부터는 밑줄 사이에 영문 어구가 껴 있어
    # ("____ outside of Korea (2)____") ANS_PATTERNS/ANS_UL_ROW 어느 쪽에도
    # 걸리지 않고 UNKNOWN → 지문 스타일로 인쇄됐다. 게다가 plan의 세트
    # 안내문 삽입(_s3_insert_set_intros)이 그 '지문'을 새 지문 블록 시작으로
    # 보고 앞에 "다음 글을 읽고 물음에 답하시오."까지 끼워 넣어, 안내문 밑에
    # 지문 대신 답란이 오는 유령 세트가 생겼다.
    # 답란 줄이 밑줄로 끝나면 기입란이 아직 안 닫힌 것 — 다음 줄은 같은
    # 답란의 연속이다 (연속 줄도 밑줄 run을 가져야 승격, 종결 줄에서 정지).
    # 승격 kind는 블록 첫 줄을 승계해 한 답란이 두 스타일로 갈라지지 않게 한다.
    for i, item in enumerate(out):
        if item["kind"] not in ("Ans", "AnsL"):
            continue
        if not R.ANS_WRAP_OPEN.search(item["text"]):
            continue
        cont_kind = item["kind"]
        j = i + 1
        while j < len(out):
            nxt = out[j]
            if nxt["kind"] == "BLANK":
                j += 1
                continue
            if nxt["kind"] not in ("UNKNOWN", "K", "P", "Word", "Ans"):
                break
            if not R.ANS_UL_RUN.search(nxt["text"]):
                break
            if R.ANS_WRAP_BREAK.match(nxt["text"]):
                break        # 형제 답란("(B) ____") — 연속 줄이 아니다
            nxt["kind"] = cont_kind
            if not R.ANS_WRAP_OPEN.search(nxt["text"]):
                break        # 기입란이 닫힌 줄 = 답란 블록 종료
            j += 1

    # 밑줄 변형 정보 (P-NOUL / P-WITH-UL은 스타일 매핑 차원 — kind는 P 유지)
    for item in out:
        if item["kind"] in ("P", "P-CONTEXT") and isinstance(item["para"], dict):
            item["has_underline"] = any(
                r.get("ul") for r in item["para"].get("runs", [])
            )

    return out
