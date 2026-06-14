"""
engines/_taxonomy — 원고 분류 체계 모듈

조판 자동화의 표준 입력 스펙. 126개 leaf 유형 코드로 영어 내신/모의 문제 분류.

밑줄 prefix `_taxonomy` = registry.py에 등록되지 않은 공유 모듈 (엔진 아님).
기존 엔진은 이 모듈을 import 안 함 → 기존 자동화 흐름에 0 영향.

기본 사용:
    from engines._taxonomy import classify, extract_text, extract_and_classify

    # 발문 1개 분류
    code, label, kind = classify("다음 글의 제목으로 가장 적절한 것은?")

    # 원고 한 파일 통째로
    results = extract_and_classify("/path/to/manuscript.hwpx")
    # → [{"q": ..., "code": "OBJ-CTN-TITLE", "label": "제목", "kind": "객관식", ...}]

스키마/룰셋:
    from engines._taxonomy.rules import RULES, INDEX
"""
from .classify import classify, classify_many, is_question, normalize_question
from .extract import (
    extract_text,
    extract_hwpx,
    extract_hwp,
    extract_docx,
    extract_questions,
    extract_and_classify,
)
from .rules import RULES, COMPILED, INDEX

__all__ = [
    "classify",
    "classify_many",
    "is_question",
    "normalize_question",
    "extract_text",
    "extract_hwpx",
    "extract_hwp",
    "extract_docx",
    "extract_questions",
    "extract_and_classify",
    "RULES",
    "COMPILED",
    "INDEX",
]

__version__ = "1.0.0"
