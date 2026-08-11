"""
화이트북 연습문제 / 연습문제 답지 docx 파서.

연습문제 문제 .docx 구조:
    제목
    (빈줄)
    (1) 발문…                ← 문제 시작
    <보기>                   ← 선택
    ∙ …                     ← 보기 라인
    ① …                     ← 선지
    ...

연습문제 답지 .docx 구조:
    제목
    ■ 해설
    (1) ④ [유형] …          ← 답 본문
      ① 해설 …               ← 해설 라인 (2-space 들여쓰기)
      ∙ 해설 …
    (2) …
    ...

밑줄(<w:u>) 은 본문 텍스트에 <u>...</u> 마커로 포함 → JSX에서 GREP으로 문자 스타일 적용.
"""

import re
import xml.etree.ElementTree as ET
import zipfile

_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

# 문제 헤더 — 형식이 아니라 구조로 인식: "(N) 발문" / "N. 발문" 모두 허용.
# "N." 형식은 본문 안 숫자("뜻: n. 1. 위도")와의 오인을 막기 위해
# 파서에서 연번(직전 문제 번호 +1) 검증을 함께 한다.
_QUESTION_HEAD_RE = re.compile(r'^\((\d+)\)\s+(.+)$')
_QUESTION_HEAD_DOT_RE = re.compile(r'^(\d+)\.\s+(.+)$')
_BOGI_RE          = re.compile(r'^[∙•]\s')                       # 보기 라인 시작
_CHOICE_RE        = re.compile(r'^[①②③④⑤⑥⑦⑧⑨⑩]\s')          # 선지 시작
_ARROW_RE         = re.compile(r'^→\s')                          # 영작 선지 답 라인
_BOGI_BLOCK_RE    = re.compile(r'^<보기>\s*$')


def _match_head(bare, expected_num):
    """문제/답 헤더 매칭 — (N)은 무조건, N.은 연번일 때만 (구조 검증).

    반환: 문제 번호(int) 또는 None."""
    m = _QUESTION_HEAD_RE.match(bare)
    if m:
        return int(m.group(1))
    m = _QUESTION_HEAD_DOT_RE.match(bare)
    if m and int(m.group(1)) == expected_num:
        return int(m.group(1))
    return None


def _extract_paragraphs(docx_path):
    """Word .docx에서 paragraph별로 (text, has_underline_map) 반환.
    has_underline run이 있을 때 그 부분을 <u>...</u> 로 감싸서 text에 포함.
    macOS Word의 ∙(U+2219)를 InDesign 본문 패턴 •(U+2022)로 정규화."""
    with zipfile.ZipFile(docx_path) as z:
        with z.open('word/document.xml') as f:
            xml = f.read()
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(_W + 'p'):
        parts = []
        for r in p.iter(_W + 'r'):
            rpr = r.find(_W + 'rPr')
            has_u = False
            if rpr is not None:
                u = rpr.find(_W + 'u')
                if u is not None:
                    val = u.get(_W + 'val')
                    if val != 'none':
                        has_u = True
            txt = ''
            for t in r.iter(_W + 't'):
                txt += (t.text or '')
            if not txt:
                continue
            # ∙ (U+2219) → • (U+2022) 정규화
            txt = txt.replace('∙', '•')
            if has_u:
                parts.append('<u>' + txt + '</u>')
            else:
                parts.append(txt)
        paras.append(''.join(parts))
    return paras


def _classify_problem_line(text):
    """문제 docx 한 줄의 단락 스타일을 추정한다."""
    bare = re.sub(r'<\/?u>', '', text).strip()
    if not bare:
        return None
    if _QUESTION_HEAD_RE.match(bare):
        return '문제'
    if _BOGI_BLOCK_RE.match(bare):
        return '보기'
    if _BOGI_RE.match(bare):
        return '보기'
    if _CHOICE_RE.match(bare):
        return '선지'
    if _ARROW_RE.match(bare):
        return '선지'   # 영작 유형: ① 우리말 다음 줄의 "→ 영문"
    # 기타 (보기 박스 마지막 줄: "① a    ② b ...") — 선지로 처리
    if re.search(r'[①②③④⑤]', bare):
        return '선지'
    return '문제'  # fallback


def parse_practice_docx(docx_path, log=None):
    """연습문제 본문 파싱.
    반환: [
      {'num': 1, 'lines': [{'sty': '문제', 'text': '...'}, ...]},
      ...
    ]

    배치 G (W37): log 콜백이 오면 침묵 유실을 가시화한다 — 문제 헤더
    '(N) ' 형식이 하나도 인식되지 않아 내용 전체가 버려지거나, 첫 문제
    앞에서 다수 라인이 무시되면 [경고] (동작 무변경, 로그만).
    """
    paras = _extract_paragraphs(docx_path)
    questions = []
    current = None
    dropped_head = []          # 첫 문제 인식 전 무시된 비어있지 않은 라인
    for raw in paras:
        text = raw.rstrip()
        if not text.strip():
            continue
        bare = re.sub(r'<\/?u>', '', text).strip()
        num = _match_head(bare, len(questions) + 1)
        if num is not None and not _is_choice_or_bogi_continuation(bare):
            # 새 문제 시작
            current = {'num': num, 'lines': []}
            questions.append(current)
            current['lines'].append({'sty': '문제', 'text': text})
            continue
        if current is None:
            # 제목 등 — 무시
            dropped_head.append(bare)
            continue
        sty = _classify_problem_line(text)
        if sty is None:
            continue
        current['lines'].append({'sty': sty, 'text': text})

    if log is not None:
        try:
            if not questions and dropped_head:
                log(f"[경고] 연습문제 파싱: 문제 헤더 '(N) '/'N. ' 미인식 — "
                    f"{len(dropped_head)}개 라인 전체가 무시됐습니다. "
                    f"첫 라인: {dropped_head[0][:50]!r}")
            elif len(dropped_head) > 2:   # 제목 1~2줄 초과 무시는 유실 의심
                log(f"[경고] 연습문제 파싱: 첫 문제 이전 {len(dropped_head)}개 "
                    f"라인 무시(제목 외 내용 유실 의심). "
                    f"예: {dropped_head[2][:50]!r}")
        except Exception:
            pass
    return questions


def _is_choice_or_bogi_continuation(line):
    return False  # placeholder — (N) 패턴은 항상 새 문제로


def parse_practice_answer_docx(docx_path, log=None):
    """연습문제 답지 파싱.
    반환: [
      {'num': 1, 'lines': [{'sty': '정답지 번호'|'해설_', 'text': '...'}, ...]},
      ...
    ]

    배치 G (W37): log 콜백이 오면 침묵 유실을 가시화 — '해설' 헤더 미발견
    (전 내용 무시) / 답 항목 0건을 [경고] (동작 무변경, 로그만).
    """
    paras = _extract_paragraphs(docx_path)
    answers = []
    started = False
    current = None
    for raw in paras:
        text = raw.rstrip()
        if not text.strip():
            continue
        bare = re.sub(r'<\/?u>', '', text)
        bare_strip = bare.strip()

        # 시작 신호는 구조로 인식: '■ 해설' 헤더 또는 첫 답 항목
        # ("(N) …"/"1. …") — 헤더 없는 신형식(제목 바로 다음 항목) 대응
        if not started:
            if '해설' in bare_strip:
                started = True
                continue
            if _match_head(bare_strip, 1) is not None:
                started = True          # 헤더 생략 형식 — 이 라인부터 항목
            else:
                continue

        num = _match_head(bare_strip, len(answers) + 1)
        if num is not None:
            current = {'num': num, 'lines': []}
            answers.append(current)
            current['lines'].append({'sty': '정답지 번호', 'text': text.strip()})
            continue
        if current is None:
            continue
        # 답 항목 아래 부속 라인(선지 해석·뜻·지문 해석 등)은 해설로
        current['lines'].append({'sty': '해설_', 'text': text})

    if log is not None:
        try:
            has_content = any(p.strip() for p in paras)
            if not started and has_content:
                log("[경고] 연습문제 답지 파싱: '해설' 헤더도 답 항목 "
                    "'(N) '/'N. ' 형식도 발견되지 않아 내용 전체가 무시됐습니다.")
            elif started and not answers and has_content:
                log("[경고] 연습문제 답지 파싱: 시작점 이후 답 항목 "
                    "'(N) '/'N. ' 형식이 하나도 인식되지 않았습니다.")
        except Exception:
            pass
    return answers


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 3:
        print('usage: practice_parser.py {q|a} <docx>')
        sys.exit(1)
    mode = sys.argv[1]
    path = sys.argv[2]
    if mode == 'q':
        print(json.dumps(parse_practice_docx(path), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(parse_practice_answer_docx(path), ensure_ascii=False, indent=2))
