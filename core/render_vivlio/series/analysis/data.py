# -*- coding: utf-8 -*-
"""분석본 계열 — 원고 → data.json.

원고 견본을 못 받아 이 단계는 **아직 안 뚫려 있다**. 파일이 있으면 그것을 그대로
읽어 계열이 무엇을 기대하는지만 확인한다(구조 판정 파서는 원고를 보고 짠다 —
라벨 화이트리스트로 미리 짜지 않는다).

data.json 스키마 (완성본 PDF 실측 기준, 지문 한 편 당 한 항목):

    {
      "book": {"id": "...", "title": "...", "school": "배재고1", "period": "26-2-중간",
                 "subtitle": "2", "range": "고1 24년 10월 20~41-42번"},
      "passages": [
        {
          "no": 20,                     # 지문 번호 (모의고사 문항 번호)
          "src": {"grade": "고1", "year": 24, "month": 10, "no": "20"},
          "band": "모의고사 | 고1 24년 10월 20번",
          "title": "The Importance of Physical Activity in Daily Life",
          "topic":   "…",               # 오른쪽 면 주제 한 줄
          "summary": "…",               # 오른쪽 면 요약 한 줄
          "passage": [                  # 왼쪽 면 구문분석 지문 — 문단 목록
            {"runs": [{"t": "...", "sv": "S|V|O|C", "note": "…"}]}
          ],
          "translation": "짧은 운동을 …",   # 왼쪽 면 하단 한글 해석
          "grampt": ["…", "…"],           # GRAMMAR POINT 세로 컬럼
          "flow":   ["…", "…"],           # FLOW NOTE
          "question": {                    # 오른쪽 면 핵심기출문제
            "stem": "…", "passage": "…", "choices": ["①…", "②…", "③…", "④…", "⑤…"]
          },
          "chks":   ["주제/제목", "…"],   # 기출포인트 12칸
          "voca":   [{"w":"…","p":"…","m":"…"}]
        }
      ]
    }
"""
import json
import os


def path(cfg):
    return cfg.path("data.json")


def load(cfg):
    p = path(cfg)
    if not os.path.exists(p):
        raise FileNotFoundError(
            "data.json 이 없다 — 분석본 계열은 원고 견본이 없어 아직 파서가 없다.\n"
            f"  {p} 를 직접 만들거나(스키마: series/analysis/data.py 상단 주석)\n"
            "  원고 견본을 받은 뒤 build() 를 다시 짜야 한다.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build(cfg, log):
    """원고 → data.json — **미구현**.

    원고 견본이 없어 파서를 짜지 않았다. 원고를 받으면 여기에 구조 판정 파서를 짠다
    (라벨 화이트리스트 금지). 지금은 data.json 이 있으면 그것을 검증만 하고 넘긴다.
    """
    d = load(cfg)
    ps = d.get("passages") or []
    if not ps:
        raise ValueError("data.json 에 passages 가 비어 있다")
    nos = [p.get("no") for p in ps]
    if len(set(nos)) != len(nos):
        raise ValueError(f"지문 번호가 중복된다: {nos}")
    log(f"[분석본] data.json 확인 — 지문 {len(ps)}편")
    return d


def sample(d, n=3):
    return dict(d, passages=(d.get("passages") or [])[:n])
