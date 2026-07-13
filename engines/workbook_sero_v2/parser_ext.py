"""세로 v2 파싱 오케스트레이션 — 정규(비증강) 모의고사 워크북 지원 (W18 c17).

v1 세로 파서(engines/workbook_sero/parser)는 마더텅 증강 원고([N강 N번
코드] / [N] 마커가 본문에 삽입된 사본)만 q_num 분할할 수 있다. 정규
모의고사 워크북 폴더(고1 23년 11월 등)는 스텝별로 다른 자체 마커를
쓰므로 v1 기준 전 스텝이 0분할 — 사이클이 전부 비워진 채 '성공'하는
침묵 유실이 된다 (W18 c17 실증, D4).

이 모듈은 v1 parse_manuscript_folder의 오케스트레이션(1단계 가로 파서 →
2단계 STEP3 → 3단계 분할 → 4단계 사이클)을 v2 계층에서 재구성하되,
분할 마커 인식만 확장한다 (v1 모듈 무수정 — helpers import 재사용):

  v1 기존:  [N강 N번 코드] / [코드] / [N] / {N} / N강 N번
  v2 확장:  N. pN-no.NN(~NN)(꼬리)   — c1/c2/2a1/2b1/2b2/2c1/2c2 지문 헤더
            고N #NN                  — a1/a1_2/a2 (오토큐엠 세대)
            NN. / NN번 (단독)        — b1 / 2c2(서술형) — 오인 방지를 위해
                                       step3 문항 번호 집합에 있을 때만
"""
import os
import re
import unicodedata

from engines.workbook_sero.parser import (
    _workbook_parse,
    _parse_step3_from_files,
    _detect_qnum,
    _augment_step1_c1_passage,
)

# 정규 모의고사 워크북 지문 헤더: "1. p2-no.20", "18. p11-no.41~42",
# "1. p2-no.20  (정답 1개)" — 선두 순번은 버리고 no.NN이 문항 번호.
_RE_Q_PNNO = re.compile(
    r'^\s*\d+\s*\.\s*p\d+\s*-\s*no\s*\.\s*(\d{1,3})'
    r'(?:\s*~\s*(?:no\s*\.\s*)?(\d{1,3}))?')
# 오토큐엠 세대 지문 마커: "고1 #20"
_RE_Q_HASH = re.compile(r'^\s*고\s*\d\s*#\s*(\d{1,3})(?:\s*~\s*(\d{1,3}))?\s*$')
# 단독 번호 라인: "20." (b1) / "20번" (2c2 서술형) — step3 문항 번호
# 집합에 있을 때만 마커로 인정 (항목 번호 "1." 오인 방지)
_RE_Q_BARE = re.compile(r'^\s*(\d{1,3})(?:\s*~\s*(\d{1,3}))?\s*(?:\.|번)\s*$')
# 발문 꼬리 문항 표기: "글의 흐름으로 보아 …? [24] ③" (b1 순서삽입 문제
# 모음 — 파일 꼬리에 지문 순서와 무관하게 몰려 있어, 발문 라인 자체를
# '포함형' 마커로 삼아 해당 문항 사이클로 배정). step3 번호 집합 한정.
_RE_Q_STEM_TAIL = re.compile(
    r'^.{0,120}[?？]\s*\[(\d{1,3})(?:~(\d{1,3}))?\]\s*[①-⑤]?\s*$')
# 스텝 파일 내부 정답 파트 표제: "내용일치 정답" / "1. 어휘2단계_Hard_정답"
# / "정답 및 해설" (a2·a1 보충본 실증 — 이하 정답 블록의 마커는
# "고1 #21 ③" 원문자 부착 또는 "[34]" 재등장 형태라 문제 파트와 구분
# 불가 → 표제부터 파일 끝까지 사이클에 싣지 않는다)
_RE_ANSWER_PART_TITLE = re.compile(
    r'^[^?？]{0,40}[_\s\-–—]정답$|^정답(\s*및\s*해설)?$')


def _detect_qnum_v2(text, known_qnums):
    """v1 _detect_qnum + 정규 모의고사 워크북 마커 확장."""
    info = _detect_qnum(text)
    if info:
        return info
    txt = (text or "").strip()
    if not txt:
        return None
    m = _RE_Q_PNNO.match(txt)
    if m:
        return (m.group(1), m.group(2), None)
    m = _RE_Q_HASH.match(txt)
    if m:
        return (m.group(1), m.group(2), None)
    m = _RE_Q_BARE.match(txt)
    if m and m.group(1) in known_qnums:
        return (m.group(1), m.group(2), None)
    return None


def _cut_answer_parts(paragraphs, known_qnums):
    """스텝 파일 내부의 정답 파트("내용일치 정답" 이하) 제거 (W18 c17 a2).

    정답 파트 표제부터 파일 끝까지 드롭한다. 정답 파트의 마커는 원문자
    부착("고1 #21 ③") 또는 단독 재등장("[34]" — a1 보충본 정답 섹션)
    형태라 마커로 문제 파트 재개를 판별할 수 없다 — 관측된 전 셰이프에서
    정답 파트는 파일 꼬리이므로 끝까지 드롭이 안전. 영단어 항목
    ("248. answer")은 한글 '정답' 종결이 아니라 무관.
    """
    out = []
    for para in paragraphs:
        text = (para.get("text", "") if isinstance(para, dict)
                else str(para)).strip()
        if _RE_ANSWER_PART_TITLE.match(text):
            break
        out.append(para)
    return out


def _split_paragraphs_by_qnum_v2(paragraphs, known_qnums):
    """v1 _split_paragraphs_by_qnum과 동일 의미론 + v2 마커 확장.

    - 마커 단락 자체는 섹션에서 제외, 첫 마커 이전 단락은 버린다 (v1 동일 —
      스텝 파일 선두의 문서 표제/공통 발문은 세로 템플릿에 이미 있음).
    - 발문 꼬리 표기("…? [24] ③")는 '포함형' 마커 — 발문 라인부터 해당
      문항 섹션 (b1 순서삽입 문제 모음 실증).
    - 같은 q_num이 다시 나오면 덮어쓰지 않고 이어붙인다 (본문정리 파트와
      문제 모음 파트가 같은 문항을 두 번 다루는 구성 — v1 코퍼스에는
      중복 q_num이 없어 파리티 무영향, 테스트 고정).
    """
    sections = []
    by_qnum = {}
    current = None
    for para in paragraphs:
        text = para.get("text", "") if isinstance(para, dict) else str(para)
        info = _detect_qnum_v2(text, known_qnums)
        inclusive = False
        if not info:
            m = _RE_Q_STEM_TAIL.match(text.strip())
            if m and m.group(1) in known_qnums:
                info = (m.group(1), m.group(2), None)
                inclusive = True
        if info:
            q_num, q_end, code = info
            if q_num in by_qnum:
                current = by_qnum[q_num]
                if q_end and not current.get("q_num_end"):
                    current["q_num_end"] = q_end
            else:
                current = {
                    "q_num": q_num,
                    "q_num_end": q_end,
                    "code": code,
                    "paragraphs": [],
                }
                by_qnum[q_num] = current
                sections.append(current)
            if inclusive:
                current["paragraphs"].append(para)
            continue
        if current is not None:
            current["paragraphs"].append(para)
    return sections


_STEP_KEYS = [
    "step1_a1", "step1_a1_2", "step1_a2", "step1_b1", "step1_b2",
    "step1_c1", "step1_c2",
    "step2_a1", "step2_a1_btm", "step2_b1", "step2_c1", "step2_c2",
]


# A1 어휘선택 보충본: "Step1 A1 어휘선택(2단계 34번).docx" — 본 파일이
# 다루지 않는 문항의 어휘 N단계 블록 ([NN] 마커 + 본문 + _정답 파트).
_RE_A1_SUPP_STAGE = re.compile(r'([12])\s*단계')


def _merge_a1_supplements(manuscript_dir, raw, log):
    """미소비 어휘선택 보충본을 step1_a1/a1_2 paragraphs 뒤에 병합 (W18 D11).

    가로 파서는 스텝당 1파일만 소비 — "(2단계 34번)" 보충본이 조용히
    무시돼 해당 문항의 어휘 2단계 박스가 비었다 (c17 Q34 실증). 병합된
    단락은 [NN] 마커 분할이 문항 사이클로 배정하고, _정답 파트 컷이
    정답 블록을 걸러낸다. 반환: 병합한 파일명 리스트 (G9 소비 보고용).
    """
    from core.extract import (_docx_extract_paragraphs,
                              _hwp_extract_paragraphs)
    steps = raw.get("steps") or {}
    used = set()
    for sd in steps.values():
        if isinstance(sd, dict) and sd.get("filename"):
            used.add(unicodedata.normalize("NFC", sd["filename"]))
    merged = []
    seen_bases = set()
    for fname_raw in sorted(os.listdir(manuscript_dir)):
        fname = unicodedata.normalize("NFC", fname_raw)
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".docx", ".hwp", ".hwpx") or fname in used:
            continue
        # 업로드 슬롯 접두("manuscripts_") 사본과 스테이징 사본이 같은
        # 디렉터리에 공존한다 — 접두 제거 기준으로 중복 병합 차단
        base = (fname[len("manuscripts_"):]
                if fname.startswith("manuscripts_") else fname)
        if base in seen_bases or base in used:
            continue
        if "어휘선택" not in fname.replace(" ", ""):
            continue
        m = _RE_A1_SUPP_STAGE.search(fname)
        if not m:
            continue
        sk = "step1_a1" if m.group(1) == "1" else "step1_a1_2"
        sd = steps.get(sk)
        if not isinstance(sd, dict):
            continue
        fpath = os.path.join(manuscript_dir, fname_raw)
        try:
            if ext == ".docx":
                paras = _docx_extract_paragraphs(fpath, True)
            else:
                paras = _hwp_extract_paragraphs(fpath, True,
                                                exclude_footnotes=True)
        except Exception as e:      # noqa: BLE001
            log(f"[파서/sero-v2] 보충본 읽기 실패: {fname} — {e}")
            continue
        # 보충본 단위로 정답 파트를 먼저 컷 — 여러 파일 병합 시 뒤 파일의
        # 문제 파트가 앞 파일 정답 컷에 쓸려가지 않게 소스별 처리
        paras = _cut_answer_parts(paras, set())
        sd.setdefault("paragraphs", []).extend(paras)
        merged.append((sk, fname))
        seen_bases.add(base)
        log(f"[파서/sero-v2] 어휘선택 보충본 병합: {fname} → {sk} "
            f"(+{len(paras)}단락)")
    return merged


def parse_manuscript_folder_v2(manuscript_dir, config, grade, year, month,
                               log):
    """v1 parse_manuscript_folder의 v2 재구성 — 분할 마커만 확장.

    반환 형식은 v1과 동일 (cycles/raw_step_counts) + 게이트(G9)용
    "steps" 미니뷰(스텝별 소비 파일명 + step3 문항 번호) 추가.
    """
    # 1단계: 가로 워크북 parser로 STEP1/2/3 추출 (v1 동일)
    log("[파서/sero-v2] 가로 워크북 parser 호출 (재사용)")
    raw = _workbook_parse(manuscript_dir, config, grade, year, month, log)
    supp_merged = _merge_a1_supplements(manuscript_dir, raw, log)

    # 2단계: STEP3 — 폴더 직접 파싱 우선, 폴백 v1 동일
    step3_dir = os.path.join(manuscript_dir, "Step3")
    step3_items = _parse_step3_from_files(step3_dir, log)
    log(f"[파서/sero-v2] STEP3 (폴더 직접 파싱): {len(step3_items)}개")
    if not step3_items:
        raw_step3 = (raw.get("steps") or {}).get("step3", {}) or {}
        normal = (raw_step3.get("normal", [])
                  if isinstance(raw_step3, dict) else [])
        short = (raw_step3.get("short", [])
                 if isinstance(raw_step3, dict) else [])
        if normal or short:
            log(f"[파서/sero-v2] STEP3 fallback (workbook parser): "
                f"normal={len(normal)}, short={len(short)}")
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
            "Step3/ 하위에 '*N번*.docx' 또는 '*N강 M번*.docx' 형태의 "
            "파일을 두세요.")

    # 분할 마커 확장용 문항 번호 집합 (단독 번호 라인 오인 방지 게이트)
    known_qnums = set()
    for it in step3_items:
        qn = str(it.get("q_num") or "").strip()
        if qn:
            known_qnums.add(qn)
        qe = str(it.get("q_num_end") or "").strip()
        if qn.isdigit() and qe.isdigit():
            for q in range(int(qn), int(qe) + 1):
                known_qnums.add(str(q))

    # 3단계: STEP1/2 paragraphs를 q_num별로 분할 (v2 마커 확장)
    splits = {}
    for sk in _STEP_KEYS:
        step_data = (raw.get("steps") or {}).get(sk, {})
        paras = (step_data.get("paragraphs", [])
                 if isinstance(step_data, dict) else [])
        paras = _cut_answer_parts(paras, known_qnums)
        sections = _split_paragraphs_by_qnum_v2(paras, known_qnums)
        m = {}
        for sec in sections:
            qn = sec["q_num"]
            if not qn:
                continue
            sec_paras = sec.get("paragraphs", [])
            if sk == "step1_c1":
                sec_paras = _augment_step1_c1_passage(sec_paras)
            m[qn] = {
                "q_num": qn,
                "q_num_end": sec.get("q_num_end"),
                "code": sec.get("code"),
                "paragraphs": sec_paras,
            }
        splits[sk] = m
        log(f"[파서/sero-v2] {sk}: {len(m)}개 q_num 분할 "
            f"(총 {len(paras)} paragraphs)")

    # 4단계: 사이클 구성 (v1 동일)
    def _q_sort_key(qn):
        try:
            return (0, int(qn))
        except Exception:
            return (1, str(qn))

    cycles = []
    for s3 in sorted(step3_items, key=lambda x: _q_sort_key(x.get("q_num",
                                                                  ""))):
        qn = str(s3.get("q_num", ""))
        cycle = {
            "q_num": qn,
            "q_num_end": s3.get("q_num_end"),
            "code": s3.get("code"),
            "steps": {},
        }
        for sk in _STEP_KEYS:
            entry = splits.get(sk, {}).get(qn)
            cycle["steps"][sk] = entry.get("paragraphs", []) if entry else []
        cycle["steps"]["step3"] = s3.get("paragraphs", [])
        cycles.append(cycle)
    log(f"[파서/sero-v2] 사이클 구성 완료: {len(cycles)}개")

    # 게이트(G9/G3)용 스텝 미니뷰 — 소비 파일명 + step3 문항 번호.
    # paragraphs는 싣지 않는다 (content.json 비대화 방지, G6은 생략).
    steps_view = {}
    for sk in _STEP_KEYS:
        sd = (raw.get("steps") or {}).get(sk)
        if isinstance(sd, dict) and sd.get("filename"):
            steps_view[sk] = {"filename": sd["filename"]}
    for i, (sk, fname) in enumerate(supp_merged):
        # 보충본도 소비 파일로 보고 (G9 미사용 오탐 방지)
        steps_view[f"{sk}_supp{i}"] = {"filename": fname}
    q_frames = []
    for it in step3_items:
        qn = str(it.get("q_num") or "")
        qe = str(it.get("q_num_end") or "")
        q_frames.append(qn)
        if qe:
            q_frames.extend([qe, f"{qn}~{qe}"])
    steps_view["step3"] = {"normal": [
        {"question_num": str(it.get("q_num") or ""),
         "filename": it.get("filename")}
        for it in step3_items], "short": [],
        # 게이트 G3용 — 세로 템플릿의 문항 번호 소형 프레임 기대 집합
        "question_numbers": q_frames}

    return {
        "grade": grade,
        "year": year,
        "month": month,
        "cycles": cycles,
        "raw_step_counts": {sk: len(splits.get(sk, {}))
                            for sk in _STEP_KEYS},
        "steps": steps_view,
    }
