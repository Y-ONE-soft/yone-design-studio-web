"""core.structure — 단락 종류 판정 (Phase 2).

원고 단락이 "무엇인지"(발문/지문/선지/조건/보기/정답/한글해석/그룹헤더)를
단어가 아닌 구조(위치+마커+컨텍스트+언어+길이)로 판정한다.
설계: docs/taxonomy/09_워크북_단락종류.md
"""

from core.structure.paragraph_kind import classify_paragraphs  # noqa: F401
