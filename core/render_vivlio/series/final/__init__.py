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
    # 한 면에 하나씩 재는 목록 — 목차처럼 큰 것을 넣으면 측정이 멎는다
    MEASURED = ("items", "problems")


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
            if any(f.get("lead") for f in fits.values()):
                fits, _h2 = self._refit(cfg, d, vol, build_dir, m, fits, log,
                                        heights)
            self._save_fit_report(cfg, d, vol, heights, fits, m)

        html_path = render_mod.write(cfg, d, vol, build_dir, fits=fits, log=log)
        self._stage(cfg, build_dir, log)
        out = cfg.out_pdf(self._suffix(cfg, sample))
        secs = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])

        # 섹션 띠는 **짝수 면에만** 러닝으로 나온다. 섹션 첫 면이 홀수일 수도
        # 있어 흐름에도 한 벌 심는데, 짝수면 그 자리에서 **글자가 두 번**
        # 찍혀 굵어진다(실측: 완성본보다 확연히 굵었다). 어느 면에서 시작할지는
        # 조판해 봐야 알므로, 한 번 짜고 **홀짝을 재서** 짝수인 섹션만 흐름
        # 글자를 빼고 다시 짠다.
        even, odd_pages = self._section_starts(out, d, vol)
        if (even or odd_pages) and not sample:
            if even:
                log(f"  [띠] 섹션 {sorted(even)} 은 짝수 면에서 시작"
                    f" — 흐름 띠 글자를 뺀다")
            if odd_pages:
                log(f"  [머리] {sorted(odd_pages)} 면은 섹션 첫 면(홀수)"
                    f" — 장 탭·워드마크를 뺀다")
            html_path = render_mod.write(cfg, d, vol, build_dir, fits=fits,
                                         log=None, plain_band=even,
                                         hide_headr=odd_pages)
            secs2 = cli.run_build(html_path, out, log=log, extra=["-f", "pdf"])
            secs += secs2

        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")

        res = {"pdf": out, "pages": pages, "seconds": round(secs, 1),
               "fits": len(fits)}
        spec = self._finish_spec(cfg)
        if spec and not sample:
            res["final"] = bleed_mod.finish(out, spec, log)
        return res

    @staticmethod
    def _section_starts(pdf, d, vol):
        """섹션 첫 면 조사 → (짝수에서 시작한 섹션들, 홀수 시작 면 번호들).

        짝수 시작 = 띠가 두 번 찍히는 자리(러닝과 흐름이 겹친다).
        홀수 시작 = 장 탭·워드마크를 꺼야 하는 면(완성본에는 없다).
        """
        import re
        try:
            import fitz
        except Exception:
            return set(), set()
        titles = {s["title"]: s["kind"]
                  for s in d["vols"][str(vol)]["sections"]}
        # ⚠ 꼬리말(`CHAPTER.01 문장 배열`)로 찾으면 안 된다 — 섹션 첫 면에는
        #   아직 안 나오고 그 다음 면부터 나온다(실측: 띠는 p2 인데 꼬리는 p3).
        #   **띠 자체**를 찾는다 — 판면 맨 위(25mm 안)에 큰 글자로 있는 제목.
        seen, even, odd = set(), set(), set()
        try:
            doc = fitz.open(pdf)
        except Exception:
            return set(), set()
        for i, pg in enumerate(doc):
            if not titles:
                break
            top = ""
            for b in pg.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for sp in l["spans"]:
                        if sp["bbox"][1] * 25.4 / 72 < 25 and sp["size"] > 15:
                            top += sp["text"]
            top = top.strip()
            for t in titles:
                if t.replace(" ", "") and t.replace(" ", "") in top.replace(" ", ""):
                    if t in seen:
                        break
                    seen.add(t)
                    if (i + 1) % 2 == 0:
                        even.add(titles[t])
                    else:
                        odd.add(i + 1)
                    break
        doc.close()
        return even, odd

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
        # 무선 제본 — 마지막 면(크레딧)은 **왼쪽(짝수)**. 본문이 홀수로 끝나면
        # 크레딧 앞에 빈 면을 한 장 넣는다(배재2 Vol1 26-2-중간: 80+1=81p 실측).
        # 짝수로 끝나는 책은 그대로다.
        spec.setdefault("end_on_left", {"page": 0})
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

    def _measure(self, cfg, d, vol, build_dir, m, log, fits=None,
                 label="지문 높이"):
        keys = [k for k, _s, _b in self._keys(d, vol)]
        html_m = render_mod.write(cfg, d, vol, build_dir, fits=fits,
                                  mode="measure", log=log)
        self._stage(cfg, build_dir, log)
        h = measure.measure(html_m, os.path.join(build_dir, "measure.pdf"),
                            keys, m["body_top"],
                            render_mod.MEASURE_PAGE_H - 20.0, pad=0.0, log=log)
        measure.save(h, cfg.path(f"heights{vol}.json"), log, label)
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
            # 0.5 = 잉크 여유, 0.5 = 답줄과 다음 지문 제목 사이 숨(완성본은
            # 최소 5.7pt 인데 여유가 없으면 4.4pt 까지 붙었다).
            return m["slot"] - 1.0
        if kind == "col":
            return m["body_h"] - 1.0
        return m["vocab_avail"] - m["vocab_safety"]

    def _fits(self, d, vol, heights, m, log):
        """칸을 넘는 지문 처리 — **활자 크기는 그대로 둔다**(사용자 확정).

        ① 한두 줄 넘침 → **행간만 조금 조여** 한 칸에 앉힌다.
        ② 그보다 길면 → **두 칸**(사분면), 한 단짜리 섹션은 **흘림**.

        인디자인 경로는 활자를 7pt 까지 줄이고 그래도 넘치면 지면 밖으로
        흘려 글을 잘라 냈다(완성본 광문2 Vol1 = 오버플로우 7건). 여기서는
        글자 크기가 책 전체에서 하나로 유지되고, 글도 잃지 않는다.
        """
        fits = {}
        for key, sec, _b in self._keys(d, vol):
            nat = heights.get(key)
            cap = self._cap(sec["kind"], m)
            if not nat or nat <= cap:
                continue
            fits[key] = self._one_fit(sec["kind"], nat, cap, m)
        self._log_fits(fits, log)
        return fits

    @staticmethod
    def _cap2(kind, m):
        """두 칸을 줬을 때의 높이.

        ⚠ 어법·영작(면당 두 단)에는 **두 칸이 없다.** 완성본은 긴 지문도
          한 단에 두고 넘치면 이어 흘린다 — 전폭 한 단으로 깔면 그 면만
          글줄이 두 배로 길어지고 한 면을 통째로 쓴다(실증: 명일3 3면).
        어휘(면당 한 지문)도 두 칸이 없다.
        """
        k = render_mod.SLOT_KIND[kind]
        if k == "slot":
            return 2 * m["slot"] - 0.5          # 사분면 두 칸 = 한 단
        return None

    @staticmethod
    def _one_fit(kind, nat, cap, m):
        """한 칸에 앉히는 사다리 — ①행간 조임 ②두 칸 ③흘림.

        ⚠ 경계는 '몇 줄 넘쳤나' 가 아니라 **행간 하한**이다. 완성본도 그렇게
          한다(실측: 광문3 17강 05 는 26줄을 8.3% 조여 한 칸에 앉혔다).
          줄 수로 끊으면 조이면 들어갈 지문이 두 칸으로 가 아래 칸이 빈다.
        """
        fx = m["fixed_mm"]
        lead = (cap - fx) / max(1.0, nat - fx)
        if lead >= m["min_lead"]:
            return {"lead": round(lead, 4)}
        cap2 = FinalSeries._cap2(kind, m)
        if cap2 is None:
            return {"flow": True}               # 어휘는 흘리는 수밖에 없다
        if nat <= cap2:
            return {"span": 2}
        fx = m["fixed_mm"]
        lead = (cap2 - fx) / max(1.0, nat - fx)
        if lead >= m["min_lead"]:
            return {"span": 2, "lead": round(lead, 4)}
        return {"flow": True}          # 두 칸으로도 안 되면 흘린다

    @staticmethod
    def _log_fits(fits, log):
        if not fits:
            return log("  [맞춤] 넘치는 지문 없음")
        ld = [f["lead"] for f in fits.values() if f.get("lead")]
        sp = sum(1 for f in fits.values() if f.get("span") == 2)
        fl = sum(1 for f in fits.values() if f.get("flow"))
        log(f"  [맞춤] 칸을 넘는 지문 {len(fits)}개 — 행간 조임 {len(ld)}"
            + (f"(최대 {100 * (1 - min(ld)):.1f}%)" if ld else "")
            + (f" · 두 칸 {sp}" if sp else "")
            + (f" · 흘림 {fl}" if fl else ""))

    def _refit(self, cfg, d, vol, build_dir, m, fits, log, heights=None):
        """조인 채로 **다시 재서** 정확한 행간을 푼다.

        높이는 `H(L) = F + (H1 − F)·L` 꼴이다(F = 글줄이 아닌 부분 — 헤더·
        답란·상자 여백). 두 점(L=1 과 첫 시도 L)이 있으면 F 와 목표 L 이
        **정확히** 풀린다. 한 번에 못 맞추는 이유가 이 F 를 몰라서다.
        하한(10%)에 닿으면 두 칸으로 물러선다 — 넘친 채로 내보내지 않는다.
        """
        h2 = self._measure(cfg, d, vol, build_dir, m, log, fits=fits,
                           label="재측정")
        h1 = heights or {}
        changed = 0
        for key, sec, _b in self._keys(d, vol):
            f = fits.get(key)
            if not f or not f.get("lead") or f.get("flow"):
                continue
            a, b = h1.get(key), h2.get(key)
            L = f["lead"]
            if not a or not b or abs(1.0 - L) < 1e-6:
                continue
            fixed = (b - L * a) / (1.0 - L)          # 글줄이 아닌 부분
            fixed = min(max(fixed, 0.0), a - 1.0)
            cap = self._cap(sec["kind"], m) - 0.3    # 여유 0.3mm
            want = (cap - fixed) / max(1.0, a - fixed)
            if want >= 1.0:
                fits.pop(key)                        # 애초에 안 넘쳤다
            elif want >= m["min_lead"]:
                if abs(want - L) > 1e-4:
                    fits[key] = dict(f, lead=round(want, 4))
                    changed += 1
                continue
            else:
                fits[key] = ({"span": 2}
                             if self._cap2(sec["kind"], m) is not None
                             else {"flow": True})
            changed += 1
        if changed:
            log(f"  [맞춤] 재측정으로 {changed}개 정정")
            self._log_fits(fits, log)
        return fits, h2

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
                             "lead": (f or {}).get("lead"),
                             "span": (f or {}).get("span", 1),
                             "flow": bool((f or {}).get("flow")),
                             "fits": bool(f) and (
                                 nat <= cap * (((f.get("pt") or m["base_pt"])
                                                / m["base_pt"]) ** -1)
                                 if False else self._ok(nat, cap, f, m,
                                                        sec["kind"]))})
        with open(cfg.path(f"fit{vol}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)

    def _ok(self, nat, cap, f, m, kind="arrange"):
        """행간 조임·두 칸을 적용하고 나면 정말 들어가는가."""
        if not f:
            return nat <= cap
        if f.get("flow"):
            return True                     # 흘리면 언제나 담긴다
        lim = cap if f.get("span", 1) == 1 else (self._cap2(kind, m) or cap)
        fx = m["fixed_mm"]
        lead = f.get("lead") or 1.0
        return fx + (nat - fx) * lead <= lim + 0.05

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
            K("metrics.over_lines", "number", "행간으로 흡수", default=2.0,
              min=0, max=6, step=0.5, unit="줄",
              affects="이만큼 넘치면 행간만 조임(넘으면 두 칸)", group="치수"),
            K("metrics.min_lead", "number", "행간 조임 하한", default=0.90,
              min=0.8, max=1.0, step=0.01, unit="배",
              affects="행간을 여기까지만 조인다", group="치수"),
        ]
