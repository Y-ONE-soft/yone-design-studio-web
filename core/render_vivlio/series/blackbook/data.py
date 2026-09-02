"""블랙북 원고(docx) → data.json.

구조 인식 원칙(형식이 아니라 구조):
  · 문항 = `N.` 로 시작하고 번호가 직전 문항 +1 인 단락 (채점 기준의 `1.` 과 구분된다)
  · 지문 = 문항 안에서 발문·선지·보기·답란·채점기준 어느 것도 아닌 단락
  · 요약문 = `↓` 바로 다음 단락 (빈칸이 길어도 답란이 아니다)
  · 답란 = 밑줄(`____`)이 있고 밑줄 뺀 글자가 20자 이하인 줄, 또는 전용 스타일
  · 해설 = 번호 단독 줄 뒤의 `[정답]`/`[해석]`/`[해설]`
  · 연관어휘 = `<N과 본문M>` → 제목 → 지문 → `〈연관 어휘〉` → 표제어 / `동의어:` / `반의어:`

런 서식(밑줄·굵게·이탤릭)은 세그먼트로 보존한다 → 밑줄 친 어휘·어법 표시가 그대로
조판된다.

**인식 게이트**: 과별 문항 수 == 해설 수, 문항 번호 연속·문제/해설 일치, 본문마다
지문·어휘 ≥ 1, 정답 비어 있지 않음. 하나라도 어긋나면 조판하지 않고 중단한다.
"""
import json, os, re, unicodedata, zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩'

# ---------------------------------------------------------------- docx 읽기

_OFF = ('none', '0', 'false', 'off')


def _on(el):
    """서식 켜짐인가 — **있다/없다로 보면 안 된다.**

    한글에서 넘어온 docx 는 모든 런에 `<w:u w:val="none"/>` 를 붙여 놓는다.
    태그 유무로 판정하면 **문서 전체가 밑줄**이 된다(화이트북에서 실제로 겪었다).
    """
    return el is not None and (el.get(W + 'val') or 'true').lower() not in _OFF


def _runs(p):
    """단락 → [(text, flags)] 세그먼트. flags = {'b','u','i'} 부분집합."""
    segs = []
    for r in p.findall(W + 'r'):
        rpr = r.find(W + 'rPr')
        fl = set()
        if rpr is not None:
            if _on(rpr.find(W + 'b')):
                fl.add('b')
            if _on(rpr.find(W + 'u')):
                fl.add('u')
            if _on(rpr.find(W + 'i')):
                fl.add('i')
        buf = []
        for n in r:
            if n.tag == W + 't':
                buf.append(n.text or '')
            elif n.tag == W + 'tab':
                buf.append('\t')
            elif n.tag == W + 'br':
                buf.append('\n')
        t = ''.join(buf)
        if t:
            segs.append((t, fl))
    return segs


def read_paras(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read('word/document.xml'))
    out = []
    for p in root.find(W + 'body').iter(W + 'p'):
        st = p.find(f'{W}pPr/{W}pStyle')
        segs = _runs(p)
        out.append({'style': st.get(W + 'val') if st is not None else '',
                    'segs': segs,
                    'text': ''.join(s for s, _ in segs)})
    return out


def split_lines(segs):
    """세그먼트 목록을 '\n' 기준으로 여러 줄로 쪼갠다(서식 유지)."""
    lines, cur = [], []
    for t, fl in segs:
        parts = t.split('\n')
        for k, part in enumerate(parts):
            if k:
                lines.append(cur)
                cur = []
            if part:
                cur.append((part, fl))
    lines.append(cur)
    return [l for l in lines]


def rich(segs, strip_bold=False):
    """세그먼트 → JSON 직렬화용 리스트. 서식 없으면 문자열로 축약."""
    out = []
    for t, fl in segs:
        if not t:
            continue
        if fl and not (strip_bold and fl == {'b'}):
            d = {'t': t}
            for f in sorted(fl):
                d[f] = 1
            out.append(d)
        else:
            out.append(t)
    # 연속 문자열 병합
    merged = []
    for s in out:
        if isinstance(s, str) and merged and isinstance(merged[-1], str):
            merged[-1] += s
        else:
            merged.append(s)
    if len(merged) == 1 and isinstance(merged[0], str):
        return merged[0]
    return merged


def plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get('t', '')
    return ''.join(plain(i) for i in x)


def txt(segs):
    return ''.join(t for t, _ in segs)


def strip_lead(segs, n):
    """앞에서 n글자 제거(서식 유지)."""
    out, left = [], n
    for t, fl in segs:
        if left <= 0:
            out.append((t, fl))
        elif len(t) <= left:
            left -= len(t)
        else:
            out.append((t[left:], fl))
            left = 0
    # 앞 공백 정리
    while out and not out[0][0].strip():
        out.pop(0)
    if out:
        out[0] = (out[0][0].lstrip(), out[0][1])
    return out


# ---------------------------------------------------------------- 문제 파서

RE_ITEM = re.compile(r'^\s*(\d+)\.\s')
RE_CRIT = re.compile(r'^\s*(\d+)\.\s')
RE_BOGI = re.compile(r'^\s*[<〈]\s*보\s*기\s*[>〉]\s*$')
RE_BLANK = re.compile(r'_{4,}')


def _is_ansline(t, style):
    """답란인가 — 밑줄이 있고 밑줄 뺀 글자가 20자 이하이거나 전용 스타일"""
    return style == 'aa' or (
        bool(RE_BLANK.search(t)) and len(RE_BLANK.sub('', t).strip()) <= 20)


def parse_problems(path):
    paras = read_paras(path)
    header = ''
    for p in paras:
        if p['text'].strip():
            header = p['text'].strip()
            break

    items, cur, expect = [], None, None
    mode = None  # None | 'bogi' | 'crit'

    def push():
        if cur is not None:
            items.append(cur)

    for p in paras:
        t = p['text'].strip()
        if not t:
            continue
        m = RE_ITEM.match(t)
        n = int(m.group(1)) if m else None
        is_item = m is not None and (expect is None or n == expect) and n is not None
        if is_item and cur is not None and not cur['blocks']:
            is_item = False  # 발문 없는 헛번호 방지
        if m and expect is not None and n == expect:
            is_item = True
        if is_item:
            push()
            cur = {'no': n, 'stem': rich(strip_lead(p['segs'], m.end())),
                   'blocks': []}
            expect = n + 1
            mode = None
            continue
        if cur is None:
            continue  # 헤더 영역

        B = cur['blocks']
        if t == '↓':
            B.append({'t': 'arrow'})
            mode = None
        elif RE_BOGI.match(t):
            B.append({'t': 'bogi', 'items': []})
            mode = 'bogi'
        elif t.startswith('[채점 기준]') or t.startswith('[답안 작성 안내]'):
            B.append({'t': 'crit', 'title': t, 'items': []})
            mode = 'crit'
        elif t[0] in CIRCLED and sum(t.count(c) for c in CIRCLED) == 1:
            # ①로 **시작하는 지문**이 있다(어법 문제 — `①When writing a novel …`).
            # 선지는 원문자가 하나, 밑줄 친 지문은 ①~⑤가 한 단락 안에 다 있다.
            B.append({'t': 'choice', 'mark': t[0],
                      'body': rich(strip_lead(p['segs'], 1))})
            mode = None
        elif mode == 'bogi' and not _is_ansline(t, p['style']):
            # 보기 상자는 ①/답란/채점기준/다음 문항 전까지 이어진다
            # (빈칸이 든 마무리 줄·단어 묶음도 보기 안에 든다)
            B[-1]['items'].append(rich(p['segs']))
        elif mode == 'crit' and RE_CRIT.match(t):
            B[-1]['items'].append(rich(p['segs']))
        elif B and B[-1]['t'] == 'arrow':
            # 화살표 바로 뒤 = 요약문(빈칸이 길어도 답란이 아니다)
            B.append({'t': 'summary', 'paras': [rich(p['segs'])]})
            mode = None
        elif _is_ansline(t, p['style']):
            if B and B[-1]['t'] == 'ansline':
                B[-1]['lines'].append(rich(p['segs']))
            else:
                B.append({'t': 'ansline', 'lines': [rich(p['segs'])]})
            mode = None
        else:
            kind = 'summary' if (B and B[-1]['t'] == 'arrow') else 'passage'
            if kind == 'passage' and B and B[-1]['t'] == 'passage':
                B[-1]['paras'].append(rich(p['segs']))
            elif kind == 'summary' and B and B[-1]['t'] == 'summary':
                B[-1]['paras'].append(rich(p['segs']))
            else:
                B.append({'t': kind, 'paras': [rich(p['segs'])]})
            mode = None
    push()
    return header, items


# ---------------------------------------------------------------- 해설 파서

RE_ANSNO = re.compile(r'^\s*(\d+)\s*$')


def parse_answers(path):
    paras = read_paras(path)
    items, cur, expect, field = [], None, None, None
    for p in paras:
        t = p['text'].strip()
        if not t:
            continue
        m = RE_ANSNO.match(t)
        if m and (expect is None or int(m.group(1)) == expect):
            if cur:
                items.append(cur)
            cur = {'no': int(m.group(1)), 'answer': '', 'trans': [], 'expl': []}
            expect = cur['no'] + 1
            field = None
            continue
        if cur is None:
            continue
        if t.startswith('[정답]'):
            cur['answer'] = rich(strip_lead(p['segs'], t.index(']') + 1))
            field = 'answer'
        elif t.startswith('[해석]'):
            cur['trans'].append(rich(strip_lead(p['segs'], t.index(']') + 1)))
            field = 'trans'
        elif t.startswith('[해설]'):
            cur['expl'].append(rich(strip_lead(p['segs'], t.index(']') + 1)))
            field = 'expl'
        elif field in ('trans', 'expl'):
            cur[field].append(rich(p['segs']))
    if cur:
        items.append(cur)
    return items


# ---------------------------------------------------------------- 연관어휘 파서

# 지문 마커는 책마다 말이 다르다 — 교과서본은 `<1과 본문1>`, 모의고사본은 `<18번>`.
# 형식을 나열하지 말고 **꺾쇠 안에 숫자가 있는 한 줄**을 마커로 본다.
# 라벨은 원고가 쓴 말 그대로(꺾쇠만 벗겨) 쓴다 — 칩에 그대로 인쇄된다.
RE_UNIT = re.compile(r'^\s*[<〈]\s*((?=[^>〉]*\d)[^>〉]{1,20})\s*[>〉]\s*$')
RE_VOCA_HEAD = re.compile(r'^\s*[<〈]\s*연관\s*어휘\s*[>〉]\s*$')
RE_SYN = re.compile(r'^(동의어|반의어|유의어|참고)\s*:\s*')
# 표제어와 뜻의 경계 — 원고가 두 칸을 띄우기도, 한 칸만 띄우기도, 붙여 쓰기도 한다
# (`impressive  인상적인` / `appreciate 높이 평가하다` / `apply지원하다`).
RE_HEAD_SPLIT = re.compile(r'\s{2,}|(?=[가-힣])')


def _split_headword(t):
    """표제어 / 뜻 — 두 칸 띄움이 먼저면 그것, 아니면 첫 한글 앞에서 자른다."""
    m = RE_HEAD_SPLIT.search(t)
    if not m:
        return t.strip(), ''
    return t[:m.start()].strip(), t[m.end():].strip()


def parse_vocab(path, has_title=True):
    paras = read_paras(path)
    units, cur, state = [], None, None
    for p in paras:
        for line in split_lines(p['segs']):
            t = txt(line).strip()
            if not t:
                continue
            m = RE_UNIT.match(t)
            if m and not RE_VOCA_HEAD.match(t):
                if cur:
                    units.append(cur)
                label = re.sub(r'\s+', ' ', m.group(1)).strip()
                cur = {'label': label,
                       'title': '', 'paras': [], 'words': []}
                state = 'title' if has_title else 'body'
                continue
            if cur is None:
                continue
            if RE_VOCA_HEAD.match(t):
                state = 'voca'
                continue
            if state == 'title':
                cur['title'] = t
                state = 'body'
            elif state == 'body':
                cur['paras'].append(rich(line))
            elif state == 'voca':
                ms = RE_SYN.match(t)
                if ms and cur['words']:
                    cur['words'][-1]['rel'].append(
                        {'kind': ms.group(1),
                         'body': rich(strip_lead(line, ms.end()))})
                elif ms:
                    continue
                else:
                    head, mean = _split_headword(t)
                    cur['words'].append(
                        {'word': head, 'mean': mean, 'rel': []})
    if cur:
        units.append(cur)
    return units


# ---------------------------------------------------------------- 게이트

class GateError(Exception):
    pass


def gate(cond, msg):
    if not cond:
        raise GateError(msg)


# ---------------------------------------------------------------- main

def find(cfg, kind, lesson):
    """원고 파일 찾기 — 파일명 규칙은 config 의 `manuscript.pattern`.

    macOS 파일명은 NFD 로 저장되므로 **정규화해서** 비교해야 한다(한글이 안 잡힌다).
    """
    m = cfg.section("manuscript") or {}
    src = cfg.resolve(m.get("dir", "원고"))
    pattern = m.get("pattern", "{kind}_{lesson}.docx")
    want = unicodedata.normalize(
        'NFC', pattern.format(kind=kind, lesson=lesson))
    for f in os.listdir(src):
        if unicodedata.normalize('NFC', f) == want:
            return os.path.join(src, f)
    raise GateError(f'원고 없음: {want} (in {src})')


def build(cfg, log=print):
    """원고 → data.json. 게이트를 통과하지 못하면 조판하지 않고 중단한다."""
    m = cfg.section("manuscript") or {}
    lessons = m.get("lessons") or [1, 2]
    # 묶음 이름은 책마다 다르다 — 교과서본은 "1과", 모의고사본은 "18 ~ 22번".
    # `labels` 가 없으면 예전처럼 "{lesson}과".
    labels = m.get("labels") or [f"{L}과" for L in lessons]
    has_title = m.get("vocab_title", True)
    kinds = m.get("kinds") or {"problems": "문제", "vocab": "연관어휘",
                               "answers": "해설"}
    book = {"title": cfg.book.get("brand", ""), "lessons": []}
    n_prob = n_ans = 0
    for i, L in enumerate(lessons):
        lab = labels[i] if i < len(labels) else f"{L}과"
        hdr, items = parse_problems(find(cfg, kinds["problems"], L))
        vunits = parse_vocab(find(cfg, kinds["vocab"], L), has_title)
        ans = parse_answers(find(cfg, kinds["answers"], L))

        mt = re.search(r'Lesson\s*(\d+)\s*(.*)$', hdr)
        title = mt.group(2).strip() if mt else ''

        gate(len(items) >= 10, f'{lab} 문항 인식 실패({len(items)})')
        gate(len(ans) == len(items),
             f'{lab} 문항 {len(items)} vs 해설 {len(ans)} 불일치')
        nos_p = [i2['no'] for i2 in items]
        nos_a = [a['no'] for a in ans]
        gate(nos_p == nos_a, f'{lab} 문항 번호 불일치: {nos_p[:5]} vs {nos_a[:5]}')
        gate(nos_p == list(range(nos_p[0], nos_p[0] + len(nos_p))),
             f'{lab} 문항 번호 비연속')
        gate(len(vunits) >= 1, f'{lab} 연관어휘 본문 인식 실패')
        for u in vunits:
            gate(u['words'], f"{u['label']} 어휘 0개")
            gate(u['paras'], f"{u['label']} 지문 0개")
        for it in items:
            gate(any(b['t'] == 'passage' for b in it['blocks']),
                 f"{lab} {it['no']}번 지문 없음")
        for a in ans:
            gate(plain(a['answer']).strip(), f"{lab} {a['no']}번 정답 없음")

        book['lessons'].append({
            'lesson': L, 'label': lab, 'unit': f'{i + 1:02d}',
            'header': hdr, 'title': title,
            'vocab': vunits, 'problems': items, 'answers': ans,
        })
        n_prob += len(items)
        n_ans += len(ans)

    out = cfg.path('data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(book, f, ensure_ascii=False, indent=1)

    log('■ 인식 결과')
    for L in book['lessons']:
        log(f"  {L.get('label') or str(L['lesson']) + '과'}  {L['title']}")
        log(f"    연관어휘 본문 {len(L['vocab'])}개 / 표제어 "
            f"{sum(len(u['words']) for u in L['vocab'])}개")
        log(f"    문항 {len(L['problems'])}개 "
            f"({L['problems'][0]['no']}~{L['problems'][-1]['no']}) / "
            f"해설 {len(L['answers'])}개")
    log(f"  합계 문항 {n_prob} / 해설 {n_ans}  → {os.path.basename(out)}")
    return out


def load(cfg, log=None):
    """data.json + 정오표(errata.json).

    정오표를 **읽는 자리**에 얹어야 조판과 검수가 같은 글을 본다.
    """
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
