# -*- coding: utf-8 -*-
"""contents 분석본(yos-analysis-v1) → 편집기 제작 분석본 틀(units.json)의 원고 — 자리 이름 → 글·꾸밈 조각.

contents 는 분석본마다 **조판 문서**(contents `src/server/analyses/typeset-doc.ts` 의 TypesetDoc — Y.OS design 에 주던 그 모양)를
가공하지 않고 보낸다: {"format": "yos-analysis-v1", "book": {"title"}, "analyses": [TypesetDoc, …]}.
틀은 「원고마다」 묶음 「분석 펼침면」이 레코드 목록을 받는다(레코드 하나 = 분석본 하나 = 펼침면 한 벌).
자리 이름·원고 꼴은 docs/편집기_재현/원고자리_규약.md 「광문 스텝업 분석본 — 자리 표」. 바꾸는 규칙은 여기 한 곳.

    to_content(data, sample) → (content, report)

문장(태깅본 + 역할 마크) → 꾸밈 조각:
    word[TAG]      → 그 낱말 아래 윗주          word[^TAG] → 위 윗주   (꼬리 |dx,dy 는 버린다 — 자리는 틀의 윗주 기본값)
    ⌃(내용)        → 다음 낱말 위 윗주(생략된 말)
    역할 마크 start/end 는 태깅본에서 대괄호 태그만 빼고 센 자리(⌃(…) 는 센다) — contents tagged-serialize.ts 의 약속
    역할 → 틀 브랜드의 문자 스타일(ROLE_CS) · badge → 첫 낱말 위 「서술형★」
    gps(문법 포인트) → 문장 앞 옆 메모(「* …」 문단)
"""
import re

ROLE_CS = {                                                              # contents 역할 → 광문 틀 문자 스타일 (글자색 먼저, 형광 다음 — 조각 cs 차례)
    "grammar": "파랑 글자", "vocab": "빨강 글자", "parallel": "빨강 물결",
    "descriptive": "형광 노랑", "antecedent": "형광 보라", "relative": "형광 보라",
    "connector": "형광 민트", "flow": "형광 민트", "blank": "형광 민트",
}
_ORDER = ["파랑 글자", "빨강 글자", "빨강 물결", "형광 노랑", "형광 보라", "형광 민트"]
BADGE = {"t": "서술형★", "pos": "above", "cs": "서술형"}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _scan(tagged):
    """태깅본 → (보이는 글자 [(글자, 센 자리)], 윗주 [(보이는 자리, 글, 위/아래)], 생략 [(보이는 자리, 글)])"""
    chars, rubies, elided = [], [], []
    i, c, n = 0, 0, len(tagged)
    while i < n:
        ch = tagged[i]
        if ch == "[":
            j = tagged.find("]", i)
            if j > i:
                tag = tagged[i + 1:j]
                up = tag.startswith("^")
                tag = tag.lstrip("^").split("|")[0].strip()
                if tag:
                    rubies.append((len(chars), tag, "above" if up else "below"))
                i = j + 1
                continue
        if tagged.startswith("⌃(", i):
            j = tagged.find(")", i)
            if j > i:
                elided.append((len(chars), tagged[i + 2:j].strip()))
                c += j + 1 - i
                i = j + 1
                if chars and chars[-1][0] == " " and i < n and tagged[i] == " ":   # 낱말 사이 생략 — 빠진 자리 앞뒤 띄어쓰기가 둘이 되지 않게
                    c += 1
                    i += 1
                continue
        chars.append((ch, c))
        c += 1
        i += 1
    return chars, rubies, elided


def _word_before(text, p):
    s = p
    while s > 0 and not text[s - 1].isspace():
        s -= 1
    return s, p


def _word_after(text, p):
    s = p
    while s < len(text) and text[s].isspace():
        s += 1
    e = s
    while e < len(text) and not text[e].isspace():
        e += 1
    return s, e


def sentence_runs(tagged, marks):
    """태깅본 한 줄 + 역할 마크 → 꾸밈 조각 목록(글 · cs · ruby)"""
    chars, rubies, elided = _scan(tagged or "")
    text = "".join(ch for ch, _ in chars)
    offs = [o for _, o in chars]
    roles = [set() for _ in chars]
    badge_at = set()
    for m in marks or []:
        cs = ROLE_CS.get(m.get("role"))
        hit = [k for k, o in enumerate(offs) if m.get("start", 0) <= o < m.get("end", 0)]
        if cs and not (m.get("role") == "parallel" and not hit):
            for k in hit:
                roles[k].add(cs)
        if m.get("badge") and hit:
            k = next((k for k in hit if not text[k].isspace()), hit[0])
            badge_at.add(_word_after(text, k)[0])
    spans = {}                                                           # 낱말 시작 → (끝, 위 윗주, 아래 윗주)

    def put(s, e, ruby, pos):
        if e <= s:
            return
        ent = spans.setdefault(s, [e, [], []])
        ent[0] = max(ent[0], e)
        ent[1 if pos == "above" else 2].append(ruby)
    for p, tag, pos in rubies:
        s, e = _word_before(text, p)
        put(s, e, {"t": tag, "pos": pos}, pos)
    for p, t in elided:
        s, e = _word_after(text, p)
        put(s, e, {"t": t, "pos": "above"}, "above")
    for s in badge_at:
        put(s, _word_after(text, s)[1], dict(BADGE), "above")
    runs, k = [], 0

    def cs_of(rs):
        cs = [x for x in _ORDER if x in rs]
        return cs[0] if len(cs) == 1 else cs
    while k < len(text):
        if k in spans:                                                   # 윗주 달린 낱말 — 한 조각(낱말 안에서 색이 갈려도 낱말 첫 글자 기준)
            e, up, down = spans[k]
            plain = [r["t"] for r in up if r.get("cs") != "서술형"]
            badge = [r for r in up if r.get("cs") == "서술형"]       # 위 자리는 하나 — 서술형★ 이 있으면 그것(생략·지칭 윗주보다 먼저)
            above = badge[:1] or ([{"t": " ".join(plain), "pos": "above"}] if plain else [])
            rb = above + ([{"t": " ".join(r["t"] for r in down), "pos": "below"}] if down else [])
            run = {"t": text[k:e], "ruby": rb[0] if len(rb) == 1 else rb}
            if roles[k]:
                run["cs"] = cs_of(roles[k])
            runs.append(run)
            k = e
            continue
        e = k + 1
        while e < len(text) and e not in spans and roles[e] == roles[k]:
            e += 1
        seg = text[k:e]
        runs.append({"t": seg, "cs": cs_of(roles[k])} if roles[k] else seg)
        k = e
    out = []                                                             # 맨글 이웃끼리 합치기
    for r in runs:
        if isinstance(r, str) and out and isinstance(out[-1], str):
            out[-1] += r
        else:
            out.append(r)
    return out


_U = re.compile(r"<u>(.*?)</u>", re.S)


def _underlined(text):
    """핵심기출 글의 <u>…</u>(밑줄이 곧 문제) → 꾸밈 조각 · 밑줄 없으면 글 그대로"""
    if "<u>" not in (text or ""):
        return text or ""
    out, at = [], 0
    for m in _U.finditer(text):
        if m.start() > at:
            out.append(text[at:m.start()])
        out.append({"t": m.group(1), "cs": "밑줄"})
        at = m.end()
    if at < len(text):
        out.append(text[at:])
    return out


def short_lesson(t):
    """머리 탭의 「강」 칸은 「7강」 크기다 — 길면 칸이 아래로 늘어 본문이 그 칸을 피해 내려간다(2026-10-11 실측).
    「Lesson 1. …」 → 「1과」 · 「7강 …」 → 「7강」 · 그 밖은 첫 낱말 4자까지"""
    m = re.search(r"(?:Lesson|Unit|Chapter)\s*(\d+)", t, re.I)
    if m:
        return f"{int(m.group(1))}과"
    m = re.search(r"(\d+)\s*(강|과|회)", t)
    if m:
        return m.group(1) + m.group(2)
    return (t.split() or [""])[0][:4]


def record(doc):
    """조판 문서 하나 → 「분석 펼침면」 레코드"""
    meta, title = doc.get("meta") or {}, doc.get("title") or {}
    rows = []
    for s in doc.get("sentences") or []:
        runs = [f"{s.get('no')} "] + sentence_runs(s.get("tagged") or "", s.get("marks") or [])
        gps = [g.strip() for g in s.get("gps") or [] if str(g).strip()]
        if gps:
            runs = [{"t": "", "side": "\n".join(("* " + g) if not g.startswith("*") else g for g in gps)}] + runs
        rows.append({"문장": runs, "해석": s.get("ko") or ""})
    src, ko = meta.get("source") or "", title.get("ko") or meta.get("subject") or title.get("en") or ""
    rec = {"강": short_lesson(meta.get("title") or ""), "회차": "분석",
           "지문제목": " · ".join(x for x in (src, ko) if x),
           "문장+해석": rows, "주제": doc.get("topic") or "", "요약": doc.get("summary") or ""}
    kq = doc.get("keyQuestion")
    if kq:
        passage = "\n".join(kq.get("passage") or [])
        choices = "\n".join(f"{CIRCLED[i] if i < len(CIRCLED) else i + 1} {c}" for i, c in enumerate(kq.get("choices") or []))
        rec["발문+문제지문+선지"] = [{"발문": _underlined(kq.get("q") or ""), "문제지문": _underlined(passage), "선지": _underlined(choices)}]
        a = int(kq.get("answerIndex") or 0)
        rec["답"] = f"답: {CIRCLED[a - 1]}" if 0 < a <= len(CIRCLED) else (f"답: {kq['answerText']}" if kq.get("answerText") else "")
    voca = [v for v in doc.get("voca") or [] if v.get("word")]
    if voca:
        rec["어휘"] = "\n".join(f"{v['word']}\t{v.get('ko') or ''}" for v in voca)
    return rec


def to_content(data, sample=None):
    docs = [d for d in (data or {}).get("analyses") or [] if isinstance(d, dict)]
    report = {"sent": [], "skipped": []}
    recs = []
    for i, d in enumerate(docs):
        if (d.get("layoutType") or "base") != "base":
            report["skipped"].append({"passage": i + 1, "label": (d.get("meta") or {}).get("source") or f"{i + 1}번째", "why": "짤지문형(좌면만) 면이 이 틀에 아직 없다"})
            continue
        if not d.get("sentences"):
            report["skipped"].append({"passage": i + 1, "label": (d.get("meta") or {}).get("source") or f"{i + 1}번째", "why": "문장이 없다"})
            continue
        recs.append(record(d))
        report["sent"].append({"passage": i + 1, "label": (d.get("meta") or {}).get("source")})
    return ({"분석 펼침면": recs} if recs else {}), report
