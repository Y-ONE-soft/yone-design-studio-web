"""한영보카 파서 — 원고 헤더 기반 열 자동 매핑 + 단원/섹션 구조화.

지원 형식: xlsx, xls, csv, tsv, txt, hwp, hwpx, docx, pdf
"""

import csv
import json
import os
import re
import struct
import zipfile
import zlib

import openpyxl


def _clean(value):
    if value is None:
        return ""
    return str(value).replace("\xa0", "").strip()


# ── 파일명 → 단원/섹션 추출 ─────────────────────────────────────────────

def _parse_filename(filepath):
    """파일명에서 단원과 섹션 힌트 추출.
    '2. 마더텅 영어독해_3~5강.xlsx' → ('마더텅 영어독해', '3~5강')
    '1. 능률(민)_1과.xlsx' → ('능률(민)', '1과')
    """
    raw = os.path.splitext(os.path.basename(filepath))[0]
    # 업로드 키 접두사 제거
    m = re.match(r'^manuscripts_(.+)$', raw)
    if m:
        raw = m.group(1)
    # 번호 접두사 제거: "1. " "2. "
    raw = re.sub(r'^\d+\.\s*', '', raw)
    # 단원_섹션 분리
    parts = raw.split('_', 1)
    chapter = parts[0].strip()
    section_hint = parts[1].strip() if len(parts) > 1 else ""
    return chapter, section_hint


def _sort_key(filepath):
    """파일명 번호 접두사 기준 정렬."""
    name = os.path.basename(filepath)
    m = re.match(r'^(?:manuscripts_)?(\d+)', name)
    return int(m.group(1)) if m else 9999


# ── 헤더 기반 열 자동 매핑 ───────────────────────────────────────────────

_COL_PATTERNS = {
    'word':       ['어휘', '단어', '표제어', 'word'],
    'meaning':    ['뜻', 'meaning'],
    'synonym':    ['유의어', 'synonym'],
    'antonym':    ['반의어', 'antonym'],
    'definition': ['영영풀이', 'english def', 'definition'],
    'section_marker': ['day', 'unit', 'lesson'],
}


def _detect_columns(header_row):
    """헤더 행에서 각 열의 역할을 감지. 반환: {'word': 0, 'meaning': 1, ...}"""
    col_map = {}
    for idx, cell in enumerate(header_row):
        text = _clean(cell).lower()
        if not text:
            continue
        for role, keywords in _COL_PATTERNS.items():
            if any(k in text for k in keywords):
                if role not in col_map:  # 첫 매칭 우선
                    col_map[role] = idx
                break
    return col_map


def _get_cell(row, col_idx, default=""):
    """행에서 안전하게 셀 값 추출."""
    if col_idx is None or col_idx < 0 or col_idx >= len(row):
        return default
    return _clean(row[col_idx])


# ── 엑셀 파싱 ───────────────────────────────────────────────────────────

def _parse_xlsx(filepath, chapter_name, log, section_hint=""):
    """xlsx 파일 → 섹션 리스트로 변환."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    all_sections = []
    has_def = False

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            rows.append([c.value for c in row])

        if not rows:
            continue

        # 헤더 감지
        col_map = _detect_columns(rows[0])
        if not col_map.get('word'):
            # 헤더가 없으면 기본 매핑 (A=단어, B=뜻, C=유의어, D=반의어)
            col_map = {'word': 0, 'meaning': 1, 'synonym': 2, 'antonym': 3}

        if 'definition' in col_map:
            has_def = True

        has_section_marker = 'section_marker' in col_map
        data_rows = rows[1:]  # 헤더 제외

        if has_section_marker:
            # Day 같은 섹션 구분자가 있는 경우 → 값별로 그룹화
            sec_col = col_map['section_marker']
            current_section = None
            current_entries = []

            for row in data_rows:
                word = _get_cell(row, col_map.get('word'))
                if not word:
                    continue

                sec_val = _clean(row[sec_col]) if sec_col < len(row) else ""
                sec_name = f"Day{sec_val}" if sec_val and sec_val.isdigit() else sec_val

                if sec_name and sec_name != current_section:
                    if current_section and current_entries:
                        all_sections.append({
                            "name": current_section,
                            "count": len(current_entries),
                            "entries": current_entries,
                        })
                        log(f"  [{current_section}] {len(current_entries)}개")
                    current_section = sec_name
                    current_entries = []

                entry = {
                    "word": word,
                    "meaning": _get_cell(row, col_map.get('meaning')),
                    "synonym": _get_cell(row, col_map.get('synonym')),
                    "antonym": _get_cell(row, col_map.get('antonym')),
                }
                if 'definition' in col_map:
                    entry["definition"] = _get_cell(row, col_map.get('definition'))
                current_entries.append(entry)

            # 마지막 섹션
            if current_section and current_entries:
                all_sections.append({
                    "name": current_section,
                    "count": len(current_entries),
                    "entries": current_entries,
                })
                log(f"  [{current_section}] {len(current_entries)}개")
        else:
            # 섹션 구분자 없음 → 시트명이 섹션명
            entries = []
            for row in data_rows:
                word = _get_cell(row, col_map.get('word'))
                if not word:
                    continue
                entry = {
                    "word": word,
                    "meaning": _get_cell(row, col_map.get('meaning')),
                    "synonym": _get_cell(row, col_map.get('synonym')),
                    "antonym": _get_cell(row, col_map.get('antonym')),
                }
                if 'definition' in col_map:
                    entry["definition"] = _get_cell(row, col_map.get('definition'))
                entries.append(entry)

            if entries:
                # 시트명이 기본값(Sheet1 등)이면 파일명의 section_hint 사용
                sec_name = sheet_name
                if re.match(r'^Sheet\d*$', sheet_name, re.IGNORECASE) and section_hint:
                    sec_name = section_hint
                all_sections.append({
                    "name": sec_name,
                    "count": len(entries),
                    "entries": entries,
                })
                log(f"  [{sec_name}] {len(entries)}개")

    wb.close()
    return all_sections, has_def


def _parse_csv(filepath, chapter_name, log, delimiter=","):
    """csv/tsv → 섹션 리스트."""
    rows = []
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            with open(filepath, encoding=enc, errors="strict") as f:
                rows = list(csv.reader(f, delimiter=delimiter))
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if not rows:
        return [], False

    col_map = _detect_columns(rows[0])
    if not col_map.get('word'):
        col_map = {'word': 0, 'meaning': 1, 'synonym': 2, 'antonym': 3}

    has_def = 'definition' in col_map
    entries = []
    for row in rows[1:]:
        word = _get_cell(row, col_map.get('word'))
        if not word:
            continue
        entry = {
            "word": word,
            "meaning": _get_cell(row, col_map.get('meaning')),
            "synonym": _get_cell(row, col_map.get('synonym')),
            "antonym": _get_cell(row, col_map.get('antonym')),
        }
        if has_def:
            entry["definition"] = _get_cell(row, col_map.get('definition'))
        entries.append(entry)

    sec_name = os.path.splitext(os.path.basename(filepath))[0]
    sections = [{"name": sec_name, "count": len(entries), "entries": entries}] if entries else []
    if entries:
        log(f"  [{sec_name}] {len(entries)}개")
    return sections, has_def


# ── HWP 파싱 (olefile + zlib) ────────────────────────────────────────────

def _extract_hwp_texts(filepath):
    """HWP 파일에서 단락 텍스트 추출."""
    import olefile
    ole = olefile.OleFileIO(filepath)
    texts = []
    sec_idx = 0
    while True:
        stream = f'BodyText/Section{sec_idx}'
        if not ole.exists(stream):
            break
        data = ole.openstream(stream).read()
        try:
            decompressed = zlib.decompress(data, -15)
        except Exception:
            sec_idx += 1
            continue
        pos = 0
        while pos < len(decompressed):
            if pos + 4 > len(decompressed):
                break
            header = struct.unpack_from('<I', decompressed, pos)[0]
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF
            if size == 0xFFF:
                if pos + 8 > len(decompressed):
                    break
                size = struct.unpack_from('<I', decompressed, pos + 4)[0]
                pos += 8
            else:
                pos += 4
            if tag_id == 67:  # HWPTAG_PARA_TEXT
                text_data = decompressed[pos:pos + size]
                chars = []
                i = 0
                while i < len(text_data) - 1:
                    ch = struct.unpack_from('<H', text_data, i)[0]
                    i += 2
                    if ch < 32:
                        if ch in (13, 10):
                            chars.append('\n')
                        if ch not in (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31):
                            i += 14
                        continue
                    chars.append(chr(ch))
                t = ''.join(chars).strip()
                if t:
                    texts.append(t)
            pos += size
        sec_idx += 1
    ole.close()
    return texts


def _is_korean(text):
    """텍스트에 한글이 포함되어 있는지 확인."""
    return bool(re.search(r'[\uac00-\ud7a3]', text))


def _is_entry_number(text):
    """단어 순번인지 확인 (1~3자리 숫자)."""
    return bool(re.match(r'^\d{1,3}$', text.strip()))


def _is_question_number(text):
    """모의고사 문항번호인지 확인 (2자리, 18~45 범위)."""
    m = re.match(r'^(\d{2})$', text.strip())
    return m and 18 <= int(m.group(1)) <= 45


def _parse_hwp_entries(texts):
    """HWP 텍스트 단락 → 단어 엔트리 목록으로 변환.

    패턴: 순번 → 단어(영어) → 뜻(한글) → [유의어] → [반의어]
    """
    entries = []
    # 헤더/메타 행 건너뛰기
    skip_keywords = ['무단', '게시금지', 'vocabulary', 'synonym', 'antonym',
                     'no', 'word', 'meaning']
    i = 0
    while i < len(texts):
        t = texts[i].strip()
        # 헤더 행 건너뛰기
        if any(k in t.lower() for k in skip_keywords):
            i += 1
            continue
        # 문항번호(21~45) 건너뛰기
        if _is_question_number(t):
            i += 1
            continue
        # 순번 감지 → 엔트리 시작
        if _is_entry_number(t):
            i += 1
            if i >= len(texts):
                break
            word = _clean(texts[i])
            if not word or _is_entry_number(word) or _is_question_number(word):
                continue
            i += 1
            meaning = ""
            synonym = ""
            antonym = ""
            # 뜻 (한글 포함 행)
            if i < len(texts) and _is_korean(texts[i]):
                meaning = _clean(texts[i])
                i += 1
            # 유의어/반의어 (다음 순번/문항번호 전까지)
            extra = []
            while i < len(texts):
                nxt = texts[i].strip()
                if _is_entry_number(nxt) or _is_question_number(nxt):
                    break
                if any(k in nxt.lower() for k in skip_keywords):
                    i += 1
                    continue
                extra.append(_clean(nxt))
                i += 1
            # extra 분류: 한글 포함 = 반의어, 영어만 = 유의어
            for ex in extra:
                if _is_korean(ex):
                    # 한글+영어 혼합 → 반의어 (예: "stable, secure, steady 안정한")
                    antonym = ex if not antonym else antonym + ", " + ex
                else:
                    synonym = ex if not synonym else synonym + ", " + ex
            entries.append({
                "word": word, "meaning": meaning,
                "synonym": synonym, "antonym": antonym,
            })
        else:
            i += 1
    return entries


def _parse_hwp(filepath, chapter_name, log, section_hint=""):
    """HWP 파일 → 섹션 리스트."""
    texts = _extract_hwp_texts(filepath)
    if not texts:
        return [], False
    entries = _parse_hwp_entries(texts)
    if not entries:
        return [], False
    sec_name = section_hint or chapter_name
    log(f"  [{sec_name}] {len(entries)}개")
    return [{"name": sec_name, "count": len(entries), "entries": entries}], False


# ── HWPX 파싱 (ZIP + XML) ───────────────────────────────────────────────

def _parse_hwpx(filepath, chapter_name, log, section_hint=""):
    """HWPX 파일 → 섹션 리스트."""
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        return [], False
    texts = []
    try:
        with zipfile.ZipFile(filepath) as zf:
            for name in sorted(zf.namelist()):
                if not re.match(r'Contents/section\d+\.xml', name):
                    continue
                tree = ET.parse(zf.open(name))
                root = tree.getroot()
                ns = {'hp': re.match(r'\{(.+?)\}', root.tag).group(1)} if root.tag.startswith('{') else {}
                # 모든 텍스트 노드 추출
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        texts.append(elem.text.strip())
    except Exception:
        return [], False
    if not texts:
        return [], False
    entries = _parse_hwp_entries(texts)
    if not entries:
        return [], False
    sec_name = section_hint or chapter_name
    log(f"  [{sec_name}] {len(entries)}개")
    return [{"name": sec_name, "count": len(entries), "entries": entries}], False


# ── DOCX 파싱 (python-docx) ─────────────────────────────────────────────

def _parse_docx(filepath, chapter_name, log, section_hint=""):
    """DOCX 파일 → 섹션 리스트. 테이블 우선, 없으면 단락에서 추출."""
    try:
        import docx
    except ImportError:
        log("  [경고] python-docx 미설치")
        return [], False

    doc = docx.Document(filepath)
    has_def = False

    # 1) 테이블이 있으면 테이블에서 추출
    all_entries_from_tables = []
    if doc.tables:
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [_clean(cell.text) for cell in row.cells]
                rows.append(cells)
            if not rows or len(rows) < 2:
                continue
            # 헤더 감지
            col_map = _detect_columns(rows[0])
            if not col_map.get('word'):
                # 빈 헤더 + 6열 = HWP 단어장 패턴 (문항번호, 순번, 단어, 뜻, 유의어, 반의어)
                ncols = len(rows[0])
                if ncols >= 5:
                    col_map = {'word': 2, 'meaning': 3, 'synonym': 4,
                               'antonym': 5 if ncols >= 6 else -1}
                else:
                    col_map = {'word': 0, 'meaning': 1, 'synonym': 2, 'antonym': 3}
            if 'definition' in col_map:
                has_def = True
            for row in rows:
                word = _get_cell(row, col_map.get('word'))
                if not word or word.lower() in ('word', '단어', '표제어', '어휘', 'no', ''):
                    continue
                entry = {
                    "word": word,
                    "meaning": _get_cell(row, col_map.get('meaning')),
                    "synonym": _get_cell(row, col_map.get('synonym')),
                    "antonym": _get_cell(row, col_map.get('antonym')),
                }
                if 'definition' in col_map:
                    entry["definition"] = _get_cell(row, col_map.get('definition'))
                all_entries_from_tables.append(entry)
    if all_entries_from_tables:
        sec_name = section_hint or chapter_name
        log(f"  [{sec_name}] {len(all_entries_from_tables)}개")
        return [{"name": sec_name, "count": len(all_entries_from_tables),
                 "entries": all_entries_from_tables}], has_def

    # 2) 테이블 없으면 단락에서 추출 (HWP와 동일 패턴)
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    entries = _parse_hwp_entries(texts)
    if not entries:
        return [], False
    sec_name = section_hint or chapter_name
    log(f"  [{sec_name}] {len(entries)}개")
    return [{"name": sec_name, "count": len(entries), "entries": entries}], False


# ── PDF 파싱 (pdfplumber) ───────────────────────────────────────────────

def _parse_pdf(filepath, chapter_name, log, section_hint=""):
    """PDF 파일 → 섹션 리스트. 테이블 우선, 없으면 텍스트에서 추출."""
    try:
        import pdfplumber
    except ImportError:
        log("  [경고] pdfplumber 미설치")
        return [], False

    has_def = False
    all_entries = []

    with pdfplumber.open(filepath) as pdf:
        # 1) 테이블 추출 시도
        table_entries = []
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                col_map = _detect_columns([_clean(c) if c else "" for c in table[0]])
                if not col_map.get('word'):
                    col_map = {'word': 0, 'meaning': 1, 'synonym': 2, 'antonym': 3}
                if 'definition' in col_map:
                    has_def = True
                for row in table[1:]:
                    cells = [_clean(c) if c else "" for c in row]
                    word = _get_cell(cells, col_map.get('word'))
                    if not word:
                        continue
                    entry = {
                        "word": word,
                        "meaning": _get_cell(cells, col_map.get('meaning')),
                        "synonym": _get_cell(cells, col_map.get('synonym')),
                        "antonym": _get_cell(cells, col_map.get('antonym')),
                    }
                    if 'definition' in col_map:
                        entry["definition"] = _get_cell(cells, col_map.get('definition'))
                    table_entries.append(entry)

        if table_entries:
            all_entries = table_entries
        else:
            # 2) 텍스트에서 추출
            texts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.extend(line.strip() for line in text.split('\n') if line.strip())
            all_entries = _parse_hwp_entries(texts)

    if not all_entries:
        return [], False
    sec_name = section_hint or chapter_name
    log(f"  [{sec_name}] {len(all_entries)}개")
    return [{"name": sec_name, "count": len(all_entries), "entries": all_entries}], has_def


# ── 메인 ─────────────────────────────────────────────────────────────────

def parse_multiple_files(file_paths, output_path, log):
    """여러 원고 파일 → content.json (단원/섹션 구조)."""
    sorted_paths = sorted(file_paths, key=_sort_key)

    chapters = []
    any_has_def = False

    for fp in sorted_paths:
        ext = os.path.splitext(fp)[1].lower()
        chapter_name, section_hint = _parse_filename(fp)
        log(f"[파서] {chapter_name} 파싱 중...")

        if ext in (".xlsx", ".xls"):
            sections, has_def = _parse_xlsx(fp, chapter_name, log, section_hint)
        elif ext == ".csv":
            sections, has_def = _parse_csv(fp, chapter_name, log, ",")
        elif ext in (".tsv", ".txt"):
            sections, has_def = _parse_csv(fp, chapter_name, log, "\t")
        elif ext == ".hwp":
            sections, has_def = _parse_hwp(fp, chapter_name, log, section_hint)
        elif ext == ".hwpx":
            sections, has_def = _parse_hwpx(fp, chapter_name, log, section_hint)
        elif ext == ".docx":
            sections, has_def = _parse_docx(fp, chapter_name, log, section_hint)
        elif ext == ".pdf":
            sections, has_def = _parse_pdf(fp, chapter_name, log, section_hint)
        else:
            log(f"  [경고] 지원하지 않는 형식: {ext}")
            continue

        if not sections:
            log(f"  [경고] 데이터 없음")
            continue

        if has_def:
            any_has_def = True

        total = sum(s["count"] for s in sections)
        chapters.append({
            "name": chapter_name,
            "sections": sections,
            "total": total,
            "has_definition": has_def,
        })

    total_entries = sum(ch["total"] for ch in chapters)
    layout = "가로형" if any_has_def else "세로형"

    content = {
        "layout": layout,
        "has_definition": any_has_def,
        "chapters": chapters,
        "total_entries": total_entries,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    log(f"[파서] 총 {total_entries}개 단어 | 레이아웃: {layout} | {len(chapters)}개 단원")
    return content
