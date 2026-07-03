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

W3 (아이콘 4스텝): 단락 dict에 선택 필드 "icon"을 지원 —
  {"t": ..., "s": ..., "runs": [...],
   "icon": {"label": "TF 버튼", "pos": "end"|"start", "pad": " ",
            "mode": "dup"(기본)|"place"}}
실행기(core/jsx/workbook_flow.body.jsx)가 스타일/밑줄/브레이크 이후 마지막
패스에서 역순으로 findLabeledItem(label) 원본을 duplicate(또는 itemLink
place — v1 processStep2B1의 링크 place + 너비 스케일) 인라인 앵커 삽입.
pad는 아이콘과 본문 사이 간격 문자(end면 아이콘 앞, start면 아이콘 뒤).
스타일 "$BASIC"은 문서 내장 [기본 단락] 센티널 — 인벤토리 실물 스타일이
아니라 InDesign 문서 기본 스타일이므로 자동 생성 금지 규칙과 무관.
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


# ── W3 공용: 아이콘 스텝용 헬퍼 ─────────────────────────────────────────────

# v1 hasCircled (1B1에서 사용하는 넓은 원문자 집합: ①~⑳ + ⓵~⓿ + ❶~❿)
_RE_CIRCLED_WIDE = re.compile("[①-⑳⓵-⓿❶-❿]")
# v1 startsWithDaeum: /^(\s*[“”‘’"']*)다음/
_RE_DAEUM = re.compile("^\\s*[\"'“”‘’]*다음")
# v1 STEP1A2 TF 토큰: ❮ T / F ❯
_RE_TF_TOKEN = re.compile("❮\\s*T\\s*/\\s*F\\s*❯")
# v1 STEP1B1 주제/제목 검출: /^\s*\{?\s*(주제|제목)\s*\}?(\s|$)/
_RE_SUBJ_HEAD = re.compile(r"^\s*\{?\s*(주제|제목)\s*\}?(?:\s|$)")
# v1 STEP1B1 교체 정규식(뒤 공백까지 소비): ^(\s*)\{?\s*주제\s*\}?\s*
_RE_SUBJ_STRIP = {
    "주제": re.compile(r"^\s*\{?\s*주제\s*\}?\s*"),
    "제목": re.compile(r"^\s*\{?\s*제목\s*\}?\s*"),
}
# v1 STEP2C2 소괄호 번호 단독줄: ^\s*\(\d{1,2}\)\s*$
_RE_C2_SOLO_NUM = re.compile(r"^\s*\(\d{1,2}\)\s*$")

_ICON_TF_DUP = {"label": "TF 버튼", "pos": "end", "pad": " "}
_ICON_TF_PLACE = {"label": "TF 버튼", "pos": "end", "pad": " ",
                  "mode": "place"}
_ICON_STEP1_Q = {"label": "STEP1 문제아이콘", "pos": "start", "pad": "\t"}
_ICON_STEP2_ANS = {"label": "STEP2 영작 답지", "pos": "start"}


def _cut_span(text, runs, start, end):
    """text[start:end] 구간을 텍스트+runs에서 동시에 제거 (오프셋 정합 유지)."""
    new_text = text[:start] + text[end:]
    new_runs = []
    off = 0
    for r in runs or []:
        t = r.get("t") or ""
        a, b = off, off + len(t)
        head = t[:max(0, min(len(t), start - a))]
        tail = t[max(0, min(len(t), end - a)):]
        kept = head + tail
        if kept:
            new_runs.append(dict(r, t=kept))
        off = b
    return new_text, new_runs


# ── STEP1 A2: 본문 O/X — v1 processStep1A2 ──────────────────────────────────
# 전체 기본 단락 → bracket 뒤 영어 본문 = A2_본문 박스, ❮T/F❯ 토큰 단락 =
# A2_OX문제 + 토큰 제거 + TF 버튼 duplicate 삽입. bracket 위 빈 단락 제거(≤5),
# bracket 기준 유닛 분할(=프레임브레이크). bracket/빈 단락은 [기본 단락] 유지.

def build_step1_a2(step_data):
    st_box = _style("STEP1A2", "P")
    st_ox = _style("STEP1A2", "OX")
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if _is_bracket_para(text):
            if seen_bracket and cur:
                # v1 insertFrameBreaksAtBrackets: bracket 위 빈 단락 제거(최대 5)
                guard = 5
                while cur and guard > 0 and _is_blank(cur[-1]["t"]):
                    cur.pop()
                    guard -= 1
                units.append(cur)
                cur = []
            seen_bracket = True
            cur.append(_mk(text, "$BASIC", runs))
            continue
        n_tok = 0
        while True:
            m = _RE_TF_TOKEN.search(text)
            if not m:
                break
            text, runs = _cut_span(text, runs, m.start(), m.end())
            n_tok += 1
        if n_tok > 0:
            item = _mk(text, st_ox, runs)
            item["icon"] = dict(_ICON_TF_DUP)
            if n_tok > 1:
                warnings.append("step1_a2: 한 단락에 TF 토큰 " + str(n_tok)
                                + "개 → 아이콘 1개만 삽입: " + text[:40])
            cur.append(item)
            continue
        if _is_blank(text):
            cur.append(_mk(text, "$BASIC", runs))   # v1: 기본 단락 유지
            continue
        if seen_bracket and re.search(r"[A-Za-z]", text):
            cur.append(_mk(text, st_box, runs))     # bracket 뒤 영어 → 박스
        else:
            cur.append(_mk(text, "$BASIC", runs))   # 섹션 제목 등 비영어
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 B1: 본문 정리 — v1 processStep1B1 ─────────────────────────────────
# {주제}/{제목} 정규화(단독줄은 다음 단락과 병합), bracket(2번째+)·"다음" 발문
# 기준 유닛 분할, 선지 위/제목 앞 빈 줄 보장, "다음" 발문에 STEP1 문제아이콘+탭.

def build_step1_b1(step_data):
    st_all = _style("STEP1B1", "*")
    st_subj = _style("STEP1B1", "SUBJ")
    st_title = _style("STEP1B1", "TITLE")
    st_q = _style("STEP1B1", "Q")
    st_jim = _style("STEP1B1", "P@bottom")
    st_c = _style("STEP1B1", "C")
    st_box = _style("STEP1B1", "Box")
    src = list(step_data.get("paragraphs", []) or [])
    warnings = []

    # 1) {주제}/{제목} 정규화 — v1 grepChange 3종 + 스타일 패스의 합성.
    #    단독줄("주제")은 다음 비공백 단락과 병합("{주제} <내용>"), 인라인은
    #    접두만 "{주제} "로 재작성. tag로 SUBJ/TITLE 스타일 지정을 예약.
    items = []
    i = 0
    while i < len(src):
        text = src[i].get("text") or ""
        runs = src[i].get("runs") or []
        m = _RE_SUBJ_HEAD.match(text)
        if m:
            kind = m.group(1)
            strip_end = _RE_SUBJ_STRIP[kind].match(text).end()
            prefix = "{" + kind + "} "
            if not text[strip_end:].strip():
                j = i + 1
                while j < len(src) and _is_blank(src[j].get("text") or ""):
                    j += 1
                if j < len(src):
                    nxt_t = src[j].get("text") or ""
                    nxt_r = src[j].get("runs") or []
                    items.append({"t": prefix + nxt_t,
                                  "runs": [{"t": prefix, "ul": False}]
                                  + list(nxt_r),
                                  "tag": kind})
                    i = j + 1
                    continue
                items.append({"t": text, "runs": runs, "tag": None})
                i += 1
                continue
            body_t, body_r = _cut_span(text, runs, 0, strip_end)
            items.append({"t": prefix + body_t,
                          "runs": [{"t": prefix, "ul": False}] + body_r,
                          "tag": kind})
            i += 1
            continue
        items.append({"t": text, "runs": runs, "tag": None})
        i += 1

    # 2) 스타일 결정 (v1 적용 순서: 전체 B1 → 선지 → 하단 → 지문/본문박스
    #    → 주제/제목 → '[' 시작 단락 [기본 단락])
    out = []
    for it in items:
        text = it["t"]
        style = st_all
        if _RE_CIRCLED_WIDE.search(text) and not _RE_DAEUM.match(text):
            style = st_c
        if _RE_DAEUM.match(text):
            style = st_q
        out.append(_mk(text, style, it["runs"]))
    for k in range(len(items) - 1):
        if (_RE_DAEUM.match(items[k]["t"])
                and re.search(r"[A-Za-z]", items[k + 1]["t"])):
            out[k + 1]["s"] = st_jim
        if _is_bracket_para(items[k]["t"]):
            out[k + 1]["s"] = st_box
    for k, it in enumerate(items):
        if it["tag"] == "주제":
            out[k]["s"] = st_subj
        elif it["tag"] == "제목":
            out[k]["s"] = st_title
        zs = re.sub("^[\\s\u00a0\u2000-\u200b]+", "", it["t"])
        if re.match("^[\\[［]", zs):
            out[k]["s"] = "$BASIC"      # v1: bracket 단락 → 기본 단락

    # 3) 선지(원문자) 위 빈 줄 보장 (역순 — v1과 동일 조건)
    k = len(out) - 1
    while k > 0:
        t = out[k]["t"]
        if _RE_CIRCLED_WIDE.search(t) and not _RE_DAEUM.match(t):
            prev = re.sub(r"[\r\n]", "", out[k - 1]["t"])
            if prev != "" and not _RE_CIRCLED_WIDE.search(prev):
                out.insert(k, _mk("", st_all, []))
        k -= 1

    # 4) {제목} 앞 빈 줄 보장 (역순)
    k = len(out) - 1
    while k >= 1:
        if out[k]["s"] == st_title:
            prev = re.sub(r"[\r\n]", "", out[k - 1]["t"])
            if prev != "":
                out.insert(k, _mk("", st_title, []))
        k -= 1

    # 5) "다음" 발문에 아이콘+탭 (실행기 최종 패스에서 삽입)
    for item in out:
        if _RE_DAEUM.match(item["t"]):
            item["icon"] = dict(_ICON_STEP1_Q)

    # 6) 유닛 분할: bracket(2번째+) + 모든 "다음" 발문 (v1 프레임브레이크 대상)
    units = []
    cur = []
    seen_bracket = False
    for item in out:
        t = item["t"]
        if _is_bracket_para(t):
            if seen_bracket and cur:
                units.append(cur)
                cur = []
            seen_bracket = True
        elif _RE_DAEUM.match(t) and cur:
            units.append(cur)
            cur = []
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP2 B1: 어법 OX — v1 processStep2B1 ───────────────────────────────────
# insertHeaderBreaks 의미론(헤더 제거+유닛 분할+빈 단락 제거 — W2 재사용),
# 각 내용 단락 끝에 TF 버튼(링크 place + 너비 스케일) 삽입.

def build_step2_b1(step_data):
    st = _style("STEP2B1", "*")
    units = []
    cur = []
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        if is_header_line(text):
            if cur:
                units.append(cur)
                cur = []
            continue
        if _is_blank(text):
            continue    # v1 insertHeaderBreaks 말미 GREP이 빈 줄 일괄 제거
        item = _mk(text, st, p.get("runs") or [])
        item["icon"] = dict(_ICON_TF_PLACE)
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": []}


# ── STEP2 C2: 영작 배열 — v1 processStep2C2 ─────────────────────────────────
# (N) 단독줄·빈 단락·영어 전용(한글/슬래시/bracket 없음) 단락 삭제,
# 한글 2자+ → 번호, 슬래시 → 보기(우선), [/] 포함 → 기본. 보기 블록 끝마다
# 빈 단락+STEP2 영작 답지 아이콘, bracket 앞 빈 줄 2개(이전 유닛 꼬리),
# bracket 기준 유닛 분할 (모의고사 — v1의 EBS 분기는 브레이크 생략이지만
# v2 W3 대상은 모의고사 내지).

def _c2_is_bracket(text):
    # v1 step9 판정: '['와 ']' 포함 + '\s*[' 시작
    return ("[" in text and "]" in text
            and bool(re.match(r"^\s*\[", text)))


def build_step2_c2(step_data):
    st_num = _style("STEP2C2", "Q")
    st_view = _style("STEP2C2", "Box")
    warnings = []

    # 1) 삭제 룰 (v1 1~2단계: (N) 단독줄, 빈 단락, 영어 전용 답 단락)
    kept = []
    for p in step_data.get("paragraphs", []) or []:
        text = p.get("text") or ""
        if _RE_C2_SOLO_NUM.match(text):
            continue
        if _is_blank(text):
            continue    # v1: \r{2,} → \r
        has_br = "[" in text and "]" in text
        eng_only = (re.search(r"[A-Za-z]", text)
                    and not re.search("[가-힣]", text)
                    and "/" not in text)
        if eng_only and not has_br:
            continue    # 영어 정답 문장 삭제
        kept.append(p)

    # 2) 스타일 (v1 3~5단계 + 9단계 bracket→기본 오버라이드)
    styled = []
    for p in kept:
        text = p.get("text") or ""
        style = "$BASIC"
        if _RE_KOR2.search(text):
            style = st_num
        if "/" in text:
            style = st_view
        if "[" in text or "]" in text:
            style = "$BASIC"
        styled.append(_mk(text, style, p.get("runs") or []))

    # 3) 보기 블록 끝마다 빈 단락 + 아이콘 (v1 6단계)
    out = []
    for k, item in enumerate(styled):
        out.append(item)
        if item["s"] == st_view and (k + 1 >= len(styled)
                                     or styled[k + 1]["s"] != st_view):
            icon_para = _mk("", "$BASIC", [])
            icon_para["icon"] = dict(_ICON_STEP2_ANS)
            out.append(icon_para)

    # 4) 유닛 분할 + bracket 앞 빈 줄 2개 보장 (v1 7·9단계 —
    #    빈 줄은 프레임브레이크 앞 = 이전 유닛 꼬리에 붙는다)
    units = []
    cur = []
    seen_bracket = False
    for item in out:
        if _c2_is_bracket(item["t"]):
            if seen_bracket and cur:
                cur.append(_mk("", "$BASIC", []))
                cur.append(_mk("", "$BASIC", []))
                units.append(cur)
                cur = []
            seen_bracket = True
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── 스텝 빌더 레지스트리 (단계 전환: 지원 스텝을 여기서 늘려간다) ────────────

STEP_BUILDERS = {
    "step3": build_step3,
    "step1_a1": build_step1_a1,
    "step1_a1_2": build_step1_a1,   # v1과 동일: 같은 처리, 다른 스토리
    "step1_a2": build_step1_a2,
    "step1_b1": build_step1_b1,
    "step1_b2": build_step1_b2,
    "step1_c2": build_step1_c2,
    "step2_a1": build_step2_a1,
    "step2_a1_btm": build_step2_a1_btm,
    "step2_b1": build_step2_b1,
    "step2_c1": build_step2_c1,
    "step2_c2": build_step2_c2,
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
