#!/usr/bin/env python3
"""Step3 회귀 진단: 수정 파서 재파싱 결과 vs 기존 content.json(베이스라인) 대조.

각 job에 대해 step3 내용 단어 집합을 비교한다:
  - recovered : 새 출력에만 있는 단어 (수정으로 복구된 내용 — 기대됨)
  - lost      : 베이스라인에만 있는 단어 (회귀! 0이어야 함)
  - ans_new   : 새 출력의 정답/해설형 단락 수 (누출 신호 — 베이스라인보다 늘면 안 됨)

usage:
  python3 scripts/step3_regression_diff.py            # 코퍼스 전수
  python3 scripts/step3_regression_diff.py --limit 30
"""
import os, re, sys, json, glob, unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines.workbook import parser as P

CFG = json.load(open(os.path.join(os.path.dirname(__file__), '..',
                                  'engines', 'workbook', 'config.json'), encoding='utf-8'))
MX = CFG.get('mockexam', {})
NORMAL = MX.get('normal_questions', [])
SHORT = MX.get('short_questions', [])
COMBINED = MX.get('combined_questions', {})

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
# 정답/해설형 단락 (누출 신호)
_ANS = re.compile(r'^\s*[①②③④⑤]\s*(?:,\s*[①②③④⑤]\s*)*:\s*.+|해설|오답\s*풀이')
# 과잉 prepend 신호: 번호 뒤가 한글 지시문(발문)인 단락 = 발문에 번호가 잘못 붙음
_OVERPREPEND = re.compile(r'^\s*[①②③④⑤]\s*.*[가-힣].*(?:것은|곳은|고르시오|문장은)\s*[\?\.]?\s*$')


def _overprepend(texts):
    return [t for t in texts if _OVERPREPEND.match((t or '').strip())]


def _nfc(s):
    return unicodedata.normalize('NFC', s or '')


def _words(texts):
    s = set()
    for t in texts:
        for w in _WORD.findall(t or ''):
            s.add(w.lower())
    return s


def _ans_count(texts):
    return sum(1 for t in texts if _ANS.search((t or '').strip()))


def _baseline_texts(content_json):
    with open(content_json, encoding='utf-8') as f:
        d = json.load(f)
    s3 = (d.get('steps', {}) or {}).get('step3', {})
    out = []
    for grp in ('normal', 'short'):
        for q in (s3.get(grp) or []):
            for p in q.get('paragraphs', []):
                out.append(_nfc(p.get('text', '') if isinstance(p, dict) else str(p)))
    return out


def _new_texts(step3_dir):
    res = P._parse_step3_folder(step3_dir, '고2', 26, 6, NORMAL, SHORT, COMBINED,
                                extract_underline=False)
    out = []
    for grp in ('normal', 'short'):
        for q in res.get(grp, []):
            for p in q.get('paragraphs', []):
                out.append(_nfc(p.get('text', '') if isinstance(p, dict) else str(p)))
    return out


def _iter_jobs(limit):
    jobs = sorted(glob.glob('jobs/*/'))
    n = 0
    for jd in jobs:
        step3 = os.path.join(jd, 'uploads', 'Step3')
        cjson = os.path.join(jd, 'content.json')
        if not (os.path.isdir(step3) and os.path.isfile(cjson)):
            continue
        yield jd, step3, cjson
        n += 1
        if limit and n >= limit:
            return


def capture(path, limit):
    """현재 코드로 코퍼스를 파싱해 베이스라인(단어집합+정답단락수)을 저장."""
    base = {}
    for jd, step3, cjson in _iter_jobs(limit):
        try:
            new = _new_texts(step3)
        except Exception as e:
            print('SKIP capture %s (%s)' % (jd, str(e)[:50]))
            continue
        base[jd] = {'w': sorted(_words(new)), 'ans': _ans_count(new)}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(base, f, ensure_ascii=False)
    print('베이스라인 저장: %s (%d jobs)' % (path, len(base)))


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    if '--capture' in sys.argv:
        capture(sys.argv[sys.argv.index('--capture') + 1], limit)
        return
    baseline = None
    if '--baseline' in sys.argv:
        with open(sys.argv[sys.argv.index('--baseline') + 1], encoding='utf-8') as f:
            baseline = json.load(f)
    checked = 0
    regress = []   # lost>0
    recov = []     # recovered>0
    leaks = []     # ans_new > ans_old
    overp = []     # 과잉 prepend
    for jd, step3, cjson in _iter_jobs(limit):
        try:
            new = _new_texts(step3)
            if baseline is not None:
                if jd not in baseline:
                    continue
                ow = set(baseline[jd]['w'])
                ao = baseline[jd]['ans']
            else:
                old = _baseline_texts(cjson)
                ow = _words(old)
                ao = _ans_count(old)
        except Exception as e:
            print('SKIP %s (%s)' % (jd, str(e)[:60]))
            continue
        checked += 1
        nw = _words(new)
        recovered = nw - ow
        lost = ow - nw
        an = _ans_count(new)
        op = _overprepend(new)
        if lost:
            regress.append((len(lost), jd, sorted(lost)[:25]))
        if recovered:
            recov.append((len(recovered), jd))
        if an > ao:
            leaks.append((an - ao, jd, ao, an))
        if op:
            overp.append((len(op), jd, op[:3]))
        if limit and checked >= limit:
            break

    print('\n===== Step3 회귀 진단 결과 =====')
    print('검사 job: %d개' % checked)
    print('복구된(단어↑) job: %d개' % len(recov))
    print('회귀(lost>0) job: %d개   <<< 0이어야 정상' % len(regress))
    print('정답누출 의심(ans↑) job: %d개' % len(leaks))

    print('\n--- 복구 상위 ---')
    for n, jd in sorted(recov, reverse=True)[:15]:
        print('  %-18s +%d 단어 복구' % (jd, n))

    if regress:
        print('\n--- ⚠️ 회귀(내용 손실) ---')
        for n, jd, sample in sorted(regress, reverse=True):
            print('  %-18s -%d 단어: %s' % (jd, n, ', '.join(sample)))
    else:
        print('\n✅ 회귀 없음 — 기존 출력의 단어가 사라진 job 0개')

    if leaks:
        print('\n--- ⚠️ 정답누출 의심 ---')
        for d, jd, ao, an in sorted(leaks, reverse=True):
            print('  %-18s 정답형 단락 %d→%d (+%d)' % (jd, ao, an, d))
    else:
        print('✅ 정답누출 신호 없음')

    print('\n과잉 prepend(발문에 번호 잘못 붙음) job: %d개' % len(overp))
    if overp:
        print('--- ⚠️ 과잉 prepend ---')
        for n, jd, sample in sorted(overp, reverse=True)[:15]:
            print('  %-18s %d건: %s' % (jd, n, ' | '.join(s[:40] for s in sample)))
    else:
        print('✅ 과잉 prepend 없음')


if __name__ == '__main__':
    main()
