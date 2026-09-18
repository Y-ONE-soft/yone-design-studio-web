# -*- coding: utf-8 -*-
"""분석본 계열(analysis) — 모의고사 지문 한 편에 짝면 2쪽(왼쪽 구문분석·오른쪽 문항+FLOW).

첫 틀 = 「스텝업 분석본 (민트·A4)」(배재고1 · 2026-10). 판형 A4, 도련 3mm.
지면(실측, 완성본 PDF 카탈로그 `_intake/23d89f0d/ref.pdf`):

    앞표지(1P) : 학교·시리즈·호수·범위
    본문(짝-홀 반복)
        짝면(왼쪽)  청록 머리띠 「모의고사 | 학년 회차 N번」·GRAMMAR POINT 세로 컬럼
                     구문분석 영어 지문(S/V/O·문법 라벨 첨자)·한글 해석 하단
        홀면(오른쪽) 「주제 · 요약」 2줄 라벨 · 핵심기출문제 상자(지문+선택지)
                     FLOW NOTE 상자 · 기출포인트 12칸 체크 · VOCA 다열 표

책은 지문 목록으로 만들어진다(원고 견본 없음 — config.manuscript 항목이 뭘 받는지 적어 둔다).
"""
import os

from core.render_vivlio import bleed as bleed_mod
from core.render_vivlio import cli, stage
from core.render_vivlio.series.analysis import data as data_mod
from core.render_vivlio.series.analysis import render as render_mod
from core.render_vivlio.series.analysis import verify as verify_mod
from core.render_vivlio.series.base import Series

FONTS = [
    "NotoSansCJKkr-Regular.otf", "NotoSansCJKkr-Medium.otf",
    "NotoSansCJKkr-Bold.otf",
    "GmarketSansLight.otf", "GmarketSansMedium.otf", "GmarketSansBold.otf",
    "EliceDXNeolliOTF-Bold.otf",
    "JalnanOTF.otf",
]


class AnalysisSeries(Series):
    name = "analysis"
    display = "스텝업 분석본 계열 (A4·짝-홀 쌍면)"
    theme = "analysis"

    style_names = {
        "spread": "지문 짝면", "even": "왼쪽면(구문분석)", "odd": "오른쪽면(문항)",
        "band": "머리띠", "batch": "지문 배지", "grampt": "GRAMMAR POINT 컬럼",
        "passage": "구문분석 지문", "trans": "한글 해석",
        "topic": "주제 줄", "summary": "요약 줄", "qbox": "핵심기출문제 상자",
        "flow": "FLOW NOTE 상자", "chks": "기출포인트 12칸", "voca": "VOCA 표",
        "folio": "쪽번호", "footer": "러닝 푸터",
    }

    def gen_data(self, cfg, log):
        return data_mod.build(cfg, log)

    def build(self, cfg, log, sample=False, **_):
        bd = cfg.build_dir
        os.makedirs(bd, exist_ok=True)
        d = data_mod.load(cfg)
        if sample:
            d = data_mod.sample(d)
        html_p = render_mod.write(cfg, d, bd, log=log)
        self._stage(cfg, bd, log)
        out = cfg.out_pdf()
        secs = cli.run_build(html_p, out, log=log, extra=["-f", "pdf"])
        from core.render_vivlio import probe
        pages = probe.page_count(out)
        log(f"OK  {secs:.1f}s · {pages}p → {out}")
        bleed_mod.finish(out, cfg.finish_spec(), log)
        return {"pdf": out, "pages": pages, "seconds": round(secs, 1)}

    def verify(self, cfg, log, report):
        return verify_mod.check(cfg, log, report)

    @staticmethod
    def _stage(cfg, bd, log):
        stage.stage_fonts(bd, [f["file"] for f in cfg.get("fonts") or []], log, required=False)
        theme = cfg.get("theme") or AnalysisSeries.theme
        stage.stage_theme(bd, cfg.resolve(theme) if theme.endswith(".css") else theme, log)
        stage.stage_assets(bd, cfg.resolve((cfg.section("assets") or {}).get("dir", "assets")))
        stage.stage_overrides(cfg, bd)
        stage.stage_book_assets(cfg, bd)
