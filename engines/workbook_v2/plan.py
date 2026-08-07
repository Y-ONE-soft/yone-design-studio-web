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

W4 (step1_c1 — 최난): v1 processStep1C1(run.jsx 1136~1648)의 이식.
  - 헤더 정규화 GREP 15+ → _sub_runs(밑줄 runs 오프셋 보존 치환)로 전처리
  - 프레임 분리 = v1 "FRAME BREAK 재적용" 섹션(실효 동작)의 유닛화:
      헤더(2번째+) → 유닛 {"page_break": true} = 실행기 NEXT_PAGE
      (EBS는 NEXT_FRAME = page_break 없음), 블록 내 첫 하단 스타일 단락
      → 일반 유닛 경계(NEXT_FRAME)
  - 화살표 답지 아이콘: C1 연속 블록 끝 뒤 빈 단락에 icon op
  - 발문("아래 주어진 문장이…") = 빌더가 텍스트 단락으로 생성 + 문제아이콘

유닛 확장 형식: 기존 유닛(단락 list) 외에 {"paras": [...], "page_break": true}
dict 형식 지원 — 실행기가 page_break 유닛 시작 단락에 NEXT_PAGE 적용.
"""
import json
import os
import re

from core.structure.header_detect import (HeaderSilenceError,
                                          detect_headers)
from core.structure.rules import Q_START_HINT as _RE_Q_START_HINT
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

# v1 processStep3 pass 2 — <보기>/<조건> 표기 정규화 (run.jsx 2197~2200)
_S3_GREPS = [
    (re.compile(r"<\s*보\s*기\s*>"), "<보기>"),
    (re.compile(r"<\s*조\s*건\s*>"), "<조건>"),
    (re.compile(r"\[\s*보기\s*\]"), "<보기>"),
    (re.compile(r"\[\s*조건\s*\]"), "<조건>"),
]
# v1 pass 10 — 번호(S3_NUM) 단락의 "숫자. " 접두 제거 (run.jsx 2423~2431)
_RE_S3_QNUM = re.compile(r"^\d+\.\s")
# W30-r15 (결함 5 — 실서비스 376b34d0 실증): 교과서 꼼꼼변형 실전문제의
# 출처 라인("공통영어2_YBM(김) 1과_03" / "… 1과_01~02" — 문항 끝 단독
# 단락, kind UNKNOWN → 지문 스타일로 인쇄됨). 완제품에 불필요 — 제거.
# 형태: <과목_출판사 토큰(밑줄 포함)> + 공백 + <N과_NN[~NN]> 전체 라인.
# 본문 영어 문장은 '_'가 붙은 선두 토큰 + 'N과_N' 꼬리를 동시에 갖지
# 않아 오매치 없음 (골든 코퍼스 전수 재빌드 diff 0으로 증명).
_RE_S3_TEXTBOOK_SRC = re.compile(r"^\S+_\S+\s+\d+과_\d+(?:\s*~\s*\d+)?$")
# v1 pass 5 번호/INTRO 휴리스틱 (run.jsx 2253~2272) — 분류기(kind)가 약한
# 판정(UNKNOWN/K/Cond)을 내린 단락에만 오버레이. v1 실물 dump 대조에서
# "(주관식) …쓰시오." / "…것은? [2-N]" 발문이 분류기 미인식으로 번호 스타일
# +번호 제거를 못 받는 16건이 실증됨 (교과서 80dd3fa2). v1의 조건 propagation
# 은 번호 스타일 단락을 덮지 않으므로(run.jsx 2417 break) Cond 포함이 파리티.
_RE_S3_KORQ = re.compile(r"[가-힣]\?")
_S3_WEAK_KINDS = {"UNKNOWN", "K", "Cond"}
# W16 c07 (D1) — [서술형 N]/[논술형 N] 접두 태그 발문 + 해요체("쓰세요")
# 발문 (리딩파워 유형편(완성) Unit17 실증: "[서술형 2] … 쓰세요. [출처]"가
# taxonomy·구조 폴백 모두 미인식 → 지문 스타일로 인쇄). 해요체는 해석(K)
# 문장과 충돌 가능 → 발문 시작 신호(Q_START_HINT)와 AND 결합.
_RE_S3_QTAG = re.compile(r"^\[(?:서술|논술)형\s*\d*\]")
_RE_S3_SEYO = re.compile(r"(?:쓰|하|고르|답하|완성하|바꾸|채우)세요")
# W18 c18 (D2) — 시작 신호 없는 해요체 발문 변형: "영어로 번역하세요
# [9강 1번]" (리딩파워 유형편 완성 기출 pool 실증 — 지문 스타일 인쇄) +
# 세로 e79f8af9 기출력 "11. (주관식) … 고르세요. [정답 2개]" 잠복(G13
# 확장 검출). 꼬리 [출처/태그]를 제거한 몸통이 세요-체 종결이면 발문.
_RE_S3_TAIL_TAG = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
_RE_S3_SEYO_END = re.compile(r"세요\s*[.?!]?\s*$")
# W16 c10 (D2) — 영단어(Word) kind 강등: 어휘 항목은 "word: 한글 뜻"이
# 원칙 (v1 실물 고2_25-6 덤프: 화자 라벨 "Minji:"/"A: …"·영문 제목·
# 안내문 필드 "Dates: …"는 전부 지문 스타일). 한글 뜻이 없거나 콜론 앞
# 머리가 1글자면 지문(P)으로 강등.
_RE_S3_HANGUL = re.compile(r"[가-힣]")
_RE_S3_WORD_BAD_HEAD = re.compile(r"^[A-Za-z]\s*[:：]")
# 대화문 화자 라벨 행("A: 노란색 코트를 … 누구야?") — 물음표가 있어도
# 발문이 아니라 대화 지문. 발문은 화자 라벨로 시작하지 않는다 (c10 실증:
# Word 오분류 수리 후 KORQ 오버레이가 대화행을 발문으로 승격하던 것 차단).
_RE_S3_SPEAKER = re.compile(r"^[A-Za-z][A-Za-z .]{0,12}[:：]")
# v1 pass 11 — 화살표 단독 단락 삭제 + 다음 단락 배경(S3_BG) (run.jsx
# 2433~2450). EBS Unit15 v1 실물 dump 대조에서 "↓" 4건 실증 (모의고사
# 코퍼스에도 19건 존재 — v1 파리티 회복).
_RE_S3_ARROW = re.compile(
    "^[⬇⇩↓↘⇓⬆↑⇧⇑️]+$")
# W39 결함 5: T/F 문항의 번호 괄호 영어 행 (선택 표기 꼬리 없는 근접
# 후보 지목용 — 침묵 강등 금지)
_RE_S3_TF_NEAR = re.compile(r"^\d{1,2}\s*\)\s+\S")
# W40 결함 3: 순서배열 선지 순열 행("(A) － (C) － (B)") — 세 라벨이
# 서로 다른 A/B/C 순열일 때만 (지문의 "(A) 문장" 항목과 형태로 구분).
# 구분자: ASCII/유니코드 대시류 + 전각 하이픈(－ U+FF0D — 0a5da924 실증).
_RE_S3_PERM_ROW = re.compile(
    r"^\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)\s*[-–—−－]\s*\(([ABC])\)$")
_S3_CIRCLED = ["①", "②", "③", "④", "⑤"]
# W39 결함 6: 발문의 "밑줄 친 <영어구>" 인용 — 조사(가/이/은/는/을/를/의)
# 앞까지의 비한글 연속. 원문자 나열("밑줄 친 ①~⑤ 중")과 구분하기 위해
# 영문자 필수. 인용구는 발문에서 밑줄로 인쇄된다 (실물 관행 — 6b66b750
# 실증: 함축의미 발문 인용구가 평문으로 인쇄).
_RE_S3_UL_QUOTE = re.compile(r"밑줄\s*친\s+([^가-힣]+)")


def _apply_ul_span(text, runs, start, end):
    """runs의 [start,end) 구간에 ul=True 부여 (기존 서식 run 분할 보존)."""
    base = runs or [{"t": text, "ul": False}]
    out = []
    pos = 0
    for r in base:
        t = r.get("t") or ""
        a, b = pos, pos + len(t)
        pos = b
        if not t:
            continue
        cuts = sorted({a, b, min(max(start, a), b), min(max(end, a), b)})
        for x, y in zip(cuts, cuts[1:]):
            if x >= y:
                continue
            seg = dict(r)
            seg["t"] = t[x - a:y - a]
            if x >= start and y <= end:
                seg["ul"] = True
            out.append(seg)
    return out


def _s3_underline_quotes(unit, st_q, st_p, st_bg, warnings):
    """W39 결함 6 — 발문이 '밑줄 친 <영어구>'를 인용하면 렌더에서 밑줄.

    (a) 발문 라인의 인용구 자체 (원고 runs 유무 무관 — 실물 관행),
    (b) 문항에 밑줄 run이 전혀 없으면 지문/배경에서 인용구 유일 일치
        위치에 부여. 대상 특정이 모호(0 또는 2+ 일치)하면 [경고]
        (임의 밑줄 금지)."""
    qi = [i for i, p in enumerate(unit) if p["s"] == st_q]
    for n, i in enumerate(qi):
        p = unit[i]
        m = _RE_S3_UL_QUOTE.search(p["t"])
        if not m:
            continue
        quote = m.group(1).rstrip("  '\"’”")
        # 영단어(2자+) 인용만 — "(A)"/"ⓐ~ⓖ" 류 표식 참조는 인용이
        # 아니라 본문 표식 지시라 제외 (r2c14/r4c03 전수 diff 실측)
        if len(quote) < 2 or not re.search(r"[A-Za-z]{2}", quote):
            continue
        s, e = m.start(1), m.start(1) + len(quote)
        if not any(r.get("ul") for r in _slice_runs(
                p.get("runs") or [{"t": p["t"], "ul": False}], s, e)):
            p["runs"] = _apply_ul_span(p["t"], p.get("runs"), s, e)
        # (b) 문항 범위 = 다음 발문 전까지의 지문/배경 본문
        hi = qi[n + 1] if n + 1 < len(qi) else len(unit)
        body = [q for q in unit[i + 1:hi] if q["s"] in (st_p, st_bg)
                or "지문" in q["s"] or "배경" in q["s"]]
        if any(r.get("ul") for q in body for r in q.get("runs") or []):
            continue          # 원고 밑줄 존재 — 그대로 신뢰
        # 문장/구 인용(3단어+ 또는 15자+)이고 본문이 이 문항 안에 있을
        # 때만 대상 탐지 — '윗글' 공유 지문 참조(본문이 앞 문항에 있음)는
        # 원고 밑줄에 위임 (임의 밑줄 금지 — r4c03 실측)
        if not body or (len(quote) < 15 and len(quote.split()) < 3):
            continue
        if re.match(r"\s*(?:윗\s*글|위\s*글)", p["t"]):
            continue    # '윗글' 참조 — 대상은 앞 공유 지문 (원고 위임)
        hits = [(q, q["t"].find(quote)) for q in body if quote in q["t"]]
        if len(hits) == 1 and hits[0][0]["t"].count(quote) == 1:
            q, at = hits[0]
            q["runs"] = _apply_ul_span(q["t"], q.get("runs"), at,
                                       at + len(quote))
        else:
            warnings.append(
                f"[밑줄] 발문 인용구의 본문 대상 특정 불가"
                f"({len(hits)}건 일치) — 임의 밑줄 미부여: "
                f"'{quote[:40]}'")


def _is_pua(ch):
    """hwp 사용자 영역(PUA) 문자 — BMP U+E000~F8FF + plane 15/16."""
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


def _s3_arrow_para(text):
    """화살표 단독 단락 판정 — 리터럴 화살표 + PUA 인코딩 변형 (W14).

    hwp 심볼표의 요약 화살표(⇩)가 원고에 따라 리터럴이 아닌 사용자
    영역 문자(, \U000f0036 등)로 저장된다 (c05 모의고사 18건 /
    c06 리딩파워 기출 2건 실증). PUA 단독 단락은 InDesign에서 글리프
    없는 tofu로 인쇄되므로 화살표와 동일하게 삭제+다음 단락 배경 처리
    (게이트 G10이 출력 검사로 이중 방어)."""
    t = text.strip()
    if not t:
        return False
    if _RE_S3_ARROW.match(t):
        return True
    return all(_is_pua(ch) for ch in t)


# ── hwp 심볼 PUA 인쇄 매핑 (W20 D1 — c06 인라인 PUA 잠복 W14 (1) 해소) ──────
# hwp 문자표 심볼이 사용자 영역(PUA) 코드로 저장된 채 본문에 혼입되면
# InDesign에서 tofu로 인쇄된다 (인라인이라 화살표 단독 단락 삭제 경로도
# 못 잡음). 문맥 증거가 실증된 코드만 유니코드 정자로 치환한다 — 근거
# 없는 코드는 등재 금지 (G10이 warning으로 지목, 미등재 잠복: U+F09F
# 조건 불릿 / U+F000 인용부호 앞 공백류 / U+F081~F085 문장 마커).
#   U+F0852/U+F0853  겹따옴표 “ ” — c06 16강 "puts it, ␦Seventy-five
#                    … whole family.␦In other words" + c21 11강 "the
#                    ␦land of opportunity␦ nevertheless" (여닫이 짝 실증)
#   U+F0036/U+F003B/U+F0EA  요약 화살표 ⇩ 변형 — W14 D2 실증(c05 18건/
#                    c06 2건) + W20 모의고사 스텝3 전수 스캔 12폴더·
#                    리딩파워 pool 전부 요약 위치 단독 단락
# 전부 1:1(한 글자) 치환 — _map_chars가 runs 오프셋을 보존한다.
PUA_PRINT_TABLE = str.maketrans({
    "\U000f0852": "“", "\U000f0853": "”",
    "\U000f0036": "⇩", "\U000f003b": "⇩", "": "⇩",
})


def apply_pua_print_map(obj):
    """content 단락 트리에 PUA 인쇄 매핑을 적용한 사본 반환 (원본 무변형).

    "text" 키를 가진 dict는 _map_chars로 텍스트+runs를 함께 치환한다
    (1:1 길이 보존 — 밑줄 runs 오프셋 유지). 매핑에 없는 PUA는 그대로
    통과 (플랜 화살표 판정/G10 게이트가 각자 처리)."""
    if isinstance(obj, list):
        return [apply_pua_print_map(x) for x in obj]
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            out = dict(obj)
            mapped = _map_chars(obj, PUA_PRINT_TABLE)
            out["text"] = mapped["text"]
            if obj.get("runs"):
                out["runs"] = mapped["runs"]
            return out
        return {k: apply_pua_print_map(v) for k, v in obj.items()}
    return obj


# ── 아래첨자 인쇄 매핑 (W23 r13 F3 — 사용자 실측: "₂ 같은 글리프가 폰트
# 때문에 안 보임") ──────────────────────────────────────────────────────────
# 아래첨자 숫자(U+2080~2089, 예: CO₂)는 이 계열 내지의 본문 폰트에 글리프가
# 없어 tofu/공백으로 인쇄된다 (job 6c1430c3 실사용 3차 피드백 — 코퍼스에도
# 06f4b2c2 306건 / 0a5da924 32건 잠복, W11부터 존재). 등가 표기로 치환:
# ASCII 숫자 + 아래첨자 서식 run(sub) — 실행기가 Position.SUBSCRIPT를 직접
# 적용한다 (문자스타일 아님 — seseospecial W7의 underline 속성 직접 적용
# 전례, 자동 생성 금지 규칙과 무관. 어떤 폰트에서든 렌더 가능).
# 게이트 G29가 이 매핑 등재 문자의 출력 잔존을 critical로 소급 검출한다
# (G10 확장의 PUA 테이블과 동일 패턴 — 잔존 = 매핑 미적용 출력).
SUBSCRIPT_PRINT_TABLE = {chr(0x2080 + i): str(i) for i in range(10)}


def _apply_sub_para(para):
    """단락 1개에 아래첨자 매핑 적용 — 텍스트는 ASCII 숫자로, 해당 위치는
    runs에 {"sub": True} 서식 run으로 분리 (1:1 길이 보존 — 밑줄 runs
    오프셋 유지. runs가 없던 단락은 전체를 비밑줄 run으로 실체화)."""
    text = para.get("text") or ""
    idxs = [i for i, ch in enumerate(text) if ch in SUBSCRIPT_PRINT_TABLE]
    if not idxs:
        return para
    runs = para.get("runs") or [{"t": text, "ul": False}]
    pieces = []
    prev = 0
    for i in idxs:
        if i > prev:
            pieces.extend(_slice_runs(runs, prev, i))
        base = _slice_runs(runs, i, i + 1)
        seg = dict(base[0] if base else {"ul": False})
        seg["t"] = SUBSCRIPT_PRINT_TABLE[text[i]]
        seg["sub"] = True
        pieces.append(seg)
        prev = i + 1
    if prev < len(text):
        pieces.extend(_slice_runs(runs, prev, len(text)))
    out = dict(para)
    out["text"] = "".join(SUBSCRIPT_PRINT_TABLE.get(ch, ch) for ch in text)
    out["runs"] = pieces
    return out


def apply_subscript_print_map(obj):
    """content 단락 트리에 아래첨자 인쇄 매핑을 적용한 사본 반환 (원본
    무변형 — apply_pua_print_map과 동일 계층·동일 순회)."""
    if isinstance(obj, list):
        return [apply_subscript_print_map(x) for x in obj]
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str):
            return _apply_sub_para(obj)
        return {k: apply_subscript_print_map(v) for k, v in obj.items()}
    return obj


# ── 글리프 인쇄 매핑 (W30 후속 — r15 c25 실측: ❮❯ 12건 글리프커버리지
# warning) ──────────────────────────────────────────────────────────────────
# 헤비 꺾쇠 ❮(U+276E)/❯(U+276F)는 이 계열 내지 본문 폰트(Noto Sans CJK KR)
# cmap에 글리프가 없어 tofu/미표시로 인쇄된다 (core.fontcov 실측 — Black/
# Bold/DemiLight/Light/Medium/Regular/Thin 전 7웨이트 미지원. r15 c25
# step3 실전문제 지문의 삽입 문장 표기 12건). W23 SUBSCRIPT_PRINT_TABLE
# 전례대로 지원 실측된 등가 문자로 플랜 계층 치환: 홑꺾쇠 〈(U+3008)/
# 〉(U+3009) — 전 7웨이트 커버 실측 (‹›(U+2039/A)·《》(U+300A/B)·＜＞
# (U+FF1C/E)도 커버되나 원표기와 시각적으로 가장 가까운 홑꺾쇠 채택,
# ‹›는 반각이라 삽입 문장 강조 표기에 과소).
#
# 단, 아래첨자/PUA 매핑과 달리 **빌더 이후**에 적용한다 — 1A1 빌더가
# ❮❯→[]를(_A1_TABLE), 1A2 빌더가 ❮T/F❯ 토큰 제거를 소비하므로 빌더 전에
# 치환하면 해당 로직이 무력화된다. 빌더 산출 유닛에 남은 잔존(=그대로
# 인쇄될 문자)에만 적용. 1:1(한 글자) 치환 — 텍스트/runs 오프셋 보존.
# content 원본은 무변형 (골든/파서 산출 보존 — W20 PUA 전례).
# 게이트 G29가 등재 문자의 출력 잔존을 소급 검출한다.
# W? (2026-08-06 실측 — 선택 워크북 조판 게이트 warning 55건):
# ⦁(U+2981 Z NOTATION SPOT)도 Noto Sans CJK KR cmap 미지원(core.fontcov
# 실측 False). 조건/보기 블록의 항목 표시로 쓰여 tofu 로 인쇄된다.
# 커버 실측 결과 •(U+2022) True / ●(U+25CF) True / ∙(U+2219) False —
# 원표기(중간 크기 점)와 가장 가까운 •(U+2022) 채택.
GLYPH_PRINT_TABLE = {"❮": "〈", "❯": "〉", "⦁": "•"}
_GLYPH_PRINT_TRANS = str.maketrans(GLYPH_PRINT_TABLE)


def apply_glyph_print_map_units(units):
    """빌더 산출 유닛 리스트에 글리프 인쇄 매핑을 in-place 적용.

    유닛은 빌더가 갓 생성한 객체(content와 비공유)라 in-place가 안전하다.
    runs는 해당 단락에 등재 문자가 있을 때만 재작성 (1:1 길이 보존)."""
    for u in units:
        for p in unit_paras(u):
            t = p.get("t") or ""
            if not any(ch in t for ch in GLYPH_PRINT_TABLE):
                continue
            p["t"] = t.translate(_GLYPH_PRINT_TRANS)
            if p.get("runs"):
                p["runs"] = [
                    dict(r, t=r["t"].translate(_GLYPH_PRINT_TRANS))
                    if isinstance(r.get("t"), str) else r
                    for r in p["runs"]]
    return units


def _s3_effective_kind(kind, text):
    # W16 D2 — 영단어 강등 (분류기 수리와 이중 방어: content-only 코퍼스
    # 재실행은 구버전 kind 주석을 그대로 쓰므로 플랜 계층에서도 강등).
    if kind == "Word":
        t = text.strip()
        if not _RE_S3_HANGUL.search(t) or _RE_S3_WORD_BAD_HEAD.match(t):
            return "P"
        return kind
    if kind not in _S3_WEAK_KINDS:
        return kind
    if _RE_S3_SPEAKER.match(text.strip()):
        return kind                     # W16 — 대화 화자 라벨 행은 발문 아님
    if _RE_S3_QTAG.match(text.strip()):
        return "Q"                      # W16 D1 — [서술형 N] 접두 발문
    if _RE_S3_KORQ.search(text):
        return "Q"
    if "다음 글을 읽고 물음에" in text:
        return "Q-INTRO"
    if "시오" in text:
        return "Q"
    if _RE_S3_SEYO.search(text) and _RE_Q_START_HINT.match(text.strip()):
        return "Q"                      # W16 D1 — 해요체 발문 (시작 신호 AND)
    from core.structure import block_grammar as _BG
    if _BG.is_english_question(text):
        return "Q"                      # W38 결함 5 — 영어 지시문 발문
                                        # (번호 + 명령형/WH — 파서 수리와
                                        # 이중 방어, 구 kind 주석 재실행용)
    core = text.strip()
    while True:                         # W18 D2 — 꼬리 [출처/태그] 제거
        nx = _RE_S3_TAIL_TAG.sub("", core)
        if nx == core:
            break
        core = nx
    if (core != text.strip() and _RE_S3_SEYO.search(core)
            and _RE_S3_SEYO_END.search(core)):
        return "Q"                      # W18 D2 — 해요체 + 꼬리 태그 발문
    return kind


def _ansline_fields(eff, arrow_bg=False):
    """답란(AnsL) 단락의 폴백/브릿지 필드 (W45).

    사용자 확정 스펙: 답란은 **답란 전용 스타일 `S_답란`**(지문 스타일 복제 +
    들여쓰기 0)로 인쇄한다. 완성본 다수가 답란을 '지문 스타일'로 갖고 있던 건
    의도가 아니라 회피였다 — 선지 스타일의 들여쓰기 때문에 답란 정렬이
    깨져서 손으로 바꾼 것 (역학습 W44, 61건/13문서).

    조판 템플릿에 `S_답란`이 아직 없을 수 있으므로 fail-open:
      s     = "STEP 03 > S_답란"          (1선)
      s_fb  = "STEP 03 > S_선지 올림포스"  (템플릿에 s가 없을 때 렌더 폴백)
      ind0  = True                        (폴백을 쓴 경우에만 들여쓰기 0
                                           로컬 오버라이드 — 브릿지)
    JSX(workbook_flow / workbook_sero_flow)가 s→s_fb 순으로 해석하고,
    s_fb를 쓴 단락에만 ind0를 적용한다 (S_답란이 있으면 오버라이드 없음)."""
    if eff != "AnsL" or arrow_bg:
        return {}
    fb = _style("STEP3", "AnsL@fallback", default_kind="C")
    if not fb:
        return {}
    return {"s_fb": fb, "ind0": True}


def build_step3(step_data):
    """step3 데이터 {normal:[{question_num, paragraphs}], short:[...]} → 유닛.

    W38 — 블록 문맥 오버레이 (core.structure.block_grammar): 파서 kind
    주석이 구버전(콘텐츠-only 코퍼스 재실행)이어도 <조건>/[요약문] 블록
    문맥이 라인 판정을 제약하도록 플랜 계층에서 같은 규칙을 적용한다
    (파서 수리와 이중 방어 — W16 D2 전례). 유닛별 최종 판정 시퀀스는
    block_grammar.validate_sequence 하드 불변식으로 검증해 [경고] 지목.

    W39 — 유형 주도 슬롯 배정 (파서와 이중 방어): 1패스(기존 오버레이)로
    eff를 확정한 뒤, 2패스에서 발문 유형의 기대 슬롯(주어진 블록)을 형태
    신호로 배정한다. 배정 불가 단락은 침묵 강등하지 않고 [경고]로 지목."""
    from core.structure import block_grammar as BG
    from core.structure import rules as R
    st_q = _style("STEP3", "Q")
    units = []
    warnings = []
    for group in ("normal", "short"):
        for item in step_data.get(group, []) or []:
            arrow_pending = False
            in_cond = False          # W38: <조건> 블록 열림 상태
            cond_no = 1              # 다음 조건 항목 번호 기대값
            sum_bg = False           # W38: [요약문] 배경 전파 상태
            pre = []                 # 1패스 산출 (슬롯 배정 전)
            for p in item.get("paragraphs", []):
                text = p.get("text", "")
                kind = p.get("kind") or "UNKNOWN"
                tclean = text.strip()
                if kind in ("GH", "A", "BLANK"):
                    continue          # 제거 대상 (style_map에서 null)
                if _s3_arrow_para(text):
                    arrow_pending = True     # v1 pass 11: 화살표 단락 삭제
                    continue
                if _RE_S3_TEXTBOOK_SRC.match(tclean):
                    continue    # W30-r15: 교과서 실전문제 출처 라인 제거
                                # (결함 5 — 배경 대기(arrow_pending)는
                                # SRC 마커와 동일하게 소비하지 않고 통과)
                eff = _s3_effective_kind(kind, text)
                # ── W38 블록 문맥 오버레이 ──────────────────────────────
                if BG.SUM_MARKER.match(tclean):
                    eff = "Sum"
                    sum_bg = True
                    in_cond = False
                elif sum_bg:
                    # 구 kind 주석 방어 (W39): 꺾쇠형 <요약문> 시절 Box로
                    # 주석된 요약 문장도 배경으로 — 단 마커 라인(<보기> 등
                    # 새 블록 진입)은 전파 종료 (stale Box 콘텐츠 한정).
                    stale_box = (eff == "Box"
                                 and not R.BOX_MARKERS["Box"].match(tclean)
                                 and not R.BOX_MARKERS["Cond"].match(tclean)
                                 and not R.C_START.match(tclean)
                                 and not R.C_AB_HEADER.match(tclean))
                    if eff in ("P", "K", "UNKNOWN") and tclean or stale_box:
                        eff = "P-CONTEXT"
                    else:
                        sum_bg = False
                if R.BOX_MARKERS["Cond"].match(tclean):
                    in_cond = True
                    cond_no = 1
                    sum_bg = False
                elif in_cond:
                    # W39 결함 3: 블록 안 단어 나열은 조건 내용물 (구
                    # kind 주석 P/UNKNOWN/C 방어 — 파서 수리와 이중)
                    if eff in ("P", "UNKNOWN", "Word", "C", "K") \
                            and BG.is_cond_wordlist(tclean):
                        eff = "Cond"
                    elif (R.COND_BLOCK_END.search(tclean)
                            or eff in ("Q-INTRO", "GH", "A", "Ans",
                                       "Box", "Sum", "C")):
                        in_cond = False
                    elif eff == "Q":
                        take, cond_no = BG.cond_item_take(tclean, cond_no)
                        if take:
                            eff = "Cond"   # 블록 문맥 우선 — 조건 항목
                        else:
                            in_cond = False   # 진짜 발문 = 블록 종료
                    elif eff == "Cond":
                        cond_no = BG.cond_item_seen(tclean, cond_no)
                # v1 pass 11: 화살표 다음 단락 → 배경(S3_BG). 출처
                # 마커(SRC)는 배경을 소비하지 않고 통과 — 배경은 마커
                # 다음 실제 요약문/주어진 문장에 부여 (W15 c04).
                arrow_bg = False
                if arrow_pending and kind != "SRC":
                    arrow_bg = True
                    arrow_pending = False
                pre.append({"text": text, "tclean": tclean, "kind": kind,
                            "eff": eff, "arrow_bg": arrow_bg,
                            "q_code": p.get("q_code"),
                            "runs": p.get("runs") or []})

            # ── 2패스: 유형 주도 슬롯 배정 (W39) ────────────────────────
            _s3_number_order_rows(pre)
            warnings.extend(_s3_assign_slots(pre, BG))

            # ── 3패스: 스타일 확정 + 유닛 생성 ──────────────────────────
            unit = []
            eff_seq = []
            for row in pre:
                style = _style("STEP3", row["eff"])
                if style is None:
                    continue
                if row["arrow_bg"]:
                    style = _style("STEP3", "P-CONTEXT")
                eff_seq.append((row["eff"], row["tclean"]))
                text, runs = row["text"], row["runs"]
                for rx, repl in _S3_GREPS:
                    text, runs = _sub_runs(rx, repl, text, runs)
                if style == st_q:
                    text, runs = _sub_runs(_RE_S3_QNUM, "", text, runs)
                para = {"t": text, "s": style, "runs": runs}
                para.update(_ansline_fields(row["eff"], row["arrow_bg"]))
                unit.append(para)
            if unit:
                _s3_underline_quotes(unit, st_q, _style("STEP3", "P"),
                                     _style("STEP3", "P-CONTEXT"),
                                     warnings)
                # 지문번호 라벨 — v1 processStep3 파리티.
                # v1(run.jsx)은 문항마다 "{code}" 단락을 맨 앞에 넣는데
                # v2 빌더에는 이 처리가 없어 실전 섹션에만 지문번호가
                # 통째로 빠져 있었다 (2026-08-07 실측: 실전 55p 코드 0개.
                # 문서 전체 코드 검사는 통과해 기계검증이 못 잡음).
                code = (item.get("code") or "").strip()
                if code:
                    unit.insert(0, {"t": "{" + code + "}", "s": "$BASIC",
                                    "runs": []})
                units.append(unit)
                warnings.extend(BG.validate_sequence(eff_seq))
    return {"units": units, "warnings": warnings}


def _s3_number_order_rows(pre):
    """순서배열 선지 순열 행 5연속에 원문자 부여 + 선지(eff C) 확정.

    W40 결함 3: 원고의 hwpx 2열 표(번호 셀|순열 셀) 병합은 파서
    (_merge_step3_split_choice_numbers 선호출)가 1선. 이 함수는 (a) 병합
    이전에 수집된 구 content.json 재플랜과 (b) 원고 자체에 번호가 없는
    원고의 폴백 — **순열 형태 행 5연속 + 전부 번호 없음**일 때만 ①~⑤를
    부여한다 (기존 자동번호와 같은 글리프. 파서가 병합한 행은 ①로 시작해
    C_START(kind C)로 이미 선지 — 여기 오지 않는다)."""
    i, n = 0, len(pre)
    while i < n:
        m = _RE_S3_PERM_ROW.match(pre[i]["tclean"])
        if not m or len(set(m.groups())) != 3:
            i += 1
            continue
        j = i
        run = []
        while j < n:
            mj = _RE_S3_PERM_ROW.match(pre[j]["tclean"])
            if not mj or len(set(mj.groups())) != 3:
                break
            run.append(pre[j])
            j += 1
        if len(run) == 5:
            for d, row in zip(_S3_CIRCLED, run):
                prefix = d + " "
                row["text"] = prefix + row["text"]
                row["tclean"] = prefix + row["tclean"]
                row["eff"] = "C"
                if row["runs"]:
                    row["runs"] = ([{"t": prefix, "ul": False}]
                                   + list(row["runs"]))
        i = j


def _s3_assign_slots(pre, BG):
    """유형 주도 슬롯 배정 2패스 (파서 컨텍스트 패스와 이중 방어).

    주어진 블록: 발문 유형의 실측 시퀀스(block_sequences.json)가 발문
    직후 배경 단락을 기대하면, 그 자리의 단락을 형태 신호로 배정한다.
    배정 불가(형태 불일치) 단락은 침묵 강등 금지 — [경고] + 후보 슬롯."""
    warn = []
    last_q = None            # (q_code, 발문 텍스트)
    given_pending = False    # 발문 직후 첫 유의 단락 대기 상태
    demote_pending = False   # W40 결함 4: 유형이 슬롯 비기대 — 구 주석 강등
    for row in pre:
        eff = row["eff"]
        if eff in ("Q", "Q-INTRO"):
            last_q = (row.get("q_code"), row["tclean"])
            given_pending = BG.expects_given_block(last_q[0], last_q[1])
            # 유형이 분류됐는데 주어진 블록을 기대하지 않으면(선지 직행
            # 실측 — OBJ-GRM-PAREN 등), 발문 직후 P-CONTEXT 구 주석은
            # 판정 2 오배정 잔재다 (0a5da924 215번 실증) — 지문으로 강등.
            # Q 한정 (Q-INTRO 묶음 인트로 뒤 장문 배열형의 주어진 글 보존).
            demote_pending = (eff == "Q" and bool(last_q[0])
                              and not given_pending)
            continue
        if not row["tclean"] or row["kind"] == "SRC" \
                or (row["eff"] == "UNKNOWN"
                    and BG.BRACKET_LABEL.match(row["tclean"])):
            continue         # 빈 단락/출처 마커/구조 라벨은 슬롯 비소비
        if demote_pending:
            # 발문 직후 첫 유의 단락에만 적용 (W40 결함 4). 요약 빈칸
            # 선택형의 요약문 형태(인라인 (A)/(B) 빈칸)는 배경 유지.
            demote_pending = False
            if eff == "P-CONTEXT" and not row["arrow_bg"] \
                    and not BG.is_summary_blank_form(row["tclean"]):
                row["eff"] = "P"
                eff = "P"
        # T/F 선택 행 (W39 결함 5 — 구 kind 주석 이중 방어)
        if last_q and BG.is_tf_question(last_q[1]) \
                and eff in ("P", "UNKNOWN", "K", "Word"):
            if BG.is_tf_choice_row(row["tclean"]):
                row["eff"] = "C"
                continue
            if _RE_S3_TF_NEAR.match(row["tclean"]) \
                    and not _RE_S3_HANGUL.search(row["tclean"]):
                warn.append(
                    "[슬롯] 선지행(T/F) 후보가 선택 표기 꼬리 없음 — "
                    f"배정 불가 지목: '{row['tclean'][:40]}'")
        if given_pending:
            given_pending = False
            verdict = BG.given_slot_scan(
                eff, row["tclean"], prior_only=not (last_q and last_q[0]))
            if verdict == "assign":
                if not row["arrow_bg"]:
                    row["eff"] = "P-CONTEXT"
                continue
            if verdict == "warn":
                warn.append(
                    "[슬롯] 주어진 블록 배정 불가 — 발문 유형은 배경 "
                    f"단락을 기대하나 형태 불일치(현재 {eff}): "
                    f"'{row['tclean'][:40]}' (발문: "
                    f"'{(last_q[1] if last_q else '')[:30]}')")

    # 답란 쌍 (W39 결함 4 — 구 kind 주석 이중 방어): "라벨:" + 밑줄 빈칸
    from core.structure import rules as R
    meaningful = [r for r in pre if r["tclean"]]
    for x, row in enumerate(meaningful):
        if row["eff"] not in ("UNKNOWN", "K") \
                or not BG.ANS_LABEL.match(row["tclean"]):
            continue
        nxt = meaningful[x + 1] if x + 1 < len(meaningful) else None
        if nxt and (nxt["eff"] in ("Ans", "AnsL")
                    or any(p.match(nxt["tclean"])
                           for p in R.ANS_PATTERNS[:2])):
            row["eff"] = "AnsL"
            nxt["eff"] = "AnsL"

    # 괄호 라벨 답란 (W40 결함 5 — 구 kind 주석 이중 방어): 보기/조건
    # 블록 내용 직후의 "(A) ______" 라인은 답란(AnsL)이다 — 파서 수리
    # 이전 content의 Box 흡수 주석(보기 스타일)·Ans 주석(지문 관행)을
    # 위치(블록 뒤) + 형태(괄호 라벨 + 밑줄 런) 신호로 승격.
    prev_eff = None
    for row in meaningful:
        if row["eff"] in ("Box", "Ans", "Cond") \
                and BG.ANS_PAREN_BLANK.match(row["tclean"]) \
                and prev_eff in ("Box", "Cond", "AnsL"):
            row["eff"] = "AnsL"
        prev_eff = row["eff"]

    # 서답형 답란 표 (2026-08-06 사용자 지적: "(기호)(어색한 표현)
    # (고친 표현) 이런 게 지문이 아니잖아"). 어법 수정 문항의 답란은
    #   "(기호)  (어색한 표현)  (고친 표현)"      ← 열 머리
    #   "(     ) ____________ → ____________"    ← 기입 줄 ×N
    # 형태인데 지문 스타일로 인쇄되고 있었다. 열 머리는 괄호 라벨만
    # 2개 이상, 기입 줄은 괄호 + 밑줄 + 화살표로 판별한다.
    for x, row in enumerate(meaningful):
        # 이미 AnsL 이면 통과. "Ans" 는 **지문 스타일**로 인쇄되므로
        # 답란 표의 기입 줄이면 AnsL 로 승격해야 한다 (2026-08-06 실측:
        # 열 머리만 S_답란 이 되고 기입 줄 2개가 지문 스타일로 남음).
        if row["eff"] == "AnsL":
            continue
        t = row["tclean"]
        is_head = (len(_RE_PAREN_LABEL.findall(t)) >= 2
                   and len(t) <= 40 and "_" not in t)
        is_row = bool(_RE_ANS_ARROW_ROW.match(t))
        if not (is_head or is_row):
            continue
        # 열 머리는 바로 뒤에 기입 줄이 와야 한다 (오검출 차단)
        if is_head:
            nxt = meaningful[x + 1] if x + 1 < len(meaningful) else None
            if not (nxt and _RE_ANS_ARROW_ROW.match(nxt["tclean"])):
                continue
        row["eff"] = "AnsL"
    return warn


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
#
# W49 (실서비스 0e3e6469 영어Ⅱ_YBM(박) 1과 실증): 지문번호는 단일 순번(본문2)
# 뿐 아니라 하위분할(major-minor) 순번(본문2-1, 본문2-2)을 가진다 — 한 지문이
# 분량상 둘로 쪼개진 경우. 하위분할 '-M'도 순번의 일부이므로 `본문\d+` 뒤에
# `-M`이 오면 기존 패턴이 매칭에 실패해(본문2 뒤 '('/'$'만 허용) legacy 인식이
# 0 → 구조 인식기의 seq(단조성)로만 잡혀, seq 제외 규칙이 있는 step2_c2가 헤더를
# 못 지우고 원문 그대로 인쇄(G1 [헤더잔존]). 어휘 특례가 아니라 '순번은 계층적
# (major.minor)일 수 있다'는 구조 일반화로 `_ORD`를 도입해 전 패턴 공유한다.
_ORD = r"\d+(?:[-–—.]\d+)*"     # 계층적 순번: 3, 2-1, 4.2 …
_HEADER_PATTERNS = [
    re.compile(r"^L\d+[-–—]본문" + _ORD + r"(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^[A-Za-z]{1,15}\d*[-–—]본문" + _ORD + r"(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—][A-Za-z]{1,30}(?:\([^\)]{0,40}\))?$"),
    re.compile(r"^L\d+[-–—]p\.?\d+(?:~\d+)?(?:[A-Za-z]{1,20})?$", re.I),
    re.compile(r"^p\d+[-–—\.]?(?:no\.)?\d+(?:~\d+)?(?:\([^\)]{0,40}\))?$",
               re.I),
    # 교과서 추가지문형 — 지문번호 뒤 한글 라벨 꼬리 ("p1-no.3과 추가지문",
    # W11): compact 매칭이라 공백 제거 후 한글 연속. 기존 패턴 무변경 append.
    re.compile(r"^p\d+[-–—\.]?(?:no\.)?\d+(?:~\d+)?[가-힣][가-힣0-9]{0,30}"
               r"(?:\([^\)]{0,40}\))?$", re.I),
    re.compile(r"^p\d+[-–—]?Example\d*$", re.I),
    re.compile(r"^p\d+[-–—][A-Za-z]{1,15}\.?\d+(?:~\d+)?$", re.I),
    re.compile(r"^p\d+[-–—](?:서술형|논술형)Practice$", re.I),
    re.compile(r"^p\d+[-–—]+수능대비ANALYSIS$", re.I),
    # 부교재 코너명형 (W12): "1. p80-수능 Analysis" — compact "p80-수능Analysis".
    # 기존 패턴 무변경 append.
    re.compile(r"^p\d+[-–—]?수능Analysis$", re.I),
    # 외부지문 무-p형 (W21 r11 — 성덕 외부지문 실사용 실증): "1. no.1" 처럼
    # 페이지 없이 지문 순번만 있는 헤더. v1 isHeaderLine도 미인식이라 v1
    # 렌더 출력엔 헤더가 그대로 인쇄됐고(3664cc0e 조판_로그 '헤더 0개'),
    # 실물 .indd(워크북03(외부지문))는 조판사가 손으로 헤더 제거+프레임
    # 분리를 복원한 상태 — 완제품 기준으로 v2가 인식한다. 기존 패턴 무변경
    # append ("N. " 접두 제거 후 compact "no.1" 형태만 매치).
    re.compile(r"^no\.?\d+(?:~\d+)?$", re.I),
    # 교과서 L-p-코너명형 (W30-r15 — 실서비스 376b34d0 실증): "1. L1-p. 13
    # 본문 1" → compact "L1-p.13본문1". 기존 L-p 패턴(위 4번째)은 한글
    # 꼬리를 허용하지 않아 미인식 → step1_c2/step2_b1/step2_c1이 지문
    # 6개를 유닛 1개 통짜로 배치 + 헤더 원문 인쇄 (사용자 지목 결함 2~4).
    # 기존 패턴 무변경 append.
    re.compile(r"^L\d+[-–—]p\.?\d+(?:~\d+)?[가-힣][가-힣0-9]{0,30}"
               r"(?:\([^\)]{0,40}\))?$", re.I),
    # 교과서 L-한글라벨형 (W30-r15 — 같은 원고): "6. L1-추가본문" →
    # compact "L1-추가본문". 페이지/숫자 없이 한글 라벨만 직결된 형태.
    # 숫자 없는 한글 꼬리라 기존 어느 패턴에도 안 걸렸다.
    re.compile(r"^L\d+[-–—][가-힣][가-힣0-9]{0,30}(?:\([^\)]{0,40}\))?$"),
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


# ── W31: 구조 우선 헤더 인식 (문서 단위 — 정규식 열거는 프라이어로 강등) ─────
# 새 인식기(core/structure/header_detect)가 1선, 기존 is_header_line/
# is_a1_header는 legacy 프라이어(가산점 + 하위호환 보장 — legacy 인식분은
# 항상 유지). False로 내리면 기존 정규식 열거 단독 동작 (안전 밸브).
USE_STRUCT_HEADER_DETECT = True


def _step_header_detection(step_data, step_name, legacy, strict=True):
    """스텝 원고 전체를 문서 단위로 훑어 헤더 인덱스 집합을 얻는다.

    strict=True: 침묵 금지 — 강한 구조 후보(직후 영어 본문)가 2+개인데
    인식이 0~1개면 HeaderSilenceError로 조판 중단 (경고 아님)."""
    texts = [(p.get("text") or "")
             for p in step_data.get("paragraphs", []) or []]
    det = (detect_headers(texts, legacy=legacy)
           if USE_STRUCT_HEADER_DETECT else _legacy_only(texts, legacy))
    if strict and USE_STRUCT_HEADER_DETECT and det.silent():
        raise HeaderSilenceError(step_name, det)
    return det


def _legacy_only(texts, legacy):
    """안전 밸브 경로 — 기존 정규식 열거만으로 Detection 구성."""
    from core.structure.header_detect import Detection
    det = Detection()
    for i, t in enumerate(texts):
        if legacy(t):
            det.header_idx.add(i)
    return det


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
# 외부지문 무-p형 (W21 r11): "1. no.1" — v1 실물(워크북03(외부지문))은
# 조판사가 손으로 {1}~{4} 정규화 + 프레임 분리를 복원했다 (스토리 61 실측).
_RE_A1_NO = re.compile(r"^\s*\d+\s*[.)]?\s*no\.?\s*\d+(?:~\d+)?\s*$", re.I)


def is_a1_header(text):
    t = re.sub(r"[\r\n]", "", text or "")
    return bool(_RE_A1_L.match(t) or _RE_A1_PNO.match(t)
                or _RE_A1_PDESC.match(t) or _RE_A1_ANALYSIS.match(t)
                or _RE_A1_BONMUN.match(t) or _RE_A1_NO.match(t))


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
    # 한글 꼬리가 지문번호에 직결된 추가지문형 ("no.3과 추가지문" → "3과
    # 추가지문", W11) — 번호+꼬리 전체가 라벨. 아래 기존 분기보다 먼저 검사
    # (기존 분기는 번호와 꼬리를 분리해 "과 추가지문"만 남긴다).
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*"
                 r"(\d+(?:~\d+)?[가-힣][가-힣0-9\s]*[가-힣0-9])\s*"
                 r"(?:\([^)]*\))?\s*$", s, re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+[\s-]*no\.?\s*(\d+(?:~\d+)?)"
                 r"(?:[\s-]*(.+))?$", s, re.I)
    if m:
        return m.group(2) if m.group(2) else m.group(1)
    # 외부지문 무-p형 (W21 r11): "1. no.1" → "1" — p-형("1. p2-no.20"→"20")과
    # 동일하게 no-번호를 라벨로 (v1 실물 {1}~{4} 대조). 기존 분기 무변경 삽입.
    m = re.match(r"^\s*\d+[\s.)-]*no\.?\s*(\d+(?:~\d+)?)\s*$", s, re.I)
    if m:
        return m.group(1)
    if re.search(r"수능\s*대비\s*analysis", s, re.I):
        return "분석"
    # 부교재 코너명형 (W12): "N. pN-수능 Analysis" → "분석N" (선행 순번 —
    # C1 GREP {분석N}/원고 [분석N] 마커 관행과 일치). 기존 분기 무변경 삽입.
    m = re.match(r"^\s*(\d+)[\s.)-]*p\.?\s*\d+[\s-]*수능\s*Analysis\s*$",
                 s, re.I)
    if m:
        return "분석" + m.group(1)
    m = re.match(r"^\s*\d+[\s.)-]*p\.?\s*\d+\s*(?:[-–—]|\s)+\s*(.+)$",
                 s, re.I)
    if m:
        return m.group(1)
    return ""


def _mk(text, style, runs):
    return {"t": text, "s": style, "runs": runs or []}


def unit_paras(unit):
    """유닛의 단락 리스트 — list(기존) / {"paras": ...} dict(W4) 겸용."""
    return unit["paras"] if isinstance(unit, dict) else unit


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
    # 지문번호 [N]은 [기본 단락] — v1 processStep1A1은 전체 BASIC_PARA 후
    # 본문 구간에만 A1_어휘 선택을 입히고 bracket은 손대지 않는다 (S1_A_NUM
    # 은 선언만 되고 미사용). v1 실물 대조: 워크북03(외부지문) 스토리 21
    # '[1]' = [기본 단락] (W21 r11 D1 — v2가 NUM을 입히던 것은 이식 오류).
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
            cur.append(_mk(text, "$BASIC", p["runs"]))
        else:
            cur.append(_mk(text, st_body, p["runs"]))
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── STEP1 B2: 내용 종합 — v1 processStep1B2 ─────────────────────────────────
# 지문번호 [N] 기준 유닛 분할, [N] 다음 본문 → A2_본문 박스, (N) → 번호,
# 원문자 → 선지. 빈 단락은 유지(v1 동일) — 스타일은 직전 단락을 따라간다.

def build_step1_b2(step_data):
    # 지문번호 [N]은 [기본 단락] — v1 processStep1B2도 전체 BASIC_PARA 후
    # ']' 닫힘 뒤 본문/번호/선지만 스타일링, bracket은 기본 유지 (W21 r11
    # D3 — v1 실물 워크북03(외부지문) 스토리 137 '[1]' = [기본 단락]).
    st_num = "$BASIC"
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


# 서답형 답란 표 판별 (아래 _promote_ansline 에서 사용)
_RE_PAREN_LABEL = re.compile(r"\([^()]{1,12}\)")
_RE_ANS_ARROW_ROW = re.compile(r"^\s*\([^()]{0,8}\)\s*_{3,}.*(?:→|->).*_{3,}")


# ── STEP1 C2 / STEP2 C1: 빈칸 어휘/어법 — v1 processStep1C2/2C1 ─────────────
# 헤더 제거+유닛 분할(insertHeaderBreaks), 빈 단락 제거, 탭→단락 분할,
# 한글 2자+ 단락 → 한글해석 스타일, 나머지 → 기본 스텝 스타일.

def _build_wordfill(step_data, step_unit):
    st_p = _style(step_unit, "P")
    st_k = _style(step_unit, "K")
    units = []
    warnings = []
    cur = []
    # W31: 구조 우선 인식 (legacy is_header_line은 프라이어) + 침묵 금지
    det = _step_header_detection(step_data, step_unit.lower(),
                                 legacy=is_header_line)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if det.is_header(i):
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
    # W31: 구조 우선 인식 (legacy is_a1_header는 프라이어) + 침묵 금지.
    # 구조 신호로만 잡힌 헤더도 유닛 분할 경계가 된다 ({tail} 정규화는
    # extract_tail이 꼬리를 찾을 때만 — v1 동일: 못 찾으면 원문 유지).
    det = _step_header_detection(step_data, "step2_a1",
                                 legacy=is_a1_header)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        runs = p.get("runs") or []
        if is_a1_header(text) or det.is_header(i):
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
_RE_A2_CHOICE = re.compile(r"[①-⑩]")
_RE_A2_QUESTION = re.compile(r"\d+\s*[.)]\s*(?:윗글|다음)")


# 전체 기본 단락 → bracket 뒤 영어 본문 = A2_본문 박스, ❮T/F❯ 토큰 단락 =
# A2_OX문제 + 토큰 제거 + TF 버튼 duplicate 삽입. bracket 위 빈 단락 제거(≤5),
# bracket 기준 유닛 분할(=프레임브레이크). bracket/빈 단락은 [기본 단락] 유지.

def build_step1_a2(step_data):
    st_box = _style("STEP1A2", "P")
    st_ox = _style("STEP1A2", "OX")
    # 5지선다 선지 전용 (템플릿 실측: STEP 01 > 하단 문제_선지)
    st_choice = "STEP 01 > 하단 문제_선지"
    units = []
    warnings = []
    cur = []
    seen_bracket = False
    in_choice = False
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
        # 5지선다(①~⑤) 구간 — 일부 회차는 O/X 문항 앞에 5지선다 문제가
        # 하나 더 붙는다. 발문("1. 윗글의 …")과 그 선지를 종전 규칙은
        # "bracket 뒤 영어" 하나로 묶어 **지문 박스**로 인쇄했다
        # (2026-08-06 사용자 지적 + 실측 p21: ①~⑤ 전부 A2_본문 박스).
        # 선지는 전용 스타일(하단 문제_선지), 발문은 기본 단락으로 분리.
        if _RE_A2_CHOICE.match(text.lstrip()):
            in_choice = True
            cur.append(_mk(text, st_choice, runs))
            continue
        if _RE_A2_QUESTION.match(text.lstrip()):
            in_choice = False
            cur.append(_mk(text, "$BASIC", runs))   # 발문은 지문 아님
            continue
        if seen_bracket and re.search(r"[A-Za-z]", text):
            # 선지 구간 안의 이어짐(줄바꿈된 긴 선지)도 선지 스타일 유지
            style = st_choice if in_choice else st_box
            cur.append(_mk(text, style, runs))
        else:
            in_choice = False
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
    # W31: 구조 우선 인식 (legacy is_header_line은 프라이어) + 침묵 금지
    det = _step_header_detection(step_data, "step2_b1",
                                 legacy=is_header_line)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if det.is_header(i):
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
# bracket 기준 유닛 분할.
# EBS 분기 (v1 run.jsx 2125 — 리딩파워는 문제들이 연속해서 흐름): bracket
# 유닛 분할(프레임브레이크) 생략, 대신 bracket 앞 빈 줄 2개만 같은 유닛에
# 유지 (v1 7단계는 유형 공통, 9단계 브레이크만 EBS 생략).

def _c2_is_bracket(text):
    # v1 step9 판정: '['와 ']' 포함 + '\s*[' 시작
    return ("[" in text and "]" in text
            and bool(re.match(r"^\s*\[", text)))


def build_step2_c2(step_data, workbook_type="모의고사"):
    st_num = _style("STEP2C2", "Q")
    st_view = _style("STEP2C2", "Box")
    is_ebs = (workbook_type == "EBS")
    warnings = []

    # 1) 삭제 룰 (v1 1~2단계: (N) 단독줄, 빈 단락, 영어 전용 답 단락)
    kept = []
    # W31: 구조 우선 인식 — 새 형식 헤더도 제거 (유닛은 bracket 기준이라
    # 침묵 게이트는 비적용 strict=False).
    det = _step_header_detection(
        step_data, "step2_c2",
        legacy=lambda t: is_header_line(_norm_header(t)), strict=False)
    for i, p in enumerate(step_data.get("paragraphs", []) or []):
        text = p.get("text") or ""
        if _RE_C2_SOLO_NUM.match(text):
            continue
        if _is_blank(text):
            continue    # v1: \r{2,} → \r
        # 지문 헤더 제거 (W17 c11: "1. L1-본문1" 한글 포함 헤더가 v1의
        # eng_only 삭제 룰을 비껴가 문항번호 스타일로 인쇄됨 — G1 검출.
        # 모의고사형 헤더("1. p16-no.01")는 eng_only가 이미 삭제하던 것과
        # 동일 의미론 — 지문 번호는 독립 프레임(passage_numbers) 담당).
        # bracket 단락([Project 1-1] 등)은 C2의 유닛 분할 마커라 제거
        # 금지 (W31 코퍼스 diff 실증: r3c13ybm 유닛 2→1 회귀 방지).
        # seq(시퀀스 단조성)만으로 잡힌 약한 검출도 제거 금지 — 모의고사
        # C2의 "20번" 문항 라벨은 v1이 인쇄하는 내용이다 (코퍼스 diff
        # 실증: r9c20mock2503/r10c22mock2503g1). C2는 유닛을 bracket이
        # 담당하므로 제거는 강한 검출(legacy/anchor/shape)로만.
        if (det.is_header(i) and not _c2_is_bracket(text)
                and det.via(i) != "seq"):
            continue
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
    #    빈 줄은 프레임브레이크 앞 = 이전 유닛 꼬리에 붙는다).
    #    EBS: 유닛 분할 없이 빈 줄 2개만 (v1 9단계 브레이크 생략 분기).
    units = []
    cur = []
    seen_bracket = False
    for item in out:
        if _c2_is_bracket(item["t"]):
            if seen_bracket and cur:
                cur.append(_mk("", "$BASIC", []))
                cur.append(_mk("", "$BASIC", []))
                if not is_ebs:
                    units.append(cur)
                    cur = []
            seen_bracket = True
        cur.append(item)
    if cur:
        units.append(cur)
    return {"units": units, "warnings": warnings}


# ── W4: STEP1 C1 문장 배열 — v1 processStep1C1 (최난) ───────────────────────
# 원본: engines/workbook/jsx/run.jsx 1136~1648. 패스 순서를 v1 그대로 유지:
# 공백 bracket 제거 → 헤더 정규화 GREP → 레지듀얼 정리 → 프리앰블 제거 →
# 스타일 패스(기본/BTM/C1/BTM갭/BTM_T/원문자/갭 빈줄 제거/교과서 분기) →
# 화살표 아이콘 → 발문 삽입 → { 안전망 → 헤더 잔재 정리 → (하단 제외) →
# 유닛 분할(헤더=NEXT_PAGE|EBS는 NEXT_FRAME, 블록 첫 하단 단락=NEXT_FRAME).

_RE_C1_HEADER = re.compile(r"^\s*\{[^}]+\}")
_RE_C1_CHOICE = re.compile(r"^\s*\([A-Z]\)")
_RE_C1_ABC = re.compile(r"^\s*\(([ABC])\)")
_RE_C1_EMPTY_BRACKET = re.compile(
    "^\\s*\\[[\\s  -​]*\\]\\s*$")
_RE_C1_NUM_BRACKET = re.compile(r"^\s*\[\d+")
# v1 hits7 (원문자 → 하단 지문): ①-⑳ + ⓵-⓿ + ❶-➓
_RE_C1_CIRCLED_WIDE = re.compile("[①-⑳⓵-⓿❶-➓]")
_RE_C1_CIRCLED_PROMPT = re.compile("[①-⑳]")   # 발문 유형 판별용
# v1 has3PlusGaps: 공백류 3연속 이상
_RE_3GAPS = re.compile("[ \\t  -​  　]{3,}")

# v1 헤더 정규화 GREP 체인 (순서 보존 — InDesign GREP과 동일 의미의 파이썬 re)
_C1_GREPS = [
    # 추가지문형: 번호+한글 꼬리 전체를 라벨로 ("no.3과 추가지문" →
    # "{3과 추가지문}", W11). 한글 꼬리 없으면 다음 룰(기존)이 담당.
    (re.compile(r"\bno\.\s*(\d{1,3}(?:~\d{1,3})?[가-힣][가-힣0-9\s]*[가-힣0-9])"),
     r"{\1}"),
    (re.compile(r"\bno\.\s*(\d{1,3}(?:~\d{1,3})?)"), r"{\1}"),
    (re.compile(r"\bExample\s+(\d{1,3})"), r"{\1}"),
    (re.compile(r"\b(\d+)\.\s*p\d+\s*[-–—]?\s*Example\b"),
     r"{\1}"),
    # 부교재 코너명형 (W12): "N. pN-수능 Analysis" → {분석N} (선행 순번 —
    # 같은 원고의 [분석N] 마커 관행과 일치), "N. pN-Practice 0M" → {M}
    # ([M] 마커 관행과 일치, 선행 0 제거). 기존 룰 무변경 삽입 — 아래
    # ANALYSIS(대문자 전용)/서술형 Practice 룰과 매치 집합이 겹치지 않는다.
    (re.compile(r"\b(\d+)\.\s*p\d+\s*[-–—]?\s*수능\s*Analysis\b", re.I),
     r"{분석\1}"),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*Practice\s*0*(\d{1,3})\b"),
     r"{\1}"),
    (re.compile(r"\bANALYSIS\b"), "{분석}"),
    (re.compile(r"\b\d+\.\s*L\d+\s*[-–—.]?\s*p\.?\s*\d+"
                r"[^\r\n]*?본문\s*(\d+)\b"), r"{본문\1}"),
    (re.compile(r"L\d+\s*[-–—.]?\s*p\.?\s*\d+"
                r"[^\r\n]*?본문\s*(\d+)\b"), r"{본문\1}"),
    # (?<!\{): 이미 {본문N}으로 정규화된 라벨 재래핑 방지 — 위 L-p 룰이
    # 만든 "{본문1}"이 "{{본문1}}"로 이중 래핑돼 인쇄되던 것 교정
    # (W30-r15 — 실서비스 376b34d0 실측. v1 JSX도 같은 순서라 동일 증상
    # 이었을 형태지만 이 헤더형("N. L1-p. 13 본문 1")은 v2 첫 실사용 —
    # 완제품 기준 교정. "N. L1-본문1"류 기존 경로는 '-' 선행이라 무영향).
    # W49: `\d+` → 하위분할 순번(본문2-1)까지 라벨에 포함. `\d+`만 잡으면
    # "본문2-1(p.18)" → "{본문2}-1(p.18)"로 (a) 라벨 충돌(2-1·2-2 둘 다 {본문2}),
    # (b) "-1(p.18)" 잔재 인쇄, (c) 마커가 `^{…}$` 아님 → 프레임브레이크 게이트
    # 오검(0e3e6469 step1_c1). 순번은 계층적 → 하위분할 전체를 라벨로.
    (re.compile(r"(?<!\{)(본문)\s*(\d+(?:\s*[-–—.]\s*\d+)*)"), r"{\1\2}"),
    (re.compile(r"\b(\d+)\.\s*L\d+\s*[-–—.]?\s*p\.?\s*\d+\b"),
     r"{본문\1}"),
    # 교과서 L-한글라벨형 (W30-r15 — "6. L1-추가본문" → "{추가본문}"):
    # 페이지/본문번호 없이 한글 라벨이 직결된 헤더. 기존 어느 룰에도 안
    # 걸려 헤더 미정규화 → 추가본문 지문이 본문5 블록에 흡수 + 발문/프레임
    # 분리 누락 (사용자 지목 결함 1). 기존 룰 무변경 삽입 — L-p형은 위
    # 룰들이 먼저 소비하고, 이 룰은 'N. L<n>-<한글>' 전체 라인만 매치.
    (re.compile(r"\b(\d+)\.\s*L\d+\s*[-–—.]\s*([가-힣][가-힣0-9\s]{0,30}?)"
                r"\s*$"), r"{\2}"),
    (re.compile(r"\bL\d+\s*[-–—.]?\s*p\.?\s*\d+\b"), ""),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*서술형\s*Practice\b"),
     "{서술형 Practice}"),
    (re.compile(r"\b\d+\.\s*p\d+\s*[-–—]?\s*논술형\s*"
                r"Prac(?:tice|ice)\b"), "{논술형 Practice}"),
]
# v1 "Clean up residual text before {" (3회 반복)
_C1_RESID = [
    (re.compile(r"((?:^|,)\s*)[^{\r\n]*?(\{[^}]+\})"), r"\1\2"),
    (re.compile(r"-\s*(\{)"), r"\1"),
    (re.compile(r"(^|,)\s+(\{)"), r"\1\2"),
]
# v1 "Clean up header remnants" (최종)
# W49: 라벨의 하위분할 순번(본문2-1) 뒤 "(p.18)" 잔재도 제거 (\d+ → 계층 순번).
_C1_REMNANT = [
    (re.compile(r"(\{본문\d+(?:[-–—.]\d+)*\})\([^)]*\)"), r"\1"),
    (re.compile(r"(\{[A-Za-z][A-Za-z\s]+\})\([^)]*\)"), r"\1"),
]

_RE_TAB = re.compile(r"\t")
_RE_LEAD3WS = re.compile(r"^\s{3,}")

_PROMPT_CIRC = "아래 주어진 문장이 들어갈 위치로 알맞은 곳을 고르시오."
_PROMPT_ORDER = "아래 주어진 문장 다음에 이어질 문장들의 적절한 순서를 쓰시오."
_ICON_ARROW = {"label": "화살표 답지", "pos": "start"}


def _slice_runs(runs, a, b):
    """runs에서 [a,b) 문자 구간만 잘라 반환 (오프셋 정합 유지)."""
    out = []
    off = 0
    for r in runs or []:
        t = r.get("t") or ""
        s, e = off, off + len(t)
        lo, hi = max(a, s), min(b, e)
        if lo < hi:
            out.append(dict(r, t=t[lo - s:hi - s]))
        off = e
    return out


def _sub_runs(rx, repl, text, runs):
    """re.sub 대응 — 텍스트와 runs를 동시에 치환 (밑줄 오프셋 보존).

    치환 삽입분은 비밑줄 run으로 들어간다 (v1 GREP changeTo와 동일:
    새 텍스트는 서식 없는 평문)."""
    matches = list(rx.finditer(text))
    if not matches:
        return text, runs
    out_t = []
    out_r = []
    last = 0
    for m in matches:
        out_t.append(text[last:m.start()])
        out_r.extend(_slice_runs(runs, last, m.start()))
        rep = m.expand(repl)
        if rep:
            out_t.append(rep)
            out_r.append({"t": rep, "ul": False})
        last = m.end()
    out_t.append(text[last:])
    out_r.extend(_slice_runs(runs, last, len(text)))
    return "".join(out_t), out_r


def _c1_true_empty(text):
    """v1 발문 삽입 walk의 isEmpty: \\r\\n 제거 후 빈 문자열 (공백은 비빈)."""
    return re.sub(r"[\r\n]", "", text or "") == ""


def _c1_remove_gap_blank(items, st_btm, st_btm_t):
    """v1: BTM(주어진 문장) → 빈 단락 → BTM_T 사이 빈 줄 1개 제거 (역순)."""
    i = len(items) - 2
    while i >= 1:
        if (items[i - 1]["s"] == st_btm and _is_blank(items[i]["t"])
                and items[i + 1]["s"] == st_btm_t):
            del items[i]
        i -= 1


# W44: step1_c1 헤더 **부분 인식** 보강 스위치 (False = W43 이전 동작).
PROMOTE_C1_MISSED_HDR = True
_RE_C1_ORDINAL = re.compile(r"^\s*(\d{1,3})\s*[.)]")


def _c1_promote_missed_headers(items, orig_texts, warnings):
    """GREP 열거가 놓친 지문 헤더를 {라벨}로 승격 (가산 전용).

    items: build_step1_c1의 작업 리스트 (GREP 정규화 후, in-place 수정)
    orig_texts: GREP 이전 원문 (인덱스 일치)
    """
    n = len(items)
    known = [i for i in range(n) if _RE_C1_HEADER.match(items[i]["t"])]
    if not known:
        return
    try:
        det = detect_headers(list(orig_texts))
    except Exception:                                          # noqa: BLE001
        return
    cand = sorted(i for i in det.header_idx
                  if i < n and not _RE_C1_HEADER.match(items[i]["t"]))
    if not cand:
        return
    # 인식 헤더의 원문 순번 (없으면 승격 판단 불가 → 종료)
    ords = {}
    for i in known:
        m = _RE_C1_ORDINAL.match(orig_texts[i] if i < len(orig_texts) else "")
        if m:
            ords[i] = int(m.group(1))
    if not ords:
        return
    promoted = 0
    for i in cand:
        m = _RE_C1_ORDINAL.match(orig_texts[i])
        if not m:
            continue
        prev = max((k for k in ords if k < i), default=None)
        if prev is None or int(m.group(1)) != ords[prev] + 1:
            continue
        nxt = min((k for k in known if k > i), default=n)
        if not any(_RE_C1_CHOICE.match(items[j]["t"])
                   for j in range(i + 1, nxt)):
            continue
        mb = re.search(r"본문\s*(\d+(?:\s*[-–—.]\s*\d+)*)", orig_texts[i])
        label = ("본문" + re.sub(r"\s+", "", mb.group(1))) if mb else m.group(1)
        new_t = "{" + label + "}"
        items[i]["t"] = new_t
        items[i]["runs"] = [{"t": new_t, "ul": False}]
        ords[i] = int(m.group(1))
        known = sorted(known + [i])
        promoted += 1
    if promoted:
        warnings.append("step1_c1: 구조 인식기로 미인식 헤더 %d개 승격 "
                        "(부분 인식 보강 — W44)" % promoted)


def build_step1_c1(step_data, workbook_type="모의고사", exclude_btm=False,
                   split_condition=True):
    # split_condition: v1 conditionIdxList 잔존 해석의 NEXT_FRAME 유닛 분리.
    # 세로 워크북(workbook_sero_v2)은 페이지당 프레임 2개(상단 보기+하단)라
    # 이 분리가 실물 v1 출력에 없고(사이클 페이지 오버플로우 유발) False로
    # 끈다. 가로(workbook_v2)는 기존 동작 유지(True) — 코퍼스 4케이스 미발동.
    st_c1 = _style("STEP1C1", "P")
    st_btm = _style("STEP1C1", "BTM")
    st_btm_t = _style("STEP1C1", "BTM_T")
    st_hadan = _style("STEP1C1", "Q@bottom")
    is_ebs = (workbook_type == "EBS")
    warnings = []

    # 0) 원본 → 작업 리스트 (s=None은 '어떤 스타일 패스도 안 건드림' 추적 —
    #    v1에서 startParagraph가 스타일 재적용에 안 지워지는 단락 판별용)
    items = [{"t": p.get("text") or "", "runs": p.get("runs") or [],
              "s": None}
             for p in step_data.get("paragraphs", []) or []]

    # 1) 공백만 있는 bracket 단락 제거: [   ] → 삭제
    items = [it for it in items if not _RE_C1_EMPTY_BRACKET.match(it["t"])]
    # GREP 정규화 전 원문 (W44 부분 인식 보강의 순번·구조 판정 기준)
    orig_texts = [it["t"] for it in items]

    # 2) 헤더 정규화 GREP 체인 + 레지듀얼 정리(3회)
    for it in items:
        t, r = it["t"], it["runs"]
        for rx, repl in _C1_GREPS:
            t, r = _sub_runs(rx, repl, t, r)
        for _ in range(3):
            for rx, repl in _C1_RESID:
                t, r = _sub_runs(rx, repl, t, r)
        it["t"], it["runs"] = t, r

    # 3) 프리앰블 제거 — 첫 {N} 헤더 앞 단락 삭제 ((A) 선지가 있으면 보류)
    first_hdr = next((i for i, it in enumerate(items)
                      if _RE_C1_HEADER.match(it["t"])), -1)
    # W31: GREP 열거가 하나도 못 잡으면 구조 우선 인식기로 폴백 — 검출된
    # 헤더를 {라벨}로 정규화해 이후 패스(_RE_C1_HEADER 기준)가 그대로 동작.
    if first_hdr < 0 and USE_STRUCT_HEADER_DETECT:
        det = detect_headers([it["t"] for it in items])
        if det.silent():
            raise HeaderSilenceError("step1_c1", det)
        if det.header_idx:
            ordinal = 0
            for i in sorted(det.header_idx):
                ordinal += 1
                t = items[i]["t"]
                m = re.search(r"본문\s*(\d+)", t)
                if m:
                    label = "본문" + m.group(1)
                else:
                    m = re.match(r"^\s*(\d{1,3})\s*[.)]", t)
                    label = m.group(1) if m else str(ordinal)
                new_t = "{" + label + "}"
                items[i]["t"] = new_t
                items[i]["runs"] = [{"t": new_t, "ul": False}]
            first_hdr = next((i for i, it in enumerate(items)
                              if _RE_C1_HEADER.match(it["t"])), -1)
            warnings.append("step1_c1: 구조 인식기로 헤더 %d개 검출 "
                            "(정규식 열거 미인식 형식)"
                            % len(det.header_idx))
    # W44 (역학습 실증 — 완성본 대조): **부분 인식** 보강. GREP 열거가 일부
    # 헤더만 잡으면(예: "N. L4-본문N(p.94)"는 잡히고 "7. L4-Read More(p.109)"
    # 는 못 잡음) 위 폴백이 발동하지 않아, 못 잡은 블록의 (A)~(J) 배열
    # 항목이 통째로 스타일 없이($BASIC) 인쇄된다 (완성본 ac9fc469
    # 영어Ⅰ_미래엔(김)_4과: 10단락이 실제로는 C1_문장 배열 스타일).
    # 승격 조건(가산만 — 기존 인식분은 절대 건드리지 않음):
    #   (a) 구조 인식기가 헤더로 본 라인이고,
    #   (b) 원문 선두 순번이 직전 인식 헤더의 순번 +1로 이어지고,
    #   (c) 그 블록에 (A)~(Z) 배열 선지가 실제로 뒤따른다.
    # 세 조건이 동시에 성립할 때만 {라벨}로 정규화한다.
    if first_hdr >= 0 and USE_STRUCT_HEADER_DETECT and PROMOTE_C1_MISSED_HDR:
        _c1_promote_missed_headers(items, orig_texts, warnings)
        first_hdr = next((i for i, it in enumerate(items)
                          if _RE_C1_HEADER.match(it["t"])), first_hdr)
    if first_hdr > 0:
        if not any(_RE_C1_CHOICE.match(items[i]["t"])
                   for i in range(first_hdr)):
            items = items[first_hdr:]
    elif first_hdr < 0:
        warnings.append("step1_c1: {N} 지문 헤더 미인식 — 프레임 분리 없이 "
                        "단일 유닛 배치")

    n = len(items)
    hdr_idx = [i for i, it in enumerate(items)
               if _RE_C1_HEADER.match(it["t"])]

    # 3b) 조건(주어진 문장) 후보 — v1 conditionIdxList와 동일 시퀀스.
    #     v1에선 이 startParagraph가 이후 스타일 적용으로 지워져(2026 회귀)
    #     '어떤 스타일도 안 받은 단락'만 실효 → _cond 플래그로 추적.
    hdr_ends = hdr_idx + [n]
    for b in range(len(hdr_ends) - 1):
        saw_choice = False
        for i in range(hdr_ends[b] + 1, hdr_ends[b + 1]):
            t = items[i]["t"]
            trim = re.sub("^[\\s　]+|[\\s　]+$", "", t)
            if not trim:
                continue
            if _RE_C1_CHOICE.match(t):
                saw_choice = True
                continue
            if (saw_choice and re.match(r"^[A-Za-z]", trim)
                    and not re.search("[가-힣]", trim)):
                items[i]["_cond"] = True
                break

    # 4a) {…} 헤더 + [N bracket → [기본 단락]
    for it in items:
        if _RE_C1_NUM_BRACKET.match(it["t"]) or _RE_C1_HEADER.match(it["t"]):
            it["s"] = "$BASIC"

    # 4b) 모든 {header} 다음 첫 비빈 단락 → C1_BTM (EBS 등 본문 별도 줄 원고)
    for h in hdr_idx:
        j = h + 1
        while j < n and _is_blank(items[j]["t"]):
            j += 1
        if j < n:
            items[j]["s"] = st_btm

    # 4c) (A)~(Z) 선지 → C1_문장 배열 (3+공백 단락에서 블록 종료)
    in_block = False
    for i, it in enumerate(items):
        if i > 0 and _RE_C1_HEADER.match(items[i - 1]["t"]):
            in_block = True
        if _RE_3GAPS.search(it["t"]):
            in_block = False
        if in_block and _RE_C1_CHOICE.match(it["t"]):
            it["s"] = st_c1

    # 4d) 3+공백 단락 → C1_BTM, BTM 단락의 탭 + 선행 공백(3+) 제거
    for it in items:
        if _RE_3GAPS.search(it["t"]):
            it["s"] = st_btm
    for it in items:
        if it["s"] == st_btm:
            t, r = _sub_runs(_RE_TAB, "", it["t"], it["runs"])
            t, r = _sub_runs(_RE_LEAD3WS, "", t, r)
            it["t"], it["runs"] = t, r

    # 4e) BTM(3+공백 잔존) 뒤 (A|B|C) 시퀀스 → C1_하단 지문
    for i in range(n):
        if items[i]["s"] != st_btm or not _RE_3GAPS.search(items[i]["t"]):
            continue
        j = i + 1
        while j < n and _is_blank(items[j]["t"]):
            j += 1
        if j >= n or not _RE_C1_ABC.match(items[j]["t"]):
            continue
        k = j
        while k < n:
            t = items[k]["t"]
            if "{" in t or not _RE_C1_ABC.match(t):
                break
            items[k]["s"] = st_btm_t
            k += 1

    # 4f) 원문자 포함 단락 → C1_하단 지문 (v1 grepFind — 스토리 전역)
    for it in items:
        if _RE_C1_CIRCLED_WIDE.search(it["t"]):
            it["s"] = st_btm_t

    # 4g) BTM → 빈 단락 → BTM_T 사이 빈 줄 1개 제거
    _c1_remove_gap_blank(items, st_btm, st_btm_t)
    n = len(items)

    # 4h) 교과서 분기: 《제목》/평문 한 줄 하단 구조 식별
    if workbook_type == "교과서":
        hdr_idx = [i for i, it in enumerate(items)
                   if _RE_C1_HEADER.match(it["t"])]
        hdr_ends = hdr_idx + [n]
        for b in range(len(hdr_ends) - 1):
            b_start, b_end = hdr_ends[b], hdr_ends[b + 1]
            last_choice = -1
            for i in range(b_start + 1, b_end):
                if _RE_C1_CHOICE.match(items[i]["t"]):
                    last_choice = i
            if last_choice < 0:
                continue
            j = last_choice + 1
            while j < b_end and _is_blank(items[j]["t"]):
                j += 1
            if j >= b_end:
                continue
            btm_i = j
            j = btm_i + 1
            while j < b_end and _is_blank(items[j]["t"]):
                j += 1
            if j >= b_end:
                continue
            nxt = items[j]["t"]
            if (not _RE_C1_CHOICE.match(nxt)
                    and not re.search("[①-⑳]", nxt)):
                continue
            if items[btm_i]["s"] == st_btm:
                continue
            items[btm_i]["s"] = st_btm
            k = j
            while k < b_end:
                t = items[k]["t"]
                if _RE_C1_HEADER.match(t):
                    break
                if not _is_blank(t):
                    items[k]["s"] = st_btm_t
                k += 1
        _c1_remove_gap_blank(items, st_btm, st_btm_t)
        n = len(items)

    # 5) 화살표 답지 아이콘 — C1 연속 블록 끝 뒤 (v1 STEP1C1_New 방식)
    out = []
    i = 0
    while i < n:
        it = items[i]
        out.append(it)
        is_run_end = (it["s"] == st_c1
                      and (i + 1 >= n or items[i + 1]["s"] != st_c1))
        if is_run_end:
            if is_ebs and i + 1 < n and _is_blank(items[i + 1]["t"]):
                # EBS: 기존 빈 단락 재사용 (frame break 밀림 방지)
                nxt = items[i + 1]
                nxt["s"] = "$BASIC"
                nxt["icon"] = dict(_ICON_ARROW)
                out.append(nxt)
                i += 2
                continue
            if not is_ebs:
                # 동아박/교과서/모의고사: \r\r — 빈 단락 2개, 두 번째에 화살표
                out.append({"t": "", "runs": [], "s": "$BASIC"})
            arrow = {"t": "", "runs": [], "s": "$BASIC",
                     "icon": dict(_ICON_ARROW)}
            out.append(arrow)
        i += 1
    items = out
    n = len(items)

    # 6) 발문 삽입 — C1_하단 지문 연속 구간 첫 단락 앞 (하단 제외 시 생략)
    if not exclude_btm:
        starts = [i for i in range(n)
                  if items[i]["s"] == st_btm_t
                  and (i == 0 or items[i - 1]["s"] != st_btm_t)]
        for i in reversed(starts):
            bt = items[i]["t"]
            if _RE_C1_CIRCLED_PROMPT.search(bt):
                prompt = _PROMPT_CIRC
            elif _RE_C1_CHOICE.match(bt):
                prompt = _PROMPT_ORDER
            else:
                continue
            ins = i
            while ins > 0:
                above = items[ins - 1]
                # v1 isEmpty: 앵커(￼) 포함 단락은 비빈 — 아이콘 단락에서 멈춤
                if above["s"] == st_btm or (
                        _c1_true_empty(above["t"])
                        and not above.get("icon")):
                    ins -= 1
                    continue
                break
            p = {"t": prompt, "runs": [], "s": st_hadan,
                 "icon": dict(_ICON_STEP1_Q)}
            items.insert(ins, p)
            # W21 r11 D4: 발문과 주어진 문장(BTM) 사이의 원고 잔여 빈 단락
            # 제거 — 걸어 올라오며 건넌 빈 단락이 발문 아래 남아 '하단 문제
            # 발문 ↔ 주어진 문장' 사이 불필요한 빈 줄로 인쇄됐다 (실사용
            # 0e3108fd 실증). v1 실물(워크북03(외부지문) 스토리 26)은 발문
            # 바로 다음이 BTM — 빈 단락 없음. 아이콘 단락은 보존.
            k = ins + 1
            while (k < len(items) and _c1_true_empty(items[k]["t"])
                   and not items[k].get("icon")):
                del items[k]
        n = len(items)

    # 7) 안전망: '{' 포함 단락 → [기본 단락] (v1 Final safety)
    for it in items:
        if "{" in it["t"]:
            it["s"] = "$BASIC"

    # 8) 헤더 잔재물 정리
    for it in items:
        t, r = it["t"], it["runs"]
        for rx, repl in _C1_REMNANT:
            t, r = _sub_runs(rx, repl, t, r)
        it["t"], it["runs"] = t, r

    # 9) 하단만 제외: BTM/BTM_T/발문 단락 삭제 (상단 유지)
    if exclude_btm:
        items = [it for it in items
                 if it["s"] not in (st_btm, st_btm_t, st_hadan)]
        n = len(items)

    # 10) 유닛 분할 — v1 "FRAME BREAK 재적용"의 실효 동작:
    #     헤더(2번째+) = NEXT_PAGE (EBS는 NEXT_FRAME),
    #     블록 내 첫 하단 스타일 단락 = NEXT_FRAME,
    #     스타일 패스가 안 건드린 조건 단락 = NEXT_FRAME (v1 startParagraph 잔존)
    bottom_styles = {st_btm, st_btm_t, st_hadan}
    units = []
    cur = []
    cur_page_break = False

    def _flush():
        if cur:
            unit = {"paras": list(cur)}
            if cur_page_break:
                unit["page_break"] = True
            units.append(unit)

    seen_header = False
    block_bottom_done = True
    for it in items:
        is_hdr = bool(_RE_C1_HEADER.match(it["t"]))
        if is_hdr:
            _flush()
            cur = []
            cur_page_break = seen_header and not is_ebs
            seen_header = True
            block_bottom_done = False
        elif (not block_bottom_done and it["s"] in bottom_styles):
            _flush()
            cur = []
            cur_page_break = False
            block_bottom_done = True
        elif split_condition and it.get("_cond") and it["s"] is None:
            _flush()
            cur = []
            cur_page_break = False
        para = _mk(it["t"], it["s"] if it["s"] is not None else "$BASIC",
                   it["runs"])
        if it.get("icon"):
            para["icon"] = it["icon"]
        cur.append(para)
    _flush()
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
    "step1_c1": build_step1_c1,
}

# 원고 유형(EBS/교과서/모의고사) 분기가 필요한 빌더 — v1은 settings의
# workbook_type으로 분기 (workbook 엔진은 미전달 = "" → 非EBS 처리).
_CTX_BUILDERS = {"step1_c1", "step2_c2"}


# ── 지문번호 라벨 추출 (W11 — 독립 번호 프레임 갱신 op + 검수 게이트용) ──────
# 헤더 "1. p1-no.3과 추가지문" → "3과 추가지문", "1. p2-no.20" → "20".
# 페이지 번호 뒤 (?!\d): 코너명형 헤더 "1. p80-수능 Analysis"에서 p80이
# p8+라벨"0"으로 쪼개져 엉뚱한 라벨이 나오던 백트래킹 차단 (W12 실증 —
# 지문번호 프레임이 0/6/8로 갱신됨). 코너명형은 라벨 없음 → 다음 스텝/
# bracket 폴백([분석N]/[N])이 담당.
_RE_LABEL_HEADER = re.compile(
    r"^\s*\d+\s*[.)]\s*p\.?\s*\d+(?!\d)\s*[-–—.]?\s*(?:no\.\s*)?"
    r"(\d+(?:\s*~\s*\d+)?(?:\s*[가-힣][가-힣0-9\s]*[가-힣0-9])?)",
    re.I)
# 외부지문 무-p형 헤더 "1. no.1" → no-번호 (W21 r11 — p-형과 동일 규칙)
_RE_LABEL_HEADER_NOP = re.compile(
    r"^\s*\d+\s*[.)]\s*no\.\s*(\d+(?:\s*~\s*\d+)?)\s*$", re.I)
# bracket 지문번호 "[3과 추가지문]" / "[20]" → 내용부
_RE_LABEL_BRACKET = re.compile(r"^\s*\[([^\]]+)\]\s*$")

# 라벨 소스 우선순위: 헤더 기반 스텝(독립 번호 프레임 섹션과 동일 원고 계열)
_LABEL_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_a1")


def passage_labels(steps):
    """원고 지문번호 라벨을 순서대로 추출 (중복 제거, 첫 유효 스텝 채택).

    독립 텍스트 프레임 지문번호 갱신 op(passage_numbers)와 검수 게이트의
    '원고 지문번호' 기준. 헤더 스텝이 없으면 step1_a1의 bracket 단락 폴백.
    """
    for key in _LABEL_STEPS:
        data = steps.get(key) or {}
        labels = []
        for p in data.get("paragraphs", []) or []:
            text = _norm_header(p.get("text") or "")
            m = _RE_LABEL_HEADER.match(text)
            if not m:
                m = _RE_LABEL_HEADER_NOP.match(text)
            if not m and key == "step1_a1":
                m = _RE_LABEL_BRACKET.match(text)
            if m:
                label = re.sub(r"\s+", " ", m.group(1)).strip()
                if label and label not in labels:
                    labels.append(label)
        if labels:
            return labels
    return []


def ensure_step3_kinds(step3_data, log=None):
    """구버전 content.json(step3 단락에 kind 미주석) 재사용 대비 —
    kind가 하나도 없으면 v1 파서의 주석기를 그대로 호출해 in-place 보강.

    현행 파서(engines/workbook/parser)는 항상 kind를 심으므로 실서비스
    경로에선 no-op. 과거 job content.json 재실행(코퍼스/E2E)용 fail-open."""
    if not step3_data:
        return
    items = ((step3_data.get("normal") or [])
             + (step3_data.get("short") or []))
    if not items:
        return
    has_kind = any(p.get("kind")
                   for it in items for p in it.get("paragraphs") or [])
    if has_kind:
        return
    try:
        from engines.workbook.parser import _annotate_step3_kinds
        _annotate_step3_kinds(items, log)
        if callable(log):
            log("[v2] step3 kind 주석 보강 (구버전 content.json — "
                "kind 미포함)")
    except Exception as e:                                  # noqa: BLE001
        if callable(log):
            log(f"[v2] ⚠️ step3 kind 주석 보강 실패 — 기본 스타일 배치: {e}")


def steps_to_plan(steps, exclude=None, workbook_type="모의고사",
                  step_map=None):
    """v1 content steps → {"format": "wb-flows-v1", "flows": [...],
    "unsupported": [스텝키]} — 미지원 스텝은 커버리지 리포트용으로 기록.

    exclude: 스텝 키(전체 제외) + "step1_c1_btm"(C1 하단만 제외) 지원.
    workbook_type: "모의고사"|"교과서"|"EBS" — C1/C2 프레임 분리·아이콘 분기.
    step_map: 스텝→스토리 매핑 override (None = 모의고사 기본 STEP_MAP).
        지정 시 매핑에 없는 스텝은 배치 불가 → unsupported로 보고
        (EBS/수능특강 내지는 스텝 페이지 구성이 다르다).
    """
    exclude = set(exclude or [])
    smap = STEP_MAP if step_map is None else step_map
    flows = []
    unsupported = []
    warnings = []
    for step_key, step_data in steps.items():
        if step_key in exclude:
            continue
        builder = STEP_BUILDERS.get(step_key)
        if builder is None or (step_map is not None
                               and step_key not in smap):
            unsupported.append(step_key)
            continue
        # W20 D1 — hwp 심볼 PUA 인쇄 매핑 (사본 — content 원본 무변형)
        step_data = apply_pua_print_map(step_data)
        # W23 F3 — 아래첨자(₂류) 인쇄 매핑: ASCII 숫자 + sub 서식 run
        step_data = apply_subscript_print_map(step_data)
        if step_key == "step1_c1":
            built = builder(step_data, workbook_type=workbook_type,
                            exclude_btm=("step1_c1_btm" in exclude))
        elif step_key in _CTX_BUILDERS:
            built = builder(step_data, workbook_type=workbook_type)
        else:
            built = builder(step_data)
        # W30 후속 — 빌더가 소비하고 남은 ❮❯ 잔존을 등가 글리프로 치환
        # (빌더 이후 적용 — 1A1 []·1A2 TF 토큰 로직 보존)
        apply_glyph_print_map_units(built["units"])
        warnings.extend(built.get("warnings") or [])
        target = dict(smap.get(step_key, {}))
        flow = {"step": step_key, "target": target,
                "break_per_unit": True, "units": built["units"]}
        if built.get("ul_style"):
            flow["ul_style"] = built["ul_style"]
        flows.append(flow)
    return {"format": "wb-flows-v1", "flows": flows,
            "unsupported": sorted(unsupported),
            "warnings": warnings}


def question_keep_op(plan, steps=("step3",)):
    """W23 r13 (F4) — 문제 단위 펼침면 킵 op 계산 (실행기/게이트 공용 계약).

    사용자 확정 스펙: 한 문제(발문+지문+선지 전체)가 왼쪽→오른쪽 페이지로
    이어지는 것은 허용, 오른쪽 페이지에서 잘려 다음 장(스프레드 넘김)으로
    이어지는 것은 금지 — 그 경우 문제 전체를 다음 페이지로 민다.

    starts = 문제 시작 단락의 '평탄화(flat) 인덱스' (실행기 processFlow가
    유닛을 순서대로 평탄화해 스토리에 얹으므로 스토리 단락 인덱스와 1:1).
    문제 시작 = STEP3 발문(Q)/그룹 인트로(Q-INTRO) 스타일 단락. 인덱스 0은
    제외 — 플로우 첫 단락을 밀면 섹션 시작 자체가 마커 페이지를 벗어난다.
    q_styles는 게이트 G30이 출력 재검산에 소비한다. 대상 스텝에 시작점이
    없으면 None (op 미적용)."""
    q_styles = set()
    for kind in ("Q", "Q-INTRO"):
        st = _style("STEP3", kind)
        if st:
            q_styles.add(st)
    flows_cfg = {}
    for fl in plan.get("flows", []):
        if fl.get("step") not in steps:
            continue
        starts = []
        idx = 0
        for u in fl.get("units", []):
            for p in unit_paras(u):
                if p.get("s") in q_styles and idx > 0:
                    starts.append(idx)
                idx += 1
        if starts:
            flows_cfg[fl["step"]] = {"starts": starts}
    if not flows_cfg:
        return None
    # W40 결함 2 — 발문 고아 방지 (프레임판 question_keep): 프레임 하단에
    # 발문만 남거나 발문+본문 1줄만 남으면 문제 시작을 다음 프레임으로
    # 민다 (실행기 enforceStemKeep 계약 — min_lines = 발문 뒤 최소 동반
    # 본문 줄수. 게이트 G41이 stem_keep 유무로 critical/warning 분기).
    return {"flows": flows_cfg, "q_styles": sorted(q_styles),
            "stem_keep": {"min_lines": 2}}


def choice_tabs_op(plan, steps=("step3",)):
    """W40 결함 1 — 다열 선지 열 정렬 op 계산 (실행기 applyChoiceTabs 계약).

    실행기는 있었는데 플랜 쪽 계약 생성부가 없어 계약 미발행 상태였고,
    그래서 명시 탭스톱 없이 InDesign 기본 12.7mm 탭 그리드로 떨어져 열이
    행마다 한 스톱씩 어긋났다 (게이트 G42가 편차 12.7mm로 지목 — v13
    33그룹). 대상 스텝에 탭 선지 단락이 없으면 None (op 미적용).

    grid/min_gap 은 v1 손마무리 실물 관행값 (배재2_워크북01 실측)."""
    hits = 0
    target = []
    for fl in plan.get("flows", []):
        step = fl.get("step")
        if step not in steps:
            continue
        n = 0
        for u in fl.get("units", []):
            for p in unit_paras(u):
                if "선지" in (p.get("s") or "") and "\t" in (p.get("t") or ""):
                    n += 1
        if n:
            target.append(step)
            hits += n
    if not target:
        return None
    return {"steps": target, "grid": 12.7, "min_gap": 2,
            "style_contains": "선지", "_rows": hits}
