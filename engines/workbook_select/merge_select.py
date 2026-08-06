# -*- coding: utf-8 -*-
"""여러 회차 워크북 content.json에서 선택 문항을 뽑아 하나로 병합.

workbook 엔진 파서 출력(content.json)을 입력으로 받아, 요청한 6자리
코드(YYMMQQ) 순서대로 스텝별 문항 블록을 이어 붙인 병합 content.json을
만든다. 조판은 기존 workbook 엔진 JSX가 그대로 수행한다.

스텝별 문항 경계 (실측 방언 — 21년11월 / 23년11월 / 22년6월 원고):
  bracket 스텝 (a1/a1_2/a2/b1/b2):
    "[22]"        — 표준 브래킷 (21년11월, 22년6월)
    "고1 #18"     — 23년11월 a1/a2
    "20."         — 23년11월 b1
    → 병합 시 전부 "[YYMMQQ]" 브래킷으로 정규화 (조판 라벨 = 6자리 코드,
      한영1 워크북03 기준 산출물과 동일 표기)
  header 스텝 (c1/c2/어법a1/어법b1/어법c1):
    "1. p3-no.22" — 전 회차 공통. JSX가 헤더를 제거하거나(no.QQ → {QQ})
      변환하므로 원문 그대로 두고 블록만 자른다.
  번 스텝 (영작 c2):
    "30번"        — 원문 그대로 유지.

step3(실전)는 파서가 문항별 item(code 포함)으로 이미 분리해 두므로
코드 필터 + 순서 정렬만 한다.
"""

import re

BRACKET_STEPS = ["step1_a1", "step1_a1_2", "step1_a2", "step1_b1", "step1_b2"]
HEADER_STEPS = ["step1_c1", "step1_c2", "step2_a1", "step2_a1_btm",
                "step2_b1", "step2_c1"]
BEON_STEPS = ["step2_c2"]

ALL_STEP_KEYS = BRACKET_STEPS + HEADER_STEPS + BEON_STEPS

_RE_BRACKET = re.compile(r"^\s*\[(\d{1,6})(?:\s*[~\-]\s*(\d{1,6}))?\]\s*$")
_RE_HASH = re.compile(r"^\s*고\s*\d\s*#\s*(\d{1,3})\s*$")
_RE_DOT = re.compile(r"^\s*(\d{1,2})\.\s*$")
_RE_HDR = re.compile(
    r"^\s*\d+\.\s*p\.?\s*\d+\s*[-–—]\s*no\.\s*(\d{1,3})(?:\s*[~\-]\s*(\d{1,3}))?\s*$")
_RE_BEON = re.compile(r"^\s*(\d{1,3})(?:\s*[~\-]\s*(\d{1,3}))?\s*번\s*$")


# ── 원고 세대차 정규화 ───────────────────────────────────────────────────
# 회차마다 원고 세대가 달라 같은 의미를 다른 표기로 쓴다. 한 회차만 조판할
# 때는 드러나지 않지만, 여러 회차를 한 책에 병합하면 한 섹션 안에서 표기가
# 섞인다. 병합 시점에 최신(다수) 표기로 통일한다.
#
# (1) 어휘/어법 선택지 마커: 구형 일부 회차가 □ 를 쓴다
#     실측 2026-08-06: 23년11월 a1 = "❮ □ same / □ different ❯",
#                      21년11월 a1 = "❮ ⓐ obscures / ⓑ defines ❯"
#     완성 조판본은 ⓐⓑ 표기이므로 □ → ⓐⓑ… 순번으로 치환한다.
#     한 괄호 안에서만 순번을 매긴다 (선택지 3개 이상도 대응).
_CIRCLED = "ⓐⓑⓒⓓⓔⓕⓖ"
_RE_CHOICE_GROUP = re.compile(r"❮[^❯]*❯|\[[^\]]*\]")


def _normalize_choice_markers(text):
    """선택지 괄호 안의 □ 를 ⓐⓑ… 순번으로 치환. □ 가 없으면 무변경."""
    if "□" not in text:
        return text

    def repl(m):
        seg = m.group(0)
        if "□" not in seg:
            return seg
        out = []
        n = 0
        for ch in seg:
            if ch == "□" and n < len(_CIRCLED):
                out.append(_CIRCLED[n])
                n += 1
            else:
                out.append(ch)
        return "".join(out)

    return _RE_CHOICE_GROUP.sub(repl, text)


def _normalize_para(para):
    """단락 1개 정규화 — 텍스트 길이 보존(runs 오프셋 유지)."""
    text = para.get("text") or ""
    new = _normalize_choice_markers(text)
    if new == text:
        return para
    out = dict(para)
    out["text"] = new
    runs = para.get("runs")
    if runs:
        # □ 는 1:1 치환이라 run 경계가 유지된다 — run별로 같은 변환 적용
        out["runs"] = [dict(r, t=_normalize_choice_markers(r.get("t") or ""))
                       for r in runs]
    return out


def _blank(text):
    return not text.strip()


# ── 블록 내용 이상 감지 (원고 결손 조기 경보) ────────────────────────────
# 코드가 원고에 "있기는 한데" 내용이 비어 있거나 정답만 남은 경우가 있다.
# 실측 2026-08-06: 24년9월 문장배열 32번 블록이 선지 0개 + 정답
# ("B-C-A-G-F-E-D")만 3단락 → 조판 결과 p86이 63자짜리 반쪽 페이지.
# coverage=True 라 종전 검수는 통과했다. 스텝별 최소 구성 요건을 두고
# 미달 블록을 경고로 남겨, 교재팀에 원고 재요청할 근거를 만든다.
_RE_CHOICE_TAG = re.compile(r"\([A-G]\)")
_RE_ORDER_ANSWER = re.compile(r"\b[A-G](?:\s*-\s*[A-G]){2,}\b")

# step_key: (최소 본문 문자수, 최소 선지 수, 설명)
_BLOCK_MIN = {
    "step1_c1": (200, 3, "문장배열 (A)(B)(C) 선지"),
    "step1_a1": (150, 0, "어휘선택 지문"),
    "step1_a1_2": (150, 0, "어휘선택2 지문"),
    "step1_a2": (150, 0, "본문 O/X 지문"),
    "step1_b1": (150, 0, "본문정리 지문"),
    "step1_b2": (150, 0, "내용종합 지문"),
    "step1_c2": (150, 0, "빈칸어휘 본문"),
    "step2_a1": (150, 0, "어법선택 지문"),
    "step2_b1": (150, 0, "어법 O/X 지문"),
    "step2_c1": (150, 0, "빈칸어법 본문"),
    "step2_c2": (80, 0, "영작배열 문항"),
}


def _check_block(step_key, paras):
    """블록 내용 건전성 검사 → 문제 있으면 사유 문자열, 없으면 None."""
    req = _BLOCK_MIN.get(step_key)
    if not req:
        return None
    min_chars, min_choice, label = req
    body = " ".join((p.get("text") or "") for p in paras)
    compact = re.sub(r"\s+", "", body)
    n_choice = len(_RE_CHOICE_TAG.findall(body))
    if len(compact) < min_chars:
        extra = ""
        if _RE_ORDER_ANSWER.search(body):
            extra = " (정답만 있음)"
        return "%s 본문 %d자%s" % (label, len(compact), extra)
    if min_choice and n_choice < min_choice:
        return "%s %d개뿐" % (label, n_choice)
    return None


def _nums_from_match(m):
    """경계 매치 → 이 블록이 커버하는 문항번호 집합. 6자리는 뒤 2자리."""
    nums = set()
    for g in m.groups():
        if g is None:
            continue
        n = int(g)
        if n >= 100000:            # 이미 6자리 코드로 쓰인 원고
            n = n % 100
        nums.add(n)
    if len(nums) == 2:             # 범위 41~42 → 사이 전부
        lo, hi = min(nums), max(nums)
        nums = set(range(lo, hi + 1))
    return nums


def _boundary_match(step_key, text):
    """이 단락이 문항 경계인가? 매치되면 re.Match, 아니면 None."""
    if step_key in BRACKET_STEPS:
        for rx in (_RE_BRACKET, _RE_HASH, _RE_DOT, _RE_HDR):
            m = rx.match(text)
            if m:
                return m
        return None
    if step_key in HEADER_STEPS:
        return _RE_HDR.match(text)
    if step_key in BEON_STEPS:
        return _RE_BEON.match(text)
    return None


def split_blocks(step_key, paragraphs):
    """단락 리스트 → (preamble, [ {nums, boundary_idx, paras} ])."""
    blocks = []
    preamble = []
    cur = None
    for p in paragraphs:
        m = _boundary_match(step_key, p.get("text", ""))
        if m:
            cur = {"nums": _nums_from_match(m), "boundary": p, "paras": []}
            blocks.append(cur)
            continue
        if cur is None:
            preamble.append(p)
        else:
            cur["paras"].append(p)
    return preamble, blocks


def _find_block(blocks, qq):
    for b in blocks:
        if qq in b["nums"]:
            return b
    return None


def _marker_para(code_label):
    return {"text": "[%s]" % code_label, "runs": [{"t": "[%s]" % code_label,
                                                   "ul": False}]}


def _blank_para():
    return {"text": "", "runs": [{"t": "", "ul": False}]}


def merge_selected(sources, codes, log=None):
    """병합 실행.

    Args:
        sources: [{"yy": 21, "mm": 11, "content": <parsed dict>}, ...]
        codes: ["231133", "211132", ...] 사용자 순서 그대로
        log: callable
    Returns:
        (merged_content, coverage, defects)
        coverage: {step_key: {code: True/False}} — 원고에 그 문항이 있었는가
        defects: [{"step","code","reason"}] — 코드는 있으나 내용 미달
    """
    if log is None:
        log = lambda s: None

    by_ym = {}
    for s in sources:
        by_ym[(s["yy"], s["mm"])] = s["content"]

    # 스텝별 블록 분할 캐시: (yy,mm,step) → (preamble, blocks)
    split_cache = {}

    def blocks_for(yy, mm, step_key):
        key = (yy, mm, step_key)
        if key not in split_cache:
            content = by_ym.get((yy, mm))
            step = (content or {}).get("steps", {}).get(step_key)
            if not step:
                split_cache[key] = None
            else:
                split_cache[key] = split_blocks(step_key, step["paragraphs"])
        return split_cache[key]

    parsed_codes = []
    for c in codes:
        c = c.strip()
        if not re.fullmatch(r"\d{6}", c):
            raise ValueError("6자리 코드가 아님: %r" % c)
        parsed_codes.append({"code": c, "yy": int(c[:2]), "mm": int(c[2:4]),
                             "qq": int(c[4:6])})

    merged_steps = {}
    coverage = {}
    defects = []          # 원고 결손 (코드는 있으나 내용 미달)

    for step_key in ALL_STEP_KEYS:
        out_paras = []
        cov = {}
        used_blocks = set()   # (yy,mm,boundary id) — 범위 블록 중복 방지
        ordinal = 0
        for pc in parsed_codes:
            sp = blocks_for(pc["yy"], pc["mm"], step_key)
            if sp is None:
                cov[pc["code"]] = False
                continue
            _pre, blocks = sp
            b = _find_block(blocks, pc["qq"])
            if b is None:
                cov[pc["code"]] = False
                continue
            bid = (pc["yy"], pc["mm"], id(b))
            if bid in used_blocks:
                cov[pc["code"]] = True   # 범위 블록(41~42)에 이미 포함됨
                continue
            used_blocks.add(bid)
            cov[pc["code"]] = True
            ordinal += 1

            if step_key in BRACKET_STEPS:
                out_paras.append(_marker_para(pc["code"]))
            elif step_key in HEADER_STEPS:
                # 원 헤더 유지하되 서수만 병합 순서로 재부여
                btxt = b["boundary"]["text"]
                new_txt = re.sub(r"^\s*\d+\.", "%d." % ordinal, btxt, count=1)
                bb = dict(b["boundary"])
                bb["text"] = new_txt
                bb["runs"] = [{"t": new_txt, "ul": False}]
                out_paras.append(bb)
            else:  # BEON
                out_paras.append(b["boundary"])

            bad = _check_block(step_key, b["paras"])
            if bad:
                defects.append({"step": step_key, "code": pc["code"],
                                "reason": bad})
                log("[원고결손] %s %s: %s — 교재팀 원고 재요청 필요"
                    % (step_key, pc["code"], bad))
            out_paras.extend(_normalize_para(p) for p in b["paras"])
            # 블록 경계 사이 빈 단락 1개 보장 (원고 관례 유지)
            if b["paras"] and not _blank(b["paras"][-1].get("text", "")):
                out_paras.append(_blank_para())

        coverage[step_key] = cov
        if any(cov.values()):
            found = sum(1 for v in cov.values() if v)
            merged_steps[step_key] = {
                "filename": "merged:%s" % step_key,
                "question_numbers": [int(pc["code"]) for pc in parsed_codes
                                     if cov.get(pc["code"])],
                "paragraph_count": len(out_paras),
                "paragraphs": out_paras,
            }
            log("[병합] %s: %d/%d 문항" % (step_key, found, len(parsed_codes)))

    # ── step3 ──────────────────────────────────────────────────────
    s3_normal = []
    s3_cov = {}
    for pc in parsed_codes:
        content = by_ym.get((pc["yy"], pc["mm"]))
        s3 = (content or {}).get("steps", {}).get("step3")
        item = None
        if s3:
            for it in (s3.get("normal") or []):
                if str(it.get("code", "")) == pc["code"]:
                    item = it
                    break
        if item:
            s3_normal.append(item)
            s3_cov[pc["code"]] = True
        else:
            s3_cov[pc["code"]] = False
    coverage["step3"] = s3_cov
    if s3_normal:
        merged_steps["step3"] = {
            "normal": s3_normal,
            "short": [],
            "normal_count": len(s3_normal),
            "short_count": 0,
        }
        log("[병합] step3: %d/%d 문항" % (len(s3_normal), len(parsed_codes)))

    merged = {
        "grade": sources[0]["content"].get("grade", 1),
        "year": parsed_codes[0]["yy"],
        "month": parsed_codes[0]["mm"],
        "steps": merged_steps,
    }
    if defects:
        log("[원고결손] 총 %d건 — coverage 는 통과하나 내용 미달 "
            "(교재팀 원고 재요청 대상)" % len(defects))
    return merged, coverage, defects
