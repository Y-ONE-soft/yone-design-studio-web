"""내용 보존 가드 — "원고에 있던 실질 단어가 출력에서 사라졌는가" 검사.

workbook parser의 _warn_step3_content_loss(pre-overhaul 1321행)를 일반화해
승격한 것. 파싱이 원고 내용을 소리 없이 떨어뜨리는 사고(silent content loss)를
로그로 드러내는 것이 목적이며, 출력(content.json)은 절대 바꾸지 않는다.

다른 엔진 적용 시 주의: 엔진이 의도적으로 버리는 텍스트(정답/해설/헤더)는
raw_words 수집 단계에서 제외해야 오탐이 없다. 오탐률을 코퍼스로 측정한 뒤
엔진별로 켠다 (Phase 2) — 경고가 시끄러우면 사람이 무시하게 되고, 그 순간
가드는 없는 것과 같다.
"""
import logging
import re

_LOG = logging.getLogger(__name__)

# 실질 단어: 영문 4자+ (관사·전치사 등 흔한 짧은 단어로 인한 노이즈 배제)
RE_CONTENT_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def collect_content_words(paras, word_re=RE_CONTENT_WORD):
    """단락 목록(dict 또는 str)에서 실질 단어 소문자 집합 추출."""
    words = set()
    for p in paras:
        t = (p.get('text', '') if isinstance(p, dict) else str(p)) or ''
        for w in word_re.findall(t):
            words.add(w.lower())
    return words


def warn_content_loss(raw_words, out_paras, label, log=None,
                      word_re=RE_CONTENT_WORD, tag="내용보존경고"):
    """raw_words(원고 실질 단어) 중 출력에서 사라진 것이 있으면 경고. 반환: 사라진 집합."""
    out_words = collect_content_words(out_paras, word_re)
    dropped = raw_words - out_words
    if dropped:
        msg = ("⚠️ [%s] %s — 원고 내용 %d개 단어가 출력에서 사라짐: %s"
               % (tag, label, len(dropped), ', '.join(sorted(dropped)[:20])))
        _LOG.warning(msg)
        if callable(log):
            try:
                log(msg)
            except Exception:
                pass
    return dropped
