# -*- coding: utf-8 -*-
"""동형모의고사 계열(mockexam) — 학교 프로파일이 조판을 구동하는 B4 시험지.

조판 코드는 이 폴더의 build·markup·theme·profile·score 가 다 한다(`BRIEF.md`). 이 파일은
그것을 계열 인터페이스(`Series`)에 얹어 카탈로그·작업대·bin/viv 가 다른 계열과 똑같이
다루게 하는 얇은 껍데기다.

책 config:
    "series": "mockexam"
    "book": {"school": "배재고1", ...}      ← 학교키(배재1)는 여기서, 없으면 원고 파일명에서
    "manuscript": {"dir": "원고", "files": {"exam": "배재고1_동형_1회_원고.hwpx"}}
"""
import json
import os

from core.render_vivlio.series.base import Series


class MockexamSeries(Series):
    name = "mockexam"
    display = "동형모의고사 계열 (B4·학교 프로파일 구동)"
    theme = ""                      # 학교 프로파일에서 theme.py 가 CSS 를 생성한다

    def _key(self, cfg):
        from core.render_vivlio.series.mockexam import profile as P, run
        for cand in ((cfg.book or {}).get("school") or "", cfg.manuscript("exam")):
            k = run.school_key(cand)
            if k:
                return k
        raise ValueError(f"학교키를 못 정했다 — book.school 또는 원고 파일명에 학교·학년 "
                         f"(가능: {', '.join(P.available())})")

    def gen_data(self, cfg, log):
        """원고(hwp·hwpx·docx) → data.json(IR)."""
        from engines.mockexam_v2.parser import build_ir, extract_file_paragraphs
        src = cfg.manuscript("exam")
        ir = build_ir(extract_file_paragraphs(src))
        p = cfg.path("data.json")
        json.dump(ir, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"data.json ← {os.path.basename(src)} · 학교 {self._key(cfg)}")
        return p

    def build(self, cfg, log, **_):
        from core.render_vivlio.series.mockexam import build as B
        ir = json.load(open(cfg.path("data.json"), encoding="utf-8"))
        r = B.render(ir, self._key(cfg), cfg.out_pdf(), log=log, build_dir=cfg.build_dir)
        for w in r.get("warnings") or []:
            log(f"⚠ {w}")
        log(f"OK  {r['seconds']:.1f}s · {r['pages']}p → {r['pdf']}")
        return {"pdf": r["pdf"], "pages": r["pages"], "seconds": r["seconds"]}
