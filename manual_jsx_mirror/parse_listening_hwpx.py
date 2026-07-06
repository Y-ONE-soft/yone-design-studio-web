#!/usr/bin/env python3
"""
Parse listening hwpx files and output text in the format expected by PocketbookListening.jsx.

Supports two formats:
1. Listening Booster: ===== 01회 ===== / [01번] / [Script] / [해석]
2. Textbook listening: [Listen & Speak 1 Listen and Answer 1] / [Script] / [해석]

Output format:
    ===SECTION===SectionName
    ===PASSAGE===PassageName
    ===SCRIPT===
    English lines...
    ===KOREAN===
    Korean lines...
"""
import sys
import re
import zipfile
import xml.etree.ElementTree as ET
import unicodedata


def extract_text_from_hwpx(path):
    """Extract plain text from a hwpx file."""
    z = zipfile.ZipFile(path)
    data = z.read("Contents/section0.xml")
    root = ET.fromstring(data)
    texts = []
    for elem in root.iter():
        if elem.tag.endswith('}t'):
            # <hp:t> 내부의 text + 자식 태그(hp:tab 등) 뒤의 tail 모두 수집
            parts = []
            if elem.text:
                parts.append(elem.text)
            for child in elem:
                if child.tail:
                    parts.append(child.tail)
            if parts:
                texts.append(''.join(parts))
    result = '\n'.join(texts)
    # Fix multi-line passage markers like [1\n번] -> [1번]
    result = re.sub(r'\[(\d+)\n(번)\]', r'[\1\2]', result)
    # Fix multi-line [해석] markers: [\n해석\n] -> [해석]
    result = re.sub(r'\[\n해석\n\]', '[해석]', result)
    # Fix multi-line [Script] markers: [\nScript\n] -> [Script]
    result = re.sub(r'\[\nScript\n\]', '[Script]', result)
    # Fix fragmented section headers like "고\n1 26\n년 \n3\n월 모의고사 듣기"
    # Reconstruct: "고1 26년 3월 모의고사 듣기"
    result = re.sub(
        r'\n고\n(\d+)\s+(\d+)\n년\s*\n(\d+)\n월\s*(모의고사[^\n]*)',
        lambda m: '\n' + '고' + m.group(1) + ' ' + m.group(2) + '년 ' + m.group(3) + '월 ' + m.group(4),
        result
    )
    return result


def normalize(s):
    """Normalize Unicode to NFC."""
    return unicodedata.normalize('NFC', s)


def is_empty_script(lines):
    """Check if script lines are just empty speaker labels (M: , G: , etc.)."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not re.match(r'^[A-Z]+:\s*$', stripped):
            return False
    return True


def is_empty_korean(lines):
    """Check if Korean lines are just empty speaker labels."""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not re.match(r'^[\uB0A8\uC5EC]:\s*$', stripped):  # 남: or 여:
            return False
    return True


def parse_listening_booster(full_text):
    """Parse Listening Booster format with ===== NN회 ===== sections."""
    sections = []
    lines = full_text.split('\n')

    cur_section = None
    cur_passage = None
    mode = ""  # "script" or "korean"

    for line in lines:
        line = line.strip()

        # Section header: ===== 01회 =====
        m = re.match(r'^={3,}\s*(\S+)\s*={3,}$', line)
        if m:
            if cur_passage and cur_section:
                cur_section['passages'].append(cur_passage)
            if cur_section:
                sections.append(cur_section)
            cur_section = {'name': m.group(1), 'passages': []}
            cur_passage = None
            mode = ""
            continue

        if not cur_section:
            continue

        # Passage header: [01번], [16-17번]
        if re.match(r'^\[\d+(-\d+)?\uBC88\]$', line):
            if cur_passage:
                cur_section['passages'].append(cur_passage)
            cur_passage = {'name': line, 'script': [], 'korean': []}
            mode = ""
            continue

        if not cur_passage:
            continue

        if line == '[Script]':
            mode = "script"
            continue
        if line.startswith('[해석]'):
            mode = "korean"
            continue

        if not line:
            continue

        if mode == "script":
            cur_passage['script'].append(line)
        elif mode == "korean":
            cur_passage['korean'].append(line)

    if cur_passage and cur_section:
        cur_section['passages'].append(cur_passage)
    if cur_section:
        sections.append(cur_section)

    return sections


def parse_textbook_listening(full_text):
    """Parse textbook listening format with Listen & Speak / Plan & Present sections."""
    sections = []
    lines = full_text.split('\n')

    cur_section = None
    cur_passage = None
    mode = ""
    passage_header_buffer = ""

    for i, line in enumerate(lines):
        line = line.strip()

        # Chapter header (공통영어1 미래엔(김) 1과, 26년3월 모의고사 등)
        if re.match(r'^(공통영어|영어[12]?\s|26년|25년)', line) or '모의고사' in line:
            if cur_passage and cur_section:
                cur_section['passages'].append(cur_passage)
            if cur_section:
                sections.append(cur_section)
            cur_section = {'name': line, 'passages': []}
            cur_passage = None
            mode = ""
            passage_header_buffer = ""
            continue

        if not cur_section:
            # If no section yet, create one with the first line as name
            if line and not re.match(r'^\[', line):
                cur_section = {'name': line, 'passages': []}
                continue
            elif line:
                cur_section = {'name': 'Listening', 'passages': []}

        # Passage header: [Listen & Speak 1 Listen and Answer 1] or multi-line
        if re.match(r'^\[Listen\s', line) or re.match(r'^\[Plan\s', line):
            if cur_passage:
                cur_section['passages'].append(cur_passage)

            # Handle multi-line headers like [Listen & Speak 1\nListen and Answer 1]
            if line.endswith(']'):
                passage_name = line
            else:
                # Multi-line header - combine with next line
                passage_header_buffer = line
                continue

            cur_passage = {'name': passage_name, 'script': [], 'korean': []}
            mode = ""
            continue

        # Continue multi-line header
        if passage_header_buffer:
            combined = passage_header_buffer + " " + line
            passage_header_buffer = ""
            if combined.endswith(']'):
                cur_passage = {'name': combined, 'script': [], 'korean': []}
                mode = ""
                continue
            else:
                passage_header_buffer = combined
                continue

        # Numbered passage: [01번]
        if re.match(r'^\[\d+(-\d+)?\uBC88\]$', line):
            if cur_passage:
                cur_section['passages'].append(cur_passage)
            cur_passage = {'name': line, 'script': [], 'korean': []}
            mode = ""
            continue

        if not cur_passage:
            continue

        if line == '[Script]':
            mode = "script"
            continue
        if line.startswith('[해석]'):
            mode = "korean"
            continue

        if not line:
            continue

        if mode == "script":
            cur_passage['script'].append(line)
        elif mode == "korean":
            cur_passage['korean'].append(line)

    if cur_passage and cur_section:
        cur_section['passages'].append(cur_passage)
    if cur_section:
        sections.append(cur_section)

    return sections


def detect_format(full_text):
    """Detect whether the content is Listening Booster or textbook format."""
    if re.search(r'={3,}\s*\d+회\s*={3,}', full_text):
        return "booster"
    if re.search(r'\[Listen\s', full_text):
        return "textbook"
    if re.search(r'\[\d+번\]', full_text):
        return "booster"
    return "textbook"


def join_fragmented_lines(lines):
    """Join fragmented lines (single words/punctuation) into proper sentences.

    Handles cases like: ['남', ':', ' ', '안녕하세요', '.'] -> ['남: 안녕하세요.']
    """
    if not lines:
        return lines

    result = []
    buf = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                result.append(buf.strip())
                buf = ""
            continue
        # Short fragments (1-2 chars, punctuation, or speaker labels without text)
        if len(stripped) <= 2 or re.match(r'^[.:,!?\s]+$', stripped):
            buf += stripped
        elif re.match(r'^[A-Z]+:\s', stripped) or re.match(r'^[\uB0A8\uC5EC]:\s', stripped):
            # Speaker label (with or without content): start new line
            if buf:
                result.append(buf.strip())
            buf = stripped
        else:
            buf += stripped
    if buf:
        result.append(buf.strip())

    # Clean up: merge lines that are just continuations
    final = []
    for line in result:
        # If line starts with punctuation or is very short, append to previous
        if final and (re.match(r'^[.:,!?]', line) or len(line) <= 2):
            final[-1] += line
        else:
            final.append(line)

    # Split at mid-line speaker labels (남:, 여: or M:/W:/B:/G: etc.)
    split = []
    for line in final:
        # Split where a Korean speaker label appears mid-line
        parts = re.split(r'(?<=[.?!)\]])(?=[\uB0A8\uC5EC]:)', line)
        if len(parts) <= 1:
            # Try English speaker labels
            parts = re.split(r'(?<=[.?!)\]])(?=[A-Z]+:\s?)', line)
        for part in parts:
            part = part.strip()
            if part:
                split.append(part)

    # Ensure space after speaker labels (남:X -> 남: X)
    for i in range(len(split)):
        split[i] = re.sub(r'^([\uB0A8\uC5EC]:)(\S)', r'\1 \2', split[i])

    return split


def format_output(sections):
    """Format sections as the text file expected by PocketbookListening.jsx."""
    out = []
    for sec in sections:
        out.append("===SECTION===" + sec['name'])
        for p in sec['passages']:
            out.append("===PASSAGE===" + p['name'])

            # Skip empty scripts
            script_lines = p.get('script', [])
            if script_lines and not is_empty_script(script_lines):
                out.append("===SCRIPT===")
                for line in script_lines:
                    out.append(line)

            korean_lines = p.get('korean', [])
            if korean_lines:
                # Join fragmented Korean lines
                korean_lines = join_fragmented_lines(korean_lines)
                out.append("===KOREAN===")
                for line in korean_lines:
                    out.append(line)

    return '\n'.join(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_listening_hwpx.py <input.hwpx> [output.txt]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    full_text = normalize(extract_text_from_hwpx(input_path))
    fmt = detect_format(full_text)

    print(f"Detected format: {fmt}", file=sys.stderr)

    if fmt == "booster":
        sections = parse_listening_booster(full_text)
    else:
        sections = parse_textbook_listening(full_text)

    # Summary
    for sec in sections:
        total_script = sum(len('\n'.join(p['script'])) for p in sec['passages'])
        total_korean = sum(len('\n'.join(p['korean'])) for p in sec['passages'])
        empty = sum(1 for p in sec['passages'] if is_empty_script(p.get('script', [])))
        print(f"  Section '{sec['name']}': {len(sec['passages'])} passages, "
              f"script={total_script} chars, korean={total_korean} chars, "
              f"empty_scripts={empty}", file=sys.stderr)

    # Filter: script와 korean 둘 다 있는 passage만 유지
    for sec in sections:
        sec['passages'] = [p for p in sec['passages']
                          if (p.get('script', []) and not is_empty_script(p['script']))
                          and (p.get('korean', []) and not is_empty_korean(p['korean']))]
    # Remove empty sections
    sections = [s for s in sections if s['passages']]

    result = format_output(sections)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f"Written to {output_path}", file=sys.stderr)
    else:
        print(result)


if __name__ == '__main__':
    main()
