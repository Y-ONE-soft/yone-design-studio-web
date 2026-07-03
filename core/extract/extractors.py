"""공용 원고 추출 계층 (Phase 1) — 파일 포맷 → 단락/밑줄 raw 추출.

engines/workbook/parser.py의 추출 블록(pre-overhaul 32~606줄)을 **그대로 이동**한
것이다 (동작 변화 0 — tests/ 스냅샷으로 보증). 구조 인식/발문 분류는 이 계층의
책임이 아니다 (Phase 2, core/structure/).

단락 데이터 구조: {"text": str, "runs": [{"t": str, "ul": bool}]}

지원 포맷:
  - docx: zipfile + XML 직접 파싱 (_docx_extract_paragraphs)
  - hwpx: ZIP + section/header XML, 다중 섹션, 표-고아 텍스트 복구
  - hwp:  HWP5 바이너리 (pyhwp + struct), 각주/미주 정밀 제거, 밑줄 charshape

이름 규칙: 기존 사용처(workbook/mockexam/workbook_sero 파서)가 밑줄 이름을
import하므로 정의 이름을 유지한다. 신규 코드는 core.extract의 공개 별칭을 쓸 것.
"""

import html
import os
import re
import struct
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

    paragraph 내부의 <w:br/> (soft return, Shift+Enter)는 paragraph break로
    승격: 한 paragraph 안에 br이 있으면 그 위치에서 paragraph를 분할.
    원고에 줄바꿈 의도가 있는 부분이 본문/요약/추가문장으로 합쳐지는 사고 방지.
    """
    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read('word/document.xml')

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_content)

    _T_TAG = f'{{{_NS_W}}}t'
    _BR_TAG = f'{{{_NS_W}}}br'

    def _flush(paragraphs, runs):
        full_text = ''.join(r['t'] for r in runs)
        paragraphs.append({
            "text": full_text,
            "runs": runs if runs else [{"t": "", "ul": False}],
        })

    paragraphs = []
    for p_elem in root.iter(f'{{{_NS_W}}}p'):
        runs = []
        for r_elem in p_elem.iter(f'{{{_NS_W}}}r'):
            # 각주/미주 참조 마커가 포함된 run 스킵
            if (r_elem.find(f'{{{_NS_W}}}footnoteReference') is not None or
                    r_elem.find(f'{{{_NS_W}}}endnoteReference') is not None):
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

            # run 내부 직계 children을 순서대로: w:t는 텍스트, w:br은 paragraph 분할
            buf = []
            for child in r_elem:
                tag = child.tag
                if tag == _T_TAG:
                    if child.text:
                        buf.append(child.text)
                elif tag == _BR_TAG:
                    # br 직전까지의 텍스트를 현재 run으로, 그 후 paragraph 분할
                    if buf:
                        runs.append({"t": ''.join(buf), "ul": is_ul})
                        buf = []
                    _flush(paragraphs, runs)
                    runs = []
            if buf:
                runs.append({"t": ''.join(buf), "ul": is_ul})

        _flush(paragraphs, runs)

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
        # HWPX 본문도 여러 섹션(section0.xml/section1.xml/…)으로 나뉠 수 있다.
        # 첫 섹션만 읽으면 두 번째 섹션 이후 단락이 통째로 누락된다(.hwp와 동일 버그).
        # 모든 section XML을 번호 순으로 모아 각각 처리한다.
        section_names = sorted(
            (n for n in names if re.search(r'section\d+\.xml', n, re.I)),
            key=lambda n: int(re.search(r'section(\d+)\.xml', n, re.I).group(1)),
        )
        if not section_names:
            raise ValueError(f"section XML을 찾을 수 없음: {hwpx_path}")
        section_xmls = [zf.read(n).decode('utf-8') for n in section_names]

        header_name = next(
            (n for n in names if re.search(r'header\.xml', n, re.I)), None
        )
        header_xml = zf.read(header_name).decode('utf-8') if header_name else ''

    ul_ids = _parse_underline_ids(header_xml) if (extract_underline and header_xml) else set()

    paragraphs = []

    def _emit(segments):
        """세그먼트 목록을 new_para 경계로 분할해 paragraphs에 append."""
        cur_runs = []

        def flush():
            text = ''.join(r['t'] for r in cur_runs)
            paragraphs.append({
                "text": text,
                "runs": [r for r in cur_runs if r['t']] or [{"t": "", "ul": False}],
            })

        for seg in segments:
            if seg['new_para']:
                flush()
                cur_runs = []
            cur_runs.append({"t": seg["t"], "ul": seg["ul"]})

        if cur_runs:
            flush()

    # <hp:p>(.*?)</hp:p> 비탐욕 매치는 표 셀의 중첩 </hp:p>에서 끊겨, 표(<hp:tbl>)
    # *뒤*에 같은 바깥 단락 안에 이어지는 본문(예: 문장삽입 지문)이 매치 사이 gap에
    # 고아로 남아 누락된다. 매치 직전 gap에서 마지막 </hp:tbl> 이후 텍스트를 복구한다.
    def _recover_post_table_text(chunk):
        tbl_close = chunk.rfind('</hp:tbl>')
        if tbl_close == -1:
            return
        orphan = chunk[tbl_close + len('</hp:tbl>'):]
        orphan_segs = _hwpx_extract_segments(orphan, ul_ids)
        if not any(s['t'].strip() for s in orphan_segs):
            # 표를 감싼 run이 표와 뒤따르는 본문을 함께 담는 경우, run 시작 태그가
            # 표 앞(이전 매치)에서 잘려 <hp:t>가 run 래퍼 없이 남는다 → 직접 추출.
            orphan_segs = []
            for t_m in re.finditer(r'<hp:t\b[^>]*>(.*?)</hp:t>', orphan, re.DOTALL):
                raw = re.sub(r'<hp:tab\b[^/]*/>', '\t', t_m.group(1))
                for j, part in enumerate(re.split(r'<hp:lineBreak\s*/>', raw)):
                    orphan_segs.append({
                        "t": html.unescape(re.sub(r'<[^>]+>', '', part)),
                        "ul": False, "new_para": j > 0,
                    })
        if any(s['t'].strip() for s in orphan_segs):
            _emit(orphan_segs)

    for section_xml in section_xmls:
        # 미주/각주 제거 (hwpx 실제 태그명: hp:endNote, hp:footNote — 대문자 N)
        section_xml = re.sub(r'<hp:endNote\b.*?</hp:endNote>', '', section_xml, flags=re.DOTALL)
        section_xml = re.sub(r'<hp:footNote\b.*?</hp:footNote>', '', section_xml, flags=re.DOTALL)

        prev_end = 0
        for m in re.finditer(r'<hp:p\b([^>]*)>(.*?)</hp:p>', section_xml, re.DOTALL):
            _recover_post_table_text(section_xml[prev_end:m.start()])
            _emit(_hwpx_extract_segments(m.group(2), ul_ids))
            prev_end = m.end()
        # 마지막 매치 이후 trailing 표-고아 텍스트도 복구
        _recover_post_table_text(section_xml[prev_end:])

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


# 모의고사 워크북 신형식 출처 표기: "┃10월 18번┃", "┃10월 43~45번┃"
_RE_SRC_BAR = re.compile(r'┃[^┃]*?월\s*\d+(?:\s*~\s*\d+)?\s*번[^┃]*?┃')


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
    # HWP 본문은 여러 BodyText 섹션(Section0/1/2…)으로 나뉠 수 있다.
    # section(0)만 읽으면 두 번째 섹션 이후 단락이 통째로 누락된다.
    #   예) "스텝3 실전문제.hwp"는 54문제가 3개 섹션(4/50/0)에 흩어져 있어
    #       Section0의 4문제만 추출되고 나머지 50문제가 조용히 사라졌다.
    # 모든 섹션의 레코드를 문서 순서대로 이어붙인다. CHAR_SHAPE(ul_map)는
    # DocInfo 전역이라 섹션을 합쳐도 밑줄 매핑이 그대로 유효하다.
    try:
        n_sections = len(hwp.bodytext.sections)
    except Exception:
        n_sections = 1
    all_recs = []
    for _si in range(n_sections):
        all_recs.extend(list(hwp.bodytext.section(_si).records()))

    # ── 모의고사 워크북 신형식 감지 ──────────────────────────────────────
    # 한 지문을 여러 유형(어법/어휘/빈칸/순서/영작…)으로 변형하는 형식으로,
    # 출처(┃…월 N번┃)·정답·해설·영작 모범답안을 전부 level 3에, 보기 박스를
    # level 5에 둔다. → 이 형식에선 level 3 = 버릴 것(살릴 본문 없음),
    #   level 5 = 살려야 할 보기. _new_format True일 때 아래 루프에서 정책을 반전.
    # 기존 워크북(수능특강·EBS 등)에는 이 두 신호가 없어 기존 동작을 유지한다.
    _new_format = False
    for _r in all_recs:
        if _r.get('tagid') != 67:
            continue
        _lv = _r.get('level', 1)
        if _lv not in (3, 5):
            continue
        try:
            _t = _hwp_decode_paratext(_r.get('payload', b'')).strip()
        except Exception:
            continue
        if _lv == 3 and _RE_SRC_BAR.search(_t):
            _new_format = True
            break
        if _lv == 5 and _t == '보기':
            _new_format = True
            break

    # HWP5 구조:
    # level 1 = 본문 단락
    # level 3 = 미주/각주 또는 문제 내용(표, 선지 등)
    #
    # exclude_footnotes=True (Step3 등):
    #   level 3 전부 제외 — Step3에서는 모든 level 3이 각주/미주(정답+해설)
    # exclude_footnotes=False (Step1/Step2 등):
    #   level 3 중 CTRL 11/12로 감지되는 FOOTNOTE 블록만 제외, 나머지 포함

    # Pass 1: FOOTNOTE 블록의 level 3 레코드 인덱스 수집.
    # ※ 양 모드(Step1/2의 exclude_footnotes=False, Step3의 True) 공통으로 실행한다.
    #   level 3에는 각주/미주뿐 아니라 표·선지 같은 "문제 내용"도 들어있으므로(주석 448행),
    #   CTRL 17/18로 도입된 진짜 각주/미주 level-3만 골라낸다. (예전 Step3의 "non-level-1
    #   전부 삭제"는 요약 (A)(B)표·선지표까지 날려 원고 내용이 소리 없이 손실됐다.)
    footnote_l3_set = set()
    if all_recs:
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
        # level 1(본문 단락): 항상 포함.
        # level 3 중 각주/미주(footnote_l3_set)가 아닌 표·선지 등 문제 내용: 포함.
        # 그 외(각주/미주 level-3, 기타 레벨): 제외.
        # ※ exclude_footnotes True/False 동일 동작 — 진짜 각주/미주만 정밀 제거하고
        #   문제 내용(표·선지)은 보존한다. (param은 hwpx 경로 시그니처 호환용으로 유지)
        if rec_level == 1:
            pass
        elif _new_format:
            # 신형식: level 5(보기 박스)만 살리고, level 3(출처/정답/해설/영작
            #   모범답안) 등 나머지는 모두 제외한다.
            if rec_level == 5:
                pass
            else:
                i += 1
                continue
        elif rec_level == 3 and i not in footnote_l3_set:
            pass
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
