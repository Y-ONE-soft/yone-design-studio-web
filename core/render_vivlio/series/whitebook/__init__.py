"""프리미엄북 화이트북 계열 — 어휘 실전문제집(A4).

블랙북과 대비되는 점이 이 계열의 성격이다:
  · 블랙북은 문항 높이를 재서 **가변 배치**하지만, 화이트북은 **사분면 고정**이다
    (한 칸 122.5mm · 한 면 4문항 · Day 하나 = 정확히 5면).
    높이 측정은 배치가 아니라 **넘침 검사**에만 쓴다.
  · 정답은 뒤에 몰아서 Day 마다 새 면 · 2단.

빌드: (선택) 문항 높이 측정 → 본 조판 → 마감(TrimBox·파리티).
`--nomeasure` 는 높이 재측정 없이 본 조판만.
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, measure, probe, stage
from core.render_vivlio import verify as gate
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.whitebook import assets as assets_mod
from core.render_vivlio.series.whitebook import data as data_mod
from core.render_vivlio.series.whitebook import render as render_mod


class WhitebookSeries(Series):

    name = "whitebook"
    display = "프리미엄북 화이트북 (어휘 실전문제)"
    theme = "whitebook"

    # 미리보기는 높이 측정을 건너뛴다 — 배치가 고정이라 지면이 달라지지 않는다.
    render_opts = {"nomeasure": True}

    SAMPLE_DAYS = 1

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    def gen_theme(self, cfg, log):
        return assets_mod.build(cfg, log)

    @classmethod
    def _sample(cls, d):
        out = dict(d)
        out["days"] = (d.get("days") or [])[:cls.SAMPLE_DAYS]
        return out

    def build(self, cfg, log, sample=False, nomeasure=False, **_):
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)
        if sample:
            d = self._sample(d)
            log(f"[견본] Day {len(d['days'])}")
        m = render_mod.metrics_of(cfg)

        # 높이 측정 — 배치가 아니라 **넘침 검사**에 쓴다(사분면은 고정이다).
        sfx = "_견본" if sample else ""
        hp = cfg.path(f"heights{sfx}.json")
        if not nomeasure:
            keys = [f"{D['day']}-{it['no']}"
                    for D in d["days"] for it in D["problems"]]
            html_m = render_mod.write(cfg, d, build_dir, mode="measure",
                                      log=log)
            self._stage(cfg, build_dir, log)
            h = measure.measure(html_m, os.path.join(build_dir, "measure.pdf"),
                                keys, m["body_top"],
                                m["body_top"] + m["body_h"], pad=0.0, log=log)
            measure.save(h, hp, log, "문항 높이")

        html_path = render_mod.write(cfg, d, build_dir, log=log)
        self._stage(cfg, build_dir, log)
        out = cfg.out_pdf(sfx)
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
        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=True)
        theme = cfg.get("theme") or WhitebookSeries.theme
        stage.stage_theme(build_dir, cfg.resolve(theme)
                          if theme.endswith(".css") else theme, log)
        stage.stage_assets(build_dir,
                           cfg.resolve((cfg.section("assets") or {}).get(
                               "dir", "assets")))
        knobs.write(cfg, WhitebookSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)

    # ── 손잡이 ──
    def knobs(self, cfg):
        K = knobs.Knob
        c = lambda key, css, label, default, affects: K(       # noqa: E731
            "palette." + key, "color", label, css=css, default=default,
            affects=affects, group="색")
        return [
            c("teal", "--teal", "강조색", "#18a6c0", "문항 번호 · 탭 · 상표"),
            c("green", "--green", "탭 라벨", "#bfdb7f", "DAY 글자"),
            c("band", "--band", "머리 띠(문제)", "#d4deed", "문제면 머리 띠"),
            c("band_a", "--band-a", "머리 띠(정답)", "#dcdcd1", "정답면 머리 띠"),
            c("boxline", "--boxline", "상자 선", "#dcdcd1", "보기 · 지문 상자"),
            c("ans_no", "--ans-no", "정답 번호", "#00559f", "정답 항목 번호"),
            c("ans_nt", "--ans-nt", "정답 부연", "#58595b", "선지 해석 · 뜻"),
            c("pgnum", "--pgnum", "쪽번호", "#074481", "쪽번호"),
            K("metrics.slot", "mm", "사분면 한 칸", default=122.5, min=80,
              max=160, step=0.5, unit="mm", affects="문항 한 칸 높이",
              group="치수"),
            K("metrics.col_gap", "mm", "문제 단 사이", default=3.65, min=0,
              max=20, step=0.5, unit="mm", affects="두 단 간격", group="치수"),
            K("metrics.ans_gap", "mm", "정답 단 사이", default=6.25, min=0,
              max=20, step=0.5, unit="mm", affects="정답 두 단", group="치수"),
        ]

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf((cfg.section("verify") or {}).get("suffix", ""))
        d = data_mod.load(cfg)
        texts = probe.page_texts(pdf)
        m = render_mod.metrics_of(cfg)

        seq = self._sequence(d)
        gate.check_sequence(texts, seq, report)
        report.note(f"대조 항목 {len(seq):,}건")

        # 빈칸 유실 — 지문·보기의 밑줄 빈칸이 살아 있는가
        items = []
        for D in d["days"]:
            for it in D["problems"]:
                src = ""
                for b in it["blocks"]:
                    if b["t"] in ("passage", "bogi"):
                        src += " " + _plain(b.get("paras") or b.get("items"))
                    elif b["t"] in ("choice", "trans"):
                        src += " " + _plain(b["body"])
                items.append((f"{D['label']} {it['no']}", src,
                              _plain(it["stem"])[:24]))
        gate.check_gaps(items, texts, report)

        self._check_slots(cfg, d, m, report)
        self._check_day_pages(d, texts, m, report)
        return report

    # ── 사분면 넘침 ──
    @staticmethod
    def _check_slots(cfg, d, m, report):
        """문항 자연 높이가 사분면 한 칸을 넘는가 — 넘으면 아랫칸을 침범한다."""
        h = measure.load(cfg.path("heights.json"))
        if not h:
            return report.warn("문항 높이 표 없음 — `build` 로 한 번 재 둘 것")
        slot = m["slot"]
        over = []
        for D in d["days"]:
            for it in D["problems"]:
                v = h.get(f"{D['day']}-{it['no']}")
                if v is not None and v > slot:
                    over.append((D["label"], it["no"], v))
        if over:
            report.fail(f"사분면 넘침 {len(over)}건 (칸 {slot}mm): "
                        f"{[(a, b, c) for a, b, c in over[:6]]}")
        else:
            report.note(f"사분면 여유 최대 "
                        f"{max(h.values()):.1f}mm / {slot}mm")
        return over

    # ── Day 면수 ──
    @staticmethod
    def _check_day_pages(d, texts, m, report):
        """Day 하나 = 20문항 = 5면. 어긋나면 사분면 계약이 깨진 것이다."""
        want = -(-len(d["days"][0]["problems"]) // 4) if d["days"] else 0
        starts = []
        for i, t in enumerate(texts):
            # ⚠ `probe.norm` 은 공백을 지운다 — 라벨도 같이 지워서 맞출 것.
            nt = probe.norm(t)
            for D in d["days"]:
                if f"DAY{D['day']:02d}" in nt and "EXERCISE" in nt:
                    starts.append((D["label"], i + 1))
                    break
        bad = [(a, b) for (a, b), (_c, e) in zip(starts, starts[1:])
               if e - b != want]
        if bad:
            report.fail(f"Day 면수 이상(기대 {want}면): {bad[:6]}")
        else:
            report.note(f"Day 시작 면 {len(starts)}개 · 각 {want}면")
        return bad

    @staticmethod
    def _sequence(d):
        seq = []
        for D in d["days"]:
            for it in D["problems"]:
                seq.append((f"{D['label']} {it['no']}번 발문",
                            _plain(it["stem"])[:40]))
                for b in it["blocks"]:
                    if b["t"] == "passage":
                        seq.append((f"{D['label']} {it['no']}번 지문",
                                    _plain(b["paras"][0])[:50]))
                    elif b["t"] == "bogi":
                        for k, x in enumerate(b["items"]):
                            seq.append((f"{D['label']} {it['no']}번 보기{k + 1}",
                                        _plain(x)[:40]))
                    elif b["t"] == "choice":
                        seq.append((f"{D['label']} {it['no']}번 {b['mark']}",
                                    _plain(b["body"])[:40]))
                    elif b["t"] == "trans":
                        seq.append((f"{D['label']} {it['no']}번 영작",
                                    _plain(b["body"])[:40]))
        for D in d["days"]:
            for a in D["answers"]:
                seq.append((f"{D['label']} 정답 {a['no']}",
                            _plain(a["answer"])[:40]))
                for k, x in enumerate(a["notes"]):
                    seq.append((f"{D['label']} 정답 {a['no']} 부연{k + 1}",
                                _plain(x)[:40]))
        return seq


def _plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get("t", "")
    if x is None:
        return ""
    return "".join(_plain(i) for i in x)
