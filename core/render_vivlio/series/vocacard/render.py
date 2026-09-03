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


def _wcls(w):
    """표제어 길이별 축소 — 라벨 열 폭 대응(vocabook._wcls 와 동일 기준)."""
    return " xlong" if len(w) >= 18 else (" long" if len(w) >= 13 else "")


class Renderer(VocabookRenderer):

    def cover_placeholder(self):
        """vocabook 버전은 `class="cover s-head"` 를 박아 둔다 — 이 계열엔 s-head
        가 없어(s-text/s-supp/s-mock) :root 기본값(첫 섹션)에 우연히 얹혀 있었다.
        실제로 쓰는 첫 섹션 클래스로 바꿔 명시적으로 맞춘다."""
        html = super().cover_placeholder()
        return html.replace('class="cover s-head"', 'class="cover s-text"', 1)

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

    def kicker(self, group):
        return (f'<div{_refs.mark("#구간 소제목", "sec-head")}>'
               f'<span class="sec-badge">&middot;</span>'
               f'<span class="sec-prompt">{esc(group)}</span></div>')

    def part_flow(self, key, items):
        cls, page, title = PART_CLASS[key], PART_PAGE[key], PART_TITLE[key]
        n = PART_ORDER.index(key) + 1
        out = [f'<section class="{cls} day-open{self._op_cls()}" style="page:{page}">'
              f'{self.running(title, str(n), 0)}'
              f'{self.day_head(n, label="PART", title=title, mark=False)}']
        cur = object()
        for it in items:
            if it["group"] != cur:
                cur = it["group"]
                out.append(self.kicker(cur))
            out.append(self.word_card(it))
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
        body = [self.cover_placeholder()]
        for k in PART_ORDER:
            if by_part[k]:
                body.append(self.part_flow(k, by_part[k]))

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
