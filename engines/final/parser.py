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


def _is_deeplearning_workbook(source):
    """딥러닝(=본문6) 전용 워크북 여부.

    Why: 딥러닝 워크북은 1과/2과의 본문6 콘텐츠가 한 스토리 안에 섞여 들어 있고,
         스토리 내부의 {1}/{2} (또는 [1]/[2]) 마커가 '본문번호'가 아니라 '과 번호'를 의미한다.
         일반 교과서 워크북은 마커 N=본문N이지만, 딥러닝 워크북은 마커 N=N과 본문6이다.
    """
    base = _nfc(os.path.basename(source or ""))
    return "\ub525\ub7ec\ub2dd" in base or "\ub525 \ub7ec\ub2dd" in base


# ── 마더텅 지문 출처 매핑 (워크북 내 지문 순번 → YYMMQQ) ──────────────
# 구조: {섹션번호: {순번: "YYMMQQ", ...}, ...}
# 예: _MT_MAP[3][1] = "221120" (마더텅3 워크북 1번째 지문은 2022년 11월 20번)
_MT_MAP = None
# 섹션 라벨 맵: {3: "필자의 주장", 4: "의미 추론", 5: "요지 추론"}
# 엑셀 R3 헤더에서 추출. 예전 기출 폴더 이름 조회용.
_MT_SECTION_LABELS = None


def load_mothertongue_map(xlsx_path):
    """마더텅 지문 출처 엑셀 로드 → 전역 _MT_MAP / _MT_SECTION_LABELS 설정.

    엑셀 구조:
        R3 (헤더): (None, "03 필자의 주장", "04 의미 추론", "05 요지 추론")
        R4~ (데이터): (순번, YYMMQQ_3, YYMMQQ_4, YYMMQQ_5)
    """
    global _MT_MAP, _MT_SECTION_LABELS
    _MT_MAP = None
    _MT_SECTION_LABELS = None
    if not xlsx_path:
        return
    try:
        from openpyxl import load_workbook
        path = os.path.expanduser(xlsx_path)
        if not os.path.exists(path):
            return
        wb = load_workbook(path, data_only=True)
        ws = wb.active
        mapping = {}
        section_nums = []
        section_labels = {}
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 2:  # R3: 섹션 헤더 행
                for cell in row[1:]:
                    if cell:
                        m = re.match(r"^\s*(\d+)\s*(.*)$", str(cell))
                        if m:
                            sect_num = int(m.group(1))
                            sect_label = m.group(2).strip()
                            section_nums.append(sect_num)
                            if sect_label:
                                section_labels[sect_num] = sect_label
                        else:
                            section_nums.append(None)
                    else:
                        section_nums.append(None)
            elif i >= 3 and section_nums:
                seq = row[0]
                if not isinstance(seq, int):
                    continue
                for j, val in enumerate(row[1:]):
                    if j >= len(section_nums) or section_nums[j] is None or val is None:
                        continue
                    sect = section_nums[j]
                    mapping.setdefault(sect, {})[seq] = str(val).zfill(6)
        if mapping:
            _MT_MAP = mapping
        if section_labels:
            _MT_SECTION_LABELS = section_labels
    except Exception:
        _MT_MAP = None
        _MT_SECTION_LABELS = None


def get_mothertongue_map():
    """현재 로드된 _MT_MAP 반환 (외부 모듈에서 조회용). 미로드 시 None."""
    return _MT_MAP


def get_mothertongue_section_labels():
    """엑셀 R3 헤더에서 파싱한 {섹션번호: 섹션라벨} 반환. 예: {3: "필자의 주장"}."""
    return _MT_SECTION_LABELS


def _mt_lookup(scope_text, seq):
    """마더텅 scope에서 섹션 번호 추출 + 순번으로 YYMMQQ 조회.

    Returns: YYMMQQ 문자열 또는 None
    """
    if not _MT_MAP or not scope_text or not isinstance(seq, int) or seq <= 0:
        return None
    m = re.search(r"\ub9c8\ub354\ud145\s*(\d+)", scope_text)
    if not m:
        return None
    return _MT_MAP.get(int(m.group(1)), {}).get(seq)


def _build_mt_seq_map(stories):
    """마더텅 워크북별 지문 시작 page_off → 원고_지문_순번 맵을 구축한다.

    _MT_MAP 조회용 seq는 워크북 원고 내 지문 출현 순번이어야 한다.
    실시간 카운터(w_mt_total)는 영작 스타일이 있는 스토리에서만 증가하므로,
    영작 없는 지문 페이지를 건너뛰어 YYMMQQ 매핑이 어긋난다.
    이를 방지하기 위해 원고 전체에서 "문장 배열" 스타일이 있는 스토리를
    지문 대표 스토리로 간주해 pageOff 순으로 seq 번호를 매긴다.
    (문장배열은 지문당 1개가 원칙이므로 지문 경계 식별에 가장 신뢰 가능.)

    Returns: {src_nfc: [(start_page_off, seq), ...]} — start_page_off 오름차순.
    writing_kor item의 page_off에 대해 "가장 큰 start_page_off <= page_off"의 seq 사용.
    """
    from collections import defaultdict
    sentence_styles = {"\ubb38\uc7a5 \ubc30\uc5f4 \uadf8\ub7a9", "C_\ubb38\uc7a5\ubc30\uc5f4", "C1_\ubb38\uc7a5 \ubc30\uc5f4"}

    per_source = defaultdict(list)
    for st in stories:
        src = st.get("source_file", "")
        po = st.get("pageOff", -1)
        if not src or po < 0:
            continue
        per_source[src].append(st)

    result = {}
    for src, sts in per_source.items():
        src_nfc = _nfc(src)
        scope_m = re.search(r"\(([^)]+)\)", src_nfc)
        scope = scope_m.group(1) if scope_m else ""
        if "\ub9c8\ub354\ud145" not in scope:
            continue

        sts.sort(key=lambda s: (s.get("pageOff", -1), s.get("idx", 0)))
        seq_entries = []  # [(start_page_off, seq), ...]
        seq = 0
        seen_pages = set()
        for st in sts:
            po = st.get("pageOff", -1)
            if po in seen_pages:
                continue
            has_sentence = False
            for p in st.get("paras", []):
                if p.get("s", "") in sentence_styles:
                    has_sentence = True
                    break
            if has_sentence:
                seq += 1
                seq_entries.append((po, seq))
                seen_pages.add(po)

        if seq_entries:
            result[src_nfc] = seq_entries

    return result


def _mt_seq_lookup(mt_seq_map, src_nfc, page_off):
    """writing_kor item의 page_off에 대응하는 원고 지문 순번 조회.

    가장 큰 start_page_off <= page_off 의 seq 반환.
    맵에 없거나 범위 밖이면 None.
    """
    if not mt_seq_map or not src_nfc or page_off is None or page_off < 0:
        return None
    entries = mt_seq_map.get(src_nfc)
    if not entries:
        return None
    result = None
    for start_po, seq in entries:
        if start_po <= page_off:
            result = seq
        else:
            break
    return result


def _clean_text(t):
    """추출 텍스트에서 InDesign 객체 교체 문자(￼) 등 정리."""
    # Object Replacement Character (U+FFFC) 제거
    t = t.replace("\ufffc", "").strip()
    return t


def _normalize_question_text(t):
    """워크북 추출 텍스트의 알려진 비표준 표기를 표준화.

    - 발문 표준화: 워크북마다 발문 표현이 미세하게 달라 동일 책자 내 일관성 유지.
    - 영문 typo 교정 (`isnot` → `is not`).
    """
    if not t:
        return t
    # 문장삽입/순서 발문 표준화
    t = re.sub(r"이어질\s*글의\s*적절한\s*순서를\s*쓰시오\.\.?",
               "이어질 문장들의 적절한 순서를 쓰시오.", t)
    t = re.sub(r"들어갈\s*위치로\s*알맞은\s*곳을\s*고르시오",
               "들어갈 곳으로 적당한 곳을 고르시오", t)
    # 영문 띄어쓰기 누락
    t = re.sub(r"\bisnot\b", "is not", t)
    return t


def _is_insert_noise(txt):
    """문장삽입 추출 시 불필요한 단락인지 확인.

    워크북에서 추출된 포맷팅 잔여물: 순번(01, 02...), 화살표(➡, ＞), 빈줄 등.
    올포 공용 파일의 페이지 레이블: "분석", "[분석]", "서술", "논술" 등.
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
    # 올포 공용 파일의 페이지 라벨 노이즈
    if t in ("\ubd84\uc11d", "[\ubd84\uc11d]", "\uc11c\uc220", "\uc11c\uc220\ud615",
             "\ub17c\uc220", "\ub17c\uc220\ud615"):
        return True
    # [N] 형식 (영작 배열 [2], [3])
    if re.match(r"^\[\d+\]$", t):
        return True
    return False


def _normalize_qmarker_text(text):
    """문항번호 마커의 잉여 괄호 노이즈를 제거.

    예: '{05]]~06}' → '{05~06}', '[01[[~02]' → '[01~02]'
    Why: 분석편 원본에서 '{05]]~06}'처럼 '[' ']' 가 잉여 삽입된 오타가 발견됨.
         이를 표준 '{NN~NN}' 형식으로 정규화해야 헤더로 인식된다.
    How to apply: '{...}' 또는 '[...]'로 둘러싸인 텍스트 한정으로 내부 '[' ']'만 제거.
    """
    t = text.strip()
    if len(t) < 2:
        return t
    open_ch, close_ch = t[0], t[-1]
    if (open_ch, close_ch) not in (("{", "}"), ("[", "]")):
        return t
    inner = t[1:-1].replace("[", "").replace("]", "")
    return f"{open_ch}{inner}{close_ch}"


def _is_question_header(text):
    """단락이 문항번호 헤더({20}, {21}, [20], [21], {41~42}, 20, 41~42, [Gateway], {Example 1} 등)인지 확인."""
    t = _normalize_qmarker_text(text.strip())
    # [Gateway] 또는 {Gateway} (고3 수능특강 분석편)
    if re.match(r"^[\[{]Gateway[\]}]$", t, re.IGNORECASE):
        return True
    # {Example N} / [Example N] (리딩파워)
    if re.match(r"^[\[{]Example\s*\d+[\]}]$", t, re.IGNORECASE):
        return True
    # {20}, {21~22}, {41~42} 등
    if re.match(r"^\{\d+(?:[~\-]\d+)?\}$", t):
        return True
    # [20], [21] 등
    if re.match(r"^\[\d+(?:[~\-]\d+)?\]$", t):
        return True
    # 분리 추출된 복합 헤더: "{41}{~42}", "[41][~42]" (extractor가 분할 추출한 경우)
    if re.match(r"^[\[{]\d+[\]}][\[{][~\-]\d+[\]}]$", t):
        return True
    # 중괄호 없는 plain 숫자: 18~45 범위 (모의고사 문항번호)
    m = re.match(r"^(\d{2})(?:[~\-](\d{2}))?$", t)
    if m:
        num = int(m.group(1))
        if 18 <= num <= 45:
            return True
    return False


def _extract_question_number(text):
    """헤더에서 문항번호 추출. '{20}' → '20', '{41~42}' → '41~42', '20' → '20', '[Gateway]' → 'Gateway', '{Example 1}' → 'Example1'"""
    t = _normalize_qmarker_text(text.strip())
    # [Gateway] 또는 {Gateway}
    if re.match(r"^[\[{]Gateway[\]}]$", t, re.IGNORECASE):
        return "Gateway"
    # {Example N} / [Example N] → "ExampleN" (공백 제거)
    m_ex = re.match(r"^[\[{]Example\s*(\d+)[\]}]$", t, re.IGNORECASE)
    if m_ex:
        return f"Example{m_ex.group(1)}"
    # {XX} or [XX] 형식
    m = re.match(r"^[\[{](\d+(?:[~\-]\d+)?)[\]}]$", t)
    if m:
        return m.group(1)
    # 분리 추출 복합: "{41}{~42}" → "41~42"
    m_sp = re.match(r"^[\[{](\d+)[\]}][\[{]([~\-])(\d+)[\]}]$", t)
    if m_sp:
        return f"{m_sp.group(1)}{m_sp.group(2)}{m_sp.group(3)}"
    # plain 숫자 형식: 20, 41~42
    m2 = re.match(r"^(\d{2}(?:[~\-]\d{2})?)$", t)
    if m2:
        return m2.group(1)
    return ""


def _merge_split_qmarkers(paras):
    """[기본 단락] 스타일에서 '[' + 'N]' 형태로 쪼개진 헤더 마커를 한 단락으로 합친다.

    Why: 분석편 원본에서 '[4]'가 두 단락 '['(空)와 '4]'로 쪼개진 케이스 발견.
         이대로면 _is_question_header가 어느 쪽도 인식 못해 영작/배열 블록이 누락됨.
    How to apply: [기본 단락] 스타일 한정. '[' 단독 단락 다음이 '\\d+\\]'면 합친다.
    """
    if not paras:
        return paras
    out = []
    i = 0
    n = len(paras)
    BASIC = ("[기본 단락]", "[Basic Paragraph]")
    while i < n:
        p = paras[i]
        ps = p.get("s", "")
        pt = (p.get("t") or "").strip()
        if ps in BASIC and pt in ("[", "{"):
            # 다음 비어있지 않은 [기본 단락] 단락을 찾아 매칭 시도
            j = i + 1
            while j < n:
                q = paras[j]
                qs = q.get("s", "")
                qt = (q.get("t") or "").strip()
                if qt == "":
                    j += 1
                    continue
                if qs in BASIC and (
                    (pt == "[" and re.match(r"^\d+(?:[~\-]\d+)?\]$", qt)) or
                    (pt == "{" and re.match(r"^\d+(?:[~\-]\d+)?\}$", qt))
                ):
                    out.append({"s": ps, "t": pt + qt})
                    i = j + 1
                    break
                # 매칭 실패 — 원본 그대로 유지
                out.append(p)
                i += 1
                break
            else:
                out.append(p)
                i += 1
        else:
            out.append(p)
            i += 1
    return out


def _dedupe_deeplearning_body_labels(sentence_blocks, insert_blocks, log=lambda m: None):
    """딥러닝 워크북이 본문N 콘텐츠를 제공하면, 비-딥러닝 워크북의 잔존 본문N 라벨 블록을 제거한다.

    워크북01의 InDesign 잔존(ghost) `06` 섹션처럼 PDF에 출력되지 않지만 추출에 잡히는
    유령 콘텐츠가 1과/2과 본문6 슬롯을 잘못 채우는 문제를 해결한다.
    """
    # 딥러닝 워크북이 어떤 본문번호를 다루는지 수집 (예: {6})
    dl_body_nums = set()
    for blocks in (sentence_blocks, insert_blocks):
        for blk in blocks:
            if not _is_deeplearning_workbook(blk.get("source", "")):
                continue
            plabel = blk.get("passage_label", "") or ""
            m = re.match(r"^본문(\d+)@과", plabel)
            if m:
                dl_body_nums.add(m.group(1))

    if not dl_body_nums:
        return

    def _filter(blocks, label):
        kept = []
        removed = 0
        # (src, page_off) 별 카운터 — 비-딥러닝 교과서 워크북에서 동일 page_off에
        # 두 번째 이상으로 등장한 블록은 잔존 콘텐츠로 간주하여 제거.
        po_seen = {}  # (src_nfc, page_off) -> count
        for blk in blocks:
            src = blk.get("source", "")
            src_nfc = _nfc(src)
            plabel = blk.get("passage_label", "") or ""
            # 1) 명시적 본문N 라벨 제거 (이전 로직)
            if not _is_deeplearning_workbook(src):
                m = re.match(r"^본문(\d+)$", plabel)
                if m and m.group(1) in dl_body_nums:
                    removed += 1
                    continue
                # 2) 동일 page_off 중복(워크북01 06 잔존 패턴): 같은 (src, page_off) 두 번째부터 제거
                #    비-딥러닝 교과서 워크북(scope에 N과 포함)에 한해 적용.
                _scope_m = re.search(r"\(([^)]+)\)", src_nfc)
                _scope = _scope_m.group(1) if _scope_m else ""
                _is_textbook_scope = bool(re.search(r"\d+\s*\uacfc", _scope)) and "\uc62c\ud3ec" not in _scope and "\uc62c\ub9bc\ud3ec\uc2a4" not in _scope
                if _is_textbook_scope:
                    po = blk.get("page_off", -1)
                    if po >= 0:
                        key = (src_nfc, po)
                        po_seen[key] = po_seen.get(key, 0) + 1
                        if po_seen[key] >= 2:
                            removed += 1
                            continue
            kept.append(blk)
        if removed:
            log(f"  [딥러닝 충돌] {label}: 비-딥러닝 워크북의 본문{','.join(sorted(dl_body_nums))} 잔존 블록 {removed}개 제거")
        return kept

    # 인플레이스 변경
    new_sa = _filter(sentence_blocks, "문장배열")
    new_si = _filter(insert_blocks, "문장삽입")
    sentence_blocks[:] = new_sa
    insert_blocks[:] = new_si


def _assign_deeplearning_writing_lesson(sentence_blocks, writing_kor, writing_view, log=lambda m: None):
    """딥러닝 워크북의 영작 항목에 q_num='본문N' + lesson hint 부여.

    딥러닝 영작 스토리는 마커({1}/{2} 등) 없이 1과/2과 본문6 콘텐츠가 한 스토리로 섞여 있다.
    같은 워크북의 sentence_blocks(이미 passage_label="본문N@과M"로 라벨링됨) 단어셋에
    영작 보기(English 문장)의 단어셋이 겹치는 비율로 과 번호를 추정한다.
    """
    # source(NFC) -> {lesson(str): set(words)}
    src_lesson_words = {}
    src_body_num = {}  # source -> "6" (딥러닝은 본문6 고정)
    for blk in sentence_blocks:
        src = _nfc(blk.get("source", ""))
        if not _is_deeplearning_workbook(src):
            continue
        plabel = blk.get("passage_label", "") or ""
        m = re.match(r"^본문(\d+)@과(\d+)$", plabel)
        if not m:
            continue
        body_num = m.group(1)
        lesson = m.group(2)
        # 영문 단어 추출 (3자 이상)
        wset = set()
        for it in blk.get("items", []):
            if not it:
                continue
            for tok in re.findall(r"[A-Za-z][A-Za-z'\u2019]+", it):
                if len(tok) >= 3:
                    wset.add(tok.lower())
        src_lesson_words.setdefault(src, {}).setdefault(lesson, set()).update(wset)
        src_body_num[src] = body_num

    if not src_lesson_words:
        return

    def _classify_entry(text, lesson_words):
        """text의 단어들이 어느 lesson과 가장 많이 겹치는지 반환."""
        if not text:
            return None
        toks = set()
        for tok in re.findall(r"[A-Za-z][A-Za-z'\u2019]+", text):
            if len(tok) >= 3:
                toks.add(tok.lower())
        if not toks:
            return None
        best_lesson = None
        best_score = 0
        for lesson, wset in lesson_words.items():
            score = len(toks & wset)
            if score > best_score:
                best_score = score
                best_lesson = lesson
        return best_lesson if best_score > 0 else None

    # writing_kor와 writing_view는 페어로 진행됨. 같은 인덱스 = 같은 entry.
    # 매칭 우선순위: writing_view(영문)에서 단어 매칭이 더 신뢰도 높음.
    n = max(len(writing_kor), len(writing_view))
    for i in range(n):
        kor = writing_kor[i] if i < len(writing_kor) else None
        view = writing_view[i] if i < len(writing_view) else None
        # 두 항목 모두 같은 source여야 함
        src = _nfc((view or kor or {}).get("source", ""))
        if src not in src_lesson_words:
            continue
        # 이미 q_num이 있으면 스킵 (마커가 있는 경우)
        if (kor and (kor.get("q_num") or "").strip()) or (view and (view.get("q_num") or "").strip()):
            continue
        # 영문 보기 우선, 없으면 한글로 매칭(한글 매칭은 영문 단어 토큰이 없으니 실패할 수 있음)
        text_for_match = (view or {}).get("text", "") or (kor or {}).get("text", "")
        lesson = _classify_entry(text_for_match, src_lesson_words[src])
        if not lesson:
            continue
        body = src_body_num.get(src, "6")
        qn = f"본문{body}"
        if kor:
            kor["q_num"] = qn
            kor["_dl_lesson"] = lesson
        if view:
            view["q_num"] = qn
            view["_dl_lesson"] = lesson
        log(f"  [딥러닝 영작] entry[{i}] → {qn} (과{lesson})")


def _classify_stories(stories):
    """추출된 스토리들을 유형별로 분류.

    모의고사 워크북은 하나의 스토리에 여러 지문이 {20}, {21}, ... 헤더로
    구분되어 있으므로, 이 헤더를 기준으로 블록을 분리한다.
    """
    # 분리 마커 사전 정규화: '[' + '4]' → '[4]'
    for _st in stories:
        _ps = _st.get("paras", [])
        if _ps:
            _st["paras"] = _merge_split_qmarkers(_ps)

    # 리딩파워 스토리의 lecture 재할당 — 파일명에서 강 목록 파싱 + 스토리 순서 매핑
    # (extracted.json의 lecture 값이 첫 강 고정이라 1,2강 파일에서도 lecture=9로 잘못됨)
    from collections import defaultdict
    _rp_story_groups = defaultdict(list)
    for _st in stories:
        _sf = _nfc(_st.get("source_file", ""))
        if _is_rp_source(_sf):
            _rp_story_groups[_sf].append(_st)
    for _sf, _sl in _rp_story_groups.items():
        _m_lec = re.search(r"\ub9ac\ub529\ud30c\uc6cc\s*([\d,\s]+)\s*\uac15", _sf)
        if not _m_lec:
            continue
        _lec_list = [int(x.strip()) for x in _m_lec.group(1).split(",") if x.strip().isdigit()]
        if not _lec_list:
            continue
        _sl.sort(key=lambda s: s.get("pageOff", 0))
        # 영작 스토리 필터
        _wr_styles = {"C2_\uc601\uc791 \ubc30\uc5f4 \ubc88\ud638",
                      "C_\uc601\uc791 \ubc30\uc5f4 \ubc88\ud638",
                      "C2_\uc601\uc791 \ubc30\uc5f4 \ubcf4\uae30",
                      "\uc601\uc791 \ubc30\uc5f4 \ubcf4\uae30"}
        _wr_stories = [s for s in _sl if any(
            p.get("s", "") in _wr_styles for p in s.get("paras", [])
        )]
        # 영작 스토리 수 == 강 수이면 1:1
        if len(_wr_stories) == len(_lec_list):
            for _s, _lec in zip(_wr_stories, _lec_list):
                _s["lecture"] = _lec
        elif len(_wr_stories) == 1 and len(_lec_list) >= 1:
            # 스토리 하나에 여러 강이 혼합된 경우 — 첫 강으로 설정 (lecture_override가 처리)
            _wr_stories[0]["lecture"] = _lec_list[0]

        # 문장배열 스토리도 동일 로직으로 강 재할당 (리딩파워 워크북은 강 수만큼 스토리 그룹)
        _sent_styles = {"\ubb38\uc7a5 \ubc30\uc5f4 \uadf8\ub7a9", "C_\ubb38\uc7a5\ubc30\uc5f4", "C1_\ubb38\uc7a5 \ubc30\uc5f4"}
        _sent_stories = [s for s in _sl if any(
            p.get("s", "") in _sent_styles for p in s.get("paras", [])
        )]
        # 문장배열 스토리 수 == 강 수이면 1:1
        if len(_sent_stories) == len(_lec_list):
            for _s, _lec in zip(_sent_stories, _lec_list):
                _s["lecture"] = _lec
        elif len(_sent_stories) >= len(_lec_list) and len(_sent_stories) % len(_lec_list) == 0:
            # 스토리 수가 강 수의 배수이면 균등 분할
            _per_lec = len(_sent_stories) // len(_lec_list)
            for _i, _s in enumerate(_sent_stories):
                _lec_idx = min(_i // _per_lec, len(_lec_list) - 1)
                _s["lecture"] = _lec_list[_lec_idx]
        elif len(_sent_stories) == 1 and len(_lec_list) >= 1:
            _sent_stories[0]["lecture"] = _lec_list[0]

    sentence_arr = []      # 문장배열 (Vol1)
    sentence_insert = []   # 문장삽입/순서배열 (Vol1)
    grammar_fix = []       # 어법수정 (Vol2)
    writing_kor = []       # 영작 한글 (Vol2)
    writing_view = []      # 영작 보기 (Vol2)
    vocab_blocks = []      # 빈칸어휘 (고3 중요어휘용)
    grammar_select = []    # 어법선택 (고3 어법수정용)

    # 스타일 → 유형 매핑
    sentence_styles = {"문장 배열 그랩", "C_문장배열", "C1_문장 배열"}
    insert_styles = {"하단 문제", "C1_문장 배열 하단", "C1_문장 배열 하단 지문",
                     "문장 배열 하단 ", "문장 배열 하단 문제"}
    grammar_styles = {"A_어법 수정"}
    grammar_select_styles = {"A1_어법 선택", "어휘 선택 그랩"}     # 고3 어법수정 대체 (교과서는 '어휘 선택 그랩' 사용)
    vocab_styles = {"C2_빈칸 어휘", "C_빈칸 어법 번호"}            # 고3 중요어휘 영어 (교과서는 'C_빈칸 어법 번호')
    vocab_kr_styles = {"C2_빈칸 어휘 한글"}      # 고3 중요어휘 한글
    writing_kor_styles = {"C_영작 배열 번호", "C2_영작 배열 번호", "C_영작 배열 번호_"}
    writing_view_styles = {"영작 배열 보기", "C2_영작 배열 보기"}
    # B1 관련 스타일 (이 스타일이 있는 스토리는 문장삽입으로 분류하지 않음)
    b1_styles = {"B1_내용 정리", "B1_내용 정리 주제", "B1_내용 정리 제목",
                 "B1_본문 박스", "하단 문제_지문", "하단 문제_선지"}

    # pageOff → 문항번호 매핑 구축 (문장삽입 스토리의 헤더에서 추출)
    # 동시에 발문 있는 (src, page_off) 수집 — 같은 페이지에 발문이 있으면
    # sentence 스타일만 가진 별개 스토리(마더텅 상단 프레임 등)는 insert 쪽에만
    # 배치하기 위해 sentence 분류에서 스킵한다.
    page_to_qnum = {}  # {pageOff: q_num, ...}  (source_file별)
    pages_with_question = set()  # (src, page_off) — 발문(insert 스타일) 있는 페이지
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
        if page_off >= 0:
            pages_with_question.add((src, page_off))
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
            if style in vocab_styles or style in vocab_kr_styles:
                types_found.add("vocab")
            if style in grammar_select_styles:
                types_found.add("grammar_select")

        # B1 스토리에서 하단 문제가 있어도 문장삽입으로 분류하지 않음
        # (B1_내용 정리 등 B1 스타일이 포함된 스토리는 insert에서 제외)
        has_b1 = bool(all_styles & b1_styles)
        if has_b1:
            types_found.discard("insert")

        # sentence + insert 동시 포함 스토리 (모의고사 대형 스레드):
        # 둘 다 처리 — sentence_styles 항목은 문장배열로, insert_styles 항목은 문장삽입으로
        # (교과서 워크북은 별도 스토리이므로 이 경우에 해당 안 됨)

        # insert + B1 아닌 경우만 유효 (sentence 없어도 OK — 교과서 문장삽입은 별도 스토리)

        source = story.get("source_file", "")
        page_off = story.get("pageOff", -1)
        lecture = story.get("lecture", 0)
        olpo_label = story.get("olpoLabel", "")
        # 모의고사 6자리 출처코드(YYMMQQ) — 워크북에 박혀있는 진짜 지문번호.
        # 있으면 헤더 결정 시 다른 모든 로직보다 우선한다.
        exam_code = story.get("examCode", "")

        # 문장배열: {XX} 헤더로 블록 분리
        if "sentence" in types_found:
            # 마더텅 워크북은 상단(배열그랩) = 문장배열 문제, 하단(발문+배열하단) =
            # 문장삽입/순서배열 문제로 같은 지문에 대해 두 문제 타입이 출제된다.
            # 따라서 sentence와 insert 양쪽 모두 배치해야 한다 (교과서와 동일 구조).
            # 단, 같은 스토리 안에 sentence+insert가 공존하는 대형 threaded story
            # (모의고사 워크북)는 `_split_sentence_blocks` 내부의 `current_has_insert`
            # 로직이 블록 단위로 처리한다.
            # 1순위: extractor가 같은 페이지에서 읽은 지문번호
            page_qnum = story.get("pageQNum", "")
            # 2순위: 같은 페이지의 문장삽입 헤더
            if not page_qnum:
                page_qnum = page_to_qnum.get((source, page_off), "")
            _before = len(sentence_arr)
            _split_sentence_blocks(paras, source, sentence_styles, sentence_arr,
                                   page_qnum=page_qnum, page_off=page_off,
                                   lecture=lecture, olpo_label=olpo_label)
            if exam_code:
                for _bi in range(_before, len(sentence_arr)):
                    sentence_arr[_bi]["exam_code"] = exam_code

        # 문장삽입/순서배열: {XX} 헤더로 블록 분리
        if "insert" in types_found:
            ins_page_qnum = story.get("pageQNum", "")
            if not ins_page_qnum:
                ins_page_qnum = page_to_qnum.get((source, page_off), "")
            _before = len(sentence_insert)
            _split_insert_blocks(paras, source, insert_styles, sentence_insert,
                                 page_qnum=ins_page_qnum, page_off=page_off,
                                 lecture=lecture, olpo_label=olpo_label)
            if exam_code:
                for _bi in range(_before, len(sentence_insert)):
                    sentence_insert[_bi]["exam_code"] = exam_code

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
            _kor_before = len(writing_kor)
            _view_before = len(writing_view)
            _split_writing_blocks(paras, source, writing_kor_styles,
                                  writing_view_styles, writing_kor, writing_view,
                                  page_off=page_off, lecture=lecture,
                                  olpo_label=olpo_label)
            if exam_code:
                for _bi in range(_kor_before, len(writing_kor)):
                    writing_kor[_bi]["exam_code"] = exam_code
                for _bi in range(_view_before, len(writing_view)):
                    writing_view[_bi]["exam_code"] = exam_code

        # 빈칸어휘 (고3 중요어휘용)
        if "vocab" in types_found:
            en_lines = []
            kr_lines = []
            for p in paras:
                txt = _clean_text(p.get("t", ""))
                s = p.get("s", "")
                if s in vocab_styles and txt:
                    en_lines.append(txt)
                elif s in vocab_kr_styles and txt:
                    kr_lines.append(txt)
            if en_lines or kr_lines:
                vocab_blocks.append({
                    "source": source, "page_off": page_off,
                    "en": en_lines, "kr": kr_lines
                })

        # 어법선택 (고3 어법수정용)
        if "grammar_select" in types_found:
            lines = []
            for p in paras:
                txt = p.get("t", "").strip()
                if p.get("s", "") in grammar_select_styles and txt:
                    lines.append(txt)
            if lines:
                # 수능특강 분석편(교과서가 아닌 경우)에서는 {XX}/{Gateway} 헤더 기준으로 블록 분할.
                # 교과서 분석편은 기존 동작 유지(한 스토리 = 한 블록).
                is_tb = _is_textbook_source(source)
                header_pat = re.compile(r"^\{(Gateway|\d+(?:[~\-]\d+)?)\}$", re.IGNORECASE)
                if not is_tb and any(header_pat.match(l.strip()) for l in lines):
                    sub_qnum = ""
                    sub_lines = []
                    sub_blocks = []
                    for l in lines:
                        m = header_pat.match(l.strip())
                        if m:
                            if sub_lines:
                                sub_blocks.append((sub_qnum, sub_lines))
                            raw = m.group(1)
                            if raw.lower() == "gateway":
                                sub_qnum = "Gateway"
                            else:
                                # {41~42} → "41~42", {01} → "01" (zfill 유지)
                                _mm = re.match(r"^(\d+)([~\-])(\d+)$", raw)
                                if _mm:
                                    sub_qnum = f"{_mm.group(1).zfill(2)}{_mm.group(2)}{_mm.group(3).zfill(2)}"
                                else:
                                    sub_qnum = raw.zfill(2)
                            sub_lines = [l]
                        else:
                            sub_lines.append(l)
                    if sub_lines:
                        sub_blocks.append((sub_qnum, sub_lines))
                    for q, ls in sub_blocks:
                        if ls:
                            grammar_select.append({
                                "source": source, "page_off": page_off,
                                "lines": ls, "q_num": q,
                            })
                else:
                    grammar_select.append({
                        "source": source, "page_off": page_off,
                        "lines": lines
                    })

    return (sentence_arr, sentence_insert, grammar_fix, writing_kor, writing_view,
            vocab_blocks, grammar_select)


def _split_sentence_blocks(paras, source, sentence_styles, output_list,
                           page_qnum="", page_off=-1, lecture=0, olpo_label=""):
    """문장배열 단락들을 {XX} 헤더 기준으로 블록 분리.

    page_qnum: pageOff 기반으로 조회된 문항번호 (같은 페이지의 문장삽입 헤더).
               헤더가 없는 스토리에서 정확한 문항번호로 사용.
    page_off: 스토리 첫 프레임의 페이지 오프셋 (교과서 블록 정렬용).
    lecture: 올포 워크북의 강 번호 (0이면 미지정).
    olpo_label: 공용 올포 파일의 페이지 레이블 (분석/본문N/서술형/논술형).
    """
    # 헤더가 있는지 확인 (모의고사 형식)
    # 딥러닝 워크북: {1}/{2} 같은 단독 정수 마커는 모의고사 문항이 아니라 과 번호 마커이므로
    # has_q_headers 판정에서 제외(=교과서 본문 마커 경로로 우회).
    _is_dl_pre = _is_deeplearning_workbook(source)
    def _is_q_for_paras(t):
        if _is_dl_pre:
            # 단독 정수 {N}/[N] (1~17)은 딥러닝에서 과 마커로 해석
            m = re.match(r"^[\[{](\d+)[\]}]$", t)
            if m and 1 <= int(m.group(1)) <= 17:
                return False
        return _is_question_header(t)
    has_q_headers = any(
        p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
        and _is_q_for_paras(p.get("t", "").strip())
        for p in paras
    )

    if has_q_headers:
        # 모의고사: {20}, {21}, ... 로 분리
        # passage(C1_문장 배열 하단)는 고3 분석편 원문 전용. 고1/고2 모의고사에서는
        # 같은 스타일이 문장삽입 "주어진 문장"으로 쓰이므로 passage로 저장하면
        # 문장배열 섹션 프레임에 하단 프레임 데이터가 섞여 들어간다.
        # → 지문 내에 "하단 문제" 발문 스타일이 있으면 passage 저장을 스킵한다.
        _lower_q_styles = {"하단 문제", "문장 배열 하단 문제"}
        current_items = []
        current_passage = ""
        current_qnum = ""
        current_has_lower_q = False
        for p in paras:
            txt = p.get("t", "").strip()
            style = p.get("s", "")

            if (style in ("[기본 단락]", "[Basic Paragraph]")
                    and _is_question_header(txt)):
                # 이전 블록 저장
                _keep_passage = bool(current_passage) and not current_has_lower_q
                if current_items or _keep_passage:
                    block = {
                        "source": source,
                        "items": current_items,
                        "q_num": current_qnum,
                        "page_off": page_off,
                        "lecture": lecture,
                        "olpo_label": olpo_label,
                    }
                    if _keep_passage:
                        block["passage"] = current_passage
                    output_list.append(block)
                current_items = []
                current_passage = ""
                current_has_lower_q = False
                current_qnum = _extract_question_number(txt)
                continue

            # 고3 분석편 원문 (C1_문장 배열 하단): 한 블록당 1줄
            if style == "C1_문장 배열 하단" and txt:
                current_passage = txt
                continue

            if style in _lower_q_styles:
                current_has_lower_q = True
                continue

            if style in sentence_styles and txt:
                current_items.append(txt)

        # 마지막 블록
        _keep_passage = bool(current_passage) and not current_has_lower_q
        if current_items or _keep_passage:
            block = {
                "source": source,
                "items": current_items,
                "q_num": current_qnum,
                "page_off": page_off,
                "lecture": lecture,
                "olpo_label": olpo_label,
            }
            if _keep_passage:
                block["passage"] = current_passage
            output_list.append(block)
    else:
        # 교과서 워크북: {본문N}/{Further Reading} 헤더로 본문별 블록 분리.
        # 워크북 지문 번호 그대로 사용(FR은 별도 라벨). 균등 분할 금지.
        _is_dl = _is_deeplearning_workbook(source)
        def _match_passage_marker(t):
            m = re.match(r"^[\[{]?(본문\d+(?:[-~]\d+)*|Further\s*Reading|Read\s*More)[\]}]?$", t, re.IGNORECASE)
            if m:
                lab = m.group(1)
                if lab.startswith("본문"):
                    return lab  # "본문3"
                # Read More → "RM" (미래엔 등), Further Reading → "FR" (YBM 등)
                if re.search(r"Read\s*More", lab, re.IGNORECASE):
                    return "RM"
                return "FR"
            # 딥러닝(본문6) 워크북: {1}/{2} 또는 [1]/[2] 같은 단독 정수 마커 → 과 번호로 해석.
            # 본문번호는 6 고정. 인코딩: "본문6@과N"
            if _is_dl:
                m2 = re.match(r"^[\[{](\d+)[\]}]$", t)
                if m2:
                    return "\ubcf8\ubb386@\uacfc" + m2.group(1)
            return None
        has_body_headers = any(
            p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
            and _match_passage_marker(p.get("t", "").strip())
            for p in paras
        )
        if has_body_headers:
            _lower_q_styles = {"하단 문제", "문장 배열 하단 문제"}
            current_items = []
            current_passage = ""
            current_has_lower_q = False
            current_label = ""
            in_block = False
            for p in paras:
                txt = p.get("t", "").strip()
                style = p.get("s", "")
                _marker = None
                if style in ("[기본 단락]", "[Basic Paragraph]"):
                    _marker = _match_passage_marker(txt)
                if _marker is not None:
                    _keep_passage = bool(current_passage) and not current_has_lower_q
                    if in_block and (current_items or _keep_passage):
                        block = {
                            "source": source,
                            "items": current_items,
                            "page_off": page_off,
                            "lecture": lecture,
                            "olpo_label": olpo_label,
                            "passage_label": current_label,
                        }
                        if _keep_passage:
                            block["passage"] = current_passage
                        output_list.append(block)
                    current_items = []
                    current_passage = ""
                    current_has_lower_q = False
                    current_label = _marker
                    in_block = True
                    continue
                if not in_block:
                    continue
                if style == "C1_문장 배열 하단" and txt:
                    current_passage = txt
                    continue
                if style in _lower_q_styles:
                    current_has_lower_q = True
                    continue
                if style in sentence_styles and txt:
                    current_items.append(txt)
            _keep_passage = bool(current_passage) and not current_has_lower_q
            if in_block and (current_items or _keep_passage):
                block = {
                    "source": source,
                    "items": current_items,
                    "page_off": page_off,
                    "lecture": lecture,
                    "olpo_label": olpo_label,
                    "passage_label": current_label,
                }
                if _keep_passage:
                    block["passage"] = current_passage
                output_list.append(block)
            return

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
            block = {"source": source, "items": items, "page_off": page_off,
                     "lecture": lecture, "olpo_label": olpo_label}
            if page_qnum:
                block["q_num"] = page_qnum
            output_list.append(block)


def _split_insert_blocks(paras, source, insert_styles, output_list,
                         page_qnum="", page_off=-1, lecture=0, olpo_label=""):
    """문장삽입 단락들을 {XX} 헤더 기준으로 블록 분리."""
    # 올포 공용 파일: 서술형/논술형/분석이 한 스토리에 묶인 경우 사전 분할
    # (extractor는 스토리 첫 프레임 기준 olpoLabel만 부여하므로 내부 섹션 구분 손실)
    _olpo_section_paras = [
        p for p in paras
        if p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
        and _clean_text(p.get("t", "").strip()) in ("\uc11c\uc220", "\ub17c\uc220", "\ubd84\uc11d")
    ]
    if len(_olpo_section_paras) >= 1 and any(
        _clean_text(p.get("t", "").strip()) in ("\uc11c\uc220", "\ub17c\uc220", "\ubd84\uc11d")
        for p in paras[1:]  # 첫 단락이 아닌 곳에서 구분 단락 발견 → 분할 필요
    ):
        sub_paras = []
        sub_ovr = olpo_label
        for p in paras:
            txt_p = _clean_text(p.get("t", "").strip())
            style_p = p.get("s", "")
            if style_p in ("[기본 단락]", "[Basic Paragraph]") and txt_p in ("\uc11c\uc220", "\ub17c\uc220", "\ubd84\uc11d"):
                if sub_paras:
                    _split_insert_blocks(sub_paras, source, insert_styles, output_list,
                                         page_qnum, page_off, lecture, sub_ovr)
                sub_paras = []
                sub_ovr = "\uc11c\uc220\ud615" if txt_p == "\uc11c\uc220" else (
                    "\ub17c\uc220\ud615" if txt_p == "\ub17c\uc220" else "\ubd84\uc11d"
                )
                continue
            sub_paras.append(p)
        if sub_paras:
            _split_insert_blocks(sub_paras, source, insert_styles, output_list,
                                 page_qnum, page_off, lecture, sub_ovr)
        return

    # 딥러닝 워크북: {1}/{2}는 모의고사 문항이 아니라 과 번호 마커 (교과서 본문 마커 경로로 우회)
    _is_dl_pre_ins = _is_deeplearning_workbook(source)
    def _is_q_for_paras_ins(t):
        if _is_dl_pre_ins:
            m = re.match(r"^[\[{](\d+)[\]}]$", t)
            if m and 1 <= int(m.group(1)) <= 17:
                return False
        return _is_question_header(t)
    has_q_headers = any(
        p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
        and _is_q_for_paras_ins(p.get("t", "").strip())
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
                        "page_off": page_off,
                        "lecture": lecture,
                        "olpo_label": olpo_label,
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
                "page_off": page_off,
                "lecture": lecture,
                "olpo_label": olpo_label,
            })
    else:
        # 교과서: {본문N}/{Further Reading} 마커가 있으면 마커 기준 분할 (워크북 지문 번호 그대로).
        # 마커가 없으면 기존 "아래 주어진" 발문 기준 분할로 폴백.
        _is_dl_ins = _is_deeplearning_workbook(source)
        def _match_passage_marker_ins(t):
            m = re.match(r"^[\[{]?(본문\d+(?:[-~]\d+)*|Further\s*Reading|Read\s*More)[\]}]?$", t, re.IGNORECASE)
            if m:
                lab = m.group(1)
                if lab.startswith("본문"):
                    return lab
                # Read More → "RM", Further Reading → "FR"
                if re.search(r"Read\s*More", lab, re.IGNORECASE):
                    return "RM"
                return "FR"
            if _is_dl_ins:
                m2 = re.match(r"^[\[{](\d+)[\]}]$", t)
                if m2:
                    return "\ubcf8\ubb386@\uacfc" + m2.group(1)
            return None

        has_body_markers = any(
            p.get("s", "") in ("[기본 단락]", "[Basic Paragraph]")
            and _match_passage_marker_ins(_clean_text(p.get("t", "").strip()))
            for p in paras
        )

        if has_body_markers:
            # 마커 기준 블록 분리 — 각 블록 = 마커 사이의 삽입/발문 단락.
            current_paras = []
            current_label = ""
            in_block = False
            for p in paras:
                raw_txt = p.get("t", "").strip()
                txt = _clean_text(raw_txt)
                style = p.get("s", "")
                _marker = _match_passage_marker_ins(txt) if style in ("[기본 단락]", "[Basic Paragraph]") else None
                if _marker is not None:
                    if in_block and current_paras:
                        output_list.append({
                            "source": source,
                            "paras": current_paras,
                            "page_off": page_off,
                            "lecture": lecture,
                            "olpo_label": olpo_label,
                            "passage_label": current_label,
                        })
                    current_paras = []
                    current_label = _marker
                    in_block = True
                    continue
                if not in_block:
                    continue
                if style in insert_styles and txt and not _is_insert_noise(txt):
                    current_paras.append({"style": style, "text": txt})
                elif style in ("[기본 단락]", "[Basic Paragraph]") and txt and not _is_question_header(txt) and not _is_insert_noise(txt):
                    if re.match(r"^\d{1,2}(?:\s*[~\-]\s*\d{1,2})?$", txt):
                        continue
                    current_paras.append({"style": style, "text": txt})
            if in_block and current_paras:
                output_list.append({
                    "source": source,
                    "paras": current_paras,
                    "page_off": page_off,
                    "lecture": lecture,
                    "olpo_label": olpo_label,
                    "passage_label": current_label,
                })
            return

        # 폴백: 마커 없는 교과서 — "아래 주어진" 발문 기준 분리
        all_paras = []
        for p in paras:
            raw_txt = p.get("t", "").strip()
            txt = _clean_text(raw_txt)
            style = p.get("s", "")
            if style in insert_styles and txt and not _is_insert_noise(txt):
                all_paras.append({"style": style, "text": txt})
            elif style in ("[기본 단락]", "[Basic Paragraph]") and txt and not _is_question_header(txt) and not _is_insert_noise(txt):
                # 지문번호 텍스트 필터 (01, 02, 01-02, 03~04 등 짧은 숫자 패턴)
                if re.match(r"^\d{1,2}(?:\s*[~\-]\s*\d{1,2})?$", txt):
                    continue
                all_paras.append({"style": style, "text": txt})

        # "아래 주어진" 발문으로 블록 분리
        blocks = []
        current = []
        for ap in all_paras:
            if ap["text"].startswith("\uc544\ub798") and current:
                # 분리 전 블록에 실질적 내용(insert_styles)이 있는지 확인
                has_real_content = any(p["style"] in insert_styles for p in current)
                if has_real_content:
                    blocks.append(current)
                    current = []
                # 실질 내용이 없으면 (숫자 헤더 등만) 다음 블록에 병합
            current.append(ap)
        if current:
            blocks.append(current)

        for insert_paras in blocks:
            if not insert_paras:
                continue
            block = {"source": source, "paras": insert_paras, "page_off": page_off,
                     "lecture": lecture, "olpo_label": olpo_label}
            if page_qnum:
                block["q_num"] = page_qnum
            output_list.append(block)


def _split_writing_blocks(paras, source, kor_styles, view_styles,
                           writing_kor, writing_view, page_off=-1, lecture=0,
                           olpo_label=""):
    """영작 단락들을 수집. 소스 정보와 문항번호 헤더도 함께 추적.

    lecture: 올포 워크북의 강 번호 (0이면 미지정).
    olpo_label: 공용 올포 파일의 페이지 레이블 (분석/본문N/서술형/논술형).
    """
    # 영작은 [20], {20}, {01~02} 같은 [기본 단락] 헤더로 구분됨
    current_qnum = ""
    current_unit_override = None  # {Unit N emxample M} 헤더에서 Unit 번호 override (lecture 우선)
    for p in paras:
        txt = p.get("t", "").strip()
        if not txt:
            continue
        style = p.get("s", "")

        # [기본 단락] 헤더 추적 — [XX], {XX}, [본문N], [분석], [Gateway] 형식
        if style in ("[기본 단락]", "[Basic Paragraph]"):
            # Gateway 헤더: [Gateway] (고3 수능특강 분석편)
            if re.match(r"^[\[{]Gateway[\]}]$", txt, re.IGNORECASE):
                current_qnum = "Gateway"
                current_unit_override = None
                continue
            # {Unit N emxample M} / {Unit N example M} — 리딩파워 워크북 변형
            m_ue = re.match(r"^[\[{]\s*Unit\s*(\d+)\s+em?xample\s*(\d+)\s*[\]}]$", txt, re.IGNORECASE)
            if m_ue:
                current_qnum = f"Ex{int(m_ue.group(2)):02d}"
                current_unit_override = int(m_ue.group(1))
                continue
            # [Example N] / {Example N} — 리딩파워 Example 헤더
            m_ex = re.match(r"^[\[{]\s*Example\s*(\d+)\s*[\]}]$", txt, re.IGNORECASE)
            if m_ex:
                current_qnum = f"Ex{int(m_ex.group(1)):02d}"
                current_unit_override = None
                continue
            # 숫자 헤더: [20], {01~02}
            m = re.match(r"^[\[{](\d+(?:[~\-]\d+)?)[\]}]$", txt)
            if m:
                current_qnum = m.group(1)
                current_unit_override = None
                continue
            # 본문N 헤더: [본문1], [본문2], 본문1 (대괄호/중괄호 optional)
            m2 = re.match(r"^[\[{]?본문(\d+(?:[-~]\d+)*)[\]}]?$", txt)
            if m2:
                current_qnum = "본문" + m2.group(1)
                current_unit_override = None
                continue
            # Project 헤더: [Project 1-1], [Project 1-2] (워크북 파일명에 Project 포함)
            m_proj = re.match(r"^[\[{]\s*Project\s*(\d+)[\s\-~]+(\d+)\s*[\]}]$", txt, re.IGNORECASE)
            if m_proj:
                current_qnum = f"Project{m_proj.group(1)}-{m_proj.group(2)}"
                current_unit_override = None
                continue
            # 교과서 Further Reading → "FR", Read More → "RM"
            m2b_fr = re.match(r"^[\[{]?Further\s*Reading[\]}]?$", txt, re.IGNORECASE)
            m2b_rm = re.match(r"^[\[{]?Read\s*More[\]}]?$", txt, re.IGNORECASE)
            if m2b_fr:
                current_qnum = "FR"
                current_unit_override = None
                continue
            if m2b_rm:
                current_qnum = "RM"
                current_unit_override = None
                continue
            # 올포 분석 섹션 헤더: [분석]
            m3 = re.match(r"^[\[{](분석)[\]}]$", txt)
            if m3:
                current_qnum = "분석"
                current_unit_override = None
                continue
            # 올포 서술형/논술형 섹션 헤더: [서술형 practice], [논술형 practice]
            m4 = re.match(r"^[\[{](서술형|논술형)(?:\s+\w+)?[\]}]$", txt)
            if m4:
                current_qnum = m4.group(1)
                current_unit_override = None
                continue
            continue

        def _mk_item(_t):
            _it = {"text": _t, "source": source, "q_num": current_qnum,
                   "page_off": page_off, "lecture": lecture, "olpo_label": olpo_label}
            if current_unit_override is not None:
                _it["lecture_override"] = current_unit_override
            return _it

        if style in kor_styles:
            writing_kor.append(_mk_item(txt))
        elif style in view_styles:
            _first_ch = txt[0] if txt else ""
            if "\uAC00" <= _first_ch <= "\uD7A3" and not txt.startswith("("):
                _paren_idx = txt.find("(")
                if _paren_idx > 0:
                    _kor_part = txt[:_paren_idx].rstrip()
                    _view_part = txt[_paren_idx:]
                    writing_kor.append(_mk_item(_kor_part))
                    writing_view.append(_mk_item(_view_part))
                else:
                    writing_kor.append(_mk_item(txt))
            else:
                writing_view.append(_mk_item(txt))


def _writing_q_to_header(scope_text, q_num, lesson_label=None):
    """영작 데이터의 문항번호/섹션번호를 헤더로 변환.

    교과서 본문: "본문1" → "1과 본문1" (lesson_label로 과 번호 결정)
    교과서 {01~02}: SL/기타 번호 → "SL 본문1~2" or "X과 본문N"
    모의고사: "20" → "251020" (YYMMQQ)
    """
    scope = _nfc(scope_text) if scope_text else ""

    # scope 기반 라벨 추출 (lesson_label이 없을 때 폴백)
    # 교과서: "1과", "3과", "SL" / TED: "TED1" / 모의고사: 건드리지 않음
    def _scope_label():
        if not scope:
            return None
        # "SL" 단독
        if "SL" in scope and not re.search(r"\d+\s*\uacfc", scope):
            return "SL"
        # "교과서N과" / "동아박3과" / "미래엔김3과"
        m_tb = re.search(r"(\d+)\s*\uacfc", scope)
        if m_tb:
            return f"{m_tb.group(1)}\uacfc"
        # TED 외부지문
        if "TED" in scope:
            return "TED1"
        if "\uc678\ubd80\uc9c0\ubb38" in scope or "\uc678\ubd80" in scope:
            return "\uc678\ubd80\uc9c0\ubb38"
        return None

    # Project 워크북: "Project1-1" → "교과서Project1 본문1"
    m_proj_qn = re.match(r"^Project(\d+)-(\d+)$", q_num)
    if m_proj_qn:
        return f"교과서Project{m_proj_qn.group(1)} 본문{m_proj_qn.group(2)}"

    # "본문N" 형태 (교과서 워크북) — lesson_label 사용
    if q_num.startswith("본문"):
        num = q_num.replace("본문", "")
        eff_label = lesson_label or _scope_label()
        if eff_label:
            if eff_label.startswith("TED"):
                return f"{eff_label} 본문{num}"
            if eff_label == "외부지문":
                return f"외부지문 본문{num}"
            if eff_label == "SL":
                return f"교과서SL 본문{num}"
            if eff_label.startswith("Project"):
                return f"교과서{eff_label} 본문{num}"
            return f"교과서{eff_label} 본문{num}"
        return f"본문{num}"

    # "FR"/"RM" (교과서 Further Reading / Read More) — lesson_label 사용
    if q_num in ("FR", "RM"):
        eff_label = lesson_label or _scope_label()
        suffix = q_num  # FR or RM 그대로 유지
        if eff_label:
            if eff_label == "SL":
                return f"교과서SL {suffix}"
            if eff_label == "외부지문":
                return f"외부지문 {suffix}"
            if not eff_label.startswith("TED"):
                return f"교과서{eff_label} {suffix}"
        return suffix

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

    # 리딩파워 (영작 등에서 블록 순번만 있을 때 강별 균등 배분)
    if "\ub9ac\ub529\ud30c\uc6cc" in scope or "Reading" in scope:
        is_ex = "Example" in scope
        inner = scope
        for tok in ("\ub9ac\ub529\ud30c\uc6cc", "Reading", "\uac15"):
            inner = inner.replace(tok, "")
        inner = re.sub(r"Example", "", inner, flags=re.IGNORECASE).strip()
        lecs = []
        for part in inner.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-")
                    lecs.extend(range(int(a), int(b) + 1))
                except Exception:
                    pass
            elif part.isdigit():
                lecs.append(int(part))
        if lecs:
            bpl = 4 if is_ex else 5  # Example: 4/강, non-Example: 4문제+1 merged Example = 5
            total = len(lecs) * bpl
            if block_num <= total:
                lec_idx = (block_num - 1) // bpl
                local = (block_num - 1) % bpl + 1
                L = lecs[lec_idx]
                if is_ex:
                    return f"\ub9ac\ub529\ud30c\uc6cc {L}\uac15 Ex{str(local).zfill(2)}"
                return f"\ub9ac\ub529\ud30c\uc6cc {L}\uac15 {str(local).zfill(2)}"
        return f"\ub9ac\ub529\ud30c\uc6cc \ube14\ub85d{block_num}"

    # 마더텅: scope에 번호 있으면 보존 ("마더텅3" → "마더텅3 본문N")
    if "마더텅" in scope:
        m_mt = re.search(r"마더텅\s*(\d+)", scope)
        if m_mt:
            return f"마더텅{m_mt.group(1)} 본문{block_num}"
        return f"마더텅 본문{block_num}"

    # 외부지문: scope에 "TED" 명시된 학교만 "TEDN 본문M"(기본 TED1).
    # 그 외 일반 외부지문(상일2 등)은 "외부지문 본문M".
    if "TED" in scope:
        return f"TED1 본문{block_num}"
    if "외부지문" in scope or "외부" in scope:
        return f"외부지문 본문{block_num}"

    # 기본
    return f"지문 {block_num}"


def _is_rp_source(src):
    """리딩파워 워크북 소스 여부."""
    s = _nfc(src or "")
    return ("\ub9ac\ub529\ud30c\uc6cc" in s) or ("Reading" in s)


def _canonical_order_key(header, source=""):
    """전체 섹션 순서 통일 키:
    0: 교과서 (과, 본문번호)
    0.7: TED 외부지문 (TEDN, 본문번호)
    1: 리딩파워 non-Example 워크북 (강, ex_flag, sub)  -- 1,2,3,5,6강 및 9,10,11강 non-Ex
    1.5: 리딩파워 Example 워크북 (강, ex_flag, sub)    -- 9,10,11강 Example만
    2: 모의고사 YYMMQQ
    3: 기타
    """
    h = _nfc(header or "").strip()
    src = _nfc(source or "")
    # 교과서
    m_tb = re.match(r'^\uad50\uacfc\uc11c(\d+)\uacfc\s+\ubcf8\ubb38(\d+)(?:-(\d+))?', h)
    if m_tb:
        return (0, int(m_tb.group(1)), int(m_tb.group(2)), int(m_tb.group(3) or 0))
    m_tb_sl = re.match(r'^\uad50\uacfc\uc11cSL\s+\ubcf8\ubb38(\d+)', h)
    if m_tb_sl:
        return (0, 999, int(m_tb_sl.group(1)), 0)
    m_tb_proj = re.match(r'^\uad50\uacfc\uc11cProject(\d+)\s+\ubcf8\ubb38(\d+)', h)
    if m_tb_proj:
        return (0, 500 + int(m_tb_proj.group(1)), int(m_tb_proj.group(2)), 0)
    m_tb_fr = re.match(r'^\uad50\uacfc\uc11c(\d+)\uacfc\s+(?:FR|RM)', h)
    if m_tb_fr:
        return (0, int(m_tb_fr.group(1)), 999, 0)
    # TED 외부지문 ("TED1 본문3", "TED2 본문1" 등)
    m_ted = re.match(r'^TED(\d+)\s+\ubcf8\ubb38(\d+)', h)
    if m_ted:
        return (0.7, int(m_ted.group(1)), int(m_ted.group(2)), 0)
    # \uc77c\ubc18 \uc678\ubd80\uc9c0\ubb38 ("\uc678\ubd80\uc9c0\ubb38 \ubcf8\ubb383") \u2014 TED\uc640 \ub3d9\uc77c tier(0.7)
    m_ext = re.match(r'^\uc678\ubd80\uc9c0\ubb38\s+\ubcf8\ubb38(\d+)', h)
    if m_ext:
        return (0.7, 1, int(m_ext.group(1)), 0)
    # 리딩파워 — 강별로 묶어서 같은 강 내에서 Ex 먼저, 일반 문제 뒤
    # (파일명 Example 여부와 무관하게 헤더의 "Ex" 표기만 기준으로 정렬 — 워크북 파일명/내용이 반대인 경우 대응)
    m_rp = re.match(r'^\ub9ac\ub529\ud30c\uc6cc\s+(\d+)\uac15\s+(?:Ex(\d+)|(\d+))', h)
    if m_rp:
        lec = int(m_rp.group(1))
        is_ex = m_rp.group(2) is not None
        sub = int(m_rp.group(2) or m_rp.group(3) or 0)
        return (1, lec, 0 if is_ex else 1, sub)
    # 모의고사 YYMMQQ
    m_mock = re.match(r'^(\d{6})(?:~\d+)?', h)
    if m_mock:
        return (2, int(m_mock.group(1)), 0, 0)
    # 고3 분석편: "N강 NN" 또는 "N강 NN~NN" (예: "3강 01", "19강 05~06")
    # Why: 강동3 등 고3 학교에서 영작/어법 헤더가 lexical 정렬돼 11강이 3강 앞으로 가는 문제.
    # How to apply: 강 번호와 첫 문항 번호로 정렬. 모의고사(2)와 기타(3) 사이.
    m_g3 = re.match(r'^(\d+)\uac15\s+(\d+)', h)
    if m_g3:
        return (2.5, int(m_g3.group(1)), int(m_g3.group(2)), h)
    # 기타 (올포 등)
    m_olpo = re.match(r'^\uc62c\ud3ec\s+(\d+)\uac15', h)
    if m_olpo:
        return (1.2, int(m_olpo.group(1)), 0, h)
    return (3, 9999, 0, h)


def _rp_header(src, lecture, counter_val):
    """리딩파워 블록 헤더 생성.

    워크북 파일명에 "Example" 포함 → "리딩파워 N강 ExMM"
    아니면 → "리딩파워 N강 MM"
    MM은 2-digit zero-pad.
    """
    sub = str(counter_val).zfill(2)
    s = _nfc(src or "")
    if "Example" in s:
        return f"\ub9ac\ub529\ud30c\uc6cc {lecture}\uac15 Ex{sub}"
    return f"\ub9ac\ub529\ud30c\uc6cc {lecture}\uac15 {sub}"


def _rp_content_to_label(block, rp_sheet_data):
    """리딩파워 블록 내용을 시트 데이터와 매칭해 (lec, is_example, num) 반환.

    시트 키: "N-ExampleM" → (N, True, M), "N-M" → (N, False, M)
    매칭 실패 시 None.
    """
    if not rp_sheet_data:
        return None
    items = block.get("items", [])
    passage = block.get("passage", "")
    # 매칭 후보 텍스트: passage 우선, 없으면 items[0]
    text_candidates = []
    if passage:
        text_candidates.append(passage)
    if items:
        text_candidates.append(items[0])
        # items[0]가 (A)로 시작하면 다음 것도 시도
        if items[0].startswith("(") and len(items) > 1:
            text_candidates.append(items[1])

    def _norm(s):
        s = re.sub(r"[\[\]()]+", "", s or "")
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    for cand in text_candidates:
        cand_norm = _norm(cand)
        if len(cand_norm) < 25:
            continue
        cand_prefix = cand_norm[:50]
        # 시트 텍스트와 매칭 (각 방향 prefix 비교)
        for key, sheet_text in rp_sheet_data:
            sheet_norm = _norm(sheet_text)
            if not sheet_norm:
                continue
            if cand_prefix in sheet_norm[:300] or sheet_norm[:50] in cand_norm[:300]:
                m = re.match(r"^(\d+)-(?:Example\s*(\d+)|(\d+))$", key, re.IGNORECASE)
                if m:
                    lec = int(m.group(1))
                    if m.group(2):
                        return (lec, True, int(m.group(2)))
                    else:
                        return (lec, False, int(m.group(3)))
    return None


def _rp_writing_to_label(choices_text, rp_sheet_data, korean_text=""):
    """영작 choices(단어 배열)/한국어를 시트 원문과 단어 단위로 매칭해 (lec, is_example, num) 반환.

    choices는 "( word1 / word2 / word3 ), non-paren-text"처럼 슬래시 단어 배열이 많아
    _rp_content_to_label의 substring prefix 매칭이 실패함. 5자 이상 단어들의 교집합 비율로
    가장 잘 매칭되는 시트 행을 선택.
    """
    if not rp_sheet_data or not choices_text:
        return None
    # 슬래시/괄호/하이픈을 공백으로, 소문자화, 영어 단어 추출 (5자 이상 + 고유성)
    _norm_text = re.sub(r"[\[\]()\-/,.:;!?]+", " ", (choices_text or "").lower())
    cand_words = set(w for w in re.findall(r'[a-z]+', _norm_text) if len(w) >= 5)
    if len(cand_words) < 4:
        return None
    best_match = None
    best_ratio = 0.0
    for key, sheet_text in rp_sheet_data:
        _sh_norm = re.sub(r"[\[\]()\-/,.:;!?]+", " ", (sheet_text or "").lower())
        sheet_words = set(w for w in re.findall(r'[a-z]+', _sh_norm) if len(w) >= 5)
        if not sheet_words:
            continue
        inter = cand_words & sheet_words
        if len(inter) < 3:
            continue
        ratio = len(inter) / len(cand_words)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = key
    # 50% 이상 단어 매칭이면 신뢰 가능
    if best_match and best_ratio >= 0.5:
        m = re.match(r"^(\d+)-(?:Example\s*(\d+)|(\d+))$", best_match, re.IGNORECASE)
        if m:
            lec = int(m.group(1))
            if m.group(2):
                return (lec, True, int(m.group(2)))
            else:
                return (lec, False, int(m.group(3)))
    return None


def _build_rp_seq_map(src, rp_lecture_counts):
    """리딩파워 워크북의 블록 순번(1..N) → (강, 지문번호, is_example) 매핑 생성.

    Example 워크북 (파일명에 "Example"): 강별 rp_lecture_counts[L]개 Ex 지문
       {1:(9,1,True),...,4:(9,4,True),5:(10,1,True),...,9:(11,1,True),10:(11,2,True)}

    Non-Example: 강별 2 Example + rp_lecture_counts[L] 문제
       {1:(L,1,True),2:(L,2,True),3:(L,1,False),4:(L,2,False),...}
       즉 {1:(1,1,True)=Ex01, 2:(1,2,True)=Ex02, 3:(1,1,False)=01, 4:(1,2,False)=02,
           5:(1,3,False)=03, 6:(1,4,False)=04, 7:(2,1,True)=Ex01, ...}

    Returns: (cum_map, is_example_workbook)
    rp_lecture_counts에 없는 강은 fallback 4개로 가정.
    """
    s = _nfc(src or "")
    is_example_wb = "Example" in s
    m = re.search(r"\(([^)]+)\)", s)
    if not m:
        return {}, is_example_wb
    inner = m.group(1)
    inner = inner.replace("\ub9ac\ub529\ud30c\uc6cc", "").replace("Reading", "")
    inner = inner.replace("\uac15", "")
    inner = re.sub(r"Example", "", inner, flags=re.IGNORECASE).strip()
    lectures = []
    for part in inner.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-")
                lectures.extend(range(int(a), int(b) + 1))
            except Exception:
                pass
        elif part.isdigit():
            lectures.append(int(part))
    cum_map = {}
    cum = 0
    for L in lectures:
        base = (rp_lecture_counts or {}).get(L, 4)
        if is_example_wb:
            # Example 워크북: rp_counts[L]개 Ex 지문만
            for i in range(1, base + 1):
                cum += 1
                cum_map[cum] = (L, i, True)
        else:
            # Non-Example: 2 Ex 먼저, 그다음 base 문제
            for i in range(1, 3):  # Example 1, 2
                cum += 1
                cum_map[cum] = (L, i, True)
            for i in range(1, base + 1):  # 문제 1..base
                cum += 1
                cum_map[cum] = (L, i, False)
    return cum_map, is_example_wb


def _build_rp_example_map(src, rp_lecture_counts):
    """하위 호환: _build_rp_seq_map의 cum_map만 반환 (is_example 생략)."""
    cum_map, _ = _build_rp_seq_map(src, rp_lecture_counts)
    return {k: (v[0], v[1]) for k, v in cum_map.items()}


def _sort_blocks(blocks):
    """블록을 source 파일명 → 페이지 순서로 정렬.

    일반 워크북: source 파일명의 워크북 번호(01, 02, 03...) → page_off 순.
    올포(공용 올림포스독해기본): lecture 번호 → page_off 순 (워크북 번호 무시).
    """
    def sort_key(item):
        idx, block = item
        src = _nfc(block.get("source", ""))
        page_off = block.get("page_off", -1)
        secondary = page_off if page_off >= 0 else (10000 + idx)
        # 올포는 lecture 기반 정렬 (워크북 번호 정보가 공용 파일에 없음)
        if "올림포스독해기본" in src or "올포" in src:
            lec = block.get("lecture", 0) or 999
            return (500, lec, secondary)
        m = re.search(r"워크북\s*(\d+)", src)
        wb_num = int(m.group(1)) if m else 999
        return (wb_num, secondary, 0)

    indexed = list(enumerate(blocks))
    indexed.sort(key=sort_key)
    return [block for _, block in indexed]


def _is_in_scope(header, scope_exams):
    """YYMMQQ 헤더가 시험범위에 포함되는지 확인."""
    if not scope_exams:
        return True  # scope 없으면 전부 포함
    if (header.startswith("교과서") or header.startswith("올포") or
            header.startswith("마더텅") or header.startswith("SL") or
            header.startswith("TED") or header.startswith("외부지문") or
            re.match(r"^\d{1,2}과\s", header)):
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


def _passes_textbook_rm_filter(header, textbook_rm_lessons):
    """'교과서N과 RM/FR' 헤더가 RM/FR 허용 과 set 필터를 통과하는지.

    textbook_rm_lessons: 시험범위 시트의 "(N과는 Read More도 포함)" 표기에서 추출한 set.
        - None: 명시 없음 → 전체 허용 (기존 동작)
        - set: 해당 과의 RM/FR만 허용. 다른 과의 RM/FR은 제외.
    """
    if textbook_rm_lessons is None:
        return True
    h = (header or "").strip()
    # 교과서N과 FR/RM 만 검사. 본문이나 비교과서 헤더는 통과.
    m = re.match(r'^교과서(\d+|SL)과?\s+(?:FR|RM)$', h)
    if not m:
        return True
    lesson = m.group(1)
    return lesson in textbook_rm_lessons


def _passes_textbook_limit(header, textbook_limits):
    """'교과서N과 본문M' 헤더가 textbook_limits 제한을 통과하는지.

    textbook_limits: {과번호(문자열): 최대본문번호(int)} — 없는 과는 제한 없음.
    교과서가 아닌 헤더(모의고사/TED/올포 등)는 항상 통과.
    """
    if not textbook_limits:
        return True
    h = (header or "").strip()
    # 교과서N과 본문M
    m = re.match(r'^\uad50\uacfc\uc11c(\d+)\uacfc\s+\ubcf8\ubb38(\d+)', h)
    if m:
        lesson = m.group(1)
        body = int(m.group(2))
        max_body = textbook_limits.get(lesson)
        if max_body is not None and body > max_body:
            return False
        return True
    # 교과서N과 FR — 제한 과에 한해 FR도 제외(본문을 줄이는 설정이므로 FR도 숨김)
    m_fr = re.match(r'^\uad50\uacfc\uc11c(\d+)\uacfc\s+(?:FR|RM)', h)
    if m_fr:
        lesson = m_fr.group(1)
        if lesson in textbook_limits:
            return False
        return True
    # 교과서SL
    m_sl = re.match(r'^\uad50\uacfc\uc11cSL(?:\s+\ubcf8\ubb38(\d+))?', h)
    if m_sl:
        body_s = m_sl.group(1)
        max_body = textbook_limits.get("SL")
        if body_s and max_body is not None and int(body_s) > max_body:
            return False
        return True
    return True


def _parse_olpo_lectures(scope_text):
    """올포 scope에서 강 리스트 파싱. "올포1-4강" → [1,2,3,4], "올포5,8,9강" → [5,8,9]."""
    s = scope_text.replace("올포", "").replace("강", "").strip()
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


def _reassign_olpo_lectures(blocks, page_off_key="page_off"):
    """올포 블록 중 lecture=0(미할당)인 블록만 page_off 기반 강 그룹핑으로 재할당.

    extractor의 {N강} 마커가 정확한 경우(예: 공용 올림포스독해기본)는 이미 lecture가 할당돼 있어 건드리지 않음.
    학교 워크북처럼 {N강} 마커 위치가 부정확한 경우에만 파일명 강 리스트와 순서대로 매핑.
    """
    from collections import defaultdict
    by_src = defaultdict(list)
    for b in blocks:
        src = _nfc(b.get("source", ""))
        if "올포" not in src and "올림포스독해기본" not in src:
            continue
        by_src[src].append(b)

    for src, src_blocks in by_src.items():
        # 이미 모든 블록에 lecture가 할당되어 있으면 extractor 결과 신뢰 (건드리지 않음)
        if all(b.get("lecture", 0) > 0 for b in src_blocks):
            continue

        m = re.search(r"\(([^)]+)\)", src)
        if not m:
            continue
        scope = m.group(1)
        # 공용 파일 (1-5강, 8-9강 등): scope에 "올포" 없어도 허용
        if "올포" not in scope and "올림포스독해기본" not in src:
            continue
        lectures = _parse_olpo_lectures(scope)
        if not lectures:
            continue

        # lecture=0인 블록만 page_off 순 정렬 후 그룹핑
        unassigned = [b for b in src_blocks if b.get("lecture", 0) == 0]
        if not unassigned:
            continue
        unassigned.sort(key=lambda x: x.get(page_off_key, -1))

        # 연속 페이지 그룹핑 (gap <= 2: 같은 강)
        groups = []
        current = [unassigned[0]]
        prev_page = unassigned[0].get(page_off_key, -1)
        for b in unassigned[1:]:
            cur_page = b.get(page_off_key, -1)
            if cur_page < 0 or prev_page < 0 or cur_page - prev_page > 2:
                groups.append(current)
                current = [b]
            else:
                current.append(b)
            if cur_page >= 0:
                prev_page = cur_page
        groups.append(current)

        # 이미 할당된 lecture 목록 추출 (재사용 방지)
        used_lectures = {b.get("lecture", 0) for b in src_blocks if b.get("lecture", 0) > 0}
        available_lectures = [l for l in lectures if l not in used_lectures]

        # 그룹별 lecture 할당
        for gi, grp in enumerate(groups):
            if gi >= len(available_lectures):
                break
            for b in grp:
                b["lecture"] = available_lectures[gi]


def _build_vol1(sentence_blocks, sentence_insert_blocks, vocab_left_text, vocab_right_text,
                scope_exams=None, lesson_block_counts=None, sl_section_headers=None,
                allowed_olpo_lectures=None, grade=None, rp_lecture_counts=None,
                rp_sheet_data=None, textbook_limits=None, olpo_lecture_map=None,
                textbook_rm_lessons=None):
    """Vol1 데이터 구성.

    lesson_block_counts: 어법수정 Word에서 감지한 과별 본문 수.
        예: {"1": 6, "2": 6} → 1과 6본문, 2과 6본문.
        이것이 있으면 페이지 갭 감지보다 우선 사용 (ground truth).
    sl_section_headers: SL 블록의 실제 섹션 헤더 (어법수정 Word 기준).
        예: ["교과서SL 본문1~2", "교과서SL 본문3", ...]
    """
    vol1 = {}

    # 올포 블록의 lecture 할당:
    # 1순위: exam_code(YYMMQQ) → xlsx 매핑 (학교 올포 워크북 정확 매핑)
    # 2순위: page_off 기반 그룹핑 (공용 올포 파일 폴백)
    def _assign_lecture_from_exam_code(blocks):
        if not olpo_lecture_map:
            return
        for b in blocks:
            if b.get("lecture", 0) > 0:
                continue
            ec = b.get("exam_code", "") or ""
            ec = str(ec).strip()
            if not ec:
                continue
            info = olpo_lecture_map.get(ec)
            if info:
                b["lecture"] = info[0]  # (lecture_int, body_label)
    if sentence_blocks:
        _assign_lecture_from_exam_code(sentence_blocks)
        _reassign_olpo_lectures(sentence_blocks)
    if sentence_insert_blocks:
        _assign_lecture_from_exam_code(sentence_insert_blocks)
        _reassign_olpo_lectures(sentence_insert_blocks)

    # 공용 올포 파일에서 추출된 블록 중 허용 강 범위 외는 제외
    if allowed_olpo_lectures:
        def _is_olpo_src(b):
            src = _nfc(b.get("source", ""))
            return "올포" in src or "올림포스독해기본" in src
        sentence_blocks = [
            b for b in sentence_blocks
            if not _is_olpo_src(b) or b.get("lecture", 0) in allowed_olpo_lectures
        ]
        sentence_insert_blocks = [
            b for b in sentence_insert_blocks
            if not _is_olpo_src(b) or b.get("lecture", 0) in allowed_olpo_lectures
        ]

    # 리딩파워 워크북은 문장삽입 섹션이 없음 — 필터는 dedup 후(sync 전)에 적용
    # (여기서 미리 제거하면 sentence_insert_blocks가 빈 상태로 sync 로직 스킵됨)

    # 마더텅 워크북의 "메인 페이지" → seq 매핑을 미리 계산.
    # xlsx에 N개 지문이 나열되어 있고, 각 지문은 워크북에 insert 질문(발문 O) 형태로
    # 존재한다. sentence-only 페이지는 같은 지문의 추가 문제(주제 판단 등 인접 페이지)
    # 이므로 insert 페이지 목록만으로 seq를 부여하고, sentence-only 페이지는 가장 가까운
    # insert 페이지의 seq를 공유한다.
    _mt_page_seq = {}  # {(src, page_off): seq(1..N)}
    _mt_insert_pages = {}  # {src: sorted[page_off]} (xlsx와 정렬되는 원본)
    for _mb in (sentence_insert_blocks or []):
        _msrc = _nfc(_mb.get("source", ""))
        if "\ub9c8\ub354\ud145" not in _msrc:
            continue
        _po = _mb.get("page_off", -1)
        if _po >= 0:
            _mt_insert_pages.setdefault(_msrc, set()).add(_po)
    for _msrc, _pages in _mt_insert_pages.items():
        _sorted = sorted(_pages)
        for _idx, _po in enumerate(_sorted, start=1):
            _mt_page_seq[(_msrc, _po)] = _idx
    # sentence-only 페이지 → 가장 가까운 insert 페이지의 seq에 붙임
    for _mb in (sentence_blocks or []):
        _msrc = _nfc(_mb.get("source", ""))
        if "\ub9c8\ub354\ud145" not in _msrc:
            continue
        _po = _mb.get("page_off", -1)
        if _po < 0 or (_msrc, _po) in _mt_page_seq:
            continue
        _ipages = sorted(_mt_insert_pages.get(_msrc, set()))
        if not _ipages:
            continue
        # 인접 insert 페이지 중 가장 가까운 것 선택 (거리 동점 시 작은 쪽)
        _nearest = min(_ipages, key=lambda _ip: (abs(_ip - _po), _ip))
        if abs(_nearest - _po) <= 6:  # 같은 지문의 후속 문제로 볼 수 있는 범위
            _mt_page_seq[(_msrc, _po)] = _mt_page_seq[(_msrc, _nearest)]

    # 문장배열 — 워크북 번호 + q_num 순으로 정렬
    if sentence_blocks:
        sentence_blocks = _sort_blocks(sentence_blocks)

        # pageQNum 누락 보완: 모의고사 워크북(scope="YY년MM월")에서 q_num이 비어 있으면
        # source별 page_off 오름차순 + 해당 시험범위 numbers 오름차순으로 1:1 매핑.
        # (24-3 워크북처럼 extractor가 pageQNum을 못 뽑은 경우 대비)
        if scope_exams:
            _fill_by_src = {}
            for _b in sentence_blocks:
                if _b.get("q_num"):
                    continue
                _src = _nfc(_b.get("source", ""))
                _sm = re.search(r"\(([^)]+)\)", _src)
                _sc = _sm.group(1) if _sm else ""
                _ym = re.search(r"(\d{2})\ub144\s*(\d{1,2})\uc6d4", _sc)
                if not _ym:
                    continue  # 모의고사 scope 아님 (교과서/올포 등 제외)
                _fill_by_src.setdefault(_src, []).append(_b)
            for _src, _blocks_to_fill in _fill_by_src.items():
                _sm = re.search(r"\(([^)]+)\)", _src)
                _sc = _sm.group(1) if _sm else ""
                _ym = re.search(r"(\d{2})\ub144\s*(\d{1,2})\uc6d4", _sc)
                _yy, _mm = _ym.group(1), _ym.group(2).zfill(2)
                _matching = None
                for _ex in scope_exams:
                    _ey = str(_ex.get("year", ""))
                    _em = str(_ex.get("month", "")).zfill(2)
                    if _ey == _yy and _em == _mm:
                        _matching = _ex
                        break
                if not _matching:
                    continue
                _nums = sorted(int(n) for n in _matching.get("numbers", []) if isinstance(n, int) or (isinstance(n, str) and n.isdigit()))
                _blocks_to_fill.sort(key=lambda _x: _x.get("page_off", 10**9))
                for _b, _n in zip(_blocks_to_fill, _nums):
                    _b["q_num"] = str(_n)

        # 교과서 블록: page_off 갭 기반 과 경계 감지
        # source별 교과서 블록의 page_off를 수집
        # q_num이 있어도 교과서 섹션번호(< 18)이면 교과서 블록으로 취급
        _tb_page_map = {}  # src -> [(block_idx_in_src, page_off), ...]
        _tb_src_order = []  # 교과서 블록만 순서대로
        _src_block_idx = {}  # src -> 현재 인덱스
        for _bi, _ab in enumerate(sentence_blocks):
            _asrc = _nfc(_ab.get("source", ""))
            _q = _ab.get("q_num", "")
            if _q:
                # 모의고사 문항번호(>= 18)는 교과서 맵에서 제외
                _qm = re.match(r"(\d+)", _q)
                if _qm and int(_qm.group(1)) >= 18:
                    continue
            if _asrc not in _tb_page_map:
                _tb_page_map[_asrc] = []
                _src_block_idx[_asrc] = 0
            po = _ab.get("page_off", -1)
            _tb_page_map[_asrc].append((_src_block_idx[_asrc], po))
            _src_block_idx[_asrc] += 1

        # source별 과 경계 맵 생성: {src: {block_idx: "교과서N과 본문M"}}
        # 핵심: 실제 추출된 블록 수를 기준으로 균등 분할. lesson_block_counts는 비율 참고용.
        _tb_lesson_map = {}
        for _src, _blocks_info in _tb_page_map.items():
            _sm = re.search(r"\(([^)]+)\)", _src)
            _scope_txt = _sm.group(1) if _sm else ""
            _lm = re.search(r"(\d+(?:,\d+)*)\s*과", _scope_txt)
            # Project 워크북 (예: 워크북02(YBM(김)Project1)) — 과 매칭 실패 시 src에서 직접 추출
            _proj_m = re.search(r"Project\s*(\d+)", _src, re.IGNORECASE) if not _lm else None
            if _proj_m:
                _proj_label = f"Project{_proj_m.group(1)}"
                _tb_lesson_map[_src] = {}
                for _idx, _po in _blocks_info:
                    _tb_lesson_map[_src][_idx] = f"교과서{_proj_label} 본문{_idx + 1}"
                continue
            if not _lm:
                continue
            _lessons = [l.strip() for l in _lm.group(1).split(",")]
            _has_sl = "SL" in _scope_txt
            _all_lessons = list(_lessons)
            if _has_sl:
                _all_lessons.append("SL")

            n_blocks = len(_blocks_info)
            if len(_all_lessons) <= 1:
                _tb_lesson_map[_src] = {}
                for _idx, _po in _blocks_info:
                    if _all_lessons[0] == "SL":
                        _sl_hdr = sl_section_headers[_idx] if sl_section_headers and _idx < len(sl_section_headers) else f"교과서SL 본문{_idx + 1}"
                        _tb_lesson_map[_src][_idx] = _sl_hdr
                    else:
                        _tb_lesson_map[_src][_idx] = f"교과서{_all_lessons[0]}과 본문{_idx + 1}"
                continue

            # 실제 블록 수를 과 수로 균등 분할
            _bpl = max(1, n_blocks // len(_all_lessons))
            _tb_lesson_map[_src] = {}
            _offset = 0
            for _li, _lesson in enumerate(_all_lessons):
                # 마지막 과는 나머지 블록 전부 할당
                if _li == len(_all_lessons) - 1:
                    _count = n_blocks - _offset
                else:
                    _count = _bpl
                for _bi in range(_count):
                    _global_idx = _offset + _bi
                    if _global_idx >= n_blocks:
                        break
                    if _lesson == "SL":
                        # SL: sl_section_headers에서 실제 헤더 사용
                        if sl_section_headers and _bi < len(sl_section_headers):
                            _tb_lesson_map[_src][_global_idx] = sl_section_headers[_bi]
                        else:
                            _tb_lesson_map[_src][_global_idx] = f"교과서SL 본문{_bi + 1}"
                    else:
                        _tb_lesson_map[_src][_global_idx] = f"교과서{_lesson}과 본문{_bi + 1}"
                _offset += _count

        # passage_label 기반 매핑: src+page_off(스토리) → 과 번호.
        # 각 스토리가 하나의 과에 대응. page_off 오름차순으로 scope 과 순서와 매칭.
        # 블록은 워크북에 적힌 {본문N}/{Further Reading} 마커로 헤더 부여 (균등 분할 금지).
        _tb_story_lesson = {}  # src -> {page_off: lesson_label}
        for _src, _blocks_info in _tb_page_map.items():
            _sm = re.search(r"\(([^)]+)\)", _src)
            _scope_txt = _sm.group(1) if _sm else ""
            _lm = re.search(r"(\d+(?:,\d+)*)\s*과", _scope_txt)
            # Project 워크북 처리
            _proj_m = re.search(r"Project\s*(\d+)", _src, re.IGNORECASE) if not _lm else None
            if _proj_m:
                _proj_label = f"Project{_proj_m.group(1)}"
                _unique_pos = sorted({_po for _, _po in _blocks_info if _po >= 0})
                _m = {}
                for _po in _unique_pos:
                    _m[_po] = _proj_label
                _tb_story_lesson[_src] = _m
                continue
            if not _lm:
                continue
            _lessons = [l.strip() for l in _lm.group(1).split(",")]
            _has_sl = "SL" in _scope_txt
            _all_lessons = list(_lessons)
            if _has_sl:
                _all_lessons.append("SL")
            _unique_pos = sorted({_po for _, _po in _blocks_info if _po >= 0})
            _m = {}
            for _si, _po in enumerate(_unique_pos):
                _m[_po] = _all_lessons[_si] if _si < len(_all_lessons) else _all_lessons[-1]
            _tb_story_lesson[_src] = _m

        def _tb_header_from_label(_src, _page_off, _label):
            """passage_label 기반 교과서 헤더. 실패 시 None."""
            if not _label:
                return None
            # 딥러닝 인코딩: "본문N@과M" → 과 번호가 라벨에 직접 포함됨 (page_off 매핑 불필요)
            # 딥러닝 워크북은 본문 슬롯에 매핑되지만 헤더 라벨은 "교과서{M}과 딥러닝"으로 출력.
            _dl_m = re.match(r"^(본문\d+)@과(\d+)$", _label)
            if _dl_m:
                return f"교과서{_dl_m.group(2)}과 딥러닝"
            _lesson_map = _tb_story_lesson.get(_src)
            if not _lesson_map:
                return None
            _lesson = _lesson_map.get(_page_off)
            if _lesson is None:
                return None
            if _label in ("FR", "RM"):
                _suf = _label
                if _lesson == "SL":
                    return f"교과서SL {_suf}"
                if _lesson.startswith("Project"):
                    return f"교과서{_lesson} {_suf}"
                return f"교과서{_lesson}과 {_suf}"
            if _label.startswith("본문"):
                if _lesson == "SL":
                    return f"교과서SL {_label}"
                if _lesson.startswith("Project"):
                    return f"교과서{_lesson} {_label}"
                return f"교과서{_lesson}과 {_label}"
            return None

        all_blocks = []
        source_counts = {}
        source_mt_total = {}  # 마더텅 워크북 전체 지문 순번 (YYMMQQ 매핑 조회용)
        # 복합 scope용: source별 exam_index + 이전 q_num 추적
        source_exam_idx = {}  # src -> exam_index
        source_prev_qnum = {}  # src -> 이전 q_num 첫 번째 숫자
        _tb_counters = {}  # src -> 교과서 블록 인덱스 카운터
        _lec_counters = {}  # (src, lecture) -> 강별 본문 카운터 (올포 폴백)
        _rp_ex_map_cache = {}  # src -> {cum: (lec, ex_num)} Example 워크북용
        _rp_ex_order_counter = {}  # src -> 순번 카운터 (Example 워크북 블록 순서)
        _used_rp_headers_per_src = {}  # src -> set(이미 매핑된 리딩파워 헤더) — 한 Story에 여러 강 혼재 시 중복 회피
        for block in sentence_blocks:
            src = _nfc(block.get("source", ""))
            q_num = block.get("q_num", "")
            block_lecture = block.get("lecture", 0)
            _olpo_label = block.get("olpo_label", "")
            _passage_label = block.get("passage_label", "")
            _label_header = _tb_header_from_label(src, block.get("page_off", -1), _passage_label)
            _exam_code = block.get("exam_code", "")

            # 워크북에 박힌 6자리 출처코드(YYMMQQ)가 있으면 최우선 사용 — 가짜번호 방지.
            if _exam_code:
                # 올포 워크북: xlsx 매핑으로 "올포 N강 본문M" 라벨로 변환
                _olpo_hdr_v1 = None
                if olpo_lecture_map and ("올포" in src or "올림포스" in src):
                    from engines.final.olpo_mapper import code_to_olpo_header
                    _olpo_hdr_v1 = code_to_olpo_header(_exam_code, olpo_lecture_map)
                header = _olpo_hdr_v1 if _olpo_hdr_v1 else _exam_code
            # 고3 사전 변환 헤더가 있으면 즉시 사용
            elif block.get("_g3_header"):
                header = block["_g3_header"]
            elif _label_header:
                # 워크북 지문 마커({본문N}/{Further Reading}) 기반 헤더 — 최우선
                header = _label_header
                if src not in _tb_counters:
                    _tb_counters[src] = 0
                _tb_counters[src] += 1
            elif _is_rp_source(src):
                # 리딩파워: 1차 — 블록 원본 q_num + 스토리 lecture (가장 신뢰할 수 있는 매핑)
                # (예: q_num="Example1" → Ex01, q_num="2" → 02 — 원본 마커 그대로)
                _raw_qn = (block.get("q_num", "") or "").strip()
                _blk_lec = block.get("lecture", 0)
                matched = None
                _mq_ex = re.match(r"^Example(\d+)$", _raw_qn, re.IGNORECASE)
                _mq_num = re.match(r"^(\d+)$", _raw_qn)
                if _blk_lec and _blk_lec > 0:
                    if _mq_ex:
                        matched = (_blk_lec, True, int(_mq_ex.group(1)))
                    elif _mq_num:
                        matched = (_blk_lec, False, int(_mq_num.group(1)))
                # 1차 매핑이 같은 src에서 이미 사용된 헤더와 중복되면 시트 매칭으로 대체
                # (광문2 워크북01처럼 한 Story에 여러 강 마커가 일련번호({1}~{10})로 매겨진 케이스)
                if matched:
                    _L0, _is_ex0, _n0 = matched
                    _hdr_test = f"\ub9ac\ub529\ud30c\uc6cc {_L0}\uac15 {'Ex' if _is_ex0 else ''}{str(_n0).zfill(2)}"
                    _used_set = _used_rp_headers_per_src.get(src, set())
                    if _hdr_test in _used_set:
                        # 중복 → 시트 substring 매칭
                        _alt_matched = _rp_content_to_label(block, rp_sheet_data)
                        # 또는 단어 교집합 매칭 (영작 choices와 동일 함수, items[0]/passage 활용)
                        if not _alt_matched:
                            _block_text = ""
                            if block.get("passage"):
                                _block_text = block["passage"]
                            elif block.get("items"):
                                _block_text = " ".join(block["items"][:3])
                            if _block_text and len(_block_text) >= 30:
                                _alt_matched = _rp_writing_to_label(_block_text, rp_sheet_data)
                        if _alt_matched:
                            matched = _alt_matched
                # 2차 폴백: 1차 매핑이 아예 없으면 시트 기반 content matching
                if not matched:
                    matched = _rp_content_to_label(block, rp_sheet_data)
                if matched:
                    _L, _is_ex_entry, _n = matched
                    if _is_ex_entry:
                        header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 Ex{str(_n).zfill(2)}"
                    else:
                        header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 {str(_n).zfill(2)}"
                    # 사용된 헤더 기록 (다음 같은 src의 중복 검출용)
                    _used_rp_headers_per_src.setdefault(src, set()).add(header)
                else:
                    # 3차 폴백: 파일명+블록 순번 매핑
                    if src not in _rp_ex_map_cache:
                        _rp_ex_map_cache[src] = _build_rp_seq_map(src, rp_lecture_counts)
                    _cum_map, _is_ex_wb = _rp_ex_map_cache[src]
                    _rp_ex_order_counter[src] = _rp_ex_order_counter.get(src, 0) + 1
                    ord_idx = _rp_ex_order_counter[src]
                    if ord_idx in _cum_map:
                        _L, _n, _is_ex_entry = _cum_map[ord_idx]
                        if _is_ex_entry:
                            header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 Ex{str(_n).zfill(2)}"
                        else:
                            header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 {str(_n).zfill(2)}"
                    else:
                        header = f"\ub9ac\ub529\ud30c\uc6cc \ube14\ub85d {str(ord_idx).zfill(2)}"
            elif q_num:
                scope_match = re.search(r"\(([^)]+)\)", src)
                wb_scope = scope_match.group(1) if scope_match else ""

                # 교과서 섹션번호 판별: q_num이 18 미만이면 교과서 섹션번호
                # (모의고사 문항번호는 18~45 범위)
                _q_first = re.match(r"(\d+)", q_num)
                _q_val = int(_q_first.group(1)) if _q_first else 999
                _is_tb_section = _q_val < 18

                if _is_tb_section:
                    # 교과서 섹션번호: q_num을 무시하고 _tb_lesson_map으로 처리
                    # (아래 else 분기와 동일 로직)
                    if src in _tb_lesson_map:
                        if src not in _tb_counters:
                            _tb_counters[src] = 0
                        _cidx = _tb_counters[src]
                        header = _tb_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                        _tb_counters[src] += 1
                    elif _is_rp_source(src):
                        # 리딩파워 워크북: 파일명 강 목록 + 블록 순번으로 매핑
                        # (extractor의 lecture 값이 부정확할 수 있어 filename 기반으로 통일)
                        if src not in _rp_ex_map_cache:
                            _rp_ex_map_cache[src] = _build_rp_seq_map(src, rp_lecture_counts)
                        _cum_map, _is_ex_wb = _rp_ex_map_cache[src]
                        _rp_ex_order_counter[src] = _rp_ex_order_counter.get(src, 0) + 1
                        ord_idx = _rp_ex_order_counter[src]
                        if ord_idx in _cum_map:
                            _L, _n, _is_ex_entry = _cum_map[ord_idx]
                            if _is_ex_entry:
                                header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 Ex{str(_n).zfill(2)}"
                            else:
                                header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 {str(_n).zfill(2)}"
                        else:
                            header = f"\ub9ac\ub529\ud30c\uc6cc \ube14\ub85d {str(ord_idx).zfill(2)}"
                    elif block_lecture > 0 and ("올포" in (scope_match.group(1) if scope_match else "") or "올림포스독해기본" in src):
                        # 1순위: olpo_label (페이지 레이블 기반)
                        if _olpo_label:
                            header = f"\uc62c\ud3ec {block_lecture}\uac15 {_olpo_label}"
                        else:
                            # 폴백: 강별 본문 카운터
                            key = (src, block_lecture)
                            _lec_counters[key] = _lec_counters.get(key, 0) + 1
                            header = f"올포 {block_lecture}강 본문{_lec_counters[key]}"
                    else:
                        scope = scope_match.group(1) if scope_match else "지문"
                        # 마더텅: q_num이 교과서 섹션번호(<18)로 오인된 블록도 page_off 기반 매핑
                        _is_mt_tb = "\ub9c8\ub354\ud145" in scope
                        if _is_mt_tb:
                            _mt_seq_tb = _mt_page_seq.get((src, block.get("page_off", -1)))
                            if _mt_seq_tb is None:
                                source_mt_total[src] = source_mt_total.get(src, 0) + 1
                                _mt_seq_tb = source_mt_total[src]
                            _mapped = _mt_lookup(scope, _mt_seq_tb)
                            if _mapped:
                                header = _mapped
                            else:
                                if src not in source_counts:
                                    source_counts[src] = 0
                                source_counts[src] += 1
                                header = _scope_to_header(scope, source_counts[src])
                        else:
                            if src not in source_counts:
                                source_counts[src] = 0
                            source_counts[src] += 1
                            header = _scope_to_header(scope, source_counts[src])
                else:
                    # 모의고사 문항번호: YYMMQQ 변환
                    # 마더텅: 블록의 page_off를 _mt_page_seq로 조회해서 seq 확보
                    # (카운터 증가 방식은 같은 페이지가 sentence/insert 양쪽에 존재할 때
                    #  오프셋이 어긋나므로 page_off 기반이 안전하다)
                    _is_mt = "\ub9c8\ub354\ud145" in wb_scope
                    _mt_seq = _mt_page_seq.get((src, block.get("page_off", -1))) if _is_mt else None
                    if _is_mt and _mt_seq is None:
                        # 폴백: 기존 카운터 방식
                        source_mt_total[src] = source_mt_total.get(src, 0) + 1
                        _mt_seq = source_mt_total[src]
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
                        # wb_scope에 yy/mm 없어 변환 실패(마더텅 등) → 매핑 우선, 폴백 source 기반 헤더
                        if header == q_num and re.match(r"^\d{1,2}(?:[~\-]\d{1,2})?$", header):
                            _mapped = _mt_lookup(wb_scope, _mt_seq) if _is_mt else None
                            if _mapped:
                                header = _mapped
                            else:
                                if src not in source_counts:
                                    source_counts[src] = 0
                                source_counts[src] += 1
                                header = _scope_to_header(wb_scope, source_counts[src])
            else:
                # 교과서 블록: page_off 기반 과 경계 맵 사용 (q_num이 None/빈 경우)
                if src in _tb_lesson_map:
                    if src not in _tb_counters:
                        _tb_counters[src] = 0
                    _cidx = _tb_counters[src]
                    header = _tb_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                    _tb_counters[src] += 1
                elif block_lecture > 0 and ("올포" in src or "올림포스독해기본" in src):
                    # 1순위: olpo_label
                    if _olpo_label:
                        header = f"\uc62c\ud3ec {block_lecture}\uac15 {_olpo_label}"
                    else:
                        key = (src, block_lecture)
                        _lec_counters[key] = _lec_counters.get(key, 0) + 1
                        header = f"올포 {block_lecture}강 본문{_lec_counters[key]}"
                elif _is_rp_source(src):
                    # 리딩파워 워크북(no q_num): 파일명 강 목록 + 블록 순번으로 매핑
                    if src not in _rp_ex_map_cache:
                        _rp_ex_map_cache[src] = _build_rp_seq_map(src, rp_lecture_counts)
                    _cum_map, _is_ex_wb = _rp_ex_map_cache[src]
                    _rp_ex_order_counter[src] = _rp_ex_order_counter.get(src, 0) + 1
                    ord_idx = _rp_ex_order_counter[src]
                    if ord_idx in _cum_map:
                        _L, _n, _is_ex_entry = _cum_map[ord_idx]
                        if _is_ex_entry:
                            header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 Ex{str(_n).zfill(2)}"
                        else:
                            header = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 {str(_n).zfill(2)}"
                    else:
                        header = f"\ub9ac\ub529\ud30c\uc6cc \ube14\ub85d {str(ord_idx).zfill(2)}"
                else:
                    scope_match = re.search(r"\(([^)]+)\)", src)
                    scope = scope_match.group(1) if scope_match else "지문"
                    # 마더텅 워크북: 전체 순번 기준 YYMMQQ 매핑 시도 (page_off 기반 seq)
                    _is_mt_noq = "\ub9c8\ub354\ud145" in scope
                    if _is_mt_noq:
                        _mt_seq_noq = _mt_page_seq.get((src, block.get("page_off", -1)))
                        if _mt_seq_noq is None:
                            source_mt_total[src] = source_mt_total.get(src, 0) + 1
                            _mt_seq_noq = source_mt_total[src]
                        _mapped = _mt_lookup(scope, _mt_seq_noq)
                        if _mapped:
                            header = _mapped
                        else:
                            if src not in source_counts:
                                source_counts[src] = 0
                            source_counts[src] += 1
                            header = _scope_to_header(scope, source_counts[src])
                    else:
                        if src not in source_counts:
                            source_counts[src] = 0
                        source_counts[src] += 1
                        header = _scope_to_header(scope, source_counts[src])

            new_b = {
                "source": src,
                "header": header,
                "items": block["items"],
            }
            if block.get("passage"):
                new_b["passage"] = block["passage"]
            all_blocks.append(new_b)
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
        # 교과서 과별 본문 제한 필터 (시험범위 시트 교과서 컬럼 기반)
        if textbook_limits:
            deduped = [b for b in deduped if _passes_textbook_limit(b["header"], textbook_limits)]
        # 교과서 과별 RM/FR 허용 필터 ((N과는 Read More도 포함) 표기 기반)
        if textbook_rm_lessons is not None:
            deduped = [b for b in deduped if _passes_textbook_rm_filter(b["header"], textbook_rm_lessons)]
        # 헤더 순 정렬: 교과서 먼저, N강 NN, YYMMQQ, 올포 N강 {분석|본문N|서술형|논술형} 순
        # 올포 섹션 순서: 분석(0) → 본문1..N(1~N) → 서술형(900) → 논술형(901)
        def _olpo_section_order(section):
            if section == "\ubd84\uc11d":
                return 0
            m_b = re.match(r'^\ubcf8\ubb38(\d+)$', section)
            if m_b:
                return int(m_b.group(1))
            if section == "\uc11c\uc220\ud615":
                return 900
            if section == "\ub17c\uc220\ud615":
                return 901
            return 999
        def _header_sort_key_g3(b):
            h = b["header"]
            # N강 NN 형식: "3강 01" → (0, 3, 1, ...)
            m_lec = re.match(r'^(\d+)강\s*(\d+)?', h)
            if m_lec:
                lec_num = int(m_lec.group(1))
                sub_num = int(m_lec.group(2)) if m_lec.group(2) else 0
                return (0, lec_num, sub_num, h)
            if h.startswith("교과서"):
                m_tb = re.match(r'^교과서\s*(\d+)\s*과\s*본문\s*(\d+)', h)
                m_tb_fr = re.match(r'^교과서\s*(\d+)\s*과\s*(?:FR|RM)', h)
                if m_tb:
                    tb_lesson = int(m_tb.group(1))
                    tb_num = int(m_tb.group(2))
                elif m_tb_fr:
                    tb_lesson = int(m_tb_fr.group(1))
                    tb_num = 999  # FR/RM은 해당 과의 본문 뒤
                elif h.startswith("교과서SL"):
                    tb_lesson = 999
                    if h.endswith("FR") or h.endswith("RM"):
                        tb_num = 999
                    else:
                        m_sl = re.search(r'본문\s*(\d+)', h)
                        tb_num = int(m_sl.group(1)) if m_sl else 0
                elif re.match(r'^교과서Project\d+', h):
                    m_pj = re.match(r'^교과서Project(\d+)\s*본문\s*(\d+)?', h)
                    tb_lesson = 500 + int(m_pj.group(1)) if m_pj else 500
                    tb_num = int(m_pj.group(2)) if (m_pj and m_pj.group(2)) else 0
                else:
                    tb_lesson = 0
                    tb_num = 0
                return (0.9, tb_lesson, tb_num, h)
            m_olpo = re.match(r'^\uc62c\ud3ec\s+(\d+)\uac15\s+(.+)$', h)
            if m_olpo:
                lec_n = int(m_olpo.group(1))
                sec = m_olpo.group(2).strip()
                return (2, lec_n, _olpo_section_order(sec), h)
            m_mt = re.match(r'^\ub9c8\ub354\ud145(\d*)\s*\ubcf8\ubb38(\d+)', h)
            if m_mt:
                mt_wb = int(m_mt.group(1)) if m_mt.group(1) else 0
                mt_n = int(m_mt.group(2))
                return (3, mt_wb, mt_n, h)
            m = re.match(r'^(\d{6})', h)
            return (1, int(m.group(1)) if m else 999999, 0, h)

        def _header_sort_key_workbook(b):
            """고1/고2: 교과서 → 리딩파워 non-Example → 리딩파워 Example → 모의고사 순."""
            src = _nfc(b.get("source", ""))
            orig = b.get("_orig_idx", 0)
            key = _canonical_order_key(b["header"], src)
            return key + (orig,)

        if grade == "\uace03":
            deduped.sort(key=_header_sort_key_g3)
        else:
            # 원본 등장 순서 기록 (고1/고2 워크북 순서 정렬용)
            for _i, _b in enumerate(deduped):
                _b["_orig_idx"] = _i
            deduped.sort(key=_header_sort_key_workbook)
            for _b in deduped:
                _b.pop("_orig_idx", None)
        vol1["문장배열"] = deduped

    # 문장삽입/순서배열 — 과 경계 감지 (문장배열과 동일 방식)
    if sentence_insert_blocks:
        sentence_insert_blocks = _sort_blocks(sentence_insert_blocks)

        # pageQNum 누락 보완 — 문장배열과 동일 로직
        if scope_exams:
            _fill_by_src = {}
            for _b in sentence_insert_blocks:
                if _b.get("q_num"):
                    continue
                _src = _nfc(_b.get("source", ""))
                _sm = re.search(r"\(([^)]+)\)", _src)
                _sc = _sm.group(1) if _sm else ""
                _ym = re.search(r"(\d{2})\ub144\s*(\d{1,2})\uc6d4", _sc)
                if not _ym:
                    continue
                _fill_by_src.setdefault(_src, []).append(_b)
            for _src, _blocks_to_fill in _fill_by_src.items():
                _sm = re.search(r"\(([^)]+)\)", _src)
                _sc = _sm.group(1) if _sm else ""
                _ym = re.search(r"(\d{2})\ub144\s*(\d{1,2})\uc6d4", _sc)
                _yy, _mm = _ym.group(1), _ym.group(2).zfill(2)
                _matching = None
                for _ex in scope_exams:
                    _ey = str(_ex.get("year", ""))
                    _em = str(_ex.get("month", "")).zfill(2)
                    if _ey == _yy and _em == _mm:
                        _matching = _ex
                        break
                if not _matching:
                    continue
                _nums = sorted(int(n) for n in _matching.get("numbers", []) if isinstance(n, int) or (isinstance(n, str) and n.isdigit()))
                _blocks_to_fill.sort(key=lambda _x: _x.get("page_off", 10**9))
                for _b, _n in zip(_blocks_to_fill, _nums):
                    _b["q_num"] = str(_n)

        # 문장삽입 교과서 블록 과 경계 맵 구축 (문장배열과 동일 로직)
        _ins_page_map = {}
        _ins_src_idx = {}
        for _ib in sentence_insert_blocks:
            _isrc = _nfc(_ib.get("source", ""))
            _iq = _ib.get("q_num", "")
            if _iq:
                _iqm = re.match(r"(\d+)", _iq)
                if _iqm and int(_iqm.group(1)) >= 18:
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
            # Project 워크북 처리 (예: 워크북02(YBM(김)Project1))
            _iproj_m = re.search(r"Project\s*(\d+)", _isrc, re.IGNORECASE) if not _ilm else None
            if _iproj_m:
                _iproj_label = f"Project{_iproj_m.group(1)}"
                _ins_lesson_map[_isrc] = {}
                for _idx, _po in _iblocks:
                    _ins_lesson_map[_isrc][_idx] = f"교과서{_iproj_label} 본문{_idx + 1}"
                continue
            if not _ilm:
                continue
            _ilessons = [l.strip() for l in _ilm.group(1).split(",")]
            # SL 포함 여부 체크
            _ihas_sl = "SL" in _iscope
            _iall_lessons = list(_ilessons)
            if _ihas_sl:
                _iall_lessons.append("SL")

            _in_blocks = len(_iblocks)
            if len(_iall_lessons) <= 1:
                _ins_lesson_map[_isrc] = {}
                for _idx, _po in _iblocks:
                    if _iall_lessons[0] == "SL":
                        _sl_hdr = sl_section_headers[_idx] if sl_section_headers and _idx < len(sl_section_headers) else f"교과서SL 본문{_idx + 1}"
                        _ins_lesson_map[_isrc][_idx] = _sl_hdr
                    else:
                        _ins_lesson_map[_isrc][_idx] = f"교과서{_iall_lessons[0]}과 본문{_idx + 1}"
                continue
            # 실제 블록 수 기준 균등 분할
            _ibpl = max(1, _in_blocks // len(_iall_lessons))
            _ins_lesson_map[_isrc] = {}
            _ioff = 0
            for _ili, _il in enumerate(_iall_lessons):
                if _ili == len(_iall_lessons) - 1:
                    _ic = _in_blocks - _ioff
                else:
                    _ic = _ibpl
                for _ibi in range(_ic):
                    _igidx = _ioff + _ibi
                    if _igidx >= _in_blocks:
                        break
                    if _il == "SL":
                        if sl_section_headers and _ibi < len(sl_section_headers):
                            _ins_lesson_map[_isrc][_igidx] = sl_section_headers[_ibi]
                        else:
                            _ins_lesson_map[_isrc][_igidx] = f"교과서SL 본문{_ibi + 1}"
                    else:
                        _ins_lesson_map[_isrc][_igidx] = f"교과서{_il}과 본문{_ibi + 1}"
                _ioff += _ic

        # passage_label 기반 매핑: src+page_off → 과 (문장배열과 동일 로직)
        _ins_story_lesson = {}
        for _isrc, _iblocks in _ins_page_map.items():
            _ism = re.search(r"\(([^)]+)\)", _isrc)
            _iscope = _ism.group(1) if _ism else ""
            _ilm = re.search(r"(\d+(?:,\d+)*)\s*과", _iscope)
            # Project 워크북 처리
            _iproj_m = re.search(r"Project\s*(\d+)", _isrc, re.IGNORECASE) if not _ilm else None
            if _iproj_m:
                _iproj_label = f"Project{_iproj_m.group(1)}"
                _unique_pos_i = sorted({_po for _, _po in _iblocks if _po >= 0})
                _mi = {}
                for _po in _unique_pos_i:
                    _mi[_po] = _iproj_label
                _ins_story_lesson[_isrc] = _mi
                continue
            if not _ilm:
                continue
            _ilessons = [l.strip() for l in _ilm.group(1).split(",")]
            _ihas_sl = "SL" in _iscope
            _iall_lessons = list(_ilessons)
            if _ihas_sl:
                _iall_lessons.append("SL")
            _unique_pos_i = sorted({_po for _, _po in _iblocks if _po >= 0})
            _mi = {}
            for _sii, _po in enumerate(_unique_pos_i):
                _mi[_po] = _iall_lessons[_sii] if _sii < len(_iall_lessons) else _iall_lessons[-1]
            _ins_story_lesson[_isrc] = _mi

        def _ins_header_from_label(_src, _page_off, _label):
            if not _label:
                return None
            # 딥러닝 인코딩: "본문N@과M" → 과 번호가 라벨에 직접 포함됨 (page_off 매핑 불필요)
            # 딥러닝 워크북은 본문 슬롯에 매핑되지만 헤더 라벨은 "교과서{M}과 딥러닝"으로 출력.
            _dl_m = re.match(r"^(본문\d+)@과(\d+)$", _label)
            if _dl_m:
                return f"교과서{_dl_m.group(2)}과 딥러닝"
            _lesson_map = _ins_story_lesson.get(_src)
            if not _lesson_map:
                return None
            _lesson = _lesson_map.get(_page_off)
            if _lesson is None:
                return None
            if _label in ("FR", "RM"):
                _suf = _label
                if _lesson == "SL":
                    return f"교과서SL {_suf}"
                if _lesson.startswith("Project"):
                    return f"교과서{_lesson} {_suf}"
                return f"교과서{_lesson}과 {_suf}"
            if _label.startswith("본문"):
                if _lesson == "SL":
                    return f"교과서SL {_label}"
                if _lesson.startswith("Project"):
                    return f"교과서{_lesson} {_label}"
                return f"교과서{_lesson}과 {_label}"
            return None

        all_insert = []
        source_counts = {}
        source_mt_total = {}  # 마더텅 워크북 전체 지문 순번 (YYMMQQ 매핑 조회용)
        source_exam_idx = {}
        source_prev_qnum = {}
        _ins_counters = {}
        _ins_lec_counters = {}  # (src, lecture) -> 강별 본문 카운터 (올포 폴백)
        for block in sentence_insert_blocks:
            src = _nfc(block.get("source", ""))
            q_num = block.get("q_num", "")
            block_lecture = block.get("lecture", 0)
            _olpo_label = block.get("olpo_label", "")
            _passage_label = block.get("passage_label", "")
            _label_header = _ins_header_from_label(src, block.get("page_off", -1), _passage_label)
            _exam_code = block.get("exam_code", "")

            # 워크북에 박힌 6자리 출처코드(YYMMQQ)가 있으면 최우선 사용 — 가짜번호 방지.
            if _exam_code:
                # 올포 워크북: xlsx 매핑으로 "올포 N강 본문M" 라벨로 변환
                _olpo_hdr_ins = None
                if olpo_lecture_map and ("올포" in src or "올림포스" in src):
                    from engines.final.olpo_mapper import code_to_olpo_header
                    _olpo_hdr_ins = code_to_olpo_header(_exam_code, olpo_lecture_map)
                header = _olpo_hdr_ins if _olpo_hdr_ins else _exam_code
            elif block.get("_preset_header"):
                # 사전 변환된 헤더 (교과서 문장삽입 등) — 즉시 사용
                header = block["_preset_header"]
            elif _label_header:
                header = _label_header
                if src not in _ins_counters:
                    _ins_counters[src] = 0
                _ins_counters[src] += 1
            elif q_num:
                scope_match = re.search(r"\(([^)]+)\)", src)
                wb_scope = scope_match.group(1) if scope_match else ""

                _q_first = re.match(r"(\d+)", q_num)
                _q_val = int(_q_first.group(1)) if _q_first else 999
                _is_tb_section = _q_val < 18

                if _is_tb_section:
                    # 교과서 섹션번호: _ins_lesson_map으로 처리
                    if src in _ins_lesson_map:
                        if src not in _ins_counters:
                            _ins_counters[src] = 0
                        _cidx = _ins_counters[src]
                        header = _ins_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                        _ins_counters[src] += 1
                    elif block_lecture > 0 and ("올포" in (scope_match.group(1) if scope_match else "") or "올림포스독해기본" in src):
                        # 1순위: olpo_label
                        if _olpo_label:
                            header = f"\uc62c\ud3ec {block_lecture}\uac15 {_olpo_label}"
                        else:
                            key = (src, block_lecture)
                            _ins_lec_counters[key] = _ins_lec_counters.get(key, 0) + 1
                            header = f"올포 {block_lecture}강 본문{_ins_lec_counters[key]}"
                    else:
                        scope = scope_match.group(1) if scope_match else "지문"
                        # 마더텅 워크북: q_num이 비어 이 경로로 빠진 블록도 page_off 기반 매핑
                        _is_mt_tb = "\ub9c8\ub354\ud145" in scope
                        if _is_mt_tb:
                            _mt_seq_tb = _mt_page_seq.get((src, block.get("page_off", -1)))
                            if _mt_seq_tb is None:
                                source_mt_total[src] = source_mt_total.get(src, 0) + 1
                                _mt_seq_tb = source_mt_total[src]
                            _mapped = _mt_lookup(scope, _mt_seq_tb)
                            if _mapped:
                                header = _mapped
                            else:
                                if src not in source_counts:
                                    source_counts[src] = 0
                                source_counts[src] += 1
                                header = _scope_to_header(scope, source_counts[src])
                        else:
                            if src not in source_counts:
                                source_counts[src] = 0
                            source_counts[src] += 1
                            header = _scope_to_header(scope, source_counts[src])
                else:
                    # 마더텅: page_off 기반 seq 매핑
                    _is_mt = "\ub9c8\ub354\ud145" in wb_scope
                    _mt_seq = _mt_page_seq.get((src, block.get("page_off", -1))) if _is_mt else None
                    if _is_mt and _mt_seq is None:
                        source_mt_total[src] = source_mt_total.get(src, 0) + 1
                        _mt_seq = source_mt_total[src]
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
                        # wb_scope에 yy/mm 없어 변환 실패(마더텅 등) → 매핑 우선, 폴백 source 기반 헤더
                        if header == q_num and re.match(r"^\d{1,2}(?:[~\-]\d{1,2})?$", header):
                            _mapped = _mt_lookup(wb_scope, _mt_seq) if _is_mt else None
                            if _mapped:
                                header = _mapped
                            else:
                                if src not in source_counts:
                                    source_counts[src] = 0
                                source_counts[src] += 1
                                header = _scope_to_header(wb_scope, source_counts[src])
            else:
                # 교과서 블록: 과 경계 맵 사용 (q_num이 None/빈 블록. 마더텅 일부도 여기로 빠짐)
                if src in _ins_lesson_map:
                    if src not in _ins_counters:
                        _ins_counters[src] = 0
                    _cidx = _ins_counters[src]
                    header = _ins_lesson_map[src].get(_cidx, f"교과서 본문{_cidx + 1}")
                    _ins_counters[src] += 1
                elif block_lecture > 0 and ("올포" in src or "올림포스독해기본" in src):
                    # 1순위: olpo_label
                    if _olpo_label:
                        header = f"\uc62c\ud3ec {block_lecture}\uac15 {_olpo_label}"
                    else:
                        key = (src, block_lecture)
                        _ins_lec_counters[key] = _ins_lec_counters.get(key, 0) + 1
                        header = f"올포 {block_lecture}강 본문{_ins_lec_counters[key]}"
                else:
                    scope_match = re.search(r"\(([^)]+)\)", src)
                    scope = scope_match.group(1) if scope_match else "지문"
                    # 마더텅 워크북: page_off 기반 YYMMQQ 매핑 시도
                    _is_mt_noq = "\ub9c8\ub354\ud145" in scope
                    if _is_mt_noq:
                        _mt_seq_noq = _mt_page_seq.get((src, block.get("page_off", -1)))
                        if _mt_seq_noq is None:
                            source_mt_total[src] = source_mt_total.get(src, 0) + 1
                            _mt_seq_noq = source_mt_total[src]
                        _mapped = _mt_lookup(scope, _mt_seq_noq)
                        if _mapped:
                            header = _mapped
                        else:
                            if src not in source_counts:
                                source_counts[src] = 0
                            source_counts[src] += 1
                            header = _scope_to_header(scope, source_counts[src])
                    else:
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
        # 교과서 과별 본문 제한 필터
        if textbook_limits:
            deduped_ins = [b for b in deduped_ins if _passes_textbook_limit(b["header"], textbook_limits)]
        # 교과서 과별 RM/FR 허용 필터
        if textbook_rm_lessons is not None:
            deduped_ins = [b for b in deduped_ins if _passes_textbook_rm_filter(b["header"], textbook_rm_lessons)]

        # 리딩파워 워크북은 문장삽입 섹션 없음 — sync 전에 제거
        # (sync에서 문장배열 헤더에 해당하는 빈 stub 생성)
        deduped_ins = [
            b for b in deduped_ins
            if not _is_rp_source(b.get("source", ""))
        ]

        # 문장배열과 1:1 동기화 — 문장배열 헤더 순서로 먼저 정렬.
        # 리딩파워/교과서 출처는 문장삽입 없으면 stub 생성하지 않음 (실제 paras 있는 블록만 포함).
        if vol1.get("문장배열"):
            arr_blocks = vol1["문장배열"]
            arr_set = set(b["header"] for b in arr_blocks)
            ins_by_header = {b["header"]: b for b in deduped_ins}
            synced = []
            for ab in arr_blocks:
                h = ab["header"]
                if h in ins_by_header and ins_by_header[h].get("paras"):
                    synced.append(ins_by_header[h])
                # stub 생성 안 함 — 실제 데이터가 있는 블록만 포함
            for b in deduped_ins:
                if b["header"] not in arr_set and b.get("paras"):
                    synced.append(b)
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
                scope_exams=None, allowed_olpo_lectures=None, mt_seq_map=None,
                vol1_sentence_blocks=None, textbook_limits=None,
                rp_sheet_data=None, olpo_lecture_map=None,
                textbook_rm_lessons=None):
    """Vol2 데이터 구성.

    allowed_olpo_lectures: 허용 올포 강 번호 set. 없으면 전체 허용.
    mt_seq_map: 마더텅 워크북별 {src_nfc: {page_off: 원고_지문_순번}}. YYMMQQ 매핑 정확도용.
    vol1_sentence_blocks: Vol1 문장배열 블록 리스트. 리딩파워 영작 헤더 매핑에 사용 (시트 기반).
    rp_sheet_data: 리딩파워 시트 (key, text) 목록. 영작 헤더 폴백 시 content matching 용.
    """
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
        _seen_grammar_headers = set()  # 중복 헤더 감지용
        for line in all_lines:
            is_header = (re.match(r"^\d{6}", line) or
                         re.match(r"^교과서", line) or
                         re.match(r"^\d{1,2}과\s", line) or
                         re.match(r"^S\d+과\s", line) or
                         re.match(r"^SL\s", line) or
                         re.match(r"^\d+강(\s|$)", line) or
                         re.match(r"^올포\s+\d+강\s+(본문\d+|분석|서술형|논술형)", line) or
                         re.match(r"^리딩파워\s+\d+강\s+본문\d+", line) or
                         re.match(r"^마더텅\d*\s+본문\d+", line) or
                         re.match(r"^TED\d+\s+본문\d+", line) or
                         re.match(r"^외부지문\s+본문\d+", line) or
                         re.match(r"^test\d+(\s|$)", line, re.IGNORECASE))
            if is_header:
                normalized = _normalize_q41_42(line.strip())
                in_scope = _is_in_scope(normalized, scope_exams) if scope_exams else True
                tb_ok = _passes_textbook_limit(normalized, textbook_limits) if textbook_limits else True
                rm_ok = _passes_textbook_rm_filter(normalized, textbook_rm_lessons) if textbook_rm_lessons is not None else True
                # 중복 헤더 제거 (같은 헤더가 두 번 나오면 두 번째부터 스킵)
                is_dup = normalized in _seen_grammar_headers
                _seen_grammar_headers.add(normalized)
                skip_until_next_header = not in_scope or is_dup or not tb_ok or not rm_ok
                if in_scope and not is_dup and tb_ok and rm_ok:
                    grammar_headers.append(normalized)
                    filtered_lines.append(normalized)
                elif is_dup:
                    pass  # 중복 헤더 + 본문 모두 스킵
            elif not skip_until_next_header:
                filtered_lines.append(line)

        # 고1/고2 올포 헤더 기준으로 재정렬 — 강번호 + 섹션순서
        # (고3 정렬은 parse_extracted에서 이미 처리되므로 여기서는 올포만 대상)
        # 헤더를 블록 단위로 묶은 후 정렬 → grammar_headers + filtered_lines 재구성
        _has_olpo_hdr = any(re.match(r"^\uc62c\ud3ec\s+\d+\uac15", h) for h in grammar_headers)
        if _has_olpo_hdr:
            def _olp_sec_order(sec):
                if sec == "\ubd84\uc11d": return 0
                mb = re.match(r"\ubcf8\ubb38(\d+)", sec)
                if mb: return int(mb.group(1))
                if sec == "\uc11c\uc220\ud615": return 900
                if sec == "\ub17c\uc220\ud615": return 901
                return 999
            def _hdr_sort_key(hdr):
                # 교과서 → 0, YYMMQQ → 1, 올포 → 2
                if hdr.startswith("\uad50\uacfc\uc11c"):
                    return (0, 0, 0, hdr)
                m_yymm = re.match(r"^(\d{6})", hdr)
                if m_yymm:
                    return (1, int(m_yymm.group(1)), 0, hdr)
                m_olp = re.match(r"^\uc62c\ud3ec\s+(\d+)\uac15\s+(.+)$", hdr)
                if m_olp:
                    return (2, int(m_olp.group(1)), _olp_sec_order(m_olp.group(2).strip()), hdr)
                return (3, 0, 0, hdr)
            # 블록 단위로 묶기: 헤더 라인 + 다음 헤더 전까지의 본문 라인
            gram_blocks = []
            cur_hdr = None
            cur_body = []
            for line in filtered_lines:
                if line in set(grammar_headers):  # 헤더 라인
                    if cur_hdr is not None:
                        gram_blocks.append((cur_hdr, cur_body))
                    cur_hdr = line
                    cur_body = []
                else:
                    if cur_hdr is not None:
                        cur_body.append(line)
            if cur_hdr is not None:
                gram_blocks.append((cur_hdr, cur_body))
            # 정렬
            gram_blocks.sort(key=lambda b: _hdr_sort_key(b[0]))
            # 재구성
            grammar_headers = [b[0] for b in gram_blocks]
            filtered_lines = []
            for hdr, body in gram_blocks:
                filtered_lines.append(hdr)
                filtered_lines.extend(body)

        # scope_exams 없어도 textbook_limits/textbook_rm_lessons 필터가 적용된 경우 filtered_lines 사용
        _has_filter = bool(scope_exams) or bool(textbook_limits) or (textbook_rm_lessons is not None)
        vol2["어법수정"] = filtered_lines if _has_filter else all_lines
        if grammar_headers:
            vol2["어법_헤더"] = grammar_headers

    # 서술형 영작: 한글과 보기를 쌍으로
    # writing_kor/writing_view는 이제 dict 리스트: {"text": ..., "source": ..., "q_num": ...}
    if writing_kor or writing_view:
        # 올포 블록의 lecture 할당:
        # 1순위: exam_code(YYMMQQ) → xlsx 매핑 (학교 올포 워크북 정확 매핑)
        # 2순위: page_off 기반 그룹핑 (공용 올포 파일 폴백)
        def _assign_lecture_from_exam_code_w(blocks):
            if not olpo_lecture_map:
                return
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("lecture", 0) > 0:
                    continue
                ec = str(b.get("exam_code", "") or "").strip()
                if not ec:
                    continue
                info = olpo_lecture_map.get(ec)
                if info:
                    b["lecture"] = info[0]
        _assign_lecture_from_exam_code_w(writing_kor)
        _assign_lecture_from_exam_code_w(writing_view)
        _reassign_olpo_lectures(writing_kor)
        _reassign_olpo_lectures(writing_view)

        # 공용 올포 파일에서 추출된 블록 중 허용 강 범위 외는 제외
        if allowed_olpo_lectures:
            def _is_olpo_src(b):
                if not isinstance(b, dict):
                    return False
                src = _nfc(b.get("source", ""))
                return "올포" in src or "올림포스독해기본" in src
            writing_kor = [
                b for b in writing_kor
                if not _is_olpo_src(b) or b.get("lecture", 0) in allowed_olpo_lectures
            ]
            writing_view = [
                b for b in writing_view
                if not _is_olpo_src(b) or b.get("lecture", 0) in allowed_olpo_lectures
            ]

        # 모의고사 문항번호 scope 필터: scope 밖 q_num은 제외
        # (헤더 생성에서만 걸러지면 pairs에는 남아 직전 블록에 지문번호 없이 합쳐짐)
        if scope_exams:
            _allowed_mock_qnums = set()
            for _ex in scope_exams:
                for _n in _ex.get("numbers", []):
                    try:
                        _allowed_mock_qnums.add(int(_n))
                    except (TypeError, ValueError):
                        continue

            # source별 허용 문항번호 사전 계산 (scope: "25년3월" → {21,22,...,40})
            _src_scope_qnums = {}  # src_nfc -> set of allowed qnums
            for _ex in scope_exams:
                try:
                    _ey = str(_ex.get('year', ''))
                    _em = str(_ex.get('month', '')).zfill(2) if isinstance(_ex.get('month'), str) else str(_ex.get('month', '')).zfill(2)
                except Exception:
                    continue
                _src_scope_qnums[(_ey, _em)] = set(int(n) for n in _ex.get('numbers', []) if isinstance(n, int) or (isinstance(n, str) and n.isdigit()))

            def _mock_q_in_scope(item):
                if not isinstance(item, dict):
                    return True
                q_num = (item.get("q_num", "") or "").strip()
                if not q_num or q_num.startswith("본문") or not q_num[0].isdigit():
                    return True
                src_nfc = _nfc(item.get("source", ""))
                _sm = re.search(r"\(([^)]+)\)", src_nfc)
                _scope = _sm.group(1) if _sm else ""
                if not re.search(r"\d{2}\ub144\s*\d{1,2}\uc6d4|\ubaa8\uc758\uace0\uc0ac", _scope):
                    return True  # 모의고사 아님
                _mm = re.match(r"(\d+)(?:[~\-](\d+))?", q_num)
                if not _mm:
                    return True
                _q1_raw = int(_mm.group(1))
                _q2_raw = int(_mm.group(2)) if _mm.group(2) else _q1_raw
                # q_num이 6자리 YYMMQQ 형태이면 자체 년월로 해당 시험의 numbers에서 직접 확인
                # (복합 scope "23년6월_24년9월"에서 q_num="240930"인 경우 24년9월 시험으로 매칭)
                if _q1_raw >= 1000:
                    _q1_str = str(_q1_raw).zfill(6)
                    _q1_yy = _q1_str[:2]
                    _q1_mm = _q1_str[2:4]
                    _q1_qq = int(_q1_str[4:6])
                    _q1_allowed = _src_scope_qnums.get((_q1_yy, _q1_mm))
                    if _q1_allowed is not None and _q1_qq in _q1_allowed:
                        return True
                    # q2가 있으면 (범위 문항) q2도 확인
                    if _q2_raw >= 1000:
                        _q2_str = str(_q2_raw).zfill(6)
                        _q2_yy = _q2_str[:2]
                        _q2_mm = _q2_str[2:4]
                        _q2_qq = int(_q2_str[4:6])
                        _q2_allowed = _src_scope_qnums.get((_q2_yy, _q2_mm))
                        if _q2_allowed is not None and _q2_qq in _q2_allowed:
                            return True
                    # 6자리 YYMMQQ인데 해당 시험/문항이 scope에 없으면 제외
                    return False
                # 2자리 문항번호 (예: q_num="30"): scope 텍스트의 첫 (yy, mm)로 매칭
                _q1 = _q1_raw
                _q2 = _q2_raw
                # source scope와 매칭되는 시험의 numbers에서 엄격 확인
                _src_yy_mm = re.search(r"(\d{2})\ub144\s*(\d{1,2})\uc6d4", _scope)
                if _src_yy_mm:
                    _src_key = (_src_yy_mm.group(1), _src_yy_mm.group(2).zfill(2))
                    _src_allowed = _src_scope_qnums.get(_src_key)
                    if _src_allowed is not None:
                        return _q1 in _src_allowed or _q2 in _src_allowed
                # 폴백: 전역 허용 집합 (기존 동작)
                return _q1 in _allowed_mock_qnums or _q2 in _allowed_mock_qnums

            writing_kor = [w for w in writing_kor if _mock_q_in_scope(w)]
            writing_view = [w for w in writing_view if _mock_q_in_scope(w)]

        # 교과서 과별 본문 제한 필터: source scope가 "N과"이고 q_num="본문M"인데 M > limit이면 제외
        if textbook_limits:
            def _tb_limit_pass(item):
                if not isinstance(item, dict):
                    return True
                q = (item.get("q_num", "") or "").strip()
                if not q.startswith("\ubcf8\ubb38"):
                    return True
                src_nfc = _nfc(item.get("source", ""))
                _sm = re.search(r"\(([^)]+)\)", src_nfc)
                _scope = _sm.group(1) if _sm else ""
                # scope에서 과 번호 추출
                m_l = re.search(r"(\d+)\s*\uacfc", _scope)
                if not m_l:
                    if "SL" in _scope:
                        lesson = "SL"
                    else:
                        return True
                else:
                    lesson = m_l.group(1)
                max_body = textbook_limits.get(lesson)
                if max_body is None:
                    return True
                # "\ubcf8\ubb383-1" \ub4f1 \ud558\uc704\ubc88\ud638 \ub300\uc751: \uc8fc\ubc88\ud638\ub9cc \ube44\uad50.
                _bm = re.match(r"(\d+)", q.replace("\ubcf8\ubb38", ""))
                if not _bm:
                    return True
                body_num = int(_bm.group(1))
                return body_num <= max_body
            writing_kor = [w for w in writing_kor if _tb_limit_pass(w)]
            writing_view = [w for w in writing_view if _tb_limit_pass(w)]

        # 교과서 과별 RM/FR 허용 필터 ((N과는 Read More도 포함) 표기 기반)
        if textbook_rm_lessons is not None:
            def _tb_rm_pass(item):
                if not isinstance(item, dict):
                    return True
                q = (item.get("q_num", "") or "").strip()
                # FR/RM 만 검사
                if q not in ("FR", "RM"):
                    return True
                src_nfc = _nfc(item.get("source", ""))
                _sm = re.search(r"\(([^)]+)\)", src_nfc)
                _scope = _sm.group(1) if _sm else ""
                # scope에서 과 번호 추출
                m_l = re.search(r"(\d+)\s*과", _scope)
                if not m_l:
                    if "SL" in _scope:
                        lesson = "SL"
                    else:
                        return True
                else:
                    lesson = m_l.group(1)
                return lesson in textbook_rm_lessons
            writing_kor = [w for w in writing_kor if _tb_rm_pass(w)]
            writing_view = [w for w in writing_view if _tb_rm_pass(w)]

        # 워크북 번호 + 파일 내 페이지 순서로 정렬
        # q_num으로 정렬하면 다른 과의 동일 본문번호가 섞이는 문제 발생
        def _writing_sort_key(item):
            if not isinstance(item, dict):
                return (999, 0, 0, 0)
            src = _nfc(item.get("source", ""))
            po = item.get("page_off", -1)
            sec = po if po >= 0 else 10000
            # 올포는 lecture 기반 정렬 (워크북 번호 정보가 공용 파일에 없음)
            if "올림포스독해기본" in src or "올포" in src:
                lec = item.get("lecture", 0) or 999
                return (500, lec, sec, 0)
            m = re.search(r"워크북\s*(\d+)", src)
            wb_num = int(m.group(1)) if m else 999
            return (wb_num, sec, 0, 0)

        writing_kor.sort(key=_writing_sort_key)
        writing_view.sort(key=_writing_sort_key)

        # (source, lecture, q_num, exam_code) 기반 한글-보기 매칭 (스타일 오류 방어)
        # 다른 강의 동일 q_num이 하나로 섞이지 않도록 source + lecture + q_num + exam_code 조합 키 사용.
        # exam_code 포함 이유: 같은 워크북에 q_num="37"이 230337(고1 3월 37번)과
        # 230637(고1 6월 37번) 두 출처로 등장할 수 있고, q_num만으로는 두 본문이 합쳐져
        # pair index와 헤더 start_idx가 어긋난다.
        from collections import OrderedDict
        def _pair_key(w):
            return (_nfc(w.get("source", "")), w.get("lecture", 0),
                    w.get("q_num", ""), w.get("exam_code", ""))
        _kor_by_q = OrderedDict()
        for w in writing_kor:
            if not isinstance(w, dict):
                continue
            _kor_by_q.setdefault(_pair_key(w), []).append(w["text"])
        _view_by_q = OrderedDict()
        for w in writing_view:
            if not isinstance(w, dict):
                continue
            _view_by_q.setdefault(_pair_key(w), []).append(w["text"])

        pairs = []
        # writing_kor 전역 index -> pairs index 매핑
        # (view-only pair가 중간에 끼면 writing_kor index와 pairs index가 어긋나서
        #  writing_headers의 start_idx가 실제 pair 위치와 밀린다)
        _kor_to_pair_idx = {}
        _kor_gi = 0
        all_keys_ordered = list(OrderedDict.fromkeys(
            [_pair_key(w) for w in writing_kor if isinstance(w, dict)] +
            [_pair_key(w) for w in writing_view if isinstance(w, dict)]
        ))
        for q in all_keys_ordered:
            kors = _kor_by_q.get(q, [])
            views = _view_by_q.get(q, [])
            q_len = max(len(kors), len(views))
            for qi in range(q_len):
                pair_idx = len(pairs)
                pair = {}
                if qi < len(kors):
                    pair["korean"] = kors[qi]
                    _kor_to_pair_idx[_kor_gi] = pair_idx
                    _kor_gi += 1
                if qi < len(views):
                    pair["choices"] = views[qi]
                pairs.append(pair)
        vol2["서술형영작"] = pairs

        # 리딩파워 영작 pair의 choices(영어)를 시트 데이터와 매칭해 정확한 (강, 번호) 매핑 구축
        # (광문2처럼 파일명/내용 불일치 워크북에서 폴백이 잘못된 Ex 헤더를 생성하는 것을 방지)
        _pair_sheet_header = {}  # pair index -> 시트 기반 header
        if rp_sheet_data:
            for _pi, _p in enumerate(pairs):
                _ch = _p.get("choices", "") or ""
                _ko = _p.get("korean", "") or ""
                if len(_ch) < 20:
                    continue
                # 1차: substring prefix 매칭 (원문 prefix가 choices에 포함된 케이스)
                _matched = _rp_content_to_label({"items": [_ch], "passage": _ch}, rp_sheet_data)
                # 2차: 단어 교집합 매칭 (단어 배열 choices에 적합)
                if not _matched:
                    _matched = _rp_writing_to_label(_ch, rp_sheet_data, _ko)
                if _matched:
                    _L, _is_ex_entry, _n = _matched
                    if _is_ex_entry:
                        _pair_sheet_header[_pi] = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 Ex{str(_n).zfill(2)}"
                    else:
                        _pair_sheet_header[_pi] = f"\ub9ac\ub529\ud30c\uc6cc {_L}\uac15 {str(_n).zfill(2)}"

        # 영작 헤더 목록 생성 — writing_kor의 q_num + source 정보를 활용
        # 과 번호 추적: "본문N" q_num이 리셋되면 다음 과로 전환
        writing_headers = []
        prev_qnum = None
        lesson_idx = 0  # 현재 과 인덱스 (0-based)
        lesson_labels = []  # scope에서 추출한 과 목록

        # scope에서 과 목록 추출 — 교과서 source를 찾을 때까지 스캔
        # (정렬 후 리딩파워 등 비교과서 source가 앞에 오면 첫 source만 보고 break하면
        #  lesson_labels가 비어 교과서 본문N 헤더가 "본문N" 그대로 나와 scope 필터에서 제외됨)
        for kor_item in writing_kor:
            if not isinstance(kor_item, dict):
                continue
            source = kor_item.get("source", "")
            scope_match = re.search(r"\(([^)]+)\)", _nfc(source))
            if not scope_match:
                continue
            scope = scope_match.group(1)
            # "교과서1,2과,SL" or "미래엔김3과" → ["1과", "2과", "SL"]
            m_lesson = re.search(r"교과(?:서)?\s*([\d,]+)\s*과", scope)
            if not m_lesson:
                m_lesson = re.search(r"(?:미래엔|능률|YBM|동아|비상|금성|천재)\S*?([\d,]+)\s*과", scope, re.IGNORECASE)
            if m_lesson:
                raw = m_lesson.group(1)
                lesson_labels = [f"{l.strip()}과" for l in raw.split(",")]
                if "SL" in scope:
                    lesson_labels.append("SL")
                break  # 교과서 발견 — 종료
            # SL 전용 교과서
            if "SL" in scope and not m_lesson:
                lesson_labels = ["SL"]
                break
            # 비교과서 source(리딩파워/모의고사 등) → 다음 스토리 계속 스캔

        prev_본문_num = (0, 0)  # (주번호, 부번호) — "본문3-1" 등 하위번호 대응
        # 복합 scope용 exam_index 추적 (source별)
        w_exam_idx = {}  # source -> exam_index
        w_prev_q = {}    # source -> 이전 q_num 숫자
        # source별 available (workbook scope에 속한 시험만 매핑 대상으로)
        w_available = {}  # source -> _build_scope_assigner 결과
        # 올포 강별 본문 카운터
        # 리딩파워 영작 헤더 매핑용 (문장배열 헤더 공유)
        _rp_arr_hdrs = None  # {src_nfc: [hdr1, hdr2, ...]}
        _rp_w_idx = {}       # src_nfc -> 다음 사용할 인덱스
        _rp_w_seen = {}      # (src_nfc, q_num) -> 할당된 인덱스

        w_olpo_counters = {}  # (src, lecture) -> 카운터
        w_olpo_prev_qnum = {}  # (src, lecture) -> 이전 q_num (새 지문 감지용)
        # 마더텅 등 yy/mm 없는 scope용: page_off 기반 지문 경계 감지 + source별 카운터
        w_src_counter = {}   # src -> 지문 카운터 (마더텅 본문N 폴백용)
        w_mt_total = {}      # src -> 마더텅 전체 지문 순번 (YYMMQQ 매핑 조회용)
        w_prev_pageoff = {}  # src -> 직전 page_off (지문 경계 감지)
        for i, kor_item in enumerate(writing_kor):
            if isinstance(kor_item, dict):
                q_num = kor_item.get("q_num", "")
                source = kor_item.get("source", "")
                item_lecture = kor_item.get("lecture", 0)
                item_page_off = kor_item.get("page_off", -1)
                src_nfc = _nfc(source)
                is_olpo_src = ("올림포스독해기본" in src_nfc or "올포" in src_nfc)

                # 워크북에 박힌 6자리 출처코드(YYMMQQ)가 있으면 최우선 사용 — 가짜번호 방지.
                _ec_kor = kor_item.get("exam_code", "")
                if _ec_kor:
                    # 올포 워크북: xlsx 매핑으로 "올포 N강 본문M" 라벨로 변환
                    _hdr_kor = _ec_kor
                    if olpo_lecture_map and is_olpo_src:
                        from engines.final.olpo_mapper import code_to_olpo_header
                        _olpo_h = code_to_olpo_header(_ec_kor, olpo_lecture_map)
                        if _olpo_h:
                            _hdr_kor = _olpo_h
                    if _hdr_kor != prev_qnum:
                        writing_headers.append({"header": _hdr_kor, "start_idx": i})
                        prev_qnum = _hdr_kor
                    continue

                # 고3 사전 변환 헤더가 있으면 즉시 사용
                g3_hdr = kor_item.get("_g3_header", "")
                if g3_hdr:
                    if g3_hdr != prev_qnum:
                        writing_headers.append({"header": g3_hdr, "start_idx": i})
                        prev_qnum = g3_hdr
                    continue

                # 마더텅 등 non-mock scope + 2-digit q_num: page_off 경계 감지로 새 헤더 강제 emit
                # (같은 "20"이 연속되더라도 page_off이 바뀌면 새 지문)
                _scope_match_mt = re.search(r"\(([^)]+)\)", src_nfc)
                _scope_txt_mt = _scope_match_mt.group(1) if _scope_match_mt else ""
                _mt_no_yymm = (q_num and q_num[0].isdigit() and not q_num.startswith("본문")
                               and not re.search(r"\d{2}년\s*\d{1,2}월|모의고사", _scope_txt_mt)
                               and not is_olpo_src and item_page_off >= 0)
                _force_emit_mt = False
                if _mt_no_yymm and re.match(r"^\d{1,2}(?:[~\-]\d{1,2})?$", q_num):
                    _prev_po = w_prev_pageoff.get(src_nfc, -2)
                    if _prev_po != item_page_off:
                        _force_emit_mt = True
                        w_prev_pageoff[src_nfc] = item_page_off
                # 마더텅 q_num="" 케이스: page_off 경계에서 강제 emit
                # (원고에 지문 번호 헤더가 없는 영작 블록도 별도 헤더로 분리)
                elif (not q_num and "\ub9c8\ub354\ud145" in _scope_txt_mt
                      and not is_olpo_src and item_page_off >= 0):
                    _prev_po = w_prev_pageoff.get(src_nfc, -2)
                    if _prev_po != item_page_off:
                        _force_emit_mt = True
                        w_prev_pageoff[src_nfc] = item_page_off

                # 딥러닝: 같은 q_num="본문6"이라도 _dl_lesson 변경 시 새 헤더 emit
                _dl_lesson_chk = kor_item.get("_dl_lesson") if kor_item else None
                _dl_force_emit = False
                if _dl_lesson_chk:
                    _last_dl = (writing_kor[i-1].get("_dl_lesson") if i > 0 and isinstance(writing_kor[i-1], dict) else None)
                    if _last_dl != _dl_lesson_chk:
                        _dl_force_emit = True
                if (q_num and q_num != prev_qnum) or _force_emit_mt or _dl_force_emit:
                    scope_match = re.search(r"\(([^)]+)\)", src_nfc)
                    scope = scope_match.group(1) if scope_match else ""

                    # 마더텅 전체 지문 순번 추적 (YYMMQQ 매핑용): 지문 경계마다 증가
                    _is_mt_w = "\ub9c8\ub354\ud145" in scope
                    if _is_mt_w:
                        # mt_seq_map이 있으면 원고 전체 기준 순번을 우선 사용
                        # (영작 문제 없는 지문 페이지도 포함된 정확한 순번)
                        _mapped_seq = _mt_seq_lookup(mt_seq_map, src_nfc, item_page_off)
                        if _mapped_seq:
                            w_mt_total[src_nfc] = _mapped_seq
                        else:
                            w_mt_total[src_nfc] = w_mt_total.get(src_nfc, 0) + 1

                    # 리딩파워 영작: source별 문장배열 헤더 맵을 활용해 동일 강·번호로 매핑
                    # (파일명만 보고 Ex/일반을 결정하면 워크북01/워크북03처럼 내용이 반대인 경우 오매핑)
                    if _is_rp_source(src_nfc):
                        # source별 문장배열 헤더 리스트 (한 번만 구축)
                        if _rp_arr_hdrs is None:
                            _rp_arr_hdrs = {}
                            for _ab in (vol1_sentence_blocks or []):
                                _asrc = _nfc(_ab.get("source", ""))
                                _rp_arr_hdrs.setdefault(_asrc, []).append((_ab.get("header") or "").strip())
                        _arr_list = _rp_arr_hdrs.get(src_nfc, [])
                        # 지문 단위 인덱싱: (src, page_off, unit_override, q_num) 키
                        # 같은 스토리(page_off)에 여러 Unit이 혼합된 경우 (예: {Unit 9 emxample 1}, {Unit 10 emxample 1}),
                        # lecture_override가 Unit 구분자 역할. 같은 q_num 반복이어도 다른 Unit이면 새 지문.
                        _unit_ov = kor_item.get("lecture_override")
                        _wi_key = (src_nfc, item_page_off, _unit_ov, q_num)
                        if _wi_key not in _rp_w_seen:
                            _cur_idx = _rp_w_idx.get(src_nfc, 0)
                            _rp_w_seen[_wi_key] = _cur_idx
                            _rp_w_idx[src_nfc] = _cur_idx + 1
                        _arr_idx = _rp_w_seen[_wi_key]
                        header = None
                        if _arr_list and _arr_idx < len(_arr_list):
                            header = _arr_list[_arr_idx]
                        # 2차 폴백: pair choices(영어)를 시트 데이터와 매칭해 실제 강/번호 도출
                        # (광문2처럼 워크북 파일명/내용 불일치로 _arr_list가 부족한 경우에 유효)
                        if not header and _pair_sheet_header:
                            _pi_for_kor = _kor_to_pair_idx.get(i, i) if _kor_to_pair_idx else i
                            _sheet_hdr = _pair_sheet_header.get(_pi_for_kor)
                            if _sheet_hdr:
                                header = _sheet_hdr
                        # 최종 폴백: 원본 q_num + lecture 조합
                        if not header:
                            eff_lec = kor_item.get("lecture_override", item_lecture) or item_lecture
                            if eff_lec and eff_lec > 0 and q_num:
                                if q_num.startswith("Ex"):
                                    header = f"\ub9ac\ub529\ud30c\uc6cc {eff_lec}\uac15 {q_num}"
                                elif q_num.isdigit():
                                    # _arr_list에 Ex가 있고 파일명에 "Example"이 있으면 Ex로 해석
                                    # (원고가 [1][2]만 있어도 Example 워크북임을 Ex 헤더로 표시)
                                    # 아니면 일반 번호로 해석 (광문2 워크북01 케이스: 파일명은 Example이지만 _arr_list는 일반 번호만)
                                    _has_ex_in_arr = any("Ex" in (h or "") for h in _arr_list) if _arr_list else False
                                    if _has_ex_in_arr and "Example" in src_nfc:
                                        header = f"\ub9ac\ub529\ud30c\uc6cc {eff_lec}\uac15 Ex{q_num.zfill(2)}"
                                    else:
                                        header = f"\ub9ac\ub529\ud30c\uc6cc {eff_lec}\uac15 {q_num.zfill(2)}"
                        if header:
                            _last_hdr = writing_headers[-1]["header"] if writing_headers else None
                            if _last_hdr != header and (not scope_exams or _is_in_scope(header, scope_exams)):
                                writing_headers.append({"header": header, "start_idx": i})
                            prev_qnum = q_num
                            continue

                    # 올포 케이스: q_num 섹션 라벨 우선, 숫자면 본문N, 아니면 카운터 폴백
                    if is_olpo_src and item_lecture > 0:
                        olp_lbl = kor_item.get("olpo_label", "")
                        # q_num 기반 직접 매핑 (olp_lbl 관계없이 일관 처리)
                        if q_num == "\ubd84\uc11d":
                            header = f"\uc62c\ud3ec {item_lecture}\uac15 \ubd84\uc11d"
                        elif q_num in ("\uc11c\uc220\ud615", "\ub17c\uc220\ud615"):
                            header = f"\uc62c\ud3ec {item_lecture}\uac15 {q_num}"
                        elif q_num and q_num.isdigit():
                            header = f"\uc62c\ud3ec {item_lecture}\uac15 \ubcf8\ubb38{int(q_num)}"
                        elif olp_lbl:
                            header = f"\uc62c\ud3ec {item_lecture}\uac15 {olp_lbl}"
                        else:
                            key = (source, item_lecture)
                            if w_olpo_prev_qnum.get(key) != q_num:
                                w_olpo_counters[key] = w_olpo_counters.get(key, 0) + 1
                                w_olpo_prev_qnum[key] = q_num
                            m_count = w_olpo_counters[key]
                            header = f"올포 {item_lecture}강 본문{m_count}"
                        # 중복 헤더 방지: 이전 추가된 헤더와 동일하면 스킵
                        _last_hdr = writing_headers[-1]["header"] if writing_headers else None
                        if _last_hdr != header and (not scope_exams or _is_in_scope(header, scope_exams)):
                            writing_headers.append({"header": header, "start_idx": i})
                        prev_qnum = q_num
                        continue

                    # 본문N 리셋 감지: 본문 번호가 감소하면 다음 과
                    lesson_label = None
                    # 딥러닝 영작 후처리에서 부여된 lesson hint 우선
                    _dl_lesson = kor_item.get("_dl_lesson") if kor_item else None
                    if _dl_lesson:
                        lesson_label = f"{_dl_lesson}과"
                    if q_num.startswith("본문"):
                        # "본문3-1" 등 하위번호 대응: (주번호, 부번호) 튜플로 비교.
                        # 같은 과 내 본문3-1 → 본문3-2는 과 증가가 아니며, 본문5 → 본문1만 다음 과.
                        _qn = q_num.replace("본문", "")
                        _mn = re.match(r"(\d+)(?:-(\d+))?", _qn)
                        cur_num = (int(_mn.group(1)), int(_mn.group(2) or 0)) if _mn else (0, 0)
                        if cur_num <= prev_본문_num and prev_본문_num > (0, 0):
                            lesson_idx += 1
                        prev_본문_num = cur_num
                        if not lesson_label and lesson_labels and lesson_idx < len(lesson_labels):
                            lesson_label = lesson_labels[lesson_idx]
                    elif q_num in ("FR", "RM"):
                        # Further Reading / Read More는 직전 본문과 같은 과 — 과 번호만 계산
                        if lesson_labels and lesson_idx < len(lesson_labels):
                            lesson_label = lesson_labels[lesson_idx]
                    elif not q_num or not q_num[0].isdigit():
                        # SL 등 비숫자 q_num, 또는 q_num 빈 경우 (마더텅 force emit)
                        pass
                    else:
                        # 숫자 q_num (모의고사 등) — 본문 카운터 리셋
                        prev_본문_num = (0, 0)
                        # 복합 scope: q_num 리셋 감지
                        if source not in w_exam_idx:
                            w_exam_idx[source] = 0
                            w_prev_q[source] = 0
                        cur_q_num = int(re.match(r"(\d+)", q_num).group(1)) if re.match(r"(\d+)", q_num) else 0
                        if cur_q_num < w_prev_q[source] and w_prev_q[source] > 0:
                            w_exam_idx[source] += 1
                        w_prev_q[source] = cur_q_num

                    # scope_exams 직접 매칭 (우선)
                    # source별 available을 사용해 workbook scope의 시험에만 q_num을 매핑
                    # (전역 first-match 시 25-3 q=39이 24-3 q=39에 잘못 할당되는 버그 방지)
                    direct = None
                    if scope_exams and q_num and q_num[0].isdigit() and not q_num.startswith("본문"):
                        if source not in w_available:
                            w_available[source] = _build_scope_assigner(scope_exams, scope)
                        avail = w_available[source]
                        if avail:
                            direct = _q_num_to_header_by_scope(q_num, scope_exams, scope, available=avail)
                        else:
                            # available 비어있으면 전역 scope_exams로 폴백 (고3 분석편 등 복합 scope 호환)
                            direct = _q_num_to_header_by_scope(q_num, scope_exams, scope)
                    if direct:
                        header = direct
                    else:
                        exam_idx = w_exam_idx.get(source, 0)
                        header = _writing_q_to_header(scope, q_num, lesson_label=lesson_label)
                        # 숫자 q_num → 모의고사 YYMMQQ 변환 (교과서 scope는 제외)
                        _is_mock_scope = bool(re.search(r"\d{2}년\s*\d{1,2}월|모의고사", scope))
                        if q_num and q_num[0].isdigit() and not q_num.startswith("본문") and _is_mock_scope:
                            header = _q_num_to_header(scope, q_num, exam_index=exam_idx)
                        # 변환 실패(마더텅 등 yy/mm 없음): 매핑 우선, 폴백 source 기반 헤더
                        elif (q_num and q_num[0].isdigit() and not q_num.startswith("본문")
                              and re.match(r"^\d{1,2}(?:[~\-]\d{1,2})?$", header)
                              and not is_olpo_src):
                            _mapped = _mt_lookup(scope, w_mt_total.get(src_nfc, 0)) if _is_mt_w else None
                            if _mapped:
                                header = _mapped
                            else:
                                w_src_counter[src_nfc] = w_src_counter.get(src_nfc, 0) + 1
                                header = _scope_to_header(scope, w_src_counter[src_nfc])
                        # q_num 빈 마더텅 지문: mt_seq_map으로 찾은 seq로 YYMMQQ 직접 매핑
                        elif (not q_num and _is_mt_w and not is_olpo_src):
                            _mapped = _mt_lookup(scope, w_mt_total.get(src_nfc, 0))
                            if _mapped:
                                header = _mapped
                    # 딥러닝 영작 라벨 변환: "교과서N과 본문6" → "교과서N과 딥러닝"
                    # _dl_lesson이 설정된 항목은 딥러닝 워크북 출처이므로 헤더 라벨만 변경한다.
                    if header and _dl_lesson:
                        _dl_hdr_m = re.match(r"^교과서(\d+)과\s+본문\d+$", header)
                        if _dl_hdr_m:
                            header = f"교과서{_dl_hdr_m.group(1)}과 딥러닝"
                    # scope 필터링
                    if header and (not scope_exams or _is_in_scope(header, scope_exams)):
                        # 교과서 RM/FR 허용 과 필터 (시험범위 시트 (N과는 Read More도 포함) 기반)
                        _rm_filter_pass = True
                        if textbook_rm_lessons is not None and q_num in ("FR", "RM"):
                            _rm_filter_pass = _passes_textbook_rm_filter(header, textbook_rm_lessons)
                        # 이전 헤더와 동일하면 스킵 (page_off 경계로 force emit 됐지만 동일 헤더일 때)
                        _last_hdr = writing_headers[-1]["header"] if writing_headers else None
                        if _last_hdr != header and _rm_filter_pass:
                            writing_headers.append({"header": header, "start_idx": i})
                    prev_qnum = q_num

        if writing_headers:
            # writing_kor 기준 start_idx를 pairs 기준 index로 변환
            # (2강 01처럼 view가 kor보다 많은 케이스에서 view-only pair가 중간에 생기면
            #  실제 pair 위치가 writing_kor index보다 뒤로 밀리므로 매핑 필요)
            for _h in writing_headers:
                _si = _h.get("start_idx", 0)
                _h["start_idx"] = _kor_to_pair_idx.get(_si, _si)
            vol2["영작_헤더_상세"] = writing_headers

    return vol2


# ── 고3 전용 헬퍼 함수들 ──────────────────────────────────────────────


def _build_lecture_map(stories, selected_lectures=None):
    """스토리의 source_file + pageOff로 강 번호 매핑 구축.

    각 분석편 파일 내 스토리를 pageOff 순으로 보면서
    문장배열 스토리(C1_문장 배열 또는 문장 배열 그랩)가 등장하는 순간을
    새 강 시작으로 간주해 파일명에서 파싱한 강 리스트와 순서 매핑.
    강당 페이지 수가 다르더라도 스토리 그룹 카운트 기반이라 안전.

    Returns:
        dict: {(source_file, page_off): "강번호", ...}
    """
    from engines.final.scope_parser import parse_lectures_from_filename
    from collections import defaultdict

    # 파일별 강 리스트 구축
    file_lectures = {}
    for story in stories:
        src = story.get("source_file", "")
        if src and src not in file_lectures:
            file_lectures[src] = parse_lectures_from_filename(src)

    # 파일별 스토리를 pageOff 순으로 그룹핑
    stories_by_file = defaultdict(list)
    for story in stories:
        src = story.get("source_file", "")
        po = story.get("pageOff", -1)
        if not src or po < 0:
            continue
        stories_by_file[src].append(story)

    sentence_styles = {"\ubb38\uc7a5 \ubc30\uc5f4 \uadf8\ub7a9", "C1_\ubb38\uc7a5 \ubc30\uc5f4"}

    lecture_map = {}
    for src, file_stories in stories_by_file.items():
        lectures = file_lectures.get(src, [])
        if not lectures:
            continue

        file_stories.sort(key=lambda s: s.get("pageOff", 0))

        # 단일 강/테스트 파일: 모든 스토리를 해당 강에 매핑
        if len(lectures) == 1:
            single_lec = lectures[0]
            for story in file_stories:
                po = story.get("pageOff", -1)
                lecture_map[(src, po)] = single_lec
            continue

        # 스토리 그룹 카운트: 문장배열 스타일이 나오면 새 강 시작
        group_idx = -1
        for story in file_stories:
            paras = story.get("paras", [])
            styles_in_story = set(p.get("s", "") for p in paras if p.get("s"))
            if styles_in_story & sentence_styles:
                group_idx += 1
            if 0 <= group_idx < len(lectures):
                po = story.get("pageOff", -1)
                lecture_map[(src, po)] = lectures[group_idx]

    return lecture_map


def _is_textbook_source(src):
    """교과서 분석편 파일인지 판별 (파일명에 'N과' 포함)."""
    return bool(re.search(r"\d+\s*\uacfc", _nfc(src)))


def _q_num_in_allowed(q_num, allowed):
    """블록 q_num이 허용 목록에 있는지 확인 (0-padding 무시, 문자열 라벨 대소문자 무시)."""
    if not q_num or not allowed:
        return False
    q_stripped = q_num.strip()
    q_lower = q_stripped.lower()
    # 문자열 라벨 매칭 (Gateway 등)
    for a in allowed:
        a_s = str(a).strip()
        if not a_s.isdigit() and a_s.lower() == q_lower:
            return True
    # q_num이 "01~02" 또는 "24~25" 같은 범위인 경우: 범위 숫자 중 하나라도 허용 목록에 있으면 OK
    rm = re.match(r"^(\d+)\s*[-~\u2013\u2014]\s*(\d+)$", q_stripped)
    if rm:
        s_n, e_n = int(rm.group(1)), int(rm.group(2))
        try:
            allowed_ints = {int(a) for a in allowed if str(a).isdigit()}
        except ValueError:
            return False
        return any(n in allowed_ints for n in range(s_n, e_n + 1))
    try:
        q_int = int(q_stripped)
    except ValueError:
        return False
    for a in allowed:
        if str(a).isdigit() and int(a) == q_int:
            return True
    return False


def _filter_blocks_by_lecture(blocks, lecture_map, selected_lectures, lecture_details=None):
    """블록 리스트에서 선택된 강에 해당하는 것만 필터링.

    lecture_details가 있으면 강별 지문번호(q_num)까지 매칭.
    예: {"4": ["2","4"]}면 4강에서 q_num이 "2" 또는 "4"(또는 "02","04")인 것만 포함.

    교과서 분석편(파일명에 'N과' 포함)은 강 매핑이 없으므로 범위 체크 없이 유지.
    (교과서 과 범위는 engine.py에서 파일 선택 시 이미 필터됨.)
    """
    result = []
    for b in blocks:
        src = b.get("source", "")
        po = b.get("page_off", -1)
        lec = lecture_map.get((src, po), "")
        if lec in selected_lectures:
            if lecture_details and lec in lecture_details:
                allowed = lecture_details[lec]
                q = b.get("q_num", "")
                # q_num이 있을 때만 지문번호 필터 적용 (없는 블록은 강 매칭만)
                if allowed and q and not _q_num_in_allowed(q, allowed):
                    continue
            result.append(b)
        elif _is_textbook_source(src):
            result.append(b)
    return result


def _filter_items_by_lecture(items, lecture_map, selected_lectures, lecture_details=None):
    """개별 항목 리스트(영작 등)에서 선택된 강에 해당하는 것만 필터링.

    lecture_details가 있으면 지문번호(q_num)까지 매칭.
    """
    result = []
    for item in items:
        src = item.get("source", "")
        po = item.get("page_off", -1)
        lec = lecture_map.get((src, po), "")
        if lec in selected_lectures:
            if lecture_details and lec in lecture_details:
                allowed = lecture_details[lec]
                q = item.get("q_num", "")
                if allowed and q and not _q_num_in_allowed(q, allowed):
                    continue
            result.append(item)
        elif _is_textbook_source(src):
            result.append(item)
    return result


def _convert_vocab_blocks(vocab_blocks, lecture_map, sentence_blocks=None,
                          exclude_gateway=False):
    """고3 빈칸어휘 블록을 중요어휘 좌/우 텍스트로 변환.

    양쪽 모두 영어 텍스트를 사용한다 (한글은 무시).
    왼쪽 = C2_빈칸 어휘 (빈칸이 있는 영어), 오른쪽 = 같은 영어 원문.
    각 지문을 "N강 MM" 헤더로 개별 패시지로 분리.
    한 지문 내 여러 줄은 공백으로 이어붙여 한 문단으로 만든다.
    지문 수는 같은 강의 문장배열 블록 수를 기준으로 균등 분할.
    exclude_gateway=True면 숫자 강의 첫 지문(Gateway)을 제거.

    Returns:
        (vocab_left, vocab_right): 영어(왼)/영어(오) 텍스트
    """
    # 강별 문장배열 블록 수 및 q_num 목록 집계 (순서 유지)
    # 교과서 블록(src에 'N과' 포함)은 별도 집계: tb_src -> [본문 번호]
    blocks_per_lec = {}
    lec_qnum_list = {}  # lec -> [q_num, q_num, ...] (문장배열 추출 순서)
    tb_blocks_per_src = {}  # tb_src -> 본문 개수
    if sentence_blocks:
        for sb in sentence_blocks:
            src = sb.get("source", "")
            po = sb.get("page_off", -1)
            lec = lecture_map.get((src, po), "")
            if lec:
                blocks_per_lec[lec] = blocks_per_lec.get(lec, 0) + 1
                lec_qnum_list.setdefault(lec, []).append(sb.get("q_num", ""))
            elif _is_textbook_source(src):
                tb_blocks_per_src[_nfc(src)] = tb_blocks_per_src.get(_nfc(src), 0) + 1

    # extractor가 빈칸어휘 스토리를 프레임 단위로 분할한 경우를 감지:
    # 같은 lec의 vocab_blocks 개수 >= 문장배열 본문 수이면 블록 한 개 = 본문 하나
    vocab_counts_per_lec = {}
    vocab_counts_per_tb_src = {}
    for b in vocab_blocks:
        bsrc = b.get("source", "")
        bpo = b.get("page_off", -1)
        blec = lecture_map.get((bsrc, bpo), "")
        if blec:
            vocab_counts_per_lec[blec] = vocab_counts_per_lec.get(blec, 0) + 1
        elif _is_textbook_source(bsrc):
            vocab_counts_per_tb_src[_nfc(bsrc)] = vocab_counts_per_tb_src.get(_nfc(bsrc), 0) + 1

    def _fmt_vocab_qnum(q):
        if not q:
            return ""
        if "~" in q or "-" in q:
            return q
        return q.zfill(2)

    def _tb_lesson_of(src_nfc):
        """교과서 src에서 과 번호 추출. '...(영어독해와작문2과)...' → '2'"""
        m = re.search(r"(\d+)\s*\uacfc", src_nfc)
        return m.group(1) if m else ""

    left_parts = []
    right_parts = []
    # 프레임 단위 분할된 vocab_blocks의 lec별 순번 추적
    lec_pre_split_idx = {}
    tb_pre_split_idx = {}
    for b in vocab_blocks:
        src = b.get("source", "")
        po = b.get("page_off", -1)
        lec = lecture_map.get((src, po), "")

        en_lines = b.get("en", [])
        if not en_lines:
            continue

        # 교과서 분석편 블록: 매핑 없음, 파일명에서 과 번호 추출
        is_tb = not lec and _is_textbook_source(src)

        # [고3] 블록에 q_num이 부여돼 있으면 1:1 매핑 — 블록=지문1개. chunk 분할 불필요.
        b_qnum = b.get("q_num", "")
        if not is_tb and b_qnum:
            lec_prefix = f"{lec}강" if lec.isdigit() else (lec or "?")
            passage = " ".join(line.strip() for line in en_lines if line.strip())
            sub_num = _fmt_vocab_qnum(b_qnum)
            header = f"{lec_prefix} {sub_num}"
            left_parts.append(header + "\n" + passage)
            right_parts.append(passage)
            continue

        if is_tb:
            tb_lesson = _tb_lesson_of(_nfc(src))
            total_passages = tb_blocks_per_src.get(_nfc(src), 1)
            pre_split = vocab_counts_per_tb_src.get(_nfc(src), 0) >= total_passages > 0
        else:
            lec_prefix = f"{lec}강" if lec.isdigit() else (lec or "?")
            total_passages = blocks_per_lec.get(lec, 1)
            pre_split = vocab_counts_per_lec.get(lec, 0) >= total_passages > 0

        # 사전 분할된 경우: 이 블록은 본문 1개. 블록 순번으로 passage 인덱스 결정.
        if pre_split:
            n_passages = 1
            if is_tb:
                passage_start_idx = tb_pre_split_idx.get(_nfc(src), 0)
                tb_pre_split_idx[_nfc(src)] = passage_start_idx + 1
            else:
                passage_start_idx = lec_pre_split_idx.get(lec, 0)
                lec_pre_split_idx[lec] = passage_start_idx + 1
        else:
            n_passages = total_passages
            passage_start_idx = 0

        total = len(en_lines)
        chunk_size = max(1, total // n_passages)
        passages = []
        for i in range(n_passages):
            start = i * chunk_size
            end = total if i == n_passages - 1 else start + chunk_size
            chunk = en_lines[start:end]
            if chunk:
                passages.append(" ".join(line.strip() for line in chunk))

        # 교과서 빈칸어휘: "N[X]]]]" 형식(잉여 닫는괄호)을 "N[X]"로 정규화
        # Why: 교과서 indd는 빈칸을 앵커 그래픽 + 고정 `]]]` 패턴으로 조판하나,
        #      extractor → _clean_text가 앵커 `\uFFFC`는 이미 제거했고 `]]]]`만 남은 상태.
        #      타겟 템플릿의 중요어휘(왼) GREP은 `[word]` 일반 포맷 전용이라
        #      `]]]]` 잔여 괄호가 그대로 노출됨.
        # How to apply: 교과서 블록에만 적용. 정상 포맷 `[word]`(단어 2글자 이상)는 무매칭.
        if is_tb:
            passages = [
                re.sub(r'(\d+)\[([A-Za-z])\]{2,}', r'\1[\2]', p)
                for p in passages
            ]

        qnums = lec_qnum_list.get(lec, []) if not is_tb else []
        for pi, passage in enumerate(passages):
            # 사전 분할된 경우 passage_start_idx로 전체 순번 계산
            effective_idx = passage_start_idx + pi
            if is_tb:
                header = f"\uad50\uacfc\uc11c{tb_lesson}\uacfc \ubcf8\ubb38{effective_idx + 1}"
            else:
                if effective_idx < len(qnums) and qnums[effective_idx]:
                    sub_num = _fmt_vocab_qnum(qnums[effective_idx])
                else:
                    sub_num = str(effective_idx + 1).zfill(2)
                header = f"{lec_prefix} {sub_num}"
            left_parts.append(header + "\n" + passage)
            right_parts.append(passage)

    return "\n\n".join(left_parts), "\n\n".join(right_parts)


def _convert_grammar_select(grammar_select_blocks, lecture_map, exclude_gateway=False):
    """고3 어법선택 블록을 어법수정 lines 배열로 변환.

    {01}, {02} 형태의 서브헤더를 "N강 01", "N강 02" 형식으로 변환한다.
    exclude_gateway=True면 숫자 강의 {01} 서브섹션(Gateway)을 본문과 함께 제거한다.

    Returns:
        list: ["3강 01", "passage1", "3강 02", "passage2", ...]
    """
    # 교과서 어휘 선택 섹션과 어법 수정 섹션이 모두 "어휘 선택 그랩" 스타일을 공유해
    # grammar_select_blocks에 중복 블록이 들어온다. 교과서 src별로 page_off가 가장 큰
    # 블록 하나만 사용한다 (어법 수정 섹션 = 문장배열/빈칸어휘 뒤 페이지).
    _tb_best_po = {}
    for _b in grammar_select_blocks:
        _src = _b.get("source", "")
        _po = _b.get("page_off", -1)
        if _is_textbook_source(_src):
            _tb_best_po[_nfc(_src)] = max(_tb_best_po.get(_nfc(_src), -1), _po)

    result = []
    for b in grammar_select_blocks:
        src = b.get("source", "")
        po = b.get("page_off", -1)
        lec = lecture_map.get((src, po), "")
        # 교과서 분석편 블록: 매핑 없음 → 과 번호 추출 후 "교과서N과 본문M" 헤더
        is_tb = not lec and _is_textbook_source(src)
        # 교과서 블록이 여러 개면 page_off가 가장 큰 것만 사용 (어법 수정 섹션)
        if is_tb and po != _tb_best_po.get(_nfc(src)):
            continue
        if is_tb:
            tb_m = re.search(r"(\d+)\s*\uacfc", _nfc(src))
            tb_lesson = tb_m.group(1) if tb_m else ""
            header_prefix = f"\uad50\uacfc\uc11c{tb_lesson}\uacfc"
            tb_counter = 0
            # 교과서 어법 섹션은 첫 본문에 헤더 라인이 없을 수 있음.
            # 블록 첫 줄이 본문이면 '본문1' 헤더를 합성해 주입.
            _first_line = next((l for l in b.get("lines", []) if l.strip()), "")
            if _first_line and not re.match(r'^\d{1,2}$', _first_line.strip()):
                tb_counter = 1
                result.append(f"{header_prefix} \ubcf8\ubb38{tb_counter}")
        else:
            lec_prefix = f"{lec}강" if lec.isdigit() else (lec or "?")
        for line in b.get("lines", []):
            stripped = line.strip()
            # 교과서는 헤더가 중괄호 없이 "01","02"… 형식
            if is_tb and re.match(r'^\d{1,2}$', stripped):
                tb_counter += 1
                result.append(f"{header_prefix} \ubcf8\ubb38{tb_counter}")
                continue
            m = re.match(r'^\{(\d+)(?:([~\-])(\d+))?\}$', stripped)
            m_gw = re.match(r'^\{Gateway\}$', stripped, re.IGNORECASE) if not m else None
            if m_gw and not is_tb:
                result.append(f"{lec_prefix} Gateway")
            elif m:
                first = m.group(1).zfill(2)
                if is_tb:
                    tb_counter += 1
                    result.append(f"{header_prefix} \ubcf8\ubb38{tb_counter}")
                else:
                    if m.group(3):
                        sub_num = f"{first}{m.group(2)}{m.group(3).zfill(2)}"
                    else:
                        sub_num = first
                    result.append(f"{lec_prefix} {sub_num}")
            else:
                if not stripped:
                    continue
                result.append(line)
    return result


def _merge_mock_insert_blocks(insert_blocks, mock_blocks, sentence_blocks=None, log=None):
    """모의고사 통합 워크북에서 추출한 문장삽입 블록을 insert_blocks에 병합.

    mock_blocks: [{"qnum": "38", "paras": [{"s":..., "t":...}, ...],
                   "source_file": "고1_25년_6월_전체(C).indd",
                   "scope_text": "25년6월"}]
    변환: 워크북 워크북05 파일(광문1_워크북05(25년6월)_내지.indd)의 source로 기록하여
           기존 매칭 로직(소스별 exam_idx 등)과 호환.
    """
    existing_keys = set()
    for ib in insert_blocks:
        src = ib.get("source", "")
        qn = ib.get("q_num", "")
        if qn:
            existing_keys.add((src, qn))

    added = 0
    for mb in mock_blocks:
        qnum = mb.get("qnum", "")
        if not qnum:
            continue
        # 이미 같은 qnum 가진 블록이 있으면 스킵 (중복 방지)
        if any(qn == qnum for _, qn in existing_keys):
            continue

        paras = mb.get("paras", [])
        if not paras:
            continue

        # 발문/번호/주어진 문장/본문을 구분하여 저장 — 스타일 힌트가 이미 paras에 있음
        # stepper/JSX가 기대하는 형태로 그대로 전달 (style 이름은 유지하되, text는 정리)
        processed_paras = []
        insert_prompt_ko = "\uc544\ub798 \uc8fc\uc5b4\uc9c4 \ubb38\uc7a5\uc774 \ub4e4\uc5b4\uac08"
        for p in paras:
            style = p.get("s", "")
            txt = (p.get("t", "") or "").strip()
            if not txt:
                continue
            # 문항번호 단독 단락 스킵 (스타일 무관, 범위/브레이스/숫자 모두 제거)
            _txt_nsp = txt.replace(" ", "")
            _qn_nsp = qnum.replace(" ", "")
            # 브레이스 제거 후 비교: "{20}" == "20"
            _txt_stripped = re.sub(r"[\{\}\[\]]", "", _txt_nsp)
            _qn_stripped = re.sub(r"[\{\}\[\]]", "", _qn_nsp)
            if _txt_stripped == _qn_stripped:
                continue
            # "41-42" ↔ "41~42" 동치 처리
            _txt_norm = _txt_stripped.replace("-", "~")
            _qn_norm = _qn_stripped.replace("-", "~")
            if _txt_norm == _qn_norm:
                continue
            # 2자리 숫자 범위/브레이스 숫자 단독 줄 (예: "41~42", "{20}", "[41~42]") 스킵
            if re.match(r"^[\{\[]?\d{1,2}([~\-]\d{1,2})?[\}\]]?$", _txt_nsp):
                continue
            # 연속 마커: "{41}{~42}", "{20}{21}" 등 (extractor 단계에서 분리 실패한 경우)
            if re.match(r"^(?:[\{\[](?:\d+(?:[~\-]\d+)?|~\d+|\ubcf8\ubb38\d+)[\}\]])+$", _txt_nsp):
                continue
            # 교과서 본문 헤더 ("{본문1}", "[본문N]") 스킵
            if re.match(r"^[\{\[]?\ubcf8\ubb38\d+[\}\]]?$", _txt_nsp):
                continue
            if re.match(r"^[\{\[]?(Read\s*More|Further\s*Reading|FR|RM)[\}\]]?$", _txt_nsp, re.IGNORECASE):
                continue
            # 객체 앵커 기호(￼) 단독 단락 스킵
            if txt in ("\uFFFC", ""):
                continue
            # 화살표 심볼 단독 단락 스킵
            if txt in ("\u27A1", "\u2192", "\u21E8", "→", "➡"):
                continue
            # 발문(prompt) 감지
            _is_prompt = (insert_prompt_ko in txt) or ("\uc774\uc5b4\uc9c8 \ubb38\uc7a5\ub4e4\uc758 \uc801\uc808\ud55c \uc21c\uc11c" in txt) or ("\uc8fc\uc5b4\uc9c4 \ubb38\uc7a5\uc774 \ub4e4\uc5b4\uac00\uae30\uc5d0" in txt)
            # 스타일 매핑 (완성본 기준):
            # - 발문: "문장 배열 하단 문제"
            # - 주어진 문장 (원본 style "문장 배열 하단 ", 탭/공백 있는 한 줄): "문장 배열 하단"
            # - 본문/(A)(B): "문장 배열 하단 문제"
            if _is_prompt:
                new_style = "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8 \ubb38\uc81c"
                # 발문 앞 ￼ 탭 제거
                txt = re.sub(r"^\ufffc?\s*", "", txt)
            elif style.strip() == "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8":
                new_style = "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8"
            elif style.strip() == "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8 \ubb38\uc81c":
                new_style = "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8 \ubb38\uc81c"
            else:
                new_style = "\ubb38\uc7a5 \ubc30\uc5f4 \ud558\ub2e8 \ubb38\uc81c"
            processed_paras.append({"style": new_style, "text": txt})

        if not processed_paras:
            continue

        # 워크북 워크북 파일명을 source로 사용 (scope_text 기반 기존 source 찾기)
        # insert_blocks → sentence_blocks 순서로 같은 scope의 워크북 파일명 탐색
        src_candidate = ""
        scope_text = mb.get("scope_text", "")
        _scope_short = scope_text.replace(" ", "") if scope_text else ""
        for ib in insert_blocks:
            _s = ib.get("source", "")
            if _scope_short and _scope_short in _s.replace(" ", ""):
                src_candidate = _s
                break
        if not src_candidate and sentence_blocks:
            for sb in sentence_blocks:
                _s = sb.get("source", "")
                if _scope_short and _scope_short in _s.replace(" ", ""):
                    src_candidate = _s
                    break
        if not src_candidate:
            # scope_text로 가상 파일명 구성 (대응 워크북을 못 찾은 경우)
            src_candidate = f"\ubaa8\uc758\uace0\uc0ac_{scope_text}\ubaa8\uc758({scope_text})_\ub0b4\uc9c0.indd"

        new_block = {
            "source": src_candidate,
            "paras": processed_paras,
            "q_num": qnum,
            "page_off": -1,
            "lecture": 0,
        }
        # 교과서 문장삽입: "교과서N과 본문M" 헤더 사전 지정
        if mb.get("is_textbook"):
            _lnum = mb.get("lesson_num", "")
            if _lnum and qnum.startswith("\ubcf8\ubb38"):
                new_block["_preset_header"] = f"\uad50\uacfc\uc11c{_lnum}\uacfc {qnum}"
            elif _lnum and qnum in ("FR", "RM"):
                new_block["_preset_header"] = f"\uad50\uacfc\uc11c{_lnum}\uacfc {qnum}"
        insert_blocks.append(new_block)
        existing_keys.add((src_candidate, qnum))
        added += 1

    if added > 0 and log:
        log(f"  [\ubb38\uc7a5\uc0bd\uc785] \ud1b5\ud569 \ud30c\uc77c\uc5d0\uc11c {added}\ube14\ub85d \ucd94\uac00")


def _fill_insert_from_sentence(sentence_blocks, insert_blocks, log):
    """모의고사 워크북에 문장삽입 스토리가 없을 때 문장배열 items를 문장삽입 paras로 재사용.

    사용자 지시: "문장배열 아래 문제가 문장삽입이라니까 거기서 가져오면 돼"
    — 25년6월 등 모의고사 워크북은 문장배열 그랩 스타일만 있고 별도 문장삽입 섹션이 없음.
    같은 (source, q_num) 조합의 문장삽입 블록이 없는 경우에 한해 문장배열 items를 복사.

    교과서/올포 워크북은 기존대로 문장삽입 스토리 데이터 사용 (영향 없음).
    """
    # 이미 있는 (source, q_num) 집합 — 중복 생성 방지
    existing_keys = set()
    for ib in insert_blocks:
        key = (ib.get("source", ""), ib.get("q_num", ""))
        existing_keys.add(key)

    added = 0
    for sb in sentence_blocks:
        src = sb.get("source", "")
        q_num = sb.get("q_num", "")
        # 모의고사 워크북만 대상: q_num이 숫자 시작이고 18~45 범위
        if not q_num:
            continue
        m = re.match(r"^(\d+)", q_num)
        if not m:
            continue
        q_val = int(m.group(1))
        if q_val < 18:
            continue  # 교과서 섹션번호는 제외

        key = (src, q_num)
        if key in existing_keys:
            continue  # 이미 insert 데이터 존재

        items = sb.get("items", [])
        if not items:
            continue

        # 문장배열 items → 문장삽입 paras (style="하단 문제"로 매핑)
        paras = [{"style": "\ud558\ub2e8 \ubb38\uc81c", "text": t} for t in items]
        new_block = {
            "source": src,
            "paras": paras,
            "q_num": q_num,
            "page_off": sb.get("page_off", -1),
            "lecture": sb.get("lecture", 0),
        }
        insert_blocks.append(new_block)
        existing_keys.add(key)
        added += 1

    if added > 0 and log:
        log(f"  [문장삽입 폴백] 모의고사 {added}블록을 문장배열에서 복사")


def parse_extracted(extracted_path, vocab_left, vocab_right,
                    school, grade, exam_period, job_dir, log,
                    grammar_word_lines=None, lesson_block_counts=None,
                    sl_section_headers=None, selected_lectures=None,
                    allowed_olpo_lectures=None, mock_insert_blocks=None,
                    exclude_gateway=False, textbook_lessons=None,
                    textbook_raw="", gdrive_content_base="",
                    lecture_details=None, rp_lecture_counts=None,
                    rp_sheet_data=None, textbook_limits=None,
                    olpo_lecture_map=None, textbook_rm_lessons=None):
    """추출 데이터 + 웹 입력을 통합하여 content.json 생성."""
    log("[파싱] 추출 데이터 분류 중...")

    with open(extracted_path, encoding="utf-8") as f:
        extracted = json.load(f)

    stories = extracted.get("stories", [])
    (sentence_blocks, insert_blocks, grammar_blocks, writing_kor, writing_view,
     vocab_blocks, grammar_select_blocks) = _classify_stories(stories)

    # 모의고사 통합 워크북에서 추출한 문장삽입 블록을 insert_blocks에 병합
    # (사용자 지정 출처: "고1_25년_6월_전체(C).indd" 등 통합 파일)
    if mock_insert_blocks and grade in ("\uace01", "\uace02"):
        _merge_mock_insert_blocks(insert_blocks, mock_insert_blocks,
                                  sentence_blocks=sentence_blocks, log=log)

    log(f"  문장배열: {len(sentence_blocks)}개 블록 ({sum(len(b['items']) for b in sentence_blocks)}줄)")
    log(f"  문장삽입: {len(insert_blocks)}개 블록")
    log(f"  어법수정(A1): {len(grammar_blocks)}개 블록 ({sum(len(b['lines']) for b in grammar_blocks)}줄)")
    log(f"  영작 한글: {len(writing_kor)}줄, 보기: {len(writing_view)}줄")
    if vocab_blocks:
        log(f"  빈칸어휘: {len(vocab_blocks)}개 블록")
    if grammar_select_blocks:
        log(f"  어법선택: {len(grammar_select_blocks)}개 블록 ({sum(len(b['lines']) for b in grammar_select_blocks)}줄)")

    # 딥러닝 영작 후처리: 마커 없이 들어온 영작 항목들에 대해 sentence_blocks의
    # passage_label("본문N@과M")을 활용해 lesson을 추론하고 q_num="본문N" 부여.
    _assign_deeplearning_writing_lesson(sentence_blocks, writing_kor, writing_view, log)

    # 딥러닝(본문N@과M) 라벨 충돌 제거: 동일 본문 번호를 다른 워크북에서 일반 "본문N"으로 추출했다면,
    # InDesign의 잔존(ghost) 단락이 가져온 잘못된 콘텐츠일 가능성이 높다 (워크북01의 `06` 섹션 등).
    # 딥러닝 워크북이 실제 본문 콘텐츠를 제공하므로 비-딥러닝 소스의 동일 본문 라벨 블록을 제거한다.
    _dedupe_deeplearning_body_labels(sentence_blocks, insert_blocks, log)

    # ── 고3 전용: 강 번호 매핑 + 데이터 변환 ──
    is_g3 = (grade == "고3")
    if is_g3:
        # 강 번호 매핑: 파일명에서 강 목록 추출 → pageOff 기반 매핑
        from engines.final.scope_parser import parse_lectures_from_filename
        _lecture_map = _build_lecture_map(stories, selected_lectures)
        log(f"  [고3] 강 매핑: {_lecture_map}")

        # 강 범위 필터링: 선택된 강에 해당하는 블록만 유지
        if selected_lectures:
            # [중요어휘 준비] 필터 전 sentence_blocks의 강별 q_num 순서를 기록.
            # vocab_blocks에는 q_num이 없으므로, 같은 강에서 같은 순서로 추출된
            # sentence의 q_num을 1:1로 부여한다 (Gateway/01/02/03/04).
            from collections import defaultdict as _dd
            _lec_sb_qnums_orig = _dd(list)
            for _sb in sentence_blocks:
                _src = _sb.get("source", "")
                _po = _sb.get("page_off", -1)
                _lec = _lecture_map.get((_src, _po), "")
                if _lec:
                    _lec_sb_qnums_orig[_lec].append(_sb.get("q_num", ""))
            _lec_vb_idx = _dd(int)
            for _vb in vocab_blocks:
                _src = _vb.get("source", "")
                _po = _vb.get("page_off", -1)
                _lec = _lecture_map.get((_src, _po), "")
                if _lec:
                    _idx = _lec_vb_idx[_lec]
                    _lec_vb_idx[_lec] += 1
                    _qnums = _lec_sb_qnums_orig.get(_lec, [])
                    if _idx < len(_qnums) and _qnums[_idx]:
                        _vb["q_num"] = _qnums[_idx]

            sentence_blocks = _filter_blocks_by_lecture(
                sentence_blocks, _lecture_map, selected_lectures, lecture_details)
            writing_kor = _filter_items_by_lecture(
                writing_kor, _lecture_map, selected_lectures, lecture_details)
            writing_view = _filter_items_by_lecture(
                writing_view, _lecture_map, selected_lectures, lecture_details)

            vocab_blocks = _filter_blocks_by_lecture(
                vocab_blocks, _lecture_map, selected_lectures, lecture_details)
            # 중요어휘는 sentence와 1:1 매칭돼야 하므로 q_num이 없는 블록은 제거
            # (교과서 블록은 매핑 없이 쓰므로 예외 유지)
            if lecture_details:
                vocab_blocks = [
                    _vb for _vb in vocab_blocks
                    if _vb.get("q_num", "") or _is_textbook_source(_vb.get("source", ""))
                ]

            grammar_select_blocks = _filter_blocks_by_lecture(
                grammar_select_blocks, _lecture_map, selected_lectures, lecture_details)
            log(f"  [고3] 필터 후: 문장배열={len(sentence_blocks)}, "
                f"빈칸어휘={len(vocab_blocks)}, 어법선택={len(grammar_select_blocks)}")
            if lecture_details:
                _preview = ", ".join(
                    f"{k}({','.join(v) if v else '-'})" for k, v in sorted(
                        lecture_details.items(),
                        key=lambda kv: (0, int(kv[0])) if kv[0].isdigit() else (1, kv[0]))
                )
                log(f"  [고3] 강별 지문번호 필터: {_preview}")

        # 고3: lecture_map에 매핑되지 않는 블록 제거 (overflow 등)
        # 교과서 분석편 파일(파일명에 "N과" 포함)은 강 리스트가 없어 매핑이 안 되므로 예외 허용
        def _is_textbook_src(src):
            return bool(re.search(r"\d+\s*\uacfc", _nfc(src)))
        def _has_mapping(item):
            src = item.get("source", "") if isinstance(item, dict) else ""
            po = item.get("page_off", -1) if isinstance(item, dict) else -1
            if _lecture_map.get((src, po), ""):
                return True
            # 교과서 파일은 map 없어도 유지
            return _is_textbook_src(src)

        _sb_before = len(sentence_blocks)
        sentence_blocks = [b for b in sentence_blocks if _has_mapping(b)]
        writing_kor = [b for b in writing_kor if _has_mapping(b)]
        writing_view = [b for b in writing_view if _has_mapping(b)]
        vocab_blocks = [b for b in vocab_blocks if _has_mapping(b)]
        grammar_select_blocks = [b for b in grammar_select_blocks if _has_mapping(b)]
        _sb_removed = _sb_before - len(sentence_blocks)
        if _sb_removed > 0:
            log(f"  [고3] 매핑 없는 블록 제거: 문장배열 {_sb_removed}개")

        # Gateway 제외: 각 강의 q_num "01"인 블록 제거 (test 항목은 제외 안 함)
        # Gateway 제외 필터 비활성화:
        # FINALEDGE 분석편 .indd를 확인한 결과, Gateway 전용 섹션/라벨이 존재하지 않고
        # {01}~{04}는 모두 본문1~4에 해당한다. q_num=="01"을 Gateway로 간주해 제거하면
        # 본문1이 누락되므로 현재 데이터셋에서는 필터를 적용하지 않는다.
        if exclude_gateway:
            log("  [고3] Gateway 제외 표기 감지 — 원본에 Gateway 섹션 없음, 필터 생략")

        # vocab_blocks도 강 순서 정렬
        def _vb_sort(b):
            lec = _lecture_map.get((b.get("source",""), b.get("page_off",-1)), "")
            m = re.match(r"(\d+)", lec)
            if m: return (0, int(m.group(1)))
            if lec.startswith("test"): return (1, 0)
            return (2, 0)
        vocab_blocks.sort(key=_vb_sort)

        # 빈칸어휘 → 중요어휘 포맷 변환 (양쪽 다 영어)
        vocab_left, vocab_right = _convert_vocab_blocks(
            vocab_blocks, _lecture_map, sentence_blocks=sentence_blocks,
            exclude_gateway=exclude_gateway)
        log(f"  [고3] 중요어휘: 왼쪽(영어) {len(vocab_left)}자, 오른쪽(영어) {len(vocab_right)}자")

        # 어법선택 → 어법수정 lines 변환
        grammar_word_lines = _convert_grammar_select(
            grammar_select_blocks, _lecture_map,
            exclude_gateway=exclude_gateway)
        log(f"  [고3] 어법수정: {len(grammar_word_lines)}줄 (어법선택에서 변환)")

        # 고3 문장배열 헤더 사전 변환: q_num "01" + lecture_map → "N강 01"
        # q_num이 없는 블록은 해당 강의 마지막 번호+1로 자동 할당
        _lec_max_q = {}  # lec -> max q_num seen
        for sb in sentence_blocks:
            lec = _lecture_map.get((sb.get("source",""), sb.get("page_off",-1)), "")
            q = sb.get("q_num", "")
            if lec and q:
                try:
                    qn = int(re.match(r"(\d+)", q).group(1))
                    _lec_max_q[lec] = max(_lec_max_q.get(lec, 0), qn)
                except Exception:
                    pass
        for sb in sentence_blocks:
            src = sb.get("source", "")
            po = sb.get("page_off", -1)
            lec = _lecture_map.get((src, po), "")
            q = sb.get("q_num", "")
            if lec and q:
                lec_prefix = f"{lec}강" if lec.isdigit() else lec
                sb["_g3_header"] = f"{lec_prefix} {q.zfill(2)}"
            elif lec and not q:
                # q_num이 없는 블록: 해당 강의 다음 번호 할당
                lec_prefix = f"{lec}강" if lec.isdigit() else lec
                next_q = _lec_max_q.get(lec, 0) + 1
                _lec_max_q[lec] = next_q
                sb["_g3_header"] = f"{lec_prefix} {str(next_q).zfill(2)}"

        # 고3 영작 헤더 사전 변환: q_num + lecture_map → "N강 03" (원본 q_num 유지, zfilled)
        # 교과서 블록은 매핑이 없으므로 src별 카운터로 "교과서N과 본문M" 헤더 부여
        def _format_wr_qnum(q):
            if "~" in q or "-" in q:
                return q
            return q.zfill(2)
        _tb_wr_counter = {}  # src_nfc -> 현재까지 부여한 본문 번호
        def _assign_g3_header(item):
            if not isinstance(item, dict):
                return
            src = item.get("source", "")
            po = item.get("page_off", -1)
            lec = _lecture_map.get((src, po), "")
            q = item.get("q_num", "")
            if lec and q:
                lec_prefix = f"{lec}강" if lec.isdigit() else lec
                item["_g3_header"] = f"{lec_prefix} {_format_wr_qnum(q)}"
                return
            if _is_textbook_source(src):
                src_n = _nfc(src)
                m_tb = re.search(r"(\d+)\s*\uacfc", src_n)
                tb_lesson = m_tb.group(1) if m_tb else ""
                # 파이널엣지 교과서 영작 섹션 번호({01},{02},...)를 본문 번호로 매핑
                if q:
                    q_m = re.match(r"(\d+)", q)
                    if q_m:
                        body_num = int(q_m.group(1))
                        item["_g3_header"] = f"\uad50\uacfc\uc11c{tb_lesson}\uacfc \ubcf8\ubb38{body_num}"
                        return
                _tb_wr_counter[src_n] = _tb_wr_counter.get(src_n, 0) + 1
                item["_g3_header"] = f"\uad50\uacfc\uc11c{tb_lesson}\uacfc \ubcf8\ubb38{_tb_wr_counter[src_n]}"
        # writing_kor/writing_view를 src+q_num 순으로 순회하며 헤더 부여
        # (같은 항목 쌍이 일관된 번호를 받도록 동일 로직을 각각 적용)
        for item in writing_kor:
            _assign_g3_header(item)
        _tb_wr_counter.clear()
        for item in writing_view:
            _assign_g3_header(item)

        # 고3 정렬: 강 번호 순서 (3→4→5→6→7→9→11→...→19→test1)
        def _g3_sort_key(item):
            h = item.get("_g3_header", "") if isinstance(item, dict) else ""
            # "N강 Gateway" — 같은 강의 숫자(01~)보다 먼저 배치
            m_gw = re.match(r"(\d+)강\s+Gateway", h, re.IGNORECASE)
            if m_gw:
                return (0, int(m_gw.group(1)), 0)
            m = re.match(r"(\d+)강\s+(\d+)", h)
            if m:
                return (0, int(m.group(1)), int(m.group(2)))
            if h.startswith("test"):
                # "testN Gateway" → 숫자보다 먼저
                if re.search(r"Gateway", h, re.IGNORECASE):
                    return (1, 0, 0)
                m2 = re.search(r"(\d+)$", h)
                return (1, 0, int(m2.group(1)) if m2 else 0)
            return (2, 0, 0)

        sentence_blocks.sort(key=_g3_sort_key)
        writing_kor.sort(key=_g3_sort_key)
        writing_view.sort(key=_g3_sort_key)

        # test 항목 순번 재매핑: 원본 문항번호(03,04,...) → 순차(01,02,...)
        # 문장배열에서 test 항목의 고유 q_num 순서 수집
        _test_qnum_order = []
        for sb in sentence_blocks:
            h = sb.get("_g3_header", "")
            if h.startswith("test"):
                m_tq = re.search(r"\s+(.+)$", h)
                if m_tq:
                    orig = m_tq.group(1)
                    if orig not in _test_qnum_order:
                        _test_qnum_order.append(orig)
        # test: 원본 번호 유지 (재번호 매핑 안 함)
        _test_renum = {}  # 비워둠 — 원본 번호 사용

        # 어법수정(grammar_word_lines)도 강 순서로 정렬
        # 헤더와 본문을 블록 단위로 묶어서 정렬
        if grammar_word_lines:
            gw_blocks = []
            cur_hdr = ""
            cur_lines = []
            for line in grammar_word_lines:
                if re.match(r"^\d+강\s+\d{2}(?:[~\-]\d{2})?$", line) or re.match(r"^test\d+\s+\d{2}(?:[~\-]\d{2})?$", line, re.IGNORECASE):
                    if cur_hdr or cur_lines:
                        gw_blocks.append((cur_hdr, cur_lines))
                    cur_hdr = line
                    cur_lines = []
                else:
                    cur_lines.append(line)
            if cur_hdr or cur_lines:
                gw_blocks.append((cur_hdr, cur_lines))

            def _gw_sort(item):
                h = item[0]
                m = re.match(r"(\d+)강\s+(\d+)", h)
                if m: return (0, int(m.group(1)), int(m.group(2)))
                if h.startswith("test"):
                    m2 = re.search(r"(\d+)$", h)
                    return (1, 0, int(m2.group(1)) if m2 else 0)
                return (2, 0, 0)

            gw_blocks.sort(key=_gw_sort)

            # test 항목: 원본 번호 유지

            grammar_word_lines = []
            for hdr, lines in gw_blocks:
                if hdr:
                    grammar_word_lines.append(hdr)
                grammar_word_lines.extend(lines)

        # 고3: 문장삽입 없음
        insert_blocks = []

    # 시험범위 데이터 가져오기
    scope_exams = None
    if not is_g3:
        try:
            from engines.final.vocab_fetcher import fetch_scope_for_school
            scope_exams = fetch_scope_for_school(school, log=None)
            if scope_exams:
                log(f"  시험범위 필터: {len(scope_exams)}개 시험")
        except Exception:
            pass

    vol1 = _build_vol1(sentence_blocks, insert_blocks, vocab_left, vocab_right,
                       scope_exams=scope_exams,
                       lesson_block_counts=lesson_block_counts,
                       sl_section_headers=sl_section_headers,
                       allowed_olpo_lectures=allowed_olpo_lectures,
                       grade=grade,
                       rp_lecture_counts=rp_lecture_counts,
                       rp_sheet_data=rp_sheet_data,
                       textbook_limits=textbook_limits,
                       olpo_lecture_map=olpo_lecture_map,
                       textbook_rm_lessons=textbook_rm_lessons)

    # Word에서 추출한 어법수정 데이터 → grammar_blocks에 추가 (A1 대신 사용)
    if grammar_word_lines:
        # Word 어법수정은 word_file scope(교과서/모의고사/EBS)를 커버하므로
        # 해당 scope의 A1은 제외, workbook_a1 scope(마더텅 등) A1은 유지하여 병합
        merged_lines = list(grammar_word_lines)
        if not is_g3 and grammar_blocks:
            from engines.final.scope_parser import (
                parse_scope_from_filename as _psf,
                classify_scope as _cls,
                get_grammar_source as _ggs,
            )

            # 1차 패스: 마더텅 블록들을 순회하며 필요한 YYMMQQ 집합 계산
            # (OX 원문 대신 모의고사 Word에서 YYMMQQ 기반으로 본문을 로드)
            _mt_block_seq = {}  # {_gb_src: [YYMMQQ, YYMMQQ, ...]} (순서대로)
            _a1_cnt = {}
            _non_mt_blocks = []  # 마더텅 외 A1 유지 블록
            for gb in grammar_blocks:
                _gb_src = _nfc(gb.get("source", ""))
                _gb_scope = _psf(_gb_src)
                _gb_type = _cls(_gb_scope)
                if _ggs(_gb_type) == "word_file":
                    continue  # Word가 처리하는 scope → A1 스킵
                _a1_cnt[_gb_src] = _a1_cnt.get(_gb_src, 0) + 1
                _block_idx = _a1_cnt[_gb_src]
                if "\ub9c8\ub354\ud145" in _gb_scope:
                    _yq = _mt_lookup(_gb_scope, _block_idx)
                    _mt_block_seq.setdefault(_gb_src, []).append((_block_idx, _yq))
                else:
                    _non_mt_blocks.append((_gb_src, _gb_scope, _block_idx, gb))

            # 마더텅 scope가 있으면 모의고사 Word에서 원고 로드
            _mt_text_map = {}
            if _mt_block_seq:
                _required_yqs = set()
                for _seq_list in _mt_block_seq.values():
                    for _bi, _yq in _seq_list:
                        if _yq:
                            _required_yqs.add(_yq)
                if _required_yqs and gdrive_content_base:
                    try:
                        from engines.final.mothertongue_grammar_loader import (
                            load_mothertongue_grammar_map
                        )
                        _mt_text_map = load_mothertongue_grammar_map(
                            gdrive_content_base,
                            grade,
                            _required_yqs,
                            mt_map=_MT_MAP,
                            mt_section_labels=_MT_SECTION_LABELS,
                            log=log,
                        )
                        log(f"  [마더텅어법] Word 로드: {len(_mt_text_map)}/{len(_required_yqs)}건")
                    except Exception as _e:
                        log(f"  [마더텅어법] 로더 실패: {_e}")

            # 2차 패스: grammar_blocks를 원래 순서대로 순회해 merged_lines 구성
            _mt_src_idx_pos = {}  # {_gb_src: 현재 소비 위치}
            _a1_cnt = {}
            for gb in grammar_blocks:
                _gb_src = _nfc(gb.get("source", ""))
                _gb_scope = _psf(_gb_src)
                _gb_type = _cls(_gb_scope)
                if _ggs(_gb_type) == "word_file":
                    continue
                _a1_cnt[_gb_src] = _a1_cnt.get(_gb_src, 0) + 1
                _block_idx = _a1_cnt[_gb_src]
                if "\ub9c8\ub354\ud145" in _gb_scope:
                    _yq = _mt_lookup(_gb_scope, _block_idx)
                    # 이미 engine의 마더텅 예전 기출/년월 Word 보충으로 merged_lines에 들어간 YYMMQQ는 스킵
                    if _yq and _yq in merged_lines:
                        continue
                    if _yq and _yq in _mt_text_map:
                        # Word에서 로드된 본문 사용 → 헤더는 YYMMQQ, 본문은 Word 텍스트
                        merged_lines.append(_yq)
                        _body = _mt_text_map[_yq]
                        for _ln in _body.split("\n"):
                            _ln = _ln.strip()
                            if _ln:
                                merged_lines.append(_ln)
                    else:
                        # 폴백: YYMMQQ 못 찾으면 해당 지문 건너뛰고 로그 남김
                        _fallback_hdr = _yq or _scope_to_header(_gb_scope, _block_idx)
                        log(f"  [마더텅어법] {_gb_scope} #{_block_idx} ({_fallback_hdr}): Word 본문 미발견 → 건너뜀")
                        # A1 원본(OX)은 사용하지 않음 (사용자 요청 방향)
                        continue
                else:
                    # 마더텅 외 workbook_a1 (올림포스 고2 기출 등): 기존 동작 유지
                    _hdr = _scope_to_header(_gb_scope, _block_idx)
                    merged_lines.append(_hdr)
                    merged_lines.extend(gb.get("lines", []))
        grammar_blocks = [{
            "source": "어법수정 Word" if not is_g3 else "어법선택 추출",
            "lines": merged_lines
        }]
        if not is_g3:
            log(f"  어법수정(Word+A1): {len(merged_lines)}줄")

    # 마더텅 원고 내 지문 순번 맵 (YYMMQQ 매핑용, 영작 없는 지문도 포함)
    mt_seq_map = _build_mt_seq_map(stories)

    vol2 = _build_vol2(grammar_blocks, writing_kor, writing_view,
                       scope_exams=scope_exams,
                       allowed_olpo_lectures=allowed_olpo_lectures,
                       mt_seq_map=mt_seq_map,
                       vol1_sentence_blocks=vol1.get("문장배열", []) if isinstance(vol1, dict) else None,
                       textbook_limits=textbook_limits,
                       rp_sheet_data=rp_sheet_data,
                       olpo_lecture_map=olpo_lecture_map,
                       textbook_rm_lessons=textbook_rm_lessons)

    # Vol1 문장배열의 헤더 목록을 Vol2 영작에 공유
    # 어법수정은 독자 헤더가 있으므로 덮어쓰지 않음
    if is_g3:
        # 고3: 영작_헤더는 영작_헤더_상세에서 추출, 어법_헤더는 어법수정 자체에서 추출
        if vol2.get("영작_헤더_상세"):
            vol2["영작_헤더"] = [h["header"] for h in vol2["영작_헤더_상세"]]
        # 어법_헤더는 _build_vol2에서 이미 설정됨 — vol1 공유 금지
    elif vol1.get("문장배열"):
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

    # 비표준 발문/영문 typo 일괄 정규화 (헤더 제외 본문 텍스트만)
    def _walk_normalize(obj, key=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = _walk_normalize(v, k)
            return obj
        if isinstance(obj, list):
            return [_walk_normalize(v, key) for v in obj]
        if isinstance(obj, str):
            if key in ("header", "source"):
                return obj
            return _normalize_question_text(obj)
        return obj
    _walk_normalize(content.get("vol1"))
    _walk_normalize(content.get("vol2"))

    content_path = os.path.join(job_dir, "content.json")
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    # ===== 자동 검증 =====
    warnings = []
    # Vol1: 문장배열/문장삽입 헤더 일관성
    arr_blocks = vol1.get("문장배열", [])
    ins_blocks = vol1.get("문장삽입", [])
    if arr_blocks and ins_blocks:
        arr_h = [b["header"] for b in arr_blocks]
        ins_h = [b["header"] for b in ins_blocks]
        if len(arr_h) != len(ins_h):
            warnings.append(f"문장배열({len(arr_h)})과 문장삽입({len(ins_h)}) 블록수 불일치")
        for h in arr_h:
            matched = any(h in ih or ih.strip("{}") == h for ih in ins_h)
            if not matched and not any(b["paras"] for b in ins_blocks if b["header"] == h or b["header"] == "{" + h + "}"):
                pass  # 빈 블록은 정상 (동기화 결과)
    # 빈 블록 검사
    empty_arr = [b["header"] for b in arr_blocks if not b.get("items")]
    empty_ins = [b["header"] for b in ins_blocks if not b.get("paras")]
    if empty_arr:
        warnings.append(f"문장배열 빈 블록: {empty_arr}")
    if empty_ins:
        warnings.append(f"문장삽입 빈 블록: {empty_ins}")

    # Vol2: 어법수정 헤더 vs 실제 데이터 일관성
    grammar_lines = vol2.get("어법수정", [])
    grammar_hdrs = vol2.get("어법_헤더", [])
    if grammar_lines and grammar_hdrs:
        actual_hdrs = []
        for line in grammar_lines:
            if (re.match(r"^\d{6}", line) or re.match(r"^교과서", line) or
                    re.match(r"^\d{1,2}과\s", line) or re.match(r"^SL\s", line) or
                    re.match(r"^S\d+과\s", line) or re.match(r"^\d+강(\s|$)", line) or
                    re.match(r"^올포\s+\d+강\s+(본문\d+|분석|서술형|논술형)", line) or
                    re.match(r"^리딩파워\s+\d+강\s+본문\d+", line) or
                    re.match(r"^마더텅\d*\s+본문\d+", line) or
                    re.match(r"^test\d+(\s|$)", line, re.IGNORECASE)):
                actual_hdrs.append(line.strip())
        if len(actual_hdrs) != len(grammar_hdrs):
            warnings.append(f"어법_헤더({len(grammar_hdrs)})와 실제 어법수정 헤더({len(actual_hdrs)}) 불일치")

    # 교과서 SL 일관성 체크
    all_headers_flat = []
    for b in arr_blocks:
        all_headers_flat.append(b["header"])
    for h in grammar_hdrs:
        all_headers_flat.append(h)
    sl_patterns = set()
    for h in all_headers_flat:
        if "SL" in h or re.match(r"^S\d+과", h):
            sl_patterns.add(h.split(" ")[0] if " " in h else h)
    if len(sl_patterns) > 1:
        warnings.append(f"SL 명명 불일치: {sl_patterns}")

    # 중요어휘 좌/우 지문수 일관성 (고3은 오른쪽 헤더 없으므로 스킵)
    if not is_g3:
        left_text = vol1.get("중요어휘_왼", "")
        right_text = vol1.get("중요어휘_오", "")
        if left_text and right_text:
            _vocab_hdr_re = r"^(?:\d{6}|\uc62c\ud3ec\s+\d+\uac15\s+\S+)"
            left_nums = re.findall(_vocab_hdr_re, left_text, re.MULTILINE)
            right_nums = re.findall(_vocab_hdr_re, right_text, re.MULTILINE)
            if set(left_nums) != set(right_nums):
                missing_right = set(left_nums) - set(right_nums)
                missing_left = set(right_nums) - set(left_nums)
                if missing_right:
                    warnings.append(f"중요어휘 오른쪽 누락: {sorted(missing_right)}")
                if missing_left:
                    warnings.append(f"중요어휘 왼쪽 누락: {sorted(missing_left)}")

    if warnings:
        log("[검증 경고]")
        for w in warnings:
            log(f"  - {w}")
        # 검증 경고를 content.json에 저장 (UI에서 표시용)
        content["_validation_warnings"] = warnings
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
    else:
        log("[검증] 통과")

    log(f"[파싱] content.json 생성 완료")
    return content_path
