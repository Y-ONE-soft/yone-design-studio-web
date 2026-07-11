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
  G7 [빈플랜]     렌더 유닛이 0 — 업로드 원고가 어느 스텝에도 매핑되지
                  않았는데 조판이 '성공'으로 끝나는 침묵 유실 (critical, W12)
  G8 [구분선잔존] 원전 교재의 챕터/유닛 구분선("Chapter 03. ..." /
                  "Unit 10 긴 어구 빈칸")이 출력 본문에 인쇄됨 (critical, W12)
  G9 [미사용원고] 업로드/원고 폴더의 원고 파일이 어느 스텝에도 소비되지
                  않고 조용히 무시됨 (W13 c15 실증: "…STEP 2_박소원
                  완료.hwpx" 통합 원고 3종 침묵 무시). 정답/답지/해설
                  파일과 '정답지 짝' 파일은 의도된 미사용이라 stats로만
                  보고, 그 외는 warning (G7 전량 유실의 부분 유실 보완).
  G10 [특수문자]  hwp 사용자 영역(PUA) 문자가 출력에 인쇄됨 — InDesign
                  폰트에 글리프가 없어 tofu(빈 네모)로 찍힌다 (W14 c05/c06
                  실증: 요약 화살표 ⇩가 /\U000f0036으로 인코딩).
                  PUA 단독 단락은 critical, 본문 내 혼입은 warning.

G4/G5는 dump_stories.jsx의 W11 확장 필드(stale_pages / pg / b)가 필요하다.
구버전 덤프에는 경고로만 보고한다 (재덤프 안내). G9는 uploads_dir를 넘긴
경우에만 검사한다 (오프라인 플랜 테스트 호환).
"""
import os
import re
import unicodedata

from core.inspect import find_leaked_answers
from engines.workbook_v2.plan import (is_header_line, is_a1_header,
                                      passage_labels, _norm_header)

_RE_BARE_NUM = re.compile(r"^\d{1,3}(?:\s*~\s*\d{1,3})?$")
_RE_DIGIT = re.compile(r"\d")
_RE_ENG_WORD = re.compile(r"[A-Za-z]+")

# G8 — 원전 교재 구분선 (파서 _RE_CHAPTER_DIVIDER/_RE_UNIT_DIVIDER 준용.
# 출력 검사용 독립 정의 — 파서가 틀리면 게이트도 같이 틀리는 순환 방지)
_DIVIDER_PATTERNS = [
    re.compile(r"^Chapter\s+\d+\.\s", re.I),
    re.compile(r"^Unit\s+\d+\s+[가-힣][가-힣0-9\s]{0,30}$"),
]


# G10 — hwp 사용자 영역(PUA) 문자 (BMP U+E000~F8FF + plane 15/16).
# InDesign 본문 폰트에 글리프가 없어 tofu로 인쇄된다. ￼(U+FFFC 앵커)는
# PUA가 아니므로 무관.
def _is_pua(ch):
    cp = ord(ch)
    return (0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD
            or 0x100000 <= cp <= 0x10FFFD)


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

# ── G9: 미사용 업로드 원고 (W13) ─────────────────────────────────────────────
_MS_EXTS = (".docx", ".hwp", ".hwpx")
_RE_ANSWERISH = re.compile(r"정답|답지|답안|해설|answer", re.I)
_RE_S3_NUMFILE = re.compile(r"\d+(?:\s*~\s*\d+)?\s*번\s*\.(?:hwpx?|docx)",
                            re.I)
_RE_VARIANT = re.compile(r"변형\s*문제")


def _norm_fname(name):
    return unicodedata.normalize(
        "NFC", os.path.splitext(name)[0]).replace(" ", "").lower()


def find_unused_uploads(content, uploads_dir):
    """(expected_unused, suspicious) — 스텝에 소비되지 않은 원고 파일 분류.

    used 판정은 파서 소비 규칙의 근사 재현:
      - 루트: content steps의 filename (파서가 매칭·rename한 실명)
      - Step3 하위폴더: "N번" 파일(모의고사 번호 매칭), 변형문제 문제모음,
        교과서 경로(step3가 textbook 항목이면 비정답 후보 전부 소비)
    expected_unused = 정답/답지/해설 토큰 파일 + '정답지 짝' 파일(빈칸어휘
    스텝처럼 정답지 본이 소비되는 경우의 문제지 본) — 관행상 폴더에 늘
    존재하므로 stats로만 보고한다.
    """
    steps = (content.get("steps") or {}) if content else {}
    used = set()
    for sd in steps.values():
        if isinstance(sd, dict) and sd.get("filename"):
            used.add(_norm_fname(sd["filename"]))
    st3 = steps.get("step3") or {}
    st3_items = ((st3.get("normal") or []) + (st3.get("short") or [])
                 if isinstance(st3, dict) else [])
    st3_textbook = any(it.get("question_num") == "textbook"
                       for it in st3_items)
    st3_numbered = any(it.get("question_num") != "textbook"
                       for it in st3_items)

    expected, suspicious = [], []
    for root, dirs, files in os.walk(uploads_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        in_step3 = "step3" in unicodedata.normalize(
            "NFC", os.path.relpath(root, uploads_dir)).lower()
        for f in sorted(files):
            if f.startswith(".") or os.path.splitext(f)[1].lower() \
                    not in _MS_EXTS:
                continue
            nf = unicodedata.normalize("NFC", f)
            key = _norm_fname(nf)
            if key in used:
                continue
            if in_step3:
                if st3_numbered and _RE_S3_NUMFILE.search(nf):
                    continue      # 모의고사 번호 매칭으로 소비
                if _RE_VARIANT.search(nf) and st3_items:
                    continue      # 변형문제 문제모음 (W12 라우팅)
                if (st3_textbook and not _RE_ANSWERISH.search(nf)):
                    continue      # 교과서 경로: 비정답 후보 전부 소비
            if _RE_ANSWERISH.search(nf) or any(u.startswith(key)
                                               for u in used):
                # 정답/답지류, 또는 소비된 변형본의 짝 파일 (예: 사용
                # "…빈칸어휘 정답지.docx"/"…영작배열(서술형).hwpx"의 짝
                # "…빈칸어휘.docx"/"…영작배열.docx") — 관행상 의도된 미사용
                expected.append(nf)
            else:
                suspicious.append(nf)
    return expected, suspicious


def inspect_workbook_finish(content, plan, dump, uploads_dir=None):
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

    # ── G7 빈 플랜 — 업로드 원고가 렌더 유닛으로 전혀 이어지지 않음 ─────
    # (W12 실증: 변형문제 문제모음 hwp가 스텝 분류에 안 잡혀 조용히
    # 유실됐는데 verify ok=True로 끝나던 침묵 유실 차단)
    total_units = sum(len(fl.get("units") or [])
                     for fl in plan.get("flows", []))
    stats["plan_units"] = total_units
    if total_units == 0:
        critical.append("[빈플랜] 렌더 유닛 0 — 업로드 원고가 어느 스텝에도 "
                        "매핑되지 않음 (파일명/폴더 규칙 확인)")

    # ── G1 헤더 원문 잔존 + G8 구분선 잔존 ──────────────────────────────
    leaks = []
    divider_leaks = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt:
            continue
        if any(p.match(tt) for p in _DIVIDER_PATTERNS):
            divider_leaks.append(tt[:60])
            continue
        if not _RE_DIGIT.search(tt):
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
    stats["divider_leaks"] = len(divider_leaks)
    if divider_leaks:
        critical.append(f"[구분선잔존] {len(divider_leaks)}개 단락이 원전 "
                        f"챕터/유닛 구분선 그대로 인쇄됨: "
                        + " | ".join(sorted(set(divider_leaks))[:5]))

    # ── G2 정답 블록 잔존 ────────────────────────────────────────────────
    ans = find_leaked_answers(dump)
    stats["answer_leaks"] = len(ans)
    if ans:
        critical.append(f"[정답잔존] {len(ans)}개 단락: "
                        + " | ".join(ans[:5]))

    # ── G10 hwp 사용자 영역(PUA) 문자 잔존 (W14) ─────────────────────────
    pua_solo = []
    pua_inline = []
    for t, _s in _dump_paras(dump):
        tt = _clean(t)
        if not tt or not any(_is_pua(ch) for ch in tt):
            continue
        codes = sorted({f"U+{ord(ch):04X}" for ch in tt if _is_pua(ch)})
        if all(_is_pua(ch) or ch.isspace() for ch in tt):
            pua_solo.append(codes[0])
        else:
            pua_inline.append(f"{codes[0]} ({tt[:30]})")
    stats["pua_solo"] = len(pua_solo)
    stats["pua_inline"] = len(pua_inline)
    if pua_solo:
        critical.append(
            f"[특수문자] hwp 사용자 영역(PUA) 단독 단락 {len(pua_solo)}개 — "
            f"폰트 글리프 없음(tofu 인쇄): "
            + ", ".join(sorted(set(pua_solo))[:5]))
    if pua_inline:
        warnings.append(
            f"[특수문자] 본문 내 PUA 문자 혼입 {len(pua_inline)}개 단락: "
            + " | ".join(pua_inline[:3]))

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

    # ── G4b 고아 번호 페이지 (W14 c03/c15 실증) ─────────────────────────
    # 지문번호/문항번호 프레임은 있는데 콘텐츠 스토리가 전혀 없는 페이지 —
    # 원고 없는 스텝의 섹션 머리/예시 페이지(c03 '20' 3p), 또는 W13 스레드
    # 절단 이후 빈 프레임 페이지가 삭제 판정(다중 프레임 전부 빈)을
    # 벗어나며 남은 잔재(c15 '5' 3p). page_cleanup 사용 시 critical.
    # 콘텐츠 판정은 '플랜(원고) 단락과 겹치는 스토리'만 — 섹션 마커
    # (" 빈칸 어휘")/발문/예시 등 내지 장식 텍스트는 콘텐츠가 아니다
    # (c03 p6/p10/p11: 마커·예시 텍스트 때문에 '내용 있음'으로 오인 방지).
    plan_texts = set()
    for fl in plan.get("flows", []):
        for u in fl.get("units", []):
            for p in (u["paras"] if isinstance(u, dict) else u):
                tt = _clean(p.get("t", ""))
                if len(tt) >= 4:
                    plan_texts.add(tt)
    num_pages = set()
    content_pages = set()
    for story in dump.get("stories", []):
        ps = story.get("paragraphs", [])
        pgs = story.get("pg") or []
        if len(ps) == 1 and _RE_BARE_NUM.match(_clean(ps[0].get("t", ""))):
            num_pages.update(pgs)
        elif any(_clean(p.get("t", "")) in plan_texts
                 for p in ps if len(_clean(p.get("t", ""))) >= 4):
            content_pages.update(pgs)
    orphan_pages = sorted(num_pages - content_pages, key=lambda x: (
        int(x) if str(x).isdigit() else 10**9, str(x)))
    stats["orphan_number_pages"] = len(orphan_pages)
    if orphan_pages:
        msg = (f"[잔여페이지] 번호 프레임만 있고 콘텐츠 없는 페이지 "
               f"{len(orphan_pages)}개: p" + ", p".join(
                   str(p) for p in orphan_pages[:10]))
        (critical if strict_pages else warnings).append(msg)

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

    # ── G9 미사용 업로드 원고 (W13 — 부분 침묵 유실 보고) ────────────────
    if uploads_dir and os.path.isdir(uploads_dir):
        expected_unused, suspicious = find_unused_uploads(content,
                                                          uploads_dir)
        stats["unused_uploads_expected"] = expected_unused
        stats["unused_uploads"] = suspicious
        if suspicious:
            warnings.append(
                f"[미사용원고] {len(suspicious)}개 파일이 어느 스텝에도 "
                f"사용되지 않음 (파일명 규칙 확인): "
                + " | ".join(suspicious[:5]))

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
