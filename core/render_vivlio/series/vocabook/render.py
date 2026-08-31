"""단어장 계열 렌더러 — data.json → build/index.html (Vivliostyle 입력).

문서 구조(계열 고정): 표지 자리 → PART1 간지 → (1)표제어 → (2)파생어&연관어휘 →
(3)more with → (4)VOCA vs. VOCA → PART2 간지 → 워크북 A~D → 정답.
책마다 다른 것(제목·브랜드·Day 범위·간지 문구·섹션 제목)은 전부 config 에서 온다.

조판 규칙(사용자 지시, 계열 공통):
  · Day 는 왼쪽 페이지에서 시작(`break-before: left`) → 생기는 오른쪽 빈 면이 MEMO 면
  · 워크북 A·B·C·D 는 각각 새 페이지에서 시작
  · 뜻은 품사 단위로 줄바꿈, 품사는 글리프 배지
  · 좌우 면 표식을 다르게: 왼쪽 = 사선 장식, 오른쪽 = DAY 탭
  · 왼쪽 푸터 = `쪽 | 책이름`, 오른쪽 = `DAY/섹션 | 쪽`

함정: 태그를 닫지 않으면 DOM 이 중첩돼 열 폭이 계속 좁아진다(B섹션에서 겪음).
원고의 **연속 공백은 의미 구분 간격**이라 `esc_gap()` 으로 보존한다(HTML 은 축약).
"""
import html
import os
import re

from core.render_vivlio import refs as _refs
from core.render_vivlio import stage

_RE_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_RE_SENSE = re.compile(r"(?<![0-9A-Za-z])(\d+)\.(?=\s)")
_RE_BLANK = re.compile(r"([A-Za-z])(_{3,})")
_RE_SPACES = re.compile(r"  +")
# 품사 — 뜻의 선두 또는 문중에 오는 '명. 동. 형. …'
_POS_CHARS = "명동형부전접대조감"
_RE_POS_ANY = re.compile(rf"(?<![가-힣])([{_POS_CHARS}])\.\s*")

PAGE_NAME = {"s-head": "p-head", "s-deriv": "p-deriv", "s-mw": "p-mw",
             "s-vs": "p-vs", "s-wb": "p-wb", "s-ans": "p-ans"}

PAGE_H = 179.0                   # 워크북 지면 세로(mm) — 문항 간격 채우기 계산용
EN_CPL, KR_CPL = 93, 53          # 한 줄에 들어가는 글자 수(추정)


def esc(s):
    return html.escape(s or "", quote=False)


def esc_gap(s):
    """원고의 연속 공백(뜻·유반의어의 항목 구분)을 고정 간격으로 보존."""
    return _RE_SPACES.sub('<span class="gap"></span>', esc(s))


def ex_en(s):
    """예문 — `[단어]` → 강조. 해석의 대괄호도 영문과 같은 빨강을 유지한다."""
    return _RE_BRACKET.sub(lambda m: f"<em>{esc(m.group(1))}</em>", esc(s))


ex_kr = ex_en


def meaning(s):
    """뜻 — 품사는 글리프 배지로, 품사가 바뀌면 줄바꿈, 의미번호는 보조색."""
    hits = [(m.start(), m.end(), m.group(1)) for m in _RE_POS_ANY.finditer(s)]
    if not hits:
        return _RE_SENSE.sub(lambda m: f"<i>{m.group(1)}.</i>", esc_gap(s))

    lines = []
    head = s[:hits[0][0]].strip()
    if head:
        lines.append(("", head))
    for i, (_st, en, ch) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(s)
        lines.append((ch, s[en:end].strip()))

    out = []
    for ch, body in lines:
        b = _RE_SENSE.sub(lambda m: f"<i>{m.group(1)}.</i>", esc_gap(body))
        pos = f'<span class="pos">{ch}</span>' if ch else ""
        out.append(f'<span class="ln">{pos}{b}</span>')
    return "".join(out)


def syn(s):
    """유반의어 — 바깥 대괄호는 묶음 표시일 뿐이라 감춘다."""
    return esc_gap(_RE_BRACKET.sub(lambda m: m.group(1), s))


def blanked(s):
    """워크북 B — 'c______' → 강조 첫 글자 + **끊기지 않은** 밑줄 한 줄."""
    return _RE_BLANK.sub(
        lambda m: f'<span class="bl"><span class="blank">{m.group(1)}</span>'
                  f'<span class="ul"></span></span>',
        esc(s))


def _wcls(w):
    """표제어 길이별 축소 — 라벨 열 폭 대응."""
    return " xlong" if len(w) >= 18 else (" long" if len(w) >= 13 else "")


def _vw(t):
    """시각 폭 — 한글 1, 나머지 0.5로 센다."""
    return sum(1.0 if ord(ch) > 0x1100 else .5 for ch in t)


class Renderer(object):
    """책 한 권치 HTML 조립. cfg = BookConfig."""

    def __init__(self, cfg, mirror=(), nomemo=False, sample=False):
        self.cfg = cfg
        o = cfg.section("options") or {}
        self.o = o
        self.title = cfg.book.get("title", "")
        self.brand = o.get("brand") or cfg.book.get("brand", "")
        self.subtitle = o.get("subtitle", "")
        self.day_first, self.day_last = (o.get("day_range") or [1, 1])[:2]
        self.idx_step = o.get("idx_step_mm", 8)
        self.sec_title = {k: (v.get("title") or "")
                          for k, v in (o.get("sections") or {}).items()}
        self.mirror = set(mirror or ())
        self.nomemo = nomemo
        self.sample = sample
        self._op = 0

    # ── 러닝 요소 ────────────────────────────────────────────────────────
    def _op_cls(self):
        """시작면 일련번호 → 오른쪽에서 시작하는 면이면 헤더를 좌우 반전."""
        self._op += 1
        return " dh-right" if self._op in self.mirror else ""

    def _step(self, day):
        """측면 라벨 세로 위치 — Day 마다 한 칸씩 아래로(실제 색인처럼)."""
        span = max(0, self.day_last - self.day_first)
        return max(0, min(span, day - self.day_first)) * self.idx_step

    def running(self, tab, num="", step=0, off=False, foot_off=False):
        """③왼쪽 마름모 탭 / ②오른쪽 상단 밴드 / 측면 라벨 / 푸터.

        off=True 는 간지처럼 Day 표식이 없는 면 — 직전 Day 값이 남지 않도록
        **빈 값을 명시적으로 흘려보내는 것**이 요점이다.
        """
        # 머리·꼬리도 지면의 일부라 **고를 수 있어야 한다.** 자리표 머리글자가
        # 곧 출처다 — 브랜드·책 제목은 책 설정에서 오고, 나머지는 조판물이다.
        k = " off" if off else ""
        fk = " off" if foot_off else ""
        return (f'<div{_refs.mark("#탭(왼쪽)", "tab-l" + k)}><i>{esc(num)}</i></div>'
                f'<div{_refs.mark("book.brand", "hdr-big")}>{esc(self.brand)}</div>'
                f'<div{_refs.mark("#머리 라벨", "idx" + k)}'
                f' style="--idx-step:{step}mm">{esc(tab)}</div>'
                f'<div{_refs.mark("#꼬리말(왼쪽)", "foot-l" + fk)}>'
                f'<span class="pg"></span>'
                f'<span class="sep">|</span>{esc(self.title)}</div>'
                f'<div{_refs.mark("#꼬리말(오른쪽)", "foot-r" + fk)}>{esc(tab)}'
                f'<span class="sep">|</span>'
                f'<span class="pg"></span></div>')

    def day_head(self, day, label="DAY", ko=False, title="", mark=True):
        """① 시작 면(왼쪽) — 상단 밴드 + 태그.

        mark=False 는 2패스 빌드가 이 면을 '① 시작면'으로 잡지 않게 한다. 정답 면은
        상단 여백을 줄여 쓰므로, 다음 면에 큰 밴드가 깔리면 본문과 겹친다.
        """
        b = f'<b class="ko">{esc(str(day))}</b>' if ko else f'<b>{day}</b>'
        return (f'<div{_refs.mark("#DAY 머리", "day-head")}>'
                + ('<u class="mk">DAYOPEN</u>' if mark else '')
                + '<span class="band"></span>'
                + f'<span{_refs.mark("#DAY 마름모", "dia")}><i>'
                + (f'<s>{esc(label)}</s>' if label else '')
                + f'{b}</i></span>'
                + (f'<span{_refs.mark("#DAY 제목", "dh-title")}>{esc(title)}</span>'
                   if title else '')
                + '</div>')

    # ── Part 1 ──────────────────────────────────────────────────────────
    def word_block(self, no, b, with_def=True, with_num=True, anchor=""):
        if with_num:
            tag = f'<span class="w-anchor">{esc(anchor)}</span>' if anchor else ""
            top = (f'<div class="w-top"><span class="w-num">{no:04d}</span>'
                   f'<span class="w-rule"></span>{tag}</div>')
        else:
            top = ""
        br = _refs.of(b)
        o = [f'<article class="w">{top}'
             f'<div class="w-lead">'
             f'<div{_refs.mark(br and br + ".word", "w-word" + _wcls(b["word"]))}>'
             f'{esc(b["word"])}</div>'
             f'<div{_refs.mark(br and br + ".meaning", "w-mean")}>'
             f'{meaning(b["meaning"])}</div></div>']
        for ri, row in enumerate(b["rows"]):
            lab = row["label"]
            if lab == "예문":
                cls, val = "r-ex", []
                for i in range(0, len(row["lines"]), 2):
                    en = row["lines"][i]
                    kr = row["lines"][i + 1] if i + 1 < len(row["lines"]) else ""
                    lr = f'{br}.rows.{ri}.lines' if br else ''
                    val.append('<div class="pair">'
                               f'<p{_refs.mark(lr and f"{lr}.{i}", "en")}>'
                               f'{ex_en(en)}</p>'
                               + (f'<p{_refs.mark(lr and f"{lr}.{i + 1}", "kr")}>'
                                  f'{ex_kr(kr)}</p>' if kr else "")
                               + "</div>")
                body = "".join(val)
            elif lab == "유반의어":
                cls = "r-syn"
                body = "".join(f"<p>{syn(x)}</p>" for x in row["lines"])
            else:
                if not with_def:
                    continue
                cls = "r-def"
                lr = f'{br}.rows.{ri}.lines' if br else ''
                body = "".join(
                    f'<p{_refs.mark(lr and f"{lr}.{li}")}>{esc_gap(x)}</p>'
                    for li, x in enumerate(row["lines"]))
            o.append(f'<div class="w-row {cls}"><div class="lab">{esc(lab)}</div>'
                     f'<div class="val">{body}</div></div>')
        o.append("</article>")
        return "".join(o)

    def day_flow(self, blocks, cls, with_def=True, grouped=False, title=""):
        """Day 단위 흐름. Day 시작 = 왼쪽 페이지 + 헤더 밴드, 이후는 러닝 탭."""
        out, cur_day, n = [], None, 0
        open_group = [False]

        def close_group():
            if open_group[0]:
                out.append("</div>")
                open_group[0] = False

        prev_stem = None
        for b in blocks:
            if b["day"] != cur_day:
                close_group()
                if cur_day is not None:
                    out.append("</section>")
                cur_day = b["day"]
                prev_stem = None
                tab = f"DAY {cur_day}"
                out.append(
                    f'<section class="day-open {cls}{self._op_cls()}">'
                    f'{self.running(tab, str(cur_day), self._step(cur_day))}'
                    f'{self.day_head(cur_day, title=title)}')
            if grouped:
                # 묶음 키 — gen_data 가 어근 기준으로 표제어에 귀속시켜 둔 값
                st = b.get("grp") or b["word"]
                if st != prev_stem:
                    close_group()
                    out.append('<div class="wg">')
                    open_group[0] = True
                    prev_stem = st
                    n += 1
                    out.append(self.word_block(n, b, with_def,
                                               anchor=b.get("grp_head", "")))
                else:
                    out.append(self.word_block(n, b, with_def, with_num=False))
            else:
                n += 1
                out.append(self.word_block(n, b, with_def))
        close_group()
        out.append("</section>")
        return "".join(out)

    def more_with(self, groups):
        title = self.sec_title.get("s-mw", "more with")
        o = ['<section class="s-mw day-open" style="page:p-mw">'
             + self.running(title, "03")
             + self.day_head("03", label="PART 1", title=title)]
        for g in groups:
            items = []
            for it in g["items"]:
                w = esc(it["word"])
                if g["root"] in it["word"]:
                    w = w.replace(g["root"], f'<b>{g["root"]}</b>', 1)
                ir = _refs.of(it)
                items.append(f'<li><span{_refs.mark(ir and ir + ".word", "wd")}>{w}</span> '
                             f'<span{_refs.mark(ir and ir + ".meaning", "mean")}>'
                             f'{meaning(it["meaning"])}</span></li>')
            o.append(f'<section class="mw"><div class="mw-root">'
                     f'<span class="mw-pill">more with</span>'
                     f'<span class="mw-word">{esc(g["root"])}</span></div>'
                     f'<ul class="mw-items">{"".join(items)}</ul></section>')
        o.append("</section>")
        return "".join(o)

    def vs_voca(self, groups):
        title = self.sec_title.get("s-vs", "VOCA vs. VOCA")
        o = ['<section class="s-vs day-open" style="page:p-vs">'
             + self.running(title, "04")
             + self.day_head("04", label="PART 1", title=title)]
        for g in groups:
            items = []
            for it in g["items"]:
                ex = "".join(f'<p class="ex-en">{ex_en(e[0])}</p>'
                             f'<p class="ex-kr">{ex_kr(e[1])}</p>'
                             for e in it["ex"] if e[0])
                ir = _refs.of(it)
                items.append(f'<li class="vs-item"><p class="hd">'
                             f'<span{_refs.mark(ir and ir + ".word", "vs-word")}>'
                             f'{esc(it["word"])}</span> '
                             f'<span{_refs.mark(ir and ir + ".meaning", "vs-mean")}>'
                             f'{esc(it["meaning"])}</span>'
                             f'</p>{ex}</li>')
            o.append(f'<section class="vs"><div class="vs-head">'
                     f'<span class="vs-pill">VOCA vs. VOCA</span>'
                     f'<span class="vs-title">{esc(g["title"])}</span></div>'
                     f'<ul class="vs-items">{"".join(items)}</ul></section>')
        o.append("</section>")
        return "".join(o)

    # ── Part 2 (워크북) ──────────────────────────────────────────────────
    @staticmethod
    def _fill_gap(heights, head_h):
        """아래 여백이 남으면 문항 사이를 벌려 지면을 채운다.
        남는 높이의 일부만 쓰고 상한을 둬서 한 면이 더 늘어나지 않게 한다."""
        n = len(heights)
        if n < 2:
            return 0.0
        total = head_h + sum(heights)
        pages = max(1, int(-(-total // PAGE_H)))
        leftover = pages * PAGE_H - total
        if leftover <= 0:
            return 0.0
        return round(min(leftover * .55 / (n - 1), 3.5), 2)

    @staticmethod
    def _est_heights(sec):
        """문항별 높이(mm) — 실제 조판 PDF 에서 잰 피치로 보정한 값.
        A 8.74 · B 6.92 · C 6.04 · D 5.65 (A·D 는 2단이라 행 수로 환산)."""
        L, hs = sec["letter"], []
        n_item = sum(1 for it in sec["items"] if it["kind"] == "item")
        if L == "A":
            return [8.74] * -(-n_item // 2)
        if L == "D":
            box = [17.2] if any(it["kind"] == "cont" for it in sec["items"]) else []
            return box + [5.65] * -(-n_item // 2)
        pend = None
        for it in sec["items"]:
            if L == "B":
                if it["kind"] == "item":
                    if pend is not None:
                        hs.append(pend)
                    pend = 6.92 + 2.9 * (max(1, -(-len(it["text"]) // EN_CPL)) - 1)
                elif it["kind"] == "cont" and pend is not None:
                    pend += 2.6 * (max(1, -(-int(_vw(it["text"])) // KR_CPL)) - 1)
            else:                                   # C
                if it["kind"] == "item":
                    hs.append(6.04 + 2.8 * (max(1, -(-len(it["text"]) // 78)) - 1))
                elif it["kind"] == "bogi":
                    hs.append(2.2)   # 띠는 문항 피치에 포함, 늘린 아래 여백만 반영
        if L == "B" and pend is not None:
            hs.append(pend)
        return hs

    def wb_section(self, sec, first=False):
        L = sec["letter"]
        opened_items = False
        gap = self._fill_gap(self._est_heights(sec), 9.0)
        o = [f'<div class="sec{" first" if first else ""}" style="--gap:{gap}mm">'
             f'<div class="sec-head">'
             f'<span class="sec-badge {L}">{L}</span>'
             f'<span class="sec-prompt">{esc(sec["prompt"])}</span></div>']
        items = sec["items"]
        if L == "A":
            o.append('<div class="qa">')
            for it in items:
                if it["kind"] != "item":
                    continue
                ir = _refs.of(it)
                o.append(f'<div class="q"><span class="no">{int(it["no"]):02d}</span>'
                         f'<span{_refs.mark(ir and ir + ".text", "wd")}>'
                         f'{esc(it["text"].strip())}</span>'
                         f'<span class="rule"></span></div>')
            o.append("</div>")
        elif L == "B":
            o.append('<div class="qb">')
            pend = None
            for it in items:
                if it["kind"] == "item":
                    if pend:
                        o.append(pend + "</div></div>")
                    ir = _refs.of(it)
                    pend = (f'<div class="q"><span class="no">{int(it["no"]):02d}</span>'
                            f'<div><p{_refs.mark(ir and ir + ".text", "en")}>'
                            f'{blanked(it["text"])}</p>')
                elif it["kind"] == "cont" and pend:
                    ir = _refs.of(it)
                    pend += (f'<p{_refs.mark(ir and ir + ".text", "kr")}>'
                             f'{esc(it["text"])}</p>')
            if pend:
                o.append(pend + "</div></div>")
            o.append("</div>")
        elif L in ("C", "D"):
            o.append(f'<div class="q{L.lower()}">')
            opts, seq = [], 0

            def flush_opts():
                if opts:
                    joined = " ".join(opts)
                    # ①②… 앞에서 끊어 항목 단위로 감싼다 — 글리프와 단어가
                    # 줄바꿈으로 갈라지지 않게 각 항목을 nowrap 으로.
                    cells = [c.strip() for c in re.split(
                        r"(?=[①-⑳㉑-㊿])", joined) if c.strip()]
                    o.append('<div class="bogi opts">'
                             + "".join(f'<span class="opt">{esc(c)}</span>'
                                       for c in cells)
                             + "</div>")
                    del opts[:]

            for it in items:
                if it["kind"] == "qgroup":
                    flush_opts()
                elif it["kind"] == "bogi":
                    flush_opts()
                    txt = it["text"]
                    if not txt:                     # D: 〈보기〉 다음 줄부터 선택지
                        continue
                    if L == "C":
                        if opened_items:
                            o.append("</div>")
                        o.append('<div class="grp">')
                        opened_items = True
                    parts = [p.strip() for p in re.split(r"\s*/\s*", txt) if p.strip()]
                    o.append('<div class="bogi">'
                             + "  /  ".join(esc(p) for p in parts) + "</div>")
                elif it["kind"] == "cont" and L == "D":
                    opts.append(it["text"])
                elif it["kind"] == "item":
                    flush_opts()
                    if L == "D" and not opened_items:
                        o.append('<div class="items">')
                        opened_items = True
                    seq += 1
                    no = seq if L == "C" else int(it["no"])
                    txt = re.sub(r"\s*:?\s*_{3,}\s*$", "", it["text"])
                    e = esc(txt)
                    head, _, tail = e.rpartition(" ")
                    body = ((head + " " if head else "")
                            + f'<span class="nb">{tail} : '
                              f'<span class="ansbox"></span></span>')
                    ir = _refs.of(it)
                    o.append(f'<div class="q"><span class="no">{no:02d}</span>'
                             f'<span{_refs.mark(ir and ir + ".text", "df")}>'
                             f'{body}</span></div>')
            if opened_items:
                o.append("</div>")
            o.append("</div>")
        o.append("</div>")
        return "".join(o)

    def workbook(self, days):
        o = []
        for d in days:
            tab = f"DAY {d['day']}"
            o.append(f'<section class="day-open s-wb">'
                     f'{self.running(tab, str(d["day"]), self._step(d["day"]))}'
                     f'{self.day_head(d["day"])}')
            for i, sec in enumerate(d["sections"]):
                o.append(self.wb_section(sec, first=(i == 0)))
            o.append("</section>")
        return "".join(o)

    def answers(self, days):
        title = self.sec_title.get("s-ans", "정답")
        o = [f'<section class="day-open s-ans{self._op_cls()}">'
             + self.running(title, off=True)
             + self.day_head(title, label="", ko=True, mark=False)]
        for i, d in enumerate(days):
            k = " first" if i == 0 else ""
            o.append(f'<div class="ans-day{k}"><p class="a-day">Day {d["day"]}</p>'
                     f'<div class="ans">')
            for sec in d["sections"]:
                o.append(f'<div class="a-sec s{sec["letter"]}">'
                         f'<p class="a-hd">{sec["letter"]}</p><div class="a-body">')
                for it in sec["items"]:
                    t = esc(it["text"])
                    t = re.sub(r"^([^:]{1,40}):", r"<b>\1</b>:", t)
                    ir = _refs.of(it)
                    o.append(f'<div class="a-it"><span class="n">{it["no"]}</span>'
                             f'<span{_refs.mark(ir and ir + ".text", "t")}>'
                             f'{t}</span></div>')
                o.append("</div></div>")
            o.append("</div></div>")
        o.append("</section>")
        return "".join(o)

    # ── 간지 ────────────────────────────────────────────────────────────
    def cover_placeholder(self):
        """1쪽 — 표지와 같은 간지가 들어갈 자리. 빌드 마지막에 실제 간지로 교체된다."""
        note = self.o.get("cover_note", "※ 표지 간지 자리 (임시)")
        return ('<section class="cover s-head" style="page:p-part">'
                + self.running("", off=True, foot_off=True)
                + f'<p class="cv-k">{esc(self.brand)}</p>'
                f'<p class="cv-t">{esc(self.title)}</p>'
                f'<p class="cv-s">{esc(self.subtitle)}</p>'
                f'<p class="cv-note">{esc(note)}</p></section>')

    def part_divider(self, cls, kicker, ttl, sub, items):
        """파트 간지 — 2면 스프레드(왼쪽=타이틀 / 오른쪽=수록 내용).

        `.divider { break-before: right }` 는 왼쪽 빈 페이지를 만든다 → PART 간지만.
        """
        li = "".join(f"<li>{esc(a)}<span>{esc(b)}</span></li>" for a, b in items)
        return (f'<section class="divider {cls} part" style="page:p-part">'
                f'{self.running(ttl, off=True, foot_off=True)}'
                f'<p class="kicker">{esc(kicker)}</p><p class="ttl">{esc(ttl)}</p>'
                f'<p class="sub">{esc(sub)}</p><div class="bar"></div></section>'
                f'<section class="divider {cls} part2" style="page:p-part">'
                f'{self.running(ttl, off=True, foot_off=True)}'
                f'<ul class="toc">{li}</ul></section>')

    # ── 문서 조립 ───────────────────────────────────────────────────────
    def document(self, d):
        head, deriv = d["head"], d["deriv"]
        mw, vs, wb, ans = d["more_with"], d["vs_voca"], d["workbook"], d["answers"]
        if self.sample:
            s = self.o.get("sample") or {}
            day = s.get("day", self.day_first)
            head = [b for b in head if b["day"] == day]
            deriv = [b for b in deriv if b["day"] == day]
            vs = vs[:s.get("vs", 2)]
            wb = wb[:s.get("workbook", 1)]
            ans = ans[:s.get("answers", 1)]

        parts = self.o.get("parts") or {}
        p1 = parts.get("1") or {}
        p2 = parts.get("2") or {}
        # PART1 수록 내용 — 라벨은 config, 수량은 원고에서 센다(간지 문구와
        # 섹션 제목은 다르다: 간지는 "(1) 표제어", 헤더 제목은 "표제어").
        counts = {"head": len(d["head"]), "deriv": len(d["deriv"]),
                  "mw": sum(len(g["items"]) for g in mw),
                  "vs": sum(len(g["items"]) for g in d["vs_voca"])}
        toc1 = [(label, f"{counts.get(key, 0)} words")
                for label, key in (p1.get("toc") or [])]

        # 시작면 번호(_op_cls)가 문서 순서와 일치해야 하므로 순차로 조립한다
        body = [self.cover_placeholder()]
        body.append(self.part_divider(
            "s-head", p1.get("kicker", "PART 1"), p1.get("title", "단어장"),
            p1.get("sub", self.subtitle), toc1))
        body.append('<section class="s-head" style="page:p-head">'
                    + self.day_flow(head, "s-head",
                                    title=self.sec_title.get("s-head", ""))
                    + "</section>")
        body.append('<section class="s-deriv" style="page:p-deriv">'
                    + self.day_flow(deriv, "s-deriv", with_def=False, grouped=True,
                                    title=self.sec_title.get("s-deriv", ""))
                    + "</section>")
        body.append(self.more_with(mw))
        body.append(self.vs_voca(vs))
        body.append(self.part_divider(
            "s-wb", p2.get("kicker", "PART 2"), p2.get("title", "워크북"),
            p2.get("sub", ""), [tuple(x) for x in (p2.get("toc") or [])]))
        body.append('<section class="s-wb" style="page:p-wb">'
                    + self.workbook(wb) + "</section>")
        body.append('<section class="s-ans" style="page:p-ans">'
                    + self.answers(ans) + "</section>")

        return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f"<title>{esc(self.title)}</title>"
                '<link rel="stylesheet" href="theme.css">'
                + ('<style>.day-open{break-before:page}</style>'
                   if self.nomemo else '')
                + '<link rel="stylesheet" href="pages.css">'
                + stage.BOOK_CSS_LINKS + '</head><body>'
                + "".join(body) + "</body></html>")


def write(cfg, data, build_dir, mirror=(), nomemo=False, sample=False, log=None):
    # 클릭 편집용 자리표 — **워크북·정답까지** 넓혔다. 여기 안 든 자리는
    # 작업대에서 클릭해도 아무 일이 안 일어난다(조용히).
    _refs.index_paths(data, [
        ("head",), ("deriv",),
        ("more_with", "items"), ("vs_voca", "items"),
        ("workbook", "sections", "items"),
        ("answers", "sections", "items"),
    ])
    r = Renderer(cfg, mirror=mirror, nomemo=nomemo, sample=sample)
    text = r.document(data)
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    _refs.dump(build_dir)
    if log:
        log(f"[렌더] {'견본' if sample else '전권'} "
            f"{len(text) // 1024}KB → {os.path.basename(out)}")
    return out
