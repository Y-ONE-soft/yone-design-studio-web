# -*- coding: utf-8 -*-
"""Y.OS contents 의 워크북 원고(지문별 등록 항목) → 워크북 data.json — **매핑은 여기 한 곳.**

contents 의 「워크북 · 교재별 제작 현황 → 지문 → 유형별 등록 현황」 화면이 보내는 것:

    {"format": "yos-workbook-v1",
     "book": {"line1": "고1 모의고사", "line2": "26년 3월", "title": "…"},        # 표지 문구(선택)
     "passages": [
        {"no": "20", "content": "<원문 지문>",
         "items": [{"key": "vocab-choice", "label": "어휘선택 1단계", "content": {…}}, …]}]}

`items[].content` 는 contents 가 외부 원고(docx)를 구조화해 둔 그대로다
(yos-contents-web `scripts/workbook-source/lib/content.ts` 의 `kind` 별 모양).
여기서 `core/render_vivlio/series/workbook/data.py` 가 읽는 data.json 으로 바꾼다 —
스텝 메타는 그쪽 `STEP_META` 를 그대로 쓴다(지면 짜임은 데이터다).

contents 항목 key → 스튜디오 스텝:
    vocab-choice        step1_a1     어휘 선택 1      텍스트의 `(1)❮ ⓐ a / ⓑ b ❯` → `(1)[ ⓐ a / ⓑ b ]`
    vocab-choice-2      step1_a1_2   어휘 선택 2      (1단계 원고에 (1) 이 두 번 나오면 뒤쪽을 2단계로)
    content-ox(-en)     step1_a2     본문 O/X         본문 + 진술 (n)
    content-summary     step1_b2     내용 종합        (n) 질문 + ①~ 선지
    sentence-order(-2)  step1_c1     문장 배열        (A)~ 보기
    vocab-blank(-2)     step1_c2     빈칸 어휘        `n[o ]` + 정답 → `n[answer]` (앞 글자 힌트)
    grammar-choice      step2_a1     어법 선택        `n[a / b]` 본문; answer-key 판본은 하단 ①~⑤ 상자
    grammar-ox          step2_b1     어법 O/X         `n. 문장`
    grammar-fix         step2_b1     어법 O/X         `n[word]` 표시를 밑줄로 — 문장마다 한 줄
    grammar-blank       step2_c1     빈칸 어법        `n[ ]` + 정답 → `n[answer]` (힌트 없음)
    writing-order       step2_c2     영작 배열        한글 + ( 조각 / 조각 )
    mock-exam · outline · content-summary(문항형)  step3  실전 문제
    interpretation-1/2 · raw · 그 밖  → 건너뛴다(로그에 남긴다). 없는 것을 지어내지 않는다.
"""
import re

from core.render_vivlio.series.workbook.data import STEP_META, STEP_ORDER

FORMAT = "yos-workbook-v1"

_KEY_STEP = {
    "vocab-choice": "step1_a1", "vocab-choice-2": "step1_a1_2",
    "content-ox": "step1_a2", "content-ox-en": "step1_a2",
    "content-summary": "step1_b2",
    "sentence-order": "step1_c1", "sentence-order-2": "step1_c1",
    "vocab-blank": "step1_c2", "vocab-blank-2": "step1_c2",
    "grammar-choice": "step2_a1",
    "grammar-ox": "step2_b1", "grammar-fix": "step2_b1",
    "grammar-blank": "step2_c1",
    "writing-order": "step2_c2",
    "mock-exam": "step3", "outline": "step3",
}

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
_RE_ANGLE = re.compile(r"\((\d+)\)\s*❮\s*([^❯]*?)\s*❯")     # (1)❮ ⓐ a / ⓑ b ❯
_RE_SQUARE_NO_LETTER = re.compile(r"(?<![A-Za-z])(\d+)\[([^\[\]]+)\]")
_RE_SENT_SPLIT = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+(?=[A-Z\"“‘(])")


def _block(role, text, runs=None, icon=None):
    return {"role": role, "text": text, "runs": runs if runs is not None else [{"t": text, "ul": False}],
            "icon": icon}


def _circ(i):
    return _CIRCLED[i] if i < len(_CIRCLED) else f"({i + 1})"


def _sentences(text):
    return [s.strip() for s in _RE_SENT_SPLIT.split((text or "").strip()) if s.strip()]


# ── 항목별 변환: content → (유닛 목록, 하단 attach 유닛 목록 or None) ─────────

def _vocab_choice(c):
    text = _RE_ANGLE.sub(lambda m: f"({m.group(1)})[ {m.group(2)} ]", str(c.get("text") or ""))
    return [[_block("vocab_sel", text)]], None


def _split_two_stages(c):
    """어휘 선택 원고 한 벌에 `(1)` 이 두 번 나오면 [1단계 본문, 2단계 본문]. 아니면 [본문]."""
    text = str(c.get("text") or "")
    hits = [m.start() for m in re.finditer(r"\(1\)\s*[❮\[]", text)]
    if len(hits) >= 2:
        return [text[:hits[1]].strip(), text[hits[1]:].strip()]
    return [text]


def _content_ox(c, passage):
    blocks = []
    if passage:
        blocks.append(_block("box_body", passage))
    blocks.append(_block("b2_q", "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오.", runs=[]))
    for s in c.get("statements") or []:
        blocks.append(_block("ox_item", f"({s.get('no')}) {s.get('text') or ''}", icon="TF 버튼"))
    return [blocks], None


def _content_summary(c, passage):
    blocks = []
    if passage:
        blocks.append(_block("box_body", passage))
    for q in c.get("questions") or []:
        blocks.append(_block("b2_q", f"({q.get('no')}) {q.get('q') or ''}"))
        for i, ch in enumerate(q.get("choices") or []):
            blocks.append(_block("b2_choice", f"{_circ(i)} {ch}"))
    return [blocks], None


def _sentence_order(c):
    lines = [_block("arr_line", f"({o.get('tag')}) {o.get('text') or ''}") for o in c.get("options") or []]
    return [lines], None


def _blank_rows(c, role):
    """빈칸 어휘·어법 — `n[o ]`(힌트) 를 `n[정답]` 으로. 정답이 없으면 힌트 글자 그대로 둔다."""
    blocks = []
    for r in c.get("rows") or []:
        answers = {b.get("no"): (b.get("answer") or "").strip() for b in r.get("blanks") or []}
        hints = {b.get("no"): (b.get("hint") or "").strip() for b in r.get("blanks") or []}

        def rep(m):
            no = int(m.group(1))
            w = answers.get(no) or hints.get(no) or m.group(2).strip()
            return f"{no}[{w}]" if w else m.group(0)
        blocks.append(_block(role, _RE_SQUARE_NO_LETTER.sub(rep, str(r.get("en") or ""))))
        if r.get("ko"):
            blocks.append(_block("blank_kr", str(r["ko"])))
    return [blocks], None


def _grammar_choice(c, passage):
    if c.get("form") == "answer-key":
        # 5지선다 판본 — 본문에 ①~⑤ 가 박힌 하단 상자. 본문 없이 정답만 온 판본은 지면이 없다.
        text = str(c.get("text") or "")
        if not text:
            return None, None
        return [], [[_block("gram_bottom", text)]]
    return [[_block("gram_sel", str(c.get("text") or ""))]], None


def _grammar_ox(c):
    lines = [_block("gram_ox", f"{s.get('no')}.  {s.get('text') or ''}", icon="TF 버튼")
             for s in c.get("sentences") or []]
    return [lines], None


def _grammar_fix(c):
    """`A job search 1[are] not …` → 문장마다 한 줄, 표시한 낱말은 밑줄(번호는 뗀다)."""
    text = str(c.get("text") or "")
    if not text:
        return None, None
    lines = []
    for i, sent in enumerate(_sentences(text), 1):
        runs, pos = [], 0
        for m in _RE_SQUARE_NO_LETTER.finditer(sent):
            if m.start() > pos:
                runs.append({"t": sent[pos:m.start()], "ul": False})
            runs.append({"t": m.group(2).strip(), "ul": True})
            pos = m.end()
        if pos < len(sent):
            runs.append({"t": sent[pos:], "ul": False})
        head = f"{i}.  "
        lines.append(_block("gram_ox", head + "".join(r["t"] for r in runs),
                            runs=[{"t": head, "ul": False}] + runs, icon="TF 버튼"))
    return [lines], None


def _writing_order(c):
    blocks = []
    for it in c.get("items") or []:
        blocks.append(_block("write_kr", str(it.get("ko") or "")))
        blocks.append(_block("write_box", "( " + " / ".join(it.get("chunks") or []) + " )"))
        blocks.append(_block("basic", "", runs=[], icon="STEP2 영작 답지"))
    return [blocks], None


def _step3(c, passage):
    blocks = []
    for q in c.get("questions") or []:
        prompt = str(q.get("prompt") or q.get("q") or "")
        if not prompt:
            continue
        blocks.append(_block("intro", "다음 글을 읽고 물음에 답하시오.", runs=[]))
        blocks.append(_block("s3_q", prompt))
        body = str(q.get("passage") or passage or "")
        if body:
            blocks.append(_block("s3_passage", body))
        for i, ch in enumerate(q.get("choices") or []):
            blocks.append(_block("s3_choice", f"{_circ(i)} {ch}"))
    return ([blocks], None) if blocks else (None, None)


def _convert(key, content, passage):
    """항목 하나 → (유닛 목록 or None, attach 유닛 목록 or None). None 이면 건너뛴다."""
    c = content if isinstance(content, dict) else {}
    kind = str(c.get("kind") or "")
    if key in ("vocab-choice", "vocab-choice-2"):
        return _vocab_choice(c)
    if key in ("content-ox", "content-ox-en"):
        return _content_ox(c, passage)
    if key == "content-summary":
        # 같은 key 가 두 모양이다 — (n)질문+선지(step1_b2) / 문항형(mock-exam 꼴)
        if kind in ("mock-exam", "outline"):
            return _step3(c, passage)
        return _content_summary(c, passage)
    if key in ("sentence-order", "sentence-order-2"):
        return _sentence_order(c)
    if key in ("vocab-blank", "vocab-blank-2"):
        return _blank_rows(c, "blank_vocab")
    if key == "grammar-choice":
        return _grammar_choice(c, passage)
    if key == "grammar-ox":
        return _grammar_ox(c)
    if key == "grammar-fix":
        return _grammar_fix(c)
    if key == "grammar-blank":
        return _blank_rows(c, "blank_gram")
    if key == "writing-order":
        return _writing_order(c)
    if key in ("mock-exam", "outline"):
        return _step3(c, passage)
    return None, None


# ── 조립 ───────────────────────────────────────────────────────────────────

def to_data(raw, log=None):
    """`yos-workbook-v1` → data.json. 항목이 하나도 안 잡히면 ValueError."""
    log = log or (lambda *_: None)
    if raw.get("format") != FORMAT:
        raise ValueError(f"모르는 형식: {raw.get('format')} (기대 {FORMAT})")
    passages = raw.get("passages")
    if not passages and raw.get("passage"):
        passages = [dict(raw["passage"], items=raw.get("items") or [])]
    if not isinstance(passages, list) or not passages:
        raise ValueError("passages 가 비어 있다")

    groups = {}                                   # step key → [group]
    skipped = []
    for p in passages:
        label = str(p.get("no") or "").strip() or None
        body = str(p.get("content") or "").strip()
        items = list(p.get("items") or [])
        keys = {it.get("key") for it in items}
        # 1단계 원고에 2단계가 붙어 온 어휘 선택 — 2단계가 따로 없을 때만 갈라 쓴다
        for it in list(items):
            if it.get("key") == "vocab-choice" and "vocab-choice-2" not in keys:
                parts = _split_two_stages(it.get("content") or {})
                if len(parts) == 2:
                    it["content"] = dict(it["content"], text=parts[0])
                    items.append({"key": "vocab-choice-2", "label": "어휘선택 2단계",
                                  "content": dict(it["content"], text=parts[1])})
        for it in items:
            key = str(it.get("key") or "")
            step = _KEY_STEP.get(key)
            units, attach = (None, None)
            if step:
                units, attach = _convert(key, it.get("content"), body)
            if not step or (units is None and attach is None):
                skipped.append(f"{label or '?'}·{it.get('label') or key}")
                continue
            if units:
                groups.setdefault(step, []).append({"label": label, "units": units})
            if attach:
                # 어법 선택 하단(①~⑤) — 같은 지문의 gram_sel 묶음에 붙인다. 없으면 상단 없이 하단만.
                g = next((g for g in groups.get("step2_a1", []) if g["label"] == label), None)
                if g is None:
                    g = {"label": label, "units": []}
                    groups.setdefault("step2_a1", []).append(g)
                g["attach"] = attach

    steps = []
    for key in STEP_ORDER:
        if key in groups and STEP_META[key]["layout"] != "attach":
            steps.append(dict(STEP_META[key], key=key, groups=groups[key]))
    if not steps:
        raise ValueError("지면으로 옮길 수 있는 항목이 없다 — 건너뛴 것: " + ", ".join(skipped))
    if skipped:
        log("[contents] 지면이 없는 항목은 건너뛴다: " + ", ".join(skipped))
    log(f"[contents] 지문 {len(passages)} · 스텝 {len(steps)}: " + " · ".join(s["key"] for s in steps))

    book = {k: v for k, v in (raw.get("book") or {}).items() if k in ("line1", "line2", "title", "brand")}
    return {"book": book, "steps": steps,
            "stats": {"steps": len(steps), "passages": {s["key"]: len(s["groups"]) for s in steps}}}
