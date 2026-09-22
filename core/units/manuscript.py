"""원고 파서 — 붙여넣은 글 · docx/hwpx · contents JSON(yos-workbook-v1) → 세트 목록.

세트 = {kind, id, blocks: [{block, fields}]} — 블록의 **자리 이름(fields)** 에 값을 맞춘다.
블록 정의(라이브러리 blocks)를 보고 맞추므로 블록을 새로 만들어도 이름만 맞으면 된다.

붙여넣은 글 규칙 (한 줄 = 한 단락, 빈 줄은 무시)
  # 21  ·  [21]  ·  21.        새 세트 (번호). 종류는 기본 passage — `# 21 어법` 처럼 뒤에 종류를 붙일 수 있다
  지문: …  /  passage: …       '이름:' 로 시작하면 그 자리 — 이름은 블록 id·블록 이름·자리 이름·자리 라벨 어느 것이든
  ① … ② …                     선지 (한 줄에 여럿이든 줄마다든)
  답: ③  /  정답: O            바로 앞 블록의 answer (O/X 자리면 참/거짓)
  (1) …  /  1. …               번호 줄 → 줄 블록. 어느 줄 블록인지는 위에 블록 이름만 한 줄(예 `빈칸`, `어법 O/X`) 써 두면 그것.
                               안 써 두면: 빈칸(___·[ ]) 있으면 빈칸 줄, 아니면 첫 번호 줄 블록
  영어 긴 단락 (첫)             지문
  한글 물음 (…? · 고르시오)      발문 (번호는 이어서)
  그 밖                         바로 앞 글 자리에 이어 붙인다 (단락 추가)

contents JSON 은 `core/sources/yos_workbook.py` 의 항목 key 를 여기 블록으로 맞춘다 — 지문마다 (항목 key = 세트 kind) 한 세트.
없는 것은 지어내지 않는다 — 못 맞춘 줄·항목은 log 에 남긴다.
"""
import re

from core.units.render import rich_plain

_CIRC = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
_RE_SET = re.compile(r"^(?:#\s*(\S+)|\[(\S+)\]|(\d+)\.?)\s*(\S.*)?$")
_RE_LABEL = re.compile(r"^([A-Za-z_][\w ]{0,30}|[가-힣][가-힣 /·]{0,20})\s*[:：]\s*(.*)$", re.S)
_RE_CIRC = re.compile(r"[" + _CIRC + r"]")
_RE_ANSWER = re.compile(r"^(?:정답|답|answer)\s*[:：]?\s*(.+)$", re.I)
_RE_NUM = re.compile(r"^\(?(\d{1,3})[).]\s*(.+)$", re.S)
_RE_BLANK = re.compile(r"_{3,}|\[\s*\]|\(\s*\)")
_RE_SQUARE = re.compile(r"(?<![A-Za-z])(\d+)\[([^\[\]]+)\]")
_RE_ANGLE = re.compile(r"\((\d+)\)\s*❮\s*([^❯]*?)\s*❯")               # (1)❮ ⓐ a / ⓑ b ❯ → (1)[ ⓐ a / ⓑ b ]


# ── 블록 정의에서 자리 찾기 ─────────────────────────────────────────────

class Blocks:
    """라이브러리 블록 → 이름으로 자리 찾기."""

    def __init__(self, blocks):
        self.by_id = {b["id"]: b for b in blocks or [] if b.get("source", "content") == "content"}
        self.names = {}                                   # 소문자 이름 → (block_id, field or None)
        for b in self.by_id.values():
            self.names[b["id"].lower()] = (b["id"], None)
            if b.get("name"):
                self.names[b["name"].lower()] = (b["id"], None)
            for f, d in (b.get("fields") or {}).items():
                self.names.setdefault(f.lower(), (b["id"], f))
                if (d or {}).get("label"):
                    self.names.setdefault(d["label"].lower(), (b["id"], f))

    def fields(self, bid):
        return (self.by_id.get(bid) or {}).get("fields") or {}

    def ftype(self, bid, f):
        return ((self.fields(bid).get(f) or {}).get("type")) or "text"

    def main_field(self, bid):
        """블록의 으뜸 글 자리 — rich > text > choices > 첫 자리."""
        fs = self.fields(bid)
        for want in ("rich", "text", "choices"):
            for f, d in fs.items():
                if (d or {}).get("type", "text") == want:
                    return f
        return next(iter(fs), None)

    def with_type(self, ftype):
        return [b for b in self.by_id.values() if any((d or {}).get("type") == ftype for d in (b.get("fields") or {}).values())]

    def with_field(self, name):
        return [b for b in self.by_id.values() if name in (b.get("fields") or {})]

    ALIAS = {"지문": "passage", "본문": "passage", "발문": "prompt", "물음": "prompt", "선지": "choices", "보기": "choices", "번호": "pnum"}

    def lookup(self, name):
        """이름 → (블록, 자리). 정확히 없으면 별칭, 그다음 앞글자 일치(가장 짧은 이름) — `빈칸` → `빈칸 줄`."""
        key = re.sub(r"\s*(줄|블록|상자)$", "", (name or "").strip().lower())
        if not key:
            return None
        hit = self.names.get(key) or self.names.get((name or "").strip().lower())
        if hit:
            return hit
        al = self.ALIAS.get(key)
        if al and al in self.by_id:
            return (al, None)
        if al and al in self.names:
            return self.names[al]
        cands = [n for n in self.names if n.startswith(key) or key.startswith(n)]
        if not cands:
            return None
        return self.names[min(cands, key=len)]

    @property
    def passage(self):
        b = self.by_id.get("passage") or next(iter(b for b in self.by_id.values() if b.get("family") == "B1"), None)
        return b["id"] if b else None

    @property
    def prompt(self):
        b = self.by_id.get("prompt") or next(iter(self.with_field("prompt")), None)
        return b["id"] if b else None

    @property
    def choices(self):
        b = self.by_id.get("choices") or next(iter(self.with_type("choices")), None)
        return b["id"] if b else None

    @property
    def pnum(self):
        b = self.by_id.get("pnum") or next(iter(self.with_field("pnum")), None)
        return b["id"] if b else None

    def rows(self):
        """번호 줄 블록들 (no + sentence)."""
        return [b["id"] for b in self.by_id.values() if "no" in (b.get("fields") or {}) and "sentence" in (b.get("fields") or {})]

    @property
    def blank(self):
        b = self.by_id.get("blank") or next(iter(b for b in self.by_id.values() if "kr" in (b.get("fields") or {})), None)
        return b["id"] if b else None

    @property
    def ox(self):
        b = self.by_id.get("ox") or next(iter(b for b in self.by_id.values() if (b.get("fields") or {}).get("answer", {}).get("type") == "bool"), None)
        return b["id"] if b else None

    @property
    def gram_ox(self):
        b = self.by_id.get("gram_ox")
        return b["id"] if b else (self.rows() or [None])[0]


def coerce(v, ftype):
    """값 → 자리 형식."""
    if ftype == "number":
        s = rich_plain(v).strip()
        return int(s) if s.isdigit() else s
    if ftype == "bool":
        if isinstance(v, bool):
            return v
        s = rich_plain(v).strip().upper()
        return s in ("O", "T", "TRUE", "참", "1", "YES", "Y", "✓")
    if ftype == "choices":
        if isinstance(v, list) and v and not isinstance(v[0], dict):
            return [rich_plain(x).strip() for x in v]
        s = rich_plain(v)
        parts = [p.strip() for p in _RE_CIRC.split(s)] if _RE_CIRC.search(s) else [p.strip() for p in s.split("|")]
        return [p for p in parts if p]
    if ftype == "answer":
        return rich_plain(v).strip()
    return v


def _is_english(s):
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if ord(c) < 0x250) / len(letters) > 0.8


def _is_korean(s):
    return any("가" <= c <= "힣" for c in s)


def _join(a, b):
    """두 값을 단락으로 잇는다 (문자열 / 서식 조각 목록)."""
    if isinstance(a, str) and isinstance(b, str):
        return a + "\n" + b
    la = a if isinstance(a, list) else [a]
    lb = b if isinstance(b, list) else [b]
    return la + ["\n"] + lb


# ── 붙여넣은 글 / docx 단락 → 세트 ─────────────────────────────────────

def from_paragraphs(paras, blocks, kind="passage", log=None):
    """단락 목록(문자열 또는 서식 조각 목록) → 세트 목록."""
    B = blocks if isinstance(blocks, Blocks) else Blocks(blocks)
    log = log if log is not None else []
    sets = []
    cur = None                       # 지금 세트
    last = None                      # 마지막으로 값을 넣은 (블록 dict, 자리)
    row_block = None                 # 번호 줄이 갈 블록 (머리글로 정한 것)
    counters = {}

    def new_set(sid, k=None):
        nonlocal cur, last, row_block
        cur = {"kind": k or kind, "id": str(sid), "blocks": []}
        sets.append(cur)
        last = None
        row_block = None
        counters.clear()
        if B.pnum:
            add(B.pnum, {"pnum": str(sid)})

    def add(bid, fields):
        nonlocal last
        if cur is None:
            new_set(len(sets) + 1)
        fs = {}
        for f, v in fields.items():
            fs[f] = coerce(v, B.ftype(bid, f))
        blk = {"block": bid, "fields": fs}
        cur["blocks"].append(blk)
        last = blk
        return blk

    def next_no(bid):
        counters[bid] = counters.get(bid, 0) + 1
        return counters[bid]

    for raw in paras:
        plain = rich_plain(raw).strip()
        if not plain:
            continue
        val = raw if isinstance(raw, list) else plain
        # 새 세트
        m = _RE_SET.match(plain)
        if m and (m.group(1) or m.group(2) or (m.group(3) and not m.group(4))) and len(plain) < 40:
            sid = m.group(1) or m.group(2) or m.group(3)
            rest = (m.group(4) or "").strip()
            k = None
            if rest:
                hit = B.lookup(rest)
                k = rest if not hit else None
            new_set(sid, k)
            continue
        # 블록 이름만 한 줄 → 이어지는 번호 줄이 갈 블록
        hit = B.lookup(plain)
        if hit and hit[1] is None and len(plain) < 30:
            row_block = hit[0]
            continue
        # 정답
        m = _RE_ANSWER.match(plain)
        if m and last is not None:
            ans = next((f for f, d in B.fields(last["block"]).items() if (d or {}).get("type") in ("answer", "bool")), None)
            if ans:
                last["fields"][ans] = coerce(m.group(1).strip(), B.ftype(last["block"], ans))
                continue
        # 이름: 값
        m = _RE_LABEL.match(plain) if not _RE_CIRC.match(plain) else None
        hit = B.lookup(m.group(1)) if m else None
        if hit:
            bid, f = hit
            f = f or B.main_field(bid)
            body = m.group(2).strip()
            if isinstance(val, list):
                # 서식 조각에서 라벨 부분을 뗀다
                head = plain[: len(plain) - len(body)]
                body = _strip_prefix(val, len(head))
            fields = {f: body}
            if "no" in B.fields(bid) and f != "no":
                fields["no"] = next_no(bid)
            add(bid, fields)
            continue
        # 선지 ①~
        if _RE_CIRC.search(plain) and (plain[0] in _CIRC or (last and last["block"] == B.choices)):
            items = coerce(plain, "choices")
            if last is not None and last["block"] == B.choices and "choices" in last["fields"] and plain[0] in _CIRC and _RE_CIRC.search(plain[1:]) is None:
                last["fields"]["choices"] = list(last["fields"]["choices"]) + items      # 줄마다 하나씩
            elif B.choices:
                add(B.choices, {"choices": items})
            else:
                log.append(f"선지 블록 없음: {plain[:30]}")
            continue
        # 번호 줄 (1) … / 1. …
        m = _RE_NUM.match(plain)
        if m and not _is_korean(m.group(2)[:2]):
            no, body = m.group(1), m.group(2).strip()
            bid = row_block or (B.blank if _RE_BLANK.search(body) and B.blank else None) or (B.rows() or [None])[0]
            if bid:
                fields = {"no": no, "sentence": _strip_prefix(val, len(plain) - len(body)) if isinstance(val, list) else body}
                add(bid, fields)
                continue
        # 한글 물음 → 발문 (앞 번호는 no 로)
        if _is_korean(plain) and (plain.endswith("?") or "고르시오" in plain or "쓰시오" in plain) and B.prompt:
            mn = _RE_NUM.match(plain)
            fields = {"prompt": mn.group(2).strip() if mn else plain}
            if "no" in B.fields(B.prompt):
                fields["no"] = mn.group(1) if mn else next_no(B.prompt)
            add(B.prompt, fields)
            continue
        # 영어 긴 단락 → 지문 (세트에 아직 없으면)
        if _is_english(plain) and len(plain) >= 40 and B.passage and (cur is None or not any(b["block"] == B.passage for b in cur["blocks"])):
            add(B.passage, {B.main_field(B.passage): val})
            continue
        # 한글 한 줄이 번호 줄(빈칸) 바로 뒤 → 해석
        if last is not None and _is_korean(plain) and "kr" in B.fields(last["block"]) and not last["fields"].get("kr"):
            mn = _RE_NUM.match(plain)
            last["fields"]["kr"] = mn.group(2).strip() if mn else plain
            continue
        # 그 밖 → 앞 글 자리에 이어 붙인다
        if last is not None:
            f = next((f for f, d in B.fields(last["block"]).items() if (d or {}).get("type") in ("rich", "text") and f in last["fields"]), None)
            if f:
                last["fields"][f] = _join(last["fields"][f], val)
                continue
        log.append(f"못 맞춘 줄: {plain[:40]}")
    return [s for s in sets if len(s["blocks"]) > (1 if B.pnum else 0)], log


def _strip_prefix(val, n):
    """서식 조각 목록의 앞 n 글자를 뗀다."""
    out = []
    for frag in val:
        t = frag if isinstance(frag, str) else str(frag.get("t", ""))
        if n >= len(t):
            n -= len(t)
            continue
        cut = t[n:]
        n = 0
        out.append(cut if isinstance(frag, str) else dict(frag, t=cut))
    while out and isinstance(out[0], str) and not out[0].strip():
        out.pop(0)
    if out and isinstance(out[0], str):
        out[0] = out[0].lstrip()
    elif out and isinstance(out[0], dict):
        out[0]["t"] = out[0]["t"].lstrip()
    return out


def from_text(text, blocks, kind="passage"):
    return from_paragraphs((text or "").splitlines(), blocks, kind)


def _runs_to_rich(runs):
    out = []
    for r in runs or []:
        t = r.get("t") or ""
        if not t:
            continue
        if r.get("ul"):
            out.append({"t": t, "u": True})
        elif out and isinstance(out[-1], str):
            out[-1] += t
        else:
            out.append(t)
    return out if any(isinstance(x, dict) for x in out) else "".join(out)


def from_file(path, blocks, kind="passage"):
    """docx / hwpx / txt → 세트. 밑줄은 서식 조각 {t, u} 로 남긴다."""
    from core.extract import extractors as ex
    low = path.lower()
    if low.endswith(".docx"):
        paras = ex._docx_extract_paragraphs(path, extract_underline=True)
    elif low.endswith(".hwpx"):
        paras = ex._hwpx_extract_paragraphs(path, extract_underline=True)
    else:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return from_text(fh.read(), blocks, kind)
    return from_paragraphs([_runs_to_rich(p.get("runs")) or p.get("text", "") for p in paras], blocks, kind)


# ── contents JSON (yos-workbook-v1) → 세트 ────────────────────────────────

def _blank_sentence(en, blanks):
    """`n[o ]` 힌트 표시 → `o_____` (힌트 글자 + 밑줄). 정답은 따로."""
    hints = {b.get("no"): (b.get("hint") or "").strip() for b in blanks or []}
    answers = {b.get("no"): (b.get("answer") or "").strip() for b in blanks or []}

    def rep(m):
        no = int(m.group(1))
        hint = hints.get(no) or m.group(2).strip()
        n = max(4, len(answers.get(no) or "") - len(hint))
        return hint + "_" * n
    return _RE_SQUARE.sub(rep, en or "")


def from_contents(raw, blocks, log=None):
    """yos-workbook-v1 → 세트 목록. 지문 하나 = 항목(key)마다 한 세트 (kind = key, id = 지문 번호)."""
    B = blocks if isinstance(blocks, Blocks) else Blocks(blocks)
    log = log if log is not None else []
    if (raw or {}).get("format") != "yos-workbook-v1":
        raise ValueError(f"모르는 형식: {(raw or {}).get('format')} (기대 yos-workbook-v1)")
    passages = raw.get("passages") or ([dict(raw["passage"], items=raw.get("items") or [])] if raw.get("passage") else [])
    sets = []
    for p in passages:
        no = str(p.get("no") or "").strip() or str(len(sets) + 1)
        body = str(p.get("content") or "").strip()

        def head(kind):
            s = {"kind": kind, "id": no if kind == "passage" else f"{no}.{kind}", "blocks": []}      # id 는 유일해야 한다
            if B.pnum:
                s["blocks"].append({"block": B.pnum, "fields": {"pnum": no}})
            return s

        def passage_block(text):
            return {"block": B.passage, "fields": {B.main_field(B.passage): text}} if B.passage and text else None

        base = head("passage")
        pb = passage_block(body)
        if pb:
            base["blocks"].append(pb)
        mine = [base] if len(base["blocks"]) > (1 if B.pnum else 0) else []
        for it in p.get("items") or []:
            key = str(it.get("key") or "")
            c = it.get("content") if isinstance(it.get("content"), dict) else {}
            kind = str(c.get("kind") or key)
            s = head(key)
            if key in ("content-ox", "content-ox-en") and B.ox:
                if pb:
                    s["blocks"].append(dict(pb))
                for st in c.get("statements") or []:
                    s["blocks"].append({"block": B.ox, "fields": {"no": coerce(st.get("no"), "number"), "sentence": st.get("text") or "",
                                                                  "answer": coerce(st.get("answer"), "bool")}})
            elif (key == "content-summary" and kind not in ("mock-exam", "outline")) or key in ("mock-exam", "outline") or kind in ("mock-exam", "outline"):
                if pb:
                    s["blocks"].append(dict(pb))
                for q in c.get("questions") or []:
                    text = q.get("prompt") or q.get("q") or ""
                    if B.prompt:
                        s["blocks"].append({"block": B.prompt, "fields": {"no": coerce(q.get("no"), "number"), "prompt": text}})
                    if B.choices and q.get("choices"):
                        s["blocks"].append({"block": B.choices, "fields": {"choices": list(q["choices"]), "answer": coerce(q.get("answer") or "", "answer")}})
            elif key in ("vocab-blank", "vocab-blank-2", "grammar-blank") and B.blank:
                for i, r in enumerate(c.get("rows") or [], 1):
                    bl = r.get("blanks") or []
                    s["blocks"].append({"block": B.blank, "fields": {"no": i, "sentence": _blank_sentence(r.get("en"), bl),
                                                                     "kr": r.get("ko") or "", "answer": ", ".join((b.get("answer") or "") for b in bl)}})
            elif key in ("grammar-ox", "grammar-fix") and B.gram_ox:
                if c.get("sentences"):
                    for st in c["sentences"]:
                        s["blocks"].append({"block": B.gram_ox, "fields": {"no": coerce(st.get("no"), "number"), "sentence": st.get("text") or "",
                                                                           "answer": coerce(st.get("answer") or "", "answer")}})
                else:
                    # 본문에 n[word] 표시 → 문장마다 한 줄, 표시한 낱말은 밑줄
                    from core.sources.yos_workbook import _sentences
                    for i, sent in enumerate(_sentences(str(c.get("text") or "")), 1):
                        rich, pos = [], 0
                        for m in _RE_SQUARE.finditer(sent):
                            if m.start() > pos:
                                rich.append(sent[pos:m.start()])
                            rich.append({"t": m.group(2).strip(), "u": True})
                            pos = m.end()
                        if pos < len(sent):
                            rich.append(sent[pos:])
                        s["blocks"].append({"block": B.gram_ox, "fields": {"no": i, "sentence": rich if any(isinstance(x, dict) for x in rich) else sent, "answer": ""}})
            elif key in ("vocab-choice", "vocab-choice-2", "grammar-choice") and B.passage:
                text = _RE_ANGLE.sub(lambda m: f"({m.group(1)})[ {m.group(2)} ]", str(c.get("text") or ""))
                if not text:
                    log.append(f"{no}·{key}: 본문 없음")
                    continue
                s["blocks"].append({"block": B.passage, "fields": {B.main_field(B.passage): text}})
            else:
                log.append(f"{no}·{it.get('label') or key}: 맞는 블록 없음 — 건너뜀")
                continue
            if len(s["blocks"]) > (1 if B.pnum else 0):
                if any(x["id"] == s["id"] for x in mine):                  # 같은 항목이 둘(예: 어법 선택 본문 + 정답지 판본)
                    s["id"] += f"-{sum(1 for x in mine if x['id'].startswith(s['id'])) + 1}"
                mine.append(s)
        sets.extend(mine)
    return sets, log
