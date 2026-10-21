# -*- coding: utf-8 -*-
"""contents 원고(yos-workbook-v1) → 편집기 제작 틀(units.json)의 원고 — 구성 이름 · 자리 이름 → 글.

contents 는 지문마다 항목(item)을 보낸다: {"no", "content", "items": [{"key", "label", "content": {"kind", …}}]}.
편집기 틀은 「원고마다」 묶음(쪽 이름 = 구성 이름)이 레코드 목록을 받는다: {"A어휘선택": [{"제목", "지문번호": […], "지문": […]}, …]}.
**약속 = 구성 이름 · 자리 이름.** 작업자가 틀을 만들 때 아래 이름으로 구성(묶음 첫 쪽 이름)과 자리를 지으면 그 틀에도 같은 원고가 들어간다.
한 벌에 지문 몇 개·문제 몇 칸인지는 **틀의 자리 수**로 센다(template_caps) — 견본 원고가 없는 틀도 된다.

    to_content(data, sample, caps) → (content, report)   sample = 틀의 견본 원고(구성 제목) · caps = template_caps(묶음)

contents 재료 → 구성 (2026-10-11 짝 확정 — 원본 책 머리 제목 기준, 실제 생성 결과로 칸 맞춤):
    A어휘선택  ← 어휘선택 1단계(vocab-choice, 제목 「… 1」) + 어휘선택 2단계(공통 문제 형식 → 원문에 고르기를 모아 박음, 제목 「… 2」)
                 업로드 원고(form: manuscript — doc 만 있고 text 없음)는 doc 의 문제 본문을 text 로(_doc_text), 2단계는 vocab-choice-2
    A본문OX    ← 내용OX 영어(진술 O/X) — 「일치하지 않는 것」 객관식 칸은 비움
    B내용종합  ← 개별 유형 내용종합(발문 · 선지)
    C문장배열  ← 순서배열 1단계(보기 문장 (A)~) + 개별 유형 삽입 · 순서배열(지문마다 번갈아)
    C빈칸어휘  ← 빈칸어휘 1단계(「1[colder]」 → 「{c}__」)   C빈칸어법 ← 빈칸어법(「1[covering]」 → 「__」)
    A어법선택  ← 어법선택(「1[a / b]」 → 「[a / b]」) — 「어법상 틀린 것」 객관식 지문 칸은 비움
    B어법OX    ← 어법OX(문제마다 「1.  문장」 → 문장 목록) — 보기 예문 칸은 비움
    C영작배열  ← 영작배열 1단계(우리말 · 「( a / b / c )」)
    S실전문제  ← 그 밖의 개별 문제 유형(한 줄기 「지문번호+번호+발문+보기+지문+…」)
    B본문정리  ← (맞는 재료 없음)
그 밖의 재료는 report.skipped 에 남기고 넣지 않는다(없는 것을 지어내지 않는다).
"""
import re
from collections import Counter

_PICK = re.compile(r"(?:\(\d+\)\s*)?❮\s*(.*?)\s*❯")                     # contents 고르기 표시 — 앞의 (번호)는 원본 책에 없다
_BLANK = re.compile(r"(\d+)\[([^\[\]]+)\]")                              # contents 빈칸 표시 n[정답]
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# 개별 문제 유형(contents workbook-items 의 question 묶음) — 실전 문제 면으로. 내용종합은 제 구성(B내용종합)이 있다.
Q_LABELS = {"어휘", "어휘2", "어휘ABC", "영영풀이", "함축의미(영)", "함축의미(한)", "무관한문장", "빈칸추론 구", "빈칸추론 절",
            "추론 한글", "추론 영어", "순서배열", "삽입", "주제", "제목", "요지", "연결사", "문단요약", "어휘종합", "틀린어법"}


def template_caps(pkg):
    """틀 묶음 → {구성 이름: Counter(자리: 한 벌의 칸 수)} — 「원고마다」 묶음은 첫 쪽 이름으로 쪽들을 모아, 한 번 나오는 쪽은 제 이름으로"""
    pages = {p["id"]: p for p in pkg.get("pages") or []}
    parts = {p["id"]: p for p in pkg.get("parts") or []}

    def binds(pg):
        out = []
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            if a.get("bind"):
                out.append(a["bind"])
            out += [x["bind"] for x in (parts.get(it.get("part")) or {}).get("atoms") or [] if x.get("bind")]
        return [b for b in out if not b.startswith("sys.")]
    caps, run = {}, None
    for s in (pkg.get("plan") or {}).get("sections") or []:
        for e in s.get("pages") or []:
            e = e if isinstance(e, dict) else {"page": e, "repeat": "once"}
            pg = pages.get(e["page"]) or {}
            nm = pg.get("name") or ""
            if e.get("repeat") == "each_set":
                if not re.fullmatch(r"빈 면 \d+", nm):
                    run = caps.setdefault(nm, Counter())
                if run is not None:
                    run.update(binds(pg))
            else:
                run = None
                caps.setdefault(nm, Counter()).update(binds(pg))
    return caps


def _circ(i):
    return _CIRCLED[i] if i < len(_CIRCLED) else f"({i + 1})"


def _u(t):
    """contents 밑줄 표시 <u>…</u> → 틀의 밑줄 약속 {…} (GREP 「표시 감추기 + 밑줄」)"""
    return re.sub(r"<u>(.*?)</u>", r"{\1}", str(t or ""), flags=re.S)


def _choices(cs):
    """선지 — 앞에 ①~ 를 단다. 선지 글이 이미 원문자로 시작하면(무관한 문장 「①」) 그대로"""
    return "\n".join(_u(c) if str(c).lstrip()[:1] in _CIRCLED else f"{_circ(i)} {_u(c)}" for i, c in enumerate(cs or []))


def _prompt(q):
    """발문 — 묶음 머리(「[1~2] 다음 글을 읽고 …」)와 앞 번호(「1.」)는 뗀다(번호는 문제번호 자리가 단다). 문제의 보기 글은 아래 줄로"""
    lines = [ln for ln in str(q.get("prompt") or "").split("\n") if not re.match(r"^\s*\[\d+\s*[~∼-]\s*\d+\]", ln)]
    t = re.sub(r"^\s*\d+\s*[.)]\s*", "", "\n".join(lines).strip())
    return _u(t + ("\n" + q["passage"].strip() if q.get("passage") else ""))


def _chunks(seq, n):
    n = max(1, int(n or 1))
    return [seq[k:k + n] for k in range(0, len(seq), n)]


def _title(sample, name):
    rec = (sample.get(name) or [{}])[0]
    return (rec or {}).get("제목") or name


def _qs(c):
    return (c or {}).get("questions") or []


def _pick(text):
    return _PICK.sub(lambda m: "[ " + re.sub(r"\s*/\s*", " / ", m.group(1)) + " ]", text or "").strip()


# ── 구성마다 바꾸기: 지문 목록 [(번호, 원문, {재료: 내용})] → 레코드 목록 ─────────

def _merge_picks(text, qs):
    """공통 문제 형식으로 쪼개 온 고르기(문제마다 문장 하나 + 「(n)❮ … ❯」 하나) → 원문 한 덩어리에 모두 박는다(어휘선택 2단계).
    문제의 문장에서 표시 앞뒤 글로 원문 자리를 찾고, 못 찾은 것은 넣지 않는다."""
    hits = []
    for q in qs:
        s = str(q.get("passage") or "")
        m = _PICK.search(s)
        if not m:
            continue
        pre, suf = s[:m.start()], s[m.end():]
        i = text.find(pre) if pre else 0
        if i < 0:
            continue
        a = i + len(pre)
        tail = suf[:40]
        b = text.find(tail, a) if tail else len(text)
        if b < 0 or b - a > 60:
            continue
        hits.append((a, b, m.group(0)))
    out, k = [], 0
    for a, b, mk in sorted(hits):
        if a < k:
            continue
        out.append(text[k:a] + mk)
        k = b
    return "".join(out) + text[k:]


def _a_vocab(ps, sample, cap):
    """A어휘선택 — 1단계 벌들 다음에 2단계 벌들(원본 책 순서). 같은 구성, 제목만 「… 1」 / 「… 2」"""
    per = cap.get("지문") or cap.get("지문번호") or 4
    t1 = _title(sample, "A어휘선택")
    t2 = re.sub(r"1\s*$", "2", t1) if re.search(r"1\s*$", t1) else t1 + " 2"
    one = [(no, _pick((g["vocab-choice"] or {}).get("text"))) for no, _, g in ps if g.get("vocab-choice")]
    # 2단계 — 업로드 원고(vocab-choice-2)는 이미 원문에 고르기가 박혀 있고, AI 생성은 문제마다 쪼개 와서 원문에 모아 박는다
    two = [(no, _pick((g.get("vocab-choice-2") or {}).get("text") or _merge_picks(text or "", _qs(g.get("q:어휘선택 2단계")))))
           for no, text, g in ps if g.get("vocab-choice-2") or g.get("q:어휘선택 2단계")]
    return [{"제목": t, "지문번호": [str(no) for no, _ in ch], "지문": [x for _, x in ch]}
            for t, rows in ((t1, one), (t2, two)) for ch in _chunks(rows, per)]


def _a_ox(ps, sample, cap):
    """A본문OX — 지문마다 [객관식(일치하지 않는 것) · O/X] 두 문제 칸. contents 내용OX 영어는 O/X 진술만 → 객관식 칸은 비워 접는다"""
    key = _flow_key(cap, "진술")
    if key:                                                              # 흐름 틀(2026-10-14) — 지문마다 한 줄기: 지문 · O/X 문제(번호 · 발문) · 진술마다 번호 · 글
        per = cap.get("지문번호") or cap.get(key) or 2
        recs = []
        for ch in _chunks(ps, per):
            r = {"제목": _title(sample, "A본문OX"), "지문번호": [], key: []}
            for no, text, g in ch:
                qs = _qs(g.get("q:내용OX 영어"))
                items = [[["지문", text or ""]]]
                if qs:
                    items.append([["문제번호", "01"], ["발문", _frags(_u(qs[0].get("prompt")))]])
                items += [[["진술번호", f"{i:02d}"], ["진술", _frags(_u(q.get("passage") or ""))]] for i, q in enumerate(qs, 1)]
                r["지문번호"].append(str(no))
                r[key].append(items)
            recs.append(r)
        return recs
    per = cap.get("지문번호") or 2
    qn = max(1, (cap.get("문제번호") or 2 * per) // per)
    sn = max(1, (cap.get("진술") or 5 * per) // per)
    cn = max(0, (cap.get("선지") or per) // per)
    recs = []
    for ch in _chunks(ps, per):
        r = {"제목": _title(sample, "A본문OX"), "지문번호": [], "지문": [], "문제번호": [], "발문": [], "선지": [], "진술번호": [], "진술": []}
        for no, text, g in ch:
            qs = _qs(g.get("q:내용OX 영어"))
            r["지문번호"].append(str(no))
            r["지문"].append(text or "")
            r["문제번호"] += [""] * (qn - 1) + ["01"]
            r["발문"] += [""] * (qn - 1) + [_u(qs[0].get("prompt") if qs else "")]
            r["선지"] += [""] * cn
            st = [_u(q.get("passage") or "") for q in qs][:sn]
            r["진술번호"] += [f"{i + 1:02d}" if i < len(st) else "" for i in range(sn)]
            r["진술"] += st + [""] * (sn - len(st))
        recs.append(r)
    return recs


def _flow_key(cap, need):
    """그 구성의 흐름 자리(인디자인 스토리 — 여러 자리 한 줄기) 가운데 need 자리가 든 것"""
    return next((k for k in cap if "+" in k and need in k.split("+")), None)


def _put(r, key, cap, items):
    """한 지문의 [자리, 값] 들을 레코드에 — 흐름 자리(key)에 든 것은 그 줄기로(빈 값은 문단이 안 생긴다),
    아닌 것은 따로 선 텍스트 프레임의 자리로(인디자인: 위 프레임은 원고만큼, 아래 문제 프레임은 제자리)"""
    names = key.split("+")
    grp = [x for x in items if x[0] in names and x[1]]
    r.setdefault(key, []).append([grp] if grp else [])
    for f, v in items:
        if f not in names and f in cap:
            r.setdefault(f, []).append(v)


def _frags(t):
    """밑줄 약속 {…}(_u) → 꾸밈 조각(문자 스타일 「밑줄」) — 흐름 자리는 표시를 감추는 GREP 대신 조각으로 받는다(인디자인 태그 텍스트처럼).
    표시가 없으면 글 그대로"""
    s = str(t or "")
    if "{" not in s:
        return s
    out, k = [], 0
    for m in re.finditer(r"\{([^{}]*)\}", s):
        if m.start() > k:
            out.append(s[k:m.start()])
        out.append({"t": m.group(1), "cs": "밑줄"})
        k = m.end()
    if k < len(s):
        out.append(s[k:])
    return out


def _b_summary(ps, sample, cap):
    key = _flow_key(cap, "발문")
    if key:                                                              # 흐름 틀(2026-10-14) — 지문마다 한 줄기: 지문 · 문제마다 번호 · 발문 · 선지(없는 문제는 안 보낸다)
        per = cap.get("지문번호") or cap.get(key) or 2
        recs = []
        for ch in _chunks(ps, per):
            r = {"제목": _title(sample, "B내용종합"), "지문번호": [], key: []}
            for no, text, g in ch:
                items = [[["지문", text or ""]]]
                for i, q in enumerate(_qs(g.get("q:내용종합")), 1):
                    items.append([["문제번호", f"{i:02d}"], ["발문", _frags(_prompt(q))], ["선지", _frags(_choices(q.get("choices")))]])
                r["지문번호"].append(str(no))
                r[key].append(items)
            recs.append(r)
        return recs
    per = cap.get("지문번호") or 2
    qn = max(1, (cap.get("문제번호") or per) // per)                     # 지문 하나에 문제 칸 수
    recs = []
    for ch in _chunks(ps, per):
        r = {"제목": _title(sample, "B내용종합"), "지문번호": [], "지문": [], "문제번호": [], "발문": [], "선지": []}
        for no, text, g in ch:
            qs = _qs(g.get("q:내용종합"))[:qn]
            r["지문번호"].append(str(no))
            r["지문"].append(text or "")
            for i in range(qn):                                          # 모자란 칸은 비워 접는다 — 다음 지문 문제가 앞 지문 칸으로 밀리지 않게
                q = qs[i] if i < len(qs) else None
                r["문제번호"].append(f"{i + 1:02d}" if q else "")
                r["발문"].append(_prompt(q) if q else "")
                r["선지"].append(_choices(q.get("choices")) if q else "")
        recs.append(r)
    return recs


def _split_insert(q):
    """삽입 문제 → (발문, 주어진 문장, 지문) — 「[주어진 문장 …]\\n문장\\n\\n… ( ① ) …」"""
    s = str(q.get("passage") or "")
    head, _, body = s.partition("\n\n")
    given = re.sub(r"^\s*\[[^\]]*\]\s*", "", head).strip()
    return _u(q.get("prompt") or ""), _u(given), _u(body.strip())


def _split_order(q):
    """순서 문제 → (발문, 주어진 글, (A)~ 글) — 「주어진 글\\n\\n(A) …」"""
    s = str(q.get("passage") or "")
    i = s.find("(A)")
    return _u(q.get("prompt") or ""), _u(s[:i].strip() if i > 0 else ""), _u(s[i:].strip() if i >= 0 else s)


def _c_order(ps, sample, cap):
    """C문장배열 — 지문마다 보기 문장 목록(순서배열 1단계 (A)~) + 문제 하나. 문제는 지문마다 삽입 → 순서 번갈아(원본 책),
    그 지문에 한쪽만 있으면 있는 것으로"""
    key = _flow_key(cap, "주어진문장")
    per = cap.get("지문번호") or (cap.get(key) if key else None) or 2
    recs = []
    for ch in _chunks(ps, per):
        if key:                                                          # 흐름 틀(2026-10-14) — 지문마다 한 줄기: 보기 문장 · 발문 · 주어진 문장 · 지문
            r = {"제목": _title(sample, "C문장배열"), "지문번호": [], key: []}
            for k, (no, text, g) in enumerate(ch):
                opts = (g.get("sentence-order") or {}).get("options") or []
                ins, order = _qs(g.get("q:삽입")), _qs(g.get("q:순서배열"))
                want = (ins, _split_insert) if k % 2 == 0 else (order, _split_order)
                other = (order, _split_order) if k % 2 == 0 else (ins, _split_insert)
                qs, split = want if want[0] else other
                prompt, given, body = split(qs[0]) if qs else ("", "", "")
                it = [["보기문장", "\n".join(f"({o.get('tag')}) {o.get('text') or ''}" for o in opts)], ["발문", _frags(prompt)],
                      ["주어진문장", _frags(given)], ["지문", _frags(body)]]
                r["지문번호"].append(str(no))
                _put(r, key, cap, it)
            recs.append(r)
            continue
        r = {"제목": _title(sample, "C문장배열"), "지문번호": [], "보기문장": [], "발문": [], "주어진문장": [], "지문": []}
        for k, (no, text, g) in enumerate(ch):
            opts = (g.get("sentence-order") or {}).get("options") or []
            ins, order = _qs(g.get("q:삽입")), _qs(g.get("q:순서배열"))
            want = (ins, _split_insert) if k % 2 == 0 else (order, _split_order)
            other = (order, _split_order) if k % 2 == 0 else (ins, _split_insert)
            qs, split = want if want[0] else other
            prompt, given, body = split(qs[0]) if qs else ("", "", "")
            r["지문번호"].append(str(no))
            r["보기문장"].append("\n".join(f"({o.get('tag')}) {o.get('text') or ''}" for o in opts))
            r["발문"].append(prompt)
            r["주어진문장"].append(given)
            r["지문"].append(body)
        recs.append(r)
    return recs


def _blank_rows(c, hint):
    """빈칸 문항 — 「n[정답]」 → 빈칸 「__」(템플릿의 GREP 스타일이 문자 스타일 「빈칸」을 입힌다), 힌트는 꾸밈 조각(문자 스타일 「첫 글자」)"""
    rows = []
    for i, r in enumerate(c.get("rows") or [], 1):
        hints = {int(b.get("no")): (b.get("hint") or (b.get("answer") or "")[:1]) for b in r.get("blanks") or [] if b.get("no") is not None}
        en, out, k = r.get("en") or "", [], 0
        for m in _BLANK.finditer(en):
            out.append(en[k:m.start()])
            if hint:
                out.append({"t": hints.get(int(m.group(1))) or m.group(2)[:1], "cs": "첫 글자"})
            out.append("__")
            k = m.end()
        out.append(en[k:])
        runs = []
        for x in out:                                                    # 잇닿은 글은 하나로
            if isinstance(x, str) and runs and isinstance(runs[-1], str):
                runs[-1] += x
            elif x != "":
                runs.append(x)
        rows.append({"문항번호": f"{i:02d}.", "빈칸문장": runs[0] if len(runs) == 1 and isinstance(runs[0], str) else runs, "해석": r.get("ko") or ""})
    return rows


def _c_blank(name, src, hint):
    def conv(ps, sample, cap):
        key = next((k for k in cap if "빈칸문장" in k), "문항번호+빈칸문장+해석")
        per = cap.get("지문번호") or cap.get(key) or 2
        return [{"제목": _title(sample, name), "지문번호": [str(no) for no, _, _ in ch], key: [_blank_rows(g[src], hint) for _, _, g in ch]}
                for ch in _chunks(ps, per)]
    return conv


def _a_grammar(ps, sample, cap):
    """A어법선택 — 지문마다 [고르기 지문 · 「어법상 틀린 것」 객관식 지문] 두 칸 + 객관식 발문. contents 어법선택은 고르기만 → 객관식 칸은 비워 접는다.
    「1[a / b]」 → 「[a / b]」(번호는 원본 책에 없다)"""
    key = _flow_key(cap, "문제지문")
    if key:                                                              # 흐름 틀(2026-10-14) — 지문마다 한 줄기: 고르기 지문 · 어법수정(객관식 발문 · 밑줄 지문, 있을 때만)
        per = cap.get("지문번호") or cap.get(key) or 2
        recs = []
        for ch in _chunks(ps, per):
            r = {"제목": _title(sample, "A어법선택"), "지문번호": []}
            for no, _, g in ch:
                fix = g.get("어법수정") or {}
                r["지문번호"].append(str(no))
                _put(r, key, cap, [["지문", re.sub(r"(?<![A-Za-z])\d+\[([^\[\]]+)\]", r"[\1]", (g.get("grammar-choice") or {}).get("text") or "")],
                                   ["발문", PROMPT["어법수정"] if fix.get("passage") else ""], ["문제지문", _frags(_u(fix.get("passage")))]])
            recs.append(r)
        return recs
    per = cap.get("지문번호") or 2
    tn = max(1, (cap.get("지문") or 2 * per) // per)
    pn = max(0, (cap.get("발문") or per) // per)
    recs = []
    for ch in _chunks(ps, per):
        r = {"제목": _title(sample, "A어법선택"), "지문번호": [], "지문": [], "발문": []}
        for no, _, g in ch:
            t = re.sub(r"(?<![A-Za-z])\d+\[([^\[\]]+)\]", r"[\1]", (g.get("grammar-choice") or {}).get("text") or "")
            fix = g.get("어법수정") or {}
            r["지문번호"].append(str(no))
            r["지문"] += ([t, _u(fix.get("passage"))] + [""] * max(0, tn - 2))[:tn] if tn > 1 else [t]
            r["발문"] += ([PROMPT["어법수정"] if fix.get("passage") else ""] + [""] * pn)[:pn]
        recs.append(r)
    return recs


def _b_grammar_ox(ps, sample, cap):
    """B어법OX — 지문마다 보기(예문) 칸 + 문장 목록. contents 어법OX 의 문제마다 「1.  문장」 → 문장번호 · 문장"""
    key = _flow_key(cap, "문장")
    if key:                                                              # 흐름 틀(2026-10-14) — 지문마다 한 줄기: 문장마다 번호 · 글(보기 예문은 없다)
        per = cap.get("지문번호") or cap.get(key) or 2
        recs = []
        for ch in _chunks(ps, per):
            r = {"제목": _title(sample, "B어법OX"), "지문번호": [], key: []}
            for no, _, g in ch:
                st = [re.sub(r"^\s*\d+\s*[.)]\s*", "", _u(q.get("passage") or "")).strip() for q in _qs(g.get("q:어법OX"))]
                r["지문번호"].append(str(no))
                r[key].append([[["문장번호", f"{i:02d}."], ["문장", _frags(t)]] for i, t in enumerate(st, 1)])
            recs.append(r)
        return recs
    per = cap.get("지문번호") or 2
    sn = max(1, (cap.get("문장") or 13 * per) // per)
    bn = max(0, (cap.get("보기") or per) // per)
    recs = []
    for ch in _chunks(ps, per):
        r = {"제목": _title(sample, "B어법OX"), "보기": [], "지문번호": [], "문장번호": [], "문장": []}
        for no, _, g in ch:
            st = [re.sub(r"^\s*\d+\s*[.)]\s*", "", _u(q.get("passage") or "")).strip() for q in _qs(g.get("q:어법OX"))][:sn]
            r["보기"] += [""] * bn
            r["지문번호"].append(str(no))
            r["문장번호"] += [f"{i + 1:02d}." if i < len(st) else "" for i in range(sn)]
            r["문장"] += st + [""] * (sn - len(st))
        recs.append(r)
    return recs


def _writing_items(g):
    """영작배열 문항 [(우리말, 보기)] — 영작배열 1단계(조각 목록)와 원고 꼴 영작배열(낱말 · 서술형 — 보기 글 그대로)"""
    out = [(it.get("ko") or "", "( " + " / ".join(it.get("chunks") or []) + " )") for it in (g.get("writing-order") or {}).get("items") or []]
    return out + [(it.get("ko") or "", it.get("words") or "") for it in (g.get("영작배열") or {}).get("items") or []]


def _c_writing(ps, sample, cap):
    key = _flow_key(cap, "보기단어")
    if key:                                                              # 흐름 틀(2026-10-14) — 쪽마다 한 줄기: 지문이 바뀌면 지문 번호 · 문항마다 번호 · 우리말 · 낱말
        page = 5                                                         # 쪽당 문항(견본 원고에서 — 없으면 원본 책 5)
        smp = (sample.get("C영작배열") or [{}])[0].get(key) if isinstance(sample.get("C영작배열"), list) else None
        if smp:
            page = max(sum(1 for it in pg if it and it[0][0] == "문항번호") for pg in smp) or page
        rows = []
        for no, _, g in ps:
            for i, (ko, words) in enumerate(_writing_items(g)):
                rows.append((str(no) if i == 0 else "", [["문항번호", f"{i + 1:02d}."], ["우리말", ko], ["보기단어", words]]))
        pages = []
        for ch in _chunks(rows, page):
            out = []
            for pno, item in ch:
                if pno:
                    out.append([["지문번호", pno]])
                out.append(item)
            pages.append(out)
        n = cap.get(key) or 2                                            # 한 벌(펼침면)의 쪽 수
        return [{"제목": _title(sample, "C영작배열"), key: pages[k:k + n]} for k in range(0, len(pages), n)]
    rows = []
    for no, _, g in ps:
        for i, (ko, words) in enumerate(_writing_items(g)):
            rows.append({"지문번호": str(no) if i == 0 else "", "문항번호": f"{i + 1:02d}.", "우리말": ko, "보기단어": words})
    per = cap.get("문항번호") or cap.get("우리말") or 10
    return [dict({"제목": _title(sample, "C영작배열")}, **{k: [r[k] for r in ch] for k in ("지문번호", "문항번호", "우리말", "보기단어")})
            for ch in _chunks(rows, per)]


def _s_exam(ps):
    """실전 문제 한 줄기 — 지문마다 머리(지문번호 · 지문) + 그 지문의 문제들(번호 · 발문 · 보기 · 선지)"""
    out = []
    for no, text, qs in ps:
        out.append([["지문번호", str(no)], ["지문", "다음 글을 읽고 물음에 답하시오.\n" + (text or "")]])
        for i, q in enumerate(qs, 1):
            rec = [["번호", f"{i:02d}"], ["발문", _frags(_u(str(q.get("prompt") or "").strip()))]]
            if q.get("passage"):
                rec.append(["보기", _frags(_u(q["passage"].strip()))])
            rec.append(["선지", _frags(_choices(q.get("choices")))])
            out.append(rec)
    return out


# 원고에 발문이 없는 문제 — 원본 책(스텝바이스텝)의 발문
PROMPT = {
    "본문OX": "다음 글의 내용과 일치하면 O, 일치하지 않으면 X를 고르시오.",
    "삽입": "아래 주어진 문장이 들어갈 곳으로 적당한 곳을 고르시오.",
    "순서배열": "아래 주어진 문장 다음에 이어질 문장들의 적절한 순서를 쓰시오.",
    "어법수정": "다음 밑줄 친 부분 중 어법상 틀린 것은?",
}


def _b_outline(ps, sample, cap):
    """B본문정리 — 지문마다 [지문 · 주제 두 줄 · 제목 두 줄](본문정리) + 객관식 하나(주제 · 제목 — 지문마다 번갈아, 한쪽만 있으면 그것)"""
    k1, k2 = _flow_key(cap, "주제"), _flow_key(cap, "선지")
    if not k1 or not k2:
        return []
    per = cap.get("지문번호") or cap.get(k1) or 2
    recs = []
    for ch in _chunks(ps, per):
        r = {"제목": _title(sample, "B본문정리"), "지문번호": []}
        for k, (no, text, g) in enumerate(ch):
            o = g.get("본문정리") or {}
            want, other = (g.get("주제"), g.get("제목")) if k % 2 == 0 else (g.get("제목"), g.get("주제"))
            q = want or other or {}
            r["지문번호"].append(str(no))
            _put(r, k1, cap, [["지문", o.get("passage") or text or ""], ["주제", "\n".join(o.get("topics") or [])],
                              ["글제목", "\n".join(o.get("titles") or [])]])
            _put(r, k2, cap, [["발문", _u(q.get("prompt"))], ["문제지문", _frags(_u(q.get("passage")))], ["주석", q.get("notes") or ""],
                              ["선지", _frags(_choices(q.get("choices")))]])
        recs.append(r)
    return recs


MS_FORM = "wb-manuscript"                                                # contents 컴포넌트 원고 꼴(src/server/studio/manuscript.ts)
OUTLINE, ORDER_WRITTEN, GRAMMAR_FIX = "cq-b54cc606", "cq-a793218f", "cq-df5aa646"     # contents 관리자 컴포넌트 key
WRITING = {"cq-5361e6bd", "cq-dc819941"}                                 # 영작배열(낱말) · 영작배열(서술형)


def _from_ms(c, caps):
    """컴포넌트 원고 꼴(AI 로 만들든 업로드든 같은 꼴) → [(받는 재료, 내용)] — 구성 함수들이 읽는 꼴로"""
    comp = c.get("component")
    if comp in ("vocab-choice", "vocab-choice-2", "grammar-choice"):
        return [(comp, {"text": c.get("passage") or ""})]
    if comp in ("vocab-blank", "grammar-blank"):
        return [(comp, {"rows": c.get("rows") or []})]
    if comp == "content-ox-en":
        return [("q:내용OX 영어", {"questions": [{"prompt": PROMPT["본문OX"], "passage": s.get("text") or ""} for s in c.get("statements") or []]})]
    if comp == OUTLINE:
        return [("본문정리", c)]
    if comp in ("q-topic", "q-title"):
        name = "주제" if comp == "q-topic" else "제목"
        if "B본문정리" in caps:
            return [(name, c)]
        return [(f"q:{name}", {"questions": [{"prompt": c.get("prompt"), "passage": c.get("passage"), "choices": c.get("choices") or []}]})]
    if comp == "content-summary":
        return [("q:내용종합", {"questions": [{"prompt": q.get("prompt"), "choices": q.get("choices") or []} for q in c.get("questions") or []]})]
    if comp == "sentence-order":
        return [("sentence-order", {"options": c.get("sentences") or []})]
    if comp == ORDER_WRITTEN:
        body = "\n".join(f"({x.get('tag')}) {x.get('text') or ''}" for x in c.get("paragraphs") or [])
        return [("q:순서배열", {"questions": [{"prompt": PROMPT["순서배열"], "passage": f"{c.get('given') or ''}\n\n{body}"}]})]
    if comp == "q-insert":
        return [("q:삽입", {"questions": [{"prompt": PROMPT["삽입"], "passage": f"{c.get('given') or ''}\n\n{c.get('passage') or ''}"}]})]
    if comp == GRAMMAR_FIX:
        return [("어법수정", c)]
    if comp == "grammar-ox":
        return [("q:어법OX", {"questions": [{"passage": x.get("text") or ""} for x in c.get("sentences") or []]})]
    if comp in WRITING:
        return [("영작배열", {"items": c.get("items") or []})]
    return []


# 구성 → (받는 재료, 바꾸기). 재료 = 원고 꼴(kind), 공통 문제 형식이면 「q:<재료 이름>」
GROUPS = {
    "A어휘선택": ({"vocab-choice", "vocab-choice-2", "q:어휘선택 2단계"}, _a_vocab),
    "A본문OX": ({"q:내용OX 영어"}, _a_ox),
    "B내용종합": ({"q:내용종합"}, _b_summary),
    "C문장배열": ({"sentence-order", "q:순서배열", "q:삽입"}, _c_order),
    "C빈칸어휘": ({"vocab-blank"}, _c_blank("C빈칸어휘", "vocab-blank", True)),
    "A어법선택": ({"grammar-choice", "어법수정"}, _a_grammar),
    "B어법OX": ({"q:어법OX"}, _b_grammar_ox),
    "C빈칸어법": ({"grammar-blank"}, _c_blank("C빈칸어법", "grammar-blank", False)),
    "C영작배열": ({"writing-order", "영작배열"}, _c_writing),
    "B본문정리": ({"본문정리", "주제", "제목"}, _b_outline),
}


def _src(it):
    c = it.get("content") or {}
    kind = c.get("kind") or it.get("key")
    return f"q:{it.get('label')}" if kind == "mock-exam" else kind


def _doc_text(c):
    """원고 그대로 올린 판본(form: manuscript — 원본 문단을 doc 에 담고 text 가 없다) → 문제 쪽 본문 글.
    번호 머리 문단(「[21]」)은 뺀다(번호는 지문번호 자리가 단다). text 가 있으면 그것을 쓴다"""
    if c.get("form") != "manuscript" or c.get("text"):
        return c
    paras = [p for p in ((c.get("doc") or {}).get("problem") or []) if p.get("type", "p") == "p" and p.get("style") != "Heading_num"]
    text = "\n".join(t for t in ("".join(r.get("t") or "" for r in p.get("runs") or []).strip() for p in paras) if t)
    return dict(c, text=text)


def to_content(data, sample=None, caps=None, start=1):
    """start = 첫 지문의 번호(이 책 안 차례) — 원고를 덩어리로 나눠 바꿀 때(order: data) 덩어리 사이 번호가 이어지게"""
    sample, caps = sample or {}, caps or {}
    story = next((k for nm, c in caps.items() if nm.startswith("S") for k in c if "발문" in k and "+" in k), None)   # 실전 문제 한 줄기 자리
    used = {s for name, (srcs, _) in GROUPS.items() if name in caps for s in srcs}
    groups, exam, report = {}, [], {"sent": [], "skipped": []}
    for seq, p in enumerate((data or {}).get("passages") or [], start):
        num = str(seq)                                                    # 지문 번호 = 이 책 안 차례(1부터) — 모의고사 원래 번호(36 등)는 쓰지 않는다
        got, qs = {}, []
        for it in p.get("items") or []:
            label = it.get("label")
            if (it.get("content") or {}).get("form") == MS_FORM:              # 컴포넌트 원고 꼴(2026-10-20) — AI · 업로드 같은 꼴
                pairs = _from_ms(it["content"], caps)
                took = False
                for s, c in pairs:
                    if s in used:
                        if s == "영작배열" and s in got:                         # 영작배열(낱말) · (서술형)을 한 구성에 이어서
                            c = {"items": got[s]["items"] + c["items"]}
                        got[s], took = c, True
                    elif story and s.startswith("q:"):
                        qs += _qs(c)
                        took = True
                if took:
                    report["sent"].append({"passage": p.get("no"), "key": it.get("key"), "label": label})
                else:
                    report["skipped"].append({"passage": p.get("no"), "key": it.get("key"), "label": label, "why": "이 틀에 아직 자리 없음"})
                continue
            s = _src(it)
            c = _doc_text(it.get("content") or {})
            if s in used:
                got[s] = c
            elif story and s.startswith("q:") and (c.get("group") == "question" or label in Q_LABELS):
                qs += _qs(c)
            else:
                report["skipped"].append({"passage": p.get("no"), "key": it.get("key"), "label": label, "why": "이 틀에 아직 자리 없음"})
                continue
            report["sent"].append({"passage": p.get("no"), "key": it.get("key"), "label": label})
        for name, (srcs, _) in GROUPS.items():
            if name in caps and srcs & set(got):
                groups.setdefault(name, []).append((num, p.get("content"), got))
        if qs:
            exam.append((num, p.get("content"), qs))
    if not groups and not exam:
        return {}, report
    # 책 머리글 자리(차례 면의 교재명 · 단원명 — 면마다 하나씩) — 교재명 = contents 책 이름(「26년 6월 고1모의고사」), 그 밖은 비운다(견본 글을 남기지 않는다)
    bk = (data or {}).get("book") or {}
    book = " ".join(x for x in (bk.get("line2"), bk.get("line1")) if x) or bk.get("title") or ""
    content = {}
    for k, v in sample.items():
        if k in GROUPS or k == story or not (isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v))):
            continue
        val = book if k == "교재명" else ""
        content[k] = val if isinstance(v, str) else [val] * len(v)
    for name, ps in groups.items():
        content[name] = GROUPS[name][1](ps, sample, caps.get(name) or Counter())
    if exam:
        content[story] = _s_exam(exam)
    return content, report
