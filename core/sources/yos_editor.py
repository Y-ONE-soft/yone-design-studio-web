# -*- coding: utf-8 -*-
"""contents 원고(yos-workbook-v1) → 편집기 제작 틀(units.json)의 원고 — 자리 이름 → 글.

contents 는 지문마다 항목(item)을 보낸다: {"no", "content", "items": [{"key", "label", "content": {"kind", …}}]}.
편집기 틀은 「원고마다」 묶음(쪽 이름 = 구성 이름)이 레코드 목록을 받는다: {"A어휘선택": [{"제목", "지문번호": […], "지문": […]}, …]}.
바꾸는 규칙은 여기 한 곳(contents 는 원고를 가공하지 않고 보낸다 — core/sources/yos_workbook.py 와 같은 약속).

    to_content(data, sample) → (content, report)      sample = 틀에 넣어 둔 견본 원고(plan.content) — 구성 제목 등 틀 고정 값을 거기서

지금 받는 유형(2026-10-11 정본 워크북 틀, 시험: 어휘선택 1단계부터):
    vocab-choice  어휘선택 1단계 → 「A어휘선택」 (펼침면 한 벌 = 지문 4개, 「(1)❮ ⓐ a / ⓑ b ❯」 → 「[ ⓐ a / ⓑ b ]」)
"""
import re

_PICK = re.compile(r"(?:\(\d+\)\s*)?❮\s*(.*?)\s*❯")                     # contents 고르기 표시 — 앞의 (번호)는 원본 책에 없다


def _vocab_text(text):
    return _PICK.sub(lambda m: "[ " + re.sub(r"\s*/\s*", " / ", m.group(1)) + " ]", text or "").strip()


def _vocab_choice(passages, sample):
    """A어휘선택 — 펼침면 한 벌에 지문 4개(지문번호 · 지문). 제목은 틀 견본의 것(구성 이름표)"""
    title = ((sample.get("A어휘선택") or [{}])[0] or {}).get("제목") or "어휘 선택 1"
    per = len(((sample.get("A어휘선택") or [{}])[0] or {}).get("지문") or []) or 4
    recs = []
    for k in range(0, len(passages), per):
        chunk = passages[k:k + per]
        recs.append({"제목": title, "지문번호": [str(no) for no, _ in chunk], "지문": [_vocab_text(t) for _, t in chunk]})
    return {"A어휘선택": recs} if recs else {}


RULES = {"vocab-choice": _vocab_choice}                                  # 항목 kind → 바꾸기(지문 [(번호, 글)] , 견본) → {구성: 레코드들}


def to_content(data, sample=None):
    sample = sample or {}
    by_kind, report = {}, {"sent": [], "skipped": []}
    for p in (data or {}).get("passages") or []:
        for it in p.get("items") or []:
            c = it.get("content") or {}
            kind = c.get("kind") or it.get("key")
            if kind not in RULES:
                report["skipped"].append({"passage": p.get("no"), "key": it.get("key"), "label": it.get("label"), "why": "이 틀에 아직 자리 없음"})
                continue
            text = c.get("text") if kind == "vocab-choice" else c
            by_kind.setdefault(kind, []).append((p.get("no"), text))
            report["sent"].append({"passage": p.get("no"), "key": it.get("key"), "label": it.get("label")})
    content = {k: v for k, v in sample.items() if isinstance(v, str)}       # 머리글 자리(교재명·단원명) — 책 이름이 오면 그걸로
    title = ((data or {}).get("book") or {}).get("title")
    if title and "교재명" in content:
        content["교재명"] = title
    for kind, items in by_kind.items():
        content.update(RULES[kind](items, sample))
    return (content if by_kind else {}), report
