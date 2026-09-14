"""Step3 지문 출처 [from …] 는 인쇄하지 않는다 (사용자 지시 2026-09-14 — 기본값)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engines.workbook_v2.plan as PL  # noqa: E402


def test_from_source_regex():
    m = PL._RE_S3_FROM_SRC.match
    assert m("[from The Brain by David Eagleman]")
    assert m("[From Space Exploration by Joseph Harris]")
    # 업체 원고가 같은 줄에 붙여 오는 쪽 이음 표시도 한 줄째
    assert m("[from The Brain by David Eagleman]                  261번 계속")
    assert not m("from the nest to find fresh vegetation")
    assert not m("[조건]")
    assert not m("[from]")


def test_build_step3_drops_from_source_line():
    item = {"question_num": "39", "code": "260939", "paragraphs": [
        {"text": "다음 글의 요지로 가장 적절한 것은? [39]", "kind": "Q"},
        {"text": "With millions of members in a colony, leaf-cutter ants "
                 "cultivate their own food.", "kind": "P"},
        {"text": "[from The Brain by David Eagleman]", "kind": "UNKNOWN"},
        {"text": "① The ants rely on nature.", "kind": "C"},
    ]}
    out = PL.build_step3({"normal": [item]}, workbook_type="모의고사",
                         only="normal")
    texts = [p.get("t") or "" for u in out["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert not any("[from" in t for t in texts), texts
    assert any("leaf-cutter ants" in t for t in texts)
