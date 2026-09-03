"""단어장 계열(vocacard) — 이의고2. 낱말 1행 = 카드 1개, 구간(교과서/부교재/모의고사)
3파트로 흐르는 단권 단어장.

`vocabook`(상일·배재보카)은 Day+4섹션+워크북 구조라 원고 형식이 다르다. 여기는
Day 도, Part2 워크북도 없이 원고 표 한 행이 곧 카드 하나다 — 별도 계열로 둔다.

**저수준 함수는 중복하지 않는다.** 낱말 카드 마크업(`.w-top/.w-lead/.w-row`),
품사 배지, 예문·유반의어 서식, 헤더 4면 체계(밴드·마름모·탭·측면 라벨)는 전부
`series.vocabook` 모듈을 그대로 불러 쓴다 — 구조가 같기 때문. **CSS 만 자체
파일**(`themes/vocacard.css`)을 쓰는데, `theme.py` 의 build_css() 가 파일 텍스트를
치환하는 방식이라 계열마다 스타일시트가 한 벌 필요해서다(vocabook.css 를 건드리면
상일보카가 흔들린다 — 파일을 나눠 원천적으로 막는다).

Day 가 없으므로 **2패스가 아니라 1패스**다: PART 시작 면(3개뿐)에 큰 헤더를 인플로우로
얹고, 이어지는 면은 CSS `position: running()` 이 자동으로 4mm 띠+작은 탭을 이어 보여준다
(호출 시점에 덮어쓸 때까지 유지되는 것이 GCPM running() 의 성질이라 별도 규칙이 필요 없다).
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, knobs, probe, stage
from core.render_vivlio.series.base import Series
from core.render_vivlio.series.vocacard import data as data_mod
from core.render_vivlio.series.vocacard import render as render_mod
from core.render_vivlio.series.vocacard import theme as theme_mod


class VocacardSeries(Series):

    name = "vocacard"
    display = "단어장 카드형 (이의고2)"
    theme = ""          # 계열 테마는 책 팔레트로 매 빌드 생성한다

    style_names = {
        "day-open": "PART 한 벌", "vc": "낱말 카드", "w-word": "표제어",
        "w-mean": "뜻", "sec-head": "구간 소제목", "r-ex": "예문",
        "r-syn": "유반의어", "r-def": "설명 행",
    }

    # ── ① 원고 → data.json ──
    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    # ── ② 팔레트/치수 → theme.css ──
    def gen_theme(self, cfg, log):
        return theme_mod.write(cfg, os.path.join(cfg.build_dir, "theme.css"), log)

    # ── ③ 조판 (1패스 — Day 가 없어 2패스 덧칠이 필요 없다) ──
    def build(self, cfg, log, sample=False, **_):
        sample = bool(sample)
        build_dir = cfg.build_dir
        os.makedirs(build_dir, exist_ok=True)
        d = data_mod.load(cfg)

        suffix = "_견본" if sample else ""
        out = cfg.out_pdf(suffix)

        stage.stage_fonts(build_dir, [f["file"] for f in cfg.get("fonts") or []],
                          log, required=False)
        theme_mod.write(cfg, os.path.join(build_dir, "theme.css"), log)

        stage.write_css(build_dir, "pages.css")   # 자리만 — 이 계열은 2패스가 없다
        knobs.write(cfg, VocacardSeries(), build_dir)
        stage.stage_overrides(cfg, build_dir)
        stage.stage_book_assets(cfg, build_dir)
        html_path = render_mod.write(cfg, d, build_dir, sample=sample, log=log)
        t = cli.run_build(html_path, out, log=log)

        npages = probe.page_count(out)
        log(f"OK  {t:.1f}s (1패스) · {npages}p → {out}")

        res = {"pdf": out, "pages": npages, "seconds": round(t, 1), "passes": 1}
        if not sample:
            spec = cfg.finish_spec()
            if spec:
                res["final"] = bleed_mod.finish(out, spec, log)
        return res

    # ── 손잡이 ──
    def knobs(self, cfg):
        from core.render_vivlio.series.vocabook.theme import DEFAULT_METRICS as D
        K = knobs.Knob
        col = lambda key, label, affects, g="색": K(          # noqa: E731
            "palette.common." + key, "color", label, affects=affects,
            group=g, resettable=False)
        mm = lambda key, label, lo, hi, affects, g="치수": K(  # noqa: E731
            "metrics." + key, "mm", label, default=D[key], min=lo, max=hi,
            step=0.1, unit="mm", affects=affects, group=g)
        out = [
            col("hl", "강조색", "예문 속 낱말 강조"),
            col("label", "라벨 글자", "행 라벨"),
            col("rule", "카드 테두리", "낱말 카드 테두리"),
            col("gray", "보조 먹", "해석 · 설명"),
            col("ink", "본문 먹", "본문 글자", "고급"),
        ]
        for sec, pal in sorted((cfg.section("palette") or {})
                               .get("sections", {}).items()):
            name = (pal or {}).get("label") or sec
            for sub, ko in (("main", "주색"), ("pale", "연한색"),
                            ("sub", "보조색")):
                if sub in (pal or {}):
                    out.append(K(f"palette.sections.{sec}.{sub}", "color",
                                 f"{name} {ko}", affects=f"{name} 파트",
                                 group="섹션", resettable=False))
        out += [
            mm("band_h", "시작면 밴드 높이", 6, 30, "PART 시작면 머리 밴드"),
            mm("strip_h", "이후 면 띠 높이", 2, 14, "이어지는 면 띠"),
            mm("margin_top", "본문 상단 여백", 10, 40, "본문 시작"),
            mm("margin_bottom", "본문 하단 여백", 6, 30, "본문 아래"),
            mm("mgn_x", "좌우 여백", 10, 40, "판면 좌우"),
            mm("lab_w", "라벨 열 폭", 12, 45, "왼쪽 라벨 열", "고급"),
        ]
        return out

    # ── ④ 계열 검수 ──
    def verify(self, cfg, log, report):
        pdf = cfg.out_pdf(cfg.section("verify").get("suffix", ""))
        n = probe.page_count(pdf)
        report.note(f"{n}p")
        want = (cfg.section("options") or {}).get("expect", {}).get("pages")
        if want is not None and n != want:
            report.fail(f"{n}p (기대 {want}p)")
        return report
