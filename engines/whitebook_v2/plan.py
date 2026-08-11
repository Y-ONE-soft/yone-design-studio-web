"""화이트북 v2 렌더 플랜 빌더 — content.json(v1 파서 출력) → wbwt-flows 플랜.

플랜 포맷 (core/jsx/whitebook_flow.body.jsx가 실행):
{
  "format": "wbwt-flows-v1",
  "week_text": "1주 차" | null,          # 주차 텍스트 GREP 치환 (v1 issueNum)
  "flows": [
    {"area": "A", "find": {"first_style": "A 어휘"},
     "units": [{"paras": [{t,s,runs}], "ops": {...}} | {"skip": true}, ...]},
    ...
    {"area": "ans",       "find": {"answer": {"second_style": "정답지 번호"}}, ...},
    {"area": "prac_main", "find": {"practice_main": true}, ...},
    {"area": "prac_ans",  "find": {"practice_answer": true}, ...}
  ]
}

배치 의미론 = v1 engines/whitebook/jsx/run.jsx v3와 동일:
  스토리 탐색(첫 단락 스타일/정답 시그니처/F·C-마스터 기하) → 유닛 i ↔ 스토리 i,
  스토리 통째 교체(replaceContent). 유닛 "skip"은 v1의 조건 미충족(스토리 무접촉).

v1 JSX의 GREP 2종은 파이썬 전처리로 이식:
  - applyOnesGrep(D 박스 ①앞 공백→\r) = _split_ones (단락 분할, 스타일 동일)
  - applyUnderlineMarkers(<u>..</u>→밑줄 문자스타일) = _ul_runs (runs 데이터)

유닛 ops (실행기가 스토리 채움 후 적용 — v1 대응 함수):
  expand_last: true             expandChainLastFrame (B)
  expand_move: [스타일...]       expandFrameAndMoveBelow (D 박스)
  numbering_restart: [단락idx]   postProcessAnswerStory numberingContinue=false
  ans_char: {style, paras}      정답 헤더 '정답' 2글자 문자스타일
  icons: [{p, sec}]             insertSectionIcon (A~E 컬러 아이콘, sec 0~4)
  ans_frame_fix: true           정답 스토리 2번째 프레임 기하 [20,23,*,190]
"""
import re

from core.structure.style_resolver import load_style_map

# v1 applyOnesGrep: ' +(?=[\x{2460}-\x{2473}\x{3251}-\x{325F}\x{32B1}-\x{32BF}])'
_RE_ONES_SPACE = re.compile(
    "[ ]+(?=[①-⑳㉑-㉟㊱-㊿])")
_RE_UL = re.compile(r"<u>(.*?)</u>", re.S)


def _tables():
    smap = load_style_map()["whitebook"]
    return smap["AREAS"], smap["PRAC"], smap["CHAR"]


def _ul_runs(text):
    """<u>..</u> 마커 → (마커 제거 텍스트, runs[{t,ul}]) — v1 GREP 의미 보존.

    runs는 밑줄 구간이 하나라도 있을 때만 반환 (없으면 [])."""
    if "<u>" not in (text or ""):
        return text or "", []
    runs = []
    pos = 0
    clean = []
    for m in _RE_UL.finditer(text):
        if m.start() > pos:
            seg = text[pos:m.start()]
            runs.append({"t": seg, "ul": False})
            clean.append(seg)
        inner = m.group(1)
        if inner:
            runs.append({"t": inner, "ul": True})
            clean.append(inner)
        pos = m.end()
    if pos < len(text):
        seg = text[pos:]
        runs.append({"t": seg, "ul": False})
        clean.append(seg)
    if not any(r["ul"] for r in runs):
        runs = []
    return "".join(clean), runs


def _split_ones(text):
    """v1 applyOnesGrep 등가 — 원문자(①~㊿) 앞 공백열을 단락 경계로 분할."""
    return _RE_ONES_SPACE.sub("\r", text or "").split("\r")


def _p(text, style, runs=None):
    return {"t": text, "s": style, "runs": runs or []}


# ── Day 영역 유닛 빌더 (v1 run.jsx Day 루프 이식) ───────────────────────────

def _unit_a(content, A):
    if not content.get("A"):
        return {"skip": True}
    paras = []
    for it in content["A"]:
        raw = it.get("raw") or f"{it['num']}. {it['word']}"
        paras.append(_p(raw, A["A_word"]))
    return {"paras": paras}


def _unit_b(content, A):
    if not content.get("B"):
        return {"skip": True}
    paras = []
    keep_eng = []
    keep_kor = []
    for b in content["B"]:
        if b.get("kor"):
            keep_eng.append(len(paras))
        paras.append(_p(f"{b['num']}. {b['eng']}", A["B_eng"]))
        if b.get("kor"):
            keep_kor.append(len(paras))
            paras.append(_p(b["kor"], A["B_kor"]))
    # keep_pairs: 문항(영문)과 해석이 페이지 경계에서 갈라지지 않게 결속
    return {"paras": paras,
            "ops": {"expand_last": True,
                    "keep_pairs": {"eng": keep_eng, "kor": keep_kor}}}


def _unit_c(content, A):
    if not content.get("C"):
        return {"skip": True}
    paras = []
    for cset in content["C"]:
        paras.append(_p("「보기」  " + "  /  ".join(cset["bogis"]),
                        A["C_bogis"]))
        for d in cset["defs"]:
            paras.append(_p(d, A["C_def"]))
    return {"paras": paras}


def _unit_d_box(content, A):
    d = content.get("D") or {}
    if not d.get("bogis_raw"):
        return {"skip": True}
    paras = []
    for raw in d["bogis_raw"]:
        if raw.startswith("〈보기〉"):        # v1: 〈보기〉 헤더 스킵
            continue
        for seg in _split_ones(raw):
            paras.append(_p(seg, A["D_box"]))
    if not paras:
        return {"skip": True}
    # v1 expandFrameAndMoveBelow(dBox, ['D 단어 new', '발문', 'E 전치사'])
    return {"paras": paras,
            "ops": {"expand_move": [A["D_item"], "발문", A["E_sent"]]}}


def _unit_d_item(content, A):
    d = content.get("D") or {}
    if not d.get("items"):
        return {"skip": True}
    # 항목 수가 템플릿 프레임 용량을 넘으면 오버셋(베타2 P8/P88) —
    # D박스와 동일하게 프레임을 늘리고 아래(발문·E전치사)를 밀어낸다
    return {"paras": [_p(it["text"], A["D_item"]) for it in d["items"]],
            "ops": {"expand_move": ["발문", A["E_sent"]]}}


def _unit_e(content, A):
    if not content.get("E"):
        return {"skip": True}
    return {"paras": [_p(f"{e['num']}. {e['text']}", A["E_sent"])
                      for e in content["E"]]}


# ── 정답 유닛 (v1 buildAnswerItems + postProcessAnswerStory 이식) ────────────

def _unit_answers(answers, A, CH):
    if not answers or not answers.get("A"):
        return {"skip": True}
    HDR, ITEM, SOL = A["ANS_hdr"], A["ANS_item"], A["ANS_sol"]
    paras = [_p(" 정답", HDR)]        # A 헤더: 공백1 (아이콘 pos 0)

    for a in answers["A"]:
        paras.append(_p(f"{a['num']}. {a['word']} : {a['meaning']}", ITEM))

    paras.append(_p("  정답", HDR))   # B (공백2 — 아이콘 pos 1)
    for b in answers.get("B") or []:
        paras.append(_p(b["answer"], ITEM))

    paras.append(_p("  정답", HDR))   # C
    for i, cset in enumerate(answers.get("C") or []):
        if i > 0:
            paras.append(_p("", SOL))
        paras.append(_p(f"[문제 {cset['set']}]", SOL))
        for ans in cset["answers"]:
            paras.append(_p(ans, ITEM))

    paras.append(_p("  정답", HDR))   # D
    for d in answers.get("D") or []:
        paras.append(_p(f"{d['word']} : {d['answer']}", ITEM))

    paras.append(_p("", SOL))         # E: 빈줄 + 헤더
    paras.append(_p("  정답", HDR))
    for e in answers.get("E") or []:
        paras.append(_p(e["sentence"], ITEM))

    # ── postProcessAnswerStory 등가 ops 계산 ────────────────────────────────
    hdr_idx = [i for i, p in enumerate(paras) if p["s"] == HDR]
    restart = []
    section = -1
    section_had_first = []
    sol_idx = []
    for i, p in enumerate(paras):
        if p["s"] == HDR:
            section += 1
            section_had_first.append(False)
        elif p["s"] == ITEM:
            if section >= 0 and not section_had_first[section]:
                section_had_first[section] = True
                # 첫 섹션(A)도 재시작 — v1은 section>0만 재시작해 A 섹션
                # 번호가 02부터 시작했다(베타2 실측: 헤더가 리스트 1번을
                # 소비, numberingContinue=true라 이어짐)
                restart.append(i)
        elif p["s"] == SOL and "[문제" in p["t"]:
            sol_idx.append(i)
    for si in sol_idx:
        nxt = si + 1
        if nxt < len(paras) and paras[nxt]["s"] == ITEM:
            restart.append(nxt)
    restart = sorted(set(restart))

    ops = {
        "numbering_restart": restart,
        "ans_char": {"style": CH["ANS"], "paras": hdr_idx},
        "icons": [{"p": h, "sec": s} for s, h in enumerate(hdr_idx[:5])],
        "ans_frame_fix": True,
    }
    return {"paras": paras, "ops": ops}


# ── 연습문제 유닛 (v1 practices 루프 + applyUnderlineMarkers 이식) ───────────

def _unit_prac_main(prac, PR):
    qs = prac.get("questions") or []
    if not qs:
        return {"skip": True}
    paras = []
    for qi, q in enumerate(qs):
        for ln in q["lines"]:
            clean, runs = _ul_runs(ln["text"])
            paras.append(_p(clean, PR[ln["sty"]], runs))
        if qi < len(qs) - 1:
            paras.append(_p("", PR["선지"]))   # v1: 문제 사이 빈줄(선지 스타일)
    return {"paras": paras}


def _unit_prac_ans(prac, PR):
    ans = prac.get("answers") or []
    if not ans:
        return {"skip": True}
    paras = []
    for a in ans:
        for ln in a["lines"]:
            clean, runs = _ul_runs(ln["text"])
            paras.append(_p(clean, PR[ln["sty"]], runs))
    return {"paras": paras}


# ── 플랜 조립 ────────────────────────────────────────────────────────────────

def content_to_plan(content, issue_num=""):
    A, PR, CH = _tables()
    days = content.get("days") or []
    practices = content.get("practices") or []

    flows = [
        {"area": "A", "find": {"first_style": A["A_word"]},
         "units": [_unit_a(d["content"], A) for d in days]},
        {"area": "B", "find": {"first_style": A["B_eng"]},
         "units": [_unit_b(d["content"], A) for d in days]},
        {"area": "C", "find": {"first_style": A["C_bogis"]},
         "units": [_unit_c(d["content"], A) for d in days]},
        {"area": "D_box", "find": {"first_style": A["D_box"]},
         "units": [_unit_d_box(d["content"], A) for d in days]},
        {"area": "D_item", "find": {"first_style": A["D_item"]},
         "units": [_unit_d_item(d["content"], A) for d in days]},
        {"area": "E", "find": {"first_style": A["E_sent"]},
         "units": [_unit_e(d["content"], A) for d in days]},
        {"area": "ans", "find": {"answer": {"second_style": A["ANS_item"]}},
         "units": [_unit_answers(d.get("answers"), A, CH) for d in days]},
        {"area": "prac_main", "find": {"practice_main": True},
         "units": [_unit_prac_main(p, PR) for p in practices]},
        {"area": "prac_ans", "find": {"practice_answer": True},
         "units": [_unit_prac_ans(p, PR) for p in practices]},
    ]
    issue_num = str(issue_num or "").strip()
    return {
        "format": "wbwt-flows-v1",
        "week_text": f"{issue_num}주 차" if issue_num else None,
        "ul_style": CH["UL"],
        "flows": flows,
    }


def unit_paras(unit):
    """검수/테스트용 — 유닛의 단락 목록 (skip이면 빈 리스트)."""
    if not unit or unit.get("skip"):
        return []
    return unit.get("paras") or []
