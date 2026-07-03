"""
블랙북 hwpx/hwp 파서

hwpx(ZIP) → section0.xml + header.xml → 단락 추출 → Day별 분류 → content.json

단락 타입:
  day_header      : "Day N"
  passage_header  : "【 N-M 】 다음 글을 읽고..."
  passage         : 지문 본문
  problem         : "N. 문제내용?" (정답 기호 제거)
  choice          : "① ② ③ ④ ⑤" 선지
  condition       : "[채점기준]" / "[조건]" 등 대괄호 레이블
  condition_item  : 조건 구간 내 번호 항목 "1. / 2. ..."
  answer_blank    : "답:" 줄
  etc             : 기타

단락 데이터 구조:
  {"text": str, "type": str, "runs": [{"t": str, "ul": bool}, ...]}
  runs[].ul == True → InDesign에서 밑줄 문자 스타일 적용
"""

import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _wtag(tag: str) -> str:
    return f"{{{_W_NS}}}{tag}"


# ── header.xml: underline charPr ID 수집 ────────────────────────────────────
# Phase 1: core/extract의 동일 구현으로 대체 (기존 사본과 byte-identical 로직)
from core.extract import _parse_underline_ids  # noqa: E402


# ── section0.xml: 단락 추출 ─────────────────────────────────────────────────

def _extract_segments(body: str, ul_ids: set) -> list:
    """
    <hp:run> 목록을 순회하며 (text, underline, new_para) 세그먼트 목록 반환.
    <hp:lineBreak/>는 새 단락 시작 신호로 처리.
    반환: [{"t": str, "ul": bool, "new_para": bool}]

    ※ core.extract._hwpx_extract_segments와 유사하나 의도적 차이 존재
      (hp:t 매칭 폭, hp:tab 미치환, page_break는 상위에서 처리) —
      통합은 Phase 2에서 골든 diff 검토와 함께. 지금은 동작 보존이 우선.
    """
    segments = []
    for run_m in re.finditer(r'<hp:run\s+charPrIDRef="(\d+)"[^>]*>(.*?)</hp:run>', body, re.DOTALL):
        ref_id = run_m.group(1)
        run_body = run_m.group(2)
        is_ul = ref_id in ul_ids

        for t_m in re.finditer(r'<hp:t[^>]*>(.*?)</hp:t>', run_body, re.DOTALL):
            t_content = t_m.group(1)
            # <hp:lineBreak/> 기준으로 분리 (선지 등 여러 항목을 한 hp:t에 담아둔 경우)
            parts = re.split(r'<hp:lineBreak\s*/>', t_content)
            for j, part in enumerate(parts):
                text = html.unescape(part)
                segments.append({
                    "t": text,
                    "ul": is_ul,
                    "new_para": j > 0,  # lineBreak 이후 → 새 단락 시작
                })
    return segments


def _segments_to_paras(segments: list, page_break: bool) -> list:
    """세그먼트 목록 → 단락 목록. new_para 플래그 기준으로 단락 분리."""
    if not segments:
        return []

    paras = []
    cur_runs = []
    is_first = True

    def flush():
        text = ''.join(r['t'] for r in cur_runs).strip()
        if text:
            paras.append({
                'page_break': page_break if is_first else False,
                'text': text,
                'runs': [r for r in cur_runs if r['t']],
            })

    for seg in segments:
        if seg['new_para']:
            flush()
            cur_runs = []
            is_first = False
        cur_runs.append({"t": seg["t"], "ul": seg["ul"]})

    flush()
    return paras


def _parse_paragraphs(section_xml: str, header_xml: str = '') -> list:
    """section0.xml + header.xml → 단락 목록 반환."""
    ul_ids = _parse_underline_ids(header_xml) if header_xml else set()

    result = []
    # 미주/각주를 section XML 전체에서 선제 제거 (중첩 hp:run 문제 방지)
    section_xml = re.sub(r'<hp:endNote\b.*?</hp:endNote>', '', section_xml, flags=re.DOTALL)
    section_xml = re.sub(r'<hp:footnote\b.*?</hp:footnote>', '', section_xml, flags=re.DOTALL)

    for m in re.finditer(r'<hp:p\b([^>]*)>(.*?)</hp:p>', section_xml, re.DOTALL):
        attrs = m.group(1)
        body = m.group(2)
        page_break = 'pageBreak="1"' in attrs
        segments = _extract_segments(body, ul_ids)
        sub_paras = _segments_to_paras(segments, page_break)
        result.extend(sub_paras)
    return result


# ── 단락 분류 ───────────────────────────────────────────────────────────────

_RE_DAY         = re.compile(r'^Day\s+\d+$')
_RE_PASSAGE_HDR = re.compile(r'^【')
_RE_PROBLEM     = re.compile(r'^\d+\.')
_RE_CHOICE      = re.compile(r'^[①②③④⑤]')
_RE_CONDITION   = re.compile(r'^\s*\[[^\]]+\]\s*$')  # [채점기준] 등 대괄호 레이블
_RE_COND_ITEM   = re.compile(r'^\s*\d+[.)\s]')
_RE_ANSWER      = re.compile(r'^\s*답\s*:')
_RE_INLINE_ANS  = re.compile(r'\s+[①②③④⑤][,\s①②③④⑤]*$')

# "다음 글을 읽고 물음에 답하시오" 단독 단락 (【...】 접두어 포함 가능)
_RE_NEXT_Q = re.compile(
    r'^(?:【[^】]*】\s*)?다음\s*글을\s*읽고[,，、]?\s*물음에\s*답하시오\.?\s*$'
)
# 레이블 변형 정규화
_RE_LABEL_SUMMARY   = re.compile(r'^[\[<（(〔【]\s*요약문?\s*[\]>）)〕】]\s*$')
_RE_LABEL_EXAMPLE   = re.compile(r'^[\[<（(〔【]\s*보\s*기\s*[\]>）)〕】]\s*$')
_RE_LABEL_CONDITION = re.compile(r'^[\[<（(〔【]\s*조\s*건\s*[\]>）)〕】]\s*$')


def _normalize_label(text: str) -> str:
    """[요약문]/[보기]/[조건] 변형을 통일된 <표기>로 정규화."""
    if _RE_LABEL_SUMMARY.match(text):   return '<요약문>'
    if _RE_LABEL_EXAMPLE.match(text):   return '<보기>'
    if _RE_LABEL_CONDITION.match(text): return '<조건>'
    return text


def _is_condition_content(text: str) -> bool:
    """조건 구간 항목 패턴 판별 (숫자/글리프/~것/~임 등)."""
    t = text.strip()
    if re.match(r'^\d+[.)]\s', t): return True        # 1. / 1)
    if re.match(r'^[（(]\d+[）)]\s*', t): return True  # (1) (2)
    if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]', t): return True  # 원문자
    if re.match(r'^[•·‧･●◆▶▷►◉∙－－]', t): return True  # 글리프
    if re.search(r'[것임][.,;：:\s]*$', t): return True  # ~것 ~임 으로 끝남
    return False


def _classify(text: str, in_condition: bool) -> str:
    if not text:
        return 'blank'
    if _RE_DAY.match(text):
        return 'day_header'
    # "다음 글을 읽고 물음에 답하시오" 단독 단락
    if _RE_NEXT_Q.match(text):
        return 'next_question'
    if _RE_PASSAGE_HDR.match(text):
        return 'passage_header'
    if _RE_ANSWER.match(text):
        return 'answer_blank'
    # 정규화된 레이블 (summary_label / example_label)
    if text.strip() == '<요약문>':
        return 'summary_label'
    if text.strip() == '<보기>':
        return 'example_label'
    if text.strip() == '<조건>':
        return 'condition'
    # 기타 대괄호 조건 레이블
    if _RE_CONDITION.match(text):
        return 'condition'
    # 문제 단락 판별 (condition 내부에서도 실제 문제는 problem으로 분류)
    if _RE_PROBLEM.match(text):
        # 조건 구간 내부라도 실제 시험 문제 패턴이면 problem으로 분류
        if not in_condition or re.match(r'^\d+\.\s*다음', text):
            return 'problem'
        # 조건 구간 내 작은 번호 항목이면 condition_item
        if _is_condition_content(text):
            return 'condition_item'
        return 'problem'
    # in_condition 상태에서는 ①②③ 등을 choice보다 먼저 확인
    if in_condition and _is_condition_content(text):
        return 'condition_item'
    if _RE_CHOICE.match(text):
        return 'choice'
    return 'passage'


def _strip_inline_answer(text: str, runs: list) -> tuple:
    """문제 단락 끝 인라인 정답 기호 제거. (text, runs) 반환."""
    m = _RE_INLINE_ANS.search(text)
    if not m:
        return text, runs
    stripped = text[:m.start()]
    # runs도 stripped 길이 내로 잘라냄
    trimmed_runs = []
    pos = 0
    for r in runs:
        t_len = len(r['t'])
        if pos >= len(stripped):
            break
        if pos + t_len > len(stripped):
            trimmed = {'t': r['t'][:len(stripped) - pos], 'ul': r['ul']}
            if trimmed['t']:
                trimmed_runs.append(trimmed)
        else:
            trimmed_runs.append(r)
        pos += t_len
    return stripped, trimmed_runs


# ── Day 분리 ────────────────────────────────────────────────────────────────

def _split_into_days(paras: list) -> list:
    """단락 목록을 Day 기준으로 분리. 레이블 정규화 + 컨텍스트 기반 타입 결정."""
    days = []
    current = None
    in_condition = False
    in_summary   = False  # <요약문> 이후 → summary_content 적용
    in_example   = False  # <보기> 이후 → 즉시 다음 단락 하나만 example_content 후보

    for p in paras:
        text = p['text']

        # 레이블 정규화 ([보기] → <보기> 등)
        norm = _normalize_label(text)
        if norm != text:
            p = dict(p)
            p['text'] = norm
            text = norm

        typ = _classify(text, in_condition)

        # ── 컨텍스트 기반 타입 오버라이드 (passage 단락 한정) ──────────────
        if typ == 'passage':
            if in_summary:
                typ = 'summary_content'
            elif in_example:
                if '/' in text or ',' in text or '，' in text:
                    typ = 'example_content'
                in_example = False  # 즉시 다음 한 단락만 체크

        # ── 컨텍스트 상태 업데이트 ────────────────────────────────────────
        if typ == 'summary_label':
            in_summary = True; in_example = False; in_condition = False
        elif typ == 'example_label':
            in_example = True; in_summary = False; in_condition = False
        elif typ == 'condition':
            in_condition = True; in_summary = False; in_example = False
        elif typ in ('problem', 'passage_header', 'next_question',
                     'choice', 'answer_blank', 'day_header'):
            in_condition = False; in_summary = False; in_example = False
        # summary_content: in_summary 유지 (계속 적용)

        # ── Day 헤더 처리 ─────────────────────────────────────────────────
        if typ == 'day_header':
            m = re.search(r'\d+', text)
            day_num = int(m.group()) if m else len(days) + 1
            if current:
                days.append(current)
            current = {'day_num': day_num, 'paragraphs': []}
            in_condition = False; in_summary = False; in_example = False
            continue

        if current is None or typ == 'blank':
            continue

        final_text = text
        final_runs = p.get('runs', [])
        if typ == 'problem':
            final_text, final_runs = _strip_inline_answer(text, final_runs)

        if final_text:
            current['paragraphs'].append({
                'text': final_text,
                'type': typ,
                'runs': final_runs,
            })

    if current:
        days.append(current)
    return days


# ── 정답 파일 파싱 ──────────────────────────────────────────────────────────

def _parse_answer_lines(lines: list) -> list:
    """
    정답 텍스트 줄 목록 → [{"num": int, "answer": str, "explanation": str}]
    지원 형식:
      HWPX: "N [정답] ANSWER" 한 줄, 이후 "[해설]" 줄, 해설 줄들
      HWP:  순수 숫자 줄, "[정답] ANSWER", "[해설] TEXT"
    """
    answers = []
    current = None
    in_explanation = False

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        # "Day N" 경계는 무시
        if re.match(r'^Day\s+\d+', line_s, re.IGNORECASE):
            continue

        # "N [정답] ANSWER" — HWPX 형식 한 줄
        m = re.match(r'^(\d+)\s+\[정답\]\s*(.*)', line_s)
        if m:
            if current is not None:
                answers.append(current)
            current = {
                'num': int(m.group(1)),
                'answer': m.group(2).strip(),
                'explanation': '',
            }
            in_explanation = False
            continue

        # "[해설]" 단독 줄
        if line_s == '[해설]':
            in_explanation = True
            continue

        # 순수 숫자 줄 → HWP 바이너리 형식 번호
        if re.match(r'^\d+$', line_s):
            num = int(line_s)
            if 1 <= num <= 200:
                if current is not None:
                    answers.append(current)
                current = {'num': num, 'answer': '', 'explanation': ''}
                in_explanation = False
            continue

        if current is None:
            continue

        # "[정답] ANSWER" — HWP 형식
        if line_s.startswith('[정답]'):
            current['answer'] = line_s[len('[정답]'):].strip()
            in_explanation = False
            continue

        # "[해설] TEXT" — HWP 인라인 해설
        if line_s.startswith('[해설]'):
            current['explanation'] = line_s[len('[해설]'):].strip()
            in_explanation = True
            continue

        # 해설 이어지는 줄
        if in_explanation:
            sep = '\n' if current['explanation'] else ''
            current['explanation'] += sep + line_s

    if current is not None:
        answers.append(current)

    return answers


def _extract_hwpx_answer_lines(hwpx_path: str) -> list:
    """HWPX(ZIP) → 텍스트 줄 목록."""
    with zipfile.ZipFile(hwpx_path, 'r') as zf:
        names = zf.namelist()
        sec_name = next(
            (n for n in names if re.search(r'section\d+\.xml', n, re.I)), None
        )
        if not sec_name:
            raise ValueError(f"section XML 없음: {hwpx_path}")
        sec_xml = zf.read(sec_name).decode('utf-8')

    sec_xml = re.sub(r'<hp:endNote\b.*?</hp:endNote>', '', sec_xml, flags=re.DOTALL)
    sec_xml = re.sub(r'<hp:footnote\b.*?</hp:footnote>', '', sec_xml, flags=re.DOTALL)

    lines = []
    for m in re.finditer(r'<hp:p\b[^>]*>(.*?)</hp:p>', sec_xml, re.DOTALL):
        body = m.group(1)
        parts = []
        for t_m in re.finditer(r'<hp:t[^>]*>(.*?)</hp:t>', body, re.DOTALL):
            parts.append(html.unescape(t_m.group(1)))
        text = ''.join(parts)
        for sub in re.split(r'<hp:lineBreak\s*/>', text):
            sub = sub.strip()
            if sub:
                lines.append(sub)
    return lines


def parse_answers_hwp(hwp_path: str) -> list:
    """
    정답 파일 → [{"num": int, "answer": str, "explanation": str}]
    HWPX(ZIP) 및 HWP(OLE2 바이너리) 모두 지원.
    """
    # HWPX: ZIP 형식
    if zipfile.is_zipfile(hwp_path):
        lines = _extract_hwpx_answer_lines(hwp_path)
        return _parse_answer_lines(lines)

    # HWP 바이너리 (OLE2)
    try:
        from hwp5.xmlmodel import Hwp5File
    except ImportError:
        raise RuntimeError("pyhwp 미설치. pip install pyhwp 실행 후 재시도.")

    hwp = Hwp5File(hwp_path)
    sec = hwp.bodytext.section(0)

    lines = []
    for rec in sec.records():
        if rec.get('tagid') != 67:
            continue
        try:
            txt = rec['payload'].decode('utf-16-le')
            txt = ''.join(c for c in txt if ord(c) >= 0x20 or c == '\n')
            txt = txt.strip()
            if txt:
                lines.append(txt)
        except Exception:
            pass

    return _parse_answer_lines(lines)


# ── DOCX 단락 파서 ──────────────────────────────────────────────────────────

def _parse_docx_paragraphs(docx_path: str) -> list:
    """docx 파일 → [{'text', 'runs', 'page_break': False}] 단락 목록."""
    with zipfile.ZipFile(docx_path, 'r') as zf:
        doc_xml = zf.read("word/document.xml").decode('utf-8')

    root = ET.fromstring(doc_xml)
    body = root.find(_wtag("body"))
    if body is None:
        return []

    result = []
    for elem in body:
        if elem.tag != _wtag("p"):
            continue

        runs = []
        for r in elem.findall(_wtag("r")):
            rpr = r.find(_wtag("rPr"))
            is_ul = False
            if rpr is not None:
                u = rpr.find(_wtag("u"))
                if u is not None:
                    val = u.get(_wtag("val"), "none")
                    is_ul = val not in ("none", "")
            for sub in r:
                if sub.tag == _wtag("t") and sub.text:
                    runs.append({'t': sub.text, 'ul': is_ul})

        text = ''.join(r['t'] for r in runs).strip()
        if text:
            # 연속 동일 underline 상태 병합
            merged = []
            for run in runs:
                if not run['t']:
                    continue
                if merged and merged[-1]['ul'] == run['ul']:
                    merged[-1]['t'] += run['t']
                else:
                    merged.append({'t': run['t'], 'ul': run['ul']})
            result.append({
                'page_break': False,
                'text': text,
                'runs': merged,
            })

    return result


def _extract_docx_lines(docx_path: str) -> list:
    """docx 본문에서 텍스트 줄 목록만 추출 (정답지 파싱용)."""
    with zipfile.ZipFile(docx_path, 'r') as zf:
        doc_xml = zf.read("word/document.xml").decode('utf-8')
    root = ET.fromstring(doc_xml)
    body = root.find(_wtag("body"))
    if body is None:
        return []
    lines = []
    for elem in body:
        if elem.tag != _wtag("p"):
            continue
        parts = []
        for r in elem.findall(_wtag("r")):
            for sub in r:
                if sub.tag == _wtag("t") and sub.text:
                    parts.append(sub.text)
        text = ''.join(parts).strip()
        if text:
            lines.append(text)
    return lines


# ── 양식 자동 감지 ──────────────────────────────────────────────────────────

_RE_PART_MARKER = re.compile(r'^\s*<\s*Part\s*[12](?:\s*어휘)?\s*>\s*$', re.IGNORECASE)
_RE_PASSAGE_MARKER = re.compile(r'^\s*<\s*본문\s*\d+\s*>\s*$')
_RE_CATEGORY = re.compile(r'^\s*<\s*(?:연관\s*어휘|영영\s*풀이|속담(?:\s*및\s*격언)?)\s*>\s*$')


def detect_format(paras: list) -> str:
    """단락 목록을 보고 'part' 또는 'day' 양식 반환."""
    for p in paras:
        text = p.get('text', '').strip()
        if _RE_PART_MARKER.match(text):
            return 'part'
        if _RE_DAY.match(text):
            return 'day'
    # 마커 없으면 기본값 'day'
    return 'day'


# ── Part 양식 분류 및 분할 ──────────────────────────────────────────────────

def _classify_vocab_line(text: str) -> str:
    """어휘 영역 내 단락 분류."""
    t = text.strip()
    if _RE_CATEGORY.match(t):
        return 'category'
    if t.startswith('동의어:') or t.startswith('반의어:'):
        return 'vocab'
    # "단어(품사): 영어 정의" 패턴 → english_def
    if re.match(r'^[A-Za-z][\w\s\-]*\([^)]+\):', t):
        return 'english_def'
    return None  # 컨텍스트 의존 — 호출부에서 결정


def _is_english_line(text: str) -> bool:
    """영어로만 된 줄인지 (한글 미포함)."""
    return bool(re.search(r'[A-Za-z]', text)) and not bool(re.search(r'[가-힣]', text))


def _split_into_parts(paras: list) -> dict:
    """단락 목록을 <Part1>/<Part1 어휘>/<Part2> 영역으로 분리."""
    section = None  # 'part1' / 'vocab' / 'part2'
    vocab_passage_no = 0
    vocab_passage_paras = None  # 현재 본문 단락 목록
    vocab_in_category = None    # 현재 카테고리 ('vocab' / 'english_def' / 'saying')

    parts = {
        'part1': [],   # 객관식 단락 (problem, choice, ...)
        'vocab': [],   # [{'passage_label', 'paragraphs': [...]}]
        'part2': [],
    }

    def start_new_passage(label):
        nonlocal vocab_passage_paras, vocab_in_category
        vocab_passage_paras = []
        vocab_in_category = None
        parts['vocab'].append({
            'label': label,
            'paragraphs': vocab_passage_paras,
        })

    in_condition = False
    in_summary = False
    in_example = False

    for p in paras:
        text = p.get('text', '').strip()
        runs = p.get('runs', [])
        if not text:
            continue

        # ── 영역 마커 ──
        m_part = _RE_PART_MARKER.match(text)
        if m_part:
            t_low = text.lower().replace(' ', '')
            if '어휘' in t_low or 'vocab' in t_low:
                section = 'vocab'
            elif 'part2' in t_low:
                section = 'part2'
            else:
                section = 'part1'
            in_condition = in_summary = in_example = False
            continue

        if section is None:
            # Part 마커 이전 단락은 무시
            continue

        # ── Part1 / Part2: 객관식 분류 (기존 _classify 재사용) ──
        if section in ('part1', 'part2'):
            # 레이블 정규화
            norm = _normalize_label(text)
            if norm != text:
                text = norm

            typ = _classify(text, in_condition)
            if typ == 'passage' and in_summary:
                typ = 'summary_content'
            elif typ == 'passage' and in_example:
                if '/' in text or ',' in text or '，' in text:
                    typ = 'example_content'
                in_example = False

            if typ == 'summary_label':
                in_summary = True; in_example = False; in_condition = False
            elif typ == 'example_label':
                in_example = True; in_summary = False; in_condition = False
            elif typ == 'condition':
                in_condition = True; in_summary = False; in_example = False
            elif typ in ('problem', 'passage_header', 'next_question',
                         'choice', 'answer_blank'):
                in_condition = False; in_summary = False; in_example = False

            if typ == 'blank':
                continue

            final_text, final_runs = text, runs
            if typ == 'problem':
                final_text, final_runs = _strip_inline_answer(text, runs)

            if final_text:
                parts[section].append({
                    'text': final_text,
                    'type': typ,
                    'runs': final_runs,
                })
            continue

        # ── Part1 어휘 영역 ──
        # 본문 마커 <본문 N>
        if _RE_PASSAGE_MARKER.match(text):
            m = re.search(r'\d+', text)
            vocab_passage_no = int(m.group()) if m else (vocab_passage_no + 1)
            start_new_passage(f'본문 {vocab_passage_no}')
            continue

        # 본문 마커가 없는 상태에서 영어 본문이 시작되면 자동 분리
        # (영어로만 된 줄 + 직전이 어휘 단락) → 새 passage
        # 단, 본 passage가 시작되지 않았으면 강제로 시작
        if vocab_passage_paras is None:
            vocab_passage_no += 1
            start_new_passage(f'본문 {vocab_passage_no}')

        # 카테고리 마커
        if _RE_CATEGORY.match(text):
            if '연관' in text:
                vocab_in_category = 'vocab'
            elif '영영' in text:
                vocab_in_category = 'english_def'
            elif '속담' in text:
                vocab_in_category = 'saying'
            vocab_passage_paras.append({
                'text': text, 'type': 'category', 'runs': runs,
            })
            continue

        # 동의어:/반의어: 줄은 헤더 없어도 vocab 모드 강제 진입
        if text.startswith('동의어:') or text.startswith('반의어:'):
            vocab_in_category = 'vocab'
            vocab_passage_paras.append({
                'text': text, 'type': 'vocab', 'runs': runs,
            })
            continue

        # "단어(품사): 영어 정의" → 영영풀이 자동 인식
        if re.match(r'^[A-Za-z][\w\s\-]*\([^)]+\):\s+[A-Za-z]', text):
            vocab_in_category = 'english_def'
            vocab_passage_paras.append({
                'text': text, 'type': 'english_def', 'runs': runs,
            })
            continue

        # 카테고리 헤더 없는 상태 (vocab_in_category is None)
        if vocab_in_category is None:
            # 영어로만 된 줄 → passage_text (영어 본문)
            if _is_english_line(text):
                vocab_passage_paras.append({
                    'text': text, 'type': 'passage_text', 'runs': runs,
                })
                continue
            # 짧은 줄 + 영어+한글 혼합 = 표제어 추정 (헤더 없이도 vocab 모드 진입)
            if (len(text) < 60
                    and re.search(r'[A-Za-z]', text)
                    and re.search(r'[가-힣]', text)):
                vocab_in_category = 'vocab'
                vocab_passage_paras.append({
                    'text': text, 'type': 'vocab', 'runs': runs,
                })
                continue
            # 그 외 (한글만 등) → passage_text
            vocab_passage_paras.append({
                'text': text, 'type': 'passage_text', 'runs': runs,
            })
            continue

        # vocab 모드 진행 중 + 긴 영어 줄 = 새 본문 시작 (마커 없는 경우 자동 분리)
        if vocab_in_category == 'vocab' and _is_english_line(text) and len(text) > 50:
            vocab_passage_no += 1
            start_new_passage(f'본문 {vocab_passage_no}')
            vocab_passage_paras.append({
                'text': text, 'type': 'passage_text', 'runs': runs,
            })
            continue

        # 카테고리별 분류
        if vocab_in_category == 'vocab':
            typ = 'vocab'
        elif vocab_in_category == 'english_def':
            typ = 'english_def'
        elif vocab_in_category == 'saying':
            typ = 'saying'
        else:
            typ = 'passage_text'

        vocab_passage_paras.append({
            'text': text, 'type': typ, 'runs': runs,
        })

    return parts


# ── 공개 API ────────────────────────────────────────────────────────────────

def parse_hwpx(hwpx_path: str) -> dict:
    """hwpx 파일 경로 → 양식별 dict 반환.
    Day 양식: {'format': 'day', 'days': [...]}
    Part 양식: {'format': 'part', 'parts': {...}}
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

    paras = _parse_paragraphs(section_xml, header_xml)
    fmt = detect_format(paras)
    if fmt == 'part':
        return {'format': 'part', 'parts': _split_into_parts(paras)}
    return {'format': 'day', 'days': _split_into_days(paras)}


def parse_docx(docx_path: str) -> dict:
    """docx 파일 경로 → 양식별 dict 반환."""
    paras = _parse_docx_paragraphs(docx_path)
    fmt = detect_format(paras)
    if fmt == 'part':
        return {'format': 'part', 'parts': _split_into_parts(paras)}
    return {'format': 'day', 'days': _split_into_days(paras)}


def parse_manuscript(path: str) -> dict:
    """원고 파일(hwpx/docx) → 양식별 dict. 확장자 자동 분기."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.docx':
        return parse_docx(path)
    return parse_hwpx(path)


def parse_answers_docx(docx_path: str) -> list:
    """정답 docx → [{'num', 'answer', 'explanation'}]."""
    lines = _extract_docx_lines(docx_path)
    return _parse_answer_lines(lines)


def parse_answers(path: str) -> list:
    """정답 파일(hwpx/hwp/docx) → 정답 목록. 확장자 자동 분기."""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.docx':
        return parse_answers_docx(path)
    return parse_answers_hwp(path)


def main():
    """CLI: python3 parser.py output.json input.hwpx [input2.hwpx ...]"""
    if len(sys.argv) < 3:
        print("사용법: python3 parser.py <output.json> <input.hwpx> [...]")
        sys.exit(1)

    output_path = sys.argv[1]
    hwpx_files = sys.argv[2:]

    all_days = []
    for hwpx_path in hwpx_files:
        print(f"[파서] 파싱 중: {hwpx_path}")
        data = parse_hwpx(hwpx_path)
        all_days.extend(data['days'])
        total = sum(len(d['paragraphs']) for d in data['days'])
        print(f"[파서] → {len(data['days'])}개 Day, {total}개 단락")

    result = {'days': all_days}
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_paras = sum(len(d['paragraphs']) for d in all_days)
    print(f"[파서] 완료: {len(all_days)}개 Day, {total_paras}개 단락 → {output_path}")


if __name__ == '__main__':
    main()
