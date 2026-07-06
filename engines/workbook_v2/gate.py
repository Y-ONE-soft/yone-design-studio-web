"""워크북 v2 완제품 검수 게이트 (W11 — job 06f4b2c2 결함 6건의 자동 검출).

기준은 '조판사가 납품하는 완제품'이다 — 파싱 결과가 아니라 출력물 자체를
검사한다 (파서가 틀리면 게이트도 같이 틀리는 순환 금지):
  G1 [헤더잔존]   지문번호 헤더 원문이 출력 본문에 인쇄됨 (critical)
  G2 [정답잔존]   '정답' 블록/정답표 행이 출력에 인쇄됨 (critical)
  G3 [지문번호]   독립 지문번호 프레임이 원고 지문번호와 불일치
                  (passage_numbers op 사용 시 critical, 아니면 warning)
  G4 [잔여페이지] 원고에 없는 스텝/남는 사이클 페이지 잔존
                  (page_cleanup op 사용 시 critical, 아니면 warning)
  G5 [상하반전]   step2_a1(상단)과 step2_a1_btm(하단)의 기하 배치 반전
                  (step_map pos 힌트 사용 시 critical, 아니면 warning)
  G6 [헤더미인식] 원고(콘텐츠 단락)에 구조적 헤더 후보가 있는데 인식기가
                  하나도 못 잡음 — 파싱 계층 경고 (순환 측정 방지)

G4/G5는 dump_stories.jsx의 W11 확장 필드(stale_pages / pg / b)가 필요하다.
구버전 덤프에는 경고로만 보고한다 (재덤프 안내).
"""
import re
import unicodedata

from core.inspect import find_leaked_answers
from engines.workbook_v2.plan import (is_header_line, is_a1_header,
                                      passage_labels, _norm_header)

_RE_BARE_NUM = re.compile(r"^\d{1,3}(?:\s*~\s*\d{1,3})?$")
_RE_DIGIT = re.compile(r"\d")
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")


def _clean(t):
    """덤프 단락 텍스트 정규화 — 앵커(￼)/개행 제거 + 공백 정리."""
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("￼", "")
    return _norm_header(t)


def _dump_paras(dump):
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            yield p.get("t", ""), p.get("s", "")


def _flow_probe_text(flow):
    """플로우에서 가장 긴 단락 텍스트 — 덤프 스토리 식별용 (충분히 고유)."""
    best = ""
    for u in flow.get("units", []):
        paras = u["paras"] if isinstance(u, dict) else u
        for p in paras:
            if len(p.get("t") or "") > len(best):
                best = p["t"]
    return best


def _find_story_with_text(dump, text):
    key = _clean(text)
    if not key:
        return None
    for story in dump.get("stories", []):
        for p in story.get("paragraphs", []):
            if _clean(p.get("t", "")) == key:
                return story
    return None


def _is_struct_header_candidate(paras, i):
    """구조적 헤더 후보 — 형식 무관 판정 (parser._is_passage_marker_struct
    준용). 짧고 숫자 포함, 영단어 적고, 뒤에 긴 영어 본문이 따라옴."""
    text = (paras[i].get("text") or "").strip()
    if not text or len(text) > 40:
        return False
    if not _RE_DIGIT.search(text):
        return False
    if len(_RE_ENG_WORD.findall(text)) >= 4:
        return False
    j = i + 1
    while j < len(paras) and not (paras[j].get("text") or "").strip():
        j += 1
    if j >= len(paras):
        return False
    return len(_RE_ENG_WORD.findall(paras[j].get("text") or "")) >= 5


# 헤더 기반 스텝 (헤더 제거/정규화가 빌더 책임인 스텝)
_HEADER_STEPS = ("step1_c2", "step2_c1", "step2_b1", "step2_a1", "step1_c1")


def inspect_workbook_finish(content, plan, dump):
    """content(원고 파싱본) + plan + 출력 덤프 → 완제품 게이트 리포트."""
    critical = []
    warnings = []
    stats = {}
    plan = plan or {}
    steps = (content.get("steps") or {}) if content else {}

    strict_numbers = bool(plan.get("passage_numbers"))
    strict_pages = bool(plan.get("page_cleanup"))
    pos_used = any((fl.get("target") or {}).get("pos")
                   for fl in plan.get("flows", []))

    # ── G1 헤더 원문 잔존 ────────────────────────────────────────────────
    leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not _RE_DIGIT.search(tt):
            continue
        if tt.startswith("{") or tt.startswith("["):
            continue    # {20}/{3과 추가지문}/[20] — 의도된 라벨 산출물
        if is_header_line(tt) or is_a1_header(tt):
            leaks.append(tt[:60])
    stats["header_leaks"] = len(leaks)
    if leaks:
        critical.append(f"[헤더잔존] {len(leaks)}개 단락이 지문번호 헤더 "
                        f"원문 그대로 인쇄됨: "
                        + " | ".join(sorted(set(leaks))[:5]))

    # ── G2 정답 블록 잔존 ────────────────────────────────────────────────
    ans = find_leaked_answers(dump)
    stats["answer_leaks"] = len(ans)
    if ans:
        critical.append(f"[정답잔존] {len(ans)}개 단락: "
                        + " | ".join(ans[:5]))

    # ── G3 독립 지문번호 프레임 ↔ 원고 지문번호 ─────────────────────────
    labels = list((plan.get("passage_numbers") or {}).get("labels") or [])
    if not labels:
        labels = passage_labels(steps)
    expected = set(labels)
    for sd in steps.values():
        if isinstance(sd, dict):
            for n in sd.get("question_numbers") or []:
                expected.add(str(n))
    bare_frames = []
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        if len(ps) != 1:
            continue
        tt = _clean(ps[0].get("t", ""))
        if _RE_BARE_NUM.match(tt):
            bare_frames.append(tt)
    unknown = sorted(set(t for t in bare_frames if t not in expected))
    stats["number_frames"] = len(bare_frames)
    stats["number_frame_unknown"] = len(unknown)
    if unknown:
        msg = (f"[지문번호] 원고에 없는 번호 프레임 {len(unknown)}종 잔존"
               f" (템플릿 잔재): " + ", ".join(unknown[:10]))
        (critical if strict_numbers else warnings).append(msg)

    # ── G4 잔여 페이지 (원고 없는 스텝/남는 사이클) ──────────────────────
    stale = dump.get("stale_pages")
    if stale is None:
        warnings.append("[잔여페이지] 덤프에 페이지 정보 없음(구버전 덤프)"
                        " — 재덤프 필요")
    else:
        empty_prefix = ((plan.get("page_cleanup") or {})
                        .get("empty_master", "M")
                        if isinstance(plan.get("page_cleanup"), dict)
                        else "M")
        residual = [e for e in stale
                    if not str(e.get("m", "")).startswith(empty_prefix)]
        stats["stale_pages"] = len(residual)
        if residual:
            names = [str(e.get("p")) for e in residual]
            msg = (f"[잔여페이지] 내용 없는 스텝/사이클 페이지 "
                   f"{len(residual)}개 잔존: p" + ", p".join(names[:12])
                   + ("…" if len(names) > 12 else ""))
            (critical if strict_pages else warnings).append(msg)

    # ── G5 step2_a1 상단 / step2_a1_btm 하단 기하 검사 ───────────────────
    flows = {fl["step"]: fl for fl in plan.get("flows", [])}
    if "step2_a1" in flows and "step2_a1_btm" in flows:
        st_top = _find_story_with_text(dump, _flow_probe_text(flows["step2_a1"]))
        st_btm = _find_story_with_text(dump,
                                       _flow_probe_text(flows["step2_a1_btm"]))
        if st_top and st_btm and st_top.get("b") and st_btm.get("b"):
            shared = set(st_top.get("pg") or []) & set(st_btm.get("pg") or [])
            if shared and st_top["b"][0] >= st_btm["b"][0]:
                msg = ("[상하반전] step2_a1(상단)이 step2_a1_btm(하단)보다 "
                       f"아래에 배치됨 (top {st_top['b'][0]} ≥ "
                       f"{st_btm['b'][0]})")
                (critical if pos_used else warnings).append(msg)
                stats["a1_swapped"] = True
            else:
                stats["a1_swapped"] = False
        elif st_top and st_btm:
            warnings.append("[상하배치] 덤프에 프레임 좌표 없음(구버전 덤프)"
                            " — 상/하단 검사 생략")

    # ── G6 파싱 계층: 구조적 헤더 후보 미인식 (경고) ─────────────────────
    for key in _HEADER_STEPS:
        sd = steps.get(key)
        if not isinstance(sd, dict):
            continue
        paras = sd.get("paragraphs") or []
        cands = [i for i in range(len(paras))
                 if _is_struct_header_candidate(paras, i)]
        if not cands:
            continue
        recognized = 0
        for i in cands:
            t = _norm_header(paras[i].get("text") or "")
            if is_header_line(t) or is_a1_header(t) or t.startswith("["):
                recognized += 1
        if recognized == 0:
            warnings.append(
                f"[헤더미인식] {key}: 구조적 헤더 후보 {len(cands)}개 중 "
                f"인식 0개 — 새 헤더 형식 의심: "
                + (paras[cands[0]].get("text") or "")[:40])

    return {"ok": not critical, "critical": critical, "warnings": warnings,
            "stats": stats}
