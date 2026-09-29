"""원고 형식 · 동형 모의고사 — 회차 원고(hwpx·docx) 하나 = 시험지 한 회 = 원고(세트) 하나.

원고를 읽는 일은 새로 짜지 않는다 — 통합웹 모의고사 엔진 파서(`engines/mockexam/parser.py`)가 이미 단락마다 역할(pstyle)을
붙인다. 여기서는 단락을 원고 순서 그대로 블록 하나씩으로 옮기고, 역할 이름을 자리 이름으로 바꾼다. 문항 번호는 발문 앞에 붙인다
(원고에는 번호가 없고 차례만 있다). 시험지는 한 흐름 — 면에 「자리 더하기」로 여러 자리를 고른 2단 글상자 하나를 두면 흘러 간다.
"""
import os
import re
import unicodedata

ID, NAME = "mockexam", "동형 모의고사 (회차 원고 hwpx·docx)"

LABELS = {
    "m_group": "묶음 발문", "m_q": "발문(번호)", "m_passage": "지문", "m_choice": "선지", "m_box": "보기·순서 상자",
    "m_desc": "서술형 발문", "m_answer_line": "서술형 답란",
    "school": "학교", "exam_title": "시험 이름", "round_label": "회차",
}
# 흘려 넣을 때 역할마다 기본 모양 — 발문은 굵게·앞 간격, 지문은 테두리 상자, 선지는 들여쓰기 (글상자에서 바꿀 수 있다)
FMT = {"m_group": {"b": True, "space": 3}, "m_q": {"b": True, "space": 3}, "m_desc": {"b": True, "space": 3},
       "m_passage": {"box": True}, "m_box": {"box": True}, "m_choice": {"indent": 3}}

_ROLE = {"다음 글을 읽고": "m_group", "문제 번호": "m_q", "선지": "m_choice", "서술형 번호": "m_desc", "서술형답지": "m_answer_line",
         "지문_순서": "m_box", "테두리_순서": "m_box", "테두리_순서삽입": "m_box"}
_RE_NAME = re.compile(r"^(?P<school>.+?고)\s*(?P<grade>[1-3])?.*?(?P<round>\d+)\s*회")


def kinds():
    return ["동형 모의고사"]


def detect(names):
    return bool(names) and all(re.search(r"(모의고사|동형)", unicodedata.normalize("NFC", os.path.basename(n))) and
                               n.lower().endswith((".hwpx", ".docx", ".hwp")) for n in names)


def _rich(p):
    runs = p.get("runs") or []
    if not any(r.get("ul") for r in runs):
        return p.get("text") or ""
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


def paragraphs_to_set(paras, school="", grade="", round_num=1):
    """단락 목록(역할 pstyle 이 붙은) → 세트 하나."""
    title = f"{school}{grade and ' 고' + grade} 동형 모의고사 {round_num}회".strip()
    blocks = [{"block": "head", "optional": True,
               "fields": {"school": school, "exam_title": title, "round_label": f"{round_num}회"}}]
    q = 0
    for p in paras:
        role = _ROLE.get(p.get("pstyle") or "", "m_passage")
        text = (p.get("text") or "").strip()
        if role == "m_q":
            q += 1
            val = _rich(p)
            val = f"{q}. {text}".strip() if isinstance(val, str) else [f"{q}. "] + val
        elif not text:
            continue
        else:
            val = _rich(p)
        blocks.append({"block": role, "fields": {role: val}})
    return {"kind": "동형 모의고사", "id": f"{school}{grade} {round_num}회".strip(), "group": f"{round_num}회", "blocks": blocks}


def parse(paths, log=None):
    from engines.mockexam import parser as P
    msgs = log if log is not None else []
    sets = []
    for fp in paths:
        name = unicodedata.normalize("NFC", os.path.basename(fp))
        m = _RE_NAME.search(name)
        school, grade, rnd = (m.group("school"), m.group("grade") or "", int(m.group("round"))) if m else ("", "", len(sets) + 1)
        c = P.parse_manuscript(fp, school, f"고{grade}" if grade else "", "", "", "", rnd, lambda x: msgs.append(str(x)))
        paras = [p for q in c.get("questions") or [] for p in q.get("paragraphs") or []]
        sets.append(paragraphs_to_set(paras, school, grade, rnd))
        msgs.append(f"{name}: 단락 {len(paras)} · 발문 {sum(1 for b in sets[-1]['blocks'] if b['block'] == 'm_q')}")
    return sets, msgs
