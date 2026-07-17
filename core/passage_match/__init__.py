"""지문 동일성 매칭 (passage fingerprint matcher).

워크북 전체(C)에서 같은 지문이 섹션마다 변형돼 등장한다:
빈칸 변형("hello ____ is yone design"), 선지 접두("(A) hello this is ..."),
첫 문장 생략, 어법 선택("1[driving / to drive]"), 한글 번역+낱말은행 등.
표면 문자열 비교로는 다른 지문으로 잡히므로, 정규화 → 단어 시퀀스 →
w-shingle 비대칭 containment + IDF 가중 토큰 containment로 묶는다.

공개 API:
    fingerprint(text)            → Fingerprint
    pair_score(fa, fb, idf=None) → PairScore (shingle/token containment)
    is_same_passage(fa, fb, ...) → bool
    group_items(texts, ...)      → list[list[int]] (인덱스 그룹, 대표 순)
"""

from .matcher import (  # noqa: F401
    Fingerprint,
    PairScore,
    fingerprint,
    normalize_tokens,
    pair_score,
    is_same_passage,
    build_idf,
    build_match_graph,
    detect_hubs,
    group_fingerprints,
    group_items,
)
from .segment import segment_content_steps, PassageItem  # noqa: F401
