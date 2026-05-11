"""HWPX/DOCX -> RTF converter for 배N제 manuscripts.

Rules:
- Preserves underlines (밑줄)
  - HWPX: charPr lookup in header.xml
  - DOCX: w:u element in run properties
- Extracts only top-level paragraphs (endNote/footnote excluded)
- Outputs ASCII RTF with \\uN? Unicode escapes for Korean/non-ASCII text
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET


def _tag(elem):
    t = elem.tag
    return t.split("}")[1] if "}" in t else t


def _build_underline_set(header_bytes):
    """header.xml 에서 밑줄(underline type != NONE)인 charPr id 집합 반환."""
    root = ET.fromstring(header_bytes)
    ul_ids = set()
    for elem in root.iter():
        if _tag(elem) != "charPr":
            continue
        pr_id = elem.get("id", "")
        for child in elem:
            if _tag(child) == "underline":
                if child.get("type", "NONE") != "NONE":
                    ul_ids.add(pr_id)
                break
    return ul_ids


def _rtf_char(ch):
    """단일 문자를 RTF ASCII 안전 문자열로 변환."""
    if ch == "\\":
        return "\\\\"
    if ch == "{":
        return "\\{"
    if ch == "}":
        return "\\}"
    if ch == "\t":
        return "\\tab "
    if ch in ("\r", "\n"):
        return ""
    code = ord(ch)
    if code < 128:
        return ch
    # RTF signed 16-bit Unicode escape
    if code > 32767:
        code -= 65536
    return "\\u%d?" % code


def _rtf_encode(text):
    return "".join(_rtf_char(c) for c in text)


def _collect_run_text(run_elem, ul_ids):
    """run 요소에서 (text, is_underline) 청크 목록 반환.

    - <t> 요소만 텍스트로 수집
    - <ctrl>, <secPr> 등은 무시 (endNote 정답 포함)
    """
    char_pr_id = run_elem.get("charPrIDRef", "")
    is_ul = char_pr_id in ul_ids
    text_parts = []
    for child in run_elem:
        if _tag(child) == "t" and child.text:
            text_parts.append(child.text)
        # ctrl, secPr, linesegarray 등 모두 무시
    combined = "".join(text_parts)
    if not combined:
        return []
    return [(combined, is_ul)]


def _paragraph_to_rtf(para_elem, ul_ids):
    """단락 요소를 RTF 행으로 변환. 빈 단락이면 빈 문자열."""
    chunks = []  # [(text, is_ul), ...]
    for child in para_elem:
        if _tag(child) != "run":
            continue
        chunks.extend(_collect_run_text(child, ul_ids))

    if not chunks:
        return "\\pard\\par"

    # 연속 동일 underline 상태 병합
    merged = []
    for text, ul in chunks:
        if merged and merged[-1][1] == ul:
            merged[-1] = (merged[-1][0] + text, ul)
        else:
            merged.append([text, ul])

    parts = ["\\pard "]
    current_ul = False
    for text, ul in merged:
        if ul and not current_ul:
            parts.append("\\ul ")
            current_ul = True
        elif not ul and current_ul:
            parts.append("\\ulnone ")
            current_ul = False
        parts.append(_rtf_encode(text))
    if current_ul:
        parts.append("\\ulnone ")
    parts.append("\\par")
    return "".join(parts)


def hwpx_to_rtf(hwpx_path, rtf_path):
    """HWPX 파일을 RTF로 변환해 rtf_path에 저장."""
    with zipfile.ZipFile(hwpx_path, "r") as z:
        header_bytes = z.read("Contents/header.xml")
        section_bytes = z.read("Contents/section0.xml")

    ul_ids = _build_underline_set(header_bytes)

    section_root = ET.fromstring(section_bytes)

    # 직접 자식 <p> 요소만 사용 (endNote 안의 정답 단락 제외)
    paragraphs = [c for c in section_root if _tag(c) == "p"]

    lines = [
        "{\\rtf1\\ansi\\deff0",
        "{\\fonttbl{\\f0 Arial;}}",
        "\\widowctrl",
    ]
    for para in paragraphs:
        lines.append(_paragraph_to_rtf(para, ul_ids))
    lines.append("}")

    with open(rtf_path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(lines))


# ── DOCX -> RTF ─────────────────────────────────────────────────────────

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx_paragraph_to_rtf(p_elem):
    """DOCX <w:p> 요소를 RTF 행으로 변환."""
    chunks = []  # [(text, is_ul), ...]
    for r in p_elem:
        if _tag(r) != "r":
            continue
        rpr = r.find(f"{{{_W_NS}}}rPr")
        is_ul = False
        if rpr is not None:
            u_elem = rpr.find(f"{{{_W_NS}}}u")
            if u_elem is not None:
                val = u_elem.get(f"{{{_W_NS}}}val", "none")
                is_ul = val not in ("none", "")
        t_elem = r.find(f"{{{_W_NS}}}t")
        if t_elem is not None and t_elem.text:
            chunks.append((t_elem.text, is_ul))

    if not chunks:
        return "\\pard\\par"

    # 연속 동일 underline 상태 병합
    merged = []
    for text, ul in chunks:
        if merged and merged[-1][1] == ul:
            merged[-1] = (merged[-1][0] + text, ul)
        else:
            merged.append([text, ul])

    parts = ["\\pard "]
    current_ul = False
    for text, ul in merged:
        if ul and not current_ul:
            parts.append("\\ul ")
            current_ul = True
        elif not ul and current_ul:
            parts.append("\\ulnone ")
            current_ul = False
        parts.append(_rtf_encode(text))
    if current_ul:
        parts.append("\\ulnone ")
    parts.append("\\par")
    return "".join(parts)


def _docx_para_text(p_elem):
    """DOCX <w:p> 요소의 평문 텍스트 반환 (판별용)."""
    parts = []
    for r in p_elem:
        if _tag(r) != "r":
            continue
        t = r.find(f"{{{_W_NS}}}t")
        if t is not None and t.text:
            parts.append(t.text)
    return "".join(parts)


def _skip_header_paragraphs(paragraphs):
    """원고 앞부분 제목/헤더 줄과 뒤따르는 빈 줄을 건너뛴 인덱스 반환.

    패턴: 첫 번째 발문(다음 글의~)이 나오기 전의 비-본문 줄을 제거.
    """
    for i, p in enumerate(paragraphs):
        text = _docx_para_text(p).strip()
        if not text:
            continue
        # 발문 시작 패턴: "다음 글", 선지 번호 ①~⑤, 영어 지문 시작
        if text.startswith("다음 글") or text.startswith("(A)"):
            return i
        # 한글 제목/부제 줄이면 계속 건너뜀
        # 본문(영어 지문, 발문 등)이 아닌 줄은 skip
    return 0


def _docx_table_to_rtf(tbl_elem):
    """DOCX <w:tbl> 요소를 탭 구분 텍스트 RTF 단락으로 변환.

    RTF 네이티브 테이블(\trowd)은 InDesign RTF import 시 크래시를 유발하므로,
    각 행을 탭(\tab)으로 구분된 단락으로 변환한다.
    JSX에서 이 단락들을 InDesign 표로 변환한다.
    """
    rows = tbl_elem.findall(f"{{{_W_NS}}}tr")
    if not rows:
        return ""

    first_cells = rows[0].findall(f"{{{_W_NS}}}tc")
    if not first_cells:
        return ""

    rtf_lines = []
    # 표 시작 마커
    rtf_lines.append("\\pard [TABLE_START:%d]\\par" % len(first_cells))

    for row in rows:
        cells = row.findall(f"{{{_W_NS}}}tc")
        cell_texts = []
        for cell in cells:
            cell_paras = cell.findall(f"{{{_W_NS}}}p")
            parts = []
            for cp in cell_paras:
                chunks = []
                for r in cp:
                    if _tag(r) != "r":
                        continue
                    rpr = r.find(f"{{{_W_NS}}}rPr")
                    is_ul = False
                    if rpr is not None:
                        u_elem = rpr.find(f"{{{_W_NS}}}u")
                        if u_elem is not None:
                            val = u_elem.get(f"{{{_W_NS}}}val", "none")
                            is_ul = val not in ("none", "")
                    t_elem = r.find(f"{{{_W_NS}}}t")
                    if t_elem is not None and t_elem.text:
                        if is_ul:
                            chunks.append("\\ul " + _rtf_encode(t_elem.text) + "\\ulnone ")
                        else:
                            chunks.append(_rtf_encode(t_elem.text))
                if chunks:
                    parts.append("".join(chunks))
            cell_texts.append(" ".join(parts) if parts else "")
        # 셀을 탭으로 구분
        rtf_lines.append("\\pard " + "\\tab ".join(cell_texts) + "\\par")

    # 표 끝 마커
    rtf_lines.append("\\pard [TABLE_END]\\par")

    return "\n".join(rtf_lines)


def docx_to_rtf(docx_path, rtf_path):
    """DOCX 파일을 RTF로 변환해 rtf_path에 저장."""
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_bytes = z.read("word/document.xml")

    root = ET.fromstring(doc_bytes)
    body = root.find(f"{{{_W_NS}}}body")
    if body is None:
        raise ValueError("DOCX 문서에서 body를 찾을 수 없습니다.")

    # body 직속 자식 중 p와 tbl을 순서대로 수집
    elements = [c for c in body if _tag(c) in ("p", "tbl")]

    # 헤더 건너뛰기: p 요소만 대상으로 판별
    header_paras = [c for c in elements if _tag(c) == "p"]
    start_offset = _skip_header_paragraphs(header_paras)
    # start_offset 번째 p 이전의 모든 요소를 건너뛰기
    p_count = 0
    skip_until = 0
    for idx, elem in enumerate(elements):
        if _tag(elem) == "p":
            if p_count >= start_offset:
                skip_until = idx
                break
            p_count += 1
    else:
        skip_until = len(elements)
    elements = elements[skip_until:]

    lines = [
        "{\\rtf1\\ansi\\deff0",
        "{\\fonttbl{\\f0 Arial;}}",
        "\\widowctrl",
    ]
    for elem in elements:
        if _tag(elem) == "tbl":
            tbl_rtf = _docx_table_to_rtf(elem)
            if tbl_rtf:
                lines.append(tbl_rtf)
        else:
            lines.append(_docx_paragraph_to_rtf(elem))
    lines.append("}")

    with open(rtf_path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(lines))
