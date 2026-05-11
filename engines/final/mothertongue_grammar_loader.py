"""파이널 직전보충 — 마더텅 어법수정 Word 로더.

마더텅 워크북 지문의 YYMMQQ 목록을 받아, 각 YYMMQQ에 대응하는
어법수정 원고(문제지 Table[1])를 Word 파일에서 추출해 dict로 반환.

자료 경로:
  1) 최신 모의고사 Word:
     {gdrive_content_base}/모의고사 작업/{grade}/{grade} YY년 M월/*어법수정_문제지.docx
     - 헤더 형식: "N. pPP-no.QQ" (YYMMQQ는 폴더 이름에서 유도)
  2) 예전 기출 Word (해당 YYMM 폴더 없을 때):
     {gdrive_content_base}/모의고사 작업/{grade}/한영{grade} 마더텅 예전 기출/
       {N}강 {섹션라벨}/마더텅{grade}{N}강예전기출_어법수정_문제지.docx
     - 헤더 형식: "N. p{N}강-no.QQ번 YYMMQQ" (헤더에 YYMMQQ가 직접 포함됨)

Google Drive 파일은 네트워크 지연/잠금 문제 때문에 반드시 /tmp로 복사 후 사용.
"""

import os
import re
import subprocess
import time
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _gdrive_copy_local(src, log=None):
    """Google Drive 파일을 /tmp로 안전하게 복사 후 로컬 경로 반환.

    실패 시 None 반환 (호출부에서 스킵 처리).
    extractor._gdrive_safe_copy로 통합 — 6가지 syscall 경로 + 95s 백오프.
    """
    if not src or not os.path.exists(src):
        return None
    # Google Drive 경로 아니면 그대로 리턴
    if not any(tag in src for tag in ("GoogleDrive", "Google Drive", "CloudStorage")):
        return src
    dst = f"/tmp/mt_grammar_{os.getpid()}_{os.path.basename(src)}"
    from engines.final.extractor import _gdrive_safe_copy
    copied, last_err = _gdrive_safe_copy(src, dst, log=log)
    if copied:
        return dst
    if log:
        log(f"  [마더텅어법] 복사 실패 — 마지막 오류: {last_err}")
    return None


def _parse_docx_table1(docx_path, log=None):
    """Word 파일 Table[1](문제 본문)에서 (헤더, 본문) 블록 리스트 추출.

    반환: [(header_text, body_text), ...]
    헤더 row: 좌측 셀 문자열이 숫자로 시작하고 no./p 등 패턴 포함.
    """
    try:
        from docx import Document
    except ImportError as e:
        if log:
            log(f"  [마더텅어법] python-docx 없음: {e}")
        return []
    try:
        doc = Document(docx_path)
    except Exception as e:
        if log:
            log(f"  [마더텅어법] 문서 열기 실패 {os.path.basename(docx_path)}: {e}")
        return []

    if not doc.tables:
        return []
    # Table[1]이 없으면 Table[0] 사용
    table = doc.tables[1] if len(doc.tables) > 1 else doc.tables[0]

    results = []
    cur_hdr = None
    cur_body = []

    for row in table.rows:
        if not row.cells:
            continue
        c0 = row.cells[0].text.strip() if len(row.cells) > 0 else ""
        if not c0:
            continue
        # 헤더 감지: "N." 로 시작하고 no./p 등 지문 마커 포함
        is_hdr = bool(re.match(
            r"^\d+\.\s*(p\d+|p\d+\uac15|L\d+|SL\d*|Special\s*Lesson\s*\d*)",
            c0
        ))
        if is_hdr:
            # 이전 블록 저장
            if cur_hdr and cur_body:
                results.append((cur_hdr, "\n".join(cur_body)))
            cur_hdr = c0
            cur_body = []
        elif cur_hdr:
            cur_body.append(c0)
    if cur_hdr and cur_body:
        results.append((cur_hdr, "\n".join(cur_body)))

    return results


def _extract_yymmqq_from_header(hdr, default_yymm=None):
    """Word 문제지 헤더에서 YYMMQQ 6자리 추출.

    - 예전 기출 형식: "1. p3강-no.4번 190920" → "190920"
    - 최신 모의고사 형식: "1. p2-no.20" + default_yymm("2211") → "221120"
    - 최신 모의고사 범위: "no.41~42" → (default_yymm + "41"만 키로 저장; 호출부에서 개별 사용 시 양쪽 조회)

    반환: YYMMQQ 문자열 (6자리) 또는 None
    """
    hdr = _nfc(hdr)
    # 1) 헤더 끝에 6자리 YYMMQQ가 직접 명시 (예전 기출)
    m = re.search(r"(\d{6})\s*$", hdr)
    if m:
        return m.group(1)
    # 2) no.QQ 추출 후 default_yymm 과 결합 (최신 모의고사)
    if default_yymm:
        m2 = re.search(r"no\.?\s*(\d{1,2})", hdr, re.IGNORECASE)
        if m2:
            qq = m2.group(1).zfill(2)
            return f"{default_yymm}{qq}"
    return None


def _modern_folder_for_yymm(content_base, grade, yymm):
    """{grade} YY년 M월 폴더 경로 탐색. YY=yymm[:2], M=yymm[2:4].

    경로: {content_base}/모의고사 작업/{grade}/{grade} YY년 M월/ (M/MM 변이 모두 매칭)
    """
    if not yymm or len(yymm) != 4:
        return None
    yy = yymm[:2]
    mm = yymm[2:4]
    mm_int = int(mm)
    mock_base = os.path.join(content_base, "\ubaa8\uc758\uace0\uc0ac \uc791\uc5c5", grade)
    if not os.path.isdir(mock_base):
        return None
    # 폴더 후보 (YY년 M월 또는 YY년 MM월)
    for d in os.listdir(mock_base):
        dn = _nfc(d)
        # "고1 25년 10월" 매칭
        if re.search(rf"\b{yy}\ub144\s*0?{mm_int}\uc6d4\b", dn):
            full = os.path.join(mock_base, d)
            if os.path.isdir(full):
                return full
    return None


def _legacy_folder_for_section(content_base, grade, section_num, section_label):
    """예전 기출 폴더 경로 탐색.

    경로: {content_base}/모의고사 작업/{grade}/한영{grade} 마더텅 예전 기출/{N}강 {섹션라벨}/
    """
    mock_base = os.path.join(content_base, "\ubaa8\uc758\uace0\uc0ac \uc791\uc5c5", grade)
    legacy_root = None
    for d in os.listdir(mock_base) if os.path.isdir(mock_base) else []:
        dn = _nfc(d)
        if "\ub9c8\ub354\ud145" in dn and "\uc608\uc804" in dn and "\uae30\ucd9c" in dn:
            legacy_root = os.path.join(mock_base, d)
            break
    if not legacy_root or not os.path.isdir(legacy_root):
        return None
    # "3강 필자의 주장" 폴더
    for d in os.listdir(legacy_root):
        dn = _nfc(d)
        if dn.startswith(f"{section_num}\uac15") and section_label in dn:
            full = os.path.join(legacy_root, d)
            if os.path.isdir(full):
                return full
    return None


def _legacy_docx(section_dir, grade, section_num):
    """예전 기출 섹션 폴더 안의 어법수정 문제지 .docx 경로 반환."""
    if not section_dir or not os.path.isdir(section_dir):
        return None
    # "마더텅고1{N}강예전기출_어법수정_문제지.docx"
    target = f"\ub9c8\ub354\ud145{grade}{section_num}\uac15\uc608\uc804\uae30\ucd9c_\uc5b4\ubc95\uc218\uc815_\ubb38\uc81c\uc9c0.docx"
    # 파일명 공백 허용
    for f in os.listdir(section_dir):
        fn = _nfc(f)
        if fn.startswith("~"):
            continue
        if "\uc5b4\ubc95\uc218\uc815" in fn and "\ubb38\uc81c\uc9c0" in fn and fn.endswith(".docx"):
            return os.path.join(section_dir, f)
    return None


def _modern_docx(folder):
    """최신 모의고사 폴더 안의 어법수정 문제지 .docx 경로 반환."""
    if not folder or not os.path.isdir(folder):
        return None
    for root, dirs, files in os.walk(folder):
        for f in files:
            fn = _nfc(f)
            if fn.startswith("~"):
                continue
            if "\uc5b4\ubc95\uc218\uc815" in fn and "\ubb38\uc81c\uc9c0" in fn and fn.endswith(".docx"):
                # 해설/정답은 제외
                if "\uc815\ub2f5" in fn or "\ud574\uc124" in fn:
                    continue
                return os.path.join(root, f)
    return None


def load_mothertongue_grammar_map(gdrive_content_base, grade, required_yymmqqs,
                                   mt_map=None, mt_section_labels=None, log=None):
    """마더텅 지문의 YYMMQQ 목록을 받아, 각 YYMMQQ에 대응하는 어법수정 원고 반환.

    Args:
        gdrive_content_base: "~/Library/.../내신대비" (틸드 OK)
        grade: "고1" 또는 "고2"
        required_yymmqqs: {"221120", "190920", ...}
        mt_map: {섹션번호: {순번: YYMMQQ}} — 섹션별 포함 관계 역추적용
        mt_section_labels: {섹션번호: "필자의 주장"} — 예전 기출 폴더 이름 조회용
        log: 로그 콜백

    Returns:
        {"221120": "본문 문자열", ...} — 못 찾은 YYMMQQ는 키 없음
    """
    if not required_yymmqqs:
        return {}

    content_base = os.path.expanduser(gdrive_content_base or "")
    if not content_base or not os.path.isdir(content_base):
        if log:
            log(f"  [마더텅어법] content_base 없음: {content_base}")
        return {}

    result = {}

    # YYMM 별로 그룹화 → 최신 폴더 우선 탐색
    by_ym = {}
    for yq in required_yymmqqs:
        if not yq or len(yq) != 6:
            continue
        by_ym.setdefault(yq[:4], set()).add(yq)

    # 1단계: 최신 모의고사 폴더에서 매칭 시도
    missing = set()
    for ym, yqs in by_ym.items():
        folder = _modern_folder_for_yymm(content_base, grade, ym)
        if not folder:
            if log:
                log(f"  [마더텅어법] {grade} {ym[:2]}\ub144{int(ym[2:4])}\uc6d4 폴더 없음 → 예전 기출로 폴백")
            for yq in yqs:
                missing.add(yq)
            continue
        docx_src = _modern_docx(folder)
        if not docx_src:
            if log:
                log(f"  [마더텅어법] {os.path.basename(folder)}: 어법수정 문제지 .docx 없음 → 예전 기출로 폴백")
            for yq in yqs:
                missing.add(yq)
            continue
        # /tmp로 복사
        local = _gdrive_copy_local(docx_src, log=log)
        if not local:
            if log:
                log(f"  [마더텅어법] 복사 실패: {os.path.basename(docx_src)}")
            for yq in yqs:
                missing.add(yq)
            continue
        # 파싱
        blocks = _parse_docx_table1(local, log=log)
        hits = 0
        for hdr, body in blocks:
            yymmqq = _extract_yymmqq_from_header(hdr, default_yymm=ym)
            if not yymmqq:
                continue
            if yymmqq in yqs and yymmqq not in result:
                result[yymmqq] = body
                hits += 1
        if log:
            log(f"  [마더텅어법] 최신 {os.path.basename(folder)}: {hits}/{len(yqs)}개 매칭")
        # 누락된 건 예전 기출로 폴백
        for yq in yqs:
            if yq not in result:
                missing.add(yq)
        # 임시 파일 정리
        try:
            if local != docx_src:
                os.remove(local)
        except Exception:
            pass

    # 2단계: 예전 기출 폴더 탐색 (섹션 단위)
    if missing and mt_map and mt_section_labels:
        # 각 missing YYMMQQ 가 어느 섹션에 속하는지 역추적
        yq_to_sections = {}  # YYMMQQ -> {섹션번호}
        for sect, d in mt_map.items():
            for seq, yq in d.items():
                if yq in missing:
                    yq_to_sections.setdefault(yq, set()).add(sect)
        # 섹션별로 예전 기출 Word 한 번씩만 파싱 (캐시)
        section_blocks = {}
        sections_needed = set()
        for sects in yq_to_sections.values():
            sections_needed |= sects
        for sect in sections_needed:
            label = mt_section_labels.get(sect)
            if not label:
                continue
            sect_dir = _legacy_folder_for_section(content_base, grade, sect, label)
            if not sect_dir:
                if log:
                    log(f"  [마더텅어법] 예전 기출 {sect}강 {label} 폴더 없음")
                continue
            docx_src = _legacy_docx(sect_dir, grade, sect)
            if not docx_src:
                if log:
                    log(f"  [마더텅어법] 예전 기출 {sect}강 문제지 .docx 없음")
                continue
            local = _gdrive_copy_local(docx_src, log=log)
            if not local:
                continue
            blocks = _parse_docx_table1(local, log=log)
            section_blocks[sect] = blocks
            if log:
                log(f"  [마더텅어법] 예전 기출 {sect}강 파싱: {len(blocks)}블록")
            try:
                if local != docx_src:
                    os.remove(local)
            except Exception:
                pass
        # 매칭
        for yq, sects in yq_to_sections.items():
            if yq in result:
                continue
            for sect in sects:
                blocks = section_blocks.get(sect, [])
                for hdr, body in blocks:
                    ext = _extract_yymmqq_from_header(hdr)
                    if ext == yq:
                        result[yq] = body
                        break
                if yq in result:
                    break

    # 누락 로깅
    missing_after = [yq for yq in required_yymmqqs if yq not in result]
    if missing_after and log:
        log(f"  [마더텅어법] 미매칭 {len(missing_after)}건: {sorted(missing_after)[:10]}{' ...' if len(missing_after)>10 else ''}")
    if log:
        log(f"  [마더텅어법] 매칭 완료: {len(result)}/{len(required_yymmqqs)}건")

    return result
