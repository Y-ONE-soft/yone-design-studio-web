"""파일명 라우팅 공용 계층 — 배치 A (W33, docs/인식지점_전수감사.md §9).

감사 리스크 1·2위(Step3 파일명→문항 라우팅 완전 침묵 / 업로드 스텝 라우팅
5벌 반복 수리 계보 W12·W13·W14·W17·W18)의 전환 지점:

  1) route_step3      — v2 계열 공용 업로드 라우터. 토큰 정규화(공백/언더스코어/
                        0패딩/NFC) 후 판정 — 'STEP 03'·'177 문제'·'변형 문항' 같은
                        토씨 변형에 견딘다. 정답/답지류와 스텝1/2 접두(세로 W18 D3
                        가드의 전 계열 확산)는 차단.
  2) canonical_step3_filename — v1 파서의 소비 규칙('N번.<ext>')에 맞지 않지만
                        문항 번호 토큰이 있는 파일명을 규격명으로 스테이징
                        ('20번 (수정).docx' → '20번.docx', '41-42번' → '41~42번').
                        v1 무수정 — v2 래퍼가 스테이징 사본 이름만 바꾼다.
  3) reconcile_step3  — 파싱 후 '입력 파일 전수 ↔ 라우팅(소비) 결과' 쌍방 대조.
                        어느 문항에도 실리지 않은 원고 파일이 남으면 [오류]로
                        조판 중단 (침묵 누락 금지 — W31 침묵 금지 원칙의 라우팅
                        이식). 의도된 제외(정답/답지류·MIXED 통합본 우선)는
                        routing_rules.json 데이터 테이블로 관리하고 로그로 보고.

v1(engines/workbook, engines/workbook_sero 등) 무수정 — 전부 v2 래퍼/선라우팅
계층에서 동작한다.
"""
import json
import os
import re
import unicodedata

_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_DIR, "routing_rules.json"), encoding="utf-8") as _f:
    _RULES = json.load(_f)

MS_EXTS = (".docx", ".hwp", ".hwpx")

# 의도된 제외 (데이터룰 — routing_rules.json)
RE_ANSWER_TOKEN = re.compile("|".join(_RULES["answer_tokens"]))
_EXCLUSION_PATTERNS = [re.compile(p) for p in
                       _RULES.get("step3_intended_exclusion_patterns", [])]
_MIXED_PRIORITY = bool(_RULES.get("mixed_priority", True))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── 토큰 정규화 ──────────────────────────────────────────────────────────────
# 구분자(공백/언더스코어/하이픈/마침표/중점/괄호류)를 지운 소문자 NFC 형태에서
# 스텝 토큰을 찾는다 — 'STEP 03'·'Step_3'·'스텝-3' 전부 같은 토큰.
_RE_SEP = re.compile(r"[\s_\-.·()\[\]]+")


def _collapsed(name):
    return _RE_SEP.sub("", _nfc(name).lower())


_RE_STEP3_TOKEN = re.compile(r"(?:스텝|step)0*3(?!\d)")
_RE_STEP12_PREFIX = re.compile(r"^(?:스텝|step)0*[12](?!\d)")
# 문항 번호 토큰 (라우팅 판정용 — v1과 동일 언어 + 물결 변형)
RE_QNUM = re.compile(r"(\d+)(?:\s*[~∼～]\s*(\d+))?\s*번")
# 문항 번호 토큰 (규격명 스테이징용 — 하이픈 범위 '41-42번'도 수용)
_RE_QNUM_FLEX = re.compile(r"(\d+)(?:\s*[~∼～\-]\s*(\d+))?\s*번")
# 변형문제 문제모음 (W12/W14 계보 + 배치 A: '변형 문항'·띄어쓴 문항수 '177 문제').
# 띄어쓴 문항수는 2자리+ & 범위(~)/학년(고N) 뒤가 아닐 때만 — 'DAY23~25 문제'
# (day 범위)·'고2 문제'는 문항수가 아니다 (W14 관행 유지).
RE_VARIANT_POOL = re.compile(
    r"변형\s*문(?:제|항)|\d문제|(?<![~∼\-\d고])\d{2,}\s+문제")
# v1 _parse_step3_folder의 소비 규칙과 동일 (파서 1470행 — 'N번.<ext>')
RE_STRICT_S3_FILE = re.compile(r"(\d+(?:~\d+)?)번\s*\.(?:hwpx?|docx)", re.I)
# 마더텅형 'N강 M번 [YYMMQQ]' — v1 폴백 분기가 그대로 소비
_RE_MOTHERTONGUE = re.compile(r"\d+\s*강\s*(\d+)(?:~\d+)?\s*번")


def is_variant_pool_filename(fname_nfc):
    """변형문제 문제모음 여부 (정답/답지류 제외) — W12 라우팅의 공용판."""
    return (bool(RE_VARIANT_POOL.search(fname_nfc))
            and not RE_ANSWER_TOKEN.search(fname_nfc))


def route_step3(fname_nfc):
    """업로드 파일명 → Step3(실전/변형문제) 폴더 라우팅 여부 — 공용 라우터.

    기존 5벌(workbook_v2 _routes_to_step3 / v1 4벌 / sero) 판정의 상위집합:
      · 스텝3 토큰 — 구분자·0패딩 무관 ('STEP 03', 'Step_3', '스텝-3')
      · 문항 번호 토큰 'N번'/'N~M번'
      · 변형문제 문제모음 (변형 문제/문항, 문항수 표기)
    차단 가드 (전 계열 공통):
      · 정답/답지/해설/답안 토큰 (W13 c05 — 정답본이 문제로 조판되는 사고)
      · 스텝1/2 접두 (W18 D3 — 'Step1 A1 어휘선택(2단계 34번)'의 'NN번' 오인)
    """
    if RE_ANSWER_TOKEN.search(fname_nfc):
        return False
    coll = _collapsed(fname_nfc)
    if _RE_STEP12_PREFIX.match(coll):
        return False
    return bool(
        _RE_STEP3_TOKEN.search(coll)
        or RE_QNUM.search(fname_nfc)
        or RE_VARIANT_POOL.search(fname_nfc)
    )


def _norm_span(span):
    """번호 스팬 정규화 — 0패딩 제거, 범위 구분자 '~' 통일 ('05'→'5')."""
    parts = re.split(r"[~∼～\-]", span)
    try:
        nums = [str(int(p)) for p in parts if p.strip() != ""]
    except ValueError:
        return span
    return "~".join(nums)


def _span_numbers(span):
    """스팬 → 문항 번호 집합 ('41~42' → {41,42}). 숫자 아님이면 빈 집합."""
    parts = re.split(r"[~∼～\-]", span or "")
    try:
        nums = [int(p) for p in parts if p.strip() != ""]
    except ValueError:
        return set()
    if len(nums) == 2:
        return set(range(min(nums), max(nums) + 1))
    return set(nums)


def extract_question_span(fname_nfc):
    """파일명에서 문항 번호 스팬을 유연 추출 ('20' / '41~42'). 없으면 None.

    괄호 주석은 무시하고, 하이픈 범위('41-42번')도 물결 범위로 정규화한다.
    """
    cleaned = re.sub(r"\([^)]*\)", " ", _nfc(fname_nfc))
    m = _RE_QNUM_FLEX.search(cleaned)
    if not m:
        return None
    span = str(int(m.group(1)))
    if m.group(2):
        span += "~" + str(int(m.group(2)))
    return span


def canonical_step3_filename(fname_nfc):
    """Step3 스테이징 규격명 — v1 소비 규칙('N번.<ext>')에 맞게 재구성.

    이미 규격에 맞고 스팬도 일치하면 None (무변경 — 기존 코퍼스 diff 0).
    마더텅형('N강 M번 …')은 v1 폴백이 그대로 소비하므로 무변경.
    """
    fname_nfc = _nfc(fname_nfc)
    base, ext = os.path.splitext(fname_nfc)
    if ext.lower() not in MS_EXTS:
        return None
    if _RE_MOTHERTONGUE.search(fname_nfc):
        return None
    span = extract_question_span(fname_nfc)
    if span is None:
        return None
    m_strict = RE_STRICT_S3_FILE.search(fname_nfc)
    if m_strict and _norm_span(m_strict.group(1)) == span:
        return None                      # 이미 규격 — 무변경
    cleaned = re.sub(r"\([^)]*\)", " ", base)
    m = _RE_QNUM_FLEX.search(cleaned)
    rest = (cleaned[:m.start()] + " " + cleaned[m.end():]) if m else cleaned
    rest = re.sub(r"[\s_]+", " ", rest).strip(" -_.·")
    return f"{rest} {span}번{ext}" if rest else f"{span}번{ext}"


def stage_step3_name(step3_dir, fname_nfc, log):
    """Step3 스테이징 파일명 결정 — 규격명 변환 + 충돌 시 원명 유지(대조가 잡음)."""
    canon = canonical_step3_filename(fname_nfc)
    if not canon or canon == fname_nfc:
        return fname_nfc
    if os.path.exists(os.path.join(step3_dir, canon)):
        log(f"[라우팅] ⚠️ Step3 규격명 충돌 — 원명 유지 (쌍방 대조가 판정): "
            f"{fname_nfc} ↔ {canon}")
        return fname_nfc
    log(f"[라우팅] Step3 규격명 스테이징: {fname_nfc} → {canon}")
    return canon


def _is_intended_exclusion(fname_nfc):
    if RE_ANSWER_TOKEN.search(fname_nfc):
        return "정답/답지류 — 의도된 제외"
    for pat in _EXCLUSION_PATTERNS:
        if pat.search(fname_nfc):
            return f"제외 목록({pat.pattern}) — 의도된 제외"
    return None


def reconcile_step3(step3_dir, st3, log, *, number_matching=False,
                    engine_label="v2"):
    """Step3 '입력 파일 전수 ↔ 라우팅 결과' 쌍방 대조 — 침묵 누락 금지.

    파싱이 끝난 뒤 Step3 폴더의 원고 파일(hwp/hwpx/docx) 전수를 소비 결과와
    대조한다. 어느 문항에도 실리지 않은 파일이 남으면 [오류] ValueError로
    조판을 중단한다 (감사 실증 #1: '20번 (수정).docx' 완전 침묵 누락·로그 0줄).
    의도된 제외(정답/답지류 — routing_rules.json, MIXED 통합본 우선)는 로그로만
    보고. textbook 폴백 소비는 명시 로그를 남긴다.

    st3: content["steps"]["step3"] dict ({"normal": [...], "short": [...]}).
         sero 계열은 항목에 filename이 있어 파일명 기준으로도 대조한다.
    number_matching: 모의고사 번호 매칭이 수행됐는지 (cfg mockexam의
         normal/short 존재 여부) — v1의 _had_number_matching과 같은 기준.
    """
    stats = {"files": 0, "consumed": 0, "excluded": [], "unrouted": []}
    if not step3_dir or not os.path.isdir(step3_dir):
        return stats
    st3 = st3 or {}
    items = list(st3.get("normal") or []) + list(st3.get("short") or [])
    consumed_keys = set()
    consumed_files = set()
    textbook_mode = False
    for it in items:
        if not isinstance(it, dict):
            continue
        qn = str(it.get("question_num") or it.get("q_num") or "")
        if qn == "textbook":
            textbook_mode = True
        elif qn:
            consumed_keys.add(qn)
            consumed_keys.add(_norm_span(qn))
        fn = it.get("filename")
        if fn:
            consumed_files.add(_nfc(fn))
    # 복합 문항 확장 집합 — v1은 '41번.hwp' 단일 번호 파일도 복합 41~42로
    # 소비한다 (_process_question의 files.get(str(q_num)) 폴백, 실서비스
    # 26-6 잡 실측). 스팬 문자열 대조에 더해 번호 집합 포함으로 대조.
    consumed_nums = set()
    for k in consumed_keys:
        consumed_nums |= _span_numbers(k)

    files = [f for f in sorted(os.listdir(step3_dir))
             if not f.startswith(".")
             and os.path.splitext(f)[1].lower() in MS_EXTS]
    stats["files"] = len(files)
    mixed_present = any("mixed" in _collapsed(f) for f in files)

    unrouted = []
    for f in files:
        fn = _nfc(f)
        if fn in consumed_files:
            stats["consumed"] += 1
            continue
        reason = _is_intended_exclusion(fn)
        if reason:
            stats["excluded"].append(fn)
            log(f"[라우팅] Step3 {reason}: {fn}")
            continue
        m = RE_STRICT_S3_FILE.search(fn)
        if m and (_norm_span(m.group(1)) in consumed_keys
                  or (_span_numbers(m.group(1))
                      and _span_numbers(m.group(1)) <= consumed_nums)):
            stats["consumed"] += 1
            continue
        mt = _RE_MOTHERTONGUE.search(fn)
        if mt and (mt.group(1) in consumed_keys
                   or _norm_span(mt.group(1)) in consumed_keys):
            stats["consumed"] += 1
            continue
        if textbook_mode and not (number_matching and m):
            # v1은 번호 매칭이 수행된 경우 'N번.<ext>' 파일을 textbook
            # 후보에서 제외한다 (파서 1710행) — 그 경우만 침묵 누락 후보
            if _MIXED_PRIORITY and mixed_present and \
                    "mixed" not in _collapsed(fn):
                stats["excluded"].append(fn)
                log(f"[라우팅] Step3 MIXED 통합본 우선 — 의도된 제외: {fn}")
                continue
            stats["consumed"] += 1          # 통합(textbook) 블롭으로 소비됨
            continue
        span = extract_question_span(fn)
        if span and (span in consumed_keys
                     or (_span_numbers(span)
                         and _span_numbers(span) <= consumed_nums)):
            hint = f"문항 {span} 중복 후보 — 소비된 파일과 병존"
        elif span:
            hint = f"문항 {span} 후보 — 기대 문항 집합/규격명 확인"
        else:
            hint = "문항 번호 토큰 없음"
        unrouted.append(f"{fn} ({hint})")

    stats["unrouted"] = unrouted
    if textbook_mode and number_matching:
        log("[라우팅] Step3 번호 매칭 결과 없음 → 통합(textbook) 폴백 소비 "
            "(명시 로그 — 감사 §9 배치 A)")
    if unrouted:
        msg = (f"[오류] Step3 원고 {len(unrouted)}개가 어느 문항에도 실리지 "
               f"않았습니다 (침묵 누락 금지 — 배치 A 쌍방 대조): "
               + " | ".join(unrouted[:8])
               + " — 파일명을 'N번.<확장자>' 규격으로 정리하거나, 의도된 "
                 "제외라면 정답/답지 토큰 또는 routing_rules.json 제외 목록에 "
                 "등록하세요")
        log(msg)
        raise ValueError(msg)
    log(f"[라우팅] Step3 쌍방 대조 통과: 파일 {stats['files']}개 전수 소비 "
        f"(의도된 제외 {len(stats['excluded'])}개)")
    return stats
