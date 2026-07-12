"""워크북 v2 완제품 검수 게이트 (W11 — job 06f4b2c2 결함 6건의 자동 검출).

기준은 '조판사가 납품하는 완제품'이다 — 파싱 결과가 아니라 출력물 자체를
검사한다 (파서가 틀리면 게이트도 같이 틀리는 순환 금지):
  G1 [헤더잔존]   지문번호 헤더 원문이 출력 본문에 인쇄됨 (critical)
  G2 [정답잔존]   '정답' 블록/정답표 행이 출력에 인쇄됨 (critical)
  G3 [지문번호]   독립 지문번호 프레임이 원고 지문번호와 불일치
                  (passage_numbers op 사용 시 critical, 아니면 warning)
  G4 [잔여페이지] 원고에 없는 스텝/남는 사이클 페이지 잔존
                  (page_cleanup op 사용 시 critical, 아니면 warning)
  G5 [상하반전]   step2_a1(상단)과 step2_a1_btm(하단)의 기하 배치 반전
                  (step_map pos 힌트 사용 시 critical, 아니면 warning)
  G6 [헤더미인식] 원고(콘텐츠 단락)에 구조적 헤더 후보가 있는데 인식기가
                  하나도 못 잡음 — 파싱 계층 경고 (순환 측정 방지)
  G7 [빈플랜]     렌더 유닛이 0 — 업로드 원고가 어느 스텝에도 매핑되지
                  않았는데 조판이 '성공'으로 끝나는 침묵 유실 (critical, W12)
  G8 [구분선잔존] 원전 교재의 챕터/유닛 구분선("Chapter 03. ..." /
                  "Unit 10 긴 어구 빈칸")이 출력 본문에 인쇄됨 (critical, W12)
  G9 [미사용원고] 업로드/원고 폴더의 원고 파일이 어느 스텝에도 소비되지
                  않고 조용히 무시됨 (W13 c15 실증: "…STEP 2_박소원
                  완료.hwpx" 통합 원고 3종 침묵 무시). 정답/답지/해설
                  파일과 '정답지 짝' 파일은 의도된 미사용이라 stats로만
                  보고, 그 외는 warning (G7 전량 유실의 부분 유실 보완).
  G10 [특수문자]  hwp 사용자 영역(PUA) 문자가 출력에 인쇄됨 — InDesign
                  폰트에 글리프가 없어 tofu(빈 네모)로 찍힌다 (W14 c05/c06
                  실증: 요약 화살표 ⇩가 /\U000f0036으로 인코딩).
                  PUA 단독 단락은 critical, 본문 내 혼입은 warning.
  G11 [마커오염/마커스타일] 변형문제 출처 마커("[NHN_..._변형]")에 원문자
                  접두가 붙어 인쇄(파서 선지 오염) 또는 같은 마커가 복수
                  스타일로 인쇄(kind 오분류 — 발문/선지 스타일로 찍힘).
                  둘 다 critical (W15 c04 실증: 183개 중 9개 비일관 + 오염 1).
  G12 [문장삽입배경] 출처 마커가 있는 스토리에서 문장삽입 발문 뒤 배경
                  (주어진 문장 박스) 미부여 — warning (W15 c04 실증 12건).
  G13 [발문스타일] 발문 시그니처 단락([서술형 N] 접두 태그, 또는 발문
                  시작 신호 + 시오/세요-체 종결)이 발문 계열 스타일이
                  아닌 스타일로 인쇄됨 — critical (W16 c07 실증:
                  "[서술형 2] … 쓰세요." 해요체 발문이 지문 스타일).
  G14 [영단어오분류] 영단어 스타일 단락이 실제 어휘 항목("word: 한글 뜻")
                  이 아님 — 한글 뜻이 없거나 콜론 앞 머리가 1글자(대화문
                  화자 라벨 "A:"/"Minji:") — critical (W16 c10 실증 6건 +
                  c04/80dd3fa2 잠복. v1 실물: 이런 행은 전부 지문 스타일).
  G15 [조건항목]  <조건> 블록 안의 강신호 조건 항목(불릿 시작 또는
                  한글 + '것' 종결, 답란 이전)이 조건 스타일이 아닌
                  스타일로 인쇄됨 — critical (W16 c10 실증 3블록 +
                  c04/c05/0a5da924 잠복).

G4/G5는 dump_stories.jsx의 W11 확장 필드(stale_pages / pg / b)가 필요하다.
구버전 덤프에는 경고로만 보고한다 (재덤프 안내). G9는 uploads_dir를 넘긴
경우에만 검사한다 (오프라인 플랜 테스트 호환).
"""
import os
import re
import unicodedata

from core.inspect import find_leaked_answers
from engines.workbook_v2.plan import (is_header_line, is_a1_header,
                                      passage_labels, _norm_header)

_RE_BARE_NUM = re.compile(r"^\d{1,3}(?:\s*~\s*\d{1,3})?$")
_RE_DIGIT = re.compile(r"\d")
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")

# G11 — 변형문제 출처 마커 (출력 검사용 독립 정의 — 파서/플랜과 순환 방지)
_RE_SRC_MARKER = re.compile(r"^\[[^\[\]]{2,}변형\]$")
_RE_SRC_POLLUTED = re.compile(r"^[①-⑤]\[[^\[\]]{2,}변형\]$")
# G12 — 문장삽입 발문 (주어진 문장 배경 박스 기대)
_RE_INSERT_PROMPT = re.compile(r"주어진 문장이 들어가|들어갈 위치|"
                               r"들어가기에 가장 적절한 곳")

# G13 — 발문 시그니처 (출력 검사용 독립 정의 — 플랜 오버레이와 순환 방지)
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_Q_LEAD_TAG = re.compile(r"^\[(?:서술|논술)형\s*\d*\]")
_RE_Q_TRAIL_SRC = re.compile(r"\s*\[[^\[\]]{1,40}\]\s*$")
_RE_Q_START = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의\s*흐름|주어진)")
_RE_Q_END = re.compile(r"(?:시오|세요)\s*[.?!]?\s*$")
# 발문 계열 스타일 시그니처 — "실전 문제 지문"(지문 스타일)과 충돌하지
# 않도록 "하단 문제"/"OX문제"처럼 구체 명칭으로 한정
_Q_STYLE_KEYS = ("번호", "발문", "다음 글을 읽고", "하단 문제", "OX문제")

# G14 — 영단어 스타일 오용 (실제 어휘 항목은 "word: 한글 뜻" — 한글 필수,
# 콜론 앞 머리 2+글자. 1글자 머리는 대화문 화자 라벨 "A:")
_RE_WORD_BAD_HEAD = re.compile(r"^[A-Za-z]\s*[:：]")

# G15 — <조건> 블록 항목 (강신호 한정 — v1 실물 관행: 영어 어구 나열은
# 지문 유지, 시오-체 번호 항목은 발문 유지. 4ed24266/c15 v1 덤프 실증)
_RE_COND_BULLET = re.compile(r"^\s*[•⦁◦∙ㆍ·]")
_RE_COND_GEOT = re.compile(r"것\s*\.?\s*$")
_RE_COND_NUMSTART = re.compile(r"^\s*\d+\s*[.)]")
_RE_COND_BLOCK_END = re.compile(r"_{3,}|^\s*(?:정답|→|우리말)")
_RE_COND_QHINT = re.compile(r"^(?:다음|윗\s*글|위\s*글|글의|밑줄|주어진|"
                            r"\(주관식\)|서술형)")

# G8 — 원전 교재 구분선 (파서 _RE_CHAPTER_DIVIDER/_RE_UNIT_DIVIDER 준용.
# 출력 검사용 독립 정의 — 파서가 틀리면 게이트도 같이 틀리는 순환 방지)
_DIVIDER_PATTERNS = [
    re.compile(r"^Chapter\s+\d+\.\s", re.I),
    re.compile(r"^Unit\s+\d+\s+[가-힣][가-힣0-9\s]{0,30}$"),
]


# G10 — hwp 사용자 영역(PUA) 문자 (BMP U+E000~F8FF + plane 15/16).
# InDesign 본문 폰트에 글리프가 없어 tofu로 인쇄된다. ￼(U+FFFC 앵커)는
# PUA가 아니므로 무관.
def _is_pua(ch):
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


def _clean(t):
    """덤프 단락 텍스트 정규화 — 앵커(￼)/개행 제거 + 공백 정리."""
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("￼", "")
    return _norm_header(t)


def _dump_paras(dump):
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            yield p.get("t", ""), p.get("s", "")


def _flow_probe_text(flow):
    """플로우에서 가장 긴 단락 텍스트 — 덤프 스토리 식별용 (충분히 고유)."""
    best = ""
    for u in flow.get("units", []):
        paras = u["paras"] if isinstance(u, dict) else u
        for p in paras:
            if len(p.get("t") or "") > len(best):
                best = p["t"]
    return best


def _find_story_with_text(dump, text):
    key = _clean(text)
    if not key:
        return None
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            if _clean(p.get("t", "")) == key:
                return story
    return None


def _is_struct_header_candidate(paras, i):
    """구조적 헤더 후보 — 형식 무관 판정 (parser._is_passage_marker_struct
    준용). 짧고 숫자 포함, 영단어 적고, 뒤에 긴 영어 본문이 따라옴."""
    text = (paras[i].get("text") or "").strip()
    if not text or len(text) > 40:
        return False
    if not _RE_DIGIT.search(text):
        return False
    if len(_RE_ENG_WORD.findall(text)) >= 4:
        return False
    j = i + 1
    while j < len(paras) and not (paras[j].get("text") or "").strip():
        j += 1
    if j >= len(paras):
        return False
    return len(_RE_ENG_WORD.findall(paras[j].get("text") or "")) >= 5


# 헤더 기반 스텝 (헤더 제거/정규화가 빌더 책임인 스텝)
_HEADER_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_c1")

# ── G9: 미사용 업로드 원고 (W13) ─────────────────────────────────────────────
_MS_EXTS = (".docx", ".hwp", ".hwpx")
_RE_ANSWERISH = re.compile(r"정답|답지|답안|해설|answer", re.I)
_RE_S3_NUMFILE = re.compile(r"\d+(?:\s*~\s*\d+)?\s*번\s*\.(?:hwpx?|docx)",
                            re.I)
_RE_VARIANT = re.compile(r"변형\s*문제")


def _norm_fname(name):
    return unicodedata.normalize(
        "NFC", os.path.splitext(name)[0]).replace(" ", "").lower()


def find_unused_uploads(content, uploads_dir):
    """(expected_unused, suspicious) — 스텝에 소비되지 않은 원고 파일 분류.

    used 판정은 파서 소비 규칙의 근사 재현:
      - 루트: content steps의 filename (파서가 매칭·rename한 실명)
      - Step3 하위폴더: "N번" 파일(모의고사 번호 매칭), 변형문제 문제모음,
        교과서 경로(step3가 textbook 항목이면 비정답 후보 전부 소비)
    expected_unused = 정답/답지/해설 토큰 파일 + '정답지 짝' 파일(빈칸어휘
    스텝처럼 정답지 본이 소비되는 경우의 문제지 본) — 관행상 폴더에 늘
    존재하므로 stats로만 보고한다.
    """
    steps = (content.get("steps") or {}) if content else {}
    used = set()
    for sd in steps.values():
        if isinstance(sd, dict) and sd.get("filename"):
            used.add(_norm_fname(sd["filename"]))
    st3 = steps.get("step3") or {}
    st3_items = ((st3.get("normal") or []) + (st3.get("short") or [])
                 if isinstance(st3, dict) else [])
    st3_textbook = any(it.get("question_num") == "textbook"
                       for it in st3_items)
    st3_numbered = any(it.get("question_num") != "textbook"
                       for it in st3_items)

    expected, suspicious = [], []
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        in_step3 = "step3" in unicodedata.normalize(
            "NFC", os.path.relpath(root, uploads_dir)).lower()
        for f in sorted(files):
            if f.startswith(".") or os.path.splitext(f)[1].lower() \
                    not in _MS_EXTS:
                continue
            nf = unicodedata.normalize("NFC", f)
            key = _norm_fname(nf)
            if key in used:
                continue
            if in_step3:
                if st3_numbered and _RE_S3_NUMFILE.search(nf):
                    continue      # 모의고사 번호 매칭으로 소비
                if _RE_VARIANT.search(nf) and st3_items:
                    continue      # 변형문제 문제모음 (W12 라우팅)
                if (st3_textbook and not _RE_ANSWERISH.search(nf)):
                    continue      # 교과서 경로: 비정답 후보 전부 소비
            if _RE_ANSWERISH.search(nf) or any(u.startswith(key)
                                               for u in used):
                # 정답/답지류, 또는 소비된 변형본의 짝 파일 (예: 사용
                # "…빈칸어휘 정답지.docx"/"…영작배열(서술형).hwpx"의 짝
                # "…빈칸어휘.docx"/"…영작배열.docx") — 관행상 의도된 미사용
                expected.append(nf)
            else:
                suspicious.append(nf)
    return expected, suspicious


def inspect_workbook_finish(content, plan, dump, uploads_dir=None):
    """content(원고 파싱본) + plan + 출력 덤프 → 완제품 게이트 리포트."""
    critical = []
    warnings = []
    stats = {}
    plan = plan or {}
    steps = (content.get("steps") or {}) if content else {}

    strict_numbers = bool(plan.get("passage_numbers"))
    strict_pages = bool(plan.get("page_cleanup"))
    pos_used = any((fl.get("target") or {}).get("pos")
                   for fl in plan.get("flows", []))

    # ── G7 빈 플랜 — 업로드 원고가 렌더 유닛으로 전혀 이어지지 않음 ─────
    # (W12 실증: 변형문제 문제모음 hwp가 스텝 분류에 안 잡혀 조용히
    # 유실됐는데 verify ok=True로 끝나던 침묵 유실 차단)
    total_units = sum(len(fl.get("units") or [])
                     for fl in plan.get("flows", []))
    stats["plan_units"] = total_units
    if total_units == 0:
        critical.append("[빈플랜] 렌더 유닛 0 — 업로드 원고가 어느 스텝에도 "
                        "매핑되지 않음 (파일명/폴더 규칙 확인)")

    # ── G1 헤더 원문 잔존 + G8 구분선 잔존 ──────────────────────────────
    leaks = []
    divider_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if any(p.match(tt) for p in _DIVIDER_PATTERNS):
            divider_leaks.append(tt[:60])
            continue
        if not _RE_DIGIT.search(tt):
            continue
        if tt.startswith("{") or tt.startswith("["):
            continue    # {20}/{3과 추가지문}/[20] — 의도된 라벨 산출물
        if is_header_line(tt) or is_a1_header(tt):
            leaks.append(tt[:60])
    stats["header_leaks"] = len(leaks)
    if leaks:
        critical.append(f"[헤더잔존] {len(leaks)}개 단락이 지문번호 헤더 "
                        f"원문 그대로 인쇄됨: "
                        + " | ".join(sorted(set(leaks))[:5]))
    stats["divider_leaks"] = len(divider_leaks)
    if divider_leaks:
        critical.append(f"[구분선잔존] {len(divider_leaks)}개 단락이 원전 "
                        f"챕터/유닛 구분선 그대로 인쇄됨: "
                        + " | ".join(sorted(set(divider_leaks))[:5]))

    # ── G2 정답 블록 잔존 ────────────────────────────────────────────────
    ans = find_leaked_answers(dump)
    stats["answer_leaks"] = len(ans)
    if ans:
        critical.append(f"[정답잔존] {len(ans)}개 단락: "
                        + " | ".join(ans[:5]))

    # ── G10 hwp 사용자 영역(PUA) 문자 잔존 (W14) ─────────────────────────
    pua_solo = []
    pua_inline = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not any(_is_pua(ch) for ch in tt):
            continue
        codes = sorted({f"U+{ord(ch):04X}" for ch in tt if _is_pua(ch)})
        if all(_is_pua(ch) or ch.isspace() for ch in tt):
            pua_solo.append(codes[0])
        else:
            pua_inline.append(f"{codes[0]} ({tt[:30]})")
    stats["pua_solo"] = len(pua_solo)
    stats["pua_inline"] = len(pua_inline)
    if pua_solo:
        critical.append(
            f"[특수문자] hwp 사용자 영역(PUA) 단독 단락 {len(pua_solo)}개 — "
            f"폰트 글리프 없음(tofu 인쇄): "
            + ", ".join(sorted(set(pua_solo))[:5]))
    if pua_inline:
        warnings.append(
            f"[특수문자] 본문 내 PUA 문자 혼입 {len(pua_inline)}개 단락: "
            + " | ".join(pua_inline[:3]))

    # ── G11 변형문제 출처 마커 인쇄 상태 (W15 c04) ───────────────────────
    # "[202506H2_18목적추론_변형]" 단독 단락은 관행상 지문 스타일로 일관
    # 인쇄된다 (v1 실물 고2 25-6 워크북 대조). ① 마커에 원문자 접두가 붙어
    # 인쇄 = 파서 선지 오염(원고에 없는 선지 번호), ② 같은 마커 셰이프가
    # 복수 스타일로 인쇄 = kind 오분류(발문/선지 스타일로 크게 찍힘) —
    # 둘 다 critical.
    src_styles = {}
    src_polluted = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if _RE_SRC_POLLUTED.match(tt):
            src_polluted.append(tt[:40])
            continue
        if _RE_SRC_MARKER.match(tt):
            src_styles.setdefault(s, []).append(tt)
    stats["src_markers"] = sum(len(v) for v in src_styles.values())
    stats["src_marker_styles"] = len(src_styles)
    stats["src_polluted"] = len(src_polluted)
    if src_polluted:
        critical.append(
            f"[마커오염] 출처 마커에 원고에 없는 원문자 접두 "
            f"{len(src_polluted)}개: " + " | ".join(src_polluted[:3]))
    if len(src_styles) > 1:
        major = max(src_styles, key=lambda k: len(src_styles[k]))
        minority = {k: v for k, v in src_styles.items() if k != major}
        critical.append(
            "[마커스타일] 출처 마커가 복수 스타일로 인쇄됨 (기준 "
            f"「{major}」 {len(src_styles[major])}개 외): "
            + " | ".join(f"「{k}」 {len(v)}개 (예: {v[0][:30]})"
                         for k, v in sorted(minority.items())[:3]))

    # ── G12 문장삽입 '주어진 문장' 배경 (W15 c04 — warning) ──────────────
    # 변형 문제모음(출처 마커가 있는 스토리)에서 문장삽입 발문 뒤 3단락 내에
    # 배경 스타일 단락이 없으면 지목 — 주어진 문장 박스 누락 (v2는 분류
    # 계층 P-CONTEXT로 부여, v1 실물은 마커에 배경을 줬음 — 어느 쪽이든
    # '배경 없음'은 결함).
    insert_missing = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if not any(_RE_SRC_MARKER.match(_clean(p.get("t", ""))) for p in ps):
            continue
        for i, p in enumerate(ps):
            if not _RE_INSERT_PROMPT.search(_clean(p.get("t", ""))):
                continue
            window = [q for q in ps[i + 1:i + 5]
                      if _clean(q.get("t", ""))][:3]
            if not any("배경" in (q.get("s") or "") for q in window):
                insert_missing.append(_clean(p.get("t", ""))[:40])
    stats["insert_bg_missing"] = len(insert_missing)
    if insert_missing:
        warnings.append(
            f"[문장삽입배경] 문장삽입 발문 뒤 배경(주어진 문장 박스) 미부여 "
            f"{len(insert_missing)}건: " + " | ".join(insert_missing[:3]))

    # ── G13 발문 스타일 누락 (W16 c07) ───────────────────────────────────
    # [서술형 N] 접두 태그, 또는 발문 시작 신호("다음/윗글/주어진…") +
    # 시오/세요-체 종결(꼬리 [출처] 태그 제거 후)이 발문 계열 스타일이
    # 아니면 검출 — 해요체("쓰세요") 발문이 지문 스타일로 인쇄되는 결함.
    q_style_miss = []
    for t, s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not _RE_HANGUL.search(tt):
            continue
        core = tt
        while True:
            nx = _RE_Q_TRAIL_SRC.sub("", core)
            if nx == core:
                break
            core = nx
        body = _RE_Q_LEAD_TAG.sub("", core).strip()
        is_q_sig = bool(_RE_Q_LEAD_TAG.match(core)) or (
            _RE_Q_START.match(body) and _RE_Q_END.search(body))
        if is_q_sig and body and not any(k in (s or "")
                                         for k in _Q_STYLE_KEYS):
            q_style_miss.append(tt[:45])
    stats["q_style_miss"] = len(q_style_miss)
    if q_style_miss:
        critical.append(
            f"[발문스타일] 발문 시그니처 단락 {len(q_style_miss)}개가 발문 "
            f"계열 스타일이 아님: " + " | ".join(q_style_miss[:3]))

    # ── G14 영단어 스타일 오분류 (W16 c10) ───────────────────────────────
    word_bad = []
    for t, s in _dump_paras(dump):
        if "영단어" not in (s or ""):
            continue
        tt = _clean(t)
        if not tt:
            continue
        if not _RE_HANGUL.search(tt) or _RE_WORD_BAD_HEAD.match(tt):
            word_bad.append(tt[:45])
    stats["word_style_bad"] = len(word_bad)
    if word_bad:
        critical.append(
            f"[영단어오분류] 어휘 항목이 아닌 단락 {len(word_bad)}개가 "
            f"영단어 스타일로 인쇄됨: " + " | ".join(word_bad[:3]))

    # ── G15 <조건> 블록 항목 스타일 (W16 c10) ────────────────────────────
    # <조건> 마커부터 답란(밑줄런/정답/→/우리말) 이전까지 스캔. 강신호
    # 조건 항목(불릿 시작 / 한글 + '것' 종결 / 번호 + 한글 + '것' 종결)이
    # 조건 스타일이 아니면 검출. 발문 스타일 + 발문 신호(시작 힌트/시오)는
    # 블록 종료로 간주 (v1 실물: 시오-체 번호 항목은 발문 유지 관행).
    cond_miss = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        for i, p in enumerate(ps):
            if _clean(p.get("t", "")) != "<조건>":
                continue
            for j in range(i + 1, len(ps)):
                qt = _clean(ps[j].get("t", ""))
                qs = ps[j].get("s") or ""
                if not qt:
                    continue
                if _RE_COND_BLOCK_END.search(qt):
                    break
                if qt.startswith("<보기>") or qt == "보기":
                    break
                if any(k in qs for k in ("다음 글을 읽고", "보기", "배경")):
                    break
                if "번호" in qs and (_RE_COND_QHINT.match(qt)
                                     or "시오" in qt):
                    break
                strong = (_RE_COND_BULLET.match(qt)
                          or (_RE_COND_GEOT.search(qt)
                              and _RE_HANGUL.search(qt)))
                if strong and "조건" not in qs:
                    cond_miss.append(qt[:45])
                elif not (_RE_HANGUL.search(qt)
                          or _RE_COND_BULLET.match(qt)):
                    continue    # 영어 어구 나열 — 지문 유지 관행 (skip)
                elif "조건" not in qs and not strong:
                    break       # 한글 비조건 문장 — 블록 종료로 간주
    stats["cond_item_miss"] = len(cond_miss)
    if cond_miss:
        critical.append(
            f"[조건항목] <조건> 블록 항목 {len(cond_miss)}개가 조건 스타일이 "
            f"아님: " + " | ".join(cond_miss[:3]))

    # ── G3 독립 지문번호 프레임 ↔ 원고 지문번호 ─────────────────────────
    labels = list((plan.get("passage_numbers") or {}).get("labels") or [])
    if not labels:
        labels = passage_labels(steps)
    expected = set(labels)
    for sd in steps.values():
        if isinstance(sd, dict):
            for n in sd.get("question_numbers") or []:
                expected.add(str(n))
    bare_frames = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if len(ps) != 1:
            continue
        tt = _clean(ps[0].get("t", ""))
        if _RE_BARE_NUM.match(tt):
            bare_frames.append(tt)
    unknown = sorted(set(t for t in bare_frames if t not in expected))
    stats["number_frames"] = len(bare_frames)
    stats["number_frame_unknown"] = len(unknown)
    if unknown:
        msg = (f"[지문번호] 원고에 없는 번호 프레임 {len(unknown)}종 잔존"
               f" (템플릿 잔재): " + ", ".join(unknown[:10]))
        (critical if strict_numbers else warnings).append(msg)

    # ── G4b 고아 번호 페이지 (W14 c03/c15 실증) ─────────────────────────
    # 지문번호/문항번호 프레임은 있는데 콘텐츠 스토리가 전혀 없는 페이지 —
    # 원고 없는 스텝의 섹션 머리/예시 페이지(c03 '20' 3p), 또는 W13 스레드
    # 절단 이후 빈 프레임 페이지가 삭제 판정(다중 프레임 전부 빈)을
    # 벗어나며 남은 잔재(c15 '5' 3p). page_cleanup 사용 시 critical.
    # 콘텐츠 판정은 '플랜(원고) 단락과 겹치는 스토리'만 — 섹션 마커
    # (" 빈칸 어휘")/발문/예시 등 내지 장식 텍스트는 콘텐츠가 아니다
    # (c03 p6/p10/p11: 마커·예시 텍스트 때문에 '내용 있음'으로 오인 방지).
    plan_texts = set()
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                tt = _clean(p.get("t", ""))
                if len(tt) >= 4:
                    plan_texts.add(tt)
    num_pages = set()
    content_pages = set()
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        pgs = story.get("pg") or []
        if len(ps) == 1 and _RE_BARE_NUM.match(_clean(ps[0].get("t", ""))):
            num_pages.update(pgs)
        elif any(_clean(p.get("t", "")) in plan_texts
                 for p in ps if len(_clean(p.get("t", ""))) >= 4):
            content_pages.update(pgs)
    orphan_pages = sorted(num_pages - content_pages, key=lambda x: (
        int(x) if str(x).isdigit() else 10**9, str(x)))
    stats["orphan_number_pages"] = len(orphan_pages)
    if orphan_pages:
        msg = (f"[잔여페이지] 번호 프레임만 있고 콘텐츠 없는 페이지 "
               f"{len(orphan_pages)}개: p" + ", p".join(
                   str(p) for p in orphan_pages[:10]))
        (critical if strict_pages else warnings).append(msg)

    # ── G4 잔여 페이지 (원고 없는 스텝/남는 사이클) ──────────────────────
    stale = dump.get("stale_pages")
    if stale is None:
        warnings.append("[잔여페이지] 덤프에 페이지 정보 없음(구버전 덤프)"
                        " — 재덤프 필요")
    else:
        empty_prefix = ((plan.get("page_cleanup") or {})
                        .get("empty_master", "M")
                        if isinstance(plan.get("page_cleanup"), dict)
                        else "M")
        residual = [e for e in stale
                    if not str(e.get("m", "")).startswith(empty_prefix)]
        stats["stale_pages"] = len(residual)
        if residual:
            names = [str(e.get("p")) for e in residual]
            msg = (f"[잔여페이지] 내용 없는 스텝/사이클 페이지 "
                   f"{len(residual)}개 잔존: p" + ", p".join(names[:12])
                   + ("…" if len(names) > 12 else ""))
            (critical if strict_pages else warnings).append(msg)

    # ── G5 step2_a1 상단 / step2_a1_btm 하단 기하 검사 ───────────────────
    flows = {fl["step"]: fl for fl in plan.get("flows", [])}
    if "step2_a1" in flows and "step2_a1_btm" in flows:
        st_top = _find_story_with_text(dump, _flow_probe_text(flows["step2_a1"]))
        st_btm = _find_story_with_text(dump,
                                       _flow_probe_text(flows["step2_a1_btm"]))
        if st_top and st_btm and st_top.get("b") and st_btm.get("b"):
            shared = set(st_top.get("pg") or []) & set(st_btm.get("pg") or [])
            if shared and st_top["b"][0] >= st_btm["b"][0]:
                msg = ("[상하반전] step2_a1(상단)이 step2_a1_btm(하단)보다 "
                       f"아래에 배치됨 (top {st_top['b'][0]} ≥ "
                       f"{st_btm['b'][0]})")
                (critical if pos_used else warnings).append(msg)
                stats["a1_swapped"] = True
            else:
                stats["a1_swapped"] = False
        elif st_top and st_btm:
            warnings.append("[상하배치] 덤프에 프레임 좌표 없음(구버전 덤프)"
                            " — 상/하단 검사 생략")

    # ── G9 미사용 업로드 원고 (W13 — 부분 침묵 유실 보고) ────────────────
    if uploads_dir and os.path.isdir(uploads_dir):
        expected_unused, suspicious = find_unused_uploads(content,
                                                          uploads_dir)
        stats["unused_uploads_expected"] = expected_unused
        stats["unused_uploads"] = suspicious
        if suspicious:
            warnings.append(
                f"[미사용원고] {len(suspicious)}개 파일이 어느 스텝에도 "
                f"사용되지 않음 (파일명 규칙 확인): "
                + " | ".join(suspicious[:5]))

    # ── G6 파싱 계층: 구조적 헤더 후보 미인식 (경고) ─────────────────────
    for key in _HEADER_STEPS:
        sd = steps.get(key)
        if not isinstance(sd, dict):
            continue
        paras = sd.get("paragraphs") or []
        cands = [i for i in range(len(paras))
                 if _is_struct_header_candidate(paras, i)]
        if not cands:
            continue
        recognized = 0
        for i in cands:
            t = _norm_header(paras[i].get("text") or "")
            if is_header_line(t) or is_a1_header(t) or t.startswith("["):
                recognized += 1
        if recognized == 0:
            warnings.append(
                f"[헤더미인식] {key}: 구조적 헤더 후보 {len(cands)}개 중 "
                f"인식 0개 — 새 헤더 형식 의심: "
                + (paras[cands[0]].get("text") or "")[:40])

    return {"ok": not critical, "critical": critical, "warnings": warnings,
            "stats": stats}
