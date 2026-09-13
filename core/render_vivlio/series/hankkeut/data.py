"""한끝 계열 원고(docx) → data.json.

원고 두 벌 (한서끝 26-2-중간 확정본, 2026-09-13):
  · 문제지     — 머리 몇 줄 + `[서답형 N] 발문  〈출처〉` 문항 N개(세트 없음, 파트 표지 없음)
  · 정답및풀이 — 빠른 정답 N줄 + 문항마다 `[서답형 N] 정답 …` / ▶ 지문 해석 / ▶ 풀이 방법 …

구조 인식(글자 모양이 아니라 자리로):
  문제지
  · 머리   = 첫 문항 앞 단락 — 굵은 줄(학교·제목) + 괄호 안 `이름 수 · 이름 수` 구성 줄 + `※` 범위 줄
  · 문항   = 굵게 시작하는 `[라벨 N]` 단락, N 이 직전 +1. 끝의 꺾쇠 `〈…〉` 는 출처,
             발문 마침표 뒤 괄호 덩어리는 안내(답안 작성 예)
  · 한 글자 화살표 줄(`↓`) 뒤 첫 단락 = 요약문
  · `[라벨]` 단독 줄(또는 `[라벨] 1. …`) = 목록 상자. 뒤따르는 `k.` 줄은 항목, `(` 줄은 꼬리.
    항목이 영문이면 보기 상자, 한글이면 조건 상자 — **라벨 이름으로 가르지 않는다**
  · `[라벨] a / b / c` = 단어 묶음(빗금으로 나눔)
  · `Q.` = 질문 줄 · `답 :` `답 →` `(  )번 :` `(  ) ___` = 답란
  · 지문 바로 뒤 `k.` 줄(상자 밖) = 배열 조각 · 첫 글자+띄운 밑줄이 있는 단락 = 요약문 · 나머지 = 지문
  정답및풀이
  · `N. [유형 · 출처]  답` = 빠른 정답
  · 굵은 `[라벨 N] 정답  답` = 문항 풀이 시작 · 굵은 `▶ 이름` = 절 · `│` 줄 = 표 행 · 굵은 `k.` = 풀이 단계

인식 게이트(하나라도 어긋나면 조판하지 않는다):
  문항 번호 연속 · 원고 머리의 유형 구성 == 구조 판정 · 문항마다 지문·답란·출처 ·
  요약문 글자 칸 벌 수 == 답란 첫 글자 수 · 빠른 정답/풀이 수·번호 == 문항 ·
  정답의 유형 이름 ⊇ 구조 판정 · 정답 출처 == 문제 출처 · 빠른 정답 == 풀이 머리 정답.
"""
import collections
import json
import os
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_OFF = ('none', '0', 'false', 'off')

# 구조 판정 유형 → 원고 머리 구성 줄의 이름
TYPE_SHORT = {'grammar': '어법', 'summary': '요약', 'ask': '내용 질문', 'match': '일치',
              'arrange': '배열', 'vocab': '낱말'}

RE_STEM = re.compile(r'^\[\s*([^\[\]\d]*?)\s*(\d{1,3})\s*\]\s*')
RE_SRC_TAIL = re.compile(r'\s*[〈<]\s*([^〈〉<>]+?)\s*[〉>]\s*$')
RE_STEM_NOTE = re.compile(r'([.?!])\s+(\(.*\))\s*$')
RE_ARROW = re.compile(r'^[↓⇓⬇]$')
RE_LABEL = re.compile(r'^\[\s*([^\[\]]{1,12}?)\s*\]\s*(.*)$')
RE_ITEM = re.compile(r'^(\d{1,2})\s*[.)]\s*(.*)$', re.S)
RE_ASK = re.compile(r'^Q\s*[.:]\s*(.+)$')
RE_ANS = re.compile(r'^(?:답\s*[:：→]|\(\s*\))')
RE_LETTER = re.compile(r'\b[A-Za-z](?:\s_){2,}')
RE_ANS_LETTER = re.compile(r'(?:^|[\s:：])[A-Za-z]\s+_{3,}')
RE_COMPOSE = re.compile(r'\(([^()]+)\)')
RE_LATIN = re.compile(r'[A-Za-z]')
RE_QUICK = re.compile(r'^(\d{1,3})\s*\.\s*\[\s*(.+?)\s*·\s*(.+?)\s*\]\s*(.+)$')
RE_AHEAD = re.compile(r'^\[\s*[^\[\]\d]*?\s*(\d{1,3})\s*\]\s*정답\s*')
RE_SEC = re.compile(r'^[▶►▸]\s*(.+)$')


# ---------------------------------------------------------------- docx 읽기

def _on(el):
    """서식 켜짐인가 — 태그 유무로 보면 안 된다(한글 docx 는 `w:u val=none` 을 전부 붙인다)."""
    return el is not None and (el.get(W + 'val') or 'true').lower() not in _OFF


def _runs(p):
    segs = []
    for r in p.iter(W + 'r'):
        rp = r.find(W + 'rPr')
        f = {}
        if rp is not None:
            for k in ('b', 'i', 'u'):
                if _on(rp.find(W + k)):
                    f[k] = 1
        t = ''
        for ch in r:
            if ch.tag == W + 't':
                t += ch.text or ''
            elif ch.tag == W + 'tab':
                t += '\t'
            elif ch.tag in (W + 'br', W + 'cr'):
                t += '\n'
        if not t:
            continue
        if segs and segs[-1][1] == f:
            segs[-1] = (segs[-1][0] + t, f)
        else:
            segs.append((t, f))
    return segs


def _split_lines(segs):
    """단락 안 줄바꿈(shift+enter)은 줄 경계다."""
    out, cur = [], []
    for t, f in segs:
        for k, s in enumerate(t.split('\n')):
            if k:
                out.append(cur)
                cur = []
            if s:
                cur.append((s, f))
    out.append(cur)
    return out


def read_body(path):
    """본문을 **순서대로** — 단락과 표를 섞어서."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    out = []
    for el in root.find(W + 'body'):
        if el.tag == W + 'p':
            for ln in _split_lines(_runs(el)):
                out.append(('p', ln))
        elif el.tag == W + 'tbl':
            rows = []
            for tr in el.findall(W + 'tr'):
                row = []
                for tc in tr.findall(W + 'tc'):
                    segs = []
                    for p in tc.findall(W + 'p'):
                        s = _runs(p)
                        if segs and s:
                            segs.append((' ', {}))
                        segs += s
                    row.append(segs)
                rows.append(row)
            out.append(('t', rows))
    return out


def plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get('t', '')
    if isinstance(x, (list, tuple)):
        if x and isinstance(x[0], tuple):
            return ''.join(t for t, _ in x)
        return ''.join(plain(i) for i in x)
    return ''


def rich(segs, drop_bold=False):
    out = []
    for t, f in segs:
        f = {k: v for k, v in f.items() if not (drop_bold and k == 'b')}
        if out and {k: v for k, v in out[-1].items() if k != 't'} == f:
            out[-1]['t'] += t
        else:
            d = {'t': t}
            d.update(f)
            out.append(d)
    if all(len(d) == 1 for d in out):
        return ''.join(d['t'] for d in out).strip()
    out[0]['t'] = out[0]['t'].lstrip()
    out[-1]['t'] = out[-1]['t'].rstrip()
    return [d for d in out if d['t']]


def cut(segs, a, b=None):
    """세그먼트 목록을 글자 위치 [a, b) 로 자른다 — 서식(밑줄·굵게)을 살린 채."""
    out, pos = [], 0
    for t, f in segs:
        s, e = pos, pos + len(t)
        pos = e
        lo, hi = max(a, s), (e if b is None else min(b, e))
        if lo < hi:
            out.append((t[lo - s:hi - s], f))
    return out


def _lead(segs):
    s = plain(segs)
    return len(s) - len(s.lstrip())


def _bold0(segs):
    for t, f in segs:
        if t.strip():
            return bool(f.get('b'))
    return False


def _norm(s):
    return re.sub(r'\s+', '', s or '')


# ---------------------------------------------------------------- 문제지

def parse_head(lines):
    bolds = [t for t, b in lines if b]
    rest = [t for t, b in lines if not b]
    h = {'school': bolds[0] if bolds else '', 'title': bolds[-1] if bolds else '',
         'summary': '', 'scope': '', 'composition': [], 'lines': rest}
    for t in rest:
        m = RE_COMPOSE.search(t)
        if m and '·' in m.group(1) and re.search(r'\d', m.group(1)):
            for piece in m.group(1).split('·'):
                x = re.match(r'^\s*(.+?)\s*(\d+)\s*$', piece)
                if x:
                    h['composition'].append([x.group(1), int(x.group(2))])
            h['summary'] = t[:m.start()].strip(' ·')
        elif t.lstrip().startswith('※'):
            h['scope'] = t.lstrip().lstrip('※').strip()
    return h


def _new_item(segs, m, no):
    body = cut(segs, _lead(segs) + m.end())
    ptxt = plain(body)
    ms = RE_SRC_TAIL.search(ptxt)
    source = ms.group(1).strip() if ms else ''
    if ms:
        body = cut(body, 0, ms.start())
    ptxt = plain(body).rstrip()
    note = ''
    mn = RE_STEM_NOTE.search(ptxt)
    if mn:
        note = ptxt[mn.start(2):].strip()
        ptxt = ptxt[:mn.start(2)].rstrip()
    body = cut(body, 0, len(ptxt))
    return {'no': no, 'label': '', 'qlabel': m.group(1).strip(),
            'stem': rich(body, drop_bold=True), 'tag': '',
            'blocks': [{'t': 'note', 'text': note}] if note else [], 'source': source}


def _add_item(blk, t):
    m = RE_ITEM.match(t)
    blk['items'].append({'n': int(m.group(1)), 'text': m.group(2).strip()})


def classify(q):
    kinds = [b['t'] for b in q['blocks']]
    if 'pieces' in kinds:
        return 'arrange'
    if 'bogi' in kinds:
        return 'match'
    if 'ask' in kinds or 'words' in kinds:
        return 'ask'
    if 'summary' in kinds:
        return 'summary'
    pas = ' '.join(plain(p) for b in q['blocks'] if b['t'] == 'passage' for p in b['paras'])
    if re.search(r'\[\(\d\)\]', pas):
        return 'grammar'
    if re.search(r'\([a-h]\)', pas):
        return 'vocab'
    return 'etc'


def parse_problems(path):
    head_lines, units, errs = [], [], []
    it, state, expect = None, None, 1
    for kind, x in read_body(path):
        if kind == 't':                                   # 표로 온 배열 조각
            if it is None:
                errs.append('소속 없는 표')
                continue
            cells = []
            for row in x:
                for c in row:
                    s = plain(c).strip()
                    if s:
                        mm = RE_ITEM.match(s)
                        cells.append({'n': int(mm.group(1)), 'text': mm.group(2).strip()}
                                     if mm else {'n': None, 'text': s})
            it['blocks'].append({'t': 'pieces', 'cells': cells,
                                 'cols': max((len(r) for r in x), default=4)})
            state = None
            continue

        segs = x
        t = plain(segs).strip()
        if not t:
            if state in ('box', 'pieces'):
                state = None
            continue
        b0 = _bold0(segs)

        m = RE_STEM.match(t)
        if m and b0 and int(m.group(2)) == expect:
            it = _new_item(segs, m, expect)
            units.append({'id': f'u{expect:02d}', 'kind': 'single', 'source': it.pop('source'),
                          'range': None, 'head': '', 'passage': [], 'notes': [], 'items': [it]})
            expect += 1
            state = None
            continue
        if it is None:
            head_lines.append((t, b0))
            continue

        B = it['blocks']
        if RE_ARROW.match(t):
            B.append({'t': 'arrow'})
            state = 'arrow'
            continue
        if state == 'arrow':
            B.append({'t': 'summary', 'paras': [rich(segs)]})
            state = None
            continue

        ml = RE_LABEL.match(t)
        if ml:
            label, rest = ml.group(1).strip(), ml.group(2).strip()
            if '/' in rest and not RE_ITEM.match(rest):
                B.append({'t': 'words', 'label': label,
                          'items': [w.strip() for w in rest.split('/') if w.strip()]})
                state = None
                continue
            if not rest or RE_ITEM.match(rest):
                blk = {'t': 'box', 'label': label, 'items': [], 'tail': []}
                if rest:
                    _add_item(blk, rest)
                B.append(blk)
                state = 'box'
                continue

        mi = RE_ITEM.match(t)
        if state == 'box':
            if mi:
                _add_item(B[-1], t)
                continue
            if t.startswith('('):
                B[-1]['tail'].append(t)
                continue
            state = None

        ma = RE_ASK.match(t)
        if ma:
            B.append({'t': 'ask', 'text': ma.group(1).strip()})
            state = None
            continue
        if RE_ANS.match(t):
            if B and B[-1]['t'] == 'ans':
                B[-1]['lines'].append(t)
            else:
                B.append({'t': 'ans', 'lines': [t]})
            state = None
            continue
        if mi and B and B[-1]['t'] in ('passage', 'pieces'):
            if B[-1]['t'] != 'pieces':
                B.append({'t': 'pieces', 'cells': [], 'cols': 0})
            B[-1]['cells'].append({'n': int(mi.group(1)), 'text': mi.group(2).strip()})
            state = 'pieces'
            continue
        state = None
        if RE_LETTER.search(t) and not any(b['t'] == 'summary' for b in B):
            B.append({'t': 'summary', 'paras': [rich(segs)]})
            continue
        if B and B[-1]['t'] == 'passage':
            B[-1]['paras'].append(rich(segs))
        else:
            B.append({'t': 'passage', 'paras': [rich(segs)]})

    for u in units:
        q = u['items'][0]
        for b in q['blocks']:
            if b['t'] == 'box':
                txt = ' '.join(i['text'] for i in b['items'])
                b['t'] = 'bogi' if len(RE_LATIN.findall(txt)) > len(txt) * 0.5 else 'cond'
            if b['t'] == 'pieces' and not b['cols']:
                n = len(b['cells'])
                longest = max((len(c['text']) for c in b['cells']), default=0)
                b['cols'] = 3 if (longest > 26 or (n % 4 and n % 3 == 0)) else 4
        q['type'] = classify(q)
    return parse_head(head_lines), units, errs


def gate_problems(head, units):
    errs = []
    if not units:
        return ['문항 0개 — 문항 머리(`[라벨 N]`)를 못 찾았다']
    nos = [u['items'][0]['no'] for u in units]
    if nos != list(range(1, len(nos) + 1)):
        errs.append('문항 번호가 연속이 아니다')
    got = collections.Counter(TYPE_SHORT.get(u['items'][0]['type'], '?') for u in units)
    if head['composition']:
        want = {k: v for k, v in head['composition']}
        if dict(got) != want:
            errs.append(f'유형 구성 불일치 — 원고 머리 {want} / 구조 판정 {dict(got)}')
    for u in units:
        q = u['items'][0]
        n, kinds = q['no'], [b['t'] for b in q['blocks']]
        if 'passage' not in kinds:
            errs.append(f'{n}번 지문 없음')
        if 'ans' not in kinds:
            errs.append(f'{n}번 답란 없음')
        if not u['source']:
            errs.append(f'{n}번 출처 없음')
        if q['type'] == 'etc':
            errs.append(f'{n}번 유형 판정 실패 {kinds}')
        if q['type'] == 'summary':
            s = ' '.join(plain(p) for b in q['blocks'] if b['t'] == 'summary' for p in b['paras'])
            a = ' '.join(ln for b in q['blocks'] if b['t'] == 'ans' for ln in b['lines'])
            ns, na = len(RE_LETTER.findall(s)), len(RE_ANS_LETTER.findall(a))
            if ns != na:
                errs.append(f'{n}번 요약문 빈칸 {ns}개 ≠ 답란 첫 글자 {na}개')
        if q['type'] == 'arrange':
            pas = ' '.join(plain(p) for b in q['blocks'] if b['t'] == 'passage' for p in b['paras'])
            if not re.search(r'_{3,}', pas):
                errs.append(f'{n}번 배열 빈칸이 지문에 없다')
        for b in q['blocks']:
            lst = b.get('cells') if b['t'] == 'pieces' else b.get('items')
            if b['t'] in ('pieces', 'bogi', 'words') and len(lst) < 3:
                errs.append(f'{n}번 {b["t"]} 항목 {len(lst)}개')
    return errs


# ---------------------------------------------------------------- 정답및풀이

def parse_answers(path):
    quick, answers, errs = [], [], []
    title, cur, sec = '', None, None
    for kind, x in read_body(path):
        if kind == 't':
            if cur is None:
                errs.append('정답 머리의 표는 모른다')
                continue
            rows = [[plain(c).strip() for c in r] for r in x]
            if sec is None:
                sec = {'title': '', 'blocks': []}
                cur['sections'].append(sec)
            sec['blocks'].append({'t': 'rows', 'rows': rows})
            continue
        segs = x
        t = plain(segs).strip()
        if not t:
            continue
        b0 = _bold0(segs)
        m = RE_AHEAD.match(t)
        if m and b0:
            cur = {'no': int(m.group(1)),
                   'answer': rich(cut(segs, _lead(segs) + m.end()), drop_bold=True),
                   'sections': []}
            answers.append(cur)
            sec = None
            continue
        if cur is None:
            mq = RE_QUICK.match(t)
            if mq:
                quick.append({'no': int(mq.group(1)), 'label': mq.group(2).strip(),
                              'source': mq.group(3).strip(), 'answer': mq.group(4).strip()})
            elif b0 and not title:
                title = t
            else:
                errs.append(f'정답 머리에서 모르는 줄: {t[:30]}')
            continue
        ms = RE_SEC.match(t)
        if ms and b0:
            sec = {'title': ms.group(1).strip(), 'blocks': []}
            cur['sections'].append(sec)
            continue
        if sec is None:
            sec = {'title': '', 'blocks': []}
            cur['sections'].append(sec)
        B = sec['blocks']
        if '│' in t:
            cells = [c.strip() for c in t.split('│')]
            if B and B[-1]['t'] == 'rows':
                B[-1]['rows'].append(cells)
            else:
                B.append({'t': 'rows', 'rows': [cells]})
            continue
        mi = RE_ITEM.match(t)
        if mi and b0:
            body = rich(cut(segs, _lead(segs) + mi.start(2)))
            if B and B[-1]['t'] == 'steps':
                B[-1]['items'].append(body)
            else:
                B.append({'t': 'steps', 'items': [body]})
            continue
        B.append({'t': 'p', 'rich': rich(segs)})
    return title, quick, answers, errs


def gate_answers(units, quick, answers):
    errs, N = [], len(units)
    if [a['no'] for a in quick] != list(range(1, N + 1)):
        errs.append(f'빠른 정답 {len(quick)}줄 — 번호가 문항 1~{N} 과 다르다')
    if [a['no'] for a in answers] != list(range(1, N + 1)):
        errs.append(f'문항별 풀이 {len(answers)}개 — 번호가 문항 1~{N} 과 다르다')
    for u, qa in zip(units, quick):
        q = u['items'][0]
        short = TYPE_SHORT.get(q['type'], '?')
        if short not in qa['label']:
            errs.append(f"{q['no']}번 유형: 정답지 '{qa['label']}' ≠ 구조 판정 '{short}'")
        if not _norm(u['source']).endswith(_norm(qa['source'])):
            errs.append(f"{q['no']}번 출처: 정답지 '{qa['source']}' ≠ 문제지 '{u['source']}'")
    for qa, a in zip(quick, answers):
        if _norm(qa['answer']) != _norm(plain(a['answer'])):
            errs.append(f"{a['no']}번 빠른 정답 ≠ 풀이 머리 정답")
        if not a['sections']:
            errs.append(f"{a['no']}번 풀이 절 없음")
    return errs


# ---------------------------------------------------------------- 빌드

def _title_tail(t):
    """`26학년도 2학기 중간고사 대비 서답형 40제` → `서답형 40제`"""
    return t.rsplit('대비', 1)[-1].strip() if '대비' in t else t


def build(cfg, log=print):
    """원고 → data.json. 게이트를 통과하지 못하면 조판하지 않고 중단한다."""
    ms = cfg.section("manuscript") or {}
    d = cfg.resolve(ms.get("dir", "원고"))
    pp = os.path.join(d, ms.get("problems") or "")
    if not ms.get("problems") or not os.path.exists(pp):
        raise FileNotFoundError(f"문제지 원고 없음: {pp}")
    head, units, errs = parse_problems(pp)
    errs += gate_problems(head, units)
    log(f"[원고] {os.path.basename(pp)} — 문항 {len(units)}")
    types = collections.Counter(TYPE_SHORT.get(u['items'][0]['type'], '?') for u in units)
    log(f"  유형 판정 {dict(types)} · 원고 머리 {dict(head['composition'])}")

    pc = cfg.get("parts") or []

    def title(i, default):
        return (pc[i].get("title") if i < len(pc) else None) or default

    parts = [{'no': 1, 'kind': 'problems', 'title': title(0, _title_tail(head['title'])),
              'units': units}]
    files = [os.path.basename(pp)]
    if ms.get("answers"):
        ap = os.path.join(d, ms["answers"])
        if not os.path.exists(ap):
            raise FileNotFoundError(f"정답 원고 없음: {ap}")
        atitle, quick, answers, e2 = parse_answers(ap)
        errs += e2 + gate_answers(units, quick, answers)
        for u, qa in zip(units, quick):
            u['items'][0]['label'] = qa['label']
            qa['type'] = u['items'][0]['type']
        parts.append({'no': 2, 'kind': 'answers', 'title': title(1, '정답 및 풀이'),
                      'quick_title': atitle, 'units': [], 'quick': quick, 'answers': answers})
        files.append(os.path.basename(ap))
        log(f"[원고] {os.path.basename(ap)} — 빠른 정답 {len(quick)} · 풀이 {len(answers)}")
    if errs:
        for e in errs[:30]:
            log(f"  [인식 실패] {e}")
        raise ValueError(f"원고 인식 게이트 {len(errs)}건 — 조판하지 않는다")
    data = {'head': head, 'intro': {}, 'parts': parts, 'manuscript': files,
            'counts': {'parts': len(parts), 'units': len(units), 'items': len(units)}}
    out = cfg.path('data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"  → {out}")
    return {'data': out, **data['counts']}


def load(cfg, log=None):
    """data.json + 정오표(errata.json) — 조판과 검수가 같은 글을 보게."""
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
