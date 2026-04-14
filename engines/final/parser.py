"""파이널 직전보충 — 추출 데이터 + 웹 입력 통합 파서.

extractor가 생성한 extracted.json과 어법수정 Word 데이터를
Vol1/Vol2용 content.json으로 변환한다.
"""

import json
import os
import re
import unicodedata


def _nfc(s):
    """macOS NFD 한글 경로를 NFC로 정규화."""
    return unicodedata.normalize("NFC", s)


def _clean_text(t):
    """추출 텍스트에서 InDesign 객체 교체 문자(￼) 등 정리."""
    # Object Replacement Character (U+FFFC) 제거
    t = t.replace("\ufffc", "").strip()
    return t


def _is_insert_noise(txt):
    """문장삽입 추출 시 불필요한 단락인지 확인.

    워크북에서 추출된 포맷팅 잔여물: 순번(01, 02...), 화살표(➡, ＞), 빈줄 등.
    """
    t = txt.strip()
    if not t:
        return True
    # 순번만 있는 줄: 01, 02, 1, 2, ...
    if re.match(r"^\d{1,2}$", t):
        return True
    # 화살표/특수문자만: ➡, ＞, >, →
    if re.match(r"^[➡＞>→\s]+$", t):
        return True
    return False


def _is_question_header(text):
    """단락이 문항번호 헤더({20}, {21}, [20], [21], {41~42}, 20, 41~42 등)인지 확인."""
    t = text.strip()
    # {20}, {21~22}, {41~42} 등
    if re.match(r"^\{\d+(?:[~\-]\d+)?\}$", t):
        return True
    # [20], [21] 등
    if re.match(r"^\[\d+(?:[~\-]\d+)?\]$", t):
        return True
    # 중괄호 없는 plain 숫자: 18~45 범위 (모의고사 문항번호)
    m = re.match(r"^(\d{2})(?:[~\-](\d{2}))?$", t)
    if m:
        num = int(m.group(1))
        if 18 <= num <= 45:
            return True
    return False


def _extract_question_number(text):
    """헤더에서 문항번호 추출. '{20}' → '20', '{41~42}' → '41~42', '20' → '20'"""
    t = text.strip()
    # {XX} or [XX] 형식
    m = re.match(r"^[\[{](\d+(?:[~\-]\d+)?)[\]}]$", t)
    if m:
        return m.group(1)
    # plain 숫자 형식: 20, 41~42
    m2 = re.match(r"^(\d{2}(?:[~\-]\d{2})?)$", t)
    if m2:
        return m2.group(1)
    return ""


def _classify_stories(stories):
    """추출된 스토리들을 유형별로 분류.

    모의고사 워크북은 하나의 스토리에 여러 지문이 {20}, {21}, ... 헤더로
    구분되어 있으므로, 이 헤더를 기준으로 블록을 분리한다.
    """
    sentence_arr = []      # 문장배열 (Vol1)
    sentence_insert = []   # 문장삽입/순서배열 (Vol1)
    grammar_fix = []       # 어법수정 (Vol2)
    writing_kor = []       # 영작 한글 (Vol2)
    writing_view = []      # 영작 보기 (Vol2)

    # 스타일 → 유형 매핑
    sentence_styles = {"문장 배열 그랩", "C1_문장 배열"}
    insert_styles = {"하단 문제", "C1_문장 배열 하단", "C1_문장 배열 하단 지문",
                     "문장 배열 하단 ", "문장 배열 하단 문제"}
    grammar_styles = {"A_어법 수정"}
    writing_kor_styles = {"C_영작 배열 번호", "C2_영작 배열 번호"}
    writing_view_styles = {"영작 배열 보기", "C2_영작 배열 보기"}
    # B1 관련 스타일 (이 스타일이 있는 스토리는 문장삽입으로 분류하지 않음)
    b1_styles = {"B1_내용 정리", "B1_내용 정리 주제", "B1_내용 정리 제목",
                 "B1_본문 박스", "하단 문제_지문", "하단 문제_선지"}

    # pageOff → 문항번호 매핑 구축 (문장삽입 스토리의 헤더에서 추출)
    page_to_qnum = {}  # {pageOff: q_num, ...}  (source_file별)
    for story in stories:
        paras = story.get("paras", [])
        page_off = story.get("pageOff", -1)
        all_s = set(p.get("s", "") for p in paras)
        if not (all_s & insert_styles):
            continue
        # B1 스토리 제외
        if all_s & b1_styles:
            continue
        # 문장삽입 스토리에서 문항번호 추출
        src = story.get("source_file", "")
        for p in paras:
            txt = _clean_text(p.get("t", "").strip())
            s = p.get("s", "")
            if s in ("[기본 단락]", "[Basic Paragraph]") and _is_question_header(txt):
                qn = _extract_question_number(txt)
                if qn and page_off >= 0:
                    key = (src, page_off)
                    if key not in page_to_qnum:
                        page_to_qnum[key] = qn

    for story in stories:
        paras = story.get("paras", [])
        if not paras:
            continue

        types_found = set()
        all_styles = set()
        for p in paras:
            style = p.get("s", "")
            all_styles.add(style)
            if style in sentence_styles:
                types_found.add("sentence")
            if style in insert_styles:
                types_found.add("insert")
            if style in grammar_styles:
                types_found.add("grammar")
            if style in writing_kor_styles:
                types_found.add("writing_kor")
            if style in writing_view_styles:
                types_found.add("writing_view")

        # B1 스토리에서 하단 문제가 있어도 문장삽입으로 분류하지 않음
        # (B1_내용 정리 등 B1 스타일이 포함된 스토리는 insert에서 제외)
        has_b1 = bool(all_styles & b1_styles)
        if has_b1:
            types_found.discard("insert")

        # sentence + insert 동시 포함 스토리: 대형 스레드 스토리 — sentence 제외
        # (개별 문장배열 스토리는 insert 스타일이 없으므로 영향 없음)
        if "sentence" in types_found and "insert" in types_found:
            types_found.discard("sentence")

        # insert + B1 아닌 경우만 유효 (sentence 없어도 OK — 교과서 문장삽입은 별도 스토리)

        source = story.get("source_file", "")
        page_off = story.get("pageOff", -1)

        # 문장배열: {XX} 헤더로 블록 분리
        if "sentence" in types_found:
            # 1순위: extractor가 같은 페이지에서 읽은 지문번호
            page_qnum = story.get("pageQNum", "")
            # 2순위: 같은 페이지의 문장삽입 헤더
            if not page_qnum:
                page_qnum = page_to_qnum.get((source, page_off), "")
            _split_sentence_blocks(paras, source, sentence_styles, sentence_arr,
                                   page_qnum=page_qnum, page_off=page_off)

        # 문장삽입/순서배열: {XX} 헤더로 블록 분리
        if "insert" in types_found:
            ins_page_qnum = story.get("pageQNum", "")
            if not ins_page_qnum:
                ins_page_qnum = page_to_qnum.get((source, page_off), "")
            _split_insert_blocks(paras, source, insert_styles, sentence_insert,
                                 page_qnum=ins_page_qnum, page_off=page_off)

        # 어법수정
        if "grammar" in types_found:
            lines = []
            for p in paras:
                txt = p.get("t", "").strip()
                if p.get("s", "") in grammar_styles and txt:
                    lines.append(txt)
            if lines:
                grammar_fix.append({"source": source, "lines": lines})

        # 영작: {XX} 헤더로 블록 분리
        if "writing_kor" in types_found or "writing_view" in types_found:
            _split_writing_blocks(paras, source, writing_kor_styles,
                                  writing_view_styles, writing_kor, writing_view)

    return sentence_arr, sentence_insert, grammar_fix, writing_kor, writing_view


def _split_sentence_blocks(paras, source, sentence_styles, output_list,
                           page_qnum="", page_off=-1):
    """문장배열 단락들을 {XX} 헤더 기준으로 블록 분리.

    page_qnum: pageOff 기반으로 조회된 문항번호 (같은 페이지의 문장삽입 헤더).
               헤더가 없는 스토리에서 정확한 문항번호로 사용.
    page_off: 스토리 첫 프레임의 페이지 오프셋 (교과서 블록 정렬용).
    """
    # 헤더가 있는지 확인 (모의고사 형식)
    has_q_headers = any(
        p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
        and _is_question_header(p.get("t", "").strip())
        for p in paras
    )

    if has_q_headers:
        # 모의고사: {20}, {21}, ... 로 분리
        current_items = []
        current_qnum = ""
        for p in paras:
            txt = p.get("t", "").strip()
            style = p.get("s", "")

            if (style in ("[기본 단락]", "[Basic Paragraph]")
                    and _is_question_header(txt)):
                # 이전 블록 저장
                if current_items:
                    output_list.append({
                        "source": source,
                        "items": current_items,
                        "q_num": current_qnum,
                    })
                current_items = []
                current_qnum = _extract_question_number(txt)
                continue

            if style in sentence_styles and txt:
                current_items.append(txt)

        # 마지막 블록
        if current_items:
            output_list.append({
                "source": source,
                "items": current_items,
                "q_num": current_qnum,
            })
    else:
        # 교과서 또는 헤더 없는 모의고사: 단일 블록
        # page_qnum이 있으면 pageOff 기반 문항번호 사용
        items = []
        for p in paras:
            txt = p.get("t", "").strip()
            if not txt:
                continue
            if p.get("s", "") in sentence_styles:
                items.append(txt)
        if items:
            block = {"source": source, "items": items, "page_off": page_off}
            if page_qnum:
                block["q_num"] = page_qnum
            output_list.append(block)


def _split_insert_blocks(paras, source, insert_styles, output_list,
                         page_qnum="", page_off=-1):
    """문장삽입 단락들을 {XX} 헤더 기준으로 블록 분리."""
    has_q_headers = any(
        p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
        and _is_question_header(p.get("t", "").strip())
        for p in paras
    )

    if has_q_headers:
        # 모의고사: {20}, {21}, 20, 24 ... 로 분리
        current_paras = []
        current_qnum = ""
        in_block = False  # 첫 헤더 이후인지 추적
        for p in paras:
            raw_txt = p.get("t", "").strip()
            txt = _clean_text(raw_txt)  # U+FFFC 등 제거 후 체크
            style = p.get("s", "")

            if (style in ("[기본 단락]", "[Basic Paragraph]")
                    and _is_question_header(txt)):
                # 이전 블록 저장
                if current_paras:
                    output_list.append({
                        "source": source,
                        "paras": current_paras,
                        "q_num": current_qnum,
                    })
                current_paras = []
                current_qnum = _extract_question_number(txt)
                in_block = True
                continue

            if style in insert_styles and txt and not _is_insert_noise(txt):
                current_paras.append({"style": style, "text": txt})
            elif in_block and style in ("[기본 단락]", "[Basic Paragraph]") and txt and not _is_insert_noise(txt):
                # 발문 (문장삽입/순서배열 지시문) — [기본 단락] 중 헤더가 아닌 텍스트
                current_paras.append({"style": style, "text": txt})

        if current_paras:
            output_list.append({
                "source": source,
                "paras": current_paras,
                "q_num": current_qnum,
            })
    else:
        # 교과서: "아래 주어진" 발문 기준으로 문제별 분리
        all_paras = []
        for p in paras:
            raw_txt = p.get("t", "").strip()
            txt = _clean_text(raw_txt)
            style = p.get("s", "")
            if style in insert_styles and txt and not _is_insert_noise(txt):
                all_paras.append({"style": style, "text": txt})
            elif style in ("[기본 단락]", "[Basic Paragraph]") and txt and not _is_question_header(txt) and not _is_insert_noise(txt):
                all_paras.append({"style": style, "text": txt})

        # "아래 주어진" 발문으로 블록 분리
        blocks = []
        current = []
        for ap in all_paras:
            if ap["text"].startswith("\uc544\ub798") and current:
                blocks.append(current)
                current = []
            current.append(ap)
        if current:
            blocks.append(current)

        for insert_paras in blocks:
            if not insert_paras:
                continue
            block = {"source": source, "paras": insert_paras, "page_off": page_off}
            if page_qnum:
                block["q_num"] = page_qnum
            output_list.append(block)


def _split_writing_blocks(paras, source, kor_styles, view_styles,
                           writing_kor, writing_view):
    """영작 단락들을 수집. 소스 정보와 문항번호 헤더도 함께 추적."""
    # 영작은 [20], {20}, {01~02} 같은 [기본 단락] 헤더로 구분됨
    current_qnum = ""
    for p in paras:
        txt = p.get("t", "").strip()
        if not txt:
            continue
        style = p.get("s", "")

        # [기본 단락] 헤더 추적 — [XX], {XX}, [본문N] 형식
        if style in ("[기본 단락]", "[Basic Paragraph]"):
            # 숫자 헤더: [20], {01~02}
            m = re.match(r"^[\[{](\d+(?:[~\-]\d+)?)[\]}]$", txt)
            if m:
                current_qnum = m.group(1)
                continue
            # 본문N 헤더: [본문1], [본문2]
            m2 = re.match(r"^[\[{]본문(\d+)[\]}]$", txt)
            if m2:
                current_qnum = "본문" + m2.group(1)
                continue
            continue

        if style in kor_styles:
            writing_kor.append({"text": txt, "source": source, "q_num": current_qnum})
        elif style in view_styles:
            writing_view.append({"text": txt, "source": source, "q_num": current_qnum})


def _writing_q_to_header(scope_text, q_num, lesson_label=None):
    """영작 데이터의 문항번호/섹션번호를 헤더로 변환.

    교과서 본문: "본문1" → "1과 본문1" (lesson_label로 과 번호 결정)
    교과서 {01~02}: SL/기타 번호 → "SL 본문1~2" or "X과 본문N"
    모의고사: "20" → "251020" (YYMMQQ)
    """
    scope = _nfc(scope_text) if scope_text else ""

    # "본문N" 형태 (교과서 워크북) — lesson_label 사용
    if q_num.startswith("본문"):
        num = q_num.replace("본문", "")
        if lesson_label:
            return f"교과서{lesson_label} 본문{num}"
        return f"본문{num}"

    # 순수 숫자 (모의고사 문항번호인지, 교과서 섹션번호인지 구분)
    m_mock = re.search(r"(\d{2})년\s*(\d{1,2})월", scope)
    if not m_mock:
        m_mock = re.search(r"모의고사\s*(\d{2})\.(\d{1,2})", scope)

    if m_mock:
        # 모의고사 → YYMMQQ (exam_index는 _build_vol2에서 관리)
        return _q_num_to_header(scope, q_num, exam_index=0)

    # 교과서 섹션번호 → SL 본문N or 과 본문N
    if "SL" in scope:
        return f"교과서SL 본문{q_num}"

    # 교과서: scope에서 과 번호 추출
    m_lesson = re.search(r"교과(서)?\s*([\d,]+)\s*과", scope)
    if m_lesson:
        lessons_str = m_lesson.group(2)
        lessons = [l.strip() for l in lessons_str.split(",")]
        return f"교과서{lessons[0]}과 본문{q_num}" if len(lessons) == 1 else f"교과서 본문{q_num}"

    return q_num


def _parse_all_exams_from_scope(scope_text):
    """복합 scope에서 모든 시험 추출. "26년3월,25년6월" → [("26","03"), ("25","06")]"""
    scope = _nfc(scope_text)
    exams = []
    for m in re.finditer(r"(\d{2})년\s*(\d{1,2})월", scope):
        exams.append((m.group(1), m.group(2).zfill(2)))
    if not exams:
        for m in re.finditer(r"모의고사\s*(\d{2})\.(\d{1,2})", scope):
            exams.append((m.group(1), m.group(2).zfill(2)))
    return exams


def _normalize_q41_42(header):
    """Q41, Q42를 항상 41~42로 정규화. 모든 년/월에 적용."""
    m = re.match(r'^(\d{4})(41|42)$', header)
    if m:
        return f"{m.group(1)}41~42"
    return header


def _build_scope_assigner(scope_exams, workbook_scope):
    """워크북 scope의 각 시험별 사용 가능 문항 셋을 생성.
    first-come-first-served 방식으로 할당하기 위한 상태 객체.
    """
    wb_exams = _parse_all_exams_from_scope(workbook_scope) if workbook_scope else []
    available = []  # [(yy, mm, available_numbers_set), ...]
    for wby, wbm in wb_exams:
        for exam in scope_exams:
            ey = exam['year']
            em = str(exam['month']).zfill(2)
            if ey == wby and em == wbm:
                nums = set(exam['numbers'])
                available.append((ey, em, nums))
                break
    return available


def _assign_q_to_exam(qq, available):
    """사용 가능한 시험 목록에서 qq에 맞는 첫 시험을 찾아 할당.
    할당되면 해당 시험의 available에서 제거.
    """
    for entry in available:
        yy, mm, nums = entry
        if qq in nums or (qq == 41 and 42 in nums) or (qq == 42 and 41 in nums):
            # 사용 처리: 41/42는 모두 제거
            nums.discard(qq)
            if qq in (41, 42):
                nums.discard(41)
                nums.discard(42)
            return yy, mm
    return None, None


def _q_num_to_header_by_scope(q_num, scope_exams, workbook_scope="", available=None):
    """available 상태를 사용하여 YYMMQQ 헤더 생성.
    available이 없으면 scope_exams 전체에서 검색.
    """
    if not scope_exams or not q_num:
        return None
    parts = re.split(r"[~\-]", q_num)
    try:
        qq = int(parts[0])
    except ValueError:
        return None

    if available is not None:
        yy, mm = _assign_q_to_exam(qq, available)
        if yy:
            if len(parts) > 1:
                result = f"{yy}{mm}{parts[0].zfill(2)}~{parts[1].zfill(2)}"
            else:
                result = f"{yy}{mm}{q_num.zfill(2)}"
            return _normalize_q41_42(result)
        return None
    else:
        for exam in scope_exams:
            yy = exam['year']
            mm = str(exam['month']).zfill(2)
            if qq in exam['numbers'] or (qq == 41 and 42 in exam['numbers']) or (qq == 42 and 41 in exam['numbers']):
                if len(parts) > 1:
                    result = f"{yy}{mm}{parts[0].zfill(2)}~{parts[1].zfill(2)}"
                else:
                    result = f"{yy}{mm}{q_num.zfill(2)}"
                return _normalize_q41_42(result)
    return None


def _q_num_to_header(scope_text, q_num, exam_index=0):
    """모의고사 문항번호를 YYMMQQ 헤더로 변환.

    Args:
        scope_text: 시험범위 (예: "25년10월" 또는 "26년3월,25년6월")
        q_num: 문항번호 문자열 (예: "20", "41~42")
        exam_index: 복합 scope에서 몇 번째 시험인지 (0-based)

    Returns:
        "251020" 또는 "251041~42" 형식
    """
    # q_num이 이미 YYMMQQ 형식(6자리 이상)이면 그대로 사용
    q_clean = q_num.replace("~", "").replace("-", "")
    if len(q_clean) >= 6 and q_clean.isdigit():
        # 이미 YYMMQQ: "250623" → 그대로, "250641-42" → "250641~42"
        if "-" in q_num:
            q_num = q_num.replace("-", "~")
        return _normalize_q41_42(q_num)

    exams = _parse_all_exams_from_scope(scope_text)
    if not exams:
        return q_num

    idx = min(exam_index, len(exams) - 1)
    yy, mm = exams[idx]

    if "~" in q_num or "-" in q_num:
        sep = "~" if "~" in q_num else "-"
        parts = q_num.split(sep)
        return f"{yy}{mm}{parts[0].zfill(2)}~{parts[1].zfill(2)}"
    result = f"{yy}{mm}{q_num.zfill(2)}"
    return _normalize_q41_42(result)


def _scope_to_header(scope_text, block_num, blocks_per_lesson=5):
    """시험범위 텍스트 → 지문 헤더 생성.

    교과서: "교과서1,2과,SL" + 본문3 → "1과 본문3" (과 번호는 순차)
    모의고사: "25년10월" + 본문5 → "251024" (YYMMQQ 형식, 문항번호 20+순번)
    올림포스: "올포5,8,9강" + 본문2 → "올포5강 본문2"

    Args:
        blocks_per_lesson: 과당 본문 수 (문장배열=5, 문장삽입=4)
    """
    scope = _nfc(scope_text)

    # 모의고사: YYMMQQ 형식
    m = re.search(r"(\d{2})년\s*(\d{1,2})월", scope)
    if m:
        yy = m.group(1)
        mm = m.group(2).zfill(2)
        qq = str(19 + block_num).zfill(2)  # 20번부터 시작
        return f"{yy}{mm}{qq}"

    # 모의고사 다른 형식: "모의고사25.3"
    m2 = re.search(r"모의고사\s*(\d{2})\.(\d{1,2})", scope)
    if m2:
        yy = m2.group(1)
        mm = m2.group(2).zfill(2)
        qq = str(19 + block_num).zfill(2)
        return f"{yy}{mm}{qq}"

    # 교과서: "교과서1,2과" or "미래엔김3과" → "교과서 1과 본문01"
    m3 = re.search(r"교과(?:서)?\s*([\d,]+)\s*과", scope)
    if not m3:
        # 출판사명+과: "미래엔김3과", "능률민1,2과"
        m3_pub = re.search(r"(?:미래엔|능률|YBM|동아|비상|금성|천재)\S*?([\d,]+)\s*과", scope, re.IGNORECASE)
        if m3_pub:
            m3 = m3_pub
    if m3:
        # group(1) = 과 번호 (예: "3" 또는 "1,2")
        lessons_str = m3.group(1)
        lessons = [l.strip() for l in lessons_str.split(",")]
        total_lesson_blocks = len(lessons) * blocks_per_lesson

        # SL이 범위에 포함된 경우, 교과서 블록 이후는 SL
        has_sl = "SL" in scope
        if has_sl and block_num > total_lesson_blocks:
            sl_num = block_num - total_lesson_blocks
            return f"교과서SL 본문{sl_num}"

        if len(lessons) == 1:
            return f"교과서{lessons[0]}과 본문{block_num}"
        lesson_idx = min((block_num - 1) // blocks_per_lesson, len(lessons) - 1)
        local_num = (block_num - 1) % blocks_per_lesson + 1
        return f"교과서{lessons[lesson_idx]}과 본문{local_num}"

    # SL
    if "SL" in scope:
        return f"교과서SL 본문{block_num}"

    # 올림포스
    if "올포" in scope:
        return f"올포 본문{block_num}"

    # 마더텅
    if "마더텅" in scope:
        return f"마더텅 본문{block_num}"

    # 기본
    return f"지문 {block_num}"


def _sort_blocks(blocks):
    """블록을 source 파일명 → 페이지 순서로 정렬.

    source 파일명의 워크북 번호(01, 02, 03...)로 1차 정렬,
    같은 워크북 내에서는 page_off(페이지 오프셋) 순으로 정렬.
    page_off가 없으면 추출 순서(idx) 유지.
    """
    def sort_key(item):
        idx, block = item
        src = _nfc(block.get("source", ""))
        # 워크북 번호 추출: "강동1_워크북03(25년3월)_내지.indd" → 3
        m = re.search(r"워크북\s*(\d+)", src)
        wb_num = int(m.group(1)) if m else 999
        page_off = block.get("page_off", -1)
        # page_off가 유효하면 페이지 순, 아니면 추출 순
        secondary = page_off if page_off >= 0 else (10000 + idx)
        return (wb_num, secondary)

    indexed = list(enumerate(blocks))
    indexed.sort(key=sort_key)
    return [block for _, block in indexed]


def _is_in_scope(header, scope_exams):
    """YYMMQQ 헤더가 시험범위에 포함되는지 확인."""
    if not scope_exams:
        return True  # scope 없으면 전부 포함
    if header.startswith("교과서") or header.startswith("올포") or header.startswith("마더텅"):
        return True
    m = re.match(r'^(\d{2})(\d{2})(\d{2})(?:~(\d{2}))?$', header)
    if not m:
        return True
    yy, mm = m.group(1), m.group(2)
    qq1 = int(m.group(3))
    qq2 = int(m.group(4)) if m.group(4) else qq1
    for exam in scope_exams:
        ey = exam['year']
        em = exam['month'].zfill(2) if isinstance(exam['month'], str) else str(exam['month']).zfill(2)
        if ey == yy and em == mm:
            for q in range(qq1, qq2 + 1):
                if q in exam['numbers']:
                    return True
    return False


def _build_vol1(sentence_blocks, sentence_insert_blocks, vocab_left_text, vocab_right_text,
                scope_exams=None, lesson_block_counts=None):
    """Vol1 데이터 구성.

    lesson_block_counts: 어법수정 Word에서 감지한 과별 본문 수.
        예: {"1": 6, "2": 6} → 1과 6본문, 2과 6본문.
        이것이 있으면 페이지 갭 감지보다 우선 사용 (ground truth).
    """
    vol1 = {}

    # 문장배열 — 워크북 번호 + q_num 순으로 정렬
    if sentence_blocks:
        sentence_blocks = _sort_blocks(sentence_blocks)

        # 교과서 블록: page_off 갭 기반 과 경계 감지
        # source별 교과서 블록(q_num 없는)의 page_off를 수집
        _tb_page_map = {}  # src -> [(block_idx_in_src, page_off), ...]
        _tb_src_order = []  # 교과서 블록만 순서대로
        _src_block_idx = {}  # src -> 현재 인덱스
        for _bi, _ab in enumerate(sentence_blocks):
            _asrc = _nfc(_ab.get("source", ""))
            if _ab.get("q_num"):
                continue
            if _asrc not in _tb_page_map:
                _tb_page_map[_asrc] = []
                _src_block_idx[_asrc] = 0
            po = _ab.get("page_off", -1)
            _tb_page_map[_asrc].append((_src_block_idx[_asrc], po))
            _src_block_idx[_asrc] += 1

        # source별 과 경계 맵 생성: {src: {block_idx: (lesson, local_num)}}
        _tb_lesson_map = {}  # src -> {block_idx: "교과서N과 본문M"}
        for _src, _blocks_info in _tb_page_map.items():
            _sm = re.search(r"\(([^)]+)\)", _src)
            _scope_txt = _sm.group(1) if _sm else ""
            _lm = re.search(r"(\d+(?:,\d+)*)\s*과", _scope_txt)
            if not _lm:
                continue
            _lessons = [l.strip() for l in _lm.group(1).split(",")]
            if len(_lessons) <= 1:
                # 과 1개면 모두 해당 과
                _tb_lesson_map[_src] = {}
                for _idx, _po in _blocks_info:
                    _tb_lesson_map[_src][_idx] = f"교과서{_lessons[0]}과 본문{_idx + 1}"
                continue

            # 방법 1 (우선): lesson_block_counts (어법수정 Word ground truth)
            if lesson_block_counts and all(l in lesson_block_counts for l in _lessons):
                _tb_lesson_map[_src] = {}
                _offset = 0
                for _lesson in _lessons:
                    _count = lesson_block_counts[_lesson]
                    for _li in range(_count):
                        if _offset + _li < len(_blocks_info):
                            _tb_lesson_map[_src][_offset + _li] = f"교과서{_lesson}과 본문{_li + 1}"
                    _offset += _count
                continue

            # 방법 2 (폴백): 페이지 갭으로 과 경계 감지
            page_offs = [po for _, po in _blocks_info]
            if all(po >= 0 for po in page_offs) and len(page_offs) > 1:
                # 연속 블록 간 페이지 갭 계산
                gaps = []
                for _gi in range(1, len(page_offs)):
                    gaps.append((page_offs[_gi] - page_offs[_gi - 1], _gi))
                # 가장 큰 갭 N-1개가 과 경계
                gaps.sort(key=lambda x: -x[0])
                boundary_indices = sorted([g[1] for g in gaps[:len(_lessons) - 1]])

                # 과별 블록 할당
                _tb_lesson_map[_src] = {}
                segments = [0] + boundary_indices + [len(_blocks_info)]
                for _li, _lesson in enumerate(_lessons):
                    seg_start = segments[_li]
                    seg_end = segments[_li + 1]
                    for _si in range(seg_start, seg_end):
                        local_num = _si - seg_start + 1
                        _tb_lesson_map[_src][_si] = f"교과서{_lesson}과 본문{local_num}"
            else:
                # page_off 없으면 균등 분할 폴백
                _bpl = max(1, len(_blocks_info) // len(_lessons))
                _tb_lesson_map[_src] = {}
                for _idx, _po in _blocks_info:
                    _li2 = min(_idx // _bpl, len(_lessons) - 1)
                    _local = _idx % _bpl + 1
                    _tb_lesson_map[_src][_idx] = f"교과서{_lessons[_li2]}과 본문{_local}"

        all_blocks = []
        source_counts = {}
        # 복합 scope용: source별 exam_index + 이전 q_num 추적
        source_exam_idx = {}  # src -> exam_index
        source_prev_qnum = {}  # src -> 이전 q_num 첫 번째 숫자
        _tb_counters = {}  # src -> 교과서 블록 인덱스 카운터
        for block in sentence_blocks:
            src = _nfc(block.get("source", ""))
            q_num = block.get("q_num", "")

            if q_num:
                scope_match = re.search(r"\(([^)]+)\)", src)
                wb_scope = scope_match.group(1) if scope_match else ""

                # 워크북별 available 상태 생성
                if scope_exams and src not in source_exam_idx:
                    source_exam_idx[src] = _build_scope_assigner(scope_exams, wb_scope)

                avail = source_exam_idx.get(src) if scope_exams else None
                direct_header = _q_num_to_header_by_scope(
                    q_num, scope_exams, wb_scope, available=avail
                ) if scope_exams else None
                if direct_header:
                    header = direct_header
                else:
                    header = _q_num_to_header(wb_scope, q_num)
            else:
                # 교과서 블록: page_off 기반 과 경계 맵 사용
                if src in _tb_lesson_map:
                    if src not in _tb_counters:
                        _tb_counters[src] = 0
                    _cidx = _tb_counters[src]
                    header = _tb_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                    _tb_counters[src] += 1
                else:
                    scope_match = re.search(r"\(([^)]+)\)", src)
                    scope = scope_match.group(1) if scope_match else "지문"
                    if src not in source_counts:
                        source_counts[src] = 0
                    source_counts[src] += 1
                    header = _scope_to_header(scope, source_counts[src])

            all_blocks.append({
                "source": src,
                "header": header,
                "items": block["items"]
            })
        # 중복 헤더 제거 (같은 header가 여러 번 나오면 첫 번째만 유지)
        seen_headers = set()
        deduped = []
        for b in all_blocks:
            if b["header"] in seen_headers:
                continue
            seen_headers.add(b["header"])
            deduped.append(b)
        # 시험범위 필터링
        if scope_exams:
            deduped = [b for b in deduped if _is_in_scope(b["header"], scope_exams)]
        # 헤더 순 정렬: 교과서 먼저, 그 다음 YYMMQQ 오름차순
        def _header_sort_key(b):
            h = b["header"]
            if h.startswith("교과서"):
                return (0, 0, h)
            # YYMMQQ에서 6자리만 추출 (41~42 → 260341의 260341만 사용)
            m = re.match(r'^(\d{6})', h)
            return (1, int(m.group(1)) if m else 999999, h)
        deduped.sort(key=_header_sort_key)
        vol1["문장배열"] = deduped

    # 문장삽입/순서배열 — 과 경계 감지 (문장배열과 동일 방식)
    if sentence_insert_blocks:
        sentence_insert_blocks = _sort_blocks(sentence_insert_blocks)

        # 문장삽입 교과서 블록 과 경계 맵 구축 (문장배열과 동일 로직)
        _ins_page_map = {}
        _ins_src_idx = {}
        for _ib in sentence_insert_blocks:
            _isrc = _nfc(_ib.get("source", ""))
            if _ib.get("q_num"):
                continue
            if _isrc not in _ins_page_map:
                _ins_page_map[_isrc] = []
                _ins_src_idx[_isrc] = 0
            _ins_page_map[_isrc].append((_ins_src_idx[_isrc], _ib.get("page_off", -1)))
            _ins_src_idx[_isrc] += 1

        _ins_lesson_map = {}
        for _isrc, _iblocks in _ins_page_map.items():
            _ism = re.search(r"\(([^)]+)\)", _isrc)
            _iscope = _ism.group(1) if _ism else ""
            _ilm = re.search(r"(\d+(?:,\d+)*)\s*과", _iscope)
            if not _ilm:
                continue
            _ilessons = [l.strip() for l in _ilm.group(1).split(",")]
            if len(_ilessons) <= 1:
                _ins_lesson_map[_isrc] = {}
                for _idx, _po in _iblocks:
                    _ins_lesson_map[_isrc][_idx] = f"교과서{_ilessons[0]}과 본문{_idx + 1}"
                continue
            # lesson_block_counts 우선
            if lesson_block_counts and all(l in lesson_block_counts for l in _ilessons):
                _ins_lesson_map[_isrc] = {}
                _off = 0
                for _il in _ilessons:
                    _ic = lesson_block_counts[_il]
                    for _ii in range(_ic):
                        if _off + _ii < len(_iblocks):
                            _ins_lesson_map[_isrc][_off + _ii] = f"교과서{_il}과 본문{_ii + 1}"
                    _off += _ic
                continue
            # 페이지 갭 폴백
            _ipo = [po for _, po in _iblocks]
            if all(po >= 0 for po in _ipo) and len(_ipo) > 1:
                _igaps = [((_ipo[g] - _ipo[g-1]), g) for g in range(1, len(_ipo))]
                _igaps.sort(key=lambda x: -x[0])
                _ibounds = sorted([g[1] for g in _igaps[:len(_ilessons) - 1]])
                _ins_lesson_map[_isrc] = {}
                _isegs = [0] + _ibounds + [len(_iblocks)]
                for _ili, _il in enumerate(_ilessons):
                    for _isi in range(_isegs[_ili], _isegs[_ili + 1]):
                        _ins_lesson_map[_isrc][_isi] = f"교과서{_il}과 본문{_isi - _isegs[_ili] + 1}"

        all_insert = []
        source_counts = {}
        source_exam_idx = {}
        source_prev_qnum = {}
        _ins_counters = {}
        for block in sentence_insert_blocks:
            src = _nfc(block.get("source", ""))
            q_num = block.get("q_num", "")

            if q_num:
                scope_match = re.search(r"\(([^)]+)\)", src)
                wb_scope = scope_match.group(1) if scope_match else ""
                if scope_exams and src not in source_exam_idx:
                    source_exam_idx[src] = _build_scope_assigner(scope_exams, wb_scope)
                avail = source_exam_idx.get(src) if scope_exams else None
                direct_header = _q_num_to_header_by_scope(
                    q_num, scope_exams, wb_scope, available=avail
                ) if scope_exams else None
                if direct_header:
                    header = direct_header
                else:
                    header = _q_num_to_header(wb_scope, q_num)
            else:
                # 교과서 블록: 과 경계 맵 사용
                if src in _ins_lesson_map:
                    if src not in _ins_counters:
                        _ins_counters[src] = 0
                    _cidx = _ins_counters[src]
                    header = _ins_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                    _ins_counters[src] += 1
                else:
                    scope_match = re.search(r"\(([^)]+)\)", src)
                    scope = scope_match.group(1) if scope_match else "지문"
                    if src not in source_counts:
                        source_counts[src] = 0
                    source_counts[src] += 1
                    header = _scope_to_header(scope, source_counts[src])

            all_insert.append({
                "source": src,
                "header": header,
                "paras": block["paras"]
            })
        # 중복 헤더 제거
        seen_ins = set()
        deduped_ins = []
        for b in all_insert:
            if b["header"] in seen_ins:
                continue
            seen_ins.add(b["header"])
            deduped_ins.append(b)
        # 시험범위 필터링
        if scope_exams:
            deduped_ins = [b for b in deduped_ins if _is_in_scope(b["header"], scope_exams)]

        # 문장배열과 1:1 동기화 — 문장배열 헤더 기준으로 정렬/필터
        if vol1.get("문장배열"):
            arr_headers = [b["header"] for b in vol1["문장배열"]]
            ins_by_header = {b["header"]: b for b in deduped_ins}
            synced = []
            for h in arr_headers:
                if h in ins_by_header:
                    synced.append(ins_by_header[h])
                else:
                    # 문장삽입 누락 — 빈 블록으로 채움
                    synced.append({"source": "", "header": h, "paras": []})
            vol1["문장삽입"] = synced
        else:
            vol1["문장삽입"] = deduped_ins

    # 중요어휘
    if vocab_left_text and vocab_left_text.strip():
        vol1["중요어휘_왼"] = vocab_left_text.strip()
    if vocab_right_text and vocab_right_text.strip():
        vol1["중요어휘_오"] = vocab_right_text.strip()

    return vol1


def _build_vol2(grammar_lines_all, writing_kor, writing_view, scopes_info=None,
                scope_exams=None):
    """Vol2 데이터 구성."""
    vol2 = {}

    # 어법수정
    if grammar_lines_all:
        all_lines = []
        for block in grammar_lines_all:
            all_lines.extend(block["lines"])
        vol2["어법수정"] = all_lines
        # 어법수정 독자 헤더 추출 (YYMMQQ, 교과서 N과, SL 등)
        # 41/42 → 41~42 정규화 + scope 필터링
        grammar_headers = []
        filtered_lines = []
        skip_until_next_header = False
        for line in all_lines:
            is_header = (re.match(r"^\d{6}", line) or
                         re.match(r"^교과서", line) or
                         re.match(r"^\d{1,2}과\s", line) or
                         re.match(r"^S\d+과\s", line) or
                         re.match(r"^SL\s", line))
            if is_header:
                normalized = _normalize_q41_42(line.strip())
                in_scope = _is_in_scope(normalized, scope_exams) if scope_exams else True
                skip_until_next_header = not in_scope
                if in_scope:
                    grammar_headers.append(normalized)
                    filtered_lines.append(normalized)
            elif not skip_until_next_header:
                filtered_lines.append(line)
        vol2["어법수정"] = filtered_lines if scope_exams else all_lines
        if grammar_headers:
            vol2["어법_헤더"] = grammar_headers

    # 서술형 영작: 한글과 보기를 쌍으로
    # writing_kor/writing_view는 이제 dict 리스트: {"text": ..., "source": ..., "q_num": ...}
    if writing_kor or writing_view:
        # 워크북 번호 + q_num 순으로 정렬
        def _writing_sort_key(item):
            if not isinstance(item, dict):
                return (999, 999)
            src = _nfc(item.get("source", ""))
            q_num = item.get("q_num", "")
            m = re.search(r"워크북\s*(\d+)", src)
            wb_num = int(m.group(1)) if m else 999
            if q_num.startswith("본문"):
                q_sort = int(q_num.replace("본문", "") or "0")
            elif q_num and q_num[0].isdigit():
                q_first = re.match(r"(\d+)", q_num)
                q_sort = int(q_first.group(1)) if q_first else 999
            else:
                q_sort = 999
            return (wb_num, q_sort)

        writing_kor.sort(key=_writing_sort_key)
        writing_view.sort(key=_writing_sort_key)

        pairs = []
        max_len = max(len(writing_kor), len(writing_view))
        for i in range(max_len):
            pair = {}
            if i < len(writing_kor):
                kor = writing_kor[i]
                pair["korean"] = kor["text"] if isinstance(kor, dict) else kor
            if i < len(writing_view):
                view = writing_view[i]
                pair["choices"] = view["text"] if isinstance(view, dict) else view
            pairs.append(pair)
        vol2["서술형영작"] = pairs

        # 영작 헤더 목록 생성 — writing_kor의 q_num + source 정보를 활용
        # 과 번호 추적: "본문N" q_num이 리셋되면 다음 과로 전환
        writing_headers = []
        prev_qnum = None
        lesson_idx = 0  # 현재 과 인덱스 (0-based)
        lesson_labels = []  # scope에서 추출한 과 목록

        # scope에서 과 목록 추출 (첫 번째 교과서 소스 사용)
        for kor_item in writing_kor:
            if isinstance(kor_item, dict):
                source = kor_item.get("source", "")
                scope_match = re.search(r"\(([^)]+)\)", _nfc(source))
                if scope_match:
                    scope = scope_match.group(1)
                    # "교과서1,2과,SL" or "미래엔김3과" → ["1과", "2과", "SL"]
                    m_lesson = re.search(r"교과(?:서)?\s*([\d,S]+)\s*과", scope)
                    if not m_lesson:
                        m_lesson = re.search(r"(?:미래엔|능률|YBM|동아|비상|금성|천재)\S*?([\d,]+)\s*과", scope, re.IGNORECASE)
                    if m_lesson:
                        raw = m_lesson.group(1)
                        lesson_labels = [f"{l.strip()}과" for l in raw.split(",")]
                    # SL이 별도로 있으면 추가
                    if "SL" in scope and not any("S" in l for l in lesson_labels):
                        lesson_labels.append("SL")
                    break

        prev_본문_num = 0
        # 복합 scope용 exam_index 추적 (source별)
        w_exam_idx = {}  # source -> exam_index
        w_prev_q = {}    # source -> 이전 q_num 숫자
        for i, kor_item in enumerate(writing_kor):
            if isinstance(kor_item, dict):
                q_num = kor_item.get("q_num", "")
                source = kor_item.get("source", "")
                if q_num and q_num != prev_qnum:
                    scope_match = re.search(r"\(([^)]+)\)", _nfc(source))
                    scope = scope_match.group(1) if scope_match else ""

                    # 본문N 리셋 감지: 본문 번호가 감소하면 다음 과
                    lesson_label = None
                    if q_num.startswith("본문"):
                        cur_num = int(q_num.replace("본문", "") or "0")
                        if cur_num <= prev_본문_num and prev_본문_num > 0:
                            lesson_idx += 1
                        prev_본문_num = cur_num
                        if lesson_labels and lesson_idx < len(lesson_labels):
                            lesson_label = lesson_labels[lesson_idx]
                    elif not q_num[0].isdigit():
                        # SL 등 비숫자 q_num
                        pass
                    else:
                        # 숫자 q_num (모의고사 등) — 본문 카운터 리셋
                        prev_본문_num = 0
                        # 복합 scope: q_num 리셋 감지
                        if source not in w_exam_idx:
                            w_exam_idx[source] = 0
                            w_prev_q[source] = 0
                        cur_q_num = int(re.match(r"(\d+)", q_num).group(1)) if re.match(r"(\d+)", q_num) else 0
                        if cur_q_num < w_prev_q[source] and w_prev_q[source] > 0:
                            w_exam_idx[source] += 1
                        w_prev_q[source] = cur_q_num

                    # scope_exams 직접 매칭 (우선)
                    direct = None
                    if scope_exams and q_num and q_num[0].isdigit() and not q_num.startswith("본문"):
                        direct = _q_num_to_header_by_scope(q_num, scope_exams, scope)
                    if direct:
                        header = direct
                    else:
                        exam_idx = w_exam_idx.get(source, 0)
                        header = _writing_q_to_header(scope, q_num, lesson_label=lesson_label)
                        if q_num and q_num[0].isdigit() and not q_num.startswith("본문"):
                            header = _q_num_to_header(scope, q_num, exam_index=exam_idx)
                    # scope 필터링
                    if not scope_exams or _is_in_scope(header, scope_exams):
                        writing_headers.append({"header": header, "start_idx": i})
                    prev_qnum = q_num

        if writing_headers:
            vol2["영작_헤더_상세"] = writing_headers

    return vol2


def parse_extracted(extracted_path, vocab_left, vocab_right,
                    school, grade, exam_period, job_dir, log,
                    grammar_word_lines=None, lesson_block_counts=None):
    """추출 데이터 + 웹 입력을 통합하여 content.json 생성."""
    log("[파싱] 추출 데이터 분류 중...")

    with open(extracted_path, encoding="utf-8") as f:
        extracted = json.load(f)

    stories = extracted.get("stories", [])
    sentence_blocks, insert_blocks, grammar_blocks, writing_kor, writing_view = _classify_stories(stories)

    log(f"  문장배열: {len(sentence_blocks)}개 블록 ({sum(len(b['items']) for b in sentence_blocks)}줄)")
    log(f"  문장삽입: {len(insert_blocks)}개 블록")
    log(f"  어법수정(A1): {len(grammar_blocks)}개 블록 ({sum(len(b['lines']) for b in grammar_blocks)}줄)")
    log(f"  영작 한글: {len(writing_kor)}줄, 보기: {len(writing_view)}줄")

    # 시험범위 데이터 가져오기
    scope_exams = None
    try:
        from engines.final.vocab_fetcher import fetch_scope_for_school
        scope_exams = fetch_scope_for_school(school, log=None)
        if scope_exams:
            log(f"  시험범위 필터: {len(scope_exams)}개 시험")
    except Exception:
        pass

    vol1 = _build_vol1(sentence_blocks, insert_blocks, vocab_left, vocab_right,
                       scope_exams=scope_exams,
                       lesson_block_counts=lesson_block_counts)

    # Word에서 추출한 어법수정 데이터 → grammar_blocks에 추가 (A1 대신 사용)
    if grammar_word_lines:
        # Word 어법수정이 있으면 A1 추출은 무시하고 Word만 사용
        grammar_blocks = [{
            "source": "어법수정 Word",
            "lines": grammar_word_lines
        }]
        log(f"  어법수정(Word): {len(grammar_word_lines)}줄 (A1 대체)")

    vol2 = _build_vol2(grammar_blocks, writing_kor, writing_view,
                       scope_exams=scope_exams)

    # Vol1 문장배열의 헤더 목록을 Vol2 영작에 공유
    # 어법수정은 독자 헤더가 있으므로 덮어쓰지 않음
    if vol1.get("문장배열"):
        all_headers = [b["header"] for b in vol1["문장배열"]]
        if vol2.get("서술형영작"):
            vol2["영작_헤더"] = all_headers
        if vol2.get("어법수정") and not vol2.get("어법_헤더"):
            vol2["어법_헤더"] = all_headers

    content = {
        "school": school,
        "grade": grade,
        "exam_period": exam_period,
        "vol1": vol1,
        "vol2": vol2,
        "총_문장배열": sum(len(b["items"]) for b in sentence_blocks),
        "총_문장삽입": len(insert_blocks),
        "총_어법수정": sum(len(b["lines"]) for b in (grammar_blocks if grammar_blocks else [])),
        "총_서술형영작": len(writing_kor),
    }

    content_path = os.path.join(job_dir, "content.json")
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    log(f"[파싱] content.json 생성 완료")
    return content_path
