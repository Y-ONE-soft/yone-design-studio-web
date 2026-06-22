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


def _norm_qcode(c):
    """문항번호 정규화: '41-42', '41~42', '41' 모두 '41'로 통일.

    모의고사 41~42번 복합문항은 어휘/요약 시트에 '41-42', '41~42', 또는 '41'로
    표기될 수 있으므로 첫 번째 숫자만 추출해 매칭 키로 사용한다.
    """
    if c is None:
        return ""
    m = re.match(r"^\s*(\d+)", str(c))
    return m.group(1) if m else str(c).strip()


def _qcode_to_yymmqq(yy, mm, raw_code):
    """문항번호 raw → 'YYMMQQ' 또는 'YYMMQQ~RR' 헤더 생성.

    raw_code가 '41-42' / '41~42'면 'YYMM41~42'로 보존, 단일 숫자면 'YYMMQQ'.
    """
    s = str(raw_code).strip()
    m_range = re.match(r"^\s*(\d+)\s*[~\-–—]\s*(\d+)\s*$", s)
    if m_range:
        qq1 = m_range.group(1).zfill(2)
        qq2 = m_range.group(2).zfill(2)
        return f"{yy}{mm}{qq1}~{qq2}"
    qq = _norm_qcode(s).zfill(2)
    return f"{yy}{mm}{qq}"


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


def _find_mothertongue_gid(sheets):
    """마더텅 시트 gid 찾기."""
    for s in sheets:
        if s["name"].strip() == "\ub9c8\ub354\ud145":
            return s["gid"]
    return None


def _fetch_mothertongue_vocab(sheet_id, mt_map):
    """마더텅 시트에서 YYMMQQ → 중요어휘 매핑 구축.

    시트 구조: "N강" 행 + 다음 행에 "1번", "2번", ... 열별 중요어휘 텍스트.
    _MT_MAP[N][seq] = YYMMQQ 와 조합해 최종 {yymmqq: text} 맵 반환.
    """
    if not mt_map:
        return {}
    sheets = _discover_sheets(sheet_id)
    mt_gid = _find_mothertongue_gid(sheets)
    if mt_gid is None:
        return {}
    rows = _fetch_csv(sheet_id, mt_gid)
    if not rows:
        return {}
    result = {}
    i = 0
    while i < len(rows) - 1:
        header = rows[i]
        data = rows[i + 1]
        if not header or not header[0]:
            i += 1
            continue
        m = re.match(r"^(\d+)\uac15$", header[0].strip())
        if not m:
            i += 1
            continue
        section = int(m.group(1))
        for j in range(1, min(len(header), len(data))):
            num_m = re.match(r"^(\d+)\ubc88$", header[j].strip())
            if not num_m:
                continue
            seq = int(num_m.group(1))
            text = data[j].strip()
            if not text:
                continue
            yymmqq = mt_map.get(section, {}).get(seq)
            if yymmqq:
                result[yymmqq] = text
        i += 2
    return result


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


def _find_scope_row(rows, school, exam_period=None):
    """시험범위 시트에서 학교명 행을 찾아 반환.

    시트에는 같은 학교가 '26-1-기말' 섹션과 '26-1-중간' 섹션에 각각 존재한다
    (예: 한영고2 기말=6월 모의고사, 중간=3월 모의고사). exam_period가 주어지면
    해당 섹션 헤더 아래의 학교 행만 매칭한다. 형식: '26-1-기말'/'26-1-중간'
    (워크북 폴더명과 동일). 섹션을 못 찾거나 exam_period 없으면 기존 동작
    (섹션 무관 첫 매칭)으로 폴백.
    """
    school_nfc = unicodedata.normalize("NFC", school)
    base_name = re.sub(r"\d+$", "", school_nfc)
    grade_num = re.search(r"(\d+)$", school_nfc)
    grade_num = grade_num.group(1) if grade_num else ""

    def _matches(cell):
        return (
            (base_name + "\uace0" + grade_num) in cell
            or (base_name + grade_num) in cell
            or (base_name + "\uc5ec\uace0" + grade_num) in cell
        )

    period_nfc = unicodedata.normalize("NFC", (exam_period or "").strip())
    target_section = (
        period_nfc if re.match(r"^\d{2}-\d-(\uc911\uac04|\uae30\ub9d0)$", period_nfc) else None
    )

    # 1\uc21c\uc704: exam_period \uc139\uc158 \uc548\uc5d0\uc11c\ub9cc \ud559\uad50 \ud589 \ud0d0\uc0c9
    if target_section:
        cur_section = None
        for r in rows:
            if not r or not r[0].strip():
                continue
            cell = unicodedata.normalize("NFC", r[0].strip())
            if re.match(r"^\d{2}-\d-(\uc911\uac04|\uae30\ub9d0)$", cell):
                cur_section = cell
                continue
            if cur_section == target_section and _matches(cell):
                return r

    # 2\uc21c\uc704(\ud3f4\ubc31): \uc139\uc158 \ubb34\uad00 \uccab \ub9e4\uce6d (\uae30\uc874 \ub3d9\uc791)
    for r in rows:
        if not r or not r[0].strip():
            continue
        cell = unicodedata.normalize("NFC", r[0].strip())
        if _matches(cell):
            return r
    return None


def fetch_high3_scope(school, log=None, exam_period=None):
    """\uace03 \ud559\uad50\uc758 \uc218\ub2a5\ud2b9\uac15/\ubd80\uad50\uc7ac \ubc94\uc704\ub97c \uad6c\uae00\uc2dc\ud2b8\uc5d0\uc11c \uc870\ud68c.

    \uc2dc\ud5d8\ubc94\uc704 \uc2dc\ud2b8\uc758 [3] \ucef4\ub7fc ("\ubd80\uad50\uc7ac \ubc0f \uc218\ub2a5\ud2b9\uac15")\uc744 \ud30c\uc2f1.
    \uc608: "* \uc218\ub2a5\ud2b9\uac15 \uc601\uc5b4 \uc720\ud615\ud3b8(40\uc9c0\ubb38): 3,6,7,11,12,13,14,16,17,18\uac15 (Gateway \uc81c\uc678)"

    Returns:
        {
            "lectures": ["3", "6", "7", "11", "12", "13", "14", "16", "17", "18"],
            "tests": [],
            "exclude_gateway": True,
            "raw": "\uc6d0\ubb38 \ud14d\uc2a4\ud2b8"
        }
    """
    empty = {
        "lectures": [], "tests": [], "exclude_gateway": False, "raw": "",
        "textbook_lessons": [], "textbook_raw": "",
        "lecture_details": {}, "lecture_exclude": {},
    }
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        if log:
            log("[\uace03 \ubc94\uc704] \uc2dc\ud5d8\ubc94\uc704 \uc2dc\ud2b8 \uc811\uadfc \uc2e4\ud328")
        return empty

    target_row = _find_scope_row(rows, school, exam_period)
    if not target_row:
        if log:
            log(f"[\uace03 \ubc94\uc704] \uc2dc\ud5d8\ubc94\uc704 \uc2dc\ud2b8\uc5d0\uc11c {school} \ubbf8\ubc1c\uacac")
        return empty

    raw = target_row[3] if len(target_row) > 3 else ""
    raw = unicodedata.normalize("NFC", raw).strip()

    # [1] 교과서 컬럼 파싱 — 예: "* (15개정)영어 독해와 작문 비상(김) 2과"
    # 과 번호가 명시돼 있으면 그 과들만, 생략이면 교과서 전체 포함
    textbook_raw = target_row[1] if len(target_row) > 1 else ""
    textbook_raw = unicodedata.normalize("NFC", textbook_raw).strip()
    textbook_lessons = []
    if textbook_raw:
        for m in re.finditer(r"(\d+(?:\s*,\s*\d+)*)\s*\uacfc", textbook_raw):
            for p in m.group(1).split(","):
                p = p.strip()
                if p.isdigit():
                    textbook_lessons.append(p)
        _seen_t = set()
        textbook_lessons = [l for l in textbook_lessons if not (l in _seen_t or _seen_t.add(l))]
        textbook_lessons.sort(key=int)

    if not raw and not textbook_raw:
        if log:
            log(f"[\uace03 \ubc94\uc704] {school} \ubd80\uad50\uc7ac/\uad50\uacfc\uc11c \ucef4\ub7fc \ube48 \uac12")
        return empty

    lectures = []
    # "17, 18, 21~30강" 처럼 단일+범위가 한 '강' 접미사를 공유하는 목록을 통째 파싱.
    # (기존엔 범위 "21~30강"을 먼저 제거한 뒤 단일을 파싱했는데, '강'이 범위에만
    #  붙어 있으면 앞쪽 단일 "17, 18"이 '강' 앵커를 잃어 통째로 누락됐다 — 광문3 17·18강.)
    _LEC_ITEM = r"\d+\s*[-~\u2013\u2014]\s*\d+|\d+"
    _LEC_LIST = r"((?:" + _LEC_ITEM + r")(?:\s*,\s*(?:" + _LEC_ITEM + r"))*)\s*\uac15"
    for m in re.finditer(_LEC_LIST, raw):
        for item in m.group(1).split(","):
            item = item.strip()
            _rng = re.match(r"(\d+)\s*[-~\u2013\u2014]\s*(\d+)$", item)
            if _rng:
                a, b = int(_rng.group(1)), int(_rng.group(2))
                if a <= b and b - a < 50:
                    lectures.extend(str(n) for n in range(a, b + 1))
            elif item.isdigit():
                lectures.append(str(int(item)))  # 0-padding 제거
    seen = set()
    lectures = [l for l in lectures if not (l in seen or seen.add(l))]
    lectures.sort(key=int)

    tests = []
    # "TEST 1,2" / "Test 1, 2" 축약형 → test1, test2 모두 캡처.
    # 기존 정규식 r"test\s*(\d+)"는 "TEST 1,2"에서 test1만 잡아 test2 누락(한영3 등).
    # 콤마로 이어진 번호 목록을 한 마커 뒤에서 모두 수집. (괄호 지문목록 "Test 1(3,4)"는
    # 마커 뒤가 '('라 미스매치 → 영향 없음.)
    for m in re.finditer(r"test\s*((?:\d+\s*,\s*)*\d+)", raw, re.IGNORECASE):
        for _num in m.group(1).split(","):
            _num = _num.strip()
            if _num.isdigit():
                tests.append(f"test{_num}")
    _seen_test = set()
    tests = [t for t in tests if not (t in _seen_test or _seen_test.add(t))]

    exclude_gateway = bool(re.search(r"gateway\s*\uc81c\uc678", raw, re.IGNORECASE))

    # 강별 지문번호 파싱: "3강(Gateway,1), 4강(2,4), 11~17강 (2,4), Test 1(3,4,6,13~19)"
    # → {"3": ["1"], "4": ["2","4"], ..., "17": ["2","4"], "test1": ["3","4","6","13"...]}
    # Gateway 라벨은 분석편 원본에 없어 무시(숫자만 매칭).
    # "제외" 표기(예: "Gateway 제외", "24~28번 제외")는 반대 의미이므로 필터 미적용(전체 포함).
    lecture_details = {}
    lecture_exclude = {}  # \uac15/test -> \uc81c\uc678 \uc9c0\ubb38\ubc88\ud638 set (\uc608: {"test2": {1,8,24,25,26,27,28}})
    def _classify_paren(content):
        # ("exclude", [nums]) | ("include", [passages]) | ("skip", None)
        if "\uc81c\uc678" in content:
            nums = _parse_passage_list(content.replace("\uc81c\uc678", "").strip())
            return ("exclude", nums) if nums else ("skip", None)
        passages = _parse_passage_list(content)
        return ("include", passages) if passages else ("skip", None)
    def _skip_paren(content):  # \uad04\ud638 \uc5c6\ub294 \ud3f4\ubc31(\uc544\ub798)\uc6a9 \u2014 \uae30\uc874 \ub3d9\uc791 \uc720\uc9c0(include\ub9cc \ucc44\ud0dd)
        return _classify_paren(content)[0] != "include"
    for m in re.finditer(
        r"(\d+)(?:\s*[-~\u2013\u2014]\s*(\d+))?\s*\uac15\s*\(([^)]*)\)", raw
    ):
        s_n = int(m.group(1))
        e_n = int(m.group(2)) if m.group(2) else s_n
        _kind, _vals = _classify_paren(m.group(3))
        if _kind == "skip":
            continue
        if s_n <= e_n and e_n - s_n < 50:
            for n in range(s_n, e_n + 1):
                if _kind == "include":
                    lecture_details[str(n)] = _vals
                else:
                    lecture_exclude[str(n)] = {int(v) for v in _vals if str(v).isdigit()}
    # \ub300\ubb38\uc790 "TEST 2"\ub3c4 \ub9e4\uce6d\ud558\ub3c4\ub85d IGNORECASE (\uae30\uc874 [Tt]est\ub294 'TEST' \ubbf8\ub9e4\uce6d \u2192 \uad11\ubb383 \ub204\ub77d \uc6d0\uc778).
    for m in re.finditer(r"[Tt]est\s*(\d+)\s*\(([^)]*)\)", raw, re.IGNORECASE):
        _kind, _vals = _classify_paren(m.group(2))
        if _kind == "skip":
            continue
        _key = f"test{m.group(1)}"
        if _kind == "include":
            lecture_details[_key] = _vals
        else:
            lecture_exclude[_key] = {int(v) for v in _vals if str(v).isdigit()}

    # 공백 구분 표기 지원: 괄호 없이 마커 뒤 공백으로 지문이 이어지는 형식.
    #   "18강 2, 4 / 19강 3~4, 7~8 / 21~23강 1, 3", "Test1 20~25, Test2 3~6"
    # (명일여고3 등. 괄호 표기 학교 동작을 깨지 않도록, 괄호 파싱이 아무것도
    #  못 얻었을 때만 적용한다.) 각 강/Test 마커 뒤 지문목록을 다음 마커·'/'·
    #  줄끝 전까지 캡처한다. 괄호 표기("Test 1(3,4)")는 마커 뒤가 '('라서 미매치.
    if not lecture_details:
        _MK = r"(?:\d+\s*[-~–—]\s*\d+|\d+)\s*강|[Tt]est\s*\d+"
        for m in re.finditer(
            r"(" + _MK + r")\s+([\d,\s~–—\-]+?)\s*(?=/|" + _MK + r"|$)",
            raw, re.MULTILINE,
        ):
            _lec_tok, _pass_tok = m.group(1), m.group(2)
            if _skip_paren(_pass_tok):
                continue
            _passages = _parse_passage_list(_pass_tok)
            if not _passages:
                continue
            _tm = re.match(r"[Tt]est\s*(\d+)", _lec_tok)
            if _tm:
                lecture_details[f"test{_tm.group(1)}"] = _passages
                continue
            _rng = re.match(r"(\d+)\s*[-~–—]\s*(\d+)\s*강", _lec_tok)
            if _rng:
                _a, _b = int(_rng.group(1)), int(_rng.group(2))
                if _a <= _b and _b - _a < 50:
                    for _n in range(_a, _b + 1):
                        lecture_details[str(_n)] = _passages
                continue
            _sm = re.match(r"(\d+)\s*강", _lec_tok)
            if _sm:
                lecture_details[str(int(_sm.group(1)))] = _passages

    if log:
        preview = raw.replace("\n", " | ")
        log(f"[\uace03 \ubc94\uc704] \uc218\ub2a5\ud2b9\uac15: {preview}")
        log(f"[\uace03 \ubc94\uc704] \uac15={lectures}, test={tests}, Gateway \uc81c\uc678={exclude_gateway}")
        if lecture_details:
            _preview = ", ".join(
                f"{k}({','.join(v) if v else '-'})" for k, v in sorted(
                    lecture_details.items(),
                    key=lambda kv: (0, int(kv[0])) if kv[0].isdigit() else (1, kv[0]))
            )
            log(f"[\uace03 \ubc94\uc704] \uac15\ubcc4 \uc9c0\ubb38: {_preview}")
        if textbook_raw:
            tb_preview = textbook_raw.replace("\n", " | ")
            log(f"[\uace03 \ubc94\uc704] \uad50\uacfc\uc11c: {tb_preview}")
            tb_desc = ",".join(textbook_lessons) + "\uacfc" if textbook_lessons else "\uc804\uccb4"
            log(f"[\uace03 \ubc94\uc704] \uad50\uacfc\uc11c: {tb_desc}")

    return {
        "lectures": lectures,
        "tests": tests,
        "exclude_gateway": exclude_gateway,
        "raw": raw,
        "textbook_lessons": textbook_lessons,
        "textbook_raw": textbook_raw,
        "lecture_details": lecture_details,
        "lecture_exclude": lecture_exclude,
    }


def _parse_passage_list(s):
    """괄호 안 지문번호 문자열을 리스트로 파싱.

    예: "Gateway,1" → ["Gateway", "1"]
        "3,4,6,13~19" → ["3","4","6","13","14","15","16","17","18","19"]
        "13~19\ubc88" → ["13","14",...,"19"]
    """
    result = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        # "13~19번" 같이 뒤에 "번"이 붙은 경우 제거
        part = re.sub(r"\ubc88\s*$", "", part).strip()
        rm = re.match(r"(\d+)\s*[-~\u2013\u2014]\s*(\d+)$", part)
        if rm:
            s_n, e_n = int(rm.group(1)), int(rm.group(2))
            if s_n <= e_n and e_n - s_n < 100:
                result.extend(str(n) for n in range(s_n, e_n + 1))
        elif part.isdigit():
            result.append(str(int(part)))  # 0-padding 제거
        elif re.match(r"^Gateway$", part, re.IGNORECASE):
            result.append("Gateway")  # 표준 표기로 정규화
        # 그 외 영문 라벨은 무시
    return result


def fetch_scope_for_school(school, log=None, exam_period=None):
    """시험범위 시트에서 특정 학교의 모의고사 범위를 가져온다."""
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        if log:
            log("[중요어휘] 시험범위 시트 접근 실패")
        return []

    target_row = _find_scope_row(rows, school, exam_period)
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


def fetch_textbook_limits_for_school(school, log=None, exam_period=None):
    """시험범위 시트의 교과서 컬럼에서 과별 본문 제한 추출.

    패턴: "(N과는 본문M까지만 들어감)", "(N과 본문M까지)", "(SL 본문M까지)" 등

    Returns:
        dict {과번호: 최대본문번호}  예: {"3": 1}  (3과 본문1까지만)
        SL은 키 "SL"로 저장.
        제한 없으면 빈 dict.
    """
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        return {}
    target_row = _find_scope_row(rows, school, exam_period)
    if not target_row:
        return {}
    # 교과서 컬럼 (인덱스 1)
    tb_text = target_row[1] if len(target_row) > 1 else ""
    tb_text = unicodedata.normalize("NFC", tb_text or "")
    limits = {}
    # "(3과는 본문1까지만 들어감)" / "(3과 본문1까지)" / "(3과 본문1번까지)"
    pat = re.compile(r"(\d+|SL|S\d+)\s*\uacfc?(?:\ub294)?\s*\ubcf8\ubb38\s*(\d+)(?:\ubc88)?\s*\uae4c\uc9c0")
    for m in pat.finditer(tb_text):
        key = m.group(1)
        # S1/S2/... → SL 정규화
        if key.startswith("S") and key != "SL":
            key = "SL"
        try:
            max_body = int(m.group(2))
        except ValueError:
            continue
        # 동일 키가 여러 번 나오면 더 작은 값으로 (엄격)
        if key in limits:
            limits[key] = min(limits[key], max_body)
        else:
            limits[key] = max_body
    if log and limits:
        log(f"[교과서] 과별 본문 제한: {limits}")
    return limits


def fetch_textbook_rm_lessons_for_school(school, log=None, exam_period=None):
    """시험범위 시트의 교과서 컬럼에서 RM/FR 포함 과 추출.

    패턴 예:
      - "(3과는 Read More도 포함)" → {"3"}
      - "(2,3과 Further Reading 포함)" → {"2", "3"}
      - "(SL은 RM 포함)" → {"SL"}

    Returns:
        set of lesson numbers that include RM/FR. None if 명시 없음(전체 허용).
    """
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        return None
    target_row = _find_scope_row(rows, school, exam_period)
    if not target_row:
        return None
    tb_text = target_row[1] if len(target_row) > 1 else ""
    tb_text = unicodedata.normalize("NFC", tb_text or "")
    if not tb_text:
        return None

    # RM/FR 명시 패턴이 있을 때만 set 반환. 없으면 None (= 전체 허용)
    has_rm_fr_mention = bool(
        re.search(r"Read\s*More|Further\s*Reading|\bRM\b|\bFR\b", tb_text, re.IGNORECASE)
    )
    if not has_rm_fr_mention:
        return None

    rm_lessons = set()
    # "N과는 Read More 포함" / "N,M과는 Further Reading도 포함" / "SL은 RM 포함" 등
    # 캡처: 앞 숫자/SL/S\d+ 그룹 + RM/FR 키워드
    # 1) 단일 또는 콤마로 묶인 과: "2과", "2,3과", "S1과"
    pat = re.compile(
        r"((?:\d+|SL|S\d+)(?:\s*,\s*\d+)*)\s*과?(?:는|은)?\s*"
        r"(?:Read\s*More|Further\s*Reading|RM|FR)\s*(?:도)?\s*포함",
        re.IGNORECASE,
    )
    for m in pat.finditer(tb_text):
        keys_str = m.group(1)
        for k in keys_str.split(","):
            k = k.strip()
            if not k:
                continue
            if k.startswith("S") and k != "SL":
                k = "SL"
            rm_lessons.add(k)

    if log and rm_lessons:
        log(f"[교과서] RM/FR 포함 과: {sorted(rm_lessons)}")
    return rm_lessons or set()


def fetch_olpo_scope_for_school(school, log=None, exam_period=None):
    """시험범위 시트 부교재 컬럼(인덱스3)에서 올포 강별 허용 라벨 추출.

    예: "올림포스 영어독해 기본1 10~12, 14~16강 분석~3"
          → 10,11,12,14,15,16강: {분석, 본문1, 본문2, 본문3}
        "올림포스 영어독해 기본1 17~18강 (Practice 1만)"
          → 17,18강: {분석, 본문1}  (장문 Practice1=분석+본문1, 본문2~/서술형/논술형 제외)

    Returns:
        dict {강(int): set(허용 라벨)}. 강이 맵에 없으면 제한 없음(전체 허용).
        빈 dict이면 필터 미적용(파싱 실패/단서 없음 — 보수적 폴백, 누락 사고 방지).
    """
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        return {}
    target_row = _find_scope_row(rows, school, exam_period)
    if not target_row:
        return {}
    raw = target_row[3] if len(target_row) > 3 else ""
    raw = unicodedata.normalize("NFC", raw or "")
    if "올림포스" not in raw and "올포" not in raw:
        return {}

    scope = {}
    # 절(clause) 분리: 각 올림포스/올포 시작 지점에서 분할 (줄바꿈/불릿 유무 무관하게 견고)
    segments = re.split(r"(?=올림포스|올포)", raw)
    for seg in segments:
        seg = seg.strip()
        if "올림포스" not in seg and "올포" not in seg:
            continue
        # 강 목록: "강" 바로 앞 숫자/범위 리스트만 캡처 ("기본1"의 1 오염 방지)
        m_lec = re.search(
            r"((?:\d+\s*[~\-–—]\s*\d+|\d+)"
            r"(?:\s*,\s*(?:\d+\s*[~\-–—]\s*\d+|\d+))*)\s*강",
            seg,
        )
        if not m_lec:
            continue
        lectures = []
        for part in m_lec.group(1).split(","):
            part = part.strip()
            rng = re.match(r"(\d+)\s*[~\-–—]\s*(\d+)$", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if a <= b and b - a < 50:
                    lectures.extend(range(a, b + 1))
            elif part.isdigit():
                lectures.append(int(part))
        if not lectures:
            continue
        # 허용 라벨 판정: "분석~N" / "Practice N만" / "본문N까지" → {분석, 본문1..N}
        allowed = None
        m_an = re.search(r"분석\s*[~\-–—]\s*(\d+)", seg)
        m_pr = re.search(r"Practice\s*(\d+)\s*만", seg, re.IGNORECASE)
        m_bm = re.search(r"본문\s*(\d+)\s*까지", seg)
        for _m in (m_an, m_pr, m_bm):
            if _m:
                n = int(_m.group(1))
                allowed = {"분석"} | set("본문%d" % i for i in range(1, n + 1))
                break
        if allowed is None:
            continue   # 인식 못한 단서 → 제한 없음(보수적, 누락 방지)
        for lec in lectures:
            scope.setdefault(lec, set()).update(allowed)
    if log and scope:
        _preview = ", ".join("%d강%s" % (k, sorted(v)) for k, v in sorted(scope.items()))
        log("[올포 범위] 강별 허용 라벨: " + _preview)
    return scope


def fetch_exclude_writing_for_school(school, log=None, exam_period=None):
    """시험범위 시트 비고 컬럼(인덱스6)에 '서술형 ... X/없음' → 서술형영작 섹션 제외.

    "서술형 문항 X", "서술형 X", "서술형 없음" 등에 매칭. "서술형 단답식형만"처럼
    출제(포함)를 의미하는 표기는 매칭하지 않는다.
    """
    rows = _fetch_csv(SCOPE_SHEET_ID, SCOPE_GID)
    if not rows:
        return False
    target_row = _find_scope_row(rows, school, exam_period)
    if not target_row:
        return False
    note = target_row[6] if len(target_row) > 6 else ""
    note = unicodedata.normalize("NFC", note or "")
    if re.search(r"서술형[^\n.]*?(?:\bX\b|없음|없다|미출제|제외)", note, re.IGNORECASE):
        if log:
            log("[서술형] 비고 '%s' → 서술형영작 섹션 제외" % note.strip()[:30])
        return True
    return False


def _parse_olpo_lectures_from_scope(scope_text):
    """올포 scope 텍스트에서 강 번호 리스트 추출. "올포1-4강" → [1,2,3,4]."""
    s = scope_text.replace("\uc62c\ud3ec", "").replace("\uac15", "").strip()
    result = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-")
                result.extend(range(int(a), int(b) + 1))
            except Exception:
                pass
        elif part.isdigit():
            result.append(int(part))
    return result


def fetch_rp_sheet_data(grade):
    """리딩파워 시트 전체 데이터 조회.

    Returns: [(key, text), ...] — key는 "N-ExampleM" / "N-M", text는 지문 전문
    """
    sheet_id = VOCAB_SHEET_IDS.get(grade)
    if not sheet_id:
        return []
    sheets = _discover_sheets(sheet_id)
    rp_gid = None
    for s in sheets:
        nm = s["name"]
        if "\ub9ac\ub529\ud30c\uc6cc" in nm or "Reading" in nm:
            rp_gid = s["gid"]
            break
    if rp_gid is None:
        return []
    rows = _fetch_csv(sheet_id, rp_gid) or []
    result = []
    for r in rows:
        if len(r) < 2 or not r[0].strip():
            continue
        key = r[0].strip()
        text = r[1].strip() if len(r) > 1 else ""
        if text:
            result.append((key, text))
    return result


def fetch_rp_lecture_problem_counts(grade):
    """리딩파워 시트에서 강별 문제(Example 제외) 지문 개수 반환.

    Example 워크북의 내부 1-N 순번을 (강, Ex 번호)로 매핑하는 데 사용.
    예: {9: 4, 10: 4, 11: 2} → 9강 4문제, 10강 4문제, 11강 2문제.

    Returns: {lecture_num: count}
    """
    sheet_id = VOCAB_SHEET_IDS.get(grade)
    if not sheet_id:
        return {}
    sheets = _discover_sheets(sheet_id)
    rp_gid = None
    for s in sheets:
        nm = s["name"]
        if "\ub9ac\ub529\ud30c\uc6cc" in nm or "Reading" in nm:
            rp_gid = s["gid"]
            break
    if rp_gid is None:
        return {}
    rows = _fetch_csv(sheet_id, rp_gid) or []
    counts = {}
    for r in rows:
        if not r or not r[0].strip():
            continue
        m = re.match(r"^(\d+)\s*-\s*(.+)$", r[0].strip())
        if not m:
            continue
        lec = int(m.group(1))
        sec = m.group(2).strip()
        if sec.isdigit():
            counts[lec] = counts.get(lec, 0) + 1
    return counts


def fetch_vocab_for_school(school, grade, log=None, olpo_lectures=None, rp_lectures=None, passage_codes=None, workbook_order=None, code_order=None, exam_period=None, olpo_scope=None):
    """학교의 시험범위에 맞는 중요어휘를 자동 추출.

    각 모의고사 시기별 워크시트에서 해당 문항번호의 데이터를 수집.
    olpo_lectures가 있으면 올포 시트에서도 해당 강의 지문 수집 (파이널 고1/고2).
    rp_lectures가 있으면 리딩파워 시트에서 해당 강의 지문 수집.
    passage_codes(YYMMQQ 리스트)가 있으면 해당 코드로 시기 시트 직접 매칭
    (마더텅 기반 학교처럼 모의고사 scope가 비어있어도 워크북 지문 출처로 추출).
    """
    # 1) 시험범위에서 모의고사 목록
    exams = fetch_scope_for_school(school, log, exam_period=exam_period)

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
    all_items = []  # [(sort_key, prefix_code, text), ...]
    # 섹션 순서 통일 (다른 섹션 _canonical_order_key와 동일):
    #   "0_..." = 리딩파워, "1_..." = 올포, "2_..." = 모의고사 (교과서 제외)
    # workbook_order가 주어지면 그 순서대로, 없으면 exams 등장 순서대로 폴백
    _wb_idx = {}
    if workbook_order:
        for _i, _pair in enumerate(workbook_order):
            try:
                _yy, _mm = _pair
                _wb_idx[(str(_yy), str(_mm).zfill(2))] = _i
            except (TypeError, ValueError):
                continue
    # code_order: YYMMQQ 리스트를 받아 그 순서대로 정렬 (최우선)
    _code_rank = {}
    if code_order:
        for _i, _c in enumerate(code_order):
            _code_rank[str(_c).strip()] = _i

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

        # 시험범위 numbers와 시트 row code를 모두 첫 번째 숫자로 정규화해 매칭.
        # ('41', '41-42', '41~42'를 같은 41~42 복합문항으로 처리)
        number_set = set(_norm_qcode(n) for n in numbers)
        found = 0
        for r in rows:
            if not r or not r[0].strip():
                continue
            code_raw = r[0].strip()
            code_norm = _norm_qcode(code_raw)
            if code_norm in number_set:
                text = r[1].strip() if len(r) > 1 else ""
                if text:
                    yymmqq = _qcode_to_yymmqq(yy, mm, code_raw)
                    # 정렬 키: code_order(마더텅 학교 등 명시 순서) 우선, 없으면 YYMMQQ 오름차순.
                    # 다른 섹션(_canonical_order_key)이 YYMMQQ 오름차순이므로 동일 정책으로 통일.
                    if yymmqq in _code_rank:
                        sk = f"2_{_code_rank[yymmqq]:04d}"
                    else:
                        sk = f"2_{yy}{mm}{code_norm.zfill(2)}"
                    all_items.append((sk, yymmqq, text))
                    found += 1

        if log:
            log(f"[중요어휘] {yy}년 {exam['month']}월: {found}/{len(numbers)}개 추출")

    # 3.2) passage_codes로 YYMMQQ 직접 매칭
    # 마더텅 기반 학교처럼 학교의 시험범위 시트에 모의고사 컬럼이 없어도,
    # 워크북에서 뽑은 지문 출처(YYMMQQ)를 시기별로 분해해 해당 시트에서 조회.
    if passage_codes:
        covered = set(it[1] for it in all_items if it[0].startswith("2_"))
        by_yymm = {}
        for code in passage_codes:
            code = str(code).strip()
            if len(code) != 6 or not code.isdigit():
                continue
            if code in covered:
                continue
            yymm = code[:4]
            qq = code[4:6]
            by_yymm.setdefault(yymm, set()).add(qq)
        pc_found = 0
        pc_missing = []
        for yymm in sorted(by_yymm.keys()):
            qqs = by_yymm[yymm]
            yy_pc = yymm[:2]
            mm_pc = yymm[2:4].lstrip("0") or "0"
            gid = _find_sheet_gid(sheets, yy_pc, mm_pc)
            if gid is None:
                if log:
                    log(f"[중요어휘] passage_codes: 시트 {yy_pc}-{mm_pc} 미발견 -> {sorted(qqs)} 건너뜀")
                pc_missing.extend([f"{yymm}{q}" for q in sorted(qqs)])
                continue
            rows = _fetch_csv(sheet_id, gid)
            if not rows:
                continue
            qq_set = {q.zfill(2) for q in qqs}
            matched_qq = set()
            for r in rows:
                if not r or not r[0].strip():
                    continue
                code = r[0].strip().zfill(2)
                if code in qq_set:
                    text = r[1].strip() if len(r) > 1 else ""
                    if text:
                        yymmqq_full = f"{yymm}{code}"
                        # 정렬 키: code_order 우선, 없으면 YYMMQQ 오름차순(다른 섹션과 통일).
                        if yymmqq_full in _code_rank:
                            sk = f"2_{_code_rank[yymmqq_full]:04d}"
                        else:
                            sk = f"2_{yymmqq_full}"
                        all_items.append((sk, yymmqq_full, text))
                        pc_found += 1
                        matched_qq.add(code)
            missing_qq = qq_set - matched_qq
            if missing_qq:
                pc_missing.extend([f"{yymm}{q}" for q in sorted(missing_qq)])
        if log:
            log(f"[중요어휘] passage_codes: {pc_found}개 지문 추가 (요청 {len(passage_codes)})")
            if pc_missing:
                log(f"[중요어휘] passage_codes 미매칭: {len(pc_missing)}개 — {pc_missing[:10]}{'...' if len(pc_missing)>10 else ''}")

    # 3.7) 마더텅 시트 폴백 — 시기별 시트에서 못 찾은 YYMMQQ를 "마더텅" 시트에서 보완
    # (2018~2019 구지문 등 시기별 시트에 없는 지문을 마더텅 기출 모음에서 가져옴)
    if passage_codes:
        try:
            from engines.final.parser import get_mothertongue_map
            _mt_map = get_mothertongue_map()
        except Exception:
            _mt_map = None
        if _mt_map:
            mt_vocab = _fetch_mothertongue_vocab(sheet_id, _mt_map)
            _covered = set(it[1] for it in all_items)
            _mt_added = 0
            for code in passage_codes:
                code = str(code).strip()
                if len(code) != 6 or not code.isdigit():
                    continue
                if code in _covered:
                    continue
                text = mt_vocab.get(code)
                if not text:
                    continue
                yy_mt = code[:2]
                mm_mt = code[2:4]
                if code in _code_rank:
                    sk = f"2_{_code_rank[code]:04d}"
                elif _wb_idx:
                    _ord = _wb_idx.get((yy_mt, mm_mt), 900)
                    sk = f"2_{_ord:03d}_{code[4:]}"
                else:
                    sk = f"2_{code}"
                all_items.append((sk, code, text))
                _mt_added += 1
            if log:
                log(f"[\uc911\uc694\uc5b4\ud718] \ub9c8\ub354\ud145 \uc2dc\ud2b8 \ud3f4\ubc31: {_mt_added}\uac1c \ucd94\uac00")

    # 3.5) 올포 시트에서 강별 데이터 수집 (고1/고2, scope에 올포가 있을 때)
    if olpo_lectures:
        olp_gids = _find_olympos_gid(sheets, grade)
        # 공통영어1 → 기본1, 영어1 → 기본2 로 매핑 — school 기반 간단 판단
        # 광문1은 기본1, 고2는 기본2. 호출자가 명시적으로 넘기지 않아도 모두 탐색.
        # 기본1/기본2 모두 시도해서 해당 강 있으면 사용
        _sec_order = {"\ubd84\uc11d": 0, "1\ubc88": 1, "2\ubc88": 2, "3\ubc88": 3,
                      "\uc11c\uc220\ud615": 4, "\ub17c\uc220\ud615": 5}
        olp_found = 0
        for olp_key in ["\uae30\ubcf8\uc218\uc900", "\uae30\ubcf82", "\uae30\ubcf81"]:
            pass  # placeholder
        # 실제로는 key "기본1", "기본2"
        for olp_key in ["\uae30\ubcf81", "\uae30\ubcf82"]:
            ogid = olp_gids.get(olp_key)
            if ogid is None:
                continue
            orows = _fetch_csv(sheet_id, ogid)
            if not orows:
                continue
            for r in orows:
                if not r or not r[0].strip():
                    continue
                key_txt = r[0].strip()
                # "3강 분석", "3강 1번", "3강 서술형"
                m = re.match(r"^(\d+)\uac15\s+(.+)$", key_txt)
                if not m:
                    continue
                lec = int(m.group(1))
                sec = m.group(2).strip()
                if lec not in olpo_lectures:
                    continue
                text = r[1].strip() if len(r) > 1 else ""
                if not text:
                    continue
                # 지문코드: "올포N_섹션" — 최종 출력시 "올포 N강 분석" 등
                # 섹션 정규화
                sec_norm = sec
                if sec == "1\ubc88":
                    sec_display = "\ubcf8\ubb381"
                elif sec == "2\ubc88":
                    sec_display = "\ubcf8\ubb382"
                elif sec == "3\ubc88":
                    sec_display = "\ubcf8\ubb383"
                elif sec == "\ubd84\uc11d":
                    sec_display = "\ubd84\uc11d"
                elif sec == "\uc11c\uc220\ud615":
                    sec_display = "\uc11c\uc220\ud615"
                elif sec == "\ub17c\uc220\ud615":
                    sec_display = "\ub17c\uc220\ud615"
                else:
                    sec_display = sec
                # 올포 강별 하위범위 필터 (분석~N / Practice N만 — 시험범위 부교재 컬럼)
                # 문장배열/삽입/어법수정과 동일 기준으로 중요어휘도 걸러 일관성 유지
                if olpo_scope and lec in olpo_scope and sec_display not in olpo_scope[lec]:
                    continue
                so = _sec_order.get(sec, 99)
                # 섹션 순서 통일: 올포 = "1_..." (리딩파워 뒤, 모의고사 앞)
                sort_key = f"1_{lec:03d}_{so}"
                prefix = f"\uc62c\ud3ec {lec}\uac15 {sec_display}"
                all_items.append((sort_key, prefix, text))
                olp_found += 1
        if log:
            log(f"[\uc911\uc694\uc5b4\ud718] \uc62c\ud3ec {olp_found}\uac1c \uc9c0\ubb38 \ucd94\uac00 (\uac15 \ubc94\uc704: {sorted(olpo_lectures)})")

    # 3.6) 리딩파워 시트에서 강별 데이터 수집 (고1/고2, scope에 리딩파워가 있을 때)
    if rp_lectures:
        rp_gid = None
        for s in sheets:
            name = s["name"]
            if "\ub9ac\ub529\ud30c\uc6cc" in name or "Reading" in name:
                rp_gid = s["gid"]
                break
        if rp_gid is not None:
            rp_rows = _fetch_csv(sheet_id, rp_gid)
            rp_found = 0
            # 섹션 정렬: Example1=0, Example2=1, 1=2, 2=3, 3=4, 4=5
            def _rp_sec_order(sec):
                if sec.startswith("Example"):
                    m_ex = re.match(r"Example\s*(\d+)", sec)
                    return int(m_ex.group(1)) - 1 if m_ex else 0
                if sec.isdigit():
                    return int(sec) + 1  # regular 문제는 Example 뒤에
                return 99
            for r in rp_rows or []:
                if not r or not r[0].strip():
                    continue
                key_txt = r[0].strip()
                # "3-Example1" / "3-1" 형식
                m = re.match(r"^(\d+)\s*-\s*(.+)$", key_txt)
                if not m:
                    continue
                lec = int(m.group(1))
                sec = m.group(2).strip()
                if lec not in rp_lectures:
                    continue
                text = r[1].strip() if len(r) > 1 else ""
                if not text:
                    continue
                # 섹션 표기: "Example1" → prefix "리딩파워 N강Ex 01", "1" → prefix "리딩파워 N강 01"
                m_ex = re.match(r"Example\s*(\d+)", sec)
                # 섹션 순서 통일: 리딩파워 = "0_..." (최앞. 교과서는 vocab 제외)
                sort_key = f"0_{lec:03d}_{_rp_sec_order(sec):03d}"
                if m_ex:
                    prefix = f"\ub9ac\ub529\ud30c\uc6cc {lec}\uac15 Ex{int(m_ex.group(1)):02d}"
                elif sec.isdigit():
                    prefix = f"\ub9ac\ub529\ud30c\uc6cc {lec}\uac15 {int(sec):02d}"
                else:
                    prefix = f"\ub9ac\ub529\ud30c\uc6cc {lec}\uac15 {sec}"
                all_items.append((sort_key, prefix, text))
                rp_found += 1
            if log:
                log(f"[\uc911\uc694\uc5b4\ud718] \ub9ac\ub529\ud30c\uc6cc {rp_found}\uac1c \uc9c0\ubb38 \ucd94\uac00 (\uac15 \ubc94\uc704: {sorted(rp_lectures)})")

    if not all_items:
        if log:
            log(f"[중요어휘] 추출된 데이터 없음")
        return {"left_text": "", "right_text": ""}

    # 4) 정렬 후 텍스트 조합
    all_items.sort(key=lambda x: x[0])

    parts = []
    for _sk, prefix, text in all_items:
        parts.append(f"{prefix}\n{text}")

    combined = "\n\n".join(parts)

    result = {
        "left_text": combined,
        "right_text": combined,  # 양쪽 동일
    }

    if log:
        log(f"[중요어휘] 최종: {len(all_items)}개 지문")

    return result
