"""파이널 직전보충 -- 중요어휘 구글시트 자동 추출.

시험범위 시트에서 모의고사 문항번호를 파싱하고,
중요어휘 구글시트의 **시기별 워크시트**에서 해당 번호의 데이터를 가져온다.

구글시트 구조:
- 각 워크시트 이름 = "YY-MM" (예: "25-3", "24-10(완)")
- 특수 시트: "올림포스독해기본1", "올림포스독해기본2", "올림포스 독해기출"
- 각 시트: A열=문항번호(20~41), B열=중요어휘 텍스트
- 왼쪽(빈칸)/오른쪽(원문) 구분 없이 단일 시트에서 가져옴
"""

import csv
import io
import re
import time
import urllib.request
import unicodedata


# 중요어휘 구글시트 ID (고1/고2)
VOCAB_SHEET_IDS = {
    "고1": "1TDyN1qVYULNFYAI4ujStuYEcvsO1ySGJW4bLD6E55eQ",
    "고2": "1tDHMuLfHHpPUQpVnQGI2facI66pqbfdmMt5kWt59x8c",
}

# 시험범위 시트
SCOPE_SHEET_ID = "1oyY9NH1T6pkeG_RRSzCW5gpod60oXuEz-2sM6NaDcQc"
SCOPE_GID = 1967472064


def _fetch_csv(sheet_id, gid, timeout=20, retries=2):
    """구글시트를 CSV로 가져온다."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    for attempt in range(retries + 1):
        try:
            data = urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8")
            return list(csv.reader(io.StringIO(data)))
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            else:
                import sys
                print(f"[vocab_fetcher] CSV fetch failed (gid={gid}): {e}", file=sys.stderr)
                return []


def _discover_sheets(sheet_id):
    """구글시트 HTML에서 워크시트 목록(gid, name) 추출."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception:
        return []

    # HTML 내부 JSON에서 [idx,0,"GID",...,"SHEET_NAME"] 패턴 추출
    pattern = r'\[(\d+),0,\\"(\d+)\\".*?0,0,\\"([^\\"]+)\\"'
    matches = re.findall(pattern, data)
    sheets = []
    for _, gid, name in matches:
        sheets.append({"gid": int(gid), "name": name})
    return sheets


def _find_sheet_gid(sheets, year, month):
    """시트 목록에서 YY-MM에 해당하는 시트의 gid를 찾는다.

    시트 이름 형식: "25-3", "25-3(완)", "24-10(완)" 등
    """
    target = f"{year}-{month}"
    target_padded = f"{year}-{month.zfill(2)}"
    for s in sheets:
        name = s["name"]
        # "(완)" 등 접미어 제거
        clean = re.sub(r"\(.*?\)", "", name).strip()
        if clean == target or clean == target_padded:
            return s["gid"]
        # "25-03" vs "25-3" 비교
        if clean == f"{year}-{int(month)}":
            return s["gid"]
    return None


def _find_olympos_gid(sheets, grade):
    """올림포스 시트 gid 찾기."""
    results = {}
    for s in sheets:
        name = s["name"]
        name_lower = name.lower()
        if "올림포스" in name or "olympos" in name_lower:
            if "기출" in name:
                results["기출"] = s["gid"]
            elif "기본1" in name:
                results["기본1"] = s["gid"]
            elif "기본2" in name and "舊" not in name:
                results["기본2"] = s["gid"]
    return results


def parse_question_numbers(text):
    """모의고사 범위 텍스트에서 문항번호 리스트 추출."""
    numbers = set()
    for m in re.finditer(r"(\d+)\s*[~\-\u2013\u2014]\s*(\d+)", text):
        start, end = int(m.group(1)), int(m.group(2))
        for n in range(start, end + 1):
            numbers.add(n)
    for m in re.finditer(r"(?<!\d)(\d{2})(?!\d)", text):
        n = int(m.group(1))
        if 18 <= n <= 45:
            end_pos = m.end()
            if end_pos < len(text) and text[end_pos] in ("년", "월"):
                continue
            numbers.add(n)
    return sorted(numbers)


def parse_exam_info(text):
    """모의고사 범위 텍스트에서 시험 정보 추출."""
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or "미정" in line:
            continue
        m = re.search(r"고(\d)\s*(\d{2})년\s*(\d{1,2})월", line)
        if m:
            grade = f"고{m.group(1)}"
            year = m.group(2)
            month = m.group(3)
            numbers = parse_question_numbers(line)
            if numbers:
                results.append({
                    "grade": grade,
                    "year": year,
                    "month": month,
                    "numbers": numbers,
                    "raw": line.strip(),
                })
    return results


def fetch_scope_for_school(school, log=None):
    """시험범위 시트에서 특정 학교의 모의고사 범위를 가져온다."""
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        if log:
            log("[중요어휘] 시험범위 시트 접근 실패")
        return []

    school_nfc = unicodedata.normalize("NFC", school)
    base_name = re.sub(r"\d+$", "", school_nfc)
    grade_num = re.search(r"(\d+)$", school_nfc)
    grade_num = grade_num.group(1) if grade_num else ""

    target_row = None
    for r in rows:
        if not r or not r[0].strip():
            continue
        cell = unicodedata.normalize("NFC", r[0].strip())
        if (base_name + "고" + grade_num) in cell or (base_name + grade_num) in cell:
            target_row = r
            break

    if not target_row:
        if log:
            log(f"[중요어휘] 시험범위 시트에서 {school} 미발견")
        return []

    # 모의고사 컬럼 (인덱스 2)
    mockexam_text = target_row[2] if len(target_row) > 2 else ""
    exams = parse_exam_info(mockexam_text)

    if log and exams:
        for e in exams:
            log(f"[중요어휘] {e['grade']} {e['year']}년 {e['month']}월: {len(e['numbers'])}개 문항")

    return exams


def fetch_vocab_for_school(school, grade, log=None):
    """학교의 시험범위에 맞는 중요어휘를 자동 추출.

    각 모의고사 시기별 워크시트에서 해당 문항번호의 데이터를 수집.
    """
    # 1) 시험범위에서 모의고사 목록
    exams = fetch_scope_for_school(school, log)
    if not exams:
        if log:
            log(f"[중요어휘] {school}: 모의고사 범위 없음 -> 중요어휘 생략")
        return {"left_text": "", "right_text": ""}

    # 2) 시트 목록 가져오기
    sheet_id = VOCAB_SHEET_IDS.get(grade)
    if not sheet_id:
        if log:
            log(f"[중요어휘] {grade} 시트 ID 없음")
        return {"left_text": "", "right_text": ""}

    sheets = _discover_sheets(sheet_id)
    if not sheets:
        if log:
            log(f"[중요어휘] 워크시트 목록 가져오기 실패")
        return {"left_text": "", "right_text": ""}

    if log:
        sheet_names = [s["name"] for s in sheets]
        log(f"[중요어휘] 발견된 시트: {sheet_names}")

    # 3) 각 시험 시기별로 해당 시트에서 데이터 수집
    all_items = []  # [(yymmqq_code, text), ...]

    for exam in exams:
        yy = exam["year"]
        mm = exam["month"].zfill(2)
        numbers = exam["numbers"]

        gid = _find_sheet_gid(sheets, yy, exam["month"])
        if gid is None:
            if log:
                log(f"[중요어휘] 시트 {yy}-{exam['month']} 미발견 -> 건너뜀")
            continue

        rows = _fetch_csv(sheet_id, gid)
        if not rows:
            if log:
                log(f"[중요어휘] 시트 {yy}-{exam['month']} 데이터 없음")
            continue

        number_set = set(str(n) for n in numbers)
        found = 0
        for r in rows:
            if not r or not r[0].strip():
                continue
            code = r[0].strip()
            if code in number_set:
                text = r[1].strip() if len(r) > 1 else ""
                if text:
                    yymmqq = f"{yy}{mm}{code.zfill(2)}"
                    all_items.append((yymmqq, text))
                    found += 1

        if log:
            log(f"[중요어휘] {yy}년 {exam['month']}월: {found}/{len(numbers)}개 추출")

    if not all_items:
        if log:
            log(f"[중요어휘] 추출된 데이터 없음")
        return {"left_text": "", "right_text": ""}

    # 4) YYMMQQ 순으로 정렬 후 텍스트 조합
    all_items.sort(key=lambda x: x[0])

    # 왼쪽(상단)과 오른쪽(하단)에 동일 텍스트가 들어감
    # 단락스타일이 빈칸/정답 표시를 처리함
    # 각 항목: "YYMMQQ\n본문텍스트(N[단어] 포함)\n\n>>내용요약\n요약텍스트"
    parts = []
    for code, text in all_items:
        parts.append(f"{code}\n{text}")

    combined = "\n\n".join(parts)

    result = {
        "left_text": combined,
        "right_text": combined,  # 양쪽 동일
    }

    if log:
        log(f"[중요어휘] 최종: {len(all_items)}개 지문")

    return result
