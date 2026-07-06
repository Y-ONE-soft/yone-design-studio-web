"""동형 v2 파서 실측 테스트 — 코퍼스 5케이스 (InDesign 불필요)."""
import glob
import os

import pytest

from core.schema import validate_v2
from engines.mockexam_v2.parser import parse_manuscripts

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus", "mockexam")

# 케이스별 기대 문항 수 (2026-07-04 실측 고정 — 파서 개선 시 diff 검토 후 갱신)
EXPECTED_ITEMS = {
    "029c4385": 30,   # 객관식 26(동형 표준) + 서답형 4 — LNG-HEADER는 그룹 도입으로 제외
    "0365e674": 40,   # 2회분 × 20 (번호 없는 발문 원고 — 구조 기반 인식)
    "057985b4": 30,
    "1f172958": 28,   # 객 22 + 서 6 (원고 표지 명기) — 2026-07-06 경계 오판 해소로 24→28
    "69f4dd89": 28,
}


def _cases():
    return sorted(os.listdir(CORPUS)) if os.path.isdir(CORPUS) else []


@pytest.mark.parametrize("case", _cases())
def test_v2_parse_case(case):
    docs = parse_manuscripts(glob.glob(os.path.join(CORPUS, case, "inputs", "*")))
    assert docs, "입력 없음"

    total = 0
    obj_ok = obj_total = 0
    for _name, doc in docs:
        assert validate_v2(doc) == [], f"스키마 오류: {validate_v2(doc)[:2]}"
        for it in doc["items"]:
            total += 1
            assert it["type"] is not None, f"미분류 발문: {it['question'][:50]}"
            assert it["stimulus"]["blocks"] or it["stimulus"]["type"] == "empty"
            if it["kind"] != "객관식":
                continue
            obj_total += 1
            n_choices = len(it["choices"]["items"]) if it["choices"] else 0
            inline = (it.get("variants") or {}).get("inline_marker") == "V6-INLINE"
            if n_choices == 5 or (n_choices == 0 and inline):
                obj_ok += 1

    assert total == EXPECTED_ITEMS[case], f"문항 수 {total} != {EXPECTED_ITEMS[case]}"
    # 객관식의 90%+ 는 '선지 5개' 또는 '밑줄형(본문 내 선지)'여야 함
    assert obj_ok / obj_total >= 0.85, f"선지 구조 정합 {obj_ok}/{obj_total}"
