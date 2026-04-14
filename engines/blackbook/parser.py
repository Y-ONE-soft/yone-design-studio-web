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
import re
import sys
import zipfile


# ── header.xml: underline charPr ID 수집 ────────────────────────────────────

def _parse_underline_ids(header_xml: str) -> set:
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


# ── section0.xml: 단락 추출 ─────────────────────────────────────────────────

def _extract_segments(body: str, ul_ids: set) -> list:
    """
    <hp:run> 목록을 순회하며 (text, underline, new_para) 세그먼트 목록 반환.
    <hp:lineBreak/>는 새 단락 시작 신호로 처리.
    반환: [{"t": str, "ul": bool, "new_para": bool}]
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
    # in_condition 상태에서는 ①②③ 등을 choice보다 먼저 확인
    if in_condition and _is_condition_content(text):
        return 'condition_item'
    if _RE_CHOICE.match(text):
        return 'choice'
    if _RE_PROBLEM.match(text):
        return 'problem'
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


# ── 공개 API ────────────────────────────────────────────────────────────────

def parse_hwpx(hwpx_path: str) -> dict:
    """hwpx 파일 경로 → {"days": [...]} dict."""
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
    days = _split_into_days(paras)
    return {'days': days}


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
