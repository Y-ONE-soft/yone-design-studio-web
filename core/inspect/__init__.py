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
    """완성 .indd를 열어 스토리 텍스트+스타일을 out_json으로 덤프."""
    from core.indesign.runner import run_jsx
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
