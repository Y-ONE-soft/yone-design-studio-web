"""
화이트북 실전문제(문제형) 파서.

원고 (Day별 25문항):
  - '화이트북NN DayA~B 문제.docx'
  - '화이트북NN DayA~B 정답.docx'

출력 content.json:
  {
    "problem_days": [ {"day":1, "lines":[{"sty":"문제","text":"..."}, ...]}, ... ],
    "answer_days":  [ {"day":1, "lines":[{"sty":"정답_문제 번호"|"해설_시작"|"해설_","text":"..."}, ...]}, ... ]
  }

밑줄(<w:u>)은 <u>...</u> 마커로 보존 → JSX의 GREP이 '밑줄' 문자스타일을 적용.
sty는 짧은 키('문제','보기','선지','지문','정답_문제 번호','해설_시작','해설_')로 출력하고,
실제 InDesign 단락스타일(독해/문제 등) 매핑은 run.jsx가 담당한다.
"""
import re
import sys
import json
import xml.etree.ElementTree as ET
import zipfile

_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

_DAY_RE    = re.compile(r'^Day\s*(\d+)', re.I)
_Q_RE      = re.compile(r'^\((\d+)\)\s*(.*)$')
_CIRCLED   = '①②③④⑤⑥⑦⑧⑨⑩'
_ANS_RE    = re.compile(r'^([①②③④⑤⑥⑦⑧⑨⑩](?:\s*,\s*[①②③④⑤⑥⑦⑧⑨⑩])*)')


def _extract_paragraphs(docx_path):
    """단락별 텍스트. 밑줄 run은 <u>..</u>로 감쌈."""
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read('word/document.xml')
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(_W + 'p'):
        parts = []
        for r in p.iter(_W + 'r'):
            rpr = r.find(_W + 'rPr')
            has_u = False
            if rpr is not None:
                u = rpr.find(_W + 'u')
                if u is not None and u.get(_W + 'val') != 'none':
                    has_u = True
            txt = ''.join(t.text or '' for t in r.iter(_W + 't'))
            if not txt:
                continue
            parts.append('<u>' + txt + '</u>' if has_u else txt)
        text = ''.join(parts).replace('</u><u>', '')   # 분할된 인접 밑줄 run 병합
        paras.append(text)
    return paras


def _strip_u(s):
    return re.sub(r'</?u>', '', s)


def _normalize(s):
    # ∙(U+2219)/•(U+2022) → ·(U+00B7): 완성본 보기 기호와 통일
    return s.replace('∙', '·').replace('•', '·')


def _classify_problem(bare):
    if _Q_RE.match(bare):
        return '문제'
    if bare.startswith('<보기>'):
        return '보기'
    if bare[:1] in '∙·•':       # ∙ · •
        return '보기'
    if bare[:1] in _CIRCLED:
        return '선지'
    if bare.startswith('→'):               # → (영작 영어줄)
        return '선지'
    return '지문'                               # 장문 지문 등


def parse_problem_docx(path):
    days, cur = [], None
    for raw in _extract_paragraphs(path):
        t = raw.strip()
        if not t:
            continue
        bare = _strip_u(t).strip()
        dm = _DAY_RE.match(bare)
        if dm:
            cur = {'day': int(dm.group(1)), 'lines': []}
            days.append(cur)
            continue
        if cur is None:
            continue                            # 표지/제목
        cur['lines'].append({'sty': _classify_problem(bare), 'text': _normalize(t)})
    return days


def parse_answer_docx(path):
    days, cur = [], None
    for raw in _extract_paragraphs(path):
        t = raw.strip()
        if not t:
            continue
        bare = _strip_u(t).strip()
        dm = _DAY_RE.match(bare)
        if dm:
            cur = {'day': int(dm.group(1)), 'lines': []}
            days.append(cur)
            continue
        if cur is None or bare == '해설':
            continue
        qm = _Q_RE.match(bare)
        if qm:
            num, rest = qm.group(1), qm.group(2).strip()
            am = _ANS_RE.match(rest)
            answer = am.group(1) if am else ''
            after = rest[am.end():].strip() if am else rest
            after = re.sub(r'^\[[^\]]*\]\s*', '', after)     # [유형] 메타태그 제거
            cur['lines'].append({'sty': '정답_문제 번호',
                                 'text': _normalize('(%s)  [정답] %s' % (num, answer))})
            if after:
                cur['lines'].append({'sty': '해설_시작', 'text': _normalize('[해설] ' + after)})
        else:
            # 추가 해설 줄 (∙ 예문 해석 / ①~⑤ 오답 해석 / 뜻: / 지문 해석:)
            cur['lines'].append({'sty': '해설_', 'text': _normalize(t)})
    return days


def run(problem_path, answer_path, out_json):
    data = {
        'problem_days': parse_problem_docx(problem_path),
        'answer_days': parse_answer_docx(answer_path) if answer_path else [],
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: parser.py <문제.docx> [정답.docx] <out.json>')
        sys.exit(1)
    problem = sys.argv[1]
    answer = sys.argv[2] if len(sys.argv) > 3 else None
    out = sys.argv[-1]
    d = run(problem, answer, out)
    pd, ad = d['problem_days'], d['answer_days']
    print('problem days:', len(pd))
    for x in pd:
        nq = sum(1 for ln in x['lines'] if ln['sty'] == '문제')
        print('  Day %-2d  lines=%-4d  문항=%d' % (x['day'], len(x['lines']), nq))
    print('answer days:', len(ad))
    for x in ad:
        nq = sum(1 for ln in x['lines'] if ln['sty'] == '정답_문제 번호')
        print('  Day %-2d  lines=%-4d  정답=%d' % (x['day'], len(x['lines']), nq))
