"""HWPX -> RTF converter for 배N제 manuscripts.

Rules:
- Preserves underlines (밑줄) via charPr lookup in header.xml
- Extracts only top-level paragraphs (direct children of <sec>)
  to exclude endnote answer paragraphs nested in <ctrl><endNote>
- Skips <ctrl> (endnotes, section properties) within runs
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
