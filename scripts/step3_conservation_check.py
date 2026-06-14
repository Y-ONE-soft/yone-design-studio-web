#!/usr/bin/env python3
"""Step3 내용 보존 검사기 (conservation invariant).

원리: 원고(raw) 추출 내용 중 '정답 섹션'을 제외한 실질 내용 단어(영어 4자+)의 집합이
출력(content.json)에 전부 살아남았는지 검사한다. 출력 어디에도 없는 단어 = silent drop.

- 파서를 수정하지 않는다(읽기 전용). 회귀 위험 0.
- SET 의미로 비교(단어 1개라도 완전히 사라지면 적발). 빈도 차이는 무시 → 오탐 최소.
- 이후 영구 가드(파서 내장)의 핵심 로직 원형이 된다.

usage:
  python3 scripts/step3_conservation_check.py <job_dir>        # 단일 job
  python3 scripts/step3_conservation_check.py --corpus         # jobs/* 전수
  python3 scripts/step3_conservation_check.py --corpus --limit 20
"""
import os, re, sys, json, glob, unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engines.workbook.parser import _hwp_extract_paragraphs, _docx_extract_paragraphs

# 정답해설 섹션 헤더 — 이 줄부터 끝까지는 정당하게 제거되는 영역
_ANSWER_SECTION = re.compile(
    r'^(정답\s*(및|과)?\s*해설|빠른\s*정답\s*찾기|정답지|\[?\s*정답\s*\]?|해설)\s*$'
)
# 실질 내용 영어 단어: 4자 이상 알파벳 (정답마커/번호/구조마커는 매치 안 됨)
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _nfc(s):
    return unicodedata.normalize('NFC', s or '')


def _paras_text(paras):
    return [(_nfc(p.get('text', '')) if isinstance(p, dict) else _nfc(str(p))) for p in paras]


def _content_words(texts):
    """정답섹션 이전 텍스트들에서 실질 영어 단어 집합 추출."""
    words = set()
    for t in texts:
        if _ANSWER_SECTION.match(t.strip()):
            break  # 정답섹션 진입 → 이후 전부 정당한 제거 영역
        for w in _WORD.findall(t):
            words.add(w.lower())
    return words


def _extract_raw(fpath):
    if fpath.lower().endswith('.docx'):
        return _docx_extract_paragraphs(fpath)
    return _hwp_extract_paragraphs(fpath)


def _final_by_qnum(content_json):
    with open(content_json, encoding='utf-8') as f:
        d = json.load(f)
    s3 = (d.get('steps', {}) or {}).get('step3', {})
    out = {}
    for grp in ('normal', 'short'):
        for q in (s3.get(grp) or []):
            key = str(q.get('question_num', '')).split('~')[0].strip()
            out[key] = _paras_text(q.get('paragraphs', []))
    # textbook 단일 버킷 케이스
    if not out:
        for grp in ('normal', 'short'):
            for q in (s3.get(grp) or []):
                out.setdefault('_all', []).extend(_paras_text(q.get('paragraphs', [])))
    return out


def check_job(job_dir):
    """반환: (검사한 파일수, 손실있는 파일수, [(파일명, dropped_words 정렬리스트), ...])"""
    step3 = os.path.join(job_dir, 'uploads', 'Step3')
    cjson = os.path.join(job_dir, 'content.json')
    if not (os.path.isdir(step3) and os.path.isfile(cjson)):
        return None
    try:
        final = _final_by_qnum(cjson)
    except (ValueError, OSError):
        return None  # 깨진/미완성 content.json → 회귀 검사 대상 아님
    # 출력 전체 단어 합집합(파일↔질문 매칭 실패 대비 fallback)
    all_final_words = set()
    for texts in final.values():
        all_final_words |= _content_words_all(texts)

    results = []
    nfiles = 0
    for fname in sorted(os.listdir(step3)):
        if not re.search(r'\.(hwp|hwpx|docx)$', fname, re.I):
            continue
        m = re.search(r'(\d+)(?:~\d+)?번', _nfc(fname))
        if not m:
            continue
        qn = m.group(1)
        fpath = os.path.join(step3, fname)
        try:
            raw_texts = _paras_text(_extract_raw(fpath))
        except Exception as e:
            results.append((fname, ['<추출실패: %s>' % e]))
            continue
        nfiles += 1
        raw_words = _content_words(raw_texts)
        out_texts = final.get(qn)
        out_words = _content_words_all(out_texts) if out_texts is not None else set()
        # 질문 매칭 실패 시 전체 출력 단어로 fallback (드롭 과대보고 방지)
        compare = out_words if out_texts is not None else all_final_words
        dropped = sorted(raw_words - compare)
        if dropped:
            results.append((fname, dropped))
    nlost = len(results)
    return (nfiles, nlost, results)


def _content_words_all(texts):
    """출력측: 정답섹션 절단 없이 전체에서 단어 추출(출력엔 정답섹션이 이미 없음)."""
    words = set()
    for t in (texts or []):
        for w in _WORD.findall(t):
            words.add(w.lower())
    return words


def main():
    args = sys.argv[1:]
    if '--corpus' in args:
        limit = None
        if '--limit' in args:
            limit = int(args[args.index('--limit') + 1])
        jobs = sorted(glob.glob('jobs/*/'))
        checked = lost_files = lost_words = 0
        worst = []
        for jd in jobs:
            r = check_job(jd.rstrip('/'))
            if not r:
                continue
            nf, nl, res = r
            checked += 1
            lost_files += nl
            wl = sum(len(d) for _, d in res)
            lost_words += wl
            if wl:
                worst.append((wl, jd, nf, nl))
            if limit and checked >= limit:
                break
        print('=== 코퍼스 보존 검사 결과 ===')
        print('검사한 job: %d개' % checked)
        print('내용 손실이 있는 파일이 포함된 job: %d개' % len([w for w in worst if w[0] > 0]))
        print('손실 단어 총합(영어 4자+, 중복제거): %d개' % lost_words)
        print()
        print('--- 손실 심한 job 상위 ---')
        for wl, jd, nf, nl in sorted(worst, reverse=True)[:25]:
            print('  %-18s 파일%d개중 %d개 손실, 단어 %d개' % (jd, nf, nl, wl))
    else:
        jd = args[0].rstrip('/')
        r = check_job(jd)
        if not r:
            print('Step3/content.json 없음:', jd)
            return
        nf, nl, res = r
        print('=== %s ===' % jd)
        print('검사 파일 %d개, 손실 파일 %d개' % (nf, nl))
        for fname, dropped in res:
            print('\n[%s] 손실 단어 %d개:' % (fname, len(dropped)))
            print('  ', ', '.join(dropped[:40]) + (' ...' if len(dropped) > 40 else ''))


if __name__ == '__main__':
    main()
