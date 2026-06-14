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


# 선지 마커 (①~⑳) — 탭 정렬된 선지를 표로 강제 변환하지 않기 위한 분류용
_OPTION_MARKERS = set(chr(c) for c in range(0x2460, 0x2474))


def _starts_with_option(cell):
    c = cell.strip()
    return len(c) > 0 and c[0] in _OPTION_MARKERS


def _classify_tab_line(full_text):
    """탭 포함 단락 분류 → 'grid' | 'header' | 'normal'.

    - grid:   한 줄에 선지(①②③…)가 여럿 탭으로 나열. 표로 묶으면 칸수 불일치·
              ⑤ 누락·순서 꼬임이 생기므로 한 줄당 한 선지로 분리한다.
    - header: 어휘 (A)/(B) 머리행. 탭/공백/선행탭 무관하게 '(A)\\tab (B)'로 정규화.
    - normal: 그 외(본문·발문·어휘 데이터행 '①단어\\t단어' 등) — 기존 처리 유지.
    """
    cells = full_text.split("\t")
    if len(cells) >= 2 and any(_starts_with_option(c) for c in cells[1:]):
        return "grid"
    if re.sub(r"\s+", " ", full_text.replace("\t", " ")).strip() == "(A) (B)":
        return "header"
    return "normal"


def _hp_text_content(t_elem):
    """<hp:t> 요소의 전체 텍스트를 추출한다.

    HWPX는 <hp:t> 안에 <hp:tab/> 같은 인라인 요소를 두고, 그 뒤에 오는 텍스트를
    그 인라인 요소의 tail에 담는다. 따라서 element.text(첫 인라인 요소 앞 텍스트)만
    읽으면 탭 뒤 내용이 통째로 누락된다((A)/(B) 보기처럼 "① carry out" 만 남고
    "prudent" 가 사라지는 증상). text + (tab→\\t) + 각 인라인 요소의 tail 을 순서대로
    이어붙여 누락을 막는다.

    연속된 탭(<hp:tab/><hp:tab/>)은 HWP에서 시각적 정렬용이므로 하나의 탭(열 구분)으로
    합친다. 그래야 표 변환 시 헤더(탭 1개)와 보기(탭 2개)의 열 수가 어긋나 빈 열이
    끼는 일이 없다.
    """
    parts = []
    if t_elem.text:
        parts.append(t_elem.text)
    for sub in t_elem:
        if _tag(sub) == "tab":
            if not parts or parts[-1] != "\t":
                parts.append("\t")
        if sub.tail:
            parts.append(sub.tail)
    return "".join(parts)


def _collect_run_text(run_elem, ul_ids):
    """run 요소에서 (text, is_underline) 청크 목록 반환.

    - <t> 요소만 텍스트로 수집
    - <ctrl>, <secPr> 등은 무시 (endNote 정답 포함)
    """
    char_pr_id = run_elem.get("charPrIDRef", "")
    is_ul = char_pr_id in ul_ids
    text_parts = []
    for child in run_elem:
        if _tag(child) == "t":
            # child.text 만 읽으면 <hp:tab/> 뒤(tail) 내용이 누락되므로 전체 추출
            text_parts.append(_hp_text_content(child))
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

    # 선지 그리드 / (A)(B) 머리행 정규화 (탭 정렬 선지를 표로 만들며 깨지는 문제 방지)
    full_text = "".join(t for t, _ in chunks)
    kind = _classify_tab_line(full_text)
    if kind == "grid":
        cells = [c.strip() for c in full_text.split("\t") if c.strip()]
        if cells:
            return "\n".join("\\pard " + _rtf_encode(c) + "\\par" for c in cells)
    elif kind == "header":
        return "\\pard (A)\\tab (B)\\par"

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
    """DOCX <w:p> 요소를 RTF 행으로 변환.

    run 내 <w:br type="textWrapping"/>(Shift+Enter)는 RTF 단락 분리로 변환한다.
    JSX의 후처리(\\r{2,} -> \\r)가 연속 빈 단락을 정리하므로 br 2개도 안전하다.
    """
    # 토큰 시퀀스: ("text", str, is_ul) 또는 ("para_break",)
    tokens = []
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
        for child in r:
            ctag = _tag(child)
            if ctag == "t" and child.text:
                tokens.append(("text", child.text, is_ul))
            elif ctag == "br":
                btype = child.get(f"{{{_W_NS}}}type", "textWrapping")
                if btype in ("textWrapping", "", None):
                    tokens.append(("para_break",))
                # column/page break은 무시

    if not tokens:
        return "\\pard\\par"

    # br 기준으로 sub-paragraph로 분할
    subparas = [[]]
    for tok in tokens:
        if tok[0] == "para_break":
            subparas.append([])
        else:
            subparas[-1].append((tok[1], tok[2]))

    lines = []
    for sub in subparas:
        if not sub:
            lines.append("\\pard\\par")
            continue
        merged = []
        for text, ul in sub:
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
        lines.append("".join(parts))

    return "\n".join(lines)


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


_NUMBERED_QUESTION_RE = re.compile(r"^\d+\.\s+(다음|글|Which|Read)")


def _skip_header_paragraphs(paragraphs):
    """원고 앞부분 제목/헤더 줄과 뒤따르는 빈 줄을 건너뛴 인덱스 반환.

    패턴: 첫 번째 발문(다음 글의~ 또는 "1. 다음~" 번호 발문)이 나오기 전의 비-본문 줄을 제거.
    """
    for i, p in enumerate(paragraphs):
        text = _docx_para_text(p).strip()
        if not text:
            continue
        # 발문 시작 패턴: "다음 글~", 번호 발문 "N. 다음/글/Which/Read~", 영어 지문 시작 "(A)"
        if (text.startswith("다음 글")
                or text.startswith("(A)")
                or _NUMBERED_QUESTION_RE.match(text)):
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
