#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
화이트북 워크북 hwpx 파서
hwpx(한글) 파일에서 각 Day의 A~E 섹션 및 정답을 추출해 JSON으로 변환
"""

import zipfile
import os
import re
import json
import xml.etree.ElementTree as ET
import sys

# ─────────────────────────────────────────────
# hwpx 텍스트 추출
# ─────────────────────────────────────────────
def extract_lines_from_hwpx(hwpx_path):
    """hwpx 파일에서 단락별 텍스트 리스트 반환"""
    lines = []
    with zipfile.ZipFile(hwpx_path) as z:
        sections = sorted([n for n in z.namelist()
                           if 'section' in n and n.endswith('.xml')])
        for sec in sections:
            with z.open(sec) as f:
                content = f.read()
            root = ET.fromstring(content.decode('utf-8'))
            for elem in root.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag == 'p':
                    texts = []
                    for t in elem.iter():
                        ttag = t.tag.split('}')[-1] if '}' in t.tag else t.tag
                        if ttag == 't' and t.text:
                            texts.append(t.text)
                    lines.append(''.join(texts))
    return lines


# ─────────────────────────────────────────────
# Day 분할
# ─────────────────────────────────────────────
def split_by_days(lines):
    """'Day N' 헤더를 기준으로 분할, [(day_num, lines_list)] 반환"""
    days = []
    current_day = None
    current_lines = []
    day_pattern = re.compile(r'^Day\s+(\d+)\s*$')
    for line in lines:
        m = day_pattern.match(line.strip())
        if m:
            if current_day is not None:
                days.append((current_day, current_lines))
            current_day = int(m.group(1))
            current_lines = []
        else:
            if current_day is not None:
                current_lines.append(line)
    if current_day is not None:
        days.append((current_day, current_lines))
    return days


# ─────────────────────────────────────────────
# 섹션 분할
# ─────────────────────────────────────────────
SECTION_HEADERS = {
    'A': re.compile(r'^A\.\s*주어진 단어에'),
    'B': re.compile(r'^B\.\s*다음 우리말 해석'),
    'C': re.compile(r'^C\.\s*다음 영영사전'),
    'D': re.compile(r'^D\.\s*주어진 단어와 유사'),
    'E': re.compile(r'^E\.\s*주어진 단어와 어울'),
}

def split_by_sections(day_lines):
    """A~E 섹션 헤더를 기준으로 분할, {A:[lines], B:[lines], ...} 반환"""
    sections = {}
    current_section = None
    for line in day_lines:
        stripped = line.strip()
        matched = False
        for sec, pat in SECTION_HEADERS.items():
            if pat.match(stripped):
                current_section = sec
                sections[current_section] = []
                matched = True
                break
        if not matched and current_section:
            sections[current_section].append(line)
    return sections


# ─────────────────────────────────────────────
# 섹션 A 파싱: 단어 목록 (1~30)
# ─────────────────────────────────────────────
def parse_section_a(lines):
    """
    반환: [{'num': 1, 'word': 'significant', 'raw': '1. significant   '}]
    """
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if m:
            num = int(m.group(1))
            word = m.group(2).strip()
            result.append({'num': num, 'word': word, 'raw': line.rstrip()})
    return result


# ─────────────────────────────────────────────
# 섹션 B 파싱: 영문 문장 + 한글 해석 쌍
# ─────────────────────────────────────────────
def parse_section_b(lines):
    """
    반환: [{'num': 1, 'eng': '...s__...', 'kor': '...한글...'}]
    """
    result = []
    i = 0
    non_empty = [l for l in lines if l.strip()]
    while i < len(non_empty):
        line = non_empty[i]
        stripped = line.strip()
        m = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if m:
            num = int(m.group(1))
            eng = m.group(2).strip()
            kor = ''
            if i + 1 < len(non_empty):
                next_line = non_empty[i + 1].strip()
                # 다음 줄이 숫자로 시작하지 않으면 한글 해석
                if not re.match(r'^\d+\.', next_line):
                    kor = next_line
                    i += 1
            result.append({'num': num, 'eng': eng, 'kor': kor})
        i += 1
    return result


# ─────────────────────────────────────────────
# 섹션 C 파싱: 영영사전 문제 세트 (5문제 × 6개)
# ─────────────────────────────────────────────
def parse_section_c(lines):
    """
    반환: [
      {'set': 1, 'bogis': ['significant', 'exhibit', ...],
       'defs': ['to cause someone...', ...]},
      ...
    ]
    """
    result = []
    current_set = None
    current_bogis = []
    current_defs = []

    problem_pat = re.compile(r'^\[문제\s*(\d+)\]')
    bogis_pat = re.compile(r'^〈보기〉\s*(.+)')
    def_pat = re.compile(r'^(\d+)\.\s+(.+?)\s*:\s*_{3,}')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 문제 헤더
        m = problem_pat.match(stripped)
        if m:
            if current_set is not None:
                result.append({
                    'set': current_set,
                    'bogis': current_bogis,
                    'defs': current_defs
                })
            current_set = int(m.group(1))
            current_bogis = []
            current_defs = []
            continue
        # 보기 라인
        m = bogis_pat.match(stripped)
        if m:
            raw_bogis = m.group(1)
            # '/' 구분자로 분리, 공백 제거
            current_bogis = [w.strip() for w in raw_bogis.split('/')]
            continue
        # 정의 라인
        m = def_pat.match(stripped)
        if m and current_set is not None:
            current_defs.append(stripped)
            continue

    if current_set is not None and current_bogis:
        result.append({
            'set': current_set,
            'bogis': current_bogis,
            'defs': current_defs
        })
    return result


# ─────────────────────────────────────────────
# 섹션 D 파싱: 보기 + 유의어/반의어 항목
# ─────────────────────────────────────────────
def parse_section_d(lines):
    """
    반환: {
      'bogis_raw': ['〈보기〉', '① concord ...', '㉝ break off ...'],  (보기 원문 라인들)
      'items': [{'num': 1, 'word': 'significant', 'type': '반의어',
                 'text': '1. significant [반의어] : ___'}]
    }
    """
    bogis_raw_lines = []
    items = []

    # 보기 시작/끝 인식
    in_bogis = False
    bogis_pat_start = re.compile(r'^〈보기〉')
    numbered_item_pat = re.compile(r'^(\d+)\.\s+(.+?)\s+\[(유의어|반의어|유의어/반의어)\]\s*:\s*_{3,}')
    # 보기 옵션 행: ①, ②... 등 특수문자로 시작
    bogis_row_pat = re.compile(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳]')

    non_empty = [l for l in lines if l.strip()]
    for line in non_empty:
        stripped = line.strip()

        # 항목 라인 (우선)
        m = numbered_item_pat.match(stripped)
        if m:
            in_bogis = False
            num = int(m.group(1))
            word = m.group(2).strip()
            typ = m.group(3).strip()
            items.append({
                'num': num,
                'word': word,
                'type': typ,
                'text': stripped
            })
            continue

        # 보기 시작
        if bogis_pat_start.match(stripped):
            in_bogis = True
            bogis_raw_lines.append(stripped)
            continue

        # 보기 행 (① ②...)
        if in_bogis and bogis_row_pat.match(stripped):
            bogis_raw_lines.append(stripped)
            continue

        # 보기 종료 조건 (빈 줄이나 다른 내용)
        if in_bogis:
            in_bogis = False

    return {
        'bogis_raw': bogis_raw_lines,
        'items': items
    }


# ─────────────────────────────────────────────
# 섹션 E 파싱: 전치사 채우기 문장
# ─────────────────────────────────────────────
def parse_section_e(lines):
    """
    반환: [{'num': 1, 'text': 'The boat is securely anchored ______ the dock...'}]
    """
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if m:
            num = int(m.group(1))
            text = m.group(2).strip()
            result.append({'num': num, 'text': text})
    return result


# ─────────────────────────────────────────────
# 정답 hwpx 파싱
# ─────────────────────────────────────────────
ANSWER_SECTION_PAT = {
    'A': re.compile(r'^▶\s*A\s*$'),
    'B': re.compile(r'^▶\s*B\s*$'),
    'C': re.compile(r'^▶\s*C\s*$'),
    'D': re.compile(r'^▶\s*D\s*$'),
    'E': re.compile(r'^▶\s*E\s*$'),
}

def parse_answer_day(day_lines):
    """
    반환: {
      'A': [{'num': 1, 'word': 'significant', 'meaning': '중요한...'}],
      'B': [{'num': 1, 'answer': 'significant'}],
      'C': [{'set': 1, 'answers': ['mislead', 'exhibit', ...]}],
      'D': [{'num': 1, 'word': 'significant', 'answer': '⑬'}],
      'E': [{'num': 1, 'sentence': 'The boat is...'}]
    }
    """
    current_section = None
    result = {'A': [], 'B': [], 'C': [], 'D': [], 'E': []}
    current_c_set = None
    current_c_answers = []

    problem_pat = re.compile(r'^\[문제\s*(\d+)\]')
    a_item_pat = re.compile(r'^(\d+)\.\s+(.+?)\s*:\s*(.+)$')
    b_item_pat = re.compile(r'^(\d+)\.\s+(.+)$')
    d_item_pat = re.compile(r'^(\d+)\.\s+(.+?)\s*:\s*(.+)$')
    e_item_pat = re.compile(r'^(\d+)\.\s+(.+)$')

    non_empty = [l for l in day_lines if l.strip()]
    i = 0
    while i < len(non_empty):
        stripped = non_empty[i].strip()

        # 섹션 헤더 확인
        section_found = False
        for sec, pat in ANSWER_SECTION_PAT.items():
            if pat.match(stripped):
                # C 섹션 전환 시 이전 set 저장
                if current_section == 'C' and current_c_set is not None:
                    result['C'].append({'set': current_c_set, 'answers': current_c_answers})
                    current_c_set = None
                    current_c_answers = []
                current_section = sec
                section_found = True
                break
        if section_found:
            i += 1
            continue

        if current_section == 'A':
            m = a_item_pat.match(stripped)
            if m:
                result['A'].append({
                    'num': int(m.group(1)),
                    'word': m.group(2).strip(),
                    'meaning': m.group(3).strip()
                })

        elif current_section == 'B':
            m = b_item_pat.match(stripped)
            if m:
                result['B'].append({
                    'num': int(m.group(1)),
                    'answer': m.group(2).strip()
                })

        elif current_section == 'C':
            m = problem_pat.match(stripped)
            if m:
                if current_c_set is not None:
                    result['C'].append({'set': current_c_set, 'answers': current_c_answers})
                current_c_set = int(m.group(1))
                current_c_answers = []
            else:
                m2 = b_item_pat.match(stripped)
                if m2:
                    current_c_answers.append(m2.group(2).strip())

        elif current_section == 'D':
            m = d_item_pat.match(stripped)
            if m:
                result['D'].append({
                    'num': int(m.group(1)),
                    'word': m.group(2).strip(),
                    'answer': m.group(3).strip()
                })

        elif current_section == 'E':
            m = e_item_pat.match(stripped)
            if m:
                result['E'].append({
                    'num': int(m.group(1)),
                    'sentence': m.group(2).strip()
                })

        i += 1

    # 마지막 C set 저장
    if current_section == 'C' and current_c_set is not None:
        result['C'].append({'set': current_c_set, 'answers': current_c_answers})

    return result


# ─────────────────────────────────────────────
# 메인 파서
# ─────────────────────────────────────────────
def parse_workbook_files(hwpx_files, answer_files=None):
    """
    hwpx_files: list of str (원고 hwpx 경로들, Week2/3/4 순)
    answer_files: list of str (정답 hwpx 경로들, 선택적)
    반환: {'days': [day1_data, day2_data, ...]}
    """
    all_days_content = {}   # {day_num: {sections}}
    all_days_answers = {}   # {day_num: {A,B,C,D,E}}

    # 원고 파싱
    for hwpx_path in hwpx_files:
        print(f"[원고 파싱] {os.path.basename(hwpx_path)}")
        lines = extract_lines_from_hwpx(hwpx_path)
        day_groups = split_by_days(lines)
        for day_num, day_lines in day_groups:
            sections = split_by_sections(day_lines)
            all_days_content[day_num] = {
                'A': parse_section_a(sections.get('A', [])),
                'B': parse_section_b(sections.get('B', [])),
                'C': parse_section_c(sections.get('C', [])),
                'D': parse_section_d(sections.get('D', [])),
                'E': parse_section_e(sections.get('E', [])),
            }
            print(f"  Day {day_num}: A={len(all_days_content[day_num]['A'])} "
                  f"B={len(all_days_content[day_num]['B'])} "
                  f"C={len(all_days_content[day_num]['C'])} sets "
                  f"D={len(all_days_content[day_num]['D']['items'])} items "
                  f"E={len(all_days_content[day_num]['E'])}")

    # 정답 파싱
    if answer_files:
        for ans_path in answer_files:
            print(f"[정답 파싱] {os.path.basename(ans_path)}")
            lines = extract_lines_from_hwpx(ans_path)
            day_groups = split_by_days(lines)
            for day_num, day_lines in day_groups:
                all_days_answers[day_num] = parse_answer_day(day_lines)
                ans = all_days_answers[day_num]
                print(f"  Day {day_num}: A={len(ans['A'])} B={len(ans['B'])} "
                      f"C={len(ans['C'])} D={len(ans['D'])} E={len(ans['E'])}")

    # 최종 구조 조립
    result = {'days': []}
    for day_num in sorted(all_days_content.keys()):
        day_data = {
            'day_num': day_num,
            'content': all_days_content[day_num],
            'answers': all_days_answers.get(day_num, {})
        }
        result['days'].append(day_data)

    return result


# ─────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print("사용법: python3 parse_whitebook.py <출력_json> <원고hwpx1> [원고hwpx2 ...] [--answers <정답hwpx1> ...]")
        print("예시:")
        print("  python3 parse_whitebook.py output.json 'Week2.hwpx' 'Week3.hwpx' 'Week4.hwpx' --answers 'Week2정답.hwpx' 'Week3정답.hwpx' 'Week4정답.hwpx'")
        sys.exit(1)

    output_json = sys.argv[1]
    args = sys.argv[2:]

    hwpx_files = []
    answer_files = []
    in_answers = False
    for arg in args:
        if arg == '--answers':
            in_answers = True
        elif in_answers:
            answer_files.append(arg)
        else:
            hwpx_files.append(arg)

    data = parse_workbook_files(hwpx_files, answer_files if answer_files else None)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료: {output_json}")
    print(f"   총 {len(data['days'])}개 Day 파싱됨")


if __name__ == '__main__':
    main()
