"""문서 단위 '구조 우선' 지문 헤더 인식기 (W31).

기존 방식(정규식 셰이프 열거 — engines/workbook/parser._RE_HEADER_NUM,
engines/workbook_v2/plan._HEADER_PATTERNS)은 실패마다 패턴을 추가하는
루프였고, 토씨 하나 바뀐 새 형식("1. L1-p. 13 본문 1")이 오면 침묵으로
통짜 유닛이 됐다 (2026-07-19 job 376b34d0 실증 — 4개 섹션 유닛 1, 경고 0).

이 모듈은 '형식'이 아니라 '구조'를 읽는다 — 문서 단위 2패스:

  1) 앵커 발견: 구조 신호(짧은 라인 / 숫자 토큰 / 영단어 희소 / 선행 순번 /
     페이지·지문 마커 토큰 / 직후 영어 본문 시작)로 고신뢰 헤더를 찾는다.
     기존 정규식은 **프라이어(가산점)로 강등** — 매칭되면 신뢰가 오르고,
     안 되면 구조 신호만으로 판정한다.
  2) 자기 유사 전파: 앵커의 셰이프(숫자→N, 대시·공백 정규화)를 그 문서
     안에서 즉석 학습해, 앵커와 닮은 저신뢰 후보를 같은 헤더로 승격한다
     (intra-document clustering). 선행 순번의 단조성(1,2,3…)으로 교차 검증
     승격(seq)도 수행한다.

침묵 금지: 후보(직후 영어 본문이 따라오는 구조 후보)가 2개 이상인데 인식이
0~1개면 Detection.silent()가 True — 호출측(플랜 빌더)은 이때 후보 리스트와
신호 점수를 담아 [오류]로 조판을 중단해야 한다 (경고 아님).

호환성 계약: legacy 프라이어가 True인 라인은 **항상** 헤더로 유지된다
(구조 신호는 추가만 하고 제거하지 않는다 — 기존 인식분 diff 0 하한선).

사용처: engines/workbook_v2/plan.py (플랜 빌더 유닛 분할),
engines/workbook_v2/gate.py (G6 — 파서와 게이트가 같은 눈),
scripts/structure_coverage.py (전수 인벤토리 인식률 측정 — detect_candidates).
"""
import re

# ── 라인 신호 정규식 ─────────────────────────────────────────────────────────

_RE_ENG_WORD = re.compile(r"[A-Za-z]+")
_RE_DIGIT = re.compile(r"\d")
_RE_CIRCLED = re.compile(r"[①-⑳㉑-㉟㊱-㊿"
                         r"ⓐ-ⓩ❶-❿]")
# 선행 순번: "N." / "N)"
_RE_NUMBERED = re.compile(r"^\s*(\d{1,3})\s*[.)]")
# 발문(question stem) — 헤더가 아니라 문제 지시문 (scripts/structure_coverage
# _RE_STEM + extract_structure _RE_QUESTION_TAIL 통합)
_RE_STEM = re.compile(
    r"(다음 글|다음 중|윗글|위 글|물음에 답|적절한 것|적절하지 않은|알맞은|"
    r"고르시오|고른 것|밑줄 친|어법상|문맥상|들어갈 말|일치하|주어진 글)")
_RE_STEM_TAIL = re.compile(
    r"(시오\s*\.?|것은\s*\??|고르시오|것을|한다면|바꾸\S*)\s*$")
# 정답/해설 마커 — 정답지 구간 라벨은 지문 헤더가 아니다
_RE_ANSWERISH = re.compile(r"정답|해설|답안|답지|answer", re.I)
# 꼬리 괄호 주석 — 헤더 본체가 아닌 부가 정보 ("1. L1-본문1(p.17) (정답 1개)"
# 의 "(정답 1개)"). answerish는 '정답지 구간 라벨'을 배제하는 신호인데,
# 꼬리 주석의 '정답' 토큰까지 라벨로 오인해 진짜 지문 헤더를 후보에서
# 원천 탈락시켰다 (2026-08-11 job de909e4d 실증: step2_a1_btm 8개 헤더 전부
# 탈락 → 24단락 무단 드롭 + 후보 0이라 침묵 가드도 미발동). answerish
# 판정만 꼬리 괄호를 벗긴 본체로 한다 (다른 신호는 원문 그대로 — 마커
# 토큰 "(p.17)"은 첫 괄호라 영향 없음).
_RE_TAIL_PARENS = re.compile(r"(?:\s*\([^()]{0,30}\))+\s*$")
# 페이지/지문 마커 토큰 (구조 신호 — 특정 헤더 '문장'이 아니라 토큰 존재만 봄)
_MARKER_CUES = [
    re.compile(r"^\s*\[[^\]]{1,25}\]\s*$"),                   # [20], [본문1]
    re.compile(r"\bp\.?\s*\d+", re.IGNORECASE),               # p2, p.82, p. 13
    re.compile(r"\bno\.?\s*\d+", re.IGNORECASE),              # no.18
    re.compile(r"\bL\s*\d+", re.IGNORECASE),                  # L4
    re.compile(r"\bU\s*\d+"),                                 # U6
    re.compile(r"본문\s*\d+"),                                # 본문1
    re.compile(r"\d+\s*과(?:\s|$|[^가-힣])"),                 # 3과
    re.compile(r"\d+\s*강(?:\s|$|[^가-힣])"),                 # 12강
    re.compile(r"\d+\s*번\s*$"),                              # 9번
    re.compile(r"\d+\s*년\s*\d+\s*월"),                       # 17년 11월 …
    re.compile(r"고[123]\s*[-–—_]\s*\d"),                     # 24-10-고1-31
    re.compile(r"\b(?:Example|Practice|Test|Exercise|Unit|Lesson|Gateway"
               r"|Analysis)\s*\.?\s*\d*", re.IGNORECASE),
]

_SHORT_MAX = 45          # 헤더 후보 최대 길이 (extract_structure.classify_line)
_ENG_WORD_MAX = 5        # 이 이상 영단어면 본문 ("L2-p.52 Further Reading"=4)
_BODY_ENG_MIN = 5        # 다음 줄이 영어 본문이라 판정하는 최소 영단어 수
_CLUSTER_MIN = 2         # 셰이프 클러스터 승격 최소 반복 수
_CLUSTER_BODY_RATIO = 0.5  # 클러스터 내 body_next 비율 하한
_CLUSTER_BODY_ABS = 2    # 클러스터 승격 body_next 절대 수 (비율 대안)
_SEQ_SHAPE_MIN = 3       # 셰이프 시퀀스 승격 최소 반복 수
_SEQ_INC_RATIO = 0.8     # 시퀀스 단조 증가 인접쌍 비율 하한


def _norm(s):
    s = (s or "").replace("\ufeff", "")
    s = re.sub("[\u00a0\u1680\u180e\u2000-\u200b\u202f\u205f\u3000]",
               " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def shape_of(text):
    """헤더 원문 → 문서 내 자기 유사 클러스터링용 셰이프.

    숫자→N, 대시 이형(–—) 통일, 공백 접기. structure_coverage.shape_of와
    호환되는 키(대시 정규화만 추가)."""
    s = _norm(text)
    s = re.sub(r"[–—﹣－]", "-", s)
    s = re.sub(r"\d+", "N", s)
    return re.sub(r"\s+", " ", s).strip()


def _eng_words(s):
    return len(_RE_ENG_WORD.findall(s))


def line_signals(text):
    """라인 하나의 구조 신호. dict(신호명→bool) — 판정·로그 공용."""
    t = _norm(text)
    sig = {
        "short": 0 < len(t) <= _SHORT_MAX,
        "digit": bool(_RE_DIGIT.search(t)),
        "few_eng": _eng_words(t) < _ENG_WORD_MAX,
        "numbered": bool(_RE_NUMBERED.match(t)),
        "marker": any(c.search(t) for c in _MARKER_CUES),
        "stem": bool(_RE_STEM.search(t) or _RE_STEM_TAIL.search(t)),
        "answerish": bool(_RE_ANSWERISH.search(_RE_TAIL_PARENS.sub("", t))),
        "circled_row": len(_RE_CIRCLED.findall(t)) >= 2,
    }
    return sig


def is_structural_candidate(text, sig=None):
    """구조적 헤더 후보 — 형식 열거 없이 신호 조합만으로.

    짧고, 숫자가 있고, 영단어가 적고, 발문/정답/원문자 나열이 아니고,
    페이지·지문 마커 토큰이 있는 라인."""
    sig = sig or line_signals(text)
    return (sig["short"] and sig["digit"] and sig["few_eng"]
            and not sig["stem"] and not sig["answerish"]
            and not sig["circled_row"] and sig["marker"])


_SCORE_WEIGHTS = (("short", 1), ("digit", 1), ("few_eng", 1), ("numbered", 2),
                  ("marker", 2), ("body_next", 2), ("legacy", 3),
                  ("shape", 3), ("seq", 1))


def _score(sig):
    return sum(w for k, w in _SCORE_WEIGHTS if sig.get(k))


class Detection(object):
    """문서 단위 헤더 인식 결과.

    header_idx     : 헤더로 판정된 라인 인덱스 set
    candidates     : 구조 후보 전수 [{i, t, score, via, signals}] (문서 순)
    anchor_shapes  : 앵커에서 학습한 셰이프 → 발생 수
    """

    def __init__(self):
        self.header_idx = set()
        self.candidates = []
        self.anchor_shapes = {}
        # 헤더 블록으로 흡수된 인접 타이틀 줄 인덱스 (Further Reading 류 —
        # 인식된 헤더 직전의 짧은 섹션 타이틀. 유닛 경계는 아니고 제거 대상)
        self.absorbed_idx = set()
        # 후보 필터(answerish 등)에서 탈락했지만 강한 헤더 신호
        # (numbered+marker+body_next)를 모두 가진 라인 수 — 침묵 가드용
        self.suppressed_strong = 0

    def is_header(self, i):
        return i in self.header_idx

    def is_absorbed(self, i):
        """헤더 직전 타이틀 줄(헤더 블록의 일부) — 본문에서 제거 대상."""
        return i in self.absorbed_idx

    def via(self, i):
        """인덱스 i 헤더의 인식 경로 ("legacy"/"anchor"/"shape"/"seq"/None)."""
        for c in self.candidates:
            if c["i"] == i:
                return c["via"]
        return "legacy" if i in self.header_idx else None

    def recognized_candidates(self):
        return [c for c in self.candidates if c["i"] in self.header_idx]

    def unrecognized_candidates(self):
        return [c for c in self.candidates if c["i"] not in self.header_idx]

    def strong_candidates(self):
        """직후에 영어 본문이 따라오는 후보 — 지문 시작의 강한 구조 증거."""
        return [c for c in self.candidates if c["signals"].get("body_next")]

    def silent(self):
        """침묵 실패 — 강한 구조 후보가 2+개인데 인식이 0~1개.

        suppressed_strong(후보 필터에서 탈락한 강신호 라인)도 합산한다 —
        필터 자체가 틀리면 후보가 0이 되어 가드까지 눈이 머는 구멍 봉합
        (2026-08-11 de909e4d "(정답 1개)" 꼬리 실증).

        True면 호출측은 [오류]로 조판을 중단해야 한다 (경고 금지)."""
        return (len(self.strong_candidates()) + self.suppressed_strong >= 2
                and len(self.header_idx) <= 1)

    def describe(self, limit=12):
        """후보별 신호 점수 로그 (침묵 실패 [오류] 메시지·G6 근거용)."""
        lines = []
        for c in self.candidates[:limit]:
            mark = "O" if c["i"] in self.header_idx else "X"
            on = [k for k, _w in _SCORE_WEIGHTS if c["signals"].get(k)]
            lines.append("  [%s] #%d score=%d via=%s (%s) %r"
                         % (mark, c["i"], c["score"], c["via"] or "-",
                            "+".join(on), c["t"][:40]))
        if len(self.candidates) > limit:
            lines.append("  … 외 %d개" % (len(self.candidates) - limit))
        return "\n".join(lines)


def _detect(entries, legacy=None):
    """공용 코어. entries: [{"t": str, "body_next": bool}] (문서 순).

    Returns Detection (header_idx는 entries 인덱스 기준)."""
    legacy = legacy or (lambda t: False)
    det = Detection()
    n = len(entries)

    # 패스 0: 신호 계산 + legacy 프라이어
    infos = []
    for i in range(n):
        t = _norm(entries[i]["t"])
        sig = line_signals(t)
        sig["body_next"] = bool(entries[i].get("body_next"))
        sig["legacy"] = bool(t) and bool(legacy(entries[i]["t"]))
        cand = is_structural_candidate(t, sig)
        # 후보 탈락했지만 강한 헤더 신호 3종을 모두 가진 라인 — 침묵
        # 가드 합산용 (필터 오류로 후보가 0이 돼도 가드는 발동해야 한다)
        if (not cand and sig["numbered"] and sig["marker"]
                and sig["body_next"]):
            det.suppressed_strong += 1
        infos.append({"i": i, "t": t, "sig": sig, "cand": cand})

    # 호환성 계약: legacy 인식 라인은 무조건 헤더 (제거 없음 — diff 0 하한)
    for info in infos:
        if info["sig"]["legacy"]:
            det.header_idx.add(info["i"])

    # 패스 1: 앵커 — (a) legacy 프라이어, (b) 순번+마커+직후 본문
    anchors = []
    for info in infos:
        if not info["cand"]:
            continue
        s = info["sig"]
        if s["legacy"] or (s["numbered"] and s["marker"] and s["body_next"]):
            anchors.append(info)
            det.header_idx.add(info["i"])

    # (c) 셰이프 클러스터 앵커 — 같은 셰이프가 반복되고 다수가 직후 본문을
    #     동반하면 그 셰이프 전체를 앵커로 (주기적 반복 신호: "본문N" 등
    #     순번 없는 헤더 계열).
    by_shape = {}
    for info in infos:
        if info["cand"]:
            by_shape.setdefault(shape_of(info["t"]), []).append(info)
    for sh, group in by_shape.items():
        if len(group) < _CLUSTER_MIN:
            continue
        body_n = sum(1 for g in group if g["sig"]["body_next"])
        if (body_n >= _CLUSTER_BODY_ABS
                or body_n / float(len(group)) >= _CLUSTER_BODY_RATIO):
            for g in group:
                if g["i"] not in det.header_idx:
                    g["sig"]["shape"] = True
                    det.header_idx.add(g["i"])
                    anchors.append(g)

    # (d) 셰이프 시퀀스 앵커 — 같은 셰이프가 3회+ 반복되고 어느 숫자 토큰
    #     위치가 문서 순으로 단조 증가하면(본문1→본문2→…, …_18번→…_20번)
    #     그 셰이프 전체를 헤더로 (번호 시퀀스 단조성 교차 검증 —
    #     직후 본문 신호가 없는 헤더 계열: 헤더 뒤 발문/한글 해석이 오는
    #     원고. 발문·정답·선지 나열은 후보 단계에서 이미 배제됨).
    for sh, group in by_shape.items():
        if len(group) < _SEQ_SHAPE_MIN:
            continue
        if all(g["i"] in det.header_idx for g in group):
            continue
        toks = [[int(x) for x in re.findall(r"\d+", g["t"])[:8]]
                for g in group]
        npos = min(len(tk) for tk in toks)
        seq_ok = False
        for pos in range(npos):
            vals = [tk[pos] for tk in toks]
            inc = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
            if inc / float(len(vals) - 1) >= _SEQ_INC_RATIO:
                seq_ok = True
                break
        if seq_ok:
            for g in group:
                if g["i"] not in det.header_idx:
                    g["sig"]["seq"] = True
                    det.header_idx.add(g["i"])
                    anchors.append(g)

    # 앵커 셰이프 학습
    for a in anchors:
        sh = shape_of(a["t"])
        det.anchor_shapes[sh] = det.anchor_shapes.get(sh, 0) + 1

    # 패스 2a: 자기 유사 전파 — 앵커 셰이프와 같은 저신뢰 후보 승격
    for info in infos:
        if info["i"] in det.header_idx or not info["cand"]:
            continue
        if shape_of(info["t"]) in det.anchor_shapes:
            info["sig"]["shape"] = True
            det.header_idx.add(info["i"])

    # 패스 2b: 순번 단조성 교차 검증 — 인식 헤더의 선행 순번 시퀀스에
    # 자연스럽게 끼는(strictly increasing) 미승격 후보 승격
    seq = []      # (entries 인덱스, 선행 순번) — 문서 순
    for info in infos:
        if info["i"] in det.header_idx:
            m = _RE_NUMBERED.match(info["t"])
            if m:
                seq.append((info["i"], int(m.group(1))))
    if len(seq) >= 2:
        for info in infos:
            if info["i"] in det.header_idx or not info["cand"]:
                continue
            m = _RE_NUMBERED.match(info["t"])
            if not m:
                continue
            num = int(m.group(1))
            prev = [(i, v) for i, v in seq if i < info["i"]]
            nxt = [(i, v) for i, v in seq if i > info["i"]]
            prev_ok = (not prev) or (prev[-1][1] < num <= prev[-1][1] + 3)
            next_ok = (not nxt) or (num < nxt[0][1])
            if prev and prev_ok and next_ok:
                info["sig"]["seq"] = True
                det.header_idx.add(info["i"])

    # 후보 리포트 (침묵 판정·로그용)
    for info in infos:
        if not info["cand"]:
            continue
        s = info["sig"]
        via = None
        if s.get("legacy"):
            via = "legacy"
        elif s.get("shape"):
            via = "shape"
        elif s.get("seq"):
            via = "seq"
        elif info["i"] in det.header_idx:
            via = "anchor"
        det.candidates.append({"i": info["i"], "t": info["t"],
                               "score": _score(s), "via": via,
                               "signals": s})
    return det


def detect_headers(texts, legacy=None):
    """문서 전체 라인 리스트 → Detection.

    texts: 문서 순 라인(단락 텍스트) 리스트. body_next(직후 비빈 줄이 영어
    본문인지)를 문맥에서 직접 계산한다."""
    stripped = [_norm(t) for t in texts]
    entries = []
    for i, t in enumerate(texts):
        j = i + 1
        while j < len(stripped) and not stripped[j]:
            j += 1
        body_next = (j < len(stripped)
                     and _eng_words(stripped[j]) >= _BODY_ENG_MIN)
        entries.append({"t": t, "body_next": body_next})
    det = _detect(entries, legacy=legacy)
    _absorb_title_lines(det, stripped)
    return det


def _absorb_title_lines(det, stripped):
    """인식된 헤더 직전의 섹션 타이틀 줄을 헤더 블록으로 흡수 (W50).

    원고는 지문 헤더 위에 섹션 타이틀을 별도 줄로 둘 수 있다:
        Further Reading                  ← 타이틀 (숫자·마커 없음)
        8. L1-Further Reading(p.26-27)   ← 지문 헤더 (인식됨)
    타이틀 줄은 숫자 토큰이 없어 구조 후보에서 원천 탈락 → 본문으로
    인쇄됐다 (2026-08-11 de909e4d 실증: 5개 스텝 누출). 이름 열거
    (_RE_SUPP 'Supplementary Reading' 특례)가 아니라 구조로 잡는다:
    인접성(직전 비빈 줄) + 내용-포함(타이틀 텍스트 ⊂ 헤더 텍스트).
    흡수 줄은 유닛 경계가 아니라 제거 대상 (is_absorbed로 노출 —
    경계로 삼으면 상·하단 유닛 수가 어긋난다)."""
    for h in sorted(det.header_idx):
        j = h - 1
        while j >= 0 and not stripped[j]:
            j -= 1
        if j < 0 or j in det.header_idx or j in det.absorbed_idx:
            continue
        t = stripped[j]
        sig = line_signals(t)
        if (not sig["short"] or sig["numbered"] or sig["stem"]
                or sig["answerish"] or sig["circled_row"]):
            continue
        ct = re.sub(r"\s+", "", t).lower()
        ch = re.sub(r"\s+", "", stripped[h]).lower()
        if len(ct) >= 3 and ct in ch:
            det.absorbed_idx.add(j)


def detect_from_candidates(cands, legacy=None):
    """후보 라인만 있는 축약 문서(전수 인벤토리 레코드) → Detection.

    cands: [{"t": str, "body_next": bool}] — 문서 순 헤더 후보 리스트
    (data_corpus/manuscript_structure/inventory.jsonl 레코드의 headers).
    detect_headers와 같은 코어(_detect)를 사용한다 — 측정과 실전이 같은 눈."""
    return _detect(list(cands), legacy=legacy)


class HeaderSilenceError(ValueError):
    """침묵 금지 — 구조 후보는 있는데 헤더 인식이 0~1개 (조판 중단 사유).

    메시지에 후보별 신호 점수를 포함한다."""

    def __init__(self, step_name, det):
        self.step_name = step_name
        self.detection = det
        strong = len(det.strong_candidates())
        msg = ("[오류] %s: 구조적 헤더 후보 %d개(강한 후보 %d개, 필터 "
               "탈락 강신호 %d개) 중 인식 %d개 — 새 헤더 형식으로 보임. "
               "지문 분할 없이 조판하면 통짜 유닛이 되므로 중단합니다.\n"
               "후보(신호 점수):\n%s"
               % (step_name, len(det.candidates), strong,
                  det.suppressed_strong, len(det.header_idx),
                  det.describe()))
        super(HeaderSilenceError, self).__init__(msg)
