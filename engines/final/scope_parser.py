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
    # "워크북NN(" 뒤의 괄호 그룹을 균형 괄호로 추출 — scope 안에 "능률(민)" 같은
    # 중첩 괄호가 있어도 전체를 잡는다(예: "워크북04(능률(민)3과)_내지" → "능률(민)3과").
    # 기존 r"\(([^)]+)\)"는 내부 ")"에서 끊겨 "능률(민"만 잡아 textbook 분류 실패(한영1).
    m_start = re.search(r"워크북\s*\d+\s*\(", fn)
    if m_start:
        start = m_start.end()
        depth = 1
        for i in range(start, len(fn)):
            if fn[i] == "(":
                depth += 1
            elif fn[i] == ")":
                depth -= 1
                if depth == 0:
                    return fn[start:i]
    # 폴백: 워크북 패턴이 없거나(분석편 등) 닫는 괄호 못 찾을 때
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
    # 어법수정은 원고(Word docx)에서 가져온다. 올림포스 어법수정 원고는
    # 'EBS 작업/올림포스 독해기본1/N강/...어법수정_문제지.docx'에 있다. 그런데 학교
    # 워크북 파일명/시험범위는 약어 '올포'가 아니라 정식 '올림포스NN강'으로 표기되는
    # 경우가 많아, "올포"만 검사하면 scope가 unknown→어법수정 원고 경로(find_ebs)에
    # 도달 못 한다(상일1). '올림포스'도 ebs_olympos로 인식한다.
    if re.search(r"올포|올림포스", scope):
        return "ebs_olympos"
    if "마더텅" in scope:
        return "mothertongue"
    if "리딩파워" in scope or "Reading" in scope:
        return "ebs_readingpower"
    if "자이스토리" in scope:
        return "zaistory"
    if "TED" in scope or "외부" in scope:
        return "external"
    # 고3 수능특강/파이널엣지 분석편
    if re.search(r"(FINALEDGE|수능특강|파이널엣지)", scope, re.IGNORECASE):
        return "ebs_suneung"
    # 강 번호만 있는 경우 (예: "3,4,5,6,7,9강")
    if re.match(r"^[\d,\s]+강$", scope):
        return "ebs_suneung"
    if scope == "test1" or re.match(r"^test\d+", scope, re.IGNORECASE):
        return "ebs_suneung"

    return "unknown"


def get_grammar_source(scope_type):
    """시험범위 유형별 어법수정 소스 결정.

    올림포스 고2 기출 / 고1 마더텅만 워크북 A1, 나머지는 전부 Word 파일.

    Returns:
        "word_file" — 교과서/모의고사/EBS 어법수정 Word
        "workbook_a1" — 워크북 STEP2 A1 추출 (마더텅, 올림포스 고2 기출만)
    """
    if scope_type in ("mothertongue", "ebs_suneung"):
        return "workbook_a1"
    # 올림포스 고2 기출도 workbook_a1 — 별도 처리 필요시 여기서 분기
    # 나머지는 전부 Word 파일
    return "word_file"


def parse_lectures_from_filename(filename):
    """분석편 파일명에서 강 번호 리스트 추출.

    Args:
        filename: 분석편 파일명 (예: "고3_FINALEDGE분석편(3,4,5,6,7,9강)_내지.indd")

    Returns:
        리스트: ["3", "4", "5", "6", "7", "9"] 또는 ["test1"]
    """
    fn = _nfc(filename)
    # 파일명 내 모든 괄호를 훑어 첫 번째 매치되는 강 목록 패턴을 찾는다.
    # (학교 분석편 파일: "(분석01)3,6,7,11,12강" 처럼 괄호 밖에 목록이 있는 경우 대응)
    candidates = re.findall(r"\(([^)]+)\)", fn) + [fn]
    for inner in candidates:
        # "test1" / "test1,test2" 등 테스트 패턴 — 강 목록처럼 쉼표로 분리.
        # (학교 합본 분석편 "(test1,test2)"을 ["test1","test2"]로 나눠야
        #  강(18,19,20,21강 → 18·19·20·21강)과 동일하게 강별 매핑된다.
        #  과거엔 통째로 ["test1,test2"]를 반환해 selected_lectures와 매칭 실패→누락.)
        _s = inner.strip()
        if re.match(r"^test\d+", _s, re.IGNORECASE):
            # 각 항목을 "testN"으로 정규화 — 접미사가 붙은 "test2짤지문"을 "test2"로.
            # (그대로 두면 selected_lectures의 "test2"와 매칭 실패 → 통합편 누락.)
            _parts = [p.strip() for p in _s.split(",") if p.strip()]
            _norm = []
            for p in _parts:
                pm = re.match(r"^test\s*(\d+)", p, re.IGNORECASE)
                _norm.append("test" + pm.group(1) if pm else None)
            if _parts and all(x is not None for x in _norm):
                return _norm
            return [_s]
        # "분석01", "분석편02" 같은 파일 번호 표기는 스킵
        if re.match(r"^\ubd84\uc11d(?:\ud3b8)?\s*\d+\s*$", inner.strip()):
            continue
        # 쉼표 + 범위 혼합 표기 지원: "7,11-14", "3,4,5", "11-16", "11"
        # 예: "7,11-14강" → [7, 11, 12, 13, 14]
        m = re.search(
            r"((?:\d+\s*[-~\u2013\u2014]\s*\d+|\d+)(?:\s*,\s*(?:\d+\s*[-~\u2013\u2014]\s*\d+|\d+))*)\s*\uac15",
            inner,
        )
        if m:
            result = []
            for part in m.group(1).split(","):
                part = part.strip()
                rm = re.match(r"(\d+)\s*[-~\u2013\u2014]\s*(\d+)$", part)
                if rm:
                    s_n, e_n = int(rm.group(1)), int(rm.group(2))
                    if s_n <= e_n and e_n - s_n < 50:
                        result.extend(str(n) for n in range(s_n, e_n + 1))
                elif part.isdigit():
                    result.append(part)
            # 같은 괄호에 강+test 혼합 표기("29,30강,test2")이면 test 마커도 수집한다.
            # (파일 내 순서상 test가 강 뒤에 오므로 result 끝에 추가 — 광문3 test2 누락 수정)
            for _tm in re.finditer(r"test\s*(\d+)", inner, re.IGNORECASE):
                _tl = "test" + _tm.group(1)
                if _tl not in result:
                    result.append(_tl)
            if result:
                return result
    return []


def parse_all_scopes(workbook_files):
    """워크북 파일 리스트에서 전체 시험범위 파싱.

    Returns:
        리스트: [{"file": 파일명, "scope": 범위텍스트, "type": 분류, "grammar_source": 소스}]
    """
    results = []
    for f in workbook_files:
        basename = _nfc(os.path.basename(f))
        scope = parse_scope_from_filename(basename)
        # 공용 올포 파일 (고1_올림포스독해기본(N-M강)): scope 앞에 "올포" 접두어 부여
        if "올림포스독해기본" in basename and scope and "올포" not in scope:
            scope = "올포" + scope
        scope_type = classify_scope(scope)
        grammar_src = get_grammar_source(scope_type)
        results.append({
            "file": basename,
            "scope": scope,
            "type": scope_type,
            "grammar_source": grammar_src,
        })
    return results
