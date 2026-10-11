# -*- coding: utf-8 -*-
"""contents 분석본(yos-analysis-v1) ⇄ 편집기 제작 분석본 틀(units.json)의 원고 — 자리 이름 → 글·꾸밈 조각, 그리고 되돌리기.

contents 는 분석본마다 **조판 문서**(contents `src/server/analyses/typeset-doc.ts` 의 TypesetDoc — Y.OS design 에 주던 그 모양)를
가공하지 않고 보낸다: {"format": "yos-analysis-v1", "book": {"title"}, "analyses": [TypesetDoc, …]}.
틀은 「원고마다」 묶음 「분석 펼침면」이 레코드 목록을 받는다(레코드 하나 = 분석본 하나 = 펼침면 한 벌).
자리 이름·원고 꼴은 docs/편집기_재현/원고자리_규약.md 「광문 스텝업 분석본 — 자리 표」. 바꾸는 규칙은 여기 한 곳.

    to_content(data, sample) → (content, report)        조판 문서들 → 틀 원고
    to_doc(rec, base) → (doc, changed)                   지면에서 고친 레코드 → 조판 문서(base = 보냈던 원래 문서)

문장(태깅본 + 역할 마크) → 꾸밈 조각:
    word[TAG]      → 그 낱말 아래 윗주          word[^TAG] → 위 윗주   (꼬리 |dx,dy 는 화면에선 버리고 되돌릴 때 살린다)
    ⌃(내용)        → 다음 낱말 위 윗주(생략된 말)          refs 「it = the brain」 → 그 낱말 위 윗주(지칭어)
    역할 마크 start/end 는 태깅본에서 대괄호 태그만 빼고 센 자리(⌃(…) 는 센다) — contents tagged-serialize.ts 의 약속
    역할 → 틀 브랜드의 문자 스타일(ROLE_CS) · badge → 첫 낱말 위 「서술형★」
    gps(문법 포인트) → 문장 앞 옆 메모(「* …」 문단)

되돌리기(지면 위 고치기 → contents): 조각에 원래 정체를 남긴다 — 아래 윗주 `raw`(원래 태그들), 위 윗주 `src`(태그·생략·지칭어),
조각 `rl`(원래 역할 — 민트 하나가 연결사·빈칸 둘을 뜻하므로). 편집기는 조각의 이런 칸을 지킨다(units_canvas rtKeys).
안 고친 문장(문장마다 `_h` 지문이 그대로)은 원래 태깅본·마크를 그대로 돌려주고, 고친 문장만 지면에서 다시 짓는다.
"""
import copy
import hashlib
import json
import re

ROLE_CS = {                                                              # contents 역할 → 광문 틀 문자 스타일 (글자색 먼저, 형광 다음 — 조각 cs 차례)
    "grammar": "파랑 글자", "vocab": "빨강 글자", "parallel": "빨강 물결",
    "descriptive": "형광 노랑", "antecedent": "형광 보라", "relative": "형광 보라",
    "connector": "형광 민트", "flow": "형광 민트", "blank": "형광 민트",
}
CS_ROLE = {"파랑 글자": "grammar", "빨강 글자": "vocab", "빨강 물결": "parallel",   # 되돌릴 때 원래 역할을 모르면(새로 칠함) 대표 역할
           "형광 노랑": "descriptive", "형광 보라": "antecedent", "형광 민트": "connector"}
_ORDER = ["파랑 글자", "빨강 글자", "빨강 물결", "형광 노랑", "형광 보라", "형광 민트"]
BADGE = {"t": "서술형★", "pos": "above", "cs": "서술형"}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_PUNCT = re.compile(r"^[\W_]+|[\W_]+$")


def _off(raw):
    return raw.split("|")[0].strip()


def _scan(tagged):
    """태깅본 → (보이는 글자 [(글자, 센 자리)], 윗주 [(보이는 자리, 원래 태그, 글, 위/아래)], 생략 [(보이는 자리, 글)])"""
    chars, rubies, elided = [], [], []
    i, c, n = 0, 0, len(tagged)
    while i < n:
        ch = tagged[i]
        if ch == "[":
            j = tagged.find("]", i)
            if j > i:
                raw = tagged[i + 1:j]
                up = raw.startswith("^")
                tag = _off(raw.lstrip("^"))
                if tag:
                    rubies.append((len(chars), raw, tag, "above" if up else "below"))
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


def _refs(refs):
    """「※ it = the brain」 → [(낱말 소문자, 원래 값)] — = 없는 것은 버린다(Y.OS design adapter 와 같이)"""
    out = []
    for r in refs or []:
        w, sep, v = str(r).lstrip("※ ").partition("=")
        if sep and w.strip() and v.strip():
            out.append((w.strip().lower(), v.strip()))
    return out


def norm_runs(runs):
    """조각 정리 — 편집기(units_canvas rtNorm)와 같은 규칙: 빈 글 빼고, 꾸밈이 같은 이웃은 잇고, 꾸밈 없는 조각은 그냥 글"""
    out = []
    for r in runs or []:
        r = {"t": r} if isinstance(r, str) else dict(r)
        if r.get("side") is None and not r.get("t"):
            continue
        p = out[-1] if out else None
        keys = lambda x: json.dumps({k: v for k, v in x.items() if k != "t"}, ensure_ascii=False, sort_keys=True)
        if p is not None and p.get("side") is None and r.get("side") is None and keys(p) == keys(r):
            p["t"] += r["t"]
        else:
            out.append(r)
    return [r["t"] if (r.get("side") is None and list(r) == ["t"]) else r for r in out]


def _hash(runs):
    return hashlib.sha1(json.dumps(norm_runs(runs), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def sentence_runs(tagged, marks, refs=None):
    """태깅본 한 줄 + 역할 마크 (+ 지칭어) → 꾸밈 조각 목록(글 · cs · ruby · 되돌리기 칸)"""
    chars, rubies, elided = _scan(tagged or "")
    text = "".join(ch for ch, _ in chars)
    offs = [o for _, o in chars]
    roles = [set() for _ in chars]
    badge_at = set()
    for m in marks or []:
        hit = [k for k, o in enumerate(offs) if m.get("start", 0) <= o < m.get("end", 0)]
        if m.get("role") in ROLE_CS:
            for k in hit:
                roles[k].add(m["role"])
        if m.get("badge") and hit:
            k = next((k for k in hit if not text[k].isspace()), hit[0])
            badge_at.add(_word_after(text, k)[0])
    spans = {}                                                           # 낱말 시작 → [끝, 위 조각들, 아래 조각들]

    def put(s, e, part, pos):
        if e <= s:
            return
        ent = spans.setdefault(s, [e, [], []])
        ent[0] = max(ent[0], e)
        ent[1 if pos == "above" else 2].append(part)
    for p, raw, tag, pos in rubies:
        s, e = _word_before(text, p)
        put(s, e, {"k": "up", "raw": raw, "t": tag} if pos == "above" else {"raw": raw, "t": tag}, pos)
    for p, t in elided:
        s, e = _word_after(text, p)
        put(s, e, {"k": "elide", "t": t}, "above")
    refs = _refs(refs)
    if refs:                                                             # 지칭어 — 위 태그([^…])가 없는 낱말에만, 같은 낱말 모두에(Y.OS design 과 같이)
        k = 0
        while k < len(text):
            s, e = _word_after(text, k)
            if s >= len(text):
                break
            w = _PUNCT.sub("", text[s:e]).lower()
            has_up = any(x.get("k") == "up" for x in (spans.get(s) or [0, [], []])[1])
            hit = next(((rw, rv) for rw, rv in refs if w and w == rw), None)   # 한 낱말에 하나 — 같은 지칭어가 대소문자만 달리 둘 든 원고가 있다
            if hit and not has_up:
                put(s, e, {"k": "ref", "w": hit[0], "v": hit[1], "t": _off(hit[1])}, "above")
            k = e
    for s in badge_at:
        put(s, _word_after(text, s)[1], dict(BADGE), "above")

    def cs_of(rs):
        cs = [x for x in _ORDER if x in {ROLE_CS[r] for r in rs}]
        return cs[0] if len(cs) == 1 else cs

    def styled(seg, rs):
        if not rs:
            return {"t": seg}
        return {"t": seg, "cs": cs_of(rs), "rl": sorted(rs)}
    runs, k = [], 0
    while k < len(text):
        if k in spans:                                                   # 윗주 달린 낱말 — 한 조각(낱말 안에서 색이 갈려도 낱말 첫 글자 기준)
            e, up, down = spans[k]
            badge = [r for r in up if r.get("cs") == "서술형"]
            parts = [r for r in up if r.get("cs") != "서술형"]
            rb = []
            if badge:                                                    # 위 자리는 하나 — 서술형★ 이 있으면 그것(다른 위 윗주는 되돌리기 칸에만)
                rb.append(dict(BADGE, **({"src": parts} if parts else {})))
            elif parts:
                parts.sort(key=lambda r: {"elide": 0, "ref": 1, "up": 2}[r["k"]])
                rb.append({"t": " ".join(r["t"] for r in parts), "pos": "above", "src": parts})
            if down:
                rb.append({"t": " ".join(r["t"] for r in down), "pos": "below", "raw": [r["raw"] for r in down]})
            run = styled(text[k:e], roles[k])
            run["ruby"] = rb[0] if len(rb) == 1 else rb
            runs.append(run)
            k = e
            continue
        e = k + 1
        while e < len(text) and e not in spans and roles[e] == roles[k]:
            e += 1
        runs.append(styled(text[k:e], roles[k]))
        k = e
    return norm_runs(runs)


def runs_sentence(runs):
    """꾸밈 조각(지면에서 고친 문장) → (태깅본, 역할 마크, 문법 포인트, 지칭어) — sentence_runs 의 반대.
    번호(맨 앞 「3 」)와 옆 메모는 문장 밖으로 뗀다. 원래 정체 칸(raw · src · rl)이 글과 맞으면 그대로 살리고, 고친 곳은 새로 짓는다."""
    gps, body = [], []
    for r in runs or []:
        r = {"t": r} if isinstance(r, str) else dict(r)
        if r.get("side") is not None:
            gps += [re.sub(r"^\*\s?", "", ln).strip() for ln in str(r["side"]).split("\n") if ln.strip()]
            continue
        body.append(r)
    lead = ""                                                            # 맨 앞 번호 떼기 — 꾸밈 없는 앞 글들에서
    while body and set(body[0]) == {"t"} and len(lead) < 6:
        lead += body.pop(0)["t"]
    m = re.match(r"\s*\d+\s", lead)
    if m:
        lead = lead[m.end():]
    if lead:
        body.insert(0, {"t": lead})
    tagged, cnt, roles, badges, refs = "", 0, [], [], []

    def emit(s, rs=None):
        nonlocal tagged, cnt
        tagged += s
        roles.extend([set(rs or ())] * len(s))
        cnt += len(s)
    for r in body:
        t = r.get("t") or ""
        rbs = r.get("ruby")
        rbs = rbs if isinstance(rbs, list) else ([rbs] if isinstance(rbs, dict) else [])
        above = [x for x in rbs if x.get("pos") != "below"]
        below = [x for x in rbs if x.get("pos") == "below"]
        cs = r.get("cs") or []
        cs = [cs] if isinstance(cs, str) else list(cs)
        rl = set(r.get("rl") or [])
        if not rl or sorted({ROLE_CS[x] for x in rl if x in ROLE_CS}, key=_ORDER.index) != [c for c in _ORDER if c in cs]:
            rl = {CS_ROLE[c] for c in cs if c in CS_ROLE}                # 원래 역할과 색이 다르면(새로 칠함) 색의 대표 역할
        parts, up_text, badge = [], None, False
        for a in above:
            if a.get("cs") == "서술형":
                badge = True
                parts += a.get("src") or []
            elif a.get("src") and a.get("t", "") == " ".join(x["t"] for x in a["src"]):
                parts += a["src"]                                        # 안 고친 위 윗주 — 원래 정체대로
            elif (a.get("t") or "").strip():
                up_text = a["t"].strip()                                 # 고쳤거나 새로 단 위 윗주 → 위 태그
        for x in parts:
            if x.get("k") == "elide":
                emit(f"⌃({x['t']}) ")
        if badge:
            badges.append(cnt)                                           # 딱지 자리 = 낱말 첫 글자(앞의 생략 표기 뒤)
        emit(t, rl)
        for b in below:
            if b.get("raw") and b.get("t", "") == " ".join(_off(x) for x in b["raw"]):
                tagged += "".join(f"[{x}]" for x in b["raw"])
            elif (b.get("t") or "").strip():
                tagged += f"[{b['t'].strip()}]"
        for x in parts:
            if x.get("k") == "up":
                tagged += f"[{x['raw']}]"
            elif x.get("k") == "ref":
                ref = f"{x['w']} = {x['v']}"
                if ref not in refs:
                    refs.append(ref)
        if up_text:
            tagged += f"[^{up_text}]"
    marks = []
    for role in ROLE_CS:
        k = 0
        while k < len(roles):
            if role in roles[k]:
                e = k
                while e < len(roles) and role in roles[e]:
                    e += 1
                marks.append({"start": k, "end": e, "role": role})
                k = e
            else:
                k += 1
    for b in badges:
        m = next((m for m in marks if m["role"] == "descriptive" and m["start"] <= b < m["end"]), None)
        if m:
            m["badge"] = True
    marks.sort(key=lambda m: (m["start"], m["end"], m["role"]))
    return tagged, marks, gps, refs


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


def _plain_u(v):
    """꾸밈 조각 → 글 — 「밑줄」 조각은 <u>…</u> 로(핵심기출의 밑줄 표기)"""
    if isinstance(v, str):
        return v
    out = ""
    for r in v or []:
        if isinstance(r, str):
            out += r
        elif r.get("side") is None:
            cs = r.get("cs") or []
            out += f"<u>{r.get('t', '')}</u>" if "밑줄" in ([cs] if isinstance(cs, str) else cs) else r.get("t", "")
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


def _key_fields(kq):
    passage = "\n".join(kq.get("passage") or [])
    choices = "\n".join(f"{CIRCLED[i] if i < len(CIRCLED) else i + 1} {c}" for i, c in enumerate(kq.get("choices") or []))
    a = int(kq.get("answerIndex") or 0)
    ans = f"답: {CIRCLED[a - 1]}" if 0 < a <= len(CIRCLED) else (f"답: {kq['answerText']}" if kq.get("answerText") else "")
    return [{"발문": _underlined(kq.get("q") or ""), "문제지문": _underlined(passage), "선지": _underlined(choices)}], ans


def record(doc):
    """조판 문서 하나 → 「분석 펼침면」 레코드"""
    meta, title = doc.get("meta") or {}, doc.get("title") or {}
    rows = []
    for s in doc.get("sentences") or []:
        runs = [f"{s.get('no')} "] + sentence_runs(s.get("tagged") or "", s.get("marks") or [], s.get("refs"))
        gps = [g.strip() for g in s.get("gps") or [] if str(g).strip()]
        if gps:
            runs = [{"t": "", "side": "\n".join(("* " + g) if not g.startswith("*") else g for g in gps)}] + runs
        runs = norm_runs(runs)
        rows.append({"문장": runs, "해석": s.get("ko") or "", "_h": _hash(runs)})
    src, ko = meta.get("source") or "", title.get("ko") or meta.get("subject") or title.get("en") or ""
    rec = {"강": short_lesson(meta.get("title") or ""), "회차": "분석",
           "지문제목": " · ".join(x for x in (src, ko) if x),
           "문장+해석": rows, "주제": doc.get("topic") or "", "요약": doc.get("summary") or ""}
    kq = doc.get("keyQuestion")
    if kq:
        rec["발문+문제지문+선지"], rec["답"] = _key_fields(kq)
    voca = [v for v in doc.get("voca") or [] if v.get("word")]
    if voca:
        rec["어휘"] = "\n".join(f"{v['word']}\t{v.get('ko') or ''}" for v in voca)
    return rec


def _ref_words(runs):
    """지면에 걸린 지칭어 낱말들 — 위 윗주의 원래 정체(src)에서"""
    out = set()
    for r in runs or []:
        rbs = r.get("ruby") if isinstance(r, dict) else None
        for x in (rbs if isinstance(rbs, list) else [rbs] if rbs else []):
            out |= {p["w"] for p in x.get("src") or [] if p.get("k") == "ref"}
    return out


def _text(v):
    if isinstance(v, str):
        return v
    return "".join(r if isinstance(r, str) else (r.get("t") or "") for r in v or [] if isinstance(r, str) or r.get("side") is None)


def to_doc(rec, base):
    """지면에서 고친 「분석 펼침면」 레코드 → 조판 문서. base = 보냈던 원래 문서(지면에 없는 칸 — 쪽번호·머리글·그림·기출 포인트 … 은 그대로).
    → (문서, 고친 칸 이름 목록)"""
    doc, changed = copy.deepcopy(base), []
    rows = rec.get("문장+해석") or []
    sents = doc.get("sentences") or []
    for i, s in enumerate(sents):
        if i >= len(rows):
            break
        row = rows[i]
        runs = norm_runs(row.get("문장") or [])
        if _hash(runs) != row.get("_h"):                                # 지문이 다르다 — 고쳤거나 편집기가 조각을 달리 나눴다
            tagged, marks, gps, refs = runs_sentence(runs)
            shown = _ref_words(sentence_runs(s.get("tagged") or "", s.get("marks") or [], s.get("refs")))
            now = {(w, v) for w, v in _refs(refs)}
            orig = [r for r in s.get("refs") or [] if _refs([r])]         # 원래 지칭어 글은 그대로 — 지면에 안 걸렸던 것(낱말이 없거나 위 태그가 있음)도
            refs = [r for r in orig if _refs([r])[0] in now or _refs([r])[0][0] not in shown] + \
                [r for r in refs if _refs([r])[0] not in {_refs([o])[0] for o in orig}]
            same = gps == [g.strip() for g in s.get("gps") or [] if str(g).strip()] and \
                _hash(sentence_runs(tagged, marks, refs)) == _hash(sentence_runs(s.get("tagged") or "", s.get("marks") or [], s.get("refs")))
            if not same:                                                 # 보이는 것이 같으면 원래 태깅본·마크를 그대로 둔다
                s.update(tagged=tagged, marks=marks, gps=gps, refs=refs)
                changed.append(f"문장 {s.get('no')}")
        ko = _text(row.get("해석"))
        if ko != (s.get("ko") or ""):
            s["ko"] = ko
            changed.append(f"해석 {s.get('no')}")
    for f, k in (("주제", "topic"), ("요약", "summary")):
        if f in rec and _text(rec[f]) != (doc.get(k) or ""):
            doc[k] = _text(rec[f])
            changed.append(f)
    kq = doc.get("keyQuestion")
    if kq and "발문+문제지문+선지" in rec:
        was, ans = _key_fields(kq)
        now = (rec.get("발문+문제지문+선지") or [{}])[0]
        if _plain_u(now.get("발문")) != _plain_u(was[0]["발문"]) or _plain_u(now.get("문제지문")) != _plain_u(was[0]["문제지문"]) \
                or _plain_u(now.get("선지")) != _plain_u(was[0]["선지"]):
            kq["q"] = _plain_u(now.get("발문"))
            kq["passage"] = [p for p in _plain_u(now.get("문제지문")).split("\n") if p.strip()]
            kq["choices"] = [re.sub(r"^\s*[①-⑩]\s?", "", c) for c in _plain_u(now.get("선지")).split("\n") if c.strip()]
            changed.append("핵심기출")
        a = _text(rec.get("답") or "")
        if a != ans:
            m = re.search(r"[①-⑩]", a)
            if m:
                kq["answerIndex"], _ = CIRCLED.index(m.group(0)) + 1, kq.pop("answerText", None)
            else:
                kq["answerIndex"], kq["answerText"] = 0, re.sub(r"^\s*답\s*:\s*", "", a).strip()
            changed.append("답")
    if "어휘" in rec:
        old = {v.get("word"): v for v in doc.get("voca") or []}
        was = "\n".join(f"{v['word']}\t{v.get('ko') or ''}" for v in doc.get("voca") or [] if v.get("word"))
        now = _text(rec["어휘"])
        if now != was:
            voca = []
            for ln in now.split("\n"):
                w, _, ko = ln.partition("\t")
                if w.strip():
                    v = dict(old.get(w.strip()) or {"word": w.strip(), "ko": "", "sent": "", "tone": "", "antonym": "", "synonym": ""})
                    v["ko"] = ko.strip()
                    voca.append(v)
            doc["voca"] = voca
            changed.append("어휘")
    return doc, changed


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
