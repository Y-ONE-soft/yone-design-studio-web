"""rich 단락 -> 시험지 문항 IR.

이 원고(학평 선별 모의고사)는 경계가 결정적이다:
    [NN년 N월 고N NN번]   <- 출처 줄이 곧 문항 시작
    NN. 발문                (원 출처의 번호 / [N~M] 묶음 머리 / [3점] 포함)
    지문 1..n               (첫 줄에 원 번호가 붙어 있기도 함)
    선지 1..5               (별도 단락 또는 지문 안 인라인 원문자)

그래서 분류기(휴리스틱)에 경계를 맡기지 않고 출처 줄로 자른다. 분류기는
문항 유형 라벨에만 쓴다. 번호는 1..N 으로 새로 매긴다.
"""
import re

RE_SRC = re.compile(r"^\[(\d{2})년\s*(\d{1,2})월\s*(고\d)\s*(\d+)번\]\s*$")
RE_GROUP_HEAD = re.compile(r"^\s*\[\d+\s*[~\-]\s*\d+\]\s*")
RE_LEAD_NUM = re.compile(r"^\s*\d+\s*[.)]\s*")
RE_SCORE = re.compile(r"\[\s*(\d)\s*점\s*\]")
RE_CIRCLED = re.compile(r"[①-⑤]")          # ①~⑤
RE_CIRCLED_SPLIT = re.compile(r"(?=[①-⑤])")
RE_FOOTNOTE = re.compile(r"(\*+\s*[^*]+?:\s*[^*]+?)(?=\*|$)")
RE_ABC_TAIL = re.compile(r"(?:\(\s*[ABC]\s*\)\s*){2,}$")
# 빈칸: 원고에서 밑줄이 공백으로 붕괴된 자리.
#  (a) 문장 한가운데의 2칸 이상 공백
#  (b) 영문에서 구두점 바로 앞의 공백 ("... included ." <- 빈칸이 1칸으로 붕괴)
RE_BLANK = re.compile(r"(?<=\S)(\s{2,})(?=\S)")
RE_BLANK_PUNCT = re.compile(r"(?<=[A-Za-z,])(\s+)(?=[.,;:?])")
RE_UNDERSCORE_BLANK = re.compile(r"_{2,}")

# 발문 판별: 한국어 지시문이고 물음/지시 어미로 끝난다.
RE_Q_TAIL = re.compile(r"(?:\?|것은|것을|고르시오\.?|쓰시오\.?|하시오\.?|답하시오\.?)\s*$")


def _looks_like_question(text):
    t = RE_SCORE.sub("", text).strip()      # 꼬리의 [3점] 은 판별에서 제외
    if not t or len(t) > 220:
        return False
    ko = sum(1 for ch in t if "가" <= ch <= "힣")
    return ko >= 4 and bool(RE_Q_TAIL.search(t))


def _rstrip_runs(runs):
    """runs 뒤쪽 공백 정리 (빈 run 제거)."""
    out = [dict(r) for r in runs if r["t"]]
    while out and not out[-1]["t"].strip():
        out.pop()
    if out:
        out[-1]["t"] = out[-1]["t"].rstrip()
    while out and not out[0]["t"].strip():
        out.pop(0)
    if out:
        out[0]["t"] = out[0]["t"].lstrip()
    return out


def _strip_prefix_from_runs(runs, pattern):
    """runs 선두에서 정규식 매치분을 떼어낸다 (첫 run 안에서만)."""
    out = [dict(r) for r in runs]
    for r in out:
        if not r["t"].strip():
            continue
        m = pattern.match(r["t"])
        if m:
            r["t"] = r["t"][m.end():]
        break
    return [r for r in out if r["t"]]


def _pull_text(runs):
    return "".join(r["t"] for r in runs)


def _cut_tail(runs, n):
    """runs 전체 텍스트 끝에서 n글자 제거."""
    out = [dict(r) for r in runs]
    while n > 0 and out:
        t = out[-1]["t"]
        if len(t) <= n:
            n -= len(t)
            out.pop()
        else:
            out[-1]["t"] = t[:-n]
            n = 0
    return out


def _extract_footnotes(runs):
    """지문 끝의 '* word: 뜻' 주석을 분리해서 돌려준다."""
    text = _pull_text(runs)
    m = re.search(r"\s(\*+\s*\S.*)$", text)
    if not m:
        return runs, []
    note = m.group(1).strip()
    if len(note) > 220 or ":" not in note:
        return runs, []
    notes = [n.strip() for n in re.split(r"(?=\*\*?\s*\S)", note) if n.strip()]
    return _rstrip_runs(_cut_tail(runs, len(text) - m.start())), notes


def _split_choices(runs):
    """선지 단락 runs -> [{'label','runs'}]  (한 단락에 여러 선지가 붙은 경우 분해)"""
    text = _pull_text(runs)
    if not RE_CIRCLED.search(text):
        return []
    # run 경계를 보존하면서 원문자 위치로 자른다.
    cuts = [m.start() for m in re.finditer(r"[①-⑤]", text)]
    pieces = []
    for i, c in enumerate(cuts):
        end = cuts[i + 1] if i + 1 < len(cuts) else len(text)
        pieces.append((c, end))
    out = []
    for s, e in pieces:
        sub, pos = [], 0
        for r in runs:
            a, b = pos, pos + len(r["t"])
            pos = b
            if b <= s or a >= e:
                continue
            nr = dict(r)
            nr["t"] = r["t"][max(s, a) - a: min(e, b) - a]
            if nr["t"]:
                sub.append(nr)
        sub = _rstrip_runs(sub)
        if not sub:
            continue
        label = sub[0]["t"][0]
        sub[0] = dict(sub[0])
        sub[0]["t"] = sub[0]["t"][1:].lstrip()
        out.append({"label": label, "runs": [r for r in sub if r["t"]]})
    return out


def _mark_blanks(runs):
    """공백/언더스코어로 붕괴된 빈칸을 blank run 으로 승격."""
    out = []
    for r in runs:
        t = r["t"]
        parts, last = [], 0
        for m in (list(RE_UNDERSCORE_BLANK.finditer(t))
                  + list(RE_BLANK.finditer(t))
                  + list(RE_BLANK_PUNCT.finditer(t))):
            parts.append((m.start(), m.end()))
        parts.sort()
        merged = []
        for s, e in parts:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
            else:
                merged.append((s, e))
        for s, e in merged:
            if s > last:
                nr = dict(r); nr["t"] = t[last:s]; out.append(nr)
            nr = dict(r); nr["t"] = ""; nr["blank"] = True
            out.append(nr)
            last = e
        if last < len(t):
            nr = dict(r); nr["t"] = t[last:]; out.append(nr)
    return [r for r in out if r["t"] or r.get("blank")]


def parse(paras, classify=None):
    """rich 단락 목록 -> {'title', 'items':[...], 'warnings':[...]}"""
    texts = [p["text"].strip() for p in paras]
    starts = [i for i, t in enumerate(texts) if RE_SRC.match(t)]
    warnings = []
    title = texts[0] if starts and starts[0] > 0 and texts[0] else ""
    if not starts:
        raise ValueError("출처 줄([NN년 N월 고N NN번])을 찾지 못했다 — 원고 형식 확인 필요")

    bounds = starts + [len(paras)]
    # 발문 결손 블록을 메울 때 쓸 참조표: 원 출처의 문항번호 -> 그 번호를 쓰는
    # 다른 블록의 발문. (직전 문항 승계는 유형이 바뀌는 자리에서 틀린다)
    q_by_num = {}
    for k, a in enumerate(starts):
        nxt = bounds[k + 1]
        blk = [p for p in paras[a + 1:nxt] if p["text"].strip()]
        if not blk:
            continue
        h = _strip_prefix_from_runs(
            _strip_prefix_from_runs(_rstrip_runs(blk[0]["runs"]), RE_GROUP_HEAD),
            RE_LEAD_NUM)
        if _looks_like_question(_pull_text(h)):
            q_by_num.setdefault(RE_SRC.match(texts[a]).group(4), h)

    items = []
    for k in range(len(starts)):
        a, b = bounds[k], bounds[k + 1]
        blk = [p for p in paras[a + 1:b] if p["text"].strip()]
        src = texts[a]
        if not blk:
            warnings.append(f"{src}: 본문 없음")
            continue

        # 발문이 아예 빠진 블록이 있다 (원고 결손). 그때는 직전 문항의 발문을
        # 물려받는다 — 같은 묶음([31~34] 등)에서 떨어져 나온 문항이기 때문.
        head = _rstrip_runs(blk[0]["runs"])
        head = _strip_prefix_from_runs(head, RE_GROUP_HEAD)
        head = _strip_prefix_from_runs(head, RE_LEAD_NUM)
        if _looks_like_question(_pull_text(head)):
            q_runs, rest = head, blk[1:]
        elif items:
            q_runs, rest = [dict(r) for r in items[-1]["question"]], blk
            warnings.append(f"{src}: 발문 단락 없음 — 직전 문항 발문 승계 "
                            f"({_pull_text(q_runs)[:30]}…)")
        else:
            q_runs, rest = head, blk[1:]
            warnings.append(f"{src}: 발문 판별 실패")
        q_text = _pull_text(q_runs)
        # 선지: 뒤에서부터 원문자로 시작하는 연속 단락
        choices, body = [], []
        tail = []
        for p in reversed(rest):
            t = p["text"].strip()
            if t[:1] in "①②③④⑤":
                tail.append(p)
            else:
                break
        tail.reverse()
        body = rest[:len(rest) - len(tail)]
        for p in tail:
            choices.extend(_split_choices(_rstrip_runs(p["runs"])))

        # (A)(B)(C) 헤더 행 (어휘 네모 문항)
        abc_header = False
        passage = []
        for p in body:
            runs = _rstrip_runs(p["runs"])
            if not runs:
                continue
            txt = _pull_text(runs)
            m = RE_ABC_TAIL.search(txt)
            if m:
                abc_header = True
                runs = _rstrip_runs(_cut_tail(runs, len(txt) - m.start()))
            passage.append(runs)

        # 지문 첫 단락 선두의 원 문항 번호 제거
        if passage:
            passage[0] = _strip_prefix_from_runs(passage[0], RE_LEAD_NUM)

        # 배점: 발문 또는 지문 끝의 [3점]
        score = None
        m = RE_SCORE.search(q_text)
        if m:
            score = int(m.group(1))
        for i, runs in enumerate(passage):
            t = _pull_text(runs)
            m2 = RE_SCORE.search(t)
            if m2:
                score = score or int(m2.group(1))
                for r in runs:
                    r["t"] = RE_SCORE.sub("", r["t"])
                passage[i] = _rstrip_runs(runs)
        if score:
            q_runs = [dict(r) for r in q_runs]
            for r in q_runs:
                r["t"] = RE_SCORE.sub("", r["t"])
            q_runs = _rstrip_runs(q_runs)

        # 어휘 주석 분리 (마지막 지문 단락 꼬리)
        notes = []
        if passage:
            passage[-1], notes = _extract_footnotes(passage[-1])
            if not passage[-1]:
                passage.pop()

        passage = [_mark_blanks(r) for r in passage if r]

        q_clean = _pull_text(q_runs)
        code = label = None
        if classify:
            try:
                code, label, _kind = classify(q_clean)
            except Exception:
                pass

        items.append({
            "n": k + 1,
            "src": src,
            "type": code,
            "label": label,
            "question": q_runs,
            "question_text": q_clean,
            "score": score,
            "passage": passage,
            "notes": notes,
            "abc_header": abc_header,
            "choices": choices,
            "inline_choices": not choices and bool(
                RE_CIRCLED.search(" ".join(_pull_text(r) for r in passage))),
        })

    return {"title": title, "items": items, "warnings": warnings}


RE_ANS = re.compile(r"^\[(\d{2}년\s*\d{1,2}월\s*고\d\s*\d+번)\]\s*정답\s*([①-⑤\d\s,]+)")


def parse_answers(paras):
    """정답및해설 원고 -> {출처줄: 정답}"""
    out = {}
    for p in paras:
        m = RE_ANS.match(p["text"].strip())
        if m:
            out["[" + re.sub(r"\s+", " ", m.group(1)) + "]"] = m.group(2).strip()
    return out
