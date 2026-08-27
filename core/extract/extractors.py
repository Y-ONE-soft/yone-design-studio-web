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
import logging
import os
import re
import struct
import unicodedata
import zipfile
import zlib

_LOG = logging.getLogger(__name__)

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
            elif code == 9:
                # 탭(인라인 제어, 8워드) — 문자로 보존 (W12: 표형 선지
                # "① is\tbe done\tit"의 셀 구분자가 통째로 사라져
                # "isbe doneit"로 병합되던 유실 수리)
                result.append('\t')
                i += 16
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


def _hwp_build_charshape_red(hwp):
    """DocInfo CHAR_SHAPE(tagid=21)에서 빨간 글자색 여부 맵 생성 (W51).

    CharShape offset 52-55: COLORREF textColor (0x00BBGGRR).
    순빨강(0x0000FF)만 정답 마킹으로 본다 — 인라인 정답형 원고(아잉카
    변형문제)가 정답/해설 표기를 빨간 글자로 구분하는 관행 실측."""
    red_map = {}
    idx = 0
    for rec in hwp.docinfo.records():
        if rec.get('tagid') != 21:
            continue
        payload = rec.get('payload', b'')
        is_red = False
        if len(payload) >= 56:
            color = struct.unpack_from('<I', payload, 52)[0]
            is_red = (color == 0x0000FF)
        red_map[idx] = is_red
        idx += 1
    return red_map


# 발문(question) 종결 시그니처 — 인라인 정답 표의 선행 라인 판정 (W51).
# "…고르시오." "…쓰시오." "…배열하시오." + 한글 의문 종결("…것은?",
# "…문장은?", "…적절한 곳은?" — W53: '것은?' 리터럴만 보다가 2강
# 무관문장 발문 '…관계 없는 문장은?'을 놓쳐 정답 표가 통과했다.
# 영어 문장의 '?'는 한글 직전 문자 조건으로 배제).
# 꼬리 괄호 주석 허용: "…고치시오. (틀린 부분 3개)" (0645d4a7 실측 —
# 이 꼬리 때문에 어법수정 6문항의 빨간 정답 전문이 판정을 비껴갔다).
_RE_Q_TAIL = re.compile(
    r'(?:시오\s*[.?]?|[가-힣]\s*\?)\s*(?:\([^()]{0,30}\)\s*)?$')


def _strip_inline_answer_tables(paragraphs, metas):
    """발문 직후 인라인 정답 표(level>=2) 제거 (W51 — 구조 기반).

    아잉카류 변형문제 원고는 문항 발문 '바로 다음'에 정답 표를 인라인으로
    둔다 (객관식=정답 선지+[해설], 배열/영작=정답 문장 단일 셀, 어법=빨간
    마킹 정답 전문, 어휘=단어 정답). 기존 파이프라인은 이 표들이 level 3
    (각주 아님)이라 보존했고, '한국어 없는 긴 영문 표 셀 = 본문' 보호
    휴리스틱까지 겹쳐 정답이 대량 인쇄됐다 (2026-08-11 job 0645d4a7 실증).

    형식 감지(문서 단위): 발문-직후 level>=2 표 그룹 중 빨간 글자 또는
    '[해설]' 텍스트를 품은 그룹이 2개 이상이면 인라인 정답형으로 판정,
    **발문-직후 그룹 전부**를 제거한다 (증거 없는 그룹 = 배열/영작 정답
    문장도 같은 위치 규칙의 정답이다). 발문-직후가 아닌 표(답란
    '틀린 부분/수정', 책 표지)는 보존. 감지 미달 문서는 무변경."""
    n = len(paragraphs)
    if n != len(metas):
        return paragraphs
    # 연속 level>=2 그룹 수집
    groups = []          # [(start, end_exclusive)]
    i = 0
    while i < n:
        if metas[i]["lv"] >= 2:
            j = i
            while j < n and metas[j]["lv"] >= 2:
                j += 1
            groups.append((i, j))
            i = j
        else:
            i += 1
    q_adjacent = []
    evidence = 0
    for (a, b) in groups:
        # 선행 비빈 level-1 라인
        k = a - 1
        while k >= 0 and (metas[k]["lv"] >= 2
                          or not (paragraphs[k].get("text") or "").strip()):
            if metas[k]["lv"] >= 2:
                break
            k -= 1
        if k < 0 or metas[k]["lv"] >= 2:
            continue
        prev = (paragraphs[k].get("text") or "").strip()
        if not _RE_Q_TAIL.search(prev):
            continue
        q_adjacent.append((a, b))
        has_red = any(metas[x].get("red") for x in range(a, b))
        has_expl = any("[해설]" in (paragraphs[x].get("text") or "")
                       for x in range(a, b))
        if has_red or has_expl:
            evidence += 1
    if evidence < 2:
        return paragraphs
    drop = set()
    for (a, b) in q_adjacent:
        drop.update(range(a, b))
    return [p for x, p in enumerate(paragraphs) if x not in drop]


def _hwp_text_with_underline(para_text_payload, charshape_pairs, ul_map):
    """PARA_TEXT payload를 디코딩하면서 charshape 기반 밑줄 run 생성."""
    # 원본 위치별 밑줄 여부 매핑
    # charshape_pairs: [(pos, csid), ...] — pos는 원본 payload 내 문자 인덱스
    #
    # (W13 성능) 예전 구현은 {위치: bool} dict를 pair마다 range(start, end)로
    # 채웠는데, 마지막 pair의 end가 999999라 단락마다 ~100만 엔트리를 만들어
    # 밑줄 추출이 단락당 ~37ms → Step3 hwp 파일당 4~5초 (25파일 원고에서
    # 파서가 행처럼 보이는 침묵 지연, W13 c05 실증). 아래 _PosUl은 같은
    # 의미론('나중 pair 쓰기가 이김' + 미커버 위치는 default)을 구간 역순
    # 스캔으로 대체한다 — 골든 스냅샷 byte-identical 검증됨.
    class _PosUl(object):
        __slots__ = ()

        @staticmethod
        def get(pos, default):
            for k in range(len(charshape_pairs) - 1, -1, -1):
                s = charshape_pairs[k][0]
                e = (charshape_pairs[k + 1][0]
                     if k + 1 < len(charshape_pairs) else 999999)
                if s <= pos < e:
                    return ul_map.get(charshape_pairs[k][1], False)
            return default

    pos_ul = _PosUl()

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
            elif code == 9:
                # 탭(인라인 제어, 8워드) — 문자로 보존 (W12,
                # _hwp_decode_paratext와 동일). 비밑줄 취급.
                ul = pos_ul.get(char_idx, cur_ul)
                if ul != cur_ul and cur_text:
                    runs.append({"t": cur_text, "ul": cur_ul})
                    cur_text = ""
                    cur_ul = ul
                cur_text += '\t'
                char_idx += 8
                i += 16
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


# ── hwp 그림(도표/그래프) 추출 ─────────────────────────────────────────────
# 사용자 지적 2026-08-27 (부교재 워크북 v2 / 올림포스 영어독해 6강):
# "원고에 있는 도표 이미지도 조판이 됐으면 좋겠어."
# HWP5는 그림을 본문 단락의 GSO 컨트롤(제어문자 11)로 걸고, 실제 비트맵은
# OLE 저장소 BinData/BIN####.ext 스트림에 (FileHeader flags&1 이면 raw
# deflate 로 압축돼) 들어 있다. 텍스트만 뽑는 기존 경로는 GSO 제어문자를
# 16바이트 건너뛰고, 그림만 있는 단락은 text=="" 라 통째로 버려졌다.
#
# 여기서는 **레코드 순서 그대로** 그림을 단락에 붙인다 (앵커 단락 = 그림
# 직전의 PARA_TEXT). 머리말/꼬리말/각주에 걸린 로고·워터마크는 앵커 단락의
# level 이 1 이 아니므로 자연히 빠진다 (본문 단락만 level 1).
_HWPUNIT_MM = 25.4 / 7200.0
_HWP_PIC_TAG = 'HWPTAG_SHAPE_COMPONENT_PICTURE'


def _hwp_bindata_storage_names(hwp):
    """DocInfo BIN_DATA → {storage_id: 'BIN0001.bmp'} (id는 그림이 참조하는 값)."""
    names = {}
    try:
        models = list(hwp.docinfo.models())
    except Exception as e:                                     # noqa: BLE001
        _LOG.warning("[추출] BinData 목록 파싱 실패 — 그림 추출 생략: %s", e)
        return names
    for m in models:
        if m.get('tagname') != 'HWPTAG_BIN_DATA':
            continue
        bd = (m.get('content') or {}).get('bindata') or {}
        sid, ext = bd.get('storage_id'), bd.get('ext')
        if sid is None or not ext:
            continue           # 링크형(외부 파일 참조) BinData — 내장 그림 아님
        names[int(sid)] = 'BIN%04X.%s' % (int(sid), ext)
    return names


def _hwp_read_bindata(hwp_path, storage_name):
    """BinData 스트림 1개를 읽어 (필요하면 inflate 해) 원본 바이트로 반환."""
    import olefile
    ole = olefile.OleFileIO(hwp_path)
    try:
        try:
            flags = struct.unpack_from('<I', ole.openstream('FileHeader').read(), 36)[0]
        except Exception:                                      # noqa: BLE001
            flags = 1
        raw = ole.openstream('BinData/' + storage_name).read()
    finally:
        try:
            ole.close()
        except Exception:                                      # noqa: BLE001
            pass
    if flags & 1:
        try:
            return zlib.decompress(raw, -15)
        except zlib.error:
            return raw          # 비압축으로 저장된 스트림 (혼재 가능)
    return raw


def _hwp_export_picture(hwp_path, storage_name, out_dir, stem, bid):
    """BinData 그림 1개를 out_dir에 파일로 쓰고 (경로, 폭px, 높이px) 반환.

    BMP/TIFF 등 인디자인 링크로 무거운 포맷은 PNG로 변환한다 (원고 도표는
    3.6MB BMP 로 들어오기도 한다 — 링크 파일이 그대로 납품 폴더에 남는다).
    변환 실패 시 원본 확장자 그대로 저장 (침묵 유실 금지)."""
    data = _hwp_read_bindata(hwp_path, storage_name)
    ext = os.path.splitext(storage_name)[1].lower().lstrip('.')
    px = (0, 0)
    if ext in ('bmp', 'tif', 'tiff', 'wmf', 'emf', 'gif'):
        try:
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(data))
            px = im.size
            if im.mode not in ('RGB', 'RGBA', 'L'):
                im = im.convert('RGB')
            out = os.path.join(out_dir, '%s_img%d.png' % (stem, bid))
            im.save(out, 'PNG', optimize=True)
            return out, px[0], px[1]
        except Exception as e:                                 # noqa: BLE001
            _LOG.warning("[추출] 그림 PNG 변환 실패(%s) — 원본 확장자로 저장: %s",
                         storage_name, e)
    out = os.path.join(out_dir, '%s_img%d.%s' % (stem, bid, ext or 'bin'))
    with open(out, 'wb') as f:
        f.write(data)
    try:
        import io
        from PIL import Image
        px = Image.open(io.BytesIO(data)).size
    except Exception:                                          # noqa: BLE001
        px = (0, 0)
    return out, px[0], px[1]


def _hwp_collect_pictures(hwp_path, all_models, image_dir):
    """레코드 목록에서 그림을 모아 {앵커 레코드 index: [image dict]} 반환.

    image dict = {"path", "w_mm", "h_mm", "bindata_id"} — w/h 는 원고에
    **표시된** 크기(mm). 조판은 이 값을 단 폭 상한과 함께 쓴다."""
    found = []          # (anchor_rec_index, bindata_id, w_mm, h_mm)
    last_para = None
    for ri, rec in enumerate(all_models):
        if rec.get('tagid') == 67:                 # PARA_TEXT
            last_para = ri
            continue
        if rec.get('tagname') != _HWP_PIC_TAG or last_para is None:
            continue
        if all_models[last_para].get('level', 1) != 1:
            continue                                # 머리말/꼬리말/각주 그림
        content = rec.get('content') or {}
        bid = ((content.get('picture') or {}).get('bindata_id'))
        if bid is None:
            continue
        # 표시 크기 — 직전 SHAPE_COMPONENT 의 width/height (HWPUNIT)
        w_mm = h_mm = 0.0
        for rj in range(ri - 1, max(-1, ri - 4), -1):
            if all_models[rj].get('tagname') == 'HWPTAG_SHAPE_COMPONENT':
                sc = all_models[rj].get('content') or {}
                w_mm = float(sc.get('width') or 0) * _HWPUNIT_MM
                h_mm = float(sc.get('height') or 0) * _HWPUNIT_MM
                break
        found.append((last_para, int(bid), w_mm, h_mm))
    if not found:
        return {}

    try:
        from hwp5.xmlmodel import Hwp5File
        names = _hwp_bindata_storage_names(Hwp5File(hwp_path))
    except Exception as e:                                     # noqa: BLE001
        _LOG.warning("[추출] 그림 저장소 이름 확인 실패 — 그림 생략: %s", e)
        return {}

    os.makedirs(image_dir, exist_ok=True)
    stem = re.sub(r'[^0-9A-Za-z가-힣]+', '_',
                  os.path.splitext(os.path.basename(hwp_path))[0])[:60]
    cache, out = {}, {}
    for anchor, bid, w_mm, h_mm in found:
        if bid not in cache:
            sname = names.get(bid)
            if not sname:
                _LOG.warning("[추출] 그림 BinData 없음(id=%s, %s) — 누락",
                             bid, os.path.basename(hwp_path))
                cache[bid] = None
            else:
                try:
                    cache[bid] = _hwp_export_picture(
                        hwp_path, sname, image_dir, stem, bid)
                except Exception as e:                         # noqa: BLE001
                    _LOG.warning("[추출] 그림 추출 실패(%s, %s) — 누락: %s",
                                 sname, os.path.basename(hwp_path), e)
                    cache[bid] = None
        info = cache[bid]
        if not info:
            continue
        path, wpx, hpx = info
        out.setdefault(anchor, []).append({
            "path": path, "bindata_id": bid,
            "w_mm": round(w_mm, 2), "h_mm": round(h_mm, 2),
            "w_px": wpx, "h_px": hpx,
        })
    return out


def _hwp_extract_paragraphs(hwp_path, extract_underline=False, exclude_footnotes=False,
                            strip_inline_answers=False, image_dir=None):
    """
    hwp 파일 파싱. hwpx(ZIP)이면 hwpx 파서 사용, 아니면 pyhwp + struct 디코딩.
    밑줄 추출: CHAR_SHAPE + PARA_CHAR_SHAPE 레코드 활용.
    exclude_footnotes: True면 level 3 레코드를 전부 제외 (Step3용 — 각주/미주 완전 제거).
    strip_inline_answers: True면 발문 직후 인라인 정답 표(level>=2, 빨간
        마킹/[해설] 증거 2개+ 문서에 한정)를 제거 (W51 — Step3 전용.
        hwpx 경로는 해당 형식 실측 전이라 미적용).
    image_dir: 지정하면 본문 그림(도표/그래프)을 이 폴더로 뽑아
        {"text": "", "runs": [], "image": {...}} 단락으로 원위치에 끼운다.
        None(기본)이면 그림 처리를 아예 하지 않는다 — 기존 호출부 무영향.
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
    red_map = _hwp_build_charshape_red(hwp) if strip_inline_answers else {}
    metas = []   # W51: 단락별 (lv, red) — 인라인 정답 표 제거 판정용
    # HWP 본문은 여러 BodyText 섹션(Section0/1/2…)으로 나뉠 수 있다.
    # section(0)만 읽으면 두 번째 섹션 이후 단락이 통째로 누락된다.
    #   예) "스텝3 실전문제.hwp"는 54문제가 3개 섹션(4/50/0)에 흩어져 있어
    #       Section0의 4문제만 추출되고 나머지 50문제가 조용히 사라졌다.
    # 모든 섹션의 레코드를 문서 순서대로 이어붙인다. CHAR_SHAPE(ul_map)는
    # DocInfo 전역이라 섹션을 합쳐도 밑줄 매핑이 그대로 유효하다.
    try:
        n_sections = len(hwp.bodytext.sections)
    except Exception as e:
        _LOG.warning("[추출] 섹션 수 확인 실패(%s) — Section0만 읽음, 뒷 섹션 단락 누락 가능: %s",
                     e, os.path.basename(hwp_path))
        n_sections = 1
    all_recs = []
    # image_dir 이 있을 때만 파싱된 모델(그림 정보 포함)을 읽는다. models()는
    # records()와 1:1 동순서이고 record 키(tagid/level/payload)를 그대로 갖는다
    # — 아래 본 루프는 두 경우 모두 같은 코드로 돈다.
    _want_images = bool(image_dir)
    for _si in range(n_sections):
        _sec = hwp.bodytext.section(_si)
        if _want_images:
            try:
                all_recs.extend(list(_sec.models()))
                continue
            except Exception as e:                             # noqa: BLE001
                _LOG.warning("[추출] 모델 파싱 실패(%s) — 그림 추출 생략: %s",
                             os.path.basename(hwp_path), e)
                _want_images = False
        all_recs.extend(list(_sec.records()))
    pics_by_rec = {}
    if _want_images:
        try:
            pics_by_rec = _hwp_collect_pictures(hwp_path, all_recs, image_dir)
        except Exception as e:                                 # noqa: BLE001
            _LOG.warning("[추출] 그림 수집 실패(%s) — 그림 없이 진행: %s",
                         os.path.basename(hwp_path), e)

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
            continue  # 형식 감지용 프리패스 — 실제 누락은 본 루프에서 경고됨
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
            except Exception as e:
                _LOG.warning("[추출] 표-본문 보호 검사 실패(레코드 %d, %s) — "
                             "각주로 분류되어 제외될 수 있음: %s",
                             rj, e, os.path.basename(hwp_path))
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
        except Exception as e:
            _LOG.warning("[추출] 단락 디코딩 실패 — 해당 단락 누락(레코드 %d, %s): %s",
                         i, e, os.path.basename(hwp_path))
            i += 1
            continue

        if txt:
            paragraphs.append({"text": txt, "runs": runs})
            if strip_inline_answers:
                has_red = any(red_map.get(sid) for _pos, sid in cs_pairs)
                metas.append({"lv": rec_level, "red": has_red})
        # 이 단락에 걸린 그림 — 원고 순서 그대로 별도 단락으로 끼운다
        # (그림만 있는 단락은 txt=="" 라 위에서 버려진다).
        for _img in pics_by_rec.get(i, ()):
            paragraphs.append({"text": "", "runs": [], "image": _img})
            if strip_inline_answers:
                metas.append({"lv": rec_level, "red": False})
        i += 1

    if strip_inline_answers:
        paragraphs = _strip_inline_answer_tables(paragraphs, metas)
    return _normalize_circled_numbers(paragraphs)
