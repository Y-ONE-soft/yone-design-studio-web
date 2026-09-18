# -*- coding: utf-8 -*-
"""분석본 계열 검수.

공용 게이트(글자 유실·판면 넘침)는 백엔드가 돌린다. 계열이 보는 것:
  · 총 면수 = 1(앞표지) + 2·N — 짝-홀 쌍
  · 지문 번호 순서
  · 짝면에 「모의고사」 머리띠, 홀면에 「주제/요약」 라벨
"""
import os

from core.render_vivlio import probe
from core.render_vivlio.series.analysis import data as data_mod


def check(cfg, log, report):
    pdf = cfg.out_pdf()
    if not os.path.exists(pdf):
        report.fail(f"조판 결과 PDF 가 없다: {pdf}")
        return report
    d = data_mod.load(cfg)
    texts = probe.page_texts(pdf)
    n_pass = len(d.get("passages") or [])
    want = 1 + n_pass * 2
    if len(texts) != want:
        report.fail(f"면 수 어긋남 — 예상 {want}면(앞표지 1 + 지문 {n_pass}×2), 실제 {len(texts)}면")
    for i, p in enumerate(d.get("passages") or []):
        even = texts[1 + i * 2] if 1 + i * 2 < len(texts) else ""
        odd = texts[2 + i * 2] if 2 + i * 2 < len(texts) else ""
        if "모의고사" not in even and p.get("band"):
            report.warn(f"짝면(지문 {p.get('no')}) 에 머리띠가 없다")
        if "주제" not in odd and "요약" not in odd:
            report.warn(f"홀면(지문 {p.get('no')}) 에 주제/요약 라벨이 없다")
    report.note(f"분석본 검수 — 지문 {n_pass}편, 면 {len(texts)}")
    return report
