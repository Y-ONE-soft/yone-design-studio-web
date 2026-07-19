# -*- coding: utf-8 -*-
"""분석본 결합 v2 — 교과서/EBS 분석본 소스 탐색·범위 유도·파일명 축약.

W28-확장 (2026-07-19): 모의고사 분석본 전용이던 v2를 교과서·EBS 분석본
소스로 확장. 실물 소스 구조 (실측):

  교과서: 내신대비/교과서 작업/{과목}/{과목 출판사(저자)}/{… N과}/{… N과[ 학교]}.indd
          예) 공통영어1/공통영어1 비상(홍)/공통영어1 비상(홍) 3과/
              공통영어1 비상(홍) 3과.indd  (+ "… 3과 세종1.indd" 학교 변형본)
  EBS   : 내신대비/EBS 작업/{교재}/{교재 N강}/{…N강}.indd
          예) 올림포스 독해기본2/올림포스 독해기본2 9강/
              올림포스 영어독해 기본2 9강.indd   ← 파일명 표기가 폴더와 다름
              (명명 변형 허용: 공백 제거 후 "(?<!숫자)N강" 토큰 매칭)

간지 범위 표기는 손마무리 실물 전례를 따른다 (w28_ext/probe_ranges 실측):
  교과서: title = "공통영어1 능률(오) 2과" (과 폴더명) / detail = 과 제목
          ("Health Matters!" — JSX가 소스 간지의 cs '챕터'에서 추출)
  EBS   : title = "올림포스 영어독해 기본1" (indd 파일명 표기) /
          detail = "11강 짧은 어구 빈칸 추론" (JSX가 소스 개요 페이지의
          cs '부제목'에서 추출, 폴백 "N강")

파일명 축약은 실물 전례("미래엔4과"/"YBM박1과"/"능률오2과"/"올포3,4강") +
사용자 예시("비상홍3과"/"올독기2_9강")를 따른다 — 숫자끼리 맞닿으면 "_" 삽입.

읽기: 미러 ∪ GDrive 합집합(list_manuscript_entries)으로 EDEADLK 회피.
쓰기: 없음 (읽기 전용 스캔 — GDrive 무접촉).
"""

import os
import re
import unicodedata


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _entries(folder):
    """미러 ∪ GDrive 합집합 열거 — [(name_nfc, src_path)] (EDEADLK 회피)."""
    from engines.final.extractor import list_manuscript_entries
    return list_manuscript_entries(folder, None) or []


def _is_lock_or_junk(name):
    return (name.startswith(".") or name.startswith("~")
            or "idlk" in name.lower())


# ── 교과서 스캔 ──────────────────────────────────────────────────────────────

# 과 폴더/라벨: "3과" / "1, 2과" / "SL", "SL2" / "Project 1"
_LESSON_RE = re.compile(r"(\d+(?:\s*,\s*\d+)*\s*과|SL\s*\d*|Project\s*\d+)")


def list_textbook_subjects(cfg):
    """교과서 작업/ 바로 아래 과목 폴더 (이전 파일(15개정) 등 제외)."""
    base = cfg.get("textbook_base", "")
    excludes = cfg.get("textbook_exclude", ["이전 파일(15개정)"])
    out = []
    for name, full in _entries(base):
        if _is_lock_or_junk(name) or name in excludes or "이전 파일" in name:
            continue
        if os.path.isdir(full):
            out.append(name)
    return out


def list_textbook_publishers(cfg, subject):
    base = cfg.get("textbook_base", "")
    if not subject or "/" in subject or ".." in subject:
        return []
    out = []
    for name, full in _entries(os.path.join(base, subject)):
        if _is_lock_or_junk(name):
            continue
        if os.path.isdir(full):
            out.append(name)
    return out


def _classify_school(stem, folder_name, lesson_label):
    """indd 파일명에서 학교 변형본 토큰 추출 (없으면 None = 기본본).

    "공통영어1 비상(홍) 3과 세종1" → "세종1" / "공통영어1 비상(홍) 3과" → None.
    학교 토큰은 한글(+학년 숫자) 형태만 인정 — EBS류 명명 변형
    ("… Unit 13 Ex, 1, 2"의 말미 "2" 등)이 학교로 오판되지 않게 한다.
    """
    stem = stem.strip()
    if _despace(stem) == _despace(folder_name):
        return None
    last = stem.split()[-1] if stem.split() else ""
    if re.fullmatch(r"\d+\s*[과강]", last):
        return None
    if lesson_label and _despace(last) == _despace(lesson_label):
        return None
    if re.fullmatch(r"[가-힣]+\d*", last):
        return last
    return None


def list_textbook_lessons(cfg, subject, publisher):
    """과 폴더 목록 + 각 폴더 최상위 .indd (기본본/학교 변형본 구분).

    반환: [{"folder","label","files":[{"name","school"}]}]
    (하위 폴더 — 워크북/리뷰테스트/타학교 기출 — 는 내리지 않는다)
    """
    base = cfg.get("textbook_base", "")
    for tok in (subject, publisher):
        if not tok or "/" in tok or ".." in tok:
            return []
    pub_dir = os.path.join(base, subject, publisher)
    out = []
    for name, full in _entries(pub_dir):
        if _is_lock_or_junk(name) or not os.path.isdir(full):
            continue
        m = _LESSON_RE.search(name)
        if not m:
            continue
        label = re.sub(r"\s+", "", m.group(1))
        files = []
        for fn, ffull in _entries(full):
            if _is_lock_or_junk(fn) or not fn.lower().endswith(".indd"):
                continue
            if not os.path.isfile(ffull):
                continue
            stem = os.path.splitext(fn)[0]
            files.append({"name": fn,
                          "school": _classify_school(stem, name, label)})
        if not files:
            continue
        # 기본본 우선, GDrive 좀비 사본("… (1).indd")은 뒤로
        files.sort(key=lambda f: (f["school"] is not None,
                                  bool(re.search(r"\(\d+\)$",
                                       os.path.splitext(f["name"])[0].strip())),
                                  f["name"]))
        out.append({"folder": name, "label": label, "files": files})
    out.sort(key=lambda e: _natural_key(e["label"]))
    return out


# ── EBS 스캔 ─────────────────────────────────────────────────────────────────

def _despace(s):
    return re.sub(r"\s+", "", _nfc(s))


def _natural_key(s):
    # 숫자/문자 혼합 정렬 키 — 타입 혼합 비교(TypeError) 방지용 태그 튜플
    return [(0, int(t)) if t.isdigit() else (1, t)
            for t in re.split(r"(\d+)", _nfc(s))]


def list_ebs_books(cfg):
    base = cfg.get("ebs_base", "")
    out = []
    for name, full in _entries(base):
        if _is_lock_or_junk(name):
            continue
        if os.path.isdir(full):
            out.append(name)
    return out


# 강/Unit 토큰 (파일명·폴더명 공용) — "9강" / "Unit 13"
_UNIT_TOKEN_RE = re.compile(r"Unit\s*(\d+)|(\d+)\s*강")

# 폴더명용 — 범위 묶음 폴더("올림포스 독해기본1 1~2강")도 라벨 보존
_UNIT_FOLDER_RE = re.compile(r"Unit\s*(\d+)|((?:\d+\s*[~\-,]\s*)*\d+)\s*강")


def _unit_token_num(m):
    return int(m.group(1) or m.group(2))


def _find_unit_token(text, unit_num):
    """text 안에서 번호가 unit_num인 강/Unit 토큰 매치 반환 (없으면 None).

    "올림포스 영어독해 기본2 15강" ↔ 폴더 "올림포스 독해기본2 15강" 같은
    명명 변형을 숫자 전체 비교로 허용한다 ("1강"↛"15강" 오매칭 없음.
    공백 제거 매칭은 "기본2"+"9강"이 "29강"으로 붙어 오판 — 실측 회귀로 폐기).
    """
    for m in _UNIT_TOKEN_RE.finditer(_nfc(text)):
        if _unit_token_num(m) == int(unit_num):
            return m
    return None


def list_ebs_units(cfg, book):
    """교재 폴더 아래 강 단위 목록 + 각 최상위 .indd.

    반환: [{"folder","label","files":[{"name","school"}]}] — 자연 정렬.
    지원 구조 (실측):
      ① "{교재} N강" 폴더 (올림포스 독해기본1/2) — 파일명 표기 변형 허용
      ② "Unit N …" 폴더 (Reading Power 유형편(기본))
      ③ 교재 폴더 직속 .indd (2026/2027 수능특강 영어 — "(12-15강)" 묶음
         버전) — 파일 1개 = 항목 1개, folder는 "" (교재 직속 표시)
    올림포스 고2 기출(연도별 분석본 아카이브 중첩)은 미지원 — 빈 목록.
    """
    base = cfg.get("ebs_base", "")
    if not book or "/" in book or ".." in book:
        return []
    book_dir = os.path.join(base, book)
    out = []
    loose_indd = []
    for name, full in _entries(book_dir):
        if _is_lock_or_junk(name):
            continue
        if os.path.isfile(full) and name.lower().endswith(".indd"):
            loose_indd.append((name, full))
            continue
        if not os.path.isdir(full):
            continue
        m = _UNIT_FOLDER_RE.search(name)
        if not m:
            continue
        if m.group(1) is not None:                      # "Unit 13"
            unit_nums = [int(m.group(1))]
            label = f"Unit {m.group(1)}"
        else:                                           # "9강" / "1~2강"
            unit_nums = [int(x) for x in re.findall(r"\d+", m.group(2))]
            label = re.sub(r"\s+", "", m.group(2)) + "강"
        files = []
        for fn, ffull in _entries(full):
            if _is_lock_or_junk(fn) or not fn.lower().endswith(".indd"):
                continue
            if not os.path.isfile(ffull):
                continue
            if not any(_find_unit_token(fn, n) for n in unit_nums):
                continue
            stem = os.path.splitext(fn)[0]
            files.append({"name": fn,
                          "school": _classify_school(stem, name, label)})
        if not files:
            continue
        # 기본본 우선, GDrive 좀비 사본("… (1).indd")은 뒤로
        files.sort(key=lambda f: (f["school"] is not None,
                                  bool(re.search(r"\(\d+\)$",
                                       os.path.splitext(f["name"])[0].strip())),
                                  f["name"]))
        out.append({"folder": name, "label": label, "files": files})

    if not out:
        # ③ 교재 직속 .indd (수능특강 스타일) — 괄호 안 강/Test 묶음이 라벨
        for name, full in sorted(loose_indd):
            stem = _nfc(os.path.splitext(name)[0])
            m = re.search(r"\(([^)]*(?:강|Test)[^)]*)\)", stem)
            if not m:
                continue
            label = re.sub(r"\s+", "", m.group(1))
            version = re.sub(r"[()\s]", " ", stem[m.end():]).strip() or None
            out.append({"folder": "", "label": label,
                        "files": [{"name": name, "school": version}]})

    out.sort(key=lambda e: _natural_key(e["label"]))
    return out


# ── 선택 → 소스 경로 재해석 (클라이언트 식별자만 신뢰) ───────────────────────

def resolve_textbook_file(cfg, subject, publisher, lesson_folder, file_name):
    """폼 식별자 → (스캔 재검증된) 실제 경로. 실패 시 ValueError."""
    for entry in list_textbook_lessons(cfg, subject, publisher):
        if entry["folder"] != lesson_folder:
            continue
        for f in entry["files"]:
            if f["name"] == file_name:
                folder = os.path.join(cfg["textbook_base"], subject,
                                      publisher, lesson_folder)
                for fn, ffull in _entries(folder):
                    if fn == file_name:
                        return ffull, entry["label"], f["school"]
    raise ValueError(
        f"교과서 소스 미발견: {subject}/{publisher}/{lesson_folder}/{file_name}")


def resolve_ebs_file(cfg, book, unit_folder, file_name):
    for entry in list_ebs_units(cfg, book):
        if entry["folder"] != unit_folder:
            continue
        for f in entry["files"]:
            if f["name"] == file_name:
                folder = os.path.join(cfg["ebs_base"], book, unit_folder) \
                    if unit_folder else os.path.join(cfg["ebs_base"], book)
                for fn, ffull in _entries(folder):
                    if fn == file_name:
                        return ffull, entry["label"], f["school"]
    raise ValueError(f"EBS 소스 미발견: {book}/{unit_folder}/{file_name}")


# ── 파일명 축약 (실물 전례 + 사용자 예시 — 테스트로 고정) ────────────────────

# EBS 교재 축약 (실물 전례: "올포3,4강"/"리딩파워19강" — 현행 폴더명 기준 갱신)
EBS_BOOK_SHORT = {
    "올림포스 독해기본1": "올독기1",
    "올림포스 독해기본2": "올독기2",
    "올림포스 고2 기출": "올고2기출",
    "Reading Power 유형편(기본)": "리딩파워기본",
    "Reading Power 유형편(완성)": "리딩파워완성",
    "2026 수능특강 영어": "26수특",
    "2027 수능특강 영어": "27수특",
}


def publisher_short(subject, publisher):
    """"공통영어1 비상(홍)" → "비상홍" (과목 접두 제거 + 괄호/공백 제거)."""
    pub = _nfc(publisher).strip()
    subj = _nfc(subject).strip()
    if subj and pub.startswith(subj):
        pub = pub[len(subj):].strip()
    return re.sub(r"[()\s]", "", pub)


def ebs_book_short(book):
    book = _nfc(book).strip()
    if book in EBS_BOOK_SHORT:
        return EBS_BOOK_SHORT[book]
    return re.sub(r"[()\s]", "", book)


def join_abbrev(short, unit_label):
    """축약 + 과/강 라벨 결합 — 숫자끼리 맞닿으면 "_" 삽입.

    "비상홍"+"3과" → "비상홍3과" / "올독기2"+"9강" → "올독기2_9강"
    """
    short = (short or "").strip()
    unit = re.sub(r"\s+", "", unit_label or "")
    if short and unit and short[-1].isdigit() and unit[0].isdigit():
        return f"{short}_{unit}"
    return short + unit


# ── 범위 자동 유도 (간지 표기 — 손마무리 실물 전례 정합) ─────────────────────

def derive_range_textbook(subject, publisher, lesson_folder, lesson_label):
    """교과서: title=과 폴더명("공통영어1 비상(홍) 3과"), detail은 JSX가
    소스 간지 cs '챕터'(과 제목)에서 추출 — 여기선 빈 값 + auto 플래그."""
    return {
        "title": _nfc(lesson_folder).strip(),
        "detail": "",
        "abbrev": join_abbrev(publisher_short(subject, publisher),
                              lesson_label),
        "auto": True,
    }


def derive_range_ebs(book, unit_label, file_name, school=None):
    """EBS: title=indd 파일명 표기(강/Unit 토큰 앞부분 — 실물 전례
    "올림포스 영어독해 기본1"), detail 폴백 "N강"/"Unit 13 …" (JSX가
    소스 개요 페이지 cs '부제목'으로 "9강 어휘 적절성" 형태로 보강)."""
    stem = _nfc(os.path.splitext(file_name)[0]).strip()
    if school:
        stem = re.sub(re.escape(school) + r"\s*$", "", stem).strip()

    unit_label = _nfc(unit_label or "").strip()
    label_nums = set(int(x) for x in re.findall(r"\d+", unit_label))
    title, detail = "", ""
    tok = None
    for m in _UNIT_FOLDER_RE.finditer(stem):
        nums = set(int(x) for x in re.findall(r"\d+", m.group(0)))
        if not label_nums or (nums & label_nums):
            tok = m
            break
    if tok:
        start = tok.start()
        if start > 0 and stem[start - 1] == "(":
            # 괄호 묶음 표기 ("2026 수능특강 영어(12-15강) 명여버전") —
            # 괄호 안이 detail, 괄호 앞이 title
            end = stem.find(")", start)
            detail = stem[start:end if end != -1 else len(stem)].strip()
            title = stem[:start - 1].strip(" -_,·~")
        else:
            title = stem[:start].strip(" -_,·~")
            detail = stem[start:].strip()
    if not title:
        # 토큰 미발견 (수능특강 "(12-15강)" 묶음 등) — 교재명/라벨 폴백
        title = re.split(r"\(", stem)[0].strip() or _nfc(book).strip()
        detail = unit_label
    if not detail:
        detail = unit_label

    # 파일명 축약 토큰: "9강" / "Unit 13"→"13강" (실물 전례 "리딩파워19강")
    abbrev_unit = re.sub(r"\s+", "", unit_label)
    m_unit = re.fullmatch(r"Unit(\d+)", abbrev_unit)
    if m_unit:
        abbrev_unit = f"{m_unit.group(1)}강"
    return {
        "title": title,
        "detail": detail,
        "abbrev": join_abbrev(ebs_book_short(book), abbrev_unit),
        "auto": True,
    }


# ── extra_sources 폼 입력 파싱 ───────────────────────────────────────────────

def parse_extra_sources(raw):
    """폼 hidden JSON → 검증된 선택 리스트 (순서 보존).

    [{"type":"textbook","subject","publisher","lesson_folder","file_name"},
     {"type":"ebs","book","unit_folder","file_name"}]
    """
    import json
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError(f"추가 소스 JSON 파싱 실패: {raw[:80]!r}")
    if not isinstance(data, list):
        raise ValueError("추가 소스 형식 오류 (리스트가 아님)")
    out = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"추가 소스 항목 형식 오류: {item!r}")
        typ = str(item.get("type", "")).strip()
        if typ == "textbook":
            keys = ("subject", "publisher", "lesson_folder", "file_name")
            optional = ()
        elif typ == "ebs":
            keys = ("book", "file_name")
            optional = ("unit_folder",)   # 교재 직속 파일(수능특강)은 ""
        else:
            raise ValueError(f"알 수 없는 소스 유형: {typ!r}")
        rec = {"type": typ}
        for k in keys:
            v = _nfc(str(item.get(k, "")).strip())
            if not v:
                raise ValueError(f"추가 소스 필드 누락: {typ}.{k}")
            rec[k] = v
        for k in optional:
            rec[k] = _nfc(str(item.get(k, "")).strip())
        out.append(rec)
    return out
