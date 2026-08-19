"""프리미엄북 블랙북 계열 — 교과 단원 문제집(A4, 문제 + 연관어휘 + 해설).

단어장과 대비되는 점이 이 계열의 성격이다:
  · 단어장은 **면 번호를 알아내 덧칠**하는 2패스, 블랙북은 **항목 높이를 재서 배치**하는
    측정 패스. 둘 다 "조판 → PDF 계측 → 다시 조판" 이지만 계측하는 것이 다르다.
  · 해설처럼 여러 면에 걸치는 흐름은 반복 조판으로 수렴시키려 하면 발산한다(10→8→7).
    높이를 재서 펼침면 용량으로 **미리 나누는** 편이 한 번에 끝난다.

빌드 3패스: 문항 높이 측정 → 해설 높이 측정 → 본 조판 → 마감(간지·MEMO·TrimBox).
`--nomeasure` 는 높이 재측정 없이 본 조판만 (원고가 그대로일 때).
"""
import os
import re

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, measure, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.blackbook import assets as assets_mod
from core.render_vivlio.series.blackbook import data as data_mod
from core.render_vivlio.series.blackbook import render as render_mod

RE_SPK = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,22}:\s")


class BlackbookSeries(Series):

    name = "blackbook"
    display = "프리미엄북 블랙북 (교과 단원)"
    theme = "blackbook"

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ② 아트워크 추출(디자인이 바뀔 때만) ──
    def gen_theme(self, cfg, log):
        return assets_mod.build(cfg, log)

    # ── ③ 조판 ──
    def build(self, cfg, log, sample=False, nomeasure=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        m = render_mod.metrics_of(cfg)
        top, bottom = m["body_top"], m["body_bottom"]

        hp = cfg.path("heights.json")
        ap = cfg.path("heights_ans.json")
        if not nomeasure:
            # 문항 — 한 면 1문항으로 조판해 바닥 잉크까지의 높이를 잰다
            nos = [it["no"] for L in d["lessons"] for it in L["problems"]]
            html_p = render_mod.write(cfg, d, build_dir, mode="measure", log=log)
            self._stage(cfg, build_dir, log)
            h = measure.measure(html_p, os.path.join(build_dir, "measure.pdf"),
                                nos, top, bottom, pad=1.0, log=log)
            measure.save(h, hp, log, "문항 높이")
            # 해설 — 한 단 폭·한 면 1항목
            anos = [a["no"] for L in d["lessons"] for a in L["answers"]]
            html_a = render_mod.write(cfg, d, build_dir, mode="measure-ans",
                                      log=log)
            self._stage(cfg, build_dir, log)
            ha = measure.measure(html_a,
                                 os.path.join(build_dir, "measure_ans.pdf"),
                                 anos, top, bottom, pad=0.5, log=log)
            measure.save(ha, ap, log, "해설 높이")

        heights = render_mod.load_heights(hp)
        aheights = render_mod.load_heights(ap)
        html_path = render_mod.write(cfg, d, build_dir, heights=heights,
                                     aheights=aheights, log=log)
        self._stage(cfg, build_dir, log)

        out = cfg.out_pdf("_견본" if sample else "")
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1)}
        spec = cfg.finish_spec()
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _stage(cfg, build_dir, log):
        """서체·테마·자산 배치. 서체가 빠지면 판면이 통째로 달라지므로 필수로 본다."""
        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=True)
        theme = cfg.get("theme") or BlackbookSeries.theme
        stage.stage_theme(build_dir, cfg.resolve(theme)
                          if theme.endswith(".css") else theme, log)
        stage.stage_assets(build_dir,
                           cfg.resolve((cfg.section("assets") or {}).get(
                               "dir", "assets")))

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        """계열 고유 게이트 — 공용(넘침·TrimBox·도련·빈면)은 백엔드가 이미 돌렸다."""
        pdf = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
        d = data_mod.load(cfg)
        texts = probe.page_texts(pdf)
        m = render_mod.metrics_of(cfg)

        # 1) 누락 / 순서 — 조판 순서대로 전수 대조
        seq = self._sequence(d)
        gate.check_sequence(texts, seq, report)
        report.note(f"대조 항목 {len(seq):,}건")

        # 2) 빈칸 유실
        items = []
        for L in d["lessons"]:
            for it in L["problems"]:
                src = ""
                for b in it["blocks"]:
                    if b["t"] in ("passage", "summary", "bogi"):
                        src += " " + _plain(b.get("paras") or b.get("items"))
                    elif b["t"] == "choice":
                        src += " " + _plain(b["body"])
                items.append((it["no"], src, _plain(it["stem"])[:28]))
        gate.check_gaps(items, texts, report)

        # 3) 지문 상자 면 걸침
        gate.check_box_cut(pdf, report, top=m["body_top"] + 2,
                           bottom=m["body_bottom"] - 5)

        # 4) 대화문 바탕 누락 / 5) 해설 펼침면 넘김
        self._check_dialog(pdf, report)
        self._check_answer_spreads(pdf, texts, report)
        return report

    @staticmethod
    def _sequence(d):
        """조판 순서대로의 (설명, 텍스트) — 연관어휘 → 문제 → 해설."""
        seq = []
        for L in d["lessons"]:
            for u in L["vocab"]:
                seq.append((f"{u['label']} 지문", _plain(u["paras"][0])[:60]))
                for w in u["words"]:
                    seq.append((f"{u['label']} {w['word']}",
                                w["word"] + w["mean"]))
            for it in L["problems"]:
                seq.append((f"{it['no']}번 발문", _plain(it["stem"])[:50]))
                for b in it["blocks"]:
                    if b["t"] == "passage":
                        seq.append((f"{it['no']}번 지문",
                                    _plain(b["paras"][0])[:60]))
                    elif b["t"] == "choice":
                        seq.append((f"{it['no']}번 {b['mark']}",
                                    _plain(b["body"])[:45]))
                    elif b["t"] == "summary":
                        seq.append((f"{it['no']}번 요약문",
                                    _plain(b["paras"][0])[:45]))
                    elif b["t"] == "bogi":
                        for k, x in enumerate(b["items"]):
                            seq.append((f"{it['no']}번 보기{k + 1}", _plain(x)[:45]))
                    elif b["t"] == "crit":
                        for k, x in enumerate(b["items"]):
                            seq.append((f"{it['no']}번 채점{k + 1}", _plain(x)[:40]))
        for L in d["lessons"]:
            for a in L["answers"]:
                seq.append((f"해설 {a['no']} 정답", _plain(a["answer"])[:40]))
                if a["trans"]:
                    seq.append((f"해설 {a['no']} 해석", _plain(a["trans"][0])[:50]))
                if a["expl"]:
                    seq.append((f"해설 {a['no']} 본문", _plain(a["expl"][0])[:50]))
        return seq

    @staticmethod
    def _check_dialog(pdf, report, tint=(241, 244, 248)):
        """대화문 줄이 옅은 바탕 밖에 있는가.

        한 줄뿐이면 제목이지 대화문이 아니다 → 지문 상자 안에 화자 줄이 둘 이상일
        때만 본다.
        """
        bad = []
        with probe.open_pdf(pdf) as doc:
            for i, page in enumerate(doc):
                dr = probe.drawings_mm(page)
                rects = [r for r, fill, _c, _w in dr
                         if fill and all(abs(c * 255 - v) < 6
                                         for c, v in zip(fill, tint))]
                boxes = [r for r, _f, color, _w in dr
                         if color and (r[2] - r[0]) > 100]
                spk = []
                for t, (_x0, y0, _x1, y1) in probe.lines_mm(page):
                    t = t.strip()
                    if not RE_SPK.match(t) or len(t) < 12:
                        continue
                    y = (y0 + y1) / 2
                    if not any(b[1] <= y <= b[3] for b in boxes):
                        continue          # 지문 상자 밖(해설 해석 등)은 대상 아님
                    spk.append((y, t))
                if len(spk) < 2:
                    continue
                for y, t in spk:
                    if not any(r[1] - 2 <= y <= r[3] + 2 for r in rects):
                        bad.append((i + 1, t[:26]))
        if bad:
            report.fail(f"대화문 바탕 누락 {len(bad)}줄: {bad[:6]}")
        return bad

    @staticmethod
    def _check_answer_spreads(pdf, texts, report):
        """해설 항목이 오른쪽 면에서 시작해 다음 왼쪽 면으로 넘어갔는가(펼침면 넘김).

        왼쪽 면 → 오른쪽 면(같은 펼침면)으로 이어지는 것은 허용한다.
        ⚠ 항목 번호는 14pt 다. Vivliostyle 출력은 서체 **이름**이 `Type3` 로 바뀌므로
        이름으로 찾으면 조용히 통과한다 — 크기로 판정한다.
        """
        first = next((i for i, t in enumerate(texts)
                      if "해설 |" in t or "해석 |" in t), None)
        if first is None:
            return []
        st, en = {}, {}
        with probe.open_pdf(pdf) as doc:
            for i in range(first, len(doc)):
                for mm in re.finditer(r"§A(\d+)§", texts[i]):
                    en[int(mm.group(1))] = i
                for t, size, _bbox in probe.spans_mm(doc[i]):
                    if size < 12:
                        continue
                    t = t.strip().rstrip(".")
                    if t.isdigit() and int(t) not in st:
                        st[int(t)] = i
        vio = [(n, st[n] + 1, en.get(n, st[n]) + 1) for n in st
               if en.get(n, st[n]) > st[n]
               and (st[n] % 2 == 0 or en[n] > st[n] + 1)]
        if vio:
            report.fail(f"해설 펼침면 넘김 {len(vio)}건: {sorted(vio)[:6]}")
        return vio


def _plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("t", "")
    if x is None:
        return ""
    return "".join(_plain(i) for i in x)
