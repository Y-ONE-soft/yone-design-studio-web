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
    """header.xml에서 underline type=BOTTOM인 charPr ID를 찾는다."""
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
    return None


def classify_part1(paragraphs: list, log=None) -> dict:
    """PART1 중요문장 원고를 분류하여 content.json['part1'] 구조로 반환."""
    entries = []
    prev_section = None

    for p in paragraphs:
        t = p['text'].strip()
        if not t:
            continue
        # 원고 첫 줄 제목 제거
        if '세서특필' in t and '중요' in t and len(t) < 30:
            continue

        # 헤더 감지 (출처)
        sec = _section_name(t)
        if sec is not None:
            # 대분류 변경 시 소제목 자동 삽입
            if sec != prev_section:
                entries.append({'style': P1_SOJEOMOK, 'text': "  " + sec})
                prev_section = sec
            entries.append({'style': P1_HEADER, 'text': t})
            continue

        # 영어 핵심문장 {…}
        if t.startswith('{') and t.endswith('}'):
            entries.append({'style': P1_ENGLISH, 'text': t[1:-1]})
            continue

        # 문법 레이블 [...]
        if t.startswith('[') and t.endswith(']'):
            entries.append({'style': P1_GRAMMAR_LABEL, 'text': t})
            continue

        # 나머지: 한글 해석, 문법 패턴 <...>, 설명 등
        entries.append({'style': P1_BODY, 'text': t})

    if log:
        log(f"[파서] PART1: {len(entries)}개 단락")
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


def classify_part2(paragraphs: list, school: str = "", log=None) -> dict:
    """PART2 실전문제+정답 원고를 분류."""
    header_re = _HEADER_RE_GM2 if '2' in school else _HEADER_RE_GM1
    has_jogeon = '2' in school  # 광문2만 조건 스타일 있음

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
        log(f"[파서] PART2 본문: {len(main_entries)}개, 정답: {len(answer_entries)}개")

    return {
        'main': main_entries,
        'answers': answer_entries,
    }


# ---------------------------------------------------------------------------
#  통합 파서 엔트리포인트
# ---------------------------------------------------------------------------
def parse_all(part1_path: str, part2_path: str, school: str,
              output_json: str, log=None) -> str:
    """PART1 + PART2 hwpx를 파싱하여 content.json 생성."""
    import json

    if log:
        log(f"[파서] PART1 파싱: {os.path.basename(part1_path)}")
    part1_paras = _parse_hwpx_paragraphs(part1_path)
    part1 = classify_part1(part1_paras, log)

    if log:
        log(f"[파서] PART2 파싱: {os.path.basename(part2_path)}")
    part2_paras = _parse_hwpx_paragraphs(part2_path)
    part2 = classify_part2(part2_paras, school, log)

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
