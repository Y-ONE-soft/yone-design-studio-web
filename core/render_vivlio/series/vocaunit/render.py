"""UNIT형 단어장 렌더러 — data.json → build/index.html (Vivliostyle 입력).

문서 구조: 간지 → Unit 1 → Unit 2 → … → 판권면(맨 뒤 왼쪽 면). Unit 은 왼쪽 면에서
시작하고, 그 때문에 남는 오른쪽 면은 MEMO 면이 된다. 책마다 다른 것(브랜드·Unit
이름·번호 자릿수·판권 문구)은 전부 config 에서 온다.

원고 표기 → 조판 표기(전부 **구조**로 바꾼다. 문구 화이트리스트를 쓰지 않는다):
  · `[명] [동] [형] …`  품사 대괄호 → **네모 배지 글리프**. 품사가 나오면 **줄을 바꾼다**
  · `1. 2. 3.`          의미 번호 → `① ② ③` (보조색)
  · `(한글만)`          쓰임 설명 → 작은 글자
  · `(= …)` `(↔ …)`    유의어·반의어 → 작은 글자 + 회색, 또는 **통째로 뺀다**
                        (`options.notes: "drop"` — 광문보카는 뺀다)
  · `[단어]`            예문 안 대괄호 → 강조색 (영문·해석 공통)
"""
import html
import os
import re

_RE_POS = re.compile(r"\[([명동형부전접대감조])\]")
# 파생어에선 품사 뒤 공백까지 먹는다 — 배지 자체 여백이 있어 겹치면 벌어져 보인다
_RE_POS_SP = re.compile(r"\[([명동형부전접대감조])\]\s*")
# 의미 번호 — 뒤따르는 공백까지 먹는다(줄바꿈 불가 공백으로 바꿔 붙이려고)
_RE_SENSE = re.compile(r"(?<![0-9A-Za-z])([1-9])\.[ \t]")
_RE_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_RE_PAREN = re.compile(r"\(([^()]*)\)")
_RE_HAS_LATIN = re.compile(r"[A-Za-z]")
# 유의어/반의어 주석 — 여는 자리만 찾고, 닫는 자리는 깊이를 세어 찾는다(중첩 괄호)
_RE_NOTE_OPEN = re.compile(r"\s*(\()\s*[=↔≠]")
_RE_SPACE_PUNCT = re.compile(r"\s+([,;.)\]])")
_RE_MULTISPACE = re.compile(r"\s{2,}")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨"


def esc(s):
    return html.escape(s or "", quote=False)


def _sense(s):
    """`1.` → `①`. 번호와 뒤 낱말을 **줄바꿈 불가 공백**으로 묶는다 —
    안 묶으면 번호만 줄 끝에 덩그러니 남는다(`… 연쇄 ②` / 다음 줄 `계승(권)`)."""
    return _RE_SENSE.sub(
        lambda m: f'<span class="n">{_CIRCLED[int(m.group(1)) - 1]}</span>\u00a0', s)


def drop_notes(s):
    """`(= …)` `(↔ …)` 를 통째로 뺀다. 지우고 남는 공백·구두점 앞 공백까지 정리.

    ⚠ 괄호 안을 `[^()]*` 로 훑는 정규식으로는 **안 된다** — 주석 안에 괄호가 또 들어온다
    (`(= judg(e)ment)` · `(↔ uncertainty … 불확실(성))`). 여는 괄호부터 깊이를
    세어 닫는 자리를 찾는다.
    """
    src = s or ""
    out, i = [], 0
    while i < len(src):
        m = _RE_NOTE_OPEN.match(src, i)
        if not m:
            out.append(src[i])
            i += 1
            continue
        depth, j = 0, m.start(1)          # m.group(1) = 여는 괄호
        while j < len(src):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1                          # 닫는 괄호까지 통째로 버린다
        while out and out[-1] == " ":      # 주석 앞 공백도 같이
            out.pop()
    res = _RE_SPACE_PUNCT.sub(r"\1", "".join(out))
    return _RE_MULTISPACE.sub(" ", res).strip()


def has_note(s):
    """빼지 못하고 남은 주석이 있는가 — 침묵 유실 방지용 확인."""
    return bool(re.search(r"\(\s*[=↔≠]", s or ""))


def _paren(s):
    """괄호 주석 — 유의어/반의어(= ↔)와 쓰임 설명(한글만)을 작은 글자로."""
    def one(m):
        inner = m.group(1)
        head = inner.lstrip()[:1]
        if head in ("=", "↔", "≠"):
            return f'<span class="note">({inner})</span>'
        if inner and not _RE_HAS_LATIN.search(inner):
            return f'<span class="q">({inner})</span>'
        return m.group(0)
    return _RE_PAREN.sub(one, s)


def meaning(s, notes="small"):
    """뜻 — 품사마다 한 줄. 품사는 네모 배지, 의미 번호는 보조색."""
    if notes == "drop":
        s = drop_notes(s)
    hits = list(_RE_POS.finditer(s or ""))
    if not hits:
        return f"<p>{_paren(_sense(esc(s)))}</p>"
    out = []
    head = s[:hits[0].start()].strip()
    if head:
        out.append(("", head))
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(s)
        out.append((m.group(1), s[m.end():end].strip()))
    return "".join(
        f'<p>{f'<b class="pos">{esc(pos)}</b>' if pos else ""}'
        f"{_paren(_sense(esc(body)))}</p>"
        for pos, body in out)


def deriv(line, notes="small"):
    """파생어 한 줄 — `단어 [품사] 뜻`. 품사만 네모 배지로."""
    if notes == "drop":
        line = drop_notes(line)
    s = _paren(_sense(esc(line)))
    return _RE_POS_SP.sub(lambda m: f'<b class="pos">{m.group(1)}</b>', s)


def example(s):
    """예문 — `[단어]` 는 강조. 해석의 대괄호도 같은 강조색을 쓴다."""
    return _RE_BRACKET.sub(lambda m: f"<em>{esc(m.group(1))}</em>", esc(s))


_SUFFIX = "(?:e?s|e?d|ing|ies|ied|ly|r|st)?"


def highlight(sentence, words):
    """예문에서 그 묶음의 표제어들을 강조.

    표형 원고는 대괄호 표시가 없다. 낱말이 원형으로 적혀 있고 문장엔 굴절형이
    나오므로(`individual` → `individuals`) 흔한 어미까지 같이 잡는다. 겹치는
    구간은 **긴 쪽을 남긴다** — `ticket office` 와 `office` 가 같이 걸리면
    짧은 쪽이 긴 쪽을 잘라 먹는다.
    """
    spans = []
    for w in sorted(set(words), key=len, reverse=True):
        pat = re.compile(r"\b" + re.escape(w).replace(r"\ ", r"\s+")
                         + _SUFFIX + r"\b", re.I)
        for m in pat.finditer(sentence):
            if all(m.end() <= a or m.start() >= b for a, b in spans):
                spans.append((m.start(), m.end()))
    out, at = [], 0
    for a, b in sorted(spans):
        out.append(esc(sentence[at:a]))
        out.append(f"<em>{esc(sentence[a:b])}</em>")
        at = b
    out.append(esc(sentence[at:]))
    return "".join(out)


def _w_em(t):
    """Tab(잘난체) 기준 글자폭 합 — 한글 1em, 라틴 0.62em, 공백 0.3em."""
    tot = 0.0
    for ch in t or "":
        tot += 0.3 if ch == " " else (1.0 if ord(ch) > 0x2000 else 0.62)
    return tot


def fit_pt(text, mm, cap):
    """`mm` 폭 안에 들어가는 최대 글자 크기(pt). 큰 원 안은 자리가 정해져 있어
    긴 이름(`Special Lesson`)을 그대로 두면 큰 숫자를 덮는다."""
    w = _w_em(text)
    if w <= 0:
        return cap
    return round(min(cap, mm / (w * 0.3528)), 2)


def _wcls(w):
    n = len(w or "")
    return " xlong" if n >= 17 else (" long" if n >= 13 else "")


class Renderer(object):

    def __init__(self, cfg, mirror=(), sample=False):
        self.cfg = cfg
        o = cfg.section("options") or {}
        self.o = o
        self.brand = o.get("brand") or cfg.book.get("brand", "")
        self.title = cfg.book.get("title", "")
        self.pad = int(o.get("no_pad", 3))
        self.notes = o.get("notes", "small")     # "small" | "drop"
        self.mirror = set(mirror or ())
        self.sample = sample
        self._op = 0
        # 둥근 탭 안쪽 폭(양옆 1.2mm 씩 여유) — 글자 크기를 여기 맞춘다
        self.tab_mm = float(o.get("tab_mm", 26.7))

    # ── 러닝 요소 ────────────────────────────────────────────────────────
    def running(self, tab, off=False, part=0):
        """③탭(왼쪽) · ④로고(오른쪽) · 쪽번호.

        off=True 는 간지처럼 표식이 없는 면 — 러닝 요소는 다음 값이 올 때까지
        남으므로 **빈 값을 명시적으로 흘려보내는 것**이 요점이다.
        """
        k = (" off" if off else "") + (f" p{part}" if part else "")
        st = (f' style="font-size:{fit_pt(tab, self.tab_mm, 12)}pt"'
              if tab else "")
        return (f'<div class="hdr-l{k}"><i{st}>{esc(tab)}</i></div>'
                f'<div class="hdr-r{k}"><b>{esc(self.brand)}</b></div>'
                f'<div class="foot-l{k}"></div><div class="foot-r{k}"></div>')

    def _mir(self):
        self._op += 1
        return " mir" if self._op in self.mirror else ""

    # ── ① Unit 시작 헤더 ────────────────────────────────────────────────
    def unit_head(self, unit):
        """큰 원 = 눈썹(대단원명) · 작은 글자 · 큰 글자.

        세 칸 다 **원고에서 온 문자열**이다 — `UNIT 15` 도 `Special Lesson 2` 도
        `2024년 9월` 도 같은 틀에 들어간다. 작은 글자는 길면 줄여 넣는다.
        """
        top = unit.get("head_top", "")
        ttl = unit.get("head_ttl", self.o.get("unit_word", "UNIT"))
        num = unit.get("head_num") or f"{unit.get('num', 0):02d}"
        slot = float(self.o.get("head_slot_mm", 12.2))
        st = f' style="font-size:{fit_pt(ttl, slot, 14)}pt"' if ttl else ""
        sp = f' style="font-size:{fit_pt(top, slot, 7.5)}pt"' if top else ""
        return (f'<div class="unit-head{self._mir()}">'
                '<u class="mk">DAYOPEN</u>'
                + (f'<span class="top"{sp}>{esc(top)}</span>' if top else "")
                + (f'<span class="ttl"{st}>{esc(ttl)}</span>' if ttl else "")
                + f'<span class="num">{esc(num)}</span></div>')

    # ── 표제어 항목 ─────────────────────────────────────────────────────
    def word(self, w):
        chk = '<span class="chk"><i></i><i></i><i></i></span>'
        der = "".join(f"<p>{deriv(x, self.notes)}</p>" for x in w["deriv"])
        pairs = []
        for en, kr in w["pairs"]:
            pairs.append('<div class="pair">'
                         f'<p class="en">{example(en)}</p>'
                         + (f'<p class="kr">{example(kr)}</p>' if kr else "")
                         + "</div>")
        return (
            '<article class="w"><div class="w-l">'
            f'<div class="w-top"><span class="w-no">{w["no"]:0{self.pad}d}</span>'
            f'{chk}</div>'
            f'<div class="w-word{_wcls(w["word"])}">{esc(w["word"])}</div>'
            f'<div class="w-pron">{esc(w["pron"])}</div>'
            + (f'<div class="w-deriv">{der}</div>' if der else "")
            + '</div><div class="w-r">'
            f'<div class="w-def">{meaning(w["meaning"], self.notes)}</div>'
            f'<div class="w-ex">{"".join(pairs)}</div>'
            "</div></article>")

    # ── 표형(낱말표) 항목 ───────────────────────────────────────────────
    def word_flat(self, w):
        """한 줄짜리 항목 — 번호·회독칸·표제어 | 뜻. 발음기호도 파생어도 없다."""
        chk = '<span class="chk"><i></i><i></i><i></i></span>'
        return (
            '<article class="w flat"><div class="w-l">'
            f'<span class="w-no">{w["no"]:0{self.pad}d}</span>{chk}'
            f'<span class="w-word{_wcls(w["word"])}">{esc(w["word"])}</span>'
            '</div><div class="w-r">'
            f'<div class="w-def">{meaning(w["meaning"], self.notes)}</div>'
            "</div></article>")

    def group_head(self, label):
        """소단원 머리 — `Analysis` · `1번` · `본문1` · `20번`."""
        return f'<div class="g-head"><span>{esc(label)}</span></div>'

    def run_ex(self, run):
        """묶음 예문 — 같은 문장에서 나온 낱말들을 한 번에 강조해 한 번만 싣는다."""
        if not run.get("ex"):
            return ""
        words = [w["word"] for w in run["words"]]
        return (f'<div class="run-ex"><p class="en">'
                f'{highlight(run["ex"], words)}</p></div>')

    # ── 대단원 간지(2면) ────────────────────────────────────────────────
    def part_cover(self, part):
        """왼쪽 = 대단원 표지 · 오른쪽 = 그 대단원의 차례.

        두 면은 **형제 섹션**이다(중첩하면 페이지 이름이 겹친다). 왼쪽 면에
        `break-before: left` 가 걸려 있어 언제나 펼침면으로 열린다.
        """
        n = part["idx"]
        sub = part.get("sub") or ""
        left = (f'<section class="part-cover p{n}" style="page:p-part{n}">'
                + self.running("", off=True, part=n)
                + f'<u class="mk">PARTOPEN</u>'
                + f'<div class="no">PART {n}</div>'
                + f'<div class="ttl">{esc(part["name"])}</div>'
                + (f'<div class="sub">{esc(sub)}</div>' if sub else "")
                + '<div class="mark"></div>'
                + "</section>")
        rows = "".join(f"<li><b>{esc(u['head'])}</b>"
                       f"<span>{u['words']}</span></li>" for u in part["toc"])
        right = (f'<section class="part-toc p{n}" style="page:p-part{n}b">'
                 + self.running("", off=True, part=n)
                 + f'<h2>{esc(part["name"])}</h2>'
                 + f'<ol>{rows}</ol>'
                 + f'<div class="cnt">모두 {part["words"]}개</div>'
                 + "</section>")
        return left + right

    # ── 판권면 ──────────────────────────────────────────────────────────
    def colophon(self):
        cr = self.o.get("copyright", "")
        return ('<section class="colophon" style="page:p-cover">'
                + self.running("", off=True)
                + '<div class="mark"></div>'
                + (f'<div class="cr">{esc(cr)}</div>' if cr else "")
                + "</section>")

    # ── 간지 ────────────────────────────────────────────────────────────
    def cover(self):
        return ('<section class="cover" style="page:p-cover">'
                + self.running("", off=True)
                + '<div class="crest"></div>'
                f'<div class="ttl">{esc(self.brand)}</div></section>')

    # ── 문서 조립 ───────────────────────────────────────────────────────
    def document(self, d):
        units = d["units"]
        parts = d.get("parts") or []
        if self.sample:
            s = self.o.get("sample") or {}
            units = units[:int(s.get("units", 1))]
            if s.get("words"):
                units = [dict(u, words=u["words"][:int(s["words"])])
                         for u in units]
            keep = {u["part"] for u in units}
            parts = [p for p in parts if p["idx"] in keep]

        # 간지의 차례는 **실제로 조판되는 단원**에서 만든다(견본이면 견본대로)
        for p in parts:
            p["toc"] = [{"head": u["head"], "words": len(u["words"])}
                        for u in units if u["part"] == p["idx"]]
            p["words"] = sum(t["words"] for t in p["toc"])

        body = []
        if self.o.get("cover", True):
            body.append(self.cover())
        seen = set()
        for u in units:
            n = u.get("part", 0)
            if n and n not in seen:
                seen.add(n)
                pt = next((p for p in parts if p["idx"] == n), None)
                if pt and self.o.get("part_cover", True):
                    body.append(self.part_cover(pt))
            body.append(self.unit(u, n))
        if self.o.get("colophon", True):
            # 마지막 면을 왼쪽으로 — `break-before: left` 라 총 쪽수가 짝수가 된다
            body.append(self.colophon())
        return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f"<title>{esc(self.title)}</title>"
                '<link rel="stylesheet" href="theme.css">'
                '<link rel="stylesheet" href="pages.css"></head><body>'
                + "".join(body) + "</body></html>")

    def group(self, g):
        """소단원 하나 — 머리 + (낱말들 + 그 묶음의 예문) 되풀이."""
        return ((self.group_head(g["label"]) if g["label"] else "")
                + "".join("".join(self.word_flat(w) for w in r["words"])
                          + self.run_ex(r) for r in g["runs"]))

    def unit(self, u, n):
        """단원 하나 — 블록형은 항목을 죽 잇고, 표형은 소단원·묶음으로 나눈다."""
        cls = f"unit unit-open{f' p{n}' if n else ''}"
        if u.get("kind") == "flat":
            inner = "".join(self.group(g) for g in u["groups"])
        else:
            inner = "".join(self.word(w) for w in u["words"])
        return (f'<section class="{cls}" style="page:p-body">'
                + self.running(u["label"], part=n)
                + self.unit_head(u) + inner + "</section>")


def write(cfg, data, build_dir, mirror=(), sample=False, log=None):
    r = Renderer(cfg, mirror=mirror, sample=sample)
    text = r.document(data)
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    if log:
        log(f"[렌더] {'견본' if sample else '전권'} {len(text) // 1024}KB "
            f"→ {os.path.basename(out)}")
    return out
