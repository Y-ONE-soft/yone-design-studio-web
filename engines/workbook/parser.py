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

    # 미주/각주 제거 (hwpx 실제 태그명: hp:endNote, hp:footNote — 대문자 N)
    section_xml = re.sub(r'<hp:endNote\b.*?</hp:endNote>', '', section_xml, flags=re.DOTALL)
    section_xml = re.sub(r'<hp:footNote\b.*?</hp:footNote>', '', section_xml, flags=re.DOTALL)

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
        elif 0xD800 <= code <= 0xDBFF and i + 3 < len(payload):
            # High surrogate — UTF-16 surrogate pair 결합 (supplementary plane: PUA U+F0000+ 등)
            low = struct.unpack_from('<H', payload, i + 2)[0]
            if 0xDC00 <= low <= 0xDFFF:
                combined = ((code - 0xD800) << 10) + (low - 0xDC00) + 0x10000
                result.append(chr(combined))
                i += 4
            else:
                i += 2  # 짝 안 맞는 단독 high surrogate 건너뜀
        elif 0xDC00 <= code <= 0xDFFF:
            i += 2  # 단독 low surrogate 건너뜀
        else:
            result.append(chr(code))
            i += 2
    # trailing 줄바꿈만 제거 (공백은 보존 — HWP 빈칸이 공백+밑줄 스타일로 입력되는 경우 보존 필수)
    return ''.join(result).rstrip('\n\r')


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
        elif 0xD800 <= code <= 0xDBFF and i + 3 < len(para_text_payload):
            # High surrogate — surrogate pair 결합 (supplementary plane 문자)
            low = struct.unpack_from('<H', para_text_payload, i + 2)[0]
            if 0xDC00 <= low <= 0xDFFF:
                combined = ((code - 0xD800) << 10) + (low - 0xDC00) + 0x10000
                ul = pos_ul.get(char_idx, cur_ul)
                ch = chr(combined)
                if ul != cur_ul and cur_text:
                    runs.append({"t": cur_text, "ul": cur_ul})
                    cur_text = ""
                cur_ul = ul
                cur_text += ch
                char_idx += 2  # surrogate pair는 원본에서 2 word 차지
                i += 4
            else:
                char_idx += 1
                i += 2  # 짝 안 맞는 단독 high surrogate 건너뜀
        elif 0xDC00 <= code <= 0xDFFF:
            char_idx += 1
            i += 2  # 단독 low surrogate 건너뜀
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

    # trailing 줄바꿈만 제거 (공백 보존 — HWP 빈칸이 공백+밑줄 스타일인 케이스 보존)
    text = ''.join(r['t'] for r in runs).rstrip('\n\r')
    if runs:
        runs[-1]['t'] = runs[-1]['t'].rstrip('\n\r')
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
                # HWP 5.0 ControlChar: 11=TABLE, 12=GSO(그림), 17=FOOTNOTE, 18=ENDNOTE
                # 표/그림은 본문 일부이므로 제외 대상이 아님. 진짜 각주/미주만 17/18.
                if code in (17, 18):
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

        # CTRL 11/12 는 footnote/endnote뿐 아니라 표/그림 같은 inline 컨트롤도 포함하는 듯.
        # 표 셀 안에 영문 본문이 들어있는 케이스(예: 수능특강 21강+)를 보호:
        # footnote_l3_set 안의 단락 중 "한국어 없는 긴 영문 단락"은 본문으로 간주하여 set에서 제외.
        _protect = set()
        for rj in footnote_l3_set:
            payload = all_recs[rj].get('payload', b'')
            try:
                txt = _hwp_decode_paratext(payload)
            except Exception:
                continue
            if len(txt) < 60:
                continue
            if re.search(r'[가-힣]', txt):
                continue
            alpha = sum(1 for c in txt if c.isalpha() and ord(c) < 128)
            if alpha >= 30:
                _protect.add(rj)
        footnote_l3_set -= _protect

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
    r'|틀린어법'                # "틀린어법(문제지)" — EBS A1 객관식
    r'|\d+\.\s+어휘\d+단계'    # "1. 어휘1단계_Hard"
    r'|\d+\.\s+내용[일종]'     # "1. 내용일치_Normal", "1. 내용종합_Normal"
    r'|마더텅\s+고[12]'        # "마더텅 고1 6강 옛날지문" (옛날 워크북 식별 헤더)
    r'|Reading\s*Power'        # "ReadingPower 유형편완성..." — EBS 리딩파워
    r'|\d{4}\s*수능특강'        # "2027수능특강 영어(2026) - ..." — EBS 수능특강
    r'|Exercises\s*$'          # 수능특강 발문 직후 "Exercises" 단독 줄
    r')'
)

# 지문 번호 구분자
_RE_BRACKET_NUM = re.compile(r'^\s*\[(\d+)\]\s*$')           # [20]
# 한글이 들어간 대괄호 발문: "[본문1]", "[다음 글의 ...]"
_RE_KOREAN_BRACKET = re.compile(r'^\s*\[[^\]]+\]\s*$')
# 페이지/레슨 마커: 출판사·교재 종류 무관하게 다양한 형식 매칭
#   p<n>, p.<n>           (모의고사/EBS:  p2, p.82)
#   L<n>                  (교과서 단순:  L1)
#   L<n>-p<n>, L<n>-p.<n> (교과서:       L4-p.82)
#   L<n>-본문<n>           (교과서:       L1-본문1)
#   U<n>                  (EBS Unit:     U6)
_RE_PAGE_MARKER = (
    r'(?:'
    r'L\d+(?:\s*[-–—]\s*(?:p\.?\d+|본문\d+))?'
    r'|p\.?\d+'
    r'|U\d+'
    r')'
)
# 지문 헤더: "[순서.] <페이지/레슨 마커>[-/구분자] [라벨] [<지문번호>][(부가정보)]"
#   예) "1. p2-no.18", "18. p8-no.41~42",
#       "1. p8-Example 1", "p66-Example 1",
#       "3. p86-no.1", "1. p8-Example 1  (정답 1개)",
#       "1. L4-p.82", "1. L4-p.82  (정답 1개)",
#       "1. L1-본문1  (정답 1개)"
# 라벨은 no., Example, Test 등 임의의 영문 토큰 허용 (특정 단어에 의존하지 않음).
_RE_HEADER_NUM = re.compile(
    r'^\s*'
    r'(?:\d+\s*[\.\)]\s*)?'                                  # 선행 순번 "N." 또는 "N)" (있으면)
    + _RE_PAGE_MARKER +                                       # 페이지/레슨 마커
    r'\s*[-–—\.]?\s*'                                        # 구분자 (선택)
    r'(?:no\.\s*|Example\s+|Practice\s+|[A-Za-z]+\.?\s*)?'   # 라벨 (선택)
    r'(\d+(?:\s*~\s*\d+)?)?'                                 # 지문 번호 (캡처, 선택)
    r'(?:\s*\([^\)]*\))?'                                    # 트레일링 부가정보 "(정답 1개)" 등 (선택)
    r'\s*$'
)
# Chapter 구분선 (EBS 등): "Chapter 03. 추론적 이해 - 09 빈칸 추론 (1)"
_RE_CHAPTER_DIVIDER = re.compile(r'^\s*Chapter\s+\d+\.\s', re.IGNORECASE)

# 옛 형식 워크북 헤더 (마더텅 옛 기출 등)
# "9번" 단독 줄 + "17년 11월 21번" 단독 줄 → "9. p0-no.21" 표준 형식으로 정규화
_RE_OLD_WB_NUM = re.compile(r'^\s*(\d+)\s*번\s*$')
_RE_OLD_WB_SOURCE = re.compile(r'^\s*\d+\s*년\s*\d+\s*월\s*(\d+)\s*번\s*$')


def _normalize_old_workbook_headers(paragraphs):
    """
    옛 마더텅 워크북 형식 헤더를 표준 형식으로 정규화.

    변환:
        "9번"               → 두 줄 합쳐 "9. p0-no.21" 한 줄로
        "17년 11월 21번"

    빈 단락이 사이에 끼어있어도 처리. 정상 원고(이미 "1. p2-no.20" 형식)에는
    매치되지 않으므로 영향 없음.
    """
    result = []
    i = 0
    n = len(paragraphs)
    while i < n:
        m_num = _RE_OLD_WB_NUM.match(paragraphs[i]['text'].strip())
        if m_num:
            # 다음 비빈 단락에서 출처(YY년 M월 K번) 패턴 찾기
            j = i + 1
            while j < n and not paragraphs[j]['text'].strip():
                j += 1
            if j < n:
                m_src = _RE_OLD_WB_SOURCE.match(paragraphs[j]['text'].strip())
                if m_src:
                    wb_num = m_num.group(1)
                    mock_num = m_src.group(1)
                    new_text = "%s. p0-no.%s" % (wb_num, mock_num)
                    result.append({
                        "text": new_text,
                        "runs": [{"t": new_text, "ul": False}],
                    })
                    i = j + 1
                    continue
        result.append(paragraphs[i])
        i += 1
    return result


# 옛 헤더 정규화 산출물 패턴 ("9. p0-no.21")
_RE_OLD_NORMALIZED_HEADER = re.compile(r'^\s*\d+\.\s*p0-no\.\d+', re.UNICODE)
# 정상(잡) 헤더 패턴 ("1. p3-no.21" 등, p0이 아닌 페이지 번호)
_RE_PRIMARY_HEADER_NONZERO = re.compile(r'^\s*\d+\.\s*p[1-9]\d*-no\.\d+', re.UNICODE)


def _strip_secondary_headers_after_old(paragraphs):
    """
    옛 헤더가 변환된 이후 본문 안에 끼어있는 정상 형식 헤더("1. p3-no.21" 등)를 제거.

    옛 마더텅 원고에는 본 보기 다음에 의미 없는 추가 헤더가 끼어있어 두 번째
    프레임브레이크가 잘못 들어가는 문제가 있다. 옛 헤더가 한 번이라도 변환된
    원고에서만 동작하므로 정상 원고("1. p2-no.20" 형식만 있음)에는 매치되지 않음.
    """
    has_old = False
    result = []
    for p in paragraphs:
        text = p['text'].strip()
        if _RE_OLD_NORMALIZED_HEADER.match(text):
            has_old = True
            result.append(p)
            continue
        if has_old and _RE_PRIMARY_HEADER_NONZERO.match(text):
            # 옛 블록 안에 끼어있는 잡 헤더 제거
            continue
        result.append(p)
    return result


# 본 보기 (A)~(Z) 패턴
_RE_CHOICE = re.compile(r'^\s*\([A-Z]\)\s')
# 원문자 ① ~ ⑳ 시작 또는 포함
_RE_CIRCLED_START = re.compile(r'^[\s\(]*[①-⑳⓵-⓿❶-❿]')


def _wrap_hadan_with_spaces(paragraphs):
    """
    옛 헤더 변환된 원고에서 본 보기 블록이 끝난 직후의 첫 비빈 영어 단락
    (= 문장 배열 하단의 '주어진 문장')에 양쪽 9칸 공백을 둘러싼다.

    정상 원고는 원본 .docx 단계에서 이미 양쪽 공백이 있어 has3PlusGaps을 트리거
    하지만, 옛 마더텅 원고는 공백 없이 평문으로 들어있어 BTM 인식이 안 된다.
    이 함수는 옛 헤더가 한 번이라도 변환된 원고에서만 동작하므로 정상 원고에
    영향이 없다.

    상태:
        IDLE / AFTER_HEADER / IN_CHOICES / AFTER_CHOICES
    """
    if not any(_RE_OLD_NORMALIZED_HEADER.match(p['text'].strip()) for p in paragraphs):
        return paragraphs

    result = []
    state = 'IDLE'

    for p in paragraphs:
        text = p['text'].strip()
        is_header = bool(_RE_OLD_NORMALIZED_HEADER.match(text)) or \
                    bool(_RE_PRIMARY_HEADER_NONZERO.match(text))
        is_choice = bool(_RE_CHOICE.match(text))
        is_empty = not text
        is_circled_start = bool(_RE_CIRCLED_START.match(text))

        if is_header:
            state = 'AFTER_HEADER'
            result.append(p)
            continue

        if state == 'AFTER_HEADER' and is_choice:
            state = 'IN_CHOICES'
            result.append(p)
            continue

        if state == 'IN_CHOICES':
            if is_choice:
                result.append(p)
                continue
            if is_empty:
                state = 'AFTER_CHOICES'
                result.append(p)
                continue
            # 보기 블록 안에 갑자기 다른 패턴 → 안전하게 종료
            state = 'AFTER_CHOICES'

        if state == 'AFTER_CHOICES':
            if is_empty:
                result.append(p)
                continue
            # 헤더면 다음 지문 시작 — wrap 없이 통과
            if is_header:
                state = 'AFTER_HEADER'
                result.append(p)
                continue
            # 원문자(①②) 시작 단락은 주어진 문장 아니라 BTM_T 본문 — 그대로
            if is_circled_start:
                state = 'IDLE'
                result.append(p)
                continue
            # (A)~(Z) — 주어진 문장 없이 바로 변형 보기 시작 — 그대로 BTM_T 처리에 맡김
            if is_choice:
                state = 'IDLE'
                result.append(p)
                continue
            # 그 외 영어 평문 단락 → 주어진 문장. 양쪽 9칸 공백 추가해 has3PlusGaps 트리거
            wrapped_text = "         " + p['text'] + "        "
            new_runs = ([{"t": "         ", "ul": False}] +
                        list(p.get('runs', [])) +
                        [{"t": "        ", "ul": False}])
            result.append({"text": wrapped_text, "runs": new_runs})
            state = 'IDLE'
            continue

        result.append(p)

    return result


def _strip_manuscript_headers(paragraphs):
    """원고 앞부분의 헤더 줄 제거.

    원고 구조: [책 제목 + 발문 + 섹션 라벨 + (선택적 부제목)] → [본문 마커 + 본문] 반복
    본문 마커 = 지문 헤더(`1. L4-p.82`, `1. p2-no.20`, `1. L1-본문1` 등) 또는 대괄호 발문(`[본문1]`, `[20]`).

    첫 본문 마커가 나오기 전까지의 모든 단락 = 헤더 영역으로 간주하고 제거.
    이렇게 단순화하면 책 제목/발문/섹션 라벨/부제목이 어떤 형식이든 (출판사/교재 변경 무관) 자동 처리됨.
    본문 마커가 끝까지 없는 STEP은 fallback으로 헤더 패턴 매칭을 사용.
    """
    # 1) 첫 본문 마커 찾기 → 그 앞 모두 헤더 영역으로 간주
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        if not text:
            continue
        if _RE_BRACKET_NUM.match(text) or _RE_HEADER_NUM.match(text) or _RE_KOREAN_BRACKET.match(text):
            return paragraphs[i:]

    # 2) 본문 마커가 끝까지 없음 → fallback: 헤더 패턴 매칭으로 스킵
    start_idx = 0
    for i, p in enumerate(paragraphs):
        text = p['text'].strip()
        if not text:
            continue
        if _RE_MANUSCRIPT_HEADER.match(text):
            start_idx = i + 1
            continue
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
            captured = m.group(1)
            if captured:
                # "41~42" 같은 범위는 첫 번호만 사용
                num_str = captured.split('~')[0]
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


def _strip_chapter_dividers(paras):
    """EBS 리딩파워 등의 챕터 구분선("Chapter 03. ...")을 모두 제거.

    원고 곳곳에 끼어있는 단순 구분선이며 지문 본문이 아니라서 그대로 두면
    프레임 브레이크가 잘못 들어가거나 본문에 흡수된다.
    """
    return [p for p in paras if not _RE_CHAPTER_DIVIDER.match(p['text'])]


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

        # 헤더 패턴: "1. p2-no.18", "25. p8-no.43~45", "1. p8-Example 1" 등
        m2 = _RE_HEADER_NUM.match(text)
        if m2:
            num_str = m2.group(1)
            if num_str is None:
                # 지문 번호가 캡처되지 않는 새 형식 헤더 (예: "1. L4-p.82") — 짤지문 매칭 대상 아님
                skip = False
                result.append(p)
                continue
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

# Step3 유형 태그: "[유형 1] 내용파악 & 대의파악" / "[유형 3] 빈칸추론" 등 섹션 라벨
_RE_STEP3_TYPE_TAG = re.compile(r'^\s*\[\s*유형\s*\d+\s*\]')
# 유형 부제: "(심경, 분위기, 지칭, 주제, ...)" 같이 한글 콤마 나열만 있는 한 줄
# - 괄호로 둘러싸이고
# - 한글 + 콤마(,)로만 구성된 부제
_RE_STEP3_TYPE_SUBTAG = re.compile(
    r'^\s*\(\s*[가-힣\s,/&·]+\s*\)\s*$'
)


def _strip_step3_type_tags(paras):
    """Step3 원고에서 유형 섹션 태그/부제를 모두 제거.

    예) "[유형 1] 내용파악 & 대의파악", "(심경, 분위기, 지칭, 주제, 제목, 주장, 요지, 내용일치)",
         "[유형 4] 지문 흐름파악", "(순서배열, 문장넣기, 무관한문장)" 등.
    이 줄들은 문제와 무관한 분류 라벨이므로 발문/지문/선지/조건/보기 구조에 끼어
    잘못된 단락스타일이 매핑되지 않도록 사전에 제거한다.
    """
    out = []
    for p in paras:
        text = p['text'].strip()
        if _RE_STEP3_TYPE_TAG.match(text):
            continue
        if _RE_STEP3_TYPE_SUBTAG.match(text):
            # 단, 짧고 (괄호 안에 한글 토큰 2개 이상 콤마로 나열) 구조여야만 부제로 간주
            inner = text.strip()[1:-1]
            tokens = [t.strip() for t in inner.replace('/', ',').split(',') if t.strip()]
            # 한글 토큰이 두 개 이상이면 부제로 판단 (단일 어휘 주석은 보존)
            kor_tokens = [t for t in tokens if any('가' <= c <= '힣' for c in t)]
            if len(kor_tokens) >= 2:
                continue
        out.append(p)
    return out


def _strip_step3_answers(paras):
    """
    Step3 hwp에서 정답+해설 줄 제거.
    제거 대상:
    1. "정답 및 해설" / "빠른 정답 찾기" / "정답지" 단독 헤더 → 그 이후 모든 단락 cut
       (MIXED 원고는 후반부에 정답해설 섹션이 통째로 붙어 있음)
    2. "②: ⓑ making → make (해설...)" — 원문자+콜론+해설
    3. ": (B) broken → alive..." — 콜론으로 시작하는 해설 이어짐
    4. "⑤" 또는 "②, ③" — 단독 정답번호 (문제 바로 다음 줄)
    """
    # 섹션 절단: 정답해설 섹션 헤더 발견 시 그 위치부터 끝까지 drop
    section_headers = ('정답 및 해설', '빠른 정답 찾기', '정답지')
    cut_idx = None
    for i, p in enumerate(paras):
        text = p['text'].strip()
        if text in section_headers:
            cut_idx = i
            break
    if cut_idx is not None:
        paras = paras[:cut_idx]

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


# Step3 5지선다 발문 패턴: '... 것은?' / '... 것을 두 개 고르시오' / '... 옳은 것은?' 등
_RE_STEP3_CHOICE_QUESTION = re.compile(
    r'^\s*\d+\.\s.*?(?:것은\??|것을\s+두\s*개\s*고르시오\.?|옳은\s*것은\??|적절한\s*곳은\??)\s*$'
)
# 5지선다에서 제외할 발문 (빈칸 채우기/영작 서술형/어법 객관식)
_RE_STEP3_NON_CHOICE = re.compile(
    r'요약하고자\s*한다|영어로\s*완성|찾아\s*쓰시오|바르게\s*고치시오|어형\s*변화'
)
# 선지가 지문 inline에 ①②③④⑤로 박혀 있는 발문 (자동 prepend skip)
# - "다음 글의 밑줄 친 부분 중 ... 어법상/문맥상 ... 적절하지 않은 것은?"
# - "다음 글의 흐름과 관계 없는 문장은?"
# - "글의 흐름상 주어진 문장이 들어가기에 가장 적절한 곳은?" (문장삽입: 주어진 문장은 보기, 선지 ①②③④⑤는 지문 inline 위치 마커)
# - "윗글의 (A), (B)에 들어갈 ... 바른 것은?" ((A)/(B) 매칭형: 선지가 표 형태 2개씩 짝)
# 이런 발문은 파서가 자동으로 ①~⑤를 추가하면 지문/보기/표 헤더 첫 글자에 ① 중복 발생
_RE_STEP3_INLINE_CHOICE = re.compile(
    r'밑줄\s*친\s*부분\s*중|흐름과\s*관계\s*없는\s*문장|어법상\s*틀린\s*것'
    r'|주어진\s*(?:문장|글)|들어갈\s*위치'
    r'|\(\s*A\s*\).{0,5}\(\s*B\s*\)'
)
# 단순 번호 발문 감지 (다음 발문 만나면 중단)
_RE_STEP3_QUESTION_LIKE = re.compile(r'^\s*\d+\.\s')
_CIRCLED_DIGITS = ['①', '②', '③', '④', '⑤']


def _add_step3_choice_numbers(paras):
    """Step3 hwp의 5지선다 자동번호(①②③④⑤) 텍스트화.

    hwp 파일은 5지선다 선지에 ①②③④⑤를 AutoNumbering 컨트롤로 표시하므로
    텍스트만 추출하면 번호가 누락된다 (어법 객관식처럼 본문에 직접 타이핑한 경우는
    이미 텍스트에 ①이 들어와 있어 영향 없음).

    구조 인식 방식:
    1. "밑줄 친 부분 중" / "흐름과 관계 없는 문장" 류 발문 → 선지가 지문 inline에
       ①~⑤로 박혀 있음 → 자동 prepend skip (지문 첫 글자에 ① 중복 방지)
    2. 그 외 5지선다 발문 → 발문 직후 시퀀스: 지문(영문 통문장) + 선지×5
       → 첫 영문 단락(지문)은 skip, 그 다음 5개 단락에 ①②③④⑤ prepend
    3. 빈칸 요약/영작 서술형/어법 고치기 등은 제외.
    """
    i = 0
    n = len(paras)
    while i < n:
        text = (paras[i].get('text', '') or '').strip()
        if not _RE_STEP3_CHOICE_QUESTION.match(text):
            i += 1
            continue
        if _RE_STEP3_NON_CHOICE.search(text):
            i += 1
            continue
        # 선지가 지문 inline에 박힌 발문 → 자동 prepend skip
        if _RE_STEP3_INLINE_CHOICE.search(text):
            i += 1
            continue

        # 발문 위에 묶음 마커(※/[Gateway]/[숫자])가 있으면 지문은 마커 아래에
        # 이미 존재 → 발문 직후는 바로 선지. 다른 발문은 건너뛰며 마커까지 거슬러 올라감.
        # 마커가 없으면 (예: 동아박 MIXED) 발문 직후 첫 영문 단락이 자기 지문.
        passage_above = False
        for k in range(i - 1, -1, -1):
            t_k = (paras[k].get('text', '') or '').strip()
            if not t_k:
                continue
            if t_k.startswith('※') or re.match(r'^\[(?:[Gg]ateway|\d+)\]$', t_k):
                passage_above = True
                break

        # 발문 직후 첫 영문 단락(지문) skip 후 5개 단락에 ①②③④⑤ prepend
        # (지문은 영문 알파벳 시작 + 한글 미포함 단락. 단락 1개만 skip)
        # passage_above=True면 지문은 발문 위에 이미 있으므로 skip 단계 우회.
        saw_passage = passage_above
        added = 0
        j = i + 1
        while j < n and added < 5:
            t_j = (paras[j].get('text', '') or '').strip()
            if not t_j:
                j += 1
                continue
            # 이미 ①~⑤로 시작하면 중단 (어법 객관식이거나 정상 입력된 경우)
            if t_j[0] in _CIRCLED_DIGITS:
                break
            # 다음 발문, 본문 마커([Gateway]/[숫자]), 본문 시작 ※ 만나면 중단
            if _RE_STEP3_QUESTION_LIKE.match(t_j):
                break
            if re.match(r'^\[(?:[Gg]ateway|\d+)\]$', t_j):
                break
            if t_j.startswith('※'):
                break
            # 첫 영문 단락 = 지문 → 1회 skip
            if not saw_passage and re.match(r'^[A-Za-z]', t_j) and not re.search(r'[가-힣]', t_j):
                saw_passage = True
                j += 1
                continue
            mark = _CIRCLED_DIGITS[added]
            paras[j]['text'] = mark + paras[j]['text']
            runs = paras[j].get('runs')
            if isinstance(runs, list):
                runs.insert(0, {'t': mark, 'ul': False})
            added += 1
            j += 1
        i = j if added > 0 else i + 1
    return paras


# Step3 책 헤더 / 묶음 마커 — 출력에서 제거
# - "2027년 수능특강 영어    더변형문제    27강 컴퓨터,인터넷" 류 책 제목 라인
# - "[Gateway]" 묶음 마커 (passage_above 판정에 사용된 후 출력에서 제거)
_RE_STEP3_BOOK_HEADER = re.compile(r'^\d{4}\s*년?\s*수능특강')
_RE_STEP3_GROUP_MARKER = re.compile(r'^\[\s*Gateway\s*\]$', re.I)


def _strip_step3_book_markers(paras):
    """수능특강 책 헤더 + [Gateway] 묶음 마커 단락 제거.

    원고 구조 예:
        2027년 수능특강 영어    더변형문제    27강 컴퓨터,인터넷    ← 책 헤더
        [Gateway]                                                ← 묶음 마커
        <지문 본문>
        1. 발문?
        ...

    [Gateway]는 _add_step3_choice_numbers의 passage_above 판정에 사용된 후
    이 단계에서 제거되어 최종 출력은 바로 발문부터 시작.
    """
    out = []
    for p in paras:
        text = (p.get('text', '') or '').strip()
        if _RE_STEP3_GROUP_MARKER.match(text):
            continue
        if _RE_STEP3_BOOK_HEADER.match(text):
            continue
        out.append(p)
    return out


# (A)/(B) 매칭형 발문 직후의 표 평탄 단락을 5쌍으로 합치기
_RE_STEP3_AB_QUESTION = re.compile(r'\(\s*A\s*\).{0,5}\(\s*B\s*\)')
_RE_STEP3_AB_HEADER = re.compile(r'^\(\s*[AB]\s*\)$')

# 순서배열 발문 — "주어진 글 다음에 이어질 글의 순서로 적절한 것은?"
_RE_STEP3_ORDER_QUESTION = re.compile(r'순서로\s*(?:가장\s*)?적절한|이어질\s*글의\s*순서')


def _fix_step3_order_label_position(paras):
    """순서배열 본문에서 (A) 라벨이 도입부 박스 위로 잘못 추출된 케이스 수정.

    HWP 박스 추출이 박스 구조를 인식 못하면서 첫 (A) 라벨이 시각 순서와 다르게
    도입부 박스 *위*로 추출되는 케이스:

    추출:
        ※ 다음 글을 읽고 물음에 답하시오.
        (A)               ← 잘못된 위치 (도입부 박스 위)
        <도입부 박스>
        <(A) 박스>        ← 라벨 누락된 채 등장
        (B)
        <(B) 박스>
        (C)
        <(C) 박스>
        7. ... 순서로 적절한 것은?

    수정:
        ※ 다음 글을 읽고 물음에 답하시오.
        <도입부 박스>     ← 라벨 없음 (도입부)
        (A)               ← (A) 박스 위로 이동
        <(A) 박스>
        (B)
        ...

    조건 (모두 만족 시에만):
    - (A) 라벨 직전 비빈 단락이 ※/[Gateway]/번호발문
    - 30단락 이내에 (B)/(C) 라벨 + 영문 박스 본문 4개 이상 + 순서배열 발문 모두 존재
    """
    if not paras:
        return paras
    out = list(paras)
    i = 0
    while i < len(out):
        text = (out[i].get('text') or '').strip()
        if text != '(A)':
            i += 1
            continue
        # 직전 비빈 단락이 발문/Gateway/※ 인지
        prev_marker = False
        for jj in range(i - 1, -1, -1):
            pt = (out[jj].get('text') or '').strip()
            if not pt:
                continue
            if pt.startswith('※') or pt == '[Gateway]' or _RE_STEP3_QUESTION_LIKE.match(pt):
                prev_marker = True
            break
        if not prev_marker:
            i += 1
            continue
        # 후속 30단락 이내: (B)/(C) 라벨 + 영문 본문 4개 이상 + 순서배열 발문
        scan_end = min(len(out), i + 30)
        b_idx = c_idx = first_body_idx = -1
        body_count = 0
        order_q_found = False
        for k in range(i + 1, scan_end):
            tk = (out[k].get('text') or '').strip()
            if not tk:
                continue
            if tk == '(B)' and b_idx < 0:
                b_idx = k
                continue
            if tk == '(C)' and c_idx < 0:
                c_idx = k
                continue
            if _RE_STEP3_ORDER_QUESTION.search(tk):
                order_q_found = True
                break
            if re.match(r'^[A-Za-z]', tk) and not re.search(r'[가-힣]', tk):
                body_count += 1
                if first_body_idx < 0:
                    first_body_idx = k
        if not (order_q_found and b_idx > 0 and c_idx > 0 and body_count >= 4 and first_body_idx > 0):
            i += 1
            continue
        # (A) 라벨을 첫 박스 본문 *다음* 위치로 이동
        a_para = out.pop(i)
        # pop으로 first_body_idx는 1 감소 → 새 인덱스 (first_body_idx - 1)이 도입부 박스 위치
        # 그 *다음*에 (A) 삽입 → insert(first_body_idx)
        out.insert(first_body_idx, a_para)
        i = first_body_idx + 1
    return out


def _merge_step3_ab_pairs(paras):
    """(A)/(B) 매칭 발문 직후의 표 평탄 단락을 5쌍으로 합쳐 ①~⑤ 부여.

    hwp/hwpx 표는 셀 단위로 평탄화되어 추출됨:
        입력:
            10. 윗글의 ... (A), (B)에 들어갈 연결사로 바른 것은?
            (A)                ← 컬럼 헤더 (제거)
            (B)                ← 컬럼 헤더 (제거)
            However            ← 1쌍 (A)값
            As a result        ← 1쌍 (B)값
            However
            Otherwise
            ...
            Therefore
            What is worse
        출력:
            10. ... 바른 것은?
            ①However\\tAs a result
            ②However\\tOtherwise
            ③For example\\tLikewise
            ④For example\\tNevertheless
            ⑤Therefore\\tWhat is worse

    영문 단락이 정확히 10개 모이지 않으면(추출 누락 등) 안전하게 원본 그대로 반환.
    """
    out = []
    i = 0
    n = len(paras)
    while i < n:
        text = (paras[i].get('text', '') or '').strip()
        # 5지선다 발문("…것은?")이고 (A)/(B) 매칭 패턴 포함 + NON_CHOICE(쓰시오/요약/영작/어법) 아닐 때만 처리.
        # 빈칸 채우기 서술형 발문에는 적용하면 안 됨 (그 발문에도 (A)/(B) 라벨이 등장하지만
        # 표 매칭이 아니라 본문 안 빈칸 표시이므로).
        is_match = (_RE_STEP3_CHOICE_QUESTION.match(text)
                    and _RE_STEP3_AB_QUESTION.search(text)
                    and not _RE_STEP3_NON_CHOICE.search(text))
        if not is_match:
            out.append(paras[i])
            i += 1
            continue
        # (A)/(B) 매칭 5지선다 발문 — 발문 단락은 그대로 유지
        out.append(paras[i])
        i += 1
        # 후속 단락 수집: 빈 줄/(A)·(B) 헤더는 따로 보관, 영문 셀만 cells에 모음
        cells = []
        passed = []  # 매칭 실패 시 복원용 (빈 줄 + (A)/(B) 헤더)
        while i < n and len(cells) < 10:
            tj = (paras[i].get('text', '') or '').strip()
            if not tj:
                passed.append(paras[i])
                i += 1
                continue
            if _RE_STEP3_AB_HEADER.match(tj):
                # (A) 또는 (B) 단독 헤더 — 5쌍 매칭 성공 시 제거, 실패 시 복원
                passed.append(paras[i])
                i += 1
                continue
            if _RE_STEP3_QUESTION_LIKE.match(tj):
                break  # 다음 발문 만나면 중단
            cells.append(paras[i])
            i += 1
        if len(cells) < 10:
            # 매칭 실패 — (A)/(B) 헤더 + 빈 줄 + cells 모두 복원
            out.extend(passed)
            out.extend(cells)
            continue
        # 5쌍 합치기: ① + (A)값 + 탭 + (B)값
        for k in range(5):
            t1 = (cells[2 * k].get('text') or '').rstrip()
            t2 = (cells[2 * k + 1].get('text') or '').rstrip()
            mark = _CIRCLED_DIGITS[k]
            merged_text = mark + t1 + '\t' + t2
            runs_a = cells[2 * k].get('runs') or [{"t": t1, "ul": False}]
            runs_b = cells[2 * k + 1].get('runs') or [{"t": t2, "ul": False}]
            new_runs = [{"t": mark, "ul": False}]
            new_runs.extend(runs_a)
            new_runs.append({"t": "\t", "ul": False})
            new_runs.extend(runs_b)
            out.append({"text": merged_text, "runs": new_runs})
    return out


def _parse_step3_folder(step3_dir, grade, year, month, normal_questions,
                        short_questions, combined_questions, extract_underline=True,
                        step3_exclude_footnotes=True):
    """
    Step3 폴더 → 지문별 단락 목록.
    파일명: "고1 25년 9월 20번.hwp" 형태.
    반환: {"normal": [...], "short": [...]}
    각 항목: {"question_num": "20", "code": "250920", "paragraphs": [...]}

    step3_exclude_footnotes: True(기본) → level 1만 (정답/해설 footnote 완전 제거).
                             False → footnote_l3_set만 제외하고 level 3 (표 셀 본문 등) 유지.
                             수능특강 21강+처럼 표 셀에 본문이 있는 케이스에 False 사용.
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
            paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                            exclude_footnotes=step3_exclude_footnotes)
        # Step3 정답/해설 줄 제거 (level 3 제외 후에도 level 1에 남은 정답 줄 처리)
        paras = _strip_step3_answers(paras)
        # Step3 유형 섹션 태그 제거 ("[유형 1] ...", "(심경, 분위기, ...)")
        paras = _strip_step3_type_tags(paras)
        # 5지선다 자동번호(①②③④⑤) 텍스트화 — hwp AutoNumbering 누락 보완
        paras = _add_step3_choice_numbers(paras)
        # 책 헤더("2027년 수능특강 ...") + [Gateway] 묶음 마커 제거
        # ※ _add_step3_choice_numbers의 passage_above 판정이 [Gateway]를 참조하므로
        #   반드시 그 호출 *후*에 실행해야 함
        paras = _strip_step3_book_markers(paras)
        # 순서배열 본문: (A) 라벨이 도입부 박스 위로 잘못 추출된 경우 정규화
        paras = _fix_step3_order_label_position(paras)
        # (A)/(B) 매칭 발문 → 표 5쌍 합치기 (①단어A\t단어B 형식)
        paras = _merge_step3_ab_pairs(paras)
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
        # 후보 파일 수집
        candidate_files = []
        for fname_raw in sorted(os.listdir(step3_dir)):
            fname = _nfc(fname_raw)
            if not fname.endswith('.hwp') and not fname.endswith('.hwpx') and not fname.endswith('.docx'):
                continue
            if re.search(r'\d+번\.(?:hwpx?|docx)', fname, re.I):
                continue  # 이미 위에서 처리 대상이었던 파일
            if fname_raw.startswith('.'):
                continue
            candidate_files.append(fname_raw)
        # MIXED 파일이 있으면 그것만 사용 (통합본 우선)
        mixed_files = [f for f in candidate_files if 'MIXED' in _nfc(f).upper()]
        if mixed_files:
            candidate_files = mixed_files

        textbook_paras = []
        for fname_raw in candidate_files:
            fpath = os.path.join(step3_dir, fname_raw)
            if fpath.lower().endswith('.docx'):
                paras = _docx_extract_paragraphs(fpath, extract_underline)
            else:
                paras = _hwp_extract_paragraphs(fpath, extract_underline,
                                                exclude_footnotes=step3_exclude_footnotes)
            paras = _strip_step3_answers(paras)
            paras = _strip_step3_type_tags(paras)
            paras = _add_step3_choice_numbers(paras)
            paras = _strip_step3_book_markers(paras)
            paras = _fix_step3_order_label_position(paras)
            paras = _merge_step3_ab_pairs(paras)
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

    매칭 전략 — 파일명의 구조(의미 토큰)를 기준으로 비교:
    1. 정규화: 영문/숫자/한글만 남기고 공백·괄호·특수문자 모두 제거, 소문자, NFC
       (예: 'Step2 A1 어법선택(객관식).docx' → 'step2a1어법선택객관식')
    2. 정확 매칭 우선
    3. 한쪽 정규화 문자열이 다른 쪽의 subsequence면 부분 매칭으로 인정
       (예: '어법객관식'은 '어법선택객관식'의 subsequence → 매칭)
    4. 부분 매칭 후보들은 LCS(공통 부분 수열) 길이가 긴 것 우선
       (예: 기대 '빈칸어법정답지' → 후보 '빈칸어법정답'(LCS=9) > '빈칸어법'(LCS=7))
    5. 동일 LCS면 확장자 일치 우선
    """
    import unicodedata
    import re

    def _normalize(name):
        nfc = unicodedata.normalize("NFC", name)
        base = os.path.splitext(nfc)[0]
        cleaned = re.sub(r'[^A-Za-z0-9가-힣]', '', base).lower()
        return cleaned

    def _is_subseq(short, long_):
        if not short:
            return True
        i = 0
        slen = len(short)
        for ch in long_:
            if short[i] == ch:
                i += 1
                if i == slen:
                    return True
        return False

    def _lcs_len(a, b):
        if not a or not b:
            return 0
        la, lb = len(a), len(b)
        if la > lb:
            a, b = b, a
            la, lb = lb, la
        prev = [0] * (la + 1)
        for j in range(1, lb + 1):
            curr = [0] * (la + 1)
            bj = b[j-1]
            for i in range(1, la + 1):
                if a[i-1] == bj:
                    curr[i] = prev[i-1] + 1
                else:
                    curr[i] = max(prev[i], curr[i-1])
            prev = curr
        return prev[la]

    ext_expected = os.path.splitext(expected_filename)[1].lower()
    norm_expected = _normalize(expected_filename)

    exact = []
    partial = []  # (file_path, lcs_score)
    for f in os.listdir(manuscript_dir):
        fp = os.path.join(manuscript_dir, f)
        if not os.path.isfile(fp):
            continue
        f_ext = os.path.splitext(f)[1].lower()
        if f_ext not in ('.docx', '.hwp', '.hwpx'):
            continue
        f_norm = _normalize(f)
        if not f_norm:
            continue
        if f_norm == norm_expected:
            exact.append(fp)
        elif _is_subseq(f_norm, norm_expected) or _is_subseq(norm_expected, f_norm):
            partial.append((fp, _lcs_len(f_norm, norm_expected)))

    if exact:
        for c in exact:
            if os.path.splitext(c)[1].lower() == ext_expected:
                return c
        return exact[0]
    if partial:
        partial.sort(key=lambda x: (
            -x[1],
            0 if os.path.splitext(x[0])[1].lower() == ext_expected else 1,
        ))
        for fp, _ in partial:
            if os.path.splitext(fp)[1].lower() == ext_expected:
                return fp
        return partial[0][0]
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

        # 옛 형식 워크북 헤더("9번"/"17년 11월 21번") → 표준 형식으로 정규화
        # 정상 원고에는 매치되지 않으므로 안전
        paras = _normalize_old_workbook_headers(paras)
        # 옛 헤더 변환 후 본문에 끼어있는 잡 헤더 제거
        paras = _strip_secondary_headers_after_old(paras)
        # 챕터 구분선 제거 (EBS 리딩파워 등). 다른 원고에는 매치되지 않음
        paras = _strip_chapter_dividers(paras)
        # 본 보기 다음 주어진 문장에 양쪽 공백 둘러싸기 (정상 원고 형태 매칭)
        paras = _wrap_hadan_with_spaces(paras)

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
            step3_exclude_footnotes=config.get('step3_exclude_footnotes', True),
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
