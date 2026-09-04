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

from core.render_vivlio import refs as _refs
from core.render_vivlio import stage
from core.render_vivlio.series.vocabook.render import (
    Renderer as VocabookRenderer, esc, esc_gap, ex_en, ex_kr, syn,
)
from core.render_vivlio.series.vocacard.data import PART_ORDER, PART_TITLE

PART_CLASS = {"text": "s-text", "supp": "s-supp", "mock": "s-mock"}
PART_PAGE = {"text": "p-text", "supp": "p-supp", "mock": "p-mock"}


PAGE_CAP = 4          # 한 면에 담는 낱말 카드 수(실측: 3장 138mm · 4장 154mm < 가용 170mm)


def _wcls(w):
    """표제어 길이별 축소 — 라벨 열 폭 대응(vocabook._wcls 와 동일 기준)."""
    return " xlong" if len(w) >= 18 else (" long" if len(w) >= 13 else "")


def _chunks(items, cap=PAGE_CAP):
    """구간을 면 단위로 **고르게** 쪼갠다 — 6낱말이면 4+2 가 아니라 3+3.

    구간마다 새 면에서 시작하므로, 한 면에 최대한 채우고 넘기면 뒷면이 거의
    백지가 된다(실측: 155mm 가 비었다). 카드 높이는 들쭉날쭉하지만 3장 묶음이
    최대 138mm, 4장이 154mm 로 가용 170mm 안이라 **낱말 수만으로 나눠도** 된다.
    그래도 넘치면 `.vc { break-inside: avoid }` 가 다음 면으로 밀어 준다.
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


class Renderer(VocabookRenderer):

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
                body = ('<div class="pair">'
                       f'<p class="en">{ex_en(en)}</p>'
                       + (f'<p class="kr">{ex_kr(kr)}</p>' if kr else "")
                       + "</div>")
                cls = "r-ex"
            elif lab == "유반의어":
                body = "".join(f"<p>{syn(x)}</p>" for x in row["lines"])
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
            for ci, chunk in enumerate(_chunks(lot)):
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


def write(cfg, data, build_dir, sample=False, log=None):
    _refs.index_paths(data, [("items",)])
    r = Renderer(cfg, sample=sample)
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
