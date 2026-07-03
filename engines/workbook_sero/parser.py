"""세로 워크북 파서.

기존 가로 워크북 parser를 재사용하면서 한 가지 후처리를 추가한다:
한 STEP의 paragraphs[]를 q_num(지문번호) 단위로 분할.

가로 워크북: paragraphs[]를 통째로 하나의 InDesign 스토리에 채워 넣음
세로 워크북: paragraphs를 q_num별로 분할 → 각 문제 사이클의 페이지에 채워야 함

원고 마커 형식:
- 마더텅 강 단위: "[15강 N번 YYMMQQ]"  (한영고1 마더텅 예전 기출)
- 모의고사 단순: "[N]"  (정규 모의고사)
"""

import os
import re
import sys
import unicodedata

# 가로 워크북 parser 모듈 재사용
from engines.workbook.parser import parse_manuscript_folder as _workbook_parse


def _augment_step1_c1_passage(paras):
    """마더텅 step1_c1 원고 본문 도입부 paragraph에 3+ space prefix 추가.

    가로 워크북 processStep1C1은 has3PlusGaps paragraph를 S1_C1_BTM(주어진 문장)으로
    분류하고, 그 다음 (A)(B)(C) paragraph를 S1_C1_BTM_T(하단 지문)로 분류한다.
    그 결과 reference(P22, P36 등)와 동일하게:
      - 상단: 보기 (A)-(F) → S1_C1
      - 하단: 발문 자동 삽입 + 도입부(BTM) + 본문 (A)(B)(C) (BTM_T)

    식별 규칙: 영문 한글미포함 paragraph이고, 다음 비빈 paragraph가 "(A)"로 시작하면
    그 paragraph가 본문 도입부.
    """
    out = []
    for p in paras:
        out.append(p)
    for i in range(len(out) - 1):
        p = out[i]
        text = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        if not text:
            continue
        if not re.match(r'^[A-Za-z]', text):
            continue
        if re.search(r'[가-힣]', text):
            continue
        # 이미 (A)/(B)/... 시작 라인이면 보기/본문 라벨, 도입부 아님
        if re.match(r'^\([A-Z]\)', text):
            continue
        # 다음 비빈 paragraph가 "(A)"로 시작하는지 확인
        for j in range(i + 1, len(out)):
            next_text = (out[j].get("text", "") if isinstance(out[j], dict) else str(out[j])).strip()
            if not next_text:
                continue
            if re.match(r'^\(A\)', next_text):
                # 도입부 확정. trailing 3+ space 추가 (선행 공백은 가로 코드 line 1283에서 자동 제거됨)
                new_p = dict(p)
                new_p["text"] = p.get("text", "") + "   "
                if isinstance(new_p.get("runs"), list) and new_p["runs"]:
                    new_p["runs"] = list(new_p["runs"]) + [{"t": "   ", "ul": False}]
                out[i] = new_p
                return out
            break
    return out


_LESSON_HEADER_PATTERN = re.compile(
    r'^\s*\d+\s*강\s*\d+(?:~\d+)?\s*번(?:\s*\d{6})?\s*(?:\([^)]*\))?\s*$'
)

_ANSWER_HEADER_PATTERNS = [
    re.compile(r'^\s*\[\s*정답\s*\]\s*$'),
    re.compile(r'^\s*【\s*정답\s*】\s*$'),
    re.compile(r'^\s*<\s*정답\s*>\s*$'),
    re.compile(r'^\s*정답\s*및\s*해설\s*$'),
    re.compile(r'^\s*정답\s*:\s*$'),
    re.compile(r'^\s*Answers?\s*:?\s*$', re.I),
]

_ANSWER_LINE_PATTERN = re.compile(
    r'^\s*\d+\s*번\s*[-:].*$'
)


_INSERT_QUESTION_PATTERN = re.compile(
    r'주어진\s*(?:문장|글)'
    r'|들어갈\s*위치'
    r'|이어질\s*순서'
    r'|다음에\s*이어질'
)


def _split_step3_insert_passage(paras):
    """문장삽입 문제: "주어진 문장" 발문 다음 paragraph가 \"주어진 문장\"+본문 형태로
    한 paragraph에 합쳐져 있으면 두 paragraph로 split.

    docx 원본 일부에서 문장삽입 문제의 주어진 문장(따옴표 안)과 본문이 한 paragraph로
    추출되어, 가로 processStep3가 paragraph 전체에 S3_BG 배경 스타일을 적용하는
    문제 해결.

    패턴: ^"..."\\s*[A-Z]...$  →  첫 그룹("...")을 별도 paragraph로 분리.
    """
    out = []
    i = 0
    while i < len(paras):
        p = paras[i]
        text = p.get("text", "") if isinstance(p, dict) else str(p)
        out.append(p)
        if _INSERT_QUESTION_PATTERN.search(text) and i + 1 < len(paras):
            next_p = paras[i + 1]
            next_text = (next_p.get("text", "") if isinstance(next_p, dict) else str(next_p))
            # ^"..."[non-quoted text] 패턴 — 첫 따옴표 쌍을 분리
            m = re.match(r'^\s*("[^"]+")\s*([A-Za-z(].*)$', next_text, re.DOTALL)
            if m:
                first_text = m.group(1)
                rest_text = m.group(2)
                # runs는 정확한 분할이 어려우니 일단 비움 (밑줄은 step3에서 큰 영향 없음)
                out.append({"text": first_text, "runs": []})
                out.append({"text": rest_text, "runs": []})
                i += 2
                continue
        i += 1
    return out


def _strip_step3_lesson_header(paras):
    """첫 단락이 "N강 N번 YYMMQQ" 형태면 제거.

    예: "15강 1번 180940" / "15강 1번 180940 (정답 1개)" / "10강 8번"
    """
    if not paras:
        return paras
    out = []
    removed_first = False
    for p in paras:
        text = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        if not removed_first and _LESSON_HEADER_PATTERN.match(text):
            removed_first = True
            continue
        out.append(p)
    return out


def _strip_step3_answers_aggressive(paras):
    """[정답] 헤더 이후 모든 paragraphs 제거.

    원고 끝에 정답 섹션이 있으면 헤더 기준으로 잘라낸다.
    또한 "N번 - 답" 형태가 연속으로 나오는 구간도 제거.
    """
    if not paras:
        return paras
    # 정답 헤더 찾기
    cut_idx = None
    for i, p in enumerate(paras):
        text = (p.get("text", "") if isinstance(p, dict) else str(p)).strip()
        for pat in _ANSWER_HEADER_PATTERNS:
            if pat.match(text):
                cut_idx = i
                break
        if cut_idx is not None:
            break
    if cut_idx is not None:
        return paras[:cut_idx]
    # 정답 헤더가 없으면 끝쪽에서 "N번 - ..." 연속 라인 제거
    last_keep = len(paras)
    while last_keep > 0:
        text = (paras[last_keep - 1].get("text", "")
                if isinstance(paras[last_keep - 1], dict)
                else str(paras[last_keep - 1])).strip()
        if text == "" or _ANSWER_LINE_PATTERN.match(text):
            last_keep -= 1
        else:
            break
    return paras[:last_keep]


_QNUM_MARKER_PATTERNS = [
    # 대괄호 형식
    # "[15강 14번 171140]" 또는 "[15강 14번]"
    re.compile(r'^\s*\[\s*\d+\s*강\s*(\d+)(?:~(\d+))?\s*번(?:\s*(\d{6}))?\s*\]\s*$'),
    # "[250920]" 6자리 코드만
    re.compile(r'^\s*\[\s*(\d{6})\s*\]\s*$'),
    # "[20]" 또는 "[41~42]" 단순 번호
    re.compile(r'^\s*\[\s*(\d{1,2})(?:~(\d{1,2}))?\s*\]\s*$'),
    # 중괄호
    # "{20}" 또는 "{250920}"  (영작 배열 등)
    re.compile(r'^\s*\{\s*(\d{1,6})(?:~(\d{1,2}))?\s*\}\s*$'),
    # 대괄호 없음
    # "15강 14번 171140" 또는 "15강 14번" 또는 "15강 14번 171140 (정답 N개)"
    re.compile(r'^\s*\d+\s*강\s*(\d+)(?:~(\d+))?\s*번(?:\s*(\d{6}))?\s*(?:\([^)]*\))?\s*$'),
]


def _detect_qnum(text):
    """텍스트가 q_num 마커이면 (q_num, q_num_end, code) 반환, 아니면 None."""
    if not text:
        return None
    txt = text.strip()
    for pat in _QNUM_MARKER_PATTERNS:
        m = pat.match(txt)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 3 and groups[2]:
            # 마더텅 강 단위: q_num, q_num_end, code (6자리)
            return (groups[0], groups[1], groups[2])
        elif len(groups) == 2 or (len(groups) == 3 and not groups[2]):
            g1 = groups[0]
            g2 = groups[1] if len(groups) > 1 else None
            # 6자리면 code, 아니면 q_num
            if g1 and len(g1) == 6:
                return (g1[-2:].lstrip('0') or g1[-2:], None, g1)
            return (g1, g2, None)
    return None


def _split_paragraphs_by_qnum(paragraphs):
    """paragraphs[]를 q_num 마커로 분할.

    Returns:
        [{
            "q_num": "14",
            "q_num_end": None,     # 합본인 경우 "42"
            "code": "171140",      # 있으면 6자리 모의고사 코드
            "paragraphs": [...],   # 마커 다음부터 다음 마커 직전까지 (마커 자체 제외)
        }, ...]
    """
    sections = []
    current = None
    for para in paragraphs:
        text = para.get("text", "") if isinstance(para, dict) else str(para)
        info = _detect_qnum(text)
        if info:
            q_num, q_end, code = info
            current = {
                "q_num": q_num,
                "q_num_end": q_end,
                "code": code,
                "paragraphs": [],
            }
            sections.append(current)
            continue
        if current is not None:
            current["paragraphs"].append(para)
    return sections


def _index_step3_by_qnum(step3_data):
    """workbook parser의 STEP3 결과를 q_num으로 인덱싱.

    workbook parser의 step3는:
      {"normal": [{question_num, code, paragraphs}, ...],
       "short": [...], ...}
    또는 (마더텅 강 단위 등 fallback 경로) 파일 단위 리스트.

    Returns: {q_num: {code, paragraphs}}
    """
    result = {}
    if not isinstance(step3_data, dict):
        return result
    for key in ("normal", "short"):
        items = step3_data.get(key, [])
        if not isinstance(items, list):
            continue
        for it in items:
            qn = str(it.get("question_num") or it.get("q_num") or "").strip()
            if not qn:
                continue
            result[qn] = {
                "code": it.get("code"),
                "paragraphs": it.get("paragraphs", []),
            }
    return result


def _parse_step3_from_files(step3_dir, log):
    """모의고사 normal_questions/short_questions에 안 잡힌 STEP3 폴더를 직접 파싱.

    파일명 패턴: "Step3 15강 N번 YYMMQQ.docx" 또는 "고1 25년 9월 N번.hwp" 등
    """
    if not os.path.isdir(step3_dir):
        return []
    from core.extract import (
        _docx_extract_paragraphs,
        _hwp_extract_paragraphs,
    )
    from engines.workbook.parser import (
        _strip_step3_answers,
        _strip_step3_type_tags,
        _strip_step3_book_markers,
        _fix_step3_order_label_position,
        _merge_step3_ab_pairs,
    )
    items = []
    for fname_raw in sorted(os.listdir(step3_dir)):
        fname = unicodedata.normalize("NFC", fname_raw)
        if not (fname.endswith(".hwp") or fname.endswith(".hwpx") or fname.endswith(".docx")):
            continue
        # 다양한 번호 패턴
        m = re.search(r'(\d+)\s*강\s*(\d+)(?:~(\d+))?\s*번(?:\s*(\d{6}))?', fname)
        if m:
            lesson = m.group(1)
            q_num = m.group(2)
            q_end = m.group(3)
            code = m.group(4)
        else:
            m2 = re.search(r'(\d+)(?:~(\d+))?\s*번', fname)
            if not m2:
                continue
            q_num = m2.group(1)
            q_end = m2.group(2)
            code = None
            lesson = None
        fpath = os.path.join(step3_dir, fname_raw)
        try:
            if fpath.lower().endswith(".docx"):
                paras = _docx_extract_paragraphs(fpath, True)
            else:
                paras = _hwp_extract_paragraphs(fpath, True, exclude_footnotes=True)
        except Exception as e:
            log(f"[파서/sero] STEP3 파일 읽기 실패: {fname} — {e}")
            continue
        # 후처리
        # 1) "N강 N번 YYMMQQ" 형태의 문제 식별 헤더 제거 (docx 첫 단락)
        paras = _strip_step3_lesson_header(paras)
        # 2) [정답] 이후 모든 paragraphs 제거 + 기존 정답 제거 패턴
        paras = _strip_step3_answers_aggressive(paras)
        paras = _strip_step3_answers(paras)
        paras = _strip_step3_type_tags(paras)
        # 2.5) 문장삽입 발문 다음 paragraph가 "주어진 문장"+본문 형태로 합쳐 있으면 split
        paras = _split_step3_insert_passage(paras)
        # 3) ① 자동 prepend 비활성화 — docx 원고는 이미 ①가 입력되어 있음
        # paras = _add_step3_choice_numbers(paras)  # 비활성 — 원고에 있는 ①의 중복 발생 방지
        paras = _strip_step3_book_markers(paras)
        paras = _fix_step3_order_label_position(paras)
        paras = _merge_step3_ab_pairs(paras)
        items.append({
            "q_num": q_num,
            "q_num_end": q_end,
            "code": code,
            "lesson": lesson,
            "filename": fname,
            "paragraphs": paras,
        })
    return items


def parse_manuscript_folder(manuscript_dir, config, grade, year, month, log):
    """세로 워크북 원고 폴더 파싱.

    Returns:
        {
            "grade", "year", "month",
            "cycles": [
                {
                    "q_num": "14",
                    "q_num_end": None,
                    "code": "171140",
                    "steps": {
                        "step1_a1": [{text, runs, ...}, ...],   # paragraphs
                        "step1_a1_2": [...],
                        "step1_a2": [...],
                        ...
                        "step3": [...],
                    },
                },
                ...
            ],
            "raw": {                                              # 원본 파서 결과 (디버그용)
                "step1_a1": {paragraphs, ...},
                ...
                "step3": {normal, short, ...},
            }
        }
    """
    # 1단계: 가로 워크북 parser로 STEP1/2/3 추출
    log("[파서/sero] 가로 워크북 parser 호출 (재사용)")
    raw = _workbook_parse(manuscript_dir, config, grade, year, month, log)

    # 2단계: STEP3 처리 — 항상 폴더 직접 파싱 (마더텅 강 단위 등 다양한 형식 지원)
    step3_dir = os.path.join(manuscript_dir, "Step3")
    step3_items = _parse_step3_from_files(step3_dir, log)
    log(f"[파서/sero] STEP3 (폴더 직접 파싱): {len(step3_items)}개")

    # workbook parser 결과가 더 풍부하면 (예: 정규 모의고사) 보조로 사용
    if not step3_items:
        raw_step3 = (raw.get("steps") or {}).get("step3", {}) or {}
        normal = raw_step3.get("normal", []) if isinstance(raw_step3, dict) else []
        short = raw_step3.get("short", []) if isinstance(raw_step3, dict) else []
        if normal or short:
            log(f"[파서/sero] STEP3 fallback (workbook parser): normal={len(normal)}, short={len(short)}")
            for it in (normal + short):
                step3_items.append({
                    "q_num": str(it.get("question_num") or ""),
                    "q_num_end": None,
                    "code": it.get("code"),
                    "paragraphs": it.get("paragraphs", []),
                })

    if not step3_items:
        raise ValueError(
            "STEP3 원고를 하나도 찾지 못했습니다. "
            "Step3/ 하위에 '*N번*.docx' 또는 '*N강 M번*.docx' 형태의 파일을 두세요."
        )

    # 3단계: STEP1/2 paragraphs를 q_num별로 분할
    step_keys = [
        "step1_a1", "step1_a1_2", "step1_a2", "step1_b1", "step1_b2",
        "step1_c1", "step1_c2",
        "step2_a1", "step2_a1_btm", "step2_b1", "step2_c1", "step2_c2",
    ]
    splits = {}  # {step_key: {q_num: [paragraphs]}}
    for sk in step_keys:
        step_data = (raw.get("steps") or {}).get(sk, {})
        paras = step_data.get("paragraphs", []) if isinstance(step_data, dict) else []
        sections = _split_paragraphs_by_qnum(paras)
        m = {}
        for sec in sections:
            qn = sec["q_num"]
            if not qn:
                continue
            sec_paras = sec.get("paragraphs", [])
            # step1_c1: 본문 도입부에 3+ space prefix 추가 → 가로 코드가 BTM/BTM_T 분류
            if sk == "step1_c1":
                sec_paras = _augment_step1_c1_passage(sec_paras)
            # 합본은 첫 번호만 키로 사용 (마지막은 q_num_end)
            m[qn] = {
                "q_num": qn,
                "q_num_end": sec.get("q_num_end"),
                "code": sec.get("code"),
                "paragraphs": sec_paras,
            }
        splits[sk] = m
        log(f"[파서/sero] {sk}: {len(m)}개 q_num 분할 (총 {len(paras)} paragraphs)")

    # 4단계: 사이클 구성 — STEP3 문제 수가 기준
    # q_num 정렬: 정수 정렬 시도, 실패하면 문자열 정렬
    def _q_sort_key(qn):
        try:
            return (0, int(qn))
        except Exception:
            return (1, str(qn))

    cycles = []
    for s3 in sorted(step3_items, key=lambda x: _q_sort_key(x.get("q_num", ""))):
        qn = str(s3.get("q_num", ""))
        cycle = {
            "q_num": qn,
            "q_num_end": s3.get("q_num_end"),
            "code": s3.get("code"),
            "steps": {},
        }
        for sk in step_keys:
            qm = splits.get(sk, {})
            entry = qm.get(qn)
            if entry:
                cycle["steps"][sk] = entry.get("paragraphs", [])
            else:
                cycle["steps"][sk] = []
        cycle["steps"]["step3"] = s3.get("paragraphs", [])
        cycles.append(cycle)

    log(f"[파서/sero] 사이클 구성 완료: {len(cycles)}개")

    return {
        "grade": grade,
        "year": year,
        "month": month,
        "cycles": cycles,
        "raw_step_counts": {sk: len(splits.get(sk, {})) for sk in step_keys},
    }


def main():
    """CLI: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>"""
    import json
    if len(sys.argv) < 6:
        print("사용법: python3 parser.py <output.json> <manuscript_dir> <grade> <year> <month>")
        sys.exit(1)
    output_path = sys.argv[1]
    manuscript_dir = sys.argv[2]
    grade = int(sys.argv[3])
    year = int(sys.argv[4])
    month = int(sys.argv[5])
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, lambda s: print(s))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
