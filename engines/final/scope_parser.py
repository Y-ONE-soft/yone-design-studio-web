"""파이널 직전보충 — 워크북 파일명에서 시험범위 파싱 + 분류."""

import os
import re
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def parse_scope_from_filename(filename):
    """워크북 파일명 괄호 안에서 시험범위 추출.

    Args:
        filename: 워크북 파일명 (예: "배재1_워크북01(교과서1,2과,SL)_내지.indd")

    Returns:
        시험범위 문자열 (예: "교과서1,2과,SL")
    """
    fn = _nfc(filename)
    m = re.search(r"\(([^)]+)\)", fn)
    return m.group(1) if m else ""


def classify_scope(scope):
    """시험범위를 소스 유형으로 분류.

    Returns:
        "textbook" | "mockexam" | "ebs_olympos" | "ebs_readingpower" |
        "mothertongue" | "zaistory" | "external" | "unknown"
    """
    if not scope:
        return "unknown"

    scope = _nfc(scope)

    if re.search(r"교과(서)?\s*\d", scope) or scope in ("SL", "SL1", "SL2"):
        return "textbook"
    # 출판사명+과 패턴: "미래엔김3과", "능률민1과" 등
    if re.search(r"(미래엔|능률|YBM|동아|비상|금성|천재)\S*\d+과", scope, re.IGNORECASE):
        return "textbook"
    if re.search(r"모의고사", scope):
        return "mockexam"
    if re.search(r"\d{2}년\d{1,2}월", scope):
        return "mockexam"
    if re.search(r"올포", scope):
        return "ebs_olympos"
    if "마더텅" in scope:
        return "mothertongue"
    if "리딩파워" in scope or "Reading" in scope:
        return "ebs_readingpower"
    if "자이스토리" in scope:
        return "zaistory"
    if "TED" in scope or "외부" in scope:
        return "external"

    return "unknown"


def get_grammar_source(scope_type):
    """시험범위 유형별 어법수정 소스 결정.

    올림포스 고2 기출 / 고1 마더텅만 워크북 A1, 나머지는 전부 Word 파일.

    Returns:
        "word_file" — 교과서/모의고사/EBS 어법수정 Word
        "workbook_a1" — 워크북 STEP2 A1 추출 (마더텅, 올림포스 고2 기출만)
    """
    if scope_type in ("mothertongue",):
        return "workbook_a1"
    # 올림포스 고2 기출도 workbook_a1 — 별도 처리 필요시 여기서 분기
    # 나머지는 전부 Word 파일
    return "word_file"


def parse_all_scopes(workbook_files):
    """워크북 파일 리스트에서 전체 시험범위 파싱.

    Returns:
        리스트: [{"file": 파일명, "scope": 범위텍스트, "type": 분류, "grammar_source": 소스}]
    """
    results = []
    for f in workbook_files:
        basename = _nfc(os.path.basename(f))
        scope = parse_scope_from_filename(basename)
        scope_type = classify_scope(scope)
        grammar_src = get_grammar_source(scope_type)
        results.append({
            "file": basename,
            "scope": scope,
            "type": scope_type,
            "grammar_source": grammar_src,
        })
    return results
