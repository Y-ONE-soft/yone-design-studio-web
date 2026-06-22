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
    # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
    from engines.final.extractor import _resolve_local_mirror as _rlm
    textbook_base = _rlm(textbook_base, None)

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
        # 과 번호 추출 (1과 → 1, S1과 → S1, "Project 1" → "Project 1")
        lesson_num = re.sub(r"과$", "", lesson.strip())

        # 과 폴더 찾기
        lesson_dir = None
        # Project N 단원 매칭 (예: "Project 1" → "공통영어1 YBM(김) Project 1")
        m_proj = re.match(r"(?:Project|PROJECT)\s*(\d+)", lesson_num)
        for d in os.listdir(publisher_dir):
            dn = _nfc(d)
            if not os.path.isdir(os.path.join(publisher_dir, d)):
                continue
            if m_proj:
                proj_num = m_proj.group(1)
                if f"Project {proj_num}" in dn or f"Project{proj_num}" in dn:
                    lesson_dir = os.path.join(publisher_dir, d)
                    break
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
                # "문제지" 표기 + "_문제.docx" 표기 모두 허용 (파일명 오타 대응)
                if ("어법수정" in fn and ("문제지" in fn or fn.endswith("_문제.docx"))
                        and fn.endswith(".docx")
                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                    full_path = os.path.join(root, f)
                    found_files.append(full_path)
                    if log:
                        log(f"  [어법수정] {lesson}: {fn}")

    return found_files


def find_mockexam_grammar_files(content_base, scope_text, grade, log=None):
    """모의고사 작업 폴더에서 어법수정 Word 파일 탐색.

    복합 scope (예: "26년3월,25년6월")는 모든 (yy, mm) 페어를 각각 처리한다.

    Args:
        content_base: 내신대비 루트
        scope_text: 시험범위 텍스트 (예: "25년10월", "26년3월,25년6월", "모의고사25.3")
        grade: "고1" 또는 "고2"
        log: 로그 콜백

    Returns:
        [(path, "YYMM"), ...] — yymm 4자리 문자열로 시기를 식별
    """
    # scope에서 모든 (년도+월) 페어 추출 (복합 scope 대응)
    pairs = []
    seen = set()
    for m in re.finditer(r"(\d{2})년\s*(\d{1,2})월", _nfc(scope_text)):
        key = (m.group(1), m.group(2))
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    if not pairs:
        for m in re.finditer(r"모의고사\s*(\d{2})\.(\d{1,2})", _nfc(scope_text)):
            key = (m.group(1), m.group(2))
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    if not pairs:
        if log:
            log(f"  [어법수정] 모의고사 년월 추출 실패: {scope_text}")
        return []

    mock_base = os.path.join(content_base, "모의고사 작업", grade)
    # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
    from engines.final.extractor import _resolve_local_mirror as _rlm
    mock_base = _rlm(mock_base, None)
    if not os.path.isdir(mock_base):
        if log:
            log(f"  [어법수정] 모의고사 폴더 없음: {mock_base}")
        return []

    found = []
    for year, month in pairs:
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
            continue

        yymm = f"{year}{int(month):02d}"

        # 폴더 내 + 직전보충 하위에서 어법수정 문제지 찾기.
        # 표준 파일: "..._어법수정_문제지.docx"
        # 변형 파일: "41~42번 어법수정.docx" 같이 특정 문항범위만 다루는 보충 파일도 포함.
        for root, dirs, files in os.walk(target_folder):
            for f in files:
                fn = _nfc(f)
                if not (fn.endswith(".docx") and "어법수정" in fn
                        and not fn.startswith("~")
                        and "정답" not in fn and "해설" not in fn):
                    continue
                is_standard = "문제지" in fn or fn.endswith("_문제.docx")
                is_range_variant = bool(
                    re.match(r"^\d+(?:\s*[~\-\u2013\u2014]\s*\d+)?\s*번\s*어법수정", fn)
                )
                if not (is_standard or is_range_variant):
                    continue
                full_path = os.path.join(root, f)
                found.append((full_path, yymm))
                if log:
                    log(f"  [어법수정] 모의고사 {year}년 {month}월: {fn}")

    return found


def find_mothertongue_grammar_files(content_base, grade, log=None):
    """마더텅 예전 기출 어법수정 Word 파일 탐색.

    경로: 모의고사 작업/{grade}/한영{grade} 마더텅 예전 기출/{N}강 .../*어법수정_문제지.docx

    Returns: [(path, section_num), ...]
    """
    grade_num = grade.replace("\uace0", "") if grade else ""
    mt_base = os.path.join(content_base, "\ubaa8\uc758\uace0\uc0ac \uc791\uc5c5", grade)
    # \ubbf8\ub7ec redirect \u2014 Drive zombie \uc2dc GDrive listdir EDEADLK \ud68c\ud53c
    from engines.final.extractor import _resolve_local_mirror as _rlm
    mt_base = _rlm(mt_base, None)
    if not os.path.isdir(mt_base):
        return []
    target_folder = None
    for d in os.listdir(mt_base):
        dn = _nfc(d)
        if "\ub9c8\ub354\ud145 \uc608\uc804 \uae30\ucd9c" in dn and f"\ud55c\uc601\uace0{grade_num}" in dn:
            target_folder = os.path.join(mt_base, d)
            break
    if not target_folder:
        return []
    found = []
    for sub in os.listdir(target_folder):
        subn = _nfc(sub)
        m = re.match(r"^(\d+)\uac15\s", subn)
        if not m:
            continue
        section = int(m.group(1))
        sub_dir = os.path.join(target_folder, sub)
        if not os.path.isdir(sub_dir):
            continue
        for f in os.listdir(sub_dir):
            fn = _nfc(f)
            if ("\uc5b4\ubc95\uc218\uc815" in fn and "\ubb38\uc81c\uc9c0" in fn and fn.endswith(".docx")
                    and not fn.startswith("~") and "\uc815\ub2f5" not in fn and "\ud574\uc124" not in fn):
                found.append((os.path.join(sub_dir, f), section))
                if log:
                    log(f"  [\uc5b4\ubc95\uc218\uc815] \ub9c8\ub354\ud145 {section}\uac15: {fn}")
    return found


def find_mockexam_grammar_files_by_codes(content_base, grade, passage_codes=None, log=None):
    """모의고사 어법수정 Word 파일 수집.

    passage_codes: ["190920", "250620", ...] 워크북에서 추출된 YYMMQQ 리스트.
                   None 또는 빈 값이면 해당 학년의 **모든 YY년 MM월 폴더**를 탐색.

    Returns: [(path, yymm), ...]
    """
    mock_base = os.path.join(content_base, "\ubaa8\uc758\uace0\uc0ac \uc791\uc5c5", grade)
    if not os.path.isdir(mock_base):
        return []
    yymm_set = set()
    if passage_codes:
        for code in passage_codes:
            code = str(code).strip()
            if len(code) != 6 or not code.isdigit():
                continue
            yymm_set.add(code[:4])
    # passage_codes 없으면 전체 년월 폴더 스캔
    found_files = []
    seen_paths = set()
    for d in os.listdir(mock_base):
        dn = _nfc(d)
        m = re.search(r"(\d{2})\s*\ub144\s*(\d{1,2})\s*\uc6d4", dn)
        if not m:
            continue
        yy = m.group(1)
        mm_int = m.group(2)
        mm = mm_int.zfill(2)
        yymm = f"{yy}{mm}"
        if yymm_set and yymm not in yymm_set:
            continue
        target = os.path.join(mock_base, d)
        if not os.path.isdir(target):
            continue
        for root, dirs, files in os.walk(target):
            for f in files:
                fn = _nfc(f)
                if not (fn.endswith(".docx") and "\uc5b4\ubc95\uc218\uc815" in fn
                        and not fn.startswith("~")
                        and "\uc815\ub2f5" not in fn and "\ud574\uc124" not in fn):
                    continue
                is_standard = "\ubb38\uc81c\uc9c0" in fn
                is_range_variant = bool(
                    re.match(r"^\d+(?:\s*[~\-\u2013\u2014]\s*\d+)?\s*\ubc88\s*\uc5b4\ubc95\uc218\uc815", fn)
                )
                if not (is_standard or is_range_variant):
                    continue
                full_path = os.path.join(root, f)
                if full_path in seen_paths:
                    continue
                seen_paths.add(full_path)
                found_files.append((full_path, yymm))
                if log:
                    log(f"  [\uc5b4\ubc95\uc218\uc815] {yy}\ub144 {mm_int}\uc6d4: {fn}")
    return found_files


def find_ebs_grammar_files(content_base, scope_text, log=None, grade=None):
    """EBS 작업 폴더에서 어법수정 Word 파일 탐색.

    Args:
        content_base: 내신대비 루트
        scope_text: 시험범위 텍스트 (예: "올포1-4강", "리딩파워1,2강")
        log: 로그 콜백
        grade: "고1"/"고2"/"고3" — 올림포스 독해기본1 vs 2 구분용

    Returns:
        발견된 파일 튜플 리스트 [(path, 강번호), ...]
        강번호는 정수 (예: 2, 3, 4). 헤더 생성("올포 N강 본문M") 용도.
    """
    ebs_base = os.path.join(content_base, "EBS 작업")
    if not os.path.isdir(ebs_base):
        return []

    scope = _nfc(scope_text)
    found = []

    # 올림포스 독해기본1 (고1) / 2 (고2) — "올포"(약어)·"올림포스"(정식) 모두 인식
    # (혼합 scope "올림포스15~18강,미래엔3,4과"는 호출부에서 올림포스 부분만 잘라 전달)
    if "올포" in scope or "올림포스" in scope:
        # 강 번호 추출 (예: "올포1-4강" → [1,2,3,4], "올포5,8,9강" → [5,8,9])
        units = _extract_unit_numbers(scope)
        # 고1 → 기본1, 고2 → 기본2 (명시적 매칭)
        target_suffix = None
        if grade == "\uace01":
            target_suffix = "\ub3c5\ud574\uae30\ubcf81"
        elif grade == "\uace02":
            target_suffix = "\ub3c5\ud574\uae30\ubcf82"
        olympos_base = None
        # grade 명시: 해당 버전만 선택
        if target_suffix:
            for d in os.listdir(ebs_base):
                dn = _nfc(d)
                if "\uc62c\ub9bc\ud3ec\uc2a4" in dn and target_suffix in dn:
                    olympos_base = os.path.join(ebs_base, d)
                    break
        # grade 미지정 또는 매칭 실패 시: 첫 매칭 폴더 사용 (기존 동작)
        if not olympos_base:
            for d in os.listdir(ebs_base):
                dn = _nfc(d)
                if "\uc62c\ub9bc\ud3ec\uc2a4" in dn and "\ub3c5\ud574\uae30\ubcf8" in dn:
                    olympos_base = os.path.join(ebs_base, d)
                    break

        if olympos_base:
            for unit_num in units:
                # "올림포스 독해기본1 5강" 형태의 폴더 (정확한 매칭: 단어 경계)
                # "1강"이 "11강"을 부분 매칭하지 않도록 정규식 사용
                _unit_pat = re.compile(rf"(?<!\d){unit_num}\uAC15(?!\d)")
                for d in os.listdir(olympos_base):
                    dn = _nfc(d)
                    if _unit_pat.search(dn):
                        unit_dir = os.path.join(olympos_base, d)
                        # 직접 하위 또는 워크북 하위에서 찾기
                        for root, dirs, files in os.walk(unit_dir):
                            for f in files:
                                fn = _nfc(f)
                                # "문제지" 표기 + "_문제.docx" 표기 모두 허용 (파일명 오타 대응)
                                if ("어법수정" in fn and ("문제지" in fn or fn.endswith("_문제.docx"))
                                        and fn.endswith(".docx")
                                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                                    found.append((os.path.join(root, f), unit_num))
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
            # 중복 파일 방지 (예: "Unit 9~11 Example" + "Unit 9~11 Example 제외" 두 디렉토리 모두 매칭될 때
            # 같은 파일이 여러 번 append되지 않도록)
            _processed_paths = set()
            for unit_num in units:
                # "Unit 9" / "unit9" 정확 매칭 또는 "Unit 9~11" / "Unit 9-11" 범위 매칭
                # (예: "Unit 9~11 Example 워크북" 디렉토리는 Unit 9, 10, 11 모두 해당)
                _unit_rng_pat = re.compile(rf"Unit\s*(\d+)\s*[~\-]\s*(\d+)", re.IGNORECASE)
                _unit_exact_pat = re.compile(rf"Unit\s*{unit_num}(?!\d)", re.IGNORECASE)
                for d in os.listdir(rp_base):
                    # 디렉토리만 대상 (".indd", ".pdf" 같은 파일 스킵)
                    full_path = os.path.join(rp_base, d)
                    if not os.path.isdir(full_path):
                        continue
                    dn = _nfc(d)
                    _matched = False
                    # 1) 범위 패턴 우선 ("Unit 9~11" 디렉토리가 unit_num=10, 11도 포함)
                    _rng = _unit_rng_pat.search(dn)
                    if _rng:
                        _rs, _re = int(_rng.group(1)), int(_rng.group(2))
                        if _rs <= unit_num <= _re:
                            _matched = True
                    # 2) 정확 단일 매칭 ("Unit 9")
                    if not _matched and _unit_exact_pat.search(dn):
                        _matched = True
                    if _matched:
                        # 각 매칭 디렉토리의 어법수정 파일 수집
                        # (Example + Example 제외 별도 디렉토리라면 둘 다 처리)
                        for root, dirs, files in os.walk(full_path):
                            for f in files:
                                fn = _nfc(f)
                                if ("어법수정" in fn and fn.endswith(".docx")
                                        and not fn.startswith("~") and "정답" not in fn and "해설" not in fn):
                                    file_path = os.path.join(root, f)
                                    if file_path in _processed_paths:
                                        continue
                                    _processed_paths.add(file_path)
                                    found.append((file_path, unit_num))
                                    if log:
                                        log(f"  [어법수정] 리딩파워 Unit{unit_num}: {fn} ({_nfc(d)})")

    return found


def find_external_ted_grammar_files(content_base, grade, school, exam_period, log=None):
    """TED 외부지문 어법수정 Word 파일 탐색.

    경로: 2026년/{grade}/{full_school}/1. {exam_period}/외부지문 TED/*어법수정_문제지.docx

    학교명 매칭: "명일2" → "명일여고2" 같이 '고'/'여고' 포함/미포함 모두 시도.

    Returns:
        [path, ...] — 어법수정 Word 경로 리스트 (보통 0~1개)
    """
    year_base = os.path.join(content_base, "2026\ub144", grade)
    if not os.path.isdir(year_base):
        return []
    # 학교 폴더 후보 탐색
    candidate_dirs = []
    school_nfc = _nfc(school or "")
    base_name = re.sub(r"\d+$", "", school_nfc)
    grade_num = re.search(r"(\d+)$", school_nfc)
    grade_num = grade_num.group(1) if grade_num else ""
    for d in os.listdir(year_base):
        dn = _nfc(d)
        if (
            dn == school_nfc
            or dn == f"{base_name}\uace0{grade_num}"
            or dn == f"{base_name}\uc5ec\uace0{grade_num}"
            or dn.startswith(base_name)
        ):
            candidate_dirs.append(os.path.join(year_base, d))
    found = []
    for school_dir in candidate_dirs:
        # 시험 시기 폴더: "1. 26-1-중간" / "2. 26-1-기말" 등
        for sd in os.listdir(school_dir):
            sdn = _nfc(sd)
            if exam_period and exam_period not in sdn:
                continue
            ted_dir = os.path.join(school_dir, sd, "\uc678\ubd80\uc9c0\ubb38 TED")
            if not os.path.isdir(ted_dir):
                continue
            for f in os.listdir(ted_dir):
                fn = _nfc(f)
                if ("\uc5b4\ubc95\uc218\uc815" in fn and "\ubb38\uc81c\uc9c0" in fn and fn.endswith(".docx")
                        and not fn.startswith("~") and "\uc815\ub2f5" not in fn and "\ud574\uc124" not in fn):
                    full = os.path.join(ted_dir, f)
                    found.append(full)
                    if log:
                        log(f"  [\uc5b4\ubc95\uc218\uc815] TED: {fn}")
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


def parse_grammar_word(docx_path, auto_unit_base=None):
    """어법수정 Word 파일(2열 테이블)에서 텍스트 추출.

    Args:
        docx_path: .docx 파일 경로
        auto_unit_base: Chapter 헤더 없는 파일에 대해 페이지 번호 점프로 Unit 자동 증가.
            첫 Unit 번호 (예: 9). page 차이 >= 3이면 current_unit += 1.

    Returns:
        리스트: [{"header": "1. L2-본문1", "text": "본문 텍스트...", "unit": 9}, ...]
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
    current_unit = None  # "Chapter 03. 추론적 이해 - 09 빈칸 추론 (1)" 같은 헤더에서 추출한 Unit 번호
    _saw_chapter = False  # Chapter 헤더 1회 이상 감지 여부 (이 경우 page 점프 분배 비활성)
    _prev_page = None    # 직전 블록의 페이지 번호 (자동 Unit 증가용)

    for table in doc.tables:
        for row in table.rows:
            # 좌측 셀 (문제 영역)
            left_text = row.cells[0].text.strip() if len(row.cells) > 0 else ""

            if not left_text:
                continue

            # 헤더 감지: 다음 패턴
            # - "1. L2-본문1" (교과서)
            # - "1. p2-no.18" (모의고사)
            # - "1. p8-Example 1" (리딩파워 Example)
            # - "1. Special Lesson 1-본문1" (교과서 SL)
            # - "1. p60-수능 대비 ANALYSIS" (EBS 올림포스 분석)
            # - "5. p65-서술형 Practice" (EBS 올림포스 서술형)
            # - "6. p66-논술형 Practice" (EBS 올림포스 논술형)
            # - "1. p3강-no.4번 190920" (마더텅 예전 기출 — 헤더 끝에 YYMMQQ)
            # - "1. TED 1-no.1" (TED 외부지문)
            is_header = bool(re.match(
                r"^\d+\.\s*(L\d+|p\d+|SL\d*|Special\s*Lesson\s*\d*|TED\s*\d*|PROJECT\s*\d+|Project\s*\d+)[-.]?(\ubcf8\ubb38|p\.?\d|no\.?\s*\d|Read|Further|"
                r"\uc218\ub2a5\s*\ub300\ube44\s*ANALYSIS|ANALYSIS|"
                r"Example\s*\d+|"
                r"\uc11c\uc220\ud615\s*Practice|\ub17c\uc220\ud615\s*Practice|Practice)",
                left_text
            ))
            # 마더텅 예전 기출 헤더 — "1. p3강-no.4번 190920"
            is_mt_header = bool(re.match(
                r"^\d+\.\s*p\d*\uac15\-no\.?\s*\d+\s*\ubc88\s*\d{6}\s*$",
                left_text
            ))
            if is_mt_header:
                is_header = True
            # "Reading", "Read More!" 같은 섹션 제목 스킵 (대소문자 무관)
            is_section = left_text.strip().upper() in ("READING", "READ MORE!", "READ MORE", "READ")

            # "Chapter XX. ... - NN 빈칸 추론 (N)" 패턴에서 NN을 Unit 번호로 추출
            # (예: "Chapter 03. 추론적 이해 - 09 빈칸 추론 (1)" → Unit 9)
            m_unit = re.match(r"^Chapter\s+\d+\.\s*.+?\s*[-\u2013\u2014]\s*0?(\d+)\s+", left_text)
            if m_unit:
                # Chapter 헤더 전환 — 이전 블록은 *이전* current_unit으로 먼저 저장
                # (그렇지 않으면 다음 헤더에서 저장 시 새 unit으로 덮여씀)
                if current_header and current_text:
                    _block = {"header": current_header, "text": "\n".join(current_text)}
                    if current_unit is not None:
                        _block["unit"] = current_unit
                    results.append(_block)
                    current_header = None
                    current_text = []
                current_unit = int(m_unit.group(1))
                _saw_chapter = True
                continue  # Chapter 헤더는 본문으로 저장하지 않음

            # 지시문/교재명/챕터 제목 스킵
            # - "ReadingPower 유형편완성(2017) - Unit 03" (교재명)
            # - "Chapter 01. 대의 파악 - 03 목적" (다른 Chapter 형식)
            # \uc120\ud589 \ubd88\ub9bf/\ub9c8\ucee4 \uc81c\uac70 \ud6c4 \uba54\ud0c0 \ud310\uc815. \uc77c\ubd80 \uc6d0\uace0\ub294 \uad50\uc7ac\uba85 \uc81c\ubaa9 \uc55e\uc5d0 '\u3134'(U+3134
            # \ud55c\uae00 \ud638\ud658 \uc790\ubaa8, \uc11c\ube0c\ubd88\ub9bf \uc6a9\ub3c4)\uc744 \ubd99\uc778\ub2e4. \uc548 \ub5bc\uba74 "\u3134\uacf5\ud1b5\uc601\uc5b41_\ubbf8\ub798\uc5d4\uae40\uc131\uc5f0 -
            # Lesson 4..." \uc81c\ubaa9\uc904\uc774 startswith \uba54\ud0c0 \uc2a4\ud0b5\uc744 \ud1b5\uacfc \ubabb \ud574 \uc720\ub839 '\ubcf8\ubb38' \ube14\ub85d\uc774
            # \uc0dd\uae30\uace0 \uc2e4\uc81c \ubcf8\ubb38 \ubc88\ud638\uac00 \ud55c \uce78\uc529 \ubc00\ub9b0\ub2e4(\uc0c1\uc77c1 4\uacfc). \ud638\ud658 \uc790\ubaa8(U+3130~318F)\uc640
            # \uac00\uc6b4\ub383\uc810/\ud654\uc0b4\ud45c \ub4f1 \uc120\ud589 \ub9c8\ucee4\ub9cc \uc81c\uac70 \u2014 \ubcf8\ubb38(\u300a\uc81c\ubaa9\u300b/\uc601\ubb38)\uc740 \uc601\ud5a5 \uc5c6\ub2e4.
            _lt_meta = re.sub(r"^[\s\u3130-\u318f\u2022\u00b7\u21b3\u2192\u25b6]+", "", left_text)
            is_meta = (
                _lt_meta.startswith("Q.") or
                _lt_meta.startswith("\uc601\uc5b4") or
                _lt_meta.startswith("\uacf5\ud1b5\uc601\uc5b4") or
                _lt_meta.startswith("\uace0\ub4f1_") or
                _lt_meta.startswith("\uace01_") or
                _lt_meta.startswith("\uace02_") or
                _lt_meta.startswith("\uc62c\ub9bc\ud3ec\uc2a4") or
                _lt_meta.startswith("ReadingPower") or
                bool(re.match(r"^Chapter\s+\d+", _lt_meta)) or
                "\ud6a8\ud615\ud3b8" in left_text or
                "\uc5b4\ubc95\uc218\uc815" in left_text
            )

            if is_meta or is_section:
                continue

            if is_header:
                # 이전 블록 먼저 저장 (현재 current_unit으로)
                if current_header and current_text:
                    _block = {"header": current_header, "text": "\n".join(current_text)}
                    if current_unit is not None:
                        _block["unit"] = current_unit
                    results.append(_block)
                # 현재 헤더의 페이지 번호로 Unit 자동 증가 (Chapter 헤더 없는 파일용)
                # (예: Example 제외 파일 p68-p71(9강) → p74-p77(10강) → p80-p81(11강))
                if auto_unit_base is not None and not _saw_chapter:
                    _m_pg = re.search(r"p(\d+)", left_text)
                    if _m_pg:
                        _cur_page = int(_m_pg.group(1))
                        if current_unit is None:
                            current_unit = auto_unit_base
                        elif _prev_page is not None and (_cur_page - _prev_page) >= 3:
                            current_unit += 1
                        _prev_page = _cur_page
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
        _block = {"header": current_header, "text": "\n".join(current_text)}
        if current_unit is not None:
            _block["unit"] = current_unit
        results.append(_block)

    return results


def parse_external_grammar_docx(docx_path):
    """외부지문/추가지문 어법수정 '원고(docx)'를 업로드 기반으로 파싱.

    외부/추가 지문은 매번 출처·형식·제목이 달라지므로(예전 'TED'도 그때의 제목일
    뿐) 폴더 경로/형식/헤더를 하드코딩하지 않는다. 원고의 단락을 순서대로 읽어
    '번호. <페이지/레슨 마커> <라벨>' 형태의 지문 헤더를 감지하고, **라벨을 원고에서
    그대로 유도**한다.

    예) '1. L4-p. 83 본문 1'              → label '본문1'
        '8. L4-p. 99 Reading about Bio-Engine' → label 'Reading about Bio-Engine'

    표(2열)/단락 어느 구조든 대응하도록 document.xml의 <w:t>를 단락(<w:p>) 단위로
    모아 처리한다(parse_grammar_word는 2열 표 전용이라 이 형식을 1블록으로 뭉친다).

    Returns:
        [{"label": "본문1"|"Reading about Bio-Engine"|..., "text": "지문(어법마커 N[..] 포함)"}]
    """
    import zipfile
    import html
    try:
        xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return []
    paras = []
    for blk in re.split(r"</w:p>", xml):
        ts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", blk)
        line = html.unescape(_nfc("".join(ts))).strip()
        if line:
            paras.append(line)

    # 지문 헤더: 선행 순번 + (임의의 페이지/레슨 마커) + 줄 끝 라벨.
    # 라벨은 '본문 N' 또는 Reading/Read More/Further(추가 읽기) 류. 특정 교재/형식에
    # 의존하지 않도록 가운데 마커는 .*?로 흘려보낸다.
    HDR = re.compile(
        r"^\d+\.\s+.*?\s(본문\s*\d+|Reading\b.*|Read\s*More.*|Further[^\n]*)$",
        re.IGNORECASE,
    )
    # 페이지/출처 마커가 'no.N'으로 끝나는 형식(예 '1. p1-no.1', '1. TED 1-no.1') →
    # 라벨을 '본문N'(no.N 번호)으로 유도. 해설지/문제지 모두 이 헤더를 쓸 수 있다.
    HDR_NO = re.compile(r"^\d+\.\s+.*?no\.?\s*(\d+)\s*$", re.IGNORECASE)

    # 서두(첫 헤더 전) 단락 = 교재 제목·발문 등. 본문 사이에 반복되는 러닝 제목을
    # 본문에 섞지 않도록 제거 기준으로 사용.
    _preamble = set()
    for p in paras:
        if HDR.match(p) or HDR_NO.match(p):
            break
        _preamble.add(p)

    def _is_korean(s):
        han = sum(1 for ch in s if "가" <= ch <= "힣")
        return han > 0 and han > 0.3 * max(1, len(s.replace(" ", "")))

    def _to_problem(s):
        # 해설지 어법 마커 'N[오답 (정답)]' → 문제지 형식 'N[오답]'
        # (문제지는 괄호가 없어 무영향)
        return re.sub(r"\[([^\[\]]*?)\s*\([^()]*\)\]", r"[\1]", s)

    out = []
    label = None
    buf = []
    for p in paras:
        m = HDR.match(p)
        mno = None if m else HDR_NO.match(p)
        if m or mno:
            if label is not None:
                out.append({"label": label, "text": "\n".join(buf).strip()})
            if m:
                raw = m.group(1).strip()
                # '본문 1' → '본문1' (그 외 라벨은 공백 보존)
                label = re.sub(r"본문\s*(\d+)", r"본문\1", raw)
            else:
                label = f"본문{mno.group(1)}"
            buf = []
        elif label is not None:
            # 러닝 제목(서두 반복)·한글 번역 단락 제외 — 어법수정은 영어 지문만.
            if p in _preamble or _is_korean(p):
                continue
            buf.append(_to_problem(p))
    if label is not None:
        out.append({"label": label, "text": "\n".join(buf).strip()})
    return out
