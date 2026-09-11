"""한끝 계열 — 한영고 특강 교재(한단끝·한문끝·한서끝) 중 **문제형** 내지.

첫 책 = 한서끝(한영고 서술형 끝, 26-2-중간 한영1). 원고는 docx — 확정본은 작성 중이라
data.py 는 초안 구조를 읽는 잠정 파서다.

빌드: 덩어리 높이 측정 → 배치(한 면 위·아래 두 칸, 긴 덩어리는 한 면 통째) → 조판 →
      면 패리티 확인(파트 간지 왼쪽 면 시작 · 총 면수 4의 배수) → TrimBox.
패리티는 **예측**(배치에서 면 수를 센다)으로 먼저 맞추고, 조판 결과의 표식 면 번호로
확인해 어긋나면 MEMO 면 수를 고쳐 한 번 더 굽는다(한 면을 넘는 덩어리가 있을 때만 난다).
"""
import json
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, measure, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.hankkeut import assets as assets_mod
from core.render_vivlio.series.hankkeut import data as data_mod
from core.render_vivlio.series.hankkeut import palette
from core.render_vivlio.series.hankkeut import render as render_mod

RE_SPECIAL = re.compile(r'§(FRONT|BACK|DL\d+|DR\d+)§')


class HankkeutSeries(Series):
    name = "hankkeut"
    display = "한끝 계열 (한영고 특강 문제형)"
    theme = "hankkeut"

    # 미리보기는 재 둔 heights.json 을 쓴다(측정은 PDF 를 한 번 더 굽는 무거운 패스)
    render_opts = {"nomeasure": True}
    SAMPLE_UNITS = 6

    style_names = {
        "unit": "덩어리(지문+문항)", "uhead": "덩어리 머리", "rng": "세트 범위 칩",
        "uh": "세트 발문", "src": "출처", "q": "문항", "stem": "발문", "no": "문항 번호",
        "tag": "시험 표기", "note": "안내", "pbox": "지문 상자", "sn": "지문 문장 번호",
        "cond": "조건 상자", "summary": "요약문 상자", "pieces": "배열 조각 표",
        "pn": "조각 번호", "ans": "답란", "alab": "답 칩", "ul": "답 밑줄",
        "slot": "칸", "sep": "칸 사이 괘선",
    }

    # ── 인쇄 원고(CMYK) — 공통 K 단계를 K 단색으로. 유채색은 ICC.
    def print_defaults(self, cfg):
        from core.render_vivlio import prepress
        return prepress.default_print(gray_map=palette.gray_map())

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    def gen_theme(self, cfg, log):
        return assets_mod.build(cfg, log)

    def knobs(self, cfg):
        K = knobs.Knob
        mm = lambda key, label, default, lo, hi, affects: K(   # noqa: E731
            "metrics." + key, "mm", label, default=default, min=lo, max=hi,
            step=0.5, unit="mm", affects=affects, group="치수")
        return [mm("slot", "반 면 칸 높이", 119.5, 90, 124, "위·아래 칸"),
                mm("gap", "두 칸 사이", 7.0, 3, 15, "가운데 괘선 자리")]

    # ── 조판 ──
    @classmethod
    def _sample(cls, d):
        if not d['parts']:
            return d
        P = dict(d['parts'][0])
        P['units'] = P['units'][:cls.SAMPLE_UNITS]
        return dict(d, parts=[P])

    def build(self, cfg, log, sample=False, nomeasure=False, **_):
        bd = cfg.build_dir
        os.makedirs(bd, exist_ok=True)
        if assets_mod.missing(cfg):
            assets_mod.build(cfg, log)
        d = data_mod.load(cfg)
        if sample:
            d = self._sample(d)
        m = render_mod.metrics_of(cfg)
        sfx = "_견본" if sample else ""
        hp = cfg.path(f"heights{sfx}.json")
        if not nomeasure or not os.path.exists(hp):
            html_m, _ = render_mod.write(cfg, d, bd, mode="measure", log=log)
            self._stage(cfg, bd, log)
            keys = [u["id"] for P in d["parts"] for u in P["units"]]
            h = measure.measure(html_m, os.path.join(bd, "measure.pdf"), keys,
                                m["body_top"], render_mod.MEASURE_H - 4, pad=0.6, log=log)
            measure.save(h, hp, log, "덩어리 높이")
        heights = measure.load(hp) or {}

        out = cfg.out_pdf(sfx)
        memo, secs = None, 0.0
        for _try in range(3):
            html_p, memo = render_mod.write(cfg, d, bd, heights=heights, memo=memo, log=log)
            self._stage(cfg, bd, log)
            secs = cli.run_build(html_p, out, log=log, extra=["-f", "pdf"])
            fix = self._parity(out, d, memo)
            if fix is None:
                break
            log(f"[패리티] 예측과 달라 MEMO 면 조정 → 앞{fix['before']} 끝{fix['end']}")
            memo = fix
        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")
        bleed_mod.finish(out, {"trim": {"bleed": m["bleed"]}}, log)
        return {"pdf": out, "pages": pages, "seconds": round(secs, 1)}

    @staticmethod
    def _parity(pdf, d, memo):
        """간지가 왼쪽 면에서 시작하고 끝이 4의 배수인가 — 아니면 고친 MEMO 계획."""
        texts = probe.page_texts(pdf)

        def page_of(mark):
            return next((i + 1 for i, t in enumerate(texts) if mark in t), None)

        n = len(d['parts'])
        dl = [page_of(f'§DL{k + 1}§') for k in range(n)]
        back = page_of('§BACK§')
        if None in dl or back is None:
            raise RuntimeError(f"간지 표식을 못 찾았다: DL={dl} BACK={back}")
        if all(p % 2 == 0 for p in dl) and back == len(texts) and back % 4 == 0:
            return None
        counts = []
        for k in range(n):
            start = dl[k] + 2
            end = (dl[k + 1] - memo['before'][k + 1]) if k + 1 < n else back - memo['end']
            counts.append(end - start)
        return render_mod.memo_plan(counts)

    @staticmethod
    def _stage(cfg, bd, log):
        """서체·테마·자산 배치. 서체가 빠지면 판면이 통째로 달라지므로 필수로 본다."""
        stage.stage_fonts(bd, [f["file"] for f in cfg.get("fonts") or []], log, required=True)
        theme = cfg.get("theme") or HankkeutSeries.theme
        stage.stage_theme(bd, cfg.resolve(theme) if theme.endswith(".css") else theme, log)
        stage.stage_assets(bd, cfg.resolve((cfg.section("assets") or {}).get("dir", "assets")))
        knobs.write(cfg, HankkeutSeries(), bd)
        stage.stage_overrides(cfg, bd)
        stage.stage_book_assets(cfg, bd)

    # ── 계열 검수 ──
    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf((cfg.section("verify") or {}).get("suffix", ""))
        d = data_mod.load(cfg)
        m = render_mod.metrics_of(cfg)
        texts = probe.page_texts(pdf)

        # 1) 누락·순서 — 되풀이되는 발문 말고 **덩어리마다 다른 글**(지문 첫머리·요약문·조각)로
        seq = self._sequence(d)
        gate.check_sequence(texts, seq, report)
        report.note(f"대조 항목 {len(seq):,}건")

        # 2) 칸 넘침 — 덩어리 끝 표식이 제 칸 안에 있는가
        lp = os.path.join(cfg.build_dir, "layout.json")
        if os.path.exists(lp):
            with open(lp, encoding="utf-8") as f:
                self._check_slots(pdf, json.load(f), m, report)

        # 3) 면 구성 — 앞·뒤 간지, 파트 간지 펼침면, 4의 배수, 빈 면
        self._check_pages(texts, d, report)

        # 4) 판면 넘침 — 간지·앞뒤 면은 판면이 없다
        special = [i + 1 for i, t in enumerate(texts) if RE_SPECIAL.search(t)]
        frame = {"inner": m["bleed"] + m["outer"], "outer": m["bleed"] + m["inner"],
                 "width": m["text_w"], "top": m["body_top"],
                 "bottom": m["bleed"] + m["H"] - m["bottom"]}
        gate.check_overflow(pdf, frame, report, skip_pages=special)
        return report

    @staticmethod
    def _sequence(d):
        def clean(s):
            s = re.sub(r'\[\((\d+)\)\]', r'(\1)', s)
            s = re.sub(r'_+', ' ', s)
            return re.sub(r'\s+', ' ', s).strip()
        seq = []
        for P in d['parts']:
            seq.append((f"PART {P['no']} 제목", P['title']))
            for u in P['units']:
                if u['passage']:
                    seq.append((f"{u['id']} 지문", clean(data_mod.plain(u['passage'][0]))[:45]))
                for q in u['items']:
                    for b in q['blocks']:
                        if b['t'] == 'passage':
                            seq.append((f"{q['no']}번 지문",
                                        clean(data_mod.plain(b['paras'][0]))[:45]))
                        elif b['t'] == 'summary':
                            s = clean(data_mod.plain(b['paras'][0]))
                            seq.append((f"{q['no']}번 요약문", s.split('(')[0][:35]))
                        elif b['t'] == 'pieces':
                            for c in b['cells']:
                                if len(c['text']) >= 12:
                                    seq.append((f"{q['no']}번 조각 {c['n']}", c['text'][:30]))
        return [(k, v) for k, v in seq if v]

    @staticmethod
    def _check_slots(pdf, lay, m, report):
        where = {}
        for pages in lay['layout'].values():
            for kind, slots in pages:
                for pos, uid in slots:
                    where[uid] = (kind, pos)
        top_lim = m['body_top'] + m['slot'] + 0.5
        bot_lim = m['bleed'] + m['H'] - m['bottom'] + 0.5
        bad, seen = [], set()
        with probe.open_pdf(pdf) as doc:
            for i, page in enumerate(doc):
                for t, (_x0, _y0, _x1, y1) in probe.lines_mm(page):
                    for mm in re.finditer(r'§E(u\d+)§', t):
                        uid = mm.group(1)
                        seen.add(uid)
                        kind, pos = where.get(uid, ('?', '?'))
                        if kind == 'over':
                            continue
                        lim = top_lim if pos == 'top' else bot_lim
                        if y1 > lim:
                            bad.append((i + 1, uid, pos, round(y1, 1)))
        miss = sorted(set(where) - seen)
        if miss:
            report.fail(f"덩어리 표식 없음 {len(miss)}건: {miss[:8]}")
        if bad:
            report.fail(f"칸 넘침 {len(bad)}건: {bad[:8]}")
        over = [u for u, (k, _p) in where.items() if k == 'over']
        if over:
            report.warn(f"한 면을 넘는 덩어리 {len(over)}건(다음 면으로 흐름): {over[:8]}")
        kinds = [k for k, _p in where.values()]
        report.note(f"칸 배치 {len(where)}덩어리 · 반 면 {kinds.count('half')} · "
                    f"한 면 {kinds.count('full')}")

    @staticmethod
    def _check_pages(texts, d, report):
        n = len(texts)
        errs = []
        if n % 4:
            errs.append(f"총 {n}면 — 4의 배수가 아니다")
        if '§FRONT§' not in texts[0]:
            errs.append("첫 면이 앞 간지가 아니다")
        if '§BACK§' not in texts[-1] or n % 2:
            errs.append("마지막 면(짝수)이 뒤 간지가 아니다")
        for k in range(len(d['parts'])):
            p = next((i + 1 for i, t in enumerate(texts) if f'§DL{k + 1}§' in t), None)
            if p is None or p % 2:
                errs.append(f"PART {k + 1} 간지가 왼쪽 면에서 시작하지 않는다({p}면)")
            elif p >= n or f'§DR{k + 1}§' not in texts[p]:
                errs.append(f"PART {k + 1} 간지 펼침면이 깨졌다")
        blank = [i + 1 for i, t in enumerate(texts) if not t.strip()]
        if blank:
            errs.append(f"빈 면 {blank[:8]}")
        for e in errs:
            report.fail(e)
        report.note(f"면 구성 {n}면 (4의 배수 {'O' if n % 4 == 0 else 'X'})")
