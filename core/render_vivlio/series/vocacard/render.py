"""vocacard 렌더러 — data.json → build/index.html.

문서 구조: 표지 자리 → PART(교과서) → PART(부교재) → PART(모의고사). 파트 안은
구간이 바뀔 때마다 작은 소제목을 얹고 낱말 카드를 흘린다(카드 1개 = 원고 1행).

`vocabook.render` 의 저수준 서식 함수(`esc`/`esc_gap`/`ex_en`/`ex_kr`/`syn`)와
헤더 4면 체계 메서드(`running`/`day_head`/`cover_placeholder`)를 그대로 물려
쓴다 — 구조가 같은 것을 다시 짜지 않는다. `word_block()`(Day 전제)만 이 계열
모양에 맞게 다시 썼다: 품사가 한글 초성이 아니라 영문 약어(n/v/a/ad)라 배지를
직접 붙이고, 라벨이 5종(예문/유반의어/파생어/주의/영영풀이)으로 늘었다.
"""
import os
import re

from core.render_vivlio import refs as _refs
from core.render_vivlio import stage
from core.render_vivlio.series.vocabook.render import (
    Renderer as VocabookRenderer, esc, esc_gap, ex_en, ex_kr,
)
from core.render_vivlio.series.vocacard.data import PART_ORDER, PART_TITLE

PART_CLASS = {"text": "s-text", "supp": "s-supp", "mock": "s-mock"}
PART_PAGE = {"text": "p-text", "supp": "p-supp", "mock": "p-mock"}


PAGE_CAP = 4          # 한 면에 담는 낱말 카드 수 — 책 config `options.page_cap` 으로 덮는다

# 유반의어 줄의 분류 태그 — `유. [유의어] downturn n. 경기 침체`
# ⚠ vocabook 의 `syn()` 은 바깥 대괄호를 **묶음 표시로 보고 벗긴다.** 이 원고에서
#   대괄호는 뜻의 범위를 가르는 **의미 있는 분류**다(원고 '범위 및 표기' 시트가
#   [문맥상 유사어]는 따로 센다고 명시). 벗기면 태그와 낱말이 뒤섞이므로
#   그대로 두고 **색만 뒤로 물린다.**
# 워드 원고는 **얇은 공백**(U+2009)으로, 엑셀 원고는 대괄호로 태그를 감싼다.
# 둘 다 받아 같은 모양으로 낸다(원고 표기 그대로 두고 색만 뒤로).
_RE_TAG = re.compile("\u2009([^\u2009]+)\u2009|\\[([^\\[\\]]+)\\]")


def syn_line(s):
    def one(m):
        return f'<span class="tg">{esc(m.group(1) or m.group(2))}</span>'
    return _RE_TAG.sub(one, esc_gap(s))


# ── 예문 속 표제어 찾기 ──────────────────────────────────────────────────
# 원고는 예문에 강조 표시를 달아 주지 않는다(상일보카는 `[낱말]` 로 왔다). 그래서
# 표제어와 그 **굴절형**을 직접 찾아 표시한다. 표제어를 그대로 찾는 것만으로는
# 96%(521/542)에 그쳐, 아래 세 갈래를 더 본다 — 실측 후 98%(531/542).
#   · 어간   abandoned→abandon+ed · realities→realit(y)+ies  (어간 4자 이상일 때만
#            — 짧은 어간으로 앞을 맞추면 엉뚱한 낱말이 걸린다)
#   · 접미사 aim→aims, fix→fixed, ban→banned (자음 겹침)  — 짧은 표제어용, 오탐 없다
#   · be     `be about to` → `was about to`
# 남는 것은 불규칙(overcome→overcame · freeze→frozen · crisis→crises)과 **예문에
# 표제어가 아예 안 나오는 낱말**이라 그대로 둔다(억지로 잡으면 오탐이 는다).
_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
_BE = {"be", "is", "are", "am", "was", "were", "been", "being"}
_SUFFIX = ("s", "es", "ed", "d", "ing", "ies", "ied")
# `at one's disposal` → `at their disposal`
_POSS = {"one's", "one\u2019s", "my", "your", "his", "her", "its", "our", "their",
         "someone's", "someone\u2019s"}
# 규칙으로 못 만드는 변화. 여기 없는 불규칙은 강조가 빠지고 `unmatched()` 가 알려준다.
_IRREGULAR = {
    "be": ("was", "were", "been", "being", "is", "are", "am"),
    "become": ("became",), "begin": ("began", "begun"), "break": ("broke", "broken"),
    "bring": ("brought",), "build": ("built",), "buy": ("bought",),
    "catch": ("caught",), "choose": ("chose", "chosen"), "come": ("came",),
    "cost": ("cost",), "deal": ("dealt",), "do": ("did", "done", "does"),
    "draw": ("drew", "drawn"), "drive": ("drove", "driven"), "eat": ("ate", "eaten"),
    "fall": ("fell", "fallen"), "feed": ("fed",), "feel": ("felt",),
    "fight": ("fought",), "find": ("found",), "fly": ("flew", "flown"),
    "forget": ("forgot", "forgotten"), "freeze": ("froze", "frozen"),
    "get": ("got", "gotten"), "give": ("gave", "given"), "go": ("went", "gone"),
    "grow": ("grew", "grown"), "hold": ("held",), "keep": ("kept",),
    "know": ("knew", "known"), "lead": ("led",), "leave": ("left",),
    "lose": ("lost",), "make": ("made",), "mean": ("meant",), "meet": ("met",),
    "overcome": ("overcame",), "pay": ("paid",), "put": ("put",),
    "read": ("read",), "rise": ("rose", "risen"), "run": ("ran",),
    "say": ("said",), "see": ("saw", "seen"), "seek": ("sought",),
    "sell": ("sold",), "send": ("sent",), "set": ("set",), "shake": ("shook", "shaken"),
    "show": ("showed", "shown"), "speak": ("spoke", "spoken"), "spend": ("spent",),
    "stand": ("stood",), "steal": ("stole", "stolen"), "take": ("took", "taken"),
    "teach": ("taught",), "tear": ("tore", "torn"), "tell": ("told",),
    "think": ("thought",), "throw": ("threw", "thrown"),
    "understand": ("understood",), "wear": ("wore", "worn"),
    "win": ("won",), "write": ("wrote", "written"),
    # 라틴·그리스계 명사
    "crisis": ("crises",), "analysis": ("analyses",), "basis": ("bases",),
    "thesis": ("theses",), "criterion": ("criteria",), "phenomenon": ("phenomena",),
    "medium": ("media",), "datum": ("data",), "stimulus": ("stimuli",),
    "index": ("indices",), "child": ("children",), "person": ("people",),
    "man": ("men",), "woman": ("women",), "foot": ("feet",), "tooth": ("teeth",),
}


def _latin_plural(w):
    """규칙적인 라틴계 복수 — 표에 없는 낱말도 받아 준다."""
    for suf, rep in (("is", "es"), ("us", "i"), ("um", "a"), ("on", "a"),
                     ("ex", "ices"), ("ix", "ices")):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            yield w[:-len(suf)] + rep


# `compare A with B` 의 A·B 처럼 **자리를 가리키는 대문자**. 예문에서는 실제
# 목적어가 들어가고 길이가 제각각이라(A = "the view in Compean's picture"),
# 자리표시자 앞의 **실질 낱말까지만** 짚는다.
_PLACEHOLDER = re.compile(r"^(?:[ABONSV]|V-ing|N\d?)$")


def _stems(w):
    w = w.lower()
    out = {w}
    for suf in ("ies", "ied", "ing", "ed", "es", "s", "e"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            out.add(w[:-len(suf)])
    if w.endswith("y") and len(w) - 1 >= 4:
        out.add(w[:-1])
    return {x for x in out if len(x) >= 4}


def _variants(w):
    """규칙적인 철자 변화 — 짧은 낱말도 놓치지 않게 **만들어서** 맞춰 본다.
    have→having(끝 e 탈락) · bury→buried · body→bodies(y→i)."""
    out = set()
    if w.endswith("e") and len(w) >= 3:
        out |= {w[:-1] + "ing", w[:-1] + "ed", w[:-1] + "es"}
    if w.endswith("y") and len(w) >= 3:
        out |= {w[:-1] + "ies", w[:-1] + "ied", w[:-1] + "ier", w[:-1] + "iest"}
    return out


def _same_word(tok, word):
    t, w = tok.lower(), word.lower()
    if w in _POSS:                       # one's → their·his·her …
        return t in _POSS
    if w == "be":
        return t in _BE
    if t == w:
        return True
    if t in _IRREGULAR.get(w, ()):       # overcome→overcame · freeze→frozen
        return True
    if t in _latin_plural(w):            # crisis→crises
        return True
    if any(t == w + suf for suf in _SUFFIX):
        return True
    if t in _variants(w):                # have→having · bury→buried · body→bodies
        return True
    if len(w) >= 3 and any(t == w + w[-1] + suf for suf in ("ed", "ing")):
        return True
    if any(t.startswith(st) for st in _stems(w)):
        return True
    # 하이픈 복합어 — `guilt` 가 `eco-guilt` 안에 들어간 꼴
    if "-" in t and len(w) >= 4:
        return any(_same_word(part, word) for part in t.split("-") if part)
    return False


def _match_from(toks, i, words, slack):
    """`toks[i]` 부터 표제어 낱말들을 **차례대로** 맞춘다.

    사이에 낀 토큰은 통틀어 `slack` 개까지 봐준다. 다 맞으면 마지막 토큰 자리를,
    아니면 None 을 돌려준다.
    """
    j, used, last = i, 0, None
    for k, w in enumerate(words):
        if k == 0:
            if j >= len(toks) or not _same_word(toks[j].group(0), w):
                return None
            last, j = j, j + 1
            continue
        found = None
        for step in range(0, slack - used + 1):
            if j + step >= len(toks):
                break
            if _same_word(toks[j + step].group(0), w):
                found = j + step
                break
        if found is None:
            return None
        used += found - j
        last, j = found, found + 1
    return last


def mark_head(en, head):
    """예문에서 표제어를 `[…]` 로 감싼다 — `ex_en()` 이 그걸 `<em>` 으로 만든다.

    원고가 이미 대괄호로 표시해 온 예문은 그대로 둔다(두 번 감싸지 않는다).
    """
    if not en or not head or "[" in en:
        return en
    words = _RE_WORD.findall(head)
    cut = next((i for i, w in enumerate(words) if _PLACEHOLDER.match(w)), None)
    if cut is not None:                  # `have no choice but to V` → `…but to`
        words = words[:cut]
    if not words:
        return en
    toks = list(_RE_WORD.finditer(en))
    # 구 표제어는 사이에 낱말이 끼어 들어온다 — `be concerned with` 가 예문에서는
    # `were much more concerned with`. 끼어든 토큰을 몇 개까지 봐줄지(slack)는
    # **구일 때만** 연다(한 낱말짜리는 0 — 열어 두면 엉뚱한 짝이 걸린다).
    slack = 3 if len(words) > 1 else 0
    hits = []
    for i in range(len(toks)):
        end = _match_from(toks, i, words, slack)
        if end is not None:
            hits.append((toks[i].start(), toks[end].end()))
    # 겹치면 **짧은 쪽**을 남긴다 — `the French Revolution` 의 첫 낱말 `the` 가
    # 앞쪽 다른 `The` 에 먼저 걸려 "The turn of the French Revolution" 을 통째로
    # 물었다(실측). 짧은 매칭이 곧 제대로 맞은 자리다.
    hits.sort(key=lambda ab: (ab[1] - ab[0], ab[0]))
    chosen = []
    for a, b in hits:
        if all(b <= x or a >= y for x, y in chosen):
            chosen.append((a, b))
    hits = sorted(chosen)
    for a, b in reversed(hits):          # 뒤에서부터 넣어야 자리가 안 밀린다
        en = en[:a] + "[" + en[a:b] + "]" + en[b:]
    return en


def _wcls(w):
    """표제어 길이별 축소 — 라벨 열 폭 대응(vocabook._wcls 와 동일 기준)."""
    return " xlong" if len(w) >= 18 else (" long" if len(w) >= 13 else "")


# 한 면이 낱말 카드에 내주는 높이 — 책 config `options.page_fill_mm` 으로 덮는다.
#
#   판면          23~202mm = 179.0
#   구간 소제목    23~33.2  =  10.2  ← **상자** 높이다(글자 잉크는 24.3부터 —
#                                     잉크로 8.9 를 잡았다가 0.2mm 차이로 카드가
#                                     밀려 한 장짜리 면이 생겼다. 실측으로 정정)
#   카드 자리      33.2~202 = 168.8
#
# 재어 둔 카드 높이에는 **카드 뒤 여백 5.4mm 가 이미 들어 있다**(다음 카드 머리까지
# 재므로). 면의 마지막 카드는 그 여백을 쓰지 않으니 그만큼 후하게 봐 준다.
#   판정: Σ높이 ≤ 168.8 + 5.4 = 174.2 → 여유 1.2mm 를 두고 173
FILL_MM = 171.0
# PART 시작 면은 큰 헤더(마름모+밴드 30mm)가 얹혀 카드 자리가 그만큼 좁다 —
# 실측: 카드가 46.2mm 에서 시작해 자리가 155.8mm(일반 면 168.8). 같은 용량을
# 쓰면 마지막 한 장이 밀려 한 장짜리 면이 생긴다(이의고1 에서 2면).
FIRST_FILL_MM = 160.0


def _chunks(items, cap=PAGE_CAP):
    """낱말 **수**로 고르게 쪼갠다 — 높이 실측이 없을 때의 폴백.

    구간마다 새 면에서 시작하므로, 한 면에 최대한 채우고 넘기면 뒷면이 거의
    백지가 된다(실측: 155mm 가 비었다). 그래도 넘치면 `.vc {break-inside:avoid}`
    가 다음 면으로 밀어 준다 — 다만 그렇게 밀린 자리가 곧 빈 면이 되므로,
    높이를 잴 수 있으면 `_pack()` 을 쓴다.
    """
    n = len(items)
    k = -(-n // cap)
    if k <= 1:
        return [items]
    base, rem = divmod(n, k)
    out, i = [], 0
    for j in range(k):
        size = base + (1 if j < rem else 0)
        out.append(items[i:i + size])
        i += size
    return out


def _need(hs, limit, first=None):
    """높이 `hs` 를 담으면 몇 면이 드는가. `first` 는 첫 면만의 용량."""
    lim = first if first is not None else limit
    n, cur = 1, 0.0
    for h in hs:
        if cur and cur + h > lim + 1e-9:
            n += 1
            cur = h
            lim = limit
        else:
            cur += h
    return n


def _pack(items, heights, fill, first_fill=None):
    """**실측 높이**로 면을 나눈다 — 면 수는 최소로, 그 안에서 가장 고르게.

    낱말 수로 나누면(`_chunks`) 카드가 유난히 큰 낱말이 몰린 구간에서 마지막
    한 장이 면 밖으로 밀려 아래가 통째로 빈다(실측: 199p 중 15면). 카드 높이는
    **면에 어디 놓이든 같은 값**(열 폭이 같다)이라, 1패스에서 재어 두면 그대로 쓸
    수 있다 — 되먹임이 없어 수렴을 걱정하지 않아도 된다.

    면 수 k 는 그리디로 정하고(더 줄일 수 없다), 그 k 를 유지하는 **가장 낮은
    한 면 높이**를 이분법으로 찾아 거기에 맞춰 담는다.
    """
    hs = [float(heights.get(it["no"]) or 0) for it in items]
    if not hs or min(hs) <= 0:
        return None                      # 잰 값이 빠졌다 — 부르는 쪽이 폴백
    ff = first_fill if first_fill is not None else fill
    k = _need(hs, fill, ff)
    lo, hi = max(hs), sum(hs)
    for _ in range(40):                  # 0.01mm 아래로 좁혀진다
        if hi - lo < 0.01:
            break
        mid = (lo + hi) / 2
        if _need(hs, mid, min(mid, ff)) <= k:
            hi = mid
        else:
            lo = mid
    limit = hi
    out, cur, acc = [], [], 0.0
    lim = min(limit, ff)                 # 첫 면만 좁게
    for it, h in zip(items, hs):
        if cur and acc + h > lim + 1e-9:
            out.append(cur)
            cur, acc = [], 0.0
            lim = limit
        cur.append(it)
        acc += h
    if cur:
        out.append(cur)
    # 마지막 면에 한 장만 남으면 앞 면에서 한 장 넘겨 준다 — 구간 끝이 허전해진다.
    # 앞 면이 3장 이상일 때만(2장을 1장으로 만들면 되레 나빠진다), 넘겨도 자리가
    # 남을 때만.
    if len(out) >= 2 and len(out[-1]) == 1 and len(out[-2]) >= 3:
        h = dict(zip((id(x) for x in items), hs))
        tail = sum(h[id(x)] for x in out[-1]) + h[id(out[-2][-1])]
        if tail <= limit + 1e-9:
            out[-1].insert(0, out[-2].pop())
    return out


class Renderer(VocabookRenderer):

    def __init__(self, cfg, heights=None, **kw):
        super(Renderer, self).__init__(cfg, **kw)
        # 1패스에서 잰 낱말 카드 높이 {번호: mm} — 없으면 낱말 수로 나눈다
        self.heights = heights or {}
        self.fill = float((self.o.get("page_fill_mm") or FILL_MM))
        # 예문에 강조가 안 붙은 낱말 — 빌드 끝에 알린다. 조용히 지나가면
        # 검수자가 대신 찾아 준다(실측: 재제작본에서 6곳을 지적받았다).
        self.no_hl = []

    # ── 간지 ────────────────────────────────────────────────────────────
    def sheet(self, kind):
        """앞·뒤 간지 — **표지를 그대로 넣지 않는다.**

        표지 PDF 를 축소해 끼웠더니 표지가 두 번 나오는 꼴이었다(지적). 표지의
        재료(워드마크·UP 3D·분홍 바탕·초록)만 가져와 여백을 크게 둔 간지로 새로
        그린다. 3D 그림은 표지 PDF 에서 뽑아 둔 `assets/up3d.png`.
        """
        o = self.o
        brand = self.brand or "EEGOEEGO"
        line = o.get("cover_line") or ""          # "이의고2 2학기 중간"
        badge = o.get("cover_badge") or ""        # "어휘"
        tag = o.get("cover_tagline") or []        # 영문 두 줄
        by = o.get("author") or ""
        run = self.running("", off=True, foot_off=True)
        if kind == "front":
            return (f'<section class="sheet front s-text" style="page:p-sheet">'
                    f'{run}'
                    f'<p class="wm">{esc(brand)}</p>'
                    f'<img class="art" src="assets/up3d.png" alt="">'
                    f'<div class="rule"></div>'
                    f'<p class="ln">{esc(line)}'
                    + (f'<span class="bdg">{esc(badge)}</span>' if badge else "")
                    + f'</p>'
                    f'<p class="by">{esc(by)}</p></section>')
        return (f'<section class="sheet back s-text" style="page:p-sheet">'
                f'{run}'
                f'<img class="art sm" src="assets/up3d.png" alt="">'
                f'<p class="wm ink">{esc(brand)}</p>'
                + "".join(f'<p class="tag">{esc(t)}</p>' for t in tag)
                + f'<p class="by">{esc(by)}</p></section>')

    def word_card(self, it):
        no = it["no"]
        top = (f'<div class="w-top"><span class="w-num">{no:04d}</span>'
              f'<span class="w-rule"></span></div>')
        o = [f'<article{_refs.mark("#낱말 카드", "vc")}>{top}'
            f'<div class="w-lead">'
            f'<div{_refs.mark("#표제어", "w-word" + _wcls(it["word"]))}>'
            f'{esc(it["word"])}</div>'
            f'<div{_refs.mark("#뜻", "w-mean")}>'
            + (f'<span class="pos">{esc(it["pos"])}</span>' if it["pos"] else "")
            + f'{esc_gap(it["meaning"])}</div></div>']
        for row in it["rows"]:
            lab = row["label"]
            if lab == "예문":
                en, kr = (row["lines"] + [""])[:2]
                marked = mark_head(en, it["word"])
                if en and "[" not in marked:
                    self.no_hl.append((it["no"], it["word"]))
                body = ('<div class="pair">'
                       f'<p class="en">{ex_en(marked)}</p>'
                       + (f'<p class="kr">{ex_kr(kr)}</p>' if kr else "")
                       + "</div>")
                cls = "r-ex"
            elif lab == "유반의어":
                body = "".join(f"<p>{syn_line(x)}</p>" for x in row["lines"])
                cls = "r-syn"
            elif lab == "영영풀이":
                body = "".join(f"<p>{esc_gap(x)}</p>" for x in row["lines"])
                cls = "r-def r-eng"
            else:
                body = "".join(f"<p>{esc_gap(x)}</p>" for x in row["lines"])
                cls = "r-def"
            o.append(f'<div class="w-row {cls}"><div class="lab">{esc(lab)}</div>'
                     f'<div class="val">{body}</div></div>')
        o.append("</article>")
        return "".join(o)

    def kicker(self, group, n, first=False, cont=False):
        """구간 소제목 — 구간마다 **새 면에서 시작**한다(.gsec 의 break-before).
        PART 시작면의 첫 구간만 예외(헤더 바로 아래에 붙는다).
        cont=True 는 한 면에 다 못 담아 넘어온 뒷장(같은 구간)."""
        k = (" first" if first else "") + (" cont" if cont else "")
        # 넘어온 장에는 낱말 수를 다시 적지 않는다(같은 구간이라 중복이고,
        # "이어서" 같은 군더더기는 빼는 편이 낫다는 지적).
        tail = "" if cont else f'<span class="n">{n} words</span>'
        return (f'<div{_refs.mark("#구간 소제목", "gsec" + k)}>'
               f'<span class="t">{esc(group)}</span>{tail}</div>')

    def part_flow(self, key, items):
        cls, page, title = PART_CLASS[key], PART_PAGE[key], PART_TITLE[key]
        n = PART_ORDER.index(key) + 1
        # 측면 라벨은 파트마다 한 칸씩 내려 단다 — 책을 넘길수록 아래로 가서
        # 옆면에서 파트 위치가 보인다(상일보카가 Day 마다 하던 것을 파트 단위로).
        step = (n - 1) * self.idx_step
        out = [f'<section class="{cls} day-open{self._op_cls()}" style="page:{page}">'
              f'{self.running(title, str(n), step)}'
              f'{self.day_head(n, label="PART", title=title)}']
        groups, order = {}, []
        for it in items:
            if it["group"] not in groups:
                groups[it["group"]] = []
                order.append(it["group"])
            groups[it["group"]].append(it)
        for gi, g in enumerate(order):
            lot = groups[g]
            cap = int(self.o.get("page_cap") or PAGE_CAP)
            # 파트의 첫 구간 첫 면 = PART 시작면(큰 헤더가 자리를 먹는다)
            ff = (float(self.o.get("page_first_fill_mm") or FIRST_FILL_MM)
                  if gi == 0 else None)
            lots = (_pack(lot, self.heights, self.fill, ff)
                    if self.heights else None)
            for ci, chunk in enumerate(lots or _chunks(lot, cap)):
                out.append(self.kicker(g, len(lot),
                                       first=(gi == 0 and ci == 0),
                                       cont=(ci > 0)))
                out.extend(self.word_card(it) for it in chunk)
        out.append("</section>")
        return "".join(out)

    # ── 문서 조립 ───────────────────────────────────────────────────────
    def document(self, d):
        items = d["items"]
        if self.sample:
            s = self.o.get("sample") or {}
            part = s.get("part", "text")
            items = [it for it in items if it["part"] == part][:s.get("n", 6)]

        by_part = {k: [it for it in items if it["part"] == k] for k in PART_ORDER}
        body = [self.sheet("front")]
        for k in PART_ORDER:
            if by_part[k]:
                body.append(self.part_flow(k, by_part[k]))
        body.append(self.sheet("back"))

        return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
                f"<title>{esc(self.title)}</title>"
                '<link rel="stylesheet" href="theme.css">'
                '<link rel="stylesheet" href="pages.css">'
                + stage.BOOK_CSS_LINKS + "</head><body>"
                + "".join(body) + "</body></html>")


def write(cfg, data, build_dir, sample=False, heights=None, log=None):
    _refs.index_paths(data, [("items",)])
    r = Renderer(cfg, sample=sample, heights=heights)
    text = r.document(data)
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    _refs.dump(build_dir)
    if log:
        log(f"[렌더] {'견본' if sample else '전권'} "
            f"{len(text) // 1024}KB → {os.path.basename(out)}")
        if r.no_hl:
            head = " · ".join(f"{n}:{w}" for n, w in r.no_hl[:8])
            log(f"[확인] 예문에 표제어 강조가 안 붙은 낱말 {len(r.no_hl)}개 — {head}"
                + (" …" if len(r.no_hl) > 8 else ""))
    return out
