"""한끝 계열 원고(docx) → data.json — **잠정 파서**(2026-09-11).

⚠ 확정 원고는 아직 작성 중이다. 이 파서는 초안(`원고/_초안/…Part 2.docx`, 제작규격 §5)
  의 구조를 읽는다. 확정 원고가 오면 **여기부터** 맞춘다 — 렌더러·배치는 data.json
  모양만 본다.

구조 인식(글자 모양이 아니라 자리로):
  · 파트     = 굵은 단락, 로마 숫자 / PART N 으로 시작 → 제목, `(a~b번)` 꼬리는 범위
  · 출처     = 꺾쇠만으로 된 단락 `<…>` (또는 문항 번호 바로 뒤 꺾쇠)
  · 묶음     = 굵은 `[a~b] …` 단락. 첫 문항 전에 **지문(영문 단락)** 이 오면 세트
               (지문 한 번 인쇄), 안 오면 파트 공통 발문(문항마다 머리에 찍는다)
  · 문항     = 굵은 `N.` 단락, N 이 직전 +1 (조건의 `1.` 과 구분된다)
  · 조건     = `[조건]` 단락 + 뒤따르는 `k.` 줄
  · 요약문   = `(A)`·`(B)` 뒤 첫 글자 + 띄어 쓴 밑줄(`h _ _ _`)이 있는 단락
  · 답란     = `답 :` 또는 `( )번:` 줄
  · 배열 조각 = 표 (칸마다 `k. 조각`)
  · 안내     = `(` 로 시작하는 짧은 단락(답안 작성 예 등)
  · 나머지   = 지문
시험 표기 `[2026년 … 중간고사]` 는 발문 끝 꼬리표로 뗀다.

인식 게이트: 문항 번호 연속 · 세트 문항 수 == 범위 · 배열 문항 조각 ≥ 3 ·
문항마다 답란 · 소속 없는 단락 0. 하나라도 어긋나면 조판하지 않는다.
"""
import json
import os
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_OFF = ('none', '0', 'false', 'off')

RE_PART = re.compile(r'^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|PART\s*\d+|Part\s*\d+)\s*[.:]?\s*(.+?)'
                     r'\s*(?:\(\s*(\d+)\s*[~∼-]\s*(\d+)\s*번?\s*\))?\s*$')
RE_SRC = re.compile(r'^<\s*([^<>]+?)\s*>$')
RE_GRP = re.compile(r'^\[\s*(\d+)\s*[~∼-]\s*(\d+)\s*\]\s*(.*)$')
RE_Q = re.compile(r'^(\d{1,3})\s*\.\s*(.*)$')
RE_QSRC = re.compile(r'^<\s*([^<>]+?)\s*>\s*(.*)$')
RE_TAG = re.compile(r'\s*\[\s*\d{4}\s*년[^\[\]]*\]\s*')
RE_COND = re.compile(r'^\[\s*조\s*건\s*\]\s*(.*)$')
RE_CITEM = re.compile(r'^\d\s*[.)]\s*\S')
RE_ANS = re.compile(r'^(?:답\s*[:：]|\(\s*\)\s*번)')
RE_LBLANK = re.compile(r'\([A-E]\)\s*[A-Za-z]\s*(?:_\s*){2,}')
RE_NOTE = re.compile(r'^\((?!\s*\))')
RE_PIECE = re.compile(r'^\s*(\d{1,2})\s*[.)]\s*(.*)$', re.S)
RE_LATIN = re.compile(r'[A-Za-z]')


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
        parts = t.split('\n')
        for k, s in enumerate(parts):
            if k:
                out.append(cur)
                cur = []
            if s:
                cur.append((s, f))
    out.append(cur)
    return out


def read_body(path):
    """본문을 **순서대로** — 단락과 표를 섞어서. (`iter(w:p)` 로 훑으면 표 칸이 흩어진다)"""
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
    if isinstance(x, list):
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
    if out:
        out[0]['t'] = out[0]['t'].lstrip()
        out[-1]['t'] = out[-1]['t'].rstrip()
    return out


def _bold0(segs):
    for t, f in segs:
        if t.strip():
            return bool(f.get('b'))
    return False


def split_tag(t):
    """발문 끝 시험 표기 `[2026년 한영고 1학년 2학기 중간고사]` 를 뗀다."""
    m = RE_TAG.search(t)
    if not m:
        return t.strip(), ''
    return (t[:m.start()] + ' ' + t[m.end():]).strip(), m.group(0).strip()


def _is_passage(t):
    return (not RE_NOTE.match(t) and len(t) > 50
            and len(RE_LATIN.findall(t)) > len(t) * 0.5)


# ---------------------------------------------------------------- 파서

def parse(path):
    elems = read_body(path)
    intro = {'title': '', 'sub': [], 'heading': '', 'lines': []}
    parts, errs = [], []
    st = {'part': None, 'unit': None, 'item': None, 'group': None,
          'src': None, 'expect': 1, 'uid': 0, 'cond': None}

    def new_unit(kind, source, rng=None, head='', tag=''):
        st['uid'] += 1
        u = {'id': f"u{st['uid']:02d}", 'kind': kind, 'source': source or '',
             'range': rng, 'head': head, 'tag': tag, 'passage': [], 'notes': [],
             'items': []}
        st['part']['units'].append(u)
        st['unit'] = u
        return u

    def block(it, t, payload):
        bl = it['blocks']
        key = {'passage': 'paras', 'ans': 'lines'}.get(t)
        if key and bl and bl[-1]['t'] == t:
            bl[-1][key].append(payload)
        elif key:
            bl.append({'t': t, key: [payload]})
        else:
            bl.append(dict(payload, t=t))

    for kind, x in elems:
        it = st['item']
        if kind == 't':
            cells = []
            for row in x:
                for c in row:
                    s = plain(c).strip()
                    if not s:
                        continue
                    m = RE_PIECE.match(s)
                    cells.append({'n': int(m.group(1)), 'text': m.group(2).strip()}
                                 if m else {'n': None, 'text': s})
            ncol = max((len(r) for r in x), default=0)
            if it is None:
                errs.append(f'소속 없는 표: {[c["text"] for c in cells][:3]}')
                continue
            block(it, 'pieces', {'cells': cells, 'cols': ncol})
            continue

        segs = x
        t = plain(segs).strip()
        if not t:
            continue
        b0 = _bold0(segs)

        m = RE_PART.match(t) if b0 else None
        if m and not RE_Q.match(t) and not RE_GRP.match(t):
            rng = [int(m.group(2)), int(m.group(3))] if m.group(2) else None
            st['part'] = {'no': len(parts) + 1, 'title': m.group(1).strip(),
                          'range': rng, 'units': []}
            parts.append(st['part'])
            st.update(unit=None, item=None, group=None, src=None, cond=None)
            continue

        if st['part'] is None:                       # 머리말 — 제목·3줄 요약
            if b0 and '요약' in t:
                intro['heading'] = t
            elif intro['heading'] and RE_CITEM.match(t):
                intro['lines'].append(re.sub(r'^\d\s*[.)]\s*', '', t))
            elif b0 and not intro['title']:
                intro['title'] = t
            else:
                intro['sub'].append(t)
            continue

        m = RE_SRC.match(t)
        if m:
            g = st['group']
            if g and st['expect'] > g['hi']:
                st['group'] = None
            st.update(src=m.group(1), item=None, cond=None)
            continue

        m = RE_GRP.match(t) if b0 else None
        if m:
            head, tag = split_tag(m.group(3))
            st['group'] = {'lo': int(m.group(1)), 'hi': int(m.group(2)),
                           'head': head, 'tag': tag, 'pre': [], 'kind': None,
                           'src': st['src']}
            st.update(src=None, item=None, cond=None)
            continue

        m = RE_Q.match(t) if b0 else None
        if m and int(m.group(1)) == st['expect']:
            no = st['expect']
            st['expect'] += 1
            rest = m.group(2)
            ms = RE_QSRC.match(rest)
            qsrc = None
            if ms:
                qsrc, rest = ms.group(1), ms.group(2)
            stem, tag = split_tag(rest)
            g = st['group']
            item = {'no': no, 'stem': stem, 'tag': tag, 'blocks': []}
            if g and g['lo'] <= no <= g['hi']:
                if g['kind'] is None:
                    pas = [p for p in g['pre'] if _is_passage(plain(p))]
                    g['kind'] = 'set' if pas else 'common'
                    notes = []
                    for p in g['pre']:
                        if _is_passage(plain(p)):
                            continue
                        s, tg = split_tag(plain(p))
                        if tg and not g['tag']:
                            g['tag'] = tg
                        if s:
                            notes.append(s)
                    g['notes'] = notes
                    if g['kind'] == 'set':
                        u = new_unit('set', g['src'], [g['lo'], g['hi']],
                                     g['head'], g['tag'])
                        u['passage'] = [rich(p) for p in pas]
                        u['notes'] = notes
                if g['kind'] == 'set':
                    st['unit']['items'].append(item)
                else:
                    u = new_unit('single', qsrc or st['src'])
                    item['stem'] = stem or g['head']
                    item['tag'] = tag or g['tag']
                    for n in g['notes']:
                        block(item, 'note', {'text': n})
                    u['items'].append(item)
            else:
                u = new_unit('single', qsrc or st['src'])
                u['items'].append(item)
                st['group'] = None
            st.update(item=item, src=None, cond=None)
            continue

        g = st['group']
        if g and g['kind'] is None:                  # 묶음 머리 뒤, 첫 문항 전
            g['pre'].append(segs)
            continue
        if it is None:
            errs.append(f'소속 없는 단락: {t[:40]}')
            continue

        m = RE_COND.match(t)
        if m:
            st['cond'] = {'items': [m.group(1).strip()] if m.group(1).strip() else []}
            block(it, 'cond', st['cond'])
            st['cond'] = it['blocks'][-1]
            continue
        if st['cond'] is not None and RE_CITEM.match(t) and not b0:
            st['cond']['items'].append(t)
            continue
        st['cond'] = None
        if RE_ANS.match(t):
            block(it, 'ans', t)
        elif RE_LBLANK.search(t):
            block(it, 'summary', {'paras': [rich(segs)]})
        elif RE_NOTE.match(t) and len(t) < 110:
            s, tg = split_tag(t)
            if tg and not it['tag']:
                it['tag'] = tg
            if s:
                block(it, 'note', {'text': s})
        else:
            block(it, 'passage', rich(segs))

    # ── 문항 유형(간지의 구성 칩) — 블록 구조로 가른다
    for P in parts:
        for u in P['units']:
            for q in u['items']:
                kinds = {b['t'] for b in q['blocks']}
                ans = ' '.join(ln for b in q['blocks'] if b['t'] == 'ans'
                               for ln in b['lines'])
                q['type'] = ('arrange' if 'pieces' in kinds else
                             'summary' if 'summary' in kinds else
                             'grammar' if '번' in ans else 'etc')

    # ── 인식 게이트
    nq = st['expect'] - 1
    items = [q for P in parts for u in P['units'] for q in u['items']]
    if [q['no'] for q in items] != list(range(1, nq + 1)):
        errs.append('문항 번호가 연속이 아니다')
    for P in parts:
        if not P['units']:
            errs.append(f"파트 {P['no']} '{P['title']}' 에 문항이 없다")
        if P['range']:
            got = [q['no'] for u in P['units'] for q in u['items']]
            if got and (got[0], got[-1]) != tuple(P['range']):
                errs.append(f"파트 {P['no']} 범위 {P['range']} ≠ 실제 {got[0]}~{got[-1]}")
        for u in P['units']:
            if u['kind'] == 'set' and len(u['items']) != u['range'][1] - u['range'][0] + 1:
                errs.append(f"세트 [{u['range'][0]}~{u['range'][1]}] 문항 {len(u['items'])}개")
            if u['kind'] == 'set' and not u['passage']:
                errs.append(f"세트 [{u['range'][0]}~{u['range'][1]}] 지문 없음")
    for q in items:
        kinds = [b['t'] for b in q['blocks']]
        if 'ans' not in kinds:
            errs.append(f"{q['no']}번 답란 없음")
        for b in q['blocks']:
            if b['t'] == 'pieces' and len(b['cells']) < 3:
                errs.append(f"{q['no']}번 배열 조각 {len(b['cells'])}개")
    return {'intro': intro, 'parts': parts,
            'counts': {'parts': len(parts),
                       'units': sum(len(P['units']) for P in parts),
                       'items': nq}}, errs


def find_manuscript(cfg):
    m = cfg.section("manuscript") or {}
    if m.get("file"):
        p = cfg.resolve(os.path.join(m.get("dir", "원고"), m["file"]))
        if not os.path.exists(p):
            raise FileNotFoundError(f"원고 없음: {p}")
        return p
    d = cfg.resolve(m.get("dir", "원고"))
    cands = sorted((f for f in os.listdir(d)
                    if f.endswith('.docx') and not f.startswith(('~', '.'))),
                   key=lambda f: os.path.getmtime(os.path.join(d, f)))
    if not cands:
        raise FileNotFoundError(f"원고 docx 없음: {d}")
    return os.path.join(d, cands[-1])


def build(cfg, log=print):
    """원고 → data.json. 게이트를 통과하지 못하면 조판하지 않고 중단한다."""
    path = find_manuscript(cfg)
    data, errs = parse(path)
    c = data['counts']
    log(f"[원고] {os.path.basename(path)}")
    log(f"  파트 {c['parts']} · 덩어리 {c['units']} · 문항 {c['items']}")
    for P in data['parts']:
        nq = sum(len(u['items']) for u in P['units'])
        sets = sum(1 for u in P['units'] if u['kind'] == 'set')
        log(f"  · {P['no']}. {P['title']}  덩어리 {len(P['units'])} (세트 {sets}) · 문항 {nq}")
    if errs:
        for e in errs[:20]:
            log(f"  [인식 실패] {e}")
        raise ValueError(f"원고 인식 게이트 {len(errs)}건 — 조판하지 않는다")
    data['manuscript'] = os.path.basename(path)
    out = cfg.path('data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"  → {out}")
    return {'data': out, **c}


def load(cfg, log=None):
    """data.json + 정오표(errata.json) — 조판과 검수가 같은 글을 보게."""
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
