"""GDrive 원고 전수 '구조 인벤토리' 추출기.

대상:
  - GDrive 내신대비: 2025년 / 2026년 / STEP3 변형문제 / EBS 작업 / 교과서 작업 / 모의고사 작업
  - 로컬: 오늘 실조판 실패한 부교재 원고 (jobs/06f4b2c2/uploads)

출력: data_corpus/manuscript_structure/inventory.jsonl (문서당 1레코드, gitignore 영역)

레코드 필드:
  path / rel / root / ext / size / series / wb_family
  para_count / text_len / has_table / has_underline
  headers: [{"t": 원문, "body_next": 다음 비빈줄이 영어 본문인지}] (최대 150)
  header_total / section_markers (최대 40) / error

원칙:
  - GDrive 파일은 절대 수정하지 않음 (읽기 전용). 미러(~/Library/Application Support/
    yone-design-web/content-mirror)가 있으면 미러에서 읽고, 없으면 _gdrive_safe_copy로
    로컬 임시 사본을 만들어 읽는다.
  - 재개 가능: 기존 inventory.jsonl의 path는 스킵 (중단 후 재실행 안전).

사용: python3 scripts/extract_structure.py [--limit N] [--workers N]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

GDRIVE_BASE = (
    "/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com"
    "/내 드라이브/콘텐츠 관리/내신대비"
)
SCAN_ROOTS = [
    "2025년",
    "2026년",
    "STEP3 변형문제",
    "EBS 작업",
    "교과서 작업",
    "모의고사 작업",
]
# 오늘(2026-07-06) 실조판 실패한 부교재 원고 — 반드시 포함
LOCAL_EXTRA_DIRS = [
    ("jobs_06f4b2c2_부교재", "/Users/nhj/dev/yone-design-web/jobs/06f4b2c2/uploads"),
]

OUT_DIR = os.path.join(_REPO, "data_corpus", "manuscript_structure")
OUT = os.path.join(OUT_DIR, "inventory.jsonl")
LOG = os.path.join(OUT_DIR, "extract_structure.log")

SKIP_DIRS = {"최종X", "이전버전", "구버전", "백업", "인디자인 파일"}

# ── 교재 계열 추정 (extract_questions.py의 CATEGORY_KEYWORDS 확장) ─────────
CATEGORY_KEYWORDS = [
    ("수능특강", ["수능특강", "수특"]),
    ("리딩파워", ["Reading Power", "리딩파워", "ReadingPower"]),
    ("올림포스", ["올림포스"]),
    ("워크북", ["워크북"]),
    ("동형모의고사", ["동형"]),
    ("세미모의고사", ["세미", "한세모", "명세모"]),
    ("4스텝모의고사", ["4스텝"]),
    ("배N제", ["배N제"]),
    ("어법총정리", ["어법총정리"]),
    ("기적의특강", ["기적의 특강"]),
    ("직전보충", ["직전보충"]),
    ("문제모음", ["문제 모음", "문제모음"]),
    ("포켓북", ["포켓북"]),
    ("분석본", ["분석본"]),
    ("교과서", ["교과서", "공통영어", "영어Ⅰ", "영어Ⅱ", "영어 독해와 작문"]),
    ("플로우노트", ["플로우노트"]),
    ("리테", ["리테"]),
    ("특강", ["특강"]),
    ("모의고사_기타", ["모의고사"]),
]
# 워크북 계열(STEP BY STEP 부교재) 판정 시그니처 — 파일명/경로
_WB_FAMILY = re.compile(
    r"(Step\s*[123]|STEP\s*[123]|워크북|변형문제|변형\s*문제|수능특강|수특|"
    r"Reading\s*Power|리딩파워|올림포스|어휘선택|어법선택|본문OX|어법OX|"
    r"문장배열|빈칸어휘|빈칸어법|영작배열|내용종합|본문정리)",
    re.IGNORECASE,
)


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def category_of(path_nfc):
    for cat, kws in CATEGORY_KEYWORDS:
        for kw in kws:
            if kw in path_nfc:
                return cat
    return None


# ── 라인 분류 규칙 ──────────────────────────────────────────────────────────
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")
_RE_CIRCLED = re.compile(r"[①-⑳㉑-㉟㊱-㊿ⓐ-ⓩ❶-❿]")

# 섹션 마커: 발문/섹션 라벨/정답 구간 (파서 _RE_MANUSCRIPT_HEADER 계열 + 정답 마커)
_RE_SECTION_MARKER = re.compile(
    r"^(?:"
    r"\d+\.\s*(?:어휘|내용[일종]|어법|빈칸|영작|문장|낱말)"  # "1. 어휘1단계_Hard" 류
    r"|어휘[선완]|어법[선수]|빈칸어|낱말배열|문장배열|틀린어법"
    r"|STEP\s*\d|Step\s*\d"
    r"|정답\s*(?:과|및|&)\s*해설\s*$"
    r"|빠른\s*정답\s*찾기\s*$"
    r"|서답형|객관식\s*$"
    r"|Exercises?\s*$"
    r"|Chapter\s+\d+\.\s"
    r"|마더텅\s+고[12]"
    r"|Reading\s*Power|\d{4}\s*수능특강"
    r")",
    re.IGNORECASE,
)

# 지문번호/헤더 후보 cue: 짧은 라인 + 숫자 + p/no/과/강/번/L/U/본문/[..] 패턴
_HEADER_CUES = [
    re.compile(r"^\s*\[\d+(?:\s*~\s*\d+)?\]\s*$"),          # [20], [41~42]
    re.compile(r"^\s*\[[^\]]{1,25}\]\s*$"),                  # [본문1], [3과 추가지문], [L1-9]
    re.compile(r"\bp\.?\s*\d+", re.IGNORECASE),              # p2, p.82
    re.compile(r"\bno\.?\s*\d+", re.IGNORECASE),             # no.18
    re.compile(r"\bL\d+"),                                   # L4
    re.compile(r"\bU\d+"),                                   # U6
    re.compile(r"본문\s*\d+"),                               # 본문1
    re.compile(r"\d+\s*과(?:\s|$|[^가-힣])"),                # 3과
    re.compile(r"\d+\s*강(?:\s|$|[^가-힣])"),                # 12강
    re.compile(r"\d+\s*번\s*$"),                             # 9번
    re.compile(r"\d+\s*년\s*\d+\s*월\s*\d+\s*번"),           # 17년 11월 21번
    re.compile(r"\b(?:Example|Practice|Test|Exercise|Unit|Lesson)\s*\.?\s*\d+", re.IGNORECASE),
    # "1. p2-…" 순번형 — 순번 뒤 마커에 반드시 숫자 동반 (영단어 나열 "1. laughable" 오탐 방지)
    re.compile(r"^\s*\d+\s*[.)]\s*(?:[pP]\.?\s*\d|L\d|U\d|[nN][oO]\.?\s*\d|본문\s*\d|\d)"),
]
_RE_QUESTION_TAIL = re.compile(r"(시오\s*\.?|것은\s*\??|고르시오|것을|한다면|바꾸\S*)\s*$")


def _eng_words(s):
    return len(_RE_ENG_WORD.findall(s))


def _is_body_line(s):
    return _eng_words(s) >= 5


def classify_line(s):
    """라인을 'section' / 'header' / None 으로 분류."""
    if not s:
        return None
    if _RE_SECTION_MARKER.match(s):
        return "section"
    if len(s) > 45 or not re.search(r"\d", s):
        return None
    if len(_RE_CIRCLED.findall(s)) >= 2:  # 정답 나열 ("1. ⓐ2. ⓑ…")
        return None
    if _eng_words(s) >= 5:  # 영어 문장 = 본문
        return None
    if _RE_QUESTION_TAIL.search(s):  # 발문 꼬리
        return None
    for cue in _HEADER_CUES:
        if cue.search(s):
            return "header"
    return None


# ── 파일 추출 ───────────────────────────────────────────────────────────────

def _read_local_path(path, log_lines):
    """GDrive 경로면 미러 redirect 또는 _gdrive_safe_copy로 로컬 사본 확보.

    Returns: (local_path, cleanup: bool)
    """
    if not path.startswith("/Users/nhj/Library/CloudStorage/"):
        return path, False
    from engines.final.extractor import _gdrive_safe_copy, _resolve_local_mirror

    mirrored = _resolve_local_mirror(path)
    if mirrored != path and os.path.isfile(mirrored):
        return mirrored, False
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1], prefix="struct_")
    os.close(fd)
    ok, err = _gdrive_safe_copy(path, tmp)
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise IOError("gdrive_safe_copy failed: %s" % err)
    return tmp, True


def _extract_lines(local_path, ext):
    """(lines, has_table, has_underline) — 파서와 동일한 core 추출기 재사용."""
    import zipfile
    from core.extract.extractors import (
        _docx_extract_paragraphs,
        _hwpx_extract_paragraphs,
        _hwp_is_hwpx,
    )

    if ext == "docx":
        paras = _docx_extract_paragraphs(local_path, extract_underline=True)
        with zipfile.ZipFile(local_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        has_table = "<w:tbl>" in xml or "<w:tbl " in xml
        has_ul = any(r.get("ul") for p in paras for r in p.get("runs", []))
        return [p["text"] for p in paras], has_table, has_ul

    if ext == "hwpx" and not _hwp_is_hwpx(local_path):
        # 확장자만 .hwpx인 바이너리 .hwp (예: "….hwp.hwpx") → hwp5txt 폴백
        ext = "hwp_binary"
    if ext == "hwpx" or (ext == "hwp" and _hwp_is_hwpx(local_path)):
        paras = _hwpx_extract_paragraphs(local_path, extract_underline=True)
        has_table = False
        with zipfile.ZipFile(local_path) as z:
            for n in z.namelist():
                if "section" in n.lower() and n.endswith(".xml"):
                    if b"<hp:tbl" in z.read(n):
                        has_table = True
                        break
        has_ul = any(r.get("ul") for p in paras for r in p.get("runs", []))
        return [p["text"] for p in paras], has_table, has_ul

    # 바이너리 .hwp — hwp5txt (extract_questions.py 전례, timeout 안전)
    # NFD 한글 장문 파일명은 hwp5 내부에서 Errno 63(File name too long)을
    # 일으키므로 항상 짧은 임시 이름의 사본으로 실행.
    import hashlib
    import shutil
    tmp = os.path.join(
        tempfile.gettempdir(),
        "_hwp_%s.hwp" % hashlib.md5(local_path.encode()).hexdigest()[:10],
    )
    try:
        shutil.copy2(local_path, tmp)
        r = subprocess.run(["hwp5txt", tmp], capture_output=True, timeout=120)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    text = r.stdout.decode("utf-8", "replace")
    return text.split("\n"), None, None


def process_file(args):
    """단일 파일 → 인벤토리 레코드 dict."""
    path, root = args
    nfc_path = _nfc(path)
    rec = {
        "path": nfc_path,
        "root": root,
        "ext": path.lower().rsplit(".", 1)[-1],
    }
    if nfc_path.startswith(_nfc(GDRIVE_BASE)):
        rec["rel"] = nfc_path[len(_nfc(GDRIVE_BASE)) + 1:]
    else:
        rec["rel"] = os.path.join(root, os.path.basename(nfc_path))
    rec["series"] = category_of(nfc_path) or root
    rec["wb_family"] = bool(_WB_FAMILY.search(nfc_path)) or root in (
        "STEP3 변형문제", "EBS 작업", "교과서 작업", "jobs_06f4b2c2_부교재",
    )

    local, cleanup = None, False
    try:
        # NFD 장문 한글 파일명은 그대로 stat하면 Errno 63 — NFC/NFD 후보 중
        # 접근 가능한 변형을 골라 사용 (_gdrive_safe_copy와 동일 전략)
        for cand in (path, _nfc(path), unicodedata.normalize("NFD", path)):
            if os.path.exists(cand):
                path = cand
                break
        rec["size"] = os.path.getsize(path)
        local, cleanup = _read_local_path(path, None)
        lines, has_table, has_ul = _extract_lines(local, rec["ext"])
        lines = [_nfc(l).strip() for l in lines]
        rec["para_count"] = len(lines)
        rec["text_len"] = sum(len(l) for l in lines)
        rec["has_table"] = has_table
        rec["has_underline"] = has_ul

        headers, sections = [], []
        seen_sec = set()
        nonempty_next = {}  # i -> 다음 비빈 줄 텍스트
        nxt = None
        for i in range(len(lines) - 1, -1, -1):
            nonempty_next[i] = nxt
            if lines[i]:
                nxt = lines[i]
        for i, s in enumerate(lines):
            kind = classify_line(s)
            if kind == "section":
                if s not in seen_sec and len(sections) < 40:
                    sections.append(s)
                    seen_sec.add(s)
            elif kind == "header":
                if len(headers) < 150:
                    nxt_line = nonempty_next.get(i)
                    headers.append({
                        "t": s,
                        "body_next": bool(nxt_line and _is_body_line(nxt_line)),
                    })
        rec["headers"] = headers
        rec["header_total"] = sum(
            1 for s in lines if classify_line(s) == "header"
        )
        rec["section_markers"] = sections
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        if cleanup and local:
            try:
                os.remove(local)
            except OSError:
                pass
    return rec


# ── 스캔 대상 열거 ──────────────────────────────────────────────────────────

def walk_targets():
    for root in SCAN_ROOTS:
        base = os.path.join(GDRIVE_BASE, root)
        if not os.path.isdir(base):
            print("[warn] 폴더 없음: %s" % base)
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [
                d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
            ]
            for f in files:
                if f.startswith("~$") or f.startswith("."):
                    continue
                if f.lower().rsplit(".", 1)[-1] in ("docx", "hwpx", "hwp"):
                    yield os.path.join(dirpath, f), root
    for root, base in LOCAL_EXTRA_DIRS:
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.startswith("~$") or f.startswith(".") or f.startswith("manuscripts_"):
                    continue  # manuscripts_* 는 동일 파일의 사본 — 중복 제외
                if f.lower().rsplit(".", 1)[-1] in ("docx", "hwpx", "hwp"):
                    yield os.path.join(dirpath, f), root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="테스트용 파일 수 제한")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    done_paths = set()
    if os.path.isfile(OUT):
        with open(OUT) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if not rec.get("error"):  # 에러 레코드는 재시도 대상
                        done_paths.add(rec["path"])
                except Exception:
                    pass

    targets = []
    for path, root in walk_targets():
        if _nfc(path) in done_paths:
            continue
        targets.append((path, root))
        if args.limit and len(targets) >= args.limit:
            break

    total = len(targets)
    print("이미 처리: %d / 신규 대상: %d" % (len(done_paths), total), flush=True)
    if not total:
        print("신규 대상 없음 — 완료 상태.")
        return

    errors = 0
    with open(OUT, "a") as fout, open(LOG, "a") as flog:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_file, t): t for t in targets}
            done = 0
            for fut in as_completed(futs):
                done += 1
                try:
                    rec = fut.result()
                except Exception as e:
                    rec = {"path": _nfc(futs[fut][0]), "root": futs[fut][1],
                           "error": "FATAL %s" % e}
                if rec.get("error"):
                    errors += 1
                    flog.write("ERR %s: %s\n" % (rec["path"], rec["error"]))
                    flog.flush()
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
                if done % 100 == 0:
                    print("  진행: %d/%d (에러 %d)" % (done, total, errors),
                          flush=True)
    print("완료. 신규 %d건 (에러 %d) → %s" % (total, errors, OUT), flush=True)


if __name__ == "__main__":
    main()
