"""스타일 룩업 테스트 — 코퍼스 전 단락이 KeyError 없이 해결되는지 포함."""
import json
import os

import pytest

from core.structure import classify_paragraphs
from core.structure.style_resolver import resolve_style

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_step3_basics():
    assert resolve_style("workbook", "STEP3", "Q") \
        == "STEP 03 > S_실전문제 번호 수정 올림포스"
    assert resolve_style("workbook", "STEP3", "GH") is None       # 제거 대상
    # P 계열은 허용 스타일 배열 (JSX가 밑줄 변형을 상황별로 적용 — E2E 파일럿 반영)
    p_styles = resolve_style("workbook", "STEP3", "P")
    assert isinstance(p_styles, list)
    assert "STEP 03 > 실전 문제 지문 올림포스_" in p_styles
    assert "STEP 03 > 지문 밑줄 있음" in p_styles


def test_override():
    assert resolve_style("workbook", "STEP3", "Q",
                         overrides={"Q": "커스텀 > 발문"}) == "커스텀 > 발문"


def test_wildcard_and_missing():
    assert resolve_style("workbook", "STEP2B1", "P") == "STEP 02 > B1_어법 OX"
    with pytest.raises(KeyError):
        resolve_style("workbook", "STEP3", "존재안함")
    with pytest.raises(KeyError):
        resolve_style("없는교재", "STEP3", "Q")


def test_corpus_step3_full_coverage():
    """골든 코퍼스 workbook Step3의 모든 단락이 스타일 결정 가능해야 한다."""
    base = os.path.join(TESTS_DIR, "corpus", "workbook")
    n = 0
    for case in sorted(os.listdir(base)):
        g = os.path.join(base, case, "golden", "content.json")
        c = json.load(open(g, encoding="utf-8"))
        step3 = c.get("steps", {}).get("step3") or {}
        for group in ("normal", "short"):
            for item in step3.get(group, []) or []:
                for r in classify_paragraphs(item.get("paragraphs", [])):
                    if r["kind"] == "BLANK":
                        continue
                    resolve_style("workbook", "STEP3", r["kind"],
                                  has_underline=r.get("has_underline"))
                    n += 1
    assert n > 2000  # 커버리지 실효성 가드
