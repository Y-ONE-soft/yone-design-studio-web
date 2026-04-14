"""파이널 직전보충 — 어법수정 Word(.docx) 파서.

교과서 작업 폴더의 어법수정 문제지 Word 파일(2열 테이블)에서
텍스트를 추출한다.
"""

import os
import re
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def find_grammar_word_files(content_base, subject, publisher, lessons, log=None):
    """교과서 작업 폴더에서 어법수정 문제지 Word 파일 경로 탐색.

    Args:
        content_base: 내신대비 루트 (교과서 작업 상위)
        subject: 과목명 (공통영어1, 영어Ⅰ 등)
        publisher: 출판사 (능률(민), YBM(김) 등)
        lessons: 과 목록 (["1과", "2과"])
        log: 로그 콜백

    Returns:
        발견된 .docx 파일 경로 리스트
    """
    textbook_base = os.path.join(content_base, "교과서 작업")

    # 과목 폴더 찾기 (NFD 대응)
    subject_dir = None
    if os.path.isdir(textbook_base):
        for d in os.listdir(textbook_base):
            if _nfc(d) == subject or _nfc(d).replace(" ", "") == subject.replace(" ", ""):
                subject_dir = os.path.join(textbook_base, d)
                break

    if not subject_dir or not os.path.isdir(subject_dir):
        if log:
            log(f"  [어법수정] 과목 폴더 없음: {subject}")
        return []

    # 교재 폴더 찾기 (subject + publisher)
    publisher_dir = None
    target_name = f"{subject} {publisher}"
    for d in os.listdir(subject_dir):
        dn = _nfc(d)
        if publisher in dn or target_name.replace(" ", "") in dn.replace(" ", ""):
            publisher_dir = os.path.join(subject_dir, d)
            break

    if not publisher_dir or not os.path.isdir(publisher_dir):
        if log:
            log(f"  [어법수정] 교재 폴더 없음: {target_name}")
        return []

    # 과 폴더별로 어법수정 문제지 찾기
    found_files = []
    for lesson in lessons:
        # 과 번호 추출 (1과 → 1, S1과 → S1 등)
        lesson_num = re.sub(r"과$", "", lesson.strip())

        # 과 폴더 찾기
        lesson_dir = None
        for d in os.listdir(publisher_dir):
            dn = _nfc(d)
            if not os.path.isdir(os.path.join(publisher_dir, d)):
                continue
            # SL 과: "S1과" → "SL1" 폴더 매칭
            if lesson_num.startswith("S") and lesson_num[1:].isdigit():
                sl_num = lesson_num[1:]
                if f"SL{sl_num}" in dn or f"SL {sl_num}" in dn:
                    lesson_dir = os.path.join(publisher_dir, d)
                    break
            # "공통영어1 능률(민) 1과" 또는 "영어1 능률(민) 1과" 패턴
            if f"{lesson_num}과" in dn or f"Lesson{lesson_num}" in dn or f"lesson{lesson_num}" in dn.lower():
                lesson_dir = os.path.join(publisher_dir, d)
                break

        if not lesson_dir:
            if log:
                log(f"  [어법수정] {lesson} 폴더 없음")
            continue

        # 어법수정 문제지 .docx 찾기 (하위 폴더 포함)
        for root, dirs, files in os.walk(lesson_dir):
            for f in files:
                fn = _nfc(f)
                if ("어법수정" in fn and "문제지" in fn and fn.endswith(".docx")
                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                    full_path = os.path.join(root, f)
                    found_files.append(full_path)
                    if log:
                        log(f"  [어법수정] {lesson}: {fn}")

    return found_files


def find_mockexam_grammar_files(content_base, scope_text, grade, log=None):
    """모의고사 작업 폴더에서 어법수정 Word 파일 탐색.

    Args:
        content_base: 내신대비 루트
        scope_text: 시험범위 텍스트 (예: "25년10월", "모의고사25.3")
        grade: "고1" 또는 "고2"
        log: 로그 콜백

    Returns:
        발견된 .docx 파일 경로 리스트
    """
    # scope에서 년도+월 추출
    m = re.search(r"(\d{2})년\s*(\d{1,2})월", _nfc(scope_text))
    if not m:
        m2 = re.search(r"모의고사\s*(\d{2})\.(\d{1,2})", _nfc(scope_text))
        if m2:
            m = m2
    if not m:
        if log:
            log(f"  [어법수정] 모의고사 년월 추출 실패: {scope_text}")
        return []

    year = m.group(1)
    month = m.group(2)

    mock_base = os.path.join(content_base, "모의고사 작업", grade)
    if not os.path.isdir(mock_base):
        if log:
            log(f"  [어법수정] 모의고사 폴더 없음: {mock_base}")
        return []

    # "고1 25년 10월" 형태의 폴더 찾기
    target_folder = None
    for d in os.listdir(mock_base):
        dn = _nfc(d)
        if f"{year}년" in dn and f"{month}월" in dn:
            target_folder = os.path.join(mock_base, d)
            break
        # "25년 3월" → "25년 03월" 도 시도
        if f"{year}년" in dn and f"{int(month)}월" in dn:
            target_folder = os.path.join(mock_base, d)
            break

    if not target_folder or not os.path.isdir(target_folder):
        if log:
            log(f"  [어법수정] 모의고사 {year}년 {month}월 폴더 없음")
        return []

    # 폴더 내 + 직전보충 하위에서 어법수정 문제지 찾기
    found = []
    for root, dirs, files in os.walk(target_folder):
        for f in files:
            fn = _nfc(f)
            if ("어법수정" in fn and "문제지" in fn and fn.endswith(".docx")
                    and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                full_path = os.path.join(root, f)
                found.append(full_path)
                if log:
                    log(f"  [어법수정] 모의고사: {fn}")

    return found


def find_ebs_grammar_files(content_base, scope_text, log=None):
    """EBS 작업 폴더에서 어법수정 Word 파일 탐색.

    Args:
        content_base: 내신대비 루트
        scope_text: 시험범위 텍스트 (예: "올포1-4강", "리딩파워1,2강")
        log: 로그 콜백

    Returns:
        발견된 .docx 파일 경로 리스트
    """
    ebs_base = os.path.join(content_base, "EBS 작업")
    if not os.path.isdir(ebs_base):
        return []

    scope = _nfc(scope_text)
    found = []

    # 올림포스 독해기본1
    if "올포" in scope:
        # 강 번호 추출 (예: "올포1-4강" → [1,2,3,4], "올포5,8,9강" → [5,8,9])
        units = _extract_unit_numbers(scope)
        olympos_base = None
        for d in os.listdir(ebs_base):
            dn = _nfc(d)
            if "올림포스" in dn and "독해기본" in dn:
                olympos_base = os.path.join(ebs_base, d)
                break

        if olympos_base:
            for unit_num in units:
                # "올림포스 독해기본1 5강" 형태의 폴더
                for d in os.listdir(olympos_base):
                    dn = _nfc(d)
                    if f"{unit_num}강" in dn:
                        unit_dir = os.path.join(olympos_base, d)
                        # 직접 하위 또는 워크북 하위에서 찾기
                        for root, dirs, files in os.walk(unit_dir):
                            for f in files:
                                fn = _nfc(f)
                                if ("어법수정" in fn and "문제지" in fn and fn.endswith(".docx")
                                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                                    found.append(os.path.join(root, f))
                                    if log:
                                        log(f"  [어법수정] 올포 {unit_num}강: {fn}")
                        break

    # 리딩파워
    elif "리딩파워" in scope or "Reading" in scope:
        units = _extract_unit_numbers(scope)
        rp_base = None
        for d in os.listdir(ebs_base):
            dn = _nfc(d)
            if "Reading Power" in dn or "리딩파워" in dn:
                rp_base = os.path.join(ebs_base, d)
                break

        if rp_base:
            for unit_num in units:
                for d in os.listdir(rp_base):
                    dn = _nfc(d)
                    if f"Unit {unit_num}" in dn or f"unit{unit_num}" in dn.lower():
                        unit_dir = os.path.join(rp_base, d)
                        for root, dirs, files in os.walk(unit_dir):
                            for f in files:
                                fn = _nfc(f)
                                if ("어법수정" in fn and fn.endswith(".docx")
                                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                                    found.append(os.path.join(root, f))
                                    if log:
                                        log(f"  [어법수정] 리딩파워 Unit{unit_num}: {fn}")
                        break

    return found


def _extract_unit_numbers(scope):
    """범위 텍스트에서 강/유닛 번호 추출.
    "올포1-4강" → [1,2,3,4]
    "올포5,8,9강" → [5,8,9]
    "리딩파워1,2강" → [1,2]
    "리딩파워9-11" → [9,10,11]
    """
    numbers = set()

    # 범위: "1-4", "9-11"
    for m in re.finditer(r"(\d+)\s*[-~]\s*(\d+)", scope):
        start, end = int(m.group(1)), int(m.group(2))
        for n in range(start, end + 1):
            numbers.add(n)

    # 개별: "5,8,9"
    for m in re.finditer(r"(\d+)", scope):
        n = int(m.group(1))
        if 1 <= n <= 30:  # 강/유닛 번호 범위
            numbers.add(n)

    return sorted(numbers)


def parse_grammar_word(docx_path):
    """어법수정 Word 파일(2열 테이블)에서 텍스트 추출.

    Args:
        docx_path: .docx 파일 경로

    Returns:
        리스트: [{"header": "1. L2-본문1", "text": "본문 텍스트..."}, ...]
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx 패키지가 필요합니다: pip install python-docx")

    doc = Document(docx_path)

    if not doc.tables:
        # 테이블 없으면 단락에서 추출
        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return [{"header": "전체", "text": "\n".join(lines)}] if lines else []

    results = []
    current_header = None
    current_text = []

    for table in doc.tables:
        for row in table.rows:
            # 좌측 셀 (문제 영역)
            left_text = row.cells[0].text.strip() if len(row.cells) > 0 else ""

            if not left_text:
                continue

            # 헤더 감지: "1. L2-본문1" 또는 "1. p2-no.18" 또는 "1. Special Lesson 1-본문1" 패턴
            is_header = bool(re.match(
                r"^\d+\.\s*(L\d+|p\d+|SL\d*|Special\s*Lesson\s*\d*)[-.]?(본문|p\.?\d|no\.?\s*\d|Read|Further)",
                left_text
            ))
            # "Reading", "Read More!" 같은 섹션 제목 스킵
            is_section = left_text in ("Reading", "Read More!", "Read More", "Read")

            # 지시문/교재명 스킵
            is_meta = (
                left_text.startswith("Q.") or
                left_text.startswith("영어") or
                left_text.startswith("공통영어") or
                left_text.startswith("고등_") or
                left_text.startswith("고1_") or
                left_text.startswith("고2_") or
                left_text.startswith("올림포스") or
                "어법수정" in left_text
            )

            if is_meta or is_section:
                continue

            if is_header:
                # 이전 블록 저장
                if current_header and current_text:
                    results.append({
                        "header": current_header,
                        "text": "\n".join(current_text)
                    })
                current_header = left_text
                current_text = []
            elif current_header:
                current_text.append(left_text)
            else:
                # 헤더 없이 본문이 시작된 경우
                current_header = "본문"
                current_text.append(left_text)

    # 마지막 블록 저장
    if current_header and current_text:
        results.append({
            "header": current_header,
            "text": "\n".join(current_text)
        })

    return results
