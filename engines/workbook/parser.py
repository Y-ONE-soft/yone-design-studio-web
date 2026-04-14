"""
워크북 원고 파서

docx/hwp 원고 → 단락 목록 → STEP별 분류 → content.json

지원 형식:
  - docx: python-docx (zipfile + XML) 직접 파싱
  - hwp:  블랙북 방식 (hwpx ZIP → section XML + header XML)

원고 파일별 처리:
  Step1 A1~C2, Step2 B1~C2: 텍스트만 추출
  Step2 A1 어법선택: 텍스트 + 밑줄 추출 (runs[].ul)
  Step3 실전문제 (hwp): 텍스트 + 밑줄 추출

단락 데이터 구조:
  {"text": str, "runs": [{"t": str, "ul": bool}]}
"""

import html
import json
import os
import re
import struct
import sys
import unicodedata
import zipfile


def _nfc(s):
    """macOS NFD 파일명을 NFC로 정규화."""
    return unicodedata.normalize('NFC', s)


# ── docx 파싱 ───────────────────────────────────────────────────────────────

_NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _docx_extract_paragraphs(docx_path, extract_underline=False):
    """
    docx → [{"text": str, "runs": [{"t": str, "ul": bool}]}]
    extract_underline=False면 runs는 단일 {"t": text, "ul": False}로 통합.
    """
    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read('word/document.xml')

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_content)

    paragraphs = []
    for p_elem in root.iter(f'{{{_NS_W}}}p'):
        runs = []
        for r_elem in p_elem.iter(f'{{{_NS_W}}}r'):
            # 각주/미주 참조 마커가 포함된 run 스킵
            if (r_elem.find(f'{{{_NS_W}}}footnoteReference') is not None or
                    r_elem.find(f'{{{_NS_W}}}endnoteReference') is not None):
                continue

            # 텍스트 수집
            text_parts = []
            for t_elem in r_elem.iter(f'{{{_NS_W}}}t'):
                if t_elem.text:
                    text_parts.append(t_elem.text)
            text = ''.join(text_parts)
            if not text:
                continue

            # 밑줄 확인
            is_ul = False
            if extract_underline:
                rpr = r_elem.find(f'{{{_NS_W}}}rPr')
                if rpr is not None:
                    u_elem = rpr.find(f'{{{_NS_W}}}u')
                    if u_elem is not None:
                        val = u_elem.get(f'{{{_NS_W}}}val', '')
                        if val and val != 'none':
                            is_ul = True

            runs.append({"t": text, "ul": is_ul})

        # 빈 단락도 포함 (구분자 역할)
        full_text = ''.join(r['t'] for r in runs)
        paragraphs.append({
            "text": full_text,
            "runs": runs if runs else [{"t": "", "ul": False}],
        })

    return paragraphs


# ── hwp/hwpx 파싱 (블랙북 방식 재활용) ──────────────────────────────────────

def _parse_underline_ids(header_xml):
    """밑줄 서식이 적용된 charPr id 집합 반환."""
    ul_ids = set()
    for m in re.finditer(r'<hh:charPr\b([^>]*)>(.*?)</hh:charPr>', header_xml, re.DOTALL):
        id_m = re.search(r'\bid="(\d+)"', m.group(1))
        if not id_m:
            continue
        body = m.group(2)
        ul_m = re.search(r'<hh:underline\s+type="([^"]+)"', body)
        if ul_m and ul_m.group(1).upper() != 'NONE':
            ul_ids.add(id_m.group(1))
    return ul_ids


def _hwpx_extract_segments(body, ul_ids):
    """hp:run → (text, underline, new_para) 세그먼트 목록."""
    segments = []
    for run_m in re.finditer(r'<hp:run\s+charPrIDRef="(\d+)"[^>]*>(.*?)</hp:run>', body, re.DOTALL):
        ref_id = run_m.group(1)
        run_body = run_m.group(2)
        is_ul = ref_id in ul_ids
        # \b prevents matching <hp:tbl>, <hp:tab> etc.
        for t_m in re.finditer(r'<hp:t\b[^>]*>(.*?)</hp:t>', run_body, re.DOTALL):
            raw = t_m.group(1)
            # Replace <hp:tab .../> with tab character
            raw = re.sub(r'<hp:tab\b[^/]*/>', '\t', raw)
            parts = re.split(r'<hp:lineBreak\s*/>', raw)
            for j, part in enumerate(parts):
                # Strip any remaining stray XML tags
                part = re.sub(r'<[^>]+>', '', part)
                text = html.unescape(part)
                segments.append({"t": text, "ul": is_ul, "new_para": j > 0})
    return segments


def _hwpx_extract_paragraphs(hwpx_path, extract_underline=False, exclude_footnotes=False):
    """
    hwpx → [{"text": str, "runs": [{"t": str, "ul": bool}]}]
    exclude_footnotes: 시그니처 호환용 (hwpx는 항상 endNote/footnote XML 태그 제거).
    """
    with zipfile.ZipFile(hwpx_path, 'r') as zf:
        names = zf.namelist()
        section_name = next(
            (n for n in names if re.search(r'section\d+\.xml', n, re.I)), None
        )
        if not section_name:
            raise ValueError(f"section XML을 찾을 수 없음: {hwpx_path}")
        section_xml = zf.read(section_name).decode('utf-8')

        header_name = next(
            (n for n in names if re.search(r'header\.xml', n, re.I)), None
        )
        header_xml = zf.read(header_name).decode('utf-8') if header_name else ''

    ul_ids = _parse_underline_ids(header_xml) if (extract_underline and header_xml) else set()

    # 미주/각주 제거
    section_xml = re.sub(r'<hp:endNote\b.*?</hp:endNote>', '', section_xml, flags=re.DOTALL)
    section_xml = re.sub(r'<hp:footnote\b.*?</hp:footnote>', '', section_xml, flags=re.DOTALL)

    paragraphs = []
    for m in re.finditer(r'<hp:p\b([^>]*)>(.*?)</hp:p>', section_xml, re.DOTALL):
        body = m.group(2)
        segments = _hwpx_extract_segments(body, ul_ids)

        cur_runs = []
        first_flush = True

        def flush():
            nonlocal first_flush
            text = ''.join(r['t'] for r in cur_runs)
            paragraphs.append({
                "text": text,
                "runs": [r for r in cur_runs if r['t']] or [{"t": "", "ul": False}],
            })
            first_flush = False

        for seg in segments:
            if seg['new_para']:
                flush()
                cur_runs = []
            cur_runs.append({"t": seg["t"], "ul": seg["ul"]})

        if cur_runs:
            flush()

    return paragraphs


# ── hwp (비압축 바이너리) 파싱 ───────────────────────────────────────────────

def _hwp_is_hwpx(path):
    """파일이 hwpx(ZIP) 형식인지 확인."""
    try:
        with zipfile.ZipFile(path, 'r') as z:
            return any('section' in n.lower() for n in z.namelist())
    except zipfile.BadZipFile:
        return False


def _hwp_decode_paratext(payload):
    """HWP5 PARA_TEXT 레코드의 payload를 struct 기반으로 디코딩.

    HWP5 제어 문자 크기 (단위: 워드=2바이트):
    - 코드 0~2: 없음/예약 → 8워드(16바이트)
    - 코드 3: 필드 시작 → 8워드
    - 코드 4~9: 인라인 → 8워드
    - 코드 10: 줄바꿈 → 1워드(2바이트)
    - 코드 11~12: 탭/미정 → 8워드
    - 코드 13: 줄바꿈2 → 1워드
    - 코드 14~23: 확장 제어 → 8워드
    - 코드 24~31: 예약 → 1워드
    """
    # 8워드(16바이트) 크기 제어 코드 집합
    _EXTENDED = set(range(0, 10)) - {10}
    _EXTENDED.update(range(11, 24))  # 11~23

    result = []
    i = 0
    while i < len(payload):
        if i + 1 >= len(payload):
            break
        code = struct.unpack_from('<H', payload, i)[0]
        if code < 0x20:
            if code == 10 or code == 13:
                result.append('\n')
                i += 2
            elif code in _EXTENDED:
                i += 16  # 8워드 = 16바이트
            else:
                i += 2
        else:
            result.append(chr(code))
            i += 2
    return ''.join(result).strip()


def _hwp_decode_para_charshape(payload):
    """PARA_CHAR_SHAPE(tagid=68): (문자위치, charshape_id) 쌍 추출."""
    pairs = []
    i = 0
    while i + 7 < len(payload):
        pos = struct.unpack_from('<I', payload, i)[0]
        csid = struct.unpack_from('<I', payload, i + 4)[0]
        pairs.append((pos, csid))
        i += 8
    return pairs


def _hwp_build_charshape_ul(hwp):
    """DocInfo CHAR_SHAPE(tagid=21)에서 밑줄 여부 맵 생성.

    HWP5 CharShape 레코드 구조:
    - offset 0-13: 7 WORD (fontface ID)
    - offset 14-41: 각종 font 속성
    - offset 42-45: INT32 (base size)
    - offset 46-49: UINT32 (property flags) ← 밑줄 정보 여기
      bit 0: italic, bit 1: bold, bit 2-3: underline (0=없음,1=밑줄)
    """
    ul_map = {}
    idx = 0
    for rec in hwp.docinfo.records():
        if rec.get('tagid') != 21:
            continue
        payload = rec.get('payload', b'')
        has_ul = False
        if len(payload) >= 50:
            flags = struct.unpack_from('<I', payload, 46)[0]
            has_ul = ((flags >> 2) & 3) == 1  # 1=밑줄
        ul_map[idx] = has_ul
        idx += 1
    return ul_map


def _hwp_text_with_underline(para_text_payload, charshape_pairs, ul_map):
    """PARA_TEXT payload를 디코딩하면서 charshape 기반 밑줄 run 생성."""
    # 원본 위치별 밑줄 여부 매핑
    # charshape_pairs: [(pos, csid), ...] — pos는 원본 payload 내 문자 인덱스
    pos_ul = {}  # {원본위치: bool}
    for cp_idx in range(len(charshape_pairs)):
        start_pos = charshape_pairs[cp_idx][0]
        end_pos = charshape_pairs[cp_idx + 1][0] if cp_idx + 1 < len(charshape_pairs) else 999999
        csid = charshape_pairs[cp_idx][1]
        is_ul = ul_map.get(csid, False)
        for p in range(start_pos, end_pos):
            pos_ul[p] = is_ul

    # payload 디코딩 + 밑줄 매핑
    _EXTENDED = set(range(0, 10)) - {10}
    _EXTENDED.update(range(11, 24))

    runs = []
    cur_text = ""
    cur_ul = False
    char_idx = 0  # payload 내 문자 인덱스 (워드 단위)

    i = 0
    while i < len(para_text_payload):
        if i + 1 >= len(para_text_payload):
            break
        code = struct.unpack_from('<H', para_text_payload, i)[0]
        if code < 0x20:
            if code == 10 or code == 13:
                # 줄바꿈 — run 분리 없이 추가
                ul = pos_ul.get(char_idx, cur_ul)
                if ul != cur_ul and cur_text:
                    runs.append({"t": cur_text, "ul": cur_ul})
                    cur_text = ""
                    cur_ul = ul
                cur_text += '\n'
                char_idx += 1
                i += 2
            elif code in _EXTENDED:
                char_idx += 8  # 확장 제어는 8워드
                i += 16
            else:
                char_idx += 1
                i += 2
        else:
            ul = pos_ul.get(char_idx, cur_ul)
            ch = chr(code)
            if ul != cur_ul and cur_text:
                runs.append({"t": cur_text, "ul": cur_ul})
                cur_text = ""
            cur_ul = ul
            cur_text += ch
            char_idx += 1
            i += 2

    if cur_text:
        runs.append({"t": cur_text, "ul": cur_ul})

    text = ''.join(r['t'] for r in runs).strip()
    # strip 후 runs도 정리
    if runs:
        runs[0]['t'] = runs[0]['t'].lstrip()
        runs[-1]['t'] = runs[-1]['t'].rstrip()
        runs = [r for r in runs if r['t']]

    return text, runs or [{"t": text, "ul": False}]


# ➀~➄ (U+2780-2784, dingbat 원문자) → ①~⑤ (U+2460-2464, 표준 원문자)
_DINGBAT_TO_STD = str.maketrans('\u2780\u2781\u2782\u2783\u2784',
                                 '\u2460\u2461\u2462\u2463\u2464')


def _normalize_circled_numbers(paras):
    """➀➁➂➃➄ → ①②③④⑤ 정규화 (폰트 글리프 깨짐 방지)."""
    for p in paras:
        p['text'] = p['text'].translate(_DINGBAT_TO_STD)
        for r in p.get('runs', []):
            r['t'] = r['t'].translate(_DINGBAT_TO_STD)
    return paras


def _hwp_extract_paragraphs(hwp_path, extract_underline=False, exclude_footnotes=False):
    """
    hwp 파일 파싱. hwpx(ZIP)이면 hwpx 파서 사용, 아니면 pyhwp + struct 디코딩.
    밑줄 추출: CHAR_SHAPE + PARA_CHAR_SHAPE 레코드 활용.
    exclude_footnotes: True면 level 3 레코드를 전부 제외 (Step3용 — 각주/미주 완전 제거).
    """
    if _hwp_is_hwpx(hwp_path):
        return _normalize_circled_numbers(
            _hwpx_extract_paragraphs(hwp_path, extract_underline, exclude_footnotes)
        )

    try:
        from hwp5.xmlmodel import Hwp5File
    except ImportError:
        raise RuntimeError(
            f"hwp 바이너리 파일({os.path.basename(hwp_path)})은 pyhwp가 필요합니다. "
            "pip install pyhwp 실행 후 재시도하세요."
        )

    hwp = Hwp5File(hwp_path)
    ul_map = _hwp_build_charshape_ul(hwp) if extract_underline else {}
    sec = hwp.bodytext.section(0)
    all_recs = list(sec.records())

    # HWP5 구조:
    # level 1 = 본문 단락
    # level 3 = 미주/각주 또는 문제 내용(표, 선지 등)
    #
    # exclude_footnotes=True (Step3 등):
    #   level 3 전부 제외 — Step3에서는 모든 level 3이 각주/미주(정답+해설)
    # exclude_footnotes=False (Step1/Step2 등):
    #   level 3 중 CTRL 11/12로 감지되는 FOOTNOTE 블록만 제외, 나머지 포함

    # Pass 1: FOOTNOTE 블록의 level 3 레코드 인덱스 수집 (선택적 필터링용)
    footnote_l3_set = set()
    if not exclude_footnotes:
        for ri, rec in enumerate(all_recs):
            if rec.get('tagid') != 67 or rec.get('level', 1) != 1:
                continue
            payload = rec.get('payload', b'')
            has_footnote = False
            j = 0
            while j < len(payload) - 1:
                code = struct.unpack_from('<H', payload, j)[0]
                if code in (11, 12):
                    has_footnote = True
                    break
                if code < 0x20 and code not in (10, 13):
                    j += 16
                else:
                    j += 2
            if has_footnote:
                # 이 단락 직후의 level 3 블록을 미주로 표시
                for rj in range(ri + 1, len(all_recs)):
                    if all_recs[rj].get('tagid') == 67:
                        if all_recs[rj].get('level', 1) == 1:
                            break  # 다음 level 1 만나면 중단
                        if all_recs[rj].get('level') == 3:
                            footnote_l3_set.add(rj)

    paragraphs = []
    i = 0
    while i < len(all_recs):
        rec = all_recs[i]
        rec_level = rec.get('level', 1)
        if rec.get('tagid') != 67:
            i += 1
            continue
        # level 1: 항상 포함
        if rec_level == 1:
            pass  # 포함
        elif exclude_footnotes:
            # Step3: level 1이 아닌 모든 레코드 제외 (각주/미주 완전 제거)
            i += 1
            continue
        elif rec_level == 3 and i not in footnote_l3_set:
            pass  # 문제 내용 → 포함
        else:
            i += 1
            continue

        # PARA_CHAR_SHAPE 찾기 (다음 레코드들 중 tagid=68, 같은 level)
        cs_pairs = []
        for j in range(i + 1, min(i + 6, len(all_recs))):
            if all_recs[j].get('tagid') == 68 and all_recs[j].get('level', 1) == rec_level:
                cs_pairs = _hwp_decode_para_charshape(all_recs[j]['payload'])
                break
            if all_recs[j].get('tagid') == 67:
                break

        try:
            if extract_underline and cs_pairs and ul_map:
                txt, runs = _hwp_text_with_underline(rec['payload'], cs_pairs, ul_map)
            else:
                txt = _hwp_decode_paratext(rec['payload'])
                runs = [{"t": txt, "ul": False}]
        except Exception:
            i += 1
            continue

        if txt:
            paragraphs.append({"text": txt, "runs": runs})
        i += 1

    return _normalize_circled_numbers(paragraphs)


# ── 원고 공통 전처리 ────────────────────────────────────────────────────────

# 원고 헤더 패턴 (스킵할 줄)
_RE_MANUSCRIPT_HEADER = re.compile(
    r'^(?:'
    r'고[12]_\d{4}_\d+월'     # "고1_2025_10월(경기도) - 읽기영역..."
    r'|Q\.\s'                  # "Q. 문맥 상..."
    r'|어휘[선완]'              # "어휘선택(문제지)", "어휘완성(문제지)"
    r'|어법[선수]'              # "어법선택(문제지)", "어법수정..."
    r'|빈칸어'                  # "빈칸어휘(문제지)"
    r'|낱말배열'                # "낱말배열(문제지)"
    r'|문장배열'                # "문장배열(문제지)"
    r'|\d+\.\s+어휘\d+단계'    # "1. 어휘1단계_Hard"
    r'|\d+\.\s+내용[일종]'     # "1. 내용일치_Normal", "1. 내용종합_Normal"
    r')'
)

# 지문 번호 구분자
_RE_BRACKET_NUM = re.compile(r'^\s*\[(\d+)\]\s*$')           # [20]
_RE_HEADER_NUM = re.compile(r'^\s*\d+\.\s*p\d+-(?:no\.)?(\d+(?:~\d+)?)')  # "1. p2-no.18" or "18. p8-no.41~42"


def _strip_manuscript_headers(paragraphs):
    """원고 앞부분의 헤더 줄 제거. 첫 지문 시작([N] 또는 번호 헤더)까지 스킵."""
    start_idx = 0
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        if not text:
            continue
        # 지문 시작 감지
        if _RE_BRACKET_NUM.match(text) or _RE_HEADER_NUM.match(text):
            start_idx = i
            break
        # 헤더 패턴이면 스킵
        if _RE_MANUSCRIPT_HEADER.match(text):
            start_idx = i + 1
            continue
        # 헤더도 아니고 지문 시작도 아닌 첫 줄 → 여기서 시작
        start_idx = i
        break

    return paragraphs[start_idx:]


def _extract_question_numbers(paragraphs, step_key):
    """원고에서 지문번호 목록 추출."""
    numbers = []
    for p in paragraphs:
        text = p['text'].strip()
        m = _RE_BRACKET_NUM.match(text)
        if m:
            numbers.append(int(m.group(1)))
            continue
        m = _RE_HEADER_NUM.match(text)
        if m:
            # "41~42" 같은 범위는 첫 번호만 사용
            num_str = m.group(1).split('~')[0]
            numbers.append(int(num_str))
    return numbers


def _clean_empty_lines(paras):
    """연속 빈줄 제거, 단일 빈줄은 유지."""
    cleaned = []
    prev_empty = False
    for p in paras:
        is_empty = not p['text'].strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(p)
        prev_empty = is_empty
    return cleaned


_RE_LESSON_MARKER = re.compile(r'^\s*\[L\d+[-—]\d+\]\s*$')  # [L1-9], [L2-3] 등


def _strip_lesson_markers(paras):
    """교과서 원고의 [L1-9] 형식 단원 구분 마커 제거."""
    return [p for p in paras if not _RE_LESSON_MARKER.match(p['text'])]


# 정답 구간 감지 패턴
_RE_ANSWER_SECTION = re.compile(
    r'^\s*\d+\.\s*(?:어휘|내용[일종]|어법|빈칸|영작|문장).*(?:정답|_정답)', re.UNICODE
)
_RE_ANSWER_HEADER = re.compile(r'^\s*(?:번호|정답)\s*$')
_RE_ANSWER_AND_EXPLANATION = re.compile(
    r'^\s*정답\s*(?:과|및|&)\s*해설\s*$', re.UNICODE
)
_RE_QUICK_ANSWER = re.compile(
    r'^\s*빠른\s*정답\s*찾기\s*$', re.UNICODE
)


def _remove_answer_section(paras):
    """
    원고에서 정답 섹션 제거.
    감지 패턴:
    - "1. 내용일치_Normal_정답" 등
    - "정답 및 해설" / "정답과 해설" 단독 줄
    - "빠른 정답 찾기" 단독 줄
    패턴이 나타나면 그 이후 모든 단락을 제거.
    """
    for i, p in enumerate(paras):
        text = p['text'].strip()
        if _RE_ANSWER_SECTION.match(text):
            return paras[:i]
        if _RE_ANSWER_AND_EXPLANATION.match(text):
            return paras[:i]
        if _RE_QUICK_ANSWER.match(text):
            return paras[:i]
        # "번호" 단독 줄 + "정답" 단독 줄 연속 = 정답 테이블 시작
        if _RE_ANSWER_HEADER.match(text) and i > 0:
            prev = paras[i - 1]['text'].strip()
            if _RE_ANSWER_SECTION.match(prev) or _RE_ANSWER_HEADER.match(prev):
                return paras[:i - 1]
    return paras


def _filter_short_questions(paras, short_numbers):
    """
    짤지문 번호에 해당하는 지문 구간을 제거.
    [18], [19], [25]~[28], [43]~[45] 번호의 지문과 그 내용을 삭제.
    헤더 패턴(p2-no.18 등)도 동일하게 처리.
    """
    if not short_numbers:
        return paras

    short_set = set(short_numbers)
    # 41~42, 43~45 같은 복합 번호도 처리
    combined_short = set()
    for n in short_numbers:
        combined_short.add(str(n))
    combined_short.add('41~42')  # 이건 일반지문이지만 일단 보존
    combined_short.add('43~45')

    result = []
    skip = False

    for p in paras:
        text = p['text'].strip()

        # 브래킷 패턴: [18]
        m = _RE_BRACKET_NUM.match(text)
        if m:
            num = int(m.group(1))
            if num in short_set:
                skip = True
                continue
            else:
                skip = False
                result.append(p)
                continue

        # 헤더 패턴: "1. p2-no.18" 또는 "25. p8-no.43~45"
        m2 = re.match(r'^\s*\d+\.\s*p\d+-(?:no\.)?(\d+(?:~\d+)?)', text)
        if m2:
            num_str = m2.group(1)
            if '~' in num_str:
                first_num = int(num_str.split('~')[0])
            else:
                first_num = int(num_str)
            if first_num in short_set:
                skip = True
                continue
            else:
                skip = False
                result.append(p)
                continue

        if not skip:
            result.append(p)

    return result


# A1 구분자 패턴
_RE_A1_SECTION = re.compile(
    r'^\s*\d+\.\s*어휘\s*\d+\s*단계', re.UNICODE
)


def _split_a1_sections(paras):
    """
    A1 원고를 섹션별로 분리.
    "1. 어휘1단계_Hard" → step1_a1
    "2. 어휘2단계_Hard" → step1_a1_2
    정답 섹션(_정답)은 제외.
    """
    sections = {}
    current_key = None
    current_paras = []

    for p in paras:
        text = p['text'].strip()
        if _RE_A1_SECTION.match(text):
            # 이전 섹션 저장
            if current_key and current_paras:
                sections[current_key] = current_paras

            # 정답 섹션 판별
            is_answer = '정답' in text
            if is_answer:
                current_key = None
                current_paras = []
                continue

            # 섹션 키 결정
            if '2단계' in text:
                current_key = "step1_a1_2"
            else:
                current_key = "step1_a1"
            current_paras = []
            continue

        if current_key:
            current_paras.append(p)

    # 마지막 섹션 저장
    if current_key and current_paras:
        sections[current_key] = current_paras

    # 빈 결과면 원본 그대로 step1_a1에 넣기
    if not sections:
        sections["step1_a1"] = paras

    return sections


# ── Step3 파싱 ───────────────────────────────────────────────────────────────

# 정답/해설 패턴 (Step3 hwp)
# "②: ⓑ making → make (...)" 또는 "③, ④" 뒤에 ": " + 해설
_RE_STEP3_ANSWER = re.compile(
    r'^\s*[①②③④⑤]\s*(?:,\s*[①②③④⑤]\s*)*:\s*.+'
)


_RE_STEP3_SINGLE_ANSWER = re.compile(
    r'^\s*[①②③④⑤](?:\s*,\s*[①②③④⑤])*\s*$'
)


def _strip_step3_answers(paras):
    """
    Step3 hwp에서 정답+해설 줄 제거.
    제거 대상:
    1. "②: ⓑ making → make (해설...)" — 원문자+콜론+해설
    2. ": (B) broken → alive..." — 콜론으로 시작하는 해설 이어짐
    3. "⑤" 또는 "②, ③" — 단독 정답번호 (문제 바로 다음 줄)
    """
    result = []
    for p in paras:
        text = p['text'].strip()
        if _RE_STEP3_ANSWER.match(text):
            continue
        if text.startswith(': ') and len(text) > 10:
            continue
        if _RE_STEP3_SINGLE_ANSWER.match(text):
            continue
        result.append(p)
    return result


def _parse_step3_folder(step3_dir, grade, year, month, normal_questions,
                        short_questions, combined_questions, extract_underline=True):
    """
    Step3 폴더 → 지문별 단락 목록.
    파일명: "고1 25년 9월 20번.hwp" 형태.
    반환: {"normal": [...], "short": [...]}
    각 항목: {"question_num": "20", "code": "250920", "paragraphs": [...]}
    """
    if not os.path.isdir(step3_dir):
        return {"normal": [], "short": []}

    # 연도 2자리, 월 2자리
    yy = str(year)[-2:]
    mm = str(month).zfill(2)

    # 파일 목록 수집 (NFD→NFC 정규화 필수)
    files = {}
    for fname_raw in os.listdir(step3_dir):
        fname = _nfc(fname_raw)
        if not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
            continue
        # "고1 25년 9월 20번.hwp" 또는 "고1 25년 9월 41~42번.docx"
        m = re.search(r'(\d+(?:~\d+)?)번\.(?:hwpx?|docx)', fname, re.I)
        if m:
            num_str = m.group(1)
            files[num_str] = os.path.join(step3_dir, fname_raw)  # 원본 경로 사용

    normal_items = []
    short_items = []

    # 복합 문제 번호 역매핑 (41 → "41~42")
    num_to_combined = {}
    for key, nums in combined_questions.items():
        file_key = key.replace('-', '~')
        for n in nums:
            num_to_combined[n] = file_key

    processed_file_keys = set()

    def _process_question(q_num, target_list):
        # 복합 문제 확인
        file_key = str(q_num)
        if q_num in num_to_combined:
            file_key = num_to_combined[q_num]

        if file_key in processed_file_keys:
            return
        processed_file_keys.add(file_key)

        fpath = files.get(file_key)
        if not fpath:
            # 단일 번호로도 시도
            fpath = files.get(str(q_num))

        if not fpath:
            return

        if fpath.lower().endswith('.docx'):
            paras = _docx_extract_paragraphs(fpath, extract_underline)
        else:
            paras = _hwp_extract_paragraphs(fpath, extract_underline, exclude_footnotes=True)
        # Step3 정답/해설 줄 제거 (level 3 제외 후에도 level 1에 남은 정답 줄 처리)
        paras = _strip_step3_answers(paras)
        code = f"{yy}{mm}{str(q_num).zfill(2)}"

        target_list.append({
            "question_num": file_key,
            "code": code,
            "paragraphs": paras,
        })

    for q in sorted(normal_questions):
        _process_question(q, normal_items)

    for q in sorted(short_questions):
        _process_question(q, short_items)

    # 교과서 Step3: 번호 없는 hwpx 파일 처리 (normal/short가 모두 비어있을 때)
    if not normal_items and not short_items:
        textbook_paras = []
        for fname_raw in sorted(os.listdir(step3_dir)):
            fname = _nfc(fname_raw)
            if not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
                continue
            if re.search(r'\d+번\.(?:hwpx?|docx)', fname, re.I):
                continue  # 이미 위에서 처리 대상이었던 파일
            if fname_raw.startswith('.'):
                continue
            fpath = os.path.join(step3_dir, fname_raw)
            if fpath.lower().endswith('.docx'):
                paras = _docx_extract_paragraphs(fpath, extract_underline)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline, exclude_footnotes=True)
            paras = _strip_step3_answers(paras)
            textbook_paras.extend(paras)
        if textbook_paras:
            normal_items.append({
                "question_num": "textbook",
                "code": "",
                "paragraphs": textbook_paras,
            })

    return {"normal": normal_items, "short": short_items}


def _find_manuscript_file(manuscript_dir, expected_filename):
    """config에 지정된 파일명이 없을 때 유사 파일을 찾는 fallback.

    전략:
    1. 정확 매칭 (공백/NFD 차이 허용)
    2. 확장자만 다른 파일 (.docx↔.hwp↔.hwpx)
    3. 접미사 차이 허용 (예: '영작배열' vs '영작배열(서술형)')
    """
    import unicodedata

    base, ext = os.path.splitext(expected_filename)
    norm_base = unicodedata.normalize("NFC", base.replace(" ", "").lower())

    exact = []
    partial = []
    for f in os.listdir(manuscript_dir):
        fp = os.path.join(manuscript_dir, f)
        if not os.path.isfile(fp):
            continue
        f_base, f_ext = os.path.splitext(f)
        if f_ext.lower() not in ('.docx', '.hwp', '.hwpx'):
            continue
        f_norm = unicodedata.normalize("NFC", f_base.replace(" ", "").lower())
        if f_norm == norm_base:
            exact.append(fp)
        # 부분 매칭: 기대 이름이 실제 파일명의 시작부분과 일치
        elif f_norm.startswith(norm_base):
            partial.append(fp)
        # 역방향: 실제 파일명이 기대 이름의 시작부분
        elif norm_base.startswith(f_norm):
            partial.append(fp)

    # 정확 매칭 우선
    if exact:
        for c in exact:
            if os.path.splitext(c)[1].lower() == ext.lower():
                return c
        return exact[0]
    # 부분 매칭
    if partial:
        for c in partial:
            if os.path.splitext(c)[1].lower() == ext.lower():
                return c
        return partial[0]
    return None


# ── 공개 API ────────────────────────────────────────────────────────────────

def parse_manuscript_folder(manuscript_dir, config, grade, year, month, log=None):
    """
    원고 폴더 → content.json dict.

    Args:
        manuscript_dir: 워크북 원고 폴더 경로
        config: config.json dict
        grade: 1 또는 2
        year: 25 (2자리) 또는 2025 (4자리)
        month: 10 등
        log: callable(str) 로그 콜백
    Returns:
        dict (content.json 구조)
    """
    if log is None:
        log = lambda s: None

    file_map = config['manuscript_file_map']
    needs_ul = set(config.get('needs_underline', []))
    mockexam = config.get('mockexam', {})

    result = {
        "grade": grade,
        "year": year,
        "month": month,
        "steps": {},
    }

    # STEP1, STEP2 파싱
    for step_key, filename in file_map.items():
        fpath = os.path.join(manuscript_dir, filename)
        if not os.path.exists(fpath):
            # fallback: 파일명 공백/확장자 유연 매칭
            found = _find_manuscript_file(manuscript_dir, filename)
            if found:
                fpath = found
                filename = os.path.basename(found)
            else:
                log(f"[파서] 파일 없음, 건너뜀: {filename}")
                continue

        extract_ul = step_key in needs_ul
        ext = os.path.splitext(filename)[1].lower()

        log(f"[파서] {step_key}: {filename}" + (" (밑줄 추출)" if extract_ul else ""))

        if ext == '.docx':
            paras = _docx_extract_paragraphs(fpath, extract_ul)
        elif ext in ('.hwp', '.hwpx'):
            paras = _hwp_extract_paragraphs(fpath, extract_ul)
        else:
            log(f"[파서] 미지원 형식: {ext}")
            continue

        short_nums = mockexam.get('short_questions', [])

        # A1 특수 처리: "어휘1단계" / "어휘2단계" 로 분리
        if step_key == "step1_a1":
            sections = _split_a1_sections(paras)
            for sec_key, sec_paras in sections.items():
                sec_paras = _strip_manuscript_headers(sec_paras)
                sec_paras = _remove_answer_section(sec_paras)
                sec_paras = _filter_short_questions(sec_paras, short_nums)
                cleaned = _clean_empty_lines(sec_paras)
                q_nums = _extract_question_numbers(cleaned, sec_key)
                result["steps"][sec_key] = {
                    "filename": filename,
                    "question_numbers": q_nums,
                    "paragraph_count": len(cleaned),
                    "paragraphs": cleaned,
                }
                log(f"[파서] → {sec_key}: {len(cleaned)}개 단락, 지문 {len(q_nums)}개")
            continue

        # 정답 구간 제거
        paras = _remove_answer_section(paras)

        # 헤더 제거
        paras = _strip_manuscript_headers(paras)

        # 짤지문 필터링 (STEP1~2만, STEP3는 별도 처리)
        paras = _filter_short_questions(paras, short_nums)

        # [L1-9] 마커 제거 (교과서 원고)
        paras = _strip_lesson_markers(paras)

        # 빈 단락 필터
        cleaned = _clean_empty_lines(paras)

        # 지문번호 추출
        q_nums = _extract_question_numbers(cleaned, step_key)

        result["steps"][step_key] = {
            "filename": filename,
            "question_numbers": q_nums,
            "paragraph_count": len(cleaned),
            "paragraphs": cleaned,
        }
        log(f"[파서] → {len(cleaned)}개 단락, 지문 {len(q_nums)}개")

    # STEP3 파싱
    step3_dir = os.path.join(manuscript_dir, "Step3")
    if os.path.isdir(step3_dir):
        log(f"[파서] Step3 폴더 파싱 중...")
        step3_data = _parse_step3_folder(
            step3_dir, grade, year, month,
            mockexam.get('normal_questions', []),
            mockexam.get('short_questions', []),
            mockexam.get('combined_questions', {}),
        )
        result["steps"]["step3"] = {
            "normal": step3_data["normal"],
            "short": step3_data["short"],
            "normal_count": len(step3_data["normal"]),
            "short_count": len(step3_data["short"]),
        }
        log(f"[파서] → Step3 일반: {len(step3_data['normal'])}개, "
            f"짤지문: {len(step3_data['short'])}개")
    else:
        log(f"[파서] Step3 폴더 없음: {step3_dir}")

    return result


def main():
    """CLI: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>"""
    if len(sys.argv) < 6:
        print("사용법: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>")
        sys.exit(1)

    output_path = sys.argv[1]
    manuscript_dir = sys.argv[2]
    grade = int(sys.argv[3])
    year = int(sys.argv[4])
    month = int(sys.argv[5])

    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)

    def log(msg):
        print(msg)

    data = parse_manuscript_folder(manuscript_dir, config, grade, year, month, log)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_paras = sum(
        s.get('paragraph_count', 0) for k, s in data['steps'].items()
        if k != 'step3'
    )
    print(f"[파서] 완료: {len(data['steps'])}개 STEP, {total_paras}개 단락 → {output_path}")


if __name__ == '__main__':
    main()
