# -*- coding: utf-8 -*-
"""포켓북 계열 — 지문 DB → A5 포켓북 내지.

다른 계열과 하나가 다르다. **책이 원고가 아니라 지문 DB(코퍼스)에서 만들어진다.**
그래서 `gen_data` 는 원고를 파는 대신 코퍼스에서 지문을 골라 온다.

지면(실측, 148×210 + 도련 3mm):
    짝(왼쪽)  지문번호 배지 · 구문분석 영어 지문 · PICTURE(삽화) · TRANSLATION
    홀(오른쪽) FLOW NOTE · 주제/요약문 · 동반의어 9칸
    (필요하면) 암기 TEST 문제 · 정답

배치는 **삽화 유무**가 가른다(원본이 마스터 A/C/E 로 나눠 놓은 그대로).
지문이 지면보다 길면 **실측 후 축소**한다 — 추정 공식으로는 안 맞는다.
"""
import json
import os

from core.render_vivlio import bleed, cli, measure, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.pocketbook import data as pdata
from core.render_vivlio.series.pocketbook import render as prender
from core.render_vivlio.series.pocketbook import theme as ptheme

FONTS = [
    "NotoSansCJKkr-Regular.otf", "NotoSansCJKkr-Medium.otf",
    "NotoSansCJKkr-Bold.otf", "EliceDXNeolliOTF-Bold.otf",
    "EliceDXNeolliOTF-Medium.otf", "HakgyoansimUndongjangOTFL.otf",
    "KCCDodamdodam_OTF.otf", "JalnanOTF.otf",
]

def _spans(page, lo, hi):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for sp in l["spans"]:
                if lo <= sp["size"] <= hi:
                    yield sp


def _count_size(page, size, tol=0.4):
    """그 크기의 글자 **덩어리** 수. 주석은 7pt 라 본문과 안 겹친다.

    ⚠ 서체 이름으로 세면 안 된다 — Vivliostyle 출력은 이름이 `Type3` 로 바뀌어
      아무것도 못 찾고 조용히 통과한다.
    """
    return sum(1 for _ in _spans(page, size - tol, size + tol))


def _lowest(page, size, tol=0.6):
    """그 크기 글자의 가장 아래 기준선(mm). 없으면 None."""
    ys = [sp["origin"][1] for sp in _spans(page, size - tol, size + tol)]
    return max(ys) / (72 / 25.4) if ys else None


MIN_SCALE = 0.834       # 9pt → 7.5pt. 원본 resolveOverflow 하한과 같다
MIN_LEAD = 14.0         # pt. 원본 하한


class PocketbookSeries(Series):
    name = "pocketbook"
    display = "포켓북"
    theme = ""              # 계열이 CSS 를 생성한다

    style_names = {
        "passage": "구문분석 영어 지문",
        "translation": "한글 해석",
        "flow": "플로우노트",
        "card": "동반의어 카드",
        "badge": "지문번호 배지",
        "memtest": "암기 TEST",
    }

    # ── ① 코퍼스 → data.json ──
    def gen_data(self, cfg, log):
        opt = cfg.section("options") or {}
        keys = opt.get("passages") or []
        corpus = cfg.resolve(opt.get("corpus")
                             or "${STUDIO}/조판/교재/포켓북/_corpus")
        rows, missing = [], []
        for k in keys:
            f = os.path.join(corpus, "%s.json" % k)
            if not os.path.exists(f):
                missing.append(k)
                continue
            with open(f, encoding="utf-8") as fh:
                rows.append(json.load(fh))
        if missing:
            raise ValueError(
                "코퍼스에 없는 지문 %d개: %s\n"
                "  → 분석본에서 먼저 수확하거나 키를 확인할 것"
                % (len(missing), ", ".join(missing[:10])))
        if not rows:
            raise ValueError("수록할 지문이 없다 — options.passages 를 확인할 것")
        out = os.path.join(cfg.build_dir, "data.json")
        os.makedirs(cfg.build_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"passages": rows}, fh, ensure_ascii=False)
        log("■ 지문 %d개" % len(rows))
        return out

    # ── ② 테마 ──
    def gen_theme(self, cfg, log):
        css = ptheme.build_css(cfg.section("palette"),
                               cfg.section("metrics"),
                               (cfg.section("palette") or {}).get("highlight"))
        os.makedirs(cfg.build_dir, exist_ok=True)
        p = os.path.join(cfg.build_dir, "pocket.css")
        with open(p, "w", encoding="utf-8") as f:
            f.write(css)
        return p

    # ── ③ 조판 ──
    def build(self, cfg, log, measure_pass=True, **opts):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        stage.stage_fonts(build_dir, cfg.get("fonts") or FONTS, required=True)
        self._stage_assets(build_dir)
        self.gen_theme(cfg, log)

        data_path = os.path.join(build_dir, "data.json")
        if not os.path.exists(data_path):
            self.gen_data(cfg, log)
        with open(data_path, encoding="utf-8") as f:
            raw = json.load(f)["passages"]

        opt = cfg.section("options") or {}
        rows = pdata.prepare(raw, build_dir,
                             illust_dirs=cfg.resolve(opt.get("illust_dirs") or []),
                             category=opt.get("category", ""))
        M = dict(ptheme.METRICS)
        M.update(cfg.section("metrics") or {})

        if measure_pass:
            self._fit(rows, M, build_dir, log)
            self._fit_memtest(rows, M, build_dir, log)

        html = os.path.join(build_dir, "index.html")
        with open(html, "w", encoding="utf-8") as f:
            f.write(prender.build_html({
                "title": (cfg.book or {}).get("title", "포켓북"),
                "passages": rows, "metrics": cfg.section("metrics"),
                "folio_start": opt.get("folio_start", 2),
                "cover": None}))
        # 검수가 다시 계산하지 않도록 조판에 쓴 값을 그대로 남긴다.
        with open(os.path.join(build_dir, "_rows.json"), "w",
                  encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        out = cfg.out_pdf()
        cli.run_build(html, out, log=log)
        spec = cfg.finish_spec()
        if spec:
            bleed.finish(out, spec, log=log)
        log("■ 산출 %s" % out)
        return out

    @staticmethod
    def _stage_assets(build_dir):
        """계열 자산(플로우노트 모눈)을 build/img 로."""
        import shutil
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "assets", "pocketbook")
        dst = os.path.join(build_dir, "img")
        os.makedirs(dst, exist_ok=True)
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.startswith("."):
                    continue
                d = os.path.join(dst, f)
                if not os.path.exists(d):
                    shutil.copy2(os.path.join(src, f), d)

    # ── 실측 후 맞춤 ──
    def _probe_html(self, rows, M, build_dir, name):
        """한 면에 지문 하나만 — 바닥 잉크를 재기 위한 조판용 HTML."""
        pages = []
        for r in rows:
            st = ""
            if r.get("lead") or r.get("scale"):
                st = ";font-size:%gpt;line-height:%gpt" % (
                    M["passage_size"] * r.get("scale", 1.0),
                    r.get("lead", M["passage_lead"]))
            lead = r.get("lead") or M["passage_lead"]
            pages.append(
                '<section class="pg"><div class="trim">'
                '<div class="passage" style="left:%gmm;top:%s;width:%gmm%s">'
                '%s</div></div></section>'
                % (M["passage"][0], prender.passage_top(M, lead),
                   M["passage"][2], st,
                   prender.runs_html(r["passage_runs"])))
        path = os.path.join(build_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="pocket.css">'
                    '<style>@page{size:%gmm 900mm}.pg{height:900mm}</style>'
                    '</head><body>%s</body></html>'
                    % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
        return path

    def _fit(self, rows, M, build_dir, log):
        """지문이 지면보다 길면 줄인다 — **행간 먼저, 그다음 글자**.

        순서를 지키는 이유가 있다. 행간만 줄이면 줄 수가 그대로라 줄바꿈이 안 변하고,
        글자를 줄이면 줄바꿈이 통째로 달라진다. 원본 InDesign 도 같은 순서로 했다
        (`run.jsx resolveOverflow`: 행간 24→14 하한, 글자 9→7.5 하한).

        추정 공식으로 하면 서체 대체·줄바꿈 때문에 반드시 어긋난다. 한 면에 하나씩
        조판해 **재고**, 그 값으로 정한다.
        """
        top = M["passage"][1]
        lead0 = M["passage_lead"]
        # ⚠ 측정 조판에는 지문면만 넣는다. 전체 목록으로 인덱스를 매기면
        #   암기테스트 면 때문에 **높이가 엉뚱한 지문에 붙는다**.
        rows = [r for r in rows if r.get("kind") != "memtest"]
        keys = [str(i) for i in range(len(rows))]

        html = self._probe_html(rows, M, build_dir, "_measure.html")
        h = measure.measure(html, os.path.join(build_dir, "_measure.pdf"),
                            keys, top, 890.0, log=log)

        PT = 25.4 / 72.0
        need_2nd = []
        for i, r in enumerate(rows):
            avail = ptheme.LAYOUTS[ptheme.layout_for(r)]["passage_h"]
            got = h.get(str(i), 0.0)
            if got <= avail:
                continue
            lines = max(1, int(round(got / (lead0 * PT))))
            lead = avail / lines / PT                    # 이 행간이면 딱 맞는다
            lead = max(MIN_LEAD, (int(lead * 2)) / 2.0)  # 0.5pt 단위로 내린다
            r["lead"] = lead
            if lead <= MIN_LEAD + 1e-6:
                # 행간을 하한까지 줄여도 모자라면 글자를 줄인다 → 줄 수가 변하니
                # 다시 재야 한다.
                r["scale"] = max(MIN_SCALE,
                                 round((avail / (got * lead / lead0)) ** 0.5, 3))
                need_2nd.append(i)

        if need_2nd:
            sub = [rows[i] for i in need_2nd]
            html2 = self._probe_html(sub, M, build_dir, "_measure2.html")
            h2 = measure.measure(html2, os.path.join(build_dir, "_measure2.pdf"),
                                 [str(k) for k in range(len(sub))], top, 890.0,
                                 log=log)
            for k, i in enumerate(need_2nd):
                r = rows[i]
                avail = ptheme.LAYOUTS[ptheme.layout_for(r)]["passage_h"]
                got = h2.get(str(k), 0.0)
                if got > avail:
                    log("  [넘침] 지문 %s — %.1fmm > %.1fmm (글자 %d%%·행간 %gpt)"
                        % (r.get("key") or r.get("label") or i, got, avail,
                           r.get("scale", 1.0) * 100, r.get("lead", lead0)))
                    r["overflow"] = round(got - avail, 1)

        n_lead = sum(1 for r in rows if r.get("lead"))
        n_sc = sum(1 for r in rows if r.get("scale"))
        log("■ 지문 실측 %d개 · 행간 조정 %d · 글자 축소 %d"
            % (len(rows), n_lead, n_sc))

    def _fit_memtest(self, rows, M, build_dir, log):
        """암기 TEST 는 지문 여러 개를 한 면에 담아 자주 넘친다 — 행간부터 줄인다."""
        mts = [r for r in rows if r.get("kind") == "memtest"]
        if not mts:
            return
        box_h = M["memtest"][3] - 6.0
        lead0 = M["memtest_lead"]
        pages = []
        for r in mts:
            pages.append(
                '<section class="pg"><div class="trim">'
                '<div class="memtest" style="left:%gmm;top:%gmm;width:%gmm">'
                '%s</div></div></section>'
                % (M["memtest"][0] + 3.0, M["memtest"][1] + 3.0,
                   M["memtest"][2] - 6.0, prender.runs_html(r["runs"])))
        path = os.path.join(build_dir, "_measure_mt.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="pocket.css">'
                    '<style>@page{size:%gmm 1400mm}.pg{height:1400mm}</style>'
                    '</head><body>%s</body></html>'
                    % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
        h = measure.measure(path, os.path.join(build_dir, "_measure_mt.pdf"),
                            [str(i) for i in range(len(mts))],
                            M["memtest"][1] + 3.0, 1390.0, log=log)
        PT = 25.4 / 72.0
        n = 0
        for i, r in enumerate(mts):
            got = h.get(str(i), 0.0)
            if got <= box_h:
                continue
            lines = max(1, int(round(got / (lead0 * PT))))
            lead = max(11.0, (int(box_h / lines / PT * 2)) / 2.0)
            r["mt_lead"] = lead
            if lead <= 11.0 + 1e-6:
                r["mt_scale"] = max(0.8, round(box_h / (got * lead / lead0), 3))
            n += 1
        log("■ 암기테스트 %d면 · 조정 %d" % (len(mts), n))

    # ── ④ 검수 ──
    def verify(self, cfg, log, report):
        """포켓북 게이트.

        사람이 손대지 않아도 되게 만드는 것은 디자인이 아니라 **게이트**다.
        특히 G-P2 는 사용자가 직접 요구한 것 — "칸이 덜 찬 건 정상이고,
        **한 개도 없는 것만** 목록으로 뽑아라".
        """
        from core.render_vivlio import probe
        rows_path = os.path.join(cfg.build_dir, "_rows.json")
        if not os.path.exists(rows_path):
            return report.fail("검수할 조판 기록이 없다 — 먼저 build 할 것")
        with open(rows_path, encoding="utf-8") as f:
            rows = json.load(f)
        pdf = cfg.out_pdf()
        M = dict(ptheme.METRICS)
        M.update(cfg.section("metrics") or {})
        opt = cfg.section("options") or {}
        # ⚠ `folio_start` 는 **인쇄될 쪽번호**이고, 이 PDF 의 면 수와는 다르다.
        #   표지는 나중에 `finish.inserts` 로 붙으므로 지금 PDF 에는 없다.
        start = 1 if opt.get("cover") else 0

        with probe.open_pdf(pdf) as doc:
            n_pages = len(doc)
            per = [1 if r.get("kind") == "memtest" else 2 for r in rows]
            want = start + sum(per)
            if n_pages != want:
                report.fail("G-P1 면 수 %d ≠ 예상 %d (지문 %d개)"
                            % (n_pages, want, len(rows)))

            # G-P3 주석 보존 · G-P6 넘침
            idx, lost, over = start, [], []
            for r, step in zip(rows, per):
                if idx >= n_pages:
                    break
                if r.get("kind") == "memtest":
                    idx += step
                    continue
                page = doc[idx]
                want_ruby = sum(1 for x in r["passage_runs"] if x.get("ruby"))
                got_ruby = _count_size(page, M["anno_size"])
                if want_ruby and got_ruby < want_ruby:
                    lost.append((r.get("key") or r.get("label"),
                                 want_ruby, got_ruby))
                lay = ptheme.LAYOUTS[ptheme.layout_for(r)]
                bottom = M["passage"][1] + lay["passage_h"]
                low = _lowest(page, M["passage_size"] * r.get("scale", 1.0))
                if low and low > bottom + 0.5:
                    over.append((r.get("key") or r.get("label"),
                                 round(low - bottom, 1)))
                idx += step

            if lost:
                report.fail("G-P3 구문분석 주석 유실 %d지문 — %s"
                            % (len(lost), ", ".join(
                                "%s(%d→%d)" % x for x in lost[:5])))
            if over:
                report.fail("G-P6 지문 넘침 %d지문 — %s"
                            % (len(over), ", ".join(
                                "%s +%.1fmm" % x for x in over[:5])))

        # G-P2 0개 항목 — 막지 않고 목록으로
        pas = [r for r in rows if r.get("kind") != "memtest"]
        no_syn = [r.get("key") or r.get("label") or "?" for r in pas
                  if not r.get("synonyms")]
        no_flow = [r.get("key") or r.get("label") or "?" for r in pas
                   if not r.get("flownote")]
        no_ill = [r.get("key") or r.get("label") or "?" for r in pas
                  if not r.get("illust")]
        if no_syn:
            report.warn("G-P2 동반의어 0개 %d지문 — %s"
                        % (len(no_syn), ", ".join(no_syn[:12])))
        if no_flow:
            report.warn("G-P2 플로우노트 0개 %d지문 — %s"
                        % (len(no_flow), ", ".join(no_flow[:12])))
        if no_ill:
            report.note("G-P5 삽화 없음 %d지문(모의고사만 필요)" % len(no_ill))
        self._write_empty_report(cfg, no_syn, no_flow)
        report.note("지문 %d개 · 암기테스트 %d면 · 총 %d면"
                    % (len(pas), len(rows) - len(pas), n_pages))
        return report

    @staticmethod
    def _write_empty_report(cfg, no_syn, no_flow):
        p = os.path.join(cfg.build_dir, "빈항목.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 채워야 할 지문\n\n")
            f.write("칸이 덜 찬 것은 정상이다. **하나도 없는 것만** 적는다.\n\n")
            f.write("## 동반의어 0개 (%d)\n\n" % len(no_syn))
            for k in no_syn:
                f.write("- %s\n" % k)
            f.write("\n## 플로우노트 0개 (%d)\n\n" % len(no_flow))
            for k in no_flow:
                f.write("- %s\n" % k)
        return p
