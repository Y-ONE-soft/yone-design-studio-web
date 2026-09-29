"""워크북 원고(스텝별 docx·hwpx 여러 개) → 캔버스 원고 세트.

원고를 읽는 일은 새로 짜지 않는다 — 통합웹 워크북 v2 엔진이 이미 읽는다(`engines/workbook_v2`):
    원고 파일들 → content.json → render_plan.json(wb-flows-v1) → 스텝·지문 묶음·역할(data_mod.from_plan)
여기서는 그 결과를 **스텝 × 지문마다 세트 하나**로 옮긴다.

    세트 = {kind: "A2 본문 O/X", id: "20·1A2", group: "20", labels: {자리: 이름}, blocks: [{block: 역할, fields}]}

자리 이름은 역할 이름 그대로다(ox_item · box_body · q_prompt …) — 원고의 단락 역할 = 인디자인 단락 스타일.
화면에는 labels 의 한글 이름으로 보인다. 글에 섞여 있는 정답(빈칸 1[fun], 발문 끝 ③)은 떼어 answer 자리로 옮긴다
— 학생 면에 정답이 찍히면 안 된다.
"""
import os
import re
import tempfile

LABELS = {
    "pnum": "지문 번호", "no": "번호", "answer": "정답",
    "step_tag": "스텝 표시", "code": "유형 코드", "type_title": "유형 제목",          # 머리 — 원고가 유형마다 채운다
    "vocab_sel": "어휘 선택 지문", "box_body": "본문 박스", "ox_item": "O/X 문항",
    "sum_topic": "내용 정리 · 주제", "sum_title": "내용 정리 · 제목", "sum_line": "내용 정리 · 줄",
    "b2_q": "내용 종합 발문", "b2_choice": "내용 종합 선지",
    "arr_line": "문장 배열 줄", "arr_given": "주어진 문장", "arr_bottom": "문장 배열 하단 지문",
    "blank_vocab": "빈칸 어휘", "blank_kr": "빈칸 해석", "gram_sel": "어법 선택 지문",
    "gram_bottom": "어법 선택 하단", "gram_ox": "어법 O/X", "blank_gram": "빈칸 어법",
    "write_kr": "영작 배열 해석", "write_box": "영작 배열 보기",
    "q_prompt": "하단 문제 발문", "q_passage": "하단 문제 지문", "q_choice": "하단 문제 선지",
}

_RE_LEAD_NO = re.compile(r"^\s*(\(\d{1,3}\)|\d{1,3}\.|\([A-Z]\))\s*")        # (1) · 1. · (A)
_RE_BLANK = re.compile(r"(\d{1,3})\[([^\[\]]*)\]")                            # 1[fun] — 괄호 안이 정답
_RE_TAIL_ANSWER = re.compile(r"\s*([①-⑩])\s*$")                              # 발문 끝의 정답 번호
_RE_TAG = re.compile(r"^\s*\{(주제|제목)\}\s*")
_NUMBERED = {"ox_item", "b2_q", "gram_ox", "arr_line", "arr_bottom"}


def _rich(u):
    """단락 → 서식 조각(밑줄) 또는 문자열."""
    runs = u.get("runs") or []
    if not any(r.get("ul") for r in runs):
        return u.get("text") or "".join(r.get("t", "") for r in runs)
    out = []
    for r in runs:
        t = r.get("t") or ""
        if not t:
            continue
        if r.get("ul"):
            out.append({"t": t, "u": True})
        elif out and isinstance(out[-1], str):
            out[-1] += t
        else:
            out.append(t)
    return out


def _cut_head(val, n):
    """값의 앞 n 글자를 뗀다 (문자열 / 서식 조각)."""
    if isinstance(val, str):
        return val[n:].lstrip()
    from core.units.manuscript import _strip_prefix
    return _strip_prefix(val, n)


def unit_fields(u):
    """역할 단락 하나 → (블록=역할, 자리 값들). 빈 단락이면 None."""
    role = u.get("role") or "basic"
    text = (u.get("text") or "").strip()
    if not text or role in ("basic", "intro"):
        return None
    val = _rich(u)
    f = {}
    if role in _NUMBERED:
        m = _RE_LEAD_NO.match(text)
        if m:
            f["no"] = m.group(1)
            val = _cut_head(val, m.end())
    if role in ("blank_vocab", "blank_gram"):
        answers = []

        def blank(m):
            answers.append(f"({m.group(1)}) {m.group(2).strip()}")
            return f"({m.group(1)}) " + "_" * max(6, len(m.group(2)) + 2)
        val = _RE_BLANK.sub(blank, text)
        if answers:
            f["answer"] = " · ".join(answers)
    elif role == "gram_sel":
        val = _RE_BLANK.sub(lambda m: f"({m.group(1)})[ {m.group(2).strip()} ]", text)
    elif role == "q_prompt":
        m = _RE_TAIL_ANSWER.search(text)
        if m:
            f["answer"] = m.group(1)
            val = text[: m.start()].rstrip()
    elif role in ("sum_topic", "sum_title"):
        val = _RE_TAG.sub("", text)
    f[role] = val
    return role, f


def _step_tag(st):
    """「STEP 01   FRAME」 — 기준 틀 머리의 스텝 표시 (빈칸은 줄바꿈 없는 빈칸이라 안 합쳐진다)."""
    return f"STEP {int(st.get('step') or 0):02d}\u00a0\u00a0\u00a0{st.get('tag') or ''}".rstrip()


def steps_to_sets(steps):
    """스텝 목록(data_mod.from_plan 의 steps) → 세트 목록. 스텝 3(실전)은 아직 뺀다."""
    sets = []
    for st in steps:
        if int(st.get("step") or 0) not in (1, 2):
            continue
        kind = f"{st.get('logo', '')} {st.get('title', '')}".strip()
        for g in st.get("groups") or []:
            label = str(g.get("label") or "").strip()
            if not label:
                continue
            blocks = [{"block": "pnum", "fields": {"pnum": label}},
                      # 머리 정보 — 머리 띠 하나가 모든 유형·스텝에 맞게. 받을 자리가 없는 면이 많으니 없어도 검수에 안 뜬다(optional)
                      {"block": "head", "optional": True, "fields": {"step_tag": _step_tag(st), "code": st.get("logo", ""),
                                                                     "type_title": st.get("title", "")}}]
            for unit in list(g.get("units") or []) + list(g.get("attach") or []):
                for u in unit:
                    r = unit_fields(u)
                    if r:
                        blocks.append({"block": r[0], "fields": r[1]})
            if len(blocks) > 2:
                # id 는 스텝까지 — Step1 B1(본문 정리)과 Step2 B1(어법 O/X)이 같은 로고라 겹치면 저장에서 덮인다
                sets.append({"kind": kind, "id": f"{label}·{st.get('step')}{st.get('logo', '')}{'-2' if st.get('key', '').endswith('_2') else ''}",
                             "group": label, "step": st.get("key"), "labels": LABELS, "blocks": blocks})
    return sets


def from_files(paths, log=None):
    """워크북 원고 파일들 → (세트, log). 워크북 v2 엔진으로 읽는다."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    from core.render_vivlio.series.workbook import data as data_mod
    import json
    msgs = log if log is not None else []
    job = tempfile.mkdtemp(prefix="units_wb_")
    eng = WorkbookV2Engine()
    cj = eng.parse({"manuscripts": list(paths)}, job, lambda m: msgs.append(str(m)))
    try:
        eng.prepare_jsx(cj, job, lambda m: msgs.append(str(m)))           # 플랜을 쓴 뒤 인디자인 원본을 찾다 멈춘다 — 플랜만 쓴다
    except Exception:
        pass
    plan = os.path.join(job, "render_plan.json")
    if not os.path.exists(plan):
        raise RuntimeError("워크북 원고를 못 읽었다: " + " / ".join(msgs[-3:]))
    with open(plan, encoding="utf-8") as fh:
        data = data_mod.from_plan(json.load(fh), log=lambda m: msgs.append(str(m)))
    return steps_to_sets(data.get("steps") or []), msgs


_RE_STEP_NAME = re.compile(r"(?i)step\s*[12]\s*[A-C]\d")


def looks_like_workbook(names):
    """파일 이름이 `Step1 A2 …` 꼴이 둘 이상이면 워크북 원고 묶음."""
    return sum(1 for n in names if _RE_STEP_NAME.search(os.path.basename(n))) >= 2


def catalog():
    """원고 없이도 틀을 그릴 수 있게 — 워크북 유형 이름(받는 원고)과 자리 이름(원고 자리)을 엔진의 스텝 표에서.

    세트의 kind 와 같은 이름이다(steps_to_sets 가 같은 logo·title 로 짓는다).
    """
    from core.render_vivlio.series.workbook.data import STEP_META
    kinds = [f"{m['logo']} {m['title']}" for m in STEP_META.values() if m["step"] in (1, 2) and m.get("layout") != "attach"]
    return {"kinds": kinds, "labels": {k: v for k, v in LABELS.items() if k not in ("no", "answer")}}
