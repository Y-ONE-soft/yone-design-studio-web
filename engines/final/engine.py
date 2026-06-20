"""파이널 직전보충 엔진 — BaseEngine 구현."""

import datetime
import json
import os
import re
import shutil
import subprocess
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy_indd
# GDrive 폴더 listing 시 미러 redirect — Drive zombie 시 EDEADLK 회피
from engines.final.extractor import _resolve_local_mirror as _rlm


def _nfc(s):
    """macOS NFD 한글 경로를 NFC로 정규화."""
    return unicodedata.normalize("NFC", s)


def _drop_revised_duplicates(files):
    """같은 .indd의 '(수정)'본과 원본이 함께 있으면 원본(비-수정)을 제외한다.

    '(수정)'은 개정/교정본이 최종본이므로, 원본까지 함께 추출하면 동일 지문이
    중복되어 중요어휘 등에서 헤더 중복·좌우 정렬 어긋남(test1 04부터 엉망)을
    유발한다. '(수정전)' 같은 다른 토큰은 매치되지 않으므로 건드리지 않는다.
    """
    def _base(name):
        # '(수정)' 토큰(및 주변 공백)만 제거 — '(수정전)' 등은 매치 안 됨
        return re.sub(r"\s*\(수정\)\s*", "", name)
    norm = {f: _nfc(os.path.basename(f)) for f in files}
    revised_bases = {_base(n) for n in norm.values() if "(수정)" in n}
    return [
        f for f in files
        if "(수정)" in norm[f] or _base(norm[f]) not in revised_bases
    ]


def _drop_identical_duplicates(files):
    """바이트 동일한 중복 .indd 제거.

    로컬 미러에 워크북 재번호매김 전의 구버전(예: '광문2_워크북01(리딩파워15,16,17강)')이
    남아 있으면, 같은 내용이 정본 '워크북02(리딩파워15,16,17강)'와 함께 추출되어 동일
    지문이 두 번 들어가고 강 라벨/순서가 어긋난다. '(수정)'/'(수정전)' 토큰이 없어 기존
    중복제거 로직에 걸리지 않으므로 별도 처리한다.

    크기가 같은 파일끼리만 MD5를 비교해(정상 케이스 = 동일 크기 충돌 없음 → 해시 0회)
    내용이 완전히 동일하면 워크북 번호가 가장 큰(= 최신 재번호) 파일만 남긴다.
    바이트 동일 파일만 제거하므로 콘텐츠 손실 위험이 없다.
    """
    import hashlib
    from collections import defaultdict
    by_size = defaultdict(list)
    for f in files:
        try:
            by_size[os.path.getsize(f)].append(f)
        except OSError:
            by_size[("__noerr__", f)].append(f)  # 크기 못 읽으면 단독 취급
    def _wbnum(p):
        m = re.search(r"워크북\s*(\d+)", _nfc(os.path.basename(p)))
        return int(m.group(1)) if m else -1
    drop = set()
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_hash = defaultdict(list)
        for f in group:
            try:
                with open(f, "rb") as fh:
                    by_hash[hashlib.md5(fh.read()).hexdigest()].append(f)
            except OSError:
                by_hash[("__noerr__", f)].append(f)
        for dups in by_hash.values():
            if len(dups) < 2:
                continue
            keep = max(dups, key=_wbnum)  # 내용 동일 → 최신(최대) 워크북 번호 유지
            for f in dups:
                if f is not keep:
                    drop.add(f)
    return [f for f in files if f not in drop]


def _drop_superseded_workbook_versions(files, log=lambda m: None):
    """같은 워크북 번호에 괄호 라벨이 다른 파일이 둘 이상이면(=구버전/신버전 공존),
    라벨 토큰셋이 다른 쪽의 '진부분집합'인 파일을 구버전으로 보고 제외한다.

    Why: 사용자가 워크북을 갱신하면 옛 파일(예: '워크북04(외부지문)')이 남고
         새 파일('워크북04(25년3월,외부지문)')이 추가되는데, 미러 미동기화로 둘 다
         감지되면 같은 외부지문이 중복 추출되고 새로 추가한 지문(25년3월)이 묻힌다.
    How: 워크북 번호로 그룹 → 괄호 안 콤마 토큰셋이 같은 번호의 다른 파일 토큰셋의
         진부분집합이면 제외. '(외부지문)'⊂'(25년3월,외부지문)' → 구버전 제외.
         '_내지_2' 연속 파트는 라벨이 동일하므로(진부분집합 아님) 모두 유지된다.
         라벨이 없거나 서로소(겹치지 않음)면 건드리지 않아 정상 워크북은 안전.
    """
    from collections import defaultdict
    def _num(p):
        m = re.search(r"워크북\s*(\d+)", _nfc(os.path.basename(p)))
        return m.group(1) if m else None
    def _tokens(p):
        m = re.search(r"\(([^)]*)\)", _nfc(os.path.basename(p)))
        if not m:
            return frozenset()
        return frozenset(t.strip() for t in m.group(1).split(",") if t.strip())
    by_num = defaultdict(list)
    for f in files:
        n = _num(f)
        if n is None:
            continue
        by_num[n].append(f)
    drop = set()
    for n, group in by_num.items():
        tok = {f: _tokens(f) for f in group}
        for f in group:
            if f in drop:
                continue
            for g in group:
                if g is f or g in drop:
                    continue
                # f의 라벨이 g 라벨의 진부분집합 → f는 구버전
                if tok[f] and tok[f] < tok[g]:
                    drop.add(f)
                    log(f"  [워크북 버전] 구버전 제외: "
                        f"{os.path.basename(f)} ← 최신 {os.path.basename(g)}")
                    break
    return [f for f in files if f not in drop]


def _extract_ebs_subscope(scope_text):
    """혼합 시험범위에서 EBS(리딩파워/올포/올림포스) 성분만 추출.

    한 워크북이 교과서 단원과 EBS 강을 함께 담으면(예: '리딩파워19강,미래엔김4과')
    classify_scope가 'textbook'으로만 분류해 EBS 강이 누락된다. EBS 접두어에 이어지는
    강 목록만 캡처하므로 교과서 과번호가 강번호로 오인되지 않는다('미래엔김4과'의 '4' 제외).

    '리딩파워19강,미래엔김4과' → '리딩파워19강'
    '올포5,8강,능률민3과'      → '올포5,8강'
    '리딩파워15,16,17강'       → '리딩파워15,16,17강' (순수 EBS는 그대로 반환)
    EBS 성분이 없으면 None.
    """
    m = re.search(
        r"(?:리딩파워|Reading\s*Power|올포|올림포스)\s*"
        r"(?:\d+(?:\s*[-~]\s*\d+)?\s*강?\s*,?\s*)+",
        _nfc(scope_text or ""),
    )
    if not m:
        return None
    return m.group(0).strip().rstrip(",").strip()


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


# ── 시험 기간(워크북 폴더) 자동 감지 ──────────────────────────────────
_TERM_ORDER = {"중간": 1, "기말": 2}


def _parse_exam_period(name):
    """'26-1-기말' → (26, 1, 2) 정렬키. 형식 불일치면 None."""
    m = re.match(r"^(\d{2})-(\d)-(중간|기말)$", _nfc(name).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), _TERM_ORDER[m.group(3)])


def scan_exam_periods(gdrive_base):
    """워크북 폴더에서 'YY-S-중간/기말' 형식 폴더를 최신순으로 반환.

    로컬 미러는 워크북 하위가 부분 동기화될 수 있어(시기 폴더 누락 가능),
    원본 GDrive 경로와 미러 경로를 모두 훑어 합집합으로 수집한다.
    """
    base = os.path.join(os.path.expanduser(gdrive_base or ""), "워크북")
    found = set()
    for cand in (base, _rlm(base, None)):
        if not cand or not os.path.isdir(cand):
            continue
        try:
            for d in os.listdir(cand):
                if _parse_exam_period(d):
                    found.add(_nfc(d))
        except OSError:
            continue
    return sorted(found, key=_parse_exam_period, reverse=True)


def estimate_exam_period(periods, today=None):
    """오늘 날짜로 가장 적절한 시험기간을 고른다.

    월 기준 추정(조판 작업이 시험 수 주 전부터인 점 반영):
      3~5월=1학기중간, 6~7월=1학기기말, 8~10월=2학기중간,
      11~12월=2학기기말, 1~2월(방학)=다가오는 1학기중간.
    추정 시기와 정확히 일치하는 폴더가 있으면 그것, 없으면 추정 시점
    이하의 최신 폴더, 그것도 없으면 폴더 목록 중 최신을 반환한다.
    """
    if not periods:
        return ""
    today = today or datetime.date.today()
    yy = today.year % 100
    mo = today.month
    if mo in (6, 7):
        sem, term = 1, 2
    elif mo in (8, 9, 10):
        sem, term = 2, 1
    elif mo in (11, 12):
        sem, term = 2, 2
    else:  # 1~5월 → 1학기 중간
        sem, term = 1, 1
    target = (yy, sem, term)
    keys = {_parse_exam_period(p): p for p in periods}
    if target in keys:
        return keys[target]
    le = [p for p in periods if _parse_exam_period(p) <= target]
    if le:
        return max(le, key=_parse_exam_period)
    return periods[0]


def resolve_exam_period(cfg, value=None):
    """exam_period 확정. value가 비었거나 'auto'면 폴더+날짜로 자동 결정.

    우선순위: 명시값(value) > config의 고정값 > 폴더+날짜 자동 추정.
    """
    if value and value.strip().lower() != "auto":
        return value.strip()
    cfg_val = (cfg.get("exam_period") or "").strip()
    if cfg_val and cfg_val.lower() != "auto":
        return cfg_val
    auto = estimate_exam_period(scan_exam_periods(cfg.get("gdrive_base", "")))
    return auto or cfg_val


def _convert_grammar_header(header, scope_text, scope_type, ebs_lecture=None):
    """어법수정 Word 헤더를 파이널 형식으로 변환.

    "1. L2-본문1" → "2과 본문1"
    "2. L1-p.17" → "1과 p.17"
    "1. p22-no.01" → "251020" (모의고사의 경우)

    올포 (ebs_olympos):
        "1. p60-수능 대비 ANALYSIS" → "올포 N강 분석"
        "2. p62-no.01" → "올포 N강 본문1"
        "3. p63-no.02" → "올포 N강 본문2"
        "5. p65-서술형 Practice" → "올포 N강 서술형"
        "6. p66-논술형 Practice" → "올포 N강 논술형"
    """
    header = _nfc(header).strip()

    # 숫자. 제거
    header = re.sub(r"^\d+\.\s*", "", header)

    if scope_type == "textbook":
        # PROJECT N 패턴 (L/SL보다 먼저 체크 — PROJECT는 별도 단원)
        m_proj = re.search(r"(?:PROJECT|Project)\s*(\d+)[-.]?(.*)", header, re.IGNORECASE)
        if m_proj:
            proj_num = m_proj.group(1)
            rest = (m_proj.group(2) or "").strip()
            if rest.startswith("-"):
                rest = rest[1:].strip()
            prefix = f"교과서Project{proj_num}"
            return f"{prefix} {rest}" if rest else prefix
        # SL/SpecialLesson 패턴 (L보다 먼저 체크해야 SL1을 L1로 잘못 매칭하지 않음)
        m_sl = re.search(r"(?:SL|Special\s*Lesson)\s*(\d+)?[-.]?(.*)", header, re.IGNORECASE)
        if m_sl:
            sl_num = m_sl.group(1) or ""
            rest = (m_sl.group(2) or "").strip()
            if rest.startswith("-"):
                rest = rest[1:].strip()
            prefix = "교과서SL"
            return f"{prefix} {rest}" if rest else prefix
        # "L2-본문1" → "교과서2과 본문1"
        m = re.search(r"L(\d+)[-.]?(.*)", header)
        if m:
            lesson = m.group(1)
            rest = m.group(2).strip()
            if rest.startswith("-"):
                rest = rest[1:].strip()
            return f"교과서{lesson}과 {rest}" if rest else f"교과서{lesson}과"

    elif scope_type == "mockexam":
        # "p22-no.01" → YYMMQQ, "no.41~42" → YYMM41~42
        # scope_text 패턴 후보: "25년3월02" / "모의고사25.3" 모두 yy/mm 추출 대상.
        m_year = re.search(r"(\d{2})년\s*(\d{1,2})월", _nfc(scope_text))
        if not m_year:
            m_year = re.search(r"모의고사\s*(\d{2})\.(\d{1,2})", _nfc(scope_text))
        if m_year:
            yy = m_year.group(1)
            mm = m_year.group(2).zfill(2)
            # 문항번호 추출 (범위 포함: no.41~42, no.43~45)
            m_q = re.search(r"no\.?\s*(\d+)(?:\s*[~\-]\s*(\d+))?", header, re.IGNORECASE)
            if m_q:
                qq = m_q.group(1).zfill(2)
                if m_q.group(2):
                    qq2 = m_q.group(2).zfill(2)
                    return f"{yy}{mm}{qq}~{qq2}"
                return f"{yy}{mm}{qq}"
            m_p = re.search(r"p\.?(\d+)", header)
            if m_p:
                qq = m_p.group(1).zfill(2)
                return f"{yy}{mm}{qq}"

    elif scope_type == "ebs_olympos":
        # 올포: 원고 헤더에서 지문 유형과 번호를 추출해 "올포 N강 ..." 형식으로 변환
        lec = str(ebs_lecture) if ebs_lecture is not None else ""
        prefix = f"\uc62c\ud3ec {lec}\uac15" if lec else "\uc62c\ud3ec"
        # 분석 (ANALYSIS)
        if re.search(r"\uc218\ub2a5\s*\ub300\ube44\s*ANALYSIS|ANALYSIS", header, re.IGNORECASE):
            return f"{prefix} \ubd84\uc11d"
        # 서술형 Practice
        if re.search(r"\uc11c\uc220\ud615\s*Practice", header, re.IGNORECASE):
            return f"{prefix} \uc11c\uc220\ud615"
        # 논술형 Practice
        if re.search(r"\ub17c\uc220\ud615\s*Practice", header, re.IGNORECASE):
            return f"{prefix} \ub17c\uc220\ud615"
        # 본문: "no.01", "no.02" → "본문1", "본문2"
        m_no = re.search(r"no\.?\s*(\d+)", header, re.IGNORECASE)
        if m_no:
            body_num = int(m_no.group(1))
            return f"{prefix} \ubcf8\ubb38{body_num}"
        # 폴백: 원문 유지
        return header

    elif scope_type == "ebs_readingpower":
        # 리딩파워 Word 헤더 → "리딩파워 N강 ExMM" 또는 "리딩파워 N강 MM"
        # "1. p8-Example 1" → "리딩파워 N강 Ex01"
        # "3. p10-no.1" → "리딩파워 N강 01"
        lec = str(ebs_lecture) if ebs_lecture is not None else ""
        prefix = f"\ub9ac\ub529\ud30c\uc6cc {lec}\uac15" if lec else "\ub9ac\ub529\ud30c\uc6cc"
        m_ex = re.search(r"Example\s*(\d+)", header, re.IGNORECASE)
        if m_ex:
            return f"{prefix} Ex{int(m_ex.group(1)):02d}"
        m_p = re.search(r"no\.?\s*(\d+)", header, re.IGNORECASE)
        if m_p:
            return f"{prefix} {int(m_p.group(1)):02d}"
        return header

    return header


_PATH_KEYS = ["gdrive_base", "gdrive_content_base", "template_vol1", "template_vol2"]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class FinalEngine(BaseEngine):

    @property
    def material_id(self):
        return "final"

    @property
    def display_name(self):
        return "파이널 직전보충"

    @property
    def description(self):
        return "파이널(Vol1/Vol2) 조판 자동화 — 워크북 텍스트 추출 → 파이널 내지 배치"

    @property
    def subject_prefix(self):
        return "파이널"

    @property
    def template_name(self):
        return "typeset_final.html"

    @property
    def log_filename(self):
        return "typeset_log.txt"

    @property
    def jsx_timeout(self):
        return 900  # 추출 + Vol1 + Vol2 = 최대 15분

    @property
    def upload_spec(self):
        return {"slots": []}

    # ── 메타데이터 헬퍼 ──

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ── 워크북 자동 감지 ──

    @staticmethod
    def find_workbook_files(gdrive_base, exam_period, grade, school):
        """워크북 디렉터리에서 .indd 파일 자동 감지.

        고1/고2: 학교별 워크북 중 '올포' 파일은 공용 EBS 독해기본 파일로 대체.
        반환: (files, wb_dir, allowed_olpo_lectures)
        """
        gdrive_base = os.path.expanduser(gdrive_base)
        # 고3: 학교별 폴더 우선 (분석편01/02/03 순) → 없으면 공유 분석편 폴더 fallback
        if grade == "고3":
            cfg = _load_config()
            # 학교 폴더 (교과서 분석편 포함 가능)
            school_dir = os.path.join(gdrive_base, "워크북", exam_period, grade, school)
            school_dir = _rlm(school_dir, None)
            school_files = []
            if os.path.isdir(school_dir):
                for f in sorted(os.listdir(school_dir)):
                    if f.endswith(".indd") and "분석" in _nfc(f):
                        school_files.append(os.path.join(school_dir, f))
            school_files = _drop_revised_duplicates(school_files)
            # 학교 폴더에 분석편이 있으면 그것만 사용 (번호순 정렬)
            if school_files:
                def _ord(p):
                    base = _nfc(os.path.basename(p))
                    # "분석편03" / "(분석01)" 등에서 숫자 추출
                    m = re.search(r"\ubd84\uc11d\s*(?:\ud3b8)?\s*0*(\d+)", base)
                    if m:
                        return (int(m.group(1)), base)
                    m2 = re.search(r"\(\ubd84\uc11d\s*0*(\d+)", base)
                    if m2:
                        return (int(m2.group(1)), base)
                    return (999, base)
                school_files.sort(key=_ord)
                return school_files, school_dir, set()

            # fallback: 공유 EBS 분석편
            wb_dir = os.path.expanduser(cfg.get("고3_workbook_base", ""))
            wb_dir = _rlm(wb_dir, None)
            if not os.path.isdir(wb_dir):
                return [], wb_dir, set()
            files = sorted([
                os.path.join(wb_dir, f) for f in os.listdir(wb_dir)
                if f.endswith(".indd") and "분석편" in _nfc(f)
            ])
            files = _drop_revised_duplicates(files)
            return files, wb_dir, set()
        wb_dir_gdrive = os.path.join(gdrive_base, "워크북", exam_period, grade, school)
        wb_dir = _rlm(wb_dir_gdrive, None)
        # 미러 ∪ GDrive 합집합 — 미러 미동기화로 새로 추가/갱신된 워크북이 누락되는
        # 사고 방지(예: 갱신된 '워크북04(25년3월,외부지문)'이 미러에 없어 구버전만 추출됨).
        # 미러본이 있으면 미러 경로(빠르고 EDEADLK 회피), 미러에 없는 파일만 GDrive로 보강.
        _names = {}
        for _d in (wb_dir, wb_dir_gdrive):
            if not _d or not os.path.isdir(_d):
                continue
            try:
                for f in os.listdir(_d):
                    nf = _nfc(f)
                    if f.lower().endswith(".indd") and "워크북" in nf and nf not in _names:
                        _names[nf] = os.path.join(_d, f)
            except OSError:
                continue
        if not _names:
            return [], wb_dir, set()
        all_files = sorted(_names.values(),
                           key=lambda p: _nfc(os.path.basename(p)))

        # "(수정전)" 구버전 파일 제외 — 같은 강 범위의 정식본이 함께 있으면 구버전이
        # 추출/중복제거 단계에서 이겨 Ex 경계가 깨진 채 들어가는 사고 방지.
        # 단, 정식본이 없으면(구버전만 존재) 콘텐츠 누락을 막기 위해 그대로 유지.
        def _lec_sig(p):
            m = re.search(r"\(([^)]*강[^)]*)\)", _nfc(os.path.basename(p)))
            return m.group(1) if m else None
        _clean_sigs = {
            _lec_sig(f) for f in all_files
            if "수정전" not in _nfc(os.path.basename(f))
        }
        all_files = [
            f for f in all_files
            if not ("수정전" in _nfc(os.path.basename(f))
                    and _lec_sig(f) in _clean_sigs)
        ]

        # 미러에 남은 구버전(다른 워크북 번호) 바이트 동일 중복 제거 — 미러 미동기화 사고 방지
        all_files = _drop_identical_duplicates(all_files)
        # 같은 워크북 번호의 구버전 라벨(예: '(외부지문)' ⊂ '(25년3월,외부지문)') 제외
        all_files = _drop_superseded_workbook_versions(all_files)

        # 올포 파일만 분리 (학교별 워크북의 올포는 공용 파일로 대체)
        non_olpo = [f for f in all_files if "올포" not in _nfc(os.path.basename(f))]
        olpo_files = [f for f in all_files if "올포" in _nfc(os.path.basename(f))]

        # 학교 올포 워크북에서 scope 강 범위 추출
        olpo_lectures_needed = set()
        for of in olpo_files:
            base = _nfc(os.path.basename(of))
            m = re.search(r"\(([^)]+)\)", base)
            if not m:
                continue
            scope = m.group(1)
            if "올포" not in scope:
                continue
            lec_str = scope.replace("올포", "").replace("강", "").strip()
            for part in lec_str.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        a, b = part.split("-")
                        olpo_lectures_needed.update(range(int(a), int(b) + 1))
                    except Exception:
                        pass
                elif part.isdigit():
                    olpo_lectures_needed.add(int(part))

        # 공용 올포 파일에서 필요한 강 포함 파일 선택
        if grade == "고1" and olpo_lectures_needed:
            cfg = _load_config()
            olpo_base = os.path.expanduser(cfg.get("고1_올포_공용_base", ""))
            olpo_base = _rlm(olpo_base, None)
            if os.path.isdir(olpo_base):
                for f in sorted(os.listdir(olpo_base)):
                    if not f.endswith(".indd"):
                        continue
                    fn = _nfc(f)
                    m = re.search(r"\((\d+)-(\d+)강\)", fn)
                    if not m:
                        continue
                    start, end = int(m.group(1)), int(m.group(2))
                    file_lectures = set(range(start, end + 1))
                    if file_lectures & olpo_lectures_needed:
                        non_olpo.append(os.path.join(olpo_base, f))

        # 고2: 학교별 올포 워크북을 그대로 포함 (공용 파일 대체 로직 없음)
        # 고2 올림포스 기출은 학교별로 별도 편집되어 있어 공용 파일이 부적절
        if grade == "고2" and olpo_files:
            non_olpo.extend(olpo_files)

        return non_olpo, wb_dir, olpo_lectures_needed

    @staticmethod
    def scan_schools(gdrive_base, exam_period):
        """시험 시기별 학교 목록 스캔."""
        result = {}
        for grade in ["고1", "고2"]:
            grade_dir = os.path.join(gdrive_base, "워크북", exam_period, grade)
            grade_dir = _rlm(grade_dir, None)
            if not os.path.isdir(grade_dir):
                continue
            schools = sorted([
                d for d in os.listdir(grade_dir)
                if os.path.isdir(os.path.join(grade_dir, d))
                and not d.startswith(".")
            ])
            if schools:
                result[grade] = schools
        # 고3: school_textbook_map에서 고3 학교 추출
        cfg = _load_config()
        stm = cfg.get("school_textbook_map", {}).get(exam_period, {})
        g3_schools = sorted([s for s in stm if s.endswith("3")])
        if not g3_schools:
            # 분석편 파일이 존재하면 빈 학교 목록이라도 고3 탭 표시
            wb_base = os.path.expanduser(cfg.get("고3_workbook_base", ""))
            if os.path.isdir(wb_base):
                g3_schools = []
        if g3_schools is not None:
            result["고3"] = g3_schools
        return result

    @staticmethod
    def scan_lectures():
        """고3 분석편에서 사용 가능한 강 목록 스캔."""
        cfg = _load_config()
        wb_base = os.path.expanduser(cfg.get("고3_workbook_base", ""))
        if not os.path.isdir(wb_base):
            return []
        from engines.final.scope_parser import parse_lectures_from_filename
        all_lectures = []
        for f in os.listdir(wb_base):
            if not f.endswith(".indd") or "분석편" not in _nfc(f):
                continue
            lectures = parse_lectures_from_filename(f)
            all_lectures.extend(lectures)
        # 숫자 강은 숫자 정렬, test는 뒤로
        def _sort_key(x):
            try:
                return (0, int(x))
            except ValueError:
                return (1, x)
        return sorted(set(all_lectures), key=_sort_key)

    # ── 파이프라인: parse ──

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()
        school = unicodedata.normalize("NFC", self._get_meta(job_dir, "school", ""))
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", "")
        exam_period = resolve_exam_period(cfg, exam_period)

        log(f"[설정] 학교={school}, 학년={grade}, 시험={exam_period}")

        # 고3: 구글시트 시험범위에서 강 목록 자동 조회 (파일 필터링 및 블록 필터링에 사용)
        selected_lectures = None
        exclude_gateway = False
        textbook_lessons = []  # 교과서 과 번호 (예: ["2"])
        textbook_raw = ""
        lecture_details = {}  # 강별 지문번호 필터 (예: {"4": ["2","4"], "test1": ["3","4","6",...]})
        if grade == "고3":
            from engines.final.vocab_fetcher import fetch_high3_scope
            scope_info = fetch_high3_scope(school, log=log, exam_period=exam_period)
            selected_lectures = scope_info["lectures"] + scope_info["tests"]
            exclude_gateway = scope_info["exclude_gateway"]
            textbook_lessons = scope_info.get("textbook_lessons", [])
            textbook_raw = scope_info.get("textbook_raw", "")
            lecture_details = scope_info.get("lecture_details", {})
            if not selected_lectures and not textbook_raw:
                raise ValueError(
                    f"구글시트 시험범위에서 {school}의 고3 범위를 찾지 못했습니다. "
                    "시험범위 시트의 '부교재 및 수능특강' 또는 '교과서' 컬럼을 확인하세요."
                )
        else:
            # 고1/고2: config의 school_textbook_map에서 과 번호 추출
            _cfg_tmp = _load_config()
            _school_info = (_cfg_tmp.get("school_textbook_map", {}) or {}).get(exam_period, {}).get(school, {})
            _cfg_lessons = _school_info.get("lessons", []) or []
            # "3과" → "3", "S1과" → "S1"
            textbook_lessons = [re.sub(r"\uacfc$", "", l).strip() for l in _cfg_lessons]

        # 1) 워크북 파일 감지
        wb_files, wb_dir, allowed_olpo_lectures = self.find_workbook_files(
            cfg["gdrive_base"], exam_period, grade, school
        )
        if not wb_files:
            raise FileNotFoundError(f"워크북 파일을 찾을 수 없습니다: {wb_dir}")

        log(f"[감지] {len(wb_files)}개 워크북:")
        for f in wb_files:
            log(f"  • {os.path.basename(f)}")

        # 고3: 선택된 강이 포함된 파일만 필터링
        # 교과서 분석편(파일명에 "N과" 포함)은 textbook_raw가 있고 lesson 매치되면 포함
        if grade == "고3":
            from engines.final.scope_parser import parse_lectures_from_filename
            filtered = []
            for f in wb_files:
                base = unicodedata.normalize("NFC", os.path.basename(f))
                # 교과서 분석편 판별: 파일명에 "N과" 포함
                tb_m = re.search(r"(\d+(?:\s*,\s*\d+)*)\s*과", base)
                is_textbook = bool(tb_m)
                if is_textbook and textbook_raw:
                    # 파일의 과 번호와 scope textbook_lessons 교집합 체크
                    file_lessons = [p.strip() for p in tb_m.group(1).split(",") if p.strip()]
                    if not textbook_lessons:  # scope에 과 번호 미기재 → 전체 포함
                        filtered.append(f)
                    elif any(l in textbook_lessons for l in file_lessons):
                        filtered.append(f)
                    continue
                # 수능특강 분석편 — 강 번호 필터
                if selected_lectures:
                    file_lectures = parse_lectures_from_filename(base)
                    if any(l in selected_lectures for l in file_lectures):
                        filtered.append(f)
            wb_files = filtered
            log(f"[고3] 필터링 후: {len(wb_files)}개 파일")

        # 2) 시험범위 파싱 + 어법수정 소스 결정
        from engines.final.scope_parser import parse_all_scopes
        scopes = parse_all_scopes(wb_files)
        log("[범위] 시험범위 분석:")
        for s in scopes:
            log(f"  • {s['scope']} → {s['type']} (어법수정: {s['grammar_source']})")

        # 2.5) 고2 올포기출 xlsx 매핑 미리 로드 (어법수정·문장배열·중요어휘 모두 사용)
        # 시트: EBS 작업/올림포스 고2 기출/고2 올림포스 기출 지문 출처 *.xlsx
        # 매핑: YYMMQQ → (강, 본문라벨)
        _olpo_lecture_map = None
        if grade == "고2" and allowed_olpo_lectures:
            try:
                from engines.final.olpo_mapper import (
                    find_olpo_xlsx_path, load_olpo_lecture_map
                )
                _xlsx_path = find_olpo_xlsx_path(cfg.get("gdrive_content_base", ""))
                if _xlsx_path:
                    _olpo_lecture_map = load_olpo_lecture_map(_xlsx_path, "2026", log=log)
            except Exception as _e_olm:
                log(f"[OLPO MAP] 로드 실패: {_e_olm}")

        # 3) InDesign으로 텍스트 추출
        from engines.final.extractor import extract_from_workbooks
        extracted_path = os.path.join(job_dir, "extracted.json")
        extract_styles = cfg.get("고3_extract_styles", cfg["extract_styles"]) if grade == "고3" else cfg["extract_styles"]
        # 기존 extracted.json 재사용 옵션 (_REUSE_EXTRACTED 환경변수)
        if os.environ.get("_REUSE_EXTRACTED") and os.path.exists(extracted_path):
            log(f"[추출] 기존 extracted.json 재사용: {extracted_path}")
        else:
            extract_from_workbooks(
                wb_files, extract_styles, extracted_path, log
            )

        # 학교 자체 '올림포스NN강' 워크북의 올포 강 번호 — 중요어휘 fetch 보강용.
        # (allowed_olpo_lectures는 '올포' 파일명 기반이라 '올림포스' 학교 워크북에선 비어
        #  올포 중요어휘가 통째로 누락된다. extracted 올포 스토리의 lecture로 union 보강.)
        _extracted_olpo_lectures = set()
        try:
            from engines.final.parser import _src_is_olpo as _is_olpo_fn
            with open(extracted_path, encoding="utf-8") as _exf:
                for _st in json.load(_exf).get("stories", []):
                    _lec = _st.get("lecture", 0)
                    if _lec and _lec > 0 and _is_olpo_fn(_st.get("source_file", "")):
                        _extracted_olpo_lectures.add(_lec)
        except Exception:
            pass

        # 4) 어법수정 Word 파일 수집 — 소스 유형별 분기
        #    + 교과서 과별 본문 수 카운트 (문장배열 과 경계 ground truth)
        lesson_block_counts = {}  # {"1": 6, "2": 6} — 과번호 → 본문 수
        sl_section_headers = []  # SL 블록의 실제 섹션 헤더 (어법수정 Word 기준)
        from engines.final.grammar_word_parser import (
            find_grammar_word_files, find_mockexam_grammar_files,
            find_ebs_grammar_files, parse_grammar_word
        )
        content_base = cfg.get("gdrive_content_base", "")
        grammar_word_lines = []
        # 고2 올포기출 → 모의고사 docx 매핑 시 사용 (시험범위 16지문 set)
        _olpo_target_codes_set = None
        # 같은 워드 파일이 여러 scope에서 매칭되는 케이스(예: "모의고사25.3"과 "25년3월02"가
        # 같은 25년3월 어법수정 워드를 가리킴) 대비 — 모든 scope를 가로질러 dedup.
        _seen_word_files = set()

        # 혼합 scope(교과서+EBS가 한 워크북에 공존, 예: '리딩파워19강,미래엔김4과') 대응:
        # classify_scope가 'textbook'으로만 분류해 EBS 강 어법수정이 통째로 누락되므로,
        # 어법수정 로딩 한정으로 EBS 성분을 별도 ebs scope 항목으로 펼쳐 둘 다 로딩한다.
        _grammar_scopes = []
        for _gs in scopes:
            _grammar_scopes.append(_gs)
            if _gs.get("type") == "textbook" and _gs.get("grammar_source") == "word_file":
                _ebs_sub = _extract_ebs_subscope(_gs.get("scope", ""))
                if _ebs_sub:
                    _ebs_type = ("ebs_readingpower"
                                 if ("리딩파워" in _ebs_sub or "Reading" in _ebs_sub)
                                 else "ebs_olympos")
                    _grammar_scopes.append({
                        "file": _gs.get("file"), "scope": _ebs_sub,
                        "type": _ebs_type, "grammar_source": "word_file",
                    })
                    log(f"  [어법수정] 혼합 scope EBS 성분 분리 로딩: "
                        f"'{_gs.get('scope')}' → '{_ebs_sub}' ({_ebs_type})")

        for s in _grammar_scopes:
            if s["grammar_source"] != "word_file":
                continue  # 마더텅 등 workbook_a1 소스는 스킵

            scope_type = s["type"]
            scope_text = s["scope"]

            word_files = []
            if scope_type == "textbook":
                # 교과서 → 교과서 작업 폴더 (과별로 개별 탐색하여 레슨 추적)
                textbook_info = cfg.get("school_textbook_map", {}).get(exam_period, {}).get(school)
                if textbook_info:
                    for lesson in textbook_info["lessons"]:
                        lesson_files = find_grammar_word_files(
                            content_base,
                            textbook_info["subject"],
                            textbook_info["publisher"],
                            [lesson],
                            log=log
                        )
                        for lf in lesson_files:
                            word_files.append((lf, lesson))
                    # 워크북 파일에서 Project N 추출 → 별도 단원으로 어법수정 탐색
                    project_labels = set()
                    for _wb in wb_files:
                        _base = unicodedata.normalize("NFC", os.path.basename(_wb))
                        m_proj = re.search(r"Project\s*(\d+)", _base, re.IGNORECASE)
                        if m_proj:
                            project_labels.add(f"Project {m_proj.group(1)}")
                    for proj_lesson in sorted(project_labels):
                        proj_files = find_grammar_word_files(
                            content_base,
                            textbook_info["subject"],
                            textbook_info["publisher"],
                            [proj_lesson],
                            log=log
                        )
                        for pf in proj_files:
                            word_files.append((pf, proj_lesson))
                else:
                    log(f"  [어법수정] 학교-교재 매핑 없음 ({school})")

            elif scope_type == "mockexam":
                # 모의고사 → 모의고사 작업 폴더
                word_files = find_mockexam_grammar_files(
                    content_base, scope_text, grade, log=log
                )
                # 시험범위 시트에서 정확한 문항번호 추출 (짧은 지문 필터링용)
                from engines.final.vocab_fetcher import fetch_scope_for_school
                allowed_qnums = set()
                try:
                    exams = fetch_scope_for_school(school, log=None, exam_period=exam_period)
                    for e in exams:
                        allowed_qnums.update(e["numbers"])
                except Exception:
                    pass
                if allowed_qnums:
                    log(f"  [어법수정] 모의고사 허용 문항: {sorted(allowed_qnums)}")
                else:
                    log(f"  [어법수정] 시험범위 문항번호 미확인 — 전체 포함")

            elif scope_type in ("ebs_olympos", "ebs_readingpower"):
                # 고2 ebs_olympos = 사실상 모의고사 (학평 기출 지문 모음).
                # xlsx 매핑으로 시험범위 강에 해당하는 16개 YYMMQQ 코드 산출 후
                # 모의고사 작업/{YY}년 {MM}월/ 폴더의 어법수정 docx에서 본문 추출.
                if scope_type == "ebs_olympos" and grade == "고2" and _olpo_lecture_map:
                    # 시험범위 코드 = 워크북01에서 추출된 examCode (= 학교 시험범위 정확)
                    # xlsx 전체에서 가져오면 16번까지 모두 들어옴(36개) → 워크북 codes로 한정.
                    _target_codes = []
                    try:
                        with open(extracted_path, encoding="utf-8") as _exf:
                            _ext_data = json.load(_exf)
                        _seen_ec = set()
                        for _st in _ext_data.get("stories", []):
                            _src = unicodedata.normalize("NFC", _st.get("source_file", ""))
                            if "올포" not in _src:
                                continue
                            _ec = _st.get("examCode", "")
                            if _ec and _ec not in _seen_ec:
                                _seen_ec.add(_ec)
                                _target_codes.append(_ec)
                    except Exception as _e:
                        log(f"  [어법수정] 고2 올포 코드 수집 실패: {_e}")
                    log(f"  [어법수정] 고2 올포 → 모의고사 docx 매핑: 대상 코드 {len(_target_codes)}개 ({sorted(_target_codes)})")
                    # YYMM 별 모의고사 어법수정 docx 수집 (passage_codes 기반)
                    from engines.final.grammar_word_parser import (
                        find_mockexam_grammar_files_by_codes
                    )
                    _ym_files = find_mockexam_grammar_files_by_codes(
                        content_base, grade, sorted(_target_codes), log=log
                    )
                    for _p, _ym in _ym_files:
                        word_files.append((_p, _ym))
                    # scope_type을 "mockexam"으로 오버라이드 → 아래 처리 로직 재사용
                    scope_type = "mockexam"
                    # 16개 YYMMQQ 코드만 유지 (allowed_qnums 대신 전체 코드 set 사용)
                    _olpo_target_codes_set = set(_target_codes)
                    allowed_qnums = set()
                else:
                    # 고1 EBS / 리딩파워 / 독해기본 — 기존 로직
                    word_files = find_ebs_grammar_files(
                        content_base, scope_text, log=log, grade=grade
                    )
                    _olpo_target_codes_set = None

            elif scope_type == "external":
                # TED 외부지문 → 학교별 '외부지문 TED' 폴더의 어법수정 Word
                from engines.final.grammar_word_parser import find_external_ted_grammar_files
                ted_paths = find_external_ted_grammar_files(
                    content_base, grade, school, exam_period, log=log
                )
                # (path, "TED") 형태로 저장해 아래 분기에서 TED1 라벨링
                for tp in ted_paths:
                    word_files.append((tp, "TED"))

            for wf_item in word_files:
                # textbook: (path, lesson_str), ebs: (path, lecture_int)
                # mockexam: (path, "YYMM"), 나머지(외부지문 TED 등): (path, "TED") or plain path
                lesson_name = None
                ebs_lecture = None
                mockexam_yymm = None  # 복합 scope 대응 — 파일별 (yy, mm)
                if isinstance(wf_item, tuple):
                    wf = wf_item[0]
                    meta = wf_item[1] if len(wf_item) > 1 else None
                    if isinstance(meta, str):
                        # mockexam은 "YYMM" 4자리 숫자, 나머지(textbook/external)는 비숫자
                        if scope_type == "mockexam" and re.fullmatch(r"\d{4}", meta):
                            mockexam_yymm = meta
                        else:
                            lesson_name = meta
                    elif isinstance(meta, int):
                        ebs_lecture = meta
                else:
                    wf = wf_item

                # 동일 파일 중복 처리 방지
                # (경로+강 번호로 구분 — 같은 파일명이 다른 폴더/강에 있을 수 있음: 리딩파워 Unit1~N 어법수정)
                wf_key = (wf, ebs_lecture if ebs_lecture is not None else lesson_name)
                if wf_key in _seen_word_files:
                    log(f"  [어법수정] 중복 파일 스킵: {os.path.basename(wf)}")
                    continue
                _seen_word_files.add(wf_key)

                # Google Drive 스트림 파일은 /tmp로 복사 후 사용
                # Drive Stream은 미적재 파일에 read syscall이 들어오면 EDEADLK 반환 →
                # _gdrive_safe_copy는 6가지 syscall 경로(python rw/cat/dd/cp/ditto/rsync)
                # + 지수 백오프 재시도(최대 95s 대기)로 우회.
                if "GoogleDrive" in wf or "Google Drive" in wf or "CloudStorage" in wf:
                    from engines.final.extractor import _gdrive_safe_copy
                    local_copy = f"/tmp/final_word_{os.getpid()}_{os.path.basename(wf)}"
                    copied, last_err = _gdrive_safe_copy(wf, local_copy, log=log)
                    if copied:
                        wf = local_copy
                        log(f"  [어법수정] GDrive -> /tmp 복사: {os.path.basename(wf)} ({os.path.getsize(wf)} bytes)")
                    else:
                        # GDrive 파일을 못 가져오면 데이터가 누락된 채 조판되므로 즉시 중단.
                        msg = (f"GDrive 어법수정 파일 복사 실패 (5회 재시도): "
                               f"{os.path.basename(wf)} — 마지막 오류: {last_err}")
                        log(f"  [오류] {msg}")
                        raise RuntimeError(msg)

                # 올포 강 필터: allowed_olpo_lectures에 없는 강은 스킵 (공용 파일에서 불필요한 Unit 제외)
                if (scope_type == "ebs_olympos" and ebs_lecture is not None
                        and allowed_olpo_lectures and ebs_lecture not in allowed_olpo_lectures):
                    log(f"  [어법수정] 올포 {ebs_lecture}강 스킵 (허용 범위 밖)")
                    continue
                # auto_unit_base: 리딩파워 Chapter 헤더 없는 파일에서 페이지 점프로 Unit 자동 증가
                # (예: Example 제외 워크북 파일 = 9강 p68-p71, 10강 p74-p77, 11강 p80-p81)
                _auto_base = ebs_lecture if scope_type == "ebs_readingpower" else None
                blocks = parse_grammar_word(wf, auto_unit_base=_auto_base)
                # 올포: 강별 본문 번호 카운터 (N강 본문1, N강 본문2, ...)
                ebs_body_counter = 0
                # 교과서(비SL): 블록 순서 기반 본문 카운터
                tb_body_counter = 0
                # TED 외부지문: "TED1 본문N" 카운터
                ted_body_counter = 0
                # 교과서: 과별 본문 수 카운트 (ground truth)
                if scope_type == "textbook" and lesson_name:
                    lesson_num = re.sub(r"과$", "", lesson_name.strip())
                    # S1, S2 등 → "SL"로 정규화 (일관된 키)
                    if lesson_num.startswith("S") and lesson_num[1:].isdigit():
                        lesson_num = "SL"
                    valid_count = sum(
                        1 for b2 in blocks
                        if (b2.get("text") or "").strip()
                        and (b2.get("text") or "").strip().upper() not in
                            ("READING", "READ", "READ MORE", "READ MORE!")
                    )
                    if valid_count > 0:
                        lesson_block_counts[lesson_num] = valid_count
                        log(f"  [어법수정] {lesson_name}: {valid_count}개 본문 감지")
                    # SL: 실제 섹션 헤더 저장 (본문1~2, 본문3 등 → 문장배열/삽입 매핑용)
                    if lesson_num == "SL":
                        for b2 in blocks:
                            t2 = (b2.get("text") or "").strip()
                            if not t2 or t2.upper() in ("READING", "READ", "READ MORE", "READ MORE!"):
                                continue
                            h2 = b2.get("header", "")
                            if h2:
                                h2 = _convert_grammar_header(h2, scope_text, scope_type)
                                sl_section_headers.append(h2)
                        log(f"  [어법수정] SL 섹션 헤더: {sl_section_headers}")

                for b in blocks:
                    text_content = (b.get("text") or "").strip()
                    # 섹션 제목만 있고 본문이 없는 블록 스킵 (예: "READING")
                    if not text_content or text_content.upper() in ("READING", "READ", "READ MORE", "READ MORE!"):
                        continue
                    # 본문 내부 섹션 제목 라인 제거 (예: 본문 중간의 단독 "READ", "READING" 줄)
                    _filtered_lines = []
                    for _line in text_content.split("\n"):
                        _s = _line.strip()
                        if _s and _s.upper() not in ("READING", "READ", "READ MORE", "READ MORE!"):
                            _filtered_lines.append(_line)
                    text_content = "\n".join(_filtered_lines).strip()
                    if not text_content:
                        continue
                    if text_content:
                        # 헤더가 있으면 먼저 추가 (지문 구분용)
                        hdr = b.get("header", "")
                        if hdr:
                            # 교과서(비SL): Word 블록 순서를 본문N으로 매핑
                            # — 원본 헤더가 "L1-p.17" 같은 페이지 번호 형식이므로
                            #   블록 순서대로 "교과서N과 본문1..K"를 부여한다.
                            _is_tb_nonsl = (
                                scope_type == "textbook" and lesson_name
                                and not (
                                    lesson_name.strip().startswith("S")
                                    and lesson_name.strip()[1:].rstrip("과").isdigit()
                                )
                                and lesson_name.strip().rstrip("과") != "SL"
                            )
                            # 올포 EBS: 원고 헤더 기반 변환 (본문/분석/서술형/논술형)
                            if _is_tb_nonsl:
                                _lesson_num_raw = re.sub(r"과$", "", lesson_name.strip())
                                # Project N 단원: "교과서ProjectN 본문M" 형식
                                _m_proj_lesson = re.match(r"(?:Project|PROJECT)\s*(\d+)", _lesson_num_raw)
                                if _m_proj_lesson:
                                    _proj_num = _m_proj_lesson.group(1)
                                    if re.search(r"Read\s*More", hdr, re.IGNORECASE):
                                        hdr = f"\uad50\uacfc\uc11cProject{_proj_num} RM"
                                    elif re.search(r"Further\s*Reading", hdr, re.IGNORECASE):
                                        hdr = f"\uad50\uacfc\uc11cProject{_proj_num} FR"
                                    else:
                                        tb_body_counter += 1
                                        hdr = f"\uad50\uacfc\uc11cProject{_proj_num} \ubcf8\ubb38{tb_body_counter}"
                                # Word 원고 헤더 변환:
                                # "Read More" → RM (미래엔 김 등), "Further Reading" → FR (YBM 박 등)
                                elif re.search(r"Read\s*More", hdr, re.IGNORECASE):
                                    hdr = f"\uad50\uacfc\uc11c{_lesson_num_raw}\uacfc RM"
                                elif re.search(r"Further\s*Reading", hdr, re.IGNORECASE):
                                    hdr = f"\uad50\uacfc\uc11c{_lesson_num_raw}\uacfc FR"
                                else:
                                    tb_body_counter += 1
                                    hdr = f"\uad50\uacfc\uc11c{_lesson_num_raw}\uacfc \ubcf8\ubb38{tb_body_counter}"
                            elif scope_type == "external" and lesson_name == "TED":
                                # TED 외부지문: 헤더에 TED 지문번호가 있으면 그걸 사용
                                # Word 헤더 형식: "1. TED 1-no.1", "2. TED 1-no.2" ...
                                # "본문" 같은 교재 제목성 헤더는 스킵
                                m_ted = re.search(r"TED\s*(\d+)\s*-\s*no\.?\s*(\d+)", hdr, re.IGNORECASE)
                                if m_ted:
                                    ted_wb = m_ted.group(1)
                                    ted_body = m_ted.group(2)
                                    hdr = f"TED{ted_wb} \ubcf8\ubb38{ted_body}"
                                elif hdr.strip() in ("\ubcf8\ubb38", "\uc804\uccb4"):
                                    # 교재 제목 블록: 스킵 (본문 없이 헤더만 추가 금지)
                                    continue
                                else:
                                    ted_body_counter += 1
                                    hdr = f"TED1 \ubcf8\ubb38{ted_body_counter}"
                            elif ebs_lecture is not None and scope_type in ("ebs_olympos", "ebs_readingpower"):
                                # Word 블록에 "unit" 정보가 있으면 (Chapter 헤더에서 추출) 그걸 우선 사용.
                                # 예: "Chapter 03. 추론적 이해 - 09 빈칸 추론" → unit=9
                                # Unit 9~11 통합 Word 파일에서 강별로 올바르게 분배됨.
                                _block_unit = b.get("unit")
                                _eff_lec = _block_unit if _block_unit is not None else ebs_lecture
                                hdr = _convert_grammar_header(hdr, scope_text, scope_type,
                                                              ebs_lecture=_eff_lec)
                            else:
                                # "1. L2-본문1" → "2과 본문1" 변환
                                # 복합 scope mockexam은 파일별 yymm으로 시기 식별
                                # (예: "26년3월,25년6월" workbook의 25년6월 Word는 mockexam_yymm="2506")
                                _eff_scope_text = scope_text
                                if mockexam_yymm:
                                    _eff_scope_text = (
                                        f"{mockexam_yymm[:2]}년{int(mockexam_yymm[2:4])}월"
                                    )
                                hdr = _convert_grammar_header(hdr, _eff_scope_text, scope_type)

                            # SL 등 레슨 이름이 헤더에 반영 안 된 경우 보완
                            if lesson_name and hdr in ("본문", "전체"):
                                lesson_num_raw = re.sub(r"과$", "", lesson_name.strip())
                                if lesson_num_raw.startswith("S"):
                                    hdr = f"교과서SL {hdr}"
                                else:
                                    hdr = f"{lesson_num_raw}과 {hdr}"

                            # 모의고사 문항번호 필터링 (시험범위 밖 문항 제외)
                            if scope_type == "mockexam" and allowed_qnums:
                                # hdr = "251020" or "251041~42"
                                m_qq = re.match(r"^\d{4}(\d{2})(?:~(\d{2}))?$", hdr)
                                if m_qq:
                                    qq1 = int(m_qq.group(1))
                                    qq2 = int(m_qq.group(2)) if m_qq.group(2) else qq1
                                    # 범위 내 하나라도 포함되면 허용
                                    in_range = any(q in allowed_qnums for q in range(qq1, qq2 + 1))
                                    if not in_range:
                                        log(f"  [어법수정] 문항 {qq1}{'~'+str(qq2) if qq2!=qq1 else ''} 제외 (범위 밖)")
                                        continue

                            # 고2 올포기출: 16개 정확 YYMMQQ 셋 외 코드는 제외
                            if _olpo_target_codes_set:
                                _hdr_base = hdr.split("~")[0][:6]
                                if _hdr_base not in _olpo_target_codes_set:
                                    continue
                                # 헤더를 "올포 N강 본문M" 형식으로 변환 (xlsx 매핑)
                                if _olpo_lecture_map:
                                    _info = _olpo_lecture_map.get(_hdr_base)
                                    if _info:
                                        hdr = f"올포 {_info[0]}강 {_info[1]}"

                            grammar_word_lines.append(hdr)
                        grammar_word_lines.append(text_content)

        # 4.5) 마더텅 예전 기출 어법수정 Word 보충
        # scope 순회에서 못 찾은 구지문(2018~2019 등)을
        # "한영고N 마더텅 예전 기출" 폴더의 3/4/5강 Word 파일에서 보충.
        # (전체 년월 폴더 스캔은 시험범위 밖 지문까지 추가되어 위험 → 마더텅 기출만 추가)
        try:
            with open("/tmp/_mt_debug.log", "a") as _dbgf:
                _dbgf.write(f"[MT-DEBUG] entering section grade={grade!r} content_base_exists={os.path.isdir(content_base)}\n")
        except Exception:
            pass
        if grade in ("\uace01", "\uace02"):
            from engines.final.grammar_word_parser import (
                find_mothertongue_grammar_files,
                find_mockexam_grammar_files_by_codes,
            )
            _existing_yymmqq = set()
            for _line in grammar_word_lines:
                _m_yy = re.match(r"^(\d{6})(?:~\d+)?$", _line.strip())
                if _m_yy:
                    _existing_yymmqq.add(_m_yy.group(1))
            # 고2 올포 → "올포 N강 본문M"으로 이미 변환된 코드도 _existing 으로 등록 (중복 방지)
            if _olpo_target_codes_set and _olpo_lecture_map:
                _existing_yymmqq.update(_olpo_target_codes_set)

            # 워크북 원고에서 추출된 YYMMQQ 수집 (extracted.json)
            _passage_codes = set()
            try:
                with open(extracted_path, encoding="utf-8") as _exf:
                    _ext_data = json.load(_exf)
                _code_pat = re.compile(r"^[\[{](\d{6})[\]}]$")
                for _st in _ext_data.get("stories", []):
                    for _p in _st.get("paras", []):
                        _t = (_p.get("t") or "").strip()
                        _cm = _code_pat.match(_t)
                        if _cm:
                            _passage_codes.add(_cm.group(1))
            except Exception as _e:
                log(f"  [\uc5b4\ubc95\uc218\uc815] passage_codes \uc218\uc9d1 \uc2e4\ud328: {_e}")

            # 마더텅 워크북 파일명의 섹션 번호 → _MT_MAP에서 전체 YYMMQQ 보충
            # (원고 헤더가 "{21}" 2자리만 있어도 워크북 전체 지문을 커버하기 위함)
            try:
                _wb_sections = set()
                for _wbf in wb_files:
                    _bname = unicodedata.normalize("NFC", os.path.basename(_wbf))
                    _ms = re.search(r"\ub9c8\ub354\ud145(\d+)", _bname)
                    if _ms:
                        _wb_sections.add(int(_ms.group(1)))
                if _wb_sections:
                    from engines.final.parser import (
                        load_mothertongue_map as _load_mt,
                        get_mothertongue_map as _get_mt,
                    )
                    _mt_paths_cfg = cfg.get("mothertongue_map_paths", {}) or {}
                    _load_mt(_mt_paths_cfg.get(grade))
                    _mt_full = _get_mt() or {}
                    for _sec in _wb_sections:
                        for _y in (_mt_full.get(_sec) or {}).values():
                            _passage_codes.add(_y)
            except Exception as _e:
                log(f"  [\uc5b4\ubc95\uc218\uc815] \ub9c8\ub354\ud145 \ubcf4\ucda9 \uc2e4\ud328: {_e}")

            extra_files = []
            # 1) passage_codes 기반 년월 폴더의 Word 파일 (scope에 없어도 추가)
            # 안전 가드: passage_codes가 비어있으면 전체 폴더 스캔 안 함
            # (시험범위에 모의고사 없는 학교에서 모든 모의고사 docx가 인입되는 사고 방지)
            if _passage_codes:
                try:
                    _ym_files = find_mockexam_grammar_files_by_codes(
                        content_base, grade, sorted(_passage_codes), log=log
                    )
                    for _p, _yymm in _ym_files:
                        extra_files.append((_p, _yymm, None))
                except Exception as _e:
                    log(f"  [\uc5b4\ubc95\uc218\uc815] \uc5f0\uc6d4 \ud3f4\ub354 \ud0d0\uc0c9 \uc2e4\ud328: {_e}")
            else:
                log(f"  [\uc5b4\ubc95\uc218\uc815] passage_codes \ube44\uc5b4\uc788\uc74c \u2014 \ubaa8\uc758\uace0\uc0ac \uc5f0\uc6d4 \ud3f4\ub354 \uc2a4\uce94 \uc0dd\ub7b5")
            # 2) 마더텅 예전 기출 (구지문 보충)
            try:
                _mt_files = find_mothertongue_grammar_files(content_base, grade, log=log)
                for _p, _section in _mt_files:
                    extra_files.append((_p, None, _section))
                try:
                    with open("/tmp/_mt_debug.log", "a") as _dbgf:
                        _dbgf.write(f"[MT-DEBUG] found {len(_mt_files)} files existing_yymmqq={sorted(_existing_yymmqq)} grammar_word_lines_len={len(grammar_word_lines)}\n")
                        _dbgf.write(f"[MT-DEBUG] first 20 grammar_word_lines: {grammar_word_lines[:20]}\n")
                except Exception:
                    pass
            except Exception as _e:
                log(f"  [\uc5b4\ubc95\uc218\uc815] \ub9c8\ub354\ud145 \uae30\ucd9c \ud0d0\uc0c9 \uc2e4\ud328: {_e}")
                try:
                    with open("/tmp/_mt_debug.log", "a") as _dbgf:
                        _dbgf.write(f"[MT-DEBUG] EXC: {_e}\n")
                except Exception:
                    pass

            _extra_added = 0
            _seen_extra_files = set()
            for _wf, _yymm, _section in extra_files:
                _wf_key = os.path.basename(_wf)
                if _wf_key in _seen_extra_files:
                    continue
                _seen_extra_files.add(_wf_key)
                # GDrive 파일 로컬 복사 — _gdrive_safe_copy로 통합
                # (6가지 syscall 경로 + 지수 백오프 재시도, 최대 95s 대기)
                if "GoogleDrive" in _wf or "Google Drive" in _wf or "CloudStorage" in _wf:
                    from engines.final.extractor import _gdrive_safe_copy
                    _local = f"/tmp/final_word_{os.getpid()}_{os.path.basename(_wf)}"
                    _copied, _last_err = _gdrive_safe_copy(_wf, _local, log=log)
                    if not _copied:
                        msg = (f"GDrive 어법수정 보충 파일 복사 실패: {_wf_key} — "
                               f"마지막 오류: {_last_err}")
                        log(f"  [\uc624\ub958] {msg}")
                        raise RuntimeError(msg)
                    _wf = _local

                try:
                    _blocks = parse_grammar_word(_wf)
                except Exception as _e:
                    log(f"  [\uc5b4\ubc95\uc218\uc815] \ud30c\uc2f1 \uc2e4\ud328 {_wf_key}: {_e}")
                    try:
                        with open("/tmp/_mt_debug.log", "a") as _dbgf:
                            _dbgf.write(f"[MT-DEBUG] parse fail {_wf_key}: {_e}\n")
                    except Exception:
                        pass
                    continue

                try:
                    with open("/tmp/_mt_debug.log", "a") as _dbgf:
                        _dbgf.write(f"[MT-DEBUG] file={_wf_key} blocks={len(_blocks)}\n")
                        for _bi, _bb in enumerate(_blocks):
                            _dbgf.write(f"  block[{_bi}] header={_bb.get('header','')!r}\n")
                except Exception:
                    pass

                for _b in _blocks:
                    _txt = (_b.get("text") or "").strip()
                    if not _txt or _txt.upper() in ("READING", "READ", "READ MORE", "READ MORE!"):
                        try:
                            with open("/tmp/_mt_debug.log", "a") as _dbgf:
                                _dbgf.write(f"  skip_empty_or_section header={_b.get('header','')!r}\n")
                        except Exception:
                            pass
                        continue
                    _hdr = _b.get("header", "")
                    # 마더텅 헤더 "1. p3강-no.4번 190920" → "190920"
                    _m_mt = re.search(r"(\d{6})\s*$", _hdr)
                    _has_gangno = ("\uac15-no" in _hdr) or ("\uac15\-no" in _hdr)
                    try:
                        with open("/tmp/_mt_debug.log", "a") as _dbgf:
                            _dbgf.write(f"  proc header={_hdr!r} m_mt={_m_mt.group(1) if _m_mt else None} has_gangno={_has_gangno}\n")
                    except Exception:
                        pass
                    if _m_mt and _has_gangno:
                        _hdr_yy = _m_mt.group(1)
                    elif _m_mt:
                        # 마더텅 5강 일부 이상 헤더: "1. p3-no.201122" (번/강 없이 끝에 YYMMQQ)
                        _hdr_yy = _m_mt.group(1)
                    elif _yymm:
                        _m_qq = re.search(r"no\.?\s*(\d+)", _hdr)
                        if not _m_qq:
                            continue
                        _qq = _m_qq.group(1).zfill(2)
                        _hdr_yy = f"{_yymm}{_qq}"
                    else:
                        continue
                    _m_comp = re.match(r"^(\d{4})(41|42)$", _hdr_yy)
                    if _m_comp:
                        _hdr_yy = f"{_m_comp.group(1)}41~42"
                    # 일반 모의고사 Word(_yymm 있음)만 passage_codes 필터 적용.
                    # 마더텅 예전 기출(_yymm=None)은 파일 자체가 구지문용이라 필터 제외.
                    if _yymm and _passage_codes:
                        _base = _hdr_yy.split("~")[0][:6]
                        if _base not in _passage_codes:
                            continue
                    if _hdr_yy in _existing_yymmqq:
                        try:
                            with open("/tmp/_mt_debug.log", "a") as _dbgf:
                                _dbgf.write(f"  skip_dup yy={_hdr_yy}\n")
                        except Exception:
                            pass
                        continue
                    _existing_yymmqq.add(_hdr_yy)
                    grammar_word_lines.append(_hdr_yy)
                    grammar_word_lines.append(_txt)
                    _extra_added += 1
                    try:
                        with open("/tmp/_mt_debug.log", "a") as _dbgf:
                            _dbgf.write(f"  ADD yy={_hdr_yy}\n")
                    except Exception:
                        pass
            if _extra_added > 0:
                log(f"[\uc5b4\ubc95\uc218\uc815] \ubcf4\ucda9 Word: {_extra_added}\uac1c \uc9c0\ubb38 \ucd94\uac00")

        if grammar_word_lines:
            log(f"[어법수정] Word에서 총 {len(grammar_word_lines)}개 지문 추출")

        # 5-ext) 외부지문/추가지문 어법수정 — 업로드된 '원고(docx)'에서 직접 파싱.
        #   외부/추가 지문은 출처·형식·제목이 매번 달라지므로(예전 'TED'도 그때 제목일
        #   뿐) 폴더 자동탐색/형식/헤더 하드코딩 대신 사용자가 원고를 업로드하고 거기서
        #   파싱한다. 라벨(본문N)은 원고에서 유도, 접두(외부지문/추가지문)는 스코프에서.
        try:
            _ext_doc = None
            if isinstance(uploaded_files, dict):
                for _k, _v in uploaded_files.items():
                    if re.search(r"external|외부|추가", _nfc(str(_k))):
                        _ext_doc = (_v[0] if isinstance(_v, list) and _v
                                    else (_v if isinstance(_v, str) else None))
                        if _ext_doc:
                            break
            if not _ext_doc:
                _updir = os.path.join(job_dir, "uploads")
                if os.path.isdir(_updir):
                    for _fn in sorted(os.listdir(_updir)):
                        if (_fn.lower().endswith(".docx")
                                and "어법수정" in _nfc(_fn)
                                and re.search(r"외부지문|추가지문|external", _nfc(_fn))):
                            _ext_doc = os.path.join(_updir, _fn)
                            break
            if _ext_doc:
                _ext_label = None
                for _s in scopes:
                    _m = re.search(r"(외부지문|추가지문)", _nfc(_s.get("scope", "")))
                    if _m:
                        _ext_label = _m.group(1)
                        break
                _ext_label = _ext_label or "외부지문"
                _ext_local = _ext_doc
                if any(x in _ext_doc for x in ("GoogleDrive", "Google Drive", "CloudStorage")):
                    from engines.final.extractor import _gdrive_safe_copy
                    _tmp = f"/tmp/final_extgram_{os.getpid()}.docx"
                    _ok, _err = _gdrive_safe_copy(_ext_doc, _tmp, log=log)
                    _ext_local = _tmp if _ok else None
                    if not _ok:
                        log(f"  [외부지문어법] 원고 GDrive 복사 실패: {_err}")
                if _ext_local:
                    from engines.final.grammar_word_parser import parse_external_grammar_docx
                    _ext_passages = parse_external_grammar_docx(_ext_local)
                    _added = 0
                    for _pp in _ext_passages:
                        _m2 = re.match(r"^본문(\d+)$", _pp.get("label", ""))
                        if not _m2:
                            # 'Reading …'/'Read More' 등 추가본문은 시험범위 밖(추가본문X) → 제외.
                            # 원고가 '본문 N'과 라벨을 구분하므로 본문N만 채택한다.
                            log(f"  [외부지문어법] 추가본문(Read More) 제외: {_pp.get('label', '')}")
                            continue
                        grammar_word_lines.append(f"{_ext_label} 본문{_m2.group(1)}")
                        grammar_word_lines.append(_pp.get("text", ""))
                        _added += 1
                    if _added:
                        log(f"[어법수정] 외부지문 원고 파싱: {_added}개 지문 추가 "
                            f"(접두='{_ext_label}', 파일={os.path.basename(_ext_doc)})")
        except Exception as _e:
            log(f"  [외부지문어법] 처리 실패: {_e}")

        # 5) 중요어휘 자동 추출
        vocab_left = ""
        vocab_right = ""
        if grade == "고3":
            # 고3: 중요어휘는 워크북 빈칸어휘(C2_빈칸 어휘)에서 추출 — parser에서 처리
            log("[중요어휘] 고3: 빈칸어휘에서 추출 (구글시트 스킵)")
        else:
            # 고1/고2: 구글시트에서 모의고사 범위 + 올포 강 범위 기반 추출
            try:
                from engines.final.vocab_fetcher import fetch_vocab_for_school
                # 올포 강 범위: allowed_olpo_lectures(공용 대체분) + extracted 올포 강(학교 올림포스 워크북)
                _olpo_lec_list = sorted((allowed_olpo_lectures or set()) | _extracted_olpo_lectures) or None
                # 워크북 파일 순서대로 (yy, mm) 페어 수집 → 중요어휘 정렬 순서로 사용
                # 복합 scope("23년6월_24년9월")는 모든 (yy, mm) 페어를 전부 추출.
                _workbook_order = []
                for _s in scopes:
                    if _s.get("type") != "mockexam":
                        continue
                    for _m_ym in re.finditer(r"(\d{2})년\s*(\d{1,2})월", _nfc(_s.get("scope", ""))):
                        _pair = (_m_ym.group(1), _m_ym.group(2).zfill(2))
                        if _pair not in _workbook_order:
                            _workbook_order.append(_pair)
                # 시험범위 시트(exams)의 기재 순서를 우선 사용.
                # 시트 기재 순서가 "23년3월, 24년9월, 23년6월, 25년3월"이면 그대로 사용.
                # 시트에 없고 워크북에만 있는 페어는 뒤에 유지.
                try:
                    from engines.final.vocab_fetcher import fetch_scope_for_school as _fssch
                    _sheet_exams = _fssch(school, log=None, exam_period=exam_period)
                    _sheet_order = []
                    for _ex in _sheet_exams:
                        _pair = (str(_ex.get("year", "")),
                                 str(_ex.get("month", "")).zfill(2))
                        if _pair not in _sheet_order:
                            _sheet_order.append(_pair)
                    if _sheet_order:
                        _reordered = [p for p in _sheet_order if p in _workbook_order]
                        _trailing = [p for p in _workbook_order if p not in _sheet_order]
                        _workbook_order = _reordered + _trailing
                except Exception:
                    pass
                # 중요어휘 순서를 다른 섹션(_canonical_order_key: YYMMQQ 오름차순)과 일치시킴
                _workbook_order = sorted(_workbook_order, key=lambda _p: (_p[0], _p[1]))
                # 마더텅 기반 학교용: 워크북 파일 순서 + _MT_MAP seq 순서대로 YYMMQQ 정렬
                # (Vol1 문장배열/영작 헤더 순서와 동일하게 중요어휘 배치하기 위함)
                _ordered_codes = []
                try:
                    from engines.final.parser import (
                        load_mothertongue_map as _load_mt_v,
                        get_mothertongue_map as _get_mt_v,
                    )
                    _load_mt_v(cfg.get("mothertongue_map_paths", {}).get(grade))
                    _mt_full_v = _get_mt_v() or {}
                    _wb_secs_v = []
                    for _wbf in wb_files:
                        _bname = unicodedata.normalize("NFC", os.path.basename(_wbf))
                        _ms = re.search(r"\ub9c8\ub354\ud145(\d+)", _bname)
                        if _ms:
                            _s = int(_ms.group(1))
                            if _s not in _wb_secs_v:
                                _wb_secs_v.append(_s)
                    for _s in _wb_secs_v:
                        _sec_map = _mt_full_v.get(_s) or {}
                        for _seq in sorted(_sec_map.keys()):
                            _y = _sec_map[_seq]
                            if _y not in _ordered_codes:
                                _ordered_codes.append(_y)
                    try:
                        with open("/tmp/_mt_debug.log", "a") as _df:
                            _df.write(f"[VOCAB-ORDER] sections={_wb_secs_v} ordered_count={len(_ordered_codes)} first5={_ordered_codes[:5]}\n")
                    except Exception:
                        pass
                except Exception as _e_ord:
                    try:
                        with open("/tmp/_mt_debug.log", "a") as _df:
                            _df.write(f"[VOCAB-ORDER] EXC: {_e_ord}\n")
                    except Exception:
                        pass

                # 리딩파워 강 범위: scope 텍스트("리딩파워3,5,6강")에서 파싱
                _rp_lectures = set()
                for _s_rp in scopes:
                    # 혼합 scope(교과서+리딩파워, 예: '리딩파워19강,미래엔김4과')도 포함하도록
                    # type 필터 대신 EBS 성분을 추출해 리딩파워 강을 수집한다.
                    _scope_txt = _extract_ebs_subscope(_s_rp.get("scope", "")) or ""
                    if not ("리딩파워" in _scope_txt or "Reading" in _scope_txt):
                        continue
                    # "리딩파워3,5,6강" / "리딩파워1-4강" / "리딩파워9-11" 등
                    _s_body = _scope_txt.replace("\ub9ac\ub529\ud30c\uc6cc", "").replace("Reading", "")
                    _s_body = _s_body.replace("\uac15", "").strip()
                    # "Example" 언급은 제거 (파일명에 Example이 있어도 강 번호 파싱은 숫자 위주)
                    _s_body = re.sub(r"Example", "", _s_body, flags=re.IGNORECASE)
                    for _part in _s_body.split(","):
                        _part = _part.strip()
                        if "-" in _part:
                            try:
                                _a, _b = _part.split("-")
                                _rp_lectures.update(range(int(_a), int(_b) + 1))
                            except Exception:
                                pass
                        elif _part.isdigit():
                            _rp_lectures.add(int(_part))
                _rp_lec_list = sorted(_rp_lectures) if _rp_lectures else None

                vocab_data = fetch_vocab_for_school(
                    school, grade, log=log,
                    olpo_lectures=_olpo_lec_list,
                    rp_lectures=_rp_lec_list,
                    workbook_order=_workbook_order,
                    passage_codes=_ordered_codes if _ordered_codes else None,
                    code_order=_ordered_codes if _ordered_codes else None,
                    exam_period=exam_period,
                )
                vocab_left = vocab_data.get("left_text", "")
                vocab_right = vocab_data.get("right_text", "")
                log(f"[중요어휘] 결과: 왼쪽 {len(vocab_left)}자, 오른쪽 {len(vocab_right)}자")
            except Exception as e:
                import traceback
                log(f"[중요어휘] 자동 추출 실패: {e}")
                log(f"  {traceback.format_exc()}")

        # 5.5) 모의고사 통합 워크북 파일에서 '문장삽입' 블록만 추가 추출
        #      현재 학교 워크북에는 문장삽입 섹션이 없는 모의고사 파일이 많으므로,
        #      "고1_25년_6월_전체(C).indd" 같은 통합 파일에서 발문 기준으로 추출한다.
        mock_insert_data = []
        mock_base = os.path.expanduser(cfg.get("mockexam_insert_base", ""))
        if mock_base and os.path.isdir(mock_base) and grade in ("고1", "고2"):
            # 시험범위에서 허용 문항번호 수집 (모의고사 scope만)
            try:
                from engines.final.vocab_fetcher import fetch_scope_for_school
                exams_info = fetch_scope_for_school(school, log=None, exam_period=exam_period)
            except Exception:
                exams_info = []

            # scope별로 처리
            _seen_mock_files = set()
            for s in scopes:
                if s["type"] != "mockexam":
                    continue
                scope_text = s["scope"]
                m_year = re.search(r"(\d{2})\uB144\s*(\d{1,2})\uC6D4", _nfc(scope_text))
                if not m_year:
                    continue
                yy = m_year.group(1)
                mm = m_year.group(2)
                mm_zero = mm.zfill(2)

                # 통합 파일 경로: 모의고사/{grade}/{grade}_{yy}년_{mm}월_전체(C).indd
                grade_dir = os.path.join(mock_base, grade)
                if not os.path.isdir(grade_dir):
                    continue
                target_file = None
                for fname in os.listdir(grade_dir):
                    fn_nfc = _nfc(fname)
                    if not fn_nfc.endswith(".indd"):
                        continue
                    if not fn_nfc.startswith(f"{grade}_{yy}\uB144"):
                        continue
                    if f"{yy}\uB144_{mm}\uC6D4_\uC804\uCCB4" not in fn_nfc and f"{yy}\uB144_{mm_zero}\uC6D4_\uC804\uCCB4" not in fn_nfc:
                        continue
                    target_file = os.path.join(grade_dir, fname)
                    break

                if not target_file:
                    log(f"[문장삽입] 통합 파일 없음: {grade}_{yy}년_{mm}월_전체")
                    continue
                if target_file in _seen_mock_files:
                    continue
                _seen_mock_files.add(target_file)

                # 이 scope의 허용 문항번호 수집
                # fetch_scope_for_school 반환 구조: {"grade", "year", "month", "numbers": [int...]}
                allowed_qnums = set()
                for e in exams_info:
                    if str(e.get("year", "")) != yy:
                        continue
                    if str(e.get("month", "")) != str(int(mm)):
                        continue
                    for n in e.get("numbers", []):
                        allowed_qnums.add(str(n))
                        # 41~42 같은 범위 문항도 허용 (qnum="41~42" 형태로 저장됨)
                        # → 추출 JSX에서 "41~42" 포함 검사를 따로 함

                if not allowed_qnums:
                    log(f"[문장삽입] 허용 문항번호 없음 → 전체 추출")
                else:
                    # 41~42 같은 범위 qnum도 매칭되도록 보조 세트 생성
                    # (추출기에서 qnum="41~42"면 41 또는 42가 allowed_qnums에 있으면 통과)
                    log(f"[문장삽입] 허용 문항번호: {sorted(int(x) for x in allowed_qnums if x.isdigit())}")

                from engines.final.extractor import extract_mock_insert_blocks
                blocks = extract_mock_insert_blocks(target_file, allowed_qnums, log)
                for b in blocks:
                    b["scope_text"] = scope_text
                mock_insert_data.extend(blocks)

        # 5.6) 교과서 문장삽입 추출 (워크북/교과서/{subject}/{publisher}/{subject}_{publisher}{N}과_내지.indd)
        tb_insert_data = []
        if grade in ("\uace01", "\uace02") and textbook_lessons:
            _school_cfg = (cfg.get("school_textbook_map", {}) or {}).get(exam_period, {}).get(school, {})
            _subject = _school_cfg.get("subject", "")
            _publisher = _school_cfg.get("publisher", "")
            if _subject and _publisher:
                # 로마자 → 숫자: "영어Ⅰ" → "영어1", "공통영어1" 유지
                _subject_file = _subject.replace("\u2160", "1").replace("\u2161", "2")
                _tb_base = os.path.join(
                    os.path.expanduser(cfg["gdrive_base"]),
                    "\uc6cc\ud06c\ubd81", "\uad50\uacfc\uc11c", _subject_file, _publisher
                )
                if os.path.isdir(_tb_base):
                    from engines.final.extractor import extract_mock_insert_blocks as _extract_ins
                    for _lesson in textbook_lessons:
                        _lesson_num = re.sub(r"\uacfc$", "", _lesson).strip()
                        _tb_file = os.path.join(
                            _tb_base,
                            f"{_subject_file}_{_publisher}{_lesson_num}\uacfc_\ub0b4\uc9c0.indd"
                        )
                        if os.path.exists(_tb_file):
                            log(f"[\uad50\uacfc\uc11c \ubb38\uc7a5\uc0bd\uc785] {os.path.basename(_tb_file)}")
                            _blks = _extract_ins(_tb_file, set(), log) or []
                            for _b in _blks:
                                _b["scope_text"] = f"\uad50\uacfc\uc11c{_lesson_num}\uacfc"
                                _b["is_textbook"] = True
                                _b["lesson_num"] = _lesson_num
                            tb_insert_data.extend(_blks)
                        else:
                            log(f"[\uad50\uacfc\uc11c \ubb38\uc7a5\uc0bd\uc785] \ud30c\uc77c \uc5c6\uc74c: {_tb_file}")
        # 교과서 insert를 mock_insert_data에 병합 (parser가 동일 경로 처리)
        mock_insert_data.extend(tb_insert_data)

        # 6) 추출 데이터 + Word 어법수정 + 중요어휘 → content.json
        from engines.final.parser import parse_extracted, load_mothertongue_map
        # 마더텅 워크북 쓰는 학교(한영 등)용 지문 출처 매핑 로드
        _mt_paths = cfg.get("mothertongue_map_paths", {}) or {}
        load_mothertongue_map(_mt_paths.get(grade))
        # 교과서 과별 본문 제한 (시험범위 시트의 "(N과는 본문M까지만 들어감)" 표기)
        _textbook_limits = {}
        if grade in ("\uace01", "\uace02"):
            try:
                from engines.final.vocab_fetcher import fetch_textbook_limits_for_school
                _textbook_limits = fetch_textbook_limits_for_school(school, log=log, exam_period=exam_period) or {}
            except Exception as _e_tl:
                log(f"[\uad50\uacfc\uc11c] \ubcf8\ubb38 \uc81c\ud55c \uc870\ud68c \uc2e4\ud328: {_e_tl}")

        # \uad50\uacfc\uc11c RM/FR \ud5c8\uc6a9 \uacfc set ((N\uacfc\ub294 Read More\ub3c4 \ud3ec\ud568) \ud45c\uae30 \uae30\ubc18)
        _textbook_rm_lessons = None
        if grade in ("\uace01", "\uace02"):
            try:
                from engines.final.vocab_fetcher import fetch_textbook_rm_lessons_for_school
                _textbook_rm_lessons = fetch_textbook_rm_lessons_for_school(school, log=log, exam_period=exam_period)
            except Exception as _e_rm:
                log(f"[\uad50\uacfc\uc11c] RM/FR \ud5c8\uc6a9 \uacfc \uc870\ud68c \uc2e4\ud328: {_e_rm}")
        # 리딩파워 Example 워크북용 강별 문제 수 (sheet 기반)
        _rp_lec_cnts = {}
        _rp_sheet = []
        if grade in ("\uace01", "\uace02"):
            try:
                from engines.final.vocab_fetcher import (
                    fetch_rp_lecture_problem_counts,
                    fetch_rp_sheet_data,
                )
                _rp_lec_cnts = fetch_rp_lecture_problem_counts(grade) or {}
                _rp_sheet = fetch_rp_sheet_data(grade) or []
                log(f"[\ub9ac\ub529\ud30c\uc6cc] \uc2dc\ud2b8 \ub370\uc774\ud130 {len(_rp_sheet)}\uac1c \uc9c0\ubb38 \ub85c\ub4dc")
            except Exception as _e_rp:
                log(f"[\ub9ac\ub529\ud30c\uc6cc] \uc2dc\ud2b8 \uc870\ud68c \uc2e4\ud328: {_e_rp}")

        # \uace02 \uc62c\ud3ec xlsx \ub9e4\ud551\uc740 step 2.5\uc5d0\uc11c \uc774\ubbf8 \ub85c\ub4dc\ub428 (_olpo_lecture_map)

        content_path = parse_extracted(
            extracted_path, vocab_left, vocab_right,
            school, grade, exam_period, job_dir, log,
            grammar_word_lines=grammar_word_lines,
            lesson_block_counts=lesson_block_counts,
            sl_section_headers=sl_section_headers,
            selected_lectures=selected_lectures,
            allowed_olpo_lectures=allowed_olpo_lectures,
            mock_insert_blocks=mock_insert_data,
            exclude_gateway=exclude_gateway,
            textbook_lessons=textbook_lessons,
            textbook_raw=textbook_raw,
            gdrive_content_base=cfg.get("gdrive_content_base", ""),
            lecture_details=lecture_details,
            rp_lecture_counts=_rp_lec_cnts,
            rp_sheet_data=_rp_sheet,
            textbook_limits=_textbook_limits,
            olpo_lecture_map=_olpo_lecture_map,
            textbook_rm_lessons=_textbook_rm_lessons,
        )

        # 6.1) 어법수정을 Vol1 문장배열 헤더 순서로 재정렬
        # (모든 섹션이 워크북 순서로 통일되도록)
        try:
            with open(content_path, encoding="utf-8") as _cf:
                _cdata = json.load(_cf)
            _v1_hdrs = [
                (b.get("header") or "").strip()
                for b in (_cdata.get("vol1", {}) or {}).get("\ubb38\uc7a5\ubc30\uc5f4", []) or []
            ]
            _g_lines = (_cdata.get("vol2", {}) or {}).get("\uc5b4\ubc95\uc218\uc815", [])
            if _v1_hdrs and _g_lines:
                def _is_hdr(_ln):
                    _s = _ln.strip()
                    return bool(
                        re.match(r"^\d{6}(?:~\d+)?$", _s) or
                        re.match(r"^\uad50\uacfc\uc11c", _s) or
                        re.match(r"^SL(\s|$)", _s) or
                        re.match(r"^S\d+\uacfc", _s) or
                        re.match(r"^\d{1,2}\uacfc\s", _s) or
                        re.match(r"^\d+\uac15\s", _s) or
                        re.match(r"^\uc62c\ud3ec\s+\d+\uac15", _s) or
                        re.match(r"^\ub9ac\ub529\ud30c\uc6cc\s+\d+\uac15", _s) or
                        re.match(r"^TED\d+\s+\ubcf8\ubb38\d+", _s) or
                        re.match(r"^(?:\uc678\ubd80\uc9c0\ubb38|\ucd94\uac00\uc9c0\ubb38)\s+\ubcf8\ubb38\d+", _s) or
                        re.match(r"^test\d+", _s, re.IGNORECASE)
                    )
                _blocks = {}
                _order_found = []
                _cur = None
                _skip_dup = False
                for _ln in _g_lines:
                    if _is_hdr(_ln):
                        _h = _ln.strip()
                        if _h in _blocks:
                            # 중복 헤더: 이 블록의 본문은 스킵 (이미 저장됨)
                            _cur = None
                            _skip_dup = True
                        else:
                            _blocks[_h] = []
                            _order_found.append(_h)
                            _cur = _h
                            _skip_dup = False
                    elif _cur and not _skip_dup:
                        _blocks[_cur].append(_ln)
                # Vol1에 있는 블록은 Vol1 순서 유지, Vol1에 없는 블록은 canonical_order_key로 올바른 위치에 삽입
                # (예: "리딩파워 3강 02"가 Vol1에 없어도 3강 01-03 사이에 정렬됨)
                from engines.final.parser import _canonical_order_key as _ck
                _used = set(_h for _h in _v1_hdrs if _h in _blocks)
                _missing = [_h for _h in _order_found if _h not in _used]
                # Vol1 순서 + canonical 순서로 missing 블록 병합
                _all_hdrs_in_order = [_h for _h in _v1_hdrs if _h in _blocks]
                for _mh in _missing:
                    _mkey = _ck(_mh)
                    # 같은 canonical 키 그룹 내에서 올바른 위치 찾기 (선두 삽입)
                    _inserted = False
                    for _i, _h in enumerate(_all_hdrs_in_order):
                        if _ck(_h) > _mkey:
                            _all_hdrs_in_order.insert(_i, _mh)
                            _inserted = True
                            break
                    if not _inserted:
                        _all_hdrs_in_order.append(_mh)
                _new_lines = []
                _new_hdrs = []
                for _h in _all_hdrs_in_order:
                    _new_lines.append(_h)
                    _new_lines.extend(_blocks[_h])
                    _new_hdrs.append(_h)
                _cdata["vol2"]["\uc5b4\ubc95\uc218\uc815"] = _new_lines
                _cdata["vol2"]["\uc5b4\ubc95_\ud5e4\ub354"] = _new_hdrs
                log(f"[\uc5b4\ubc95\uc218\uc815] Vol1+canonical \uc21c\uc11c\ub85c \uc7ac\uc815\ub82c: {len(_new_hdrs)}\uac1c \ud5e4\ub354 (missing {len(_missing)}\uac1c)")

            # 영작: canonical 순서로 직접 재정렬 (교과서→리딩파워→모의고사)
            # — Vol1 문장배열 기반 재정렬이 아니라 헤더 자체 기준으로 정렬 (straggler 방지)
            _wp = (_cdata.get("vol2", {}) or {}).get("\uc11c\uc220\ud615\uc601\uc791", []) or []
            _wd = (_cdata.get("vol2", {}) or {}).get("\uc601\uc791_\ud5e4\ub354_\uc0c1\uc138", []) or []
            if _wp and _wd:
                from engines.final.parser import _canonical_order_key as _ck
                # 각 헤더의 pairs 슬라이스 경계(_end)는 start_idx **오름차순**으로 잡아야
                # 정확하다. _wd가 추출/페이지 순서라 start_idx가 단조가 아니면
                # _wd[i+1].start_idx가 이 블록의 끝이 아니게 되어 옆 강 영작이 섞인다
                # (고3 영작 강-단위 변위 버그 방어 — 입력 순서와 무관하게 정확히 슬라이스).
                _by_start = sorted(range(len(_wd)),
                                   key=lambda _j: _wd[_j].get("start_idx", 0))
                _bnds = [_wd[_j].get("start_idx", 0) for _j in _by_start] + [len(_wp)]
                _w_blocks = {}
                _w_order = []
                for _rank, _j in enumerate(_by_start):
                    _hi = _wd[_j]
                    _hh = (_hi.get("header") or "").strip()
                    _start = _hi.get("start_idx", 0)
                    _end = _bnds[_rank + 1]
                    if _hh and _hh not in _w_blocks:
                        _w_blocks[_hh] = _wp[_start:_end]
                        _w_order.append(_hh)
                _sorted_hdrs = sorted(_w_order, key=lambda h: _ck(h))
                _new_wp = []
                _new_wd = []
                for _hh in _sorted_hdrs:
                    _new_wd.append({"header": _hh, "start_idx": len(_new_wp)})
                    _new_wp.extend(_w_blocks[_hh])
                _cdata["vol2"]["\uc11c\uc220\ud615\uc601\uc791"] = _new_wp
                _cdata["vol2"]["\uc601\uc791_\ud5e4\ub354_\uc0c1\uc138"] = _new_wd
                _cdata["vol2"]["\uc601\uc791_\ud5e4\ub354"] = [_h["header"] for _h in _new_wd]
                log(f"[\uc601\uc791] canonical \uc21c\uc11c\ub85c \uc7ac\uc815\ub82c: {len(_new_wd)}\uac1c \ud5e4\ub354")

            if _v1_hdrs and (_g_lines or (_wp and _wd)):
                with open(content_path, "w", encoding="utf-8") as _cf:
                    json.dump(_cdata, _cf, ensure_ascii=False, indent=2)
        except Exception as _e_rs:
            log(f"[\uc7ac\uc815\ub82c] \uc2e4\ud328: {_e_rs}")

        # 6.5) 중요어휘 폴백 — 1차(vocab_fetcher 모의고사 scope) 결과가 비어있을 때,
        # content.json의 YYMMQQ 지문 출처로 시기 시트를 직접 조회해 중요어휘 보강.
        # (한영1 등 마더텅 기반 학교: 시험범위 시트에 모의고사 컬럼이 없어도 워크북 지문 기반 추출)
        if grade != "\uace03":
            try:
                with open(content_path, encoding="utf-8") as f:
                    _content = json.load(f)
                _vol1 = _content.get("vol1", {})
                _has_vocab = bool(_vol1.get("\uc911\uc694\uc5b4\ud718_\uc67c")) or bool(_vol1.get("\uc911\uc694\uc5b4\ud718_\uc624"))
                if not _has_vocab:
                    _codes = set()
                    for _key in ("\ubb38\uc7a5\ubc30\uc5f4", "\ubb38\uc7a5\uc0bd\uc785"):
                        for _b in _vol1.get(_key, []) or []:
                            _h = (_b.get("header") or "").strip()
                            # YYMMQQ 형식(6자리 숫자)만
                            if len(_h) == 6 and _h.isdigit():
                                _codes.add(_h)
                            # 범위 헤더 "241041~42" → 앞 6자리만 사용
                            elif len(_h) >= 6 and _h[:6].isdigit():
                                _codes.add(_h[:6])
                    if _codes:
                        log(f"[중요어휘] 폴백: 지문 {len(_codes)}개 코드로 재추출 시도")
                        from engines.final.vocab_fetcher import fetch_vocab_for_school as _fetch_vocab_pc
                        _olpo_lec_list2 = sorted((allowed_olpo_lectures or set()) | _extracted_olpo_lectures) or None
                        _vd = _fetch_vocab_pc(
                            school, grade, log=log,
                            olpo_lectures=_olpo_lec_list2,
                            passage_codes=sorted(_codes),
                        )
                        _vl = _vd.get("left_text", "") or ""
                        _vr = _vd.get("right_text", "") or ""
                        if _vl or _vr:
                            if _vl:
                                _vol1["\uc911\uc694\uc5b4\ud718_\uc67c"] = _vl
                            if _vr:
                                _vol1["\uc911\uc694\uc5b4\ud718_\uc624"] = _vr
                            _content["vol1"] = _vol1
                            with open(content_path, "w", encoding="utf-8") as f:
                                json.dump(_content, f, ensure_ascii=False, indent=2)
                            log(f"[중요어휘] 폴백 주입: 왼쪽 {len(_vl)}자, 오른쪽 {len(_vr)}자")
                        else:
                            log("[중요어휘] 폴백: 결과 없음")
                    else:
                        log("[중요어휘] 폴백: 매칭 가능한 YYMMQQ 코드 없음")
            except Exception as _e:
                import traceback
                log(f"[중요어휘] 폴백 실패: {_e}")
                log(f"  {traceback.format_exc()}")

        # 6.6) 고2 올포 중요어휘 26올포기출 시트 주입 (xlsx 매핑된 (강,본문)별 본문/요약)
        # — 학교 워크북01 올포 16지문에 대응하는 중요어휘 데이터를 전용 시트에서 가져옴
        if grade == "고2" and _olpo_lecture_map:
            try:
                from engines.final.olpo_mapper import load_olpo_vocab_sheet
                vocab_map = load_olpo_vocab_sheet("26올포기출", log=log)
                if vocab_map:
                    with open(content_path, encoding="utf-8") as f:
                        _content = json.load(f)
                    _vol1 = _content.get("vol1", {})
                    # Vol1 문장배열의 올포 헤더 기준으로 중요어휘 데이터 매칭
                    # 기존 컨벤션: 좌/우 동일 텍스트 (본문+내용요약 결합)
                    _olpo_parts = []
                    for _b in _vol1.get("문장배열", []) or []:
                        _h = (_b.get("header") or "").strip()
                        # "올포 N강 본문M" 패턴
                        m = re.match(r"^올포\s+(\d+)강\s+(본문\d+)$", _h)
                        if not m:
                            continue
                        lec = int(m.group(1))
                        body = m.group(2)
                        v = vocab_map.get((lec, body))
                        if not v:
                            continue
                        _label = f"올포 {lec}강 {body}"
                        _body_text = v.get("body", "").strip()
                        _summary = v.get("summary", "").strip()
                        # 본문 + 내용요약 결합 (셀 원본 형식 보존)
                        _combined = _body_text
                        if _summary:
                            _combined = (
                                (_combined + "\n\n" if _combined else "")
                                + ">>   내용요약   \n"
                                + _summary
                            )
                        if _combined:
                            _olpo_parts.append(_label + "\n" + _combined)
                    if _olpo_parts:
                        new_text = "\n\n".join(_olpo_parts)
                        existing_left = _vol1.get("중요어휘_왼", "")
                        existing_right = _vol1.get("중요어휘_오", "")
                        _vol1["중요어휘_왼"] = (
                            existing_left + ("\n\n" if existing_left else "") + new_text
                        )
                        _vol1["중요어휘_오"] = (
                            existing_right + ("\n\n" if existing_right else "") + new_text
                        )
                        _content["vol1"] = _vol1
                        with open(content_path, "w", encoding="utf-8") as f:
                            json.dump(_content, f, ensure_ascii=False, indent=2)
                        log(f"[중요어휘] 26올포기출 주입: {len(_olpo_parts)}지문 (좌우 동일)")
            except Exception as _e:
                import traceback
                log(f"[중요어휘] 26올포기출 주입 실패: {_e}")
                log(f"  {traceback.format_exc()}")

        return content_path

    # ── 파이프라인: prepare_jsx ──

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        school = self._get_meta(job_dir, "school", "학교미선택")
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", "")
        exam_period = resolve_exam_period(cfg, exam_period)

        with open(json_path, encoding="utf-8") as f:
            content = json.load(f)

        # 출력 디렉터리: 조판/교재/파이널 직전보충/{학년}/{시험기간}/{학교명}/
        output_dir = os.path.join(
            STUDIO_ROOT, "조판", "교재", "파이널 직전보충",
            grade, exam_period, school
        )
        os.makedirs(output_dir, exist_ok=True)

        # Vol1/Vol2 템플릿 복사 + jobs 구성
        jobs = []
        for vol_key, tpl_key, vol_label in [
            ("vol1", "template_vol1", "Vol1"),
            ("vol2", "template_vol2", "Vol2"),
        ]:
            vol_data = content.get(vol_key, {})
            # 데이터가 있는 경우에만 생성
            has_data = any(vol_data.get(k) for k in vol_data if k not in ("", None))
            if not has_data:
                log(f"[내지] {vol_label}: 데이터 없음 — 건너뜀")
                continue

            template_src = cfg[tpl_key]
            indd_name = f"{school}_파이널({vol_label})_내지.indd"
            indd_path = os.path.join(output_dir, indd_name)
            indd_path = safe_copy_indd(template_src, indd_path)
            log(f"[내지] {vol_label}: {os.path.basename(indd_path)}")

            jobs.append({
                "vol": vol_key,
                "indd_path": indd_path,
                "data": vol_data,
            })

        if not jobs:
            raise ValueError("Vol1/Vol2 모두 데이터가 없습니다.")

        # .settings.json
        settings = {
            "jobs": jobs,
            "output_dir": output_dir,
            "school": school,
            "grade": grade,
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return settings_path

    # ── 파이프라인: run_indesign (stepper 방식) ──

    def run_indesign(self, job_dir, log):
        from engines.final.indesign_stepper import run_typeset
        settings_path = os.path.join(job_dir, ".settings.json")
        run_typeset(settings_path, log)

    # ── 파이프라인: verify ──

    def verify(self, job_dir, log):
        cfg = _load_config()
        log_path = os.path.join(job_dir, cfg["log_filename"])

        # content.json 통계
        content = {}
        cp = os.path.join(job_dir, "content.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                content = json.load(f)

        warnings = []
        overflow = 0
        indd_paths = []

        if os.path.exists(log_path):
            lc = open(log_path, encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r"오버플로우:\s*(\d+)개", lc):
                overflow += int(m.group(1))
            if overflow > 0:
                warnings.append(f"오버플로우 {overflow}개")

        # 내지(.indd) 수집 — 직전보충은 PDF 미생성, 인디자인 파일만 산출.
        # .settings.json의 jobs[].indd_path = 이번 실행에서 저장된 내지 (권위 있는 목록).
        sp = os.path.join(job_dir, ".settings.json")
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                settings = json.load(f)
            for _job in settings.get("jobs", []):
                _ip = _job.get("indd_path", "")
                if _ip and os.path.exists(_ip) and _ip not in indd_paths:
                    indd_paths.append(_ip)

        totals = {
            "문장배열": content.get("총_문장배열", 0),
            "어법수정": content.get("총_어법수정", 0),
            "서술형영작": content.get("총_서술형영작", 0),
        }
        stories = {k: {"actual": v, "expected": v} for k, v in totals.items()}

        # 블록 상세 요약 (UI 표시용)
        vol1 = content.get("vol1", {})
        vol2 = content.get("vol2", {})
        block_summary = {}

        _arr = vol1.get("문장배열", [])
        block_summary["문장배열"] = {
            "blocks": len(_arr),
            "items": sum(len(b.get("items", [])) for b in _arr),
            "headers": [b["header"] for b in _arr[:5]],
        }

        _ins = vol1.get("문장삽입", [])
        _ins_empty = sum(1 for b in _ins if not b.get("paras"))
        block_summary["문장삽입"] = {
            "blocks": len(_ins),
            "empty": _ins_empty,
        }

        _ghdrs = vol2.get("어법_헤더", [])
        block_summary["어법수정"] = {
            "lines": len(vol2.get("어법수정", [])),
            "headers": len(_ghdrs),
        }

        _wr = vol2.get("서술형영작", [])
        _wrh = vol2.get("영작_헤더_상세", [])
        block_summary["서술형영작"] = {
            "pairs": len(_wr),
            "headers": len(_wrh),
        }

        _vl = vol1.get("중요어휘_왼", "")
        _vr = vol1.get("중요어휘_오", "")
        _vocab_re = r"^(?:\d{6}|\uc62c\ud3ec\s+\d+\uac15)"
        block_summary["중요어휘"] = {
            "left": len(re.findall(_vocab_re, _vl, re.MULTILINE)) if _vl else 0,
            "right": len(re.findall(_vocab_re, _vr, re.MULTILINE)) if _vr else 0,
        }

        validation_warnings = content.get("_validation_warnings", [])

        # 범위 검증 리포트
        report_lines = ["=== 범위 검증 리포트 ==="]
        vol1 = content.get("vol1", {})
        vol2 = content.get("vol2", {})

        arr_blocks = vol1.get("문장배열", [])
        ins_blocks = vol1.get("문장삽입", [])
        report_lines.append(f"문장배열: {len(arr_blocks)}개")
        report_lines.append(f"  헤더: {', '.join(b['header'] for b in arr_blocks)}")
        report_lines.append(f"문장삽입: {len(ins_blocks)}개")
        arr_set = set(b["header"] for b in arr_blocks)
        ins_set = set(b["header"] for b in ins_blocks)
        if arr_set != ins_set:
            report_lines.append(f"  ⚠ 문장배열/삽입 불일치: 배열만={arr_set-ins_set}, 삽입만={ins_set-arr_set}")
        else:
            report_lines.append(f"  ✓ 문장배열/삽입 1:1 일치")

        # 중요어휘
        vocab_left = vol1.get("중요어휘_왼", "")
        vocab_nums = [p.strip()[:6] for p in vocab_left.split("\n") if re.match(r"^\d{6}", p.strip())] if vocab_left else []
        vocab_olp = [p.strip() for p in vocab_left.split("\n") if re.match(r"^\uc62c\ud3ec\s+\d+\uac15", p.strip())] if vocab_left else []
        vocab_count = len(vocab_nums) + len(vocab_olp)
        v_25_3 = [n for n in vocab_nums if n.startswith("2503")]
        v_25_6 = [n for n in vocab_nums if n.startswith("2506")]
        v_26_3 = [n for n in vocab_nums if n.startswith("2603")]
        report_lines.append(f"중요어휘: {vocab_count}개 지문 (25-3: {len(v_25_3)}, 25-6: {len(v_25_6)}, 26-3: {len(v_26_3)}, 올포: {len(vocab_olp)})")
        report_lines.append(f"  25-3: {', '.join(v_25_3)}")
        report_lines.append(f"  25-6: {', '.join(v_25_6)}")
        report_lines.append(f"  26-3: {', '.join(v_26_3)}")
        report_lines.append(f"  ※ 교과서는 중요어휘 대상 아님, 41~42 복합문항은 41번으로 포함")

        # Vol2
        grammar = vol2.get("어법수정", [])
        grammar_headers = vol2.get("어법_헤더", [])
        report_lines.append(f"어법수정: {len(grammar)}줄, {len(grammar_headers)}개 지문")
        report_lines.append(f"  헤더: {', '.join(grammar_headers[:10])}{'...' if len(grammar_headers)>10 else ''}")

        writing = vol2.get("서술형영작", [])
        writing_headers = vol2.get("영작_헤더_상세", [])
        report_lines.append(f"서술형영작: {len(writing)}쌍, {len(writing_headers)}개 지문")

        # 리포트 파일 저장
        report_path = os.path.join(job_dir, "scope_report.txt")
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("\n".join(report_lines))
        log("[리포트] " + report_path)
        for line in report_lines:
            log(f"  {line}")

        ok = len(indd_paths) > 0 and overflow == 0

        # 검증 경고가 있으면 ok를 warn으로 처리
        if validation_warnings:
            warnings.extend(validation_warnings)

        return {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "indd_path": indd_paths[0] if indd_paths else None,
            "indd_paths": indd_paths,
            "pdf_path": None,
            "warnings": warnings,
            "block_summary": block_summary,
            "validation_warnings": validation_warnings,
            "grade_label": f"내지 {len(indd_paths)}개 | 문장배열 {totals['문장배열']} | 어법수정 {totals['어법수정']} | 영작 {totals['서술형영작']}",
        }
