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
import shutil

from core.render_vivlio import bleed, cli, measure, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.pocketbook import data as pdata
from core.render_vivlio.series.pocketbook import memtest as pmemtest
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


def _text(runs):
    return "".join(r["t"] for r in runs)


def _bag(s):
    import collections
    import re as _re
    return collections.Counter(
        _re.sub(r"[^0-9A-Za-z가-힣]", "", s).lower())


def _page_bag(page, size, tol=0.6):
    return _bag("".join(sp["text"] for sp in _spans(page, size - tol,
                                                   size + tol)))


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
        """코퍼스에서 수록 지문을 고른다.

        키를 손으로 나열해도 되고(`options.passages`), 학교·학기로 골라도 된다
        (`options.school`·`options.term`). 뒤쪽이 실제 작업에 가깝다 —
        "상일2 26-2 중간 포켓북" 이라고 말하지 지문 키를 외우지 않는다.
        """
        opt = cfg.section("options") or {}
        corpus = cfg.resolve(opt.get("corpus")
                             or "${STUDIO}/조판/교재/포켓북/_corpus")
        keys = list(opt.get("passages") or [])
        if not keys and (opt.get("school") or opt.get("term")
                         or opt.get("units")):
            keys = self._pick(corpus, opt, log)
        rows, missing = [], []
        rows += self._from_analysis(cfg, opt, log)
        for k in keys:
            # 인덱스 키(`강동1:25-2:3과-04`)와 파일명(`강동1__25-2__3과-04.json`)이
            # 다르다 — 인덱스가 알려 주는 파일명을 쓴다.
            f = k if k.endswith(".json") else os.path.join(corpus, "%s.json" % k)
            if not os.path.isabs(f):
                f = os.path.join(corpus, os.path.basename(f))
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
            raise ValueError(
                "수록할 지문이 없다 — options 에 passages·school/term·analysis "
                "중 하나는 있어야 한다")
        self._apply_manuscript(cfg, opt, rows, log)
        rows = self._apply_memtest(cfg, opt, rows, log)
        out = os.path.join(cfg.build_dir, "data.json")
        os.makedirs(cfg.build_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"passages": rows}, fh, ensure_ascii=False)
        log("■ 지문 %d개" % len(rows))
        return out

    # ── 새 지문: 분석본에서 ──
    @staticmethod
    def _tools():
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(here))))
        t = os.path.join(repo, "tools", "pocket_harvest")
        if t not in sys.path:
            sys.path.insert(0, t)
        return t

    def _from_analysis(self, cfg, opt, log):
        """`options.analysis` 의 분석본 IDML → 새 지문.

        코퍼스에 없는 **이번 학기 신규 지문**이 들어오는 자리다. 분석본에는
        플로우노트·동반의어가 없으므로 비어서 들어오고, 원고(hwpx)가 채운다.
        둘 다 없으면 G-P2 가 목록으로 알려 준다.
        """
        srcs = cfg.resolve(opt.get("analysis") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        files = []
        for sfile in srcs:
            if os.path.isdir(sfile):
                for root, _d, fs in os.walk(sfile):
                    files += [os.path.join(root, f) for f in sorted(fs)
                              if f.lower().endswith(".idml")]
            elif os.path.exists(sfile):
                files.append(sfile)
        if not files:
            return []
        self._tools()
        import analysis
        out = []
        for f in files:
            got = analysis.read_book(f)
            out += got
            log("■ 분석본 %s — 지문 %d" % (os.path.basename(f), len(got)))
        return out

    # ── 플로우노트·동반의어: 교재팀 원고에서 ──
    def _apply_manuscript(self, cfg, opt, rows, log):
        """`options.manuscript` 의 hwpx → 지문에 플로우·주제·동반의어를 얹는다.

        원고 키(`24-9 21번 Flow`·`명일2 4과 본문2`)와 지문 키를 **느슨하게** 맞춘다
        — 표기가 학교마다 다르므로 숫자만 남긴 형태로도 한 번 더 본다.
        """
        srcs = cfg.resolve(opt.get("manuscript") or [])
        if isinstance(srcs, str):
            srcs = [srcs]
        files = [f for f in srcs if os.path.exists(f)
                 and f.lower().endswith((".hwpx", ".hwp"))]
        for d in [x for x in srcs if os.path.isdir(x)]:
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.lower().endswith(".hwpx")]
        if not files:
            return
        self._tools()
        import manuscript
        frags = []
        for f in files:
            got = manuscript.parse(f)
            frags += got
            log("■ 원고 %s — 블록 %d" % (os.path.basename(f), len(got)))

        def norm(x):
            import re as _re
            return _re.sub(r"[^0-9a-z가-힣]", "", (x or "").lower())

        def digits(x):
            import re as _re
            return "".join(_re.findall(r"\d", x or ""))

        by_key, by_num = {}, {}
        for fr in frags:
            k = norm(fr["key_raw"])
            by_key[k] = fr
            dn = digits(fr["key_raw"])
            if dn:
                by_num.setdefault(dn, fr)
        used, hit = set(), 0
        for r in rows:
            cands = [r.get("key"), r.get("pno"), r.get("label")]
            fr = None
            for c in cands:
                fr = by_key.get(norm(c)) or fr
            if fr is None:
                for c in cands:
                    dn = digits(c)
                    if dn and dn in by_num:
                        fr = by_num[dn]
                        break
            if fr is None:
                continue
            used.add(id(fr))
            hit += 1
            if fr.get("flow") and not r.get("flownote"):
                r["flownote"] = fr["flow"]
            if fr.get("synonyms") and not r.get("synonyms"):
                r["synonyms"] = fr["synonyms"]
            if fr.get("topic") and not r.get("topic"):
                r["topic"] = fr["topic"]
            if fr.get("summary") and not r.get("summary"):
                r["summary"] = fr["summary"]
        orphan = [f["key_raw"] for f in frags if id(f) not in used]
        log("■ 원고 %d블록 중 %d개가 지문에 붙었다" % (len(frags), hit))
        if orphan:
            # 조용히 버리면 원고를 쓴 사람이 영영 모른다.
            log("  [원고 미사용] %d개 — %s"
                % (len(orphan), ", ".join(orphan[:8])))

    @staticmethod
    def _pick(corpus, opt, log):
        """학교·학기(·단원)로 코퍼스에서 지문 키를 고른다. 순서는 인덱스 순."""
        idx_path = os.path.join(corpus, "_index.json")
        if not os.path.exists(idx_path):
            raise ValueError("코퍼스 인덱스가 없다: %s\n"
                             "  → tools/pocket_harvest/corpus.py build" % idx_path)
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        rows = idx.get("passages") if isinstance(idx, dict) else idx
        if isinstance(rows, dict):
            rows = [dict(v, key=k) for k, v in rows.items()]
        rows.sort(key=lambda r: (r.get("where") or [{}])[0].get("pages", ""))
        school = opt.get("school")
        term = opt.get("term")
        units = set(opt.get("units") or [])
        out = []
        for r in rows:
            if school and r.get("school") != school:
                continue
            if term and r.get("term") != term:
                continue
            if units and r.get("unit") not in units:
                continue
            out.append(r.get("file") or (r["key"] + ".json"))
        if not out:
            raise ValueError(
                "고른 지문이 없다 (school=%s term=%s units=%s)"
                % (school, term, sorted(units)))
        log("■ 코퍼스에서 %d지문 선택" % len(out))
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
            self._fit_right(rows, M, build_dir, log)

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
        # 마감(표지 삽입) 전 상태를 남긴다 — 검수는 **우리가 조판한 면만** 본다.
        # 표지를 끼우면 면 번호가 밀려 지문면 검사가 통째로 어긋난다(그렇게 됐다).
        body_pdf = os.path.join(build_dir, "_body.pdf")
        shutil.copyfile(out, body_pdf)
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

    def _fit_right(self, rows, M, build_dir, log):
        """오른쪽 면 — 플로우노트와 주제/요약이 상자를 넘지 않게 줄인다.

        둘 다 상자가 작고(41mm · 23mm) 원고 길이가 들쭉날쭉해서 자주 넘친다.
        지문과 달리 **줄 수가 적어** 행간만 줄이면 티가 나므로 글자와 함께 줄인다.
        """
        pas = [r for r in rows if r.get("kind") != "memtest"]
        if not pas:
            return
        fl, tb = M["flow"], M["topic"]
        for kind, box_h, mk in (("flow", fl[3], self._flow_probe),
                                ("topic", tb[3], self._topic_probe)):
            pages = [mk(r, M) for r in pas]
            path = os.path.join(build_dir, "_measure_%s.html" % kind)
            with open(path, "w", encoding="utf-8") as f:
                f.write('<!doctype html><html><head><meta charset="utf-8">'
                        '<link rel="stylesheet" href="pocket.css">'
                        '<style>@page{size:%gmm 700mm}.pg{height:700mm}</style>'
                        '</head><body>%s</body></html>'
                        % (M["page_w"] + 2 * M["bleed"], "".join(pages)))
            h = measure.measure(path,
                                os.path.join(build_dir, "_measure_%s.pdf" % kind),
                                [str(i) for i in range(len(pas))], 10.0, 690.0,
                                log=log)
            n = 0
            for i, r in enumerate(pas):
                got = h.get(str(i), 0.0)
                if got > box_h - 1.0:
                    r[kind + "_scale"] = max(0.72,
                                             round((box_h - 1.0) / got, 3))
                    n += 1
            log("■ %s 조정 %d/%d" % ("플로우노트" if kind == "flow" else "주제/요약",
                                     n, len(pas)))

    @staticmethod
    def _flow_probe(r, M):
        rows = []
        for line in r.get("flownote") or []:
            cls = ' class="arrow"' if line.lstrip().startswith(("→", "⇒", "▶")) else ""
            rows.append("<p%s>%s</p>" % (cls, prender.ESC(line)))
        return ('<section class="pg"><div class="trim">'
                '<div class="flow" style="left:%gmm;top:10mm;width:%gmm;'
                'background:none">%s</div></div></section>'
                % (M["flow"][0], M["flow"][2], "".join(rows)))

    @staticmethod
    def _topic_probe(r, M):
        tt = ""
        if r.get("topic"):
            tt += "<p>%s</p>" % prender.ESC(r["topic"])
        if r.get("summary"):
            tt += "<p>%s</p>" % prender.ESC(r["summary"])
        return ('<section class="pg"><div class="trim">'
                '<div class="topictext" style="left:%gmm;top:10mm;width:%gmm">'
                '%s</div></div></section>'
                % (M["topic_text_x"],
                   M["topic"][0] + M["topic"][2] - M["topic_text_x"] - 2.0, tt))

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
        body = os.path.join(cfg.build_dir, "_body.pdf")
        pdf = body if os.path.exists(body) else cfg.out_pdf()
        M = dict(ptheme.METRICS)
        M.update(cfg.section("metrics") or {})
        opt = cfg.section("options") or {}
        start = 0        # `_body.pdf` 는 표지 전이라 첫 면이 곧 첫 지문면이다

        with probe.open_pdf(pdf) as doc:
            n_pages = len(doc)
            per = [1 if r.get("kind") == "memtest" else 2 for r in rows]
            want = start + sum(per)
            if n_pages != want:
                report.fail("G-P1 면 수 %d ≠ 예상 %d (지문 %d개)"
                            % (n_pages, want, len(rows)))

            # G-P3 주석 보존 · G-P6 넘침
            idx, lost, over, wrong = start, [], [], []
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
                # G-P7 — 원고 글자가 지면에 다 있는가.
                #   순서로 비교하면 안 된다: 루비 낱말이 inline-block 이라 PDF
                #   추출 순서가 뒤섞이고, 인접 span 이 붙어 낱말이 엉킨다.
                #   **글자 개수**로 보면 순서·붙임과 무관하게 유실만 잡힌다.
                sc = r.get("scale", 1.0)
                miss = _bag(_text(r["passage_runs"])) - _page_bag(
                    page, M["passage_size"] * sc)
                if sum(miss.values()):
                    wrong.append((r.get("key") or r.get("label"),
                                  sum(miss.values())))
                lay = ptheme.LAYOUTS[ptheme.layout_for(r)]
                bottom = M["passage"][1] + lay["passage_h"]
                low = _lowest(page, M["passage_size"] * r.get("scale", 1.0))
                if low and low > bottom + 0.5:
                    over.append((r.get("key") or r.get("label"),
                                 round(low - bottom, 1)))
                idx += step

            if wrong:
                report.fail("G-P7 원문 글자 유실 %d지문 — %s"
                            % (len(wrong), ", ".join(
                                "%s(%d자)" % x for x in wrong[:5])))
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
        report.note("지문 %d개 · 암기테스트 %d면 · 본문 %d면"
                    % (len(pas), len(rows) - len(pas), n_pages))
        final = cfg.out_pdf()
        if os.path.exists(final) and final != pdf:
            from core.render_vivlio import probe as _pb
            n_final = _pb.page_count(final)
            spec = cfg.finish_spec()
            add = len(spec.get("inserts") or []) + len(spec.get("append") or [])
            if n_final is not None and n_final < n_pages:
                report.fail("G-P1 최종 %d면 < 본문 %d면" % (n_final, n_pages))
            else:
                report.note("표지·마감 포함 최종 %d면 (추가 %d)"
                            % (n_final, (n_final or 0) - n_pages))
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
