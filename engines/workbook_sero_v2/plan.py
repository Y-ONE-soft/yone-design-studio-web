"""워크북 세로 v2 렌더 플랜 빌더 — 사이클(문제) 단위 재편성.

세로 워크북은 한 문제(q_num)가 14페이지 사이클(STEP1/2 = 10p + STEP3 = 4p)을
차지하고 사이클이 문제 수만큼 반복되는 구조다. 파서(engines/workbook_sero/
parser.py 재사용)가 content["cycles"]로 문제별 스텝 데이터를 주면, 이 모듈이
사이클마다 workbook_v2의 STEP_BUILDERS를 그대로 호출해 슬롯(페이지 프레임)
단위 플랜을 만든다.

v1 대응 (engines/workbook_sero/jsx/run.jsx):
  - seroAugment      → _augment       (마커 단락 prepend — [N]/{N}/[code]/{code})
  - seroProcessCycle → _build_cycle   (페이지 오프셋별 슬롯 → 스텝 매핑)
  - seroClearFrame   → {"clear": true} 슬롯 (원고 없는 프레임의 잔존 데이터 비움)
  - 페이지번호 frame → qnum_slots     (P+5/P+7/P+8 소형 frame에 q_num 표기)
  - processStep3의 {code} prepend + [기본 단락] → step3 유닛 선두 $BASIC 단락

step3 kind 주석: 세로 파서는 Step3 폴더를 직접 파싱해 kind가 없으므로,
여기서 core.structure.classify_paragraphs로 주석 후 build_step3에 전달
(v1 workbook parser의 _annotate_step3_kinds와 동일 의미론, fail-open).

플랜 형식 "wb-sero-cycles-v1":
  {"format": "wb-sero-cycles-v1", "cycle_count": N, "cycles": [사이클...],
   "unsupported": []}
사이클: {"q_num", "q_num_end", "code",
         "slots": [{"slot", "step", "units", ("ul_style"), ("clear")}],
         "qnum_slots": ["p5_num", ...], "warnings": [...]}
유닛/단락 형식은 workbook_v2와 동일 ({"t","s","runs",("icon")}, dict 유닛의
page_break 포함) — 실행기(core/jsx/workbook_sero_flow.body.jsx)가 해석한다.
"""
import re

from engines.workbook_v2.plan import (STEP_BUILDERS, _RE_3GAPS, build_step3,
                                      unit_paras)  # noqa: F401 (unit_paras — verify 재사용)

# ── 슬롯 → 스텝 매핑 (v1 seroProcessCycle의 페이지 오프셋 구조) ──────────────
# slot 이름은 실행기의 기하 해석 규칙과 1:1 (pN_main = 최대 높이 frame 등).
_SLOT_STEPS = [
    ("p0_top", "step1_a1_2"),   # P+0 위 frame — 어휘 선택 2단계
    ("p0_bot", "step1_a1"),     # P+0 아래 frame — 어휘 선택 1단계
    ("p1_main", "step1_a2"),    # P+1 본문 O/X
    ("p2_main", "step1_b1"),    # P+2 본문 정리
    ("p3_main", "step1_b2"),    # P+3 내용 종합
    ("p4_main", "step1_c1"),    # P+4 문장 배열
    ("p5_main", "step1_c2"),    # P+5 빈칸 어휘 (+ p5_num 페이지번호)
    ("p6_sel", "step2_a1"),     # P+6 위 frame — 어법 선택(선택형)
    ("p6_btm", "step2_a1_btm"),  # P+6 아래 frame — 어법 선택(객관식)
    ("p7_main", "step2_b1"),    # P+7 어법 O/X (+ p7_num)
    ("p8_main", "step2_c1"),    # P+8 빈칸 어법 (+ p8_num)
    ("p9_main", "step2_c2"),    # P+9 영작 배열
]

# v1 페이지 게이트: excludeSet[키]가 참이면 해당 페이지/frame을 아예 안 건드림.
# (v1 quirk 보존: step1_a1_2 단독 제외는 P+0 게이트에 없음 — step1_a1이 게이트)
_SLOT_GATES = {
    "p0_top": ("step1_a1",),
    "p0_bot": ("step1_a1",),
    "p1_main": ("step1_a2",),
    "p2_main": ("step1_b1",),
    "p3_main": ("step1_b2",),
    "p4_main": ("step1_c1",),
    "p5_main": ("step1_c2",),
    "p6_sel": ("step2_a1",),
    "p6_btm": ("step2_a1", "step2_a1_btm"),
    "p7_main": ("step2_b1",),
    "p8_main": ("step2_c1",),
    "p9_main": ("step2_c2",),
}

# q_num 표기 frame (v1: P+5/P+7/P+8의 소형 frame에 q_num 텍스트)
_QNUM_SLOTS = [("p5_num", "step1_c2"), ("p7_num", "step2_b1"),
               ("p8_num", "step2_c1")]

# ── 마커 prepend 규칙 (v1 seroAugment) ──────────────────────────────────────
_MARKER_RULES = {
    "step1_a1": "bracket_qnum",     # [20]
    "step1_a2": "bracket_qnum",
    "step1_b1": "bracket_qnum",
    "step1_b2": "bracket_qnum",
    "step1_a1_2": "bracket_code",   # [250920] (code 없으면 [20])
    "step1_c1": "brace_qnum",       # {20}
    "step2_a1": "brace_qnum",
    "step2_c2": "brace_code",       # {250920}
    # step1_c2 / step2_a1_btm / step2_b1 / step2_c1 → 마커 없음
}


def _augment(paras, q_num, code, step_key):
    """v1 seroAugment — 마커 단락을 파서 형식({"text","runs"})으로 prepend."""
    rule = _MARKER_RULES.get(step_key)
    if not rule:
        return paras
    if rule == "bracket_qnum":
        marker = "[" + q_num + "]"
    elif rule == "bracket_code":
        marker = "[" + (code or q_num) + "]"
    elif rule == "brace_qnum":
        marker = "{" + q_num + "}"
    else:                            # brace_code
        marker = "{" + (code or q_num) + "}"
    return [{"text": marker, "runs": []}] + list(paras)


# v1 processStep3 배경 규칙 (문장삽입): 발문에 "주어진 문장/글"·"들어갈 위치"
# → 다음 첫 비빈 지문 단락을 배경(S3_BG)으로. 분류기(core.structure)는
# q_code(taxonomy leaf)가 있어야 P-CONTEXT를 주는데, 이 발문들이 taxonomy에
# 미등록이라 q_code가 비어 지문(P)으로 남는다 — v1 규칙을 후처리로 보강.
_RE_S3_INSERT_Q = re.compile(r"주어진\s*(?:문장|글)|들어갈\s*위치")


# 문장삽입 변형 C1의 조건(주어진 문장) 감지 — v1 conditionIdxList와 동일 시퀀스
_RE_C1_CHOICE_HEAD = re.compile(r"^\s*\([A-Z]\)")


def _augment_c1_condition_gap(paras):
    """C1 조건(주어진 문장) 단락에 3+ 공백 suffix → BTM(분홍 박스) 스타일 유도.

    v1 세로 파서의 _augment_step1_c1_passage는 '다음 단락이 (A)로 시작'하는
    문장배열 변형만 커버한다. 문장삽입 변형(다음 단락이 ①-번호 본문)은
    미커버라 v1 실물 출력에서 조건이 무스타일로 방치됐다(발문 미삽입).
    세로 v2는 같은 의도를 일반화: (A)-선지 시퀀스 뒤 첫 영문(한글 미포함)
    단락에 3+ 공백이 없으면 부여 → build_step1_c1의 pass 4d가 BTM으로
    스타일 → 발문 자동 삽입 + 하단 유닛(NEXT_FRAME) 경계가 발문 앞에 형성
    (템플릿 레퍼런스 레이아웃: 발문 → 주어진 문장 분홍 박스 → 본문 박스).
    """
    saw_choice = False
    out = list(paras)
    for i, p in enumerate(out):
        text = (p.get("text") or "") if isinstance(p, dict) else str(p)
        trim = text.strip()
        if not trim:
            continue
        if _RE_C1_CHOICE_HEAD.match(text):
            saw_choice = True
            continue
        if not saw_choice:
            continue
        if not re.match(r"^[A-Za-z]", trim) or re.search("[가-힣]", trim):
            continue
        if _RE_3GAPS.search(text):
            break       # 이미 3+ 공백 (파서 helper가 처리한 변형) — 그대로
        new_p = dict(p) if isinstance(p, dict) else {"text": str(p),
                                                     "runs": []}
        new_p["text"] = text + "   "
        if isinstance(new_p.get("runs"), list) and new_p["runs"]:
            new_p["runs"] = list(new_p["runs"]) + [{"t": "   ", "ul": False}]
        out[i] = new_p
        break
    return out


def _annotate_step3_kinds(paras, warnings):
    """core.structure 판정 → 단락 사본에 kind 병기 (fail-open).

    v1 workbook parser의 _annotate_step3_kinds와 동일 의미론 — 세로 파서는
    Step3 폴더 직접 파싱 경로라 kind가 없어 여기서 주석한다.
    """
    try:
        from core.structure import classify_paragraphs
        results = classify_paragraphs(paras)
    except Exception as e:                                  # noqa: BLE001
        warnings.append(f"step3 kind 주석 실패 — 기본 스타일 배치: {e}")
        return list(paras)
    # 문장삽입 발문 뒤 첫 비빈 P → P-CONTEXT (v1 processStep3 pass 5/7.5)
    for i, r in enumerate(results):
        if r["kind"] not in ("Q", "Q-INTRO"):
            continue
        if not _RE_S3_INSERT_Q.search(r["text"]):
            continue
        for j in range(i + 1, len(results)):
            if results[j]["kind"] == "BLANK":
                continue
            if results[j]["kind"] == "P":
                results[j]["kind"] = "P-CONTEXT"
            break
    out = []
    for r in results:
        p = r["para"]
        if isinstance(p, dict):
            p = dict(p)
            p["kind"] = r["kind"]
            if r.get("q_code"):
                p["q_code"] = r["q_code"]
        out.append(p)
    return out


def _build_cycle(cyc, exclude, workbook_type):
    """사이클 1개 → 슬롯 플랜. workbook_v2 STEP_BUILDERS 재사용."""
    q_num = str(cyc.get("q_num") or "?")
    code = cyc.get("code") or ""
    steps = cyc.get("steps") or {}
    slots = []
    warnings = []

    for slot, step_key in _SLOT_STEPS:
        if any(g in exclude for g in _SLOT_GATES[slot]):
            continue        # v1: 페이지/frame을 아예 건드리지 않음
        paras = steps.get(step_key) or []
        if not paras:
            # v1 seroClearFrame — 원본 잔존 데이터 사고 방지
            slots.append({"slot": slot, "step": step_key, "clear": True})
            continue
        builder = STEP_BUILDERS[step_key]
        if step_key == "step1_c1":
            paras = _augment_c1_condition_gap(paras)
        augmented = _augment(paras, q_num, code, step_key)
        if step_key == "step1_c1":
            # split_condition=False: 세로 C1 페이지는 프레임 2개(상단 보기 +
            # 하단 발문/지문). v1 실물 출력에는 조건(주어진 문장) NEXT_FRAME이
            # 없으며(FRAME BREAK 재적용이 헤더+하단만 복원), 켜면 3프레임을
            # 요구해 사이클 페이지가 오버플로우된다 (E2E 실증).
            built = builder({"paragraphs": augmented},
                            workbook_type=workbook_type,
                            exclude_btm=("step1_c1_btm" in exclude),
                            split_condition=False)
        else:
            built = builder({"paragraphs": augmented})
        entry = {"slot": slot, "step": step_key, "units": built["units"]}
        if built.get("ul_style"):
            entry["ul_style"] = built["ul_style"]
        warnings.extend(f"Q{q_num} {w}" for w in built.get("warnings", []))
        slots.append(entry)

    # STEP3 — v1: 데이터 없으면 페이지를 건드리지 않음 (clear 없음)
    if "step3" not in exclude:
        s3_paras = steps.get("step3") or []
        if s3_paras:
            annotated = _annotate_step3_kinds(s3_paras, warnings)
            built = build_step3({"normal": [{"question_num": q_num,
                                             "paragraphs": annotated}],
                                 "short": []})
            units = built["units"]
            warnings.extend(f"Q{q_num} {w}"
                            for w in built.get("warnings", []))
            if not units:
                warnings.append(f"Q{q_num} step3: 배치할 단락 없음")
            else:
                if code:
                    # v1 processStep3: {code} prepend + [기본 단락] (pass 19)
                    units[0] = ([{"t": "{" + code + "}", "s": "$BASIC",
                                  "runs": []}] + list(units[0]))
                slots.append({"slot": "step3", "step": "step3",
                              "units": units})

    qnum_slots = [slot for slot, gate in _QNUM_SLOTS if gate not in exclude]
    return {"q_num": q_num, "q_num_end": cyc.get("q_num_end"),
            "code": code, "slots": slots, "qnum_slots": qnum_slots,
            "warnings": warnings}


def content_to_plan(content, exclude=None, workbook_type="모의고사"):
    """세로 파서 content(cycles) → wb-sero-cycles-v1 플랜."""
    exclude = set(exclude or [])
    cycles = [_build_cycle(cyc, exclude, workbook_type)
              for cyc in content.get("cycles", [])]
    return {"format": "wb-sero-cycles-v1", "cycle_count": len(cycles),
            "cycles": cycles, "unsupported": []}
