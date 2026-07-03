"""워크북 v2 렌더 플랜 빌더 — v1 파서 산출(steps)을 플랜으로 변환.

스텝별 빌더 레지스트리 방식(단계 전환): 빌더가 있는 스텝만 v2가 렌더하고,
없는 스텝은 플랜에서 제외되며 커버리지 리포트에 '미지원'으로 남는다.
스타일 결정 = core/structure/style_map.json "workbook" 섹션 (실물 인벤토리 가드).

Step3는 Phase 2에서 심은 단락 kind 주석을 그대로 사용 — 스타일 결정이
데이터 룩업 한 줄이다 (v1 processStep3 480줄의 휴리스틱을 대체).

W2 (순수 텍스트 6스텝): v1 JSX의 GREP 치환/단락 삭제/패턴 스타일을
스토리 배치 전 파이썬 전처리로 이식 (engines/workbook/jsx/run.jsx의
processStep1A1/1B2/1C2/2A1/2A1Btm/2C1 대응). v1의 "프레임브레이크 삽입" =
빌더의 유닛 분할 (실행기 break_per_unit이 유닛 경계에 NEXT_FRAME 적용).
"""
import json
import os
import re

from core.structure.style_resolver import resolve_style

_DIR = os.path.dirname(os.path.abspath(__file__))
STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                          encoding="utf-8"))


def _style(step_unit, kind, default_kind="P"):
    try:
        v = resolve_style("workbook", step_unit, kind)
    except KeyError:
        try:
            v = resolve_style("workbook", step_unit, default_kind)
        except KeyError:
            return None
    if isinstance(v, list):
        return v[0]
    return v


# ── Step3: kind 주석 기반 (질문/지문/선지/보기/조건/답란 전부 데이터 룩업) ──

def build_step3(step_data):
    """step3 데이터 {normal:[{question_num, paragraphs}], short:[...]} → 유닛."""
    units = []
    warnings = []
    for group in ("normal", "short"):
        for item in step_data.get(group, []) or []:
            unit = []
            for p in item.get("paragraphs", []):
                text = p.get("text", "")
                kind = p.get("kind") or "UNKNOWN"
                if kind in ("GH", "A", "BLANK"):
                    continue          # 제거 대상 (style_map에서 null)
                style = _style("STEP3", kind)
                if style is None:
                    continue
                unit.append({"t": text, "s": style,
                             "runs": p.get("runs") or []})
            if unit:
                units.append(unit)
    return {"units": units, "warnings": warnings}


# ── W2 공용: v1 JSX 판정 로직의 파이썬 포트 ─────────────────────────────────
# (원본: engines/workbook/jsx/run.jsx — isBracketPara/isBlankPara/hasKorean2/
#  isHeaderLine/isA1Header/extractTail. 의미론 보존을 위해 패턴을 그대로 이식)

# v1 isBlankPara의 공백 문자 집합
_RE_BLANK = re.compile(
    "^[\\s\u00a0\u1680\u180e\u2000-\u200b\u202f\u205f\u3000]*$")
_RE_BRACKET = re.compile(r"^\s*\[[^\]]+\]\s*$")
_RE_HARD = re.compile(r"^\s*2\.\s*어휘\s*2단계_Hard\s*$")   # 1A1 삭제 대상
_RE_KOR2 = re.compile(r"[가-힣][\s\S]*[가-힣]")             # v1 hasKorean2
_RE_B2_QNUM = re.compile(r"^\s*\(\d+\)")                    # v1 reNumStart
_RE_B2_CHOICE = re.compile(r"^\s*[①-⑳]")          # v1 reCircled

# v1 insertHeaderBreaks의 헤더 패턴 (run.jsx headerPatterns — compact form 매칭)
_HEADER_PATTERNS = [
    re.compile(r"^L\d+[-–—]본문\d+(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^[A-Za-z]{1,15}\d*[-–—]본문\d+(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—][A-Za-z]{1,30}(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—]p\.?\d+(?:~\d+)?(?:[A-Za-z]{1,20})?$", re.I),
    re.compile(r"^p\d+[-–—\.]?(?:no\.)?\d+(?:~\d+)?(?:\([^\)]{0,40}\))?$",
               re.I),
    re.compile(r"^p\d+[-–—]?Example\d*$", re.I),
    re.compile(r"^p\d+[-–—][A-Za-z]{1,15}\.?\d+(?:~\d+)?$", re.I),
    re.compile(r"^p\d+[-–—](?:서술형|논술형)Practice$", re.I),
    re.compile(r"^p\d+[-–—]+수능대비ANALYSIS$", re.I),
]
_RE_SUPP = re.compile(r"^Supplementary Reading$", re.I)


def _is_blank(text):
    return bool(_RE_BLANK.match(text or ""))


def _is_bracket_para(text):
    """v1 isBracketPara: [XX] 단독 단락 (내용 없는 [  ]는 제외)."""
    if not _RE_BRACKET.match(text or ""):
        return False
    inner = re.sub(r"\]\s*$", "", re.sub(r"^\s*\[", "", text))
    return len(re.sub(r"\s", "", inner)) > 0


def _has_circled(text):
    """v1 processStep2A1Btm isPassage: ①~⑳ (U+2460~2473) 포함 여부."""
    return any(0x2460 <= ord(ch) <= 0x2473 for ch in text or "")


def _norm_header(s):
    s = (s or "").replace("\ufeff", "")
    s = re.sub("[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def is_header_line(text):
    """v1 isHeaderLine: 'N. p2-no.20' 류 지문 헤더 (제거+프레임 분리 대상)."""
    hn = _norm_header(text)
    if len(hn) > 60:
        return False
    if _RE_SUPP.match(hn):
        return True
    body = re.sub(r"^\d+\s*[.)]?\s*", "", hn)
    if not body or len(body) > 50:
        return False
    compact = re.sub(r"\s+", "", body)
    return any(p.match(compact) for p in _HEADER_PATTERNS)


# v1 processStep2A1의 헤더 판정 (isA1Header — 헤더를 지우지 않고 {tail}로 변환)
_RE_A1_L = re.compile(r"^\s*\d+\s*[.)]?\s*L\d+\s*[-–—﹣－]\s*.+",
                      re.I)
_RE_A1_PNO = re.compile(
    r"^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)*"
    r"no\.?\s*\d+(?:~\d+)?\b.*$", re.I)
_RE_A1_PDESC = re.compile(
    r"^\s*\d+\s*[.)]?\s*p\.?\s*\d+\s*(?:[-–—﹣－]|\s)+\s*.+$",
    re.I)
_RE_A1_ANALYSIS = re.compile(r"^\s*\d+.*수능\s*대비\s*analysis.*$", re.I)
_RE_A1_BONMUN = re.compile(r"^\s*\d+\s*[.)]?\s*.*?본문\s*\d+\s*$", re.I)


def is_a1_header(text):
    t = re.sub(r"[\r\n]", "", text or "")
    return bool(_RE_A1_L.match(t) or _RE_A1_PNO.match(t)
                or _RE_A1_PDESC.match(t) or _RE_A1_ANALYSIS.match(t)
                or _RE_A1_BONMUN.match(t))


def extract_tail(text):
    """v1 processStep2A1 extractTail: 헤더 → {tail} 정규화용 꼬리 추출."""
    s = (text or "").strip()
    m = re.search(r"(본문\s*\d+)\s*$", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?"
                 r"\s*[-–—]?\s*(본문\s*\d+)\b", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*(\d+)[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)\s*$",
                 s, re.I)
    if m:
        return "본문" + m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*L\d+(?:\s*[-–—]\s*p\.?\s*\d+)?"
                 r"\s*[-–—]?\s*(.+)$", s, re.I)
    if m:
        return re.sub(r"^\s*p\.?\s*\d+\s*[-–—]?\s*", "", m.group(1),
                      flags=re.I)
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*(\d+(?:~\d+)?)"
                 r"(?:[\s-]*(.+))?$", s, re.I)
    if m:
        return m.group(2) if m.group(2) else m.group(1)
    if re.search(r"수능\s*대비\s*analysis", s, re.I):
        return "분석"
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+\s*(?:[-–—]|\s)+\s*(.+)$",
                 s, re.I)
    if m:
        return m.group(1)
    return ""


def _mk(text, style, runs):
    return {"t": text, "s": style, "runs": runs or []}


def _map_chars(para, table):
    """텍스트+runs에 1:1 문자 치환 적용 (길이 보존 → runs 오프셋 유지)."""
    text = (para.get("text") or "").translate(table)
    runs = [dict(r, t=(r.get("t") or "").translate(table))
            for r in para.get("runs") or []]
    return {"text": text, "runs": runs}


def _split_tabs(text, runs):
    """v1 grepChange('\\t','\\r') 대응 — 탭 경계에서 단락 분할 (runs도 분할)."""
    if "\t" not in (text or ""):
        return [(text, runs or [])]
    pieces = []
    cur_runs = []
    for r in runs or [{"t": text, "ul": False}]:
        parts = (r.get("t") or "").split("\t")
        for i, part in enumerate(parts):
            if i > 0:
                pieces.append(cur_runs)
                cur_runs = []
            if part:
                cur_runs.append(dict(r, t=part))
    pieces.append(cur_runs)
    return [("".join(r["t"] for r in rs), rs) for rs in pieces]


# ── STEP1 A1 (+A1_2): 어휘 선택 — v1 processStep1A1 ─────────────────────────
# ❮❯→[] 치환, 빈 단락(\r{2,}) 제거, "2. 어휘2단계_Hard" 단락 삭제,
# 지문번호 [N] 기준 유닛 분할(=프레임브레이크), [N] 다음 본문 구간 → A1_어휘 선택.

_A1_TABLE = str.maketrans({"❮": "[", "❯": "]"})


def build_step1_a1(step_data):
    st_num = _style("STEP1A1", "NUM")
    st_body = _style("STEP1A1", "C")
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    for raw in step_data.get("paragraphs", []) or []:
        p = _map_chars(raw, _A1_TABLE)
        text = p["text"]
        if _is_blank(text) or _RE_HARD.match(text):
            continue    # v1: \r{2,}→\r + Hard 단락 remove()
        if _is_bracket_para(text):
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
            cur.append(_mk(text, st_num, p["runs"]))
        else:
            cur.append(_mk(text, st_body, p["runs"]))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 B2: 내용 종합 — v1 processStep1B2 ─────────────────────────────────
# 지문번호 [N] 기준 유닛 분할, [N] 다음 본문 → A2_본문 박스, (N) → 번호,
# 원문자 → 선지. 빈 단락은 유지(v1 동일) — 스타일은 직전 단락을 따라간다.

def build_step1_b2(step_data):
    st_num = _style("STEP1B2", "NUM")
    st_body = _style("STEP1B2", "P")
    st_q = _style("STEP1B2", "Q")
    st_c = _style("STEP1B2", "C")
    paras = list(step_data.get("paragraphs", []) or [])
    while paras and _is_blank(paras[-1].get("text") or ""):
        paras.pop()     # v1: \r{2,}\s*$ → \r (꼬리 빈 단락 정리)
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    in_body = False     # [N] 직후 본문 구간 (v1: ']' 닫힘 뒤 ~ (N)/원문자 전)
    prev_style = st_body
    for p in paras:
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if _is_bracket_para(text):
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
            in_body = True
            cur.append(_mk(text, st_num, runs))
            prev_style = st_num
            continue
        if _is_blank(text):
            cur.append(_mk(text, prev_style, runs))
            continue
        if _RE_B2_QNUM.match(text):
            style = st_q
            in_body = False
        elif _RE_B2_CHOICE.match(text):
            style = st_c
            in_body = False
        elif in_body:
            style = st_body
        else:
            style = st_body
            warnings.append("step1_b2: 본문 구간 밖 미분류 단락 → P: "
                            + text[:40])
        cur.append(_mk(text, style, runs))
        prev_style = style
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 C2 / STEP2 C1: 빈칸 어휘/어법 — v1 processStep1C2/2C1 ─────────────
# 헤더 제거+유닛 분할(insertHeaderBreaks), 빈 단락 제거, 탭→단락 분할,
# 한글 2자+ 단락 → 한글해석 스타일, 나머지 → 기본 스텝 스타일.

def _build_wordfill(step_data, step_unit):
    st_p = _style(step_unit, "P")
    st_k = _style(step_unit, "K")
    units = []
    warnings = []
    cur = []
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        if is_header_line(text):
            if cur:
                units.append(cur)
                cur = []
            continue    # v1: 헤더 단락은 비우고 프레임브레이크만 남김
        if _is_blank(text):
            continue    # v1: insertHeaderBreaks 말미의 빈 줄 일괄 제거
        for piece_text, piece_runs in _split_tabs(text, p.get("runs") or []):
            style = st_k if _RE_KOR2.search(piece_text) else st_p
            cur.append(_mk(piece_text, style, piece_runs))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


def build_step1_c2(step_data):
    return _build_wordfill(step_data, "STEP1C2")


def build_step2_c1(step_data):
    return _build_wordfill(step_data, "STEP2C1")


# ── STEP2 A1: 어법 선택 — v1 processStep2A1 ─────────────────────────────────
# 헤더 → {tail} 정규화(제거 아님), 헤더 기준 유닛 분할(첫 헤더 제외),
# 전 단락 → A1_어법 선택. 빈 단락 유지 (v1 동일 — 유닛 끝이라 지면 영향 없음).

def build_step2_a1(step_data):
    st = _style("STEP2A1", "P")
    units = []
    warnings = []
    cur = []
    seen_header = False
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if is_a1_header(text):
            if seen_header and cur:
                units.append(cur)
                cur = []
            seen_header = True
            tail = extract_tail(text)
            if tail:
                text = "{" + tail.strip() + "}"
                runs = [{"t": text, "ul": False}]
        cur.append(_mk(text, st, runs))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP2 A1 하단: 어법 선택 객관식 — v1 processStep2A1Btm ──────────────────
# 원문자(①~⑳) 없는 단락 전부 삭제, 지문 1개 = 유닛 1개(프레임 1개),
# 전 단락 → A1_어법 선택 하단. 밑줄은 지문 밑줄 문자스타일 (v1 CS_PASSAGE_UL).

def build_step2_a1_btm(step_data):
    st = _style("STEP2A1Practice", "P")
    units = []
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        if not _has_circled(text):
            continue    # 책 제목/발문/헤더/빈 단락 = 삭제 대상 (v1 동일)
        units.append([_mk(text, st, p.get("runs") or [])])
    return {"units": units, "warnings": [],
            "ul_style": "공통 > 지문 밑줄"}


# ── 스텝 빌더 레지스트리 (단계 전환: 지원 스텝을 여기서 늘려간다) ────────────

STEP_BUILDERS = {
    "step3": build_step3,
    "step1_a1": build_step1_a1,
    "step1_a1_2": build_step1_a1,   # v1과 동일: 같은 처리, 다른 스토리
    "step1_b2": build_step1_b2,
    "step1_c2": build_step1_c2,
    "step2_a1": build_step2_a1,
    "step2_a1_btm": build_step2_a1_btm,
    "step2_c1": build_step2_c1,
}


def steps_to_plan(steps, exclude=None):
    """v1 content steps → {"format": "wb-flows-v1", "flows": [...],
    "unsupported": [스텝키]} — 미지원 스텝은 커버리지 리포트용으로 기록."""
    exclude = set(exclude or [])
    flows = []
    unsupported = []
    for step_key, step_data in steps.items():
        if step_key in exclude:
            continue
        builder = STEP_BUILDERS.get(step_key)
        if builder is None:
            unsupported.append(step_key)
            continue
        built = builder(step_data)
        target = dict(STEP_MAP.get(step_key, {}))
        flow = {"step": step_key, "target": target,
                "break_per_unit": True, "units": built["units"]}
        if built.get("ul_style"):
            flow["ul_style"] = built["ul_style"]
        flows.append(flow)
    return {"format": "wb-flows-v1", "flows": flows,
            "unsupported": sorted(unsupported)}
