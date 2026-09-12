"""세서특필 원고(docx 3종) → data.json.

원고는 **스타일 없는 docx** 다(단락 스타일 0개, 표 0개). 그래서 구조 신호는
글자 모양이 아니라 **자리와 표식**이다. 표식을 모르는 단락이 나오면 조용히 버리지
않고 게이트로 세운다 — 원고가 조금만 바뀌어도 여기서 멈추게 하는 것이 목적이다.

## Part 1 (구문 특강 · 중요문장)
  · 출처     = 색 1F3B73 굵은 단락           `올림포스 영어독해 기본2 1강 분석`
  · 문장     = `{…}` 로 감싼 단락            영어 문장(한 단락에 두 문장일 수도)
  · 해석     = 문장 바로 다음 단락(색 444444)
  · 포인트   = 색 B03030 `[라벨]` → `<구문>` → 설명 단락(들)
  · 묶음     = 출처에서 **도출**(올림포스 / 모의고사 / 교과서) — 원고에는 없다.
               완성본(26-1 기말)의 `> 올림포스 11강 ~ 16강` 띠를 재현한다.

## Part 2 (광문고 기출 서술형 실전문제)
  · 4줄 요약 → 대표유형 NN(▷ 유형 설명 · 💡 3단계 · 🔥 필승법 · 문제 · [정답] ·
    해설 · 오답 주의) → 지문 세트(`<출처>` · `↳ 출제 이력` · `[a~b] 발문` · 지문 ·
    문항 `N.`)
  · 문항 몸체 = 발문 종류로 가른다(찾아쓰기 · 물음 단답 · 요약문 · 어법 · 도식 · 사례)

## 정답 및 해설
  · `■ [a~b] 출처` → `N. 정답` → `해설 N) …` → `지문 해석 …`

## 어법 고치기의 밑줄
원고에 밑줄 서식이 **없다**(run 의 `w:u` 0개). 그런데 어법 고치기는 밑줄이 곧
문제다. 그래서 `(a) came` 의 밑줄 범위를 **해설에서 되짚는다** — 해설은 반드시
틀린 말을 그대로 인용한다(`came을 현재분사 coming으로`). 표식 뒤 1~6 어절 중
해설에 그대로 나오는 가장 긴 것을 밑줄로 삼고, 못 찾으면 원문 지문과 대조하고,
그래도 못 찾으면 한 어절로 두되 **경고로 세운다**.
"""
import difflib
import json
import os
import re
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_OFF = ('0', 'false', 'off', 'none')


# ---------------------------------------------------------------- docx 읽기

def _on(el):
    return el is not None and (el.get(W + 'val') or 'true').lower() not in _OFF


def read_paras(path):
    """본문 단락을 순서대로 — [{text, segs:[(글자, 굵게, 색)], color}]."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    body = root.find(W + 'body')
    if body.find(W + 'tbl') is not None:
        raise ValueError(f"표가 있는 원고는 이 계열이 모른다: {os.path.basename(path)}")
    out = []
    for p in body.iter(W + 'p'):
        segs = []
        for r in p.iter(W + 'r'):
            rp = r.find(W + 'rPr')
            b, color = False, ''
            if rp is not None:
                b = _on(rp.find(W + 'b'))
                ce = rp.find(W + 'color')
                if ce is not None:
                    color = (ce.get(W + 'val') or '').upper()
            t = ''
            for ch in r:
                if ch.tag == W + 't':
                    t += ch.text or ''
                elif ch.tag == W + 'tab':
                    t += ' '
                elif ch.tag in (W + 'br', W + 'cr'):
                    t += ' '
            if t:
                segs.append((t, b, color))
        text = ''.join(s[0] for s in segs).replace(' ', ' ').strip()
        if not text:
            continue
        colors = {}
        for t, _b, c in segs:
            colors[c] = colors.get(c, 0) + len(t.strip())
        out.append({'text': text, 'segs': segs,
                    'color': max(colors, key=colors.get) if colors else ''})
    return out


def rich(p):
    """단락 → 서식 조각. 굵게만 옮긴다(색은 원고 사정이고 조판 색은 테마가 정한다)."""
    out = []
    for t, b, _c in p['segs']:
        t = t.replace(' ', ' ')
        f = {'b': 1} if b else {}
        if out and isinstance(out[-1], dict) and {k: v for k, v in out[-1].items()
                                                    if k != 't'} == f:
            out[-1]['t'] += t
        else:
            out.append(dict(f, t=t))
    # 앞뒤 공백 정리 + 서식 없는 조각은 문자열로
    if out:
        out[0]['t'] = out[0]['t'].lstrip()
        out[-1]['t'] = out[-1]['t'].rstrip()
    return [o['t'] if len(o) == 1 else o for o in out if o['t']]


def plain(x):
    if x is None:
        return ''
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get('t', '')
    return ''.join(plain(i) for i in x)


# ---------------------------------------------------------------- Part 1

RE_SENT = re.compile(r'^\{(.+)\}$', re.S)
RE_LABEL = re.compile(r'^\[(.+)\]$')
RE_PAT = re.compile(r'^<.+>$', re.S)
SRC_COLOR = '1F3B73'
LABEL_COLOR = 'B03030'
KO_COLOR = '444444'


def group_of(src):
    """출처 → (묶음 종류, 묶음 열쇠, 강 번호). 원고에 없는 묶음 띠를 여기서 만든다."""
    m = re.match(r'^올림포스\s*(?:영어독해\s*)?(?:기본\s*\d\s*)?(\d+)\s*강', src)
    if m:
        return '올림포스', '올림포스', int(m.group(1))
    m = re.match(r'^(고\d)\s*(\d+\s*년\s*\d+\s*월)', src)
    if m:
        return '모의고사', f'{m.group(1)} {m.group(2)}', None
    m = re.match(r'^(\S+)\s+(공통영어\s*\d)\s+(.+?)\s*본문\s*\d+', src)
    if m:
        return '교과서', f'{m.group(2)} {m.group(1)} {m.group(3)}', None
    return None, src, None


def parse_part1(paras, bad):
    items, skipped = [], []
    started, want_ko, pt = False, False, None
    for p in paras:
        t = p['text']
        if p['color'] == SRC_COLOR and not RE_SENT.match(t):
            started, want_ko, pt = True, False, None
            items.append({'t': 'src', 'r': t})
            continue
        if not started:
            skipped.append(t)
            continue
        m = RE_SENT.match(t)
        if m:
            if want_ko:
                bad.append(('P1', '해석 없는 문장', items[-1]['en'][:40]))
            items.append({'t': 'sent', 'en': m.group(1).strip(), 'ko': ''})
            want_ko, pt = True, None
            continue
        if want_ko:
            if p['color'] != KO_COLOR:
                bad.append(('P1', '문장 다음이 해석(444444)이 아니다', t[:40]))
            items[-1]['ko'] = t
            want_ko = False
            continue
        m = RE_LABEL.match(t)
        if m and p['color'] == LABEL_COLOR:
            pt = {'t': 'pt', 'label': m.group(1).strip(), 'pat': '', 'exp': []}
            items.append(pt)
            continue
        if pt is not None and RE_PAT.match(t) and not pt['pat'] and not pt['exp']:
            pt['pat'] = t
            continue
        if pt is not None:
            pt['exp'].append(rich(p))
            continue
        bad.append(('P1', '소속 없는 단락', t[:50]))

    # 게이트 — 포인트는 라벨·구문·설명이 다 있어야 한다
    for it in items:
        if it['t'] == 'pt' and (not it['pat'] or not it['exp']):
            bad.append(('P1', '포인트 결손(구문/설명)', it['label']))
        if it['t'] == 'sent' and not it['ko']:
            bad.append(('P1', '해석 없는 문장', it['en'][:40]))

    # 묶음 띠 — 연속된 같은 종류의 출처를 한 띠로
    out, run = [], None
    for it in items:
        if it['t'] == 'src':
            kind, key, no = group_of(it['r'])
            if run is None or (kind, key) != (run['kind'], run['key']):
                run = {'t': 'group', 'kind': kind or '', 'key': key, 'nos': []}
                out.append(run)
            if no is not None:
                run['nos'].append(no)
        out.append(it)
    for g in out:
        if g['t'] != 'group':
            continue
        if g['kind'] == '올림포스' and g['nos']:
            lo, hi = min(g['nos']), max(g['nos'])
            g['rest'] = f'{lo}강' if lo == hi else f'{lo}강 ~ {hi}강'
        elif g['kind']:
            g['rest'] = g['key']
        else:
            g['rest'] = g['key']
        del g['nos']
    return {'items': out, 'skipped': skipped}


# ---------------------------------------------------------------- Part 2

RE_SETSRC = re.compile(r'^<\s*([^<>]+?)\s*>\s*(<\s*광문고\s*기출\s*>)?\s*$')
RE_HIST = re.compile(r'^↳\s*광문고\s*기출\s*출제\s*이력\s*[:：]\s*(.+)$')
RE_RANGE = re.compile(r'^\[\s*(\d+)\s*~\s*(\d+)\s*\]\s*(.+)$')
RE_Q = re.compile(r'^(\d{1,3})(?:\s*[-–]\s*(\d{1,2}))?\s*[.．]\s+(.+)$')
# 광문2(고2) 원고 방언 — 한 지문에 딸린 문항이 `1-1.` `1-2.` 로 갈린다.
# 정답지는 base 번호 하나로 묶어 준다(`1. (A)… / (C)…`).
RE_SAME = re.compile(r'^※\s*지문은\s*위와\s*동일')
RE_ANSLINE = re.compile(r'^(\(\s*\)|→|[ⓐ-ⓩ])\s*_{3,}')
RE_SUB = re.compile(r'^\(([a-h])\)\s')
RE_LAB = re.compile(r'^\[([A-Z])\]$')
RE_BRACKET = re.compile(r'^\[(.+)\]$')
RE_ARROW = re.compile(r'^\s*→\s*(.+)$')
RE_TAG = re.compile(r'\s*\[\s*(\d{4}\s*년[^\[\]]*)\]\s*')
RE_TYPE = re.compile(r'^대표유형\s*(\d+)\s*[:：]\s*(.+)$')
RE_STEP = re.compile(r'^Step\s*(\d+)\s*[.．]\s*(.+)$', re.I)
RE_EMOJI = re.compile(r'^[\U0001F300-\U0001FAFF☀-➿️]+\s*')
# 광문2(고2) 원고는 영어 발문 문항에서 보기 상자를 `< Word Bank >` 로 쓴다
BOGI = ('<보기>', '〈보기〉', '<WordBank>', '〈WordBank〉')
SUMMARY = ('〈요약문〉', '<요약문>')


def tagword(t):
    """표식 단락을 사이 공백 없이 — 광문2 원고는 `< 보 기 >` 처럼 벌려 쓴다."""
    return re.sub(r'\s+', '', t)


def setsrc(t):
    """세트 출처 `<…>` 인가 — `<보기>`·`<요약문>` 도 꺾쇠라 따로 뺀다.
    광문2 원고는 `< 보 기 >` 로 벌려 쓰므로 공백을 지운 꼴로 견준다."""
    if tagword(t) in BOGI or tagword(t) in SUMMARY:
        return None
    return RE_SETSRC.match(t)


def is_passage(t):
    """영문 지문 단락인가 — 길고, 라틴 문자가 대부분."""
    if len(t) < 60:
        return False
    lat = sum(1 for c in t if 'A' <= c <= 'z')
    han = sum(1 for c in t if '가' <= c <= '힣')
    return lat > 3 * han


def qkind(stem):
    if '밑줄' in stem and '고치' in stem:
        return 'grammar'
    # 광문2(고2) 방언 — `다음 ①~⑤ 중, 어법상 틀린 곳이 있는 문장을 …`
    if '어법' in stem and ('틀린' in stem or '고치' in stem):
        return 'grammar'
    # 배열영작 — 주어진 낱말을 모두 써서 문장을 완성
    if '주어진 단어' in stem and '완성' in stem:
        return 'arrange'
    if 'Word Bank' in stem or 'ONE word from the passage' in stem:
        return 'fill'
    if '요약' in stem:
        return 'summary'
    if '도식' in stem:
        return 'diagram'
    if '사례' in stem:
        return 'case'
    if '물음에' in stem and '답' in stem:
        return 'qa'
    if '빈칸' in stem:
        return 'fill'
    return 'other'


def split_stem(stem):
    """발문 → (발문, 시험 표기). `[2026년 광문고 … 중간고사]` 꼬리를 뗀다."""
    tag = ''
    m = RE_TAG.search(stem)
    if m:
        tag = m.group(1).strip()
        stem = (stem[:m.start()] + ' ' + stem[m.end():]).strip()
    return re.sub(r'\s{2,}', ' ', stem), tag


def qnext(t, base):
    """다음 문항 머리인가 — 인쇄 번호가 base+1 이거나, base 의 하위 번호(1-2)."""
    m = RE_Q.match(t)
    if not m:
        return False
    num = int(m.group(1))
    return num == base + 1 or (num == base and m.group(2))


def parse_qbody(stem, lines, bad, where, allow_passage=False):
    """문항 몸체 → 블록 목록."""
    kind = qkind(stem)
    blocks, i = [], 0
    while i < len(lines):
        t = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        w = tagword(t)
        if RE_SAME.match(t):                     # ※ 지문은 위와 동일 (광문2)
            blocks.append({'t': 'same', 'r': t.lstrip('※').strip()})
            i += 1
            continue
        if RE_ANSLINE.match(t):                  # (   ) ____ → ____ / → ____
            blocks.append({'t': 'ans', 'r': t})
            i += 1
            continue
        if w in SUMMARY:
            if nxt is None:
                bad.append((where, '요약문 몸체 없음', t))
                break
            blocks.append({'t': 'summary', 'label': '요약문', 'r': nxt})
            i += 2
            continue
        if w in BOGI:
            if nxt is None:
                bad.append((where, '<보기> 몸체 없음', t))
                break
            blocks.append({'t': 'bogi', 'r': nxt,
                           'lab': t.strip().strip('<>〈〉').strip() or '보기'})
            i += 2
            continue
        m = RE_LAB.match(t)
        if m:
            if nxt is None:
                bad.append((where, f'{t} 몸체 없음', t))
                break
            blocks.append({'t': 'case', 'label': m.group(1), 'r': nxt})
            i += 2
            continue
        if kind == 'diagram' and RE_BRACKET.match(t):
            # 도식은 두 꼴이다 — 흐름(둘째 줄부터 `→` 로 시작)과 항목표(줄 안에
            # `항목 → 값`). 제목부터 <보기> 전까지가 모두 도식 칸이다.
            raw = []
            i += 1
            while i < len(lines):
                s = lines[i]
                if tagword(s) in BOGI or tagword(s) in SUMMARY or RE_LAB.match(s):
                    break
                raw.append(s)
                i += 1
            flow = len(raw) > 1 and all(RE_ARROW.match(s) for s in raw[1:])
            steps = [(RE_ARROW.match(s).group(1) if RE_ARROW.match(s) else s).strip()
                     for s in raw]
            if not steps:
                bad.append((where, '도식 칸 없음', t))
            blocks.append({'t': 'diagram', 'title': RE_BRACKET.match(t).group(1).strip(),
                           'steps': steps, 'flow': flow})
            continue
        if RE_SUB.match(t):
            blocks.append({'t': 'line', 'r': t})
            i += 1
            continue
        if is_passage(t):
            if kind == 'grammar':
                blocks.append({'t': 'grammar', 'r': t})
            elif allow_passage:
                blocks.append({'t': 'passage', 'r': t})
            else:
                bad.append((where, '문항 안의 모르는 영문 단락', t[:50]))
            i += 1
            continue
        bad.append((where, '문항 안의 모르는 단락', t[:60]))
        i += 1
    return kind, blocks


def parse_part2(paras, bad):
    L = [p['text'] for p in paras]
    i, n = 0, len(L)
    skipped = []
    while i < n and '4줄 요약' not in L[i]:
        skipped.append(L[i])
        i += 1
    if i >= n:
        bad.append(('P2', '4줄 요약 없음', ''))
        return {}
    summary = {'title': L[i].strip(), 'items': []}
    i += 1
    while i < n and re.match(r'^\d+\.\s', L[i]) and not RE_TYPE.match(L[i]):
        summary['items'].append(L[i])
        i += 1

    types = []
    while i < n and RE_TYPE.match(L[i]):
        m = RE_TYPE.match(L[i])
        ty = {'no': int(m.group(1)), 'title': m.group(2).strip(), 'kind': '', 'desc': [],
              'proc': '', 'steps': [], 'tip_title': '', 'tip': [], 'stem': '', 'tag': '',
              'blocks': [], 'answer': '', 'exp_title': '', 'exp': [], 'wrong_title': '',
              'wrong': []}
        where = f"대표유형{ty['no']:02d}"
        i += 1
        if i < n and L[i].startswith('▷'):
            ty['kind'] = L[i].lstrip('▷').strip()
            i += 1
        while i < n and not L[i].startswith('💡'):
            ty['desc'].append(L[i])
            i += 1
        if i < n:
            ty['proc'] = RE_EMOJI.sub('', L[i]).strip()
            i += 1
        while i < n and RE_STEP.match(L[i]):
            ms = RE_STEP.match(L[i])
            st = {'no': int(ms.group(1)), 'title': ms.group(2).strip(), 'body': []}
            i += 1
            while i < n and not RE_STEP.match(L[i]) and not L[i].startswith('🔥'):
                st['body'].append(L[i])
                i += 1
            ty['steps'].append(st)
        if i < n and L[i].startswith('🔥'):
            ty['tip_title'] = RE_EMOJI.sub('', L[i]).strip()
            i += 1
        while i < n and L[i] != '문제':
            ty['tip'].append(L[i])
            i += 1
        i += 1                                  # '문제'
        if i >= n:
            bad.append((where, '문제 없음', ''))
            break
        ty['stem'], ty['tag'] = split_stem(L[i])
        i += 1
        body = []
        while i < n and L[i] != '[정답]':
            body.append(L[i])
            i += 1
        ty['qkind'], ty['blocks'] = parse_qbody(ty['stem'], body, bad, where,
                                                allow_passage=True)
        i += 1                                  # '[정답]'
        if i < n:
            ty['answer'] = L[i]
            i += 1
        if i < n and '해설' in L[i] and len(L[i]) < 30:
            ty['exp_title'] = L[i].strip()
            i += 1
        while i < n and L[i] != '오답 주의':
            ty['exp'].append(L[i])
            i += 1
        if i < n:
            ty['wrong_title'] = L[i]
            i += 1
        while i < n and not RE_TYPE.match(L[i]) and not setsrc(L[i]):
            ty['wrong'].append(L[i])
            i += 1
        if len(ty['steps']) != 3:
            bad.append((where, f"3단계가 {len(ty['steps'])}개", ''))
        for k in ('kind', 'proc', 'tip_title', 'stem', 'answer', 'exp_title', 'wrong_title'):
            if not ty[k]:
                bad.append((where, f'{k} 없음', ''))
        types.append(ty)

    sets, qno, lastnum = [], 0, 0
    while i < n:
        m = setsrc(L[i])
        if not m:
            bad.append(('P2', '세트 밖 단락', L[i][:60]))
            i += 1
            continue
        s = {'src': m.group(1).strip(), 'gichul': bool(m.group(2)), 'hist': [],
             'lo': 0, 'hi': 0, 'lead': '', 'passages': [], 'qs': []}
        where = s['src']
        i += 1
        while i < n and RE_HIST.match(L[i]):
            s['hist'].append(RE_HIST.match(L[i]).group(1).strip())
            i += 1
        mr = RE_RANGE.match(L[i]) if i < n else None
        if not mr:
            bad.append((where, '[a~b] 발문 없음', L[i][:40] if i < n else ''))
            continue
        s['lo'], s['hi'], s['lead'] = int(mr.group(1)), int(mr.group(2)), mr.group(3).strip()
        i += 1
        # 광문2 원고는 **발문이 지문보다 먼저** 온다 — 그러면 지문이 문항 몸체로
        # 들어오므로 그때만 허용한다(광문1은 지문이 앞이라 지금 그대로 엄격하다).
        qallow = bool(i < n and qnext(L[i], lastnum))
        label = None
        base = lastnum          # 직전 문항의 인쇄 번호(하위 번호 잇기용)
        while i < n and not qnext(L[i], base):
            t = L[i]
            if RE_LAB.match(t):
                label = RE_LAB.match(t).group(1)
            elif is_passage(t) or t.startswith(('⟪', '《')):
                s['passages'].append({'label': label, 'r': t})
                label = None
            else:
                bad.append((where, '지문 자리의 모르는 단락', t[:60]))
            i += 1
        while i < n and qnext(L[i], base):
            mq = RE_Q.match(L[i])
            num = int(mq.group(1))
            sub = int(mq.group(2)) if mq.group(2) else None
            base = lastnum = num
            qno += 1
            stem, tag = split_stem(mq.group(3).strip())
            i += 1
            body = []
            while i < n and not setsrc(L[i]) and not qnext(L[i], base):
                body.append(L[i])
                i += 1
            lab = f'{num}-{sub}' if sub else f'{num}'
            kind, blocks = parse_qbody(stem, body, bad, f'{lab}번',
                                       allow_passage=qallow)
            s['qs'].append({'no': qno, 'num': num, 'sub': sub, 'lab': lab,
                            'stem': stem, 'tag': tag, 'kind': kind, 'blocks': blocks})
        if not s['passages'] and not any(
                b['t'] in ('passage', 'case') for q in s['qs'] for b in q['blocks']):
            bad.append((where, '지문 없음', ''))
        got = sorted({q['num'] for q in s['qs']})
        if got != list(range(s['lo'], s['hi'] + 1)):
            bad.append((where, f"문항 {got} ≠ 범위 {s['lo']}~{s['hi']}", ''))
        sets.append(s)
    return {'summary': summary, 'types': types, 'sets': sets, 'skipped': skipped}


# ---------------------------------------------------------------- 정답 및 해설

RE_AHEAD = re.compile(r'^■\s*\[\s*(\d+)\s*~\s*(\d+)\s*\]\s*(.+)$')
RE_AITEM = re.compile(r'^(\d{1,3})\.\s+(.+)$')
RE_AEXP = re.compile(r'^해설\s*(\d{1,3})\)\s*(.+)$')
RE_TRANS = re.compile(r'^지문\s*해석\s+(.+)$')


def parse_answers(paras, bad):
    out, skipped, cur = [], [], None
    for p in paras:
        t = p['text']
        m = RE_AHEAD.match(t)
        if m:
            cur = {'lo': int(m.group(1)), 'hi': int(m.group(2)), 'src': m.group(3).strip(),
                   'items': [], 'trans': ''}
            out.append(cur)
            continue
        if cur is None:
            skipped.append(t)
            continue
        m = RE_AEXP.match(t)
        if m:
            no = int(m.group(1))
            it = next((x for x in cur['items'] if x['no'] == no), None)
            if it is None:
                bad.append(('정답', f'해설 {no}) 의 정답 줄 없음', ''))
            else:
                it['exp'] = m.group(2).strip()
            continue
        m = RE_TRANS.match(t)
        if m:
            cur['trans'] = m.group(1).strip()
            continue
        m = RE_AITEM.match(t)
        if m:
            cur['items'].append({'no': int(m.group(1)), 'ans': m.group(2).strip(), 'exp': ''})
            continue
        bad.append(('정답', '모르는 단락', t[:60]))
    for s in out:
        got = [x['no'] for x in s['items']]
        if got != list(range(s['lo'], s['hi'] + 1)):
            bad.append(('정답', f"[{s['lo']}~{s['hi']}] 정답 번호 {got}", ''))
        for x in s['items']:
            if not x['exp']:
                bad.append(('정답', f"{x['no']}번 해설 없음", ''))
        if not s['trans']:
            bad.append(('정답', f"[{s['lo']}~{s['hi']}] 지문 해석 없음", ''))
    return {'sets': out, 'skipped': skipped}


# ---------------------------------------------------------------- 밑줄 되짚기

# 표식 두 꼴 — 광문1 `(a) `, 광문2 `①`(뒤 공백 없음)
RE_MARK = re.compile(r'\(([a-h])\)\s+|([\u2460-\u2473])\s*')
RE_MARKANY = r'\([a-h]\)|[\u2460-\u2473]'


def mark_key(m):
    return m.group(1) or m.group(2)
_PUNCT = ',.;:!?"\'“”‘’)('


def _clean(w):
    return w.strip(_PUNCT)


def _exp_segment(exp, mark):
    """해설에서 그 표식 부분만 — 다음 표식 전까지. 표식은 `(a)` 또는 `①`."""
    pat = r'\(' + mark + r'\)' if mark.isalpha() else re.escape(mark)
    segs = []
    for m in re.finditer(pat, exp):
        nxt = re.search(RE_MARKANY, exp[m.end():])
        segs.append(exp[m.end(): m.end() + (nxt.start() if nxt else len(exp))])
    return ' '.join(segs)


def _in_exp(phrase, seg):
    if not phrase:
        return False
    return re.search(r'(?<![A-Za-z])' + re.escape(phrase) + r'(?![A-Za-z])', seg,
                     re.I) is not None


def _diff_n(text, start, limit, orig):
    """원문 지문과 대조해 표식 뒤에서 **바뀐 어절 수**를 센다(해설로 못 찾을 때)."""
    if not orig:
        return 0
    before = RE_MARK.sub('', text[:start]).split()
    q = before + RE_MARK.sub('', text[start:]).split()
    o = orig.split()
    k = len(before)
    sm = difflib.SequenceMatcher(a=[_clean(w).lower() for w in q],
                                 b=[_clean(w).lower() for w in o], autojunk=False)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ('replace', 'insert') and i1 <= k < i2:
            span = len(text[start:limit].split())
            return max(1, min(i2 - k, span))
    return 0


def underline(text, exp, orig=None, report=None):
    """어법 지문 → 서식 조각(밑줄). report 에 (표식, 밑줄, 방법) 을 쌓는다."""
    out, pos = [], 0
    marks = list(RE_MARK.finditer(text))
    for k, m in enumerate(marks):
        start = m.end()
        limit = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        words = list(re.finditer(r'\S+', text[start:limit]))
        if not words:
            continue
        seg = _exp_segment(exp or '', mark_key(m))
        best = 0
        for cnt in range(1, min(6, len(words)) + 1):
            phrase = ' '.join(_clean(w.group(0)) for w in words[:cnt])
            if _in_exp(phrase, seg):
                best = cnt
        how = '해설'
        if not best:
            best = _diff_n(text, start, limit, orig)
            how = '원문대조'
        if not best:
            best, how = 1, '한어절'
        end = start + words[best - 1].end()
        while end > start and text[end - 1] in _PUNCT:
            end -= 1
        if pos < start:
            out.append(text[pos:start])
        out.append({'t': text[start:end], 'u': 1})
        pos = end
        if report is not None:
            report.append((m.group(0).strip(), text[start:end], how))
    if pos < len(text):
        out.append(text[pos:])
    return out


# ---------------------------------------------------------------- 조립

def _nfc(s):
    return unicodedata.normalize('NFC', s)


def build(cfg, log=print):
    bad = []
    p1 = parse_part1(read_paras(cfg.manuscript('part1')), bad)
    p2 = parse_part2(read_paras(cfg.manuscript('part2')), bad)
    an = parse_answers(read_paras(cfg.manuscript('answers')), bad)

    # 정답 ↔ 문항 대조
    # 하위 번호(1-1·1-2)는 정답지에서 한 줄로 묶인다 — **인쇄 번호**로 견준다
    q_all = sorted({q['num'] for s in p2.get('sets', []) for q in s['qs']})
    a_all = [x['no'] for s in an['sets'] for x in s['items']]
    if q_all != a_all:
        bad.append(('정답', f'문항 번호 {len(q_all)}개 ≠ 정답 {len(a_all)}개', ''))
    ranges_q = [(s['lo'], s['hi']) for s in p2.get('sets', [])]
    ranges_a = [(s['lo'], s['hi']) for s in an['sets']]
    if ranges_q != ranges_a:
        bad.append(('정답', '세트 범위가 문항 쪽과 다르다', ''))
    src_warn = [(s['lo'], s['src'], a['src']) for s, a in zip(p2.get('sets', []), an['sets'])
                if _nfc(re.sub(r'\s', '', s['src'])) != _nfc(re.sub(r'\s', '', a['src']))]

    # 어법 밑줄 — 해설에서 되짚는다
    exp_of = {x['no']: x['exp'] for s in an['sets'] for x in s['items']}
    ul = []
    for ty in p2.get('types', []):
        exp = ' '.join(ty['exp']) + ' ' + ty['answer']
        for b in ty['blocks']:
            if b['t'] == 'grammar' and '밑줄' in ty['stem']:
                b['r'] = underline(b['r'], exp, None, ul)
    for s in p2.get('sets', []):
        orig = ' '.join(p['r'] for p in s['passages'])
        for q in s['qs']:
            for b in q['blocks']:
                # ⚠ 어법 문항은 두 꼴이다 — `밑줄 친 부분`(구를 밑줄)과
                #   `①~⑤ 중 … 문장을`(문장에 번호만). 뒤엣것은 밑줄이 없다.
                if b['t'] == 'grammar' and '밑줄' in q['stem']:
                    b['r'] = underline(b['r'], exp_of.get(q.get('num', q['no']), ''), orig, ul)
    how = {}
    for _m, _t, h in ul:
        how[h] = how.get(h, 0) + 1

    data = {
        'part1': p1['items'],
        'part2': {k: p2.get(k) for k in ('summary', 'types', 'sets')},
        'answers': an['sets'],
        'skipped': {'part1': p1['skipped'], 'part2': p2.get('skipped', []),
                    'answers': an['skipped']},
        'underlines': [list(x) for x in ul],
    }

    n_sent = sum(1 for x in p1['items'] if x['t'] == 'sent')
    n_pt = sum(1 for x in p1['items'] if x['t'] == 'pt')
    n_src = sum(1 for x in p1['items'] if x['t'] == 'src')
    kinds = {}
    for s in p2.get('sets', []):
        for q in s['qs']:
            kinds[q['kind']] = kinds.get(q['kind'], 0) + 1
    log(f"  Part 1: 출처 {n_src} · 문장 {n_sent} · 포인트 {n_pt} · 묶음 "
        f"{[g['kind'] + ' ' + g['rest'] for g in p1['items'] if g['t'] == 'group']}")
    log(f"  Part 2: 대표유형 {len(p2.get('types', []))} · 세트 {len(p2.get('sets', []))} · "
        f"문항 {len(q_all)} {kinds}")
    log(f"  정답: 세트 {len(an['sets'])} · 문항 {len(a_all)}")
    log(f"  어법 밑줄 {len(ul)}곳 · 되짚은 방법 {how}")
    for sk, v in data['skipped'].items():
        if v:
            log(f"  [원고 머리 — 조판 안 함] {sk}: {v}")
    for lo, a, b in src_warn:
        log(f"  [경고] {lo}번 세트 출처 표기가 문항/정답에서 다르다: {a!r} / {b!r}")
    if how.get('한어절'):
        for m_, t_, h_ in ul:
            if h_ == '한어절':
                log(f"  [경고] 밑줄 범위를 못 되짚어 한 어절로 둠: {m_} {t_}")
    if bad:
        for b in bad[:40]:
            log(f"  [인식 실패] {b}")
        raise ValueError(f"원고 인식 게이트 {len(bad)}건 — 조판하지 않는다")

    out = cfg.path('data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"  data.json → {out}")
    return data


def load(cfg):
    """data.json + 편집 이력(정오표). 원고를 다시 뽑아도 고친 글자가 살아남는다."""
    from core.render_vivlio import edits
    return edits.load_data(cfg)
