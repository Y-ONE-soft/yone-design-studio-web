"""파이널 직전보충 계열 — 시험 직전 보충 교재(A4, Vol1/Vol2).

한 권(폴더 하나) = 한 Vol 이다. 두 권은 **같은 원고**(파이널 엔진이 만든
`content.json`)를 보고, `options.vol` 이 어느 쪽을 조판할지 정한다.

지면 성격은 화이트북과 같은 **고정 칸**이다. 다만 화이트북은 칸을 넘기면
결함으로 잡고 끝내지만, 파이널은 지문 길이를 고를 수 없어서(시험범위가 정한다)
**넘치는 지문만 활자를 줄인다** — 인디자인 경로가 런타임에 하던 일이다.
줄인 것은 전부 리포트에 남긴다.

빌드: (선택) 지문 높이 측정 → 축소율 계산 → 본 조판 → 마감(간지·TrimBox).
`--nomeasure` 는 측정 없이 본 조판만(미리보기).
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, measure, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.final import data as data_mod
from core.render_vivlio.series.final import render as render_mod
from core.render_vivlio.series.final import verify as verify_mod


class FinalSeries(Series):

    name = "final"
    display = "파이널 직전보충 (FINAL STEP)"
    theme = "final"

    # 미리보기는 측정을 건너뛴다 — 축소는 넘치는 지문에만 걸리고 느리다.
    render_opts = {"nomeasure": True}

    style_names = {
        "blk": "지문 한 칸", "given": "주어진 문장 상자", "it": "배열 항목",
        "prompt": "발문", "ansline": "답란", "vp": "어휘 지문",
        "vsum": "내용요약", "body": "어법 본문", "wkor": "영작 한글",
        "wcho": "영작 보기",
    }

    # ── ① 원고 ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ③ 조판 ──
    def vol_of(self, cfg):
        return int((cfg.section("options") or {}).get("vol", 1))

    def build(self, cfg, log, sample=False, nomeasure=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        vol = self.vol_of(cfg)
        m = render_mod.metrics_of(cfg)
        if sample:
            d = self._sample(d, vol)
            log(f"[견본] 섹션마다 지문 4개")

        fits, heights = {}, {}
        if not nomeasure:
            heights = self._measure(cfg, d, vol, build_dir, m, log)
            fits = self._fits(d, vol, heights, m, log)
            self._save_fit_report(cfg, d, vol, heights, fits, m)

        html_path = render_mod.write(cfg, d, vol, build_dir, fits=fits, log=log)
        self._stage(cfg, build_dir, log)
        out = cfg.out_pdf(self._suffix(cfg, sample))
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1),
               "fits": len(fits)}
        spec = self._finish_spec(cfg)
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def series_asset(name=""):
        """`core/render_vivlio/assets/final/…` — 계열 공용 자산."""
        here = os.path.dirname(os.path.abspath(__file__))        # …/series/final
        root = os.path.dirname(os.path.dirname(here))            # …/render_vivlio
        return os.path.join(root, "assets", "final", name)

    def _finish_spec(self, cfg):
        """마감 — 크레딧 면은 **계열 자산**이다(모든 학교가 같은 면을 쓴다).

        책 config 에 적게 하면 학교 수만큼 같은 경로가 복사된다. 책이 직접
        `finish.append` 를 적었으면 그것을 존중한다.
        """
        spec = cfg.finish_spec()
        credits = self.series_asset("credits.pdf")
        if not spec.get("append") and os.path.exists(credits):
            spec["append"] = [{"pdf": credits, "page": 0}]
        spec.setdefault("trim", {"bleed": cfg.page["bleed"] or 3})
        return spec

    def _suffix(self, cfg, sample=False):
        o = cfg.section("output") or {}
        return (o.get("suffix") or f"(Vol{self.vol_of(cfg)})_내지") + (
            "_견본" if sample else "")

    @staticmethod
    def _sample(d, vol, n=4):
        import copy
        d = copy.deepcopy(d)
        for s in d["vols"][str(vol)]["sections"]:
            s["blocks"] = s["blocks"][:n]
        return d

    # ── 자연 높이 측정 ──
    @staticmethod
    def _keys(d, vol):
        out = []
        for sec in d["vols"][str(vol)]["sections"]:
            for i, b in enumerate(sec["blocks"]):
                out.append((render_mod.key_of(vol, sec, i, b), sec, b))
        return out

    def _measure(self, cfg, d, vol, build_dir, m, log):
        keys = [k for k, _s, _b in self._keys(d, vol)]
        html_m = render_mod.write(cfg, d, vol, build_dir, mode="measure",
                                  log=log)
        self._stage(cfg, build_dir, log)
        h = measure.measure(html_m, os.path.join(build_dir, "measure.pdf"),
                            keys, m["body_top"],
                            render_mod.MEASURE_PAGE_H - 20.0, pad=0.0, log=log)
        measure.save(h, cfg.path(f"heights{vol}.json"), log, "지문 높이")
        return h

    # ── 축소율 ──
    def _cap(self, kind, m):
        """그 지문이 쓸 수 있는 높이(mm) — 안전 여유를 뺀 값.

        ⚠ 잉크 바닥으로 잰 높이는 상자 높이보다 조금 작다. 여유를 안 두면
          "재 보니 들어가는데 조판하면 다음 면으로 밀리는" 일이 생긴다
          (중요어휘 250330: 잰 값 248.9, 판면 252.6 인데 요약이 밀렸다).
        """
        kind = render_mod.SLOT_KIND[kind]
        if kind == "slot":
            return m["slot"] - 0.5
        if kind == "col":
            return m["body_h"] - 1.0
        return m["vocab_avail"] - m["vocab_safety"]

    def _fits(self, d, vol, heights, m, log):
        """칸을 넘는 지문 처리 — ① 활자 축소, ② 그래도 안 되면 **두 칸**.

        인디자인 경로는 ①만 하고, 그래도 넘치면 지면 밖으로 흘려 보냈다
        (완성본 광문2 Vol1 = 오버플로우 7건, 실제로 글이 잘려 나간다).
        여기서는 ② 로 물러서서 **글을 잃지 않는다.**
        """
        fits = {}
        for key, sec, _b in self._keys(d, vol):
            nat = heights.get(key)
            cap = self._cap(sec["kind"], m)
            if not nat or nat <= cap:
                continue
            step, lo = m["step_pt"], m["min_pt"]
            want = m["base_pt"] * cap / nat
            if want >= lo:
                fits[key] = {"pt": round(int(want / step) * step, 2)}
                continue
            if render_mod.SLOT_KIND[sec["kind"]] == "slot":
                cap2 = 2 * m["slot"] - 0.5
                if nat <= cap2:
                    fits[key] = {"span": 2}
                else:
                    w2 = m["base_pt"] * cap2 / nat
                    fits[key] = {"span": 2,
                                 "pt": round(max(lo, int(w2 / step) * step), 2)}
            else:
                # 한 단(253mm)보다 긴 지문 — 줄여도 안 들어간다(어법 19강
                # 07~08 = 321mm). 자르지 말고 **흘린다**: 다음 단·면으로
                # 이어지고 글은 하나도 잃지 않는다.
                fits[key] = {"flow": True}
        if fits:
            sh = [f["pt"] for f in fits.values() if f.get("pt")]
            sp = sum(1 for f in fits.values() if f.get("span") == 2)
            fl = sum(1 for f in fits.values() if f.get("flow"))
            log(f"  [맞춤] 칸을 넘는 지문 {len(fits)}개 — 활자 축소 {len(sh)}"
                + (f"(최소 {min(sh):.1f}pt)" if sh else "")
                + (f" · 두 칸 {sp}" if sp else "")
                + (f" · 흘림 {fl}" if fl else ""))
        else:
            log("  [맞춤] 넘치는 지문 없음")
        return fits

    def _save_fit_report(self, cfg, d, vol, heights, fits, m):
        import json
        rows = []
        for key, sec, b in self._keys(d, vol):
            nat = heights.get(key)
            cap = self._cap(sec["kind"], m)
            f = fits.get(key)
            if f or (nat and nat > cap):
                rows.append({"key": key, "section": sec["title"],
                             "header": b["header"], "natural_mm": nat,
                             "cap_mm": round(cap, 1),
                             "pt": (f or {}).get("pt"),
                             "span": (f or {}).get("span", 1),
                             "flow": bool((f or {}).get("flow")),
                             "fits": bool(f) and (
                                 nat <= cap * (((f.get("pt") or m["base_pt"])
                                                / m["base_pt"]) ** -1)
                                 if False else self._ok(nat, cap, f, m))})
        with open(cfg.path(f"fit{vol}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)

    @staticmethod
    def _ok(nat, cap, f, m):
        """축소·두 칸을 적용하고 나면 정말 들어가는가."""
        if not f:
            return nat <= cap
        if f.get("flow"):
            return True                     # 흘리면 언제나 담긴다
        cap2 = cap if f.get("span", 1) == 1 else 2 * m["slot"] - 0.5
        pt = f.get("pt") or m["base_pt"]
        return nat * pt / m["base_pt"] <= cap2 + 0.05

    # ── 배치 ──
    @staticmethod
    def _stage(cfg, build_dir, log):
        stage.stage_fonts(build_dir,
                          [f["file"] for f in cfg.get("fonts") or []],
                          log, required=True)
        theme = cfg.get("theme") or FinalSeries.theme
        stage.stage_theme(build_dir, cfg.resolve(theme)
                          if theme.endswith(".css") else theme, log)
        stage.stage_assets(build_dir,
                           cfg.resolve((cfg.section("assets") or {}).get(
                               "dir", "assets")))
        knobs.write(cfg, FinalSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)
        FinalSeries._stage_series_assets(build_dir)

    @staticmethod
    def _stage_series_assets(build_dir):
        """계열 자산(간지 워드마크)은 책 자산 **뒤에 덧붙인다**.

        `stage_assets` 는 폴더를 지우고 다시 넣으므로, 순서를 바꾸면 책이
        넣은 그림이 사라진다.
        """
        import shutil
        src = FinalSeries.series_asset("")
        if not os.path.isdir(src):
            return
        dst = os.path.join(build_dir, "assets")
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(src):
            shutil.copy2(os.path.join(src, n), os.path.join(dst, n))

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        return verify_mod.run(self, cfg, log, report)

    # ── 손잡이 ──
    def knobs(self, cfg):
        K = knobs.Knob
        return [
            K("metrics.slot", "mm", "사분면 한 칸", default=126.0, min=90,
              max=160, step=0.5, unit="mm", affects="배열·삽입 한 지문 칸",
              group="치수"),
            K("metrics.base_pt", "pt", "본문 활자", default=8.5, min=7, max=11,
              step=0.1, unit="pt", affects="지문 글자 크기", group="치수"),
            K("metrics.min_pt", "pt", "축소 하한", default=7.0, min=6, max=9,
              step=0.1, unit="pt", affects="넘칠 때 줄이는 하한", group="치수"),
        ]
