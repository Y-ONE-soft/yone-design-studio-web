"""세서특필 hwpx 파서.

PART1(중요문장) + PART2(실전문제+정답) hwpx 파일을 파싱하여
InDesign 조판용 content.json을 생성한다.
"""
import html
import os
import re
import zipfile

# ---------------------------------------------------------------------------
#  PART1 스타일 코드
# ---------------------------------------------------------------------------
P1_SOJEOMOK       = 0   # 소제목 (자동 생성: 교과서/올림포스/모의고사)
P1_HEADER         = 1   # 핵심문장_단원
P1_ENGLISH        = 2   # 핵심문장_음영
P1_BODY           = 3   # 단락 스타일 2
P1_GRAMMAR_LABEL  = 4   # 핵심문장_박스
P1_ANSWER         = 5   # 답안지 (핵심문장 아래 써보는 빈 칸)

# ---------------------------------------------------------------------------
#  PART2 스타일 코드
# ---------------------------------------------------------------------------
P2_CHULCHEO       = 0   # 출처
P2_SILJEUN_NUM    = 1   # 실전문제_번호
P2_JIMUN          = 2   # 지문
P2_SEONJI         = 3   # 선지
P2_BAEGYEONG      = 4   # 배경
P2_BOGI           = 5   # 보기
P2_JOGEON         = 6   # 조건

# ---------------------------------------------------------------------------
#  hwpx 공통 파싱
# ---------------------------------------------------------------------------
_P_PAT   = re.compile(r'<hp:p\b[^>]*>(.*?)</hp:p>', re.DOTALL)
_RUN_PAT = re.compile(r'<hp:run\b([^>]*)>(.*?)</hp:run>', re.DOTALL)
_T_PAT   = re.compile(r'<hp:t>(.*?)</hp:t>', re.DOTALL)
_CPR_PAT = re.compile(r'charPrIDRef="(\d+)"')


def _find_underline_ids(header_xml: str) -> set:
    """header.xml에서 underline type=BOTTOM인 charPr ID를 찾는다.

    ※ core.extract._parse_underline_ids와 의미가 다름 (BOTTOM 한정 vs NONE 외 전부)
      — 세서특필 원고 특성에 맞춘 것. 통합은 Phase 2에서 검토.
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(header_xml)
    ul_ids = set()
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'charPr' and elem.get('id'):
            cid = int(elem.get('id'))
            for child in elem:
                ctag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if ctag == 'underline' and child.get('type') == 'BOTTOM':
                    ul_ids.add(cid)
    return ul_ids


def _parse_hwpx_paragraphs(hwpx_path: str):
    """hwpx ZIP -> [(text, runs:[{text,ul}], has_ul)]"""
    with zipfile.ZipFile(hwpx_path) as zf:
        header_xml = zf.read('Contents/header.xml').decode('utf-8')
        section_xml = zf.read('Contents/section0.xml').decode('utf-8')

    ul_ids = _find_underline_ids(header_xml)
    paragraphs = []

    for p_match in _P_PAT.finditer(section_xml):
        runs = []
        has_ul = False
        for run_match in _RUN_PAT.finditer(p_match.group(1)):
            cpr = _CPR_PAT.search(run_match.group(1))
            cid = int(cpr.group(1)) if cpr else 0
            texts = _T_PAT.findall(run_match.group(2))
            txt = html.unescape("".join(texts))
            is_ul = cid in ul_ids
            if is_ul and txt:
                has_ul = True
            if txt:
                runs.append({'text': txt, 'ul': is_ul})

        full_text = "".join(r['text'] for r in runs)
        paragraphs.append({
            'text': full_text,
            'runs': runs,
            'has_ul': has_ul,
        })

    return paragraphs


def _compute_ul_ranges(runs):
    """runs -> [(start, end), ...]  밑줄 문자 범위"""
    ranges = []
    offset = 0
    for run in runs:
        rlen = len(run['text'])
        if run['ul']:
            ranges.append((offset, offset + rlen))
        offset += rlen
    return ranges


# ---------------------------------------------------------------------------
#  PART1 분류
# ---------------------------------------------------------------------------
def _section_name(header_text: str):
    """헤더 텍스트에서 대분류(교과서/올림포스/모의고사 등) 추출."""
    t = header_text.strip()
    if re.match(r'^(공통영어|영어)', t):
        return "교과서"
    if re.match(r'^(올림포스|Reading Power)', t):
        sec = "올림포스" if "올림포스" in t else "Reading Power"
        return sec
    if re.match(r'^고\d', t):
        m = re.match(r'^(고\d\s*\d+년\s*\d+월)', t)
        return m.group(1) if m else "모의고사"
    # 수능특강(고3): 강 / TEST 단위로 범위 구분
    if re.match(r'^수능특강', t):
        m = re.match(r'^(수능특강\s*영어\s*(?:\d+강|TEST\s*\d+))', t)
        return m.group(1) if m else "수능특강"
    return None


def classify_part1(paragraphs: list, log=None) -> dict:
    """PART1 중요문장 원고를 분류하여 content.json['part1'] 구조로 반환."""
    entries = []
    prev_section = None
    prev_english = False   # 직전이 영어 핵심문장이면, 그 해석 뒤에 답안지(써보는 칸) 삽입

    for p in paragraphs:
        t = p['text'].strip()
        if not t:
            continue
        # 원고 파일 제목 줄 제거 (예: "…세서특필 중요문장", "광문고 3학년 세서특필 Part 1.")
        if '세서특필' in t and len(t) < 40 and ('중요' in t or 'Part' in t or 'part' in t):
            continue

        # 헤더 감지 (출처) → 범위 구분 소제목 + 핵심문장_단원
        sec = _section_name(t)
        if sec is not None:
            # 대분류(범위) 변경 시 소제목 자동 삽입
            if sec != prev_section:
                entries.append({'style': P1_SOJEOMOK, 'text': "  " + sec})
                prev_section = sec
            entries.append({'style': P1_HEADER, 'text': t})
            prev_english = False
            continue

        # 영어 핵심문장 {…}
        if t.startswith('{') and t.endswith('}'):
            entries.append({'style': P1_ENGLISH, 'text': t[1:-1]})
            prev_english = True
            continue

        # 문법 레이블 [...]
        if t.startswith('[') and t.endswith(']'):
            entries.append({'style': P1_GRAMMAR_LABEL, 'text': t})
            prev_english = False
            continue

        # 나머지: 한글 해석, 문법 패턴 <...>, 설명 등
        entries.append({'style': P1_BODY, 'text': t})
        # 영어 핵심문장 바로 뒤의 해석이면 → 그 아래에 답안지(써보는 빈 칸) 삽입
        if prev_english:
            entries.append({'style': P1_ANSWER, 'text': ''})
            prev_english = False

    if log:
        log(f"[파서] PART1: {len(entries)}개 단락")
        # 배치 G (W37): 대분류(출처) 헤더 0건 = _section_name 열거가 못 읽는
        # 새 교과/출처 명칭 가능 — 소제목·핵심문장_단원 스타일이 통째로 빠진 채
        # 본문 스타일로 침묵 흡수되던 지점 ([경고]만, 동작 무변경).
        if entries and prev_section is None:
            _first = next((e['text'][:50] for e in entries if e['text']), '')
            log("[경고] PART1: 대분류 헤더(교과서/올림포스/모의고사/수능특강)가 "
                f"하나도 인식되지 않았습니다 — 새 출처 명칭이면 _section_name "
                f"열거 확인 필요. 첫 단락: {_first!r}")
    return {
        'paragraphs': [
            {'style': e['style'], 'text': e['text']}
            for e in entries
        ],
    }


# ---------------------------------------------------------------------------
#  PART2 분류
# ---------------------------------------------------------------------------
_HEADER_RE_GM1 = re.compile(r'^(공통영어|올림포스|고\d\s*\d+년|고1 2025년)')
_HEADER_RE_GM2 = re.compile(r'^(영어|올림포스|고\d\s*\d+년|고2 26년|Reading Power)')
_QUESTION_RE = re.compile(r'^\d+\.\s')

# 배치 G (W37): 광문1/2 하드코딩 데이터화 — 출처 헤더 패턴 + 조건 스타일 유무를
# part2_profiles.json 데이터 테이블에서 로드 (새 표기/학교 = 테이블 추가).
# 로드 실패 시 위 리터럴 폴백 (fail-open — 동작 하한 유지).
_PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "part2_profiles.json")


def _load_part2_profiles():
    import json
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        profiles = {}
        for key, p in raw["profiles"].items():
            profiles[key] = {
                "header_re": re.compile(p["header_pattern"]),
                "has_jogeon": bool(p["has_jogeon"]),
            }
        select = raw.get("select", {})
        return {"profiles": profiles, "select": select}
    except Exception:
        # 폴백: 종전 하드코딩과 동일 (데이터 파일 훼손이 조판을 막지 않는다)
        return {
            "profiles": {
                "gm1": {"header_re": _HEADER_RE_GM1, "has_jogeon": False},
                "gm2": {"header_re": _HEADER_RE_GM2, "has_jogeon": True},
            },
            "select": {"school_contains": {"2": "gm2"}, "default": "gm1"},
        }


_PART2_PROFILES = _load_part2_profiles()


def _part2_profile(school: str):
    """학교명 → PART2 프로필 (데이터 테이블 select 규칙 — 종전 `'2' in school`
    분기와 동일 의미론)."""
    sel = _PART2_PROFILES.get("select", {})
    for token, key in (sel.get("school_contains") or {}).items():
        if token in (school or "") and key in _PART2_PROFILES["profiles"]:
            return key, _PART2_PROFILES["profiles"][key]
    default = sel.get("default", "gm1")
    return default, _PART2_PROFILES["profiles"][default]


def classify_part2(paragraphs: list, school: str = "", log=None) -> dict:
    """PART2 실전문제+정답 원고를 분류."""
    profile_key, profile = _part2_profile(school)
    header_re = profile["header_re"]
    has_jogeon = profile["has_jogeon"]  # 광문2 계열만 조건 스타일 있음
    # 배치 G: 출처 후보 미분류 가시화용 — 다른 프로필의 눈 (로그만, 판정 미사용)
    _other_res = [p["header_re"] for k, p in _PART2_PROFILES["profiles"].items()
                  if k != profile_key]
    _demoted_srcs = []

    main_entries = []
    answer_entries = []
    in_answers = False
    after_arrow = False
    in_bogi = False
    in_jogeon = False

    for p in paragraphs:
        t = p['text'].strip()
        if not t:
            continue

        # 정답 섹션 분리
        if t == '정답':
            in_answers = True
            continue
        if in_answers:
            m = re.match(r'^(\d+)\.\s+(.*)', t, re.DOTALL)
            if m:
                answer_entries.append({
                    'num': m.group(1),
                    'text': m.group(2).replace('\n', ' ').replace('\r', ' '),
                })
            else:
                # 다중 행 답변 ([예시], ■ 키워드 등)
                answer_entries.append({
                    'num': '',
                    'text': t.replace('\n', ' ').replace('\r', ' '),
                })
            continue

        # 밑줄 범위 계산
        ul_ranges = _compute_ul_ranges(p['runs']) if p['has_ul'] else []
        ul_key = p['text'][:50].replace('\n', ' ').replace('\r', ' ') if ul_ranges else None
        ul_len = len(p['text']) if ul_ranges else None
        ul_ranges_str = ",".join(f"{s}:{e}" for s, e in ul_ranges) if ul_ranges else None

        style = -1

        # 조건 블록 (광문2 전용)
        if has_jogeon:
            if t.startswith('< 조건 >') or t.startswith('<조건>'):
                style = P2_JOGEON
                in_jogeon = True
                in_bogi = False
                after_arrow = False
            elif in_jogeon:
                if (t.startswith('밑줄') or t.startswith('총 ') or
                    (re.match(r'^\d+\.\s', t) and
                     any(kw in t for kw in ['단어', '사용', '영작', '의미']))):
                    style = P2_JOGEON
                elif t.startswith('[') and '/' in t:
                    style = P2_JOGEON
                else:
                    in_jogeon = False

        if style < 0:
            if header_re.match(t):
                style = P2_CHULCHEO
                in_bogi = False
                after_arrow = False
                in_jogeon = False
            elif t in ('\u2193', '\u21d3'):  # ↓ ⇓
                style = P2_JIMUN
                after_arrow = True
                in_bogi = False
            elif after_arrow:
                style = P2_BAEGYEONG
                after_arrow = False
            elif t.startswith('< 보기 >') or t.startswith('<보기>'):
                style = P2_BOGI
                in_bogi = True
            elif in_bogi:
                if _QUESTION_RE.match(t) or header_re.match(t):
                    in_bogi = False
                elif re.search(r'[a-zA-Z]', t) and ('/' in t or len(t) < 120):
                    style = P2_BOGI
                else:
                    in_bogi = False

        if style < 0:
            if _QUESTION_RE.match(t):
                style = P2_SILJEUN_NUM
                in_bogi = False
            elif re.match(r'^\[[A-E]\]$', t):
                style = P2_JIMUN
            elif re.match(r'^\([a-z]\)', t) or re.match(r'^[\u24d0-\u24e9]', t):
                style = P2_SEONJI
            elif t.startswith('_____') or t.startswith(' _____') or t.startswith('Answer'):
                style = P2_SEONJI
            elif len(t) > 80 and re.search(r'[a-zA-Z]{4,}', t):
                style = P2_JIMUN
            elif re.search(r'_{5,}', t):
                style = P2_SEONJI
            else:
                style = P2_SEONJI  # default
                # 배치 G: 선택 프로필은 못 읽었지만 다른 프로필이 출처로 보는
                # 라인 = 출처 후보의 선지 침묵 강등 — 수집해 [경고] (동작 무변경)
                if any(r.match(t) for r in _other_res):
                    _demoted_srcs.append(t)

        entry = {
            'style': style,
            'text': p['text'].replace('\n', ' ').replace('\r', ' '),
        }
        if ul_key:
            entry['ul_key'] = ul_key
            entry['ul_len'] = ul_len
            entry['ul_ranges'] = ul_ranges_str
        main_entries.append(entry)

    if log:
        log(f"[파서] PART2 본문: {len(main_entries)}개, 정답: {len(answer_entries)}개"
            f" (프로필 {profile_key})")
        if _demoted_srcs:
            log(f"[경고] PART2: 출처 헤더 후보 {len(_demoted_srcs)}건이 프로필 "
                f"'{profile_key}' 패턴에 미매치되어 선지 스타일로 강등됐습니다 "
                "(다른 프로필은 출처로 인식하는 표기 — part2_profiles.json 확인):")
            for t_src in _demoted_srcs[:5]:
                log(f"    • {t_src[:60]!r}")

    return {
        'main': main_entries,
        'answers': answer_entries,
    }


# ---------------------------------------------------------------------------
#  PART2 새 형식 (문제접근법 intro + [N~M] 문제세트) 분류
# ---------------------------------------------------------------------------
#  style 코드 (JSX p2Styles 와 일치):
#    0 출처  1 실전문제_번호(=프레임브레이크 트리거)  2 지문  3 선지  4 배경
#    5 보기  6 조건  7 소제목(대표유형)  8 핵심문장_박스(▷,💡)  9 step
#    10 설명_기본  11 세희T  12 서답형_발문
_NEW_GROUP = re.compile(r'^\[\s*\d+\s*~\s*\d+\s*\]')          # [1~3] 문제 그룹
_NEW_TYP   = re.compile(r'^대표유형')
_NEW_STEP  = re.compile(r'^Step\s*\d')
_NEW_SUBQ  = re.compile(r'(윗글을|윗글의|주어진 단어|다음 글의|위 글의|다음 글을|다음은)')
_NEW_SRC   = re.compile(r'^<.*?(미래엔|능률|YBM|비상|천재|동아|올림포스|Reading Power|공통영어|영어|본문).*?>$')
_NEW_BOGI  = re.compile(r'(\S+\s*/\s*){2,}\S+')               # a / b / c ...


def _clean_lb(t: str) -> str:
    """원고에 박힌 <hp:lineBreak/> 등 잔여 태그를 공백으로 정리."""
    t = re.sub(r'<hp:[^>]*>', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _is_passage(t: str) -> bool:
    return (len(t) > 55 and len(re.findall(r'[A-Za-z]{3,}', t)) >= 6
            and not t.startswith('(') and '/' not in t[:30])


def is_new_part2_format(paragraphs: list) -> bool:
    """대표유형 / [N~M] 마커가 있으면 새 형식."""
    for p in paragraphs[:150]:
        t = p['text'].strip()
        if _NEW_TYP.match(t) or _NEW_GROUP.match(t):
            return True
    return False


def classify_part2_new(paragraphs: list, log=None) -> dict:
    """새 형식 PART2 → {intro:[{text,style}], main:[{text,style}]}.
    그룹 = 출처<...> + [N~M] 헤더(다음글을읽고) + 지문 + 발문(실전문제_번호)들."""
    texts = [_clean_lb(p['text']) for p in paragraphs if p['text'].strip()]
    texts = [t for t in texts if t]
    # main 시작 = 첫 [N~M]. 단 바로 앞 출처(<...>)가 있으면 그 출처부터 포함
    gi = next((i for i, t in enumerate(texts) if _NEW_GROUP.match(t)), len(texts))
    main_start = gi
    if gi > 0 and _NEW_SRC.match(texts[gi - 1]):
        main_start = gi - 1

    # --- intro (대표유형 문제접근법 + 풀이 예시) ---
    intro = []
    for t in texts[1:main_start]:
        if _NEW_TYP.match(t):                                   c = 7
        elif t.startswith('▷') or t.startswith('💡') or t.startswith('★'): c = 8   # ▷ 💡 ★ → 핵심문장_박스
        elif _NEW_STEP.match(t):                                c = 9
        elif t.startswith('🔥') or t.startswith('세희T') or t.strip() == '풀이 사고과정': c = 11  # 🔥 세희T → 세희T 강조
        elif t.startswith('☞'):                            c = 10     # ☞
        elif t.startswith('〈보기') or t.startswith('<보기'): c = 5      # 〈보기〉 → 보기
        elif t.startswith('⇒'):                          c = 3      # ⇒ 답란 → 선지
        elif _NEW_GROUP.match(t):                               c = 13
        elif _NEW_SUBQ.search(t) and '시오' in t:       c = 12  # intro 예시 발문(번호 미소비)
        elif _NEW_SRC.match(t):                                 c = 0
        elif t.startswith('[요약문'):               c = 4      # [요약문]
        elif t.startswith('[정답]') or t.startswith('[보기'): c = 3
        elif _is_passage(t):                                    c = 2
        else:                                                   c = 10
        intro.append({'text': t, 'style': c})

    # --- main (문제 세트) ---
    main = []
    skip = False
    summ = False        # [요약문] 모드 (다음 지문도 배경)
    for t in texts[main_start:]:
        if _NEW_GROUP.match(t):
            main.append({'text': t, 'style': 13})   # 다음 글을 읽고 (그룹헤더)
            skip = False
            summ = False
            continue
        if t.startswith('[정답]'):           # [정답] (정답은 별도파일 → 스킵)
            skip = True
            continue
        if skip:
            if (_NEW_SUBQ.search(t) and '시오' in t) or _NEW_GROUP.match(t) or _NEW_SRC.match(t):
                skip = False
            else:
                continue
        if _NEW_SRC.match(t):
            main.append({'text': t, 'style': 0}); summ = False; continue          # 출처
        if t.startswith('[요약문'):                                    # [요약문] → 배경
            main.append({'text': t, 'style': 4}); summ = True; continue
        if _NEW_SUBQ.search(t) and '시오' in t:                            # 발문 → 실전문제_번호
            qt = re.sub(r'^\d+\.\s*', '', t)        # 선행 "N. " 제거(실전문제_번호 자동번호와 중복 방지)
            main.append({'text': qt, 'style': 1}); summ = False; continue
        if t.startswith('<보기') or t.startswith('[보기') or t == '[보기]':
            main.append({'text': t, 'style': 5}); summ = False; continue
        if _NEW_BOGI.search(t) and len(re.findall(r'[A-Za-z]{2,}', t)) >= 3 and len(t) < 170:
            main.append({'text': t, 'style': 5}); summ = False; continue
        if t.startswith('<조건') or re.match(r'^\d+\.\s', t):
            main.append({'text': t, 'style': 6}); continue
        if summ and _is_passage(t):                                                # 요약문 지문 → 배경
            main.append({'text': t, 'style': 4}); summ = False; continue
        if _is_passage(t):
            main.append({'text': t, 'style': 2}); continue
        main.append({'text': t, 'style': 3})

    if log:
        groups = sum(1 for e in main if e['style'] == 13)
        log(f"[\ud30c\uc11c] PART2 \uc0c8\ud615\uc2dd: intro {len(intro)}\ub2e8\ub77d, \ubb38\uc81c {len(main)}\ub2e8\ub77d, \uadf8\ub8f9 {groups}\uac1c")
    return {'intro': intro, 'main': main}


# ---------------------------------------------------------------------------
#  정답·해설 (별도 파일) 파싱
# ---------------------------------------------------------------------------
#  실전문제(PART2)와 분리되어 별도 파일로 작업된 정답·해설지를 파싱한다.
#  파일 형식 예:
#    ■ [1~3] 영어I 미래엔(김) 4과 본문 1     ← 출처/범위 헤더
#    1. (A) ... (B) ...                       ← 정답(번호, 다중행 가능)
#    2. ...
#    해설 1) ...                              ← 해설 풀이
#    해설 2) ...
#  배치: 번호별로 [번호 → 정답 → 해설] 묶음. 해설 본문은 '정답 사본' 스타일 사용.
#  출력: [{text, style}]  style 0=해설_번호 사본, 1=정답 사본, 2=출처(헤더)
_ANS_NUM_RE  = re.compile(r'^(\d+)\.\s*(.*)$', re.DOTALL)
_EXP_RE      = re.compile(r'^해설\s*(\d+)\s*[)\.]\s*(.*)$', re.DOTALL)
_ANS_HEADER_RE = re.compile(r'^■')


def _read_docx_texts(path: str):
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "python-docx 미설치 — docx 정답/해설을 읽으려면 'pip install python-docx' 후 재시도")
    doc = Document(path)
    return [p.text for p in doc.paragraphs]


def _read_paragraph_lines(path: str):
    """hwpx/docx → 줄 단위 텍스트 리스트 (단락 내 줄바꿈도 분리)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".hwpx":
        texts = [p['text'] for p in _parse_hwpx_paragraphs(path)]
    elif ext == ".docx":
        texts = _read_docx_texts(path)
    else:
        raise ValueError(f"지원하지 않는 형식: {ext} ({os.path.basename(path)})")
    lines = []
    for t in texts:
        for ln in re.split(r'[\r\n]+', t):
            ln = ln.strip()
            if ln:
                lines.append(ln)
    return lines


def parse_answer_explanation(answer_paths, log=None) -> list:
    """별도 정답·해설 파일(들)을 파싱하여 [{text, style}] 단락 리스트 생성."""
    if isinstance(answer_paths, str):
        answer_paths = [answer_paths]

    blocks = []
    cur = None
    mode = None        # 'answer' | 'explanation'
    cur_answer = None

    def ensure_block():
        nonlocal cur
        if cur is None:
            cur = {'header': None, 'answers': [], 'explanations': []}
            blocks.append(cur)

    for path in answer_paths:
        if not path or not os.path.exists(path):
            if log:
                log(f"[파서] 정답/해설 파일 없음 (무시): {path}")
            continue
        if log:
            log(f"[파서] 정답/해설 파싱: {os.path.basename(path)}")
        for t in _read_paragraph_lines(path):
            if _ANS_HEADER_RE.match(t):
                cur = {'header': t, 'answers': [], 'explanations': []}
                blocks.append(cur)
                mode = None
                cur_answer = None
                continue
            m_exp = _EXP_RE.match(t)
            if m_exp:
                ensure_block()
                cur['explanations'].append(
                    {'num': m_exp.group(1), 'text': m_exp.group(2).strip()})
                mode = 'explanation'
                cur_answer = None
                continue
            m_ans = _ANS_NUM_RE.match(t)
            if m_ans:
                ensure_block()
                cur_answer = {'num': m_ans.group(1), 'lines': []}
                rest = m_ans.group(2).strip()
                if rest:
                    cur_answer['lines'].append(rest)
                cur['answers'].append(cur_answer)
                mode = 'answer'
                continue
            # 번호/헤더 아닌 줄 = 이전 항목의 연속
            if mode == 'answer' and cur_answer is not None:
                cur_answer['lines'].append(t)
            elif mode == 'explanation' and cur and cur['explanations']:
                cur['explanations'][-1]['text'] += ' ' + t
            # 그 외(제목 등 선행 잡음) 무시

    entries = []
    q_count = 0
    for b in blocks:
        if b['header']:
            entries.append({'text': b['header'], 'style': 2})
        answers, exps = b['answers'], b['explanations']
        for i, a in enumerate(answers):
            entries.append({'text': a['num'] + ") ", 'style': 0})
            q_count += 1
            for ln in a['lines']:
                entries.append({'text': ln, 'style': 1})
            if i < len(exps):
                entries.append({'text': "해설 " + exps[i]['text'], 'style': 1})
        # 정답보다 해설이 많으면 남은 해설은 번호와 함께 출력
        for j in range(len(answers), len(exps)):
            entries.append(
                {'text': "해설 " + exps[j]['num'] + ") " + exps[j]['text'], 'style': 1})

    if log:
        log(f"[파서] 정답/해설: {len(blocks)}블록, {q_count}문항, {len(entries)}단락")
    return entries


def _legacy_answers_to_entries(answers) -> list:
    """part2 내장 정답(레거시 {num,text})을 새 {text,style} 구조로 변환."""
    out = []
    for a in answers or []:
        num = a.get('num') if isinstance(a, dict) else None
        text = a.get('text', '') if isinstance(a, dict) else str(a)
        if num:
            out.append({'text': num + ") ", 'style': 0})
        out.append({'text': text, 'style': 1})
    return out


# ---------------------------------------------------------------------------
#  통합 파서 엔트리포인트
# ---------------------------------------------------------------------------
def parse_all(part1_path: str, part2_path: str, school: str,
              output_json: str, log=None, answer_paths=None) -> str:
    """PART1 + PART2(+별도 정답·해설) hwpx를 파싱하여 content.json 생성."""
    import json

    if log:
        log(f"[파서] PART1 파싱: {os.path.basename(part1_path)}")
    part1_paras = _parse_hwpx_paragraphs(part1_path)
    part1 = classify_part1(part1_paras, log)

    if log:
        log(f"[파서] PART2 파싱: {os.path.basename(part2_path)}")
    part2_paras = _parse_hwpx_paragraphs(part2_path)
    if is_new_part2_format(part2_paras):
        # 새 형식(문제접근법 intro + [N~M] 문제세트)
        if log:
            log("[파서] PART2 형식 판정: 새형식 (선두 150단락 내 '대표유형'/"
                "'[N~M]' 마커 발견)")  # 배치 G: 형식 분기 근거 가시화
        p2 = classify_part2_new(part2_paras, log)
        part2 = {'intro': p2['intro'], 'main': p2['main'], 'answers': []}
    else:
        # 구 형식(출처→실전문제_번호→지문→…)
        if log:
            log("[파서] PART2 형식 판정: 구형식 (새형식 마커 미발견 — 오판 시 "
                "전체 오분류이므로 원고가 새형식이면 마커 표기를 확인하세요)")
        part2 = classify_part2(part2_paras, school, log)
        part2.setdefault('intro', [])

    # 정답·해설: 별도 파일이 있으면 그걸로, 없으면 part2 내장 정답(레거시) 변환
    if answer_paths:
        part2['answers'] = parse_answer_explanation(answer_paths, log)
    else:
        part2['answers'] = _legacy_answers_to_entries(part2.get('answers', []))

    data = {
        'school': school,
        'part1': part1,
        'part2': part2,
    }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if log:
        log(f"[파서] content.json 생성 완료 ({os.path.getsize(output_json):,} bytes)")

    return output_json
