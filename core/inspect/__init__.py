"""검수 게이트 (Phase 4) — 조판 결과가 원고를 보존했는지 기계 대조.

구성:
    dump_indd(indd_path, out_json, log)   .indd → typeset_dump.json (InDesign 필요)
    inspect_workbook_step3(content, dump) content.json ↔ 덤프 대조 리포트

리포트 등급 (리스크분석 A8 — 알람 피로 방지):
    critical: 내용 누락·정답 잔존 등 사람이 반드시 봐야 하는 것 → ok=False
    warning:  스타일 불일치·매칭 불가 등 정보성 (오탐률 측정 후 승격)
"""
import json
import os
import re
import tempfile
import unicodedata

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(os.path.dirname(_DIR), "jsx", "dump_stories.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def dump_indd(indd_path, out_json, log, timeout=600):
    """완성 .indd를 열어 스토리 텍스트+스타일을 out_json으로 덤프.

    경로는 반드시 절대경로로 강제 — ExtendScript의 File(상대경로)는 InDesign
    프로세스 기준으로 풀려서, 상대경로를 넘기면 JSX가 로그를 엉뚱한 곳에 쓰고
    러너가 '시작 안 됨'으로 오판해 InDesign을 강제종료한다 (2026-07-05 실사고).
    """
    from core.indesign.runner import run_jsx
    indd_path = os.path.abspath(indd_path)
    out_json = os.path.abspath(out_json)
    dump_log = out_json + ".log"
    for p in (out_json, dump_log):
        try:
            os.remove(p)
        except OSError:
            pass
    with open(_JSX_TEMPLATE, encoding="utf-8") as f:
        src = f.read()
    src = (src.replace("__INDD_PATH__", indd_path.replace("\\", "\\\\").replace('"', '\\"'))
              .replace("__OUT_PATH__", out_json)
              .replace("__LOG_PATH__", dump_log))
    fd, jsx_path = tempfile.mkstemp(suffix=".jsx", prefix="dump_stories_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        run_jsx(jsx_path, log, poll_log_path=dump_log, timeout=timeout,
                completion_marker="덤프 완료")
    finally:
        try:
            os.remove(jsx_path)
        except OSError:
            pass
    if not os.path.isfile(out_json):
        raise RuntimeError(f"덤프 파일이 생성되지 않음: {out_json}")
    return json.load(open(out_json, encoding="utf-8"))


def _norm_key(text):
    """단락 매칭 키: NFC + 소문자 + 영숫자/한글만 (JSX 치환·공백 변형 흡수)."""
    t = unicodedata.normalize("NFC", text or "").lower()
    return re.sub(r"[^0-9a-z가-힣①-⑤ⓐ-ⓔ]", "", t)


def _dump_paragraphs(dump):
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            yield p.get("t", ""), p.get("s", "")


def inspect_workbook_step3(content, dump, style_overrides=None):
    """workbook content.json(step3 주석본) ↔ 덤프 대조 리포트 (파일럿).

    검사:
      C1 (critical) 내용 보존 — step3 문항별 실질 단어가 덤프 어딘가에 존재
      C2 (critical) 정답 잔존 — 덤프에 정답/해설 패턴 단락 존재
      W1 (warning)  스타일 적합 — kind 주석 단락의 실제 스타일이 style_map과 일치
      W2 (warning)  오버플로우 스토리 수
    """
    from core.structure import rules as R
    from core.structure.style_resolver import resolve_style

    critical, warnings = [], []
    stats = {}

    dump_words = set()
    dump_by_key = {}
    for t, s in _dump_paragraphs(dump):
        for w in _RE_WORD.findall(t):
            dump_words.add(w.lower())
        k = _norm_key(t)
        if k and k not in dump_by_key:
            dump_by_key[k] = (t, s)

    # C1 — 문항별 내용 보존
    step3 = (content.get("steps") or {}).get("step3") or {}
    items = (step3.get("normal") or []) + (step3.get("short") or [])
    missing_total = 0
    for item in items:
        want = set()
        for p in item.get("paragraphs", []):
            if p.get("kind") in ("GH", "A", "BLANK"):   # 의도적 제거 대상 제외
                continue
            for w in _RE_WORD.findall(p.get("text", "")):
                want.add(w.lower())
        dropped = want - dump_words
        if dropped:
            missing_total += len(dropped)
            critical.append(
                f"[내용누락] step3 {item.get('question_num')}번: "
                f"{len(dropped)}개 단어 미발견 — {', '.join(sorted(dropped)[:10])}"
            )
    stats["step3_items"] = len(items)
    stats["missing_words"] = missing_total

    # C2 — 정답/해설 잔존 (정답 단독/정답+해설 라인)
    leaked = []
    for t, _s in _dump_paragraphs(dump):
        tt = t.strip()
        if not tt:
            continue
        if R.A_PATTERNS[0].match(tt) or R.A_PATTERNS[1].match(tt):
            leaked.append(tt[:60])
    if leaked:
        critical.append(f"[정답잔존의심] {len(leaked)}개 단락: "
                        + " | ".join(leaked[:5]))
    stats["answer_leaks"] = len(leaked)

    # W1 — 스타일 적합 (텍스트 매칭 가능한 단락만)
    checked = matched = mismatched = 0
    mismatch_samples = []
    for item in items:
        for p in item.get("paragraphs", []):
            kind = p.get("kind")
            if not kind or kind in ("BLANK", "UNKNOWN", "GH", "A"):
                continue
            k = _norm_key(p.get("text", ""))
            if not k or k not in dump_by_key:
                continue
            checked += 1
            try:
                expected = resolve_style("workbook", "STEP3", kind,
                                         overrides=style_overrides)
            except KeyError:
                continue
            actual = dump_by_key[k][1]
            if expected is None:
                continue
            accepted = expected if isinstance(expected, list) else [expected]
            if actual in accepted:
                matched += 1
            else:
                mismatched += 1
                if len(mismatch_samples) < 8:
                    mismatch_samples.append(
                        f"{kind}: 기대 {expected!r} ≠ 실제 {actual!r} "
                        f"({p.get('text', '')[:40]!r})")
    stats["style_checked"] = checked
    stats["style_matched"] = matched
    stats["style_mismatched"] = mismatched
    if mismatched:
        warnings.append(f"[스타일] {mismatched}/{checked} 불일치 — "
                        + " ; ".join(mismatch_samples))

    # W2 — 오버플로우
    ovf = dump.get("overflow_stories", 0)
    stats["overflow_stories"] = ovf
    if ovf:
        warnings.append(f"[오버플로우] 스토리 {ovf}개 넘침")

    return {
        "ok": not critical,
        "critical": critical,
        "warnings": warnings,
        "stats": stats,
    }


# ── 정답 블록 잔존 검출 (W11 — 완제품 게이트 공용) ───────────────────────────

# 정답표 행: "1. ①   2. ⑤   3. ①  …" (번호+원문자 3쌍 이상)
_RE_ANSWER_ROW = re.compile(
    r"(?:^|\s)\d{1,2}\s*\.\s*[①-⑤](?:\s+\d{1,2}\s*\.\s*[①-⑤]){2,}")


def find_leaked_answers(dump):
    """덤프에서 정답 블록 잔존 단락 수집 — '정답'류 단독 마커 + 정답표 행.

    원고의 정답 섹션("정답" 단독 줄 + 정답표)이 파서/플랜을 뚫고 출력물에
    인쇄된 경우를 잡는다 (workbook_supp 06f4b2c2 실증 — 완제품 기준).
    """
    from core.structure import rules as R
    hits = []
    for t, _s in _dump_paragraphs(dump):
        tt = t.strip()
        if not tt:
            continue
        if R.A_PATTERNS[2].match(tt) or _RE_ANSWER_ROW.search(tt):
            hits.append(tt[:60])
    return hits


# ── 범용 검수 (전 교재 확산 — 엔진 코드/JSX 무수정) ──────────────────────────

_SKIP_KEYS = {"file", "filename", "path", "source_file", "pstyle", "kind",
              "q_code", "code", "marker", "style", "indd_path", "pdf_path",
              "jsx_path", "log_path", "json_path", "output_dir", "meta_path"}


def _norm_typo(s):
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def harvest_content_words(obj, out=None, key=None):
    """content.json(스키마 무관)에서 조판돼야 할 영문 실질 단어를 수확.

    경로/메타성 키와 '_' 접두 키는 제외 — 어떤 엔진의 content 구조든 동작.
    """
    if out is None:
        out = set()
    if isinstance(obj, str):
        if key not in _SKIP_KEYS and not obj.startswith("/"):
            for w in _RE_WORD.findall(_norm_typo(obj)):
                out.add(w.lower())
    elif isinstance(obj, list):
        for v in obj:
            harvest_content_words(v, out, key)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_") or k == "runs":
                # runs = 밑줄 run 조각 — text와 중복이며 단어가 쪼개져
                # ("m"+"aking") 오탐을 만든다. text만 수확.
                continue
            harvest_content_words(v, out, k)
    return out


def _find_indd_paths(obj, out):
    if isinstance(obj, str):
        if obj.endswith(".indd") and os.path.isfile(obj):
            out.append(obj)
    elif isinstance(obj, list):
        for v in obj:
            _find_indd_paths(v, out)
    elif isinstance(obj, dict):
        for v in obj.values():
            _find_indd_paths(v, out)
    return out


def inspect_generic(job_dir, log, timeout=600):
    """엔진 무관 조판 검수 — content.json 단어셋 ↔ 산출 .indd 덤프 대조.

    검사: (a) 내용 보존(파서 산출물 기준 — 파서 단계 손실은 보존 가드 담당),
          (b) 오버플로우 스토리 수.
    반환: {"ok", "missing_words", "missing_sample", "overflow_stories",
           "indd_count"} 또는 None(대상 없음). 예외는 위로 — 호출부 fail-open.
    """
    job_dir = os.path.abspath(job_dir)
    content_path = os.path.join(job_dir, "content.json")
    settings_path = os.path.join(job_dir, ".settings.json")
    if not (os.path.isfile(content_path) and os.path.isfile(settings_path)):
        return None
    settings = json.load(open(settings_path, encoding="utf-8"))
    indd_paths = []
    _find_indd_paths(settings, indd_paths)
    indd_paths = list(dict.fromkeys(indd_paths))
    if not indd_paths:
        return None

    want = harvest_content_words(json.load(open(content_path, encoding="utf-8")))
    got = set()
    overflow = 0
    for i, indd in enumerate(indd_paths, start=1):
        dump = dump_indd(indd,
                         os.path.join(job_dir, f"typeset_dump_g{i}.json"),
                         log, timeout=timeout)
        overflow += dump.get("overflow_stories", 0)
        for t, _s in _dump_paragraphs(dump):
            for w in _RE_WORD.findall(_norm_typo(t)):
                got.add(w.lower())
    missing = want - got
    return {
        "ok": not missing,
        "missing_words": len(missing),
        "missing_sample": sorted(missing)[:15],
        "overflow_stories": overflow,
        "indd_count": len(indd_paths),
        "content_words": len(want),
    }
